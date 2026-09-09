#!/usr/bin/env python3
"""Fail fast on unsafe or incomplete production configuration."""
from __future__ import annotations

import os
import sys
from collections.abc import Mapping

PLACEHOLDER_PREFIXES = (
    "brain-secure-",
    "change-me",
    "change_this",
    "replace-",
    "replace_with",
    "your_",
)


def _unsafe_secret(value: str, minimum: int = 32) -> bool:
    normalized = value.strip().lower()
    return len(value.strip()) < minimum or normalized.startswith(PLACEHOLDER_PREFIXES)


def collect_errors(service: str, env: Mapping[str, str] | None = None) -> list[str]:
    values = os.environ if env is None else env
    errors: list[str] = []
    api_key = values.get("BRAIN_API_KEY", "").strip()
    gemini_key = values.get("GEMINI_API_KEY", "").strip()
    telegram_token = values.get("TELEGRAM_BOT_TOKEN", "").strip()

    if _unsafe_secret(api_key):
        errors.append("BRAIN_API_KEY must be a random secret of at least 32 characters")
    if service in {"api", "telegram"} and not gemini_key:
        errors.append("GEMINI_API_KEY is required for live AI responses")
    if service == "telegram" and len(telegram_token) < 20:
        errors.append("TELEGRAM_BOT_TOKEN is required for the Telegram service")
    if api_key and api_key in {gemini_key, telegram_token}:
        errors.append("BRAIN_API_KEY must be different from provider and bot tokens")

    max_file_raw = values.get("MAX_FILE_SIZE_BYTES", str(20 * 1024 * 1024))
    try:
        max_file = int(max_file_raw)
        if not 1_048_576 <= max_file <= 2_147_483_648:
            errors.append("MAX_FILE_SIZE_BYTES must be between 1 MiB and 2 GiB")
    except ValueError:
        errors.append("MAX_FILE_SIZE_BYTES must be an integer")
    return errors


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    service = (args[0] if args else os.environ.get("BRAIN_SERVICE", "api")).strip().lower()
    if service not in {"api", "telegram"}:
        print(f"Unsupported BRAIN_SERVICE: {service}", file=sys.stderr)
        return 2
    errors = collect_errors(service)
    if errors:
        print("Configuration validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Configuration valid for {service} service.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
