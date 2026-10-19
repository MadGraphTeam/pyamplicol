# Live one-loop report

`benchmarks.pdf` is the rendered report; `benchmarks.typ` is its source.

Current physics coverage includes complete model-rule UV/R2 controls through two
six-leg processes in double, DoubleFloat and AP80, and full-CKM mixed-Born
four-quark scattering with QCD corrections in double, DoubleFloat and AP70. The provider grid keeps their
B1/B128, generation and stage timing cells explicitly pending; earlier measured
observations are unchanged. The six-fermion case exercises eight true
six-propagator families. Independent references remain binary64; analytic pole,
exact coupling-update and cross-carrier convergence checks establish the separate
high-precision evidence.

Native helicity-resolved full-colour output is delivered (`ede24fad`, finite-guard
follow-up `182f06c3`). Its singleton colour axis is a complete contracted component,
not a colour-flow decomposition. `.total()` retains every order/pole and the
original averaging. Public generic generation now passes real DY and gg controls
from an explicit prepared `loop_sm`: source/staged-runtime validation before
transactional publication, public Runtime/CLI, and loaded DD32/AP70 evaluation.
This generation slice is full-colour, model-R2 and JIT; public helicity-resolved
publication now also passes a fresh DY artifact in all three carriers
(`0dd89d11`). The resolved axis has 16 helicities and one complete contracted
full-colour component; `.total()` preserves orders, poles and original averaging. The observed 215.94 s is a correctness-test duration, not a
benchmark. Directed correlation/mapping transport and SDK/UMAMI delivery remain
open. Typed native failures retain physical identities and compact whole-point
successes. State/scale compaction and exact-snapshot replay are delivered; public
opt-in cross-precision verification/rescue now passes eight native cases across
all carriers. Default evaluation performs no hidden precision retry.
Structural mass-shell binding (`e070f5fe`) fixes the demonstrated rounded-input
DD/AP branch discrepancy in the six-leg control, with all components and carriers
checked. General input-consistency diagnostics, global source-owner binding
overflow and the separate AP CMS zero-width master gate remain open. Charged chiral R2 source rules and
full-CKM mixed-Born QCD corrections now pass (`886ffd74`); this is not a joint
QCD/EW correction claim.

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
That removes the old six-propagator consumer cap. Complete six-propagator
physical validation now passes separately; seven-propagator physical coverage remains open. The five-leg counterterm fix recovers
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

An isolated audit of newer NinjaRS `0d0d7e7` passes locked dependency resolution
without any `references/` path. Its Symbolica commit is still `e679e8c1`, with
new FeynKit and oneloopmaster pins. The selected producer/consumer remain on
`e4c16a7`: a coherent consumer compile and focused physics check are required
before adoption. Rank-n+2 callbacks and master behavior changed; the owner also
documents remaining accuracy limits. This audit changes no measured timing or
advertised rank/physics capability.

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
completion. Source-owned complete QCD plans also retain exact scalar state across rebinding
(`75bb2487`); formal-colour and correlated retained views remain separate;
fresh reducers still prepare their own Laurent expansions.

Architecture coverage also records request-scoped source lowering (`5ecc735c`),
which preserves full-source species eligibility before bounded pruning, and the
internal portable checkpoints (`94340682`, extended by `95c4ed50`). Existing
PACBIN envelopes and validated Rust-owned layouts now cover complete model-rule
four-quark/top controls and direct gluon controls, including nonzero external
fields. Fresh source-free views pass in all three carriers. Source-model portable plans and public activation have subsequently been
validated. Formal/correlated portable composition and standalone SDK dispatch
remain separate; explicit public numerical rescue is now delivered below.
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
updates also pass. That experiment motivated the later explicit binding checkpoint below; its
measurements remain separate and tables retain their recorded original engines. Driver: `experiments/loop_projector_profile.py`.

The next performance additions include bounded CMS controls and further
validated processes. Pending measurements are never inferred from test durations. New validated processes and colour modes remain live-report work.

Shared typed buffers, saved evaluators, tiled schedules, exact ingress,
wavefunctions and the polynomial reduction facade now live outside PyO3
(`d3883dea` through `e90ab9f5`), retaining thin wrappers and validated native
shapes. Those primitive checkpoints now underpin complete native source coordination
and helicity-resolved evaluation. SDK activation remains open. Shared timing
modules were unchanged.

