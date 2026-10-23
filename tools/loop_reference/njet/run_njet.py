#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""NJet references for the all-gluon ladder g g -> (n-2) g, n = 4..7.

Subcommands
-----------
``points``     exact points JSON: ``exact_points.generate`` for n massless legs
               (pyAmpliCol's generator and order) or the points of a
               ``tests/fixtures/loop/required`` fixture.
``run``        evaluate NJet (``njet_driver.cpp``) at a points JSON, one pinned
               CPU, and write a result JSON with provenance.
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
from fractions import Fraction
import hashlib
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
sys.path.insert(0, str(HERE.parent))
from exact_points import _matmul, _rotate, _rotation, check, decimal_string, generate  # noqa: E402

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
        rotation = _matmul(_rotation(2, (Fraction(3, 5), Fraction(4, 5))),
                           _rotation(0, (Fraction(7, 25), Fraction(24, 25))))
        for point in found[:args.rotated]:
            copy = [_rotate(rotation, p) for p in point]
            check(copy, [0] * args.legs)
            found.append(copy)
        points = [[[decimal_string(x) for x in leg] for leg in point] for point in found]
        mu_r = [args.mu_r[i % len(args.mu_r)] for i in range(len(points))]
        source = (f"tools/loop_reference/exact_points.generate([0]*{args.legs}, count={args.count}, "
                  f"cut={args.cut}) (the generator and order of pyAmpliCol's loop_v2_generate/campaign)")
        if args.rotated:
            source += (f"; points {args.count}..{args.count + args.rotated - 1} are points "
                       f"0..{args.rotated - 1} rotated by Rz(3/5,4/5) Rx(7/25,24/25)")
    report = {"legs": len(points[0]), "source": source, "points": points, "mu_r": mu_r}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=1) + "\n")
    print(args.output)


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


def build_driver(build, out_dir):
    """Compile njet_driver.cpp against an NJet build (cached by source digest)."""
    prefix, pc, version = njet_install(build)
    digest = sha256(HERE / "njet_driver.cpp")[:12]
    binary = Path(out_dir) / f"njet_driver-{version}-{digest}"
    if binary.exists():
        return binary, version
    qd = Path(build) / "qd" / "prefix" / "lib"
    if pc is not None:
        env = dict(os.environ)
        paths = [str(pc.parent)]
        if (qd / "pkgconfig").is_dir():
            paths.insert(0, str(qd / "pkgconfig"))
        env["PKG_CONFIG_PATH"] = ":".join(paths)
        env["PATH"] = PKG_CONFIG + ":" + env["PATH"]
        flags = subprocess.run(["pkg-config", "--cflags", "--libs", pc.stem], env=env,
                               check=True, capture_output=True, text=True).stdout.split()
    else:
        # NJet 2: the internal headers of its own (unmodified) source tree,
        # the build's config.h, the bundled QD installed with it.
        flags = ["-DUSE_DD", f"-I{njet_source(build)}", f"-I{Path(build) / 'njet' / 'build'}",
                 f"-I{prefix / 'include'}", f"-L{prefix / 'lib'}", "-lnjet2", "-lqd",
                 "-lqcdloop1"]
    rpaths = [f"-Wl,-rpath,{prefix / 'lib'}"] + ([f"-Wl,-rpath,{qd}"] if qd.is_dir() else [])
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    command = ["g++", "-std=c++17", "-O2", str(HERE / "njet_driver.cpp"), "-o", str(binary),
               *flags, *rpaths]
    subprocess.run(command, check=True)
    (binary.parent / (binary.name + ".command")).write_text(" ".join(command) + "\n")
    return binary, version


def sign_contract(build, run_dir, legs, amp, options):
    """Order file -> contract signed by the build's own njet.py."""
    prefix, _, _ = njet_install(build)
    amplitude = {"standard": "loop", "ds": "loopds"}[amp]
    lines = ["CorrectionType QCD", "IRregularisation CDR", f"AlphasPower {legs - 2}",
             f"AmplitudeType {amplitude}", "Extra NJetReturnAccuracy 2",
             f"Extra NJetMultiPrec {options['multiprec']}", f"Extra Precision {options['precision']}",
             f"Extra NJetNf {options['nf']}",
             "21 21 -> " + " ".join(["21"] * (legs - 2))]
    order = run_dir / "OLE_order.lh"
    order.write_text("\n".join(lines) + "\n")
    contract = run_dir / "OLE_contract.lh"
    subprocess.run([sys.executable, "-I", str(prefix / "bin" / "njet.py"), str(order), "-o",
                    str(contract)], check=True, capture_output=True, text=True)
    text = contract.read_text()
    if "Error" in text or "| 1 1 #" not in text:
        raise SystemExit(f"njet.py did not accept the order file:\n{text}")
    return contract


