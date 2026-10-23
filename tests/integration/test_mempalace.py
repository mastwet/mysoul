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


def test_process_settings_bind_actual_data_and_embedding(tmp_path):
    from mysoul.mempalace import ProcessConfig

    config = ProcessConfig(
        command="python",
        args=["-m", "mempalace.mcp_server"],
        source_dir=tmp_path / "upstream",
        data_dir=tmp_path / "memory",
        embedding_model="embeddinggemma",
    )
    env = config.process_environment()
    assert env["MEMPALACE_PALACE_PATH"] == str((tmp_path / "memory/palace").resolve())
    assert env["MEMPALACE_EMBEDDING_MODEL"] == "embeddinggemma"
    assert env["MEMPALACE_CONFIG_DIR"] == str((tmp_path / "memory/config").resolve())


@pytest.mark.mempalace
async def test_real_mempalace_chinese_restart(tmp_path):
    config = os.environ.get("MYSOUL_MEMPALACE_CONFIG")
    if not config:
        pytest.skip("Real MemPalace process, pinned revision and multilingual index not configured")
    store = StateStore(tmp_path / "state.sqlite")
    evidence = Evidence(id="real-chinese", text="主人希望先完成离线验证，再接入真实群聊。")
    async with isolated_process(config, store, tmp_path) as memory:
        await memory.add(evidence)
        assert any(e.id == evidence.id for e in await memory.search("离线验证", Scope(), 10))
    async with isolated_process(config, store, tmp_path) as memory:
        assert (await memory.get(evidence.id, Scope())).text == evidence.text
    store.close()


@pytest.mark.mempalace
async def test_real_semantic_chinese_provenance_and_restart(tmp_path):
    config = os.environ.get("MYSOUL_MEMPALACE_CONFIG")
    if not config:
        pytest.skip("Real multilingual MemPalace not configured")
    store = StateStore(tmp_path / "state.sqlite")
    text = (
        "我和用户分享了巨嘴鸟的结构奇迹：喙内部的泡沫骨骼让它又轻又坚固，外层角蛋白还能帮助散热。"
    )
    records = [
        Evidence(id="toucan-one", text=text),
        Evidence(id="toucan-two", text=text),
        Evidence(id="firefly", text="我和用户分享了萤火虫用化学反应产生冷光的故事。"),
        Evidence(id="commitment", text="用户希望下周四核对报告，再决定是否发布。"),
    ]
    async with isolated_process(config, store, tmp_path) as memory:
        refs = [await memory.add(item) for item in records]
        assert refs[0] != refs[1]
        hits = await memory.search("那种嘴巴特别大的热带鸟，为何不会被沉重的嘴拖累？", Scope(), 3)
        assert any(hit.id.startswith("toucan-") for hit in hits)
        assert len({hit.id for hit in hits}) == len(hits)
        with pytest.raises(PermissionError):
            await memory.get("toucan-one", Scope(audience="group", conversation="g"))
        assert not await memory.search("巨嘴鸟", Scope(audience="group", conversation="g"), 5)
    async with isolated_process(config, store, tmp_path) as memory:
        assert (await memory.get("toucan-one", Scope())).text == text
        assert any(
            hit.id.startswith("toucan-") for hit in await memory.search("大鸟的嘴很轻", Scope(), 5)
        )
    store.close()


def isolated_process(config, store, tmp_path):
    process = MemPalaceProcess.from_file(config, store)
    process.config = process.config.model_copy(update={"data_dir": tmp_path / "palace"})
    return process


def test_live_fixture_never_reuses_configured_palace(tmp_path):
    import json

    production = tmp_path / "production-palace"
    fixture = tmp_path / "fixture"
    config = tmp_path / "process.json"
    config.write_text(
        json.dumps(
            {
                "command": "python",
                "args": ["-m", "mempalace.mcp_server"],
                "source_dir": str(tmp_path / "upstream"),
                "data_dir": str(production),
                "embedding_model": "embeddinggemma",
            }
        ),
        encoding="utf-8",
    )
    process = isolated_process(config, None, fixture)
    assert process.config.data_dir == fixture / "palace"
    assert json.loads(config.read_text(encoding="utf-8"))["data_dir"] == str(production)
