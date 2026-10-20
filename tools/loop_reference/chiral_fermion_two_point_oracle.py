# SPDX-License-Identifier: 0BSD
"""Independent source chiral slashes and exact calibrated-vector projections.

This local four-dimensional off-shell control certifies neither source scalar
coefficients nor a complete process. The ALOHA reference is binary64; native
projection/endpoint identities use exact Symbolica expressions.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import subprocess
import sys
from contextlib import chdir
from dataclasses import replace
from itertools import product
from pathlib import Path
from types import SimpleNamespace

from ct_tensor_oracle import aloha_vector_contraction, native_vector_contraction
from symbolica import E, S

from pyamplicol.loops.model import CovariantKernelCatalogue, build_loop_model
from pyamplicol.loops.scalar_frontend import lower_scalar_program
from pyamplicol.loops.vertex_frames import native_physical_vertex
from pyamplicol.models.loop_import import load_raw_loop_model


def _exchange_endpoints(local, spins):
    """Apply the production adapter to the dependency-owned local port frame."""
    # The adapter reads only edge spins and endpoint ownership. This one-vertex
    # fixture carries actual dependency half-edges and actual source spins; it
    # introduces neither a new tensor nor a process graph.
    graph = SimpleNamespace(
        edges=tuple(SimpleNamespace(id=i, spin=spin) for i, spin in enumerate(spins)),
        half_edges=tuple(
            (half, 0, edge, None)
            for edge, half in enumerate(local.leg_half_edges)
        ),
    )
    value = native_physical_vertex(graph, 0, local.lorentz)
    assert set(value.axes) == set(local.lorentz.axes)
    return replace(local, lorentz=value)


def chiral_fermion_two_point_oracle(ufo: Path, madgraph: Path, build_dir: Path):
    from ufo_model_loader.model import Model

    ufo, madgraph, build_dir = ufo.resolve(), madgraph.resolve(), build_dir.resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    names = ("FF3", "FF6")
    # The physical export combines equal FF3/FF6 coefficients. Generate these
    # two existing source routines independently, without a process graph.
    with chdir(build_dir):
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(madgraph))
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
        reference.write(str(build_dir), "Fortran")
    sources = [build_dir / f"{name}_0.f" for name in names]
    shared = build_dir / "chiral_fermion_two_point.so"
    subprocess.run(
        ["gfortran", "-O2", "-fPIC", "-shared", *map(str, sources), "-o", str(shared)],
        check=True,
        capture_output=True,
        text=True,
    )
    library = ctypes.CDLL(str(shared))
    raw = load_raw_loop_model(ufo, restriction="full")
    raw_snapshot = raw.to_json()
    source = build_loop_model(raw, scalar_program=lower_scalar_program(raw))
    structural = Model.from_ufo_model(
        str(ufo), include_counterterm_finite_parts=False
    )
    structural.wrap_indices_in_lorentz_structures()
    catalogue = CovariantKernelCatalogue(source, json.loads(structural.to_json()))
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
    momentum = tuple(S(f"chiral_fermion_ct_oracle::p{i}") for i in range(4))
    routed = (momentum, tuple(-value for value in momentum))
    vector_momenta = (*routed, (E("0"),) * 4)
    controls, exact_values = [], {}
    for name, vector_name, reference_path in zip(
        names, ("FFV2", "FFV3"), sources, strict=True
    ):
        entry = next(
            entry
            for entry in source.kernels
            if entry.lorentz_name == name
            and tuple(
                raw.collections["particles"][index]["fields"]["pdg_code"]
                for index in entry.particle_ids
            )
            == (-2, 2)
        )
        vector_entry = next(
            entry
            for entry in source.kernels
            if entry.kind == "tree" and entry.lorentz_name == vector_name
        )
        local, vector = catalogue.lower(entry), catalogue.lower(vector_entry)
        color = local.color.to_tensor().to_dense()
        assert tuple(color.shape) == (3, 3)
        assert all(color[i, j] == int(i == j) for i in range(3) for j in range(3))
        function = getattr(library, f"{name.lower()}_0_")
        function.argtypes, function.restype = [ctypes.c_void_p] * 4, None
        errors = []
        for numeric_momentum in momenta:
            numeric_routed = (numeric_momentum, tuple(-v for v in numeric_momentum))
            for pair in currents:
                expected = native_vector_contraction(local, numeric_routed, pair)
                actual = aloha_vector_contraction(function, numeric_routed, pair)
                error = abs(actual - expected.evaluate({})) / max(
                    1.0, abs(expected.evaluate({}))
                )
                assert error < 5e-14, (name, actual, expected, error)
                errors.append(error)
        physical_local, physical_vector = (
            _exchange_endpoints(
                kernel,
                tuple(
                    raw.collections["particles"][index]["fields"]["spin"]
                    for index in basis_entry.particle_ids
                ),
            )
            for kernel, basis_entry in ((local, entry), (vector, vector_entry))
        )
        identities, exact_values[name] = 0, []
        for pair in product(basis, repeat=2):
            value = native_vector_contraction(local, routed, pair)
            projection = native_vector_contraction(
                vector, vector_momenta, (*pair, momentum)
            )
            physical_value = native_vector_contraction(physical_local, routed, pair)
            physical_projection = native_vector_contraction(
                physical_vector, vector_momenta, (*pair, momentum)
            )
            assert (value - projection).expand() == 0
            assert (physical_value - physical_projection).expand() == 0
            assert (
                physical_value - native_vector_contraction(local, routed, pair[::-1])
            ).expand() == 0
            exact_values[name].append(value)
            identities += 3
        controls.append(
            dict(
                source_key=entry.key,
                source_lorentz=entry.lorentz,
                source_color=entry.color,
                vector_source_lorentz=vector_entry.lorentz,
                reference_source=str(reference_path),
                reference_sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest(),
                checks=len(errors),
                maximum_scaled_error=max(errors),
                exact_vector_projection_and_endpoint_identities=identities,
            )
        )
    # The sum is additional coverage; neither chiral test is inferred from it.
    slash_entry = next(
        entry
        for entry in source.kernels
        if entry.lorentz_name == "FF1" and entry.particle_names == local.particle_names
    )
    slash = catalogue.lower(slash_entry)
    for index, pair in enumerate(product(basis, repeat=2)):
        assert (
            exact_values["FF3"][index]
            + exact_values["FF6"][index]
            - native_vector_contraction(slash, routed, pair)
        ).expand() == 0
    assert raw.to_json() == raw_snapshot
    return dict(
        kind="local-chiral-fermion-two-point-source-aloha-and-vector-control",
        native_arithmetic="exact Symbolica expressions",
        reference_arithmetic="binary64 generated ALOHA",
        reference_phase_removed="-i*COUP",
        momentum_reference="original first source leg, unchanged by endpoint exchange",
        physical_frame="typed endpoint exchange; no additional FFS projector swap",
        off_shell_complex_momenta_and_arbitrary_spinor_components=True,
        exact_chiral_sum_identities=len(basis) ** 2,
        scalar_couplings_validated=False,
        full_process_validated=False,
        controls=controls,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ufo", "madgraph", "build-dir", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    report = chiral_fermion_two_point_oracle(args.ufo, args.madgraph, args.build_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
