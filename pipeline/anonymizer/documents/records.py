"""Structured output for the platform hand-off (Script.md §7).

Writes, into the output directory:
  records.json   — one JSON record per document (the schema in TECHNICAL_DESIGN §7)
  records.xlsx   — the same records flattened to a spreadsheet for the client
  run_report.md  — human-readable run report (cost per file, projected total, quarantine)
  run_report.json— machine-readable totals
  quarantine.csv — every rejected/failed file with a reason

Nothing here calls an LLM or touches raw input; it only serialises what the pipeline
already computed.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import List

from openpyxl import Workbook

# Field labels used in the JSON record and the XLSX header.
F_DECISION = "رقم القرار"
F_FILE = "رقم الملف"
F_DATE = "تاريخ القرار"


def write_json(records: List[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def _row(r: dict) -> dict:
    """Flatten one record for the spreadsheet."""
    f = r.get("fields", {})
    def val(k): return (f.get(k) or {}).get("value", "")
    def conf(k): return (f.get(k) or {}).get("confidence", "")
    links = "؛ ".join(f'{l["to"]}({l["role"]},{l["confidence"]})' for l in r.get("links", []))
    lk = r.get("leak_test", {})
    c = r.get("cost", {})
    return {
        "doc_id": r.get("doc_id", ""),
        "source_file": r.get("source_file", ""),
        "format": r.get("format", ""),
        "read_method": r.get("read_method", ""),
        "level": r.get("level", ""),
        "category": (r.get("category") or {}).get("value", "") if isinstance(r.get("category"), dict) else r.get("category", ""),
        "category_source": (r.get("category") or {}).get("source", "") if isinstance(r.get("category"), dict) else "",
        "case_id": r.get("case_id", ""),
        "review": r.get("review", ""),
        F_DECISION: val(F_DECISION),
        F_FILE: val(F_FILE),
        F_DATE: val(F_DATE),
        "decision_conf": conf(F_DECISION),
        "file_conf": conf(F_FILE),
        "date_conf": conf(F_DATE),
        "pii_removed": r.get("pii", {}).get("removed_count", 0),
        "leak_passed": lk.get("passed", ""),
        "leak_hits": lk.get("hits", 0),
        "links": links,
        "pages": r.get("pages", 0),
        "cost_usd": c.get("usd", 0),
        "input_tokens": c.get("input_tokens", 0),
        "output_tokens": c.get("output_tokens", 0),
        "status": r.get("status", ""),
    }


def write_xlsx(records: List[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "documents"
    if not records:
        ws.append(["(no documents)"])
        wb.save(path)
        return
    rows = [_row(r) for r in records]
    headers = list(rows[0].keys())
    ws.append(headers)
    for row in rows:
        ws.append([row.get(h, "") for h in headers])
    wb.save(path)


def write_quarantine_csv(quarantined: List[dict], path: Path) -> None:
    """quarantined: [{doc_id, source_file, reason, detail}]."""
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["doc_id", "source_file", "reason", "detail"])
        for q in quarantined:
            w.writerow([q.get("doc_id", ""), q.get("source_file", ""),
                        q.get("reason", ""), q.get("detail", "")])


def write_run_report(totals: dict, records: List[dict], quarantined: List[dict],
                     model: str, budget_usd: float,
                     path_md: Path, path_json: Path,
                     projected_n: int = 2000, halted: bool = False) -> None:
    processed = totals.get("documents", 0) or len(records)
    cost = float(totals.get("cost", 0.0) or 0.0)
    per_file = (cost / processed) if processed else 0.0
    projected = per_file * projected_n
    leaked = sum(1 for r in records if r.get("leak_test", {}).get("passed") is False)

    report = {
        "run_id": totals.get("run_id", ""),
        "timestamp": _dt.datetime.now().isoformat(timespec="seconds"),
        "model": model,
        "documents_processed": processed,
        "pages": totals.get("pages", 0),
        "pii_removed": totals.get("pii", 0),
        "failed": totals.get("failed", 0),
        "quarantined": len(quarantined),
        "leaked_blocked": leaked,
        "cost_usd_total": round(cost, 4),
        "cost_usd_per_file": round(per_file, 6),
        f"projected_usd_for_{projected_n}": round(projected, 2),
        "budget_usd": budget_usd,
        "budget_halted": halted,
    }
    path_json.parent.mkdir(parents=True, exist_ok=True)
    path_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Run report",
        "",
        f"- **Model:** {model}",
        f"- **Documents processed:** {processed}",
        f"- **Pages:** {report['pages']}",
        f"- **PII removed:** {report['pii_removed']}",
        f"- **Failed:** {report['failed']}",
        f"- **Quarantined (incl. leak-blocked):** {report['quarantined']}  (leak-blocked: {leaked})",
        "",
        "## Cost",
        f"- **Total:** ${report['cost_usd_total']:.4f}",
        f"- **Measured per file:** ${report['cost_usd_per_file']:.6f}",
        f"- **Projected for {projected_n:,}:** ${report[f'projected_usd_for_{projected_n}']:.2f}",
        f"- **Budget ceiling:** {'$%.2f' % budget_usd if budget_usd else 'none'}"
        + ("  ⛔ **HALTED — budget reached**" if halted else ""),
        "",
    ]
    if quarantined:
        lines += ["## Quarantine", "", "| doc | reason | detail |", "| --- | --- | --- |"]
        for q in quarantined:
            lines.append(f"| {q.get('doc_id','')} | {q.get('reason','')} | {q.get('detail','')} |")
        lines.append("")
    else:
        lines += ["## Quarantine", "", "None — every file passed.", ""]
    path_md.write_text("\n".join(lines), encoding="utf-8")
