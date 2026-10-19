# SPDX-License-Identifier: 0BSD
"""Generate an independent unequal-mass/Yukawa charged-current ALOHA fixture."""

from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
from contextlib import chdir
from pathlib import Path

import numpy as np


def charged_ffv_oracle(ufo: Path, madgraph: Path, build_dir: Path) -> dict:
    ufo, madgraph, build_dir = ufo.resolve(), madgraph.resolve(), build_dir.resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    # ALOHA's parser may write PLY tables into cwd; keep them in this workspace
    # build directory as well as its generated Fortran and shared library.
    with chdir(build_dir):
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(madgraph))
        import aloha
        from aloha import create_aloha

        reference = create_aloha.AbstractALOHAModel(str(ufo))
        reference.look_for_symmetries()
        aloha.loop_mode = True
        for name, routines in (("FFS4", [(1, []), (2, [])]), ("FFV2", [(0, [])])):
            reference.compute_aloha(
                create_aloha.AbstractRoutineBuilder(
                    getattr(reference.model.lorentz, name)
                ),
                routines=routines,
            )
        reference.write(str(build_dir), "Fortran")
        sources = [build_dir / f"{name}.f" for name in ("FFS4_1", "FFS4_2", "FFV2_0")]
    shared = build_dir / "charged_ffv.so"
    subprocess.run(
        ["gfortran", "-O2", "-fPIC", "-shared", *map(str, sources), "-o", str(shared)],
        check=True,
        capture_output=True,
    )
    library = ctypes.CDLL(str(shared.resolve()))

    def array(values):
        return np.asarray(values, dtype=np.complex128)

    def call(name, *arrays):
        function = getattr(library, name)
        function.argtypes = [ctypes.c_void_p] * len(arrays)
        function.restype = None
        function(*(value.ctypes.data_as(ctypes.c_void_p) for value in arrays))

    def current(side, state, momentum, mass, yukawa):
        output = array([0] * 8)
        call(
            f"ffs4_{side}_",
            array([*[-p for p in momentum], *state]),
            array([0, 0, 0, 0, 1]),
            array([yukawa]),
            np.array([mass]),
            np.array([0.0]),
            output,
        )
        return output

    def pair(z):
        return [float(z.real), float(z.imag)]

    first = [2 / 3 + 1j / 5, -3 / 7 + 1j / 11, 5 / 13 - 2j / 7, -1 / 3 - 4j / 9]
    second = [-4 / 7 + 3j / 5, 1 / 7 - 2j / 11, 4 / 13 + 1j / 7, -2 / 3 + 1j / 9]
    vector = [1 / 7 + 2j / 3, -2 / 5 + 1j / 7, 3 / 11 - 1j / 13, -2 / 17 + 1j / 19]
    q = [3 + 1j / 5, 1 / 3 - 1j / 7, -2 / 5 + 1j / 11, 4 / 7 - 1j / 13]
    r = [4 - 1j / 3, -3 / 5 + 1j / 11, 7 / 9 - 1j / 17, 2 / 7 + 1j / 19]
    yukawas = (2 / 5 + 1j / 11, 3 / 7 - 1j / 13)
    rows = []
    for masses in ((2 / 3, 5 / 7), (11 / 13, 17 / 19)):
        a = current(1, first, q, masses[0], yukawas[0])
        b = current(2, second, r, masses[1], yukawas[1])
        value = array([0])
        call("ffv2_0_", a, b, array([0] * 4 + vector), array([1]), value)
        rows.append(
            dict(
                masses=masses,
                yukawas=list(map(pair, yukawas)),
                first=list(map(pair, a[4:])),
                second=list(map(pair, b[4:])),
                vector=list(map(pair, vector)),
                expected=pair(value[0] / (-1j)),
            )
        )
    return dict(
        description=(
            "Unmodified ALOHA FFS4_1 and FFS4_2 with independent unequal masses "
            "and Yukawa couplings feed FFV2_0; final common -i removed, central "
            "vector coupling one; complex off-shell momenta."
        ),
        sources=[f"MG5_aMC_v3_7_0 ALOHA {path.stem}" for path in sources],
        rows=rows,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ufo", type=Path, required=True)
    parser.add_argument("--madgraph", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = charged_ffv_oracle(args.ufo, args.madgraph, args.build_dir)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
