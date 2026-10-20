# pyAmpliCol one-loop report

`benchmarks.typ` is the source of the live report `benchmarks.pdf`. It is the
steering document for the one-loop work: required-process status, measured
runtime and generation cost, and the architecture of the current engine.

## Build

```sh
cd docs/performance_reports/loop
typst compile benchmarks.typ benchmarks.pdf      # Typst 0.15
```

Commit the PDF when the data or a milestone changes, not for every prose edit.

## Data

Every number in the report is read from `data/*.json`, except the cited
architecture evidence (probe and stack-sample values in the scaling-walls
table), whose source the report names.

| File | Content |
|---|---|
| `measurements.json` | Timed processes: generation time, peak RSS, warm samples (µs per point, median/min/max) per batch, instrumented stage samples (`stages`), provider references with MadLoop stage clocks (`references`), protocol notes. |
| `provider-cold.json` | MadLoop export and compilation, Recola generation and OpenLoops setup times. |
| `colour-measurements.json` | Matched leading-colour and full-colour runs (warm samples and stages). |
| `provider-audit.json` | Recola Drell–Yan observation and the OpenLoops build/settings audit; used for the run-to-run drift note. |
| `processes.json` | Status registry: required 2→5 processes, the seven-leg control and the validated but untimed processes, with sources. Labels and notes are Typst markup. |
| `generation.json` | Generation observations outside the timing snapshot: cold generation from correctness runs and the seven-leg stage timeline. |

Missing observations stay absent; the report prints an explicit marker
instead of estimating them. Correctness-run durations are never used as event
timings.

## Regenerate

- Timings: the drivers that produced `measurements.json`,
  `provider-cold.json` and `colour-measurements.json` are not yet in the
  repository (`workspace/experiments/loop_live_*.py`,
  `workspace/reference/live_provider_benchmark.py`). Retime once, after the
  engine redesign, with the plan's timing protocol.
- `generation.json`: `python scripts/collect_generation.py <workspace>/reports`
  reads the retained correctness-run records and the seven-leg stage log.
- `figures/*.svg`: `python scripts/draw_graphs.py` draws example graphs with
  FeynKit's renderer (needs the Community HEPKit module and the
  `symbolica-fonts` bundle; set `SYMBOLICA_DATA_DIRECTORY` to its `fonts`
  directory when loading Symbolica from an overlay).
- `processes.json` is edited by hand when a process changes status.

Experiment-only data that the report no longer uses are kept outside the
repository in `workspace/reports/report-data-archive/`.
