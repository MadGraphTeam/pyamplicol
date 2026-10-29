# Local chiral fermion two-point control

> Historical: this describes the per-diagram legacy one-loop engine, removed on
> 2026-10-29 (MQ-LEGACY-REMOVE; v2 is the only one-loop engine, see
> `docs/development/loop_v2/DESIGN.md` and §13.3 there). The modules, tools and tests named
> here may no longer exist.

`chiral_fermion_two_point_oracle.py` independently checks the two chiral slashes
in the official sgluon NLO UFO. The actual ordered source ports are `u~ u`, with
`Identity(1,2)` colour and first-leg momentum:

- `FF3 = P(-1,1)*Gamma(-1,2,-2)*ProjM(-2,1)`;
- `FF6 = P(-1,1)*Gamma(-1,2,-2)*ProjP(-2,1)`.

The captured `chiral_fermion_two_point_local.json` uses MadGraph 3.7.0 ALOHA and
the Python-3-converted official source, with its scalar expressions unchanged.
Separate generated `FF3_0` and `FF6_0` routines test each chirality independently:
the physical process export combines their equal coefficients, which would not
by itself establish either local convention. Each routine is checked on all
16 spinor-component pairs and an arbitrary complex pair, at real and complex
off-shell momenta. The largest binary64 comparison error is `2.04e-16`.

An additional 96 exact Symbolica identities compare the source slashes with
their calibrated `FFV2`/`FFV3` tensors contracted with first-leg momentum, before
and after the existing production typed-endpoint adapter. The momentum label
does not move when the spinor endpoints are exchanged. No additional scalar-FFS
projector swap is applied. Sixteen exact identities also check that the two
chiral slashes sum to the unprojected slash. The source payload is unchanged.

This is local four-dimensional Lorentz/frame evidence. It does not certify
scalar coefficients, a renormalization prescription, an identity/mass insertion,
or a complete process. The independent ALOHA comparison is binary64; the
projection and endpoint identities are exact.

To reproduce in a configured dependency environment, run the tool with
`--ufo`, `--madgraph`, `--build-dir` and `--output`. All generated ALOHA sources
and libraries go under the explicit build directory; no process generation is
performed. The captured reference-source names below are relative to that
directory.
