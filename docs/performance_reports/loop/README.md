# pyAmpliCol one-loop report

`benchmarks.typ` is the source of the live report `benchmarks.pdf`. It opens
with **Table 1, "State of the one-loop engine"** (summary first, user request
of 2026-10-24): one row per test process by multiplicity, with generation
cost, batched full-colour and leading-colour time per point against the
fastest provider, the gate-G1 verdict, stage shares and the validation line,
followed by its legend and Figure 1 (the batched full-colour times against
the gate limits on a log scale). Then a status page (what is on `loop`, the
gate, what is in development or missing, the timing protocol), the gate-G1
details (provider grid with B = 1 and the largest batch, gate bands, stage
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

| File | Content |
|---|---|
| `summary.json` | The data of Table 1 and Figure 1, written by `scripts/build_summary.py` from `g1.json`, `measured.json`, `milestone.json` and `tools/loop_benchmark/processes.json`. Per row (grouped by multiplicity, then by number of gluons): process, legs, corrections, loop families; the validation (largest finite-part deviation per reference, points, median, whether the worst point lies within pyAmpliCol's own binary64 estimate); generation (`main` = the integrated configuration, `dev` = the WP3.1 native-input configuration or the newest older record with its revision and a note; provider generation times and the fastest; ratios); full colour (`main`/`dev` at the largest batch > 1 with median, uncertainty, stage shares, gate verdict and ratio to the fastest provider; refused, not batched or not measured otherwise; the providers' production times; for the seven-leg rows the provider references of DESIGN Table 1b as text and, without a matched provider, NJet as an unmatched alternative); leading colour (`main`/`dev`, LC/FC). Every entry names its `source`; a value without a record is `null` or a status, never an estimate. |
| `g1.json` | The gate-G1 campaign: per process the providers' production-mode times (median and mean per point, repeats, setup, MadLoop's stage split; a provider without a library or export keeps the reason), every pyAmpliCol configuration (integrated slice, native inputs, LC, schedule M, one lane; a refused generation keeps its error) per batch with its stage split, counts, throughput, uncertainty and gate verdict (pass, fail or open from the band), schedule M against B, the value comparison with the providers, binary64 and double-double values at the worst points, the cost-model terms and the G1-recalibrated design estimates. Written by `python -m tools.loop_benchmark gate` (see `tools/loop_benchmark`). |
| `g1-values.json` | The per-point values behind `g1.json`: pyAmpliCol's Born and finite part per configuration and stream point, and every provider run's per-point Born, finite part (Recola's raw finite part too) and time, from which the value comparison and the provider statistics can be re-derived. |
| `milestone.json` | Hand-maintained registry, each block with its source: integrated packages at the pinned engine revision and the commits after the last integration, provider generation times and the 45-minute rule (HANDOFF §0.1), provider production timings of the seven-leg gates (DESIGN §1.3), the required-set generation and validation rows (DESIGN WP3.1 status), NJet Table 5 and the re-measured NJet timings (`njet-benchmark.md`), NJet validation figures, and `status_notes`: the short refusal and status attributions Table 1 prints (no numbers). |
| `measured.json` | Development records written by `scripts/collect_milestone.py`: the seven-gluon records of 23 October (generation, counterterm program, native bare loop, first virtual and its rotation, u u~ > g g g g g against MadLoop/Recola); `required_native`, the WP3.1 native validations of the required set (DESIGN WP3.1 eighth increment: generation and export cost, largest deviation per reference and coefficient, per-point estimates and single-point evaluation times); `provider_generation`, the provider reference runs' generation records of the seven-leg rows (MadLoop export, Recola generation or its unfinished status, the OpenLoops library). |
| `measurements.json`, `provider-cold.json`, `legacy-labels.json` | The legacy per-diagram engine's timing snapshot of 2026-10-18 (unchanged, cited by `docs/development/loop_v2/DESIGN.md`) and its labels; no longer shown (the history table is in the report revisions up to `ba7d510d`). |
| `colour-measurements.json` | The legacy engine's LC/FC runs; not shown, kept for the citations in DESIGN.md and `research-leading-colour-structure.md`. |

Missing observations stay absent; the report prints an explicit marker
instead of estimating them. Test durations are never used as event timings,
and development measurements are labelled with their branch.

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
  campaign are archived in `workspace/reports/engine-v2/measure-g1/records/`.

- `measured.json`: `python scripts/collect_milestone.py <workspace>` reads the
  run records under `<workspace>/tmp/generation-scale/runs/` and
  `<workspace>/tmp/ct-recursion/s4/` (JSON and `/usr/bin/time` logs: wall,
  user and system time, peak memory, CPU share), the WP3.1 native validations
  under `<workspace>/tmp/generation-scale/gint/val1/` and `val2/` and the
  provider reference runs under `<workspace>/reference/runs/required/`.
- `summary.json`: `python scripts/build_summary.py` after any of the files
  above changed, then recompile. At the next milestone (G-int integrated, G1
  re-measured on the integrated configuration) the regenerated `g1.json` makes
  the native-input numbers the main values; the seven-leg G1 rows
  (`measure-g1-7leg`) fill the 2 → 5 cells the same way. Keep the
  `status_notes` of `milestone.json` current (they explain grey cells).
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
