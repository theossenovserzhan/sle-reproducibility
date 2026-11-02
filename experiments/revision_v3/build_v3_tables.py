"""Generate draft tables from audited rows; unfinished series remain explicit."""
from pathlib import Path
import contextlib,io,json,re
import summarize_current

ROOT=Path(__file__).resolve().parent
TARGET=ROOT/"manuscript_v3"

def tidy(text):
    prefixes="original|over|same|Same|both|The|the|Longer|at|At|second|fixed|with|through|extrapolated|small|give|gives|versus|and|of|from|to|old|new|FaceNet|SFace|LFW|CelebA|paired|seeds|seed|loses|about|on|is|are|averaging|All|all|plus|centered|measures|RTT|a|an"
    text=re.sub(r"\b("+prefixes+r")(\d)",r"\1 \2",text)
    text=re.sub(r"(\d)(MB|ms|s)(?=[^A-Za-z]|$)",r"\1 \2",text)
    return text.replace("AES128-CTR","AES-128-CTR").replace("Full N128 query","Full $N=128$ query").replace("Rank1(","Rank-1 (").replace("Rank5(","Rank-5 (").replace(r"\%CI",r"\% CI").replace("Delta(pp)","Delta (pp)").replace("CI(pp)","CI (pp)")

def table(caption,label,columns,header,rows):
    return "\n".join([r"\begin{table}[t]",r"\caption{"+caption+"}",r"\label{"+label+r"}\centering\small",r"\setlength{\tabcolsep}{3pt}",r"\begin{tabular}{"+columns+"}",r"\toprule",header+r" \\",r"\midrule",*[" & ".join(row)+r" \\" for row in rows],r"\bottomrule",r"\end{tabular}",r"\end{table}",""])

def timing(row):
    metric=row["full_vm_seconds"]
    return f"${metric['mean']:.2f}\\pm{metric['sd']:.2f}$"

def complete(row,minimum):
    assert len(row["circuit_hashes"])==1,"Never pool different circuit hashes"
    return row["repetitions"]>=minimum

