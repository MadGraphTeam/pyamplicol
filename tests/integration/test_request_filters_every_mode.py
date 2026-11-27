# SPDX-License-Identifier: 0BSD
"""Every request filter acts the same in every tree mode, for both model sources.

The table below is the contract: each tree execution mode (compiled,
recurrence, on-the-fly, eager) on the built-in SM and on a prepared UFO model
(the shipped ``sm``, and a copy whose ``NP`` order has expansion order 1),
planned and generated. A filter is *applied*: the members it removes are
absent from the plan and the artifact, and a request it empties raises
``RequestFilterError`` naming it; the coupling-order limits change the value.
A request without a tree-level diagram is refused for its physics
(``NoTreeDiagramError``), and a particle veto, a one-loop setting, is refused
for a tree request (``ConfigurationError``). ``plan`` and ``generate`` give
the same outcome in every cell: the same refusal word for word, or the same
processes.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

import pyamplicol
from pyamplicol import (
    Generator,
    ModelSource,
    NoTreeDiagramError,
    RequestFilterError,
    Runtime,
)
from pyamplicol.config import (
    ColorConfig,
    ConfigurationError,
    EvaluatorConfig,
    GenerationConfig,
    GenerationRelationDiscoveryConfig,
    GenerationValidationConfig,
    ModelConfig,
    ProcessConfig,
    RunConfig,
)

MODES = ("compiled", "recurrence", "on-the-fly", "eager")
_SM_UFO = Path(pyamplicol.__file__).resolve().parent / "assets/models/ufo/sm"
_POINT = [[100, 0, 0, 100], [100, 0, 0, -100], [100, 60, 80, 0], [100, -60, -80, 0]]
_QUARKS = {"u", "d", "s", "c", "b", "t"}


@pytest.fixture(scope="module")
def models(tmp_path_factory: pytest.TempPathFactory) -> dict[str, ModelSource]:
    """The built-in SM and prepared bundles of the UFO ``sm`` and its NP copy."""

    if importlib.util.find_spec("pyamplicol._rusticol") is None:
        pytest.skip("the Rusticol extension has not been built")
    root = tmp_path_factory.mktemp("request-filter-models")
    np_source = root / "NP"
    shutil.copytree(
        _SM_UFO, np_source, ignore=shutil.ignore_patterns("*.pkl", "__pycache__")
    )
    with (np_source / "coupling_orders.py").open("a", encoding="utf-8") as handle:
        handle.write(
            "\nNP = CouplingOrder(name='NP', expansion_order=1, hierarchy=1)\n"
        )
    couplings = np_source / "couplings.py"
    text, count = re.subn(
        r"(GC_(?:50|58|62) = Coupling\([^)]*?(?:.|\n)*?order = )\{'QED':1\}",
        r"\1{'QED':1,'NP':1}",
        couplings.read_text(encoding="utf-8"),
    )
    assert count == 3
    couplings.write_text(text, encoding="utf-8")
    prepared = {"builtin": ModelSource.built_in_sm()}
    for name, source in (("ufo", _SM_UFO), ("np", np_source)):
        bundle = root / f"{name}.pyamplicol-model"
        ModelSource.from_path(source, restriction="default").compile(
            cache_dir=root / f"cache-{name}",
            prepared_output=bundle,
            evaluator=EvaluatorConfig(),
        )
        prepared[name] = ModelSource.from_path(bundle)
    return prepared


@dataclass(frozen=True)
class Cell:
    """One row: a request, its process settings, the model sources it runs
    on, and what every mode must do with it."""

    name: str
    request: str
    settings: dict[str, object]
    models: tuple[str, ...]
    #: "filter" (RequestFilterError naming ``named``), "served" (no member
    #: above ``max_lines`` quark lines; ``value`` when given), "physics"
    #: (NoTreeDiagramError), "veto" (ConfigurationError).
    outcome: str
    named: tuple[str, ...] = ()
    max_lines: int | None = None
    value: float | None = None
    #: Generate as well as plan (the large served expansions are planned only).
    generate: bool = True


_EXPLICIT = {"coupling_order_policy": "explicit"}
_LABEL = {"multiparticles": {"x": ("a", "u", "u~")}}
_LINES = ("process.max_quark_lines",)
_ORDERS = ("process.max_coupling_orders",)
_SM = ("builtin", "ufo")
TABLE = (
    Cell("cut empties", "u d > u d", {"max_quark_lines": 1}, _SM, "filter", _LINES),
    Cell(
        "cut empties 2->3", "u d > u d g", {"max_quark_lines": 1}, _SM, "filter", _LINES
    ),
    Cell(
        "cut removes part",
        "p p > j j",
        {"max_quark_lines": 1},
        _SM,
        "served",
        max_lines=1,
        generate=False,
    ),
    Cell(
        "cut removes part, the rest has a Born",
        "x x > w+ w-",
        {"max_quark_lines": 0, **_LABEL},
        _SM,
        "served",
        max_lines=0,
    ),
    Cell(
        "cut removes part, the rest has no Born",
        "x x > z z",
        {"max_quark_lines": 0, **_LABEL},
        _SM,
        "filter",
        _LINES,
    ),
    Cell(
        "limit empties (card)",
        "b g > b g",
        {"max_coupling_orders": {"QCD": 0}, **_EXPLICIT},
        _SM,
        "filter",
        _ORDERS,
    ),
    Cell("limit empties (annotation)", "b g > b g QCD=0", {}, _SM, "filter", _ORDERS),
    Cell(
        "limit removes part",
        "u u~ > d d~",
        {"max_coupling_orders": {"QCD": 0}, **_EXPLICIT},
        _SM,
        "served",
        value=0.0302257265317149,
    ),
    Cell("no limit", "u u~ > d d~", {}, _SM, "served", value=0.6107749852478589),
    Cell("expansion order empties", "d d~ > vm vm~", {}, ("np",), "filter", _ORDERS),
    Cell(
        "expansion order replaced by a limit",
        "d d~ > vm vm~",
        {"max_coupling_orders": {"NP": 2}},
        ("np",),
        "served",
        value=0.0018678450497771036,
    ),
    Cell("particle veto", "u u~ > e+ e- / z", {}, _SM, "veto"),
    Cell("no diagram", "a a > a a", {}, _SM, "physics"),
    Cell("charge conservation", "u u~ > e+ e+", {}, _SM, "physics"),
)
CELLS = [
    pytest.param(cell, model, id=f"{cell.name}-{model}")
    for cell in TABLE
    for model in cell.models
]


def _generator(mode: str, settings: dict[str, object]) -> Generator:
    return Generator(
        RunConfig(
            action="generate",
            model=ModelConfig(cache=False),
            color=ColorConfig(accuracy="lc"),
            process=ProcessConfig(**settings),  # type: ignore[arg-type]
            evaluator=EvaluatorConfig(execution_mode=mode),
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


def _lines(expression: str) -> int:
    legs = expression.replace(">", " ").split()
    return sum(leg.rstrip("~") in _QUARKS for leg in legs) // 2


_ERRORS = {
    "filter": RequestFilterError,
    "physics": NoTreeDiagramError,
    "veto": ConfigurationError,
}


@pytest.mark.parametrize(("cell", "model"), CELLS)
@pytest.mark.parametrize("mode", MODES)
def test_every_filter_in_every_tree_mode(
    cell: Cell,
    model: str,
    mode: str,
    models: dict[str, ModelSource],
    tmp_path: Path,
) -> None:
    source = models[model]
    if cell.outcome in _ERRORS:
        error = _ERRORS[cell.outcome]
        with pytest.raises(error) as planned:
            _generator(mode, cell.settings).plan([cell.request], model=source)
        output = tmp_path / "refused"
        with pytest.raises(error) as generated:
            _generator(mode, cell.settings).generate(
                [cell.request], output, model=source
            )
        assert not output.exists()
        assert str(generated.value) == str(planned.value)
        if cell.outcome == "filter":
            assert isinstance(generated.value, RequestFilterError)
            assert generated.value.settings == cell.named
            assert "loop-induced" not in str(generated.value)
        return
    plan = _generator(mode, cell.settings).plan([cell.request], model=source)
    planned_members = sorted(process.expression for process in plan.concrete_processes)
    assert planned_members
    if cell.max_lines is not None:
        assert all(_lines(member) <= cell.max_lines for member in planned_members)
    if not cell.generate:
        return
    output = tmp_path / "served"
    _generator(mode, cell.settings).generate([cell.request], output, model=source)
    manifest = json.loads((output / "artifact.json").read_text(encoding="utf-8"))
    stored = sorted(str(process["expression"]) for process in manifest["processes"])
    assert stored == planned_members
    if cell.value is not None:
        runtime = Runtime.load(output, process=str(manifest["processes"][0]["id"]))
        value = complex(runtime.evaluate([_POINT])[0]).real
        assert value == pytest.approx(cell.value, rel=1e-10)
