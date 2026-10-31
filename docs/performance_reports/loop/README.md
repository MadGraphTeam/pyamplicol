# pyAmpliCol one-loop report

`benchmarks.typ` is the source of the live report `benchmarks.pdf`. It opens
with **Table 1, "State of the one-loop engine"** (summary first, user request
of 2026-10-24): one row per test process by multiplicity, with generation
cost, batched full-colour and leading-colour time per point against the
fastest provider, the gate-G1 verdict, stage shares and the validation line,
and Figure 1 (the batched full-colour times against the gate limits on a log
scale). Pages 1–2 hold only the title line, Table 1, Figure 1 and compact
visual legends; every explanation (reading guide, gate chips, stage shares,
references, configurations) follows in the unnumbered section "Reading the
summary" (user rules of 2026-10-24 ~22:35: (a) generation cells uncoloured,
their multiplier as text; (b) run times on a green (faster) → white → red
(slower) scale; (e) summary pages without prose). Table 1 and Figure 1 show
only the **most recent measured configuration** of each cell (user request of
2026-10-24: "remove legacy timings and only focus on the most recent ones");
its provenance (branch, commits, and whether it is a development measurement
not yet on `loop`) is stated once, in Table 1's column header (explained in
"Reading the summary"); a cell of a row that comes from a newer validation
record than the row's G1 timing names that record's revision and run
conditions. The runtime speed gate is taken at B = 128 only (user rule of
2026-10-28, slice-status DECISIONS ~08:20 item 2; `milestone.json`
`gate_decisions.gate_batch`; `tools/loop_benchmark/gate.py` `GATE_BATCH`,
package gate-b128): Table 1 and Figure 1 show B = 128, and every other batch
size (B = 1, the 2 → 5 rows' B = 16, the history's 8 and 32) is measured and
reported with its ratio and band (gate status `reported`), without a verdict
and in a neutral, uncoloured cell of the gate-G1 tables; a configuration
without a B = 128 timing has no verdict (`missing`, with its reason). Gate
verdicts follow the user's gate rule of 2026-10-24 ~22:35: a process whose
time per point at B = 128 is below 5 ms has no blocking gate; its ratio is
shown and its verdict is "below 5 ms: not gated (user 2026-10-24)"
(`milestone.json` `gate_decisions.threshold_rule`, applied by
`scripts/build_summary.py` for Table 1 and Figure 1 and by the report's gate
helpers for the gate-G1 tables). Older
configurations (today the campaigns of m1026a at `11542fd5`, m1025a at
`1d27426b` and G-int at `4e9b5a9e` as earlier runs, the
engine before G-int with Python per-point inputs, and the development campaign
of `39824f9b`: one lane, schedule M, stability runs and the batches this
milestone did not repeat) stay in the gate-G1 details for history, labelled
with their revisions. G1 at milestone m1025a (`1d27426b`) timed with the setup
heap frozen out of Python's cyclic collector (a scratch launcher around the
unmodified harness; the protocol of `work/v2-measure-g1-7leg` `de8d3eb8`, in
the committed harness since that package's integration): the report states
this deviation from that revision's harness in the gate-G1 section and the
status page, and `g1.json` in `timing_protocol`; the 2 → 5 rows
(`measure-g1-7leg`) were timed on the same engine and build with the freeze
in the harness itself. Milestone m1025c (2026-10-26, engine `4fc72e39` on
`loop`, build `loop-native-v2-slice-79f2a5bd`; it replaces the m1025b
attempt at `db13c260`, which was not pushed) did not re-measure G1: when
`milestone.json` `engine_revision` differs from `g1.json` `slice_revision`,
the title line states once that every pyAmpliCol timing is G1's on that
revision and build (`slice_build`), and the gate-G1 section names the head
check of the 2 → 5 rows by `measure-g1-7leg`'s integration (on `db13c260`)
and the merges after it that no G1 row check covers. Milestone m1026a
(2026-10-27, engine `11542fd5` on `loop`, build `loop-native-v2-slice-11542fd5`)
re-measured G1 on that engine with the committed harness (the heap freeze is
in the harness since `de8d3eb8`; no launcher) and generated every row cold
(a fresh cache directory per run; `g1.json` `generation_protocol`), so the
title line names one engine again and the m1025a runs are `earlier_runs`.
Milestone m1028a (2026-10-28, engine `28a16255` on `loop`, build
`loop-native-v2-slice-5cb5ea83`) re-measured G1 on that engine with the same
protocol and cold generation; its round 1 of the 2 → 2 to 2 → 4 rows ran
under host contention and was repeated once, round 2 deciding (`g1.json`
`host`; round 1 stays in `earlier_runs`, which the report tells apart from a
verdict repeat: a verdict repeat times every batch size). A note under a
Table 1 value (`milestone.json` `cell_notes`, through `summary.json`
`<cell>.main.note`) qualifies one measured cell and leaves the value as
measured: in amber a known limitation, in grey run conditions. None at
m1028a: the identical-flavour LC/NLC limitation of m1026a (u u~ > u u~ g's
LC cell, then a cost measurement only) is fixed by identical-flavour-lc
(`5cb5ea83`), and the seven-gluon contention note qualified m1026a's
re-run. Milestone M-QCD (2026-10-29, engine `e18a024b` on `loop`, build
`loop-native-v2-slice-d0fef168`; full QCD one-loop support on the stock
`loop_sm`, reproducing MadLoop) re-measured G1 at B = 128 only (B = 1 and the
2 → 5 rows' B = 16 are `28a16255`'s earlier runs, marked ° in the tables) and
adds the QCD capability matrix and the FFT cost table (section "QCD capability
matrix", from `data/mqcd-matrix.json`) and the campaign's per-row appendix
(from `data/mqcd.json`). Milestone M-SM (2026-10-31, engine `71e2041e` on
`loop`, build `loop-native-v2-slice-71e2041e`; QCD + QED/EW one loop on the
shipped `loop_qcd_qed_sm` and `loop_qcd_qed_sm_Gmu`, reproducing MadLoop)
re-measured G1 at B = 128 only (B = 1 and the 2 → 5 rows' B = 16 stay
`28a16255`'s earlier runs), adds the electroweak G1 row to Table 1 and
Figure 1 (`data/msm-g1.json`, timed and reported *indicatively*, without a
verdict: `m-sm/PLAN.md` [U5], the EW speed gate binds in M-FINAL; its leading
colour is not supported, by design), the electroweak capability matrix and
the CMS table (section "Electroweak capability matrix", from
`data/msm-matrix.json`) and the M-SM campaign's per-row appendix; the M-QCD
campaign re-run at the pin replaces `data/mqcd.json` (statuses and counts
unchanged, 84 of 1212 values moved at rounding level). Then a status page
(what is on `loop`, M-SM, the gate, M-QCD kept, M-FINAL next, what is missing
with the typed refusal keys and the accepted limitations, the timing
protocol), the electroweak and QCD capability matrices, the gate-G1
details (provider grid with B = 1 and B = 128, gate bands, stage
split, levers, leading colour, throughput and recalibration, schedule B
against M, values), the required processes, the seven-gluon comparison with
NJet, the capability matrix and the architecture of the recursive v2 engine.

## Build

```sh
cd docs/performance_reports/loop
typst compile benchmarks.typ benchmarks.pdf      # Typst 0.15
```

Update source and PDF together at each milestone push to `loop`.

## Data

Table values are read from `data/*.json`; numbers quoted in prose name their
source in the report's last section. Table 1 and Figure 1 read only
`data/summary.json`, which `scripts/build_summary.py` assembles from the other
files: never edit it by hand.

**Main-configuration rule** (`MAIN_RULE` and `Recency` in
`scripts/build_summary.py`): every cell (generation, validation, full colour,
leading colour) shows the most recent configuration that measured it. The
candidates of a row: a G1 campaign's *development* side (gate `--meta
native_revision`, `native_commit`: work ahead of `loop`, being integrated;
revision `native_revision`), its *integrated* side (`slice_revision`,
`slice_lc_revision`: the engine on `loop`; revision `slice_revision`), the
development branch's validation record of the process (`measured.json`
`required_native`, revision: the docs-only commit of the DESIGN increment that
reports it; generation and validation, no batched timing, so a row G1 has not
timed shows "pending" with the package named in `milestone.json` `pending`)
and last the registry (`milestone.json` `status_notes`: a refusal attributed
to `loop`, or a capability nobody has started; no run). **Recency**: A is newer
than B if B's revision is an ancestor of A's (`git merge-base
--is-ancestor`) or if A and B are the development and integrated sides of one
G1 campaign, transitively; equal revisions keep the order development,
integrated, records; candidates that no basis orders, or that the bases order
both ways, stop the build (the order is never guessed). The ancestry of the
data's revisions is recorded in `milestone.json` `ancestry` and checked
against git wherever both revisions are present (a contradiction, or a
revision the registry does not list, stops the build), so `summary.json`
rebuilds identically in any checkout, including a clone of `loop` that lacks
the development revisions. Every fact used is recorded in `summary.json`
`meta.main_rule.recency`. **Validation** (`VALIDATION_RULE`): a newer
comparison with fewer points or fewer references than an older one and no
larger deviation only repeats part of it, so the older, more complete
comparison stays in the cell and the repeat is listed in `partial_repeats`
(configuration, revision, record, points, references, deviation and why); a
check that omits a point therefore never improves the cell, and one that finds
a larger deviation replaces it. The candidates include the older records of a
process (`measured.json` `required_native` `superseded`, as
`development_records@<revision>` in the recency order), never as its
generation, which the newest record measured. Today the ninth increment's
record of g g > g g g g g (`6f5a64cc`, point 0, with the eighth's deviations
there) repeats part of the eighth's 3-point comparison (`0ea83af2`, points
0-2), which stays in Table 1 and Table 14; the ninth's record supplies the
row's generation. Since the G-int milestone G1's configuration on `loop`
(`4e9b5a9e`, now `28a16255`) descends from every development record, so it supplies every
cell of the G1 rows, generation included (the records of g g > g g g g and
g g > t t~ g g are older candidates there). **Generation multipliers** (`GENERATION_RULE`) pair
values timed under the same kind of conditions: in a G1 row the campaign's
provider generation (idle pinned cores) with a G1 configuration; a newer
development record there (shared host under load) is printed without a
multiplier (`no_ratio`, white cell), the providers' G1 values listed beside it;
in the rows without a G1 record the record pairs with the providers' reference
runs (`ratio_basis`: both run records on this shared host outside the G1
protocol). Without a measurement a cell shows the status of the
newest configuration with a record of the row (refused, not timed, not
batched, pending, not started), so "refused" appears only where the most
recent configuration refuses. Within a row, a cell from another configuration
than the row's timing is marked: quietly with its revision and the records'
run conditions (`milestone.json` `development_records`: shared host under
load, not G1's idle pinned cores; `threads`: the generation threads each
DESIGN increment states — seventh one thread, eighth not recorded, ninth 8
pinned cores with rayon-parallel native stages — printed in Table 12) when it
is a newer record of the same branch, in amber with its origin otherwise; a
validation kept from an older record of the row's configuration names its
revision ("record 0ea83af2").

| File | Content |
|---|---|
| `summary.json` | The data of Table 1, Figure 1 and the provider-generation table, written by `scripts/build_summary.py` from `g1.json`, `measured.json`, `milestone.json` and `tools/loop_benchmark/processes.json`. `meta.main_rule` states the main-configuration rule, the validation rule, the generation rule and every recency fact it used (newer and older configuration with their revisions, and the basis: git ancestry as recorded in `milestone.json` `ancestry`, or the G1 campaign's roles); `meta.configurations` lists the candidates (`development`, `integrated`, `development_records`, `registry`) with branch, revision, commit, native build, per-point inputs, label (e.g. "development, being integrated into loop" and the integration package, from `milestone.json` `development`), the DESIGN records of the development validations (`records`, newest first, each with its revision and rows) and their run conditions, `main_rows` and `main_cells`, the rows (per cell) where each supplies a main value; the per-point inputs of a G1 side come from its own records. Per row (grouped by multiplicity, then by number of gluons; `kind` `g1` or `records`): process, legs, corrections, loop families of the main value's configuration (a count recorded only with another particle veto — the seven-gluon generation with top loops against the top-free validation — sits in `other_configuration` and is printed as that configuration's); `row_status` (the newest configuration's refusal, or a capability in development that no configuration generates yet, or one not started, with reason, package and source); the validation of the newest configuration compared with references, unless it only repeats part of an older comparison (largest finite-part deviation per reference, points, median, and whether the worst point lies within the binary64 stability estimate of the same configuration, only where the campaign re-evaluated it in that configuration; for the records rows the DESIGN record and the fixture point indices; `partial_repeats` lists newer checks that only repeat part of it); `generation.main` (generate + export, peak memory, plan size, ratio to the fastest provider generation with its `ratio_basis`, or `no_ratio` where `GENERATION_RULE` forms none, and for a development record its run conditions and threads; provider generation times with MadLoop's graph, export and compilation stages, unfinished provider runs, the fastest); `full_colour.main` (at B = 128, the gate batch (`GATE_BATCH`; a configuration that timed other batch sizes only has the status `no gate batch`, one without any batch above 1 `not batched`): median, uncertainty, stage shares — `inputs`: trees, Born and counterterm inputs; `glue`: point parameters, input conversion, assembly; `untimed`: the rest of the call in a record without any per-point input timer, i.e. the build on `loop` before lc-perf (`88657260`), whose native trees, Born and counterterm inputs only the development campaign's scratch commit `39824f9b` timed: shown apart, never attributed to a stage; since lc-perf the executor times them itself (`trees`, the harness's `native trees`), so `untimed` is 0 and the report hides its legend entry and column — gate verdict and ratio to the fastest provider; a verdict set by a user decision keeps the measured ratio, band and status, and so does a verdict set by the user's 5 ms gate rule (status `not gated`, `measured_status`, `rule`, `rule_source`; the rule takes precedence over a decision); otherwise refused, not batched, pending, not started or not measured; the providers' production times; for the seven-leg rows the production references — OpenLoops and Recola from DESIGN Table 1b as text, MadLoop from its production-build timing record, Recola's protocol run where it has no production time — and the gate limit computed from them only when every matched provider has a production time (else `missing_production` names the missing ones), and, without a matched provider, NJet as an unmatched alternative, its single-evaluation time from `measured.json`); `leading_colour.main` (LC/FC, schedule, and `adopted_schedule` where G1 adopted schedule M for the class: shown next to the protocol's schedule-B value, which stays the main one, only when run at the main value's revision: an earlier campaign's schedule-M run stays in the schedule table of the gate-G1 details). A worst point's stability re-evaluation records its run's revision (`worst_point.revision`; today the campaign's own runs at `28a16255`, bitwise the values of `11542fd5`'s rows except one unit in the last place at NJet's point 4, the estimates at rounding level: `g1.json` `values_note`), and `meta.configurations.development_records.integrated_at` the revision that integrated the records' branch into `loop`. Every main cell names its `configuration`, its `source` and `considered`, the revision and status of every candidate (and its `note` where `milestone.json` `cell_notes` has one), newest first (so the choice can be audited); a value without a record is `null` or a status, never an estimate. |
| `g1.json` | The gate-G1 campaign: per process the providers' production-mode times (median and mean per point, repeats, setup, MadLoop's stage split; a provider without a library or export keeps the reason), every pyAmpliCol configuration (today: native inputs on `loop` at full colour and LC, with the G-int campaign's and the development campaign's runs as `earlier_runs`; the Python-input history; the development campaign's one lane and schedule M; a refused generation keeps its error) per batch with its stage split, counts, throughput, uncertainty and gate verdict (pass, fail or open from the band at B = 128; `reported` at every other batch size, with the checks' own verdict as `measured_status`; per configuration `gate`, its B = 128 status or `missing` with the reason: package gate-b128), schedule M against B, the value comparison with the providers, binary64 and double-double values at the worst points, the cost-model terms and the G1-recalibrated design estimates. Written by `python -m tools.loop_benchmark gate` (see `tools/loop_benchmark`). |
| `g1-values.json` | The per-point values behind `g1.json`: pyAmpliCol's Born and finite part per configuration and stream point, and every provider run's per-point Born, finite part and time, from which the value comparison and the provider statistics can be re-derived. Recola's `finite` is stored as Recola returns it (equal to its `raw_finite`, Recola's own normalisation): the comparison first converts it to MadLoop's convention, finite + π²/6 × D × Born with D the universal double-pole coefficient of the process (`tools/loop_benchmark/gate.py` `_provider_values`, D from `providers.universal_double_pole`); compared as stored it differs at O(1). |
| `milestone.json` | Hand-maintained registry, each block with its source: integrated packages at the pinned engine revision and the commits after the last integration, `previous_loop` and `previous_engine` (the `loop` head and engine before this milestone), `development` (the branch of the development revisions G1 timed: the gate tool records a detached checkout as `HEAD`; `integrated_at`, the revision that integrated it into `loop`), OpenLoops and Recola production timings of the seven-leg gates as transcribed from DESIGN §1.3 Table 1b (text; MadLoop's come from its records in `measured.json`; the gate limit is computed by `build_summary.py`), the required-set validation notes (DESIGN WP3.1 status), NJet Table 5 and the re-measured NJet timings (`njet-benchmark.md`), NJet validation figures, `gate_decisions` (user verdicts replacing a measured open gate verdict of their process and batch, each with the revision it was made for: the u u~ > u u~ g pass of 2026-10-24, made for `39824f9b`, no longer applies, the re-measure on `loop` passing; `gate_batch`, the user's rule of 2026-10-28 (slice-status DECISIONS ~08:20 item 2): the runtime speed gate is taken at B = 128 only, every other batch size is reported with its ratio and band, without a verdict; and `threshold_rule`, the user's gate rule of 2026-10-24 ~22:35: below 5 ms per point at B = 128 the process has no blocking gate, its ratio and band shown as measured (a configuration without a B = 128 timing has no verdict at all); today u u~ > d d~ g, u u~ > u u~ g and u u~ > e- e+ g (u u~ > e- e+ g g, at 5.01 ms, is gated since M-SM), g g > g g being 2 → 2 without a gate), `status_notes`: the registry's short refusal and status attributions (a refusal attributed to `loop`, with its basis where it is inferred rather than run; a capability in development that no configuration generates yet (`in_development`; none since M-SM) or not started (`not_started`), with its work package; for an EW G1 row of `msm-g1.json` its `gate` label and `gate_reason` (indicative, no verdict) and its `leading_colour` status (not supported, by design), which `build_summary.py` requires; the V+jets refusals of the Python-input engine left at the G-int milestone), printed in Table 1 only where the most recent configuration refuses or nobody has a record, and the configuration of a development record that does not carry it (`particle_veto` of the top-free seven-gluon validation), and `pending`: the package that will time a row whose most recent configuration has no batched timing (`measure-g1-7leg`); `development` also gives the label and integration package of the development branch (Table 1's provenance); `ancestry`: the git ancestry of the revisions the main-configuration rule orders (every [older, newer] pair, as data, checked against git where present); `development_records`: the run conditions of the development validation records (shared host under load, from DESIGN WP3.1) and `threads`, the generation threads each increment states (by revision), stated wherever a record supplies a main value; `cell_notes`: notes on single measured cells (process, cell, G1 configuration, revision, kind `not validated` or `run conditions`, label, reason, source), which `build_summary.py` attaches to the main cell and which stop the build when that cell's main value is no longer the noted measurement; no measured numbers. |
| `measured.json` | Development records written by `scripts/collect_milestone.py`: the seven-gluon records of 23 October (generation with its counts and `particle_veto`, read from the run's command line — empty, so top loops included —, counterterm program, native bare loop, first virtual and its rotation); `njet_single_evaluation`, the mean time of one NJet 3.1.2 seven-gluon evaluation without the scaling test (standard and de-symmetrised) from NJet's raw timing records; `required_native`, the WP3.1 native validations of the required set, the newest record per process with the DESIGN record that reports it (`record`, and `revision`, that increment's docs-only commit: the ninth increment, 6f5a64cc, re-ran g g > g g g g, u u~ > e- e+ d d~ g and g g > g g g g g after the ct-simplify merge; the eighth, 0ea83af2, re-ran the set on its merged head; u u~ > g g g g g's newest record is the seventh increment's, fef92189), each with generation and export cost, largest deviation per reference and coefficient, per-point estimates and single-point evaluation times, and `superseded`, an earlier record of a process whose newest record re-ran fewer points (g g > g g g g g: the eighth increment's points 0-2; the ninth re-ran point 0, bitwise equal), an older candidate of Table 1's validation cell (`VALIDATION_RULE`: it stays there and in Table 14 while the newer record only repeats part of it), never of the generation cell; `provider_generation`, the provider reference runs' records of the seven-leg rows (MadLoop export, MadLoop's production-build times per point from `madloop-production-result.json` or its run state, Recola generation and its protocol run's times per point or its unfinished status, the OpenLoops library, and the reference merge's largest provider-to-provider distance). |
| `mqcd.json`, `mqcd-findings.json` | The M-QCD validation campaign (`m-qcd/PLAN.md` §4): per row the manifest facts, every tier's summary (points, checks, failures, largest deviations: DD from the reference, binary64 from DD, poles from Catani), variants, delegated columns and status; the findings' triage (curated by MQ-VALIDATE, re-checked at the pin). Written by `scripts/build_mqcd.py` from the campaign's records (see its docstring); the appendix table reads it. |
| `mqcd-public.json`, `mqcd-fft-cost.json`, `mqcd-fft-worst.json`, `mqcd-selftest.json` | The campaign's public-route representatives (one row per class through `Generator` on the shipped `loop_sm`), the FFT against direct seed contraction at B = 128 and at the worst binary64 points, and the wheel self-test of two fresh venvs; copied from `workspace/tmp/campaign-m1029-mqcd` (records archived in `workspace/reports/engine-v2/m-qcd/records/m1029-mqcd/`). |
| `mqcd-matrix.json` | The QCD capability matrix per class and the FFT cost rows, written by `scripts/build_mqcd_matrix.py` from the five files above (never by hand). |
| `msm.json`, `msm-findings.json` | The M-SM validation campaign (`m-sm/PLAN.md` §4): the same build as `mqcd.json` on the M-SM manifest (`tests/fixtures/loop/msm/manifest.json`, 71 rows), per row its tiers, variants, delegated `uv_eps_ir0` columns and status; the findings' triage (MS-VALIDATE's, unchanged at the pin). Its JSON may hold `Infinity` (out-of-scope estimates), so the report reads it only through `msm-matrix.json`. |
| `msm-public.json`, `msm-selftest.json` | The campaign's public-route test file on the shipped EW UFOs (JUnit outcomes of `tests/unit/test_loop_v2_ew_public_models.py` and its `PUBLIC_ROUTE` cases, read with `ast`) and the wheel self-test of two fresh venvs (`pyamplicol self-test --json`, its EW virtual from the shipped prepared artifact); written by the import modes of `scripts/build_msm_matrix.py`. |
| `msm-matrix.json` | The electroweak capability matrix per class of `m-sm/PLAN.md` §1.1 (public route, DD and binary64 deviations, Catani, native inputs, CMS rows, status), the CMS table and the per-row appendix data, written by `scripts/build_msm_matrix.py` from the four files above and the manifest's facts that `msm.json` does not carry (native rows, mass scheme, widths, unpredicted sectors); never by hand. |
| `msm-g1.json`, `msm-g1-values.json` | The electroweak G1 row (`gg_ttxemepg_ew`), written by `python -m tools.loop_benchmark gate` over the EW records like `g1.json`; `build_summary.py` adds it to `g1.json`'s integrated configuration when both campaigns timed the same engine (`slice_revision`; otherwise the build stops) and labels it from `milestone.json` `status_notes` (indicative, not gated). |
| `measurements.json`, `provider-cold.json`, `legacy-labels.json` | The legacy per-diagram engine's timing snapshot of 2026-10-18 (unchanged, cited by `docs/development/loop_v2/DESIGN.md`) and its labels; no longer shown (the history table is in the report revisions up to `ba7d510d`). |
| `colour-measurements.json` | The legacy engine's LC/FC runs; not shown, kept for the citations in DESIGN.md and `research-leading-colour-structure.md`. |

Missing observations stay absent; the report prints an explicit marker
instead of estimating them. Test durations are never used as event timings,
and development measurements are labelled with their branch and commit (in
Table 1 once, in its column header).

## Regenerate

- `g1.json`, `g1-values.json`: run `python -m tools.loop_benchmark pyamplicol
  <process>` (options `--inputs native`, `--accuracy lc`, `--schedule M`,
  `--lanes 1`), `… providers <process> --cpu N --work DIR --reference-root ROOT
  [--madloop-stages]` and `… stability <process> --points I … --arithmetic
  double double-double` on pinned idle cores, then `… gate <records> --json
  data/g1.json --values-json data/g1-values.json --reference-root ROOT --meta
  date=… slice_revision=… native_revision=… native_commit=… slice_build=…
  native_build=…` (the report prints these labels). The module docstrings of
  `tools/loop_benchmark` give the protocol; the records of the 2026-10-24
  campaign are archived in `workspace/reports/engine-v2/measure-g1/records/`
  (`runs/`, `runs2/`). The re-measure on `loop` at the G-int milestone
  (`4e9b5a9e`, 2026-10-24, records in `records/gint/`) ran `--inputs
  native` for full colour and LC at B = 1 and 128 (every B only for the
  single repeat of u u~ > u u~ g) and passed the gate the earlier records as
  scratch copies with the old root's paths rewritten (the gate reads a
  MadLoop export at its recorded path when that path exists), with `--meta
  slice_revision=4e9b5a9e slice_lc_revision=4e9b5a9e slice_build=…` and
  without `native_*`, so the development campaign's native/full and native/lc
  runs became `earlier_runs` of the configuration on `loop`. That gate run
  pairs the development campaign's schedule-M runs with the new schedule-B
  times (the report's schedule table says so). The re-measure at milestone
  m1025a (`1d27426b`, 2026-10-25, build `loop-native-v2-slice-7db32901`,
  records in `records/m1025a/`) ran the same configurations at B = 1 and 128
  (LC at 128; no verdict open, so no repeat) on cores 178 and 189 through
  `gc_launcher.py` with `G1_GC=freeze` (`gc.collect()`, `gc.freeze()` before
  the warm-up; `G1_GC=observe` is the committed protocol, measured on two
  processes in `gc/`), and passed the gate the earlier and G-int records
  first and its own last, with `--meta slice_revision=1d27426b
  slice_lc_revision=1d27426b slice_build=… slice_native_digest=…` and the
  text fields `integrated_configuration`, `timing_protocol`,
  `public_path_check`, `provider_records`, `previous_integrated_side`,
  `previous_development_side`, `repeats`, `values_note` (`make_g1.sh`), so the
  G-int runs became `earlier_runs` too; the same gate on the earlier records
  alone reproduces the G-int milestone's `g1.json` and `g1-values.json`
  byte for byte. The re-measure at milestone m1026a (`11542fd5`, 2026-10-26,
  the g g > g g g g g full-colour runtime re-run on 2026-10-27; build
  `loop-native-v2-slice-11542fd5`, records in `records/m1026a/`, a copy of
  the scratch campaign `workspace/tmp/g1-m1026a/`) ran the same
  configurations (2 → 2 to 2 → 4: B = 1 and 128, LC at 128; 2 → 5: B = 16
  and 128 at full and leading colour, from the stored seven-gluon process)
  with the committed harness of `11542fd5` on cores 128-223, every row
  generated cold, and passed the gate the previous campaign's 182 inputs
  (which reproduce its `g1.json` exactly) and its own 49 records
  (`inputs-final.txt`, labels `meta-final.json`), with `--meta
  slice_revision=11542fd5 slice_lc_revision=11542fd5 slice_build=…
  slice_native_digest=… slice_tool_revisions=11542fd5` and the text fields
  above plus `generation_protocol` and `known_limitations`. The re-measure
  at milestone m1028a (`28a16255`, 2026-10-28, 08:55-10:12 UTC; build
  `loop-native-v2-slice-5cb5ea83`, records in `records/m1028a/`, a copy of
  the scratch campaign `workspace/tmp/g1-m1028a/`) ran the same
  configurations with the same harness options (one guard changed: the
  seven-gluon full colour with `--budget 5400`, which only decides whether
  a batch size is skipped) with the committed harness of `28a16255` on
  cores 128-215 (one job per CCX whose least busy core was below 50 % busy;
  the public-path check and the same-core old/new A/B runs on 216-223),
  repeated the ten 2 → 2 to 2 → 4 rows and u u~ > e- e+ g g g LC once
  because of host contention (`m1028a-r2-*`, listed after round 1 so that
  they decide), and passed the gate tool of `28a16255` (gate-b128: verdicts
  at B = 128 only) the previous campaigns' 231 inputs and its own 70 records
  (`out/inputs-final.txt`, labels `out/meta-final.json`), with `--meta
  slice_revision=28a16255 measured_revision=28a16255
  slice_lc_revision=28a16255 slice_build=… slice_native_digest=…
  slice_tool_revisions=28a16255` and the same text fields.

  The re-measure at milestone M-QCD (`e18a024b`, 2026-10-29, 17:21-19:07
  UTC; build `loop-native-v2-slice-d0fef168`, records in
  `records/m1029-mqcd/`, a copy of `workspace/tmp/g1-m1029-mqcd/`) timed every
  configuration at B = 128 only, one round (timings indicative), and passed
  the gate tool of `e18a024b` (g1-accuracy: binary64 asserted where E <= 1e-9,
  DD elsewhere) the previous campaigns' inputs and its own (357 in
  `inputs-final.txt`, labels `meta-final.json`).
  The re-measure at milestone M-SM (`71e2041e`, 2026-10-31, 07:31-09:19
  UTC; build `loop-native-v2-slice-71e2041e`, records in
  `records/m1031-msm/`, a copy of `workspace/tmp/g1-m1031-msm/`) timed every
  configuration at B = 128 only, one round (the native digest changed), and
  passed the gate tool of `71e2041e` M-QCD's 357 inputs and its own (406 in
  `inputs-final.txt`, labels `meta-final.json`); the same tool on M-QCD's
  inputs and labels reproduces M-QCD's files byte for byte.
- `msm-g1.json`, `msm-g1-values.json`: `python -m tools.loop_benchmark gate
  <MS-VALIDATE's EW record> <the campaign's EW record> <the merged EW provider
  record> --json data/msm-g1.json --values-json data/msm-g1-values.json
  --reference-root ROOT --meta date=… slice_revision=… measured_revision=…
  native_build=… slice_native_digest=… ew_model=…` (at M-SM: `bin/finalize.sh`
  of `records/m1031-msm/`, inputs in its `ew-inputs/` and `runs/`); then
  `build_summary.py`.
- `mqcd.json`: `python scripts/build_mqcd.py <campaign>/c1/results --junit
  <campaign>/c1/junit-*.xml --findings data/mqcd-findings.json --meta ...`
  (the campaign's labels: `campaign_head`, `native`, `references`,
  `estimate`, `date`, `timings`, `rules`); then `python
  scripts/build_mqcd_matrix.py` and recompile. At M-SM the campaign re-ran at
  the pin (`workspace/reports/engine-v2/m-qcd/records/m1031-msm-mqcd/`, with
  `compare.json` against M-QCD's file); its `mqcd.json` replaces M-QCD's
  (the public-route, FFT and self-test files stay M-QCD's).
- `msm.json`: `python scripts/build_mqcd.py <campaign>/results --manifest
  tests/fixtures/loop/msm/manifest.json --output data/msm.json --findings
  data/msm-findings.json --junit <campaign>/ps-dy01.xml <campaign>/ps-tt01.xml
  --meta branch=… records=… natives=…` (the campaign's labels; at M-SM
  `workspace/reports/engine-v2/m-sm/records/m1031-msm/`, which rebuilds it
  byte for byte); `msm-public.json`: `python scripts/build_msm_matrix.py
  --import-public <campaign>/public.xml --source …`; `msm-selftest.json`:
  `python scripts/build_msm_matrix.py --import-selftest <pypi.json>
  <community.json> --source …`; then `python scripts/build_msm_matrix.py`
  (`msm-matrix.json`) and recompile.
- `measured.json`: `python scripts/collect_milestone.py <workspace>` reads the
  run records under `<workspace>/tmp/generation-scale/runs/` and
  `<workspace>/tmp/ct-recursion/s4/` (JSON and `/usr/bin/time` logs: wall,
  user and system time, peak memory, CPU share), the WP3.1 native validations
  under `<workspace>/tmp/generation-scale/gint2/after/`, `gint/val1/` and
  `i7/val/` (one record per process, listed in the script's `GINT_RECORDS`
  with its DESIGN record and revision; earlier records with more points in
  `SUPERSEDED`), the provider reference runs under
  `<workspace>/reference/runs/required/` and NJet's timing records under
  `<workspace>/reference/runs/njet/timing/`.
- `summary.json`: `python scripts/build_summary.py` after any of the files
  above changed, then recompile; it runs in any checkout of the report (the
  recency order reads `milestone.json` `ancestry` and checks it against git
  where the revisions are present; a new revision in the data must be added
  there with its ancestry facts, which the builder's error message names).
  The main values follow the main-configuration rule above. The gate's `--meta
  slice_revision=… slice_lc_revision=…` name the integrated side (native
  per-point inputs first where several configurations of one side qualify);
  `native_revision`, `native_commit` (and optionally `native_branch`, else
  `milestone.json` `development`) name an optional development side, which
  is ignored when absent, equal to the integrated revision or not timed; a
  campaign without any configuration at its own `slice_revision` stops the
  build. Done at the G-int milestone (package report-gint): with G1
  re-measured on `loop` at `4e9b5a9e` without a development side and
  `4e9b5a9e` added to `milestone.json` `ancestry` with its five ancestors,
  `loop`'s configuration supplies every cell of the G1 rows (likewise at
  milestone m1025a: `1d27426b` added with its six ancestors; at milestone
  m1025c `4fc72e39`, the engine on `loop`, with its seven, although no G1
  campaign ran there; at milestone m1026a `11542fd5`, engine and G1 campaign,
  with its eight; at milestone m1028a `28a16255`, engine and G1 campaign,
  with its nine; at milestone M-QCD `e18a024b` with its ten; at milestone M-SM
  `71e2041e` with its eleven); the 2 → 5 rows kept the development validation
  records (made on the branch before its integration,
  `development.integrated_at`) until the seven-leg G1 rows
  (`measure-g1-7leg`) were added to `g1.json`, which now supplies their
  cells. Checked before, on a scratch clone of this branch (2026-10-24, package
  report-dev, `git clone --single-branch`, so without the development
  revisions): `summary.json` and the PDF rebuild byte-identical; then, with
  `work/v2-generation-scale` fetched, a re-measure on `loop` simulated by
  setting `slice_revision` and `slice_lc_revision` of `g1.json` and the
  `revision` of every configuration to the generation-scale head `798a543a`
  (branch `loop`), removing the `native_*` keys and adding `798a543a` with its
  ancestry to `milestone.json`: every G1 cell comes from `integrated`, the
  2 → 5 rows from the records, and the report compiles. Changing only
  `slice_revision` (configurations left at the old campaign's revisions)
  stops the build with the message above. Earlier checks (report-dev's first
  round): a development configuration that refuses a process (Table 1 and
  Figure 1 say "refused on the development branch"; the stage-split table of
  the gate-G1 details still assumes a generable native-input configuration);
  a cell only the integrated side measured (shown with its origin). The status page's gate
  box reads Table 1's values, its M-SM box `data/msm-matrix.json`, its M-QCD box `data/mqcd-matrix.json`; its
  hand-written boxes ("Next: M-FINAL", "Missing or incomplete") and the
  feature capability matrix are updated by hand at each milestone (the QCD
  and electroweak capability matrices and the CMS table are generated). Keep the `status_notes`, `pending`, `development` (label,
  integration package, revisions) and `gate_decisions` of `milestone.json`
  current; a decision applies to a measured open verdict of its process and
  batch only; `gate_decisions.threshold_rule` (the user's 5 ms rule) applies
  to every gated process and takes precedence.
- `milestone.json` is edited by hand when a package lands or a measurement is
  replaced; keep each block's `source`.
- `figures/*.svg`: `python scripts/draw_graphs.py` draws example graphs with
  FeynKit's renderer (needs the Community HEPKit module and the
  `symbolica-fonts` bundle; set `SYMBOLICA_DATA_DIRECTORY` to its `fonts`
  directory when loading Symbolica from an overlay).

Data the report no longer uses and nothing cites were removed at the
2026-10-23 milestone: the legacy status registry `data/processes.json`, the
provider audit `data/provider-audit.json`, the seven-leg stage log
`data/generation.json` and its collector `scripts/collect_generation.py`. They
remain in the git history, e.g.
`git show 45875b87:docs/performance_reports/loop/data/generation.json`
(a copy is in the development workspace under
`reports/report-data-archive/loop-report-legacy-20261020/`).
