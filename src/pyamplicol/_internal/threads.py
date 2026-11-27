# SPDX-License-Identifier: 0BSD
"""Helper threads whose start never waits for ever.

``threading.Thread.start`` waits, without a timeout, for the new thread to
signal that it runs. When the new thread fails before it signals (CPython
3.11 raises ``MemoryError`` in its bootstrap when the process cannot map
memory any more, for example once ``vm.max_map_count`` memory maps exist, and
reports it as "Exception ignored in thread started by"), that wait never
ends: the caller hangs for good. pyAmpliCol's auxiliary threads (resource
monitor, log forwarder, progress heartbeats) only observe the work, so their
start is bounded: :class:`AuxiliaryThread` raises :class:`ThreadStartError`
after ``START_SECONDS`` without the thread running, and the thread then
never runs its target; the caller continues without it.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Callable

# How long start() waits for the new thread to run (seconds). A healthy
# thread runs within microseconds; the bound only matters when it cannot.
START_SECONDS = 10.0


class ThreadStartError(RuntimeError):
    """An auxiliary thread could not be started (it did not run within the
    start bound, or the system refused a new thread)."""


class _BoundedEvent(threading.Event):
    """The thread's "started" event: an unbounded wait (the one in
    ``Thread.start``) waits at most ``seconds``."""

    def __init__(self, seconds: float) -> None:
        super().__init__()
        self._seconds = seconds

    def wait(self, timeout: float | None = None) -> bool:
        return super().wait(self._seconds if timeout is None else timeout)


class AuxiliaryThread(threading.Thread):
    """A daemon thread whose :meth:`start` returns within ``start_seconds``
    or raises :class:`ThreadStartError` (module docstring). An abandoned
    thread that runs later returns at once, without running its target."""

    def __init__(
        self,
        target: Callable[..., object],
        *,
        name: str | None = None,
        args: tuple[object, ...] = (),
        start_seconds: float | None = None,
    ) -> None:
        super().__init__(target=target, name=name, args=args, daemon=True)
        if start_seconds is None:
            start_seconds = START_SECONDS
        self._decision = threading.Lock()
        self._abandoned = False
        self._ran = False
        # Thread.start waits on this event (CPython 3.11 to 3.14); without
        # it the start is the standard, unbounded one.
        if isinstance(getattr(self, "_started", None), threading.Event):
            self._started = _BoundedEvent(start_seconds)

    def run(self) -> None:
        with self._decision:
            if self._abandoned:
                return
            self._ran = True
        super().run()

    def start(self) -> None:
        try:
            super().start()
        except RuntimeError as exc:  # "can't start new thread"
            raise ThreadStartError(f"{self.name}: {exc}") from exc
        with self._decision:
            if self._ran or self._started.is_set():
                return
            self._abandoned = True
        raise ThreadStartError(
            f"{self.name}: the new thread did not run within the start bound "
            "(the process may be out of memory or memory maps)"
        )


def start_auxiliary(
    target: Callable[..., object],
    *,
    name: str,
    args: tuple[object, ...] = (),
    start_seconds: float | None = None,
) -> AuxiliaryThread | None:
    """Start an :class:`AuxiliaryThread`; None (and a warning on the
    ``pyamplicol`` logger) when it cannot be started."""

    thread = AuxiliaryThread(target, name=name, args=args, start_seconds=start_seconds)
    try:
        thread.start()
    except ThreadStartError as exc:
        with contextlib.suppress(Exception):  # the warning is best effort
            logging.getLogger("pyamplicol").warning("continuing without %s", exc)
        return None
    return thread
