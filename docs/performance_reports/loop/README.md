# Live one-loop report

`benchmarks.pdf` is the rendered report; `benchmarks.typ` is its source.
Build with Typst 0.15.1 from this directory:

```sh
typst compile benchmarks.typ benchmarks.pdf
```

`data/measurements.json` is the measured snapshot used by the tables. It retains
the original complete-call timing samples and the compact native-provider
timing records. Missing stage/provider measurements remain absent rather than
being estimated. Update source, data and PDF together after each milestone.

The first snapshot is a development control run on 2026-10-18. It uses repeated
three-point physical fixtures, includes Python batch scheduling and exact input
ingress on the pyAmpliCol side, and has different provider rescue policies.
It is not the distinct-point, native-interface performance acceptance campaign.
Generation, first evaluation, warmed totals and instrumented component clocks
have separate definitions in the report. Test durations are not event timings.

Architecture notes include retained model-plan checkpoint `7290ec92`, the
explicit Gmu helper convention, exact Bose-symmetric counterterm witness
matching (`fcb5aa8b`), and the adopted NinjaRS `e4c16a7` consumer (`02922947`).
The seven-propagator rank-eight numerator cancelling exactly to a triangle
master passes generic double/DoubleFloat/AP80 and binary64 fast-tensor evaluation.
That removes the old six-propagator consumer cap; higher-multiplicity
physical validation remains separate. The five-leg counterterm fix recovers
39 missed insertions; complete five-leg Born/bare/UV/R2/full components now
pass in double, DoubleFloat and AP80 at the external reference accuracy
(`f89249d2`), with separate exact parameter-update controls.
The separate five-leg timing row comes from a fresh measured run at executed
revision `f89249d2`, including complete native components and provider checks.
Its original timer read HEAD after construction while main advanced; the retained
revision note corrects this to the actual imported source. The original pyAmpliCol warm/stage observations at `fa599885` are unchanged;
the later provider audit adds a matched Recola DY observation without replacing
the original provider timings. Validation durations
are not event timings.

The single process/provider grid continues across the first two pages and shows
B=1 and B=128 totals, preparation and stage detail in each cell. The original
five controls retain B=32 stage clocks; the five-leg row uses separate B=128 clocks.
It follows the NinjaRS benchmark's value/reference/multiplier
layout. Heat-map ratios use the fastest available original-binary provider
median for the same process and batch width, computed from the retained data. A separate LC
page pairs each new LC measurement with its own full-colour run; its colours
refer only to the matched internal full-colour value, never to external providers.
Generation and instrumented components stay neutral because their reference
boundaries are not matched. Full numeric observations and samples remain in
the JSON; display values are rounded for readability. Input and rescue-policy
asymmetries still prevent treating these ratios as performance acceptance.

The original measurement drivers and full provider logs are retained in the
task workspace as `experiments/loop_live_benchmark.py`,
`experiments/loop_live_stages.py`,
`reference/live_provider_benchmark.py`, `reports/loop-live-benchmark/`, and
`reports/loop-live-provider-benchmark/`. Frozen physical input fixtures and the
reusable native reference harness are in the repository's `tools/loop_reference/`.

`data/local-sharing-experiment.json` records a separate bounded binary64
experiment at revision `4c5a11ab`, on CPU 379. Its 32/128 distinct finite-decimal
points rescale the energies of the three frozen massless gluon controls. Five
alternating calls compare unchanged complete model-rule evaluation with exact
local instruction interning in one existing native coefficient plan. Every
original graph coefficient and complete component is bit-identical; the global
arena is slower and was not adopted. Raw samples, gather/scatter diagnostics,
workspace capacities and memory limitations are retained. This experiment does
not replace the headline snapshot or constitute a provider acceptance result.
The driver is retained as `workspace/experiments/loop_node_reuse_complete.py`;
its separate cProfile observations are in the workspace reports directory.

`data/provider-cold.json` adds separately measured preparation costs; the warm
snapshot is unchanged. MadLoop includes model/process preparation, source export
and static compilation (existing external reduction libraries reused except the
DY bundled-library build). Recola includes parameter setup, definition and
process generation; OpenLoops includes registration/start of prebuilt libraries,
not source generation. These are one fresh-process observation each on CPU380 (MadLoop DY: CPU381;
new Recola DY audit: CPU382),
without a filesystem-cache flush or uncertainty estimate. Their differing scopes
are not used for coloured ratios or an acceptance gate. Full per-case scopes and
original component timings remain in the data.

The retained-plan architecture also includes the bounded direct-R2 full-colour
gluon checkpoint `54f28474`: dimensional instructions and physical/evanescent
sectors rebind into fresh arithmetic workspaces while retaining UV/field
completion. Source, formal-colour and correlated retained views remain separate;
fresh reducers still prepare their own Laurent expansions.

