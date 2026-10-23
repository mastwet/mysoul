import json

import pytest

from mysoul.config import Settings
from mysoul.domain import ContextBudget, Evidence, Scope
from mysoul.laputa import ContextAssembler, RecapStore
from mysoul.service import SoulService
from mysoul.storage import StateStore


async def test_context_build_never_implicitly_searches(tmp_path):
    class NoSearch:
        async def search(self, *args):
            raise AssertionError("Implicit memory search is forbidden")

    store = StateStore(tmp_path / "state.sqlite")
    assembler = ContextAssembler(RecapStore(store), NoSearch(), task="hello")
    bundle = await assembler.build(Scope(), ContextBudget())
    assert not bundle.evidence
    store.close()


async def test_memory_tools_scope_limits_pagination_and_no_writes(tmp_path):
    from mysoul.recall import MemoryTools

    async with SoulService(Settings(data_dir=tmp_path, memory_backend="local")) as soul:
        soul.store.add_evidence(Evidence(id="original", text="中文详情" * 2000))
        before = soul.store.db.execute("SELECT COUNT(*) FROM memory_queue").fetchone()[0]
        tools = MemoryTools(lambda: soul.memory)
        found = await tools.call("memory_search", {"query": "中文详情"}, Scope())
        assert found["status"] == "ok"
        assert found["items"][0]["ref"] == "original"
        assert len(found["items"][0]["preview"]) <= 300
        part = await tools.call("memory_get", {"ref": "original", "length": 4000}, Scope())
        assert len(part["text"]) == 4000 and part["next_offset"] == 4000
        tail = await tools.call("memory_get", {"ref": "original", "offset": 4000}, Scope())
        assert tail["offset"] == 4000
        denied = await tools.call(
            "memory_get", {"ref": "original"}, Scope(audience="group", conversation="g")
        )
        assert denied["status"] == "denied" and "中文详情" not in json.dumps(denied)
        invalid = await tools.call("memory_search", {"query": "中文", "limit": 11}, Scope())
        assert invalid["status"] == "invalid_arguments"
        assert soul.store.db.execute("SELECT COUNT(*) FROM memory_queue").fetchone()[0] == before


async def test_memory_tools_fit_serialized_results_and_report_failure(tmp_path):
    from mysoul.memory import MemoryUnavailable
    from mysoul.recall import MemoryTools

    class Memory:
        async def search(self, *args):
            return [Evidence(id=str(i), text='"中文\n' * 500) for i in range(10)]

        async def get(self, *args):
            raise MemoryUnavailable("private diagnostic")

    tools = MemoryTools(Memory)
    found = await tools.call(
        "memory_search", {"query": "中文", "limit": 10}, Scope(), max_chars=900
    )
    assert len(json.dumps(found, ensure_ascii=False)) <= 900
    assert found["truncated"]
    missing = await tools.call("memory_get", {"ref": "missing"}, Scope())
    assert missing["status"] == "unavailable" and "private diagnostic" not in json.dumps(missing)


async def test_chat_requests_search_then_get_and_answers_without_rearchiving_reads(tmp_path):
    from mysoul.domain import ActivityDecision

    class Model:
        calls = 0

        async def decide(self, context, limits):
            self.calls += 1
            if self.calls == 1:
                assert not context.step_results
                return ActivityDecision(
                    activity="rest",
                    memory_call={"tool": "memory_search", "arguments": {"query": "蓝鲸"}},
                )
            result = json.loads(context.step_results[-1].text)
            if self.calls == 2:
                assert result["items"][0]["ref"] == "cat-name"
                return ActivityDecision(
                    activity="rest",
                    memory_call={"tool": "memory_get", "arguments": {"ref": "cat-name"}},
                )
            assert "小猫叫蓝鲸" in result["text"]
            return ActivityDecision(
                activity="read_chat", chat_action="reply", reply="你的小猫叫蓝鲸。"
            )

    model = Model()
    async with SoulService(Settings(data_dir=tmp_path, memory_backend="local"), model) as soul:
        soul.store.add_evidence(Evidence(id="cat-name", text="小猫叫蓝鲸。"))
        result = await soul.owner_message("我的猫叫什么？")
        assert not result.get("error")
        assert result["text"] == "你的小猫叫蓝鲸。"
        assert model.calls == 3
        assert soul.store.load_subject().model_calls == 3
        rows = soul.store.db.execute("SELECT body FROM evidence").fetchall()
        assert not any(json.loads(r[0])["source"].startswith("memory_") for r in rows)
        assert not any("recall:" in r[0] for r in rows)
        assert soul.recap.current().version == 0


