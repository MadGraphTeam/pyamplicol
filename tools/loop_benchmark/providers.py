# SPDX-License-Identifier: 0BSD
"""Provider timing for gate G1 in production mode (REQUIREMENTS_ADDENDUM D).

MadLoop, Recola and OpenLoops evaluate the first ``--points`` points of the
frozen stream (``streams.py``; decimal text ``streams.binary64``) on one
pinned core, through the drivers and settings of the required-references
toolkit (``tools/loop_reference/references.py``, ``required_spec``) with the
process specification of ``processes.json``. Only the pole settings differ
from that campaign, as the addendum asks:

- **OpenLoops**: ``truepoles 0`` (its production default: Collier cache on,
  poles from the I-operator, the default stability system); OpenLoops has no
  mode without poles. Its finite part equals the ``truepoles 1`` campaign's
  (DESIGN Appendix C).
- **Recola**: ``compute_ir_poles 0`` (one ``compute_amplitude`` per point
  instead of three) with the Collier global cache as in production
  (``collier_cache``). The toolkit driver gets an ``irpoles`` command for
  this (the copy patched here; ``tools/loop_reference/recola_driver.f90`` is
  not changed). Without poles Recola's finite part stays in its own
  convention; ``gate.py`` adds ``pi^2/6 D`` with the universal double pole
  of the massless coloured legs for the value comparison.
- **MadLoop**: its production setting (``MLStabThres`` and the default
  stability test, ``--madloop-accuracy`` <= 0 in the toolkit), on an export
  built with MG5's production Fortran flags, with ``COLLIERGlobalCache`` as
  in production (``collier_cache``); MadLoop always returns its poles.

Caches are those of production (REQUIREMENTS_ADDENDUM D). The one exception
is the documented COLLIER global-cache defect at N = 7 of the releases
``COLLIER_CACHE_DEFECT`` (the toolkit's ``UNCACHED_LEG_THRESHOLD``): the
cache is switched off at seven legs or more only when the provider links
such a release (MG5_aMC 3.7.0's HEPTools COLLIER 1.2.9 for MadLoop), never
for another one (Recola's COLLIER 1.2.8). The decision and the linked
release are part of every record (``collier_cache``).

A provider tree built before its reference root moved still names files of
the old root (a MadLoop export's static reducers, the RUNPATH of Recola's
shared libraries, OpenLoops' compiled-in installation path). Such files are
never opened: each is taken from the same place under the current root
(``relocated``; Recola through ``LD_LIBRARY_PATH``, OpenLoops through
``OpenLoopsPath``, MadLoop by linking the relocated archives), and a Recola
run whose resolved libraries lie outside the root is refused. TRANSITIONAL:
retired once the reference trees name the current root (README).

Every driver evaluates point 1 once untimed (initialisation), then times
points 2..n and 1 one by one. Per point the driver's own timer is recorded;
the provider's per-point time is the mean over the timed points (providers
have no batch API: the per-point time does not depend on B). Generation and
initialisation (Recola's ``generate``, MadLoop's first call, OpenLoops'
library load) are recorded separately.

Provider trees follow the toolkit's layout (``run_required.sh``): the
reference root (``--reference-root``, default ``$LOOP_REFERENCE_ROOT``) holds
``sources/MG5_aMC_v3_7_0``, ``sources/recola2-2.3.0`` and
``sources/OpenLoops-2.1.5`` (``--mg5``, ``--recola``, ``--openloops`` or
``LOOP_REFERENCE_RECOLA`` / ``LOOP_REFERENCE_OPENLOOPS`` override them), and
the MadLoop export of a process is ``madloop.export`` of ``processes.json``
relative to that root (``--madloop-export`` overrides it). A provider that a
process specification marks ``unavailable`` (no installed library, an export
beyond HANDOFF §0.1) is recorded with that reason, never silently dropped.

Usage:
    python -m tools.loop_benchmark providers gg_gggg --cpu 150 \\
        --work DIR --points 16 [--providers openloops recola madloop] \\
        [--reference-root ROOT] [--madloop-export EXPORT] --json OUT.json
"""

from __future__ import annotations

import contextlib
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from . import streams


class Trees:
    """The provider trees of one run (module docstring)."""

    def __init__(self, options: Any) -> None:
        root = options.reference_root or os.environ.get("LOOP_REFERENCE_ROOT")
        if root is None:
            raise SystemExit("set --reference-root or LOOP_REFERENCE_ROOT")
        self.root = Path(root).resolve()
        sources = self.root / "sources"
        self.mg5 = Path(options.mg5 or sources / "MG5_aMC_v3_7_0")
        self.openloops = Path(
            options.openloops
            or os.environ.get("LOOP_REFERENCE_OPENLOOPS")
            or sources / "OpenLoops-2.1.5"
        )
        self.recola = Path(
            options.recola
            or os.environ.get("LOOP_REFERENCE_RECOLA")
            or sources / "recola2-2.3.0"
        )

    def madloop_export(self, spec: dict, override: Path | None) -> Path | None:
        if override is not None:
            return Path(override)
        relative = spec.get("madloop", {}).get("export")
        return self.root / relative if relative else None


