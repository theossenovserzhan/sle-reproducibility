"""Revision experiments on frozen submitted data; NumPy + stdlib only.

Reference CPU timings are explicitly separate from MPC evidence. No test-set
threshold fitting or invented floating embeddings are performed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def write_csv(path, rows):
    if not rows:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def distances(probes, gallery):
    """Exact Hamming via signed int32 products, avoiding uint8 overflow."""
    left, right = probes.astype(np.int32), gallery.astype(np.int32)
    return left.sum(1)[:, None] + right.sum(1)[None, :] - 2 * (left @ right.T)


def mask(key, locator, bits):
    # Same SHAKE domain and serialization as the submitted lifecycle simulation.
    packed = hashlib.shake_256(
        b"M-SLE/root-mask/v1" + key + int(locator).to_bytes(8, "big")
    ).digest((bits + 7) // 8)
    return np.unpackbits(np.frombuffer(packed, np.uint8))[:bits]


def all_masks(key, locators, bits):
    return np.stack([mask(key, loc, bits) for loc in locators])


def block_values(roots, width):
    if roots.shape[1] % width:
        raise ValueError("block width must divide root width")
    blocks = roots.reshape(len(roots), -1, width).astype(np.int32)
    return blocks @ (1 << np.arange(width, dtype=np.int32))


def make_index(gallery, width):
    vals = block_values(gallery, width)
    return {
        (block, value): np.flatnonzero(vals[:, block] == value)
        for block in range(vals.shape[1]) for value in range(1 << width)
    }


def retrieve(index, probe_values, capacity=None):
    rows, overflow, occurrences = [], False, 0
    for block, value in enumerate(probe_values):
        bucket = index[(block, int(value))]
        overflow |= capacity is not None and len(bucket) > capacity
        used = bucket if capacity is None else bucket[:capacity]
        occurrences += len(used)
        rows.extend(used.tolist())
    return np.asarray(sorted(set(rows)), dtype=np.int64), bool(overflow), occurrences


def choose_winner(distance_row, candidates):
    if not len(candidates):
        return -1
    return int(candidates[np.argmin(distance_row[candidates])])


def identify(index, probe_values, distance_row, capacity, certified=False):
    candidates, overflow, occurrences = retrieve(index, probe_values, capacity)
    selected = choose_winner(distance_row, candidates)
    uncertified = selected < 0 or int(distance_row[selected]) >= len(probe_values)
    fallback = (len(candidates) < len(distance_row) and (overflow or uncertified)) if certified else overflow
    if fallback:
        selected = int(np.argmin(distance_row))
    return selected, candidates, fallback, occurrences


def index_audit(gallery, probes, labels, probe_labels, config, output):
    full = distances(probes, gallery)
    winners = np.argmin(full, axis=1)
    label_to_row = {int(label): i for i, label in enumerate(labels)}
    genuine = np.asarray([label_to_row[int(label)] for label in probe_labels])
    all_rows = np.arange(len(gallery))
    rows, details = [], []
    for width in config["index_block_bits"]:
        index = make_index(gallery, width)
        values = block_values(probes, width)
        max_occupancy = max(map(len, index.values()))
        capacities = [None] + config["index_capacities"]
        for capacity in capacities:
            policies = ["unbounded_reference"] if capacity is None else [
                "bounded_drop_diagnostic", "bounded_overflow_fallback", "bounded_certified_exact"
            ]
            for policy in policies:
                records = []
                for q, vals in enumerate(values):
                    candidates, overflow, occurrences = retrieve(index, vals, capacity)
                    preliminary = choose_winner(full[q], candidates)
                    fallback = False
                    if policy == "bounded_overflow_fallback":
                        fallback = overflow
                    if policy == "bounded_certified_exact":
                        fallback = len(candidates) < len(gallery) and (
                            overflow or preliminary < 0 or int(full[q, preliminary]) >= len(vals)
                        )
                    effective = all_rows if fallback else candidates
                    winner = choose_winner(full[q], effective)
                    records.append({
                        "genuine_retrieved": int(genuine[q] in candidates),
                        "exhaustive_winner_retrieved": int(winners[q] in candidates),
                        "decision_agreement": int(winner == winners[q]),
                        "rank1_correct": int(winner >= 0 and labels[winner] == probe_labels[q]),
                        "candidates": len(candidates),
                        "effective_candidates": len(effective),
                        "occurrences": occurrences,
                        "fallback": int(fallback),
                        "queried_overflow": int(overflow),
                    })
                    if policy in ("unbounded_reference", "bounded_certified_exact"):
                        details.append({"block_bits": width, "capacity": capacity,
                                        "policy": policy, "probe_row": q, **records[-1]})
                mean = lambda name: float(np.mean([item[name] for item in records]))
                row = {
                    "dataset": "submitted_CelebA_binary",
                    "n_gallery": len(gallery), "n_probes": len(probes),
                    "block_bits": width, "n_blocks": gallery.shape[1] // width,
                    "capacity": "unbounded" if capacity is None else capacity,
                    "policy": policy, "required_capacity": max_occupancy,
                    "overflow_buckets": 0 if capacity is None else sum(len(b) > capacity for b in index.values()),
                    "dropped_occurrences": 0 if capacity is None else sum(max(0, len(b) - capacity) for b in index.values()),
                    "genuine_candidate_recall": mean("genuine_retrieved"),
                    "exhaustive_winner_candidate_recall": mean("exhaustive_winner_retrieved"),
                    "decision_agreement": mean("decision_agreement"),
                    "rank1": mean("rank1_correct"),
                    "mean_unique_candidates": mean("candidates"),
                    "candidate_fraction": mean("candidates") / len(gallery),
                    "mean_effective_candidates": mean("effective_candidates"),
                    "mean_bucket_occurrences": mean("occurrences"),
                    "fallback_rate": mean("fallback"),
                    "queried_overflow_rate": mean("queried_overflow"),
                    "padded_index_slots": "not_applicable" if capacity is None else len(index) * capacity,
                }
                if policy == "bounded_certified_exact" and row["decision_agreement"] != 1.0:
                    raise AssertionError("certified search disagrees with exhaustive winner")
                rows.append(row)
        print(f"index width={width}: required_capacity={max_occupancy}", flush=True)
    write_csv(output / "index_results.csv", rows)
    write_csv(output / "index_per_probe.csv", details)
    baseline = {
        "rank1": float(np.mean(labels[winners] == probe_labels)),
        "rank5": float(np.mean(np.any(labels[np.argsort(full, axis=1, kind="stable")[:, :5]] == probe_labels[:, None], axis=1))),
        "tie_policy": "first gallery row among minimum Hamming scores",
        "historical_mpc_tie_policy": "random unique tie tags; distinct from stable-row policy",
        "probes_with_minimum_distance_ties": int(np.sum(np.sum(full == full.min(1)[:, None], 1) > 1)),
        "minimum_winner_distance": int(full.min()),
        "median_winner_distance": float(np.median(full.min(1))),
        "maximum_winner_distance": int(full.min(1).max()),
    }
    write_json(output / "binary_baseline.json", baseline)
    return rows, baseline


def lifecycle(gallery, probes, config, output):
    rng = np.random.default_rng(config["seed"])
    n, bits = gallery.shape
    locators = rng.integers(1, np.iinfo(np.uint64).max, size=n, dtype=np.uint64)
    key = rng.bytes(32)
    masks = all_masks(key, locators, bits)
    protected = gallery ^ masks
    expected = distances(probes, gallery)
    rows = []
    for epoch in range(1, config["lifecycle_epochs"] + 1):
        # Independent new simulated tokens; not asserted to implement a PRP.
        new_locators = rng.integers(1, np.iinfo(np.uint64).max, size=n, dtype=np.uint64)
        if len(np.unique(new_locators)) != n:
            raise RuntimeError("simulated locator collision")
        new_key = rng.bytes(32)
        fresh_masks = all_masks(new_key, new_locators, bits)
        renewed = protected ^ masks ^ fresh_masks
        mismatch_bits = int(np.count_nonzero(renewed != (gallery ^ fresh_masks)))
        score_mismatches = 0
        for start in range(0, len(probes), 16):
            q = probes[start:start + 16]
            actual = np.count_nonzero((q[:, None, :] ^ fresh_masks) != renewed, axis=2)
            score_mismatches += int(np.count_nonzero(actual != expected[start:start + len(q)]))
        rows.append({"epoch": epoch, "rekey_bit_mismatches": mismatch_bits,
                     "protected_score_mismatches": score_mismatches,
                     "scores_compared": int(expected.size), "bits_rekeyed": int(gallery.size)})
        protected, masks, locators, key = renewed, fresh_masks, new_locators, new_key
    write_csv(output / "exact_lifecycle.csv", rows)
    if any(r["rekey_bit_mismatches"] or r["protected_score_mismatches"] for r in rows):
        raise AssertionError("masking or rekeying mismatch")
    return {"epochs": len(rows), "rekey_bit_mismatches": 0, "protected_score_mismatches": 0,
            "total_scores_compared": sum(r["scores_compared"] for r in rows),
            "total_bits_rekeyed": sum(r["bits_rekeyed"] for r in rows)}


def benchmark(gallery, probes, config, output):
    raw, summary, model_rows = [], [], []
    rng = np.random.default_rng(config["seed"] + 1)
    for synthetic, sizes in ((False, config["timing_real_gallery_sizes"]),
                             (True, config["timing_synthetic_gallery_sizes"])):
        for n in sizes:
            g = rng.integers(0, 2, (n, gallery.shape[1]), np.uint8) if synthetic else gallery[:n]
            q = rng.integers(0, 2, gallery.shape[1], np.uint8) if synthetic else probes[0]
            locators = np.arange(1, n + 1, dtype=np.uint64)
            old_key, new_key = rng.bytes(32), rng.bytes(32)
            old_masks = all_masks(old_key, locators, g.shape[1])
            protected = g ^ old_masks
            label = "synthetic_compute_only" if synthetic else "submitted_CelebA_binary"
            for rep in range(-config["warmups"], config["timing_repeats"]):
                start = time.perf_counter_ns()
                query_masks = all_masks(old_key, locators, g.shape[1])
                mask_end = time.perf_counter_ns()
                protected_query = q[None, :] ^ query_masks
                scores = np.count_nonzero(protected_query != protected, axis=1)
                decision = int(np.argmin(scores))
                query_end = time.perf_counter_ns()
                previous_masks = all_masks(old_key, locators, g.shape[1])
                next_masks = all_masks(new_key, locators + n, g.shape[1])
                renewal_masks_end = time.perf_counter_ns()
                updated = protected ^ previous_masks ^ next_masks
                rekey_end = time.perf_counter_ns()
                if not np.array_equal(scores, np.count_nonzero(g != q, axis=1)):
                    raise AssertionError("CPU query differs from binary full scan")
                if not np.array_equal(updated, g ^ next_masks):
                    raise AssertionError("CPU rekey differs from fresh enrollment")
                if rep < 0:
                    continue
                raw.append({"dataset": label, "n": n, "repeat": rep,
                            "query_mask_ms": (mask_end - start) / 1e6,
                            "query_compare_argmin_ms": (query_end - mask_end) / 1e6,
                            "query_total_ms": (query_end - start) / 1e6,
                            "rekey_two_masks_ms": (renewal_masks_end - query_end) / 1e6,
                            "rekey_xor_ms": (rekey_end - renewal_masks_end) / 1e6,
                            "rekey_total_ms": (rekey_end - query_end) / 1e6,
                            "array_persistent_bytes_unpacked": int(protected.nbytes + locators.nbytes),
                            "template_payload_bytes_packed": int(n * g.shape[1] // 8),
                            "decision_row": decision})
            current = [r for r in raw if r["dataset"] == label and r["n"] == n]
            for metric in ("query_mask_ms", "query_total_ms", "rekey_two_masks_ms", "rekey_total_ms"):
                vals = np.asarray([r[metric] for r in current])
                summary.append({"dataset": label, "n": n, "metric": metric,
                                "mean_ms": float(vals.mean()), "std_ms": float(vals.std(ddof=1)),
                                "median_ms": float(np.median(vals)),
                                "min_ms": float(vals.min()), "max_ms": float(vals.max()),
                                "repeats": len(vals), "mpc_measured": False,
                                "communication_measured": False})
            # Workload/storage counts only, not a validated MPC latency model.
            for width in config["index_block_bits"]:
                vals = block_values(g, width)
                occupancy = [np.bincount(vals[:, b], minlength=1 << width).max()
                             for b in range(vals.shape[1])]
                required = int(max(occupancy))
                slots = vals.shape[1] * (1 << width) * required
                model_rows.append({"dataset": label, "n": n, "root_bits": g.shape[1],
                                   "block_bits": width, "required_capacity": required,
                                   "padded_slots": slots,
                                   "unpacked_template_bytes": int(g.nbytes),
                                   "packed_template_bytes": int(n * g.shape[1] // 8),
                                   "minimum_index_payload_bytes_locator64_valid1": int((slots * 65 + 7) // 8),
                                   "share_storage_bytes_at_128bit_field_5_parties": int((n * (g.shape[1] + 1) + 2 * slots) * 16 * 5),
                                   "mask_expansions_per_query": n,
                                   "mask_expansions_per_rekey": 2 * n,
                                   "locator_evaluations_per_rekey": n + slots,
                                   "assumption": "illustrative 128-bit field, each bit/validity separately shared; no MAC, buffer or runtime overhead"})
            print(f"CPU reference {label} N={n} complete", flush=True)
    write_csv(output / "cpu_reference_raw.csv", raw)
    write_csv(output / "cpu_reference_summary.csv", summary)
    write_csv(output / "workload_storage_counts.csv", model_rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "inputs" / "celeba_128_binary_roots.npz")
    parser.add_argument("--output", type=Path, default=ROOT / "results")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    config = json.loads((ROOT / "protocol.json").read_text(encoding="utf-8"))
    with np.load(args.input, allow_pickle=False) as data:
        gallery, probes = data["gallery_roots"], data["probe_roots"]
        labels, probe_labels = data["gallery_labels"], data["probe_labels"]
    assert gallery.shape == (128, 512) and probes.shape == (512, 512)
    assert np.isin(gallery, [0, 1]).all() and np.isin(probes, [0, 1]).all()
    assert len(np.unique(labels)) == len(gallery)
    assert set(probe_labels).issubset(set(labels))
    write_json(args.output / "run_manifest.json", {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "input_path": str(args.input.resolve()), "input_sha256": sha256(args.input),
        "script_sha256": sha256(__file__), "protocol_sha256": sha256(ROOT / "protocol.json"),
        "python": sys.version, "numpy": np.__version__, "platform": platform.platform(),
        "cpu": platform.processor(), "logical_cpus": os.cpu_count(),
        "thread_environment": {k: os.environ.get(k) for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
        "gallery_shape": list(gallery.shape), "probe_shape": list(probes.shape),
        "probes_per_identity": sorted(set(Counter(map(int, probe_labels)).values())),
        "float_embeddings_available": False, "mpc_timings_in_this_run": False,
        "limitations": config["evidence_boundary"],
    })
    index_rows, baseline = index_audit(gallery, probes, labels, probe_labels, config, args.output)
    life = lifecycle(gallery, probes, config, args.output)
    benchmark(gallery, probes, config, args.output)
    summary = {"baseline": baseline, "lifecycle": life,
               "unbounded_index": [r for r in index_rows if r["policy"] == "unbounded_reference"],
               "certified_search_all_agree": all(r["decision_agreement"] == 1 for r in index_rows if r["policy"] == "bounded_certified_exact"),
               "remaining": ["float vs binary biometric comparison", "full secure MPC query and transition timing", "oblivious storage and access measurements", "stronger same-contract MPC baseline"],
               "completed_utc": datetime.now(timezone.utc).isoformat()}
    write_json(args.output / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
