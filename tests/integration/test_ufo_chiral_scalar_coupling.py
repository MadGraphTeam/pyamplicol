# SPDX-License-Identifier: 0BSD
"""A charged scalar with chiral UFO lone-projector couplings against MadGraph.

The packaged sm UFO plus H+ with ``H+ bbar (yHL P_L + yHR P_R) t + h.c.``,
written with the sm's own FFS1 = ProjM(2,1) and FFS3 = ProjP(2,1). In
``b b~ > h+ w-`` (one diagram, a t-channel top between the chiral W vertex and
the H+ vertex) |M|^2 = yHL^2 A + yHR^2 B with A != B, so the helicity sum
tells the two chiralities apart.
"""

from __future__ import annotations

import importlib.util
import math
import os
import shutil
from pathlib import Path
from typing import NoReturn

import pytest

from pyamplicol import Generator, ModelSource, Runtime
from pyamplicol.config import (
    ColorConfig,
    EvaluatorConfig,
    GenerationConfig,
    GenerationValidationConfig,
    JITConfig,
    RunConfig,
)

_SM_UFO = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "pyamplicol"
    / "assets"
    / "models"
    / "ufo"
    / "sm"
)
_ADDITIONS = {
    "parameters.py": """
MHp = Parameter(name='MHp', nature='external', type='real', value=300.,
                texname='MHp', lhablock='MASS', lhacode=[37])
WHp = Parameter(name='WHp', nature='external', type='real', value=0.,
                texname='WHp', lhablock='DECAY', lhacode=[37])
yHL = Parameter(name='yHL', nature='external', type='real', value=1.0,
                texname='yHL', lhablock='HPLUS', lhacode=[1])
yHR = Parameter(name='yHR', nature='external', type='real', value=0.2,
                texname='yHR', lhablock='HPLUS', lhacode=[2])
""",
    "particles.py": """
H__plus__ = Particle(pdg_code=37, name='H+', antiname='H-', spin=1, color=1,
                     mass=Param.MHp, width=Param.WHp, texname='H+',
                     antitexname='H-', charge=1, GhostNumber=0,
                     LeptonNumber=0, Y=0)
H__minus__ = H__plus__.anti()
""",
    "couplings.py": """
GC_HPL = Coupling(name='GC_HPL', value='complex(0,1)*yHL', order={'QED':1})
GC_HPR = Coupling(name='GC_HPR', value='complex(0,1)*yHR', order={'QED':1})
""",
    "vertices.py": """
V_HP1 = Vertex(name='V_HP1', particles=[P.t__tilde__, P.b, P.H__plus__],
               color=['Identity(1,2)'], lorentz=[L.FFS1, L.FFS3],
               couplings={(0,0):C.GC_HPL,(0,1):C.GC_HPR})
V_HP2 = Vertex(name='V_HP2', particles=[P.b__tilde__, P.t, P.H__minus__],
               color=['Identity(1,2)'], lorentz=[L.FFS1, L.FFS3],
               couplings={(0,0):C.GC_HPR,(0,1):C.GC_HPL})
""",
}
# sqrt(s) = 1 TeV, on shell for MB = 4.7, MHp = 300 and the model's MW.
_POINT = (
    (500.0, 0.0, 0.0, 499.97790951201034),
    (500.0, 0.0, 0.0, -499.97790951201034),
    (541.7663922180795, -193.63353947054688, 216.71729887270064, 345.03693787538566),
    (458.23360778192045, 193.63353947054688, -216.71729887270064, -345.03693787538566),
)
# MadGraph5_aMC@NLO 3.7.0 standalone smatrix at _POINT for the same UFO (the
# sm defaults, MT = 173, at full precision) and (yHL, yHR).
_MADGRAPH = {
    (1.0, 0.2): 2.5578120350182,
    (0.2, 1.0): 0.11322998418504657,
}


def _unavailable(reason: str) -> NoReturn:
    if os.environ.get("PYAMPLICOL_REQUIRE_NATIVE_TESTS") == "1":
        pytest.fail(reason)
    pytest.skip(reason)


def test_lone_projector_couplings_keep_their_chirality(tmp_path: Path) -> None:
    if importlib.util.find_spec("pyamplicol._rusticol") is None:
        _unavailable("the Rusticol extension has not been built")
    model = tmp_path / "sm_hplus"
    shutil.copytree(_SM_UFO, model, ignore=shutil.ignore_patterns("__pycache__"))
    for card in model.glob("restrict_*.dat"):
        card.unlink()
    for name, text in _ADDITIONS.items():
        with (model / name).open("a", encoding="utf-8") as stream:
            stream.write(text)
    compiled = ModelSource.from_path(model, restriction="none").compile(
        use_cache=False, require_supported=True
    )
    artifact = tmp_path / "bb_hpw"
    Generator(
        RunConfig(
            action="generate",
            color=ColorConfig(accuracy="full"),
            generation=GenerationConfig(
                workers=1,
                emit_api_bundle=False,
                validation=GenerationValidationConfig(
                    enabled=False, post_build_validation=False
                ),
            ),
            evaluator=EvaluatorConfig(
                execution_mode="compiled", jit=JITConfig(optimization_level=1)
            ),
        )
    ).generate("b b~ > h+ w-", artifact, model=compiled)
    runtime = Runtime.load(artifact)

    for (left, right), expected in _MADGRAPH.items():
        runtime.set_model_parameters({"yHL": left, "yHR": right})
        value = complex(runtime.evaluate((_POINT,))[0])
        assert math.isclose(value.real, expected, rel_tol=1e-10), (left, right)
        assert abs(value.imag) <= 1e-12 * abs(value.real)
