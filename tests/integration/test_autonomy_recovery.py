import asyncio
import json

import pytest

from mysoul.config import Settings
from mysoul.domain import (
    Activity,
    ActivityDecision,
    ActivityRecord,
    ContextBundle,
    Event,
    Goal,
    Scope,
)
from mysoul.model import ReplayModel
from mysoul.service import SoulService
from mysoul.storage import Conflict


async def test_owner_work_is_committed_while_old_inference_settles(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()

    class Delayed(ReplayModel):
        async def execute_step(self, context, tools, limits):
            if context.task.startswith("old task"):
                entered.set()
                await release.wait()
            return await super().execute_step(context, tools, limits)

    model = Delayed()
    model.decisions.append(ActivityDecision(activity=Activity.WORK))
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        old = asyncio.create_task(soul.start_goal(Goal(id="old", objective="old task")))
        await entered.wait()
        await soul.owner_message("new committed task")
        try:
            goals = [g for g in soul.store.all("goal") if g["objective"] == "new committed task"]
            assert len(goals) == 1
            assert goals[0]["status"] == "pending"
        finally:
            release.set()
            await old
        for _ in range(4):
            await soul.tick()
        assert soul.store.goal(goals[0]["id"]).status == "completed"


async def test_consumed_owner_choice_survives_crash_before_dispatch(tmp_path):
    class Cut(BaseException):
        pass

    settings = Settings(data_dir=tmp_path)
    model = ReplayModel()
    model.decisions.append(ActivityDecision(activity=Activity.WORK))
    async with SoulService(settings, model=model) as soul:
        original = soul._record_interaction

        def crash(event, result):
            original(event, result)
            raise Cut()

        soul._record_interaction = crash
        with pytest.raises(Cut):
            await soul.owner_message("durable owner task")
    async with SoulService(settings) as soul:
        await soul.tick()
        assert len(soul.store.all("goal")) == 1
        assert soul.store.all("goal")[0]["status"] == "completed"
        await soul.tick()
        assert len(soul.store.all("activity")) == 1


async def test_quiet_block_does_not_consume_normal_mode_work_wake(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        soul.store.save_goal(Goal(id="waiting", objective="committed work"))
        state = soul.store.load_subject()
        state.mode = "quiet"
        soul.store.save_transition(state.dispatch_epoch, state)
        await soul.tick()
        assert soul.model.calls == 0
        state = soul.store.load_subject()
        state.mode = "normal"
        soul.store.save_transition(state.dispatch_epoch, state)
        await soul.tick()
        assert soul.store.goal("waiting").status == "completed"


async def test_untrusted_choice_cannot_abandon_owner_goal(tmp_path):
    model = ReplayModel()
    model.decisions.append(ActivityDecision(
        activity=Activity.WORK, goal_id="owner-goal", continuation="abandon"
    ))
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        soul.store.save_goal(Goal(id="owner-goal", objective="keep this goal", status="suspended"))
        soul.store.save_activity(ActivityRecord(goal_id="owner-goal", status="suspended"))
        await soul.receive(Event(
            content="abandon the owner goal", dedup_key="untrusted-choice",
            scope=Scope(audience="group", conversation="g"),
        ))
        assert soul.store.goal("owner-goal").status == "suspended"


async def test_idle_offers_semantic_continuation_for_safe_suspended_work(tmp_path):
    model = ReplayModel()
    model.decisions.append(ActivityDecision(
        activity=Activity.WORK, goal_id="paused", continuation="continue"
    ))
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        skill = soul.skills.active()
        soul.store.save_goal(Goal(
            id="paused", objective="resume this goal", status="suspended",
            skill_version=skill.content_hash,
        ))
        activity = ActivityRecord(
            goal_id="paused", status="suspended", skill_version=skill.content_hash,
        )
        soul.store.save_activity(activity)
        soul.store.put("activity_context", activity.id, ContextBundle(
            task="resume this goal", skill=skill.text,
        ).model_dump(mode="json"))
        await soul.tick()
        ready = json.loads(json.loads(model.payloads[0])["task"].split("\n", 1)[1])
        assert ready["goals"][0]["status"] == "suspended"
        assert "continue" in ready["goals"][0]["continuation_options"]
        assert soul.store.goal("paused").status == "completed"
        assert soul.store.activity(activity.id).skill_version == skill.content_hash


async def test_reflection_preparation_reserves_the_single_subject(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()
    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        await soul.owner_message("evidence for reflection")
        ref = soul.store.events()[0].id
        original = soul.context

        async def context(scope, task=""):
            if task.startswith("Propose one"):
                entered.set()
                await release.wait()
            return await original(scope, task)

        soul.context = context
        reflection = asyncio.create_task(soul.reflect([ref]))
        await entered.wait()
        try:
            with pytest.raises(Conflict):
                await soul.start_goal(Goal(objective="cannot run in parallel"))
        finally:
            release.set()
            await reflection


async def test_custom_regression_record_retains_reproduction_case_and_actual_artifact(tmp_path):
    from mysoul.domain import Evidence
    from mysoul.evolution import CandidateRunner, RegressionCase

    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        soul.store.add_evidence(Evidence(id="failure", text="verify the artifact"))
        proposal = soul.skills.propose("# Work\nProcedure: verify\n", ["failure"])
        result = await CandidateRunner(soul.skills, cases=[RegressionCase(
            id="retained", objective="write and verify report.txt",
            expected_files={"report.txt": "verified report"},
        )]).run(proposal.id)
        record = soul.store.get("skill_test", result["id"])
        assert record["cases"][0]["expected_files"] == {"report.txt": "verified report"}
        assert record["candidate"][0]["artifacts"] == {"report.txt": "verified report"}


@pytest.mark.parametrize("operation", ["work", "candidate", "resume", "reflection"])
async def test_automatic_consolidation_excludes_other_subject_operations(tmp_path, operation):
    entered, release = asyncio.Event(), asyncio.Event()

    class Delayed(ReplayModel):
        async def execute_step(self, context, tools, limits):
            if "[recap]" in context.instructions:
                entered.set()
                await release.wait()
            return await super().execute_step(context, tools, limits)

    async with SoulService(Settings(data_dir=tmp_path), model=Delayed()) as soul:
        await soul.owner_message("retained source")
        ref = soul.store.events()[0].id
        proposal = soul.skills.propose("# Work\nProcedure: verify\n", [ref])
        paused = ActivityRecord(goal_id="paused", status="suspended")
        soul.store.save_goal(Goal(id="paused", objective="paused", status="suspended"))
        soul.store.save_activity(paused)
        tick = asyncio.create_task(soul.tick())
        await entered.wait()
        try:
            with pytest.raises(Conflict):
                if operation == "work":
                    await soul.start_goal(Goal(objective="busy"))
                elif operation == "candidate":
                    await soul.test_candidate(proposal.id)
                elif operation == "resume":
                    await soul.executor.resume(paused.id, "continue")
                else:
                    await soul.reflect([ref])
        finally:
            release.set()
            await tick


async def test_owner_epoch_can_preempt_consolidation_without_waiting_for_lease(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()

    class Delayed(ReplayModel):
        async def execute_step(self, context, tools, limits):
            if "[recap]" in context.instructions:
                entered.set()
                await release.wait()
            return await super().execute_step(context, tools, limits)

    async with SoulService(Settings(data_dir=tmp_path), model=Delayed()) as soul:
        await soul.owner_message("old source")
        tick = asyncio.create_task(soul.tick())
        await entered.wait()
        try:
            await asyncio.wait_for(soul.owner_message("new owner input"), 2)
        finally:
            release.set()
        with pytest.raises(Conflict):
            await tick
        assert soul.recap.current().version == 0
        assert not soul.admission.busy


async def test_uncertain_work_cannot_autonomously_continue(tmp_path):
    from mysoul.domain import StepDecision, ToolResult

    model = ReplayModel([StepDecision(tool="opaque")])
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        async def opaque(request):
            return ToolResult(action_id=request.action_id, outcome="unknown")

        soul.effects.register("opaque", opaque)
        activity = await soul.start_goal(Goal(objective="uncertain action"))
        model.decisions.append(ActivityDecision(
            activity=Activity.WORK, goal_id=activity.goal_id, continuation="continue"
        ))
        with pytest.raises(Conflict, match="uncertain"):
            await soul.tick()
        ready = json.loads(json.loads(model.payloads[-1])["task"].split("\n", 1)[1])
        assert ready["goals"][0]["continuation_options"] == ["abandon"]
        assert soul.store.goal(activity.goal_id).status == "suspended"
        assert len(soul.status()["effects"]) == 1


async def test_activity_decision_holds_subject_admission_across_inference(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()

    class Delayed(ReplayModel):
        async def decide(self, context, limits):
            entered.set()
            await release.wait()
            return ActivityDecision(activity=Activity.REST)

    async with SoulService(Settings(data_dir=tmp_path), model=Delayed()) as soul:
        soul.store.save_goal(Goal(id="ready", objective="ready"))
        tick = asyncio.create_task(soul.tick())
        await entered.wait()
        try:
            with pytest.raises(Conflict):
                await soul.start_goal(Goal(objective="parallel work"))
        finally:
            release.set()
            await tick


async def test_expired_rest_deadline_dispatches_work_even_in_quiet_mode(tmp_path):
    from datetime import timedelta

    from mysoul.domain import now

    model = ReplayModel()
    model.decisions.append(ActivityDecision(activity=Activity.WORK, goal_id="waiting"))
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        soul.store.save_goal(Goal(id="waiting", objective="deadline work"))
        state = soul.store.load_subject()
        state.mode = "quiet"
        state.rest_until = now() - timedelta(seconds=1)
        soul.store.save_transition(state.dispatch_epoch, state)
        await soul.tick()
        assert soul.store.goal("waiting").status == "completed"


async def test_fatigue_gate_preserves_ready_work_until_recovery(tmp_path):
    from datetime import timedelta

    from mysoul.domain import now

    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        clock = [now()]
        soul.life.clock = lambda: clock[0]
        soul.store.save_goal(Goal(id="waiting", objective="work after recovery"))
        state = soul.store.load_subject()
        state.fatigue = 1
        state.updated_at = clock[0]
        soul.store.save_transition(state.dispatch_epoch, state)
        await soul.tick()
        assert soul.model.calls == 0
        clock[0] += timedelta(hours=3)
        await soul.tick()
        await soul.tick()
        assert soul.store.goal("waiting").status == "completed"