# COLLIER releases with the global-cache defect at N = 7 (NinjaRS owners;
# DESIGN "Provider production columns"; the toolkit's UNCACHED_LEG_THRESHOLD
# names them). Every other release keeps the production cache.
COLLIER_CACHE_DEFECT = frozenset({"1.2.9", "1.2.10"})


def collier_cache(legs: int, version: str | None) -> dict[str, Any]:
    """The protocol's Collier global cache for a ``legs``-leg process of a
    provider linking COLLIER ``version`` (module docstring): ``on`` True as
    in production, False only for a release of ``COLLIER_CACHE_DEFECT`` at
    seven legs or more, None when the release is unknown there (no decision:
    a timing run refuses it)."""

    threshold = _references().UNCACHED_LEG_THRESHOLD
    if legs < threshold:
        on, reason = True, f"below {threshold} legs"
    elif version is None:
        on, reason = None, f"unknown COLLIER release at {threshold} legs or more"
    elif version in COLLIER_CACHE_DEFECT:
        on, reason = False, f"COLLIER {version} global cache defect at N = 7"
    else:
        on, reason = True, f"COLLIER {version} has no N = 7 cache defect"
    return {"on": on, "collier": version, "reason": reason}


def _collier_version(text: str | None) -> str | None:
    """The COLLIER release named in a provider's version text
    (``... / libcollier.so 1.2.8``, ``... / Collier 1.2.8``)."""

    match = re.search(r"collier\S*\s+(\d+(?:\.\d+)+)", text or "", re.IGNORECASE)
    return match.group(1) if match else None


def _inside(path: str, directory: Path) -> bool:
    return path == str(directory) or path.startswith(str(directory) + os.sep)


def relocated(path: str | Path, root: Path) -> Path:
    """``path`` when it lies under the reference root ``root`` or in the Nix
    store; otherwise the file or directory at its longest tail that exists
    under ``root`` and starts with one of the root's entries (a tree built
    before the root moved names files of the old root, module docstring).
    Only paths under ``root`` are looked at: the original is never opened or
    stat'ed."""

    text = os.path.normpath(str(path))
    if _inside(text, root) or _inside(text, Path("/nix/store")):
        return Path(text)
    parts = Path(text).parts[1:]
    top = {entry.name for entry in root.iterdir()}
    for start in range(len(parts)):
        if parts[start] not in top:
            continue
        candidate = root.joinpath(*parts[start:])
        if candidate.exists():
            return candidate
    raise RuntimeError(f"{text} lies outside the reference root {root}")


def _elf_dynamic(library: Path) -> dict[str, list[str]]:
    """``NEEDED`` and ``RUNPATH``/``RPATH`` entries of an ELF object, read
    from its dynamic section (nothing is loaded)."""

    text = subprocess.run(
        ["readelf", "-d", str(library)], capture_output=True, text=True, check=True
    ).stdout
    needed = re.findall(r"\(NEEDED\)\s+Shared library: \[([^\]]+)\]", text)
    paths = re.findall(
        r"\((?:RUNPATH|RPATH)\)\s+Library r(?:un)?path: \[([^\]]*)\]", text
    )
    return {
        "needed": needed,
        "runpath": [entry for item in paths for entry in item.split(":") if entry],
    }


def library_path(library: Path, root: Path) -> list[Path]:
    """The directories a program linking ``library`` (a provider's shared
    library under ``root``) searches first, at link time (``-rpath-link``)
    and at run time (``LD_LIBRARY_PATH`` of that program only): the RUNPATH
    entries of the library and of every dependency found through them, in
    order, each ``relocated`` under ``root``. With them the linker and the
    loader resolve every dependency before they would search a RUNPATH entry
    of the old root."""

    dirs: list[Path] = []
    pending, seen = [library], set()
    while pending:
        current = pending.pop(0)
        if current in seen:
            continue
        seen.add(current)
        dynamic = _elf_dynamic(current)
        for entry in dynamic["runpath"]:
            directory = relocated(entry, root)
            if directory not in dirs:
                dirs.append(directory)
        for name in dynamic["needed"]:
            for directory in dirs:
                if _inside(str(directory), root) and (directory / name).is_file():
                    pending.append(directory / name)
                    break
    return dirs


