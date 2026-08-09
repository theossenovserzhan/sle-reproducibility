# SLE: formal protocol and experimental claims

## 1. Scope

Synchronized Locator Evolution (SLE) is the epoch-transition component of a
private indexed 1:N biometric identification system. SLE is not a new MPC,
ORAM, PRF, secret-sharing, or biometric-hashing primitive. Its proposed
contribution is the way independently shared copies of one semantic locator
are evolved and verified across a protected biometric database and its padded
candidate index without constructing an explicit old-to-new pointer map.

## 2. Parties and adversary

- `P0,...,P4` are five MPC computing parties.
- The current executable backend is Shamir sharing with threshold `t=2`.
- The implemented security model is passive/semi-honest.
- At least one key contribution must remain unknown to the adversary.
- Enrollment roots, probes, locators, distances, candidates, and epoch keys
  remain shared. Only Top-1/reject or transition accept/reject is opened.
- Active fault injection tests protocol invariants; it does not turn passive
  Shamir into an actively secure MPC protocol.

## 3. State

At epoch `e`, the protected state contains:

```text
D_e[i] = ([ell_i^e], [b_i], [label_i])
H_e[m,v,s] = ([ell^e], [valid])
```

Here `b_i` is a binary biometric root, `ell_i^e` is its secret semantic
locator, `m` is a public root block, `v` is a public block value, and `s` is a
slot in a fixed-capacity padded bucket. Database and index occurrences of the
same semantic locator are independent secret sharings.

## 4. Identification

Given shared probe root `[q]`:

1. Derive `L=d/block_bits` secret bucket addresses from `[q]`.
2. Read fixed-capacity candidate lists with MPC-ORAM.
3. Read candidate roots with MPC-ORAM.
4. Compute exact Hamming distances inside MPC.
5. Apply deterministic secure ArgMin and the public acceptance threshold.
6. Open only identity/reject.

The executable comparison is:

```text
full scan: O(N*d) secure matching, no secret index
indexed query: ORAM retrieval + O(C*d) secure matching
```

The indexed design is considered faster only after measured runtime and
communication beat full scan under the same MPC backend and hardware.

## 5. SLE transition

### Inputs

- Old database locators `[ell_i^e]`.
- Old padded-index locator copies and valid bits.
- Binary roots `[b_i]` used only to derive the expected bucket relation.
- One secret key contribution `[k_j]` from each party.

### Algorithm

```text
K_(e+1) <- sum_j [k_j]

for every database locator copy:
    [ell_i^(e+1)] <- PRP_MPC(K_(e+1), e+1, [ell_i^e])

for every independently shared index locator copy:
    [ell^(e+1)] <- PRP_MPC(K_(e+1), e+1, [ell^e])

expected <- {(ell_i^(e+1), m, h_m(b_i)) for every i,m}
actual   <- {(ell^(e+1), m, v) for every valid index slot (m,v,s)}

ok <- MultisetFingerprint(expected) == MultisetFingerprint(actual)

if ok:
    atomically commit the new shared state
else:
    retain the old shared state

open only ok
```

SLE applies the same secret transformation independently to semantically
equal locator copies. It never asks where the database row moved and never
produces an old-row/new-row pointer relation.

## 6. Integrity check

For public challenge `r` and tuple encoding `E`, each multiset is represented
by:

```text
Phi(S,r) = product_(x in S) (r - E(x)).
```

Two independently sampled challenges are used. Assuming non-colliding tuple
encoding and challenges sampled after candidate values are fixed, an unequal
relation is accepted only with the polynomial identity-test error. The exact
bound and commitment order must be proved for the final field and malicious
backend; the current implementation is an empirical invariant check.

## 7. Executable transition baseline

`sle_pointer_join_transition.mpc` represents generic secret pointer
translation. It evolves `N` database locators and, for each of `M` index
entries, performs secret equality against all old database locators:

```text
[new_index_j] = sum_i [old_index_j == old_db_i] * [new_db_i].
```

It reveals no map but requires `O(N*M)` secure equality work. Both SLE and the
baseline use the same key construction, relation check, atomic commit,
backend, and opened output. This isolates the proposed pointerless transition.

## 8. Falsifiable hypotheses

The method claim survives only if all mandatory hypotheses hold.

| ID | Hypothesis | Required evidence |
|---|---|---|
| H1 | SLE preserves identification semantics. | Equal Top-1/reject decisions before and after accepted transitions. |
| H2 | SLE detects invalid epoch states. | Omission, duplication, locator corruption, and wrong-bucket tests are rejected. |
| H3 | SLE reduces transition cost. | Lower runtime, communication, rounds, or secure comparisons than pointer join at equal leakage. |
| H4 | Evolving state reduces cross-epoch linkage. | Graph/linking attack AUC approaches 0.5 without unacceptable identification loss. |
| H5 | Indexed search scales better than full scan. | A measured crossover as `N` grows under the same MPC protocol. |

Failure of H3 removes the efficiency claim but may leave a lifecycle/security
contribution. Failure of H2 or H4 invalidates the main SLE security objective.

## 9. Benchmark protocol

For every configuration, report:

- `N`, root bits, block bits, candidate capacity, real/padded index entries;
- compile time, secure timer, total runtime, global communication, and rounds;
- accepted identity or transition bit;
- protocol, party count, threshold, machine, and network setting;
- mean, standard deviation, and confidence interval over at least five runs.

The minimum scaling grid is `N in {8,16,32,64,128}` with fixed 32-bit roots
for cryptographic scaling, followed by realistic 512/1024-bit roots on the
largest configuration that fits. Synthetic roots test cryptographic wiring;
FaceNet/CelebA roots test biometric behavior. These result classes must not be
mixed.

## 10. Literature-facing comparison boundary

- IDFace and PFIP are encrypted biometric-identification references. Their
  published latency cannot be treated as a direct speed baseline unless the
  dataset, hardware, output, threat model, and accuracy protocol are aligned.
- GigaDORAM is infrastructure for secret indexed access, not an SLE competitor.
- Use-Once KVS, secret shuffle, proactive sharing, and distributed PRFs are
  building blocks or adjacent infrastructure; none should be claimed as new.
- The direct executable algorithmic baseline is generic secret pointer
  translation. Full scan is the direct query baseline.

## 11. Current claim status

The smoke experiment establishes functional feasibility only: SLE can execute
inside five-party MPC and the tested relation faults are detected. It does not
yet establish active security, biometric accuracy, cross-epoch unlinkability,
or scalable advantage. Those claims become available only after H1-H5 are
measured and the formal proof assumptions are reviewed.
