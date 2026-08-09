#!/usr/bin/env python3
"""Generate reproducible inputs for journal-scale SLE experiments.

Unlike the original smoke-test generator, biometric-root width and locator
width are independent parameters. Locators are Python integers, so a 64-bit
storage width is exercised without NumPy signed-integer truncation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


SEED = 20260804


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=("transition", "integrated"), required=True
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--n-records", type=int, required=True)
    parser.add_argument("--root-bits", type=int, required=True)
    parser.add_argument("--block-bits", type=int, default=4)
    parser.add_argument("--bucket-capacity", type=int, required=True)
    parser.add_argument("--locator-bits", type=int, default=32)
    parser.add_argument("--query-row", type=int, default=0)
    parser.add_argument("--npz", type=Path)
    parser.add_argument("--flip-probability", type=float, default=0.05)
    return parser.parse_args()


def flatten(*arrays) -> list[int]:
    output: list[int] = []
    for array in arrays:
        if isinstance(array, np.ndarray):
            output.extend(int(value) for value in array.reshape(-1))
        elif isinstance(array, (list, tuple)):
            output.extend(int(value) for value in array)
        else:
            output.append(int(array))
    return output


def load_roots(args: argparse.Namespace):
    rng = np.random.default_rng(SEED)

    if args.npz is None:
        gallery = rng.integers(
            0, 2, size=(args.n_records, args.root_bits), dtype=np.uint8
        )
        labels = np.arange(1000, 1000 + args.n_records, dtype=np.int64)
        probes = gallery.copy()
        flips = rng.random(probes.shape) < args.flip_probability
        probes ^= flips.astype(np.uint8)
    else:
        archive = np.load(args.npz)
        gallery = np.asarray(archive["gallery_roots"], dtype=np.uint8)
        probes = np.asarray(archive["probe_roots"], dtype=np.uint8)
        labels = np.asarray(
            archive.get("labels", archive.get("gallery_labels")),
            dtype=np.int64,
        )
        if gallery.ndim != 2 or probes.ndim != 2:
            raise ValueError("gallery_roots and probe_roots must be matrices")
        if len(gallery) < args.n_records:
            raise ValueError("NPZ has fewer enrolled identities than requested")
        if gallery.shape[1] < args.root_bits or probes.shape[1] < args.root_bits:
            raise ValueError("NPZ roots are narrower than --root-bits")
        gallery = gallery[: args.n_records, : args.root_bits]
        labels = labels[: args.n_records]
        probes = probes[:, : args.root_bits]

    if not np.isin(gallery, (0, 1)).all():
        raise ValueError("gallery roots must be binary")
    if not np.isin(probes, (0, 1)).all():
        raise ValueError("probe roots must be binary")
    if not 0 <= args.query_row < len(probes):
        raise ValueError("query row is outside probe_roots")

    tie_tags = rng.permutation(
        np.arange(1, args.n_records + 1, dtype=np.int64)
    )
    probe = probes[args.query_row]
    distances = np.count_nonzero(gallery != probe[None, :], axis=1)
    best = np.flatnonzero(distances == distances.min())
    winner = best[np.argmin(tie_tags[best])]

    return gallery, labels, tie_tags, probe, int(labels[winner]), int(distances[winner])


def block_value(root: np.ndarray, block: int, block_bits: int) -> int:
    start = block * block_bits
    value = 0
    for bit, item in enumerate(root[start : start + block_bits]):
        value |= int(item) << bit
    return value


def build_bucket_rows(gallery: np.ndarray, block_bits: int, capacity: int):
    n_records, root_bits = gallery.shape
    if root_bits % block_bits:
        raise ValueError("root_bits must be divisible by block_bits")

    n_blocks = root_bits // block_bits
    bucket_values = 2**block_bits
    n_buckets = n_blocks * bucket_values
    rows = np.full((n_buckets, capacity), n_records, dtype=np.int64)
    valid = np.zeros((n_buckets, capacity), dtype=np.uint8)
    occupancy = np.zeros(n_buckets, dtype=np.int64)

    for row in range(n_records):
        for block in range(n_blocks):
            value = block_value(gallery[row], block, block_bits)
            address = block * bucket_values + value
            slot = int(occupancy[address])
            if slot >= capacity:
                raise ValueError(
                    f"bucket {address} needs {slot + 1} slots; "
                    "increase --bucket-capacity"
                )
            rows[address, slot] = row
            valid[address, slot] = 1
            occupancy[address] += 1

    return rows, valid, int(occupancy.max())


def random_unique_values(count: int, bits: int, rng: np.random.Generator):
    if not 16 <= bits <= 64:
        raise ValueError("locator bits must be in [16, 64]")
    mask = (1 << bits) - 1
    values: set[int] = set()
    while len(values) < count:
        value = int(rng.bit_generator.random_raw()) & mask
        if value:
            values.add(value)
    return sorted(values)


def build_locators(rows, valid, n_records, locator_bits):
    rng = np.random.default_rng(SEED + locator_bits + n_records)
    db_locators = random_unique_values(n_records, locator_bits, rng)
    forbidden = set(db_locators)

    index_locators = np.empty(rows.shape, dtype=object)
    for address in range(rows.shape[0]):
        for slot in range(rows.shape[1]):
            if valid[address, slot]:
                index_locators[address, slot] = db_locators[int(rows[address, slot])]
            else:
                while True:
                    candidate = random_unique_values(1, locator_bits, rng)[0]
                    if candidate not in forbidden:
                        forbidden.add(candidate)
                        index_locators[address, slot] = candidate
                        break

    contributions = [
        int(value)
        for value in rng.integers(1, 2**30, size=5, dtype=np.int64)
    ]
    return db_locators, index_locators, contributions


def write_inputs(output_dir: Path, values_by_player: dict[int, list[int]]):
    output_dir.mkdir(parents=True, exist_ok=True)
    for player in range(5):
        path = output_dir / f"Input-P{player}-0"
        values = values_by_player.get(player, [])
        path.write_text(" ".join(str(int(value)) for value in values) + "\n")


def sha256_array(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def main() -> None:
    args = parse_args()
    if args.n_records < 2:
        raise ValueError("n-records must be at least two")
    if args.root_bits % args.block_bits:
        raise ValueError("root-bits must be divisible by block-bits")

    gallery, labels, tie_tags, probe, expected_identity, expected_distance = load_roots(args)
    rows, valid, required_capacity = build_bucket_rows(
        gallery, args.block_bits, args.bucket_capacity
    )
    db_locators, index_locators, contributions = build_locators(
        rows, valid, args.n_records, args.locator_bits
    )

    player_values = {
        0: flatten(
            db_locators,
            gallery,
            index_locators,
            valid,
        )
    }

    if args.mode == "integrated":
        player_values[0].extend(flatten(labels, tie_tags, contributions[0]))
        player_values[1] = flatten(contributions[1], probe)
    else:
        # Trailing row references are consumed by the ORAM-reindex baseline
        # and ignored by the SLE, pointer-join, and sort/merge programs.
        player_values[0].extend(flatten(contributions[0], rows))
        player_values[1] = [contributions[1]]

    for player in range(2, 5):
        player_values[player] = [contributions[player]]

    write_inputs(args.output_dir, player_values)

    metadata = {
        "mode": args.mode,
        "n_records": args.n_records,
        "root_bits": args.root_bits,
        "block_bits": args.block_bits,
        "bucket_capacity": args.bucket_capacity,
        "required_capacity": required_capacity,
        "locator_bits": args.locator_bits,
        "query_row": args.query_row,
        "expected_identity": expected_identity,
        "expected_distance": expected_distance,
        "gallery_sha256": sha256_array(gallery),
        "probe_sha256": sha256_array(probe),
        "index_slots": int(rows.size),
        "semantic_index_entries": int(valid.sum()),
    }
    metadata_path = args.output_dir / "sle_journal_input_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
