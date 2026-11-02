TBIOM-2026-08-0274: revision_v3 reproducibility guide, 2026-10-30

ENTRY POINTS
output/pdf/main.pdf: current article, 9 pages including references/biographies.
output/pdf/supplement.pdf: detailed protocols and evidence, 12 pages.
output/pdf/response_to_reviewers.pdf: numbered response to both reviewers, 6 pages.
REVIEWER_CLOSURE_V3_RU.txt: Russian reviewer-to-evidence map.
results/current_results.json: measured means, sample SD, repetitions, raw logs
and exact circuit hashes. CURRENT_RESULTS_RU.txt is generated from that evidence.
results/final_evidence_audit.json and results/pdf_visual_qa.json record checks
against the current PDFs. output/package_manifest.json records the final ZIP.
Nothing in this package has been submitted or published by this workflow.

LAYERS AND DIRECTORY STRUCTURE
The combined archive has root TBIOM_R1_v3/. It preserves the frozen original
and revision_v2 evidence in their original relative layout and adds revision_v3/.
The frozen revision_v2 ZIP SHA-256 is
eb0b7411fe238e3dd7c1728b3311d23f8cb78e7f6b7e68a0f2f52796185a587c.
Old notes, interrupted pilots and original outputs are historical evidence,
not alternative current results. In particular, use only *_corrected directories
for V3 ITQ/projection open-set outcomes. Closed-set outcomes were unaffected.
The old 30-bit-contribution/73-round timings are excluded from current claims.

SUMMARY-ONLY REPRODUCTION (NO BIOMETRIC DATA OR MPC RUN REQUIRED)
Use Python 3.12, from revision_v3:
  python build_v3_final_tables.py
  python update_response_v3.py
These read the released summaries/log rows plus the frozen revision_v2 TeX.
They regenerate generated_v3_results.tex, generated_v3_supplement.tex and the
point-by-point response/macros. They do not re-fit a model or re-run matching.
summarize_current.py intentionally updates the summary timestamp; exact source
table and response bytes, rather than that timestamp, are reproduction targets.
The archive fresh-extraction check is results/archive_reproduction_audit.json.
The internal audit requires pypdf and NumPy for its optional numeric self-test;
dependency versions and local build/install reports are retained.

FIGURE AND PDF REBUILD
plot_v3.py plots only frozen JSON evidence. It uses an isolated data/plot_libs
target (matplotlib 3.10.7, numpy 2.3.5); no model training/scoring occurs.
The original Windows build uses compile_v3_draft.ps1 with Tectonic and Poppler
and -RenderSubfolder final_qa. Machine-specific executable/cache paths at the
top of that script must be configured on another host. The script uses the
frozen revision_v2 cached TeX resources in the original local environment;
the shareable archive excludes those binaries/caches. Standard IEEEtran,
XeLaTeX-compatible fontspec, Times New Roman/Arial/Courier New and BibTeX are
an alternative on a configured TeX installation. Font/layout differences on
another system require a new visual inspection. All figures and author photos
needed by the paper are included.

