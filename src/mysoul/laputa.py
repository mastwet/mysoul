import json
from hashlib import sha256

from mysoul.domain import ContextBudget, ContextBundle, RecapVersion, Scope
from mysoul.memory import MemoryUnavailable
from mysoul.storage import Conflict, StateStore


class ContextOverflow(ValueError):
    pass


class RecapStore:
    def __init__(self, store: StateStore):
        self.store = store
        with store.transaction() as db:
            initial = RecapVersion()
            db.execute(
                "INSERT OR IGNORE INTO recap VALUES(?,?,?)",
                ("mysoul", 0, initial.model_dump_json()),
            )
            db.execute("INSERT OR IGNORE INTO recap_head VALUES('mysoul',0)")

    def current(self) -> RecapVersion:
        with self.store.lock:
            row = self.store.db.execute(
                "SELECT r.body FROM recap r JOIN recap_head h "
                "ON r.subject=h.subject AND r.version=h.version WHERE h.subject='mysoul'"
            ).fetchone()
            return RecapVersion.model_validate_json(row[0])

    def history(self):
        with self.store.lock:
            return [
                RecapVersion.model_validate_json(r[0])
                for r in self.store.db.execute(
                    "SELECT body FROM recap WHERE subject='mysoul' ORDER BY version DESC"
                )
            ]

    def publish(
        self,
        expected_version: int,
        text: str,
        refs: list[str],
        *,
        clear=False,
        author="operator",
        segments=(),
        expected_epoch=None,
        cognitive_run=None,
    ):
        if len(text) > 64000:
            raise ContextOverflow("Recap exceeds storage limit; review before publishing")
        with self.store.transaction() as db:
            if (
                expected_epoch is not None
                and db.execute("SELECT epoch FROM subjects WHERE id='mysoul'").fetchone()[0]
                != expected_epoch
            ):
                raise Conflict("Recap publication superseded by owner input")
            head = db.execute("SELECT version FROM recap_head WHERE subject='mysoul'").fetchone()[0]
            if head != expected_version:
                raise Conflict("Recap version conflict")
            old = RecapVersion.model_validate_json(
                db.execute(
                    "SELECT body FROM recap WHERE subject='mysoul' AND version=?", (head,)
                ).fetchone()[0]
            )
            for ref in refs:
                if not db.execute("SELECT 1 FROM evidence WHERE id=?", (ref,)).fetchone():
                    raise KeyError(ref)
            version = RecapVersion(
                version=head + 1,
                parent=head,
                text=text,
                refs=refs,
                content_hash=sha256(text.encode()).hexdigest(),
                invalidation_epoch=old.invalidation_epoch + int(clear),
                author=author,
            )
            db.execute(
                "INSERT INTO recap VALUES('mysoul',?,?)",
                (version.version, version.model_dump_json()),
            )
            db.execute("UPDATE recap_head SET version=? WHERE subject='mysoul'", (version.version,))
            if cognitive_run is not None:
                run = cognitive_run.model_copy(deep=True)
                policy = self.store.get("cognitive_policy", "current") or {"version": 0}
                if policy["version"] != run.policy.version:
                    raise Conflict("Maintenance policy changed")
                for part in run.window.slices:
                    source = self.store.get("cognitive_source", part.source_id)
                    if source.get("cleared") or source["covered"] != part.start:
                        raise Conflict("Source coverage changed")
                    source["covered"] = part.end
                    db.execute(
                        "UPDATE objects SET body=? WHERE kind='cognitive_source' AND id=?",
                        (json.dumps(source), part.source_id),
                    )
                    for ref in (source["event_id"], "reply:" + source["event_id"]):
                        db.execute(
                            "UPDATE objects SET body=json_set(body,'$.status','managed') "
                            "WHERE kind='recap_segment' AND id=?",
                            (ref,),
                        )
                run.stage = "reflect"
                run.recap_published_version = version.version
                run.receipts.append("reconcile")
                db.execute(
                    "UPDATE objects SET body=? WHERE kind='cognitive_run' AND id=?",
                    (run.model_dump_json(), run.id),
                )
            if clear:
                db.execute(
                    "UPDATE objects SET body=json_set(body,'$.cleared',1) "
                    "WHERE kind='cognitive_source'"
                )
                db.execute(
                    "UPDATE objects SET body=json_set(body,'$.status','cleared') "
                    "WHERE kind='recap_segment' AND json_extract(body,'$.status')='pending'"
                )
            else:
                for ref in segments:
                    db.execute(
                        "UPDATE objects SET body=json_set(body,'$.status','published',"
                        "'$.version',?) WHERE kind='recap_segment' AND id=?",
                        (version.version, ref),
                    )
            return version

    def clear(self, expected_version: int):
        return self.publish(expected_version, "", [], clear=True)

    def enqueue(self, ref):
        evidence = self.store.evidence(ref)
        if evidence.permitted(Scope()):
            self.store.put_new("recap_segment", ref, {"id": ref, "status": "pending"})

    def pending(self):
        return [s["id"] for s in self.store.all("recap_segment") if s["status"] == "pending"]


