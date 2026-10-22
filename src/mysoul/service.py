"""One application service shared by replay, phone ingestion and the local API."""

from mysoul.admission import admitted
from mysoul.config import Settings
from mysoul.domain import (
    Activity,
    ContextBudget,
    Event,
    Evidence,
    Goal,
    ModelLimits,
    Scope,
    ToolResult,
    uid,
)
from mysoul.effects import EffectDispatcher
from mysoul.executor import Executor
from mysoul.laputa import ContextAssembler, ContextOverflow, RecapStore
from mysoul.lease import SubjectLease
from mysoul.life import LifeController
from mysoul.memory import FixtureMemory
from mysoul.model import ReplayModel, reservation
from mysoul.phone.replay import ReplayPhone
from mysoul.scheduler import Scheduler
from mysoul.skills import SkillStore
from mysoul.storage import StateStore
from mysoul.tools.files import ReadArgs, WorkspaceFiles, WriteArgs
from mysoul.tools.news import NewsReader


class SoulService:
    def __init__(self, settings: Settings, model=None, phone=None):
        self.settings = settings
        self.store = StateStore(settings.data_dir / "state.sqlite")
        self.store.load_subject()
        if model is None and settings.model_mode == "provider":
            from mysoul.provider import OpenAICompatibleModel

            model = OpenAICompatibleModel.from_environment()
        elif model is None and settings.model_mode == "procedure-replay":
            from mysoul.evolution import ProcedureReplayModel

            model = ProcedureReplayModel()
        self.model = model or ReplayModel()
        if phone is None and settings.backend == "napcat":
            import os

            from mysoul.phone.napcat import NapCatPhone

            phone = NapCatPhone(
                os.environ["MYSOUL_NAPCAT_URL"], os.environ["MYSOUL_NAPCAT_TOKEN"], settings
            )
        self.phone = phone or ReplayPhone()
        if bool(self.phone.capabilities["live"]) != (settings.backend == "napcat"):
            raise ValueError("Phone backend differs from trusted runtime configuration")
        self.memory = FixtureMemory(self.store)
        self.recap = RecapStore(self.store)
        self.skills = SkillStore(self.store, settings.data_dir / "skill-revisions")
        self.skills.initialize()
        self.life = LifeController(self.store, self.model, settings)
        self.scheduler = Scheduler(settings.event_capacity)
        self.effects = EffectDispatcher(self.store)
        self.effects.register("draft", self._draft, {"owner", "group", "public"})
        self.files = WorkspaceFiles(settings.data_dir / "workspace")
        self.effects.register("read_file", self._read_file, schema=ReadArgs.model_json_schema())
        self.effects.register("write_file", self._write_file, schema=WriteArgs.model_json_schema())
        self.news = NewsReader(settings.news_sources)
        if settings.news_sources:
            self.effects.register(
                "read_news",
                self._read_news,
                {"owner", "group", "public"},
                schema={
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "enum": sorted(settings.news_sources)}
                    },
                    "required": ["source"],
                    "additionalProperties": False,
                },
            )
        if self.phone.capabilities["live"]:
            self.effects.register(
                "qq_send",
                self.phone.act,
                {"group"},
                schema={
                    "type": "object",
                    "properties": {"text": {"type": "string", "maxLength": 4000}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
            )
        self.executor = Executor(
            self.store,
            self.model,
            self.effects,
            settings.data_dir / "graph-checkpoints.sqlite",
            settings,
        )
        self.lease = SubjectLease(settings.data_dir / "subject.lock")
        self.admission = self.executor.admission
        self.phone_cursor = (self.store.get("cursor", "phone") or {}).get("value")
        self.memory_process = None
        self.owner_turns = 0
        from mysoul.autonomy import ActivityRouter

        self.activities = ActivityRouter(self)

    async def __aenter__(self):
        try:
            self.lease.acquire()
            if self.settings.memory_backend == "mempalace":
                from mysoul.mempalace import MemPalaceProcess

                if not self.settings.mempalace_config:
                    raise ValueError("MemPalace process configuration required")
                self.memory_process = MemPalaceProcess.from_file(
                    self.settings.mempalace_config, self.store
                )
                self.memory = await self.memory_process.__aenter__()
            await self.executor.open()
        except BaseException:
            self.lease.release()
            self.store.close()
            raise
        return self

    async def __aexit__(self, *args):
        await self.executor.close()
        close = getattr(self.phone, "close", None)
        if close:
            await close()
        close_model = getattr(self.model, "close", None)
        if close_model:
            await close_model()
        if self.memory_process:
            await self.memory_process.__aexit__(*args)
        self.store.close()
        self.lease.release()

    async def tick(self):
        try:
            if self.admission.available():
                await self._phone_tick()
        finally:
            # Delivery is bounded and independent of ambient events and foreground work.
            if self.settings.memory_backend == "mempalace":
                from mysoul.memory import flush_memory_queue

                await flush_memory_queue(self.store, self.memory)

    @admitted("life")
    async def _phone_tick(self):
        batch = await self.phone.observe(self.phone_cursor)
        self.store.enqueue_batch(batch.events, batch.cursor)
        for event in self.store.pending_events(self.settings.event_capacity):
            self.scheduler.offer(event.model_copy(update={"trust": "data"}))
        self.phone_cursor = batch.cursor
        if self.executor.running or self.owner_turns:
            return
        events = self.scheduler.drain()
        if not events:
            await self.activities.idle()
            return
        groups = {}
        for event in events:
            if self.store.get("interaction", event.id):
                self.store.processed_event(event)
                continue
            groups.setdefault(event.scope.model_dump_json(), []).append(event)
        for group in groups.values():
            chunk = []
            size = 0
            for event in group:
                if chunk and size + len(event.content) > 4000:
                    await self._process_batch(chunk)
                    chunk = []
                    size = 0
                chunk.append(event)
                size += len(event.content)
            if chunk:
                await self._process_batch(chunk)

    async def _process_batch(self, group):
        if self.owner_turns:
            return
        epoch = self.store.load_subject().dispatch_epoch
        try:
            context = await self.context(group[0].scope, "\n".join(e.content for e in group))
            if self.store.load_subject().dispatch_epoch != epoch:
                return
            decision = await self.life.choose(group, context)
            for event in group:
                selected = (
                    decision
                    if event is group[-1]
                    else decision.model_copy(update={"chat_action": "silent", "reply": ""})
                )
                await self._ingest(
                    event, decision=selected, admission_epoch=epoch, execute_activity=False
                )
            await self.activities.drain_choices()
        except ContextOverflow:
            # Retain full evidence and consume the bad batch so other scopes can progress.
            for event in group:
                self.store.add_evidence(
                    Evidence(
                        id=event.id, text=event.content, scope=event.scope, source=event.source
                    )
                )
                self._record_interaction(
                    event,
                    {
                        "choice": "silent",
                        "event_id": event.id,
                        "activity": "rest",
                        "text": "",
                        "input": event.content,
                        "error": "context_overflow; retained for explicit operator review",
                    },
                )

    async def run_loop(self, stop):
        import asyncio

        while not stop.is_set():
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.store.put("job_error", "phone-loop", {"error": type(exc).__name__})
            try:
                await asyncio.wait_for(stop.wait(), 5)
            except TimeoutError:
                pass

    async def context(self, scope, task=""):
        persona = self.store.get("config", "persona") or {"public": "A helpful companion."}
        return await ContextAssembler(
            self.recap, self.memory, task=task, public_persona=persona["public"]
        ).build(scope, ContextBudget())

    async def _draft(self, request):
        text = request.arguments.get("text", "")
        if not isinstance(text, str) or not text or len(text) > 4000:
            return ToolResult(action_id=request.action_id, outcome="failed", error="Invalid draft")
        self.store.put(
            "draft",
            request.action_id,
            {"text": text, "scope": request.scope.model_dump(), "status": "draft"},
        )
        return ToolResult(
            action_id=request.action_id,
            outcome="confirmed",
            receipt=f"draft:{request.action_id}",
            content=text,
        )

    async def _read_file(self, request):
        try:
            args = ReadArgs.model_validate(request.arguments)
            text = self.files.read(args.path)
            evidence = Evidence(text=text, source=f"workspace:{args.path}", scope=request.scope)
            self.store.add_evidence(evidence)
            return ToolResult(
                action_id=request.action_id,
                outcome="confirmed",
                content=text,
                evidence_ref=evidence.id,
            )
        except (OSError, ValueError) as exc:
            return ToolResult(
                action_id=request.action_id, outcome="failed", error=type(exc).__name__
            )

    async def _write_file(self, request):
        try:
            args = WriteArgs.model_validate(request.arguments)
            self.files.write(args.path, args.text)
            return ToolResult(
                action_id=request.action_id,
                outcome="confirmed",
                receipt=f"workspace:{args.path}",
                content=f"Wrote {args.path}",
            )
        except (OSError, ValueError) as exc:
            return ToolResult(
                action_id=request.action_id, outcome="failed", error=type(exc).__name__
            )

    async def _read_news(self, request):
        try:
            if set(request.arguments) != {"source"}:
                raise ValueError("One configured source required")
            event = await self.news.read(request.arguments["source"])
            evidence = Evidence(
                id=event.id, text=event.content, scope=event.scope, source=event.source
            )
            self.store.add_evidence(evidence)
            return ToolResult(
                action_id=request.action_id,
                outcome="confirmed",
                content=event.content,
                evidence_ref=evidence.id,
            )
        except (ValueError, OSError) as exc:
            return ToolResult(
                action_id=request.action_id, outcome="failed", error=type(exc).__name__
            )

    @admitted("life")
    async def receive(self, event: Event):
        # External callers never get to assert owner authority in an Event field.
        event = event.model_copy(update={"trust": "data"})
        return await self._ingest(event)

    async def owner_message(self, text: str):
        event = Event(
            source="local-owner",
            sender=self.settings.owner_id,
            content=text,
            dedup_key=uid(),
            trust="owner_command",
        )
        self.owner_turns += 1
        try:
            await self.executor.interrupt(event)
            return await self._ingest(event)
        finally:
            self.owner_turns -= 1

    def _record_interaction(self, event, result):
        self.store.put("interaction", event.id, result)
        self.store.processed_event(event)
        return result

    def _reply_outcome(self, intent):
        result = dict(intent["result"])
        sends = self.store.effects_for_goal(intent["goal_id"], "qq_send")
        for request, receipt in sends:
            if receipt.outcome == "confirmed" and receipt.receipt:
                result.update(choice="sent", text=request.arguments["text"])
            elif receipt.outcome in {"unknown", "in_flight"}:
                result.update(choice="unknown", text="Reply outcome is uncertain; no resend")
        return result

    async def _ingest(
        self, event: Event, decision=None, admission_epoch=None, execute_activity=True
    ):
        if not self.store.add_event(event):
            canonical = self.store.event_for_dedup(event.dedup_key)
            if not canonical or self.store.get("interaction", canonical.id):
                return {"choice": "duplicate", "event_id": event.id}
            event = canonical
        intent = self.store.get("reply_intent", event.id)
        if intent:
            return self._record_interaction(event, self._reply_outcome(intent))
        self.store.add_evidence(
            Evidence(id=event.id, text=event.content, scope=event.scope, source=event.source)
        )
        self.recap.enqueue(event.id)
        if admission_epoch is None:
            admission_epoch = self.store.load_subject().dispatch_epoch
        if decision is None:
            context = await self.context(event.scope, event.content)
            if self.store.load_subject().dispatch_epoch != admission_epoch:
                return self._record_interaction(
                    event,
                    {
                        "choice": "silent",
                        "event_id": event.id,
                        "activity": "rest",
                        "text": "",
                        "input": event.content,
                        "error": "superseded",
                    },
                )
            decision = await self.life.choose([event], context)
        if event.trust == "owner_command":
            choice = "owner_served"
        elif (
            decision.activity == Activity.CHAT
            and decision.chat_action == "reply"
            and decision.reply
        ):
            choice = "draft"
        else:
            choice = "silent"
        text = ""
        if choice in {"draft", "owner_served"}:
            text = (
                "Replay: message received. No live message sent."
                if isinstance(self.model, ReplayModel)
                else decision.reply or decision.rationale
            )
        if (
            choice == "draft"
            and self.phone.capabilities["live"]
            and self.settings.send_enabled
            and event.scope.audience == "group"
            and not self.executor.running
            and not self.owner_turns
            and self.store.load_subject().dispatch_epoch == admission_epoch
        ):
            context = await self.context(
                event.scope, "Reply to this group using qq_send: " + decision.reply
            )
            goal = Goal(
                id="reply-" + event.id,
                objective="Reply to allowed group",
                step_limit=3,
                token_limit=16000,
                skill_version=self.skills.active().content_hash,
            )
            if self.store.load_subject().dispatch_epoch == admission_epoch:
                base = {
                    "choice": "draft",
                    "event_id": event.id,
                    "activity": decision.activity,
                    "text": text,
                    "input": event.content,
                }
                intent = {"goal_id": goal.id, "result": base, "epoch": admission_epoch}
                claimed = self.store.put_new("reply_intent", event.id, intent)
                if claimed:
                    await self.executor.start(goal, context, expected_epoch=admission_epoch)
                result = self._reply_outcome(self.store.get("reply_intent", event.id))
                return self._record_interaction(event, result)
        result = {
            "choice": choice,
            "event_id": event.id,
            "activity": decision.activity,
            "text": text,
            "input": event.content,
        }
        if choice == "draft":
            self.store.put(
                "draft",
                event.id,
                {"text": text, "scope": event.scope.model_dump(), "status": "draft"},
            )
        self.activities.enqueue(decision, admission_epoch, event)
        result = self._record_interaction(event, result)
        if execute_activity:
            await self.activities.drain_choices(
                owner_event_id=event.id if event.trust == "owner_command" else None
            )
        return result

    @admitted("work")
    async def start_goal(self, goal: Goal, *, expected_epoch=None):
        epoch = (
            self.store.load_subject().dispatch_epoch if expected_epoch is None else expected_epoch
        )
        version = self.skills.active()
        context = await self.context(
            Scope(), goal.objective + "\nCompletion: " + goal.completion_criteria
        )
        goal.skill_version = version.content_hash
        context.skill = version.text
        try:
            return await self.executor.start(goal, context, expected_epoch=epoch)
        finally:
            self.activities.capture_feedback()

    @admitted("reflection")
    async def reflect(self, evidence_refs: list[str], *, expected_epoch=None):
        from mysoul.storage import Conflict

        if self.executor.running:
            raise Conflict("Interrupt foreground work before reflection")
        if not evidence_refs:
            raise ValueError("Reflection requires evidence")
        epoch = (
            self.store.load_subject().dispatch_epoch if expected_epoch is None else expected_epoch
        )
        evidence = [self.store.evidence(ref) for ref in evidence_refs]
        context = await self.context(Scope(), "Propose one revised work skill as Markdown in note.")
        context.instructions += (
            "\n[reflection] Evolve procedures only; no authority or runtime edits."
        )
        context.evidence = evidence
        if len(context.payload()) > 16000:
            raise ValueError("Reflection evidence exceeds context budget")
        limits = ModelLimits(retries=0)
        reserve, attempts = reservation(self.model, context, limits, [])
        state = self.store.load_subject()
        if state.dispatch_epoch != epoch:
            raise Conflict("Reflection superseded during context preparation")
        if (
            state.model_calls + attempts > self.settings.model_call_limit
            or state.tokens_used + reserve > self.settings.token_budget
        ):
            raise Conflict("Reflection budget exhausted")
        state.activity = Activity.REFLECT
        state.model_calls += attempts
        state.tokens_used += reserve
        self.store.save_transition(state.dispatch_epoch, state)
        import asyncio

        result = await asyncio.wait_for(
            self.model.execute_step(context, [], limits), limits.timeout
        )
        if self.store.load_subject().dispatch_epoch != state.dispatch_epoch:
            raise Conflict("Reflection superseded by owner input")
        proposal = self.skills.propose(result.note, evidence_refs)
        self.store.put(
            "reflection", proposal.id, {"evidence_refs": evidence_refs, "proposal_id": proposal.id}
        )
        return proposal

    @admitted("reflection")
    async def maintain(self, epoch, refs):
        from mysoul.laputa import consolidate_recap

        await consolidate_recap(self, epoch)
        if refs and not any(p["status"] in {"proposed", "tested", "approved"}
                            for p in self.store.all("proposal")):
            proposal = await self.reflect(refs, expected_epoch=epoch)
            for ref in refs:
                self.store.put("task_feedback", ref, {
                    "id": ref, "status": "proposed", "learn": True, "proposal_id": proposal.id,
                })

    @admitted("reflection")
    async def test_candidate(self, proposal_id, cases=None):
        from mysoul.evolution import CandidateRunner, ProcedureReplayModel

        factory = ProcedureReplayModel
        label = "procedure-replay"
        if self.settings.model_mode == "provider":
            from mysoul.provider import OpenAICompatibleModel

            factory = OpenAICompatibleModel.from_environment
            label = getattr(self.model, "model", "configured-provider")
        return await CandidateRunner(
            self.skills, model_factory=factory, cases=cases, model_label=label, budget_owner=self
        ).run(proposal_id)

    def status(self):
        with self.store.lock:
            from mysoul.domain import ToolResult

            effects = [
                ToolResult.model_validate_json(row[0]).model_dump(mode="json")
                for row in self.store.db.execute(
                    "SELECT result FROM effects ORDER BY rowid DESC LIMIT 100"
                )
            ]
        return {
            "state": self.store.load_subject().model_dump(mode="json"),
            "activities": self.store.all("activity"),
            "goals": self.store.all("goal"),
            "recap": self.recap.current().model_dump(mode="json"),
            "interactions": self.store.all("interaction")[-100:],
            "drafts": self.store.all("draft")[-100:],
            "gates": {
                "provider": "deferred",
                "mempalace": "deferred",
                "qq": "deferred",
                "isolation": "disabled",
            },
            "backend": self.settings.backend,
            "send_enabled": self.settings.send_enabled,
            "persona": self.store.get("config", "persona") or {"public": "A helpful companion."},
            "reflections": self.store.all("reflection"),
            "errors": self.store.all("job_error")[-20:],
            "effects": effects,
        }
