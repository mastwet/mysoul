"""One persistent owner stream across work, initiative, compaction and restart."""

from mysoul.archives import CompressionPolicy
from mysoul.config import Settings
from mysoul.domain import Activity, ActivityDecision, Goal, Scope, StepDecision
from mysoul.model import ReplayModel
from mysoul.service import SoulService
from mysoul.timeline import TimelineStore


class UnifiedModel(ReplayModel):
    async def decide(self, context, limits):
        return ActivityDecision(
            activity=Activity.CHAT,
            chat_action="reply",
            reply="A concrete shared thought"
            if "[main-chat initiative]" in context.task
            else "Owner reply retained",
        )

    async def execute_step(self, context, tools, limits):
        if "[archive-compression]" in context.instructions:
            self.calls += 1
            return StepDecision(
                done=True,
                note=(
                    "History includes owner requests, verified report and cancellation. "
                    "Preserve these commitments."
                ),
            )
        return await super().execute_step(context, tools, limits)


async def test_unified_chat_archives_restart_and_original_expansion(tmp_path):
    settings = Settings(data_dir=tmp_path, token_budget=None)
    async with SoulService(settings, UnifiedModel()) as soul:
        for n in range(32):
            await soul.owner_message(f"Owner request {n}, keep its original evidence and context.")
        state = soul.store.load_subject()
        state.autonomy_enabled = True
        soul.store.save_transition(state.dispatch_epoch, state)
        assert await soul.activities._main_chat_initiative()
        soul.model.steps.extend(
            [
                StepDecision(
                    tool="write_file", arguments={"path": "report.txt", "text": "VERIFIED_RESULT"}
                ),
                StepDecision(tool="read_file", arguments={"path": "report.txt"}),
                StepDecision(done=True, note="Verified report"),
            ]
        )
        activity = await soul.start_goal(Goal(id="report", objective="Write and verify report"))
        assert activity.status == "completed"
        soul.model.steps.append(StepDecision(tool="read_file", arguments={"path": "missing.txt"}))
        paused = await soul.start_goal(Goal(id="cancelled", objective="Read missing file"))
        assert paused.status == "suspended"
        soul.executor.cancel("cancelled")
        before = TimelineStore(soul.store).page(limit=100)
        assert len([i for i in before.items if i.id == "task:report"]) == 1
        assert any(
            i.body.get("choice") == "initiative" and i.body.get("input") == "" for i in before.items
        )
        sources = len(soul.store.all("cognitive_source"))
        persona = soul.persona.current().version
        soul.compression.set_policy(CompressionPolicy(raw_trigger=10, raw_batch=4))
        for _ in range(15):
            result = await soul.compression.run_due(force=True)
            if result is None:
                break
            assert result.status == "completed", result.error
        frontier = soul.compression.archives.frontier(Scope())
        assert any(n.level == 2 for n in frontier)
        assert len(soul.store.all("cognitive_source")) == sources
        assert soul.persona.current().version == persona
        ids = [i.id for i in before.items]
        ranges = [seq for n in frontier for seq in range(n.first_seq, n.last_seq + 1)]
        assert ranges == [i.seq for i in before.items]
    async with SoulService(settings, UnifiedModel()) as soul:
        assert [i.id for i in TimelineStore(soul.store).page(limit=100).items] == ids
        assert soul.store.goal("cancelled").cancelled
        context = await soul.context(Scope(), "Continue")
        assert "VERIFIED_RESULT" in context.payload()
        archive = next(n for n in soul.compression.archives.frontier(Scope()) if n.level == 2)
        page = soul.compression.archives.expand(archive.id, Scope(), limit=100)
        assert [i["seq"] for i in page["items"]] == list(
            range(archive.first_seq, archive.last_seq + 1)
        )
        assert "Owner request 0" in page["items"][0]["body"]["input"]
        assert all(n.scope == Scope() for n in soul.compression.archives.frontier(Scope()))
