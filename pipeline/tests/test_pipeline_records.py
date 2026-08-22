"""End-to-end pipeline wiring: records output + leak-test quarantine, no network.

Uses a fake provider so the full run (read -> detect -> redact -> leak-test -> records)
is exercised without any LLM call.
"""
import dataclasses
import json
from pathlib import Path

import pytest
from docx import Document

from anonymizer.config import Settings
from anonymizer.llm.base import BatchResult, DocIdentity, DocumentAI, PIIEntity
from anonymizer.pipeline import Pipeline, RunOptions

FLAGGED = ["محمد العلوي", "سعاد بناني"]


class FakeAI(DocumentAI):
    """Flags a fixed name list; fills a plausible identity. No OCR/network."""
    def process_pdf(self, pdf_bytes: bytes) -> BatchResult:
        return self._result()

    def process_text(self, text: str) -> BatchResult:
        return self._result()

    def _result(self) -> BatchResult:
        return BatchResult(
            pages=[], pii=[PIIEntity(n, "name") for n in FLAGGED],
            court="محكمة النقض", category="تجارية",
            identity=DocIdentity(level="نقض", court="محكمة النقض",
                                 decision_no="652", date="2018-12-12", file_no="1293/8222/2017"),
            refs=[], input_tokens=100, output_tokens=50,
        )


def _docx(path: Path, text: str) -> None:
    d = Document()
    for line in text.split("\n"):
        d.add_paragraph(line)
    d.save(str(path))


def _settings(tmp: Path) -> Settings:
    base = dataclasses.replace(
        Settings.load(),
        provider="fake", api_key="x", soffice_path="",
        input_dir=tmp / "in", output_dir=tmp / "out",
        state_file=tmp / "out" / ".state.json", db_path=tmp / "cases.db",
        max_workers=1, budget_usd=0,
    )
    (tmp / "in").mkdir(parents=True, exist_ok=True)
    return base


def test_records_output_and_diacritic_redaction(tmp_path):
    s = _settings(tmp_path)
    # A: name plain. B: same-style name carrying harakat — the redactor must still remove it
    # (regression for the char-by-char matcher), so BOTH pass the leak gate.
    _docx(s.input_dir / "clean.docx", "حكمت المحكمة على محمد العلوي بأداء المبلغ المحكوم به")
    _docx(s.input_dir / "diac.docx", "المطلوبة في النقض سُعَاد بَنَّانِي التمست رفض الطلب")

    totals = Pipeline(s, provider=FakeAI()).run(RunOptions(overwrite=True))

    for name in ("records.json", "records.xlsx", "run_report.md", "quarantine.csv"):
        assert (s.output_dir / name).exists(), f"missing {name}"

    records = json.loads((s.output_dir / "records.json").read_text(encoding="utf-8"))
    by_id = {r["doc_id"]: r for r in records}
    assert set(by_id) == {"clean", "diac"}
    # both delivered clean — no leak survived, nothing quarantined
    assert all(by_id[k]["leak_test"]["passed"] for k in by_id)
    assert totals["quarantined"] == 0 and totals["leaked"] == 0
    assert (s.output_dir / "clean.docx").exists() and (s.output_dir / "diac.docx").exists()

    # extracted fields carried through with source/confidence
    f = by_id["clean"]["fields"]["رقم القرار"]
    assert f["value"] == "652" and f["source"] in ("llm", "llm+regex")


def test_quarantine_mechanism_when_a_leak_slips_through(tmp_path, monkeypatch):
    """If a leak ever survives, it must be moved out of the clean output dir and logged."""
    from anonymizer.core.leaktest import LeakResult
    monkeypatch.setattr("anonymizer.pipeline.leak_scan",
                        lambda text, vals: LeakResult(passed=False, hits=1, leaked=["محمد العلوي"]))
    s = _settings(tmp_path)
    _docx(s.input_dir / "leaky.docx", "نص القرار على محمد العلوي")

    totals = Pipeline(s, provider=FakeAI()).run(RunOptions(overwrite=True))

    records = json.loads((s.output_dir / "records.json").read_text(encoding="utf-8"))
    rec = records[0]
    assert rec["leak_test"]["passed"] is False and rec["status"] == "quarantined"
    assert (s.output_dir / "_quarantine" / "leaky.docx").exists()
    assert not (s.output_dir / "leaky.docx").exists()
    assert totals["leaked"] == 1 and totals["quarantined"] == 1


def test_budget_ceiling_halts(tmp_path):
    s = dataclasses.replace(_settings(tmp_path), budget_usd=0.00001)  # tiny -> halts after first doc
    for i in range(4):
        _docx(s.input_dir / f"d{i}.docx", "نص على محمد العلوي هنا")
    totals = Pipeline(s, provider=FakeAI()).run(RunOptions(overwrite=True))
    assert totals["halted"] is True
    assert totals["documents"] < 4  # stopped early