def loaded_libraries(binary: Path, pattern: str) -> dict[str, dict[str, Any]]:
    """The shared libraries the loader resolves for ``binary`` in the
    current environment (its own loader in trace mode,
    ``LD_TRACE_LOADED_OBJECTS``: unlike ``ldd`` it shares the program's C
    library with ``LD_LIBRARY_PATH``), with ``references.library_version``,
    for the sonames matching ``pattern``."""

    references = _references()
    text = subprocess.run(
        [str(binary)],
        env={**os.environ, "LD_TRACE_LOADED_OBJECTS": "1"},
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    found = {}
    for line in text.splitlines():
        match = re.match(r"\s*(\S+) => (\S+)", line)
        if match and re.search(pattern, match.group(1)):
            path = Path(match.group(2))
            found[match.group(1)] = {
                "path": str(path),
                "version": references.library_version(path),
            }
    return found


@contextlib.contextmanager
def _environment(**values: str):
    """``os.environ`` with ``values`` set (the toolkit's ``run_native`` and
    ``ldd`` inherit it), restored afterwards."""

    saved = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _madloop_libraries(export: Path, root: Path) -> list[Path]:
    """The toolkit's ``build.madloop_libraries`` (the export's static
    reducers, ``LOOP_LIBS`` of ``MadLoop_makefile_definitions``) with every
    archive ``relocated`` under ``root``: an export built before the root
    moved names the old root's HEPTools archives, which the toolkit's helper
    would stat and link."""

    import shlex

    definitions = export / "SubProcesses/MadLoop_makefile_definitions"
    rows = [
        line.split("=", 1)[1].strip()
        for line in definitions.read_text().splitlines()
        if line.startswith("LOOP_LIBS =")
    ]
    if len(rows) != 1:
        raise ValueError("MadLoop export has no unique LOOP_LIBS definition")
    value = rows[0].replace("$(LIBDIR)", str(export / "lib") + "/")
    value = value.replace("$(libext)", "a")
    if "$" in value or value.endswith("\\"):
        raise ValueError("unsupported MadLoop static-library definition")
    libraries = [relocated(item, root) for item in shlex.split(value)]
    if not libraries or any(not item.is_file() for item in libraries):
        raise ValueError("MadLoop static reducer libraries are missing")
    return libraries


@contextlib.contextmanager
def _relocated_madloop_build(root: Path):
    """The toolkit's ``build_madloop`` linking ``_madloop_libraries`` (its
    helper is looked up in module ``build`` at each call)."""

    _references()
    import build

    original = build.madloop_libraries
    build.madloop_libraries = lambda export: _madloop_libraries(Path(export), root)
    try:
        yield
    finally:
        build.madloop_libraries = original


def _madloop_collier(export: Path, root: Path) -> str | None:
    """The COLLIER release of an export's static reducers (MG5_aMC's HEPTools
    install: a ``COLLIER-<release>`` directory beside ``libcollier.a``)."""

    for library in _madloop_libraries(export, root):
        if library.name.startswith("libcollier"):
            return _references().library_version(library)
    return None


def unavailable(spec: dict, provider: str) -> str | None:
    """The specification's reason why ``provider`` has no timing, if any."""

    return spec.get(provider, {}).get("unavailable")


def _references() -> Any:
    reference = str(streams.REFERENCE)
    if reference not in sys.path:
        sys.path.insert(0, reference)
    import references

    return references


def _points(key: str, count: int) -> dict[str, Any]:
    """The first ``count`` stream points in the toolkit's points format."""

    stream = streams.load(key)
    return {
        "pdgs": stream["pdgs"],
        "points": streams.binary64(stream, count),
        "mu_r": stream["mu_r"][:count],
    }


def _summary(rows: list[dict[str, Any]], extra: dict[str, Any], wall: float) -> dict:
    seconds = [row["seconds"] for row in rows]
    return {
        "points": len(rows),
        "mean_seconds_per_point": statistics.fmean(seconds),
        "median_seconds_per_point": statistics.median(seconds),
        "min_seconds_per_point": min(seconds),
        "max_seconds_per_point": max(seconds),
        "rows": rows,
        "setup": extra,
        "process_wall_seconds": wall,
    }


def openloops(
    spec: dict, points: dict, work: Path, cpu: int, trees: Trees
) -> dict[str, Any]:
    references = _references()
    openloops_tree = trees.openloops
    run = work / "openloops-run"
    run.mkdir(parents=True, exist_ok=True)
    binary = run / "openloops-driver"
    if not binary.exists():
        subprocess.run(
            [
                "g++",
                "-O2",
                "-std=c++17",
                str(streams.REFERENCE / "openloops_driver.cpp"),
                "-I",
                str(openloops_tree / "include"),
                "-L",
                str(openloops_tree / "lib"),
                f"-Wl,-rpath,{openloops_tree / 'lib'}",
                "-lopenloops",
                "-o",
                str(binary),
            ],
            check=True,
            cwd=run,
        )
    commands = [
        "int truepoles 0" if c == "int truepoles 1" else c
        for c in references.openloops_commands(spec)
    ]
    if "int truepoles 0" not in commands:
        raise RuntimeError("the toolkit's OpenLoops commands changed")
    count = len(points["points"])
    lines = [*commands, f"points {count}", *references.point_lines(points)]
    stdin = "\n".join(lines) + "\n"
    # OpenLoops finds its process libraries under its compiled-in install
    # path unless OpenLoopsPath names another (ol_interface.F90); after a
    # move of the root the compiled-in one is the old root's.
    with _environment(OpenLoopsPath=str(openloops_tree)):
        stdout, wall = references.run_native(
            [str(binary)], stdin, run, run / "output.log", cpu
        )
    rows, extra = references.parse_rows(stdout, "openloops", count)
    library = spec["openloops"]["library"]
    return {
        "provider": "openloops",
        "mode": "production: truepoles 0 (Collier cache, I-operator poles, "
        "default stability)",
        "version": f"OpenLoops {references.openloops_release(openloops_tree)}",
        "library": {
            "name": library,
            **references.openloops_library_version(openloops_tree, library),
        },
        "commands": commands,
        "install_path": "OpenLoopsPath = the OpenLoops tree",
        **_summary(rows, extra, wall),
    }


def _recola_driver(run: Path, recola_tree: Path, link: list[Path]) -> Path:
    """The toolkit's Recola driver with an ``irpoles <0|1>`` command, linked
    with ``link`` (``library_path``) as the linker's search path for the
    libraries Recola's own need (before their RUNPATH)."""

    source = (streams.REFERENCE / "recola_driver.f90").read_text()
    patches = (
        (
            "  integer :: stored_nf = -1\n",
            "  integer :: stored_nf = -1\n  integer :: irpoles = 1\n",
        ),
        (
            "    case ('cache')",
            "    case ('irpoles')\n      read(line, *) keyword, irpoles\n"
            "    case ('cache')",
        ),
        (
            "      call set_compute_ir_poles_rcl(1)",
            "      call set_compute_ir_poles_rcl(irpoles)",
        ),
        (
            "    call get_squared_amplitude_rcl(1, pow_nlo, 'NLO-IR1', result(3))\n"
            "    call get_squared_amplitude_rcl(1, pow_nlo, 'NLO-IR2', result(4))",
            "    result(3:4) = 0d0\n    if (irpoles == 1) then\n"
            "      call get_squared_amplitude_rcl(1, pow_nlo, 'NLO-IR1', result(3))\n"
            "      call get_squared_amplitude_rcl(1, pow_nlo, 'NLO-IR2', result(4))\n"
            "    end if",
        ),
    )
    for old, new in patches:
        if source.count(old) != 1:
            raise RuntimeError(
                f"the toolkit's Recola driver changed near {old.strip()!r}"
            )
        source = source.replace(old, new)
    path = run / "recola_driver_production.f90"
    path.write_text(source)
    binary = run / "recola-driver-production"
    subprocess.run(
        [
            "gfortran",
            "-O2",
            "-ffree-line-length-none",
            str(path),
            "-I",
            str(recola_tree / "include"),
            "-L",
            str(recola_tree),
            f"-Wl,-rpath,{recola_tree}",
            *(f"-Wl,-rpath-link,{directory}" for directory in link),
            "-lrecola",
            "-o",
            str(binary),
        ],
        check=True,
        cwd=run,
    )
    return binary


def recola(
    spec: dict, points: dict, work: Path, cpu: int, trees: Trees
) -> dict[str, Any]:
    references = _references()
    recola_tree = trees.recola
    run = work / "recola-run"
    run.mkdir(parents=True, exist_ok=True)
    root = trees.root
    # The driver's own C library (its compiler's, through its interpreter)
    # serves Recola as well: a C library directory of Recola's build on the
    # search path would pair the driver's loader with another libc (a
    # glibc 2.42 loader with glibc 2.40's libc.so.6: "undefined symbol
    # __nptl_change_stack_perm", exit 127).
    dirs = [
        d
        for d in library_path(recola_tree / "librecola.so", root)
        if not (d / "libc.so.6").is_file()
    ]
    binary = _recola_driver(run, recola_tree, dirs)
    search = os.pathsep.join(
        [*map(str, dirs), *filter(None, [os.environ.get("LD_LIBRARY_PATH")])]
    )
    with _environment(LD_LIBRARY_PATH=search):
        linked = loaded_libraries(binary, r"recola|collier|modelfile")
        outside = [v["path"] for v in linked.values() if not _inside(v["path"], root)]
        collier = [v["version"] for k, v in linked.items() if "collier" in k]
        if outside or len(collier) != 1:
            raise RuntimeError(
                f"Recola's libraries do not resolve under {root}: {sorted(linked)}"
            )
        cache = collier_cache(len(spec["pdgs"]), collier[0])
        if cache["on"] is None:
            raise RuntimeError(f"no Collier cache decision: {cache['reason']}")
        commands = references.recola_commands(spec, points, not cache["on"])
        commands.insert(commands.index("generate"), "irpoles 0")
        count = len(points["points"])
        lines = [*commands, f"points {count}", *references.point_lines(points)]
        stdin = "\n".join(lines) + "\n"
        stdout, wall = references.run_native(
            [str(binary)], stdin, run, run / "output.log", cpu
        )
    rows, extra = references.parse_rows(stdout, "recola", count)
    return {
        "provider": "recola",
        "mode": "production: compute_ir_poles 0, Collier global cache "
        + ("on" if cache["on"] else "off")
        + f" ({cache['reason']})",
        "version": "Recola2 (tree "
        + recola_tree.name
        + ") / "
        + " / ".join(f"{k} {v['version']}" for k, v in sorted(linked.items())),
        "collier_cache": cache,
        "libraries": {
            k: str(Path(v["path"]).relative_to(root)) for k, v in sorted(linked.items())
        },
        "commands": commands,
        "finite_convention": "Recola (Gamma(1+eps)); MadLoop's adds pi^2/6 D",
        **_summary(rows, extra, wall),
    }


def _prepare_madloop(
    spec: dict, export: Path, run: Path, trees: Trees
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The toolkit's ``prepare_madloop_run`` (it sets ``COLLIERGlobalCache``
    to 0 at seven legs or more) with the export's own production value
    restored unless the export's COLLIER release has the cache defect
    (``collier_cache``)."""

    references = _references()
    legs = len(spec["pdgs"])
    settings = references.prepare_madloop_run(spec, export, run, trees.mg5, legs)
    cache = collier_cache(legs, _madloop_collier(export, trees.root))
    if cache["on"] is None:
        raise RuntimeError(f"no Collier cache decision: {cache['reason']}")
    params = run / "SubProcesses/MadLoop5_resources/MadLoopParams.dat"
    pattern = r"(#COLLIERGlobalCache\s*\n)\s*(-?\d+)"
    production = re.search(
        pattern,
        (export / "SubProcesses/MadLoop5_resources/MadLoopParams.dat").read_text(),
    )
    if cache["on"] and production is not None:
        text, n = re.subn(pattern, rf"\g<1>{production.group(2)}", params.read_text())
        if n != 1:
            raise RuntimeError("cannot restore MadLoop's COLLIERGlobalCache")
        params.write_text(text)
        settings["MadLoopParams"]["COLLIERGlobalCache"] = production.group(2)
    return settings, cache


def madloop(
    spec: dict, points: dict, work: Path, cpu: int, export: Path, trees: Trees
) -> dict[str, Any]:
    references = _references()
    mg5 = trees.mg5
    run = work / "madloop-run"
    run.mkdir(parents=True, exist_ok=True)
    flags = references.madloop_build_flags(export, mg5)
    if not flags["production_build"]:
        raise RuntimeError(f"{export} is not built with MG5's production flags")
    with _relocated_madloop_build(trees.root):
        binary, repairs = references.build_madloop(
            export, run, flags["export_make_opts"]["GLOBAL_FLAG"]
        )
    settings, cache = _prepare_madloop(spec, export, run, trees)
    born, loop = spec["born_orders"], spec["loop_orders"]
    count = len(points["points"])
    alpha_s = references.value(spec["scheme_data"], "aS")
    header = (
        f"{2 * born['QCD']} {2 * born['QED']} {born['QCD'] + loop['QCD']} "
        f"{born['QED'] + loop['QED']} {alpha_s} -1 0\n{count}\n"
    )
    stdin = header + "\n".join(references.point_lines(points)) + "\n"
    stdout, wall = references.run_native(
        [str(binary)], stdin, run, run / "output.log", cpu
    )
    rows, extra = references.parse_rows(stdout, "madloop", count)
    return {
        "provider": "madloop",
        "mode": "production: MLStabThres and the default stability test, MG5 "
        "production Fortran flags, COLLIERGlobalCache "
        + ("as in production" if cache["on"] else "0")
        + f" ({cache['reason']})",
        "version": "MadLoop/MG5_aMC 3.7.0",
        "export": str(export),
        "collier_cache": cache,
        "madloop_params": settings["MadLoopParams"],
        "fortran_flags": flags["export_make_opts"],
        "qp_model_repairs": repairs,
        **_summary(rows, extra, wall),
    }


# MadLoop's per-point call sites, grouped as the live report shows them:
# 0 loop-numerator coefficients (COEF_CONSTRUCTION), 1 Born, counterterm and
# shared wavefunction HELAS calls (HELAS_CALLS_AMPB, HELAS_CALLS_UVCT),
# 2 reduction and masters (LOOP_CT_CALLS: the reducers and their integrals,
# stability retries included); multiple-precision variants count alike.
STAGE_CALL = re.compile(
    r"\s+CALL ML5_\d+_(?:MP_)?(COEF_CONSTRUCTION|HELAS_CALLS_AMPB|HELAS_CALLS_UVCT"
    r"|LOOP_CT_CALLS)_\d+\(.*\)\s*$"
)
STAGE_BUCKETS = {
    "COEF_CONSTRUCTION": 0,
    "HELAS_CALLS_AMPB": 1,
    "HELAS_CALLS_UVCT": 1,
    "LOOP_CT_CALLS": 2,
}
STAGE_NAMES = (
    "loop numerator coefficients",
    "Born and counterterm HELAS",
    "reduction and masters",
)
STAGE_TIMER = r"""
#include <stdio.h>
#include <time.h>
static double total[3], begin[3];
static unsigned long long calls[3];
static double now(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return t.tv_sec + 1e-9 * t.tv_nsec;
}
void reference_stage_start_(const int *i) { begin[*i] = now(); }
void reference_stage_stop_(const int *i) {
  total[*i] += now() - begin[*i];
  ++calls[*i];
}
__attribute__((destructor)) static void report(void) {
  FILE *f = fopen("madloop-stages.json", "w");
  if (!f) return;
  fprintf(f, "{\"seconds\": [%.9e, %.9e, %.9e], \"calls\": [%llu, %llu, %llu]}\n",
          total[0], total[1], total[2], calls[0], calls[1], calls[2]);
  fclose(f);
}
"""


def _instrumented_madloop(
    export: Path, run: Path, global_flag: str, reference_root: Path
) -> Path:
    """MadLoop's driver linked with copies of ``loop_matrix.f`` and
    ``mp_compute_loop_coefs.f`` whose stage calls are bracketed by wall-clock
    timers (``STAGE_CALL``); the export itself is never modified. The timers
    write ``madloop-stages.json`` into the working directory at exit."""

    import shlex

    references = _references()
    process = references.madloop_process_dir(export)
    objects = []
    for name in ("loop_matrix.f", "mp_compute_loop_coefs.f"):
        lines = []
        count = 0
        for line in (process / name).read_text().splitlines(keepends=True):
            match = STAGE_CALL.match(line)
            if match:
                bucket = STAGE_BUCKETS[match.group(1)]
                lines += [
                    f"      CALL REFERENCE_STAGE_START({bucket})\n",
                    line,
                    f"      CALL REFERENCE_STAGE_STOP({bucket})\n",
                ]
                count += 1
            else:
                lines.append(line)
        if not count:
            raise RuntimeError(f"no MadLoop stage calls found in {name}")
        source = run / name
        source.write_text("".join(lines))
        target = run / (name[:-2] + ".o")
        subprocess.run(
            [
                "gfortran",
                "-w",
                "-fPIC",
                "-fno-common",
                "-ffixed-line-length-132",
                "-fallow-argument-mismatch",
                *shlex.split(global_flag),
                "-I",
                str(process),
                "-I",
                str(export / "SubProcesses"),
                "-I",
                str(export / "Source/MODEL"),
                "-J",
                str(run),
                "-c",
                str(source),
                "-o",
                str(target),
            ],
            check=True,
            cwd=run,
        )
        objects.append(target)
    timer = run / "stage_timer.c"
    timer.write_text(STAGE_TIMER)
    subprocess.run(
        ["gcc", "-O2", "-c", str(timer), "-o", str(run / "stage_timer.o")],
        check=True,
        cwd=run,
    )
    objects.append(run / "stage_timer.o")
    driver = run / "madloop_driver.f90"
    driver.write_text(
        (streams.REFERENCE / "madloop_driver.f90")
        .read_text()
        .replace("ML5_0_", references.madloop_prefix(process))
    )
    fixes, _ = references.madloop_model_fix(export, run, global_flag)
    binary = run / "madloop-driver-stages"
    subprocess.run(
        [
            "gfortran",
            "-O2",
            "-ffree-line-length-none",
            "-I",
            str(process),
            str(driver),
            *map(str, objects),
            *map(str, fixes),
            str(export / "lib/libMadLoop.a"),
            "-L" + str(export / "lib"),
            "-ldhelas",
            "-lmodel",
            *map(str, _madloop_libraries(export, reference_root)),
            "-lstdc++",
            "-Wl,--no-relax",
            "-o",
            str(binary),
        ],
        check=True,
        cwd=run,
    )
    return binary


def madloop_stages(
    spec: dict, points: dict, work: Path, cpu: int, export: Path, trees: Trees
) -> dict[str, Any]:
    """MadLoop's numerator / Born-and-CT / reduction-and-masters split.

    The instrumented driver runs the stream's points once and the first
    point alone, after a warm-up that stores MadLoop's filters; both measured
    runs initialise identically (point 1, untimed), so the difference of
    their stage totals is the stage time of points 2..n, and the per-point
    stage times are that difference over n - 1. The driver's own per-point
    total (instrumented) is reported beside them; the timers cost one clock
    read per call."""

    references = _references()
    mg5 = trees.mg5
    run = work / "madloop-stages-run"
    run.mkdir(parents=True, exist_ok=True)
    flags = references.madloop_build_flags(export, mg5)
    binary = _instrumented_madloop(
        export, run, flags["export_make_opts"]["GLOBAL_FLAG"], trees.root
    )
    _prepare_madloop(spec, export, run, trees)
    born, loop = spec["born_orders"], spec["loop_orders"]
    alpha_s = references.value(spec["scheme_data"], "aS")
    totals = {}
    rows = {}
    # MadLoop stores its helicity and loop filters in the resources at the
    # end of its initialisation; the untimed warm-up writes them, so both
    # measured runs load them and initialise identically.
    runs = (("warm-up", 1), ("all", len(points["points"])), ("first", 1))
    for label, count in runs:
        subset = {
            **points,
            "points": points["points"][:count],
            "mu_r": points["mu_r"][:count],
        }
        header = (
            f"{2 * born['QCD']} {2 * born['QED']} {born['QCD'] + loop['QCD']} "
            f"{born['QED'] + loop['QED']} {alpha_s} -1 0\n{count}\n"
        )
        stdin = header + "\n".join(references.point_lines(subset)) + "\n"
        stdout, _ = references.run_native(
            [str(binary)], stdin, run, run / f"output-{label}.log", cpu
        )
        rows[label], _ = references.parse_rows(stdout, "madloop", count)
        totals[label] = json.loads((run / "madloop-stages.json").read_text())
    timed = len(points["points"]) - 1
    if timed < 1:
        raise RuntimeError("the stage split needs at least two points")
    stage = [
        (a - b) / timed
        for a, b in zip(
            totals["all"]["seconds"], totals["first"]["seconds"], strict=True
        )
    ]
    per_point = statistics.fmean(row["seconds"] for row in rows["all"][:-1])
    return {
        "stages_seconds_per_point": dict(zip(STAGE_NAMES, stage, strict=True)),
        "residual_seconds_per_point": per_point - sum(stage),
        "instrumented_seconds_per_point": per_point,
        "points": timed,
        "calls_per_point": [
            (a - b) / timed
            for a, b in zip(
                totals["all"]["calls"], totals["first"]["calls"], strict=True
            )
        ],
    }


def imported(spec: dict, provider: str, trees: Trees) -> dict[str, Any]:
    """An existing timing of the reference campaign (``timing`` of the
    provider's specification, relative to the reference root), for a process
    whose provider generation HANDOFF §0.1 forbids repeating. Its rows are the
    campaign's points, which are the stream's first points (``streams.py``);
    the record keeps the run's own core, settings and timing scope.
    ``protocol_mode`` says whether its settings are the gate protocol's
    (MadLoop: the production stability setting on a production build, poles
    included as always; Recola: no IR-pole evaluation and the protocol's
    Collier cache, ``collier_cache`` of the release its version names); a
    run outside the protocol is reported beside the gate, never in it
    (``gate.py``). A Recola run that also evaluates the IR poles (three
    ``compute_amplitude`` calls per point instead of one) with the
    protocol's Collier cache, or without the cache (which only saves
    repeated tensor-integral work), does the production work and more: its
    time bounds the production time from above (``production_upper_bound``,
    the reason), which the report uses as a bound only, never as a limit or
    an extrapolated time."""

    relative = spec[provider]["timing"]
    path = trees.root / relative
    data = json.loads(path.read_text())
    if data.get("provider") != provider or data.get("process_name") != spec["name"]:
        raise RuntimeError(f"{relative} is not a {provider} result of {spec['name']}")
    stream = streams.load(spec["name"])
    reference = json.loads((path.parent / "points.json").read_text())
    count = len(data["rows"])
    if (
        reference["points"][:count] != stream["points"][:count]
        or reference["mu_r"][:count] != stream["mu_r"][:count]
    ):
        raise RuntimeError(f"{relative}: its points are not the stream's first points")
    settings = data.get("settings", {})
    bound = None
    if provider == "madloop":
        flags = settings.get("fortran_flags", {})
        protocol = bool(flags.get("production_build")) and "production" in str(
            settings.get("requested_relative_accuracy", "")
        )
        mode = (
            f"reference campaign: {settings.get('requested_relative_accuracy')}, "
            f"{settings.get('stability_check')}, production build "
            f"{flags.get('production_build')}"
        )
    elif provider == "recola":
        poles = settings.get("compute_ir_poles")
        cache = settings.get("collier_cache")
        version = _collier_version(data.get("version"))
        decision = collier_cache(len(spec["pdgs"]), version)
        wanted = {True: "on", False: "off"}.get(decision["on"])
        protocol = poles == 0 and cache == wanted
        mode = (
            f"reference campaign: compute_ir_poles {poles}, Collier cache {cache}"
            f" (the protocol's: {wanted or 'undecided'}, {decision['reason']})"
        )
        if poles == 1 and cache in (wanted, "off"):
            how = (
                f"with the protocol's Collier cache ({cache})"
                if cache == wanted
                else "without the Collier cache, which production keeps on and"
                " which only saves repeated tensor-integral work"
            )
            bound = (
                "the run evaluates the IR poles (compute_ir_poles 1: three"
                f" compute_amplitude calls per point instead of one) {how}, so"
                " the production-mode time is at most this time"
            )
    else:
        raise RuntimeError(f"no import of {provider} timings")
    rows = [
        {key: row[key] for key in ("born", "finite", "seconds", "raw") if key in row}
        for row in data["rows"]
    ]
    out = {
        "provider": provider,
        "mode": mode,
        "protocol_mode": protocol,
        "version": data.get("version"),
        "imported_from": relative,
        "measured": _modified(path),
        "timing_scope": data.get("timing_scope"),
        "cpu": data.get("cpu"),
        **_summary(rows, {}, data.get("process_wall_seconds", 0.0)),
    }
    out["setup"] = {
        key: data[key]
        for key in ("initial_call_seconds", "generation_seconds")
        if key in data
    }
    if bound is not None and not protocol:
        out["production_upper_bound"] = bound
    return out


def _modified(path: Path) -> str:
    import datetime

    stamp = datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.UTC)
    return stamp.strftime("%Y-%m-%d %H:%M UTC")


def main(options: Any) -> int:
    key = options.process
    spec = streams.spec(key)
    points = _points(key, options.points)
    work = options.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    # MG5_aMC writes py.py and additional_command into the working directory.
    os.chdir(work)
    record: dict[str, Any] = {
        "kind": "providers",
        "process": key,
        "cpu": options.cpu,
        "host": platform.node(),
        "points": len(points["points"]),
        "timing_scope": "single pinned core; point 1 once untimed, then points "
        "2..n, 1 timed one by one with the driver's own timer",
        "providers": {},
    }
    if options.json and options.json.exists():
        record = json.loads(options.json.read_text())
    trees = Trees(options)
    for provider in options.providers:
        start = time.perf_counter()
        reason = unavailable(spec, provider)
        try:
            if "timing" in spec.get(provider, {}):
                result = imported(spec, provider, trees)
                if reason is not None:
                    result["unavailable"] = reason
            elif reason is not None:
                result = {"provider": provider, "unavailable": reason}
            elif provider == "openloops":
                result = openloops(spec, points, work, options.cpu, trees)
            elif provider == "recola":
                result = recola(spec, points, work, options.cpu, trees)
            else:
                export = trees.madloop_export(spec, options.madloop_export)
                if export is None:
                    raise RuntimeError("no MadLoop export for this process")
                result = madloop(spec, points, work, options.cpu, export, trees)
                if options.madloop_stages:
                    result["stages"] = madloop_stages(
                        spec, points, work, options.cpu, export, trees
                    )
        except Exception as error:  # recorded, never silently dropped
            result = {"provider": provider, "error": f"{type(error).__name__}: {error}"}
        result["harness_wall_seconds"] = time.perf_counter() - start
        record["providers"][provider] = result
        mean = result.get("mean_seconds_per_point")
        if "error" in result:
            status = "error " + result["error"]
        elif "unavailable" in result:
            status = "unavailable: " + result["unavailable"]
        else:
            status = f"{mean * 1e3:.3f} ms/pt"
        print(key, provider, status, flush=True)
        if options.json:
            options.json.parent.mkdir(parents=True, exist_ok=True)
            options.json.write_text(json.dumps(record, indent=1) + "\n")
    return 0


def alpha_s(spec: dict) -> float:
    """The specification's alpha_s as the providers receive it (the
    toolkit's ``references.value``: a fixed parameter overrides)."""

    return float(_references().value(spec["scheme_data"], "aS"))


def universal_double_pole(spec: dict) -> float:
    """D / Born of the declared correction: -(alpha_s/2pi) sum_i C_i over the
    massless coloured legs for QCD (the toolkit's ``double_pole_factor``,
    from its particle metadata)."""

    _, required_spec = streams._toolkit()
    if spec["correction"] != "QCD":
        raise ValueError("the G1 value comparison converts QCD corrections only")
    return required_spec.double_pole_factor(spec, alpha_s(spec))
