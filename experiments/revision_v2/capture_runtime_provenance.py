"""Record the actual source/build used for the local MPC experiments."""
from pathlib import Path
import argparse,hashlib,json,platform,subprocess,sys,time

ROOT=Path(__file__).resolve().parent
EXPECTED="9d809599ea6ce627216a389ca7d984fbb75d0cb9"

def command(argv,cwd=None):
    run=subprocess.run(argv,cwd=cwd,capture_output=True,text=True)
    return {"argv":argv,"returncode":run.returncode,"stdout":run.stdout.strip(),"stderr":run.stderr.strip()}

def portable_bytes(value):
    # Git for Windows checked text out as CRLF; shell scripts were normalized
    # to LF before the Linux build. Preserve binary bytes exactly.
    return value.replace(b"\r\n",b"\n") if b"\0" not in value else value

def main(source):
    runtime=Path(json.loads((ROOT.parent/"mpc_logs/runtime.json").read_text())["runtime"])
    source=source.resolve() if source else runtime
    git=["git","-c","safe.directory="+str(source),"-c","core.filemode=false"]
    revision=command(git+["rev-parse","HEAD"],source)
    files=command(git+["ls-files","--stage"],source)
    if files["returncode"]:raise RuntimeError("A Git checkout is needed to capture the complete source manifest")
    staged=[row.split("\t",1) for row in files["stdout"].splitlines()]
    submodules=[p for metadata,p in staged if metadata.startswith("160000 ")]
    tracked=[p for metadata,p in staged if not metadata.startswith("160000 ")]
    hashes={p:{"sha256":hashlib.sha256((runtime/p).read_bytes()).hexdigest(),"sha256_lf_text":hashlib.sha256(portable_bytes((runtime/p).read_bytes())).hexdigest()} for p in tracked if (runtime/p).is_file()}
    missing=[p for p in tracked if not (runtime/p).is_file()]
    different=[p for p,h in hashes.items() if hashlib.sha256(portable_bytes((source/p).read_bytes())).hexdigest()!=h["sha256_lf_text"]]
    changes=command(git+["diff","--no-ext-diff","--ignore-cr-at-eol","HEAD"],source)
    manifest=ROOT/"runtime_source_hashes.json"
    manifest.write_text(json.dumps(hashes,indent=2,sort_keys=True))
    actual=revision["stdout"] if revision["returncode"]==0 else None
    record={"captured_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"source_revision":actual,"expected_revision":EXPECTED,
        "revision_matches":actual==EXPECTED,"tracked_source_changes_ignoring_crlf_and_filemode":changes,
        "runtime_copy_missing_reference_files":missing,"runtime_copy_differing_reference_files":different,
        "gitlinks_not_regular_files":submodules,"normalization":"CRLF to LF for text without NUL; file modes ignored. Raw and normalized hashes both retained.",
        "tracked_file_count":len(hashes),"source_hash_manifest_sha256":hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "compiler":command(["g++","--version"]),"kernel":command(["uname","-a"]),"os_release":Path("/etc/os-release").read_text(),
        "python":sys.version,"numpy":__import__("numpy").__version__,"platform":platform.platform(),
        "runtime_binary_sha256":hashlib.sha256((runtime/"shamir-party.x").read_bytes()).hexdigest(),
        "runtime_binary_libraries":command(["ldd",str(runtime/"shamir-party.x")]),
        "build_configuration":{p:(runtime/p).read_text() for p in ("CONFIG.mine",) if (runtime/p).is_file()},
        "network":"Five local party processes over loopback; no injected delay or bandwidth cap",
        "note":"The source manifest records tracked files actually present. Local generated circuits, TLS keys, inputs and share files are excluded. Binary hash is provenance, not a portable-build requirement."}
    (ROOT/"runtime_provenance.json").write_text(json.dumps(record,indent=2))
    print(json.dumps({k:record[k] for k in ("source_revision","revision_matches","tracked_file_count","runtime_copy_missing_reference_files","runtime_copy_differing_reference_files","tracked_source_changes_ignoring_crlf_and_filemode","build_configuration")},indent=2))
    if actual!=EXPECTED or missing or different or changes["returncode"] or changes["stdout"]:raise SystemExit("Runtime/reference source audit failed")

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--source",type=Path);args=parser.parse_args();main(args.source)
