"""Read the primary Bristol Fashion AES circuit and check independent AES KATs."""
from pathlib import Path
from collections import Counter
import hashlib,json,urllib.request
import numpy as np

ROOT=Path(__file__).resolve().parent
URL="https://nigelsmart.github.io/MPC-Circuits/aes_128.txt"
TARGET=ROOT/"data/aes_128_bristol.txt"

def load(path=TARGET):
    lines=[line.split() for line in Path(path).read_text().splitlines() if line.strip()]
    gates,wires=map(int,lines[0]);input_sizes=list(map(int,lines[1]));output_sizes=list(map(int,lines[2]))
    assert input_sizes==[2,128,128] and output_sizes==[1,128]
    parsed=[];seen=set(range(256))
    for fields in lines[3:]:
        ni,no=int(fields[0]),int(fields[1]);op=fields[-1]
        assert no==1 and len(fields)==ni+no+3
        ins=tuple(map(int,fields[2:2+ni]));out=int(fields[2+ni])
        assert op in ("XOR","AND","INV","EQW","EQ") and out not in seen
        if op!="EQ":assert all(w in seen for w in ins)
        else:assert ins in ((0,),(1,))
        assert all(0<=w<wires for w in (*ins,out))
        parsed.append((op,ins,out));seen.add(out)
    assert len(parsed)==gates and len(seen)==wires
    return wires,parsed

def encode(value,order):
    bits=np.unpackbits(np.frombuffer(value,dtype=np.uint8)).tolist()
    if order=="msb":return bits
    if order=="whole_reverse":return bits[::-1]
    if order=="byte_lsb":return np.asarray(bits).reshape(-1,8)[:,::-1].reshape(-1).tolist()
    if order=="byte_reverse":return np.asarray(bits).reshape(-1,8)[::-1].reshape(-1).tolist()
    raise ValueError(order)

def decode(bits,order):
    # Each supported permutation is its own inverse.
    packed=np.packbits(np.asarray(bits,dtype=np.uint8)).tobytes()
    return np.packbits(np.asarray(encode(packed,order),dtype=np.uint8)).tobytes()

def evaluate(key,message,orientation):
    count,gates=load();values=[None]*count
    first,second=(key,message) if orientation["key_first"] else (message,key)
    values[:256]=encode(first,orientation["input_order"])+encode(second,orientation["input_order"])
    for op,ins,out in gates:
        if op=="AND":value=values[ins[0]]&values[ins[1]]
        elif op=="XOR":value=values[ins[0]]^values[ins[1]]
        elif op=="INV":value=1-values[ins[0]]
        elif op=="EQW":value=values[ins[0]]
        else:value=ins[0]
        values[out]=value
    return decode(values[-128:],orientation["output_order"])

def main():
    TARGET.parent.mkdir(exist_ok=True)
    if not TARGET.exists():
        with urllib.request.urlopen(URL,timeout=120) as response:payload=response.read()
        TARGET.write_bytes(payload)
    from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
    vectors=[("000102030405060708090a0b0c0d0e0f","00112233445566778899aabbccddeeff","69c4e0d86a7b0430d8cdb78070b4c55a"),
             ("00"*16,"00"*16,"66e94bd4ef8a2c3b884cfa59ca342b2e"),
             ("2b7e151628aed2a6abf7158809cf4f3c","6bc1bee22e409f96e93d7e117393172a","3ad77bb40d7a3660a89ecaf32466ef97")]
    found=None
    for key_first in (True,False):
        for inp in ("msb","whole_reverse","byte_lsb","byte_reverse"):
            for out in ("msb","whole_reverse","byte_lsb","byte_reverse"):
                candidate={"key_first":key_first,"input_order":inp,"output_order":out}
                if evaluate(bytes.fromhex(vectors[0][0]),bytes.fromhex(vectors[0][1]),candidate).hex()==vectors[0][2]:
                    found=candidate;break
            if found:break
        if found:break
    assert found,"Cannot map circuit wires to standard AES"
    for key_hex,msg_hex,cipher_hex in vectors:
        key,message=bytes.fromhex(key_hex),bytes.fromhex(msg_hex)
        independent=Cipher(algorithms.AES(key),modes.ECB()).encryptor().update(message)
        assert independent.hex()==cipher_hex and evaluate(key,message,found)==independent
    count,gates=load()
    metadata={"source_url":URL,"source_sha256":hashlib.sha256(TARGET.read_bytes()).hexdigest(),
        "gates":len(gates),"wires":count,"gate_counts":dict(Counter(op for op,_,_ in gates)),
        "orientation":found,"published_known_answer_vectors_passed":len(vectors),
        "independent_oracle":"cryptography AES ECB; block primitive for CTR", "mpc_tested":False}
    (ROOT/"results/aes_circuit_validation.json").write_text(json.dumps(metadata,indent=2))
    print(json.dumps(metadata,indent=2))

if __name__=="__main__":main()
