#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Validation of a stored process without a provider (M-FINAL MF-8G-3 (ii)-(v)
and (vii)): one scripted harness, so that a 2->6 row is a pure compute step.

The process is a G1-harness store (``python -m tools.loop_benchmark
pyamplicol KEY --inputs native --store DIR``: the artifact's loop runtime
member with native point inputs and ``generation.json``), loaded as the public
runtime loads it (``pyamplicol_v2.read_store_process``, the G1 harness's
``--load`` loader, nothing regenerated; refused unless generated with the
``--native-build`` given) and
evaluated by its native executor with Catani's prediction formed natively
(``NativeExecutor(catani=True)``: the stored dipole orbits, M-FINAL MF-8G-3).
Stages, each recorded in ``--json`` as it ends (``OUT.DONE`` at the end):

* ``checked`` (binary64 at ``--points``, every pole, the recommended checks
  ``stability.RECOMMENDED_CHECKS``): per point the finite part, the poles,
  the estimate E, (iii) the rotation estimate; (i) the poles against Catani's
  prediction (full colour, a stored Catani record), each deviation <= 10 E
  plus 1e-12 of the prediction (a point without the prediction fails where
  it is required: at full colour by default); (iv) the universal double pole
  -(alpha_s/2pi) sum_i C_i Born (``pyamplicol_v2.universal_double_pole``:
  the leading Casimirs at leading colour), <= 10 E plus 1e-10;
* ``dd`` (v, double-double at ``--dd-points``, every pole, no checks): each
  binary64 Laurent coefficient against double-double within 10 E (plus
  1e-12), and the double-double poles against Catani's double-double
  prediction (1e-12: precision is lax);
* ``ward`` (ii, a store generated on the full tree kernels, ``--kernels
  full``): ``ward.ward_check`` at ``--ward-points`` (binary64 with its
  reduction check) and ``--ward-dd-points``, epsilon_j -> p_j / p_j^0 on
  ``--ward-legs`` (default: three of the stored process's massless vector
  legs, ``ward.gauge_legs``: first, middle and last); a
  binary64 point whose estimate leaves the binary64 scope (O1: E > 1e-9) is
  recorded, not asserted (``asserted``), in both carriers (its conditioning
  carries into double-double, whose Ward bound is fixed), and at least one
  row must be asserted;
