"""Importing a results folder: fast, and still obeying every rule it did before.

The reading now happens in worker processes and the writing in batches, which is
where an import like this usually starts losing documents or silently overwriting
corrections. These are the rules that must survive that change.
"""
import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp()
os.environ.update(
    DB_DIR=_tmp, FILESTORE_DIR=os.path.join(_tmp, "files"),
    AUTH_SECRET="test-secret", SEED_EMAIL="admin@x.com", SEED_PASSWORD="admin-pass",
    AUTO_PUBLISH="0",
)
os.environ.pop("DATABASE_URL", None)
os.environ.pop("MINIO_ENDPOINT", None)

import clock  # noqa: E402
import db  # noqa: E402
import versions  # noqa: E402
import importer  # noqa: E402
import server  # noqa: E402
import storage  # noqa: E402

server._startup()


def _docx(text):
    import io
    from docx import Document
    d = Document()
    for line in text.split("\n"):
        d.add_paragraph(line)
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()


def _folder(tmp_path, rulings, held=(), missing=()):
    """A results folder: real files, plus records the pipeline held or lost."""
    out = tmp_path / "results"
    (out / "documents").mkdir(parents=True)
    records = []
    for doc_id, text in rulings:
        (out / "documents" / f"{doc_id}.docx").write_bytes(_docx(text))
        records.append({"doc_id": doc_id, "anonymized_file": f"{doc_id}.docx",
                        "file_path": f"documents/{doc_id}.docx", "status": "done",
                        "format": "docx", "category": {"value": "مدنية"}, "level": "نقض",
                        "fields": {"رقم القرار": {"value": "1"},
                                   "تاريخ القرار": {"value": "01/01/2020"}},
                        "pii": {"removed_count": 1}, "review": "ok"})
    for doc_id in held:
        records.append({"doc_id": doc_id, "status": "quarantined", "quarantined": True,
                        "anonymized_file": f"{doc_id}.docx", "category": {"value": "مدنية"}})
    for doc_id in missing:
        records.append({"doc_id": doc_id, "status": "done", "anonymized_file": f"{doc_id}.docx",
                        "file_path": f"documents/{doc_id}.docx", "category": {"value": "مدنية"}})
    (out / "records.json").write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return out


def test_every_ruling_arrives_with_its_own_text(tmp_path):
    """The obvious failure of a parallel import: text landing on the wrong ruling."""
    rulings = [(f"imp_{i}", f"محكمة النقض\nنص القرار رقم {i} بعد إزالة XXXXXXX") for i in range(40)]
    counts = importer.run(_folder(tmp_path, rulings), publish=True, actor="t",
                                          workers=4)
    assert counts["imported"] == 40
    for doc_id, text in rulings:
        got = db.get_decision(doc_id, body=True)
        assert got is not None, doc_id
        assert got["body_text"] == text, f"{doc_id} got another ruling's text"


def test_a_ruling_the_pipeline_held_never_arrives(tmp_path):
    counts = importer.run(
        _folder(tmp_path, [("imp_ok1", "نص")], held=["imp_held1"]), publish=True, actor="t", workers=2)
    assert counts["held_by_pipeline"] == 1
    assert db.get_decision("imp_held1") is None


def test_a_record_whose_file_is_gone_is_counted_not_skipped_silently(tmp_path):
    counts = importer.run(
        _folder(tmp_path, [("imp_ok2", "نص")], missing=["imp_gone"]), publish=True, actor="t", workers=2)
    assert counts["no_file"] == 1 and db.get_decision("imp_gone") is None


def test_a_file_that_still_holds_personal_data_is_refused(tmp_path):
    folder = _folder(tmp_path, [("imp_clean", "نص نظيف"), ("imp_dirty", "اتصل على 0612345678")])
    counts = importer.run(folder, publish=True, actor="t", workers=2)
    assert counts["gate_quarantined"] == 1
    assert db.get_decision("imp_dirty") is None and db.get_decision("imp_clean") is not None


