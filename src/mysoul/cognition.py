"""Durable memory and persona maintenance, sharing the application's SQLite authority."""

import asyncio
import json
from datetime import timedelta
from typing import Literal

from pydantic import AwareDatetime, Field

from mysoul.domain import (
    Activity,
    ContextBundle,
    Contract,
    Event,
    Evidence,
    ModelLimits,
    Scope,
    now,
    uid,
)
from mysoul.laputa import ContextOverflow, RecapStore
from mysoul.model import budget_exceeded, reservation
from mysoul.recap_style import (
    RECAP_INSTRUCTIONS,
    clean_recap,
    previous_for_prompt,
    recap_evidence,
)
from mysoul.storage import Conflict


class SourceSlice(Contract):
    source_id: str
    event_id: str
    role: Literal["user", "assistant", "failure", "outcome", "legacy"]
    scope: Scope
    text: str
    start: int
    end: int
    total: int


class SourceWindow(Contract):
    recap_version: int
    invalidation_epoch: int
    slices: list[SourceSlice] = Field(default_factory=list)

    @property
    def refs(self):
        return list(dict.fromkeys(s.source_id for s in self.slices))


class CognitiveStore:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def _insert(db, ident, event_id, role, text, scope, created_at):
        if not text or scope.audience != "owner":
            return
        from mysoul.conversation import current_source_in

        if not current_source_in(db, event_id):
            return
        evidence = Evidence(
            id=ident, text=text, scope=scope, source="experience:" + role,
            source_scopes=[scope], created_at=created_at,
        )
        db.execute(
            "INSERT OR IGNORE INTO evidence VALUES(?,?)", (ident, evidence.model_dump_json()),
        )
        db.execute("INSERT OR IGNORE INTO objects VALUES('cognitive_source',?,?)", (
            ident, json.dumps({"id": ident, "event_id": event_id, "role": role,
                               "scope": scope.model_dump(), "covered": 0, "total": len(text),
                               "created_at": created_at.isoformat()}, ensure_ascii=False),
        ))

    def capture_interaction(self, event_id):
        with self.store.transaction() as db:
            self.capture_interaction_in(db, event_id)

    @classmethod
    def capture_interaction_in(cls, db, event_id):
        event_row = db.execute("SELECT body FROM events WHERE id=?", (event_id,)).fetchone()
        row = db.execute(
            "SELECT body FROM objects WHERE kind='interaction' AND id=?", (event_id,),
        ).fetchone()
        if not event_row or not row:
            return
        event, result = Event.model_validate_json(event_row[0]), json.loads(row[0])
        if event.scope.audience != "owner":
            return
        if event.source != "local-initiative":
            cls._insert(db, "experience:" + event.id + ":user", event.id, "user",
                        event.content, event.scope, event.received_at)
        failure = result.get("error") or result.get("choice") in {"unknown", "interrupted"}
        text = result.get("text", "")
        if text in {"Model unavailable", "Rest or runtime limit", "Context budget exhausted"}:
            failure = True
        if failure:
            text = json.dumps({"error": result.get("error"), "choice": result.get("choice"),
                               "message": text}, ensure_ascii=False)
        role = "failure" if failure else "assistant"
        cls._insert(db, "experience:" + event.id + ":" + role, event.id, role,
                    text, event.scope, event.received_at)

    def capture_outcome(self, activity_id):
        from mysoul.domain import now

        activity = self.store.activity(activity_id)
        if activity.status not in {"completed", "failed", "cancelled", "abandoned", "suspended"}:
            return
        context = self.store.get("activity_context", activity_id)
        if not context or context["scope"]["audience"] != "owner":
            return
        goal = self.store.goal(activity.goal_id)
        activity_body = activity.model_dump(mode="json", exclude={"final_note"})
        activity_body["effect_ids"] = [
            req.action_id for req, _ in self.store.effects_for_goal(goal.id)
            if req.activity_id == activity_id and req.tool not in {"memory_search", "memory_get"}
        ]
        text = json.dumps({"activity": activity_body,
                           "objective": goal.objective, "effects": [
                               {"id": req.action_id, "tool": req.tool, "outcome": res.outcome,
                                "evidence_ref": res.evidence_ref, "error": res.error}
                               for req, res in self.store.effects_for_goal(goal.id)
                               if req.tool not in {"memory_search", "memory_get"}
                           ]}, ensure_ascii=False)
        ident = f"outcome:{activity_id}:{activity.cursor}:{activity.status}"
        with self.store.transaction() as db:
            self._insert(db, ident, activity_id, "outcome", text, Scope(), now())
            def capture_result(key, content, provenance):
                # Separate immutable sources keep large results windowable with provenance.
                for offset in range(0, len(content), 60000):
                    body = json.dumps(provenance | {
                        "offset": offset, "total": len(content),
                        "content": content[offset:offset + 60000],
                    }, ensure_ascii=False)
                    self._insert(db, key + f":{offset}", activity_id, "outcome",
                                 body, Scope.model_validate(context["scope"]), now())

            for request, result in self.store.effects_for_goal(goal.id):
                if request.tool in {"memory_search", "memory_get"}:
                    continue
                if request.activity_id != activity_id or not Scope().admits(request.scope):
                    continue
                provenance = {"author": "tool", "tool": request.tool,
                              "action_id": request.action_id, "outcome": result.outcome,
                              "evidence_ref": result.evidence_ref}
                if result.outcome != "confirmed":
                    continue
                evidence = self.store.evidence(result.evidence_ref) if result.evidence_ref else None
                if evidence and not evidence.permitted(Scope()):
                    continue
                capture_result("outcome-tool:" + request.action_id, result.content, provenance)
                if evidence and evidence.text != result.content:
                    capture_result("outcome-evidence:" + request.action_id, evidence.text,
                                   provenance | {"source": evidence.source})
            if activity.final_note:
                capture_result("outcome-note:" + activity_id, activity.final_note,
                               {"author": "model", "status": activity.status})

    def recover_unfinished(self):
        # This runs under the service lease on every startup, independently of legacy migration.
        with self.store.transaction() as db:
            for segment in self.store.all("recap_segment"):
                if segment["status"] != "pending":
                    continue
                ref = segment["id"]
                row = db.execute("SELECT body FROM events WHERE id=?", (ref,)).fetchone()
                if not row or self.store.get("interaction", ref):
                    continue
                event = Event.model_validate_json(row[0])
                if event.source == "local-initiative":
                    continue
                self._insert(db, "experience:" + ref + ":user", ref, "user",
                             event.content, event.scope, event.received_at)
                self._insert(db, "experience:" + ref + ":failure", ref, "failure",
                             "Interaction unfinished at restart; no confirmed reply.",
                             event.scope, event.received_at)

    def migrate_pending(self):
        if self.store.get("cognitive_migration", "v1") is not None:
            return
        with self.store.transaction() as db:
            for segment in self.store.all("recap_segment"):
                ref = segment["id"]
                if segment["status"] != "pending":
                    db.execute("INSERT OR IGNORE INTO objects VALUES('cognitive_legacy',?,?)", (
                        ref, json.dumps({"id": ref, "status": "legacy_excerpt"}),
                    ))
                    continue
                event_id = ref.removeprefix("reply:")
                if self.store.get("interaction", event_id):
                    self.capture_interaction_in(db, event_id)
                else:
                    evidence = self.store.evidence(ref)
                    event_row = db.execute("SELECT body FROM events WHERE id=?", (ref,)).fetchone()
                    if event_row:
                        event = Event.model_validate_json(event_row[0])
                        if event.source != "local-initiative":
                            self._insert(db, "experience:" + ref + ":user", ref, "user",
                                         event.content, event.scope, event.received_at)
                            self._insert(db, "experience:" + ref + ":failure", ref, "failure",
                                         "Interaction unfinished at restart; no confirmed reply.",
                                         event.scope, event.received_at)
                        continue
                    self._insert(db, "legacy:" + ref, ref, "legacy", evidence.text,
                                 evidence.scope, evidence.created_at)
            db.execute("INSERT INTO objects VALUES('cognitive_migration','v1','{}')")

    def pending_window(self, max_chars):
        if max_chars <= 0:
            raise ValueError("Positive source window budget required")
        recap = RecapStore(self.store).current()
        window = SourceWindow(recap_version=recap.version,
                              invalidation_epoch=recap.invalidation_epoch)
        remaining = max_chars
        for source in sorted(self.store.all("cognitive_source"), key=lambda s: (
            s["created_at"], s["event_id"], s["role"] != "user", s["id"],
        )):
            start = source["covered"]
            if source.get("cleared") or start >= source["total"]:
                continue
            evidence = self.store.evidence(source["id"])
            size = source["total"] - start
            if window.slices and size > remaining:
                break
            end = min(source["total"], start + remaining)
            window.slices.append(SourceSlice(
                source_id=source["id"], event_id=source["event_id"], role=source["role"],
                scope=source["scope"], text=evidence.text[start:end],
                start=start, end=end, total=source["total"],
            ))
            remaining -= end - start
            if not remaining:
                break
        return window if window.slices else None





