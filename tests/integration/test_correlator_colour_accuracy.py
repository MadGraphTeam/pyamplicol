# SPDX-License-Identifier: 0BSD
"""Inherited LC/NLC Born results from independently generated ordinary artifacts."""

import math
from decimal import Decimal, localcontext

import pytest

from pyamplicol import (
    ColorCorrelator,
    CorrelatorConfig,
    Generator,
    ModelSource,
    Runtime,
)
from pyamplicol.config import (
    ColorConfig,
    EvaluatorConfig,
    EvaluatorOptimizationConfig,
    GenerationConfig,
    GenerationValidationConfig,
    JITConfig,
    RunConfig,
)

_POINT = (
    (500, 0, 0, 500),
    (500, 0, 0, -500),
    (500, 300, 0, 400),
    (500, -300, 0, -400),
)
_THREE_BODY_POINT = (
    (900, 0, 0, 900),
    (900, 0, 0, -900),
    (500, 400, 300, 0),
    (500, 400, -300, 0),
    (800, -800, 0, 0),
)


def _configuration(accuracy):
    return RunConfig(
        action="generate",
        color=ColorConfig(accuracy=accuracy, contraction="direct"),
        generation=GenerationConfig(
            workers=1,
            emit_api_bundle=False,
            validation=GenerationValidationConfig(
                enabled=False, post_build_validation=False
            ),
        ),
        evaluator=EvaluatorConfig(
            execution_mode="compiled",
            optimization=EvaluatorOptimizationConfig(cores=1, horner_iterations=1),
            jit=JITConfig(optimization_level=0),
        ),
    )


@pytest.mark.parametrize("accuracy", ("lc", "nlc"))
@pytest.mark.parametrize(
    ("expression", "point"),
    (
        ("g g > g g", _POINT),
        ("d d~ > g g", _POINT),
        ("d d~ > u u~", _POINT),
        ("d d~ > d d~", _POINT),
        ("d d~ > u u~ g", _THREE_BODY_POINT),
        ("d d~ > d d~ g", _THREE_BODY_POINT),
    ),
    ids=(
        "gluons",
        "one-quark-pair",
        "two-quark-pairs",
        "identical-quarks",
        "two-pairs-and-gluon",
        "identical-pairs-and-gluon",
    ),
)
def test_generated_correlated_born_matches_inherited_accuracy(
    tmp_path, expression, point, accuracy
):
    pytest.importorskip("pyamplicol._rusticol")
    config = _configuration(accuracy)
    model = ModelSource.built_in_sm()
    ordinary_path = tmp_path / "ordinary"
    correlated_path = tmp_path / "correlated"
    Generator(config).generate(expression, ordinary_path, model=model)
    Generator(config).generate(
        expression,
        correlated_path,
        model=model,
        correlators=CorrelatorConfig(
            color_correlations=(ColorCorrelator.dipole("T11", 1, 1),)
        ),
    )
    ordinary = Runtime.load(ordinary_path).evaluate((point,), precision=36)[0]
    correlated = Runtime.load(correlated_path).evaluate_correlated(
        (point,), precision=32
    )[0]
    with localcontext() as context:
        context.prec = 40
        assert ordinary > 0
        assert abs(correlated.real / ordinary - 1) < Decimal("1e-27")
        assert abs(correlated.imag / ordinary) < Decimal("1e-27")


_ACCURACY_PROCESSES = (
    ("g g > g g", _POINT),
    ("d d~ > u u~ g", _THREE_BODY_POINT),
    ("u u~ > g g g", _THREE_BODY_POINT),
)


@pytest.mark.parametrize("accuracy", ("lc", "nlc"))
@pytest.mark.parametrize(
    ("expression", "point"),
    _ACCURACY_PROCESSES,
    ids=("gluons", "two-pairs-and-gluon", "pair-and-three-gluons"),
)
def test_a_correlated_artifact_has_one_colour_accuracy(
    tmp_path, expression, point, accuracy
):
    """Every evaluation of a correlated artifact generated at LC or NLC is at
    that accuracy: the ordinary value (plain, extended precision, resolved,
    per helicity and, at LC, per colour flow) equals an independently
    generated ordinary artifact of that accuracy, compiled and recurrence,
    and equals its own correlated Born."""

    pytest.importorskip("pyamplicol._rusticol")
    config = _configuration(accuracy)
    model = ModelSource.built_in_sm()
    correlated_path = tmp_path / "correlated"
    Generator(config).generate(
        expression,
        correlated_path,
        model=model,
        correlators=CorrelatorConfig(
            color_correlations=(ColorCorrelator.dipole("T12", 1, 2),)
        ),
    )
    ordinary_path = tmp_path / "ordinary"
    Generator(config).generate(expression, ordinary_path, model=model)
    recurrence_path = tmp_path / "recurrence"
    Generator(
        RunConfig(
            action="generate",
            color=ColorConfig(accuracy=accuracy),
            generation=config.generation,
            evaluator=EvaluatorConfig(execution_mode="recurrence"),
        )
    ).generate(expression, recurrence_path, model=model)
    correlated = Runtime.load(correlated_path)
    ordinary = Runtime.load(ordinary_path)
    recurrence = Runtime.load(recurrence_path)
    assert str(correlated.physics.color_accuracy) == accuracy
    expected = complex(ordinary.evaluate((point,))[0]).real
    assert expected > 0
    for value in (
        complex(correlated.evaluate((point,))[0]).real,
        float(complex(correlated.evaluate((point,), precision=32)[0]).real),
        float(
            sum(
                complex(item).real
                for row in correlated.evaluate_resolved((point,)).values[0]
                for item in row
            )
        ),
        float(correlated.evaluate_correlated((point,))[0].real),
        complex(recurrence.evaluate((point,))[0]).real,
    ):
        assert value == pytest.approx(expected, rel=1e-12)
    for helicity in ordinary.physics.helicities:
        assert complex(
            correlated.evaluate((point,), helicities=[helicity.id])[0]
        ).real == pytest.approx(
            complex(ordinary.evaluate((point,), helicities=[helicity.id])[0]).real,
            rel=1e-12,
            abs=1e-15 * expected,
        )
    if accuracy == "lc":
        flows = {flow.id for flow in correlated.physics.color_flows}
        assert flows == {flow.id for flow in ordinary.physics.color_flows}
        for flow in sorted(flows):
            assert complex(
                correlated.evaluate((point,), color_flows=[flow])[0]
            ).real == pytest.approx(
                complex(ordinary.evaluate((point,), color_flows=[flow])[0]).real,
                rel=1e-12,
                abs=1e-15 * expected,
            )


