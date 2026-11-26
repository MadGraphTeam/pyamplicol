# SPDX-License-Identifier: 0BSD
"""The compiled lane's amplitude-order record and its squared-order axis.

The Python exact executor orders squared orders exactly as the native
catalogue (``rusticol-amplitude-orders-v1``): nonzero ``(name index, power)``
pairs compared lexicographically, each with its ordered component pairs.
"""

from __future__ import annotations

import pytest

from pyamplicol.api.errors import ArtifactError, CompatibilityError
from pyamplicol.runtime.symbolica_exact import _compiled_amplitude_orders


def _physics(record: object) -> dict[str, object]:
    return {"extensions": {"amplitude_orders": record}}


def _record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "kind": "pyamplicol-compiled-amplitude-orders-v1",
        "names": ["QCD", "QED"],
        "components": [[0, 2], [2, 0]],
        "executions": {"primary": [0, 1, 1, 0], "helicity_sum": [1, 0]},
    }
    record.update(overrides)
    return record


def test_squared_orders_follow_the_native_catalogue() -> None:
    orders = _compiled_amplitude_orders(_physics(_record()))

    # The native catalogue of u u~ > d d~ at {QCD 2, QED 2}: QCD2 QED2 (the
    # interference, both orderings), QCD4, QED4.
    assert orders.squared == (((0, 1), (1, 0)), ((1, 1),), ((0, 0),))
    assert orders.executions == {"primary": (0, 1, 1, 0), "helicity_sum": (1, 0)}


def test_single_component_has_one_squared_order() -> None:
    orders = _compiled_amplitude_orders(
        _physics(_record(components=[[2, 0]], executions={"primary": [0, 0, 0]}))
    )

    assert orders.squared == (((0, 0),),)


def test_an_artifact_without_the_record_is_a_compatibility_error() -> None:
    with pytest.raises(CompatibilityError, match="records no amplitude coupling"):
        _compiled_amplitude_orders({"extensions": {}})


@pytest.mark.parametrize(
    "record",
    [
        _record(kind="other"),
        _record(components=[[0, 2, 1]]),
        _record(executions={"primary": [2]}),
    ],
)
def test_a_damaged_record_is_an_artifact_error(record: dict[str, object]) -> None:
    with pytest.raises(ArtifactError):
        _compiled_amplitude_orders(_physics(record))
