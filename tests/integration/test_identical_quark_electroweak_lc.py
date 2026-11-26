# SPDX-License-Identifier: 0BSD
"""Identical-flavour four-quark processes with photon and Z exchange only, LC.

At ``QCD=0`` the two leading-colour flows of ``b b > b b`` each carry one
pairing of the identical quark lines (a colour-singlet exchange keeps the
colour on its quark line), so the helicities of one flow are the permuted
helicities of the other. A topology replay that reuses one flow for the other
would take the helicity support of the materialized flow for the whole
process; every lane materializes both flows instead. Each lane builds these
processes, equals the on-the-fly lane resolved by helicity and colour flow,
selects helicities and flows at run time, and equals MadGraph 3.7.0 (leading
colour: the diagonal of its colour matrix), on the built-in SM and on the UFO
``sm`` (massive b).

References: MadGraph 3.7.0 standalone, t-channel widths kept,
``tools/developer/madgraph_split_orders.py --colour lc`` at RAMBO points
(sqrt(s) = 1000 GeV, seeds 9001 and 9002), for all ten identical-flavour
processes: UFO ``sm-no_masses`` (the built-in SM's parameters) and UFO
``sm`` with its default restriction.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from pyamplicol import Generator, ModelSource, Runtime
from pyamplicol.config import (
    ColorConfig,
    EvaluatorConfig,
    GenerationConfig,
    GenerationRelationDiscoveryConfig,
    GenerationValidationConfig,
    ModelConfig,
    RunConfig,
)

LANES = ("recurrence", "compiled", "eager", "on-the-fly")
_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "tree"
    / "madgraph-identical-quark-electroweak-lc.json"
)


def _generator(lane: str) -> Generator:
    return Generator(
        RunConfig(
            action="generate",
            model=ModelConfig(cache=False),
            color=ColorConfig(accuracy="lc"),
            evaluator=EvaluatorConfig(execution_mode=lane),
            generation=GenerationConfig(
                workers=1,
                emit_api_bundle=False,
                relation_discovery=GenerationRelationDiscoveryConfig(mode="off"),
                validation=GenerationValidationConfig(
                    enabled=False, samples=1, seed=7, post_build_validation=False
                ),
            ),
        )
    )


def _reference(model: str, process: str) -> dict:
    references = json.loads(_FIXTURE.read_text())["references"][model]
    return next(
        entry for entry in references["processes"] if entry["process"] == process
    )


def _resolved(runtime: Runtime, points: list) -> dict:
    resolved = runtime.evaluate_resolved(points)
    return {
        (helicity, flow): [
            complex(resolved.values[point][h][f]).real for point in range(len(points))
        ]
        for h, helicity in enumerate(resolved.helicity_ids)
        for f, flow in enumerate(resolved.color_ids)
    }


def _check_lanes(model: ModelSource, process: str, reference: dict, root: Path) -> None:
    points = reference["points"]
    by_lane = {}
    for lane in LANES:
        output = root / lane
        _generator(lane).generate([process], output, model=model)
        runtime = Runtime.load(output)
        totals = [complex(value).real for value in runtime.evaluate(points)]
        for value, expected in zip(totals, reference["total"], strict=True):
            assert value == pytest.approx(expected, rel=1e-12), lane
        resolved = _resolved(runtime, points)
        # Run-time selection of one helicity or one colour flow.
        for axis, keyword in ((0, "helicities"), (1, "color_flows")):
            for selector in {key[axis] for key in resolved}:
                selected = runtime.evaluate(points, **{keyword: [selector]})
                for point, value in enumerate(selected):
                    expected = math.fsum(
                        values[point]
                        for key, values in resolved.items()
                        if key[axis] == selector
                    )
                    assert complex(value).real == pytest.approx(
                        expected, rel=1e-12, abs=1e-14 * abs(totals[point])
                    ), (lane, selector)
        by_lane[lane] = resolved
    reference_lane = by_lane["on-the-fly"]
    scale = max(abs(value) for values in reference_lane.values() for value in values)
    expected_nonzero = {key for key, values in reference_lane.items() if any(values)}
    for lane, resolved in by_lane.items():
        nonzero = {key for key, values in resolved.items() if any(values)}
        assert nonzero == expected_nonzero, lane
        for key in nonzero:
            for value, expected in zip(resolved[key], reference_lane[key], strict=True):
                assert abs(value - expected) <= 1e-13 * scale, (lane, key)
    # Each flow carries one pairing of the quark lines: both flows together
    # give the six helicities of the two pairings.
    assert len({helicity for helicity, _flow in expected_nonzero}) == 6


@pytest.mark.parametrize("process", ("b b > b b QCD=0", "b~ b~ > b~ b~ QCD=0"))
def test_built_in_sm(process: str, tmp_path: Path) -> None:
    _check_lanes(
        ModelSource.built_in_sm(),
        process,
        _reference("sm-no_masses", process),
        tmp_path,
    )


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


@pytest.mark.parametrize("process", ("b~ b~ > b~ b~ QCD=0", "u u > u u QCD=0"))
def test_ufo_sm(process: str, sm_model: ModelSource, tmp_path: Path) -> None:
    _check_lanes(sm_model, process, _reference("sm", process), tmp_path)
