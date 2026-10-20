# SPDX-License-Identifier: 0BSD
"""Local adjoint vector CT bases versus independent ALOHA and MG colour.

Uses exact source tensors, complete vector component bases and complex off-shell
momenta. This local check does not certify scalar couplings or a whole process.
"""

import argparse
import ctypes
import json
import subprocess
import sys
from contextlib import chdir
from itertools import product
from pathlib import Path

from ct_tensor_oracle import aloha_vector_contraction, native_vector_contraction
from four_gluon_oracle import color_oracle
from symbolica import E
from ufo_model_loader.model import Model

from pyamplicol.loops.model import CovariantKernelCatalogue, build_loop_model
from pyamplicol.loops.scalar_frontend import lower_scalar_program
from pyamplicol.models.loop_import import load_raw_loop_model


def adjoint_vector_oracle(ufo: Path, mg: Path, build: Path) -> dict:
    raw = load_raw_loop_model(ufo, restriction="full")
    before = raw.to_json()
    source = build_loop_model(raw, scalar_program=lower_scalar_program(raw))
    structural = Model.from_ufo_model(str(ufo), include_counterterm_finite_parts=False)
    structural.wrap_indices_in_lorentz_structures()
    catalogue = CovariantKernelCatalogue(source, json.loads(structural.to_json()))
    names = (
        "VV1",
        "VV2",
        "VV3",
        "VV4",
        "VV5",
        "VVV2",
        "VVV3",
        "VVV4",
        "VVV5",
        "VVV6",
        "VVV7",
    )
    entries = [
        e
        for e in source.kernels
        if e.kind != "tree"
        and e.lorentz_name in names
        and dict(e.order).get("NP", 0) == dict(e.order).get("QED", 0) == 0
        and all(
            (
                raw.collections["particles"][i]["fields"]["spin"],
                raw.collections["particles"][i]["fields"]["color"],
            )
            == (3, 8)
            for i in e.particle_ids
        )
    ]
    assert {e.lorentz_name for e in entries} == set(names)
    build.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(mg))
    with chdir(build):
        import aloha
        from aloha import create_aloha

        reference = create_aloha.AbstractALOHAModel(str(ufo))
        reference.look_for_symmetries()
        aloha.loop_mode = True
        for name in names:
            reference.compute_aloha(
                create_aloha.AbstractRoutineBuilder(
                    getattr(reference.model.lorentz, name)
                ),
                routines=[(0, [])],
            )
        reference.write(str(build), "Fortran")
    paths = [build / f"{n}_0.f" for n in names]
    library_path = build / "gauge_local.so"
    subprocess.run(
        [
            "gfortran",
            "-O2",
            "-fPIC",
            "-shared",
            *map(str, paths),
            "-o",
            str(library_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    library = ctypes.CDLL(str(library_path))
    basis = [tuple(E(str(int(i == j))) for j in range(4)) for i in range(4)]
    results = []
    for name in names:
        entry = next(e for e in entries if e.lorentz_name == name)
        local = catalogue.lower(entry)
        n = len(entry.particle_ids)
        fn = getattr(library, f"{name.lower()}_0_")
        fn.argtypes = [ctypes.c_void_p] * (n + 2)
        fn.restype = None
        errors = []
        for complex_control in (False, True):
            momenta = tuple(
                tuple(
                    E(f"{(leg + 2) * (axis + 1)}/3")
                    + (E("1i") * E(f"{leg - axis}/7") if complex_control else E("0"))
                    for axis in range(4)
                )
                for leg in range(n - 1)
            )
            momenta += (tuple(-sum(p[a] for p in momenta) for a in range(4)),)
            states = list(product(basis, repeat=n))
            states.append(
                tuple(
                    tuple(
                        E(f"{leg + axis + 1}/11") + E("1i") * E(f"{leg - axis + 2}/13")
                        for axis in range(4)
                    )
                    for leg in range(n)
                )
            )
            for state in states:
                expected = native_vector_contraction(local, momenta, state).evaluate({})
                actual = aloha_vector_contraction(fn, momenta, state)
                error = abs(actual - expected) / max(1.0, abs(expected))
                assert error < 5e-14, (name, actual, expected, error)
                errors.append(float(error))
        row = {
            "lorentz": name,
            "source_expression": entry.lorentz,
            "source_keys": [e.key for e in entries if e.lorentz_name == name],
            "checks": len(errors),
            "maximum_scaled_error": max(errors),
        }
        results.append(row)
        print("GAUGE_LOCAL_PASS", json.dumps(row), flush=True)
    colors = {
        str(n): color_oracle(
            [e for e in entries if len(e.particle_ids) == n], catalogue, mg, ufo
        )
        for n in (2, 3)
    }
    assert raw.to_json() == before
    out = {
        "scope": "actual adjoint vector CT entries; local tensor evidence only",
        "lorentz": results,
        "color": colors,
        "source_preserved": True,
        "scalar_coefficients_certified": False,
        "full_process_certified": False,
    }
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ufo", "madgraph", "build-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = adjoint_vector_oracle(args.ufo, args.madgraph, args.build_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
