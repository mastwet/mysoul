from mysoul.config import Settings
from mysoul.domain import Activity, Evidence
from mysoul.service import SoulService


async def test_reflection_is_visible_budgeted_and_proposes_from_evidence(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        soul.store.add_evidence(Evidence(id="failure", text="Report was not verified"))
        before = soul.store.load_subject().model_calls
        proposal = await soul.reflect(["failure"])
        assert proposal.evidence_refs == ["failure"]
        assert soul.store.load_subject().activity == Activity.REFLECT
        assert soul.store.load_subject().model_calls == before + 1
        assert soul.store.all("reflection")[-1]["proposal_id"] == proposal.id
