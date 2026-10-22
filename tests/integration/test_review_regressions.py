import asyncio

import httpx
import pytest

from mysoul.config import Settings
from mysoul.domain import Activity, ActivityDecision, Event, Evidence, Goal, Scope, StepDecision
from mysoul.evolution import CandidateRunner
from mysoul.memory import FixtureMemory, MemoryUnavailable
from mysoul.model import ReplayModel
from mysoul.phone.napcat import NapCatPhone
from mysoul.phone.replay import ReplayPhone
from mysoul.service import SoulService
from mysoul.skills import SkillStore
from mysoul.storage import Conflict, StateStore


class ReplyModel(ReplayModel):
    async def decide(self, context, limits):
        self.calls += 1
        self.payloads.append(context.payload())
        return ActivityDecision(activity=Activity.CHAT, chat_action="reply", reply="planned reply")

    async def execute_step(self, context, tool_specs, limits):
        self.calls += 1
        self.payloads.append(context.payload())
        return (
            StepDecision(done=True)
            if context.step_results
            else StepDecision(tool="qq_send", arguments={"text": "actual reply"})
        )


def group_event(key="group"):
    return Event(
        content="@mysoul hello", dedup_key=key, scope=Scope(audience="group", conversation="g")
    )


def phone_rig(tmp_path, calls, unknown=False):
    settings = Settings(
        data_dir=tmp_path, backend="napcat", owner_id="42", allowed_groups={"g"}, send_enabled=True
    )

    def handler(request):
        if request.url.path == "/send_group_msg":
            calls.append(request)
            if unknown:
                raise httpx.ReadTimeout("lost acknowledgment")
        return httpx.Response(200, json={"retcode": 0, "data": {"message_id": 123, "messages": []}})

    return settings, NapCatPhone(
        "http://127.0.0.1:3000", "key", settings, transport=httpx.MockTransport(handler)
    )


@pytest.mark.parametrize("unknown", [False, True])
async def test_event_reply_crash_never_creates_second_remote_operation(tmp_path, unknown):
    class Cut(BaseException):
        pass

    calls = []
    settings, phone = phone_rig(tmp_path, calls, unknown)
    event = group_event()
    async with SoulService(settings, model=ReplyModel(), phone=phone) as soul:
        original = soul.store.put

        def crash(kind, *args):
            if kind == "interaction":
                raise Cut()
            return original(kind, *args)

        soul.store.put = crash
        with pytest.raises(Cut):
            await soul.receive(event)
        soul.store.put = original
    settings, phone = phone_rig(tmp_path, calls, unknown)
    async with SoulService(settings, model=ReplyModel(), phone=phone) as soul:
        recovered = await soul.receive(event)
        assert len(calls) == 1
        assert recovered["choice"] == ("unknown" if unknown else "sent")
        assert len(soul.status()["effects"]) == 1


async def test_owner_interrupt_during_reply_context_cannot_adopt_new_epoch(tmp_path):
    calls = []
    settings, phone = phone_rig(tmp_path, calls)
    async with SoulService(settings, model=ReplyModel(), phone=phone) as soul:
        entered, release = asyncio.Event(), asyncio.Event()
        original = soul.context

        async def delayed(scope, task=""):
            if task.startswith("Reply to this group"):
                entered.set()
                await release.wait()
            return await original(scope, task)

        soul.context = delayed
        task = asyncio.create_task(soul.receive(group_event()))
        await entered.wait()
        await soul.owner_message("stop autonomous work")
        release.set()
        await task
        assert calls == []


async def test_one_coalesced_batch_dispatches_at_most_one_reply(tmp_path):
    calls = []
    settings, phone = phone_rig(tmp_path, calls)
    for ident in range(3):
        phone.accept_event(
            {
                "message_type": "group",
                "group_id": "g",
                "user_id": 1,
                "message_id": ident,
                "raw_message": "@mysoul hello",
            }
        )
    async with SoulService(settings, model=ReplyModel(), phone=phone) as soul:
        await soul.tick()
        assert len(calls) == 1
        assert len(soul.store.all("interaction")) == 3


async def test_large_batch_and_oversized_event_do_not_poison_inbox(tmp_path):
    events = [
        Event(content="x" * 500, dedup_key=str(i), scope=Scope(audience="group", conversation="g"))
        for i in range(50)
    ]
    events.append(
        Event(
            content="x" * 32000,
            dedup_key="big",
            scope=Scope(audience="group", conversation="other"),
        )
    )
    async with SoulService(Settings(data_dir=tmp_path), phone=ReplayPhone(events)) as soul:
        await soul.tick()
        await soul.tick()
        assert soul.store.pending_events() == []
        assert len(soul.store.all("interaction")) == 51


