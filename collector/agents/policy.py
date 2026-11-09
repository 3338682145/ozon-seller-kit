"""Human-in-the-loop decisions. No arbitrary SQL, Shell, DDL or restore calls."""
from __future__ import annotations
from datetime import timedelta
from sqlalchemy.orm import Session
from collector.storage.models import AgentApproval, AgentDecision, utc_now, uuid_str
from collector.errors import PolicyViolation
from collector.scheduler.jobs import contains_secret_keys

READ_ONLY = {
    "get_collection_status", "get_source_health", "get_collection_coverage", "inspect_collection_errors",
    "get_worker_metrics", "check_database_health", "check_data_quality", "find_duplicate_records",
    "analyze_slow_queries", "inspect_storage_usage", "check_backup_status", "inspect_data_lineage"
}
PROPOSALS = {"schedule_collection_job", "pause_collection_source", "schema_migration", "delete_records", "restore_backup", "change_authorization"}
EXECUTABLE_AFTER_APPROVAL = {"schedule_collection_job", "pause_collection_source"}


def propose(db: Session, agent: str, operation: str, inputs: dict, rationale: str) -> dict:
    if operation not in PROPOSALS:
        raise PolicyViolation("operation is not in the approved runbook catalog")
    if contains_secret_keys(inputs):
        raise PolicyViolation("credential material is prohibited in Agent proposals")
    ticket_id, session_id = uuid_str(), uuid_str()
    d = AgentDecision(agent=agent, ticket_id=ticket_id, session_id=session_id,
                      decision=operation, rationale=rationale[:2048],
                      inputs={k: v for k, v in inputs.items() if k not in {"cookie", "token", "secret"}},
                      assignment={"type": "human_approval", "status": "pending"},
                      report={"status": "awaiting_approval"})
    db.add(d)
    db.flush()
    a = AgentApproval(decision_id=d.id, operation=operation, status="pending", expires_at=utc_now()+timedelta(hours=1))
    db.add(a)
    db.flush()
    return {"ticket_id": ticket_id, "session_id": session_id, "decision_id": d.id,
            "approval_id": a.id, "assignment": "human", "report": "awaiting_approval"}


def authorize_approval(db: Session, approval_id: str, approver: str) -> AgentDecision:
    approval = db.get(AgentApproval, approval_id)
    if approval is None or approval.status != "pending":
        raise PolicyViolation("approval missing or already resolved")
    expiry = approval.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=utc_now().tzinfo)
    if expiry < utc_now():
        approval.status = "expired"
        raise PolicyViolation("approval expired")
    decision = db.get(AgentDecision, approval.decision_id)
    if approval.operation not in EXECUTABLE_AFTER_APPROVAL:
        raise PolicyViolation("high-risk operation requires external change control")
    approval.status, approval.approver, approval.approved_at = "approved", approver, utc_now()
    return decision
