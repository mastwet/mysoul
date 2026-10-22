import json
from contextlib import contextmanager

import httpx
import pytest
from fastapi.testclient import TestClient

from mysoul.api import create_app
from mysoul.config import Settings
from mysoul.provider import OpenAICompatibleModel
from mysoul.service import SoulService
from mysoul.storage import Conflict


@pytest.fixture
def provider(monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"activity":"rest","rationale":"connected"}'}}]
            },
        )

    original = OpenAICompatibleModel.__init__

    def initialize(self, url, model, key, **kwargs):
        original(self, url, model, key, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(OpenAICompatibleModel, "__init__", initialize)
    return requests


@contextmanager
def connect(settings):
    client = TestClient(create_app(settings, token="operator"), base_url="http://127.0.0.1:8765")
    with client:
        client.headers["Authorization"] = "Bearer operator"
        client.headers.update(
            {
                "Origin": "http://127.0.0.1:8765",
                "X-CSRF-Token": client.get("/api/session").json()["csrf"],
            }
        )
        yield client


def values(**changes):
    return (
        dict(
            mode="provider",
            url="https://provider.test/v1",
            model="raw-id",
            api_key="private-test-key",
            expected_version=0,
        )
        | changes
    )


def test_save_activate_restart_and_secret_redaction(tmp_path, provider):
    settings = Settings(data_dir=tmp_path)
    with connect(settings) as client:
        assert client.get("/api/model").json()["mode"] == "replay"
        saved = client.post("/api/model", json=values())
        assert saved.status_code == 200, saved.text
        assert saved.json()["key_present"] is True
        assert "private-test-key" not in saved.text
        soul = client.app.state.soul
        assert soul.model is soul.executor.model is soul.life.model
        assert soul.status()["model"]["mode"] == "provider"
        assert soul.model.model == "raw-id"
        assert client.post("/api/model", json=values()).status_code == 409
        # Changing hosts must never silently forward the existing key.
        assert (
            client.post(
                "/api/model",
                json=values(url="https://other.test/v1", api_key="", expected_version=1),
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/model", json=values(model="next-id", api_key="", expected_version=1)
            ).status_code
            == 200
        )
    with connect(Settings(data_dir=tmp_path)) as client:
        assert client.get("/api/model").json()["model"] == "next-id"
        assert client.app.state.soul.model.model == "next-id"
        assert (
            client.app.state.soul.model.client.headers["Authorization"] == "Bearer private-test-key"
        )
        assert "private-test-key" not in client.get("/api/status").text
    import os

    if os.name == "nt":
        assert b"private-test-key" not in (tmp_path / "model.settings").read_bytes()
    assert not provider  # saving does not make paid calls


def test_context_capacity_and_request_timeout_persist_across_restart(tmp_path, provider):
    with connect(Settings(data_dir=tmp_path)) as client:
        result = client.post(
            "/api/model", json=values(context_chars=262144, request_timeout=180)
        )
        assert result.status_code == 200
        assert result.json()["context_chars"] == 262144
        assert result.json()["request_timeout"] == 180
    with connect(Settings(data_dir=tmp_path)) as client:
        model = client.get("/api/model").json()
        assert model["context_chars"] == 262144
        assert model["request_timeout"] == 180
    assert not provider


def test_probe_is_private_bounded_budgeted_and_does_not_activate(tmp_path, provider):
    with connect(Settings(data_dir=tmp_path)) as client:
        client.post("/api/recap", json={"expected_version": 0, "text": "PRIVATE_RECAP", "refs": []})
        response = client.post("/api/model/test", json=values())
        assert response.status_code == 200, response.text
        assert response.json()["ok"]
        assert client.get("/api/model").json()["mode"] == "replay"
        assert not (tmp_path / "model.settings").exists()
        assert len(provider) == 1
        payload = json.loads(provider[0].content)
        assert payload["model"] == "raw-id"
        assert "PRIVATE_RECAP" not in str(payload)
        assert provider[0].headers["Authorization"] == "Bearer private-test-key"
        assert client.get("/api/status").json()["state"]["model_calls"] == 1
        client.app.state.soul.settings.model_call_limit = 1
        assert client.post("/api/model/test", json=values()).status_code == 409
        assert len(provider) == 1


def test_probe_reserves_its_actual_activity_schema_before_sending(tmp_path, provider):
    from mysoul.domain import ContextBundle, ModelLimits

    with connect(Settings(data_dir=tmp_path)) as client:
        model = OpenAICompatibleModel("https://provider.test/v1", "raw-id", "private-test-key")
        required = model.reservation(
            ContextBundle(task="Connection test. Choose rest."),
            ModelLimits(max_tokens=None, timeout=30, retries=0),
        )
        import asyncio

        asyncio.run(model.close())
        client.app.state.soul.settings.token_budget = required - 1
        response = client.post("/api/model/test", json=values())
        assert response.status_code == 409
        assert not provider


def test_probe_accepts_reasoning_provider_without_a_small_output_cap(tmp_path, monkeypatch):
    original = OpenAICompatibleModel.__init__
    payloads = []

    def handler(request):
        payload = json.loads(request.content)
        payloads.append(payload)
        if payload.get("max_tokens", 10000) < 512:
            return httpx.Response(
                200, json={"choices": [{"finish_reason": "length", "message": {"content": "```"}}]}
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": '{"activity":"rest"}'}}
                ]
            },
        )

    def initialize(self, url, model, key, **kwargs):
        original(self, url, model, key, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(OpenAICompatibleModel, "__init__", initialize)
    with connect(Settings(data_dir=tmp_path)) as client:
        result = client.post(
            "/api/model/test", json=values(output_token_limit=None, token_budget=None)
        )
        assert result.status_code == 200
        assert "max_tokens" not in payloads[0]
        assert client.get("/api/model").json()["mode"] == "replay"


def test_fenced_provider_reply_reaches_the_actual_chat_api(tmp_path, monkeypatch):
    original = OpenAICompatibleModel.__init__

    def handler(request):
        decision = {"activity": "read_chat", "chat_action": "reply", "reply": "Hello from provider"}
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "```json\n" + json.dumps(decision) + "\n```"}}]
            },
        )

    def initialize(self, url, model, key, **kwargs):
        original(self, url, model, key, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(OpenAICompatibleModel, "__init__", initialize)
    with connect(Settings(data_dir=tmp_path)) as client:
        assert client.post("/api/model", json=values()).status_code == 200
        result = client.post("/api/chat", json={"text": "hello"})
        assert result.status_code == 200
        assert result.json()["text"] == "Hello from provider"
        assert client.get("/api/status").json()["interactions"][-1]["text"] == "Hello from provider"


def test_unlimited_model_budget_persists_and_owner_chat_still_runs(tmp_path, provider):
    with connect(Settings(data_dir=tmp_path)) as client:
        response = client.post(
            "/api/model", json=values(output_token_limit=None, token_budget=None)
        )
        assert response.status_code == 200
        assert response.json()["output_token_limit"] is None
        assert response.json()["token_budget"] is None
        assert client.get("/api/status").json()["limits"]["tokens"] is None
        assert client.post("/api/chat", json={"text": "hello"}).status_code == 200
        assert "max_tokens" not in json.loads(provider[0].content)
    with connect(Settings(data_dir=tmp_path)) as client:
        assert client.get("/api/status").json()["limits"]["tokens"] is None


def test_explicit_zero_budget_still_blocks_provider_calls(tmp_path, provider):
    with connect(Settings(data_dir=tmp_path)) as client:
        assert (
            client.post(
                "/api/model", json=values(output_token_limit=512, token_budget=0)
            ).status_code
            == 200
        )
        assert (
            client.post("/api/model/test", json=values(api_key="", expected_version=1)).status_code
            == 409
        )
        client.post("/api/chat", json={"text": "hello"})
        assert not provider


def test_omitted_budget_fields_preserve_limits_for_existing_clients(tmp_path, provider):
    with connect(Settings(data_dir=tmp_path)) as client:
        assert (
            client.post(
                "/api/model", json=values(output_token_limit=512, token_budget=7000)
            ).status_code
            == 200
        )
        updated = client.post(
            "/api/model", json=values(model="next", api_key="", expected_version=1)
        ).json()
        assert updated["token_budget"] == 7000
        assert updated["output_token_limit"] == 512


def test_old_saved_settings_keep_runtime_budget_until_explicitly_changed(tmp_path, provider):
    import os

    from mysoul.model_settings import windows_protect

    with connect(Settings(data_dir=tmp_path)) as client:
        assert client.post("/api/model", json=values()).status_code == 200
    path = tmp_path / "model.settings"
    data = path.read_bytes()
    body = json.loads(windows_protect(data, decrypt=True) if os.name == "nt" else data)
    body.pop("token_budget")
    body.pop("output_token_limit")
    data = json.dumps(body).encode()
    path.write_bytes(windows_protect(data) if os.name == "nt" else data)
    with connect(Settings(data_dir=tmp_path, token_budget=7000)) as client:
        assert client.get("/api/model").json()["token_budget"] == 7000


@pytest.mark.parametrize("call_limit", [100, None])
async def test_unlimited_work_and_recap_run_above_previous_token_ceiling(tmp_path, call_limit):
    from mysoul.domain import ContextBundle, Event, Goal
    from mysoul.evolution import ProcedureReplayModel
    from mysoul.laputa import consolidate_recap

    class Model(ProcedureReplayModel):
        async def execute_step(self, context, tool_specs, limits):
            assert limits.max_tokens is None
            return await super().execute_step(context, tool_specs, limits)

    async with SoulService(
        Settings(data_dir=tmp_path, token_budget=None, model_call_limit=call_limit), model=Model(),
    ) as soul:
        state = soul.store.load_subject()
        state.tokens_used = 1_000_000
        state.model_calls = 1000 if call_limit is None else 0
        soul.store.save_transition(state.dispatch_epoch, state)
        activity = await soul.start_goal(Goal(objective="Write report.txt", token_limit=None))
        assert activity.status == "completed"
        await soul.life.choose([Event(content="hello", dedup_key="unlimited")], ContextBundle())
        assert soul.recap.pending()
        result = await consolidate_recap(soul, soul.store.load_subject().dispatch_epoch)
        assert result.version > 0
        await soul.activities.idle()


@pytest.mark.parametrize(
    "url",
    [
        "http://remote.test/v1",
        "https://user:secret@host/v1",
        "https://host/v1?api_key=private-test-key",
        "file:///tmp",
    ],
)
def test_invalid_inputs_auth_and_csrf_do_not_echo_secrets(tmp_path, url):
    with connect(Settings(data_dir=tmp_path)) as client:
        response = client.post("/api/model", json=values(url=url))
        assert response.status_code in {400, 422}
        assert "private-test-key" not in response.text
        response = client.post("/api/model", json=values(model={"key": "private-test-key"}))
        assert response.status_code == 422
        assert "private-test-key" not in response.text
        assert client.get("/api/model", headers={"Authorization": ""}).status_code == 401
        assert (
            client.post("/api/model", json=values(), headers={"X-CSRF-Token": ""}).status_code
            == 403
        )


async def test_busy_service_rejects_switch_and_replay_ignores_saved_provider(tmp_path, provider):
    from mysoul.model_settings import ModelUpdate

    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        soul.owner_turns = 1
        with pytest.raises(Conflict):
            await soul.configure_model(ModelUpdate(**values()))
        soul.owner_turns = 0
        await soul.configure_model(ModelUpdate(**values()))
    async with SoulService(Settings(data_dir=tmp_path, load_saved_model=False)) as soul:
        assert soul.status()["model"]["mode"] == "replay"
        assert not isinstance(soul.model, OpenAICompatibleModel)


async def test_failed_persistence_keeps_active_model_and_settings(tmp_path, provider, monkeypatch):
    from mysoul.model_settings import ModelUpdate

    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        before = soul.model

        def fail(configuration):
            raise OSError("disk full")

        monkeypatch.setattr(soul.model_settings, "save", fail)
        with pytest.raises(OSError):
            await soul.configure_model(ModelUpdate(**values()))
        assert soul.model is soul.life.model is soul.executor.model is before
        assert soul.model_configuration.mode == "replay"
        assert not (tmp_path / "model.settings").exists()


async def test_active_work_admission_blocks_model_changes(tmp_path, provider):
    import asyncio

    from mysoul.model_settings import ModelUpdate

    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        started, release = asyncio.Event(), asyncio.Event()

        async def work():
            with soul.admission.hold("work"):
                started.set()
                await release.wait()

        task = asyncio.create_task(work())
        await started.wait()
        try:
            with pytest.raises(Conflict):
                await soul.configure_model(ModelUpdate(**values()))
            assert soul.model_configuration.mode == "replay"
        finally:
            release.set()
            await task


async def test_saved_provider_candidate_factory_is_pinned_even_if_environment_changes(
    tmp_path, monkeypatch
):
    from mysoul.domain import Evidence
    from mysoul.evolution import RegressionCase
    from mysoul.model_settings import ModelUpdate

    requests = []
    original = OpenAICompatibleModel.__init__

    def handler(request):
        requests.append(request)
        context = json.loads(json.loads(request.content)["messages"][1]["content"])
        decision = (
            {"done": True}
            if context["step_results"]
            else {"tool": "write_file", "arguments": {"path": "answer.txt", "text": "verified"}}
        )
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(decision)}}]}
        )

    def initialize(self, url, model, key, **kwargs):
        original(self, url, model, key, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(OpenAICompatibleModel, "__init__", initialize)
    async with SoulService(Settings(data_dir=tmp_path)) as soul:
        await soul.configure_model(ModelUpdate(**values(output_token_limit=64)))
        monkeypatch.setenv("MYSOUL_PROVIDER_URL", "https://wrong.test/v1")
        monkeypatch.setenv("MYSOUL_API_KEY", "wrong-key")
        soul.store.add_evidence(Evidence(id="feedback", text="verify output"))
        proposal = soul.skills.propose("# Work\nProcedure: verify\n", ["feedback"])
        result = await soul.test_candidate(
            proposal.id,
            [
                RegressionCase(
                    id="provider-case",
                    objective="Write answer.txt",
                    expected_files={"answer.txt": "verified"},
                )
            ],
        )
        assert result["objective_pass"]
        assert requests
        assert all(r.url.host == "provider.test" for r in requests)
        assert all(r.headers["Authorization"] == "Bearer private-test-key" for r in requests)
        assert all(json.loads(r.content)["max_tokens"] == 64 for r in requests)


def test_failed_probe_is_not_retried_or_saved_and_key_is_not_in_error(tmp_path, monkeypatch):
    requests, clients = [], []
    original = OpenAICompatibleModel.__init__

    def handler(request):
        requests.append(request)
        return httpx.Response(401, json={"error": "private-test-key"})

    def initialize(self, url, model, key, **kwargs):
        original(self, url, model, key, transport=httpx.MockTransport(handler))
        clients.append(self.client)

    monkeypatch.setattr(OpenAICompatibleModel, "__init__", initialize)
    with connect(Settings(data_dir=tmp_path)) as client:
        result = client.post("/api/model/test", json=values())
        assert result.status_code == 400
        assert "private-test-key" not in result.text
        assert len(requests) == 1
        assert clients[0].is_closed
        assert client.get("/api/model").json()["mode"] == "replay"
        assert not (tmp_path / "model.settings").exists()


def test_probe_runs_above_old_call_ceiling_with_unlimited_calls(tmp_path, provider):
    with connect(Settings(data_dir=tmp_path, model_call_limit=None, token_budget=None)) as client:
        soul = client.app.state.soul
        state = soul.store.load_subject()
        state.model_calls = 1000
        soul.store.save_transition(state.dispatch_epoch, state)
        assert client.post("/api/model/test", json=values()).status_code == 200
        assert soul.store.load_subject().model_calls == 1001
