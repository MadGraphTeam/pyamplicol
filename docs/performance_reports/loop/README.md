# pyAmpliCol one-loop benchmark report

`benchmarks.typ` is the source of `benchmarks.pdf`, the one-loop benchmark
report, rebuilt whenever its data change.

## The essentials rule

The report holds the tables and only the text needed to read them. Its items, in order:

| Label | Content |
|---|---|
| `<tab:summary>` | **Table 1**, Born-interfered one-loop processes |
| `<tab:summary-li>` | **Table 2**, loop-induced processes (\|A_loop\|²), read as Table 1 |
| `<fig:gate>` | **Figure 1**, batched times per point against the providers and the gate limit (log scale): Table 1's rows, then Table 2's rows with a pyAmpliCol and a matched provider time |
| `<tab:backends>` | **Table 3**, TIRust against NinjaRS with the unchecked setting, both process types: time, ratio, agreement |
| `<missing>` | **Missing or incomplete**, generated from `summary-li.json` `missing`: cells without a value, failing or open gates, partial validation, accuracy above 1e-5 |
| `<tab:gate>` | **Table 4**, gate and stage split at B = 128: the numbers behind Table 1's chips and bars |
| `<reading>` | **Reading the tables**: settings, symbols and caveats |

Every value is the newest measurement of its cell; no history, project
narrative or architecture text. Each table states its provenance in its first
row (engine revision, native build and digest, host, date); the running header
and the page-1 subtitle give the report's date and newest engine revision
(`summary.json` `meta.report`). The report reads only `data/summary.json` and
`data/summary-li.json`; `tests/unit/test_performance_report_policy.py` checks
these rules on the source. How each table is read (colours, chips, markers,
settings) is in the report itself, under "Reading the tables".

## Build

```sh
cd docs/performance_reports/loop
python scripts/build_summary.py                  # data/summary.json, data/summary-li.json
typst compile benchmarks.typ benchmarks.pdf      # Typst 0.15
```

Update source, data and PDF together.

## Data

`scripts/build_summary.py` writes `data/summary.json` (Table 1, Figure 1,
Table 4) and `data/summary-li.json` (Table 2; in `figure` Figure 1's
loop-induced rows, in `backends` Table 3, in `missing` the "Missing or
incomplete" box) from the campaign records below;
never edit either by hand. Every value names its `source`.

**Stage split** (every bar and Table 4; `STAGE_ORDER`, `_split`): inputs, numerator, scatter, the
reduction backend's own stages (NinjaRS: its expansions = the reduction
without the masters, and the masters (oneloopmaster); TIRust: its tensor
moments and contraction, and its master integrals only where a profiled arm
recorded them), glue; one colour per stage in the whole report. Table 2's
records carry the instrumented run's stages verbatim
(`retime_unchecked.py` `_stage_split`) and the builder groups them as
Table 1's.

**Main-configuration rule** (`MAIN_RULE`, `Recency`): every Table 1 cell
(generation, validation, full colour, leading colour) shows the most recent
configuration that measured it: the development side of a G1 campaign (G1:
Table 1's gate timing campaign, `g1.json`; gate `--meta native_revision`,
`native_commit`), its integrated side (`slice_revision`), the
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
measured cells of both tables (`report_meta`, by the recorded ancestry);
`meta.report.provenance` the code the numbers come from, printed once on
page 1 (`milestone.json` `provenance`, hand-maintained with its source: the
shipped commit and its dependency revisions, the commit the times were
measured at with its own, the paired timing check that ties the two, and the
cells kept at an older measurement with their dates).