def test_a_damaged_file_is_reported_and_the_rest_still_import(tmp_path):
    folder = _folder(tmp_path, [("imp_good", "نص سليم"), ("imp_broken", "نص")])
    (folder / "documents" / "imp_broken.docx").write_bytes(b"this is not a word file")
    counts = importer.run(folder, publish=True, actor="t", workers=2)
    assert counts["unreadable"] == 1
    assert db.get_decision("imp_broken") is None
    assert db.get_decision("imp_good") is not None, "one bad file must not lose the others"


def test_a_hand_edited_ruling_is_left_exactly_as_edited(tmp_path):
    folder = _folder(tmp_path, [("imp_edited", "النص الأصلي مع XXXXXXX")])
    importer.run(folder, publish=True, actor="t", workers=2)
    before = db.get_decision("imp_edited", body=True)

    import docedit
    current = storage.STORE.get(before["file_name"])
    new_text = before["body_text"].replace("الأصلي", "XXXXXXX")
    new_file, stored = docedit.apply_to_docx(current, new_text)
    versions.apply_version("imp_edited", base_version=before["version"], current_file=current,
                     new_file=new_file, new_text=stored, actor="admin", action="hide",
                     summary="1 hidden")

    counts = importer.run(folder, publish=True, actor="t", workers=2)
    assert counts["kept_edited"] == 1
    assert db.get_decision("imp_edited", body=True)["body_text"] == stored, \
        "a re-import must never undo a correction made on the site"


def test_importing_twice_updates_and_never_duplicates(tmp_path):
    folder = _folder(tmp_path, [(f"imp_again_{i}", f"نص {i}") for i in range(10)])
    first = importer.run(folder, publish=True, actor="t", workers=4)
    second = importer.run(folder, publish=True, actor="t", workers=4)
    assert first["imported"] == 10 and second["updated"] == 10 and second["imported"] == 0
    assert db.counts()["decisions"] >= 10


@pytest.mark.parametrize("workers", [1, 4])
def test_the_result_does_not_depend_on_how_many_workers_read(tmp_path, workers):
    rulings = [(f"imp_w{workers}_{i}", f"نص رقم {i}") for i in range(12)]
    counts = importer.run(_folder(tmp_path, rulings), publish=True,
                                          actor="t", workers=workers)
    assert counts["imported"] == 12
    assert all(db.get_decision(d, body=True)["body_text"] == t for d, t in rulings)


# ---------------- the admin's upload: the same import, through a .zip ----------------
RULING_WITH_AN_OUTCOME = "محكمة النقض\nرفض الطلب\nنص القرار بعد إزالة XXXXXXX\nلهذه الأسباب قضت محكمة النقض برفض الطلب"


def _zip_of(folder):
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for p in folder.rglob("*"):
            if p.is_file():
                z.write(p, p.relative_to(folder).as_posix())
    return buf.getvalue()


def _upload(client, data):
    tok = client.post("/api/auth/login", json={"email": "admin@x.com", "password": "admin-pass"}).json()["token"]
    return client.post("/api/admin/import", headers={"Authorization": f"Bearer {tok}"},
                       files={"file": ("delivery.zip", data, "application/zip")})


def test_the_upload_reads_the_ruling_as_the_command_line_does(tmp_path):
    from fastapi.testclient import TestClient
    folder = _folder(tmp_path, [("up_same", RULING_WITH_AN_OUTCOME)])
    with TestClient(server.app) as client:
        out = _upload(client, _zip_of(folder)).json()
    assert out["status"] == "done" and out["imported"] == 1
    assert db.get_decision("up_same")["outcome"] == "رفض الطلب", "the outcome read off the file"

    # the command line on the same delivery gives the very same row
    by_upload = db.get_decision("up_same")
    importer.run(folder, publish=False, actor="t", workers=1)
    by_folder = db.get_decision("up_same")
    for k in ("outcome", "theme", "rule", "keywords", "category", "decision_no"):
        assert by_upload[k] == by_folder[k], k


