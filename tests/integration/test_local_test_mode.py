from fastapi.testclient import TestClient

from mysoul.api import create_app
from mysoul.config import Settings


def test_tokenless_local_session_can_chat_but_requires_origin_and_csrf(tmp_path):
    settings = Settings(data_dir=tmp_path, operator_auth_required=False, model_call_limit=None)
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        session = client.get("/api/session")
        assert session.status_code == 200
        assert session.json()["auth_required"] is False
        assert client.get("/api/status").json()["limits"]["model_calls"] is None
        headers = {"Origin": "http://127.0.0.1:8765", "X-CSRF-Token": session.json()["csrf"]}
        body = {"text": "hello"}
        assert client.post("/api/chat", json=body).status_code == 403
        assert client.post("/api/chat", json=body, headers=headers | {
            "Origin": "https://other.test",
        }).status_code == 403
        assert client.post("/api/chat", json=body, headers=headers | {
            "X-CSRF-Token": "wrong",
        }).status_code == 403
        assert client.get("/api/status", headers={"Host": "other.test"}).status_code == 400
        response = client.post("/api/chat", json=body, headers=headers)
        assert response.json()["choice"] == "owner_served"
    assert not (tmp_path / "operator.token").exists()
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as restarted:
        assert restarted.get("/api/status").status_code == 200


def test_default_local_session_still_requires_operator_token(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path)),
                    base_url="http://127.0.0.1:8765") as client:
        assert client.get("/api/session").status_code == 401
        assert client.get("/api/status").status_code == 401


def test_runtime_environment_accepts_unlimited_call_budget(monkeypatch):
    monkeypatch.setenv("MYSOUL_MODEL_CALL_LIMIT", "unlimited")
    monkeypatch.setenv("MYSOUL_OPERATOR_AUTH_REQUIRED", "false")
    settings = Settings.from_environment()
    assert settings.model_call_limit is None
    assert settings.operator_auth_required is False
    monkeypatch.setenv("MYSOUL_MODEL_CALL_LIMIT", "0")
    assert Settings.from_environment().model_call_limit == 0


def test_local_test_cli_starts_tokenless_without_a_call_ceiling(tmp_path, monkeypatch, capsys):
    import sys

    import uvicorn

    from mysoul.__main__ import main

    seen = {}

    def serve(app, **kwargs):
        with TestClient(app, base_url="http://127.0.0.1:8765") as client:
            seen.update(client.get("/api/status").json())
        assert kwargs["host"] == "127.0.0.1"

    monkeypatch.setattr(uvicorn, "run", serve)
    monkeypatch.setattr(sys, "argv", [
        "mysoul", "serve", "--local-test", "--data-dir", str(tmp_path),
    ])
    main()
    assert seen["limits"]["model_calls"] is None
    assert "#token=" not in capsys.readouterr().out


async def test_unlimited_calls_allow_reflection_and_candidate_after_100_calls(tmp_path):
    from mysoul.domain import Evidence
    from mysoul.service import SoulService

    async with SoulService(Settings(data_dir=tmp_path, model_call_limit=None,
                                    token_budget=None)) as soul:
        state = soul.store.load_subject()
        state.model_calls = 1000
        soul.store.save_transition(state.dispatch_epoch, state)
        soul.store.add_evidence(Evidence(id="feedback", text="Verify written artifacts."))
        proposal = await soul.reflect(["feedback"])
        result = await soul.test_candidate(proposal.id)
        assert result["objective_pass"]
        assert soul.store.load_subject().model_calls > 1001
