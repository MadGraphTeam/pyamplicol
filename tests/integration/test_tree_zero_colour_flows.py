# SPDX-License-Identifier: 0BSD
"""Pure electroweak four-quark amplitudes: zero colour flows.

Two quark lines that only a W joins (``c d > u s``; ``u d~ > b~ t`` with the
massive b of the UFO ``sm`` default restriction) have diagrams in one
quark-antiquark pairing only. The colour flow of the other pairing is
identically zero. The tree lanes take such an open-line colour flow as zero:
- the recurrence certifies it (the structural-zero physical-sector certificate
  of topology-replay, all-flow and contracted plans) and keeps one destination
  without closure terms for it where a public flow or replay target needs one;
- the compiled lane's LC replay skips its rootless sector.

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


@pytest.mark.parametrize(
    ("process", "execution_mode"),
    [
        ("c d > u s", "compiled"),
        ("u d~ > b~ t", "compiled"),
        ("c d > u s", "on-the-fly"),
    ],
)
def test_other_lanes_take_the_zero_flow_at_leading_colour(
    sm_model: ModelSource, tmp_path: Path, process: str, execution_mode: str
) -> None:
    """The compiled lane refused its rootless LC sector ("LC topology replay
    materialized sector N has no amplitude root"); the on-the-fly lane built
    it already."""

    _check(sm_model, tmp_path, process, "lc", execution_mode)


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


def test_full_colour_helicity_selection_skips_the_zero_flow(
    sm_model: ModelSource, tmp_path: Path
) -> None:
    """Full colour keeps a helicity-selector companion. Its zero flow has a
    destination without closure terms and no local colour group of the
    primary plan; selected helicities reproduce the resolved rows and their
    sum the total."""

    entry = _references(REFERENCE)["u d~ > b~ t"]
    runtime = _runtime(sm_model, "u d~ > b~ t", tmp_path / "artifact", accuracy="full")
    helicities = list(runtime.physics.helicity_ids)
    resolved = runtime.evaluate_resolved(entry["points"])
    selected = runtime.evaluate_resolved(entry["points"], helicities=helicities)
    totals = runtime.evaluate(entry["points"])
    assert selected.helicity_ids == resolved.helicity_ids
    for point in range(len(entry["points"])):
        rows = [complex(row[0]).real for row in resolved.values[point]]
        assert [
            complex(row[0]).real for row in selected.values[point]
        ] == pytest.approx(rows, rel=1e-14, abs=0.0)
        assert math.fsum(rows) == pytest.approx(complex(totals[point]).real, rel=1e-14)
        assert complex(totals[point]).real == pytest.approx(
            entry["total"][point], rel=1e-10
        )


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
