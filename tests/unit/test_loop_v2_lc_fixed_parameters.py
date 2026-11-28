# SPDX-License-Identifier: 0BSD
"""Leading colour with fixed parameters.

The counterterm couplings of a leading- or next-to-leading-colour request are
graded by N_c in exact arithmetic (``ct_recursion.lower_model_counterterms``),
and the formal-colour preparation hands the fixed parameters on as
``(real, imaginary)`` decimal pairs (``source_color_fixed_parameters``).

* A fixed parameter's decimal value (``fixed_parameters``, e.g.
  ``MT = 173.3``) must reach the grading as an exact number, as the scalar
  bindings lower it; written as a binary64 float it made the grading fail
  (``N_c grading of the coupling failed: exact expressions reject floating
  numeric atoms``, ``unlowered-counterterm``). In full colour the same float
  capped the counterterm coefficients at binary64 precision.
* ``ew_policy.is_zero`` must read such a pair (a fixed MZ raised
  ``decimal.InvalidOperation`` while classifying the Z at LC and NLC).

The sweep fixes one parameter of every kind a user can fix on loop_sm (a
boson mass, a width, a coupling input, a quark mass zero and nonzero) in a
process that reads it, at LC, NLC and full colour: the request generates and
its values equal those of the same request with the parameter set at run
time. loop_sm declares no complex external parameter.
"""

from __future__ import annotations

from decimal import Decimal, getcontext

import pytest

SCALE = "8315.251344"


@pytest.mark.loop_fast
@pytest.mark.parametrize(
    "value,zero",
    [
        (("0", "0"), True),
        (("0.0", "0E-5"), True),
        (("2.441404", "0"), False),
        (("0", "1e-3"), False),
        ("0", True),
        ("1.5", False),
        (None, False),
    ],
)
def test_is_zero_reads_fixed_parameter_pairs(value, zero):
    from pyamplicol.loops.v2.ew_policy import is_zero

    fixed = {} if value is None else {"WZ": value}
    assert is_zero("WZ", {}, fixed) is zero


def _exact_point(masses):
    from tools.loop_reference import exact_points

    point = exact_points.generate(list(masses), count=1)[0]
    return [[exact_points.decimal_string(x) for x in leg] for leg in point]


def _two_to_two(sqrt_s, masses, cosine):
    """A massless-beam 2 -> 2 point with unequal final masses (50 digits)."""

    getcontext().prec = 50
    rs, m3, m4, c = (Decimal(x) for x in (sqrt_s, *masses, cosine))
    e3 = (rs * rs + m3 * m3 - m4 * m4) / (2 * rs)
    q = (e3 * e3 - m3 * m3).sqrt()
    s = (1 - c * c).sqrt()
    half = rs / 2
    legs = [
        (half, 0, 0, half),
        (half, 0, 0, -half),
        (e3, q * s, 0, q * c),
        (rs - e3, -q * s, 0, -q * c),
    ]
    return [[str(Decimal(x)) for x in leg] for leg in legs]


def _values(result):
    values = [Decimal(str(v)) for v in result.born.values()]
    for sectors in result.components.values():
        for laurent in sectors.values():
            values += [Decimal(str(c)) for c in laurent.coefficients]
    return values


QCD = ({"QCD": 2, "QED": 0}, {"QCD": 4, "QED": 0})
DRELL_YAN = ({"QCD": 0, "QED": 2}, {"QCD": 2, "QED": 2})
MASSLESS = [0, 0, 0, 0]
# id -> (process, Born and loop orders, the fixed parameters, the point).
SWEEP = {
    "top-mass": ("u u~ > t t~", QCD, {"MT": "173.3", "ymt": "173.3"}, ("173.3",) * 2),
    "z-mass": ("u u~ > e+ e-", DRELL_YAN, {"MZ": "91.3"}, None),
    "z-width": ("u u~ > e+ e-", DRELL_YAN, {"WZ": "2.4"}, None),
    "alpha-input": ("u u~ > e+ e-", DRELL_YAN, {"aEWM1": "132.4"}, None),
    "fermi-input": ("u u~ > e+ e-", DRELL_YAN, {"Gf": "0.0000117"}, None),
    "w-width": ("u d~ > e+ ve", DRELL_YAN, {"WW": "2.1"}, None),
    "w-via-z-mass": ("u d~ > e+ ve", DRELL_YAN, {"MZ": "91.3"}, None),
    "strong-input": ("u u~ > d d~", QCD, {"aS": "0.12"}, None),
    "bottom-mass": ("g g > b b~", QCD, {"MB": "4.75", "ymb": "4.75"}, "bb"),
    "bottom-massless": ("g g > b b~", QCD, {"MB": "0", "ymb": "0"}, None),
    "higgs-mass": ("u u~ > z h", DRELL_YAN, {"MH": "125"}, "zh"),
}
# The default tier runs the fixed MZ, the top mass and a W; the
# others are nightly.
DEFAULT = {"top-mass", "z-mass", "w-width"}


