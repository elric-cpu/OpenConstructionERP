#!/usr/bin/env python3
"""Reject Benson frontend artifacts containing non-English locale chunks."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend" / "dist"
NON_ENGLISH = {
    "ar", "bg", "cs", "da", "de", "es", "es-MX", "fi", "fr", "hi", "hr", "id",
    "it", "ja", "ko", "ky", "mn", "nl", "no", "pl", "pt", "ro", "ru", "sv", "th",
    "tr", "vi", "zh",
}


def main() -> int:
    if not DIST.is_dir():
        print("frontend/dist does not exist", file=sys.stderr)
        return 1
    violations = []
    locale_pattern = re.compile(r"(?:i18n|locale)[-_]([A-Za-z-]+)", re.IGNORECASE)
    for path in DIST.rglob("*"):
        if not path.is_file():
            continue
        match = locale_pattern.search(path.name)
        if match and match.group(1).split("-")[0] in NON_ENGLISH:
            violations.append(path.relative_to(DIST).as_posix())
    text_extensions = {".js", ".mjs", ".json", ".html"}
    for path in DIST.rglob("*"):
        if path.is_file() and path.suffix in text_extensions:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for locale in NON_ENGLISH:
                if f"locales/{locale}" in text or f"locales\\/{locale}" in text:
                    violations.append(f"{path.relative_to(DIST)} references {locale}")
                    break
    if violations:
        print("Non-English Benson artifact content found:", file=sys.stderr)
        print("\n".join(sorted(set(violations))), file=sys.stderr)
        return 1
    print("Benson artifact contains no non-English locale chunks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