def main():
    with contextlib.redirect_stdout(io.StringIO()):summarize_current.main()
    evidence=json.loads((ROOT/"results/current_results.json").read_text())
    main=[r"\subsection{New Representation and Cipher Comparisons}",
          "The following are fresh within-series comparisons. They are not pooled with the retained timing batch above. The virtual representation changes logical references as specified in the method; it retains all share refresh and state-verification work."]
    persisted=[]
    for row in evidence["comparisons"]["persisted_rekey"]:
        if complete(row,5):persisted.append([str(row["n"]),"Materialized" if row["method"]=="eager" else "Virtual",timing(row),f"{row['global_communication_mb']['mean']:.1f}"])
    if persisted:main.append(table("Actual persisted-share rekeying: five alternating measured trials, mean and sample SD. All five parties are local.","tab:v3persisted","rlrr",r"$N$ & Representation & Seconds & Global MB",persisted))
    scale=[]
    for row in sorted(evidence["comparisons"]["larger_real_gallery"],key=lambda r:(r["n"],r["mode"],r["locator_representation"])):
        if complete(row,3):scale.append([str(row["n"]),"Rekey" if row["mode"]==1 else "Query","Materialized" if row["locator_representation"].startswith("materialized") else "Virtual",timing(row),f"{row['global_communication_mb']['mean']:.1f}"])
    if scale:main.append(table("Larger real LFW galleries, original512-bit roots: three measured cold-input trials per completed cell. VM time and global traffic; initialization fixture is a trusted input owner.","tab:v3scale","rllrr",r"$N$ & Operation & View & Seconds & MB",scale))
    main.append("Reducing permutation work on the padded index substantially reduces renewal communication, but does not reduce standalone-query communication. Source hashes, phase timers, rounds, largest-party RSS and all repetitions are retained in the artifact.")
    aes=json.loads((ROOT/"results/aes_baseline_summary.json").read_text())
    selected=[row for row in aes["complete_metrics"] if row["transition"]==0 and row["mode"]==1 and (row["cipher"].endswith("_stable") or row["n"]==2 and row["cipher"] in ("AES_CTR","MiMC_mask"))]
    cipher_rows=[]
    for row in selected:
        name="AES-CTR" if row["cipher"].startswith("AES") else "MiMC"
        view="Virtual" if row["cipher"].endswith("_stable") else "Materialized"
        cipher_rows.append([str(row["n"]),view,name,f"${row['mean_vm_seconds']:.2f}\\pm{row['sd_vm_seconds']:.2f}$",f"{row['mean_global_mb']:.1f}"])
    main.append(table("Conventional-cipher control, five measured rekeys. Both ciphers implement the same high-level invariant/check/maintenance contract in arithmetic Shamir MPC.","tab:v3cipher","rllrr",r"$N$ & View & Cipher & Seconds & MB",cipher_rows))
    main.append("AES passes three published known-answer vectors in the independent library and MPC. It is faster in the smallest materialized case; larger stable-view trials favor the arithmetic MiMC circuit. This is an implementation comparison, not a universal lower bound on AES or evidence that generic encryption cannot realize the lifecycle contract.")
    private=evidence["comparisons"]["private_output_full_query"]
    if len(private)==3 and all(complete(row,5) for row in private):
        query_rows=[]
        for row in private:
            name="Fused blocks" if row["method"]=="fused" else "Full scan" if row["mode"]==2 else "Polynomial index"
            query_rows.append([name,timing(row),f"{row['global_communication_mb']['mean']:.2f}"])
        main.append(table("Full N128 query from the same persisted state with private client input/output: five balanced measured trials. Candidate and exhaustive winners agree.","tab:v3privatequery","lrr","Method & Seconds & Global MB",query_rows))
        main.append("The standalone index operator is compared separately from this complete matcher. All three methods score the same gallery and return the same reference result to the external client; servers open only its uniformly padded encoding.")
    else:main.append("% Private-output query comparison remains pending; do not finalize this manuscript.")
    ablation=[row for row in summarize_current.rows("joint_ablation_runs.jsonl") if row.get("source_sha256")=="99eb8155c0dda553a7d4df2b4050b2064889008fe6b6556c6dfec66cbb3d8b58"]
    for n in (4,8):
        witness=[r for r in ablation if r["n"]==n and r["fault"]==9 and r["check_index"]==1]
        assert any(r["check_template"]==0 and r["accepted_candidate"]==1 for r in witness)
        assert any(r["check_template"]==1 and r["accepted_candidate"]==0 for r in witness)
    main.append("The coupled fault changes a root bit and relocates its corresponding index occurrence into the new root's bucket. Relation-only checking accepts this wrong enrolled root at both tested sizes, while full template binding rejects it. Template-only checking misses a missing occurrence. These necessity witnesses concern valid-bit application logic under passive MPC.")
    main.append(r"\subsection{Second Frontend at Fixed Binary Width}")
    utility=[]
    for frontend,method,label,bits in (("facenet","original_cosine","FaceNet float","512D"),("facenet","original_sign_512","FaceNet sign","512"),("sface","original_cosine","SFace float","128D"),("sface","original_sign_128","SFace sign","128"),("sface","RP_centered_512_seed20261030","SFace RP seed1","512"),("sface","RP_centered_512_seed20261031","SFace RP seed2","512")):
        summary=json.loads((ROOT/f"results/projection_{frontend}/summary.json").read_text())
        values={r["n_gallery"]:r for r in summary["closed_set"] if r["method"]==method}
        utility.append([label,bits,f"{100*values[128]['rank1']:.2f}",f"{100*values[4096]['rank1']:.2f}"])
    main.append(table("Paired LFW Rank-1 percentages over20 frozen assignments; the same128 query identities at each size. Both fixed centered projections are shown, without selecting a seed.","tab:v3frontend","llrr","Frontend & Bits & $N=128$ & $N=4096$",utility))
    main.append("The512-bit SFace projections improve closed-set utility at the same binary width, changing encoder, alignment and coding together. Longer1024/2048-bit results are retained separately; their MPC costs have not been measured. Four-bit bucket capacity fits both512-bit seeds, but candidate fractions near one do not establish useful pruning.")
    supplement=[r"\section{New Implementation and Evidence Audit}",r"The new sources and manifests are in revision\_v3. The reference and all development attempts remain available. Warmups and diagnostic oracles are excluded from production timings. Cold protected-owner inputs, actual per-party state shares and external private query shares are distinct interfaces."]
    repair=evidence["status"].get("calibration_repair",{})
    if repair.get("finished") and repair.get("correctness_passed"):
        supplement.append("A numerical audit found that NumPy2 weak scalar promotion rounded a strict nextafter64 threshold when compared with float32 Hamming scores. Corrected evaluators convert the exact integer scores to float64 before thresholding. Frozen models, seeds, cohorts, calibration rules and all closed-set flags are unchanged. Every corrected native float/sign open-set flag exactly reproduces the original independent evaluator, and every calibration acceptance count respects its prescribed limit. Original attempts are retained; only corrected open-set outputs are used below.")
        open_rows=[]
        for frontend,methods in (("facenet",("original_sign_512",)),("sface",("RP_centered_512_seed20261030","RP_centered_512_seed20261031"))):
            summary=json.loads((ROOT/f"results/projection_{frontend}_corrected/summary.json").read_text())
            for row in summary["open_set"]:
                if row["n_gallery"]!=4096 or row["method"] not in methods:continue
                label="FaceNet512" if frontend=="facenet" else "SFace512 seed"+str(1+methods.index(row["method"]))
                open_rows.append([label,"Emp." if row["rule"]=="empirical" else "Cons.",f"{100*row['test_fpir']['mean']:.3f}",f"{100*row['test_dir']['mean']:.2f}"])
        main.append(table("Corrected open-set results at4096 gallery entries. Same512 calibration and512 unknown identities; actual test FPIR and DIR percentages, not nominal operating points.","tab:v3open","llrr","Frontend & Rule & FPIR & DIR",open_rows))
        main.append("The calibration rule is identical across methods, but the achieved test FPIR need not be. DIR gains must be read together with false-positive rates; they are not an equal-FPIR comparison. Identity-paired intervals, all seeds and all dimensions are in the supplement/artifact.")
        for frontend in ("facenet","sface"):
            summary=json.loads((ROOT/f"results/projection_{frontend}_corrected/summary.json").read_text())
            rows=[]
            for row in summary["closed_set"]:
                if row["n_gallery"]==4096:rows.append([row["method"].replace("_",r"\_"),f"{100*row['rank1']:.3f}",f"{100*row['rank5']:.3f}"])
            supplement.append(table(frontend.capitalize()+" full predefined projection study at4096: all widths/seeds/centering variants. Public hyperplanes are established preprocessing.","tab:v3all"+frontend,"lrr","Method & Rank1(\\%) & Rank5(\\%)",rows))
    else:supplement.append("% Strict-calibration recomputation is pending. Do not use the original new-study float32 open-set outputs.")
    confirmation=ROOT/"results/frontend_confirmation/summary.json"
    if confirmation.exists():
        data=json.loads(confirmation.read_text());transfer=[]
        for cohort in data["cohorts"]:
            for row in cohort["methods"]:
                if row["method"] in ("FaceNet_sign512","SFace_cosine","SFace_sign128","SFace_RP_centered_512_seed20261030","SFace_RP_centered_512_seed20261031"):
                    transfer.append([cohort["cohort"].replace("_",r"\_"),row["method"].replace("_",r"\_"),f"{100*row['rank1']:.3f}"])
        supplement.append(table("Frozen-model transfer on identical images/splits. CelebA cohorts share one identity; do not pool intervals.","tab:v3transfer","llr","Cohort & Method & Rank1(\\%)",transfer))
    else:supplement.append("% Transfer/private-root confirmation is pending.")
    for filename,contents in (("generated_v3_results.tex",main),("generated_v3_supplement.tex",supplement)):
        (TARGET/filename).write_text(tidy("\n\n".join(contents))+"\n")
    (ROOT/"results/manuscript_v3_table_audit.json").write_text(json.dumps({"working_draft_only":True,"corrected_open_set_used":bool(repair.get("finished") and repair.get("correctness_passed")),"scale_cells":[{key:row[key] for key in ("n","mode","repetitions")} for row in evidence["comparisons"]["larger_real_gallery"] if row["repetitions"]>=3],"statuses":evidence["status"]},indent=2))
    print("V3_DRAFT_TABLES_GENERATED; not a submission-ready package")

if __name__=="__main__":main()
