"""Evaluate a valid-compacted sort/merge under the unchanged full contract."""
from pathlib import Path
import argparse,hashlib,json,time
import mpc_driver as core

ROOT=Path(__file__).resolve().parent
SOURCE="msle_compact_sort_system"
CONFIG="compact_baseline_config.json"

def audit():
    main=(ROOT/"mpc/msle_system.mpc").read_text()
    baseline=(ROOT/f"mpc/{SOURCE}.mpc").read_text()
    before=lambda s:s[s.index("def permute("):s.index("def radix_translate(")]
    after=lambda s:s[s.index("start_timer(30)"):]
    assert before(main)==before(baseline) and after(main)==after(baseline)
    result={"only_translation_function_differs":True,"same_initial_inputs_and_verification_commit_maintenance_query":True,
        "main_sha256":core.digest(ROOT/"mpc/msle_system.mpc"),"baseline_sha256":core.digest(ROOT/f"mpc/{SOURCE}.mpc"),
        "config_sha256":core.digest(ROOT/CONFIG),"same_prefix_sha256":hashlib.sha256(before(main).encode()).hexdigest(),
        "same_protocol_tail_sha256":hashlib.sha256(after(main).encode()).hexdigest()}
    (ROOT/"results/compact_common_core_audit.json").write_text(json.dumps(result,indent=2))
    return result

def case(runtime,**kwargs):
    return core.system_case(runtime,transition=1,source_name=SOURCE,extra_config=CONFIG,result_file="compact_sort_runs.jsonl",**kwargs)

def main(phase,ns,repeats):
    proof=audit();runtime=core.setup_runtime()
    status_path=ROOT/"results/compact_status.json"
    state={"finished":False,"audit":proof,"phase":phase,"completed":[]}
    if phase in ("all","correctness"):
        case(runtime,n=2,bits=64,mode=0,tag="compact_correctness")
        case(runtime,n=8,bits=512,mode=0,tag="compact_correctness")
        for fault in (1,5,7):case(runtime,n=4,bits=64,mode=0,fault=fault,tag="compact_faults")
        state["correctness_passed"]=True
    else:
        previous=json.loads(status_path.read_text()) if status_path.exists() else {}
        if not previous.get("correctness_passed") or previous.get("audit")!=proof:
            raise RuntimeError("Validate the current compacted comparator before timing it")
        state["correctness_passed"]=True
    status_path.write_text(json.dumps(state,indent=2))
    if phase in ("all","performance"):
        for n in ns:
            archive=ROOT/"results/compact_sort_runs.jsonl"
            rows=[json.loads(line) for line in archive.read_text().splitlines()] if archive.exists() else []
            count=sum(r["tag"]=="performance" and r["n"]==n and r["root_bits"]==512 and not r["warmup"] and r["diag"]==0 and r["circuit_sha256"]==proof["baseline_sha256"] and r.get("extra_config_sha256")==proof["config_sha256"] for r in rows)
            if count<repeats:case(runtime,n=n,bits=512,mode=1,diag=0,tag="performance",repeats=repeats-count,repeat_offset=count,warmups=1)
            state["completed"].append(n);status_path.write_text(json.dumps(state,indent=2))
    state.update(finished=True,finished_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()))
    status_path.write_text(json.dumps(state,indent=2))
    print("COMPACT_BASELINE_COMPLETE",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--phase",choices=["all","correctness","performance"],default="all")
    parser.add_argument("--n",nargs="+",type=int,default=[8,16]);parser.add_argument("--repeats",type=int,default=3)
    args=parser.parse_args();main(args.phase,args.n,args.repeats)
