#!/usr/bin/env python3
"""Validate the public SLE reproducibility package before release."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "README.md",
    "CITATION.cff",
    "DATA_AVAILABILITY.md",
    "requirements.txt",
    "docs/SLE_FORMAL_PROTOCOL.md",
    "notebooks/00_mpc_smoke_test.ipynb",
    "notebooks/01_journal_biometric_security_validation.ipynb",
    "notebooks/02_external_biometric_validation.ipynb",
    "notebooks/03_same_backend_and_sota_validation.ipynb",
    "notebooks/04_full_width_scaling_and_network_validation.ipynb",
    "Programs/Source/sle_transition_optimized.mpc",
    "Programs/Source/sle_oram_reindex_transition.mpc",
    "Programs/Source/sle_sort_merge_transition.mpc",
    "Programs/Source/sle_pointer_join_transition.mpc",
]

FORBIDDEN_SUFFIXES = {".npz", ".npy", ".pt", ".pth", ".pem", ".key"}
SECRET_PATTERNS = {
    "generic API key": re.compile(
        r"(?i)(api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*['\"][^'\"]{8,}"
    ),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "Kaggle credential": re.compile(r'"(?:username|key)"\s*:\s*"[^"\n]+"'),
}


def main() -> int:
    errors: list[str] = []

    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            errors.append(f"missing required file: {relative}")

    files = [path for path in ROOT.rglob("*") if path.is_file()]
    for path in files:
        relative = path.relative_to(ROOT)
        if "__pycache__" in relative.parts or path.suffix.lower() == ".pyc":
            errors.append(f"generated Python cache file: {relative}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            errors.append(f"forbidden binary or credential file: {relative}")

        if path.suffix == ".ipynb":
            try:
                notebook = json.loads(path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                errors.append(f"invalid notebook {relative}: {exc}")
                continue
            output_count = sum(
                len(cell.get("outputs", [])) for cell in notebook.get("cells", [])
            )
            if output_count:
                errors.append(f"notebook contains saved outputs: {relative}")

        if path.suffix.lower() in {".py", ".md", ".txt", ".json", ".ipynb", ".cff"}:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for label, pattern in SECRET_PATTERNS.items():
                if pattern.search(text):
                    errors.append(f"possible {label} in {relative}")

    if errors:
        print("Artifact validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"Artifact validation passed: {len(files)} files checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
