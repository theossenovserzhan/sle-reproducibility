TBIOM-2026-08-0274: corrected R1 experiments

The enclosing archive preserves the first-batch support modules one directory
above revision_v2. Keep that layout when extracting. All commands below run in
revision_v2 unless another directory is stated. This is research code, not a
production biometric service. No journal submission or remote publication is
performed by these scripts.

EVIDENCE MAP
manuscript_R1/: main, supplement and point-by-point response sources.
output/pdf/: checked document builds.
reviewer_evidence_matrix.csv: every numbered concern and its evidence/scope.
results/secure_summary.csv: input-inclusive computation reference, 19 groups.
results/persisted_state_summary.csv: actual per-party file loading, 8 groups.
results/compact_sort_summary.csv: optimized full-width sort baseline, 2 groups.
results/*runs.jsonl and logs/: all repetitions, correctness runs and raw logs.
results/lfw_extended/: closed/open-set, candidate/capacity and subject outcomes.
results/celeba*_paired/: distinct fixed and historical CelebA populations.
results/retained_lifecycle/: exactly reproduced historical SHAKE diagnostics.
runtime_provenance.json and runtime_source_hashes.json: actual MPC build/source.
source_history/ and legacy_reproduce/: prior source versions, not final timings.

QUICK REBUILD FROM INCLUDED OUTCOMES
Use Python 3.12 with NumPy. Face images, embeddings and an MPC installation are
not needed to regenerate tables from the supplied outcomes:
  python build_revision_results.py
Plot regeneration additionally needs matplotlib:
  python plot_revision.py
Compile from manuscript_R1 with a normal LaTeX installation:
  latexmk -pdf main.tex
  latexmk -pdf supplement.tex
  latexmk -pdf response_to_reviewers.tex
The supplied builds used Tectonic/XeTeX with Windows Times New Roman, Arial and
Courier New; pdflatex uses the IEEEtran fonts instead. IEEEtran.cls/.bst and the
standard amsmath, amssymb, amsthm, graphicx, booktabs, tabularx, float, cite,
iftex, url, hyperref and xspace packages are required.

FRESH EXPERIMENTS
Work in a separate extraction of this archive. First move results/ to a sibling
published_results/ directory and create an empty results/ directory. Retain
the published logs for comparison. This is essential: the secure batch resumes
completed runs and otherwise deliberately skips them. Never run two MPC drivers
against the same runtime concurrently: Player-Data/Persistence is shared.

1. Obtain the frozen published binary input:
  python prepare_frozen_input.py
or supply an existing copy with --source /path/to/celeba_128_binary_roots.npz.
The SHA-256 must be 96862a03...486f0db1 (full hash is in the script). This archive
does not redistribute biometric roots, faces, embeddings or model weights.
The loader URL is content-verified even if the public repository branch moves.

2. Install the recorded biometric environment in a dedicated Python 3.12 venv:
  python -m pip install -r requirements_biometric.txt
  python -m pip install --no-deps facenet-pytorch==2.6.0
The second step is intentional: facenet-pytorch 2.6.0's package metadata pins
older torch/torchvision/Pillow versions. The tested extraction used 2.8.0+cpu,
0.23.0+cpu and Pillow 12.3.0. CPU wheels of torch/torchvision may be selected
from their provider. Do not let dependency resolution silently downgrade this
recorded stack. environment_biometric.json records the observed environment;
transitive package versions not recorded there are not claimed fully pinned.

3. Re-extract LFW and recover the exact CelebA cohorts:
  (from the parent directory) python extract_float_features.py --dataset LFW
  python extract_lfw_extended.py
  python evaluate_lfw_extended.py
  python recover_celeba.py --phase labels
  python recover_celeba.py --phase extract
  python recover_celeba_external.py
  python audit_celeba_reproduction.py
Downloads require access to the original providers and their conditions.
The complete LFW funneled tar archive belongs at
../image_cache/lfw_home/lfw-funneled.tgz; expected SHA-256 is
b47c8422c8cded889dc5a13418c4bc2abbda121092b3533a83306f90d900100a.
The loader bypasses incomplete extraction/joblib caches. Do not run the older
CelebA filter-based download in extract_float_features.py; the corrected
recover_celeba scripts read selected ranges from the frozen Parquet revision.
First-time models are obtained by facenet-pytorch; the VGGFace2 checkpoint hash
is 281cebca8662831adb987a874bdcb36e73f5b1c6dc5ee5878f305e985625d99b.
The prospective extra-identity manifest must remain unchanged. N=256 secure
inputs are generated from real LFW embeddings by evaluate_lfw_extended.py.
The exact NPZ byte hash can depend on ZIP serialization/environment; compare
decoded bits, per-image/feature provenance and all historical ranks as well.

4. Reproduce the retained simulation:
  python legacy_reproduce/validate_masked_sle.py --input ../inputs/celeba_128_binary_roots.npz --output-dir results/retained_lifecycle --epochs 20 --seed 20260818
  python audit_retained_lifecycle.py
The only historical source correction avoids a materialized 16-GiB integer
range. The bounded version preserves the sampled sequence and all aggregates.

5. Build a separate MP-SPDZ checkout in Linux/WSL, outside temporary directories:
  git clone https://github.com/data61/MP-SPDZ.git /path/to/MP-SPDZ
  git -C /path/to/MP-SPDZ checkout 9d809599ea6ce627216a389ca7d984fbb75d0cb9
Use that frozen checkout's build instructions and dependencies. The measured
host used Ubuntu 24.04.4, g++ 13.3, GMP, OpenSSL, libsodium and Boost, and:
  make -j2 shamir-party.x CXX=g++ USE_KOS=1 GDEBUG=
  bash Scripts/setup-ssl.sh 5
Run both commands inside the checkout. build.log is included under the parent
mpc_logs/ directory. Python 3.12.3/NumPy 2.4.3 were used for orchestration.
Register it from revision_v2:
  python3 configure_runtime.py --runtime /path/to/MP-SPDZ
This verifies the revision when Git metadata exist and compares all 1095
regular tracked source files against the recorded normalized hashes. CRLF/LF
text differences and file modes are ignored; code changes are not ignored.
The binary hash is provenance, not a cross-machine build requirement.

6. Run sequentially from revision_v2 in Linux/WSL:
  OPENBLAS_NUM_THREADS=2 OMP_NUM_THREADS=2 python3 -m unittest test_reference.py
  python3 mpc_driver.py --phase primitives
  python3 run_secure_batch.py
  python3 persisted_driver.py --n 8 128 --repeats 3
The secure batch includes all eight faults, raw-root and private-index
controls, full-state checks, N=256 performance and the compact-sort comparator.
Set BLAS/OpenMP thread limits for every invocation. The persisted initializer
is a trusted external research fixture: each computing party receives one
degree-two Shamir evaluation per field. The fixture is outside the corruption
model. Later invocations read only their own share files, plus fresh keys or
query inputs. Local plaintext input/share/TLS files are not distributed here.

7. Regenerate and compare:
  python build_revision_results.py
The final builder refuses incomplete batches and filters current circuit,
parameter/backend hashes, diagnostic flag and warmup. It keeps all measured
repetitions; it does not select only the fastest. Final PDFs must be compiled
again after any regenerated table changes. Retrieval/calibration unit tests
also run from the parent directory: python -m unittest test_experiments.py.

INTERPRETATION
Input-inclusive and actual persisted-state timing families are separate. All
five parties share one host; time variability and largest-child RSS are shown.
Traffic phase counters are P0 traffic; global totals are identified separately.
The time model failed some held-out sizes and is not used to predict large
gallery latency. The 4096-gallery study is biometric utility, not measured MPC
scale. The private fixed-scan index is costly and gives no measured speedup.
Masking does not improve below-threshold sharing privacy over shared raw roots.
The extra snapshot claim requires secret mask keys and hidden metadata.
Logical commit/rollback is tested; distributed crash recovery, OS secure erasure
and a composable mobile-adversary proof are outside this prototype.

LICENSES
Public datasets, FaceNet weights and MP-SPDZ retain their providers' licenses.
No third-party runtime binaries or data are embedded in this archive. Frozen
predecessor/released code is retained for review with its original provenance;
this package does not silently assign new rights to that source.
