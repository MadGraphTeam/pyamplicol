# SPDX-License-Identifier: 0BSD
"""The master census of a complex-mass (CM) row (M-SM MS-MASTERS, DESIGN
risk 13): generate the row's slice under the complex-mass scheme, run
``master_census.slice_census`` at its points, and optionally compare the
carriers (binary64, double-double, AP(40) and AP(60)) at some of them, the
check of the ``Float`` route's complex-mass boxes.

    python -m tools.loop_benchmark.master_census_rows ROW OUT [--carriers 0,1]
        [--precisions double,dd,ap40,ap60]

Writes ``OUT/census.json``. CM01 reads ``tests/fixtures/loop/
cms-ufo-standard-gmu.json`` (its finite block), CM10 loop_sm, the other rows
the G_mu UFO and ``tests/fixtures/loop/required/msm/``. Needs the native
extension, the licence and env.sh's model locations. Generation takes 1-6
minutes and up to 8 GB per row (CM07: 5 min, 6 GB); CM07 takes 1.5 min in
double-double and 5 min in AP(40) per point, 15 GB.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import resource
import time
from dataclasses import replace
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from typing import Any

REPOSITORY = Path(__file__).resolve().parents[2]
FIXTURES = REPOSITORY / "tests/fixtures/loop"

#: row -> (kind, fixture, process).
ROWS = {
    "CM01": ("cm01", None, "e- e+ > m- m+"),
    "CM02": ("gmu", "uux_emep_cms", "u u~ > e- e+"),
    "CM03": ("gmu", "udx_epve_cms", "u d~ > e+ ve"),
    "CM04": ("gmu", "gg_ttx_cms", "g g > t t~"),
    "CM05": ("gmu", "uux_emepg_cms", "u u~ > e- e+ g"),
    "CM07": ("gmu", "gg_ttxemepg_cms", "g g > t t~ e- e+ g"),
    "CM08": ("gmu", "udx_epvebbx_cms", "u d~ > e+ ve b b~"),
    "CM09": ("gmu", "udx_epvea_cms", "u d~ > e+ ve a"),
    "CM10": ("cm10", "udx_wpbbx_cms", "u d~ > w+ b b~"),
}
GMU_PARAMETERS = {
    "Gf": "0.0000116639",
    "aS": "0.118",
    "MT": "173.3",
    "MZ": "91.188",
    "MW": "80.419",
    "MH": "125",
}


def _row(row: str, cache: Path) -> tuple[Any, Any, list, list, dict, float]:
    """The row's model, request, points, mu_R^2, parameters and the coupling
    of the campaign metric."""

    from pyamplicol.loops.model_cms import complex_mass_model
    from pyamplicol.loops.v2.assemble import SliceRequest
    from pyamplicol.models.loading import compile_model_source

    kind, fixture, process = ROWS[row]
    # The tests' copy (conftest ``loop_gmu_ufo``): UFOmodeldb's.
    gmu = Path(os.environ["PYAMPLICOL_LOOP_WORKSPACE"]) / (
        "reference/models/ufodb-6ca4b120-patched/loop_qcd_qed_sm_Gmu_py3"
    )
    if kind == "cm01":
        ref = json.loads((FIXTURES / "cms-ufo-standard-gmu.json").read_text())
        compiled = compile_model_source(
            gmu,
            restriction="default",
            cache_dir=cache,
            require_supported=False,
            gauge="feynman",
        )
        fixed = {"MB": "0", "MTA": "0"}
        model, _ = complex_mass_model(compiled, fixed_parameters=fixed, cache_dir=cache)
        fixed = {k: v for k, v in fixed.items() if k in model.parameter_defaults}
        request = SliceRequest(
            process,
            {"QCD": 0, "QED": 2},
            {"QCD": 0, "QED": 4},
            corrections=("QED",),
            fixed_parameters=fixed,
            compatibility="gmu_particle_anti",
            scale_parameter="MU_R",
        )
        block = ref["finite"]
        points = block["points"]
        return (
            model,
            request,
            points,
            ["1000000"] * len(points),
            {**GMU_PARAMETERS, **block["widths"]},
            1 / 132.0,
        )
    ref = json.loads((FIXTURES / "required/msm" / f"{fixture}.json").read_text())
    points = ref["points"]
    scales = [str(Fraction(m) ** 2) for m in ref["mu_r"]]
    if kind == "cm10":
        from tools.loop_reference.model_compatibility import (
            prepare_loop_sm_scalar_declarations,
        )

        compiled = compile_model_source(
            Path(os.environ["PYAMPLICOL_NLO_UFO_REFERENCE"]),
            restriction=ref["restriction"],
            cache_dir=cache,
        )
        compiled = replace(
            compiled,
            raw_loop_model=prepare_loop_sm_scalar_declarations(
                compiled.raw_loop_model
            ).derived,
            _serialized_path=None,
            _prepared_bundle=None,
        )
        model, _ = complex_mass_model(
            compiled, fixed_parameters=ref["fixed_parameters"], cache_dir=cache
        )
        fixed = {
            k: v
            for k, v in ref["fixed_parameters"].items()
            if k in model.parameter_defaults
        }
        request = SliceRequest(
            process, ref["born_orders"], ref["loop_orders"], fixed_parameters=fixed
        )
    else:
        compiled = compile_model_source(
            gmu,
            restriction=ref["restriction"],
            cache_dir=cache,
            require_supported=False,
            gauge="feynman",
        )
        widths = {k: v for k, v in ref["fixed_parameters"].items() if k.startswith("W")}
        model, _ = complex_mass_model(
            compiled, fixed_parameters=widths, cache_dir=cache
        )
        fixed = {
            k: v
            for k, v in ref["fixed_parameters"].items()
            if k in model.parameter_defaults
        }
        madloop = ref["process"]
        corrections = tuple(sorted(madloop.split("[virt=")[1].split("]")[0].split()))
        born = {"QCD": 0, "QED": 0, **ref["born_orders"]}
        if "^2==" in madloop:
            loops: Any = dict(ref["loop_orders"])
        else:
            loops = tuple({**born, c: born[c] + 2} for c in corrections)
            loops = loops[0] if len(loops) == 1 else loops
        request = SliceRequest(
            process,
            ref["born_orders"],
            loops,
            corrections=corrections,
            fixed_parameters=fixed,
            compatibility="gmu_particle_anti",
            scale_parameter="MU_R",
        )
    parameters = {
        k: v
        for k, v in ref["parameters"].items()
        if k in model.parameter_defaults and k not in fixed
    }
    coupling = float(parameters.get("aS", 0.118)) if kind == "cm10" else 1 / 132.0
    return model, request, points, scales, parameters, coupling


def _values(result) -> dict[str, list[Decimal]]:
    """The Born and the virtual's Laurent coefficients per sector."""

    def real(value: Any) -> Decimal:
        part = value.real if hasattr(value, "real") else value
        return Decimal(repr(part)) if isinstance(part, float) else Decimal(str(part))

    values = {"born": [sum(real(v) for v in result.born.values())]}
    for sector, laurent in result.components["virtual"].items():
        values[str(sorted(dict(sector).items()))] = [
            real(x) for x in laurent.coefficients
        ]
    return values


