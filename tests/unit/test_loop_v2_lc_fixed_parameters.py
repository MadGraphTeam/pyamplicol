# SPDX-License-Identifier: 0BSD
"""Leading colour with fixed decimal parameters.

The counterterm couplings of a leading- or next-to-leading-colour request are
graded by N_c in exact arithmetic (``ct_recursion.lower_model_counterterms``).
A fixed parameter's decimal value (``fixed_parameters``, e.g. ``MT = 173.3``)
must reach that grading as an exact number, as the scalar bindings lower it;
written as a binary64 float it made the grading fail (``N_c grading of the
coupling failed: exact expressions reject floating numeric atoms``) and the
request was refused with ``unlowered-counterterm``. In full colour the same
float capped the counterterm coefficients at binary64 precision.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

MASSES = {"MT": "173.3", "ymt": "173.3"}
SCALE = "8315.251344"


def _point():
    from tools.loop_reference import exact_points

    point = exact_points.generate([0, 0, MASSES["MT"], MASSES["MT"]], count=1)[0]
    return [[exact_points.decimal_string(x) for x in leg] for leg in point]


def _values(result):
    values = [Decimal(str(v)) for v in result.born.values()]
    for sectors in result.components.values():
        for laurent in sectors.values():
            values += [Decimal(str(c)) for c in laurent.coefficients]
    return values


@pytest.mark.loop_physics
@pytest.mark.parametrize("accuracy", ("lc", "nlc", "full"))
def test_fixed_decimal_masses_grade_exactly_and_equal_run_time_values(
    loop_sm_compiled_model, loop_native, accuracy
):
    """u u~ > t t~ with QCD corrections on loop_sm: with MT and ymt fixed to
    173.3 the LC (NLC) request generates, and its Born and every Laurent
    coefficient of every component equal those of the same request with MT
    and ymt set at evaluation, to 1e-30 at 40 digits. Full colour generated
    before, but its counterterms carried the fixed decimal as a binary64
    float (3.8e-18 off the run-time values at 40 digits)."""

    from pyamplicol.loops.v2.assemble import LoopSlice, Precision, SliceRequest
    from pyamplicol.models.loading import load_compiled_model

    compiled = load_compiled_model(loop_sm_compiled_model)

    def generate(fixed):
        request = SliceRequest(
            "u u~ > t t~",
            {"QCD": 2, "QED": 0},
            {"QCD": 4, "QED": 0},
            accuracy=accuracy,
            fixed_parameters=fixed,
        )
        return LoopSlice.generate(compiled, request, loop_native)

    point = _point()
    precision = Precision.arbitrary(40)
    fixed = generate(dict(MASSES)).evaluate(
        point, SCALE, parameters={"aS": "0.118"}, precision=precision
    )
    free = generate({}).evaluate(
        point, SCALE, parameters={"aS": "0.118", **MASSES}, precision=precision
    )
    mine, theirs = _values(fixed), _values(free)
    assert len(mine) == len(theirs)
    scale = max(abs(v) for v in theirs)
    for a, b in zip(mine, theirs, strict=True):
        assert abs(a - b) <= Decimal("1e-30") * max(abs(b), scale * Decimal("1e-10"))
