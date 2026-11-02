#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""NJet references for the all-gluon ladder g g -> (n-2) g, n = 4..7, and
(BLHA mode, ``--process``) for NJet's other massless QCD channels.

Subcommands
-----------
``points``     exact points JSON: ``exact_points.generate`` for n massless legs
               (pyAmpliCol's generator and order) or the points of a
               ``tests/fixtures/loop/required`` fixture.
``run``        evaluate NJet (``njet_driver.cpp``) at a points JSON, one pinned
               CPU, and write a result JSON with provenance. ``--nc N`` sets
               NJet's N_c (MQ-NC's oracle): direct mode keeps the N_c = 3
               colour average of its normalisation; blha mode (``Extra NJetNc
               N`` in the order file) has NJet's average at N_c, which the
               result corrects to the N_c = 3 one (``colour_average``).
``nc-entry``   one process entry of the N_c-scan fixture
               (``tests/fixtures/loop/nc/njet_nc_scan.json``) from ``run``
               results at several N_c.
``openloops``  the matching OpenLoops 2 values (``../openloops_driver.cpp``)
               with the top quark in the loops (``nf=6``, as the fixtures) or
               without it (``nf=5``, massless five-flavour QCD as NJet).
``compare``    coefficient-wise comparison of two result/reference JSONs.

