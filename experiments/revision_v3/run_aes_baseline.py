"""Sequential standard-encryption comparator with independent AES oracle inputs."""
from pathlib import Path
import argparse,fcntl,json,random,re,shutil,time
import numpy as np
import mpc_driver as core
import aes_input_fixture as fixture
from run_joint_ablation import case as diagnostic_case

ROOT=Path(__file__).resolve().parent
ORIGINAL_INPUTS=core.system_inputs
ORIGINAL_MASKS,ORIGINAL_EVOLVE=core.masks,core.evolve

def case(runtime,cipher,**kwargs):
    stable=cipher.endswith("_stable")
    aes=cipher.startswith("AES_CTR")
    core.masks,core.evolve=ORIGINAL_MASKS,ORIGINAL_EVOLVE
    fixture.evolve=(lambda key,locators:list(locators)) if stable else ORIGINAL_EVOLVE
    if stable and not aes:
        core.masks=lambda keys,locators,bits=512:ORIGINAL_MASKS(keys,ORIGINAL_EVOLVE(keys[0],locators),bits)
        core.evolve=lambda key,locators:list(locators)
    generator=fixture.system_inputs if aes else ORIGINAL_INPUTS
    def inputs(*args,**opts):
        info=generator(*args,**opts)
        info.update(cipher_comparison=cipher,locator_representation="stable secret handles" if stable else "materialized evolving locators")
        return info
    core.system_inputs=inputs
    source=("msle_aes_lazy_system" if stable else "msle_aes_system") if aes else ("msle_lazy_epoch_system" if stable else "msle_compact_sort_positions")
    return core.system_case(runtime,source_name=source,
        extra_config="aes_backend_config.json" if aes else None,result_file="aes_baseline_runs.jsonl",**kwargs)

