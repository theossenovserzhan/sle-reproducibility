"""Exact candidate flags on a known locator support, with explicit preconditions."""
from pathlib import Path
import hashlib,json

ROOT=Path(__file__).resolve().parent

HELPERS='''def known_support_flags(handles,index_values,query_flags):
    # The invariant ensures that every flagged slot is in the distinct handle
    # support. Lagrange basis values are therefore exact membership bits.
    length=len(index_values)
    batch_size=256
    leaves=1<<(N-1).bit_length()
    denominators=[]
    for row in range(N):
        factors=sint.Array(N)
        factors.assign_vector(handles.get_vector()-handles[row])
        factors[row]=1
        denominators.append(factors.get_vector())
    inverse=tree_reduce(lambda a,b:a*b,denominators)**(PRIME-2)
    inverse_array=sint.Array(N)
    inverse_array.assign_vector(inverse)
    padded=((length+batch_size-1)//batch_size)*batch_size
    packed_index,packed_flags=sint.Array(padded),sint.Array(padded)
    packed_index.assign_all(0)
    packed_flags.assign_all(0)
    packed_index.assign_vector(index_values.get_vector())
    packed_flags.assign_vector(query_flags.get_vector())
    tree=sint.Array(2*leaves*batch_size)
    complement=sint.Array(2*leaves*batch_size)
    row_factors=sint.Array(N*batch_size)
    no_hit=sint.Array(N)
    no_hit.assign_all(1)
    @for_range(padded//batch_size)
    def _(batch):
        start=batch*batch_size
        slots=packed_index.get_vector(base=start,size=batch_size)
        flags=packed_flags.get_vector(base=start,size=batch_size)
        for row in range(leaves):
            value=slots-handles[row] if row<N else sint(1,size=batch_size)
            tree.assign_vector(value,base=(leaves+row)*batch_size)
        for node in range(leaves-1,0,-1):
            left=tree.get_vector(base=2*node*batch_size,size=batch_size)
            right=tree.get_vector(base=(2*node+1)*batch_size,size=batch_size)
            tree.assign_vector(left*right,base=node*batch_size)
        complement.assign_vector(sint(1,size=batch_size),base=batch_size)
        for node in range(1,leaves):
            outer=complement.get_vector(base=node*batch_size,size=batch_size)
            left=tree.get_vector(base=2*node*batch_size,size=batch_size)
            right=tree.get_vector(base=(2*node+1)*batch_size,size=batch_size)
            complement.assign_vector(outer*right,base=2*node*batch_size)
            complement.assign_vector(outer*left,base=(2*node+1)*batch_size)
        for row in range(N):
            basis=complement.get_vector(base=(leaves+row)*batch_size,size=batch_size)*inverse_array[row]
            row_factors.assign_vector(1-basis*flags,base=row*batch_size)
        width=batch_size
        while width>1:
            vector=row_factors.get_vector(size=N*width)
            half_count=N*width//2
            row_factors.assign_vector(vector.get_vector(size=half_count,skip=2)*vector.get_vector(base=1,size=half_count,skip=2))
            width//=2
        no_hit.assign_vector(no_hit.get_vector()*row_factors.get_vector(size=N))
    result=sint.Array(N)
    result.assign_vector(1-no_hit.get_vector())
    return result


def select_query_buckets(index_values,slot_flags,bucket_flags):
    # Exactly one query bucket per block; every original slot is read.
    selected_index,selected_flags=sint.Array(BLOCKS*C),sint.Array(BLOCKS*C)
    for block in range(BLOCKS):
        locators=sint(0,size=C)
        flags=sint(0,size=C)
        for value in range(VALUES):
            base=(block*VALUES+value)*C
            locators+=bucket_flags[block*VALUES+value]*index_values.get_vector(base=base,size=C)
            flags+=slot_flags.get_vector(base=base,size=C)
        selected_index.assign_vector(locators,base=block*C)
        selected_flags.assign_vector(flags,base=block*C)
    return selected_index,selected_flags


'''

def main():
    audits=[]
    for name,parent,selected in (("msle_poly_query_system","msle_system",False),
        ("msle_bucket_poly_query_system","msle_system",True),
        ("msle_lazy_bucket_poly_query_system","msle_lazy_epoch_system",True)):
        original=(ROOT/f"mpc/{parent}.mpc").read_text()
        marker="def select_arrays(bit,left,right):"
        source=original.replace(marker,HELPERS+marker)
        start=source.index("        candidate_flags=sint.Array(N)")
        end=source.index("        stop_timer(23)",start)
        body='''        lookup_index,lookup_flags=select_query_buckets(current_index,slot_flags,bucket_flags)
        candidate_flags=known_support_flags(current_locs,lookup_index,lookup_flags)
''' if selected else '''        candidate_flags=known_support_flags(current_locs,current_index,slot_flags)
'''
        body+='''        if DIAG:
            original_flags=sint.Array(N)
            @for_range(N)
            def _(row):
                matches=field_zero(current_index.get_vector()-current_locs[row])*slot_flags.get_vector()
                original_flags[row]=1-product_vector(1-matches)
            candidate_membership_ok=product_vector(1-xor(candidate_flags.get_vector(),original_flags.get_vector()))
'''
        source=source[:start]+body+source[end:]
        source=source.replace("query_ok = sint(1)\n","query_ok = sint(1)\ncandidate_membership_ok = sint(1)\n")
        source+="\nif DIAG and INDEXED:\n    print_ln('MSLE_CANDIDATES exact_membership_ok=%s',candidate_membership_ok.reveal())\n"
        target=ROOT/f"mpc/{name}.mpc";target.write_text(source)
        audits.append({"name":name,"parent":parent,"source_sha256":hashlib.sha256(target.read_bytes()).hexdigest(),
            "parent_sha256":hashlib.sha256((ROOT/f"mpc/{parent}.mpc").read_bytes()).hexdigest(),"secret_bucket_selection":selected,
            "changes":"Query candidate construction only, plus diagnostic membership-bit equality; state transition and scoring/fallback definitions retained."})
    (ROOT/"results/poly_query_source_audit.json").write_text(json.dumps(audits,indent=2))
    print(json.dumps(audits,indent=2))

if __name__=="__main__":main()
