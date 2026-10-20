#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Generate and compile one MadLoop standalone export from a process specification.

The specification (see ``required_processes.json``) names the MG5 model and
process string. The export uses optimized loop output with the installed
Ninja/Collier reducers and records split orders ``QCD, QED`` so the driver can
select the Born-virtual interference by squared coupling order. Graph counts,
the observed Born/loop amplitude orders and the generation, export and
compilation wall times are written to ``generation.json`` next to the export.

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
import shutil
import subprocess
import sys
import time


def _orders(diagram):
    return diagram["orders"].get("QCD", 0), diagram["orders"].get("QED", 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True, help="process specification JSON")
    parser.add_argument("--process", required=True, help="process name inside the specification")
    parser.add_argument("--mg5", type=Path, required=True, help="MG5_aMC source tree")
    parser.add_argument("--output", type=Path, required=True, help="new export directory")
    parser.add_argument(
        "--reference-root", type=Path,
        help="directory substituted for {reference} in model paths (default: MG5 tree's grandparent)",
    )
    parser.add_argument("--compile-jobs", type=int, default=8)
    parser.add_argument("--no-compile", action="store_true")
    args = parser.parse_args()

    from required_spec import load_process

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
        "status": "generating",
    }

    def write():
        status_path.write_text(json.dumps(report, indent=2) + "\n")

    write()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(mg5))
    logging.basicConfig(level=logging.INFO)
    from models import import_ufo
    from madgraph.interface.master_interface import MasterCmd

    import_ufo.ReadWrite = False
    command = MasterCmd()
    for setting in (
        "automatic_html_opening False",
        "auto_update 0",
        f"ninja {mg5}/HEPTools/ninja/lib",
        f"collier {mg5}/HEPTools/collier",
        "output_dependencies external",
        "loop_optimized_output True",
        f"complex_mass_scheme {madloop.get('complex_mass_scheme', False)}",
    ):
        command.exec_cmd("set " + setting)
    start = time.perf_counter()
    command.exec_cmd(f"import model {madloop['model']}")
    command.exec_cmd(f"set gauge {madloop.get('gauge', 'Feynman')}")
    command.exec_cmd("generate " + madloop["process"])
    if len(command._curr_amps) != 1:
        raise RuntimeError("expected exactly one MadLoop amplitude")
    amplitude = command._curr_amps[0]
    born = Counter(_orders(d) for d in amplitude["born_diagrams"])
    loops = Counter()
    for diagram in amplitude["loop_diagrams"]:
        loops[_orders(diagram)] += diagram["multiplier"]
    expected_born = {(spec["born_orders"]["QCD"], spec["born_orders"]["QED"])}
    expected_loop = {(spec["loop_orders"]["QCD"], spec["loop_orders"]["QED"])}
    report.update(
        {
            "graph_generation_s": time.perf_counter() - start,
            "process": amplitude["process"].nice_string(),
            "born": len(amplitude["born_diagrams"]),
            "loops": sum(loops.values()),
            "identified_loop_records": len(amplitude["loop_diagrams"]),
            "count_convention": "loops: sum of native diagram.multiplier",
            "born_orders": [{"QCD": q, "QED": e, "count": n} for (q, e), n in sorted(born.items())],
            "loop_orders": [{"QCD": q, "QED": e, "count": n} for (q, e), n in sorted(loops.items())],
            "UVCT_diagrams": len(amplitude["loop_UVCT_diagrams"]),
            "attached_CT_vertices": sum(len(d["CT_vertices"]) for d in amplitude["loop_diagrams"]),
        }
    )
    # Loop records of other orders may remain in the export; the driver selects
    # the Born-virtual interference by its squared split orders.
    if set(born) != expected_born or not expected_loop <= set(loops):
        report["status"] = "unexpected amplitude orders"
        write()
        raise RuntimeError(
            f"Born/loop orders {dict(born)}/{dict(loops)} differ from {expected_born}/{expected_loop}"
        )
    report["status"] = "exporting"
    write()
    amplitude["process"].set("split_orders", ["QCD", "QED"])
    command.exec_cmd(f"output standalone {output}")
    report["source_export_s"] = time.perf_counter() - start - report["graph_generation_s"]
    report["status"] = "exported"
    write()
    if not args.no_compile:
        report["status"] = "compiling"
        write()
        compile_start = time.perf_counter()
        with open(output.parent / f"{output.name}.compile.log", "w") as log:
            subprocess.run(
                ["make", f"-j{args.compile_jobs}", "OLP_static", f"SHELL={shutil.which('bash') or 'bash'}"],
                cwd=output / "SubProcesses",
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
            )
        report["compile_s"] = time.perf_counter() - compile_start
        report["compile_jobs"] = args.compile_jobs
        report["status"] = "compiled"
        write()
    print("MADLOOP_EXPORT_DONE", output, flush=True)


if __name__ == "__main__":
    sys.path.insert(0, os.fspath(Path(__file__).resolve().parent))
    main()
