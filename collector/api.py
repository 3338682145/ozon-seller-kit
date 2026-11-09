"""FastAPI control/data API. All mutation routes are RBAC protected."""
from __future__ import annotations
from decimal import Decimal
from datetime import timedelta
from typing import Any
import hmac
import os
from fastapi import FastAPI, Depends, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST
from collector.agents.tools import CollectorOperationsAgent, DatabaseOperationsAgent
from collector.agents.policy import authorize_approval
from collector.config import Settings, must_have_auth
from collector.errors import PolicyViolation
from collector.scheduler.jobs import JobService
from collector.sessions.credentials import mark_dead
from collector.monitoring.incidents import verify_incident_recovery
from collector.storage.database import make_session_factory
from collector.storage.models import (CollectionJob, CollectionPolicy, DataSource, Product, Keyword,
                                      KeywordProduct, Incident, JobEvent, DataQualityIssue, AgentDecision, WorkerHeartbeat, utc_now)

REQUESTS = Counter("ozon_api_requests_total", "API responses", ["method", "route", "status"])
JOB_STATES = ("pending", "retry_wait", "running", "completed", "canceled", "dead_letter", "blocked")
JOB_GAUGE = Gauge("ozon_collection_jobs", "Control-plane jobs by state", ["status"])
INCIDENT_GAUGE = Gauge("ozon_open_incidents", "Unresolved incidents by severity", ["severity"])
WORKER_GAUGE = Gauge("ozon_live_workers", "Workers with heartbeat within 90 seconds")


class JobCreate(BaseModel):
    source_id: str = Field(min_length=1, max_length=64)
    endpoint: str = Field(min_length=1, max_length=256)
    kind: str = Field(min_length=1, max_length=24)
    payload: dict[str, Any] = Field(default_factory=dict)
    batch_id: str | None = Field(default=None, max_length=128)
    priority: int | None = Field(default=None, ge=-10, le=10)


class RecoveryVerification(BaseModel):
    checks: dict[str, bool]
    evidence_ref: str = Field(min_length=1, max_length=128)


class DeadCredential(BaseModel):
    credential_ref: str = Field(min_length=1, max_length=256)
    reason: str = Field(default="revoked", max_length=64)


def _page(query, db: Session, limit: int, offset: int, convert):
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.offset(offset).limit(limit)).all()
    return {"items": [convert(x) for x in rows], "limit": limit, "offset": offset, "total": total}


