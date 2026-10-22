"""Candidate regression runs compose a fresh offline service with fixed tools."""

import asyncio
import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated

from pydantic import Field, model_validator

from mysoul.config import Settings
from mysoul.domain import Contract, Goal, SkillVersion, StepDecision, uid
from mysoul.model import ReplayModel, reservation
from mysoul.storage import Conflict


class ProcedureReplayModel(ReplayModel):
    """Deterministic fixture interpreting only draft/verify procedure directives.

    It is a regression fixture, not evidence of live model improvement.
    """

    async def execute_step(self, context, tool_specs, limits):
        if "[reflection]" in context.instructions or "[recap]" in context.instructions:
            return await super().execute_step(context, tool_specs, limits)
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


class RegressionCase(Contract):
    id: str = Field(min_length=1, max_length=100)
    objective: str = Field(min_length=1, max_length=8000)
    initial_files: dict[str, Annotated[str, Field(max_length=32000)]] = Field(
        default_factory=dict, max_length=8
    )
    expected_files: dict[str, Annotated[str, Field(max_length=32000)]] = Field(
        default_factory=dict, max_length=8
    )
    required_tools: set[str] = Field(default_factory=set, max_length=3)

    @model_validator(mode="after")
    def has_objective_assertions(self):
        if not self.expected_files and not self.required_tools:
            raise ValueError("Regression needs objective file or tool assertions")
        if not self.required_tools <= {"draft", "read_file", "write_file"}:
            raise ValueError("Regression tools are local only")
        return self


class BudgetedCandidateModel:
    """A candidate has local limits and also charges the live subject before every call."""

    def __init__(self, model, owner, epoch):
        self.model, self.owner, self.epoch = model, owner, epoch

    def reservation(self, context, limits, tool_specs=None):
        return reservation(self.model, context, limits, tool_specs)[0]

    async def execute_step(self, context, tool_specs, limits):
        state = self.owner.store.load_subject()
        reserve, attempts = reservation(self.model, context, limits, tool_specs)
        if state.dispatch_epoch != self.epoch:
            raise Conflict("Candidate evaluation superseded")
        if (state.model_calls + attempts > self.owner.settings.model_call_limit
                or state.tokens_used + reserve > self.owner.settings.token_budget):
            raise Conflict("Candidate evaluation budget exhausted")
        state.model_calls += attempts
        state.tokens_used += reserve
        self.owner.store.save_transition(self.epoch, state)
        result = await self.model.execute_step(context, tool_specs, limits)
        if self.owner.store.load_subject().dispatch_epoch != self.epoch:
            raise Conflict("Candidate evaluation superseded")
        return result

    async def close(self):
        close = getattr(self.model, "close", None)
        if close:
            await close()


