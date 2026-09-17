"""Build a small demo pack from the results folder, to show the platform to someone.

The full delivery is 667 MB and 15,923 rulings; nobody needs that to look at the site.
This picks a spread -- every chamber, a range of years and cities, rulings that actually
carry a number and a date -- and copies just those into a folder small enough to send.

    cd platform
    python scripts/make_demo.py                    # -> demo-pack/ (60 rulings)
    python scripts/make_demo.py --count 30 --zip   # -> demo-pack.zip

Then, on any machine with Docker:

    docker compose -f docker-compose.demo.yml up --build

Everything in the pack is anonymized and passed the pipeline's leak check, the same as
what the client receives. Held-back rulings are never in the results folder to begin with.
"""
from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from collections import defaultdict
from pathlib import Path

F_DECISION, F_DATE = "رقم القرار", "تاريخ القرار"


def _field(rec: dict, label: str) -> str:
    return ((rec.get("fields") or {}).get(label) or {}).get("value", "") or ""


def _chamber(rec: dict) -> str:
    cat = rec.get("category")
    return (cat.get("value", "") if isinstance(cat, dict) else cat) or "غير محدد"


def pick(records: list, count: int) -> list:
    """A spread, not the first N: every chamber present, years and cities varied."""
    by_chamber: dict = defaultdict(list)
    for rec in records:
        if _field(rec, F_DECISION) and _field(rec, F_DATE) and rec.get("city"):
            by_chamber[_chamber(rec)].append(rec)
    for chamber, rows in by_chamber.items():
        # Vary the year and city within each chamber before taking from the front.
        rows.sort(key=lambda r: (_field(r, F_DATE)[-4:], r.get("city", ""), r["doc_id"]))
        seen_year, spread = set(), []
        for row in rows:                       # one per year first, then fill in
            year = _field(row, F_DATE)[-4:]
            if year not in seen_year:
                seen_year.add(year)
                spread.append(row)
        by_chamber[chamber] = spread + [r for r in rows if r not in spread]

    chosen, chambers = [], sorted(by_chamber, key=lambda c: -len(by_chamber[c]))
    for i in range(count):                     # round-robin: small chambers get in too
        chamber = chambers[i % len(chambers)]
        pool = by_chamber[chamber]
        if pool:
            chosen.append(pool.pop(0))
        if len(chosen) >= count:
            break
    return chosen


def build(results: Path, out: Path, count: int) -> dict:
    records = json.loads((results / "records.json").read_text(encoding="utf-8"))
    chosen = pick(records, count)
    if out.exists():
        shutil.rmtree(out)
    (out / "documents").mkdir(parents=True)

    kept, total_bytes = [], 0
    for rec in chosen:
        src = results / rec["file_path"]
        if not src.exists():
            continue
        dst = out / rec["file_path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        total_bytes += dst.stat().st_size
        # Keep only what the platform imports; drop the pipeline's internal bookkeeping.
        kept.append({k: v for k, v in rec.items()
                     if k not in ("audit", "cost", "leak_test", "corpus")})
    (out / "records.json").write_text(json.dumps(kept, ensure_ascii=False, indent=1),
                                      encoding="utf-8")

    chambers = sorted({_chamber(r) for r in kept})
    years = sorted({_field(r, F_DATE)[-4:] for r in kept if _field(r, F_DATE)})
    (out / "README.txt").write_text(
        "Demo pack for the anonymized rulings platform\n"
        "=============================================\n\n"
        f"{len(kept)} rulings, {len(chambers)} chambers, {years[0]}-{years[-1]}.\n"
        "Every one is anonymized: names are replaced with XXXXXXX.\n\n"
        "To look at the site, from the platform/ folder of the repository:\n\n"
        "    docker compose -f docker-compose.demo.yml up --build\n\n"
        "then open http://127.0.0.1:8080 and sign in:\n\n"
        "    admin@demo.local / demo-admin      an administrator: can correct rulings\n"
        "    client@demo.local / demo-client    a reader: can browse, search, report\n\n"
        "These accounts exist only in the demo. Stop it with Ctrl+C;\n"
        "'docker compose -f docker-compose.demo.yml down -v' removes everything.\n",
        encoding="utf-8")

    return {"rulings": len(kept), "chambers": chambers, "years": (years[0], years[-1]),
            "megabytes": round(total_bytes / 1e6, 1)}


def main() -> int:
    here = Path(__file__).resolve().parent.parent          # platform/
    ap = argparse.ArgumentParser(description="Build a small demo pack from results/")
    ap.add_argument("--results", default=str(here.parent / "results"))
    ap.add_argument("--out", default=str(here / "demo-pack"))
    ap.add_argument("--count", type=int, default=60)
    ap.add_argument("--zip", action="store_true", help="also write <out>.zip to send")
    args = ap.parse_args()

    results = Path(args.results)
    if not (results / "records.json").exists():
        print(f"No records.json in {results} -- build it with anonymizer.assemble first")
        return 2
    out = Path(args.out)
    counts = build(results, out, args.count)
    print(f"{counts['rulings']} rulings, {counts['megabytes']} MB -> {out}")
    print(f"  chambers: {', '.join(counts['chambers'])}")
    print(f"  years:    {counts['years'][0]}-{counts['years'][1]}")
    if args.zip:
        archive = out.with_suffix(".zip")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            for path in sorted(out.rglob("*")):
                if path.is_file():
                    z.write(path, path.relative_to(out.parent).as_posix())
        print(f"  zipped:   {archive} ({archive.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
