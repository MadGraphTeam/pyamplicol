# SPDX-License-Identifier: 0BSD
"""A failure caused by the process's exhausted memory maps is typed, and
only such a failure.

Once a process holds ``vm.max_map_count`` memory maps, the next native code
compiled at run time fails wherever it is: Symbolica raises a
``PanicException`` (not an ``Exception``), SymJIT reports "unable to make
memory readable+executable ... os error 12". ``generate`` and
``Runtime.load`` raise ``ResourceExhaustedError("memory maps")`` in their
place, chained to the original, when the failure is an allocation failure
AND the map count is at the limit. An unrelated error near the limit keeps
its type; an allocation failure away from the limit is not called
exhausted maps.
"""

from __future__ import annotations

import errno

import pytest

from pyamplicol import Generator, ResourceExhaustedError, Runtime
from pyamplicol._internal import process_limits
from pyamplicol.api.errors import CompatibilityError, GenerationError, PyAmpliColError

SYMJIT_FAILURE = (
    "called `Result::unwrap()` on an `Err` value: Backend(unable to make memory "
    "readable+executable\n\nCaused by:\n    System call failed: Cannot allocate "
    "memory (os error 12))"
)
LIMIT = 1048576
AT_LIMIT = (LIMIT - 39, LIMIT)  # the reviewer's count: 1,048,537 in use
AWAY = (264, LIMIT)


class PanicException(BaseException):
    """Stands for pyo3's ``pyo3_runtime.PanicException`` (a BaseException)."""


def _raise(exc: BaseException):
    def fail(*args: object, **kwargs: object) -> object:
        raise exc

    return fail


def _counts(monkeypatch: pytest.MonkeyPatch, counts: tuple[int, int]) -> None:
    monkeypatch.setattr(process_limits, "memory_maps", lambda: counts)


def _generate_raising(monkeypatch: pytest.MonkeyPatch, failure: BaseException):
    monkeypatch.setattr(Generator, "_generate", _raise(failure))
    return lambda: Generator().generate(["e+ e- > mu+ mu-"], "unused")


def _load_raising(failure: BaseException):
    class Artifact:
        def __fspath__(self) -> str:
            raise failure

    return lambda: Runtime.load(Artifact())  # type: ignore[arg-type]


def test_a_symbolica_panic_at_the_map_limit_is_typed_in_generate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _counts(monkeypatch, AT_LIMIT)
    panic = PanicException(SYMJIT_FAILURE)
    with pytest.raises(ResourceExhaustedError) as caught:
        _generate_raising(monkeypatch, panic)()
    assert isinstance(caught.value, PyAmpliColError)
    assert caught.value.resource == "memory maps"
    assert (caught.value.in_use, caught.value.limit) == AT_LIMIT
    assert "memory maps exhausted in this process" in str(caught.value)
    assert "Start a new process" in str(caught.value)
    assert caught.value.__cause__ is panic


def test_a_symjit_load_failure_at_the_map_limit_is_typed_in_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _counts(monkeypatch, AT_LIMIT)
    failure = CompatibilityError(f"SymJIT panicked while loading: {SYMJIT_FAILURE}")
    with pytest.raises(ResourceExhaustedError, match="memory maps exhausted") as caught:
        _load_raising(failure)()
    assert caught.value.__cause__ is failure


@pytest.mark.parametrize(
    "failure", [MemoryError(), OSError(errno.ENOMEM, "Cannot allocate memory")]
)
def test_a_structured_allocation_failure_at_the_limit_is_typed(
    monkeypatch: pytest.MonkeyPatch, failure: BaseException
) -> None:
    _counts(monkeypatch, AT_LIMIT)
    with pytest.raises(ResourceExhaustedError) as caught:
        _generate_raising(monkeypatch, failure)()
    assert caught.value.resource == "memory maps"
    assert caught.value.__cause__ is failure


def test_a_missing_artifact_near_the_limit_keeps_its_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """The reviewer's case: a nonexistent path at 39 maps below the limit."""

    missing = tmp_path / "no-such-artifact"
    with pytest.raises(BaseException) as reference:
        Runtime.load(missing)
    _counts(monkeypatch, AT_LIMIT)
    with pytest.raises(BaseException) as near:
        Runtime.load(missing)
    assert not isinstance(near.value, ResourceExhaustedError)
    assert type(near.value) is type(reference.value)
    assert str(near.value) == str(reference.value)


def test_enomem_text_away_from_the_limit_is_not_called_memory_maps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reviewer's inverse case: the SymJIT ENOMEM text at 264 maps."""

    _counts(monkeypatch, AWAY)
    typed = CompatibilityError(f"SymJIT panicked while loading: {SYMJIT_FAILURE}")
    with pytest.raises(CompatibilityError) as caught:
        _load_raising(typed)()
    assert caught.value is typed  # already typed: unchanged
    panic = PanicException(SYMJIT_FAILURE)
    with pytest.raises(ResourceExhaustedError) as untyped:
        _generate_raising(monkeypatch, panic)()
    assert untyped.value.resource == "memory"
    assert "memory maps exhausted" not in str(untyped.value)
    assert "264 of its 1048576 memory maps are in use" in str(untyped.value)
    assert "out of memory" in str(untyped.value)
    assert untyped.value.__cause__ is panic


@pytest.mark.parametrize(
    "failure",
    [
        GenerationError("no tree amplitude at these orders"),
        FileNotFoundError(errno.ENOENT, "No such file or directory"),
        ValueError("bad"),
        PanicException("index out of bounds"),
        KeyboardInterrupt(),
    ],
)
@pytest.mark.parametrize("counts", [AT_LIMIT, AWAY])
def test_unrelated_failures_pass_unchanged(
    monkeypatch: pytest.MonkeyPatch, failure: BaseException, counts
) -> None:
    _counts(monkeypatch, counts)
    with pytest.raises(type(failure)) as caught:
        _generate_raising(monkeypatch, failure)()
    assert caught.value is failure
