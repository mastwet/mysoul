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

from mysoul.domain import Contract, Evidence, Scope, now
from mysoul.memory import MemoryUnavailable

INSPECTED_REVISION = "f41e8e75ddaadf5588d5127715fa531d79eadb45"


class MCPMemory:
    required = {"mempalace_add_drawer", "mempalace_search", "mempalace_get_drawer"}

    def __init__(self, store, session, schemas):
        if not self.required.issubset(schemas):
            raise ValueError("MemPalace MCP tool schema missing required capabilities")
        self.store, self.session, self.schemas = store, session, schemas
        self._health = {"state": "connected", "last_success_at": now().isoformat(), "error": ""}
        # Local/fixture delivery is not a confirmed MemPalace receipt. Backfill
        # retained originals once, while leaving confirmed remote mappings intact.
        with store.transaction() as db:
            db.execute("INSERT OR IGNORE INTO memory_queue(id) SELECT id FROM evidence")
            db.execute(
                "UPDATE memory_queue SET status='pending',remote_ref=NULL WHERE NOT EXISTS "
                "(SELECT 1 FROM objects WHERE kind='memory_ref' AND id=memory_queue.id)"
            )

    def health(self):
        return dict(self._health)

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
            self._health = {"state": "connected", "last_success_at": now().isoformat(), "error": ""}
            return data
        except MemoryUnavailable:
            self._health.update(state="unavailable", error="MemPalace operation failed")
            raise
        except Exception as exc:
            self._health.update(state="unavailable", error=type(exc).__name__)
            raise MemoryUnavailable("MemPalace unavailable; local evidence retained") from exc

    async def add(self, evidence: Evidence) -> str:
        self.store.add_evidence(evidence)
        data = await self.call(
            "mempalace_add_drawer",
            {
                "wing": self.wing(evidence.scope),
                # Upstream deduplicates by wing+room+content. A stable room per
                # source retains distinct provenance for repeated identical words.
                "room": "evidence-" + sha256(evidence.id.encode()).hexdigest()[:24],
                "content": evidence.text,
                "source_file": f"mysoul:{evidence.id}",
                "added_by": "mysoul",
            },
        )
        ref = data.get("drawer_id")
        if not isinstance(ref, str) or not ref:
            self._health.update(state="unavailable", error="Invalid drawer receipt")
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
            },
        )
        hits = []
        seen = set()
        for item in data.get("results", []):
            source = item.get("source_path") or item.get("source_file", "")
            if not source.startswith("mysoul:"):
                continue
            try:
                evidence = self.store.evidence(source.removeprefix("mysoul:"))
            except KeyError:
                continue
            if evidence.permitted(scope) and evidence.id not in seen:
                seen.add(evidence.id)
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
            self._health.update(state="unavailable", error="Remote content mismatch")
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

    def process_environment(self):
        env = {
            k: v
            for k, v in os.environ.items()
            if k.upper() in {"PATH", "SYSTEMROOT", "TEMP", "TMP"}
        }
        env.update(self.env)
        env.update(
            {
                "MEMPALACE_PALACE_PATH": str((self.data_dir / "palace").resolve()),
                "MEMPALACE_CONFIG_DIR": str((self.data_dir / "config").resolve()),
                "MEMPALACE_EMBEDDING_MODEL": self.embedding_model,
            }
        )
        return env


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
        env = config.process_environment()
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
