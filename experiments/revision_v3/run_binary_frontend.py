"""Training-only ITQ development study; preserve the complete predefined comparison."""
from pathlib import Path
import argparse,fcntl,hashlib,json,os,sys,time
import numpy as np

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/"revision_v2"))
sys.path.insert(0,str(ROOT.parent))
from evaluate_lfw_extended import bootstrap_mean,conservative_allowed,index_metrics,split_data
from evaluate_float_binary import normalize,threshold_from_calibration
from run_experiments import distances,write_csv

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def update(state,**values):
    state.update(values)
    (ROOT/"results/binary_frontend_status.json").write_text(json.dumps(state,indent=2))

def fit(cfg,selection,extended,state):
    """This function receives training rows only and never recognition outcomes."""
    train=normalize(extended[selection["row_indices"]].astype(np.float64))
    mean=train.mean(0)
    centered=train-mean
    eigenvalues,basis=np.linalg.eigh(centered.T@centered)
    basis=basis[:,np.argsort(eigenvalues)[::-1]]
    # Fix the arbitrary eigenvector signs for portable saved transforms.
    signs=np.sign(basis[np.argmax(np.abs(basis),axis=0),np.arange(basis.shape[1])])
    basis*=np.where(signs==0,1,signs)
    parameters={"mean":mean,"basis":basis}
    diagnostics={}
    for bits in (512,256):
        projected=centered@basis[:,:bits]
        rng=np.random.default_rng(cfg["ITQ"]["initialization_seed"]+bits)
        rotation=np.linalg.qr(rng.standard_normal((bits,bits)))[0]
        losses=[]
        for iteration in range(cfg["ITQ"]["iterations"]):
            signed=np.where(projected@rotation>=0,1.,-1.)
            left,_,right=np.linalg.svd(projected.T@signed,full_matrices=False)
            rotation=left@right
            losses.append(float(np.mean((signed-projected@rotation)**2)))
            update(state,current={"phase":"fit","bits":bits,"iteration":iteration+1})
        error=float(np.max(np.abs(rotation.T@rotation-np.eye(bits))))
        assert error<1e-8 and np.isfinite(rotation).all()
        parameters[f"rotation_{bits}"]=rotation
        diagnostics[str(bits)]={"training_quantization_loss":losses,"orthogonality_max_error":error}
    target=ROOT/"data/binary_frontend_model.npz"
    if target.exists():raise RuntimeError("Refuse to overwrite an existing fitted model; use its recorded experiment or a new named study")
    np.savez_compressed(target,**parameters)
    meta={"protocol_sha256":sha(ROOT/"binary_frontend_protocol.json"),"script_sha256":sha(__file__),
        "training_selection_sha256":sha(ROOT/"data/binary_frontend_training_selection.json"),
        "model_sha256":sha(target),"numpy":np.__version__,"training_identities":len(train),
        "diagnostics":diagnostics,"fit_uses_recognition_outcomes":False}
    (ROOT/"data/binary_frontend_model.json").write_text(json.dumps(meta,indent=2))
    print("TRAINING_ONLY_MODEL_FROZEN "+meta["model_sha256"],flush=True)
    return parameters,meta

METHODS=("original_cosine","original_sign_512","centered_cosine","centered_sign_512",
         "PCA512_cosine","PCA_ITQ_512","PCA256_cosine","PCA_ITQ_256")

def transform(values,method,model):
    normalized=normalize(values.astype(np.float64))
    if method=="original_cosine":return normalized
    if method=="original_sign_512":return (normalized>=0).astype(np.float32)
    centered=normalized-model["mean"]
    if method=="centered_cosine":return normalize(centered)
    if method=="centered_sign_512":return (centered>=0).astype(np.float32)
    bits=256 if "256" in method else 512
    projected=centered@model["basis"][:,:bits]
    if "cosine" in method:return normalize(projected)
    return (projected@model[f"rotation_{bits}"]>=0).astype(np.float32)

def scores(left,right,binary):
    product=left@right.T
    if binary:
        # Every dot product sums <=512 exact 0/1 products, exactly representable
        # in float32; verify against the independent int32 oracle below.
        return 2*product-left.sum(1)[:,None]-right.sum(1)[None,:]
    return product