class CognitivePolicy(Contract):
    version: int = 0
    enabled: bool = True
    persona_enabled: bool = True
    interval_minutes: int = Field(default=3, ge=3, le=1440)
    window_chars: int = Field(default=16000, ge=1000, le=64000)
    tail_turns: int = Field(default=8, ge=0, le=20)


class CognitiveRun(Contract):
    id: str = Field(default_factory=uid)
    created_at: AwareDatetime = Field(default_factory=now)
    status: Literal["queued", "running", "failed", "superseded", "completed"] = "queued"
    stage: Literal["collect", "prepare", "reconcile", "reflect", "effects", "finish"] = "collect"
    receipts: list[str] = Field(default_factory=list)
    window: SourceWindow | None = None
    epoch: int = 0
    policy: CognitivePolicy = Field(default_factory=CognitivePolicy)
    persona: dict = Field(default_factory=dict)
    recap_text: str = ""
    recap_result: str | None = None
    recap_published_version: int | None = None
    reflection: dict | None = None
    attempts: int = 0
    next_attempt_at: AwareDatetime | None = None
    error: str = ""
    outcome: str = ""


class CognitiveService:
    def __init__(self, soul):
        self.soul = soul
        self.store = soul.store
        self.sources = CognitiveStore(self.store)

    def policy(self):
        return CognitivePolicy.model_validate(self.store.get("cognitive_policy", "current") or {})

    def set_policy(self, expected_version, enabled, persona_enabled, interval_minutes,
                   window_chars=None, tail_turns=None):
        with self.store.transaction() as db:
            old = self.policy()
            if old.version != expected_version:
                raise Conflict("Maintenance policy changed")
            data = old.model_dump() | dict(version=old.version + 1, enabled=enabled,
                                          persona_enabled=persona_enabled,
                                          interval_minutes=interval_minutes)
            if window_chars is not None:
                data["window_chars"] = window_chars
            if tail_turns is not None:
                data["tail_turns"] = tail_turns
            policy = CognitivePolicy.model_validate(data)
            db.execute("INSERT OR REPLACE INTO objects VALUES('cognitive_policy','current',?)",
                       (policy.model_dump_json(),))
            return policy

    def save(self, run):
        self.store.put("cognitive_run", run.id, run.model_dump(mode="json"))

    def status(self):
        sources = self.store.all("cognitive_source")
        runs = sorted(self.store.all("cognitive_run"), key=lambda r: r["created_at"])
        return {"policy": self.policy().model_dump(), "runs": runs[-30:],
                "sources": sources, "pending": sum(
                    not s.get("cleared") and s["covered"] < s["total"] for s in sources),
                "covered": sum(s["covered"] == s["total"] for s in sources),
                "legacy_excerpts": len(self.store.all("cognitive_legacy"))}

    def enqueue(self, expected_version):
        if self.policy().version != expected_version:
            raise Conflict("Maintenance policy changed")
        for data in self.store.all("cognitive_run"):
            if data["status"] in {"queued", "running", "failed"}:
                run = CognitiveRun.model_validate(data)
                if run.status != "running":
                    run.status = "queued"
                    run.next_attempt_at = None
                    self.save(run)
                return run
        if not self.sources.pending_window(self.policy().window_chars):
            return None
        run = CognitiveRun()
        self.save(run)
        return run

    def check(self, run):
        if self.store.load_subject().dispatch_epoch != run.epoch:
            raise Conflict("Owner input superseded maintenance")
        if self.policy().version != run.policy.version:
            raise Conflict("Maintenance policy changed")
        recap = self.soul.recap.current()
        expected = run.recap_published_version or run.window.recap_version
        if recap.version != expected or recap.invalidation_epoch != run.window.invalidation_epoch:
            raise Conflict("Recap changed during maintenance")

    def context(self, run, instructions):
        context = ContextBundle(instructions=instructions, recap=run.recap_text,
                                recap_version=run.window.recap_version,
                                recap_invalidation_epoch=run.window.invalidation_epoch)
        context.evidence = [self.store.evidence(s.source_id).model_copy(update={
            "text": json.dumps({"role": s.role, "start": s.start, "end": s.end,
                                "total": s.total, "content": s.text}, ensure_ascii=False),
        }) for s in run.window.slices]
        return context

    async def call(self, run, context, *, reflection=False):
        self.check(run)
        if len(context.payload()) > self.soul.settings.context_chars:
            raise ContextOverflow("Required maintenance window exceeds context budget")
        state = self.store.load_subject()
        limits = ModelLimits(max_tokens=self.soul.settings.model_output_limit,
                             timeout=self.soul.settings.request_timeout)
        reserve, attempts = reservation(self.soul.model, context, limits, [])
        if reflection and hasattr(self.soul.model, "reflection_reservation"):
            reserve = self.soul.model.reflection_reservation(context, limits)
        if (budget_exceeded(state.model_calls, attempts, self.soul.settings.model_call_limit)
                or budget_exceeded(state.tokens_used, reserve, self.soul.settings.token_budget)):
            raise ValueError("Maintenance budget exhausted")
        state.model_calls += attempts
        state.tokens_used += reserve
        state.activity = Activity.REFLECT
        self.store.save_transition(run.epoch, state)
        call = (self.soul.model.reflect(context, limits) if reflection
                else self.soul.model.execute_step(context, [], limits))
        result = await asyncio.wait_for(call, limits.timeout)
        self.check(run)
        return result

    async def reflect_run(self, run):
        from mysoul.persona import ReflectionDecision

        self.check(run)
        if not run.policy.persona_enabled:
            decision = ReflectionDecision(reason="Automatic persona evolution paused by owner")
        else:
            context = self.context(run, (
                "[persona-reflection] Reflect on this admitted experience window. Return only "
                "evidence-supported changes or no changes with a reason. Changes replace a field's "
                "whole text except WORLD; preserve existing supported content. WORLD text is an "
                "addition merged with its unseen base, never a replacement. Allowed targets: "
                "identity, "
                "relationship, dark, world, user_observations. Redline, Mission, Dream, public "
                "persona and owner-written USER text are protected. These cannot change tools, "
                "permissions or runtime rules. User observations are model inferences, not facts. "
                "Assistant fiction is not owner biography; failures are not completed actions. "
                "Cite only supplied evidence IDs. Omit routine chatter, errors and speculative "
                "changes. Notes are private, model-authored reflection. Write Chinese."
            ))
            projection = json.loads(json.dumps(run.persona))
            projection["sections"].pop("world", None)
            context.task = json.dumps({"frozen_persona": projection}, ensure_ascii=False)
            context.recap = run.recap_result
            context.persona_version = run.persona["version"]
            decision = ReflectionDecision.model_validate(await self.call(
                run, context, reflection=True))
        run.reflection = decision.model_dump(mode="json")
        run.receipts.append("reflect")
        run.stage = "effects"
        self.save(run)

    def apply_effects(self, run):
        from mysoul.persona import ReflectionDecision, content_hash

        self.check(run)
        decision = ReflectionDecision.model_validate(run.reflection)
        if decision.changes:
            self.soul.persona.apply_evolution(
                run.persona["version"], run.epoch, "evolution:" + run.id,
                decision.changes, run.window.refs,
                expected_base_hash=content_hash(run.persona),
                source_window=run.window.model_dump(mode="json"),
            )
            receipt = self.store.get("persona_change", "evolution:" + run.id)
            run.outcome = receipt["status"]
        else:
            run.outcome = "no_change"
        if decision.note:
            self.store.add_evidence(Evidence(
                id="reflection-note:" + run.id,
                text="[Model-inferred reflection; not owner-confirmed]\n" + decision.note,
                source="model-reflection", source_scopes=[Scope()],
            ))
        run.receipts.append("effects")
        run.stage = "finish"
        self.save(run)

    async def run_due(self, *, force=False):
        soul, instant, policy = self.soul, self.soul.life.clock(), self.policy()
        state = self.store.load_subject()
        if (not soul.admission.available() or soul.executor.running or soul.owner_turns
                or state.mode != "normal" or state.fatigue >= 0.9
                or (state.rest_until and state.rest_until > instant)):
            return None
        candidates = [CognitiveRun.model_validate(r) for r in self.store.all("cognitive_run")
                      if r["status"] in {"queued", "running", "failed"}]
        run = candidates[0] if candidates else None
        if not policy.enabled and not force and not (run and run.status == "queued"):
            return None
        if run and run.next_attempt_at and run.next_attempt_at > instant and not force:
            return None
        if run is None:
            schedule = self.store.get("cognitive_schedule", "current")
            if not force and schedule and now_from_iso(schedule["due"]) > instant:
                return None
            window = self.sources.pending_window(policy.window_chars)
            if window is None:
                return None
            run = CognitiveRun(created_at=instant)
        with soul.admission.hold("cognition"):
            try:
                if run.stage == "collect":
                    run.window = self.sources.pending_window(policy.window_chars)
                    if run.window is None:
                        run.status, run.outcome = "completed", "empty"
                        self.save(run)
                        return run
                    run.policy, run.epoch = policy, state.dispatch_epoch
                    run.persona = soul.persona.current().model_dump(mode="json")
                    run.recap_text = soul.recap.current().text
                    run.receipts = ["collect", "prepare"]
                    run.stage = "reconcile"
                run.status, run.error = "running", ""
                self.save(run)
                self.store.put("cognitive_schedule", "current", {
                    "due": (instant + timedelta(minutes=policy.interval_minutes)).isoformat(),
                })
                self.check(run)
                if run.stage == "reconcile":
                    if run.recap_result is None:
                        context = self.context(run, RECAP_INSTRUCTIONS)
                        context.recap = previous_for_prompt(self.store, run.recap_text)
                        context.evidence = recap_evidence(context.evidence)
                        result = await self.call(run, context)
                        if not result.done or result.tool or not result.note.strip():
                            raise ValueError("Recap must be a complete document without tools")
                        note = clean_recap(result.note)
                        if not note:
                            raise ValueError(
                                "Recap contains no event memory after removing citations"
                            )
                        run.recap_result = note
                        self.save(run)
                    self.check(run)
                    run.recap_result = clean_recap(run.recap_result)
                    if not run.recap_result:
                        run.recap_result = None
                        raise ValueError("Recap contains no event memory after removing citations")
                    published = soul.recap.publish(
                        run.window.recap_version, run.recap_result,
                        list(dict.fromkeys(soul.recap.current().refs + run.window.refs)),
                        author="agent", expected_epoch=run.epoch, cognitive_run=run,
                    )
                    run.recap_published_version = published.version
                    run.stage = "reflect"
                    run.receipts.append("reconcile")
                if run.stage == "reflect":
                    await self.reflect_run(run)
                if run.stage == "effects":
                    self.apply_effects(run)
                run.status = "completed"
                run.receipts.append("finish")
                run.next_attempt_at = None
                self.save(run)
            except Conflict as exc:
                run.status, run.error = "superseded", str(exc)
                self.save(run)
            except Exception as exc:
                run.status = "failed"
                run.error = type(exc).__name__ + ": " + str(exc)[:300]
                run.attempts += 1
                run.next_attempt_at = instant + timedelta(minutes=min(60, 3 * 2 ** min(
                    run.attempts - 1, 5)))
                self.save(run)
            return run


def now_from_iso(value):
    from datetime import datetime

    return datetime.fromisoformat(value)
