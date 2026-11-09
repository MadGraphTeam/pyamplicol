# SPDX-License-Identifier: 0BSD
"""The loop-induced Table 2 re-time in the UNCHECKED setting, one scripted
command (m-lit lit-unchecked (3)-(5); USER 2026-11-08 ~21:14 / ~22:34,
DECISIONS 22:34 (1)).

``python tools/loop_benchmark/retime_unchecked.py campaign --checkout C
--native N --out O [--rows P ...] [--dry-run]`` launches one systemd unit
per row (``row``), each pinned to its own idle core, waits for them, then
``collect``s: the records go into ``docs/performance_reports/loop/data/
li-timing.json`` and the summaries and ``benchmarks.pdf`` are rebuilt.
``--dry-run`` prints the units and commands and launches nothing.

**Headline times (public API, documented settings only).** Per row, in one
process on one pinned core: ``Runtime.load(<artifact>,
reduction_unchecked=True)`` (the public loader; the artifact from the public
generation) and ``evaluate(<the 128 distinct stream points as binary64
texts>, mu_r2=<their mu_R^2>, poles="none", reduction=<"tirust" |
"ninjars">)`` on the whole batch (B = 128): no stability checks, no rescue
policy, full colour, one thread (``RAYON_NUM_THREADS=1``). Nothing else
runs in the timed call: no stage timer, no harness hook, no executor
internal. EXECUTOR-INSTANCE CONTROL (A-unchecked.md §3.1): each arm runs on
``--instances`` fresh runtimes (``Runtime.load`` each), created in rotated
order, and every round times every (arm, instance) once in a rotated order;
the cell is the median over instances of each instance's median over rounds,
and the per-instance medians and their spread are recorded. ``--auto-row``
adds, on that row only, the ``"auto"`` arm (the default backend choice) with
the same setting, paired with the TIRust arm: its values must equal the
TIRust arm's bitwise, with no per-point fallback.

**Providers, paired.** The F4 most optimistic providers (lit-perf's
``python -m tools.loop_benchmark providers <row> --protocol optimistic``,
as landed) run in the same unit on the same core, back-to-back with the
pyAmpliCol arms, the order of the two blocks alternating between rounds
(the provider tool is a separate process: it cannot be interleaved per
call). A provider the tool cannot run on a row is listed, never filled.

**Stage bars (separate instrumented run).** After the timed rounds, the unit
runs lit-perf's instrumented harness (``python -m tools.loop_benchmark
pyamplicol <row> --reduction tirust ninjars --unchecked --batches 128``,
the native stage report) on the same core: the stage split (trees + CT
kets, dressing, scatter, reduction, rest) of a run of its own, labelled
'instrumented run: stage shares, not the timed call', and the engine's
generation time (generation without the validation probes).

``row`` and ``collect`` are the campaign's own steps (``row`` runs inside its
unit). Records: ``--out``/rows/<process>.json (timed arms, instances,
providers), ``--out``/stages/<process>.json (the instrumented run).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import statistics
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable
LI_TIMING = Path("docs/performance_reports/loop/data/li-timing.json")
# The configuration the headline times are measured in: every public setting
# and its value (the report's protocol line reads it).
SETTINGS = {
    "Runtime.load": {"reduction_unchecked": True},
    "evaluate": {"poles": "none", "on_failure": "return"},
    "arms": {"tirust": {"reduction": "tirust"}, "ninjars": {"reduction": "ninjars"}},
    "auto arm": {"reduction": "auto (the default backend choice)"},
    "points": "the 128 distinct stream points (tools/loop_benchmark/streams/"
    "<row>.json) as binary64 texts, mu_r2 their stream mu_R^2; B = 128 (one call)",
    "environment": {
        "RAYON_NUM_THREADS": "1",
        "pinned": "taskset -c <one idle core>",
    },
}
STAGES = ("trees + CT kets", "dressing", "scatter", "reduction")
LABEL = "instrumented run: stage shares, not the timed call"


# ------------------------------------------------------------------- rows


def _li_timing(checkout: Path) -> dict[str, Any]:
    return json.loads((checkout / LI_TIMING).read_text())


def timed_rows(checkout: Path) -> list[tuple[str, str]]:
    """The loop-induced rows lit-perf times (its checked records,
    ``tir_options`` "shipped"), as (stream process, record key), in record
    order; the process is the one each record's source names."""

    found: dict[str, str] = {}
    for record in _li_timing(checkout)["records"]:
        if record.get("tir_options") != "shipped":
            continue
        match = re.search(r"process (li_[a-z0-9_]+)", record.get("source", ""))
        if match and match.group(1) not in found:
            found[match.group(1)] = record["key"]
    return list(found.items())


