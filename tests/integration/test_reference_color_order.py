# SPDX-License-Identifier: 0BSD
"""``process.reference_color_order`` relabels the colour plan, nothing more.

The sector whose colour tensor the order spells comes first; a cyclic
rotation of a trace, or its reflection where reflections are folded, names
that same sector, never another. For every reference order the published
flows, the value of each flow, every squared-order partial and the inclusive
value equal those of the default order, in the recurrence, compiled and
on-the-fly modes at LC, NLC and full colour, and every advertised flow is
selectable. With a cap the reference sector is kept (it is the plan's first)
and the kept flows are distinct and equal the same flows of the complete
artifact. An open line read from its antiquark end is the same line, its
gluons in the reverse order.

A reference is an ordering of the process's coloured legs (colourless legs
may stand in it and are ignored): a repeated, foreign or missing label is a
configuration error before generation in every mode; a well-formed order that
spells no sector reorders nothing, and a colourless process has nothing to
name. The eager mode refuses a colour-sector subset of a plan with folded
trace reflections.
"""

from __future__ import annotations

import importlib.util
import math
import re
from itertools import permutations
from pathlib import Path

import pytest

from pyamplicol import Generator, ModelSource, Runtime
from pyamplicol.api.errors import GenerationError
from pyamplicol.config import (
    ColorConfig,
    ConfigurationError,
    EvaluatorConfig,
    EvaluatorOptimizationConfig,
    GenerationConfig,
    GenerationRelationDiscoveryConfig,
    GenerationValidationConfig,
    ModelConfig,
    ProcessConfig,
    RunConfig,
)
from pyamplicol.generation.phase_space import massive_rambo_final_state

_NIGHTLY = pytest.mark.loop_nightly
_MASSES = {6: 173.0}
_MODES = ("recurrence", "compiled", "on-the-fly")


def _model(name: str) -> ModelSource:
    return ModelSource.built_in_sm() if name == "sm" else ModelSource.built_in_sm_heft()


def _config(mode: str, accuracy: str, orders, **selection) -> RunConfig:
    process = (
        ProcessConfig(**selection)
        if orders is None
        else ProcessConfig(
            coupling_order_policy="explicit", max_coupling_orders=orders, **selection
        )
    )
    return RunConfig(
        action="generate",
        model=ModelConfig(cache=False),
        color=ColorConfig(accuracy=accuracy),
        process=process,
        generation=GenerationConfig(
            workers=1,
            emit_api_bundle=False,
            relation_discovery=GenerationRelationDiscoveryConfig(mode="off"),
            validation=GenerationValidationConfig(
                enabled=False, post_build_validation=False
            ),
        ),
        evaluator=EvaluatorConfig(
            execution_mode=mode,
            optimization=EvaluatorOptimizationConfig(cores=1),
        ),
    )


def _points(runtime: Runtime):
    masses = [
        _MASSES.get(abs(particle.pdg_id), 0.0)
        for particle in runtime.physics.external_particles
    ]
    sqrt_s, (m1, m2) = 1000.0, masses[:2]
    s = sqrt_s * sqrt_s
    p = math.sqrt((s - (m1 + m2) ** 2) * (s - (m1 - m2) ** 2)) / (2 * sqrt_s)
    return [
        [
            [math.hypot(p, m1), 0.0, 0.0, p],
            [math.hypot(p, m2), 0.0, 0.0, -p],
            *[
                [float(v) for v in momentum]
                for momentum in massive_rambo_final_state(
                    len(masses) - 2, sqrt_s=sqrt_s, masses=masses[2:], seed=seed
                )
            ],
        ]
        for seed in (7, 8)
    ]


def _real(values) -> list[float]:
    return [complex(value).real for value in values]


def _record(runtime: Runtime, points):
    """Inclusive values, squared-order partials and, at LC, every flow."""

    total = _real(runtime.evaluate(points))
    split = runtime.evaluate_orders(points)
    partials = {label: _real(split.for_order(label)) for label in split.orders}
    flows = {}
    if runtime.physics.color_accuracy == "lc":
        for flow in runtime.physics.color_flows:
            flows[flow.id] = _real(runtime.evaluate(points, color_flows=[flow.id]))
    return total, partials, flows


def _assert_close(left, right, context) -> None:
    for a, b in zip(left, right, strict=True):
        assert a == pytest.approx(b, rel=1e-12, abs=1e-300), context


