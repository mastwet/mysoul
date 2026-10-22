from datetime import timedelta

import pytest

from mysoul.config import Settings
from mysoul.domain import Activity, ActivityDecision, Scope, now
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
