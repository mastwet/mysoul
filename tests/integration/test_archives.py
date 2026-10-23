import pytest

from mysoul.archives import ArchiveStore, CompressionPolicy
from mysoul.domain import Event, Scope
from mysoul.laputa import RecapStore
from mysoul.storage import Conflict, StateStore


def seed(tmp_path, count, text_size=80):
    store = StateStore(tmp_path / "state.sqlite")
    store.load_subject()
    RecapStore(store)
    for n in range(count):
        e = Event(id=str(n), dedup_key=str(n), content="U" * text_size)
        store.add_event(e)
        store.record_interaction(
            e,
            {
                "event_id": e.id,
                "input": e.content,
                "text": "A" * text_size,
                "choice": "owner_served",
            },
        )
    return store, ArchiveStore(store)


def test_l0_count100_compacts70(tmp_path):
    store, archives = seed(tmp_path, 100)
    plan = archives.plan(CompressionPolicy(), 131072, 0)
    assert len(plan.replace_ids) == 70 and plan.level == 1
    node = archives.publish(plan, "older experience", "op")
    assert node.level == 1
    nodes = archives.frontier(Scope())
    assert len(nodes) == 31
    assert [n.first_seq for n in nodes] == [1] + list(range(71, 101))
    assert archives.publish(plan, "older experience", "op").id == node.id
    store.close()


def test_level4_compacts3_and_frontier_partition(tmp_path):
    store, archives = seed(tmp_path, 12)
    policy = CompressionPolicy(raw_trigger=3, raw_batch=2, keep_recent=0)
    for n in range(4):
        p = archives.plan(policy, 131072, 0)
        assert p.level == 1
        archives.publish(p, f"phase{n}", str(n))
    p = archives.plan(policy, 131072, 0)
    assert p.level == 2 and len(p.replace_ids) == 3
    archives.publish(p, "old phases", "upper")
    covered = []
    for n in archives.frontier(Scope()):
        covered += list(range(n.first_seq, n.last_seq + 1))
    assert covered == list(range(1, 13))
    page = archives.expand(archives.frontier(Scope())[0].id, Scope(), limit=100)
    assert len(page["items"]) == 6
    store.close()


def test_level8_root_compaction(tmp_path):
    store, archives = seed(tmp_path, 10)
    policy = CompressionPolicy(raw_trigger=2, raw_batch=1, keep_recent=0, max_level=1)
    for n in range(4):
        p = archives.plan(policy, 131072, 0)
        archives.publish(p, "x", str(n))
    p = archives.plan(policy, 131072, 0)
    assert p.level == 1 and len(p.replace_ids) == 3
    archives.publish(p, "root", "root")
    assert max(n.level for n in archives.frontier(Scope())) == 1
    store.close()


def test_publication_rejects_source_change_and_growth(tmp_path):
    store, archives = seed(tmp_path, 100)
    p = archives.plan(CompressionPolicy(), 131072, 0)
    before = [n.id for n in archives.frontier(Scope())]
    with pytest.raises(ValueError):
        archives.publish(p, "X" * 100000, "growth")
    assert [n.id for n in archives.frontier(Scope())] == before
    store.interrupt()
    with pytest.raises(Conflict):
        archives.publish(p, "short", "stale")
    assert [n.id for n in archives.frontier(Scope())] == before
    store.close()


def test_scope_blocks_owner_archive_expansion(tmp_path):
    store, archives = seed(tmp_path, 100)
    node = archives.publish(archives.plan(CompressionPolicy(), 131072, 0), "private", "op")
    with pytest.raises(PermissionError):
        archives.expand(node.id, Scope(audience="group", conversation="g"))
    store.close()


