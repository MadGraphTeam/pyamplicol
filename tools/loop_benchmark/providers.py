# SPDX-License-Identifier: 0BSD
"""Provider timing for gate G1 in production mode (REQUIREMENTS_ADDENDUM D).

MadLoop, Recola and OpenLoops evaluate the first ``--points`` points of the
frozen stream (``streams.py``; decimal text ``streams.binary64``) on one
pinned core, through the drivers and settings of the required-references
toolkit (``tools/loop_reference/references.py``, ``required_spec``) with the
process specification of ``processes.json``. Only the pole settings differ
from that campaign, as the addendum asks:

- **OpenLoops**: ``truepoles 0`` (its production default: Collier cache on,
  poles from the I-operator, the default stability system); OpenLoops has no
  mode without poles. Its finite part equals the ``truepoles 1`` campaign's
  (DESIGN Appendix C).
- **Recola**: ``compute_ir_poles 0`` (one ``compute_amplitude`` per point
  instead of three) with the Collier global cache on below seven legs, as in
  production. The toolkit driver gets an ``irpoles`` command for this (the
  copy patched here; ``tools/loop_reference/recola_driver.f90`` is not
  changed). Without poles Recola's finite part stays in its own convention;
  ``gate.py`` adds ``pi^2/6 D`` with the universal double pole of the
  massless coloured legs for the value comparison.
- **MadLoop**: its production setting (``MLStabThres`` and the default
  stability test, ``--madloop-accuracy`` <= 0 in the toolkit), on an export
  built with MG5's production Fortran flags; MadLoop always returns its
  poles.

Every driver evaluates point 1 once untimed (initialisation), then times
points 2..n and 1 one by one. Per point the driver's own timer is recorded;
the provider's per-point time is the mean over the timed points (providers
have no batch API: the per-point time does not depend on B). Generation and
initialisation (Recola's ``generate``, MadLoop's first call, OpenLoops'
library load) are recorded separately.

Usage:
    python -m tools.loop_benchmark providers gg_gggg --cpu 150 \\
        --work DIR --points 16 [--providers openloops recola madloop] \\
        [--madloop-export EXPORT] --json OUT.json
"""

from __future__ import annotations

import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from . import streams

WORKSPACE = Path("/shared/external/pyLoopAmpliCol/workspace")
MG5 = WORKSPACE / "reference/sources/MG5_aMC_v3_7_0"
OPENLOOPS = WORKSPACE / "reference/sources/OpenLoops-2.1.5"
RECOLA = WORKSPACE / "reference/sources/recola2-2.3.0"
# Campaign exports built with MG5's production flags, per process.
REQUIRED = WORKSPACE / "reference/runs/required"
MADLOOP_EXPORTS = {
    "uux_ddxg": REQUIRED / "uux_ddxg/madloop-export",
    "uux_uuxg": REQUIRED / "uux_uuxg/madloop-export",
    "gg_gggg": REQUIRED / "gg_gggg/madloop-export-production-flags",
    "gg_ttxgg": REQUIRED / "gg_ttxgg/madloop-export-production-flags",
}


def _references() -> Any:
    reference = str(streams.REFERENCE)
    if reference not in sys.path:
        sys.path.insert(0, reference)
    import references

    return references


def _points(key: str, count: int) -> dict[str, Any]:
    """The first ``count`` stream points in the toolkit's points format."""

    stream = streams.load(key)
    return {
        "pdgs": stream["pdgs"],
        "points": streams.binary64(stream, count),
        "mu_r": stream["mu_r"][:count],
    }


def _summary(rows: list[dict[str, Any]], extra: dict[str, Any], wall: float) -> dict:
    seconds = [row["seconds"] for row in rows]
    return {
        "points": len(rows),
        "mean_seconds_per_point": statistics.fmean(seconds),
        "median_seconds_per_point": statistics.median(seconds),
        "min_seconds_per_point": min(seconds),
        "max_seconds_per_point": max(seconds),
        "rows": rows,
        "setup": extra,
        "process_wall_seconds": wall,
    }


