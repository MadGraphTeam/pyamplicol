# pyAmpliCol one-loop benchmark report

`benchmarks.typ` is the source of `benchmarks.pdf`, the one-loop benchmark
report updated at every milestone push.

## The essentials rule

User request of 2026-11-06 ~13:25 ("keep this document to the essential with
mostly just the relevant tables"; slice-status DECISIONS ~13:25), binding for
every later milestone push. The report holds, in this order:

| Label | Content | Why it is there |
|---|---|---|
| `<tab:summary>` | **Table 1**, Born-interfered one-loop processes, on the first pages | the summary table (user 2026-10-24) |
| `<tab:summary-li>` | **Table 2**, loop-induced processes (\|A_loop\|²), Table 1's rules | the loop-induced summary table (user 2026-11-06 ~06:00) |
| `<fig:gate>` | **Figure 1**, Table 1's batched full-colour times against the providers and the gate limit (log scale); beneath them, as diamonds, Table 2's rows with a pyAmpliCol time and a matched provider time (the others not drawn, counted in the key) | the only view of how far each row is from its limit (loop-induced rows: user 2026-11-07 ~10:40) |
| `<tab:backends>` | **Table 3**, TIRust against NinjaRS under the same public unchecked setting, both process types: time per point at B = 128 with each backend's stage bar, the ratio, the agreement (loop-induced: each backend against the 256-bit truth and the L6 verdict of the checked default; Born-interfered: the largest TIRust-vs-NinjaRS difference at the timed points, LI-B1's L6) | the backend comparison (m-lit Q40): what Table 2's NinjaRS line and the Born-interfered TIRust option need |
| `<missing>` | **Missing or incomplete**, generated from the two summaries (`summary-li.json` `missing`, no hand text): one line per reason for the cells without a value, the gated rows whose verdict is fail or open (time ÷ limit and the stage that dominates pyAmpliCol's time), the partial validation cells and the accuracy notes above 1e-5, rows sharing a reason on one line | what is not (yet) measured or not passing, in one place |
| `<tab:gate>` | **Table 4**, gate and stage split at B = 128: limit, binding provider, band, chip, ms per stage | the numbers behind Table 1's gate chips and stage bars (the table view of Figure 1 and of the bars) |
| `<reading>` | "Reading the tables": one paragraph per table and marker | the explanations the summary pages leave out |

Every value is the newest measurement of its cell. Not printed: historical
data (earlier retimes, older milestones' records, superseded comparisons,
development history), milestone descriptions and narratives (status pages,
"what changed"), capability matrices, campaign appendices and architecture
text. Each table states its provenance in one line, its first row (engine
revision, native build and digest, host, date); the running header and the
page-1 subtitle name the report's date and newest measured engine revision
and label Table 1's configuration as Table 1's (`summary.json`
`meta.report`). The report reads only
`data/summary.json` and `data/summary-li.json`;
`tests/unit/test_performance_report_policy.py` checks these rules on the
source.

The table rules:

- large coloured cells per process, grouped by multiplicity; the cell value is
  the batched B = 128 median per point (finite part, binary64, one pinned
  thread, checks off) with its multiplier against the fastest matched provider
  (each provider in the settings its record names: the most optimistic ones of
  m-lit F4 where re-timed so, a production record marked ᵖ beside them, with
  the reason in `g1.json` `provider_kept`), coloured green (faster) → white →
  red (slower) on a log₂
  scale clamped at ×1/16 and ×16; every coloured cell prints its multiplier;
- generation time and memory uncoloured (the multiplier as text), leading
  colour without a provider ratio;
- explicit grey markers for every missing value, with the reason; nothing is
  estimated or extrapolated;
- gate chips (time ÷ the smallest of MadLoop's time and 1.30 × each of
  OpenLoops' and Recola's): pass or fail when the whole uncertainty band lies
  on one side of 1, else open; taken at B = 128 only (user 2026-10-28);
  below 5 ms per point not gated (user 2026-10-24); 2 → 2 not gated;
- Table 2: on the rows re-timed with the unchecked reduction setting
  ("Unchecked Table 2" below; `lit-perf`'s timed rows), TIRust unchecked as
  the cell (= `auto` with the setting) and NinjaRS unchecked beneath, each
  with its stage bar from a separate instrumented run and its measured
  accuracy against the 256-bit truth (`data/li-unchecked-accuracy.json`; in
  red the points above 1e-5 and the failed points); the providers paired in
  the same unit on the same core; the gate chip is `gate.py`'s verdict on
  TIRust (the gated backend). The other rows keep their earlier record
  (labelled in the cell): the backend `auto` serves in its checked default,
  with the other backend beside it. Generation is the engine's generation
  (generate + filter + plan export); the optional generation-time validation
  probes (off by default since `lit-probe`) are shown apart with their
  carrier where a record ran them, never in it. Rows of four legs or fewer
  are reported without a gate; *pending* where the serving package has not
  landed or the input file does not exist yet, *not run* for a landed
  package without a record.

## Build

```sh
cd docs/performance_reports/loop
python scripts/build_summary.py                  # data/summary.json, data/summary-li.json
typst compile benchmarks.typ benchmarks.pdf      # Typst 0.15
```

Update source, data and PDF together at each milestone push.

## Data

`scripts/build_summary.py` writes `data/summary.json` (Table 1, Figure 1,
Table 4) and `data/summary-li.json` (Table 2; in `figure` Figure 1's
loop-induced rows, in `backends` Table 3, in `missing` the "Missing or
incomplete" box) from the campaign records below;
never edit either by hand. Every value names its `source`.

**Stage split** (every bar and Table 4; `STAGE_ORDER`, `_split`; the
MASTER_PLAN live-report stage-split rule): inputs, numerator, scatter, the
reduction backend's own stages (NinjaRS: its expansions = the reduction
without the masters, and the masters (oneloopmaster); TIRust: its tensor
moments and contraction, and its master integrals only where a profiled arm
recorded them), glue; one colour per stage in the whole report. Table 2's
records carry the instrumented run's stages verbatim
(`retime_unchecked.py` `_stage_split`) and the builder groups them as
Table 1's.

**Main-configuration rule** (`MAIN_RULE`, `Recency`): every Table 1 cell
(generation, validation, full colour, leading colour) shows the most recent
configuration that measured it: a G1 campaign's development side (gate `--meta
native_revision`, `native_commit`), its integrated side (`slice_revision`), the
development validation records (`measured.json` `required_native`) and last
the registry (`milestone.json` `status_notes`: a refusal, or a capability
nobody has started). A is newer than B if B's revision is an ancestor of A's
or A and B are the development and integrated sides of one G1 campaign;
equal revisions keep the order development, integrated, records; an order no
basis decides stops the build. The ancestry is recorded in `milestone.json`
`ancestry` and checked against git wherever the revisions are present, so the
builder runs in any checkout; a new revision in the data needs its ancestry
facts there (the error message names them). A newer comparison that only
repeats part of an older, more complete one leaves the older in the cell
(`VALIDATION_RULE`); a generation multiplier pairs values timed under the same
kind of conditions (`GENERATION_RULE`). `meta.configurations` gives each
configuration's revision, native build and digest, date and the rows it
supplies; `meta.host` and `meta.date` the G1 host and date; `meta.report` the
report's date (`milestone.json` `date`) and the newest revision of the
measured cells of both tables (`report_meta`, by the recorded ancestry).

**Loop-induced table** (`build_loop_induced`): the row registry
`milestone.json` `loop_induced` (every process row of `m-lit/PLAN.md` §4.1 by
multiplicity group, ids, gate class, references, serving package; `landed`),
checked against `lit-ref`'s manifest `tools/loop_reference/li_campaign.json`;
pyAmpliCol's records `data/li-timing.json` (per record `key`, `revision`,
`backend` `tirust` or `ninjars` (the effective one; absent on a `missing`
record of an `auto` request, which resolved none), optional `requested`
(`auto`, `ninjars` or `tirust`, resolved as the runtime resolves a call, with
`effective` and `reason` as returned), `batch`, `seconds_per_point` (only on a
record that served every point of every block), optional `failed_points` (per
block), `served_fraction`, `failure_causes` and `whole_call_seconds_per_point`
(a call that failed points, timed whole: no served-point time) or `refused`
(a typed refusal) or `missing` (the row was not generated or timed: the
measured reason, e.g. a generation beyond the 45-min rule with its progress;
no time, no `effective`), `host`, `generation` `{seconds` (generate + the exact helicity-zero filter +
plan export), `probes_seconds` (the generation-time probes), `peak_gib` (over
all of them), `plan_mb}`; the cell is their sum, a record without
`probes_seconds` is "not recorded"), `source`, optional `native_build`,
`native_digest` (the provenance line) and, from `lit-perf` on, the gate
tool's fields: `date`, `core`, `blocks`, `stages_per_point`, `served_points`
(a failed call's time on its served points), `tir_counts_last_block` and
`gate` `{status, ratio_to_limit, band, ...}`, written by `python -m
tools.loop_benchmark gate --li-timing`); the
providers' production timing records the manifest names (below
`tests/fixtures/loop/`, MadLoop at its loop-induced card `MLReductionLib
7|6|1` only, their `host` in the provenance line; a provider whose record
has `values_excluded` is timed and shown but no matched provider: never the
fastest matched one or a limit, the multiplier to it beside the cell); `data/lit.json`
(`lit-val`'s validation figures: written by `python tools/loop_benchmark/li_manifest.py lit
--records <run records> ...` from `lit-val`'s run records, its rules and the
§4.1 checks that are not run or, by a user ruling, not applicable in
`tests/fixtures/loop/required/li/lit-val/spec/campaign.json`; there is no
separate builder script, `build_summary.py` reads it directly). A registry
row may declare `untimed` (the reason; LI-X1, an execution check without a
reference, USER 2026-11-06 ~14:55): its cells print "not timed" with it. An
absent file reads as pending. The cell
takes the newest revision's B = 128 record of the backend `auto` serves
(records without a request: the default backend first), never one with failed
points; the other backend's B = 128 record beside it with its served fraction
and causes, its time only where it served every point; one record per
request, backend, batch and revision.

| File | Content | Printed |
|---|---|---|
| `summary.json`, `summary-li.json` | the report's data (above) | yes |
| `g1.json`, `g1-values.json` | the G1 campaign: providers' times (each with its `protocol`), pyAmpliCol configurations per batch with stages, uncertainty and gate verdicts, value comparisons, stability rows (`python -m tools.loop_benchmark gate`); the per-point values behind it | through `summary.json` (newest configuration only) |
| `msm-g1.json`, `msm-g1-values.json` | the electroweak G1 row, the same gate tool; joined to `g1.json`'s integrated configuration when both timed the same engine | through `summary.json` |
| `milestone.json` | hand-maintained registry, each block with its `source`: engine revision and native build, `ancestry`, `development`, `gate_decisions` (user decisions, `gate_batch`, `threshold_rule`), `validation_decisions`, `status_notes`, `pending`, `cell_notes`, `loop_induced` | through the summaries |
| `backends-born.json` | Table 3's Born-interfered rows: TIRust and NinjaRS through the public API with `reduction_unchecked = True` on Table 1's 2 → 3 / 2 → 4 rows (time, stages, the largest TIRust-vs-NinjaRS difference at the timed points), written by `lit-report`'s final re-time; absent: those cells print "not timed" | through `summary-li.json` |
| `measured.json` | development records (`scripts/collect_milestone.py`): required-set native validations, provider reference runs, NJet timings | through `summary.json` |
| `2to6.json` | the 2 → 6 records (`scripts/build_2to6.py`): Table 1's `preliminary` rows | through `summary.json` |
| `mqcd*.json`, `msm*.json` (other than `msm-g1*`), `dec*.json`, `hc.json`, `corr.json` | the QCD, electroweak and decay validation campaigns and their matrices (`scripts/build_mqcd.py`, `build_mqcd_matrix.py`, `build_msm_matrix.py`, `build_dec_matrix.py`, `build_hc.py`, `build_corr.py`), the HC_NLO_X0 and Recola correlation rows | no (campaign records) |
| `rounds-7leg.json`, `measurements.json`, `provider-cold.json`, `legacy-labels.json`, `colour-measurements.json`, `figures/*.svg` | the seven-leg optimisation rounds, the legacy engine's timings and labels (`measurements.json` and `colour-measurements.json` are cited by `docs/development/loop_v2/DESIGN.md`), example graphs (`scripts/draw_graphs.py`) | no (records) |

## Regenerate

- `g1.json`, `g1-values.json`: `python -m tools.loop_benchmark pyamplicol
  <process>`, `… providers <process>`, `… stability <process>` on pinned idle
  cores, then `… gate <records> --json data/g1.json --values-json
  data/g1-values.json --reference-root ROOT --meta date=… slice_revision=…
  slice_lc_revision=… slice_build=… slice_native_digest=…` (the module
  docstrings of `tools/loop_benchmark` give the protocol; records of each
  retime are archived under `workspace/reports/engine-v2/measure-g1/records/`).
- `msm-g1.json`, `msm-g1-values.json`: the same `gate` over the EW records with
  `--host-spread <g1.json host_provider_spread>`.
- `measured.json`: `python scripts/collect_milestone.py <workspace>`.
- `2to6.json`: `python3 -I scripts/build_2to6.py json …` from the mf-2to6 run
  records (see its docstring).
- `data/li-timing.json`: written by the loop-induced timing steps (the
  milestone steps M-LIT-a and M-LIT-b, `lit-perf`) in the record format above
  (M-LIT-b: the harness and raw records in
  `workspace/reports/engine-v2/measure-g1/records/mlitb-li/`).
- the campaign files: their builders' docstrings.
- then `python scripts/build_summary.py` and `typst compile benchmarks.typ
  benchmarks.pdf`.

## Unchecked Table 2

Table 2 is timed with the unchecked reduction setting (`m-lit` `lit-unchecked`;
USER 2026-11-08 ~21:14 / ~22:34): both backends without their own acceptance
or refusal checks, pyAmpliCol's checks off, in a configuration any user can
set. The setting is off by default; a default call does not get these times.

**Replication** (one row, one backend; the headline times are this call, with
nothing else in the timed path):

```sh
pyamplicol <card.toml>              # the public generation (the row's run card)
RAYON_NUM_THREADS=1 taskset -c <one idle core> python - <<'PY'
import pyamplicol
from tools.loop_benchmark import streams          # the frozen stream points
stream = streams.load("li_gg_zzg")                # any row of Table 2
points = streams.binary64(stream, 128)            # B = 128 distinct points
mu_r2 = streams.mu_r2(stream, 128)                 # their mu_R^2, decimal text
rt = pyamplicol.Runtime.load("<artifact>", reduction_unchecked=True)
result = rt.evaluate(points, mu_r2=mu_r2, poles="none", on_failure="return",
                     reduction="tirust")          # or "ninjars", or "auto"
PY
```

The settings, verbatim: `Runtime.load(..., reduction_unchecked=True)` (config
`evaluation.reduction_unchecked = true`, CLI `--reduction-unchecked`, C ABI
`rusticol_virtual_set_reduction_unchecked`), `evaluate(..., poles="none",
on_failure="return", reduction="tirust" | "ninjars")` (a call that fails
points returns them as failed and is timed whole), no `stability_checks`, no
rescue policy, full colour, binary64, one thread. The setting has no
accuracy certificate: its measured accuracy per row is
`data/li-unchecked-accuracy.json` (the same public call against TIRust at
256 bits; shown in every re-timed cell). `reduction="auto"` with the setting gives the
TIRust values bitwise with no per-point fallback (shown paired on one row in
the records).

**Re-time command** (all rows, one command; `lit-report` re-runs it after
`lit-dress`):

```sh
python tools/loop_benchmark/retime_unchecked.py campaign \
  --checkout <checkout with the staged native> --native <native build dir> \
  --out <scratch dir> --artifacts <scratch dir>/artifacts \
  --cards <dir of <row>/card.toml> [--rows li_gg_zzg ...] [--dry-run]
python tools/loop_benchmark/retime_unchecked.py collect \
  --checkout <this checkout> --native <native build dir> --out <scratch dir> \
  --typst <typst 0.15.1>
```

`campaign` launches one `systemd-run --user` unit per row (rows: `lit-perf`'s
timed loop-induced rows; one physical core each, its SMT siblings idle),
waits (or `--no-wait`) and runs `collect`. A unit: the row's artifact through
the public `Generator` from its card (reused when present), then rounds of
the public calls above on every arm (`tirust`, `ninjars`; `auto` on
`--auto-row`) over `--instances` fresh runtimes created in rotated order, the
providers in their F4 most optimistic settings (`python -m tools.loop_benchmark
providers <row> --protocol optimistic`) in the same unit on the same core,
alternating with pyAmpliCol between rounds, then the separate instrumented
run (`python -m tools.loop_benchmark pyamplicol <row> --unchecked`: stage
shares and the engine's generation, never the timed call). `collect` writes one
`data/li-timing.json` record per row and backend (`configuration`
`"unchecked"`: the settings verbatim, `instance_medians`, `instance_spread`,
`cpu_share`, the paired `providers` with their rounds, `gate` by `gate.py`'s
rules unchanged, `stages` of the instrumented run, `generation`, `tir_counts`
from a counters-only read outside the timed calls, `auto_pairing`), then the
summaries and the PDF. The builder takes an unchecked record's paired
providers as the row's provider times. Runtime: the rows run in parallel,
the longest (`li_gg_hggg`, 2 rounds) about 2 h; memory up to ~30 GiB per row (`li_gg_hggg`, six runtimes in one
process).

Campaign `c1` (2026-11-09, engine `ecc80899`, before `lit-dress`): the
records' `cpu_share` is empty (the field came after the timed revision);
`li_gg_hggg` has 2 rounds per runtime (the row budget); g g > W+ W- g ended
inconclusive (ratio 1.40, band 0.92-1.88, its provider rounds drifting by
about 1.9× within the unit) and was not repeated: `lit-report` re-times
every row after `lit-dress`.
