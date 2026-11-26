# SPDX-License-Identifier: 0BSD
"""Specialisation guards of one-loop artifacts (custom copies of ``loop_sm``;
no shipped loop model records a guard, so these paths are reachable only
with custom models).

The loop plan's Born and tree blocks run on the tree model with its
restriction simplification (``LoopSlice._generate``:
``CompiledUFOModel(compiled)``), so the model's guards apply to the plan at
every way a value reaches it:

- explicit bindings, compared exactly in the binding's decimal precision
  with the parameter's generation value as exact carriers read it (the
  shortest decimal of its binary64: 91.188, as the plan's defaults give it);
- ``[loop.preparation] fixed_parameters``, refused at generation when they
  move a guarded parameter;
- a loop that dresses the removed vertex, refused by the loop generation
  itself (``loop-vertex-outside-tree-model``);
- the complex-mass scheme, which turns a guarded mass into a complex pole
  mass: refused on a model with restriction-simplification guards (the
  removed term need not vanish there, with no binding changed).

The guard is the model's: every plan from the model holds its parameters,
also one whose diagrams never meet the removed vertex (a conservative scope
that refuses, never accepts, a binding).
"""

from __future__ import annotations

import json
import shutil
from importlib import resources
from pathlib import Path

import pytest

pytest.importorskip("symbolica")

_PHOTON_DOWN = "'-(ee*complex(0,1))/3.'"
_ELECTRON_Z = (
    "GC_24 = Coupling(name = 'GC_24',\n"
    "                 value = '(ee*complex(0,1)*sw)/(2.*cw)'"
)
_POINT = [
    ["250", "0", "0", "250"],
    ["250", "0", "0", "-250"],
    ["250", "150", "0", "200"],
    ["250", "-150", "0", "-200"],
]


def _custom_loop_sm(destination: Path, original: str, factor: str) -> Path:
    shipped = Path(
        str(resources.files("pyamplicol").joinpath("assets/models/ufo/loop_sm"))
    )
    shutil.copytree(shipped, destination, ignore=shutil.ignore_patterns("__pycache__"))
    couplings = destination / "couplings.py"
    text = couplings.read_text(encoding="utf-8")
    assert text.count(original) == 1
    couplings.write_text(
        text.replace(original, original[:-1] + f"*{factor}'"), encoding="utf-8"
    )
    return destination


def _generate(
    root: Path,
    model: Path | str,
    fixed: dict[str, str],
    process: str = "u u~ > e+ e-",
    mass_scheme: str = "real-on-shell",
) -> Path:
    from pyamplicol.api import Generator, ProcessRequest, ProcessSet
    from pyamplicol.config import resolve_config

    root.mkdir(parents=True, exist_ok=True)
    entries = ", ".join(
        f"{name} = {json.dumps(value)}" for name, value in fixed.items()
    )
    card = root / "card.toml"
    card.write_text(
        f"""action = "generate"
[model]
source = "{model}"
cache_dir = "{root / "cache"}"
[process]
entries = [{{expression = {json.dumps(process)}, name = "p"}}]
loop_coupling_orders = ["QCD"]
[loop]
external_widths = "zero"
r2_strategy = "model"
[loop.model]
loop_coupling_orders = ["QCD"]
uv_complete = true
model_r2_complete = true
[loop.model.scheme]
dimensional_regularization = "HV"
external_states = "physical-four-dimensional"
gamma5 = "source-UFO-four-dimensional-prescription"
renormalization = "source-UFO mass-dependent decoupling"
mass_scheme = "{mass_scheme}"
finite_restoration = "source-UFO-local-rules"
model_convention = "loop_sm lhv=1 supplied QCD rules"
[loop.preparation]
fixed_parameters = {{{entries}}}
[generation]
output = "artifact"
emit_api_bundle = false
[generation.validation]
post_build_validation = false
"""
    )
    config = resolve_config(card)
    output = Path(config.effective.generation.output)
    Generator(config).generate(
        ProcessSet((ProcessRequest.parse(process, name="p"),)), output
    )
    return output


def _values(runtime, arithmetic: str = "double-double") -> list:
    result = runtime.evaluate([_POINT], mu_r2=["250000"], arithmetic=arithmetic)
    return [
        [complex(value).real for value in result.born_values[0]],
        [complex(v.finite).real for v in result.values[0]],
    ]


@pytest.fixture(scope="module")
def photon_down_mt(tmp_path_factory) -> Path:
    return _custom_loop_sm(
        tmp_path_factory.mktemp("loop-sm-gc1") / "loop_sm_gc1",
        _PHOTON_DOWN,
        "(MT-173)",
    )


