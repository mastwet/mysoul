import asyncio

import pytest

from mysoul.config import Settings
from mysoul.domain import Event, Scope
from mysoul.phone.replay import ReplayPhone
from mysoul.service import SoulService


def test_environment_defaults_and_invalid_mode(monkeypatch, tmp_path):
    monkeypatch.setenv("MYSOUL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MYSOUL_MODEL_MODE", "replay")
    assert Settings.from_environment().data_dir == tmp_path
    monkeypatch.setenv("MYSOUL_MODEL_MODE", "typo")
    with pytest.raises(ValueError):
        Settings.from_environment()


async def test_background_life_loop_consumes_phone_and_rests_quietly(tmp_path):
    events = [
        Event(content="hello", dedup_key="loop", scope=Scope(audience="group", conversation="g"))
    ]
    async with SoulService(Settings(data_dir=tmp_path), phone=ReplayPhone(events)) as soul:
        stop = asyncio.Event()
        await soul.tick()
        assert len(soul.store.events()) == 1
        count = soul.model.calls
        await soul.tick()
        await soul.tick()
        assert soul.model.calls == count
        stop.set()
        await soul.run_loop(stop)


async def test_two_subject_processes_cannot_share_one_data_root(tmp_path):
    from mysoul.storage import Conflict

    async with SoulService(Settings(data_dir=tmp_path)):
        with pytest.raises(Conflict):
            async with SoulService(Settings(data_dir=tmp_path)):
                pass


async def test_queued_phone_events_survive_restart(tmp_path):
    event = Event(
        content="retained inbox",
        dedup_key="pending",
        scope=Scope(audience="group", conversation="g"),
    )
    async with SoulService(Settings(data_dir=tmp_path), phone=ReplayPhone([event])) as soul:
        soul.executor.running = "busy"
        await soul.tick()
        soul.executor.running = None
    async with SoulService(Settings(data_dir=tmp_path), phone=ReplayPhone([event])) as soul:
        await soul.tick()
        assert len(soul.store.events()) == 1
        assert len(soul.store.all("interaction")) == 1


async def test_phone_burst_is_one_model_decision(tmp_path):
    events = [
        Event(content="hello", dedup_key=str(i), scope=Scope(audience="group", conversation="g"))
        for i in range(50)
    ]
    async with SoulService(Settings(data_dir=tmp_path), phone=ReplayPhone(events)) as soul:
        await soul.tick()
        assert soul.model.calls == 1
        assert len(soul.store.events()) == 50
