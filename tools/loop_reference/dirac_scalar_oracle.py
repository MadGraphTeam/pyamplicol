# SPDX-License-Identifier: 0BSD
"""Exact local FFS source tensors versus unmodified standalone ALOHA routines.

Only the four-dimensional Dirac/scalar vertex and external-current frame are
tested. Scalar couplings, propagators, UV/R2 completeness and dimensional gamma5
prescriptions are outside this control. Reference arithmetic is binary64.
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
from types import SimpleNamespace

from ct_tensor_oracle import aloha_vector_contraction, native_vector_contraction
from symbolica import E
from symbolica.community import hepkit as h

from pyamplicol.loops.covariant_model import build_covariant_structure
from pyamplicol.loops.model import CovariantKernelCatalogue, build_loop_model
from pyamplicol.loops.model_expressions import parse_exact_ufo
from pyamplicol.loops.scalar_frontend import lower_scalar_program
from pyamplicol.loops.vertex_frames import certified_ffs_source, native_physical_vertex
from pyamplicol.models.loop_import import load_raw_loop_model

NAMES = ("FFS1", "FFS2", "FFS3", "FFS4", "FFS5", "l_epemH23", "l_epemH24")


def _exact_complex(value):
    return E(str(value.real)) + E("1i") * E(str(value.imag))


def _physical_states(momentum, helicity, kind):
    from aloha.template_files.wavefunctions import ixxxxx, oxxxxx

    native = (
        h.FourMomentum(*momentum)
        .wavefunction(kind, h.Helicity.PLUS if helicity == 1 else h.Helicity.MINUS)
        .components
    )
    mass = (momentum[0] ** 2 - sum(x * x for x in momentum[1:])) ** 0.5
    routine = oxxxxx if kind.endswith("_bar") else ixxxxx
    reference = routine(momentum, mass, helicity, 1 if kind.startswith("u") else -1)[2:]
    if max(abs(a - b) for a, b in zip(native, reference, strict=True)) > 2e-14:
        raise AssertionError("dependency/ALOHA physical spinor conventions differ")
    return tuple(map(_exact_complex, native)), tuple(map(_exact_complex, reference))


def _controls():
    basis = [tuple(E(str(int(i == j))) for j in range(4)) for i in range(4)]
    scalars = (E("1"), E("2/3+1i/5"))
    momenta = (
        (E("2"), E("1"), E("0"), E("0")),
        (E("3"), E("0"), E("1"), E("0")),
        (E("-5"), E("-1"), E("-1"), E("0")),
    )
    for left, right, scalar in product(basis, basis, scalars):
        yield "all-bispinor-components", momenta, (left, right), (left, right), scalar
    currents = tuple(
        tuple(E(f"{(leg + 1) * (axis + 2)}/7+{leg - axis}i/11") for axis in range(4))
        for leg in range(2)
    )
    offshell = tuple(
        tuple(E(f"{leg + axis + 1}+{leg - axis}i/7") for axis in range(4))
        for leg in range(2)
    )
    offshell += (tuple(-offshell[0][i] - offshell[1][i] for i in range(4)),)
    for order, scalar in product(((0, 1), (1, 0)), scalars):
        pair = tuple(currents[index] for index in order)
        yield "complex-off-shell", offshell, pair, pair, scalar
    # Each output component of both local open-current orientations is probed
    # with arbitrary complex incoming components, before adding propagators.
    for orientation, component, scalar in product((0, 1), basis, scalars):
        pair = (
            (component, currents[0]) if orientation == 0 else (currents[1], component)
        )
        yield "open-endpoint-components", offshell, pair, pair, scalar
    for barred_momentum, ket_momentum in (
        ((5.0, 3.0, 0.0, 4.0), (5.0, 0.0, 3.0, -4.0)),
        ((13.0, 3.0, 4.0, 0.0), (13.0, 0.0, 0.0, -5.0)),
    ):
        momenta = (
            tuple(E(str(x)) for x in barred_momentum),
            tuple(E(str(x)) for x in ket_momentum),
            tuple(
                E(str(-a - b))
                for a, b in zip(barred_momentum, ket_momentum, strict=True)
            ),
        )
        for barred, ket in (
            ("u_bar", "u"),
            ("v_bar", "v"),
            ("v_bar", "u"),
            ("u_bar", "v"),
        ):
            for left, right, scalar in product((-1, 1), (-1, 1), scalars):
                a, ra = _physical_states(barred_momentum, left, barred)
                b, rb = _physical_states(ket_momentum, right, ket)
                yield f"physical-{barred}-{ket}", momenta, (a, b), (ra, rb), scalar


def dirac_scalar_oracle(ufo: Path, madgraph: Path, build_dir: Path):
    from ufo_model_loader.symbolica_processing import wrap_indices

    # No source-model edits, cache writes or patched generated reference code.
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(madgraph))
    import aloha
    from aloha import create_aloha

    build_dir.mkdir(parents=True, exist_ok=True)
    reference = create_aloha.AbstractALOHAModel(str(ufo))
    reference.look_for_symmetries()
    aloha.loop_mode = True
    for name in NAMES:
        routine = create_aloha.AbstractRoutineBuilder(
            getattr(reference.model.lorentz, name)
        )
        reference.compute_aloha(routine, routines=[(0, [])])
    reference.write(str(build_dir), "Fortran")
    library_path = build_dir / "aloha_dirac_scalar.so"
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
    controls = tuple(_controls())
    report = {
        "kind": "local-dirac-scalar-source-physical-frame-aloha-control",
        "reference_phase_removed": "-i*COUP",
        "reference_spinor_order": "unbarred HELAS F1, barred HELAS F2",
        "native_arithmetic": "exact local tensors; binary64 physical-state inputs",
        "reference_arithmetic": "binary64",
        "source_scalars_evaluated": False,
        "propagators_changed": False,
        "full_process_validated": False,
        "dimensional_gamma5_validated": False,
        "controls": [],
    }
    for name in NAMES:
        entries = tuple(entry for entry in source.kernels if entry.lorentz_name == name)
        entry = entries[0]
        declaration = SimpleNamespace(
            spins=tuple(
                source.raw.collections["particles"][index]["fields"]["spin"]
                for index in entry.particle_ids
            ),
            structure=wrap_indices(parse_exact_ufo(entry.lorentz)),
        )
        if not certified_ffs_source(declaration):
            raise AssertionError(f"actual source {name} is outside the local FFS gate")
        local = catalogue.lower(entry)
        graph_frame = SimpleNamespace(
            edges=tuple(
                SimpleNamespace(id=i, spin=spin) for i, spin in enumerate((2, 2, 1))
            ),
            half_edges=tuple(
                (half, 0, leg, "incoming")
                for leg, half in enumerate(local.leg_half_edges)
            ),
        )
        mapped = replace(
            local, lorentz=native_physical_vertex(graph_frame, 0, local.lorentz)
        )
        assert native_physical_vertex(graph_frame, 0, mapped.lorentz) == local.lorentz
        assert set(mapped.lorentz.axes) == set(local.lorentz.axes)
        function = getattr(library, f"{name.lower()}_0_")
        function.argtypes, function.restype = [ctypes.c_void_p] * 5, None
        errors, raw_failures = [], 0
        for kind, momenta, spinors, reference_spinors, scalar in controls:
            # Scalar legs carry no tensor port; their unit state or supplied
            # off-shell scalar-current value multiplies the local bilinear.
            value = scalar * native_vector_contraction(mapped, momenta, spinors)
            target = aloha_vector_contraction(
                function,
                (momenta[1], momenta[0], momenta[2]),
                (reference_spinors[1], reference_spinors[0], (scalar,)),
            )
            error = abs(value.evaluate({}) - target) / max(1.0, abs(target))
            if error > 3e-13:
                raise AssertionError(f"{name} {kind}: FFS/ALOHA scaled error {error}")
            errors.append(error)
            raw_value = scalar * native_vector_contraction(local, momenta, spinors)
            raw_failures += abs(raw_value.evaluate({}) - target) > 3e-13 * max(
                1.0, abs(target)
            )
        report["controls"].append(
            {
                "lorentz_name": name,
                "source_lorentz": entry.lorentz,
                "source_keys": [entry.key for entry in entries],
                "reference_source": str((build_dir / f"{name}_0.f").resolve()),
                "checks": len(errors),
                "maximum_scaled_error": max(errors),
                "unadapted_failing_controls": int(raw_failures),
            }
        )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ufo", "madgraph", "build-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = dirac_scalar_oracle(args.ufo, args.madgraph, args.build_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "checks": sum(row["checks"] for row in report["controls"]),
                "maximum_scaled_error": max(
                    row["maximum_scaled_error"] for row in report["controls"]
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
