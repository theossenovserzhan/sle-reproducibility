"""Report only actually completed new experiments, filtering current source hashes."""
from pathlib import Path
from collections import defaultdict
import hashlib,json,statistics

ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rows(p):return [json.loads(r) for r in p.read_text().splitlines()] if p.exists() else []

def main():
    sources={"full_direct":"msle_system","matrix_compact_direct":"msle_valid_compact_system","matrix_compact_sort":"msle_compact_sort_known_bits","position_compact_direct":"msle_position_compact_system","position_compact_sort":"msle_compact_sort_positions","lazy_epoch":"msle_lazy_epoch_system"}
    hashes={name:sha(ROOT/f"mpc/{source}.mpc") for name,source in sources.items() if (ROOT/f"mpc/{source}.mpc").exists()}
    by_hash={v:k for k,v in hashes.items()}
    groups=defaultdict(list)
    for row in rows(ROOT/"results/transition_comparison_runs.jsonl")+rows(ROOT/"results/lazy_epoch_runs.jsonl"):
        if row["tag"] in ("performance","position_comparison","lazy_comparison") and not row["warmup"] and row["diag"]==0 and row["circuit_sha256"] in by_hash:
            groups[(row["n"],row["mode"],row["tag"],by_hash[row["circuit_sha256"]])].append(row)
    stats=[]
    for (n,mode,family,method),data in sorted(groups.items()):
        out={"n":n,"mode":mode,"family":family,"method":method,"repetitions":len(data),"source_sha256":hashes[method]}
        for field in ("full_vm_seconds","wall_seconds","global_communication_mb","timer12_seconds","timer13_seconds","max_rss_single_child_kib"):
            values=[r[field] for r in data if r.get(field) is not None]
            out[field+"_mean"]=statistics.mean(values) if values else None
            out[field+"_sd"]=statistics.stdev(values) if len(values)>1 else None
        stats.append(out)
    ablations=rows(ROOT/"results/joint_ablation_runs.jsonl")
    base_hash=sha(ROOT/"mpc/msle_joint_ablation.mpc")
    base=[r for r in ablations if r["source_sha256"]==base_hash]
    witness={str(bits):{
        "full_checker_rejects":any(r["bits"]==bits and r["fault"]==9 and r["check_template"]==1 and r["check_index"]==1 and r["accepted_candidate"]==0 and r["state_oracle_ok"]==1 for r in base),
        "relation_only_accepts_wrong_root":any(r["bits"]==bits and r["fault"]==9 and r["check_template"]==0 and r["check_index"]==1 and r["template_ok"]==0 and r["index_ok"]==1 and r["unsafe_acceptance"] and r["query_oracle_ok"]==0 for r in base)} for bits in (64,512)}
    jobs={}
    for name in ("position_compact","lazy_epoch","binary_frontend","scale_batch"):
        path=ROOT/f"results/{name}_status.json"
        if path.exists():
            try:jobs[name]=json.loads(path.read_text())
            except json.JSONDecodeError:jobs[name]={"status":"being updated; consult live file"}
    result={"job_status":jobs,"joint_ablation_status":json.loads((ROOT/"results/joint_ablation_status.json").read_text()),"joint_invariant_witness":witness,"completed_current_source_performance":stats,
        "frozen_r1_package_unchanged":sha(ROOT.parent/"revision_v2/output/TBIOM_R1_package.zip")=="eb0b7411fe238e3dd7c1728b3311d23f8cb78e7f6b7e68a0f2f52796185a587c",
        "scope":"Diagnostic ablations are functional necessity witnesses, not a malicious-MPC proof or a novelty proof. Partial timing groups are not final comparisons."}
    (ROOT/"results/progress_summary.json").write_text(json.dumps(result,indent=2))
    lines=["Новый этап: фактически полученные результаты", "", "Контрольный архив R1 сохранён: "+str(result["frozen_r1_package_unchanged"]),
        "", "Согласованная замена шаблона и индекса:"]
    for bits,proof in witness.items():lines.append(f"{bits} бит: полный checker отклоняет={proof['full_checker_rejects']}; checker только нового отношения принимает изменённый корень и неверную оценку запроса={proof['relation_only_accepts_wrong_root']}")
    lines += ["", "Текущие замеры (незавершённые группы не являются итоговым сравнением):"]
    for r in stats:lines.append(f"N={r['n']}, mode={r['mode']}, series={r['family']}, {r['method']}, runs={r['repetitions']}: VM mean={r['full_vm_seconds_mean']:.4f}s, global={r['global_communication_mb_mean']:.3f}MB")
    lines += ["", "Дальнейшие серии и критерии: EXPERIMENT_PLAN_RU.txt. Все неудачные и промежуточные варианты сохраняются. Новизна этим отчётом не объявляется доказанной."]
    (ROOT/"INITIAL_RESULTS_RU.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps({"witness":witness,"performance":stats,"frozen_r1_unchanged":result["frozen_r1_package_unchanged"]},indent=2))

if __name__=="__main__":main()
