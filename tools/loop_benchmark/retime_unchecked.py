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


def registry_key(checkout: Path, process: str) -> str:
    """The Table 2 registry key (milestone.json loop_induced) of a stream
    process: the row whose process (or alternative) is the specification's
    MadLoop process without its loop and order annotations; the process
    itself when no row matches."""

    sys.path.insert(0, str(ROOT))
    from tools.loop_benchmark import streams

    text = streams.spec(process)["madloop"]["process"]
    words = [w for w in re.sub(r"\[[^\]]*\]", " ", text).split() if "=" not in w]
    wanted = " ".join(words)
    registry = json.loads(
        (checkout / "docs/performance_reports/loop/data/milestone.json").read_text()
    )["loop_induced"]["rows"]
    for row in registry:
        if wanted in (row.get("process"), row.get("alternative")):
            return row["key"]
    return process


def record_keys(checkout: Path, processes: list[str]) -> dict[str, str]:
    """Each process's record key: lit-perf's timed rows' keys, else the
    registry's (``registry_key``)."""

    known = dict(timed_rows(checkout))
    return {p: known.get(p) or registry_key(checkout, p) for p in processes}


def host_state(core: int) -> dict[str, Any]:
    """The host at the moment of a measurement: the load averages, the
    MemAvailable, and the busy share of ``core`` and of its SMT siblings over
    one second (``/proc``)."""

    def sample() -> dict[int, tuple[int, int]]:
        out = {}
        for line in Path("/proc/stat").read_text().splitlines():
            if line.startswith("cpu") and line[3:4].isdigit():
                name, *fields = line.split()
                values = [int(v) for v in fields]
                out[int(name[3:])] = (sum(values), values[3] + values[4])
        return out

    siblings_file = Path(
        f"/sys/devices/system/cpu/cpu{core}/topology/thread_siblings_list"
    )
    group = {core}
    if siblings_file.is_file():
        for part in siblings_file.read_text().strip().split(","):
            lo, _, hi = part.partition("-")
            group.update(range(int(lo), int(hi or lo) + 1))
    first = sample()
    time.sleep(1.0)
    second = sample()

    def busy(cpu: int) -> float:
        dt = second[cpu][0] - first[cpu][0]
        di = second[cpu][1] - first[cpu][1]
        return round((dt - di) / dt, 3) if dt else 0.0

    memory = {
        line.split(":")[0]: int(line.split()[1])
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith(("MemAvailable", "MemTotal"))
    }
    return {
        "loadavg": Path("/proc/loadavg").read_text().split()[:3],
        "mem_available_gib": round(memory["MemAvailable"] / 2**20, 1),
        "core_busy": busy(core),
        "siblings_busy": {str(c): busy(c) for c in sorted(group - {core})},
    }


def idle_cores(count: int, exclude: set[int]) -> list[int]:
    """``count`` cores with the least busy physical core over a one-second
    sample (``/proc/stat``): a core is ranked by the busiest of its SMT
    siblings (a busy sibling slows a pinned thread by up to ~1.5x, as the
    campaign of 2026-11-09 measured on li_gg_hgg: providers and pyAmpliCol
    alike), and the siblings of a chosen core are skipped."""

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
    load: dict[int, float] = {}
    for cpu, (total, idle) in second.items():
        dt = total - first[cpu][0]
        di = idle - first[cpu][1]
        load[cpu] = (dt - di) / dt if dt else 1.0

    def group_of(cpu: int) -> set[int]:
        siblings = Path(
            f"/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list"
        )
        group = {cpu}
        if siblings.is_file():
            for part in siblings.read_text().strip().split(","):
                lo, _, hi = part.partition("-")
                group.update(range(int(lo), int(hi or lo) + 1))
        return group

    busy = [(max(load.get(c, 1.0) for c in group_of(cpu)), cpu) for cpu in load]
    chosen: list[int] = []
    taken = set(exclude)
    for _load, cpu in sorted(busy):
        if cpu in taken:
            continue
        group = group_of(cpu)
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
        "--row-budget",
        str(options.row_budget),
        "--instances",
        str(options.instances),
        "--provider-points",
        str(options.provider_points),
    ]
    if options.cards is not None:
        inner += ["--cards", shlex.quote(str(options.cards))]
    if options.auto_row == process:
        inner.append("--auto")
    if not options.providers:
        inner.append("--no-providers")
    if not options.stages:
        inner.append("--no-stages")
    if not options.generation:
        inner.append("--no-generation")
    log = out / "logs" / f"{process}.log"
    done = out / "logs" / f"{process}.DONE"
    shell = (
        " ".join(inner)
        + f" > {shlex.quote(str(log))} 2>&1; echo rc=$? > {shlex.quote(str(done))}"
    )
    return [
        "systemd-run",
        "--user",
        f"--unit={options.unit_prefix}-{options.tag}-{process.replace('_', '-')}",
        "--collect",
        "-p",
        f"MemoryMax={options.memory_max}",
        "bash",
        "-c",
        shell,
    ]


