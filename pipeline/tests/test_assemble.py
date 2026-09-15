"""results/: every delivered ruling from every folder, nothing held back."""
from __future__ import annotations

import csv
import json

import pytest

from anonymizer.assemble import assemble
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