def idle_cores(count: int, exclude: set[int]) -> list[int]:
    """``count`` cores with the least busy time over a one-second sample
    (``/proc/stat``), physical siblings of a chosen core skipped where the
    topology says so."""

    def sample() -> dict[int, tuple[int, int]]:
        out = {}
        for line in Path("/proc/stat").read_text().splitlines():
            if line.startswith("cpu") and line[3:4].isdigit():
                name, *fields = line.split()
                values = [int(v) for v in fields]
                idle = values[3] + values[4]
                out[int(name[3:])] = (sum(values), idle)
        return out

    first = sample()
    time.sleep(1.0)
    second = sample()
    busy = []
    for cpu, (total, idle) in second.items():
        dt = total - first[cpu][0]
        di = idle - first[cpu][1]
        busy.append(((dt - di) / dt if dt else 1.0, cpu))
    chosen: list[int] = []
    taken = set(exclude)
    for _load, cpu in sorted(busy):
        if cpu in taken:
            continue
        siblings = Path(
            f"/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list"
        )
        group = {cpu}
        if siblings.is_file():
            for part in siblings.read_text().strip().split(","):
                lo, _, hi = part.partition("-")
                group.update(range(int(lo), int(hi or lo) + 1))
        if group & taken:
            continue
        chosen.append(cpu)
        taken |= group
        if len(chosen) == count:
            break
    return chosen


# ------------------------------------------------------------- campaign


def unit_command(options: Any, process: str, core: int) -> list[str]:
    """The ``systemd-run`` command of one row's unit (the licence is read
    inside the unit's command, never a unit property or a file)."""

    out = Path(options.out)
    inner = [
        "source",
        str(options.env),
        "&&",
        "source",
        str(options.reference_env),
        "&&",
        "export",
        "SYMBOLICA_LICENSE=$(grep -o 'S-130-2027[A-Z0-9.-]*' "
        f"{shlex.quote(str(options.licence_file))} | head -1)",
        "RAYON_NUM_THREADS=1",
        f"LOOP_REFERENCE_ROOT={shlex.quote(str(options.reference_root))}",
        f"PYTHONPATH={shlex.quote(options.pythonpath)}",
        "&&",
        "cd",
        shlex.quote(str(options.checkout)),
        "&&",
        "taskset",
        "-c",
        str(core),
        shlex.quote(PYTHON),
        "tools/loop_benchmark/retime_unchecked.py",
        "row",
        process,
        "--checkout",
        shlex.quote(str(options.checkout)),
        "--native",
        shlex.quote(str(options.native)),
        "--out",
        shlex.quote(str(out)),
        "--artifacts",
        shlex.quote(str(options.artifacts)),
        "--core",
        str(core),
        "--rounds",
        str(options.rounds),
        "--instances",
        str(options.instances),
        "--provider-points",
        str(options.provider_points),
    ]
    if options.auto_row == process:
        inner.append("--auto")
    if not options.providers:
        inner.append("--no-providers")
    if not options.stages:
        inner.append("--no-stages")
    log = out / "logs" / f"{process}.log"
    done = out / "logs" / f"{process}.DONE"
    shell = (
        " ".join(inner)
        + f" > {shlex.quote(str(log))} 2>&1; echo rc=$? > {shlex.quote(str(done))}"
    )
    return [
        "systemd-run",
        "--user",
        f"--unit=lit-retime-{options.tag}-{process.replace('_', '-')}",
        "--collect",
        f"-p MemoryMax={options.memory_max}",
        "bash",
        "-c",
        shell,
    ]


