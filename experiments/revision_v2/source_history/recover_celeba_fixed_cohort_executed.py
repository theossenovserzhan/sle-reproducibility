"""Recover selected CelebA images using projected Parquet labels + rows API.

Only label columns are range-read from the original frozen Parquet shards.
Only selected image rows are downloaded. No full shard download is allowed.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from collections import Counter
import argparse
import hashlib
import io
import json
import os
import time
import urllib.request
import urllib.parse

import numpy as np

ROOT=Path(__file__).resolve().parent
FIRST=ROOT.parent
DATA=ROOT/"data/celeba"
REVISION="2d738f56e0e7f925ea36ae7c808ea925264aacec"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def request(url,headers=None,limit=256000):
    error=None
    for attempt in range(3):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"M-SLE-revision-research/2.0",**(headers or {})})
            with urllib.request.urlopen(req,timeout=35) as response:
                payload=response.read(limit+1)
                if len(payload)>limit:
                    raise RuntimeError("Response exceeds declared bounded size")
                return payload,dict(response.headers),response.status
        except Exception as exc:
            error=exc
            if attempt<2:
                time.sleep(1+attempt)
    raise error


class RangeFile(io.RawIOBase):
    def __init__(self,url,size):
        super().__init__()
        self.url,self.size,self.pos=url,size,0
        self.bytes_read=0
        self.requests=0
    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos
    def seek(self,offset,whence=0):
        self.pos=offset if whence==0 else self.pos+offset if whence==1 else self.size+offset
        if not 0<=self.pos<=self.size: raise ValueError("seek out of bounds")
        return self.pos
    def read(self,n=-1):
        if n<0 or n>16*1024*1024: raise RuntimeError("Full shard / image column reads are forbidden")
        n=min(n,self.size-self.pos)
        if n==0:return b""
        start,end=self.pos,self.pos+n-1
        headers={"Range":f"bytes={start}-{end}"}
        url=self.url+f"&range_start={start}&range_end={end}"
        req=urllib.request.Request(url,headers={"User-Agent":"M-SLE-revision-research/2.0",**headers})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req,timeout=35) as response:
                    if response.status!=206 or not response.headers.get("Content-Range","").startswith(f"bytes {start}-{end}/"):
                        raise RuntimeError("Server ignored/mis-cached the exact Range request")
                    payload=response.read(n+1)
                if len(payload)!=n:raise RuntimeError("Truncated Range response")
                self.pos+=n
                self.bytes_read+=n
                self.requests+=1
                return payload
            except Exception:
                if attempt==2:raise
                time.sleep(1+attempt)
    def readinto(self,buffer):
        payload=self.read(len(buffer))
        buffer[:len(payload)]=payload
        return len(payload)


def shard_labels(item):
    import pyarrow.parquet as pq
    name=Path(item["path"]).stem
    path=DATA/f"{name}_labels.npy"
    if path.exists():return np.load(path)
    url="https://huggingface.co/datasets/flwrlabs/celeba/resolve/"+REVISION+"/"+urllib.parse.quote(item["path"],safe="/")+"?download=true"
    remote=RangeFile(url,item["size"])
    parquet=pq.ParquetFile(remote,pre_buffer=False)
    labels=parquet.read(columns=["celeb_id"],use_threads=False).column(0).to_numpy()
    np.save(path,labels)
    metadata={"file":item["path"],"source_bytes":item["size"],"rows":len(labels),
              "range_bytes_read":remote.bytes_read,"range_requests":remote.requests,
              "labels_sha256":digest(path),"row_groups":parquet.num_row_groups,
              "first_identity":int(labels[0]),"last_identity":int(labels[-1]),
              "monotone_labels":bool(np.all(labels[1:]>=labels[:-1]))}
    (DATA/f"{name}_metadata.json").write_text(json.dumps(metadata,indent=2))
    print(metadata,flush=True)
    return labels


def labels():
    DATA.mkdir(parents=True,exist_ok=True)
    raw,_,_=request("https://huggingface.co/api/datasets/flwrlabs/celeba/tree/"+REVISION+"/img_align%2Bidentity%2Battr")
    files=sorted([item for item in json.loads(raw) if "/train-" in item["path"]],key=lambda item:item["path"])
    output={}
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs={pool.submit(shard_labels,item):i for i,item in enumerate(files)}
        for job in as_completed(jobs):output[jobs[job]]=job.result()
    all_labels=np.concatenate([output[i] for i in range(len(files))])
    assert len(all_labels)==162770
    np.save(DATA/"train_labels.npy",all_labels)
    print("CelebA train labels recovered",len(all_labels),flush=True)
    return all_labels


def rows_for_identity(identity,positions):
    cache=DATA/f"rows_{identity}.json"
    if cache.exists():return json.loads(cache.read_text())
    base={"dataset":"flwrlabs/celeba","config":"img_align+identity+attr","split":"train"}
    # The published row order is checked against the projected label column.
    if np.all(np.diff(positions)==1):
        batches=[(int(positions[0]),len(positions))]
    else:
        batches=[(int(position),1) for position in positions]
    output=[]
    for offset,length in batches:
        url="https://datasets-server.huggingface.co/rows?"+urllib.parse.urlencode({**base,"offset":offset,"length":length})
        raw,_,_=request(url)
        records=json.loads(raw)["rows"]
        if len(records)!=length:raise RuntimeError("Unexpected rows API count")
        for record in records:
            if int(record["row"]["celeb_id"])!=int(identity):
                raise RuntimeError("Rows API order differs from frozen Parquet order")
            output.append(record)
    assert [int(r["row_idx"]) for r in output]==list(map(int,positions))
    cache.write_text(json.dumps(output))
    return output


def images_for_identity(identity,positions):
    from PIL import Image
    records=rows_for_identity(identity,positions)
    paths=[]
    info=[]
    folder=DATA/"selected_images"
    folder.mkdir(exist_ok=True)
    for record in records:
        row=int(record["row_idx"])
        path=folder/f"train_row_{row}.image"
        image=record["row"]["image"]
        if isinstance(image,list):image=image[0]
        if not path.exists():
            payload,_,_=request(image["src"],limit=1024*1024)
            path.write_bytes(payload)
        with Image.open(path) as loaded:
            size=loaded.size
            image_format=loaded.format
        paths.append(path)
        info.append({"identity":int(identity),"row":row,"image_sha256":digest(path),
                     "dimensions":list(size),"format":image_format})
    return paths,info


def parquet_selected_images(positions):
    """Bypass unavailable thumbnail assets using selected original row groups.

    At most selected row-group image columns are read, never complete shards.
    Cached output contains only the six selected images per identity.
    """
    import pyarrow.parquet as pq
    from PIL import Image
    wanted={int(row):int(identity) for identity,rows in positions.items() for row in rows}
    folder=DATA/"selected_images"
    folder.mkdir(exist_ok=True)
    jobs=[]
    offset=0
    for path in sorted(DATA.glob("train-*_metadata.json")):
        meta=json.loads(path.read_text())
        selected={row-offset:identity for row,identity in wanted.items() if offset<=row<offset+meta["rows"]}
        if selected:jobs.append((meta,offset,selected))
        offset+=meta["rows"]
    assert offset==162770
    def one_shard(job):
        meta,offset,selected=job
        pending={row:identity for row,identity in selected.items() if not (folder/f"train_row_{offset+row}.image").exists()}
        remote=None
        groups_read=0
        if pending:
            url="https://huggingface.co/datasets/flwrlabs/celeba/resolve/"+REVISION+"/"+urllib.parse.quote(meta["file"],safe="/")+"?download=true"
            remote=RangeFile(url,meta["source_bytes"])
            parquet=pq.ParquetFile(remote,pre_buffer=False)
            base=0
            for group in range(parquet.num_row_groups):
                count=parquet.metadata.row_group(group).num_rows
                needed=[row for row in pending if base<=row<base+count]
                if needed:
                    records=parquet.read_row_group(group,columns=["image","celeb_id"],use_threads=False).to_pylist()
                    groups_read+=1
                    for row in needed:
                        record=records[row-base]
                        if int(record["celeb_id"])!=pending[row]:raise RuntimeError("Original Parquet identity mismatch")
                        payload=record["image"]["bytes"]
                        if payload is None:raise RuntimeError("Original image bytes missing")
                        (folder/f"train_row_{offset+row}.image").write_bytes(payload)
                base+=count
        stats={"shard":meta["file"],"selected_images":len(selected),"groups_read_this_run":groups_read,
               "range_bytes_this_run":remote.bytes_read if remote else 0,"range_requests_this_run":remote.requests if remote else 0}
        print("CelebA original selected row groups",stats,flush=True)
        return stats
    with ThreadPoolExecutor(max_workers=3) as pool:
        stats=list(pool.map(one_shard,jobs))
    (DATA/"original_image_range_download.json").write_text(json.dumps(stats,indent=2))
    paths,metadata={},{}
    for identity,rows in positions.items():
        paths[identity],metadata[identity]=[],[]
        for row in rows:
            path=folder/f"train_row_{int(row)}.image"
            with Image.open(path) as loaded:
                size,fmt=loaded.size,loaded.format
            paths[identity].append(path)
            metadata[identity].append({"identity":int(identity),"row":int(row),"image_sha256":digest(path),
                "dimensions":list(size),"format":fmt,"source":"original frozen Parquet image bytes"})
    return paths,metadata


def extract(download_only=False):
    import torch
    import torchvision
    from PIL import Image
    from torchvision import transforms
    from facenet_pytorch import InceptionResnetV1
    from evaluate_float_binary import evaluate
    target=DATA/"celeba_facenet_vggface2.npz"
    if target.exists():
        evaluate(target,ROOT/"results/celeba_paired","CelebA")
        return
    all_labels=np.load(DATA/"train_labels.npy") if (DATA/"train_labels.npy").exists() else labels()
    with np.load(FIRST/"inputs/celeba_128_binary_roots.npz") as frozen:
        evaluation=list(map(int,frozen["gallery_labels"]))
    counts=Counter(map(int,all_labels))
    eligible=sorted(identity for identity,count in counts.items() if count>=6 and identity not in evaluation)
    rng=np.random.default_rng(20261029)
    extra=list(map(int,rng.choice(eligible,64,replace=False)))
    identities=evaluation+sorted(extra[:32])+sorted(extra[32:])
    positions={identity:np.flatnonzero(all_labels==identity)[:6] for identity in identities}
    if any(len(p)!=6 for p in positions.values()):raise RuntimeError("Frozen evaluation identity unavailable")
    selection={"revision":REVISION,"evaluation":evaluation,"calibration":identities[128:160],
               "test_unknown":identities[160:],"row_indices":{str(i):p.tolist() for i,p in positions.items()},
               "selection":"same frozen evaluation IDs, first six train rows per identity; extras sampled using availability only"}
    (DATA/"selection.json").write_text(json.dumps(selection,indent=2))
    image_paths,image_metadata=parquet_selected_images(positions)
    (DATA/"image_provenance.json").write_text(json.dumps(image_metadata,indent=2))
    if download_only:
        print("CelebA selected images cached; CPU feature extraction deferred until secure timings finish",flush=True)
        return
    torch.set_num_threads(2)
    os.environ.setdefault("TORCH_HOME",str(FIRST/"model_cache"))
    model=InceptionResnetV1(pretrained="vggface2").eval()
    transform=transforms.Compose([transforms.Resize((160,160)),transforms.ToTensor(),transforms.Normalize([.5]*3,[.5]*3)])
    ordered=[path for identity in identities for path in image_paths[identity]]
    batches=[]
    with torch.inference_mode():
        for start in range(0,len(ordered),32):
            images=[Image.open(path).convert("RGB") for path in ordered[start:start+32]]
            tensor=torch.stack([transform(image) for image in images])
            batches.append(torch.nn.functional.normalize(model(tensor),dim=1).numpy())
            if start%256==0:print(f"CelebA FaceNet {start+len(images)}/{len(ordered)}",flush=True)
    embeddings=np.concatenate(batches).astype(np.float32).reshape(192,6,512)
    ids=np.asarray([[f"celeba_train_row_{int(p)}" for p in positions[identity]] for identity in identities])
    np.savez_compressed(target,embeddings=embeddings,identities=np.asarray(identities),image_ids=ids)
    with np.load(FIRST/"inputs/celeba_128_binary_roots.npz") as frozen:
        g=(embeddings[:128,:2].mean(1)>=0).astype(np.uint8)
        p=(embeddings[:128,2:]>=0).astype(np.uint8).reshape(-1,512)
        checks={"gallery_bit_mismatches":int(np.count_nonzero(g!=frozen["gallery_roots"])),
                "probe_bit_mismatches":int(np.count_nonzero(p!=frozen["probe_roots"]))}
    (DATA/"extraction.json").write_text(json.dumps({"features_sha256":digest(target),"script_sha256":digest(__file__),
           "torch":torch.__version__,"torchvision":torchvision.__version__,"numpy":np.__version__,
           "selection_sha256":digest(DATA/"selection.json"),"source_revision":REVISION,"frozen_binary_checks":checks},indent=2))
    print(checks,flush=True)
    evaluate(target,ROOT/"results/celeba_paired","CelebA")


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--phase",choices=["labels","download","extract"],required=True)
    args=parser.parse_args()
    sys_path=FIRST
    import sys
    sys.path.insert(0,str(sys_path))
    if args.phase=="labels":labels()
    else:extract(download_only=args.phase=="download")
