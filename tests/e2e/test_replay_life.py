import asyncio
from datetime import UTC, datetime

from mysoul.config import Settings
from mysoul.domain import Event, Goal, Scope, StepDecision
from mysoul.phone.replay import ReplayPhone
from mysoul.service import SoulService


async def test_read_silent_reply_choices(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        group = Scope(audience="group", conversation="g")
        event = Event(content="ordinary group chatter", scope=group, dedup_key="1")
        result = await soul.receive(event)
        assert result["choice"] == "silent"
        draft = await soul.receive(Event(content="@mysoul hello", scope=group, dedup_key="2"))
        assert draft["choice"] == "draft"
        assert soul.phone.sent == []
        assert len(soul.store.events()) == 2


async def test_owner_interrupt_preserves_task(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        entered, release = asyncio.Event(), asyncio.Event()
        original = soul.model.execute_step

        async def delayed(*args):
            entered.set()
            await release.wait()
            return await original(*args)

        soul.model.execute_step = delayed
        task = asyncio.create_task(soul.start_goal(Goal(objective="remember task")))
        await entered.wait()
        reply = await soul.owner_message("please pause")
        assert reply["choice"] == "owner_served"
        assert soul.store.load_subject().dispatch_epoch == 1
        release.set()
        activity = await task
        assert soul.store.activity(activity.id).status == "suspended"
        assert soul.store.goal(activity.goal_id).objective == "remember task"


async def test_resume_uses_effect_evidence(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        soul.model.steps.extend(
            [StepDecision(tool="draft", arguments={"text": "hello"}), StepDecision(done=True)]
        )
        activity = await soul.start_goal(Goal(objective="draft a reply"))
        assert activity.status == "completed"
        assert soul.store.effect(activity.effect_ids[0]).outcome == "confirmed"
        assert soul.phone.sent == []


async def test_replay_has_no_live_transport():
    phone = ReplayPhone([])
    assert phone.capabilities["live"] is False
    assert not hasattr(phone, "client")


async def test_restart_deduplicates_events(tmp_path):
    instant = datetime(2026, 10, 22, tzinfo=UTC)
    event = Event(content="hello", dedup_key="same", received_at=instant)
    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        first = await soul.receive(event)
    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        assert (await soul.receive(event))["choice"] == "duplicate"
        assert len(soul.store.events()) == 1
    assert first["choice"] == "silent"


async def test_same_trace_twice_has_same_semantic_outputs(tmp_path):
    outputs = []
    for directory in (tmp_path / "a", tmp_path / "b"):
        async with SoulService(Settings(data_dir=directory)) as soul:
            phone = ReplayPhone.from_jsonl("tests/fixtures/life_trace.jsonl")
            batch = await phone.observe(None)
            outputs.append([(await soul.receive(e))["choice"] for e in batch.events])
    assert outputs[0] == outputs[1] == ["silent", "draft"]
