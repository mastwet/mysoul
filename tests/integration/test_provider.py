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
