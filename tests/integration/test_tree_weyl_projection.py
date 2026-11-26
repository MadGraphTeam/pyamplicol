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
import math
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


# The projection is an identity over every parameter binding the runtime
# admits, not only the generation's values: a chiral half may be dropped only
# where it vanishes for all of them. A copy of the shipped sm whose tau-line W
# couplings get a vector term proportional to MT - 173 (zero at the default
# MT, but MT stays a runtime parameter) keeps the full neutrino current.
def _mt_dependent_vector_sm(destination: Path) -> Path:
    shipped = Path(str(resources.files("pyamplicol").joinpath("assets/models/ufo/sm")))
    shutil.copytree(shipped, destination, ignore=shutil.ignore_patterns("__pycache__"))
    couplings = destination / "couplings.py"
    couplings.write_text(
        couplings.read_text(encoding="utf-8") + "\nGC_MTV = Coupling(name = 'GC_MTV',\n"
        "                 value = '(MT - 173.)*(ee*complex(0,1))/(sw*cmath.sqrt(2))',\n"
        "                 order = {'QED':1})\n",
        encoding="utf-8",
    )
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
            r"\1lorentz = [ L.FFV2, L.FFV1 ],\2couplings = {(0,0):C.\3,(0,1):C.GC_MTV}",
            text,
        )
        edited += count
    assert edited == 2
    path.write_text(text, encoding="utf-8")
    card = (destination / "restrict_default.dat").read_text(encoding="utf-8")
    assert "    6 1.730000e+02 # MT" in card
    (destination / "restrict_mt174.dat").write_text(
        card.replace("    6 1.730000e+02 # MT", "    6 1.740000e+02 # MT"),
        encoding="utf-8",
    )
    return destination


def _prepared_at_173_and_174(
    root: Path, source: Path, *, simplify: bool
) -> dict[str, ModelSource]:
    built = {}
    for mass, restriction in (
        ("173", "default"),
        ("174", source / "restrict_mt174.dat"),
    ):
        bundle = root / f"mt{mass}.pyamplicol-model"
        ModelSource.from_path(
            source, restriction=restriction, simplify=simplify
        ).compile(
            cache_dir=root / "cache",
            prepared_output=bundle,
            evaluator=EvaluatorConfig(),
        )
        built[mass] = ModelSource.from_path(bundle)
    return built


@pytest.fixture(scope="module")
def mt_vector_models(tmp_path_factory: pytest.TempPathFactory):
    """The MT-dependent model prepared at MT = 173 (the vector term vanishes)
    and at MT = 174, with simplification off (the restriction keeps the
    coupling)."""

    root = tmp_path_factory.mktemp("sm-mt-vector")
    source = _mt_dependent_vector_sm(root / "sm_mt_vector")
    return _prepared_at_173_and_174(root, source, simplify=False)


@pytest.fixture(scope="module")
def simplified_mt_vector_models(tmp_path_factory: pytest.TempPathFactory):
    """The same model with the default restriction simplification, which
    removes the vector coupling at MT = 173 (and records its guard)."""

    root = tmp_path_factory.mktemp("sm-mt-vector-simplified")
    source = _mt_dependent_vector_sm(root / "sm_mt_vector")
    return _prepared_at_173_and_174(root, source, simplify=True)


def _parameter_value(runtime: Runtime, name: str) -> float:
    (value,) = (
        parameter.default_real
        for parameter in runtime.physics.model_parameters
        if parameter.name == name
    )
    return value


def _w_mass(runtime: Runtime) -> float:
    mz = _parameter_value(runtime, "MZ")
    alpha = 1 / _parameter_value(runtime, "aEWM1")
    gf = _parameter_value(runtime, "Gf")
    return math.sqrt(
        mz**2 / 2 + math.sqrt(mz**4 / 4 - alpha * math.pi * mz**2 / (gf * math.sqrt(2)))
    )


def _tau_pair_to_w_pair_points(runtime: Runtime) -> list:
    mta, mw = _parameter_value(runtime, "MTA"), _w_mass(runtime)
    root = 1000.0
    p = math.sqrt(root**2 / 4 - mta**2)
    q = math.sqrt(root**2 / 4 - mw**2)
    points = []
    for cosine in (0.3, -0.7):
        sine = math.sqrt(1 - cosine * cosine)
        v = [q * sine * 0.6, q * sine * 0.8, q * cosine]
        points.append(
            [
                [root / 2, 0.0, 0.0, p],
                [root / 2, 0.0, 0.0, -p],
                [root / 2, *v],
                [root / 2, *(-x for x in v)],
            ]
        )
    return points


