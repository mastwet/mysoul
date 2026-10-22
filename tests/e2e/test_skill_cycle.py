from mysoul.config import Settings
from mysoul.domain import Evidence, Goal
from mysoul.evolution import CandidateRunner, ProcedureReplayModel
from mysoul.service import SoulService


async def test_active_goal_keeps_skill_version_and_rollback_changes_next_task_default(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path), model=ProcedureReplayModel()) as soul:
        base = soul.skills.active()
        soul.store.add_evidence(Evidence(id="failure", text="Missing verification"))
        proposal = soul.skills.propose("# Work\nProcedure: verify\n", ["failure"])
        result = await CandidateRunner(soul.skills).run(proposal.id)
        assert result["objective_pass"]
        active = soul.skills.activate(proposal.id, base.content_hash, proposal.candidate_hash)
        activity = await soul.start_goal(Goal(objective="write report"))
        assert activity.skill_version == active.content_hash
        assert len(activity.effect_ids) == 2
        soul.skills.rollback("work", base.content_hash)
        assert soul.store.activity(activity.id).skill_version == active.content_hash
        next_activity = await soul.start_goal(Goal(objective="write another report"))
        assert next_activity.skill_version == base.content_hash
        assert len(next_activity.effect_ids) == 1