Conventions (README "NJet"): NJet's BLHA2 output in CDR with MS-bar
renormalisation is the MadLoop/BLHA convention of the fixtures
(``C_eps=(4 pi)^eps/Gamma(1-eps)``, physical couplings, initial average and
final symmetry) with five massless quark flavours and no top quark. The
driver's direct mode applies the BLHA normalisation of ``njet_olp.cpp``
itself; ``run --mode blha`` goes through ``OLP_EvalSubProcess2``.
"""

import argparse
import hashlib
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from exact_points import _matmul, _rotate, _rotation, check, decimal_string, generate  # noqa: E402
import provider_paths  # noqa: E402

COEFFICIENTS = ("born", "finite", "single_pole", "double_pole")
PKG_CONFIG = "/nix/store/1c6lyixjky1pfr9ia3mvpy01sxxh307a-pkg-config-0.29.2/bin"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cpu_model():
    for line in Path("/proc/cpuinfo").read_text().splitlines():
        if line.startswith("model name"):
            return line.split(":", 1)[1].strip()
    return platform.processor()


# ------------------------------------------------------------------ points


def command_points(args):
    if args.fixture:
        ref = json.loads(Path(args.fixture).read_text())
        points, mu_r = ref["points"], [str(m) for m in ref["mu_r"]]
        source = f"points and mu_r of {Path(args.fixture).name}"
    else:
        found = generate([0] * args.legs, count=args.count, cut=Fraction(args.cut))
        # exact_points accepts one point per sqrt(s), so only a handful exist
        # per multiplicity; timing sets are filled with exactly rotated copies
        # (rational rotation, mass shells and momentum conservation exact).
        rotation = _matmul(
            _rotation(2, (Fraction(3, 5), Fraction(4, 5))),
            _rotation(0, (Fraction(7, 25), Fraction(24, 25))),
        )
        for point in found[: args.rotated]:
            copy = [_rotate(rotation, p) for p in point]
            check(copy, [0] * args.legs)
            found.append(copy)
        points = [
            [[decimal_string(x) for x in leg] for leg in point] for point in found
        ]
        mu_r = [args.mu_r[i % len(args.mu_r)] for i in range(len(points))]
        source = (
            f"tools/loop_reference/exact_points.generate([0]*{args.legs}, count={args.count}, "
            f"cut={args.cut}) (the generator and order of pyAmpliCol's loop_v2_generate/campaign)"
        )
        if args.rotated:
            source += (
                f"; points {args.count}..{args.count + args.rotated - 1} are points "
                f"0..{args.rotated - 1} rotated by Rz(3/5,4/5) Rx(7/25,24/25)"
            )
    report = {"legs": len(points[0]), "source": source, "points": points, "mu_r": mu_r}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=1) + "\n")
    print(args.output)


# Exact rational rotations (Pythagorean cos/sin, terminating decimals). The
# colour- and helicity-summed virtual is a Lorentz scalar, so NJet may be
# evaluated at a rotated copy of a point; NJet's numerics are not
# orientation-blind (README "NJet"), so references use generic orientations.
ROTATIONS = {
    "R1": ((2, (3, 5), (4, 5)), (0, (7, 25), (24, 25))),
    "R2": ((1, (117, 125), (44, 125)), (2, (7, 25), (24, 25))),
}


def rotation_matrix(name):
    matrix = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    for axis, c, s_ in ROTATIONS[name]:
        matrix = _matmul(matrix, _rotation(axis, (Fraction(*c), Fraction(*s_))))
    return matrix


def rotate_points(points, name):
    matrix = rotation_matrix(name)
    out = []
    for point in points:
        exact = [_rotate(matrix, [Fraction(x) for x in leg]) for leg in point]
        check(exact, [0] * len(exact))
        out.append([[decimal_string(x) for x in leg] for leg in exact])
    return out


def points_text(points, mu_r):
    lines = [f"{len(points)} {len(points[0])}"]
    for point, mu in zip(points, mu_r, strict=True):
        lines.append(str(mu))
        lines += [" ".join(str(x) for x in leg) for leg in point]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------- NJet


def njet_install(build):
    """(prefix, pkg-config file or None, version) of a build_njet.sh build."""
    prefix = Path(build) / "njet" / "prefix"
    pcs = sorted((prefix / "lib" / "pkgconfig").glob("njet*.pc"))
    if pcs:
        version = re.search(r"^Version:\s*(\S+)", pcs[0].read_text(), re.M).group(1)
        return prefix, pcs[0], version
    # NJet 2 installs neither a pkg-config file nor its internal headers.
    config = (Path(build) / "njet" / "build" / "config.h").read_text()
    version = re.search(r'PACKAGE_VERSION "([^"]+)"', config).group(1)
    return prefix, None, version


def njet_source(build):
    info = (Path(build) / "build-info.txt").read_text()
    return Path(re.search(r"^njet_source: (.+)$", info, re.M).group(1))


def check_build_paths(build, paths=(), libraries=(), driver_dir=None):
    """Refuse (with a configured reference root; warn without one) NJet files
    outside the build directory and the reference root (provider_paths)."""
    root = provider_paths.reference_root()
    provider_paths.check(paths, [Path(build).resolve(), root, driver_dir], libraries=libraries,
                         what="NJet build", strict=root is not None)


def build_driver(build, out_dir):
    """Compile njet_driver.cpp against an NJet build (cached by source digest)."""
    prefix, pc, version = njet_install(build)
    digest = sha256(HERE / "njet_driver.cpp")[:12]
    binary = Path(out_dir) / f"njet_driver-{Path(build).resolve().name}-{digest}"
    if binary.exists():
        check_build_paths(build, libraries=[binary], driver_dir=binary.parent.resolve())
        return binary, version
    qd = Path(build) / "qd" / "prefix" / "lib"
    if pc is not None:
        env = dict(os.environ)
        paths = [str(pc.parent)]
        if (qd / "pkgconfig").is_dir():
            paths.insert(0, str(qd / "pkgconfig"))
        env["PKG_CONFIG_PATH"] = ":".join(paths)
        env["PATH"] = PKG_CONFIG + ":" + env["PATH"]
        flags = subprocess.run(
            ["pkg-config", "--cflags", "--libs", pc.stem],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()
    else:
        # NJet 2: the internal headers of its own (unmodified) source tree,
        # the build's config.h, the bundled QD installed with it.
        flags = [
            "-DUSE_DD",
            f"-I{njet_source(build)}",
            f"-I{Path(build) / 'njet' / 'build'}",
            f"-I{prefix / 'include'}",
            f"-L{prefix / 'lib'}",
            "-lnjet2",
            "-lqd",
            "-lqcdloop1",
        ]
    if (qd / "libqdmod.so").exists():
        # --with-oneloop: OneLOop's double-double integrals use QD's Fortran module.
        gfortran = (
            Path(
                subprocess.run(
                    ["gfortran", "-print-file-name=libgfortran.so"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
            )
            .resolve()
            .parent
        )
        flags += [
            "-lqdmod",
            "-lqd",
            f"-L{gfortran}",
            "-lgfortran",
            f"-Wl,-rpath,{gfortran}",
        ]
    rpaths = [f"-Wl,-rpath,{prefix / 'lib'}"] + (
        [f"-Wl,-rpath,{qd}"] if qd.is_dir() else []
    )
    check_build_paths(build, paths=[f[2:] for f in flags if f[:2] in ("-I", "-L")],
                      libraries=sorted((prefix / "lib").glob("lib*.so")))
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    command = [
        "g++",
        "-std=c++17",
        "-O2",
        str(HERE / "njet_driver.cpp"),
        "-o",
        str(binary),
        *flags,
        *rpaths,
    ]
    subprocess.run(command, check=True)
    (binary.parent / (binary.name + ".command")).write_text(" ".join(command) + "\n")
    check_build_paths(build, libraries=[binary], driver_dir=binary.parent.resolve())
    return binary, version


def blha_process(text, legs):
    """(initial PDG codes, final PDG codes) of a BLHA process line
    ``"2 -2 -> 21 21 21"``; ``None`` is the all-gluon channel of ``legs``."""

    if text is None:
        return [21, 21], [21] * (legs - 2)
    initial, arrow, final = text.partition("->")
    if not arrow:
        raise SystemExit(f"--process must read 'a b -> c d ...', got {text!r}")
    initial, final = [int(x) for x in initial.split()], [int(x) for x in final.split()]
    if len(initial) != 2 or len(initial) + len(final) != legs:
        raise SystemExit(f"--process {text!r} does not have the points' {legs} legs")
    return initial, final


def colour_states(pdg, nc):
    """NJet's colour states of a leg at N_c = ``nc`` (njet.py
    ``Process.get_colour_dof``): N_c for a quark, N_c^2 - 1 for the gluon, 1
    for a colour singlet."""

    if pdg == 21:
        return nc * nc - 1
    return nc if 1 <= abs(pdg) <= 6 else 1


def colour_average(initial, nc):
    """NJet's initial-state colour average at N_c = ``nc`` (njet.py
    ``Process.get_process``: the product of the incoming legs' states)."""

    out = Fraction(1)
    for pdg in initial:
        out *= colour_states(pdg, nc)
    return out


