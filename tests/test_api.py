from fastapi.testclient import TestClient
from collector.api import create_app
from collector.config import Settings
from collector.storage.models import Keyword, Product


def make_client(rig):
    app = create_app(settings=Settings(database_url="sqlite:///unused", api_key="test-operator", admin_key="test-admin", allow_insecure_dev=False), session_factory=rig["sf"])
    return TestClient(app)


def test_api_auth_openapi_job_and_health(rig):
    client = make_client(rig)
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/api/v1/sources").status_code == 401
    h = {"x-api-key": "test-operator"}
    assert client.get("/api/v1/sources", headers=h).status_code == 200
    r = client.post("/api/v1/jobs", headers={**h, "Idempotency-Key": "api-once"}, json={"source_id": "mock", "endpoint": "sample", "kind": "keyword", "payload": {"keyword": "ант"}})
    assert r.status_code == 201, r.text
    jid = r.json()["id"]
    assert client.get(f"/api/v1/jobs/{jid}", headers=h).json()["status"] == "pending"
    assert client.get("/api/v1/agents/collector/status", headers=h).status_code == 200
    assert client.get("/api/v1/database/health", headers=h).json()["dialect"] == "sqlite"
    assert client.post("/mark_dead", headers=h, json={"credential_ref": "dev/ref"}).status_code == 403
    assert client.post(f"/api/v1/jobs/{jid}/cancel", headers=h).json()["status"] == "canceled"


def test_agent_approval_default_proposal_only(rig):
    client = make_client(rig)
    operator = {"x-api-key": "test-operator"}
    decision = client.post("/api/v1/agents/collector/pause-proposal?source_id=mock", headers=operator)
    assert decision.status_code == 200, decision.text
    from collector.storage.models import DataSource
    with rig["sf"]() as db:
        assert db.get(DataSource, "mock").enabled  # no auto mutation
    appr = decision.json()["approval_id"]
    assert client.post(f"/api/v1/agents/approvals/{appr}/approve", headers=operator).status_code == 403
    yes = client.post(f"/api/v1/agents/approvals/{appr}/approve", headers={"x-api-key": "test-admin"})
    assert yes.status_code == 200
    with rig["sf"]() as db:
        assert db.get(DataSource, "mock").blocked


def test_viewer_role_cannot_submit_or_pause_jobs(rig):
    app = create_app(settings=Settings(database_url="sqlite:///unused", api_key="operator", admin_key="admin", viewer_key="read-only"), session_factory=rig["sf"])
    client = TestClient(app)
    headers = {"x-api-key": "read-only"}
    assert client.get("/api/v1/products", headers=headers).status_code == 200
    assert client.post("/api/v1/jobs", headers=headers, json={"source_id":"mock", "endpoint":"sample", "kind":"sku"}).status_code == 403
    assert client.post("/api/v1/agents/collector/pause-proposal?source_id=mock", headers=headers).status_code == 403