def _difference(mine, theirs, coupling: float) -> float:
    """The largest coefficient difference in the campaign metric: relative,
    against max(|value|, |Born| coupling / 2 pi)."""

    with localcontext(prec=90):
        flux = abs(theirs["born"][0]) * Decimal(coupling) / Decimal(2 * math.pi)
        return float(
            max(
                abs(a - b) / max(abs(b), flux)
                for key, values in theirs.items()
                for a, b in zip(mine[key], values, strict=True)
            )
        )


def main(argv: list[str] | None = None) -> None:
    from pyamplicol.loops.native import load_loop_native
    from pyamplicol.loops.v2.assemble import LoopSlice, Precision
    from pyamplicol.loops.v2.native_trees import NativeExportUnsupported
    from pyamplicol.loops.v2.plan_export import NativeExecutor
    from tools.loop_benchmark.master_census import slice_census

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("row", choices=sorted(ROWS))
    parser.add_argument("out", type=Path)
    parser.add_argument(
        "--carriers",
        help="comma-separated point indices at which to compare the carriers",
    )
    parser.add_argument(
        "--precisions",
        default="double,dd,ap40,ap60",
        help="comma-separated carriers among double, dd, ap40, ap60; the last "
        "is the reference",
    )
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    start = time.time()

    def log(*items: Any) -> None:
        print(f"[{time.time() - start:7.1f}s]", *items, flush=True)

    model, request, points, scales, parameters, coupling = _row(
        args.row, args.out / "cache"
    )
    slice_ = LoopSlice.generate(model, request, load_loop_native())
    log(
        "generated; maxrss GB", resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
    )
    try:
        executor = NativeExecutor(slice_, inputs="native")
    except NativeExportUnsupported as refusal:
        # The census needs the plan's families and masses only; the carriers
        # then run with Python point inputs.
        log("native export refused, Python inputs:", refusal)
        executor = NativeExecutor(slice_, inputs="python")
    found = slice_census(executor, points, scales, parameters)
    record: dict[str, Any] = {
        "row": args.row,
        "points": len(points),
        "families": len(executor.exported.program["families"]),
        "census": found.record(),
    }
    log("census", json.dumps(record["census"]))
    if args.carriers:
        chosen = [int(k) for k in args.carriers.split(",")]
        at = [points[k] for k in chosen], [scales[k] for k in chosen]
        known = {
            "double": Precision.double(),
            "dd": Precision.double_double(),
            "ap40": Precision.arbitrary(40),
            "ap60": Precision.arbitrary(60),
        }
        carriers = [(name, known[name]) for name in args.precisions.split(",")]
        runs = {}
        for name, precision in carriers:
            began = time.time()
            results = executor.evaluate(*at, parameters=parameters, precision=precision)
            runs[name] = [_values(result) for result in results]
            log(name, "evaluated in", round(time.time() - began, 1), "s")
        reference = carriers[-1][0]
        record["agreement"] = {
            f"{name}-vs-{reference}": max(
                _difference(mine, theirs, coupling)
                for mine, theirs in zip(runs[name], runs[reference], strict=True)
            )
            for name, _ in carriers[:-1]
        } | {"points": chosen}
        log("agreement", record["agreement"])
    (args.out / "census.json").write_text(json.dumps(record, indent=1))


if __name__ == "__main__":
    main()
