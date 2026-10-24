# Gate-G1 benchmark (`python -m tools.loop_benchmark`)

End-to-end timing of the v2 one-loop engine against MadLoop, Recola and
OpenLoops under the speed-gate protocol (REQUIREMENTS_ADDENDUM D, MASTER_PLAN
§5.8): finite part only, stability checks off, one pinned thread, the same
frozen phase-space points for every tool.

| Module | Role |
|---|---|
| `processes.json` | Process specifications in the required-references format (`tools/loop_reference/required_processes.json`, scheme `qcd` = loop_sm-no_b_mass). |
| `streams.py`, `streams/` | Frozen streams of 128 distinct exact points per process; the first three are the reference campaign's. |
| `pyamplicol_v2.py` | pyAmpliCol v2 through `NativeExecutor.evaluate` (the public v2 runtime's call): generation time and memory, the accuracy check at the campaign points, per-batch timings with the stage split (Python per-point inputs, the native report's stages, master integrals), and `stability` estimates at chosen points. |
| `providers.py` | MadLoop, Recola and OpenLoops in production mode through the toolkit's drivers; optionally MadLoop's stage split from an instrumented copy. |
| `gate.py` | Combines the records into `docs/performance_reports/loop/data/g1.json`: gate verdicts, value comparison, cost-model recalibration. |

Typical campaign (one of our jobs per CCX on cores without SMT siblings; the
host is shared, so others' jobs are not controlled):

```sh
python -m tools.loop_benchmark streams uux_emepgg            # freeze a new stream
python -m tools.loop_benchmark pyamplicol uux_ddxg --batches 1 8 32 128 --reps 3 \
    --native-build BUILD_DIR --json runs/uux_ddxg.json          # integrated slice
python -m tools.loop_benchmark pyamplicol uux_ddxg --inputs native ...   # WP3.1 path
python -m tools.loop_benchmark providers uux_ddxg --cpu 153 --points 16 \
    --work WORK_DIR --reference-root ROOT --json runs/providers-uux_ddxg.json [--madloop-stages]
python -m tools.loop_benchmark stability gg_ggg --points 10 --inputs native \
    --arithmetic double double-double --json runs/stability-gg_ggg.json
python -m tools.loop_benchmark gate runs/*.json --json docs/performance_reports/loop/data/g1.json \
    --values-json docs/performance_reports/loop/data/g1-values.json --reference-root ROOT \
    --meta date=... slice_revision=... native_revision=... native_commit=... slice_build=... native_build=...
python tools/loop_v2_costmodel.py --g1 docs/performance_reports/loop/data/g1.json
```

`ROOT` is the provider reference root (`$LOOP_REFERENCE_ROOT`, toolkit
layout: `sources/MG5_aMC_v3_7_0`, `sources/recola2-2.3.0`,
`sources/OpenLoops-2.1.5`, MadLoop exports at `madloop.export` of
`processes.json`). A new process needs only its specification in
`processes.json` (PDG codes, orders, provider process strings, `madloop.export`
or `unavailable` reasons) and its stream: particle names come from the model,
labels from the specification, and the gate refuses records of unknown
processes. The gate statistic is the median per point on both sides with an
uncertainty band; `open` verdicts are repeated once (MASTER_PLAN §5.8 item 10);
the record given last for a configuration or provider decides, earlier runs
are kept.

Run the `pyamplicol` jobs under `taskset -c N` with `RAYON_NUM_THREADS=1`.
Respect HANDOFF §0.1 for provider generations (no generation expected to
exceed about 45 minutes).
