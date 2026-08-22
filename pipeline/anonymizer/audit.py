"""Corpus audit (Script.md §5.1) — deterministic, no LLM, no paid calls.

Profiles the input folder BEFORE any run: format mix, scanned-vs-text, chamber guesses
(from header keywords), empty/damaged files, and duplicates. Writes audit_report.md/.json.
Run this first — its numbers gate the full run.

Usage:
    python -m anonymizer.audit --input input --out output/audit
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import List, Optional, Tuple

from .core.categories import COURTS, _TRIGGERS, _normalize
from .documents.convert import autodetect_soffice, convert_to_docx
from .documents.loaders import _docx_lines

IMG_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
SCAN_TEXT_THRESHOLD = 120  # a PDF with less extractable text than this is treated as scanned


def _guess_chamber(norm_text: str) -> str:
    for trig, canon in _TRIGGERS:
        if trig in norm_text:
            return canon
    return "غير محدد"


def _guess_court(text: str) -> str:
    for c in COURTS:
        if c in text:
            return c
    return ""


def _extract(path: Path, soffice: str) -> Tuple[Optional[str], str, str]:
    """Return (text|None, kind, format). text=None means unreadable/damaged."""
    ext = path.suffix.lower()
    try:
        if ext == ".docx":
            return "\n".join(_docx_lines(path)), "text", "docx"
        if ext == ".doc":
            if not soffice:
                return None, "error:no-soffice", "doc"
            with tempfile.TemporaryDirectory() as td:
                out = convert_to_docx(path, soffice, Path(td))
                return "\n".join(_docx_lines(out)), "text", "doc"
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            txt = "\n".join((pg.extract_text() or "") for pg in reader.pages)
            kind = "scanned" if len(txt.strip()) < SCAN_TEXT_THRESHOLD else "text"
            return txt, kind, "pdf"
        if ext in IMG_EXT:
            return "", "scanned", "image"
        return "", "unknown", ext.lstrip(".") or "none"
    except Exception as exc:  # a bad file must never crash the audit
        return None, "error:" + str(exc)[:60], ext.lstrip(".") or "none"


def audit(input_dir: Path, soffice: str) -> Tuple[dict, List[dict]]:
    files = sorted(p for p in input_dir.iterdir() if p.is_file() and not p.name.startswith("."))
    per: List[dict] = []
    fmt, kinds, chambers = Counter(), Counter(), Counter()
    hashes: dict[str, str] = {}
    empty = damaged = 0

    for p in files:
        text, kind, f = _extract(p, soffice)
        fmt[f] += 1
        kinds[kind] += 1
        if text is None:
            damaged += 1
            per.append({"file": p.name, "format": f, "status": kind})
            continue
        n = len(text.strip())
        if n == 0:
            empty += 1
        chamber = _guess_chamber(_normalize(text)) if text else "غير محدد"
        chambers[chamber] += 1
        h = hashlib.sha256(text.encode("utf-8")).hexdigest() if text.strip() else ""
        dup_of = hashes.get(h, "") if h else ""
        if h and not dup_of:
            hashes[h] = p.name
        per.append({"file": p.name, "format": f, "kind": kind, "chars": n,
                    "chamber": chamber, "court": _guess_court(text), "duplicate_of": dup_of})

    duplicates = sum(1 for r in per if r.get("duplicate_of"))
    summary = {
        "total_files": len(files),
        "by_format": dict(fmt),
        "by_kind": dict(kinds),
        "by_chamber": dict(chambers),
        "empty": empty,
        "damaged": damaged,
        "duplicates": duplicates,
        "scanned_ratio": round(kinds.get("scanned", 0) / len(files), 3) if files else 0.0,
    }
    return summary, per


def render_md(summary: dict, per: List[dict]) -> str:
    def table(counter: dict) -> str:
        return "\n".join(f"| {k or '—'} | {v} |" for k, v in sorted(counter.items(),
                                                                     key=lambda x: -x[1]))
    lines = [
        "# Corpus audit",
        "",
        f"- **Total files:** {summary['total_files']}",
        f"- **Scanned ratio:** {summary['scanned_ratio']*100:.1f}%  (drives OCR cost)",
        f"- **Empty:** {summary['empty']} · **Damaged/unreadable:** {summary['damaged']} · "
        f"**Duplicates:** {summary['duplicates']}",
        "",
        "## By format", "| format | n |", "| --- | --- |", table(summary["by_format"]), "",
        "## By kind", "| kind | n |", "| --- | --- |", table(summary["by_kind"]), "",
        "## By chamber (header-keyword guess — not the model)",
        "| chamber | n |", "| --- | --- |", table(summary["by_chamber"]), "",
    ]
    dups = [r for r in per if r.get("duplicate_of")]
    if dups:
        lines += ["## Duplicates", "| file | same as |", "| --- | --- |",
                  *[f"| {r['file']} | {r['duplicate_of']} |" for r in dups], ""]
    bad = [r for r in per if r.get("status", "").startswith("error")]
    if bad:
        lines += ["## Unreadable", "| file | reason |", "| --- | --- |",
                  *[f"| {r['file']} | {r['status']} |" for r in bad], ""]
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Deterministic corpus audit (no LLM).")
    p.add_argument("--input", default="input", help="Input folder to audit")
    p.add_argument("--out", default="output/audit", help="Output prefix (writes .md and .json)")
    args = p.parse_args(argv)

    soffice = autodetect_soffice()
    summary, per = audit(Path(args.input), soffice)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    md = render_md(summary, per)
    print(md)
    out.with_suffix(".md").write_text(md, encoding="utf-8")
    out.with_suffix(".json").write_text(
        json.dumps({"summary": summary, "documents": per}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
