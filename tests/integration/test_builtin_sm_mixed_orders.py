# SPDX-License-Identifier: 0BSD
"""Built-in SM Born amplitudes of several coupling orders.

The built-in stage evaluators carry the local vertex couplings and one global
factor restores g_s and e. A Born with amplitudes of several (QCD, QED) orders
takes the global factor (4 pi alpha_s)^N, N the common total order, and
weighs every QED order of an amplitude by rho = sqrt(8 pi alpha / (4 pi
alpha_s)) at the current run-time inputs (``generation.born_orders``): the
electroweak coupling slots carry rho in the compiled and eager modes, the
closures of QED order e carry rho^e in the recurrence and on-the-fly modes.

The values are compared with MadGraph5_aMC 3.7.0 standalone split orders
(model ``sm``, restrict_default, ``zerowidth_tchannel False``;
``fixtures/tree/madgraph-split-orders*.json``, the four processes the shared
fixtures lack in ``madgraph-split-orders-builtin-mixed*.json``, written by
``tools/developer/madgraph_split_orders.py``) and with the UFO ``sm`` at the
same parameters, in every execution mode at leading and full colour.
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

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

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/tree"
_REFERENCES = {
    "full": (
        _FIXTURES / "madgraph-split-orders.json",
        _FIXTURES / "madgraph-split-orders-builtin-mixed.json",
    ),
    "lc": (
        _FIXTURES / "madgraph-split-orders-lc.json",
        _FIXTURES / "madgraph-split-orders-builtin-mixed-lc.json",
    ),
}
# The process and its explicit coupling-order limits (all its Born orders).
# MadGraph's leading colour exists only without external gluons.
_PROCESSES = (
    ("u u~ > d d~", {"QCD": 2, "QED": 2}),
    ("u u~ > u u~", {"QCD": 2, "QED": 2}),
    ("u d > u d", {"QCD": 2, "QED": 2}),
    ("u d~ > u d~", {"QCD": 2, "QED": 2}),
    ("u u~ > d d~ g", {"QCD": 3, "QED": 2}),
    ("g u > u d d~", {"QCD": 3, "QED": 2}),
    ("u u~ > t t~", {"QCD": 2, "QED": 2}),
    ("u t > u t", {"QCD": 2, "QED": 2}),
)
_MODES = ("recurrence", "compiled", "eager", "on-the-fly")
_ACCURACIES = ("lc", "full")
_ALPHA_S = 0.118
_ALPHA_EW = 1.0 / 132.507


def _reference(process: str, accuracy: str) -> dict[str, object] | None:
    for path in _REFERENCES[accuracy]:
        for entry in json.loads(path.read_text(encoding="utf-8"))["processes"]:
            if entry["process"] == process:
                return entry
    return None


def _points(process: str) -> list[list[list[float]]]:
    reference = _reference(process, "full")
    assert reference is not None, process
    return reference["points"]  # type: ignore[return-value]


def _config(mode: str, accuracy: str, orders: dict[str, int]) -> RunConfig:
    return RunConfig(
        action="generate",
        model=ModelConfig(cache=False),
        color=ColorConfig(accuracy=accuracy),
        process=ProcessConfig(
            coupling_order_policy="explicit", max_coupling_orders=orders
        ),
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


def _require_native() -> None:
    if importlib.util.find_spec("pyamplicol._rusticol") is None:
        pytest.skip("the Rusticol extension has not been built")


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory: pytest.TempPathFactory):
    """One built-in artifact per (mode, accuracy, process), generated lazily."""

    _require_native()
    root = tmp_path_factory.mktemp("builtin-mixed-orders")
    cache: dict[tuple[str, str, str], Path] = {}

    def artifact(mode: str, accuracy: str, process: str) -> Path:
        key = (mode, accuracy, process)
        if key not in cache:
            orders = next(item[1] for item in _PROCESSES if item[0] == process)
            path = root / f"{mode}-{accuracy}-{len(cache)}"
            Generator(_config(mode, accuracy, orders)).generate(
                process, path, model=ModelSource.built_in_sm()
            )
            cache[key] = path
        return cache[key]

    return artifact


@pytest.fixture(scope="module")
def ufo_artifacts(madgraph_source: Path, tmp_path_factory: pytest.TempPathFactory):
    """The same requests on the UFO ``sm`` (restrict_default)."""

    _require_native()
    root = tmp_path_factory.mktemp("builtin-mixed-orders-ufo")
    bundle = root / "sm.pyamplicol-model"
    ModelSource.from_path(madgraph_source / "models/sm", restriction="default").compile(
        cache_dir=root / "cache", prepared_output=bundle, evaluator=EvaluatorConfig()
    )
    model = ModelSource.from_path(bundle)
    cache: dict[tuple[str, str, str], Path] = {}

    def artifact(mode: str, accuracy: str, process: str) -> Path:
        key = (mode, accuracy, process)
        if key not in cache:
            orders = next(item[1] for item in _PROCESSES if item[0] == process)
            path = root / f"{mode}-{accuracy}-{len(cache)}"
            Generator(_config(mode, accuracy, orders)).generate(
                process, path, model=model
            )
            cache[key] = path
        return cache[key]

    return artifact


def _scale(partials: list[float]) -> float:
    return math.fsum(abs(value) for value in partials)


def _real(values) -> list[float]:
    result = []
    for value in values:
        value = complex(value)
        assert value.imag == 0.0
        result.append(value.real)
    return result


# The default tier runs the 2 -> 2 and the 2 -> 3 process of the report in every
# mode and accuracy; the nightly tier the other six.
_DEFAULT_TIER = ("u u~ > d d~", "u u~ > d d~ g")
_CELLS = [
    pytest.param(
        process,
        mode,
        accuracy,
        id=f"{process}-{mode}-{accuracy}",
        marks=() if process in _DEFAULT_TIER else pytest.mark.loop_nightly,
    )
    for process, _orders in _PROCESSES
    for mode in _MODES
    for accuracy in _ACCURACIES
]


@pytest.mark.parametrize(("process", "mode", "accuracy"), _CELLS)
def test_mixed_orders_match_madgraph_and_the_ufo_sm(
    artifacts, ufo_artifacts, process: str, mode: str, accuracy: str
) -> None:
    """The total, with the interference between the orders, equals MadGraph's
    sum of split orders (where MadGraph's colour basis gives the accuracy) and
    the UFO ``sm`` value of the same mode and accuracy; the recurrence mode's
    squared-order partials equal MadGraph's, and the UFO ``sm``'s."""

    points = _points(process)
    runtime = Runtime.load(artifacts(mode, accuracy, process))
    totals = _real(runtime.evaluate(points))
    ufo = Runtime.load(ufo_artifacts(mode, accuracy, process))
    for value, expected in zip(totals, _real(ufo.evaluate(points)), strict=True):
        assert value == pytest.approx(expected, rel=1e-12, abs=0.0)
    reference = _reference(process, accuracy)
    if reference is not None:
        for point, (total, partials) in enumerate(
            zip(totals, reference["partials"], strict=True)
        ):
            assert abs(total - math.fsum(partials)) <= 1e-12 * _scale(partials), point
    if mode != "recurrence":
        return
    split = runtime.evaluate_orders(points)
    ufo_split = ufo.evaluate_orders(points)
    assert split.orders == ufo_split.orders
    assert _real(split.total) == totals
    for order in split.orders:
        for value, expected in zip(
            _real(split.for_order(order)),
            _real(ufo_split.for_order(order)),
            strict=True,
        ):
            assert abs(value - expected) <= 1e-12 * max(
                abs(expected), *(abs(x) for x in totals)
            ), order
    if reference is None:
        return
    expected_orders = tuple(
        tuple(sorted((name, power) for name, power in order.items() if power))
        for order in reference["squared_orders"]
    )
    assert split.orders == tuple(sorted(expected_orders))
    for point, partials in enumerate(reference["partials"]):
        for order, expected in zip(expected_orders, partials, strict=True):
            actual = _real(split.for_order(order))[point]
            assert abs(actual - expected) <= 1e-12 * _scale(partials), (point, order)


def _scaled_partials(split, alpha_s: float, alpha_ew: float) -> list[float]:
    """The squared-order partials at (alpha_s, alpha_ew): each partial
    (QCD^q QED^e) scales as (alpha_s / 0.118)^(q/2) (alpha_ew / alpha)^(e/2)."""

    totals = [0.0] * len(split.total)
    for order in split.orders:
        powers = dict(order)
        weight = (alpha_s / _ALPHA_S) ** (powers.get("QCD", 0) / 2) * (
            alpha_ew / _ALPHA_EW
        ) ** (powers.get("QED", 0) / 2)
        for point, value in enumerate(_real(split.for_order(order))):
            totals[point] += weight * value
    return totals


@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize("accuracy", _ACCURACIES)
def test_rebinding_alpha_rescales_every_order_by_its_own_powers(
    artifacts, mode: str, accuracy: str
) -> None:
    """After a run-time change of alpha_s and alpha_ew the value equals the
    sum of the default partials, each scaled by its own coupling powers, in
    every mode; changing back restores the default values bitwise, and the
    recurrence partials scale order by order."""

    process = "u u~ > d d~ g"
    points = _points(process)
    reference = Runtime.load(artifacts("recurrence", accuracy, process))
    expected = _scaled_partials(reference.evaluate_orders(points), 0.13, 1 / 128.0)
    runtime = Runtime.load(artifacts(mode, accuracy, process))
    default = _real(runtime.evaluate(points))
    runtime.set_model_parameter("normalization.alpha_s_me_check", 0.13)
    runtime.set_model_parameter("normalization.alpha_ew", 1 / 128.0)
    for value, target in zip(_real(runtime.evaluate(points)), expected, strict=True):
        assert value == pytest.approx(target, rel=1e-12, abs=0.0)
    if mode == "recurrence":
        rebound = runtime.evaluate_orders(points)
        default_split = reference.evaluate_orders(points)
        for order in rebound.orders:
            powers = dict(order)
            weight = (0.13 / _ALPHA_S) ** (powers.get("QCD", 0) / 2) * (
                (1 / 128.0) / _ALPHA_EW
            ) ** (powers.get("QED", 0) / 2)
            for value, base in zip(
                _real(rebound.for_order(order)),
                _real(default_split.for_order(order)),
                strict=True,
            ):
                assert value == pytest.approx(weight * base, rel=1e-12, abs=1e-300)
    runtime.set_model_parameter("normalization.alpha_s_me_check", _ALPHA_S)
    runtime.set_model_parameter("normalization.alpha_ew", _ALPHA_EW)
    assert _real(runtime.evaluate(points)) == default


@pytest.mark.parametrize("accuracy", _ACCURACIES)
def test_a_bound_electroweak_coupling_stays_a_local_coupling(
    artifacts, accuracy: str
) -> None:
    """The electroweak coupling components stay the local couplings, weighted
    at evaluation: binding one and changing alpha commute, bitwise (eager
    mode; the recurrence and on-the-fly modes hold the couplings as exact row
    factors)."""

    process = "u u~ > d d~"
    points = _points(process)
    path = artifacts("eager", accuracy, process)
    # A photon coupling of the u line: every mode and accuracy uses it.
    (name, local) = next(
        (parameter.name, parameter.default_real)
        for parameter in Runtime.load(path).physics.model_parameters
        if parameter.name.startswith("coupling.")
        and parameter.name.split(".")[2].endswith("_22")
        and parameter.default_real != 0.0
    )
    first = Runtime.load(path)
    first.set_model_parameter(name, 1.5 * local)
    first.set_model_parameter("normalization.alpha_ew", 1 / 128.0)
    second = Runtime.load(path)
    second.set_model_parameter("normalization.alpha_ew", 1 / 128.0)
    second.set_model_parameter(name, 1.5 * local)
    assert _real(first.evaluate(points)) == _real(second.evaluate(points))
    first.set_model_parameter(name, local)
    first.set_model_parameter("normalization.alpha_ew", _ALPHA_EW)
    assert _real(first.evaluate(points)) == _real(Runtime.load(path).evaluate(points))


@pytest.mark.parametrize("mode", _MODES)
def test_alpha_s_must_stay_positive(artifacts, mode: str) -> None:
    runtime = Runtime.load(artifacts(mode, "lc", "u u~ > d d~"))
    points = _points("u u~ > d d~")
    default = _real(runtime.evaluate(points))
    with pytest.raises(Exception, match="alpha_s"):
        runtime.set_model_parameter("normalization.alpha_s_me_check", 0.0)
    assert _real(runtime.evaluate(points)) == default


@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize("accuracy", _ACCURACIES)
def test_selected_helicities_and_flows_sum_to_the_total(
    artifacts, mode: str, accuracy: str
) -> None:
    process = "u u~ > d d~ g"
    points = _points(process)
    runtime = Runtime.load(artifacts(mode, accuracy, process))
    totals = _real(runtime.evaluate(points))
    helicities = [helicity.id for helicity in runtime.physics.helicities]
    summed = [0.0] * len(points)
    for helicity in helicities:
        for point, value in enumerate(
            _real(runtime.evaluate(points, helicities=[helicity]))
        ):
            summed[point] += value
    for value, total in zip(summed, totals, strict=True):
        assert value == pytest.approx(total, rel=1e-12, abs=0.0)
    if accuracy != "lc":
        return
    flows = [flow.id for flow in runtime.physics.color_flows]
    summed = [0.0] * len(points)
    for flow in flows:
        for point, value in enumerate(
            _real(runtime.evaluate(points, color_flows=[flow]))
        ):
            summed[point] += value
    for value, total in zip(summed, totals, strict=True):
        assert value == pytest.approx(total, rel=1e-12, abs=0.0)
