from datetime import timedelta

import pytest

from mysoul.config import Settings
from mysoul.domain import Activity, ActivityDecision, Event, Scope, now
from mysoul.model import ReplayModel
from mysoul.service import SoulService


class InitiativeModel(ReplayModel):
    def __init__(self):
        super().__init__()
        self.contexts = []

    async def decide(self, context, limits):
        self.calls += 1
        self.contexts.append(context.model_copy(deep=True))
        if "[main-chat initiative]" in context.task:
            return ActivityDecision(
                activity=Activity.CHAT,
                chat_action="reply",
                reply="今天我们可以接着把自主行为的节奏调舒服。",
            )
        return ActivityDecision(activity=Activity.REST)


async def test_idle_creates_one_persisted_main_chat_initiative(tmp_path):
    model = InitiativeModel()
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        state = soul.store.load_subject()
        state.autonomy_enabled = True
        state.next_initiative_at = now() - timedelta(seconds=1)
        soul.store.save_transition(state.dispatch_epoch, state)

        await soul.activities.idle()

        messages = [
            item for item in soul.status()["interactions"] if item["choice"] == "initiative"
        ]
        assert len(messages) == 1
        assert messages[0]["input"] == ""
        assert messages[0]["text"] == "今天我们可以接着把自主行为的节奏调舒服。"
        assert soul.store.load_subject().autonomy_last_result == "message"
        assert "[main-chat initiative]" in model.contexts[0].task
        turns = soul.dialogue_history(Scope())
        assert len(turns) == 1
        assert [(message.role, message.content) for message in turns[0]] == [
            ("assistant", "今天我们可以接着把自主行为的节奏调舒服。")
        ]

        await soul.activities.idle()
        assert model.calls == 1

    async with SoulService(Settings(data_dir=tmp_path), model=InitiativeModel()) as restarted:
        await restarted.activities.idle()
        assert restarted.model.calls == 0


@pytest.mark.parametrize("gate", ["disabled", "quiet", "fatigue", "budget"])
async def test_autonomous_chat_respects_runtime_gates(tmp_path, gate):
    model = InitiativeModel()
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        state = soul.store.load_subject()
        state.autonomy_enabled = gate != "disabled"
        state.next_initiative_at = now() - timedelta(seconds=1)
        if gate == "disabled":
            state.autonomy_enabled = False
        elif gate == "quiet":
            state.mode = "quiet"
        elif gate == "fatigue":
            state.fatigue = 0.95
        else:
            state.tokens_used = soul.settings.token_budget
        soul.store.save_transition(state.dispatch_epoch, state)

        await soul.activities.idle()

        assert model.calls == 0
        assert not [
            item for item in soul.status()["interactions"] if item["choice"] == "initiative"
        ]


async def test_owner_input_interrupts_initiative_without_a_late_message(tmp_path):
    import asyncio

    entered, release = asyncio.Event(), asyncio.Event()

    class DelayedInitiativeModel(InitiativeModel):
        async def decide(self, context, limits):
            self.calls += 1
            self.contexts.append(context.model_copy(deep=True))
            if "[main-chat initiative]" in context.task:
                entered.set()
                await release.wait()
                return ActivityDecision(
                    activity=Activity.CHAT,
                    chat_action="reply",
                    reply="这条过时的主动消息不应出现。",
                )
            return ActivityDecision(activity=Activity.REST)

    model = DelayedInitiativeModel()
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        state = soul.store.load_subject()
        state.autonomy_enabled = True
        state.next_initiative_at = now() - timedelta(seconds=1)
        soul.store.save_transition(state.dispatch_epoch, state)
        tick = asyncio.create_task(soul.activities.idle())
        await entered.wait()
        await soul.owner_message("先听我说")
        release.set()
        await tick
        assert not [
            item for item in soul.status()["interactions"] if item["choice"] == "initiative"
        ]
        assert soul.store.load_subject().autonomy_last_result == "interrupted"