def evaluate(cfg,model,metadata,extended,state):
    output=ROOT/"results/binary_frontend"
    output.mkdir(exist_ok=True)
    with np.load(ROOT.parent/"float_features/lfw_facenet_vggface2.npz") as old:
        enrolled=old["embeddings"][:128].astype(np.float64)
    calibration,unknown,distractors=extended[:512],extended[512:1024],extended[1024:4992]
    with np.load(ROOT.parent/"revision_v2/results/lfw_extended/subject_outcomes.npz") as old:
        original_rank1=old["rank1"].copy();original_rank5=old["rank5"].copy()
    sizes=(128,256,512,1024,2048,4096)
    rank1=np.zeros((len(METHODS),len(sizes),20,128,4),dtype=np.uint8)
    rank5=np.zeros_like(rank1)
    unknown_accept=np.zeros((len(METHODS),len(sizes),20,2,512),dtype=np.uint8)
    known_accept=np.zeros_like(unknown_accept)
    closed_rows,open_rows,index_rows=[],[],[]
    conservative=conservative_allowed(512,.01)
    for method_index,method in enumerate(METHODS):
        update(state,current={"phase":"evaluate","method":method,"split":0})
        binary="cosine" not in method
        dg=transform(distractors,method,model)
        pool=transform(enrolled.reshape(-1,512),method,model)
        cal=transform(calibration,method,model)
        unk=transform(unknown,method,model)
        if binary:
            assert np.array_equal(scores(pool[:17],dg[:13],True),-distances(pool[:17],dg[:13]))
        fixed_pool=scores(pool,dg,binary)
        fixed_cal=scores(cal,dg,binary)
        fixed_unknown=scores(unk,dg,binary)
        for split in range(20):
            g,p,labels,pool_indices=split_data(enrolled,split)
            gallery=transform(g,method,model)
            probes=pool[pool_indices]
            all_scores=np.concatenate([scores(probes,gallery,binary),fixed_pool[pool_indices]],axis=1)
            all_cal=np.concatenate([scores(cal,gallery,binary),fixed_cal],axis=1)
            all_unknown=np.concatenate([scores(unk,gallery,binary),fixed_unknown],axis=1)
            for size_index,n in enumerate(sizes):
                comparison=all_scores[:,:n]
                genuine=comparison[np.arange(len(labels)),labels]
                ranks=1+(comparison>genuine[:,None]).sum(1)+((comparison==genuine[:,None])&(np.arange(n)[None,:]<labels[:,None])).sum(1)
                correct=ranks==1
                rank1[method_index,size_index,split]=correct.reshape(128,4)
                rank5[method_index,size_index,split]=(ranks<=5).reshape(128,4)
                closed_rows.append({"method":method,"split":split,"n_gallery":n,"rank1":float(correct.mean()),"rank5":float(np.mean(ranks<=5)),"query_identities":128,"probes":512})
                if binary and split==0:
                    all_gallery=np.concatenate([gallery,dg[:n-128]],axis=0).astype(np.uint8)
                    current_index=index_metrics(all_gallery,probes.astype(np.uint8),comparison,labels,n,output)
                    index_rows.extend({"method":method,**row} for row in current_index)
                for rule,allowed in enumerate((5,conservative)):
                    cal_max=all_cal[:,:n].max(1)
                    threshold=threshold_from_calibration(cal_max,allowed/512)
                    accepts=all_unknown[:,:n].max(1)>=threshold
                    directions=correct&(comparison.max(1)>=threshold)
                    unknown_accept[method_index,size_index,split,rule]=accepts
                    known_accept[method_index,size_index,split,rule]=directions
                    open_rows.append({"method":method,"split":split,"n_gallery":n,
                        "rule":"empirical" if rule==0 else "conservative_iid_order_statistic",
                        "threshold":threshold,"calibration_allowed_accepts":allowed,
                        "calibration_fpir":float(np.mean(cal_max>=threshold)),"test_fpir":float(accepts.mean()),"test_dir":float(directions.mean())})
            update(state,current={"phase":"evaluate","method":method,"split":split+1})
        if method in ("original_cosine","original_sign_512"):
            old_index=0 if method=="original_cosine" else 1
            assert np.array_equal(rank1[method_index],original_rank1[old_index]),"R1 rank1 baseline changed"
            assert np.array_equal(rank5[method_index],original_rank5[old_index]),"R1 rank5 baseline changed"
        print("FRONTEND_METHOD_COMPLETE "+method,flush=True)
    np.savez_compressed(output/"subject_outcomes.npz",rank1=rank1,rank5=rank5,unknown_accept=unknown_accept,correct_accepted=known_accept)
    write_csv(output/"closed_set_splits.csv",closed_rows)
    write_csv(output/"open_set_splits.csv",open_rows)
    write_csv(output/"index_frozen_split.csv",index_rows)
    summary={"methods":list(METHODS),"model_sha256":metadata["model_sha256"],
        "protocol_sha256":sha(ROOT/"binary_frontend_protocol.json"),"script_sha256":sha(__file__),
        "R1_baselines_reproduced_exactly":True,"closed_set":[],"open_set":[],
        "scope":"Predefined development study, all methods retained. Repeated image assignments are not independent identities. ITQ is established preprocessing, not the protected-system novelty. No MPC timings are estimated as measured results."}
    for size_index,n in enumerate(sizes):
        old_binary=rank1[1,size_index].mean(axis=(0,2))
        original_float=rank1[0,size_index].mean(axis=(0,2))
        for index,method in enumerate(METHODS):
            by_id=rank1[index,size_index].mean(axis=(0,2))
            summary["closed_set"].append({"method":method,"n_gallery":n,"rank1":float(by_id.mean()),"rank5":float(rank5[index,size_index].mean()),
                "delta_vs_original_sign":bootstrap_mean(by_id-old_binary,20261100+100*size_index+index),
                "delta_vs_original_cosine":bootstrap_mean(by_id-original_float,20261200+100*size_index+index)})
            for rule in range(2):
                summary["open_set"].append({"method":method,"n_gallery":n,
                    "rule":"empirical" if rule==0 else "conservative_iid_order_statistic",
                    "test_fpir":bootstrap_mean(unknown_accept[index,size_index,:,rule].mean(0),20262000+100*size_index+10*index+rule),
                    "test_dir":bootstrap_mean(known_accept[index,size_index,:,rule].reshape(20,128,4).mean(axis=(0,2)),20263000+100*size_index+10*index+rule)})
    (output/"summary.json").write_text(json.dumps(summary,indent=2))
    print(json.dumps({"n4096":[r for r in summary["closed_set"] if r["n_gallery"]==4096]},indent=2),flush=True)

