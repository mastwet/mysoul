import asyncio

import pytest

from mysoul.config import Settings
from mysoul.domain import Event, Scope, StepDecision
from mysoul.model import ReplayModel
from mysoul.service import SoulService
from mysoul.storage import Conflict


async def test_owner_evidence_is_consolidated_during_explicit_reflection(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        await soul.owner_message("PRIVATE_CANARY: reports must be checked before completion")
        before = soul.store.load_subject().model_calls
        await soul.tick()
        recap = soul.recap.current()
        assert "PRIVATE_CANARY" in recap.text
        assert recap.author == "agent"
        assert recap.refs
        assert soul.store.evidence(recap.refs[0]).text.startswith("PRIVATE_CANARY")
        assert soul.store.load_subject().model_calls == before + 2  # choose + synthesis
        assert not soul.store.all("proposal")
        calls = soul.model.calls
        for _ in range(20):
            await soul.tick()
        assert soul.model.calls == calls
        await soul.receive(Event(
            content="@mysoul hi", dedup_key="group", scope=Scope(audience="group", conversation="g")
        ))
        assert "PRIVATE_CANARY" not in soul.model.payloads[-1]


async def test_failed_synthesis_retains_raw_segments_without_retry_storm(tmp_path):
    class Broken(ReplayModel):
        async def execute_step(self, context, tool_specs, limits):
            if "[recap]" in context.instructions:
                raise ValueError("synthesis failed")
            return await super().execute_step(context, tool_specs, limits)

    settings = Settings(data_dir=tmp_path)
    async with SoulService(settings, model=Broken()) as soul:
        await soul.owner_message("retain this raw segment")
        with pytest.raises(ValueError, match="synthesis failed"):
            await soul.tick()
        assert soul.recap.current().version == 0
        assert soul.store.all("recap_segment")[0]["status"] == "pending"
        ref = soul.store.all("recap_segment")[0]["id"]
    async with SoulService(settings) as soul:
        for _ in range(20):
            await soul.tick()
        assert soul.model.calls == 0
        assert soul.store.evidence(ref).text == "retain this raw segment"


async def test_clear_during_synthesis_cannot_restore_old_context(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()

    class Delayed(ReplayModel):
        async def execute_step(self, context, tool_specs, limits):
            if "[recap]" in context.instructions:
                entered.set()
                await release.wait()
                return StepDecision(done=True, note="STALE_PRIVATE_CANARY")
            return await super().execute_step(context, tool_specs, limits)

    async with SoulService(Settings(data_dir=tmp_path), model=Delayed()) as soul:
        await soul.owner_message("STALE_PRIVATE_CANARY")
        task = asyncio.create_task(soul.tick())
        await asyncio.wait_for(entered.wait(), 2)
        soul.recap.clear(0)
        release.set()
        with pytest.raises(Conflict):
            await task
        for _ in range(5):
            await soul.tick()
        assert soul.recap.current().text == ""
        assert all(s["status"] == "cleared" for s in soul.store.all("recap_segment"))
        assert soul.store.events()[0].content == "STALE_PRIVATE_CANARY"


async def test_recap_budget_denial_preserves_segments(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path, model_call_limit=1)) as soul:
        await soul.owner_message("save evidence even when budget is spent")
        await soul.tick()
        assert soul.recap.current().version == 0
        assert soul.store.all("recap_segment")[0]["status"] == "pending"
        assert soul.model.calls == 1
