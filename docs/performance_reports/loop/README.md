# pyAmpliCol one-loop report

`benchmarks.typ` is the source of the live report `benchmarks.pdf`: the
milestone status, the performance gates and the gate-G1 measurement of the v2
engine against MadLoop, Recola and OpenLoops (end-to-end timings, stage split,
leading colour, throughput and recalibration, schedule B against M, levers),
the required processes, the seven-gluon comparison with NJet, the capability
matrix and the architecture of the recursive v2 engine.

## Build

```sh
cd docs/performance_reports/loop
typst compile benchmarks.typ benchmarks.pdf      # Typst 0.15
```

Update source and PDF together at each milestone push to `loop`.

## Data

Table values are read from `data/*.json`; numbers quoted in prose name their
source in the report's last section.

| File | Content |
|---|---|
| `g1.json` | The gate-G1 campaign: per process the providers' production-mode times (and MadLoop's stage split), every pyAmpliCol configuration (integrated slice, native inputs, LC, schedule M, one lane) per batch with its stage split, counts, throughput and gate verdict, the value comparison with the providers, stability estimates at the worst points and the cost-model recalibration. Written by `python -m tools.loop_benchmark gate` (see `tools/loop_benchmark`). |
| `milestone.json` | Hand-maintained registry, each block with its source: integrated packages at the pinned engine revision and the commits after the last integration, provider generation times and the 45-minute rule (HANDOFF §0.1), provider production timings for the gate (DESIGN §1.3), the required-set generation and validation rows (DESIGN WP3.1 status), native loop-stage timings (DESIGN §5.5, §5.6), NJet Table 5 and the re-measured NJet timings (`njet-benchmark.md`), NJet validation figures. |
| `measured.json` | Seven-gluon development records (generation, counterterm program, native bare loop, first virtual and its rotation, u u~ > g g g g g against MadLoop/Recola), written by `scripts/collect_milestone.py`. |
| `measurements.json`, `provider-cold.json`, `legacy-labels.json` | The legacy per-diagram engine's timing snapshot of 2026-10-18 (unchanged, cited by `docs/development/loop_v2/DESIGN.md`) and its labels, shown only as history. |
| `colour-measurements.json` | The legacy engine's LC/FC runs; not shown, kept for the citations in DESIGN.md and `research-leading-colour-structure.md`. |

Missing observations stay absent; the report prints an explicit marker
instead of estimating them. Test durations are never used as event timings,
and development measurements are labelled with their branch.

## Regenerate

- `g1.json`: run `python -m tools.loop_benchmark pyamplicol <process>` (options
  `--inputs native`, `--accuracy lc`, `--schedule M`, `--lanes 1`),
  `… providers <process> --cpu N --work DIR [--madloop-stages]` and
  `… stability <process> --points I …` on pinned idle cores, then
  `… gate <records> --json data/g1.json --meta date=… slice_revision=…
  native_revision=… slice_build=… native_build=…` (the report prints these
  labels). The module docstrings of `tools/loop_benchmark` give the protocol.

- `measured.json`: `python scripts/collect_milestone.py <workspace>` reads the
  run records under `<workspace>/tmp/generation-scale/runs/` and
  `<workspace>/tmp/ct-recursion/s4/` (JSON and `/usr/bin/time` logs: wall,
  user and system time, peak memory, CPU share).
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