async def test_initiative_honors_an_unrevoked_owner_followup_request(tmp_path):
    class ContinuingRequestModel(InitiativeModel):
        async def decide(self, context, limits):
            self.calls += 1
            self.contexts.append(context.model_copy(deep=True))
            if "[main-chat initiative]" not in context.task:
                return ActivityDecision(activity=Activity.REST)
            has_followup = any(
                message.role == "user" and "除非我叫停" in message.content
                for message in context.history
            )
            if has_followup and "仍然有效的持续请求" in context.instructions:
                return ActivityDecision(
                    activity=Activity.CHAT,
                    chat_action="reply",
                    reply="林先生把那枚青铜齿轮放到灯下，发现齿背刻着一行细字……",
                )
            return ActivityDecision(activity=Activity.REST)

    model = ContinuingRequestModel()
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        owner_request = Event(
            source="local-owner",
            sender="owner",
            content="接着写这个故事，除非我叫停，否则之后继续写。",
            trust="owner_command",
            dedup_key="owner-followup-request",
        )
        soul.store.add_event(owner_request)
        prior_reply = {
            "choice": "owner_served",
            "event_id": owner_request.id,
            "activity": Activity.CHAT,
            "text": "我会在之后继续写。",
            "input": owner_request.content,
        }
        soul.store.record_interaction(
            owner_request,
            prior_reply,
            soul._assistant_evidence(owner_request, prior_reply),
            enqueue=False,
        )
        state = soul.store.load_subject()
        state.autonomy_enabled = True
        state.next_initiative_at = now() - timedelta(seconds=1)
        soul.store.save_transition(state.dispatch_epoch, state)

        await soul.activities.idle()

        messages = [
            item for item in soul.status()["interactions"] if item["choice"] == "initiative"
        ]
        assert len(messages) == 1
        assert "青铜齿轮" in messages[0]["text"]
        assert soul.store.load_subject().autonomy_last_result == "message"


@pytest.mark.parametrize("change", ["disable", "quiet_mode"])
async def test_runtime_pause_during_a_check_suppresses_its_reply(tmp_path, change):
    import asyncio

    entered, release = asyncio.Event(), asyncio.Event()

    class DelayedInitiativeModel(InitiativeModel):
        async def decide(self, context, limits):
            self.calls += 1
            self.contexts.append(context.model_copy(deep=True))
            if "[main-chat initiative]" in context.task:
                entered.set()
                await release.wait()
                return ActivityDecision(
                    activity=Activity.CHAT,
                    chat_action="reply",
                    reply="关闭后不应显示这条主动消息。",
                )
            return ActivityDecision(activity=Activity.REST)

    model = DelayedInitiativeModel()
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        state = soul.store.load_subject()
        state.autonomy_enabled = True
        state.next_initiative_at = now() - timedelta(seconds=1)
        soul.store.save_transition(state.dispatch_epoch, state)
        tick = asyncio.create_task(soul.activities.idle())
        await entered.wait()

        state = soul.store.load_subject()
        if change == "disable":
            state.autonomy_enabled = False
        else:
            state.mode = "quiet"
        soul.store.save_transition(state.dispatch_epoch, state)
        release.set()
        await tick

        assert not [
            item for item in soul.status()["interactions"] if item["choice"] == "initiative"
        ]
        assert soul.store.load_subject().autonomy_last_result == "paused"


async def test_three_minute_heartbeat_repeats_through_ticks_and_restart(tmp_path, monkeypatch):
    instant = now()
    monkeypatch.setattr("mysoul.autonomy.now", lambda: instant)
    model = InitiativeModel()
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        soul.life.clock = lambda: instant
        state = soul.store.load_subject()
        state.autonomy_enabled = True
        state.autonomy_interval_minutes = 3
        state.next_initiative_at = instant
        soul.store.save_transition(state.dispatch_epoch, state)
        await soul.tick()
        assert model.calls == 1
        assert soul.store.load_subject().next_initiative_at == instant + timedelta(minutes=3)
        instant += timedelta(seconds=179)
        await soul.tick()
        assert model.calls == 1
        instant += timedelta(seconds=1)
        await soul.tick()
        assert model.calls == 2

    restarted_model = InitiativeModel()
    async with SoulService(Settings(data_dir=tmp_path), model=restarted_model) as soul:
        soul.life.clock = lambda: instant
        await soul.tick()
        assert restarted_model.calls == 0
        instant += timedelta(minutes=3)
        await soul.tick()
        assert restarted_model.calls == 1
        messages = [i for i in soul.status()["interactions"] if i["choice"] == "initiative"]
        assert len(messages) == 3


async def test_previously_considered_maintenance_does_not_starve_due_heartbeat(tmp_path):
    from mysoul.domain import Evidence

    model = InitiativeModel()
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        evidence = Evidence(text="A remembered detail.")
        soul.store.add_evidence(evidence)
        soul.recap.enqueue(evidence.id)
        state = soul.store.load_subject()
        state.autonomy_enabled = True
        state.next_initiative_at = now() - timedelta(seconds=1)
        soul.store.save_transition(state.dispatch_epoch, state)
        await soul.tick()  # New maintenance has priority; the model elects to rest.
        assert model.calls == 1
        assert soul.recap.pending()
        await soul.tick()  # Unchanged maintenance must not consume every later idle tick.
        assert model.calls == 2
        assert soul.store.load_subject().autonomy_last_result == "message"
        await soul.tick()
        assert model.calls == 2
