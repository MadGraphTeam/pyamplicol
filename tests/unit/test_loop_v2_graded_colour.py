"""Graded colour at one loop: the virtual split by power of N_c
(``SliceRequest.graded``, ``docs/correlator-conventions.md``).

A graded request reports, besides its contracted value, one output per N_c
degree d that its projection keeps (``LoopSlice.graded_degrees``): the
contribution c_d 3^d of that degree to the Born, the counterterm, field and
bare loop components, per squared-order sector. Oracles:

* the sum rule: the degrees of every output add up to the contracted value
  of the same request without grading (``strict-lc``, ``strict-nlc``, and
  full colour), to rounding;
* the N_c scan (``tests/unit/loop_nc_scan.py``): full colour at several
  values of N fixes the exact polynomial in N, whose coefficients are the
  degrees.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "loop" / "legacy"
PARAMETERS = {"aS": "0.118", "MT": "173"}
TOLERANCE = 1e-12


@pytest.fixture(scope="module")
def loop_sm(loop_sm_compiled_model):
    from pyamplicol.models.loading import load_compiled_model

    return load_compiled_model(loop_sm_compiled_model)


@pytest.fixture(scope="module")
def built(loop_sm, loop_native):
    """``(process, born QCD, accuracy, graded) -> ObservableSlice`` with the
    shipped loop_sm colour declaration (QCD Born, QCD correction)."""

    from pyamplicol.loops.v2.assemble import SliceRequest
    from pyamplicol.loops.v2.observables import ObservableSlice
    from pyamplicol.models.loop_color_declaration import (
        resolve_loop_color_declaration,
    )
    from tools.loop_reference import legacy_capture

    declaration = resolve_loop_color_declaration(loop_sm.raw_loop_model)
    cache = {}

    def build(process: str, qcd: int, accuracy: str, graded: bool):
        key = (process, qcd, accuracy, graded)
        if key not in cache:
            projected = accuracy != "full" or graded
            cache[key] = ObservableSlice.generate(
                loop_sm,
                SliceRequest(
                    process,
                    {"QCD": qcd, "QED": 0},
                    {"QCD": qcd + 2, "QED": 0},
                    fixed_parameters=legacy_capture.FIXED_PARAMETERS,
                    accuracy=accuracy,
                    graded=graded,
                    colour_declaration=declaration if projected else None,
                    colour_contraction="direct",
                ),
                loop_native,
            )
        return cache[key]

    return build


def _point(name: str):
    fixture = json.loads((FIXTURES / f"{name}.json").read_text())
    return fixture["points"][0], fixture["scales_squared"][0]


def _flat(result) -> dict:
    """Born per squared order and every component's Laurent coefficients per
    sector, as complex numbers."""

    out = {("born", order): complex(value) for order, value in result.born.items()}
    for name, sectors in result.components.items():
        for sector, laurent in sectors.items():
            for power, value in enumerate(laurent.coefficients):
                out[name, sector, power] = complex(value)
    return out


CASES = [
    ("g g > g g", 2, "gg_gg"),
    ("u u~ > d d~ g", 3, "uux_ddxg"),
]


@pytest.mark.parametrize("accuracy", ["strict-lc", "strict-nlc", "full"])
@pytest.mark.parametrize(("process", "qcd", "fixture"), CASES)
def test_degrees_sum_to_the_contracted_value(built, process, qcd, fixture, accuracy):
    """Every output's degrees add up to the same request without grading."""

    from pyamplicol.loops.v2.assemble import Precision
    from pyamplicol.loops.v2.observables import INCLUSIVE

    point, scale = _point(fixture)
    graded = built(process, qcd, accuracy, True)
    plain = built(process, qcd, accuracy, False)
    split = graded.evaluate_graded(
        point, scale, parameters=PARAMETERS, precision=Precision.double()
    )
    degrees = graded.graded_degrees(None)
    assert degrees and list(degrees) == sorted(degrees, reverse=True)
    assert set(split) == {(INCLUSIVE, d) for d in degrees}
    reference = _flat(
        plain.slice.evaluate(
            point, scale, parameters=PARAMETERS, precision=Precision.double()
        )
    )
    total: dict = {}
    for result in split.values():
        for key, value in _flat(result).items():
            total[key] = total.get(key, 0) + value
    scale_of = max(abs(value) for value in reference.values())
    worst = max(
        abs(total.get(key, 0) - value) / scale_of for key, value in reference.items()
    )
    extra = {key for key in total if key not in reference and abs(total[key]) > 0}
    print(f"{process} {accuracy}: degrees {degrees}, worst {worst:.2e}")
    assert not extra
    assert worst <= TOLERANCE
