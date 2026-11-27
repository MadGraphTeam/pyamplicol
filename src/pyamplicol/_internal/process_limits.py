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
their place.
"""

from __future__ import annotations

import contextlib
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

# The kernel's mprotect/mmap refusal as SymJIT reports it.
_SIGNATURES = (
    "unable to make memory readable+executable",
    "Cannot allocate memory (os error 12)",
)
# A process this close to its limit cannot be relied on to map anything.
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


def _messages(exc: BaseException) -> str:
    seen: set[int] = set()
    parts = []
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        with contextlib.suppress(Exception):  # a broken __str__ adds nothing
            parts.append(str(current))
        current = current.__cause__ or current.__context__
    return "\n".join(parts)


def resource_exhaustion(exc: BaseException) -> ResourceExhaustedError | None:
    """The typed error for ``exc`` when it was caused by this process's
    exhausted memory maps; None otherwise (``KeyboardInterrupt``,
    ``SystemExit`` and ``GeneratorExit`` never)."""

    from pyamplicol.api.errors import ResourceExhaustedError

    if isinstance(exc, ResourceExhaustedError):
        return None
    if isinstance(exc, (KeyboardInterrupt, SystemExit, GeneratorExit)):
        return None
    if not isinstance(exc, Exception) and type(exc).__name__ != "PanicException":
        return None
    counts = memory_maps()
    at_limit = counts is not None and counts[0] >= counts[1] - _MARGIN
    text = _messages(exc)
    signed = all(signature in text for signature in _SIGNATURES)
    if not (at_limit or signed):
        return None
    in_use, limit = counts if counts is not None else (None, None)
    held = (
        f"{in_use} memory maps of its limit vm.max_map_count = {limit}"
        if counts is not None
        else "its limit of memory maps (vm.max_map_count)"
    )
    return ResourceExhaustedError(
        f"memory maps exhausted in this process: it holds {held}, so native "
        "code can no longer be mapped. Start a new process (code compiled at "
        "run time is never released, so a process that generates or loads "
        "many artifacts reaches the limit), or raise vm.max_map_count. "
        f"Original error: {type(exc).__name__}: {str(exc)[:400]}",
        resource="memory maps",
        in_use=in_use,
        limit=limit,
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
