# SPDX-License-Identifier: 0BSD
"""Built-in SM: Higgs exchange between two fermion lines.

The built-in vertex table carries the Yukawa interaction in every orientation
a tree needs: a fermion and a Higgs fuse into a fermion (either input order,
one evaluation class, so a recurrence parent pair counts the vertex once), and
a fermion pair fuses into the Higgs current. Without the last one the
s- and t-channel Higgs exchange between two top lines was missing and
``t t~ > t t~`` at QCD=0 QED=2 was 0.633 instead of 1.563 at the default
point, without a message.

The values are compared with MadGraph5_aMC 3.7.0 standalone split orders
(model ``sm``, restrict_default, ``zerowidth_tchannel False``;
``fixtures/tree/madgraph-split-orders-builtin-higgs*.json``, written by
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
    "full": _FIXTURES / "madgraph-split-orders-builtin-higgs.json",
    "lc": _FIXTURES / "madgraph-split-orders-builtin-higgs-lc.json",
}
# (process, coupling-order limits): the pure electroweak request and the
# request with every Born order (the interference with gluon exchange).
_REQUESTS = (
    ("t t~ > t t~", {"QCD": 0, "QED": 2}),
    ("t t~ > t t~", {"QCD": 2, "QED": 2}),
    ("t t > t t", {"QCD": 0, "QED": 2}),
    ("t t > t t", {"QCD": 2, "QED": 2}),
    ("t t~ > t t~ h", {"QCD": 2, "QED": 3}),
)
_MODES = ("recurrence", "compiled", "eager", "on-the-fly")
_ACCURACIES = ("lc", "full")


def _reference(process: str, accuracy: str) -> dict[str, object]:
    for entry in json.loads(_REFERENCES[accuracy].read_text(encoding="utf-8"))[
        "processes"
    ]:
        if entry["process"] == process:
            return entry
    raise AssertionError(process)


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


def _generator(root: Path, model: ModelSource):
    cache: dict[tuple[str, str, str, str], Path] = {}

    def artifact(mode: str, accuracy: str, process: str, orders) -> Path:
        key = (mode, accuracy, process, json.dumps(orders, sort_keys=True))
        if key not in cache:
            path = root / f"{mode}-{accuracy}-{len(cache)}"
            Generator(_config(mode, accuracy, orders)).generate(
                process, path, model=model
            )
            cache[key] = path
        return cache[key]

    return artifact


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory: pytest.TempPathFactory):
    _require_native()
    return _generator(
        tmp_path_factory.mktemp("builtin-higgs"), ModelSource.built_in_sm()
    )


@pytest.fixture(scope="module")
def ufo_artifacts(madgraph_source: Path, tmp_path_factory: pytest.TempPathFactory):
    """The same requests on the UFO ``sm`` (restrict_default)."""

    _require_native()
    root = tmp_path_factory.mktemp("builtin-higgs-ufo")
    bundle = root / "sm.pyamplicol-model"
    ModelSource.from_path(madgraph_source / "models/sm", restriction="default").compile(
        cache_dir=root / "cache", prepared_output=bundle, evaluator=EvaluatorConfig()
    )
    return _generator(root, ModelSource.from_path(bundle))


def _real(values) -> list[float]:
    result = []
    for value in values:
        value = complex(value)
        assert value.imag == 0.0
        result.append(value.real)
    return result


def _expected(reference, orders: dict[str, int]) -> tuple[tuple, list[list[float]]]:
    """MadGraph's squared orders a request keeps, and their partials. The
    amplitude QCD orders of these Borns step by two, so a squared order
    (Q, E) comes from amplitudes within the limits exactly when Q and E are
    at most twice the limits."""

    keep = [
        index
        for index, order in enumerate(reference["squared_orders"])
        if order["QCD"] <= 2 * orders["QCD"] and order["QED"] <= 2 * orders["QED"]
    ]
    labels = tuple(
        tuple(
            sorted(
                (name, power)
                for name, power in reference["squared_orders"][index].items()
                if power
            )
        )
        for index in keep
    )
    partials = [[row[index] for index in keep] for row in reference["partials"]]
    return labels, partials


_DEFAULT_TIER = {("t t~ > t t~", "QCD=0,QED=2"), ("t t~ > t t~", "QCD=2,QED=2")}
_CELLS = [
    pytest.param(
        process,
        orders,
        mode,
        accuracy,
        id=f"{process}-QCD{orders['QCD']}QED{orders['QED']}-{mode}-{accuracy}",
        marks=()
        if (process, f"QCD={orders['QCD']},QED={orders['QED']}") in _DEFAULT_TIER
        else pytest.mark.loop_nightly,
    )
    for process, orders in _REQUESTS
    for mode in _MODES
    for accuracy in _ACCURACIES
]


@pytest.mark.parametrize(("process", "orders", "mode", "accuracy"), _CELLS)
def test_higgs_exchange_matches_madgraph_and_the_ufo_sm(
    artifacts, ufo_artifacts, process: str, orders, mode: str, accuracy: str
) -> None:
    """The total equals MadGraph's sum of the split orders the request keeps
    and the UFO ``sm`` value of the same mode and accuracy; the recurrence
    mode's squared-order partials equal MadGraph's and the UFO ``sm``'s."""

    reference = _reference(process, accuracy)
    points = reference["points"]
    labels, partials = _expected(reference, orders)
    runtime = Runtime.load(artifacts(mode, accuracy, process, orders))
    totals = _real(runtime.evaluate(points))
    ufo = Runtime.load(ufo_artifacts(mode, accuracy, process, orders))
    for value, expected in zip(totals, _real(ufo.evaluate(points)), strict=True):
        assert value == pytest.approx(expected, rel=1e-12, abs=0.0)
    for point, (total, row) in enumerate(zip(totals, partials, strict=True)):
        scale = math.fsum(abs(value) for value in row)
        # MadGraph sums its diagrams in another order: 2e-12 at the second
        # point of t t > t t (leading colour) is rounding.
        assert abs(total - math.fsum(row)) <= 1e-10 * scale, point
    if mode != "recurrence":
        return
    split = runtime.evaluate_orders(points)
    assert split.orders == ufo.evaluate_orders(points).orders
    assert split.orders == tuple(sorted(labels))
    for point, row in enumerate(partials):
        scale = math.fsum(abs(value) for value in row)
        for order, expected in zip(labels, row, strict=True):
            actual = _real(split.for_order(order))[point]
            assert abs(actual - expected) <= 1e-10 * scale, (point, order)
