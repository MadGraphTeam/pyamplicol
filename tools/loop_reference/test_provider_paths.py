# SPDX-License-Identifier: 0BSD
"""The toolkit refuses provider files outside the configured reference root."""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import provider_paths
import references

OLD = "/nonexistent-old-root/workspace/reference"


@pytest.fixture
def no_access_outside(monkeypatch, tmp_path):
    """Record every lstat/readlink/stat; the test asserts none left tmp_path."""
    seen = []
    for name in ("lstat", "readlink", "stat"):
        original = getattr(os, name)

        def spy(path, *args, _original=original, **kwargs):
            seen.append(os.fspath(path))
            return _original(path, *args, **kwargs)

        monkeypatch.setattr(os, name, spy)
    yield seen
    assert not [p for p in seen if str(p).startswith(OLD.split("/workspace")[0])]


def shared_library(path, runpath):
    """A minimal shared library with the given RUNPATH (gcc, as for the drivers)."""
    source = path.with_suffix(".c")
    source.write_text("int answer(void) { return 42; }\n")
    gcc = shutil.which("gcc")
    assert gcc, "gcc is required (the toolkit compiles its provider drivers)"
    subprocess.run(
        [
            gcc,
            "-shared",
            "-fPIC",
            str(source),
            "-o",
            str(path),
            "-Wl,--enable-new-dtags",
            f"-Wl,-rpath,{runpath}",
        ],
        check=True,
    )
    return path


def test_paths_outside_the_root_are_refused_without_being_opened(
    tmp_path, no_access_outside
):
    root = tmp_path / "reference"
    (root / "sources/lib").mkdir(parents=True)
    (root / "sources/lib/libcts.a").write_text("")
    (root / "sources/old").symlink_to(OLD + "/sources/lib")
    roots = [root]
    assert provider_paths.foreign(root / "sources/lib/libcts.a", roots) is None
    assert provider_paths.foreign("/nix/store/x-glibc/lib", roots) is None
    assert (
        provider_paths.foreign(OLD + "/sources/lib/libninja.a", roots)
        == OLD + "/sources/lib/libninja.a"
    )
    # A symbolic link inside the root that leaves it is followed by its text only.
    assert (
        provider_paths.foreign(root / "sources/old/libninja.a", roots)
        == OLD + "/sources/lib/libninja.a"
    )
    with pytest.raises(provider_paths.ForeignProviderPath, match="libninja"):
        provider_paths.check(
            [root / "sources/lib/libcts.a", OLD + "/sources/lib/libninja.a"],
            roots,
            strict=True,
        )


def test_without_a_reference_root_a_violation_is_a_warning(tmp_path, capsys):
    provider_paths.check([OLD + "/x"], [tmp_path], strict=False)
    assert "warning:" in capsys.readouterr().err


def test_runpath_into_another_root_is_refused(tmp_path, no_access_outside):
    root = tmp_path / "reference"
    (root / "collier").mkdir(parents=True)
    shared_library(root / "collier/libcollier.so", "$ORIGIN")
    good = shared_library(
        root / "librecola.so", f"{root / 'collier'}:/nix/store/x-glibc/lib"
    )
    bad = shared_library(
        root / "libold.so", f"{OLD}/sources/COLLIER-1.2.8:{root / 'collier'}"
    )
    provider_paths.check([], [root], libraries=[good], strict=True)
    with pytest.raises(provider_paths.ForeignProviderPath, match=r"COLLIER-1\.2\.8"):
        provider_paths.check([], [root], libraries=[bad], strict=True)


def test_reference_run_refuses_a_madloop_export_linking_another_roots_archives(
    tmp_path, no_access_outside
):
    root = tmp_path / "reference"
    definitions = (
        root / "runs/p/madloop-export/SubProcesses/MadLoop_makefile_definitions"
    )
    definitions.parent.mkdir(parents=True)
    ninja = f"{OLD}/sources/HEPTools/ninja/lib/libninja"
    definitions.write_text(f"LOOP_LIBS = $(LIBDIR)libcts.$(libext) {ninja}.$(libext)\n")
    args = argparse.Namespace(
        provider="madloop", madloop_export=definitions.parents[1], mg5=None
    )
    with pytest.raises(
        provider_paths.ForeignProviderPath, match=re.escape(ninja + ".a")
    ):
        references.check_provider_paths(args, root)
    definitions.write_text("LOOP_LIBS = $(LIBDIR)libcts.$(libext)\n")
    references.check_provider_paths(args, root)


def test_reference_root_comes_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv(provider_paths.ENVIRONMENT, str(tmp_path))
    assert provider_paths.reference_root() == tmp_path
    assert provider_paths.reference_root(tmp_path / "other") == tmp_path / "other"
    monkeypatch.delenv(provider_paths.ENVIRONMENT)
    assert provider_paths.reference_root() is None
