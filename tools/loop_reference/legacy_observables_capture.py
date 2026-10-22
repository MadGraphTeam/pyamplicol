#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Freeze the legacy engine's observables as O1 oracles of the v2 engine.

DESIGN.md (docs/development/loop_v2) section 14, O1, lists directed colour
correlations, spin sources, resolved outputs and flavour members among the
frozen legacy outputs; ``legacy_capture.py`` freezes the inclusive ones. This
tool captures the observables through the legacy public pipeline (``Generator``
with a ``CorrelatorConfig``, ``Runtime.evaluate_correlated_many`` and
``Runtime.evaluate_resolved``) for the controls in ``CONTROLS`` and writes
``tests/fixtures/loop/legacy/observables/<name>.json``:

* ``directed``: per colour history the correlated Born and the virtual's
  Laurent coefficients per squared-order sector (complex, ordered histories
  included), every history evaluated on ordinary helicities;
* ``spin``: per declared spin class the Born and the virtual with literal
  complex source vectors (one vector per leg and point);
* ``resolved``: per Born helicity row the Born and the virtual summed over the
  legacy colour components (legacy anchors are canonical diagram colour
  tensors; v2 anchors Born basis elements, design §1.6 decision 3, so only
  the helicity axis and the totals are comparable);
* ``members``: for a flavour-blind group, the member process's directed and
  spin outputs evaluated through the admitted representative.

The legacy engine refuses ordered two-emission histories on gg -> gg and on
uu~ -> ggg ("formal color overlap retained unsupported tensors"), so ordered
histories are captured on d d~ > g g only.

Values are the runtime's decimal strings, in binary64 and at 60 decimal digits
(200 bits). Model: MG5_aMC 3.7.0 ``loop_sm`` with the ``no_b_mass``
restriction, alpha_s = 0.118 and MT = 173 (the defaults of the restricted card),
model R2, full colour.

Usage (licensed Symbolica and the staged native module are required)::

    python tools/loop_reference/legacy_observables_capture.py --ufo <MG5>/models/loop_sm
    python tools/loop_reference/legacy_observables_capture.py --ufo ... --control gg_gg
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "tests/fixtures/loop/legacy/observables"
# carrier label -> (arithmetic, decimal digits)
CARRIERS = {"double": ("double", 16), "arbitrary-200": ("arbitrary", 60)}
PARAMETERS = {"aS": "0.118", "MT": "173"}
ENGINE = (
    "legacy public pipeline: Generator(...).generate(..., correlators=...); "
    "Runtime.evaluate_correlated_many / evaluate_resolved"
)
MODEL = "MG5_aMC 3.7.0 loop_sm, restriction no_b_mass (MB = 0), aS 0.118, MT 173"
CONVENTION = (
    "MadLoop/BLHA C_eps=(4pi)^eps/Gamma(1-eps); physical couplings; initial "
    "spin/colour average and final identical-particle factor included, also for "
    "spin sources and resolved entries. Values are [real, imaginary] decimal "
    "strings; Laurent coefficients are ordered finite, single pole, double pole. "
    "A directed history (bra, ket) is B^dagger K_BL L + L^dagger K_LB B. Spin "
    "vectors are literal complex four-vectors replacing the leg's wavefunction "
    "(crossing phase only)."
)
# Two literal complex four-vectors (not transverse, not normalised).
VECTORS = (
    (("0.1", "0.2"), ("0.8", "-0.3"), ("0.4", "1"), ("-0.6", "0.5")),
    (("-0.3", "0.7"), ("-0.2", "0.8"), ("0.6", "0.1"), ("0.5", "-0.4")),
)


@dataclass(frozen=True)
class Control:
    """One captured process (or flavour group)."""

    entries: tuple[tuple[str, str], ...]  # (name, process); the first represents
    born_qcd: int
    points: str
    histories: tuple[dict[str, Any], ...] = ()
    spin_classes: tuple[tuple[int, ...], ...] = ()
    resolved: bool = False
    # "full", or "lc"/"nlc" with the committed QCD colour continuation.
    accuracy: str = "full"

    @property
    def flavour_group(self) -> bool:
        return len(self.entries) > 1


