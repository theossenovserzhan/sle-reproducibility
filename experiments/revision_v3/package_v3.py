"""Combine frozen R1 provenance with explicit V3 allowlists, never biometric shares."""
from pathlib import Path
import hashlib,json,zipfile

ROOT=Path(__file__).resolve().parent
def sha(data):return hashlib.sha256(data).hexdigest()

def main():
    audit=json.loads((ROOT/"results/final_evidence_audit.json").read_text())
    qa=json.loads((ROOT/"results/pdf_visual_qa.json").read_text())
    assert audit["all_pass"] and qa["all_pages_reviewed"]
    reproduction_path=ROOT/"results/archive_reproduction_audit.json"
    if reproduction_path.exists():
        reproduction=json.loads(reproduction_path.read_text());assert reproduction["all_pass"]
        for name,digest in reproduction["tested_tables_and_response_sha256"].items():
            assert sha((ROOT/"manuscript_v3"/name).read_bytes())==digest,name
        for name,digest in reproduction["tested_pdf_sha256"].items():
            assert sha((ROOT/f"output/pdf/{name}.pdf").read_bytes())==digest,name
    old=ROOT.parent/"revision_v2/output/TBIOM_R1_package.zip"
    assert sha(old.read_bytes())==audit["frozen_R1_sha256"]
    archive=ROOT/"output/TBIOM_R1_v3_package.zip";files={};base_manifest={}
    def add(path):
        path=Path(path);arc="revision_v3/"+path.relative_to(ROOT).as_posix()
        assert path.is_file();files[arc]=path
    for pattern in ("*.py","*.ps1","*.json","*.txt"):
        for path in ROOT.glob(pattern):add(path)
    allowed={".py",".mpc",".tex",".bib",".log",".json",".jsonl",".csv",".txt",".svg"}
    for folder in ("mpc","source_history","notes","logs","results","manuscript_v3"):
        for path in (ROOT/folder).rglob("*"):
            if not path.is_file():continue
            if path.suffix in allowed:add(path)
            elif folder=="manuscript_v3" and path.suffix in (".png",".jpg"):add(path)
            elif folder=="results" and path.name=="subject_outcomes.npz":add(path)
            elif folder=="results" and path.parent.name=="frontend_confirmation" and path.name.endswith("_subject_outcomes.npz"):add(path)
    # Exact image/feature/model provenance only; no feature/weight/root arrays.
    for name in ("sface_assets.json","sface_extraction.json","sface_selection.json","sface_rp512_secure_inputs.json","binary_frontend_training_selection.json","binary_frontend_model.json","projection_facenet_model.json","projection_sface_model.json","plot_installation_report.json"):
        add(ROOT/"data"/name)
    for name in ("main","supplement","response_to_reviewers"):
        path=ROOT/f"output/pdf/{name}.pdf"
        assert sha(path.read_bytes())==qa["pdfs"][name]["sha256"];add(path)
    forbidden={"Player-Data","Persistence","image_cache","selected_images","plot_libs","opencv_libs","python_libs","__pycache__",".git"}
    for arc in files:
        assert not forbidden.intersection(Path(arc).parts),arc
        assert not Path(arc).name.startswith(("Input-P","Persistence")),arc
        if arc.endswith((".npz",".npy")):assert "/results/" in arc and "subject_outcomes" in arc,arc
    archive.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(old) as frozen,zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as output:
        for info in frozen.infolist():
            if info.is_dir() or info.filename.endswith("CONTENTS_SHA256.json"):continue
            relative=info.filename.split("/",1)[1];data=frozen.read(info)
            output.writestr("TBIOM_R1_v3/"+relative,data)
            base_manifest[relative]={"bytes":len(data),"sha256":sha(data),"provenance":"frozen_R1"}
        for arc,path in sorted(files.items()):
            data=path.read_bytes();output.writestr("TBIOM_R1_v3/"+arc,data)
            base_manifest[arc]={"bytes":len(data),"sha256":sha(data),"provenance":"revision_v3"}
        output.writestr("TBIOM_R1_v3/CONTENTS_SHA256.json",json.dumps(base_manifest,indent=2,sort_keys=True))
    with zipfile.ZipFile(archive) as output:
        assert output.testzip() is None
        for arc,metadata in base_manifest.items():assert sha(output.read("TBIOM_R1_v3/"+arc))==metadata["sha256"],arc
    result={"archive":archive.name,"bytes":archive.stat().st_size,"files":len(base_manifest),"sha256":sha(archive.read_bytes()),"CRC_and_every_member_hash_verified":True,"excluded":"Biometric images/features/roots, trained transform arrays, model weights, per-party input/state shares, runtime/dependency binaries and caches. Author portraits, paper figures and deidentified correctness outcomes are included.","not_submitted":True}
    (ROOT/"output/package_manifest.json").write_text(json.dumps(result,indent=2))
    (ROOT/"output/TBIOM_R1_v3_package.sha256").write_text(result["sha256"]+"  "+archive.name+"\n")
    print(json.dumps(result,indent=2))

if __name__=="__main__":main()
