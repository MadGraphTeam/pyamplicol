# SPDX-License-Identifier: 0BSD
"""Independent MadLoop references for the model-rule top-pair fixtures.

Regenerates ``tests/fixtures/loop/top-pair-model.json`` (``g g > t t~`` and
``u u~ > t t~``) and ``top-pair-higgs-model.json`` (``e+ e- > t t~ h``), all
``[virt=QCD]`` with ``loop_sm-no_b_mass`` in Feynman gauge, from an unmodified
MG5_aMC checkout:

    python tools/loop_reference/madloop_top_pair_model.py generate \\
        --set top-pair --mg5 "$MG5" --builds "$BUILDS"
    python tools/loop_reference/madloop_top_pair_model.py run \\
        --set top-pair --mg5 "$MG5" --builds "$BUILDS" --runs "$RUNS" \\
        --fixture tests/fixtures/loop/top-pair-model.json

``generate`` writes standalone exports and refuses to overwrite them. ``run``
evaluates the exact on-shell points in binary64. The counterterm split only
sets the generated ``SKIPLOOPEVAL`` switch and selects counterterm interference
indices in copies of ``loop_matrix.f`` (diffs are kept beside each binary);
Feynman rules and the export are unchanged. Bare is full minus the generated
counterterm sum. Correctness references only, never timing references.

``--set epsilon-sign`` regenerates ``tests/fixtures/loop/epsilon-sign.json``,
the Levi-Civita sign test of WP3.2 EWI-7b (PLAN [U6](d)):
``u u~ > e- e+ g g / d s b [virt=QCD]``, whose closed quark loops keep only
the up-type flavours, so the axial Z-gluon R2 (``R2_GGZ``, ``R2_GGGVa``, the
UFO ``Epsilon``) and the bare loops' gamma5 traces no longer cancel between
the doublet members. Bare and R2 are compared separately.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import random
import re
import shutil
import subprocess
import sys
from collections import Counter
from decimal import Decimal, getcontext
from fractions import Fraction
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build import madloop_libraries

POLES = ("finite", "single_pole", "double_pole")
COMPONENTS = (
    "bare",
    "uv",
    "r2",
    "full",
    "uv_vertex",
    "wf",
    "uv_mass",
    "r2_quark_two_point",
)
MU = "1000"
COMMON = {
    "source": "MG5_aMC_v3_7_0/models/loop_sm-no_b_mass (MadLoop standalone, "
    "Feynman gauge, complex_mass_scheme False)",
    "provenance": "tools/loop_reference/madloop_top_pair_model.py; diagnostic CT "
    "split by generated SKIPLOOPEVAL plus CT index selection only",
    "convention": "MadLoop finite part, Cepsilon=(4pi)^epsilon/Gamma(1-epsilon); "
    "aS fixed (no running) at MU_R",
}
TAIL = {
    "parameters": {
        "aS": "0.118",
        "aEWM1": "132.507",
        "Gf": "0.0000116639",
        "MZ": "91.188",
        "MH": "125",
        "MT": "173",
        "ymt": "173",
        "MU_R": MU,
    },
    "fixed_parameters": {
        "MB": "0",
        "ymb": "0",
        "MTA": "0",
        "ymtau": "0",
        "WT": "0",
        "WW": "0",
        "WZ": "0",
        "WH": "0",
    },
    "component_scope": "bare = full minus generated CT sum; uv = uv_vertex + wf; "
    "uv_mass = top-mass UV insertions (Identity two-point); r2_quark_two_point = "
    "R2_QQ_1+R2_QQ_2 insertions",
}


def _decimal(value):
    value = Fraction(value)
    text = Decimal(value.numerator) / Decimal(value.denominator)
    assert Fraction(str(text)) == value
    return format(text.normalize(), "f") if value else "0"


def _centre_of_mass_points():
    """p_t^2 = 173^2 exactly: E - p = 173^2/(E + p) with terminating decimals."""
    getcontext().prec = 50
    points = []
    for total, direction in (
        (500, ("0.48", "0.6", "0.64")),
        (800, ("0.352", "-0.36", "0.864")),
        (1250, ("-0.6", "0.48", "-0.64")),
    ):
        total = Decimal(total)
        a = Decimal(173) ** 2 / total
        energy, momentum = (total + a) / 2, (total - a) / 2
        unit = [Decimal(x) for x in direction]
        assert sum(x * x for x in unit) == 1
        top = [energy, *(momentum * x for x in unit)]
        assert top[0] ** 2 - sum(x * x for x in top[1:]) == 173**2
        legs = [
            [energy, 0, 0, energy],
            [energy, 0, 0, -energy],
            top,
            [top[0], *(-x for x in top[1:])],
        ]
        points.append(
            [
                [str(Decimal(x).normalize()) if x != 0 else "0" for x in leg]
                for leg in legs
            ]
        )
    return points


def _higgs_points():
    """Seeded exact on-shell non-CM t t~ h points with terminating decimals."""

    def terminating(value):
        denominator = Fraction(value).denominator
        for prime in (2, 5):
            while denominator % prime == 0:
                denominator //= prime
        return denominator == 1

    def shell(mass, u):
        s = sum(x * x for x in u)
        return [mass * (1 + s) / (1 - s), *(2 * mass * x / (1 - s) for x in u)]

    grid = [Fraction(k, 20) for k in range(-12, 13)]
    directions = [
        u
        for u in product(grid, repeat=3)
        if sum(x * x for x in u) < Fraction(1, 2)
        and terminating(1 / (1 - sum(x * x for x in u)))
        and all(x != 0 for x in u)
    ]
    generator = random.Random(3)
    points = []
    while len(points) < 3:
        u1, u3 = generator.choice(directions), generator.choice(directions)
        top, higgs = shell(Fraction(173), u1), shell(Fraction(125), u3)
        transverse = [-(top[i] + higgs[i]) for i in (1, 2)]
        m2 = 173**2 + transverse[0] ** 2 + transverse[1] ** 2
        a = Fraction(generator.choice([150, 200, 250, 320, 400, 500]))
        antitop = [(a + m2 / a) / 2, *transverse, (m2 / a - a) / 2]
        energy = top[0] + antitop[0] + higgs[0]
        pz = top[3] + antitop[3] + higgs[3]
        x1, x2 = (energy + pz) / 2, (energy - pz) / 2
        legs = [[x1, 0, 0, x1], [x2, 0, 0, -x2], top, antitop, higgs]
        if not all(terminating(c) for leg in legs for c in leg):
            continue
        if not (300 < energy < 2500 and x1 > 0 and x2 > 0):
            continue
        if any(
            len(str(Fraction(c).limit_denominator(10**30))) > 40
            for leg in legs
            for c in leg
        ):
            continue
        for leg, mass in zip(legs, (0, 0, 173, 173, 125), strict=True):
            assert leg[0] ** 2 - sum(x * x for x in leg[1:]) == mass * mass
        for mu in range(4):
            assert legs[0][mu] + legs[1][mu] == sum(leg[mu] for leg in legs[2:])
        getcontext().prec = 60
        points.append([[_decimal(c) for c in leg] for leg in legs])
    return points


SETS = {
    "top-pair": {
        "exports": {
            "gg": (
                "g g > t t~ QED=0 [virt=QCD]",
                "madloop-gg-top-pair-model",
                "P0_gg_ttx",
            ),
            "uu": (
                "u u~ > t t~ QED=0 [virt=QCD]",
                "madloop-uu-top-pair-model",
                "P0_uux_ttx",
            ),
        },
        "labels": {"gg": "g g > t t~ [virt=QCD]", "uu": "u u~ > t t~ [virt=QCD]"},
        "legs": 4,
        # Only the first entry of the driver's two-slot order buffer is set
        # by this export; its QCD power is checked.
        "loop_orders": ["6"],
        "card": (("mass", 6, 173.0), ("yukawa", 6, 173.0)),
        "points": _centre_of_mass_points,
        "scope": "Internal massive top in QCD loops and counterterms (gg) and "
        "top-loop gluon self-energy (uu); binary64 independent MadLoop references; "
        "no timing claim",
        "points_scope": "Exact on-shell CM points: massless gluons/quarks, "
        "p_t^2=173^2 exactly in terminating decimals",
    },
    "top-pair-higgs": {
        "exports": {
            "ee": (
                "e+ e- > t t~ h QED=3 [virt=QCD]",
                "madloop-ee-top-pair-higgs-model",
                "P0_epem_ttxh",
            ),
        },
        "labels": {"ee": "e+ e- > t t~ h [virt=QCD]"},
        "legs": 5,
        # QED is the only split order of this export; its QCD power is checked.
        "loop_orders": ["2"],
        "card": (("mass", 6, 173.0), ("yukawa", 6, 173.0), ("mass", 25, 125.0)),
        "points": _higgs_points,
        "scope": "QCD corrections with massive internal tops, top Yukawa/Goldstone "
        "(FFS) vertices and their QCD counterterms; binary64 independent MadLoop "
        "references; no timing claim",
        "points_scope": "Exact on-shell, non-CM rational points (terminating "
        "decimals): massless beams along z, p_t^2=p_tbar^2=173^2, p_h^2=125^2",
    },
    "epsilon-sign": {
        "exports": {
            "uu": (
                "u u~ > e- e+ g g / d s b QED=2 [virt=QCD]",
                "madloop-epsilon-sign-uux-emepgg-dsb",
                "P0_uux_emepgg_no_dsb",
            ),
        },
        "labels": {"uu": "u u~ > e- e+ g g / d s b [virt=QCD]"},
        "legs": 6,
        "loop_orders": None,
        "card": (("mass", 6, 173.0), ("yukawa", 6, 173.0)),
        "points": lambda: _fixture_points("dilepton-two-gluon.json")[0],
        "mu_r": lambda: _fixture_points("dilepton-two-gluon.json")[1],
        "scope": "Levi-Civita sign test (WP3.2 EWI-7b, EW-20): the d, s, b "
        "vetoed, the axial Z-gluon R2 (R2_GGZ, R2_GGGVa: UFO Epsilon) and the "
        "closed up-type quark loops' axial parts do not cancel; bare and R2 "
        "components; binary64 independent MadLoop references; no timing claim",
        "points_scope": "The three points and scales of "
        "tests/fixtures/loop/dilepton-two-gluon.json (massless, binary64 "
        "decimals)",
    },
}


def _fixture_points(name):
    """The points and per-point renormalisation scales of a loop fixture."""

    fixture = Path(__file__).resolve().parents[2] / "tests/fixtures/loop" / name
    data = json.loads(fixture.read_text())
    return data["points"], data["mu_r"]


DRIVER = """! Diagnostic only: raw MadLoop split-order Born and Laurent values.
program top_pair_model_reference
  implicit none
  integer :: nanswer, nloop, nborn, orders(2), i, j, count, status
  double precision :: p(0:3,LEGS), mu
  double precision, allocatable :: answer(:,:), precision(:)
  character(512) :: card_path, resource_path
  card_path = 'Cards/param_card.dat'
  resource_path = 'SubProcesses/MadLoop5_resources'
  call setpara2(card_path)
  call update_as_param2(1000000d0,0.118d0)
  call setmadlooppath(resource_path)
  call ml5_0_get_answer_dimension(nanswer)
  call ml5_0_get_nsqso_loop(nloop)
  call ml5_0_get_nsqso_born(nborn)
  allocate(answer(0:3,0:nanswer),precision(0:nloop))
  write(*,*) 'DIMENSIONS ',nanswer,nloop,nborn
  do i=1,nloop
    call ml5_0_ml5get_squared_orders_for_soindex(i,orders)
    write(*,*) 'MAP_LOOP ',i,orders
  end do
  read(*,*) count
  do i=1,count
    read(*,*) mu,p
    call update_as_param2(mu**2,0.118d0)
    FORCE_STABILITY
    call ml5_0_sloopmatrix_thres(p,answer,1d-11,precision,status)
    write(*,'(A,2I6,ES26.17E3)') 'POINT ',i,status,precision(0)
    do j=1,nborn
      write(*,'(A,2I6,ES26.17E3)') 'BORN ',i,j,answer(0,j)
    end do
    do j=1,nloop
      write(*,'(A,2I6,4ES26.17E3)') 'LOOP ',i,j,answer(1:3,j),precision(j)
    end do
  end do
