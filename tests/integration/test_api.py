import pytest
from fastapi.testclient import TestClient

from mysoul.api import create_app
from mysoul.config import Settings
from mysoul.domain import Goal


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path), token="operator-token")
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        client.headers["Authorization"] = "Bearer operator-token"
        csrf = client.get("/api/session").json()["csrf"]
        client.headers.update({"Origin": "http://127.0.0.1:8765", "X-CSRF-Token": csrf})
        yield client


def test_unauthenticated_mutations_and_invalid_origins(client):
    assert client.get("/api/status").status_code == 200
    assert (
        client.post("/api/chat", json={"text": "hello"}, headers={"Authorization": ""}).status_code
        == 401
    )
    assert (
        client.post(
            "/api/chat", json={"text": "hello"}, headers={"Origin": "https://evil.test"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/chat", json={"text": "hello"}, headers={"X-CSRF-Token": "wrong"}
        ).status_code
        == 403
    )
    assert client.post("/api/chat", json={"text": "hello"}).json()["choice"] == "owner_served"


def test_stale_recap_edits_and_clear(client):
    assert (
        client.post(
            "/api/recap", json={"expected_version": 0, "text": "first", "refs": []}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/recap", json={"expected_version": 0, "text": "stale", "refs": []}
        ).status_code
        == 409
    )
    assert client.post("/api/recap/clear", json={"expected_version": 1}).json()["text"] == ""
    assert len(client.get("/api/recap/history").json()) == 3


def test_stale_approval_hashes_and_real_skill_workflow(client):
    client.post("/api/chat", json={"text": "report was not verified"})
    refs = [e["id"] for e in client.get("/api/evidence").json()]
    proposal = client.post(
        "/api/skills/propose", json={"text": "# Work\nProcedure: verify\n", "evidence_refs": refs}
    ).json()
    assert client.post(f"/api/skills/{proposal['id']}/test", json={}).json()["objective_pass"]
    bad = {"expected_base_hash": proposal["base_hash"], "approved_candidate_hash": "wrong"}
    assert client.post(f"/api/skills/{proposal['id']}/approve", json=bad).status_code == 409
    bad["approved_candidate_hash"] = proposal["candidate_hash"]
    assert client.post(f"/api/skills/{proposal['id']}/approve", json=bad).status_code == 200
    assert (
        client.post(
            "/api/skills/rollback", json={"target_version": proposal["base_hash"]}
        ).status_code
        == 200
    )


def test_cancelling_completed_work_and_redacted_errors(client):
    goal = Goal(objective="already done", status="completed")
    client.app.state.soul.store.save_goal(goal)
    response = client.post(f"/api/goals/{goal.id}/cancel", json={})
    assert response.status_code == 409
    assert "Traceback" not in response.text
    assert client.get("/api/effects/missing").status_code == 404


def test_persona_and_mode_are_persisted(client):
    assert (
        client.post(
            "/api/persona", json={"expected_version": 0, "public": "A careful companion."}
        ).status_code
        == 200
    )
    assert client.post("/api/life", json={"mode": "quiet", "fatigue": 0.5}).status_code == 200
    body = client.get("/api/status").json()
    assert body["state"]["mode"] == "quiet" and body["state"]["fatigue"] == 0.5
    assert body["persona"]["public"] == "A careful companion."
    assert client.get("/api/persona/history").json()[0]["public"] == "A careful companion."


def test_persona_version_conflict_and_memory_search(client):
    body = client.get("/api/status").json()
    sections = body["persona"]["sections"]
    sections["identity"] = "Updated private identity"
    update = client.post(
        "/api/persona",
        json={
            "expected_version": body["persona"]["version"],
            "public": body["persona"]["public"],
            "sections": sections,
        },
    )
    assert update.status_code == 200
    stale = client.post(
        "/api/persona", json={"expected_version": body["persona"]["version"], "public": "stale"}
    )
    assert stale.status_code == 409
    client.post("/api/chat", json={"text": "蓝鲸住在海洋"})
    hits = client.get("/api/memory/search", params={"q": "蓝鲸"}).json()
    assert any("蓝鲸" in item["text"] for item in hits)


def test_operator_status_exposes_budget_limits_without_credentials(client):
    body = client.get("/api/status").json()
    assert body["limits"] == {
        "model_calls": 100,
        "tokens": 50000,
        "context_chars": 131072,
        "request_timeout": 120.0,
    }
    assert "operator_token" not in body
    assert "api_key" not in body
