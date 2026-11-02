# Data availability

CelebA and LFW are available from their respective providers subject to their
terms of use. This repository does not redistribute raw face images,
floating-point face embeddings, or biometric-root archives.

The current snapshot is under `experiments/`, with source image selections,
preprocessing, hashes and provider revisions needed for reconstruction.
Current paper files are under `paper/`. No model weights, learned transform
arrays, epoch secrets or private party shares are included.

Twelve narrowly allowlisted `subject_outcomes.npz` files contain deidentified
uint8 flags (0 or 1) for Rank-1, Rank-5, unknown acceptance and correct accepted
identification. They contain no images, embeddings, biometric roots, keys or
person-name fields. Their exact schemas and hashes are recorded in
`publication/manifest.json` and checked by the public-snapshot verifier.

Author biographies and portraits are included as dependencies of the paper.
Editorial correspondence, reviewer responses and superseded PDF exports are
not included in this public snapshot. The original archive manifest and the
explicit list of omitted members preserve provenance without redistributing
those documents.

The `results/` directory contains aggregate measurements, summary tables,
figures without identifiable face samples, and protocol logs supporting the
reported findings. The notebooks document how the protected roots and
aggregate outputs are regenerated from provider-hosted datasets.

No permanent DOI or journal acceptance is asserted by this repository update.

