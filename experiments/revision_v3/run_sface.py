"""Independent CPU frontend on the exact frozen images, after MPC timing."""
from pathlib import Path
import argparse,fcntl,hashlib,importlib,json,os,shutil,subprocess,sys,tarfile,time
import numpy as np

ROOT=Path(__file__).resolve().parent
FIRST=ROOT.parent
sys.path.insert(0,str(FIRST))
sys.path.insert(0,str(FIRST/"revision_v2"))

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def atomic_json(path,value):
    temporary=path.with_name(path.name+".next")
    temporary.write_text(json.dumps(value,indent=2));temporary.replace(path)

def selection():
    groups={};entries=[];sources={}
    for name,path in (("lfw",FIRST/"float_features/lfw_facenet_vggface2.npz"),
        ("celeba",FIRST/"revision_v2/data/celeba/celeba_facenet_vggface2.npz"),
        ("celeba_external",FIRST/"revision_v2/data/celeba_external/celeba_external_facenet_vggface2.npz")):
        with np.load(path) as old:
            identities=old["identities"].tolist();image_ids=old["image_ids"].tolist()
        start=len(entries)
        for identity,row in zip(identities,image_ids):
            for image_id in row:
                item={"group":name,"identity":str(identity),"image_id":str(image_id),"source":"lfw_archive" if name=="lfw" else "celeba_cache"}
                if name!="lfw":
                    item["row"]=int(str(image_id).removeprefix("celeba_train_row_"))
                entries.append(item)
        groups[name]={"start":start,"stop":len(entries),"identities":identities,"image_ids":image_ids}
        sources[name+"_features_sha256"]=sha(path)
    extended_path=FIRST/"revision_v2/data/lfw_extended_selection.json"
    extended=json.loads(extended_path.read_text())
    start=len(entries)
    for identity,image_id in zip(extended["subjects"],extended["image_ids"]):
        entries.append({"group":"lfw_extended","identity":identity,"image_id":image_id,"source":"lfw_archive"})
    groups["lfw_extended"]={"start":start,"stop":len(entries),"identities":extended["subjects"],"image_ids":extended["image_ids"]}
    sources["lfw_extended_selection_sha256"]=sha(extended_path)
    manifest={"groups":groups,"entries":entries,"sources":sources,"protocol_sha256":sha(ROOT/"second_encoder_protocol.json")}
    target=ROOT/"data/sface_selection.json"
    if target.exists():assert json.loads(target.read_text())==manifest,"Frozen SFace image selection changed"
    else:atomic_json(target,manifest)
    return manifest,sha(target)

def cv_runtime():
    assets=json.loads((ROOT/"data/sface_assets.json").read_text())
    assert assets["protocol_sha256"]==sha(ROOT/"second_encoder_protocol.json")
    for role in ("recognition","detector","opencv_wheel"):
        assert sha(ROOT/assets[role]["path"])==assets[role]["sha256"]
    library=ROOT/"data/opencv_libs"
    sys.path.insert(0,str(library))
    try:import cv2 as cv
    except ImportError:
        wheel=ROOT/assets["opencv_wheel"]["path"]
        subprocess.run([sys.executable,"-m","pip","install","--no-deps","--no-compile","--disable-pip-version-check","--target",str(library),str(wheel)],check=True)
        importlib.invalidate_caches()
        import cv2 as cv
    assert cv.__version__=="4.11.0",cv.__version__
    cv.setNumThreads(2);cv.ocl.setUseOpenCL(False)
    return cv,assets