def _emit(emitter: int, emitted: int) -> dict[str, Any]:
    return {"kind": "emit-gluon", "emitter": emitter, "emitted": emitted}


def _dipole(name: str, i: int, j: int) -> dict[str, Any]:
    return {"id": name, "bra": [_emit(i, -1)], "ket": [_emit(j, -1)]}


ORDERED = {
    "id": "ordered",
    "bra": [_emit(1, -1), _emit(1, -2)],
    "ket": [_emit(2, -1), _emit(3, -2)],
}
SWAPPED = {"id": "swapped", "bra": ORDERED["ket"], "ket": ORDERED["bra"]}

CONTROLS = {
    "gg_gg": Control(
        (("gg", "g g > g g"),),
        2,
        "gluon_scattering_qcd",
        (_dipole("casimir", 1, 1), _dipole("T12", 1, 2), _dipole("T34", 3, 4)),
        ((3,), (3, 4)),
        resolved=True,
    ),
    "ddgg_ssgg": Control(
        (("ddgg", "d d~ > g g"), ("ssgg", "s s~ > g g")),
        2,
        "uudd_qcd",
        (_dipole("casimir", 1, 1), ORDERED, SWAPPED),
        ((3,), (3, 4)),
    ),
    # uu~ -> ggg in two captures (the legacy generation of directed histories
    # and spin classes together takes hours at five legs).
    "uux_ggg": Control(
        (("uuggg", "u u~ > g g g"),),
        3,
        "quark_three_gluon_qcd",
        (_dipole("T12", 1, 2), _dipole("T35", 3, 5)),
        resolved=True,
    ),
    "uux_ggg_spin": Control(
        (("uuggg", "u u~ > g g g"),),
        3,
        "quark_three_gluon_qcd",
        spin_classes=((3,), (4, 5)),
    ),
    # Directed histories at LC and NLC (complete-family degree convention).
    **{
        f"gg_gg_{accuracy}": Control(
            (("gg", "g g > g g"),),
            2,
            "gluon_scattering_qcd",
            (_dipole("casimir", 1, 1), _dipole("T12", 1, 2), _dipole("T13", 1, 3)),
            accuracy=accuracy,
        )
        for accuracy in ("lc", "nlc")
    },
    "uux_ggg_lc": Control(
        (("uuggg", "u u~ > g g g"),),
        3,
        "quark_three_gluon_qcd",
        (_dipole("T12", 1, 2), _dipole("T13", 1, 3), _dipole("T35", 3, 5)),
        accuracy="lc",
    ),
}
COLOUR_DECLARATION = ROOT / "examples/loop/source_colour/loop_sm_qcd_subset.json"


def control_points(control: Control) -> tuple[list, list[str]]:
    from decimal import Decimal

    path = ROOT / "tools/loop_reference" / f"{control.points}.json"
    data = json.loads(path.read_text(), parse_int=str, parse_float=str)
    points = data["points"][:2]
    mu_r = data.get("mu_r", ["1000"] * len(points))[: len(points)]
    return points, [format(Decimal(mu) ** 2, "f") for mu in mu_r]


def _card(model: Path, output: Path, control: Control) -> str:
    entries = ",\n           ".join(
        f'{{expression="{process}", name="{name}"}}'
        for name, process in control.entries
    )
    flavour = "\nflavor_blind = true" if control.flavour_group else ""
    return f"""
action = "generate"
[model]
source = {json.dumps(str(model))}
[process]
entries = [{entries}]
max_coupling_orders = {{QCD={control.born_qcd}, QED=0}}{flavour}
loop_coupling_orders = ["QCD"]
coupling_order_policy = "minimal"
[color]
accuracy = "{control.accuracy}"
contraction = "direct"
[loop]
r2_strategy = "model"{_loop_model(control)}[generation]
output = {json.dumps(str(output))}
emit_api_bundle = false
[generation.validation]
post_build_validation = true
samples = 2
relative_tolerance = 3e-9
absolute_tolerance = 2e-12
"""