def campaign(options: Any) -> int:
    checkout = Path(options.checkout)
    rows = [(p, p) for p in options.rows] if options.rows else timed_rows(checkout)
    rows = [row for row in rows if row[0] not in set(options.skip or ())]
    cores = (
        list(range(len(rows)))
        if options.dry_run
        else idle_cores(len(rows), set(options.exclude_cores or ()))
    )
    if len(cores) < len(rows):
        print(f"only {len(cores)} idle cores for {len(rows)} rows", file=sys.stderr)
        return 2
    out = Path(options.out)
    plan = [
        {"process": p, "key": k, "core": c, "command": unit_command(options, p, c)}
        for (p, k), c in zip(rows, cores, strict=True)
    ]
    collect_command = [
        PYTHON,
        "tools/loop_benchmark/retime_unchecked.py",
        "collect",
        "--checkout",
        str(checkout),
        "--native",
        str(options.native),
        "--out",
        str(out),
    ]
    if options.dry_run:
        for entry in plan:
            process, key, core = entry["process"], entry["key"], entry["core"]
            print(f"# {process} (record key {key}), core {core}")
            print(shlex.join(entry["command"]))
        print("# then, when every unit's DONE marker exists:")
        print(shlex.join(collect_command))
        return 0
    (out / "logs").mkdir(parents=True, exist_ok=True)
    (out / "plan.json").write_text(json.dumps(plan, indent=1))
    for entry in plan:
        subprocess.run(entry["command"], check=True)
    pending = {entry["process"] for entry in plan}
    deadline = time.time() + options.wait_hours * 3600
    while pending and time.time() < deadline:
        time.sleep(30)
        pending = {p for p in pending if not (out / "logs" / f"{p}.DONE").is_file()}
    if pending:
        print(
            f"units still running: {sorted(pending)}; rerun 'collect'", file=sys.stderr
        )
        return 3
    return subprocess.run(collect_command, check=False, cwd=checkout).returncode


# ------------------------------------------------------------------ row


def _stream(process: str) -> tuple[list, list]:
    sys.path.insert(0, str(ROOT))
    from tools.loop_benchmark import streams

    stream = streams.load(process)
    count = len(stream["points"])
    points = streams.binary64(stream, count)
    scales = [str(Fraction(m) ** 2) for m in stream["mu_r"][:count]]
    return points, scales


def _rotated(items: list, by: int) -> list:
    by %= max(len(items), 1)
    return items[by:] + items[:by]