def _full_index(pdg: int) -> object:
    """A full (chirality-0) current of ``pdg`` as the model's flow probes take
    it."""

    from types import SimpleNamespace

    return SimpleNamespace(
        particle_id=pdg, pdg=pdg, chirality=0, flavour_flow=(pdg,), coupling_orders=()
    )


def test_a_coupling_zero_only_at_the_defaults_keeps_the_full_current(
    mt_vector_models,
) -> None:
    """The tau-line W vertex of the MT-dependent model has both chiral
    projections over the admitted bindings, so a full tau current into the
    neutrino stays full at MT = 173, where its vector half vanishes."""

    from pyamplicol.models.external import CompiledUFOModel
    from pyamplicol.models.loading import load_compiled_model

    model = CompiledUFOModel(load_compiled_model(mt_vector_models["173"].path))
    (vertex,) = (v for v in model.vertices if v.particles == (15, 24, 16))
    full = [_full_index(pdg) for pdg in (15, 24)]
    assert [f.chirality for f in model.allowed_quantum_flows(vertex, *full)] == [0]


def test_the_shipped_w_still_projects(sm_models) -> None:
    """The shipped sm's W (a structural left-handed projector) still
    projects."""

    from pyamplicol.models.external import CompiledUFOModel
    from pyamplicol.models.loading import load_compiled_model

    model = CompiledUFOModel(load_compiled_model(sm_models("default").path))
    (vertex,) = (v for v in model.vertices if v.particles == (15, 24, 16))
    full = [_full_index(pdg) for pdg in (15, 24)]
    chiralities = tuple(f.chirality for f in model.allowed_quantum_flows(vertex, *full))
    assert chiralities in ((-1,), (1,))


@pytest.mark.parametrize(
    ("lane", "accuracy"), [("compiled", "full"), ("recurrence", "lc")]
)
def test_a_runtime_parameter_update_equals_a_fresh_generation(
    mt_vector_models, tmp_path: Path, lane: str, accuracy: str
) -> None:
    """ta- ta+ > w- w+ (a neutrino t channel through the tau-line W):
    the artifact prepared at MT = 173 and evaluated at MT = 174 equals the
    artifact prepared at MT = 174. With the vector half dropped at MT = 173
    the two differed by 1.5x; in the recurrence lane the coupling, an
    imaginary derived parameter that is zero at MT = 173, also had only a
    real runtime component."""

    process = "ta- ta+ > w- w+"
    at_173 = _runtime(
        mt_vector_models["173"], process, tmp_path / "a173", lane=lane,
        accuracy=accuracy,
    )  # fmt: skip
    at_174 = _runtime(
        mt_vector_models["174"], process, tmp_path / "a174", lane=lane,
        accuracy=accuracy,
    )  # fmt: skip
    points = _tau_pair_to_w_pair_points(at_174)
    before = _values(at_173, points)
    at_173.set_model_parameters({"MT": 174.0})
    updated = _values(at_173, points)
    fresh = _values(at_174, points)
    _assert_close(updated, fresh)
    assert all(abs(u - b) > 1e-3 * abs(b) for u, b in zip(updated, before, strict=True))


def test_a_line_through_a_coupling_zero_only_at_the_defaults_is_refused(
    mt_vector_models, tmp_path: Path
) -> None:
    """vt vt~ > ta+ ta- closes the full neutrino current on the Weyl
    neutrino: refused, as for any vertex with both chiral projections."""

    with pytest.raises(GenerationError, match=r"dirac-weyl-closure:.*both chiral"):
        _runtime(mt_vector_models["173"], "vt vt~ > ta+ ta-", tmp_path / "a")


_GUARDED_LANES = [
    ("compiled", "full"),
    ("eager", "full"),
    ("recurrence", "lc"),
    ("recurrence", "full"),
    ("on-the-fly", "lc"),
]


@pytest.mark.parametrize(("lane", "accuracy"), _GUARDED_LANES)
def test_a_simplified_artifact_refuses_the_update_that_revives_the_coupling(
    simplified_mt_vector_models, tmp_path: Path, lane: str, accuracy: str
) -> None:
    """Under the default restriction simplification the vector coupling,
    zero at MT = 173, is removed with its specialisation guard: the 173
    artifact refuses MT = 174 (it gave 0.054 instead of 678.5) and keeps its
    binding; the 174 artifact has the coupling."""

    process = "ta- ta+ > w- w+"
    models = simplified_mt_vector_models
    at_173 = _runtime(
        models["173"], process, tmp_path / "a173", lane=lane, accuracy=accuracy
    )
    at_174 = _runtime(
        models["174"], process, tmp_path / "a174", lane=lane, accuracy=accuracy
    )
    points = _tau_pair_to_w_pair_points(at_174)
    before = _values(at_173, points)
    with pytest.raises(Exception, match=r"specialisation-guard: binding MT.*GC_MTV"):
        at_173.set_model_parameters({"MT": 174.0})
    assert _values(at_173, points) == before
    fresh = _values(at_174, points)
    assert all(abs(f - b) > 1e-3 * abs(b) for f, b in zip(fresh, before, strict=True))


