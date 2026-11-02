"""Measure candidate-membership optimization after exact flag agreement checks."""
from pathlib import Path
import argparse,fcntl,json,random,time
import numpy as np
import mpc_driver as core
import run_lazy_epoch as virtual

ROOT=Path(__file__).resolve().parent
METHODS={"original":"msle_system","polynomial":"msle_poly_query_system","bucket_polynomial":"msle_bucket_poly_query_system","virtual_bucket_polynomial":"msle_lazy_bucket_poly_query_system"}
ORIGINAL_INPUT=core.INPUT_PATH

def case(runtime,method,**kwargs):
    virtual.select("lazy_epoch" if method=="virtual_bucket_polynomial" else "full_direct")
    rows=core.system_case(runtime,source_name=METHODS[method],transition=0,result_file="poly_query_runs.jsonl",**kwargs)
    if kwargs.get("diag",1) and kwargs.get("mode",0) in (3,4) and method!="original":
        for row in rows:assert "MSLE_CANDIDATES exact_membership_ok=1" in (ROOT/row["raw_log"]).read_text(),"Candidate flags disagree even if fallback happens to return the right identity"
    return rows

def main(after_aes):
    path=ROOT/"results/poly_query_status.json"
    state={"finished":False,"correctness_passed":False,"current":"waiting_for_AES" if after_aes else "starting","last_error":None}
    def save(**values):state.update(values);path.write_text(json.dumps(state,indent=2))
    save()
    try:
        if after_aes:
            while True:
                prior_path=ROOT/"results/aes_baseline_status.json"
                if prior_path.exists():
                    try:prior=json.loads(prior_path.read_text())
                    except json.JSONDecodeError:time.sleep(1);continue
                    if prior.get("finished") or prior.get("last_error"):
                        save(preceding_aes_error=prior.get("last_error"));break
                time.sleep(5)
        runtime=Path(json.loads((ROOT.parent/"mpc_logs/runtime.json").read_text())["runtime"])
        with (runtime/".msle_v3_driver.lock").open("w") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            runtime=core.setup_runtime()
            save(current="candidate_correctness")
            for method in ("polynomial","bucket_polynomial"):
                case(runtime,method,n=2,bits=64,mode=3,tag="poly_correctness")
                case(runtime,method,n=8,bits=512,mode=3,tag="poly_real_correctness")
            case(runtime,"virtual_bucket_polynomial",n=8,bits=512,mode=4,tag="poly_composed_correctness")
            for kind in ("none","all","selective"):
                gallery=np.zeros((2,64),dtype=np.uint8)
                probe=np.ones((1,64),dtype=np.uint8) if kind=="none" else np.zeros((1,64),dtype=np.uint8)
                if kind=="selective":gallery[1]=1
                target=ROOT/f"data/poly_correctness_only_{kind}.npz"
                np.savez_compressed(target,gallery_roots=gallery,probe_roots=probe,gallery_labels=np.asarray([1,2]))
                core.INPUT_PATH=target
                for method in ("polynomial","bucket_polynomial"):case(runtime,method,n=2,bits=64,mode=3,tag="synthetic_membership_edges")
            core.INPUT_PATH=ORIGINAL_INPUT
            save(correctness_passed=True,current="controlled_query_comparison")
            methods=["original","polynomial","bucket_polynomial"]
            random.Random(20261030).shuffle(methods)
            for repeat in range(-1,5):
                shift=(repeat+1)%3;order=methods[shift:]+methods[:shift]
                if repeat%2:order.reverse()
                for method in order:
                    save(current={"n":8,"method":method,"repeat":repeat})
                    opts={"n":8,"bits":512,"mode":3,"diag":0,"tag":"poly_query_comparison"}
                    if repeat<0:case(runtime,method,repeats=0,warmups=1,**opts)
                    else:case(runtime,method,repeats=1,repeat_offset=repeat,**opts)
            for n in (32,128):
                for repeat in range(-1,3):
                    save(current={"n":n,"method":"bucket_polynomial","repeat":repeat})
                    opts={"n":n,"bits":512,"mode":3,"diag":0,"tag":"poly_query_scale"}
                    if repeat<0:case(runtime,"bucket_polynomial",repeats=0,warmups=1,**opts)
                    else:case(runtime,"bucket_polynomial",repeats=1,repeat_offset=repeat,**opts)
        save(finished=True,current=None)
        print("POLYNOMIAL_QUERY_COMPLETE",flush=True)
    except BaseException as error:
        save(last_error=repr(error));raise

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--after-aes",action="store_true")
    main(parser.parse_args().after_aes)
