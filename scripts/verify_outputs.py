#!/usr/bin/env python3
"""Check the intentionally small public output of an MP-SPDZ SLE run."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


RESULT_RE = re.compile(
    r"SLE_MPC_RESULT mode=(?P<mode>\w+).*?"
    r"(?:accepted=(?P<accepted>[01]).*?identity=(?P<identity>-?\d+)|"
    r"relation_ok=(?P<relation_ok>[01]))"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--expect-relation", type=int, choices=(0, 1))
    args = parser.parse_args()

    text = args.log.read_text(encoding="utf-8", errors="replace")
    match = RESULT_RE.search(text)
    if match is None:
        raise SystemExit("No SLE_MPC_RESULT line found")

    result = match.groupdict()
    if result["mode"] in ("full_scan", "oram"):
        if args.metadata is None:
            raise SystemExit("--metadata is required for identification modes")
        metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
        expected = int(metadata["expected_identity"])
        observed = int(result["identity"])
        accepted = int(result["accepted"])
        if accepted != 1 or observed != expected:
            raise SystemExit(
                f"Identification failed: expected {expected}, observed {observed}, "
                f"accepted={accepted}"
            )
        print(f"PASS: {result['mode']} opened only the expected identity {expected}")
    else:
        expected = args.expect_relation
        observed = int(result["relation_ok"])
        if expected is None:
            raise SystemExit("--expect-relation is required for transition mode")
        if observed != expected:
            raise SystemExit(
                f"Transition check failed: expected {expected}, observed {observed}"
            )
        print(f"PASS: transition relation_ok={observed}")


if __name__ == "__main__":
    main()

