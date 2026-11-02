from pathlib import Path
import hashlib,json,math

ROOT=Path(__file__).resolve().parent
expected=json.loads((ROOT/"legacy_reproduce/expected_msle_summary.json").read_text())
actual=json.loads((ROOT/"results/retained_lifecycle/msle_summary.json").read_text())
def equal(a,b):
    if isinstance(a,list):return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    if isinstance(a,(int,float)) and not isinstance(a,bool):return math.isclose(a,b,rel_tol=0,abs_tol=1e-12)
    return a==b
differences={key:{"expected":value,"actual":actual.get(key)} for key,value in expected.items() if not equal(value,actual.get(key))}
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
audit={"all_aggregate_fields_reproduced":not differences,"absolute_float_tolerance":1e-12,"differences":differences,
    "original_source_sha256":sha(ROOT/"source_history/validate_masked_sle_original.py"),
    "bounded_source_sha256":sha(ROOT/"legacy_reproduce/validate_masked_sle.py"),
    "expected_summary_sha256":sha(ROOT/"legacy_reproduce/expected_msle_summary.json"),
    "actual_summary_sha256":sha(ROOT/"results/retained_lifecycle/msle_summary.json"),
    "change":"equivalent integer-population sampling, no materialized 16-GiB range; no cryptographic parameter change"}
(ROOT/"results/retained_lifecycle/reproduction_audit.json").write_text(json.dumps(audit,indent=2))
print(json.dumps({"all_aggregate_fields_reproduced":not differences,"differences":differences},indent=2))
if differences:raise SystemExit(1)
