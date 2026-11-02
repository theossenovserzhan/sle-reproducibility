"""Wait for E4, validate the new representation, then run fresh paired controls."""
from pathlib import Path
import fcntl,json,random,time
import mpc_driver as core
import reference
from run_joint_ablation import case as diagnostic_case

ROOT=Path(__file__).resolve().parent
original_inputs=core.system_inputs
original_masks,original_evolve=core.masks,core.evolve
CURRENT="full_direct"

def lazy_masks(keys,handles,bits=512):
    return original_masks(keys,original_evolve(keys[0],handles),bits)

def inputs(*args,**kwargs):
    info=original_inputs(*args,**kwargs)
    info["locator_representation"]="stable secret handles with virtual epochs" if CURRENT=="lazy_epoch" else "materialized evolving locators"
    info["experiment_family"]="lazy_epoch_development"
    return info

def select(method):
    global CURRENT
    CURRENT=method
    core.masks=lazy_masks if method=="lazy_epoch" else original_masks
    core.evolve=(lambda key,handles:list(handles)) if method=="lazy_epoch" else original_evolve
    core.system_inputs=inputs

def case(runtime,method,**kwargs):
    select(method)
    return core.system_case(runtime,source_name="msle_lazy_epoch_system" if method=="lazy_epoch" else "msle_system",transition=0,result_file="lazy_epoch_runs.jsonl",**kwargs)

def main():
    path=ROOT/"results/lazy_epoch_status.json"
    state={"finished":False,"current":"waiting_for_E4_lock","correctness_passed":False,"completed":[],"last_error":None}
    path.write_text(json.dumps(state,indent=2))
    runtime=Path(json.loads((ROOT.parent/"mpc_logs/runtime.json").read_text())["runtime"])
    try:
        with (runtime/".msle_v3_driver.lock").open("w") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            prerequisite=json.loads((ROOT/"results/position_compact_status.json").read_text())
            if not prerequisite.get("finished") or not prerequisite.get("correctness_passed"):raise RuntimeError("Prior controlled series did not finish successfully")
            runtime=core.setup_runtime()
            state["current"]="correctness";path.write_text(json.dumps(state,indent=2))
            case(runtime,"lazy_epoch",n=2,bits=64,mode=0,tag="lazy_correctness")
            case(runtime,"lazy_epoch",n=8,bits=512,mode=0,tag="lazy_correctness")
            for fault in (1,2,3,4,5,7,8):case(runtime,"lazy_epoch",n=4,bits=64,mode=0,fault=fault,tag="lazy_faults")
            select("lazy_epoch")
            diagnostic_case(runtime,8,512,9,1,1,source_name="msle_lazy_epoch_ablation",transition=0)
            case(runtime,"lazy_epoch",n=8,bits=512,mode=3,tag="lazy_indexed_correctness")
            case(runtime,"lazy_epoch",n=8,bits=512,mode=4,tag="lazy_transition_indexed_correctness")
            case(runtime,"lazy_epoch",n=8,bits=512,mode=2,threshold=0,tag="lazy_reject_control")
            case(runtime,"lazy_epoch",n=8,bits=512,mode=2,threshold=0,exact_probe=True,tag="lazy_accept_control")
            case(runtime,"lazy_epoch",n=128,bits=512,mode=0,tag="lazy_large_correctness")
            state["correctness_passed"]=True;path.write_text(json.dumps(state,indent=2))
            for n in (8,32,128):
                order=["full_direct","lazy_epoch"];random.Random(20261030+n).shuffle(order)
                for repeat in range(-1,5):
                    for method in (order if repeat%2==0 else list(reversed(order))):
                        state["current"]={"n":n,"method":method,"mode":1,"repeat":repeat};path.write_text(json.dumps(state,indent=2))
                        if repeat<0:case(runtime,method,n=n,bits=512,mode=1,diag=0,tag="lazy_comparison",repeats=0,warmups=1)
                        else:case(runtime,method,n=n,bits=512,mode=1,diag=0,tag="lazy_comparison",repeats=1,repeat_offset=repeat)
                state["completed"].append(n);path.write_text(json.dumps(state,indent=2))
            for repeat in range(-1,3):
                for method in ("full_direct","lazy_epoch") if repeat%2==0 else ("lazy_epoch","full_direct"):
                    state["current"]={"n":128,"method":method,"mode":2,"repeat":repeat};path.write_text(json.dumps(state,indent=2))
                    if repeat<0:case(runtime,method,n=128,bits=512,mode=2,diag=0,tag="lazy_comparison",repeats=0,warmups=1)
                    else:case(runtime,method,n=128,bits=512,mode=2,diag=0,tag="lazy_comparison",repeats=1,repeat_offset=repeat)
        state.update(finished=True,current=None);path.write_text(json.dumps(state,indent=2));print("LAZY_EPOCH_COMPLETE",flush=True)
    except BaseException as error:
        state["last_error"]=repr(error);path.write_text(json.dumps(state,indent=2));raise

if __name__=="__main__":main()
