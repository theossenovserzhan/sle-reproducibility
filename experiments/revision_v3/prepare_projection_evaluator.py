"""Reuse the completed evaluator without altering its frozen ITQ source."""
from pathlib import Path
import ast,hashlib,json

ROOT=Path(__file__).resolve().parent

def main():
    original=(ROOT/"run_binary_frontend.py").read_text()
    tree=ast.parse(original)
    function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="evaluate")
    source=ast.get_source_segment(original,function)
    substitutions={
        'ROOT/"results/binary_frontend"':'ROOT/("results/projection_"+state["frontend"])',
        'ROOT.parent/"float_features/lfw_facenet_vggface2.npz"':'Path(metadata["feature_archive"])',
        'ROOT.parent/"revision_v2/results/lfw_extended/subject_outcomes.npz"':'Path(metadata["baseline_outcomes_archive"])',
        'enrolled.reshape(-1,512)':'enrolled.reshape(-1,enrolled.shape[-1])',
        'method in ("original_cosine","original_sign_512")':'method in ("original_cosine",METHODS[1])',
        'ROOT/"binary_frontend_protocol.json"':'ROOT/"projection_code_protocol.json"',
        '"R1_baselines_reproduced_exactly"':'"frozen_frontend_baselines_reproduced_exactly"',
        'ITQ is established preprocessing':'Random hyperplanes are established preprocessing'
    }
    for old,new in substitutions.items():
        assert old in source,old
        source=source.replace(old,new)
    header='''"""Generated evaluator; exact same frozen image/cohort/calibration rules."""
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
'''
    target=ROOT/"projection_evaluator.py"
    target.write_text(header+"\n"+source+"\n")
    (ROOT/"results/projection_evaluator_audit.json").write_text(json.dumps({"base_sha256":sha(ROOT/"run_binary_frontend.py"),"generated_sha256":sha(target),"changes":"Only feature/reference/protocol/output paths and native width; all predefined score/calibration/uncertainty calculations retained."},indent=2))
    print("PROJECTION_EVALUATOR_READY")

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
if __name__=="__main__":main()
