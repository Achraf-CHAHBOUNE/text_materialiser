"""Evaluation harness (Script.md §4 / §6).

Scores a completed run against a ground-truth annotation file and prints the §4
metrics table — **broken down by format and by chamber**, not just a global average.
It reads only the delivered output (records.json + the anonymized files); it never runs
the model, so it is fast, re-runnable, and CI-friendly.

Usage:
    python -m anonymizer.evaluate --truth truth.json --output output/ [--md report.md]

Ground-truth file: a JSON object keyed by doc_id, e.g.
    {
      "652_Cassation": {
        "format": "docx", "chamber": "تجارية", "level": "نقض",
        "fields": {"رقم القرار": "652", "رقم الملف": "1293/8222/2017", "تاريخ القرار": "2018-12-12"},
        "pii": ["محمد العلوي"],            // must be ABSENT from the output (recall)
        "kept_terms": ["المبلغ المحكوم به"], // must be PRESENT (precision / no over-removal)
        "links": ["3646_appel"]             // expected linked doc_ids (relation)
      }
    }
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from docx import Document

from .core.leaktest import leak_scan

_DIAC = re.compile("[ؐ-ؚـً-ٰٟ]")
_AR2ASCII = {ord("٠") + i: str(i) for i in range(10)}  # Arabic-Indic digits -> ASCII


def _norm(s: str) -> str:
    s = (s or "").translate(_AR2ASCII)
    s = _DIAC.sub("", s)
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي")
    return re.sub(r"\s+", "", s)


def _delivered_text(output_dir: Path, rec: dict) -> str:
    name = rec.get("anonymized_file") or (rec["doc_id"] + ".docx")
    path = output_dir / name
    if not path.exists():
        path = output_dir / "_quarantine" / name   # leaked files live here
    if not path.exists():
        return ""
    return "\n".join(p.text for p in Document(str(path)).paragraphs)


class Tally:
    """Accumulates counts for one bucket (global, a format, or a chamber)."""
    def __init__(self) -> None:
        self.docs = 0
        self.pii_total = self.pii_removed = 0
        self.kept_total = self.kept_present = 0
        self.field_total: Dict[str, int] = defaultdict(int)
        self.field_ok: Dict[str, int] = defaultdict(int)
        self.cat_total = self.cat_ok = 0
        self.link_tp = self.link_fp = self.link_fn = 0
        self.quarantined = 0

    def rate(self, ok: int, total: int) -> float:
        return (ok / total * 100.0) if total else 100.0


def _score_doc(t: Tally, rec: dict, truth: dict, text: str) -> None:
    t.docs += 1
    if rec.get("quarantined"):
        t.quarantined += 1

    # PII recall: each true PII value must be absent from the delivered text.
    for pii in truth.get("pii", []):
        t.pii_total += 1
        if leak_scan(text, [pii]).passed:      # absent == removed
            t.pii_removed += 1

    # Precision proxy: annotated kept terms must survive (not over-removed).
    ntext = _norm(text)
    for term in truth.get("kept_terms", []):
        t.kept_total += 1
        if _norm(term) in ntext:
            t.kept_present += 1

    # Extracted fields.
    rec_fields = rec.get("fields", {})
    for label, gold in (truth.get("fields") or {}).items():
        t.field_total[label] += 1
        got = (rec_fields.get(label) or {}).get("value", "")
        if _norm(got) == _norm(gold) and _norm(gold):
            t.field_ok[label] += 1

    # Category.
    if truth.get("chamber"):
        t.cat_total += 1
        got_cat = rec.get("category", {})
        got_cat = got_cat.get("value", "") if isinstance(got_cat, dict) else got_cat
        if _norm(got_cat) == _norm(truth["chamber"]):
            t.cat_ok += 1

    # Relation (links).
    predicted = {l["to"] for l in rec.get("links", [])}
    gold_links = set(truth.get("links", []))
    t.link_tp += len(predicted & gold_links)
    t.link_fp += len(predicted - gold_links)
    t.link_fn += len(gold_links - predicted)


def evaluate(truth: dict, output_dir: Path) -> dict:
    records = {r["doc_id"]: r for r in
               json.loads((output_dir / "records.json").read_text(encoding="utf-8"))}
    overall = Tally()
    by_format: Dict[str, Tally] = defaultdict(Tally)
    by_chamber: Dict[str, Tally] = defaultdict(Tally)
    missing: List[str] = []

    for doc_id, gold in truth.items():
        rec = records.get(doc_id)
        if not rec:
            missing.append(doc_id)
            continue
        text = _delivered_text(output_dir, rec)
        fmt = gold.get("format") or rec.get("format") or "?"
        chamber = gold.get("chamber") or "غير محدد"
        for bucket in (overall, by_format[fmt], by_chamber[chamber]):
            _score_doc(bucket, rec, gold, text)

    return {"overall": overall, "by_format": dict(by_format),
            "by_chamber": dict(by_chamber), "missing": missing,
            "evaluated": len(truth) - len(missing)}


def _metrics(t: Tally) -> dict:
    link_p = t.link_tp / (t.link_tp + t.link_fp) * 100 if (t.link_tp + t.link_fp) else 100.0
    link_r = t.link_tp / (t.link_tp + t.link_fn) * 100 if (t.link_tp + t.link_fn) else 100.0
    fields = {lbl: round(t.rate(t.field_ok[lbl], t.field_total[lbl]), 1) for lbl in t.field_total}
    return {
        "docs": t.docs,
        "pii_recall": round(t.rate(t.pii_removed, t.pii_total), 2),
        "pii_precision_proxy": round(t.rate(t.kept_present, t.kept_total), 2),
        "fields": fields,
        "category": round(t.rate(t.cat_ok, t.cat_total), 2),
        "relation_precision": round(link_p, 2),
        "relation_recall": round(link_r, 2),
        "quarantine_rate": round(t.rate(t.quarantined, t.docs), 2),
    }


def render_md(result: dict) -> str:
    def row(name: str, t: Tally) -> str:
        m = _metrics(t)
        fields = " · ".join(f"{k.split()[-1]} {v}%" for k, v in m["fields"].items()) or "—"
        return (f"| {name} | {m['docs']} | {m['pii_recall']}% | {m['pii_precision_proxy']}% | "
                f"{fields} | {m['category']}% | {m['relation_precision']}% / {m['relation_recall']}% | "
                f"{m['quarantine_rate']}% |")

    lines = [
        "# Evaluation report",
        "",
        f"Evaluated **{result['evaluated']}** documents against ground truth."
        + (f"  ⚠️ Missing from output: {', '.join(result['missing'])}" if result["missing"] else ""),
        "",
        "| Bucket | Docs | PII recall | PII precision* | Fields | Category | Relation P/R | Quarantine |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
        row("**Overall**", result["overall"]),
    ]
    for fmt, t in sorted(result["by_format"].items()):
        lines.append(row(f"format · {fmt}", t))
    for ch, t in sorted(result["by_chamber"].items()):
        lines.append(row(f"chamber · {ch}", t))
    lines += [
        "",
        "\\* PII precision here is the *proxy* from annotated kept-terms (share of terms that",
        "must survive and did). Targets (§4): recall ≥ 99.5%, precision ≥ 95%, fields ≥ 99%,",
        "category ≥ 98%, relation ≥ 98% / ≥ 90%, quarantine < 2%.",
        "",
    ]
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Score a run against ground truth (§4 metrics).")
    p.add_argument("--truth", required=True, help="Ground-truth JSON file")
    p.add_argument("--output", default="output", help="Output dir with records.json + files")
    p.add_argument("--md", help="Write the markdown report here (also prints to stdout)")
    p.add_argument("--json", help="Write machine-readable metrics here")
    args = p.parse_args(argv)

    truth = json.loads(Path(args.truth).read_text(encoding="utf-8"))
    result = evaluate(truth, Path(args.output))
    md = render_md(result)
    print(md)
    if args.md:
        Path(args.md).write_text(md, encoding="utf-8")
    if args.json:
        payload = {"overall": _metrics(result["overall"]),
                   "by_format": {k: _metrics(v) for k, v in result["by_format"].items()},
                   "by_chamber": {k: _metrics(v) for k, v in result["by_chamber"].items()},
                   "missing": result["missing"]}
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