def row(options: Any) -> int:
    import platform

    from pyamplicol import Runtime

    process = options.process
    out = Path(options.out)
    (out / "rows").mkdir(parents=True, exist_ok=True)
    artifact = Path(options.artifacts) / process / "artifact"
    points, scales = _stream(process)
    arms = ["tirust", "ninjars"] + (["auto"] if options.auto else [])
    kwargs = {arm: {} if arm == "auto" else {"reduction": arm} for arm in arms}
    record: dict[str, Any] = {
        "process": process,
        "artifact": str(artifact),
        "settings": SETTINGS,
        "host": platform.node(),
        "date": time.strftime("%Y-%m-%d", time.gmtime()),
        "core": options.core,
        "batch": len(points),
        "rounds": options.rounds,
        "instances": options.instances,
        "native": str(options.native),
    }
    # Fresh runtimes, created in rotated arm order (the executor-instance
    # control): instance i of every arm, then i + 1.
    runtimes: dict[tuple[str, int], Any] = {}
    load_seconds: dict[str, list[float]] = {arm: [] for arm in arms}
    for i in range(options.instances):
        for arm in _rotated(arms, i):
            begin = time.perf_counter()
            runtimes[arm, i] = Runtime.load(artifact, reduction_unchecked=True)
            load_seconds[arm].append(time.perf_counter() - begin)
    record["load_seconds"] = load_seconds

    def call(arm: str, i: int) -> tuple[float, Any]:
        begin = time.perf_counter()
        result = runtimes[arm, i].evaluate(
            points, mu_r2=scales, poles="none", on_failure="return", **kwargs[arm]
        )
        return time.perf_counter() - begin, result

    # Untimed warm-up of every instance (kernels compiled, caches built).
    first: dict[str, Any] = {}
    for arm, i in runtimes:
        _seconds, result = call(arm, i)
        first.setdefault(arm, result)
    for arm, result in first.items():
        lanes = result.diagnostics
        reductions = [lane.reduction for lane in lanes]
        call_record = reductions[0]
        record.setdefault("arms", {})[arm] = {
            "requested": call_record.requested,
            "effective": call_record.effective,
            "reason": call_record.reason,
            "unchecked": call_record.unchecked,
            "fallback": call_record.fallback,
            "failed_points": sum(v is None for v in result.values),
            "failures": {
                str(p): [f.detail for f in lane.failures]
                for p, lane in enumerate(lanes)
                if result.values[p] is None
            },
            "fallback_points": sum(
                1
                for r in reductions
                if r is not None and r.effective != call_record.effective
            ),
        }
    if "auto" in first:
        record["auto_bitwise_tirust"] = repr(first["auto"].values) == repr(
            first["tirust"].values
        )
    seconds: dict[str, dict[int, list[float]]] = {
        arm: {i: [] for i in range(options.instances)} for arm in arms
    }
    providers: list[dict[str, Any]] = []
    order = [(arm, i) for i in range(options.instances) for arm in arms]
    for r in range(options.rounds):
        blocks = (
            ["pyamplicol", "providers"] if r % 2 == 0 else ["providers", "pyamplicol"]
        )
        for block in blocks:
            if block == "providers":
                if options.providers:
                    providers.append(_providers(options, r))
                continue
            for arm, i in _rotated(order, r):
                elapsed, _result = call(arm, i)
                seconds[arm][i].append(elapsed / len(points))
    record["seconds_per_point"] = {
        arm: {str(i): values for i, values in per.items()}
        for arm, per in seconds.items()
    }
    cells = {}
    for arm, per in seconds.items():
        medians = [statistics.median(v) for v in per.values() if v]
        cells[arm] = {
            "median": statistics.median(medians),
            "instance_medians": medians,
            "instance_spread": max(medians) / min(medians)
            if min(medians) > 0
            else None,
            "round_spread": [max(v) / min(v) for v in per.values() if v and min(v) > 0],
        }
    record["cells"] = cells
    record["providers"] = providers
    # Counters-only read (untimed): TIRust's rows per served class.
    counts_runtime = runtimes["tirust", 0]
    counts_runtime.evaluate(
        points, mu_r2=scales, poles="none", on_failure="return", reduction="tirust"
    )
    counts = dict(counts_runtime._backend._executor.last_report["counts"])
    record["tir_counts"] = {
        name: counts.get(name, 0)
        for name in (
            "tensor moment rows",
            "TIR gate refusals",
            "TIR method-choice rows",
            "TIR last-resort rows",
            "TIR method-choice check rows",
            "TIR method-choice lanes refused by their check",
        )
    }
    (out / "rows" / f"{process}.json").write_text(json.dumps(record, indent=1))
    if options.stages:
        _stages(options)
    return 0


def _providers(options: Any, round_: int) -> dict[str, Any]:
    """One F4 most-optimistic provider run of the row on this core (lit-perf's
    provider tool as landed)."""

    out = Path(options.out) / "providers"
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{options.process}-r{round_}.json"
    command = [
        PYTHON,
        "-m",
        "tools.loop_benchmark",
        "providers",
        options.process,
        "--protocol",
        "optimistic",
        "--cpu",
        str(options.core),
        "--points",
        str(options.provider_points),
        "--work",
        str(out / "work" / f"{options.process}-r{round_}"),
        "--json",
        str(target),
    ]
    begin = time.time()
    done = subprocess.run(
        command, capture_output=True, text=True, check=False, cwd=options.checkout
    )
    entry: dict[str, Any] = {
        "round": round_,
        "command": shlex.join(command),
        "rc": done.returncode,
        "wall_seconds": time.time() - begin,
    }
    if target.is_file():
        found = json.loads(target.read_text())
        entry["seconds_per_point"] = {
            name: provider.get("median_seconds_per_point")
            for name, provider in found.get("providers", {}).items()
        }
        entry["protocol"] = found.get("protocol")
    else:
        entry["error"] = (done.stdout[-2000:] + done.stderr[-2000:]).strip()
    return entry


