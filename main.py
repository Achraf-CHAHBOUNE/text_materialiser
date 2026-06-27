"""CLI entry point for the Arabic PDF anonymization pipeline.

Examples:
    python main.py                      # process all PDFs in INPUT_DIR
    python main.py --limit 5            # first 5 only (good for a cost test)
    python main.py --overwrite          # ignore resume state, redo everything
    python main.py --input ach --output output --workers 8
"""
from __future__ import annotations

import argparse
import sys

from anonymizer.config import Settings
from anonymizer.logging_setup import setup_logging
from anonymizer.pipeline import Pipeline, RunOptions


def parse_args(settings: Settings) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Anonymize PII in scanned Arabic PDFs -> .docx")
    p.add_argument("--input", help="Input folder of PDFs (default from .env)")
    p.add_argument("--output", help="Output folder for .docx (default from .env)")
    p.add_argument("--provider", help="LLM provider (default from .env)")
    p.add_argument("--model", help="Model id (default from .env)")
    p.add_argument("--workers", type=int, help="Parallel documents (default from .env)")
    p.add_argument("--batch-size", type=int, help="Pages per LLM call (default from .env)")
    p.add_argument("--limit", type=int, default=None, help="Process at most N documents")
    p.add_argument("--overwrite", action="store_true", help="Reprocess even if already done")
    p.add_argument("--no-resume", action="store_true", help="Do not skip done documents")
    p.add_argument("--log-level", help="DEBUG/INFO/WARNING/ERROR (default from .env)")
    return p.parse_args()


def main() -> int:
    settings = Settings.load()
    args = parse_args(settings)

    # CLI overrides .env via a shallow merge.
    from dataclasses import replace
    overrides = {}
    if args.input:        overrides["input_dir"] = type(settings.input_dir)(args.input)
    if args.output:       overrides["output_dir"] = type(settings.output_dir)(args.output)
    if args.provider:     overrides["provider"] = args.provider.lower()
    if args.model:        overrides["model"] = args.model
    if args.workers:      overrides["max_workers"] = args.workers
    if args.batch_size:   overrides["pages_per_batch"] = args.batch_size
    if args.log_level:    overrides["log_level"] = args.log_level.upper()
    settings = replace(settings, **overrides)

    log = setup_logging(settings.log_level)
    log.info("Provider=%s Model=%s | input=%s output=%s | batch=%d workers=%d",
             settings.provider, settings.model, settings.input_dir, settings.output_dir,
             settings.pages_per_batch, settings.max_workers)

    try:
        pipeline = Pipeline(settings)
    except Exception as exc:
        log.error("Startup failed: %s", exc)
        return 2

    opts = RunOptions(
        limit=args.limit,
        overwrite=args.overwrite,
        resume=not args.no_resume,
    )

    totals = pipeline.run(opts)

    log.info("=" * 60)
    log.info("DONE. documents=%d pages=%d PII=%d",
             totals["documents"], totals["pages"], totals["pii"])
    log.info("tokens: in=%d out=%d | estimated cost=$%.4f",
             totals["input_tokens"], totals["output_tokens"], totals["cost"])
    if totals["failed"]:
        log.warning("%d document(s) failed — see logs above; rerun to retry.", totals["failed"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
