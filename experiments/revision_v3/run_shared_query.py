"""Stored-state tests with private client share input at all five computing parties."""
from pathlib import Path
import fcntl,json,time
import mpc_driver as core
import persisted_lazy_driver as owner_input
import persisted_shared_query_driver as shared_input

ROOT=Path(__file__).resolve().parent

def main():
    path=ROOT/"results/shared_query_status.json"
    state={"finished":False,"correctness_passed":False,"current":"waiting_for_frontend_and_vector_tests","last_error":None}
    def save(**values):state.update(values);path.write_text(json.dumps(state,indent=2))
    save()
    try:
        while True:
            paths=[ROOT/"results/vector_query_status.json",ROOT/"results/sface_status.json",ROOT/"results/lazy_persistence_status.json"]
            if all(p.exists() for p in paths):
                try:vector,sface,persisted=[json.loads(p.read_text()) for p in paths]
                except json.JSONDecodeError:time.sleep(1);continue
                for name,prior in (("vector",vector),("persisted",persisted)):
                    if prior.get("last_error"):raise RuntimeError(name+" validation must be repaired: "+prior["last_error"])
                if vector.get("finished") and persisted.get("finished") and (sface.get("finished") or sface.get("last_error")):break
            time.sleep(5)
        runtime=Path(json.loads((ROOT.parent/"mpc_logs/runtime.json").read_text())["runtime"])
        with (runtime/".msle_v3_driver.lock").open("w") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);runtime=core.setup_runtime()
            shared_input.audit_common_core()
            save(current="shared_query_correctness")
            fixture=shared_input.initialize(runtime,8,0)
            row=shared_input.execute(runtime,fixture,4,diag=1,tag="shared_query_correctness")
            assert "MSLE_CANDIDATES exact_membership_ok=1" in (ROOT/row["raw_log"]).read_text()
            shared_input.execute(runtime,fixture,2,diag=1,exact=True,threshold=0,tag="shared_query_accept_control")
            shared_input.execute(runtime,fixture,2,diag=1,threshold=0,tag="shared_query_reject_control")
            fixture=shared_input.initialize(runtime,8,0)
            shared_input.execute(runtime,fixture,0,diag=1,fault=1,tag="shared_query_rollback")
            shared_input.execute(runtime,fixture,2,diag=1,tag="shared_query_rollback_reload")
            fixture=shared_input.initialize(runtime,128,0)
            shared_input.execute(runtime,fixture,0,diag=1,tag="shared_query_large_state_correctness")
            save(correctness_passed=True)
            # Query does not modify persistent state, so both input interfaces
            # read the same already-rekeyed state throughout paired trials.
            for repeat in range(-1,5):
                methods=[("owner_input",owner_input),("external_shared_client",shared_input)]
                if repeat%2:methods.reverse()
                for name,driver in methods:
                    save(current={"n":128,"method":name,"repeat":repeat})
                    driver.execute(runtime,fixture,2,diag=0,repeat=repeat,warmup=repeat<0,tag="query_input_interface_comparison")
        save(finished=True,current=None);print("FULLY_SHARED_QUERY_COMPLETE",flush=True)
    except BaseException as error:
        save(last_error=repr(error));raise

if __name__=="__main__":main()
