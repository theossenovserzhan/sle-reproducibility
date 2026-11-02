"""Scientific static figure from the frozen paired identity-level outcomes."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parent
data=json.loads((ROOT/"results/lfw_extended/summary.json").read_text())["closed_set"]
x=np.asarray([r["n_gallery"] for r in data])
float_r1=np.asarray([r["float_rank1"] for r in data])*100
binary_r1=np.asarray([r["binary_rank1"] for r in data])*100
delta=np.asarray([r["binary_minus_float_rank1"]["mean"] for r in data])*100
ci=np.asarray([r["binary_minus_float_rank1"]["ci95"] for r in data])*100
plt.rcParams.update({"font.family":"DejaVu Serif","font.size":8,"axes.labelsize":8,"legend.fontsize":7,"axes.spines.top":False,"axes.spines.right":False})
fig,axes=plt.subplots(1,2,figsize=(7.05,2.35),layout="constrained")
axes[0].plot(x,float_r1,"o-",color="black",label="Float cosine",markersize=3,linewidth=1)
axes[0].plot(x,binary_r1,"s--",color="black",label="Binary Hamming",markersize=3,linewidth=1)
axes[0].set_ylabel("Rank-1 identification (%)")
axes[0].legend(frameon=False,loc="lower left")
axes[0].set_title("(a) Same 128 query identities",fontsize=8)
axes[1].errorbar(x,delta,yerr=np.stack([delta-ci[:,0],ci[:,1]-delta]),fmt="o-",color="black",capsize=3,markersize=3,linewidth=1)
axes[1].axhline(0,color="0.5",linewidth=.6,linestyle=":")
axes[1].set_ylabel("Binary minus float Rank-1 (pp)")
axes[1].set_title("(b) Identity-bootstrap 95% intervals",fontsize=8)
for axis in axes:
    axis.set_xscale("log",base=2)
    axis.set_xticks(x,[str(n) for n in x],rotation=30)
    axis.set_xlabel("Gallery identities")
    axis.grid(axis="y",color=".85",linewidth=.5)
folder=ROOT/"manuscript_R1/figures"
folder.mkdir(exist_ok=True)
fig.savefig(folder/"lfw_paired_scale.png",dpi=450)
plt.close(fig)
print("Saved frozen paired-scale figure")
