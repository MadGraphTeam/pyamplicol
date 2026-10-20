# SPDX-License-Identifier: 0BSD
"""Source Dirac identity two-point (mass insertion) versus generated ALOHA.

Generates the unmodified ALOHA ``R2_QQ_2_0`` routine for ``Identity(1,2)`` from
the source UFO, independently of any process export, and records its binary64
values for exact-rational complex spinor components at complex off-shell
momenta. ``tests/unit/test_loop_fermion_mass_counterterms.py`` contracts the
actual lowered source kernels, before and after the production endpoint
adapter, with the recorded inputs. Scalar couplings, renormalization scheme and
complete processes are outside this local control.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import subprocess
import sys
from contextlib import chdir
from fractions import Fraction
from itertools import product
from pathlib import Path

NAME = "R2_QQ_2"


def _inputs():
    basis = [[(int(i == j), 0) for j in range(4)] for i in range(4)]
    pairs = [*product(basis, repeat=2)]
    for seed in range(3):
        pairs.append(
            tuple(
                [
                    (
                        Fraction((leg + 2) * (axis + seed + 1), 7 + seed),
                        Fraction(leg - axis + seed, 11),
                    )
                    for axis in range(4)
                ]
                for leg in range(2)
            )
        )
    momenta = (
        [(5, 0), (1, 0), (2, 0), (3, 0)],
        [(Fraction(i + 2, i + 1), Fraction(i - 2, 7)) for i in range(4)],
    )
    return pairs, momenta


def fermion_mass_two_point_oracle(ufo: Path, madgraph: Path, build_dir: Path):
    ufo, madgraph, build_dir = ufo.resolve(), madgraph.resolve(), build_dir.resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    with chdir(build_dir):
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(madgraph))
        import aloha
        from aloha import create_aloha

        reference = create_aloha.AbstractALOHAModel(str(ufo))
        reference.look_for_symmetries()
        aloha.loop_mode = True
        lorentz = getattr(reference.model.lorentz, NAME)
        reference.compute_aloha(
            create_aloha.AbstractRoutineBuilder(lorentz), routines=[(0, [])]
        )
        reference.write(str(build_dir), "Fortran")
    source = build_dir / f"{NAME}_0.f"
    shared = build_dir / "fermion_mass_two_point.so"
    subprocess.run(
        ["gfortran", "-O2", "-fPIC", "-shared", str(source), "-o", str(shared)],
        check=True,
        capture_output=True,
        text=True,
    )
    function = getattr(ctypes.CDLL(str(shared)), f"{NAME.lower()}_0_")
    function.argtypes, function.restype = [ctypes.c_void_p] * 4, None

    import numpy as np

    pairs, momenta = _inputs()
    coupling = np.asarray([complex(3 / 7, 2 / 5)], dtype=np.complex128)
    rows = []
    for momentum, (first, second) in product(momenta, pairs):
        p = [complex(float(re), float(im)) for re, im in momentum]
        waves = [
            np.asarray(
                [*p, *(complex(float(re), float(im)) for re, im in spinor)],
                dtype=np.complex128,
            )
            for spinor in (first, second)
        ]
        output = np.empty(1, dtype=np.complex128)
        function(
            *(a.ctypes.data_as(ctypes.c_void_p) for a in (*waves, coupling, output))
        )
        # ALOHA's generated vertex API includes this explicit common phase.
        value = output[0] / (-1j * coupling[0])
        rows.append(
            {
                "momentum": [[str(re), str(im)] for re, im in momentum],
                "first": [[str(re), str(im)] for re, im in first],
                "second": [[str(re), str(im)] for re, im in second],
                "expected": [value.real, value.imag],
            }
        )
    return {
        "kind": "local-fermion-mass-two-point-source-aloha-control",
        "source_lorentz": lorentz.structure,
        "source_spins": list(lorentz.spins),
        "reference": f"MG5_aMC ALOHA {NAME}_0 (loop mode), generated from the UFO",
        "reference_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "reference_arithmetic": "binary64",
        "reference_phase_removed": "-i*COUP",
        "binding": "F1/F2 are the original UFO endpoint slots 1/2",
        "scalar_couplings_validated": False,
        "full_process_validated": False,
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ufo", "madgraph", "build-dir", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    report = fermion_mass_two_point_oracle(args.ufo, args.madgraph, args.build_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=1) + "\n")


if __name__ == "__main__":
    main()
