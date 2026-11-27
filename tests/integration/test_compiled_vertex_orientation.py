# SPDX-License-Identifier: 0BSD
"""Compiled and eager lanes: a vertex the model lists in one input order only.

The compiled and eager lanes build their DAG from ordered splits of the leg
set and look a vertex up by its ordered inputs, while the colour engine keeps
one order of each merge. A vertex the model lists only in the order the colour
engine refuses was dropped without a message: the built-in SM listed the top
Yukawa with the Higgs as the right input only, so a Higgs current carrying
coloured labels (a Z or W from a light-quark line fusing with a Z or W) was
never absorbed on a top line. ``s t > s t z`` at QCD=0 was 58 % off and
``s t > s t mu+ mu-`` at QCD=0 1.2 %, in both lanes, at full and leading
colour; the recurrence and on-the-fly lanes, which pair parents in both
orders, equal MadGraph.

These lanes now refuse such a merge with ``VertexOrientationUnavailable``.
With a model that lists the vertex in both input orders they give MadGraph's
value. The tests take the branch from the model itself: every vertex whose
inputs are not a fermion and an antifermion must have its exchanged order.

References: MadGraph5_aMC 3.7.0 standalone split orders (model ``sm``,
restriction ``no_masses``, the built-in parameters: the b quark is massless,
which the W-radiation diagrams see; ``zerowidth_tchannel False``;
``fixtures/tree/madgraph-split-orders-vertex-orientation*.json``, written by
``tools/developer/madgraph_split_orders.py``); a request at QCD=0 keeps the
squared orders without QCD.
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import pytest

from pyamplicol import Generator, ModelSource, Runtime
from pyamplicol.api.errors import GenerationError
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
from pyamplicol.generation.dag_compiler import GenericDAGCompiler
from pyamplicol.generation.dag_ordering import VertexOrientationUnavailable
from pyamplicol.models import BuiltinSMModel
from pyamplicol.models.builtin.process_ir import build_process_ir

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/tree"
_REFERENCES = {
    "full": _FIXTURES / "madgraph-split-orders-vertex-orientation.json",
    "lc": _FIXTURES / "madgraph-split-orders-vertex-orientation-lc.json",
}
# (process, coupling-order limits). The first two are the smallest process
# and the reported one; the others are the largest departures of a sweep of
# the class (light-quark line with Z or W radiation, the Z or W decayed, and
# the s-channel form).
_REQUESTS = (
    ("s t > s t z", {"QCD": 0, "QED": 3}),
    ("s t > s t mu+ mu-", {"QCD": 0, "QED": 4}),
    ("c~ t > c~ t z", {"QCD": 0, "QED": 3}),
    ("d t~ > d t~ mu+ mu-", {"QCD": 0, "QED": 4}),
    ("u t > d t w+", {"QCD": 0, "QED": 3}),
)
_DEFAULT_TIER = {"s t > s t z"}
_MODES = ("recurrence", "compiled", "eager", "on-the-fly")
_ACCURACIES = ("lc", "full")
# The modes that build the DAG from ordered splits.
_ORDERED_SPLIT_MODES = {"compiled", "eager"}


def _exchanged_orders_listed(model: BuiltinSMModel) -> bool:
    """Whether the model lists every vertex whose inputs are not a fermion
    and an antifermion in both input orders."""

    for accuracy in _ACCURACIES:
        listed = {
            vertex.particles for vertex in model.iter_vertices(color_accuracy=accuracy)
        }
        for first, second, result in listed:
            if first == second or (
                model.is_fermion(first) and model.is_fermion(second)
            ):
                continue
            if (second, first, result) not in listed:
                return False
    return True


_COMPLETE = _exchanged_orders_listed(BuiltinSMModel())


def _reference(process: str, accuracy: str) -> dict[str, object]:
    for entry in json.loads(_REFERENCES[accuracy].read_text(encoding="utf-8"))[
        "processes"
    ]:
        if entry["process"] == process:
            return entry
    raise AssertionError(process)


def _expected(reference) -> list[float]:
    keep = [
        index
        for index, order in enumerate(reference["squared_orders"])
        if order["QCD"] == 0
    ]
    return [math.fsum(row[index] for index in keep) for row in reference["partials"]]


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
    _require_native()
    root = tmp_path_factory.mktemp("vertex-orientation")
    cache: dict[tuple[str, str, str], Path | GenerationError] = {}

    def artifact(mode: str, accuracy: str, process: str, orders) -> Path:
        key = (mode, accuracy, process)
        if key not in cache:
            path = root / f"{mode}-{accuracy}-{len(cache)}"
            try:
                Generator(_config(mode, accuracy, orders)).generate(
                    process, path, model=ModelSource.built_in_sm()
                )
                cache[key] = path
            except GenerationError as exc:
                cache[key] = exc
        entry = cache[key]
        if isinstance(entry, GenerationError):
            raise entry
        return entry

    return artifact


def _real(values) -> list[float]:
    result = []
    for value in values:
        value = complex(value)
        assert value.imag == 0.0
        result.append(value.real)
    return result


def _close(values, expected, tolerance: float = 1e-10) -> None:
    for point, (value, target) in enumerate(zip(values, expected, strict=True)):
        assert abs(float(value) - target) <= tolerance * abs(target), point


def _refused(exc: BaseException) -> bool:
    while exc is not None:
        if isinstance(exc, VertexOrientationUnavailable):
            return True
        exc = exc.__cause__
    return False


_CELLS = [
    pytest.param(
        process,
        orders,
        mode,
        accuracy,
        id=f"{process}-{mode}-{accuracy}",
        marks=() if process in _DEFAULT_TIER else pytest.mark.loop_nightly,
    )
    for process, orders in _REQUESTS
    for mode in _MODES
    for accuracy in _ACCURACIES
]


@pytest.mark.parametrize(("process", "orders", "mode", "accuracy"), _CELLS)
def test_madgraph_value_or_typed_refusal(
    artifacts, process: str, orders, mode: str, accuracy: str
) -> None:
    """Every mode gives MadGraph's value at binary64 (and at 50 digits where
    the mode evaluates them), except that the compiled and eager modes refuse
    with ``VertexOrientationUnavailable`` while the model lists a vertex in
    one input order only. Never a wrong value."""

    reference = _reference(process, accuracy)
    points = reference["points"]
    expected = _expected(reference)
    if mode in _ORDERED_SPLIT_MODES and not _COMPLETE:
        with pytest.raises(GenerationError) as caught:
            artifacts(mode, accuracy, process, orders)
        assert _refused(caught.value)
        assert "vertex-orientation-unavailable" in str(caught.value)
        return
    runtime = Runtime.load(artifacts(mode, accuracy, process, orders))
    _close(_real(runtime.evaluate(points)), expected)
    if mode != "on-the-fly":
        _close(runtime.evaluate(points, precision=50), expected)


@pytest.mark.parametrize("accuracy", _ACCURACIES)
@pytest.mark.parametrize("mode", _MODES)
def test_32_digits(artifacts, mode: str, accuracy: str) -> None:
    process, orders = _REQUESTS[0]
    reference = _reference(process, accuracy)
    if mode == "on-the-fly" or (mode in _ORDERED_SPLIT_MODES and not _COMPLETE):
        pytest.skip("no 32-digit evaluation in this mode")
    runtime = Runtime.load(artifacts(mode, accuracy, process, orders))
    _close(runtime.evaluate(reference["points"], precision=32), _expected(reference))


@pytest.mark.parametrize("accuracy", _ACCURACIES)
def test_selection_sums_and_rebinding(artifacts, accuracy: str) -> None:
    """Helicity and colour-flow selection sum to the total in every mode that
    builds; a run-time Higgs mass is the same in every such mode, and the
    default value comes back."""

    process, orders = _REQUESTS[0]
    points = _reference(process, accuracy)["points"]
    default = _expected(_reference(process, accuracy))
    rebound: dict[str, list[float]] = {}
    for mode in _MODES:
        if mode in _ORDERED_SPLIT_MODES and not _COMPLETE:
            continue
        runtime = Runtime.load(artifacts(mode, accuracy, process, orders))
        total = _real(runtime.evaluate(points))
        helicities = [0.0] * len(points)
        for helicity in runtime.physics.helicity_ids:
            for index, value in enumerate(
                _real(runtime.evaluate(points, helicities=[helicity]))
            ):
                helicities[index] += value
        _close(helicities, total, 1e-12)
        flows = list(runtime.physics.color_flow_ids)
        if flows:
            summed = [0.0] * len(points)
            for flow in flows:
                for index, value in enumerate(
                    _real(runtime.evaluate(points, color_flows=[flow]))
                ):
                    summed[index] += value
            _close(summed, total, 1e-12)
        (mass,) = (
            parameter.default_real
            for parameter in runtime.physics.model_parameters
            if parameter.name == "particle.25.mass"
        )
        runtime.set_model_parameter("particle.25.mass", 300.0)
        rebound[mode] = _real(runtime.evaluate(points))
        runtime.set_model_parameter("particle.25.mass", mass)
        # Restoring the default rederives the dependent parameters: equal to
        # rounding, not bitwise.
        _close(_real(runtime.evaluate(points)), total, 1e-15)
    reference = rebound["recurrence"]
    # The Higgs-exchange diagrams are a visible part of the value.
    assert any(
        abs(value - target) > 1e-2 * abs(target)
        for value, target in zip(reference, default, strict=True)
    )
    for values in rebound.values():
        _close(values, reference, 1e-12)


def _without_exchanged_yukawa(model: BuiltinSMModel) -> type[BuiltinSMModel]:
    """The built-in SM with each scalar-fermion vertex listed with the scalar
    as the right input only (as before the two orders were listed)."""

    class OneOrder(type(model)):
        def iter_vertices(self, *, color_accuracy: str = "lc"):
            for vertex in super().iter_vertices(color_accuracy=color_accuracy):
                first, second, result = vertex.particles
                if (
                    second == result
                    and self.is_fermion(second)
                    and not self.is_fermion(first)
                    and self.particle(first).spin == 1
                ):
                    continue
                yield vertex

    return OneOrder


@pytest.mark.parametrize("accuracy", _ACCURACIES)
def test_the_dag_compiler_refuses_the_missing_order(accuracy: str) -> None:
    """With the exchanged Yukawa order removed from the table, the DAG of
    ``s t > s t z`` at QCD=0 is refused; ``e- t > e- t z`` (whose Higgs
    current carries no coloured labels, so the kept order is listed) and the
    complete table build."""

    one_order = _without_exchanged_yukawa(BuiltinSMModel())()
    limits = {"QCD": 0, "QED": 3}
    with pytest.raises(VertexOrientationUnavailable, match="vertex-orientation"):
        GenericDAGCompiler(model=one_order, max_coupling_orders=limits).compile(
            build_process_ir("s t > s t z", color_accuracy=accuracy)
        )
    dag = GenericDAGCompiler(model=one_order, max_coupling_orders=limits).compile(
        build_process_ir("e- t > e- t z", color_accuracy=accuracy)
    )
    assert dag.amplitude_roots
    if _COMPLETE:
        dag = GenericDAGCompiler(
            model=BuiltinSMModel(), max_coupling_orders=limits
        ).compile(build_process_ir("s t > s t z", color_accuracy=accuracy))
        assert dag.amplitude_roots