def sign_contract(build, run_dir, legs, amp, options, process=None):
    """Order file -> contract signed by the build's own njet.py.

    ``process`` is the BLHA line (``blha_process``); with ``options["nc"]``
    the order file sets NJet's global ``NJetNc``, which changes the colour
    sums and NJet's initial colour average (``colour_average``)."""
    prefix, _, _ = njet_install(build)
    amplitude = {"standard": "loop", "ds": "loopds"}[amp]
    initial, final = blha_process(process, legs)
    lines = [
        "CorrectionType QCD",
        "IRregularisation CDR",
        f"AlphasPower {legs - 2}",
        f"AmplitudeType {amplitude}",
        "Extra NJetReturnAccuracy 2",
        f"Extra NJetMultiPrec {options['multiprec']}",
        f"Extra Precision {options['precision']}",
        f"Extra NJetNc {options.get('nc', '3')}",
        f"SetParameter qcd(Nf) {options['nf']}",
        " ".join(map(str, initial)) + " -> " + " ".join(map(str, final)),
    ]
    order = run_dir / "OLE_order.lh"
    order.write_text("\n".join(lines) + "\n")
    contract = run_dir / "OLE_contract.lh"
    subprocess.run(
        [
            sys.executable,
            "-I",
            str(prefix / "bin" / "njet.py"),
            str(order),
            "-o",
            str(contract),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    text = contract.read_text()
    if "Error" in text or "| 1 1 #" not in text:
        raise SystemExit(f"njet.py did not accept the order file:\n{text}")
    return contract


def corrected_row(row, factor):
    """``row`` with its values times ``factor`` (32 digits) and the raw NJet
    values under ``"njet"``."""

    if factor == 1:
        return row
    from decimal import Decimal, localcontext

    out = dict(row, njet={key: row[key] for key in COEFFICIENTS})
    with localcontext() as context:
        context.prec = 32
        scale = Decimal(factor.numerator) / Decimal(factor.denominator)
        for key in COEFFICIENTS:
            out[key] = str(Decimal(row[key]) * scale)
    return out


def command_run(args):
    pts = json.loads(Path(args.points).read_text())
    indices = list(range(len(pts["points"]))) if args.indices is None else args.indices
    pts["points"] = [pts["points"][i] for i in indices]
    pts["mu_r"] = [pts["mu_r"][i] for i in indices]
    evaluated = (
        rotate_points(pts["points"], args.rotation) if args.rotation else pts["points"]
    )
    run_dir = Path(args.output).with_suffix("")
    run_dir.mkdir(parents=True, exist_ok=True)
    binary, version = build_driver(args.njet_build, Path(args.driver_dir))
    (run_dir / "points.txt").write_text(points_text(evaluated, pts["mu_r"]))
    legs = pts["legs"]
    options = {
        "mode": args.mode,
        "amp": args.amp,
        "prec": args.prec,
        "scaling": args.scaling,
        "rotation": (
            None
            if not args.rotation
            else {
                "name": args.rotation,
                "factors": ROTATIONS[args.rotation],
                "note": "NJet evaluated at the exactly rotated points",
            }
        ),
        "alphas": args.alphas,
        "nf": args.nf,
        "nc": args.nc,
        "scheme": args.scheme,
        "renorm": args.renorm,
    }
    command = [
        str(binary),
        args.mode,
        f"points={run_dir / 'points.txt'}",
        f"alphas={args.alphas}",
    ]
    correction = None
    if args.mode == "blha":
        options.update(
            multiprec=args.multiprec, precision=args.precision, process=args.process
        )
        for key in ("prec", "scaling", "scheme", "renorm"):
            options.pop(key)
        if args.scheme != "cdr" or args.renorm != "1":
            raise SystemExit("blha mode uses the contract's CDR and renormalisation")
        contract = sign_contract(
            args.njet_build, run_dir, legs, args.amp, options, args.process
        )
        command.append(f"contract={contract}")
        # NJetNc also changes NJet's initial colour average; the values are
        # brought to the N_c = 3 average (pyAmpliCol's N_c scan keeps the
        # request's, tests/unit/loop_nc_scan.py): times avg(N_c) / avg(3).
        initial, _ = blha_process(args.process, legs)
        nc = Fraction(args.nc)
        factor = colour_average(initial, nc) / colour_average(initial, Fraction(3))
        correction = {
            "nc": args.nc,
            "njet_average": str(colour_average(initial, nc)),
            "reference_average": str(colour_average(initial, Fraction(3))),
            "factor": str(factor),
            "note": "NJet's BLHA output divides by its initial colour average at "
            "N_c (njet.py get_colour_dof); born/double_pole/single_pole/finite are "
            "multiplied by factor = avg(N_c)/avg(3) (the N_c = 3 average); the raw "
            "NJet values are under 'njet'",
        }
        options["colour_average"] = correction
    else:
        if args.process is not None:
            raise SystemExit("direct mode evaluates the all-gluon channels only")
        command += [
            f"legs={legs}",
            f"amp={args.amp}",
            f"prec={args.prec}",
            f"scaling={args.scaling}",
            f"nf={args.nf}",
            f"nc={args.nc}",
            f"scheme={args.scheme}",
            f"renorm={args.renorm}",
        ]
    if args.cpu is not None:
        command = ["taskset", "-c", str(args.cpu), *command]
    started = time.time()
    with open(run_dir / "driver.log", "w") as log:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log, text=True)
        rows, init = [], None
        for line in proc.stdout:
            log.write(line)
            log.flush()
            if not line.startswith("{"):
                continue
            row = json.loads(line)
            if "initialisation_seconds" in row:
                init = row["initialisation_seconds"]
            elif "index" in row:
                row["index"] = indices[row["index"]]
                if correction is not None:
                    row = corrected_row(row, Fraction(correction["factor"]))
                rows.append(row)
                print(
                    json.dumps({k: row[k] for k in ("index", "seconds", "finite")}),
                    flush=True,
                )
        code = proc.wait()
    if code:
        raise SystemExit(f"njet_driver failed ({code}); see {run_dir / 'driver.log'}")
    build_info = Path(args.njet_build) / "build-info.txt"
    result = {
        "tool": f"NJet {version}",
        "njet_build": str(Path(args.njet_build).resolve()),
        "build_info": build_info.read_text() if build_info.exists() else None,
        "driver": {
            "binary": str(binary),
            "source_sha256": sha256(HERE / "njet_driver.cpp"),
            "compile": (binary.parent / (binary.name + ".command")).read_text().strip(),
        },
        "options": options,
        "command": command,
        "host": platform.node(),
        "cpu_model": cpu_model(),
        "cpu": args.cpu,
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "wall_seconds": round(time.time() - started, 3),
        "legs": legs,
        "points_source": pts["source"],
        "points_file": str(Path(args.points).resolve()),
        "indices": indices,
        "points": pts["points"],
        "mu_r": pts["mu_r"],
        "initialisation_seconds": init,
        "rows": rows,
    }
    Path(args.output).write_text(json.dumps(result, indent=1) + "\n")
    print(args.output)


# ------------------------------------------------------------------- Catani


def command_catani(args):
    """IR-pole prediction from NJet's colour-correlated Borns (tree level only).

    For massless gluons, MS-bar with n_f light flavours and the MadLoop/BLHA
    C_eps normalisation (Catani-Seymour I operator, 2 Re<M0|M1> = -<M0|I|M0>
    at the poles):
      double = -(alpha_s/2pi) sum_i C_A B,
      single = (alpha_s/2pi) [ -sum_i gamma_g B
                               + sum_{i != j} <T_i.T_j> log(mu^2 / |2 p_i.p_j|) ],
    gamma_g = 11/6 C_A - 2/3 T_F n_f. The i pi of timelike invariants is
    imaginary at this order and drops out of the real part.
    """
    pts = json.loads(Path(args.points).read_text())
    run_dir = Path(args.output).with_suffix("")
    run_dir.mkdir(parents=True, exist_ok=True)
    binary, version = build_driver(args.njet_build, Path(args.driver_dir))
    (run_dir / "points.txt").write_text(points_text(pts["points"], pts["mu_r"]))
    command = [
        str(binary),
        "cc",
        f"points={run_dir / 'points.txt'}",
        f"alphas={args.alphas}",
        f"prec={args.prec}",
    ]
    proc = subprocess.run(command, capture_output=True, text=True, check=True)
    (run_dir / "driver.log").write_text(proc.stdout + proc.stderr)
    alphas = float(Fraction(args.alphas))
    ca, tf, nf = 3.0, 0.5, int(args.nf)
    gamma_g = 11.0 / 6.0 * ca - 2.0 / 3.0 * tf * nf
    rows = []
    for line in proc.stdout.splitlines():
        if not line.startswith('{"index'):
            continue
        row = json.loads(line)
        i = row["index"]
        point = [[Fraction(x) for x in leg] for leg in pts["points"][i]]
        legs = len(point)
        born = float(row["born"])
        mu2 = Fraction(pts["mu_r"][i]) ** 2
        cc = {(a, b): float(v) for a, b, v in row["cc"]}
        conservation = max(
            abs(
                sum(cc[tuple(sorted((a, b)))] for b in range(legs) if b != a)
                + ca * born
            )
            / (ca * born)
            for a in range(legs)
        )
        logs = 0.0
        for (a, b), value in cc.items():
            p, q = point[a], point[b]
            dot = p[0] * q[0] - p[1] * q[1] - p[2] * q[2] - p[3] * q[3]
            logs += 2 * value * math.log(float(mu2 / abs(2 * dot)))
        single = alphas / (2 * math.pi) * (-legs * gamma_g * born + logs)
        double = -alphas / (2 * math.pi) * legs * ca * born
        rows.append(
            {
                "index": i,
                "born": repr(born),
                "double_pole": repr(double),
                "single_pole": repr(single),
                "colour_conservation": conservation,
            }
        )
    result = {
        "tool": f"NJet {version} colour-correlated Born + Catani I operator",
        "nf": nf,
        "alphas": args.alphas,
        "prec": args.prec,
        "points_source": pts["source"],
        "points": pts["points"],
        "mu_r": pts["mu_r"],
        "rows": rows,
    }
    Path(args.output).write_text(json.dumps(result, indent=1) + "\n")
    print(
        args.output,
        "max colour-conservation residual",
        max(r["colour_conservation"] for r in rows),
    )


# ---------------------------------------------------------------- OpenLoops


def command_openloops(args):
    pts = json.loads(Path(args.points).read_text())
    legs = pts["legs"]
    root = Path(args.openloops).resolve()
    reference = provider_paths.reference_root()
    provider_paths.check([root], [reference] if reference else [root],
                         libraries=[root / "lib/libopenloops.so"], what="OpenLoops",
                         strict=reference is not None)
    work = Path(args.output).with_suffix("")
    work.mkdir(parents=True, exist_ok=True)
    binary = work / "openloops-driver"
    if not binary.exists():
        subprocess.run(
            [
                "g++",
                "-O2",
                "-std=c++17",
                str(HERE.parent / "openloops_driver.cpp"),
                f"-I{root / 'include'}",
                f"-L{root / 'lib'}",
                f"-Wl,-rpath,{root / 'lib'}",
                "-lopenloops",
                "-o",
                str(binary),
            ],
            check=True,
        )
    # Matched to the fixtures' OpenLoops settings (references.openloops_commands,
    # QCD scheme): only nf distinguishes the top-free configuration.
    commands = [
        "int truepoles 1",
        "int polenorm 0",
        "int ct_on 1",
        "int r2_on 1",
        "int iop_on 0",
        f"int nf {args.nf}",
        "int nq_nondecoupled 5",
        f"int coupling_qcd_0 {legs - 2}",
        "int coupling_qcd_1 1",
        "int coupling_ew_0 0",
        "int coupling_ew_1 0",
        f"double mass(6) {args.mt}",
        "double width(6) 0",
        "double mass(5) 0",
        "double width(5) 0",
        f"double alpha_s {args.alphas}",
        "register 11 21 21 -> " + " ".join(["21"] * (legs - 2)),
        f"points {len(pts['points'])}",
    ]
    for point, mu in zip(pts["points"], pts["mu_r"], strict=True):
        commands.append(f"{mu} " + " ".join(x for leg in point for x in leg))
    command = (["taskset", "-c", str(args.cpu)] if args.cpu is not None else []) + [
        str(binary)
    ]
    proc = subprocess.run(
        command,
        input="\n".join(commands) + "\n",
        capture_output=True,
        text=True,
        cwd=work,
        # process libraries from this tree, not from the compiled-in install path
        env={**os.environ, "OpenLoopsPath": str(root)},
    )
    (work / "output.log").write_text(proc.stdout + proc.stderr)
    rows = {}
    for line in proc.stdout.splitlines():
        if line.startswith("ROW"):
            _, index, seconds, born, finite, single, double, _ = line.split()
            rows[int(index) - 1] = {
                "index": int(index) - 1,
                "seconds": float(seconds),
                "born": born,
                "finite": finite,
                "single_pole": single,
                "double_pole": double,
            }
    if proc.returncode or len(rows) != len(pts["points"]):
        raise SystemExit(f"OpenLoops failed; see {work / 'output.log'}")
    result = {
        "tool": "OpenLoops 2.1.5",
        "openloops": str(root),
        "commands": commands[: -len(pts["points"])],
        "nf": args.nf,
        "legs": legs,
        "points_source": pts["source"],
        "points": pts["points"],
        "mu_r": pts["mu_r"],
        "rows": [rows[i] for i in range(len(rows))],
    }
    Path(args.output).write_text(json.dumps(result, indent=1) + "\n")
    print(args.output)


# ------------------------------------------------------------- N_c fixture


def command_nc_entry(args):
    """One process entry of an N_c-scan fixture (tests/fixtures/loop/nc/
    njet_nc_scan.json) from ``run`` results at several N_c: the points, the
    provider options and per N_c its rows (values at the N_c = 3 colour
    average; blha mode's raw values and average correction kept)."""

    results = {}
    for item in args.result:
        nc, _, path = item.partition("=")
        results[nc] = json.loads(Path(path).read_text())
    first = next(iter(results.values()))
    options = {
        k: v for k, v in first["options"].items() if k not in ("nc", "colour_average")
    }
    for nc, data in results.items():
        other = {
            k: v
            for k, v in data["options"].items()
            if k not in ("nc", "colour_average")
        }
        if (
            other != options
            or data["points"] != first["points"]
            or data["options"]["nc"] != nc
        ):
            raise SystemExit(f"result at N_c = {nc} differs in options or points")
    build = Path(first["njet_build"])
    entry = {
        "process": args.process,
        "born_orders": json.loads(args.born_orders),
        "points_source": f"{first['points_source']}; indices {first['indices']}",
        "points": first["points"],
        "mu_r": first["mu_r"],
        "provider": {
            "tool": first["tool"],
            "build": f"workspace/builds/{build.name}",
            "options": options,
            "driver_source_sha256": first["driver"]["source_sha256"],
            "host": first["host"],
            "cpu_model": first["cpu_model"],
        },
    }
    if options["mode"] == "blha":
        entry["colour_average"] = {
            nc: {
                k: data["options"]["colour_average"][k]
                for k in ("njet_average", "reference_average", "factor")
            }
            for nc, data in results.items()
        }
    keep = ("index", *COEFFICIENTS, "errors", "relative_accuracy", "njet")
    entry["nc"] = {
        nc: [{k: row[k] for k in keep if k in row} for row in data["rows"]]
        for nc, data in results.items()
    }
    fixture = json.loads(Path(args.fixture).read_text())
    fixture["processes"][args.name] = entry
    Path(args.fixture).write_text(json.dumps(fixture, indent=1) + "\n")
    print(args.fixture, args.name)


# ------------------------------------------------------------------ compare


def relative(a, b, floor=0.0):
    """The merge metric of references.py: |a-b| / max(|a|, |b|, floor)."""
    scale = max(abs(a), abs(b), floor)
    return abs(a - b) / scale if scale else 0.0


def load_rows(path, provider=None):
    data = json.loads(Path(path).read_text())
    if "rows" in data and data["rows"] and "providers" in data["rows"][0]:
        rows = data["rows"]
        if provider:
            rows = [r["providers"][provider] for r in rows]
        return data, [{k: float(r[k]) for k in COEFFICIENTS if k in r} for r in rows]
    return data, [
        {k: float(r[k]) for k in COEFFICIENTS if k in r} for r in data["rows"]
    ]


def compare_rows(a, b, alphas):
    out = []
    # Compared over the common leading points (a fixture may hold fewer).
    for i, (x, y) in enumerate(zip(a, b, strict=False)):
        floor = abs(y["born"]) * alphas / (2 * math.pi)
        out.append(
            {
                "index": i,
                **{
                    k: relative(x[k], y[k], 0.0 if k == "born" else floor)
                    for k in COEFFICIENTS
                    if k in x and k in y
                },
            }
        )
    return out


def command_compare(args):
    _, a = load_rows(args.a, args.a_provider)
    _, b = load_rows(args.b, args.b_provider)
    table = compare_rows(a, b, float(args.alphas))
    for row in table:
        print(json.dumps(row))
    worst = max(max(r[k] for k in COEFFICIENTS if k in r) for r in table)
    print(json.dumps({"max_relative": worst}))


def command_add_top(args):
    """NJet (massless, N_f=5) + T, T = OpenLoops(nf=6) - OpenLoops(nf=5) per point.

    T is the closed top-quark loop contribution with the top decoupled from
    alpha_s (the fixtures' loop_sm scheme); the sum is comparable with the
    fixtures' MadLoop/Recola/OpenLoops values.
    """
    nj = json.loads(Path(args.njet).read_text())
    six = json.loads(Path(args.nf6).read_text())
    five = json.loads(Path(args.nf5).read_text())
    if not (
        nj["points"]
        == six["points"][: len(nj["points"])]
        == five["points"][: len(nj["points"])]
    ):
        raise SystemExit("different points")
    rows = []
    for row in nj["rows"]:
        i = row["index"]
        top = {
            k: float(six["rows"][i][k]) - float(five["rows"][i][k])
            for k in COEFFICIENTS
        }
        rows.append(
            {
                "index": i,
                **{k: repr(float(row[k]) + top[k]) for k in COEFFICIENTS},
                "top": top,
            }
        )
    out = {
        "tool": f"{nj['tool']} + T(OpenLoops nf=6 - nf=5)",
        "njet": str(Path(args.njet).resolve()),
        "nf6": str(Path(args.nf6).resolve()),
        "nf5": str(Path(args.nf5).resolve()),
        "points": nj["points"],
        "mu_r": nj["mu_r"],
        "rows": rows,
    }
    Path(args.output).write_text(json.dumps(out, indent=1) + "\n")
    print(args.output)


def command_calibration(args):
    """Summarise comparisons: entries "label|a.json|b.json[|b_provider]"."""
    summary = {}
    for spec in args.entry:
        label, a_path, b_path, *rest = spec.split("|")
        provider = rest[0] if rest and rest[0] else None
        a_data, a = load_rows(a_path)
        b_data, b = load_rows(b_path, provider)
        n = min(len(a), len(b))
        if a_data.get("points", [])[:n] != b_data.get("points", [])[:n]:
            raise SystemExit(f"{label}: different points")
        table = compare_rows(a[:n], b[:n], float(args.alphas))
        entry = {
            "a": str(Path(a_path).resolve()),
            "b": str(Path(b_path).resolve()),
            "a_tool": a_data.get("tool"),
            "b_tool": b_data.get("tool", provider),
            "b_provider": provider,
            "points": n,
            "max_relative_deviation": {
                k: max(r[k] for r in table) for k in COEFFICIENTS if k in table[0]
            },
        }
        if a_data.get("rows") and "errors" in a_data["rows"][0]:
            estimates = []
            for row in a_data["rows"][:n]:
                floor = abs(float(row["born"])) * float(args.alphas) / (2 * math.pi)
                estimates.append(
                    max(
                        abs(float(e)) / max(abs(float(row[k])), floor)
                        for e, k in zip(
                            row["errors"],
                            ("double_pole", "single_pole", "finite"),
                            strict=True,
                        )
                    )
                )
            entry["max_njet_estimated_relative_accuracy"] = max(estimates)
            entry["per_point"] = [
                {**r, "njet_estimate": e} for r, e in zip(table, estimates, strict=True)
            ]
        else:
            entry["per_point"] = table
        summary[label] = entry
        print(
            label,
            json.dumps(entry["max_relative_deviation"]),
            entry.get("max_njet_estimated_relative_accuracy"),
        )
    Path(args.output).write_text(json.dumps(summary, indent=1) + "\n")


# ------------------------------------------------------------------- timing


def command_timing(args):
    """Markdown table of per-point seconds of ``run`` results (one pinned CPU each)."""
    import statistics

    rows = []
    for path in args.results:
        data = json.loads(Path(path).read_text())
        seconds = [r["seconds"] for r in data["rows"]]
        o = data["options"]
        rows.append(
            (
                data["legs"],
                data["tool"],
                o.get("amp"),
                o.get("scaling"),
                o.get("prec"),
                len(seconds),
                statistics.mean(seconds),
                statistics.median(seconds),
                min(seconds),
                max(seconds),
                data.get("initialisation_seconds"),
                data.get("cpu"),
            )
        )
    print(
        "| channel | NJet | sum | scaling test | precision | points | mean s/pt | median | "
        "min | max | init s | cpu |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(rows):
        legs, tool, amp, sc, prec, n, mean, med, lo, hi, init, cpu = r
        test = {"1": "yes (2 evaluations)", "0": "no (1 evaluation)"}.get(sc, sc)
        init_text = f"{init:.4g}" if init is not None else "-"
        print(
            f"| gg->{legs - 2}g | {tool.split()[-1]} | {amp} | {test} | {prec} | {n} | "
            f"{mean:.4g} | {med:.4g} | {lo:.4g} | {hi:.4g} | {init_text} | {cpu} |"
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("points")
    p.add_argument("--legs", type=int)
    p.add_argument("--count", type=int, default=3)
    p.add_argument("--cut", default="1/1000")
    p.add_argument(
        "--rotated", type=int, default=0, help="append rotated copies of the first K"
    )
    p.add_argument("--mu-r", nargs="+", default=["1000"])
    p.add_argument("--fixture")
    p.add_argument("--output", required=True)
    r = sub.add_parser("run")
    r.add_argument("--njet-build", required=True, help="build dir of build_njet.sh")
    r.add_argument(
        "--driver-dir", required=True, help="where compiled drivers are cached"
    )
    r.add_argument("--points", required=True)
    r.add_argument("--mode", choices=("direct", "blha"), default="direct")
    r.add_argument("--amp", choices=("standard", "ds"), default="standard")
    r.add_argument("--prec", choices=("double", "dd"), default="double")
    r.add_argument("--scaling", choices=("0", "1"), default="1")
    r.add_argument("--scheme", choices=("cdr", "fdh", "none"), default="cdr")
    r.add_argument("--renorm", choices=("0", "1"), default="1")
    r.add_argument("--nf", default="5")
    r.add_argument(
        "--nc",
        default="3",
        help="NJet's N_c (NJetNc; MQ-NC's N_c-scan oracle); direct mode's "
        "normalisation keeps the N_c = 3 colour average, blha mode's values are "
        "corrected to it (avg(N_c)/avg(3))",
    )
    r.add_argument(
        "--process",
        help="blha: the BLHA process line, e.g. '2 -2 -> 21 21 21' in the points' "
        "leg order (default: the all-gluon channel)",
    )
    r.add_argument("--alphas", default="0.118")
    r.add_argument("--multiprec", default="0", help="blha: NJetMultiPrec")
    r.add_argument("--precision", default="1e-5", help="blha: rescue threshold")
    r.add_argument("--indices", type=int, nargs="+", help="evaluate only these points")
    r.add_argument(
        "--rotation",
        choices=sorted(ROTATIONS),
        help="evaluate NJet at the exactly rotated points (values are invariant)",
    )
    r.add_argument("--cpu", type=int)
    r.add_argument("--output", required=True)
    o = sub.add_parser("openloops")
    o.add_argument("--openloops", required=True)
    o.add_argument("--points", required=True)
    o.add_argument("--nf", choices=("0", "5", "6"), required=True)
    o.add_argument("--mt", default="173")
    o.add_argument("--alphas", default="0.118")
    o.add_argument("--cpu", type=int)
    o.add_argument("--output", required=True)
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    c.add_argument("--a-provider")
    c.add_argument("--b-provider")
    c.add_argument("--alphas", default="0.118")
    ca = sub.add_parser("catani")
    ca.add_argument("--njet-build", required=True)
    ca.add_argument("--driver-dir", required=True)
    ca.add_argument("--points", required=True)
    ca.add_argument("--nf", default="5")
    ca.add_argument("--alphas", default="0.118")
    ca.add_argument("--prec", choices=("double", "dd"), default="double")
    ca.add_argument("--output", required=True)
    a = sub.add_parser("add-top")
    a.add_argument("--njet", required=True)
    a.add_argument("--nf6", required=True)
    a.add_argument("--nf5", required=True)
    a.add_argument("--output", required=True)
    k = sub.add_parser("calibration")
    k.add_argument("--entry", action="append", required=True)
    k.add_argument("--alphas", default="0.118")
    k.add_argument("--output", required=True)
    e = sub.add_parser("nc-entry")
    e.add_argument("--fixture", required=True, help="N_c-scan fixture to update")
    e.add_argument("--name", required=True, help="process key in the fixture")
    e.add_argument(
        "--process", required=True, help="pyAmpliCol process, e.g. 'u u~ > g g g'"
    )
    e.add_argument(
        "--born-orders", required=True, help='JSON, e.g. {"QCD": 3, "QED": 0}'
    )
    e.add_argument("--result", action="append", required=True, help="N=run result JSON")
    t = sub.add_parser("timing")
    t.add_argument("results", nargs="+")
    args = parser.parse_args()
    {
        "points": command_points,
        "run": command_run,
        "openloops": command_openloops,
        "compare": command_compare,
        "calibration": command_calibration,
        "add-top": command_add_top,
        "catani": command_catani,
        "timing": command_timing,
        "nc-entry": command_nc_entry,
    }[args.command](args)


if __name__ == "__main__":
    main()
