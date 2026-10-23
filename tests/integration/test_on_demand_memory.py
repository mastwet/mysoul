import json

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
