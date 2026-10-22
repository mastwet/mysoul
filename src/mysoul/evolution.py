"""Candidate regression runs compose a fresh offline service with fixed tools."""

from pathlib import Path
from tempfile import TemporaryDirectory

from mysoul.config import Settings
from mysoul.domain import Goal, StepDecision, uid
from mysoul.model import ReplayModel
from mysoul.storage import Conflict


class ProcedureReplayModel(ReplayModel):
    """Deterministic fixture interpreting only draft/verify procedure directives.

    It is a regression fixture, not evidence of live model improvement.
    """

    async def execute_step(self, context, tool_specs, limits):
        self.calls += 1
        self.payloads.append(context.payload())
        tools = [e.source for e in context.step_results]
        if not tools:
            return StepDecision(
                tool="write_file", arguments={"path": "report.txt", "text": "verified report"}
            )
        if len(tools) == 1 and "Procedure: verify" in context.skill:
            return StepDecision(tool="read_file", arguments={"path": "report.txt"})
        return StepDecision(done=True)


class CandidateRunner:
    def __init__(self, skills):
        self.skills = skills

    async def run(self, proposal_id, model_judgment=None):
        from mysoul.service import SoulService

        proposal = self.skills.proposal(proposal_id)
        if proposal.status not in {"proposed", "tested"}:
            raise Conflict("Cannot test a closed proposal")
        with TemporaryDirectory(prefix="mysoul-candidate-") as directory:
            async with SoulService(
                Settings(data_dir=Path(directory)), model=ProcedureReplayModel()
            ) as soul:
                # Install only the immutable candidate as this isolated fixture's baseline.
                candidate = soul.skills.initialize()
                from mysoul.domain import SkillVersion

                candidate = SkillVersion(content_hash=proposal.candidate_hash, text=proposal.text)
                soul.skills._write(candidate.text)
                soul.store.put(
                    "skill_version", candidate.content_hash, candidate.model_dump(mode="json")
                )
                soul.store.put("skill_active", "work", {"hash": candidate.content_hash})
                activity = await soul.start_goal(
                    Goal(objective="Write report and verify its contents")
                )
                tools = []
                with soul.store.lock:
                    import json

                    for (request,) in soul.store.db.execute(
                        "SELECT request FROM effects ORDER BY rowid"
                    ):
                        tools.append(json.loads(request)["tool"])
                passed = (
                    activity.status == "completed"
                    and tools == ["write_file", "read_file"]
                    and soul.files.read("report.txt") == "verified report"
                )
                result = {
                    "id": uid(),
                    "candidate_hash": proposal.candidate_hash,
                    "objective_pass": passed,
                    "live_transport": False,
                    "model_judgment": model_judgment,
                    "tools": tools,
                    "fixture": "write-and-verify",
                    "limits": "8 steps, offline, temporary workspace",
                }
        self.skills.store.put("skill_test", result["id"], result)
        proposal.test_run_ids.append(result["id"])
        proposal.status = "tested"
        self.skills.store.put("proposal", proposal.id, proposal.model_dump(mode="json"))
        return result
