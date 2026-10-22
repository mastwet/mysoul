from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from mysoul.domain import Activity, Event, Goal, LifeState
from mysoul.storage import Conflict, StateStore


def test_duplicate_event_has_one_record(tmp_path):
    store = StateStore(tmp_path / "state.sqlite")
    event = Event(id="e1", dedup_key="qq:1", content="hello")
    assert store.add_event(event)
    assert not store.add_event(event.model_copy(update={"id": "e2"}))
    assert len(store.events()) == 1
    store.close()


def test_stale_epoch_rejected(tmp_path):
    store = StateStore(tmp_path / "state.sqlite")
    state = store.load_subject()
    state.dispatch_epoch = 1
    store.save_transition(0, state)
    with pytest.raises(Conflict):
        store.save_transition(0, state.model_copy(update={"activity": Activity.WORK}))
    assert store.load_subject().activity == "rest"
    store.close()


def test_cancelled_goal_remains_terminal_after_reload(tmp_path):
    path = tmp_path / "state.sqlite"
    store = StateStore(path)
    goal = Goal(id="g", objective="write report", status="cancelled")
    store.save_goal(goal)
    state = store.load_subject()
    store.save_transition(0, state)
    store.close()
    reopened = StateStore(path)
    assert reopened.load_subject() == state
    assert reopened.goal("g").status == "cancelled"
    with pytest.raises(Conflict):
        reopened.save_goal(goal.model_copy(update={"status": "active"}))
    reopened.close()


@pytest.mark.parametrize("fatigue", [-1, 1.1, float("nan"), float("inf")])
def test_invalid_fatigue_rejected(fatigue):
    with pytest.raises(ValidationError):
        LifeState(fatigue=fatigue)


def test_configuration_and_utc_validation(tmp_path):
    from mysoul.config import Settings

    assert Settings(data_dir=tmp_path).send_enabled is False
    with pytest.raises(ValidationError):
        Settings(data_dir=tmp_path, host="0.0.0.0")
    with pytest.raises(ValidationError):
        LifeState(updated_at=datetime(2026, 1, 1))
    assert LifeState().updated_at.tzinfo == UTC
