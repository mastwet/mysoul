import asyncio

from mysoul.config import Settings
from mysoul.domain import (
    Activity,
    ActivityDecision,
    ContextBundle,
    Event,
    ModelLimits,
    now,
)
from mysoul.model import ModelAdapter
from mysoul.storage import StateStore


class LifeController:
    def __init__(self, store: StateStore, model: ModelAdapter, settings: Settings, clock=now):
        self.store, self.model, self.settings, self.clock = store, model, settings, clock
        store.load_subject()
        self.lock = asyncio.Lock()

    async def choose(
        self, events: list[Event], context: ContextBundle | None = None
    ) -> ActivityDecision:
        async with self.lock:
            state = self.store.load_subject()
            elapsed = max(0, (self.clock() - state.updated_at).total_seconds()) / 3600
            if self.settings.fatigue_enabled:
                rate = (
                    -self.settings.recovery_per_hour
                    if state.activity == Activity.REST
                    else self.settings.fatigue_per_hour
                )
                state.fatigue = max(0, min(1, state.fatigue + elapsed * rate))
            state.updated_at = self.clock()
            owner = any(e.trust == "owner_command" for e in events)
            limits = ModelLimits()
            blocked = (
                not events
                or state.model_calls >= self.settings.model_call_limit
                or state.tokens_used + limits.max_tokens > self.settings.token_budget
                or (state.fatigue >= 0.9 and not owner)
            )
            if blocked:
                state.activity = Activity.REST
                self.store.save_transition(state.dispatch_epoch, state)
                return ActivityDecision(activity=Activity.REST, rationale="Rest or runtime limit")
            # Reserve maximum output tokens before inference, including failed requests.
            state.model_calls += 1
            state.tokens_used += limits.max_tokens
            self.store.save_transition(state.dispatch_epoch, state)
            if context is None:
                scope = events[0].scope
                context = ContextBundle(
                    scope=scope,
                    task="\n".join(e.content for e in events if scope.admits(e.scope)),
                )
            try:
                decision = await asyncio.wait_for(
                    self.model.decide(context, limits), limits.timeout
                )
            except (ValueError, TimeoutError):
                decision = ActivityDecision(activity=Activity.REST, rationale="Model unavailable")
            latest = self.store.load_subject()
            if latest.dispatch_epoch != state.dispatch_epoch:
                return ActivityDecision(
                    activity=Activity.REST, rationale="Superseded by owner input"
                )
            latest.activity = decision.activity
            latest.rest_until = decision.rest_until
            self.store.save_transition(latest.dispatch_epoch, latest)
            return decision
