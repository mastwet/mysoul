import pytest

from mysoul.domain import Evidence
from mysoul.evolution import CandidateRunner
from mysoul.skills import SkillStore
from mysoul.storage import Conflict, StateStore


@pytest.fixture
def rig(tmp_path):
    store = StateStore(tmp_path / "s.db")
    store.add_evidence(Evidence(id="failure", text="Artifact was not verified"))
    skills = SkillStore(store, tmp_path / "versions")
    skills.initialize("# Work\nProcedure: draft\n")
    yield store, skills
    store.close()


def test_proposal_requires_evidence(rig):
    _, skills = rig
    with pytest.raises(ValueError):
        skills.propose("# Work\nProcedure: verify\n", [])
    with pytest.raises(KeyError):
        skills.propose("# Work\nProcedure: verify\n", ["missing"])


@pytest.mark.parametrize("target", ["runtime", "persona", "permissions"])
def test_runtime_or_persona_edit_rejected(rig, target):
    _, skills = rig
    with pytest.raises(PermissionError):
        skills.propose("change authority", ["failure"], target=target)


async def test_candidate_cannot_use_real_effects(rig):
    store, skills = rig
    proposal = skills.propose("# Work\nProcedure: verify\n", ["failure"])
    result = await CandidateRunner(skills).run(proposal.id)
    assert result["objective_pass"] is True
    assert result["live_transport"] is False
    assert result["model_judgment"] is None
    assert "read_file" in result["tools"]
    assert store.get("proposal", proposal.id)["status"] == "tested"


async def test_stale_approval_conflicts(rig):
    _, skills = rig
    proposal = skills.propose("# Work\nProcedure: verify\n", ["failure"])
    await CandidateRunner(skills).run(proposal.id)
    with pytest.raises(Conflict):
        skills.activate(proposal.id, proposal.base_hash, "wrong")
    skills.activate(proposal.id, proposal.base_hash, proposal.candidate_hash)
    with pytest.raises(Conflict):
        skills.activate(proposal.id, proposal.base_hash, proposal.candidate_hash)


async def test_failed_objective_cannot_be_overridden_by_model_rating(rig):
    _, skills = rig
    proposal = skills.propose("# Work\nProcedure: draft\n", ["failure"])
    result = await CandidateRunner(skills).run(proposal.id, model_judgment="excellent")
    assert not result["objective_pass"]
    with pytest.raises(Conflict):
        skills.activate(proposal.id, proposal.base_hash, proposal.candidate_hash)
