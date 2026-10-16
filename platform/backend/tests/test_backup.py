"""The files' half of a backup: complete on its own, cheap when little changed, and a
restore that puts the store back exactly as it was."""
import os

from ops import backup


def _store(tmp_path, monkeypatch):
    for k in ("S3_ENDPOINT", "MINIO_ENDPOINT"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("FILESTORE_DIR", str(tmp_path / "store"))
    from filestore import get_filestore
    return get_filestore()


def test_a_second_backup_copies_only_what_changed(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    for i in range(5):
        store.put(f"r{i}.docx", f"ruling {i}".encode())
    first = backup.save(tmp_path / "backups" / "20261016-0100")
    assert first["copied"] == 5 and first["linked"] == 0

    store.put("r2.docx", b"ruling 2, corrected")             # same name, new content
    second = backup.save(tmp_path / "backups" / "20261017-0100")
    assert second["copied"] == 1 and second["linked"] == 4
    assert (tmp_path / "backups/20261017-0100/files/r2.docx").read_bytes() == b"ruling 2, corrected"
    assert (tmp_path / "backups/20261016-0100/files/r2.docx").read_bytes() == b"ruling 2", \
        "an older backup keeps the file as it was then"


def test_a_restore_puts_the_store_back_exactly(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    store.put("a.docx", b"A")
    store.put("b.docx", b"B")
    backup.save(tmp_path / "backups" / "20261016-0100")

    store.put("a.docx", b"A changed later")
    store.delete("b.docx")
    store.put("c.docx", b"added later")
    out = backup.restore(tmp_path / "backups" / "20261016-0100")
    assert out == {"files": 2, "uploaded": 2, "deleted": 1}
    assert store.get("a.docx") == b"A" and store.get("b.docx") == b"B"
    assert not store.exists("c.docx")


def test_an_unfinished_backup_is_not_used_as_the_base(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    store.put("a.docx", b"A")
    (tmp_path / "backups" / "20261015-0100" / "files").mkdir(parents=True)   # cut off: no manifest
    out = backup.save(tmp_path / "backups" / "20261016-0100")
    assert out["copied"] == 1 and out["since"] == ""
    assert os.path.exists(tmp_path / "backups/20261016-0100/files/manifest.json")
