# Reproducing the 2 November 2026 M-SLE snapshot

`paper/` is the authoritative current manuscript. `experiments/` preserves
the relative layout of a frozen experiment archive. Historical manuscript
sources there support numerical reproduction; regenerating them does not
overwrite the current editorial source in `paper/`.

## Lightweight verification

From the repository root, install `requirements-validation.txt` and run:

```bash
python scripts/validate_artifact.py
python scripts/verify_msle_snapshot.py
```

The second command verifies every published experiment/paper hash against
`publication/manifest.json`, confirms that the twelve outcome archives
contain only uint8 0/1 flags, checks the current PDFs, and runs the independent
reference algebra and strict-threshold self-tests. It needs no images or MPC.

## Rebuild evidence tables

Work in a disposable copy: the generators intentionally rewrite their
historical manuscript outputs.

```bash
cd experiments/revision_v3
python build_v3_final_tables.py
```

This reads the frozen summaries, run logs and `revision_v2` table dependencies.
It does not refit a frontend or rerun recognition. The current paper has
subsequent wording and layout edits, while result numbers and table cells
remain the same. Do not replace `paper/` with generated historical drafts.

`summarize_current.py` updates timestamps. Timestamps are not a numerical
reproduction target. Only `*_corrected` ITQ/projection open-set results
support the current threshold claims.

## Biometric reconstruction and model evaluation

Follow the frozen [experiment instructions](../experiments/revision_v3/README_REPRODUCE_V3.txt)
and [reference instructions](../experiments/revision_v2/README_REPRODUCE.txt).
Obtain CelebA, LFW and model weights from their providers under their access
conditions. Keep the supplied selections, preprocessing, checksums and all
twenty assignments. The fixed and portability CelebA cohorts are distinct
and share one identity; do not pool their intervals.

Fitted transforms, embeddings, roots and images are intentionally absent.
Reconstruct them in an ignored local working area and verify the recorded
hashes. Both predefined projection seeds and all development variants remain
documented. A separate 512-identity calibration pool and 512 unknown test
identities support the current open-set comparisons.

## Full MPC runs

Install the pinned MP-SPDZ revision and configure a fresh local runtime.
Machine-specific paths in the frozen drivers must be adapted. Runtime,
Player-Data and persisted shares are not supplied. Never reuse another
party's private state.

Run drivers sequentially: they share runtime paths and use
`.msle_v3_driver.lock`. Follow the frozen instructions for persisted-state,
private-client, fused-query, virtual-representation, cipher and network-delay
experiments. These are costly runs, not lightweight validation. Five local
processes and stream-delay emulation are not physical WAN deployment.

## Compile the current paper

With an IEEEtran/BibTeX-capable LaTeX installation, from `paper/`:

```bash
latexmk -pdf main.tex
latexmk -pdf supplement.tex
```

The sources support PDFTeX and fontspec-based engines. Engine/font changes
can alter layout; the supplied manuscript PDF is the visually checked
9-page version, and the supplied supplement has 13 pages.

## Scope of the public subset

`publication/source_archive_manifest.json` records the original local
archive's hashes. `publication/manifest.json` identifies exactly which
members are published and why others are omitted. Editorial correspondence,
superseded PDFs and local progress notes are not redistributed.

Some historical full-archive/PDF audit scripts expect those intentionally
omitted author files. They are provenance, not the verifier for this public
subset. Use the top-level public-snapshot validators for the checkout.
Biometric datasets and third-party runtime binaries are never part of it.
