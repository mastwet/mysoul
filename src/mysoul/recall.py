"""Explicit scoped memory reads. Retrieved history is never a new experience."""

import json

from pydantic import Field, ValidationError

from mysoul.domain import Contract, Scope
from mysoul.memory import MemoryUnavailable

NAMES = {"memory_search", "memory_get"}


class SearchArgs(Contract):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=10)


class GetArgs(Contract):
    ref: str = Field(min_length=1, max_length=256)
    offset: int = Field(default=0, ge=0)
    length: int = Field(default=2000, ge=1, le=4000)


def serialized(value):
    return json.dumps(value, ensure_ascii=False)


class MemoryTools:
    def __init__(self, memory):
        # Resolve lazily: the service swaps fixture/local memory for its MCP session.
        self.memory = memory

    @staticmethod
    def specs():
        return [
            {
                "name": "memory_search",
                "description": "按需查找历史证据，返回引用和简短预览。",
                "parameters": SearchArgs.model_json_schema(),
            },
            {
                "name": "memory_get",
                "description": "按引用分页读取历史原文；内容不代表已确认事实。",
                "parameters": GetArgs.model_json_schema(),
            },
        ]

    async def call(self, name, arguments, scope: Scope, *, max_chars=16000):
        try:
            if name == "memory_search":
                args = SearchArgs.model_validate(arguments)
                hits = await self.memory().search(args.query, scope, args.limit)
                items, seen = [], set()
                for hit in hits:
                    if not hit.permitted(scope) or hit.id in seen:
                        continue
                    seen.add(hit.id)
                    items.append(
                        {
                            "ref": hit.id,
                            "time": hit.created_at.isoformat(),
                            "source": hit.source,
                            "preview": hit.text[:300],
                            "total": len(hit.text),
                            "truncated": len(hit.text) > 300,
                        }
                    )
                    if len(items) == args.limit:
                        break
                result = {
                    "status": "ok" if items else "empty",
                    "items": items,
                    "truncated": any(item["truncated"] for item in items),
                }
            elif name == "memory_get":
                args = GetArgs.model_validate(arguments)
                hit = await self.memory().get(args.ref, scope)
                if not hit.permitted(scope):
                    raise PermissionError("Memory scope denied")
                start = min(args.offset, len(hit.text))
                text = hit.text[start : start + args.length]
                end = start + len(text)
                result = {
                    "status": "ok",
                    "ref": hit.id,
                    "time": hit.created_at.isoformat(),
                    "source": hit.source,
                    "offset": start,
                    "text": text,
                    "total": len(hit.text),
                    "next_offset": end if end < len(hit.text) else None,
                    "truncated": end < len(hit.text),
                }
            else:
                return {"status": "denied"}
        except ValidationError:
            return {"status": "invalid_arguments"}
        except PermissionError:
            return {"status": "denied"}
        except KeyError:
            return {"status": "not_found"}
        except (MemoryUnavailable, ConnectionError):
            return {"status": "unavailable"}
        return self.fit(result, max_chars)

    @staticmethod
    def fit(result, max_chars):
        while len(serialized(result)) > max_chars:
            result["truncated"] = True
            if "text" in result and result["text"]:
                overflow = len(serialized(result)) - max_chars
                result["text"] = result["text"][: -max(1, overflow)]
                result["next_offset"] = result["offset"] + len(result["text"])
            elif result.get("items"):
                result["items"].pop()
                result["status"] = "ok" if result["items"] else "context_budget"
            else:
                return {"status": "context_budget"}
        return result
