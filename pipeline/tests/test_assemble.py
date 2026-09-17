"""results/: every delivered ruling from every folder, nothing held back."""
from __future__ import annotations

import csv
import json
import zipfile

import pytest

from anonymizer.assemble import assemble, load_edits
from anonymizer.pipeline import Pipeline, RunOptions
from test_listing_pipeline import FakeAI, _docx, _ruling, _settings


def _process(tmp_path, folder, *names, blank=()):
    s = _settings(tmp_path, folder=f"corpus/{folder}", out=f"work/{folder}", db="work/cases.db")
    for n in names:
        _ruling(s.input_dir / f"{n}.docx", n)
    for n in blank:
        _docx(s.input_dir / f"{n}.docx", "حضر محمد العلوي")   # held as empty
    Pipeline(s, FakeAI()).run(RunOptions())


def test_results_gather_every_folder_and_leave_out_held_files(tmp_path):
    _process(tmp_path, "02_statut", "a", "b", blank=["held"])
    _process(tmp_path, "01_civile", "c")
    counts = assemble(tmp_path / "work", tmp_path / "results")

    assert counts["rulings"] == 3
    assert counts["folders"] == {"01_civile": 1, "02_statut": 2}
    rows = list(csv.DictReader(open(tmp_path / "results" / "listing.csv", encoding="utf-8-sig")))
    files = sorted(r["الملف"] for r in rows)
    assert files == ["documents/personal_status/a.docx", "documents/personal_status/b.docx",
                     "documents/personal_status/c.docx"]
    for f in files:
        assert (tmp_path / "results" / f).exists()
    assert not list((tmp_path / "results").rglob("held.docx")), "held files never reach results"
    recs = json.loads((tmp_path / "results" / "records.json").read_text(encoding="utf-8"))
    assert {r["corpus"] for r in recs} == {"01_civile", "02_statut"}
    assert (tmp_path / "results" / "README.md").exists()


def test_results_are_rebuilt_whole(tmp_path):
    _process(tmp_path, "02_statut", "a")
    assemble(tmp_path / "work", tmp_path / "results")
    stray = tmp_path / "results" / "documents" / "civil" / "old.docx"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"from an earlier build")
    assemble(tmp_path / "work", tmp_path / "results")
    assert not stray.exists()


def test_the_same_file_delivered_by_two_folders_is_an_error(tmp_path):
    _process(tmp_path, "one", "a")
    s = _settings(tmp_path, folder="corpus/two", out="work/two", db="work/other.db")
    _ruling(s.input_dir / "a.docx", "مختلف")      # same name, different content
    Pipeline(s, FakeAI()).run(RunOptions())
    with pytest.raises(SystemExit, match="delivered by both"):
        assemble(tmp_path / "work", tmp_path / "results")


def test_hand_edits_from_the_platform_are_applied_and_never_reach_the_work_folder(tmp_path):
    _process(tmp_path, "02_statut", "a", "b")
    work_file = next((tmp_path / "work" / "02_statut").rglob("a.docx"))
    before = work_file.read_bytes()

    export = tmp_path / "edits.zip"
    with zipfile.ZipFile(export, "w") as z:
        z.writestr("edits.json", json.dumps([
            {"doc_id": "a", "file_name": "a.docx", "version": 3, "edited_at": "2026-09-17",
             "edited_by": "admin@x.com", "court": "محكمة النقض", "category": "جنائية",
             "decision_no": "901", "file_no": "", "date": "01/02/2020", "city": "فاس"},
            {"doc_id": "gone", "file_name": "gone.docx", "category": "مدنية"},
        ], ensure_ascii=False))
        z.writestr("files/a.docx", b"edited file")
        z.writestr("files/gone.docx", b"x")

    for _ in range(2):                          # and again: a rebuild keeps the edit
        counts = assemble(tmp_path / "work", tmp_path / "results", load_edits(export))
        assert counts["edited"] == 1 and counts["edits_not_found"] == ["gone"]
        out = tmp_path / "results" / "documents" / "criminal" / "a.docx"   # moved chamber
        assert out.read_bytes() == b"edited file"
    assert work_file.read_bytes() == before, "the edit must not write through a hard link"
    recs = json.loads((tmp_path / "results" / "records.json").read_text(encoding="utf-8"))
    rec = next(r for r in recs if r["doc_id"] == "a")
    assert rec["fields"]["رقم القرار"]["value"] == "901" and rec["city"] == "فاس"
    assert rec["edited"]["version"] == 3
