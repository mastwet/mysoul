from datetime import UTC, datetime, timedelta

import pytest

from mysoul.config import Settings
from mysoul.domain import ActivityDecision, Event, Goal, Scope
from mysoul.model import ReplayModel
from mysoul.service import SoulService


@pytest.fixture
async def soul(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path), model=ReplayModel()) as soul:
        state = soul.store.load_subject()
        state.autonomy_enabled = True
        state.autonomy_interval_minutes = 3
        soul.store.save_transition(state.dispatch_epoch, state)
        assert getattr(soul, "wakeups", None) is not None, "Durable wakeup tool is missing"
        yield soul


def schedule(soul, delay=600, reason="休息后重新决定活动", call_id="test:1", **extra):
    return soul.wakeups.schedule(
        {"after_seconds": delay, "reason": reason, **extra},
        call_id=call_id,
        epoch=soul.store.load_subject().dispatch_epoch,
        scope=Scope(),
    )


async def test_tool_replaces_next_wake_and_replay_does_not_extend_it(soul):
    instant = datetime(2026, 10, 24, 0, 0, tzinfo=UTC)
    soul.life.clock = lambda: instant
    first = schedule(soul)
    assert first["status"] == "scheduled"
    assert soul.store.load_subject().next_initiative_at == instant + timedelta(seconds=600)
    second = schedule(soul, delay=60, call_id="test:2")
    assert second["status"] == "scheduled"
    assert soul.wakeups.pending()["id"] == second["ref"]
    assert soul.store.get("scheduled_wakeup", first["ref"])["status"] == "replaced"
    assert schedule(soul) == first
    assert soul.wakeups.pending()["id"] == second["ref"]
    assert soul.store.load_subject().next_initiative_at == instant + timedelta(seconds=60)


async def test_tool_checks_arguments_scope_epoch_and_autonomy(soul):
    for delay in (0, 29, 86401):
        assert schedule(soul, delay=delay)["status"] == "invalid_arguments"
    assert schedule(soul, reason="")["status"] == "invalid_arguments"
    assert (
        soul.wakeups.schedule(
            {"after_seconds": 60, "reason": "x"},
            call_id="x",
            epoch=0,
            scope=Scope(audience="group", conversation="g"),
        )["status"]
        == "denied"
    )
    soul.store.interrupt()
    assert (
        soul.wakeups.schedule(
            {"after_seconds": 60, "reason": "x"}, call_id="x", epoch=0, scope=Scope()
        )["status"]
        == "interrupted"
    )
    state = soul.store.load_subject()
    state.autonomy_enabled = False
    soul.store.save_transition(state.dispatch_epoch, state)
    assert schedule(soul)["status"] == "disabled"
    assert soul.wakeups.pending() is None


async def test_future_wake_has_no_model_poll_and_due_reason_reaches_same_subject(soul):
    instant = datetime(2026, 10, 24, 0, 0, tzinfo=UTC)
    soul.life.clock = lambda: instant
    schedule(soul, reason="恢复我的自由探索")
    contexts = []

    async def decide(context, limits):
        contexts.append(context.model_copy(deep=True))
        return ActivityDecision(activity="rest", rationale="安静看看")

    soul.model.decide = decide
    for _ in range(4):
        await soul.activities.idle()
    assert contexts == []
    instant += timedelta(seconds=600)
    assert await soul.activities._main_chat_initiative()
    assert len(contexts) == 1
    assert "恢复我的自由探索" in contexts[0].payload()
    assert contexts[0].persona_version == soul.persona.current().version
    assert soul.wakeups.pending() is None
    assert not await soul.activities._main_chat_initiative()
    assert len(contexts) == 1


async def test_due_wake_waits_for_owner_and_survives_ordinary_interruption(soul):
    instant = datetime(2026, 10, 24, 0, 0, tzinfo=UTC)
    soul.life.clock = lambda: instant
    result = schedule(soul, delay=30)
    soul.store.interrupt()
    instant += timedelta(seconds=30)
    soul.owner_turns = 1
    assert not await soul.activities._main_chat_initiative()
    assert soul.wakeups.pending()["id"] == result["ref"]
    soul.owner_turns = 0
    assert await soul.activities._main_chat_initiative()
    assert soul.store.get("scheduled_wakeup", result["ref"])["status"] == "fired"


