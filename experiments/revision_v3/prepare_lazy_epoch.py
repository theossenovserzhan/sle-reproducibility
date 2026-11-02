"""Generate a separately named virtual-epoch candidate from the frozen circuit."""
from pathlib import Path
import hashlib,json
from prepare_variants import COORDINATED

ROOT=Path(__file__).resolve().parent

def main():
    base=(ROOT.parent/"revision_v2/mpc/msle_system.mpc").read_text()
    source=base.replace("def mask_array(keys, locators):","def mask_at_semantic_locators(keys, locators):")
    marker="def select_arrays(bit,left,right):"
    wrapper='''def mask_array(keys, handles):
    if PROTECTION:
        return mask_at_semantic_locators(keys,handles)
    semantic=permute_array(handles,keys[0])
    return mask_at_semantic_locators(keys,semantic)


'''
    source=source.replace(marker,wrapper+marker)
    old='''    next_locs = permute_array(old_locs,new_keys[0])
    if TRANSITION:
        next_index,join_ok = radix_translate(old_locs,old_index,valid,next_locs)
    else:
        next_index = permute_array(old_index,new_keys[0])
        join_ok = sint(1)
'''
    new='''    # Stored locators are stable secret handles. Their semantic epoch
    # locators are derived with the selected global key when masking.
    next_locs=sint.Array(N)
    next_locs.assign_vector(old_locs.get_vector())
    next_index=sint.Array(M)
    next_index.assign_vector(old_index.get_vector())
    join_ok=sint(1)
'''
    assert old in source
    source=source.replace(old,new)
    source=source.replace('"""M-SLE revision system, explicit-prime arithmetic, fixed-scan backend.', '"""Experimental virtual-epoch system: stored secret handles, derived semantic locators.')
    source=source.replace("TRANSITION 0=direct locator PRP, 1=oblivious radix sort/merge translation.","TRANSITION argument retained for driver compatibility; handles stay secret/stable.")
    source=source.replace("5=wrong index key,6=stale index entry,7=template bit flip,8=stale template.","5=wrong index transform,6=NO-OP in this representation,7=template bit flip,8=stale template.")
    (ROOT/"mpc/msle_lazy_epoch_system.mpc").write_text(source)
    diagnostic=source.replace("FAULT, SRC, DST, DIAG = map", "FAULT, SRC, DST, DIAG, CHECK_TEMPLATE, CHECK_INDEX = map")
    diagnostic=diagnostic.replace("    start_timer(14)\n",COORDINATED+"    start_timer(14)\n")
    diagnostic=diagnostic.replace("relation_ok = template_ok*join_ok*fingerprints[0]*fingerprints[1]", "index_ok=fingerprints[0]*fingerprints[1]\n    relation_ok=(template_ok if CHECK_TEMPLATE else 1)*join_ok*(index_ok if CHECK_INDEX else 1)")
    diagnostic+="\nif DIAG:\n    print_ln('MSLE_COMPONENTS template_ok=%s index_ok=%s check_template=%s check_index=%s',template_ok.reveal(),index_ok.reveal(),CHECK_TEMPLATE,CHECK_INDEX)\n"
    (ROOT/"mpc/msle_lazy_epoch_ablation.mpc").write_text(diagnostic)
    digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    audit={"base_sha256":digest(ROOT.parent/"revision_v2/mpc/msle_system.mpc"),"candidate_sha256":digest(ROOT/"mpc/msle_lazy_epoch_system.mpc"),"diagnostic_sha256":digest(ROOT/"mpc/msle_lazy_epoch_ablation.mpc"),
        "proposed_state_verification_commit_refresh_query_tail_identical":source[source.index("    next_valid = sint.Array(M)"):]==base[base.index("    next_valid = sint.Array(M)"):],
        "changes":"Stored handle semantics; wrapper derives N semantic locators for masks; physical index values preserved. This is a distinct representation candidate, not exact eager-state equality."}
    assert audit["proposed_state_verification_commit_refresh_query_tail_identical"]
    (ROOT/"results/lazy_epoch_source_audit.json").write_text(json.dumps(audit,indent=2))
    print(json.dumps(audit,indent=2))

if __name__=="__main__":main()
