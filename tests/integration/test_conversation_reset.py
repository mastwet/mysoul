import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mysoul.api import create_app
from mysoul.config import Settings
from mysoul.domain import Event, Goal, Scope
from mysoul.model import ReplayModel
from mysoul.service import SoulService
from mysoul.timeline import TimelineStore


@pytest.fixture
def client(tmp_path):
    settings = Settings(data_dir=tmp_path)
    soul = SoulService(settings, model=ReplayModel())
    with TestClient(
        create_app(settings, token="reset-test", service=soul), base_url="http://127.0.0.1:8765"
    ) as client:
        client.headers.update({"Authorization": "Bearer reset-test"})
        csrf = client.get("/api/session").json()["csrf"]
        client.headers.update({"Origin": "http://127.0.0.1:8765", "X-CSRF-Token": csrf})
        yield client, soul


def seed(soul, text="旧聊天原文"):
    event = Event(
        source="local-owner", sender="owner", content=text, dedup_key=text, trust="owner_command"
    )
    soul.store.add_event(event)
    soul.store.record_interaction(
        event, {"event_id": event.id, "input": text, "text": "旧回复", "choice": "owner_served"}
    )
    return event


def test_reset_archives_chat_clears_short_term_and_preserves_identity_memory(client):
    client, soul = client
    old = seed(soul)
    soul.recap.publish(0, "旧短期摘要", [])
    from mysoul.domain import Evidence

    soul.store.add_evidence(Evidence(id="preserved-memory", text="长期事实", source="test"))
    memory_before = soul.store.db.execute("SELECT * FROM memory_queue").fetchall()
    persona = soul.persona.current()
    goal = Goal(objective="旧后台待办", lane="background")
    soul.store.save_goal(goal)
    before = soul.store.load_subject()
    originals = soul.store.events()
    response = client.post("/api/conversation/reset", json={"expected_version": 0})
    assert response.status_code == 200
    assert response.json()["revision"] == 1
    assert response.json()["recap"]["text"] == ""
    assert soul.recap.current().text == ""
    assert soul.recap.current().invalidation_epoch == 1
    assert soul.recap.history()[1].text == "旧短期摘要"
    assert soul.persona.current() == persona
    assert soul.store.evidence("preserved-memory").text == "长期事实"
    assert soul.store.db.execute("SELECT * FROM memory_queue").fetchall() == memory_before
    assert soul.store.events() == originals
    assert soul.store.get("interaction", old.id)["text"] == "旧回复"
    assert soul.store.goal(goal.id).cancelled
    assert soul.store.load_subject().dispatch_epoch == before.dispatch_epoch + 1
    assert soul.store.load_subject().model_calls == before.model_calls
    assert client.get("/api/timeline").json()["items"] == []
    archived = client.get("/api/conversation/archives/1").json()
    assert archived["items"][0]["body"]["input"] == old.content
    assert soul.activities.attention.snapshot(Scope())["handled_inputs"] == []
    assert soul.activities.attention.snapshot(Scope())["background_tasks"] == []
    assert all(s["cleared"] for s in soul.store.all("cognitive_source"))


def test_stale_reset_cannot_erase_the_new_conversation_and_archive_is_bounded(client):
    client, soul = client
    first = seed(soul, "first")
    assert client.post("/api/conversation/reset", json={"expected_version": 0}).status_code == 200
    second = seed(soul, "second")
    assert client.post("/api/conversation/reset", json={"expected_version": 0}).status_code == 409
    page = client.get("/api/timeline?after_change=0").json()
    assert page["session_revision"] == 1
    assert [i["source_id"] for i in page["items"]] == [second.id]
    assert client.post("/api/conversation/reset", json={"expected_version": 1}).status_code == 200
    assert [i["source_id"] for i in client.get("/api/conversation/archives/1").json()["items"]] == [
        first.id
    ]
    assert [i["source_id"] for i in client.get("/api/conversation/archives/2").json()["items"]] == [
        second.id
    ]
    assert client.get("/api/conversation/archives/999").status_code == 404


def test_delayed_old_interaction_cannot_reenter_chat_recap_or_attention(client):
    client, soul = client
    old = seed(soul)
    client.post("/api/conversation/reset", json={"expected_version": 0})
    soul.store.record_interaction(
        old, {"event_id": old.id, "text": "迟到回复", "choice": "owner_served"}
    )
    assert client.get("/api/timeline").json()["items"] == []
    assert soul.activities.attention.snapshot(Scope())["handled_inputs"] == []
    assert all(s.get("cleared") for s in soul.store.all("cognitive_source"))
    assert soul.recap.pending() == []
    assert soul.compression.archives.frontier(Scope()) == []
    new = seed(soul, "全新聊天")
    assert [i.source_id for i in TimelineStore(soul.store).page().items] == [new.id]
    assert soul.dialogue_history(Scope())[0][0].event_id == new.id


