#!/usr/bin/env python3
"""Idempotent-ish Metabase 0.64 dashboard bootstrap for the Ozon analytics views.

Use an API key or existing admin session; this script does NOT create an admin,
write Ozon business data, inject SQL literals, or execute any scraper.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
COLLECTION = "Ozon 商品分析（只读）"
DASHBOARD = "Ozon · 商品筛选与关键词机会（演示配置）"
DB_PG = "Ozon PostgreSQL Analytics (read-only)"
DB_CH = "Ozon ClickHouse Analytics (read-only)"

# A dashboard string variable is a single-valued input, while SQL does the
# partial-text match. Number inputs are bounds in SQL, NOT 'equal to' filters.
FILTERS = (
    ("keyword", "关键词包含", "string/=", "антистресс", "text"),
    ("max_price", "最高价格 RUB", "number/=", 500, "number"),
    ("rank_max", "搜索排名前 N", "number/=", 30, "number"),
)
QUESTIONS = (
    ("商品机会筛选表", "product_filter.sql", "postgres", "table", 0, 0, 24, 9),
    ("当前结果概览", "product_summary.sql", "postgres", "table", 9, 0, 12, 4),
    ("关键词机会评分（有验证才显示）", "keyword_opportunities.sql", "postgres", "table", 9, 12, 12, 6),
    ("每日关键词搜索位覆盖", "serp_rank_trend.sql", "clickhouse", "line", 15, 0, 12, 6),
    ("每日搜索位挂牌价格", "serp_price_trend.sql", "clickhouse", "line", 15, 12, 12, 6),
)


def params() -> list[dict[str, Any]]:
    return [{"id": code, "name": label, "slug": code, "type": kind,
             "default": default, "required": True}
            for code, label, kind, default, _ in FILTERS]


def native_query(filename: str, database_id: int) -> dict:
    sql = (ROOT / "sql" / "metabase" / "cards" / filename).read_text(encoding="utf-8")
    tags = {}
    for code, label, _, default, tag_type in FILTERS:
        assert "{{" + code + "}}" in sql, (filename, code)
        tags[code] = {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, "ozon-metabase-" + code)),
            "name": code, "display-name": label, "type": tag_type,
            "required": True, "default": default,
        }
    return {"database": database_id, "type": "native",
            "native": {"query": sql, "template-tags": tags}}


def dashboard_payload(existing_dashcards: list[dict], cards: list[tuple[int, tuple]]) -> dict:
    """Preserve user-added cards when rerunning: PUT requires the *full* list."""
    by_card = {item.get("card_id"): item for item in existing_dashcards
               if item.get("card_id") is not None}
    handled: set[int] = set()
    dashcards = []
    for cid, spec in cards:
        _, _, _, _, row, col, sx, sy = spec
        existing = by_card.get(cid)
        record = {
            "id": existing["id"] if existing else -len(dashcards) - 1,
            "card_id": cid, "row": row, "col": col, "size_x": sx, "size_y": sy,
            "parameter_mappings": [
                {"parameter_id": code, "card_id": cid,
                 "target": ["variable", ["template-tag", code]]}
                for code, *_ in FILTERS
            ],
        }
        if existing and existing.get("dashboard_tab_id") is not None:
            record["dashboard_tab_id"] = existing["dashboard_tab_id"]
        handled.add(cid)
        dashcards.append(record)
    # Don't erase other users' charts. Metabase PUT replaces all dashcards.
    for old in existing_dashcards:
        if old.get("card_id") in handled:
            continue
        record = {k: old[k] for k in (
            "id", "card_id", "row", "col", "size_x", "size_y",
            "parameter_mappings", "dashboard_tab_id", "visualization_settings"
        ) if k in old}
        if "id" in record:
            dashcards.append(record)
    return {"parameters": params(), "dashcards": dashcards}


def unpack_items(response: Any) -> list:
    if isinstance(response, list):
        return response
    if isinstance(response, dict):
        if isinstance(response.get("data"), list):
            return response["data"]
        if isinstance(response.get("items"), list):
            return response["items"]
    raise RuntimeError("Metabase list endpoint returned an unexpected response shape")


class MetabaseClient:
    def __init__(self, url: str, *, api_key: str = "", email: str = "", password: str = "",
                 session: httpx.Client | None = None):
        if not url.startswith(("http://127.0.0.1:", "http://localhost:", "https://")):
            raise ValueError("Set METABASE_URL to localhost or trusted HTTPS (no public HTTP)")
        self.url = url.rstrip("/")
        self.session = session or httpx.Client()
        self.session.headers["Content-Type"] = "application/json"
        if api_key:
            self.session.headers["X-API-Key"] = api_key
        elif email and password:
            auth = self.call("POST", "/api/session", {"username": email, "password": password})
            self.session.headers["X-Metabase-Session"] = auth["id"]
        else:
            raise ValueError("Set METABASE_API_KEY or METABASE_ADMIN_EMAIL/PASSWORD")

    def call(self, method: str, path: str, data: dict | None = None) -> Any:
        # Error bodies can contain secrets; only show HTTP status and endpoint.
        response = self.session.request(method, self.url + path, json=data, timeout=30,
                                        follow_redirects=False)
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"Metabase {method} {path.split('?')[0]}: HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as e:
            raise RuntimeError("Metabase returned malformed JSON") from e


def upsert_database(api: MetabaseClient, name: str, engine: str, details: dict) -> int:
    matches = [x for x in unpack_items(api.call("GET", "/api/database"))
               if x.get("name") == name]
    if matches:
        if len(matches) != 1 or matches[0].get("engine") != engine:
            raise RuntimeError(f"Database name conflict: {name}")
        # Don't overwrite manually configured databases silently.
        return int(matches[0]["id"])
    return int(api.call("POST", "/api/database", {"name": name,
                    "engine": engine, "details": details})["id"])



def clickhouse_connection_details(api: MetabaseClient, password: str, username: str) -> dict:
    """Adapt to the installed CH driver's declared connection field names."""
    props = api.call("GET", "/api/session/properties")
    engine = (props.get("engines") or {}).get("clickhouse", {})
    fields = {f.get("name") for f in engine.get("details-fields", [])
              if isinstance(f, dict)}
    details = {"host": "clickhouse", "port": 8123,
               "user": username, "password": password}
    for name in ("databases", "dbname", "db", "database"):
        if name in fields:
            details[name] = "analytics"
            break
    else:
        raise RuntimeError("ClickHouse driver lacks a recognized database field; inspect Metabase /api/session/properties")
    if "scan-all-databases" in fields:
        details["scan-all-databases"] = False
    return details