def _loop_model(control: Control) -> str:
    """The loop model declaration of a full-colour card (the colour-declared
    model of an LC/NLC control carries its own)."""

    if control.accuracy != "full":
        return "\n"
    return """
[loop.model]
loop_coupling_orders = ["QCD"]
uv_complete = true
model_r2_complete = true
[loop.model.scheme]
dimensional_regularization = "HV"
external_states = "physical-four-dimensional"
gamma5 = "source-UFO-four-dimensional-prescription"
renormalization = "source-UFO mass-dependent decoupling"
mass_scheme = "real-on-shell"
finite_restoration = "source-UFO-local-rules"
model_convention = "loop_sm lhv=1 supplied QCD rules"
"""


def _model(ufo: Path, root: Path, control: Control) -> Path:
    """loop_sm (MB = 0) with its scalar declarations; for an LC/NLC control
    also the committed QCD colour continuation (as
    ``examples/loop/source_colour/prepare_model.py`` declares it)."""

    from pyamplicol.loops.model_compatibility import prepare_loop_sm_scalar_declarations
    from pyamplicol.models.loading import compile_model_source

    model = compile_model_source(
        str(ufo), restriction="no_b_mass", cache_dir=root / "model-cache"
    )
    model = replace(
        model,
        raw_loop_model=prepare_loop_sm_scalar_declarations(
            model.raw_loop_model
        ).derived,
        _serialized_path=None,
        _prepared_bundle=None,
    )
    if control.accuracy != "full":
        from pyamplicol.models.loop_color_declaration import (
            LoopColorDeclaration,
            with_loop_color_declaration,
        )
        from pyamplicol.models.loop_declaration import (
            LoopModelDeclaration,
            with_loop_model_declaration,
        )

        data = LoopColorDeclaration.from_dict(
            json.loads(COLOUR_DECLARATION.read_text())
        )
        model = with_loop_model_declaration(
            model, LoopModelDeclaration(data.scheme, ("QCD",), True, True)
        )
        model = with_loop_color_declaration(model, data)
    return model.write(root / "model.json")


def _generate(model: Path, output: Path, control: Control, correlators) -> None:
    from pyamplicol.api import Generator, ProcessRequest, ProcessSet
    from pyamplicol.config import resolve_config

    card = output.parent / f"{output.name}.toml"
    card.write_text(_card(model, output, control))
    requests = ProcessSet(
        tuple(
            ProcessRequest.parse(process, name=name)
            for name, process in control.entries
        )
    )
    Generator(resolve_config(card)).generate(requests, output, correlators=correlators)


def _pair(value: Any) -> list[str]:
    real = getattr(value, "real", value)
    imag = getattr(value, "imag", 0)
    return [str(real), str(imag)]


def _correlated(result) -> dict[str, Any]:
    return {
        "born": [[_pair(x) for x in row] for row in result.born_values],
        "virtual": [
            [[_pair(x) for x in sector] for sector in row] for row in result.values
        ],
    }


def _spin_vectors(legs: tuple[int, ...], count: int) -> dict[int, list]:
    return {
        leg: [[list(c) for c in VECTORS[i % len(VECTORS)]] for _ in range(count)]
        for i, leg in enumerate(legs)
    }


def _observables(runtime, control: Control, points, scales) -> dict[str, Any]:
    from pyamplicol import CorrelatedRequest

    out: dict[str, Any] = {}
    if control.histories:
        ids = ("born", *(item["id"] for item in control.histories))
        grouped = runtime.evaluate_correlated_many(
            points, {name: CorrelatedRequest(name, {}) for name in ids}, mu_r2=scales
        )
        out["directed"] = {name: _correlated(grouped[name]) for name in ids}
    if control.spin_classes:
        requests = {
            ",".join(map(str, legs)): CorrelatedRequest(
                "born", _spin_vectors(legs, len(points))
            )
            for legs in control.spin_classes
        }
        grouped = runtime.evaluate_correlated_many(points, requests, mu_r2=scales)
        out["spin"] = {name: _correlated(value) for name, value in grouped.items()}
    return out


