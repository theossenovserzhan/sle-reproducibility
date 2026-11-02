"""WSL orchestration for corrected MPC evidence using the existing runtime."""
from pathlib import Path
import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time

import numpy as np

from reference import ROOT, P, PARAMETERS, encrypt, key_contributions, digest, masks, evolve, unique_locators


def run(argv, runtime, log, timeout=900):
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log.open("w", encoding="utf-8") as stream:
        stream.write(json.dumps({"argv": list(map(str, argv)), "cwd": str(runtime)}) + "\n")
        stream.flush()
        done = subprocess.run(list(map(str, argv)), cwd=runtime, stdout=stream,
                              stderr=subprocess.STDOUT, timeout=timeout)
    elapsed = time.monotonic() - started
    print(f"{log.name}: exit={done.returncode}, wall_s={elapsed:.2f}", flush=True)
    if done.returncode:
        print(log.read_text(errors="replace")[-9000:], flush=True)
        raise RuntimeError(str(log))
    return elapsed


def write_inputs(runtime, by_party):
    for party in range(5):
        path = runtime / f"Player-Data/Input-P{party}-0"
        path.write_text(" ".join(map(str, by_party.get(party, []))) + "\n")


def setup_runtime():
    runtime = Path(json.loads((ROOT.parent / "mpc_logs/runtime.json").read_text())["runtime"])
    if not (runtime / "shamir-party.x").is_file():
        raise RuntimeError("Previously built persistent MPC runtime unavailable")
    shutil.copy2(ROOT / "parameters.json", runtime / "msle_parameters.json")
    for source in (ROOT / "mpc").glob("*.mpc"):
        shutil.copy2(source, runtime / "Programs/Source" / source.name)
    os.environ.update(PLAYERS="5", THRESHOLD="2")
    return runtime


def primitive_test(runtime):
    log_dir = ROOT / "logs/primitives"
    rng = random.Random(20261029)
    values = [0, 1, P-1, P-2, (1<<64)-1, 1<<64, 1<<127, (1<<127)-1]
    values += [rng.randrange(P) for _ in range(8)]
    n = len(values)
    contributions, keys = key_contributions()
    expected = [encrypt(x, keys[0]) for x in values]
    words = [encrypt(x, keys[1]) for x in values]
    expected_bits = [(x >> bit) & 1 for bit in range(64) for x in words]
    by_party = {j: list(row) for j, row in enumerate(contributions)}
    by_party[0] = values + by_party[0] + expected + expected_bits
    write_inputs(runtime, by_party)
    run(["python3", "compile.py", "-P", P, "-M", "msle_primitives", n], runtime,
        log_dir / "compile.log")
    run(["/usr/bin/time", "-v", "bash", "Scripts/shamir.sh", f"msle_primitives-{n}", "--prime", P], runtime,
        log_dir / "run.log", 600)
    text = (log_dir / "run.log").read_text()
    match = re.search(r"MSLE_PRIMITIVES n=\d+ cipher_ok=(\d+) mask_bits_ok=(\d+) full_field_eq_ok=(\d+) shuffle_rows_ok=(\d+) shuffle_multiset_ok=(\d+)", text)
    if not match or match.groups() != ("1",)*5:
        raise AssertionError("Primitive/reference agreement failed")
    result = {"all_pass": True, "test_values": n, "mask_bits_checked": 64*n,
              "prime": str(P), "field_bits": P.bit_length(), "rounds": PARAMETERS["rounds"],
              "parameters_sha256": digest(ROOT / "parameters.json"),
              "reference_sha256": digest(ROOT / "reference.py"),
              "circuit_sha256": digest(ROOT / "mpc/msle_primitives.mpc"),
              "checks": ["full-field MiMC oracle agreement", "canonical bit extraction including >2^64", "full-field exact zero test", "secret row shuffle association and multiset"]}
    target = ROOT / "results/primitives.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


INPUT_PATH=ROOT.parent / "inputs/celeba_128_binary_roots.npz"


