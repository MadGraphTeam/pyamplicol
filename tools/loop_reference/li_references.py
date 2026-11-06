#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Loop-induced (Born-less) provider references: MadLoop, Recola, OpenLoops, analytic.

The loop-induced counterpart of ``references.py`` (M-LIT package LIT-REF, PLAN
§3.2): the observable is |A_loop|^2 of a process without a Born amplitude
(``"loop_induced": true`` in ``required_processes.json``, ``required_spec``).

Subcommands
-----------
``points``  the process's points (its ``points`` record: ``exact_points.py``,
            ``supplied_points.py --family ...`` or ``decay_points.py``).
``export``  the MadLoop standalone loop-squared export (``madloop_export.py``,
            ``[sqrvirt=...]``), under ``timeout`` (45-minute rule).
``run``     one provider at the points: ``madloop`` (driver
            ``madloop_li_driver.f90``: no Born index, per-helicity rows,
            warm-up past MadLoop's loop-induced initialisation),
            ``recola`` (the toolkit driver's ``loop_induced`` mode),
            ``openloops`` (``ol_evaluate_loop2``, amptype 12) or
            ``analytic`` (``li_analytic.py``).
``merge``   all results of a work directory into one reference (all-pairs
            comparisons, MadLoop's QP-checked value as the reference value),
            written with the cards (MadLoop param card and MadLoopParams
            settings, Recola and OpenLoops command streams).

MadLoop runs. The REFERENCE run (no ``--tag``) requests relative accuracy
``1e-11`` with the stability test forced on every call (quadruple-precision
rescue through CutTools/Ninja), the numerical helicity filter OFF
(``HelicityFilterLevel = 0``: MadLoop's filter can map or drop helicities that
agree only at symmetric points) and every helicity configuration
(``SLOOPMATRIXHEL_THRES``). A TIMING run (``--tag production``) keeps the
export's own MadLoopParams.dat (MG5's loop-induced card: ``MLReductionLib
7|6|1``, COLLIER UV/IR poles off, helicity filter level 2) and MadLoop's own
``MLStabThres``; ``--madloop-param MLReductionLib=6|7|1`` gives the OPP column.
Single-helicity values are converted from MadLoop's USERHEL convention (colour
average and identical-particle factor, no helicity average) to
``|A(h)|^2/avg`` of the summed convention (PLAN Q39): divided by the export's
HELAVGFACTOR.

Values are physical (no couplings extracted), averaged over initial and summed
over final helicities and colours, with the final identical-particle factor.
A loop-induced |A|^2 is finite: the pole columns (MadLoop's incomplete
``2 Re(A^-1 A^0*)``, Recola's ``NLO-IR1/2``) are recorded as a check only.
"""

import argparse
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
import provider_paths  # noqa: E402
import references  # noqa: E402
import required_spec  # noqa: E402

PROVIDERS = ("madloop", "recola", "openloops", "analytic")
DEFAULT_TIMEOUT = 2700  # REQUIREMENTS_ADDENDUM F: 45 minutes per provider generation/run
REFERENCE_ACCURACY = 1e-11
L1_TOLERANCE = 1e-5  # PLAN §4.0 rule L1 (lax precision)


def load(args):
    roots = {"mg5": args.mg5, "reference": args.reference_root} if hasattr(args, "mg5") else None
    spec = required_spec.load_process(args.spec, args.process, roots)
    if not spec.get("loop_induced"):
        raise SystemExit(f"{args.process} is not loop-induced (use references.py)")
    return spec


# ----------------------------------------------------------------- points

def command_points(args):
    spec = load(args)
    record = spec["points"]
    tool = record["tool"]
    command = [sys.executable, "-I", str(HERE / tool), "--spec", str(args.spec), "--process", spec["name"],
               "--output", str(args.output), "--count", str(args.count)]
    if tool == "supplied_points.py":
        command += ["--family", record.get("family", "regular")]
        if record.get("sqrt_s"):
            command += ["--sqrt-s", *record["sqrt_s"][:args.count]]
    elif tool == "exact_points.py":
        if record.get("scale_window"):
            command += ["--scale-window", *record["scale_window"]]
    elif tool != "decay_points.py":
        raise SystemExit(f"unknown point tool {tool}")
    subprocess.run(command, check=True)


# ----------------------------------------------------------------- export

def command_export(args):
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    log = output.parent / f"{output.name}.log"
    command = ["timeout", str(args.timeout), sys.executable, str(HERE / "madloop_export.py"), "--spec", str(args.spec),
               "--process", args.process, "--mg5", str(args.mg5), "--output", str(output),
               "--compile-jobs", str(args.compile_jobs)]
    if args.reference_root:
        command += ["--reference-root", str(args.reference_root)]
    start = time.perf_counter()
    with open(log, "w") as handle:
        # MG5 writes py.py and additional_command into the working directory.
        completed = subprocess.run(command, cwd=output.parent, stdout=handle, stderr=subprocess.STDOUT)
    status = {"process": args.process, "export": str(output), "returncode": completed.returncode,
              "wall_seconds": time.perf_counter() - start, "timeout_seconds": args.timeout}
    if completed.returncode == 124:
        status["miss"] = f"45-minute rule: the MadLoop export did not finish within {args.timeout} s"
    (output.parent / f"{output.name}.status.json").write_text(json.dumps(status, indent=2) + "\n")
    if completed.returncode:
        raise SystemExit(f"MadLoop export failed ({completed.returncode}); see {log}")


# ------------------------------------------------------------------ MadLoop

def helavg_factor(process_dir):
    text = (process_dir / "loop_matrix.f").read_text()
    factor = re.search(r"DATA HELAVGFACTOR/(\d+)/", text)
    iden = re.search(r"DATA IDEN/(\d+)/", text)
    if factor is None or iden is None:
        raise RuntimeError(f"no HELAVGFACTOR / IDEN in {process_dir}/loop_matrix.f")
    return int(factor.group(1)), int(iden.group(1))


def build_madloop(export, work, global_flag, quadruple=False):
    from build import madloop_libraries

    process_dir = references.madloop_process_dir(export)
    prefix = references.madloop_prefix(process_dir)
    source = (HERE / "madloop_li_driver.f90").read_text().replace("ML5_0_", prefix).replace(
        "HELCONFIGS_FILE", f"SubProcesses/MadLoop5_resources/{prefix}HelConfigs.dat")
    driver = work / "madloop_li_driver.f90"
    driver.write_text(source)
    binary = work / "madloop-li-driver"
    fixes, repairs = references.madloop_model_fix(export, work, global_flag)
    if quadruple:
        fixes.append(references.madloop_quadruple_stage(export, process_dir, work, global_flag))
    subprocess.run(["gfortran", "-O2", "-ffree-line-length-none", "-I", str(process_dir), str(driver),
                    *map(str, fixes), str(export / "lib/libMadLoop.a"), "-L" + str(export / "lib"), "-ldhelas",
                    "-lmodel", *map(str, madloop_libraries(export)), "-lstdc++", "-Wl,--no-relax", "-o", str(binary)],
                   check=True, cwd=work)
    return binary, repairs


def parse_madloop(stdout, count, helavg):
    rows = [None] * count
    extra = {"loop_squared_orders": {}, "helicities": {}}
    dims = None
    for line in stdout.splitlines():
        fields = line.split()
        if not fields:
            continue
        key = fields[0]
        if key == "SPLIT_ORDER_INDICES":
            extra["loop_index"], *dims = map(int, fields[1:4])
        elif key == "LOOP_SO":
            index, qcd, qed = map(int, fields[1:4])
            extra["loop_squared_orders"][index] = {"QCD": qcd, "QED": qed}
        elif key == "HEL_INDEX":
            extra["helicities"][int(fields[1])] = {"madloop_index": int(fields[2]),
                                                   "helicity": list(map(int, fields[3:]))}
        elif key == "INITIAL_CALL_SECONDS":
            extra["initial_call_seconds"], extra["initialization_calls"] = float(fields[1]), int(fields[2])
            extra["initialization_status"] = int(fields[3])
        elif key == "ROW":
            i = int(fields[1]) - 1
            values = list(map(float, fields[4:]))
            rows[i] = {"value": values[1], "single_pole": values[2], "double_pole": values[3],
                       "born_slot": values[0], "accuracy": values[4], "status": int(fields[2]),
                       "seconds": float(fields[3]), "total_all_orders": values[5:9]}
        elif key == "HEL_ROW":
            i, h, status = int(fields[1]) - 1, int(fields[2]), int(fields[3])
            values = list(map(float, fields[5:]))
            nanswer, nloop = dims
            answer = [values[4 * j:4 * j + 4] for j in range(nanswer + 1)]
            accuracy = values[4 * (nanswer + 1):4 * (nanswer + 1) + nloop + 1]
            loop = answer[extra["loop_index"]]
            rows[i].setdefault("per_helicity", []).append({
                **extra["helicities"][h], "status": status, "seconds": float(fields[4]),
                "madloop_userhel_value": loop[1], "value": loop[1] / helavg,
                "single_pole": loop[2] / helavg, "double_pole": loop[3] / helavg,
                "accuracy": accuracy[extra["loop_index"]]})
    if any(r is None for r in rows):
        raise RuntimeError("madloop: missing result rows")
    for index, row in enumerate(rows):
        numbers = [row["value"], row["single_pole"], row["double_pole"]] + [
            e["value"] for e in row.get("per_helicity", ())]
        if not all(math.isfinite(x) for x in numbers):
            raise RuntimeError(f"madloop: non-finite values at point {index + 1}")
        if row.get("per_helicity"):
            row["per_helicity_sum_over_avg_relative_deviation"] = (
                abs(sum(e["value"] for e in row["per_helicity"]) - row["value"]) / max(abs(row["value"]), 1e-300))
    extra["helicities"] = [extra["helicities"][h] for h in sorted(extra["helicities"])]
    extra["loop_squared_orders"] = [{"index": i, **o} for i, o in sorted(extra["loop_squared_orders"].items())]
    return rows, extra


def checkcycle(run_dir):
    text = (run_dir / "SubProcesses/MadLoop5_resources/MadLoopParams.dat").read_text()
    return int(re.search(r"#CheckCycle\s*\n\s*(\d+)", text).group(1))


def run_madloop(args, spec, points, run_dir, result):
    export = args.madloop_export.resolve()
    generation = export.parent / f"{export.name}.generation.json"
    production = args.madloop_accuracy <= 0
    flags = references.madloop_build_flags(export, args.mg5)
    if not flags["production_build"]:
        raise RuntimeError(f"export built with {flags['export_make_opts']}, not MG5's production flags")
    binary, repairs = build_madloop(export, run_dir, flags["export_make_opts"]["GLOBAL_FLAG"], args.madloop_quadruple)
    params = dict(item.split("=", 1) for item in args.madloop_param)
    if not production and not args.tag:
        params.setdefault("HelicityFilterLevel", "0")
    result["settings"] = references.prepare_madloop_run(spec, export, run_dir, args.mg5, len(spec["pdgs"]), params)
    exported = (export / "SubProcesses/MadLoop5_resources/MadLoopParams.dat").read_text()
    result["settings"]["exported_card"] = {
        key: (re.search(rf"#{key}\s*\n\s*(\S+)", exported) or [None, None])[1]
        for key in ("MLReductionLib", "COLLIERComputeUVpoles", "COLLIERComputeIRpoles", "HelicityFilterLevel",
                    "CheckCycle", "MLStabThres", "COLLIERGlobalCache", "CTModeRun", "ImprovePSPoint")}
    result["settings"]["export"] = str(export)
    result["settings"]["fortran_flags"] = flags
    result["settings"]["mg5_quadruple_precision_model_function_repairs"] = repairs
    result["settings"]["requested_relative_accuracy"] = "MadLoop MLStabThres (production)" if production else args.madloop_accuracy
    result["settings"]["stability_check"] = ("MadLoop default (CTModeRun = -1 after initialisation)" if production
                                             else "forced on every call")
    result["generation"] = json.loads(generation.read_text()) if generation.exists() else None
    mg5_version = re.search(r"version = (\S+)", (args.mg5 / "VERSION").read_text()).group(1)
    from build import madloop_libraries

    result["version"] = f"MadLoop/MG5_aMC {mg5_version}"
    result["provenance"] = {"MG5_aMC": {"path": str(args.mg5), "version": mg5_version},
                            "reducer_libraries": {lib.name: {"path": str(lib.resolve()),
                                                             "version": references.library_version(lib.resolve())}
                                                  for lib in madloop_libraries(export)}}
    process_dir = references.madloop_process_dir(export)
    helavg, iden = helavg_factor(process_dir)
    warmup = checkcycle(run_dir) + 1
    result["settings"]["warm_up"] = (f"untimed calls cycling through the points until MadLoop leaves its "
                                     f"initialisation phase, at least CheckCycle + 1 = {warmup}")
    result["settings"]["HELAVGFACTOR"], result["settings"]["IDEN"] = helavg, iden
    orders = spec["squared_orders"]
    count = len(points["points"])
    stdin = (f"{orders['QCD']} {orders['QED']} {references.value(spec['scheme_data'], 'aS')} "
             f"{args.madloop_accuracy} {0 if production else 1} {warmup}\n{count}\n"
             + "\n".join(references.point_lines(points)) + "\n")
    if args.helicities:
        tuples = references.madloop_helicities(export)
        stdin += f"{len(tuples)}\n" + "\n".join(" ".join(map(str, t)) for t in tuples) + "\n"
        result["per_helicity_normalization"] = (
            "value = |A(h)|^2/avg (the summed convention's divisor, PLAN Q39) = MadLoop's USERHEL value "
            "(SLOOPMATRIXHEL_THRES: colour average and identical factor, no helicity average) / HELAVGFACTOR; "
            "helicity labels in MadLoop's HelConfigs.dat convention")
    stdout, wall = references.run_native([str(binary)], stdin, run_dir, run_dir / "output.log", args.cpu)
    rows, extra = parse_madloop(stdout, count, helavg)
    return rows, extra, wall


# ------------------------------------------------------------------- Recola

def recola_commands(spec, points, uncached):
    loop = spec["loop_orders"]["QCD"]
    lines = references.recola_setup_commands(spec, points, uncached)
    lines += [f"legs {len(spec['pdgs'])}", "loop_induced", f"loop_gs {loop}", f"pow_nlo {loop}"]
    lines += [f"switchoff3 {' '.join(triple)}" for triple in spec["recola"].get("switchoff", ())]
    lines += [f"process {spec['recola']['process']}", "generate"]
    return lines


def run_recola(args, spec, points, run_dir, result):
    root = args.recola.resolve()
    binary = run_dir / "recola-driver"
    subprocess.run(["gfortran", "-O2", "-ffree-line-length-none", str(HERE / "recola_driver.f90"),
                    "-I", str(root / "include"), "-L", str(root), f"-Wl,-rpath,{root}", "-lrecola", "-o", str(binary)],
                   check=True, cwd=run_dir)
    uncached = len(spec["pdgs"]) >= references.UNCACHED_LEG_THRESHOLD
    commands = recola_commands(spec, points, uncached)
    count = len(points["points"])
    result["settings"] = {"recola_tree": str(root), "commands": commands, "collier_cache": "off" if uncached else "on",
                          "dynamic_settings": 1, "compute_ir_poles": 1}
    stdin = "\n".join(commands + [f"points {count}", *references.point_lines(points)]) + "\n"
    stdout, wall = references.run_native([str(binary)], stdin, run_dir, run_dir / "output.log", args.cpu)
    rows, extra = [None] * count, {}
    for line in stdout.splitlines():
        fields = line.split()
        if fields and fields[0] == "ROW":
            lo, nlo, ir1, ir2 = map(float, fields[3:7])
            rows[int(fields[1]) - 1] = {"value": nlo, "single_pole": ir1, "double_pole": ir2, "lo_slot": lo,
                                        "seconds": float(fields[2])}
        elif fields and fields[0] in ("GENERATION_SECONDS", "INITIAL_CALL_SECONDS"):
            extra[fields[0].lower()] = float(fields[1])
    if any(r is None for r in rows):
        raise RuntimeError("recola: missing result rows")
    banner = re.search(r"Version (\S+)", stdout)
    linked = references.linked_libraries(binary, r"recola|collier|modelfile")
    result["version"] = f"Recola2 {banner.group(1) if banner else '?'} (tree {root.name})"
    result["provenance"] = {"recola_tree": str(root), "linked": linked}
    return rows, extra, wall


# ---------------------------------------------------------------- OpenLoops

def openloops_commands(spec):
    return [*references.openloops_setup_commands(spec), f"register 12 {spec['openloops']['process']}"]


def run_openloops(args, spec, points, run_dir, result):
    root = args.openloops.resolve()
    binary = run_dir / "openloops-driver"
    subprocess.run(["g++", "-O2", "-std=c++17", str(HERE / "openloops_driver.cpp"), "-I", str(root / "include"),
                    "-L", str(root / "lib"), f"-Wl,-rpath,{root / 'lib'}", "-lopenloops", "-o", str(binary)],
                   check=True, cwd=run_dir)
    commands = openloops_commands(spec)
    library = spec["openloops"]["library"]
    result["settings"] = {"commands": commands, "OpenLoopsPath": str(root)}
    result["version"] = f"OpenLoops {references.openloops_release(root)}"
    result["library"] = {"name": library, **references.openloops_library_version(root, library)}
    count = len(points["points"])
    stdin = "\n".join(commands + [f"points {count}", *references.point_lines(points)]) + "\n"
    stdout, wall = references.run_native([str(binary)], stdin, run_dir, run_dir / "output.log", args.cpu,
                                         env={"OpenLoopsPath": str(root)})
    rows, extra = [None] * count, {}
    for line in stdout.splitlines():
        fields = line.split()
        if fields and fields[0] == "ROW":
            _, value, _, _, acc = map(float, fields[3:8])
            rows[int(fields[1]) - 1] = {"value": value, "accuracy": acc, "seconds": float(fields[2])}
        elif fields and fields[0] in ("START_SECONDS", "INITIAL_CALL_SECONDS"):
            extra[fields[0].lower()] = float(fields[1])
    if any(r is None for r in rows):
        raise RuntimeError("openloops: missing result rows")
    return rows, extra, wall


# ----------------------------------------------------------------- analytic

def run_analytic(args, spec, points, run_dir, result):
    import li_analytic

    start = time.perf_counter()
    values = {oracle: li_analytic.evaluate(oracle, spec["scheme_data"], points["points"], args.dps)
              for oracle in spec.get("analytic", ())}
    if not values:
        raise SystemExit(f"{spec['name']} has no analytic oracle")
    primary = spec["analytic"][0]
    rows = [{"value": float(values[primary][i]), "decimal": values[primary][i],
             **({"other_oracles": {o: values[o][i] for o in values if o != primary}} if len(values) > 1 else {})}
            for i in range(len(points["points"]))]
    result["settings"] = {"oracle": primary, "dps": args.dps}
    result["version"] = "li_analytic.py (mpmath)"
    return rows, {}, time.perf_counter() - start


# ---------------------------------------------------------------------- run

def command_run(args):
    spec = load(args)
    points = json.loads(args.points.read_text())
    if points["pdgs"] != spec["pdgs"]:
        raise SystemExit("points JSON belongs to another process")
    references.check_point_masses(spec, points)
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    label = f"{args.provider}-{args.tag}" if args.tag else args.provider
    run_dir = work / f"{label}-run"
    run_dir.mkdir(exist_ok=True)
    reference_root = provider_paths.reference_root(args.reference_root)
    if args.provider in ("madloop", "recola", "openloops") and reference_root is not None:
        tree = {"madloop": args.madloop_export, "recola": args.recola, "openloops": args.openloops}[args.provider]
        provider_paths.check([Path(os.path.abspath(tree))], [reference_root], what=f"{args.provider} reference",
                             strict=True)
    references.status_update(work, label, "running")
    result = {"provider": args.provider, "process_name": spec["name"], "loop_induced": True,
              "host": platform.node(), "cpu": args.cpu, "points_file": str(args.points.resolve()),
              "timing_scope": "single thread pinned; untimed warm-up (MadLoop: past its initialisation), then each "
                              "point timed once; not a benchmark campaign"}
    runner = {"madloop": run_madloop, "recola": run_recola, "openloops": run_openloops,
              "analytic": run_analytic}[args.provider]
    try:
        rows, extra, wall = runner(args, spec, points, run_dir, result)
    except Exception as error:
        references.status_update(work, label, f"failed: {error}")
        raise
    result.update(extra)
    result["rows"] = rows
    result["process_wall_seconds"] = wall
    out = work / f"{label}-result.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    references.status_update(work, label, "done")
    print(out)


# -------------------------------------------------------------------- merge

def relative(a, b):
    scale = max(abs(a), abs(b))
    return abs(a - b) / scale if scale else 0.0


def command_merge(args):
    spec = load(args)
    points = json.loads(args.points.read_text())
    references.check_point_masses(spec, points)
    work = args.work_dir.resolve()
    results = {p: json.loads((work / f"{p}-result.json").read_text())
               for p in PROVIDERS if (work / f"{p}-result.json").exists()}
    if not results:
        raise SystemExit("no provider results")
    primary = "madloop" if "madloop" in results else next(iter(results))
    rows, worst = [], 0.0
    names = list(results)
    for index in range(len(points["points"])):
        row = {"value": results[primary]["rows"][index]["value"], "value_source": primary, "providers": {},
               "provider_pair_relative_errors": {}}
        for provider, result in results.items():
            entry = {k: v for k, v in result["rows"][index].items() if k not in ("per_helicity", "total_all_orders")}
            if "single_pole" in entry and entry.get("value"):
                entry["pole_over_value"] = [abs(entry["single_pole"] / entry["value"]),
                                            abs(entry["double_pole"] / entry["value"])]
            row["providers"][provider] = entry
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                error = relative(results[a]["rows"][index]["value"], results[b]["rows"][index]["value"])
                row["provider_pair_relative_errors"][f"{a}-{b}"] = error
                worst = max(worst, error)
        if "per_helicity" in results.get("madloop", {"rows": [{}]})["rows"][index]:
            row["per_helicity"] = [{k: e[k] for k in ("helicity", "value", "accuracy", "status")}
                                   for e in results["madloop"]["rows"][index]["per_helicity"]]
        rows.append(row)
    secondary = {}
    for path in sorted(work.glob("*-*-result.json")):
        label = path.name[: -len("-result.json")]
        provider, _, tag = label.partition("-")
        if provider not in PROVIDERS:
            continue
        data = json.loads(path.read_text())
        deviation = [relative(r["value"], rows[i]["value"]) for i, r in enumerate(data["rows"])]
        secondary[label] = {"settings": data.get("settings"), "max_relative_deviation_from_reference": max(deviation),
                            "seconds": [r["seconds"] for r in data["rows"]],
                            "statuses": [r.get("status") for r in data["rows"]],
                            "initial_call_seconds": data.get("initial_call_seconds"),
                            "initialization_calls": data.get("initialization_calls")}
    providers = {}
    for provider, result in results.items():
        providers[provider] = {k: v for k, v in result.items() if k != "rows"}
        settings = providers[provider].get("settings") or {}
        if "param_card" in settings:
            # The card's values without MG5's comment lines.
            settings["param_card"] = "\n".join(
                line.split("#")[0].rstrip() for line in settings["param_card"].splitlines()
                if line.split("#")[0].strip())
        providers[provider]["evaluation_seconds"] = [r.get("seconds") for r in result["rows"]]
    misses = {}
    for status in sorted(work.glob("*.status.json")):
        data = json.loads(status.read_text())
        if data.get("miss"):
            misses[status.name[: -len(".status.json")]] = data["miss"]
    out = {
        "name": spec["name"], "li_row": spec.get("li_row"), "loop_induced": True, "pdgs": spec["pdgs"],
        "initial": spec.get("initial", 2), "madloop_process": spec["madloop"]["process"],
        "recola_process": spec["recola"].get("process"), "openloops": spec.get("openloops"),
        "loop_orders": spec["loop_orders"], "squared_orders": spec["squared_orders"], "correction": spec["correction"],
        "scheme": spec["scheme"], "scheme_data": spec["scheme_data"],
        "derived_parameters": references.derived_parameters(spec["scheme_data"])
        if spec["scheme_data"]["electroweak_inputs"] in ("alpha_fixed", "gmu") else None,
        "normalization": {**required_spec.normalization(spec),
                          "convention": "|A_loop|^2 summed over final and averaged over initial helicities and "
                                        "colours, with the final identical-particle factor; physical couplings"},
        "point_construction": {k: v for k, v in points.items() if k not in ("points", "mu_r", "pdgs")},
        "points": points["points"], "mu_r": points["mu_r"],
        "rows": rows,
        "max_provider_pair_relative_error": worst,
        "rule": f"PLAN §4.0 L1: provider agreement <= {L1_TOLERANCE:g} relative (lax); digits recorded",
        "passed": len(results) >= 2 and worst <= L1_TOLERANCE,
        "providers": providers,
        "secondary_runs": secondary,
        "unavailable": {p: spec.get(p, {}).get("unavailable") for p in ("openloops",) if spec.get(p, {}).get("unavailable")},
        "misses_45_min": misses,
    }
    if spec.get("note"):
        out["note"] = spec["note"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2) + "\n")
    print(args.output, "max pair error", f"{worst:.2e}", "passed" if out["passed"] else "NOT PASSED")


def command_fixture(args):
    """The merged reference with absolute paths rewritten to ${LOOP_REFERENCE_ROOT}
    and ${REPOSITORY} (mqcd_campaign's rule: no /shared, /home, /tmp left)."""
    root = str(provider_paths.reference_root(args.reference_root))
    repository = str(HERE.parents[1])
    text = args.reference.read_text().replace(root, "${LOOP_REFERENCE_ROOT}").replace(repository, "${REPOSITORY}")
    left = sorted(set(re.findall(r"(/(?:shared|home|tmp)/[^\"\s]*)", text)))
    store = [p for p in re.findall(r"(/nix/store/[^\"\s]*)", text) if not re.search(r"gcc|gfortran", p)]
    if left or store:
        raise SystemExit(f"absolute paths left in the fixture: {(left + store)[:5]}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text)
    print(args.output)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("points", "export", "run", "merge", "fixture"):
        p = sub.add_parser(name)
        p.add_argument("--spec", type=Path, default=required_spec.DEFAULT_SPEC)
        p.add_argument("--process", required=name != "fixture")
        p.add_argument("--reference-root", type=Path)
    pts = sub.choices["points"]
    pts.add_argument("--output", type=Path, required=True)
    pts.add_argument("--count", type=int, default=3)
    exp = sub.choices["export"]
    exp.add_argument("--mg5", type=Path, required=True)
    exp.add_argument("--output", type=Path, required=True)
    exp.add_argument("--compile-jobs", type=int, default=8)
    exp.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    run = sub.choices["run"]
    run.add_argument("--provider", choices=PROVIDERS, required=True)
    run.add_argument("--points", type=Path, required=True)
    run.add_argument("--work-dir", type=Path, required=True)
    run.add_argument("--mg5", type=Path)
    run.add_argument("--madloop-export", type=Path)
    run.add_argument("--madloop-accuracy", type=float, default=REFERENCE_ACCURACY)
    run.add_argument("--madloop-param", action="append", default=[], metavar="KEY=VALUE")
    run.add_argument("--madloop-quadruple", action="store_true")
    run.add_argument("--helicities", action="store_true", help="MadLoop: every helicity configuration too")
    run.add_argument("--tag", help="secondary run label, e.g. production")
    run.add_argument("--recola", type=Path)
    run.add_argument("--openloops", type=Path)
    run.add_argument("--cpu", type=int)
    run.add_argument("--dps", type=int, default=50)
    merge = sub.choices["merge"]
    merge.add_argument("--points", type=Path, required=True)
    merge.add_argument("--work-dir", type=Path, required=True)
    merge.add_argument("--output", type=Path, required=True)
    fixture = sub.choices["fixture"]
    fixture.add_argument("--reference", type=Path, required=True)
    fixture.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    {"points": command_points, "export": command_export, "run": command_run, "merge": command_merge,
     "fixture": command_fixture}[args.command](args)


if __name__ == "__main__":
    main()