def _point(spec):
    if spec == "bb":
        return _two_to_two("500", ("4.75", "4.75"), "0.3")
    if spec == "zh":
        # MZ at loop_sm's default (MH fixed at its default: the point stays
        # on its shell).
        return _two_to_two("500", ("91.188", "125"), "0.3")
    return _exact_point([0, 0, *spec] if spec else MASSLESS)


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            name,
            marks=pytest.mark.loop_physics
            if name in DEFAULT
            else pytest.mark.loop_nightly,
        )
        for name in SWEEP
    ],
)
@pytest.mark.parametrize("accuracy", ("lc", "nlc", "full"))
def test_a_fixed_parameter_equals_the_same_value_at_run_time(
    loop_sm_compiled_model, loop_native, tmp_path, case, accuracy
):
    """Each fixed parameter of the sweep (module docstring) at LC, NLC and
    full colour: the request generates, and its Born and every Laurent
    coefficient of every component equal those of the same request with the
    parameter set at evaluation (a massless b: loop_sm's no_b_mass
    restriction), to 1e-30 at 40 digits (on main: LC and NLC
    raised for a decimal mass or a fixed MZ, full colour was ~1e-18 off for a
    non-dyadic decimal)."""

    from pyamplicol.loops.v2.assemble import LoopSlice, Precision, SliceRequest
    from pyamplicol.models.loading import compile_model_source, load_compiled_model

    process, (born, loop), fixed, point_spec = SWEEP[case]
    compiled = load_compiled_model(loop_sm_compiled_model)

    def generate(parameters):
        request = SliceRequest(
            process, born, loop, accuracy=accuracy, fixed_parameters=parameters
        )
        return LoopSlice.generate(compiled, request, loop_native)

    point = _point(point_spec)
    precision = Precision.arbitrary(40)
    if case == "bottom-massless":
        # A run-time MB = 0 is refused where the counterterms were lowered
        # for a massive b (``CountertermModel.check_parameters``): the
        # reference is loop_sm's own massless-b restriction.
        reference = compile_model_source(
            "loop_sm", restriction="no_b_mass", cache_dir=tmp_path / "model-cache"
        )
        free = LoopSlice.generate(
            reference,
            SliceRequest(process, born, loop, accuracy=accuracy),
            loop_native,
        ).evaluate(point, SCALE, parameters={"aS": "0.118"}, precision=precision)
    else:
        free = generate({}).evaluate(
            point, SCALE, parameters={"aS": "0.118", **fixed}, precision=precision
        )
    # A fixed parameter is not a run-time input of the pinned request.
    inputs = {} if "aS" in fixed else {"aS": "0.118"}
    pinned = generate(dict(fixed)).evaluate(
        point, SCALE, parameters=inputs, precision=precision
    )
    mine, theirs = _values(pinned), _values(free)
    assert len(mine) == len(theirs)
    scale = max(abs(v) for v in theirs)
    for a, b in zip(mine, theirs, strict=True):
        assert abs(a - b) <= Decimal("1e-30") * max(abs(b), scale * Decimal("1e-10"))


@pytest.mark.loop_physics
@pytest.mark.parametrize("accuracy", ("lc", "nlc"))
def test_the_public_card_with_only_mz_fixed_generates_at_lc(tmp_path, accuracy):
    """The public run card on shipped loop_sm with only MZ fixed
    (``[loop.preparation] fixed_parameters = { MZ = "91.3" }``), u u~ > e+ e-
    with QCD corrections at LC and NLC: the artifact is generated (on main
    ``ew_policy.is_zero`` raised ``decimal.InvalidOperation`` on the
    ``(real, zero)`` pair while classifying the Z), and its virtual equals
    that of the artifact without the fixed MZ evaluated at MZ = 91.3."""

    from pyamplicol.api import Generator, Runtime
    from pyamplicol.config import resolve_config

    def artifact(name, fixed):
        card = tmp_path / f"{name}.toml"
        card.write_text(
            f"""
action = "generate"
[model]
source = "loop_sm"
[process]
entries = [{{ expression = "u u~ > e+ e-", name = "dy" }}]
loop_coupling_orders = ["QCD"]
[color]
accuracy = "{accuracy}"
[loop.preparation]
fixed_parameters = {{ {fixed} }}
[generation]
output = "{tmp_path / name}"
"""
        )
        Generator(resolve_config(card)).generate("u u~ > e+ e-", tmp_path / name)
        return tmp_path / name

    point = _exact_point(MASSLESS)
    pinned = Runtime.load(
        artifact("pinned", 'MZ = "91.3"'), arithmetic="arbitrary", precision=40
    ).evaluate([point], mu_r2=SCALE)
    free = Runtime.load(
        artifact("free", ""),
        arithmetic="arbitrary",
        precision=40,
        model_parameters={"MZ": "91.3"},
    ).evaluate([point], mu_r2=SCALE)
    for name in ("finite", "single_pole", "double_pole"):
        mine = [Decimal(str(x)) for x in getattr(pinned, name)[0]]
        theirs = [Decimal(str(x)) for x in getattr(free, name)[0]]
        assert len(mine) == len(theirs)
        for a, b in zip(mine, theirs, strict=True):
            assert abs(a - b) <= Decimal("1e-30") * max(abs(b), Decimal("1e-40")), name
