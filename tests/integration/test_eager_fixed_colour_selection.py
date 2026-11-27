# SPDX-License-Identifier: 0BSD
"""The eager mode refuses a fixed colour-sector selection beyond the leading
sectors of the colour plan.

Its colour tables are indexed by the plan's sector ids, so it lowers a
generation-time selection only when that selection is the leading run
0, ..., k-1 of the plan. Any other fixed selection is a typed refusal raised
before anything is written (the compiled and recurrence modes generate it;
every mode selects it at run time on a complete artifact). The leading
selection is generated as before.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from pyamplicol import Generator, ModelSource, Runtime
from pyamplicol.api.errors import GenerationError
from pyamplicol.config import (
    ColorConfig,
    EvaluatorConfig,
    EvaluatorOptimizationConfig,
    GenerationConfig,
    ModelConfig,
    ProcessConfig,
    RunConfig,
)

_REFUSAL = "eager mode does not generate a fixed colour-sector selection"


def _config(selected: tuple[int, ...]) -> RunConfig:
    return RunConfig(
        action="generate",
        model=ModelConfig(cache=False),
        color=ColorConfig(accuracy="lc"),
        process=ProcessConfig(selected_color_sector_ids=selected),
        generation=GenerationConfig(workers=1, emit_api_bundle=False),
        evaluator=EvaluatorConfig(
            execution_mode="eager",
            optimization=EvaluatorOptimizationConfig(cores=1),
        ),
    )


@pytest.fixture(autouse=True)
def _native() -> None:
    if importlib.util.find_spec("pyamplicol._rusticol") is None:
        pytest.skip("the Rusticol extension has not been built")


@pytest.mark.parametrize("process", ["g g > t t~", "u u~ > d d~ g"])
@pytest.mark.parametrize("selected", [(1,), (0, 2)])
def test_a_selection_beyond_the_leading_sectors_is_refused_before_generation(
    tmp_path: Path, process: str, selected: tuple[int, ...]
) -> None:
    path = tmp_path / "artifact"
    with pytest.raises(GenerationError, match=_REFUSAL):
        Generator(_config(selected)).generate(
            process, path, model=ModelSource.built_in_sm()
        )
    assert not path.exists()
    with pytest.raises(GenerationError, match=_REFUSAL):
        Generator(_config(selected)).plan(process, model=ModelSource.built_in_sm())


def test_the_leading_sector_is_generated_as_before(tmp_path: Path) -> None:
    path = tmp_path / "artifact"
    Generator(_config((0,))).generate(
        "g g > t t~", path, model=ModelSource.built_in_sm()
    )
    assert [flow.id for flow in Runtime.load(path).physics.color_flows] == [
        "flow:3,1,2,4"
    ]
