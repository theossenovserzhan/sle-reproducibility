"""Paired real-valued/binary utility and calibrated rejection evaluation.

Input NPZ: embeddings [identities, >=6 images, 128 float features], identities,
image_ids [identities, images]. Supply independently extracted real embeddings.
The first 128 identities form evaluation, next 32 calibration, last 32 unknown.
No test probes participate in threshold selection. Masks add zero score error
algebraically; this script quantifies the separate binarization cost.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

import numpy as np

from run_experiments import distances, sha256, write_csv, write_json


def normalize(values):
    norms = np.linalg.norm(values, axis=-1, keepdims=True)
    if np.any(norms < 1e-10):
        raise ValueError("zero embedding")
    return values / norms


def threshold_from_calibration(negative_scores, target_far):
    negative_scores = np.sort(np.asarray(negative_scores, dtype=np.float64).ravel())
    if not len(negative_scores):
        raise ValueError("no calibration negatives")
    allowed = int(np.floor(target_far * len(negative_scores)))
    if allowed >= len(negative_scores):
        return float(negative_scores[0])
    # Strictly above the (allowed+1)-th highest negative, so ties cannot
    # accidentally exceed the nominal calibration FAR.
    return float(np.nextafter(negative_scores[-allowed - 1], np.inf))


def scores_for(prototypes, probes, representation):
    if representation == "float_cosine":
        return normalize(probes) @ normalize(prototypes).T
    return -distances((probes >= 0).astype(np.uint8),
                      (prototypes >= 0).astype(np.uint8)).astype(float)


def split_prototypes(embeddings, split_index, dataset_seed):
    rng = np.random.default_rng(dataset_seed + split_index)
    galleries, probes, labels, positions = [], [], [], []
    for row, images in enumerate(embeddings):
        chosen = np.sort(rng.choice(6, 2, replace=False))
        held = np.setdiff1d(np.arange(6), chosen)
        galleries.append(images[chosen].mean(0))
        probes.extend(images[held])
        labels.extend([row] * len(held))
        positions.append(chosen.tolist())
    return np.asarray(galleries), np.asarray(probes), np.asarray(labels), positions


def bootstrap_subject_delta(float_values, binary_values, rng, samples=5000):
    delta = np.asarray(binary_values) - np.asarray(float_values)
    samples_out = np.empty(samples)
    for i in range(samples):
        samples_out[i] = rng.choice(delta, size=len(delta), replace=True).mean()
    return {"binary_minus_float": float(delta.mean()),
            "subject_bootstrap_ci95": np.quantile(samples_out, [0.025, 0.975]).tolist(),
            "bootstrap_units": "identities after averaging their repeated splits",
            "bootstrap_resamples": samples}


def evaluate(input_path, output, dataset_name, n_eval=128, n_cal=32, n_unknown=32, n_splits=20):
    with np.load(input_path, allow_pickle=False) as data:
        embeddings = data["embeddings"].astype(np.float64)
        identities = data["identities"]
        image_ids = data["image_ids"]
    if embeddings.ndim != 3 or embeddings.shape[1:] != (6, 128):
        raise ValueError("expected [identities,6,128] float embeddings")
    if len(embeddings) != n_eval + n_cal + n_unknown:
        raise ValueError("cohort sizes do not match input")
    if len(np.unique(identities)) != len(identities):
        raise ValueError("identity overlap")
    if len(np.unique(image_ids)) != image_ids.size:
        raise ValueError("image reused across cohorts")
    if not np.isfinite(embeddings).all() or np.isin(embeddings, [0, 1]).all():
        raise ValueError("need finite original float embeddings, not binary roots")
    eval_e, cal_e = embeddings[:n_eval], embeddings[n_eval:n_eval+n_cal]
    unknown_e = embeddings[n_eval+n_cal:]
    rows, split_records, subject_records = [], [], []
    seed = 20260722 + (10000 if dataset_name == "CelebA" else 20000)
    for split in range(n_splits):
        g, p, labels, chosen = split_prototypes(eval_e, split, seed)
        cg, cp, clabels, cchosen = split_prototypes(cal_e, split, seed + 100000)
        split_records.append({"split": split, "evaluation_gallery_positions": chosen,
                              "calibration_gallery_positions": cchosen})
        for rep in ("float_cosine", "binary_hamming"):
            scores = scores_for(g, p, rep)
            cal_scores = scores_for(cg, cp, rep)
            truth = np.arange(n_eval)[None, :] == labels[:, None]
            cal_truth = np.arange(n_cal)[None, :] == clabels[:, None]
            order = np.argsort(-scores, axis=1, kind="stable")
            correct1 = (order[:, 0] == labels)
            correct5 = np.any(order[:, :5] == labels[:, None], 1)
            row = {"dataset": dataset_name, "split": split, "representation": rep,
                   "rank1": float(correct1.mean()), "rank5": float(correct5.mean()),
                   "genuine_pairs": int(truth.sum()), "impostor_pairs": int((~truth).sum()),
                   "verification_calibration_negative_pairs": int((~cal_truth).sum())}
            for subject in range(n_eval):
                use = labels == subject
                subject_records.append({"split": split, "representation": rep, "subject_row": subject,
                                        "rank1": float(correct1[use].mean()), "rank5": float(correct5[use].mean())})
            for target in (0.01, 0.001):
                token = str(target).replace(".", "p")
                threshold = threshold_from_calibration(cal_scores[~cal_truth], target)
                row[f"verification_threshold_far_{token}"] = threshold
                row[f"verification_test_far_{token}"] = float(np.mean(scores[~truth] >= threshold))
                row[f"verification_test_tar_{token}"] = float(np.mean(scores[truth] >= threshold))
                row[f"verification_calibration_far_{token}"] = float(np.mean(cal_scores[~cal_truth] >= threshold))
            # Calibration identities are all unenrolled in the evaluation
            # gallery. Evaluate open-set thresholds against that same gallery
            # size, using a separate unknown cohort only for testing.
            cal_unknown_scores = scores_for(g, cal_e.reshape(-1, 128), rep).max(1)
            unknown_scores = scores_for(g, unknown_e.reshape(-1, 128), rep).max(1)
            row["open_calibration_probes"] = len(cal_unknown_scores)
            row["open_test_unknown_probes"] = len(unknown_scores)
            row["open_calibration_fpir_resolution"] = 1 / len(cal_unknown_scores)
            for target in (0.01, 0.001):
                token = str(target).replace(".", "p")
                threshold = threshold_from_calibration(cal_unknown_scores, target)
                row[f"open_threshold_fpir_{token}"] = threshold
                row[f"open_calibration_fpir_{token}"] = float(np.mean(cal_unknown_scores >= threshold))
                row[f"open_test_fpir_{token}"] = float(np.mean(unknown_scores >= threshold))
                row[f"open_test_dir_{token}"] = float(np.mean(correct1 & (scores.max(1) >= threshold)))
            rows.append(row)
        print(f"{dataset_name}: paired split {split+1}/{n_splits}", flush=True)
    output = Path(output)
    write_csv(output / "paired_split_metrics.csv", rows)
    write_csv(output / "paired_subject_metrics.csv", subject_records)
    write_json(output / "split_positions.json", split_records)
    paired = {}
    for metric in ("rank1", "rank5"):
        by_rep = {}
        for rep in ("float_cosine", "binary_hamming"):
            by_rep[rep] = [np.mean([r[metric] for r in subject_records if r["representation"] == rep and r["subject_row"] == s])
                           for s in range(n_eval)]
        paired[metric] = bootstrap_subject_delta(by_rep["float_cosine"], by_rep["binary_hamming"], np.random.default_rng(seed + 200000))
        paired[metric]["float_mean"] = float(np.mean(by_rep["float_cosine"]))
        paired[metric]["binary_mean"] = float(np.mean(by_rep["binary_hamming"]))
    write_json(output / "paired_summary.json", {
        "frontend":"SFace128D with YuNet alignment", "dataset": dataset_name, "input_sha256": sha256(input_path),
        "script_sha256": sha256(__file__), "numpy": np.__version__,
        "n_evaluation": n_eval, "n_calibration": n_cal, "n_test_unknown": n_unknown,
        "splits": n_splits, "paired": paired,
        "verification_pairs": "all 4 probes per evaluation identity vs each gallery prototype; one genuine and N-1 impostors per probe",
        "threshold_selection": "identity-disjoint calibration only; discrete thresholds with acceptance score>=threshold",
        "open_set": "calibration and test unknown cohorts disjoint, both scored against same evaluation gallery",
        "limitations": ["custom protocols, not official LFW verification", "repeated splits reuse identities and images", "low FAR/FPIR estimates limited by negative counts; rows are correlated within identity", "conditional on this SFace frontend and its alignment; do not pool with FaceNet outcomes"]})
    return paired


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset", choices=["CelebA", "LFW"], required=True)
    args = parser.parse_args()
    print(evaluate(args.input, args.output, args.dataset))
