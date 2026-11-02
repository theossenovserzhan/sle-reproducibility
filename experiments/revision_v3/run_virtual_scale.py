"""Confirm the frozen512-bit representation on larger real LFW galleries."""
from pathlib import Path
import fcntl,json,time
import mpc_driver as core
import run_lazy_epoch as study

ROOT=Path(__file__).resolve().parent

def main():
    path=ROOT/"results/virtual_scale_status.json"
    state={"finished":False,"current":"waiting_for_persisted_validation","completed":[],"last_error":None}
    def save(**values):state.update(values);path.write_text(json.dumps(state,indent=2))
    save()
    try:
        while True:
            prior_path=ROOT/"results/lazy_persistence_status.json"
            if prior_path.exists():
                try:prior=json.loads(prior_path.read_text())
                except json.JSONDecodeError:time.sleep(1);continue
                if prior.get("last_error"):raise RuntimeError("Persisted candidate validation must be repaired before scaling: "+prior["last_error"])
                if prior.get("finished") and prior.get("correctness_passed"):
                    extra_paths=[ROOT/"results/vector_query_status.json",ROOT/"results/sface_status.json",ROOT/"results/shared_query_status.json"]
                    if all(p.exists() for p in extra_paths):
                        try:vector,sface,shared=[json.loads(p.read_text()) for p in extra_paths]
                        except json.JSONDecodeError:time.sleep(1);continue
                        if vector.get("last_error"):raise RuntimeError("Repair vectorized query before larger queued measurements: "+vector["last_error"])
                        if shared.get("last_error"):raise RuntimeError("Repair external query-share validation before scaling: "+shared["last_error"])
                        if vector.get("finished") and shared.get("finished") and shared.get("correctness_passed") and (sface.get("finished") or sface.get("last_error")):break
            time.sleep(5)
        runtime=Path(json.loads((ROOT.parent/"mpc_logs/runtime.json").read_text())["runtime"])
        with (runtime/".msle_v3_driver.lock").open("w") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            runtime=core.setup_runtime()
            for n in (512,1024):
                core.INPUT_PATH=ROOT.parent/f"revision_v2/data/lfw_gallery_n{n}.npz"
                for method in ("full_direct","lazy_epoch"):
                    save(current={"phase":"full_state_correctness","n":n,"method":method})
                    study.case(runtime,method,n=n,bits=512,mode=0,tag="virtual_scale_correctness")
                for mode in (1,2):
                    for repeat in range(-1,3):
                        order=("full_direct","lazy_epoch") if repeat%2==0 else ("lazy_epoch","full_direct")
                        for method in order:
                            save(current={"n":n,"mode":mode,"method":method,"repeat":repeat})
                            opts={"n":n,"bits":512,"mode":mode,"diag":0,"tag":"virtual_scale_comparison"}
                            # The case helper fixes its own result file; retain
                            # those rows there with a separate unambiguous tag.
                            if repeat<0:study.case(runtime,method,repeats=0,warmups=1,**opts)
                            else:study.case(runtime,method,repeats=1,repeat_offset=repeat,**opts)
                state["completed"].append(n);save()
        save(finished=True,current=None)
        print("VIRTUAL_SCALE_COMPLETE",flush=True)
    except BaseException as error:
        save(last_error=repr(error));raise

if __name__=="__main__":main()