def openloops(spec: dict, points: dict, work: Path, cpu: int) -> dict[str, Any]:
    references = _references()
    run = work / "openloops-run"
    run.mkdir(parents=True, exist_ok=True)
    binary = run / "openloops-driver"
    if not binary.exists():
        subprocess.run(
            [
                "g++",
                "-O2",
                "-std=c++17",
                str(streams.REFERENCE / "openloops_driver.cpp"),
                "-I",
                str(OPENLOOPS / "include"),
                "-L",
                str(OPENLOOPS / "lib"),
                f"-Wl,-rpath,{OPENLOOPS / 'lib'}",
                "-lopenloops",
                "-o",
                str(binary),
            ],
            check=True,
            cwd=run,
        )
    commands = [
        "int truepoles 0" if c == "int truepoles 1" else c
        for c in references.openloops_commands(spec)
    ]
    if "int truepoles 0" not in commands:
        raise RuntimeError("the toolkit's OpenLoops commands changed")
    count = len(points["points"])
    lines = [*commands, f"points {count}", *references.point_lines(points)]
    stdin = "\n".join(lines) + "\n"
    stdout, wall = references.run_native(
        [str(binary)], stdin, run, run / "output.log", cpu
    )
    rows, extra = references.parse_rows(stdout, "openloops", count)
    library = spec["openloops"]["library"]
    return {
        "provider": "openloops",
        "mode": "production: truepoles 0 (Collier cache, I-operator poles, "
        "default stability)",
        "version": f"OpenLoops {references.openloops_release(OPENLOOPS)}",
        "library": {
            "name": library,
            **references.openloops_library_version(OPENLOOPS, library),
        },
        "commands": commands,
        **_summary(rows, extra, wall),
    }


def _recola_driver(run: Path) -> Path:
    """The toolkit's Recola driver with an ``irpoles <0|1>`` command."""

    source = (streams.REFERENCE / "recola_driver.f90").read_text()
    patches = (
        (
            "  integer :: stored_nf = -1\n",
            "  integer :: stored_nf = -1\n  integer :: irpoles = 1\n",
        ),
        (
            "    case ('cache')",
            "    case ('irpoles')\n      read(line, *) keyword, irpoles\n"
            "    case ('cache')",
        ),
        (
            "      call set_compute_ir_poles_rcl(1)",
            "      call set_compute_ir_poles_rcl(irpoles)",
        ),
        (
            "    call get_squared_amplitude_rcl(1, pow_nlo, 'NLO-IR1', result(3))\n"
            "    call get_squared_amplitude_rcl(1, pow_nlo, 'NLO-IR2', result(4))",
            "    result(3:4) = 0d0\n    if (irpoles == 1) then\n"
            "      call get_squared_amplitude_rcl(1, pow_nlo, 'NLO-IR1', result(3))\n"
            "      call get_squared_amplitude_rcl(1, pow_nlo, 'NLO-IR2', result(4))\n"
            "    end if",
        ),
    )
    for old, new in patches:
        if source.count(old) != 1:
            raise RuntimeError(
                f"the toolkit's Recola driver changed near {old.strip()!r}"
            )
        source = source.replace(old, new)
    path = run / "recola_driver_production.f90"
    path.write_text(source)
    binary = run / "recola-driver-production"
    subprocess.run(
        [
            "gfortran",
            "-O2",
            "-ffree-line-length-none",
            str(path),
            "-I",
            str(RECOLA / "include"),
            "-L",
            str(RECOLA),
            f"-Wl,-rpath,{RECOLA}",
            "-lrecola",
            "-o",
            str(binary),
        ],
        check=True,
        cwd=run,
    )
    return binary


