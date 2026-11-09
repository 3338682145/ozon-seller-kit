from fastapi.testclient import TestClient
from collector.api import create_app
from collector.config import Settings
from collector.monitoring.incidents import report_incident
from collector.storage.models import Incident

def test_incident_dedup_escalation_and_verified_recovery(rig):
    with rig["sf"].begin() as db:
        incident = report_incident(db,"mock","storage_unavailable", severity="P2")
        db.flush()
        incident_id = incident.id
    with rig["sf"].begin() as db:
        report_incident(db,"mock","storage_unavailable", severity="P1")
    app = create_app(settings=Settings(api_key="operator", admin_key="admin"),session_factory=rig["sf"])
    c = TestClient(app)
    url = f"/api/v1/incidents/{incident_id}/verify-recovery"
    evidence = {"evidence_ref":"incident-ticket-123", "checks":{"storage_integrity":True, "job_completion":False}}
    assert c.post(url,headers={"x-api-key":"operator"},json=evidence).status_code == 403
    assert c.post(url,headers={"x-api-key":"admin"},json=evidence).status_code == 409
    evidence["checks"]["job_completion"] = True
    assert c.post(url,headers={"x-api-key":"admin"},json=evidence).status_code == 200
    with rig["sf"]() as db:
        i = db.get(Incident,incident_id)
        assert (i.severity,i.occurrence_count,i.status) == ("P1",2,"resolved")
        assert i.recovered_at is not None
        assert i.actions[-1]["evidence_ref"] == "incident-ticket-123"
