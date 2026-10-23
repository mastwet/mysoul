"""Persistent boundaries for the single visible owner conversation; originals stay archived."""

import json
from datetime import timedelta
from hashlib import sha256

from fastapi import Depends, Query
from pydantic import Field

from mysoul.domain import TERMINAL, Activity, Contract, LifeState, RecapVersion, Scope, now
from mysoul.storage import Conflict


def boundary_in(db):
    row = db.execute(
        "SELECT body FROM objects WHERE kind='conversation' AND id='current'"
    ).fetchone()
    return (
        json.loads(row[0])
        if row
        else {"revision": 0, "timeline_floor": 0, "event_floor": 0, "object_floor": 0}
    )


def current_source_in(db, ident):
    boundary = boundary_in(db)
    if not boundary["revision"]:
        return True
    event = db.execute("SELECT rowid FROM events WHERE id=?", (ident,)).fetchone()
    if event:
        return event[0] > boundary["event_floor"]
    goal = db.execute(
        "SELECT g.id FROM objects a JOIN objects g "
        "ON g.kind='goal' AND g.id=json_extract(a.body,'$.goal_id') "
        "WHERE a.kind='activity' AND a.id=?",
        (ident,),
    ).fetchone()
    return (
        goal is None
        or db.execute(
            "SELECT 1 FROM objects WHERE kind='conversation_archived_goal' AND id=?", (goal[0],)
        ).fetchone()
        is None
    )


class ConversationStore:
    def __init__(self, store):
        self.store = store

    def current(self):
        with self.store.lock:
            return boundary_in(self.store.db)

    def reset(self, expected_version):
        with self.store.transaction() as db:
            old = boundary_in(db)
            if old["revision"] != expected_version:
                raise Conflict("Conversation changed; reload before resetting")
            instant = now()
            state = LifeState.model_validate_json(
                db.execute("SELECT body FROM subjects WHERE id='mysoul'").fetchone()[0]
            )
            state.dispatch_epoch += 1
            state.activity, state.current_activity_id, state.rest_until = Activity.REST, None, None
            state.autonomy_last_check_id = None
            state.autonomy_last_result = "waiting"
            state.updated_at = instant
            state.next_initiative_at = (
                instant + timedelta(minutes=state.autonomy_interval_minutes)
                if state.autonomy_enabled
                else None
            )
            db.execute(
                "UPDATE subjects SET epoch=?,body=? WHERE id='mysoul'",
                (state.dispatch_epoch, state.model_dump_json()),
            )
            head = db.execute("SELECT version FROM recap_head WHERE subject='mysoul'").fetchone()[0]
            recap = RecapVersion.model_validate_json(
                db.execute(
                    "SELECT body FROM recap WHERE subject='mysoul' AND version=?", (head,)
                ).fetchone()[0]
            )
            empty = RecapVersion(
                version=head + 1,
                parent=head,
                author="conversation-reset",
                invalidation_epoch=recap.invalidation_epoch + 1,
                content_hash=sha256(b"").hexdigest(),
            )
            db.execute(
                "INSERT INTO recap VALUES('mysoul',?,?)", (empty.version, empty.model_dump_json())
            )
            db.execute("UPDATE recap_head SET version=? WHERE subject='mysoul'", (empty.version,))
            boundary = {
                "revision": old["revision"] + 1,
                "created_at": instant.isoformat(),
                "timeline_floor": db.execute(
                    "SELECT COALESCE(MAX(seq),0) FROM timeline"
                ).fetchone()[0],
                "event_floor": db.execute("SELECT COALESCE(MAX(rowid),0) FROM events").fetchone()[
                    0
                ],
                "object_floor": db.execute("SELECT COALESCE(MAX(rowid),0) FROM objects").fetchone()[
                    0
                ],
            }
            archive = boundary | {"start_seq": old["timeline_floor"], "recap_version": head}
            for ident, encoded in db.execute(
                "SELECT id,body FROM objects WHERE kind='goal'"
            ).fetchall():
                goal = json.loads(encoded)
                contexts = db.execute(
                    "SELECT c.body FROM objects a JOIN objects c ON "
                    "c.kind='activity_context' AND c.id=a.id WHERE a.kind='activity' AND "
                    "json_extract(a.body,'$.goal_id')=?",
                    (ident,),
                ).fetchall()
                if contexts and not any(
                    json.loads(row[0]).get("scope") == Scope().model_dump() for row in contexts
                ):
                    continue
                db.execute(
                    "INSERT OR IGNORE INTO objects VALUES('conversation_archived_goal',?,?)",
                    (ident, json.dumps({"revision": boundary["revision"]})),
                )
                if goal["status"] not in TERMINAL:
                    goal.update(status="cancelled", cancelled=True)
                    db.execute(
                        "UPDATE objects SET body=? WHERE kind='goal' AND id=?",
                        (json.dumps(goal), ident),
                    )
                    db.execute(
                        "UPDATE objects SET body=json_set(body,'$.status','cancelled') "
                        "WHERE kind='activity' AND json_extract(body,'$.goal_id')=? AND "
                        "json_extract(body,'$.status') NOT IN "
                        "('completed','failed','cancelled','abandoned')",
                        (ident,),
                    )
            db.execute(
                "UPDATE objects SET body=json_set(body,'$.cleared',1) WHERE kind='cognitive_source'"
            )
            db.execute(
                "UPDATE objects SET body=json_set(body,'$.status','cleared') WHERE "
                "kind='recap_segment' AND json_extract(body,'$.status')='pending'"
            )
            for kind in ("cognitive_run", "compression_run", "activity_choice"):
                db.execute(
                    "UPDATE objects SET body=json_set(body,'$.status','superseded') WHERE "
                    "kind=? AND json_extract(body,'$.status') IN "
                    "('queued','running','pending','failed')",
                    (kind,),
                )
            db.execute(
                "UPDATE objects SET body=json_set(body,'$.status','recorded') WHERE "
                "kind='task_feedback' AND json_extract(body,'$.status')='pending'"
            )
            from mysoul.wakeup import WakeupStore

            WakeupStore.cancel_in(db, "conversation_reset", instant)
            db.execute(
                "INSERT INTO objects VALUES('conversation_archive',?,?)",
                (str(boundary["revision"]), json.dumps(archive)),
            )
            db.execute(
                "INSERT OR REPLACE INTO objects VALUES('conversation','current',?)",
                (json.dumps(boundary),),
            )
        return boundary | {"recap": empty.model_dump(mode="json")}


class ResetInput(Contract):
    expected_version: int = Field(ge=0)


def register_conversation_routes(app, authorize):
    guard = [Depends(authorize)]

    @app.post("/api/conversation/reset", dependencies=guard)
    async def reset(body: ResetInput):
        return ConversationStore(app.state.soul.store).reset(body.expected_version)

    @app.get("/api/conversation/archives/{revision}", dependencies=guard)
    async def archive(
        revision: int,
        before: int | None = Query(default=None, ge=1),
        limit: int = Query(default=50, ge=1, le=100),
    ):
        from mysoul.timeline import TimelineStore

        return TimelineStore(app.state.soul.store).page(
            before=before, limit=limit, archive_revision=revision
        )