@pytest.mark.parametrize(
    ("expression", "orders", "point"),
    (
        ("c d > u s", {"QCD": 0, "QED": 2}, _POINT),
        (
            "u u~ > d d~ s s~",
            {"QCD": 0, "QED": 4},
            (
                (900, 0, 0, 900),
                (900, 0, 0, -900),
                (450, 450, 0, 0),
                (450, -450, 0, 0),
                (450, 0, 450, 0),
                (450, 0, -450, 0),
            ),
        ),
        ("d d~ > u u~ g", None, _THREE_BODY_POINT),
        ("g g > g g", None, _POINT),
    ),
    ids=("w-exchange", "three-pairs-electroweak", "two-pairs-and-gluon", "gluons"),
)
def test_a_correlated_lc_artifact_exposes_the_ordinary_colour_flows(
    tmp_path, expression, orders, point
):
    """At LC a correlated artifact exposes exactly the ordinary LC artifact's
    colour flows, structural zeros included (only block-permutation aliases
    are one flow): every flow is selectable in evaluate and evaluate_orders,
    a flow without trees returns exactly zero, and the values are the
    ordinary artifact's."""

    pytest.importorskip("pyamplicol._rusticol")
    from dataclasses import replace

    from pyamplicol.config import ProcessConfig

    config = _configuration("lc")
    if orders is not None:
        config = replace(
            config,
            process=ProcessConfig(
                coupling_order_policy="explicit", max_coupling_orders=orders
            ),
        )
    model = ModelSource.built_in_sm()
    correlated_path = tmp_path / "correlated"
    Generator(config).generate(
        expression,
        correlated_path,
        model=model,
        correlators=CorrelatorConfig(
            color_correlations=(ColorCorrelator.dipole("T12", 1, 2),)
        ),
    )
    ordinary_path = tmp_path / "ordinary"
    Generator(config).generate(expression, ordinary_path, model=model)
    correlated = Runtime.load(correlated_path)
    ordinary = Runtime.load(ordinary_path)
    recurrence_path = tmp_path / "recurrence"
    Generator(
        replace(config, evaluator=EvaluatorConfig(execution_mode="recurrence"))
    ).generate(expression, recurrence_path, model=model)
    recurrence = Runtime.load(recurrence_path)
    flows = [flow.id for flow in ordinary.physics.color_flows]
    assert sorted(flow.id for flow in correlated.physics.color_flows) == sorted(flows)
    assert sorted(flow.id for flow in recurrence.physics.color_flows) == sorted(flows)
    total = complex(ordinary.evaluate((point,))[0]).real
    assert complex(correlated.evaluate((point,))[0]).real == pytest.approx(
        total, rel=1e-12
    )

    def resolved(runtime):
        evaluation = runtime.evaluate_resolved((point,))
        ids = [flow.id for flow in runtime.physics.color_flows]
        return {
            flow: math.fsum(complex(row[index]).real for row in evaluation.values[0])
            for index, flow in enumerate(ids)
        }

    resolved_correlated, resolved_ordinary = resolved(correlated), resolved(ordinary)
    for flow in flows:
        if resolved_ordinary[flow] == 0.0:
            assert resolved_correlated[flow] == 0.0, flow
        else:
            assert resolved_correlated[flow] == pytest.approx(
                resolved_ordinary[flow], rel=1e-12
            ), flow
        expected = complex(ordinary.evaluate((point,), color_flows=[flow])[0]).real
        actual = complex(correlated.evaluate((point,), color_flows=[flow])[0]).real
        if expected == 0.0:
            assert actual == 0.0, flow
        else:
            assert actual == pytest.approx(expected, rel=1e-12), flow
        split = correlated.evaluate_orders((point,), color_flows=[flow])
        reference = ordinary.evaluate_orders((point,), color_flows=[flow])
        assert set(split.orders) == set(reference.orders)
        for order in reference.orders:
            want = complex(reference.for_order(order)[0]).real
            got = complex(split.for_order(order)[0]).real
            if want == 0.0:
                assert got == 0.0, (flow, order)
            else:
                assert got == pytest.approx(want, rel=1e-12), (flow, order)
