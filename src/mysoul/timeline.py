"""Permanent owner timeline. Original content and stable pagination have separate lifetimes."""

import json
from datetime import datetime

from pydantic import Field

from mysoul.domain import ActivityRecord, Contract, Scope


class TimelineItem(Contract):
    id: str
    seq: int
    revision: int
    change_seq: int
    kind: str
    source_id: str
    created_at: str
    scope: Scope = Field(default_factory=Scope)
    body: dict


class TimelinePage(Contract):
    items: list[TimelineItem]
    next_before: int | None
    has_more: bool
    change_cursor: int
    watermark: int


class TimelineStore:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def upsert_in(db, ident, kind, source_id, created_at, body):
        encoded = json.dumps(body, ensure_ascii=False, sort_keys=True)
        row = db.execute("SELECT seq,body FROM timeline WHERE id=?", (ident,)).fetchone()
        if row and row[1] == encoded:
            return
        if row:
            seq = row[0]
            db.execute("UPDATE timeline SET body=?,revision=revision+1 WHERE seq=?", (encoded, seq))
        else:
            seq = db.execute(
                "INSERT INTO timeline(id,kind,source_id,created_at,body) VALUES(?,?,?,?,?)",
                (ident, kind, source_id, created_at, encoded),
            ).lastrowid
        change = db.execute("INSERT INTO timeline_changes(item_seq) VALUES(?)", (seq,)).lastrowid
        db.execute("UPDATE timeline SET change_seq=? WHERE seq=?", (change, seq))

    @classmethod
    def event_in(cls, db, event):
        if event.scope != Scope() or event.trust != "owner_command":
            return
        if db.execute(
            "SELECT 1 FROM objects WHERE kind='interaction' AND id=?", (event.id,)
        ).fetchone():
            return
        cls.upsert_in(
            db,
            "chat:" + event.id,
            "chat",
            event.id,
            event.received_at.isoformat(),
            {
                "event_id": event.id,
                "input": event.content,
                "text": "",
                "pending": True,
                "choice": "owner_served",
            },
        )

    @classmethod
    def interaction_in(cls, db, event, result):
        if event.scope != Scope():
            return
        body = dict(result)
        body.setdefault("input", "" if event.source == "local-initiative" else event.content)
        body["pending"] = False
        cls.upsert_in(db, "chat:" + event.id, "chat", event.id, event.received_at.isoformat(), body)

    @classmethod
    def task_in(cls, db, goal, activity):
        context = db.execute(
            "SELECT body FROM objects WHERE kind='activity_context' AND id=?", (activity.id,)
        ).fetchone()
        if not context or json.loads(context[0]).get("scope") != Scope().model_dump():
            return
        from mysoul.domain import Evidence, ToolRequest, ToolResult

        effects = []
        for request_json, result_json in db.execute(
            "SELECT request,result FROM effects"
        ).fetchall():
            request = ToolRequest.model_validate_json(request_json)
            if request.activity_id != activity.id or request.scope != Scope():
                continue
            result = ToolResult.model_validate_json(result_json)
            if result.evidence_ref:
                evidence = db.execute(
                    "SELECT body FROM evidence WHERE id=?", (result.evidence_ref,)
                ).fetchone()
                if evidence and not Evidence.model_validate_json(evidence[0]).permitted(Scope()):
                    continue
            effects.append(
                {
                    "action_id": request.action_id,
                    "tool": request.tool,
                    "outcome": result.outcome,
                    "content": result.content,
                    "evidence_ref": result.evidence_ref,
                    "error": result.error,
                }
            )
        cls.upsert_in(
            db,
            "task:" + goal.id,
            "task",
            goal.id,
            goal.created_at.isoformat(),
            {
                "goal_id": goal.id,
                "activity_id": activity.id,
                "objective": goal.objective,
                "status": goal.status
                if goal.status in {"cancelled", "abandoned", "failed", "completed"}
                else activity.status,
                "result": activity.final_note,
                "cursor": activity.cursor,
                "effect_ids": activity.effect_ids,
                "effects": effects,
                "context_refs": activity.context_refs,
            },
        )

    def sync_task_in(self, db, goal_id):
        from mysoul.domain import Goal

        goal = db.execute(
            "SELECT body FROM objects WHERE kind='goal' AND id=?", (goal_id,)
        ).fetchone()
        if not goal:
            return
        rows = db.execute(
            "SELECT body FROM objects WHERE kind='activity' "
            "AND json_extract(body,'$.goal_id')=? ORDER BY rowid",
            (goal_id,),
        ).fetchall()
        if rows:
            self.task_in(
                db,
                Goal.model_validate_json(goal[0]),
                ActivityRecord.model_validate_json(rows[-1][0]),
            )

    def migrate(self):
        if self.store.get("timeline_migration", "v1") is not None:
            return
        with self.store.transaction() as db:
            entries = []
            for event in self.store.events():
                result = self.store.get("interaction", event.id)
                if result:
                    entries.append(
                        (event.received_at.isoformat(), "chat:" + event.id, event, result)
                    )
                elif event.trust == "owner_command":
                    entries.append((event.received_at.isoformat(), "chat:" + event.id, event, None))
            for goal in self.store.all("goal"):
                entries.append((goal["created_at"], "task:" + goal["id"], None, goal["id"]))
            for _, _, event, result in sorted(
                entries, key=lambda row: (datetime.fromisoformat(row[0]), row[1])
            ):
                if event is None:
                    self.sync_task_in(db, result)
                elif result is not None:
                    self.interaction_in(db, event, result)
                else:
                    self.event_in(db, event)
            db.execute("INSERT INTO objects VALUES('timeline_migration','v1','{}')")

    def page(self, *, before=None, after_change=0, limit=50):
        if not 1 <= limit <= 100 or (before is not None and before < 1) or after_change < 0:
            raise ValueError("Invalid timeline cursor or limit")
        if before is not None and after_change:
            raise ValueError("Use older paging or change polling separately")
        with self.store.lock:
            db = self.store.db
            watermark = db.execute("SELECT COALESCE(MAX(seq),0) FROM timeline").fetchone()[0]
            cursor = db.execute("SELECT COALESCE(MAX(seq),0) FROM timeline_changes").fetchone()[0]
            if after_change:
                rows = db.execute(
                    "SELECT * FROM timeline WHERE change_seq>? AND change_seq<=? "
                    "ORDER BY change_seq LIMIT ?",
                    (after_change, cursor, limit + 1),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM timeline WHERE seq<? ORDER BY seq DESC LIMIT ?",
                    (before or watermark + 1, limit + 1),
                ).fetchall()
            more = len(rows) > limit
            rows = rows[:limit]
            columns = [
                "seq",
                "id",
                "kind",
                "source_id",
                "created_at",
                "body",
                "revision",
                "change_seq",
            ]
            items = []
            for row in rows:
                data = dict(zip(columns, row, strict=True))
                data["body"] = json.loads(data["body"])
                items.append(TimelineItem.model_validate(data))
            change_cursor = (
                max((i.change_seq for i in items), default=after_change)
                if (after_change and more)
                else cursor
            )
            items.sort(key=lambda i: i.seq)
            return TimelinePage(
                items=items,
                next_before=items[0].seq if items else None,
                has_more=more,
                change_cursor=change_cursor,
                watermark=watermark,
            )
