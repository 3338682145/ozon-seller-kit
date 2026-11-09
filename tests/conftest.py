from __future__ import annotations
import pytest
from pathlib import Path
from collector.storage.database import make_session_factory, seed_mock
from collector.storage.objects import MemoryObjectStore
from collector.storage.facts import MemoryFactsSink
from collector.pipeline.runner import Pipeline
from collector.scheduler.broker import MemoryBroker
from collector.scheduler.publisher import Publisher
from collector.scheduler.jobs import JobService
from collector.adapters.mock import MockAdapter
from collector.workers.runtime import Worker

@pytest.fixture
def rig(tmp_path):
    sf = make_session_factory(f"sqlite+pysqlite:///{tmp_path / 'test.db'}", test_schema=True)
    seed_mock(sf)
    object_store = MemoryObjectStore()
    facts = MemoryFactsSink()
    pipeline = Pipeline(object_store, facts, "mock-v1")
    broker = MemoryBroker()
    sample = str(Path(__file__).resolve().parents[1]/"samples"/"mock_collection.json")
    worker = Worker(sf, broker, lambda src, policy: MockAdapter(sample), pipeline)
    publisher = Publisher(sf, broker, max_backlog=100)
    return {"sf": sf, "objects": object_store, "facts": facts, "pipeline": pipeline,
            "broker": broker, "worker": worker, "publisher": publisher, "jobs": JobService(sf), "sample": sample}
