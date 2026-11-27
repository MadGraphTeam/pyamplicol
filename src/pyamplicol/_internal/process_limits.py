# SPDX-License-Identifier: 0BSD
"""Failures caused by a process that has exhausted its memory maps.

Linux limits the memory mappings of a process (``vm.max_map_count``; 65,530
on many systems). Native code that is compiled at run time (SymJIT, inside
Symbolica and pyAmpliCol's native runtime) needs new executable mappings,
and SymJIT never releases the ones it made; a long-lived process that
generates or loads many artifacts can therefore reach the limit. Every later
mapping then fails, and the failure surfaces wherever it happens: a
Symbolica ``PanicException`` (not even an ``Exception``), a SymJIT
"unable to make memory readable+executable ... os error 12" error, a
``MemoryError``. :func:`resource_exhaustion` recognises these and returns
the typed :class:`pyamplicol.api.errors.ResourceExhaustedError` to raise in
their place, and only when the process's map count corroborates it.
"""

from __future__ import annotations

import contextlib
import errno
import functools
import os
import platform
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, ParamSpec, TypeVar

if TYPE_CHECKING:
    from pyamplicol.api.errors import ResourceExhaustedError

_P = ParamSpec("_P")
_R = TypeVar("_R")

# ENOMEM as Rust's io::Error renders it (SymJIT's mprotect/mmap refusal,
# "System call failed: Cannot allocate memory (os error 12)"): the evidence
# read from the text of an error that carries no structured cause.
_ENOMEM_TEXT = ("(os error 12)", "Cannot allocate memory")
# The map count corroborates exhaustion within this many maps of the limit.
_MARGIN = 64


def memory_maps() -> tuple[int, int] | None:
    """(mappings in use, ``vm.max_map_count``) of this process; None where
    the platform does not expose them."""

    if platform.system() != "Linux":
        return None
    try:
        limit = int(Path("/proc/sys/vm/max_map_count").read_text())
        with open(f"/proc/{os.getpid()}/maps", "rb") as maps:
            in_use = sum(1 for _ in maps)
    except (OSError, ValueError, MemoryError):
        return None
    return in_use, limit


def _chain(exc: BaseException) -> list[BaseException]:
    seen: set[int] = set()
    chain = []
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def _allocation_failure(exc: BaseException) -> bool:
    """Whether ``exc`` (or an error in its chain) is a failure to allocate or
    map memory: a ``MemoryError``, an ``OSError`` with errno ENOMEM, or, for
    an error without structured information, the ENOMEM text of native
    code. An ``OSError`` with another errno (a missing file) is not."""

    for error in _chain(exc):
        if isinstance(error, MemoryError):
            return True
        if isinstance(error, OSError):
            if error.errno == errno.ENOMEM:
                return True
            continue
        text = ""
        with contextlib.suppress(Exception):  # a broken __str__ adds nothing
            text = str(error)
        if any(signature in text for signature in _ENOMEM_TEXT):
            return True
    return False


def resource_exhaustion(exc: BaseException) -> ResourceExhaustedError | None:
    """The typed error to raise in place of ``exc``, or None to let ``exc``
    pass unchanged.

    "memory maps" is claimed only when both hold: ``exc`` is an allocation
    or mapping failure (``_allocation_failure``) and the process's map count
    is within ``_MARGIN`` of ``vm.max_map_count`` now. Every other failure
    passes unchanged (an unrelated error near the limit keeps its type),
    except an untyped native panic (pyo3's ``PanicException``, which is not
    even an ``Exception``) of an allocation failure away from the limit: it
    becomes the error it is, ``resource="memory"``. ``KeyboardInterrupt``,
    ``SystemExit`` and ``GeneratorExit`` always pass."""

    from pyamplicol.api.errors import ResourceExhaustedError

    if isinstance(
        exc, (ResourceExhaustedError, KeyboardInterrupt, SystemExit, GeneratorExit)
    ):
        return None
    panic = type(exc).__name__ == "PanicException"
    if not (isinstance(exc, Exception) or panic) or not _allocation_failure(exc):
        return None
    counts = memory_maps()
    detail = f"Original error: {type(exc).__name__}: {str(exc)[:400]}"
    if counts is not None and counts[0] >= counts[1] - _MARGIN:
        in_use, limit = counts
        return ResourceExhaustedError(
            "memory maps exhausted in this process: it holds "
            f"{in_use} memory maps of its limit vm.max_map_count = {limit}, so "
            "native code can no longer be mapped. Start a new process (code "
            "compiled at run time is never released, so a process that "
            "generates or loads many artifacts reaches the limit), or raise "
            f"vm.max_map_count. {detail}",
            resource="memory maps",
            in_use=in_use,
            limit=limit,
        )
    if not panic:
        return None
    held = (
        f" while {counts[0]} of its {counts[1]} memory maps are in use"
        if counts is not None
        else ""
    )
    return ResourceExhaustedError(
        "out of memory: native code failed to allocate memory (ENOMEM)"
        f"{held}. Free memory (or raise the process's memory limit), or start "
        f"a new process. {detail}",
        resource="memory",
        in_use=None if counts is None else counts[0],
        limit=None if counts is None else counts[1],
    )


def translates_resource_exhaustion(function: Callable[_P, _R]) -> Callable[_P, _R]:
    """Raise :func:`resource_exhaustion`'s typed error in place of a failure
    caused by exhausted memory maps (chained to the original)."""

    @functools.wraps(function)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        try:
            return function(*args, **kwargs)
        except BaseException as exc:
            typed = resource_exhaustion(exc)
            if typed is None:
                raise
            raise typed from exc

    return wrapper
