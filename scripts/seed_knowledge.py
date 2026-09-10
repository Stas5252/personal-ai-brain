#!/usr/bin/env python3
"""Compatibility entry point for the vetted built-in knowledge seed."""
from __future__ import annotations

import argparse

from seed_vetted_knowledge import VETTED_FILES, main as seed_vetted


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate or index the vetted Personal AI Brain corpus")
    parser.add_argument("--check", action="store_true", help="Print the production manifest without indexing")
    parser.add_argument("--reset", action="store_true", help="Deprecated; built-in sources are content-deduplicated")
    args = parser.parse_args()
    if args.check:
        print("Production knowledge manifest:")
        for name in VETTED_FILES:
            print(f"- {name}")
        return 0
    if args.reset:
        print("--reset no longer deletes user data; indexing the vetted manifest idempotently.")
    return seed_vetted()


if __name__ == "__main__":
    raise SystemExit(main())
