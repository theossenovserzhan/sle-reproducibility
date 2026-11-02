"""Build a separately named standard-encryption comparator from frozen sources."""
from pathlib import Path
import ast,hashlib,json
from prepare_variants import COORDINATED

ROOT=Path(__file__).resolve().parent

AES_HELPERS='''# Standard AES circuit, arithmetic-shared bit gates. Circuit source and wire
# orientation are independently validated; key-only gates are hoisted per call.
import hashlib as _aes_hashlib
_aes_text=Path("msle_aes_128_bristol.txt").read_bytes()
_aes_meta=json.loads(Path("msle_aes_backend.json").read_text())
assert _aes_hashlib.sha256(_aes_text).hexdigest()==_aes_meta["circuit_sha256"]
_aes_lines=[line.split() for line in _aes_text.decode().splitlines() if line.strip()]
_AES_WIRES=int(_aes_lines[0][1])
_AES_GATES=[]
for _fields in _aes_lines[3:]:
    _ni=int(_fields[0])
    assert int(_fields[1])==1
    _AES_GATES.append((_fields[-1],tuple(map(int,_fields[2:2+_ni])),int(_fields[2+_ni])))


def _aes_gate(op,values,ins):
    if op=="XOR":
        a,b=values[ins[0]],values[ins[1]]
        if isinstance(a,int):return b if a==0 else 1-b
        if isinstance(b,int):return a if b==0 else 1-a
        return xor(a,b)
    if op=="AND":
        a,b=values[ins[0]],values[ins[1]]
        if isinstance(a,int):return 0 if a==0 else b
        if isinstance(b,int):return 0 if b==0 else a
        return a*b
    if op=="INV":return 1-values[ins[0]]
    if op=="EQW":return values[ins[0]]
    if op=="EQ":return ins[0]
    raise ValueError(op)


def aes_encrypt_bits(key,counter_bits):
    # Bristol Fashion uses whole-value little-endian wire order for both
    # inputs and output. Missing high counter bits are known public zeros.
    width=len(counter_bits)
    assert 0<width<=128
    key_bits=key.bit_decompose(128)
    values=[None]*_AES_WIRES
    values[:128]=key_bits
    dependencies=[0]*_AES_WIRES
    dependencies[:128]=[1]*128
    for bit in range(128):
        if bit<width:dependencies[128+bit]=2
        else:values[128+bit]=0
    remaining=[]
    for op,ins,out in _AES_GATES:
        dep=0
        if op!="EQ":
            for wire in ins:dep|=dependencies[wire]
        dependencies[out]=dep
        if dep&2:remaining.append((op,ins,out))
        else:values[out]=_aes_gate(op,values,ins)
    for bit,value in enumerate(counter_bits):values[128+bit]=value
    for op,ins,out in remaining:values[out]=_aes_gate(op,values,ins)
    return values[-128:]


'''

AES_MASK='''def mask_array(keys,locators,tags):
    result=sint.Array(N*D)
    if PROTECTION:
        result.assign_all(0)
        return result
    assert D%128==0
    chunks=D//128
    assert chunks&(chunks-1)==0
    shift=(chunks-1).bit_length()
    width=max(1,(N-1).bit_length())
    # Enrolled tags are the trusted unique integers1..N, carried with rows.
    # counter=(tag-1)*chunks+chunk, never reduced modulo the field.
    assert (N*chunks-1)<PRIME
    tag_bits=(tags.get_vector()-1).bit_decompose(width)
    length=N*chunks
    counter_bits=[]
    for bit in range(shift):
        counter_bits.append(cint((regint.inc(length)//(N*(2**bit)))%2))
    for bit in range(width):
        expanded=sint.Array(length)
        for chunk in range(chunks):expanded.assign_vector(tag_bits[bit],base=chunk*N)
        counter_bits.append(expanded.get_vector())
    encrypted=aes_encrypt_bits(keys[1],counter_bits)
    temporary=sint.Array(length)
    for bit in range(128):
        temporary.assign_vector(encrypted[127-bit])
        for chunk in range(chunks):
            result.assign_vector(temporary.get_vector(base=chunk*N,size=N),base=(chunk*128+bit)*N)
    return result


'''

FIXTURE_HEADER='''"""Generated AES oracle fixture: encryption from an independent standard library."""
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

'''

