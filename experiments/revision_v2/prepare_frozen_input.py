"""Obtain the already published input, verifying its immutable content hash."""
from pathlib import Path
import argparse,hashlib,urllib.request

ROOT=Path(__file__).resolve().parent
EXPECTED="96862a03094d7a92b697e30b8e264dc7d6b000b7a6303512c510c530486f0db1"
URL="https://raw.githubusercontent.com/theossenovserzhan/sle-reproducibility/main/results/celeba_128_binary_roots.npz"

def main(source):
    target=ROOT.parent/"inputs/celeba_128_binary_roots.npz"
    if target.exists():value=target.read_bytes()
    elif source:value=source.read_bytes()
    else:
        request=urllib.request.Request(URL,headers={"User-Agent":"TBIOM-R1-reproduction"})
        with urllib.request.urlopen(request,timeout=60) as stream:value=stream.read()
    if hashlib.sha256(value).hexdigest()!=EXPECTED:raise SystemExit("Frozen input hash mismatch; no file installed")
    target.parent.mkdir(exist_ok=True)
    if not target.exists():target.write_bytes(value)
    print("Verified frozen input:",EXPECTED)

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--source",type=Path);args=parser.parse_args();main(args.source)
