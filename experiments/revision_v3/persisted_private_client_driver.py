"""Actual per-party persistence lifecycle, initialized by an external fixture.

Never run concurrently with mpc_driver.py: both use this study's Player-Data
and Persistence directories. No computing party receives plaintext DB/index.
"""
from pathlib import Path
import argparse,hashlib,json,re,secrets,time
import numpy as np
from reference import ROOT,P,key_contributions,unique_locators,masks,evolve,digest
from mpc_driver import setup_runtime,write_inputs,run
INPUT_OVERRIDE=None
from reference import masks as raw_masks,evolve as prp_evolve
def masks(keys,locators,bits=512):
    return raw_masks(keys,prp_evolve(keys[0],locators),bits)
def evolve(key,locators):
    return list(locators)


def audit_common_core():
    result=json.loads((ROOT/"results/private_client_source_audit.json").read_text())
    assert result["sources"]["msle_private_client_system"]==digest(ROOT/"mpc/msle_private_client_system.mpc")
    return result


def compile_case(runtime,name,args,folder):
    folder.mkdir(parents=True,exist_ok=True)
    source=ROOT/f"mpc/{name}.mpc"
    key=digest(source)+digest(ROOT/"parameters.json")+digest(ROOT/"backend_config.json")
    program=name+"-"+"-".join(map(str,args))
    stamp=folder/"compile_stamp.json"
    if not stamp.exists() or json.loads(stamp.read_text()).get("key")!=key or not (runtime/f"Programs/Schedules/{program}.sch").exists():
        run(["python3","compile.py","-P",P,"-b",64,"-M",name,*args],runtime,folder/"compile.log",1800)
        stamp.write_text(json.dumps({"key":key,"program":program}))
    return program

