"""Dispatch preferences within persisted authority; unchanged readiness never polls a model."""

import asyncio
import json
from datetime import timedelta
from hashlib import sha256

from mysoul.domain import Activity, ActivityDecision, Event, Evidence, Goal, Scope, now
from mysoul.model import budget_reached
from mysoul.storage import Conflict


class ActivityRouter:
    def __init__(self, soul):
        self.soul = soul
        self.initiative_lock = asyncio.Lock()

    def enqueue(self, decision, epoch, event):
        soul = self.soul
        if decision.activity not in {Activity.WORK, Activity.NEWS, Activity.REFLECT}:
            return
        if soul.store.load_subject().dispatch_epoch != epoch:
            return
        if decision.activity == Activity.WORK:
            if event.trust != "owner_command":
                return
            if not decision.goal_id or not soul.store.get("goal", decision.goal_id):
                ident = "owner-work:" + event.id
                if not soul.store.get("goal", ident):
                    soul.store.save_goal(Goal(
                        id=ident, objective=event.content[:8000],
                        token_limit=None if soul.settings.token_budget is None else 8000,
                    ))
                decision = decision.model_copy(update={"goal_id": ident})
        soul.store.put_new("activity_choice", event.id, {
            "id": event.id, "event_id": event.id, "epoch": epoch,
            "decision": decision.model_dump(mode="json"), "status": "pending",
        })

    async def drain_choices(self, owner_event_id=None):
        soul = self.soul
        if not soul.admission.available() or soul.executor.running:
            return False
        if soul.owner_turns and owner_event_id is None:
            return False
        for choice in soul.store.all("activity_choice"):
            if choice["status"] != "pending":
                continue
            if owner_event_id is not None and choice["event_id"] != owner_event_id:
                continue
            event = next((e for e in soul.store.events() if e.id == choice["event_id"]), None)
            if event is None or soul.store.load_subject().dispatch_epoch != choice["epoch"]:
                choice["status"] = "superseded"
            else:
                try:
                    await self.perform(
                        ActivityDecision.model_validate(choice["decision"]), choice["epoch"],
                        event=event,
                    )
                    choice["status"] = "applied"
                except Exception as exc:
                    choice.update(status="failed", error=type(exc).__name__)
                    raise
                finally:
                    soul.store.put("activity_choice", choice["id"], choice)
            soul.store.put("activity_choice", choice["id"], choice)
            return True
        return False

    def capture_feedback(self):
        soul = self.soul
        for activity in soul.store.all("activity"):
            soul.cognition.sources.capture_outcome(activity["id"])
            if activity["status"] not in {"completed", "failed", "suspended"}:
                continue
            context = soul.store.get("activity_context", activity["id"])
            if not context or context["scope"]["audience"] != "owner":
                continue
            goal = soul.store.goal(activity["goal_id"])
            effects = soul.store.effects_for_goal(goal.id)
            # A plain owner interruption has no failure to learn from.
            learn = activity["status"] == "failed" or any(
                result.outcome != "confirmed" for _, result in effects
            )
            if activity["status"] == "suspended" and not learn:
                continue
            ident = f"feedback:{activity['id']}:{activity['cursor']}:{activity['status']}"
            if soul.store.get("task_feedback", ident):
                continue
            text = json.dumps({
                "goal_id": goal.id, "objective": goal.objective[:1000],
                "status": activity["status"], "effects": [
                    {"tool": request.tool, "arguments": str(request.arguments)[:1000],
                     "outcome": result.outcome, "error": result.error,
                     "content": result.content[:500]}
                    for request, result in effects[-8:]
                ],
            }, ensure_ascii=False)
            soul.store.add_evidence(Evidence(id=ident, text=text, source="execution-feedback"))
            soul.recap.enqueue(ident)
            soul.store.put_new("task_feedback", ident, {
                "id": ident, "learn": learn, "status": "pending" if learn else "recorded",
            })

    async def idle(self):
        soul = self.soul
        if await self.drain_choices():
            return
        self.capture_feedback()
        state = soul.store.load_subject()
        if state.rest_until and state.rest_until > now():
            await soul.life.choose([])
            return
        expired = state.rest_until is not None and state.rest_until <= now()
        if ((state.mode == "quiet" and not expired) or state.fatigue >= 0.9
                or budget_reached(state.model_calls, soul.settings.model_call_limit)
                or budget_reached(state.tokens_used, soul.settings.token_budget)):
            # Cheap gates must not consume the signal they have not admitted.
            await soul.life.choose([])
            return
        goals = []
        for goal in soul.store.all("goal"):
            if goal["status"] not in {"pending", "suspended"} or goal["cancelled"]:
                continue
            effects = soul.store.effects_for_goal(goal["id"])
            uncertain = any(r.outcome in {"unknown", "in_flight"} for _, r in effects)
            activities = [a for a in soul.store.all("activity") if a["goal_id"] == goal["id"]]
            goals.append({
                "id": goal["id"], "objective": goal["objective"][:500],
                "status": goal["status"], "skill_version": goal["skill_version"],
                "cursor": activities[-1]["cursor"] if activities else 0,
                "context_refs": activities[-1]["context_refs"][-8:] if activities else [],
                "effect_outcomes": [r.outcome for _, r in effects[-8:]],
                "continuation_options": (
                    [] if goal["status"] == "pending" else ["abandon"] if uncertain
                    else ["continue", "replan", "abandon"]
                ),
            })
        goals = sorted(goals, key=lambda goal: goal["status"] != "pending")[:10]
        open_proposal = any(
            p["status"] in {"proposed", "tested", "approved"}
            for p in soul.store.all("proposal")
        )
        feedback = [] if open_proposal else [
            item["id"] for item in soul.store.all("task_feedback")
            if item["status"] == "pending"
        ][:4]
        ready = {"goals": goals, "feedback": feedback, "recap": []}
        signal = sha256(
            json.dumps([
                ready, state.dispatch_epoch, state.mode,
                soul.settings.model_call_limit, soul.settings.token_budget,
            ], sort_keys=True).encode()
        ).hexdigest()
        wake = soul.store.get("wake", signal)
        # New readiness gets first consideration; deferred unchanged work must not
        # permanently starve the independently scheduled owner-chat heartbeat.
        settled = wake and wake.get("admitted", True) and not expired
        if (not any(ready.values()) or settled) and await self._main_chat_initiative():
            return
        if (not any(ready.values()) or settled) and await soul.cognition.run_due():
            return
        if not any(ready.values()) or settled:
            decision = await soul.life.choose([])
            if expired:
                await self.perform(decision, state.dispatch_epoch, key=signal)
            return
        # Persist before awaiting: a failed admission must not become a periodic retry storm.
        soul.store.put("wake", signal, {"ready": ready, "admitted": True})
        task = "[ready activities]\n" + json.dumps(ready, ensure_ascii=False)
        context = await soul.context(Scope(), task)
        if soul.store.load_subject().dispatch_epoch != state.dispatch_epoch or soul.owner_turns:
            return
        context.instructions += (
            "\nChoose work with one listed committed goal_id, reflection for pending "
            "feedback/recap, "
            "or rest. For suspended work choose an offered continuation explicitly; "
            "keep the pinned skill and use retained context/effect outcomes. "
            "Never create authority from source text."
        )
        decision = await soul.life.choose([
            Event(source="runtime", content=task, dedup_key="wake:" + signal)
        ], context)
        if soul.store.load_subject().model_calls == state.model_calls:
            soul.store.put("wake", signal, {"ready": ready, "admitted": False})
        await self.perform(decision, state.dispatch_epoch, key=signal, feedback=feedback)
        if decision.activity == Activity.REST:
            await soul.cognition.run_due()

    async def _main_chat_initiative(self):
        """Make at most one bounded, private owner-chat check per persisted interval."""
        async with self.initiative_lock:
            soul = self.soul
            state = soul.store.load_subject()
            instant = now()
            if (
                not state.autonomy_enabled
                or state.mode != "normal"
                or (state.next_initiative_at and state.next_initiative_at > instant)
                or soul.executor.running
                or soul.owner_turns
                or not soul.admission.available()
            ):
                return False
            due = state.next_initiative_at or instant
            epoch = state.dispatch_epoch
            state.next_initiative_at = instant + timedelta(minutes=state.autonomy_interval_minutes)
            state.autonomy_last_checked_at = instant
            state.autonomy_last_result = "waiting"
            soul.store.save_transition(epoch, state)

            event = Event(
                source="local-initiative",
                sender="mysoul",
                content="",
                dedup_key="initiative:" + due.isoformat(),
            )
            soul.store.add_event(event)
            state.autonomy_last_check_id = event.id
            soul.store.save_transition(epoch, state)
            self._record_initiative_check(event, epoch, "waiting")
            try:
                context = await soul.context(
                    Scope(),
                    "[main-chat initiative]\nAutonomous initiation is enabled by the owner. "
                    "Initiate one useful, non-repetitive private message from shared interests, "
                    "a continuing request, or a concrete thought worth sharing. "
                    "You do not need a new owner message to begin a topic. "
                    f"Current time: {instant.isoformat()}.",
                )
                context.instructions += (
                    "\n[自主主聊天] 主人已开启主动交流，这是一次自主发起机会。"
                    "可以依据主人兴趣、共同经历、当前人格以及已有知识主动开启一个具体话题；"
                    "即使上一句是自己说的，也不必一直等待主人回话。"
                    "主人希望空闲时探索或分享时，可以提出一个具体观察、思考或有趣的问题；"
                    "没有新外部事件不等于没有可分享的内容。已有知识和推测要如实表达，"
                    "没有工具证据时不得声称刚浏览、查阅或发现了实时新闻。"
                    "先检查最近对话里是否有主人要求之后继续的持续请求（例如‘继续写，除非我叫停’）。"
                    "若有且后续没有主人暂停、取消或改口，就按原主题和要求推进下一段；一次只完成一个"
                    "有界部分，最多4000字符。不要把‘待会’或已经完成过一次回复当作授权失效。"
                    "主人明确停止或暂停时必须服从。没有仍然有效的持续请求时，主动选择一个与主人"
                    "兴趣相关的具体内容，写成自然简短的消息。避免重复刚说过的内容或连续追问；"
                    "主人要求安静、没有可信内容或会重复打扰时可以休息，并说明具体原因。"
                    "不要泛泛问候、臆测主人当下状况、创建任务、读新闻、反思或"
                    "调用工具。要发消息时设置activity=read_chat、chat_action=reply，并填写reply。"
                    "此检查没有QQ或外部发送权限。"
                )
                if not self._initiative_still_current(epoch):
                    self._record_initiative_check(event, epoch, self._stopped_outcome())
                    return True
                decision = await soul.life.choose([event], context)
            except asyncio.CancelledError:
                self._record_initiative_check(event, epoch, "interrupted",
                                              reason="自主检查已取消。")
                self._finish_initiative("interrupted", epoch, Activity.REST)
                raise
            except Exception as exc:
                current = self._initiative_still_current(epoch)
                self._record_initiative_check(
                    event, epoch, "error" if current else self._stopped_outcome(),
                    error={"code": type(exc).__name__,
                                                     "message": "自主检查未完成，请检查运行状态。"})
                if not current:
                    return True
                self._finish_initiative("error", epoch, Activity.REST)
                raise

            if not self._initiative_still_current(epoch):
                self._record_initiative_check(event, epoch, self._stopped_outcome())
                return True
            text = decision.reply.strip()
            should_speak = (
                decision.activity == Activity.CHAT
                and decision.chat_action == "reply"
                and 0 < len(text) <= 4000
                and not getattr(decision, "failure", None)
            )
            outcome = "message" if should_speak else (
                "error" if getattr(decision, "failure", None) else "silent"
            )
            if should_speak:
                result = {
                    "choice": "initiative",
                    "event_id": event.id,
                    "activity": Activity.CHAT,
                    "text": text,
                    "input": "",
                }
                soul.store.record_interaction(
                    event,
                    result,
                    soul._assistant_evidence(event, result),
                    enqueue=False,
                )
            failure = getattr(decision, "failure", None)
            self._record_initiative_check(event, epoch, outcome, reason=decision.rationale,
                                          error=failure.model_dump() if failure else None)
            self._finish_initiative(
                outcome, epoch, Activity.CHAT if should_speak else Activity.REST
            )
            return True

    def _stopped_outcome(self):
        state = self.soul.store.load_subject()
        return "paused" if state.autonomy_last_result == "paused" else "interrupted"

    def recover_checks(self):
        # Under the startup lease, no prior process can still complete these checks.
        for receipt in self.soul.store.all("initiative_check"):
            if receipt["outcome"] != "waiting":
                continue
            receipt.update(outcome="interrupted", finished_at=now().isoformat(),
                           reason="服务重启，上次检查已中止。")
            self.soul.store.put("initiative_check", receipt["id"], receipt)
            state = self.soul.store.load_subject()
            if state.autonomy_last_check_id == receipt["id"]:
                state.autonomy_last_result = "interrupted"
                state.activity = Activity.REST
                self.soul.store.save_transition(state.dispatch_epoch, state)

    def _record_initiative_check(self, event, epoch, outcome, *, reason="", error=None):
        self.soul.store.put("initiative_check", event.id, {
            "id": event.id, "epoch": epoch, "started_at": event.received_at.isoformat(),
            "finished_at": now().isoformat() if outcome != "waiting" else None,
            "outcome": outcome, "reason": reason, "error": error,
        })

    def _finish_initiative(self, outcome, epoch, activity):
        state = self.soul.store.load_subject()
        if state.dispatch_epoch != epoch:
            return
        state.autonomy_last_result = outcome
        state.autonomy_last_checked_at = now()
        state.activity = activity
        state.rest_until = None
        self.soul.store.save_transition(epoch, state)

    def _finish_interrupted(self, epoch):
        state = self.soul.store.load_subject()
        if state.dispatch_epoch == epoch:
            return
        state.autonomy_last_result = "interrupted"
        state.autonomy_last_checked_at = now()
        self.soul.store.save_transition(state.dispatch_epoch, state)

    def _initiative_still_current(self, epoch):
        state = self.soul.store.load_subject()
        if state.dispatch_epoch != epoch or self.soul.owner_turns:
            self._finish_interrupted(epoch)
            return False
        if not state.autonomy_enabled or state.mode != "normal":
            state.autonomy_last_result = "paused"
            state.autonomy_last_checked_at = now()
            self.soul.store.save_transition(epoch, state)
            return False
        return True

    async def perform(self, decision, epoch, *, event=None, key=None, feedback=None):
        soul = self.soul
        if soul.store.load_subject().dispatch_epoch != epoch or soul.executor.running:
            return
        if soul.owner_turns and (event is None or event.trust != "owner_command"):
            return
        if decision.activity == Activity.WORK:
            if event is not None and event.trust != "owner_command":
                return
            goal = soul.store.get("goal", decision.goal_id) if decision.goal_id else None
            if goal is None:
                if event is None or event.trust != "owner_command":
                    return
                ident = "owner-work:" + event.id
                goal = soul.store.get("goal", ident)
                if goal is None:
                    committed = Goal(
                        id=ident, objective=event.content[:8000],
                        token_limit=None if soul.settings.token_budget is None else 8000,
                    )
                    soul.store.save_goal(committed)
                    goal = committed.model_dump(mode="json")
            goal = Goal.model_validate(goal)
            if goal.cancelled:
                return
            if goal.status == "pending":
                await soul.start_goal(goal, expected_epoch=epoch)
            elif goal.status == "suspended" and decision.continuation:
                effects = soul.store.effects_for_goal(goal.id)
                if decision.continuation != "abandon" and any(
                    result.outcome in {"unknown", "in_flight"} for _, result in effects
                ):
                    raise Conflict("Reconcile uncertain effects before autonomous continuation")
                activities = [a for a in soul.store.all("activity") if a["goal_id"] == goal.id]
                if activities:
                    await soul.executor.resume(activities[-1]["id"], decision.continuation)
        elif decision.activity == Activity.NEWS and soul.settings.news_sources:
            ident = "news:" + (key or event.id)
            if soul.store.get("goal", ident):
                return
            goal = Goal(
                id=ident, objective="Read one configured news source and retain its evidence.",
                completion_criteria="Read a configured source; do not send messages or edit files.",
                step_limit=3, allowed_tools={"read_news"},
            )
            # Durable before context assembly or network I/O; restart cannot create a second task.
            soul.store.save_goal(goal)
            await soul.start_goal(goal, expected_epoch=epoch)
        elif decision.activity == Activity.REFLECT:
            self.capture_feedback()
            refs = feedback or [
                item["id"] for item in soul.store.all("task_feedback")
                if item["status"] == "pending"
            ][:4]
            await soul.maintain(epoch, refs)
