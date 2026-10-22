import asyncio

import pytest

from mysoul.config import Settings
from mysoul.domain import Activity, ActivityDecision, Event, Goal, Scope, StepDecision
from mysoul.model import ReplayModel
from mysoul.service import SoulService


async def test_idle_dispatches_committed_goal_once_and_then_stays_quiet(tmp_path):
    model = ReplayModel([
        StepDecision(tool="write_file", arguments={"path": "result.txt", "text": "done"}),
        StepDecision(done=True),
    ])
    model.decisions.append(ActivityDecision(activity=Activity.WORK, goal_id="committed"))
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        soul.store.save_goal(Goal(id="committed", objective="Write result.txt"))
        await soul.tick()
        assert soul.files.read("result.txt") == "done"
        assert soul.store.goal("committed").status == "completed"
        # Retire feedback through the explicit reflection activity, then quiet ticks cost nothing.
        await soul.tick()
        calls = model.calls
        for _ in range(20):
            await soul.tick()
        assert model.calls == calls
        assert len(soul.store.all("activity")) == 1


async def test_owner_work_decision_executes_but_group_cannot_commit_new_goal(tmp_path):
    model = ReplayModel([StepDecision(done=True)])
    model.decisions.extend([ActivityDecision(activity=Activity.WORK)] * 2)
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        await soul.receive(Event(
            content="Write a file", dedup_key="untrusted",
            scope=Scope(audience="group", conversation="g"),
        ))
        assert not soul.store.all("goal")
        await soul.owner_message("Write a file")
        assert len(soul.store.all("goal")) == 1
        assert soul.store.all("goal")[0]["status"] == "completed"


async def test_failed_execution_becomes_durable_feedback_and_reviewable_proposal(tmp_path):
    model = ReplayModel([StepDecision(tool="read_file", arguments={"path": "missing.txt"})])
    settings = Settings(data_dir=tmp_path)
    async with SoulService(settings, model=model) as soul:
        activity = await soul.start_goal(Goal(objective="Read missing file"))
        assert activity.status == "suspended"
    async with SoulService(settings) as reopened:
        await reopened.tick()
        proposals = reopened.store.all("proposal")
        assert len(proposals) == 1
        assert proposals[0]["status"] == "proposed"
        evidence = reopened.store.evidence(proposals[0]["evidence_refs"][0])
        assert "missing.txt" in evidence.text
        assert "failed" in evidence.text
        # Proposal creation never activates a new skill.
        assert reopened.skills.active().content_hash == proposals[0]["base_hash"]
        calls = reopened.model.calls
        for _ in range(20):
            await reopened.tick()
        assert reopened.model.calls == calls


async def test_superseded_activity_choice_cannot_launch_work(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()

    class Delayed(ReplayModel):
        async def decide(self, context, limits):
            if context.task.startswith("[ready activities]"):
                entered.set()
                await release.wait()
                return ActivityDecision(activity=Activity.WORK, goal_id="waiting")
            return await super().decide(context, limits)

    async with SoulService(Settings(data_dir=tmp_path), model=Delayed()) as soul:
        soul.store.save_goal(Goal(id="waiting", objective="Never start stale work"))
        task = asyncio.create_task(soul.tick())
        await asyncio.wait_for(entered.wait(), 2)
        await soul.owner_message("stop for now")
        release.set()
        await task
        assert soul.store.goal("waiting").status == "pending"
        assert not soul.store.all("activity")


async def test_news_choice_runs_only_configured_read_tools(tmp_path):
    class NewsModel(ReplayModel):
        async def execute_step(self, context, tool_specs, limits):
            assert {tool["name"] for tool in tool_specs} == {"read_news"}
            return await super().execute_step(context, tool_specs, limits)

    model = NewsModel([StepDecision(
        tool="write_file", arguments={"path": "escaped.txt", "text": "denied"}
    )])
    model.decisions.append(ActivityDecision(activity=Activity.NEWS))
    async with SoulService(Settings(
        data_dir=tmp_path, news_sources={"https://example.com/feed"}
    ), model=model) as soul:
        await soul.receive(Event(content="read news", dedup_key="news"))
        effects = soul.status()["effects"]
        assert len(effects) == 1
        assert effects[0]["outcome"] == "not_sent"
        with pytest.raises(FileNotFoundError):
            soul.files.read("escaped.txt")


async def test_rest_choice_does_not_repoll_same_ready_work_after_restart(tmp_path):
    settings = Settings(data_dir=tmp_path)
    model = ReplayModel()
    model.decisions.append(ActivityDecision(activity=Activity.REST))
    async with SoulService(settings, model=model) as soul:
        soul.store.save_goal(Goal(id="waiting", objective="Wait"))
        await soul.tick()
        assert model.calls == 1
    async with SoulService(settings) as reopened:
        for _ in range(20):
            await reopened.tick()
        assert reopened.model.calls == 0