@pytest.mark.parametrize(
    ("lane", "accuracy"), [("recurrence", "lc"), ("eager", "full")]
)
def test_a_simplified_line_through_the_removed_coupling_refuses_its_revival(
    simplified_mt_vector_models, tmp_path: Path, lane: str, accuracy: str
) -> None:
    """vt vt~ > ta+ ta-: at MT = 173 the simplified model's W is purely
    left-handed and the line builds; MT = 174 would revive the right-handed
    half the line was built without, and is refused. Generated at 174 the
    line meets both chiral projections and is refused at generation."""

    process = "vt vt~ > ta+ ta-"
    runtime = _runtime(
        simplified_mt_vector_models["173"],
        process,
        tmp_path / "a173",
        lane=lane,
        accuracy=accuracy,
    )
    with pytest.raises(Exception, match=r"specialisation-guard: binding MT.*GC_MTV"):
        runtime.set_model_parameters({"MT": 174.0})
    with pytest.raises(GenerationError, match=r"dirac-weyl-closure:.*both chiral"):
        _runtime(
            simplified_mt_vector_models["174"],
            process,
            tmp_path / "a174",
            lane=lane,
            accuracy=accuracy,
        )


# A derived parameter the recurrence template holds real (one runtime
# component: its default is real and not zero) must stay real at every
# binding the template lanes accept. A copy of the shipped sm whose tau-line
# W couplings get an imaginary part proportional to MT - 173 (the W stays
# purely left-handed, so the projection is unaffected): the coupling is real
# only at MT = 173.
def _mt_dependent_phase_sm(destination: Path) -> Path:
    shipped = Path(str(resources.files("pyamplicol").joinpath("assets/models/ufo/sm")))
    shutil.copytree(shipped, destination, ignore=shutil.ignore_patterns("__pycache__"))
    couplings = destination / "couplings.py"
    text = couplings.read_text(encoding="utf-8")
    path = destination / "vertices.py"
    vertices = path.read_text(encoding="utf-8")
    for index, (particles, sign) in enumerate(
        (
            ("P.vt__tilde__, P.ta__minus__, P.W__plus__", "1"),
            ("P.ta__plus__, P.vt, P.W__minus__", "-1"),
        )
    ):
        pattern = re.compile(
            r"(particles = \[ "
            + re.escape(particles)
            + r" \],\n\s*color = \[ '1' \],\n\s*lorentz = \[ L\.FFV2 \],"
            r"\n\s*couplings = \{\(0,0\):C\.)GC_\d+"
        )
        vertices, count = pattern.subn(rf"\g<1>GC_MTR{index}", vertices)
        assert count == 1
        text += (
            f"\nGC_MTR{index} = Coupling(name = 'GC_MTR{index}',\n"
            f"                 value = '({sign}+complex(0,1)*(MT-173.))*ee"
            "/(sw*cmath.sqrt(2))',\n"
            "                 order = {'QED':1})\n"
        )
    couplings.write_text(text, encoding="utf-8")
    path.write_text(vertices, encoding="utf-8")
    card = (destination / "restrict_default.dat").read_text(encoding="utf-8")
    (destination / "restrict_mt174.dat").write_text(
        card.replace("    6 1.730000e+02 # MT", "    6 1.740000e+02 # MT"),
        encoding="utf-8",
    )
    return destination


