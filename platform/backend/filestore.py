"""Storage for the anonymized files ONLY (website_brief §4).

A flat, name-keyed store with two backings:

  - a folder on disk (the default, and what the tests use);
  - any S3-compatible object storage -- AWS S3, Google Cloud Storage through its
    S3 interface, or a MinIO server. One protocol, so moving between them is a
    change of settings, never of code.

Raw documents never pass through here: the pipeline produced these files and the
import gate checked them before anything is stored.

Settings (S3_* preferred; the older MINIO_* names still work):

    S3_ENDPOINT      host[:port], no scheme        s3.amazonaws.com
                                                   storage.googleapis.com   (GCS)
                                                   minio:9000               (MinIO)
    S3_BUCKET        bucket name                   default "anonymized"
    S3_ACCESS_KEY    access key      (GCS: an HMAC key from Cloud Storage settings)
    S3_SECRET_KEY    secret key
    S3_REGION        the bucket's region           eu-west-3, europe-west1, ...
    S3_SECURE        "false" only for a local MinIO over plain HTTP (default: HTTPS)
    S3_CREATE_BUCKET "true" creates the bucket when missing -- local MinIO only.
                     On S3/GCS the app's key normally may not create buckets, so
                     a missing bucket is an error with a clear message instead.
    S3_VERIFY_BUCKET "false" skips the startup check (a key allowed to read and
                     write objects but not to look the bucket up).

With no S3_ENDPOINT/MINIO_ENDPOINT, files go in FILESTORE_DIR (default data/files).
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


class S3FileStore:
    """Any S3-compatible storage, through the `minio` client library."""

    def __init__(self, endpoint: str, access: str, secret: str, *, bucket: str,
                 secure: bool = True, region: str = "", create_bucket: bool = False,
                 verify_bucket: bool = True, client=None) -> None:
        self.bucket = bucket
        self.endpoint = endpoint
        if client is None:
            from minio import Minio
            client = Minio(endpoint, access_key=access, secret_key=secret,
                           secure=secure, region=region or None)
        self.client = client
        if verify_bucket:
            self._verify(create_bucket)

    def _verify(self, create_bucket: bool) -> None:
        """Fail at startup with a readable message, not on the first download."""
        where = f"{self.endpoint}/{self.bucket}"
        try:
            found = self.client.bucket_exists(self.bucket)
        except Exception as e:
            raise RuntimeError(
                f"Cannot reach the file storage at {where}: {e}. Check S3_ENDPOINT, the "
                f"keys and S3_REGION, or set S3_VERIFY_BUCKET=false if the key may not "
                f"look buckets up.") from e
        if found:
            return
        if not create_bucket:
            raise RuntimeError(
                f"The bucket {where} does not exist. Create it (S3/GCS keys usually may "
                f"not), or set S3_CREATE_BUCKET=true for a local MinIO.")
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


MinioFileStore = S3FileStore          # the name this class had before


def _env(name: str, old: str, default: str = "") -> str:
    return os.getenv(name) or os.getenv(old) or default


def _flag(name: str, old: str, default: bool) -> bool:
    raw = _env(name, old)
    return default if raw == "" else raw.strip().lower() in ("1", "true", "yes", "on")


def get_filestore(**overrides):
    endpoint = _env("S3_ENDPOINT", "MINIO_ENDPOINT")
    if not endpoint:
        return LocalFileStore(os.getenv("FILESTORE_DIR", "data/files"))
    settings = dict(
        bucket=_env("S3_BUCKET", "MINIO_ANON_BUCKET", "anonymized"),
        secure=_flag("S3_SECURE", "MINIO_SECURE", True),
        region=_env("S3_REGION", "MINIO_REGION"),
        create_bucket=_flag("S3_CREATE_BUCKET", "MINIO_CREATE_BUCKET", False),
        verify_bucket=_flag("S3_VERIFY_BUCKET", "MINIO_VERIFY_BUCKET", True),
    )
    settings.update(overrides)
    return S3FileStore(endpoint, _env("S3_ACCESS_KEY", "MINIO_ACCESS_KEY"),
                       _env("S3_SECRET_KEY", "MINIO_SECRET_KEY"), **settings)
