"""Memory-compatible archive lookup and bounded, query-specific original excerpts."""

import json
import re

from mysoul.domain import Evidence, Scope
from mysoul.memory import MemoryUnavailable


class ArchiveMemory:
    def __init__(self, memory, archives):
        self.memory, self.archives = memory, archives

    def __getattr__(self, name):
        return getattr(self.memory, name)

    @property
    def available(self):
        return self.memory.available

    @available.setter
    def available(self, value):
        self.memory.available = value

    async def add(self, evidence):
        return await self.memory.add(evidence)

    def evidence(self, node, scope):
        if node.scope != scope or scope != Scope():
            raise PermissionError("Archive outside admitted scope")
        if len(node.text) > 131072:
            raise MemoryUnavailable("Original requires paginated archive inspection")
        return Evidence(
            id=node.id,
            text=node.text,
            scope=scope,
            source=f"archive:L{node.level}",
            source_scopes=[scope],
        )

    async def get(self, ref, scope):
        if ref.startswith(("archive:", "leaf:")):
            return self.evidence(self.archives.node(ref), scope)
        return await self.memory.get(ref, scope)

    @staticmethod
    def terms(query):
        return re.findall(r"[a-z0-9_-]{3,}|[\u3400-\u9fff]{2,}", query.casefold())[:40]

    async def search(self, query, scope, limit):
        hits = await self.memory.search(query, scope, limit)
        terms = self.terms(query)
        if scope == Scope() and terms:
            for node in self.archives.frontier(scope):
                if node.level and any(term in node.text.casefold() for term in terms):
                    hits.append(self.evidence(node, scope))
        return hits[: max(0, min(limit, 100))]

    async def detail(self, hit, query, scope):
        if scope != Scope() or not hit.permitted(scope) or not query.strip():
            return None
        ref = hit.id.removeprefix("reply:")
        if ref.startswith("experience:"):
            ref = ref.removeprefix("experience:").rsplit(":", 1)[0]
        store = self.archives.store
        with store.lock:
            row = store.db.execute("SELECT seq FROM timeline WHERE source_id=?", (ref,)).fetchone()
            if row is None:
                row = store.db.execute(
                    "SELECT seq FROM timeline WHERE kind='task' AND "
                    "EXISTS(SELECT 1 FROM json_each(timeline.body,'$.effects') "
                    "WHERE json_extract(value,'$.evidence_ref')=?)",
                    (hit.id,),
                ).fetchone()
        if row is None:
            return None
        seq = row[0]
        root = next(
            (
                n
                for n in self.archives.frontier(scope)
                if n.level and n.first_seq <= seq <= n.last_seq
            ),
            None,
        )
        if root is None:
            return None
        current = root
        for _ in range(1000):
            if current.scope != scope:
                raise PermissionError("Archive child scope denied")
            if current.level == 0:
                break
            children = [self.archives.node(ident) for ident in current.children]
            current = next((n for n in children if n.first_seq <= seq <= n.last_seq), None)
            if current is None:
                return None
        else:
            return None
        body = json.loads(current.text)["body"]
        if hit.id.startswith("reply:"):
            text, role = body.get("text", ""), "assistant"
        elif body.get("input"):
            text, role = body["input"], "user"
        else:
            text, role = body.get("result", ""), "task-result"
            for effect in body.get("effects", []):
                if effect.get("evidence_ref") == hit.id:
                    text, role = effect.get("content", ""), "tool-result"
                    break
        matches = [text.casefold().find(term) for term in self.terms(query)]
        matches = [index for index in matches if index >= 0]
        if not matches:
            return None
        start = max(0, min(matches) - 100)
        end = min(len(text), start + 500)
        return Evidence(
            id=f"archive-detail:{current.id}:{start}:{end}",
            scope=scope,
            source="archive-detail",
            source_scopes=[scope],
            text=json.dumps(
                {
                    "archive": root.id,
                    "leaf": current.id,
                    "role": role,
                    "start": start,
                    "end": end,
                    "total": len(text),
                    "content": text[start:end],
                },
                ensure_ascii=False,
            ),
        )