def test_a_large_upload_waits_for_the_worker_and_loses_nothing(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import dataclasses
    import settings
    monkeypatch.setattr(settings, "S", dataclasses.replace(settings.S, import_inline_max=2))
    rulings = [(f"up_big_{i}", f"نص رقم {i}") for i in range(5)]
    with TestClient(server.app) as client:
        job = _upload(client, _zip_of(_folder(tmp_path, rulings))).json()
        assert job["status"] == "queued" and job["total_records"] == 5
        assert db.get_decision("up_big_0") is None                 # not yet
        assert importer.run_queued(publish=False) == 1             # what the worker does
        tok = client.post("/api/auth/login", json={"email": "admin@x.com", "password": "admin-pass"}).json()["token"]
        done = client.get(f"/api/admin/import/jobs/{job['id']}", headers={"Authorization": f"Bearer {tok}"}).json()
    assert done["status"] == "done" and done["imported"] == 5
    assert all(db.get_decision(d, body=True)["body_text"] == t for d, t in rulings)
    assert not [n for n in storage.STORE.list() if n.startswith("import-")], "the upload is not kept once imported"


def test_an_upload_that_is_not_a_delivery_is_refused(tmp_path):
    from fastapi.testclient import TestClient
    with TestClient(server.app) as client:
        r = _upload(client, b"not a zip at all")
    assert r.status_code == 400


def test_a_subject_a_model_wrote_survives_importing_the_ruling_again(tmp_path):
    """The file prints no subject; a model gave it one. Importing it again must not
    blank what the file simply does not carry."""
    folder = _folder(tmp_path, [("up_model", "نص بلا موضوع")])
    importer.run(folder, publish=True, actor="t", workers=1)
    with db.session() as s:
        d = s.get(db.Decision, "up_model")
        d.theme, d.theme_key, d.theme_source, d.abstract = "الكراء", "الكراء", "model", "ملخص"
        s.commit()
    importer.run(folder, publish=True, actor="t", workers=1)
    d = db.get_decision("up_model")
    assert (d["theme"], d["theme_source"], d["abstract"]) == ("الكراء", "model", "ملخص")


def test_the_worker_asks_the_model_once_for_a_new_ruling(tmp_path, monkeypatch):
    """AUTO_ENRICH=1: a ruling that arrives printing no subject gets a summary from the
    model, and is never asked again -- whatever the model answered."""
    import dataclasses
    import enrich
    import settings
    import worker
    long_text = "محكمة النقض\n" + "حيث إن الطاعن يعيب على القرار المطعون فيه خرق القانون. " * 40
    importer.run(_folder(tmp_path, [("enrich_new", long_text)]), publish=True, actor="t", workers=1)
    with db.session() as s:      # what the corpus was already: asked long ago
        from sqlalchemy import update
        s.execute(update(db.Decision).where(db.Decision.doc_id != "enrich_new")
                  .values(enriched_at=clock.utcnow()))
        s.commit()
    asked = []

    def fake_ask(client, text, chamber, vocab, **kw):
        asked.append(text[:20])
        return {"theme": "", "abstract": "لا يقبل الطعن بالنقض إلا ممن كان طرفا في الحكم المطعون فيه، والمحكمة تراقب ذلك تلقائيا."}, None

    monkeypatch.setattr(enrich, "ask", fake_ask)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(settings, "S", dataclasses.replace(settings.S, auto_enrich=True))
    first = worker.enrich_new()
    assert first["processed"] == 1 and first["abstract"] == 1 and len(asked) == 1
    assert db.get_decision("enrich_new", body=True)["abstract"].startswith("لا يقبل")
    assert worker.enrich_new() == {} and len(asked) == 1, "never asked twice"


def test_a_zip_with_windows_backslash_paths_imports(tmp_path):
    """Older Windows zip tools separate folders with backslashes; the upload reads it all the same."""
    import io
    import zipfile
    from fastapi.testclient import TestClient
    folder = _folder(tmp_path, [("up_backslash", RULING_WITH_AN_OUTCOME)])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for p in folder.rglob("*"):
            if p.is_file():
                z.writestr("results" + chr(92) + str(p.relative_to(folder)).replace("/", chr(92)), p.read_bytes())
    with TestClient(server.app) as client:
        out = _upload(client, buf.getvalue()).json()
    assert out["status"] == "done" and out["imported"] == 1, out
    assert db.get_decision("up_backslash")["outcome"] == "رفض الطلب"