def extract(save):
    cfg=json.loads((ROOT/"second_encoder_protocol.json").read_text())
    manifest,selection_hash=selection()
    entries=manifest["entries"];total=len(entries)
    cv,assets=cv_runtime()
    recognizer=cv.FaceRecognizerSF.create(model=str(ROOT/assets["recognition"]["path"]),config="",backend_id=cv.dnn.DNN_BACKEND_OPENCV,target_id=cv.dnn.DNN_TARGET_CPU)
    detector=cv.FaceDetectorYN.create(model=str(ROOT/assets["detector"]["path"]),config="",input_size=(250,250),score_threshold=cfg["detector_score_threshold"],nms_threshold=cfg["detector_nms_threshold"],top_k=5000,backend_id=cv.dnn.DNN_BACKEND_OPENCV,target_id=cv.dnn.DNN_TARGET_CPU)
    progress_path=ROOT/"data/sface_progress.json"
    feature_path=ROOT/"data/sface_all_features.npy"
    audit_path=ROOT/"data/sface_image_audit.jsonl"
    start=0
    if progress_path.exists():
        progress=json.loads(progress_path.read_text())
        assert progress["selection_sha256"]==selection_hash and progress["script_sha256"]==sha(__file__)
        start=progress["completed"]
        features=np.lib.format.open_memmap(feature_path,mode="r+")
        assert features.shape==(total,128)
        old_audit=audit_path.read_text().splitlines() if audit_path.exists() else []
        assert len(old_audit)>=start
        if len(old_audit)>start:
            shutil.copy2(audit_path,ROOT/f"logs/sface_interrupted_audit_{time.time_ns()}.jsonl")
            audit_path.write_text("\n".join(old_audit[:start])+"\n")
    else:
        features=np.lib.format.open_memmap(feature_path,mode="w+",dtype=np.float32,shape=(total,128))
    if start<total:
        wanted={item["image_id"] for item in entries[start:] if item["source"]=="lfw_archive"}
        archive_path=FIRST/"image_cache/lfw_home/lfw-funneled.tgz"
        assert sha(archive_path)=="b47c8422c8cded889dc5a13418c4bc2abbda121092b3533a83306f90d900100a"
        lfw_bytes={}
        with tarfile.open(archive_path) as archive:
            for member in archive:
                if member.name in wanted:
                    with archive.extractfile(member) as stream:lfw_bytes[member.name]=stream.read()
        assert set(lfw_bytes)==wanted,"Frozen LFW image not found in the archive"
        provenance={}
        for path in (FIRST/"revision_v2/data/celeba/image_provenance.json",FIRST/"revision_v2/data/celeba_external/image_provenance.json"):
            for rows in json.loads(path.read_text()).values():
                for item in rows:
                    if item["row"] in provenance:assert provenance[item["row"]]==item["image_sha256"]
                    provenance[item["row"]]=item["image_sha256"]
        with audit_path.open("a") as audit:
            for index in range(start,total):
                item=entries[index]
                if item["source"]=="lfw_archive":payload=lfw_bytes[item["image_id"]]
                else:
                    payload=(FIRST/f"revision_v2/data/celeba/selected_images/train_row_{item['row']}.image").read_bytes()
                    assert hashlib.sha256(payload).hexdigest()==provenance[item["row"]]
                image=cv.imdecode(np.frombuffer(payload,dtype=np.uint8),cv.IMREAD_COLOR)
                assert image is not None and image.ndim==3,(index,item)
                height,width=image.shape[:2]
                detector.setInputSize((width,height))
                faces=detector.detect(image)[1]
                count=0 if faces is None else len(faces)
                if count:
                    face=sorted(faces,key=lambda row:(-float(row[2]*row[3]),-float(row[-1]),tuple(map(float,row[:4]))))[0]
                    aligned=recognizer.alignCrop(image,face[:14])
                    chosen={"bbox":list(map(float,face[:4])),"confidence":float(face[-1])}
                else:
                    side=min(height,width);left=(width-side)//2;top=(height-side)//2
                    aligned=cv.resize(image[top:top+side,left:left+side],(112,112),interpolation=cv.INTER_LINEAR)
                    chosen=None
                vector=recognizer.feature(aligned).reshape(-1).astype(np.float64)
                assert len(vector)==128 and np.isfinite(vector).all() and np.linalg.norm(vector)>1e-10
                features[index]=(vector/np.linalg.norm(vector)).astype(np.float32)
                audit.write(json.dumps({"index":index,"group":item["group"],"image_id":item["image_id"],"source_image_sha256":hashlib.sha256(payload).hexdigest(),"detected_faces":count,"fallback":count==0,"selected":chosen})+"\n")
                if (index+1)%64==0 or index+1==total:
                    features.flush();audit.flush()
                    progress={"completed":index+1,"total":total,"selection_sha256":selection_hash,"script_sha256":sha(__file__),"opencv":cv.__version__,"backend":"OpenCV DNN CPU; two threads; OpenCL disabled"}
                    atomic_json(progress_path,progress)
                    save(current={"phase":"extract","completed":index+1,"total":total})
                    print(f"SFACE_FEATURES {index+1}/{total}",flush=True)
    for group,description in manifest["groups"].items():
        values=np.asarray(features[description["start"]:description["stop"]])
        if group=="lfw_extended":np.save(ROOT/"data/sface_lfw_extended_features.npy",values)
        else:
            np.savez_compressed(ROOT/f"data/sface_{group}.npz",embeddings=values.reshape(len(description["identities"]),6,128),identities=np.asarray(description["identities"]),image_ids=np.asarray(description["image_ids"]))
    audit=[json.loads(line) for line in audit_path.read_text().splitlines()]
    assert len(audit)==total
    summary={"selection_sha256":selection_hash,"features_sha256":sha(feature_path),"script_sha256":sha(__file__),"opencv":cv.__version__,"numpy":np.__version__,"feature_dimension":128,"entries":total,"groups":{name:{"images":sum(row["group"]==name for row in audit),"detection_fallbacks":sum(row["group"]==name and row["fallback"] for row in audit),"multiple_faces":sum(row["group"]==name and row["detected_faces"]>1 for row in audit)} for name in manifest["groups"]},"images_excluded":0}
    atomic_json(ROOT/"data/sface_extraction.json",summary)
    print(json.dumps(summary,indent=2),flush=True)

