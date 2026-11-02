"""Generate isolated experimental variants from the frozen R1 circuit."""
from pathlib import Path
import hashlib,json

ROOT=Path(__file__).resolve().parent
FROZEN=ROOT.parent/"revision_v2"

COMPACT='''def radix_translate(old_db, old_index, valid, new_db, key):
    L=N*BLOCKS
    assert L<=M
    compact=sint.Matrix(M,3)
    compact.set_column(0,old_index.get_vector())
    compact.set_column(1,sint(regint.inc(M)))
    compact.set_column(2,valid.get_vector())
    known_bits=sint.Matrix(1,M)
    known_bits[0].assign_vector(1-valid.get_vector())
    sorting.radix_sort_from_matrix(known_bits,compact,n_threads=1)
    compact_valid=compact.get_column(2)
    count_ok=product_vector(compact_valid.get_vector(size=L))
    if M>L:
        count_ok*=product_vector(1-compact_valid.get_vector(base=L,size=M-L))
    valid_locs=sint.Array(L)
    valid_locs.assign_vector(compact.get_column(0).get_vector(size=L))
    evolved=permute_array(valid_locs,key)
    values=sint.Array(M)
    values.assign_vector(evolved.get_vector())
    if M>L:
        values.assign_vector(sint.get_random(size=M-L),base=L)
    compact.set_column(0,values.get_vector())
    restore=sint.Array(M)
    restore.assign_vector(compact.get_column(1))
    sorting.reveal_sort(restore,compact,n_threads=1)
    result=sint.Array(M)
    result.assign_vector(compact.get_column(0))
    return result,count_ok


'''

COORDINATED='''    elif FAULT == 9:
        # Flip one root bit AND move its corresponding index occurrence to
        # the new bucket. Thus the proposed state is internally consistent,
        # but no longer represents the previous enrolled biometric root.
        candidate_c[0]=1-candidate_c[0]
        changed=candidate_c.get_vector() if PROTECTION else xor(candidate_c.get_vector(),new_mask.get_vector())
        wanted_bucket=sum(changed[bit*N]*(2**bit) for bit in range(B))
        width=VALUES*C
        remove=field_zero(next_index.get_vector(size=width)-next_locs[0])*next_valid.get_vector(size=width)
        next_valid.assign_vector(next_valid.get_vector(size=width)*(1-remove))
        installed=sint.Array(1)
        installed[0]=0
        @for_range(width)
        def _(position):
            take=(1-installed[0])*(wanted_bucket==cint(position//C))*(1-next_valid[position])
            next_index[position]=take.if_else(next_locs[0],next_index[position])
            next_valid[position]+=take
            installed[0]+=take
        join_ok*=installed[0]

'''

POSITION_PREFIX='''    L=N*BLOCKS
    assert L<=M
    bit_key=sint.Array(M)
    bit_key.assign_vector(1-valid.get_vector())
    positions=sint.Array(M)
    positions.assign_vector(sorting.gen_bit_perm(bit_key,n_threads=1))
    packed=sint.Array(M)
    packed.assign_vector(old_index.get_vector())
    sorting.reveal_sort(positions,packed,n_threads=1)
    count_ok=field_zero(valid.get_vector().sum()-L)
'''

POSITION_DIRECT='''def radix_translate(old_db, old_index, valid, new_db, key):
'''+POSITION_PREFIX+'''    live=sint.Array(L)
    live.assign_vector(packed.get_vector(size=L))
    evolved=permute_array(live,key)
    result=sint.Array(M)
    result.assign_vector(evolved.get_vector())
    if M>L:
        result.assign_vector(sint.get_random(size=M-L),base=L)
    sorting.reveal_sort(positions,result,reverse=True,n_threads=1)
    return result,count_ok


'''

