"""Portable registration of a separately built frozen MP-SPDZ checkout."""
from pathlib import Path
import argparse,hashlib,json,subprocess

ROOT=Path(__file__).resolve().parent
REVISION="9d809599ea6ce627216a389ca7d984fbb75d0cb9"
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--runtime",type=Path,required=True);args=parser.parse_args()
    runtime=args.runtime.resolve()
    required=["shamir-party.x","compile.py","Compiler/compilerLib.py","Scripts/shamir.sh"]
    if any(not (runtime/p).is_file() for p in required):raise SystemExit("Build MP-SPDZ shamir-party.x and retain compiler/scripts first")
    git=subprocess.run(["git","-C",str(runtime),"rev-parse","HEAD"],capture_output=True,text=True)
    revision=git.stdout.strip() if git.returncode==0 else None
    if revision and revision!=REVISION:raise SystemExit("Unexpected MP-SPDZ revision: "+revision)
    expected_hashes=json.loads((ROOT/"runtime_source_hashes.json").read_text())
    def portable_digest(path):
        value=path.read_bytes()
        if b"\0" not in value:value=value.replace(b"\r\n",b"\n")
        return hashlib.sha256(value).hexdigest()
    mismatches=[p for p,want in expected_hashes.items() if not (runtime/p).is_file() or portable_digest(runtime/p)!=want["sha256_lf_text"]]
    if mismatches:raise SystemExit("Source differs from measured checkout: "+", ".join(mismatches[:10]))
    provenance={"runtime":str(runtime),"expected_source_revision":REVISION,"verified_git_revision":revision,
        "revision_verified":revision==REVISION,"tracked_source_files_match_recorded_manifest":True,"status":"registered separate build",
        "source_file_sha256":{p:hashlib.sha256((runtime/p).read_bytes()).hexdigest() for p in required},
        "note":"All supplied source-manifest hashes match; binary hash is local-build provenance only. Create five-party SSL material using Scripts/setup-ssl.sh 5."}
    output=ROOT.parent/"mpc_logs/runtime.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(provenance,indent=2))
    print("Registered runtime",runtime,"git revision verified",provenance["revision_verified"])
