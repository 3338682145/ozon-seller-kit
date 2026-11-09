"""Deterministic error dedup/escalation. Agent may propose, never auto-run shell."""
from __future__ import annotations
from sqlalchemy.orm import Session
from collector.storage.models import Incident
from collector.storage.bulk import stable_id

SEVERITY_RANK = {"P3": 3, "P2": 2, "P1": 1, "P0": 0}


def report_incident(db: Session, source_id: str, code: str, *, severity: str = "P2", summary: str = "") -> Incident:
    if severity not in SEVERITY_RANK:
        raise ValueError("unknown incident severity")
    key = stable_id(f"incident:{source_id}:{code}")
    item = db.query(Incident).filter(Incident.dedup_key == key).one_or_none()
    if item:
        item.occurrence_count += 1
        if SEVERITY_RANK[severity] < SEVERITY_RANK[item.severity]:
            item.severity = severity
        item.status = "open"
        return item
    item = Incident(dedup_key=key, source_id=source_id, error_code=code,
                    severity=severity, summary=summary or f"{source_id}: {code}", status="open")
    db.add(item)
    return item
