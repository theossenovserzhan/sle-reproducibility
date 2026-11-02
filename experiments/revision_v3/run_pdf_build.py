"""Keep document compilation/rendering outside all experimental timing windows."""
from pathlib import Path
import fcntl,json,subprocess,time

ROOT=Path(__file__).resolve().parent

def main():
    state={"finished":False,"current":"waiting_for_frontend_confirmation","last_error":None,"working_draft_only":True}
    path=ROOT/"results/pdf_build_status.json"
    def save(**values):state.update(values);path.write_text(json.dumps(state,indent=2))
    save()
    try:
        while True:
            prior_path=ROOT/"results/frontend_confirmation_status.json"
            if prior_path.exists():
                try:prior=json.loads(prior_path.read_text())
                except json.JSONDecodeError:time.sleep(1);continue
                if prior.get("last_error"):raise RuntimeError("Repair frontend confirmation before PDF build: "+prior["last_error"])
                if prior.get("finished"):break
            time.sleep(5)
        runtime=Path(json.loads((ROOT.parent/"mpc_logs/runtime.json").read_text())["runtime"])
        with (runtime/".msle_v3_driver.lock").open("w") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);save(current="compile_and_render_drafts")
            pwsh="/mnt/c/Users/ossen/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe"
            script="C:\\Users\\ossen\\OneDrive\\Documents\\SmartCity\\TBIOM_revision_experiments_2026-10-29\\revision_v3\\compile_v3_draft.ps1"
            log=ROOT/"logs/pdf_draft_build.log"
            with log.open("w") as stream:
                subprocess.run([pwsh,"-NoProfile","-File",script],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=600,check=True)
        save(finished=True,current=None);print("DRAFT_PDF_BUILD_COMPLETE; inspect all rendered pages",flush=True)
    except BaseException as error:
        save(last_error=repr(error));raise

if __name__=="__main__":main()
