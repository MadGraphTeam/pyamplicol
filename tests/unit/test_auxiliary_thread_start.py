# SPDX-License-Identifier: 0BSD
"""An auxiliary thread that cannot start never blocks its caller.

``threading.Thread.start`` waits without a timeout for the new thread to
signal that it runs; a thread whose bootstrap fails first (``MemoryError``
once the process holds ``vm.max_map_count`` memory maps) left
``generate`` hanging for good in the resource monitor's start. The start of
pyAmpliCol's auxiliary threads is bounded, the work continues without them.
"""

from __future__ import annotations

import gc
import os
import platform
import subprocess
import sys
import textwrap
import threading
import time
import weakref
from pathlib import Path

import pytest

from pyamplicol._internal import threads
from pyamplicol._internal.threads import (
    AuxiliaryThread,
    ThreadStartError,
    start_auxiliary,
)

# The failed bootstraps are reported by CPython as unraisable exceptions.
_UNRAISABLE = pytest.mark.filterwarnings(
    "ignore::pytest.PytestUnraisableExceptionWarning"
)


class _FailingBootstrap(AuxiliaryThread):
    """The bootstrap fails before the thread signals that it started, as
    CPython's does when the process cannot allocate any more."""

    def _bootstrap(self) -> None:
        raise MemoryError


class _LateBootstrap(AuxiliaryThread):
    def _bootstrap(self) -> None:
        time.sleep(0.5)
        super()._bootstrap()  # type: ignore[misc]


@_UNRAISABLE
def test_a_thread_that_never_runs_raises_within_the_bound() -> None:
    ran = threading.Event()
    thread = _FailingBootstrap(ran.set, name="never", start_seconds=0.2)
    began = time.monotonic()
    with pytest.raises(ThreadStartError, match="did not run"):
        thread.start()
    assert time.monotonic() - began < 5.0
    assert not ran.wait(0.3)


def test_an_abandoned_thread_that_runs_late_skips_its_target() -> None:
    ran = threading.Event()
    thread = _LateBootstrap(ran.set, name="late", start_seconds=0.05)
    with pytest.raises(ThreadStartError):
        thread.start()
    assert not ran.wait(1.5)


def test_a_healthy_thread_runs_and_joins() -> None:
    ran = threading.Event()
    thread = start_auxiliary(ran.set, name="healthy")
    assert thread is not None
    thread.join(5.0)
    assert ran.is_set() and not thread.is_alive() and thread.daemon