The seventh row adds real-mass full-EW Gmu `e- e+ -> mu- mu+` through the generic
source compiler at `85fb0900`, on CPU382. Fresh source capture/complete plan,
first evaluation, B1/B128 complete calls and separate B128 stage clocks are
retained in the measured snapshot. Matched Recola native timing uses the existing
verified full-EW Gmu setup, actual poles, normal cache/rescue policy and the
Cepsilon conversion inside the clock. Every timed Born/pole value is checked
against the independent MadLoop capture. The B1 fresh Recola constructor supplies
the neutral generation cell; both constructor observations remain in raw data.
No MadLoop/OpenLoops runtime is inferred. All earlier six cases and provider
observations remain unchanged. The measured provider grid continues over three pages, followed by its new
six-leg rows with timings pending, two LC pages and seven architecture pages. Drivers:
`workspace/experiments/loop_live_ew.py`,
`workspace/reference/recola_electroweak_timing.f90`, and
`workspace/reference/benchmark_recola_electroweak.py`.

`data/projector-binding-benchmark.json` measures the integrated opt-in family
projector binding (`d6c05e08`, main `996ade2d`) at CPU379. Exact saved bilinear
instructions bind as one node in the existing native tiled CoefficientPlan;
`projector_engine="jit"` is binary64-only and independent of coefficient JIT.
The interpreter remains the default and the DoubleFloat/AP path. Initial,
retained and portable bindings retain ordered shapes and fresh workspaces;
twelve focused controls cover mixed orders, all three default carriers,
precision rejection, changed parameters/scales, empty/tail batches, point IDs
and old-buffer independence. The actual complete gg production API gives B128
projection medians 1.75161→0.52171 ms/point and complete 13.28348→11.84918 ms/point
over five paired blocks of 128 distinct exact energy rescalings. All original
independent MadLoop components and old/new complete outputs pass the unchanged
rtol=5e-10/atol=1e-10 gate. Raw samples retain JIT variation; both bound plans coexist,
so RSS is not a standalone A/B measure. There is no factorization, arena change,
new engine or provider acceptance claim. Driver:
`workspace/experiments/loop_projector_binding_benchmark.py`.

Source-owned complete gluon plans now pass the internal PACBIN v3 roundtrip
(`e09f19f5`) in double, DoubleFloat and AP70, with nonzero external-field terms,
exact parameter overlays, shared ordinary/CT scale snapshots and a fresh process
without source producers. Native source coordination and public artifact dispatch are now delivered;
remaining portable feature combinations are still separate milestones.

The current priority is feature coverage and higher multiplicity; further
small-process optimization is deferred. Complete full gamma/Z
`u u~ -> e- e+ g g [QCD]` now passes all carriers at exact on-shell points,
with 528 loops, 71 families and separate bare/UV/R2/field controls. Structural
external mass-shell bindings now make the original three rounded RAMBO points
pass all components in double, DoubleFloat and AP80. Exact old/new controls,
empty batches and permuted lanes also pass. The raw off-shell evaluator is
unchanged; there is no numerical snapping. This closes the demonstrated branch
discrepancy, while general input-consistency diagnostics and unrecovered global
source-binding overflow remain separate requirements.

Complete pure-QCD `u u~ -> d d~ s s~ [QCD]` (`ec2fb7f5`, author `287df96a`)
adds 7 Born graphs, 275 loops, 94 families (eight with six propagators), and 341
CT matches. Three distinct exact-decimal points/scales match MadLoop/Ninja,
MadLoop/Collier and Recola within 1.53e-11 relative. Every emitted family/order
status, empty and permuted batches, and separate physical components are checked.
DD pole/scaling tests pass 3e-25 and AP80 tests pass 1e-60, with relative alpha_s
updates 2^-70 and 2^-180 respectively. Full DD/AP80 convergence is 6.99e-29;
this is not an independent high-precision provider comparison. Frozen tests and
fixtures are in `tests/unit/test_loop_physical_multiquark_six_propagator.py` and
`tests/fixtures/loop/multiquark-six-propagator.json`.

The new six-fermion provider audit separates two issues. MadLoop/Ninja disagrees
with agreeing Collier/Recola on a symmetric Gram configuration despite a small
reported accuracy estimate; pyAmpliCol/NinjaRS matches that pair within 7.71e-14
in double. Recola already resets Collier per event, but initialization on special
exact configurations can affect subsequent cached results. Priming with asymmetric
points restores cached/uncached agreement. Equivalence learning is an inferred
mechanism, not a fully isolated upstream defect; no provider source was changed.
The failing external results remain recorded. This audit supplies no evidence
that previous published timings are invalid, and no timing observations change.

