from datetime import UTC, datetime, timedelta

import pytest

from mysoul.config import Settings
from mysoul.domain import Activity, ActivityDecision, Event
from mysoul.life import LifeController
from mysoul.model import ReplayModel
from mysoul.scheduler import Scheduler
from mysoul.storage import StateStore


@pytest.fixture
def rig(tmp_path):
    store = StateStore(tmp_path / "s.db")
    model = ReplayModel()
    clock = [datetime(2026, 10, 22, tzinfo=UTC)]
    controller = LifeController(store, model, Settings(data_dir=tmp_path), lambda: clock[0])
    yield controller, store, model, clock
    store.close()


async def test_rest_has_zero_recurring_model_calls(rig):
    life, _, model, clock = rig
    for _ in range(1000):
        clock[0] += timedelta(hours=1)
        assert (await life.choose([])).activity == Activity.REST
    assert model.calls == 0


async def test_owner_wakes_rest(rig):
    life, store, model, _ = rig
    event = Event(content="hello", dedup_key="owner1", trust="owner_command")
    assert (await life.choose([event])).activity == Activity.CHAT
    assert model.calls == store.load_subject().model_calls == 1


async def test_event_burst_coalesces(rig):
    life, _, model, _ = rig
    scheduler = Scheduler(capacity=20)
    for i in range(1000):
        scheduler.offer(Event(content="hello", dedup_key=str(i)))
    assert len(scheduler.pending) == 20
    await life.choose(scheduler.drain())
    assert model.calls == 1
    assert scheduler.drain() == []


async def test_fatigue_clamped_and_rest_recovers(rig):
    life, store, _, clock = rig
    state = store.load_subject()
    state.activity = Activity.WORK
    state.updated_at = clock[0]
    store.save_transition(0, state)
    clock[0] += timedelta(hours=100)
    await life.choose([])
    assert store.load_subject().fatigue == 1
    clock[0] += timedelta(hours=100)
    await life.choose([])
    assert store.load_subject().fatigue == 0


async def test_budget_exhaustion_blocks_model(rig):
    life, store, model, _ = rig
    state = store.load_subject()
    state.tokens_used = life.settings.token_budget
    store.save_transition(0, state)
    await life.choose([Event(content="hello", dedup_key="x")])
    assert model.calls == 0


async def test_mode_does_not_expand_permissions(rig):
    life, store, model, _ = rig
    life.settings.model_call_limit = 0
    state = store.load_subject()
    state.mode = "focused"
    store.save_transition(0, state)
    await life.choose([Event(content="work", dedup_key="x")])
    assert model.calls == 0


async def test_all_five_activities_and_fatigue_ab(rig):
    life, store, model, _ = rig
    for activity in Activity:
        model.decisions.append(ActivityDecision(activity=activity))
        result = await life.choose([Event(content="tick", dedup_key=activity)])
        assert result.activity == activity
    assert store.load_subject().model_calls == 5
    life.settings.fatigue_enabled = False
    assert (await life.choose([])).activity == Activity.REST