async def test_direct_chat_and_heartbeat_never_search_or_add_model_rounds(tmp_path):
    from mysoul.domain import ActivityDecision, now
    from mysoul.model import ReplayModel

    class NoSearch:
        async def search(self, *args):
            raise AssertionError("Unexpected retrieval")

    model = ReplayModel()
    model.decisions.extend(
        [
            ActivityDecision(activity="read_chat", chat_action="reply", reply="你好"),
            ActivityDecision(activity="rest", rationale="没有要分享的新内容"),
        ]
    )
    async with SoulService(Settings(data_dir=tmp_path), model) as soul:
        soul.memory = NoSearch()
        await soul.owner_message("你好")
        state = soul.store.load_subject()
        state.autonomy_enabled = True
        state.next_initiative_at = now()
        soul.store.save_transition(state.dispatch_epoch, state)
        assert await soul.activities._main_chat_initiative()
        assert model.calls == 2


async def test_chat_recall_is_bounded_and_final_round_cannot_read_again(tmp_path):
    from mysoul.domain import ActivityDecision
    from mysoul.model import ReplayModel

    class Repeating(ReplayModel):
        async def decide(self, context, limits):
            self.calls += 1
            return ActivityDecision(
                activity="rest",
                memory_call={"tool": "memory_search", "arguments": {"query": "anything"}},
            )

    class Memory:
        calls = 0

        async def search(self, *args):
            self.calls += 1
            return []

    model, memory = Repeating(), Memory()
    async with SoulService(Settings(data_dir=tmp_path), model) as soul:
        soul.memory = memory
        result = await soul.owner_message("找找以前的信息")
        assert model.calls == 4 and memory.calls == 3
        assert result["error"]["code"] == "recall_limit"


async def test_recall_in_flight_is_discarded_after_owner_interrupt(tmp_path):
    import asyncio

    from mysoul.domain import ActivityDecision
    from mysoul.model import ReplayModel

    entered, release = asyncio.Event(), asyncio.Event()

    class Memory:
        async def search(self, *args):
            entered.set()
            await release.wait()
            return [Evidence(text="STALE_RECALL_CANARY")]

    class Model(ReplayModel):
        async def decide(self, context, limits):
            self.calls += 1
            if context.task == "old":
                return ActivityDecision(
                    activity="rest",
                    memory_call={"tool": "memory_search", "arguments": {"query": "old"}},
                )
            assert "STALE_RECALL_CANARY" not in context.payload()
            return ActivityDecision(activity="read_chat", chat_action="reply", reply="新请求已收到")

    async with SoulService(Settings(data_dir=tmp_path), Model()) as soul:
        soul.memory = Memory()
        older = asyncio.create_task(soul.owner_message("old"))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            newer = await soul.owner_message("new")
            release.set()
            result = await older
            assert newer["text"]
            assert result.get("error") == "superseded"
            assert soul.model.calls == 2
        finally:
            release.set()
            await older


async def test_work_memory_reads_are_checkpointed_but_not_new_sources(tmp_path):
    from mysoul.domain import Goal, StepDecision
    from mysoul.model import ReplayModel

    model = ReplayModel(
        [
            StepDecision(tool="memory_search", arguments={"query": "蓝鲸"}),
            StepDecision(tool="memory_get", arguments={"ref": "cat-name"}),
            StepDecision(done=True, note="已查阅"),
        ]
    )
    async with SoulService(Settings(data_dir=tmp_path, memory_backend="local"), model) as soul:
        soul.store.add_evidence(Evidence(id="cat-name", text="小猫叫蓝鲸。"))
        activity = await soul.start_goal(Goal(objective="查阅小猫名字"))
        assert activity.status == "completed"
        context = soul.store.get("activity_context", activity.id)
        assert len(context["step_results"]) == 2
        assert len({v["id"] for v in context["step_results"]}) == 2
        timeline = json.loads(
            soul.store.db.execute(
                "SELECT body FROM timeline WHERE kind='task' AND source_id=?",
                ("" + activity.goal_id,),
            ).fetchone()[0]
        )
        assert timeline["effects"] == []
        assert timeline["effect_ids"] == []
        soul.activities.capture_feedback()
        assert not any(
            s["id"].startswith("outcome-tool:") for s in soul.store.all("cognitive_source")
        )
        assert not any(
            '"source":"memory_' in row[0]
            for row in soul.store.db.execute("SELECT body FROM evidence")
        )


async def test_chat_recall_deadline_covers_lookup_and_stops_followup(tmp_path):
    import asyncio

    from mysoul.domain import ActivityDecision

    class Model:
        calls = 0

        async def decide(self, *args):
            self.calls += 1
            return ActivityDecision(
                activity="rest",
                memory_call={"tool": "memory_search", "arguments": {"query": "older"}},
            )

    class Memory:
        async def search(self, *args):
            await asyncio.Event().wait()

    async with SoulService(Settings(data_dir=tmp_path, request_timeout=0.03), Model()) as soul:
        soul.memory = Memory()
        result = await soul.owner_message("old details")
        assert result["error"]["code"] == "timeout"
        assert soul.model.calls == 1