@pytest.fixture(scope="module")
def generate(tmp_path_factory: pytest.TempPathFactory):
    if importlib.util.find_spec("pyamplicol._rusticol") is None:
        pytest.skip("the Rusticol extension has not been built")
    root = tmp_path_factory.mktemp("reference-order")
    count = [0]

    def artifact(model: str, process: str, mode: str, accuracy: str, orders, **sel):
        count[0] += 1
        path = root / f"a{count[0]}"
        Generator(_config(mode, accuracy, orders, **sel)).generate(
            process, path, model=_model(model)
        )
        return Runtime.load(path)

    return artifact


# (model, process, orders, references): ordinary QCD processes.
_ALL_FOUR = tuple(permutations((1, 2, 3, 4)))
_CASES = (
    pytest.param(
        "sm", "g g > g g", None, ((1, 3, 4, 2), (2, 3, 4, 1), (1, 2, 4, 3)), id="qcd"
    ),
    pytest.param("sm", "g g > g g", None, _ALL_FOUR, id="qcd-all", marks=_NIGHTLY),
    pytest.param(
        "sm",
        "g g > g g g",
        None,
        ((2, 3, 4, 5, 1), (1, 3, 5, 2, 4), (1, 5, 4, 3, 2)),
        id="qcd-five",
        marks=_NIGHTLY,
    ),
    pytest.param(
        "sm",
        "g g > t t~ g",
        None,
        ((3, 2, 1, 5, 4), (3, 1, 5, 2, 4), (3, 5, 2, 1, 4)),
        id="line-five",
        marks=_NIGHTLY,
    ),
    # One quark line from either end (the incoming u is the outgoing
    # antiquark 1), and two quark lines: line blocks in either order, a line
    # spelled from its antiquark, the other pairing.
    pytest.param(
        "sm",
        "u u~ > g g g",
        None,
        ((2, 3, 4, 5, 1), (1, 5, 4, 3, 2), (2, 4, 3, 5, 1)),
        id="quark-gluons",
    ),
    pytest.param(
        "sm",
        "d d~ > u u~ g",
        None,
        ((3, 4, 1, 5, 2), (1, 5, 2, 3, 4), (2, 5, 1, 3, 4), (2, 4, 3, 5, 1)),
        id="two-lines",
    ),
    pytest.param(
        "sm",
        "g g > g g g g",
        None,
        (
            (1, 2, 3, 4, 5, 6),
            (4, 5, 6, 1, 2, 3),
            (1, 6, 5, 4, 3, 2),
            (1, 4, 2, 6, 3, 5),
        ),
        id="qcd-six",
        marks=_NIGHTLY,
    ),
)


@pytest.mark.parametrize("accuracy", ["lc", "nlc", "full"])
@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize(("model", "process", "orders", "references"), _CASES)
def test_a_reference_order_changes_no_flow_and_no_value(
    generate, model: str, process: str, orders, references, mode: str, accuracy: str
) -> None:
    default = generate(model, process, mode, accuracy, orders)
    points = _points(default)
    total, partials, flows = _record(default, points)
    for reference in references:
        reordered = generate(
            model,
            process,
            mode,
            accuracy,
            orders,
            reference_color_order=list(reference),
        )
        r_total, r_partials, r_flows = _record(reordered, points)
        _assert_close(r_total, total, ("total", reference))
        assert set(r_partials) == set(partials), reference
        for label, values in r_partials.items():
            _assert_close(values, partials[label], (label, reference))
        assert len(reordered.physics.color_flows) == len(default.physics.color_flows)
        assert set(r_flows) == set(flows), reference
        for flow, values in r_flows.items():
            _assert_close(values, flows[flow], (flow, reference))


def _reflected(flow: str) -> str:
    """The same trace in the other orientation (from the same first label)."""

    labels = flow.removeprefix("flow:").split(",")
    return "flow:" + ",".join([labels[0], *reversed(labels[1:])])


def _reference_flow(flows: list[str], reference: tuple[int, ...]) -> str:
    """The published flow the reference names: the same open lines, or the
    same trace up to rotation (and reflection where reflections are folded)."""

    rotations = {reference[i:] + reference[:i] for i in range(len(reference))}
    reflected = tuple(reversed(reference))
    rotations |= {reflected[i:] + reflected[:i] for i in range(len(reflected))}
    matches = [
        flow
        for flow in flows
        if "|" not in flow
        and tuple(int(x) for x in flow.removeprefix("flow:").split(",")) in rotations
    ]
    exact = [
        flow
        for flow in matches
        if tuple(int(x) for x in flow.removeprefix("flow:").split(","))
        in {reference[i:] + reference[:i] for i in range(len(reference))}
    ]
    return (exact or matches)[0]


