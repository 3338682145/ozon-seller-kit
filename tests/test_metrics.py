from fastapi.testclient import TestClient
from collector.api import create_app
from collector.config import Settings
from collector.monitoring.incidents import report_incident

def test_prometheus_exposes_bounded_control_plane_gauges(rig):
    j = rig["jobs"].create(source_id="mock",endpoint="sample",kind="sku",payload={})
    with rig["sf"].begin() as db:
        report_incident(db, "mock", "database_unavailable",severity="P1")
    app = create_app(settings=Settings(api_key="a",admin_key="b"),session_factory=rig["sf"])
    response = TestClient(app).get("/metrics")
    assert response.status_code == 200
    assert 'ozon_collection_jobs{status="pending"} 1.0' in response.text
    assert 'ozon_open_incidents{severity="P1"} 1.0' in response.text
    assert 'ozon_live_workers 0.0' in response.text