def command_run(args):
    pts = json.loads(Path(args.points).read_text())
    indices = list(range(len(pts["points"]))) if args.indices is None else args.indices
    pts["points"] = [pts["points"][i] for i in indices]
    pts["mu_r"] = [pts["mu_r"][i] for i in indices]
    run_dir = Path(args.output).with_suffix("")
    run_dir.mkdir(parents=True, exist_ok=True)
    binary, version = build_driver(args.njet_build, Path(args.driver_dir))
    (run_dir / "points.txt").write_text(points_text(pts["points"], pts["mu_r"]))
    legs = pts["legs"]
    options = {"mode": args.mode, "amp": args.amp, "prec": args.prec, "scaling": args.scaling,
               "alphas": args.alphas, "nf": args.nf, "nc": "3", "scheme": args.scheme,
               "renorm": args.renorm}
    command = [str(binary), args.mode, f"points={run_dir / 'points.txt'}", f"alphas={args.alphas}"]
    if args.mode == "blha":
        options.update(multiprec=args.multiprec, precision=args.precision)
        for key in ("prec", "scaling", "scheme", "renorm"):
            options.pop(key)
        if args.scheme != "cdr" or args.renorm != "1":
            raise SystemExit("blha mode uses the contract's CDR and renormalisation")
        command.append(f"contract={sign_contract(args.njet_build, run_dir, legs, args.amp, options)}")
    else:
        command += [f"legs={legs}", f"amp={args.amp}", f"prec={args.prec}",
                    f"scaling={args.scaling}", f"nf={args.nf}", "nc=3", f"scheme={args.scheme}",
                    f"renorm={args.renorm}"]
    if args.cpu is not None:
        command = ["taskset", "-c", str(args.cpu)] + command
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
                rows.append(row)
                print(json.dumps({k: row[k] for k in ("index", "seconds", "finite")}), flush=True)
        code = proc.wait()
    if code:
        raise SystemExit(f"njet_driver failed ({code}); see {run_dir / 'driver.log'}")
    build_info = Path(args.njet_build) / "build-info.txt"
    result = {
        "tool": f"NJet {version}",
        "njet_build": str(Path(args.njet_build).resolve()),
        "build_info": build_info.read_text() if build_info.exists() else None,
        "driver": {"binary": str(binary), "source_sha256": sha256(HERE / "njet_driver.cpp"),
                   "compile": (binary.parent / (binary.name + ".command")).read_text().strip()},
        "options": options,
        "command": command,
        "host": platform.node(), "cpu_model": cpu_model(), "cpu": args.cpu,
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "wall_seconds": round(time.time() - started, 3),
        "legs": legs, "points_source": pts["source"], "points_file": str(Path(args.points).resolve()),
        "indices": indices, "points": pts["points"], "mu_r": pts["mu_r"],
        "initialisation_seconds": init,
        "rows": rows,
    }
    Path(args.output).write_text(json.dumps(result, indent=1) + "\n")
    print(args.output)


# ---------------------------------------------------------------- OpenLoops

