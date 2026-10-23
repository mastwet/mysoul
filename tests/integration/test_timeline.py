import pytest

from mysoul.domain import ActivityRecord, Event, Goal, Scope
from mysoul.storage import StateStore
from mysoul.timeline import TimelineStore


def turn(store, key, *, scope=None):
    event = Event(
        id=key,
        dedup_key=key,
        source="local-owner",
        trust="owner_command",
        content="input " + key,
        scope=scope or Scope(),
    )
    store.add_event(event)
    store.record_interaction(
        event,
        {"event_id": key, "choice": "owner_served", "input": event.content, "text": "reply " + key},
    )
    return event


def test_migration_is_repeatable_and_preserves_originals(tmp_path):
    store = StateStore(tmp_path / "state.sqlite")
    turn(store, "a")
    timeline = TimelineStore(store)
    timeline.migrate()
    before = timeline.page()
    timeline.migrate()
    assert timeline.page() == before
    assert len(store.events()) == 1
    assert before.items[0].body["text"] == "reply a"
    store.close()


def test_interaction_capture_is_atomic_and_pending_resolves_in_place(tmp_path):
    store = StateStore(tmp_path / "state.sqlite")
    event = Event(
        id="a", dedup_key="a", source="local-owner", trust="owner_command", content="hello"
    )
    store.add_event(event)
    timeline = TimelineStore(store)
    pending = timeline.page().items[0]
    assert pending.body["pending"]
    store.record_interaction(
        event, {"event_id": "a", "choice": "owner_served", "text": "hi", "input": "hello"}
    )
    resolved = timeline.page().items[0]
    assert resolved.seq == pending.seq
    assert resolved.revision == pending.revision + 1
    assert resolved.body["text"] == "hi"
    assert not resolved.body.get("pending")
    with pytest.raises(RuntimeError), store.transaction() as db:
        timeline.interaction_in(db, event, {"event_id": "a", "text": "bad"})
        raise RuntimeError("rollback")
    assert timeline.page().items[0] == resolved
    store.close()


def test_task_updates_keep_one_seq(tmp_path):
    store = StateStore(tmp_path / "state.sqlite")
    goal = Goal(id="g", objective="read file")
    store.save_goal(goal)
    activity = ActivityRecord(id="a", goal_id="g", status="active")
    store.save_activity(activity)
    store.put("activity_context", "a", {"scope": Scope().model_dump()})
    timeline = TimelineStore(store)
    old = timeline.page().items[0]
    activity.status = "completed"
    activity.final_note = "Result retained"
    store.save_activity(activity)
    new = timeline.page().items[0]
    assert old.seq == new.seq and old.id == new.id
    assert new.body["status"] == "completed"
    assert new.body["result"] == "Result retained"
    assert len(timeline.page().items) == 1
    store.close()


def test_cursor_survives_identical_times_and_new_items(tmp_path):
    store = StateStore(tmp_path / "state.sqlite")
    timeline = TimelineStore(store)
    for n in range(150):
        turn(store, str(n))
    first = timeline.page(limit=50)
    turn(store, "new")
    second = timeline.page(before=first.next_before, limit=50)
    third = timeline.page(before=second.next_before, limit=50)
    assert len({i.id for p in (first, second, third) for i in p.items}) == 150
    assert not third.has_more
    changes = timeline.page(after_change=first.change_cursor, limit=50)
    assert [i.body["input"] for i in changes.items] == ["input new"]
    store.close()


def test_group_never_enters_owner_timeline(tmp_path):
    store = StateStore(tmp_path / "state.sqlite")
    turn(store, "private-group", scope=Scope(audience="group", conversation="g"))
    TimelineStore(store).migrate()
    assert TimelineStore(store).page().items == []
    store.close()


def test_legacy_task_and_chat_migrate_in_time_order(tmp_path):
    from datetime import timedelta

    from mysoul.domain import now

    store = StateStore(tmp_path / "state.sqlite")
    goal = Goal(id="g", objective="old task", created_at=now() - timedelta(days=1))
    store.save_goal(goal)
    activity = ActivityRecord(id="work", goal_id="g", status="completed")
    store.save_activity(activity)
    store.put("activity_context", activity.id, {"scope": Scope().model_dump()})
    turn(store, "newer-chat")
    # Remove only the derived projection to represent a pre-feature database.
    with store.transaction() as db:
        db.execute("DELETE FROM timeline_changes")
        db.execute("DELETE FROM timeline")
    TimelineStore(store).migrate()
    assert [i.kind for i in TimelineStore(store).page().items] == ["task", "chat"]
    store.close()
