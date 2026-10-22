import json
from pathlib import Path

from mysoul.domain import Event, EventBatch, ToolRequest, ToolResult


class ReplayPhone:
    capabilities = {"live": False, "lookup": True, "idempotency": True}

    def __init__(self, events=()):
        self.events = list(events)
        self.sent = []
        self.results: dict[str, ToolResult] = {}

    @classmethod
    def from_jsonl(cls, path):
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        if len(lines) > 10000:
            raise ValueError("Replay trace exceeds event limit")
        return cls(Event.model_validate(json.loads(line)) for line in lines if line.strip())

    async def observe(self, cursor: str | None):
        start = int(cursor or 0)
        if start < 0 or start > len(self.events):
            raise ValueError("Invalid replay cursor")
        end = min(start + 100, len(self.events))
        return EventBatch(events=self.events[start:end], cursor=str(end))

    async def act(self, request: ToolRequest):
        if request.action_id not in self.results:
            self.results[request.action_id] = ToolResult(
                action_id=request.action_id,
                outcome="confirmed",
                receipt=f"replay:{request.action_id}",
                content="Simulated; no live transport",
            )
        return self.results[request.action_id]

    async def result(self, action_id: str):
        return self.results.get(action_id, ToolResult(action_id=action_id, outcome="unknown"))
