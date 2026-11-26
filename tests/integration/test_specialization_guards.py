# SPDX-License-Identifier: 0BSD
"""Specialisation guards end to end: a runtime binding that invalidates what
restriction simplification removed is refused in every tree lane.

The model is a copy of the shipped ``sm`` UFO whose tau-neutrino W vertices
get a vector term proportional to ``MT - 173``. Restriction simplification at
``MT = 173`` removes that coupling (its value is zero) although ``MT`` stays a
runtime parameter; before the guards, ``set_model_parameters({"MT": 174})``
evaluated the specialised model (``ta- ta+ > w- w+`` was off by four orders of
magnitude). The artifact generated at 173 now refuses that binding and keeps
its state; one generated at 174 evaluates the coupling.
"""

from __future__ import annotations

import math
import re
import shutil
from importlib import resources
from pathlib import Path

import pytest

pytest.importorskip("symbolica")

from pyamplicol import Generator, ModelSource, Runtime
from pyamplicol.artifacts.manifest import load_manifest
from pyamplicol.config import (
    ColorConfig,
    EvaluatorConfig,
    EvaluatorOptimizationConfig,
    GenerationConfig,
    GenerationRelationDiscoveryConfig,
    GenerationValidationConfig,
    ModelConfig,
    RunConfig,
)
from pyamplicol.models.specialization_guards import (
    GUARD_FILE_PATH,
    GUARD_PAYLOAD_ROLE,
)

PROCESS = "ta- ta+ > w- w+"
LANES = (
    ("recurrence", "lc"),
    ("recurrence", "full"),
    ("compiled", "full"),
    ("eager", "full"),
    ("on-the-fly", "lc"),
)


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


@pytest.fixture(scope="module")
def simplified_models(tmp_path_factory: pytest.TempPathFactory):
    """The model prepared with restriction simplification at MT = 173 (the
    vector coupling is removed) and at MT = 174 (it is kept)."""

    root = tmp_path_factory.mktemp("sm-mt-vector-simplified")
    source = _mt_dependent_vector_sm(root / "sm_mt_vector")
    built = {}
    for mass, restriction in (
        (173, "default"),
        (174, source / "restrict_mt174.dat"),
    ):
        bundle = root / f"mt{mass}.pyamplicol-model"
        ModelSource.from_path(source, restriction=restriction, simplify=True).compile(
            cache_dir=root / "cache",
            prepared_output=bundle,
            evaluator=EvaluatorConfig(),
        )
        built[mass] = ModelSource.from_path(bundle)
    built["source"] = source
    return built


def _generate(model: ModelSource, artifact: Path, lane: str, accuracy: str) -> Runtime:
    config = RunConfig(
        action="generate",
        model=ModelConfig(cache=False),
        color=ColorConfig(accuracy=accuracy),
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
    Generator(config).generate(PROCESS, artifact, model=model)
    return Runtime.load(artifact)


def _points(runtime: Runtime) -> list[list[list[float]]]:
    values = {p.name: p.default_real for p in runtime.physics.model_parameters}
    mz, aew, gf = values["MZ"], 1 / values["aEWM1"], values["Gf"]
    mw = math.sqrt(
        mz**2 / 2 + math.sqrt(mz**4 / 4 - (aew * math.pi * mz**2) / (gf * math.sqrt(2)))
    )
    energy = 500.0
    beam = math.sqrt(energy**2 - values["MTA"] ** 2)
    q = math.sqrt(energy**2 - mw**2)
    return [
        [
            [energy, 0.0, 0.0, beam],
            [energy, 0.0, 0.0, -beam],
            [energy, q * s, 0.0, q * c],
            [energy, -q * s, 0.0, -q * c],
        ]
        for s, c in ((0.8, 0.6), (0.28, 0.96))
    ]


def _values(runtime: Runtime, points) -> list[float]:
    return [complex(value).real for value in runtime.evaluate(points)]


def test_restriction_simplification_records_the_removed_coupling(
    simplified_models, tmp_path: Path
) -> None:
    from pyamplicol.models.loading import compile_model_source

    source = simplified_models["source"]
    compiled = compile_model_source(source, simplify=True, cache_dir=tmp_path)
    (guard,) = compiled.specialization_guards
    assert guard.kind == "vanishing"
    assert guard.subject == "coupling GC_MTV removed by restriction simplification"
    assert "MT" in guard.parameters
    # At 174 the coupling is not zero, so nothing is removed or recorded.
    at_174 = compile_model_source(
        source,
        restriction=str(source / "restrict_mt174.dat"),
        simplify=True,
        cache_dir=tmp_path,
    )
    assert at_174.specialization_guards == ()


@pytest.mark.parametrize(("lane", "accuracy"), LANES)
def test_a_binding_that_revives_a_removed_coupling_is_refused(
    simplified_models, tmp_path: Path, lane: str, accuracy: str
) -> None:
    runtime = _generate(simplified_models[173], tmp_path / "173", lane, accuracy)
    manifest = load_manifest(tmp_path / "173")
    assert [r.path for r in manifest.payloads if r.role == GUARD_PAYLOAD_ROLE] == [
        GUARD_FILE_PATH
    ]
    points = _points(runtime)
    before = _values(runtime, points)
    with pytest.raises(Exception, match="specialisation-guard: binding MT") as error:
        runtime.set_model_parameters({"MT": 174.0})
    assert "GC_MTV" in str(error.value)
    # A refused binding applies nothing.
    assert _values(runtime, points) == before
    # Bindings that keep the coupling zero are accepted.
    runtime.set_model_parameters({"MT": 173.0})
    runtime.set_model_parameters({"WW": 2.1})
    fresh = _generate(simplified_models[174], tmp_path / "174", lane, accuracy)
    at_174 = _values(fresh, points)
    assert all(math.isfinite(value) for value in at_174)
    assert all(abs(a - b) > 1e-3 * abs(b) for a, b in zip(before, at_174, strict=True))


def test_an_unguarded_model_writes_no_guard_payload(tmp_path: Path) -> None:
    _generate(ModelSource.built_in_sm(), tmp_path / "a", "recurrence", "lc")
    manifest = load_manifest(tmp_path / "a")
    assert all(record.role != GUARD_PAYLOAD_ROLE for record in manifest.payloads)
