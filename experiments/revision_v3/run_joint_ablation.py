"""Diagnostic component matrix, retaining intentionally unsafe acceptances."""
from pathlib import Path
import argparse,fcntl,json,re,time
import mpc_driver as core

ROOT=Path(__file__).resolve().parent

def case(runtime,n,bits,fault,check_template,check_index,source_name="msle_joint_ablation",transition=0):
    info=core.system_inputs(runtime,n,bits,0,0,1,fault,1)
    args=[n,bits,4,info["capacity"],0,0,transition,1,fault,info["src"],info["dst"],1,check_template,check_index]
    name=source_name;program=name+"-"+"-".join(map(str,args))
    folder=ROOT/"logs/joint_ablation"/name/("-".join(map(str,args)))
    folder.mkdir(parents=True,exist_ok=True)
    stamp=folder/"compile_stamp.json";key=core.digest(ROOT/f"mpc/{name}.mpc")+core.digest(ROOT/"parameters.json")
    if not stamp.exists() or json.loads(stamp.read_text()).get("key")!=key or not (runtime/f"Programs/Schedules/{program}.sch").exists():
        core.run(["python3","compile.py","-P",core.P,"-b",64,"-M",name,*args],runtime,folder/"compile.log",1800)
        stamp.write_text(json.dumps({"key":key}))
    log=folder/f"run_{time.time_ns()}.log"
    wall=core.run(["/usr/bin/time","-v","bash","Scripts/shamir.sh",program,"--prime",core.P],runtime,log,1800)
    text=log.read_text()
    result=re.search(r"relation=(\d+) accepted=(\d+) identity=(-?\d+) state_ok=(\d+) query_ok=(\d+)",text)
    components=re.search(r"MSLE_COMPONENTS template_ok=(\d+) index_ok=(\d+)",text)
    if not result or not components:raise AssertionError("Missing diagnostic output")
    relation,accepted,identity,state,query=map(int,result.groups());tpl,idx=map(int,components.groups())
    expected_tpl=0 if fault==9 else 1
    expected_index=0 if fault==1 else 1
    expected_relation=(expected_tpl if check_template else 1)*(expected_index if check_index else 1)
    assert (tpl,idx,relation)==(expected_tpl,expected_index,expected_relation),(log,tpl,idx,relation)
    unsafe=bool(fault and relation)
    assert state==(0 if unsafe else 1),(log,state,unsafe)
    if not unsafe:assert query==1
    number=lambda pattern:float(re.search(pattern,text)[1])
    row={"n":n,"bits":bits,"fault":fault,"check_template":check_template,"check_index":check_index,"template_ok":tpl,"index_ok":idx,"accepted_candidate":relation,"unsafe_acceptance":unsafe,"state_oracle_ok":state,"query_oracle_ok":query,"wall_seconds":wall,"source_name":name,"transition":transition,
        "vm_seconds":number(r"\nTime = ([\d.]+) seconds"),"global_mb":number(r"Global data sent = ([\d.]+) MB"),"source_sha256":core.digest(ROOT/f"mpc/{name}.mpc"),"parameters_sha256":core.digest(ROOT/"parameters.json"),"input_sha256":info["input_sha256"],"raw_log":str(log.relative_to(ROOT))}
    with (ROOT/"results/joint_ablation_runs.jsonl").open("a") as f:f.write(json.dumps(row)+"\n")
    print(json.dumps(row),flush=True)
    return row

def main():
    runtime=core.setup_runtime()
    with (runtime/".msle_v3_driver.lock").open("w") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        status=ROOT/"results/joint_ablation_status.json";done=[]
        status.write_text(json.dumps({"finished":False,"completed":done}))
        for fault in (0,1,9):
            for a,b in ((1,1),(0,1),(1,0),(0,0)):
                row=case(runtime,4,64,fault,a,b);done.append({k:row[k] for k in ("n","bits","fault","check_template","check_index")})
                status.write_text(json.dumps({"finished":False,"completed":done},indent=2))
        for a,b in ((1,1),(0,1)):
            row=case(runtime,8,512,9,a,b);done.append({k:row[k] for k in ("n","bits","fault","check_template","check_index")})
        status.write_text(json.dumps({"finished":True,"completed":done},indent=2))
        print("JOINT_ABLATION_COMPLETE",flush=True)

if __name__=="__main__":main()
