import asyncio
from collections.abc import Awaitable, Callable

from mysoul.domain import ToolRequest, ToolResult, now
from mysoul.storage import Conflict, StateStore


class EffectDispatcher:
    def __init__(self, store: StateStore, clock=now):
        self.store, self.clock = store, clock
        self.handlers: dict[str, Callable[[ToolRequest], Awaitable[ToolResult]]] = {}
        self.audiences: dict[str, set[str]] = {}
        self.specifications: dict[str, dict] = {}
        self.lock = asyncio.Lock()

    def register(self, name: str, handler, audiences=None, schema=None):
        if name in self.handlers:
            raise Conflict("Tool already registered")
        self.handlers[name] = handler
        self.audiences[name] = audiences or {"owner"}
        self.specifications[name] = {"name": name, "parameters": schema or {"type": "object"}}

    def tool_specs(self, audience):
        return [
            spec for name, spec in self.specifications.items() if audience in self.audiences[name]
        ]

    async def dispatch(self, request: ToolRequest) -> ToolResult:
        async with self.lock:
            with self.store.transaction() as db:
                previous = db.execute(
                    "SELECT request,result FROM effects WHERE id=?", (request.action_id,)
                ).fetchone()
                if previous:
                    old = ToolRequest.model_validate_json(previous[0])
                    if old.tool != request.tool or old.arguments != request.arguments:
                        raise Conflict("Action ID reused for different operation")
                    return ToolResult.model_validate_json(previous[1])
                # Read under the same SQLite transaction as intent insertion.
                row = db.execute("SELECT epoch FROM subjects WHERE id='mysoul'").fetchone()
                goal_row = db.execute(
                    "SELECT body FROM objects WHERE kind='goal' AND id=?", (request.goal_id,)
                ).fetchone()
                from mysoul.domain import Goal

                goal = Goal.model_validate_json(goal_row[0]) if goal_row else None
                allowed = (
                    row
                    and row[0] == request.epoch
                    and goal
                    and goal.status == "active"
                    and not goal.cancelled
                    and request.deadline > self.clock()
                    and request.tool in self.handlers
                    and request.scope.audience in self.audiences.get(request.tool, set())
                    and goal.elapsed_seconds < goal.time_limit
                )
                result = ToolResult(
                    action_id=request.action_id,
                    outcome="in_flight" if allowed else "not_sent",
                    error=None if allowed else "Runtime dispatch denied",
                )
                db.execute(
                    "INSERT INTO effects VALUES(?,?,?)",
                    (request.action_id, request.model_dump_json(), result.model_dump_json()),
                )
            if not allowed:
                return result
            try:
                # No scheduling point between the final checks and handler invocation.
                async with asyncio.timeout(
                    max(0.001, (request.deadline - self.clock()).total_seconds())
                ):
                    result = await self.handlers[request.tool](request)
                if result.action_id != request.action_id:
                    raise ValueError("Mismatched action receipt")
            except asyncio.CancelledError:
                self.store.record_result(
                    ToolResult(
                        action_id=request.action_id,
                        outcome="unknown",
                        error="Cancelled after dispatch",
                    )
                )
                raise
            except Exception as exc:
                result = ToolResult(
                    action_id=request.action_id, outcome="unknown", error=type(exc).__name__
                )
            self.store.record_result(result)
            return result

    async def reconcile(self, action_id: str, lookup) -> ToolResult:
        previous = self.store.effect(action_id)
        if not previous:
            raise KeyError(action_id)
        if previous.outcome != "unknown":
            return previous
        result = await lookup(action_id)
        if result.action_id != action_id:
            raise Conflict("Mismatched receipt")
        self.store.record_result(result)
        return result
