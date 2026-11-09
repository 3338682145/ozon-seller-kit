"""Offline contract tests. Real PG/CH/Metabase integration requires Docker."""
from __future__ import annotations

import importlib.util
import re
import sqlite3
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/metabase/bootstrap_dashboard.py"
spec = importlib.util.spec_from_file_location("metabase_bootstrap", SCRIPT)
mb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mb)


def test_compose_overlay_reuses_internal_stack_and_pins_image():
    c = yaml.safe_load((ROOT / "docker-compose.metabase.yml").read_text())
    services = c["services"]
    assert set(services) == {"metabase", "metabase-pg-init", "metabase-ch-init"}
    assert services["metabase"]["image"] == "metabase/metabase:v0.64.1"
    assert services["metabase"]["ports"] == ["127.0.0.1:${MB_PORT:-3001}:3000"]
    assert all(s["networks"] == ["internal"] for s in services.values())
    assert services["metabase"]["environment"]["MB_DB_TYPE"] == "postgres"
    assert services["metabase"]["environment"]["MB_LOAD_SAMPLE_CONTENT"] == "false"
    assert all("${" in c["services"]["metabase"]["environment"][x]
               for x in ("MB_DB_PASS", "MB_ENCRYPTION_SECRET_KEY"))


def test_pg_analytics_and_permissions_are_restricted():
    sql = (ROOT / "sql/metabase/010_pg_analytics.sql").read_text()
    role = (ROOT / "sql/metabase/020_pg_roles.psql").read_text()
    assert "CREATE OR REPLACE VIEW analytics.v_product_keyword_filter" in sql
    assert "latest_day" in sql and "ROW_NUMBER() OVER" in sql
    assert "keyword_opportunity_score" in sql and "missing_verified_inputs" in sql
    assert "s.verified = TRUE" in sql
    assert "GRANT SELECT ON analytics.v_product_keyword_filter" in role
    assert "default_transaction_read_only" in role
    assert "GRANT SELECT ON public." not in role
    assert "GRANT SELECT ON analytics.keyword_opportunity_inputs" not in role
    assert "CREATE TABLE IF NOT EXISTS analytics.keyword_opportunity_inputs" in sql


def test_clickhouse_has_safe_projection_and_definer_security():
    sql = (ROOT / "sql/metabase/030_clickhouse_views.sql").read_text()
    assert "DEFINER = CURRENT_USER SQL SECURITY DEFINER" in sql
    assert "FROM default.fact_keyword_sku_daily FINAL" in sql
    assert "FROM default.fact_price_history FINAL" in sql
    actual = sql[sql.index("CREATE OR REPLACE VIEW"):]
    assert not re.search(r"(?mi)^\s*(payload|raw_json)\s*(,|$)", actual)
    sh = (ROOT / "scripts/metabase/init_clickhouse.sh").read_text()
    assert "IDENTIFIED WITH sha256_hash" in sh
    assert "SETTINGS readonly = 1" in sh
    assert "GRANT SELECT ON analytics.v_serp_observations" in sh
    assert "GRANT SELECT ON default." not in sh


def test_templates_bound_to_all_controls_and_sort_nulls_last():
    for name in [x[1] for x in mb.QUESTIONS]:
        q = mb.native_query(name, 6)
        assert q["database"] == 6
        for code, _name, _kind, _default, dtype in mb.FILTERS:
            assert q["native"]["template-tags"][code]["type"] == dtype
            assert "{{" + code + "}}" in q["native"]["query"]
        assert "DROP " not in q["native"]["query"]
        assert "INSERT " not in q["native"]["query"]
    sql = (ROOT / "sql/metabase/cards/product_filter.sql").read_text()
    assert "keyword_opportunity_score DESC NULLS LAST" in sql
    assert "LIMIT 500" in sql
    assert [x["default"] for x in mb.params()] == ["антистресс", 500, 30]


