# Live one-loop report

`benchmarks.pdf` is the rendered report; `benchmarks.typ` is its source.
Build with Typst 0.15.1 from this directory:

```sh
typst compile benchmarks.typ benchmarks.pdf
```

`data/measurements.json` is the measured snapshot used by the tables. It retains
the original complete-call timing samples and the compact native-provider
timing records. Missing stage/provider measurements remain absent rather than
being estimated. Update source, data and PDF together after each milestone.

The first snapshot is a development control run on 2026-10-18. It uses repeated
three-point physical fixtures, includes Python batch scheduling and exact input
ingress on the pyAmpliCol side, and has different provider rescue policies.
It is not the distinct-point, native-interface performance acceptance campaign.
Generation, first evaluation, warmed totals and instrumented component clocks
have separate definitions in the report. Test durations are not event timings.

Architecture notes are updated through the retained model-plan checkpoint
`7290ec92` and explicit Gmu helper convention `146f6d8a`. The tables and their
measurement revision remain unchanged. The pulled generic-any-n NinjaRS
extension is described as a consumer candidate until its validation and
staged-module adoption finish.

The summary tables follow the NinjaRS benchmark's value/reference/multiplier
layout. Heat-map ratios use the fastest available original-binary provider
median for the same process and batch width, computed from the retained data.
Generation and instrumented components stay neutral because their reference
boundaries are not matched. Full numeric observations and samples remain in
the JSON; display values are rounded for readability. Input and rescue-policy
asymmetries still prevent treating these ratios as performance acceptance.

The original measurement drivers and full provider logs are retained in the
task workspace as `experiments/loop_live_benchmark.py`,
`experiments/loop_live_stages.py`,
`reference/live_provider_benchmark.py`, `reports/loop-live-benchmark/`, and
`reports/loop-live-provider-benchmark/`. Frozen physical input fixtures and the
reusable native reference harness are in the repository's `tools/loop_reference/`.
