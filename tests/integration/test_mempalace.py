import os

import pytest

from mysoul.domain import Evidence, Scope
from mysoul.memory import flush_memory_queue
from mysoul.mempalace import MCPMemory, MemPalaceProcess
from mysoul.storage import StateStore


class Session:
    def __init__(self):
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "mempalace_add_drawer":
            return {"success": True, "drawer_id": "remote1"}
        if name == "mempalace_search":
            return {"results": [{"source_file": "mysoul:raw", "text": "中文原始证据"}]}
        return {"content": "中文原始证据"}


def schemas():
    return {
        "mempalace_add_drawer": {"type": "object", "required": ["wing", "room", "content"]},
        "mempalace_search": {"type": "object", "required": ["query"]},
        "mempalace_get_drawer": {"type": "object", "required": ["drawer_id"]},
    }


async def test_mcp_contract_and_scoped_outbox(tmp_path):
    store = StateStore(tmp_path / "s.db")
    evidence = Evidence(id="raw", text="中文原始证据")
    store.add_evidence(evidence)
    session = Session()
    memory = MCPMemory(store, session, schemas())
    assert await flush_memory_queue(store, memory) == 1
    assert await flush_memory_queue(store, memory) == 0
    assert (await memory.search("中文", Scope(), 5))[0].id == "raw"
    assert (await memory.get("raw", Scope())).text == "中文原始证据"
    with pytest.raises(PermissionError):
        await memory.get("raw", Scope(audience="group", conversation="g"))
    owner_wing = session.calls[0][1]["wing"]
    await memory.search("中文", Scope(audience="group", conversation="g"), 5)
    assert session.calls[-1][1]["wing"] != owner_wing
    store.close()


def test_mcp_missing_schema_fails_explicitly(tmp_path):
    store = StateStore(tmp_path / "s.db")
    with pytest.raises(ValueError):
        MCPMemory(store, Session(), {})
    store.close()


@pytest.mark.mempalace
async def test_real_mempalace_chinese_restart(tmp_path):
    config = os.environ.get("MYSOUL_MEMPALACE_CONFIG")
    if not config:
        pytest.skip("Real MemPalace process, pinned revision and multilingual index not configured")
    store = StateStore(tmp_path / "state.sqlite")
    evidence = Evidence(id="real-chinese", text="主人希望先完成离线验证，再接入真实群聊。")
    async with MemPalaceProcess.from_file(config, store) as memory:
        await memory.add(evidence)
        assert any(e.id == evidence.id for e in await memory.search("离线验证", Scope(), 10))
    async with MemPalaceProcess.from_file(config, store) as memory:
        assert (await memory.get(evidence.id, Scope())).text == evidence.text
    store.close()
