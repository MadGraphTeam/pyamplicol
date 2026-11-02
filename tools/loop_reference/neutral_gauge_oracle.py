# SPDX-License-Identifier: 0BSD
"""Local neutral-current QCD counterterms versus unchanged ALOHA and MG colour.

Tests off-shell complex currents before any physical state sum or integration.
The epsilon is strictly four-dimensional; this is not a dimensional gamma-five,
renormalization scheme, or whole-process certificate.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
from itertools import product
from pathlib import Path

from ct_tensor_oracle import aloha_vector_contraction, native_vector_contraction
from four_gluon_oracle import color_oracle
from model_compatibility import prepare_loop_sm_scalar_declarations
from symbolica import E

from pyamplicol.loops.compiler import prepare_loop_request_model
from pyamplicol.loops.model import CovariantKernelCatalogue
from pyamplicol.models.loop_import import load_raw_loop_model


def neutral_gauge_oracle(ufo, madgraph, build_dir):
    names = ("R2_GGZ", "R2_GGGVa", "R2_GGVV")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(madgraph))
    import aloha
    from aloha import create_aloha

    build_dir.mkdir(parents=True, exist_ok=True)
    reference = create_aloha.AbstractALOHAModel(str(ufo))
    reference.look_for_symmetries()
    aloha.loop_mode = True
    for name in names:
        routine = create_aloha.AbstractRoutineBuilder(
            getattr(reference.model.lorentz, name)
        )
        reference.compute_aloha(routine, routines=[(0, [])])
    reference.write(str(build_dir), "Fortran")
    output = build_dir / "aloha_neutral_gauge.so"
    subprocess.run(
        [
            "gfortran",
            "-O2",
            "-fPIC",
            "-shared",
            *(str(build_dir / f"{name}_0.f") for name in names),
            "-o",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    library = ctypes.CDLL(str(output.resolve()))
    view = prepare_loop_sm_scalar_declarations(load_raw_loop_model(ufo))
    prepared = prepare_loop_request_model(
        view.derived,
        born_order_bounds={"QCD": 2, "QED": 2},
        loop_order_bounds={"QCD": 4, "QED": 2},
        fixed_parameters={"MB": "0", "ymb": "0", "MTA": "0", "ymtau": "0"},
    )
    catalogue = CovariantKernelCatalogue(
        prepared.model, json.loads(prepared.structure.native.to_json())
    )
    entries = [
        entry
        for entry in prepared.model.kernels
        if entry.vertex_name in ("V_GGZ", "V_GGGZ", "V_GGGA")
    ]
    basis = [tuple(E(str(int(i == j))) for j in range(4)) for i in range(4)]
    controls = []
    for name in names:
        entry = next(entry for entry in entries if entry.lorentz_name == name)
        local = catalogue.lower(entry)
        legs = len(local.leg_half_edges)
        function = getattr(library, name.lower() + "_0_")
        function.argtypes, function.restype = [ctypes.c_void_p] * (legs + 2), None
        checks, maximum = 0, 0.0
        for sample in range(2):
            momenta = tuple(
                tuple(
                    E(f"{(leg + 2) * (axis + 1) + sample}/{axis + 1}")
                    + E("1i") * E(f"{sample * (leg - axis + 2)}/7")
                    for axis in range(4)
                )
                for leg in range(legs - 1)
            )
            momenta += (tuple(-sum(p[axis] for p in momenta) for axis in range(4)),)
            currents = [
                *product(basis, repeat=legs),
                tuple(
                    tuple(
                        E(f"{(leg + 1) * (axis + 2)}/7")
                        + E("1i") * E(f"{leg - axis}/11")
                        for axis in range(4)
                    )
                    for leg in range(legs)
                ),
            ]
            for states in currents:
                actual = native_vector_contraction(local, momenta, states).evaluate({})
                expected = aloha_vector_contraction(function, momenta, states)
                error = abs(actual - expected) / max(1.0, abs(expected))
                assert error < 5e-13, (name, sample, error, actual, expected)
                maximum = max(maximum, error)
                checks += 1
        controls.append(
            dict(
                source_key=entry.key,
                lorentz=name,
                source_lorentz=entry.lorentz,
                checks=checks,
                maximum_scaled_error=maximum,
            )
        )
    colors = [
        color_oracle(
            [entry for entry in entries if len(entry.particle_ids) == legs],
            catalogue,
            madgraph,
            ufo,
        )
        for legs in (3, 4)
    ]
    return dict(
        kind="local-neutral-gauge-source-aloha-and-mg-color-control",
        native_arithmetic="exact native dependency tensor components",
        reference_arithmetic="binary64 ALOHA; exact MG colour",
        reference_phase_removed="-i*COUP",
        off_shell_complex_currents=True,
        scalar_couplings_validated=False,
        dimensional_gamma5_validated=False,
        full_process_validated=False,
        lorentz_controls=controls,
        color_controls=colors,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ufo", "madgraph", "build-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = neutral_gauge_oracle(args.ufo, args.madgraph, args.build_dir)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