def upsert_collection(api: MetabaseClient) -> int:
    matches = [x for x in unpack_items(api.call("GET", "/api/collection"))
               if x.get("name") == COLLECTION]
    if matches:
        return int(matches[0]["id"])
    return int(api.call("POST", "/api/collection", {
        "name": COLLECTION, "color": "#509EE2", "description": "Ozon 只读分析：数据源/计算口径透明。"})["id"])


def collection_items(api: MetabaseClient, coll_id: int) -> list:
    # A dedicated collection holds fewer than 50 managed items.
    return unpack_items(api.call("GET", f"/api/collection/{coll_id}/items"))


def run(api: MetabaseClient, pg_password: str, ch_password: str, pg_dbname: str,
        pg_username: str, *, ch_username: str = "metabase_reader") -> dict:
    api.call("GET", "/api/health")
    pg_id = upsert_database(api, DB_PG, "postgres", {
        "host": "postgres", "port": 5432, "dbname": pg_dbname,
        "user": pg_username, "password": pg_password,
    })
    ch_id = upsert_database(api, DB_CH, "clickhouse",
                            clickhouse_connection_details(api, ch_password, ch_username))
    cid = upsert_collection(api)
    known = {x.get("name"): x for x in collection_items(api, cid)}
    saved = []
    for spec in QUESTIONS:
        name, file, engine, display, *_ = spec
        body = {"name": name, "type": "question", "display": display,
                "description": "Read-only. Scores are verified keyword-level only; null means not calculated.",
                "collection_id": cid,
                "visualization_settings": {},
                "dataset_query": native_query(file, pg_id if engine == "postgres" else ch_id)}
        existing = known.get(name)
        if existing:
            card_id = int(existing["id"])
            api.call("PUT", f"/api/card/{card_id}", body)
        else:
            card_id = int(api.call("POST", "/api/card", body)["id"])
        saved.append((card_id, spec))
    known = {x.get("name"): x for x in collection_items(api, cid)}
    if DASHBOARD in known:
        did = int(known[DASHBOARD]["id"])
    else:
        did = int(api.call("POST", "/api/dashboard", {
            "name": DASHBOARD, "collection_id": cid,
            "description": "默认：антистресс，最高 500 RUB，排名前 30；机会评分来源需验证。"})["id"])
    current = api.call("GET", f"/api/dashboard/{did}")
    patch = dashboard_payload(current.get("dashcards") or [], saved)
    api.call("PUT", f"/api/dashboard/{did}", patch)
    return {"dashboard_id": did, "dashboard_url": api.url + f"/dashboard/{did}",
            "collection_id": cid, "questions": len(saved), "defaults": {f[0]: f[3] for f in FILTERS}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Validate templates; no API calls or credentials required")
    args = parser.parse_args(argv)
    if args.dry_run:
        print(json.dumps({"name": DASHBOARD, "parameters": params(), "questions": [
            {"name": q[0], "engine": q[2], "sql_filename": q[1],
             "template_variables": list(native_query(q[1], 1)["native"]["template-tags"])}
            for q in QUESTIONS]}, ensure_ascii=False, indent=2))
        return 0
    pg_password = os.environ.get("MB_READER_PASSWORD", "")
    ch_password = os.environ.get("MB_CH_READER_PASSWORD", "")
    if not pg_password or not ch_password or pg_password.startswith("CHANGE_ME") or ch_password.startswith("CHANGE_ME"):
        parser.error("Set MB_READER_PASSWORD and MB_CH_READER_PASSWORD from .env.metabase securely")
    api = MetabaseClient(os.environ.get("METABASE_URL", "http://localhost:3001"),
                         api_key=os.environ.get("METABASE_API_KEY", ""),
                         email=os.environ.get("METABASE_ADMIN_EMAIL", ""),
                         password=os.environ.get("METABASE_ADMIN_PASSWORD", ""))
    result = run(api, pg_password, ch_password,
                 os.environ.get("POSTGRES_DB", "ozon"),
                 os.environ.get("MB_READER_USER", "metabase_reader"))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
