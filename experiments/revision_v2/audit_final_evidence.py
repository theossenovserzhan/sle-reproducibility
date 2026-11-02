"""Final evidence audit; keeps source versions and measurement families apart."""
from pathlib import Path
import hashlib,json,re,time

ROOT=Path(__file__).resolve().parent
def read(p):return json.loads((ROOT/p).read_text())
def sha(p):return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
def rows(p):return [json.loads(r) for r in (ROOT/p).read_text().splitlines()]

def main():
    build=read("results/revision_build_manifest.json")
    current=[r for r in rows("results/system_runs.jsonl") if all(r.get(k)==v for k,v in build["final_hashes"].items())]
    faults=[r for r in current if r["tag"]=="faults"]
    persisted=[r for r in rows("results/persisted_runs.jsonl") if r["source_sha256"]==sha("mpc/msle_persistent_system.mpc")]
    compact=[r for r in rows("results/compact_sort_runs.jsonl") if r["circuit_sha256"]==sha("mpc/msle_compact_sort_system.mpc")]
    runtime=read("runtime_provenance.json")
    checks={
        "final_build_not_draft":build["draft"] is False,
        "secure_batch_finished":bool(read("results/secure_batch_status.json").get("finished_utc")),
        "all_current_system_oracle_checks":bool(current) and all(r["state_ok"]==1 and r["query_ok"]==1 for r in current),
        "all_eight_faults_reject":{r["fault"] for r in faults}==set(range(1,9)) and all(r["relation_ok"]==0 for r in faults),
        "large_state_checks_128_and_256":all(any(r["n"]==n and r["diag"]==1 and r["mode"]==0 and r["fault"]==0 for r in current) for n in (128,256)),
        "persisted_lifecycle_finished":read("results/persisted_status.json")["finished"],
        "all_persisted_checks":bool(persisted) and all(r["state_ok"]==1 and r["query_ok"]==1 and r["whole_state_read_from_own_share_file"] and not r["plaintext_db_or_index_input"] for r in persisted),
        "persisted_rollback_and_reload":all(any(r["tag"]==tag for r in persisted) for tag in ("persisted_rollback","persisted_rollback_reload")),
        "compact_baseline_finished":read("results/compact_status.json")["finished"] and all(r["state_ok"]==1 and r["query_ok"]==1 for r in compact),
        "primitives_pass":read("results/primitives.json")["all_pass"],
        "retained_simulation_reproduced":read("results/retained_lifecycle/reproduction_audit.json")["all_aggregate_fields_reproduced"],
        "historical_celeba_all_20_exact":read("results/celeba_external_paired/paired_summary.json")["all_20_historical_ranks_exact"],
        "fixed_celeba_bits_exact":all(v==0 for v in read("data/celeba/extraction.json")["frozen_binary_checks"].values()),
        "runtime_source_audit":runtime["revision_matches"] and not runtime["runtime_copy_missing_reference_files"] and not runtime["runtime_copy_differing_reference_files"] and not runtime["tracked_source_changes_ignoring_crlf_and_filemode"]["stdout"],
        "no_manuscript_placeholders":not any(re.search(r"internal draft|pending|TODO|TBD",p.read_text(),re.I) for p in (ROOT/"manuscript_R1").glob("*.tex")),
    }
    audit={"created_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"all_pass":all(checks.values()),"checks":checks,
        "current_system_runs":len(current),"persisted_runs":len(persisted),"compact_runs":len(compact),"build_manifest_sha256":sha("results/revision_build_manifest.json"),
        "note":"Automated evidence consistency only; PDF visual inspection is recorded separately. Old-source measurements are retained but excluded from final means."}
    (ROOT/"results/final_evidence_audit.json").write_text(json.dumps(audit,indent=2))
    print(json.dumps(audit,indent=2))
    if not audit["all_pass"]:raise SystemExit(1)

if __name__=="__main__":main()
