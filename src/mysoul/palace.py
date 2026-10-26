"""Read-only native palace inspection, exclusively for the local operator UI."""

import json

from fastapi import Depends, HTTPException, Query

from mysoul.domain import Scope, now
from mysoul.memory import MemoryUnavailable
from mysoul.mempalace import MCPMemory


class PalaceInspector:
    required = frozenset(
        {
            "mempalace_get_taxonomy",
            "mempalace_status",
            "mempalace_list_drawers",
            "mempalace_get_drawer",
        }
    )

    def __init__(self, memory, store):
        self.memory, self.store = memory, store

    def capability(self):
        schemas = getattr(self.memory, "schemas", None)
        if schemas is None:
            return {"state": "not_configured", "missing": []}
        missing = sorted(self.required - schemas.keys())
        return {"state": "unsupported" if missing else "ready", "missing": missing}

    async def call(self, name, arguments):
        if self.capability()["state"] != "ready":
            raise HTTPException(501, "当前记忆引擎未提供完整的原生浏览接口。")
        data = await self.memory.call(name, arguments)
        if not isinstance(data, dict) or data.get("partial"):
            raise MemoryUnavailable("Incomplete native palace response")
        return data

    @staticmethod
    def count(value):
        if type(value) is not int or value < 0:
            raise MemoryUnavailable("Invalid native palace count")
        return value

    async def overview(self):
        capability = self.capability()
        if capability["state"] != "ready":
            return capability
        data = await self.call("mempalace_get_taxonomy", {})
        taxonomy = data.get("taxonomy")
        if not isinstance(taxonomy, dict):
            raise MemoryUnavailable("Missing native taxonomy")
        with self.store.lock:
            scopes = self.store.db.execute(
                "SELECT DISTINCT json_extract(body,'$.scope') FROM evidence"
            ).fetchall()
        labels = {MCPMemory.wing(Scope()): "主人私有"}
        for (raw,) in scopes:
            scope = Scope.model_validate_json(raw)
            label = {"owner": "主人私有", "group": "群聊", "public": "公开"}[scope.audience]
            labels[MCPMemory.wing(scope)] = label + (
                " · " + scope.conversation if scope.conversation != "owner" else ""
            )
        wings = []
        for wing, room_counts in sorted(taxonomy.items()):
            if not isinstance(wing, str) or not isinstance(room_counts, dict):
                raise MemoryUnavailable("Invalid native taxonomy")
            rooms = []
            for room, count in sorted(room_counts.items()):
                if not isinstance(room, str):
                    raise MemoryUnavailable("Invalid native room")
                rooms.append({"id": room, "chunks": self.count(count)})
            wings.append(
                {
                    "id": wing,
                    "label": labels.get(wing, wing),
                    "rooms": rooms,
                    "chunks": sum(r["chunks"] for r in rooms),
                }
            )
        status = await self.call("mempalace_status", {})
        return {
            **capability,
            "wings": wings,
            "counts": {
                "wings": len(wings),
                "rooms": sum(len(w["rooms"]) for w in wings),
                "chunks": sum(w["chunks"] for w in wings),
            },
            "diagnostics": {
                k: status[k]
                for k in (
                    "backend",
                    "embedding_device",
                    "vector_disabled",
                    "vector_disabled_reason",
                    "hnsw_capacity",
                    "sqlite_integrity_failed",
                )
                if k in status
            },
            "read_at": now().isoformat(),
        }

    def record(self, item, *, detail=False):
        if not isinstance(item, dict) or not isinstance(item.get("drawer_id"), str):
            raise MemoryUnavailable("Invalid native drawer")
        meta = item.get("metadata", {})
        if not isinstance(meta, dict):
            raise MemoryUnavailable("Invalid native drawer metadata")
        field = "content" if detail else "content_preview"
        text = item.get(field)
        if not isinstance(text, str):
            raise MemoryUnavailable("Missing native drawer text")
        result = {"id": item["drawer_id"], field: text}
        for key in ("wing", "room", "source_file", "filed_at", "last_modified", "added_by"):
            value = item.get(key, meta.get(key, ""))
            result[key] = value if isinstance(value, str) else ""
        result["chunks"] = self.count(item.get("chunks", meta.get("chunks", 1)))
        if detail:
            ids = item.get("chunk_ids", meta.get("chunk_ids", []))
            if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
                raise MemoryUnavailable("Invalid native chunk IDs")
            result["chunk_ids"] = ids
        return result

    async def drawers(self, *, wing=None, room=None, limit=20, offset=0):
        args = {"limit": limit, "offset": offset}
        if wing:
            args["wing"] = wing
        if room:
            args["room"] = room
        data = await self.call("mempalace_list_drawers", args)
        rows = data.get("drawers")
        total = self.count(data.get("total"))
        if not isinstance(rows, list) or len(rows) > limit:
            raise MemoryUnavailable("Invalid native drawer page")
        return {
            "drawers": [self.record(row) for row in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
            "wing": wing or "",
            "room": room or "",
        }

    async def drawer(self, drawer_id):
        data = await self.call("mempalace_get_drawer", {"drawer_id": drawer_id})
        result = self.record(data, detail=True)
        if result["id"] != drawer_id:
            raise MemoryUnavailable("Native drawer ID mismatch")
        with self.store.lock:
            rows = self.store.db.execute(
                "SELECT e.body FROM objects m JOIN evidence e ON e.id=m.id "
                "WHERE m.kind='memory_ref' AND json_extract(m.body,'$.remote')=?",
                (drawer_id,),
            ).fetchall()
        sources = [json.loads(row[0]) for row in rows]
        result["sources"] = [
            {
                "id": s["id"],
                "source": s["source"],
                "scope": s["scope"],
                "matches_original": s["text"] == result["content"],
            }
            for s in sources
        ]
        return result


def register_palace_routes(app, authorize):
    """Do not register these global reads in the model's memory-tool registry."""
    guard = [Depends(authorize)]

    def inspector():
        soul = app.state.soul
        return PalaceInspector(soul.memory, soul.store)

    @app.get("/api/memory/palace", dependencies=guard)
    async def palace_overview():
        result = await inspector().overview()
        result["sync"] = app.state.soul.memory_status()["long_term"]
        return result

    @app.get("/api/memory/palace/drawers", dependencies=guard)
    async def palace_drawers(
        wing: str | None = Query(default=None, min_length=1, max_length=256),
        room: str | None = Query(default=None, min_length=1, max_length=256),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ):
        return await inspector().drawers(wing=wing, room=room, limit=limit, offset=offset)

    @app.get("/api/memory/palace/drawer", dependencies=guard)
    async def palace_drawer(drawer_id: str = Query(min_length=1, max_length=512)):
        return await inspector().drawer(drawer_id)
