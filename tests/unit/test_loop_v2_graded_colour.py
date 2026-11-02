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
    sector, in the evaluation's carrier."""

    out = {("born", order): value for order, value in result.born.items()}
    for name, sectors in result.components.items():
        for sector, laurent in sectors.items():
            for power, value in enumerate(laurent.coefficients):
                out[name, sector, power] = value
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


@pytest.mark.parametrize(
    ("process", "qcd", "fixture", "accuracy"),
    [
        ("g g > g g", 2, "gg_gg", "strict-nlc"),
        ("u u~ > d d~ g", 3, "uux_ddxg", "full"),
    ],
)
def test_native_degrees_equal_the_reference(built, process, qcd, fixture, accuracy):
    """The native executor's graded columns (seed records projected
    natively per degree) equal the Python reference path's, in binary64 and
    at 40 digits."""

    from pyamplicol.loops.v2.assemble import Precision
    from pyamplicol.loops.v2.observables import NativeObservables

    point, scale = _point(fixture)
    observables = built(process, qcd, accuracy, True)
    columns = observables.graded_columns()
    native = NativeObservables(observables, columns)
    for precision, tolerance in (
        (Precision.double(), 1e-11),
        (Precision.arbitrary(40), 1e-30),
    ):
        reference = observables.evaluate_graded(
            point, scale, parameters=PARAMETERS, precision=precision
        )
        (found,) = native.evaluate(
            [point], [scale], parameters=PARAMETERS, precision=precision
        )
        assert len(found) == len(reference)
        worst = 0.0
        for column in columns:
            mine = _flat(found[column.key])
            theirs = _flat(reference[column.key[1], column.key[2]])
            size = max(abs(value) for value in theirs.values()) or 1.0
            for key, value in theirs.items():
                worst = max(worst, abs(mine.get(key, 0) - value) / size)
        print(f"{process} {accuracy} {precision}: worst {worst:.2e}")
        assert worst <= tolerance


SCHEME = """
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


def _card(model, output, expression: str, accuracy: str, graded: bool) -> str:
    return f"""
action = "generate"
[model]
source = {json.dumps(str(model))}
[process]
entries = [{{expression={json.dumps(expression)}, name="p"}}]
loop_coupling_orders = ["QCD"]
coupling_order_policy = "minimal"
[color]
accuracy = {json.dumps(accuracy)}
contraction = "direct"
graded = {"true" if graded else "false"}
[loop]
r2_strategy = "model"
[loop.preparation]
fixed_parameters = {{MB = "0"}}
{SCHEME}
[generation]
output = {json.dumps(str(output))}
emit_api_bundle = false
[generation.validation]
post_build_validation = false
samples = 1
"""


@pytest.fixture(scope="module")
def artifact(loop_sm_compiled_model, loop_native, tmp_path_factory):
    """``(expression, accuracy, graded) -> Runtime`` of an artifact generated
    through the public API."""

    from pyamplicol.api import Generator, ProcessRequest, ProcessSet, Runtime
    from pyamplicol.config import resolve_config

    cache = {}

    def get(expression: str, accuracy: str, graded: bool):
        key = (expression, accuracy, graded)
        if key not in cache:
            root = tmp_path_factory.mktemp("graded-artifact")
            output = root / "artifact"
            card = root / "card.toml"
            card.write_text(
                _card(loop_sm_compiled_model, output, expression, accuracy, graded)
            )
            Generator(resolve_config(card)).generate(
                ProcessSet((ProcessRequest.parse(expression, name="p"),)), output
            )
            cache[key] = Runtime.load(output)
        return cache[key]

    return get


def _real(value) -> float:
    """The real part of a public virtual scalar (float, complex or Decimal)."""

    return float(value.real) if isinstance(value, complex) else float(value)


@pytest.mark.parametrize("accuracy", ["strict-nlc", "full"])
def test_public_graded_virtual_sums_to_the_evaluation(artifact, accuracy):
    """``Runtime.evaluate_graded`` of a graded one-loop artifact: one
    evaluation per N_c degree (the physics metadata's contracted components),
    summing to ``evaluate`` of the same artifact; ``evaluate_resolved`` has the
    degrees as its colour axis and the same per-degree values summed over
    helicities."""

    from pyamplicol.api.virtual_results import GradedVirtualEvaluation

    point, scale = _point("gg_gg")
    momenta = (tuple(tuple(float(x) for x in p) for p in point),)
    runtime = artifact("g g > g g", accuracy, True)
    physics = runtime.physics
    degrees = tuple(item.nc_degree for item in physics.contracted_color_components)
    assert degrees and all(degree is not None for degree in degrees)
    graded = runtime.evaluate_graded(momenta, mu_r2=float(scale))
    assert isinstance(graded, GradedVirtualEvaluation)
    assert graded.degrees == degrees
    assert graded.color_ids == tuple(
        item.id for item in physics.contracted_color_components
    )
    total = runtime.evaluate(momenta, mu_r2=float(scale))
    resolved = runtime.evaluate_resolved(momenta, mu_r2=float(scale))
    assert resolved.virtual_color_ids == graded.color_ids
    (sector,) = range(len(total.sectors))
    for epsilon in range(3):
        expected = _real(total.values[0][sector][epsilon])
        summed = sum(
            _real(item.values[0][sector][epsilon]) for item in graded.by_degree
        )
        assert abs(summed - expected) <= 1e-11 * max(abs(expected), 1.0)
        for k, item in enumerate(graded.by_degree):
            per_helicity = sum(
                _real(row[k][epsilon]) for row in resolved.values[0][sector]
            )
            value = _real(item.values[0][sector][epsilon])
            assert abs(per_helicity - value) <= 1e-11 * max(abs(expected), 1.0)
    born = sum(_real(item.born_values[0][0]) for item in graded.by_degree)
    assert abs(born - _real(total.born_values[0][0])) <= 1e-12 * abs(born)
