# SPDX-License-Identifier: 0BSD
"""The fd-1 capture of known dependency log lines (m-lit ux-besteffort;
ux-polish item 5): known lines are counted, every other byte is forwarded
unchanged and promptly (a carriage-return progress line at once, any other
partial line once the pipe is quiet), and leaving the capture never waits
indefinitely for a descendant that keeps the redirected descriptor."""

from __future__ import annotations

import os
import subprocess
import sys
import time

from pyamplicol._internal import symbolica_log

KNOWN = (
    b"\x1b[33m WARN\x1b[0m symbolica::coefficient: "
    b"Created infinity by raising 0 to the power of -1\n"
)


def test_known_lines_are_counted_and_the_rest_forwarded(capfd):
    with symbolica_log.capture("generate") as sink:
        os.write(1, b"before\n" + KNOWN + KNOWN + b"after\n")
    out = capfd.readouterr().out
    assert out == "before\nafter\n"
    (warning,) = sink.warnings()
    assert (warning.kind, warning.count, warning.where) == (
        "symbolica::coefficient",
        2,
        "generate",
    )


def test_partial_lines_are_forwarded_promptly(capfd):
    with symbolica_log.capture("check"):
        os.write(1, b"progress 10%\r")
        time.sleep(0.3)
        assert capfd.readouterr().out == "progress 10%\r"
        os.write(1, b"no newline yet")
        time.sleep(0.3)
        assert capfd.readouterr().out == "no newline yet"
        os.write(1, b" and the rest\n")
    assert capfd.readouterr().out == " and the rest\n"


def test_a_lingering_descendant_does_not_block_the_exit(capfd):
    start = time.monotonic()
    with symbolica_log.capture("generate"):
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import sys, time; time.sleep(4); sys.stdout.write('late\\n')",
            ]
        )
    left = time.monotonic() - start
    try:
        assert left < symbolica_log.LINGER_SECONDS + 1.5
    finally:
        child.wait(timeout=30)
    time.sleep(0.3)
    # The descendant's output is still forwarded, unchanged.
    assert "late\n" in capfd.readouterr().out


def _count(sink):
    return sum(warning.count for warning in sink.warnings())


def test_a_caller_arriving_during_setup_waits_and_is_counted(monkeypatch, capfd):
    """The first caller's reader is held at its bootstrap until a second
    caller (another thread) has entered its capture; the second caller's
    known line, written as soon as its block starts, is counted with the
    first's (it entered before standard output was redirected, and was
    printed uncounted, when it did not wait for the setup)."""

    import threading

    from pyamplicol._internal import threads

    monkeypatch.setattr(threads, "START_SECONDS", 6.0)
    boot_requested, second_arrives = threading.Event(), threading.Event()
    original = threads.AuxiliaryThread._bootstrap

    def held(self):
        boot_requested.set()
        if second_arrives.wait(4):
            time.sleep(0.3)  # the second caller is inside capture() by now
        original(self)

    monkeypatch.setattr(threads.AuxiliaryThread, "_bootstrap", held)
    sinks = []

    def second():
        assert boot_requested.wait(4)
        second_arrives.set()
        with symbolica_log.capture("second caller") as sink:
            os.write(1, KNOWN)
        sinks.append(sink)

    worker = threading.Thread(target=second)
    worker.start()
    with symbolica_log.capture("first caller") as sink:
        os.write(1, KNOWN)
        worker.join(10)
    assert sinks == [sink]
    assert _count(sink) == 2
    assert "Created infinity" not in capfd.readouterr().out


def test_two_concurrent_callers_count_both_lines(capfd):
    """Two worker threads enter their captures together and each writes one
    known line while both are in scope: both lines are counted, every time
    (117 of 120 pairs counted one when a second caller did not wait for the
    first caller's setup)."""

    import threading
    from concurrent.futures import ThreadPoolExecutor

    def emit(start, finish):
        start.wait(3)
        with symbolica_log.capture("simultaneous caller") as sink:
            os.write(1, KNOWN)
            finish.wait(3)
        return sink

    counts = []
    with ThreadPoolExecutor(2) as pool:
        for _ in range(40):
            start, finish = threading.Barrier(2), threading.Barrier(2)
            first = pool.submit(emit, start, finish)
            second = pool.submit(emit, start, finish)
            sink = first.result()
            assert second.result() is sink
            counts.append(_count(sink))
    assert counts == [2] * 40
    assert "Created infinity" not in capfd.readouterr().out


def test_a_failed_setup_leaves_no_stale_capture(monkeypatch, capfd):
    """A MemoryError while the first caller installs the loader filter (a
    process out of memory) propagates, and the next capture is a fresh one:
    it counts its own line at once instead of joining a stale sink and
    waiting for a setup that never comes."""

    import logging

    import pytest

    from pyamplicol._internal import threads

    monkeypatch.setattr(threads, "START_SECONDS", 10.0)
    loader = logging.getLogger(symbolica_log.LOADER_LOGGER)
    original = loader.addFilter
    calls = []

    def failing_once(flt):
        calls.append(flt)
        if len(calls) == 1:
            raise MemoryError
        original(flt)

    monkeypatch.setattr(loader, "addFilter", failing_once)
    with pytest.raises(MemoryError), symbolica_log.capture("failed setup"):
        pass
    began = time.monotonic()
    with symbolica_log.capture("next caller") as sink:
        os.write(1, KNOWN)
    assert time.monotonic() - began < 5.0
    assert sink.where == "next caller"
    assert _count(sink) == 1
    assert symbolica_log._FILTER not in loader.filters
