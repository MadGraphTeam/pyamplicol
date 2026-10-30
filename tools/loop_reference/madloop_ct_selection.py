#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Counterterm components of an existing MadLoop standalone reference run.

The Born x CT interference of a selection of a process's counterterm
amplitudes, evaluated on the run's own cards, points and scales
(``runs/required/<name>``: ``madloop-export``, ``madloop-run/Cards``,
``points.json``). Each amplitude of the process's helas-call files is
classified by the coupling names its call passes; a ``--group NAME=REGEX``
holds the amplitudes whose call arguments match REGEX. Evaluated variants:
``ct`` (every CT amplitude), one per group, and ``rest`` (the amplitudes of
no group). The instrumentation is that of ``madloop_ct_component.py`` (a copy
of ``loop_matrix.f`` with the generated ``SKIPLOOPEVAL`` switch on and the
rejected CT amplitude indices skipped; the diff kept beside each binary); the
export is not modified. Correctness references only, never timing
references.

    python tools/loop_reference/madloop_ct_selection.py \\
        --work "$RUNS/required/gt_tttx_ew" --orders 2 4 2 6 --alpha-s 0.118 \\
        --group 'mixing=C_UV(G0Z|AG0|GPWM|GMWP)MASS' --group 'r2=R2GC_' \\
        --output "$SCRATCH/gt_tttx_ew-ct"
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import madloop_libraries
from references import madloop_model_fix, madloop_prefix, point_lines

HERE = Path(__file__).resolve().parent


def statements(path: Path) -> list[str]:
    """The Fortran statements of a fixed-form source, continuations joined."""

    out: list[str] = []
    for line in path.read_text().splitlines():
        if not line.strip() or line[0] in "Cc*!":
            continue
        if len(line) > 5 and line[5] not in " 0":
            out[-1] += line[6:].strip()
        else:
            out.append(line[6:].strip())
    return out


