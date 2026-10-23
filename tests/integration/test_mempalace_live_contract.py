import pytest

from mysoul.config import Settings
from mysoul.domain import Evidence, Scope
from mysoul.mempalace import MCPMemory
from mysoul.service import SoulService
from mysoul.storage import StateStore
from tests.integration.test_mempalace import Session, schemas


async def test_identical_words_keep_distinct_source_identity(tmp_path):
    store = StateStore(tmp_path / "state.sqlite")
    session = Session()
    memory = MCPMemory(store, session, schemas())
    await memory.add(Evidence(id="a", text="相同原文"))
    await memory.add(Evidence(id="b", text="相同原文"))
    adds = [args for name, args in session.calls if name == "mempalace_add_drawer"]
    assert adds[0]["room"] != adds[1]["room"]
    await memory.search("相同", Scope(), 10)
    assert "room" not in session.calls[-1][1]
    store.close()


async def test_health_records_real_failure_and_recovery(tmp_path):
    class Failing(Session):
        broken = True

        async def call_tool(self, name, arguments):
            if self.broken:
                raise ConnectionError("gone")
            return await super().call_tool(name, arguments)

    store = StateStore(tmp_path / "state.sqlite")
    session = Failing()
    memory = MCPMemory(store, session, schemas())
    from mysoul.memory import MemoryUnavailable

    with pytest.raises(MemoryUnavailable):
        await memory.search("中文", Scope(), 5)
    assert memory.health()["state"] == "unavailable"
    session.broken = False
    await memory.search("中文", Scope(), 5)
    assert memory.health()["state"] == "connected" and memory.health()["last_success_at"]
    store.close()


async def test_memory_status_exposes_delivered_count_without_fake_connection(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        status = soul.memory_status()
        assert status["long_term"]["state"] == "not_configured"
        assert status["long_term"]["backend"] == "mempalace"
        assert status["long_term"]["delivered"] == 0
        assert status["short_term"]["recap_version"] == soul.recap.current().version


async def test_full_source_path_and_chunk_hits_retain_one_evidence(tmp_path):
    class Chunked(Session):
        async def call_tool(self, name, arguments):
            if name == "mempalace_search":
                return {"results": [{"source_file": "raw", "source_path": "mysoul:raw"}] * 2}
            return await super().call_tool(name, arguments)

    store = StateStore(tmp_path / "state.sqlite")
    store.add_evidence(Evidence(id="raw", text="中文原文"))
    memory = MCPMemory(store, Chunked(), schemas())
    assert [hit.id for hit in await memory.search("中文", Scope(), 10)] == ["raw"]
    store.close()


def test_saved_memory_selection_survives_normal_start_but_can_be_overridden(tmp_path):
    import json
    from pathlib import Path

    path = tmp_path / "memory.settings.json"
    path.write_text(
        json.dumps({"backend": "mempalace", "process_config": str(tmp_path / "engine.json")}),
        encoding="utf-8",
    )
    service = SoulService(Settings(data_dir=tmp_path))
    try:
        assert service.settings.memory_backend == "mempalace"
        assert service.settings.mempalace_config == Path(tmp_path / "engine.json")
    finally:
        service.store.close()
    service = SoulService(Settings(data_dir=tmp_path, memory_backend="local"))
    try:
        assert service.settings.memory_backend == "local"
    finally:
        service.store.close()


async def test_first_real_connection_backfills_previously_local_deliveries(tmp_path):
    from mysoul.memory import LocalMemory, flush_memory_queue

    store = StateStore(tmp_path / "state.sqlite")
    store.add_evidence(Evidence(id="older", text="接入前已有的中文经历"))
    store.add_evidence(Evidence(id="synced", text="已确认的长期记忆"))
    await flush_memory_queue(store, LocalMemory(store))
    store.put("memory_ref", "synced", {"remote": "confirmed-remote"})
    session = Session()
    memory = MCPMemory(store, session, schemas())
    assert await flush_memory_queue(store, memory) == 1
    assert session.calls[0][1]["source_file"] == "mysoul:older"
    assert store.get("memory_ref", "synced")["remote"] == "confirmed-remote"
    MCPMemory(store, session, schemas())
    assert await flush_memory_queue(store, memory) == 0
    store.close()


def test_search_failure_returns_recoverable_error_without_losing_original(tmp_path):
    from fastapi.testclient import TestClient

    from mysoul.api import create_app
    from mysoul.memory import MemoryUnavailable

    class Broken:
        async def search(self, *args):
            raise MemoryUnavailable("private engine diagnostic that must not leak")

    app = create_app(Settings(data_dir=tmp_path), token="local-test-token")
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        app.state.soul.store.add_evidence(Evidence(id="retained", text="故障时仍保留的原文"))
        app.state.soul.memory = Broken()
        result = client.get(
            "/api/memory/search?q=test", headers={"Authorization": "Bearer local-test-token"}
        )
        assert result.status_code == 503
        assert "本地记录已保留" in result.json()["detail"]
        assert "private engine" not in result.text
        assert app.state.soul.store.evidence("retained").text == "故障时仍保留的原文"


async def test_invalid_remote_receipt_marks_health_unavailable(tmp_path):
    from mysoul.memory import MemoryUnavailable

    class Invalid(Session):
        async def call_tool(self, name, arguments):
            return {"success": True}

    store = StateStore(tmp_path / "state.sqlite")
    memory = MCPMemory(store, Invalid(), schemas())
    with pytest.raises(MemoryUnavailable):
        await memory.add(Evidence(id="lost-receipt", text="应保留原文"))
    assert memory.health()["state"] == "unavailable"
    store.close()


async def test_changed_remote_original_marks_health_unavailable(tmp_path):
    from mysoul.memory import MemoryUnavailable

    store = StateStore(tmp_path / "state.sqlite")
    memory = MCPMemory(store, Session(), schemas())
    await memory.add(Evidence(id="raw", text="与远端不同的原文"))
    with pytest.raises(MemoryUnavailable):
        await memory.get("raw", Scope())
    assert memory.health()["state"] == "unavailable"
    store.close()
