from collections import OrderedDict

from mysoul.domain import Event


class Scheduler:
    """Bounded coalescing queue; owner input is retained ahead of ambient events."""

    def __init__(self, capacity=256):
        self.capacity = capacity
        self.pending: OrderedDict[str, Event] = OrderedDict()
        self.dropped = 0

    def offer(self, event: Event) -> bool:
        if event.dedup_key in self.pending:
            return False
        if len(self.pending) >= self.capacity:
            victim = next((k for k, v in self.pending.items() if v.trust != "owner_command"), None)
            if victim is None:
                self.dropped += 1
                return False
            del self.pending[victim]
            self.dropped += 1
        self.pending[event.dedup_key] = event
        return True

    def drain(self) -> list[Event]:
        batch = list(self.pending.values())
        self.pending.clear()
        return sorted(batch, key=lambda e: e.trust != "owner_command")

    def next_wake(self, clock):
        return clock() if self.pending else None
