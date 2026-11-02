"""Build a review archive using an explicit allowlist, excluding biometric data."""
from pathlib import Path
import hashlib,json,zipfile

ROOT=Path(__file__).resolve().parent
FIRST=ROOT.parent

def main():
    audit=json.loads((ROOT/"results/final_evidence_audit.json").read_text())
    qa=json.loads((ROOT/"results/pdf_visual_qa.json").read_text())
    if not audit["all_pass"] or not qa["all_pages_reviewed"]:raise SystemExit("Final evidence and PDF checks must pass")
    files={}
    def add(path,arc=None):
        path=Path(path)
        if not path.is_file():raise FileNotFoundError(path)
        files[arc or path.relative_to(FIRST).as_posix()]=path
    for path in ROOT.glob("*.py"):
        if path.name not in {"pause_for_user.py","probe_celeba_access.py","probe_celeba_image.py"}:add(path)
    for name in ("README_REPRODUCE.txt","REPORT_RU.txt","requirements_biometric.txt","reviewer_evidence_matrix.csv","parameters.json","backend_config.json","compact_baseline_config.json","lfw_extended_protocol.json","environment_biometric.json","runtime_provenance.json","runtime_source_hashes.json"):
        add(ROOT/name)
    for folder in ("mpc","legacy_reproduce","source_history","logs","manuscript_R1","results"):
        for path in (ROOT/folder).rglob("*"):
            if not path.is_file():continue
            if path.suffix.lower() in {".py",".mpc",".tex",".bib",".log",".json",".jsonl",".csv",".svg",".png",".jpg",".txt"}:add(path)
            elif path==ROOT/"results/lfw_extended/subject_outcomes.npz":add(path)
    for name in ("main","supplement","response_to_reviewers"):
        pdf=ROOT/f"output/pdf/{name}.pdf"
        if hashlib.sha256(pdf.read_bytes()).hexdigest()!=qa["pdfs"][name]["sha256"]:raise SystemExit("PDF changed after visual review")
        add(pdf)
    for rel in ("lfw_extended_selection.json","lfw_extended_extraction.json","celeba/selection.json","celeba/image_provenance.json","celeba/extraction.json","celeba_external/selection.json","celeba_external/image_provenance.json","celeba_external/extraction.json"):
        add(ROOT/"data"/rel)
    for name in ("run_experiments.py","evaluate_float_binary.py","extract_float_features.py","test_experiments.py","protocol.json","hardware.json","source_checksums.json"):
        add(FIRST/name)
    add(FIRST/"inputs/historical_randomized_splits.csv")
    for name in ("lfw_input_audit.json","lfw_extraction.json"):add(FIRST/"float_features"/name)
    for name in ("build.log","build_previous.log"):add(FIRST/"mpc_logs"/name)
    for path in (FIRST/"results/paired_lfw").glob("*"):
        if path.is_file() and path.suffix in {".csv",".json"}:add(path)
    forbidden=("Player-Data","Persistence","model_cache","image_cache","python_libs",".git","__pycache__")
    for arc in files:
        if any(part in forbidden for part in Path(arc).parts):raise AssertionError("Excluded path: "+arc)
        if arc.endswith((".npz",".npy")) and arc!="revision_v2/results/lfw_extended/subject_outcomes.npz":raise AssertionError("Unexpected data array: "+arc)
    manifest={arc:{"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()} for arc,p in sorted(files.items())}
    archive=ROOT/"output/TBIOM_R1_package.zip"
    archive.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for arc,path in sorted(files.items()):z.write(path,"TBIOM_R1/"+arc)
        z.writestr("TBIOM_R1/CONTENTS_SHA256.json",json.dumps(manifest,indent=2,sort_keys=True))
    with zipfile.ZipFile(archive) as z:
        bad=z.testzip()
        if bad:raise AssertionError("ZIP CRC failure: "+bad)
        for arc,row in manifest.items():
            if hashlib.sha256(z.read("TBIOM_R1/"+arc)).hexdigest()!=row["sha256"]:raise AssertionError("ZIP hash mismatch: "+arc)
    result={"archive":archive.name,"file_count":len(manifest),"bytes":archive.stat().st_size,"sha256":hashlib.sha256(archive.read_bytes()).hexdigest(),"zip_crc_pass":True,"all_member_hashes_verified":True,
        "excluded":"Face images, biometric embeddings/roots, model weights, runtime binaries, per-party inputs/shares and TLS secrets. Author portraits and deidentified correctness outcomes are included."}
    (ROOT/"output/package_manifest.json").write_text(json.dumps(result,indent=2))
    (ROOT/"output/TBIOM_R1_package.sha256").write_text(result["sha256"]+"  "+archive.name+"\n")
    print(json.dumps(result,indent=2))

if __name__=="__main__":main()
