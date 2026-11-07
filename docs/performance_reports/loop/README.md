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
| `<fig:gate>` | **Figure 1**, Table 1's batched full-colour times against the providers and the gate limit (log scale) | the only view of how far each row is from its limit |
| `<tab:gate>` | **Table 3**, gate and stage split at B = 128: limit, binding provider, band, chip, ms per stage | the numbers behind Table 1's gate chips and stage bars (the table view of Figure 1 and of the bars) |
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
  (production mode), coloured green (faster) → white → red (slower) on a log₂
  scale clamped at ×1/16 and ×16; every coloured cell prints its multiplier;
- generation time and memory uncoloured (the multiplier as text), leading
  colour without a provider ratio;
- explicit grey markers for every missing value, with the reason; nothing is
  estimated or extrapolated;
- gate chips (time ÷ the smallest of MadLoop's time and 1.30 × each of
  OpenLoops' and Recola's): pass or fail when the whole uncertainty band lies
  on one side of 1, else open; taken at B = 128 only (user 2026-10-28);
  below 5 ms per point not gated (user 2026-10-24); 2 → 2 not gated;
- Table 2: the default backend TIRust, NinjaRS per amplitude labelled where TIR
  does not serve the row yet; generation is the full production `generate`
  cost, the mandatory generation-time probes included (their share shown);
  rows of four legs or fewer reported without a gate; *pending* where the serving package has not landed or the input file
  does not exist yet, *not run* for a landed package without a record.

## Build

```sh
cd docs/performance_reports/loop
python scripts/build_summary.py                  # data/summary.json, data/summary-li.json
typst compile benchmarks.typ benchmarks.pdf      # Typst 0.15
```

Update source, data and PDF together at each milestone push.

## Data

`scripts/build_summary.py` writes `data/summary.json` (Table 1, Figure 1,
Table 3) and `data/summary-li.json` (Table 2) from the campaign records below;
never edit either by hand. Every value names its `source`.

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
`backend` `tirust` or `ninjars`, `batch`, `seconds_per_point`, `host`,
`generation` `{seconds` (generate + plan export), `probes_seconds` (the
generation-time probes), `peak_gib` (over the three), `plan_mb}`; the cell is
their sum, a record without `probes_seconds` is "not recorded"), `source`,
optional `native_build`,
`native_digest` (the provenance line) and, from `lit-perf` on, `gate`); the
providers' production timing records the manifest names (below
`tests/fixtures/loop/`, MadLoop at its loop-induced card `MLReductionLib
7|6|1` only, their `host` in the provenance line); `data/lit.json`
(`lit-val`'s validation figures). An absent file reads as pending. The cell
takes the newest revision's B = 128 record, the default backend first; one
record per backend, batch and revision.

| File | Content | Printed |
|---|---|---|
| `summary.json`, `summary-li.json` | the report's data (above) | yes |
| `g1.json`, `g1-values.json` | the G1 campaign: providers' production-mode times, pyAmpliCol configurations per batch with stages, uncertainty and gate verdicts, value comparisons, stability rows (`python -m tools.loop_benchmark gate`); the per-point values behind it | through `summary.json` (newest configuration only) |
| `msm-g1.json`, `msm-g1-values.json` | the electroweak G1 row, the same gate tool; joined to `g1.json`'s integrated configuration when both timed the same engine | through `summary.json` |
| `milestone.json` | hand-maintained registry, each block with its `source`: engine revision and native build, `ancestry`, `development`, `gate_decisions` (user decisions, `gate_batch`, `threshold_rule`), `validation_decisions`, `status_notes`, `pending`, `cell_notes`, `loop_induced` | through the summaries |
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
- `data/li-timing.json`: written by the loop-induced timing packages
  (`lit-amp`, `lit-r2`, `lit-ew`, `lit-perf`) in the record format above.
- the campaign files: their builders' docstrings.
- then `python scripts/build_summary.py` and `typst compile benchmarks.typ
  benchmarks.pdf`.
