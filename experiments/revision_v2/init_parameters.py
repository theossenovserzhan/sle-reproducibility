"""Freeze an explicit MiMC-over-prime-field configuration; run with WSL."""
from pathlib import Path
import hashlib
import json
import math

import gmpy2

root = Path(__file__).resolve().parent
prime = ((1 << 128) - 1) // 32768 * 32768 + 1
while not (gmpy2.is_prime(prime) and math.gcd(3, prime - 1) == 1):
    prime -= 32768
rounds = 81
assert 3 ** rounds >= prime
constants = [0]
for i in range(1, rounds):
    nonce = 0
    while True:
        block = hashlib.shake_256(f"MSLE-revision-v2/MiMC3/constants/{i}/{nonce}".encode()).digest(16)
        candidate = int.from_bytes(block, "big")
        if candidate < prime:
            constants.append(candidate)
            break
        nonce += 1
config = {
    "version": "M-SLE revision v2 candidate configuration",
    "prime": str(prime), "prime_bits": prime.bit_length(),
    "distance_below_2pow128": str((1 << 128) - prime),
    "exponent": 3, "rounds": rounds, "round_constants": list(map(str, constants)),
    "round_constants_sampling": "SHAKE256 domain-separated rejection sampling; first constant zero",
    "mask_chunk_bits": 64, "root_bits": 512,
    "mask_key_count": 8, "locator_key_count": 1,
    "key_sampling": "independent uniform elements of F_p, separately contributed by all five parties",
    "mask": "G_j(K_j,ell)=low64(MiMC3_81(K_j,ell)), concatenate j=0..7",
    "domain_separation": "independent keys per mask chunk and for the locator PRP; fresh bundle per epoch",
    "compiler_security_bits": 80,
    "mpc": "5-party passive Shamir, t=2, explicit prime at compile time",
    "full_field_zero_test": "1 - x^(p-1), exact by Fermat; no bounded-integer EQZ for fingerprints",
    "assumptions": ["MiMC3_81 is a secure PRP for this field and stated data limits", "MPC passive privacy", "fresh keys and specified leakage only"],
    "security_claim": "Targeted conventional 128-bit cipher configuration, conditional on PRP assumption; not a new cryptanalysis or proof of MiMC",
    "primary_source": "https://eprint.iacr.org/2016/492"
}
path = root / "parameters.json"
if path.exists() and json.loads(path.read_text()) != config:
    raise RuntimeError("Refusing to replace a different frozen parameter set")
path.write_text(json.dumps(config, indent=2), encoding="utf-8")
print(json.dumps({k:v for k,v in config.items() if k != "round_constants"}, indent=2))