end program
"""


def generate(spec, mg5, builds):
    outputs = {process: builds / name for process, name, _ in spec["exports"].values()}
    if any(path.exists() for path in outputs.values()):
        raise FileExistsError("refusing to overwrite an existing MadLoop export")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(mg5))
    os.chdir(builds)
    from madgraph.interface.master_interface import MasterCmd
    from models import import_ufo

    import_ufo.ReadWrite = False
    command = MasterCmd()
    for setting in (
        "automatic_html_opening False",
        "auto_update 0",
        f"ninja {mg5}/HEPTools/ninja/lib",
        f"collier {mg5}/HEPTools/collier",
        "output_dependencies external",
        "loop_optimized_output True",
        "complex_mass_scheme False",
    ):
        command.exec_cmd("set " + setting)
    command.exec_cmd(f"import model {mg5}/models/loop_sm-no_b_mass")
    command.exec_cmd("set gauge Feynman")
    for process, output in outputs.items():
        command.exec_cmd("generate " + process)
        amplitude = command._curr_amps[0]
        loops = Counter()
        for diagram in amplitude["loop_diagrams"]:
            orders = diagram["orders"]
            loops[(orders.get("QCD", 0), orders.get("QED", 0))] += diagram["multiplier"]
        counts = {
            "born": len(amplitude["born_diagrams"]),
            "loops": sum(loops.values()),
            "UVCT_diagrams": len(amplitude["loop_UVCT_diagrams"]),
        }
        print("COUNTS", process, json.dumps(counts), flush=True)
        command.exec_cmd(f"output standalone {output}")


def _classify(process):
    statements = []
    for line in (process / "helas_calls_ampb_1.f").read_text().splitlines():
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
        # Coupling arguments only: the UV mass insertion reuses R2_QQ_2_0.
        args = statement[statement.index("(") + 1 :]
        if "R2_" in args:
            kind = "r2"
        elif "UV_" in args:
            kind = "uv"
        else:
            raise ValueError("unclassified CT call: " + statement)
        if kind == "uv" and "MASS" in args:
            kind = "uv_mass"
        if kind == "r2" and statement.startswith("CALL R2_QQ_"):
            kind = "r2_quark_two_point"
        amplitudes[int(match[1])] = kind
    text = (process / "helas_calls_uvct_1.f").read_text()
    for match in re.finditer(
        r"AMPL\([12],(\d+)\)=AMPL\([12],\1\)\*\(2\.0D0\*UVWFCT", text
    ):
        amplitudes[int(match[1])] = "wf"
    total = re.search(r"NCTAMPS=(\d+)", (process / "loop_matrix.f").read_text())
    assert set(amplitudes) == set(range(1, int(total[1]) + 1))
    return amplitudes


def _evaluate(executable, directory, stream, points, loop_orders):
    result = subprocess.run(
        [str(executable)], input=stream, text=True, capture_output=True, cwd=directory
    )
    (directory / "output.log").write_text(result.stdout + result.stderr)
    result.check_returncode()
    rows = [{} for _ in points]
    for line in result.stdout.splitlines():
        t = line.split()
        if not t:
            continue
        if t[0] == "MAP_LOOP" and loop_orders is not None:
            # Instrumented copies relink loop_matrix.o; only the unmodified
            # export's order map is authoritative.
            assert t[2 : 2 + len(loop_orders)] == loop_orders, t
        elif t[0] == "BORN":
            assert t[2] == "1", t
            rows[int(t[1]) - 1]["born"] = float(t[3])
        elif t[0] == "LOOP":
            assert t[2] == "1", t
            values = zip((*POLES, "accuracy"), map(float, t[3:]), strict=True)
            rows[int(t[1]) - 1].update(values)
        elif t[0] == "POINT":
            rows[int(t[1]) - 1]["status"] = int(t[2])
    assert all({"born", *POLES} <= row.keys() for row in rows), rows
    return rows


def run(spec, mg5, builds, runs, fixture):
    sys.path.insert(0, str(mg5))
    from models.check_param_card import ParamCard

    points = spec["points"]()
    scales = spec["mu_r"]() if "mu_r" in spec else [MU] * len(points)
    stream = f"{len(points)}\n" + "".join(
        mu + " " + " ".join(x for leg in point for x in leg) + "\n"
        for mu, point in zip(scales, points, strict=True)
    )
    groups = {
        "full": None,
        "ct": None,
        "r2": {"r2", "r2_quark_two_point"},
        "uv": {"uv", "uv_mass", "wf"},
        "wf": {"wf"},
        "uv_vertex": {"uv", "uv_mass"},
        "uv_mass": {"uv_mass"},
        "r2_quark_two_point": {"r2_quark_two_point"},
    }
    report = {
        "processes": spec["labels"],
        "source": COMMON["source"],
        "scope": spec["scope"],
        "provenance": COMMON["provenance"],
        "convention": COMMON["convention"],
        "points_scope": spec["points_scope"],
        "points": points,
        "mu_r": list(scales),
        **TAIL,
        "amplitude_counts": {},
        "rows": {},
    }
    for key, (_process, export_name, process_name) in spec["exports"].items():
        export = builds / export_name
        process = export / "SubProcesses" / process_name
        card = ParamCard(str(export / "Cards/param_card.dat"))
        for block, code, value in (
            ("sminputs", 3, 0.118),
            *spec["card"],
            ("loop", 1, 1000.0),
        ):
            card[block].get((code,)).value = value
        for item in card["decay"]:
            item.value = 0.0
        amplitudes = _classify(process)
        groups["ct"] = set(amplitudes.values())
        original = (process / "loop_matrix.f").read_text()
        components = {}
        for kind, accepted in groups.items():
            directory = runs / f"{key}-{kind}"
            directory.mkdir(parents=True, exist_ok=True)
            for part in ("SubProcesses/MadLoop5_resources", "Cards"):
                shutil.copytree(export / part, directory / part, dirs_exist_ok=True)
            card.write(str(directory / "Cards/param_card.dat"))
            objects = []
            force = "call ml5_0_force_stability_check(.true.)" if kind == "full" else ""
            driver = DRIVER.replace("FORCE_STABILITY", force).replace(
                "LEGS", str(spec["legs"])
            )
            if kind != "full":
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
                needle = "PARAMETER (SKIPLOOPEVAL=.FALSE.)"
                assert original.count(needle) == 1
                modified = original.replace(needle, "PARAMETER (SKIPLOOPEVAL=.TRUE.)")
                rejected = sorted(i for i, k in amplitudes.items() if k not in accepted)
                if rejected:
                    needle = "            DO I=1,NCTAMPS\n"
                    assert modified.count(needle) == 1
                    modified = modified.replace(
                        needle,
                        needle
                        + "".join(
                            f"              IF(I.EQ.{i}) CYCLE\n" for i in rejected
                        ),
                    )
                (directory / "loop_matrix.f").write_text(modified)
                (directory / "instrumentation.diff").write_text(
                    "".join(
                        difflib.unified_diff(
                            original.splitlines(True),
                            modified.splitlines(True),
                            fromfile="original/loop_matrix.f",
                            tofile=f"{kind}/loop_matrix.f",
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
                        "-o",
                        str(directory / "loop_matrix.o"),
                    ],
                    check=True,
                )
                objects = [str(directory / "loop_matrix.o")]
            (directory / "driver.f90").write_text(driver)
            subprocess.run(
                [
                    "gfortran",
                    "-O2",
                    str(directory / "driver.f90"),
                    *objects,
                    str(export / "lib/libMadLoop.a"),
                    "-L" + str(export / "lib"),
                    "-ldhelas",
                    "-lmodel",
                    *map(str, madloop_libraries(export)),
                    "-lstdc++",
                    "-o",
                    str(directory / "evaluate"),
                ],
                check=True,
            )
            components[kind] = _evaluate(
                directory / "evaluate",
                directory,
                stream,
                points,
                spec["loop_orders"] if kind == "full" else None,
            )
            print(
                key, kind, [[r[p] for p in POLES] for r in components[kind]], flush=True
            )
        rows = []
        for index, total in enumerate(components["full"]):
            values = {
                kind: {p: components[kind][index][p] for p in POLES} for kind in groups
            }
            for p in POLES:
                scale = max(abs(total["born"]), *(abs(v[p]) for v in values.values()))
                assert (
                    abs(values["ct"][p] - values["uv"][p] - values["r2"][p])
                    < 2e-12 * scale
                )
                assert (
                    abs(values["uv"][p] - values["wf"][p] - values["uv_vertex"][p])
                    < 2e-12 * scale
                )
            for kind in groups:
                assert abs(
                    components[kind][index]["born"] - total["born"]
                ) < 2e-12 * abs(total["born"])
            values["bare"] = {p: values["full"][p] - values["ct"][p] for p in POLES}
            rows.append(
                {
                    "born": total["born"],
                    "madloop_status": total["status"],
                    "madloop_accuracy": total["accuracy"],
                    "components": {kind: values[kind] for kind in COMPONENTS},
                }
            )
        report["amplitude_counts"][key] = dict(
            sorted(Counter(amplitudes.values()).items())
        )
        report["rows"][key] = rows
    fixture.write_text(json.dumps(report, indent=2) + "\n")
    print(fixture)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", choices=("generate", "run"))
    parser.add_argument("--set", choices=sorted(SETS), required=True)
    parser.add_argument("--mg5", type=Path, required=True, help="MG5_aMC checkout")
    parser.add_argument("--builds", type=Path, required=True, help="export directory")
    parser.add_argument("--runs", type=Path, help="run directory (run step)")
    parser.add_argument("--fixture", type=Path, help="output JSON (run step)")
    args = parser.parse_args()
    spec = SETS[args.set]
    mg5, builds = args.mg5.resolve(), args.builds.resolve()
    if args.step == "generate":
        builds.mkdir(parents=True, exist_ok=True)
        generate(spec, mg5, builds)
    else:
        if args.runs is None or args.fixture is None:
            parser.error("run requires --runs and --fixture")
        run(spec, mg5, builds, args.runs.resolve(), args.fixture.resolve())


if __name__ == "__main__":
    main()
