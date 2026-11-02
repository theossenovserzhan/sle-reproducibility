"""Integrate the completed evidence by topic; move historical timing detail out of main."""
from pathlib import Path
import json,re
import build_v3_tables as base

ROOT=Path(__file__).resolve().parent
TARGET=ROOT/"manuscript_v3"

def tables(text):
    result={}
    for match in re.finditer(r"\\begin\{table\}\[t\].*?\\end\{table\}",text,re.S):
        label=re.search(r"\\label\{([^}]+)\}",match[0]);assert label
        result[label[1]]=match[0]
    return result

def main():
    base.main()
    reference=(ROOT.parent/"revision_v2/manuscript_R1/generated_results.tex").read_text()
    generated=(TARGET/"generated_v3_results.tex").read_text()
    new=tables(generated);old=tables(reference)
    summary=json.loads((ROOT/"results/frontend_confirmation/summary.json").read_text())
    main=[reference[:reference.index(r"\begin{table}")].strip(),
          "On LFW, native FaceNet sign binarization loses0.420 percentage points at128 and1.641 points at4096 (paired95\\% interval at4096: $[-2.480,-0.850]$ points). Masking adds zero binary-domain score error; it does not recover frontend loss.",
          new["tab:v3frontend"]]
    figure=re.search(r"\\begin\{figure\*\}.*?\\end\{figure\*\}",reference,re.S)[0]
    if (TARGET/"figures/frontend_scale_v3.png").exists():
        figure=r'''\begin{figure*}[t]\centering\includegraphics[width=\textwidth]{figures/frontend_scale_v3.png}\caption{Paired utility with the same128 query identities across nested galleries. Both fixed SFace512-bit projection seeds are retained; the right panel compares them with native FaceNet512-bit signs. Intervals resample identities after averaging20 repeated assignments and are conditional on the frozen gallery/calibration pools.}\label{fig:paired_scale}\end{figure*}'''
    main.append(figure)
    main.append("At4096 entries, centered SFace512 projections give97.295\\% and96.895\\% Rank-1 for seeds20261030 and20261031, versus93.672\\% for FaceNet512 signs. Paired gains are3.623 points (95\\% interval $[1.729,5.449]$) and3.223 points ($[1.514,4.922]$). The two code instances are reported separately; their mean is not an ensemble prediction. The same frozen transforms give89.951\\%/90.381\\% on the main CelebA cohort and91.846\\%/91.768\\% on the historical cohort, compared with86.055\\%/85.146\\% FaceNet512 baselines respectively. Model, alignment and coding change together. No unseen-identity or isolated-hash improvement is inferred.")
    if "tab:v3open" in new:main.append(new["tab:v3open"])
    main.append("Actual test FPIR is reported beside DIR. The conservative rule gives1.758\\%/1.563\\% FPIR and85.44\\%/86.10\\% DIR for the two SFace512 seeds, compared with0.391\\% and46.33\\% for FaceNet512. This is not an equal-FPIR comparison. The original32-identity frequent-image pilot and all less favorable preprocessing variants remain in the supplement/artifact. We do not claim reliable performance at FPIR $10^{-3}$ from512 unknowns.")
    main.extend([r"\subsection{Retrieval and Complete Private Query}",old["tab:index"],
        "Four-bit buckets retrieve almost the whole gallery. At4096 entries, eight-bit buckets retrieve about29\\%, but require certified fallback on95.70\\% of probes. Their public capacity is72 versus138 required, so enrollment rejects or reconfigures. Certified selection agrees with exhaustive decisions for every evaluated probe. Both SFace512 codes also have near-one four-bit candidate fractions; no pruning speedup follows."])
    if "tab:v3privatequery" in new:main.append(new["tab:v3privatequery"])
    main.append("The exact polynomial index operator is faster than repeated full-field equality, but still adds work to the full matcher. Reusing already computed mismatch bits produces the same candidate flags without reading the index; full scan needs no candidate construction. The complete controls return the same identity/reject result from the same persisted state. Independent candidate-bit oracles cover mixed/no/all sets and a three-row gallery, preventing exhaustive fallback from concealing retrieval defects.")
    integrity=re.search(r"All eight injected faults.*?(?=\\subsection\{Complete Secure Cost\})",reference,re.S)[0].strip()
    integrity=integrity.replace("All eight injected faults","In the materialized reference, all eight injected faults",1)
    main.extend([r"\subsection{State Integrity and Linkage Diagnostics}",integrity,
        "A coupled mutation changes a root bit and moves its index occurrence into the corresponding new bucket. Relation-only checking accepts the wrong enrolled root at both tested sizes; full binding rejects it. Template-only checking misses an omitted occurrence. The virtual view excludes a stale-handle no-op from its rejection count. These witnesses concern application invariants under passive MPC, not malicious-protocol soundness.",
        r"\subsection{Complete Renewal and Simpler Controls}",new["tab:v3persisted"],new["tab:v3scale"],
        "The persisted-share comparison includes loading, old/new masks, full relation and binding checks, selection, complete-row shuffle, every-field share refresh and writes. Its fresh paired materialized control is27.81s at128, separate from the older reference batch. Larger-gallery cold-input runs use real LFW roots but a trusted protected-state input owner. These interfaces are not pooled. Timing, traffic, rounds and largest-party RSS are recorded; non-monotonic cross-size timings and variability do not establish a latency scaling law.",new["tab:v3cipher"],
        "AES-CTR passes three independent/MPC known-answer vectors and the same state checks. AES is faster in the smallest materialized case; the32-record virtual comparison favors MiMC in this arithmetic backend. Conventional encryption supports the useful lifecycle contract. Shared raw roots already protect below-threshold party views and remove mask costs. Complete matched raw-root and full-width compact-sort controls, phase breakdowns and original timing ranges are retained in the supplement. The old quadratic pointer join is not the main transition comparator."])
    network_path=ROOT/"results/network_status.json"
    if network_path.exists() and json.loads(network_path.read_text()).get("finished"):
        main.append("Task-local stream-delay tests separately examine added RTT0/1/20/50ms with echo calibration. Results are reported by tested size; all parties remain on one host, and the small64-bit rekey is not extrapolated to512-bit deployment. Relay queueing and controller CPU are disclosed with the complete measurements.")
    (TARGET/"generated_v3_results.tex").write_text(base.tidy("\n\n".join(main))+"\n")
    supplement=(TARGET/"generated_v3_supplement.tex").read_text()
    ci_rows=[]
    for cohort in summary["cohorts"]:
        for row in cohort["methods"]:
            if not row["method"].startswith("SFace_RP_centered_512_seed"):continue
            delta=row["delta_vs_FaceNet_sign512"];seed=row["method"].rsplit("seed",1)[1]
            label=cohort["cohort"].replace("_",r"\_")+"128"
            ci_rows.append([label,seed,f"{100*delta['mean']:.3f}",f"$[{100*delta['ci95'][0]:.3f},{100*delta['ci95'][1]:.3f}]$"])
    for row in summary["extended_paired"]:
        if row["n_gallery"]!=4096 or "centered" not in row["method"]:continue
        delta=row["rank1_delta"];seed=row["method"].rsplit("seed",1)[1]
        ci_rows.append(["LFW4096",seed,f"{100*delta['mean']:.3f}",f"$[{100*delta['ci95'][0]:.3f},{100*delta['ci95'][1]:.3f}]$"])
    supplement+="\n"+base.table("SFace512 minus FaceNet512 Rank-1, percentage points. Nominal identity-bootstrap intervals,128 units after averaging20 splits; conditional on the selected images. Both seeds and the near-zero LFW128 difference are shown. Development/multiple comparisons limit confirmatory interpretation.","tab:v3pairedCI","llrr","Cohort & Seed & Delta(pp) &95\\%CI(pp)",ci_rows)
    supplement+=r'''
\section{Virtual-State and Private-Client Interfaces}
Distinct secret handles preserve a complete root/index relation under an injective semantic-locator map. The accepted virtual transition changes keys and protected templates, then shuffles complete rows and refreshes every share, while logical handles remain stable. Thus it is not physical replacement of every logical reference. Hiding handles, index contents, labels and tie tags is essential. Proposed templates are checked against both the old/new mask equation and the proposed decoded root/index relation; challenges follow candidate fixation.

For client input, each bit, threshold and fresh output pad uses independently sampled degree-two coefficients. The five evaluations are privately input and interpolated inside MPC using weights $(5,-10,10,-5,1)$. Any two original evaluations are independent of the secret constant. Only $M=y+R\pmod p$ is opened, for identity/reject encoding $y$ and uniform fresh pad $R$. For any fixed $y$, $M$ is uniform; the client knows $R$ and recovers $y$. There is no separate acceptance opening. This is a standard pad/MPC composition with honest binary input and private-channel assumptions. The benchmark controller acts as the external trusted client; it knows the probes/pads/reference answers and is not a computing-server corruption. Diagnostic oracle inputs are excluded from production privacy claims.

Exact polynomial lookup uses the Lagrange basis on the distinct valid handle support; invalid slots are suppressed by zero validity flags. Secret bucket selection still scans every padded slot. Its preconditions are a valid stored relation, distinct handles and bit-valued inputs, rather than malicious input validation. Candidate bits are checked against independent full-field equality. In a complete matcher the same flags equal the OR of exact block matches already available from Hamming mismatches; a full exact scan is the stronger minimal control. All metadata addresses remain public fixed scans.

\section{Retained Reference Timing Controls}
The following matched reference-batch results retain shared-root, materialized-mask and compact full-field sort controls. They are not pooled with the fresh virtual or private-client timing series. Their complete source/config/input hashes and raw logs identify the configuration. Root confidentiality below threshold already holds for shared roots; extra masking addresses only the stated separate value-exposure view.
'''
    for label in ("tab:secure","tab:persisted","tab:baselines"):supplement+="\n"+old[label]+"\n"
    evidence=json.loads((ROOT/"results/current_results.json").read_text())
    resources=[]
    for family,interface in (("persisted_rekey","Persisted rekey"),("larger_real_gallery","Cold"),("private_output_full_query","Private client")):
        for row in evidence["comparisons"][family]:
            if family=="persisted_rekey":view="Materialized" if row["method"]=="eager" else "Virtual";operation="Rekey"
            elif family=="larger_real_gallery":view="Materialized" if row["locator_representation"].startswith("materialized") else "Virtual";operation="Rekey" if row["mode"]==1 else "Query"
            else:view="Fused" if row["method"]=="fused" else "Full scan" if row["mode"]==2 else "Polynomial";operation="Query"
            memory=row["max_rss_single_child_kib"]
            resources.append([interface,str(row["n"]),operation,view,f"{row['party0_rounds']['mean']:.0f}",f"${memory['mean']/1024:.2f}\\pm{memory['sd']/1024:.2f}$"])
    supplement+="\n"+r"\section{Resources for the New Complete-System Comparisons}"+"\n"+base.table("Mean party-zero rounds and largest single-party peak RSS (MiB, mean/sample SD). Five measured persisted/client trials and three cold-input trials. Peak memory is not an aggregate over five parties; all per-run VM/wall times and phase traffic remain in the artifact.","tab:v3resources","lrllrr","Interface & $N$ & Operation & View & Rounds & Peak RSS",resources)
    network=evidence["comparisons"].get("network_delay",[])
    if network:
        network_rows=[]
        for row in sorted(network,key=lambda x:(x["n"],x["requested_added_rtt_ms"],x["locator_representation"])):
            if row["repetitions"]<3:continue
            network_rows.append([str(row["n"])+"/"+str(row["root_bits"]),str(row["requested_added_rtt_ms"]),"Materialized" if row["locator_representation"].startswith("materialized") else "Virtual",base.timing(row),f"{row['global_communication_mb']['mean']:.3f}"])
        supplement+="\n"+base.table("User-space stream-delay sensitivity: one warmup plus3 alternating measured trials. N2D64 is rekey; N8D512 is query. Requested added RTT, mean/SD VM time and global MB. Sizes and operations must not be pooled or extrapolated.","tab:v3network","rllrr","$N/d$ & RTT(ms) & View & Seconds & MB",network_rows)
        audit=evidence["network_audit"]
        supplement+="\nEcho-calibration medians in milliseconds (target: observed): "+"; ".join(f"{target}: {cal['echo_median_ms']:.3f}" for target,cal in audit["calibrations"].items())+f". All20 echo samples per target, relay CPU, queue high-water marks and per-party logs are retained. Total buffer backpressure events: {audit['backpressure_events']}; maximum direction queue: {audit['maximum_direction_queue_bytes']} bytes. Every peer connection uses a task-owned loopback relay; no global network settings are changed. This models stream delay, not packet loss, physical separation or an imposed WAN bandwidth.\n"
    (TARGET/"generated_v3_supplement.tex").write_text(base.tidy(supplement))
    main_path=TARGET/"main.tex";text=main_path.read_text()
    text=re.sub(r"The following retained reference results.*?\\input\{generated_results\.tex\}\s*\\input\{generated_v3_results\.tex\}",lambda _:r"\input{generated_v3_results.tex}",text,flags=re.S)
    main_path.write_text(text)
    print("V3_RESULTS_INTEGRATED_BY_TOPIC; original matched controls retained in supplement")

if __name__=="__main__":main()
