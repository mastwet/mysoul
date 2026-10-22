"""Finite LangGraph steps with durable application-level effect reconciliation."""

import asyncio
from datetime import timedelta
from time import monotonic
from typing import TypedDict

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph

from mysoul.config import Settings
from mysoul.domain import (
    TERMINAL,
    Activity,
    ActivityRecord,
    ContextBundle,
    Event,
    Goal,
    ModelLimits,
    StepDecision,
    ToolRequest,
    now,
)
from mysoul.laputa import ContextOverflow, refresh_recap_context
from mysoul.life import advance_fatigue
from mysoul.model import reservation
from mysoul.storage import Conflict


class GraphState(TypedDict, total=False):
    activity_id: str
    cursor: int
    context: dict
    limits: dict
    decision: dict
    result: dict | None


class Executor:
    def __init__(self, store, model, dispatcher, checkpoint_path, settings: Settings, clock=now):
        self.store, self.model, self.dispatcher = store, model, dispatcher
        self.path, self.settings, self.clock = checkpoint_path, settings, clock
        self.running: str | None = None
        self.graph = None

    async def open(self):
        self.store.recover_effects()
        for item in self.store.all("activity"):
            record = ActivityRecord.model_validate(item)
            if record.status == "active":
                record.status = "suspended"
                self.store.save_activity(record)
                goal = self.store.goal(record.goal_id)
                if goal.status not in TERMINAL:
                    goal.status = "suspended"
                    self.store.save_goal(goal)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._saver_cm = AsyncSqliteSaver.from_conn_string(str(self.path))
        self.saver = await self._saver_cm.__aenter__()
        builder = StateGraph(GraphState)
        builder.add_node("prepare", self._prepare)
        builder.add_node("dispatch", self._dispatch)
        builder.add_edge(START, "prepare")
        builder.add_edge("prepare", "dispatch")
        builder.add_edge("dispatch", END)
        self.graph = builder.compile(checkpointer=self.saver, interrupt_before=["dispatch"])

    async def close(self):
        await self._saver_cm.__aexit__(None, None, None)

    async def _prepare(self, state: GraphState):
        limits = ModelLimits.model_validate(state["limits"])
        context = ContextBundle.model_validate(state["context"])
        current = refresh_recap_context(self.store, context.model_copy(deep=True))
        if current.payload() != context.payload():
            raise Conflict("Recap changed during model admission; resume with refreshed context")
        goal = self.store.goal(self.store.activity(state["activity_id"]).goal_id)
        specs = self.dispatcher.tool_specs(context.scope.audience)
        if goal.allowed_tools is not None:
            specs = [spec for spec in specs if spec["name"] in goal.allowed_tools]
        decision = await asyncio.wait_for(
            self.model.execute_step(
                context,
                specs,
                limits,
            ),
            limits.timeout,
        )
        return {"decision": decision.model_dump(), "result": None}

    async def _dispatch(self, state: GraphState):
        decision = StepDecision.model_validate(state["decision"])
        if not decision.tool or decision.done:
            return {"result": None}
        activity = self.store.activity(state["activity_id"])
        goal = self.store.goal(activity.goal_id)
        request = ToolRequest(
            action_id=f"{activity.id}:{state['cursor']}",
            activity_id=activity.id,
            goal_id=goal.id,
            epoch=activity.dispatch_epoch,
            tool=decision.tool,
            arguments=decision.arguments,
            scope=ContextBundle.model_validate(state["context"]).scope,
            deadline=self.clock()
            + timedelta(seconds=min(30, goal.time_limit - goal.elapsed_seconds)),
        )
        result = await self.dispatcher.dispatch(request)
        return {"result": result.model_dump(mode="json")}

    async def start(
        self, goal: Goal, context: ContextBundle | None = None, *, expected_epoch=None
    ) -> ActivityRecord:
        if self.running:
            raise Conflict("One foreground goal at a time")
        if goal.status in TERMINAL:
            raise Conflict("Cannot start terminal goal")
        state = self.store.load_subject()
        if expected_epoch is not None and state.dispatch_epoch != expected_epoch:
            raise Conflict("Operation was interrupted during context preparation")
        advance_fatigue(state, self.settings, self.clock())
        state.activity = Activity.WORK
        goal.status = "active"
        self.store.save_goal(goal)
        activity = ActivityRecord(
            goal_id=goal.id,
            status="active",
            dispatch_epoch=state.dispatch_epoch,
            skill_version=goal.skill_version,
        )
        self.store.save_activity(activity)
        state.current_activity_id = activity.id
        self.store.save_transition(state.dispatch_epoch, state)
        context = context or ContextBundle(task=goal.objective)
        self.store.put("activity_context", activity.id, context.model_dump(mode="json"))
        return await self._run(activity.id)

    async def _run(self, activity_id):
        self.running = activity_id
        started = monotonic()
        try:
            while True:
                activity = self.store.activity(activity_id)
                goal = self.store.goal(activity.goal_id)
                if goal.status in TERMINAL or activity.status != "active":
                    return activity
                if (
                    activity.cursor >= goal.step_limit
                    or goal.elapsed_seconds >= goal.time_limit
                    or goal.tokens_used >= goal.token_limit
                ):
                    return self._finish(activity, "failed")
                config = {"configurable": {"thread_id": activity.id}}
                snapshot = await self.graph.aget_state(config)
                if not (snapshot.next and snapshot.values.get("cursor") == activity.cursor):
                    state = self.store.load_subject()
                    latest = self.store.activity(activity.id)
                    if latest.status != "active" or latest.dispatch_epoch != state.dispatch_epoch:
                        return latest
                    limits = ModelLimits(
                        max_tokens=min(1024, goal.token_limit - goal.tokens_used),
                        timeout=min(30, goal.time_limit - goal.elapsed_seconds),
                    )
                    context = ContextBundle.model_validate(
                        self.store.get("activity_context", activity.id)
                    )
                    refresh_recap_context(self.store, context)
                    if len(context.payload()) > 16000:
                        raise ContextOverflow("Refreshed required context exceeds budget")
                    self.store.put("activity_context", activity.id, context.model_dump(mode="json"))
                    reserve, attempts = reservation(
                        self.model,
                        context,
                        limits,
                        self.dispatcher.tool_specs(context.scope.audience),
                    )
                    if (
                        state.model_calls + attempts > self.settings.model_call_limit
                        or state.tokens_used + reserve > self.settings.token_budget
                        or goal.tokens_used + reserve > goal.token_limit
                    ):
                        return self._finish(activity, "suspended")
                    state.model_calls += attempts
                    state.tokens_used += reserve
                    self.store.save_transition(state.dispatch_epoch, state)
                    goal.tokens_used += reserve
                    self.store.save_goal(goal)
                    await self.graph.ainvoke(
                        {
                            "activity_id": activity.id,
                            "cursor": activity.cursor,
                            "context": self.store.get("activity_context", activity.id),
                            "limits": limits.model_dump(),
                            "result": None,
                        },
                        config,
                    )
                latest = self.store.activity(activity.id)
                goal = self.store.goal(activity.goal_id)
                goal.elapsed_seconds += monotonic() - started
                started = monotonic()
                self.store.save_goal(goal)
                if (
                    latest.status != "active"
                    or self.store.load_subject().dispatch_epoch != latest.dispatch_epoch
                ):
                    return latest
                if goal.elapsed_seconds >= goal.time_limit:
                    return self._finish(latest, "failed")
                output = await self.graph.ainvoke(None, config)
                latest = self.store.activity(activity.id)
                goal = self.store.goal(activity.goal_id)
                goal.elapsed_seconds += monotonic() - started
                started = monotonic()
                self.store.save_goal(goal)
                result = output.get("result")
                if result:
                    if result["action_id"] not in latest.effect_ids:
                        latest.effect_ids.append(result["action_id"])
                    if result["outcome"] != "confirmed":
                        self.store.save_activity(latest)
                        return self._finish(latest, "suspended")
                    from mysoul.domain import Evidence

                    context = ContextBundle.model_validate(
                        self.store.get("activity_context", activity.id)
                    )
                    evidence = Evidence(
                        text=result.get("content", ""),
                        scope=context.scope,
                        source=f"tool:{result['action_id']}",
                    )
                    self.store.add_evidence(evidence)
                    latest.context_refs.append(evidence.id)
                    context.step_results.append(evidence)
                    if len(context.payload()) > 16000:
                        self.store.save_activity(latest)
                        return self._finish(latest, "suspended")
                    self.store.put("activity_context", activity.id, context.model_dump(mode="json"))
                latest.cursor += 1
                latest.checkpoint_ref = activity.id
                self.store.save_activity(latest)
                if latest.status != "active" or goal.status in TERMINAL:
                    return latest
                if output["decision"]["done"]:
                    return self._finish(latest, "completed")
        except asyncio.CancelledError:
            self._finish(self.store.activity(activity_id), "suspended")
            raise
        except (Conflict, ContextOverflow):
            self._finish(self.store.activity(activity_id), "suspended")
            raise
        except Exception:
            self._finish(self.store.activity(activity_id), "failed")
            raise
        finally:
            goal = self.store.goal(self.store.activity(activity_id).goal_id)
            goal.elapsed_seconds += max(0, monotonic() - started)
            self.store.save_goal(goal)
            self.running = None

    def _finish(self, activity, status):
        goal = self.store.goal(activity.goal_id)
        if goal.status in TERMINAL:
            status = goal.status
        activity.status = status
        goal.status = status
        self.store.save_goal(goal)
        self.store.save_activity(activity)
        state = self.store.load_subject()
        if state.current_activity_id == activity.id:
            advance_fatigue(state, self.settings, self.clock())
            state.activity = Activity.REST
            if status in TERMINAL:
                state.current_activity_id = None
            self.store.save_transition(state.dispatch_epoch, state)
        return activity

    async def interrupt(self, owner_event: Event):
        if owner_event.trust != "owner_command":
            raise PermissionError("Authenticated owner command required")
        state = self.store.interrupt()
        if state.current_activity_id:
            activity = self.store.activity(state.current_activity_id)
            if activity.status not in TERMINAL:
                return self._finish(activity, "suspended")
        return None

    def cancel(self, goal_id):
        goal = self.store.goal(goal_id)
        if goal.status in TERMINAL:
            raise Conflict("Goal already terminal")
        goal.cancelled = True
        goal.status = "cancelled"
        self.store.save_goal(goal)
        for row in self.store.all("activity"):
            if row["goal_id"] == goal_id:
                self._finish(ActivityRecord.model_validate(row), "cancelled")

    async def resume(self, activity_id, decision):
        if self.running:
            raise Conflict("Wait for in-flight work to settle before resuming")
        activity = self.store.activity(activity_id)
        goal = self.store.goal(activity.goal_id)
        if goal.status in TERMINAL or activity.status != "suspended":
            raise Conflict("Only suspended, non-terminal work may resume")
        if decision not in {"continue", "replan", "abandon"}:
            raise ValueError("Invalid continuation decision")
        activity.continuation = decision
        if decision == "abandon":
            return self._finish(activity, "abandoned")
        if decision == "replan":
            activity.id = __import__("uuid").uuid4().hex
            activity.cursor = 0
            # New execution thread; old evidence and activity history remain retained.
            self.store.put(
                "activity_context", activity.id, self.store.get("activity_context", activity_id)
            )
        state = self.store.load_subject()
        activity.dispatch_epoch = state.dispatch_epoch
        activity.status = goal.status = "active"
        self.store.save_goal(goal)
        self.store.save_activity(activity)
        state.current_activity_id = activity.id
        advance_fatigue(state, self.settings, self.clock())
        state.activity = Activity.WORK
        self.store.save_transition(state.dispatch_epoch, state)
        return await self._run(activity.id)
