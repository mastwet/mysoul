"""Recap prose uses exact source time and short events, never internal citations."""

from datetime import UTC, datetime

from mysoul.config import Settings
from mysoul.domain import Event, Evidence, StepDecision
from mysoul.laputa import consolidate_recap
from mysoul.model import ReplayModel
from mysoul.service import SoulService

STAMP = datetime(2026, 10, 23, 4, 5, 6, 123456, tzinfo=UTC)
TEXT = "2026-10-23 04:05:06 — 我和用户分享了巨嘴鸟的结构奇迹。"
IDENT = "c98f8d9d81d145f8a97565813f79809a"


def seed(soul):
    event = Event(
        id=IDENT,
        dedup_key=IDENT,
        source="local-owner",
        trust="owner_command",
        received_at=STAMP,
        content="和我分享巨嘴鸟的科普。",
    )
    soul.store.add_event(event)
    soul.store.record_interaction(
        event,
        {
            "event_id": event.id,
            "input": event.content,
            "choice": "owner_served",
            "text": "巨嘴鸟的喙很大却很轻，内部结构兼具强度和散热能力。",
        },
    )
    soul.store.add_evidence(Evidence(id=event.id, text=event.content, created_at=STAMP))
    soul.recap.enqueue(event.id)
    return event


async def test_recap_prompt_and_published_prose_are_timestamped_without_ids(tmp_path):
    class Inspect(ReplayModel):
        async def execute_step(self, context, tools, limits):
            assert "精确时间" in context.instructions
            assert (
                "地点" in context.instructions
                and "人物" in context.instructions
                and "事件" in context.instructions
            )
            assert "我和用户分享了巨嘴鸟的结构奇迹" in context.instructions
            assert "Cite supplied evidence IDs" not in context.instructions
            assert all(IDENT not in e.id for e in context.evidence)
            assert any("2026-10-23 04:05:06" in e.text for e in context.evidence)
            assert all(".123456" not in e.text and "+00:00" not in e.text for e in context.evidence)
            return StepDecision(done=True, note=TEXT + f" [experience:{IDENT}:assistant]")

    async with SoulService(Settings(data_dir=tmp_path), Inspect()) as soul:
        seed(soul)
        run = await soul.cognition.run_due(force=True)
        assert run.status == "completed", run.error
        recap = soul.recap.current()
        assert recap.text == TEXT
        assert any(IDENT in ref for ref in recap.refs)
        reflection = next(p for p in soul.model.payloads if "[persona-reflection]" in p)
        assert f"experience:{IDENT}:user" in reflection


async def test_legacy_synthesis_uses_same_recap_style(tmp_path):
    class Inspect(ReplayModel):
        async def execute_step(self, context, tools, limits):
            assert "精确时间" in context.instructions
            assert "Cite stable evidence IDs" not in context.instructions
            assert all(IDENT not in e.id for e in context.evidence)
            assert any("2026-10-23 04:05:06" in e.text for e in context.evidence)
            assert all(".123456" not in e.text and "+00:00" not in e.text for e in context.evidence)
            return StepDecision(done=True, note=TEXT)

    async with SoulService(Settings(data_dir=tmp_path), Inspect()) as soul:
        seed(soul)
        result = await consolidate_recap(soul, soul.store.load_subject().dispatch_epoch)
        assert result.text == TEXT
        assert IDENT in result.refs


async def test_reformat_old_recap_preserves_sources_versions_and_pending_coverage(tmp_path):
    class Inspect(ReplayModel):
        async def execute_step(self, context, tools, limits):
            self.calls += 1
            assert IDENT not in context.payload()
            assert "2026-10-23 04:05:06" in context.recap
            return StepDecision(done=True, note=TEXT)

    async with SoulService(Settings(data_dir=tmp_path), Inspect()) as soul:
        seed(soul)
        refs = [f"experience:{IDENT}:assistant"]
        soul.recap.publish(0, f"我介绍了巨嘴鸟的喙。 [{refs[0]}]", refs, author="agent")
        before = soul.cognition.status()["sources"]
        result = await consolidate_recap(
            soul, soul.store.load_subject().dispatch_epoch, rewrite=True
        )
        assert result.text == TEXT and result.refs == refs and result.version == 2
        assert soul.cognition.status()["sources"] == before
        assert len(soul.recap.history()) == 3
        assert soul.model.calls == 1


def test_remove_source_citations_preserves_factual_fingerprints():
    from mysoul.recap_style import clean_citations

    fingerprint = "a" * 64
    text = (
        f"文件指纹是 {fingerprint}，验收代号 BLUE-739。 "
        f"[experience:{IDENT}:user, outcome:{IDENT}:0:cancelled]"
    )
    assert clean_citations(text) == f"文件指纹是 {fingerprint}，验收代号 BLUE-739。"

    assert clean_citations(f"文件指纹 [{fingerprint}]") == f"文件指纹 [{fingerprint}]"


async def test_citation_only_output_does_not_erase_or_cover_memory(tmp_path):
    class CitationsOnly(ReplayModel):
        async def execute_step(self, context, tools, limits):
            return StepDecision(done=True, note=f"[experience:{IDENT}:assistant]")

    async with SoulService(Settings(data_dir=tmp_path), CitationsOnly()) as soul:
        seed(soul)
        soul.recap.publish(0, "保留已有约定", [])
        run = await soul.cognition.run_due(force=True)
        assert run.status == "failed"
        assert soul.recap.current().text == "保留已有约定"
        assert all(source["covered"] == 0 for source in soul.cognition.status()["sources"])


def test_display_time_uses_seconds_without_fraction_or_zone():
    from mysoul.recap_style import clean_recap

    assert (
        clean_recap("2026-10-23T04:05:06.123456+00:00 — 分享巨嘴鸟。")
        == "2026-10-23 04:05:06 — 分享巨嘴鸟。"
    )
    assert (
        clean_recap("2026-10-23 04:05:06+00:00 — 分享巨嘴鸟。")
        == "2026-10-23 04:05:06 — 分享巨嘴鸟。"
    )
