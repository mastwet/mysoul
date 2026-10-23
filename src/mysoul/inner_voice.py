"""Short decision summaries and operational receipts; never raw model reasoning."""

import base64
import json
import re
from typing import Literal

from fastapi import Depends, HTTPException, Query

from mysoul.domain import Scope, now, uid

Category = Literal["all", "initiative", "conversation", "task", "maintenance", "schedule"]


def brief(value, limit=1000):
    text = str(value or "")
    text = re.sub(r"(?i)bearer\s+[a-z0-9._-]+|sk-[a-z0-9-]{12,}", "[已隐藏]", text)
    return text[:limit]


class VoiceJournal:
    def __init__(self, store):
        self.store = store

    def record_decision(self, events, decision, epoch):
        if not events or events[-1].scope != Scope():
            return
        event = events[-1]
        if event.source == "local-initiative" and not (
            decision.memory_call or decision.runtime_call
        ):
            return  # The initiative receipt already has the actual publication outcome.
        if event.source not in {"local-owner", "runtime", "local-initiative"}:
            return
        failure = getattr(decision, "failure", None)
        interrupted = self.store.load_subject().dispatch_epoch != epoch
        ident = uid()
        self.store.put(
            "decision_note",
            ident,
            {
                "id": ident,
                "created_at": now().isoformat(),
                "scope": Scope().model_dump(),
                "category": "conversation",
                "title": "日程安排决策"
                if decision.runtime_call
                else "记忆查阅决策"
                if decision.memory_call
                else "对话决策",
                "summary": brief(decision.rationale),
                "status": "interrupted" if interrupted else "error" if failure else "decided",
                "details": {
                    "epoch": epoch,
                    "activity": decision.activity,
                    "chat_action": decision.chat_action,
                    "event_id": event.id,
                    "tool": (decision.runtime_call or decision.memory_call).tool
                    if decision.runtime_call or decision.memory_call
                    else None,
                    "error_code": failure.code if failure else None,
                },
            },
        )

    def record_step(self, activity, decision, result, *, step=None):
        raw = self.store.get("activity_context", activity.id)
        if raw and raw.get("scope") != Scope().model_dump():
            return
        goal = self.store.goal(activity.goal_id)
        step = activity.cursor if step is None else step
        ident = f"step:{activity.id}:{step}"
        previous = self.store.get("decision_note", ident)
        self.store.put(
            "decision_note",
            ident,
            {
                "id": ident,
                "created_at": previous["created_at"] if previous else now().isoformat(),
                "scope": Scope().model_dump(),
                "category": "task",
                "title": "后台任务进度" if goal.lane == "background" else "前台任务进度",
                "summary": brief(decision.note, 600),
                "status": "failed"
                if result and result.get("outcome") != "confirmed"
                else "completed"
                if decision.done
                else "progress",
                "details": {
                    "goal_id": goal.id,
                    "activity_id": activity.id,
                    "step": step,
                    "epoch": activity.dispatch_epoch,
                    "tool": decision.tool,
                    "outcome": (result or {}).get("outcome"),
                },
            },
        )

    @staticmethod
    def cursor(stamp, key):
        return base64.urlsafe_b64encode(json.dumps([stamp, key]).encode()).decode().rstrip("=")

    def page(self, *, category="all", before=None, limit=30):
        if category not in {"all", "initiative", "conversation", "task", "maintenance", "schedule"}:
            raise ValueError("Unknown category")
        if not 1 <= limit <= 100:
            raise ValueError("Limit out of range")
        clauses, parameters = ["stamp IS NOT NULL"], []
        if category != "all":
            clauses.append("category=?")
            parameters.append(category)
        if before:
            try:
                stamp, key = json.loads(
                    base64.b64decode(
                        before + "=" * (-len(before) % 4), altchars=b"-_", validate=True
                    )
                )
                if not isinstance(stamp, str) or not isinstance(key, str) or len(key) > 200:
                    raise ValueError("Invalid cursor")
            except (ValueError, TypeError, UnicodeError):
                raise ValueError("Invalid cursor") from None
            clauses.append("(stamp<? OR (stamp=? AND key<?))")
            parameters.extend([stamp, stamp, key])
        query = (
            """
            SELECT * FROM (
              SELECT 'initiative' AS source,'initiative:'||id AS key, body,
                'initiative' AS category,
                strftime('%Y-%m-%dT%H:%M:%fZ',json_extract(body,'$.started_at')) AS stamp
              FROM objects WHERE kind='initiative_check'
              UNION ALL
              SELECT 'note','note:'||id,body,json_extract(body,'$.category'),
                strftime('%Y-%m-%dT%H:%M:%fZ',json_extract(body,'$.created_at'))
              FROM objects WHERE kind='decision_note'
                AND json_extract(body,'$.scope.audience')='owner'
                AND json_extract(body,'$.scope.conversation')='owner'
              UNION ALL
              SELECT 'schedule','schedule:'||id,body,'schedule',
                strftime('%Y-%m-%dT%H:%M:%fZ',json_extract(body,'$.created_at'))
              FROM objects WHERE kind='scheduled_wakeup'
              UNION ALL
              SELECT 'maintenance','maintenance:'||id,body,'maintenance',
                strftime('%Y-%m-%dT%H:%M:%fZ',json_extract(body,'$.created_at'))
              FROM objects WHERE kind='cognitive_run'
            ) WHERE """
            + " AND ".join(clauses)
            + " ORDER BY stamp DESC,key DESC LIMIT ?"
        )
        with self.store.lock:
            rows = self.store.db.execute(query, [*parameters, limit + 1]).fetchall()
        more = len(rows) > limit
        items = [self.project(row) for row in rows[:limit]]
        return {
            "items": items,
            "has_more": more,
            "next_before": self.cursor(rows[limit - 1][4], rows[limit - 1][1]) if more else None,
        }

    @staticmethod
    def project(row):
        source, key, encoded, category, stamp = row
        body = json.loads(encoded)
        if source == "initiative":
            title, summary, status = "自主检查", body.get("reason"), body.get("outcome", "waiting")
            details = {
                name: body.get(name)
                for name in (
                    "epoch",
                    "publication_status",
                    "background_goal_id",
                    "background_status",
                    "started_at",
                    "finished_at",
                )
            }
            error = body.get("error")
            if isinstance(error, dict):
                details["error_code"] = brief(error.get("code"), 80)
                details["error_message"] = brief(error.get("message"), 300)
        elif source == "schedule":
            title, summary, status = "唤醒安排", body.get("reason"), body.get("status")
            details = {
                name: body.get(name)
                for name in (
                    "due_at",
                    "triggered_at",
                    "finished_at",
                    "goal_id",
                    "epoch",
                    "outcome",
                )
            }
        elif source == "maintenance":
            title, status = "记忆整理", body.get("status", "queued")
            summary = {
                "completed": "本轮经历整理已完成。",
                "failed": "整理失败，等待重试。",
                "superseded": "新输入打断了本轮整理。",
            }.get(status, "正在整理近期经历。")
            details = {
                name: body.get(name) for name in ("stage", "epoch", "attempts", "next_attempt_at")
            }
            if body.get("error"):
                details["error_code"] = brief(str(body["error"]).split(":", 1)[0], 80)
        else:
            title, summary, status = (
                body.get("title", "决策记录"),
                body.get("summary"),
                body.get("status"),
            )
            safe = {
                "epoch",
                "activity",
                "chat_action",
                "event_id",
                "tool",
                "error_code",
                "goal_id",
                "activity_id",
                "step",
                "outcome",
            }
            details = {
                name: value for name, value in body.get("details", {}).items() if name in safe
            }
        return {
            "id": key,
            "time": stamp,
            "category": category,
            "title": brief(title, 80),
            "summary": brief(summary),
            "status": status,
            "details": {
                key: brief(value, 300) if isinstance(value, str) else value
                for key, value in details.items()
                if value is not None
            },
        }


def register_inner_voice_routes(app, authorize):
    @app.get("/api/inner-voice", dependencies=[Depends(authorize)])
    async def inner_voice(
        category: Category = "all",
        before: str | None = Query(default=None, max_length=400),
        limit: int = Query(default=30, ge=1, le=100),
    ):
        try:
            soul = app.state.soul
            pending = soul.wakeups.public_pending()
            result = VoiceJournal(soul.store).page(category=category, before=before, limit=limit)
            result["wakeup"] = {
                "pending": pending,
                "next_at": soul.store.load_subject().next_initiative_at,
                "enabled": soul.store.load_subject().autonomy_enabled,
            }
            return result
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