async def test_cancelled_goal_disable_and_conversation_reset_cancel_schedule(soul):
    from mysoul.conversation import ConversationStore

    goal = Goal(objective="稍后继续", lane="background")
    soul.store.save_goal(goal)
    result = schedule(soul, goal_id=goal.id)
    soul.executor.cancel(goal.id)
    assert soul.wakeups.pending() is None
    assert soul.store.get("scheduled_wakeup", result["ref"])["status"] == "cancelled"
    result = schedule(soul, call_id="reset")
    ConversationStore(soul.store).reset(0)
    assert soul.wakeups.pending() is None
    assert soul.store.get("scheduled_wakeup", result["ref"])["status"] == "cancelled"
    result = schedule(soul, call_id="disable")
    state = soul.store.load_subject()
    state.autonomy_enabled = False
    soul.store.save_transition(state.dispatch_epoch, state)
    assert soul.wakeups.pending() is None
    assert soul.store.get("scheduled_wakeup", result["ref"])["status"] == "cancelled"


async def test_owner_can_request_tool_and_answer_from_its_receipt(soul):
    calls = []

    async def decide(context, limits):
        calls.append(context.model_copy(deep=True))
        if not context.step_results:
            return ActivityDecision.model_validate(
                {
                    "activity": "rest",
                    "runtime_call": {
                        "tool": "schedule_wakeup",
                        "arguments": {"after_seconds": 900, "reason": "稍后继续"},
                    },
                }
            )
        return ActivityDecision(activity="read_chat", chat_action="reply", reply="我安排好了。")

    soul.model.decide = decide
    result = await soul.owner_message("你可以晚点再醒来")
    assert result.get("error") is None
    assert len(calls) == 2
    assert soul.wakeups.pending()["reason"] == "稍后继续"
    assert calls[1].step_results[-1].source == "schedule_wakeup"
    assert "scheduled" in calls[1].step_results[-1].text
    assert not any("scheduled" in s.get("text", "") for s in soul.store.all("cognitive_source"))


async def test_restart_retains_pending_and_interrupts_started_wakes(tmp_path):
    settings = Settings(data_dir=tmp_path)
    async with SoulService(settings, model=ReplayModel()) as soul:
        assert getattr(soul, "wakeups", None) is not None
        state = soul.store.load_subject()
        state.autonomy_enabled = True
        soul.store.save_transition(state.dispatch_epoch, state)
        first = schedule(soul)
    async with SoulService(settings, model=ReplayModel()) as soul:
        assert soul.wakeups.pending()["id"] == first["ref"]
        raw = soul.store.get("scheduled_wakeup", first["ref"])
        raw.update(status="running", event_id="old-check")
        soul.store.put("scheduled_wakeup", raw["id"], raw)
    async with SoulService(settings, model=ReplayModel()) as soul:
        assert soul.wakeups.pending() is None
        assert soul.store.get("scheduled_wakeup", first["ref"])["status"] == "interrupted"


async def test_executor_uses_same_tool_without_archiving_receipts(soul):
    import json

    from mysoul.domain import StepDecision

    seen = []

    async def step(context, tools, limits):
        seen.append(tools)
        if not context.step_results:
            return StepDecision(
                tool="schedule_wakeup",
                arguments={"after_seconds": 300, "reason": "TASK_SCHEDULE_RECEIPT"},
                note="安排继续",
            )
        return StepDecision(done=True, note="完成安排")

    soul.model.execute_step = step
    goal = Goal(objective="安排稍后再醒来", step_limit=3)
    activity = await soul.start_goal(goal)
    assert activity.status == "completed"
    assert any(tool["name"] == "schedule_wakeup" for tool in seen[0])
    assert soul.wakeups.pending()["reason"] == "TASK_SCHEDULE_RECEIPT"
    sources = soul.store.all("cognitive_source")
    evidence = [soul.store.evidence(source["id"]).text for source in sources]
    assert "TASK_SCHEDULE_RECEIPT" not in json.dumps(evidence)
    requests = soul.store.effects_for_goal(goal.id, "schedule_wakeup")
    assert len(requests) == 1
    request, result = requests[0]
    assert (await soul.effects.dispatch(request)).content == result.content
    assert len(soul.store.all("scheduled_wakeup")) == 1


async def test_tool_is_denied_to_untrusted_owner_source_and_group(soul):
    contexts = []

    async def decide(context, limits):
        contexts.append(context.model_copy(deep=True))
        if not context.step_results:
            return ActivityDecision.model_validate(
                {
                    "activity": "rest",
                    "runtime_call": {
                        "tool": "schedule_wakeup",
                        "arguments": {"after_seconds": 60, "reason": "forged"},
                    },
                }
            )
        return ActivityDecision(activity="rest")

    soul.model.decide = decide
    event = Event(source="local-owner", content="untrusted", dedup_key="forged", trust="data")
    await soul.receive(event)
    assert soul.wakeups.pending() is None
    assert "denied" in contexts[-1].step_results[-1].text