@pytest.mark.parametrize(
    ("model", "process", "orders", "reference"),
    [
        pytest.param("sm", "g g > g g", None, (2, 3, 4, 1), id="qcd-cyclic"),
        pytest.param("sm", "g g > g g", None, (1, 3, 4, 2), id="qcd"),
        pytest.param("sm", "g g > t t~ g", None, (3, 2, 1, 5, 4), id="line"),
    ],
)
def test_a_capped_reference_keeps_the_reference_first(
    generate, model: str, process: str, orders, reference
) -> None:
    complete = generate(model, process, "compiled", "lc", orders)
    points = _points(complete)
    ids = [flow.id for flow in complete.physics.color_flows]
    first = _reference_flow(ids, reference)
    for cap in range(1, len(ids) + 1):
        capped = generate(
            model,
            process,
            "compiled",
            "lc",
            orders,
            reference_color_order=list(reference),
            max_color_sectors=cap,
        )
        kept = [flow.id for flow in capped.physics.color_flows]
        assert len(kept) == len(set(kept)), (cap, kept)
        # Where reflections are folded, a kept trace publishes both of its
        # orientations: at most two flows per kept sector.
        assert cap <= len(kept) <= 2 * cap or len(kept) == len(ids), (cap, kept)
        # Public physics lists flows in its own order: the cap keeps the
        # reference sector (alone at cap one).
        assert first in kept, (cap, kept)
        if cap == 1:
            assert set(kept) <= {first, _reflected(first)}, kept
        total = [0.0] * len(points)
        for flow in kept:
            expected = _real(complete.evaluate(points, color_flows=[flow]))
            total = [a + b for a, b in zip(total, expected, strict=True)]
            _assert_close(
                _real(capped.evaluate(points, color_flows=[flow])),
                expected,
                (cap, flow),
            )
        _assert_close(_real(capped.evaluate(points)), total, cap)


def _sector_count(model: str, process: str, mode: str, accuracy: str, orders) -> int:
    """The lane's colour-sector count, from its dry run (which reads the
    model cache)."""

    from dataclasses import replace

    config = replace(_config(mode, accuracy, orders), model=ModelConfig())
    plan = Generator(config).plan(process, model=_model(model))
    (record,) = plan.estimated_coverage["processes"]
    return int(record["color_sector_count"])


@pytest.mark.parametrize("reference", [None, "cyclic"])
@pytest.mark.parametrize("mode", _MODES)
@pytest.mark.parametrize(
    ("model", "process", "orders", "cyclic"),
    [
        pytest.param("sm", "g g > g g", None, (2, 3, 4, 1), id="qcd"),
        pytest.param("sm", "u u~ > g g g", None, (2, 3, 4, 5, 1), id="quark-gluons"),
        pytest.param("sm", "d d~ > u u~ g", None, (3, 4, 1, 5, 2), id="two-lines"),
    ],
)
def test_the_cap_boundary_of_an_ordinary_plan(
    generate, tmp_path: Path, model, process, orders, cyclic, mode, reference
) -> None:
    """A cap truncates the plan only when it leaves a sector out, with or
    without a reference order: a cap of n or n + 1 for an n-sector plan
    serves the complete plan in every lane that takes caps; n - 1 truncates
    (recurrence refuses a truncated plan, compiled serves the subset, whose
    flows keep their complete values); on-the-fly refuses any cap."""

    selection = {} if reference is None else {"reference_color_order": list(cyclic)}
    complete = generate(model, process, mode, "lc", orders)
    points = _points(complete)
    inclusive = _real(complete.evaluate(points))
    n = _sector_count(
        model, process, "compiled" if mode == "on-the-fly" else mode, "lc", orders
    )
    for cap in (n - 1, n, n + 1):
        config = _config(mode, "lc", orders, max_color_sectors=cap, **selection)
        path = tmp_path / f"{mode}-{cap}"
        if mode == "on-the-fly" or (mode == "recurrence" and cap < n):
            with pytest.raises(GenerationError, match=r"max_color_sectors|truncated"):
                Generator(config).generate(process, path, model=_model(model))
            continue
        Generator(config).generate(process, path, model=_model(model))
        capped = Runtime.load(path)
        flows = [flow.id for flow in capped.physics.color_flows]
        assert len(flows) == len(set(flows))
        values = _real(capped.evaluate(points))
        if cap >= n:
            assert set(flows) == {flow.id for flow in complete.physics.color_flows}
            _assert_close(values, inclusive, (cap, "complete"))
            continue
        total = [0.0] * len(points)
        for flow in flows:
            expected = _real(complete.evaluate(points, color_flows=[flow]))
            _assert_close(
                _real(capped.evaluate(points, color_flows=[flow])), expected, flow
            )
            total = [a + b for a, b in zip(total, expected, strict=True)]
        _assert_close(values, total, (cap, "subset"))


