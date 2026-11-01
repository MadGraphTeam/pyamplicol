#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Recola colour- and spin-correlation references (independent oracles).

For one process of ``required_processes.json`` this builds the generic driver
``recola_correlations.f90`` against a Recola2 tree, evaluates at exact points
(``exact_points.py``, or ``--points``) every request of the generic catalogue

* ``born``: the plain Born and NLO interference (public getters);
* ``cc``: ``compute_colour_correlation_rcl(i, j)`` for every ordered pair of
  distinct coloured legs, LO and NLO;
* ``sc``: ``compute_spin_correlation_rcl(g, v)`` for every external gluon or
  photon g, LO and NLO;
* ``scc``: ``compute_spin_colour_correlation_rcl(g, j, v)`` for every gluon g
  and coloured partner j != g, LO and NLO;

and writes one JSON fixture with Recola's raw values. The NLO pole
coefficients come from Delta_IR = (0,0), (1,0), (0,1) with a linearity check
at (2,3). Each spin vector v is complex and transverse (v.k = 0 exactly):
Recola projects v onto the gluon's two physical helicities, which equals the
literal replacement v.M only for v.k = 0 (v may keep a component along k,
which the Ward identity removes from v.M).

Conventions of the raw values (binary64): Recola's cc(i, j) = <T_i.T_j>/C_i
(cc(i, i) would be the Born), scc(g, j) = <M(v)|T_g.T_j|M(v)>/C_A, incoming
spin/colour averages and final symmetry factors included; the NLO finite part
is Recola's (Gamma(1+eps) normalisation): F_BLHA = F + pi^2/6 IR2.
No process-, name- or multiplicity-keyed branch: every request follows from
the PDG codes (``required_spec.particle``).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from fractions import Fraction as F
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import exact_points  # noqa: E402
import provider_paths  # noqa: E402
import references  # noqa: E402
import required_spec  # noqa: E402

# Recola2 SM particle names by PDG code (the model file's naming).
RECOLA_NAMES = {
    1: "d",
    2: "u",
    3: "s",
    4: "c",
    5: "b",
    6: "t",
    11: "e-",
    12: "nu_e",
    13: "mu-",
    14: "nu_mu",
    15: "tau-",
    16: "nu_tau",
    21: "g",
    22: "A",
    23: "Z",
    24: "W+",
    25: "H",
}
# Fixed generic directions for the transverse vectors and complex weights of
# v = alpha a + beta b + gamma k (a = k x U1 / 1000, b = k x a / 1000).
U1, U2 = (F(3), F(-1), F(2)), (F(1), F(2), F(-5))
ALPHA, BETA, GAMMA = (
    (F(8, 10), F(3, 10)),
    (F(-4, 10), F(9, 10)),
    (F(1, 1000), F(-5, 10000)),
)


def recola_name(pdg: int) -> str:
    base = RECOLA_NAMES[abs(pdg)]
    if pdg > 0 or abs(pdg) in (21, 22, 23, 25):
        return base
    if abs(pdg) == 24:
        return "W-"
    if base.endswith("-"):
        return base[:-1] + "+"
    return base + "~"


def recola_process(spec: dict) -> str:
    given = spec.get("recola", {}).get("process")
    if given:
        return given
    names = [recola_name(p) for p in spec["pdgs"]]
    return " ".join(names[:2]) + " -> " + " ".join(names[2:])


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def transverse_vector(momentum) -> list[list[str]]:
    """A complex vector v with v.k = 0 exactly for the massless momentum k
    (exact decimal strings, [real, imaginary] per component)."""

    k = [F(x) for x in momentum]
    space = tuple(k[1:])
    a = _cross(space, U1)
    if not any(a):
        a = _cross(space, U2)
    a = tuple(x / 1000 for x in a)
    b = tuple(x / 1000 for x in _cross(space, a))
    vector = []
    for mu in range(4):
        am = F(0) if mu == 0 else a[mu - 1]
        bm = F(0) if mu == 0 else b[mu - 1]
        parts = [ALPHA[c] * am + BETA[c] * bm + GAMMA[c] * k[mu] for c in range(2)]
        vector.append(parts)
    for c in range(2):
        dot = vector[0][c] * k[0] - sum(vector[m][c] * k[m] for m in range(1, 4))
        if dot:
            raise AssertionError("spin vector not transverse")
    return [[exact_points.decimal_string(x) for x in parts] for parts in vector]


def catalogue(spec: dict, points: dict) -> list[dict]:
    """Every request of the generic catalogue at every point."""

    info = [required_spec.particle(p) for p in spec["pdgs"]]
    coloured = [k for k, i in enumerate(info, 1) if i["colour"] != 1]
    masses = required_spec.masses(spec)
    # Massless vectors (gluons, photons): Recola's spin correlations; a massive
    # vector's third polarisation is outside its projection.
    vectors = [
        k for k, i in enumerate(info, 1) if i["spin"] == "1" and not masses[k - 1]
    ]
    rows = []
    for index, point in enumerate(points["points"]):
        rows.append({"kind": "born", "legs": [], "point": index, "vector": None})
        for i in coloured:
            for j in coloured:
                if i != j:
                    rows.append(
                        {"kind": "cc", "legs": [i, j], "point": index, "vector": None}
                    )
        for g in vectors:
            v = transverse_vector(point[g - 1])
            rows.append({"kind": "sc", "legs": [g], "point": index, "vector": v})
            if info[g - 1]["colour"] == 8:  # Recola's spin-colour leg is a gluon
                for j in coloured:
                    if j != g:
                        rows.append(
                            {"kind": "scc", "legs": [g, j], "point": index, "vector": v}
                        )
    return rows


