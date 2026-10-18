# SPDX-License-Identifier: 0BSD
"""Off-shell source quark slash versus generated ALOHA and vector contraction.

The independent comparison is binary64; native identities use exact rational
complex components. This does not certify scalar couplings, a whole process or
insertion into a different model's spinor convention.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import subprocess
from dataclasses import replace
from itertools import product
from pathlib import Path

from ct_tensor_oracle import aloha_vector_contraction, native_vector_contraction
from symbolica import E, S

from pyamplicol.loops.model import CovariantKernelCatalogue, build_loop_model
from pyamplicol.models.loop_import import load_raw_loop_model


def fermion_two_point_oracle(ufo, madloop_build, build_dir):
    from ufo_model_loader.model import Model

    reference = madloop_build / "Source/DHELAS/R2_QQ_1_0.f"
    build_dir.mkdir(parents=True, exist_ok=True)
    output = build_dir / "aloha_fermion_two_point.so"
    subprocess.run(
        ["gfortran", "-O2", "-fPIC", "-shared", str(reference), "-o", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    library = ctypes.CDLL(str(output.resolve()))
    function = library.r2_qq_1_0_
    function.argtypes, function.restype = [ctypes.c_void_p] * 4, None
    source = build_loop_model(load_raw_loop_model(ufo))
    structural = Model.from_ufo_model(str(ufo))
    structural.wrap_indices_in_lorentz_structures()
    catalogue = CovariantKernelCatalogue(source, json.loads(structural.to_json()))
    entry = next(e for e in source.kernels if e.vertex_name == "V_R2UU")
    tree = next(
        e
        for e in source.kernels
        if e.kind == "tree" and e.particle_names == ("u~", "u", "G")
    )
    local, vector = catalogue.lower(entry), catalogue.lower(tree)
    color = local.color.to_tensor().to_dense()
    assert tuple(color.shape) == (3, 3)
    assert all(color[i, j] == int(i == j) for i in range(3) for j in range(3))

    # The proposed native slash is obtained by contracting the calibrated native
    # vector-current representative, not by assuming source spinor slots agree.
    target_entry = replace(entry, lorentz="P(-1,1)*Gamma(-1,1,2)")
    target_tree = replace(tree, lorentz="Gamma(3,1,2)")
    target_source = replace(
        source, kernels=(*source.kernels, target_entry, target_tree)
    )
    target_catalogue = CovariantKernelCatalogue(
        target_source, json.loads(structural.to_json())
    )
    target_local, target_vector = (
        target_catalogue.lower(target_entry),
        target_catalogue.lower(target_tree),
    )
    basis = [tuple(E(str(int(i == j))) for j in range(4)) for i in range(4)]
    momenta = (
        tuple(E(str(v)) for v in (5, 1, 2, 3)),
        tuple(E(f"{i + 2}/{i + 1}") + E("1i") * E(f"{i - 2}/7") for i in range(4)),
    )
    currents = [
        *product(basis, repeat=2),
        tuple(
            tuple(
                E(f"{(leg + 1) * (axis + 2)}/7") + E("1i") * E(f"{leg - axis}/11")
                for axis in range(4)
            )
            for leg in range(2)
        ),
    ]
    errors = []
    for momentum in momenta:
        routed = (momentum, tuple(-v for v in momentum))
        for pair in currents:
            exact = native_vector_contraction(local, routed, pair)
            actual = aloha_vector_contraction(function, routed, pair)
            expected = exact.evaluate({})
            error = abs(actual - expected) / max(1.0, abs(expected))
            if error > 5e-14:
                raise AssertionError(
                    f"source slash native/ALOHA mismatch: {actual} != {expected}"
                )
            errors.append(error)
    # Generic symbolic momentum, all16 basis pairs: exact equality proves the
    # complete linear tensor relation, not only the sampled ALOHA momenta.
    momentum = tuple(S(f"fermion_ct_oracle::p{i}") for i in range(4))
    routed = (momentum, tuple(-v for v in momentum))
    vector_momenta = (*routed, (E("0"),) * 4)
    identities = 0
    for pair in product(basis, repeat=2):
        exact = native_vector_contraction(local, routed, pair)
        source_projection = native_vector_contraction(
            vector, vector_momenta, (*pair, momentum)
        )
        target_projection = native_vector_contraction(
            target_vector, vector_momenta, (*pair, momentum)
        )
        target_slash = native_vector_contraction(target_local, routed, pair)
        assert (exact - source_projection).expand() == 0
        assert (target_slash - target_projection).expand() == 0
        assert (
            target_slash - native_vector_contraction(local, routed, pair[::-1])
        ).expand() == 0
        identities += 3
    return {
        "kind": "local-fermion-two-point-source-aloha-control",
        "source_key": entry.key,
        "source_lorentz": entry.lorentz,
        "source_color": entry.color,
        "reference_source": str(reference.resolve()),
        "reference_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
        "native_arithmetic": "exact Symbolica expressions",
        "aloha_arithmetic": "binary64",
        "reference_phase_removed": "-i*COUP",
        "off_shell_complex_momenta_and_arbitrary_spinor_components": True,
        "checks": len(errors),
        "maximum_scaled_error": max(errors),
        "exact_vector_projection_and_slot_identities": identities,
        "native_vector_lorentz": target_tree.lorentz,
        "native_projected_slash": target_entry.lorentz,
        "scalar_couplings_validated": False,
        "native_process_insertion_validated": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ufo", "madloop-build", "build-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = fermion_two_point_oracle(args.ufo, args.madloop_build, args.build_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