def _flow_values(runtime: Runtime, points) -> dict[str, list[float]]:
    return {
        flow.id: _real(runtime.evaluate(points, color_flows=[flow.id]))
        for flow in runtime.physics.color_flows
    }


@pytest.mark.parametrize("mode", ("compiled", "recurrence", "on-the-fly", "eager"))
@pytest.mark.parametrize(
    ("process", "spellings"),
    [
        # The incoming u is the outgoing antiquark 1: a line from 2 to 1.
        pytest.param("u u~ > g g", ((2, 3, 4, 1), (1, 4, 3, 2)), id="one-line"),
        pytest.param(
            "u u~ > g g g", ((2, 3, 5, 4, 1), (1, 4, 5, 3, 2)), id="one-line-three"
        ),
        # Lines 2 -> 5 6 -> 1 and 3 -> 4, each read from either end, in either
        # order.
        pytest.param(
            "d d~ > u u~ g g",
            (
                (2, 5, 6, 1, 3, 4),
                (1, 6, 5, 2, 4, 3),
                (4, 3, 2, 5, 6, 1),
                (3, 4, 1, 6, 5, 2),
            ),
            id="two-lines",
        ),
    ],
)
def test_a_line_read_from_its_other_end_is_the_same_line(
    generate, process: str, spellings, mode: str
) -> None:
    """Every spelling of the same open lines names the same sector: a cap of
    one (compiled, eager) or the fixed sector 0 (compiled, recurrence) keeps
    the same flow with the same value, that flow's value in the complete
    artifact; on-the-fly lists it first."""

    complete = generate("sm", process, "compiled", "lc", None)
    points = _points(complete)
    reference_values = _flow_values(complete, points)
    selections = {
        "compiled": ({"max_color_sectors": 1}, {"selected_color_sector_ids": [0]}),
        "recurrence": ({"selected_color_sector_ids": [0]},),
        "eager": ({"max_color_sectors": 1},),
        "on-the-fly": ({},),
    }[mode]
    for selection in selections:
        kept = set()
        for spelling in spellings:
            runtime = generate(
                "sm",
                process,
                mode,
                "lc",
                None,
                reference_color_order=list(spelling),
                **selection,
            )
            flows = [flow.id for flow in runtime.physics.color_flows]
            first = flows[0] if mode == "on-the-fly" else None
            if mode != "on-the-fly":
                assert len(flows) == 1, (spelling, flows)
                first = flows[0]
            kept.add(first)
            _assert_close(
                _real(runtime.evaluate(points, color_flows=[first])),
                reference_values[first],
                (spelling, first),
            )
        assert len(kept) == 1, (selection, kept)


_MALFORMED = (
    pytest.param([1, 2, 2, 4], r"repeats the labels \[2\]", id="repeated"),
    pytest.param([1, 2, 3], r"leaves out the coloured legs \[4\]", id="missing"),
    pytest.param([1, 2, 3, 4, 91], r"names labels \[91\]", id="foreign"),
)


