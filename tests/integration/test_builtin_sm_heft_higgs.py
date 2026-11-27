# SPDX-License-Identifier: 0BSD
"""Built-in SM + HEFT: a Higgs between the effective gluon vertex and the rest.

* Gluons fusing into an internal Higgs that decays into colour singlets
  (``g g > z z``, ``g g > h h``): the compiled and eager modes refused them
  ("no model-supported tree-level amplitudes"), because their colour-order
  pruning built colour-singlet-only currents on open colour lines only. They
  are now served in every mode and equal MadGraph's ``heft``.
* A colour singlet exchanged between a pure-gluon part and a quark line
  (``g g > t t~`` through ``g g -> H* -> t t~``, ``t g > t g g``,
  ``u u~ > z g g``): its colour, an open line times a closed gluon trace, has
  no colour-flow sector in this version; the compiled and eager modes gave a
  wrong value, the recurrence and on-the-fly modes dropped it. Generation now
  refuses it in every mode (``SingletExchangeColourError``); ``HIG = 0``
  serves the rest.

References: MadGraph5_aMC 3.7.0 standalone split orders (QCD, QED, HIG) with
the ``heft`` model of UFOmodeldb at the parameters of ``built-in-sm-heft``
(``MT = ymt = 173``, ``ymb = MB = 4.7``, ``MZ = 91.188``, ``aEWM1 = 132.507``;
``fixtures/tree/madgraph-split-orders-heft*.json``, written by
``tools/developer/madgraph_split_orders.py --orders QCD,QED,HIG --set-param``),
also after a run-time change of ``MH`` and of ``ymt``.
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

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/tree"
_MODES = ("recurrence", "compiled", "eager", "on-the-fly")


def _references(tag: str = "") -> dict[str, dict[str, object]]:
    name = "madgraph-split-orders-heft" + (f"-{tag}" if tag else "") + ".json"
    payload = json.loads((_FIXTURES / name).read_text(encoding="utf-8"))
    return {entry["process"]: entry for entry in payload["processes"]}


def _config(mode: str, accuracy: str, orders: dict[str, int] | None) -> RunConfig:
    return RunConfig(
        action="generate",
        model=ModelConfig(cache=False),
        color=ColorConfig(accuracy=accuracy),
        process=(
            ProcessConfig()
            if orders is None
            else ProcessConfig(
                coupling_order_policy="explicit", max_coupling_orders=orders
            )
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


@pytest.fixture(scope="module")
def generate(tmp_path_factory: pytest.TempPathFactory):
    if importlib.util.find_spec("pyamplicol._rusticol") is None:
        pytest.skip("the Rusticol extension has not been built")
    root = tmp_path_factory.mktemp("builtin-heft-higgs")
    cache: dict[tuple[object, ...], Path] = {}

    def artifact(process: str, mode: str, accuracy: str, orders) -> Path:
        key = (process, mode, accuracy, json.dumps(orders, sort_keys=True))
        if key not in cache:
            path = root / f"a{len(cache)}"
            Generator(_config(mode, accuracy, orders)).generate(
                process, path, model=ModelSource.built_in_sm_heft()
            )
            cache[key] = path
        return cache[key]

    return artifact


def _real(values) -> list[float]:
    return [complex(value).real for value in values]


def _scale(row) -> float:
    return math.fsum(abs(value) for value in row)


# (process, order limits): every amplitude of these goes through the
# effective vertex with an internal Higgs, or interferes with one that does
# through an open colour line (t t~ > h g).
_SERVED = (
    ("g g > z z", {"QCD": 0, "QED": 1, "HIG": 1}),
    ("g g > h h", {"QCD": 0, "QED": 1, "HIG": 1}),
    ("t t~ > h g", {"QCD": 1, "QED": 1, "HIG": 1}),
)


@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize(("process", "orders"), _SERVED)
def test_internal_higgs_from_the_effective_vertex_matches_madgraph_heft(
    generate, process: str, orders, mode: str
) -> None:
    reference = _references()[process]
    runtime = Runtime.load(generate(process, mode, "full", orders))
    values = _real(runtime.evaluate(reference["points"]))
    for point, (value, row) in enumerate(
        zip(values, reference["partials"], strict=True)
    ):
        assert abs(value - math.fsum(row)) <= 1e-12 * _scale(row), point
    if mode != "recurrence":
        return
    split = runtime.evaluate_orders(reference["points"])
    labels = tuple(
        tuple(sorted((name, power) for name, power in order.items() if power))
        for order in reference["squared_orders"]
    )
    assert split.orders == tuple(sorted(labels))
    for point, row in enumerate(reference["partials"]):
        for label, expected in zip(labels, row, strict=True):
            actual = _real(split.for_order(label))[point]
            assert abs(actual - expected) <= 1e-12 * _scale(row), (point, label)


@pytest.mark.parametrize("mode", _MODES)
def test_leading_colour_lanes_agree(generate, mode: str) -> None:
    """MadGraph's leading colour needs a basis without external gluons;
    every mode at leading colour equals the recurrence mode's value."""

    process, orders = "g g > z z", {"QCD": 0, "QED": 1, "HIG": 1}
    points = _references()[process]["points"]
    expected = _real(
        Runtime.load(generate(process, "recurrence", "lc", orders)).evaluate(points)
    )
    values = _real(Runtime.load(generate(process, mode, "lc", orders)).evaluate(points))
    for value, target in zip(values, expected, strict=True):
        assert value == pytest.approx(target, rel=1e-12, abs=0.0)