def campaign(options: Any) -> int:
    # Absolute paths: the units run from their own working directory.
    for name in ("checkout", "native", "out", "artifacts", "cards"):
        if getattr(options, name) is not None:
            setattr(options, name, Path(getattr(options, name)).resolve())
    options.pythonpath = ":".join(
        str(options.checkout / "src") if part == "src" else part
        for part in options.pythonpath.split(":")
    )
    checkout = Path(options.checkout)
    rows = (
        list(record_keys(checkout, options.rows).items())
        if options.rows
        else timed_rows(checkout)
    )
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
    if not options.wait:
        print("units launched; when every DONE marker exists:")
        print(shlex.join(collect_command))
        return 0
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
    # mu_R^2 as the public API reads it: exact decimal text.
    scales = streams.mu_r2(stream, count)
    return points, scales


def _rotated(items: list, by: int) -> list:
    by %= max(len(items), 1)
    return items[by:] + items[:by]


def ensure_artifact(options: Any, process: str) -> tuple[Path, dict[str, Any]]:
    """The row's artifact (``--artifacts``/<process>/artifact): reused when it
    exists, else generated through the public ``Generator`` from the row's
    run card (``--cards``/<process>/card.toml, its ``generation.output``
    rewritten), with the command and its wall time recorded."""

    import tomllib

    target = Path(options.artifacts) / process / "artifact"
    if (target / "artifact.json").is_file():
        return target, {"artifact": str(target), "generated": "reused"}
    from pyamplicol.api import Generator, ProcessRequest, ProcessSet
    from pyamplicol.config import resolve_config

    text = (Path(options.cards) / process / "card.toml").read_text()
    text = re.sub(
        r"^output = .*$", f"output = {json.dumps(str(target))}", text, flags=re.M
    )
    card = target.parent / "card.toml"
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_text(text)
    (entry,) = tomllib.loads(text)["process"]["entries"]
    begin = time.perf_counter()
    Generator(resolve_config(card)).generate(
        ProcessSet((ProcessRequest.parse(entry["expression"], name=entry["name"]),)),
        target,
    )
    return target, {
        "artifact": str(target),
        "generated": "public Generator",
        "card": str(card),
        "command": "Generator(resolve_config(card)).generate(ProcessSet(("
        f"ProcessRequest.parse({entry['expression']!r}, name={entry['name']!r}),)), "
        "artifact)",
        "seconds": time.perf_counter() - begin,
    }


# One public generation in a child process (its own peak RSS): the run card's
# process through Generator(resolve_config(card)).generate(...) into
# ``target``, timed around the call; the model and preparation caches are
# those of PYAMPLICOL_CACHE_DIR (docs/user/configuration.md), set by the
# caller; generation.loop_induced_probes and SymJIT as shipped (the card's).
GENERATE = """
import json, resource, sys, time, tomllib
from pathlib import Path
from pyamplicol.api import Generator, ProcessRequest, ProcessSet
from pyamplicol.config import resolve_config
card, target = Path(sys.argv[1]), Path(sys.argv[2])
(entry,) = tomllib.loads(card.read_text())["process"]["entries"]
begin = time.perf_counter()
Generator(resolve_config(card)).generate(
    ProcessSet((ProcessRequest.parse(entry["expression"], name=entry["name"]),)),
    target,
)
seconds = time.perf_counter() - begin
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(json.dumps({"seconds": seconds, "peak_gib": peak / 2**20}))
"""


