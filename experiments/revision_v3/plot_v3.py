"""Paper figure using frozen paired outcomes; no scoring, fitting or selection."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parent
PLOT_LIBS=ROOT/"data/plot_libs"
# Caller holds the common runtime lock. Dependencies stay inside this study;
# no global Python installation or user font-cache directory is modified.
if not (PLOT_LIBS/".installation_ok.json").exists():
    subprocess.run([sys.executable,"-m","pip","install","--disable-pip-version-check","--no-input","--only-binary=:all:","--upgrade","--target",str(PLOT_LIBS),"--report",str(ROOT/"data/plot_installation_report.json"),"matplotlib==3.10.7","numpy==2.3.5"],check=True,timeout=150)
    (PLOT_LIBS/".installation_ok.json").write_text(json.dumps({"matplotlib":"3.10.7","numpy":"2.3.5","target":"data/plot_libs"}))
sys.path.insert(0,str(PLOT_LIBS))
os.environ["MPLCONFIGDIR"]=str(ROOT/"tmp/matplotlib_config")
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def main():
    fn=json.loads((ROOT/"results/projection_facenet_corrected/summary.json").read_text())
    sf=json.loads((ROOT/"results/projection_sface_corrected/summary.json").read_text())
    paired=json.loads((ROOT/"results/frontend_confirmation/summary.json").read_text())
    sizes=[128,256,512,1024,2048,4096];x=np.arange(len(sizes))
    plt.rcParams.update({"font.family":"DejaVu Serif","font.size":9,"axes.spines.top":False,"axes.spines.right":False,"svg.fonttype":"none"})
    fig,axes=plt.subplots(1,2,figsize=(7.25,2.9),gridspec_kw={"width_ratios":[1.08,1]})
    methods=((fn,"original_cosine","FaceNet float","-","o"),(fn,"original_sign_512","FaceNet 512","--","s"),(sf,"original_cosine","SFace float",":","^"),(sf,"RP_centered_512_seed20261030","SFace 512 seed 1","-.","D"),(sf,"RP_centered_512_seed20261031","SFace 512 seed 2",(0,(2,2)),"x"))
    for summary,method,label,style,marker in methods:
        values={row["n_gallery"]:row["rank1"] for row in summary["closed_set"] if row["method"]==method}
        axes[0].plot(x,[100*values[n] for n in sizes],label=label,color="black",linestyle=style,marker=marker,markersize=3,linewidth=1)
    axes[0].set_title("(a) Same 128 query identities")
    axes[0].set_ylabel("Rank-1 identification (%)")
    axes[0].legend(fontsize=6.4,frameon=False,ncol=1,loc="lower left")
    for seed,offset,marker in ((20261030,-.07,"o"),(20261031,.07,"s")):
        values={row["n_gallery"]:row["rank1_delta"] for row in paired["extended_paired"] if row["method"]==f"SFace_RP_centered_512_seed{seed}"}
        mean=np.array([100*values[n]["mean"] for n in sizes]);lo=np.array([100*values[n]["ci95"][0] for n in sizes]);hi=np.array([100*values[n]["ci95"][1] for n in sizes])
        axes[1].errorbar(x+offset,mean,yerr=[mean-lo,hi-mean],color="black",marker=marker,markersize=3,linewidth=.9,capsize=2,label=f"Seed {seed}")
    axes[1].axhline(0,color=".5",linestyle=":",linewidth=.8)
    axes[1].set_title("(b) Paired identity 95% intervals")
    axes[1].set_ylabel("SFace 512 minus FaceNet 512 (pp)")
    axes[1].legend(fontsize=6.5,frameon=False,loc="upper left")
    for axis in axes:
        axis.set_xticks(x,sizes,rotation=40);axis.set_xlabel("Gallery identities");axis.grid(axis="y",alpha=.22)
    fig.tight_layout(pad=.6,w_pad=1.1)
    output=ROOT/"manuscript_v3/figures";output.mkdir(exist_ok=True)
    for suffix in ("png","svg"):fig.savefig(output/f"frontend_scale_v3.{suffix}",dpi=220,bbox_inches="tight")
    plt.close(fig)
    sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
    (ROOT/"results/plot_v3_audit.json").write_text(json.dumps({"script_sha256":sha(__file__),"source_summaries":[sha(ROOT/f"results/projection_{name}_corrected/summary.json") for name in ("facenet","sface")],"paired_summary_sha256":sha(ROOT/"results/frontend_confirmation/summary.json"),"matplotlib":matplotlib.__version__,"new_recognition_scores_computed":False,"figure_sha256":sha(output/"frontend_scale_v3.png")},indent=2))
    print("PAIRED_FRONTEND_FIGURE_GENERATED",flush=True)

if __name__=="__main__":main()
