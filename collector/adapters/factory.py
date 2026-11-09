"""Production adapter selection: no implicit live Buyer access."""
from __future__ import annotations
from collector.adapters.mock import MockAdapter
from collector.adapters.legacy_seller import SellerLegacyAdapter, UnimplementedAdapter, ALLOWED_ENDPOINTS
from collector.adapters.buyer_snapshot import BuyerSnapshotAdapter
from collector.config import Settings
from collector.sessions.credentials import VaultKV2Resolver
from collector.errors import PermissionLost, SourceNotImplemented


def make_adapter_factory(settings: Settings, session_factory):
    def factory(source_id, policy):
        if source_id == "mock":
            return MockAdapter(settings.sample_path)
        if source_id == "seller_p7":
            return UnimplementedAdapter()
        if source_id in ALLOWED_ENDPOINTS:
            if not settings.vault_addr or not settings.vault_token:
                raise PermissionLost("Vault not configured for Seller")
            from collector.storage.models import DataSource, CredentialStatus, utc_now
            with session_factory() as db:
                source = db.get(DataSource, source_id)
                ref = source.credential_ref if source else None
                status = db.get(CredentialStatus, ref) if ref else None
            if not ref or not status or status.status != "active":
                raise PermissionLost("approved active Seller credential reference required")
            expiry = status.expires_at
            if expiry is not None and (expiry.replace(tzinfo=utc_now().tzinfo) if expiry.tzinfo is None else expiry) <= utc_now():
                raise PermissionLost("Seller credential reference expired")
            return SellerLegacyAdapter(source_id, VaultKV2Resolver(settings.vault_addr, settings.vault_token, settings.vault_mount), ref, policy.timeout_seconds)
        if source_id.startswith("buyer_"):
            return BuyerSnapshotAdapter(source_id)
        raise SourceNotImplemented(source_id)
    return factory
