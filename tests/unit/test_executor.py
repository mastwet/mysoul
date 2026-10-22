import asyncio
from datetime import timedelta

import pytest

from mysoul.config import Settings
from mysoul.domain import ContextBundle, Event, Goal, StepDecision, ToolRequest, ToolResult, now
from mysoul.effects import EffectDispatcher
from mysoul.executor import Executor
from mysoul.model import ReplayModel
from mysoul.storage import Conflict, StateStore


@pytest.fixture
async def rig(tmp_path):
    store = StateStore(tmp_path / "s.db")
    store.load_subject()
    effects = EffectDispatcher(store)
    model = ReplayModel(
        [StepDecision(tool="write", arguments={"text": "ok"}), StepDecision(done=True)]
    )
    executor = Executor(store, model, effects, tmp_path / "graph.db", Settings(data_dir=tmp_path))
    await executor.open()
    yield store, effects, model, executor
    await executor.close()
    store.close()


async def test_interrupt_during_inference(rig):
    store, effects, model, executor = rig
    entered, release = asyncio.Event(), asyncio.Event()
    original = model.execute_step

    async def delayed(*args):
        entered.set()
        await release.wait()
        return await original(*args)

    model.execute_step = delayed
    calls = []
    effects.register("write", lambda req: confirmed(req, calls))
    task = asyncio.create_task(executor.start(Goal(objective="test")))
    await entered.wait()
    activity = await executor.interrupt(Event(dedup_key="owner", trust="owner_command"))
    release.set()
    await task
    assert store.activity(activity.id).status == "suspended"
    assert calls == []
    resumed = await executor.resume(activity.id, "continue")
    assert resumed.status == "completed"
    assert len(calls) == 1


async def confirmed(request, calls):
    calls.append(request.action_id)
    return ToolResult(action_id=request.action_id, outcome="confirmed", receipt="receipt")


async def test_interrupt_before_dispatch(rig):
    store, effects, _, executor = rig
    calls = []
    effects.register("write", lambda req: confirmed(req, calls))
    goal = Goal(objective="test", status="active")
    store.save_goal(goal)
    request = ToolRequest(
        activity_id="a",
        goal_id=goal.id,
        epoch=0,
        tool="write",
        deadline=now() + timedelta(seconds=10),
    )
    await executor.interrupt(Event(dedup_key="owner", trust="owner_command"))
    assert (await effects.dispatch(request)).outcome == "not_sent"
    assert calls == []


async def test_interrupt_with_remote_in_flight(rig):
    store, effects, _, executor = rig
    entered, release = asyncio.Event(), asyncio.Event()

    async def remote(request):
        entered.set()
        await release.wait()
        return ToolResult(action_id=request.action_id, outcome="confirmed", receipt="sent")

    effects.register("write", remote)
    task = asyncio.create_task(executor.start(Goal(objective="test")))
    await entered.wait()
    activity = await executor.interrupt(Event(dedup_key="owner", trust="owner_command"))
    release.set()
    await task
    assert store.activity(activity.id).status == "suspended"
    assert store.effect(f"{activity.id}:0").receipt == "sent"


async def test_late_result_does_not_resume_cancelled_goal(rig):
    store, effects, _, executor = rig
    entered, release = asyncio.Event(), asyncio.Event()

    async def remote(request):
        entered.set()
        await release.wait()
        return ToolResult(action_id=request.action_id, outcome="confirmed")

    effects.register("write", remote)
    goal = Goal(objective="test")
    task = asyncio.create_task(executor.start(goal))
    await entered.wait()
    executor.cancel(goal.id)
    release.set()
    activity = await task
    assert store.goal(goal.id).status == "cancelled"
    with pytest.raises(Conflict):
        await executor.resume(activity.id, "continue")


async def test_unknown_effect_is_not_resent(rig):
    store, effects, _, _ = rig
    calls = []

    async def lost(request):
        calls.append(1)
        raise TimeoutError("lost receipt")

    effects.register("write", lost)
    goal = Goal(objective="test", status="active")
    store.save_goal(goal)
    req = ToolRequest(
        activity_id="a",
        goal_id=goal.id,
        epoch=0,
        tool="write",
        deadline=now() + timedelta(seconds=10),
    )
    assert (await effects.dispatch(req)).outcome == "unknown"
    assert (await effects.dispatch(req)).outcome == "unknown"
    assert calls == [1]


async def test_goal_step_limit_and_skill_context(rig):
    store, _, model, executor = rig
    model.steps.clear()
    model.steps.extend([StepDecision(note="thinking"), StepDecision(note="still thinking")])
    activity = await executor.start(
        Goal(objective="bounded", step_limit=1), ContextBundle(skill="verify")
    )
    assert store.goal(activity.goal_id).status == "failed"
    assert "verify" in model.payloads[0]


async def test_interrupted_inference_charges_elapsed_time(rig):
    store, _, model, executor = rig
    entered, release = asyncio.Event(), asyncio.Event()
    original = model.execute_step

    async def delayed(*args):
        entered.set()
        await release.wait()
        return await original(*args)

    model.execute_step = delayed
    goal = Goal(objective="charge interrupted work")
    task = asyncio.create_task(executor.start(goal))
    await entered.wait()
    await executor.interrupt(Event(dedup_key="owner-time", trust="owner_command"))
    release.set()
    await task
    assert store.goal(goal.id).elapsed_seconds > 0