@pytest.fixture(scope="module")
def mt_phase_models(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("sm-mt-phase")
    source = _mt_dependent_phase_sm(root / "sm_mt_phase")
    return _prepared_at_173_and_174(root, source, simplify=True)


@pytest.mark.parametrize(
    ("lane", "accuracy"),
    [("recurrence", "lc"), ("recurrence", "full"), ("on-the-fly", "lc")],
)
def test_a_template_lane_follows_a_binding_that_makes_a_coupling_complex(
    mt_phase_models, tmp_path: Path, lane: str, accuracy: str
) -> None:
    """vt e- > ve ta-: the template lanes held the coupling real (its
    default is real) and gave the MT = 173 value after MT = 174, half the
    right one. The template now types a derived parameter real only where the
    model proves it real, so the 173 artifact bound to 174 equals the 174
    artifact and the eager lane."""

    process = "vt e- > ve ta-"
    points = _reference("default", process)["points"]
    at_173 = _runtime(
        mt_phase_models["173"], process, tmp_path / "a173", lane=lane, accuracy=accuracy
    )
    before = _values(at_173, points)
    at_173.set_model_parameters({"MT": 174.0})
    updated = _values(at_173, points)
    fresh = _values(
        _runtime(
            mt_phase_models["174"],
            process,
            tmp_path / "a174",
            lane=lane,
            accuracy=accuracy,
        ),
        points,
    )
    eager = _runtime(
        mt_phase_models["174"],
        process,
        tmp_path / "e174",
        lane="eager",
        accuracy="full",
    )
    _assert_close(updated, fresh)
    _assert_close(fresh, _values(eager, points))
    assert all(abs(u - b) > 0.5 * abs(b) for u, b in zip(updated, before, strict=True))


@pytest.mark.parametrize("lane", ["eager", "compiled"])
def test_the_complex_typed_lanes_follow_the_binding(
    mt_phase_models, tmp_path: Path, lane: str
) -> None:
    """The eager and compiled lanes evaluate the coupling as complex: the
    173 artifact updated to MT = 174 equals the 174 artifact."""

    process = "vt e- > ve ta-"
    points = _reference("default", process)["points"]
    at_173 = _runtime(
        mt_phase_models["173"], process, tmp_path / "a173", lane=lane, accuracy="full"
    )
    at_173.set_model_parameters({"MT": 174.0})
    at_174 = _runtime(
        mt_phase_models["174"], process, tmp_path / "a174", lane=lane, accuracy="full"
    )
    _assert_close(_values(at_173, points), _values(at_174, points))


# A template with paired rows (a projection and its full-state counterpart)
# carries the execution ABI, which readers that ignore the markers refuse
# (they compare the ABI with the plain one); a template without them keeps
# the plain ABI, and a model loaded with such a pack keeps the full results
# the pack was built for.
_PLAIN_TEMPLATE_ABI = "pyamplicol-recurrence-template-v1"


def test_paired_rows_carry_an_abi_the_plain_reader_refuses(sm_models) -> None:
    from pyamplicol.models.prepared import load_prepared_model_bundle
    from pyamplicol.models.recurrence_template import (
        RECURRENCE_TEMPLATE_EXECUTION_ABI,
        RecurrenceTemplateCatalog,
        RecurrenceTemplateError,
    )

    pack = load_prepared_model_bundle(sm_models("default").path).kernel_pack
    template = json.loads(json.dumps(pack.recurrence_template, default=dict))
    header = dict(template["header"])
    assert header["abi"] == RECURRENCE_TEMPLATE_EXECUTION_ABI != _PLAIN_TEMPLATE_ABI
    assert pack.provenance["recurrence_template_abi"] == header["abi"]
    # Relabelled with the plain ABI the catalog is refused: no reader takes
    # marked rows as plain ones.
    template["header"] = {**header, "abi": _PLAIN_TEMPLATE_ABI}
    with pytest.raises(RecurrenceTemplateError, match="does not match its transitions"):
        RecurrenceTemplateCatalog.from_dict(template)


def test_a_pack_without_paired_rows_keeps_the_full_results(sm_models) -> None:
    """A model whose prepared pack has the plain ABI (prepared before the
    projection) keeps the full result of full inputs, which that pack has
    kernels for; without a pack, or with the execution ABI, it projects."""

    from dataclasses import replace
    from types import SimpleNamespace

    from pyamplicol.models.external import CompiledUFOModel
    from pyamplicol.models.loading import load_compiled_model

    compiled = load_compiled_model(sm_models("default").path)
    old_pack = SimpleNamespace(
        kernel_pack=SimpleNamespace(
            recurrence_template={"header": {"abi": _PLAIN_TEMPLATE_ABI}}
        )
    )
    full = [_full_index(pdg) for pdg in (15, 24)]
    for bundle, expected in (
        (old_pack, ((0,),)),
        (None, ((-1,), (1,))),
        (compiled.prepared_bundle, ((-1,), (1,))),
    ):
        model = CompiledUFOModel(replace(compiled, _prepared_bundle=bundle))
        (vertex,) = (v for v in model.vertices if v.particles == (15, 24, 16))
        flows = model.allowed_quantum_flows(vertex, *full)
        assert tuple(flow.chirality for flow in flows) in expected
