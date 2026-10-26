import pytest
from fastapi.testclient import TestClient

from mysoul.api import create_app
from mysoul.config import Settings
from mysoul.domain import Evidence
from mysoul.memory import MemoryUnavailable
from mysoul.mempalace import MCPMemory
from mysoul.storage import StateStore


class Session:
    def __init__(self):
        self.calls = []
        self.responses = {
            "mempalace_get_taxonomy": {"taxonomy": {"private": {"evidence-one": 3}}},
            "mempalace_status": {
                "backend": "chroma",
                "vector_disabled": True,
                "vector_disabled_reason": "capacity mismatch",
                "protocol": "DO NOT DISPLAY OR EXECUTE",
            },
            "mempalace_list_drawers": {
                "drawers": [
                    {
                        "drawer_id": "remote",
                        "wing": "private",
                        "room": "evidence-one",
                        "content_preview": "<script>untrusted</script>",
                        "metadata": {"source_file": "mysoul:local", "chunks": 3},
                    }
                ],
                "total": 1,
                "offset": 0,
                "limit": 20,
            },
            "mempalace_get_drawer": {
                "drawer_id": "remote",
                "content": "original\ntext",
                "metadata": {
                    "wing": "private",
                    "room": "evidence-one",
                    "source_file": "mysoul:local",
                    "chunks": 3,
                },
                "chunks": 3,
                "chunk_ids": ["a", "b", "c"],
            },
        }

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return self.responses[name]


def make_memory(store):
    session = Session()
    names = MCPMemory.required | set(session.responses)
    memory = MCPMemory(store, session, {n: {"type": "object"} for n in names})
    store.add_evidence(Evidence(id="local", text="original\ntext", source="chat"))
    store.put("memory_ref", "local", {"remote": "remote"})
    return memory, session


async def test_native_read_contract_and_provenance(tmp_path):
    from mysoul.palace import PalaceInspector

    store = StateStore(tmp_path / "state.sqlite")
    try:
        memory, session = make_memory(store)
        inspector = PalaceInspector(memory, store)
        overview = await inspector.overview()
        assert overview["state"] == "ready"
        assert overview["counts"] == {"wings": 1, "rooms": 1, "chunks": 3}
        assert overview["diagnostics"]["vector_disabled"] is True
        assert "protocol" not in overview["diagnostics"]
        page = await inspector.drawers(wing="private", room="evidence-one", limit=20, offset=0)
        assert page["total"] == 1
        assert page["drawers"][0]["chunks"] == 3
        assert session.calls[-1][1] == {
            "wing": "private",
            "room": "evidence-one",
            "limit": 20,
            "offset": 0,
        }
        detail = await inspector.drawer("remote")
        assert detail["content"] == "original\ntext"
        assert detail["sources"][0]["id"] == "local"
        assert detail["sources"][0]["matches_original"] is True
        assert detail["chunk_ids"] == ["a", "b", "c"]
        assert all(name in session.responses for name, _ in session.calls)
    finally:
        store.close()


async def test_capability_and_partial_failure_are_not_empty_palaces(tmp_path):
    from mysoul.palace import PalaceInspector

    store = StateStore(tmp_path / "state.sqlite")
    try:
        assert (await PalaceInspector(object(), store).overview())["state"] == "not_configured"
        memory, session = make_memory(store)
        del memory.schemas["mempalace_get_taxonomy"]
        assert (await PalaceInspector(memory, store).overview())["state"] == "unsupported"
        memory.schemas["mempalace_get_taxonomy"] = {"type": "object"}
        session.responses["mempalace_get_taxonomy"] = {"taxonomy": {}, "partial": True}
        with pytest.raises(MemoryUnavailable):
            await PalaceInspector(memory, store).overview()
        session.responses["mempalace_list_drawers"] = {"drawers": [], "total": "not a number"}
        with pytest.raises(MemoryUnavailable):
            await PalaceInspector(memory, store).drawers(limit=20, offset=0)
        session.responses["mempalace_get_drawer"] = {"error": "Drawer not found: missing"}
        with pytest.raises(MemoryUnavailable):
            await PalaceInspector(memory, store).drawer("missing")
    finally:
        store.close()


def test_operator_routes_auth_validation_and_native_detail(tmp_path):
    app = create_app(Settings(data_dir=tmp_path), token="operator-token")
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        for path in (
            "memory/palace",
            "memory/palace/drawers",
            "memory/palace/drawer?drawer_id=remote",
        ):
            assert client.get("/api/" + path).status_code == 401
        client.headers["Authorization"] = "Bearer operator-token"
        assert client.get("/api/memory/palace").json()["state"] == "not_configured"
        memory, session = make_memory(app.state.soul.store)
        app.state.soul.memory = memory
        assert client.get("/api/memory/palace").json()["counts"]["chunks"] == 3
        assert client.get("/api/memory/palace/drawers?limit=101").status_code == 422
        assert client.get("/api/memory/palace/drawers?offset=-1").status_code == 422
        assert client.get("/api/memory/palace/drawer?drawer_id=").status_code == 422
        assert (
            client.get("/api/memory/palace/drawer?drawer_id=remote").json()["sources"][0]["id"]
            == "local"
        )
        assert client.post("/api/memory/palace/drawer").status_code == 405
        assert client.get("/palace.mjs").headers["content-type"].startswith("text/javascript")


@pytest.mark.mempalace
async def test_real_native_palace_structure_and_full_original(tmp_path):
    import os

    from mysoul.mempalace import MemPalaceProcess
    from mysoul.palace import PalaceInspector

    config = os.environ.get("MYSOUL_MEMPALACE_CONFIG")
    if not config:
        pytest.skip("Real MemPalace configuration required")
    store = StateStore(tmp_path / "local.sqlite")
    process = MemPalaceProcess.from_file(config, store)
    process.config = process.config.model_copy(update={"data_dir": tmp_path / "native-palace"})
    content = ("原生宫殿浏览应保留空白、换行与来源。\n" * 120) + "结尾  "
    try:
        async with process as memory:
            ref = await memory.add(Evidence(id="native-long", text=content, source="native-test"))
            inspector = PalaceInspector(memory, store)
            overview = await inspector.overview()
            assert overview["counts"]["wings"] == 1
            assert overview["counts"]["rooms"] == 1
            assert overview["counts"]["chunks"] > 1
            wing = overview["wings"][0]
            page = await inspector.drawers(wing=wing["id"], room=wing["rooms"][0]["id"])
            assert page["total"] == 1
            assert page["drawers"][0]["id"] == ref
            detail = await inspector.drawer(ref)
            assert detail["content"] == content
            assert detail["sources"][0]["matches_original"] is True
            assert len(detail["chunk_ids"]) == overview["counts"]["chunks"]
    finally:
        store.close()
