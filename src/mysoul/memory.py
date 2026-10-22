"""Source-scoped memory, with an outbox independent of graph checkpoints."""

from typing import Protocol

from mysoul.domain import Evidence, Scope


class MemoryUnavailable(RuntimeError):
    pass


class Memory(Protocol):
    async def add(self, evidence: Evidence) -> str: ...
    async def search(self, query: str, scope: Scope, limit: int) -> list[Evidence]: ...
    async def get(self, ref: str, scope: Scope) -> Evidence: ...


class FixtureMemory:
    """Durable deterministic fixture; explicitly not the real-memory release gate."""

    def __init__(self, store):
        self.store = store
        self.available = True

    def check(self):
        if not self.available:
            raise MemoryUnavailable("Fixture memory unavailable")

    async def add(self, evidence: Evidence) -> str:
        self.check()
        self.store.add_evidence(evidence)
        return evidence.id

    async def search(self, query: str, scope: Scope, limit: int) -> list[Evidence]:
        self.check()
        with self.store.lock:
            rows = self.store.db.execute("SELECT body FROM evidence ORDER BY rowid DESC").fetchall()
        evidence = [Evidence.model_validate_json(row[0]) for row in rows]
        # Fixture recall is intentionally transparent, not a semantic-search claim.
        return [e for e in evidence if e.permitted(scope)][: max(0, min(limit, 100))]

    async def get(self, ref: str, scope: Scope) -> Evidence:
        self.check()
        evidence = self.store.evidence(ref)
        if not evidence.permitted(scope):
            raise PermissionError("Evidence outside admitted scope")
        return evidence


async def flush_memory_queue(store, memory: Memory, limit=20):
    with store.lock:
        rows = store.db.execute(
            "SELECT id FROM memory_queue WHERE status='pending' ORDER BY rowid LIMIT ?", (limit,)
        ).fetchall()
    delivered = 0
    for (ident,) in rows:
        try:
            ref = await memory.add(store.evidence(ident))
        except MemoryUnavailable:
            break
        with store.transaction() as db:
            db.execute(
                "UPDATE memory_queue SET status='delivered',remote_ref=? WHERE id=?", (ref, ident)
            )
        delivered += 1
    return delivered
