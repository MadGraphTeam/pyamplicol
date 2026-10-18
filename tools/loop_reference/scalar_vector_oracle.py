# SPDX-License-Identifier: 0BSD
"""Local neutral scalar/vector mixing tensors versus unmodified ALOHA.

The source couplings and physical insertion phases are not certified by this
local vertex check. All source keys are retained; no numerical zero pruning is
used to decide whether a basis has evidence.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
from dataclasses import replace
from itertools import product
from pathlib import Path

from ct_tensor_oracle import aloha_vector_contraction, native_vector_contraction
from symbolica import E

from pyamplicol.loops.covariant_model import build_covariant_structure
from pyamplicol.loops.model import CovariantKernelCatalogue, build_loop_model
from pyamplicol.loops.model_electroweak import (
    neutral_scalar_vector_counterterm_validations,
)
from pyamplicol.loops.scalar_frontend import lower_scalar_program
from pyamplicol.models.loop_import import load_raw_loop_model

NAMES = ("l_GpWmMass4", "l_GpWmMass5")


def scalar_vector_oracle(ufo: Path, madgraph: Path, build_dir: Path):
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(madgraph))
    import aloha
    from aloha import create_aloha

    build_dir.mkdir(parents=True, exist_ok=True)
    reference = create_aloha.AbstractALOHAModel(str(ufo))
    reference.look_for_symmetries()
    aloha.loop_mode = True
    for name in NAMES:
        builder = create_aloha.AbstractRoutineBuilder(
            getattr(reference.model.lorentz, name)
        )
        reference.compute_aloha(builder, routines=[(0, [])])
    reference.write(str(build_dir), "Fortran")
    library_path = build_dir / "aloha_scalar_vector.so"
    subprocess.run(
        [
            "gfortran",
            "-O2",
            "-fPIC",
            "-shared",
            *(str(build_dir / f"{name}_0.f") for name in NAMES),
            "-o",
            str(library_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    library = ctypes.CDLL(str(library_path.resolve()))
    raw = load_raw_loop_model(ufo, restriction="full")
    scalars = lower_scalar_program(raw)
    source = build_loop_model(raw, scalar_program=scalars)
    structure = build_covariant_structure(
        raw,
        scalars=scalars,
        compatibility="gmu_particle_anti",
        covariant_multiplets={
            23: [23, 250, 9000002, -9000002],
            24: [24, 251, 9000003, -9000004],
            -24: [-24, -251, 9000004, -9000003],
        },
    )
    catalogue = CovariantKernelCatalogue(source, structure.native)
    validated = {
        item.source_key
        for item in neutral_scalar_vector_counterterm_validations(source)
    }
    basis = [tuple(E(str(int(i == j))) for j in range(4)) for i in range(4)]
    vectors = (*basis, tuple(E(f"{axis + 2}/7+{axis - 2}i/11") for axis in range(4)))
    scalar_values = (E("1"), E("2/3+1i/5"))
    real = tuple(map(E, ("5", "1", "2", "3")))
    complex_ = tuple(map(E, ("3+1i/5", "1/3-1i/7", "-2/5+1i/11", "4/7-1i/13")))
    momenta = (
        (real, tuple(-x for x in real)),
        (complex_, tuple(-x for x in complex_)),
        (real, complex_),
    )
    report = {
        "kind": "local-neutral-scalar-vector-source-ALOHA-control",
        "reference_phase_removed": "-i*COUP",
        "reference_arithmetic": "binary64",
        "native_arithmetic": "exact Symbolica local tensors",
        "independent_leg_momenta_checked": True,
        "scalar_couplings_validated": False,
        "full_process_validated": False,
        "controls": [],
    }
    for name in NAMES:
        entries = tuple(
            e for e in source.kernels if e.key in validated and e.lorentz_name == name
        )
        if not entries or any(e.lorentz != entries[0].lorentz for e in entries):
            raise ValueError(f"missing or ambiguous neutral source tensor {name}")
        entry = entries[0]
        local = catalogue.lower(entry)
        assert len(local.lorentz.axes) == 1 and local.color.to_tensor()[0] == 1
        # The scalar has no tensor port. Preserve both native momentum edge IDs
        # while handing the one actual vector port to the shared contraction.
        vector_local = replace(local, leg_half_edges=(local.leg_half_edges[1],))
        function = getattr(library, f"{name.lower()}_0_")
        function.argtypes, function.restype = [ctypes.c_void_p] * 4, None
        errors = []
        for momentum, scalar, vector in product(momenta, scalar_values, vectors):
            exact = scalar * native_vector_contraction(
                vector_local, momentum, (vector,)
            )
            expected = exact.evaluate({})
            actual = aloha_vector_contraction(function, momentum, ((scalar,), vector))
            error = abs(actual - expected) / max(1.0, abs(expected))
            if error > 3e-13:
                raise AssertionError(
                    f"{name}: native/ALOHA mismatch {actual} != {expected}"
                )
            errors.append(error)
        report["controls"].append(
            {
                "lorentz_name": name,
                "source_lorentz": entry.lorentz,
                "source_keys": [e.key for e in entries],
                "reference_source": str((build_dir / f"{name}_0.f").resolve()),
                "checks": len(errors),
                "maximum_scaled_error": max(errors),
            }
        )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ufo", "madgraph", "build-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = scalar_vector_oracle(args.ufo, args.madgraph, args.build_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