def test_reset_is_protected_and_invalid_input_does_not_mutate(client):
    client, soul = client
    for headers, expected in [
        ({"Authorization": "bad"}, 401),
        ({"Origin": "https://evil.invalid"}, 403),
        ({"X-CSRF-Token": "bad"}, 403),
    ]:
        assert (
            client.post(
                "/api/conversation/reset", json={"expected_version": 0}, headers=headers
            ).status_code
            == expected
        )
    assert client.post("/api/conversation/reset", json={"expected_version": -1}).status_code == 422
    assert soul.store.get("conversation", "current") is None


def test_boundary_survives_restart_and_archive_paging(client):
    client, soul = client
    for n in range(4):
        seed(soul, f"old-{n}")
    client.post("/api/conversation/reset", json={"expected_version": 0})
    page = client.get("/api/conversation/archives/1?limit=2").json()
    assert page["has_more"]
    other = client.get(f"/api/conversation/archives/1?limit=2&before={page['next_before']}").json()
    assert len({i["id"] for i in page["items"] + other["items"]}) == 4
    from mysoul.storage import StateStore

    reopened = StateStore(Path(soul.store.db.execute("PRAGMA database_list").fetchone()[2]))
    try:
        assert TimelineStore(reopened).page().items == []
        assert (
            json.loads(
                reopened.db.execute(
                    "SELECT body FROM objects WHERE kind='conversation'"
                ).fetchone()[0]
            )["revision"]
            == 1
        )
    finally:
        reopened.close()


def test_old_task_cannot_become_current_when_its_receipt_arrives_late(client):
    from mysoul.cognition import CognitiveStore
    from mysoul.domain import ActivityRecord

    client, soul = client
    goal = Goal(objective="旧任务", lane="background")
    soul.store.save_goal(goal)
    activity = ActivityRecord(goal_id=goal.id, status="active")
    soul.store.save_activity(activity)
    soul.store.put("activity_context", activity.id, {"scope": Scope().model_dump()})
    assert client.post("/api/conversation/reset", json={"expected_version": 0}).status_code == 200
    soul.store.save_goal(soul.store.goal(goal.id))
    soul.store.save_activity(soul.store.activity(activity.id))
    CognitiveStore(soul.store).capture_outcome(activity.id)
    assert soul.activities.attention.background_tasks() == []
    assert soul.store.all("cognitive_source") == []
    assert client.get("/api/timeline").json()["items"] == []


def test_reset_rolls_back_every_change_if_archiving_fails(client):
    import sqlite3

    client, soul = client
    seed(soul)
    before = soul.store.load_subject()
    recap = soul.recap.current()
    soul.store.db.executescript(
        "CREATE TRIGGER reject_reset BEFORE INSERT ON objects WHEN "
        "NEW.kind='conversation_archive' BEGIN SELECT RAISE(ABORT,'failure'); END;"
    )
    from mysoul.conversation import ConversationStore

    with pytest.raises(sqlite3.IntegrityError):
        ConversationStore(soul.store).reset(0)
    assert soul.store.load_subject() == before
    assert soul.recap.current() == recap
    assert len(client.get("/api/timeline").json()["items"]) == 1


@pytest.mark.asyncio
async def test_reset_during_real_owner_turn_rejects_the_old_reply(tmp_path):
    import asyncio

    from mysoul.conversation import ConversationStore
    from mysoul.domain import ActivityDecision

    started, release = asyncio.Event(), asyncio.Event()
    model = ReplayModel()

    async def delayed(context, limits):
        started.set()
        await release.wait()
        return ActivityDecision(activity="read_chat", chat_action="reply", reply="旧轮次回复")

    model.decide = delayed
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        running = asyncio.create_task(soul.owner_message("重置前的输入"))
        await asyncio.wait_for(started.wait(), 3)
        ConversationStore(soul.store).reset(0)
        release.set()
        result = await asyncio.wait_for(running, 3)
        assert result["error"] == "superseded"
        assert result["text"] == ""
        assert TimelineStore(soul.store).page().items == []
        assert soul.recap.current().text == ""
        assert not soul.cognition.sources.pending_window(4000)


def test_idle_feedback_capture_cannot_recreate_old_failed_task_sources(client):
    from mysoul.domain import ActivityRecord

    client, soul = client
    goal = Goal(objective="旧失败任务", status="failed")
    soul.store.save_goal(goal)
    activity = ActivityRecord(goal_id=goal.id, status="failed")
    soul.store.save_activity(activity)
    soul.store.put("activity_context", activity.id, {"scope": Scope().model_dump()})
    assert client.post("/api/conversation/reset", json={"expected_version": 0}).status_code == 200
    soul.activities.capture_feedback()
    assert soul.recap.pending() == []
    assert soul.store.all("task_feedback") == []
    assert soul.store.all("cognitive_source") == []
