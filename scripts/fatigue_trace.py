"""Paired simulated-clock experiment; outputs measurements, not psychological claims."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from mysoul.config import Settings
from mysoul.domain import Activity, ActivityDecision, Event, Goal
from mysoul.effects import EffectDispatcher
from mysoul.executor import Executor
from mysoul.life import LifeController
from mysoul.model import ReplayModel
from mysoul.storage import StateStore


async def trace(enabled):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        settings = Settings(data_dir=root, fatigue_enabled=enabled, fatigue_per_hour=0.8)
        store = StateStore(root / "state.sqlite")
        clock = [datetime(2026, 10, 22, tzinfo=UTC)]
        state = store.load_subject()
        state.updated_at = clock[0]
        store.save_transition(0, state)

        class TimedModel(ReplayModel):
            async def execute_step(self, *args):
                clock[0] += timedelta(minutes=45)
                return await super().execute_step(*args)

        model = TimedModel()
        life = LifeController(store, model, settings, lambda: clock[0])
        executor = Executor(
            store, model, EffectDispatcher(store), root / "graph.sqlite", settings, lambda: clock[0]
        )
        await executor.open()
        rows = []
        completed = 0
        for i in range(8):
            clock[0] = datetime(2026, 10, 22, tzinfo=UTC) + timedelta(hours=i)
            model.decisions.append(ActivityDecision(activity=Activity.WORK))
            decision = await life.choose([Event(dedup_key=str(i), content="bounded fixture task")])
            if decision.activity == Activity.WORK:
                result = await executor.start(
                    Goal(objective="Complete one deterministic fixture step", time_limit=3600)
                )
                completed += int(result.status == "completed")
            state = store.load_subject()
            rows.append(
                {"hour": i, "activity": decision.activity, "fatigue": round(state.fatigue, 3)}
            )
        await executor.close()
        result = {
            "fatigue_enabled": enabled,
            "trace": rows,
            "model_calls": state.model_calls,
            "reserved_tokens": state.tokens_used,
            "fixture_tasks_completed": completed,
        }
        store.close()
        return result


async def main():
    print(
        json.dumps(
            {
                "method": (
                    "Eight hourly events, 45-minute fixture work, "
                    "fatigue gain 0.8/h, recovery 0.4/h"
                ),
                "interpretation": (
                    "Synthetic scheduling comparison, not an intelligence or fatigue benchmark"
                ),
                "runs": [await trace(True), await trace(False)],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
