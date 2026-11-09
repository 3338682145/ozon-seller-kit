"""Production adapter selection: no implicit live Buyer access."""
from __future__ import annotations
from collector.adapters.mock import MockAdapter
from collector.adapters.legacy_seller import SellerLegacyAdapter, UnimplementedAdapter, ALLOWED_ENDPOINTS
from collector.adapters.buyer_snapshot import BuyerSnapshotAdapter
from collector.config import Settings
from collector.sessions.credentials import VaultKV2Resolver
from collector.errors import PermissionLost, SourceNotImplemented


def make_adapter_factory(settings: Settings):
    def factory(source_id, policy):
        if source_id == "mock":
            return MockAdapter(settings.sample_path)
        if source_id == "seller_p7":
            return UnimplementedAdapter()
        if source_id in ALLOWED_ENDPOINTS:
            if not settings.vault_addr or not settings.vault_token:
                raise PermissionLost("Vault not configured for Seller")
            ref = policy._credential_ref if hasattr(policy, "_credential_ref") else None
            if not ref:
                raise PermissionLost("Seller credential reference not supplied by source")
            return SellerLegacyAdapter(source_id, VaultKV2Resolver(settings.vault_addr, settings.vault_token, settings.vault_mount), ref, policy.timeout_seconds)
        if source_id.startswith("buyer_"):
            return BuyerSnapshotAdapter(source_id)
        raise SourceNotImplemented(source_id)
    return factory