def main():
    metadata=json.loads((ROOT/"results/aes_circuit_validation.json").read_text())
    assert metadata["published_known_answer_vectors_passed"]==3
    assert metadata["orientation"]=={"key_first":True,"input_order":"whole_reverse","output_order":"whole_reverse"}
    base=(ROOT/"mpc/msle_compact_sort_positions.mpc").read_text()
    start=base.index("def mask_array(keys, locators):")
    end=base.index("def select_arrays(bit,left,right):",start)
    source=base[:start]+AES_HELPERS+AES_MASK+base[end:]
    source=source.replace("KEY_COUNT = 1 if PROTECTION else 9","KEY_COUNT = 1 if PROTECTION else 2")
    source=source.replace("mask_array(old_keys,old_locs),mask_array(new_keys,next_locs)","mask_array(old_keys,old_locs,ties),mask_array(new_keys,next_locs,ties)")
    source=source.replace("mask_array(current_keys,current_locs)","mask_array(current_keys,current_locs,current_ties)")
    source=source.replace('"""M-SLE revision system, explicit-prime arithmetic, fixed-scan backend.','"""AES-128 CTR standard-encryption comparator, same private transition checks.')
    (ROOT/"mpc/msle_aes_system.mpc").write_text(source)
    old_transition='''    next_locs = permute_array(old_locs,new_keys[0])
    if TRANSITION:
        next_index,join_ok = radix_translate(old_locs,old_index,valid,next_locs)
    else:
        next_index = permute_array(old_index,new_keys[0])
        join_ok = sint(1)
'''
    stable_transition='''    # Same secret-handle representation as the virtual-epoch candidate.
    # AES counters use existing stable secret tie tags; no locator copies
    # need to be materialized for encryption or private relation checks.
    next_locs=sint.Array(N)
    next_locs.assign_vector(old_locs.get_vector())
    next_index=sint.Array(M)
    next_index.assign_vector(old_index.get_vector())
    join_ok=sint(1)
'''
    assert old_transition in source
    stable=source.replace(old_transition,stable_transition)
    stable=stable.replace("6=stale index entry","6=NO-OP with stable handles")
    (ROOT/"mpc/msle_aes_lazy_system.mpc").write_text(stable)
    diagnostic=source.replace("FAULT, SRC, DST, DIAG = map", "FAULT, SRC, DST, DIAG, CHECK_TEMPLATE, CHECK_INDEX = map")
    diagnostic=diagnostic.replace("    start_timer(14)\n",COORDINATED+"    start_timer(14)\n")
    diagnostic=diagnostic.replace("relation_ok = template_ok*join_ok*fingerprints[0]*fingerprints[1]","index_ok=fingerprints[0]*fingerprints[1]\n    relation_ok=(template_ok if CHECK_TEMPLATE else 1)*join_ok*(index_ok if CHECK_INDEX else 1)")
    diagnostic+="\nif DIAG:\n    print_ln('MSLE_COMPONENTS template_ok=%s index_ok=%s check_template=%s check_index=%s',template_ok.reveal(),index_ok.reveal(),CHECK_TEMPLATE,CHECK_INDEX)\n"
    (ROOT/"mpc/msle_aes_ablation.mpc").write_text(diagnostic)
    primitive=source[:source.index("start_timer(30)")]
    primitive=primitive.replace("N, D, B, C, MODE, PROTECTION, TRANSITION, MAINTENANCE, FAULT, SRC, DST, DIAG = map(int, program.args[1:])", "N,D,B,C,MODE,PROTECTION,TRANSITION,MAINTENANCE,FAULT,SRC,DST,DIAG = 3,128,4,3,2,0,0,1,0,0,0,1")
    primitive+='''start_timer(30)
kat_keys,kat_messages=sint.Array(3),sint.Array(3)
kat_expected=sint.Array(3*128)
kat_keys.input_from(0)
kat_messages.input_from(0)
kat_expected.input_from(0)
kat_output=aes_encrypt_bits(kat_keys.get_vector(),kat_messages.get_vector().bit_decompose(128))
kat_checks=sint.Array(128)
for bit in range(128):
    kat_checks[bit]=product_vector(1-xor(kat_output[bit],kat_expected.get_vector(base=bit*3,size=3)))
kat_ok=product_vector(kat_checks.get_vector())
stop_timer(30)
print_ln('MSLE_AES_KAT vectors=3 bits=384 ok=%s',kat_ok.reveal())
'''
    (ROOT/"mpc/msle_aes_primitives.mpc").write_text(primitive)
    original=(ROOT/"mpc_driver.py").read_text()
    function=next(node for node in ast.parse(original).body if isinstance(node,ast.FunctionDef) and node.name=="system_inputs")
    fixture=ast.get_source_segment(original,function).replace("key_count=1 if protection else 9","key_count=1 if protection else 2")
    fixture=fixture.replace("    return info","    info.update(cipher_name='AES-128-CTR',counter_assignment='(secret_tag-1)*(D/128)+chunk',aes_oracle_library='cryptography '+cryptography.__version__,fixture_sha256=digest(__file__))\n    return info")
    (ROOT/"aes_input_fixture.py").write_text(FIXTURE_HEADER+fixture+"\n")
    config={"circuit_sha256":metadata["source_sha256"],"source_url":metadata["source_url"],
        "orientation":metadata["orientation"],"field_backend_unchanged":True,
        "key_schedule":"Key-only gates hoisted once per mask call; all row/counter instances vectorized", "aes_key_count":1,"locator_key_count":1,
        "scope":"Arithmetic shared-bit implementation, not a lower bound on AES across backends"}
    (ROOT/"aes_backend_config.json").write_text(json.dumps(config,indent=2))
    digest=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
    audit={"base_sha256":digest(ROOT/"mpc/msle_compact_sort_positions.mpc"),"aes_system_sha256":digest(ROOT/"mpc/msle_aes_system.mpc"),
        "fixture_sha256":digest(ROOT/"aes_input_fixture.py"),"config_sha256":digest(ROOT/"aes_backend_config.json"),
        "changes":"Only encryption/key count and tag-aware mask calls; same transition checks and complete-state maintenance. Strong compact-sort and direct controls use TRANSITION1/0."}
    (ROOT/"results/aes_source_audit.json").write_text(json.dumps(audit,indent=2))
    print(json.dumps(audit,indent=2))

if __name__=="__main__":main()
