"""Immutable archive trees and atomic, non-overlapping owner context frontiers."""

import json
from hashlib import sha256
from itertools import groupby
from typing import Literal

from pydantic import Field

from mysoul.domain import Contract, Scope
from mysoul.laputa import RecapStore
from mysoul.storage import Conflict


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class CompressionPolicy(Contract):
    version: int = 0
    enabled: bool = True
    raw_trigger: int = Field(default=100, ge=2)
    raw_batch: int = Field(default=70, ge=1)
    keep_recent: int = Field(default=8, ge=0)
    upper_trigger: int = Field(default=4, ge=2)
    upper_batch: int = Field(default=3, ge=2)
    max_level: int = Field(default=8, ge=1, le=8)
    high_water: float = Field(default=0.75, gt=0, lt=1)
    low_water: float = Field(default=0.55, gt=0, lt=1)


class ArchiveNode(Contract):
    id: str
    level: int
    first_seq: int
    last_seq: int
    start_time: str
    end_time: str
    scope: Scope = Field(default_factory=Scope)
    children: list[str] = Field(default_factory=list)
    source_hash: str
    text: str
    active: bool = True
    revision: int = 1
    timeline_revision: int = 0
    fragment_of: str | None = None
    staged: bool = False
    eligible: bool = True
    start: int = 0
    end: int = 0
    total: int = 0


class CompressionPlan(Contract):
    mode: Literal["merge", "fragment", "fragment_merge", "fragment_reduce"] = "merge"
    replace_ids: list[str]
    input_ids: list[str]
    hashes: list[str]
    level: int
    first_seq: int
    last_seq: int
    epoch: int
    invalidation_epoch: int
    policy: CompressionPolicy
    content: str
    summary_limit: int = 4000
    start: int = 0
    end: int = 0
    total: int = 0


