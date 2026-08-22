"""Corpus audit tool: format/kind/chamber counts + duplicate detection."""
from docx import Document

from anonymizer.audit import audit, render_md


def _docx(path, text):
    d = Document()
    for line in text.split("\n"):
        d.add_paragraph(line)
    d.save(str(path))


def test_audit_counts_and_duplicates(tmp_path):
    _docx(tmp_path / "a.docx", "قرار عن الغرفة الإدارية بمحكمة النقض")
    _docx(tmp_path / "b.docx", "قرار عن الغرفة التجارية")
    _docx(tmp_path / "a_copy.docx", "قرار عن الغرفة الإدارية بمحكمة النقض")  # dup of a
    _docx(tmp_path / "empty.docx", "")

    summary, per = audit(tmp_path, soffice="")
    assert summary["total_files"] == 4
    assert summary["by_format"]["docx"] == 4
    assert summary["by_chamber"].get("إدارية") == 2
    assert summary["by_chamber"].get("تجارية") == 1
    assert summary["duplicates"] == 1
    assert summary["empty"] == 1
    # duplicate is reported against the first occurrence
    dup = [r for r in per if r.get("duplicate_of")]
    assert len(dup) == 1 and dup[0]["duplicate_of"] == "a.docx"
    assert "# Corpus audit" in render_md(summary, per)
