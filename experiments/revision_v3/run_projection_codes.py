"""Fixed public angular hashes: a next development step, with both seeds retained."""
from pathlib import Path
import argparse,fcntl,hashlib,json,re,sys,time
import numpy as np
import projection_evaluator as evaluator
from run_binary_frontend import normalize

ROOT=Path(__file__).resolve().parent
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def run(frontend):
    """Caller must hold the common runtime lock before heavy scoring."""
    state={"frontend":frontend,"finished":False,"current":"prepare","last_error":None}
    evaluator.update(state)
    try:
        cfg=json.loads((ROOT/"projection_code_protocol.json").read_text())
        if frontend=="facenet":
            feature_path=ROOT.parent/"float_features/lfw_facenet_vggface2.npz"
            extended_path=ROOT.parent/"revision_v2/data/lfw_extended_features.npy"
            baseline_path=ROOT.parent/"revision_v2/results/lfw_extended/subject_outcomes.npz"
        else:
            feature_path=ROOT/"data/sface_lfw.npz";extended_path=ROOT/"data/sface_lfw_extended_features.npy"
            baseline_path=ROOT/"results/sface_lfw_extended/subject_outcomes.npz"
        extended=np.load(extended_path,mmap_mode="r")
        dimension=extended.shape[1]
        training=normalize(extended[4992:].astype(np.float64))
        assert len(training)==565
        model={"mean":training.mean(0)}
        for seed in cfg["public_projection_seeds"]:
            model[f"projection_{seed}"]=np.random.default_rng(seed).standard_normal((max(cfg["widths"]),dimension)).T
        model_path=ROOT/f"data/projection_{frontend}_model.npz"
        if model_path.exists():raise RuntimeError("Refuse to overwrite a frozen projection study; inspect existing outputs or start a separately named confirmation")
        np.savez_compressed(model_path,**model)
        metadata={"frontend":frontend,"feature_archive":str(feature_path),"baseline_outcomes_archive":str(baseline_path),
            "model_sha256":sha(model_path),"extended_feature_sha256":sha(extended_path),"protocol_sha256":sha(ROOT/"projection_code_protocol.json"),
            "script_sha256":sha(__file__),"numpy":np.__version__,"input_dimension":dimension,"training_identities":565}
        (ROOT/f"data/projection_{frontend}_model.json").write_text(json.dumps(metadata,indent=2))
        def transform(values,method,unused):
            normalized=normalize(values.astype(np.float64))
            if method=="original_cosine":return normalized
            if method.startswith("original_sign"):return (normalized>=0).astype(np.float32)
            centered=normalized-model["mean"]
            if method=="centered_cosine":return normalize(centered)
            if method.startswith("centered_sign"):return (centered>=0).astype(np.float32)
            kind,width,seed=re.fullmatch(r"RP_(original|centered)_(\d+)_seed(\d+)",method).groups()
            source=centered if kind=="centered" else normalized
            return (source@model[f"projection_{seed}"][:,:int(width)]>=0).astype(np.float32)
        methods=["original_cosine",f"original_sign_{dimension}","centered_cosine",f"centered_sign_{dimension}"]
        for kind in ("original","centered"):
            for width in cfg["widths"]:
                for seed in cfg["public_projection_seeds"]:methods.append(f"RP_{kind}_{width}_seed{seed}")
        evaluator.METHODS=tuple(methods);evaluator.transform=transform
        evaluator.evaluate(cfg,model,metadata,extended,state)
        evaluator.update(state,finished=True,current=None)
        print("PROJECTION_CODES_COMPLETE "+frontend,flush=True)
    except BaseException as error:
        evaluator.update(state,last_error=repr(error));raise

def main(after_sface):
    evaluator.update({"frontend":"facenet","finished":False,"current":"waiting_for_SFace" if after_sface else "starting","last_error":None})
    if after_sface:
        while True:
            path=ROOT/"results/sface_status.json"
            if path.exists():
                try:state=json.loads(path.read_text())
                except json.JSONDecodeError:time.sleep(1);continue
                if state.get("finished") or state.get("last_error"):break
            time.sleep(5)
    runtime=Path(json.loads((ROOT.parent/"mpc_logs/runtime.json").read_text())["runtime"])
    with (runtime/".msle_v3_driver.lock").open("w") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);run("facenet")

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--after-sface",action="store_true")
    main(parser.parse_args().after_sface)