def recola(spec: dict, points: dict, work: Path, cpu: int) -> dict[str, Any]:
    references = _references()
    run = work / "recola-run"
    run.mkdir(parents=True, exist_ok=True)
    binary = _recola_driver(run)
    uncached = len(spec["pdgs"]) >= references.UNCACHED_LEG_THRESHOLD
    commands = references.recola_commands(spec, points, uncached)
    commands.insert(commands.index("generate"), "irpoles 0")
    count = len(points["points"])
    lines = [*commands, f"points {count}", *references.point_lines(points)]
    stdin = "\n".join(lines) + "\n"
    stdout, wall = references.run_native(
        [str(binary)], stdin, run, run / "output.log", cpu
    )
    rows, extra = references.parse_rows(stdout, "recola", count)
    linked = references.linked_libraries(binary, r"recola|collier|modelfile")
    return {
        "provider": "recola",
        "mode": "production: compute_ir_poles 0, Collier global cache "
        + ("off (seven legs, COLLIER cache defect)" if uncached else "on"),
        "version": "Recola2 (tree "
        + RECOLA.name
        + ") / "
        + " / ".join(f"{k} {v['version']}" for k, v in sorted(linked.items())),
        "commands": commands,
        "finite_convention": "Recola (Gamma(1+eps)); MadLoop's adds pi^2/6 D",
        **_summary(rows, extra, wall),
    }


def madloop(
    spec: dict, points: dict, work: Path, cpu: int, export: Path
) -> dict[str, Any]:
    references = _references()
    run = work / "madloop-run"
    run.mkdir(parents=True, exist_ok=True)
    flags = references.madloop_build_flags(export, MG5)
    if not flags["production_build"]:
        raise RuntimeError(f"{export} is not built with MG5's production flags")
    binary, repairs = references.build_madloop(
        export, run, flags["export_make_opts"]["GLOBAL_FLAG"]
    )
    settings = references.prepare_madloop_run(spec, export, run, MG5, len(spec["pdgs"]))
    born, loop = spec["born_orders"], spec["loop_orders"]
    count = len(points["points"])
    alpha_s = references.value(spec["scheme_data"], "aS")
    header = (
        f"{2 * born['QCD']} {2 * born['QED']} {born['QCD'] + loop['QCD']} "
        f"{born['QED'] + loop['QED']} {alpha_s} -1 0\n{count}\n"
    )
    stdin = header + "\n".join(references.point_lines(points)) + "\n"
    stdout, wall = references.run_native(
        [str(binary)], stdin, run, run / "output.log", cpu
    )
    rows, extra = references.parse_rows(stdout, "madloop", count)
    return {
        "provider": "madloop",
        "mode": "production: MLStabThres and the default stability test, MG5 "
        "production Fortran flags",
        "version": "MadLoop/MG5_aMC 3.7.0",
        "export": str(export),
        "madloop_params": settings["MadLoopParams"],
        "fortran_flags": flags["export_make_opts"],
        "qp_model_repairs": repairs,
        **_summary(rows, extra, wall),
    }


# MadLoop's per-point call sites, grouped as the live report shows them:
# 0 loop-numerator coefficients (COEF_CONSTRUCTION), 1 Born, counterterm and
# shared wavefunction HELAS calls (HELAS_CALLS_AMPB, HELAS_CALLS_UVCT),
# 2 reduction and masters (LOOP_CT_CALLS: the reducers and their integrals,
# stability retries included); multiple-precision variants count alike.
STAGE_CALL = re.compile(
    r"\s+CALL ML5_\d+_(?:MP_)?(COEF_CONSTRUCTION|HELAS_CALLS_AMPB|HELAS_CALLS_UVCT"
    r"|LOOP_CT_CALLS)_\d+\(.*\)\s*$"
)
STAGE_BUCKETS = {
    "COEF_CONSTRUCTION": 0,
    "HELAS_CALLS_AMPB": 1,
    "HELAS_CALLS_UVCT": 1,
    "LOOP_CT_CALLS": 2,
}
STAGE_NAMES = (
    "loop numerator coefficients",
    "Born and counterterm HELAS",
    "reduction and masters",
)
STAGE_TIMER = r"""
#include <stdio.h>
#include <time.h>
static double total[3], begin[3];
static unsigned long long calls[3];
static double now(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return t.tv_sec + 1e-9 * t.tv_nsec;
}
void reference_stage_start_(const int *i) { begin[*i] = now(); }
void reference_stage_stop_(const int *i) {
  total[*i] += now() - begin[*i];
  ++calls[*i];
}
__attribute__((destructor)) static void report(void) {
  FILE *f = fopen("madloop-stages.json", "w");
  if (!f) return;
  fprintf(f, "{\"seconds\": [%.9e, %.9e, %.9e], \"calls\": [%llu, %llu, %llu]}\n",
          total[0], total[1], total[2], calls[0], calls[1], calls[2]);
  fclose(f);
}
"""


