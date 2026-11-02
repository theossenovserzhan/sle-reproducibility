"""Stop only one named study driver and its own descendant process tree."""
from pathlib import Path
import argparse,os,signal

ROOT=Path(__file__).resolve().parent
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("name",choices=["run_compact_direct.py","run_position_compact.py","run_joint_ablation.py","run_scale_batch.py","run_lazy_epoch.py","run_binary_frontend.py","run_aes_baseline.py","run_sface.py","finish_sface.py","run_projection_codes.py","run_poly_query.py","run_vector_query.py","run_lazy_persistence.py","run_shared_query.py","run_private_client.py","repair_frontend_thresholds.py","run_frontend_confirmation.py","run_network_study.py","run_pdf_build.py","finalize_v3_draft.py","run_virtual_scale.py"]);a=p.parse_args()
    procs={}
    for folder in Path("/proc").iterdir():
        if not folder.name.isdigit():continue
        try:
            argv=(folder/"cmdline").read_bytes().split(b"\0")
            argv=[x.decode(errors="replace") for x in argv if x]
            status=(folder/"status").read_text()
            parent=int(next(x.split()[1] for x in status.splitlines() if x.startswith("PPid:")))
            procs[int(folder.name)]=(parent,argv,Path(os.readlink(folder/"cwd")).resolve())
        except (OSError,StopIteration,ValueError):pass
    roots=[pid for pid,(_,argv,cwd) in procs.items() if cwd==ROOT and any(Path(x).name==a.name for x in argv[1:]) and pid!=os.getpid() and "stop_v3_driver.py" not in " ".join(argv)]
    victims=set(roots)
    while True:
        more={pid for pid,(parent,_,_) in procs.items() if parent in victims}
        if more<=victims:break
        victims|=more
    for pid in sorted(victims-set(roots),reverse=True)+roots:
        try:os.kill(pid,signal.SIGTERM)
        except ProcessLookupError:pass
    print({"driver":a.name,"roots":roots,"stopped_descendants":sorted(victims-set(roots))})



