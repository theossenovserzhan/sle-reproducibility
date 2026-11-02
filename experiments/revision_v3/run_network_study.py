"""Isolated latency sensitivity; all parties remain on the same physical host."""
from pathlib import Path
import asyncio,fcntl,json,time
import mpc_driver as core
import run_lazy_epoch as study
from network_delay import echo_calibration,run_mpc

ROOT=Path(__file__).resolve().parent
ORIGINAL_RUN=core.run
CURRENT_RTT=0
CALIBRATION=None

def delayed_run(argv,runtime,log,timeout=900):
    command=list(map(str,argv))
    if "Scripts/shamir.sh" not in command:return ORIGINAL_RUN(argv,runtime,log,timeout)
    program=command[command.index("Scripts/shamir.sh")+1]
    return asyncio.run(run_mpc(runtime,program,core.P,CURRENT_RTT,log,min(timeout,900)))

def case(runtime,method,**opts):
    data=study.case(runtime,method,**opts)
    for row in data:
        meta=json.loads((ROOT/row["raw_log"]).with_suffix(".network.json").read_text())
        row={**row,"requested_added_rtt_ms":CURRENT_RTT,"echo_calibration":CALIBRATION,"network_emulation":meta}
        with (ROOT/"results/network_runs.jsonl").open("a") as stream:stream.write(json.dumps(row)+"\n")
    return data

def main():
    global CURRENT_RTT,CALIBRATION
    state={"finished":False,"correctness_passed":False,"current":"waiting_for_frontend_confirmation","last_error":None}
    path=ROOT/"results/network_status.json"
    def save(**values):state.update(values);path.write_text(json.dumps(state,indent=2))
    save()
    try:
        while True:
            prior_path=ROOT/"results/frontend_confirmation_status.json"
            if prior_path.exists():
                try:prior=json.loads(prior_path.read_text())
                except json.JSONDecodeError:time.sleep(1);continue
                if prior.get("finished") or prior.get("last_error"):
                    pdf_path=ROOT/"results/pdf_build_status.json"
                    repair_path=ROOT/"results/calibration_repair_status.json"
                    if pdf_path.exists() and repair_path.exists():
                        try:pdf,repair=[json.loads(p.read_text()) for p in (pdf_path,repair_path)]
                        except json.JSONDecodeError:time.sleep(1);continue
                        if (pdf.get("finished") or pdf.get("last_error")) and (repair.get("finished") or repair.get("last_error")):
                            save(preceding_frontend_error=prior.get("last_error"),preceding_pdf_error=pdf.get("last_error"),preceding_calibration_error=repair.get("last_error"));break
            time.sleep(5)
        runtime=Path(json.loads((ROOT.parent/"mpc_logs/runtime.json").read_text())["runtime"])
        with (runtime/".msle_v3_driver.lock").open("w") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX);runtime=core.setup_runtime();core.run=delayed_run
            CURRENT_RTT=0;CALIBRATION=asyncio.run(echo_calibration(0))
            for method in ("full_direct","lazy_epoch"):
                save(current={"phase":"zero_delay_correctness","method":method})
                case(runtime,method,n=2,bits=64,mode=0,diag=1,tag="network_zero_correctness")
            save(correctness_passed=True)
            # A full512-bit query and a smaller64-bit rekey isolate latency
            # sensitivity without an unbounded WAN-duration experiment.
            # Report these sizes separately; never extrapolate rekey latency.
            for rtt in (0,1,20,50):
                CURRENT_RTT=rtt;CALIBRATION=asyncio.run(echo_calibration(rtt))
                for n,bits,mode in ((2,64,1),(8,512,2)):
                    for repeat in range(-1,3):
                        order=("full_direct","lazy_epoch") if repeat%2==0 else ("lazy_epoch","full_direct")
                        for method in order:
                            save(current={"n":n,"bits":bits,"mode":mode,"rtt_ms":rtt,"method":method,"repeat":repeat})
                            opts={"n":n,"bits":bits,"mode":mode,"diag":0,"tag":"network_emulation"}
                            if repeat<0:case(runtime,method,repeats=0,warmups=1,**opts)
                            else:case(runtime,method,repeats=1,repeat_offset=repeat,**opts)
        save(finished=True,current=None);print("NETWORK_STUDY_COMPLETE",flush=True)
    except BaseException as error:
        save(last_error=repr(error));raise

if __name__=="__main__":main()
