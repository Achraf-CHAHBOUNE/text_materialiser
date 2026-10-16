"""Take a delivery of anonymized rulings and make it searchable. One command.

This replaces four passes that each re-read the same files: import the folder, read
the headnotes, ask a model for the ones with none, fold the proposals back in. Now a
ruling is opened once, in a worker process, and everything that can be read off it is
read at once; only the rulings that print nothing go to a model afterwards.

    python ingest.py ../../results
    python ingest.py ../../results --no-model          # free, deterministic only
    python ingest.py ../../results --provider openrouter --model x-ai/grok-4.3
    python ingest.py ../../results --dry-run

What each ruling ends up with
-----------------------------
    from the file itself     the text, the Word document, and the PII gate's verdict
    from the pipeline        chamber, numbers, date, city, year
    from the page            subject, keyword chain, the court's own rule, outcome
    from a model (optional)  a subject and a summary, but only where the court
                             printed none, written to their own columns and labelled

The court's words are never overwritten. `rule` only ever holds what the court wrote;
anything a model writes goes to `abstract`, and `theme_source` says which is which.

Rules this keeps
----------------
  - a ruling the pipeline held back is not imported;
  - every file is re-scanned for PII before it is stored, whatever the pipeline said;
  - a ruling edited by hand on the site is left exactly as edited;
  - a subject a model invents is not adopted: it is written to a proposals file for a
    person to approve, and that ruling keeps its summary but no subject.

Safe to interrupt. Work is committed in batches and already-done rulings are skipped,
so running it again costs only what was left.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    _backend = Path(__file__).resolve().parents[1] / "backend"
except NameError:
    _backend = Path.cwd()
if not (_backend / "db.py").exists():
    _backend = Path.cwd()
sys.path.insert(0, str(_backend))
sys.stdout.reconfigure(encoding="utf-8")

import db            # noqa: E402
import importer      # noqa: E402  -- step 1 is the platform's one import, shared with the upload page


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest a pipeline results folder")
    ap.add_argument("results", help="the results folder, or a .zip of it")
    ap.add_argument("--no-publish", action="store_true", help="import for review instead")
    ap.add_argument("--no-model", action="store_true",
                    help="skip the model pass: nothing leaves this machine")
    ap.add_argument("--provider", default=os.getenv("LLM_PROVIDER", "gemini"),
                    choices=["gemini", "openrouter", "opencode"])
    ap.add_argument("--model", default="", help="override the provider's default model")
    ap.add_argument("--actor", default="ingest", help="who to record in the audit log")
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--batch", type=int, default=400)
    ap.add_argument("--dry-run", action="store_true", help="read and count, write nothing")
    args = ap.parse_args()

    results = Path(args.results)
    try:
        importer.open_source(results)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2

    db.init_db()
    print("step 1/2  reading the rulings")
    counts = importer.run(results, publish=not args.no_publish, actor=args.actor,
                          workers=args.workers, batch=args.batch, dry_run=args.dry_run)
    print(json.dumps({k: v for k, v in counts.items() if not isinstance(v, list)}, ensure_ascii=False, indent=2))

    if args.no_model or args.dry_run:
        print("\nstep 2/2  skipped (--no-model)" if args.no_model else "\nstep 2/2  skipped (dry run)")
    else:
        print("\nstep 2/2  asking a model for the rulings that printed nothing")
        import classify_rulings
        sys.argv = ["classify_rulings", "--provider", args.provider]
        if args.model:
            sys.argv += ["--model", args.model]
        classify_rulings.main()

    print("\n" + json.dumps(db.counts(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
