"""Confirm the vectorized candidate preparation with the old scalar oracle."""
from pathlib import Path
import argparse,fcntl,json,time
import numpy as np
import mpc_driver as core
import run_lazy_epoch as virtual

ROOT=Path(__file__).resolve().parent
ORIGINAL_INPUT=core.INPUT_PATH
SOURCES={"original":"msle_system","full_vector":"msle_vector_poly_query_system","bucket_vector":"msle_vector_bucket_poly_query_system","virtual_bucket_vector":"msle_vector_lazy_bucket_poly_query_system"}

def case(runtime,method,**opts):
    virtual.select("lazy_epoch" if method=="virtual_bucket_vector" else "full_direct")
    rows=core.system_case(runtime,source_name=SOURCES[method],transition=0,result_file="vector_query_runs.jsonl",**opts)
    if opts.get("diag",1) and method!="original":
        for row in rows:assert "MSLE_CANDIDATES exact_membership_ok=1" in (ROOT/row["raw_log"]).read_text()
    return rows

def main():
    path=ROOT/"results/vector_query_status.json"
    state={"finished":False,"correctness_passed":False,"current":"waiting_for_first_polynomial_series","last_error":None}
    def save(**values):state.update(values);path.write_text(json.dumps(state,indent=2))
    save()
    try:
        while True:
            prior_path=ROOT/"results/poly_query_status.json"
            if prior_path.exists():
                try:prior=json.loads(prior_path.read_text())
                except json.JSONDecodeError:time.sleep(1);continue
                if prior.get("finished") or prior.get("last_error"):
                    save(preceding_poly_error=prior.get("last_error"));break
            time.sleep(5)
        runtime=Path(json.loads((ROOT.parent/"mpc_logs/runtime.json").read_text())["runtime"])
        with (runtime/".msle_v3_driver.lock").open("w") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);runtime=core.setup_runtime()
            save(current="candidate_correctness")
            for method in ("full_vector","bucket_vector"):
                case(runtime,method,n=2,bits=64,mode=3,tag="vector_candidate_correctness")
                case(runtime,method,n=8,bits=512,mode=3,tag="vector_real_correctness")
            case(runtime,"virtual_bucket_vector",n=8,bits=512,mode=4,tag="vector_composed_correctness")
            rng=np.random.default_rng(20261030)
            probe=rng.integers(0,2,size=(1,64),dtype=np.uint8)
            gallery=np.repeat(probe,3,axis=0)
            gallery[0,::8]^=1;gallery[1,::4]^=1;gallery[2,1::4]^=1
            target=ROOT/"data/vector_correctness_only_mixed_n3.npz"
            np.savez_compressed(target,gallery_roots=gallery,probe_roots=probe,gallery_labels=np.arange(1,4))
            core.INPUT_PATH=target
            for method in ("full_vector","bucket_vector"):case(runtime,method,n=3,bits=64,mode=3,tag="synthetic_mixed_bucket_edges")
            core.INPUT_PATH=ORIGINAL_INPUT
            save(correctness_passed=True)
            for repeat in range(-1,5):
                methods=["original","bucket_vector","full_vector"]
                shift=(repeat+1)%3;order=methods[shift:]+methods[:shift]
                if repeat%2:order.reverse()
                for method in order:
                    save(current={"n":8,"method":method,"repeat":repeat})
                    opts={"n":8,"bits":512,"mode":3,"diag":0,"tag":"vector_query_comparison"}
                    if repeat<0:case(runtime,method,repeats=0,warmups=1,**opts)
                    else:case(runtime,method,repeats=1,repeat_offset=repeat,**opts)
            for n in (32,128):
                for repeat in range(-1,3):
                    save(current={"n":n,"method":"bucket_vector","repeat":repeat})
                    opts={"n":n,"bits":512,"mode":3,"diag":0,"tag":"vector_query_scale"}
                    if repeat<0:case(runtime,"bucket_vector",repeats=0,warmups=1,**opts)
                    else:case(runtime,"bucket_vector",repeats=1,repeat_offset=repeat,**opts)
        save(finished=True,current=None);print("VECTOR_QUERY_COMPLETE",flush=True)
    except BaseException as error:
        save(last_error=repr(error));raise

if __name__=="__main__":main()