BIOMETRIC RECONSTRUCTION AND FROZEN-MODEL EVALUATION
Face images, embeddings, binary-root arrays and transform matrices are excluded.
Obtain the public source datasets and model weights from their providers under
their access conditions. Source URLs, pinned revisions, image IDs, preprocessing
and SHA-256 values are in the inherited manifests and data/*json provenance.
The original LFW archive hash is
b47c8422c8cded889dc5a13418c4bc2abbda121092b3533a83306f90d900100a.
revision_v2/README_REPRODUCE.txt describes FaceNet/CelebA recovery. V3 SFace uses
prepare_sface_assets.py, run_sface.py and finish_sface.py. SFace/YuNet hashes,
OpenCV 4.11.0.86, deterministic detection fallback and image pairing are recorded.
Keep the supplied identity/image positions and all 20 assignments unchanged.
There are 128 query identities across nested galleries, not 4096 query people.

565 unused identities fit the centering/ITQ transforms. They are separate from
512 calibration, 512 unknown test identities and 3968 used distractors. Both
predefined projection seeds 20261030/20261031 and all widths/variants are retained.
Binary/projection protocols describe fitting; on a reconstruction, compare the
resulting transform and feature hashes before evaluating. Do not overwrite or
refit the existing local frozen model files as part of an evaluation rerun.
repair_frontend_thresholds.py reads those frozen models and outputs *_corrected.
calibration_numeric.py tests strict threshold ties and independent Hamming scores.
The corrected run exactly reproduces native float/sign open-set flags and all
closed-set flags; every calibration count is within the prescribed five or one.
run_frontend_confirmation.py checks paired transfer, identity-bootstrap intervals
and actual 512-bit secure inputs. It contains MPC phases: run it sequentially.

FULL MPC REPRODUCTION
MP-SPDZ commit 9d809599ea6ce627216a389ca7d984fbb75d0cb9, passive five-party
degree-two Shamir over p=2^128-3637247; statistical parameter 80. See
parameters.json, backend_config.json, protocol_v3.json and per-study protocols.
The local hardware was Intel i5-1135G7, four cores/eight threads, Windows/WSL.
The runtime path is configured by the inherited revision_v2 setup and
mpc_logs/runtime.json. Source/compiler/input hashes and commands accompany runs.
Configure a new runtime on another host; do not reuse someone else's shares.
The trusted initialization/controller is outside the computing-party model.

Never run MPC drivers concurrently: they share Player-Data/Persistence paths.
The current runners use runtime/.msle_v3_driver.lock. Heavy extraction, scoring,
plotting, compilation and PDF rendering also use that lock during measurements.
Old revision_v2 runners do not know this lock: run them only with all V3 jobs idle.
Suggested isolated fresh-run order (these are costly experiments, not audit steps):
  run_joint_ablation.py
  run_lazy_epoch.py
  run_aes_baseline.py
  run_poly_query.py, then run_vector_query.py
  run_lazy_persistence.py, then run_shared_query.py
  run_virtual_scale.py
  run_private_client.py
  repair_frontend_thresholds.py, then run_frontend_confirmation.py
  run_network_study.py
Read each study's frozen protocol/configuration before execution; runner gates
and append-only logs are intended for this original pipeline. For a fresh series,
use a separate output directory and preserve every warmup, diagnostic and failure.
Do not silently append new circuits/repetitions to the published comparison tags.

PRIVATE CLIENT, STORAGE AND NETWORK INTERPRETATION
Each client probe bit, threshold and independent fresh uniform output pad is
degree-two shared. Servers open only the padded result; no separate acceptance
or identity is opened by the private-client kernel. Honest bit inputs, private
channels and passive MPC are assumptions. DIAG oracle runs test correctness only.
Persisted trials reload each server's own state shares; cold-input scale/network
trials use a trusted protected-state input owner. These timing families are not
pooled. Virtual handles stay logically stable but all their shares are refreshed;
semantic locators/masks change. This is a distinct representation/update family.
Network RTT0/1/20/50ms uses task-owned loopback TCP relays. Echo medians, queues,
controller CPU, all party logs and bytes are retained. It is stream-delay
emulation on one host, with no imposed bandwidth/loss or physical WAN deployment.

CLAIM BOUNDARIES AND NEGATIVE RESULTS
The mask PRP is assumed; field width/round count alone do not prove 128-bit
composed security. Secret keys and hidden handles/index/labels/tie tags are
required. Fixed scans hide access addresses but do not yield sublinear search.
Full scan/fused/polynomial complete-query controls are all retained. ITQ and
compaction pilots include unfavorable outcomes. Larger code widths have no
measured 512-bit MPC cost equivalence. SFace changes encoder/alignment/coding
together and requires new features/enrollment; it is not a root-free frontend
upgrade. Open-set DIR must be read beside actual FPIR, not as an equal-FPIR gain.
Nominal paired intervals condition on the development images/pools/backbones.
No malicious-security, crash-recovery, replay-freshness, OS-erasure or broad
first-in-literature claim follows from these experiments.

ARCHIVE CONTENTS
Included: source, protocols, reference vectors, provenance, deidentified outcome
arrays, raw performance/correctness logs, manuscript sources, figures/photos,
current PDFs and a SHA-256 manifest for every member. Excluded: face images,
features/roots, transform arrays, weights, per-party inputs/state shares and
dependency/runtime binaries/caches. CRC and member hashes are verified when
package_v3.py runs. No external repository push or journal submission occurs.
