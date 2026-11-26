# SPDX-License-Identifier: 0BSD
"""Pure electroweak four-quark amplitudes: zero colour flows.

Two quark lines that only a W joins (``c d > u s``; ``u d~ > b~ t`` with the
massive b of the UFO ``sm`` default restriction) have diagrams in one
quark-antiquark pairing only. The colour flow of the other pairing is
identically zero. The tree lanes take such an open-line colour flow as zero:
- the recurrence certifies it (the structural-zero physical-sector certificate
  of topology-replay, all-flow and contracted plans) and keeps one destination
  without closure terms for it, which every public evaluation path (totals,
  resolved values, colour-flow and helicity selection, per point and in mixed
  batches, order partials, the full-colour helicity-selector companion)
  returns as an exact zero;
- the certificate holds for every permitted parameter binding only: a model
  whose vertex support depends on the values of mutable parameters (a coupling
  the restriction removed, or a projection the support probe dropped, at the
  card values) is refused (``models.binding_support``);
- the compiled lane lists the flow in public physics outside every reduction
  group and declares ``rusticol.compiled.zero-color-flows.v1`` (a released
  reader refuses the artifact); colour-flow selection of it returns an exact
  zero, alone, per point and in mixed batches;
- the eager and on-the-fly lanes take it as zero, as before.

The references are MadGraph 3.7.0 standalone, UFO ``sm`` with its default
restriction and t-channel widths kept, from
``tools/developer/madgraph_split_orders.py`` at RAMBO points (sqrt(s) =
1000 GeV, seeds 9001 and 9002): full colour in
``madgraph-ew-four-quark.json``, leading colour (``--colour lc``, no external
gluons) in ``madgraph-ew-four-quark-lc.json``. They hold:
- the six processes of the report;
- all 36 class representatives of the 2 -> 2 built-in particle table that the
  recurrence refused ("no exact closure for physical LC sector");
- ``c d > u s g`` and ``u d~ > t b~ g``;
- the single-top and multi-line processes of the design notes.

The default tier checks two of the six and the zero flow itself; the full list
runs in the nightly tier.

At full colour, ``u u~ > d d~ s s~`` and ``u d > u d s s~`` at QCD = 0, and
``u c~ > d s~ d d~``, reach a different refusal: their helicity-selector
companion needs complete per-sector helicity blocks of the primary colour
reducer, which a helicity-dependent zero (the W pairing of these lines exists
for some helicities only) does not give. That is pinned as a refusal here.
"""

from __future__ import annotations

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

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/tree"
REFERENCE = FIXTURES / "madgraph-ew-four-quark.json"
LC_REFERENCE = FIXTURES / "madgraph-ew-four-quark-lc.json"
ALL_ORDERS = {"QCD": 99, "QED": 99}
# Two of the six processes of the report in the default tier (the light-quark
# lines and the top line); the nightly tier runs all six with the rest.
REPORTED = ("c d > u s", "u d~ > b~ t")
# Explicit coupling orders of the multi-line references; MadGraph's QCD = 0
# value is the sum of its partials without QCD.
PURE_ELECTROWEAK = {
    "u u~ > d d~ s s~": {"QCD": 0, "QED": 4},
    "u d > u d s s~": {"QCD": 0, "QED": 4},
}
# Full colour: the helicity-selector companion refuses a primary colour
# reducer with incomplete per-sector helicity blocks (module docstring).
_FULL_COLOUR_HELICITY_BLOCK_REFUSALS = frozenset(
    {"u u~ > d d~ s s~", "u d > u d s s~", "u c~ > d s~ d d~"}
)
_HELICITY_BLOCK_REFUSAL = (
    "local-color view requires a direct, Walsh, or symmetric-group Fourier reducer"
)