@_UNRAISABLE
def test_the_resource_monitor_and_log_capture_continue_without_their_thread(
    monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    from pyamplicol._internal import symbolica_log
    from pyamplicol.reporting.resources import ResourceUsageMonitor

    monkeypatch.setattr(threads, "START_SECONDS", 0.2)
    monkeypatch.setattr(AuxiliaryThread, "_bootstrap", _FailingBootstrap._bootstrap)
    monitor = ResourceUsageMonitor(interval_seconds=0.05)
    began = time.monotonic()
    monitor.start()
    monitor.close()
    with symbolica_log.capture("test") as captured:
        os.write(1, b"line through the unredirected stdout\n")
    assert time.monotonic() - began < 5.0
    assert captured.warnings() == ()
    assert "line through the unredirected stdout" in capfd.readouterr().out


@_UNRAISABLE
def test_an_abandoned_thread_is_unregistered_and_releases_its_target() -> None:
    """Three bootstraps that fail before signalling: none stays listed by
    ``threading.enumerate()``, none keeps its target alive."""

    class Owner:
        def sample(self) -> None:
            pass

    before = set(threading.enumerate())
    owners = []
    for index in range(3):
        owner = Owner()
        owners.append(weakref.ref(owner))
        thread = _FailingBootstrap(
            owner.sample, name=f"resource-{index}", start_seconds=0.02
        )
        with pytest.raises(ThreadStartError):
            thread.start()
        del thread, owner
    gc.collect()
    assert [t.name for t in threading.enumerate() if t not in before] == []
    assert sum(ref() is not None for ref in owners) == 0


_LATE_READER = textwrap.dedent(
    """
    import fcntl, logging, os, sys, threading, time
    from pyamplicol._internal import threads, symbolica_log

    mode = sys.argv[1]
    threads.START_SECONDS = 0.3
    original = threads.AuxiliaryThread._bootstrap

    def late(self):
        time.sleep(1.0)
        original(self)

    threads.AuxiliaryThread._bootstrap = late
    initial = os.fstat(1).st_ino

    def existing_writer():
        # Writes as soon as standard output changes (or after 1.5 s).
        deadline = time.monotonic() + 1.5
        while os.fstat(1).st_ino == initial and time.monotonic() < deadline:
            time.sleep(0.001)
        if mode == "full":
            os.write(1, b"x" * fcntl.fcntl(1, fcntl.F_GETPIPE_SZ))
        os.write(1, b"output from another active task\\n")

    writer = threading.Thread(target=existing_writer)
    writer.start()
    # Ordinary application console logging on standard output.
    logging.getLogger("pyamplicol").addHandler(logging.StreamHandler(sys.stdout))
    with symbolica_log.capture("reader started late"):
        print("capture body reached", flush=True)
    writer.join()
    print("caller finished", flush=True)
    """
)


@pytest.mark.skipif(platform.system() != "Linux", reason="F_GETPIPE_SZ is Linux")
@pytest.mark.parametrize("mode", ["short", "full"])
def test_a_log_reader_that_starts_late_loses_and_blocks_nothing(mode: str) -> None:
    """The capture's reader does not run within the bound: standard output
    was never redirected, so another thread's output reaches it and the
    startup warning (on a stdout logging handler) cannot block on a full,
    unread pipe."""

    result = subprocess.run(
        [sys.executable, "-c", _LATE_READER, mode],
        capture_output=True,
        text=True,
        timeout=60,
        env=_environment(),
    )
    assert "output from another active task" in result.stdout, result.stderr[-2000:]
    assert "continuing without pyamplicol-symbolica-log" in result.stdout
    assert result.stdout.rstrip().endswith("caller finished")


def _environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(Path(__file__).resolve().parents[2] / "src"), *sys.path]
    )
    return environment


_EXHAUST = textwrap.dedent(
    """
    import ctypes, mmap, time
    from pathlib import Path
    from pyamplicol._internal import threads, symbolica_log
    from pyamplicol.reporting.resources import ResourceUsageMonitor

    threads.START_SECONDS = 2.0
    libc = ctypes.CDLL(None, use_errno=True)
    libc.mmap.restype = ctypes.c_void_p
    libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
                          ctypes.c_int, ctypes.c_int, ctypes.c_long]
    libc.mprotect.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    limit = int(Path("/proc/sys/vm/max_map_count").read_text())
    page = mmap.PAGESIZE
    pages = 2 * limit + 16
    # One reservation, split into a map per other page until the kernel
    # refuses: the process then holds vm.max_map_count memory maps.
    base = libc.mmap(None, pages * page, 0,  # PROT_NONE
                     mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS | 0x4000, -1, 0)
    for i in range(limit + 8):
        if libc.mprotect(base + (2 * i + 1) * page, page, mmap.PROT_READ):
            break
    began = time.monotonic()
    monitor = ResourceUsageMonitor(interval_seconds=0.05)
    monitor.start()
    monitor.close()
    try:
        with symbolica_log.capture("exhausted"):
            pass
    except OSError:
        pass
    print("returned", round(time.monotonic() - began, 1), flush=True)
    """
)


@pytest.mark.skipif(platform.system() != "Linux", reason="vm.max_map_count is Linux")
def test_no_hang_once_the_process_holds_every_memory_map() -> None:
    limit = int(Path("/proc/sys/vm/max_map_count").read_text())
    if limit > 4 * 1048576:
        pytest.skip(f"vm.max_map_count {limit}: too many maps to exhaust cheaply")
    result = subprocess.run(
        [sys.executable, "-c", _EXHAUST],
        capture_output=True,
        text=True,
        timeout=240,
        env=_environment(),
    )
    assert "returned" in result.stdout, (result.returncode, result.stderr[-2000:])
