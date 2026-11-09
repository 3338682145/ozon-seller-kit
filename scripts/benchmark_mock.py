"""Deterministic local synthetic Silver/Gold microbenchmark, not Ozon throughput.

python scripts/benchmark_mock.py --rows 5000
No network, Redis or real database. Never use this result to raise source limits.
"""
from __future__ import annotations
import argparse
import json
import platform
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from collector.pipeline.clean import clean_records
from collector.pipeline.gold import keyword_sku_metrics
from collector.storage.facts import MemoryFactsSink


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--rows",type=int,default=5000)
    args=ap.parse_args()
    if not 1<=args.rows<=500000:
        ap.error("1<=rows<=500000 required")
    fixture=[{"sku":str(i+100000),"keyword":"антистресс", "position":i+1,
              "price":"199,90 ₽", "is_advert":False, "observed_at":"2026-11-09T00:00:00Z"}
             for i in range(args.rows)]
    start=time.perf_counter()
    silver=clean_records(fixture,"mock","benchmark-v1")
    t1=time.perf_counter()
    gold=keyword_sku_metrics(silver.records,version="benchmark-v1")
    sink=MemoryFactsSink()
    sink.write(silver.records,gold)
    t2=time.perf_counter()
    print(json.dumps({"scope":"SYNTHETIC_ONLY_NOT_SOURCE_BENCHMARK",
        "python":platform.python_version(),"rows":args.rows,
        "silver_seconds":round(t1-start,6),
        "silver_rows_per_second":round(args.rows/max(t1-start,1e-9)),
        "gold_and_memory_sink_seconds":round(t2-t1,6),
        "fact_product_daily_rows":len(sink.tables["fact_product_daily"]),
        "fact_serp_observation_rows":len(sink.tables["fact_serp_observation"]),
        "errors":len(silver.issues)}, ensure_ascii=False, indent=2))


if __name__=="__main__":
    main()