def _resolved(runtime, points, scales) -> dict[str, Any]:
    """Per Born helicity row, the Born [order] and the virtual [sector][eps]
    summed over the legacy colour components."""

    result = runtime.evaluate_resolved(points, mu_r2=scales)
    helicities = [list(h.values) for h in runtime.physics.helicities]
    rows = range(len(helicities))
    born = [
        [[_pair(sum(order[h])) for h in rows] for order in point]
        for point in result.born_values
    ]
    virtual = [
        [
            [
                [_pair(sum(colour[e] for colour in sector[h])) for e in range(3)]
                for h in rows
            ]
            for sector in point
        ]
        for point in result.values
    ]
    return {
        "helicities": helicities,
        "born_colour_ids": list(result.born_color_ids),
        "virtual_colour_ids": list(result.virtual_color_ids),
        "born": born,
        "virtual": virtual,
    }


def capture(ufo: Path, name: str) -> dict[str, Any]:
    from pyamplicol import CorrelatorConfig, Runtime
    from pyamplicol.color.correlator_matrices import ColorCorrelator
    from pyamplicol.correlators import _emission_from_json

    control = CONTROLS[name]
    points, scales = control_points(control)
    record: dict[str, Any] = {
        "name": name,
        "processes": [list(entry) for entry in control.entries],
        "engine": ENGINE,
        "model": MODEL,
        "parameters": dict(PARAMETERS),
        "points": points,
        "scales_squared": scales,
        "convention": CONVENTION,
        "histories": list(control.histories),
        "spin_classes": [list(legs) for legs in control.spin_classes],
        "spin_vectors": [[list(c) for c in vector] for vector in VECTORS],
        "accuracy": control.accuracy,
        "colour_declaration": None
        if control.accuracy == "full"
        else str(COLOUR_DECLARATION.relative_to(ROOT)),
        "results": {},
    }
    with tempfile.TemporaryDirectory(prefix="legacy-observables-") as temporary:
        root = Path(temporary)
        model = _model(ufo, root, control)
        correlators = None
        if control.histories or control.spin_classes:
            correlators = CorrelatorConfig(
                color_correlations=tuple(
                    ColorCorrelator(
                        item["id"],
                        tuple(map(_emission_from_json, item["bra"])),
                        tuple(map(_emission_from_json, item["ket"])),
                    )
                    for item in control.histories
                ),
                spin_correlations=control.spin_classes,
            )
            correlated = root / "correlated"
            _generate(model, correlated, control, correlators)
        if control.resolved:
            resolved = root / "resolved"
            _generate(model, resolved, control, None)
        for carrier, (arithmetic, precision) in CARRIERS.items():
            out: dict[str, Any] = {}
            for process_name, _process in control.entries:
                entry: dict[str, Any] = {}
                if correlators is not None:
                    runtime = Runtime.load(
                        correlated,
                        process=process_name,
                        arithmetic=arithmetic,
                        precision=precision,
                        model_parameters=PARAMETERS,
                    )
                    entry.update(_observables(runtime, control, points, scales))
                if control.resolved:
                    runtime = Runtime.load(
                        resolved,
                        process=process_name,
                        arithmetic=arithmetic,
                        precision=precision,
                        model_parameters=PARAMETERS,
                    )
                    entry["resolved"] = _resolved(runtime, points, scales)
                out[process_name] = entry
            record["results"][carrier] = out
        if control.flavour_group:
            from pyamplicol.artifacts import load_manifest

            manifest = load_manifest(correlated)
            processes = manifest.extensions["generation"]["concrete_processes"]
            record["flavour_grouping"] = [
                item["filters"]["flavor_grouping"] for item in processes
            ]
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ufo", type=Path, required=True)
    parser.add_argument(
        "--control", nargs="+", choices=tuple(CONTROLS), default=list(CONTROLS)
    )
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if len(args.control) == 1:
        record = capture(args.ufo, args.control[0])
        path = args.output_dir / f"{args.control[0]}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=1) + "\n")
        print(f"{path}: {path.stat().st_size} bytes")
        return 0
    # One fresh interpreter per control (Symbolica term order, see legacy_capture).
    failed = 0
    for name in args.control:
        command = [sys.executable, __file__, "--ufo", str(args.ufo), "--control", name]
        command += ["--output-dir", str(args.output_dir)]
        failed += subprocess.run(command).returncode != 0
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