def main(after_lazy):
    state={"finished":False,"current":"waiting_for_MPC" if after_lazy else "starting","last_error":None}
    update(state)
    began=time.monotonic()
    try:
        if after_lazy:
            while True:
                prerequisite=ROOT/"results/lazy_epoch_status.json"
                if prerequisite.exists():
                    try:prior=json.loads(prerequisite.read_text())
                    except json.JSONDecodeError:
                        time.sleep(1);continue
                    if prior.get("last_error"):raise RuntimeError("Prior MPC development run failed: "+prior["last_error"])
                    if prior.get("finished") and prior.get("correctness_passed"):break
                time.sleep(5)
        runtime=Path(json.loads((ROOT.parent/"mpc_logs/runtime.json").read_text())["runtime"])
        with (runtime/".msle_v3_driver.lock").open("w") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            cfg=json.loads((ROOT/"binary_frontend_protocol.json").read_text())
            selection=json.loads((ROOT/"data/binary_frontend_training_selection.json").read_text())
            assert selection["protocol_sha256"]==sha(ROOT/"binary_frontend_protocol.json")
            feature_path=ROOT.parent/"revision_v2/data/lfw_extended_features.npy"
            assert selection["feature_sha256"]==sha(feature_path)
            extended=np.load(feature_path,mmap_mode="r")
            model,metadata=fit(cfg,selection,extended,state)
            evaluate(cfg,model,metadata,extended,state)
        update(state,finished=True,current=None,elapsed_seconds=time.monotonic()-began)
        print("BINARY_FRONTEND_COMPLETE",flush=True)
    except BaseException as error:
        update(state,last_error=repr(error));raise

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--after-lazy",action="store_true")
    main(parser.parse_args().after_lazy)
