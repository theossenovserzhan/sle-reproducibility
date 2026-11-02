"""Prospective open-set confirmation and real larger-gallery utility.

No threshold is fitted to test unknown identities. Repeated image splits are
not treated as independent identities. The previous frequent-ID hard pilot
remains a separate population/protocol and must be reported as such.
"""
from pathlib import Path
import csv
import hashlib
import json
import math
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from evaluate_float_binary import normalize,threshold_from_calibration
from run_experiments import distances,block_values,make_index,retrieve,choose_winner,write_json,write_csv


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def conservative_allowed(n,alpha,confidence=.95):
    """One-sided order-statistic rule; IID identity-score assumption explicit."""
    result=-1
    for k in range(int(math.floor(alpha*n))+1):
        cdf=sum(math.comb(n,j)*alpha**j*(1-alpha)**(n-j) for j in range(k+1))
        if cdf <= 1-confidence:
            result=k
    if result<0:
        raise ValueError("Not enough independent calibration identities for this target/confidence")
    return result


def bootstrap_mean(values,seed,resamples=5000):
    values=np.asarray(values,dtype=float)
    rng=np.random.default_rng(seed)
    estimates=[]
    for start in range(0,resamples,250):
        indices=rng.integers(len(values),size=(min(250,resamples-start),len(values)))
        estimates.extend(values[indices].mean(1).tolist())
    return {"mean":float(values.mean()),"ci95":np.quantile(estimates,[.025,.975]).tolist(),
            "units":len(values),"bootstrap_resamples":resamples}


def split_data(embeddings,split):
    rng=np.random.default_rng(20260722+20000+split)
    gallery,probes,labels,pool_indices=[],[],[],[]
    for row,images in enumerate(embeddings):
        chosen=np.sort(rng.choice(6,2,replace=False))
        held=np.setdiff1d(np.arange(6),chosen)
        gallery.append(images[chosen].mean(0))
        probes.extend(images[held])
        labels.extend([row]*4)
        pool_indices.extend((row*6+held).tolist())
    return np.asarray(gallery),np.asarray(probes),np.asarray(labels),np.asarray(pool_indices)


def index_metrics(gallery,probes,scores,truth,n,output):
    rows=[]
    true_winners=scores.argmax(1)
    for width in (4,8):
        index=make_index(gallery,width)
        vals=block_values(probes,width)
        genuine,agreement,candidates,fallback,correct=[],[],[],[],[]
        for q,blocks in enumerate(vals):
            found,_,_=retrieve(index,blocks)
            best=choose_winner(-scores[q],found)
            use_fallback=len(found)<n and (best<0 or -scores[q,best]>=len(blocks))
            certified=int(true_winners[q]) if use_fallback else best
            assert certified==true_winners[q]
            genuine.append(truth[q] in found)
            agreement.append(best==true_winners[q])
            correct.append(best==truth[q])
            candidates.append(len(found))
            fallback.append(use_fallback)
        capacity=min(n,8+math.ceil(4*n/(1<<width)))
        required=max(map(len,index.values()))
        rows.append({"n_gallery":n,"block_bits":width,"n_probes":len(probes),
                     "image_split":0,"candidate_recall":float(np.mean(genuine)),
                     "exhaustive_decision_agreement":float(np.mean(agreement)),
                     "indexed_rank1":float(np.mean(correct)),"candidate_fraction":float(np.mean(candidates)/n),
                     "certified_fallback_rate":float(np.mean(fallback)),"certified_agreement":1.0,
                     "public_capacity_policy":capacity,"required_capacity":required,
                     "admission_capacity_sufficient":required<=capacity,
                     "overflow_buckets_at_public_capacity":sum(len(b)>capacity for b in index.values())})
    return rows


