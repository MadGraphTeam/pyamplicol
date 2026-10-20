#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Run matched MadLoop/Recola/OpenLoops one-loop references and merge them.

Subcommands
-----------
``run``    evaluate one provider for one process on a points JSON (from
           ``exact_points.py``); writes ``<work>/<provider>-result.json``.
``merge``  combine the available provider results into one reference JSON
           (Born plus finite/single/double pole per point, settings, versions,
           generation and per-point evaluation times) and check agreement.

All providers use physical couplings and return the MadLoop/BLHA Laurent
convention ``C_eps = (4 pi)^eps / Gamma(1 - eps)``: MadLoop directly, OpenLoops
with ``truepoles=1, polenorm=0``, and Recola after ``F += pi^2/6 * D``
(``Gamma(1+eps)`` normalization, identical poles at matched scales). All
three average initial spins/colours and include final identical-particle
factors. Settings are built from the scheme in ``required_processes.json``;
nothing here is process-specific.
"""

import argparse
from decimal import Decimal, getcontext
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import required_spec  # noqa: E402

COEFFICIENTS = ("born", "finite", "single_pole", "double_pole")
PI = Decimal("3.14159265358979323846264338327950288419716939937510582097494")
getcontext().prec = 50
UNCACHED_LEG_THRESHOLD = 7  # COLLIER 1.2.9/1.2.10 global cache defect at N=7 (NinjaRS owners)
LHA_VALUE_CHARACTERS = 20  # character*20 value buffer of MadLoop's lha_read.f


def derived_parameters(scheme):
    """Tree-level derived EW inputs shared by every provider (exact decimals)."""
    p = {k: Decimal(v) for k, v in scheme["parameters"].items()}
    two = Decimal(2)
    if scheme["electroweak_inputs"] == "alpha_fixed":
        alpha = 1 / p["aEWM1"]
        mz2 = p["MZ"] ** 2
        mw = (mz2 / 2 + (mz2 ** 2 / 4 - alpha * PI * mz2 / (p["Gf"] * two.sqrt())).sqrt()).sqrt()
    else:
        mw = p["MW"]
        alpha = two.sqrt() * p["Gf"] * mw ** 2 * (1 - mw ** 2 / p["MZ"] ** 2) / PI
    return {"MW": f"{mw:.30g}", "alpha": f"{alpha:.30g}"}


def value(scheme, name):
    merged = {**scheme["parameters"], **scheme["fixed_parameters"]}
    return merged.get(name)


def width(scheme, name):
    w = value(scheme, name)
    return w if w is not None else "0"


# ---------------------------------------------------------------- Recola

def recola_commands(spec, points, uncached):
    scheme = spec["scheme_data"]
    derived = derived_parameters(scheme)
    zero = "0"
    masses = [
        ("W", derived["MW"], width(scheme, "WW")),
        ("Z", value(scheme, "MZ"), width(scheme, "WZ")),
        ("H", value(scheme, "MH"), width(scheme, "WH")),
        ("top", value(scheme, "MT"), width(scheme, "WT")),
        ("bottom", value(scheme, "MB") or zero, zero),
        ("charm", zero, zero), ("strange", zero, zero), ("up", zero, zero), ("down", zero, zero),
        ("tau", value(scheme, "MTA") or zero, zero), ("muon", zero, zero), ("electron", zero, zero),
    ]
    lines = [f"mass {n} {m} {w}" for n, m, w in masses]
    if scheme["electroweak_inputs"] == "alpha_fixed":
        lines.append(f"alpha0 {derived['alpha']}")
    else:
        lines.append(f"gfermi {value(scheme, 'Gf')}")
    lines.append("complex_mass" if scheme.get("complex_mass_scheme") else "onshell")
    lines.append(f"alphas {value(scheme, 'aS')} {points['mu_r'][0]} {scheme['active_flavours']}")
    if uncached:
        lines.append("cache 0")
    born, loop = spec["born_orders"]["QCD"], spec["loop_orders"]["QCD"]
    lines += [f"legs {len(spec['pdgs'])}", f"born_gs {born}", f"loop_gs {loop}",
              f"pow_lo {born}", f"pow_nlo {(born + loop) // 2}",
              f"process {spec['recola']['process']}", "generate"]
    return lines


# ------------------------------------------------------------- OpenLoops

def openloops_commands(spec):
    scheme = spec["scheme_data"]
    derived = derived_parameters(scheme)
    born, loop = spec["born_orders"], spec["loop_orders"]
    lines = [
        "int truepoles 1", "int polenorm 0", "int ct_on 1", "int r2_on 1", "int iop_on 0",
        f"int nf {scheme['loop_quark_flavours']}",
        f"int nq_nondecoupled {scheme['active_flavours']}",
        f"int coupling_qcd_0 {born['QCD']}", f"int coupling_qcd_1 {(loop['QCD'] - born['QCD']) // 2}",
        f"int coupling_ew_0 {born['QED']}", f"int coupling_ew_1 {(loop['QED'] - born['QED']) // 2}",
        "int ew_scheme 1", "int ew_renorm_scheme 1",
        f"int complex_mass_scheme {1 if scheme.get('complex_mass_scheme') else 0}",
        f"double gmu {value(scheme, 'Gf')}",
        f"double mass(23) {value(scheme, 'MZ')}", f"double width(23) {width(scheme, 'WZ')}",
        f"double mass(24) {derived['MW']}", f"double width(24) {width(scheme, 'WW')}",
        f"double mass(25) {value(scheme, 'MH')}", f"double width(25) {width(scheme, 'WH')}",
        f"double mass(6) {value(scheme, 'MT')}", f"double width(6) {width(scheme, 'WT')}",
        f"double mass(5) {value(scheme, 'MB') or '0'}", f"double width(5) 0",
        f"double mass(15) {value(scheme, 'MTA') or '0'}",
        f"double alpha_s {value(scheme, 'aS')}",
    ]
    if spec["correction"] == "EW":
        lines.append("int ew_renorm 1")
    lines.append(f"register 11 {spec['openloops']['process']}")
    return lines


def openloops_release(root):
    """OpenLoops release string of the installation actually used."""
    text = (root / "pyol/config/default.cfg").read_text()
    match = re.search(r"^release\s*=\s*(\S+)", text, re.MULTILINE)
    if not match:
        raise RuntimeError(f"cannot read the OpenLoops release from {root}")
    return match.group(1)


# ---------------------------------------------------------- provenance

def library_version(library):
    """Best-effort version of the package that ships ``library``: a CMake
    ``*ConfigVersion.cmake``, a ``VERSION`` file or a ``<NAME>-<version>``
    directory next to it or one level up. Returns None when none is found."""
    for directory in (library.parent, library.parent.parent):
        for config in sorted(directory.glob("*ConfigVersion.cmake")):
            match = re.search(r'set\(PACKAGE_VERSION "([^"]+)"\)', config.read_text())
            if match:
                return match.group(1)
        version_file = directory / "VERSION"
        if version_file.is_file():
            first = version_file.read_text().split()
            if first and re.fullmatch(r"\d+(\.\d+)+", first[0]):
                return first[0]
        for child in sorted(directory.iterdir()):
            match = re.fullmatch(r"[A-Za-z]+-(\d+(\.\d+)+)", child.name)
            if child.is_dir() and match:
                return match.group(1)
    return None


def linked_libraries(binary, pattern):
    """Resolved shared libraries of ``binary`` whose soname matches ``pattern``."""
    text = subprocess.run(["ldd", str(binary)], capture_output=True, text=True, check=True).stdout
    found = {}
    for line in text.splitlines():
        match = re.match(r"\s*(\S+) => (\S+)", line)
        if match and re.search(pattern, match.group(1)):
            path = Path(match.group(2)).resolve()
            found[match.group(1)] = {"path": str(path), "version": library_version(path)}
    return found


def openloops_library_version(root, library):
    info = {}
    path = root / "process_src" / library / "version.info"
    for line in path.read_text().splitlines():
        if line.strip():
            key, _, val = line.partition(" ")
            info[key] = val.strip()
    return info


# --------------------------------------------------------------- MadLoop

def madloop_process_dir(export):
    candidates = sorted(p for p in (export / "SubProcesses").glob("P*") if p.is_dir())
    if len(candidates) != 1:
        raise RuntimeError(f"expected one SubProcesses/P* directory in {export}")
    return candidates[0]


def madloop_prefix(process_dir):
    text = (process_dir / "loop_matrix.f").read_text()
    match = re.search(r"SUBROUTINE (ML5_\d+_)SLOOPMATRIX_THRES", text)
    if not match:
        raise RuntimeError("cannot identify the MadLoop routine prefix")
    return match.group(1)


def build_madloop(export, work):
    from build import madloop_libraries

    process_dir = madloop_process_dir(export)
    source = (HERE / "madloop_driver.f90").read_text().replace("ML5_0_", madloop_prefix(process_dir))
    driver = work / "madloop_driver.f90"
    driver.write_text(source)
    binary = work / "madloop-driver"
    subprocess.run(
        ["gfortran", "-O2", "-ffree-line-length-none", "-I", str(process_dir), str(driver),
         str(export / "lib/libMadLoop.a"), "-L" + str(export / "lib"), "-ldhelas", "-lmodel",
         *map(str, madloop_libraries(export)), "-lstdc++",
         # Large exports (g g -> 6 g: 7.7 GB of static arrays) put PIC data
         # beyond the range of relaxed GOTPCREL loads; keep GOT loads.
         "-Wl,--no-relax", "-o", str(binary)],
        check=True, cwd=work,
    )
    return binary


def prepare_madloop_run(spec, export, run_dir, mg5, legs):
    """Copy cards/resources and set every scheme parameter by its card name."""
    sys.path.insert(0, str(mg5))
    from models.check_param_card import ParamCard

    shutil.copytree(export / "Cards", run_dir / "Cards", dirs_exist_ok=True)
    shutil.copytree(export / "SubProcesses/MadLoop5_resources",
                    run_dir / "SubProcesses/MadLoop5_resources", dirs_exist_ok=True, symlinks=False)
    card = ParamCard(str(run_dir / "Cards/param_card.dat"))
    by_name = {}
    for block in card.values():
        for param in block:
            comment = (param.comment or "").strip()
            # Dependent entries read "<particle> : <expression>"; skip them.
            if comment and not re.match(r"^\S+ : ", comment):
                by_name[comment.split()[0].lower()] = param
    scheme = spec["scheme_data"]
    absent = []
    for name, text in {**scheme["parameters"], **scheme["fixed_parameters"]}.items():
        param = by_name.get(name.lower())
        if param is None:
            if Decimal(text) != 0:
                raise RuntimeError(f"MadLoop card has no parameter {name} (value {text})")
            absent.append(name)  # removed by the model restriction, i.e. fixed to zero
            continue
        # Write the scheme's exact decimal text (MG5's default %.6e would silently
        # truncate longer inputs for MadLoop only). MadLoop's LHA reader keeps 20
        # characters per value; fall back to the shortest round-trip binary64
        # text, and refuse anything that would not reproduce the same double.
        exact = float(Decimal(text))
        written = text.strip() if len(text.strip()) <= LHA_VALUE_CHARACTERS else repr(exact)
        if len(written) > LHA_VALUE_CHARACTERS or float(written) != exact:
            raise RuntimeError(f"cannot write {name}={text} exactly into a MadLoop param_card")
        param.value, param.format = written, "str"
    card.write(str(run_dir / "Cards/param_card.dat"))
    reread = ParamCard(str(run_dir / "Cards/param_card.dat"))
    for name, text in {**scheme["parameters"], **scheme["fixed_parameters"]}.items():
        param = by_name.get(name.lower())
        if param is not None and float(reread[param.lhablock].get(param.lhacode).value) != float(Decimal(text)):
            raise RuntimeError(f"MadLoop card does not reproduce {name}={text}")
    params = run_dir / "SubProcesses/MadLoop5_resources/MadLoopParams.dat"
    text = params.read_text()
    settings = {}
    if legs >= UNCACHED_LEG_THRESHOLD:
        text, n = re.subn(r"(#COLLIERGlobalCache\s*\n)\s*-?\d+", r"\g<1>0", text)
        if n != 1:
            raise RuntimeError("cannot disable the COLLIER global cache")
        params.write_text(text)
    for key in ("MLReductionLib", "COLLIERGlobalCache", "MLStabThres", "ImprovePSPoint"):
        match = re.search(rf"#{key}\s*\n\s*(\S+)", text)
        settings[key] = match.group(1) if match else None
    return {"absent_card_parameters_fixed_to_zero": absent, "MadLoopParams": settings,
            "param_card": (run_dir / "Cards/param_card.dat").read_text()}


# ----------------------------------------------------------------- common

def point_lines(points):
    return [" ".join([mu, *(x for leg in point for x in leg)])
            for mu, point in zip(points["mu_r"], points["points"], strict=True)]


def run_native(command, stdin_text, cwd, log, cpu):
    env = os.environ.copy()
    env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"})

    def pin():
        if cpu is not None:
            os.sched_setaffinity(0, {cpu})

    start = time.perf_counter()
    with open(log, "w") as handle:
        completed = subprocess.run(command, input=stdin_text, text=True, cwd=cwd, env=env,
                                   stdout=subprocess.PIPE, stderr=handle, preexec_fn=pin)
    handle_text = completed.stdout
    with open(log, "a") as handle:
        handle.write(handle_text)
    if completed.returncode:
        raise RuntimeError(f"{command[0]} failed with {completed.returncode}; see {log}")
    return handle_text, time.perf_counter() - start


def parse_rows(stdout, provider, count):
    rows = [None] * count
    extra = {}
    for line in stdout.splitlines():
        fields = line.split()
        if not fields:
            continue
        if fields[0] == "ROW":
            i = int(fields[1]) - 1
            if provider == "madloop":
                status, seconds = int(fields[2]), float(fields[3])
                born, fin, sp, dp, acc = map(float, fields[4:9])
                rows[i] = {"born": born, "finite": fin, "single_pole": sp, "double_pole": dp,
                           "accuracy": acc, "status": status, "seconds": seconds,
                           "total_all_orders": list(map(float, fields[9:13]))}
            elif provider == "recola":
                seconds = float(fields[2])
                born, fin, sp, dp = map(float, fields[3:7])
                rows[i] = {"born": born, "finite": fin + math.pi ** 2 / 6 * dp, "single_pole": sp,
                           "double_pole": dp, "seconds": seconds,
                           "raw": {"born": born, "finite": fin, "single_pole": sp, "double_pole": dp}}
            else:
                seconds = float(fields[2])
                born, fin, sp, dp, acc = map(float, fields[3:8])
                rows[i] = {"born": born, "finite": fin, "single_pole": sp, "double_pole": dp,
                           "accuracy": acc, "seconds": seconds}
        elif fields[0] in ("GENERATION_SECONDS", "START_SECONDS"):
            extra[fields[0].lower()] = float(fields[1])
        elif fields[0] == "INITIAL_CALL_SECONDS":
            extra["initial_call_seconds"] = float(fields[1])
            if len(fields) > 2:
                extra["initialization_calls"] = int(fields[2])
        elif fields[0] == "SPLIT_ORDER_INDICES":
            extra["split_order_indices"] = list(map(int, fields[1:]))
    if any(r is None for r in rows):
        raise RuntimeError(f"{provider}: missing result rows")
    for row in rows:
        for key in COEFFICIENTS:
            if not math.isfinite(row[key]):
                raise RuntimeError(f"{provider}: non-finite {key}")
    return rows, extra


EXPORT_IN_PROGRESS = ("generating", "exporting", "exported", "compiling")


def export_processes(generation, export):
    """Live processes producing ``export``: the pid recorded by madloop_export.py
    or, for exports started without one, every live madloop_export.py whose
    command line names ``export`` as its ``--output``."""
    pid = json.loads(generation.read_text()).get("pid")
    if pid is not None:
        return [pid] if Path(f"/proc/{pid}").exists() else []
    found = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            argv = [a.decode(errors="replace") for a in (proc / "cmdline").read_bytes().split(b"\0")]
        except OSError:
            continue
        if not any(a.endswith("madloop_export.py") for a in argv):
            continue
        targets = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == "--output"]
        if any(Path(t).resolve() == export for t in targets):
            found.append(int(proc.name))
    return found


def status_update(work, label, state):
    """One status file per provider run label, so concurrent runs never race."""
    path = work / f"status-{label}.json"
    path.write_text(json.dumps({"provider": label, "state": state, "pid": os.getpid(),
                                "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + "\n")


def command_run(args):
    roots = {"mg5": args.mg5, "reference": args.reference_root}
    spec = required_spec.load_process(args.spec, args.process, roots)
    points = json.loads(args.points.read_text())
    if points["pdgs"] != spec["pdgs"]:
        raise SystemExit("points JSON belongs to another process")
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    provider = args.provider
    label = f"{provider}-{args.tag}" if args.tag else provider
    run_dir = work / f"{label}-run"
    run_dir.mkdir(exist_ok=True)
    legs = len(spec["pdgs"])
    count = len(points["points"])
    status_update(work, label, "running")
    result = {"provider": provider, "process_name": spec["name"], "host": platform.node(),
              "cpu": args.cpu, "points_file": str(args.points.resolve()),
              "timing_scope": "single thread pinned; point 1 evaluated once untimed for "
              "initialization, then each point timed once (points 2..n,1); includes all "
              "actual poles; not a benchmark campaign"}
    try:
        if provider == "madloop":
            export = args.madloop_export.resolve()
            generation = export.parent / f"{export.name}.generation.json"
            while args.wait_for_export:
                state = json.loads(generation.read_text())["status"] if generation.exists() else "absent"
                if state == "compiled":
                    break
                if state not in EXPORT_IN_PROGRESS:
                    raise RuntimeError(f"MadLoop export state {state!r}; not waiting")
                pids = export_processes(generation, export)
                if not pids:
                    # Re-read: the export may have finished between the two reads.
                    state = json.loads(generation.read_text())["status"]
                    if state == "compiled":
                        break
                    raise RuntimeError(f"no live MadLoop export process for {export} (state {state!r})")
                status_update(work, label, f"waiting for MadLoop export ({state}; pid {pids[0]})")
                time.sleep(args.wait_interval)
            binary = build_madloop(export, run_dir)
            result["settings"] = prepare_madloop_run(spec, export, run_dir, args.mg5, legs)
            result["generation"] = json.loads(generation.read_text()) if generation.exists() else None
            mg5_version = re.search(r"version = (\S+)", (args.mg5 / "VERSION").read_text()).group(1)
            from build import madloop_libraries
            reducers = {lib.name: {"path": str(lib.resolve()), "version": library_version(lib.resolve())}
                        for lib in madloop_libraries(export)}
            result["version"] = f"MadLoop/MG5_aMC {mg5_version}"
            result["provenance"] = {"MG5_aMC": {"path": str(args.mg5), "version": mg5_version},
                                    "reducer_libraries": reducers}
            production = args.madloop_accuracy <= 0
            result["settings"]["requested_relative_accuracy"] = (
                "MadLoop MLStabThres (production setting)" if production else args.madloop_accuracy)
            result["settings"]["stability_check"] = (
                "MadLoop default (CTModeRun=-1 after initialization)" if production
                else "forced on every call")
            orders = spec["born_orders"], spec["loop_orders"]
            header = (f"{2 * orders[0]['QCD']} {2 * orders[0]['QED']} "
                      f"{orders[0]['QCD'] + orders[1]['QCD']} {orders[0]['QED'] + orders[1]['QED']} "
                      f"{value(spec['scheme_data'], 'aS')} {args.madloop_accuracy} "
                      f"{0 if production else 1}\n{count}\n")
            stdin = header + "\n".join(point_lines(points)) + "\n"
            stdout, wall = run_native([str(binary)], stdin, run_dir, run_dir / "output.log", args.cpu)
        elif provider == "recola":
            root = args.recola.resolve()
            binary = run_dir / "recola-driver"
            subprocess.run(["gfortran", "-O2", "-ffree-line-length-none", str(HERE / "recola_driver.f90"),
                            "-I", str(root / "include"), "-L", str(root), f"-Wl,-rpath,{root}",
                            "-lrecola", "-o", str(binary)], check=True, cwd=run_dir)
            uncached = legs >= UNCACHED_LEG_THRESHOLD or args.recola_uncached
            commands = recola_commands(spec, points, uncached)
            result["settings"] = {"recola_tree": str(root), "commands": commands,
                                  "collier_cache": "off" if uncached else "on",
                                  "dynamic_settings": 1, "compute_ir_poles": 1,
                                  "delta_uv": 0, "delta_ir": [0, 0], "mu_uv=mu_ir=mu_r": True}
            stdin = "\n".join(commands + [f"points {count}", *point_lines(points)]) + "\n"
            stdout, wall = run_native([str(binary)], stdin, run_dir, run_dir / "output.log", args.cpu)
        else:
            root = args.openloops.resolve()
            binary = run_dir / "openloops-driver"
            subprocess.run(["g++", "-O2", "-std=c++17", str(HERE / "openloops_driver.cpp"),
                            "-I", str(root / "include"), "-L", str(root / "lib"),
                            f"-Wl,-rpath,{root / 'lib'}", "-lopenloops", "-o", str(binary)],
                           check=True, cwd=run_dir)
            commands = openloops_commands(spec)
            library = spec["openloops"]["library"]
            result["settings"] = {"commands": commands}
            result["version"] = f"OpenLoops {openloops_release(root)}"
            result["provenance"] = {"openloops": {"path": str(root), "release": openloops_release(root)},
                                    "linked": linked_libraries(binary, r"openloops")}
            result["library"] = {"name": library, **openloops_library_version(root, library)}
            stdin = "\n".join(commands + [f"points {count}", *point_lines(points)]) + "\n"
            stdout, wall = run_native([str(binary)], stdin, run_dir, run_dir / "output.log", args.cpu)
        rows, extra = parse_rows(stdout, provider, count)
        if provider == "recola":
            banner = re.search(r"Version (\S+)", stdout)
            linked = linked_libraries(binary, r"recola|collier|modelfile")
            versions = {re.sub(r"^lib|\.so.*$", "", name): info["version"] for name, info in linked.items()}
            result["provenance"] = {"recola_tree": str(root),
                                    "self_reported_version": banner.group(1) if banner else None,
                                    "linked": linked}
            result["version"] = (f"Recola2 {result['provenance']['self_reported_version']} "
                                 f"(tree {root}) / " + " / ".join(
                                     f"{k} {v}" for k, v in sorted(versions.items()) if k != "recola"))
        result.update(extra)
        result["rows"] = rows
        result["process_wall_seconds"] = wall
    except Exception as error:
        status_update(work, label, f"failed: {error}")
        raise
    out = work / f"{label}-result.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    status_update(work, label, "done")
    print(out)


def relative(a, b, floor=0.0):
    """|a-b| / max(|a|, |b|, floor). The floor is one natural loop unit
    |Born| * coupling/(2 pi) for Laurent coefficients, so identically vanishing
    coefficients (e.g. a double pole without massless charged legs) compare on
    their natural scale instead of on round-off; Born values use no floor."""
    scale = max(abs(a), abs(b), floor)
    return 0.0 if scale == 0 else abs(a - b) / scale


def command_merge(args):
    spec = required_spec.load_process(args.spec, args.process)
    points = json.loads(args.points.read_text())
    work = args.work_dir.resolve()
    results = {}
    for provider in ("madloop", "recola", "openloops"):
        path = work / f"{provider}-result.json"
        if path.exists():
            results[provider] = json.loads(path.read_text())
    if not results:
        raise SystemExit("no provider results")
    # Persistent, documented exclusions live next to the results so that later
    # automatic merges (run_required.sh) keep them.
    record = work / "exclusions.json"
    excluded = json.loads(record.read_text()) if record.exists() else {}
    excluded.update(dict(item.split("=", 1) for item in args.exclude))
    if set(excluded) - set(results):
        raise SystemExit(f"excluded provider without result: {set(excluded) - set(results)}")
    validated = [p for p in results if p not in excluded]
    if not validated:
        raise SystemExit("every provider is excluded")
    primary = validated[0]
    scheme = spec["scheme_data"]
    derived = derived_parameters(scheme)
    coupling = float(Decimal(value(scheme, "aS"))) if spec["correction"] == "QCD" else float(Decimal(derived["alpha"]))
    pole_factor = required_spec.double_pole_factor(spec, coupling)
    rows, errors, pole_errors = [], [], []
    names = list(results)
    for index in range(len(points["points"])):
        row = {key: results[primary]["rows"][index][key] for key in COEFFICIENTS}
        row["providers"] = {}
        row["provider_pair_relative_errors"] = {}
        row["provider_pair_strict_relative_errors"] = {}
        for provider, result in results.items():
            values = result["rows"][index]
            row["providers"][provider] = {k: v for k, v in values.items() if k != "total_all_orders"}
            unit = abs(values["born"]) * coupling / (2 * math.pi)
            pole_error = relative(values["double_pole"], pole_factor * values["born"], unit)
            row["providers"][provider]["universal_double_pole_relative_error"] = pole_error
            if provider not in excluded:
                pole_errors.append(pole_error)
        # Every unordered provider pair; excluded providers are compared too but
        # never enter the agreement check.
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                va, vb = results[a]["rows"][index], results[b]["rows"][index]
                unit = max(abs(va["born"]), abs(vb["born"])) * coupling / (2 * math.pi)
                pair = f"{a}-{b}"
                rel = {key: relative(va[key], vb[key], 0.0 if key == "born" else unit)
                       for key in COEFFICIENTS}
                row["provider_pair_relative_errors"][pair] = rel
                row["provider_pair_strict_relative_errors"][pair] = {
                    key: relative(va[key], vb[key]) for key in COEFFICIENTS}
                if a not in excluded and b not in excluded:
                    errors.extend(rel.values())
        rows.append(row)
    max_error = max(errors) if errors else None
    passed = (len(validated) >= 2 and max_error < args.tolerance and max(pole_errors) < args.tolerance)
    normalization = required_spec.normalization(spec)
    providers = {}
    for provider, result in results.items():
        providers[provider] = {k: v for k, v in result.items() if k not in ("rows",)}
        providers[provider]["evaluation_seconds"] = [r["seconds"] for r in result["rows"]]
    # Secondary timing runs (e.g. MadLoop at its production stability setting):
    # timings and their deviation from the accurate run only, never reference values.
    for path in sorted(work.glob("*-*-result.json")):
        label = path.name[: -len("-result.json")]
        provider, _, tag = label.partition("-")
        if provider not in results:
            continue
        secondary = json.loads(path.read_text())
        deviation = []
        for accurate, other in zip(results[provider]["rows"], secondary["rows"], strict=True):
            unit = abs(accurate["born"]) * coupling / (2 * math.pi)
            deviation.append({key: relative(other[key], accurate[key], 0.0 if key == "born" else unit)
                              for key in COEFFICIENTS})
        providers[provider].setdefault("secondary_runs", {})[tag] = {
            "settings": {k: secondary["settings"][k] for k in ("requested_relative_accuracy", "stability_check")
                         if k in secondary.get("settings", {})},
            "evaluation_seconds": [r["seconds"] for r in secondary["rows"]],
            "statuses": [r.get("status") for r in secondary["rows"]],
            "relative_deviation_from_reference_run": deviation,
            "initial_call_seconds": secondary.get("initial_call_seconds"),
            "cpu": secondary.get("cpu"),
        }
    report = {
        "process": spec["madloop"]["process"] if "madloop" in spec else spec["name"],
        "name": spec["name"],
        "pdgs": spec["pdgs"],
        "correction": spec["correction"],
        "born_orders": spec["born_orders"],
        "loop_orders": spec["loop_orders"],
        "scheme": spec["scheme"],
        "scheme_description": scheme["description"],
        "source": "independent references: " + "; ".join(
            results[p].get("version", p) for p in results),
        "scope": "Independent provider references at exact on-shell decimal points; binary64 "
                 "provider arithmetic; timings are single-run by-products, not benchmarks.",
        "convention": "MadLoop/BLHA C_eps=(4pi)^eps/Gamma(1-eps); F_MadLoop=F_Recola+pi^2/6*D; "
                      "OpenLoops truepoles=1, polenorm=0; physical couplings, no alpha extraction; "
                      "initial spin/colour average and final identical-particle factor included",
        "normalization": normalization,
        "normalization_denominator": normalization["denominator"],
        "points": points["points"],
        "mu_r": points["mu_r"],
        "point_construction": {k: points[k] for k in ("construction", "cuts", "sqrt_s") if k in points},
        "parameters": scheme["parameters"],
        "fixed_parameters": scheme["fixed_parameters"],
        "derived_parameters": derived,
        "active_flavours": scheme["active_flavours"],
        "loop_quark_flavours": scheme["loop_quark_flavours"],
        "rows": rows,
        "primary_provider": primary,
        "universal_double_pole_factor": pole_factor,
        "maximum_provider_relative_error": max_error,
        "error_metric": "|a-b|/max(|a|,|b|,|Born|*coupling/(2pi)) for Laurent coefficients, "
                        "|a-b|/max(|a|,|b|) for Born; strict relative errors also listed per row",
        "maximum_universal_double_pole_relative_error": max(pole_errors),
        "tolerance": args.tolerance,
        "validation_status": "passed" if passed else (
            "single provider; no cross-check" if len(validated) < 2 else "FAILED"),
        "validated_providers": validated,
        "excluded_providers": excluded,
        "providers": providers,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{spec['name']}: providers={validated} excluded={list(excluded)} max_rel={max_error} "
          f"max_pole_identity={max(pole_errors):.3g} status={report['validation_status']}")
    if not passed:
        sys.exit(2)


def generation_seconds(provider, result):
    if provider == "madloop":
        g = result.get("generation") or {}
        parts = [g.get(k) for k in ("graph_generation_s", "source_export_s", "compile_s")]
        return sum(parts) if all(x is not None for x in parts) else None
    if provider == "recola":
        return result.get("generation_seconds")
    return None  # OpenLoops: precompiled public library (installation recorded separately)


def command_summary(args):
    """Markdown table of merged references (generation and per-point times).
    The agreement column is the largest difference over all pairs of validated
    providers; excluded providers are listed separately."""
    print("| process | validated | excluded | max pairwise rel. diff (validated) | status | "
          "generation [s] | s/point (mean) |")
    print("|---|---|---|---|---|---|---|")
    for path in args.references:
        d = json.loads(Path(path).read_text())
        gen, per = [], []
        for provider, result in d["providers"].items():
            g = generation_seconds(provider, result)
            gen.append(f"{provider} {g:.4g}" if g is not None else f"{provider} -")
            t = result["evaluation_seconds"]
            per.append(f"{provider} {sum(t) / len(t):.3g}")
            for tag, run in result.get("secondary_runs", {}).items():
                t = run["evaluation_seconds"]
                per.append(f"{provider}-{tag} {sum(t) / len(t):.3g}")
        err = d["maximum_provider_relative_error"]
        print(f"| {d['name']} | {', '.join(d['validated_providers'])} | "
              f"{', '.join(d['excluded_providers']) or '-'} | {err if err is None else f'{err:.2g}'} | "
              f"{d['validation_status']} | {'; '.join(gen)} | {'; '.join(per)} |")


def provider_state(work, label):
    """'done', 'failed: ...', 'dead: ...' (status claims a live run whose process
    is gone) or 'running: <state>' for one provider run label."""
    if (work / f"{label}-result.json").exists():
        return "done"
    status = work / f"status-{label}.json"
    if not status.exists():
        return "dead: no status file"
    record = json.loads(status.read_text())
    if record["state"].startswith("failed"):
        return record["state"]
    if not Path(f"/proc/{record['pid']}").exists():
        return f"dead: process {record['pid']} gone in state {record['state']!r}"
    if record["state"].startswith("waiting for MadLoop export"):
        # Waiters started by older toolkit versions cannot see a dead export themselves.
        export = work / "madloop-export"
        generation = work / "madloop-export.generation.json"
        alive = generation.exists() and export_processes(generation, export)
        export_state = json.loads(generation.read_text())["status"] if generation.exists() else "absent"
        if export_state != "compiled" and not alive:
            return f"dead: MadLoop export ended in state {export_state!r}; waiter {record['pid']} cannot finish"
    return f"running: {record['state']}"


def command_watch(args):
    """Re-merge long-running processes periodically until every expected
    provider run has finished, failed or died; then report and exit (status 1
    if any expected run did not produce a result)."""
    expected = {}
    for item in args.expect:
        process, _, labels = item.partition(":")
        expected[process] = labels.split(",")
    while True:
        states = {}
        for process, labels in expected.items():
            work = args.root / process
            states[process] = {label: provider_state(work, label) for label in labels}
            if any(work.glob("*-result.json")):
                subprocess.run([sys.executable, str(Path(__file__).resolve()), "merge", "--spec", str(args.spec),
                                "--process", process, "--points", str(work / "points.json"),
                                "--work-dir", str(work), "--output", str(work / "reference.json")])
        print(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), json.dumps(states), flush=True)
        pending = [s for d in states.values() for s in d.values() if s.startswith("running")]
        if not pending:
            failed = {p: {l: s for l, s in d.items() if s != "done"} for p, d in states.items()}
            failed = {p: d for p, d in failed.items() if d}
            print("WATCH_FINISHED", json.dumps(failed) if failed else "all expected results present", flush=True)
            sys.exit(1 if failed else 0)
        time.sleep(args.interval)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "merge"):
        p = sub.add_parser(name)
        p.add_argument("--spec", type=Path, default=required_spec.DEFAULT_SPEC)
        p.add_argument("--process", required=True)
        p.add_argument("--points", type=Path, required=True)
        p.add_argument("--work-dir", type=Path, required=True)
    run = sub.choices["run"]
    run.add_argument("--provider", choices=("madloop", "recola", "openloops"), required=True)
    run.add_argument("--mg5", type=Path, help="MG5_aMC tree (MadLoop card handling, version)")
    run.add_argument("--reference-root", type=Path)
    run.add_argument("--madloop-export", type=Path)
    run.add_argument("--madloop-accuracy", type=float, default=1e-11,
                     help="relative accuracy target forcing quadruple-precision rescue; <= 0 keeps "
                     "MadLoop's production MLStabThres and its default stability test")
    run.add_argument("--tag", help="suffix for a secondary run of the same provider, e.g. "
                     "'production' (writes <provider>-<tag>-result.json; never merged as values)")
    run.add_argument("--wait-for-export", action="store_true",
                     help="poll the export's generation.json until it is compiled; fail as "
                     "soon as no live export process remains")
    run.add_argument("--wait-interval", type=float, default=300.0, help="seconds between polls")
    run.add_argument("--recola", type=Path, help="Recola2 source/build tree with librecola.so")
    run.add_argument("--recola-uncached", action="store_true")
    run.add_argument("--openloops", type=Path, help="OpenLoops installation")
    run.add_argument("--cpu", type=int)
    merge = sub.choices["merge"]
    merge.add_argument("--output", type=Path, required=True)
    merge.add_argument("--tolerance", type=float, default=2e-8)
    merge.add_argument("--exclude", action="append", default=[], metavar="PROVIDER=REASON",
                       help="keep a provider's values but leave it out of the agreement check")
    watch = sub.add_parser("watch")
    watch.add_argument("--spec", type=Path, default=required_spec.DEFAULT_SPEC)
    watch.add_argument("--root", type=Path, required=True, help="directory holding <process>/ work dirs")
    watch.add_argument("--interval", type=float, default=900.0)
    watch.add_argument("expect", nargs="+", metavar="PROCESS:LABEL[,LABEL...]",
                       help="expected provider run labels, e.g. gg_ggggg:madloop-production,madloop,recola")
    summary = sub.add_parser("summary")
    summary.add_argument("references", nargs="+", type=Path)
    args = parser.parse_args()
    if args.command == "summary":
        command_summary(args)
        return
    if args.command == "watch":
        command_watch(args)
        return
    if args.command == "run":
        if args.mg5:
            args.mg5 = args.mg5.resolve()
        command_run(args)
    else:
        command_merge(args)


if __name__ == "__main__":
    main()