**Loop-induced table** (`build_loop_induced`): the row registry
`milestone.json` `loop_induced` (every process row of the loop-induced validation set by
multiplicity group, ids, gate class, references, `served_by`, `landed`),
checked against the provider manifest `tools/loop_reference/li_campaign.json`;
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
`native_digest` (the provenance line) and, optionally, the gate
tool's fields: `date`, `core`, `blocks`, `stages_per_point`, `served_points`
(a failed call's time on its served points), `tir_counts_last_block` and
`gate` `{status, ratio_to_limit, band, ...}`, written by `python -m
tools.loop_benchmark gate --li-timing`); the
providers' production timing records the manifest names (below
`tests/fixtures/loop/`, MadLoop at its loop-induced card `MLReductionLib
7|6|1` only, their `host` in the provenance line; a provider whose record
has `values_excluded` is timed and shown but no matched provider: never the
fastest matched one or a limit, the multiplier to it beside the cell); `data/lit.json`
(the validation figures: written by `python tools/loop_benchmark/li_manifest.py lit
--records <run records> ...` from the validation run records, its rules and the
checks that are not run or not applicable in
`tests/fixtures/loop/required/li/lit-val/spec/campaign.json`; there is no
separate builder script, `build_summary.py` reads it directly). A registry
row may declare `untimed` (the reason; the EFT execution check without a
reference): its cells print "not timed" with it. An
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
| `milestone.json` | hand-maintained registry, each block with its `source`: engine revision and native build, `ancestry`, `development`, `gate_decisions` (gate decisions, `gate_batch`, `threshold_rule`), `validation_decisions`, `status_notes`, `pending`, `cell_notes`, `loop_induced` | through the summaries |
| `backends-born.json` | Table 3's Born-interfered rows: TIRust and NinjaRS through the public API with `reduction_unchecked = True` on Table 1's 2 → 3 / 2 → 4 rows (time, stages, the largest TIRust-vs-NinjaRS difference at the timed points), written by the final timing; absent: those cells print "not timed" | through `summary-li.json` |
| `measured.json` | development records (`scripts/collect_milestone.py`): required-set native validations, provider reference runs, NJet timings | through `summary.json` |
| `2to6.json` | the 2 → 6 records (`scripts/build_2to6.py`): Table 1's `preliminary` rows | through `summary.json` |
| `mqcd*.json`, `msm*.json` (other than `msm-g1*`), `dec*.json`, `hc.json`, `corr.json` | the QCD, electroweak and decay validation campaigns and their matrices (`scripts/build_mqcd.py`, `build_mqcd_matrix.py`, `build_msm_matrix.py`, `build_dec_matrix.py`, `build_hc.py`, `build_corr.py`), the HC_NLO_X0 and Recola correlation rows | no (campaign records) |
| `rounds-7leg.json`, `measurements.json`, `provider-cold.json`, `legacy-labels.json`, `colour-measurements.json` | the seven-leg optimisation rounds, the legacy engine's timings and labels (`measurements.json` and `colour-measurements.json` are cited by `docs/development/loop_v2/DESIGN.md`) | no (records) |

## Regenerate

- `g1.json`, `g1-values.json`: `python -m tools.loop_benchmark pyamplicol
  <process>`, `… providers <process>`, `… stability <process>` on pinned idle
  cores, then `… gate <records> --json data/g1.json --values-json
  data/g1-values.json --reference-root ROOT --meta date=… slice_revision=…
  slice_lc_revision=… slice_build=… slice_native_digest=…` (the module
  docstrings of `tools/loop_benchmark` give the protocol).
- `msm-g1.json`, `msm-g1-values.json`: the same `gate` over the EW records with
  `--host-spread <g1.json host_provider_spread>`.
- `measured.json`: `python scripts/collect_milestone.py <workspace>`.
- `2to6.json`: `python3 -I scripts/build_2to6.py json …` from the 2 → 6 run
  records (see its docstring).
- `data/li-timing.json`: `retime_unchecked.py collect` (below), in the record
  format above.
- the campaign files: their builders' docstrings.
- then `python scripts/build_summary.py` and `typst compile benchmarks.typ
  benchmarks.pdf`.

## Unchecked Table 2

Tables 2 and 3 are timed with the unchecked reduction setting: both backends
without their own acceptance or refusal checks, pyAmpliCol's checks off,
through public options only. The setting is off by default and has no
accuracy guarantee; a default call does not get these times. (With `on_failure="best-effort"`, the default, a
point that no backend accepts is returned with status `best-effort`, its
unchecked value and an uncertainty where the unchecked re-evaluation gives a
value, and stays a failed point without a value otherwise; a runtime loaded
with the unchecked setting has no check left to skip, so its failed points
stay failed under every policy.)

