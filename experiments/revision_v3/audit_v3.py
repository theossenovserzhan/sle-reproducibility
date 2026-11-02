"""Require matching completed evidence and latest all-page QA before packaging."""
from pathlib import Path
import csv,hashlib,json,re
from pypdf import PdfReader
from summarize_current import rows

ROOT=Path(__file__).resolve().parent
FROZEN="eb0b7411fe238e3dd7c1728b3311d23f8cb78e7f6b7e68a0f2f52796185a587c"
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(name):return json.loads((ROOT/name).read_text(encoding="utf-8-sig"))

def main():
    checks={}
    def check(name,condition):
        checks[name]=bool(condition)
        if not condition:raise AssertionError(name)
    check("frozen_R1_unchanged",sha(ROOT.parent/"revision_v2/output/TBIOM_R1_package.zip")==FROZEN)
    for name in ("joint_ablation","position_compact","lazy_epoch","aes_baseline","poly_query","vector_query","lazy_persistence","shared_query","virtual_scale","private_client","calibration_repair","frontend_confirmation","network"):
        data=read(f"results/{name}_status.json")
        check(name+"_finished",data.get("finished") and not data.get("last_error"))
        if "correctness_passed" in data:check(name+"_correctness",data["correctness_passed"])
    evidence=read("results/current_results.json")
    for name,count,repeats in (("persisted_rekey",2,5),("larger_real_gallery",8,3),("private_output_full_query",3,5),("network_delay",16,3)):
        groups=evidence["comparisons"][name]
        check(name+"_all_cells",len(groups)==count and all(g["repetitions"]==repeats and len(g["circuit_hashes"])==1 for g in groups))
    check("three_secure_AES_KATs",read("results/aes_baseline_summary.json")["secure_AES_vectors_passed"]==3)
    for name in ("binary_frontend","projection_facenet","projection_sface"):
        summary=read(f"results/{name}_corrected/summary.json");audit=summary["strict_calibration_correction"]
        for key in ("closed_set_all_flags_unchanged","original_float_and_sign_open_set_all_flags_reproduced_exactly","all_calibration_accept_counts_within_allowed"):check(name+"_"+key,audit[key])
        with (ROOT/f"results/{name}_corrected/open_set_splits.csv").open() as stream:
            data=list(csv.DictReader(stream))
        check(name+"_every_calibration_count",all(int(r["calibration_actual_accepts"])<=int(r["calibration_allowed_accepts"]) for r in data))
    check("extended_frontend_pairing",read("results/frontend_identity_pairing_audit.json")["all5557_extended_identity_and_image_positions_identical"])
    client_rows=rows("private_client_runs.jsonl")+rows("private_fused_runs.jsonl")
    public_fields=re.compile(r" (?:identity|accepted|probe|output_pad|client_output_pad)=")
    for row in client_rows:
        check("private_log_"+str(row["raw_log"]),not public_fields.search((ROOT/row["raw_log"]).read_text()))
        if not row["diag"] and row["mode"]!=1:check("private_production_output_"+row["raw_log"],row["client_private_result"] and row["production_output_privacy_claim"])
    for seed in (20261030,20261031):
        for n in (8,128):
            selected=[r for r in client_rows if r["n"]==n and r["tag"]==f"sface_rp512_seed{seed}_state_correctness"]
            check(f"secure_frontend_{seed}_{n}",len(selected)==1 and selected[0]["state_ok"]==selected[0]["query_ok"]==1)
    qa=read("results/pdf_visual_qa.json")
    check("all_latest_pages_reviewed",qa["all_pages_reviewed"])
    pdfs={}
    for name in ("main","supplement","response_to_reviewers"):
        path=ROOT/f"output/pdf/{name}.pdf";reader=PdfReader(path)
        digest=sha(path);pages=len(reader.pages)
        check(name+"_latest_QA_hash",qa["pdfs"][name]["sha256"]==digest)
        check(name+"_all_page_indices",qa["pdfs"][name]["visually_reviewed_pages"]==list(range(1,pages+1)))
        text="\n".join(page.extract_text() or "" for page in reader.pages)
        check(name+"_no_placeholders",not re.search(r"\[\?\]|\?\?|working draft awaits|pending in this working draft",text,re.I))
        pdfs[name]={"pages":pages,"sha256":digest}
    check("regular_main_within10pages",pdfs["main"]["pages"]<=10)
    sources={p.stem:sha(p) for p in (ROOT/"mpc").glob("*.mpc")}
    result={"all_pass":True,"checks":checks,"pdfs":pdfs,"source_hashes":sources,"frozen_R1_sha256":FROZEN,"scope":"Completed prototype/revision evidence under stated assumptions; no publication acceptance or broad novelty guarantee."}
    (ROOT/"results/final_evidence_audit.json").write_text(json.dumps(result,indent=2))
    status=read("manuscript_v3/DRAFT_STATUS.json")
    status.update(working_draft_only=False,revision_artifact_ready_for_author_review=True,pending=[],not_submitted=True,evidence_audit_sha256=sha(ROOT/"results/final_evidence_audit.json"))
    (ROOT/"manuscript_v3/DRAFT_STATUS.json").write_text(json.dumps(status,indent=2))
    print(json.dumps({"all_pass":True,"checks":len(checks),"pdfs":pdfs},indent=2))

if __name__=="__main__":main()
