"""Mock microbenchmark only, explicitly NOT a source performance claim."""
import time
import pytest
from collector.pipeline.clean import clean_records

@pytest.mark.benchmark
def test_local_batch_baseline():
    rows = [{"sku": str(i+1), "keyword": "игрушка", "position": i+1, "price": "99,99 ₽"} for i in range(500)]
    t0 = time.perf_counter()
    b = clean_records(rows, "mock", "benchmark-local")
    elapsed = time.perf_counter()-t0
    assert len(b.records) == 500
    print(f"mock-only Silver rows={len(b.records)} elapsed_s={elapsed:.4f} rows_per_s={len(b.records)/max(elapsed,1e-9):.0f}; NOT real-source throughput")