**Replication** (one row, one backend; the headline time is this call alone):

```sh
pyamplicol <card.toml>              # the public generation (the row's run card)
RAYON_NUM_THREADS=1 taskset -c <one idle core> python - <<'PY'
import pyamplicol
from tools.loop_benchmark import streams          # the frozen stream points
stream = streams.load("li_gg_zzg")                # any row of Table 2
points = streams.binary64(stream, 128)            # B = 128 distinct points
mu_r2 = streams.mu_r2(stream, 128)                # their mu_R^2, decimal text
rt = pyamplicol.Runtime.load("<artifact>", reduction_unchecked=True)
result = rt.evaluate(points, mu_r2=mu_r2, poles="none", on_failure="return",
                     reduction="tirust")          # or "ninjars", or "auto"
PY
```

The settings: `Runtime.load(..., reduction_unchecked=True)` (config
`evaluation.reduction_unchecked = true`, CLI `--reduction-unchecked`, C ABI
`rusticol_virtual_set_reduction_unchecked`); `evaluate(..., poles="none",
on_failure="return", reduction="tirust" | "ninjars")`; no `stability_checks`,
no rescue policy; full colour, binary64, one thread. A call with failed points
is timed whole. The measured accuracy per row is
`data/li-unchecked-accuracy.json` (the same call against TIRust at 256 bits;
at a numerical zero, a truth below 2^-52 times the sector's median over the
row's points, the error is absolute over that median; a row without a truth
within its time budget carries the TIRust-vs-NinjaRS difference instead).
`reduction="auto"` with the setting gives TIRust's values bitwise, with no
per-point fallback.

For another process, the master card times the same public evaluation on
both backends (flat points, no providers):

```sh
pyamplicol examples/loop_generate.toml generate --process="..."
pyamplicol examples/loop_generate.toml profile --runtime --reduction-unchecked --batch-size 128
```

**Re-time command** (all rows):

```sh
python tools/loop_benchmark/retime_unchecked.py campaign \
  --checkout <checkout with the staged native> --native <native build dir> \
  --out <scratch dir> --artifacts <scratch dir>/artifacts \
  --cards <dir of <row>/card.toml> [--rows li_gg_zzg ...] [--dry-run]
python tools/loop_benchmark/retime_unchecked.py collect \
  --checkout <this checkout> --native <native build dir> --out <scratch dir> \
  --typst <typst 0.15.1>
```

`campaign` starts one `systemd-run --user` unit per timed row (one physical
core each, its SMT siblings idle), waits (or `--no-wait`) and runs `collect`.
A unit builds the row's artifact through the public `Generator` from its card
(reused when present), runs rounds of the public calls above on every arm
(`tirust`, `ninjars`; `auto` on `--auto-row`) over `--instances` fresh
runtimes created in rotated order, times the providers in their most
optimistic settings (`python -m tools.loop_benchmark providers <row> --protocol
optimistic`) in the same unit on the same core, alternating with pyAmpliCol
between rounds, and then makes the separate instrumented run (`python -m
tools.loop_benchmark pyamplicol <row> --unchecked`: stage shares and the
engine's generation, never the timed call). `collect` writes one
`data/li-timing.json` record per row and backend (`configuration`
`"unchecked"`: the settings, `instance_medians`, `instance_spread`,
`cpu_share`, the paired `providers` with their rounds, `gate` by `gate.py`'s
rules, `stages` of the instrumented run, `generation`, `tir_counts` from a
counters-only read outside the timed calls, `auto_pairing`), then the
summaries and the PDF. The builder takes an unchecked record's paired
providers as the row's provider times. Runtime: rows run in parallel; the
longest (`li_gg_hggg`, 2 rounds) takes about 2 h and up to ~30 GiB (six
runtimes in one process).
