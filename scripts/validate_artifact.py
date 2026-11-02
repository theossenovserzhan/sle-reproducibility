#!/usr/bin/env python3
"""Validate the public SLE reproducibility package before release."""

from __future__ import annotations

import json
import os
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
    "paper/manuscript.pdf",
    "paper/supplement.pdf",
    "paper/main.tex",
    "paper/supplement.tex",
    "experiments/revision_v3/results/current_results.json",
    "publication/manifest.json",
]

FORBIDDEN_SUFFIXES = {".npz", ".npy", ".pt", ".pth", ".pem", ".key", ".onnx", ".pkl", ".ckpt"}
SECRET_PATTERNS = {
    "generic API key": re.compile(
        r"(?i)(api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*['\"][^'\"]{8,}"
    ),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"(?:gh[pousr]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{40,})"),
}


def contains_kaggle_credentials(value):
    if isinstance(value, dict):
        if isinstance(value.get('username'), str) and isinstance(value.get('key'), str):
            return bool(value['username'] and value['key'])
        return any(contains_kaggle_credentials(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_kaggle_credentials(item) for item in value)
    return False


def main() -> int:
    errors: list[str] = []

    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            errors.append(f"missing required file: {relative}")

    manifest_path = ROOT / 'publication/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.is_file() else {}
    allowed_outcomes = manifest.get('classification_outcome_arrays', {})
    files = []
    for directory, folders, names in os.walk(ROOT):
        folders[:] = [name for name in folders if name != '.git']
        files.extend(Path(directory) / name for name in names)
    for path in files:
        relative = path.relative_to(ROOT)
        if "__pycache__" in relative.parts or path.suffix.lower() == ".pyc":
            errors.append(f"generated Python cache file: {relative}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES and relative.as_posix() not in allowed_outcomes:
            errors.append(f"forbidden binary or credential file: {relative}")
        if relative.as_posix() in allowed_outcomes:
            try:
                from verify_msle_snapshot import check_outcomes
                check_outcomes(path, allowed_outcomes[relative.as_posix()])
            except (AssertionError, ValueError, ImportError) as exc:
                errors.append(f"invalid allowlisted classification outcomes: {relative}: {exc}")

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

        if path.suffix.lower() == '.json':
            try:
                payload = json.loads(path.read_text(encoding='utf-8'))
                if path.name.lower() == 'kaggle.json' or contains_kaggle_credentials(payload):
                    errors.append(f"possible Kaggle credential in {relative}")
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass

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