def public_generation(options: Any, process: str) -> dict[str, Any]:
    """The row's generation as a user runs it (lit-ewprep open point (5)):
    the public Generator from the row's run card, twice in one fresh scratch
    cache (PYAMPLICOL_CACHE_DIR, the documented setting; never a user's
    cache): ``cold`` (empty: the model compiled and prepared) and ``warm``
    (the same cache: the second generation), each in its own child process
    on this core with its wall time and peak RSS. The scratch cache and the
    two artifacts are removed afterwards."""

    import shutil
    import tempfile

    text = (Path(options.cards) / process / "card.toml").read_text()
    root = Path(tempfile.mkdtemp(prefix=f"gen-{process}-", dir=options.out))
    out: dict[str, Any] = {
        "entry_point": "Generator(resolve_config(card)).generate(...) (Python API)",
        "cache": "PYAMPLICOL_CACHE_DIR=<fresh scratch directory> (model and"
        " preparation caches; docs/user/configuration.md)",
        "settings": "the run card's (generation.loop_induced_probes off, SymJIT"
        " optimization_level as shipped)",
    }
    try:
        for state in ("cold", "warm"):
            target = root / state / "artifact"
            card = root / state / "card.toml"
            card.parent.mkdir(parents=True)
            card.write_text(
                re.sub(
                    r"^output = .*$",
                    f"output = {json.dumps(str(target))}",
                    text,
                    flags=re.M,
                )
            )
            env = {**os.environ, "PYAMPLICOL_CACHE_DIR": str(root / "cache")}
            done = subprocess.run(
                [PYTHON, "-c", GENERATE, str(card), str(target)],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            if done.returncode:
                out[state] = {"error": (done.stdout + done.stderr)[-2000:]}
                break
            out[state] = json.loads(done.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return out


def _git(checkout: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, cwd=checkout, check=False
    )


def _revision(checkout: Path) -> dict[str, Any]:
    """The timed checkout's revision and whether lit-dress (the dressing
    levers lit-report re-times after) is in it: its integration merge on the
    slice, ``Integrate work/v2-lit-dress``, in the history."""

    head = _git(checkout, "rev-parse", "HEAD").stdout.strip()
    merges = _git(
        checkout, "log", "--oneline", "--grep", "Integrate work/v2-lit-dress", "HEAD"
    ).stdout.strip()
    return {"revision": head, "lit_dress": bool(merges)}


def row(options: Any) -> int:
    import platform

    from pyamplicol import Runtime

    process = options.process
    out = Path(options.out)
    (out / "rows").mkdir(parents=True, exist_ok=True)
    artifact, generation = ensure_artifact(options, process)
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
        "public_generation": generation,
    }
    record.update(_revision(Path(options.checkout)))
    record["host_state"] = {"start": host_state(options.core)}
    if options.cards is not None and options.generation:
        record["public_generation_timing"] = public_generation(options, process)
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

    cpu_share: dict[str, list[float]] = {arm: [] for arm in arms}

    def call(arm: str, i: int) -> tuple[float, Any]:
        cpu = time.process_time()
        begin = time.perf_counter()
        result = runtimes[arm, i].evaluate(
            points, mu_r2=scales, poles="none", on_failure="return", **kwargs[arm]
        )
        elapsed = time.perf_counter() - begin
        # The process's CPU time over the wall time of the call (below 1: the
        # pinned core was shared with another process; an SMT sibling's load
        # does not show here).
        cpu_share[arm].append(round((time.process_time() - cpu) / elapsed, 3))
        return elapsed, result

    # Untimed warm-up of every instance (kernels compiled, caches built).
    first: dict[str, Any] = {}
    warm: dict[tuple[str, int], float] = {}
    for arm, i in runtimes:
        warm[arm, i], result = call(arm, i)
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
    # The two backends' agreement at the timed points (the same public call;
    # the accuracy line of a row without a truth, and the Born-interfered
    # rows' agreement in the backend table).
    record["cross_backend"] = cross_backend(first["tirust"], first["ninjars"])
    seconds: dict[str, dict[int, list[float]]] = {
        arm: {i: [] for i in range(options.instances)} for arm in arms
    }
    providers: list[dict[str, Any]] = []
    order = [(arm, i) for i in range(options.instances) for arm in arms]
    # Rounds within the row's budget (``--row-budget``, one round's timed
    # calls estimated by the warm-up), at least two (an instance's median
    # needs a repeat).
    round_cost = sum(warm.values())
    rounds = max(
        2, min(options.rounds, int(options.row_budget // max(round_cost, 1e-9)))
    )
    record["rounds"] = rounds
    record["round_cost_estimate_seconds"] = round_cost
    for r in range(rounds):
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
    record["cpu_share"] = cpu_share
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
    record["host_state"]["end"] = host_state(options.core)
    (out / "rows" / f"{process}.json").write_text(json.dumps(record, indent=1))
    if options.stages:
        _stages(options)
    return 0


def cross_backend(tirust: Any, ninjars: Any) -> dict[str, Any]:
    """Per point, |T - N| / max(|T|, |N|) of the finite part, the largest
    over the squared-order sectors, on the points both backends served (a
    point either fails is counted apart)."""

    per: list[float | None] = []
    for t, n in zip(tirust.values, ninjars.values, strict=True):
        if t is None or n is None:
            per.append(None)
            continue
        worst = 0.0
        for a, b in zip(t, n, strict=True):
            x, y = float(a[0]), float(b[0])
            scale = max(abs(x), abs(y))
            worst = max(worst, abs(x - y) / scale if scale else 0.0)
        per.append(worst)
    served = [v for v in per if v is not None]
    return {
        "metric": "|T - N| / max(|T|, |N|), finite part, largest over sectors",
        "points": len(served),
        "failed": len(per) - len(served),
        "max_relative": max(served) if served else None,
        "above_1e-5": sum(v > 1e-5 for v in served),
        "per_point": per,
    }


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
        # The one-helicity arm per backend (the plan's first helicity row,
        # |A(h)|^2/avg): the helicity-selection table beside the bars.
        "--one-helicity",
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
    """The li-timing records of the campaign (one per row and explicit
    backend; the "auto" pairing on the TIRust record of its row), then the
    summaries and the PDF."""

    checkout = Path(options.checkout)
    out = Path(options.out)
    build = json.loads((Path(options.native) / "build-info.json").read_text())
    digest = build.get("native_build_inputs_sha256")
    keys = record_keys(
        checkout,
        [json.loads(p.read_text())["process"] for p in (out / "rows").glob("*.json")],
    )
    records = []
    heads: set[str] = set()
    concurrency = len(list((out / "rows").glob("*.json")))
    for path in sorted((out / "rows").glob("*.json")):
        found = json.loads(path.read_text())
        process = found["process"]
        # The timed checkout's revision (the rows' own record; the collecting
        # checkout may be a later one).
        timed = found.get("revision") or _revision(checkout)["revision"]
        heads.add(timed)
        stages_path = out / "stages" / f"{process}.json"
        stages = json.loads(stages_path.read_text()) if stages_path.is_file() else None
        paired = paired_providers(process, found["providers"])
        for arm, cell in found["cells"].items():
            if arm == "auto":
                continue
            records.append(
                _record(
                    found,
                    arm,
                    cell,
                    stages,
                    paired,
                    key=keys.get(process, process),
                    revision=timed,
                    native=Path(options.native).name,
                    digest=digest,
                    concurrency=concurrency,
                )
            )
    # Born-interfered rows (the backend table's, lit-report R4) go to their
    # own file; the loop-induced ones to Table 2's records.
    sys.path.insert(0, str(ROOT))
    from tools.loop_benchmark import streams

    born = [r for r in records if not streams.spec(r["process"]).get("loop_induced")]
    records = [r for r in records if r not in born]
    target = checkout / LI_TIMING
    data = json.loads(target.read_text())
    data["records"] = [
        r
        for r in data["records"]
        if not (r.get("configuration") == "unchecked" and r.get("revision") in heads)
    ] + records
    target.write_text(json.dumps(data, indent=1) + "\n")
    print(f"{len(records)} unchecked records into {target}")
    if born:
        target = checkout / BORN_BACKENDS
        old = json.loads(target.read_text()) if target.is_file() else {"records": []}
        old["what"] = (
            "the backend table's Born-interfered rows (benchmarks.typ Table 3): TIRust"
            " and NinjaRS through the public API with reduction_unchecked = True on"
            " Table 1's 2->3 / 2->4 rows (tools/loop_benchmark/retime_unchecked.py,"
            " written by collect)"
        )
        old["records"] = [
            r for r in old["records"] if r.get("revision") not in heads
        ] + [_born_record(r) for r in born]
        target.write_text(json.dumps(old, indent=1) + "\n")
        print(f"{len(born)} Born-interfered records into {target}")
    if not options.render:
        return 0
    for command in (
        [PYTHON, "docs/performance_reports/loop/scripts/build_summary.py"],
        [options.typst, "compile", "docs/performance_reports/loop/benchmarks.typ"],
    ):
        if subprocess.run(command, cwd=checkout, check=False).returncode:
            return 1
    return 0


BORN_BACKENDS = Path("docs/performance_reports/loop/data/backends-born.json")


def _born_record(record: dict[str, Any]) -> dict[str, Any]:
    """A Born-interfered row's record of one backend (build_summary.py
    build_backend_table's fields)."""

    out = {
        k: record[k]
        for k in (
            "key",
            "process",
            "revision",
            "backend",
            "requested",
            "reason",
            "batch",
            "instances",
            "instance_medians",
            "instance_spread",
            "native_build",
            "native_digest",
            "host",
            "core",
            "date",
            "concurrency",
            "host_state",
            "settings",
            "source",
        )
        if k in record
    }
    if "seconds_per_point" in record:
        out["seconds_per_point"] = record["seconds_per_point"]
    else:
        out["failed_points"] = record["failed_points"][0]
    if record["backend"] == "tirust" and record.get("cross_backend"):
        cross = record["cross_backend"]
        out["agreement"] = {
            "max_relative": cross["max_relative"],
            "points": cross["points"],
            "metric": cross["metric"],
        }
    return out


def _record(
    found: dict[str, Any],
    arm: str,
    cell: dict[str, Any],
    stages: dict[str, Any] | None,
    paired: dict[str, Any],
    **meta: Any,
) -> dict[str, Any]:
    """One li-timing record of a row's arm, in the shape of lit-perf's
    records (build_summary.py's checks): a call that failed points was
    timed whole and carries no time per point (``whole_call_seconds_per_
    point``), its failed points per instance (deterministic: every call of
    an instance evaluates the same points) and causes."""

    process = found["process"]
    outcome = found["arms"][arm]
    failed = outcome["failed_points"]
    batch = found["batch"]
    causes: dict[str, int] = {}
    failures: dict[str, str] = {}
    for point, details in outcome["failures"].items():
        cause, where = _cause(details[0] if details else "no detail")
        causes[cause] = causes.get(cause, 0) + 1
        failures[point] = f"{cause}{where}"
    record: dict[str, Any] = {
        "key": meta["key"],
        "process": process,
        "revision": meta["revision"],
        "lit_dress": found.get("lit_dress"),
        "configuration": "unchecked",
        "requested": outcome["requested"],
        "backend": outcome["effective"],
        "effective": outcome["effective"],
        "reason": outcome["reason"],
        "unchecked": outcome["unchecked"],
        "entry_point": "Runtime.load + evaluate (Python API)",
        "settings": found["settings"],
        "replication": REPLICATION.format(process=process),
        "batch": batch,
        "rounds": found["rounds"],
        "instances": found["instances"],
        "failed_points": [failed] * found["instances"],
        "served_fraction": 1 - failed / batch,
        "fallback_points": outcome["fallback_points"],
        "instance_medians": cell["instance_medians"],
        "instance_spread": cell["instance_spread"],
        "round_spread": cell["round_spread"],
        "providers": paired,
        "gate": gate_of(process, outcome["effective"], cell, failed, batch, paired),
        "stages": _stage_split(stages, outcome["effective"]),
        "generation": _generation(stages),
        "public_generation": found.get("public_generation_timing"),
        "host_state": found.get("host_state"),
        "cross_backend": {
            k: v
            for k, v in (found.get("cross_backend") or {}).items()
            if k != "per_point"
        }
        or None,
        "native_build": meta["native"],
        "native_digest": meta["digest"],
        "host": found["host"],
        "core": found["core"],
        "concurrency": f"{meta['concurrency']} rows in parallel units, one pinned "
        "core each (separate physical cores)",
        "date": found["date"],
        "source": "lit-unchecked re-time (tools/loop_benchmark/"
        f"retime_unchecked.py; process {process}): public API with the "
        "documented unchecked setting; stages from a separate instrumented run",
    }
    shares = (found.get("cpu_share") or {}).get(arm)
    if shares:
        # Per timed call (warm-up included): CPU time over wall time.
        record["cpu_share"] = {
            "min": min(shares),
            "median": statistics.median(shares),
        }
    if failed:
        record["whole_call_seconds_per_point"] = cell["median"]
        record["failures"] = failures
        record["failure_causes"] = causes
    else:
        record["seconds_per_point"] = cell["median"]
    if outcome["effective"] == "tirust":
        record["tir_counts"] = found["tir_counts"]
        if "auto" in found["cells"]:
            auto = found["arms"]["auto"]
            record["auto_pairing"] = {
                "requested": auto["requested"],
                "effective": auto["effective"],
                "reason": auto["reason"],
                "values_bitwise_tirust": found.get("auto_bitwise_tirust"),
                "fallback_points": auto["fallback_points"],
                "failed_points": auto["failed_points"],
                "seconds_per_point": found["cells"]["auto"]["median"],
                "instance_medians": found["cells"]["auto"]["instance_medians"],
                "ratio_to_tirust": found["cells"]["auto"]["median"] / cell["median"],
            }
    return record


def _cause(detail: str) -> tuple[str, str]:
    """A failed point's cause class and where (compact): the lane statuses
    of a per-lane detail ("family F lane LaneKey {...}: Status; ..."), with
    the families and the lane count, else the detail's first line."""

    lanes = re.findall(r"family (\d+) lane LaneKey \{[^}]*\}: (\w+)", detail)
    if not lanes:
        return detail.splitlines()[0][:200], ""
    statuses = sorted({status for _family, status in lanes})
    families = sorted({int(family) for family, _status in lanes})
    return (
        f"lane status {', '.join(statuses)}",
        f" ({len(lanes)} lanes; families {', '.join(map(str, families))})",
    )


# The replication command a user runs (README: the unchecked Table 2).
REPLICATION = (
    'RAYON_NUM_THREADS=1 taskset -c <core> python -c "import pyamplicol; '
    "rt = pyamplicol.Runtime.load('<artifact of {process}>', "
    "reduction_unchecked=True); rt.evaluate(points, mu_r2=mu_r2, poles='none', "
    "on_failure='return', reduction='tirust' | 'ninjars' | 'auto')\" (points: "
    "the 128 stream points "
    "of tools/loop_benchmark/streams/{process}.json)"
)


def _generation(stages: dict[str, Any] | None) -> dict[str, Any] | None:
    """The engine's generation of the instrumented run (gate.py's fields:
    generate + export + filter in ``seconds``, the validation probes apart in
    ``probes_seconds``)."""

    if stages is None or not stages.get("generation"):
        return None
    generation = stages["generation"]
    stage = {
        n: (generation.get(n) or {}).get("seconds", 0.0)
        for n in ("generate", "export", "filter", "probes")
    }
    return {
        "seconds": stage["generate"] + stage["export"] + stage["filter"],
        "generate_seconds": stage["generate"],
        "dressed_frame_seconds": (generation.get("generate") or {}).get(
            "dressed_frame_seconds"
        ),
        "export_seconds": stage["export"],
        "filter_seconds": stage["filter"],
        "probes_seconds": stage["probes"],
        "peak_gib": max(
            (v.get("peak_gib") or 0.0)
            for v in generation.values()
            if isinstance(v, dict)
        ),
        "plan_mb": generation.get("plan_mb"),
        "model_seconds": (generation.get("model") or {}).get("seconds"),
        "source": LABEL,
    }


def paired_providers(process: str, rounds: list[dict[str, Any]]) -> dict[str, Any]:
    """The providers timed in the row's unit (``row``'s rounds of the F4
    most-optimistic provider tool): per provider the median over rounds of
    its per-point median, the rounds' half range, the protocol; the ones the
    tool could not run listed with its error, never filled."""

    sys.path.insert(0, str(ROOT))
    from tools.loop_benchmark import gate

    per: dict[str, list[float]] = {}
    errors = [r["error"] for r in rounds if "error" in r]
    for entry in rounds:
        for name, value in (entry.get("seconds_per_point") or {}).items():
            if value is not None:
                per.setdefault(name, []).append(value)
    return {
        "protocol": "optimistic (m-lit F4; lit-perf's providers --protocol optimistic)",
        "pairing": "same unit and core as the pyAmpliCol arms, back-to-back, the "
        "order of the two blocks alternating between rounds",
        "rounds": len(rounds),
        "times": {
            name: {
                "seconds_per_point": statistics.median(values),
                "rounds": values,
                "half_range": gate.half_range(values),
            }
            for name, values in sorted(per.items())
        },
        "errors": errors,
    }


def gate_of(
    process: str,
    backend: str,
    cell: dict[str, Any],
    failed: int,
    batch: int,
    paired: dict[str, Any],
) -> dict[str, Any]:
    """gate.py's verdict, its rules unchanged, of an unchecked cell against
    the paired provider times: ``gate.gate_verdict`` (the 5 ms rule, the
    matched providers, the band) and ``gate.induced_verdict`` (TIRust gated,
    NinjaRS the second mode, failed points a gap), in the li-timing record
    shape of lit-perf's records."""

    sys.path.insert(0, str(ROOT))
    from tools.loop_benchmark import gate

    record = {
        "providers": {
            name: {"median_seconds_per_point": value["seconds_per_point"]}
            for name, value in paired["times"].items()
        }
    }
    unmatched = gate.unmatched_providers(process, record)
    missing = gate.missing_providers(process, record)
    times = {
        name: value["seconds_per_point"]
        for name, value in paired["times"].items()
        if name not in unmatched
    }
    if not times:
        return {"status": "no matched provider timing", "missing": missing}
    samples = cell["instance_medians"]
    verdict = gate.gate_verdict(
        cell["median"],
        times,
        uncertainty=gate.median_uncertainty(samples),
        reference_uncertainty={
            name: (paired["times"][name]["half_range"] or 0.0, False) for name in times
        },
        missing=missing,
        batch=batch,
        unmatched={
            name: {
                "seconds": paired["times"][name]["seconds_per_point"],
                "reason": reason,
            }
            for name, reason in unmatched.items()
            if name in paired["times"]
        },
    )
    summary = {
        "failed_points": [failed],
        "points_per_block": batch,
        "median_seconds_per_point": cell["median"],
    }
    verdict = gate.induced_verdict(verdict, summary, backend, None, times)
    out = {
        k: verdict[k]
        for k in (
            "status",
            "measured_status",
            "binding_provider",
            "binding_limit",
            "fastest_provider",
            "served_fraction",
            "not_matched",
            "missing",
            "floor_basis_seconds",
        )
        if k in verdict
    }
    if "ratio_to_binding_limit" in verdict:
        out["ratio_to_limit"] = verdict["ratio_to_binding_limit"]
        out["band"] = verdict["band_to_binding_limit"]
    out["provider_protocols"] = {name: "optimistic" for name in sorted(times)}
    return out


def _stage_split(stages: dict[str, Any] | None, backend: str) -> dict[str, Any] | None:
    """The instrumented run's per-stage seconds per point of ``backend`` at
    its largest B (the harness record's ``backend_runs``), verbatim: every
    stage the native report and the harness timed, the reduction with its
    backend's own sub-stages (TIRust: tensor moments, contraction; NinjaRS:
    masters); the report groups them (build_summary.py ``_split``, the
    MASTER_PLAN stage-split rule), labelled."""

    if stages is None:
        return None
    entry = stages.get("backend_runs", {}).get(backend)
    if not entry or not entry.get("batches"):
        return None
    size = max(entry["batches"], key=int)
    summary = entry["batches"][size]
    return {
        "label": LABEL,
        "batch": int(size),
        "seconds_per_point": dict(summary.get("stages_per_point") or {}),
        "total": summary["median_seconds_per_point"],
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
    run.add_argument(
        "--cards",
        type=Path,
        help="run cards <process>/card.toml of rows without an artifact",
    )
    run.add_argument("--rounds", type=int, default=5)
    run.add_argument(
        "--row-budget",
        type=float,
        default=3600.0,
        help="seconds of timed rounds per row (fewer rounds, at least two, "
        "where the rounds would exceed it)",
    )
    run.add_argument("--instances", type=int, default=3)
    run.add_argument("--provider-points", type=int, default=16)
    run.add_argument("--auto-row", default="li_gg_hgg")
    run.add_argument("--no-providers", dest="providers", action="store_false")
    run.add_argument("--no-stages", dest="stages", action="store_false")
    run.add_argument(
        "--no-generation",
        dest="generation",
        action="store_false",
        help="skip the public cold / warm generation timing",
    )
    run.add_argument("--exclude-cores", type=int, nargs="*")
    run.add_argument("--tag", default=time.strftime("%Y%m%dT%H%M", time.gmtime()))
    run.add_argument(
        "--unit-prefix",
        default="lit-lit-unchecked-retime",
        help="systemd unit name prefix (the host's memguard governs lit-*)",
    )
    run.add_argument("--memory-max", default="150G")
    run.add_argument("--wait-hours", type=float, default=6.0)
    run.add_argument(
        "--no-wait",
        dest="wait",
        action="store_false",
        help="launch the units and print the collect command",
    )
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
    one.add_argument("--cards", type=Path)
    one.add_argument("--core", type=int, required=True)
    one.add_argument("--rounds", type=int, default=5)
    one.add_argument("--row-budget", type=float, default=3600.0)
    one.add_argument("--instances", type=int, default=3)
    one.add_argument("--provider-points", type=int, default=16)
    one.add_argument("--auto", action="store_true")
    one.add_argument("--no-providers", dest="providers", action="store_false")
    one.add_argument("--no-stages", dest="stages", action="store_false")
    one.add_argument("--no-generation", dest="generation", action="store_false")

    gather = commands.add_parser("collect", help="records, summaries, PDF")
    common(gather)
    gather.add_argument(
        "--typst",
        default="typst",
        help="Typst 0.15.1 (the report's renderer)",
    )
    gather.add_argument(
        "--no-render",
        dest="render",
        action="store_false",
        help="write the records only (no summaries, no PDF)",
    )
    options = parser.parse_args(argv)
    if options.command == "campaign":
        return campaign(options)
    if options.command == "row":
        return row(options)
    return collect(options)


if __name__ == "__main__":
    sys.exit(main())
