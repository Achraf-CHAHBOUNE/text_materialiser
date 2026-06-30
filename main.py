"""Thin entry-point shim. Real CLI lives in anonymizer/cli.py.

    python main.py [options]      # equivalent to: python -m anonymizer [options]
"""
import sys

from anonymizer.cli import main

if __name__ == "__main__":
    sys.exit(main())
