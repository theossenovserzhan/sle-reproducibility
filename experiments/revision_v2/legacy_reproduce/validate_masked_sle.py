"""Validate masked SLE on the saved CelebA binary-root split.

The experiment evaluates the biometric-specific extension used in the T-BIOM
revision.  An enrolled binary root b_i is stored only as

    c_i^e = b_i XOR G(K_e, locator_i^e)

where G is instantiated with SHAKE-256 for the protocol simulation.  At the
next epoch, the stored value is re-keyed directly as

    c_i^(e+1) = c_i^e XOR G(K_e, locator_i^e)
                         XOR G(K_(e+1), locator_i^(e+1)).

The raw root is never an input to the re-keying operation.  During matching,
the current candidate mask is applied to the probe inside the protected
computation, so Hamming distances are preserved exactly.

This script deliberately uses only NumPy and the Python standard library so it
can run in the repository's lightweight validation environment.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Iterable

import numpy as np


METHOD = "Masked Synchronized Locator Evolution (M-SLE)"


def prf_mask(key: bytes, locator: int, n_bits: int) -> np.ndarray:
    """Expand a secret epoch key and secret locator to a binary mask."""

    n_bytes = (n_bits + 7) // 8
    domain = b"M-SLE/root-mask/v1" + key + int(locator).to_bytes(8, "big")
    packed = hashlib.shake_256(domain).digest(n_bytes)
    return np.unpackbits(np.frombuffer(packed, dtype=np.uint8))[:n_bits]


def locator_prp(key: bytes, locator: int) -> int:
    """Simulation of a keyed 64-bit locator permutation interface.

    The executable MPC artifact uses its own MPC-friendly PRP.  This function
    supplies deterministic, key-dependent tokens for the biometric lifecycle
    tests; it is not presented as the production PRP implementation.
    """

    domain = b"M-SLE/locator/v1" + int(locator).to_bytes(8, "big")
    return int.from_bytes(hashlib.blake2b(domain, key=key, digest_size=8).digest(), "big")


def masks_for(key: bytes, locators: np.ndarray, n_bits: int) -> np.ndarray:
    return np.stack([prf_mask(key, int(locator), n_bits) for locator in locators])


def evolve_locators(key: bytes, locators: np.ndarray) -> np.ndarray:
    evolved = np.asarray([locator_prp(key, int(value)) for value in locators], dtype=np.uint64)
    if np.unique(evolved).size != evolved.size:
        raise RuntimeError("A simulated locator collision occurred; rerun with another seed")
    return evolved


def pairwise_hamming(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    return np.count_nonzero(left[:, None, :] != right[None, :, :], axis=2)


def auc_from_scores(positive: np.ndarray, negative: np.ndarray) -> float:
    """AUC as P(score_positive > score_negative), with half credit for ties."""

    positive = np.asarray(positive).ravel()
    negative = np.asarray(negative).ravel()
    values = np.concatenate([positive, negative])
    labels = np.concatenate([
        np.ones(positive.size, dtype=np.uint8),
        np.zeros(negative.size, dtype=np.uint8),
    ])
    order = np.argsort(values, kind="mergesort")
    values = values[order]
    labels = labels[order]
    lower_negative = 0
    wins = 0.0
    start = 0
    while start < values.size:
        end = start + 1
        while end < values.size and values[end] == values[start]:
            end += 1
        block = labels[start:end]
        n_pos = int(block.sum())
        n_neg = int(block.size - n_pos)
        wins += n_pos * (lower_negative + 0.5 * n_neg)
        lower_negative += n_neg
        start = end
    return float(wins / (positive.size * negative.size))


def assignment_min_cost(cost: np.ndarray) -> np.ndarray:
    """Hungarian algorithm for a square cost matrix.

    Returns one selected column for every row.
    """

    cost = np.asarray(cost, dtype=float)
    n, m = cost.shape
    if n != m:
        raise ValueError("The assignment implementation expects a square matrix")
    u = np.zeros(n + 1)
    v = np.zeros(m + 1)
    p = np.zeros(m + 1, dtype=int)
    way = np.zeros(m + 1, dtype=int)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = np.full(m + 1, np.inf)
        used = np.zeros(m + 1, dtype=bool)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = np.inf
            j1 = 0
            for j in range(1, m + 1):
                if not used[j]:
                    cur = cost[i0 - 1, j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    selected = np.empty(n, dtype=int)
    for j in range(1, m + 1):
        selected[p[j] - 1] = j - 1
    return selected


def relational_signature_assignment(old_templates: np.ndarray,
                                    new_templates: np.ndarray,
                                    observed_order: np.ndarray) -> float:
    """Link epochs through the geometry of the complete template set.

    For every template, the attack sorts its distances to all other templates.
    The resulting signature is invariant to row permutation.  A global
    distance-preserving transform therefore remains linkable even when direct
    old-to-new template distances look random.  Independent identity-specific
    masks should remove this relational signal.
    """

    old_distances = pairwise_hamming(old_templates, old_templates).astype(float)
    new_distances = pairwise_hamming(new_templates, new_templates).astype(float)
    keep = ~np.eye(old_templates.shape[0], dtype=bool)
    old_signatures = np.sort(old_distances[keep].reshape(old_templates.shape[0], -1), axis=1)
    new_signatures = np.sort(new_distances[keep].reshape(new_templates.shape[0], -1), axis=1)
    shuffled_signatures = new_signatures[observed_order]
    cost = np.mean(
        np.abs(old_signatures[:, None, :] - shuffled_signatures[None, :, :]),
        axis=2,
    )
    assignment = assignment_min_cost(cost)
    linked_identity = observed_order[assignment]
    return float(np.mean(linked_identity == np.arange(old_templates.shape[0])))


def rank_metrics(gallery: np.ndarray, probes: np.ndarray, gallery_labels: np.ndarray,
                 probe_labels: np.ndarray) -> dict[str, float]:
    distances = pairwise_hamming(probes, gallery)
    order = np.argsort(distances, axis=1, kind="stable")
    ranked_labels = gallery_labels[order]
    return {
        "rank1": float(np.mean(ranked_labels[:, 0] == probe_labels)),
        "rank5": float(np.mean(np.any(ranked_labels[:, :5] == probe_labels[:, None], axis=1))),
        "mean_genuine_distance": float(np.mean([
            distances[row, np.flatnonzero(gallery_labels == label)[0]]
            for row, label in enumerate(probe_labels)
        ])),
    }


def protected_rank_metrics(masked_gallery: np.ndarray, probes: np.ndarray, masks: np.ndarray,
                           gallery_labels: np.ndarray, probe_labels: np.ndarray) -> dict[str, float]:
    # Candidate-conditioned query masking is evaluated in a vectorized form.
    distances = np.empty((probes.shape[0], masked_gallery.shape[0]), dtype=np.int16)
    for start in range(0, probes.shape[0], 64):
        batch = probes[start:start + 64]
        protected_queries = np.bitwise_xor(batch[:, None, :], masks[None, :, :])
        distances[start:start + batch.shape[0]] = np.count_nonzero(
            protected_queries != masked_gallery[None, :, :], axis=2
        )
    order = np.argsort(distances, axis=1, kind="stable")
    ranked_labels = gallery_labels[order]
    return {
        "rank1": float(np.mean(ranked_labels[:, 0] == probe_labels)),
        "rank5": float(np.mean(np.any(ranked_labels[:, :5] == probe_labels[:, None], axis=1))),
    }


def cross_key_misuse_rank1(old_gallery: np.ndarray, probes: np.ndarray, new_masks: np.ndarray,
                           gallery_labels: np.ndarray, probe_labels: np.ndarray) -> float:
    distances = np.empty((probes.shape[0], old_gallery.shape[0]), dtype=np.int16)
    for start in range(0, probes.shape[0], 64):
        batch = probes[start:start + 64]
        new_queries = np.bitwise_xor(batch[:, None, :], new_masks[None, :, :])
        distances[start:start + batch.shape[0]] = np.count_nonzero(
            new_queries != old_gallery[None, :, :], axis=2
        )
    predicted = gallery_labels[np.argmin(distances, axis=1)]
    return float(np.mean(predicted == probe_labels))


def linear_root_recovery_accuracy(masked: np.ndarray, roots: np.ndarray,
                                  train_rows: np.ndarray, test_rows: np.ndarray,
                                  ridge: float = 10.0) -> tuple[float, float]:
    """Held-out multi-output ridge attack and train-prior baseline."""

    x_train = masked[train_rows].astype(float)
    x_test = masked[test_rows].astype(float)
    y_train = roots[train_rows].astype(float)
    y_test = roots[test_rows]
    x_train = np.concatenate([x_train, np.ones((x_train.shape[0], 1))], axis=1)
    x_test = np.concatenate([x_test, np.ones((x_test.shape[0], 1))], axis=1)
    gram = x_train @ x_train.T + ridge * np.eye(x_train.shape[0])
    dual = np.linalg.solve(gram, y_train)
    weights = x_train.T @ dual
    prediction = (x_test @ weights >= 0.5).astype(np.uint8)
    attack_accuracy = float(np.mean(prediction == y_test))
    prior = (np.mean(y_train, axis=0) >= 0.5).astype(np.uint8)
    prior_accuracy = float(np.mean(prior[None, :] == y_test))
    return attack_accuracy, prior_accuracy


def lagrange_at_zero(xs: Iterable[int], ys: np.ndarray, prime: int) -> np.ndarray:
    xs = list(xs)
    result = np.zeros(ys.shape[1:], dtype=np.int64)
    for i, x_i in enumerate(xs):
        numerator = 1
        denominator = 1
        for j, x_j in enumerate(xs):
            if i != j:
                numerator = (numerator * (-x_j)) % prime
                denominator = (denominator * (x_i - x_j)) % prime
        coefficient = numerator * pow(int(denominator), -1, prime) % prime
        result = (result + coefficient * ys[i]) % prime
    return result


def shamir_share(secrets: np.ndarray, rng: np.random.Generator, prime: int = 65537,
                 parties: int = 5, threshold: int = 2) -> np.ndarray:
    coefficients = rng.integers(0, prime, size=(threshold,) + secrets.shape, dtype=np.int64)
    shares = np.empty((parties,) + secrets.shape, dtype=np.int64)
    for party in range(parties):
        x = party + 1
        value = secrets.astype(np.int64).copy()
        for degree in range(1, threshold + 1):
            value = (value + coefficients[degree - 1] * pow(x, degree, prime)) % prime
        shares[party] = value
    return shares


def proactive_refresh(shares: np.ndarray, rng: np.random.Generator, prime: int = 65537,
                      threshold: int = 2) -> np.ndarray:
    parties = shares.shape[0]
    refreshed = shares.copy()
    # Every party contributes a random degree-t zero polynomial.  Its constant
    # coefficient is zero, so the reconstructed secret does not change.
    for _dealer in range(parties):
        coefficients = rng.integers(0, prime, size=(threshold,) + shares.shape[1:], dtype=np.int64)
        for receiver in range(parties):
            x = receiver + 1
            delta = np.zeros(shares.shape[1:], dtype=np.int64)
            for degree in range(1, threshold + 1):
                delta = (delta + coefficients[degree - 1] * pow(x, degree, prime)) % prime
            refreshed[receiver] = (refreshed[receiver] + delta) % prime
    return refreshed


def mean_ci95(values: Iterable[float]) -> tuple[float, float, float]:
    values = np.asarray(list(values), dtype=float)
    mean = float(values.mean())
    if values.size < 2:
        return mean, mean, mean
    half = 1.96 * float(values.std(ddof=1)) / math.sqrt(values.size)
    return mean, mean - half, mean + half


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def make_svg(path: Path, summary: dict) -> None:
    metrics = [
        ("Raw Rank-1", summary["raw_rank1"]),
        ("M-SLE Rank-1", summary["protected_rank1"]),
        ("Cross-epoch AUC", summary["cross_epoch_auc_mean"]),
        ("Assignment accuracy", summary["global_link_mean"]),
        ("Cross-key Rank-1", summary["cross_key_rank1_mean"]),
        ("Root attack accuracy", summary["root_attack_mean"]),
    ]
    width, height = 1120, 520
    left, top, plot_w, row_h = 300, 62, 740, 64
    colors = ["#2f5597", "#2f5597", "#777777", "#777777", "#b45f06", "#777777"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#111}.title{font-size:24px;font-weight:700}.label{font-size:18px}.value{font-size:17px;font-weight:700}.axis{font-size:14px;fill:#444}</style>',
        '<text x="560" y="32" text-anchor="middle" class="title">M-SLE biometric utility and lifecycle privacy</text>',
    ]
    for tick in range(0, 11, 2):
        x = left + plot_w * tick / 10
        parts.append(f'<line x1="{x:.1f}" y1="48" x2="{x:.1f}" y2="448" stroke="#d6d6d6" stroke-width="1"/>')
        parts.append(f'<text x="{x:.1f}" y="472" text-anchor="middle" class="axis">{tick/10:.1f}</text>')
    for idx, ((label, value), color) in enumerate(zip(metrics, colors)):
        y = top + idx * row_h
        bar_w = max(1, plot_w * value)
        parts.append(f'<text x="{left-14}" y="{y+25}" text-anchor="end" class="label">{label}</text>')
        parts.append(f'<rect x="{left}" y="{y+5}" width="{bar_w:.1f}" height="30" fill="{color}"/>')
        value_x = min(left + bar_w + 10, width - 45)
        parts.append(f'<text x="{value_x:.1f}" y="{y+27}" class="value">{value:.4f}</text>')
    parts.append('<text x="560" y="505" text-anchor="middle" class="axis">Probability / accuracy (lower is better for the four lifecycle-privacy attack metrics)</text>')
    parts.append('</svg>')
    path.write_text("\n".join(parts), encoding="utf-8")


def run(input_path: Path, output_dir: Path, epochs: int, seed: int) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    data = np.load(input_path)
    gallery = data["gallery_roots"].astype(np.uint8)
    gallery_labels = data["gallery_labels"]
    probes = data["probe_roots"].astype(np.uint8)
    probe_labels = data["probe_labels"]
    n_identities, n_bits = gallery.shape
    rng = np.random.default_rng(seed)

    raw = rank_metrics(gallery, probes, gallery_labels, probe_labels)
    # Same sampled indices and RNG state without constructing a 16-GiB arange.
    locators = (rng.choice(2 ** 31 - 1, size=n_identities, replace=False) + 1).astype(np.uint64)
    key = rng.bytes(32)
    masks = masks_for(key, locators, n_bits)
    masked = np.bitwise_xor(gallery, masks)
    first_protected = protected_rank_metrics(masked, probes, masks, gallery_labels, probe_labels)

    order = rng.permutation(n_identities)
    split = int(round(0.75 * n_identities))
    train_rows, test_rows = order[:split], order[split:]

    epoch_rows: list[dict] = []
    old_key = key
    old_locators = locators
    old_masked = masked
    old_masks = masks
    old_global_mask = prf_mask(rng.bytes(32), 0, n_bits)
    old_global_masked = np.bitwise_xor(gallery, old_global_mask[None, :])

    for epoch in range(1, epochs + 1):
        new_key = rng.bytes(32)
        new_locators = evolve_locators(new_key, old_locators)
        new_masks = masks_for(new_key, new_locators, n_bits)
        rekeyed = np.bitwise_xor(np.bitwise_xor(old_masked, old_masks), new_masks)
        direct = np.bitwise_xor(gallery, new_masks)
        rekey_exact = bool(np.array_equal(rekeyed, direct))

        protected = protected_rank_metrics(rekeyed, probes, new_masks, gallery_labels, probe_labels)
        distance = pairwise_hamming(old_masked, rekeyed)
        diagonal = -np.diag(distance).astype(float)
        off_diagonal = -distance[~np.eye(n_identities, dtype=bool)].astype(float)
        link_auc = auc_from_scores(diagonal, off_diagonal)

        observed_order = rng.permutation(n_identities)
        assignment = assignment_min_cost(distance[:, observed_order])
        linked_identity = observed_order[assignment]
        global_link = float(np.mean(linked_identity == np.arange(n_identities)))
        relational_link = relational_signature_assignment(
            old_masked, rekeyed, observed_order
        )

        # Naive epoch rotation with one global mask is a deliberately strong
        # comparison.  It preserves every inter-identity Hamming distance, so
        # the relational attack can link identities despite fresh epoch keys.
        new_global_mask = prf_mask(rng.bytes(32), 0, n_bits)
        new_global_masked = np.bitwise_xor(gallery, new_global_mask[None, :])
        global_mask_distance = pairwise_hamming(old_global_masked, new_global_masked)
        global_mask_auc = auc_from_scores(
            -np.diag(global_mask_distance).astype(float),
            -global_mask_distance[~np.eye(n_identities, dtype=bool)].astype(float),
        )
        global_mask_relational_link = relational_signature_assignment(
            old_global_masked, new_global_masked, observed_order
        )

        cross_key_rank1 = cross_key_misuse_rank1(
            old_masked, probes, new_masks, gallery_labels, probe_labels
        )
        recovery_accuracy, prior_accuracy = linear_root_recovery_accuracy(
            rekeyed, gallery, train_rows, test_rows
        )

        # Positive controls verify that the attack metrics respond when a
        # persistent relation or the complete key is exposed.
        stable_distance = pairwise_hamming(old_masked, old_masked)
        stable_auc = auc_from_scores(
            -np.diag(stable_distance).astype(float),
            -stable_distance[~np.eye(n_identities, dtype=bool)].astype(float),
        )
        key_recovered = np.bitwise_xor(rekeyed, new_masks)
        key_recovery_accuracy = float(np.mean(key_recovered == gallery))

        epoch_rows.append({
            "epoch": epoch,
            "rekey_exact": int(rekey_exact),
            "rank1": protected["rank1"],
            "rank5": protected["rank5"],
            "cross_epoch_auc": link_auc,
            "global_assignment_accuracy": global_link,
            "relational_signature_accuracy": relational_link,
            "random_assignment_chance": 1.0 / n_identities,
            "global_mask_pairwise_auc": global_mask_auc,
            "global_mask_relational_accuracy": global_mask_relational_link,
            "cross_key_rank1": cross_key_rank1,
            "random_identification_chance": 1.0 / n_identities,
            "linear_root_recovery_accuracy": recovery_accuracy,
            "root_prior_accuracy": prior_accuracy,
            "stable_template_auc_control": stable_auc,
            "known_key_root_recovery_control": key_recovery_accuracy,
        })

        old_key = new_key
        old_locators = new_locators
        old_masked = rekeyed
        old_masks = new_masks
        old_global_mask = new_global_mask
        old_global_masked = new_global_masked

    # Demonstrate proactive share refresh and the mobile-adversary boundary on
    # the final masked state.  The same secret is reconstructed each epoch, but
    # shares captured from different epochs cannot be pooled as one polynomial.
    prime = 65537
    shares_0 = shamir_share(old_masked, rng, prime=prime)
    shares_1 = proactive_refresh(shares_0, rng, prime=prime)
    shares_2 = proactive_refresh(shares_1, rng, prime=prime)
    reconstructed = lagrange_at_zero([1, 2, 3], shares_2[:3], prime)
    refresh_preserves_secret = bool(np.array_equal(reconstructed, old_masked))
    stale_reconstruction = lagrange_at_zero(
        [1, 2, 3], np.stack([shares_0[0], shares_1[1], shares_2[2]]), prime
    )
    stale_exact_fraction = float(np.mean(stale_reconstruction == old_masked))
    static_reconstruction = lagrange_at_zero(
        [1, 2, 3], np.stack([shares_0[0], shares_0[1], shares_0[2]]), prime
    )
    static_exact_fraction = float(np.mean(static_reconstruction == old_masked))

    auc_mean, auc_low, auc_high = mean_ci95(row["cross_epoch_auc"] for row in epoch_rows)
    global_mean, global_low, global_high = mean_ci95(
        row["global_assignment_accuracy"] for row in epoch_rows
    )
    relational_mean, relational_low, relational_high = mean_ci95(
        row["relational_signature_accuracy"] for row in epoch_rows
    )
    global_mask_auc_mean, global_mask_auc_low, global_mask_auc_high = mean_ci95(
        row["global_mask_pairwise_auc"] for row in epoch_rows
    )
    global_mask_rel_mean, global_mask_rel_low, global_mask_rel_high = mean_ci95(
        row["global_mask_relational_accuracy"] for row in epoch_rows
    )
    cross_mean, cross_low, cross_high = mean_ci95(row["cross_key_rank1"] for row in epoch_rows)
    recovery_mean, recovery_low, recovery_high = mean_ci95(
        row["linear_root_recovery_accuracy"] for row in epoch_rows
    )
    prior_mean, _, _ = mean_ci95(row["root_prior_accuracy"] for row in epoch_rows)

    summary = {
        "method": METHOD,
        "dataset": "CelebA identity subset with saved FaceNet/VGGFace2 binary roots",
        "identities": int(n_identities),
        "gallery_templates": int(gallery.shape[0]),
        "probe_templates": int(probes.shape[0]),
        "root_bits": int(n_bits),
        "epochs": int(epochs),
        "seed": int(seed),
        "raw_rank1": raw["rank1"],
        "raw_rank5": raw["rank5"],
        "protected_rank1": first_protected["rank1"],
        "protected_rank5": first_protected["rank5"],
        "all_rekeys_exact": bool(all(row["rekey_exact"] for row in epoch_rows)),
        "all_epoch_rank1_equal_raw": bool(all(row["rank1"] == raw["rank1"] for row in epoch_rows)),
        "cross_epoch_auc_mean": auc_mean,
        "cross_epoch_auc_ci95": [auc_low, auc_high],
        "global_link_mean": global_mean,
        "global_link_ci95": [global_low, global_high],
        "relational_link_mean": relational_mean,
        "relational_link_ci95": [relational_low, relational_high],
        "global_link_chance": 1.0 / n_identities,
        "global_mask_pairwise_auc_mean": global_mask_auc_mean,
        "global_mask_pairwise_auc_ci95": [global_mask_auc_low, global_mask_auc_high],
        "global_mask_relational_link_mean": global_mask_rel_mean,
        "global_mask_relational_link_ci95": [global_mask_rel_low, global_mask_rel_high],
        "cross_key_rank1_mean": cross_mean,
        "cross_key_rank1_ci95": [cross_low, cross_high],
        "identification_chance": 1.0 / n_identities,
        "root_attack_mean": recovery_mean,
        "root_attack_ci95": [recovery_low, recovery_high],
        "root_prior_mean": prior_mean,
        "known_key_root_recovery": float(np.mean([row["known_key_root_recovery_control"] for row in epoch_rows])),
        "stable_template_auc_control": float(np.mean([row["stable_template_auc_control"] for row in epoch_rows])),
        "proactive_refresh_preserves_secret": refresh_preserves_secret,
        "same_epoch_three_share_recovery_fraction": static_exact_fraction,
        "cross_epoch_mixed_share_recovery_fraction": stale_exact_fraction,
        "claim_boundary": (
            "The experiment validates exact matching, re-key correctness, tested cross-epoch attacks, "
            "and proactive-share semantics. It does not replace a proof for the PRF, MPC, ORAM, "
            "secure-erasure, or active-adversary assumptions."
        ),
    }

    write_csv(output_dir / "msle_epoch_results.csv", epoch_rows)
    write_csv(output_dir / "msle_biometric_metrics.csv", [{
        "representation": "raw binary root",
        "rank1": raw["rank1"],
        "rank5": raw["rank5"],
    }, {
        "representation": "M-SLE candidate-conditioned protected matching",
        "rank1": first_protected["rank1"],
        "rank5": first_protected["rank5"],
    }])
    (output_dir / "msle_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    make_svg(output_dir / "msle_biometric_security.svg", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "analysis_journal_validation"
        / "celeba_128_binary_roots.npz",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "analysis_msle_tbiom",
    )
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260818)
    args = parser.parse_args()
    summary = run(args.input, args.output_dir, args.epochs, args.seed)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
