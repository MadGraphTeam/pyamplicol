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

Typical campaign (one idle core per job, one job per CCX; the host is shared):

```sh
python -m tools.loop_benchmark pyamplicol uux_ddxg --batches 1 8 32 128 --reps 3 \
    --native-build BUILD_DIR --json runs/uux_ddxg.json          # integrated slice
python -m tools.loop_benchmark pyamplicol uux_ddxg --inputs native ...   # WP3.1 path
python -m tools.loop_benchmark providers uux_ddxg --cpu 153 --points 16 \
    --work WORK_DIR --json runs/providers-uux_ddxg.json [--madloop-stages]
python -m tools.loop_benchmark gate runs/*.json --json docs/performance_reports/loop/data/g1.json \
    --meta date=... slice_revision=... native_revision=... slice_build=... native_build=...
python tools/loop_v2_costmodel.py --g1 docs/performance_reports/loop/data/g1.json
```

Run the `pyamplicol` jobs under `taskset -c N` with `RAYON_NUM_THREADS=1`.
Respect HANDOFF §0.1 for provider generations (no generation expected to
exceed about 45 minutes).