def command_openloops(args):
    pts = json.loads(Path(args.points).read_text())
    legs = pts["legs"]
    root = Path(args.openloops).resolve()
    work = Path(args.output).with_suffix("")
    work.mkdir(parents=True, exist_ok=True)
    binary = work / "openloops-driver"
    if not binary.exists():
        subprocess.run(["g++", "-O2", "-std=c++17", str(HERE.parent / "openloops_driver.cpp"),
                        f"-I{root / 'include'}", f"-L{root / 'lib'}", f"-Wl,-rpath,{root / 'lib'}",
                        "-lopenloops", "-o", str(binary)], check=True)
    # Matched to the fixtures' OpenLoops settings (references.openloops_commands,
    # QCD scheme): only nf distinguishes the top-free configuration.
    commands = ["int truepoles 1", "int polenorm 0", "int ct_on 1", "int r2_on 1", "int iop_on 0",
                f"int nf {args.nf}", "int nq_nondecoupled 5",
                f"int coupling_qcd_0 {legs - 2}", "int coupling_qcd_1 1",
                "int coupling_ew_0 0", "int coupling_ew_1 0",
                f"double mass(6) {args.mt}", "double width(6) 0", "double mass(5) 0",
                "double width(5) 0", f"double alpha_s {args.alphas}",
                "register 11 21 21 -> " + " ".join(["21"] * (legs - 2)),
                f"points {len(pts['points'])}"]
    for point, mu in zip(pts["points"], pts["mu_r"], strict=True):
        commands.append(f"{mu} " + " ".join(x for leg in point for x in leg))
    command = (["taskset", "-c", str(args.cpu)] if args.cpu is not None else []) + [str(binary)]
    proc = subprocess.run(command, input="\n".join(commands) + "\n", capture_output=True,
                          text=True, cwd=work)
    (work / "output.log").write_text(proc.stdout + proc.stderr)
    rows = {}
    for line in proc.stdout.splitlines():
        if line.startswith("ROW"):
            _, index, seconds, born, finite, single, double, _ = line.split()
            rows[int(index) - 1] = {"index": int(index) - 1, "seconds": float(seconds),
                                    "born": born, "finite": finite, "single_pole": single,
                                    "double_pole": double}
    if proc.returncode or len(rows) != len(pts["points"]):
        raise SystemExit(f"OpenLoops failed; see {work / 'output.log'}")
    result = {"tool": "OpenLoops 2.1.5", "openloops": str(root), "commands": commands[:-len(pts['points'])],
              "nf": args.nf, "legs": legs, "points_source": pts["source"],
              "points": pts["points"], "mu_r": pts["mu_r"],
              "rows": [rows[i] for i in range(len(rows))]}
    Path(args.output).write_text(json.dumps(result, indent=1) + "\n")
    print(args.output)


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
        return data, [{k: float(r[k]) for k in COEFFICIENTS} for r in rows]
    return data, [{k: float(r[k]) for k in COEFFICIENTS} for r in data["rows"]]


def compare_rows(a, b, alphas):
    out = []
    for i, (x, y) in enumerate(zip(a, b)):
        floor = abs(y["born"]) * alphas / (2 * math.pi)
        out.append({"index": i, **{k: relative(x[k], y[k], 0.0 if k == "born" else floor)
                                   for k in COEFFICIENTS}})
    return out


def command_compare(args):
    _, a = load_rows(args.a, args.a_provider)
    _, b = load_rows(args.b, args.b_provider)
    table = compare_rows(a, b, float(args.alphas))
    for row in table:
        print(json.dumps(row))
    worst = max(max(r[k] for k in COEFFICIENTS) for r in table)
    print(json.dumps({"max_relative": worst}))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("points")
    p.add_argument("--legs", type=int)
    p.add_argument("--count", type=int, default=3)
    p.add_argument("--cut", default="1/1000")
    p.add_argument("--rotated", type=int, default=0, help="append rotated copies of the first K")
    p.add_argument("--mu-r", nargs="+", default=["1000"])
    p.add_argument("--fixture")
    p.add_argument("--output", required=True)
    r = sub.add_parser("run")
    r.add_argument("--njet-build", required=True, help="build dir of build_njet.sh")
    r.add_argument("--driver-dir", required=True, help="where compiled drivers are cached")
    r.add_argument("--points", required=True)
    r.add_argument("--mode", choices=("direct", "blha"), default="direct")
    r.add_argument("--amp", choices=("standard", "ds"), default="standard")
    r.add_argument("--prec", choices=("double", "dd"), default="double")
    r.add_argument("--scaling", choices=("0", "1"), default="1")
    r.add_argument("--scheme", choices=("cdr", "fdh", "none"), default="cdr")
    r.add_argument("--renorm", choices=("0", "1"), default="1")
    r.add_argument("--nf", default="5")
    r.add_argument("--alphas", default="0.118")
    r.add_argument("--multiprec", default="0", help="blha: NJetMultiPrec")
    r.add_argument("--precision", default="1e-5", help="blha: rescue threshold")
    r.add_argument("--indices", type=int, nargs="+", help="evaluate only these points")
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
    args = parser.parse_args()
    {"points": command_points, "run": command_run, "openloops": command_openloops,
     "compare": command_compare}[args.command](args)


if __name__ == "__main__":
    main()
