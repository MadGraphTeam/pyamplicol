#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Compile the small native controls against already built reference providers."""

import argparse
import shlex
import shutil
import subprocess
from pathlib import Path


def madloop_library_paths(root):
    """The export's static reducer archives as named by ``LOOP_LIBS`` (not opened)."""
    definitions = root / "SubProcesses/MadLoop_makefile_definitions"
    rows = [
        line.split("=", 1)[1].strip()
        for line in definitions.read_text().splitlines()
        if line.startswith("LOOP_LIBS =")
    ]
    if len(rows) != 1:
        raise ValueError("MadLoop export has no unique LOOP_LIBS definition")
    value = rows[0].replace("$(LIBDIR)", str(root / "lib") + "/")
    value = value.replace("$(libext)", "a")
    if "$" in value or value.endswith("\\"):
        raise ValueError("unsupported MadLoop static-library definition")
    return [Path(x) for x in shlex.split(value)]


def madloop_libraries(root):
    """Use the export's actual static reducers, including optional Ninja/Collier."""
    libraries = madloop_library_paths(root)
    if not libraries or any(not x.is_file() for x in libraries):
        raise ValueError("MadLoop static reducer libraries are missing")
    return libraries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for provider in ("openloops", "recola", "madloop"):
        parser.add_argument(f"--{provider}", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cxx", default="g++")
    parser.add_argument("--fc", default="gfortran")
    parser.add_argument(
        "--case",
        choices=(
            "uudd",
            "drell-yan",
            "top-pair",
            "gluon-scattering",
            "quark-gluon",
            "quark-three-gluon",
            "five-gluon",
        ),
        default="uudd",
    )
    args = parser.parse_args()
    if args.case == "drell-yan" and args.openloops:
        parser.error("the photon-only Drell-Yan control has no matched OpenLoops library")
    source = Path(__file__).resolve().parent
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    case_defines = {
        "drell-yan": ["-DLOOP_REFERENCE_DRELL_YAN", "-DLOOP_REFERENCE_QCD_BORN_POWER=0"],
        "top-pair": ["-DLOOP_REFERENCE_TOP_PAIR"],
        "gluon-scattering": ["-DLOOP_REFERENCE_GLUON_SCATTERING"],
        "quark-gluon": ["-DLOOP_REFERENCE_QUARK_GLUON"],
        "quark-three-gluon": ["-DLOOP_REFERENCE_QUARK_THREE_GLUON"],
        "five-gluon": ["-DLOOP_REFERENCE_FIVE_GLUON"],
    }.get(args.case, [])
    if args.case in {"quark-three-gluon", "five-gluon"}:
        case_defines += ["-DLOOP_REFERENCE_LEGS=5", "-DLOOP_REFERENCE_QCD_BORN_POWER=3"]

    def run(command, **kwargs):
        subprocess.run([str(x) for x in command], check=True, **kwargs)

    for provider in ("openloops", "recola", "madloop"):
        root = getattr(args, provider)
        if root is None:
            continue
        root = root.resolve()
        command = [args.cxx, "-O2", "-std=c++17", source / f"{provider}_uudd.cpp"]
        command += case_defines
        if provider == "openloops":
            command += [
                "-I",
                root / "include",
                "-L",
                root / "lib",
                f"-Wl,-rpath,{root / 'lib'}",
                "-lopenloops",
            ]
        elif provider == "recola":
            bridge = output / "recola_bridge.o"
            run(
                [
                    args.fc,
                    "-O2",
                    "-cpp",
                    *case_defines,
                    "-c",
                    source / "recola_bridge.f90",
                    "-I",
                    root / "include",
                    "-o",
                    bridge,
                ]
            )
            command += [bridge, "-L", root, f"-Wl,-rpath,{root}", "-lrecola"]
        else:
            directory = {
                "uudd": "P0_uux_ddx",
                "drell-yan": "P0_uux_emep_no_z",
                "top-pair": "P0_uux_ttx",
                "gluon-scattering": "P0_gg_gg",
                "quark-gluon": "P0_uux_gg",
                "quark-three-gluon": "P0_uux_ggg",
                "five-gluon": "P0_gg_ggg",
            }[args.case]
            process = root / "SubProcesses" / directory
            if not process.is_dir():
                parser.error(
                    f"MadLoop export must contain the documented {directory} process"
                )
            # The native target avoids the export's optional f2py targets.
            run(
                [
                    "make",
                    "-j4",
                    "OLP_static",
                    f"SHELL={shutil.which('bash') or 'bash'}",
                ],
                cwd=root / "SubProcesses",
            )
            bridge = output / "madloop_bridge.o"
            run(
                [
                    args.fc,
                    "-O2",
                    "-ffixed-line-length-132",
                    "-c",
                    source / "madloop_bridge.f",
                    "-I",
                    process,
                    "-I",
                    root / "Source/MODEL",
                    "-o",
                    bridge,
                ]
            )
            command += [
                bridge,
                root / "lib/libMadLoop.a",
                "-L",
                root / "lib",
                "-ldhelas",
                "-lmodel",
                *madloop_libraries(root),
            ]
            for library in ("libgfortran.so", "libquadmath.so"):
                library_path = subprocess.check_output(
                    [args.fc, f"-print-file-name={library}"], text=True
                ).strip()
                command += [library_path]
        run([*command, "-o", output / f"{provider}-{args.case}"])


if __name__ == "__main__":
    main()
