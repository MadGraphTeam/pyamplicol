# SPDX-License-Identifier: 0BSD
"""Compiled code on reused pages computes what it should.

Since SymJIT 2.28.4 the pages of dropped machine code are freed and reused
for the next kernel; on aarch64 that needs an instruction-cache flush
(SymJIT 2.28.5), or the core may run the previous kernel's instructions.
The check compiles, evaluates and drops distinct kernels and reloads an
on-the-fly artifact, comparing every value bit for bit. CI runs the same
check on each architecture's consumer job (``tools/ci/eager_portability.py
consume``, macOS arm64 included).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyamplicol import Generator, ModelSource
from tools.ci.eager_portability import reused_code_pages_check
from tools.developer.builtin_sm_ufo_sweep import on_shell_points, run_config

PROCESS = "e+ e- > mu+ mu-"


@pytest.fixture(scope="module")
def artifact(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("reused-code-pages") / "on-the-fly"
    Generator(run_config("on-the-fly", None)).generate(
        [PROCESS], path, model=ModelSource.built_in_sm()
    )
    return path


def test_kernels_on_reused_code_pages_keep_their_values(artifact: Path) -> None:
    counts = reused_code_pages_check(
        artifact, on_shell_points(PROCESS)[0], process="e_e_to_mu_mu"
    )
    assert counts == {"kernels": 40, "load_cycles": 20}
