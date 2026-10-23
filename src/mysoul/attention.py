"""Bounded runtime receipts, derived from canonical state; never a memory source."""

import json
import unicodedata

from mysoul.domain import Scope


class AttentionLedger:
    def __init__(self, store):
        self.store = store

    def _rows(self, owner_inputs=False, limit=8):
        where = "AND json_extract(e.body,'$.source')='local-owner'" if owner_inputs else ""
        with self.store.lock:
            rows = self.store.db.execute(
                "SELECT i.body,e.body FROM objects i JOIN events e ON e.id=i.id "
                "WHERE i.kind='interaction' AND json_extract(e.body,'$.scope.audience')='owner' "
                "AND json_extract(e.body,'$.scope.conversation')='owner' "
                + where
                + " ORDER BY e.rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [(json.loads(i), json.loads(e)) for i, e in reversed(rows)]

    @staticmethod
    def _published(result):
        return (
            not result.get("error")
            and result.get("text")
            and result.get("choice") in {"owner_served", "initiative", "sent"}
            and result["text"]
            not in {"Model unavailable", "Rest or runtime limit", "Context budget exhausted"}
            and not result["text"].startswith("Replay:")
        )

    def snapshot(self, scope):
        if scope != Scope():
            return {}
        handled = []
        for result, event in self._rows(owner_inputs=True, limit=6):
            handled.append(
                {
                    "event_id": event["id"],
                    "time": event["received_at"],
                    "input": event["content"][:400],
                    "status": "replied"
                    if self._published(result)
                    else "failed"
                    if result.get("error")
                    else "unanswered",
                }
            )
        publications = [
            {
                "event_id": event["id"],
                "time": event["received_at"],
                "kind": result["choice"],
                "text": result["text"][:600],
                "truncated": len(result["text"]) > 600,
            }
            for result, event in self._rows(limit=16)
            if self._published(result)
        ][-8:]
        return {
            "handled_inputs": handled,
            "recent_publications": publications,
            "background_tasks": self.background_tasks(),
            "truncated": False,
        }

    def background_tasks(self):
        with self.store.lock:
            rows = self.store.db.execute(
                "SELECT body FROM objects WHERE kind='goal' "
                "AND json_extract(body,'$.lane')='background' "
                "ORDER BY CASE json_extract(body,'$.status') "
                "WHEN 'active' THEN 0 WHEN 'suspended' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END, "
                "CASE WHEN json_extract(body,'$.status') IN ('active','suspended','pending') "
                "THEN rowid ELSE -rowid END LIMIT 4"
            ).fetchall()
            tasks = []
            for row in rows:
                goal = json.loads(row[0])
                activity_row = self.store.db.execute(
                    "SELECT body FROM objects WHERE kind='activity' "
                    "AND json_extract(body,'$.goal_id')=? ORDER BY rowid DESC LIMIT 1",
                    (goal["id"],),
                ).fetchone()
                activity = json.loads(activity_row[0]) if activity_row else {}
                tasks.append(
                    {
                        "id": goal["id"],
                        "objective": goal["objective"][:500],
                        "status": goal["status"],
                        "cursor": activity.get("cursor", 0),
                        "pause_reason": activity.get("pause_reason", ""),
                        "progress": activity.get("progress_note", "")[:600],
                        "result": activity.get("final_note", "")[:1200],
                        "shared": self.store.get("background_publication", goal["id"]) is not None,
                    }
                )
        return tasks

    def attach(self, context, budget):
        attention = self.snapshot(context.scope)
        if not attention:
            return
        context.runtime_state["attention"] = attention
        self.fit(context, budget)

    @staticmethod
    def fit(context, budget):
        attention = context.runtime_state.get("attention")
        if not attention:
            while len(context.payload()) > budget and context.runtime_state.get("background_tasks"):
                context.runtime_state["background_tasks"].pop(0)
            return
        while len(context.payload()) > budget:
            attention["truncated"] = True
            tasks = attention.get("background_tasks", [])
            publications = attention["recent_publications"]
            inputs = attention["handled_inputs"]
            if len(tasks) > 1:
                # Keep the current task; discard older terminal reports before receipts.
                terminal = [
                    i
                    for i, task in enumerate(tasks)
                    if task["status"] in {"completed", "failed", "cancelled", "abandoned"}
                ]
                tasks.pop(terminal[-1] if terminal else -1)
            elif len(publications) > 1:
                publications.pop(0)
            elif len(inputs) > 1:
                inputs.pop(0)
            elif tasks and any(
                len(tasks[0][key]) > 160 for key in ("result", "progress", "objective")
            ):
                for key in ("result", "progress", "objective"):
                    tasks[0][key] = tasks[0][key][:160]
            elif tasks:
                tasks.pop()
            elif publications and len(publications[0]["text"]) > 160:
                publications[0]["text"] = publications[0]["text"][:160]
                publications[0]["truncated"] = True
            elif inputs and len(inputs[0]["input"]) > 160:
                inputs[0]["input"] = inputs[0]["input"][:160]
            elif inputs:
                inputs.pop()
            elif publications:
                publications.pop()
            else:
                del context.runtime_state["attention"]
                break

    def is_duplicate(self, text):
        def normalize(value):
            return "".join(unicodedata.normalize("NFKC", value).split())

        key = normalize(text)
        return bool(key) and any(
            self._published(result) and normalize(result["text"]) == key
            for result, _ in self._rows(limit=16)
        )
