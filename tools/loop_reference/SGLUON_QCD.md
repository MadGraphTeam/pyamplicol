# Saved scalar-QCD 2→3 control

> Historical: this describes the per-diagram legacy one-loop engine, removed on
> 2026-10-29 (MQ-LEGACY-REMOVE; v2 is the only one-loop engine, see
> `docs/development/loop_v2/DESIGN.md` and §13.3 there). The modules, tools and tests named
> here may no longer exist.

The complete full-colour `u u~ -> sig8 sig8 g [QCD]` control passes against
independently generated MadLoop 3.7.0 at its binary64 accuracy. Genuine
DoubleFloat, AP60 and AP80 saved executions also pass that external comparison
and separate internal convergence checks. These results use isolated candidate
dependencies; normal package adoption is still pending. No timing or general
BSM-model capability is inferred.

## Source and conventions

The official FeynRules NLO catalogue's `sgluons_NLO` version 1.0 was converted
using MadGraph's existing Python-2 importer. Exact source order selection
`NP=QED=0` defines the pure-QCD request; excluded effective operators remain in
the raw source. The actual source UV/R2 coefficients, Laurent powers, loop
groups and diagnostics are preserved. Local scalar, vector and chiral-fermion
tensors were checked separately against ALOHA and exact dependency operations;
those local certificates alone did not certify the complete amplitude.

The frozen fixture `sgluon_qcd.json` records all inputs and the independent
reference. It uses `m8=500`, `MT=173`, `aS=0.118`, `MU_R=1000`, zero scalar/top
widths and five massless light quarks. Other source defaults are retained
explicitly. The three exact on-shell points have energies 2500, 2500 and 5200;
the baseline scale squared is 1000000 and the extra scale control is 2250000.
The source's on-shell mass and heavy-particle decoupling conventions are used
without an additional field/LSZ factor. There are no explicit external-field
currents in this request; generated MadLoop field-only contributions are also
zero. Physical couplings and the established
`Cepsilon=(4*pi)^epsilon/Gamma(1-epsilon)` convention are compared directly.

Both implementations have 6 Born graphs and 201 loop contributions. Actual
squared orders are Born QCD6 and virtual QCD8. Initial averaging 36 and the
identical-scalar factor 2 give divisor 72. MadLoop's 392 generated CT amplitudes
comprise 121 R2 and 271 local UV contributions. These counts describe the fixture;
they are not production limits or expected equalities between different graph
and current representations.

## Demonstrated fixes and accepted scope

Two exact scalar-integral chart defects initially produced nonfinite values.
[oneloopmaster PR10](https://github.com/alphal00p/oneloopmaster/pull/10), head
`cd945f4568961706ac4fe5cc0c406a7a6560711a`, dispatches exact post-chart limits
to existing infrared box routines. Independent Collier and working OneLOop
quadruple-precision orderings validate all Laurent coefficients, including
absorptive parts and nonzero double poles. The provider regression covers
1536 carrier/path/permutation/scale evaluations. No regulator, numerical
perturbation or first-finite retry was introduced.

After those repairs, complete outputs exposed missing CT attachments. Ordinary
three-gluon source aliases `GC_10=-G` and `GC_12=+G` had been treated as independent
symbols by a literal-native Bose proof. The source-owned helper (`0a224ad0`,
integrated as `41ccde87`) verifies the actual alias definitions and native
expressions, then uses the existing paired scalar resolver and Bose proof.
Equal parameter defaults never establish symbolic equality. Missing, foreign
or overridden paired bindings reject; genuinely unpaired catalogues retain
their literal proof.

The correction recovered 32 alternatives at 19 independently identified HELAS
placements across 13 source groups, including four currently zero groups.
No coupling, sign, symmetry factor, loop-group rule or CT matching algorithm
was replaced. The resulting 283 source insertions produce 408 numerical CT
currents. A new normal PACBIN was written over the retained 6 Born / 201 loop
graphs and 58 denominator families before evaluation. Original numerical owners
and source snapshots remained unchanged.

All seven complete blocks—Born, bare, local UV, external fields, UV, R2 and
total virtual—pass for all three points and the changed scale, including
finite/single/double poles and complex values. The largest normalized
binary64 difference is `1.76069e-14`; the three higher carriers each agree
with MadLoop within `2.00968e-14`, under the unchanged `3e-9` external criterion.
MadLoop is not an independent AP80 oracle. Internal DoubleFloat/AP80 agreement
is `2.30125e-31` under `1e-25`; AP60/AP80 agreement is `6.41946e-60` under
`1e-50`. The actual carriers have 106, 200 and 266 bits. Internal errors use each
component's own complex Laurent norm, with exact-zero handling and no unit
floor or Born normalization.

The isolated build used one coherent provider instance for the direct and
unchanged NinjaRS paths. Normal provider pins remain unchanged, PR10 is not
assumed merged, and the separate mixed-precision CMS fix in PR9 is not included.
Source preparation also required the isolated Goldstone-alias helper from
[ufo_model_loader PR3](https://github.com/alphal00p/ufo_model_loader/pull/3);
normal loader 1.0.1 adoption is separate. Saved numerical execution does not
reconstruct the source model. Public generation, projected colour, correlated
observables and other BSM models are outside this control.

## Replaying a retained artifact

Use an ordinarily built and staged package with the required provider repair,
and a saved complete PACBIN produced with the source-owned CT matcher. The
runner uses the standard native loader and identity check. It does not stage
an extension, override dependencies, supply a licence or generate graphs.

```sh
python tools/loop_reference/sgluon_qcd_saved.py \
  --pacbin /path/to/uubar-sgluon-pair-gluon-matched.pacbin \
  --inputs tools/loop_reference/sgluon_qcd.json \
  --output /path/to/saved-results.json
python tools/loop_reference/compare_sgluon_qcd.py \
  --producer /path/to/saved-results.json \
  --output /path/to/binary64-comparison.json
python tools/loop_reference/compare_sgluon_qcd.py \
  --producer /path/to/saved-results.json --record ap80 \
  --output /path/to/ap80-reference-comparison.json
python tools/loop_reference/compare_sgluon_qcd_convergence.py \
  --producer /path/to/saved-results.json \
  --output /path/to/internal-convergence.json
```

The runner records each result before asserting success, keeps exact decimal
inputs/outputs and captures actual carrier precision. `--carriers double`
selects only the binary64 validation case. Both comparison tools are read-only;
they preserve the independent reference precision and report every component
failure before raising. The checked-in runner is a portable packaging of the
accepted replay; its CLI/syntax checks do not constitute an additional physics
campaign.
