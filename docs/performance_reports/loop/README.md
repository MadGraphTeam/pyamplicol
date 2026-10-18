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
revision note corrects this to the actual imported source. The five original
warm/provider/stage observations at `fa599885` are unchanged. Validation durations
are not event timings.

The single process/provider grid continues across the first two pages and shows
B=1 and B=128 totals, preparation and stage detail in each cell. The original
five controls retain B=32 stage clocks; the five-leg row uses separate B=128 clocks.
It follows the NinjaRS benchmark's value/reference/multiplier
layout. Heat-map ratios use the fastest available original-binary provider
median for the same process and batch width, computed from the retained data.
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
not source generation. These are one fresh-process observation each on CPU380 (MadLoop DY: CPU381),
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
internal portable model-rule four-quark checkpoint (`94340682`). The latter
uses the existing PACBIN envelope and validated Rust-owned numerical layouts;
fresh source-free arithmetic views pass in all three carriers. Its first control
has nonzero UV/R2 but no external fields. Direct/source/formal/correlated plans,
rescue, public artifact activation and standalone SDK dispatch remain separate.
The shared source compiler (`43d22a52`) also prepares complete bounded QCD and
neutral-current Gmu controls from retained raw models and exact restrictions,
without named-process dispatch or rounded normalized defaults.

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