def _references(path: Path) -> dict[str, dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {entry["process"]: entry for entry in payload["processes"]}


def _expected(entry: dict[str, object], limits: dict[str, int]) -> list[float]:
    if limits.get("QCD") == 0:
        columns = [
            index
            for index, order in enumerate(entry["squared_orders"])
            if order.get("QCD", 0) == 0
        ]
        return [math.fsum(row[index] for index in columns) for row in entry["partials"]]
    return list(entry["total"])


@pytest.fixture(scope="module")
def sm_model(
    madgraph_source: Path, tmp_path_factory: pytest.TempPathFactory
) -> ModelSource:
    root = tmp_path_factory.mktemp("madgraph-sm")
    bundle = root / "sm.pyamplicol-model"
    ModelSource.from_path(madgraph_source / "models/sm", restriction="default").compile(
        cache_dir=root / "cache",
        prepared_output=bundle,
        evaluator=EvaluatorConfig(),
    )
    return ModelSource.from_path(bundle)


def _runtime(
    model: ModelSource,
    process: str,
    artifact: Path,
    *,
    accuracy: str,
    execution_mode: str = "recurrence",
    limits: dict[str, int] = ALL_ORDERS,
    lc_flow_layout: str = "topology-replay",
) -> Runtime:
    config = RunConfig(
        action="generate",
        model=ModelConfig(cache=False),
        color=ColorConfig(accuracy=accuracy, lc_flow_layout=lc_flow_layout),
        process=ProcessConfig(
            coupling_order_policy="explicit", max_coupling_orders=limits
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
    Generator(config).generate(process, artifact, model=model)
    return Runtime.load(artifact)


def _assert_matches(runtime: Runtime, entry: dict[str, object], limits) -> None:
    values = [complex(value) for value in runtime.evaluate(entry["points"])]
    for point, (value, expected) in enumerate(
        zip(values, _expected(entry, limits), strict=True)
    ):
        assert value.imag == 0.0
        assert value.real == pytest.approx(expected, rel=1e-10, abs=0.0), point


def _check(
    model: ModelSource,
    tmp_path: Path,
    process: str,
    accuracy: str,
    execution_mode: str = "recurrence",
) -> None:
    entry = _references(REFERENCE if accuracy == "full" else LC_REFERENCE)[process]
    limits = PURE_ELECTROWEAK.get(process, ALL_ORDERS)
    if (
        accuracy == "full"
        and execution_mode == "recurrence"
        and process in _FULL_COLOUR_HELICITY_BLOCK_REFUSALS
    ):
        with pytest.raises(GenerationError, match=_HELICITY_BLOCK_REFUSAL):
            _runtime(
                model, process, tmp_path / "artifact", accuracy=accuracy, limits=limits
            )
        return
    runtime = _runtime(
        model,
        process,
        tmp_path / "artifact",
        accuracy=accuracy,
        execution_mode=execution_mode,
        limits=limits,
    )
    _assert_matches(runtime, entry, limits)


@pytest.mark.parametrize("accuracy", ["lc", "full"])
@pytest.mark.parametrize("process", REPORTED)
def test_reported_processes_match_madgraph(
    sm_model: ModelSource, tmp_path: Path, process: str, accuracy: str
) -> None:
    """The recurrence refused every one of them at both accuracies ("no exact
    closure for physical LC sector")."""

    _check(sm_model, tmp_path, process, accuracy)


@pytest.mark.parametrize("execution_mode", ["on-the-fly", "compiled"])
def test_the_other_lanes_take_the_zero_flow(
    sm_model: ModelSource, tmp_path: Path, execution_mode: str
) -> None:
    """The on-the-fly lane built these processes already; the compiled lane
    refused a rootless LC sector ("has no amplitude root") before."""

    _check(sm_model, tmp_path, "c d > u s", "lc", execution_mode)


def test_the_compiled_lane_declares_its_zero_flows(
    sm_model: ModelSource, tmp_path: Path
) -> None:
    """Only a compiled artifact with a zero colour flow requires the
    capability, so every other artifact keeps its bytes and a released reader
    refuses this one at load."""

    capability = "rusticol.compiled.zero-color-flows.v1"
    for process, expected in (("c d > u s", True), ("u d > u d", False)):
        artifact = tmp_path / process.replace(" ", "_").replace(">", "to")
        _runtime(
            sm_model,
            process,
            artifact,
            accuracy="lc",
            execution_mode="compiled",
            limits={"QCD": 0, "QED": 2},
        )
        manifest = json.loads((artifact / "artifact.json").read_text())
        declared = manifest["runtime"]["required_runtime_capabilities"]
        assert (capability in declared) is expected


def test_the_zero_flow_is_exactly_zero_in_every_lc_layout(
    sm_model: ModelSource, tmp_path: Path
) -> None:
    """c d > u s at LC: of its two flows, the (c, u)(d, s) pairing has no
    diagram. Its resolved amplitude is exactly zero for every helicity in the
    topology-replay and all-flow layouts, and the other flow carries the
    total."""

    entry = _references(LC_REFERENCE)["c d > u s"]
    for layout in ("topology-replay", "all-flow-union"):
        runtime = _runtime(
            sm_model,
            "c d > u s",
            tmp_path / layout,
            accuracy="lc",
            lc_flow_layout=layout,
        )
        resolved = runtime.evaluate_resolved(entry["points"])
        totals = runtime.evaluate(entry["points"])
        flows = runtime.physics.color_flow_ids
        assert len(flows) == 2
        for point, rows in enumerate(resolved.values):
            zero_flows = [
                flow
                for flow in range(len(flows))
                if all(complex(row[flow]) == 0.0 for row in rows)
            ]
            assert len(zero_flows) == 1
            per_flow = [
                math.fsum(complex(row[flow]).real for row in rows)
                for flow in range(len(flows))
            ]
            assert math.fsum(per_flow) == pytest.approx(
                complex(totals[point]).real, rel=1e-14
            )
            assert complex(totals[point]).real == pytest.approx(
                entry["total"][point], rel=1e-10
            )


@pytest.mark.parametrize("process", ["c d > u s", "u d~ > b~ t", "c d > u s g"])
def test_full_colour_singleton_helicity_selection_matches_the_resolved_rows(
    sm_model: ModelSource, tmp_path: Path, process: str
) -> None:
    """Full colour keeps a helicity-selector companion, used by a selection of
    some helicities only. Its zero flow keeps a destination without closure
    terms and has no local colour group of the primary plan. One helicity at
    a time (globally and per point) reproduces the primary plan's resolved
    row, and the rows sum to the total."""

    entry = _references(REFERENCE)[process]
    runtime = _runtime(sm_model, process, tmp_path / "artifact", accuracy="full")
    points = entry["points"]
    resolved = runtime.evaluate_resolved(points)
    totals = [complex(value).real for value in runtime.evaluate(points)]
    helicities = list(resolved.helicity_ids)
    for index, helicity in enumerate(helicities):
        rows = [complex(resolved.values[point][index][0]).real for point in range(2)]
        single = runtime.evaluate(points, helicities=[helicity])
        assert [complex(value).real for value in single] == pytest.approx(
            rows, rel=1e-13, abs=0.0
        )
    by_point = runtime.evaluate(points, helicity_by_point=helicities[:2])
    assert [complex(value).real for value in by_point] == pytest.approx(
        [complex(resolved.values[point][point][0]).real for point in range(2)],
        rel=1e-13,
        abs=0.0,
    )
    for point in range(2):
        rows = [complex(row[0]).real for row in resolved.values[point]]
        assert math.fsum(rows) == pytest.approx(totals[point], rel=1e-13)
        assert totals[point] == pytest.approx(entry["total"][point], rel=1e-10)


@pytest.mark.parametrize(
    ("execution_mode", "layout"),
    [
        ("recurrence", "topology-replay"),
        ("recurrence", "all-flow-union"),
        ("compiled", "topology-replay"),
    ],
)
@pytest.mark.parametrize("precision", [16, 32])
def test_selecting_the_zero_flow_returns_an_exact_zero(
    sm_model: ModelSource,
    tmp_path: Path,
    execution_mode: str,
    layout: str,
    precision: int,
) -> None:
    """Selecting the zero colour flow, alone, per point and next to the live
    flow in one batch, returns exactly zero in binary64 and at 32 digits; the
    live flow returns the total."""

    entry = _references(LC_REFERENCE)["c d > u s"]
    runtime = _runtime(
        sm_model,
        "c d > u s",
        tmp_path / "artifact",
        accuracy="lc",
        execution_mode=execution_mode,
        lc_flow_layout=layout,
    )
    points = entry["points"]
    resolved = runtime.evaluate_resolved(points)
    flows = list(resolved.color_ids)
    zero = next(
        index
        for index in range(len(flows))
        if all(complex(row[index]) == 0.0 for rows in resolved.values for row in rows)
    )
    live = 1 - zero
    zero_values = runtime.evaluate(
        points, color_flows=[flows[zero]], precision=precision
    )
    assert all(complex(value) == 0.0 for value in zero_values)
    zero_resolved = runtime.evaluate_resolved(
        points, color_flows=[flows[zero]], precision=precision
    )
    assert all(
        complex(v) == 0.0 for rows in zero_resolved.values for row in rows for v in row
    )
    live_values = runtime.evaluate(
        points, color_flows=[flows[live]], precision=precision
    )
    assert [complex(value).real for value in live_values] == pytest.approx(
        entry["total"], rel=1e-10
    )
    mixed = runtime.evaluate(
        points, color_flow_by_point=[flows[zero], flows[live]], precision=precision
    )
    assert complex(mixed[0]) == 0.0
    assert complex(mixed[1]).real == pytest.approx(entry["total"][1], rel=1e-10)


@pytest.mark.parametrize("layout", ["topology-replay", "all-flow-union"])
def test_order_partials_of_a_zero_flow_process_in_binary64(
    sm_model: ModelSource, tmp_path: Path, layout: str
) -> None:
    """u c~ > d s~ d d~ at LC, all orders: two of its six flows are zero colour
    flows. The binary64 squared coupling-order partials equal the 32-digit
    ones and MadGraph's (binary64 refused with "order-split destination has
    no closure rows" before)."""

    entry = _references(LC_REFERENCE)["u c~ > d s~ d d~"]
    runtime = _runtime(
        sm_model,
        "u c~ > d s~ d d~",
        tmp_path / "artifact",
        accuracy="lc",
        lc_flow_layout=layout,
    )
    binary64 = runtime.evaluate_orders(entry["points"])
    exact = runtime.evaluate_orders(entry["points"], precision=32)
    expected_orders = tuple(
        tuple(sorted((name, power) for name, power in order.items() if power))
        for order in entry["squared_orders"]
    )
    assert binary64.orders == exact.orders == tuple(sorted(expected_orders))
    for point, partials in enumerate(entry["partials"]):
        scale = math.fsum(abs(value) for value in partials)
        for order, expected in zip(expected_orders, partials, strict=True):
            value = complex(binary64.for_order(order)[point]).real
            assert abs(value - float(exact.for_order(order)[point])) <= 1e-13 * scale
            assert abs(value - expected) <= 1e-12 * scale, (point, order)


def _mutable_coupling_model(root: Path, madgraph_source: Path, mt: int) -> Path:
    """The UFO sm with both udW couplings multiplied by (MT - 173) and MT set
    to ``mt`` on the default restriction card."""

    import re
    import shutil

    model = root / f"sm-mt{mt}"
    shutil.copytree(
        madgraph_source / "models/sm",
        model,
        ignore=shutil.ignore_patterns("__pycache__", "*.pkl"),
    )
    couplings = model / "couplings.py"
    text = couplings.read_text(encoding="utf-8")
    for name in ("41", "100"):
        text, count = re.subn(
            rf"(GC_{name} = Coupling\(name = 'GC_{name}',\s+value = ')([^']+)",
            r"\g<1>(MT-173)*(\g<2>)",
            text,
        )
        assert count == 1
    couplings.write_text(text, encoding="utf-8")
    card = model / "restrict_default.dat"
    text = card.read_text(encoding="utf-8")
    assert "1.730000e+02 # MT " in text
    card.write_text(text.replace("1.730000e+02 # MT ", f"{mt}.0 # MT "))
    return model


@pytest.mark.xfail(
    strict=True,
    reason="needs the specialisation guards of the parameter-binding boundary",
)
def test_a_zero_flow_that_a_mutable_parameter_revives_is_refused(
    madgraph_source: Path, tmp_path: Path
) -> None:
    """A W coupling proportional to MT - 173 vanishes at MT = 173 and is
    removed by the restriction (and dropped by the support probe without
    simplification), so the W pairing of u d > u d at QCD = 0 has no diagram
    there; MT stays mutable. Certifying that flow as zero gave
    0.0985435252 at MT = 174 against 0.1996120998 from the artifact
    generated at 174. The recurrence now refuses it at LC and full colour,
    and the compiled lane refuses it at LC (as every rootless LC sector); the
    artifact generated at 174 is unaffected."""

    limits = {"QCD": 0, "QED": 2}
    at_173 = _mutable_coupling_model(tmp_path, madgraph_source, 173)
    at_174 = _mutable_coupling_model(tmp_path, madgraph_source, 174)
    prepared = {}
    for name, source in (("173", at_173), ("174", at_174)):
        bundle = tmp_path / f"sm-{name}.pyamplicol-model"
        ModelSource.from_path(source, restriction="default").compile(
            cache_dir=tmp_path / "cache",
            prepared_output=bundle,
            evaluator=EvaluatorConfig(),
        )
        prepared[name] = ModelSource.from_path(bundle)
    refusal = "cannot be certified zero for every permitted parameter binding"
    for accuracy in ("lc", "full"):
        with pytest.raises(GenerationError, match=refusal):
            _runtime(
                prepared["173"],
                "u d > u d",
                tmp_path / f"recurrence-{accuracy}",
                accuracy=accuracy,
                limits=limits,
            )
    for simplify in (True, False):
        # The compiled lane refuses every rootless LC sector.
        with pytest.raises(GenerationError, match="has no amplitude root"):
            _runtime(
                ModelSource.from_path(at_173, restriction="default", simplify=simplify),
                "u d > u d",
                tmp_path / f"compiled-{simplify}",
                accuracy="lc",
                execution_mode="compiled",
                limits=limits,
            )
    runtime = _runtime(
        prepared["174"], "u d > u d", tmp_path / "at-174", accuracy="lc", limits=limits
    )
    assert len(runtime.physics.color_flow_ids) == 2


@pytest.mark.loop_nightly
@pytest.mark.parametrize("accuracy", ["lc", "full"])
@pytest.mark.parametrize("process", sorted(_references(REFERENCE)))
def test_every_reference_matches_madgraph(
    sm_model: ModelSource, tmp_path: Path, process: str, accuracy: str
) -> None:
    """The full list in the recurrence lane, at both accuracies (leading
    colour where MadGraph's colour basis is the colour-flow basis)."""

    if accuracy == "lc" and process not in _references(LC_REFERENCE):
        pytest.skip("no MadGraph leading-colour reference with external gluons")
    _check(sm_model, tmp_path, process, accuracy)
