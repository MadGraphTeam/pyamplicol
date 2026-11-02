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


@pytest.mark.loop_physics
@pytest.mark.parametrize("row", ["A01", "A12"])
def test_degrees_are_the_powers_of_the_nc_scan(
    loop_sm_compiled_model, loop_native, tmp_path, row
):
    """Every degree d of graded ``strict-nlc`` and graded full colour, every
    component and Laurent coefficient (Born included), on native MPFR,
    equals c_d 3^d of the exact N_c fit of full colour (the scan and fit of
    ``test_loop_v2_nc_projection``, rule 7's tolerance 1e-24 per
    coefficient), at the row's campaign point 0; a degree the request keeps
    but does not report has c_d = 0."""

    from dataclasses import replace
    from fractions import Fraction

    from pyamplicol.loops.v2.assemble import Precision
    from pyamplicol.loops.v2.observables import NativeObservables, ObservableSlice
    from pyamplicol.models.loading import load_compiled_model
    from pyamplicol.models.loop_color_declaration import (
        resolve_loop_color_declaration,
    )

    from .loop_nc_scan import scan, slice_request
    from .test_loop_v2_nc_projection import (
        AP_DIGITS,
        CHECK_NODES,
        FIT_NODES,
        SCAN_DIGITS,
        TOLERANCE,
        _entries,
        _exact,
        _result_entries,
        absolute_scale,
        deviation,
        fit,
        row_spec,
        sector_degrees,
        sector_of,
    )

    compiled = load_compiled_model(loop_sm_compiled_model)
    declaration = resolve_loop_color_declaration(compiled.raw_loop_model)
    spec = row_spec(row, (0,))
    alpha_s = _exact(spec["parameters"]["aS"])
    ((point, scale),) = spec["points"]
    graded: dict[str, dict] = {}
    degrees = None
    span = None
    for accuracy in ("strict-nlc", "full"):
        request = replace(
            slice_request(spec, declaration, accuracy, "direct"), graded=True
        )
        observables = ObservableSlice.generate(compiled, request, loop_native)
        if accuracy == "strict-nlc":
            degrees = sector_degrees(observables.slice)
            span = 2 * sum(
                1 for leg in observables.slice.basis.legs if leg.representation != 1
            )
        columns = observables.graded_columns()
        (found,) = NativeObservables(observables, columns).evaluate(
            [point],
            [scale],
            parameters=spec["parameters"],
            precision=Precision.arbitrary(AP_DIGITS),
        )
        graded[accuracy] = {
            column.key[2]: _result_entries(found[column.key]) for column in columns
        }
    top = max(v for v in degrees.values() if v is not None)
    values = (*FIT_NODES[: span + 1], *CHECK_NODES)
    scanned = scan(
        loop_sm_compiled_model, spec, values, f"arbitrary:{SCAN_DIGITS}", tmp_path
    )
    data = {
        n: _entries(
            scanned[n]["results"][0]["born"], scanned[n]["results"][0]["components"]
        )
        for n in values
    }
    coefficients, miss = fit(data, span, top, alpha_s)
    at_three = data["3"]
    three = Fraction(3)
    report = {"fit": float(miss)}
    for accuracy, per_degree in graded.items():
        worst = Fraction(0)
        reported = sorted(per_degree, reverse=True)
        for key, row_c in coefficients.items():
            degree = degrees[sector_of(key)]
            size = absolute_scale(at_three, key, alpha_s)
            for power in set(row_c) | set(per_degree):
                c = row_c.get(power, Fraction(0))
                kept_here = accuracy == "full" or (
                    degree is not None and degree - 2 <= power <= degree
                )
                want = c * three**power if kept_here else Fraction(0)
                got = per_degree.get(power, {}).get(key, Fraction(0))
                worst = max(worst, deviation(got, want, size))
        report[accuracy] = {"degrees": reported, "worst": float(worst)}
        assert worst <= TOLERANCE, (row, accuracy, float(worst))
    print(json.dumps({"row": row, **report}))
    assert miss <= TOLERANCE


