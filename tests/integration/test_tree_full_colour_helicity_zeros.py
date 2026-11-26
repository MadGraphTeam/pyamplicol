# SPDX-License-Identifier: 0BSD
"""Full colour where a colour flow vanishes for some helicities only.

In ``u u~ > d d~`` at QCD = 0 the photon and Z join the u line to the d line
in one colour flow for every helicity, while the W pairing (the other flow)
exists only for left-handed quarks. The full-colour primary plan of the
recurrence lane keeps one colour group per (sector, helicity) with diagrams,
so its reducer has incomplete per-sector helicity blocks. Every helicity
selection at full colour (one helicity, a subset, per point) runs on the
helicity-selector companion, which reads that reducer through a sparse
local-colour view (``primary-sparse-local-color-view-v1``, refused by
released readers): one local group per active owner sector and, as local
colour matrix, the union of the per-component entries. The companion computes
every sector at its runtime helicity itself.

The references are MadGraph 3.7.0 standalone, UFO ``sm`` default restriction,
t-channel widths kept, at RAMBO points (sqrt(s) = 1000 GeV, seeds 9001 and
9002), with amplitude-level coupling-order limits (``QCD<=n`` in the process),
from ``tools/developer/madgraph_split_orders.py``: full colour in
``madgraph-helicity-dependent-zeros.json``, leading colour in
``madgraph-helicity-dependent-zeros-lc.json``.

A zero of such a block is decided at generation: chirality on massless lines
(their masses are no runtime parameters) and chiral couplings. A coupling that
vanishes only at the card values is removed by restriction simplification
and recorded as a specialisation guard, so a binding that would revive the
missing helicities is refused (the right-handed W term below).
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from pyamplicol import Generator, ModelSource, Runtime
from pyamplicol.api.errors import EvaluationError
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
REFERENCE = FIXTURES / "madgraph-helicity-dependent-zeros.json"
LC_REFERENCE = FIXTURES / "madgraph-helicity-dependent-zeros-lc.json"
SPARSE_VIEW = "primary-sparse-local-color-view-v1"


def _references(path: Path) -> dict[str, dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {entry["process"]: entry for entry in payload["processes"]}


def _split(key: str) -> tuple[str, dict[str, int]]:
    match = re.fullmatch(r"(.*?)(?: QCD<=(\d+))?", key)
    process, qcd = match.group(1), match.group(2)
    return process, {"QCD": 99 if qcd is None else int(qcd), "QED": 99}


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


def _runtime(
    model: ModelSource,
    process: str,
    artifact: Path,
    *,
    accuracy: str = "full",
    execution_mode: str = "recurrence",
    limits: dict[str, int],
) -> Runtime:
    config = RunConfig(
        action="generate",
        model=ModelConfig(cache=False),
        color=ColorConfig(accuracy=accuracy),
        process=ProcessConfig(
            coupling_order_policy="explicit", max_coupling_orders=limits
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
            execution_mode=execution_mode,
            optimization=EvaluatorOptimizationConfig(cores=1),
        ),
    )
    Generator(config).generate(process, artifact, model=model)
    return Runtime.load(artifact)


def _real(values) -> list[float]:
    return [complex(value).real for value in values]


def _declares_sparse_view(artifact: Path) -> bool:
    return any(
        SPARSE_VIEW in path.read_text(encoding="utf-8", errors="ignore")
        for path in artifact.rglob("*.json")
    )


def _check_against_madgraph(
    model: ModelSource, tmp_path: Path, key: str, accuracy: str
) -> Runtime:
    entry = _references(REFERENCE if accuracy == "full" else LC_REFERENCE)[key]
    process, limits = _split(key)
    runtime = _runtime(
        model, process, tmp_path / accuracy, accuracy=accuracy, limits=limits
    )
    for point, (value, expected) in enumerate(
        zip(_real(runtime.evaluate(entry["points"])), entry["total"], strict=True)
    ):
        assert value == pytest.approx(expected, rel=1e-10, abs=0.0), point
    return runtime


def _check_helicity_selection(
    runtime: Runtime, reference: Runtime, points, total: list[float]
) -> None:
    """Every helicity alone, a subset and a per-point selection against a lane
    without a helicity-selector companion; the resolved rows sum to the
    total."""

    scale = max(abs(value) for value in total)
    helicities = list(reference.evaluate_resolved(points).helicity_ids)
    singles = {}
    for helicity in helicities:
        expected = _real(reference.evaluate(points, helicities=[helicity]))
        found = _real(runtime.evaluate(points, helicities=[helicity]))
        singles[helicity] = expected
        for value, wanted in zip(found, expected, strict=True):
            assert abs(value - wanted) <= 1e-12 * scale, helicity
            if wanted == 0.0:
                assert value == 0.0, helicity
    assert any(all(value == 0.0 for value in singles[h]) for h in helicities)
    subset = helicities[: len(helicities) // 2]
    found = _real(runtime.evaluate(points, helicities=subset))
    expected = [sum(singles[h][point] for h in subset) for point in range(len(points))]
    assert found == pytest.approx(expected, rel=1e-12, abs=1e-12 * scale)
    by_point = [helicities[0], helicities[-1]][: len(points)]
    found = _real(runtime.evaluate(points, helicity_by_point=by_point))
    expected = [singles[h][point] for point, h in enumerate(by_point)]
    assert found == pytest.approx(expected, rel=1e-12, abs=1e-12 * scale)
    resolved = runtime.evaluate_resolved(points)
    sums = [
        sum(complex(value).real for row in point for value in row)
        for point in resolved.values
    ]
    assert sums == pytest.approx(total, rel=1e-12, abs=0.0)


@pytest.mark.parametrize("key", ["u u~ > d d~ QCD<=0", "u d > u d QCD<=0"])
def test_full_colour_with_a_helicity_dependent_zero_matches_madgraph(
    sm_model: ModelSource, tmp_path: Path, key: str
) -> None:
    """The recurrence lane refused these at full colour ("local-color view
    requires a direct, Walsh, or symmetric-group Fourier reducer"). The total
    matches MadGraph; every helicity selection matches the eager lane, a
    helicity whose amplitude vanishes is an exact zero; the companion declares
    the sparse view."""

    runtime = _check_against_madgraph(sm_model, tmp_path, key, "full")
    assert _declares_sparse_view(tmp_path / "full")
    process, limits = _split(key)
    eager = _runtime(
        sm_model, process, tmp_path / "eager", execution_mode="eager", limits=limits
    )
    points = _references(REFERENCE)[key]["points"]
    _check_helicity_selection(runtime, eager, points, _real(eager.evaluate(points)))


def test_the_built_in_sm_builds_them_at_full_colour(tmp_path: Path) -> None:
    """The same in the built-in SM with the default lane and policy, the
    request that was refused: every helicity selection against the eager
    lane."""

    limits = {"QCD": 0, "QED": 2}
    model = ModelSource.built_in_sm()
    entry = _references(REFERENCE)["u u~ > d d~ QCD<=0"]
    for process in ("u u~ > d d~", "u d > u d"):
        root = tmp_path / process.replace(" ", "_").replace(">", "to")
        runtime = _runtime(model, process, root / "recurrence", limits=limits)
        eager = _runtime(
            model, process, root / "eager", execution_mode="eager", limits=limits
        )
        total = _real(eager.evaluate(entry["points"]))
        assert _real(runtime.evaluate(entry["points"])) == pytest.approx(
            total, rel=1e-12, abs=0.0
        )
        _check_helicity_selection(runtime, eager, entry["points"], total)


def test_complete_helicity_blocks_keep_their_view(
    sm_model: ModelSource, tmp_path: Path
) -> None:
    """Only a primary reducer with incomplete blocks takes the sparse view; at
    all orders u u~ > d d~ (gluon exchange in both flows) keeps the dense view
    and its artifact as before."""

    _runtime(sm_model, "u u~ > d d~", tmp_path / "all", limits={"QCD": 99, "QED": 99})
    assert not _declares_sparse_view(tmp_path / "all")


def _right_handed_w_model(root: Path, madgraph_source: Path, mt: int) -> Path:
    """The UFO sm with a right-handed term on both udW vertices whose coupling
    is the left-handed one times (MT - 173); MT set to ``mt`` on the default
    restriction card."""

    model = root / f"sm-rh-mt{mt}"
    shutil.copytree(
        madgraph_source / "models/sm",
        model,
        ignore=shutil.ignore_patterns("__pycache__", "*.pkl"),
    )
    lorentz = model / "lorentz.py"
    lorentz.write_text(
        lorentz.read_text(encoding="utf-8") + "\nFFVR = Lorentz(name = 'FFVR',\n"
        "               spins = [ 2, 2, 3 ],\n"
        "               structure = 'Gamma(3,2,-1)*ProjP(-1,1)')\n",
        encoding="utf-8",
    )
    couplings = model / "couplings.py"
    text = couplings.read_text(encoding="utf-8")
    for name in ("41", "100"):
        value = re.search(
            rf"GC_{name} = Coupling\(name = 'GC_{name}',\s+value = '([^']+)'", text
        ).group(1)
        text += (
            f"\nGC_{name}R = Coupling(name = 'GC_{name}R',\n"
            f"                 value = '(MT-173)*({value})',\n"
            "                 order = {'QED':1})\n"
        )
    couplings.write_text(text, encoding="utf-8")
    vertices = model / "vertices.py"
    text = vertices.read_text(encoding="utf-8")
    for name in ("41", "100"):
        text, count = re.subn(
            rf"lorentz = \[ L\.FFV2 \],(\s+)couplings = \{{\(0,0\):C\.GC_{name}\}}\)",
            rf"lorentz = [ L.FFV2, L.FFVR ],\g<1>couplings = "
            rf"{{(0,0):C.GC_{name},(0,1):C.GC_{name}R}})",
            text,
        )
        assert count == 1
    vertices.write_text(text, encoding="utf-8")
    card = model / "restrict_default.dat"
    text = card.read_text(encoding="utf-8")
    assert "1.730000e+02 # MT " in text
    card.write_text(text.replace("1.730000e+02 # MT ", f"{mt}.0 # MT "))
    return model


def test_a_binding_that_revives_missing_helicities_is_refused(
    madgraph_source: Path, tmp_path: Path
) -> None:
    """A right-handed W term proportional to MT - 173 vanishes at MT = 173,
    where restriction simplification removes it: the W pairing of
    u u~ > d d~ at QCD = 0 then has left-handed groups only. The removal is a
    specialisation guard on MT, so a binding of MT away from 173 is refused
    (at load and in set_model_parameters) instead of serving the missing
    right-handed helicities as zeros; an artifact generated at MT = 174 has
    them, and its right-handed W helicities are nonzero."""

    limits = {"QCD": 0, "QED": 2}
    runtimes = {}
    for mt in (173, 174):
        source = _right_handed_w_model(tmp_path, madgraph_source, mt)
        bundle = tmp_path / f"sm-rh-{mt}.pyamplicol-model"
        ModelSource.from_path(source, restriction="default").compile(
            cache_dir=tmp_path / "cache",
            prepared_output=bundle,
            evaluator=EvaluatorConfig(),
        )
        runtimes[mt] = _runtime(
            ModelSource.from_path(bundle),
            "u u~ > d d~",
            tmp_path / f"at-{mt}",
            limits=limits,
        )
    entry = _references(REFERENCE)["u u~ > d d~ QCD<=0"]
    points = entry["points"]
    at_173 = _real(runtimes[173].evaluate(points))
    # At MT = 173 the model is the shipped sm: MadGraph's value.
    assert at_173 == pytest.approx(entry["total"], rel=1e-10, abs=0.0)
    refusal = "specialisation-guard: binding MT"
    with pytest.raises(EvaluationError, match=refusal):
        runtimes[173].set_model_parameters({"MT": 174.0})
    assert _real(runtimes[173].evaluate(points)) == at_173
    with pytest.raises(EvaluationError, match=refusal):
        Runtime.load(tmp_path / "at-173", model_parameters={"MT": 174.0})
    # Generated at 174, the right-handed W helicities contribute: helicities
    # zero at 173 are not zero at 174.
    helicities = list(runtimes[174].evaluate_resolved(points).helicity_ids)
    revived = [
        helicity
        for helicity in helicities
        if all(
            v == 0.0
            for v in _real(runtimes[173].evaluate(points, helicities=[helicity]))
        )
        and any(
            v != 0.0
            for v in _real(runtimes[174].evaluate(points, helicities=[helicity]))
        )
    ]
    assert revived
    runtimes[174].set_model_parameters({"MT": 173.0})
    assert _real(runtimes[174].evaluate(points)) == pytest.approx(
        at_173, rel=1e-12, abs=0.0
    )


@pytest.mark.loop_nightly
@pytest.mark.parametrize("accuracy", ["lc", "full"])
@pytest.mark.parametrize("key", sorted(_references(REFERENCE)))
def test_every_reference_matches_madgraph(
    sm_model: ModelSource, tmp_path: Path, key: str, accuracy: str
) -> None:
    """The whole set at both accuracies in the recurrence lane."""

    _check_against_madgraph(sm_model, tmp_path, key, accuracy)