def main():
    source=(FROZEN/"mpc/msle_system.mpc").read_text()
    assert hashlib.sha256((FROZEN/"mpc/msle_system.mpc").read_bytes()).hexdigest()=="bf5086b808432fa86978fe82e0e6042e5144c060f0af162747a75b3c0c648401"
    begin,end=source.index("def radix_translate("),source.index("start_timer(30)")
    optimized=source[:begin]+COMPACT+source[end:]
    optimized=optimized.replace("radix_translate(old_locs,old_index,valid,next_locs)","radix_translate(old_locs,old_index,valid,next_locs,new_keys[0])")
    (ROOT/"mpc/msle_valid_compact_system.mpc").write_text(optimized)
    def diagnostic_variant(base):
        result=base.replace("FAULT, SRC, DST, DIAG = map", "FAULT, SRC, DST, DIAG, CHECK_TEMPLATE, CHECK_INDEX = map")
        marker="    start_timer(14)\n"
        assert result.count(marker)==1
        result=result.replace(marker,COORDINATED+marker)
        result=result.replace("relation_ok = template_ok*join_ok*fingerprints[0]*fingerprints[1]", "index_ok=fingerprints[0]*fingerprints[1]\n    relation_ok = (template_ok if CHECK_TEMPLATE else 1)*join_ok*(index_ok if CHECK_INDEX else 1)")
        return result+"\nif DIAG:\n    print_ln('MSLE_COMPONENTS template_ok=%s index_ok=%s check_template=%s check_index=%s',template_ok.reveal(),index_ok.reveal(),CHECK_TEMPLATE,CHECK_INDEX)\n"
    ablation=diagnostic_variant(source)
    (ROOT/"mpc/msle_joint_ablation.mpc").write_text(ablation)
    (ROOT/"mpc/msle_valid_compact_ablation.mpc").write_text(diagnostic_variant(optimized))
    sort_source=(FROZEN/"mpc/msle_compact_sort_system.mpc").read_text()
    old="    compact_key=sint.Array(M)\n    compact_key.assign_vector(1-valid.get_vector())\n    sorting.radix_sort(compact_key,compact,n_bits=1,signed=False,n_threads=1)"
    new="    known_bits=sint.Matrix(1,M)\n    known_bits[0].assign_vector(1-valid.get_vector())\n    sorting.radix_sort_from_matrix(known_bits,compact,n_threads=1)"
    assert old in sort_source
    sort_source=sort_source.replace(old,new)
    (ROOT/"mpc/msle_compact_sort_known_bits.mpc").write_text(sort_source)
    position_direct=source[:begin]+POSITION_DIRECT+source[end:]
    position_direct=position_direct.replace("radix_translate(old_locs,old_index,valid,next_locs)","radix_translate(old_locs,old_index,valid,next_locs,new_keys[0])")
    (ROOT/"mpc/msle_position_compact_system.mpc").write_text(position_direct)
    (ROOT/"mpc/msle_position_compact_ablation.mpc").write_text(diagnostic_variant(position_direct))
    sb,se=sort_source.index("def radix_translate("),sort_source.index("start_timer(30)")
    function=sort_source[sb:se]
    function="def radix_translate(old_db, old_index, valid, new_db):\n"+POSITION_PREFIX+function[function.index("    length = N+L"):]
    function=function.replace("compact[i][0]","packed[i]").replace("compact[i][2]","sint(1)")
    function=function[:function.index("    compact.set_column(0,compact_values.get_vector())")]+"    sorting.reveal_sort(positions,compact_values,reverse=True,n_threads=1)\n    return compact_values,join_ok\n\n\n"
    position_sort=sort_source[:sb]+function+sort_source[se:]
    (ROOT/"mpc/msle_compact_sort_positions.mpc").write_text(position_sort)
    runner=(ROOT/"run_compact_direct.py").read_text().replace("msle_valid_compact_system","msle_position_compact_system").replace("msle_valid_compact_ablation","msle_position_compact_ablation").replace("msle_compact_sort_known_bits","msle_compact_sort_positions").replace("compact_direct_status.json","position_compact_status.json").replace('"performance"','"position_comparison"')
    (ROOT/"run_position_compact.py").write_text(runner)
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    audit={"frozen_r1_sha256":sha(FROZEN/"mpc/msle_system.mpc"),"optimized_source_sha256":sha(ROOT/"mpc/msle_valid_compact_system.mpc"),"ablation_source_sha256":sha(ROOT/"mpc/msle_joint_ablation.mpc"),
        "optimized_helpers_before_translation_identical":optimized[:begin]==source[:begin],
        "optimized_state_checks_commit_shuffle_refresh_query_identical":optimized[optimized.index("    next_valid = sint.Array(M)"):]==source[source.index("    next_valid = sint.Array(M)"):],
        "optimized_change":"Already-known validity bit supplied directly to the one-bit radix sorter; L=N*BLOCKS PRP evaluations, fresh dummy values, perfect-permutation restoration. Public state size and validity positions unchanged.",
        "strong_sort_source_sha256":sha(ROOT/"mpc/msle_compact_sort_known_bits.mpc"),
        "strong_sort_receives_same_known_bit_optimization":True,
        "position_direct_sha256":sha(ROOT/"mpc/msle_position_compact_system.mpc"),
        "position_sort_sha256":sha(ROOT/"mpc/msle_compact_sort_positions.mpc"),
        "position_refinement":"Direct stable destination permutation from known validity bits, one-field forward/inverse sorting, exact secret count check. Same optimization supplied to sort/merge.",
        "ablation_scope":"Diagnostic-only public removal of checker components and a coupled root/index defect. Does not establish malicious-party security."}
    assert audit["optimized_helpers_before_translation_identical"] and audit["optimized_state_checks_commit_shuffle_refresh_query_identical"]
    (ROOT/"results/variant_source_audit.json").write_text(json.dumps(audit,indent=2))
    print(json.dumps(audit,indent=2))

if __name__=="__main__":main()
