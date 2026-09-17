"""Where the anonymized files live: a folder, or S3 / GCS / MinIO through one protocol.

These run against a stand-in for the storage client, so they check what we ask the
storage to do -- which is where the mistakes are -- without a network or an account.
"""
import io
import os
import tempfile

import pytest

import filestore


class FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data

    def close(self) -> None:
        pass

    def release_conn(self) -> None:
        pass


class FakeS3:
    """Remembers what it was asked, and holds objects in memory."""

    def __init__(self, buckets=("anonymized",)) -> None:
        self.buckets = set(buckets)
        self.objects: dict[tuple[str, str], bytes] = {}
        self.made: list[str] = []

    def bucket_exists(self, bucket):
        return bucket in self.buckets

    def make_bucket(self, bucket):
        self.made.append(bucket)
        self.buckets.add(bucket)

    def put_object(self, bucket, name, data, length):
        self.objects[(bucket, name)] = data.read()

    def get_object(self, bucket, name):
        return FakeResponse(self.objects[(bucket, name)])

    def stat_object(self, bucket, name):
        from minio.error import S3Error
        if (bucket, name) not in self.objects:
            raise S3Error("NoSuchKey", "missing", name, "", "", None)
        return object()

    def remove_object(self, bucket, name):
        self.objects.pop((bucket, name), None)

    def list_objects(self, bucket):
        return [type("O", (), {"object_name": n})() for (b, n) in self.objects if b == bucket]


@pytest.fixture
def clean_env(monkeypatch):
    for name in list(os.environ):
        if name.startswith(("S3_", "MINIO_", "FILESTORE_")):
            monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_without_an_endpoint_files_go_in_a_folder(clean_env):
    tmp = tempfile.mkdtemp()
    clean_env.setenv("FILESTORE_DIR", tmp)
    store = filestore.get_filestore()
    assert isinstance(store, filestore.LocalFileStore)
    store.put("a.docx", b"hello")
    assert store.get("a.docx") == b"hello" and store.exists("a.docx")
    assert store.list() == ["a.docx"]
    store.delete("a.docx")
    assert not store.exists("a.docx")


def test_reading_and_writing_go_to_the_configured_bucket(clean_env):
    fake = FakeS3()
    store = filestore.S3FileStore("s3.amazonaws.com", "k", "s", bucket="anonymized", client=fake)
    store.put("a.docx", b"ruling")
    assert fake.objects[("anonymized", "a.docx")] == b"ruling"
    assert store.get("a.docx") == b"ruling"
    assert store.exists("a.docx") and not store.exists("missing.docx")
    assert store.list() == ["a.docx"]
    store.delete("a.docx")
    assert not store.exists("a.docx")


def test_a_missing_bucket_is_an_error_not_a_bucket_we_create(clean_env):
    """On S3 and GCS the app's key normally may not create buckets: creating one
    silently is how you end up writing rulings into the wrong place."""
    fake = FakeS3(buckets=())
    with pytest.raises(RuntimeError, match="does not exist"):
        filestore.S3FileStore("storage.googleapis.com", "k", "s", bucket="rulings", client=fake)
    assert fake.made == []

    store = filestore.S3FileStore("minio:9000", "k", "s", bucket="rulings",
                                  create_bucket=True, client=FakeS3(buckets=()))
    assert store.client.made == ["rulings"]         # local MinIO, asked for explicitly


def test_unreachable_storage_says_so_at_startup(clean_env):
    class Broken(FakeS3):
        def bucket_exists(self, bucket):
            raise OSError("connection refused")

    with pytest.raises(RuntimeError, match="Cannot reach the file storage"):
        filestore.S3FileStore("s3.amazonaws.com", "k", "s", bucket="b", client=Broken())


def test_the_bucket_check_can_be_skipped_for_a_restricted_key(clean_env):
    class Forbidden(FakeS3):
        def bucket_exists(self, bucket):
            raise OSError("access denied")

    store = filestore.S3FileStore("s3.amazonaws.com", "k", "s", bucket="b",
                                  verify_bucket=False, client=Forbidden())
    store.put("a.docx", b"x")
    assert store.get("a.docx") == b"x"


def test_settings_pick_the_storage_and_default_to_https(clean_env):
    seen = {}

    class Recorder(FakeS3):
        def __init__(self, **kw):
            super().__init__()

    def fake_minio(endpoint, access_key, secret_key, secure, region):
        seen.update(endpoint=endpoint, access_key=access_key, secret_key=secret_key,
                    secure=secure, region=region)
        return FakeS3()

    import minio
    clean_env.setattr(minio, "Minio", fake_minio)
    clean_env.setenv("S3_ENDPOINT", "storage.googleapis.com")
    clean_env.setenv("S3_ACCESS_KEY", "GOOG1E")
    clean_env.setenv("S3_SECRET_KEY", "hmac-secret")
    clean_env.setenv("S3_REGION", "europe-west1")
    store = filestore.get_filestore()
    assert seen == {"endpoint": "storage.googleapis.com", "access_key": "GOOG1E",
                    "secret_key": "hmac-secret", "secure": True, "region": "europe-west1"}
    assert store.bucket == "anonymized"


def test_the_old_minio_settings_still_work(clean_env):
    seen = {}

    def fake_minio(endpoint, access_key, secret_key, secure, region):
        seen.update(endpoint=endpoint, secure=secure, region=region)
        return FakeS3(buckets=("files",))

    import minio
    clean_env.setattr(minio, "Minio", fake_minio)
    clean_env.setenv("MINIO_ENDPOINT", "minio:9000")
    clean_env.setenv("MINIO_ACCESS_KEY", "minioadmin")
    clean_env.setenv("MINIO_SECRET_KEY", "minioadmin")
    clean_env.setenv("MINIO_SECURE", "false")
    clean_env.setenv("MINIO_ANON_BUCKET", "files")
    store = filestore.get_filestore()
    assert seen == {"endpoint": "minio:9000", "secure": False, "region": None}
    assert store.bucket == "files"


def test_an_edited_ruling_round_trips_through_object_storage(clean_env):
    """The edit path only ever calls get/put/exists: it works the same on S3."""
    import docedit
    from docx import Document

    doc = Document()
    for line in ("محكمة النقض — مدنية", "حضر السيد محمد العلوي"):
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)

    store = filestore.S3FileStore("s3.amazonaws.com", "k", "s", bucket="anonymized", client=FakeS3())
    store.put("r.docx", buf.getvalue())
    text = docedit.read_text(store.get("r.docx"))
    edited, new_text = docedit.apply_to_docx(store.get("r.docx"), text.replace("محمد العلوي", "XXXXXXX"))
    store.put("r.docx", edited)
    assert "محمد العلوي" not in docedit.read_text(store.get("r.docx"))
    assert docedit.read_text(store.get("r.docx")) == new_text
