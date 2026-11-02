"""Recompute strict thresholds from frozen models; preserve original attempts."""
from pathlib import Path
import argparse,fcntl,hashlib,json,shutil,time
import numpy as np
from calibration_numeric import binary_scores,self_test
from run_binary_frontend import bootstrap_mean,conservative_allowed,normalize,split_data,threshold_from_calibration,transform as itq_transform,write_csv

ROOT=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def repair(study,save):
    frontend="sface" if study=="projection_sface" else "facenet"
    old=ROOT/f"results/{study}";output=ROOT/f"results/{study}_corrected";output.mkdir(exist_ok=True)
    summary=json.loads((old/"summary.json").read_text());methods=summary["methods"]
    with np.load(old/"subject_outcomes.npz") as data:
        original={key:data[key].copy() for key in data.files}
    if frontend=="sface":
        feature_path=ROOT/"data/sface_lfw.npz";extended_path=ROOT/"data/sface_lfw_extended_features.npy"
        baseline_path=ROOT/"results/sface_lfw_extended/subject_outcomes.npz"
    else:
        feature_path=ROOT.parent/"float_features/lfw_facenet_vggface2.npz";extended_path=ROOT.parent/"revision_v2/data/lfw_extended_features.npy"
        baseline_path=ROOT.parent/"revision_v2/results/lfw_extended/subject_outcomes.npz"
    with np.load(feature_path) as data:enrolled=data["embeddings"][:128].astype(np.float64)
    extended=np.load(extended_path,mmap_mode="r")
    model_path=ROOT/("data/binary_frontend_model.npz" if study=="binary_frontend" else f"data/projection_{frontend}_model.npz")
    with np.load(model_path) as data:model={key:data[key].copy() for key in data.files}
    def transform(values,method):
        if study=="binary_frontend":return itq_transform(values,method,model)
        normalized=normalize(values.astype(np.float64))
        if method=="original_cosine":return normalized
        if method.startswith("original_sign"):return (normalized>=0).astype(np.float32)
        centered=normalized-model["mean"]
        if method=="centered_cosine":return normalize(centered)
        if method.startswith("centered_sign"):return (centered>=0).astype(np.float32)
        _,kind,width,seed=method.split("_")
        source=centered if kind=="centered" else normalized
        return (source@model[f"projection_{int(seed.removeprefix('seed'))}"][:,:int(width)]>=0).astype(np.float32)
    def scores(left,right,binary):return binary_scores(left,right) if binary else left@right.T
    unknown=np.zeros_like(original["unknown_accept"]);known=np.zeros_like(original["correct_accepted"])
    sizes=(128,256,512,1024,2048,4096);open_rows=[]
    for method_index,method in enumerate(methods):
        save(current={"study":study,"method":method,"phase":"strict_open_set"})
        binary="cosine" not in method
        dg=transform(extended[1024:4992],method)
        pool=transform(enrolled.reshape(-1,enrolled.shape[-1]),method)
        cal=transform(extended[:512],method);unk=transform(extended[512:1024],method)
        fixed_pool=scores(pool,dg,binary);fixed_cal=scores(cal,dg,binary);fixed_unk=scores(unk,dg,binary)
        for split in range(20):
            gallery,_,labels,positions=split_data(enrolled,split)
            gallery=transform(gallery,method)
            all_scores=np.concatenate([scores(pool[positions],gallery,binary),fixed_pool[positions]],axis=1)
            all_cal=np.concatenate([scores(cal,gallery,binary),fixed_cal],axis=1)
            all_unk=np.concatenate([scores(unk,gallery,binary),fixed_unk],axis=1)
            assert all_scores.dtype==all_cal.dtype==all_unk.dtype==np.float64
            for ni,n in enumerate(sizes):
                comparison=all_scores[:,:n];genuine=comparison[np.arange(512),labels]
                ranks=1+(comparison>genuine[:,None]).sum(1)+((comparison==genuine[:,None])&(np.arange(n)[None,:]<labels[:,None])).sum(1)
                correct=ranks==1
                assert np.array_equal(correct.reshape(128,4),original["rank1"][method_index,ni,split])
                assert np.array_equal((ranks<=5).reshape(128,4),original["rank5"][method_index,ni,split])
                cal_max=all_cal[:,:n].max(1)
                for rule,allowed in enumerate((5,conservative_allowed(512,.01))):
                    threshold=threshold_from_calibration(cal_max,allowed/512)
                    accepted=all_unk[:,:n].max(1)>=threshold
                    directions=correct&(comparison.max(1)>=threshold)
                    actual_cal=int(np.count_nonzero(cal_max>=threshold));assert actual_cal<=allowed
                    unknown[method_index,ni,split,rule]=accepted
                    known[method_index,ni,split,rule]=directions
                    open_rows.append({"method":method,"split":split,"n_gallery":n,"rule":"empirical" if rule==0 else "conservative_iid_order_statistic","threshold":threshold,"calibration_allowed_accepts":allowed,"calibration_actual_accepts":actual_cal,"calibration_fpir":actual_cal/512,"test_fpir":float(accepted.mean()),"test_dir":float(directions.mean()),"score_dtype":"float64"})
        print("STRICT_CALIBRATION_METHOD_COMPLETE "+study+" "+method,flush=True)
    with np.load(baseline_path) as baseline:
        for index in (0,1):
            assert np.array_equal(unknown[index],baseline["unknown_accept"][index]),"Original open-set FPIR failed exact reproduction"
            assert np.array_equal(known[index],baseline["correct_accepted"][index]),"Original open-set DIR failed exact reproduction"
    np.savez_compressed(output/"subject_outcomes.npz",rank1=original["rank1"],rank5=original["rank5"],unknown_accept=unknown,correct_accepted=known)
    for name in ("closed_set_splits.csv","index_frozen_split.csv"):shutil.copy2(old/name,output/name)
    write_csv(output/"open_set_splits.csv",open_rows)
    summary["open_set"]=[]
    for ni,n in enumerate(sizes):
        for index,method in enumerate(methods):
            for rule in range(2):
                summary["open_set"].append({"method":method,"n_gallery":n,"rule":"empirical" if rule==0 else "conservative_iid_order_statistic","test_fpir":bootstrap_mean(unknown[index,ni,:,rule].mean(0),20262000+100*ni+10*index+rule),"test_dir":bootstrap_mean(known[index,ni,:,rule].reshape(20,128,4).mean(axis=(0,2)),20263000+100*ni+10*index+rule)})
    summary["strict_calibration_correction"]={"script_sha256":sha(__file__),"numeric_helper_sha256":sha(ROOT/"calibration_numeric.py"),"protocol_sha256":sha(ROOT/"calibration_repair_protocol.json"),"frozen_model_sha256":sha(model_path),"original_summary_sha256":sha(old/"summary.json"),"closed_set_all_flags_unchanged":True,"original_float_and_sign_open_set_all_flags_reproduced_exactly":True,"all_calibration_accept_counts_within_allowed":True,"cause":"NumPy2 weak scalar promotion rounded float64 nextafter cutoff when compared to float32 binary scores; convert exact integer scores to float64 before thresholding","original_attempts_retained":str(old.relative_to(ROOT)),"changed_unknown_flags":int(np.count_nonzero(unknown!=original["unknown_accept"])),"changed_known_accepted_flags":int(np.count_nonzero(known!=original["correct_accepted"]))}
    (output/"summary.json").write_text(json.dumps(summary,indent=2))
    return summary["strict_calibration_correction"]

def main():
    state={"finished":False,"correctness_passed":False,"current":"waiting_for_private_client_series","last_error":None,"completed":[]}
    path=ROOT/"results/calibration_repair_status.json"
    def save(**values):state.update(values);path.write_text(json.dumps(state,indent=2))
    save()
    try:
        while True:
            prior_path=ROOT/"results/private_client_status.json"
            if prior_path.exists():
                try:prior=json.loads(prior_path.read_text())
                except json.JSONDecodeError:time.sleep(1);continue
                if prior.get("finished") or prior.get("last_error"):
                    save(preceding_private_client_error=prior.get("last_error"));break
            time.sleep(5)
        runtime=Path(json.loads((ROOT.parent/"mpc_logs/runtime.json").read_text())["runtime"])
        with (runtime/".msle_v3_driver.lock").open("w") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);save(numeric_self_test=self_test())
            for study in ("binary_frontend","projection_facenet","projection_sface"):
                correction=repair(study,save);state["completed"].append({"study":study,**correction});save()
        save(finished=True,correctness_passed=True,current=None);print("STRICT_CALIBRATION_REPAIR_COMPLETE",flush=True)
    except BaseException as error:
        save(last_error=repr(error));raise

if __name__=="__main__":main()
