import pytest

from mysoul.config import Settings
from mysoul.domain import ActivityDecision, Scope, StepDecision
from mysoul.service import SoulService
from mysoul.storage import Conflict


class ChatModel:
    def __init__(self):
        self.contexts = []
        self.step_contexts = []

    async def decide(self, context, limits):
        self.contexts.append(context.model_copy(deep=True))
        return ActivityDecision(
            activity="read_chat", chat_action="reply", reply="The silver clock sang."
        )

    async def execute_step(self, context, tool_specs, limits):
        self.step_contexts.append(context.model_copy(deep=True))
        return StepDecision(done=True, note="A verified summary.")


async def test_persona_has_versioned_sections_and_private_projection(tmp_path):
    async with SoulService(Settings(data_dir=tmp_path), model=ChatModel()) as soul:
        profile = soul.persona.current()
        sections = profile.sections.model_dump()
        assert set(sections) == {
            "identity",
            "relationship",
            "redline",
            "user",
            "world",
            "dream",
            "dark",
            "mission",
        }
        sections["identity"] = "PRIVATE_IDENTITY_MARKER"
        sections["user"] = "PRIVATE_OWNER_MARKER"
        updated = soul.persona.update(profile.version, sections=sections, public="PUBLIC_PROFILE")
        with pytest.raises(Conflict):
            soul.persona.update(profile.version, public="stale")
        owner = await soul.context(Scope(), "hello")
        group = await soul.context(Scope(audience="group", conversation="g"), "hello")
        assert "PRIVATE_IDENTITY_MARKER" in owner.instructions
        assert "PRIVATE_OWNER_MARKER" in owner.instructions
        assert "PUBLIC_PROFILE" in group.instructions
        assert "PRIVATE_" not in group.payload()
        assert updated.version == profile.version + 1
    async with SoulService(Settings(data_dir=tmp_path), model=ChatModel()) as soul:
        assert soul.persona.current().sections.user == "PRIVATE_OWNER_MARKER"
        assert len(soul.persona.history()) == 2


async def test_dialogue_and_assistant_evidence_survive_restart_and_are_scoped(tmp_path):
    model = ChatModel()
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        first = await soul.owner_message("Tell a story about a silver clock.")
        reply_ref = "reply:" + first["event_id"]
        assert soul.store.evidence(reply_ref).text == "The silver clock sang."
        assert reply_ref in soul.recap.pending()
    async with SoulService(Settings(data_dir=tmp_path), model=model) as soul:
        await soul.owner_message("Continue that story.")
        history = model.contexts[-1].history
        assert [m.role for m in history[-2:]] == ["user", "assistant"]
        assert history[-1].content == "The silver clock sang."
        group = await soul.context(Scope(audience="group", conversation="g"), "hello")
        assert not group.history
        assert "silver clock" not in group.payload().lower()
        assert "不能当作主人真实经历" in model.contexts[-1].instructions
        from mysoul.laputa import consolidate_recap

        await consolidate_recap(soul, soul.store.load_subject().dispatch_epoch)
        recap_prompt = model.step_contexts[-1].instructions
        assert "Assistant replies are model-authored" in recap_prompt
        assert "never as owner biography" in recap_prompt
        assert "omit greetings, UI/tool acceptance logs" in recap_prompt


async def test_local_memory_finds_older_chinese_fact_instead_of_recent_noise(tmp_path):
    from mysoul.domain import Evidence
    from mysoul.memory import LocalMemory
    from mysoul.storage import StateStore

    store = StateStore(tmp_path / "state.sqlite")
    try:
        memory = LocalMemory(store)
        await memory.add(Evidence(id="fact", text="我给小猫取名蓝鲸。"))
        for i in range(40):
            await memory.add(Evidence(id=f"noise-{i}", text=f"无关消息 {i}"))
        hits = await memory.search("蓝鲸", Scope(), 5)
        assert hits[0].id == "fact"
        group = Scope(audience="group", conversation="g")
        assert not await memory.search("蓝鲸", group, 5)
    finally:
        store.close()
