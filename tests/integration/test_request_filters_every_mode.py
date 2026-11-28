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
    ProcessAlias,
    ProcessRequest,
    ProcessSet,
    RequestFilterError,
    Runtime,
)
from pyamplicol.api.errors import GenerationError
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
    #: The members served, exactly (when given).
    members: tuple[str, ...] | None = None


_EXPLICIT = {"coupling_order_policy": "explicit"}
_LABEL = {"multiparticles": {"x": ("a", "u", "u~")}}
_LINES = ("process.max_quark_lines",)
_ORDERS = ("process.max_coupling_orders",)
_SM = ("builtin", "ufo")
# x = [g, u, u~, a], x x > t t~ at QCD<=0 QED<=2: the bounds remove the gluon
# members (QCD trees only), the photon and quark members have a Born.
_TOPS = {"multiparticles": {"x": ("g", "u", "u~", "a")}, **_EXPLICIT}
_TOP_LIMITS = {"max_coupling_orders": {"QCD": 0, "QED": 2}}
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
    Cell(
        "bounds remove some members of a label",
        "x x > t t~",
        {**_TOPS, **_TOP_LIMITS},
        _SM,
        "served",
        members=("a a > t t~", "u u~ > t t~"),
    ),
    Cell(
        "bounds and the cut remove some members of a label",
        "x x > t t~",
        {**_TOPS, **_TOP_LIMITS, "max_quark_lines": 1},
        _SM,
        "served",
        max_lines=1,
        members=("a a > t t~",),
    ),
    # g g > e+ e- has no tree-level diagram: skipped, in the plan as well.
    Cell(
        "a member without a tree-level diagram",
        "p p > e+ e-",
        {},
        ("builtin",),
        "served",
        members=tuple(f"{q} {q}~ > e+ e-" for q in "bcdsu"),
    ),
    Cell(
        "a member without a tree-level diagram",
        "p p > e+ e-",
        {},
        ("ufo",),
        "served",
        members=tuple(f"{q} {q}~ > e+ e-" for q in "cdsu"),
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
    if cell.members is not None:
        assert tuple(planned_members) == cell.members
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


@pytest.mark.parametrize("model", _SM)
@pytest.mark.parametrize("mode", MODES)
def test_members_without_a_born_go_before_any_mode_and_keep_the_ids(
    mode: str, model: str, models: dict[str, ModelSource], tmp_path: Path
) -> None:
    # The served members keep the IDs they have without the bounds; on a UFO
    # model also those they have without the quark-line cut.
    source = models[model]

    def plan_ids(settings: dict[str, object]) -> dict[str, str]:
        plan = _generator(mode, settings).plan(["x x > t t~"], model=source)
        return {process.expression: process.name for process in plan.concrete_processes}

    unbounded = plan_ids({**_TOPS, "max_quark_lines": 1})
    bounded = plan_ids({**_TOPS, **_TOP_LIMITS, "max_quark_lines": 1})
    assert list(bounded) == ["a a > t t~"]
    assert bounded["a a > t t~"] == unbounded["a a > t t~"]
    if model == "ufo":
        assert bounded["a a > t t~"] == plan_ids(_TOPS)["a a > t t~"]
    output = tmp_path / "served"
    _generator(mode, {**_TOPS, **_TOP_LIMITS, "max_quark_lines": 1}).generate(
        ["x x > t t~"], output, model=source
    )
    manifest = json.loads((output / "artifact.json").read_text(encoding="utf-8"))
    assert [(item["expression"], item["id"]) for item in manifest["processes"]] == [
        ("a a > t t~", bounded["a a > t t~"])
    ]


@pytest.mark.parametrize("mode", MODES)
def test_an_excluded_member_never_stands_for_a_flavour_class(
    mode: str, models: dict[str, ModelSource], tmp_path: Path
) -> None:
    # NP fixture at the default NP<=1: d d~ > vm vm~ (NP^2) has no Born,
    # u u~ > vm vm~ has one. Flavour-blind grouping may not let the excluded
    # down member represent the class.
    settings: dict[str, object] = {
        "multiparticles": {"x": ("u", "d"), "y": ("u~", "d~")},
        "flavor_blind": True,
    }
    plan = _generator(mode, settings).plan(["x y > vm vm~"], model=models["np"])
    assert [process.expression for process in plan.concrete_processes] == [
        "u u~ > vm vm~"
    ]
    output = tmp_path / "grouped"
    _generator(mode, settings).generate(["x y > vm vm~"], output, model=models["np"])
    manifest = json.loads((output / "artifact.json").read_text(encoding="utf-8"))
    assert [item["expression"] for item in manifest["processes"]] == ["u u~ > vm vm~"]


# An alias of a label request that the quark-line cut leaves with one member
# follows that member's ID; a call that refuses publishes nothing.
_COMPTON = {"multiparticles": {"x": ("u", "e-")}}
_PUBLIC = [[100, 0, 0, -100], [100, 0, 0, 100], [100, -60, -80, 0], [100, 60, 80, 0]]


def _compton() -> ProcessSet:
    request = ProcessRequest.parse("x a > x a", name="compton")
    return ProcessSet(
        (request,), (ProcessAlias("crossed", request.name, (1, 0, 3, 2)),)
    )


@pytest.mark.parametrize("append", (False, True), ids=("fresh", "append"))
@pytest.mark.parametrize("mode", ("compiled", "recurrence", "on-the-fly"))
def test_an_alias_follows_the_one_member_the_cut_keeps(
    mode: str, append: bool, models: dict[str, ModelSource], tmp_path: Path
) -> None:
    source = models["ufo"]
    output = tmp_path / "artifact"
    cut = {**_COMPTON, "max_quark_lines": 0}
    if append:
        _generator(mode, cut).generate(["e- mu- > e- mu-"], output, model=source)
    if append and mode == "recurrence":
        # The recurrence mode does not append; its refusal leaves the
        # artifact as it was.
        before = (output / "artifact.json").read_bytes()
        with pytest.raises(GenerationError, match="instead of appending"):
            _generator(mode, cut).generate(
                _compton(), output, model=source, mode="append"
            )
        assert (output / "artifact.json").read_bytes() == before
        return
    result = _generator(mode, cut).generate(
        _compton(), output, model=source, mode="append" if append else "error"
    )
    (alias,) = result.processes.aliases
    assert alias.process_name == "compton_2"
    manifest = json.loads((output / "artifact.json").read_text(encoding="utf-8"))
    assert ("e- a > e- a", "compton_2") in [
        (item["expression"], item["id"]) for item in manifest["processes"]
    ]
    crossed = complex(Runtime.load(output, process="crossed").evaluate([_PUBLIC])[0])
    # The alias's leg i is the representative's leg (1, 0, 3, 2)[i].
    representative = [_PUBLIC[index] for index in (1, 0, 3, 2)]
    member = complex(
        Runtime.load(output, process="compton_2").evaluate([representative])[0]
    )
    assert crossed.real == pytest.approx(member.real, rel=1e-12)
    assert crossed.real > 0.0
    # Without the cut the alias is ambiguous: refused before anything is
    # published (a new output is not created, an appended one is unchanged).
    target = tmp_path / ("ambiguous" if not append else "artifact")
    before = (output / "artifact.json").read_bytes()
    with pytest.raises(GenerationError, match="ambiguous"):
        _generator(mode, _COMPTON).generate(
            _compton(), target, model=source, mode="append" if append else "error"
        )
    if append:
        assert (output / "artifact.json").read_bytes() == before
    else:
        assert not target.exists()


@pytest.mark.parametrize("mode", MODES)
def test_a_plan_reports_the_member_it_skips(
    mode: str,
    models: dict[str, ModelSource],
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        plan = _generator(mode, {}).plan(["p p > e+ e-"], model=models["ufo"])
    assert "g g > e+ e-" not in [p.expression for p in plan.concrete_processes]
    assert (
        "Skipped 1 concrete subprocess with no model-supported tree-level "
        "amplitudes: p_p_to_e_e_1 (g g > e+ e-)"
    ) in caplog.text
