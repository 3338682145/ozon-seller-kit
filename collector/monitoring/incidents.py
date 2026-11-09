"""Deterministic error dedup/escalation. Agent may propose, never auto-run shell."""
from __future__ import annotations
from sqlalchemy.orm import Session
from collector.storage.models import Incident, utc_now
from collector.storage.bulk import stable_id

SEVERITY_RANK = {"P3": 3, "P2": 2, "P1": 1, "P0": 0}


def report_incident(db: Session, source_id: str, code: str, *, severity: str = "P2", summary: str = "") -> Incident:
    if severity not in SEVERITY_RANK:
        raise ValueError("unknown incident severity")
    key = stable_id(f"incident:{source_id}:{code}")
    item = db.query(Incident).filter(Incident.dedup_key == key).one_or_none()
    if item:
        item.occurrence_count += 1
        item.last_seen_at = utc_now()
        if SEVERITY_RANK[severity] < SEVERITY_RANK[item.severity]:
            item.severity = severity
        item.status = "open"
        return item
    item = Incident(dedup_key=key, source_id=source_id, error_code=code,
                    severity=severity, summary=summary or f"{source_id}: {code}", status="open")
    db.add(item)
    return item


def verify_incident_recovery(db: Session, incident_id: str, *, checks: dict[str, bool],
                             evidence_ref: str, approver: str) -> bool:
    """Record explicit recovery checks; do not execute repair commands.

    All checks must be positive, an evidence link required, P0/P1 demand an
    accountable human approver. An empty set of checks never passes.
    """
    incident = db.get(Incident, incident_id)
    if incident is None:
        return False
    if not checks or not all(v is True for v in checks.values()) or not evidence_ref or len(evidence_ref) > 128:
        return False
    if incident.severity in {"P0", "P1"} and not approver:
        return False
    allowed = {"source_health", "storage_integrity", "job_completion", "permissions_verified", "backup_recovery"}
    if not set(checks).issubset(allowed):
        return False
    incident.actions = [*(incident.actions or []), {"type": "recovery_verified", "checks": checks,
                         "evidence_ref": evidence_ref, "approver": approver, "at": utc_now().isoformat()}]
    incident.status = "resolved"
    incident.recovered_at = utc_now()
    return True
