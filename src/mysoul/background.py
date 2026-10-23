"""Read-only background goals advance cooperatively, one persisted step per wake."""

from mysoul.domain import BACKGROUND_TOOLS, TERMINAL, Goal


class BackgroundTasks:
    def __init__(self, soul):
        self.soul = soul

    def queue(self, request, epoch, key, *, owner_queue=False):
        soul = self.soul
        if soul.store.load_subject().dispatch_epoch != epoch:
            return None
        ident = "background:" + key
        old = soul.store.get("goal", ident)
        if old:
            return Goal.model_validate(old)
        # Only explicit owner requests may join the durable waiting queue.
        waiting = [
            item
            for item in soul.store.all("goal")
            if item.get("lane") == "background" and item["status"] not in TERMINAL
        ]
        if len(waiting) >= 8 or (waiting and not owner_queue):
            return None
        goal = Goal(
            id=ident,
            lane="background",
            objective=request.objective,
            completion_criteria=request.completion_criteria,
            allowed_tools=BACKGROUND_TOOLS,
            step_limit=8,
            time_limit=300,
            token_limit=None if soul.settings.token_budget is None else 8000,
        )
        soul.store.save_goal(goal)
        return goal

    async def advance(self, goal_id, epoch, continuation=None):
        soul = self.soul
        state = soul.store.load_subject()
        raw = soul.store.get("goal", goal_id)
        if (
            not raw
            or raw.get("lane") != "background"
            or state.dispatch_epoch != epoch
            or soul.owner_turns
            or not state.autonomy_enabled
            or state.mode != "normal"
        ):
            return "deferred"
        goal = Goal.model_validate(raw)
        if goal.status in TERMINAL or goal.cancelled:
            return goal.status
        if continuation == "abandon" and goal.status == "pending":
            goal.status = "abandoned"
            soul.store.save_goal(goal)
            return "abandoned"
        if continuation != "abandon":
            waiting = [
                item
                for item in soul.store.all("goal")
                if item.get("lane") == "background" and item["status"] not in TERMINAL
            ]
            current = next(
                (item for item in waiting if item["status"] != "pending"),
                waiting[0] if waiting else None,
            )
            if current and current["id"] != goal.id:
                return "queued"
        if goal.status == "pending":
            activity = await soul.start_goal(goal, expected_epoch=epoch)
        elif goal.status == "suspended":
            activities = [a for a in soul.store.all("activity") if a["goal_id"] == goal_id]
            if not activities:
                return "deferred"
            latest = activities[-1]
            if continuation == "abandon":
                activity = await soul.executor.resume(latest["id"], "abandon")
            else:
                if latest.get("pause_reason") not in {"yield", "owner", "restart"} or any(
                    result.outcome != "confirmed"
                    for _, result in soul.store.effects_for_goal(goal_id)
                ):
                    return "blocked"
                activity = await soul.executor.resume(latest["id"], "continue")
        else:
            return "deferred"
        return activity.pause_reason or activity.status

    def mark_shared(self, goal_id, event_id):
        raw = self.soul.store.get("goal", goal_id) if goal_id else None
        if raw and raw.get("lane") == "background" and raw["status"] == "completed":
            self.soul.store.put_new("background_publication", goal_id, {"event_id": event_id})
