"""One application service shared by replay, phone ingestion and the local API."""

from mysoul.config import Settings
from mysoul.domain import (
    ContextBudget,
    Event,
    Evidence,
    Goal,
    Scope,
    ToolResult,
    uid,
)
from mysoul.effects import EffectDispatcher
from mysoul.executor import Executor
from mysoul.laputa import ContextAssembler, RecapStore
from mysoul.life import LifeController
from mysoul.memory import FixtureMemory
from mysoul.model import ReplayModel
from mysoul.phone.replay import ReplayPhone
from mysoul.scheduler import Scheduler
from mysoul.storage import StateStore


class SoulService:
    def __init__(self, settings: Settings, model=None, phone=None):
        self.settings = settings
        self.store = StateStore(settings.data_dir / "state.sqlite")
        self.store.load_subject()
        self.model = model or ReplayModel()
        self.phone = phone or ReplayPhone()
        if bool(self.phone.capabilities["live"]) != (settings.backend == "napcat"):
            raise ValueError("Phone backend differs from trusted runtime configuration")
        self.memory = FixtureMemory(self.store)
        self.recap = RecapStore(self.store)
        self.life = LifeController(self.store, self.model, settings)
        self.scheduler = Scheduler(settings.event_capacity)
        self.effects = EffectDispatcher(self.store)
        self.effects.register("draft", self._draft, {"owner", "group", "public"})
        self.executor = Executor(
            self.store,
            self.model,
            self.effects,
            settings.data_dir / "graph-checkpoints.sqlite",
            settings,
        )

    async def __aenter__(self):
        await self.executor.open()
        return self

    async def __aexit__(self, *args):
        await self.executor.close()
        close = getattr(self.phone, "close", None)
        if close:
            await close()
        self.store.close()

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

    async def _ingest(self, event: Event):
        if not self.store.add_event(event):
            return {"choice": "duplicate", "event_id": event.id}
        self.store.add_evidence(
            Evidence(id=event.id, text=event.content, scope=event.scope, source=event.source)
        )
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
        }
        self.store.put("interaction", event.id, result)
        return result

    async def start_goal(self, goal: Goal):
        context = await self.context(Scope(), goal.objective)
        return await self.executor.start(goal, context)

    def status(self):
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
        }