def system_inputs(runtime, n, bits, mode, protection, maintenance, fault, diag, query_row=0, threshold=None, exact_probe=False):
    do_transition=mode in (0,1,4)
    indexed=mode in (3,4)
    key_count=1 if protection else 9
    with np.load(INPUT_PATH) as data:
        gallery = data["gallery_roots"][:n,:bits]
        labels = data["gallery_labels"][:n]
        probe = gallery[0] if exact_probe else data["probe_roots"][query_row,:bits]
    if len(gallery) != n:
        raise ValueError("requested real gallery exceeds frozen data")
    block_bits = 4
    blocks,values = bits//block_bits,16
    capacity = min(n,8+(n+3)//4)
    m = blocks*values*capacity
    old_contributions,old_keys = key_contributions()
    new_contributions,new_keys = key_contributions()
    all_locators = unique_locators(n+m)
    db_locs = all_locators[:n]
    old_c = gallery if protection else gallery ^ masks(old_keys,db_locs,bits)
    new_locs = evolve(new_keys[0],db_locs)
    new_c = gallery if protection else gallery ^ masks(new_keys,new_locs,bits)
    counts = np.zeros(blocks*values,dtype=int)
    index_locs = all_locators[n:]
    valid = [0]*m
    for row,root in enumerate(gallery):
        for block in range(blocks):
            value = sum(int(root[block*block_bits+b]) << b for b in range(block_bits))
            bucket = block*values+value
            slot = int(counts[bucket])
            if slot >= capacity:
                raise RuntimeError("Declared public capacity insufficient; enrollment must reject/reconfigure")
            index_locs[bucket*capacity+slot] = db_locs[row]
            valid[bucket*capacity+slot] = 1
            counts[bucket] += 1
    src = valid.index(1)
    dst = next(i for i,v in enumerate(valid) if not v and i//capacity != src//capacity)
    tags = list(range(1,n+1))
    scores = np.count_nonzero(gallery != probe,axis=1)
    winner = int(np.argmin(scores))
    threshold = bits if threshold is None else threshold
    oracle_label = int(labels[winner]) if scores[winner] <= threshold else -1
    oracle_relation = 1 if mode==2 or fault==0 else 0
    by_party = {j:[] for j in range(5)}
    by_party[0].extend(map(int,db_locs))
    by_party[0].extend(map(int,old_c.T.reshape(-1)))
    if do_transition or indexed:
        by_party[0].extend(map(int,index_locs))
        by_party[0].extend(valid)
    by_party[0].extend(map(int,labels))
    by_party[0].extend(tags)
    for j in range(5):
        by_party[j].extend(old_contributions[j][:key_count])
        if do_transition:
            by_party[j].extend(new_contributions[j][:key_count])
    if mode != 1:
        by_party[1].extend(map(int,probe))
        by_party[1].append(threshold)
    if diag:
        if do_transition:
            by_party[0].extend(new_locs)
            by_party[0].extend(map(int,new_c.T.reshape(-1)))
        by_party[0].extend([oracle_label,int(scores[winner]),oracle_relation])
    state_elements = n*(bits+3)+2*m+key_count
    if do_transition and maintenance:
        for j in range(5):
            by_party[j].extend([0]*state_elements)
    write_inputs(runtime,by_party)
    info = {"n":n,"root_bits":bits,"block_bits":block_bits,"capacity":capacity,"index_slots":m,
            "required_capacity":int(counts.max()),"mode":mode,"protection":protection,
            "maintenance":maintenance,"fault":fault,"diag":diag,"src":src,"dst":dst,
            "query_row":query_row,"threshold":threshold,"exact_gallery_probe":exact_probe,
            "expected_identity":oracle_label,"expected_distance":int(scores[winner]),
            "expected_relation":oracle_relation,"gallery_roots_are_protocol_input":bool(protection),
            "input_archive":str(INPUT_PATH),"input_sha256":digest(INPUT_PATH),"key_count":key_count,
            "persistent_state_field_elements_per_party":state_elements,
            "logical_state_share_bytes_128bit_field_per_party":16*state_elements,
            "key_sampling":"5 independent contributions per key, uniform Fp, secrets.randbelow",
            "contribution_support":"[0,p)","oracle_inputs_in_timed_program":bool(diag)}
    return info


def system_case(runtime, n=2,bits=64,mode=0,protection=0,transition=0,maintenance=1,fault=0,diag=1,
                query_row=0,threshold=None,exact_probe=False,repeats=1,tag="correctness",warmups=0):
    rows=[]
    for repeat in range(-warmups,repeats):
        info=system_inputs(runtime,n,bits,mode,protection,maintenance,fault,diag,query_row+max(0,repeat),threshold,exact_probe)
        cargs=[n,bits,4,info["capacity"],mode,protection,transition,maintenance,fault,info["src"],info["dst"],diag]
        program="msle_system-"+"-".join(map(str,cargs))
        cache_key=digest(ROOT/"mpc/msle_system.mpc")+digest(ROOT/"parameters.json")+digest(ROOT/"backend_config.json")
        logdir=ROOT/"logs/system"/tag/program
        logdir.mkdir(parents=True,exist_ok=True)
        stamp=logdir/"compile_stamp.json"
        if not stamp.exists() or json.loads(stamp.read_text()).get("source_key")!=cache_key or not (runtime/f"Programs/Schedules/{program}.sch").exists():
            run(["python3","compile.py","-P",P,"-b",64,"-M","msle_system",*cargs],runtime,logdir/"compile.log",1800)
            stamp.write_text(json.dumps({"source_key":cache_key,"args":cargs}))
        (logdir/f"input_r{repeat}.json").write_text(json.dumps(info,indent=2))
        log=logdir/f"run_r{repeat}.log"
        wall=run(["/usr/bin/time","-v","bash","Scripts/shamir.sh",program,"--prime",P],runtime,log,1800)
        contents=log.read_text()
        match=re.search(r"MSLE_SYSTEM n=\d+ d=\d+ mode=\d+ protection=\d+ transition=\d+ maintenance=\d+ fault=\d+ relation=(\d+) accepted=(\d+) identity=(-?\d+) state_ok=(\d+) query_ok=(\d+)",contents)
        if not match:
            raise AssertionError(f"Missing system result in {log}")
        relation,accepted,identity,state_ok,query_ok=map(int,match.groups())
        if relation!=info["expected_relation"] or state_ok!=1 or query_ok!=1 or (mode!=1 and identity!=info["expected_identity"]):
            raise AssertionError(f"System/reference mismatch in {log}: {match.groups()}")
        def number(pattern):
            result=re.search(pattern,contents)
            return float(result[1]) if result else None
        row={**info,"transition":transition,"repeat":repeat,"warmup":repeat<0,"tag":tag,"relation_ok":relation,
             "accepted":accepted,"identity":identity,"state_ok":state_ok,"query_ok":query_ok,
             "wall_seconds":wall,"full_vm_seconds":number(r"\nTime = ([\d.]+) seconds"),
             "global_communication_mb":number(r"Global data sent = ([\d.]+) MB"),
             "party0_rounds":number(r"Data sent = .*?in ~(\d+) rounds"),
             "max_rss_single_child_kib":number(r"Maximum resident set size \(kbytes\): (\d+)"),
             "parameters_sha256":digest(ROOT/"parameters.json"),"circuit_sha256":digest(ROOT/"mpc/msle_system.mpc"),
             "backend_sha256":digest(ROOT/"backend_config.json"),"compiler_budget":64}
        for timer in (30,11,12,13,14,15,16,20,21,22,23):
            row[f"timer{timer}_seconds"]=number(rf"Time{timer} = ([\d.]+) seconds")
            row[f"timer{timer}_party0_mb"]=number(rf"Time{timer} = [\d.]+ seconds \(([\d.]+) MB")
        rows.append(row)
        target=ROOT/"results/system_runs.jsonl"
        target.parent.mkdir(exist_ok=True)
        with target.open("a") as stream:
            stream.write(json.dumps(row)+"\n")
        print(json.dumps({k:row[k] for k in ["n","root_bits","mode","transition","fault","diag","state_ok","query_ok","full_vm_seconds","global_communication_mb"]}),flush=True)
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["primitives","system-smoke","correctness","performance","sort-smoke","indexed-smoke","shared-smoke"], required=True)
    parser.add_argument("--n",type=int,nargs="+",default=[8,32,128])
    parser.add_argument("--repeats",type=int,default=3)
    parser.add_argument("--input",type=Path,default=INPUT_PATH)
    parser.add_argument("--modes",type=int,nargs="+",default=[1,2])
    parser.add_argument("--protection",type=int,choices=[0,1],default=0)
    parser.add_argument("--transition",type=int,choices=[0,1],default=0)
    args = parser.parse_args()
    INPUT_PATH=args.input.resolve()
    runtime=setup_runtime()
    if args.phase=="primitives":
        primitive_test(runtime)
    elif args.phase=="system-smoke":
        system_case(runtime)
    elif args.phase=="sort-smoke":
        system_case(runtime,n=2,bits=64,mode=0,transition=1,tag="sort_correctness_memory_bounded")
    elif args.phase=="indexed-smoke":
        system_case(runtime,n=2,bits=64,mode=3,tag="indexed_correctness")
        system_case(runtime,n=8,bits=512,mode=4,tag="indexed_correctness")
    elif args.phase=="shared-smoke":
        system_case(runtime,n=8,bits=512,mode=0,protection=1,tag="shared_root_correctness")
    elif args.phase=="correctness":
        for mode in (0,1,2):
            system_case(runtime,n=8,bits=512,mode=mode,tag="correctness")
        for fault in range(1,9):
            system_case(runtime,n=4,bits=64,mode=0,fault=fault,tag="faults")
        system_case(runtime,n=8,bits=512,mode=2,threshold=0,tag="reject_control")
        system_case(runtime,n=8,bits=512,mode=2,threshold=0,exact_probe=True,tag="accept_control")
    else:
        for n in args.n:
            for mode in args.modes:
                system_case(runtime,n=n,bits=512,mode=mode,diag=0,repeats=args.repeats,warmups=1,
                            protection=args.protection,transition=args.transition,tag="performance")
