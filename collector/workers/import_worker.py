"""Offline licensed JSONL/JSON file importer, separate from HTTP workers.

Requires metadata sidecar proving usage rights. Enqueues one job per batch;
never silently impersonates the Ozon network source.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from collector.pipeline.clean import clean_records, to_arrow
from collector.errors import PolicyViolation


def read_licensed_file(file: Path, license_manifest: Path) -> list[dict]:
    proof = json.loads(license_manifest.read_text(encoding="utf-8"))
    if proof.get("may_retain") is not True or not proof.get("authorization_scope") or not proof.get("source_id"):
        raise PolicyViolation("import requires explicit retention/license manifest")
    if file.suffix.lower() == ".jsonl":
        rows = [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines() if line.strip()]
    elif file.suffix.lower() == ".json":
        raw = json.loads(file.read_text(encoding="utf-8"))
        rows = raw["records"] if isinstance(raw, dict) else raw
    else:
        raise PolicyViolation("only JSON and JSONL are supported")
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", type=Path)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--out", type=Path, default=Path("/tmp/silver-import.parquet"))
    args = ap.parse_args()
    rows = read_licensed_file(args.data, args.manifest)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    batch = clean_records(rows, manifest["source_id"], manifest.get("dataset_version", "licensed-import-v1"))
    if batch.issues:
        print(json.dumps({"issue_count": len(batch.issues)}, ensure_ascii=False))
    import pyarrow.parquet as pq
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(to_arrow(batch.records), args.out)
    print(json.dumps({"rows": len(batch.records), "parquet": str(args.out)}))


if __name__ == "__main__":
    main()