def _instrumented_madloop(export: Path, run: Path, global_flag: str) -> Path:
    """MadLoop's driver linked with copies of ``loop_matrix.f`` and
    ``mp_compute_loop_coefs.f`` whose stage calls are bracketed by wall-clock
    timers (``STAGE_CALL``); the export itself is never modified. The timers
    write ``madloop-stages.json`` into the working directory at exit."""

    import shlex

    references = _references()
    from build import madloop_libraries

    process = references.madloop_process_dir(export)
    objects = []
    for name in ("loop_matrix.f", "mp_compute_loop_coefs.f"):
        lines = []
        count = 0
        for line in (process / name).read_text().splitlines(keepends=True):
            match = STAGE_CALL.match(line)
            if match:
                bucket = STAGE_BUCKETS[match.group(1)]
                lines += [
                    f"      CALL REFERENCE_STAGE_START({bucket})\n",
                    line,
                    f"      CALL REFERENCE_STAGE_STOP({bucket})\n",
                ]
                count += 1
            else:
                lines.append(line)
        if not count:
            raise RuntimeError(f"no MadLoop stage calls found in {name}")
        source = run / name
        source.write_text("".join(lines))
        target = run / (name[:-2] + ".o")
        subprocess.run(
            [
                "gfortran",
                "-w",
                "-fPIC",
                "-fno-common",
                "-ffixed-line-length-132",
                "-fallow-argument-mismatch",
                *shlex.split(global_flag),
                "-I",
                str(process),
                "-I",
                str(export / "SubProcesses"),
                "-I",
                str(export / "Source/MODEL"),
                "-J",
                str(run),
                "-c",
                str(source),
                "-o",
                str(target),
            ],
            check=True,
            cwd=run,
        )
        objects.append(target)
    timer = run / "stage_timer.c"
    timer.write_text(STAGE_TIMER)
    subprocess.run(
        ["gcc", "-O2", "-c", str(timer), "-o", str(run / "stage_timer.o")],
        check=True,
        cwd=run,
    )
    objects.append(run / "stage_timer.o")
    driver = run / "madloop_driver.f90"
    driver.write_text(
        (streams.REFERENCE / "madloop_driver.f90")
        .read_text()
        .replace("ML5_0_", references.madloop_prefix(process))
    )
    fixes, _ = references.madloop_model_fix(export, run, global_flag)
    binary = run / "madloop-driver-stages"
    subprocess.run(
        [
            "gfortran",
            "-O2",
            "-ffree-line-length-none",
            "-I",
            str(process),
            str(driver),
            *map(str, objects),
            *map(str, fixes),
            str(export / "lib/libMadLoop.a"),
            "-L" + str(export / "lib"),
            "-ldhelas",
            "-lmodel",
            *map(str, madloop_libraries(export)),
            "-lstdc++",
            "-Wl,--no-relax",
            "-o",
            str(binary),
        ],
        check=True,
        cwd=run,
    )
    return binary


