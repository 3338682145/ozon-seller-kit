"""Fail-closed Supabase PostgreSQL URL and schema validation.

This module never prints connection strings, passwords, SQL row values, or raw
exceptions. Run ``--check-remote`` inside the private API container after the
schema and permissions have been provisioned by the operator.
"""
from __future__ import annotations

import argparse
import os
from sqlalchemy.engine import make_url

SCHEMA = "collector_core"


def validate_supabase_url(url: str, *, allow_admin: bool = False, schema_config: str = SCHEMA) -> None:
    if not url:
        raise ValueError("Supabase database URL is required")
    try:
        parsed = make_url(url)
    except Exception as exc:
        raise ValueError("invalid Supabase database URL") from None
    if parsed.drivername != "postgresql+psycopg":
        raise ValueError("required SQLAlchemy driver: postgresql+psycopg")
    if not parsed.host or not parsed.username or not parsed.password:
        raise ValueError("database hostname, username and password are required")
    if parsed.query.get("sslmode") not in {"require", "verify-ca", "verify-full"}:
        raise ValueError("external database connection must require TLS")
    if schema_config != SCHEMA:
        raise ValueError("COLLECTOR_PG_SCHEMA must equal collector_core")
    username = parsed.username.split(".", 1)[0]
    if not allow_admin and username in {"postgres", "supabase_admin", "service_role"}:
        raise ValueError("the runtime requires an unprivileged database role")


def verify_remote(url: str) -> None:
    # Imported here so a static URL check works without a database client.
    from sqlalchemy import text
    from collector.storage.database import make_session_factory

    engine = make_session_factory(url).kw["bind"]
    try:
        with engine.connect() as db:
            schema = db.scalar(text("SELECT current_schema()"))
            tls = db.scalar(text("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()"))
            table = db.scalar(text("SELECT to_regclass('collector_core.collection_jobs') IS NOT NULL"))
            can_ddl = db.scalar(text("SELECT has_schema_privilege(current_user, 'collector_core', 'CREATE')"))
            public_roles = db.execute(text("""
              SELECT has_schema_privilege('anon','collector_core','USAGE'),
                     has_schema_privilege('authenticated','collector_core','USAGE')
            """)).one()
            if schema != SCHEMA or not tls or not table or can_ddl or any(public_roles):
                raise RuntimeError("schema, TLS, migration or public-role isolation check failed")
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-remote", action="store_true")
    parser.add_argument("--allow-admin", action="store_true", help="only for one-off migrations")
    args = parser.parse_args()
    try:
        url = os.environ.get("DATABASE_URL", "")
        validate_supabase_url(url, allow_admin=args.allow_admin,
                              schema_config=os.getenv("COLLECTOR_PG_SCHEMA", ""))
        if args.check_remote:
            verify_remote(url)
    except Exception as exc:
        # NEVER include an exception message from a remote DB driver: it may
        # contain credentials, internal hostnames, or other sensitive context.
        print("Supabase connection validation failed (URL, TLS, role, schema or permissions)")
        return 2
    print("Supabase connection policy OK" + ("; private schema verified" if args.check_remote else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
