"""Alembic migrations: only DATABASE_URL controls the target."""
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool, event
import os
from collector.storage.models import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url")))
target_metadata = Base.metadata


def offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def online():
    engine = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    if os.getenv("COLLECTOR_PG_SCHEMA") == "collector_core" and engine.dialect.name == "postgresql":
        @event.listens_for(engine, "connect")
        def _migration_search_path(dbapi_connection, _connection_record):
            with dbapi_connection.cursor() as cursor:
                cursor.execute("SET SESSION search_path TO collector_core, public")
            dbapi_connection.commit()
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    offline()
else:
    online()