def madloop_stages(
    spec: dict, points: dict, work: Path, cpu: int, export: Path
) -> dict[str, Any]:
    """MadLoop's numerator / Born-and-CT / reduction-and-masters split.

    The instrumented driver runs the stream's points once and the first
    point alone, after a warm-up that stores MadLoop's filters; both measured
    runs initialise identically (point 1, untimed), so the difference of
    their stage totals is the stage time of points 2..n, and the per-point
    stage times are that difference over n - 1. The driver's own per-point
    total (instrumented) is reported beside them; the timers cost one clock
    read per call."""

    references = _references()
    run = work / "madloop-stages-run"
    run.mkdir(parents=True, exist_ok=True)
    flags = references.madloop_build_flags(export, MG5)
    binary = _instrumented_madloop(
        export, run, flags["export_make_opts"]["GLOBAL_FLAG"]
    )
    references.prepare_madloop_run(spec, export, run, MG5, len(spec["pdgs"]))
    born, loop = spec["born_orders"], spec["loop_orders"]
    alpha_s = references.value(spec["scheme_data"], "aS")
    totals = {}
    rows = {}
    # MadLoop stores its helicity and loop filters in the resources at the
    # end of its initialisation; the untimed warm-up writes them, so both
    # measured runs load them and initialise identically.
    runs = (("warm-up", 1), ("all", len(points["points"])), ("first", 1))
    for label, count in runs:
        subset = {
            **points,
            "points": points["points"][:count],
            "mu_r": points["mu_r"][:count],
        }
        header = (
            f"{2 * born['QCD']} {2 * born['QED']} {born['QCD'] + loop['QCD']} "
            f"{born['QED'] + loop['QED']} {alpha_s} -1 0\n{count}\n"
        )
        stdin = header + "\n".join(references.point_lines(subset)) + "\n"
        stdout, _ = references.run_native(
            [str(binary)], stdin, run, run / f"output-{label}.log", cpu
        )
        rows[label], _ = references.parse_rows(stdout, "madloop", count)
        totals[label] = json.loads((run / "madloop-stages.json").read_text())
    timed = len(points["points"]) - 1
    if timed < 1:
        raise RuntimeError("the stage split needs at least two points")
    stage = [
        (a - b) / timed
        for a, b in zip(
            totals["all"]["seconds"], totals["first"]["seconds"], strict=True
        )
    ]
    per_point = statistics.fmean(row["seconds"] for row in rows["all"][:-1])
    return {
        "stages_seconds_per_point": dict(zip(STAGE_NAMES, stage, strict=True)),
        "residual_seconds_per_point": per_point - sum(stage),
        "instrumented_seconds_per_point": per_point,
        "points": timed,
        "calls_per_point": [
            (a - b) / timed
            for a, b in zip(
                totals["all"]["calls"], totals["first"]["calls"], strict=True
            )
        ],
    }


def main(options: Any) -> int:
    key = options.process
    spec = streams.spec(key)
    points = _points(key, options.points)
    work = options.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    # MG5_aMC writes py.py and additional_command into the working directory.
    os.chdir(work)
    record: dict[str, Any] = {
        "kind": "providers",
        "process": key,
        "cpu": options.cpu,
        "host": platform.node(),
        "points": len(points["points"]),
        "timing_scope": "single pinned core; point 1 once untimed, then points "
        "2..n, 1 timed one by one with the driver's own timer",
        "providers": {},
    }
    if options.json and options.json.exists():
        record = json.loads(options.json.read_text())
    for provider in options.providers:
        start = time.perf_counter()
        try:
            if provider == "openloops":
                result = openloops(spec, points, work, options.cpu)
            elif provider == "recola":
                result = recola(spec, points, work, options.cpu)
            else:
                export = options.madloop_export or MADLOOP_EXPORTS.get(key)
                if export is None:
                    raise RuntimeError("no MadLoop export for this process")
                result = madloop(spec, points, work, options.cpu, Path(export))
                if options.madloop_stages:
                    result["stages"] = madloop_stages(
                        spec, points, work, options.cpu, Path(export)
                    )
        except Exception as error:  # recorded, never silently dropped
            result = {"provider": provider, "error": f"{type(error).__name__}: {error}"}
        result["harness_wall_seconds"] = time.perf_counter() - start
        record["providers"][provider] = result
        mean = result.get("mean_seconds_per_point")
        print(
            key,
            provider,
            "error " + result["error"]
            if "error" in result
            else f"{mean * 1e3:.3f} ms/pt",
            flush=True,
        )
        if options.json:
            options.json.parent.mkdir(parents=True, exist_ok=True)
            options.json.write_text(json.dumps(record, indent=1) + "\n")
    return 0


def universal_double_pole(spec: dict) -> float:
    """-(alpha_s/2pi) sum_i C_i over the massless coloured legs (D / Born)."""

    references = _references()
    alpha_s = float(references.value(spec["scheme_data"], "aS"))
    masses = streams._toolkit()[1].masses(spec)
    total = 0.0
    for pdg, mass in zip(spec["pdgs"], masses, strict=True):
        if mass:
            continue
        if pdg == 21:
            total += 3.0
        elif abs(pdg) <= 6:
            total += 4.0 / 3.0
    return -alpha_s / (2 * math.pi) * total
