# SPDX-License-Identifier: 0BSD
"""Squared coupling-order partials of the compiled and on-the-fly lanes.

Every amplitude root of a compiled artifact has one amplitude coupling order,
recorded at generation (``physics.json`` extension ``amplitude_orders``);
``Runtime.evaluate_orders`` reduces the roots of every ordered component pair.
The on-the-fly lane derives each closure's order from its query trace and
evaluates every component of every query in a family of its own.
The partials are checked against MadGraph 3.7.0 split orders (the committed
references of ``test_tree_coupling_orders.py``, produced by
``tools/developer/madgraph_split_orders.py`` from standalone output of the UFO
``sm`` model, default restriction, t-channel widths kept), against the
recurrence lane's partials of the same process, per global helicity and
colour-flow selection, above binary64, after a run-time ``aS`` change and
against a fresh generation at the new value. Totals are always those of
``evaluate``.
"""

from __future__ import annotations

import json
import math
from decimal import Decimal
from pathlib import Path

import pytest

from pyamplicol import Generator, ModelSource, Runtime, TreeOrderEvaluation
from pyamplicol.api.errors import CompatibilityError
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

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/tree"
REFERENCE = FIXTURES / "madgraph-split-orders.json"
LC_REFERENCE = FIXTURES / "madgraph-split-orders-lc.json"
ORDER_LIMITS = {"QCD": 99, "QED": 99}


def _reference(process: str, path: Path = REFERENCE) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    (entry,) = (item for item in payload["processes"] if item["process"] == process)
    return entry


