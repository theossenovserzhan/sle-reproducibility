"""After measurements, regenerate scientific figure and the latest three PDFs."""
from pathlib import Path
import fcntl,json,subprocess,time

ROOT=Path(__file__).resolve().parent
WINROOT="C:\\Users\\ossen\\OneDrive\\Documents\\SmartCity\\TBIOM_revision_experiments_2026-10-29\\revision_v3"

def main():
    state={"finished":False,"current":"waiting_for_network_series","last_error":None,"visual_review_pending":True}
    path=ROOT/"results/pdf_final_build_status.json"
    def save(**values):state.update(values);path.write_text(json.dumps(state,indent=2))
    save()
    try:
        while True:
            p=ROOT/"results/network_status.json"
            if p.exists():
                try:network=json.loads(p.read_text())
                except json.JSONDecodeError:time.sleep(1);continue
                if network.get("finished") or network.get("last_error"):
                    save(network_completed=bool(network.get("finished")),network_error=network.get("last_error"));break
            time.sleep(5)
        for name in ("private_client","calibration_repair","frontend_confirmation"):
            prior=json.loads((ROOT/f"results/{name}_status.json").read_text())
            assert prior.get("finished") and not prior.get("last_error"),(name,prior)
        runtime=Path(json.loads((ROOT.parent/"mpc_logs/runtime.json").read_text())["runtime"])
        with (runtime/".msle_v3_driver.lock").open("w") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);save(current="figure_then_final_pdf_build")
            python="/mnt/c/Users/ossen/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
            pwsh="/mnt/c/Users/ossen/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/powershell/pwsh.exe"
            with (ROOT/"logs/pdf_final_build.log").open("w") as stream:
                subprocess.run([python,WINROOT+"\\plot_v3.py"],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=180,check=True)
                subprocess.run([pwsh,"-NoProfile","-File",WINROOT+"\\compile_v3_draft.ps1","-RenderSubfolder","final_qa"],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=600,check=True)
        save(finished=True,current=None);print("FINAL_PDFS_RENDERED; all-page visual and evidence audits still required",flush=True)
    except BaseException as error:
        save(last_error=repr(error));raise

if __name__=="__main__":main()
