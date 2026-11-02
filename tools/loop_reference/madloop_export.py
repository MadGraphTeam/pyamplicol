#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Generate and compile one MadLoop standalone export from a process specification.

The specification (see ``required_processes.json``) names the MG5 model and
process string. The export uses optimized loop output with the installed
Ninja/Collier reducers and records split orders ``QCD, QED`` so the driver can
select the Born-virtual interference by squared coupling order. Graph counts,
the observed Born/loop amplitude orders, the compilation flags and the
generation, export and compilation wall times are written to
``generation.json`` next to the export, the UFO counterterm couplings behind
its calls to ``ct_couplings.json`` (``madloop_ct_couplings.py``).

The export is compiled with MG5_aMC's production flags (``production_make_opts``),
not with the unset ``GLOBAL_FLAG`` (gfortran ``-O0``) of a bare standalone output.
``--recompile`` rebuilds an existing export (e.g. a copy) the same way.

Run with the Python that runs MG5_aMC (it imports MG5 from ``--mg5``). The
script refuses to overwrite an existing export.
"""

import argparse
from collections import Counter
import json
import logging
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time


def _orders(diagram):
    return diagram["orders"].get("QCD", 0), diagram["orders"].get("QED", 0)


def _import_mg5(mg5):
    sys.dont_write_bytecode = True
    if str(mg5) not in sys.path:
        sys.path.insert(0, str(mg5))


def production_make_opts(mg5):
    """MG5_aMC's production Fortran flags: the run-card defaults (``global_flag``,
    ``aloha_flag``, ``matrix_flag``) that ``CommonRunCmd.update_make_opts`` writes
    into ``Source/make_opts`` when MG5 runs optimised, as ``bin/mg5_aMC`` always
    does unless ``--debug`` (MG5 3.7.0: ``GLOBAL_FLAG=-O``). A standalone output
    never sets them, so its default build is unoptimised."""
    _import_mg5(mg5)
    from madgraph.various.banner import RunCardLO

    card = RunCardLO()
    return {"GLOBAL_FLAG": card["global_flag"], "ALOHA_FLAG": card["aloha_flag"],
            "MATRIX_FLAG": card["matrix_flag"]}


def make_opts_variables(export):
    """Variable block of an export's ``Source/make_opts`` (what make compiles with)."""
    variables = {}
    for line in (Path(export) / "Source/make_opts").read_text().splitlines():
        if line.startswith("#end_of_make_opts_variables"):
            break
        match = re.match(r"^(\w+)\s*=\s*(.*)$", line.strip())
        if match:
            variables[match.group(1)] = match.group(2)
    return variables


def apply_production_flags(export, mg5):
    """Write the production flags into the export's ``Source/make_opts`` with
    MG5's own updater (idempotent); returns them."""
    flags = production_make_opts(mg5)
    from madgraph.interface.common_run_interface import CommonRunCmd

    CommonRunCmd.update_make_opts_full(str(Path(export) / "Source/make_opts"), flags)
    return flags


def compile_export(export, mg5, jobs, log_path):
    """Build the export with the production flags, as MG5 does after a
    ``global_flag`` change: clean and rebuild the Source libraries (DHELAS,
    MODEL; MG5's ``Running make for Source directory`` target), then every
    MadLoop object and ``libMadLoop.a`` (``OLP_static``). Returns the flags."""
    flags = apply_production_flags(export, mg5)
    make = ["make", f"SHELL={shutil.which('bash') or 'bash'}"]
    sub = export / "SubProcesses"
    with open(log_path, "w") as log:
        def run(arguments, cwd):
            subprocess.run(make + arguments, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, check=True)

        for directory in ("Source/DHELAS", "Source/MODEL"):
            run(["clean"], export / directory)
        run([f"-j{jobs}"], export / "Source")
        for directory in (sub, *sorted(p for p in sub.glob("P*") if p.is_dir())):
            run(["clean"], directory)
        run([f"-j{jobs}", "OLP_static"], sub)
    return flags


def recompile(args):
    output = args.output.resolve()
    status_path = output.parent / f"{output.name}.generation.json"
    report = json.loads(status_path.read_text()) if status_path.exists() else {}
    report.update({"status": "compiling", "recompiled_from_existing_export": True})
    status_path.write_text(json.dumps(report, indent=2) + "\n")
    start = time.perf_counter()
    report["fortran_flags"] = compile_export(output, args.mg5.resolve(), args.compile_jobs,
                                             output.parent / f"{output.name}.compile.log")
    report.update({"compile_s": time.perf_counter() - start, "compile_jobs": args.compile_jobs,
                   "status": "compiled"})
    status_path.write_text(json.dumps(report, indent=2) + "\n")
    print("MADLOOP_EXPORT_DONE", output, flush=True)


