"""Generated AES oracle fixture: encryption from an independent standard library."""
from pathlib import Path
import secrets
import numpy as np
import cryptography
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from reference import P,evolve,unique_locators,digest
from mpc_driver import INPUT_PATH,write_inputs

def key_contributions():
    rows=[[secrets.randbelow(P) for _ in range(2)] for _ in range(5)]
    return rows,[sum(row[j] for row in rows)%P for j in range(2)]

def masks(keys,locators,bits=512):
    assert bits%128==0
    chunks=bits//128
    counters=b"".join((row*chunks+chunk).to_bytes(16,"big") for row in range(len(locators)) for chunk in range(chunks))
    encryptor=Cipher(algorithms.AES(int(keys[1]).to_bytes(16,"big")),modes.ECB()).encryptor()
    stream=encryptor.update(counters)+encryptor.finalize()
    return np.unpackbits(np.frombuffer(stream,dtype=np.uint8)).reshape(len(locators),bits)

def system_inputs(runtime, n, bits, mode, protection, maintenance, fault, diag, query_row=0, threshold=None, exact_probe=False):
    do_transition=mode in (0,1,4)
    indexed=mode in (3,4)
    key_count=1 if protection else 2
    with np.load(INPUT_PATH) as data:
        gallery = data["gallery_roots"][:n,:bits]
        labels = data["gallery_labels"][:n]
        probe = gallery[0] if exact_probe else data["probe_roots"][query_row,:bits]
    if len(gallery) != n:
        raise ValueError("requested real gallery exceeds frozen data")
    block_bits = 4
    blocks,values = bits//block_bits,16
    capacity = min(n,8+(n+3)//4)
    m = blocks*values*capacity
    old_contributions,old_keys = key_contributions()
    new_contributions,new_keys = key_contributions()
    all_locators = unique_locators(n+m)
    db_locs = all_locators[:n]
    old_c = gallery if protection else gallery ^ masks(old_keys,db_locs,bits)
    new_locs = evolve(new_keys[0],db_locs)
    new_c = gallery if protection else gallery ^ masks(new_keys,new_locs,bits)
    counts = np.zeros(blocks*values,dtype=int)
    index_locs = all_locators[n:]
    valid = [0]*m
    for row,root in enumerate(gallery):
        for block in range(blocks):
            value = sum(int(root[block*block_bits+b]) << b for b in range(block_bits))
            bucket = block*values+value
            slot = int(counts[bucket])
            if slot >= capacity:
                raise RuntimeError("Declared public capacity insufficient; enrollment must reject/reconfigure")
            index_locs[bucket*capacity+slot] = db_locs[row]
            valid[bucket*capacity+slot] = 1
            counts[bucket] += 1
    src = valid.index(1)
    dst = next(i for i,v in enumerate(valid) if not v and i//capacity != src//capacity)
    tags = list(range(1,n+1))
    scores = np.count_nonzero(gallery != probe,axis=1)
    winner = int(np.argmin(scores))
    threshold = bits if threshold is None else threshold
    oracle_label = int(labels[winner]) if scores[winner] <= threshold else -1
    oracle_relation = 1 if mode==2 or fault==0 else 0
    by_party = {j:[] for j in range(5)}
    by_party[0].extend(map(int,db_locs))
    by_party[0].extend(map(int,old_c.T.reshape(-1)))
    if do_transition or indexed:
        by_party[0].extend(map(int,index_locs))
        by_party[0].extend(valid)
    by_party[0].extend(map(int,labels))
    by_party[0].extend(tags)
    for j in range(5):
        by_party[j].extend(old_contributions[j][:key_count])
        if do_transition:
            by_party[j].extend(new_contributions[j][:key_count])
    if mode != 1:
        by_party[1].extend(map(int,probe))
        by_party[1].append(threshold)
    if diag:
        if do_transition:
            by_party[0].extend(new_locs)
            by_party[0].extend(map(int,new_c.T.reshape(-1)))
        by_party[0].extend([oracle_label,int(scores[winner]),oracle_relation])
    state_elements = n*(bits+3)+2*m+key_count
    if do_transition and maintenance:
        for j in range(5):
            by_party[j].extend([0]*state_elements)
    write_inputs(runtime,by_party)
    info = {"n":n,"root_bits":bits,"block_bits":block_bits,"capacity":capacity,"index_slots":m,
            "required_capacity":int(counts.max()),"mode":mode,"protection":protection,
            "maintenance":maintenance,"fault":fault,"diag":diag,"src":src,"dst":dst,
            "query_row":query_row,"threshold":threshold,"exact_gallery_probe":exact_probe,
            "expected_identity":oracle_label,"expected_distance":int(scores[winner]),
            "expected_relation":oracle_relation,"gallery_roots_are_protocol_input":bool(protection),
            "input_archive":str(INPUT_PATH),"input_sha256":digest(INPUT_PATH),"key_count":key_count,
            "persistent_state_field_elements_per_party":state_elements,
            "logical_state_share_bytes_128bit_field_per_party":16*state_elements,
            "key_sampling":"5 independent contributions per key, uniform Fp, secrets.randbelow",
            "contribution_support":"[0,p)","oracle_inputs_in_timed_program":bool(diag)}
    info.update(cipher_name='AES-128-CTR',counter_assignment='(secret_tag-1)*(D/128)+chunk',aes_oracle_library='cryptography '+cryptography.__version__,fixture_sha256=digest(__file__))
    return info
