# SPDX-License-Identifier: 0BSD
"""The compiled code of a SymJIT kernel is shared by every load in a process.

SymJIT never releases the executable pages of the code it compiles, and each
kernel takes its own pages (two memory maps). An on-the-fly artifact loads
its model's kernel library (about a thousand applications for the built-in
SM) at every ``Runtime.load``: before the process-wide cache each load added
about 2,000 memory maps and 8 MB that dropping the runtime never returned,
until the process reached ``vm.max_map_count`` and every later load or
generation failed. A process that holds every memory map raises the typed
``ResourceExhaustedError`` from ``generate`` and ``Runtime.load``.
"""

from __future__ import annotations

import ast
import gc
import json
import os
import platform
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from pyamplicol._rusticol import _symjit_plane_code_cache_len

from pyamplicol import Generator, ModelSource, Runtime
from tools.developer.builtin_sm_ufo_sweep import on_shell_points, run_config

PROCESS = "e+ e- > mu+ mu-"
CYCLES = 20
LINUX = platform.system() == "Linux"


def _maps() -> int:
    with open(f"/proc/{os.getpid()}/maps", "rb") as maps:
        return sum(1 for _ in maps)


def _values(runtime: Runtime) -> list[str]:
    return [
        part.hex()
        for value in runtime.evaluate(on_shell_points(PROCESS))
        for part in (value.real, value.imag)
    ]


@pytest.fixture(scope="module")
def artifact(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("kernel-code-sharing") / "on-the-fly"
    Generator(run_config("on-the-fly", None)).generate(
        [PROCESS], path, model=ModelSource.built_in_sm()
    )
    return path


def test_repeated_loads_compile_the_kernels_once(artifact: Path) -> None:
    Runtime.load(artifact, process=PROCESS).evaluate(on_shell_points(PROCESS))
    gc.collect()
    compiled = _symjit_plane_code_cache_len()
    assert compiled > 0  # the distinct applications of the kernel library
    maps = _maps() if LINUX else 0
    for _ in range(CYCLES):
        runtime = Runtime.load(artifact, process=PROCESS)
        runtime.evaluate(on_shell_points(PROCESS))
        del runtime
        gc.collect()
    assert _symjit_plane_code_cache_len() == compiled
    if LINUX:
        # Before: about 2,000 maps per load (40,000 here).
        assert _maps() - maps < 200


def test_two_live_runtimes_share_the_kernels(artifact: Path) -> None:
    first = Runtime.load(artifact, process=PROCESS)
    compiled = _symjit_plane_code_cache_len()
    maps = _maps() if LINUX else 0
    second = Runtime.load(artifact, process=PROCESS)
    assert _symjit_plane_code_cache_len() == compiled
    if LINUX:
        assert _maps() - maps < 100
    assert _values(first) == _values(second)
    # A run-time parameter of one runtime is not the other's.
    reference = _values(first)
    second.set_model_parameters({"normalization.alpha_ew": 0.008})
    assert _values(second) != reference
    assert _values(first) == reference


_FRESH = textwrap.dedent(
    """
    import json, sys
    from pyamplicol import Runtime
    from tools.developer.builtin_sm_ufo_sweep import on_shell_points

    process = sys.argv[2]
    def values(runtime):
        return [part.hex() for value in runtime.evaluate(on_shell_points(process))
                for part in (value.real, value.imag)]
    runtime = Runtime.load(sys.argv[1], process=process)
    plain = values(runtime)
    runtime.set_model_parameters({"normalization.alpha_ew": 0.008})
    print(json.dumps([plain, values(runtime)]))
    """
)


def _environment() -> dict[str, str]:
    root = Path(__file__).resolve().parents[2]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(root / "src"), str(root), *sys.path]
    )
    return environment


def test_shared_kernels_give_the_values_of_a_fresh_process(artifact: Path) -> None:
    """Bitwise, with and without a run-time parameter change: the cached
    code of this process (loaded many times) against a process that compiles
    the kernels once."""

    for _ in range(3):
        Runtime.load(artifact, process=PROCESS)
    runtime = Runtime.load(artifact, process=PROCESS)
    plain = _values(runtime)
    runtime.set_model_parameters({"normalization.alpha_ew": 0.008})
    changed = _values(runtime)
    fresh = subprocess.run(
        [sys.executable, "-c", _FRESH, str(artifact), PROCESS],
        capture_output=True,
        text=True,
        timeout=600,
        env=_environment(),
        check=True,
    )
    assert json.loads(fresh.stdout.strip().splitlines()[-1]) == [plain, changed]


_EXHAUSTED = textwrap.dedent(
    """
    import ctypes, mmap, sys
    from pathlib import Path
    from pyamplicol import Generator, ModelSource, Runtime
    from pyamplicol.api.errors import ResourceExhaustedError
    from tools.developer.builtin_sm_ufo_sweep import run_config

    artifact, process, output = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    libc = ctypes.CDLL(None, use_errno=True)
    libc.mmap.restype = ctypes.c_void_p
    libc.mmap.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int,
                          ctypes.c_int, ctypes.c_int, ctypes.c_long]
    libc.mprotect.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    limit = int(Path("/proc/sys/vm/max_map_count").read_text())
    page = mmap.PAGESIZE
    base = libc.mmap(None, (2 * limit + 16) * page, 0,
                     mmap.MAP_PRIVATE | mmap.MAP_ANONYMOUS | 0x4000, -1, 0)
    for i in range(limit + 8):
        if libc.mprotect(base + (2 * i + 1) * page, page, mmap.PROT_READ):
            break
    outcomes = []
    for name, call in (
        ("generate", lambda: Generator(run_config("compiled", None)).generate(
            [process], output, model=ModelSource.built_in_sm())),
        ("load", lambda: Runtime.load(artifact, process=process)),
    ):
        try:
            call()
            outcomes.append((name, "served"))
        except ResourceExhaustedError as exc:
            outcomes.append((name, "typed", exc.resource, str(exc)[:80]))
        except BaseException as exc:
            outcomes.append((name, "untyped", type(exc).__name__, str(exc)[:200]))
    print(repr(outcomes), flush=True)
    """
)


@pytest.mark.skipif(not LINUX, reason="vm.max_map_count is Linux")
def test_exhausted_memory_maps_raise_a_typed_error(
    artifact: Path, tmp_path: Path
) -> None:
    # Without the bounded start of the auxiliary threads, generate hangs in
    # the resource monitor's Thread.start once the maps are exhausted.
    pytest.importorskip("pyamplicol._internal.threads")
    limit = int(Path("/proc/sys/vm/max_map_count").read_text())
    if limit > 4 * 1048576:
        pytest.skip(f"vm.max_map_count {limit}: too many maps to exhaust cheaply")
    result = subprocess.run(
        [sys.executable, "-c", _EXHAUSTED, str(artifact), PROCESS, str(tmp_path / "x")],
        capture_output=True,
        text=True,
        timeout=600,
        env=_environment(),
    )
    lines = [line for line in result.stdout.splitlines() if line.startswith("[(")]
    assert lines, (result.returncode, result.stderr[-3000:])
    outcomes = ast.literal_eval(lines[-1])
    for outcome in outcomes:
        assert outcome[1] == "typed", outcomes
        assert outcome[2] == "memory maps"
        assert "memory maps exhausted in this process" in outcome[3]
