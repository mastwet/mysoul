from mysoul.config import Settings
from mysoul.domain import Goal, StepDecision, ToolRequest, ToolResult, now
from mysoul.effects import EffectDispatcher
from mysoul.executor import Executor
from mysoul.model import ReplayModel
from mysoul.storage import StateStore


async def test_checkpoint_restart_preserves_ledger(tmp_path):
    store = StateStore(tmp_path / "s.db")
    store.load_subject()
    goal = Goal(objective="persist")
    dispatcher = EffectDispatcher(store)
    executor = Executor(
        store, ReplayModel([StepDecision(done=True)]), dispatcher, tmp_path / "g.db", Settings()
    )
    await executor.open()
    activity = await executor.start(goal)
    assert (await executor.graph.aget_state({"configurable": {"thread_id": activity.id}})).values
    await executor.close()
    with store.transaction() as db:
        req = ToolRequest(
            action_id="lost",
            activity_id=activity.id,
            goal_id=goal.id,
            epoch=0,
            tool="x",
            deadline=now(),
        )
        result = ToolResult(action_id="lost", outcome="in_flight")
        db.execute(
            "INSERT INTO effects VALUES(?,?,?)",
            ("lost", req.model_dump_json(), result.model_dump_json()),
        )
    store.close()
    store = StateStore(tmp_path / "s.db")
    store.recover_effects()
    assert store.effect("lost").outcome == "unknown"
    assert store.goal(goal.id).status == "completed"
    store.close()
