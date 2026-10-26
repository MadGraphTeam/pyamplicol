# SPDX-License-Identifier: 0BSD
"""Provider files must come from the configured reference root.

A provider tree that was built under one root and then moved still names
files of its old place: the RUNPATH of its shared libraries, the reducer
archives of a MadLoop export (``MadLoop_makefile_definitions``), OpenLoops'
compiled-in installation path. The loader, the linker or the provider then
silently reads the old tree (this happened after the 2026-10-24 move of the
working root). ``check`` lists every such path that lies outside the allowed
roots: the configured reference root (``--reference-root`` or
``LOOP_REFERENCE_ROOT``), the explicitly given provider trees where a runner
takes them, and the system prefixes. A path outside them is judged by its text
and never opened; symbolic links are followed one component at a time and
only while they stay inside. With a configured reference root a violation is
an error, without one a warning.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

ENVIRONMENT = "LOOP_REFERENCE_ROOT"
SYSTEM_PREFIXES = ("/nix/store", "/usr", "/lib", "/lib64")
MAX_LINKS = 40


class ForeignProviderPath(RuntimeError):
    """A provider file lies outside the configured reference root."""


def reference_root(explicit=None):
    """The configured reference root (absolute, normalised) or None."""
    value = explicit if explicit is not None else os.environ.get(ENVIRONMENT)
    return Path(os.path.abspath(value)) if value else None


def _inside(path, directory):
    path, directory = str(path), str(directory).rstrip("/") or "/"
    return path == directory or path.startswith(directory + "/") or directory == "/"


def _allowed(path, roots):
    return any(_inside(path, root) for root in (*roots, *SYSTEM_PREFIXES))


def _ancestor(path, roots):
    return any(_inside(root, path) for root in roots)


def foreign(path, roots):
    """None when ``path`` resolves inside ``roots`` (or a system prefix),
    otherwise the first path outside them: the path itself or the target of a
    symbolic link on the way. Only paths already known to lie inside (or above)
    an allowed root are ever looked at."""
    roots = [os.path.normpath(os.path.abspath(r)) for r in roots]
    path = os.path.normpath(os.path.abspath(str(path)))
    for _ in range(MAX_LINKS):
        if not _allowed(path, roots):
            return path
        if any(_inside(path, p) for p in SYSTEM_PREFIXES):
            return None
        parts = Path(path).parts
        current = parts[0]
        for index, part in enumerate(parts[1:], 1):
            current = os.path.join(current, part)
            if not _allowed(current, roots):
                if _ancestor(current, roots):
                    continue  # above a root: the root's own spelling is trusted
                return current
            if os.path.islink(current):
                target = os.path.join(os.path.dirname(current), os.readlink(current))
                path = os.path.normpath(os.path.join(target, *parts[index + 1 :]))
                break
        else:
            return None
    return path  # a symbolic-link loop is not a provider path either


def elf_search_path(library):
    """The RUNPATH/RPATH entries of an ELF object, ``$ORIGIN`` expanded."""
    text = subprocess.run(
        ["readelf", "-d", "-W", str(library)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    origin = os.path.dirname(os.path.abspath(str(library)))
    entries = []
    for value in re.findall(
        r"\((?:RUNPATH|RPATH)\)\s+Library r(?:un)?path: \[([^\]]*)\]", text
    ):
        for entry in value.split(":"):
            if entry:
                entries.append(re.sub(r"\$(ORIGIN|\{ORIGIN\})", origin, entry))
    return entries


def elf_needed(library):
    text = subprocess.run(
        ["readelf", "-d", "-W", str(library)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return re.findall(r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]", text)


def library_violations(library, roots):
    """Foreign RUNPATH entries of ``library`` and, recursively, of the
    libraries it needs that are found through its allowed entries."""
    violations, pending, seen = [], [Path(library)], set()
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        entries = elf_search_path(current)
        for entry in entries:
            bad = foreign(entry, roots)
            if bad is not None:
                violations.append(f"{current}: RUNPATH entry {entry}")
        for name in elf_needed(current):
            for entry in entries:
                candidate = Path(entry) / name
                if (
                    foreign(entry, roots) is None
                    and not any(_inside(entry, p) for p in SYSTEM_PREFIXES)
                    and candidate.is_file()
                ):
                    pending.append(candidate)
                    break
    return violations


def check(paths, roots, libraries=(), what="provider", strict=None):
    """Raise ``ForeignProviderPath`` (``strict``) or warn on stderr for every
    path in ``paths`` and every RUNPATH entry of ``libraries`` outside ``roots``.
    ``strict`` defaults to whether a reference root is configured."""
    roots = [r for r in roots if r is not None]
    if strict is None:
        strict = reference_root() is not None
    violations = []
    for path in paths:
        bad = foreign(path, roots)
        if bad is not None:
            violations.append(
                f"{path}"
                + (f" (resolves to {bad})" if bad != os.path.abspath(str(path)) else "")
            )
    for library in libraries:
        bad = foreign(library, roots)
        if bad is not None:
            violations.append(f"{library}")
            continue
        violations += library_violations(library, roots)
    if not violations:
        return
    allowed = ", ".join(map(str, roots)) or "(none)"
    message = (
        f"{what} files outside the reference roots {allowed} (a tree built under "
        "another root; relocate it): " + "; ".join(violations)
    )
    if strict:
        raise ForeignProviderPath(message)
    print(f"warning: {message}", file=sys.stderr)
