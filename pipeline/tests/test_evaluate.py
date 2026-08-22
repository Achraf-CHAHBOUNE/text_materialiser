"""Evaluation harness: scores a real run against ground truth and reports §4 metrics."""
import dataclasses
import json

from docx import Document

from anonymizer.config import Settings
from anonymizer.evaluate import evaluate, render_md, _metrics
from anonymizer.llm.base import BatchResult, DocIdentity, DocumentAI, PIIEntity
from anonymizer.pipeline import Pipeline, RunOptions


class FakeAI(DocumentAI):
    def process_pdf(self, b):  # noqa
        return self._r()

    def process_text(self, t):  # noqa
        return self._r()

    def _r(self):
        return BatchResult(
            pages=[], pii=[PIIEntity("محمد العلوي", "name")],
            court="محكمة النقض", category="تجارية",
            identity=DocIdentity(level="نقض", decision_no="652",
                                 date="2018-12-12", file_no="1293/8222/2017"),
            input_tokens=100, output_tokens=50,
        )


def test_harness_scores_a_run(tmp_path):
    s = dataclasses.replace(
        Settings.load(), provider="fake", api_key="x", soffice_path="",
        input_dir=tmp_path / "in", output_dir=tmp_path / "out",
        state_file=tmp_path / "out" / ".state.json", db_path=tmp_path / "cases.db",
        max_workers=1, budget_usd=0,
    )
    (tmp_path / "in").mkdir(parents=True)
    d = Document()
    d.add_paragraph("حكمت المحكمة على محمد العلوي بأداء المبلغ المحكوم به")
    d.save(str(s.input_dir / "652_Cassation.docx"))

    Pipeline(s, provider=FakeAI()).run(RunOptions(overwrite=True))

    truth = {
        "652_Cassation": {
            "format": "docx", "chamber": "تجارية", "level": "نقض",
            "fields": {"رقم القرار": "652", "رقم الملف": "1293/8222/2017",
                       "تاريخ القرار": "2018-12-12"},
            "pii": ["محمد العلوي"],
            "kept_terms": ["المبلغ المحكوم به"],
            "links": [],
        }
    }
    result = evaluate(truth, s.output_dir)
    m = _metrics(result["overall"])

    assert result["evaluated"] == 1 and not result["missing"]
    assert m["pii_recall"] == 100.0          # the name was removed
    assert m["pii_precision_proxy"] == 100.0  # the kept term survived
    assert m["category"] == 100.0
    assert m["fields"]["رقم القرار"] == 100.0
    # markdown renders with per-format + per-chamber rows
    md = render_md(result)
    assert "format · docx" in md and "chamber · تجارية" in md
