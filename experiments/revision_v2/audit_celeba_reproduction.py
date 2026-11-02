from pathlib import Path
import csv,json,sys
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent))
from evaluate_float_binary import scores_for,bootstrap_subject_delta
rows=list(csv.DictReader((ROOT/"results/celeba_paired/paired_split_metrics.csv").open()))
historical={int(r["split"]):r for r in csv.DictReader((ROOT.parent/"inputs/historical_randomized_splits.csv").open()) if r["dataset"]=="CelebA"}
comparison=[]
for row in rows:
    if row["representation"]!="binary_hamming":continue
    old=historical[int(row["split"])]
    comparison.append({"split":int(row["split"]),"rank1_exact":float(row["rank1"])==float(old["rank1"]),"rank5_exact":float(row["rank5"])==float(old["rank5"]),"new_rank1":float(row["rank1"]),"historical_rank1":float(old["rank1"])})
with np.load(ROOT/"data/celeba/celeba_facenet_vggface2.npz") as source:e=source["embeddings"][:128].astype(np.float64)
g,p=e[:,:2].mean(1),e[:,2:].reshape(-1,512)
truth=np.repeat(np.arange(128),4)
fixed={}
flags={}
for rep in ("float_cosine","binary_hamming"):
    scores=scores_for(g,p,rep)
    order=np.argsort(-scores,axis=1,kind="stable")
    flags[rep]=(order[:,0]==truth).reshape(128,4).mean(1)
    fixed[rep]={"rank1":float(flags[rep].mean()),"rank5":float(np.mean(np.any(order[:,:5]==truth[:,None],axis=1)))}
fixed["paired_delta_rank1"]=bootstrap_subject_delta(flags["float_cosine"],flags["binary_hamming"],np.random.default_rng(20261029))
result={"comparison_scope":"new resplits on the fixed main-paper cohort versus the distinct historical external cohort; equality is not expected across different populations","all_20_split_binary_rank1_rank5_exact":len(comparison)==20 and all(r["rank1_exact"] and r["rank5_exact"] for r in comparison),"splits":comparison,"fixed_original_two_gallery_four_probe":fixed}
(ROOT/"results/celeba_paired/historical_reproduction.json").write_text(json.dumps(result,indent=2))
print(json.dumps({"all_historical_splits_exact":result["all_20_split_binary_rank1_rank5_exact"],"fixed_original":fixed},indent=2))
