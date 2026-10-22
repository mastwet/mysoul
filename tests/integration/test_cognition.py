from mysoul import cognition
from mysoul.domain import Event
from mysoul.laputa import RecapStore
from mysoul.storage import StateStore


def source_store(tmp_path, *, text="明天一起整理资料", result=None, source="owner"):
    store = StateStore(tmp_path / "state.sqlite")
    store.load_subject()
    RecapStore(store)
    event = Event(id="turn-1", dedup_key="turn-1", content=text, source=source)
    store.add_event(event)
    store.record_interaction(event, result or {
        "event_id": event.id, "choice": "owner_served", "text": "好，保留这项约定。",
    })
    return store, cognition.CognitiveStore(store)


def test_capture_once_preserves_both_roles(tmp_path):
    store, sources = source_store(tmp_path, text="长文" * 3000)
    sources.capture_interaction("turn-1")
    sources.capture_interaction("turn-1")
    window = sources.pending_window(16000)
    assert [(s.role, s.text) for s in window.slices] == [
        ("user", "长文" * 3000), ("assistant", "好，保留这项约定。"),
    ]
    assert len(store.all("cognitive_source")) == 2
    assert window.recap_version == 0
    store.close()


def test_failed_turn_stays_failure(tmp_path):
    store, sources = source_store(tmp_path, result={
        "event_id": "turn-1", "choice": "owner_served", "text": "Model unavailable",
        "error": {"code": "timeout"},
    })
    sources.capture_interaction("turn-1")
    window = sources.pending_window(16000)
    assert window.slices[1].role == "failure"
    assert 'timeout' in window.slices[1].text
    store.close()


def test_large_segment_keeps_unseen_suffix(tmp_path):
    store, sources = source_store(tmp_path, text="甲" * 10 + "乙" * 10)
    sources.capture_interaction("turn-1")
    first = sources.pending_window(10)
    assert first.slices[0].text == "甲" * 10
    assert (first.slices[0].start, first.slices[0].end, first.slices[0].total) == (0, 10, 20)
    # Simulate a committed coordinate, not deletion of the raw source.
    row = store.get("cognitive_source", first.slices[0].source_id)
    row["covered"] = 10
    store.put("cognitive_source", row["id"], row)
    second = sources.pending_window(10)
    assert second.slices[0].text == "乙" * 10
    assert second.slices[0].start == 10
    store.close()


def test_reopen_preserves_pending_window(tmp_path):
    store, sources = source_store(tmp_path)
    sources.capture_interaction("turn-1")
    before = sources.pending_window(16000)
    store.close()
    reopened = StateStore(tmp_path / "state.sqlite")
    assert cognition.CognitiveStore(reopened).pending_window(16000) == before
    reopened.close()


def test_initiative_has_no_invented_user(tmp_path):
    store, sources = source_store(tmp_path, source="local-initiative")
    sources.capture_interaction("turn-1")
    assert [s.role for s in sources.pending_window(16000).slices] == ["assistant"]
    store.close()
