# SPDX-License-Identifier: 0BSD
"""Specialisation guards of a one-loop artifact.

A copy of the shipped ``loop_sm`` whose photon-down coupling ``GC_1`` gets a
factor ``MT - 173``. At its card (MT = 173) the tree model's restriction
simplification removes the coupling and records a guard holding ``MT``. The
loop plan's Born and tree blocks run on that tree model
(``LoopSlice._generate``: ``CompiledUFOModel(compiled)``), so the plan
consumed the specialisation even though the exact loop preparation keeps
the coupling's expression: the guard applies to the plan, at every way a
value reaches it.

- An explicit binding of MT other than 173 is refused, and 173 is accepted,
  compared exactly in the binding's decimal precision.
- A card's ``[loop.preparation] fixed_parameters`` that fix MT at another
  value are refused at generation (admission), and fixing it at 173 is
  accepted.
"""

from __future__ import annotations

import json
import shutil
from importlib import resources
from pathlib import Path

import pytest

pytest.importorskip("symbolica")


def _custom_loop_sm(destination: Path) -> Path:
    shipped = Path(
        str(resources.files("pyamplicol").joinpath("assets/models/ufo/loop_sm"))
    )
    shutil.copytree(shipped, destination, ignore=shutil.ignore_patterns("__pycache__"))
    couplings = destination / "couplings.py"
    text = couplings.read_text(encoding="utf-8")
    original = "'-(ee*complex(0,1))/3.'"
    assert text.count(original) == 1
    couplings.write_text(
        text.replace(original, "'-((MT-173)*ee*complex(0,1))/3.'"), encoding="utf-8"
    )
    return destination


def _generate(root: Path, model: Path, fixed: dict[str, str]) -> Path:
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
entries = [{{expression = "d d~ > e+ e-", name = "p"}}]
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
mass_scheme = "real-on-shell"
finite_restoration = "source-UFO-local-rules"
model_convention = "loop_sm lhv=1 supplied QCD rules"
[loop.preparation]
fixed_parameters = {{{entries}}}
[generation]
output = "artifact"
emit_api_bundle = false
"""
    )
    config = resolve_config(card)
    output = Path(config.effective.generation.output)
    Generator(config).generate(
        ProcessSet((ProcessRequest.parse("d d~ > e+ e-", name="p"),)), output
    )
    return output


@pytest.fixture(scope="module")
def custom_model(tmp_path_factory) -> Path:
    return _custom_loop_sm(tmp_path_factory.mktemp("loop-sm-gc1") / "loop_sm_gc1")


@pytest.mark.loop_physics
def test_a_loop_plan_holds_the_parameter_its_born_specialised(
    custom_model, tmp_path
) -> None:
    from pyamplicol.api import Runtime

    artifact = _generate(tmp_path / "a", custom_model, {})
    runtime = Runtime.load(artifact)
    runtime.set_model_parameters({"MT": "173"})
    runtime.set_model_parameters({"MT": "173.000"})
    with pytest.raises(Exception, match="specialisation-guard: binding MT"):
        runtime.set_model_parameters({"MT": "174"})
    # Equal in binary64, different as bound.
    with pytest.raises(Exception, match="specialisation-guard: binding MT"):
        runtime.set_model_parameters({"MT": "173.00000000000000000001"})
    with pytest.raises(Exception, match="specialisation-guard: binding MT"):
        Runtime.load(artifact, model_parameters={"MT": "174"})


@pytest.mark.loop_physics
def test_a_fixed_parameter_is_checked_at_admission(custom_model, tmp_path) -> None:
    with pytest.raises(Exception, match="a fixed parameter of the plan"):
        _generate(tmp_path / "b", custom_model, {"MT": "174"})
    # Fixed at the guarded value: accepted.
    _generate(tmp_path / "c", custom_model, {"MT": "173"})
