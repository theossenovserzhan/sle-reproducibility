"""Sequential, resumable secure runs; never share Player-Data concurrently."""
from pathlib import Path
import json
import subprocess
import sys
import time
import hashlib

ROOT=Path(__file__).resolve().parent
STEPS=[
    ("current_correctness",["--phase","correctness"]),
    ("backend_correctness",["--phase","backend-correctness"]),
    ("scale_state_correctness",["--phase","scale-correctness","--input",str(ROOT/"data/lfw_gallery_n256.npz")]),
    ("masked_measured",["--phase","performance","--n","8","16","32","64","128","--repeats","3"]),
    ("raw_measured",["--phase","performance","--n","8","32","128","--repeats","3","--protection","1"]),
    ("larger_masked",["--phase","performance","--n","256","--repeats","3","--input",str(ROOT/"data/lfw_gallery_n256.npz")]),
    ("same_contract_sort",["--phase","all","--n","8","16","--repeats","3"]),
    ("indexed_cost",["--phase","performance","--n","8","--modes","3","--repeats","3"]),
    ("large_state_correctness",["--phase","large-correctness"]),
]

if __name__=="__main__":
    state_path=ROOT/"results/secure_batch_status.json"
    fingerprint="".join(hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ("mpc/msle_system.mpc","parameters.json","backend_config.json"))
    state=json.loads(state_path.read_text()) if state_path.exists() else {}
    if state.get("fingerprint")!=fingerprint:
        if state:
            (ROOT/f"source_history/secure_batch_status_{time.time_ns()}.json").write_text(json.dumps(state,indent=2))
        state={"completed":[],"started_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"fingerprint":fingerprint}
    compact_fingerprint="".join(hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ("mpc/msle_compact_sort_system.mpc","compact_baseline_config.json"))
    if state.get("compact_fingerprint")!=compact_fingerprint and "same_contract_sort" in state["completed"]:
        state["completed"].remove("same_contract_sort")
    state["compact_fingerprint"]=compact_fingerprint
    state.update(user_paused=False,pause_reason=None)
    for name,args in STEPS:
        if name in state["completed"]:continue
        state.pop("finished_utc",None)
        state.update(current=name,last_error=None)
        state_path.write_text(json.dumps(state,indent=2))
        print("SECURE_BATCH_START",name,flush=True)
        script="compact_driver.py" if name=="same_contract_sort" else "mpc_driver.py"
        result=subprocess.run([sys.executable,"-u",str(ROOT/script),*args],cwd=ROOT)
        if result.returncode:
            state["last_error"]={"step":name,"returncode":result.returncode}
            state_path.write_text(json.dumps(state,indent=2))
            raise SystemExit(result.returncode)
        state["completed"].append(name)
        state_path.write_text(json.dumps(state,indent=2))
    state.update(current=None,finished_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()))
    state_path.write_text(json.dumps(state,indent=2))
    print("SECURE_BATCH_COMPLETE",flush=True)