async def consolidate_recap(soul, expected_epoch):
    """Only called from a chosen reflection activity, never as hidden rest polling."""
    import asyncio

    from mysoul.domain import ContextBundle, ModelLimits
    from mysoul.model import budget_exceeded, reservation

    refs = soul.recap.pending()[:4]
    if not refs:
        return None
    previous = soul.recap.current()
    context = ContextBundle(
        instructions=(
            "[recap] Write a compact, useful private memory in note, done=true, no tool. "
            "Keep confirmed owner facts and interaction preferences separate from active topics. "
            "Assistant replies are model-authored: preserve fiction only as a clearly labeled "
            "continuity note, never as owner biography. Keep durable details and open threads; "
            "omit greetings, UI/tool acceptance logs, routine errors, and event IDs unless they "
            "matter to an unresolved issue. Cite stable evidence IDs after claims. "
            "Do not infer personal facts. Excerpts may be truncated; "
            "original evidence remains retrievable."
        ),
        recap=previous.text,
        recap_version=previous.version,
        recap_invalidation_epoch=previous.invalidation_epoch,
        evidence=[
            soul.store.evidence(ref).model_copy(
                update={"text": soul.store.evidence(ref).text[:1000]}
            )
            for ref in refs
        ],
    )
    if len(context.payload()) > soul.settings.context_chars:
        raise ContextOverflow("Recap needs operator reduction before automatic consolidation")
    state = soul.store.load_subject()
    if state.dispatch_epoch != expected_epoch:
        raise Conflict("Recap synthesis superseded")
    limits = ModelLimits(
        max_tokens=soul.settings.model_output_limit, timeout=soul.settings.request_timeout
    )
    reserve, attempts = reservation(soul.model, context, limits, [])
    if budget_exceeded(
        state.model_calls, attempts, soul.settings.model_call_limit
    ) or budget_exceeded(state.tokens_used, reserve, soul.settings.token_budget):
        raise Conflict("Recap synthesis budget exhausted")
    state.model_calls += attempts
    state.tokens_used += reserve
    soul.store.save_transition(expected_epoch, state)
    result = await asyncio.wait_for(soul.model.execute_step(context, [], limits), limits.timeout)
    if not result.done or result.tool or not result.note.strip():
        raise ValueError("Recap synthesis must produce a complete document without tools")
    return soul.recap.publish(
        previous.version,
        result.note,
        list(dict.fromkeys(previous.refs + refs)),
        author="agent",
        segments=refs,
        expected_epoch=expected_epoch,
    )


class ContextAssembler:
    def __init__(
        self,
        recap: RecapStore,
        memory,
        task="",
        persona_instructions="A helpful companion.",
        history=(),
        required_evidence=(),
        archive_evidence=(),
        covered_refs=(),
        required_history=False,
    ):
        self.recap, self.memory, self.task = recap, memory, task
        self.persona_instructions = persona_instructions
        self.history = history
        self.archive_evidence = list(archive_evidence)
        self.covered_refs = set(covered_refs)
        self.required_evidence = required_evidence
        self.required_history = required_history

    def base_bundle(self, scope: Scope) -> ContextBundle:
        # Deliberately no summary cache: every admission reads the committed head.
        version = self.recap.current()
        bundle = ContextBundle(scope=scope, task=self.task)
        bundle.instructions += "\n" + self.persona_instructions
        bundle.instructions += (
            "\n[记忆来源规则] 对话历史按 user/assistant 标注。"
            "assistant-reply 是 mysoul 生成的内容，"
            "其中的故事、假设和示例不能当作主人真实经历；仅为继续创作时保留为明确标注的故事设定。"
            "主人资料只依据主人自己的消息或明确确认。"
        )
        if scope.audience == "owner":
            bundle.recap = version.text
        bundle.recap_version = version.version
        bundle.recap_invalidation_epoch = version.invalidation_epoch
        bundle.evidence = list(self.required_evidence)
        bundle.archives = [e for e in self.archive_evidence if e.permitted(scope)]
        return bundle

    async def build(self, scope: Scope, budget: ContextBudget) -> ContextBundle:
        bundle = self.base_bundle(scope)
        if len(bundle.payload()) > budget.max_chars:
            raise ContextOverflow("Required context and raw sources exceed context budget")
        # Most recent whole turns first for admission; emit them chronologically.
        admitted = []
        for turn in reversed(self.history):
            candidate = bundle.model_copy(deep=True)
            candidate.history = list(turn) + admitted
            if len(candidate.payload()) > budget.max_chars:
                if self.required_history:
                    raise ContextOverflow("Required recent turns exceed context budget")
                break
            admitted = candidate.history
        bundle.history = admitted
        try:
            hits = await self.memory.search(self.task, scope, 10)
        except MemoryUnavailable:
            bundle.recall_status = "unavailable"
            hits = []
        refresh_recap_context(self.recap.store, bundle)
        if len(bundle.payload()) > budget.max_chars:
            raise ContextOverflow("Committed context changed beyond admission budget")
        for hit in hits:
            if not hit.permitted(scope):
                continue
            existing_ids = {e.id for e in bundle.evidence + bundle.archives}
            if hit.id in existing_ids:
                continue
            if hit.id in self.covered_refs:
                detail = getattr(self.memory, "detail", None)
                hit = await detail(hit, self.task, scope) if detail else None
                if hit is None or hit.id in existing_ids:
                    continue
            history_events = {message.event_id for message in bundle.history}
            if hit.id in history_events or (
                hit.source == "assistant-reply" and hit.id.removeprefix("reply:") in history_events
            ):
                continue
            candidate = bundle.model_copy(deep=True)
            candidate.evidence.append(hit)
            if len(candidate.payload()) <= budget.max_chars:
                bundle = candidate
        return bundle


def refresh_recap_context(store, bundle):
    version = RecapStore(store).current()
    bundle.recap = version.text if bundle.scope.audience == "owner" else ""
    bundle.recap_version = version.version
    bundle.recap_invalidation_epoch = version.invalidation_epoch
    return bundle
