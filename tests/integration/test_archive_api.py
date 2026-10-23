import pytest
from fastapi.testclient import TestClient

from mysoul.api import create_app
from mysoul.archives import ArchiveNode
from mysoul.config import Settings
from mysoul.domain import Scope
from tests.integration.test_timeline import turn


@pytest.fixture
def client(tmp_path):
    with TestClient(
        create_app(Settings(data_dir=tmp_path), token="test"), base_url="http://127.0.0.1:8765"
    ) as c:
        c.headers["Authorization"] = "Bearer test"
        c.headers.update(
            {
                "Origin": "http://127.0.0.1:8765",
                "X-CSRF-Token": c.get("/api/session").json()["csrf"],
            }
        )
        yield c


def test_timeline_paging_and_invalid_cursors(client):
    store = client.app.state.soul.store
    for n in range(55):
        turn(store, str(n))
    turn(store, "private", scope=Scope(conversation="secret", audience="group"))
    page = client.get("/api/timeline").json()
    assert len(page["items"]) == 50 and page["has_more"]
    older = client.get("/api/timeline", params={"before": page["next_before"]}).json()
    assert len(older["items"]) == 5
    assert "private" not in str(page) + str(older)
    for query in ["before=0", "after_change=-1", "limit=101", "before=4&after_change=1"]:
        assert client.get("/api/timeline?" + query).status_code in {400, 422}
    assert client.get("/api/timeline", headers={"Authorization": ""}).status_code == 401


def test_archive_scope_security_and_queued_version(client):
    soul = client.app.state.soul
    archive = ArchiveNode(
        id="secret",
        level=1,
        first_seq=1,
        last_seq=1,
        start_time="2026-10-23",
        end_time="2026-10-23",
        scope=Scope(conversation="secret", audience="group"),
        source_hash="h",
        text="private",
    )
    soul.store.put("archive_node", archive.id, archive.model_dump(mode="json"))
    assert client.get("/api/archives/secret").status_code == 403
    assert client.get("/api/archives/missing").status_code == 404
    assert client.get("/api/archives").status_code == 200
    for headers in [{"Origin": "http://evil.test"}, {"X-CSRF-Token": "bad"}]:
        assert (
            client.post(
                "/api/archives/run", json={"expected_version": 0}, headers=headers
            ).status_code
            == 403
        )
    assert client.post("/api/archives/run", json={"expected_version": 99}).status_code == 409
    assert client.post("/api/archives/run", json={"expected_version": 0}).status_code == 202


def test_manual_archive_job_is_durable_and_version_bound(client):
    from mysoul.archives import CompressionPolicy

    soul = client.app.state.soul
    for n in range(12):
        turn(soul.store, str(n))
    soul.compression.set_policy(CompressionPolicy(raw_trigger=10, raw_batch=4))
    response = client.post("/api/archives/run", json={"expected_version": 1})
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    assert run_id and soul.store.get("compression_run", run_id)
    assert client.post("/api/archives/run", json={"expected_version": 0}).status_code == 409
