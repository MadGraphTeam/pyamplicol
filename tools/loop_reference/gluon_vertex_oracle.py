# SPDX-License-Identifier: 0BSD
"""Off-shell ordinary/UV/R2 three-gluon and ordinary/UV quartic tensor control.

Tensor entries are compared with independent generated ALOHA routines and
MadGraph colour algebra. Source scalar coefficients and physical amplitudes are
not certified by this local control. All generated products go in --build-dir.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import subprocess
from itertools import product
from pathlib import Path

from ct_tensor_oracle import aloha_vector_contraction, native_vector_contraction
from four_gluon_oracle import color_oracle
from symbolica import E

from pyamplicol.loops.model import CovariantKernelCatalogue, build_loop_model
from pyamplicol.models.loop_import import load_raw_loop_model


def gluon_vertex_oracle(ufo, madloop_build, build_dir, mg5_source):
    from ufo_model_loader.model import Model

    names = ("VVV1", "VVVV1", "VVVV3", "VVVV4")
    files = [madloop_build / "Source" / "DHELAS" / f"{name}_0.f" for name in names]
    build_dir.mkdir(parents=True, exist_ok=True)
    output = build_dir / "aloha_gluon_gauge_vertices.so"
    subprocess.run(
        ["gfortran", "-O2", "-fPIC", "-shared", *map(str, files), "-o", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    library = ctypes.CDLL(str(output.resolve()))
    source = build_loop_model(load_raw_loop_model(ufo))
    entries = tuple(
        entry
        for entry in source.kernels
        if len(entry.particle_ids) in (3, 4)
        and all(
            source.raw.collections["particles"][i]["fields"]["pdg_code"] == 21
            for i in entry.particle_ids
        )
        and (len(entry.particle_ids) == 3 or entry.kind != "R2")
    )
    if len(entries) != 26 or {entry.lorentz_name for entry in entries} != set(names):
        raise ValueError("control expects the loop_sm ordinary/UV/R2 gauge basis")
    structural = Model.from_ufo_model(str(ufo))
    structural.wrap_indices_in_lorentz_structures()
    catalogue = CovariantKernelCatalogue(source, json.loads(structural.to_json()))
    basis = [tuple(E(str(int(i == j))) for j in range(4)) for i in range(4)]
    controls = []
    for name, reference in zip(names, files, strict=True):
        entry = next(entry for entry in entries if entry.lorentz_name == name)
        local = catalogue.lower(entry)
        legs = len(entry.particle_ids)
        function = getattr(library, f"{name.lower()}_0_")
        function.argtypes, function.restype = [ctypes.c_void_p] * (legs + 2), None
        errors = []
        for sample in range(2):
            momenta = tuple(
                tuple(
                    E(f"{(leg + 2) * (axis + 1) + sample}/{axis + 1}")
                    + E("1i") * E(f"{sample * (leg - axis + 2)}/7")
                    for axis in range(4)
                )
                for leg in range(legs - 1)
            )
            momenta += (
                tuple(-sum(vector[axis] for vector in momenta) for axis in range(4)),
            )
            polarizations = list(product(basis, repeat=legs))
            polarizations += [
                tuple(
                    tuple(
                        E(f"{(leg + 1) * (axis + 2) + sample}/7")
                        + E("1i") * E(f"{(leg + 2) * (axis + 1) - sample}/11")
                        for axis in range(4)
                    )
                    for leg in range(legs)
                )
            ]
            for pol in polarizations:
                expected = native_vector_contraction(local, momenta, pol).evaluate({})
                actual = aloha_vector_contraction(function, momenta, pol)
                error = abs(actual - expected) / max(1.0, abs(expected))
                if error > 5e-14:
                    raise AssertionError(
                        f"{name} native/ALOHA disagreement: {actual} != {expected}"
                    )
                errors.append(error)
        controls.append(
            {
                "lorentz_name": name,
                "source_lorentz": entry.lorentz,
                "checks": len(errors),
                "maximum_scaled_error": max(errors),
                "reference_source": str(reference.resolve()),
                "reference_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
            }
        )
    return {
        "kind": "local-gluon-ordinary-and-counterterm-aloha-control",
        "source_keys": [entry.key for entry in entries],
        "source_entry_count": len(entries),
        "native_arithmetic": "exact Symbolica expressions",
        "aloha_arithmetic": "binary64",
        "reference_phase_removed": "-i*COUP",
        "off_shell_complex_momenta_and_arbitrary_polarizations": True,
        "scalar_couplings_validated": False,
        "full_process_validated": False,
        "lorentz_controls": controls,
        "color_controls": [
            color_oracle(
                [entry for entry in entries if len(entry.particle_ids) == legs],
                catalogue,
                mg5_source,
                ufo,
            )
            for legs in (3, 4)
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ufo", "madloop-build", "build-dir", "mg5-source", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    report = gluon_vertex_oracle(
        args.ufo, args.madloop_build, args.build_dir, args.mg5_source
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "source_keys"},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
