"""Reuse the upstream SellerClient's P6/P8/CJM request builders.

Its network post() is REPLACED: no auth redirects, challenge solving,
Cookie writes, retry loops, identity/proxy rotation or silent re-login.
Live sources stay disabled until an operator verifies authorization/limits.
"""
from __future__ import annotations
import asyncio
import json
from typing import Any
import httpx
from collector.adapters.base import CollectionTask, SourceAdapter
from collector.errors import (AccessChallenge, DataQualityError, PermissionLost,
                              SourceNotImplemented, TransientSourceError, classify_http)
from collector.sessions.credentials import CredentialResolver

ALLOWED_ENDPOINTS = {
    "seller_p6": "/api/site/seller-analytics/what_to_sell/data/v3",
    "seller_p8": "/api/search-query-analytics/v2/external/explanation_by_id",
    "seller_cjm": "/api/search-query-analytics/v1/cjm/get-seller-analytics",
}


class _SafeSellerTransport:
    """Synchronously callable by unmodified upstream high-level methods."""
    def __init__(self, jar, *, expected_path: str, timeout: int):
        from ozon_seller.api import SellerClient
        self.original = SellerClient(jar=jar, timeout=timeout)
        self.expected_path = expected_path
        self.timeout = timeout
        self.original.post = self.post  # builder/response extraction logic is unchanged

    def post(self, path: str, body: dict, *, app_name: str, page_type: str, referer: str, retries: int = 0) -> dict:
        if path != self.expected_path:
            raise PermissionLost("out-of-scope seller endpoint")
        headers = self.original._headers(app_name, page_type, referer)
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=False, trust_env=False) as client:
                response = client.post("https://seller.ozon.ru" + path, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise TransientSourceError("source request timed out") from exc
        except httpx.TransportError as exc:
            raise TransientSourceError("source transport error") from exc
        classify_http(response.status_code, response.text[:512], response.headers.get("content-type", ""))
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise DataQualityError("seller returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise DataQualityError("seller returned non-object JSON")
        return payload


class SellerLegacyAdapter(SourceAdapter):
    def __init__(self, source_id: str, resolver: CredentialResolver, credential_ref: str, timeout: int = 30):
        if source_id not in ALLOWED_ENDPOINTS:
            raise SourceNotImplemented(source_id)
        self.source_id, self.resolver, self.credential_ref, self.timeout = source_id, resolver, credential_ref, timeout

    async def prepare(self, task: CollectionTask) -> None:
        if task.source_id != self.source_id or task.endpoint != ALLOWED_ENDPOINTS[self.source_id]:
            raise PermissionLost("source/endpoint scope mismatch")
        if not self.credential_ref:
            raise PermissionLost("credential reference is missing")
        # Resolve only at execution time, never in Job or Agent payloads.

    async def fetch(self, task: CollectionTask) -> dict[str, Any]:
        cred = self.resolver.resolve(self.credential_ref)
        # We do not write credentials to local disk, or let upstream code renew them.
        from ozon_seller.api import Jar
        jar = Jar(cookie=cred["cookie"], ua=cred["user_agent"], company_id=cred["company_id"], uuid=cred.get("uuid"))
        def run():
            client = _SafeSellerTransport(jar, expected_path=ALLOWED_ENDPOINTS[self.source_id], timeout=self.timeout).original
            if self.source_id == "seller_p6":
                p = task.payload
                return {"items": client.what_to_sell(skus=p.get("skus"), offset=int(p.get("offset", 0)), limit=min(int(p.get("limit", 50)), 50), period=p.get("period", "monthly"))}
            if self.source_id == "seller_p8":
                return client.explainer(str(task.payload["keyword"]))
            return client.my_products(period_from=str(task.payload["period_from"]), period_to=str(task.payload["period_to"]), per_page=min(int(task.payload.get("per_page", 100)), 500))
        return await asyncio.to_thread(run)

    async def parse(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        if self.source_id == "seller_p8":
            return [{**item, "keyword": response["kw"]} for item in response.get("items", [])]
        if self.source_id == "seller_cjm":
            return response.get("skus", [])
        return response.get("items", [])


class UnimplementedAdapter(SourceAdapter):
    async def prepare(self, task: CollectionTask) -> None:
        raise SourceNotImplemented("P7 online collection has no upstream implementation")

    async def fetch(self, task: CollectionTask) -> dict:  # pragma: no cover
        raise SourceNotImplemented("source not implemented")

    async def parse(self, response: dict) -> list[dict]:  # pragma: no cover
        raise SourceNotImplemented("source not implemented")
