# Photon-source reference controls

> Historical: this describes the per-diagram legacy one-loop engine, removed on
> 2026-10-29 (MQ-LEGACY-REMOVE; v2 is the only one-loop engine, see
> `docs/development/loop_v2/DESIGN.md` and §13.3 there). The modules, tools and tests named
> here may no longer exist.

`photon_sources.json` contains complete QCD Born–loop interference for
`u u~ -> A g` and `u A -> u g`, evaluated with Recola2 2.3.0 and SM2.2.3.
`recola_photon_sources.f90` is the independent provider driver. It selects
Born/loop strong-coupling powers 1/3, enables actual IR poles and disables the
Recola point cache for pole-parameter reevaluation. The parameters are recorded
in the JSON. In particular, its `aEWM1=132.50698` differs slightly from the
loop UFO default `132.507`; pyAmpliCol binds the matched exact value at runtime.

Compile the driver against the Recola module and shared library. Its standard
input begins with the number of rows. Each row supplies process ID, one-based
source leg (zero for ordinary), renormalization scale, momenta in
leg/component order, then the real and imaginary source four-vectors. Output
contains Born, Recola finite, single pole, double pole, and a pole-linearity
control at `(DeltaIR1,DeltaIR2)=(2,3)`. Convert finite to pyAmpliCol's convention
by adding `pi^2/6 * double_pole`.

The nonzero-source rows use **transverse complex vectors**. Recola reconstructs
these through physical helicity projectors, so it does not independently
certify the extension to arbitrary nontransverse literal four-vectors.
pyAmpliCol retains that literal contract without projecting or conjugating
inputs; publication compares source recurrence with cold execution, and
separate tests check homogeneity, exact input ownership and precision replay.

`tests/unit/test_loop_photon_sources.py` generates fresh public artifacts with
actual model-owned photon/gluon SourceIR, then covers outgoing and incoming
photons in double, DoubleFloat and arbitrary precision. It also checks joint
polarization sums, empty/tail batches, source defaults, clear, subset rescue,
and malformed saved source contracts. Set `PYAMPLICOL_NLO_UFO_REFERENCE` to
the loop UFO directory. The optional `PYAMPLICOL_PHOTON_ARTIFACTS` directory
contains existing artifact paths named `1` and `2` for read-only reruns.

`photon_sdk.rs` is a small safe Rust client for the newly generated outgoing
artifact. Link it to the existing `rusticol_loop_sdk` rlib and its dependency
directory; pass the artifact's real directory path. It checks new-schema
loading, literal source scaling, invalid class rejection and owned results.
This is a focused loading/ingress check, not a repeated SDK language campaign.
