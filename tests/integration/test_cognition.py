
import pytest

from mysoul import cognition
from mysoul.config import Settings
from mysoul.domain import Event, Scope, StepDecision
from mysoul.laputa import RecapStore
from mysoul.model import ReplayModel
from mysoul.service import SoulService
from mysoul.storage import StateStore


def source_store(tmp_path, *, text="明天一起整理资料", result=None, source="owner"):
    store = StateStore(tmp_path / "state.sqlite")
    store.load_subject()
    RecapStore(store)
    event = Event(id="turn-1", dedup_key="turn-1", content=text, source=source)
    store.add_event(event)
    store.record_interaction(event, result or {
        "event_id": event.id, "choice": "owner_served", "text": "好，保留这项约定。",
    })
    return store, cognition.CognitiveStore(store)


def test_capture_once_preserves_both_roles(tmp_path):
    store, sources = source_store(tmp_path, text="长文" * 3000)
    sources.capture_interaction("turn-1")
    sources.capture_interaction("turn-1")
    window = sources.pending_window(16000)
    assert [(s.role, s.text) for s in window.slices] == [
        ("user", "长文" * 3000), ("assistant", "好，保留这项约定。"),
    ]
    assert len(store.all("cognitive_source")) == 2
    assert window.recap_version == 0
    store.close()


def test_failed_turn_stays_failure(tmp_path):
    store, sources = source_store(tmp_path, result={
        "event_id": "turn-1", "choice": "owner_served", "text": "Model unavailable",
        "error": {"code": "timeout"},
    })
    sources.capture_interaction("turn-1")
    window = sources.pending_window(16000)
    assert window.slices[1].role == "failure"
    assert 'timeout' in window.slices[1].text
    store.close()


def test_large_segment_keeps_unseen_suffix(tmp_path):
    store, sources = source_store(tmp_path, text="甲" * 10 + "乙" * 10)
    sources.capture_interaction("turn-1")
    first = sources.pending_window(10)
    assert first.slices[0].text == "甲" * 10
    assert (first.slices[0].start, first.slices[0].end, first.slices[0].total) == (0, 10, 20)
    # Simulate a committed coordinate, not deletion of the raw source.
    row = store.get("cognitive_source", first.slices[0].source_id)
    row["covered"] = 10
    store.put("cognitive_source", row["id"], row)
    second = sources.pending_window(10)
    assert second.slices[0].text == "乙" * 10
    assert second.slices[0].start == 10
    store.close()


def test_reopen_preserves_pending_window(tmp_path):
    store, sources = source_store(tmp_path)
    sources.capture_interaction("turn-1")
    before = sources.pending_window(16000)
    store.close()
    reopened = StateStore(tmp_path / "state.sqlite")
    assert cognition.CognitiveStore(reopened).pending_window(16000) == before
    reopened.close()


def test_initiative_has_no_invented_user(tmp_path):
    store, sources = source_store(tmp_path, source="local-initiative")
    sources.capture_interaction("turn-1")
    assert [s.role for s in sources.pending_window(16000).slices] == ["assistant"]
    store.close()




def seed(soul, text="保留这个完整约定"):
    event = Event(id="seed", dedup_key="seed", content=text, source="owner")
    soul.store.add_event(event)
    soul.store.record_interaction(event, {"event_id": event.id,
                                       "choice": "owner_served", "text": "已经记下"})


@pytest.mark.asyncio
async def test_empty_maintenance_has_no_model_calls(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path), ReplayModel()) as soul:
        assert await soul.cognition.run_due(force=True) is None
        assert soul.model.calls == 0


