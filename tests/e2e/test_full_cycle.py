from mysoul.config import Settings
from mysoul.domain import Evidence, Goal, Scope
from mysoul.evolution import CandidateRunner, ProcedureReplayModel
from mysoul.service import SoulService


async def test_four_chain_cycle_with_persistence(tmp_path):
    settings = Settings(data_dir=tmp_path)
    async with SoulService(settings, model=ProcedureReplayModel()) as soul:
        await soul.owner_message("完成报告前必须检查实际产物。")
        first = await soul.start_goal(Goal(objective="produce report"))
        assert first.status == "completed"
        assert len(first.effect_ids) == 1
        soul.store.add_evidence(
            Evidence(id="failure", text="Initial procedure did not read back the report")
        )
        proposal = await soul.reflect(["failure"])
        assert (await CandidateRunner(soul.skills).run(proposal.id))["objective_pass"]
        soul.skills.activate(proposal.id, proposal.base_hash, proposal.candidate_hash)
        second = await soul.start_goal(Goal(objective="produce verified report"))
        assert len(second.effect_ids) == 2
        soul.recap.publish(0, "保留报告检查要求。", ["failure"])
        soul.skills.rollback("work", proposal.base_hash)
    async with SoulService(settings) as reopened:
        assert reopened.recap.current().text == "保留报告检查要求。"
        assert reopened.store.goal(second.goal_id).status == "completed"
        assert reopened.skills.active().content_hash == proposal.base_hash
        assert (await reopened.memory.get("failure", Scope())).text.startswith("Initial procedure")
