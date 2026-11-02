"""Generated evaluator; exact same frozen image/cohort/calibration rules."""
from pathlib import Path
import hashlib,json
import numpy as np
from run_binary_frontend import bootstrap_mean,conservative_allowed,index_metrics,split_data,threshold_from_calibration,distances,write_csv
ROOT=Path(__file__).resolve().parent
METHODS=()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def update(state,**values):
    state.update(values)
    path=ROOT/("results/projection_"+state["frontend"]+"_status.json")
    temporary=path.with_name(path.name+".next")
    temporary.write_text(json.dumps(state,indent=2));temporary.replace(path)
def scores(left,right,binary):
    product=left@right.T
    return 2*product-left.sum(1)[:,None]-right.sum(1)[None,:] if binary else product

def evaluate(cfg,model,metadata,extended,state):
    output=ROOT/("results/projection_"+state["frontend"])
    output.mkdir(exist_ok=True)
    with np.load(Path(metadata["feature_archive"])) as old:
        enrolled=old["embeddings"][:128].astype(np.float64)
    calibration,unknown,distractors=extended[:512],extended[512:1024],extended[1024:4992]
    with np.load(Path(metadata["baseline_outcomes_archive"])) as old:
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
        pool=transform(enrolled.reshape(-1,enrolled.shape[-1]),method,model)
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
        if method in ("original_cosine",METHODS[1]):
            old_index=0 if method=="original_cosine" else 1
            assert np.array_equal(rank1[method_index],original_rank1[old_index]),"R1 rank1 baseline changed"
            assert np.array_equal(rank5[method_index],original_rank5[old_index]),"R1 rank5 baseline changed"
        print("FRONTEND_METHOD_COMPLETE "+method,flush=True)
    np.savez_compressed(output/"subject_outcomes.npz",rank1=rank1,rank5=rank5,unknown_accept=unknown_accept,correct_accepted=known_accept)
    write_csv(output/"closed_set_splits.csv",closed_rows)
    write_csv(output/"open_set_splits.csv",open_rows)
    write_csv(output/"index_frozen_split.csv",index_rows)
    summary={"methods":list(METHODS),"model_sha256":metadata["model_sha256"],
        "protocol_sha256":sha(ROOT/"projection_code_protocol.json"),"script_sha256":sha(__file__),
        "frozen_frontend_baselines_reproduced_exactly":True,"closed_set":[],"open_set":[],
        "scope":"Predefined development study, all methods retained. Repeated image assignments are not independent identities. Random hyperplanes are established preprocessing, not the protected-system novelty. No MPC timings are estimated as measured results."}
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