@pytest.mark.parametrize("cap", [None, 1], ids=["uncapped", "cap-1"])
@pytest.mark.parametrize("mode", ("compiled", "recurrence", "on-the-fly", "eager"))
@pytest.mark.parametrize(("word", "problem"), _MALFORMED)
def test_a_malformed_reference_is_a_configuration_error(
    tmp_path: Path, word, problem: str, mode: str, cap
) -> None:
    """A reference that is not an ordering of the coloured legs is refused
    in the dry run and in generation, before anything is written, with or
    without a cap (on-the-fly refuses any cap first, for its own reason)."""

    from dataclasses import replace

    if mode == "on-the-fly" and cap is not None:
        pytest.skip("on-the-fly refuses a cap before it reads the process")
    selection = {"reference_color_order": word}
    if cap is not None:
        selection["max_color_sectors"] = cap
    config = _config(mode, "lc", None, **selection)
    message = r"process\.reference_color_order=.* is not an ordering of the "
    message += r"coloured legs \[1, 2, 3, 4\] of 'g g > g g' .*" + problem
    with pytest.raises(ConfigurationError, match=message):
        Generator(replace(config, model=ModelConfig())).plan(
            "g g > g g", model=_model("sm")
        )
    output = tmp_path / "artifact"
    with pytest.raises(ConfigurationError, match=message):
        Generator(config).generate("g g > g g", output, model=_model("sm"))
    assert not output.exists()


@pytest.mark.parametrize(("word", "problem"), _MALFORMED)
def test_the_cli_and_the_run_card_refuse_a_malformed_reference(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], word, problem: str
) -> None:
    from pyamplicol.cli.main import main as cli_main

    setting = "process.reference_color_order=[" + ",".join(map(str, word)) + "]"
    for dry_run in ((), ("--dry-run",)):
        output = tmp_path / f"cli{len(dry_run)}"
        code = cli_main(
            [
                "generate",
                "g g > g g",
                str(output),
                "--set",
                setting,
                *dry_run,
            ]
        )
        assert code == 2
        assert re.search(problem, capsys.readouterr().err)
        assert not output.exists()
    card = tmp_path / "card.toml"
    card.write_text(
        'action = "generate"\n'
        "[process]\n"
        'entries = [{ expression = "g g > g g" }]\n'
        f"reference_color_order = {list(word)}\n",
        encoding="utf-8",
    )
    output = tmp_path / "card-artifact"
    assert cli_main([str(card), "generate", "--output", str(output)]) == 2
    assert re.search(problem, capsys.readouterr().err)
    assert not output.exists()


@pytest.mark.parametrize("mode", ("compiled", "recurrence"))
def test_a_well_formed_order_that_names_no_sector_reorders_nothing(
    generate, mode: str
) -> None:
    """``u u~ > g g`` ``[3, 1, 2, 4]`` interrupts the quark line with a gluon:
    a well-formed order of the coloured legs that spells no sector keeps the
    default order (fixed sector 0 is the default's first flow). A colourless
    leg in a reference is ignored: ``[5, 2, 3, 4, 1]`` names the line
    2 -> 3 4 -> 1 of ``u u~ > g g z``."""

    for process, word, expected in (
        ("u u~ > g g", [3, 1, 2, 4], None),
        ("u u~ > g g z", [5, 2, 3, 4, 1], "flow:2,3,4,1"),
        ("u u~ > g g z", [1, 4, 5, 3, 2], "flow:2,3,4,1"),
    ):
        complete = generate("sm", process, mode, "lc", None)
        points = _points(complete)
        first = expected or complete.physics.color_flows[0].id
        fixed = generate(
            "sm",
            process,
            mode,
            "lc",
            None,
            reference_color_order=word,
            selected_color_sector_ids=[0],
        )
        assert [flow.id for flow in fixed.physics.color_flows] == [first], word
        _assert_close(
            _real(fixed.evaluate(points)),
            _real(complete.evaluate(points, color_flows=[first])),
            word,
        )


@pytest.mark.parametrize("accuracy", ["lc", "nlc", "full"])
@pytest.mark.parametrize("mode", _MODES)
def test_a_colourless_process_has_no_sector_to_name(
    generate, tmp_path: Path, mode: str, accuracy: str
) -> None:
    """``e+ e- > mu+ mu-`` with ``[4, 3, 2, 1]``: an ordering of its legs that
    names nothing; the artifact loads and equals the default one (on-the-fly
    stores no reference word). A label it does not have is refused."""

    default = generate("sm", "e+ e- > mu+ mu-", mode, accuracy, None)
    points = _points(default)
    reordered = generate(
        "sm",
        "e+ e- > mu+ mu-",
        mode,
        accuracy,
        None,
        reference_color_order=[4, 3, 2, 1],
    )
    _assert_close(_real(reordered.evaluate(points)), _real(default.evaluate(points)), 0)
    with pytest.raises(ConfigurationError, match=r"names labels \[5\]"):
        Generator(
            _config(mode, accuracy, None, reference_color_order=[1, 2, 3, 5])
        ).generate("e+ e- > mu+ mu-", tmp_path / "foreign", model=_model("sm"))