def initialize(runtime,n,protection):
    bits=512;c=min(n,8+(n+3)//4);m=128*16*c;kcount=1 if protection else 9
    data_path=INPUT_OVERRIDE if INPUT_OVERRIDE is not None else (ROOT.parent/"inputs/celeba_128_binary_roots.npz" if n<=128 else ROOT.parent/f"revision_v2/data/lfw_gallery_n{n}.npz")
    with np.load(data_path) as data:
        gallery=data["gallery_roots"][:n].copy();labels=data["gallery_labels"][:n].copy();probes=data["probe_roots"].copy()
    locs=unique_locators(n+m);db_locs=locs[:n];index=locs[n:];valid=[0]*m
    _,keys=key_contributions();protected=gallery if protection else gallery^masks(keys,db_locs)
    counts=[0]*(128*16)
    for row,root in enumerate(gallery):
        for block in range(128):
            value=sum(int(root[4*block+b])<<b for b in range(4));bucket=16*block+value
            if counts[bucket]>=c:raise RuntimeError("Enrollment capacity insufficient")
            slot=bucket*c+counts[bucket];index[slot]=db_locs[row];valid[slot]=1;counts[bucket]+=1
    state=[]
    for row in range(n):state.extend([int(db_locs[row]),int(labels[row]),row+1,*map(int,protected[row])])
    state.extend(index);state.extend(valid);state.extend(keys[:kcount])
    before=time.monotonic()
    a=[secrets.randbelow(P) for _ in state];b=[secrets.randbelow(P) for _ in state]
    inputs={j:[(v+aa*(j+1)+bb*(j+1)**2)%P for v,aa,bb in zip(state,a,b)] for j in range(5)}
    weights=(5,-10,10,-5,1)
    assert all(sum(weights[j]*inputs[j][i] for j in range(5))%P==v for i,v in enumerate(state))
    write_inputs(runtime,inputs)
    dealing_seconds=time.monotonic()-before
    folder=ROOT/"logs/persisted"/digest(ROOT/"mpc/msle_share_enrollment.mpc")[:12]/f"init_n{n}_p{protection}"
    program=compile_case(runtime,"msle_share_enrollment",[n,512,4,c,protection],folder)
    log=folder/f"run_{time.time_ns()}.log"
    wall=run(["/usr/bin/time","-v","bash","Scripts/shamir.sh",program,"--prime",P],runtime,log,1800)
    if "MSLE_SHARE_ENROLL" not in log.read_text():raise AssertionError("No shared initialization result")
    info={"n":n,"protection":protection,"state_fields":len(state),"client_dealing_seconds":dealing_seconds,"wall_seconds":wall,"client_sharing_degree":2,"client_sharing_reconstruction_checked_all_fields":True,"computing_party_input":"one degree-two sharing evaluation per state field; no plaintext state","input_sha256":digest(data_path),"raw_log":str(log.relative_to(ROOT))}
    with (ROOT/"results/private_client_initializations.jsonl").open("a") as f:f.write(json.dumps(info)+"\n")
    src=valid.index(1);dst=next(i for i,v in enumerate(valid) if not v and i//c!=src//c)
    return {"n":n,"c":c,"m":m,"keys":keys,"locs":db_locs,"protected":protected,"gallery":gallery,"labels":labels,"probes":probes,"protection":protection,"state_fields":len(state),"src":src,"dst":dst,"input_sha256":digest(data_path)}

def execute(runtime,fixture,mode,diag=0,repeat=0,warmup=False,tag="performance",fault=0,exact=False,threshold=512):
    n=fixture["n"];protection=fixture["protection"];kc=1 if protection else 9;transition=mode in (0,1,4)
    contributions,newkeys=key_contributions()
    by_party={j:list(contributions[j][:kc]) if transition else [] for j in range(5)}
    probe=fixture["gallery"][0] if exact else fixture["probes"][max(0,repeat)]
    score=np.count_nonzero(fixture["gallery"]!=probe,axis=1);winner=int(np.argmin(score))
    want=int(fixture["labels"][winner]) if score[winner]<=threshold else -1
    output_pad=0
    query_dealing_seconds=0.0
    if mode!=1:
        query_started=time.monotonic()
        output_pad=secrets.randbelow(P)
        values=[*map(int,probe),threshold,output_pad]
        first=[secrets.randbelow(P) for _ in values]
        second=[secrets.randbelow(P) for _ in values]
        evaluations=[[(value+a*(party+1)+b*(party+1)**2)%P for value,a,b in zip(values,first,second)] for party in range(5)]
        weights=(5,-10,10,-5,1)
        assert all(sum(weights[j]*evaluations[j][i] for j in range(5))%P==value for i,value in enumerate(values))
        for party in range(5):by_party[party].extend(evaluations[party])
        query_dealing_seconds=time.monotonic()-query_started

    if diag:
        if transition:
            # Diagnostic transition is run immediately after fresh fixture
            # initialization, before its row order becomes secret-shuffled.
            nextloc=evolve(newkeys[0],fixture["locs"])
            nextc=fixture["gallery"] if protection else fixture["gallery"]^masks(newkeys,nextloc)
            by_party[0].extend(nextloc);by_party[0].extend(map(int,nextc.T.reshape(-1)))
        by_party[0].extend([want,int(score[winner]),0 if fault else 1])
    if transition:
        for j in range(5):by_party[j].extend([0]*fixture["state_fields"])
    write_inputs(runtime,by_party)
    args=[n,512,4,fixture["c"],mode,protection,0,1,fault,fixture["src"],fixture["dst"],diag]
    folder=ROOT/"logs/persisted"/digest(ROOT/"mpc/msle_private_client_system.mpc")[:12]/tag/("-".join(map(str,args)))
    program=compile_case(runtime,"msle_private_client_system",args,folder)
    log=folder/f"run_r{repeat}_{time.time_ns()}.log"
    started=time.time()
    wall=run(["/usr/bin/time","-v","bash","Scripts/shamir.sh",program,"--prime",P],runtime,log,1800)
    contents=log.read_text()
    match=re.search(r"relation=(\d+) masked_identity=(-?\d+) state_ok=(\d+) query_ok=(\d+)",contents)
    if not match:raise AssertionError("Missing persisted-state result")
    relation,masked_identity,state_ok,query_ok=map(int,match.groups())
    identity=(masked_identity-output_pad)%P
    if identity==P-1:identity=-1
    accepted=int(identity!=-1)
    assert " identity=" not in contents and " accepted=" not in contents

    if relation!=(0 if fault else 1) or state_ok!=1 or query_ok!=1 or (mode!=1 and identity!=want):raise AssertionError("Persisted-state/reference mismatch: "+str(log))
    def number(pattern):
        found=re.search(pattern,contents);return float(found[1]) if found else None
    row={"n":n,"mode":mode,"protection":protection,"diag":diag,"fault":fault,"repeat":repeat,"warmup":warmup,"tag":tag,"family":"private_client_state","relation":relation,"accepted":accepted,"identity":identity,"state_ok":state_ok,"query_ok":query_ok,"wall_seconds":wall,"full_vm_seconds":number(r"\nTime = ([\d.]+) seconds"),"global_communication_mb":number(r"Global data sent = ([\d.]+) MB"),"party0_rounds":number(r"Data sent = .*?in ~(\d+) rounds"),"max_rss_single_child_kib":number(r"Maximum resident set size \(kbytes\): (\d+)"),"started_unix":started,"finished_unix":time.time(),"raw_log":str(log.relative_to(ROOT)),"source_sha256":digest(ROOT/"mpc/msle_private_client_system.mpc"),"parameters_sha256":digest(ROOT/"parameters.json"),"backend_sha256":digest(ROOT/"backend_config.json"),"input_sha256":fixture["input_sha256"],"state_fields":fixture["state_fields"],"whole_state_read_from_own_share_file":True,"plaintext_db_or_index_input":False,"plaintext_probe_input":False,"client_private_result":True,"diagnostic_oracles_present":bool(diag),"production_output_privacy_claim":not bool(diag),"query_client_sharing_degree":2,"query_client_dealing_seconds":query_dealing_seconds,"query_sharing_reconstruction_checked_all_fields":bool(mode!=1)}
    for t in (30,31,11,12,13,14,15,16,20,21,22,23):
        row[f"timer{t}_seconds"]=number(rf"Time{t} = ([\d.]+) seconds")
        row[f"timer{t}_party0_mb"]=number(rf"Time{t} = [\d.]+ seconds \(([\d.]+) MB")
    with (ROOT/"results/private_client_runs.jsonl").open("a") as f:f.write(json.dumps(row)+"\n")
    print(json.dumps({k:row[k] for k in ("n","mode","protection","diag","fault","full_vm_seconds","global_communication_mb","state_ok","query_ok")}),flush=True)
    return row

def main(ns,repeats):
    audit=audit_common_core();runtime=setup_runtime()
    state={"finished":False,"core_audit":audit,"completed":[]}
    status=ROOT/"results/private_client_status.json"
    for n in ns:
        for protection in (0,1):
            state["current"]={"n":n,"protection":protection};status.write_text(json.dumps(state,indent=2))
            fixture=initialize(runtime,n,protection)
            execute(runtime,fixture,0,diag=1,tag="correctness")
            execute(runtime,fixture,2,diag=1,tag="correctness_exact",exact=True,threshold=0)
            execute(runtime,fixture,2,diag=1,tag="correctness_reject",threshold=0)
            if n==8 and protection==0:execute(runtime,fixture,3,diag=1,tag="indexed_correctness")
            for mode in (1,2):
                for repeat in range(-1,repeats):
                    execute(runtime,fixture,mode,diag=0,repeat=repeat,warmup=repeat<0)
                    if mode==1:execute(runtime,fixture,2,diag=1,repeat=max(0,repeat),tag="post_rekey_verification")
            state["completed"].append({"n":n,"protection":protection});status.write_text(json.dumps(state,indent=2))
    fixture=initialize(runtime,8,0)
    execute(runtime,fixture,0,diag=1,fault=1,tag="private_client_rollback")
    execute(runtime,fixture,2,diag=1,tag="private_client_rollback_reload")
    state.update(finished=True,current=None);status.write_text(json.dumps(state,indent=2))
    print("PERSISTED_LIFECYCLE_COMPLETE",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--n",nargs="+",type=int,default=[8,128]);parser.add_argument("--repeats",type=int,default=3);args=parser.parse_args();main(args.n,args.repeats)
