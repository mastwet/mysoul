import json

import httpx
import pytest
from pydantic import ValidationError

from mysoul import persona
from mysoul.config import Settings
from mysoul.domain import ContextBundle, Evidence, ModelLimits, Scope, StepDecision
from mysoul.model import ReplayModel
from mysoul.provider import OpenAICompatibleModel
from mysoul.service import SoulService
from mysoul.storage import Conflict


def proposal(target="user_observations", refs=None):
    return persona.PersonaChange(target=target, text="PRIVATE_OBSERVATION", reason="主人明确提到",
                                 evidence_refs=refs or ["source"])


async def test_automatic_activation_protects_owner_text_and_is_idempotent(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        soul.store.add_evidence(Evidence(id="source", text="我喜欢简洁的回答"))
        original = soul.persona.current()
        updated = soul.persona.apply_evolution(0, 0, "op", [proposal()], ["source"])
        assert updated.version == 1
        assert updated.sections.user == original.sections.user
        assert updated.sections.redline == original.sections.redline
        assert updated.user_observations == "PRIVATE_OBSERVATION"
        soul.persona.apply_evolution(0, 0, "op", [proposal()], ["source"])
        assert len(soul.persona.history()) == 2
        changes = soul.persona.changes()
        assert changes[0]["changes"][0]["old"] == ""
        assert changes[0]["changes"][0]["new"] == "PRIVATE_OBSERVATION"
        assert changes[0]["candidate_hash"]
        with pytest.raises(Conflict):
            soul.persona.apply_evolution(0, 0, "op", [proposal("identity")], ["source"])
        group = await soul.context(Scope(audience="group", conversation="g"))
        assert "PRIVATE_OBSERVATION" not in group.payload()


@pytest.mark.parametrize("target", ["user", "redline", "mission", "dream", "public"])
def test_protected_fields_are_unrepresentable(target):
    with pytest.raises(ValidationError):
        proposal(target)


async def test_invalid_citation_and_stale_versions_preserve_authority(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        soul.store.add_evidence(Evidence(id="source", text="private"))
        with pytest.raises(ValueError):
            soul.persona.apply_evolution(0, 0, "bad-ref", [proposal(refs=["outside"])], ["source"])
        assert soul.persona.current().version == 0
        soul.persona.update(0, public="Manual public")
        with pytest.raises(Conflict):
            soul.persona.apply_evolution(0, 0, "stale", [proposal()], ["source"])
        soul.store.interrupt()
        with pytest.raises(Conflict):
            soul.persona.apply_evolution(1, 0, "epoch", [proposal()], ["source"])
        assert soul.persona.current().version == 1
        assert {c["status"] for c in soul.persona.changes()} == {"rejected", "conflict"}


async def test_rollback_publishes_new_version_and_world_stays_out_of_payload(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        soul.store.add_evidence(Evidence(id="source", text="world"))
        before = soul.persona.current()
        soul.persona.apply_evolution(0, 0, "world", [proposal("world")], ["source"])
        assert soul.persona.current().sections.world == "PRIVATE_OBSERVATION"
        assert "PRIVATE_OBSERVATION" not in (await soul.context(Scope())).instructions
        rolled = soul.persona.rollback(1, 0)
        assert rolled.version == 2
        assert rolled.sections == before.sections
        with pytest.raises(Conflict):
            soul.persona.rollback(1, 1)
        assert len(soul.persona.history()) == 3


async def test_pipeline_activates_once_and_keeps_private_notes_out_of_sources(tmp_path):
    class Evolving(ReplayModel):
        async def reflect(self, context, limits):
            self.payloads.append(context.payload())
            return persona.ReflectionDecision(changes=[persona.PersonaChange(
                target="relationship", text="PRIVATE_EVOLVED", reason="interaction evidence",
                evidence_refs=[context.evidence[0].id],
            )], note="PRIVATE_INFERRED_NOTE", reason="evidence-backed adaptation")

    async with SoulService(Settings(data_dir=tmp_path), Evolving()) as soul:
        await soul.owner_message("倾向简洁交流")
        run = await soul.cognition.run_due(force=True)
        assert run.status == "completed"
        assert run.outcome == "applied"
        assert soul.persona.current().version == 1
        context = await soul.context(Scope())
        assert context.persona_version == 1
        assert "PRIVATE_EVOLVED" in context.instructions
        assert all(s["role"] != "reflection" for s in soul.cognition.status()["sources"])
        assert soul.store.evidence("reflection-note:" + run.id).source == "model-reflection"
        group = await soul.context(Scope(audience="group", conversation="g"))
        assert "PRIVATE_" not in group.payload()
    async with SoulService(Settings(data_dir=tmp_path), ReplayModel()) as reopened:
        assert await reopened.cognition.run_due(force=True) is None
        assert reopened.persona.current().version == 1


async def test_reflection_failure_retries_without_repeating_recap(tmp_path):
    class BadReflection(ReplayModel):
        async def reflect(self, context, limits):
            raise TimeoutError("reflection failed")

    async with SoulService(Settings(data_dir=tmp_path), BadReflection()) as soul:
        await soul.owner_message("pending reflection")
        result = await soul.cognition.run_due(force=True)
        assert result.status == "failed"
        assert result.stage == "reflect"
        assert soul.recap.current().version == 1
        soul.model = ReplayModel()
        result = await soul.cognition.run_due(force=True)
        assert result.status == "completed"
        assert soul.recap.current().version == 1
        assert soul.persona.current().version == 0
        assert not any('[recap]' in p for p in soul.model.payloads)


async def test_provider_uses_typed_reflection_schema():
    captured = []
    def reply(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({
            "changes": [], "note": "", "reason": "insufficient evidence",
        })}}]})
    model = OpenAICompatibleModel("http://localhost/v1", "test", "test",
                                  transport=httpx.MockTransport(reply))
    try:
        decision = await model.reflect(ContextBundle(), ModelLimits())
        assert not decision.changes
        assert "user_observations" in captured[0]["messages"][0]["content"]
        assert "available tools" not in captured[0]["messages"][0]["content"].lower()
    finally:
        await model.close()


