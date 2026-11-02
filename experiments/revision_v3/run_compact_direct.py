"""Correctness first, then alternated full/compacted direct-transition timings."""
from pathlib import Path
import argparse,fcntl,json,random,time
import mpc_driver as core
from run_joint_ablation import case as diagnostic_case

ROOT=Path(__file__).resolve().parent
METHODS={"full_direct":("msle_system",0),"valid_compact_direct":("msle_valid_compact_system",1),"compact_sort":("msle_compact_sort_known_bits",1)}

def case(runtime,method,**kwargs):
    name,transition=METHODS[method]
    return core.system_case(runtime,source_name=name,transition=transition,result_file="transition_comparison_runs.jsonl",**kwargs)

def main(phase,ns,repeats):
    runtime=core.setup_runtime()
    status_path=ROOT/"results/compact_direct_status.json"
    source_hash=core.digest(ROOT/"mpc/msle_valid_compact_system.mpc")
    state=json.loads(status_path.read_text()) if status_path.exists() else {}
    if state.get("source_sha256")!=source_hash:state={"source_sha256":source_hash,"correctness_passed":False,"completed":[]}
    with (runtime/".msle_v3_driver.lock").open("w") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state.update(finished=False,current="correctness");status_path.write_text(json.dumps(state,indent=2))
        if not state["correctness_passed"]:
            case(runtime,"valid_compact_direct",n=2,bits=64,mode=0,tag="compact_direct_correctness")
            case(runtime,"valid_compact_direct",n=8,bits=512,mode=0,tag="compact_direct_correctness")
            for fault in range(1,9):case(runtime,"valid_compact_direct",n=4,bits=64,mode=0,fault=fault,tag="compact_direct_faults")
            diagnostic_case(runtime,8,512,9,1,1,source_name="msle_valid_compact_ablation",transition=1)
            case(runtime,"compact_sort",n=2,bits=64,mode=0,tag="sort_known_bit_correctness")
            case(runtime,"compact_sort",n=8,bits=512,mode=0,tag="sort_known_bit_correctness")
            state["correctness_passed"]=True;status_path.write_text(json.dumps(state,indent=2))
        if phase in ("all","performance"):
            for n in ns:
                methods=["full_direct","valid_compact_direct"]+(["compact_sort"] if n==8 else [])
                rng=random.Random(20261030+n)
                rng.shuffle(methods)
                schedule=[]
                for index,repeat in enumerate(range(-1,repeats)):
                    # Frozen first order, then balanced cyclic/reverse orders.
                    shift=index%len(methods)
                    order=methods[shift:]+methods[:shift]
                    if (index//len(methods))%2:order.reverse()
                    for method in order:schedule.append((repeat,method))
                (ROOT/f"results/comparison_schedule_n{n}.json").write_text(json.dumps({"seed":20261030+n,"schedule":schedule},indent=2))
                for repeat,method in schedule:
                    name,transition=METHODS[method]
                    existing=[json.loads(r) for r in (ROOT/"results/transition_comparison_runs.jsonl").read_text().splitlines()]
                    done=any(r["tag"]=="performance" and r["n"]==n and r["repeat"]==repeat and r["circuit_sha256"]==core.digest(ROOT/f"mpc/{name}.mpc") and r["diag"]==0 for r in existing)
                    if done:continue
                    state["current"]={"n":n,"method":method,"repeat":repeat};status_path.write_text(json.dumps(state,indent=2))
                    if repeat<0:case(runtime,method,n=n,bits=512,mode=1,diag=0,tag="performance",repeats=0,warmups=1)
                    else:case(runtime,method,n=n,bits=512,mode=1,diag=0,tag="performance",repeats=1,repeat_offset=repeat)
                if n not in state["completed"]:state["completed"].append(n)
        state.update(finished=True,current=None,finished_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()))
        status_path.write_text(json.dumps(state,indent=2))
        print("COMPACT_DIRECT_PHASE_COMPLETE",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--phase",choices=["all","correctness","performance"],default="all");parser.add_argument("--n",nargs="+",type=int,default=[8,32,128]);parser.add_argument("--repeats",type=int,default=5);a=parser.parse_args();main(a.phase,a.n,a.repeats)