def main():
    began=time.monotonic()
    cfg=json.loads((ROOT/"lfw_extended_protocol.json").read_text())
    manifest=json.loads((ROOT/"data/lfw_extended_selection.json").read_text())
    progress=json.loads((ROOT/"data/lfw_extended_progress.json").read_text())
    assert progress["completed"]==progress["total"]
    with np.load(ROOT.parent/"float_features/lfw_facenet_vggface2.npz") as old:
        enrolled=old["embeddings"][:128].astype(np.float64)
        old_names={Path(str(r[0])).parts[-2] for r in old["image_ids"]}
    extended=np.load(ROOT/"data/lfw_extended_features.npy",mmap_mode="r").astype(np.float64)
    subjects=manifest["subjects"]
    assert len(set(subjects))==len(subjects) and not old_names.intersection(subjects)
    calibration,test_unknown,distractors=extended[:512],extended[512:1024],extended[1024:]
    sizes=cfg["gallery_sizes"]
    max_distractors=max(sizes)-128
    distractors=distractors[:max_distractors]
    pool=enrolled.reshape(-1,512)
    # Precompute the fixed distractor part once; prototypes of the 128 query
    # identities still change with every frozen 2-gallery/4-probe assignment.
    fixed={}
    for rep in ("float_cosine","binary_hamming"):
        if rep=="float_cosine":
            score=lambda q: normalize(q)@normalize(distractors).T
        else:
            dg=(distractors>=0).astype(np.uint8)
            score=lambda q: -distances((q>=0).astype(np.uint8),dg).astype(float)
        fixed[rep]=[score(pool),score(calibration),score(test_unknown)]
        print(f"Precomputed fixed distractor scores: {rep}",flush=True)
    utility=np.zeros((2,len(sizes),20,128,4),dtype=np.uint8)
    rank5_flags=np.zeros_like(utility)
    unknown_accept=np.zeros((2,len(sizes),20,2,512),dtype=np.uint8)
    dirs=np.zeros_like(unknown_accept)
    closed_rows,open_rows,index_rows=[],[],[]
    k_conservative=conservative_allowed(512,.01)
    strata=np.asarray([1 if n==1 else 2 if n<6 else 3 for n in manifest["source_images_per_identity"][512:1024]])
    cohort_counts={"one_image":int(np.sum(strata==1)),"two_to_five":int(np.sum(strata==2)),"six_or_more":int(np.sum(strata==3))}
    for split in range(20):
        g,p,labels,pool_idx=split_data(enrolled,split)
        for r,rep in enumerate(("float_cosine","binary_hamming")):
            if rep=="float_cosine":
                base=lambda q: normalize(q)@normalize(g).T
            else:
                g_binary=(g>=0).astype(np.uint8)
                base=lambda q: -distances((q>=0).astype(np.uint8),g_binary).astype(float)
            all_scores=np.concatenate([base(p),fixed[rep][0][pool_idx]],axis=1)
            all_cal=np.concatenate([base(calibration),fixed[rep][1]],axis=1)
            all_unknown=np.concatenate([base(test_unknown),fixed[rep][2]],axis=1)
            for s,n in enumerate(sizes):
                scores=all_scores[:,:n]
                genuine=scores[np.arange(len(p)),labels]
                ranks=1+(scores>genuine[:,None]).sum(1)+((scores==genuine[:,None])&(np.arange(n)[None,:]<labels[:,None])).sum(1)
                correct=ranks==1
                utility[r,s,split]=correct.reshape(128,4)
                rank5_flags[r,s,split]=(ranks<=5).reshape(128,4)
                closed_rows.append({"split":split,"representation":rep,"n_gallery":n,
                                    "query_identities":128,"probes":512,"rank1":float(correct.mean()),
                                    "rank5":float(np.mean(ranks<=5))})
                cal_max=all_cal[:,:n].max(1)
                unknown_max=all_unknown[:,:n].max(1)
                for rule,allowed in enumerate((int(.01*512),k_conservative)):
                    threshold=threshold_from_calibration(cal_max,allowed/512)
                    accepted=unknown_max>=threshold
                    direction=correct&(scores.max(1)>=threshold)
                    unknown_accept[r,s,split,rule]=accepted
                    dirs[r,s,split,rule]=direction
                    row={"split":split,"representation":rep,"n_gallery":n,
                         "rule":"empirical" if rule==0 else "conservative_iid_order_statistic",
                         "nominal_target_fpir":.01,"calibration_identities":512,"test_unknown_identities":512,
                         "calibration_allowed_accepts":allowed,"threshold":threshold,
                         "calibration_fpir":float(np.mean(cal_max>=threshold)),
                         "test_fpir":float(accepted.mean()),"test_dir":float(direction.mean())}
                    for code,name in ((1,"one_image"),(2,"two_to_five"),(3,"six_or_more")):
                        use=strata==code
                        row[f"test_{name}_identities"]=int(use.sum())
                        row[f"test_{name}_fpir"]=float(accepted[use].mean()) if use.any() else "not_available"
                    open_rows.append(row)
                if split==0 and rep=="binary_hamming":
                    gallery_binary=np.concatenate([(g>=0).astype(np.uint8),(distractors[:n-128]>=0).astype(np.uint8)])
                    index_rows.extend(index_metrics(gallery_binary,(p>=0).astype(np.uint8),scores,labels,n,ROOT/"results"))
                    path=ROOT/f"data/lfw_gallery_n{n}.npz"
                    np.savez_compressed(path,gallery_roots=gallery_binary,probe_roots=(p>=0).astype(np.uint8),
                                        gallery_labels=np.arange(1,n+1),probe_labels=labels+1)
        print(f"Extended paired split {split+1}/20 complete",flush=True)
    output=ROOT/"results/lfw_extended"
    write_csv(output/"closed_set_splits.csv",closed_rows)
    write_csv(output/"open_set_splits.csv",open_rows)
    write_csv(output/"index_frozen_split.csv",index_rows)
    np.savez_compressed(output/"subject_outcomes.npz",rank1=utility,rank5=rank5_flags,
                        unknown_accept=unknown_accept,correct_accepted=dirs)
    historical=list(csv.DictReader((ROOT.parent/"inputs/historical_randomized_splits.csv").open()))
    historical={int(row["split"]):row for row in historical if row["dataset"]=="LFW"}
    for split in range(20):
        assert utility[1,0,split].mean()==float(historical[split]["rank1"])
        assert rank5_flags[1,0,split].mean()==float(historical[split]["rank5"])
    summary={"protocol_sha256":digest(ROOT/"lfw_extended_protocol.json"),"script_sha256":digest(__file__),
             "extended_features_sha256":digest(ROOT/"data/lfw_extended_features.npy"),"numpy":np.__version__,
             "calibration_identities":512,"fresh_test_unknown_identities":512,"test_unknown_image_count_strata":cohort_counts,
             "historical_20_split_binary_ranks_exact":True,"closed_set":[],"open_set":[],
             "limitations":["custom LFW-derived protocols, not official LFW benchmark", "same 128 query identities across nested galleries and 20 image assignments", "new unknown pool samples all identities with >=1 image; distinct from earlier >=6-image hard pilot", "one image per new identity; conditional on the frozen backbone/preprocessing", "binomial conservative threshold requires IID calibration identity-score assumption; no distribution-shift guarantee", "0.1% FPIR not claimed"],
             "elapsed_s":time.monotonic()-began}
    for s,n in enumerate(sizes):
        float_id=utility[0,s].mean(axis=(0,2))
        binary_id=utility[1,s].mean(axis=(0,2))
        summary["closed_set"].append({"n_gallery":n,"float_rank1":float(float_id.mean()),
            "binary_rank1":float(binary_id.mean()),"float_rank5":float(rank5_flags[0,s].mean()),
            "binary_rank5":float(rank5_flags[1,s].mean()),
            "binary_minus_float_rank1":bootstrap_mean(binary_id-float_id,20261030+s)})
        for r,rep in enumerate(("float_cosine","binary_hamming")):
            for rule in range(2):
                unknown_by_id=unknown_accept[r,s,:,rule,:].mean(0)
                known_by_id=dirs[r,s,:,rule,:].reshape(20,128,4).mean(axis=(0,2))
                summary["open_set"].append({"n_gallery":n,"representation":rep,
                    "rule":"empirical" if rule==0 else "conservative_iid_order_statistic",
                    "test_fpir":bootstrap_mean(unknown_by_id,20480000+100*s+10*r+rule),
                    "test_dir":bootstrap_mean(known_by_id,20481000+100*s+10*r+rule)})
    summary["elapsed_s"]=time.monotonic()-began
    write_json(output/"summary.json",summary)
    print(json.dumps({"closed_set":summary["closed_set"],"open_set_n128":[r for r in summary["open_set"] if r["n_gallery"]==128],"elapsed_s":summary["elapsed_s"]},indent=2))


if __name__=="__main__":
    main()