def _sqlite_view():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.create_function("LEAST", -1, lambda *xs: min(xs))
    conn.executescript('''
       CREATE TABLE keywords(id TEXT PRIMARY KEY, text TEXT, normalized TEXT);
       CREATE TABLE products(ozon_id TEXT PRIMARY KEY, title TEXT, category_id TEXT,
                             seller_id TEXT, price_rub REAL, currency TEXT, observed_at TEXT);
       CREATE TABLE keyword_product_relations(id TEXT PRIMARY KEY, keyword_id TEXT,
                             ozon_id TEXT, observed_date TEXT, position INTEGER,
                             is_advert INTEGER, source TEXT, dataset_version TEXT);
       CREATE TABLE keyword_opportunity_inputs(id TEXT PRIMARY KEY, keyword_id TEXT,
                             as_of_date TEXT, max_slot30 INTEGER,
                             new_top10_share REAL, source TEXT, dataset_version TEXT,
                             algorithm_version TEXT, evidence_ref TEXT,
                             verified INTEGER, verified_at TEXT);
    ''')
    sql = (ROOT / "sql/metabase/010_pg_analytics.sql").read_text()
    select_sql = "WITH latest_day AS (" + sql.split("WITH latest_day AS (", 1)[1].split(";\n\nCOMMENT", 1)[0]
    select_sql = select_sql.replace("public.", "").replace("analytics.keyword_opportunity_inputs", "keyword_opportunity_inputs")
    select_sql = select_sql.replace("s.max_slot30::numeric", "CAST(s.max_slot30 AS REAL)")
    conn.execute("CREATE VIEW v_filter AS " + select_sql)
    return conn


def test_latest_snapshot_price_rank_and_verified_keyword_score():
    db = _sqlite_view()
    db.executemany("INSERT INTO keywords VALUES (?,?,?)", [
        ("kw1", "антистресс мяч", "антистресс мяч"),
        ("kw2", "антистресс набор", "антистресс набор"),
        ("kw3", "игрушка", "игрушка")])
    db.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?)", [
        ("A", "DEMO ball", "cat", "seller", 390, "RUB", "2026-11-09T00:00:00Z"),
        ("B", "DEMO expensive", "cat", "seller", 600, "RUB", "2026-11-09T00:00:00Z"),
        ("C", "DEMO low rank", "cat", "seller", 420, "RUB", "2026-11-09T00:00:00Z"),
        ("D", "DEMO set", "cat", "seller", 480, "RUB", "2026-11-09T00:00:00Z"),
        ("E", "DEMO old snapshot", "cat", "seller", 200, "RUB", "2026-11-08T00:00:00Z"),
    ])
    db.executemany("INSERT INTO keyword_product_relations VALUES (?,?,?,?,?,?,?,?)", [
        ("r1", "kw1", "A", "2026-11-09", 12, 0, "mock", "mock-v1"),
        ("r2", "kw1", "B", "2026-11-09", 5, 0, "mock", "mock-v1"),
        ("r3", "kw1", "C", "2026-11-09", 45, 0, "mock", "mock-v1"),
        ("r4", "kw2", "D", "2026-11-09", 22, 1, "mock", "mock-v1"),
        ("r5", "kw1", "E", "2026-11-08", 2, 0, "mock", "mock-v1"),
        ("r6", "kw3", "E", "2026-11-09", 1, 0, "mock", "mock-v1"),
    ])
    db.executemany("INSERT INTO keyword_opportunity_inputs VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
        ("s1", "kw1", "2026-11-09", 2, 0.2, "mock", "mock-v1", "gold-analytics-v1", "MOCK only", 1, "2026-11-09T06:00:00Z"),
        ("s2", "kw2", "2026-11-09", 6, 0.1, "mock", "mock-v1", "gold-analytics-v1", "MOCK only", 0, None),
    ])
    rows = db.execute('''SELECT sku, keyword_opportunity_score, opportunity_status FROM v_filter
        WHERE keyword_normalized LIKE '%' || ? || '%' AND price_rub <= ?
        AND search_position <= ?
        ORDER BY keyword_opportunity_score DESC NULLS LAST, search_position ASC''',
        ("антистресс", 500, 30)).fetchall()
    assert [r["sku"] for r in rows] == ["A", "D"]
    assert rows[0]["keyword_opportunity_score"] == pytest.approx(68.0)
    assert rows[1]["keyword_opportunity_score"] is None
    assert rows[1]["opportunity_status"] == "missing_verified_inputs"
    # Not today + missing verified data => no guessed rank/score.
    assert "E" not in [r["sku"] for r in rows]


