# Local adjoint-vector counterterm bases

`adjoint_vector_oracle.py` checks the five two-vector and six individual
three-vector tensors in the official sgluon NLO UFO against generated ALOHA
routines. The source and import conventions are recorded in
[ADJOINT_SCALAR_LOCAL.md](ADJOINT_SCALAR_LOCAL.md).

The captured control in `adjoint_vector_local.json` covers 57 actual matched
source entries: 170 two-vector and 780 three-vector Lorentz contractions, with
all vector basis components plus complex currents at real and complex off-shell
momenta. The largest scaled difference is `9.08e-16`. Native tensor arithmetic
is exact; the independent ALOHA comparison is binary64. The existing MadGraph
colour oracle independently checks nine exact overlaps for each colour basis,
including four nonreal overlaps for the three-adjoint structure.

The catalogue binds the original typed ports, colour and Lorentz expressions.
In particular, the two-point momentum remains the second source leg. No
coefficient, loop-particle group, scalar diagnostic, graph normalization or
renormalization scheme is changed or certified by these local checks. The
individual three-gluon entries are kept separately, with their original scalar
couplings. UV and R2 categories use the same local tensor evidence where their
exact tensors agree. Unknown expressions still fail if physically selected.

This is local conformance evidence, not complete sgluon-process validation.