def kat(runtime):
    vectors=[("000102030405060708090a0b0c0d0e0f","00112233445566778899aabbccddeeff","69c4e0d86a7b0430d8cdb78070b4c55a"),
        ("00"*16,"00"*16,"66e94bd4ef8a2c3b884cfa59ca342b2e"),
        ("2b7e151628aed2a6abf7158809cf4f3c","6bc1bee22e409f96e93d7e117393172a","3ad77bb40d7a3660a89ecaf32466ef97")]
    keys=[int(row[0],16) for row in vectors];messages=[int(row[1],16) for row in vectors]
    outputs=[int(row[2],16) for row in vectors]
    bits=[(word>>bit)&1 for bit in range(128) for word in outputs]
    core.write_inputs(runtime,{0:keys+messages+bits})
    folder=ROOT/"logs/aes_primitives";folder.mkdir(exist_ok=True)
    core.run(["python3","compile.py","-P",core.P,"-b",64,"-M","msle_aes_primitives"],runtime,folder/"compile.log",1800)
    log=folder/f"run_{time.time_ns()}.log"
    core.run(["/usr/bin/time","-v","bash","Scripts/shamir.sh","msle_aes_primitives","--prime",core.P],runtime,log,1800)
    assert "MSLE_AES_KAT vectors=3 bits=384 ok=1" in log.read_text()
    result={"vectors":3,"bits":384,"all_pass":True,"circuit_source_sha256":core.digest(ROOT/"data/aes_128_bristol.txt"),
        "mpc_source_sha256":core.digest(ROOT/"mpc/msle_aes_primitives.mpc"),"backend_sha256":core.digest(ROOT/"backend_config.json"),
        "raw_log":str(log.relative_to(ROOT)),"scope":"AES block primitive in five-party Shamir; not yet complete CTR system validation"}
    (ROOT/"results/aes_mpc_primitives.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)

def main(after_frontend):
    path=ROOT/"results/aes_baseline_status.json"
    state={"finished":False,"correctness_passed":False,"current":"waiting_for_frontend" if after_frontend else "starting","last_error":None,"completed":[]}
    def save(**values):state.update(values);path.write_text(json.dumps(state,indent=2))
    save()
    try:
        if after_frontend:
            while True:
                prior_path=ROOT/"results/binary_frontend_status.json"
                if prior_path.exists():
                    try:prior=json.loads(prior_path.read_text())
                    except json.JSONDecodeError:time.sleep(1);continue
                    if prior.get("finished") or prior.get("last_error"):
                        save(preceding_frontend_error=prior.get("last_error"));break
                time.sleep(5)
        runtime=Path(json.loads((ROOT.parent/"mpc_logs/runtime.json").read_text())["runtime"])
        with (runtime/".msle_v3_driver.lock").open("w") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            runtime=core.setup_runtime()
            shutil.copy2(ROOT/"data/aes_128_bristol.txt",runtime/"msle_aes_128_bristol.txt")
            shutil.copy2(ROOT/"aes_backend_config.json",runtime/"msle_aes_backend.json")
            save(current="secure_known_answer_tests")
            kat(runtime)
            save(current="system_correctness")
            case(runtime,"AES_CTR",n=2,bits=512,mode=0,transition=0,tag="aes_correctness")
            case(runtime,"AES_CTR",n=2,bits=512,mode=0,transition=1,tag="aes_sort_correctness")
            case(runtime,"AES_CTR",n=8,bits=512,mode=4,transition=0,tag="aes_transition_indexed_correctness")
            for fault in range(1,9):case(runtime,"AES_CTR",n=2,bits=128,mode=0,transition=0,fault=fault,tag="aes_faults")
            core.system_inputs=fixture.system_inputs
            diagnostic_case(runtime,2,128,9,1,1,source_name="msle_aes_ablation",transition=0)
            case(runtime,"AES_CTR",n=8,bits=512,mode=2,transition=0,threshold=0,tag="aes_reject_control")
            case(runtime,"AES_CTR",n=8,bits=512,mode=2,transition=0,threshold=0,exact_probe=True,tag="aes_accept_control")
            case(runtime,"AES_CTR_stable",n=8,bits=512,mode=4,transition=0,tag="aes_stable_correctness")
            for fault in (1,4,7,8):case(runtime,"AES_CTR_stable",n=2,bits=128,mode=0,transition=0,fault=fault,tag="aes_stable_faults")
            save(correctness_passed=True)
            # Direct control isolates encryption; strong-sort series also compares
            # the same standard private-index transaction. Freeze before timing.
            for transition,ns in ((0,(2,8,32)),(1,(2,8))):
                for n in ns:
                    initial=["MiMC_mask","AES_CTR"];random.Random(20261030+100*transition+n).shuffle(initial)
                    for repeat in range(-1,5):
                        for cipher in (initial if repeat%2==0 else list(reversed(initial))):
                            save(current={"n":n,"transition":transition,"cipher":cipher,"mode":1,"repeat":repeat})
                            opts={"n":n,"bits":512,"mode":1,"transition":transition,"diag":0,"tag":"aes_comparison"}
                            if repeat<0:case(runtime,cipher,repeats=0,warmups=1,**opts)
                            else:case(runtime,cipher,repeats=1,repeat_offset=repeat,**opts)
                    state["completed"].append({"n":n,"transition":transition});save()
            # Match the new representation as well: otherwise an encryption
            # comparison could conflate cipher cost with physical-index work.
            for n in (8,32):
                for repeat in range(-1,5):
                    for cipher in (("AES_CTR_stable","MiMC_mask_stable") if repeat%2 else ("MiMC_mask_stable","AES_CTR_stable")):
                        save(current={"n":n,"cipher":cipher,"mode":1,"repeat":repeat})
                        opts={"n":n,"bits":512,"mode":1,"transition":0,"diag":0,"tag":"aes_stable_comparison"}
                        if repeat<0:case(runtime,cipher,repeats=0,warmups=1,**opts)
                        else:case(runtime,cipher,repeats=1,repeat_offset=repeat,**opts)
                state["completed"].append({"n":n,"representation":"stable"});save()
            for repeat in range(-1,3):
                for cipher in (("AES_CTR","MiMC_mask","AES_CTR_stable","MiMC_mask_stable") if repeat%2 else ("MiMC_mask_stable","AES_CTR_stable","MiMC_mask","AES_CTR")):
                    save(current={"n":32,"cipher":cipher,"mode":2,"repeat":repeat})
                    opts={"n":32,"bits":512,"mode":2,"transition":0,"diag":0,"tag":"aes_comparison"}
                    if repeat<0:case(runtime,cipher,repeats=0,warmups=1,**opts)
                    else:case(runtime,cipher,repeats=1,repeat_offset=repeat,**opts)
        save(finished=True,current=None)
        print("AES_BASELINE_COMPLETE",flush=True)
    except BaseException as error:
        save(last_error=repr(error));raise

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--after-frontend",action="store_true")
    main(parser.parse_args().after_frontend)