def create_app(*, settings: Settings | None = None, session_factory=None) -> FastAPI:
    settings = settings or Settings()
    must_have_auth(settings)
    sf = session_factory or make_session_factory(settings.database_url)
    jobs = JobService(sf)
    collector = CollectorOperationsAgent(sf)
    database = DatabaseOperationsAgent(sf)
    app = FastAPI(title="Ozon Collection Operations API", version="0.1.0", docs_url="/docs", openapi_url="/openapi.json")
    app.state.session_factory = sf
    app.state.job_service = jobs

    @app.middleware("http")
    async def stats(request: Request, call_next):
        response = await call_next(request)
        path = request.scope.get("route")
        REQUESTS.labels(request.method, path.path if path else "unknown", str(response.status_code)).inc()
        return response

    @app.exception_handler(PolicyViolation)
    async def policy_error(req: Request, exc: PolicyViolation):
        return JSONResponse(status_code=403, content={"error": {"code": exc.code, "message": str(exc), "request_id": req.headers.get("x-request-id", "")}})

    @app.exception_handler(HTTPException)
    async def http_error(req: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": "http_error", "message": str(exc.detail), "request_id": req.headers.get("x-request-id", "")}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(req: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"error": {"code": "validation_error", "message": "invalid request", "request_id": req.headers.get("x-request-id", "")}})

    def role(request: Request) -> str:
        if settings.allow_insecure_dev:
            return "admin"
        candidate = request.headers.get("x-api-key", "")
        if not candidate:
            auth = request.headers.get("authorization", "")
            candidate = auth.removeprefix("Bearer ") if auth.startswith("Bearer ") else ""
        if settings.admin_key and hmac.compare_digest(candidate, settings.admin_key):
            return "admin"
        if settings.api_key and hmac.compare_digest(candidate, settings.api_key):
            return "operator"
        if settings.viewer_key and hmac.compare_digest(candidate, settings.viewer_key):
            return "viewer"
        raise HTTPException(status_code=401, detail="invalid API key")

    def reader(request: Request):
        return role(request)

    def operator(request: Request):
        who = role(request)
        if who not in {"operator", "admin"}:
            raise HTTPException(status_code=403, detail="operator role required")
        return who

    def admin(request: Request):
        if role(request) != "admin":
            raise HTTPException(status_code=403, detail="admin approval required")
        return "admin"

    @app.get("/metrics", include_in_schema=False)
    def prometheus():
        # Refresh server-side gauges from PG; labels are bounded, never contain
        # user input, credential metadata or source URLs.
        with sf() as db:
            statuses = dict(db.execute(select(CollectionJob.status, func.count()).group_by(CollectionJob.status)).all())
            severities = dict(db.execute(select(Incident.severity, func.count()).where(Incident.status == "open").group_by(Incident.severity)).all())
            active = db.scalar(select(func.count()).select_from(WorkerHeartbeat).where(WorkerHeartbeat.last_seen_at >= utc_now()-timedelta(seconds=90)))
            for status in JOB_STATES:
                JOB_GAUGE.labels(status).set(statuses.get(status, 0))
            for severity in ("P0", "P1", "P2", "P3"):
                INCIDENT_GAUGE.labels(severity).set(severities.get(severity, 0))
            WORKER_GAUGE.set(active or 0)
        return PlainTextResponse(generate_latest().decode(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        with sf() as db:
            db.execute(text("SELECT 1"))
        return {"ok": True}

    @app.get("/api/v1/sources", dependencies=[Depends(reader)])
    def sources(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        with sf() as db:
            return _page(select(DataSource).order_by(DataSource.source_id), db, limit, offset,
                         lambda x: {"source_id": x.source_id, "enabled": x.enabled, "blocked": x.blocked,
                                    "license_verified": x.license_verified, "authorization_scope": x.authorization_scope})

    @app.get("/api/v1/sources/health", dependencies=[Depends(reader)])
    def sources_health():
        return collector.get_source_health()

    @app.post("/api/v1/jobs", status_code=201, dependencies=[Depends(operator)])
    def create_job(data: JobCreate, idempotency_key: str | None = Header(None)):
        if idempotency_key and len(idempotency_key) > 128:
            raise HTTPException(422, "idempotency key too long")
        job = jobs.create(**data.model_dump(), idempotency_key=idempotency_key)
        return {"id": job.id, "status": job.status, "source_id": job.source_id, "created_at": job.created_at}

    @app.get("/api/v1/batches/{batch_id}", dependencies=[Depends(reader)])
    def get_batch_status(batch_id: str):
        """Crawlab batch visibility. PostgreSQL is the only job-status authority.

        Never return task payloads, cookies or raw product data to Crawlab.
        Empty/unknown batches return 404; a failed child is not reported as
        a successful batch merely because the submit script has finished.
        """
        with sf() as db:
            counts = dict(db.execute(
                select(CollectionJob.status, func.count(CollectionJob.id))
                .where(CollectionJob.batch_id == batch_id)
                .group_by(CollectionJob.status)
            ).all())
        total = sum(counts.values())
        if not total:
            raise HTTPException(status_code=404, detail="batch not found")
        done = counts.get("completed", 0)
        failed = sum(counts.get(k, 0) for k in ("blocked", "dead_letter", "canceled"))
        if done == total:
            status = "completed"
        elif done + failed == total:
            status = "failed" if done == 0 else "partial"
        else:
            status = "running"
        return {"batch_id": batch_id, "status": status, "total": total,
                "completed": done, "failed": failed,
                "pending": total - done - failed,
                "by_status": {k: counts.get(k, 0) for k in JOB_STATES}}

    @app.get("/api/v1/jobs/{job_id}", dependencies=[Depends(reader)])
    def get_job(job_id: str):
        with sf() as db:
            job = db.get(CollectionJob, job_id)
            if not job:
                raise HTTPException(404, "job not found")
            return {"id": job.id, "status": job.status, "attempts": job.attempts, "source_id": job.source_id,
                    "last_error_code": job.last_error_code, "checkpoint": job.checkpoint,
                    "raw_object_key": job.raw_object_key, "created_at": job.created_at, "completed_at": job.completed_at}

    @app.post("/api/v1/jobs/{job_id}/cancel", dependencies=[Depends(operator)])
    def cancel_job(job_id: str):
        job = jobs.cancel(job_id)
        if not job:
            raise HTTPException(404, "job not found")
        return {"id": job.id, "status": job.status}

    @app.post("/api/v1/sources/{source_id}/resume", dependencies=[Depends(admin)])
    def resume_source(source_id: str):
        if not jobs.resume_source(source_id):
            raise HTTPException(409, "source recovery requires an operator pause and verified policy")
        return {"source_id": source_id, "status": "enabled"}

    @app.get("/api/v1/products", dependencies=[Depends(reader)])
    def products(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        with sf() as db:
            return _page(select(Product).order_by(Product.ozon_id), db, limit, offset,
                         lambda x: {"ozon_id": x.ozon_id, "title": x.title, "price_rub": str(x.price_rub) if x.price_rub is not None else None,
                                    "source": x.source, "data_type": x.data_type, "dataset_version": x.dataset_version})

    @app.get("/api/v1/products/{ozon_id}", dependencies=[Depends(reader)])
    def product(ozon_id: str):
        with sf() as db:
            item = db.get(Product, ozon_id)
            if not item:
                raise HTTPException(404, "product not found")
            return {"ozon_id": item.ozon_id, "title": item.title, "price_rub": item.price_rub,
                    "observed_at": item.observed_at, "source": item.source, "data_type": item.data_type,
                    "dataset_version": item.dataset_version, "algorithm_version": item.algorithm_version}

    @app.get("/api/v1/products/{ozon_id}/keywords", dependencies=[Depends(reader)])
    def product_keywords(ozon_id: str, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        with sf() as db:
            rows = db.execute(select(Keyword.id, Keyword.normalized, KeywordProduct.position, KeywordProduct.observed_date).join(KeywordProduct, Keyword.id == KeywordProduct.keyword_id).where(KeywordProduct.ozon_id == ozon_id).order_by(KeywordProduct.observed_date.desc()).offset(offset).limit(limit)).all()
            return {"items": [{"keyword_id": r[0], "keyword": r[1], "position": r[2], "observed_date": r[3]} for r in rows], "limit": limit, "offset": offset}

    @app.get("/api/v1/keywords", dependencies=[Depends(reader)])
    def keywords(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        with sf() as db:
            return _page(select(Keyword).order_by(Keyword.normalized), db, limit, offset, lambda x: {"id": x.id, "text": x.text, "normalized": x.normalized})

    @app.get("/api/v1/keywords/{keyword_id}/products", dependencies=[Depends(reader)])
    def keyword_products(keyword_id: str, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        with sf() as db:
            rows = db.execute(select(Product.ozon_id, Product.title, KeywordProduct.position, KeywordProduct.is_advert).join(KeywordProduct, Product.ozon_id == KeywordProduct.ozon_id).where(KeywordProduct.keyword_id == keyword_id).order_by(KeywordProduct.position).offset(offset).limit(limit)).all()
            return {"items": [{"ozon_id": r[0], "title": r[1], "position": r[2], "is_advert": r[3]} for r in rows], "limit": limit, "offset": offset}

    @app.get("/api/v1/keywords/{keyword_id}/ranking-history", dependencies=[Depends(reader)])
    def ranking_history(keyword_id: str, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        with sf() as db:
            rel = db.scalars(select(KeywordProduct).where(KeywordProduct.keyword_id == keyword_id).order_by(KeywordProduct.observed_date.desc(), KeywordProduct.position).offset(offset).limit(limit)).all()
            return {"items": [{"ozon_id": r.ozon_id, "observed_date": r.observed_date, "position": r.position, "is_advert": r.is_advert, "dataset_version": r.dataset_version} for r in rel], "limit": limit, "offset": offset}

    @app.get("/api/v1/metrics/collection", dependencies=[Depends(reader)])
    def collection_metrics():
        return collector.get_collection_status()

    @app.get("/api/v1/metrics/data-quality", dependencies=[Depends(reader)])
    def data_quality_metrics():
        return database.check_data_quality()

    @app.get("/api/v1/incidents", dependencies=[Depends(reader)])
    def incidents(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        with sf() as db:
            return _page(select(Incident).order_by(Incident.created_at.desc()), db, limit, offset,
                         lambda i: {"id": i.id, "severity": i.severity, "status": i.status, "summary": i.summary, "count": i.occurrence_count})

    @app.post("/api/v1/incidents/{incident_id}/verify-recovery", dependencies=[Depends(admin)])
    def verify_recovery(incident_id: str, evidence: RecoveryVerification):
        with sf.begin() as db:
            if not verify_incident_recovery(db, incident_id, checks=evidence.checks,
                                            evidence_ref=evidence.evidence_ref, approver="admin-api"):
                raise HTTPException(409, "recovery must pass whitelisted checks with evidence")
        return {"incident_id": incident_id, "status": "resolved"}

    @app.get("/api/v1/database/health", dependencies=[Depends(reader)])
    def database_health():
        return database.check_database_health()

    @app.get("/api/v1/agents/collector/status", dependencies=[Depends(reader)])
    def agent_collector_status():
        return collector.get_collection_status()

    @app.get("/api/v1/agents/database/health", dependencies=[Depends(reader)])
    def agent_database_health():
        return database.check_database_health()

    @app.post("/api/v1/agents/collector/pause-proposal", dependencies=[Depends(operator)])
    def propose_pause(source_id: str):
        return collector.pause_collection_source(source_id)

    @app.post("/api/v1/agents/approvals/{approval_id}/approve", dependencies=[Depends(admin)])
    def approve(approval_id: str):
        # Only limited, fixed runbooks may execute after approval.
        with sf.begin() as db:
            decision = authorize_approval(db, approval_id, "admin-api")
            action, args = decision.decision, decision.inputs
            if action == "pause_collection_source":
                source = db.get(DataSource, args["source_id"])
                if not source:
                    raise HTTPException(404, "source not found")
                source.enabled, source.blocked, source.blocked_reason = False, True, "approved_agent_pause"
                db.query(CollectionJob).filter(CollectionJob.source_id == source.source_id,
                    CollectionJob.status.in_(["pending", "retry_wait", "running"])).update(
                    {"status": "blocked", "last_error_code": "source_blocked", "lease_owner": None,
                     "lease_expires_at": None}, synchronize_session=False)
            elif action == "schedule_collection_job":
                # Requires a second transaction because JobService validates its own policy.
                # Do not execute inside this transaction: use the human-reviewed API job POST.
                decision.report = {"status": "approved_for_manual_submission", "operation": action}
                return {"decision_id": decision.id, "status": "approved_for_manual_submission"}
            decision.report = {"status": "executed", "operation": action}
            return {"decision_id": decision.id, "status": "executed"}

    @app.post("/mark_dead", dependencies=[Depends(admin)], include_in_schema=True)
    def mark_dead_compat(data: DeadCredential):
        with sf.begin() as db:
            mark_dead(db, data.credential_ref, data.reason)
        return {"status": "revoked", "credential_ref": data.credential_ref}

    if settings.otel_endpoint:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
    return app


# Launch with: uvicorn collector.api:create_app --factory
