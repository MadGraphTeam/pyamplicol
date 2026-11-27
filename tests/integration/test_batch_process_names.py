# SPDX-License-Identifier: 0BSD
"""Several processes whose readable names collide, generated in one call.

``u mu- > u mu-`` and ``u mu+ > u mu+`` share the readable default name
``u_mu_to_u_mu``: one ``generate`` call (and an append) builds both, with the
values of the processes generated alone, whichever public request type carries
the automatically named request; a name the user gives still collides.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from pyamplicol import (
    Generator,
    ModelSource,
    ProcessRequest,
    ProcessSet,
    PyAmpliColError,
    Runtime,
)
from pyamplicol.api.requests import _digest_process_name
from pyamplicol.config import (
    ColorConfig,
    EvaluatorConfig,
    GenerationConfig,
    GenerationRelationDiscoveryConfig,
    GenerationValidationConfig,
    RunConfig,
)

PAIR = ("u mu- > u mu-", "u mu+ > u mu+")
# Massless built-in SM: a 2 -> 2 point at sqrt(s) = 1000 with a generic angle.
_E = 500.0
_C, _S = math.cos(0.7), math.sin(0.7)
POINT = [
    [_E, 0.0, 0.0, _E],
    [_E, 0.0, 0.0, -_E],
    [_E, _E * _S, 0.0, _E * _C],
    [_E, -_E * _S, 0.0, -_E * _C],
]


def _generator() -> Generator:
    return Generator(
        RunConfig(
            action="generate",
            color=ColorConfig(accuracy="lc"),
            evaluator=EvaluatorConfig(execution_mode="compiled"),
            generation=GenerationConfig(
                workers=1,
                emit_api_bundle=False,
                relation_discovery=GenerationRelationDiscoveryConfig(mode="off"),
                validation=GenerationValidationConfig(
                    enabled=False, samples=1, seed=7, post_build_validation=False
                ),
            ),
        )
    )


def _value(artifact: Path, name: str) -> float:
    runtime = Runtime.load(artifact, process=name)
    return complex(runtime.evaluate([POINT])[0]).real


def _ids(artifact: Path) -> list[str]:
    manifest = json.loads((artifact / "artifact.json").read_text())
    return [str(record["id"]) for record in manifest["processes"]]


def test_colliding_names_generate_in_one_call_and_by_append(tmp_path: Path) -> None:
    model = ModelSource.built_in_sm()
    alone = {}
    for expression in PAIR:
        output = tmp_path / ("alone-" + expression.replace(" ", ""))
        _generator().generate([expression], output, model=model)
        assert _ids(output) == ["u_mu_to_u_mu"]
        alone[expression] = _value(output, "u_mu_to_u_mu")
    assert alone[PAIR[0]] != alone[PAIR[1]]

    together = tmp_path / "together"
    _generator().generate(list(PAIR), together, model=model)
    names = [_digest_process_name(expression) for expression in PAIR]
    assert _ids(together) == names
    for expression, name in zip(PAIR, names, strict=True):
        assert _value(together, name) == pytest.approx(alone[expression], rel=1e-13)

    appended = tmp_path / "appended"
    _generator().generate([PAIR[0]], appended, model=model)
    _generator().generate([PAIR[1]], appended, model=model, mode="append")
    assert _ids(appended) == ["u_mu_to_u_mu", names[1]]
    assert _value(appended, names[1]) == pytest.approx(alone[PAIR[1]], rel=1e-13)


# The second process of the pair, through every public request type: its
# automatic name collides with the appended artifact's ``u_mu_to_u_mu``.
SECOND = {
    "expression": lambda: PAIR[1],
    "expression list": lambda: [PAIR[1]],
    "ProcessRequest.parse": lambda: ProcessRequest.parse(PAIR[1]),
    "ProcessRequest list": lambda: [ProcessRequest.parse(PAIR[1])],
    "ProcessSet.from_expressions": lambda: ProcessSet.from_expressions([PAIR[1]]),
    "ProcessSet": lambda: ProcessSet((ProcessRequest.parse(PAIR[1]),)),
}


@pytest.mark.parametrize("kind", sorted(SECOND))
def test_an_automatic_name_is_automatic_in_every_request_type(
    kind: str, tmp_path: Path
) -> None:
    model = ModelSource.built_in_sm()
    appended = tmp_path / "appended"
    _generator().generate(ProcessSet.from_expressions([PAIR[0]]), appended, model=model)
    _generator().generate(SECOND[kind](), appended, model=model, mode="append")
    assert _ids(appended) == ["u_mu_to_u_mu", _digest_process_name(PAIR[1])]


def test_a_user_given_name_still_collides(tmp_path: Path) -> None:
    model = ModelSource.built_in_sm()
    appended = tmp_path / "appended"
    _generator().generate([PAIR[0]], appended, model=model)
    named = ProcessRequest.parse(PAIR[1], name="u_mu_to_u_mu")
    with pytest.raises(PyAmpliColError, match="u_mu_to_u_mu"):
        _generator().generate(named, appended, model=model, mode="append")
    assert _ids(appended) == ["u_mu_to_u_mu"]
