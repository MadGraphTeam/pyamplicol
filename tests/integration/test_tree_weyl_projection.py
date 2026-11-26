# SPDX-License-Identifier: 0BSD
"""Weyl projection at single-chirality vertices, in every tree lane.

A massless external fermion is a two-component Weyl source, and a fermion
current whose line passed a massive fermion is a four-component Dirac
current; models install no Dirac-Weyl closure contraction. A vertex with a
single chiral projector (every W vertex, Z to neutrinos) that takes such a
line to a massless fermion has a Dirac result whose other half vanishes
identically, so the model gives that result as the Weyl state of its
chirality (``CompiledUFOModel._result_chiralities``; the built-in model's
``_builtin_vertex_result_chiralities``). The line is then Weyl again at its
massless end and closes on its massless sink like any Weyl line, whatever
leg the lane closes at. The recurrence template holds both that projection
and its full-state counterpart (``Model.recurrence_quantum_flows``), marked
in the transition's output projection: the strategies whose currents carry
Weyl states run the projection, the all-flow union (the full-colour
helicity-selector companion, which runs every source family through its
full state) runs the counterpart.

Before, every tree lane refused these processes with ``dirac-weyl-closure``
wherever it closed at the massless leg (``vt e- > ve ta-``, not
``e- vt > ve ta-``). A vertex with both chiral projections (left- and
right-handed couplings) between a massive and a massless fermion keeps the
Dirac current, and the lanes still refuse a line that brings it to a massless
sink (``test_a_vertex_with_both_chiral_projections_is_still_refused``).

References: MadGraph 3.7.0 standalone, ``tools/developer/madgraph_split_orders.py``
on the UFO ``sm`` (default restriction, ``lepton_masses``, ``no_b_mass``;
t-channel widths kept), full colour and, for the processes without external
gluons, leading colour (``--colour lc``), at RAMBO points (seeds 9001, 9002,
sqrt(s) = 1000 GeV, the restriction's masses): ``madgraph-weyl-projection-*.json``.
A colour-singlet process has the same value at leading and full colour.
"""

from __future__ import annotations

import json
import re
import shutil
from importlib import resources
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
REFERENCES = {
    "default": FIXTURES / "madgraph-weyl-projection-sm.json",
    "lepton_masses": FIXTURES / "madgraph-weyl-projection-lepton-masses.json",
    "no_b_mass": FIXTURES / "madgraph-weyl-projection-no-b-mass.json",
}
LC_REFERENCES = {"no_b_mass": FIXTURES / "madgraph-weyl-projection-no-b-mass-lc.json"}
LANES = ("recurrence", "compiled", "eager", "on-the-fly")
ALL_ORDERS = {"QCD": 99, "QED": 99}
TOLERANCE = 1e-11


