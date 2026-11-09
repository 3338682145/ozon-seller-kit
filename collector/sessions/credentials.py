"""Credential references only. Vault secret payload never goes to DB or Agents."""
from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import datetime, timezone
import os
import re
import httpx
from sqlalchemy.orm import Session
from collector.errors import PermissionLost
from collector.storage.models import CredentialStatus, DataSource, JobEvent, CollectionJob, utc_now


class CredentialResolver(ABC):
    @abstractmethod
    def resolve(self, ref: str) -> dict[str, str]: ...


class VaultKV2Resolver(CredentialResolver):
    """Use Vault KV2 HTTPS endpoint; tokens never leave server process."""
    def __init__(self, addr: str, token: str, mount: str = "secret"):
        if not addr.startswith("https://"):
            raise PermissionLost("Vault requires HTTPS in production")
        self.addr, self.token, self.mount = addr.rstrip("/"), token, mount

    def resolve(self, ref: str) -> dict[str, str]:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_/-]{0,199}", ref) or ".." in ref:
            raise PermissionLost("invalid credential reference")
        with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as c:
            resp = c.get(f"{self.addr}/v1/{self.mount}/data/{ref}", headers={"X-Vault-Token": self.token})
        if resp.status_code != 200:
            raise PermissionLost("Vault denied credential retrieval")
        return resp.json()["data"]["data"]


class DevEnvironmentResolver(CredentialResolver):
    """Tests/dev only; server admin must explicitly enable this provider."""
    def __init__(self, allowed: bool = False):
        if not allowed:
            raise PermissionLost("environment secrets disabled")

    def resolve(self, ref: str) -> dict[str, str]:
        if ref != "seller-dev":
            raise PermissionLost("unknown credential reference")
        keys = {"cookie": "SELLER_COOKIE", "user_agent": "SELLER_USER_AGENT", "company_id": "SELLER_COMPANY_ID", "uuid": "SELLER_UUID"}
        out = {k: os.getenv(v, "") for k, v in keys.items()}
        if not out["cookie"] or not out["company_id"]:
            raise PermissionLost("missing seller credentials")
        return out


def mark_dead(db: Session, credential_ref: str, reason: str = "revoked") -> None:
    record = db.get(CredentialStatus, credential_ref)
    if record is None:
        record = CredentialStatus(credential_ref=credential_ref)
        db.add(record)
    record.status = "revoked"
    record.updated_at = utc_now()
    db.flush()  # autoflush=False in runtime sessions; source credential_ref may have changed
    for source in db.query(DataSource).filter(DataSource.credential_ref == credential_ref):
        source.enabled, source.blocked, source.blocked_reason = False, True, "credential_revoked"
        db.query(CollectionJob).filter(CollectionJob.source_id == source.source_id, CollectionJob.status.in_(["pending", "retry_wait", "running"])).update({"status": "blocked", "last_error_code": "credential_revoked"}, synchronize_session=False)
