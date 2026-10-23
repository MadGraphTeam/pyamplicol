#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""One counterterm component of an existing MadLoop standalone export.

The instrumentation of ``madloop_top_pair_model.py`` (the generated
``SKIPLOOPEVAL`` switch and a selection of counterterm interference indices in
a copy of ``loop_matrix.f``, the diff kept beside the binary) applied to an
export that already exists, e.g. the three-provider reference of
``tests/fixtures/loop/required/gg_gggg.json``. The export is not modified;
every helas-call file of the process classifies its counterterm amplitudes.
Correctness references only, never timing references.

    python tools/loop_reference/madloop_ct_component.py \\
        --export "$RUNS/required/gg_gggg/madloop-export" --process P0_gg_gggg \\
        --points tests/fixtures/loop/required/gg_gggg.json --legs 6 \\
        --mg5 "$MG5" --output "$SCRATCH/gg_gggg-r2" --component r2
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import madloop_libraries
from madloop_top_pair_model import DRIVER, MU, _evaluate

GROUPS = {"r2": {"r2", "r2_quark_two_point"}, "uv": {"uv", "uv_mass", "wf"}}


def classify(process: Path) -> dict[int, str]:
    """Kind of every counterterm amplitude of a MadLoop process directory."""

    statements: list[str] = []
    files = sorted(
        process.glob("helas_calls_ampb_*.f"),
        key=lambda path: int(path.stem.rsplit("_", 1)[1]),
    )
    for path in files:
        for line in path.read_text().splitlines():
            if not line.strip() or line[0] in "Cc*!":
                continue
            if len(line) > 5 and line[5] not in " 0":
                statements[-1] += line[6:].strip()
            else:
                statements.append(line[6:].strip())
    amplitudes = {}
    for statement in statements:
        match = re.search(r"AMPL\([123],(\d+)\)", statement)
        if not (match and statement.startswith("CALL ")):
            continue
        # Coupling arguments only (the UV mass insertion reuses an R2 routine).
        args = statement[statement.index("(") + 1 :]
        if "R2_" in args or "R2GC_" in args:
            kind = "r2"
        elif "UV_" in args or "UVGC_" in args:
            kind = "uv"
        else:
            raise ValueError("unclassified CT call: " + statement)
        if kind == "uv" and "MASS" in args:
            kind = "uv_mass"
        if kind == "r2" and statement.startswith("CALL R2_QQ_"):
            kind = "r2_quark_two_point"
        amplitudes[int(match[1])] = kind
    for path in process.glob("helas_calls_uvct_*.f"):
        for match in re.finditer(
            r"AMPL\([12],(\d+)\)=AMPL\([12],\1\)\*\([0-9.]+D0\*UVWFCT", path.read_text()
        ):
            amplitudes[int(match[1])] = "wf"
    total = re.search(r"NCTAMPS=(\d+)", (process / "loop_matrix.f").read_text())
    missing = set(range(1, int(total[1]) + 1)) - set(amplitudes)
    if missing:
        raise ValueError(f"unclassified CT amplitudes {sorted(missing)[:10]}")
    return amplitudes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--process", required=True)
    parser.add_argument("--points", type=Path, required=True)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--legs", type=int, required=True)
    parser.add_argument("--mg5", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--component", choices=tuple(GROUPS), default="r2")
    args = parser.parse_args()
    sys.path.insert(0, str(args.mg5))
    from models.check_param_card import ParamCard

    export, process = args.export, args.export / "SubProcesses" / args.process
    directory = args.output / args.component
    points = json.loads(args.points.read_text())["points"][: args.count]
    stream = f"{len(points)}\n" + "".join(
        MU + " " + " ".join(x for leg in point for x in leg) + "\n" for point in points
    )
    amplitudes = classify(process)
    card = ParamCard(str(export / "Cards/param_card.dat"))
    for block, code, value in (
        ("sminputs", 3, 0.118),
        ("mass", 6, 173.0),
        ("mass", 5, 0.0),
        ("loop", 1, float(MU)),
    ):
        card[block].get((code,)).value = value
    for item in card["decay"]:
        item.value = 0.0
    for part in ("SubProcesses/MadLoop5_resources", "Cards"):
        shutil.copytree(export / part, directory / part, dirs_exist_ok=True)
    card.write(str(directory / "Cards/param_card.dat"))
    resources = directory / "SubProcesses/MadLoop5_resources"
    params = (resources / "MadLoopParams.dat").read_text()
    for name, value in (
        ("CTModeRun", "1"),
        ("CTModeInit", "1"),
        ("CheckCycle", "1"),
        ("HelicityFilterLevel", "0"),
        ("DoubleCheckHelicityFilter", ".FALSE."),
        ("WriteOutFilters", ".FALSE."),
    ):
        params, count = re.subn(
            r"(#" + name + r"\s*\n)[^\n]+",
            lambda m, value=value: m[1] + value,
            params,
            flags=re.I,
        )
        assert count == 1, name
    (resources / "MadLoopParams.dat").write_text(params)
    original = (process / "loop_matrix.f").read_text()
    needle = "PARAMETER (SKIPLOOPEVAL=.FALSE.)"
    assert original.count(needle) == 1
    modified = original.replace(needle, "PARAMETER (SKIPLOOPEVAL=.TRUE.)")
    runs: list[list[int]] = []
    for index in sorted(
        i for i, k in amplitudes.items() if k not in GROUPS[args.component]
    ):
        if runs and runs[-1][1] == index - 1:
            runs[-1][1] = index
        else:
            runs.append([index, index])
    needle = "            DO I=1,NCTAMPS\n"
    assert modified.count(needle) == 1
    modified = modified.replace(
        needle,
        needle
        + "".join(f"              IF(I.GE.{a}.AND.I.LE.{b}) CYCLE\n" for a, b in runs),
    )
    (directory / "loop_matrix.f").write_text(modified)
    (directory / "instrumentation.diff").write_text(
        "".join(
            difflib.unified_diff(
                original.splitlines(True),
                modified.splitlines(True),
                fromfile="original/loop_matrix.f",
                tofile=f"{args.component}/loop_matrix.f",
            )
        )
    )
    subprocess.run(
        [
            "gfortran", "-O2", "-w", "-fPIC", "-ffixed-line-length-132",
            "-fallow-argument-mismatch", "-c", str(directory / "loop_matrix.f"),
            "-I" + str(process), "-I" + str(export / "SubProcesses"),
            "-I" + str(export / "Source/MODEL"), "-J" + str(directory),
            "-o", str(directory / "loop_matrix.o"),
        ],
        check=True,
    )  # fmt: skip
    driver = DRIVER.replace("FORCE_STABILITY", "").replace("LEGS", str(args.legs))
    (directory / "driver.f90").write_text(driver)
    subprocess.run(
        [
            "gfortran", "-O2", str(directory / "driver.f90"),
            str(directory / "loop_matrix.o"), str(export / "lib/libMadLoop.a"),
            "-L" + str(export / "lib"), "-ldhelas", "-lmodel",
            *map(str, madloop_libraries(export)), "-lstdc++", "-Wl,--no-relax",
            "-o", str(directory / "evaluate"),
        ],
        check=True,
        cwd=directory,
    )  # fmt: skip
    rows = _evaluate(directory / "evaluate", directory, stream, points, None)
    report = {
        "component": args.component,
        "mu_r": MU,
        "points": points,
        "rows": rows,
        "ct_amplitude_counts": dict(sorted(Counter(amplitudes.values()).items())),
    }
    (args.output / f"{args.component}.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
