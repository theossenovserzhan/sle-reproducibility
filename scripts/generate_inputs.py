#!/usr/bin/env python3
"""Generate reproducible MP-SPDZ inputs for the SLE MPC programs.

The default path creates a small synthetic gallery/probe pair so the
cryptographic layer can be tested without downloading a face dataset. An NPZ
export from the biometric notebook can be supplied later; the MPC programs see
only binary roots, never face images or real-valued FaceNet embeddings.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np


SEED = 20260720


@dataclass
class ProtectedInputs:
    gallery: np.ndarray
    labels: np.ndarray
    tie_tags: np.ndarray
    probe: np.ndarray
    query_label: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("full_scan", "oram", "transition"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--n-records", type=int, default=16)
    parser.add_argument("--root-bits", type=int, default=64)
    parser.add_argument("--block-bits", type=int, default=4)
    parser.add_argument("--bucket-capacity", type=int, default=8)
    parser.add_argument("--query-row", type=int, default=0)
    parser.add_argument("--flip-probability", type=float, default=0.05)
    parser.add_argument("--npz", type=Path)
    return parser.parse_args()


def load_or_generate(args: argparse.Namespace) -> ProtectedInputs:
    rng = np.random.default_rng(SEED)

    if args.npz is not None:
        archive = np.load(args.npz)
        gallery = np.asarray(archive["gallery_roots"], dtype=np.int64)
        labels = np.asarray(
            archive.get("labels", np.arange(len(gallery))), dtype=np.int64
        )
        probes = np.asarray(archive["probe_roots"], dtype=np.int64)
        if gallery.ndim != 2 or probes.ndim != 2:
            raise ValueError("gallery_roots and probe_roots must be two-dimensional")
        if gallery.shape != probes.shape:
            raise ValueError("gallery_roots and probe_roots must have equal shape")
        if len(gallery) < args.n_records or gallery.shape[1] < args.root_bits:
            raise ValueError("NPZ does not contain enough records/root bits")
        gallery = gallery[: args.n_records, : args.root_bits]
        labels = labels[: args.n_records]
        probe = probes[args.query_row, : args.root_bits]
    else:
        gallery = rng.integers(
            0, 2, size=(args.n_records, args.root_bits), dtype=np.int64
        )
        labels = np.arange(1000, 1000 + args.n_records, dtype=np.int64)

        # Guarantee that the first flattened index slot is real. This is used
        # only by the explicit fault-injection smoke tests.
        gallery[0, : args.block_bits] = 0

        probe = gallery[args.query_row].copy()
        flips = rng.random(args.root_bits) < args.flip_probability
        probe[flips] ^= 1

    if not np.isin(gallery, (0, 1)).all() or not np.isin(probe, (0, 1)).all():
        raise ValueError("MPC roots must be binary")

    tie_tags = rng.permutation(np.arange(1, args.n_records + 1, dtype=np.int64))
    return ProtectedInputs(
        gallery=gallery,
        labels=labels,
        tie_tags=tie_tags,
        probe=probe,
        query_label=int(labels[args.query_row]),
    )


def block_value(root: np.ndarray, block: int, block_bits: int) -> int:
    start = block * block_bits
    value = 0
    for bit, item in enumerate(root[start : start + block_bits]):
        value |= int(item) << bit
    return value


def build_bucket_rows(
    gallery: np.ndarray,
    block_bits: int,
    capacity: int,
) -> tuple[np.ndarray, np.ndarray]:
    n_records, root_bits = gallery.shape
    if root_bits % block_bits:
        raise ValueError("root_bits must be divisible by block_bits")

    n_blocks = root_bits // block_bits
    bucket_values = 2**block_bits
    n_buckets = n_blocks * bucket_values
    dummy_row = n_records
    rows = np.full((n_buckets, capacity), dummy_row, dtype=np.int64)
    valid = np.zeros((n_buckets, capacity), dtype=np.int64)
    occupancy = np.zeros(n_buckets, dtype=np.int64)

    for row in range(n_records):
        for block in range(n_blocks):
            value = block_value(gallery[row], block, block_bits)
            address = block * bucket_values + value
            slot = int(occupancy[address])
            if slot >= capacity:
                raise ValueError(
                    f"bucket {address} requires more than {capacity} slots; "
                    "increase --bucket-capacity"
                )
            rows[address, slot] = row
            valid[address, slot] = 1
            occupancy[address] += 1

    return rows, valid


def flatten(*arrays: np.ndarray | list[int] | tuple[int, ...]) -> list[int]:
    output: list[int] = []
    for array in arrays:
        output.extend(np.asarray(array, dtype=np.int64).reshape(-1).tolist())
    return output


def write_inputs(output_dir: Path, values_by_player: dict[int, list[int]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for player in range(5):
        values = values_by_player.get(player, [])
        path = output_dir / f"Input-P{player}-0"
        path.write_text(" ".join(str(int(value)) for value in values) + "\n")


def full_scan_inputs(data: ProtectedInputs) -> dict[int, list[int]]:
    return {
        0: flatten(data.labels, data.tie_tags, data.gallery),
        1: flatten(data.probe),
    }


def oram_inputs(
    data: ProtectedInputs,
    block_bits: int,
    capacity: int,
) -> tuple[dict[int, list[int]], np.ndarray, np.ndarray]:
    rows, valid_slots = build_bucket_rows(data.gallery, block_bits, capacity)
    n_records, root_bits = data.gallery.shape

    labels = np.concatenate((data.labels, [-1]))
    valid_records = np.concatenate((np.ones(n_records, dtype=np.int64), [0]))
    tie_tags = np.concatenate((data.tie_tags, [2**31 - 1]))
    gallery = np.vstack((data.gallery, np.zeros(root_bits, dtype=np.int64)))

    return (
        {
            0: flatten(labels, valid_records, tie_tags, gallery, rows),
            1: flatten(data.probe),
        },
        rows,
        valid_slots,
    )


def transition_inputs(
    data: ProtectedInputs,
    block_bits: int,
    capacity: int,
) -> tuple[dict[int, list[int]], np.ndarray, np.ndarray]:
    rows, valid_slots = build_bucket_rows(data.gallery, block_bits, capacity)
    rng = np.random.default_rng(SEED + 1)
    # Generate only the required unique locators. Building
    # np.arange(1, 2**31) would allocate roughly 16 GiB before sampling and
    # can make a Colab runtime terminate with exit code 137.
    unique_locators: set[int] = set()
    while len(unique_locators) < len(data.gallery):
        unique_locators.add(int(rng.integers(1, 2**31)))
    old_db_locators = np.asarray(sorted(unique_locators), dtype=np.int64)
    dummy_locators = rng.integers(
        1, 2**31, size=rows.shape, dtype=np.int64
    )
    # The pointer-join baseline requires every dummy slot to match zero real
    # database locators. Make that invariant deterministic instead of relying
    # on the already tiny probability of a random 31-bit collision.
    collides = np.isin(dummy_locators, old_db_locators)
    while collides.any():
        dummy_locators[collides] = rng.integers(
            1, 2**31, size=int(collides.sum()), dtype=np.int64
        )
        collides = np.isin(dummy_locators, old_db_locators)
    old_index_locators = dummy_locators.copy()
    for address in range(rows.shape[0]):
        for slot in range(rows.shape[1]):
            if valid_slots[address, slot]:
                old_index_locators[address, slot] = old_db_locators[
                    rows[address, slot]
                ]

    # Each party contributes one independent key component. The MPC program
    # adds them while shared, so no party observes the complete epoch key.
    contributions = rng.integers(1, 2**30, size=5, dtype=np.int64)
    player_values = {
        0: flatten(
            old_db_locators,
            data.gallery,
            old_index_locators,
            valid_slots,
            [contributions[0]],
            # Persistent secret row references are consumed only by the
            # ORAM-reindexing baseline.  Existing SLE/join/sort programs stop
            # after the key contribution and safely ignore these trailing
            # test inputs.
            rows,
        )
    }
    for player in range(1, 5):
        player_values[player] = [int(contributions[player])]
    return player_values, rows, valid_slots


def main() -> None:
    args = parse_args()
    if args.n_records < 2:
        raise ValueError("--n-records must be at least two")
    if args.root_bits % args.block_bits:
        raise ValueError("--root-bits must be divisible by --block-bits")

    data = load_or_generate(args)
    metadata: dict[str, object] = {
        "mode": args.mode,
        "n_records": args.n_records,
        "root_bits": args.root_bits,
        "block_bits": args.block_bits,
        "bucket_capacity": args.bucket_capacity,
        "query_row": args.query_row,
        "expected_identity": data.query_label,
        "plain_query_distance": int(
            np.count_nonzero(data.gallery[args.query_row] != data.probe)
        ),
    }

    if args.mode == "full_scan":
        player_values = full_scan_inputs(data)
    elif args.mode == "oram":
        player_values, rows, valid = oram_inputs(
            data, args.block_bits, args.bucket_capacity
        )
        metadata.update(
            padded_slots=int(rows.size),
            real_slots=int(valid.sum()),
            maximum_occupancy=int(valid.sum(axis=1).max()),
        )
    else:
        player_values, rows, valid = transition_inputs(
            data, args.block_bits, args.bucket_capacity
        )
        metadata.update(
            padded_slots=int(rows.size),
            real_relation_entries=int(valid.sum()),
            maximum_occupancy=int(valid.sum(axis=1).max()),
        )

    write_inputs(args.output_dir, player_values)
    (args.output_dir / "sle_input_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
