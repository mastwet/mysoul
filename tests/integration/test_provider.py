import os

import httpx
import pytest

from mysoul.domain import ContextBundle, ModelLimits
from mysoul.provider import OpenAICompatibleModel, ProviderError


@pytest.mark.parametrize(
    "message",
    [
        {"content": "invalid JSON"},
        {"content": '{"activity":"work","unexpected":true}'},
        {"refusal": "declined", "content": None},
    ],
)
async def test_malformed_output_and_refusal_are_bounded(message):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json={"choices": [{"message": message}]})

    model = OpenAICompatibleModel(
        "https://provider.test/v1", "raw-id", "secret", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ProviderError):
        await model.decide(ContextBundle(), ModelLimits(retries=1))
    assert len(calls) <= 2
    await model.close()


async def test_outbound_model_id_and_structured_tool_output():
    payloads = []

    def handler(request):
        import json

        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"done":false,"tool":"read_file","arguments":{"path":"a.txt"}}'
                            )
                        }
                    }
                ]
            },
        )

    model = OpenAICompatibleModel(
        "https://provider.test/v1", "deepseek-chat", "key", transport=httpx.MockTransport(handler)
    )
    result = await model.execute_step(ContextBundle(), [{"name": "read_file"}], ModelLimits())
    assert result.tool == "read_file"
    assert payloads[0]["model"] == "deepseek-chat"
    await model.close()


async def test_timeout_and_rate_limit_have_bounded_retries():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("timeout")
        return httpx.Response(429, json={"error": "limited"})

    model = OpenAICompatibleModel(
        "https://provider.test/v1", "id", "key", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ProviderError):
        await model.decide(ContextBundle(), ModelLimits(retries=1))
    assert len(calls) == 2
    await model.close()


@pytest.mark.live
async def test_real_provider_contract():
    if os.environ.get("MYSOUL_VALIDATE_PROVIDER") != "1":
        pytest.skip("Explicit real-provider validation opt-in is absent")
    model = OpenAICompatibleModel.from_environment()
    try:
        result = await model.decide(ContextBundle(task="Choose rest."), ModelLimits(retries=0))
        assert result.activity
    finally:
        await model.close()


async def test_prompt_and_schema_are_reserved_before_network_call(tmp_path):
    from mysoul.config import Settings
    from mysoul.domain import Event
    from mysoul.life import LifeController
    from mysoul.storage import StateStore

    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"activity":"rest"}'}}]}
        )

    model = OpenAICompatibleModel(
        "https://provider.test/v1", "id", "key", transport=httpx.MockTransport(handler)
    )
    store = StateStore(tmp_path / "s.db")
    life = LifeController(store, model, Settings(token_budget=1200))
    await life.choose([Event(content="x" * 3000, dedup_key="e")])
    assert calls == []
    await model.close()
    store.close()


async def test_unspecified_output_limit_is_omitted_from_the_actual_request():
    import json

    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"activity":"rest"}'}}]}
        )

    model = OpenAICompatibleModel(
        "http://127.0.0.1:8045/v1",
        "fixture-model",
        "fixture-key",
        transport=httpx.MockTransport(handler),
    )
    try:
        limits = ModelLimits(max_tokens=None)
        assert model.reservation(ContextBundle(), limits) > 0
        await model.decide(ContextBundle(), limits)
        assert "max_tokens" not in requests[0]
        assert "max_completion_tokens" not in requests[0]
    finally:
        await model.close()


async def test_large_configured_output_cap_does_not_starve_a_finite_goal(tmp_path):
    import json

    from mysoul.config import Settings
    from mysoul.domain import Goal
    from mysoul.service import SoulService

    payloads = []

    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"done":true}'}}]})

    model = OpenAICompatibleModel(
        "https://provider.test/v1", "fixture", "fixture-key", transport=httpx.MockTransport(handler)
    )
    async with SoulService(
        Settings(data_dir=tmp_path, model_output_limit=8192), model=model
    ) as soul:
        activity = await soul.start_goal(Goal(objective="Already complete"))
        assert activity.status == "completed"
        assert len(payloads) == 1
        assert payloads[0]["max_tokens"] <= 1024


@pytest.mark.parametrize("fence", ["```json", "```JSON", "```"])
async def test_complete_json_fence_is_accepted_for_decisions_and_steps(fence):
    contents = iter(['{"activity":"read_chat","reply":"Hello"}', '{"done":true}'])

    def handler(request):
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": fence + "\n" + next(contents) + "\n```"}}]},
        )

    model = OpenAICompatibleModel(
        "https://provider.test/v1", "fixture", "fixture-key", transport=httpx.MockTransport(handler)
    )
    try:
        assert (await model.decide(ContextBundle(), ModelLimits())).reply == "Hello"
        assert (await model.execute_step(ContextBundle(), [], ModelLimits())).done
    finally:
        await model.close()


@pytest.mark.parametrize(
    "content",
    [
        'Here is the answer:\n```json\n{"activity":"rest"}\n```',
        '```json\n{"activity":"rest"}\n```\nadditional instructions',
        '```json\n{"activity":"rest","unexpected":true}\n```',
        '```json\n{"activity":"rest"}\n```\n```json\n{"activity":"work"}\n```',
        '```json\n{"activity":"rest"',
    ],
)
async def test_fence_compatibility_preserves_strict_validation(content):
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    model = OpenAICompatibleModel(
        "https://provider.test/v1", "fixture", "fixture-key", transport=httpx.MockTransport(handler)
    )
    try:
        with pytest.raises(ProviderError):
            await model.decide(ContextBundle(), ModelLimits())
    finally:
        await model.close()