def request_lines(rows: list[dict]) -> list[str]:
    lines = [f"requests {len(rows)}"]
    for row in rows:
        legs = (row["legs"] + [0, 0])[:2]
        vector = row["vector"] or [["0", "0"]] * 4
        parts = " ".join(f"{re} {im}" for re, im in vector)
        lines.append(f"{row['kind']} {legs[0]} {legs[1]} {row['point'] + 1} {parts}")
    return lines


def run(args) -> dict:
    spec = required_spec.load_process(args.spec, args.process)
    if args.points:
        points = json.loads(args.points.read_text())
        if points["pdgs"] != spec["pdgs"]:
            raise SystemExit("points JSON belongs to another process")
    else:
        masses = required_spec.masses(spec)
        values = {
            **spec["scheme_data"]["parameters"],
            **spec["scheme_data"]["fixed_parameters"],
        }
        resonances = [
            values[n] for n in ("MZ", "MW", "MH", "MT") if n in values and F(values[n])
        ]
        found = exact_points.generate(
            masses, args.count, F(1, 1000), resonances, pdgs=spec["pdgs"]
        )
        points = {
            "pdgs": spec["pdgs"],
            "points": [
                [[exact_points.decimal_string(x) for x in leg] for leg in p]
                for p in found
            ],
            "mu_r": [args.mu_r[k % len(args.mu_r)] for k in range(args.count)],
        }
    references.check_point_masses(spec, points)
    root = args.recola.resolve()
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    reference_root = provider_paths.reference_root(args.reference_root)
    if reference_root is not None:
        provider_paths.check(
            [Path(os.path.abspath(args.recola))],
            [reference_root],
            libraries=[root / "librecola.so"],
            what="Recola",
            strict=True,
        )
    binary = work / "recola-correlations"
    subprocess.run(
        [
            "gfortran",
            "-O2",
            "-ffree-line-length-none",
            str(HERE / "recola_correlations.f90"),
            "-I",
            str(root / "include"),
            "-L",
            str(root),
            f"-Wl,-rpath,{root}",
            "-lrecola",
            "-o",
            str(binary),
        ],
        check=True,
        cwd=work,
    )
    process = recola_process(spec)
    commands = [
        line if not line.startswith("process ") else f"process {process}"
        for line in references.recola_commands(
            {**spec, "recola": {"process": process}}, points, uncached=True
        )
    ]
    rows = catalogue(spec, points)
    stdin = (
        "\n".join(
            [
                *commands,
                f"points {len(points['points'])}",
                *references.point_lines(points),
                *request_lines(rows),
            ]
        )
        + "\n"
    )
    stdout, _ = references.run_native(
        [str(binary)], stdin, work, work / "output.log", args.cpu
    )
    lines = [line.split() for line in stdout.splitlines() if line.startswith("CORR ")]
    if len(lines) != len(rows):
        log = work / "output.log"
        raise RuntimeError(
            f"{len(lines)} CORR lines for {len(rows)} requests; see {log}"
        )
    for row, fields in zip(rows, lines, strict=True):
        if fields[2] != "T":
            raise RuntimeError(f"Recola's momenta check failed for {row}")
        lo, finite, ir1, ir2, residual = (float(x) for x in fields[3:8])
        row.update({"lo": lo, "nlo": [finite, ir1, ir2], "linearity": residual})
    linked = references.linked_libraries(binary, r"recola|collier|modelfile")
    versions = {
        name.split(".so")[0].removeprefix("lib"): info["version"]
        for name, info in linked.items()
    }
    return {
        "process": spec["name"],
        "pdgs": spec["pdgs"],
        "recola_process": process,
        "scheme": spec["scheme"],
        "born_orders": spec["born_orders"],
        "provenance": (
            f"Recola2 {versions.get('recola')} (recola2-2.3.0 tree), COLLIER "
            f"{versions.get('collier')}, model {versions.get('modelfile')}; "
            "binary64, cache off, Delta_UV = 0, mu_UV = mu_IR = mu_R; "
            "tools/loop_reference/recola_correlations.py"
        ),
        "conventions": (
            "raw Recola: cc(i,j) = <T_i.T_j>/C_i; "
            "scc(g,j) = <M(v)|T_g.T_j|M(v)>/C_A; sc(g) = <M(v)|M(v)>; "
            "averages included; nlo = [F, IR1, IR2] with F_BLHA = F + pi^2/6 IR2; "
            "v complex, v.k_g = 0 exactly"
        ),
        "points": points["points"],
        "mu_r": points["mu_r"],
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--spec", type=Path, default=required_spec.DEFAULT_SPEC)
    parser.add_argument("--process", required=True)
    parser.add_argument(
        "--points",
        type=Path,
        help="points JSON (exact_points.py format); default: generate",
    )
    parser.add_argument("--count", type=int, default=2)
    parser.add_argument("--mu-r", nargs="+", default=["1000", "700"])
    parser.add_argument(
        "--recola", type=Path, required=True, help="Recola2 tree with librecola.so"
    )
    parser.add_argument("--reference-root", type=Path)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--cpu", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=1) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
