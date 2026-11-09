"""Idempotent PostgreSQL/SQLite bulk upserts with stable relation keys."""
from __future__ import annotations
from datetime import datetime
from uuid import uuid5, NAMESPACE_URL
from sqlalchemy import select
from sqlalchemy.orm import Session
from collector.storage.models import Product, Keyword, KeywordProduct, DataQualityIssue


def stable_id(key: str) -> str:
    return str(uuid5(NAMESPACE_URL, "ozon-collector:" + key))


def _upsert(db: Session, table, rows: list[dict], keys: list[str], updates: list[str]):
    if not rows:
        return
    dialect = db.bind.dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise ValueError("unsupported dialect (require PostgreSQL or SQLite tests)")
    # Split by value lengths to avoid SQLite's bind parameter limit.
    for start in range(0, len(rows), 100):
        batch = rows[start:start+100]
        statement = insert(table).values(batch)
        assignment = {col: getattr(statement.excluded, col) for col in updates}
        db.execute(statement.on_conflict_do_update(index_elements=keys, set_=assignment))


def write_silver(db: Session, batch, job_id: str) -> dict[str, int]:
    products, keywords, relations = {}, {}, {}
    for r in batch.records:
        sku, kw = r["ozon_id"], r.get("keyword")
        products[sku] = {"ozon_id": sku, "title": r["title"], "price_rub": r["price_rub"],
                         "observed_at": r["observed_at"], "source": r["source"],
                         "data_type": r["data_type"], "dataset_version": r["dataset_version"],
                         "algorithm_version": r["algorithm_version"], "currency": "RUB"}
        if kw:
            kid = stable_id("kw:" + kw)
            keywords[kid] = {"id": kid, "text": r["keyword_original"], "normalized": kw,
                             "language": "ru", "observed_at": r["observed_at"], "dataset_version": r["dataset_version"]}
            day = r["observed_at"].date().isoformat()
            rel_key = f"{kid}:{sku}:{day}:{r['source']}"
            rid = stable_id("rel:" + rel_key)
            relations[rid] = {"id": rid, "keyword_id": kid, "ozon_id": sku, "observed_date": day,
                              "position": r["position"], "is_advert": r["is_advert"], "source": r["source"],
                              "dataset_version": r["dataset_version"], "algorithm_version": r["algorithm_version"]}
    _upsert(db, Product.__table__, list(products.values()), ["ozon_id"], ["title", "price_rub", "observed_at", "source", "dataset_version", "algorithm_version", "data_type"])
    _upsert(db, Keyword.__table__, list(keywords.values()), ["id"], ["text", "observed_at", "dataset_version"])
    _upsert(db, KeywordProduct.__table__, list(relations.values()), ["id"], ["position", "is_advert", "dataset_version", "algorithm_version"])
    for issue in batch.issues:
        # Stable issue id prevents repeated retries from multiplying quality issues.
        iid = stable_id(f"issue:{job_id}:{issue['index']}:{issue['issue_type']}")
        _upsert(db, DataQualityIssue.__table__, [{"id": iid, "job_id": job_id, "source": batch.records[0]["source"] if batch.records else "unknown", "issue_type": issue["issue_type"], "reference_id": issue.get("reference_id"), "details": issue}], ["id"], ["details"])
    return {"products": len(products), "keywords": len(keywords), "relations": len(relations), "issues": len(batch.issues)}