def _entries(path: Path) -> dict[str, dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {entry["process"]: entry for entry in payload["processes"]}


def _reference(restriction: str, process: str, accuracy: str = "full"):
    path = LC_REFERENCES.get(restriction) if accuracy == "lc" else None
    entries = _entries(path) if path is not None else {}
    return entries.get(process) or _entries(REFERENCES[restriction])[process]


def _compile(source: Path, restriction: str, root: Path) -> ModelSource:
    bundle = root / f"sm-{restriction}.pyamplicol-model"
    ModelSource.from_path(source, restriction=restriction).compile(
        cache_dir=root / "cache", prepared_output=bundle, evaluator=EvaluatorConfig()
    )
    return ModelSource.from_path(bundle)


@pytest.fixture(scope="module")
def sm_models(madgraph_source: Path, tmp_path_factory: pytest.TempPathFactory):
    """The UFO sm under a restriction card, compiled once per module."""

    built: dict[str, ModelSource] = {}

    def model(restriction: str) -> ModelSource:
        if restriction not in built:
            root = tmp_path_factory.mktemp(f"sm-{restriction}")
            built[restriction] = _compile(
                madgraph_source / "models/sm", restriction, root
            )
        return built[restriction]

    return model


def _runtime(
    model: ModelSource,
    process: str,
    artifact: Path,
    *,
    lane: str = "recurrence",
    accuracy: str = "full",
) -> Runtime:
    config = RunConfig(
        action="generate",
        model=ModelConfig(cache=False),
        color=ColorConfig(accuracy=accuracy),
        process=ProcessConfig(
            coupling_order_policy="explicit", max_coupling_orders=ALL_ORDERS
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
            execution_mode=lane, optimization=EvaluatorOptimizationConfig(cores=1)
        ),
    )
    Generator(config).generate(process, artifact, model=model)
    return Runtime.load(artifact)


def _values(runtime: Runtime, points) -> list[float]:
    values = [complex(value) for value in runtime.evaluate(points)]
    assert all(value.imag == 0.0 for value in values)
    return [value.real for value in values]


def _assert_close(values: list[float], expected: list[float]) -> None:
    assert len(values) == len(expected)
    for value, reference in zip(values, expected, strict=True):
        assert abs(value - reference) <= TOLERANCE * abs(reference), (value, reference)


# (restriction, process, lane, colour accuracy): the class's members in the
# default tier, one per mechanism. The tau t channel of a massless line closed
# at its massless leg, at full colour (the contracted-colour plan and the
# all-flow-union helicity selector) and at leading colour; a line with no
# fermion leg the lanes could close at instead; a massless b line through the
# top (coloured); the electron and muon with their masses.
_DEFAULT_TIER = (
    ("default", "vt e- > ve ta-", "recurrence", "full"),
    ("default", "vt vt~ > w- w+", "recurrence", "lc"),
    ("default", "vt vt~ > w- w+", "on-the-fly", "lc"),
    ("default", "vt a > ta- w+", "eager", "full"),
    ("no_b_mass", "b b~ > w+ w-", "recurrence", "full"),
    ("no_b_mass", "g b > t w-", "on-the-fly", "full"),
    ("lepton_masses", "vm e- > ve mu-", "recurrence", "full"),
)


@pytest.mark.parametrize(("restriction", "process", "lane", "accuracy"), _DEFAULT_TIER)
def test_a_massless_line_through_a_massive_fermion_matches_madgraph(
    sm_models, tmp_path: Path, restriction: str, process: str, lane: str, accuracy: str
) -> None:
    reference = _reference(restriction, process, accuracy)
    runtime = _runtime(
        sm_models(restriction),
        process,
        tmp_path / "artifact",
        lane=lane,
        accuracy=accuracy,
    )
    _assert_close(_values(runtime, reference["points"]), reference["total"])


def test_the_closure_leg_no_longer_matters(sm_models, tmp_path: Path) -> None:
    """vt e- > ve ta- (the lanes close at the massless vt) and e- vt > ve ta-
    (at the e-, which built before) at the same physical points."""

    reference = _reference("default", "vt e- > ve ta-")
    swapped = [[point[1], point[0], *point[2:]] for point in reference["points"]]
    model = sm_models("default")
    first = _values(
        _runtime(model, "vt e- > ve ta-", tmp_path / "a"), reference["points"]
    )
    second = _values(_runtime(model, "e- vt > ve ta-", tmp_path / "b"), swapped)
    _assert_close(first, reference["total"])
    _assert_close(second, first)


def _mixed_chirality_sm(destination: Path) -> Path:
    """A copy of the shipped UFO sm whose W couplings of the tau and its
    neutrino get a vector-like structure next to the left-handed one: both
    chiral projections of those vertices are nonzero."""

    shipped = Path(str(resources.files("pyamplicol").joinpath("assets/models/ufo/sm")))
    shutil.copytree(shipped, destination, ignore=shutil.ignore_patterns("__pycache__"))
    path = destination / "vertices.py"
    text = path.read_text(encoding="utf-8")
    edited = 0
    for particles in (
        "P.vt__tilde__, P.ta__minus__, P.W__plus__",
        "P.ta__plus__, P.vt, P.W__minus__",
    ):
        pattern = re.compile(
            r"(particles = \[ "
            + re.escape(particles)
            + r" \],\n\s*color = \[ '1' \],\n\s*)lorentz = \[ L\.FFV2 \],"
            r"(\n\s*)couplings = \{\(0,0\):C\.(GC_\d+)\}"
        )
        text, count = pattern.subn(
            r"\1lorentz = [ L.FFV2, L.FFV1 ],\2couplings = {(0,0):C.\3,(0,1):C.\3}",
            text,
        )
        edited += count
    assert edited == 2
    path.write_text(text, encoding="utf-8")
    return destination


@pytest.fixture(scope="module")
def mixed_chirality_model(tmp_path_factory: pytest.TempPathFactory) -> ModelSource:
    root = tmp_path_factory.mktemp("sm-mixed-chirality")
    return _compile(_mixed_chirality_sm(root / "sm_mixed"), "default", root)


@pytest.mark.parametrize(
    ("lane", "accuracy"), [("recurrence", "lc"), ("eager", "full")]
)
def test_a_vertex_with_both_chiral_projections_is_still_refused(
    mixed_chirality_model: ModelSource, tmp_path: Path, lane: str, accuracy: str
) -> None:
    """With a vector-like W coupling of the tau and its neutrino, the
    neutrino current that passed the tau keeps both halves (a Dirac current);
    the lanes refuse to close it on the massless neutrino instead of dropping
    the tau exchange."""

    with pytest.raises(
        GenerationError, match=r"dirac-weyl-closure:.*both chiral projections"
    ):
        _runtime(
            mixed_chirality_model,
            "vt vt~ > ta+ ta-",
            tmp_path / "artifact",
            lane=lane,
            accuracy=accuracy,
        )


def test_the_template_marks_the_projection_and_its_full_counterpart(
    sm_models,
) -> None:
    """The recurrence template of the default sm holds, for full inputs into
    a neutrino through a W, the projected Weyl row (Weyl-state strategies)
    and its Dirac counterpart (the all-flow union); rows of vertices that
    project nothing stay unmarked."""

    from pyamplicol.models.prepared import load_prepared_model_bundle

    bundle = load_prepared_model_bundle(sm_models("default").path)
    template = dict(bundle.kernel_pack.recurrence_template)
    projections = [str(row["output_projection"]) for row in template["transitions"]]
    weyl = [p for p in projections if p.endswith(";execution=weyl-states")]
    full = [p for p in projections if p.endswith(";execution=full-states")]
    assert weyl and full
    assert all(p.startswith("weyl-chiral:chirality=") for p in weyl)
    assert all(p.startswith("dirac:chirality=0") for p in full)
    assert len(weyl) == len(full)
    assert len(weyl) + len(full) < len(projections)


def _nightly_cases():
    for restriction, path in REFERENCES.items():
        for process in _entries(path):
            for lane in LANES:
                for accuracy in ("lc", "full"):
                    yield pytest.param(
                        restriction,
                        process,
                        lane,
                        accuracy,
                        id=f"{restriction}-{process}-{lane}-{accuracy}",
                    )


# Leading-colour sectors without any diagram (two quark lines joined only by a
# W): the recurrence lane refuses them at leading and full colour, the
# compiled lane at leading colour, a separate open item (DESIGN WP2.9, flows
# without roots).
_EMPTY_LC_SECTOR = re.compile(
    "no exact closure for physical LC sector|LC topology replay materialized sector"
)


def _has_external_gluon(process: str) -> bool:
    return " g " in f" {process} "


@pytest.mark.loop_nightly
@pytest.mark.parametrize(
    ("restriction", "process", "lane", "accuracy"), _nightly_cases()
)
def test_the_class_matches_madgraph_in_every_lane_nightly(
    sm_models, tmp_path: Path, restriction: str, process: str, lane: str, accuracy: str
) -> None:
    """Every reference process in every lane at leading and full colour: full
    colour and the leading colour of colour-singlet or gluon-free processes
    against MadGraph; leading colour with an external gluon against the eager
    lane."""

    reference = _reference(restriction, process, accuracy)
    model = sm_models(restriction)
    try:
        runtime = _runtime(
            model, process, tmp_path / "artifact", lane=lane, accuracy=accuracy
        )
    except GenerationError as error:
        if _EMPTY_LC_SECTOR.search(str(error)):
            pytest.xfail("an empty leading-colour sector (separate open item)")
        raise
    values = _values(runtime, reference["points"])
    if accuracy == "lc" and _has_external_gluon(process):
        if lane == "eager":
            return
        eager = _runtime(
            model, process, tmp_path / "eager", lane="eager", accuracy="lc"
        )
        _assert_close(values, _values(eager, reference["points"]))
        return
    _assert_close(values, reference["total"])
