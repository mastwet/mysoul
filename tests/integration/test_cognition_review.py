import asyncio

from mysoul.config import Settings
from mysoul.domain import Goal, StepDecision
from mysoul.model import ReplayModel
from mysoul.persona import PersonaChange, ReflectionDecision
from mysoul.service import SoulService


async def test_interrupted_turn_after_migration_is_recovered_on_each_restart(tmp_path):
    started = asyncio.Event()

    class Blocked(ReplayModel):
        async def decide(self, context, limits):
            started.set()
            await asyncio.Event().wait()

    async with SoulService(Settings(data_dir=tmp_path), Blocked()) as soul:
        assert soul.store.get('cognitive_migration', 'v1') is not None
        turn = asyncio.create_task(soul.owner_message('UNFINISHED_OWNER_REQUEST'))
        await started.wait()
        turn.cancel()
        try:
            await turn
        except asyncio.CancelledError:
            pass
    async with SoulService(Settings(data_dir=tmp_path), ReplayModel()) as soul:
        window = soul.cognition.sources.pending_window(16000)
        assert window is not None
        assert [(s.role, s.text) for s in window.slices][0] == (
            'user', 'UNFINISHED_OWNER_REQUEST')
        assert window.slices[1].role == 'failure'
        assert 'unfinished' in window.slices[1].text.lower()
        assert (await soul.cognition.run_due(force=True)).status == 'completed'
    async with SoulService(Settings(data_dir=tmp_path), ReplayModel()) as soul:
        assert soul.cognition.sources.pending_window(16000) is None


async def test_task_result_and_final_note_reach_actual_recap_payload(tmp_path):
    model = ReplayModel([
        StepDecision(tool='read_file', arguments={'path': 'report.txt'}),
        StepDecision(done=True, note='FINAL_RESULT: Launch moved to Thursday.'),
    ])
    async with SoulService(Settings(data_dir=tmp_path), model) as soul:
        (tmp_path / 'workspace' / 'report.txt').write_text(
            'UNIQUE_RESULT_3437: Launch postponed to Thursday.', encoding='utf-8')
        activity = await soul.start_goal(Goal(objective='Read report', token_limit=None))
        assert activity.status == 'completed'
        soul.activities.capture_feedback()
        run = await soul.cognition.run_due(force=True)
        assert run.status == 'completed'
        payload = next(p for p in model.payloads if '[recap]' in p)
        assert 'UNIQUE_RESULT_3437' in payload
        assert 'FINAL_RESULT' in payload
        assert 'read_file' in payload
        assert soul.cognition.status()['pending'] == 0
        soul.activities.capture_feedback()
        assert soul.cognition.status()['pending'] == 0


async def test_successive_world_additions_preserve_unseen_base(tmp_path):
    class Learning(ReplayModel):
        async def reflect(self, context, limits):
            self.payloads.append(context.payload())
            return ReflectionDecision(changes=[PersonaChange(
                target='world', text=f'NEW_WORLD_{soul.persona.current().version}',
                reason='Evidence supported addition', evidence_refs=[context.evidence[0].id],
            )], reason='Supported learning')

    async with SoulService(Settings(data_dir=tmp_path), Learning()) as soul:
        sections = soul.persona.current().sections.model_dump() | {'world': 'OLD_WORLD_A'}
        soul.persona.update(0, sections=sections)
        for marker in ('first', 'second'):
            await soul.owner_message(marker)
            assert (await soul.cognition.run_due(force=True)).status == 'completed'
        assert soul.persona.current().sections.world == 'OLD_WORLD_A\n\nNEW_WORLD_1\n\nNEW_WORLD_2'
        reflection = [p for p in soul.model.payloads if '[persona-reflection]' in p]
        assert len(reflection) == 2
        assert all('OLD_WORLD_A' not in p for p in reflection)
