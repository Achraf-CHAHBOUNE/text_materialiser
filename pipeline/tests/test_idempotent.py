"""Idempotence: same input -> byte-identical anonymized files, every run (Script.md §2/§6)."""
import dataclasses
import hashlib

from docx import Document

from anonymizer.config import Settings
from anonymizer.llm.base import BatchResult, DocIdentity, DocumentAI, PIIEntity
from anonymizer.pipeline import Pipeline, RunOptions


class FakeAI(DocumentAI):
    def process_pdf(self, pdf_bytes: bytes) -> BatchResult:
        return self._r()

    def process_text(self, text: str) -> BatchResult:
        return self._r()

    def _r(self) -> BatchResult:
        return BatchResult(
            pages=[], pii=[PIIEntity("محمد العلوي", "name")],
            court="محكمة النقض", category="تجارية",
            identity=DocIdentity(level="نقض", decision_no="652",
                                 date="2018-12-12", file_no="1293/8222/2017"),
            input_tokens=100, output_tokens=50,
        )


def _run(tmp):
    s = dataclasses.replace(
        Settings.load(), provider="fake", api_key="x", soffice_path="",
        input_dir=tmp / "in", output_dir=tmp / "out",
        state_file=tmp / "out" / ".state.json", db_path=tmp / "cases.db",
        max_workers=1, budget_usd=0,
    )
    Pipeline(s, provider=FakeAI()).run(RunOptions(overwrite=True))
    return s.output_dir


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_reruns_are_byte_identical(tmp_path):
    inp = tmp_path / "in"
    inp.mkdir(parents=True)
    d = Document()
    d.add_paragraph("حكمت المحكمة على محمد العلوي بأداء المبلغ المحكوم به")
    d.save(str(inp / "doc.docx"))

    out = _run(tmp_path)
    first = _sha(out / "doc.docx")
    # second run over the same input must reproduce the exact same file
    out = _run(tmp_path)
    second = _sha(out / "doc.docx")
    assert first == second, "anonymized .docx is not byte-identical across runs"
