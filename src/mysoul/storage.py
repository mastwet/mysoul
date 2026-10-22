"""Short durable transactions; no transaction spans a network await."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from mysoul.domain import TERMINAL, ActivityRecord, Event, Evidence, Goal, LifeState, ToolResult


class Conflict(ValueError):
    pass


class StateStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript((Path(__file__).parent / "migrations/001_initial.sql").read_text())
        self.db.commit()

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                yield self.db
                self.db.commit()
            except BaseException:
                self.db.rollback()
                raise

    def load_subject(self, subject_id="mysoul") -> LifeState:
        with self.transaction() as db:
            row = db.execute("SELECT body FROM subjects WHERE id=?", (subject_id,)).fetchone()
            if row:
                return LifeState.model_validate_json(row[0])
            state = LifeState(subject_id=subject_id)
            db.execute(
                "INSERT INTO subjects VALUES(?,?,?)", (subject_id, 0, state.model_dump_json())
            )
            return state

    def save_transition(self, expected_epoch: int, transition: LifeState):
        with self.transaction() as db:
            cursor = db.execute(
                "UPDATE subjects SET epoch=?,body=? WHERE id=? AND epoch=?",
                (
                    transition.dispatch_epoch,
                    transition.model_dump_json(),
                    transition.subject_id,
                    expected_epoch,
                ),
            )
            if cursor.rowcount != 1 or transition.dispatch_epoch < expected_epoch:
                raise Conflict("Stale dispatch epoch")

    def interrupt(self) -> LifeState:
        with self.transaction() as db:
            row = db.execute("SELECT body FROM subjects WHERE id='mysoul'").fetchone()
            state = LifeState.model_validate_json(row[0])
            state.dispatch_epoch += 1
            db.execute(
                "UPDATE subjects SET epoch=?,body=? WHERE id='mysoul'",
                (state.dispatch_epoch, state.model_dump_json()),
            )
            return state

    def add_event(self, event: Event) -> bool:
        with self.transaction() as db:
            return (
                db.execute(
                    "INSERT OR IGNORE INTO events VALUES(?,?,?)",
                    (event.id, event.dedup_key, event.model_dump_json()),
                ).rowcount
                == 1
            )

    def events(self) -> list[Event]:
        with self.lock:
            return [
                Event.model_validate_json(r[0])
                for r in self.db.execute("SELECT body FROM events ORDER BY rowid")
            ]

    def enqueue_batch(self, events: list[Event], cursor: str):
        with self.transaction() as db:
            for event in events:
                db.execute(
                    "INSERT OR IGNORE INTO events VALUES(?,?,?)",
                    (event.id, event.dedup_key, event.model_dump_json()),
                )
                canonical = db.execute(
                    "SELECT body FROM events WHERE dedup=?", (event.dedup_key,)
                ).fetchone()
                if canonical:
                    db.execute(
                        "INSERT OR IGNORE INTO inbox(dedup,body) VALUES(?,?)",
                        (event.dedup_key, canonical[0]),
                    )
            db.execute(
                "INSERT OR REPLACE INTO objects VALUES('cursor','phone',?)",
                (json.dumps({"value": cursor}),),
            )

    def pending_events(self, limit=256):
        with self.lock:
            return [
                Event.model_validate_json(row[0])
                for row in self.db.execute(
                    "SELECT body FROM inbox WHERE status='pending' ORDER BY rowid LIMIT ?", (limit,)
                )
            ]

    def processed_event(self, event):
        with self.transaction() as db:
            db.execute("UPDATE inbox SET status='processed' WHERE dedup=?", (event.dedup_key,))

    def event_for_dedup(self, dedup):
        with self.lock:
            row = self.db.execute("SELECT body FROM events WHERE dedup=?", (dedup,)).fetchone()
            return Event.model_validate_json(row[0]) if row else None

    def get(self, kind: str, ident: str):
        with self.lock:
            row = self.db.execute(
                "SELECT body FROM objects WHERE kind=? AND id=?", (kind, ident)
            ).fetchone()
            return json.loads(row[0]) if row else None

    def put(self, kind: str, ident: str, value):
        with self.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO objects VALUES(?,?,?)",
                (kind, ident, json.dumps(value, ensure_ascii=False)),
            )

    def all(self, kind: str):
        with self.lock:
            return [
                json.loads(r[0])
                for r in self.db.execute(
                    "SELECT body FROM objects WHERE kind=? ORDER BY rowid", (kind,)
                )
            ]

    def save_goal(self, goal: Goal):
        with self.transaction() as db:
            row = db.execute(
                "SELECT body FROM objects WHERE kind='goal' AND id=?", (goal.id,)
            ).fetchone()
            if row:
                old = Goal.model_validate_json(row[0])
                if old.status in TERMINAL and goal.status != old.status:
                    raise Conflict("Terminal goal cannot be revived")
            db.execute(
                "INSERT OR REPLACE INTO objects VALUES('goal',?,?)",
                (goal.id, goal.model_dump_json()),
            )

    def goal(self, ident: str) -> Goal:
        value = self.get("goal", ident)
        if value is None:
            raise KeyError(ident)
        return Goal.model_validate(value)

    def save_activity(self, activity: ActivityRecord):
        self.put("activity", activity.id, activity.model_dump(mode="json"))

    def activity(self, ident: str) -> ActivityRecord:
        return ActivityRecord.model_validate(self.get("activity", ident))

    def effect(self, ident: str) -> ToolResult | None:
        with self.lock:
            row = self.db.execute("SELECT result FROM effects WHERE id=?", (ident,)).fetchone()
            return ToolResult.model_validate_json(row[0]) if row else None

    def record_result(self, result: ToolResult):
        with self.transaction() as db:
            db.execute(
                "UPDATE effects SET result=? WHERE id=?",
                (result.model_dump_json(), result.action_id),
            )

    def recover_effects(self):
        with self.transaction() as db:
            for ident, body in db.execute("SELECT id,result FROM effects").fetchall():
                result = ToolResult.model_validate_json(body)
                if result.outcome == "in_flight":
                    result.outcome = "unknown"
                    result.error = "Process stopped before receipt; reconcile before retry"
                    db.execute(
                        "UPDATE effects SET result=? WHERE id=?", (result.model_dump_json(), ident)
                    )

    def add_evidence(self, evidence: Evidence):
        with self.transaction() as db:
            db.execute(
                "INSERT OR IGNORE INTO evidence VALUES(?,?)",
                (evidence.id, evidence.model_dump_json()),
            )
            db.execute("INSERT OR IGNORE INTO memory_queue(id) VALUES(?)", (evidence.id,))

    def evidence(self, ident: str) -> Evidence:
        with self.lock:
            row = self.db.execute("SELECT body FROM evidence WHERE id=?", (ident,)).fetchone()
            if not row:
                raise KeyError(ident)
            return Evidence.model_validate_json(row[0])

    def close(self):
        self.db.close()
