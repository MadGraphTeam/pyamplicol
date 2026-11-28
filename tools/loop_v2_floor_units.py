#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Measure the unit count of a loop-induced estimate's first-order floor.

A loop-induced output's floor (``loops.v2.induced.floor``) is
eps1 (N S' + S N') + eps2^2 S S' with eps1 = BILINEAR_FLOOR_UNITS u and
eps2 = FLOOR_UNITS u: its first-order term bounds the first-order error of
each amplitude that the stability checks do not sample, |delta a| <= eps1 S
(S the row's term floor). That error is not only the roundings the floor
names: a rotation cannot see an error in a rotation-invariant quantity (a
master integral, a reduction coefficient built from invariants), and the
reduction checks under-measure the reduction's own error, so the unit count
is a measured bound. This tool measures it.

``run`` evaluates the points of a loop-induced artifact in binary64 with
the given checks and in double-double at exactly the same inputs (each
binary64 momentum component as its exact decimal expansion, the kinematics
improvement off, so that both carriers evaluate one point) and writes one
JSON line per point: the binary64 value, its relative estimate E, the
checks' relative budgets and the double-double value.

``table`` reads such lines and gives, per file and unit count k (powers of
4), the points whose double-double error exceeds E(k) = SAFETY x sampled +
(E - SAFETY x sampled) x k / K, with K the unit count of the build that
wrote the lines (the first-order floor scales like k; the second-order term
matters only at exact zeros), and the largest error / E(k). A record whose
floor part is zero (an estimate carried by its checks alone) is a miss no
unit count cures: counted apart.

Usage:
    python tools/loop_v2_floor_units.py run ARTIFACT POINTS.json OUT.jsonl
        [--reduction tirust|ninjars] [--checks rotation|recommended]
        [--mu-r2 VALUE] [--batch N]
    python tools/loop_v2_floor_units.py table OUT.jsonl... [--units K]

POINTS.json holds a list of points, each a list of momenta (E, px, py, pz)
as binary64 numbers.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from decimal import Decimal
from pathlib import Path

SAFETY = 2.0
GRID = tuple(4**n for n in range(2, 11))


def _sampled(checks: dict[str, float]) -> float:
    rotated = max([v for k, v in checks.items() if k.startswith("rotation")] or [0.0])
    return SAFETY * (rotated + sum(v for k, v in checks.items() if not k.startswith("rotation")))


def run(options) -> int:
    from pyamplicol import Runtime
    from pyamplicol.api.virtual_results import VirtualStabilityChecks

    points = json.loads(Path(options.points).read_text())
    runtime = Runtime.load(options.artifact)
    checks = (
        VirtualStabilityChecks(1, True, rescaled=True)
        if options.checks == "recommended"
        else VirtualStabilityChecks(1)
    )
    common = {
        "mu_r2": None,
        "poles": "none",
        "on_failure": "return",
        "reduction": options.reduction,
        "kinematics_improvement": "off",
    }
    with open(options.out, "a") as out:
        for first in range(0, len(points), options.batch):
            chunk = [
                [[Decimal(float(x)) for x in momentum] for momentum in point]
                for point in points[first : first + options.batch]
            ]
            common["mu_r2"] = [options.mu_r2] * len(chunk)
            checked = runtime.evaluate(chunk, stability_checks=checks, **common)
            truth = runtime.evaluate(chunk, arithmetic="double-double", **common)
            for k in range(len(chunk)):
                value, reference = checked.values[k], truth.values[k]
                estimate = None if checked.stability is None else checked.stability[k]
                out.write(
                    json.dumps(
                        {
                            "index": first + k,
                            "value": None if value is None else str(value[0].finite),
                            "reference": None if reference is None else str(reference[0].finite),
                            "estimate": None if estimate is None else estimate.relative,
                            "checks": None if estimate is None else dict(estimate.checks),
                        }
                    )
                    + "\n"
                )
    return 0


def table(options) -> int:
    for name in options.records:
        records = []
        for line in Path(name).read_text().splitlines():
            r = json.loads(line)
            if r["value"] is None or r["reference"] is None or r["estimate"] is None:
                continue
            reference = Decimal(r["reference"])
            if not reference:
                continue
            error = float(abs(Decimal(r["value"]) - reference) / abs(reference))
            sampled = _sampled(r["checks"])
            records.append((error, sampled, max(r["estimate"] - sampled, 0.0)))
        cured = [x for x in records if x[2] > 0]
        stuck = [x for x in records if x[2] == 0 and x[0] > x[1]]
        print(f"{name}: {len(records)} points; misses with no floor part (no count cures): {len(stuck)}")
        for k in GRID:
            ratios = [e / (s + f * k / options.units) for e, s, f in cured]
            misses = sum(r > 1 for r in ratios)
            print(f"  k = {k:8d}: misses {misses:6d}, largest error / E {max(ratios, default=0.0):.3g}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    commands = parser.add_subparsers(dest="command", required=True)
    runner = commands.add_parser("run")
    runner.add_argument("artifact")
    runner.add_argument("points")
    runner.add_argument("out")
    runner.add_argument("--reduction", choices=("tirust", "ninjars"), default="tirust")
    runner.add_argument("--checks", choices=("rotation", "recommended"), default="recommended")
    runner.add_argument("--mu-r2", default="8315.251344")
    runner.add_argument("--batch", type=int, default=8)
    tabler = commands.add_parser("table")
    tabler.add_argument("records", nargs="+")
    tabler.add_argument("--units", type=float, default=2.0**16)
    options = parser.parse_args(argv)
    return run(options) if options.command == "run" else table(options)


if __name__ == "__main__":
    sys.exit(main())
