"""Recover the distinct 20260722 CelebA cohort of the old 20-split study."""
from pathlib import Path
from collections import Counter
import argparse,json,sys,os,hashlib,csv
import numpy as np
import recover_celeba as recovery

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"data/celeba_external"
OUT.mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT.parent))
from evaluate_float_binary import split_prototypes,scores_for,bootstrap_subject_delta

def main(download_only):
    labels=np.load(recovery.DATA/"train_labels.npy")
    counts=Counter(map(int,labels))
    eligible=sorted(i for i,n in counts.items() if n>=6)
    ids=sorted(map(int,np.random.default_rng(20260722).choice(eligible,128,replace=False)))
    positions={identity:np.flatnonzero(labels==identity)[:6] for identity in ids}
    fixed=np.load(ROOT.parent/"inputs/celeba_128_binary_roots.npz")["gallery_labels"]
    manifest={"seed":20260722,"eligibility":"all train identities with >=6 images","source_revision":recovery.REVISION,
        "identities":ids,"image_rows":{str(i):p.tolist() for i,p in positions.items()},"overlap_with_main_fixed_cohort":len(set(ids)&set(map(int,fixed))),
        "reason":"historical external 20-split cohort sampled with a different seed from the fixed main-paper cohort"}
    (OUT/"selection.json").write_text(json.dumps(manifest,indent=2))
    target=OUT/"celeba_external_facenet_vggface2.npz"
    if not target.exists():
        paths,provenance=recovery.parquet_selected_images(positions)
        (OUT/"image_provenance.json").write_text(json.dumps(provenance,indent=2))
        if download_only:
            print("External CelebA original images cached; cohort overlap",manifest["overlap_with_main_fixed_cohort"],flush=True)
            return
        import torch,torchvision
        from PIL import Image
        from torchvision import transforms
        from facenet_pytorch import InceptionResnetV1
        torch.set_num_threads(2)
        os.environ.setdefault("TORCH_HOME",str(ROOT.parent/"model_cache"))
        model=InceptionResnetV1(pretrained="vggface2").eval()
        transform=transforms.Compose([transforms.Resize((160,160)),transforms.ToTensor(),transforms.Normalize([.5]*3,[.5]*3)])
        ordered=[p for i in ids for p in paths[i]]
        features=[]
        with torch.inference_mode():
            for start in range(0,len(ordered),32):
                images=[transform(Image.open(p).convert("RGB")) for p in ordered[start:start+32]]
                features.append(torch.nn.functional.normalize(model(torch.stack(images)),dim=1).numpy())
                if start%256==0:print("External CelebA features",start+len(images),"/",len(ordered),flush=True)
        embeddings=np.concatenate(features).astype(np.float32).reshape(128,6,512)
        np.savez_compressed(target,embeddings=embeddings,identities=np.asarray(ids),image_ids=np.asarray([[f"celeba_train_row_{int(p)}" for p in positions[i]] for i in ids]))
        (OUT/"extraction.json").write_text(json.dumps({"features_sha256":recovery.digest(target),"script_sha256":recovery.digest(__file__),"torch":torch.__version__,"torchvision":torchvision.__version__,"selection_sha256":recovery.digest(OUT/"selection.json")},indent=2))
    with np.load(target) as data:embeddings=data["embeddings"].astype(np.float64)
    results,subject=[],[]
    for split in range(20):
        g,p,truth,_=split_prototypes(embeddings,split,20260722+10000)
        for rep in ("float_cosine","binary_hamming"):
            order=np.argsort(-scores_for(g,p,rep),axis=1,kind="stable")
            rank1=(order[:,0]==truth).reshape(128,4)
            rank5=np.any(order[:,:5]==truth[:,None],axis=1).reshape(128,4)
            results.append({"dataset":"CelebA_external_historical","split":split,"representation":rep,"rank1":float(rank1.mean()),"rank5":float(rank5.mean())})
            for i in range(128):subject.append({"split":split,"rep":rep,"subject":i,"rank1":float(rank1[i].mean()),"rank5":float(rank5[i].mean())})
    output=ROOT/"results/celeba_external_paired"
    output.mkdir(exist_ok=True)
    with (output/"paired_split_metrics.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
    paired={}
    for metric in ("rank1","rank5"):
        values={rep:np.asarray([np.mean([r[metric] for r in subject if r["rep"]==rep and r["subject"]==i]) for i in range(128)]) for rep in ("float_cosine","binary_hamming")}
        paired[metric]=bootstrap_subject_delta(values["float_cosine"],values["binary_hamming"],np.random.default_rng(20261029))
        paired[metric].update(float_mean=float(values["float_cosine"].mean()),binary_mean=float(values["binary_hamming"].mean()))
    old={int(r["split"]):r for r in csv.DictReader((ROOT.parent/"inputs/historical_randomized_splits.csv").open()) if r["dataset"]=="CelebA"}
    comparison=[{"split":r["split"],"rank1_exact":r["rank1"]==float(old[r["split"]]["rank1"]),"rank5_exact":r["rank5"]==float(old[r["split"]]["rank5"])} for r in results if r["representation"]=="binary_hamming"]
    summary={"paired":paired,"comparison":comparison,"all_20_historical_ranks_exact":all(r["rank1_exact"] and r["rank5_exact"] for r in comparison),"feature_sha256":recovery.digest(target),"selection":manifest}
    (output/"paired_summary.json").write_text(json.dumps(summary,indent=2))
    print(json.dumps({"paired":paired,"all_20_historical_ranks_exact":summary["all_20_historical_ranks_exact"]},indent=2))

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--download-only",action="store_true");args=parser.parse_args();main(args.download_only)
