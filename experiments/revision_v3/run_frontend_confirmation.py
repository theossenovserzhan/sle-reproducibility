"""Transfer the frozen512-bit SFace projections and verify actual MPC inputs."""
from pathlib import Path
import csv,fcntl,hashlib,json,time
import numpy as np
import mpc_driver as core
import persisted_private_fused_driver as secure
from run_binary_frontend import bootstrap_mean,normalize,split_data,write_csv
from evaluate_float_binary_128 import split_prototypes

ROOT=Path(__file__).resolve().parent
SEEDS=(20261030,20261031)
METHODS=("FaceNet_cosine","FaceNet_sign512","SFace_cosine","SFace_sign128")+tuple(f"SFace_RP_{kind}_512_seed{seed}" for kind in ("original","centered") for seed in SEEDS)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def codes(values,model,seed,centered=True):
    values=normalize(values.astype(np.float64))
    if centered:values=values-model["mean"]
    return (values@model[f"projection_{seed}"][:,:512]>=0).astype(np.uint8)

def score(gallery,probes,method,model):
    if "cosine" in method:return normalize(probes)@normalize(gallery).T
    if "_RP_" in method:
        kind=method.split("_RP_")[1].split("_")[0]
        seed=int(method.rsplit("seed",1)[1])
        left=codes(probes,model,seed,kind=="centered").astype(np.int32)
        right=codes(gallery,model,seed,kind=="centered").astype(np.int32)
    else:
        left=(probes>=0).astype(np.int32);right=(gallery>=0).astype(np.int32)
    return 2*(left@right.T)-left.sum(1)[:,None]-right.sum(1)[None,:]

def transfer(model):
    output=ROOT/"results/frontend_confirmation";output.mkdir(exist_ok=True)
    cohorts=(("LFW",ROOT/"data/sface_lfw.npz",ROOT.parent/"float_features/lfw_facenet_vggface2.npz"),
             ("CelebA",ROOT/"data/sface_celeba.npz",ROOT.parent/"revision_v2/data/celeba/celeba_facenet_vggface2.npz"),
             ("CelebA_external",ROOT/"data/sface_celeba_external.npz",ROOT.parent/"revision_v2/data/celeba_external/celeba_external_facenet_vggface2.npz"))
    summary={"methods":METHODS,"protocol_sha256":sha(ROOT/"frontend_confirmation_protocol.json"),"script_sha256":sha(__file__),"frozen_projection_model_sha256":sha(ROOT/"data/projection_sface_model.npz"),"cohorts":[],"extended_paired":[],"limitations":["All LFW methods are development results after observed outcomes; no claim of blinded selection", "Same images/identities paired across frontends; model, alignment, and hashing change together", "LFW/CelebA identity overlap and pretrained-model identity overlap are unaudited", "The two CelebA cohorts share one identity; do not pool confidence intervals", "Projection seeds are both retained, not selected by test outcomes", "Public projection is not a cryptographic protection mechanism"]}
    split_rows=[]
    for cohort,sface_path,facenet_path in cohorts:
        with np.load(sface_path) as sf,np.load(facenet_path) as fn:
            for key in ("identities","image_ids"):assert np.array_equal(sf[key],fn[key]),(cohort,key)
            embeddings={"SFace":sf["embeddings"][:128].astype(np.float64),"FaceNet":fn["embeddings"][:128].astype(np.float64)}
        arrays={name:np.zeros((len(METHODS),20,128,4),dtype=np.uint8) for name in ("rank1","rank5")}
        seed=20260722+(20000 if cohort=="LFW" else 10000)
        for split in range(20):
            values={name:split_prototypes(features,split,seed) for name,features in embeddings.items()}
            assert np.array_equal(values["SFace"][2],values["FaceNet"][2])
            assert values["SFace"][3]==values["FaceNet"][3]
            for i,method in enumerate(METHODS):
                g,p,truth,_=values["FaceNet" if method.startswith("FaceNet") else "SFace"]
                order=np.argsort(-score(g,p,method,model),axis=1,kind="stable")
                arrays["rank1"][i,split]=(order[:,0]==truth).reshape(128,4)
                arrays["rank5"][i,split]=np.any(order[:,:5]==truth[:,None],axis=1).reshape(128,4)
                split_rows.append({"cohort":cohort,"method":method,"split":split,**{key:float(array[i,split].mean()) for key,array in arrays.items()}})
        np.savez_compressed(output/f"{cohort}_subject_outcomes.npz",**arrays)
        result={"cohort":cohort,"sface_input_sha256":sha(sface_path),"facenet_input_sha256":sha(facenet_path),"identical_identities_images_splits":True,"methods":[]}
        for i,method in enumerate(METHODS):
            by_id=arrays["rank1"][i].mean(axis=(0,2))
            original=arrays["rank1"][1].mean(axis=(0,2))
            result["methods"].append({"method":method,"rank1":float(by_id.mean()),"rank5":float(arrays["rank5"][i].mean()),"delta_vs_FaceNet_sign512":bootstrap_mean(by_id-original,20264000+i)})
        summary["cohorts"].append(result)
        print("FRONTEND_TRANSFER_COMPLETE "+cohort,flush=True)
    write_csv(output/"closed_set_splits.csv",split_rows)
    # Paired uncertainty across exactly the same known/unknown identities in
    # the completed large-gallery study; splits are averaged within identity.
    with np.load(ROOT/"results/projection_sface_corrected/subject_outcomes.npz") as sf,np.load(ROOT/"results/projection_facenet_corrected/subject_outcomes.npz") as fn:
        methods=json.loads((ROOT/"results/projection_sface_corrected/summary.json").read_text())["methods"]
        for n_index,n in enumerate((128,256,512,1024,2048,4096)):
            for method in methods:
                if not method.startswith(("RP_original_512_","RP_centered_512_")):continue
                i=methods.index(method)
                sf_known=sf["rank1"][i,n_index].mean(axis=(0,2));fn_known=fn["rank1"][1,n_index].mean(axis=(0,2))
                result={"n_gallery":n,"method":"SFace_"+method,"rank1":float(sf_known.mean()),"FaceNet_sign512_rank1":float(fn_known.mean()),"rank1_delta":bootstrap_mean(sf_known-fn_known,20265000+n_index*20+i),"open_set":[]}
                for rule in range(2):
                    sf_dir=sf["correct_accepted"][i,n_index,:,rule].reshape(20,128,4).mean(axis=(0,2))
                    fn_dir=fn["correct_accepted"][1,n_index,:,rule].reshape(20,128,4).mean(axis=(0,2))
                    sf_fpir=sf["unknown_accept"][i,n_index,:,rule].mean(0)
                    fn_fpir=fn["unknown_accept"][1,n_index,:,rule].mean(0)
                    result["open_set"].append({"rule":"empirical" if rule==0 else "conservative_iid_order_statistic","SFace_DIR":float(sf_dir.mean()),"FaceNet_DIR":float(fn_dir.mean()),"DIR_delta":bootstrap_mean(sf_dir-fn_dir,20266000+n_index*50+2*i+rule),"SFace_FPIR":float(sf_fpir.mean()),"FaceNet_FPIR":float(fn_fpir.mean()),"FPIR_delta":bootstrap_mean(sf_fpir-fn_fpir,20267000+n_index*50+2*i+rule)})
                summary["extended_paired"].append(result)
    (output/"summary.json").write_text(json.dumps(summary,indent=2))
    return output

