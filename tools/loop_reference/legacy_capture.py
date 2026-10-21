#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Freeze the legacy one-loop engine as test oracles for the v2 engine.

DESIGN.md (docs/development/loop_v2) section 14 names two legacy oracles that
must survive the engine swap; this tool captures both for a fixed control set
(``CONTROLS``) and writes them below ``tests/fixtures/loop/legacy/``:

* O1, ``<name>.json``: Born and the six virtual components (virtual, bare, uv,
  r2, uv_local, uv_external_fields) per squared coupling order and Laurent
  coefficient, at every point, in binary64 and in 200-bit arbitrary precision;
  the multisets of matched counterterm and external-field insertions; for the
  controls with ``colour_projections`` also the leading- and next-to-leading
  colour projections with their colour degrees (the committed QCD colour
  declaration; Drell-Yan's control program continues its own couplings).
* O2, ``<name>.families.json.gz``: per denominator family the Born-weighted,
  helicity- and colour-summed numerator coefficients that the legacy engine
  hands to its reducer, at the first point, in both carriers.

Every value is the engine's own decimal output string, so a regeneration with
the same native build reproduces the files byte for byte (``--check``). The
gzip stream is written with a zero timestamp for the same reason, and every
control is captured in a fresh interpreter: Symbolica orders terms by symbol
creation, so earlier work in the same process changes the last bits.

The production legacy path is the generic source compiler
(``prepare_loop_request_model(...).compile``) on MG5_aMC 3.7.0 ``loop_sm`` with
``MB`` fixed to zero, i.e. the providers' ``loop_sm-no_b_mass`` scheme of
``required_processes.json``. Drell-Yan uses the legacy photon-only control
program, matching MadLoop's ``u u~ > e- e+ / z`` reference.

Usage (licensed Symbolica and the staged native module are required)::

    python tools/loop_reference/legacy_capture.py --ufo <MG5>/models/loop_sm
    python tools/loop_reference/legacy_capture.py --ufo ... --process uux_uux --check
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "tests/fixtures/loop/legacy"
COMPONENTS = ("virtual", "bare", "uv", "r2", "uv_local", "uv_external_fields")
# carrier label -> (arithmetic, decimal digits, reduction engine, coefficient engine);
# 60 decimal digits are exactly 200 bits (ceil(60 log2 10)).
CARRIERS = {
    "double": ("double", None, "fast", "jit"),
    "arbitrary-200": ("arbitrary", 60, "generic", "interpreted"),
}
PARAMETERS = {"aS": "0.118", "MT": "173", "MU_R": "1000"}
FIXED_PARAMETERS = {"MB": "0"}
DRELL_YAN_MODEL_VALUES = ("0.118", "132.507")  # alpha_s, 1/alpha
MODEL = "MG5_aMC 3.7.0 loop_sm, MB fixed to 0 (provider scheme loop_sm-no_b_mass)"
SOURCE_ENGINE = "legacy engine: prepare_loop_request_model(loop_sm).compile"
DRELL_YAN_ENGINE = "legacy engine: drell_yan_model_virtual_program (photon only)"
COLOUR_DECLARATION = ROOT / "examples/loop/source_colour/loop_sm_qcd_subset.json"
CONVENTION = (
    "MadLoop/BLHA C_eps=(4pi)^eps/Gamma(1-eps); physical couplings; initial "
    "spin/colour average and final identical-particle factor included. Values are "
    "[real, imaginary] decimal strings; Laurent coefficients are ordered "
    "finite, single pole, double pole."
)
FAMILY_CONVENTION = (
    "Legacy reducer input per family: denominators D_i = (q + V_i)^2 - m_i^2 with "
    "V_i = sum_j shifts[i][j] p_j over the external momenta p_j of the point "
    "(incoming momenta as given, positive energy); the numerator is "
    "sum_a c_a q0^a0 q1^a1 q2^a2 q3^a3 mu2^a4 eps^a5 for the monomial powers a. "
    "Coefficients are Born-weighted (Born colour metric over the initial average), "
    "helicity- and colour-summed, one row per virtual order sector; the legacy "
    "virtual is its postprocess of the summed family reductions."
)


@dataclass(frozen=True, slots=True)
class Control:
    """One control process: pdgs, Born (QCD, QED) powers, points, program kind."""

    process: str
    incoming: tuple[int, ...]
    outgoing: tuple[int, ...]
    born: tuple[int, int]
    points: str
    drell_yan: bool = False
    colour_projections: tuple[str, ...] = ()

    @property
    def born_order_bounds(self):
        return dict(zip(("QCD", "QED"), self.born, strict=True))

    @property
    def loop_order_bounds(self):
        return {"QCD": self.born[0] + 2, "QED": self.born[1]}


# Points: tools/loop_reference/<file>.json (mu_R = 1000 GeV) or the committed
# three-provider references tests/fixtures/loop/required/<name>.json (own mu_R).
CONTROLS = {
    "gg_gg": Control(
        "g g > g g",
        (21, 21),
        (21, 21),
        (2, 0),
        "gluon_scattering_qcd",
        colour_projections=("lc", "nlc"),
    ),
    "uux_ddxg": Control(
        "u u~ > d d~ g",
        (2, -2),
        (1, -1, 21),
        (3, 0),
        "required:uux_ddxg",
        colour_projections=("lc", "nlc"),
    ),
    "uux_ggg": Control(
        "u u~ > g g g",
        (2, -2),
        (21, 21, 21),
        (3, 0),
        "quark_three_gluon_qcd",
        colour_projections=("lc", "nlc"),
    ),
    "dy": Control(
        "u u~ > e- e+ / z",
        (2, -2),
        (11, -11),
        (0, 2),
        "drell_yan_qcd",
        drell_yan=True,
        colour_projections=("lc", "nlc"),
    ),
    "uudd": Control("u u~ > d d~", (2, -2), (1, -1), (2, 0), "uudd_qcd"),
    "tt": Control(
        "u u~ > t t~",
        (2, -2),
        (6, -6),
        (2, 0),
        "top_pair_qcd",
        colour_projections=("lc", "nlc"),
    ),
    "uux_uux": Control("u u~ > u u~", (2, -2), (2, -2), (2, 0), "required:uux_uux"),
    "uux_uuxg": Control(
        "u u~ > u u~ g", (2, -2), (2, -2, 21), (3, 0), "required:uux_uuxg"
    ),
}


def control_points(control: Control) -> tuple[list, list[str]]:
    """Exact decimal points and mu_R^2 per point, as decimal strings."""
    from decimal import Decimal

    if control.points.startswith("required:"):
        name = control.points.split(":", 1)[1]
        path = ROOT / "tests/fixtures/loop/required" / f"{name}.json"
    else:
        path = ROOT / "tools/loop_reference" / f"{control.points}.json"
    data = json.loads(path.read_text(), parse_int=str, parse_float=str)
    points = data["points"]
    mu_r = data.get("mu_r", ["1000"] * len(points))
    scales = [format(Decimal(mu) ** 2, "f") for mu in mu_r]
    return points, scales


def _source_model(ufo: Path, control: Control, *, colour: bool = False):
    from pyamplicol.loops.compiler import prepare_loop_request_model
    from pyamplicol.models.loop_import import load_raw_loop_model

    raw = load_raw_loop_model(str(ufo))
    fixed = dict(FIXED_PARAMETERS)
    declaration = None
    if colour:
        from pyamplicol.loops.source_color_declaration import (
            source_color_fixed_parameters,
        )
        from pyamplicol.models.loop_color_declaration import LoopColorDeclaration

        declaration = LoopColorDeclaration.from_dict(
            json.loads(COLOUR_DECLARATION.read_text())
        )
        fixed = source_color_fixed_parameters(raw, declaration, fixed_parameters=fixed)
    prepared = prepare_loop_request_model(
        raw,
        born_order_bounds=control.born_order_bounds,
        loop_order_bounds=control.loop_order_bounds,
        fixed_parameters=fixed,
    )
    if declaration is None:
        return prepared, None
    from pyamplicol.loops.source_color_declaration import prepare_declared_source_color

    return prepare_declared_source_color(
        prepared, declaration, scheme=declaration.scheme
    )


def _program(ufo: Path, control: Control, *, color_accuracy: str = "full"):
    """Return (virtual program, insertions, field insertions) in binary64."""
    arithmetic, precision, reduction, coefficient = CARRIERS["double"]
    options = {
        "arithmetic": arithmetic,
        "precision": precision,
        "reduction_engine": reduction,
        "coefficient_engine": coefficient,
    }
    if control.drell_yan:
        from pyamplicol.loops.model import build_loop_model
        from pyamplicol.loops.physical_counterterms import (
            drell_yan_model_virtual_program,
        )
        from pyamplicol.models.loop_import import load_raw_loop_model

        source = build_loop_model(load_raw_loop_model(str(ufo)))
        program = drell_yan_model_virtual_program(
            source, color_accuracy=color_accuracy, **options
        )
        return program, program.insertions, program.external_fields
    colour = color_accuracy != "full"
    prepared, source_color = _source_model(ufo, control, colour=colour)
    program = prepared.compile(
        control.incoming,
        control.outgoing,
        selected_corrections=["QCD"],
        parameters=PARAMETERS,
        source_color=source_color,
        color_accuracy=color_accuracy,
        **options,
    )
    return program, program.matched.insertions, program.virtual.external_fields


def _rebind(program, carrier: str):
    arithmetic, precision, reduction, coefficient = CARRIERS[carrier]
    if arithmetic == "double":
        return program
    return program.rebind(
        arithmetic=arithmetic,
        precision=precision,
        reduction_engine=reduction,
        coefficient_engine=coefficient,
    )


def _virtual(program):
    """The NativeModelVirtualProgram of a source program or a legacy control."""
    return getattr(program, "virtual", program)


def _model_values(control: Control):
    return list(DRELL_YAN_MODEL_VALUES) if control.drell_yan else None


def _o1_results(virtual, control: Control, points, scales):
    import numpy as np

    result = virtual.evaluate_ordered_decimal(
        np.asarray(points, dtype=str), scales, model_values=_model_values(control)
    )
    if any(status != "success" for row in result.statuses for _, status in row):
        raise ArithmeticError(f"legacy reduction failed: {result.statuses}")
    record = {"born": result.born.tolist()}
    record.update({name: getattr(result, name).tolist() for name in COMPONENTS})
    return record, result


def _orders(result) -> dict[str, list]:
    return {
        "born": [dict(order) for order in result.born_orders],
        "virtual": [dict(order) for order in result.virtual_orders],
    }


def _multiset(keys) -> list:
    return [[key, count] for key, count in sorted(Counter(keys).items())]


def _insertions(insertions, fields) -> dict[str, list]:
    return {
        "counterterms": _multiset(
            "{}:{}:{}".format(
                insertion.rule.kind,
                "+".join(
                    sorted({entry.vertex_name for entry in insertion.rule.entries})
                ),
                ",".join(map(str, insertion.rule.particle_pdgs)),
            )
            for insertion in insertions
        ),
        "external_fields": _multiset(
            f"leg{insertion.external_index}:{insertion.rule.pdg}"
            for insertion in fields
        ),
    }


def _shift_coefficients(shift, parameters) -> list[int]:
    """Integer coefficients of the external momenta in one exact shift vector."""
    from symbolica import E

    legs = len(parameters) // 4
    coefficients = [
        int(str(shift[0].coefficient(parameters[4 * leg]))) for leg in range(legs)
    ]
    for mu, component in enumerate(shift):
        rebuilt = sum(
            (
                E(str(c)) * parameters[4 * leg + mu]
                for leg, c in enumerate(coefficients)
            ),
            E("0"),
        )
        if (component - rebuilt).expand() != E("0"):
            raise ValueError(
                f"family shift is not a fixed momentum combination: {shift}"
            )
    return coefficients


def _family_layout(bare) -> list[dict[str, Any]]:
    families = []
    for family in bare.families:
        plan = family.kinematics
        n = plan.propagators
        families.append(
            {
                "index": family.index,
                "graphs": len(family.graph_indices),
                "shifts": [
                    _shift_coefficients(shift, plan.momentum_parameters)
                    for shift in plan.shifts
                ],
                "masses_squared": [str(mass) for mass in plan.mass_expressions[:n]],
                "sectors": list(family.sector_indices),
                "powers": [list(power) for power in family.powers],
            }
        )
    return families


def _family_coefficients(virtual, control: Control, point, scale) -> list:
    """Coefficients exactly as the legacy engine passes them to its reducer."""
    import numpy as np

    bare = virtual.bare
    momenta = np.asarray([point], dtype=str)
    currents = bare.prepare_currents_native(
        momenta, [scale], model_values=_model_values(control)
    )
    weights = getattr(bare, "dual_born_weights", None)
    dual = None if weights is None else weights.evaluate_batch(currents.born)
    rows = []
    for family in bare.families:
        values = family.projector.evaluate_batch(
            bare.family_projection_arguments(currents, family, weights=dual)
        ).to_decimal()
        width = len(family.powers)
        rows.append([values[i : i + width] for i in range(0, len(values), width)])
    return rows


def capture(ufo: Path, name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return the O1 and O2 records of one control process."""
    control = CONTROLS[name]
    points, scales = control_points(control)
    program, insertions, fields = _program(ufo, control)
    header = {
        "name": name,
        "process": control.process,
        "pdgs": [*control.incoming, *control.outgoing],
        "engine": DRELL_YAN_ENGINE if control.drell_yan else SOURCE_ENGINE,
        "model": MODEL,
        "parameters": (
            dict(zip(("alpha_s", "inverse_alpha"), DRELL_YAN_MODEL_VALUES, strict=True))
            if control.drell_yan
            else dict(PARAMETERS)
        ),
        "born_order_bounds": control.born_order_bounds,
        "loop_order_bounds": control.loop_order_bounds,
        "carriers": {
            label: {
                "arithmetic": arithmetic,
                "decimal_digits": digits,
                "reduction": reduction,
            }
            for label, (arithmetic, digits, reduction, _) in CARRIERS.items()
        },
        "points": points,
        "scales_squared": scales,
    }
    o1 = {
        **header,
        "convention": CONVENTION,
        "insertions": _insertions(insertions, fields),
    }
    o2 = {**header, "points": points[:1], "scales_squared": scales[:1]}
    o2["convention"] = FAMILY_CONVENTION
    o2["families"] = _family_layout(_virtual(program).bare)
    o1["results"], o2["coefficients"] = {}, {}
    for carrier in CARRIERS:
        virtual = _virtual(_rebind(program, carrier))
        o1["results"][carrier], result = _o1_results(virtual, control, points, scales)
        o1.setdefault("orders", _orders(result))
        o2["coefficients"][carrier] = _family_coefficients(
            virtual, control, points[0], scales[0]
        )
    for accuracy in control.colour_projections:
        program, _, _ = _program(ufo, control, color_accuracy=accuracy)
        projected = {}
        for carrier in CARRIERS:
            virtual = _virtual(_rebind(program, carrier))
            projected[carrier], result = _o1_results(virtual, control, points, scales)
        o1.setdefault("colour_projections", {})[accuracy] = {
            "born_degree": result.born_color_degree,
            "virtual_degree": result.virtual_color_degree,
            "colour_declaration": (
                None if control.drell_yan else str(COLOUR_DECLARATION.relative_to(ROOT))
            ),
            "results": projected,
        }
    return o1, o2


def serialize(o1: dict[str, Any], o2: dict[str, Any]) -> tuple[bytes, bytes]:
    """Deterministic file contents: plain JSON for O1, gzip (mtime 0) for O2."""
    text = (json.dumps(o1, indent=1) + "\n").encode()
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0, filename="") as stream:
        stream.write((json.dumps(o2, separators=(",", ":")) + "\n").encode())
    return text, buffer.getvalue()


def paths(name: str, directory: Path = OUTPUT) -> tuple[Path, Path]:
    return directory / f"{name}.json", directory / f"{name}.families.json.gz"


def _write_or_check(ufo: Path, name: str, directory: Path, check: bool) -> bool:
    contents = serialize(*capture(ufo, name))
    ok = True
    for path, content in zip(paths(name, directory), contents, strict=True):
        if check:
            same = path.is_file() and path.read_bytes() == content
            print(f"{path}: {'identical' if same else 'DIFFERS'}")
            ok &= same
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            print(f"{path}: {len(content)} bytes")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--ufo", type=Path, required=True, help="MG5_aMC 3.7.0 models/loop_sm"
    )
    parser.add_argument(
        "--process", nargs="+", choices=tuple(CONTROLS), default=list(CONTROLS)
    )
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare with the existing files instead of writing",
    )
    args = parser.parse_args()
    if len(args.process) == 1:
        ok = _write_or_check(args.ufo, args.process[0], args.output_dir, args.check)
        return 0 if ok else 1
    # Symbolica's term order depends on the symbols an interpreter has already
    # created, so the last bits of a capture depend on what ran before it in the
    # same process. Each control therefore runs in a fresh interpreter.
    failed = 0
    for name in args.process:
        command = [sys.executable, __file__, "--ufo", str(args.ufo), "--process", name]
        command += ["--output-dir", str(args.output_dir)]
        failed += subprocess.run(command + ["--check"] * args.check).returncode != 0
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