* ``rescue`` (vii, ``--rescue-points``): the default rescue policy's level 0
  (``VirtualRescuePolicy().levels[0]``: binary64 with its rotation and the
  rescaled reduction check) and the count of points it sends up (E above
  its target); the policy's double-double level then runs on escalated points
  until ``--rescue-dd`` double-double evaluations are reached (the ``dd``
  stage's points count; default 2, never the arbitrary level).

Usage:
    python tools/loop_benchmark/stored_checks.py STORE --native-build BUILD \\
        [--key KEY] [--points 0 1 2] [--dd-points 0] [--ward-points 0] \\
        [--ward-dd-points] \\
        [--rescue-points 0 ... 15] [--rescue-dd 2] [--threads 16] --json OUT
"""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from fractions import Fraction
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Catani and double-double comparisons: each deviation within ESTIMATES x E
# plus a relative floor of the compared value (precision is lax).
ESTIMATES = 10
CATANI_FLOOR = 1e-12
DOUBLE_POLE_FLOOR = 1e-10
DD_FLOOR = 1e-12


def _peak_gib() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20


def _c(x: Any) -> complex:
    return complex(x)


def _sector(sector: Any) -> str:
    return " ".join(f"{name}^{power}" for name, power in sector)


def point_row(
    result: Any, expected_double: float | None, require_catani: bool = False
) -> dict[str, Any]:
    """One evaluated point (``PointResult``): Born, the virtual per sector and
    Laurent coefficient, E per coefficient (absolute and relative), Catani's
    poles and the deviations, and the double pole over the Born against the
    universal value. With ``require_catani`` a point without Catani's
    prediction fails."""

    born = sum(_c(v).real for v in result.born.values())
    virtual = result.components["virtual"]
    estimate = result.stability
    sectors = {}
    passed = True
    for sector, laurent in virtual.items():
        values = [_c(x).real for x in laurent.coefficients]
        absolute = (
            None
            if estimate is None
            else [abs(float(x)) for x in estimate.absolute[sector].coefficients]
        )
        entry: dict[str, Any] = {"virtual": values, "estimate": absolute}
        poles = (result.ir_poles or {}).get(sector)
        if poles is not None and len(values) == 3:
            catani = [_c(poles[0]).real, _c(poles[1]).real]
            deviations, ok = [], True
            for k in (1, 2):
                deviation = abs(values[k] - catani[k - 1])
                bound = CATANI_FLOOR * abs(catani[k - 1])
                if absolute is not None:
                    bound += ESTIMATES * absolute[k]
                deviations.append(deviation)
                ok = ok and deviation <= bound
            entry.update(catani=catani, catani_deviation=deviations, catani_passed=ok)
            passed = passed and ok
        sectors[_sector(sector)] = entry
    widths = {len(laurent.coefficients) for laurent in virtual.values()}
    double = (
        sum(_c(laurent.coefficients[2]).real for laurent in virtual.values())
        if widths == {3}
        else None
    )
    row: dict[str, Any] = {
        "born": born,
        "sectors": sectors,
        "relative_estimate": None
        if estimate is None
        else float(estimate.relative),
        "catani_formed": result.ir_poles is not None,
    }
    if require_catani and result.ir_poles is None:
        passed = False
    if double is not None and born and expected_double is not None:
        ratio = double / born
        bound = DOUBLE_POLE_FLOOR * abs(expected_double)
        if estimate is not None:
            bound += ESTIMATES * sum(
                abs(float(b.coefficients[2])) for b in estimate.absolute.values()
            ) / abs(born)
        row["double_pole"] = {
            "over_born": ratio,
            "universal": expected_double,
            "deviation": abs(ratio - expected_double),
            "passed": abs(ratio - expected_double) <= bound,
        }
        passed = passed and row["double_pole"]["passed"]
    row["passed"] = passed
    return row


def compare_carriers(
    binary64: Any, dd: Any, require_catani: bool = False
) -> dict[str, Any]:
    """Binary64 against double-double per sector and Laurent coefficient,
    within 10 E of the binary64 point (plus ``DD_FLOOR`` of the value), and
    the double-double poles against its Catani prediction (required with
    ``require_catani``)."""

    out: dict[str, Any] = {
        "born": sum(_c(v).real for v in dd.born.values()),
        "sectors": {},
        "passed": not (require_catani and dd.ir_poles is None),
        "catani_formed": dd.ir_poles is not None,
    }
    for sector, laurent in dd.components["virtual"].items():
        exact = [_c(x).real for x in laurent.coefficients]
        b64 = [_c(x).real for x in binary64.components["virtual"][sector].coefficients]
        absolute = [
            abs(float(x)) for x in binary64.stability.absolute[sector].coefficients
        ]
        deviations = [abs(a - b) for a, b in zip(b64, exact, strict=True)]
        ok = all(
            d <= ESTIMATES * e + DD_FLOOR * abs(x)
            for d, e, x in zip(deviations, absolute, exact, strict=True)
        )
        entry: dict[str, Any] = {
            "double_double": exact,
            "deviation": deviations,
            "within_10E": ok,
        }
        poles = (dd.ir_poles or {}).get(sector)
        if poles is not None:
            catani = [_c(poles[0]).real, _c(poles[1]).real]
            errors = [
                abs(exact[k] - catani[k - 1]) / max(abs(catani[k - 1]), 1e-300)
                for k in (1, 2)
            ]
            entry.update(catani=catani, catani_relative=errors)
            ok = ok and all(e <= DD_FLOOR for e in errors)
        out["sectors"][_sector(sector)] = entry
        out["passed"] = out["passed"] and ok
    return out


def check_process(
    process: Any,
    native: Any,
    key: str,
    accuracy: str,
    *,
    points: list[int],
    dd_points: list[int],
    ward_points: list[int] = (),
    ward_dd_points: list[int] = (),
    ward_legs: list[int] | None = None,
    rescue_points: list[int] = (),
    rescue_dd: int = 2,
    lanes: int = 16,
    threads: int | None = None,
    record: dict[str, Any] | None = None,
    write: Any = None,
    require_catani: bool | None = None,
) -> dict[str, Any]:
    """Every stage (module docstring) on a native process (``NativeProcess``)
    of the G1-harness process ``key`` at colour ``accuracy``; returns the
    record (``write()`` after each stage when given). ``require_catani``
    (default: at full colour) fails the run when the store holds no Catani
    record (``dipoles.catani_record``; a store written before M-FINAL
    MF-8G-3, or a process the stored route does not predict)."""

    from pyamplicol.api.virtual_results import VirtualRescuePolicy
    from pyamplicol.loops.v2.assemble import Precision
    from pyamplicol.loops.v2.stability import RECOMMENDED_CHECKS
    from tools.loop_benchmark import pyamplicol_v2, streams

    # The default rescue policy's binary64 and double-double levels (vii).
    policy = VirtualRescuePolicy()
    level0, level1 = policy.levels[0], policy.levels[1]

    record = {} if record is None else record
    record.setdefault("stages", {})
    record["criteria"] = {
        "estimates": ESTIMATES,
        "catani_floor": CATANI_FLOOR,
        "double_pole_floor": DOUBLE_POLE_FLOOR,
        "dd_floor": DD_FLOOR,
        "rescue_target": level0.target,
    }

    def stage(name: str, begin: float, **extra: Any) -> None:
        record["stages"][name] = {
            "seconds": round(time.perf_counter() - begin, 2),
            "peak_gib": round(_peak_gib(), 2),
            **extra,
        }
        print(key, name, json.dumps(record["stages"][name]), flush=True)
        if write is not None:
            write()

    begin = time.perf_counter()
    executor = process.executor(native, lanes=lanes, threads=threads, catani=True)
    record["catani_record"] = process.record.get("catani") is not None
    if require_catani is None:
        require_catani = accuracy == "full"
    stage(
        "executor",
        begin,
        **(
            {"passed": record["catani_record"], "note": "Catani record required"}
            if require_catani
            else {}
        ),
    )

    stream = streams.load(key)
    parameters = pyamplicol_v2._parameters(key)
    expected = pyamplicol_v2.universal_double_pole(key, accuracy)

    def batch(indices: list[int]) -> tuple[list, list]:
        found = [streams.exact(stream, i) for i in indices]
        scales = [str(Fraction(stream["mu_r"][i]) ** 2) for i in indices]
        return found, scales

    checked: dict[int, Any] = {}
    if points:
        begin = time.perf_counter()
        found, scales = batch(points)
        results = executor.evaluate(
            found,
            scales,
            parameters=parameters,
            precision=Precision.double(),
            stability=RECOMMENDED_CHECKS,
        )
        rows = []
        for index, result in zip(points, results, strict=True):
            checked[index] = result
            rows.append(
                {"index": index, **point_row(result, expected, require_catani)}
            )
        record["checked"] = rows
        stage("checked", begin, points=len(rows), passed=all(r["passed"] for r in rows))

    if dd_points:
        begin = time.perf_counter()
        found, scales = batch(dd_points)
        results = executor.evaluate(
            found,
            scales,
            parameters=parameters,
            precision=Precision.double_double(),
        )
        rows = []
        for index, result in zip(dd_points, results, strict=True):
            row: dict[str, Any] = {"index": index}
            if index in checked:
                row.update(compare_carriers(checked[index], result, require_catani))
            elif require_catani and result.ir_poles is None:
                row.update(passed=False, catani_formed=False)
            rows.append(row)
        record["dd"] = rows
        stage(
            "dd",
            begin,
            points=len(rows),
            passed=all(r.get("passed", True) for r in rows),
        )

    if ward_points or ward_dd_points:
        from pyamplicol.loops.v2 import ward

        legs = ward_legs
        if not legs:
            # The stored process's massless vector legs (a Ward store records
            # them; an older one needs --ward-legs).
            gauge = ward.gauge_legs(executor.slice)
            if not gauge:
                raise SystemExit(
                    "the stored process records no massless vector leg (a Ward "
                    "store of an older tree: pass --ward-legs)"
                )
            legs = sorted({gauge[0], gauge[len(gauge) // 2], gauge[-1]})
        rows = []
        in_scope: dict[int, bool] = {}
        begin = time.perf_counter()
        for carrier, indices in (
            ("double", ward_points),
            ("double-double", ward_dd_points),
        ):
            for index in indices:
                (point,), (scale,) = batch([index])
                found = ward.ward_check(
                    executor,
                    point,
                    scale,
                    carrier,
                    legs=legs,
                    factors=[(1, 0)],
                    parameters=parameters,
                )
                # O1 (as ``ward.ward_row``): binary64 is asserted only where
                # every row's estimate is within its scope (E <= 1e-9 of the
                # physical scale). A point beyond it is recorded, not
                # asserted, in both carriers: its conditioning (binary64 E
                # over the unit roundoff) carries into double-double, whose
                # Ward bound is a fixed 1e-25 of the scale (g g > 4g stream
                # point 1: binary64 E 2.4e-6, double-double residual 1.4e-24
                # = the binary64 one times the carriers' roundoff ratio).
                scope = [
                    r.get("in_scope", True) for r in found["rows"]
                ] if carrier == "double" else None
                if scope is not None:
                    in_scope[index] = all(scope)
                asserted = in_scope.get(index, True)
                rows.append(
                    {
                        "index": index,
                        "carrier": carrier,
                        "legs": list(legs),
                        "asserted": asserted,
                        "passed": found["passed"] if asserted else None,
                        "rows": [
                            {
                                k: v
                                for k, v in r.items()
                                if k
                                in ("leg", "born", "parts", "estimate", "in_scope", "passed")
                            }
                            for r in found["rows"]
                        ],
                    }
                )
        record["ward"] = rows
        verdicts = [r["passed"] for r in rows if r["asserted"]]
        stage(
            "ward",
            begin,
            rows=len(rows),
            asserted=len(verdicts),
            passed=bool(verdicts) and all(verdicts),
        )

    if rescue_points:
        begin = time.perf_counter()
        found, scales = batch(rescue_points)
        results = executor.evaluate(
            found,
            scales,
            parameters=parameters,
            precision=Precision.double(),
            poles="none",
            stability=level0.checks.to_checks(),
        )
        estimates = {
            index: float(result.stability.relative)
            for index, result in zip(rescue_points, results, strict=True)
        }
        up = [i for i, e in estimates.items() if not e <= level0.target]
        rescue: dict[str, Any] = {
            "level0_estimates": estimates,
            "sent_up": up,
            "count": len(up),
            "of": len(estimates),
        }
        record["rescue"] = rescue
        stage("rescue level 0", begin, sent_up=len(up), of=len(estimates))
        # At most ``rescue_dd`` double-double evaluations in all: the dd
        # stage's points count (PLAN MF-8G-3 (vii)).
        budget = max(0, rescue_dd - len(dd_points))
        chosen = [i for i in up if i not in dd_points][:budget]
        if chosen:
            begin = time.perf_counter()
            found, scales = batch(chosen)
            results = executor.evaluate(
                found,
                scales,
                parameters=parameters,
                precision=Precision.double_double(),
                poles="none",
                stability=level1.checks.to_checks(),
            )
            rescue["double_double"] = {
                index: {
                    "estimate": float(result.stability.relative),
                    "met": float(result.stability.relative) <= level1.target,
                    "finite": [
                        _c(v.coefficients[0]).real
                        for v in result.components["virtual"].values()
                    ],
                }
                for index, result in zip(chosen, results, strict=True)
            }
            stage("rescue double-double", begin, points=len(chosen))

    verdicts = [
        info.get("passed")
        for info in record["stages"].values()
        if info.get("passed") is not None
    ]
    record["passed"] = all(verdicts) if verdicts else None
    record["max_rss_gib"] = round(_peak_gib(), 2)
    if write is not None:
        write()
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("store", type=Path, help="a G1-harness --store directory")
    parser.add_argument("--key", help="processes.json key (default: the store's)")
    parser.add_argument("--points", type=int, nargs="*", default=[0, 1, 2])
    parser.add_argument("--dd-points", type=int, nargs="*", help="default: the first")
    parser.add_argument("--ward-points", type=int, nargs="*", default=[])
    parser.add_argument("--ward-dd-points", type=int, nargs="*", default=[])
    parser.add_argument("--ward-legs", type=int, nargs="*")
    parser.add_argument("--rescue-points", type=int, nargs="*", default=[])
    parser.add_argument("--rescue-dd", type=int, default=2)
    parser.add_argument("--lanes", type=int, default=16)
    parser.add_argument("--threads", type=int)
    parser.add_argument(
        "--native-build",
        type=Path,
        required=True,
        help="the staged native build (a store generated with another is refused)",
    )
    parser.add_argument(
        "--no-catani",
        action="store_true",
        help="do not require a stored Catani record at full colour",
    )
    parser.add_argument("--json", type=Path, required=True)
    options = parser.parse_args(argv)

    from pyamplicol.loops.native import load_loop_native
    from tools.loop_benchmark import pyamplicol_v2

    meta = json.loads((options.store / pyamplicol_v2.STORED_META).read_text())
    pyamplicol_v2.check_store_native(meta, options.native_build)
    key = options.key or meta["process"]
    record: dict[str, Any] = {
        "kind": "stored-checks",
        "store": options.store.name,
        "process": key,
        "accuracy": meta["accuracy"],
        "kernels": meta.get("kernels", "production"),
        "native": meta.get("native"),
        "stages": {},
    }

    def write() -> None:
        options.json.parent.mkdir(parents=True, exist_ok=True)
        options.json.write_text(json.dumps(record, indent=1) + "\n")

    begin = time.perf_counter()
    native = load_loop_native()
    process = pyamplicol_v2.read_store_process(options.store, meta)
    record["stages"]["load"] = {
        "seconds": round(time.perf_counter() - begin, 2),
        "peak_gib": round(_peak_gib(), 2),
    }
    print(key, "load", json.dumps(record["stages"]["load"]), flush=True)
    write()
    check_process(
        process,
        native,
        key,
        meta["accuracy"],
        points=options.points,
        dd_points=options.points[:1] if options.dd_points is None else options.dd_points,
        ward_points=options.ward_points,
        ward_dd_points=options.ward_dd_points,
        ward_legs=options.ward_legs,
        rescue_points=options.rescue_points,
        rescue_dd=options.rescue_dd,
        lanes=options.lanes,
        threads=options.threads,
        record=record,
        write=write,
        require_catani=False if options.no_catani else None,
    )
    status = "passed" if record["passed"] in (True, None) else "FAILED"
    Path(f"{options.json}.DONE").write_text(f"{status}\n")
    print(key, "DONE", status, flush=True)
    return 0 if record["passed"] in (True, None) else 1


if __name__ == "__main__":
    raise SystemExit(main())
