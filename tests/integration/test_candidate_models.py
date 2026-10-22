import pytest

from mysoul.config import Settings
from mysoul.domain import Evidence, StepDecision
from mysoul.evolution import CandidateRunner
from mysoul.model import ReplayModel
from mysoul.service import SoulService
from mysoul.storage import Conflict


class ArtifactModel(ReplayModel):
    async def execute_step(self, context, tool_specs, limits):
        self.calls += 1
        assert {t["name"] for t in tool_specs} <= {"draft", "read_file", "write_file"}
        assert "qq_send" not in {t["name"] for t in tool_specs}
        if not context.step_results:
            text = "checked" if "Procedure: verify" in context.skill else "unchecked"
            return StepDecision(tool="write_file", arguments={"path": "answer.txt", "text": text})
        return StepDecision(done=True)


async def test_candidate_uses_selected_model_and_records_baseline_objective(tmp_path):
    from mysoul.evolution import RegressionCase

    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        soul.store.add_evidence(Evidence(id="feedback", text="answer.txt was unchecked"))
        proposal = soul.skills.propose("# Work\nProcedure: verify\n", ["feedback"])
        case = RegressionCase(
            id="real-artifact", objective="Write checked to answer.txt",
            expected_files={"answer.txt": "checked"}, required_tools={"write_file"},
        )
        result = await CandidateRunner(
            soul.skills, model_factory=ArtifactModel, cases=[case], model_label="selected-model"
        ).run(proposal.id)
        assert result["objective_pass"] is True
        assert result["baseline"][0]["objective_pass"] is False
        assert result["candidate"][0]["objective_pass"] is True
        assert result["model_label"] == "selected-model"
        assert result["case_hash"]
        assert not result["live_transport"]
        assert not (tmp_path / "workspace/answer.txt").exists()


async def test_selected_model_rating_cannot_override_real_artifact_failure(tmp_path):
    from mysoul.evolution import RegressionCase

    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        soul.store.add_evidence(Evidence(id="feedback", text="wrong artifact"))
        proposal = soul.skills.propose("# Work\nProcedure: verify\n", ["feedback"])
        result = await CandidateRunner(soul.skills, model_factory=ArtifactModel, cases=[
            RegressionCase(id="wrong", objective="Write exact answer", expected_files={
                "answer.txt": "a different exact answer"
            })
        ]).run(proposal.id, model_judgment="excellent")
        assert not result["objective_pass"]
        with pytest.raises(Conflict):
            soul.skills.activate(proposal.id, proposal.base_hash, proposal.candidate_hash)


async def test_candidate_calls_use_subject_budget(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path, model_call_limit=0)) as soul:
        soul.store.add_evidence(Evidence(id="feedback", text="needs verification"))
        proposal = soul.skills.propose("# Work\nProcedure: verify\n", ["feedback"])
        with pytest.raises(Conflict, match="budget"):
            await soul.test_candidate(proposal.id)
        assert not soul.store.all("skill_test")


async def test_candidate_model_cannot_use_live_tool_even_if_it_requests_one(tmp_path):
    from mysoul.evolution import RegressionCase

    def model_factory():
        return ReplayModel([StepDecision(tool="qq_send", arguments={"text": "must not send"})])

    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        soul.store.add_evidence(Evidence(id="feedback", text="keep testing isolated"))
        proposal = soul.skills.propose("# Work\nProcedure: verify\n", ["feedback"])
        result = await CandidateRunner(soul.skills, model_factory=model_factory, cases=[
            RegressionCase(id="blocked", objective="produce answer", expected_files={"x": "y"})
        ]).run(proposal.id)
        assert not result["objective_pass"]
        assert result["candidate"][0]["status"] == "suspended"
        assert result["candidate"][0]["outcomes"] == ["not_sent"]
        assert not soul.store.all("goal")
