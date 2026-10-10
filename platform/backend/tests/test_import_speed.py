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

import db  # noqa: E402
import import_results  # noqa: E402
import server  # noqa: E402

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
    counts = import_results.import_folder(_folder(tmp_path, rulings), publish=True, actor="t",
                                          workers=4)
    assert counts["imported"] == 40
    for doc_id, text in rulings:
        got = db.get_decision(doc_id, body=True)
        assert got is not None, doc_id
        assert got["body_text"] == text, f"{doc_id} got another ruling's text"


def test_a_ruling_the_pipeline_held_never_arrives(tmp_path):
    counts = import_results.import_folder(
        _folder(tmp_path, [("imp_ok1", "نص")], held=["imp_held1"]), publish=True, actor="t", workers=2)
    assert counts["held_by_pipeline"] == 1
    assert db.get_decision("imp_held1") is None


def test_a_record_whose_file_is_gone_is_counted_not_skipped_silently(tmp_path):
    counts = import_results.import_folder(
        _folder(tmp_path, [("imp_ok2", "نص")], missing=["imp_gone"]), publish=True, actor="t", workers=2)
    assert counts["no_file"] == 1 and db.get_decision("imp_gone") is None


def test_a_file_that_still_holds_personal_data_is_refused(tmp_path):
    folder = _folder(tmp_path, [("imp_clean", "نص نظيف"), ("imp_dirty", "اتصل على 0612345678")])
    counts = import_results.import_folder(folder, publish=True, actor="t", workers=2)
    assert counts["gate_quarantined"] == 1
    assert db.get_decision("imp_dirty") is None and db.get_decision("imp_clean") is not None


def test_a_damaged_file_is_reported_and_the_rest_still_import(tmp_path):
    folder = _folder(tmp_path, [("imp_good", "نص سليم"), ("imp_broken", "نص")])
    (folder / "documents" / "imp_broken.docx").write_bytes(b"this is not a word file")
    counts = import_results.import_folder(folder, publish=True, actor="t", workers=2)
    assert counts["unreadable"] == 1
    assert db.get_decision("imp_broken") is None
    assert db.get_decision("imp_good") is not None, "one bad file must not lose the others"


def test_a_hand_edited_ruling_is_left_exactly_as_edited(tmp_path):
    folder = _folder(tmp_path, [("imp_edited", "النص الأصلي مع XXXXXXX")])
    import_results.import_folder(folder, publish=True, actor="t", workers=2)
    before = db.get_decision("imp_edited", body=True)

    import docedit
    current = server.STORE.get(before["file_name"])
    new_text = before["body_text"].replace("الأصلي", "XXXXXXX")
    new_file, stored = docedit.apply_to_docx(current, new_text)
    db.apply_version("imp_edited", base_version=before["version"], current_file=current,
                     new_file=new_file, new_text=stored, actor="admin", action="hide",
                     summary="1 hidden")

    counts = import_results.import_folder(folder, publish=True, actor="t", workers=2)
    assert counts["kept_edited"] == 1
    assert db.get_decision("imp_edited", body=True)["body_text"] == stored, \
        "a re-import must never undo a correction made on the site"


def test_importing_twice_updates_and_never_duplicates(tmp_path):
    folder = _folder(tmp_path, [(f"imp_again_{i}", f"نص {i}") for i in range(10)])
    first = import_results.import_folder(folder, publish=True, actor="t", workers=4)
    second = import_results.import_folder(folder, publish=True, actor="t", workers=4)
    assert first["imported"] == 10 and second["updated"] == 10 and second["imported"] == 0
    assert db.counts()["decisions"] >= 10


@pytest.mark.parametrize("workers", [1, 4])
def test_the_result_does_not_depend_on_how_many_workers_read(tmp_path, workers):
    rulings = [(f"imp_w{workers}_{i}", f"نص رقم {i}") for i in range(12)]
    counts = import_results.import_folder(_folder(tmp_path, rulings), publish=True,
                                          actor="t", workers=workers)
    assert counts["imported"] == 12
    assert all(db.get_decision(d, body=True)["body_text"] == t for d, t in rulings)