async def test_suspended_task_keeps_persona_snapshot_after_update(tmp_path):
    from mysoul.domain import Goal

    model = ReplayModel([StepDecision(tool="read_file", arguments={"path": "absent"})])
    async with SoulService(Settings(data_dir=tmp_path), model) as soul:
        activity = await soul.start_goal(Goal(objective="Read absent file"))
        assert activity.status == "suspended"
        sections = soul.persona.current().sections.model_dump() | {"identity": "NEW_IDENTITY"}
        soul.persona.update(0, sections=sections)
        await soul.executor.resume(activity.id, "continue")
        payload = json.loads(model.payloads[-1])
        assert payload["persona_version"] == 0
        assert "NEW_IDENTITY" not in payload["instructions"]
        assert (await soul.context(Scope())).persona_version == 1

async def test_persona_receipt_recovers_after_effect_commit_before_run_finish(tmp_path):
    class Evolving(ReplayModel):
        async def reflect(self, context, limits):
            return persona.ReflectionDecision(changes=[persona.PersonaChange(
                target="identity", text="PRIVATE_SNAPSHOT", reason="source",
                evidence_refs=[context.evidence[0].id],
            )], reason="supported")
    async with SoulService(Settings(data_dir=tmp_path), Evolving()) as soul:
        await soul.owner_message("记住共同经历")
        original = soul.cognition.save
        def interrupted_save(run):
            if run.stage == "finish":
                raise SystemExit("crash after authority transaction")
            return original(run)
        soul.cognition.save = interrupted_save
        with pytest.raises(SystemExit):
            await soul.cognition.run_due(force=True)
        assert soul.persona.current().version == 1
    async with SoulService(Settings(data_dir=tmp_path), ReplayModel()) as soul:
        result = await soul.cognition.run_due(force=True)
        assert result.status == "completed"
        assert soul.persona.current().version == 1
        assert len(soul.persona.changes()) == 1
        assert soul.model.calls == 0


async def test_manual_persona_edit_during_reflection_wins(tmp_path):
    class Racing(ReplayModel):
        async def reflect(self, context, limits):
            soul.persona.update(0, public="Owner correction")
            return persona.ReflectionDecision(changes=[persona.PersonaChange(
                target="identity", text="STALE", reason="source",
                evidence_refs=[context.evidence[0].id],
            )], reason="source")
    async with SoulService(Settings(data_dir=tmp_path), Racing()) as soul:
        await soul.owner_message("旧经历")
        result = await soul.cognition.run_due(force=True)
        assert result.status == "superseded"
        assert soul.persona.current().public == "Owner correction"
        assert soul.persona.current().sections.identity != "STALE"
        assert soul.persona.changes()[0]["status"] == "conflict"

async def test_world_is_not_injected_into_automatic_reflection(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path), ReplayModel()) as soul:
        sections = soul.persona.current().sections.model_dump() | {"world": "WORLD_EXPLICIT_ONLY"}
        soul.persona.update(0, sections=sections)
        await soul.owner_message("一次普通对话")
        await soul.cognition.run_due(force=True)
        reflection = [p for p in soul.model.payloads if '[persona-reflection]' in p]
        assert len(reflection) == 1
        assert "WORLD_EXPLICIT_ONLY" not in reflection[0]
