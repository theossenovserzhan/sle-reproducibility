#!/usr/bin/env python3
"""Build deterministic SHA-256 checksums for the curated release files."""

from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "SHA256SUMS.txt"
IGNORED_PARTS = {".git", "__pycache__", ".ipynb_checkpoints"}


def main() -> None:
    rows: list[str] = []
    for path in sorted(item for item in ROOT.rglob("*") if item.is_file()):
        relative = path.relative_to(ROOT)
        if path == OUTPUT or any(part in IGNORED_PARTS for part in relative.parts):
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        rows.append(f"{digest}  {relative.as_posix()}")
    OUTPUT.write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} checksums to {OUTPUT.name}")


if __name__ == "__main__":
    main()

