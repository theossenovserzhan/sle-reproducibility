"""Build paper tables from frozen evidence, excluding superseded MPC sources."""
from pathlib import Path
from collections import defaultdict
import argparse
import csv
import hashlib
import json
import statistics
import math

import numpy as np

ROOT=Path(__file__).resolve().parent
PAPER=ROOT/"manuscript_R1"

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def write_csv(path,rows):
    if not rows:
        Path(path).write_text("",encoding="utf-8")
        return
    with Path(path).open("w",newline="",encoding="utf-8") as stream:
        out=csv.DictWriter(stream,fieldnames=list(rows[0]));out.writeheader();out.writerows(rows)
def tex_table(caption,label,columns,header,rows):
    return "\n".join([r"\begin{table}[t]",r"\caption{"+caption+"}",r"\label{"+label+r"}\centering\small",
        r"\setlength{\tabcolsep}{3pt}",r"\begin{tabular}{"+columns+"}",r"\toprule",header+r" \\",r"\midrule",
        *[" & ".join(map(str,row))+r" \\" for row in rows],r"\bottomrule",r"\end{tabular}",r"\end{table}"])

def aggregate():
    hashes={"circuit_sha256":sha(ROOT/"mpc/msle_system.mpc"),"parameters_sha256":sha(ROOT/"parameters.json"),"backend_sha256":sha(ROOT/"backend_config.json")}
    all_runs=[json.loads(line) for line in (ROOT/"results/system_runs.jsonl").read_text().splitlines()]
    selected=[r for r in all_runs if all(r.get(k)==v for k,v in hashes.items())]
    final=[r for r in selected if r["tag"]=="performance" and r["diag"]==0 and not r["warmup"]]
    groups=defaultdict(list)
    for row in final:groups[(row["n"],row["mode"],row["protection"],row["transition"])].append(row)
    output=[]
    for key,rows in sorted(groups.items()):
        n,mode,protection,transition=key
        # A batch can be resumed; preserve all observations rather than silently
        # cherry-picking the fastest repetitions with the same repeat number.
        out={"n":n,"mode":mode,"protection":protection,"transition":transition,"repetitions":len(rows),**hashes}
        fields=["full_vm_seconds","wall_seconds","global_communication_mb","party0_rounds","max_rss_single_child_kib"]
        fields += [f"timer{t}_{suffix}" for t in (30,11,12,13,14,15,16,20,21,22,23) for suffix in ("seconds","party0_mb")]
        for field in fields:
            values=[r[field] for r in rows if r.get(field) is not None]
            for suffix,func in (("mean",statistics.mean),("median",statistics.median),("min",min),("max",max)):
                out[field+"_"+suffix]=float(func(values)) if values else None
            out[field+"_std"]=float(statistics.stdev(values)) if len(values)>1 else (0. if values else None)
        for field in ("index_slots","capacity","persistent_state_field_elements_per_party","logical_state_share_bytes_128bit_field_per_party"):
            assert len({r[field] for r in rows})==1
            out[field]=rows[0][field]
        output.append(out)
    write_csv(ROOT/"results/secure_summary.csv",output)
    return hashes,selected,output

