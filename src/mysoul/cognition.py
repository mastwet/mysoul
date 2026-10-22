"""Durable memory and persona maintenance, sharing the application's SQLite authority."""

import json
from typing import Literal

from pydantic import Field

from mysoul.domain import Contract, Event, Evidence, Scope
from mysoul.laputa import RecapStore


class SourceSlice(Contract):
    source_id: str
    event_id: str
    role: Literal["user", "assistant", "failure", "outcome", "legacy"]
    scope: Scope
    text: str
    start: int
    end: int
    total: int


class SourceWindow(Contract):
    recap_version: int
    invalidation_epoch: int
    slices: list[SourceSlice] = Field(default_factory=list)

    @property
    def refs(self):
        return list(dict.fromkeys(s.source_id for s in self.slices))


class CognitiveStore:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def _insert(db, ident, event_id, role, text, scope, created_at):
        if not text or scope.audience != "owner":
            return
        evidence = Evidence(
            id=ident, text=text, scope=scope, source="experience:" + role,
            source_scopes=[scope], created_at=created_at,
        )
        db.execute(
            "INSERT OR IGNORE INTO evidence VALUES(?,?)", (ident, evidence.model_dump_json()),
        )
        db.execute("INSERT OR IGNORE INTO memory_queue(id) VALUES(?)", (ident,))
        db.execute("INSERT OR IGNORE INTO objects VALUES('cognitive_source',?,?)", (
            ident, json.dumps({"id": ident, "event_id": event_id, "role": role,
                               "scope": scope.model_dump(), "covered": 0, "total": len(text),
                               "created_at": created_at.isoformat()}, ensure_ascii=False),
        ))

    def capture_interaction(self, event_id):
        with self.store.transaction() as db:
            self.capture_interaction_in(db, event_id)

    @classmethod
    def capture_interaction_in(cls, db, event_id):
        event_row = db.execute("SELECT body FROM events WHERE id=?", (event_id,)).fetchone()
        row = db.execute(
            "SELECT body FROM objects WHERE kind='interaction' AND id=?", (event_id,),
        ).fetchone()
        if not event_row or not row:
            return
        event, result = Event.model_validate_json(event_row[0]), json.loads(row[0])
        if event.scope.audience != "owner":
            return
        if event.source != "local-initiative":
            cls._insert(db, "experience:" + event.id + ":user", event.id, "user",
                        event.content, event.scope, event.received_at)
        failure = result.get("error") or result.get("choice") in {"unknown", "interrupted"}
        text = result.get("text", "")
        if text in {"Model unavailable", "Rest or runtime limit", "Context budget exhausted"}:
            failure = True
        if failure:
            text = json.dumps({"error": result.get("error"), "choice": result.get("choice"),
                               "message": text}, ensure_ascii=False)
        role = "failure" if failure else "assistant"
        cls._insert(db, "experience:" + event.id + ":" + role, event.id, role,
                    text, event.scope, event.received_at)

    def capture_outcome(self, activity_id):
        from mysoul.domain import now

        activity = self.store.activity(activity_id)
        if activity.status not in {"completed", "failed", "cancelled", "abandoned", "suspended"}:
            return
        context = self.store.get("activity_context", activity_id)
        if not context or context["scope"]["audience"] != "owner":
            return
        goal = self.store.goal(activity.goal_id)
        text = json.dumps({"activity": activity.model_dump(mode="json"),
                           "objective": goal.objective, "effects": [
                               {"id": req.action_id, "tool": req.tool, "outcome": res.outcome,
                                "evidence_ref": res.evidence_ref, "error": res.error}
                               for req, res in self.store.effects_for_goal(goal.id)
                           ]}, ensure_ascii=False)
        ident = f"outcome:{activity_id}:{activity.cursor}:{activity.status}"
        with self.store.transaction() as db:
            self._insert(db, ident, activity_id, "outcome", text, Scope(), now())

    def migrate_pending(self):
        if self.store.get("cognitive_migration", "v1"):
            return
        with self.store.transaction() as db:
            for segment in self.store.all("recap_segment"):
                ref = segment["id"]
                if segment["status"] != "pending":
                    db.execute("INSERT OR IGNORE INTO objects VALUES('cognitive_legacy',?,?)", (
                        ref, json.dumps({"id": ref, "status": "legacy_excerpt"}),
                    ))
                    continue
                event_id = ref.removeprefix("reply:")
                if self.store.get("interaction", event_id):
                    self.capture_interaction_in(db, event_id)
                else:
                    evidence = self.store.evidence(ref)
                    # Unsettled interactions will be captured atomically when they finish.
                    if db.execute("SELECT 1 FROM events WHERE id=?", (ref,)).fetchone():
                        continue
                    self._insert(db, "legacy:" + ref, ref, "legacy", evidence.text,
                                 evidence.scope, evidence.created_at)
            db.execute("INSERT INTO objects VALUES('cognitive_migration','v1','{}')")

    def pending_window(self, max_chars):
        if max_chars <= 0:
            raise ValueError("Positive source window budget required")
        recap = RecapStore(self.store).current()
        window = SourceWindow(recap_version=recap.version,
                              invalidation_epoch=recap.invalidation_epoch)
        remaining = max_chars
        for source in sorted(self.store.all("cognitive_source"), key=lambda s: (
            s["created_at"], s["event_id"], s["role"] != "user", s["id"],
        )):
            start = source["covered"]
            if source.get("cleared") or start >= source["total"]:
                continue
            evidence = self.store.evidence(source["id"])
            size = source["total"] - start
            if window.slices and size > remaining:
                break
            end = min(source["total"], start + remaining)
            window.slices.append(SourceSlice(
                source_id=source["id"], event_id=source["event_id"], role=source["role"],
                scope=source["scope"], text=evidence.text[start:end],
                start=start, end=end, total=source["total"],
            ))
            remaining -= end - start
            if not remaining:
                break
        return window if window.slices else None
