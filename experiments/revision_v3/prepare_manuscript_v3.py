"""Create a separate working manuscript; never overwrite the frozen R1 source."""
from pathlib import Path
import hashlib,json,shutil

ROOT=Path(__file__).resolve().parent

def replace_once(text,old,new):
    assert text.count(old)==1,old[:120]
    return text.replace(old,new,1)

def main():
    source=ROOT.parent/"revision_v2/manuscript_R1";target=ROOT/"manuscript_v3"
    if target.exists():raise RuntimeError("Working manuscript already exists; edit it explicitly instead of recreating")
    shutil.copytree(source,target)
    text=(source/"main.tex").read_text()
    start=text.index("\\begin{abstract}");end=text.index("\\end{abstract}",start)+len("\\end{abstract}")
    text=text[:start]+r'''\begin{abstract}
Renewing a protected biometric template also requires preserving its association with a private index. Masked Synchronized Locator Evolution couples binary-template masking with a verified transaction over protected templates, references and epoch secrets. We separate inherited locator consistency from the added old/new template-binding invariant and test why both checks are needed. Hamming scores are exact over the same candidates; candidate completeness is handled by a strict certificate and exhaustive fallback. A virtual-locator representation keeps secret logical handles stable while renewing their shares and the epoch-dependent template protection, reducing unnecessary permutation evaluations on padded index copies. In five-party local MPC, complete re-keying at 512 records decreases from 140.2 to 67.6 seconds and global communication from 9.78 to 2.58 GB; query cost does not share this improvement. Real persisted-share experiments, a conventional AES-CTR construction and shared-root controls expose the costs and limits of the lifecycle contract. Paired utility evaluation retains 128 query identities across nested LFW galleries up to 4096. A second frontend with two fixed public 512-bit projections improves mean Rank-1 from 93.67\% to 97.09\% at unchanged code width; model, alignment and coding change together. The contribution is a condition-scoped lifecycle construction and reproducible evaluation, not a new cipher, general post-compromise guarantee or sublinear encrypted-search algorithm.
\end{abstract}'''+text[end:]
    old="The paper makes four contributions precise:"
    start=text.index(old);end=text.index("\n\n\\section{Related Work",start)
    text=text[:start]+r'''The paper contributes (i) an explicit template-binding and index-relation invariant with necessity witnesses; (ii) materialized and virtual-locator implementations under stated hidden-metadata assumptions; (iii) complete private-query and persisted-state measurements against shared roots, oblivious sort/merge and a conventional cipher; and (iv) paired biometric, retrieval and calibration evidence for two frontends. The fixed-scan backend does not provide sublinear query time.'''+text[end:]
    anchor="MPC, Shamir sharing, proactive refresh, shuffles, ORAM and private joins supply the required components"
    start=text.index(anchor)
    text=text[:start]+r'''Updatable tokenization already preserves references across key changes~\cite{cachin2017tokenization}; MUSES delegates private keyword-index re-encryption to distributed servers~\cite{le2024muses}. Protected biometric indexing~\cite{drozdowski2021fusion} and packed preselection~\cite{xin2026pfip} also precede our implementation. Pura supplies threshold-encrypted matching~\cite{xu2025pura}, CryptoFace additionally encrypts feature extraction~\cite{ao2025cryptoface}, and BioZKFHE verifies outsourced similarity against malicious compute~\cite{xin2026biozkfhe}. Our passive consistency checks do not supply that public-proof guarantee. These interfaces motivate a precise lifecycle comparison rather than a first-private-recognition claim.

'''+text[start:]
    text=replace_once(text,r"\caption{Internal SLE predecessor and the evaluated extension.}",r"\caption{Internal SLE and the materialized masked reference. The virtual representation is specified separately.}")
    anchor="Subsequent transitions and queries load each party's own share file; plaintext database, index and old keys are not resupplied to a computing party."
    text=replace_once(text,anchor,anchor+r'''

For an external query client, each probe bit and the threshold are independently degree-two shared; each server receives only one evaluation. To return the result only to the client, it also shares a fresh uniform $R\in\mathbb F_p$. The circuit opens $y+R$, where $y$ is the identity or $-1$, and the client subtracts $R$. Acceptance is not separately opened. This standard additive pad hides the outcome from the computing parties under passive MPC and private channels. The client is honest and supplies valid bits; diagnostic runs with trusted correctness-oracle inputs are excluded from this privacy statement.''')
    anchor=r"\subsection{Verified Epoch Transition}"
    text=replace_once(text,anchor,r'''\subsection{Complete-Matcher Controls}
The reference computes all Hamming distances on a fixed schedule. A strong complete-matcher control can therefore form candidate flags directly from the already computed mismatch bits $z_{i,j}=b_{i,j}\oplus q_j$:
\[
a_i=1-\prod_g\left(1-\prod_{j\in g}(1-z_{i,j})\right).
\]
For a valid index relation, $a_i$ equals membership in the union of selected buckets. This fused construction and a full exact scan are mandatory controls for an optimized index lookup. Our polynomial support-lookup variant is useful as a separate index operator, but its acceleration over repeated field equality does not establish acceleration of complete identification.

\subsection{Verified Epoch Transition}''')
    anchor=r"\section{Security Boundaries}"
    text=replace_once(text,anchor,r'''\subsection{Virtual-Locator Representation}
An alternative stores distinct secret handles $h_i$ and defines semantic locators by $\ell_e(h)=\Pi_{k_e}(h)$. Valid index slots store independent shares of the referenced handle, while $\mathbf c_i^e=\mathbf b_i\oplus G(K_e,\ell_e(h_i))$. Rekeying computes
\[
\mathbf c_i'=\mathbf c_i\oplus G(K_e,\ell_e(h_i))\oplus G(K_{e+1},\ell_{e+1}(h_i)).
\]
The logical handles remain stable. Since $\Pi$ is injective, the root/index tuple relation checked over handles is equivalent to the relation over their semantic locators. Template binding, proposed-root/index verification, joint state selection, complete-row shuffle, all-field share refresh and persistence writes remain.

Materialized evolution evaluates a permutation on $N+M$ references; the virtual masked implementation derives $2N$ old/new semantic locators. Standalone queries add $N$ locator derivations. This is a different representation and update family, not a physical rewrite of every logical index value. Hidden handles, labels, tie tags and bucket contents are essential. A stale-handle-value injection is a no-op and is excluded from the virtual fault-rejection count.

\section{Security Boundaries}''')
    anchor="Thus the field/key width is approximately 128 bits"
    text=replace_once(text,anchor,r"A separate bad event is collision among independently sampled epoch/word keys; for $E$ epochs and nine keys per epoch it is bounded by $\binom{9E}{2}/p$. " + anchor)
    anchor=r"\subsection{Secure System and Baselines}"
    text=replace_once(text,anchor,r'''We additionally use the fixed OpenCV SFace/YuNet frontend~\cite{opencv2026zoo}. Public Gaussian hyperplane signs~\cite{charikar2002similarity} produce 512, 1024 or 2048 bits, with both seeds retained. A centering mean uses only 565 unused LFW identities, separate from evaluation, calibration, unknowns and used distractors. This is established preprocessing. Changing frontend requires source features or re-enrollment; epoch renewal keeps its selected binary root fixed. No images are excluded; deterministic detection fallback and pretrained-model checksums are reported in the supplement. Cross-dataset and pretrained-training identity overlap are unaudited.

\subsection{Secure System and Baselines}''')
    anchor=r"\input{generated_results.tex}"
    text=replace_once(text,anchor,r'''The following retained reference results are from the frozen revision batch; new paired comparisons and representation changes are reported separately below.
\input{generated_results.tex}
\input{generated_v3_results.tex}''')
    text=replace_once(text,"The prototype uses passive MPC, one encoder and custom public-dataset protocols, with five colocated processes.","The prototype uses passive MPC, two frontends and custom public-dataset protocols, with five colocated processes. Public projection hashes do not add cryptographic irreversibility; model, alignment and code-width changes must be evaluated separately from protection.")
    (target/"main.tex").write_text(text)
    supplement=(target/"supplement.tex").read_text()
    marker=r"\bibliographystyle{IEEEtran}"
    assert marker in supplement
    supplement=supplement.replace(marker,r"\input{generated_v3_supplement.tex}"+"\n"+marker,1)
    (target/"supplement.tex").write_text(supplement)
    (target/"generated_v3_results.tex").write_text("% Generated by build_v3_tables.py; the working draft is not finalized.\n")
    (target/"generated_v3_supplement.tex").write_text("% Await complete corrected result audit before final integration.\n")
    bibliography=r'''
@inproceedings{cachin2017tokenization,
 author={Christian Cachin and Jan Camenisch and Eduarda Freire-St{\"o}gbuchner and Anja Lehmann},
 title={Updatable Tokenization: Formal Definitions and Provably Secure Constructions},
 booktitle={Financial Cryptography and Data Security},year={2017},pages={59--75},doi={10.1007/978-3-319-70972-7_4}}
@inproceedings{le2024muses,
 author={Tung Le and Rouzbeh Behnia and Jorge Guajardo and Thang Hoang},
 title={{MUSES}: Efficient Multi-User Searchable Encrypted Database},
 booktitle={33rd USENIX Security Symposium},year={2024},url={https://www.usenix.org/system/files/usenixsecurity24-le.pdf}}
@article{drozdowski2021fusion,
 author={Pawel Drozdowski and Fabian Stockhardt and Christian Rathgeb and Daile Osorio-Roig and Christoph Busch},
 title={Feature Fusion Methods for Indexing and Retrieval of Biometric Data: Application to Face Recognition with Privacy Protection},
 journal={IEEE Access},volume={9},pages={139361--139378},year={2021},doi={10.1109/ACCESS.2021.3118830}}
@inproceedings{xin2026pfip,
 author={Rundong Xin and Taotao Wang and Jin Wang and Chonghe Zhao and Jing Wang},
 title={Privacy-Preserving Preselection for Face Identification Based on Packing},
 booktitle={Security and Privacy in Communication Networks},series={LNICST},volume={689},year={2026},pages={410--426},doi={10.1007/978-3-032-23453-7_22}}
@misc{xu2025pura,
 author={Guotao Xu and Bowen Zhao and Yang Xiao and Yantao Zhong and Liang Zhai and Qingqi Pei},
 title={{Pura}: An Efficient Privacy-Preserving Solution for Face Recognition},
 year={2025},howpublished={arXiv:2505.15476},url={https://arxiv.org/abs/2505.15476}}
@inproceedings{ao2025cryptoface,
 author={Wei Ao and Vishnu Naresh Boddeti},title={{CryptoFace}: End-to-End Encrypted Face Recognition},
 booktitle={Proc. IEEE/CVF Conf. Computer Vision and Pattern Recognition},year={2025},pages={19197--19206},url={https://openaccess.thecvf.com/content/CVPR2025/html/Ao_CryptoFace_End-to-End_Encrypted_Face_Recognition_CVPR_2025_paper.html}}
@article{xin2026biozkfhe,
 author={Rundong Xin and Taotao Wang and Xiaoxiao Wu and Weizhi Meng and Shengli Zhang and Shui Yu},
 title={{BioZKFHE}: Scalable Encrypted Biometric Identification via Verifiable Homomorphic Similarity Evaluation},
 journal={IEEE Transactions on Dependable and Secure Computing},year={2026},note={Early access},doi={10.1109/TDSC.2026.3716308}}
@misc{opencv2026zoo,
 author={{OpenCV}},title={OpenCV Zoo: Face Recognition SFace and Face Detection YuNet},
 year={2026},url={https://github.com/opencv/opencv_zoo},note={Pinned model hashes and preprocessing in the artifact}}
@inproceedings{charikar2002similarity,
 author={Moses S. Charikar},title={Similarity Estimation Techniques from Rounding Algorithms},
 booktitle={Proc. ACM Symp. Theory of Computing},year={2002},url={https://www.cs.princeton.edu/courses/archive/spring04/cos598B/bib/CharikarEstim.pdf}}
'''
    with (target/"references.bib").open("a") as stream:stream.write(bibliography)
    status={"working_draft_only":True,"base_main_sha256":hashlib.sha256((source/"main.tex").read_bytes()).hexdigest(),"pending":["Private client/fused correctness and comparisons", "Corrected strict-threshold open-set arrays", "Paired frontend/transfer/secure-root confirmation", "Complete scale/network results", "Generate new result/supplement tables", "Rewrite point-by-point response", "Compile and visual PDF QA", "Fresh package audit"]}
    (target/"DRAFT_STATUS.json").write_text(json.dumps(status,indent=2))
    print(json.dumps(status,indent=2))

if __name__=="__main__":main()
