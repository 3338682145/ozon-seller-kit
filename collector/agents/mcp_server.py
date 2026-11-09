"""MCP tools for DSH integration (read-only by default).

Exposes StreamableHTTP when mcp SDK is installed. Mutating tools only create
approval proposals, never execute directly. DSH transport contract unverified.
"""
from __future__ import annotations
import os
from mcp.server.fastmcp import FastMCP
from collector.storage.database import make_session_factory
from collector.agents.tools import CollectorOperationsAgent, DatabaseOperationsAgent

sf = make_session_factory(os.environ["DATABASE_URL"])
collector = CollectorOperationsAgent(sf)
database = DatabaseOperationsAgent(sf)
mcp = FastMCP("ozon-operations", host="0.0.0.0", port=8090)

@mcp.tool()
def get_collection_status() -> dict: return collector.get_collection_status()

@mcp.tool()
def get_source_health() -> dict: return collector.get_source_health()

@mcp.tool()
def get_collection_coverage() -> dict: return collector.get_collection_coverage()

@mcp.tool()
def inspect_collection_errors(limit: int = 50) -> dict: return collector.inspect_collection_errors(limit)

@mcp.tool()
def get_worker_metrics() -> dict: return collector.get_worker_metrics()

@mcp.tool()
def schedule_collection_job(source_id: str, endpoint: str, kind: str, payload: dict) -> dict:
    return collector.schedule_collection_job({"source_id": source_id, "endpoint": endpoint, "kind": kind, "payload": payload})

@mcp.tool()
def pause_collection_source(source_id: str) -> dict: return collector.pause_collection_source(source_id)

@mcp.tool()
def check_database_health() -> dict: return database.check_database_health()

@mcp.tool()
def check_data_quality() -> dict: return database.check_data_quality()

@mcp.tool()
def find_duplicate_records() -> dict: return database.find_duplicate_records()

@mcp.tool()
def analyze_slow_queries() -> dict: return database.analyze_slow_queries()

@mcp.tool()
def inspect_storage_usage() -> dict: return database.inspect_storage_usage()

@mcp.tool()
def check_backup_status() -> dict: return database.check_backup_status()

@mcp.tool()
def inspect_data_lineage(job_id: str) -> dict: return database.inspect_data_lineage(job_id)

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
