"""Private client output and a strong root-derived candidate baseline."""
from pathlib import Path
import ast,hashlib,json

ROOT=Path(__file__).resolve().parent

def main():
    base=(ROOT/"mpc/msle_shared_query_system.mpc").read_text()
    private=base.replace("if MODE != 1:\n    # Client inputs", "client_output_pad=sint(0)\nif MODE != 1:\n    # Client inputs")
    marker="        threshold+=weights[party]*local_threshold\n"
    assert marker in private
    private=private.replace(marker,marker+"        client_output_pad+=weights[party]*sint.get_input_from(party)\n")
    start=private.index('print_ln("MSLE_SYSTEM')
    end=private.index("\nif DIAG and INDEXED:",start)
    output='''print_ln("MSLE_PRIVATE_QUERY n=%s d=%s mode=%s protection=%s transition=%s maintenance=%s fault=%s relation=%s masked_identity=%s state_ok=%s query_ok=%s",
         N,D,MODE,PROTECTION,TRANSITION,MAINTENANCE,FAULT,relation_ok.reveal(),(decision+client_output_pad).reveal(),state_ok.reveal(),query_ok.reveal())
'''
    private=private[:start]+output+private[end:]
    assert "decision.reveal()" not in private and "accepted.reveal()" not in private
    (ROOT/"mpc/msle_private_client_system.mpc").write_text(private)
    fused=private
    begin=fused.index("    if INDEXED:\n        start_timer(23)",fused.index("    start_timer(20)"))
    end=fused.index("    start_timer(21)",begin)
    fused=fused[:begin]+fused[end:]
    begin=fused.index("    distances = sint(0,size=N)")
    end=fused.index("    def best(left,right):",begin)
    replacement='''    distances=sint(0,size=N)
    if INDEXED:
        no_block_match=sint(1,size=N)
        block_match=sint(1,size=N)
    for bit in range(D):
        protected_probe=probe[bit] if PROTECTION else xor(probe[bit],query_mask.get_vector(base=bit*N,size=N))
        mismatch=xor(current_c.get_vector(base=bit*N,size=N),protected_probe)
        distances+=mismatch
        if INDEXED:
            block_match*=1-mismatch
            if bit%B==B-1:
                no_block_match*=1-block_match
                block_match=sint(1,size=N)
    if INDEXED:
        candidate_flags=sint.Array(N)
        candidate_flags.assign_vector(1-no_block_match)
        if DIAG:
            oracle_buckets=sint.Array(BLOCKS*VALUES)
            for block in range(BLOCKS):
                for value in range(VALUES):
                    terms=[probe[block*B+b] if (value>>b)&1 else 1-probe[block*B+b] for b in range(B)]
                    oracle_buckets[block*VALUES+value]=tree_reduce(lambda a,b:a*b,terms)
            oracle_slots=sint.Array(M)
            @for_range(M)
            def _(position):
                oracle_slots[position]=oracle_buckets[position//C]*current_valid[position]
            oracle_candidates=sint.Array(N)
            @for_range(N)
            def _(row):
                matches=field_zero(current_index.get_vector()-current_locs[row])*oracle_slots.get_vector()
                oracle_candidates[row]=1-product_vector(1-matches)
            candidate_membership_ok=product_vector(1-xor(candidate_flags.get_vector(),oracle_candidates.get_vector()))
'''
    fused=fused[:begin]+replacement+fused[end:]
    (ROOT/"mpc/msle_private_fused_system.mpc").write_text(fused)
    # Keep the private input interface and complete transition unchanged.
    state_marker="current_locs,current_c,current_labels,current_ties ="
    assert private[private.index("start_timer(30)"):private.index(state_marker)]==fused[fused.index("start_timer(30)"):fused.index(state_marker)]
    assert private[private.index(state_marker):private.index("query_ok = sint(1)")]==fused[fused.index(state_marker):fused.index("query_ok = sint(1)")]
    original=(ROOT/"persisted_shared_query_driver.py").read_text()
    rows={}
    for name,source in (("private_client","msle_private_client_system"),("private_fused","msle_private_fused_system")):
        driver=original.replace("msle_shared_query_system",source).replace("shared_query_",name+"_")
        driver=driver.replace("    query_dealing_seconds=0.0","    output_pad=0\n    query_dealing_seconds=0.0")
        driver=driver.replace("        values=[*map(int,probe),threshold]","        output_pad=secrets.randbelow(P)\n        values=[*map(int,probe),threshold,output_pad]")
        old='match=re.search(r"relation=(\\d+) accepted=(\\d+) identity=(-?\\d+) state_ok=(\\d+) query_ok=(\\d+)",contents)'
        new='match=re.search(r"relation=(\\d+) masked_identity=(-?\\d+) state_ok=(\\d+) query_ok=(\\d+)",contents)'
        assert old in driver
        driver=driver.replace(old,new)
        old='    relation,accepted,identity,state_ok,query_ok=map(int,match.groups())'
        new='''    relation,masked_identity,state_ok,query_ok=map(int,match.groups())
    identity=(masked_identity-output_pad)%P
    if identity==P-1:identity=-1
    accepted=int(identity!=-1)
    assert " identity=" not in contents and " accepted=" not in contents
'''
        assert old in driver
        driver=driver.replace(old,new)
        driver=driver.replace('"plaintext_probe_input":False','"plaintext_probe_input":False,"client_private_result":True,"diagnostic_oracles_present":bool(diag),"production_output_privacy_claim":not bool(diag)')
        # Allow explicit correctness fixtures without changing the default
        # real data used in performance comparisons.
        driver=driver.replace('from mpc_driver import setup_runtime,write_inputs,run\n','from mpc_driver import setup_runtime,write_inputs,run\nINPUT_OVERRIDE=None\n')
        lines=driver.splitlines()
        for i,line in enumerate(lines):
            if line.lstrip().startswith('data_path='):
                prefix=line[:len(line)-len(line.lstrip())]
                lines[i]=prefix+'data_path=INPUT_OVERRIDE if INPUT_OVERRIDE is not None else ('+line.strip()[len('data_path='):]+')'
        driver="\n".join(lines)+"\n"
        tree=ast.parse(driver)
        old_audit=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="audit_common_core")
        original_audit=ast.get_source_segment(driver,old_audit)
        new_audit='''def audit_common_core():
    result=json.loads((ROOT/"results/private_client_source_audit.json").read_text())
    assert result["sources"]["SOURCE_NAME"]==digest(ROOT/"mpc/SOURCE_NAME.mpc")
    return result
'''.replace("SOURCE_NAME",source)
        driver=driver.replace(original_audit,new_audit)
        path=ROOT/f"persisted_{name}_driver.py";path.write_text(driver)
        rows[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
    audit={"sources":{name:sha(ROOT/f"mpc/{name}.mpc") for name in ("msle_private_client_system","msle_private_fused_system")},
        "drivers":rows,"new_plaintext_outcome_reveals":False,"private_and_fused_input_loader_identical":True,"private_and_fused_transition_identical":True,
        "output_protocol":"External client shares a fresh uniformFp additive pad together with its private probe; only masked identity is opened. Client subtracts its pad; reject is encoded as-1. Acceptance is inferred by the client, never separately opened.",
        "fused_scope":"With a valid stored root/index relation, candidate flags equal OR over exact block matches. Reuse the already computed secret Hamming mismatch bits. This is a strong baseline for a full-scan matcher, not an index-only service."}
    (ROOT/"results/private_client_source_audit.json").write_text(json.dumps(audit,indent=2))
    print(json.dumps(audit,indent=2))

if __name__=="__main__":main()