def test_oversized_leaf_fragment_resume(tmp_path):
    store, archives = seed(tmp_path, 10, text_size=16000)
    policy = CompressionPolicy(raw_trigger=2, raw_batch=1, keep_recent=8)
    initial = archives.frontier(Scope())[0].id
    ends = []
    for n in range(40):
        plan = archives.plan(policy, 4000, 1000)
        assert plan is not None
        ends.append(plan.end)
        node = archives.publish(plan, "piece summary", f"part{n}")
        if plan.mode == "fragment_merge":
            break
        assert archives.frontier(Scope())[0].id == initial
        store.close()
        store = StateStore(tmp_path / "state.sqlite")
        archives = ArchiveStore(store)
    assert node.id == archives.frontier(Scope())[0].id
    assert node.level == 1 and plan.mode == "fragment_merge"
    assert max(ends) > 32000
    store.close()


def test_publish_rejects_changed_task_leaf(tmp_path):
    from mysoul.domain import ActivityRecord, Goal

    store, archives = seed(tmp_path, 0)
    goal = Goal(id="g", objective="task")
    store.save_goal(goal)
    task = ActivityRecord(id="a", goal_id="g", status="completed", final_note="X" * 500)
    store.save_activity(task)
    store.put("activity_context", "a", {"scope": Scope().model_dump()})
    for n in range(3):
        e = Event(id=str(n), dedup_key=str(n), content="test")
        store.add_event(e)
        store.record_interaction(e, {"text": "reply", "choice": "owner_served"})
    p = archives.plan(CompressionPolicy(raw_trigger=2, raw_batch=1, keep_recent=0), 131072, 0)
    task.final_note = "changed"
    store.save_activity(task)
    with pytest.raises(Conflict):
        archives.publish(p, "old result", "stale-task")
    assert not store.all("archive_receipt")
    store.close()


def test_publication_rolls_back_after_parent_insert(tmp_path, monkeypatch):
    store, archives = seed(tmp_path, 100)
    p = archives.plan(CompressionPolicy(), 131072, 0)
    ids = [n.id for n in archives.frontier(Scope())]
    original = archives.save_in

    def fail(db, node):
        original(db, node)
        if node.level > 0:
            raise RuntimeError("disk failure")

    monkeypatch.setattr(archives, "save_in", fail)
    with pytest.raises(RuntimeError):
        archives.publish(p, "small", "broken")
    assert [n.id for n in archives.frontier(Scope())] == ids
    assert not store.all("archive_receipt")
    store.close()


def test_pressure_compacts_upper_level_below_count_trigger(tmp_path):
    store, archives = seed(tmp_path, 3, text_size=1000)
    policy = CompressionPolicy(raw_trigger=2, raw_batch=1, keep_recent=0)
    for n in range(2):
        archives.publish(archives.plan(policy, 131072, 0), "S" * 1600, str(n))
    p = archives.plan(policy, 5000, 0)
    assert p.level == 2
    store.close()


def test_fragment_summaries_are_reduced_before_final_merge(tmp_path):
    store, archives = seed(tmp_path, 10, text_size=16000)
    policy = CompressionPolicy(raw_trigger=2, raw_batch=1, keep_recent=8)
    modes = []
    for n in range(80):
        p = archives.plan(policy, 4000, 1000)
        modes.append(p.mode)
        archives.publish(p, "S" * min(500, len(p.content) // 2), f"fragment-{n}")
        if p.mode == "fragment_merge":
            break
    assert "fragment_reduce" in modes
    assert modes[-1] == "fragment_merge"
    assert archives.frontier(Scope())[0].level == 1
    store.close()


def test_archive_expands_frozen_original_after_source_edit(tmp_path):
    store, archives = seed(tmp_path, 100)
    node = archives.publish(
        archives.plan(CompressionPolicy(), 131072, 0), "old period", "old-period"
    )
    e = store.events()[0]
    store.record_interaction(
        e, {"event_id": e.id, "input": e.content, "text": "CORRECTION", "choice": "owner_served"}
    )
    archived = archives.expand(node.id, Scope(), limit=100)["items"][0]
    assert archived["body"]["text"] == "A" * 80
    assert all(n.id != node.id for n in archives.frontier(Scope()))
    store.close()