@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize(
    ("process", "orders", "tag", "parameters"),
    (
        ("g g > z z", {"QCD": 0, "QED": 1, "HIG": 1}, "mh200", {"MH": 200.0}),
        ("g g > h g", {"QCD": 1, "QED": 0, "HIG": 1}, "mh200", {"MH": 200.0}),
        ("t t~ > h g", {"QCD": 1, "QED": 1, "HIG": 1}, "ymt200", {"ymt": 200.0}),
    ),
)
def test_rebinding_mh_and_the_top_yukawa_follows_madgraph_heft(
    generate, process: str, orders, tag: str, parameters, mode: str
) -> None:
    """The effective coupling depends on MH and MT, the Higgs propagator on
    MH, the top Yukawa on ymt: a run-time change equals MadGraph at the
    changed values and a load with the values bound."""

    reference = _references(tag)[process]
    path = generate(process, mode, "full", orders)
    runtime = Runtime.load(path)
    for name, value in parameters.items():
        runtime.set_model_parameter(name, value)
    values = _real(runtime.evaluate(reference["points"]))
    for value, expected in zip(values, reference["total"], strict=True):
        assert value == pytest.approx(expected, rel=1e-12, abs=0.0)
    bound = Runtime.load(path, model_parameters=parameters)
    assert _real(bound.evaluate(reference["points"])) == values


@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize("accuracy", ("lc", "nlc", "full"))
def test_singlet_exchange_with_a_closed_gluon_trace_is_refused(
    generate, accuracy: str, mode: str
) -> None:
    """Every mode and accuracy refuses the request before lowering and names
    the order that removes these trees."""

    with pytest.raises(GenerationError, match="closed gluon trace") as refused:
        generate("g g > t t~", mode, accuracy, {"QCD": 2, "QED": 1, "HIG": 1})
    assert "HIG = 0" in str(refused.value)


@pytest.mark.parametrize(
    ("process", "orders"),
    (
        ("u u~ > z g g", {"QCD": 2, "QED": 2, "HIG": 1}),
        ("t g > t g g", {"QCD": 3, "QED": 0, "HIG": 2}),
        ("g g > h t t~", {"QCD": 2, "QED": 2, "HIG": 1}),
    ),
)
def test_the_refused_class_reaches_through_z_bosons_and_effective_vertices(
    generate, process: str, orders
) -> None:
    with pytest.raises(GenerationError, match="closed gluon trace"):
        generate(process, "compiled", "full", orders)


@pytest.mark.parametrize("mode", _MODES)
def test_default_orders_follow_the_expansion_order_of_the_effective_coupling(
    generate, mode: str
) -> None:
    """The minimal policy works within the UFO expansion orders (HIG <= 1 per
    amplitude, as MadGraph): the default t g > t g g is its QCD tree, equal
    to the HIG = 0 request bitwise and to MadGraph's QCD^6 split order."""

    process = "t g > t g g"
    reference = _references()[process]
    points = reference["points"]
    default = _real(
        Runtime.load(generate(process, mode, "full", None)).evaluate(points)
    )
    explicit = _real(
        Runtime.load(
            generate(process, mode, "full", {"QCD": 3, "QED": 0, "HIG": 0})
        ).evaluate(points)
    )
    assert default == explicit
    column = next(
        index
        for index, order in enumerate(reference["squared_orders"])
        if order == {"QCD": 6, "QED": 0, "HIG": 0}
    )
    for value, row in zip(default, reference["partials"], strict=True):
        assert value == pytest.approx(row[column], rel=1e-12, abs=0.0)


@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize(
    ("process", "orders"),
    (
        ("g g > t t~", {"QCD": 2, "QED": 1, "HIG": 0}),
        ("u u~ > h g g", {"QCD": 2, "QED": 2, "HIG": 1}),
    ),
)
def test_requests_without_that_exchange_still_build(
    generate, process: str, orders, mode: str
) -> None:
    generate(process, mode, "full", orders)