async def test_pending_wake_not_consumed_by_budget_or_mode_gates(soul):
    instant = datetime(2026, 10, 24, 0, 0, tzinfo=UTC)
    soul.life.clock = lambda: instant
    schedule(soul, delay=30)
    instant += timedelta(seconds=30)
    soul.settings.model_call_limit = 0
    assert not await soul.activities._main_chat_initiative()
    assert soul.wakeups.pending()
    soul.settings.model_call_limit = 100
    state = soul.store.load_subject()
    state.mode = "quiet"
    soul.store.save_transition(state.dispatch_epoch, state)
    assert not await soul.activities._main_chat_initiative()
    assert soul.wakeups.pending()


async def test_scheduling_during_initiative_keeps_custom_time(soul):
    instant = datetime(2026, 10, 24, 0, 0, tzinfo=UTC)
    soul.life.clock = lambda: instant
    state = soul.store.load_subject()
    state.next_initiative_at = instant
    soul.store.save_transition(state.dispatch_epoch, state)

    async def decide(context, limits):
        if not context.step_results:
            return ActivityDecision.model_validate(
                {
                    "activity": "rest",
                    "runtime_call": {
                        "tool": "schedule_wakeup",
                        "arguments": {"after_seconds": 1200, "reason": "自由休息"},
                    },
                }
            )
        return ActivityDecision(activity="rest")

    soul.model.decide = decide
    assert await soul.activities._main_chat_initiative()
    assert soul.store.load_subject().next_initiative_at == instant + timedelta(seconds=1200)
    assert len(soul.store.all("scheduled_wakeup")) == 1


async def test_insufficient_receipt_space_prevents_schedule_mutation(soul):
    result = soul.wakeups.schedule(
        {"after_seconds": 60, "reason": "x"},
        call_id="context",
        epoch=0,
        scope=Scope(),
        accept=lambda result: False,
    )
    assert result["status"] == "context_budget"
    assert soul.wakeups.pending() is None


def test_life_interval_changes_preserve_schedule_and_disable_cancels(tmp_path):
    from fastapi.testclient import TestClient

    from mysoul.api import create_app

    service = SoulService(Settings(data_dir=tmp_path, port=8765), model=ReplayModel())
    with TestClient(
        create_app(service.settings, service=service, token="wake-test"),
        base_url="http://127.0.0.1:8765",
    ) as client:
        client.headers["Authorization"] = "Bearer wake-test"
        client.headers.update(
            {
                "Origin": "http://127.0.0.1:8765",
                "X-CSRF-Token": client.get("/api/session").json()["csrf"],
            }
        )
        body = {"mode": "normal", "fatigue": 0, "autonomy_enabled": True}
        assert client.post("/api/life", json=body).status_code == 200
        first = schedule(service)
        response = client.post("/api/life", json=body | {"autonomy_interval_minutes": 240})
        assert response.status_code == 200
        assert response.json()["next_initiative_at"] == first["due_at"].replace("+00:00", "Z")
        page = client.get("/api/inner-voice?category=schedule").json()
        assert page["items"][0]["status"] == "scheduled"
        assert page["wakeup"]["pending"]["reason"] == "休息后重新决定活动"
        response = client.post("/api/life", json=body | {"autonomy_enabled": False})
        assert response.status_code == 200
        assert response.json()["next_initiative_at"] is None
        assert (
            client.get("/api/inner-voice?category=schedule").json()["items"][0]["status"]
            == "cancelled"
        )


async def test_candidate_schedule_attempt_cannot_change_production_schedule(soul):
    from mysoul.domain import StepDecision
    from mysoul.evolution import CandidateRunner, RegressionCase

    first = schedule(soul, delay=600)

    class Candidate(ReplayModel):
        async def execute_step(self, context, tools, limits):
            return StepDecision(
                tool="schedule_wakeup", arguments={"after_seconds": 30, "reason": "candidate"}
            )

    runner = CandidateRunner(soul.skills, model_factory=Candidate)
    skill = soul.skills.active()
    result = await runner._trial(
        skill.text,
        skill.content_hash,
        RegressionCase(id="isolated", objective="test", expected_files={"report.txt": "ok"}),
        None,
    )
    assert not result["objective_pass"]
    assert soul.wakeups.pending()["id"] == first["ref"]


