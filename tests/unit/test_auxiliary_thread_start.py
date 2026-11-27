# SPDX-License-Identifier: 0BSD
"""An auxiliary thread that cannot start never blocks its caller.

``threading.Thread.start`` waits without a timeout for the new thread to
signal that it runs; a thread whose bootstrap fails first (``MemoryError``
once the process holds ``vm.max_map_count`` memory maps) left
``generate`` hanging for good in the resource monitor's start. The start of
pyAmpliCol's auxiliary threads is bounded, the work continues without them.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import textwrap
import threading
import time
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
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(Path(__file__).resolve().parents[2] / "src"), *sys.path]
    )
    result = subprocess.run(
        [sys.executable, "-c", _EXHAUST],
        capture_output=True,
        text=True,
        timeout=240,
        env=environment,
    )
    assert "returned" in result.stdout, (result.returncode, result.stderr[-2000:])
