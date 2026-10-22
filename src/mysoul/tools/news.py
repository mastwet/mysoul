from hashlib import sha256

import httpx

from mysoul.domain import Event, Scope


class NewsReader:
    def __init__(self, sources=()):
        self.sources = set(sources)

    @staticmethod
    def as_event(source, text):
        return Event(
            source=source,
            content=text[:32000],
            scope=Scope(audience="public"),
            dedup_key="news:" + sha256((source + text).encode()).hexdigest(),
            trust="data",
        )

    async def read(self, source):
        if source not in self.sources or not source.startswith("https://"):
            raise PermissionError("News source must be explicitly allowlisted HTTPS")
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            async with client.stream("GET", source) as response:
                response.raise_for_status()
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 64000:
                        raise ValueError("News exceeds byte limit")
        return self.as_event(source, data.decode("utf-8", errors="replace"))