def complex_mass_scheme(spec):
    return bool(spec["scheme_data"].get("complex_mass_scheme", False))


def mg5_session(spec, mg5, recorder=None):
    """An MG5_aMC command interface with the export settings and the process's
    model imported (``recorder``: a ``madloop_ct_couplings.Recorder`` installed
    before the import); no model pickle is written."""
    _import_mg5(mg5)
    logging.basicConfig(level=logging.INFO)
    from models import import_ufo
    from madgraph.interface.master_interface import MasterCmd

    import_ufo.ReadWrite = False
    if recorder is not None:
        recorder.install()
    command = MasterCmd()
    for setting in (
        "automatic_html_opening False",
        "auto_update 0",
        f"ninja {mg5}/HEPTools/ninja/lib",
        f"collier {mg5}/HEPTools/collier",
        "output_dependencies external",
        "loop_optimized_output True",
        f"complex_mass_scheme {complex_mass_scheme(spec)}",
    ):
        command.exec_cmd("set " + setting)
    command.exec_cmd(f"import model {spec['madloop']['model']}")
    command.exec_cmd(f"set gauge {spec['madloop'].get('gauge', 'Feynman')}")
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, help="process specification JSON")
    parser.add_argument("--process", help="process name inside the specification")
    parser.add_argument("--mg5", type=Path, required=True, help="MG5_aMC source tree")
    parser.add_argument("--output", type=Path, required=True, help="new export directory")
    parser.add_argument(
        "--reference-root", type=Path,
        help="directory substituted for {reference} in model paths (default: MG5 tree's grandparent)",
    )
    parser.add_argument("--compile-jobs", type=int, default=8)
    parser.add_argument("--no-compile", action="store_true")
    parser.add_argument("--recompile", action="store_true",
                        help="rebuild the existing export --output with the production flags")
    args = parser.parse_args()
    if args.recompile:
        if not args.output.is_dir():
            parser.error(f"no export to recompile at {args.output}")
        recompile(args)
        return
    if args.spec is None or args.process is None:
        parser.error("--spec and --process are required to generate an export")

    from required_spec import CORRECTION_STEP, load_process

    mg5 = args.mg5.resolve()
    roots = {"mg5": mg5, "reference": (args.reference_root or mg5.parent.parent).resolve()}
    spec = load_process(args.spec, args.process, roots)
    madloop = spec["madloop"]
    output = args.output.resolve()
    if output.exists():
        parser.error(f"refusing to overwrite existing export {output}")
    status_path = output.parent / f"{output.name}.generation.json"
    report = {
        "process_name": spec["name"],
        "mg5": str(args.mg5.resolve()),
        "model": madloop["model"],
        "command": madloop["process"],
        "host": platform.node(),
        "pid": os.getpid(),
        "status": "generating",
    }

    def write():
        status_path.write_text(json.dumps(report, indent=2) + "\n")

    write()
    import madloop_ct_couplings

    start = time.perf_counter()
    recorder = madloop_ct_couplings.Recorder()
    command = mg5_session(spec, mg5, recorder)
    command.exec_cmd("generate " + madloop["process"])
    multiparticle = bool(spec.get("multiparticle"))
    if not command._curr_amps or (len(command._curr_amps) != 1 and not multiparticle):
        raise RuntimeError(f"expected exactly one MadLoop amplitude, got {len(command._curr_amps)} "
                           "(a multiparticle request sets \"multiparticle\": true)")
    # One correction step per correction of the request (a joint [virt=QCD QED]
    # request over several loop sectors lists both; spec["corrections"]).
    steps = [CORRECTION_STEP[c] for c in spec["corrections"]]
    expected_born = {(o["QCD"], o["QED"]) for o in spec["born_orders_all"]}
    expected_loop = {(spec["loop_orders"]["QCD"], spec["loop_orders"]["QED"])}
    allowed_loop = {(q + step["QCD"], e + step["QED"]) for q, e in expected_born for step in steps}
    subprocesses = []
    for amplitude in command._curr_amps:
        born = Counter(_orders(d) for d in amplitude["born_diagrams"])
        loops = Counter()
        for diagram in amplitude["loop_diagrams"]:
            loops[_orders(diagram)] += diagram["multiplier"]
        legs = amplitude["process"]["legs"]
        subprocesses.append({
            "process": amplitude["process"].nice_string(),
            "pdgs": [leg["id"] for leg in legs],
            "born": len(amplitude["born_diagrams"]),
            "loops": sum(loops.values()),
            "identified_loop_records": len(amplitude["loop_diagrams"]),
            "born_orders": [{"QCD": q, "QED": e, "count": n} for (q, e), n in sorted(born.items())],
            "loop_orders": [{"QCD": q, "QED": e, "count": n} for (q, e), n in sorted(loops.items())],
            "UVCT_diagrams": len(amplitude["loop_UVCT_diagrams"]),
            "attached_CT_vertices": sum(len(d["CT_vertices"]) for d in amplitude["loop_diagrams"]),
            "_born": born, "_loops": loops,
        })
    first = subprocesses[0]
    report.update(
        {
            "graph_generation_s": time.perf_counter() - start,
            "process": first["process"],
            "born": sum(sp["born"] for sp in subprocesses),
            "loops": sum(sp["loops"] for sp in subprocesses),
            "identified_loop_records": sum(sp["identified_loop_records"] for sp in subprocesses),
            "count_convention": "loops: sum of native diagram.multiplier",
            "born_orders": first["born_orders"],
            "loop_orders": first["loop_orders"],
            "UVCT_diagrams": sum(sp["UVCT_diagrams"] for sp in subprocesses),
            "attached_CT_vertices": sum(sp["attached_CT_vertices"] for sp in subprocesses),
        }
    )
    def public(items):
        return [{k: v for k, v in sp.items() if not k.startswith("_")} for sp in items]

    # Loop records of other orders may remain in the export; the driver selects
    # the Born-virtual interference by its squared split orders. A mixed-order
    # request (born_orders_all) admits loop records of every Born order's
    # correction step. A multiparticle request checks each subprocess against
    # its own Born orders (its members differ, e.g. q q~, a a and g g initial
    # states) and records a member without a Born (MG5's loop-squared
    # [sqrvirt] subprocess, m-sm/PLAN.md Q2(a)) as skipped: it is not compared.
    for sp in subprocesses:
        born, loops = sp["_born"], sp["_loops"]
        if multiparticle:
            own = {(q + step["QCD"], e + step["QED"]) for q, e in born for step in steps}
            if not born:
                sp["skipped"] = "no Born: MG5's loop-squared member (sqrvirt), not a Born x virtual reference"
            elif not set(loops) <= own or not set(loops):
                report["status"] = "unexpected amplitude orders"
                report["subprocesses"] = public(subprocesses)
                write()
                raise RuntimeError(f"{sp['process']}: loop orders {dict(loops)} outside {own}")
            continue
        if set(born) != expected_born or not expected_loop <= set(loops) or (
                (len(expected_born) > 1 or len(steps) > 1) and not set(loops) <= allowed_loop):
            report["status"] = "unexpected amplitude orders"
            write()
            raise RuntimeError(
                f"{sp['process']}: Born/loop orders {dict(born)}/{dict(loops)} differ from "
                f"{expected_born}/{expected_loop}")
    if multiparticle:
        report["subprocesses"] = public(subprocesses)
    report["status"] = "exporting"
    write()
    for amplitude in command._curr_amps:
        amplitude["process"].set("split_orders", ["QCD", "QED"])
    # The UFO counterterm couplings behind the export's calls (MG5's coupling
    # renamings), recorded before the output (which empties the loop diagrams'
    # CT vertices) and checked against its sources after it.
    record = madloop_ct_couplings.write_record(output, madloop["process"], madloop["model"],
                                               complex_mass_scheme(spec), command._curr_amps, recorder)
    if record["attached_CT_vertices"] != report["attached_CT_vertices"]:
        raise RuntimeError(f"ct_couplings record: {record['attached_CT_vertices']} attached CT vertices")
    command.exec_cmd(f"output standalone {output}")
    madloop_ct_couplings.check_export(output, record)
    report["source_export_s"] = time.perf_counter() - start - report["graph_generation_s"]
    report["subprocess_directories"] = sorted(p.name for p in (output / "SubProcesses").glob("P*") if p.is_dir())
    report["status"] = "exported"
    write()
    if not args.no_compile:
        report["status"] = "compiling"
        write()
        compile_start = time.perf_counter()
        report["fortran_flags"] = compile_export(output, mg5, args.compile_jobs,
                                                 output.parent / f"{output.name}.compile.log")
        report["compile_s"] = time.perf_counter() - compile_start
        report["compile_jobs"] = args.compile_jobs
        report["status"] = "compiled"
        write()
    print("MADLOOP_EXPORT_DONE", output, flush=True)


if __name__ == "__main__":
    sys.path.insert(0, os.fspath(Path(__file__).resolve().parent))
    main()