@pytest.fixture(scope="module")
def correlated(loop_sm, loop_native):
    """``(accuracy, graded) -> ObservableSlice`` of g g > g g with a dipole
    and a directed two-emission history declared."""

    from pyamplicol.color.connections import EmitGluon
    from pyamplicol.color.correlator_matrices import ColorCorrelator
    from pyamplicol.correlators import CorrelatorConfig
    from pyamplicol.loops.v2.assemble import SliceRequest
    from pyamplicol.loops.v2.observables import ObservableSlice
    from pyamplicol.models.loop_color_declaration import (
        resolve_loop_color_declaration,
    )
    from tools.loop_reference import legacy_capture

    declaration = resolve_loop_color_declaration(loop_sm.raw_loop_model)
    ordered = ColorCorrelator(
        "ordered",
        (EmitGluon(1, -1), EmitGluon(1, -2)),
        (EmitGluon(2, -1), EmitGluon(3, -2)),
    )
    correlators = CorrelatorConfig(
        color_correlations=(ColorCorrelator.dipole("T12", 1, 2), ordered)
    )
    cache = {}

    def build(accuracy: str, graded: bool):
        key = (accuracy, graded)
        if key not in cache:
            cache[key] = ObservableSlice.generate(
                loop_sm,
                SliceRequest(
                    "g g > g g",
                    {"QCD": 2, "QED": 0},
                    {"QCD": 4, "QED": 0},
                    fixed_parameters=legacy_capture.FIXED_PARAMETERS,
                    accuracy=accuracy,
                    graded=graded,
                    colour_declaration=declaration,
                    colour_contraction="direct",
                ),
                loop_native,
                correlators=correlators,
            )
        return cache[key]

    return build


@pytest.mark.parametrize("accuracy", ["strict-nlc", "full"])
def test_correlated_degrees_sum_to_the_correlation(correlated, accuracy):
    """Declared colour correlations (a dipole and a directed history) split
    by power of N_c: per history the degrees (its own, at its complete
    family's degrees) sum to its ungraded value; the native executor's
    graded columns equal the reference's."""

    from pyamplicol.loops.v2.assemble import Precision
    from pyamplicol.loops.v2.observables import INCLUSIVE, NativeObservables

    point, scale = _point("gg_gg")
    histories = (INCLUSIVE, "T12", "ordered")
    graded = correlated(accuracy, True)
    plain = correlated(accuracy, False)
    precision = Precision.double()
    split = graded.evaluate_graded(
        point,
        scale,
        correlations=histories,
        parameters=PARAMETERS,
        precision=precision,
    )
    reference = plain.evaluate(
        point,
        scale,
        correlations=histories,
        parameters=PARAMETERS,
        precision=precision,
    )
    columns = graded.graded_columns(histories)
    (native,) = NativeObservables(graded, columns).evaluate(
        [point], [scale], parameters=PARAMETERS, precision=precision
    )
    for history in histories:
        degrees = graded.graded_degrees(graded.history(history))
        assert degrees and set(split) >= {(history, d) for d in degrees}
        expected = _flat(reference[history])
        total: dict = {}
        for degree in degrees:
            for key, value in _flat(split[history, degree]).items():
                total[key] = total.get(key, 0) + value
        size = max(abs(value) for value in expected.values())
        worst = max(abs(total.get(k, 0) - v) / size for k, v in expected.items())
        lanes = 0.0
        for column in columns:
            if column.key[1] != history:
                continue
            mine = _flat(native[column.key])
            theirs = _flat(split[history, column.key[2]])
            lanes = max(
                lanes,
                max(abs(mine.get(k, 0) - v) / size for k, v in theirs.items()),
            )
        print(
            f"{accuracy} {history}: degrees {degrees}, sum {worst:.2e}, "
            f"native {lanes:.2e}"
        )
        assert worst <= TOLERANCE
        assert lanes <= TOLERANCE
