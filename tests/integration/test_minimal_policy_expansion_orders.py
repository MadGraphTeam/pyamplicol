# SPDX-License-Identifier: 0BSD
"""The minimal coupling-order policy works within the UFO expansion orders.

A user SM UFO tags the down-quark and neutrino Z couplings ``NP:1`` and
declares ``NP`` with ``expansion_order = 1``, so ``d d~ > vm vm~`` needs
``NP^2``: at the default (minimal) policy it has no Born, in the tree, the
correlated and the loop-Born paths alike; a named limit still decides.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
from pathlib import Path

import pytest

from pyamplicol import (
    ColorCorrelator,
    CorrelatorConfig,
    Generator,
    ModelSource,
    Runtime,
)
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
from pyamplicol.generation import loop_service

_SM_UFO = Path(__file__).resolve().parents[2] / "src/pyamplicol/assets/models/ufo/sm"
_POINTS = [[(100, 0, 0, 100), (100, 0, 0, -100), (100, 60, 80, 0), (100, -60, -80, 0)]]


@pytest.fixture(scope="module")
def np_model(tmp_path_factory: pytest.TempPathFactory) -> ModelSource:
    if importlib.util.find_spec("pyamplicol._rusticol") is None:
        pytest.skip("the Rusticol extension has not been built")
    source = tmp_path_factory.mktemp("np-ufo") / "NP"
    shutil.copytree(
        _SM_UFO, source, ignore=shutil.ignore_patterns("*.pkl", "__pycache__")
    )
    with (source / "coupling_orders.py").open("a", encoding="utf-8") as handle:
        handle.write(
            "\nNP = CouplingOrder(name='NP', expansion_order=1, hierarchy=1)\n"
        )
    couplings = source / "couplings.py"
    text, count = re.subn(
        r"(GC_(?:50|58|62) = Coupling\([^)]*?(?:.|\n)*?order = )\{'QED':1\}",
        r"\1{'QED':1,'NP':1}",
        couplings.read_text(encoding="utf-8"),
    )
    assert count == 3
    couplings.write_text(text, encoding="utf-8")
    return ModelSource.from_path(source, restriction="default")


def _config(orders: dict[str, int] | None) -> RunConfig:
    return RunConfig(
        action="generate",
        model=ModelConfig(cache=False),
        color=ColorConfig(accuracy="full"),
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
            execution_mode="compiled",
            optimization=EvaluatorOptimizationConfig(cores=1),
        ),
    )


_DIPOLE = CorrelatorConfig(color_correlations=(ColorCorrelator.dipole("T12", 1, 2),))


@pytest.mark.parametrize("correlated", (False, True))
def test_the_default_policy_stays_within_the_expansion_order(
    np_model: ModelSource, tmp_path: Path, correlated: bool
) -> None:
    extra = {"correlators": _DIPOLE} if correlated else {}
    with pytest.raises(GenerationError, match="no model-supported tree-level"):
        Generator(_config(None)).generate(
            "d d~ > vm vm~", tmp_path / "default", model=np_model, **extra
        )


@pytest.mark.parametrize("correlated", (False, True))
def test_a_named_limit_decides(
    np_model: ModelSource, tmp_path: Path, correlated: bool
) -> None:
    extra = {"correlators": _DIPOLE} if correlated else {}
    with pytest.raises(GenerationError, match="no model-supported tree-level"):
        Generator(_config({"NP": 1})).generate(
            "d d~ > vm vm~", tmp_path / "np1", model=np_model, **extra
        )
    Generator(_config({"NP": 2})).generate(
        "d d~ > vm vm~", tmp_path / "np2", model=np_model, **extra
    )
    value = complex(Runtime.load(tmp_path / "np2").evaluate(_POINTS)[0])
    assert value.real > 0.0


def test_the_loop_born_limits_keep_the_cap_when_nothing_is_inferred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The loop service's Born limits: an empty minimal inference (no Born
    within the expansion orders) keeps the capped limits, not the uncapped
    explicit ones."""

    class _Model:
        def coupling_order_expansion_orders(self) -> dict[str, int]:
            return {"NP": 1}

    class _Names:
        def mapping(self, values):
            return dict(values)

    monkeypatch.setattr(
        loop_service,
        "infer_minimal_coupling_order_limits",
        lambda process, *, model, max_coupling_orders: {},
    )
    assert loop_service._minimal_born_limits(object(), _Model(), {}, _Names()) == {
        "NP": 1
    }
    assert loop_service._minimal_born_limits(
        object(), _Model(), {"NP": 2}, _Names()
    ) == {"NP": 2}
