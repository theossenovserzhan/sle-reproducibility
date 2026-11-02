"""Remove the scalar per-slot interaction loop without changing membership."""
from pathlib import Path
import hashlib,json

ROOT=Path(__file__).resolve().parent
OLD_FLAGS='''        slot_flags=sint.Array(M)
        @for_range(M)
        def _(position):
            slot_flags[position]=bucket_flags[position//C]*current_valid[position]
'''
SELECT='''def select_query_buckets(index_values,valid,bucket_flags):
    # Slot-major output; OR membership is independent of slot order.
    selected_index,selected_flags=sint.Array(BLOCKS*C),sint.Array(BLOCKS*C)
    for offset in range(C):
        locators=sint(0,size=BLOCKS)
        flags=sint(0,size=BLOCKS)
        for value in range(VALUES):
            choose=bucket_flags.get_vector(base=value,size=BLOCKS,skip=VALUES)
            locators+=choose*index_values.get_vector(base=value*C+offset,size=BLOCKS,skip=VALUES*C)
            flags+=choose*valid.get_vector(base=value*C+offset,size=BLOCKS,skip=VALUES*C)
        selected_index.assign_vector(locators,base=offset*BLOCKS)
        selected_flags.assign_vector(flags,base=offset*BLOCKS)
    return selected_index,selected_flags


'''

def main():
    audits=[]
    for target,parent,selected in (("msle_vector_poly_query_system","msle_poly_query_system",False),
        ("msle_vector_bucket_poly_query_system","msle_bucket_poly_query_system",True),
        ("msle_vector_lazy_bucket_poly_query_system","msle_lazy_bucket_poly_query_system",True)):
        source=(ROOT/f"mpc/{parent}.mpc").read_text()
        assert OLD_FLAGS in source
        if selected:
            diagnostic="        if DIAG:\n"+"\n".join("    "+line for line in OLD_FLAGS.rstrip().splitlines())+"\n"
            source=source.replace(OLD_FLAGS,diagnostic)
            begin=source.index("def select_query_buckets(")
            end=source.index("def select_arrays(",begin)
            source=source[:begin]+SELECT+source[end:]
            source=source.replace("select_query_buckets(current_index,slot_flags,bucket_flags)","select_query_buckets(current_index,current_valid,bucket_flags)")
        else:
            replacement='''        slot_flags,transposed_index=sint.Array(M),sint.Array(M)
        bucket_count=BLOCKS*VALUES
        for offset in range(C):
            slot_flags.assign_vector(bucket_flags.get_vector()*current_valid.get_vector(base=offset,size=bucket_count,skip=C),base=offset*bucket_count)
            transposed_index.assign_vector(current_index.get_vector(base=offset,size=bucket_count,skip=C),base=offset*bucket_count)
        if DIAG:
            oracle_slot_flags=sint.Array(M)
            @for_range(M)
            def _(position):
                oracle_slot_flags[position]=bucket_flags[position//C]*current_valid[position]
'''
            source=source.replace(OLD_FLAGS,replacement)
            source=source.replace("known_support_flags(current_locs,current_index,slot_flags)","known_support_flags(current_locs,transposed_index,slot_flags)")
            source=source.replace("field_zero(current_index.get_vector()-current_locs[row])*slot_flags.get_vector()","field_zero(current_index.get_vector()-current_locs[row])*oracle_slot_flags.get_vector()")
        path=ROOT/f"mpc/{target}.mpc";path.write_text(source)
        sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
        audits.append({"source":target,"source_sha256":sha(path),"parent":parent,"parent_sha256":sha(ROOT/f"mpc/{parent}.mpc"),
            "operation":"Public SIMD transpose/strided selection; remove scalar per-slot interaction; same exact known-support membership; original scalar diagnostic oracle retained."})
    (ROOT/"results/vector_query_source_audit.json").write_text(json.dumps(audits,indent=2))
    print(json.dumps(audits,indent=2))

if __name__=="__main__":main()
