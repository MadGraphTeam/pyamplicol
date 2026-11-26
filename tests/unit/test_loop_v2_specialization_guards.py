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
    simplify: bool = True,
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
simplify = {"true" if simplify else "false"}
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


# A coupling zero at a non-dyadic card value only at its decimal (zero at
# MZ = 91.188, not at the binary64 nearest it, which the native tree runtime
# promotes) is not removed: the simplified model then gives the unsimplified
# one's double-double values, for a mass, a width and a coupling input. (A
# guarded non-dyadic default is in the tie test below.)
_NON_DYADIC = {
    "mass": ("MZ", "91.188"),
    "width": ("WZ", "2.441404"),
    "coupling input": ("aEWM1", "132.507"),
}


@pytest.mark.loop_physics
@pytest.mark.parametrize("kind", sorted(_NON_DYADIC))
def test_a_zero_only_at_the_decimal_is_kept(kind, tmp_path) -> None:
    from pyamplicol.api import Runtime

    name, decimal = _NON_DYADIC[kind]
    model = _custom_loop_sm(tmp_path / "loop_sm_x", _ELECTRON_Z, f"({name}-{decimal})")
    simplified = _generate(tmp_path / "s", model, {})
    unsimplified = _generate(tmp_path / "u", model, {}, simplify=False)
    assert not (simplified / "model/specialization-guards.json").exists()
    assert _values(Runtime.load(simplified)) == _values(Runtime.load(unsimplified))


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


def _with_card(model: Path, replacements: dict[str, str]) -> Path:
    card = model / "restrict_default.dat"
    text = card.read_text(encoding="utf-8")
    for old, new in replacements.items():
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    card.write_text(text, encoding="utf-8")
    return model


@pytest.mark.loop_physics
def test_a_tie_between_shortest_decimals_is_one_value(tmp_path, loop_native) -> None:
    """MT = ymt = 173 + 2^-15: Python's repr writes 173.00003051757812,
    Rust's Debug 173.00003051757813. The guard (on GC_24 times MT - ymt)
    records the producer's text, the plan's default is written by the same
    function, and every reader parses that text: the default loads in Python
    and through the native runtime's own admission."""

    from pyamplicol.api import Runtime

    value = 173.0 + 2.0**-15
    assert repr(value) == "173.00003051757812"
    model = _custom_loop_sm(tmp_path / "loop_sm_tie", _ELECTRON_Z, "(MT-ymt)")
    _with_card(
        model,
        {
            "    6 1.730000e+02 # MT": "    6 1.73000030517578125e+02 # MT",
            "    6 1.730000e+02 # ymt": "    6 1.73000030517578125e+02 # ymt",
        },
    )
    artifact = _generate(tmp_path / "a", model, {})
    guards = json.loads((artifact / "model/specialization-guards.json").read_text())
    (guard,) = guards["guards"]
    assert guard["generation_exact"]["MT"][0] == repr(value)
    default = _values(Runtime.load(artifact))
    flat = [str(c) for momentum in _POINT for c in momentum]
    found = loop_native.evaluate_v2_artifact(
        str(artifact), [flat], ["250000"], process=None, parameters=None
    )
    ((_values_native, failures),) = found
    assert not failures, failures
    assert default
    # The same value bound explicitly: the producer's text, the float.
    for bound in (repr(value), value):
        assert (
            _values(Runtime.load(artifact, model_parameters={"MT": bound})) == default
        )


@pytest.mark.loop_physics
def test_an_order_one_coupling_zero_in_binary64_is_kept(tmp_path) -> None:
    """An electron-Z coupling times 2e8 (sqrt(10000000000000001) - 1e8): of
    order one, zero in binary64 only. The exact rule keeps it, so the
    simplified model gives the unsimplified one's double-double values."""

    from pyamplicol.api import Runtime

    model = _custom_loop_sm(
        tmp_path / "loop_sm_cancel",
        _ELECTRON_Z,
        "200000000*(cmath.sqrt(10000000000000001)-100000000)",
    )
    simplified = _generate(tmp_path / "s", model, {})
    unsimplified = _generate(tmp_path / "u", model, {}, simplify=False)
    assert not (simplified / "model/specialization-guards.json").exists()
    assert _values(Runtime.load(simplified)) == _values(Runtime.load(unsimplified))
