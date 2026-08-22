"""Object storage for anonymized files ONLY (website_brief §4).

A flat, name-keyed store. MinIO in Docker, local filesystem otherwise. Raw documents
never pass through here — the pipeline produced these files and the import gate checked
them before anything is stored.
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import List


class LocalFileStore:
    def __init__(self, base: str) -> None:
        self.base = Path(base)
        self.base.mkdir(parents=True, exist_ok=True)

    def put(self, name: str, data: bytes) -> None:
        (self.base / name).write_bytes(data)

    def get(self, name: str) -> bytes:
        return (self.base / name).read_bytes()

    def exists(self, name: str) -> bool:
        return (self.base / name).exists()

    def delete(self, name: str) -> None:
        p = self.base / name
        if p.exists():
            p.unlink()

    def list(self) -> List[str]:
        return [p.name for p in self.base.iterdir() if p.is_file()]


class MinioFileStore:
    def __init__(self, endpoint: str, access: str, secret: str, secure: bool) -> None:
        from minio import Minio
        self.bucket = os.getenv("MINIO_ANON_BUCKET", "anonymized")
        self.client = Minio(endpoint, access_key=access, secret_key=secret, secure=secure)
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def put(self, name: str, data: bytes) -> None:
        self.client.put_object(self.bucket, name, io.BytesIO(data), length=len(data))

    def get(self, name: str) -> bytes:
        resp = self.client.get_object(self.bucket, name)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def exists(self, name: str) -> bool:
        from minio.error import S3Error
        try:
            self.client.stat_object(self.bucket, name)
            return True
        except S3Error:
            return False

    def delete(self, name: str) -> None:
        self.client.remove_object(self.bucket, name)

    def list(self) -> List[str]:
        return [o.object_name for o in self.client.list_objects(self.bucket)]


def get_filestore():
    endpoint = os.getenv("MINIO_ENDPOINT", "")
    if endpoint:
        return MinioFileStore(
            endpoint,
            os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            os.getenv("MINIO_SECURE", "false").lower() == "true",
        )
    return LocalFileStore(os.getenv("FILESTORE_DIR", "data/files"))
