from typing import Protocol

from mysoul.domain import EventBatch, ToolRequest, ToolResult


class Phone(Protocol):
    capabilities: dict[str, bool]

    async def observe(self, cursor: str | None) -> EventBatch: ...
    async def act(self, request: ToolRequest) -> ToolResult: ...
    async def result(self, action_id: str) -> ToolResult: ...
