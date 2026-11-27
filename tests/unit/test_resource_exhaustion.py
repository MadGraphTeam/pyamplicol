# SPDX-License-Identifier: 0BSD
"""A failure caused by the process's exhausted memory maps is typed.

Once a process holds ``vm.max_map_count`` memory maps, the next native code
compiled at run time fails wherever it is: Symbolica raises a
``PanicException`` (not an ``Exception``), SymJIT reports "unable to make
memory readable+executable ... os error 12". ``generate`` and
``Runtime.load`` raise ``ResourceExhaustedError`` in their place, chained
to the original; any other failure passes unchanged.
"""

from __future__ import annotations

import pytest

from pyamplicol import Generator, ResourceExhaustedError, Runtime
from pyamplicol._internal import process_limits
from pyamplicol.api.errors import CompatibilityError, PyAmpliColError

SYMJIT_FAILURE = (
    "called `Result::unwrap()` on an `Err` value: Backend(unable to make memory "
    "readable+executable\n\nCaused by:\n    System call failed: Cannot allocate "
    "memory (os error 12))"
)


class PanicException(BaseException):
    """Stands for pyo3's ``pyo3_runtime.PanicException`` (a BaseException)."""


def _raise(exc: BaseException):
    def fail(*args: object, **kwargs: object) -> object:
        raise exc

    return fail


def test_a_symbolica_panic_at_the_map_limit_is_typed_in_generate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    panic = PanicException(SYMJIT_FAILURE)
    monkeypatch.setattr(Generator, "_generate", _raise(panic))
    with pytest.raises(ResourceExhaustedError) as caught:
        Generator().generate(["e+ e- > mu+ mu-"], "unused")
    assert isinstance(caught.value, PyAmpliColError)
    assert caught.value.resource == "memory maps"
    assert "memory maps exhausted in this process" in str(caught.value)
    assert "Start a new process" in str(caught.value)
    assert caught.value.__cause__ is panic


def test_a_symjit_load_failure_at_the_map_limit_is_typed_in_load() -> None:
    class Artifact:
        def __fspath__(self) -> str:
            raise CompatibilityError(f"SymJIT panicked while loading: {SYMJIT_FAILURE}")

    with pytest.raises(ResourceExhaustedError, match="memory maps exhausted"):
        Runtime.load(Artifact())  # type: ignore[arg-type]


def test_the_live_map_count_at_the_limit_types_any_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(process_limits, "memory_maps", lambda: (65530, 65530))
    monkeypatch.setattr(Generator, "_generate", _raise(MemoryError()))
    with pytest.raises(ResourceExhaustedError) as caught:
        Generator().generate(["e+ e- > mu+ mu-"], "unused")
    assert (caught.value.in_use, caught.value.limit) == (65530, 65530)
    assert "65530 memory maps" in str(caught.value)


@pytest.mark.parametrize(
    "failure",
    [PanicException("index out of bounds"), ValueError("bad"), KeyboardInterrupt()],
)
def test_other_failures_pass_unchanged(
    monkeypatch: pytest.MonkeyPatch, failure: BaseException
) -> None:
    monkeypatch.setattr(process_limits, "memory_maps", lambda: (1000, 65530))
    monkeypatch.setattr(Generator, "_generate", _raise(failure))
    with pytest.raises(type(failure)) as caught:
        Generator().generate(["e+ e- > mu+ mu-"], "unused")
    assert caught.value is failure
