"""Private client output and fair full-scan/fused/index-only query controls."""
from pathlib import Path
import fcntl,json,time
import numpy as np
import mpc_driver as core
import persisted_private_client_driver as indexed
import persisted_private_fused_driver as fused

ROOT=Path(__file__).resolve().parent

def check_candidates(row):
    assert "MSLE_CANDIDATES exact_membership_ok=1" in (ROOT/row["raw_log"]).read_text()

def main():
    path=ROOT/"results/private_client_status.json"
    state={"finished":False,"correctness_passed":False,"current":"waiting_for_scale_and_shared_query","last_error":None}
    def save(**values):
        state.update(values);path.write_text(json.dumps(state,indent=2))
    save()
    try:
        while True:
            paths=[ROOT/"results/virtual_scale_status.json",ROOT/"results/shared_query_status.json"]
            if all(p.exists() for p in paths):
                try:scale,shared=[json.loads(p.read_text()) for p in paths]
                except json.JSONDecodeError:time.sleep(1);continue
                if shared.get("last_error"):raise RuntimeError("Repair shared client input: "+shared["last_error"])
                if shared.get("finished") and shared.get("correctness_passed") and (scale.get("finished") or scale.get("last_error")):
                    save(preceding_scale_error=scale.get("last_error"));break
            time.sleep(5)
        runtime=Path(json.loads((ROOT.parent/"mpc_logs/runtime.json").read_text())["runtime"])
        with (runtime/".msle_v3_driver.lock").open("w") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);runtime=core.setup_runtime()
            indexed.audit_common_core();fused.audit_common_core()
            save(current="private_output_composed_correctness")
            for name,driver in (("index_polynomial",indexed),("root_fused",fused)):
                fixture=driver.initialize(runtime,8,0)
                check_candidates(driver.execute(runtime,fixture,4,diag=1,tag="private_output_composed_correctness"))
                assert driver.execute(runtime,fixture,2,diag=0,exact=True,threshold=0,tag="private_output_accept_control")["accepted"]==1
                assert driver.execute(runtime,fixture,2,diag=0,threshold=0,tag="private_output_reject_control")["accepted"]==0
            fixture=indexed.initialize(runtime,8,0)
            indexed.execute(runtime,fixture,0,diag=1,fault=1,tag="private_output_rollback")
            indexed.execute(runtime,fixture,2,diag=0,tag="private_output_rollback_reload")
            # Non-power-of-two gallery and mixed/all/no candidate sets. These
            # are explicitly correctness-only; measured trials use real roots.
            rng=np.random.default_rng(20261030)
            probe=rng.integers(0,2,size=(1,512),dtype=np.uint8)
            gallery=np.repeat(probe,3,axis=0)
            gallery[0,::8]^=1;gallery[1,::4]^=1;gallery[2,1::4]^=1
            for label,g,q in (("mixed",gallery,probe),("none",np.zeros((3,512),dtype=np.uint8),np.ones((1,512),dtype=np.uint8)),("all",np.zeros((3,512),dtype=np.uint8),np.zeros((1,512),dtype=np.uint8))):
                target=ROOT/f"data/private_correctness_only_{label}_n3.npz"
                np.savez_compressed(target,gallery_roots=g,probe_roots=q,gallery_labels=np.arange(1,4))
                for name,driver in (("index_polynomial",indexed),("root_fused",fused)):
                    driver.INPUT_OVERRIDE=target
                    fixture=driver.initialize(runtime,3,0)
                    check_candidates(driver.execute(runtime,fixture,3,diag=1,tag="private_synthetic_"+label))
                    driver.INPUT_OVERRIDE=None
            fixture=indexed.initialize(runtime,128,0)
            indexed.execute(runtime,fixture,0,diag=1,tag="private_output_large_state_correctness")
            save(correctness_passed=True)
            # Same persisted, already-rekeyed state and private I/O for all
            # three alternatives. Query runs do not change persistent state.
            methods=[("full_scan",indexed,2),("index_polynomial",indexed,3),("root_fused",fused,3)]
            for repeat in range(-1,5):
                shift=(repeat+1)%len(methods);order=methods[shift:]+methods[:shift]
                if repeat%2:order.reverse()
                for name,driver,mode in order:
                    save(current={"n":128,"method":name,"repeat":repeat})
                    driver.execute(runtime,fixture,mode,diag=0,repeat=repeat,warmup=repeat<0,tag="private_output_query_comparison")
        save(finished=True,current=None);print("PRIVATE_CLIENT_OUTPUT_COMPLETE",flush=True)
    except BaseException as error:
        save(last_error=repr(error));raise

if __name__=="__main__":main()
