"""Source-scoped memory, with an outbox independent of graph checkpoints."""

import json
import re
from typing import Protocol

from mysoul.domain import Evidence, Scope

READ_ONLY_MEMORY_TOOLS = frozenset({"memory_search", "memory_get"})


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


class LocalMemory(FixtureMemory):
    """Durable local lexical recall, explicitly distinct from semantic MemPalace."""

    async def search(self, query: str, scope: Scope, limit: int) -> list[Evidence]:
        self.check()
        limit = max(0, min(limit, 100))
        if not limit:
            return []
        words = re.findall(r"[a-zA-Z0-9_]{2,}|[\u3400-\u9fff]+", query.casefold())
        terms = list(
            dict.fromkeys(
                part
                for word in words
                for part in (
                    [word]
                    if not re.search(r"[\u3400-\u9fff]", word)
                    else [word] + [word[i : i + 2] for i in range(len(word) - 1)]
                )
            )
        )[:40]
        permitted = "(json_extract(body,'$.scope.audience')='public' OR "
        permitted += "(json_extract(body,'$.scope.audience')=? AND "
        permitted += "json_extract(body,'$.scope.conversation')=?))"
        arguments = [scope.audience, scope.conversation]
        where = permitted
        if terms:
            where += (
                " AND ("
                + " OR ".join("json_extract(body,'$.text') LIKE ? ESCAPE '!'" for _ in terms)
                + ")"
            )
            arguments.extend(
                "%" + term.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
                for term in terms
            )
        with self.store.lock:
            rows = self.store.db.execute(
                "SELECT body FROM evidence WHERE " + where + " ORDER BY rowid DESC LIMIT 1000",
                arguments,
            ).fetchall()
        hits = [Evidence.model_validate(json.loads(row[0])) for row in rows]
        hits = [hit for hit in hits if hit.permitted(scope)]
        if terms:
            hits.sort(
                key=lambda hit: sum(
                    len(term) ** 2 for term in terms if term in hit.text.casefold()
                ),
                reverse=True,
            )
        return hits[:limit]


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
