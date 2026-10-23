# pyAmpliCol one-loop report

`benchmarks.typ` is the source of the live report `benchmarks.pdf`: the
milestone status of the `loop` branch, the performance-gate policy and status,
measured generation and runtime (development measurements kept apart from the
acceptance campaign), the seven-gluon comparison with NJet, the capability
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
| `milestone.json` | Hand-maintained registry, each block with its source: integrated packages at the pinned engine revision, provider generation times and the 45-minute rule (HANDOFF §0.1), provider production timings for the gate (DESIGN §1.3), the required-set generation and validation rows (DESIGN WP3.1 status), native loop-stage timings (DESIGN §5.5, §5.6), NJet Table 5 and the re-measured NJet timings (`njet-benchmark.md`), NJet validation figures. |
| `measured.json` | Seven-gluon development records (generation, counterterm program, native bare loop, first virtual and its rotation, u u~ > g g g g g against MadLoop/Recola), written by `scripts/collect_milestone.py`. |
| `measurements.json`, `provider-cold.json`, `legacy-labels.json` | The legacy per-diagram engine's timing snapshot of 2026-10-18 (unchanged, cited by `docs/development/loop_v2/DESIGN.md`) and its labels, shown only as history. |
| `colour-measurements.json` | The legacy engine's LC/FC runs; not shown, kept for the citations in DESIGN.md and `research-leading-colour-structure.md`. |

Missing observations stay absent; the report prints an explicit marker
instead of estimating them. Test durations are never used as event timings,
and development measurements are labelled with their branch.

## Regenerate

- `measured.json`: `python scripts/collect_milestone.py <workspace>` reads the
  run records under `<workspace>/tmp/generation-scale/runs/` and
  `<workspace>/tmp/ct-recursion/s4/` (JSON and `/usr/bin/time` logs: wall
  time, peak memory, CPU share).
- `milestone.json` is edited by hand when a package lands or a measurement is
  replaced; keep each block's `source`.
- `figures/*.svg`: `python scripts/draw_graphs.py` draws example graphs with
  FeynKit's renderer (needs the Community HEPKit module and the
  `symbolica-fonts` bundle; set `SYMBOLICA_DATA_DIRECTORY` to its `fonts`
  directory when loading Symbolica from an overlay).

Data the report no longer uses and nothing cites (the legacy status registry,
provider audit and seven-leg stage log) are kept outside the repository in
`workspace/reports/report-data-archive/`.
