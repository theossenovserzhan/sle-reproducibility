# M-SLE: Re-Keyable Private Face Identification

Reproducibility materials for **Masked Synchronized Locator Evolution for
Re-Keyable Private Face Identification**, by Beibut Amirgaliyev and Serzhan
Ossenov. The current manuscript and public evidence snapshot are dated
**2 November 2026**. This repository does not claim that the manuscript has
been accepted or published.

## Start here

- [Current manuscript, PDF](paper/manuscript.pdf)
- [Supplementary material, PDF](paper/supplement.pdf)
- [LaTeX sources](paper/)
- [Current experiment summaries](experiments/revision_v3/results/current_results.json)
- [Detailed reproduction instructions](docs/REPRODUCE_MSLE.md)
- [Frozen experiment instructions](experiments/revision_v3/README_REPRODUCE_V3.txt)
- [Public-snapshot provenance and file hashes](publication/manifest.json)

The current construction checks both faithful renewal of enrolled binary
templates and consistency of their private index. It includes materialized
and virtual locator representations, private client input/output, persisted
shares, a conventional AES-CTR control, shared-root controls and complete
private-query measurements.

## Reading the evidence

| Question | Main evidence |
|---|---|
| Are both renewal checks necessary? | [Coupled mutation and missing-slot tests](experiments/revision_v3/results/joint_ablation_runs.jsonl) |
| What is the cost of a complete private query? | [Fused-query runs](experiments/revision_v3/results/private_fused_runs.jsonl), [summary](experiments/revision_v3/results/current_results.json) |
| Does virtual representation reduce complete renewal work? | [Persisted, scale and cipher comparisons](experiments/revision_v3/results/current_results.json) |
| How much utility does binarization lose? | [Paired frontend confirmation](experiments/revision_v3/results/frontend_confirmation/summary.json) |
| Are open-set thresholds numerically correct? | [Calibration audit](experiments/revision_v3/results/calibration_precision_audit.json), `*_corrected` result directories |
| What are the cryptographic parameters? | [Parameters](experiments/revision_v3/parameters.json), [backend](experiments/revision_v3/backend_config.json), [protocol](experiments/revision_v3/protocol_v3.json) |

Current secure measurements use five colocated passive Shamir parties,
degree-two sharing, the explicit prime `2^128 - 3637247`, and an 80-bit
statistical parameter. The concrete MiMC assumption is stated separately;
field size alone is not an unconditional security-level proof.

Complete 512-bit-root MPC runs extend to 1024 records. The separate biometric
study extends galleries to 4096 entries while retaining the same 128 query
identities. The index does **not** demonstrate a useful complete-query
speedup. Renewal savings must not be presented as search acceleration.

Use only the `*_corrected` ITQ/projection open-set outputs for current
claims. Less favorable development variants and earlier outputs remain for
provenance. The legacy 32-bit locator-core speedup is not a complete M-SLE
speedup and is not comparable to the current full-system timings.

## Repository layout

```text
paper/                       Current paper, supplement and their source dependencies
experiments/revision_v3/      Current experiment programs, manifests, logs and results
experiments/revision_v2/      Matched reference and reconstruction dependencies
publication/                 Public-snapshot manifest and original archive hashes
docs/REPRODUCE_MSLE.md        Reproduction guide for this public subset
Programs/, notebooks/,       Preserved legacy unmasked SLE artifact
scripts/, results/           Legacy tools/results plus current snapshot validators
```

The unmasked SLE implementation is an internal, unpublished baseline.
Legacy files are preserved for provenance, rather than presented as a
separate peer-reviewed contribution. The former top-level README and
citation metadata are preserved under `docs/LEGACY_*`.

## Verify the public snapshot without biometric data

With Python 3.12:

```bash
python -m pip install -r requirements-validation.txt
python scripts/validate_artifact.py
python scripts/verify_msle_snapshot.py
python scripts/build_checksums.py
```

These commands check source hashes, outcome-array schemas, current document
hashes, relative links and numerical primitive tests. They do not download
images, refit models or launch MPC benchmarks. See the reproduction guide
before running the resource-intensive experiments.

## Data and correspondence

No dataset face images, embeddings, biometric-root arrays, model weights,
learned transform matrices, epoch keys or private party state are included.
The narrowly allowed `subject_outcomes.npz` files contain only deidentified
0/1 classification outcomes for interval reproduction; their exact schemas
and hashes are checked. Dataset-selection metadata and public source-image
identifiers support reconstruction under the providers' access conditions.

Editorial correspondence, reviewer responses and superseded PDF exports
are excluded from this public snapshot. The current paper sources include
author biographies and portraits. See [data availability](DATA_AVAILABILITY.md).

## Citation and license

Use [CITATION.cff](CITATION.cff) for the software artifact. No paper DOI or
acceptance status is implied. The existing [license notice](LICENSE_NOTICE.md)
remains in effect; this update does not grant a new open-source license.
Third-party software retains its upstream license and is not vendored here.