class CandidateRunner:
    def __init__(
        self, skills, *, model_factory=ProcedureReplayModel, cases=None,
        model_label="procedure-replay", budget_owner=None,
    ):
        self.skills = skills
        self.model_factory, self.model_label = model_factory, model_label
        self.budget_owner = budget_owner
        self.cases = cases or [RegressionCase(
            id="write-and-verify", objective="Write report and verify its contents",
            expected_files={"report.txt": "verified report"},
            required_tools={"write_file", "read_file"},
        )]
        self.cases = [RegressionCase.model_validate(case) for case in self.cases]
        if len(self.cases) > 4 or len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("At most four distinct regression cases")

    async def _trial(self, text, content_hash, case, epoch):
        from mysoul.service import SoulService

        model = self.model_factory()
        if self.budget_owner:
            model = BudgetedCandidateModel(model, self.budget_owner, epoch)
        with TemporaryDirectory(prefix="mysoul-candidate-") as directory:
            async with SoulService(Settings(
                data_dir=Path(directory), model_call_limit=8, token_budget=32000
            ), model=model) as soul:
                version = SkillVersion(content_hash=content_hash, text=text)
                if soul.skills._write(version.text) != content_hash:
                    raise Conflict("Candidate artifact hash mismatch")
                soul.store.put("skill_version", content_hash, version.model_dump(mode="json"))
                soul.store.put("skill_active", "work", {"hash": content_hash})
                error = None
                status = "failed"
                files_match = False
                artifacts = {}
                try:
                    for path, content in case.initial_files.items():
                        soul.files.write(path, content)
                    activity = await soul.start_goal(Goal(
                        objective=case.objective, token_limit=32000,
                        allowed_tools={"draft", "read_file", "write_file"},
                    ))
                    status = activity.status
                    for path in case.expected_files:
                        try:
                            artifacts[path] = soul.files.read(path)
                        except (ValueError, OSError):
                            artifacts[path] = None
                    files_match = artifacts == case.expected_files
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    error = type(exc).__name__
                with soul.store.lock:
                    effects = soul.store.db.execute(
                        "SELECT request,result FROM effects ORDER BY rowid"
                    ).fetchall()
                tools = [json.loads(request)["tool"] for request, _ in effects]
                outcomes = [json.loads(receipt)["outcome"] for _, receipt in effects]
                return {
                    "case_id": case.id, "status": status, "error": error,
                    "objective_pass": (
                        status == "completed" and files_match
                        and case.required_tools <= set(tools)
                        and all(outcome == "confirmed" for outcome in outcomes)
                    ),
                    "tools": tools, "outcomes": outcomes,
                    "artifacts": artifacts,
                }

    async def run(self, proposal_id, model_judgment=None):
        proposal = self.skills.proposal(proposal_id)
        if proposal.status not in {"proposed", "tested"}:
            raise Conflict("Cannot test a closed proposal")
        epoch = None
        if self.budget_owner:
            state = self.budget_owner.store.load_subject()
            epoch = state.dispatch_epoch
            if (state.model_calls >= self.budget_owner.settings.model_call_limit
                    or state.tokens_used >= self.budget_owner.settings.token_budget):
                raise Conflict("Candidate evaluation budget exhausted")
        base = self.skills.store.get("skill_version", proposal.base_hash)
        baseline, candidate = [], []
        for case in self.cases:
            baseline.append(await self._trial(base["text"], proposal.base_hash, case, epoch))
            candidate.append(await self._trial(proposal.text, proposal.candidate_hash, case, epoch))
        result = {
            "id": uid(), "base_hash": proposal.base_hash,
            "candidate_hash": proposal.candidate_hash,
            "cases": [case.model_dump(mode="json") for case in self.cases],
            "case_hash": sha256(json.dumps([
                {**case.model_dump(mode="json"), "required_tools": sorted(case.required_tools)}
                for case in self.cases
            ], sort_keys=True).encode()).hexdigest(),
            "objective_pass": all(run["objective_pass"] for run in candidate),
            "live_transport": False, "model_judgment": model_judgment,
            "model_label": self.model_label, "baseline": baseline, "candidate": candidate,
            "tools": [tool for run in candidate for tool in run["tools"]],
            "fixture": ",".join(case.id for case in self.cases),
            "limits": "8 steps / 32000 reserved tokens per trial; local tools; temporary workspace",
        }
        self.skills.store.put("skill_test", result["id"], result)
        with self.skills.store.transaction() as db:
            from mysoul.domain import SkillProposal

            current = SkillProposal.model_validate_json(
                db.execute(
                    "SELECT body FROM objects WHERE kind='proposal' AND id=?", (proposal.id,)
                ).fetchone()[0]
            )
            if (
                current.status not in {"proposed", "tested"}
                or current.candidate_hash != proposal.candidate_hash
            ):
                raise Conflict("Proposal changed while candidate tests were running")
            current.test_run_ids.append(result["id"])
            current.status = "tested"
            db.execute(
                "UPDATE objects SET body=? WHERE kind='proposal' AND id=?",
                (current.model_dump_json(), current.id),
            )
        return result
