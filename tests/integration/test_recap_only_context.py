import pytest

from mysoul.config import Settings
from mysoul.domain import ActivityDecision, Evidence, Scope
from mysoul.service import SoulService


class EmptyRecall:
    async def search(self, query, scope, limit):
        return []


async def test_new_turn_uses_recap_without_previous_raw_context(tmp_path):
    seen = []

    class Model:
        async def decide(self, context, limits):
            seen.append(context.model_copy(deep=True))
            return ActivityDecision(activity="read_chat", reply="OLD_REPLY_CANARY" * 1500)

    async with SoulService(Settings(data_dir=tmp_path, context_chars=8192), Model()) as soul:
        soul.memory = EmptyRecall()
        await soul.owner_message("OLD_INPUT_CANARY")
        soul.recap.publish(0, "CURRENT_RECAP", [])
        result = await soul.owner_message("NEW_INPUT")
        assert not result.get("error")
        assert seen[-1].task == "NEW_INPUT"
        assert seen[-1].recap == "CURRENT_RECAP"
        assert "OLD_INPUT_CANARY" not in seen[-1].payload()
        assert "OLD_REPLY_CANARY" not in seen[-1].payload()
        assert not seen[-1].history and not seen[-1].archives
        assert soul.cognition.sources.pending_window(4000) is not None


async def test_old_unfinished_input_does_not_block_new_turn(tmp_path):
    from mysoul.domain import Event

    async with SoulService(Settings(data_dir=tmp_path, context_chars=8192)) as soul:
        soul.memory = EmptyRecall()
        soul.store.add_event(Event(content="OLD_PENDING" * 2000, dedup_key="old"))
        context = await soul.context(Scope(), "CURRENT_INPUT")
        assert "OLD_PENDING" not in context.payload()
        assert context.task == "CURRENT_INPUT"


async def test_recall_remains_optional_bounded_and_scoped(tmp_path):
    class Recall:
        async def search(self, query, scope, limit):
            assert query == "current query"
            return [Evidence(id="hit", text="RECALLED_FACT"),
                    Evidence(id="large", text="X" * 10000)]

    async with SoulService(Settings(data_dir=tmp_path, context_chars=8192)) as soul:
        soul.memory = Recall()
        context = await soul.context(Scope(), "current query")
        assert not context.evidence
        from mysoul.recall import admit_result

        found = await soul.memory_tools.call("memory_search", {"query": "current query"}, Scope())
        evidence = admit_result(context, found, "memory_search", "recall:test", 8192)
        assert evidence is not None and "RECALLED_FACT" in evidence.text
        context.step_results.append(evidence)
        assert len(context.payload()) <= 8192


async def test_real_required_overflow_preserves_input_without_model_call(tmp_path):
    class Model:
        async def decide(self, *args):
            raise AssertionError("Overflow must not call model")

    async with SoulService(Settings(data_dir=tmp_path, context_chars=4096), Model()) as soul:
        soul.memory = EmptyRecall()
        text = "CURRENT_INPUT" * 1000
        result = await soul.owner_message(text)
        assert result["error"]["code"] == "context_budget"
        assert result["input"] == text
        assert soul.store.evidence(result["event_id"]).text == text


async def test_tool_results_stay_in_activity_and_do_not_enter_next_turn(tmp_path):
    from mysoul.domain import Goal, StepDecision

    class Model:
        steps = 0

        async def execute_step(self, context, tools, limits):
            self.steps += 1
            if self.steps == 1:
                return StepDecision(
                    tool="write_file", arguments={"path": "result.txt", "text": "TOOL_SECRET"}
                )
            if self.steps == 2:
                return StepDecision(tool="read_file", arguments={"path": "result.txt"})
            assert any(e.text == "TOOL_SECRET" for e in context.step_results)
            return StepDecision(done=True, note="completed")

        async def decide(self, context, limits):
            assert not context.step_results
            assert "TOOL_SECRET" not in context.payload()
            return ActivityDecision(activity="read_chat", reply="ok")

    async with SoulService(Settings(data_dir=tmp_path), Model()) as soul:
        soul.memory = EmptyRecall()
        activity = await soul.start_goal(Goal(objective="Run current tool sequence"))
        assert activity.status == "completed"
        assert soul.store.get("activity_context", activity.id)["step_results"]
        assert (await soul.owner_message("new turn"))["text"] == "ok"


async def test_recap_overflow_is_still_enforced(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path, context_chars=4096)) as soul:
        soul.memory = EmptyRecall()
        soul.recap.publish(0, "R" * 5000, [])
        result = await soul.owner_message("small current input")
        assert result["error"]["code"] == "context_budget"
        assert "Recap" in result["text"]
        assert soul.recap.current().text == "R" * 5000


@pytest.mark.parametrize("existing_goal", [False, True])
async def test_current_owner_input_survives_handoff_to_work(tmp_path, existing_goal):
    from mysoul.domain import Goal, StepDecision

    text = "A" * 8100 + "CURRENT_ROUND_TAIL"

    class Model:
        async def decide(self, context, limits):
            return ActivityDecision(activity="work", goal_id="existing" if existing_goal else None)

        async def execute_step(self, context, tools, limits):
            assert "CURRENT_ROUND_TAIL" in context.task
            return StepDecision(done=True, note="done")

    async with SoulService(Settings(data_dir=tmp_path), Model()) as soul:
        soul.memory = EmptyRecall()
        if existing_goal:
            soul.store.save_goal(Goal(id="existing", objective="Previous pending goal"))
        await soul.owner_message(text)
        assert soul.store.all("activity")[0]["status"] == "completed"
