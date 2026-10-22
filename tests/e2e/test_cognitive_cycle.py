"""Deterministic acceptance across memory, persona, correction and restart."""

from mysoul.config import Settings
from mysoul.domain import Scope
from mysoul.model import ReplayModel
from mysoul.persona import PersonaChange, ReflectionDecision
from mysoul.service import SoulService


async def test_experience_evolves_future_turns_and_rollback_survives_restart(tmp_path):
    class Evolving(ReplayModel):
        async def reflect(self, context, limits):
            return ReflectionDecision(changes=[PersonaChange(
                target="relationship", text="PRIVATE_KEEP_CONCLUSIONS_FIRST",
                reason="Owner asked for concise explanations",
                evidence_refs=[context.evidence[0].id],
            )], reason="Supported by admitted owner message")

    settings = Settings(data_dir=tmp_path)
    async with SoulService(settings, Evolving()) as soul:
        await soul.owner_message("请先告诉我结论，再给必要细节。")
        await soul.tick()
        assert soul.recap.current().version == 1
        assert soul.persona.current().version == 1
        assert "请先告诉我结论" in soul.recap.current().text
        future = await soul.context(Scope(), "继续讨论")
        assert future.persona_version == 1
        assert "PRIVATE_KEEP_CONCLUSIONS_FIRST" in future.instructions
        before = soul.persona.current()
        soul.persona.update(1, sections=before.sections.model_dump() | {
            "relationship": "主人手动纠正：需要充分解释时不要省略。",
        })
        assert "主人手动纠正" in (await soul.context(Scope())).instructions
        soul.persona.rollback(2, 0)
        receipt_count = len(soul.persona.changes())
    async with SoulService(settings, ReplayModel()) as reopened:
        assert reopened.persona.current().version == 3
        restored_context = await reopened.context(Scope())
        assert "PRIVATE_KEEP_CONCLUSIONS_FIRST" not in restored_context.instructions
        assert await reopened.cognition.run_due(force=True) is None
        assert reopened.model.calls == 0
        assert reopened.recap.current().version == 1
        assert len(reopened.persona.changes()) == receipt_count