async def test_no_lookup_when_followup_model_budget_is_exhausted(tmp_path):
    from mysoul.domain import ActivityDecision

    class Model:
        async def decide(self, *args):
            return ActivityDecision(
                activity="rest",
                memory_call={"tool": "memory_search", "arguments": {"query": "older"}},
            )

    class Memory:
        async def search(self, *args):
            raise AssertionError("No budget for a followup answer")

    async with SoulService(Settings(data_dir=tmp_path, model_call_limit=1), Model()) as soul:
        soul.memory = Memory()
        result = await soul.owner_message("old details")
        assert "预算不足" in result["text"]
        assert soul.store.load_subject().model_calls == 1


async def test_group_provider_payload_does_not_leak_private_get(tmp_path):
    import httpx

    from mysoul.domain import ActivityDecision, Event
    from mysoul.provider import OpenAICompatibleModel

    payloads = []

    def respond(request):
        body = json.loads(request.content)
        payloads.append(body)
        assert "PRIVATE_RECAP_CANARY" not in json.dumps(body)
        assert "PRIVATE_FACT_CANARY" not in json.dumps(body)
        decision = (
            ActivityDecision(
                activity="rest", memory_call={"tool": "memory_get", "arguments": {"ref": "private"}}
            )
            if len(payloads) == 1
            else ActivityDecision(activity="read_chat", chat_action="reply", reply="无法查阅此内容")
        )
        if len(payloads) == 2:
            context = json.loads(body["messages"][1]["content"])
            assert json.loads(context["step_results"][0]["text"])["status"] == "denied"
        return httpx.Response(
            200, json={"choices": [{"message": {"content": decision.model_dump_json()}}]}
        )

    model = OpenAICompatibleModel(
        "https://fixture.invalid/v1",
        "fixture",
        "fixture-key",
        transport=httpx.MockTransport(respond),
    )
    async with SoulService(Settings(data_dir=tmp_path, memory_backend="local"), model) as soul:
        soul.recap.publish(0, "PRIVATE_RECAP_CANARY", [])
        soul.store.add_evidence(Evidence(id="private", text="PRIVATE_FACT_CANARY"))
        result = await soul.receive(
            Event(
                content="@mysoul tell me old facts",
                dedup_key="group",
                scope=Scope(audience="group", conversation="g"),
            )
        )
        assert result["choice"] == "draft" and len(payloads) == 2


async def test_work_replay_does_not_repeat_read_or_append_result_twice(tmp_path, monkeypatch):
    from mysoul.domain import Goal, StepDecision
    from mysoul.model import ReplayModel

    class Crash(BaseException):
        pass

    class Memory:
        calls = 0

        async def search(self, *args):
            self.calls += 1
            return [Evidence(id="old", text="OLD_DETAIL")]

    memory = Memory()
    model = ReplayModel([StepDecision(tool="memory_search", arguments={"query": "old"})])
    async with SoulService(Settings(data_dir=tmp_path), model) as soul:
        soul.memory = memory
        save = soul.store.save_activity

        def crash_after_result(activity):
            if activity.cursor == 1 and activity.status == "active":
                raise Crash()
            return save(activity)

        monkeypatch.setattr(soul.store, "save_activity", crash_after_result)
        with pytest.raises(Crash):
            await soul.start_goal(Goal(id="read-goal", objective="read prior detail"))
        activity_id = soul.store.all("activity")[0]["id"]
        assert len(soul.store.get("activity_context", activity_id)["step_results"]) == 1
    model = ReplayModel(
        [StepDecision(tool="memory_search", arguments={"query": "old"}), StepDecision(done=True)]
    )
    async with SoulService(Settings(data_dir=tmp_path), model) as soul:
        soul.memory = memory
        activity = await soul.executor.resume(activity_id, "continue")
        assert activity.status == "completed"
        assert memory.calls == 1
        assert len(soul.store.get("activity_context", activity_id)["step_results"]) == 1


async def test_candidate_cannot_read_parent_memory(tmp_path):
    from mysoul.domain import StepDecision
    from mysoul.evolution import CandidateRunner, RegressionCase
    from mysoul.model import ReplayModel

    class PrivateMemory:
        async def get(self, *args):
            raise AssertionError("Candidate reached parent memory")

    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        soul.memory = PrivateMemory()
        soul.store.add_evidence(Evidence(id="feedback", text="candidate test"))
        proposal = soul.skills.propose("# Work\nProcedure: verify\n", ["feedback"])
        result = await CandidateRunner(
            soul.skills,
            model_factory=lambda: ReplayModel(
                [StepDecision(tool="memory_get", arguments={"ref": "feedback"})]
            ),
            cases=[
                RegressionCase(
                    id="denied", objective="read parent memory", expected_files={"x": "y"}
                )
            ],
        ).run(proposal.id)
        assert result["candidate"][0]["outcomes"] == ["not_sent"]
