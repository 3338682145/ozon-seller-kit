"""Bronze -> Silver -> Gold. Raw store must succeed before SQL/fact writes."""
from __future__ import annotations
import json
from collector.storage.objects import serialize
from collector.pipeline.clean import clean_records
from collector.pipeline.gold import keyword_sku_metrics
from collector.storage.bulk import write_silver


class Pipeline:
    def __init__(self, object_store, facts_sink, dataset_version: str):
        self.objects, self.facts = object_store, facts_sink
        self.dataset_version = dataset_version

    def save_raw(self, job_id: str, response: dict) -> tuple[str, str]:
        key = f"{self.dataset_version}/{job_id}.json"
        sha = self.objects.put("raw-snapshots", key, serialize(response))
        return key, sha

    def ingest(self, db, job_id: str, source: str, records: list[dict], version: str | None = None):
        batch = clean_records(records, source, version or self.dataset_version)
        counts = write_silver(db, batch, job_id)
        gold = keyword_sku_metrics(batch.records, version=version or self.dataset_version)
        db.flush()  # constraint errors are surfaced before fact writes
        self.facts.write(batch.records, gold)
        return {**counts, "gold": len(gold)}

    async def recompute(self, db, job_id: str, source: str, object_key: str, adapter, version: str):
        """Replay retained Bronze through the current parser without network I/O.

        Caller owns the transaction and the permission check. Version is explicit
        so the result can be compared with, not silently overwrite, the old run.
        """
        raw = json.loads(self.objects.get("raw-snapshots", object_key))
        records = await adapter.validate(await adapter.parse(raw))
        return self.ingest(db, job_id, source, records, version=version)