def _stages(options: Any) -> None:
    """The separate instrumented run (lit-perf's harness with its native stage
    report, the same setting, points and B on this core)."""

    out = Path(options.out) / "stages"
    out.mkdir(parents=True, exist_ok=True)
    command = [
        PYTHON,
        "-m",
        "tools.loop_benchmark",
        "pyamplicol",
        options.process,
        "--inputs",
        "native",
        "--reduction",
        "tirust",
        "ninjars",
        "--unchecked",
        "--batches",
        "128",
        "--reps",
        "1",
        "--native-build",
        str(options.native),
        "--json",
        str(out / f"{options.process}.json"),
    ]
    with open(out / f"{options.process}.log", "w") as log:
        subprocess.run(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
            cwd=options.checkout,
        )


# -------------------------------------------------------------- collect


def collect(options: Any) -> int:
    """The li-timing records of the campaign (one per row and backend), then
    the summaries and the PDF."""

    checkout = Path(options.checkout)
    out = Path(options.out)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        cwd=checkout,
        check=True,
    ).stdout.strip()
    build = json.loads((Path(options.native) / "build-info.json").read_text())
    digest = build.get("native_digest") or build.get("digest")
    keys = dict(timed_rows(checkout))
    records = []
    for path in sorted((out / "rows").glob("*.json")):
        found = json.loads(path.read_text())
        process = found["process"]
        stages_path = out / "stages" / f"{process}.json"
        stages = json.loads(stages_path.read_text()) if stages_path.is_file() else None
        for arm, cell in found["cells"].items():
            records.append(
                {
                    "key": keys.get(process, process),
                    "process": process,
                    "revision": head,
                    "configuration": "unchecked",
                    "requested": found["arms"][arm]["requested"],
                    "backend": found["arms"][arm]["effective"],
                    "effective": found["arms"][arm]["effective"],
                    "reason": found["arms"][arm]["reason"],
                    "unchecked": True,
                    "entry_point": "Runtime.load + evaluate (Python API)",
                    "settings": found["settings"],
                    "batch": found["batch"],
                    "rounds": found["rounds"],
                    "instances": found["instances"],
                    "seconds_per_point": cell["median"],
                    "instance_medians": cell["instance_medians"],
                    "instance_spread": cell["instance_spread"],
                    "failed_points": found["arms"][arm]["failed_points"],
                    "failures": found["arms"][arm]["failures"],
                    "fallback_points": found["arms"][arm]["fallback_points"],
                    "tir_counts": found["tir_counts"] if arm != "ninjars" else None,
                    "providers": found["providers"],
                    "stages": _stage_split(stages, found["arms"][arm]["effective"]),
                    "generation": None if stages is None else stages.get("generation"),
                    "native_build": Path(options.native).name,
                    "native_digest": digest,
                    "host": found["host"],
                    "core": found["core"],
                    "date": found["date"],
                    "source": "lit-unchecked re-time (tools/loop_benchmark/"
                    "retime_unchecked.py): public API with the documented unchecked "
                    "setting; stages from a separate instrumented run",
                }
            )
    target = checkout / LI_TIMING
    data = json.loads(target.read_text())
    data["records"] = [
        r
        for r in data["records"]
        if not (r.get("configuration") == "unchecked" and r.get("revision") == head)
    ] + records
    target.write_text(json.dumps(data, indent=1) + "\n")
    print(f"{len(records)} unchecked records into {target}")
    for command in (
        [PYTHON, "docs/performance_reports/loop/scripts/build_summary.py"],
        [options.typst, "compile", "docs/performance_reports/loop/benchmarks.typ"],
    ):
        if subprocess.run(command, cwd=checkout, check=False).returncode:
            return 1
    return 0


