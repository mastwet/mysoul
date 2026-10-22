"""One application service shared by replay, phone ingestion and the local API."""

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
from mysoul.laputa import ContextAssembler, RecapStore
from mysoul.lease import SubjectLease
from mysoul.life import LifeController
from mysoul.memory import FixtureMemory
from mysoul.model import ReplayModel
from mysoul.phone.replay import ReplayPhone
from mysoul.scheduler import Scheduler
from mysoul.skills import SkillStore
from mysoul.storage import StateStore
from mysoul.tools.files import ReadArgs, WorkspaceFiles, WriteArgs


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
        self.effects.register("read_file", self._read_file)
        self.effects.register("write_file", self._write_file)
        self.executor = Executor(
            self.store,
            self.model,
            self.effects,
            settings.data_dir / "graph-checkpoints.sqlite",
            settings,
        )
        self.lease = SubjectLease(settings.data_dir / "subject.lock")
        self.phone_cursor = (self.store.get("cursor", "phone") or {}).get("value")
        self.memory_process = None

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
        batch = await self.phone.observe(self.phone_cursor)
        for event in batch.events:
            self.scheduler.offer(event.model_copy(update={"trust": "data"}))
        self.phone_cursor = batch.cursor
        self.store.put("cursor", "phone", {"value": batch.cursor})
        if self.executor.running:
            return
        events = self.scheduler.drain()
        if not events:
            await self.life.choose([])
            return
        groups = {}
        for event in events:
            if self.store.get("interaction", event.id) or any(
                e.dedup_key == event.dedup_key for e in self.store.events()
            ):
                continue
            groups.setdefault(event.scope.model_dump_json(), []).append(event)
        for group in groups.values():
            context = await self.context(group[0].scope, "\n".join(e.content for e in group))
            decision = await self.life.choose(group, context)
            for event in group:
                await self._ingest(event, decision=decision)
        if self.settings.memory_backend == "mempalace":
            from mysoul.memory import flush_memory_queue

            await flush_memory_queue(self.store, self.memory)

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
        await self.executor.interrupt(event)
        return await self._ingest(event)

    async def _ingest(self, event: Event, decision=None):
        if not self.store.add_event(event):
            return {"choice": "duplicate", "event_id": event.id}
        self.store.add_evidence(
            Evidence(id=event.id, text=event.content, scope=event.scope, source=event.source)
        )
        if decision is None:
            context = await self.context(event.scope, event.content)
            decision = await self.life.choose([event], context)
        if event.trust == "owner_command":
            choice = "owner_served"
        elif "@mysoul" in event.content:
            choice = "draft"
        else:
            choice = "silent"
        text = ""
        if choice in {"draft", "owner_served"}:
            text = (
                "Replay: message received. No live message sent."
                if isinstance(self.model, ReplayModel)
                else decision.rationale
            )
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
        self.store.put("interaction", event.id, result)
        return result

    async def start_goal(self, goal: Goal):
        context = await self.context(Scope(), goal.objective)
        version = self.skills.active()
        goal.skill_version = version.content_hash
        context.skill = version.text
        return await self.executor.start(goal, context)

    async def reflect(self, evidence_refs: list[str]):
        from mysoul.storage import Conflict

        if self.executor.running:
            raise Conflict("Interrupt foreground work before reflection")
        if not evidence_refs:
            raise ValueError("Reflection requires evidence")
        evidence = [self.store.evidence(ref) for ref in evidence_refs]
        context = await self.context(Scope(), "Propose one revised work skill as Markdown in note.")
        context.instructions += (
            "\n[reflection] Evolve procedures only; no authority or runtime edits."
        )
        context.evidence = evidence
        if len(context.payload()) > 16000:
            raise ValueError("Reflection evidence exceeds context budget")
        limits = ModelLimits(retries=0)
        state = self.store.load_subject()
        if (
            state.model_calls >= self.settings.model_call_limit
            or state.tokens_used + limits.max_tokens > self.settings.token_budget
        ):
            raise Conflict("Reflection budget exhausted")
        state.activity = Activity.REFLECT
        state.model_calls += 1
        state.tokens_used += limits.max_tokens
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