class FakeResponse:
    status_code = 200
    def __init__(self, payload):
        self.payload = payload
    def json(self):
        return self.payload


class FakeMetabaseSession:
    def __init__(self):
        self.headers = {}
        self.databases = []
        self.collections = []
        self.items = {}
        self.dashboards = {}
        self.requests = []
        self.seq = 10

    def request(self, method, url, *, json=None, timeout=30, follow_redirects=False):
        path = url.split("/api", 1)[1].split("?", 1)[0]
        self.requests.append((method, path, json))
        if method == "GET":
            if path == "/health": return FakeResponse({"status":"ok"})
            if path == "/session/properties": return FakeResponse({"engines": {
                "clickhouse": {"details-fields": [
                    {"name":"host"}, {"name":"port"}, {"name":"user"},
                    {"name":"password"}, {"name":"databases"},
                    {"name":"scan-all-databases"}]}}})
            if path == "/database": return FakeResponse({"data": self.databases})
            if path == "/collection": return FakeResponse(self.collections)
            if path.startswith("/collection/") and path.endswith("/items"):
                return FakeResponse({"data": list(self.items.get(path.split("/")[2], []))})
            if path.startswith("/dashboard/"):
                return FakeResponse(self.dashboards.get(int(path.split("/")[-1]), {"dashcards": []}))
        if method == "POST":
            self.seq += 1
            obj = {"id": self.seq, **(json or {})}
            if path == "/database": self.databases.append(obj)
            elif path == "/collection": self.collections.append(obj)
            elif path in ("/card", "/dashboard"):
                cid = next(c["id"] for c in self.collections if c["name"] == mb.COLLECTION)
                self.items.setdefault(str(cid), []).append({"name":obj["name"],"id":obj["id"],"model":path[1:]})
                if path == "/dashboard": self.dashboards[obj["id"]] = {"dashcards": []}
            return FakeResponse(obj)
        if method == "PUT":
            if path.startswith("/dashboard/"):
                self.dashboards[int(path.split("/")[-1])] = {"dashcards": json["dashcards"], "parameters": json["parameters"]}
            return FakeResponse({"id":int(path.split("/")[-1])})
        raise AssertionError((method, path))


def test_metabase_bootstrap_idempotent_without_live_api():
    fake = FakeMetabaseSession()
    api = mb.MetabaseClient("http://localhost:3001",api_key="test",session=fake)
    first = mb.run(api, "safe-pg-reader-password", "safe-ch-reader-password", "ozon", "metabase_reader")
    second = mb.run(api, "safe-pg-reader-password", "safe-ch-reader-password", "ozon", "metabase_reader")
    assert first["dashboard_id"] == second["dashboard_id"]
    assert first["questions"] == 5
    assert len(fake.databases) == 2 and len(fake.collections) == 1
    assert sum(1 for method, path, _ in fake.requests if method=="POST" and path=="/card") == 5
    dash = fake.dashboards[first["dashboard_id"]]
    assert len(dash["dashcards"]) == 5
    assert all(len(c["parameter_mappings"]) == 3 for c in dash["dashcards"])
    assert {p["id"]:p["default"] for p in dash["parameters"]} == {
        "keyword":"антистресс", "max_price":500, "rank_max":30}


def test_repeat_bootstrap_preserves_custom_cards():
    old = [{"id":17,"card_id":999,"row":20,"col":0,"size_x":10,"size_y":5,
            "parameter_mappings":[]}]
    payload = mb.dashboard_payload(old, [(23,mb.QUESTIONS[0])])
    assert len(payload["dashcards"]) == 2
    assert payload["dashcards"][-1]["card_id"] == 999


def test_fail_closed_on_insecure_metabase_url():
    with pytest.raises(ValueError, match="trusted HTTPS"):
        mb.MetabaseClient("http://untrusted.example",api_key="test")


def test_driver_introspection_fails_closed_for_unknown_database_field():
    class MissingDriver:
        def call(self, method, path):
            return {"engines": {"clickhouse": {"details-fields": [{"name":"host"}]}}}
    with pytest.raises(RuntimeError, match="driver lacks"):
        mb.clickhouse_connection_details(MissingDriver(), "secret", "reader")