@pytest.mark.asyncio
async def test_due_pipeline_covers_sources_after_rest(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path), ReplayModel()) as soul:
        seed(soul)
        await soul.activities.idle()
        runs = soul.cognition.status()["runs"]
        assert runs[-1]["status"] == "completed"
        assert soul.cognition.sources.pending_window(16000) is None
        assert "保留这个完整约定" in soul.recap.current().text
        calls = soul.model.calls
        await soul.activities.idle()
        assert soul.model.calls == calls


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", ["epoch", "edit", "clear"])
async def test_stale_publish_never_covers_sources(tmp_path, conflict):
    class RacingModel(ReplayModel):
        async def execute_step(self, context, tools, limits):
            if conflict == "epoch":
                soul.store.interrupt()
            elif conflict == "clear":
                soul.recap.clear(0)
            else:
                soul.recap.publish(0, "主人修正", [])
            return StepDecision(done=True, note="过期内容")

    async with SoulService(Settings(data_dir=tmp_path), RacingModel()) as soul:
        seed(soul)
        run = await soul.cognition.run_due(force=True)
        assert run.status == "superseded"
        assert all(s["covered"] == 0 for s in soul.store.all("cognitive_source"))
        assert soul.recap.current().text != "过期内容"
        if conflict == "clear":
            assert soul.cognition.sources.pending_window(16000) is None


@pytest.mark.asyncio
async def test_failure_retains_context_and_backoff_survives_restart(tmp_path):
    class Broken(ReplayModel):
        async def execute_step(self, context, tools, limits):
            self.calls += 1
            raise TimeoutError()

    async with SoulService(Settings(data_dir=tmp_path), Broken()) as soul:
        seed(soul, "不可丢失的完整约定")
        failed = await soul.cognition.run_due(force=True)
        assert failed.status == "failed"
        assert failed.attempts == 1
        assert await soul.cognition.run_due() is None
        assert soul.model.calls == 1
        assert "不可丢失的完整约定" not in (await soul.context(Scope())).payload()
        recovered = await soul.memory_tools.call("memory_get", {
            "ref": "experience:seed:user"
        }, Scope())
        assert "不可丢失的完整约定" in recovered["text"]
        assert soul.cognition.sources.pending_window(16000) is not None
    async with SoulService(Settings(data_dir=tmp_path), ReplayModel()) as soul:
        assert await soul.cognition.run_due() is None
        result = await soul.cognition.run_due(force=True)
        assert result.id == failed.id
        assert result.status == "completed"
        assert soul.recap.current().version == 1


@pytest.mark.asyncio
async def test_restart_after_recap_commit_does_not_refold(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path), ReplayModel()) as soul:
        seed(soul)
        original = soul.cognition.reflect_run

        async def crash(run):
            raise SystemExit("simulated process stop after durable recap")

        soul.cognition.reflect_run = crash
        with pytest.raises(SystemExit):
            await soul.cognition.run_due(force=True)
        assert soul.recap.current().version == 1
        soul.cognition.reflect_run = original
    async with SoulService(Settings(data_dir=tmp_path), ReplayModel()) as soul:
        await soul.cognition.run_due(force=True)
        assert soul.recap.current().version == 1
        assert not any('[recap]' in p for p in soul.model.payloads)

@pytest.mark.asyncio
async def test_recap_can_preserve_more_than_four_thousand_characters(tmp_path):
    class Detailed(ReplayModel):
        async def execute_step(self, context, tools, limits):
            return StepDecision(done=True, note="甲" * 5000)
    async with SoulService(Settings(data_dir=tmp_path), Detailed()) as soul:
        seed(soul)
        run = await soul.cognition.run_due(force=True)
        assert run.status == "completed"
        assert len(soul.recap.current().text) == 5000


def test_legacy_unfinished_owner_turn_remains_a_pending_failure(tmp_path):
    store = StateStore(tmp_path / "state.sqlite")
    store.load_subject()
    recap = RecapStore(store)
    from mysoul.domain import Evidence
    event = Event(id="unfinished", dedup_key="unfinished", content="不要丢掉这次请求")
    store.add_event(event)
    store.add_evidence(Evidence(id=event.id, text=event.content))
    recap.enqueue(event.id)
    sources = cognition.CognitiveStore(store)
    sources.migrate_pending()
    window = sources.pending_window(16000)
    assert window is not None
    assert window.slices[0].role == "user"
    assert window.slices[0].text == "不要丢掉这次请求"
    assert window.slices[1].role == "failure"
    assert "unfinished" in window.slices[1].text.lower()
    store.close()
