import pytest
from fastapi.testclient import TestClient

from mysoul.api import create_app
from mysoul.config import Settings
from mysoul.domain import ActivityDecision, Scope, StepDecision
from mysoul.model import ReplayModel
from mysoul.service import SoulService


@pytest.fixture
def client(tmp_path):
    model = ReplayModel()
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings, token="voice-test", service=SoulService(settings, model=model))
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        client.headers.update({"Authorization": "Bearer voice-test"})
        csrf = client.get("/api/session").json()["csrf"]
        client.headers.update({"Origin": "http://127.0.0.1:8765", "X-CSRF-Token": csrf})
        yield client, app.state.soul, model


def test_existing_checks_are_visible_without_model_or_memory_writes(client):
    client, soul, model = client
    soul.store.put(
        "initiative_check",
        "check1",
        {
            "id": "check1",
            "epoch": 4,
            "started_at": "2026-10-23T10:00:00+00:00",
            "finished_at": "2026-10-23T10:00:02+00:00",
            "outcome": "silent",
            "reason": "最近说得比较多，我先安静一会儿。",
            "error": None,
            "publication_status": "silent",
            "reasoning_content": "RAW_PRIVATE_REASONING",
            "api_key": "sk-do-not-expose-123456789",
        },
    )
    before = (model.calls, len(soul.recap.pending()), len(soul.store.all("cognitive_source")))
    response = client.get("/api/inner-voice")
    assert response.status_code == 200
    data = response.json()
    entry = data["items"][0]
    assert entry["category"] == "initiative"
    assert entry["summary"] == "最近说得比较多，我先安静一会儿。"
    assert entry["status"] == "silent"
    assert entry["details"]["epoch"] == 4
    assert "RAW_PRIVATE_REASONING" not in response.text
    assert "sk-do-not-expose" not in response.text
    assert before == (
        model.calls,
        len(soul.recap.pending()),
        len(soul.store.all("cognitive_source")),
    )


def test_decision_summary_is_recorded_but_group_context_and_reply_are_not_copied(client):
    client, soul, model = client
    model.decisions.append(
        ActivityDecision(
            activity="read_chat",
            chat_action="reply",
            reply="REPLY_NOT_A_DEBUG_NOTE",
            rationale="先回应当前问题。",
        )
    )
    assert client.post("/api/chat", json={"text": "PRIVATE_INPUT"}).status_code == 200
    response = client.get("/api/inner-voice", params={"category": "conversation"})
    assert response.status_code == 200
    assert response.json()["items"][0]["summary"] == "先回应当前问题。"
    assert "PRIVATE_INPUT" not in response.text
    assert "REPLY_NOT_A_DEBUG_NOTE" not in response.text
    soul.store.put(
        "decision_note",
        "group",
        {
            "id": "group",
            "created_at": "2026-10-23T11:00:00+00:00",
            "scope": Scope(audience="group", conversation="g").model_dump(),
            "category": "conversation",
            "status": "decided",
            "summary": "GROUP_PRIVATE_NOTE",
        },
    )
    assert "GROUP_PRIVATE_NOTE" not in client.get("/api/inner-voice").text


def test_pagination_filter_and_live_receipt_update_keep_identity_stable(client):
    client, soul, _ = client
    for index in range(4):
        ident = str(index)
        soul.store.put(
            "initiative_check",
            ident,
            {
                "id": ident,
                "started_at": "2026-10-23T10:00:00+00:00",
                "outcome": "waiting",
                "reason": "",
                "epoch": 0,
            },
        )
    page = client.get("/api/inner-voice", params={"limit": 2}).json()
    assert len(page["items"]) == 2
    assert page["has_more"]
    ids = [item["id"] for item in page["items"]]
    receipt = soul.store.get("initiative_check", "3")
    receipt.update(outcome="silent", reason="安静。")
    soul.store.put("initiative_check", "3", receipt)
    older = client.get(
        "/api/inner-voice", params={"limit": 2, "before": page["next_before"]}
    ).json()
    assert len(set(ids + [item["id"] for item in older["items"]])) == 4
    updated = client.get("/api/inner-voice", params={"limit": 2}).json()
    assert updated["items"][0]["id"] == ids[0]
    assert updated["items"][0]["status"] == "silent"
    assert client.get("/api/inner-voice", params={"category": "task"}).json()["items"] == []
    assert client.get("/api/inner-voice", params={"limit": 101}).status_code == 422
    assert client.get("/api/inner-voice", params={"before": "broken-cursor"}).status_code == 400
    assert client.get("/api/inner-voice", headers={"Authorization": ""}).status_code == 401


def test_task_progress_has_a_short_note_without_copying_memory_results(client):
    from mysoul.domain import Goal
    from mysoul.inner_voice import VoiceJournal

    _, soul, _ = client
    goal = Goal(objective="Test task", lane="background")
    soul.store.save_goal(goal)
    from mysoul.domain import ActivityRecord

    activity = ActivityRecord(goal_id=goal.id, cursor=1)
    VoiceJournal(soul.store).record_step(
        activity,
        StepDecision(note="已完成第一步。"),
        {"outcome": "confirmed", "content": "PRIVATE_MEMORY_RESULT"},
    )
    page = VoiceJournal(soul.store).page(category="task")
    assert page["items"][0]["summary"] == "已完成第一步。"
    assert "PRIVATE_MEMORY_RESULT" not in str(page)
    assert soul.recap.pending() == []


@pytest.mark.asyncio
async def test_failed_task_step_is_visible_in_debug_journal(tmp_path):
    from mysoul.domain import Goal

    model = ReplayModel([StepDecision(tool="unknown_tool", note="尝试读取工具。")])
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        activity = await soul.start_goal(Goal(lane="background", objective="A failed step"))
        assert activity.status == "suspended"
        from mysoul.inner_voice import VoiceJournal

        page = VoiceJournal(soul.store).page(category="task")
        assert len(page["items"]) == 1
        assert page["items"][0]["status"] == "failed"
        assert page["items"][0]["details"]["outcome"] == "not_sent"


@pytest.mark.asyncio
async def test_failed_second_step_does_not_overwrite_first_progress_note(tmp_path):
    from mysoul.domain import Goal
    from mysoul.inner_voice import VoiceJournal

    model = ReplayModel(
        [
            StepDecision(note="第一步已完成。"),
            StepDecision(tool="unknown_tool", note="第二步未能执行。"),
        ]
    )
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        activity = await soul.start_goal(Goal(lane="background", objective="Two steps"))
        await soul.executor.resume(activity.id, "continue")
        items = VoiceJournal(soul.store).page(category="task")["items"]
        assert len(items) == 2
        assert {item["details"]["step"] for item in items} == {1, 2}
        assert {item["summary"] for item in items} == {"第一步已完成。", "第二步未能执行。"}
