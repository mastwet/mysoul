from collections import deque
from typing import Protocol

from mysoul.domain import Activity, ActivityDecision, ContextBundle, ModelLimits, StepDecision


class ModelAdapter(Protocol):
    async def decide(self, context: ContextBundle, limits: ModelLimits) -> ActivityDecision: ...

    async def execute_step(
        self, context: ContextBundle, tool_specs: list[dict], limits: ModelLimits
    ) -> StepDecision: ...


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
        activity = Activity.CHAT if context.task else Activity.REST
        return ActivityDecision(activity=activity, rationale="Deterministic replay policy")

    async def execute_step(
        self, context: ContextBundle, tool_specs: list[dict], limits: ModelLimits
    ) -> StepDecision:
        self.calls += 1
        self.payloads.append(context.payload())
        return (
            self.steps.popleft() if self.steps else StepDecision(done=True, note="Replay complete")
        )
