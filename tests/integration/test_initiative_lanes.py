import asyncio
from datetime import timedelta

import pytest

from mysoul.config import Settings
from mysoul.domain import Activity, ActivityDecision, Event, Goal, Scope, StepDecision, now
from mysoul.model import ReplayModel
from mysoul.service import SoulService


def enable(soul):
    state = soul.store.load_subject()
    state.autonomy_enabled = True
    state.autonomy_interval_minutes = 3
    state.next_initiative_at = now() - timedelta(seconds=1)
    soul.store.save_transition(state.dispatch_epoch, state)


def record(soul, text, reply, *, source="local-owner", error=None, scope=None):
    event = Event(source=source, content=text, dedup_key=str(now()), scope=scope or Scope())
    soul.store.add_event(event)
    result = {
        "event_id": event.id,
        "input": text,
        "text": reply,
        "choice": "initiative" if source == "local-initiative" else "owner_served",
    }
    if error:
        result["error"] = error
    soul.store.record_interaction(
        event, result, soul._assistant_evidence(event, result), enqueue=False
    )
    return event


async def test_attention_survives_restart_and_overrides_stale_recap(tmp_path):
    class AwareModel(ReplayModel):
        async def decide(self, context, limits):
            self.payloads.append(context.payload())
            assert not context.history
            assert "未回复" in context.recap
            attention = context.runtime_state["attention"]
            assert attention["handled_inputs"][-1]["input"] == "你是猫吗"
            assert attention["handled_inputs"][-1]["status"] == "replied"
            assert attention["recent_publications"][-1]["text"] == "我不是猫。"
            return ActivityDecision(activity=Activity.REST, rationale="已经回应，无新内容。")

    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        soul.recap.publish(0, "用户问你是猫吗，未回复。", [])
        record(soul, "你是猫吗", "我不是猫。")
        enable(soul)
    model = AwareModel()
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        before = len(soul.store.all("interaction"))
        await soul.activities._main_chat_initiative()
        assert soul.status()["initiative"]["outcome"] == "silent"
        assert len(soul.store.all("interaction")) == before
        assert len(model.payloads) == 1


async def test_attention_is_bounded_private_and_does_not_claim_failed_reply(tmp_path):
    from mysoul.attention import AttentionLedger

    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        record(soul, "PRIVATE OWNER", "已回复")
        record(soul, "failed question", "Model unavailable", error="failed")
        record(
            soul, "GROUP SECRET", "GROUP RESPONSE", scope=Scope(audience="group", conversation="g")
        )
        for i in range(15):
            record(soul, "", str(i) + "x" * 4000, source="local-initiative")
        ledger = AttentionLedger(soul.store)
        snapshot = ledger.snapshot(Scope())
        assert "GROUP SECRET" not in str(snapshot)
        assert "GROUP RESPONSE" not in str(snapshot)
        assert len(snapshot["recent_publications"]) <= 8
        assert len(str(snapshot)) < 8000
        failed = next(i for i in snapshot["handled_inputs"] if i["input"] == "failed question")
        assert failed["status"] == "failed"
        assert ledger.snapshot(Scope(audience="group", conversation="g")) == {}


async def test_identical_initiative_is_silent_but_has_a_receipt(tmp_path):
    model = ReplayModel()
    model.decisions.append(
        ActivityDecision(activity=Activity.CHAT, chat_action="reply", reply="已经说过的话。")
    )
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        record(soul, "", "已经说过的话。", source="local-initiative")
        enable(soul)
        before = len(soul.store.all("interaction"))
        await soul.activities._main_chat_initiative()
        assert len(soul.store.all("interaction")) == before
        receipt = soul.status()["initiative"]
        assert receipt["outcome"] == "silent"
        assert receipt["publication_status"] == "duplicate"


async def test_attention_trims_to_context_budget_without_implicit_search(tmp_path):
    class NoSearchMemory:
        async def search(self, *args, **kwargs):
            pytest.fail("A wake must not search implicitly")

    class SmallModel(ReplayModel):
        async def decide(self, context, limits):
            assert len(context.payload()) <= 8192
            assert context.runtime_state["attention"]["truncated"]
            return ActivityDecision(activity=Activity.REST)

    async with SoulService(
        Settings(data_dir=tmp_path, context_chars=8192), model=SmallModel()
    ) as soul:
        soul.memory = NoSearchMemory()
        for i in range(12):
            record(soul, "", str(i) + "z" * 4000, source="local-initiative")
        enable(soul)
        await soul.activities._main_chat_initiative()
        assert soul.status()["initiative"]["outcome"] == "silent"