async def test_recap_clear_applies_before_the_next_execution_inference(tmp_path):
    model = ReplayModel([StepDecision(note="first step"), StepDecision(done=True)])
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        soul.recap.publish(0, "PRIVATE_OLD", [])
        entered, release = asyncio.Event(), asyncio.Event()
        original = model.execute_step

        async def delayed(*args):
            if not entered.is_set():
                entered.set()
                await release.wait()
            return await original(*args)

        model.execute_step = delayed
        task = asyncio.create_task(soul.start_goal(Goal(objective="two steps")))
        await entered.wait()
        soul.recap.clear(1)
        release.set()
        await task
        assert "PRIVATE_OLD" in model.payloads[0]
        assert "PRIVATE_OLD" not in model.payloads[1]


async def test_candidate_test_completion_cannot_undo_rejection(tmp_path, monkeypatch):
    store = StateStore(tmp_path / "s.db")
    skills = SkillStore(store, tmp_path / "versions")
    skills.initialize()
    store.add_evidence(Evidence(id="failure", text="Not verified"))
    proposal = skills.propose("# Work\nProcedure: verify\n", ["failure"])
    entered, release = asyncio.Event(), asyncio.Event()
    original = SoulService.start_goal

    async def delayed(self, goal):
        entered.set()
        await release.wait()
        return await original(self, goal)

    monkeypatch.setattr(SoulService, "start_goal", delayed)
    task = asyncio.create_task(CandidateRunner(skills).run(proposal.id))
    await entered.wait()
    skills.reject(proposal.id)
    release.set()
    with pytest.raises(Conflict):
        await task
    assert skills.proposal(proposal.id).status == "rejected"
    assert len(store.all("skill_test")) == 1
    store.close()


async def test_memory_outbox_drains_on_quiet_ticks_without_model_calls(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        await soul.owner_message("retain my evidence")
        state = soul.store.load_subject()
        state.mode = "quiet"
        soul.store.save_transition(state.dispatch_epoch, state)
        before = soul.model.calls

        class RecoveringMemory(FixtureMemory):
            calls = 0

            async def add(self, evidence):
                self.calls += 1
                if self.calls == 1:
                    raise MemoryUnavailable("temporarily down")
                return await super().add(evidence)

        memory = RecoveringMemory(soul.store)
        soul.memory = memory
        soul.settings.memory_backend = "mempalace"
        await soul.tick()
        await soul.tick()
        assert memory.calls == 2
        assert soul.model.calls == before
        assert (
            soul.store.db.execute(
                "SELECT COUNT(*) FROM memory_queue WHERE status='pending'"
            ).fetchone()[0]
            == 0
        )


async def test_started_goal_is_displayed_and_accounted_as_work(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        entered, release = asyncio.Event(), asyncio.Event()
        original = soul.model.execute_step

        async def delayed(*args):
            entered.set()
            await release.wait()
            return await original(*args)

        soul.model.execute_step = delayed
        task = asyncio.create_task(soul.start_goal(Goal(objective="show actual work")))
        await entered.wait()
        try:
            assert soul.store.load_subject().activity == Activity.WORK
        finally:
            release.set()
            await task


async def test_send_status_and_text_come_from_the_actual_qq_receipt(tmp_path):
    calls = []
    settings, phone = phone_rig(tmp_path, calls)
    async with SoulService(settings, model=ReplyModel(), phone=phone) as soul:
        result = await soul.receive(group_event())
        assert result["choice"] == "sent" and result["text"] == "actual reply"


async def test_local_draft_receipt_is_not_a_sent_qq_message(tmp_path):
    calls = []
    settings, phone = phone_rig(tmp_path, calls)
    model = ReplyModel()

    async def draft(context, tool_specs, limits):
        return (
            StepDecision(done=True)
            if context.step_results
            else StepDecision(tool="draft", arguments={"text": "only a draft"})
        )

    model.execute_step = draft
    async with SoulService(settings, model=model, phone=phone) as soul:
        assert (await soul.receive(group_event()))["choice"] == "draft"
        assert calls == []


async def test_owner_turn_does_not_wait_for_ambient_inference(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        entered, release, owner_called = asyncio.Event(), asyncio.Event(), asyncio.Event()
        original = soul.model.decide

        async def delayed(context, limits):
            if context.scope.audience == "group":
                entered.set()
                await release.wait()
            else:
                owner_called.set()
            return await original(context, limits)

        soul.model.decide = delayed
        ambient = asyncio.create_task(soul.receive(group_event()))
        await entered.wait()
        owner = asyncio.create_task(soul.owner_message("owner takes priority"))
        try:
            await asyncio.wait_for(owner_called.wait(), 2)
        finally:
            release.set()
            await asyncio.gather(ambient, owner)


async def test_repeated_send_steps_cannot_send_two_replies_for_one_event(tmp_path):
    calls = []
    settings, phone = phone_rig(tmp_path, calls)
    model = ReplyModel()

    async def repeated(context, tool_specs, limits):
        return StepDecision(tool="qq_send", arguments={"text": "one reply"})

    model.execute_step = repeated
    async with SoulService(settings, model=model, phone=phone) as soul:
        await soul.receive(group_event())
        assert len(calls) == 1
