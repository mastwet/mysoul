import pytest

from mysoul.archives import CompressionPolicy
from mysoul.config import Settings
from mysoul.domain import Event, Evidence, Scope, StepDecision
from mysoul.model import ReplayModel
from mysoul.service import SoulService


def seed(soul, count=12, size=100):
    for n in range(count):
        e = Event(id=f"event{n}", dedup_key=f"event{n}", content=f"original{n} " + "U" * size)
        soul.store.add_event(e)
        soul.store.record_interaction(
            e,
            {
                "event_id": e.id,
                "input": e.content,
                "text": "answer " + "A" * size,
                "choice": "owner_served",
            },
        )


def enable_small(soul):
    soul.compression.set_policy(CompressionPolicy(raw_trigger=10, raw_batch=4))


async def test_empty_archive_work_makes_no_call(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path), ReplayModel()) as soul:
        assert await soul.compression.run_due(force=True) is None
        assert soul.model.calls == 0


async def test_context_contains_nonoverlapping_frontier_and_recent_originals(tmp_path):
    model = ReplayModel([StepDecision(done=True, note="ARCHIVED_OLD_PERIOD")])
    async with SoulService(Settings(data_dir=tmp_path), model) as soul:
        seed(soul)
        enable_small(soul)
        result = await soul.compression.run_due(force=True)
        assert result.status == "completed"
        context = await soul.context(Scope())
        assert "ARCHIVED_OLD_PERIOD" in context.payload()
        assert "original11" in context.payload()
        assert all("original0 " not in e.text for e in context.evidence)
        assert not any(m.event_id == "event0" for m in context.history)
        assert context.archives
        group = await soul.context(Scope(audience="group", conversation="g"))
        assert "ARCHIVED_OLD_PERIOD" not in group.payload()


async def test_failure_preserves_context_and_restart_retries(tmp_path):
    class Broken(ReplayModel):
        async def execute_step(self, context, tools, limits):
            raise TimeoutError()

    async with SoulService(Settings(data_dir=tmp_path), Broken()) as soul:
        seed(soul)
        enable_small(soul)
        failed = await soul.compression.run_due(force=True)
        assert failed.status == "failed"
        assert all(n.level == 0 for n in soul.compression.archives.frontier(Scope()))
        assert await soul.compression.run_due() is None
    async with SoulService(
        Settings(data_dir=tmp_path), ReplayModel([StepDecision(done=True, note="RECOVERED")])
    ) as soul:
        result = await soul.compression.run_due(force=True)
        assert result.id == failed.id and result.status == "completed"


@pytest.mark.parametrize("race", ["epoch", "clear", "source"])
async def test_racing_changes_supersede_archive_run(tmp_path, race):
    class Racing(ReplayModel):
        async def execute_step(self, context, tools, limits):
            if race == "epoch":
                soul.store.interrupt()
            elif race == "clear":
                soul.recap.clear(soul.recap.current().version)
            else:
                e = soul.store.events()[0]
                soul.store.record_interaction(e, {"text": "CORRECTED", "choice": "owner_served"})
            return StepDecision(done=True, note="STALE")

    async with SoulService(Settings(data_dir=tmp_path), Racing()) as soul:
        seed(soul)
        enable_small(soul)
        result = await soul.compression.run_due(force=True)
        assert result.status == "superseded"
        assert not soul.store.all("archive_receipt")


async def test_restart_reuses_saved_result(tmp_path):
    async with SoulService(
        Settings(data_dir=tmp_path), ReplayModel([StepDecision(done=True, note="PERSISTED")])
    ) as soul:
        seed(soul)
        enable_small(soul)

        def crash(*args, **kwargs):
            raise SystemExit("after durable generation")

        soul.compression.archives.publish = crash
        with pytest.raises(SystemExit):
            await soul.compression.run_due(force=True)
    async with SoulService(Settings(data_dir=tmp_path), ReplayModel()) as soul:
        run = await soul.compression.run_due(force=True)
        assert run.status == "completed" and soul.model.calls == 0


async def test_recalled_child_is_not_injected_twice(tmp_path):
    async with SoulService(
        Settings(data_dir=tmp_path), ReplayModel([StepDecision(done=True, note="OLD_SUMMARY")])
    ) as soul:
        seed(soul)
        enable_small(soul)
        soul.store.add_evidence(Evidence(id="event0", text="PRIVATE_OLD_RAW", source="local-owner"))
        await soul.compression.run_due(force=True)
        context = await soul.context(Scope(), "PRIVATE_OLD_RAW")
        assert "PRIVATE_OLD_RAW" not in str([e.text for e in context.evidence])
        assert not any(s["role"] == "reflection" for s in soul.cognition.status()["sources"])


async def test_capacity75_triggers_before_overflow(tmp_path):
    async with SoulService(
        Settings(data_dir=tmp_path), ReplayModel([StepDecision(done=True, note="SMALL")])
    ) as soul:
        seed(soul, count=14, size=4000)
        soul.compression.set_policy(CompressionPolicy(raw_trigger=100, raw_batch=4))
        run = await soul.compression.run_due(force=True)
        assert run is not None and run.status == "completed"


async def test_batch_stops_at_low55(tmp_path):
    async with SoulService(
        Settings(data_dir=tmp_path),
        ReplayModel(
            [StepDecision(done=True, note="FIRST"), StepDecision(done=True, note="SECOND")]
        ),
    ) as soul:
        seed(soul, count=14, size=4000)
        soul.compression.set_policy(CompressionPolicy(raw_trigger=100, raw_batch=4))
        first = await soul.compression.run_due(force=True)
        assert first.status == "completed"
        second = await soul.compression.run_due(force=True)
        assert second is not None and second.status == "completed"
        assert await soul.compression.run_due(force=True) is None


async def test_invalid_generated_summary_can_be_regenerated(tmp_path):
    async with SoulService(
        Settings(data_dir=tmp_path),
        ReplayModel(
            [StepDecision(done=True, note="X" * 5000), StepDecision(done=True, note="VALID")]
        ),
    ) as soul:
        seed(soul)
        enable_small(soul)
        failed = await soul.compression.run_due(force=True)
        assert failed.status == "failed"
        done = await soul.compression.run_due(force=True)
        assert done.status == "completed" and done.id == failed.id