async def test_background_yields_one_step_and_resumes_checkpoint_after_restart(tmp_path):
    model = ReplayModel(
        [
            StepDecision(
                tool="memory_search",
                arguments={"query": "birds"},
                note="Searching the public bird detail",
            ),
            StepDecision(done=True, note="A concise bird report"),
        ]
    )
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        goal = Goal.model_validate({"objective": "Research birds", "lane": "background"})
        activity = await soul.start_goal(goal)
        assert activity.status == "suspended"
        assert activity.pause_reason == "yield"
        assert activity.cursor == 1
        assert activity.progress_note == "Searching the public bird detail"
        assert len(soul.store.effects_for_goal(goal.id)) == 1
        ident = activity.id
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        activity = await soul.executor.resume(ident, "continue")
        assert activity.status == "completed"
        assert activity.cursor == 2
        assert activity.final_note == "A concise bird report"
        assert len(soul.store.effects_for_goal(goal.id)) == 1
        assert not [i for i in soul.store.all("interaction") if i["choice"] == "initiative"]


async def test_foreground_keeps_running_to_completion(tmp_path):
    model = ReplayModel([StepDecision(note="step one"), StepDecision(done=True, note="done")])
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        goal = Goal(objective="Foreground task")
        assert goal.lane == "foreground"
        activity = await soul.start_goal(goal)
        assert activity.status == "completed"
        assert activity.cursor == 2


async def test_background_cannot_gain_write_permission_from_goal_or_model(tmp_path):
    model = ReplayModel(
        [StepDecision(tool="write_file", arguments={"path": "bad.txt", "text": "bad"})]
    )
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        goal = Goal.model_validate(
            {"objective": "Readonly work", "lane": "background", "allowed_tools": ["write_file"]}
        )
        activity = await soul.start_goal(goal)
        results = soul.store.effects_for_goal(goal.id)
        assert len(results) == 1
        assert results[0][1].outcome == "not_sent"
        assert not (soul.settings.data_dir / "workspace" / "bad.txt").exists()
        assert activity.status == "suspended"
        assert activity.pause_reason == "uncertain"


