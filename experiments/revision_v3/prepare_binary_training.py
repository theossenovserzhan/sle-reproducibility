"""Audit the unused identity pool without fitting or inspecting recognition scores."""
from pathlib import Path
import hashlib,json
import numpy as np

ROOT=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    cfg=json.loads((ROOT/"binary_frontend_protocol.json").read_text())
    source=ROOT.parent/"revision_v2/data/lfw_extended_selection.json"
    manifest=json.loads(source.read_text())
    names=manifest["subjects"]
    boundary=512+512+(4096-128)
    rows=list(range(boundary,len(names)))
    assert len(rows)==cfg["expected_training_identities"]
    assert len(set(names))==len(names)
    with np.load(ROOT.parent/"float_features/lfw_facenet_vggface2.npz") as first:
        original_names={Path(str(row[0])).parts[-2] for row in first["image_ids"]}
    training_names={names[i] for i in rows}
    assert not training_names.intersection(original_names)
    assert not training_names.intersection(names[:boundary])
    feature_path=ROOT.parent/"revision_v2/data/lfw_extended_features.npy"
    features=np.load(feature_path,mmap_mode="r")
    assert features.shape==(len(names),512)
    selected={"protocol_sha256":sha(ROOT/"binary_frontend_protocol.json"),
        "source_selection_sha256":sha(source),"feature_sha256":sha(feature_path),
        "training_count":len(rows),"row_indices":rows,
        "subjects":[names[i] for i in rows],"image_ids":[manifest["image_ids"][i] for i in rows],
        "original_identities_excluded":len(original_names),
        "calibration_unknown_and_used_distractors_excluded":boundary,
        "all_disjointness_checks_passed":True,
        "scores_observed":False,"transform_fitted":False}
    out=ROOT/"data/binary_frontend_training_selection.json"
    out.parent.mkdir(exist_ok=True)
    if out.exists():
        previous=json.loads(out.read_text())
        assert {k:v for k,v in previous.items() if k!="protocol_sha256"}=={k:v for k,v in selected.items() if k!="protocol_sha256"},"Frozen training selection changed"
        assert not (ROOT/"data/binary_frontend_model.npz").exists(),"Do not amend protocol after fitting"
    out.write_text(json.dumps(selected,indent=2))
    print(json.dumps({k:selected[k] for k in ("training_count","original_identities_excluded","calibration_unknown_and_used_distractors_excluded","all_disjointness_checks_passed","scores_observed","transform_fitted")},indent=2))

if __name__=="__main__":main()
