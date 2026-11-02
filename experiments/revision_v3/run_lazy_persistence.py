"""Validate persisted virtual epochs, then measure fresh paired stored-state controls."""
from pathlib import Path
import argparse,fcntl,json,random,time
import mpc_driver as core
import persisted_driver as eager
import persisted_lazy_driver as virtual

ROOT=Path(__file__).resolve().parent

def main(after_projection):
    path=ROOT/"results/lazy_persistence_status.json"
    state={"finished":False,"current":"waiting_for_projection" if after_projection else "starting","correctness_passed":False,"last_error":None}
    def save(**values):state.update(values);path.write_text(json.dumps(state,indent=2))
    save()
    try:
        if after_projection:
            while True:
                prior_path=ROOT/"results/projection_facenet_status.json"
                if prior_path.exists():
                    try:prior=json.loads(prior_path.read_text())
                    except json.JSONDecodeError:time.sleep(1);continue
                    if prior.get("finished") or prior.get("last_error"):
                        save(preceding_projection_error=prior.get("last_error"));break
                time.sleep(5)
        runtime=Path(json.loads((ROOT.parent/"mpc_logs/runtime.json").read_text())["runtime"])
        with (runtime/".msle_v3_driver.lock").open("w") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            core.setup_runtime()
            save(current="persisted_lifecycle")
            virtual.main([8,128],3)
            save(correctness_passed=True,current="paired_stored_state_controls")
            eager.audit_common_core();virtual.audit_common_core()
            for repeat in range(-1,5):
                order=[("eager",eager),("virtual",virtual)]
                if repeat%2:order.reverse()
                for name,driver in order:
                    save(current={"phase":"paired_stored_state_controls","n":128,"method":name,"repeat":repeat})
                    fixture=driver.initialize(runtime,128,0)
                    driver.execute(runtime,fixture,1,diag=0,repeat=repeat,warmup=repeat<0,tag="paired_virtual_persistence")
                    driver.execute(runtime,fixture,2,diag=1,repeat=max(0,repeat),tag="paired_persistence_post_rekey_check")
        save(finished=True,current=None)
        print("VIRTUAL_PERSISTENCE_COMPLETE",flush=True)
    except BaseException as error:
        save(last_error=repr(error));raise

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--after-projection",action="store_true")
    main(parser.parse_args().after_projection)
