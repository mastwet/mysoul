import argparse
import asyncio
import json
from pathlib import Path

from mysoul.config import Settings


def main():
    parser = argparse.ArgumentParser(description="mysoul: a bounded single-subject companion")
    parser.add_argument("command", choices=["serve", "replay"])
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--trace", type=Path)
    args = parser.parse_args()
    settings = Settings.from_environment()
    if args.data_dir:
        settings.data_dir = args.data_dir
    settings.port = args.port
    if args.command == "serve":
        import uvicorn

        from mysoul.api import create_app, operator_token

        token = operator_token(settings)
        print(f"Open http://127.0.0.1:{settings.port}/#token={token}", flush=True)
        uvicorn.run(
            create_app(settings, token=token),
            host=settings.host,
            port=settings.port,
            access_log=False,
        )
    else:
        if not args.trace:
            parser.error("replay requires --trace")
        # Replay command cannot construct a live provider or phone backend.
        settings.backend = "replay"
        settings.model_mode = "replay"
        settings.memory_backend = "fixture"
        settings.send_enabled = False
        asyncio.run(replay(settings, args.trace))


async def replay(settings, trace):
    from mysoul.phone.replay import ReplayPhone
    from mysoul.service import SoulService

    async with SoulService(settings, phone=ReplayPhone.from_jsonl(trace)) as soul:
        while True:
            batch = await soul.phone.observe(soul.phone_cursor)
            if not batch.events:
                break
            for event in batch.events:
                print(json.dumps(await soul.receive(event), ensure_ascii=False))
            soul.phone_cursor = batch.cursor
            soul.store.put("cursor", "phone", {"value": batch.cursor})


if __name__ == "__main__":
    main()
