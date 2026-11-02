"""Adapt only input paths and feature width; preserve the frozen R1 split rules."""
from pathlib import Path
import hashlib,json

ROOT=Path(__file__).resolve().parent

def main():
    first=ROOT.parent
    paired=(first/"evaluate_float_binary.py").read_text()
    paired=paired.replace("512","128")
    paired=paired.replace('"dataset": dataset_name, "input_sha256"','"frontend":"SFace128D with YuNet alignment", "dataset": dataset_name, "input_sha256"')
    paired=paired.replace('"not evidence of generalization to an unseen recognition backbone"','"conditional on this SFace frontend and its alignment; do not pool with FaceNet outcomes"')
    (ROOT/"evaluate_float_binary_128.py").write_text(paired)
    source=(first/"revision_v2/evaluate_lfw_extended.py").read_text()
    replacements={
        'ROOT/"lfw_extended_protocol.json"':'ROOT.parent/"revision_v2/lfw_extended_protocol.json"',
        'ROOT/"data/lfw_extended_selection.json"':'ROOT.parent/"revision_v2/data/lfw_extended_selection.json"',
        'ROOT/"data/lfw_extended_progress.json"':'ROOT/"data/sface_progress.json"',
        'ROOT.parent/"float_features/lfw_facenet_vggface2.npz"':'ROOT/"data/sface_lfw.npz"',
        'ROOT/"data/lfw_extended_features.npy"':'ROOT/"data/sface_lfw_extended_features.npy"',
        'pool=enrolled.reshape(-1,512)':'pool=enrolled.reshape(-1,128)',
        'ROOT/f"data/lfw_gallery_n{n}.npz"':'ROOT/f"data/sface_lfw_gallery_n{n}.npz"',
        'ROOT/"results/lfw_extended"':'ROOT/"results/sface_lfw_extended"',
        '"historical_20_split_binary_ranks_exact":True':'"historical_comparison":"Different frontend; no equality to FaceNet outcomes is required"'
    }
    for old,new in replacements.items():
        assert old in source,old
        source=source.replace(old,new)
    start=source.index('    historical=list(csv.DictReader(')
    end=source.index('    summary={',start)
    source=source[:start]+source[end:]
    (ROOT/"evaluate_sface_lfw_extended.py").write_text(source)
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    audit={"base_paired_sha256":sha(first/"evaluate_float_binary.py"),"generated_paired_sha256":sha(ROOT/"evaluate_float_binary_128.py"),
        "base_extended_sha256":sha(first/"revision_v2/evaluate_lfw_extended.py"),"generated_extended_sha256":sha(ROOT/"evaluate_sface_lfw_extended.py"),
        "adaptations":"Feature dimension128 and SFace input/output paths only; same cohort sizes, seeds, means, scores, calibration and identity uncertainty. Remove equality assertion to the different FaceNet frontend."}
    (ROOT/"results/sface_evaluation_source_audit.json").write_text(json.dumps(audit,indent=2))
    print(json.dumps(audit,indent=2))

if __name__=="__main__":main()
