#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""NGluon leading-colour values of n-gluon one-loop matrix elements (M-FINAL
MF-8G-3 (vi); NJet 3.1.2 ``ngluon2``, 8g0-report §9): an independent
leading-colour reference for the 2->6 row g g > g g g g g g, validated at six
and seven gluons against pyAmpliCol's leading colour.

``ngluon_lc.cpp`` sums the tree and the leading gluon-loop primitive over the
(n-1)! colour orderings and the non-vanishing helicities: S0 = sum |A0|^2,
S1 = sum 2 Re(conj(A0) A1) (FDH, unrenormalised, c_Gamma and couplings
factored out as in NJet's colour sums). pyAmpliCol's leading colour keeps
the leading N_c degree (n_f of degree 0: no quark loops, beta_0 -> 11 N_c/3;
research-leading-colour-structure.md §1), at which every ordering enters
with N_c^n (Born) and N_c^(n+1) (virtual), so the leading-colour virtual over
the leading-colour Born is

    V/B = (alpha_s/4pi) [N_c S1/S0 + c0 + c1/eps],

c1 = -(n-2) 11 N_c/3 (MS-bar coupling renormalisation) and c0 = (n-2) N_c/3
- n N_c/3 (FDH -> CDR at n external gluons), NJet's chsums/NJetRenorm.cpp at
leading colour. The ratio is normalisation-free; the Born is compared through
S0 times the leading colour factor only when ``--born`` is given (the
relative factor between NGluon's trace normalisation and pyAmpliCol's is
recorded, not assumed).

Commands:
  build    compile ngluon_lc.cpp against an NJet 3 build (``build_njet.sh``)
  run      the values at stream points of a G1-harness key
           (``tools/loop_benchmark``), split over ``--jobs`` processes
           (orderings k % jobs == j); JSON record with S0, S1 and V/B
  compare  a ``run`` record against a pyAmpliCol record of V/B at the same
           points (``--pyamplicol``: ``stored_checks.py``/G1 ``physical``
           rows with ``born`` and the virtual's Laurent coefficients)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "njet"))
sys.path.insert(0, str(HERE.parent))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

NC = 3


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(njet_build: Path, out_dir: Path) -> Path:
    """The driver compiled against ``njet_build`` (cached by source digest)."""

    import run_njet

    prefix, pc, _version = run_njet.njet_install(njet_build)
    if pc is None:
        raise SystemExit("the NGluon driver needs an NJet 3 build (pkg-config file)")
    source = HERE / "ngluon_lc.cpp"
    binary = out_dir / f"ngluon_lc-{njet_build.resolve().name}-{_sha(source)[:12]}"
    if binary.exists():
        return binary
    qd = njet_build / "qd" / "prefix" / "lib"
    env = dict(os.environ)
    env["PKG_CONFIG_PATH"] = ":".join([str(qd / "pkgconfig"), str(pc.parent)])
    env["PATH"] = run_njet.PKG_CONFIG + ":" + env["PATH"]
    flags = subprocess.run(
        ["pkg-config", "--cflags", "--libs", pc.stem],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    run_njet.check_build_paths(
        njet_build,
        paths=[f[2:] for f in flags if f[:2] in ("-I", "-L")],
        libraries=sorted((prefix / "lib").glob("lib*.so")),
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "g++",
        "-std=c++17",
        "-O2",
        str(source),
        "-o",
        str(binary),
        *flags,
        f"-Wl,-rpath,{prefix / 'lib'}",
        f"-Wl,-rpath,{qd}",
    ]
    subprocess.run(command, check=True)
    return binary


def ratio(s0: float, s1: list[float], legs: int, alpha_s: float) -> list[float]:
    """V/B = (alpha_s/4pi) [N_c S1/S0 + c0 + c1/eps] (module docstring):
    [finite, single, double]."""

    c1 = -(legs - 2) * Fraction(11, 3) * NC
    c0 = (legs - 2) * Fraction(NC, 3) - legs * Fraction(NC, 3)
    k = alpha_s / (4 * math.pi)
    return [
        k * (NC * s1[0] / s0 + float(c0)),
        k * (NC * s1[1] / s0 + float(c1)),
        k * (NC * s1[2] / s0),
    ]


def command_run(args) -> int:
    from tools.loop_benchmark import pyamplicol_v2, streams

    binary = build(args.njet_build, args.scratch)
    stream = streams.load(args.key)
    legs = len(streams.spec(args.key)["pdgs"])
    if any(int(pdg) != 21 for pdg in streams.spec(args.key)["pdgs"]):
        raise SystemExit("the NGluon driver serves all-gluon rows")
    alpha_s = float(Fraction(pyamplicol_v2._parameters(args.key)["aS"]))
    points = [streams.exact(stream, i) for i in args.points]
    mu = [Fraction(stream["mu_r"][i]) for i in args.points]
    lines = [f"{len(points)} {legs}"]
    for point, scale in zip(points, mu, strict=True):
        lines.append(f"{float(scale)!r}" if args.prec == "double" else _decimal(scale))
        lines += [" ".join(_decimal(Fraction(x)) for x in leg) for leg in point]
    args.scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=args.scratch, suffix=".points", delete=False
    ) as handle:
        handle.write("\n".join(lines) + "\n")
        path = handle.name
    start = time.perf_counter()
    jobs = [
        subprocess.Popen(
            [str(binary), f"points={path}", f"first={j}", f"stride={args.jobs}", f"prec={args.prec}"],
            stdout=subprocess.PIPE,
            text=True,
        )
        for j in range(args.jobs)
    ]
    parts = []
    for job in jobs:
        out, _ = job.communicate()
        if job.returncode:
            raise SystemExit(f"ngluon_lc failed ({job.returncode})")
        # NJet prints its banner on stdout: the records are the JSON lines.
        parts += [json.loads(line) for line in out.splitlines() if line.startswith("{")]
    os.unlink(path)
    rows = []
    for k, index in enumerate(args.points):
        mine = [p for p in parts if p["index"] == k]
        s0 = sum(p["S0"] for p in mine)
        s1 = [sum(p["S1"][c] for p in mine) for c in range(3)]
        rows.append(
            {
                "index": index,
                "orderings": sum(p["orderings"] for p in mine),
                "evaluations": sum(p["evaluations"] for p in mine),
                "S0": s0,
                "S1": s1,
                "virtual_over_born": ratio(s0, s1, legs, alpha_s),
                "core_seconds": round(sum(p["seconds"] for p in mine), 2),
            }
        )
    record = {
        "kind": "ngluon-lc",
        "key": args.key,
        "legs": legs,
        "alpha_s": alpha_s,
        "precision": args.prec,
        "jobs": args.jobs,
        "wall_seconds": round(time.perf_counter() - start, 2),
        "convention": "pyAmpliCol leading colour (n_f degree 0), MS-bar, CDR; "
        "V/B = (alpha_s/4pi)[N_c S1/S0 + c0 + c1/eps]",
        "rows": rows,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(record, indent=1) + "\n")
    print(json.dumps(record, indent=1))
    return 0


def _decimal(value: Fraction) -> str:
    """A decimal text of ``value`` with 40 significant digits."""

    from decimal import Decimal, localcontext

    with localcontext() as context:
        context.prec = 40
        return str(Decimal(value.numerator) / Decimal(value.denominator))


def command_compare(args) -> int:
    ours = json.loads(args.record.read_text())
    theirs = json.loads(args.pyamplicol.read_text())
    reference = {row["index"]: row for row in theirs["checked"]}
    out = []
    worst = 0.0
    for row in ours["rows"]:
        other = reference.get(row["index"])
        if other is None:
            continue
        ((sector, entry),) = other["sectors"].items()
        born = other["born"]
        values = [v / born for v in entry["virtual"]]
        errors = [
            abs(a - b) / max(abs(b), 1e-300)
            for a, b in zip(row["virtual_over_born"], values, strict=True)
        ]
        worst = max(worst, *errors)
        out.append(
            {
                "index": row["index"],
                "sector": sector,
                "ngluon": row["virtual_over_born"],
                "pyamplicol": values,
                "relative": errors,
            }
        )
    print(json.dumps({"rows": out, "worst": worst}, indent=1))
    return 0 if worst <= args.tolerance else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    b = commands.add_parser("build")
    b.add_argument("--njet-build", type=Path, required=True)
    b.add_argument("--scratch", type=Path, required=True)
    r = commands.add_parser("run")
    r.add_argument("key")
    r.add_argument("--points", type=int, nargs="+", default=[0])
    r.add_argument("--jobs", type=int, default=1)
    r.add_argument("--prec", choices=("double", "dd"), default="double")
    r.add_argument("--njet-build", type=Path, required=True)
    r.add_argument("--scratch", type=Path, required=True)
    r.add_argument("--json", type=Path, required=True)
    c = commands.add_parser("compare")
    c.add_argument("record", type=Path)
    c.add_argument("--pyamplicol", type=Path, required=True)
    c.add_argument("--tolerance", type=float, default=1e-8)
    args = parser.parse_args(argv)
    if args.command == "build":
        print(build(args.njet_build, args.scratch))
        return 0
    if args.command == "run":
        return command_run(args)
    return command_compare(args)


if __name__ == "__main__":
    raise SystemExit(main())
