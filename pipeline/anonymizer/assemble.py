"""Gather every delivered ruling, from every processed folder, into one place.

The pipeline works one input folder at a time, and each working folder also holds
what the client must never receive: files held back by the leak gate, duplicate
copies, internal state. `results/` is the single hand-off -- rebuilt from the
working folders on demand, so it is always complete and never stale:

    results/
      README.md       what is inside, with counts per chamber and year
      listing.csv     one row per ruling: court, chamber, year, number, date, city
      records.json    the full record per ruling (what the platform imports)
      records.xlsx    the same, as a spreadsheet
      documents/<chamber>/<ruling>.docx

Only delivered rulings are included. Documents are hard-linked where the disk
allows it (no second copy of the data), copied otherwise.

    python -m anonymizer.assemble --work ../data/work --out ../results
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import json
import os
import shutil
from collections import Counter
from pathlib import Path
from typing import List

from .documents import records as records_mod
from .documents.records import F_DATE, F_DECISION

# Folder names are Latin: Arabic names are mangled by some unzip tools.
CHAMBER_FOLDERS = {
    "أحوال شخصية": "personal_status", "مدنية": "civil", "جنائية": "criminal",
    "اجتماعية": "social", "تجارية": "commercial", "عقارية": "real_estate",
    "إدارية": "administrative",
}
COURT_BY_LEVEL = {"نقض": "محكمة النقض", "استئناف": "محكمة الاستئناف",
                  "ابتدائي": "المحكمة الابتدائية"}


def _link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _field(rec: dict, label: str) -> str:
    return ((rec.get("fields") or {}).get(label) or {}).get("value", "") or ""


def assemble(work: Path, out: Path) -> dict:
    """Rebuild `out` from every working folder under `work`. Returns counts."""
    folders = sorted(p for p in work.iterdir() if (p / "records.json").exists())
    if not folders:
        raise SystemExit(f"No processed folders (with records.json) under {work}")

    docs_dir = out / "documents"
    if docs_dir.exists():
        shutil.rmtree(docs_dir)          # generated: always rebuilt whole
    out.mkdir(parents=True, exist_ok=True)

    records: List[dict] = []
    seen: dict = {}
    for folder in folders:
        for rec in json.loads((folder / "records.json").read_text(encoding="utf-8")):
            if rec.get("quarantined") or rec.get("status") != "done":
                continue                 # held back: never part of the hand-off
            src = folder / rec["anonymized_file"]
            if not src.exists():
                raise SystemExit(f"{folder.name}: record {rec['doc_id']} has no file {src.name}")
            name = rec["anonymized_file"]
            if name in seen:
                raise SystemExit(f"{name} is delivered by both {seen[name]} and {folder.name}")
            seen[name] = folder.name
            chamber = (rec.get("category") or {}).get("value", "")
            rel = Path("documents") / CHAMBER_FOLDERS.get(chamber, "undetermined") / name
            _link_or_copy(src, out / rel)
            rec = dict(rec, corpus=folder.name, file_path=rel.as_posix())
            records.append(rec)

    def order(r):
        date = _field(r, F_DATE)
        num = _field(r, F_DECISION)
        return ((r.get("category") or {}).get("value", ""), date[-4:], date[3:5], date[:2],
                int(num) if num.isdigit() else 0, r["doc_id"])

    records.sort(key=order)
    records_mod.write_json(records, out / "records.json")
    records_mod.write_xlsx(records, out / "records.xlsx")

    with open(out / "listing.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["المحكمة", "الغرفة", "السنة", "رقم القرار", "تاريخ القرار", "المدينة", "الملف"])
        for r in records:
            date = _field(r, F_DATE)
            w.writerow([COURT_BY_LEVEL.get(r.get("level", ""), r.get("level", "")),
                        (r.get("category") or {}).get("value", ""), date[-4:],
                        _field(r, F_DECISION), date, r.get("city", ""), r["file_path"]])

    counts = _write_readme(records, folders, out)
    return counts


def _write_readme(records: List[dict], folders: List[Path], out: Path) -> dict:
    n = len(records)
    by_chamber = Counter((r.get("category") or {}).get("value", "") for r in records)
    by_corpus = Counter(r["corpus"] for r in records)
    years = sorted(y for y in (_field(r, F_DATE)[-4:] for r in records) if y)

    def pct(pred) -> str:
        k = sum(1 for r in records if pred(r))
        return f"{k:,} / {n:,} ({k / n * 100:.1f}%)" if n else "0"

    lines = [
        "# Anonymized rulings — results",
        "",
        f"Built {_dt.datetime.now():%Y-%m-%d %H:%M} from {len(folders)} processed folder(s). "
        "Rebuilt whole each time; do not edit by hand.",
        "",
        f"**{n:,} rulings**, every one anonymized and passed by the leak check. Files the "
        "check held back, and duplicate copies, are not included.",
        "",
        "| File | What it is |", "| --- | --- |",
        "| `listing.csv` | one row per ruling: court, chamber, year, number, date, city, file |",
        "| `records.json` | the full record per ruling — what the platform imports |",
        "| `records.xlsx` | the same records as a spreadsheet |",
        "| `documents/<chamber>/` | the anonymized rulings (.docx) |",
        "",
        "## By chamber", "", "| الغرفة | folder | rulings |", "| --- | --- | --- |",
    ]
    for chamber, k in by_chamber.most_common():
        lines.append(f"| {chamber} | `{CHAMBER_FOLDERS.get(chamber, 'undetermined')}` | {k:,} |")
    lines += ["", "## By source folder", "", "| folder | rulings |", "| --- | --- |"]
    lines += [f"| {c} | {k:,} |" for c, k in sorted(by_corpus.items())]
    lines += [
        "", "## Fields", "",
        f"Years covered: {years[0]}–{years[-1]}" if years else "",
        "", "| field | filled |", "| --- | --- |",
        f"| رقم القرار — decision number | {pct(lambda r: _field(r, F_DECISION))} |",
        f"| تاريخ القرار — date | {pct(lambda r: _field(r, F_DATE))} |",
        f"| الغرفة — chamber | {pct(lambda r: (r.get('category') or {}).get('value'))} |",
        f"| المدينة — city of the court the appeal came from | {pct(lambda r: r.get('city'))} |",
        "",
        "المدينة is the city of the lower court named in the ruling itself (the Court of "
        "Cassation sits only in Rabat). Where a ruling never names it, the cell is empty.",
    ]
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"rulings": n, "chambers": dict(by_chamber), "folders": dict(by_corpus)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Gather every delivered ruling into one results folder")
    ap.add_argument("--work", default="../data/work", help="Folder holding one working folder per input")
    ap.add_argument("--out", default="../results", help="The results folder to (re)build")
    args = ap.parse_args()
    counts = assemble(Path(args.work), Path(args.out))
    print(f"results: {counts['rulings']:,} rulings -> {args.out}")
    for c, k in sorted(counts["folders"].items()):
        print(f"  {c}: {k:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
