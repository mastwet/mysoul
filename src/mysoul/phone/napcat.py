"""NapCat OneBot HTTP adapter. Sending has no automatic retries or assumed idempotency."""

from collections import OrderedDict
from datetime import UTC, datetime

import httpx

from mysoul.domain import Event, EventBatch, Scope, ToolResult


class NapCatPhone:
    capabilities = {"live": True, "lookup": False, "idempotency": False}

    def __init__(self, url, token, settings, *, transport=None):
        self.settings = settings
        self.client = httpx.AsyncClient(
            base_url=url,
            timeout=10,
            follow_redirects=False,
            headers={"Authorization": f"Bearer {token}"},
            transport=transport,
        )
        self.pending: OrderedDict[str, Event] = OrderedDict()
        self.seen: OrderedDict[str, None] = OrderedDict()
        self.results = {}

    def parse_event(self, data):
        kind = data.get("message_type")
        if kind not in {"group", "private"}:
            raise ValueError("Unsupported OneBot event")
        group = str(data.get("group_id", ""))
        if kind == "group" and group not in self.settings.allowed_groups:
            raise PermissionError("Group not allowlisted")
        sender = str(data["user_id"])
        if kind == "private" and sender != self.settings.owner_id:
            raise PermissionError("Private sender not allowlisted")
        return Event(
            source="napcat",
            sender=sender,
            dedup_key=f"napcat:{kind}:{group}:{data['message_id']}",
            scope=Scope(audience="group", conversation=group) if kind == "group" else Scope(),
            source_time=datetime.fromtimestamp(data["time"], UTC) if data.get("time") else None,
            content=data.get("raw_message", ""),
            trust="data",
        )

    def accept_event(self, data):
        event = self.parse_event(data)
        if event.dedup_key in self.seen:
            return False
        self.seen[event.dedup_key] = None
        if len(self.seen) > 2048:
            self.seen.popitem(last=False)
        self.pending[event.dedup_key] = event
        if len(self.pending) > self.settings.event_capacity:
            self.pending.popitem(last=False)
        return True

    async def observe(self, cursor):
        if not self.pending:
            for group in sorted(self.settings.allowed_groups):
                response = await self.client.post(
                    "/get_group_msg_history", json={"group_id": group, "count": 20}
                )
                response.raise_for_status()
                body = response.json()
                if body.get("retcode") != 0:
                    raise ValueError("NapCat observation failed")
                for item in body.get("data", {}).get("messages", []):
                    item = {**item, "message_type": "group", "group_id": group}
                    self.accept_event(item)
        events = list(self.pending.values())
        self.pending.clear()
        return EventBatch(events=events, cursor=events[-1].dedup_key if events else (cursor or ""))

    async def act(self, request):
        scope = request.scope
        if (
            not self.settings.send_enabled
            or not self.settings.owner_id
            or scope.audience != "group"
            or scope.conversation not in self.settings.allowed_groups
        ):
            return ToolResult(
                action_id=request.action_id,
                outcome="not_sent",
                error="QQ sending requires explicit runtime opt-in and allowlist",
            )
        if request.action_id in self.results:
            return self.results[request.action_id]
        text = request.arguments.get("text")
        if not isinstance(text, str) or not text or len(text) > 4000:
            return ToolResult(action_id=request.action_id, outcome="not_sent", error="Invalid text")
        try:
            response = await self.client.post(
                "/send_group_msg",
                json={
                    "group_id": scope.conversation,
                    "message": [{"type": "text", "data": {"text": text}}],
                },
            )
            response.raise_for_status()
            body = response.json()
            if body.get("retcode") != 0:
                result = ToolResult(
                    action_id=request.action_id, outcome="failed", error="QQ rejected send"
                )
            else:
                receipt = body.get("data", {}).get("message_id")
                result = ToolResult(
                    action_id=request.action_id,
                    outcome="confirmed" if receipt is not None else "unknown",
                    receipt=str(receipt) if receipt is not None else None,
                )
        except (httpx.HTTPError, ValueError):
            result = ToolResult(
                action_id=request.action_id,
                outcome="unknown",
                error="QQ acknowledgment unavailable; do not resend",
            )
        self.results[request.action_id] = result
        return result

    async def result(self, action_id):
        return self.results.get(
            action_id,
            ToolResult(
                action_id=action_id,
                outcome="unknown",
                error="Receipt lookup by action ID unsupported",
            ),
        )

    async def close(self):
        await self.client.aclose()