def secure_confirmation(runtime,model,save):
    with np.load(ROOT/"data/sface_lfw.npz") as data:enrolled=data["embeddings"][:128].astype(np.float64)
    extended=np.load(ROOT/"data/sface_lfw_extended_features.npy",mmap_mode="r")
    gallery,probe,truth,_=split_data(enrolled,0)
    metadata=[]
    for seed in SEEDS:
        all_roots=codes(np.concatenate([gallery,extended[1024:4992]],axis=0),model,seed)
        probe_roots=codes(probe,model,seed)
        for n in (8,128):
            target=ROOT/f"data/sface_rp512_seed{seed}_n{n}.npz"
            np.savez_compressed(target,gallery_roots=all_roots[:n],probe_roots=probe_roots,gallery_labels=np.arange(n))
            metadata.append({"seed":seed,"n":n,"input_sha256":sha(target),"source_model_sha256":sha(ROOT/"data/projection_sface_model.npz"),"input_dimension":128,"root_bits":512,"training_or_seed_selection":False})
            secure.INPUT_OVERRIDE=target
            fixture=secure.initialize(runtime,n,0)
            save(current={"phase":"secure_code_confirmation","seed":seed,"n":n})
            secure.execute(runtime,fixture,0,diag=1,tag=f"sface_rp512_seed{seed}_state_correctness")
            # Indexed query includes a full independent candidate-bit oracle
            # atN8. AtN128 keep production I/O; earlier N8/non-power-of-two
            # fixtures already establish the candidate implementation.
            if n==8:
                row=secure.execute(runtime,fixture,3,diag=1,tag=f"sface_rp512_seed{seed}_candidate_correctness")
                assert "MSLE_CANDIDATES exact_membership_ok=1" in (ROOT/row["raw_log"]).read_text()
            assert secure.execute(runtime,fixture,2,diag=0,exact=True,threshold=0,tag=f"sface_rp512_seed{seed}_private_accept")["accepted"]==1
            assert secure.execute(runtime,fixture,2,diag=0,threshold=0,tag=f"sface_rp512_seed{seed}_private_reject")["accepted"]==0
            secure.INPUT_OVERRIDE=None
    (ROOT/"data/sface_rp512_secure_inputs.json").write_text(json.dumps(metadata,indent=2))

def main():
    state={"finished":False,"current":"waiting_for_private_output_validation","last_error":None}
    path=ROOT/"results/frontend_confirmation_status.json"
    def save(**values):state.update(values);path.write_text(json.dumps(state,indent=2))
    save()
    try:
        while True:
            prior_path=ROOT/"results/private_client_status.json"
            if prior_path.exists():
                try:prior=json.loads(prior_path.read_text())
                except json.JSONDecodeError:time.sleep(1);continue
                if prior.get("last_error"):raise RuntimeError("Repair private output validation: "+prior["last_error"])
                if prior.get("finished") and prior.get("correctness_passed"):
                    repair_path=ROOT/"results/calibration_repair_status.json"
                    if repair_path.exists():
                        try:repair=json.loads(repair_path.read_text())
                        except json.JSONDecodeError:time.sleep(1);continue
                        if repair.get("last_error"):raise RuntimeError("Repair strict score calibration: "+repair["last_error"])
                        if repair.get("finished") and repair.get("correctness_passed"):break
            time.sleep(5)
        runtime=Path(json.loads((ROOT.parent/"mpc_logs/runtime.json").read_text())["runtime"])
        with (runtime/".msle_v3_driver.lock").open("w") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);runtime=core.setup_runtime()
            with np.load(ROOT/"data/projection_sface_model.npz") as values:model={key:values[key].copy() for key in values.files}
            save(current="cross_dataset_paired_confirmation");transfer(model)
            secure.audit_common_core();secure_confirmation(runtime,model,save)
        save(finished=True,current=None);print("FRONTEND_CONFIRMATION_COMPLETE",flush=True)
    except BaseException as error:
        save(last_error=repr(error));raise

if __name__=="__main__":main()
