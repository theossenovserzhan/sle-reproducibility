"""Finish evaluation from frozen features; do not repeat completed extraction."""
from pathlib import Path
import fcntl,hashlib,json,os,subprocess,sys,time

ROOT=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    state={"finished":False,"current":"waiting_for_vector_query","last_error":None,"resume_from_frozen_features":True}
    path=ROOT/"results/sface_status.json"
    def save(**values):
        state.update(values);temp=path.with_name(path.name+".next")
        temp.write_text(json.dumps(state,indent=2));temp.replace(path)
    save()
    try:
        while True:
            prior_path=ROOT/"results/vector_query_status.json"
            if prior_path.exists():
                try:prior=json.loads(prior_path.read_text())
                except json.JSONDecodeError:time.sleep(1);continue
                if prior.get("finished") or prior.get("last_error"):
                    save(preceding_mpc_error=prior.get("last_error"));break
            time.sleep(5)
        runtime=Path(json.loads((ROOT.parent/"mpc_logs/runtime.json").read_text())["runtime"])
        with (runtime/".msle_v3_driver.lock").open("w") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            progress=json.loads((ROOT/"data/sface_progress.json").read_text())
            extraction=json.loads((ROOT/"data/sface_extraction.json").read_text())
            assert progress["completed"]==progress["total"]==8629
            assert extraction["features_sha256"]==sha(ROOT/"data/sface_all_features.npy")
            assert extraction["selection_sha256"]==sha(ROOT/"data/sface_selection.json")
            assert extraction["images_excluded"]==0
            # The large fresh-cohort evaluation has already completed. Its
            # outcomes stay in place; only unfinished evaluation stages run.
            assert (ROOT/"results/sface_lfw_extended/summary.json").exists()
            for dataset,name in (("LFW","lfw"),("CelebA","celeba")):
                output=ROOT/f"results/sface_{name}_paired"
                if (output/"paired_summary.json").exists():continue
                save(current="evaluate_"+name+"_original_cohort")
                subprocess.run([sys.executable,str(ROOT/"evaluate_float_binary_128.py"),"--input",str(ROOT/f"data/sface_{name}.npz"),"--output",str(output),"--dataset",dataset],cwd=ROOT,check=True)
            if not (ROOT/"results/sface_celeba_external/summary.json").exists():
                save(current="evaluate_CelebA_external")
                from run_sface import evaluate_external
                evaluate_external()
            if not (ROOT/"results/projection_sface/summary.json").exists():
                save(current="evaluate_frozen_projection_codes")
                from run_projection_codes import run
                run("sface")
        save(finished=True,current=None)
        print("SFACE_EVALUATION_COMPLETE",flush=True)
    except BaseException as error:
        save(last_error=repr(error));raise

if __name__=="__main__":main()