@pytest.fixture(scope="module")
def sm_bundle(madgraph_source: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("order-split-sm")
    bundle = root / "sm.pyamplicol-model"
    ModelSource.from_path(madgraph_source / "models/sm", restriction="default").compile(
        cache_dir=root / "cache",
        prepared_output=bundle,
        evaluator=EvaluatorConfig(),
    )
    return bundle


@pytest.fixture(scope="module")
def sm_model(sm_bundle: Path) -> ModelSource:
    return ModelSource.from_path(sm_bundle)


def _config(
    *,
    accuracy: str,
    execution_mode: str,
    limits: dict[str, int] | None,
    lc_flow_layout: str = "topology-replay",
) -> RunConfig:
    return RunConfig(
        action="generate",
        model=ModelConfig(cache=False),
        color=ColorConfig(accuracy=accuracy, lc_flow_layout=lc_flow_layout),
        process=(
            ProcessConfig()
            if limits is None
            else ProcessConfig(
                coupling_order_policy="explicit", max_coupling_orders=limits
            )
        ),
        generation=GenerationConfig(
            workers=1,
            emit_api_bundle=False,
            relation_discovery=GenerationRelationDiscoveryConfig(mode="off"),
            validation=GenerationValidationConfig(
                enabled=False, samples=1, seed=7, post_build_validation=False
            ),
        ),
        evaluator=EvaluatorConfig(
            execution_mode=execution_mode,
            optimization=EvaluatorOptimizationConfig(cores=1),
        ),
    )


def _runtime(
    model: ModelSource | None,
    process: str,
    artifact: Path,
    *,
    accuracy: str = "full",
    execution_mode: str = "compiled",
    limits: dict[str, int] | None = ORDER_LIMITS,
    lc_flow_layout: str = "topology-replay",
) -> Runtime:
    config = _config(
        accuracy=accuracy,
        execution_mode=execution_mode,
        limits=limits,
        lc_flow_layout=lc_flow_layout,
    )
    if model is None:
        Generator(config).generate(process, artifact)
    else:
        Generator(config).generate(process, artifact, model=model)
    return Runtime.load(artifact)


def _scale(result: TreeOrderEvaluation, point: int) -> float:
    return math.fsum(abs(complex(value).real) for value in result.values[point])


def _assert_partials_keep_the_total(
    runtime: Runtime, result: TreeOrderEvaluation, points, **selectors
) -> None:
    assert result.total == runtime.evaluate(points, **selectors)
    for point, (total, summed) in enumerate(
        zip(result.total, result.sum_orders(), strict=True)
    ):
        assert abs(complex(summed).real - complex(total).real) <= 1e-13 * max(
            _scale(result, point), abs(complex(total))
        ), point


def _assert_same_partials(
    actual: TreeOrderEvaluation, expected: TreeOrderEvaluation, tolerance: float
) -> None:
    assert actual.amplitude_orders == expected.amplitude_orders
    assert actual.orders == expected.orders
    assert actual.sectors == expected.sectors
    for point in range(len(expected.values)):
        scale = max(_scale(expected, point), _scale(actual, point))
        for order in expected.orders:
            left = complex(actual.for_order(order)[point]).real
            right = complex(expected.for_order(order)[point]).real
            assert abs(left - right) <= tolerance * scale, (point, order)


def _assert_matches_madgraph(result: TreeOrderEvaluation, reference) -> None:
    expected_orders = tuple(
        tuple(sorted((name, power) for name, power in order.items() if power))
        for order in reference["squared_orders"]
    )
    assert result.orders == tuple(sorted(expected_orders))
    for point, partials in enumerate(reference["partials"]):
        scale = math.fsum(abs(value) for value in partials)
        assert abs(complex(result.total[point]).real - math.fsum(partials)) <= (
            1e-12 * scale
        ), point
        for order, expected in zip(expected_orders, partials, strict=True):
            actual = complex(result.for_order(order)[point])
            assert actual.imag == 0.0
            assert abs(actual.real - expected) <= 1e-12 * scale, (point, order)


# Two Born coupling orders: QCD x EW interference between s, t and u
# channels, identical quarks, a radiated gluon (colour contraction at full
# colour; colour flows at leading colour).
_FULL_COLOUR_PROCESSES = (
    "u u~ > d d~",
    "u u~ > u u~",
    "u d > u d",
    "u u~ > d d~ g",
    "u u~ > u u~ g",
)
_LEADING_COLOUR_PROCESSES = ("u u~ > d d~", "u u~ > u u~", "u d > u d")
_LANES = ("compiled", "on-the-fly")


@pytest.mark.parametrize("lane", _LANES)
@pytest.mark.parametrize("process", _FULL_COLOUR_PROCESSES)
def test_partials_match_madgraph_and_keep_the_total(
    sm_model: ModelSource, tmp_path: Path, process: str, lane: str
) -> None:
    reference = _reference(process)
    runtime = _runtime(sm_model, process, tmp_path / "artifact", execution_mode=lane)
    points = reference["points"]

    result = runtime.evaluate_orders(points)

    _assert_partials_keep_the_total(runtime, result, points)
    _assert_matches_madgraph(result, reference)


@pytest.mark.parametrize("lane", _LANES)
@pytest.mark.parametrize("process", _LEADING_COLOUR_PROCESSES)
def test_leading_colour_partials_match_madgraph(
    sm_model: ModelSource, tmp_path: Path, process: str, lane: str
) -> None:
    reference = _reference(process, LC_REFERENCE)
    runtime = _runtime(
        sm_model, process, tmp_path / "artifact", accuracy="lc", execution_mode=lane
    )
    points = reference["points"]

    result = runtime.evaluate_orders(points)

    _assert_partials_keep_the_total(runtime, result, points)
    _assert_matches_madgraph(result, reference)


@pytest.mark.parametrize("lane", _LANES)
@pytest.mark.parametrize(
    ("process", "accuracy"),
    [
        ("u u~ > d d~", "full"),
        ("u u~ > d d~", "lc"),
        ("u u~ > d d~ g", "full"),
        ("u u~ > d d~ g", "lc"),
        ("u u~ > u u~ g", "lc"),
        ("g u > u d d~", "full"),
        ("g u > u d d~", "lc"),
        ("u u~ > t t~", "full"),
        ("u u~ > t t~", "lc"),
        ("u u~ > d d~ g", "nlc"),
        ("g u > u d d~", "nlc"),
    ],
)
def test_partials_equal_the_recurrence_lane_per_selection(
    sm_model: ModelSource, tmp_path: Path, process: str, accuracy: str, lane: str
) -> None:
    limits = {"QCD": 3, "QED": 2} if process.count(" ") > 4 else {"QCD": 2, "QED": 2}
    lane_runtime = _runtime(
        sm_model,
        process,
        tmp_path / "lane",
        accuracy=accuracy,
        limits=limits,
        execution_mode=lane,
    )
    recurrence = _runtime(
        sm_model,
        process,
        tmp_path / "recurrence",
        accuracy=accuracy,
        execution_mode="recurrence",
        limits=limits,
    )
    points = [recurrence._backend.validation_momenta()[0]]
    reference = _reference(process) if process in _FULL_COLOUR_PROCESSES else None
    if reference is not None and accuracy == "full":
        points = reference["points"]

    result = lane_runtime.evaluate_orders(points)
    assert len(result.amplitude_orders) == 2
    _assert_partials_keep_the_total(lane_runtime, result, points)
    _assert_same_partials(result, recurrence.evaluate_orders(points), 1e-12)

    # Every global helicity selection, alone; a colour-flow selection at
    # leading colour (each flow alone, then two together).
    for helicity in lane_runtime.physics.helicities:
        selected = lane_runtime.evaluate_orders(points, helicities=[helicity.id])
        _assert_partials_keep_the_total(
            lane_runtime, selected, points, helicities=[helicity.id]
        )
        _assert_same_partials(
            selected,
            recurrence.evaluate_orders(points, helicities=[helicity.id]),
            1e-12,
        )
    if accuracy == "lc":
        flows = [flow.id for flow in lane_runtime.physics.color_flows]
        for selection in ([flows[0]], flows[:2], [flows[-1]]):
            selected = lane_runtime.evaluate_orders(points, color_flows=selection)
            _assert_partials_keep_the_total(
                lane_runtime, selected, points, color_flows=selection
            )
            _assert_same_partials(
                selected,
                recurrence.evaluate_orders(points, color_flows=selection),
                1e-12,
            )
    with pytest.raises(CompatibilityError):
        lane_runtime.evaluate_orders(points, helicity_by_point=[0] * len(points))


@pytest.mark.parametrize("accuracy", ["full", "lc"])
def test_compiled_extended_precision_partials(
    sm_model: ModelSource, tmp_path: Path, accuracy: str
) -> None:
    runtime = _runtime(
        sm_model, "u u~ > d d~ g", tmp_path / "artifact", accuracy=accuracy
    )
    points = _reference("u u~ > d d~ g")["points"][:1]

    exact = runtime.evaluate_orders(points, precision=32)
    native = runtime.evaluate_orders(points)

    assert exact.total == runtime.evaluate(points, precision=32)
    assert exact.orders == native.orders
    assert all(isinstance(value, Decimal) for value in exact.values[0])
    assert abs(exact.sum_orders()[0] - exact.total[0]) <= Decimal("1e-30") * abs(
        exact.total[0]
    )
    scale = math.fsum(abs(float(value)) for value in exact.values[0])
    for exact_value, native_value in zip(
        exact.values[0], native.values[0], strict=True
    ):
        assert abs(float(exact_value) - complex(native_value).real) <= 1e-13 * scale


@pytest.mark.parametrize("lane", _LANES)
def test_single_order_process_has_one_partial(
    sm_model: ModelSource, tmp_path: Path, lane: str
) -> None:
    reference = _reference("g g > t t~")
    runtime = _runtime(
        sm_model, "g g > t t~", tmp_path / "artifact", execution_mode=lane
    )
    points = reference["points"]

    result = runtime.evaluate_orders(points)

    assert result.amplitude_orders == ((("QCD", 2),),)
    assert result.orders == ((("QCD", 4),),)
    assert result.total == runtime.evaluate(points)
    _assert_matches_madgraph(result, reference)
    for point, total in enumerate(result.total):
        assert result.values[point] == (total,)


@pytest.mark.parametrize("lane", _LANES)
def test_partials_follow_a_runtime_alpha_s_change(
    sm_model: ModelSource, tmp_path: Path, lane: str
) -> None:
    """Each partial scales by its own QCD power, as a fresh generation at the
    new value gives (generation keeps no value-dependent decision here)."""

    process = "u u~ > d d~ g"
    points = _reference(process)["points"]
    runtime = _runtime(sm_model, process, tmp_path / "artifact", execution_mode=lane)
    alpha_s = 0.118
    runtime.set_model_parameters({"aS": alpha_s})
    before = runtime.evaluate_orders(points)
    runtime.set_model_parameters({"aS": 2 * alpha_s})
    after = runtime.evaluate_orders(points)
    _assert_partials_keep_the_total(runtime, after, points)
    for point in range(len(points)):
        for order in before.orders:
            qcd = dict(order).get("QCD", 0)
            expected = complex(before.for_order(order)[point]).real * 2 ** (qcd / 2)
            actual = complex(after.for_order(order)[point]).real
            assert abs(actual - expected) <= 1e-12 * 2**3 * _scale(before, point)

    fresh_root = tmp_path / "fresh"
    fresh = _runtime(sm_model, process, fresh_root, execution_mode=lane)
    fresh.set_model_parameters({"aS": 2 * alpha_s})
    _assert_same_partials(after, fresh.evaluate_orders(points), 1e-13)


@pytest.mark.parametrize("lane", _LANES)
@pytest.mark.parametrize("process", ["u u~ > d d~", "u d > u d"])
def test_zero_colour_flow_partials_are_exact_zeros(
    sm_model: ModelSource, tmp_path: Path, process: str, lane: str
) -> None:
    """Leading colour without QCD: a flow no electroweak exchange fills, and
    one only a W pairing fills for some helicities (u d > u d), are the exact
    zeros of the recurrence lane in every partial, per flow and helicity."""

    limits = {"QCD": 0, "QED": 2}
    runtime = _runtime(
        sm_model,
        process,
        tmp_path / "artifact",
        accuracy="lc",
        limits=limits,
        execution_mode=lane,
    )
    recurrence = _runtime(
        sm_model,
        process,
        tmp_path / "recurrence",
        accuracy="lc",
        execution_mode="recurrence",
        limits=limits,
    )
    points = _reference(process, LC_REFERENCE)["points"]
    selections = [{"color_flows": [flow.id]} for flow in runtime.physics.color_flows]
    selections += [{"helicities": [h.id]} for h in runtime.physics.helicities]
    for selection in selections:
        result = runtime.evaluate_orders(points, **selection)
        expected = recurrence.evaluate_orders(points, **selection)
        _assert_same_partials(result, expected, 1e-12)
        for point_values, expected_values in zip(
            result.values, expected.values, strict=True
        ):
            for value, reference in zip(point_values, expected_values, strict=True):
                if complex(reference) == 0:
                    assert complex(value) == 0


def test_builtin_sm_single_order_compiled_partial(tmp_path: Path) -> None:
    runtime = _runtime(None, "g g > t t~", tmp_path / "artifact", limits=None)
    points = [runtime._backend.validation_momenta()[0]]

    result = runtime.evaluate_orders(points)

    assert result.amplitude_orders == ((("QCD", 2),),)
    assert result.values == tuple((total,) for total in result.total)
    assert result.total == runtime.evaluate(points)


def test_eager_artifacts_keep_refusing_partials(
    sm_model: ModelSource, tmp_path: Path
) -> None:
    runtime = _runtime(
        sm_model, "u u~ > d d~", tmp_path / "eager", execution_mode="eager"
    )
    with pytest.raises(CompatibilityError, match="eager artifacts"):
        runtime.evaluate_orders(_reference("u u~ > d d~")["points"])


def _without_amplitude_orders(source: Path, destination: Path) -> Path:
    """Copy a compiled artifact as written before it recorded root orders: the
    same payloads without the ``amplitude_orders`` physics extension, under a
    re-signed manifest."""

    import shutil

    from pyamplicol.artifacts import ArtifactBuilder, load_manifest

    shutil.copytree(source, destination)
    manifest = load_manifest(destination)
    with ArtifactBuilder(destination, mode="append") as builder:
        for record in manifest.payloads:
            if not record.path.endswith("/physics.json"):
                continue
            value = json.loads((destination / record.path).read_text())
            assert value["extensions"].pop("amplitude_orders")
            builder.discard_payloads(record.path)
            builder.add_json(
                record.path,
                value,
                role=record.role,
                process_id=record.process_id,
                compact=True,
            )
        builder.finalize(
            kind=manifest.kind,
            producer=manifest.producer,
            model=manifest.model,
            configuration=manifest.configuration,
            processes=manifest.processes,
            runtime=manifest.runtime,
            dependencies=manifest.dependencies,
            default_process_id=manifest.default_process_id,
            extensions=manifest.extensions,
        )
    return destination


def test_compiled_artifact_without_recorded_orders_evaluates_and_refuses_partials(
    sm_model: ModelSource, tmp_path: Path
) -> None:
    points = _reference("u u~ > d d~")["points"]
    current = _runtime(sm_model, "u u~ > d d~", tmp_path / "artifact")
    older = Runtime.load(
        _without_amplitude_orders(tmp_path / "artifact", tmp_path / "older")
    )

    assert older.evaluate(points) == current.evaluate(points)
    with pytest.raises(CompatibilityError, match="records no amplitude coupling"):
        older.evaluate_orders(points)
    with pytest.raises(CompatibilityError, match="records no amplitude coupling"):
        older.evaluate_orders(points, precision=32)


@pytest.mark.parametrize("lane", _LANES)
@pytest.mark.parametrize("accuracy", ["full", "nlc", "lc"])
def test_two_gluon_partials_equal_the_recurrence_lane(
    sm_model: ModelSource, tmp_path: Path, accuracy: str, lane: str
) -> None:
    """Two gluons: the compiled lane replays colour topologies (leading and
    full colour) and the on-the-fly lane's full colour uses the
    symmetric-group Fourier reducer; both split as the recurrence lane."""

    process = "u u~ > d d~ g g"
    limits = {"QCD": 4, "QED": 2}
    runtime = _runtime(
        sm_model,
        process,
        tmp_path / "lane",
        accuracy=accuracy,
        limits=limits,
        execution_mode=lane,
    )
    recurrence = _runtime(
        sm_model,
        process,
        tmp_path / "recurrence",
        accuracy=accuracy,
        execution_mode="recurrence",
        limits=limits,
    )
    points = [recurrence._backend.validation_momenta()[0]]

    result = runtime.evaluate_orders(points)

    assert len(result.amplitude_orders) == 2
    _assert_partials_keep_the_total(runtime, result, points)
    _assert_same_partials(result, recurrence.evaluate_orders(points), 1e-12)


# ---------------------------------------------------------------------------
# A user UFO whose extra coupling order makes the minimal order dominate:
# the shipped ``sm`` with the two Z-lepton couplings GC_50 and GC_59 tagged
# ``NP:1`` besides ``QED:1``. At QCD <= 0, QED <= 2, NP <= 2 the photon
# exchange of e+ e- > mu+ mu- is (QED 2, NP 0) and the Z exchange (QED 2,
# NP 2), which a Pareto-minimal order sweep would drop. MadGraph's split
# orders of the same model: ``fixtures/tree/madgraph-split-orders-np.json``
# (``tools/developer/madgraph_split_orders.py --orders QCD,QED,NP``).
NP_REFERENCE = FIXTURES / "madgraph-split-orders-np.json"
_NP_PROCESS = "e+ e- > mu+ mu-"
_NP_LIMITS = {"QCD": 0, "QED": 2, "NP": 2}


def _np_tagged_sm(source: Path, destination: Path) -> Path:
    import re
    import shutil

    shutil.copytree(
        source, destination, ignore=shutil.ignore_patterns("*.pyc", "__pycache__")
    )
    couplings = (destination / "couplings.py").read_text(encoding="utf-8")
    for name in ("GC_50", "GC_59"):
        couplings, count = re.subn(
            rf"({name} = Coupling\(name = '{name}',\n\s+value = '[^']*',\n"
            r"\s+order = )\{'QED':1\}\)",
            r"\1{'NP':1,'QED':1})",
            couplings,
        )
        assert count == 1, name
    (destination / "couplings.py").write_text(couplings, encoding="utf-8")
    orders = (destination / "coupling_orders.py").read_text(encoding="utf-8")
    orders += (
        "\nNP = CouplingOrder(name = 'NP',\n"
        "                   expansion_order = 99,\n"
        "                   hierarchy = 3)\n"
    )
    (destination / "coupling_orders.py").write_text(orders, encoding="utf-8")
    return destination


@pytest.fixture(scope="module")
def np_model(madgraph_source: Path, tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("np-tagged-sm")
    ufo = _np_tagged_sm(madgraph_source / "models/sm", root / "sm_np")
    bundle = root / "sm_np.pyamplicol-model"
    ModelSource.from_path(ufo, restriction="default").compile(
        cache_dir=root / "cache", prepared_output=bundle, evaluator=EvaluatorConfig()
    )
    return ModelSource.from_path(bundle)


def test_an_order_dominating_the_minimal_one_gets_its_own_column(
    np_model: ModelSource, tmp_path: Path
) -> None:
    """Every lane lists the three squared orders (QED^4 NP^0, NP^2, NP^4) and
    puts each contribution in its own column, as MadGraph does; on-the-fly
    and compiled equal the recurrence lane, per helicity too."""

    (reference,) = json.loads(NP_REFERENCE.read_text(encoding="utf-8"))["processes"]
    points = reference["points"]
    expected_orders = tuple(
        sorted(
            tuple(sorted((name, power) for name, power in order.items() if power))
            for order in reference["squared_orders"]
        )
    )
    results = {}
    for lane in ("recurrence", "compiled", "on-the-fly"):
        runtime = _runtime(
            np_model,
            _NP_PROCESS,
            tmp_path / lane,
            limits=_NP_LIMITS,
            execution_mode=lane,
        )
        result = runtime.evaluate_orders(points)
        assert result.orders == expected_orders, lane
        assert len(result.amplitude_orders) == 2, lane
        _assert_partials_keep_the_total(runtime, result, points)
        _assert_matches_madgraph(result, reference)
        helicity = next(
            h.id
            for h in runtime.physics.helicities
            if complex(runtime.evaluate(points, helicities=[h.id])[0]) != 0
        )
        selected = runtime.evaluate_orders(points, helicities=[helicity])
        _assert_partials_keep_the_total(
            runtime, selected, points, helicities=[helicity]
        )
        results[lane] = (result, selected)
    for lane in ("compiled", "on-the-fly"):
        for actual, expected in zip(results[lane], results["recurrence"], strict=True):
            _assert_same_partials(actual, expected, 1e-12)


# ---------------------------------------------------------------------------
# Every layout and option of the two lanes: the partials are the total's own
# decomposition (default and one selected helicity), on a process with
# several Born orders and on one with a single order; a layout that cannot be
# served refuses evaluate_orders with a typed error.
_LAYOUTS = (
    pytest.param("compiled", {"accuracy": "lc"}, {}, id="compiled-lc-topology-replay"),
    pytest.param(
        "compiled",
        {"accuracy": "lc", "lc_flow_layout": "all-flow-union"},
        {},
        id="compiled-lc-all-flow-union",
    ),
    pytest.param("compiled", {"accuracy": "nlc"}, {}, id="compiled-nlc"),
    pytest.param("compiled", {"accuracy": "full"}, {}, id="compiled-full"),
    pytest.param(
        "compiled", {"accuracy": "full", "graded": True}, {}, id="compiled-full-graded"
    ),
    pytest.param("compiled", {"accuracy": "strict-lc"}, {}, id="compiled-strict-lc"),
    pytest.param("compiled", {"accuracy": "strict-nlc"}, {}, id="compiled-strict-nlc"),
    pytest.param(
        "compiled", {"accuracy": "lc"}, {"backend": "asm"}, id="compiled-lc-asm"
    ),
    pytest.param(
        "compiled",
        {"accuracy": "full"},
        {"relation_discovery": "certified-reuse"},
        id="compiled-full-certified-reuse",
    ),
    pytest.param(
        "compiled",
        {"accuracy": "lc"},
        {"jit_optimization_level": 1},
        id="compiled-lc-jit-o1",
    ),
    pytest.param(
        "compiled",
        {"accuracy": "full"},
        {"backend": "cpp"},
        id="compiled-full-cpp",
        marks=pytest.mark.skipif(
            __import__("shutil").which("c++") is None, reason="no C++ compiler"
        ),
    ),
    pytest.param(
        "compiled",
        {"accuracy": "lc"},
        {"process": {"selected_color_sector_ids": (1,)}},
        id="compiled-lc-fixed-colour-sector",
    ),
    pytest.param(
        "compiled",
        {"accuracy": "full"},
        {"process": {"selected_source_helicities": {"1": 1, "5": -1}}},
        id="compiled-full-fixed-source-helicities",
    ),
    pytest.param("on-the-fly", {"accuracy": "lc"}, {}, id="on-the-fly-lc"),
    pytest.param("on-the-fly", {"accuracy": "nlc"}, {}, id="on-the-fly-nlc"),
    pytest.param("on-the-fly", {"accuracy": "full"}, {}, id="on-the-fly-full-auto"),
    pytest.param(
        "on-the-fly",
        {"accuracy": "full", "contraction": "direct"},
        {},
        id="on-the-fly-full-direct",
    ),
    pytest.param(
        "on-the-fly",
        {"accuracy": "full", "fft_basis": "trace"},
        {},
        id="on-the-fly-full-fft-trace",
    ),
)
_LAYOUT_PROCESSES = (
    pytest.param("u u~ > d d~ g", {"QCD": 3, "QED": 2}, id="several-orders"),
    pytest.param("u u~ > d d~ g", {"QCD": 3, "QED": 0}, id="one-order"),
)


def _layout_runtime(
    model: ModelSource,
    process: str,
    artifact: Path,
    lane: str,
    color: dict[str, object],
    options: dict[str, object],
    limits: dict[str, int],
) -> Runtime:
    from pyamplicol.config import JITConfig

    config = RunConfig(
        action="generate",
        model=ModelConfig(cache=False),
        color=ColorConfig(**color),
        process=ProcessConfig(
            coupling_order_policy="explicit",
            max_coupling_orders=limits,
            **dict(options.get("process", {})),  # type: ignore[arg-type]
        ),
        generation=GenerationConfig(
            workers=1,
            emit_api_bundle=False,
            relation_discovery=GenerationRelationDiscoveryConfig(
                mode=str(options.get("relation_discovery", "off"))
            ),
            validation=GenerationValidationConfig(
                enabled=False, samples=1, seed=7, post_build_validation=False
            ),
        ),
        evaluator=EvaluatorConfig(
            execution_mode=lane,
            backend=str(options.get("backend", "jit")),
            optimization=EvaluatorOptimizationConfig(cores=1),
            jit=JITConfig(
                optimization_level=int(options.get("jit_optimization_level", 2))
            ),
        ),
    )
    Generator(config).generate(process, artifact, model=model)
    return Runtime.load(artifact)


@pytest.mark.parametrize(("process", "limits"), _LAYOUT_PROCESSES)
@pytest.mark.parametrize(("lane", "color", "options"), _LAYOUTS)
def test_every_layout_decomposes_its_own_total(
    sm_model: ModelSource,
    tmp_path: Path,
    lane: str,
    color: dict[str, object],
    options: dict[str, object],
    process: str,
    limits: dict[str, int],
) -> None:
    runtime = _layout_runtime(
        sm_model, process, tmp_path / "artifact", lane, color, options, limits
    )
    points = _reference("u u~ > d d~ g")["points"]
    result = runtime.evaluate_orders(points)
    assert len(result.amplitude_orders) == (2 if limits["QED"] else 1)
    _assert_partials_keep_the_total(runtime, result, points)
    if len(result.amplitude_orders) == 1:
        assert result.values == tuple((total,) for total in result.total)
    helicity = next(
        h.id
        for h in runtime.physics.helicities
        if complex(runtime.evaluate(points[:1], helicities=[h.id])[0]) != 0
    )
    selected = runtime.evaluate_orders(points, helicities=[helicity])
    _assert_partials_keep_the_total(runtime, selected, points, helicities=[helicity])


def test_the_compiled_fft_diagnostic_refuses_partials_typed(
    sm_model: ModelSource, tmp_path: Path
) -> None:
    """The compiled symmetric-group FFT diagnostic contraction has no
    order-resolved reduction: the configuration refuses it for the compiled
    lane; were it built, evaluate_orders would refuse it typed."""

    from pyamplicol.api.errors import GenerationError
    from pyamplicol.config.errors import ConfigurationError

    try:
        runtime = _layout_runtime(
            sm_model,
            "u u~ > d d~ g g",
            tmp_path / "artifact",
            "compiled",
            {"accuracy": "full", "contraction": "symmetric-group-fft"},
            {},
            {"QCD": 4, "QED": 2},
        )
    except (ConfigurationError, GenerationError, CompatibilityError):
        return
    points = [runtime._backend.validation_momenta()[0]]
    with pytest.raises(CompatibilityError):
        runtime.evaluate_orders(points)


@pytest.mark.parametrize("gluons", [1, 2])
def test_compiled_all_flow_union_partials_run_every_helicity_schedule(
    tmp_path: Path, gluons: int
) -> None:
    """Built-in SM u u~ > d d~ g (g) at QCD <= 4, QED <= 2 in the compiled
    leading-colour all-flow-union layout: its plain amplitude stage holds only
    the representative helicities, so the partials run every helicity's
    schedule; they sum to the total, per helicity too, and equal the
    recurrence lane's."""

    process = "u u~ > d d~" + " g" * gluons
    final = (
        [
            [500.0, 400.0, 300.0, 0.0],
            [500.0, 400.0, -300.0, 0.0],
            [800.0, -800.0, 0.0, 0.0],
        ]
        if gluons == 1
        else [
            [450.0, 360.0, 270.0, 0.0],
            [450.0, 360.0, -270.0, 0.0],
            [450.0, -360.0, 0.0, 270.0],
            [450.0, -360.0, 0.0, -270.0],
        ]
    )
    points = [[[900.0, 0.0, 0.0, 900.0], [900.0, 0.0, 0.0, -900.0], *final]]
    limits = {"QCD": 4, "QED": 2}
    runtime = _runtime(
        None,
        process,
        tmp_path / "union",
        accuracy="lc",
        limits=limits,
        lc_flow_layout="all-flow-union",
    )
    recurrence = _runtime(
        None,
        process,
        tmp_path / "recurrence",
        accuracy="lc",
        limits=limits,
        execution_mode="recurrence",
    )
    result = runtime.evaluate_orders(points)
    _assert_partials_keep_the_total(runtime, result, points)
    _assert_same_partials(result, recurrence.evaluate_orders(points), 1e-12)
    for helicity in ("h:-1,+1,-1,+1" + ",-1" * gluons,):
        selected = runtime.evaluate_orders(points, helicities=[helicity])
        _assert_partials_keep_the_total(
            runtime, selected, points, helicities=[helicity]
        )
        _assert_same_partials(
            selected, recurrence.evaluate_orders(points, helicities=[helicity]), 1e-12
        )

    # Above binary64 the exact executor runs every helicity's schedule too:
    # its partials are the exact total's decomposition and equal the
    # recurrence lane's exact partials.
    for selectors in ({}, {"helicities": ["h:-1,+1,-1,+1" + ",-1" * gluons]}):
        exact = runtime.evaluate_orders(points, precision=32, **selectors)
        reference = recurrence.evaluate_orders(points, precision=32, **selectors)
        assert exact.total == runtime.evaluate(points, precision=32, **selectors)
        assert exact.orders == reference.orders
        scale = sum(abs(value) for value in reference.values[0])
        assert abs(sum(exact.values[0]) - exact.total[0]) <= Decimal("1e-25") * scale
        # The two lanes' exact totals of this built-in several-order process
        # already differ at 1e-17 (the same at 32 and 50 digits: an input of
        # the electroweak weighting held in binary64), so the lanes are
        # compared at 1e-15; the split itself is exact (the sum above).
        for value, expected in zip(exact.values[0], reference.values[0], strict=True):
            assert abs(value - expected) <= Decimal("1e-15") * scale


@pytest.mark.parametrize(
    "fixed",
    [
        {"selected_color_sector_ids": (1,)},
        {"selected_source_helicities": {"1": 1, "5": -1}},
    ],
)
def test_on_the_fly_refuses_generation_fixed_coverage(
    sm_model: ModelSource, tmp_path: Path, fixed: dict[str, object]
) -> None:
    """On-the-fly keeps every selection at run time: generation-fixed colour
    sectors or source helicities are refused when the artifact is built, so
    no on-the-fly artifact of that kind exists to split."""

    from pyamplicol.api.errors import GenerationError

    with pytest.raises(GenerationError, match="complete runtime selector coverage"):
        _layout_runtime(
            sm_model,
            "u u~ > d d~ g",
            tmp_path / "artifact",
            "on-the-fly",
            {"accuracy": "lc" if "selected_color_sector_ids" in fixed else "full"},
            {"process": fixed},
            {"QCD": 3, "QED": 2},
        )