@pytest.mark.loop_physics
def test_a_loop_plan_holds_the_parameter_its_born_specialised(
    photon_down_mt, tmp_path
) -> None:
    from pyamplicol.api import Runtime

    artifact = _generate(tmp_path / "a", photon_down_mt, {})
    runtime = Runtime.load(artifact)
    runtime.set_model_parameters({"MT": "173"})
    runtime.set_model_parameters({"MT": "173.000"})
    with pytest.raises(Exception, match="specialisation-guard: binding MT"):
        runtime.set_model_parameters({"MT": "174"})
    with pytest.raises(Exception, match="specialisation-guard: binding MT"):
        runtime.set_model_parameters({"MT": "173.00000000000000000001"})
    with pytest.raises(Exception, match="specialisation-guard: binding MT"):
        Runtime.load(artifact, model_parameters={"MT": "174"})


@pytest.mark.loop_physics
def test_a_loop_that_needs_the_removed_vertex_is_refused(
    photon_down_mt, tmp_path
) -> None:
    with pytest.raises(Exception, match="loop-vertex-outside-tree-model"):
        _generate(tmp_path / "d", photon_down_mt, {}, "d d~ > e+ e-")


@pytest.mark.loop_physics
def test_a_fixed_parameter_is_checked_at_admission(photon_down_mt, tmp_path) -> None:
    with pytest.raises(Exception, match="a fixed parameter of the plan"):
        _generate(tmp_path / "b", photon_down_mt, {"MT": "174"})
    _generate(tmp_path / "c", photon_down_mt, {"MT": "173"})


# A guarded parameter with a non-dyadic card value: the plan's default (the
# card's decimal), the same decimal bound explicitly, and the same value as a
# float are one value; the binary64 nearest it, read exactly, is another and
# is refused.
_NON_DYADIC = {
    "mass": ("MZ", "91.188"),
    "width": ("WZ", "2.441404"),
    "coupling input": ("aEWM1", "132.507"),
}


@pytest.mark.loop_physics
@pytest.mark.parametrize("kind", sorted(_NON_DYADIC))
def test_a_non_dyadic_guarded_default_is_one_value(kind, tmp_path) -> None:
    from decimal import Decimal

    from pyamplicol.api import Runtime

    name, decimal = _NON_DYADIC[kind]
    binary64 = str(Decimal(float(decimal)))
    assert binary64 != decimal
    model = _custom_loop_sm(tmp_path / "loop_sm_x", _ELECTRON_Z, f"({name}-{decimal})")
    artifact = _generate(tmp_path / "a", model, {})
    guards = json.loads((artifact / "model/specialization-guards.json").read_text())
    assert [guard["parameters"] for guard in guards["guards"]] == [[name]]
    default = _values(Runtime.load(artifact))
    explicit = _values(Runtime.load(artifact, model_parameters={name: decimal}))
    as_float = _values(Runtime.load(artifact, model_parameters={name: float(decimal)}))
    assert explicit == default and as_float == default
    with pytest.raises(Exception, match=f"specialisation-guard: binding {name}"):
        Runtime.load(artifact, model_parameters={name: binary64})


@pytest.mark.loop_physics
def test_the_complex_mass_scheme_refuses_a_guarded_model(tmp_path) -> None:
    from pyamplicol.api import Runtime

    # GC_24 (electron-Z) times MT - 173: removed at MT = 173 in the real
    # scheme; under the complex-mass scheme MT is a complex pole mass and the
    # term does not vanish (the Born was 17.9 % low).
    model = _custom_loop_sm(tmp_path / "loop_sm_z", _ELECTRON_Z, "(MT-173)")
    with pytest.raises(Exception, match="complex-mass continuation does not preserve"):
        _generate(
            tmp_path / "cms",
            model,
            {"WW": "0", "WZ": "0"},
            mass_scheme="complex-mass",
        )
    # Its real-scheme twin generates and holds MT.
    artifact = _generate(tmp_path / "real", model, {})
    runtime = Runtime.load(artifact)
    with pytest.raises(Exception, match="specialisation-guard: binding MT"):
        runtime.set_model_parameters({"MT": "174"})


@pytest.mark.loop_physics
def test_the_complex_mass_scheme_on_a_shipped_model_is_unchanged(tmp_path) -> None:
    from pyamplicol.api import Runtime

    artifact = _generate(
        tmp_path / "cms", "loop_sm", {"WW": "0", "WZ": "0"}, mass_scheme="complex-mass"
    )
    assert not (artifact / "model/specialization-guards.json").exists()
    born, _finite = _values(Runtime.load(artifact), arithmetic="double")
    assert all(value != 0.0 for value in born)
