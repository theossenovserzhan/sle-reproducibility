"""Independent clear reference for the corrected field configuration.

This code is an experiment oracle, not a production cryptography library.
MiMC security remains an explicit assumption; tests establish implementation
agreement, inversion and score preservation, never pseudorandomness.
"""
from pathlib import Path
import hashlib
import json
import secrets

import numpy as np

ROOT = Path(__file__).resolve().parent
PARAMETERS = json.loads((ROOT / "parameters.json").read_text(encoding="utf-8"))
P = int(PARAMETERS["prime"])
CONSTANTS = tuple(map(int, PARAMETERS["round_constants"]))
KEYS = 1 + PARAMETERS["mask_key_count"]
INVERSE_CUBE = pow(3, -1, P - 1)


def encrypt(value, key):
    value, key = int(value) % P, int(key) % P
    for constant in CONSTANTS:
        value = pow(value + key + constant, 3, P)
    return (value + key) % P


def decrypt(value, key):
    value, key = (int(value) - int(key)) % P, int(key) % P
    for constant in reversed(CONSTANTS):
        value = (pow(value, INVERSE_CUBE, P) - key - constant) % P
    return value


def key_contributions():
    contributions = [[secrets.randbelow(P) for _ in range(KEYS)] for _ in range(5)]
    aggregate = [sum(row[j] for row in contributions) % P for j in range(KEYS)]
    return contributions, aggregate


def unique_locators(n):
    seen = set()
    while len(seen) < n:
        seen.add(secrets.randbelow(P))
    return list(seen)


def mask_bits(keys, locator, bits=512):
    if bits % 64 or bits // 64 > len(keys) - 1:
        raise ValueError("unsupported root width")
    return masks(keys, [locator], bits)[0]


def masks(keys, locators, bits=512):
    # Compute each field word once, independently of the MPC implementation.
    words = [[encrypt(locator, keys[1 + chunk]) for chunk in range(bits // 64)]
             for locator in locators]
    return np.asarray([[(word >> bit) & 1 for word in row for bit in range(64)]
                       for row in words], dtype=np.uint8)


def evolve(key, locators):
    return [encrypt(value, key) for value in locators]


def hamming(query, roots):
    return np.count_nonzero(roots != query, axis=1)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
