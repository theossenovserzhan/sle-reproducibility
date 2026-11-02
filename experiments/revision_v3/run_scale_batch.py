"""Queue larger real-data measurements after the current E4 series completes."""
from pathlib import Path
import fcntl,json,random,time
import mpc_driver as core

ROOT=Path(__file__).resolve().parent
STATUS=ROOT/"results/scale_batch_status.json"

def stamp():return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def read_rows():
    path=ROOT/"results/scale_runs.jsonl"
    return [json.loads(r) for r in path.read_text().splitlines()] if path.exists() else []

def execute(runtime,n,mode,source,transition,repeat=-1,diag=0):
    tag="scale_correctness" if diag else "scale_performance"
    key=core.digest(ROOT/f"mpc/{source}.mpc")
    if any(r["tag"]==tag and r["n"]==n and r["mode"]==mode and r["repeat"]==repeat and r["circuit_sha256"]==key and r["input_sha256"]==core.digest(core.INPUT_PATH) and r["parameters_sha256"]==core.digest(ROOT/"parameters.json") and r["backend_sha256"]==core.digest(ROOT/"backend_config.json") for r in read_rows()):return
    options=dict(n=n,bits=512,mode=mode,source_name=source,transition=transition,diag=diag,tag=tag,result_file="scale_runs.jsonl")
    if repeat<0 and not diag:core.system_case(runtime,repeats=0,warmups=1,**options)
    else:core.system_case(runtime,repeats=1,repeat_offset=max(0,repeat),**options)

def main():
    state={"finished":False,"started_utc":stamp(),"current":"waiting_for_E4_lock","completed":[],"last_error":None}
    STATUS.write_text(json.dumps(state,indent=2))
    # Resolve read-only first. setup_runtime writes shared files and therefore
    # must only run AFTER acquiring the common Player-Data lock.
    runtime=Path(json.loads((ROOT.parent/"mpc_logs/runtime.json").read_text())["runtime"])
    try:
        with (runtime/".msle_v3_driver.lock").open("w") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            prerequisite=json.loads((ROOT/"results/position_compact_status.json").read_text())
            if not prerequisite.get("finished") or not prerequisite.get("correctness_passed"):
                raise RuntimeError("E4 did not finish successfully; scale queue will not bypass its failure/pause")
            runtime=core.setup_runtime()
            for n in (512,1024):
                core.INPUT_PATH=ROOT.parent/f"revision_v2/data/lfw_gallery_n{n}.npz"
                state["current"]={"n":n,"stage":"correctness"};STATUS.write_text(json.dumps(state,indent=2))
                execute(runtime,n,0,"msle_system",0,repeat=0,diag=1)
                for mode in (1,2):
                    for repeat in range(-1,3):
                        state["current"]={"n":n,"mode":mode,"repeat":repeat};STATUS.write_text(json.dumps(state,indent=2))
                        execute(runtime,n,mode,"msle_system",0,repeat=repeat)
                state["completed"].append({"n":n,"family":"real_lfw_full_system"});STATUS.write_text(json.dumps(state,indent=2))
            core.INPUT_PATH=ROOT.parent/"inputs/celeba_128_binary_roots.npz"
            for n in (32,64):
                methods=[("msle_system",0),("msle_compact_sort_positions",1)]
                random.Random(20261030+n).shuffle(methods)
                for step,repeat in enumerate(range(-1,3)):
                    order=methods if step%2==0 else list(reversed(methods))
                    for source,transition in order:
                        state["current"]={"n":n,"source":source,"repeat":repeat};STATUS.write_text(json.dumps(state,indent=2))
                        execute(runtime,n,1,source,transition,repeat=repeat)
                state["completed"].append({"n":n,"family":"strong_sort_comparison"});STATUS.write_text(json.dumps(state,indent=2))
        state.update(finished=True,current=None,finished_utc=stamp());STATUS.write_text(json.dumps(state,indent=2))
        print("SCALE_BATCH_COMPLETE",flush=True)
    except BaseException as error:
        state.update(last_error=repr(error),failed_utc=stamp());STATUS.write_text(json.dumps(state,indent=2))
        raise

if __name__=="__main__":main()
