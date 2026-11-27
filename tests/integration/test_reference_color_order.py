# SPDX-License-Identifier: 0BSD
"""``process.reference_color_order`` relabels the colour plan, nothing more.

The sector whose colour tensor the order spells comes first; a cyclic
rotation of a trace, or its reflection where reflections are folded, names
that same sector, never another. For every reference order the published
flows, the value of each flow, every squared-order partial and the inclusive
value equal those of the default order, in the recurrence, compiled and
on-the-fly modes at LC, NLC and full colour, and every advertised flow is
selectable. With a cap the reference sector is kept (it is the plan's first)
and the kept flows are distinct and equal the same flows of the complete
artifact.
"""

from __future__ import annotations

import importlib.util
import math
from itertools import permutations

import pytest

from pyamplicol import Generator, ModelSource, Runtime
from pyamplicol.config import (
    ColorConfig,
    EvaluatorConfig,
    EvaluatorOptimizationConfig,
    GenerationConfig,
    GenerationRelationDiscoveryConfig,
    GenerationValidationConfig,
    ModelConfig,
    ProcessConfig,
    RunConfig,
)
from pyamplicol.generation.phase_space import massive_rambo_final_state

_NIGHTLY = pytest.mark.loop_nightly
_MASSES = {6: 173.0}
_MODES = ("recurrence", "compiled", "on-the-fly")


def _model(name: str) -> ModelSource:
    return ModelSource.built_in_sm() if name == "sm" else ModelSource.built_in_sm_heft()


def _config(mode: str, accuracy: str, orders, **selection) -> RunConfig:
    process = (
        ProcessConfig(**selection)
        if orders is None
        else ProcessConfig(
            coupling_order_policy="explicit", max_coupling_orders=orders, **selection
        )
    )
    return RunConfig(
        action="generate",
        model=ModelConfig(cache=False),
        color=ColorConfig(accuracy=accuracy),
        process=process,
        generation=GenerationConfig(
            workers=1,
            emit_api_bundle=False,
            relation_discovery=GenerationRelationDiscoveryConfig(mode="off"),
            validation=GenerationValidationConfig(
                enabled=False, post_build_validation=False
            ),
        ),
        evaluator=EvaluatorConfig(
            execution_mode=mode,
            optimization=EvaluatorOptimizationConfig(cores=1),
        ),
    )


def _points(runtime: Runtime):
    masses = [
        _MASSES.get(abs(particle.pdg_id), 0.0)
        for particle in runtime.physics.external_particles
    ]
    sqrt_s, (m1, m2) = 1000.0, masses[:2]
    s = sqrt_s * sqrt_s
    p = math.sqrt((s - (m1 + m2) ** 2) * (s - (m1 - m2) ** 2)) / (2 * sqrt_s)
    return [
        [
            [math.hypot(p, m1), 0.0, 0.0, p],
            [math.hypot(p, m2), 0.0, 0.0, -p],
            *[
                [float(v) for v in momentum]
                for momentum in massive_rambo_final_state(
                    len(masses) - 2, sqrt_s=sqrt_s, masses=masses[2:], seed=seed
                )
            ],
        ]
        for seed in (7, 8)
    ]


def _real(values) -> list[float]:
    return [complex(value).real for value in values]


def _record(runtime: Runtime, points):
    """Inclusive values, squared-order partials and, at LC, every flow."""

    total = _real(runtime.evaluate(points))
    split = runtime.evaluate_orders(points)
    partials = {label: _real(split.for_order(label)) for label in split.orders}
    flows = {}
    if runtime.physics.color_accuracy == "lc":
        for flow in runtime.physics.color_flows:
            flows[flow.id] = _real(runtime.evaluate(points, color_flows=[flow.id]))
    return total, partials, flows


def _assert_close(left, right, context) -> None:
    for a, b in zip(left, right, strict=True):
        assert a == pytest.approx(b, rel=1e-12, abs=1e-300), context


@pytest.fixture(scope="module")
def generate(tmp_path_factory: pytest.TempPathFactory):
    if importlib.util.find_spec("pyamplicol._rusticol") is None:
        pytest.skip("the Rusticol extension has not been built")
    root = tmp_path_factory.mktemp("reference-order")
    count = [0]

    def artifact(model: str, process: str, mode: str, accuracy: str, orders, **sel):
        count[0] += 1
        path = root / f"a{count[0]}"
        Generator(_config(mode, accuracy, orders, **sel)).generate(
            process, path, model=_model(model)
        )
        return Runtime.load(path)

    return artifact


