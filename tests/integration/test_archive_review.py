from mysoul.archives import CompressionPolicy
from mysoul.config import Settings
from mysoul.domain import ActivityRecord, Event, Goal, Scope, StepDecision
from mysoul.model import ReplayModel
from mysoul.service import SoulService
from tests.integration.test_compression import seed


async def test_pending_oldest_does_not_block_later_complete_window(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path), ReplayModel()) as soul:
        soul.store.add_event(
            Event(
                id="pending",
                dedup_key="pending",
                source="local-owner",
                trust="owner_command",
                content="unfinished",
            )
        )
        seed(soul, count=99)
        assert soul.compression.prepare() is None
        seed(soul, count=100)
        plan = soul.compression.prepare()
        assert plan is not None
        assert plan.first_seq == 2
        assert soul.compression.archives.node("leaf:1:1").active


async def test_archived_chat_is_not_reinjected_after_many_tasks(tmp_path):
    async with SoulService(
        Settings(data_dir=tmp_path),
        ReplayModel([StepDecision(done=True, note="ARCHIVED_CHAT_PERIOD")]),
    ) as soul:
        seed(soul, count=8)
        for n in range(8):
            goal = Goal(id=f"g{n}", objective="finished work", status="completed")
            soul.store.save_goal(goal)
            activity = ActivityRecord(
                id=f"a{n}", goal_id=goal.id, status="completed", final_note="verified"
            )
            soul.store.save_activity(activity)
            soul.store.put("activity_context", activity.id, {"scope": Scope().model_dump()})
        soul.compression.set_policy(CompressionPolicy(raw_trigger=10, raw_batch=8))
        run = await soul.compression.run_due(force=True)
        assert run.status == "completed"
        context = await soul.context(Scope())
        assert "ARCHIVED_CHAT_PERIOD" not in context.payload()
        assert not context.archives
        assert not context.history


async def test_fixed_recap_and_serialization_trigger_early_compression(tmp_path):
    async with SoulService(
        Settings(data_dir=tmp_path, context_chars=8192),
        ReplayModel([StepDecision(done=True, note="small")]),
    ) as soul:
        soul.recap.publish(0, "R" * 5500, [])
        seed(soul, count=12, size=10)
        plan = soul.compression.prepare()
        assert plan is not None
        run = await soul.compression.run_due(force=True)
        assert run.status == "completed"


async def test_restarted_unfinished_input_is_retained_without_automatic_injection(tmp_path):
    settings = Settings(data_dir=tmp_path)
    async with SoulService(settings, ReplayModel()) as soul:
        soul.store.add_event(
            Event(
                id="unfinished",
                dedup_key="unfinished",
                source="local-owner",
                trust="owner_command",
                content="UNFINISHED_ORCHID_REQUEST",
            )
        )
    async with SoulService(settings, ReplayModel()) as soul:
        context = await soul.context(Scope(), "new input")
        assert "UNFINISHED_ORCHID_REQUEST" not in context.payload()
        assert not context.archives
        assert soul.store.events()[0].content == "UNFINISHED_ORCHID_REQUEST"


async def test_query_can_recover_original_detail_omitted_by_summary(tmp_path):
    from mysoul.domain import Evidence

    async with SoulService(
        Settings(data_dir=tmp_path),
        ReplayModel([StepDecision(done=True, note="Early project discussions")]),
    ) as soul:
        event = Event(
            id="orchid",
            dedup_key="orchid",
            content="Project Orchid reference code BLUE-739, confirmed by owner.",
        )
        soul.store.add_event(event)
        soul.store.record_interaction(
            event,
            {
                "event_id": event.id,
                "input": event.content,
                "text": "Recorded",
                "choice": "owner_served",
            },
        )
        soul.store.add_evidence(Evidence(id=event.id, text=event.content, source="local-owner"))
        seed(soul, count=12)
        soul.compression.set_policy(CompressionPolicy(raw_trigger=10, raw_batch=4))
        run = await soul.compression.run_due(force=True)
        context = await soul.context(Scope(), "What was Project Orchid reference code?")
        assert "BLUE-739" not in context.payload()
        found = await soul.memory_tools.call("memory_search", {"query": "Project Orchid"}, Scope())
        assert any(item["ref"] == event.id for item in found["items"])
        original = await soul.memory_tools.call("memory_get", {"ref": event.id}, Scope())
        assert "BLUE-739" in original["text"]
        assert len(context.payload()) <= soul.settings.context_chars
        assert soul.compression.archives.node(run.node_id).text == "Early project discussions"
        assert not any(
            e.id == run.node_id for e in await soul.memory.search("Early project", Scope(), 10)
        )
        group = await soul.context(Scope(audience="group", conversation="g"), "Project Orchid")
        assert "BLUE-739" not in group.payload()


def test_explicit_zero_change_cursor_returns_all_changes_from_start(tmp_path):
    from mysoul.storage import StateStore
    from mysoul.timeline import TimelineStore
    from tests.integration.test_timeline import turn

    store = StateStore(tmp_path / "state.sqlite")
    try:
        timeline = TimelineStore(store)
        assert not timeline.page().items
        for n in range(150):
            turn(store, str(n))
        first = timeline.page(after_change=0, limit=100)
        assert first.items[0].seq == 1
        remaining = timeline.page(after_change=first.change_cursor, limit=100)
        assert len(first.items) + len(remaining.items) == 150
    finally:
        store.close()
