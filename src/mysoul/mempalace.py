"""Full upstream MemPalace stdio MCP adapter; runtime schemas are mandatory."""

import asyncio
import json
import os
from contextlib import AsyncExitStack
from hashlib import sha256
from pathlib import Path

from jsonschema import validate
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mysoul.domain import Contract, Evidence, Scope
from mysoul.memory import MemoryUnavailable

INSPECTED_REVISION = "f41e8e75ddaadf5588d5127715fa531d79eadb45"


class MCPMemory:
    required = {"mempalace_add_drawer", "mempalace_search", "mempalace_get_drawer"}

    def __init__(self, store, session, schemas):
        if not self.required.issubset(schemas):
            raise ValueError("MemPalace MCP tool schema missing required capabilities")
        self.store, self.session, self.schemas = store, session, schemas

    @staticmethod
    def wing(scope: Scope):
        return "mysoul-" + sha256(scope.model_dump_json().encode()).hexdigest()[:24]

    async def call(self, name, arguments):
        validate(arguments, self.schemas[name])
        try:
            async with asyncio.timeout(30):
                response = await self.session.call_tool(name, arguments)
            if isinstance(response, dict):
                data = response
            elif response.isError:
                raise MemoryUnavailable("MemPalace returned a tool error")
            elif response.structuredContent:
                data = response.structuredContent
            else:
                data = json.loads("\n".join(c.text for c in response.content if c.type == "text"))
            if "error" in data or data.get("success") is False:
                raise MemoryUnavailable("MemPalace operation failed")
            return data
        except MemoryUnavailable:
            raise
        except Exception as exc:
            raise MemoryUnavailable("MemPalace unavailable; local evidence retained") from exc

    async def add(self, evidence: Evidence) -> str:
        self.store.add_evidence(evidence)
        data = await self.call(
            "mempalace_add_drawer",
            {
                "wing": self.wing(evidence.scope),
                "room": "evidence",
                "content": evidence.text,
                "source_file": f"mysoul:{evidence.id}",
                "added_by": "mysoul",
            },
        )
        ref = data.get("drawer_id")
        if not isinstance(ref, str):
            raise MemoryUnavailable("MemPalace returned no drawer ID")
        self.store.put("memory_ref", evidence.id, {"remote": ref})
        return ref

    async def search(self, query: str, scope: Scope, limit: int) -> list[Evidence]:
        data = await self.call(
            "mempalace_search",
            {
                "query": query[:250] or "recent",
                "limit": max(1, min(limit, 100)),
                "wing": self.wing(scope),
                "room": "evidence",
            },
        )
        hits = []
        for item in data.get("results", []):
            source = item.get("source_file", "")
            if not source.startswith("mysoul:"):
                continue
            try:
                evidence = self.store.evidence(source.removeprefix("mysoul:"))
            except KeyError:
                continue
            if evidence.permitted(scope):
                # Return the original retained evidence, not an untrusted replacement scope.
                hits.append(evidence)
        return hits[:limit]

    async def get(self, ref: str, scope: Scope) -> Evidence:
        evidence = self.store.evidence(ref)
        if not evidence.permitted(scope):
            raise PermissionError("Memory reference outside authorized scope")
        mapping = self.store.get("memory_ref", ref)
        if not mapping:
            raise MemoryUnavailable("Evidence not yet delivered to MemPalace")
        data = await self.call("mempalace_get_drawer", {"drawer_id": mapping["remote"]})
        if data.get("content", data.get("text")) != evidence.text:
            raise MemoryUnavailable("Remote drawer differs from retained source; review required")
        return evidence


class ProcessConfig(Contract):
    command: str
    args: list[str]
    source_dir: Path
    revision: str = INSPECTED_REVISION
    data_dir: Path
    embedding_model: str
    env: dict[str, str] = {}


class MemPalaceProcess:
    def __init__(self, config: ProcessConfig, store):
        self.config, self.store = config, store

    @classmethod
    def from_file(cls, path, store):
        return cls(ProcessConfig.model_validate_json(Path(path).read_text(encoding="utf-8")), store)

    async def __aenter__(self):
        config = self.config
        process = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(config.source_dir),
            "rev-parse",
            "HEAD",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        output, _ = await process.communicate()
        if process.returncode or output.decode().strip() != config.revision:
            raise MemoryUnavailable("Upstream checkout differs from configured revision")
        config.data_dir.mkdir(parents=True, exist_ok=True)
        fingerprint = config.data_dir / "mysoul-index.json"
        identity = {"revision": config.revision, "embedding_model": config.embedding_model}
        if fingerprint.exists() and json.loads(fingerprint.read_text()) != identity:
            raise MemoryUnavailable("Index identity changed; explicit migration/reindex required")
        fingerprint.write_text(json.dumps(identity), encoding="utf-8")
        env = {
            k: v
            for k, v in os.environ.items()
            if k.upper() in {"PATH", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE"}
        }
        env.update(config.env)
        self.stack = AsyncExitStack()
        try:
            streams = await self.stack.enter_async_context(
                stdio_client(
                    StdioServerParameters(
                        command=config.command,
                        args=config.args,
                        env=env,
                        cwd=str(config.source_dir),
                    )
                )
            )
            session = await self.stack.enter_async_context(ClientSession(*streams))
            async with asyncio.timeout(30):
                await session.initialize()
                listed = await session.list_tools()
            return MCPMemory(self.store, session, {t.name: t.inputSchema for t in listed.tools})
        except BaseException:
            await self.stack.aclose()
            raise

    async def __aexit__(self, *args):
        await self.stack.aclose()
