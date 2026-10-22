import json

import httpx
import pytest

from mysoul.config import Settings
from mysoul.domain import ContextBundle, ModelLimits, Scope
from mysoul.provider import OpenAICompatibleModel, ProviderError
from mysoul.service import SoulService


async def test_large_reply_is_valid_and_advertised_without_small_field_limit():
    text = "长篇故事。" * 1500

    def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps({"activity": "read_chat", "reply": text})}}
                ]
            },
        )

    model = OpenAICompatibleModel(
        "https://fixture.test/v1", "m", "k", transport=httpx.MockTransport(handler)
    )
    try:
        result = await model.decide(ContextBundle(), ModelLimits(max_tokens=None))
        assert result.reply == text
    finally:
        await model.close()


async def test_large_reply_is_saved_to_conversation_and_memory(tmp_path):
    from mysoul.domain import ActivityDecision

    reply = "长篇故事。" * 15000

    class Model:
        async def decide(self, context, limits):
            return ActivityDecision(activity="read_chat", reply=reply)

    async with SoulService(Settings(data_dir=tmp_path), model=Model()) as soul:
        result = await soul.owner_message("继续故事")
        assert result["text"] == reply
        assert soul.store.evidence("reply:" + result["event_id"]).text == reply
        assert len(soul.store.all("interaction")) == 1


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (
            400,
            {"error": {"code": "context_length_exceeded", "message": "secret-input"}},
            "context_limit",
        ),
        (401, {"error": "secret-key"}, "authentication"),
        (429, {"error": "secret-key"}, "rate_limit"),
    ],
)
async def test_safe_failure_categories_do_not_echo_provider_body(status, body, expected):
    model = OpenAICompatibleModel(
        "https://fixture.test/v1",
        "m",
        "k",
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body)),
    )
    try:
        with pytest.raises(ProviderError) as caught:
            await model.decide(ContextBundle(), ModelLimits())
        assert caught.value.code == expected
        assert "secret" not in str(caught.value)
    finally:
        await model.close()


async def test_timeout_is_recorded_as_failure_instead_of_assistant_memory(tmp_path):
    class SlowModel:
        async def decide(self, context, limits):
            raise TimeoutError

    async with SoulService(Settings(data_dir=tmp_path), model=SlowModel()) as soul:
        result = await soul.owner_message("hello")
        assert result["error"]["code"] == "timeout"
        assert "Model unavailable" not in result["text"]
        assert not soul.dialogue_history(Scope())[-1][1:]
        with pytest.raises(KeyError):
            soul.store.evidence("reply:" + result["event_id"])


async def test_complete_chat_reply_does_not_start_a_second_background_goal(tmp_path):
    from mysoul.domain import ActivityDecision

    class Model:
        async def decide(self, context, limits):
            return ActivityDecision(
                activity="work", chat_action="reply", reply="Here is the requested story."
            )

        async def execute_step(self, context, tool_specs, limits):
            raise AssertionError("A complete chat turn must not launch another model step")

    async with SoulService(Settings(data_dir=tmp_path), model=Model()) as soul:
        result = await soul.owner_message("Write a story")
        assert result["text"] == "Here is the requested story."
        assert not soul.store.all("goal")
        assert soul.store.load_subject().activity == "read_chat"


async def test_context_capacity_and_timeout_are_runtime_settings(tmp_path):
    from mysoul.domain import ActivityDecision, Scope

    class Model:
        async def decide(self, context, limits):
            assert limits.timeout == 150
            return ActivityDecision(activity="read_chat", reply="ok")

    async with SoulService(
        Settings(data_dir=tmp_path, context_chars=128000, request_timeout=150), model=Model()
    ) as soul:
        soul.recap.publish(0, "A" * 20000, [])
        assert len((await soul.context(Scope(), "hello")).recap) == 20000
        assert (await soul.owner_message("hello"))["text"] == "ok"