def evaluate_external():
    from evaluate_float_binary import split_prototypes,scores_for
    from evaluate_lfw_extended import bootstrap_mean
    from run_experiments import write_csv
    with np.load(ROOT/"data/sface_celeba_external.npz") as archive:embeddings=archive["embeddings"].astype(np.float64)
    outcomes=np.zeros((2,20,128,4),dtype=np.uint8)
    rank5=np.zeros_like(outcomes);rows=[]
    for split in range(20):
        gallery,probes,truth,_=split_prototypes(embeddings,split,20260722+10000)
        for index,rep in enumerate(("float_cosine","binary_hamming")):
            order=np.argsort(-scores_for(gallery,probes,rep),axis=1,kind="stable")
            outcomes[index,split]=(order[:,0]==truth).reshape(128,4)
            rank5[index,split]=np.any(order[:,:5]==truth[:,None],axis=1).reshape(128,4)
            rows.append({"split":split,"representation":rep,"rank1":float(outcomes[index,split].mean()),"rank5":float(rank5[index,split].mean())})
    output=ROOT/"results/sface_celeba_external";output.mkdir(exist_ok=True)
    write_csv(output/"closed_set_splits.csv",rows)
    np.savez_compressed(output/"subject_outcomes.npz",rank1=outcomes,rank5=rank5)
    summary={"frontend":"SFace128D+YuNet alignment","cohort":"separate frozen historical CelebA128; one identity overlaps the main fixed cohort, do not pool uncertainty", "rank1":{},"rank5":{}}
    for name,array in (("rank1",outcomes),("rank5",rank5)):
        by_id=array.mean(axis=(1,3))
        summary[name]={"float":float(by_id[0].mean()),"binary":float(by_id[1].mean()),"binary_minus_float":bootstrap_mean(by_id[1]-by_id[0],20261101)}
    atomic_json(output/"summary.json",summary)

def main(after_aes,after_poly_query=False,after_vector_query=False):
    prerequisite="vector_query" if after_vector_query else ("poly_query" if after_poly_query else ("aes_baseline" if after_aes else None))
    state={"finished":False,"current":"waiting_for_"+prerequisite if prerequisite else "starting","last_error":None}
    def save(**values):state.update(values);atomic_json(ROOT/"results/sface_status.json",state)
    save()
    try:
        if prerequisite:
            while True:
                path=ROOT/("results/"+prerequisite+"_status.json")
                if path.exists():
                    try:prior=json.loads(path.read_text())
                    except json.JSONDecodeError:time.sleep(1);continue
                    if prior.get("finished") or prior.get("last_error"):
                        save(preceding_mpc_error=prior.get("last_error"));break
                time.sleep(5)
        runtime=Path(json.loads((FIRST/"mpc_logs/runtime.json").read_text())["runtime"])
        with (runtime/".msle_v3_driver.lock").open("w") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            for proc in Path("/proc").iterdir():
                if not proc.name.isdigit():continue
                try:
                    if Path(os.readlink(proc/"cwd")).resolve()!=runtime:continue
                    command=(proc/"cmdline").read_bytes()
                    assert b"shamir-party.x" not in command and b"compile.py" not in command,"Runtime still has an MPC process; do not overlap extraction"
                except (OSError,PermissionError):pass
            extract(save)
            save(current="evaluate_LFW_extended")
            # Execute generated adapters as separate processes to keep their
            # imports/output provenance separate from the extraction runtime.
            subprocess.run([sys.executable,"evaluate_sface_lfw_extended.py"],cwd=ROOT,check=True)
            for dataset,name in (("LFW","lfw"),("CelebA","celeba")):
                save(current="evaluate_"+name+"_original_cohort")
                subprocess.run([sys.executable,"evaluate_float_binary_128.py","--input",str(ROOT/f"data/sface_{name}.npz"),"--output",str(ROOT/f"results/sface_{name}_paired"),"--dataset",dataset],cwd=ROOT,check=True)
            save(current="evaluate_CelebA_external")
            evaluate_external()
            save(current="evaluate_frozen_projection_codes")
            from run_projection_codes import run as evaluate_projection
            evaluate_projection("sface")
        save(finished=True,current=None)
        print("SFACE_FRONTEND_COMPLETE",flush=True)
    except BaseException as error:
        save(last_error=repr(error));raise

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--after-aes",action="store_true");parser.add_argument("--after-poly-query",action="store_true");parser.add_argument("--after-vector-query",action="store_true")
    args=parser.parse_args();main(args.after_aes,args.after_poly_query,args.after_vector_query)