Architecture coverage also records request-scoped source lowering (`5ecc735c`),
which preserves full-source species eligibility before bounded pruning, and the
internal portable checkpoints (`94340682`, extended by `95c4ed50`). Existing
PACBIN envelopes and validated Rust-owned layouts now cover complete model-rule
four-quark/top controls and direct gluon controls, including nonzero external
fields. Fresh source-free views pass in all three carriers. Source-model, formal
and correlated portable plans, rescue, public artifact activation and standalone
SDK dispatch remain separate.
The shared source compiler (`43d22a52`) also prepares complete bounded QCD and
neutral-current Gmu controls from retained raw models and exact restrictions,
without named-process dispatch or rounded normalized defaults. Source gg fields
and source-owned scale snapshots also pass in all three carriers (`3ead6484`).

`data/local-arena-experiment.json` records a separate graph-local compaction
prototype (`a738b6a3`, not adopted). It reuses the existing core lifetime allocator,
unchanged instructions and 16-row tiles, over the same distinct finite-decimal
gluon stream on CPU379. Five alternating B32/B128 calls establish exact binary64
coefficient/full-component parity; actual graph instructions also pass DD/AP80
layout checks using identical natively promoted inputs, without a higher-accuracy
physics claim. Arena capacity falls 48.4%, but no speed benefit is established.
The production baseline is retained. Both plan sets coexist during this diagnostic;
capacity excludes dependency workspaces and RSS is not a standalone A/B measure.
The driver remains `workspace/experiments/loop_arena_compaction.py`.


`data/colour-measurements.json` contains a new paired full/LC campaign at
`95c4ed50`, CPU379: fresh process for each mode, complete source/plan generation,
separate first evaluation, then five warmed calls at B1/B128. Separate B128
instrumented calls retain numerator, exclusive NinjaRS, masters, residual and
clocked total for both modes; independently computed medians need not add. The three-point
streams are repeated controls; this is not the performance acceptance campaign.
DY, distinct-flavour quarks and top use model R2. Gluon scattering uses direct
R2 and formal colour for both modes; the model four-gluon rules are not given an
unsupported formal continuation. Each full result passes its complete reference
components. LC is checked against the already certified Born/pole/UV/field
relations and full component reconstruction. These observations do not replace
the older headline full-colour data or claim numerical numerator pruning.
Workspace drivers are `experiments/loop_live_colour.py` and
`experiments/loop_live_colour_stages.py`. The two LC pages use the same grid;
stage pairs always list LC before full, and generation remains neutral.

`data/provider-audit.json` records the new CPU382 Recola photon-only DY control
and the isolated OpenLoops compiler/settings experiment. Recola uses the public
Z/e-/e+ coupling switch before generation, explicit alpha0 and massless electron;
all three Laurent coefficients and Born pass analytic controls at two scales.
OpenLoops actual-pole mode evaluates the amplitude three times and disables
Collier caching; the normal OLMode3/default high-precision policy is retained.
No QP upgrades occurred on the three smooth audit points. Generated loop kernels
in the saved original build use -O0. A separately loaded, verified -O3 library did
not establish a speed improvement in five paired B128 blocks, so original
OpenLoops headline values remain. Loaded paths, samples and all output checks
are retained. Provider source explanations are in `tools/loop_reference/README.md`.

`data/local-projector-experiment.json` retains a separate bounded CPU379
experiment at `678d19bc`. The same saved family projector instructions are bound
as one-node existing CoefficientPlans with unchanged ordered inputs/outputs and
16-row tiles. On distinct gluon control rescalings, B128 projection falls from
1.79 to 0.54ms/point and complete evaluation from 12.59 to 11.52ms/point with JIT;
tiled interpretation alone does not help. The original independent physical
rtol=5e-10/atol=1e-10 gate remains unchanged and passes. JIT arithmetic ordering is
not bit-identical; stricter extra diagnostics exposed near-zero cancellation
and one 3.03e-12 relative finite difference. Output-wise DD checks use identical
native-promoted f64 inputs and are retained without mixing differently dimensioned
coefficient norms; the flagged final finite value is closer to the DD-projector
oracle with JIT. Tiled interpreter/carrier layout, empty/tail/IDs and parameter
updates also pass. This remains an isolated, unadopted optimization; tables use
the original engines. Driver: `experiments/loop_projector_profile.py`.

The next performance additions include the already validated real-mass EW and
bounded CMS controls. They are listed as pending measurements, not inferred from
test durations. New validated processes and colour modes remain live-report work.

Shared typed buffer parsing and immutable transport now live outside PyO3
(`d3883dea`), retaining thin wrappers and validated native shapes. This is a
mechanical native boundary checkpoint, not complete native coordinator/SDK
activation; the shared timing module was unchanged.