async def test_unaffordable_inference_does_not_consume_due_wake(soul):
    instant = datetime(2026, 10, 24, 0, 0, tzinfo=UTC)
    soul.life.clock = lambda: instant
    receipt = schedule(soul, delay=30)
    instant += timedelta(seconds=30)
    soul.settings.token_budget = 1
    await soul.activities._main_chat_initiative()
    assert soul.model.calls == 0
    assert soul.wakeups.pending()["id"] == receipt["ref"]
    assert soul.store.load_subject().next_initiative_at == instant
    soul.settings.token_budget = None
    assert await soul.activities._main_chat_initiative()
    assert soul.model.calls == 1
    assert soul.wakeups.pending() is None


async def test_restart_restores_unstarted_due_wake_and_reuses_event(tmp_path):
    settings = Settings(data_dir=tmp_path)
    instant = datetime(2026, 10, 24, 0, 0, tzinfo=UTC)
    async with SoulService(settings, model=ReplayModel()) as soul:
        soul.life.clock = lambda: instant
        state = soul.store.load_subject()
        state.autonomy_enabled = True
        soul.store.save_transition(state.dispatch_epoch, state)
        receipt = schedule(soul, delay=30)
        instant += timedelta(seconds=30)
        state = soul.store.load_subject()
        state.next_initiative_at = instant + timedelta(hours=6)
        soul.store.save_transition(state.dispatch_epoch, state)
        event = Event(source="local-initiative", sender="mysoul", content="",
                      dedup_key="initiative:" + instant.isoformat())
        soul.store.add_event(event)
    async with SoulService(settings, model=ReplayModel()) as soul:
        soul.life.clock = lambda: instant
        assert soul.store.load_subject().next_initiative_at == instant
        assert await soul.activities._main_chat_initiative()
        raw = soul.store.get("scheduled_wakeup", receipt["ref"])
        assert raw["status"] == "fired"
        assert raw["event_id"] == event.id


async def test_executor_receipt_admission_precedes_schedule_mutation(soul):
    import json

    from mysoul.domain import ContextBundle, ToolRequest, now

    soul.settings.context_chars = 4096
    goal = Goal(objective="capacity", status="active")
    soul.store.save_goal(goal)
    context = ContextBundle(scope=Scope(), task="capacity")
    context.instructions = "x" * (4096 - len(context.payload()) - 20)
    soul.store.put("activity_context", "cramped", context.model_dump(mode="json"))
    result = await soul._schedule_wakeup(ToolRequest(
        activity_id="cramped", goal_id=goal.id, epoch=0, tool="schedule_wakeup",
        arguments={"after_seconds": 60, "reason": "x" * 300},
        deadline=now()+timedelta(seconds=30),
    ))
    assert json.loads(result.content)["status"] == "context_budget"
    assert soul.wakeups.pending() is None


async def test_cancel_while_context_builds_prevents_model_admission(soul):
    instant = datetime(2026, 10, 24, 0, 0, tzinfo=UTC)
    soul.life.clock = lambda: instant
    goal = Goal(objective="cancel before admission", lane="background")
    soul.store.save_goal(goal)
    receipt = schedule(soul, delay=30, goal_id=goal.id)
    instant += timedelta(seconds=30)
    original = soul.context

    async def context(*args, **kwargs):
        result = await original(*args, **kwargs)
        soul.executor.cancel(goal.id)
        return result

    soul.context = context
    await soul.activities._main_chat_initiative()
    assert soul.store.get("scheduled_wakeup", receipt["ref"])["status"] == "cancelled"
    assert soul.model.calls == 0
    assert soul.store.load_subject().tokens_used == 0
    assert not soul.store.all("interaction")


async def test_cancel_during_wake_inference_prevents_tool_and_publication(soul):
    instant = datetime(2026, 10, 24, 0, 0, tzinfo=UTC)
    soul.life.clock = lambda: instant
    goal = Goal(objective="cancel during inference", lane="background")
    soul.store.save_goal(goal)
    receipt = schedule(soul, delay=30, goal_id=goal.id)
    instant += timedelta(seconds=30)
    calls = []

    async def decide(context, limits):
        calls.append(context)
        soul.executor.cancel(goal.id)
        return ActivityDecision(activity="read_chat", chat_action="reply", reply="晚到的回复")

    soul.model.decide = decide
    await soul.activities._main_chat_initiative()
    assert len(calls) == 1
    assert not soul.store.all("interaction")
    assert soul.store.get("scheduled_wakeup", receipt["ref"])["status"] == "interrupted"