def _stage_split(stages: dict[str, Any] | None, backend: str) -> dict[str, Any] | None:
    """The instrumented run's per-stage seconds per point of ``backend`` at
    its largest B (the harness record's ``backend_runs``: trees + CT kets,
    dressing, scatter, reduction, the rest of its call), labelled."""

    if stages is None:
        return None
    entry = stages.get("backend_runs", {}).get(backend)
    if not entry or not entry.get("batches"):
        return None
    size = max(entry["batches"], key=int)
    summary = entry["batches"][size]
    per = summary.get("stages_per_point") or {}
    main = {name: per.get(name, 0.0) for name in STAGES}
    total = summary["median_seconds_per_point"]
    main["rest"] = max(total - sum(main.values()), 0.0)
    return {
        "label": LABEL,
        "batch": int(size),
        "seconds_per_point": main,
        "total": total,
    }


# ------------------------------------------------------------------ CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="retime_unchecked.py")
    commands = parser.add_subparsers(dest="command", required=True)
    workspace = Path(os.environ.get("PYAMPLICOL_LOOP_WORKSPACE", "/nonexistent"))

    def common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--checkout", type=Path, default=ROOT)
        sub.add_argument("--native", type=Path, required=True)
        sub.add_argument("--out", type=Path, required=True)

    run = commands.add_parser("campaign", help="launch, wait, collect")
    common(run)
    run.add_argument("--rows", nargs="*", help="stream processes (default: lit-perf's)")
    run.add_argument("--skip", nargs="*", help="rows not run (recorded as such)")
    run.add_argument("--artifacts", type=Path, required=True)
    run.add_argument("--rounds", type=int, default=5)
    run.add_argument("--instances", type=int, default=3)
    run.add_argument("--provider-points", type=int, default=16)
    run.add_argument("--auto-row", default="li_gg_hgg")
    run.add_argument("--no-providers", dest="providers", action="store_false")
    run.add_argument("--no-stages", dest="stages", action="store_false")
    run.add_argument("--exclude-cores", type=int, nargs="*")
    run.add_argument("--tag", default=time.strftime("%Y%m%dT%H%M", time.gmtime()))
    run.add_argument("--memory-max", default="150G")
    run.add_argument("--wait-hours", type=float, default=6.0)
    run.add_argument("--env", type=Path, default=workspace / "env.sh")
    run.add_argument(
        "--reference-env", type=Path, default=workspace / "reference" / "env.sh"
    )
    run.add_argument("--reference-root", type=Path, default=workspace / "reference")
    run.add_argument(
        "--licence-file",
        type=Path,
        default=workspace.parent / "HANDOFF_24_10_2026.md",
        help="the file the unit greps the Symbolica licence from (never copied)",
    )
    run.add_argument(
        "--pythonpath",
        default=f"{workspace / 'builds' / 'community-release-python-dfe6bd97'}:src",
    )
    run.add_argument("--dry-run", action="store_true")

    one = commands.add_parser("row", help="one row's timing (inside its unit)")
    one.add_argument("process")
    common(one)
    one.add_argument("--artifacts", type=Path, required=True)
    one.add_argument("--core", type=int, required=True)
    one.add_argument("--rounds", type=int, default=5)
    one.add_argument("--instances", type=int, default=3)
    one.add_argument("--provider-points", type=int, default=16)
    one.add_argument("--auto", action="store_true")
    one.add_argument("--no-providers", dest="providers", action="store_false")
    one.add_argument("--no-stages", dest="stages", action="store_false")

    gather = commands.add_parser("collect", help="records, summaries, PDF")
    common(gather)
    gather.add_argument(
        "--typst",
        default="typst",
        help="Typst 0.15.1 (the report's renderer)",
    )
    options = parser.parse_args(argv)
    if options.command == "campaign":
        return campaign(options)
    if options.command == "row":
        return row(options)
    return collect(options)


if __name__ == "__main__":
    sys.exit(main())
