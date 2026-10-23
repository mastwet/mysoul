"""One durable, owner-scoped self-wakeup. Scheduling is not an external message."""

import json
from datetime import datetime, timedelta

from pydantic import Field, ValidationError, field_validator

from mysoul.conversation import boundary_in
from mysoul.domain import Contract, LifeState, Scope, now


class ScheduleWakeupArgs(Contract):
    after_seconds: int = Field(ge=30, le=86400, strict=True)
    reason: str = Field(min_length=1, max_length=300)
    goal_id: str | None = Field(default=None, max_length=200)

    @field_validator("reason")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Wakeup reason is empty")
        return value.strip()


class WakeupStore:
    def __init__(self, store, clock=now):
        self.store, self.clock = store, clock

    @staticmethod
    def spec():
        return {
            "name": "schedule_wakeup",
            "description": ("安排本体下次自主唤醒，替换旧安排。到点重新决定活动，"
                            "不自动发言；不是固定时间提醒。"),
            "parameters": ScheduleWakeupArgs.model_json_schema(),
        }

    @staticmethod
    def _save(db, body):
        db.execute(
            "INSERT OR REPLACE INTO objects VALUES('scheduled_wakeup',?,?)",
            (body["id"], json.dumps(body, ensure_ascii=False)),
        )

    @staticmethod
    def _head(db):
        row = db.execute(
            "SELECT body FROM objects WHERE kind='wakeup_head' AND id='current'"
        ).fetchone()
        if not row:
            return None
        ident = json.loads(row[0])["id"]
        row = db.execute(
            "SELECT body FROM objects WHERE kind='scheduled_wakeup' AND id=?", (ident,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def _state(db):
        return LifeState.model_validate_json(
            db.execute("SELECT body FROM subjects WHERE id='mysoul'").fetchone()[0]
        )

    @staticmethod
    def _state_save(db, state):
        db.execute(
            "UPDATE subjects SET body=? WHERE id='mysoul' AND epoch=?",
            (state.model_dump_json(), state.dispatch_epoch),
        )

    @staticmethod
    def _goal_status(db, ident):
        if not ident:
            return None
        row = db.execute("SELECT body FROM objects WHERE kind='goal' AND id=?", (ident,)).fetchone()
        if not row:
            return "missing"
        goal = json.loads(row[0])
        if goal.get("cancelled") or goal["status"] in {"cancelled", "abandoned"}:
            return "cancelled"
        if db.execute(
            "SELECT 1 FROM objects WHERE kind='conversation_archived_goal' AND id=?", (ident,)
        ).fetchone():
            return "cancelled"
        contexts = db.execute(
            "SELECT c.body FROM objects a JOIN objects c ON c.kind='activity_context' "
            "AND c.id=a.id WHERE a.kind='activity' AND "
            "json_extract(a.body,'$.goal_id')=?",
            (ident,),
        ).fetchall()
        if contexts and not any(
            json.loads(r[0]).get("scope") == Scope().model_dump() for r in contexts
        ):
            return "denied"
        # Pending background requests and API-created owner goals can have no context yet.
        return None

    @classmethod
    def cancel_in(cls, db, reason, instant):
        body = cls._head(db)
        if not body or body["status"] != "scheduled":
            return
        body.update(status="cancelled", finished_at=instant.isoformat(), outcome=reason)
        cls._save(db, body)
        state = cls._state(db)
        if state.next_initiative_at and state.next_initiative_at.isoformat() == body["due_at"]:
            state.next_initiative_at = (
                instant + timedelta(minutes=state.autonomy_interval_minutes)
                if state.autonomy_enabled
                else None
            )
            cls._state_save(db, state)

    def _pending_in(self, db):
        body = self._head(db)
        if not body or body["status"] != "scheduled":
            return None
        state = self._state(db)
        cause = (
            "autonomy_disabled"
            if not state.autonomy_enabled
            else "conversation_reset"
            if boundary_in(db)["revision"] != body["session_revision"]
            else self._goal_status(db, body.get("goal_id"))
        )
        if cause:
            self.cancel_in(db, cause, self.clock())
            return None
        return body

    def pending(self):
        with self.store.transaction() as db:
            return self._pending_in(db)

    def schedule(self, arguments, *, call_id, epoch, scope, accept=None):
        if scope != Scope():
            return {"status": "denied"}
        try:
            args = ScheduleWakeupArgs.model_validate(arguments)
        except ValidationError:
            return {"status": "invalid_arguments"}
        with self.store.transaction() as db:
            state = self._state(db)
            if state.dispatch_epoch != epoch:
                return {"status": "interrupted"}
            if not state.autonomy_enabled:
                return {"status": "disabled"}
            if self._goal_status(db, args.goal_id):
                return {"status": "denied"}
            ident = "wakeup:" + call_id
            row = db.execute(
                "SELECT body FROM objects WHERE kind='scheduled_wakeup' AND id=?", (ident,)
            ).fetchone()
            if row:
                previous = json.loads(row[0])
                return (
                    previous["result"]
                    if previous["arguments"] == args.model_dump()
                    else {"status": "conflict"}
                )
            instant = self.clock()
            due = instant + timedelta(seconds=args.after_seconds)
            result = {
                "status": "scheduled",
                "ref": ident,
                "due_at": due.isoformat(),
                "reason": args.reason,
                "goal_id": args.goal_id,
            }
            if accept is not None and not accept(result):
                return {"status": "context_budget"}
            body = {
                "id": ident,
                "created_at": instant.isoformat(),
                "due_at": due.isoformat(),
                "reason": args.reason,
                "goal_id": args.goal_id,
                "epoch": epoch,
                "session_revision": boundary_in(db)["revision"],
                "status": "scheduled",
                "arguments": args.model_dump(),
                "result": result,
            }
            old = self._head(db)
            if old and old["status"] == "scheduled":
                old.update(status="replaced", finished_at=instant.isoformat())
                self._save(db, old)
            self._save(db, body)
            db.execute(
                "INSERT OR REPLACE INTO objects VALUES('wakeup_head','current',?)",
                (json.dumps({"id": ident}),),
            )
            state.next_initiative_at = due
            state.rest_until = None
            self._state_save(db, state)
            return result

    def public_pending(self):
        body = self.pending()
        if not body:
            return None
        return {
            key: body.get(key)
            for key in ("id", "created_at", "due_at", "reason", "goal_id", "status")
        }

    def preserve(self):
        with self.store.transaction() as db:
            body = self._pending_in(db)
            if body:
                state = self._state(db)
                state.next_initiative_at = datetime.fromisoformat(body["due_at"])
                self._state_save(db, state)

    def valid_origin(self, ident):
        """Check a running wake's dependencies, independently of a new next wake."""
        with self.store.transaction() as db:
            row = db.execute(
                "SELECT body FROM objects WHERE kind='scheduled_wakeup' AND id=?", (ident,)
            ).fetchone()
            if not row:
                return False
            body = json.loads(row[0])
            return (
                self._state(db).autonomy_enabled
                and boundary_in(db)["revision"] == body["session_revision"]
                and self._goal_status(db, body.get("goal_id")) is None
            )

    def begin(self, event, epoch, *, expected_id=None):
        with self.store.transaction() as db:
            body = self._pending_in(db)
            if (
                not body
                or (expected_id is not None and body["id"] != expected_id)
                or self._state(db).dispatch_epoch != epoch
                or datetime.fromisoformat(body["due_at"]) > self.clock()
            ):
                return None
            body.update(status="running", event_id=event.id, triggered_at=self.clock().isoformat())
            self._save(db, body)
            return body

    def finish(self, event_id, outcome):
        with self.store.transaction() as db:
            rows = db.execute(
                "SELECT body FROM objects WHERE kind='scheduled_wakeup' AND "
                "json_extract(body,'$.event_id')=?",
                (event_id,),
            ).fetchall()
            for row in rows:
                body = json.loads(row[0])
                if body["status"] != "running":
                    continue
                body.update(
                    status="failed"
                    if outcome == "error"
                    else "interrupted"
                    if outcome in {"interrupted", "paused"}
                    else "fired",
                    outcome=outcome,
                    finished_at=self.clock().isoformat(),
                )
                self._save(db, body)

    def recover(self):
        with self.store.transaction() as db:
            for row in db.execute(
                "SELECT body FROM objects WHERE kind='scheduled_wakeup' AND "
                "json_extract(body,'$.status')='running'"
            ).fetchall():
                body = json.loads(row[0])
                body.update(
                    status="interrupted", outcome="restart", finished_at=self.clock().isoformat()
                )
                self._save(db, body)
        self.preserve()