class ArchiveStore:
    def __init__(self, store):
        self.store = store

    def nodes(self):
        return [ArchiveNode.model_validate(v) for v in self.store.all("archive_node")]

    @staticmethod
    def save_in(db, node):
        db.execute(
            "INSERT OR REPLACE INTO objects VALUES('archive_node',?,?)",
            (node.id, node.model_dump_json()),
        )

    def node(self, ident):
        value = self.store.get("archive_node", ident)
        if value is None:
            raise KeyError(ident)
        return ArchiveNode.model_validate(value)

    def frontier(self, scope):
        if scope != Scope():
            return []
        with self.store.transaction() as db:
            rows = db.execute(
                "SELECT seq,id,created_at,body,revision,kind FROM timeline ORDER BY seq"
            ).fetchall()
            nodes = self.nodes()
            known = {n.id for n in nodes}
            active = [n for n in nodes if n.active]
            rebuild = set()
            for seq, _ident, _, _body, revision, _kind in rows:
                leaf_id = f"leaf:{seq}:{revision}"
                if leaf_id in known:
                    continue
                rebuild.add(seq)
                for n in active:
                    if n.first_seq <= seq <= n.last_seq:
                        n.active = False
                        self.save_in(db, n)
                        rebuild.update(range(n.first_seq, n.last_seq + 1))
            for seq, ident, created, body, revision, kind in rows:
                if seq not in rebuild:
                    continue
                value = json.loads(body)
                text = json.dumps(
                    {"kind": kind, "source_id": ident, "body": value}, ensure_ascii=False
                )
                eligible = not value.get("pending") and (
                    kind != "task"
                    or value.get("status") in {"completed", "cancelled", "failed", "abandoned"}
                )
                leaf = ArchiveNode(
                    id=f"leaf:{seq}:{revision}",
                    level=0,
                    first_seq=seq,
                    last_seq=seq,
                    start_time=created,
                    end_time=created,
                    source_hash=digest(value),
                    text=text,
                    timeline_revision=revision,
                    eligible=eligible,
                    end=len(text),
                    total=len(text),
                )
                self.save_in(db, leaf)
        return sorted((n for n in self.nodes() if n.active), key=lambda n: n.first_seq)

    def plan(self, policy, budget_chars, reserved_chars):
        policy = CompressionPolicy.model_validate(policy)
        nodes = self.frontier(Scope())
        if not policy.enabled or not nodes:
            return None
        size = sum(len(n.text) for n in nodes) + reserved_chars
        drain = self.store.get("archive_drain", "owner") or {}
        pressure = drain.get("active", False) and drain.get("policy_version") == policy.version
        if size >= budget_chars * policy.high_water:
            pressure = True
        if size <= budget_chars * policy.low_water:
            pressure = False
        updated = {"active": pressure, "policy_version": policy.version}
        if drain != updated:
            self.store.put("archive_drain", "owner", updated)
        raw = [n for n in nodes if n.level == 0]
        protected = {n.id for n in raw[-policy.keep_recent :]} if policy.keep_recent else set()
        groups = [list(g) for _, g in groupby(nodes, key=lambda n: n.level)]
        candidates = []
        for group in groups:
            upper_pressure = pressure and (
                len(group) >= 2
                or len(group[0].text) > max(256, budget_chars * policy.low_water - reserved_chars)
            )
            if group[0].level > 0 and (len(group) >= policy.upper_trigger or upper_pressure):
                candidates.append(group[: policy.upper_batch])
        if not candidates:
            for group in groups:
                if group[0].level != 0:
                    continue
                allowed = []
                for node in group:
                    if node.id in protected or not node.eligible:
                        break
                    allowed.append(node)
                if allowed and (len(raw) >= policy.raw_trigger or pressure):
                    candidates.append(allowed[: policy.raw_batch])
                    break
        if not candidates:
            return None
        selected = candidates[0]
        # Leave framing space; final admission rechecks the full serialized request.
        capacity = max(0, budget_chars - reserved_chars - 512)
        if capacity < 128:
            return None
        parts = []
        for node in selected:
            if parts and sum(len(p.text) + 32 for p in parts) + len(node.text) > capacity:
                break
            parts.append(node)
        selected = parts
        first = selected[0]
        level = min(policy.max_level, first.level + 1)
        inputs = [n.id for n in selected]
        replacements = inputs[:]
        content = "\n\n".join(n.text for n in selected)
        mode = "merge"
        start = 0
        end = len(content)
        total = len(content)
        if len(first.text) > capacity:
            selected = [first]
            replacements = [first.id]
            level = min(policy.max_level, first.level + 1)
            fragments = sorted(
                (
                    n
                    for n in self.nodes()
                    if n.fragment_of == first.id and n.total == len(first.text) and n.staged
                ),
                key=lambda n: n.start,
            )
            offset = 0
            contiguous = []
            for f in fragments:
                if f.start == offset:
                    contiguous.append(f)
                    offset = f.end
            if offset == len(first.text):
                mode = "fragment_merge"
                inputs = [f.id for f in contiguous]
                content = "\n\n".join(f.text for f in contiguous)
                if len(content) > capacity:
                    mode = "fragment_reduce"
                    batch = []
                    size = 0
                    for fragment in contiguous:
                        if size + len(fragment.text) + 2 > capacity:
                            break
                        batch.append(fragment)
                        size += len(fragment.text) + 2
                    if len(batch) < 2:
                        raise ValueError("Staged summary exceeds bounded fragment allowance")
                    inputs = [f.id for f in batch]
                    content = "\n\n".join(f.text for f in batch)
                    offset = batch[-1].end
                start = 0
                end = offset
                total = len(first.text)
            else:
                mode = "fragment"
                start = offset
                end = min(len(first.text), offset + capacity)
                total = len(first.text)
                content = first.text[start:end]
                inputs = [first.id]
        return CompressionPlan(
            mode=mode,
            replace_ids=replacements,
            input_ids=inputs,
            hashes=[self.node(i).source_hash for i in inputs],
            level=level,
            first_seq=selected[0].first_seq,
            last_seq=selected[-1].last_seq,
            epoch=self.store.load_subject().dispatch_epoch,
            invalidation_epoch=RecapStore(self.store).current().invalidation_epoch,
            policy=policy,
            content=content,
            summary_limit=min(
                4000 if level == 1 else 6000,
                capacity // 4 if mode.startswith("fragment") else capacity // 2,
            ),
            start=start,
            end=end,
            total=total,
        )

    def publish(self, plan, summary, operation_id):
        plan = CompressionPlan.model_validate(plan)
        candidate = digest({"plan": plan.model_dump(mode="json"), "summary": summary})
        receipt = self.store.get("archive_receipt", operation_id)
        if receipt:
            if receipt["hash"] != candidate:
                raise Conflict("Archive operation changed")
            return self.node(receipt["node_id"])
        cap = min(4000 if plan.level == 1 else 6000, plan.summary_limit)
        if not summary.strip() or len(summary) > min(cap, len(plan.content)):
            raise ValueError("Invalid or expanding archive summary")
        recap = RecapStore(self.store)
        with self.store.transaction() as db:
            state = db.execute("SELECT epoch FROM subjects WHERE id='mysoul'").fetchone()[0]
            if state != plan.epoch or recap.current().invalidation_epoch != plan.invalidation_epoch:
                raise Conflict("Archive snapshot superseded")
            # Compare timeline revisions without invoking a nested frontier transaction.
            for ident in plan.replace_ids:
                node = self.node(ident)
                if not node.active:
                    raise Conflict("Archive frontier changed")
                rows = db.execute(
                    "SELECT seq,revision FROM timeline WHERE seq BETWEEN ? AND ?",
                    (node.first_seq, node.last_seq),
                ).fetchall()
                for seq, revision in rows:
                    if self.store.get("archive_node", f"leaf:{seq}:{revision}") is None:
                        raise Conflict("Archive source changed")
            for ident, expected in zip(plan.input_ids, plan.hashes, strict=True):
                if self.node(ident).source_hash != expected:
                    raise Conflict("Archive child changed")
            first = self.node(plan.replace_ids[0])
            last = self.node(plan.replace_ids[-1])
            ident = "archive:" + candidate
            node = ArchiveNode(
                id=ident,
                level=plan.level,
                first_seq=plan.first_seq,
                last_seq=plan.last_seq,
                start_time=first.start_time,
                end_time=last.end_time,
                children=plan.input_ids,
                source_hash=candidate,
                text=summary,
                active=plan.mode in {"merge", "fragment_merge"},
                staged=plan.mode in {"fragment", "fragment_reduce"},
                fragment_of=first.id if plan.mode in {"fragment", "fragment_reduce"} else None,
                start=plan.start,
                end=plan.end,
                total=plan.total,
            )
            self.save_in(db, node)
            if plan.mode in {"fragment_reduce", "fragment_merge"}:
                for child_id in plan.input_ids:
                    child = self.node(child_id)
                    if not child.staged:
                        raise Conflict("Staged fragment already consumed")
                    child.staged = False
                    self.save_in(db, child)
            if node.active:
                for child_id in plan.replace_ids:
                    child = self.node(child_id)
                    child.active = False
                    self.save_in(db, child)
            db.execute(
                "INSERT INTO objects VALUES('archive_receipt',?,?)",
                (operation_id, json.dumps({"hash": candidate, "node_id": ident})),
            )
            return node

    def expand(self, node_id, scope, *, before=None, limit=50):
        if not 1 <= limit <= 100 or (before is not None and before < 1):
            raise ValueError("Invalid page")
        node = self.node(node_id)
        if not node.scope.admits(scope) or scope != node.scope:
            raise PermissionError("Archive scope denied")
        leaves = {}
        stack = [(node_id, False)]
        path = set()
        visited = set()
        while stack:
            ident, exiting = stack.pop()
            if exiting:
                path.remove(ident)
                visited.add(ident)
                continue
            if ident in path:
                raise ValueError("Archive reference cycle")
            if ident in visited:
                continue
            current = self.node(ident)
            if current.scope != scope:
                raise PermissionError("Archive child scope denied")
            path.add(ident)
            stack.append((ident, True))
            if current.level == 0:
                if before is None or current.first_seq < before:
                    leaves[current.first_seq] = {
                        "seq": current.first_seq,
                        "revision": current.timeline_revision,
                        "body": json.loads(current.text)["body"],
                    }
            else:
                stack.extend((child, False) for child in reversed(current.children))
        rows = sorted(leaves.values(), key=lambda value: value["seq"], reverse=True)
        items = list(reversed(rows[:limit]))
        return {
            "items": items,
            "next_before": items[0]["seq"] if items else None,
            "has_more": len(rows) > limit,
            "node": node.model_dump(mode="json"),
        }
