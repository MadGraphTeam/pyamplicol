# SPDX-License-Identifier: 0BSD
"""A tree-level request without any diagram is refused with one message.

The refusal is typed (``NoTreeDiagramError``, a ``GenerationError``), names
the process and the requested coupling orders, says that no tree-level
diagram exists there and, unless a conserved charge forbids the process,
that it may be loop-induced. It is raised after process expansion, before any
execution lane is built, so it reads the same in every lane and for the
built-in SM and a UFO model. A request with diagrams is never refused.
Which requests have diagrams: MadGraph 3.7.0 ``generate`` on UFO ``sm``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyamplicol import Generator, ModelSource, NoTreeDiagramError, Runtime
from pyamplicol.api.errors import GenerationError
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


def _generator(lane: str, accuracy: str = "lc") -> Generator:
    return Generator(
        RunConfig(
            action="generate",
            model=ModelConfig(cache=False),
            color=ColorConfig(accuracy=accuracy),
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


def _refusal(
    model: ModelSource, request: str, lane: str, tmp_path: Path, accuracy: str = "lc"
) -> NoTreeDiagramError:
    output = tmp_path / f"{lane}-{accuracy}"
    with pytest.raises(NoTreeDiagramError) as caught:
        _generator(lane, accuracy).generate([request], output, model=model)
    assert isinstance(caught.value, GenerationError)
    assert caught.value.key == "no-tree-diagram"
    assert not output.exists()
    return caught.value


ANY = "at any coupling order"
QCD0 = "at the requested coupling orders (QCD<=0)"
QED1 = "at the requested coupling orders (QED<=1)"
# (request, process, coupling-order text, loop hint)
BUILT_IN = (
    ("a a > a a", "a a > a a", ANY, True),
    ("b g > b g QCD=0", "b g > b g", QCD0, True),
    ("a a > b~ b QED=1", "a a > b~ b", QED1, True),
    ("a a > g g", "a a > g g", ANY, True),
)


@pytest.mark.parametrize("case", BUILT_IN, ids=lambda case: case[0])
@pytest.mark.parametrize("lane", LANES)
def test_built_in_sm_refuses_in_every_lane(
    case: tuple[str, str, str, bool], lane: str, tmp_path: Path
) -> None:
    request, process, orders, loop_hint = case
    error = _refusal(ModelSource.built_in_sm(), request, lane, tmp_path)
    message = str(error)
    assert message.startswith("no tree-level diagram: process ")
    assert repr(process) in message
    assert f"has no tree-level Feynman diagram {orders}" in message
    assert ("loop-induced" in message) is loop_hint
    assert error.processes == (process,)


def test_the_message_is_the_same_in_every_lane_and_colour(tmp_path: Path) -> None:
    messages = {
        str(_refusal(ModelSource.built_in_sm(), "a a > z h", lane, tmp_path, accuracy))
        for lane in LANES
        for accuracy in ("lc", "full")
    }
    assert len(messages) == 1


def test_requests_with_diagrams_are_served(tmp_path: Path) -> None:
    output = tmp_path / "served"
    _generator("recurrence").generate(
        ["a a > b~ b QED=2"], output, model=ModelSource.built_in_sm()
    )
    assert Runtime.load(output) is not None


def test_one_call_names_only_the_requests_without_a_diagram(tmp_path: Path) -> None:
    with pytest.raises(NoTreeDiagramError) as caught:
        _generator("recurrence").generate(
            ["e+ e- > mu+ mu-", "a a > a a", "g g > a a"],
            tmp_path / "batch",
            model=ModelSource.built_in_sm(),
        )
    assert caught.value.processes == ("a a > a a", "g g > a a")
    assert str(caught.value).startswith(
        "no tree-level diagram: processes 'a a > a a', 'g g > a a'"
    )


def test_plan_refuses_the_same(tmp_path: Path) -> None:
    with pytest.raises(NoTreeDiagramError, match="'a a > a a'"):
        _generator("compiled").plan(["a a > a a"], model=ModelSource.built_in_sm())


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


# The four internal messages of the recurrence lane that this refusal
# replaces on the UFO sm, and a charge-violating request.
UFO = (
    ("a a > b~ b QED=1", QED1, True),
    ("a a > a a", ANY, True),
    ("a a > z h", ANY, True),
    ("b g > b g QCD=0", QCD0, True),
    ("b e- > d ta-", ANY, False),
)


@pytest.mark.parametrize("case", UFO, ids=lambda case: case[0])
@pytest.mark.parametrize("lane", LANES)
def test_ufo_sm_refuses_in_every_lane(
    case: tuple[str, str, bool],
    lane: str,
    sm_model: ModelSource,
    tmp_path: Path,
) -> None:
    request, orders, loop_hint = case
    error = _refusal(sm_model, request, lane, tmp_path)
    message = str(error)
    assert f"has no tree-level Feynman diagram {orders}" in message
    assert ("loop-induced" in message) is loop_hint