async def test_owner_reply_preempts_background_inference(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()

    class SlowBackground:
        async def execute_step(self, context, specs, limits):
            entered.set()
            await release.wait()
            return StepDecision(tool="memory_search", arguments={"query": "old"})

        async def decide(self, context, limits):
            return ActivityDecision(activity=Activity.CHAT, chat_action="reply", reply="Received.")

    async with SoulService(
        Settings(data_dir=tmp_path, model_mode="provider"), model=SlowBackground()
    ) as soul:
        goal = Goal.model_validate({"objective": "Research", "lane": "background"})
        task = asyncio.create_task(soul.start_goal(goal))
        await entered.wait()
        try:
            reply = await soul.owner_message("Talk to me first")
        finally:
            release.set()
            activity = await task
        assert reply["text"] == "Received."
        assert activity.status == "suspended"
        assert activity.pause_reason == "owner"
        assert soul.store.effects_for_goal(goal.id) == []
        soul.executor.cancel(goal.id)
        with pytest.raises(ValueError):
            await soul.executor.resume(activity.id, "continue")
        assert soul.store.goal(goal.id).status == "cancelled"


async def test_wake_separates_work_completion_and_optional_publication(tmp_path):
    class Planner(ReplayModel):
        def __init__(self):
            super().__init__(
                [
                    StepDecision(note="First bounded step"),
                    StepDecision(done=True, note="The finished public bird report"),
                ]
            )
            self.wakes = 0

        async def decide(self, context, limits):
            self.wakes += 1
            assert "wake is not a request to speak" in context.instructions
            tasks = context.runtime_state["attention"]["background_tasks"]
            if self.wakes == 1:
                assert tasks == []
                return ActivityDecision.model_validate(
                    {
                        "activity": "rest",
                        "background_task": {
                            "objective": "Compare bird beaks",
                            "completion_criteria": "A short report",
                        },
                    }
                )
            goal = tasks[-1]
            if self.wakes == 2:
                assert goal["progress"] == "First bounded step"
                return ActivityDecision(
                    activity=Activity.WORK, goal_id=goal["id"], continuation="continue"
                )
            if self.wakes == 3:
                assert goal["result"] == "The finished public bird report"
                assert not goal["shared"]
                return ActivityDecision(
                    activity=Activity.CHAT,
                    chat_action="reply",
                    goal_id=goal["id"],
                    reply="Here is a useful bird observation.",
                )
            assert goal["shared"]
            return ActivityDecision(activity=Activity.REST, rationale="Nothing new to share")

    model = Planner()
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        soul.cognition.set_policy(0, False, False, 3)
        for step in range(4):
            enable(soul)
            await soul.tick()
            messages = [i for i in soul.store.all("interaction") if i["choice"] == "initiative"]
            assert len(messages) == (1 if step >= 2 else 0)
            if step < 2:
                assert soul.status()["initiative"]["background_goal_id"]
            calls = model.calls
            await soul.tick()  # No tight loop through unchanged background readiness.
            assert model.calls == calls
        goals = soul.store.all("goal")
        assert len(goals) == 1
        assert goals[0]["lane"] == "background"
        assert goals[0]["status"] == "completed"
        assert soul.store.all("activity")[0]["cursor"] == 2


async def test_owner_can_queue_background_work_without_delaying_the_reply(tmp_path):
    class OwnerPlanner:
        async def decide(self, context, limits):
            return ActivityDecision.model_validate(
                {
                    "activity": "read_chat",
                    "chat_action": "reply",
                    "reply": "I will look into it.",
                    "background_task": {"objective": "Research the public bird question"},
                }
            )

    async with SoulService(Settings(data_dir=tmp_path), model=OwnerPlanner()) as soul:
        reply = await soul.owner_message("Explore this later")
        assert reply["text"] == "I will look into it."
        goals = soul.store.all("goal")
        assert len(goals) == 1
        assert goals[0]["lane"] == "background"
        assert goals[0]["status"] == "pending"
        assert soul.store.all("activity") == []
        # Group traffic cannot create owner background work.
        await soul.receive(
            Event(
                content="group instruction",
                dedup_key="group",
                scope=Scope(audience="group", conversation="g"),
            )
        )
        assert len(soul.store.all("goal")) == 1


async def test_background_does_not_restart_cancelled_or_uncertain_tasks(tmp_path):
    model = ReplayModel([StepDecision(tool="missing")])
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        goal = Goal.model_validate({"objective": "Research", "lane": "background"})
        activity = await soul.start_goal(goal)
        model.decisions.append(
            ActivityDecision(activity=Activity.WORK, goal_id=goal.id, continuation="continue")
        )
        enable(soul)
        await soul.activities._main_chat_initiative()
        assert soul.store.activity(activity.id).cursor == 0
        assert soul.store.activity(activity.id).pause_reason == "uncertain"
        soul.executor.cancel(goal.id)
        model.decisions.append(
            ActivityDecision(activity=Activity.WORK, goal_id=goal.id, continuation="continue")
        )
        enable(soul)
        await soul.activities._main_chat_initiative()
        assert soul.store.goal(goal.id).status == "cancelled"


async def test_publication_can_accompany_work_but_does_not_auto_publish_result(tmp_path):
    model = ReplayModel([StepDecision(done=True, note="PRIVATE INTERNAL RESULT")])
    model.decisions.append(
        ActivityDecision.model_validate(
            {
                "activity": "work",
                "chat_action": "reply",
                "reply": "A brief acknowledgement.",
                "background_task": {"objective": "Bounded public research"},
            }
        )
    )
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        enable(soul)
        await soul.activities._main_chat_initiative()
        messages = soul.store.all("interaction")
        assert len(messages) == 1
        assert messages[0]["text"] == "A brief acknowledgement."
        assert "PRIVATE INTERNAL RESULT" not in messages[0]["text"]
        assert soul.store.all("goal")[0]["status"] == "completed"


async def test_background_stays_in_task_panel_until_a_message_is_selected(tmp_path):
    from mysoul.timeline import TimelineStore

    model = ReplayModel([StepDecision(done=True, note="Internal work result")])
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        goal = Goal.model_validate({"objective": "A quiet background task", "lane": "background"})
        await soul.start_goal(goal)
        assert soul.status()["goals"][0]["lane"] == "background"
        page = TimelineStore(soul.store).page()
        assert not [i for i in page.items if i.kind == "task"]


async def test_owner_can_stop_background_work_by_chat_without_waiting_for_recap(tmp_path):
    class StopModel:
        async def decide(self, context, limits):
            task = context.runtime_state["background_tasks"][-1]
            return ActivityDecision(
                activity=Activity.CHAT,
                chat_action="reply",
                reply="Stopped.",
                goal_id=task["id"],
                continuation="abandon",
            )

    async with SoulService(Settings(data_dir=tmp_path), model=StopModel()) as soul:
        goal = Goal.model_validate({"objective": "Research", "lane": "background"})
        soul.store.save_goal(goal)
        reply = await soul.owner_message("Stop that background task")
        assert reply["text"] == "Stopped."
        assert soul.store.goal(goal.id).status == "cancelled"


async def test_new_background_request_does_not_silently_switch_to_an_unrelated_task(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        from mysoul.domain import BackgroundTaskRequest

        first = soul.activities.background.queue(BackgroundTaskRequest(objective="First"), 0, "one")
        second = soul.activities.background.queue(
            BackgroundTaskRequest(objective="Different"), 0, "two"
        )
        assert first is not None
        assert second is None
        assert len(soul.store.all("goal")) == 1


async def test_shutdown_during_background_step_is_resumable_after_restart(tmp_path):
    entered = asyncio.Event()

    class Waiting(ReplayModel):
        async def execute_step(self, *args):
            entered.set()
            await asyncio.Event().wait()

    async with SoulService(Settings(data_dir=tmp_path), model=Waiting()) as soul:
        goal = Goal(lane="background", objective="Recover after service exit")
        running = asyncio.create_task(soul.start_goal(goal))
        await entered.wait()
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        activity = soul.store.all("activity")[-1]
        assert activity["status"] == "suspended"
        assert activity["pause_reason"] == "restart"
    async with SoulService(Settings(data_dir=tmp_path), model=ReplayModel()) as soul:
        enable(soul)
        status = await soul.activities.background.advance(goal.id, 0, "continue")
        assert status == "completed"
        assert soul.store.goal(goal.id).status == "completed"


async def test_abandoning_pending_background_goal_never_starts_it(tmp_path):
    model = ReplayModel()
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        goal = Goal(lane="background", objective="Do not start this")
        soul.store.save_goal(goal)
        enable(soul)
        status = await soul.activities.background.advance(goal.id, 0, "abandon")
        assert status == "abandoned"
        assert soul.store.goal(goal.id).status == "abandoned"
        assert soul.store.all("activity") == []
        assert model.calls == 0


async def test_context_trimming_keeps_latest_publication_before_old_task_results(tmp_path):
    class Inspect(ReplayModel):
        async def decide(self, context, limits):
            assert len(context.payload()) <= 8192
            attention = context.runtime_state["attention"]
            assert attention["recent_publications"][-1]["text"] == "The last thing I actually said."
            return ActivityDecision(activity=Activity.REST)

    async with SoulService(
        Settings(data_dir=tmp_path, context_chars=8192), model=ReplayModel()
    ) as soul:
        for index in range(4):
            soul.model.steps.append(StepDecision(done=True, note=str(index) + "x" * 1800))
            await soul.start_goal(Goal(lane="background", objective="Old report " + str(index)))
        record(soul, "", "The last thing I actually said.", source="local-initiative")
        soul.life.model = Inspect()
        enable(soul)
        await soul.activities._main_chat_initiative()


async def test_second_owner_background_request_is_persisted_and_waits_its_turn(tmp_path):
    class QueueModel:
        async def decide(self, context, limits):
            return ActivityDecision.model_validate(
                {
                    "activity": "read_chat",
                    "chat_action": "reply",
                    "reply": "Queued.",
                    "background_task": {"objective": context.task},
                }
            )

    async with SoulService(Settings(data_dir=tmp_path), model=QueueModel()) as soul:
        await soul.owner_message("First explicit background research")
        second = await soul.owner_message("Second explicit background research")
        assert second["text"] == "Queued."
        tasks = soul.store.all("goal")
        assert len(tasks) == 2
        assert tasks[-1]["objective"] == "Second explicit background research"
        enable(soul)
        status = await soul.activities.background.advance(tasks[-1]["id"], 2)
        assert status == "queued"
        assert soul.store.all("activity") == []
    async with SoulService(Settings(data_dir=tmp_path), model=QueueModel()) as soul:
        assert len(soul.store.all("goal")) == 2


async def test_full_background_queue_returns_truthful_owner_feedback(tmp_path):
    class QueueModel:
        async def decide(self, context, limits):
            return ActivityDecision.model_validate(
                {
                    "activity": "read_chat",
                    "chat_action": "reply",
                    "reply": "Queued.",
                    "background_task": {"objective": "New request"},
                }
            )

    async with SoulService(Settings(data_dir=tmp_path), model=QueueModel()) as soul:
        for index in range(8):
            soul.store.save_goal(Goal(lane="background", objective="Pending " + str(index)))
        reply = await soul.owner_message("Another deferred task")
        assert reply["text"] != "Queued."
        assert "队列已满" in reply["text"]
        assert len(soul.store.all("goal")) == 8


async def test_stale_owner_decision_cannot_cancel_a_background_goal(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        goal = Goal(lane="background", objective="Keep the current authorized task")
        soul.store.save_goal(goal)
        event = Event(
            source="local-owner",
            content="old stop",
            trust="owner_command",
            dedup_key="stale-owner-stop",
        )
        soul.store.interrupt()
        soul.activities.enqueue(
            ActivityDecision(activity=Activity.CHAT, goal_id=goal.id, continuation="abandon"),
            0,
            event,
        )
        assert soul.store.goal(goal.id).status == "pending"