_FOLDED_SUBSETS = (
    pytest.param({"max_color_sectors": 1}, id="cap"),
    pytest.param({"selected_color_sector_ids": [0]}, id="fixed"),
    pytest.param({"max_color_sectors": 2, "selected_color_sector_ids": [1]}, id="both"),
)


@pytest.mark.parametrize("reference", [None, [2, 4, 1, 3]], ids=["plain", "reference"])
@pytest.mark.parametrize("selection", _FOLDED_SUBSETS)
def test_eager_refuses_a_subset_of_a_folded_plan(
    tmp_path: Path, selection, reference
) -> None:
    """``g g > g g`` folds each trace with its reflection: an eager subset of
    its sectors would publish both orientations of a kept trace and serve
    half of their value, so it is refused before any work, in the dry run
    and in generation."""

    from dataclasses import replace

    extra = {} if reference is None else {"reference_color_order": reference}
    config = _config("eager", "lc", None, **selection, **extra)
    message = (
        r"the eager mode does not generate a subset of the colour sectors of "
        r"'g g > g g'.*compiled or recurrence mode"
    )
    with pytest.raises(GenerationError, match=message):
        Generator(replace(config, model=ModelConfig())).plan(
            "g g > g g", model=_model("sm")
        )
    with pytest.raises(GenerationError, match=message):
        Generator(config).generate("g g > g g", tmp_path / "a", model=_model("sm"))
    assert not (tmp_path / "a").exists()


@pytest.mark.parametrize(
    ("process", "selection", "reference"),
    [
        # A folded plan kept whole.
        pytest.param("g g > g g", {"max_color_sectors": 3}, None, id="folded-cap-n"),
        pytest.param(
            "g g > g g", {"selected_color_sector_ids": [0, 1, 2]}, None, id="folded-all"
        ),
        # A quark line folds nothing: every subset is served.
        pytest.param("u u~ > g g", {"max_color_sectors": 1}, None, id="line-cap"),
        pytest.param(
            "u u~ > g g", {"selected_color_sector_ids": [0]}, None, id="line-fixed"
        ),
        pytest.param(
            "u u~ > g g", {"max_color_sectors": 1}, [1, 4, 3, 2], id="line-cap-ref"
        ),
        pytest.param(
            "u u~ > g g",
            {"selected_color_sector_ids": [0]},
            [1, 4, 3, 2],
            id="line-fixed-ref",
        ),
    ],
)
def test_eager_serves_every_other_subset(
    generate, process: str, selection, reference
) -> None:
    complete = generate("sm", process, "eager", "lc", None)
    points = _points(complete)
    values = _flow_values(complete, points)
    extra = {} if reference is None else {"reference_color_order": reference}
    subset = generate("sm", process, "eager", "lc", None, **selection, **extra)
    flows = [flow.id for flow in subset.physics.color_flows]
    expected = [sum(values[flow][i] for flow in flows) for i in range(len(points))]
    _assert_close(_real(subset.evaluate(points)), expected, flows)
    if process == "u u~ > g g":
        assert flows == ["flow:2,3,4,1"]


@pytest.mark.parametrize("accuracy", ["nlc", "full"])
@pytest.mark.parametrize("mode", _MODES)
def test_every_single_helicity_has_its_squared_order_split(
    generate, mode: str, accuracy: str
) -> None:
    """``g g > g g`` with ``[1, 3, 4, 2]``: every one of the 16 helicities,
    physically vanishing ones included (their weights are roundoff), has its
    one squared-order partial, equal to its value."""

    runtime = generate(
        "sm", "g g > g g", mode, accuracy, None, reference_color_order=[1, 3, 4, 2]
    )
    points = _points(runtime)
    scale = max(abs(value) for value in _real(runtime.evaluate(points)))
    helicities = [helicity.id for helicity in runtime.physics.helicities]
    assert len(helicities) == 16
    for helicity in helicities:
        value = _real(runtime.evaluate(points, helicities=[helicity]))
        split = runtime.evaluate_orders(points, helicities=[helicity])
        (order,) = split.orders
        for a, b in zip(_real(split.for_order(order)), value, strict=True):
            assert a == pytest.approx(b, rel=1e-12, abs=1e-14 * scale), helicity
