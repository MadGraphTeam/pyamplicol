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
    or raises :class:`ThreadStartError` (module docstring).

    The decision is taken once, under a lock that the new thread's bootstrap
    also takes: either the thread had started when the bound expired, or it
    is abandoned. An abandoned thread whose bootstrap had not begun is
    removed from the standard library's registry of starting threads (it
    is no longer listed by ``threading.enumerate()``) and the references to
    its target and arguments are dropped; if it bootstraps later it returns
    at once, without registering or running anything.

    What cannot be cleaned up: the operating-system thread, if one was
    created, is not ours to stop (it exits on its own; a daemon thread never
    blocks interpreter exit). A bootstrap that had already begun when the
    bound expired and then fails (the process is out of memory) may leave its
    entry in that registry: the standard library removes it only from the
    thread itself, and nothing can be released safely from outside while
    that thread may still run. In a process out of memory maps, new threads
    fail until memory is released.
    """

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
        self._bootstrapping = False
        # Thread.start waits on this event (CPython 3.11 to 3.14); without
        # it the start is the standard, unbounded one.
        if isinstance(getattr(self, "_started", None), threading.Event):
            self._started = _BoundedEvent(start_seconds)

    def _bootstrap(self) -> None:
        with self._decision:
            if self._abandoned:
                return
            self._bootstrapping = True
        super()._bootstrap()  # type: ignore[misc]

    def run(self) -> None:
        with self._decision:
            if self._abandoned:
                return
        super().run()

    def start(self) -> None:
        try:
            super().start()
        except RuntimeError as exc:  # "can't start new thread"
            raise ThreadStartError(f"{self.name}: {exc}") from exc
        with self._decision:
            if self._started.is_set():
                return
            self._abandoned = True
            bootstrapping = self._bootstrapping
        if not bootstrapping:
            self._forget()
        # Drop the references to the target: an abandoned thread never runs
        # it (run() returns first).
        self._target = None
        self._args = ()
        self._kwargs = {}
        raise ThreadStartError(
            f"{self.name}: the new thread did not run within the start bound "
            "(the process may be out of memory or memory maps)"
        )

    def _forget(self) -> None:
        """Remove a thread whose bootstrap never began from the standard
        library's starting-thread registry (``threading._limbo``, private:
        skipped where it does not exist)."""

        lock = getattr(threading, "_active_limbo_lock", None)
        limbo = getattr(threading, "_limbo", None)
        if lock is None or not isinstance(limbo, dict):
            return
        with lock:
            limbo.pop(self, None)


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
