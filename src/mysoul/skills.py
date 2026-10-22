"""Immutable skill versions and hash-bound operator activation."""

import difflib
from hashlib import sha256
from pathlib import Path

from mysoul.domain import SkillProposal, SkillVersion
from mysoul.storage import Conflict

INITIAL_SKILL = (
    "# Work\nProcedure: draft\nProduce a bounded artifact. Report limitations honestly.\n"
)


def digest(text):
    return sha256(text.encode("utf-8")).hexdigest()


class SkillStore:
    def __init__(self, store, versions_dir: Path):
        self.store, self.directory = store, versions_dir
        self.directory.mkdir(parents=True, exist_ok=True)

    def _write(self, text):
        content_hash = digest(text)
        path = self.directory / f"{content_hash}.md"
        if path.exists():
            if path.read_text(encoding="utf-8") != text:
                raise Conflict("Skill artifact hash mismatch")
        else:
            with path.open("x", encoding="utf-8", newline="") as file:
                file.write(text)
        return content_hash

    def initialize(self, text=INITIAL_SKILL):
        if self.store.get("skill_active", "work"):
            return self.active()
        version = SkillVersion(
            content_hash=self._write(text), text=text, review="Initial operator baseline"
        )
        self.store.put("skill_version", version.content_hash, version.model_dump(mode="json"))
        self.store.put("skill_active", "work", {"hash": version.content_hash})
        return version

    def active(self, skill_id="work") -> SkillVersion:
        pointer = self.store.get("skill_active", skill_id)
        version = SkillVersion.model_validate(self.store.get("skill_version", pointer["hash"]))
        if self._write(version.text) != version.content_hash:
            raise Conflict("Skill metadata hash mismatch")
        return version

    def propose(self, text: str, evidence_refs: list[str], *, target="skill"):
        if target != "skill":
            raise PermissionError("Only skill Markdown procedures may evolve")
        if not evidence_refs or not text.strip() or len(text) > 16000:
            raise ValueError("Bounded Markdown and evidence are required")
        for ref in evidence_refs:
            self.store.evidence(ref)
        if any(
            p["status"] in {"proposed", "tested", "approved"} for p in self.store.all("proposal")
        ):
            raise Conflict("Review or reject the existing proposal first")
        base = self.active()
        proposal = SkillProposal(
            base_hash=base.content_hash,
            candidate_hash=self._write(text),
            text=text,
            evidence_refs=evidence_refs,
        )
        self.store.put("proposal", proposal.id, proposal.model_dump(mode="json"))
        return proposal

    def proposal(self, proposal_id):
        value = self.store.get("proposal", proposal_id)
        if value is None:
            raise KeyError(proposal_id)
        return SkillProposal.model_validate(value)

    def diff(self, proposal_id):
        proposal = self.proposal(proposal_id)
        old = self.store.get("skill_version", proposal.base_hash)["text"]
        return "".join(
            difflib.unified_diff(
                old.splitlines(True),
                proposal.text.splitlines(True),
                fromfile="active.md",
                tofile="candidate.md",
            )
        )

    def activate(self, proposal_id, expected_base_hash, approved_candidate_hash):
        proposal = self.proposal(proposal_id)
        self._write(proposal.text)
        with self.store.transaction() as db:
            import json

            active = json.loads(
                db.execute(
                    "SELECT body FROM objects WHERE kind='skill_active' AND id='work'"
                ).fetchone()[0]
            )
            current = SkillProposal.model_validate_json(
                db.execute(
                    "SELECT body FROM objects WHERE kind='proposal' AND id=?", (proposal_id,)
                ).fetchone()[0]
            )
            if (
                active["hash"] != expected_base_hash
                or current.base_hash != expected_base_hash
                or current.candidate_hash != approved_candidate_hash
                or digest(current.text) != approved_candidate_hash
                or current.status != "tested"
            ):
                raise Conflict("Stale or untested skill approval")
            runs = [
                json.loads(
                    db.execute(
                        "SELECT body FROM objects WHERE kind='skill_test' AND id=?", (run_id,)
                    ).fetchone()[0]
                )
                for run_id in current.test_run_ids
            ]
            if not runs or not all(
                r["objective_pass"]
                and r["candidate_hash"] == approved_candidate_hash
                and not r["live_transport"]
                for r in runs
            ):
                raise Conflict("Objective candidate regression gate failed")
            version = SkillVersion(
                content_hash=current.candidate_hash,
                text=current.text,
                parent=current.base_hash,
                review=f"Operator approved proposal {proposal_id}",
            )
            current.status = "active"
            for kind, ident, value in [
                ("skill_version", version.content_hash, version.model_dump(mode="json")),
                ("skill_active", "work", {"hash": version.content_hash}),
                ("proposal", current.id, current.model_dump(mode="json")),
            ]:
                db.execute(
                    "INSERT OR REPLACE INTO objects VALUES(?,?,?)", (kind, ident, json.dumps(value))
                )
            return version

    def reject(self, proposal_id):
        proposal = self.proposal(proposal_id)
        if proposal.status not in {"proposed", "tested"}:
            raise Conflict("Proposal already closed")
        proposal.status = "rejected"
        self.store.put("proposal", proposal.id, proposal.model_dump(mode="json"))
        return proposal

    def rollback(self, skill_id, target_version):
        version = SkillVersion.model_validate(self.store.get("skill_version", target_version))
        if version.skill_id != skill_id:
            raise Conflict("Wrong skill rollback target")
        self._write(version.text)
        self.store.put("skill_active", skill_id, {"hash": version.content_hash})
        return version