Detailed source/component/status evidence and provider audit remain under
`workspace/reports/multiquark-sixprop-validation-summary.json`,
`workspace/reports/multiquark-provider-audit.md` and
`workspace/reference/runs/multiquark-sixleg-decimal-control/`.
The next seven-leg six-fermion-plus-gluon catalogue has 751 families, including
48 seven-propagator families. Three exact-decimal points/scales now match
MadLoop/Ninja, MadLoop/Collier and cached/uncached Recola within 1.11e-10; separate
MadLoop UV/R2/field controls are frozen too. The original source build stopped on a symbolic colour residual. Existing native
exact components give -1/9 for that network; a narrowly scoped physical-colour
fallback now passes 11 focused controls, including the nonconjugated trace-square
value -10/27. Formal Nc contraction remains symbolic. Source construction has
restarted from the retained graph plan; no seven-leg physical result is claimed
yet. The separate squared-trace dummy-scoping fix is submitted as
[draft FeynKit PR #154](https://github.com/alphal00p/gammaloop/pull/154), with three
focused trace tests passing. The broader shorthand run passes 191/192; its one
finite-dot assertion failure is reproduced on the unchanged dependency base.
Shared installed modules remain unchanged beneath the retained source producer.

Full unrestricted-CKM `u u~ -> d d~ [QCD]` now matches MadLoop for every one of
three Born orders and three virtual orders/poles at three exact points, within
6.7e-15. This extends the pure-QCD timed row rather than replacing its scope.
Independent ALOHA unequal-mass/Yukawa endpoint controls cover both charged FFV
orientations. Saved native inclusive/resolved reconstruction and exact alpha_s
updates pass all carriers (AP70 uses 2^-170); no joint QCD/EW correction claim is
made. The consolidated grid records this new control with pending timings.

Source scalar colour preparation (`2693ab28`) now retains explicitly supplied
semantic identities, exact formal grades and active diagnostics through saved
native evaluation in all carriers. It neither guesses numerical colour constants
nor enables public source LC/NLC. Counterterm scalar-alias incidence and exact
local grade-zero propagation (`326e5045`, `31314297`, `f717f0fa`) now retain local
cancellations such as `(g1+g2)*J` with coefficients `(1,-1)`, without expanding
whole currents. Common squared-sector projection (`baa222ac`) now combines
bare/UV/R2/field and epsilon rows before selecting catalogue-aligned degrees;
Born degrees remain independent and zero sectors retain their axes. Retained
projected transport (`d53d871c`) now preserves full/LC/NLC model-rule plans across
save, reload and exact-state rebinding, with native resolved sums in all three
carriers. Descriptors report the actual colour policy; public artifacts claiming
full colour for a projected plan are rejected. Certified source effective-rule
continuation and signed LC resolved semantics still gate public source LC/NLC.

The seven-leg formal-colour probe identifies a separate dependency limitation.
After the trace-scope repair, the documented symbolic routes still retain a
degree-five fundamental invariant; Idenso's dimension-invariant rewrite covers
degrees three and four. Exact SU(3) component closure remains available and is
used by the running physical producer. This does not justify substituting
numerical colour values into LC/NLC. The focused audit is recorded in
`workspace/reports/sevenprop-formal-color-audit.md`.

The explicit HV general-Nc four-gluon R2 asset (`7d0d3029`) now prepares a
whole-rule replacement after exact conformance with the complete source tensor
at Nc=3. A different published decomposition checks its formal continuation.
Original groups, species alternatives, orders and scalar diagnostics remain
source-owned. Process composition and consistent HV scheme bindings are still
required; this is local preparation, not newly certified public LC coverage.

Native point-stage failures (`6b8da611`) now include external states, scale values,
currents, reduction and assembly. State/scale blocks compact before currents;
later failures remove whole physical points and replay surviving original exact
inputs under one captured source snapshot. Typed diagnostics retain physical
identities. Public evaluation still rejects failures by default. This supplies
same-carrier failure isolation; failed global parameter binding remains a
separate boundary.

Explicit public precision verification/rescue (`43ae3254`, `cdac4326`) captures
one exact source snapshot and retries original decimal rows in native batches.
Rescue needs two higher-carrier results to agree across all Born/component/order/
pole/helicity values and a checked conversion to the requested output carrier.
Eight actual native cases pass across all three carriers, including sparse
failures, resolved results, output-bound rejection, exact parameter updates and
per-attempt diagnostic history. Initially successful points remain accuracy-
unestablished unless verification is requested. This is empirical numerical
evidence, not independent physics certification; no timing row enables it.
Global source-owner construction/update overflow remains unrecovered.

These milestones contribute no
new benchmark measurements. Keep the source, PDF and coverage notes live after
each accepted feature milestone.
