#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Compile the small native controls against already built reference providers."""

import argparse
import shutil
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for provider in ("openloops", "recola", "madloop"):
        parser.add_argument(f"--{provider}", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cxx", default="g++")
    parser.add_argument("--fc", default="gfortran")
    parser.add_argument(
        "--case", choices=("uudd", "drell-yan", "top-pair"), default="uudd"
    )
    args = parser.parse_args()
    if args.case == "drell-yan" and (args.recola or args.openloops):
        parser.error("the photon-only Drell-Yan control currently supports MadLoop")
    source = Path(__file__).resolve().parent
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    def run(command, **kwargs):
        subprocess.run([str(x) for x in command], check=True, **kwargs)

    for provider in ("openloops", "recola", "madloop"):
        root = getattr(args, provider)
        if root is None:
            continue
        root = root.resolve()
        command = [args.cxx, "-O2", "-std=c++17", source / f"{provider}_uudd.cpp"]
        if args.case == "top-pair":
            command += ["-DLOOP_REFERENCE_TOP_PAIR"]
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
                    *(["-DLOOP_REFERENCE_TOP_PAIR"] if args.case == "top-pair" else []),
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
                "-lcts",
                "-liregi",
            ]
            for library in ("libgfortran.so", "libquadmath.so"):
                library_path = subprocess.check_output(
                    [args.fc, f"-print-file-name={library}"], text=True
                ).strip()
                command += [library_path]
        run([*command, "-o", output / f"{provider}-{args.case}"])


if __name__ == "__main__":
    main()
