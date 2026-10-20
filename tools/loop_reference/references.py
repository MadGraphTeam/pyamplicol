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
         *map(str, madloop_libraries(export)), "-lstdc++", "-o", str(binary)],
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
        param.value = float(Decimal(text))
    card.write(str(run_dir / "Cards/param_card.dat"))
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


def status_update(work, provider, state):
    """One status file per provider, so concurrent provider runs never race."""
    path = work / f"status-{provider}.json"
    path.write_text(json.dumps({"provider": provider, "state": state, "pid": os.getpid(),
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
    run_dir = work / f"{provider}-run"
    run_dir.mkdir(exist_ok=True)
    legs = len(spec["pdgs"])
    count = len(points["points"])
    status_update(work, provider, "running")
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
                if state not in ("generating", "exporting", "compiling"):
                    raise RuntimeError(f"MadLoop export state {state!r}; not waiting")
                pid = json.loads(generation.read_text()).get("pid")
                if pid is not None and not Path(f"/proc/{pid}").exists():
                    raise RuntimeError(f"MadLoop export process {pid} ended in state {state!r}")
                status_update(work, provider, f"waiting for MadLoop export ({state})")
                time.sleep(300)
            binary = build_madloop(export, run_dir)
            result["settings"] = prepare_madloop_run(spec, export, run_dir, args.mg5, legs)
            result["generation"] = json.loads(generation.read_text()) if generation.exists() else None
            result["version"] = "MadLoop/MG5_aMC " + re.search(
                r"version = (\S+)", (args.mg5 / "VERSION").read_text()).group(1)
            result["settings"]["requested_relative_accuracy"] = args.madloop_accuracy
            result["settings"]["stability_check"] = "forced on every timed call"
            orders = spec["born_orders"], spec["loop_orders"]
            header = (f"{2 * orders[0]['QCD']} {2 * orders[0]['QED']} "
                      f"{orders[0]['QCD'] + orders[1]['QCD']} {orders[0]['QED'] + orders[1]['QED']} "
                      f"{value(spec['scheme_data'], 'aS')} {args.madloop_accuracy} 64\n{count}\n")
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
            result["version"] = "OpenLoops 2.1.5"
            result["library"] = {"name": library, **openloops_library_version(root, library)}
            stdin = "\n".join(commands + [f"points {count}", *point_lines(points)]) + "\n"
            stdout, wall = run_native([str(binary)], stdin, run_dir, run_dir / "output.log", args.cpu)
        rows, extra = parse_rows(stdout, provider, count)
        if provider == "recola":
            banner = re.search(r"Version (\S+)", stdout)
            result["version"] = (f"Recola2 (supplied 2.3.0 tree, self-reported {banner.group(1) if banner else '?'})"
                                 " / SM model 2.2.3 / Collier 1.2.8")
        result.update(extra)
        result["rows"] = rows
        result["process_wall_seconds"] = wall
    except Exception as error:
        status_update(work, provider, f"failed: {error}")
        raise
    out = work / f"{provider}-result.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    status_update(work, provider, "done")
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
    for index in range(len(points["points"])):
        row = {key: results[primary]["rows"][index][key] for key in COEFFICIENTS}
        row["providers"] = {}
        row["provider_relative_errors"] = {}
        for provider, result in results.items():
            values = result["rows"][index]
            row["providers"][provider] = {k: v for k, v in values.items() if k != "total_all_orders"}
            unit = abs(values["born"]) * coupling / (2 * math.pi)
            pole_error = relative(values["double_pole"], pole_factor * values["born"], unit)
            row["providers"][provider]["universal_double_pole_relative_error"] = pole_error
            if provider not in excluded:
                pole_errors.append(pole_error)
            if provider != primary:
                unit = abs(row["born"]) * coupling / (2 * math.pi)
                rel = {key: relative(values[key], row[key], 0.0 if key == "born" else unit)
                       for key in COEFFICIENTS}
                strict = {key: relative(values[key], row[key]) for key in COEFFICIENTS}
                row["provider_relative_errors"][provider] = rel
                row.setdefault("provider_strict_relative_errors", {})[provider] = strict
                if provider not in excluded:
                    errors.extend(rel.values())
        rows.append(row)
    max_error = max(errors) if errors else None
    passed = (len(validated) >= 2 and max_error < args.tolerance and max(pole_errors) < args.tolerance)
    normalization = required_spec.normalization(spec)
    providers = {}
    for provider, result in results.items():
        providers[provider] = {k: v for k, v in result.items() if k not in ("rows",)}
        providers[provider]["evaluation_seconds"] = [r["seconds"] for r in result["rows"]]
    report = {
        "process": spec["madloop"]["process"] if "madloop" in spec else spec["name"],
        "name": spec["name"],
        "pdgs": spec["pdgs"],
        "correction": spec["correction"],
        "born_orders": spec["born_orders"],
        "loop_orders": spec["loop_orders"],
        "scheme": spec["scheme"],
        "scheme_description": scheme["description"],
        "source": "MG5_aMC_v3_7_0 / Recola2 2.3.0 / OpenLoops 2.1.5 independent references",
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
    """Markdown table of merged references (generation and per-point times)."""
    print("| process | providers | max rel. diff | status | generation [s] | s/point (mean) |")
    print("|---|---|---|---|---|---|")
    for path in args.references:
        d = json.loads(Path(path).read_text())
        gen, per = [], []
        for provider, result in d["providers"].items():
            g = generation_seconds(provider, result)
            gen.append(f"{provider} {g:.4g}" if g is not None else f"{provider} -")
            t = result["evaluation_seconds"]
            per.append(f"{provider} {sum(t) / len(t):.3g}")
        err = d["maximum_provider_relative_error"]
        print(f"| {d['name']} | {', '.join(d['providers'])} | {err if err is None else f'{err:.2g}'} | "
              f"{d['validation_status']} | {'; '.join(gen)} | {'; '.join(per)} |")


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
    run.add_argument("--madloop-accuracy", type=float, default=1e-11)
    run.add_argument("--wait-for-export", action="store_true",
                     help="poll the export's generation.json until it is compiled")
    run.add_argument("--recola", type=Path, help="Recola2 source/build tree with librecola.so")
    run.add_argument("--recola-uncached", action="store_true")
    run.add_argument("--openloops", type=Path, help="OpenLoops installation")
    run.add_argument("--cpu", type=int)
    merge = sub.choices["merge"]
    merge.add_argument("--output", type=Path, required=True)
    merge.add_argument("--tolerance", type=float, default=2e-8)
    merge.add_argument("--exclude", action="append", default=[], metavar="PROVIDER=REASON",
                       help="keep a provider's values but leave it out of the agreement check")
    summary = sub.add_parser("summary")
    summary.add_argument("references", nargs="+", type=Path)
    args = parser.parse_args()
    if args.command == "summary":
        command_summary(args)
        return
    if args.command == "run":
        if args.mg5:
            args.mg5 = args.mg5.resolve()
        command_run(args)
    else:
        command_merge(args)


if __name__ == "__main__":
    main()