def aggregate_additional_families():
    output={}
    for family,filename,source,hash_field in (
        ("persisted_state","persisted_runs.jsonl","msle_persistent_system.mpc","source_sha256"),
        ("compact_sort","compact_sort_runs.jsonl","msle_compact_sort_system.mpc","circuit_sha256")):
        path=ROOT/"results"/filename
        rows=[json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        rows=[r for r in rows if r.get(hash_field)==sha(ROOT/"mpc"/source) and r.get("parameters_sha256")==sha(ROOT/"parameters.json") and r.get("backend_sha256")==sha(ROOT/"backend_config.json") and r["tag"]=="performance" and not r["warmup"] and r["diag"]==0]
        if family=="compact_sort":rows=[r for r in rows if r.get("extra_config_sha256")==sha(ROOT/"compact_baseline_config.json")]
        groups=defaultdict(list)
        for r in rows:groups[(r["n"],r["mode"],r["protection"])].append(r)
        summary=[]
        for (n,mode,protection),measurements in sorted(groups.items()):
            state_fields=measurements[0].get("state_fields",measurements[0].get("persistent_state_field_elements_per_party"))
            row={"family":family,"n":n,"mode":mode,"protection":protection,"repetitions":len(measurements),"circuit_sha256":sha(ROOT/"mpc"/source),"state_fields":state_fields,"state_payload_bytes_per_party":16*state_fields}
            fields=["full_vm_seconds","wall_seconds","global_communication_mb","party0_rounds","max_rss_single_child_kib"]
            fields += [f"timer{t}_{suffix}" for t in (30,31,11,12,13,14,15,16,20,21,22,23) for suffix in ("seconds","party0_mb")]
            for field in fields:
                values=[r[field] for r in measurements if r.get(field) is not None]
                for suffix,fn in (("mean",statistics.mean),("median",statistics.median),("min",min),("max",max)):
                    row[field+"_"+suffix]=float(fn(values)) if values else None
                row[field+"_std"]=float(statistics.stdev(values)) if len(values)>1 else (0. if values else None)
            summary.append(row)
        write_csv(ROOT/"results"/(family+"_summary.csv"),summary)
        output[family]=summary
    return output

def cost_models(summary):
    validation=[]
    for mode in (1,2):
        rows={r["n"]:r for r in summary if r["mode"]==mode and r["protection"]==0 and r["transition"]==0 and r["repetitions"]>=3}
        if not all(n in rows for n in (8,16,32)):continue
        unit=lambda row:row["persistent_state_field_elements_per_party"] if mode==1 else row["n"]
        x=np.asarray([[1.,unit(rows[n])] for n in (8,16,32)])
        for metric in ("full_vm_seconds_mean","global_communication_mb_mean"):
            y=np.asarray([rows[n][metric] for n in (8,16,32)])
            coef=np.linalg.lstsq(x,y,rcond=None)[0]
            for n in (64,128,256):
                if n not in rows:continue
                predicted=float(np.asarray([1.,unit(rows[n])])@coef)
                actual=rows[n][metric]
                validation.append({"mode":mode,"metric":metric,"training_n":"8,16,32","held_out_n":n,
                    "feature":"logical_state_fields" if mode==1 else "gallery_n","intercept":float(coef[0]),"slope":float(coef[1]),
                    "predicted":predicted,"measured":actual,"relative_error":abs(predicted-actual)/actual,
                    "model_scope":"input-inclusive local fixed-scan reference; excludes persisted-file loading; held-out validation, no runtime extrapolation claim"})
    write_csv(ROOT/"results/cost_model_validation.csv",validation)
    return validation

def projected_traffic(validation):
    output=[]
    for mode in (1,2):
        rows=[r for r in validation if r["mode"]==mode and r["metric"]=="global_communication_mb_mean"]
        if not rows or max(r["held_out_n"] for r in rows)<128 or max(r["relative_error"] for r in rows)>.05:continue
        fit=rows[0]
        for n in (1024,4096):
            c=min(n,8+math.ceil(n/4));m=128*16*c;s=n*515+2*m+9
            unit=s if mode==1 else n
            output.append({"mode":mode,"n":n,"capacity":c,"index_slots":m,"logical_state_fields":s,
                "projected_global_mb":fit["intercept"]+fit["slope"]*unit,
                "max_held_out_relative_error":max(r["relative_error"] for r in rows),
                "measurement_status":"projection only, not executed; no runtime prediction", "assumption":"input-inclusive reference only; same field, padding, protocol and batch schedule; out-of-range model uncertainty remains"})
    write_csv(ROOT/"results/communication_projections.csv",output)
    return output

def main(draft=False):
    bio=read(ROOT/"results/lfw_extended/summary.json")
    batch=read(ROOT/"results/secure_batch_status.json")
    if not draft and (batch.get("finished_utc") is None or batch.get("last_error")):
        raise RuntimeError("Secure batch incomplete; use --draft only for internal layout checks")
    hashes,selected,secure=aggregate()
    additional=aggregate_additional_families()
    persisted=additional["persisted_state"]
    compact=additional["compact_sort"]
    if not draft:
        if not read(ROOT/"results/persisted_status.json").get("finished"):raise RuntimeError("Persisted lifecycle incomplete")
        if not read(ROOT/"results/compact_status.json").get("finished"):raise RuntimeError("Compact comparator incomplete")
        required_cold={(n,m,0,0) for n in (8,16,32,64,128,256) for m in (1,2)}|{(n,m,1,0) for n in (8,32,128) for m in (1,2)}|{(8,3,0,0)}
        actual_cold={(r["n"],r["mode"],r["protection"],r["transition"]) for r in secure if r["repetitions"]>=3}
        required_persisted={(n,m,p) for n in (8,128) for m in (1,2) for p in (0,1)}
        actual_persisted={(r["n"],r["mode"],r["protection"]) for r in persisted if r["repetitions"]>=3}
        actual_compact={r["n"] for r in compact if r["repetitions"]>=3}
        if not required_cold<=actual_cold or not required_persisted<=actual_persisted or not {8,16}<=actual_compact:
            raise RuntimeError("Final evidence table is missing required repetitions for a current source version")
    model=cost_models(secure)
    projections=projected_traffic(model)
    indexed=list(csv.DictReader((ROOT/"results/lfw_extended/index_frozen_split.csv").open()))
    fixed_celeba_path=ROOT/"results/celeba_paired/paired_summary.json"
    fixed_celeba=read(fixed_celeba_path) if fixed_celeba_path.exists() else None
    external_celeba_path=ROOT/"results/celeba_external_paired/paired_summary.json"
    external_celeba=read(external_celeba_path) if external_celeba_path.exists() else None
    celeba=external_celeba or fixed_celeba
    if not draft and external_celeba is None:raise RuntimeError("Distinct historical CelebA cohort recovery must finish before final build")
    lines=[r"\subsection{Binary Exactness and Frontend Loss}",
        "On the frozen CelebA roots, all 1,310,720 tested re-keyed bits and 1,310,720 protected probe/gallery scores agree with their reference across 20 epochs. This is exactness relative to the binary frontend."]
    if celeba:
        c=celeba["paired"]["rank1"]
        cohort="historical portability cohort" if external_celeba else "fixed cohort (new resplits)"
        lines += [f"On the exactly recovered fixed CelebA gallery/probe images, float Rank-1/Rank-5 are 0.8691/0.9473, versus binary 0.8516/0.9375. Twenty paired splits on the {cohort} give mean float/binary Rank-1 {c['float_mean']:.4f}/{c['binary_mean']:.4f}. The paired binary-minus-float difference is {100*c['binary_minus_float']:.3f} percentage points (identity-bootstrap 95\\% interval [{100*c['subject_bootstrap_ci95'][0]:.3f}, {100*c['subject_bootstrap_ci95'][1]:.3f}]). The supplement states the historical reproduction outcome."]
    lines += [tex_table("Paired LFW closed-set utility over 20 splits. The same 128 identities supply probes at every gallery size.","tab:utility","rrrrr",r"Gallery & Float R1 & Binary R1 & Float R5 & Binary R5",
        [[r["n_gallery"],f"{r['float_rank1']:.4f}",f"{r['binary_rank1']:.4f}",f"{r['float_rank5']:.4f}",f"{r['binary_rank5']:.4f}"] for r in bio["closed_set"]])]
    if (PAPER/"figures/lfw_paired_scale.png").exists():
        lines += [r"\begin{figure*}[t]\centering\includegraphics[width=\textwidth]{figures/lfw_paired_scale.png}\caption{Paired utility on nested LFW galleries, using the same 128 query identities and 20 gallery/probe assignments. Additional gallery identities are distractors. Intervals resample query identities after averaging repeated contexts; these are not 4096 independent query subjects.}\label{fig:paired_scale}\end{figure*}"]
    first,last=bio["closed_set"][0],bio["closed_set"][-1]
    gap=last["binary_minus_float_rank1"]
    lines += [f"At 128 identities, binarization costs {100*(first['float_rank1']-first['binary_rank1']):.3f} percentage points in Rank-1. At 4096, the loss is {100*(-gap['mean']):.3f} points (binary-minus-float 95\\% interval [{100*gap['ci95'][0]:.3f}, {100*gap['ci95'][1]:.3f}]). Masking adds no further score error, but it does not recover this frontend loss.",
        r"\subsection{Unenrolled Probes and Candidate Behavior}"]
    open_rows=[]
    for row in bio["open_set"]:
        if row["n_gallery"] not in (128,4096):continue
        open_rows.append([row["n_gallery"],"Float" if row["representation"]=="float_cosine" else "Binary","Emp." if row["rule"]=="empirical" else "Cons.",f"{100*row['test_fpir']['mean']:.3f}",f"{100*row['test_dir']['mean']:.2f}"])
    lines += [tex_table("Fresh-unknown LFW test: 512 calibration and 512 disjoint unknown identities. FPIR and DIR are percentages; rules are defined before feature extraction.","tab:open","rlrrr",r"Gallery & Root & Rule & FPIR & DIR",open_rows),
        "The nominal 1\\% empirical calibration rule does not guarantee 1\\% test FPIR. Conservative thresholds reduce false positives at a substantial DIR cost (Table~\\ref{tab:open}). Identity-level intervals and all intermediate gallery sizes are retained in the supplement. The earlier 32-identity frequent-image pilot has test FPIR 5.34\\% (float) and 7.19\\% (binary) at its nominal 1\\% target. This distinct hard population is not replaced or pooled with the confirmation cohort."]
    index_small=[r for r in indexed if int(r["n_gallery"]) in (128,4096)]
    lines += [tex_table("Unbounded candidate union on one frozen LFW split. Capacity-failing rows are diagnostics, not admitted secure indices.","tab:index","rrrrrr",r"Gallery & $w$ & Recall & Agreement & Fraction & Fallback",
        [[r["n_gallery"],r["block_bits"],f"{float(r['candidate_recall']):.4f}",f"{float(r['exhaustive_decision_agreement']):.4f}",f"{float(r['candidate_fraction']):.4f}",f"{float(r['certified_fallback_rate']):.4f}"] for r in index_small]),
        "Four-bit buckets retrieve almost the complete gallery. At 4096 identities, eight-bit buckets retrieve about 29\\%, but the exactness certificate invokes fallback on 95.70\\% of probes. Their public capacity is 72 versus a required 138, with 59 overflowing buckets; enrollment must reject or reconfigure. The certified policy agrees with exhaustive decisions for every evaluated probe. The secure reference hides its choice by computing the full schedule, so candidate pruning is not a measured speedup.",
        r"\subsection{Relation Integrity and Leakage Diagnostics}",
        "All eight injected faults are rejected, the previous logical state is retained, and the post-rejection query agrees with the independent oracle. Primitive tests also agree at full field width. In the retained SHAKE simulation, direct linkage AUC is 0.4948, direct assignment 0.0066 and relational assignment 0.0082, against chance 1/128 for assignment; the global-mask relational control is 1.0000. These are attack-specific observations, not an exposed-key or general irreversibility proof.",
        r"\subsection{Complete Secure Cost}"]
    good=[r for r in secure if r["protection"]==0 and r["transition"]==0 and r["mode"] in (1,2) and r["repetitions"]>=3]
    rows=[]
    for r in good:
        rows.append([r["n"],"Re-key" if r["mode"]==1 else "Query",f"{r['full_vm_seconds_mean']:.2f}$\\pm${r['full_vm_seconds_std']:.2f}",f"{r['global_communication_mb_mean']:.1f}",f"{r['max_rss_single_child_kib_max']/1024:.1f}"])
    if rows:lines += [tex_table("Input-inclusive five-party masked-system reference: mean and sample SD of three VM timings, global traffic (MB) and largest-child peak RSS (MiB). Five colocated processes; no WAN claim.","tab:secure","rlrrr",r"$N$ & Operation & Seconds & MB & RSS",rows)]
    stored_rows=[]
    for r in persisted:
        if r["repetitions"]<3:continue
        stored_rows.append([r["n"],"Masked" if r["protection"]==0 else "Shared root","Re-key" if r["mode"]==1 else "Query",f"{r['full_vm_seconds_mean']:.2f}$\\pm${r['full_vm_seconds_std']:.2f}",f"{r['global_communication_mb_mean']:.1f}"])
    if stored_rows:
        lines += [tex_table("Complete lifecycle from each party's own persisted share file. Mean and sample SD of three measured VM timings; global MB. No plaintext database/index or old keys are resupplied to a computing party.","tab:persisted","rllrr",r"$N$ & State & Operation & Seconds & MB",stored_rows),
            "The persisted-state implementation loads the complete public-size bundle before computing. Its helper functions and transition/query tail are source-identical to the input-inclusive reference; only the state entry point differs. Initialization uses an external trusted fixture that sends each party one degree-two Shamir evaluation per field. Repeated re-keying and reload queries agree with the oracle; exact/reject controls and rollback followed by reload also pass. The fixture is outside the computing-party corruption model."]
    n128={r["mode"]:r for r in good if r["n"]==128}
    if n128:
        state=next(iter(n128.values()))
        lines += [f"At $N=128$, logical masked state is {state['logical_state_share_bytes_128bit_field_per_party']/1048576:.3f} MiB per party before serialization. Phase timers separate locator/index evolution, old/new masks, verification, selection, shuffle/refresh and fresh query masks; the supplement gives all components and wall times."]
    comparisons=[]
    for r in secure:
        if r["repetitions"]<3 or (r["protection"]==0 and r["transition"]==0 and r["mode"]!=3):continue
        name="Raw roots" if r["protection"] else ("Sort/merge" if r["transition"] else "Private index")
        comparisons.append([r["n"],name,"Re-key" if r["mode"]==1 else "Query",f"{r['full_vm_seconds_mean']:.2f}$\\pm${r['full_vm_seconds_std']:.2f}",f"{r['global_communication_mb_mean']:.1f}"])
    for r in compact:
        if r["repetitions"]>=3:
            comparisons.append([r["n"],"Compact sort","Re-key",f"{r['full_vm_seconds_mean']:.2f}$\\pm${r['full_vm_seconds_std']:.2f}",f"{r['global_communication_mb_mean']:.1f}"])
    if comparisons:lines += [tex_table("Input-inclusive same-configuration baselines and private indexed-query reference. Three measured runs after warmup; mean and sample SD. Full phase details accompany the logs.","tab:baselines","rllrr",r"$N$ & Design & Operation & Seconds & MB",comparisons)]
    if model:
        errors=[r["relative_error"] for r in model if r["metric"]=="global_communication_mb_mean"]
        time_errors=[r["relative_error"] for r in model if r["metric"]=="full_vm_seconds_mean"]
        lines += [f"An input-inclusive cost model fitted only at $N=8,16,32$ is checked on held-out measured sizes. Maximum relative error is {100*max(errors):.1f}\\% for global communication and {100*max(time_errors):.1f}\\% for local VM time. Exact residuals are reported even when the model is inaccurate; we make no extrapolated runtime claim at 4096. This model excludes persisted-file loading. The biometric 4096-gallery study is separate from measured MPC scale."]
    if draft:lines.insert(0,r"\noindent\textbf{Internal layout draft: the secure batch or CelebA recovery is still running.}")
    (PAPER/"generated_results.tex").write_text("\n\n".join(lines)+"\n",encoding="utf-8")
    supp=[r"\subsection{Complete Repetition and Phase Tables}"]
    loaded_phases=[]
    for r in persisted:
        if r["repetitions"]<3:continue
        for timer,phase in ((31,"Read own shares"),(12,"Locator/index"),(13,"Old/new masks"),(14,"Verification"),(15,"Selection"),(16,"Shuffle/refresh/write"),(21,"Fresh query masks"),(22,"Hamming/ArgMin")):
            value=r.get(f"timer{timer}_seconds_mean")
            if value is None:continue
            loaded_phases.append([r["n"],"Masked" if r["protection"]==0 else "Raw",r["mode"],phase,f"{value:.3f}",f"{r[f'timer{timer}_party0_mb_mean']:.3f}"])
    for start in range(0,len(loaded_phases),24):
        supp += [tex_table("Persisted-state phase means. Read/write executes on all five local share files; traffic is party-zero MB. Mode1 re-keys, mode2 queries.",f"tab:persisted_phases{start}","rlrlrr",r"$N$ & State & Mode & Phase & Seconds & P0 MB",loaded_phases[start:start+24])]
    if persisted:
        supp += [tex_table("Persisted-state memory and launcher-inclusive timing; largest-child RSS is not aggregate memory.","tab:persisted_memory","rlrrrr",r"$N$ & State & Mode & Wall s & Peak RSS MiB & State MiB",[[r["n"],"Masked" if r["protection"]==0 else "Raw",r["mode"],f"{r['wall_seconds_mean']:.3f}",f"{r['max_rss_single_child_kib_max']/1024:.2f}",f"{r['state_payload_bytes_per_party']/1048576:.3f}"] for r in persisted if r["repetitions"]>=3])]
    if compact:
        supp += [tex_table("Valid-compacted full-width sort/merge: repetition range, wall time and memory. Three measured runs after a warmup; input-inclusive family.","tab:compact_memory","rrrrrr",r"$N$ & Wall s & VM range s & Rounds & Peak RSS MiB & State MiB",[[r["n"],f"{r['wall_seconds_mean']:.2f}",f"{r['full_vm_seconds_min']:.2f}--{r['full_vm_seconds_max']:.2f}",int(r["party0_rounds_mean"]),f"{r['max_rss_single_child_kib_max']/1024:.2f}",f"{r['state_payload_bytes_per_party']/1048576:.3f}"] for r in compact if r["repetitions"]>=3])]
        compact_phases=[]
        for r in compact:
            if r["repetitions"]<3:continue
            for timer,phase in ((12,"Compact/sort/translate/restore"),(13,"Old/new masks"),(14,"Verification"),(15,"Selection"),(16,"Shuffle/refresh/write")):
                value=r.get(f"timer{timer}_seconds_mean")
                if value is not None:compact_phases.append([r["n"],phase,f"{value:.3f}",f"{r[f'timer{timer}_party0_mb_mean']:.3f}"])
        supp += [tex_table("Valid-compacted sort/merge phase means; traffic is party-zero MB.","tab:compact_phases","rlrr",r"$N$ & Phase & Seconds & P0 MB",compact_phases)]
    perfrows=[]
    for r in secure:
        if r["repetitions"]<3:continue
        name="Raw" if r["protection"] else ("Sort" if r["transition"] else "Masked")
        op={1:"Re-key",2:"Query",3:"Indexed query"}.get(r["mode"],str(r["mode"]))
        perfrows.append([r["n"],name,op,r["repetitions"],f"{r['wall_seconds_mean']:.2f}",f"{r['full_vm_seconds_min']:.2f}--{r['full_vm_seconds_max']:.2f}",int(r["party0_rounds_mean"]),f"{r['logical_state_share_bytes_128bit_field_per_party']/1048576:.3f}"])
    supp += [tex_table("Repetition range, launcher-inclusive mean wall time, party-zero rounds and nominal persistent state per party. Runtime tables use MB as printed by MP-SPDZ.","tab:supp_perf","rllrrrrr",r"$N$ & Design & Operation & Runs & Wall s & VM range s & Rounds & State MiB",perfrows)]
    phase_rows=[]
    for r in secure:
        if r["n"] not in (8,128,256) or r["repetitions"]<3:continue
        name="Raw" if r["protection"] else ("Sort" if r["transition"] else "Masked")
        for timer,phase in ((12,"Locators/index"),(13,"Old/new masks"),(14,"Verification"),(15,"Selection"),(16,"Shuffle/refresh/write"),(21,"Fresh query masks"),(22,"Hamming/ArgMin"),(23,"Private candidate retrieval")):
            value=r.get(f"timer{timer}_seconds_mean")
            if value is None:continue
            phase_rows.append([r["n"],name,r["mode"],phase,f"{value:.3f}",f"{r[f'timer{timer}_party0_mb_mean']:.3f}"])
    # Split to avoid a single oversized one-column float.
    for i in range(0,len(phase_rows),24):
        supp += [tex_table("Phase means; communication is party-zero traffic, not global traffic. Mode 1 is re-key, 2 full-scan query, 3 private indexed query.",f"tab:phases{i}","rlrlrr",r"$N$ & Design & Mode & Phase & Seconds & P0 MB",phase_rows[i:i+24])]
    if model:supp += [tex_table("Input-inclusive held-out cost-model validation. Training sizes are always 8,16,32. No held-out result is refitted; persisted-file loading is outside this model.","tab:model","rlrrrr",r"Mode & Metric & Held-out $N$ & Predicted & Measured & Error (\%)",[[r["mode"],"Traffic MB" if "communication" in r["metric"] else "VM s",r["held_out_n"],f"{r['predicted']:.3f}",f"{r['measured']:.3f}",f"{100*r['relative_error']:.2f}"] for r in model])]
    if projections:
        supp += [tex_table("Input-inclusive communication projections only, not executed MPC measurements. Runtime is not extrapolated. Padding, field and batch policy are held fixed.","tab:projections","rrrrr",r"Mode & Gallery $N$ & Capacity & Index slots & Projected MB",[[r["mode"],r["n"],r["capacity"],r["index_slots"],f"{r['projected_global_mb']:.1f}"] for r in projections]),
            "These projections use only the communication model that passed held-out validation below 5\\% relative error. Their out-of-range uncertainty remains unmeasured. They do not predict indexed-query cost, latency, throughput or a different ORAM backend."]
    if celeba:
        extraction=read(ROOT/"data/celeba/extraction.json")
        checks=extraction["frozen_binary_checks"]
        supp += [r"\subsection{CelebA Recovery Outcome}",f"The recovered gallery has {checks['gallery_bit_mismatches']} binary bit differences and the recovered probes have {checks['probe_bit_mismatches']} relative to the frozen NPZ. These counts determine whether the historical fixed split is exactly reproduced; the paired float/binary experiment always uses identical reconstructed images. Source and feature hashes remain in the artifact."]
        if external_celeba:
            exact=external_celeba["all_20_historical_ranks_exact"]
            count=sum(r["rank1_exact"] and r["rank5_exact"] for r in external_celeba["comparison"])
            supp += [f"The distinct historical portability cohort reproduces both Rank-1 and Rank-5 exactly in {count} of 20 splits. All per-split comparisons are recorded; any mismatch is retained. The two CelebA populations are not pooled."]
        if fixed_celeba:
            paired_rows=[]
            for cohort,source in (("Fixed cohort, new splits",fixed_celeba),("Historical portability",external_celeba)):
                if not source:continue
                c=source["paired"]["rank1"]
                paired_rows.append([cohort,f"{c['float_mean']:.4f}",f"{c['binary_mean']:.4f}",f"{100*c['binary_minus_float']:.3f} [{100*c['subject_bootstrap_ci95'][0]:.3f}, {100*c['subject_bootstrap_ci95'][1]:.3f}]"])
            supp += [tex_table("Separate CelebA 20-split paired cohorts; intervals resample 128 identities. Delta is binary minus float Rank-1 in percentage points.","tab:celeba_cohorts","lrrr",r"Cohort & Float R1 & Binary R1 & Delta [95\% CI]",paired_rows)]
    open_ci=[]
    for r in bio["open_set"]:
        if r["n_gallery"] not in (128,4096):continue
        f,d=r["test_fpir"],r["test_dir"]
        open_ci.append([r["n_gallery"],"Float" if r["representation"]=="float_cosine" else "Binary","Emp." if r["rule"]=="empirical" else "Cons.",f"{100*f['mean']:.3f} [{100*f['ci95'][0]:.3f}, {100*f['ci95'][1]:.3f}]",f"{100*d['mean']:.2f} [{100*d['ci95'][0]:.2f}, {100*d['ci95'][1]:.2f}]"])
    supp += [tex_table("Observed test FPIR and DIR with identity-bootstrap 95\\% intervals, in percentages.","tab:open_ci","rllrr",r"Gallery & Root & Rule & FPIR [95\% CI] & DIR [95\% CI]",open_ci),
        "The fresh unknown cohort contains 365 identities with one source image, 134 with two to five, and 13 with at least six. Image-count-stratified FPIR is exported for every split in the CSV. The strata are descriptive and were not used to tune thresholds."]
    open_split_rows=list(csv.DictReader((ROOT/"results/lfw_extended/open_set_splits.csv").open()))
    strata=[]
    for representation in ("float_cosine","binary_hamming"):
        # Use the representation labels in the frozen CSV, rather than assuming
        # that the displayed names form part of the machine-readable protocol.
        matching=[r for r in open_split_rows if int(r["n_gallery"])==128 and r["representation"]==representation]
        for rule in ("empirical","conservative_iid_order_statistic"):
            rows=[r for r in matching if r["rule"]==rule]
            if not rows:continue
            strata.append(["Float" if representation=="float_cosine" else "Binary","Emp." if rule=="empirical" else "Cons.",*[f"{100*statistics.mean(float(r['test_'+s+'_fpir']) for r in rows):.3f}" for s in ("one_image","two_to_five","six_or_more")]])
    if strata:supp += [tex_table("Descriptive test FPIR at gallery 128 by source identity image count, in percentages. The strata have 365, 134 and 13 identities; the small final stratum does not support a low-FPIR guarantee.","tab:unknown_strata","llrrr",r"Root & Rule & One & Two--five & Six or more",strata)]
    # Keep one-column evidence tables beside their explanatory text instead of
    # allowing a float queue to place them after the references.
    (PAPER/"generated_supplement.tex").write_text(("\n\n".join(supp)+"\n").replace(r"\begin{table}[t]",r"\begin{table}[H]"),encoding="utf-8")
    def group(n,mode,protection=0,transition=0):
        return next((r for r in secure if r["n"]==n and r["mode"]==mode and r["protection"]==protection and r["transition"]==transition and r["repetitions"]>=3),None)
    def mean_time(row):return f"{row['full_vm_seconds_mean']:.2f}" if row else "(internal draft: pending)"
    stored_group=lambda n,mode,protection:next((r for r in persisted if r["n"]==n and r["mode"]==mode and r["protection"]==protection and r["repetitions"]>=3),None)
    raw=stored_group(128,1,1) or group(128,1,1)
    masked_rekey128=stored_group(128,1,0) or group(128,1)
    masked_query128=stored_group(128,2,0) or group(128,2)
    sort=next((r for r in compact if r["n"]==8 and r["repetitions"]>=3),None)
    iq=group(8,3)
    macros={"RekeyOneTwentyEight":mean_time(masked_rekey128),"QueryOneTwentyEight":mean_time(masked_query128),
        "LargestSecureGallery":str(max((r["n"] for r in good),default=0)),
        "RawBaselineSentence":f"At $N=128$, full shared-root re-key time is {mean_time(raw)} s, versus {mean_time(masked_rekey128)} s for masked roots, using persisted-share loading; the same-threshold confidentiality of shared roots is preserved in our comparison.",
        "SortBaselineSentence":f"At $N=8$ and $d=512$, valid-compacted sort/merge takes {mean_time(sort)} s, versus {mean_time(group(8,1))} s for direct synchronized evolution in the same input-inclusive harness. Both retain all 128 sort-key bits and restore the same public-size padded state.",
        "IndexedCostSentence":f"At $N=8$ and $d=512$, a standalone private indexed query takes {mean_time(iq)} s, versus {mean_time(group(8,2))} s for exhaustive query. This measured reference cost is disclosed rather than advertised as a speedup.",
        "CelebAPairedSentence":"(Internal draft: CelebA recovery is still in progress.)",
        "CelebAReproductionSentence":"(Internal draft: the CelebA bit/split reproduction audit is pending.)"}
    if celeba:
        c=celeba["paired"]["rank1"]
        checks=read(ROOT/"data/celeba/extraction.json")["frozen_binary_checks"]
        macros["CelebAPairedSentence"]=f"On the fixed CelebA image assignment, float/binary Rank-1 is 0.8691/0.8516. The separate historical 20-split cohort gives {c['float_mean']:.4f}/{c['binary_mean']:.4f}." if external_celeba else f"Recovered CelebA fixed-cohort resplit float/binary Rank-1 is {c['float_mean']:.4f}/{c['binary_mean']:.4f}."
        macros["CelebAReproductionSentence"]=f"CelebA recovery differs from the frozen fixed artifact in {checks['gallery_bit_mismatches']} gallery bits and {checks['probe_bit_mismatches']} probe bits."
        if external_celeba:
            count=sum(r["rank1_exact"] and r["rank5_exact"] for r in external_celeba["comparison"])
            macros["CelebAReproductionSentence"]+=f" The distinct historical portability cohort reproduces both ranks exactly in {count}/20 splits; it shares only one subject with the fixed main-paper cohort and is reported separately."
    (PAPER/"generated_response_values.tex").write_text("\n".join("\\newcommand{\\"+k+"}{"+v+"}" for k,v in macros.items())+"\n",encoding="utf-8")
    evidence=[
        {"concern":"R1.1 / R2 major 2","action":"identify unpublished internal predecessor; inherited/new table; shared-root baseline; conventional encryption/HERS/UE positioning","evidence":"main.tex sections II-IV; legacy_reproduce/sle_sort_merge_transition.mpc; results/persisted_state_summary.csv","scope":"same-threshold shared roots already confidential; no first-combination or unique re-key claim"},
        {"concern":"R1.2 / R2 major 1","action":"restrict theorem to secret keys; remove hidden-input/exposed-key guarantee; explicit PRP/data bounds","evidence":"main.tex sections III,V; supplement.tex II; parameters.json; results/primitives.json","scope":"concrete MiMC PRP assumed; passive MPC statistical parameter 80"},
        {"concern":"R1.3 / R2 major 4","action":"private retrieval, OR deduplication, capacity admission, strict completeness certificate and hidden exhaustive fallback","evidence":"mpc/msle_system.mpc modes 3/4; results/lfw_extended/index_frozen_split.csv","scope":"fixed-scan implementation; four-bit retrieval nearly exhaustive; eight-bit overflow/fallback disclosed"},
        {"concern":"R1 suggestion 1 / R2 major 3","action":"measure complete re-key/query/maintenance and actual per-party share-file reload with external shared initialization","evidence":"results/persisted_state_summary.csv; results/persisted_runs.jsonl; results/persisted_common_core_audit.json; results/secure_summary.csv; logs/persisted","scope":"trusted external initializer; five colocated processes; largest-child RSS; logical rather than distributed crash atomicity"},
        {"concern":"R2 major 5","action":"same-contract valid-compacted full-128-bit oblivious sort/merge baseline; larger actual MPC gallery; held-out model checks","evidence":"results/compact_sort_summary.csv; results/compact_common_core_audit.json; results/cost_model_validation.csv; mpc/msle_compact_sort_system.mpc","scope":"model errors retained; input-inclusive baselines/model kept distinct from persisted-family timings; no extrapolated 4096-gallery MPC runtime"},
        {"concern":"R1 suggestion 2 / R2 major 6","action":"matched float/binary images and 20 splits; fresh 512/512 calibration/unknown LFW cohorts; image-level provenance","evidence":"results/lfw_extended; results/celeba_paired; data/celeba/extraction.json","scope":"custom datasets/backbone; 128 query identities even at 4096 gallery; no reliable 0.1 percent FPIR claim"},
        {"concern":"R2 additional 1","action":"correct full-field key entropy, MiMC rounds, expansion and equality; disclose legacy defects","evidence":"parameters.json; reference.py; test_reference.py; supplement.tex I-II","scope":"legacy narrow-key and implicit-field timings excluded"},
        {"concern":"R2 additional 2","action":"hardware/software/network/variability and memory semantics","evidence":"supplement.tex VI; results/secure_summary.csv; ../hardware.json","scope":"local-loopback timings, no WAN claim"},
        {"concern":"R2 additional 3-4 / editorial","action":"retain expanded supplement; shorten main repetition; point-by-point response; black text and bios/photos","evidence":"manuscript_R1/main.tex; supplement.tex; response_to_reviewers.tex","scope":"local revision package; user author review and submission remain external actions"},
    ]
    write_csv(ROOT/"reviewer_evidence_matrix.csv",evidence)
    manifest={"draft":draft,"final_hashes":hashes,"selected_current_source_runs":len(selected),"performance_groups":len(secure),"additional_family_groups":{k:len(v) for k,v in additional.items()},"batch_status":batch,"lfw_utility_source_sha256":sha(ROOT/"results/lfw_extended/summary.json"),"builder_sha256":sha(__file__)}
    (ROOT/"results/revision_build_manifest.json").write_text(json.dumps(manifest,indent=2))
    print(json.dumps({"draft":draft,"groups":len(secure),"completed_steps":batch["completed"]},indent=2))

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--draft",action="store_true");args=parser.parse_args();main(args.draft)
