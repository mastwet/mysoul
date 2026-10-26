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


async def test_saved_archives_do_not_become_mandatory_context(tmp_path):
    model = ReplayModel([StepDecision(done=True, note="ARCHIVED_OLD_PERIOD")])
    async with SoulService(Settings(data_dir=tmp_path), model) as soul:
        seed(soul)
        enable_small(soul)
        result = await soul.compression.run_due(force=True)
        assert result.status == "completed"
        context = await soul.context(Scope())
        assert "ARCHIVED_OLD_PERIOD" not in context.payload()
        assert not context.history
        assert all("original0 " not in e.text for e in context.evidence)
        assert not any(m.event_id == "event0" for m in context.history)
        assert not context.archives
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


async def test_retrieved_original_no_longer_depends_on_local_archive_wrapper(tmp_path):
    async with SoulService(
        Settings(data_dir=tmp_path), ReplayModel([StepDecision(done=True, note="OLD_SUMMARY")])
    ) as soul:
        seed(soul)
        enable_small(soul)
        soul.store.add_evidence(Evidence(id="event0", text="PRIVATE_OLD_RAW", source="local-owner"))
        await soul.compression.run_due(force=True)
        context = await soul.context(Scope(), "PRIVATE_OLD_RAW")
        assert not context.evidence
        found = await soul.memory_tools.call("memory_search", {"query": "PRIVATE_OLD_RAW"}, Scope())
        assert [item["ref"] for item in found["items"]] == ["event0"]
        assert not any(s["role"] == "reflection" for s in soul.cognition.status()["sources"])


async def test_old_archive_size_no_longer_triggers_model_context_pressure(tmp_path):
    async with SoulService(
        Settings(data_dir=tmp_path), ReplayModel([StepDecision(done=True, note="SMALL")])
    ) as soul:
        seed(soul, count=14, size=4000)
        soul.compression.set_policy(CompressionPolicy(raw_trigger=100, raw_batch=4))
        run = await soul.compression.run_due(force=True)
        assert run is None
        assert len((await soul.context(Scope(), "unrelated")).payload()) < 131072 * 0.75


async def test_idle_does_not_schedule_legacy_compression(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path), ReplayModel()) as soul:
        seed(soul, count=100)

        async def forbidden(*args, **kwargs):
            raise AssertionError("Idle must not run legacy archive compression")

        soul.compression.run_due = forbidden
        await soul.activities.idle()
        assert not soul.store.all("compression_run")


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
