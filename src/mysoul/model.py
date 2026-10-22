from collections import deque
from typing import Protocol

from mysoul.domain import Activity, ActivityDecision, ContextBundle, ModelLimits, StepDecision


class ModelAdapter(Protocol):
    async def decide(self, context: ContextBundle, limits: ModelLimits) -> ActivityDecision: ...

    async def execute_step(
        self, context: ContextBundle, tool_specs: list[dict], limits: ModelLimits
    ) -> StepDecision: ...


def reservation(model, context, limits, tool_specs=None):
    estimate = getattr(model, "reservation", None)
    tokens = (
        estimate(context, limits, tool_specs)
        if estimate
        else limits.max_tokens * (limits.retries + 1)
    )
    return tokens, limits.retries + 1


class ReplayModel:
    """Deterministic offline model; no network or external-effect capability."""

    def __init__(self, steps=()):
        self.calls = 0
        self.decisions = deque()
        self.steps = deque(steps)
        self.payloads: list[str] = []

    async def decide(self, context: ContextBundle, limits: ModelLimits) -> ActivityDecision:
        self.calls += 1
        self.payloads.append(context.payload())
        if self.decisions:
            return self.decisions.popleft()
        if context.task.startswith("[ready activities]\n"):
            import json

            ready = json.loads(context.task.split("\n", 1)[1])
            if ready["feedback"]:
                return ActivityDecision(activity=Activity.REFLECT)
            if ready["goals"]:
                return ActivityDecision(activity=Activity.WORK, goal_id=ready["goals"][0]["id"])
        activity = Activity.CHAT if context.task else Activity.REST
        return ActivityDecision(
            activity=activity,
            rationale="Deterministic replay policy",
            chat_action="reply" if "@mysoul" in context.task else "silent",
            reply="Replay draft: message received." if "@mysoul" in context.task else "",
        )

    async def execute_step(
        self, context: ContextBundle, tool_specs: list[dict], limits: ModelLimits
    ) -> StepDecision:
        self.calls += 1
        self.payloads.append(context.payload())
        if "[reflection]" in context.instructions:
            return StepDecision(
                done=True,
                note="# Work\nProcedure: verify\nRead artifacts before completing work.\n",
            )
        return (
            self.steps.popleft() if self.steps else StepDecision(done=True, note="Replay complete")
        )
