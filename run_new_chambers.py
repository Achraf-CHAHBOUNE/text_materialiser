"""Process the five chambers that have never been run, then rebuild results/.

Extracts each archive, anonymizes it, and finally gathers every chamber -- old and
new -- into results/. Safe to stop and start again: finished rulings are skipped
and nothing is paid for twice.

    python run_new_chambers.py                                    # everything
    python run_new_chambers.py --only 03_commerciale --limit 200   # a trial

Progress goes to data/work/run-all.log
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UNRAR = Path(r"C:\Program Files\WinRAR\UnRAR.exe")
LOG = ROOT / "data" / "work" / "run-all.log"

# The chamber a folder holds -- assumed only when a ruling never names its own.
CHAMBERS = {
    "03_commerciale": "تجارية",
    "04_administrative": "إدارية",
    "05_sociale": "اجتماعية",
    "06_penale": "جنائية",
    "07_immobiliere": "عقارية",
}


def say(msg):
    line = f"{dt.datetime.now():%H:%M:%S}  {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(cmd, cwd):
    with open(LOG, "a", encoding="utf-8") as f:
        return subprocess.run(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT,
                              env={**os.environ, "PYTHONUTF8": "1"}).returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--budget", type=float, default=40.0)
    ap.add_argument("--skip-assemble", action="store_true")
    args = ap.parse_args()

    folders = [args.only] if args.only else list(CHAMBERS)
    say("=" * 60)
    say(f"starting: {', '.join(folders)}")

    for folder in folders:
        target = ROOT / "data" / "corpus" / folder
        if not target.exists():
            say(f"{folder}: extracting")
            rc = run([str(UNRAR), "x", "-y", "-idq",
                      str(ROOT / "lastinput" / f"{folder}.rar"),
                      str(ROOT / "data" / "corpus") + "\\"], ROOT)
            if rc != 0:
                say(f"{folder}: EXTRACTION FAILED (code {rc}) -- skipped")
                continue
        say(f"{folder}: {len(list(target.rglob('*.pdf'))):,} PDFs ready")

        cmd = [sys.executable, "-m", "anonymizer",
               "--input", f"../data/corpus/{folder}",
               "--output", f"../data/work/{folder}",
               "--corpus", folder,
               "--category", CHAMBERS[folder],
               "--workers", str(args.workers),
               "--budget", str(args.budget)]
        if args.limit:
            cmd += ["--limit", str(args.limit)]
        say(f"{folder}: anonymizing with {args.workers} workers")
        os.environ["STATE_FILE"] = f"../data/work/{folder}/.state.json"
        os.environ["DB_PATH"] = "../data/work/cases.db"
        say(f"{folder}: finished (code {run(cmd, ROOT / 'pipeline')})")

    if not args.skip_assemble:
        say("rebuilding results/ with every chamber")
        run([sys.executable, "-m", "anonymizer.assemble",
             "--work", "../data/work", "--out", "../results"], ROOT / "pipeline")
    say("ALL DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
