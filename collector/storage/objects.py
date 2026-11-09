"""MinIO Bronze snapshots. The key is deterministic by job, hash verifies content."""
from __future__ import annotations
import hashlib
import io
import json
from collector.errors import StorageUnavailable

BUCKETS = ("raw-snapshots", "failed-records", "exports", "archives")


def serialize(raw: dict) -> bytes:
    return json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


class MemoryObjectStore:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}

    def put(self, bucket: str, key: str, data: bytes) -> str:
        self.objects[(bucket, key)] = data
        return hashlib.sha256(data).hexdigest()

    def get(self, bucket: str, key: str) -> bytes:
        return self.objects[(bucket, key)]


class MinioObjectStore:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, secure: bool = False):
        from minio import Minio
        self.client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)

    def put(self, bucket: str, key: str, data: bytes) -> str:
        try:
            self.client.put_object(bucket, key, io.BytesIO(data), len(data), content_type="application/json")
        except Exception as exc:
            raise StorageUnavailable("MinIO write failed") from exc
        return hashlib.sha256(data).hexdigest()

    def get(self, bucket: str, key: str) -> bytes:
        try:
            obj = self.client.get_object(bucket, key)
            try:
                return obj.read()
            finally:
                obj.close()
                obj.release_conn()
        except Exception as exc:
            raise StorageUnavailable("MinIO read failed") from exc
