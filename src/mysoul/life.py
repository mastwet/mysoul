import asyncio

from mysoul.config import Settings
from mysoul.domain import (
    Activity,
    ActivityDecision,
    ContextBundle,
    Event,
    ModelLimits,
    Scope,
    now,
)
from mysoul.model import ModelAdapter, reservation
from mysoul.storage import StateStore


def advance_fatigue(state, settings, instant):
    elapsed = max(0, (instant - state.updated_at).total_seconds()) / 3600
    if settings.fatigue_enabled:
        rate = (
            -settings.recovery_per_hour
            if state.activity == Activity.REST
            else settings.fatigue_per_hour
        )
        state.fatigue = max(0, min(1, state.fatigue + elapsed * rate))
    state.updated_at = instant
    return state


class LifeController:
    def __init__(self, store: StateStore, model: ModelAdapter, settings: Settings, clock=now):
        self.store, self.model, self.settings, self.clock = store, model, settings, clock
        store.load_subject()
        self.lock = asyncio.Lock()

    async def choose(
        self, events: list[Event], context: ContextBundle | None = None
    ) -> ActivityDecision:
        if any(event.trust == "owner_command" for event in events):
            return await self._choose(events, context)
        async with self.lock:
            return await self._choose(events, context)

    async def _choose(self, events, context):
        state = self.store.load_subject()
        advance_fatigue(state, self.settings, self.clock())
        owner = any(e.trust == "owner_command" for e in events)
        expired = state.rest_until is not None and self.clock() >= state.rest_until
        limits = ModelLimits()
        if context is None:
            scope = events[0].scope if events else Scope()
            context = ContextBundle(
                scope=scope, task="\n".join(e.content for e in events if scope.admits(e.scope))
            )
        reserve, attempts = reservation(self.model, context, limits)
        blocked = (
            (not events and not expired)
            or state.model_calls + attempts > self.settings.model_call_limit
            or state.tokens_used + reserve > self.settings.token_budget
            or (state.fatigue >= 0.9 and not owner)
            or (
                state.mode == "quiet"
                and not owner
                and not expired
                and not any("@mysoul" in e.content for e in events)
            )
        )
        if blocked:
            state.activity = Activity.REST
            self.store.save_transition(state.dispatch_epoch, state)
            return ActivityDecision(activity=Activity.REST, rationale="Rest or runtime limit")
        from mysoul.laputa import ContextOverflow, refresh_recap_context

        refresh_recap_context(self.store, context)
        if len(context.payload()) > 16000:
            raise ContextOverflow("Required context exceeds admission budget")
        context.instructions += (
            "\nPrefer bounded goals over incidental chat."
            if state.mode == "focused"
            else "\nPrefer silence unless directly addressed."
            if state.mode == "quiet"
            else ""
        )
        # Reserve after final context admission, including any mode instructions.
        reserve, attempts = reservation(self.model, context, limits)
        if state.tokens_used + reserve > self.settings.token_budget:
            return ActivityDecision(activity=Activity.REST, rationale="Context budget exhausted")
        # Reserve maximum output tokens before inference, including failed requests.
        state.model_calls += attempts
        state.tokens_used += reserve
        self.store.save_transition(state.dispatch_epoch, state)
        try:
            decision = await asyncio.wait_for(self.model.decide(context, limits), limits.timeout)
        except (ValueError, TimeoutError):
            decision = ActivityDecision(activity=Activity.REST, rationale="Model unavailable")
        latest = self.store.load_subject()
        if latest.dispatch_epoch != state.dispatch_epoch:
            return ActivityDecision(activity=Activity.REST, rationale="Superseded by owner input")
        latest.activity = decision.activity
        latest.rest_until = (
            decision.rest_until
            if decision.rest_until and decision.rest_until > self.clock()
            else None
        )
        self.store.save_transition(latest.dispatch_epoch, latest)
        return decision