# (model, process, orders, references): ordinary QCD processes, pure gluons
# with folded reflections and an open line beside gluons.
_ALL_FOUR = tuple(permutations((1, 2, 3, 4)))
_CASES = (
    pytest.param(
        "sm", "g g > g g", None, ((1, 3, 4, 2), (2, 3, 4, 1), (1, 2, 4, 3)), id="qcd"
    ),
    pytest.param(
        "sm",
        "g g > t t~ g",
        None,
        ((3, 2, 1, 5, 4), (3, 1, 5, 2, 4)),
        id="line",
    ),
    pytest.param("sm", "g g > g g", None, _ALL_FOUR, id="qcd-all", marks=_NIGHTLY),
    pytest.param(
        "sm",
        "g g > g g g",
        None,
        ((2, 3, 4, 5, 1), (1, 3, 5, 2, 4), (1, 5, 4, 3, 2)),
        id="qcd-five",
        marks=_NIGHTLY,
    ),
    pytest.param(
        "sm",
        "g g > t t~ g",
        None,
        ((3, 5, 2, 1, 4), (3, 1, 2, 5, 4)),
        id="line-five",
        marks=_NIGHTLY,
    ),
)


@pytest.mark.parametrize("accuracy", ["lc", "nlc", "full"])
@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize(("model", "process", "orders", "references"), _CASES)
def test_a_reference_order_changes_no_flow_and_no_value(
    generate, model: str, process: str, orders, references, mode: str, accuracy: str
) -> None:
    default = generate(model, process, mode, accuracy, orders)
    points = _points(default)
    total, partials, flows = _record(default, points)
    for reference in references:
        reordered = generate(
            model,
            process,
            mode,
            accuracy,
            orders,
            reference_color_order=list(reference),
        )
        r_total, r_partials, r_flows = _record(reordered, points)
        _assert_close(r_total, total, ("total", reference))
        assert set(r_partials) == set(partials), reference
        for label, values in r_partials.items():
            _assert_close(values, partials[label], (label, reference))
        assert len(reordered.physics.color_flows) == len(default.physics.color_flows)
        assert set(r_flows) == set(flows), reference
        for flow, values in r_flows.items():
            _assert_close(values, flows[flow], (flow, reference))


def _reference_flow(flows: list[str], reference: tuple[int, ...]) -> str:
    """The published flow the reference names: the same open lines, or the
    same trace up to rotation (and reflection where reflections are folded)."""

    rotations = {reference[i:] + reference[:i] for i in range(len(reference))}
    reflected = tuple(reversed(reference))
    rotations |= {reflected[i:] + reflected[:i] for i in range(len(reflected))}
    matches = [
        flow
        for flow in flows
        if "|" not in flow
        and tuple(int(x) for x in flow.removeprefix("flow:").split(",")) in rotations
    ]
    exact = [
        flow
        for flow in matches
        if tuple(int(x) for x in flow.removeprefix("flow:").split(","))
        in {reference[i:] + reference[:i] for i in range(len(reference))}
    ]
    return (exact or matches)[0]


@pytest.mark.parametrize(
    ("model", "process", "orders", "reference"),
    [
        pytest.param("sm", "g g > g g", None, (2, 3, 4, 1), id="qcd-cyclic"),
        pytest.param("sm", "g g > g g", None, (1, 3, 4, 2), id="qcd"),
        pytest.param("sm", "g g > t t~ g", None, (3, 2, 1, 5, 4), id="line"),
    ],
)
def test_a_capped_reference_keeps_the_reference_first(
    generate, model: str, process: str, orders, reference
) -> None:
    complete = generate(model, process, "compiled", "lc", orders)
    points = _points(complete)
    ids = [flow.id for flow in complete.physics.color_flows]
    first = _reference_flow(ids, reference)
    for cap in range(1, len(ids) + 1):
        capped = generate(
            model,
            process,
            "compiled",
            "lc",
            orders,
            reference_color_order=list(reference),
            max_color_sectors=cap,
        )
        kept = [flow.id for flow in capped.physics.color_flows]
        assert len(kept) == cap == len(set(kept)), (cap, kept)
        # Public physics lists flows in its own order: the cap keeps the
        # reference sector (alone at cap one).
        assert first in kept, (cap, kept)
        if cap == 1:
            assert kept == [first]
        total = [0.0] * len(points)
        for flow in kept:
            expected = _real(complete.evaluate(points, color_flows=[flow]))
            _assert_close(
                _real(capped.evaluate(points, color_flows=[flow])),
                expected,
                (cap, flow),
            )
            total = [a + b for a, b in zip(total, expected, strict=True)]
        _assert_close(_real(capped.evaluate(points)), total, cap)
