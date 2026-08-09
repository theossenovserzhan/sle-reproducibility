# SLE journal evidence summary

## External biometric validation
- CelebA: Rank-1=0.8515 (95% split-bootstrap CI 0.8474-0.8558), EER=0.0477.
- LFW: Rank-1=0.9849 (95% split-bootstrap CI 0.9832-0.9864), EER=0.0111.

## Direct transition comparison at N=128
- Runtime speedup: 28.47x.
- Communication reduction: 38.79x.
- Effective-AUC gap: 0.0020.

## Claim boundary
- Empirical unlinkability is claimed only for observable locator tokens.
- Root, complete key, and persistent metadata compromise are out of scope.
- The current passive backend and fault tests are not an active-security proof.
- LFW results use a custom closed-set protocol, not the official LFW protocol.