def classify(process: Path, groups: dict[str, re.Pattern[str]]) -> dict[int, str]:
    """Group of every counterterm amplitude (``rest`` for none); an amplitude
    whose calls match two groups, or whose calls differ in group, is refused."""

    found: dict[int, set[str]] = {}
    for path in sorted(process.glob("helas_calls_ampb_*.f")):
        for statement in statements(path):
            match = re.search(r"AMPL\([123],(\d+)\)", statement)
            if not (match and statement.startswith("CALL ")):
                continue
            arguments = statement[statement.index("(") + 1 :]
            names = {
                name for name, pattern in groups.items() if pattern.search(arguments)
            }
            if len(names) > 1:
                raise ValueError(f"amplitude {match[1]} matches groups {sorted(names)}")
            found.setdefault(int(match[1]), set()).add(names.pop() if names else "rest")
    # UV counterterm diagrams (helas_calls_uvct_*.f): a tree call times a UV factor
    # (``AMPL(k,n)=AMPL(k,n)*(...UVWFCT...)``); an amplitude belongs to the group
    # its call or its factor names (several groups refused), else to 'rest'.
    uvct: dict[int, set[str]] = {}
    for path in sorted(process.glob("helas_calls_uvct_*.f")):
        for statement in statements(path):
            match = re.search(r"AMPL\([123],(\d+)\)", statement)
            if not match:
                continue
            text = statement[statement.index("(") + 1 :] if statement.startswith("CALL ") else statement
            uvct.setdefault(int(match[1]), set()).update(
                name for name, pattern in groups.items() if pattern.search(text))
    for index, names in uvct.items():
        if index in found or len(names) > 1:
            raise ValueError(f"UV counterterm amplitude {index} is ambiguous ({sorted(names)})")
        found[index] = {names.pop() if names else "rest"}
    total = int(re.search(r"NCTAMPS=(\d+)", (process / "loop_matrix.f").read_text())[1])
    if set(found) != set(range(1, total + 1)):
        raise ValueError(f"classified {len(found)} of {total} CT amplitudes")
    if any(len(kinds) != 1 for kinds in found.values()):
        raise ValueError("a CT amplitude's calls fall into several groups")
    return {index: kinds.pop() for index, kinds in sorted(found.items())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument(
        "--orders",
        type=int,
        nargs=4,
        required=True,
        metavar=("BORN_QCD", "BORN_QED", "LOOP_QCD", "LOOP_QED"),
    )
    parser.add_argument("--alpha-s", required=True)
    parser.add_argument("--group", action="append", default=[], metavar="NAME=REGEX")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    groups = {}
    for item in args.group:
        name, _, pattern = item.partition("=")
        if not pattern or name in ("ct", "rest") or name in groups:
            raise SystemExit(f"bad group {item!r}")
        groups[name] = re.compile(pattern, re.I)
    export = args.work / "madloop-export"
    (process,) = sorted(p for p in (export / "SubProcesses").glob("P*_*") if p.is_dir())
    kinds = classify(process, groups)
    points = json.loads((args.work / "points.json").read_text())
    stdin = (
        " ".join(map(str, args.orders))
        + f" {args.alpha_s} -1 0\n"
        + f"{len(points['points'])}\n"
        + "\n".join(point_lines(points))
        + "\n"
    )
    original = (process / "loop_matrix.f").read_text()
    needle = "PARAMETER (SKIPLOOPEVAL=.FALSE.)"
    loop = "            DO I=1,NCTAMPS\n"
    if original.count(needle) != 1 or original.count(loop) != 1:
        raise ValueError("loop_matrix.f lacks the SKIPLOOPEVAL switch or the CT loop")
    variants = {
        "ct": {"rest", *groups},
        **{name: {name} for name in groups},
        "rest": {"rest"},
    }
    report = {
        "work": args.work.name,
        "orders": args.orders,
        "alpha_s": args.alpha_s,
        "groups": {name: pattern.pattern for name, pattern in groups.items()},
        "ct_amplitude_counts": {
            name: sum(1 for kind in kinds.values() if kind == name)
            for name in ("rest", *groups)
        },
        "variants": {},
    }
    for name, accepted in variants.items():
        directory = args.output / name
        directory.mkdir(parents=True, exist_ok=True)
        for part in ("Cards", "SubProcesses/MadLoop5_resources"):
            shutil.copytree(
                args.work / "madloop-run" / part, directory / part, dirs_exist_ok=True
            )
        resources = directory / "SubProcesses/MadLoop5_resources"
        params = (resources / "MadLoopParams.dat").read_text()
        for key, value in (
            ("CTModeRun", "1"),
            ("CTModeInit", "1"),
            ("CheckCycle", "1"),
            ("HelicityFilterLevel", "0"),
            ("DoubleCheckHelicityFilter", ".FALSE."),
            ("WriteOutFilters", ".FALSE."),
        ):
            params, count = re.subn(
                r"(#" + key + r"\s*\n)[^\n]+",
                lambda m, v=value: m[1] + v,
                params,
                flags=re.I,
            )
            if count != 1:
                raise ValueError(f"MadLoopParams.dat has no single {key}")
        (resources / "MadLoopParams.dat").write_text(params)
        modified = original.replace(needle, "PARAMETER (SKIPLOOPEVAL=.TRUE.)")
        rejected = sorted(i for i, kind in kinds.items() if kind not in accepted)
        modified = modified.replace(
            loop,
            loop + "".join(f"              IF(I.EQ.{i}) CYCLE\n" for i in rejected),
        )
        (directory / "loop_matrix.f").write_text(modified)
        (directory / "instrumentation.diff").write_text(
            "".join(
                difflib.unified_diff(
                    original.splitlines(True),
                    modified.splitlines(True),
                    fromfile="original/loop_matrix.f",
                    tofile=f"{name}/loop_matrix.f",
                )
            )
        )
        subprocess.run(
            [
                "gfortran",
                "-O2",
                "-ffixed-line-length-132",
                "-fallow-argument-mismatch",
                "-c",
                str(directory / "loop_matrix.f"),
                "-I" + str(process),
                "-I" + str(export / "SubProcesses"),
                "-I" + str(export / "Source/MODEL"),
                "-J",
                str(directory),
                "-o",
                str(directory / "loop_matrix.o"),
            ],
            check=True,
            cwd=directory,
        )
        source = (
            (HERE / "madloop_driver.f90")
            .read_text()
            .replace("ML5_0_", madloop_prefix(process))
        )
        (directory / "madloop_driver.f90").write_text(source)
        fixes, _repairs = madloop_model_fix(export, directory, "-O")
        subprocess.run(
            [
                "gfortran",
                "-O2",
                "-ffree-line-length-none",
                "-I",
                str(process),
                str(directory / "madloop_driver.f90"),
                str(directory / "loop_matrix.o"),
                *map(str, fixes),
                str(export / "lib/libMadLoop.a"),
                "-L" + str(export / "lib"),
                "-ldhelas",
                "-lmodel",
                *map(str, madloop_libraries(export)),
                "-lstdc++",
                "-Wl,--no-relax",
                "-o",
                str(directory / "driver"),
            ],
            check=True,
            cwd=directory,
        )
        run = subprocess.run(
            [str(directory / "driver")],
            input=stdin,
            text=True,
            capture_output=True,
            cwd=directory,
            check=False,
        )
        (directory / "output.log").write_text(run.stdout + run.stderr)
        run.check_returncode()
        rows = {}
        for line in run.stdout.splitlines():
            fields = line.split()
            if fields and fields[0] == "ROW":
                rows[int(fields[1]) - 1] = {
                    "status": int(fields[2]),
                    "born": float(fields[4]),
                    "finite": float(fields[5]),
                    "single_pole": float(fields[6]),
                    "double_pole": float(fields[7]),
                }
        report["variants"][name] = [rows[i] for i in sorted(rows)]
        print(name, json.dumps(report["variants"][name]), flush=True)
    (args.output / "components.json").write_text(json.dumps(report, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
