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

import json
import math
import re
import shutil
from decimal import Decimal
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


def _mt_dependent_vector_sm(destination: Path, factor: str = "(MT - 173.)") -> Path:
    shipped = Path(str(resources.files("pyamplicol").joinpath("assets/models/ufo/sm")))
    shutil.copytree(shipped, destination, ignore=shutil.ignore_patterns("__pycache__"))
    couplings = destination / "couplings.py"
    couplings.write_text(
        couplings.read_text(encoding="utf-8") + "\nGC_MTV = Coupling(name = 'GC_MTV',\n"
        f"                 value = '{factor}*(ee*complex(0,1))/(sw*cmath.sqrt(2))',\n"
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


def _prepared_at_173_and_174(root: Path, source: Path) -> dict[object, object]:
    built: dict[object, object] = {}
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


@pytest.fixture(scope="module")
def simplified_models(tmp_path_factory: pytest.TempPathFactory):
    """The model prepared with restriction simplification at MT = 173 (the
    vector coupling is removed) and at MT = 174 (it is kept)."""

    root = tmp_path_factory.mktemp("sm-mt-vector-simplified")
    return _prepared_at_173_and_174(root, _mt_dependent_vector_sm(root / "sm_mt"))


@pytest.fixture(scope="module")
def sixth_power_models(tmp_path_factory: pytest.TempPathFactory):
    """The same with the factor (MT - 173)^6: exactly 1 at MT = 174, an
    ordinary W-strength coupling that a rounding allowance on the expression
    (64 u x 347^6 > 12) accepted."""

    root = tmp_path_factory.mktemp("sm-mt-sixth-power")
    source = _mt_dependent_vector_sm(root / "sm_mt6", factor="(MT - 173.)**6")
    return _prepared_at_173_and_174(root, source)


def _generate(
    model: ModelSource,
    artifact: Path,
    lane: str,
    accuracy: str,
    process: str = PROCESS,
) -> Runtime:
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
    Generator(config).generate(process, artifact, model=model)
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


@pytest.mark.parametrize(("lane", "accuracy"), LANES)
def test_a_sixth_power_zero_refuses_the_update_in_every_lane(
    sixth_power_models, tmp_path: Path, lane: str, accuracy: str
) -> None:
    runtime = _generate(sixth_power_models[173], tmp_path / "173", lane, accuracy)
    points = _points(runtime)
    before = _values(runtime, points)
    with pytest.raises(Exception, match="specialisation-guard: binding MT"):
        runtime.set_model_parameters({"MT": 174.0})
    assert _values(runtime, points) == before
    runtime.set_model_parameters({"MT": 173.0})
    fresh = _values(
        _generate(sixth_power_models[174], tmp_path / "174", lane, accuracy), points
    )
    # Fresh at 174 differs by orders of magnitude (482.7 against 0.133).
    assert all(f > 10 * b for f, b in zip(fresh, before, strict=True))


def _legacy(compiled) -> object:
    """``compiled`` as a pyAmpliCol without guards wrote it: no record of
    restriction simplification, no guards, the plain schema."""

    from dataclasses import replace

    return replace(compiled, specialization_guards=(), specialization_record=False)


def test_generation_refuses_a_legacy_simplified_compiled_model(
    simplified_models, tmp_path: Path
) -> None:
    from pyamplicol.models.loading import compile_model_source

    compiled = compile_model_source(
        simplified_models["source"], simplify=True, cache_dir=tmp_path / "cache"
    )
    assert compiled.specialization_record and compiled.specialization_guards
    legacy = _legacy(compiled)
    payload = legacy.to_dict()
    assert "specialization_record" not in payload
    assert "specialization_guards" not in payload
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(Exception, match="prepare or compile the model again"):
        _generate(ModelSource.from_path(path), tmp_path / "a", "recurrence", "lc")


def test_generation_refuses_a_legacy_simplified_prepared_model(
    simplified_models, tmp_path: Path
) -> None:
    from pyamplicol.models.loading import compile_model_source
    from pyamplicol.models.prepared_compile import prepare_model_bundle

    compiled = compile_model_source(
        simplified_models["source"], simplify=True, cache_dir=tmp_path / "cache"
    )
    bundle = tmp_path / "legacy.pyamplicol-model"
    prepare_model_bundle(_legacy(compiled), bundle, evaluator=EvaluatorConfig())
    for lane, accuracy in (("recurrence", "lc"), ("eager", "full")):
        with pytest.raises(Exception, match="prepare or compile the model again"):
            _generate(ModelSource.from_path(bundle), tmp_path / lane, lane, accuracy)


# The built-in SM exposes each vertex coupling component as a runtime
# parameter in the eager and compiled lanes. Where the chirality selection
# dropped the Weyl currents of a chirality because its component is zero (a W
# between massless leptons), that component holds at zero; where it dropped
# nothing (the W's t-b vertex: the Dirac top keeps both chiralities), the
# component is a working parameter.
_TWO_TO_TWO = {
    "e- ve~ > mu- vm~": (0.0, 0.0, 0.0, 0.0),
    "t b~ > u d~": (173.0, 0.0, 0.0, 0.0),
}


def _builtin_point(process: str) -> list[list[list[float]]]:
    m1, m2, m3, m4 = _TWO_TO_TWO[process]
    cm = 1000.0

    def pair(a_mass: float, b_mass: float, rotate: bool) -> list[list[float]]:
        a = (cm * cm + a_mass * a_mass - b_mass * b_mass) / (2 * cm)
        p = math.sqrt(a * a - a_mass * a_mass)
        c, s = (0.6, 0.8) if rotate else (1.0, 0.0)
        return [[a, p * s, 0.0, p * c], [cm - a, -p * s, 0.0, -p * c]]

    return [pair(m1, m2, False) + pair(m3, m4, True)]


def _builtin_with(component: tuple[int, tuple[int, ...], int, float] | None):
    """A context that generates the built-in SM with one vertex coupling
    component changed at generation (a fresh generation at that value)."""

    from contextlib import contextmanager
    from dataclasses import replace

    from pyamplicol.models.builtin.model import BuiltinSMModel

    @contextmanager
    def patched():
        if component is None:
            yield
            return
        kind, particles, index, value = component
        original = BuiltinSMModel._build_vertices

        def build(self):
            out = []
            for vertex in original(self):
                if (vertex.kind, tuple(vertex.particles)) == (kind, particles):
                    coupling = list(vertex.coupling)
                    coupling[index] = value
                    vertex = replace(vertex, coupling=tuple(coupling))
                out.append(vertex)
            return out

        BuiltinSMModel._build_vertices = build
        try:
            yield
        finally:
            BuiltinSMModel._build_vertices = original

    return patched()


@pytest.mark.parametrize("lane", ["eager", "compiled"])
def test_a_working_right_handed_top_coupling_stays_a_parameter(
    tmp_path: Path, lane: str
) -> None:
    process, name = "t b~ > u d~", "coupling.21.5_-6_-24.component_1"
    runtime = _generate(
        ModelSource.built_in_sm(), tmp_path / "a", lane, "full", process
    )
    point = _builtin_point(process)
    before = _values(runtime, point)
    runtime.set_model_parameters({name: 1.5})
    rebound = _values(runtime, point)
    assert rebound != before
    # The fresh generation runs the compiled lane (the eager lane reads the
    # packaged prepared pack, which has no kernel for the changed coupling).
    with _builtin_with((21, (5, -6, -24), 1, 1.5)):
        fresh = _values(
            _generate(
                ModelSource.built_in_sm(),
                tmp_path / "fresh",
                "compiled",
                "full",
                process,
            ),
            point,
        )
    for value, reference in zip(rebound, fresh, strict=True):
        assert abs(value - reference) <= 1e-12 * abs(reference)
    # The process's u-d W vertex (two massless quarks) is guarded; the t-b
    # component is not.
    guards = json.loads((tmp_path / "a" / GUARD_FILE_PATH).read_text(encoding="utf-8"))[
        "guards"
    ]
    held = {name for guard in guards for name in guard["parameters"]}
    assert name not in held
    assert len(held) == 1


@pytest.mark.parametrize("lane", ["eager", "compiled"])
def test_a_zero_chiral_coupling_of_a_massless_line_is_held_zero(
    tmp_path: Path, lane: str
) -> None:
    process = "e- ve~ > mu- vm~"
    runtime = _generate(
        ModelSource.built_in_sm(), tmp_path / "a", lane, "full", process
    )
    names = {
        parameter.name: parameter.default_real
        for parameter in runtime.physics.model_parameters
        if parameter.name.startswith("coupling.")
    }
    zero = [name for name, value in names.items() if value == 0.0]
    free = [name for name, value in names.items() if value != 0.0]
    assert zero and free
    point = _builtin_point(process)
    before = _values(runtime, point)
    with pytest.raises(
        Exception, match="specialisation-guard: binding coupling"
    ) as error:
        runtime.set_model_parameters({zero[0]: 1.5})
    assert "vertex-chiral-support" in str(error.value)
    assert _values(runtime, point) == before
    runtime.set_model_parameters({zero[0]: 0.0})
    runtime.set_model_parameters({name: 0.75 for name in free})
    assert _values(runtime, point) != before


# A coupling is removed by value only if it is exactly zero under every exact
# reading of the generation values: the decimal the one-loop runtime and the
# Python paths read, and the binary64 the native tree runtime promotes. A
# coupling zero under one reading only, or zero in binary64 by an order-one
# cancellation, is kept: the simplified and the unsimplified model then give
# the same amplitude at every precision.
_ELECTRON_Z = (
    "GC_24 = Coupling(name = 'GC_24',\n"
    "                 value = '(ee*complex(0,1)*sw)/(2.*cw)'"
)
_KEPT_FACTORS = {
    "decimal-only zero": "*(MZ-22797/250)*1000000000000000",
    "binary64 cancellation": "*200000000*(cmath.sqrt(10000000000000001)-100000000)",
}
_TREE_POINT = [
    [
        [250.0, 0.0, 0.0, 250.0],
        [250.0, 0.0, 0.0, -250.0],
        [250.0, 150.0, 0.0, 200.0],
        [250.0, -150.0, 0.0, -200.0],
    ]
]


@pytest.fixture(scope="module", params=sorted(_KEPT_FACTORS))
def kept_coupling_model(request, tmp_path_factory) -> Path:
    shipped = Path(
        str(resources.files("pyamplicol").joinpath("assets/models/ufo/loop_sm"))
    )
    destination = tmp_path_factory.mktemp("kept") / "loop_sm_kept"
    shutil.copytree(shipped, destination, ignore=shutil.ignore_patterns("__pycache__"))
    couplings = destination / "couplings.py"
    text = couplings.read_text(encoding="utf-8")
    assert text.count(_ELECTRON_Z) == 1
    couplings.write_text(
        text.replace(
            _ELECTRON_Z, _ELECTRON_Z[:-1] + _KEPT_FACTORS[request.param] + "'"
        ),
        encoding="utf-8",
    )
    return destination


def _real_part(value: object) -> Decimal:
    text = str(value).strip("()")
    match = re.match(r"[+-]?[0-9.]+(?:[eE][+-]?[0-9]+)?", text)
    assert match is not None, text
    return Decimal(match.group(0))


@pytest.mark.parametrize(("lane", "accuracy"), LANES)
def test_a_coupling_zero_under_one_reading_only_is_kept(
    kept_coupling_model, tmp_path: Path, lane: str, accuracy: str
) -> None:
    from pyamplicol.models.loading import compile_model_source

    compiled = compile_model_source(
        kept_coupling_model, simplify=True, cache_dir=tmp_path / "cache"
    )
    assert compiled.specialization_guards == ()
    assert any(c.get("name") == "GC_24" for c in compiled.model["couplings"])

    def values(runtime) -> dict[int, list[Decimal]]:
        return {
            digits: [
                _real_part(value)
                for value in runtime.evaluate(_TREE_POINT, precision=digits)
            ]
            for digits in (16, 32, 50)
        }

    # The simplified model (prepared) in this lane against the unsimplified
    # model in the compiled lane (an unsimplified loop_sm has no prepared
    # catalog on this base; the compiled lane needs none).
    bundle = tmp_path / "simplified.pyamplicol-model"
    ModelSource.from_path(kept_coupling_model, simplify=True).compile(
        cache_dir=tmp_path / "cache-s",
        prepared_output=bundle,
        evaluator=EvaluatorConfig(),
    )
    simplified = values(
        _generate(
            ModelSource.from_path(bundle),
            tmp_path / "s",
            lane,
            accuracy,
            "u u~ > e+ e-",
        )
    )
    reference = values(
        _generate(
            ModelSource.from_path(kept_coupling_model, simplify=False),
            tmp_path / "u",
            "compiled",
            "full",
            "u u~ > e+ e-",
        )
    )
    # Different lanes agree to their own extended-precision accuracy; the
    # pruned term the defect dropped changed the result by 7 %.
    tolerance = {16: Decimal("1e-12"), 32: Decimal("1e-22"), 50: Decimal("1e-40")}
    for digits, found in simplified.items():
        for a, b in zip(found, reference[digits], strict=True):
            assert abs(a - b) <= abs(b) * tolerance[digits], (digits, a, b)
