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
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import provider_paths  # noqa: E402
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
        # One derivation shared with the point construction (required_spec.masses).
        alpha, mw = 1 / p["aEWM1"], Decimal(required_spec.derived_mw(scheme))
    elif scheme["electroweak_inputs"] == "alpha_mw":
        # alpha, MZ and MW all inputs (MG5_aMC's loop_qcd_qed_sm).
        alpha, mw = 1 / p["aEWM1"], p["MW"]
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

def _gmu_or_alpha_fixed(scheme, provider):
    """Recola and OpenLoops are driven in the G_mu or fixed-alpha schemes only."""
    if scheme["electroweak_inputs"] not in ("alpha_fixed", "gmu"):
        raise NotImplementedError(
            f"{provider}: electroweak inputs {scheme['electroweak_inputs']!r} have no "
            "translation in this driver (MadLoop only)")


def recola_commands(spec, points, uncached):
    scheme = spec["scheme_data"]
    _gmu_or_alpha_fixed(scheme, "Recola")
    derived = derived_parameters(scheme)
    zero = "0"
    masses = [
        ("W", derived["MW"], width(scheme, "WW")),
        ("Z", value(scheme, "MZ"), width(scheme, "WZ")),
        ("H", value(scheme, "MH"), width(scheme, "WH")),
        ("top", value(scheme, "MT"), width(scheme, "WT")),
        ("bottom", value(scheme, "MB") or zero, zero),
        ("charm", value(scheme, "MC") or zero, zero),
        ("strange", zero, zero), ("up", zero, zero), ("down", zero, zero),
        ("tau", value(scheme, "MTA") or zero, zero), ("muon", value(scheme, "MM") or zero, zero),
        ("electron", value(scheme, "Me") or zero, zero),
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
    _gmu_or_alpha_fixed(scheme, "OpenLoops")
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
        f"double mass(5) {value(scheme, 'MB') or '0'}", "double width(5) 0",
        f"double mass(4) {value(scheme, 'MC') or '0'}",
        f"double mass(15) {value(scheme, 'MTA') or '0'}",
        f"double mass(13) {value(scheme, 'MM') or '0'}", f"double mass(11) {value(scheme, 'Me') or '0'}",
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

def madloop_process_dir(export, name=None):
    """The export's SubProcesses/P* directory: the only one, or ``name`` of a
    multi-subprocess (multiparticle) export."""
    candidates = sorted(p for p in (export / "SubProcesses").glob("P*") if p.is_dir())
    if name is not None:
        chosen = [p for p in candidates if p.name == name]
        if len(chosen) != 1:
            raise RuntimeError(f"no subprocess directory {name} in {export}: {[p.name for p in candidates]}")
        return chosen[0]
    if len(candidates) != 1:
        raise RuntimeError(f"expected one SubProcesses/P* directory in {export} (pass --subprocess)")
    return candidates[0]


def madloop_born_split_orders(process_dir):
    """Squared split orders of the Born indices of a MadLoop subprocess, from the
    DATA statement of its ``SOINDEX_FOR_SQUARED_ORDERS`` (born_matrix.f). MG5
    3.7.0's inverse routine GET_SQUARED_ORDERS_FOR_SOINDEX cannot be used: its
    common block /SQPLITORDERS/ is never initialised (the DATA fills a local
    array SQSPLITORDERS), so it returns zeros."""
    text = (process_dir / "born_matrix.f").read_text()
    text = re.sub(r"\n {5}\$", "", text)  # join fixed-form continuation lines
    function = re.search(r"INTEGER FUNCTION ML5_\d+_SOINDEX_FOR_SQUARED_ORDERS\(ORDERS\)(.*?)\n\s+END\b",
                         text, re.DOTALL)
    if function is None:
        raise RuntimeError(f"cannot find SOINDEX_FOR_SQUARED_ORDERS in {process_dir}/born_matrix.f")
    out = {}
    for match in re.finditer(r"DATA \(SQSPLITORDERS\(\s*(\d+),I\),I=\s*1,\s*2\) /\s*(-?\d+),\s*(-?\d+)/",
                             function.group(1)):
        out[int(match.group(1))] = (int(match.group(2)), int(match.group(3)))
    if not out:
        raise RuntimeError(f"no Born split orders in {process_dir}/born_matrix.f")
    return out


def madloop_helicities(export, subprocess_dir=None):
    """MadLoop's helicity configurations of a subprocess (HelConfigs.dat order)."""
    prefix = madloop_prefix(madloop_process_dir(export, subprocess_dir))
    path = export / "SubProcesses/MadLoop5_resources" / f"{prefix}HelConfigs.dat"
    return [list(map(int, line.split())) for line in path.read_text().splitlines() if line.strip()]


def madloop_prefix(process_dir):
    text = (process_dir / "loop_matrix.f").read_text()
    match = re.search(r"SUBROUTINE (ML5_\d+_)SLOOPMATRIX_THRES", text)
    if not match:
        raise RuntimeError("cannot identify the MadLoop routine prefix")
    return match.group(1)


QP_PI_TYPO = "3.14169258478796109557151794433593750E0_16"
QP_PI = "3.14159265358979323846264338327950288E0_16"


def fix_qp_model_functions(text):
    """Repair two MG5_aMC 3.7.0 defects in the quadruple-precision (MP_*) model
    functions of an export's ``Source/MODEL/model_functions.f``:

    * ``CMPLX(...)`` without ``KIND=16`` returns default (single-precision)
      complex, so MP_REGLOG/REGLOGP/REGLOGM/REGSQRT/GRREGLOG truncate real
      arguments to ~7 digits. Every UFO parameter built from them (EW on-shell
      counterterms, the top-decoupling log of the QCD counterterm) is then off
      by 1e-9..5e-7 in MadLoop's quadruple-precision rescue only.
    * ``TWOPII`` uses 3.14169258... instead of pi (branch terms only).

    Returns the repaired text and the list of applied repairs. Continuation
    markers (newline + 5 columns + ``$``) are transparent to the parser."""
    start = re.search(r"^\s*COMPLEX\*32 FUNCTION MP_", text, re.MULTILINE)
    if start is None:
        return text, []
    head, body = text[:start.start()], text[start.start():]
    out, i, fixed = [], 0, 0
    for match in re.finditer(r"(?<![A-Z0-9_])CMPLX\(", body):
        if match.start() < i:
            continue
        depth, j, args, current = 1, match.end(), [], []
        while depth:
            continuation = re.match(r"\n {5}\S", body[j:j + 7])
            if continuation:  # fixed-form continuation line: transparent
                j += 7
                continue
            c = body[j]
            if c == "\n":
                raise RuntimeError("unterminated CMPLX( in model_functions.f")
            depth += (c == "(") - (c == ")")
            if depth == 1 and c == ",":
                args.append("".join(current))
                current = []
            elif depth >= 1:
                current.append(c)
            j += 1
        args.append("".join(current))
        if not any(re.match(r"\s*KIND\s*=", arg, re.IGNORECASE) for arg in args):
            out.append(body[i:j - 1] + ",KIND=16")
            i = j - 1
            fixed += 1
    out.append(body[i:])
    body = "".join(out)
    repairs = [f"added KIND=16 to {fixed} CMPLX calls in MP_ functions"] if fixed else []
    if QP_PI_TYPO in body:
        repairs.append(f"replaced {body.count(QP_PI_TYPO)} TWOPII pi literals {QP_PI_TYPO} by {QP_PI}")
        body = body.replace(QP_PI_TYPO, QP_PI)
    return head + body, repairs


def madloop_model_fix(export, work, global_flag):
    """Compile a repaired model_functions.f into ``work`` (the export is never
    modified) with the export's ``GLOBAL_FLAG``; its object is linked before
    libmodel.a. Returns (objects, repairs)."""
    source = export / "Source/MODEL/model_functions.f"
    text, repairs = fix_qp_model_functions(source.read_text())
    if not repairs:
        return [], []
    fixed = work / "model_functions_qpfix.f"
    fixed.write_text(text)
    obj = work / "model_functions_qpfix.o"
    subprocess.run(["gfortran", "-w", "-fPIC", "-fno-common", "-ffixed-line-length-none",
                    *shlex.split(global_flag),
                    "-I", str(source.parent), "-J", str(work), "-c", str(fixed), "-o", str(obj)],
                   check=True, cwd=work)
    return [obj], repairs


def fix_unassigned_jamps(text):
    """Zero-initialise the colour-flow amplitudes of MG5_aMC 3.7.0 Born matrix
    elements that leave some ``JAMP(colour, amplitude split order)`` unassigned.

    ``JAMP`` is a local ``COMPLEX*16`` array that is not zeroed; when a colour
    flow gets no amplitude of some split order (u u~ > t t~ QCD<=2 QED<=2: no
    QED amplitude in the colour-singlet flow), its entry stays uninitialised
    stack memory and enters every squared split order built from it (garbage or
    Inf in MadLoop's ANS(0,i) Born sectors, varying from run to run). Returns
    the repaired text and the list of repairs; subroutines assigning every
    entry are left byte-identical."""
    repairs, out, start = [], [], 0
    for match in re.finditer(r"^      SUBROUTINE (\w+)\(.*?^      END\s*$", text, re.MULTILINE | re.DOTALL):
        body = match.group(0)
        declared = re.search(r"^\s+COMPLEX\*16 JAMP\((\w+),(\w+)\)", body, re.MULTILINE)
        if declared is None:
            continue
        parameters = {}
        for content in re.findall(r"^\s+PARAMETER\s*\((.*)\)", body, re.MULTILINE):
            for item in content.split(","):
                name, _, value = item.partition("=")
                if value.strip().isdigit():
                    parameters[name.strip().upper()] = int(value)
        dims = [parameters.get(d.upper(), int(d) if d.isdigit() else None) for d in declared.groups()]
        assigned = {(int(i), int(j)) for i, j in re.findall(r"^\s+JAMP\((\d+),(\d+)\)\s*=", body, re.MULTILINE)}
        if None not in dims:
            missing = sorted({(i, j) for i in range(1, dims[0] + 1) for j in range(1, dims[1] + 1)} - assigned)
            if not missing:
                continue
            what = f"{len(missing)} entries never assigned: {missing[:8]}"
        else:
            what = "dimensions not resolved; zeroed as a precaution"
        begin = re.search(r"^C\s+BEGIN CODE\s*\nC\s+-+\s*\n", body, re.MULTILINE)
        if begin is None:
            raise RuntimeError(f"born_matrix.f: no BEGIN CODE marker in {match.group(1)}")
        cut = match.start() + begin.end()
        out.append(text[start:cut] + "      JAMP(:,:) = (0D0,0D0)\n")
        start = cut
        repairs.append(f"born_matrix.f: zero-initialised JAMP in {match.group(1)} ({what})")
    out.append(text[start:])
    return "".join(out), repairs


def madloop_born_fix(process_dir, work, global_flag):
    """Compile a repaired born_matrix.f (``fix_unassigned_jamps``) into ``work``
    (the export is never modified) with the export's ``GLOBAL_FLAG`` and
    MadLoop's fixed-form line length; its object is linked before
    libMadLoop.a, so the archive's own born_matrix.o is not loaded. Returns
    (objects, repairs)."""
    source = process_dir / "born_matrix.f"
    text, repairs = fix_unassigned_jamps(source.read_text())
    if not repairs:
        return [], []
    fixed = work / "born_matrix_jampfix.f"
    fixed.write_text(text)
    obj = work / "born_matrix_jampfix.o"
    subprocess.run(["gfortran", "-w", "-fPIC", *shlex.split(global_flag), "-ffixed-line-length-132",
                    "-I", str(process_dir), "-c", str(fixed), "-o", str(obj)], check=True, cwd=work)
    return [obj], repairs


def madloop_build_flags(export, mg5):
    """The export's Fortran flags (its ``Source/make_opts``) next to MG5_aMC's
    production flags; ``production_build`` tells whether they coincide."""
    from madloop_export import make_opts_variables, production_make_opts

    production = production_make_opts(mg5)
    variables = make_opts_variables(export)
    used = {key: variables.get(key, "") for key in production}
    return {"export_make_opts": used, "mg5_production": production,
            "production_build": used == production,
            "source": "MG5_aMC run-card defaults global_flag/aloha_flag/matrix_flag "
                      "(CommonRunCmd.update_make_opts of an optimised MG5 run); "
                      "MadLoop's own makefile adds -O3 for polynomial.f"}


def build_madloop(export, work, global_flag, subprocess_dir=None):
    from build import madloop_libraries

    process_dir = madloop_process_dir(export, subprocess_dir)
    prefix = madloop_prefix(process_dir)
    source = (HERE / "madloop_driver.f90").read_text().replace("ML5_0_", prefix).replace(
        "HELCONFIGS_FILE", f"SubProcesses/MadLoop5_resources/{prefix}HelConfigs.dat")
    driver = work / "madloop_driver.f90"
    driver.write_text(source)
    binary = work / "madloop-driver"
    fixes, repairs = madloop_model_fix(export, work, global_flag)
    born_fixes, born_repairs = madloop_born_fix(process_dir, work, global_flag)
    fixes, repairs = [*fixes, *born_fixes], [*repairs, *born_repairs]
    subprocess.run(
        ["gfortran", "-O2", "-ffree-line-length-none", "-I", str(process_dir), str(driver),
         *map(str, fixes), str(export / "lib/libMadLoop.a"), "-L" + str(export / "lib"), "-ldhelas", "-lmodel",
         *map(str, madloop_libraries(export)), "-lstdc++",
         # Large exports (g g -> 6 g: 7.7 GB of static arrays) put PIC data
         # beyond the range of relaxed GOTPCREL loads; keep GOT loads.
         "-Wl,--no-relax", "-o", str(binary)],
        check=True, cwd=work,
    )
    return binary, repairs


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


def check_point_masses(spec, points):
    """Refuse points off the scheme's mass shells (``required_spec.masses``).

    A points JSON built for other masses (for example before the process moved
    to another scheme) is evaluated off shell by the providers, while a client
    takes each leg's invariant on its model mass shell: their comparison then
    measures the inconsistency, not the virtual. Printed points are on shell
    to about 1e-27 (``exact_points.py``)."""

    expected = required_spec.masses(spec)
    recorded = points.get("masses")
    if recorded is not None and [Fraction(m) for m in recorded] != expected:
        raise SystemExit(
            f"points JSON was built for the leg masses {recorded}; the scheme "
            f"{spec['scheme']!r} gives {[str(m) for m in expected]}")
    for index, point in enumerate(points["points"]):
        for leg, (momentum, mass) in enumerate(zip(point, expected, strict=True)):
            energy, *space = (Fraction(x) for x in momentum)
            shell = energy * energy - sum(x * x for x in space)
            if abs(shell - mass * mass) > energy * energy / 10**20:
                raise SystemExit(
                    f"point {index + 1}, leg {leg + 1}: p^2 = {float(shell)!r} is "
                    f"off the mass shell {float(mass * mass)!r} of the scheme "
                    f"{spec['scheme']!r}")


def run_native(command, stdin_text, cwd, log, cpu, env=None):
    env = {**os.environ, **(env or {})}
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


LAURENT = ("finite", "single_pole", "double_pole")


def madloop_sectors(values, nanswer, nloop, born_so, loop_so, step):
    """Split one SECTORS/HEL_ROW payload (ANS(0:3,0:nanswer) column-major, then
    ACC(0:nloop)) into named squared split orders. Each loop sector names the
    Born sector its Catani poles multiply (its orders minus the correction step)."""
    answer = [values[4 * j:4 * j + 4] for j in range(nanswer + 1)]
    accuracy = values[4 * (nanswer + 1):4 * (nanswer + 1) + nloop + 1]
    if len(accuracy) != nloop + 1:
        raise RuntimeError("madloop: truncated SECTORS line")
    born_orders = {}
    born = []
    for index, (qcd, qed) in sorted(born_so.items()):
        born.append({"QCD": qcd, "QED": qed, "born": answer[index][0]})
        born_orders[(qcd, qed)] = answer[index][0]
    loop = []
    for index, (qcd, qed) in sorted(loop_so.items()):
        entry = {"QCD": qcd, "QED": qed, **dict(zip(LAURENT, answer[index][1:])), "accuracy": accuracy[index]}
        partner = (qcd - step["QCD"], qed - step["QED"])
        entry["born_sector"] = {"QCD": partner[0], "QED": partner[1]} if partner in born_orders else None
        loop.append(entry)
    total = {"born": answer[0][0], **dict(zip(LAURENT, answer[0][1:])), "accuracy": accuracy[0]}
    return {"born": born, "loop": loop, "total": total}


def parse_rows(stdout, provider, count, step=None, born_so=None):
    rows = [None] * count
    extra = {}
    born_so, loop_so, hel_tuples, dims = dict(born_so or {}), {}, {}, None
    for line in stdout.splitlines():
        fields = line.split()
        if not fields:
            continue
        if provider == "madloop" and fields[0] == "LOOP_SO":
            index, qcd, qed = map(int, fields[1:4])
            loop_so[index] = (qcd, qed)
            continue
        if provider == "madloop" and fields[0] == "HEL_INDEX":
            hel_tuples[int(fields[1])] = {"madloop_index": int(fields[2]), "helicity": list(map(int, fields[3:]))}
            continue
        if provider == "madloop" and fields[0] == "SECTORS":
            i = int(fields[1]) - 1
            rows[i]["sectors"] = madloop_sectors(list(map(float, fields[3:])), dims[0], dims[1],
                                                 born_so, loop_so, step)
            continue
        if provider == "madloop" and fields[0] == "HEL_ROW":
            i, h, status = int(fields[1]) - 1, int(fields[2]), int(fields[3])
            sectors = madloop_sectors(list(map(float, fields[5:])), dims[0], dims[1], born_so, loop_so, step)
            rows[i].setdefault("per_helicity", []).append(
                {**hel_tuples[h], "status": status, "seconds": float(fields[4]), "sectors": sectors})
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
            dims = extra["split_order_indices"][2:4]
    if any(r is None for r in rows):
        raise RuntimeError(f"{provider}: missing result rows")
    if born_so or loop_so:
        extra["squared_split_orders"] = {
            "born": [{"index": i, "QCD": q, "QED": e} for i, (q, e) in sorted(born_so.items())],
            "loop": [{"index": i, "QCD": q, "QED": e} for i, (q, e) in sorted(loop_so.items())]}
        missing = [i + 1 for i, row in enumerate(rows) if "sectors" not in row]
        if missing:
            raise RuntimeError(f"madloop: no SECTORS line for points {missing}")
    if hel_tuples:
        extra["helicities"] = [hel_tuples[h] for h in sorted(hel_tuples)]
        short = [i + 1 for i, row in enumerate(rows) if len(row.get("per_helicity", ())) != len(hel_tuples)]
        if short:
            raise RuntimeError(f"madloop: incomplete per-helicity rows at points {short}")
    for index, row in enumerate(rows):
        for key in COEFFICIENTS:
            if not math.isfinite(row[key]):
                raise RuntimeError(f"{provider}: non-finite {key}")
        # Every printed number of a point, squared split orders and helicities included.
        values = [("total_all_orders", x) for x in row.get("total_all_orders", ())]
        values += sector_values(row.get("sectors"), "sectors")
        for entry in row.get("per_helicity", ()):
            values += sector_values(entry["sectors"], f"helicity {entry['helicity']}")
        bad = [where for where, x in values if not math.isfinite(x)]
        if bad:
            raise RuntimeError(f"{provider}: non-finite values at point {index + 1}: {bad[:6]}")
    return rows, extra


def sector_values(sectors, label):
    """(where, value) of every number of a madloop_sectors record."""
    if not sectors:
        return []
    out = [(f"{label} born {s['QCD']},{s['QED']}", s["born"]) for s in sectors["born"]]
    for s in sectors["loop"]:
        out += [(f"{label} loop {s['QCD']},{s['QED']} {k}", s[k]) for k in (*LAURENT, "accuracy")]
    out += [(f"{label} total {k}", v) for k, v in sectors["total"].items()]
    return out


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


def check_provider_paths(args, root):
    """Refuse provider files outside the reference root ``root`` before any of
    them is linked, loaded or run (provider_paths); no check without a root."""
    if root is None:
        print("warning: no reference root configured (--reference-root or "
              f"{provider_paths.ENVIRONMENT}); provider paths are not checked", file=sys.stderr)
        return
    from build import madloop_library_paths

    roots, what = [root], f"{args.provider} reference"
    absolute = lambda path: Path(os.path.abspath(path))  # noqa: E731 (resolve() would stat it)
    if args.provider == "madloop":
        export = absolute(args.madloop_export)
        provider_paths.check([export, *([args.mg5] if args.mg5 else [])], roots, what=what, strict=True)
        provider_paths.check(madloop_library_paths(export), roots, what=what, strict=True)
    elif args.provider == "recola":
        tree = absolute(args.recola)
        provider_paths.check([tree], roots, libraries=[tree / "librecola.so"], what=what, strict=True)
    else:
        tree = absolute(args.openloops)
        provider_paths.check([tree], roots, libraries=[tree / "lib/libopenloops.so"], what=what, strict=True)


def command_run(args):
    roots = {"mg5": args.mg5, "reference": args.reference_root}
    reference_root = provider_paths.reference_root(args.reference_root)
    check_provider_paths(args, reference_root)
    spec = required_spec.load_process(args.spec, args.process, roots)
    if args.pdgs:
        spec["pdgs"] = [int(x) for x in args.pdgs.split(",")]  # one subprocess of a multiparticle export
    points = json.loads(args.points.read_text())
    if points["pdgs"] != spec["pdgs"]:
        raise SystemExit("points JSON belongs to another process")
    check_point_masses(spec, points)
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
            production = args.madloop_accuracy <= 0
            flags = madloop_build_flags(export, args.mg5)
            if production and not flags["production_build"]:
                raise RuntimeError(
                    f"export built with {flags['export_make_opts']}, not MG5's production flags "
                    f"{flags['mg5_production']}; rebuild it with madloop_export.py --recompile")
            binary, repairs = build_madloop(export, run_dir, flags["export_make_opts"]["GLOBAL_FLAG"],
                                            args.subprocess)
            result["settings"] = prepare_madloop_run(spec, export, run_dir, args.mg5, legs)
            result["settings"]["export"] = str(export)
            result["settings"]["fortran_flags"] = flags
            result["settings"]["mg5_quadruple_precision_model_function_repairs"] = [
                r for r in repairs if not r.startswith("born_matrix.f:")]
            born_repairs = [r for r in repairs if r.startswith("born_matrix.f:")]
            if born_repairs:
                result["settings"]["mg5_born_matrix_repairs"] = born_repairs
            result["generation"] = json.loads(generation.read_text()) if generation.exists() else None
            mg5_version = re.search(r"version = (\S+)", (args.mg5 / "VERSION").read_text()).group(1)
            from build import madloop_libraries
            reducers = {lib.name: {"path": str(lib.resolve()), "version": library_version(lib.resolve())}
                        for lib in madloop_libraries(export)}
            result["version"] = f"MadLoop/MG5_aMC {mg5_version}"
            result["provenance"] = {"MG5_aMC": {"path": str(args.mg5), "version": mg5_version},
                                    "reducer_libraries": reducers}
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
            if args.helicities:
                tuples = (madloop_helicities(export, args.subprocess) if args.helicities == "all"
                          else [list(map(int, t.split(","))) for t in args.helicities.split(";")])
                stdin += f"{len(tuples)}\n" + "\n".join(" ".join(map(str, t)) for t in tuples) + "\n"
                result["settings"]["helicities"] = ("all MadLoop helicity configurations"
                                                    if args.helicities == "all" else "selected tuples")
                result["per_helicity_normalization"] = (
                    "MadLoop SLOOPMATRIXHEL_THRES: |M_h|^2 with the colour average and identical-particle "
                    "factor but no helicity average (sum over all configurations = HELAVGFACTOR x summed "
                    "value); helicity labels in MadLoop's HelConfigs.dat convention")
            if args.subprocess:
                result["settings"]["subprocess_directory"] = args.subprocess
            stdout, wall = run_native([str(binary)], stdin, run_dir, run_dir / "output.log", args.cpu)
        elif provider == "recola":
            root = args.recola.resolve()
            binary = run_dir / "recola-driver"
            subprocess.run(["gfortran", "-O2", "-ffree-line-length-none", str(HERE / "recola_driver.f90"),
                            "-I", str(root / "include"), "-L", str(root), f"-Wl,-rpath,{root}",
                            "-lrecola", "-o", str(binary)], check=True, cwd=run_dir)
            if reference_root is not None:
                provider_paths.check([], [reference_root, run_dir], libraries=[binary],
                                     what="Recola driver", strict=True)
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
            # OpenLoops loads its process libraries from <install_path>/proclib; the
            # compiled-in default is the tree it was built in, OpenLoopsPath this one.
            result["settings"]["OpenLoopsPath"] = str(root)
            stdin = "\n".join(commands + [f"points {count}", *point_lines(points)]) + "\n"
            stdout, wall = run_native([str(binary)], stdin, run_dir, run_dir / "output.log", args.cpu,
                                      env={"OpenLoopsPath": str(root)})
        step = {k: spec["loop_orders"][k] - spec["born_orders"][k] for k in ("QCD", "QED")}
        born_so = (madloop_born_split_orders(madloop_process_dir(args.madloop_export.resolve(), args.subprocess))
                   if provider == "madloop" else None)
        rows, extra = parse_rows(stdout, provider, count, step, born_so)
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


def point_construction(points):
    """The points file's construction record; ``scale_variation`` also names
    its rows 0-based (``point`` and ``copy_of_point`` are 1-based)."""
    out = {k: points[k] for k in ("construction", "cuts", "sqrt_s", "family", "family_values", "rotation",
                                  "madloop_qp_point", "point_labels", "precision", "scale_variation")
           if k in points}
    if "scale_variation" in out:
        variation = out["scale_variation"]
        out["scale_variation"] = {**variation, "row": variation["point"] - 1,
                                  "copy_of_row": variation["copy_of_point"] - 1}
    return out


POINT_STATUSES = ("ok", "none")
COMPARISONS = ("relative", "absolute")


def point_statuses(text, count):
    """Per-point reference statuses (``--point-status``): a JSON object keyed by
    0-based row index, e.g. ``{"2": {"status": "none", "reason": "..."}}`` or
    ``{"0": {"comparison": "absolute", "scale_row": 2, "reason": "..."}}``."""
    statuses = {}
    for key, entry in (json.loads(text) if text else {}).items():
        index = int(key)
        if not 0 <= index < count:
            raise SystemExit(f"--point-status: row {index} outside 0..{count - 1}")
        unknown = set(entry) - {"status", "comparison", "scale_row", "reason"}
        if unknown:
            raise SystemExit(f"--point-status: unknown keys {sorted(unknown)}")
        entry = {"status": "ok", "comparison": "relative", **entry}
        if entry["status"] not in POINT_STATUSES or entry["comparison"] not in COMPARISONS:
            raise SystemExit(f"--point-status: row {index}: status in {POINT_STATUSES}, "
                             f"comparison in {COMPARISONS}")
        if (entry["comparison"] == "absolute") != ("scale_row" in entry):
            raise SystemExit(f"--point-status: row {index}: an absolute comparison needs scale_row (only)")
        if not entry.get("reason"):
            raise SystemExit(f"--point-status: row {index}: a reason is required")
        statuses[index] = entry
    for index, entry in statuses.items():
        scale = entry.get("scale_row")
        if scale is not None and (scale not in range(count) or statuses.get(scale, {}).get("comparison",
                                                                                           "relative") != "relative"):
            raise SystemExit(f"--point-status: row {index}: scale_row {scale} must be a relative-comparison row")
    return statuses


def sector_pole_error(madloop_row, pole_factor, coupling, absolute_scale=None):
    """Largest violation of the universal double pole, per loop squared split
    order: |D_s - factor * Born(born sector of s)| over max(|D_s|, |factor *
    Born|, the point's largest |D|, |Born| * coupling/(2 pi), |factor| *
    absolute_scale). MadLoop's values as printed (Born in double precision at
    the binary64 input): a garbage or overflowing Born sector violates it at
    O(1); limit points violate it by their binary64 Born condition."""
    sectors = madloop_row.get("sectors")
    pairs = []
    if sectors:
        born = {(b["QCD"], b["QED"]): b["born"] for b in sectors["born"]}
        for loop in sectors["loop"]:
            partner = loop["born_sector"]
            pairs.append((loop["double_pole"], born[(partner["QCD"], partner["QED"])] if partner else 0.0))
    else:
        pairs.append((madloop_row["double_pole"], madloop_row["born"]))
    largest = max(abs(d) for d, _ in pairs)
    worst = 0.0
    for double_pole, born_value in pairs:
        floor = max(largest, abs(born_value) * coupling / (2 * math.pi),
                    abs(pole_factor) * (absolute_scale or 0.0))
        worst = max(worst, relative(double_pole, pole_factor * born_value, floor))
    return worst


def madloop_point(qp_point, status):
    """Which point MadLoop's loop values refer to."""
    if isinstance(status, int) and status // 100 in (3, 4):
        return ("published point (quadruple precision)" if qp_point else
                "MadLoop's quadruple-precision repair of the binary64 rounding (~1e-16 from the published point)")
    return "binary64 rounding of the published point (double precision)"


def madloop_references(rows, madloop_rows, primary, pole_factor, coupling, statuses, qp_point, tolerance):
    """Per point: the reference Born at the published point and a
    machine-readable ``reference`` record; refuses a point whose MadLoop sector
    values violate the universal double pole beyond ``tolerance`` unless its
    status declares it. At ``madloop_qp_point`` points MadLoop's printed Born
    (ANS(0), double precision at the binary64 input) is not the Born at the
    published point; its quadruple-precision double pole over the universal
    factor is, so it becomes the reference Born (row and sectors) and the
    printed value is kept as ``born_madloop_binary64_input``."""
    substitute = qp_point and bool(pole_factor)
    for row, madloop_row in zip(rows, madloop_rows, strict=True):
        if not substitute:
            continue
        if primary == "madloop":
            row["born_madloop_binary64_input"] = row["born"]
            row["born"] = madloop_row["double_pole"] / pole_factor
        sectors = row.get("sectors")
        if sectors:
            sectors = row["sectors"] = json.loads(json.dumps(sectors))
            loops = {(s["born_sector"]["QCD"], s["born_sector"]["QED"]): s for s in sectors["loop"]
                     if s["born_sector"]}
            for born in sectors["born"]:
                loop = loops.get((born["QCD"], born["QED"]))
                if loop is not None:
                    born["born_binary64_input"] = born["born"]
                    born["born"] = loop["double_pole"] / pole_factor
            sectors["total"]["born_binary64_input"] = sectors["total"]["born"]
            sectors["total"]["born"] = sectors["total"]["double_pole"] / pole_factor
    refused = []
    for index, (row, madloop_row) in enumerate(zip(rows, madloop_rows, strict=True)):
        status = statuses.get(index, {"status": "ok", "comparison": "relative"})
        scale_row = status.get("scale_row")
        absolute_scale = abs(rows[scale_row]["born"]) if scale_row is not None else None
        pole_error = sector_pole_error(madloop_row, pole_factor, coupling, absolute_scale)
        mismatch = None
        if pole_factor:
            mismatch = relative(madloop_row["born"], madloop_row["double_pole"] / pole_factor,
                                absolute_scale or 0.0)
        row["reference"] = {
            "status": status["status"],
            "comparison": status["comparison"],
            "absolute_scale_row": scale_row,
            "absolute_scale": absolute_scale,
            "born_source": ("madloop_double_pole_over_universal_factor" if substitute and primary == "madloop"
                            else primary),
            "madloop_point": madloop_point(qp_point, madloop_row.get("status")),
            "born_double_pole_relative_mismatch": mismatch,
            "max_sector_double_pole_relative_error": pole_error,
            "reason": status.get("reason"),
        }
        if status["status"] == "ok" and pole_error > tolerance:
            refused.append(f"point {index + 1}: {pole_error:.3g}")
    if refused:
        raise SystemExit("MadLoop values violate the universal double pole (a non-physical Born or loop sector, "
                         f"e.g. uninitialised memory) beyond {tolerance:g}: {'; '.join(refused)}; declare a limit "
                         "point with --point-status if this is its known binary64 condition")


def command_merge(args):
    spec = required_spec.load_process(args.spec, args.process)
    if args.pdgs:
        spec["pdgs"] = [int(x) for x in args.pdgs.split(",")]
    points = json.loads(args.points.read_text())
    check_point_masses(spec, points)
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
        if "madloop" in results:
            madloop_row = results["madloop"]["rows"][index]
            row["madloop_accuracy"] = madloop_row.get("accuracy")
            row["madloop_status"] = madloop_row.get("status")
            if "sectors" in madloop_row:
                row["sectors"] = madloop_row["sectors"]
            if pole_factor:
                # MadLoop's Born (ANS(0)) is evaluated in double precision at the
                # binary64 input point, its quadruple-precision loop at the improved
                # point: there the Born is the double pole over the universal factor.
                row["born_from_madloop_double_pole"] = madloop_row["double_pole"] / pole_factor
        row["providers"] = {}
        row["provider_pair_relative_errors"] = {}
        row["provider_pair_strict_relative_errors"] = {}
        for provider, result in results.items():
            values = result["rows"][index]
            row["providers"][provider] = {k: v for k, v in values.items()
                                          if k not in ("total_all_orders", "sectors")}
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
    qp_point = bool(points.get("madloop_qp_point"))
    if "madloop" in results:
        madloop_references(rows, results["madloop"]["rows"], primary, pole_factor, coupling,
                           point_statuses(args.point_status, len(rows)), qp_point, args.tolerance)
    elif args.point_status:
        raise SystemExit("--point-status needs a MadLoop result")
    max_error = max(errors) if errors else None
    passed = (len(validated) >= 2 and max_error < args.tolerance and max(pole_errors) < args.tolerance)
    normalization = required_spec.normalization(spec)
    providers = {}
    for provider, result in results.items():
        providers[provider] = {k: v for k, v in result.items() if k not in ("rows",)}
        providers[provider]["evaluation_seconds"] = [r["seconds"] for r in result["rows"]]
    # Secondary timing runs (e.g. MadLoop at its production stability setting):
    # timings and their deviation from the accurate run only, never reference values.
    # Without the provider's own reference run (still running) the secondary run
    # is reported separately and compared with the merged reference values.
    timing_only = {}
    per_helicity = None
    for path in sorted(work.glob("*-*-result.json")):
        label = path.name[: -len("-result.json")]
        provider, _, tag = label.partition("-")
        if provider not in ("madloop", "recola", "openloops"):
            continue
        secondary = json.loads(path.read_text())
        if "helicities" in secondary:
            # Per-helicity reference values (MadLoop SLOOPMATRIXHEL_THRES), not timings.
            if per_helicity is not None:
                raise SystemExit(f"two per-helicity runs in {work}")
            per_helicity = {
                "provider": provider, "run": label,
                "normalization": secondary.get("per_helicity_normalization"),
                "helicities": secondary["helicities"],
                "settings": {k: secondary["settings"][k] for k in
                             ("requested_relative_accuracy", "stability_check", "helicities")
                             if k in secondary.get("settings", {})},
                "rows": [[{"helicity": entry["helicity"], "madloop_index": entry["madloop_index"],
                           "status": entry["status"], **{k: entry["sectors"]["total"][k] for k in COEFFICIENTS
                                                          if k in entry["sectors"]["total"]},
                           "accuracy": entry["sectors"]["total"]["accuracy"],
                           **({"sectors": entry["sectors"]} if len(entry["sectors"]["loop"]) > 1
                              or len(entry["sectors"]["born"]) > 1 else {})}
                          for entry in hel_row["per_helicity"]] for hel_row in secondary["rows"]],
            }
            continue
        own = provider in results
        against = results[provider]["rows"] if own else rows
        deviation = []
        for accurate, other in zip(against, secondary["rows"], strict=True):
            unit = abs(accurate["born"]) * coupling / (2 * math.pi)
            deviation.append({key: relative(other[key], accurate[key], 0.0 if key == "born" else unit)
                              for key in COEFFICIENTS})
        entry = {
            "settings": {k: secondary["settings"][k] for k in ("requested_relative_accuracy", "stability_check", "fortran_flags")
                         if k in secondary.get("settings", {})},
            "version": secondary.get("version"),
            "evaluation_seconds": [r["seconds"] for r in secondary["rows"]],
            "statuses": [r.get("status") for r in secondary["rows"]],
            "estimated_accuracies": [r.get("accuracy") for r in secondary["rows"]],
            ("relative_deviation_from_reference_run" if own
             else "relative_deviation_from_merged_reference"): deviation,
            "initial_call_seconds": secondary.get("initial_call_seconds"),
            "cpu": secondary.get("cpu"),
        }
        if own:
            providers[provider].setdefault("secondary_runs", {})[tag] = entry
        else:
            timing_only[label] = entry
    report = {
        "process": spec["madloop"]["process"] if "madloop" in spec else spec["name"],
        "name": spec["name"],
        "pdgs": spec["pdgs"],
        "correction": spec["correction"],
        "born_orders": spec["born_orders"],
        "loop_orders": spec["loop_orders"],
        "scheme": spec["scheme"],
        "scheme_description": scheme["description"],
        "restriction": scheme.get("restriction"),
        "madloop_model": Path(spec["madloop"]["model"]).name if "madloop" in spec else None,
        "gauge": spec.get("madloop", {}).get("gauge", "Feynman"),
        "parameter_overrides": scheme.get("parameter_overrides", {}),
        "born_orders_all": spec["born_orders_all"],
        "squared_split_orders": results.get("madloop", {}).get("squared_split_orders"),
        "source": "independent references: " + "; ".join(
            results[p].get("version", p) for p in results),
        "scope": "Independent provider references at exact on-shell decimal points; "
                 + provider_arithmetic(results)
                 + "; timings are single-run by-products, not benchmarks.",
        "convention": "MadLoop/BLHA C_eps=(4pi)^eps/Gamma(1-eps); F_MadLoop=F_Recola+pi^2/6*D; "
                      "OpenLoops truepoles=1, polenorm=0; physical couplings, no alpha extraction; "
                      "initial spin/colour average and final identical-particle factor included",
        "normalization": normalization,
        "normalization_denominator": normalization["denominator"],
        "points": points["points"],
        "mu_r": points["mu_r"],
        "point_construction": point_construction(points),
        "parameters": scheme["parameters"],
        "fixed_parameters": scheme["fixed_parameters"],
        "derived_parameters": derived,
        "active_flavours": scheme["active_flavours"],
        "loop_quark_flavours": scheme["loop_quark_flavours"],
        "rows": rows,
        "per_helicity": per_helicity,
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
        "timing_only_runs": timing_only,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{spec['name']}: providers={validated} excluded={list(excluded)} max_rel={max_error} "
          f"max_pole_identity={max(pole_errors):.3g} status={report['validation_status']}")
    if not passed:
        sys.exit(2)


def provider_arithmetic(results):
    """The arithmetic of each provider's values as its run records it. MadLoop
    reports a return code 100*H + 10*T + U per point, H = 1, 2 for double and
    3, 4 for quadruple precision; the other providers keep no per-point record,
    so their recorded settings describe them."""
    parts = []
    for provider, result in results.items():
        statuses = [row.get("status") for row in result["rows"]]
        quadruple = [isinstance(s, int) and s // 100 in (3, 4) for s in statuses]
        if provider == "madloop" and statuses and all(isinstance(s, int) for s in statuses):
            codes = ", ".join(str(s) for s in sorted(set(statuses)))
            if all(quadruple):
                parts.append(f"MadLoop in quadruple precision at every point (return codes {codes})")
            elif any(quadruple):
                parts.append("MadLoop in quadruple precision where its return code is 3xx or 4xx, "
                             f"double precision elsewhere (return codes {codes})")
            else:
                parts.append(f"MadLoop in double precision (return codes {codes})")
        else:
            parts.append(f"{provider} as configured in its recorded settings")
    return "; ".join(parts)


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
        for label, run in d.get("timing_only_runs", {}).items():
            t = run["evaluation_seconds"]
            per.append(f"{label} {sum(t) / len(t):.3g} (timing only)")
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
        p.add_argument("--pdgs", help="comma-separated PDGs of one subprocess of a multiparticle export")
    run = sub.choices["run"]
    run.add_argument("--provider", choices=("madloop", "recola", "openloops"), required=True)
    run.add_argument("--mg5", type=Path, help="MG5_aMC tree (MadLoop card handling, version)")
    run.add_argument("--reference-root", type=Path,
                     help=f"reference root (default ${provider_paths.ENVIRONMENT}); provider files "
                     "outside it are refused")
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
    run.add_argument("--subprocess", help="SubProcesses/P* directory of a multiparticle MadLoop export")
    run.add_argument("--helicities", help="MadLoop per-helicity mode: 'all' (every HelConfigs.dat "
                     "configuration) or 'h1,h2,...;h1,h2,...' tuples (use with --tag)")
    merge = sub.choices["merge"]
    merge.add_argument("--output", type=Path, required=True)
    merge.add_argument("--tolerance", type=float, default=2e-8)
    merge.add_argument("--exclude", action="append", default=[], metavar="PROVIDER=REASON",
                       help="keep a provider's values but leave it out of the agreement check")
    merge.add_argument("--point-status", metavar="JSON",
                       help="per-point reference statuses keyed by 0-based row: status ok|none, comparison "
                       "relative|absolute (with scale_row), reason")
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
            args.mg5 = Path(os.path.abspath(args.mg5))  # checked before it is resolved
        command_run(args)
    else:
        command_merge(args)


if __name__ == "__main__":
    main()
