# SPDX-License-Identifier: 0BSD
"""A tree-level request without a diagram is refused with its true reason.

A request with no tree-level diagram at any coupling order raises the typed
``NoTreeDiagramError`` (a ``GenerationError``): it names the process, says
that no tree-level diagram exists and why when a conservation law forbids
the process, and otherwise that it may be loop-induced. A request that has
diagrams but whose settings remove them all (``process.max_quark_lines``,
``process.max_coupling_orders``, the expansion orders of the minimal
coupling-order policy) raises ``RequestFilterError`` instead: it names the
setting, keeps the selection's own words and never suggests a loop. Both
are raised after process expansion, before any execution lane is built, so
they read the same in every lane and for the built-in SM and a UFO model. A
request with diagrams is never refused. Which requests have diagrams:
MadGraph 3.7.0 ``generate`` on UFO ``sm``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyamplicol import (
    Generator,
    ModelSource,
    NoTreeDiagramError,
    RequestFilterError,
    Runtime,
)
from pyamplicol.api.errors import GenerationError
from pyamplicol.config import (
    ColorConfig,
    EvaluatorConfig,
    GenerationConfig,
    GenerationRelationDiscoveryConfig,
    GenerationValidationConfig,
    ModelConfig,
    ProcessConfig,
    RunConfig,
)

LANES = ("recurrence", "compiled", "eager", "on-the-fly")
LOOP = "loop-induced"


def _generator(
    lane: str, accuracy: str = "lc", process: ProcessConfig | None = None
) -> Generator:
    return Generator(
        RunConfig(
            action="generate",
            model=ModelConfig(cache=False),
            color=ColorConfig(accuracy=accuracy),
            process=process or ProcessConfig(),
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
    model: ModelSource,
    request: str,
    lane: str,
    tmp_path: Path,
    accuracy: str = "lc",
    *,
    error: type[GenerationError] = NoTreeDiagramError,
    process: ProcessConfig | None = None,
) -> GenerationError:
    output = tmp_path / f"{lane}-{accuracy}"
    with pytest.raises(error) as caught:
        _generator(lane, accuracy, process).generate([request], output, model=model)
    assert isinstance(caught.value, GenerationError)
    assert not output.exists()
    return caught.value


ANY = "has no tree-level Feynman diagram at any coupling order"
# (request, process, reason in the message or None, loop hint)
BUILT_IN = (
    ("a a > a a", "a a > a a", None, True),
    ("a a > g g", "a a > g g", None, True),
    ("u u~ > e+ e+", "u u~ > e+ e+", "violates electric-charge conservation", False),
    ("g e- > a e-", "g e- > a e-", "single coloured particle", False),
)


@pytest.mark.parametrize("case", BUILT_IN, ids=lambda case: case[0])
@pytest.mark.parametrize("lane", LANES)
def test_built_in_sm_refuses_in_every_lane(
    case: tuple[str, str, str | None, bool], lane: str, tmp_path: Path
) -> None:
    request, process, reason, loop_hint = case
    error = _refusal(ModelSource.built_in_sm(), request, lane, tmp_path)
    assert isinstance(error, NoTreeDiagramError)
    assert error.key == "no-tree-diagram"
    message = str(error)
    assert message.startswith("no tree-level diagram: process ")
    assert repr(process) in message
    assert ANY in message
    assert reason is None or reason in message
    assert (LOOP in message) is loop_hint
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


# The reviewer's case: the quark-line cut, not the model, empties the request.
QUARK_LINES = (
    "request filter: no valid processes found for 'u d > u d': "
    "process.max_quark_lines = 1 removes every concrete process of the request "
    "(they have 2 quark lines)"
)


@pytest.mark.parametrize("lane", LANES)
def test_the_quark_line_cut_is_named_not_a_missing_diagram(
    lane: str, tmp_path: Path
) -> None:
    cut = ProcessConfig(max_quark_lines=1)
    error = _refusal(
        ModelSource.built_in_sm(),
        "u d > u d",
        lane,
        tmp_path,
        error=RequestFilterError,
        process=cut,
    )
    assert isinstance(error, RequestFilterError)
    assert error.key == "request-filter"
    message = str(error)
    assert message.startswith(QUARK_LINES)
    assert "relaxing process.max_quark_lines serves it" in message
    assert LOOP not in message
    assert "no tree-level" not in message
    assert error.processes == ("u d > u d",)
    assert error.settings == ("process.max_quark_lines",)
    with pytest.raises(RequestFilterError, match=r"process\.max_quark_lines = 1"):
        _generator(lane, process=cut).plan(
            ["u d > u d"], model=ModelSource.built_in_sm()
        )
    # Without the cut the request is served.
    _generator(lane).generate(
        ["u d > u d"], tmp_path / "uncut", model=ModelSource.built_in_sm()
    )


# An explicit coupling-order limit that removes every diagram.
LIMITS = (
    ("b g > b g QCD=0", "b g > b g", "QCD<=0"),
    ("a a > b~ b QED=1", "a a > b~ b", "QED<=1"),
)


@pytest.mark.parametrize("case", LIMITS, ids=lambda case: case[0])
@pytest.mark.parametrize("lane", LANES)
def test_a_coupling_order_limit_is_named_not_a_missing_diagram(
    case: tuple[str, str, str], lane: str, tmp_path: Path
) -> None:
    request, process, limit = case
    error = _refusal(
        ModelSource.built_in_sm(), request, lane, tmp_path, error=RequestFilterError
    )
    assert isinstance(error, RequestFilterError)
    message = str(error)
    assert message.startswith(
        f"request filter: process {process!r} has tree-level diagrams, but none "
        f"within process.max_coupling_orders ({limit})"
    )
    assert LOOP not in message
    assert error.settings == ("process.max_coupling_orders",)


def test_one_call_with_a_filtered_and_a_missing_request(tmp_path: Path) -> None:
    with pytest.raises(RequestFilterError) as caught:
        _generator("recurrence", process=ProcessConfig(max_quark_lines=1)).generate(
            ["u d > u d", "a a > a a"],
            tmp_path / "mixed",
            model=ModelSource.built_in_sm(),
        )
    message = str(caught.value)
    assert message.startswith(QUARK_LINES)
    assert "no tree-level diagram: process 'a a > a a' " + ANY in message
    assert caught.value.processes == ("u d > u d",)


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


# The internal messages of the recurrence lane that these refusals replace on
# the UFO sm, and a charge-violating request.
# (request, error, message start, loop hint)
UFO = (
    ("a a > a a", NoTreeDiagramError, "no tree-level diagram: process 'a a > a a' "),
    ("a a > z h", NoTreeDiagramError, "no tree-level diagram: process 'a a > z h' "),
    (
        "b e- > d ta-",
        NoTreeDiagramError,
        "no tree-level diagram: process 'b e- > d ta-' (no concrete process "
        "conserves the additive charges",
    ),
    (
        "a a > b~ b QED=1",
        RequestFilterError,
        "request filter: process 'a a > b~ b' has tree-level diagrams, but none "
        "within process.max_coupling_orders (QED<=1)",
    ),
    (
        "b g > b g QCD=0",
        RequestFilterError,
        "request filter: process 'b g > b g' has tree-level diagrams, but none "
        "within process.max_coupling_orders (QCD<=0)",
    ),
)
_UFO_LOOP_HINT = {"a a > a a", "a a > z h"}


@pytest.mark.parametrize("case", UFO, ids=lambda case: case[0])
@pytest.mark.parametrize("lane", LANES)
def test_ufo_sm_refuses_in_every_lane(
    case: tuple[str, type[GenerationError], str],
    lane: str,
    sm_model: ModelSource,
    tmp_path: Path,
) -> None:
    request, error_type, start = case
    error = _refusal(sm_model, request, lane, tmp_path, error=error_type)
    message = str(error)
    assert message.startswith(start)
    assert (LOOP in message) is (request in _UFO_LOOP_HINT)


def test_ufo_compiled_lane_names_the_quark_line_cut(
    sm_model: ModelSource, tmp_path: Path
) -> None:
    # On a UFO model the cut acts in the DAG of the compiled lane.
    with pytest.raises(GenerationError) as caught:
        _generator("compiled", process=ProcessConfig(max_quark_lines=1)).generate(
            ["u d > u d"], tmp_path / "cut", model=sm_model
        )
    message = str(caught.value)
    assert "process.max_quark_lines = 1 removes it (it has 2 quark lines)" in message
    assert LOOP not in message
