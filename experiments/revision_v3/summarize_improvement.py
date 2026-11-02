"""Audit complete comparisons; keep engineering gains separate from novelty."""
from pathlib import Path
import hashlib,json,statistics
import numpy as np

ROOT=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def ci(values,seed):
    values=np.asarray(values,float);rng=np.random.default_rng(seed)
    means=values[rng.integers(len(values),size=(10000,len(values)))].mean(1)
    return {"mean":float(values.mean()),"ci95":np.quantile(means,[.025,.975]).tolist(),"units":len(values)}

def main():
    rows=[json.loads(line) for line in (ROOT/"results/lazy_epoch_runs.jsonl").read_text().splitlines()]
    hashes={name:sha(ROOT/f"mpc/{name}.mpc") for name in ("msle_system","msle_lazy_epoch_system")}
    comparisons=[]
    for n,mode in ((8,1),(32,1),(128,1),(128,2)):
        methods={}
        for name,digest in hashes.items():
            selected=[r for r in rows if r["tag"]=="lazy_comparison" and not r["warmup"] and r["diag"]==0 and r["n"]==n and r["mode"]==mode and r["circuit_sha256"]==digest]
            assert len(selected)==(3 if mode==2 else 5)
            assert all(r["state_ok"]==1 and r["query_ok"]==1 and r["relation_ok"]==1 for r in selected)
            methods[name]={r["repeat"]:r for r in selected}
        eager=methods["msle_system"];lazy=methods["msle_lazy_epoch_system"]
        assert eager.keys()==lazy.keys()
        pairs=sorted(eager)
        old=np.asarray([eager[k]["full_vm_seconds"] for k in pairs]);new=np.asarray([lazy[k]["full_vm_seconds"] for k in pairs])
        rng=np.random.default_rng(20261030+n+1000*mode)
        picks=rng.integers(len(pairs),size=(10000,len(pairs)))
        ratios=old[picks].mean(1)/new[picks].mean(1)
        omb=statistics.mean(eager[k]["global_communication_mb"] for k in pairs)
        nmb=statistics.mean(lazy[k]["global_communication_mb"] for k in pairs)
        comparisons.append({"n":n,"mode":mode,"paired_repetitions":len(pairs),"eager_mean_seconds":float(old.mean()),"virtual_mean_seconds":float(new.mean()),
            "time_ratio_eager_over_virtual":float(old.mean()/new.mean()),"paired_run_bootstrap_ratio_ci95":np.quantile(ratios,[.025,.975]).tolist(),
            "eager_mean_global_mb":omb,"virtual_mean_global_mb":nmb,"communication_ratio_eager_over_virtual":omb/nmb,
            "virtual_communication_change_percent":100*(nmb/omb-1),"eager_source_sha256":hashes["msle_system"],"virtual_source_sha256":hashes["msle_lazy_epoch_system"]})
    biometric=json.loads((ROOT/"results/binary_frontend/summary.json").read_text())
    with np.load(ROOT/"results/binary_frontend/subject_outcomes.npz") as data:
        rank=data["rank1"];known=data["correct_accepted"];unknown=data["unknown_accept"]
    utility=[];s=5
    for index,method in enumerate(biometric["methods"]):
        known_delta=known[index,s].reshape(20,2,128,4).mean(axis=(0,3))-known[1,s].reshape(20,2,128,4).mean(axis=(0,3))
        unknown_delta=unknown[index,s].mean(0)-unknown[1,s].mean(0)
        utility.append({"method":method,"n_gallery":4096,"rank1":float(rank[index,s].mean()),
            "paired_rank1_delta_vs_original_sign":ci((rank[index,s]-rank[1,s].astype(float)).mean(axis=(0,2)),20261100+index),
            "empirical_DIR_delta":ci(known_delta[0],20261200+index),"empirical_FPIR_delta":ci(unknown_delta[0],20261300+index),
            "conservative_DIR_delta":ci(known_delta[1],20261400+index),"conservative_FPIR_delta":ci(unknown_delta[1],20261500+index)})
    summary={"comparison_family":"input-inclusive local five-party Shamir prototype; cold fixture, not persisted-state load or WAN",
        "ingestion_scope":"The cold fixture uses a trusted-owner input role with plaintext locators/index; these timings are not evidence of hiding that fixture from its own input owner. The real per-computing-party own-share-file lifecycle is a separate required validation.",
        "time_ci_scope":"Run-level bootstrap describes this measured environment; five/three timing pairs do not establish cross-machine performance",
        "mpc_comparisons":comparisons,"biometric_n4096_all_methods":utility,
        "biometric_scope":"Predefined development study; repeated image splits averaged by identity. Intervals are not adjusted for multiple comparisons; ITQ did not improve closed-set rank1.",
        "functional_validation":"N2/N8/N128 state and queries; meaningful fault cases and coupled defect reject; private indexed control passes",
        "claim_boundary":"Stored handles stay secret and logically stable. Virtual semantic locator renewal differs from eager physical locator replacement. No security claim after logical handle exposure. Formal C-only privacy argument and persisted lifecycle still require completion.",
        "R1_package_unchanged":sha(ROOT.parent/"revision_v2/output/TBIOM_R1_package.zip")=="eb0b7411fe238e3dd7c1728b3311d23f8cb78e7f6b7e68a0f2f52796185a587c"}
    (ROOT/"results/improvement_summary.json").write_text(json.dumps(summary,indent=2))
    lines=["Улучшение метода: завершённые сравнительные измерения", "", summary["comparison_family"], "Начальная fixture использует доверенную роль владельца входных данных; приватность от этой роли не проверяется таймингами. Загрузка собственных долей каждым вычислителем проверяется отдельной серией.", ""]
    for row in comparisons:
        lines.append(f"N={row['n']}, mode={row['mode']}, repeats={row['paired_repetitions']}: eager {row['eager_mean_seconds']:.3f}s -> virtual {row['virtual_mean_seconds']:.3f}s; ratio {row['time_ratio_eager_over_virtual']:.3f}; traffic {row['eager_mean_global_mb']:.3f} -> {row['virtual_mean_global_mb']:.3f}MB.")
    lines += ["", "Поиск: добавлена деривация семантического локатора; связь выросла примерно2.7%. Ускорение поиска не заявляется по3повторам.",
        "", "Качество, N4096; все заранее определённые методы:"]
    for row in utility:lines.append(f"{row['method']}: rank1={row['rank1']:.6f}; delta_vs_sign={row['paired_rank1_delta_vs_original_sign']['mean']:.6f}; empirical DIR delta={row['empirical_DIR_delta']['mean']:.6f}, FPIR delta={row['empirical_FPIR_delta']['mean']:.6f}.")
    lines += ["", "ITQ не улучшил закрытую идентификацию. Центрирование даёт вторичный прирост DIR; это требует подтверждения с учётом FPIR, неопределённости и множественных сравнений.",
        "Следующий заранее зафиксированный шаг: random-hyperplane codes512/1024/2048, два публичных seed, включая независимый SFace frontend. Более длинный код требует реальных новых замеров стоимости.",
        "", "Новая архитектура сохраняет секретные стабильные handles; виртуальная смена локатора не является физическим изменением всех значений индекса. Новизна отдельно не доказана.",
        "Нужно завершить сравнение AES на обеих архитектурах, persisted lifecycle, масштаб, сеть, второй frontend и формальное обоснование. Исходный R1 архив сохранён: "+str(summary["R1_package_unchanged"])]
    (ROOT/"REPORT_IMPROVEMENT_RU.txt").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps({"mpc":comparisons,"R1_unchanged":summary["R1_package_unchanged"]},indent=2))

if __name__=="__main__":main()
