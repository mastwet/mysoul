import pytest

from mysoul.domain import ContextBudget, Evidence, Scope
from mysoul.laputa import ContextAssembler, ContextOverflow, RecapStore
from mysoul.memory import FixtureMemory, MemoryUnavailable
from mysoul.storage import Conflict, StateStore


@pytest.fixture
def rig(tmp_path):
    store = StateStore(tmp_path / "s.db")
    recap = RecapStore(store)
    memory = FixtureMemory(store)
    assembler = ContextAssembler(recap, memory, task="current goal")
    yield store, recap, memory, assembler
    store.close()


def test_recap_stale_edit_conflicts(rig):
    _, recap, _, _ = rig
    recap.publish(0, "first", [])
    with pytest.raises(Conflict):
        recap.publish(0, "stale", [])
    assert recap.current().text == "first"


def test_failed_publish_keeps_source_context(rig):
    store, recap, _, _ = rig
    store.add_evidence(Evidence(id="raw", text="original"))
    with pytest.raises(KeyError):
        recap.publish(0, "summary", ["missing"])
    assert recap.current().version == 0
    assert store.evidence("raw").text == "original"


async def test_context_budget_preserves_required_state(rig):
    _, recap, _, assembler = rig
    recap.publish(0, "large" * 1000, [])
    with pytest.raises(ContextOverflow):
        await assembler.build(Scope(), ContextBudget(max_chars=500))
    assert recap.current().text.startswith("large")


async def test_group_context_excludes_private_sources(rig):
    _, recap, memory, assembler = rig
    recap.publish(0, "PRIVATE-CANARY", [])
    group = Scope(audience="group", conversation="g1")
    await memory.add(Evidence(text="public group fact", scope=group))
    await memory.add(Evidence(text="private evidence"))
    result = await assembler.build(group, ContextBudget())
    assert "public group fact" not in result.payload()
    from mysoul.recall import MemoryTools

    found = await MemoryTools(lambda: memory).call("memory_search", {"query": "fact"}, group)
    assert "public group fact" in str(found)
    assert "private evidence" not in str(found)
    assert "PRIVATE-CANARY" not in result.payload()
    assert "private evidence" not in result.payload()


async def test_private_recap_canary_absent_from_provider_payload_with_mixed_tags(rig):
    from mysoul.domain import ModelLimits
    from mysoul.model import ReplayModel

    _, recap, memory, assembler = rig
    group = Scope(audience="group", conversation="g1")
    recap.publish(0, "PRIVATE-CANARY", [])
    await memory.add(Evidence(text="MIXED-CANARY", scope=group, source_scopes=[Scope(), group]))
    model = ReplayModel()
    await model.decide(await assembler.build(group, ContextBudget()), ModelLimits())
    assert "CANARY" not in model.payloads[-1]


async def test_recap_clear_invalidates_summaries_but_keeps_raw_evidence(rig):
    store, recap, memory, assembler = rig
    await memory.add(Evidence(id="raw", text="retained"))
    recap.publish(0, "old recap", ["raw"])
    await assembler.build(Scope(), ContextBudget())
    cleared = recap.clear(1)
    assert cleared.text == "" and cleared.invalidation_epoch == 1
    assert store.evidence("raw").text == "retained"


async def test_stale_cache_cannot_repopulate_cleared_recap(rig):
    _, recap, _, assembler = rig
    recap.publish(0, "old recap", [])
    await assembler.build(Scope(), ContextBudget())
    recap.clear(1)
    assert (await assembler.build(Scope(), ContextBudget())).recap == ""
    with pytest.raises(Conflict):
        recap.publish(1, "resurrect", [])


async def test_memory_unavailable_is_explicit(rig):
    _, _, memory, assembler = rig
    memory.available = False
    bundle = await assembler.build(Scope(), ContextBudget())
    assert bundle.recall_status == "not_requested"
    with pytest.raises(MemoryUnavailable):
        await memory.search("fact", Scope(), 5)
