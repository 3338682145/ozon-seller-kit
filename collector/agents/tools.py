"""Read-only control-plane Agent tools; no arbitrary user SQL or shell."""
from __future__ import annotations
from sqlalchemy import text, select, func
from datetime import timedelta
from collector.agents.policy import propose
from collector.storage.models import (CollectionJob, CollectionPolicy, DataSource, Product, Keyword,
                                      KeywordProduct, DataQualityIssue, Incident, JobEvent, WorkerHeartbeat, utc_now)


class CollectorOperationsAgent:
    def __init__(self, session_factory):
        self.sf = session_factory

    def get_collection_status(self) -> dict:
        with self.sf() as db:
            rows = db.execute(select(CollectionJob.status, func.count()).group_by(CollectionJob.status)).all()
            return {"jobs_by_status": dict(rows), "total_jobs": sum(n for _, n in rows)}

    def get_source_health(self) -> dict:
        with self.sf() as db:
            return {"sources": [{"source_id": s.source_id, "enabled": s.enabled, "blocked": s.blocked,
                                 "license_verified": s.license_verified, "blocked_reason": s.blocked_reason}
                                for s in db.scalars(select(DataSource).order_by(DataSource.source_id))]}

    def get_collection_coverage(self) -> dict:
        with self.sf() as db:
            return {"products": db.scalar(select(func.count()).select_from(Product)),
                    "keywords": db.scalar(select(func.count()).select_from(Keyword)),
                    "keyword_sku_relations": db.scalar(select(func.count()).select_from(KeywordProduct)),
                    "coverage_scope": "ingested sample, not Ozon universe"}

    def inspect_collection_errors(self, limit: int = 50) -> dict:
        with self.sf() as db:
            jobs = db.scalars(select(CollectionJob).where(CollectionJob.last_error_code.is_not(None)).order_by(CollectionJob.updated_at.desc()).limit(min(100, max(1, limit)))).all()
            return {"errors": [{"job_id": j.id, "source_id": j.source_id, "code": j.last_error_code, "attempts": j.attempts} for j in jobs]}

    def get_worker_metrics(self) -> dict:
        with self.sf() as db:
            claimed = db.scalar(select(func.count()).select_from(JobEvent).where(JobEvent.event == "claimed"))
            done = db.scalar(select(func.count()).select_from(JobEvent).where(JobEvent.event == "completed"))
            threshold = utc_now() - timedelta(seconds=90)
            fresh = db.scalars(select(WorkerHeartbeat).where(WorkerHeartbeat.last_seen_at >= threshold)).all()
            return {"claimed_events": claimed, "completed_events": done,
                    "live_workers": len(fresh),
                    "workers": [{"worker_id": w.worker_id, "state": w.state,
                                 "last_seen_at": w.last_seen_at.isoformat()} for w in fresh]}

    def schedule_collection_job(self, payload: dict) -> dict:
        with self.sf.begin() as db:
            return propose(db, "collector_ops", "schedule_collection_job", payload, "review source authorization and policy before enqueue")

    def pause_collection_source(self, source_id: str) -> dict:
        with self.sf.begin() as db:
            return propose(db, "collector_ops", "pause_collection_source", {"source_id": source_id}, "operator-reviewed pause")


class DatabaseOperationsAgent:
    def __init__(self, session_factory):
        self.sf = session_factory

    def check_database_health(self) -> dict:
        with self.sf() as db:
            db.execute(text("SELECT 1"))
            return {"postgres_control_plane": "ok" if db.bind.dialect.name == "postgresql" else "sqlite_test_only",
                    "dialect": db.bind.dialect.name, "clickhouse": "not_checked", "minio": "not_checked"}

    def check_data_quality(self) -> dict:
        with self.sf() as db:
            n = db.scalar(select(func.count()).select_from(DataQualityIssue))
            return {"issue_count": n, "status": "warning" if n else "no_known_issues"}

    def find_duplicate_records(self) -> dict:
        # This is scoped to master products and keyword relationships only.
        with self.sf() as db:
            rows = db.execute(select(KeywordProduct.keyword_id, KeywordProduct.ozon_id, KeywordProduct.observed_date, func.count()).group_by(KeywordProduct.keyword_id, KeywordProduct.ozon_id, KeywordProduct.observed_date, KeywordProduct.source).having(func.count() > 1)).all()
            return {"duplicates": len(rows)}

    def analyze_slow_queries(self) -> dict:
        with self.sf() as db:
            if db.bind.dialect.name != "postgresql":
                return {"status": "not_available", "reason": "pg_stat_statements needs PostgreSQL"}
            try:
                # Only fixed whitelist SELECT, never user-provided SQL.
                rows = db.execute(text("SELECT calls, round(mean_exec_time::numeric, 2) AS mean_ms FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10")).mappings().all()
            except Exception:
                return {"status": "not_available", "reason": "pg_stat_statements not installed or insufficient privileges"}
            return {"queries": [{"calls": x["calls"], "mean_ms": str(x["mean_ms"])} for x in rows]}

    def inspect_storage_usage(self) -> dict:
        with self.sf() as db:
            if db.bind.dialect.name != "postgresql":
                return {"status": "not_available", "reason": "SQLite test environment"}
            size = db.scalar(text("SELECT pg_database_size(current_database())"))
            return {"postgres_bytes": size, "clickhouse_bytes": None, "minio_bytes": None}

    def check_backup_status(self) -> dict:
        # Never infer a successful backup from existence of configuration.
        return {"status": "unverified", "last_success_at": None, "restore_test_at": None}

    def inspect_data_lineage(self, job_id: str) -> dict:
        with self.sf() as db:
            job = db.get(CollectionJob, job_id)
            if not job:
                return {"status": "not_found"}
            events = db.scalars(select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.occurred_at)).all()
            return {"job_id": job.id, "source_id": job.source_id, "dataset_version": job.checkpoint.get("dataset_version") if job.checkpoint else None,
                    "raw_key": job.raw_object_key, "raw_sha256": job.raw_sha256,
                    "events": [e.event for e in events]}
