# SPDX-License-Identifier: 0BSD
"""A refusal raised while an execution manifest is built keeps its own
message; only a JSON encoding failure is reported as one."""

from __future__ import annotations

import pytest

from pyamplicol.generation import artifact_writer


def _refuse(*_args, **_kwargs):
    raise ValueError("recurrence helicity-selector refusal of its own")


def test_a_recurrence_manifest_refusal_is_not_reported_as_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(artifact_writer, "_recurrence_execution_manifest", _refuse)
    with pytest.raises(ValueError) as error:
        artifact_writer._bounded_recurrence_execution_summary(
            None,  # type: ignore[arg-type]
            schedule_path="recurrence/schedules/x",
            binding={},
            color_contraction_record=None,
        )
    assert str(error.value) == "recurrence helicity-selector refusal of its own"


def test_an_eager_manifest_refusal_is_not_reported_as_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(artifact_writer, "_eager_plan_v3_execution_manifest", _refuse)
    with pytest.raises(ValueError) as error:
        artifact_writer._eager_execution_summary(None)  # type: ignore[arg-type]
    assert "not canonical JSON" not in str(error.value)


def test_an_unencodable_manifest_is_reported_as_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        artifact_writer,
        "_recurrence_execution_manifest",
        lambda *_args, **_kwargs: {"value": float("nan")},
    )
    with pytest.raises(ValueError, match="not canonical JSON"):
        artifact_writer._bounded_recurrence_execution_summary(
            None,  # type: ignore[arg-type]
            schedule_path="recurrence/schedules/x",
            binding={},
            color_contraction_record=None,
        )
