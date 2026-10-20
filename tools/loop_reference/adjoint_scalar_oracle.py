# SPDX-License-Identifier: 0BSD
"""Independent local adjoint-scalar UFO tensors, without process generation.

Run against the official converted sgluon NLO UFO and MadGraph source. The
binary64 ALOHA Lorentz checks and exact MadGraph SU(3) colour checks certify only
local tensors; they do not certify scalar coefficients, scheme, matching, or a
complete physical amplitude. Generated local Fortran belongs in --build-dir.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
from contextlib import chdir
from itertools import product
from pathlib import Path

import numpy as np
from four_gluon_oracle import color_oracle
from symbolica import E
from symbolica.community import hepkit as hep
from symbolica.community import tensor
from ufo_model_loader.model import Model

from pyamplicol.loops.model import CovariantKernelCatalogue, build_loop_model
from pyamplicol.loops.scalar_frontend import lower_scalar_program
from pyamplicol.loops.tensor_components import physical_tensor_library
from pyamplicol.models.loop_import import load_raw_loop_model


def native_contraction(local, spins, momenta, states):
    tensor_library = physical_tensor_library()
    for leg, momentum in enumerate(momenta):
        tensor_library.register(
            tensor.Tensor.dense(
                tensor.TensorName(hep.Symbols.edge_momentum().get_name())(
                    leg, tensor.Representation.mink(4)
                ),
                momentum,
            )
        )
    expression = local.lorentz
    for leg, (spin, state) in enumerate(zip(spins, states, strict=True)):
        if spin == 1:
            expression *= state[0]
        else:
            assert spin == 3
            label = hep.Symbols.half_edge()(local.leg_half_edges[leg], 1)
            axis = next(
                axis for axis in local.lorentz.axes if axis.index == label
            ).dual()
            name = tensor.TensorName(f"sgluon_local_oracle::source{leg}")
            tensor_library.register(
                tensor.Tensor.dense(name(axis.representation), state)
            )
            expression *= name(axis)
    value = expression.to_tensor(tensor_library)
    assert not value.axes
    return value[0]


def aloha_contraction(function, momenta, states):
    arrays = [
        np.asarray([x.evaluate({}) for x in (*p, *s)], dtype=np.complex128)
        for p, s in zip(momenta, states, strict=True)
    ]
    coupling = np.asarray([3 / 7 + 2j / 5], dtype=np.complex128)
    output = np.empty(1, dtype=np.complex128)
    function(*(a.ctypes.data_as(ctypes.c_void_p) for a in (*arrays, coupling, output)))
    # Same local vertex convention as the existing independent ALOHA oracles.
    return output[0] / (-1j * coupling[0])


def adjoint_scalar_oracle(ufo: Path, madgraph: Path, build_dir: Path) -> dict:
    build_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(madgraph.resolve()))
    raw = load_raw_loop_model(ufo, restriction="full")
    raw_before = raw.to_json()
    source = build_loop_model(raw, scalar_program=lower_scalar_program(raw))
    # The existing local-kernel API uses only this model's structural species and
    # propagator metadata, never its numerical defaults. No Process is constructed.
    structural = Model.from_ufo_model(str(ufo), include_counterterm_finite_parts=False)
    structural.wrap_indices_in_lorentz_structures()
    catalogue = CovariantKernelCatalogue(source, json.loads(structural.to_json()))
    names = ("SS1", "SS2", "VSS1", "VVSS1")
    entries = [
        entry
        for entry in source.kernels
        if 9000001
        in tuple(
            raw.collections["particles"][i]["fields"]["pdg_code"]
            for i in entry.particle_ids
        )
        and dict(entry.order).get("NP", 0) == 0
        and dict(entry.order).get("QED", 0) == 0
        and entry.lorentz_name in names
    ]
    assert {entry.lorentz_name for entry in entries} == set(names)

    with chdir(build_dir):
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
    paths = [build_dir / f"{name}_0.f" for name in names]
    library_path = build_dir / "scalar_local.so"
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
    controls = []
    for name in names:
        entry = next(e for e in entries if e.lorentz_name == name)
        local = catalogue.lower(entry)
        spins = tuple(
            raw.collections["particles"][i]["fields"]["spin"]
            for i in entry.particle_ids
        )
        momenta = tuple(
            tuple(
                E(f"{(leg + 2) * (axis + 1)}/3") + E("1i") * E(f"{leg - axis}/7")
                for axis in range(4)
            )
            for leg in range(len(spins) - 1)
        )
        momenta += (tuple(-sum(row[axis] for row in momenta) for axis in range(4)),)
        # Complete vector component basis, nonunit complex scalar currents, then a
        # dense complex vector source. All momenta are off shell and conserved.
        selections = [basis if spin == 3 else [(E("2/5+3i/7"),)] for spin in spins]
        states = list(product(*selections))
        states.append(
            tuple(
                tuple(
                    E(f"{leg + axis + 1}/11") + E("1i") * E(f"{leg - axis + 2}/13")
                    for axis in range(4)
                )
                if spin == 3
                else (E("5/7-2i/11"),)
                for leg, spin in enumerate(spins)
            )
        )
        function = getattr(library, f"{name.lower()}_0_")
        function.argtypes = [ctypes.c_void_p] * (len(spins) + 2)
        function.restype = None
        errors = []
        for state in states:
            expected = native_contraction(local, spins, momenta, state).evaluate({})
            actual = aloha_contraction(function, momenta, state)
            error = abs(actual - expected) / max(1.0, abs(expected))
            assert error < 5e-14, (name, actual, expected, error)
            errors.append(float(error))
        controls.append(
            dict(
                lorentz=name,
                source_keys=[e.key for e in entries if e.lorentz_name == name],
                spins=spins,
                checks=len(errors),
                max_scaled_error=max(errors),
            )
        )
        print("SCALAR_LORENTZ_PASS", json.dumps(controls[-1]), flush=True)

    ggss = [
        e
        for e in entries
        if e.kind == "R2" and e.particle_names == ("g", "g", "sig8", "sig8")
    ]
    assert ggss
    colors = color_oracle(ggss, catalogue, madgraph, ufo)
    assert raw.to_json() == raw_before
    controls_color = {"vvss": colors}
    for label, ports in (("ss", ("sig8", "sig8")), ("vss", ("g", "sig8", "sig8"))):
        controls_color[label] = color_oracle(
            [e for e in entries if e.particle_names == ports], catalogue, madgraph, ufo
        )
    report = dict(
        scope="local scalar SS/VSS/VVSS tensors and actual SU3 colour bases",
        native="exact dependency tensor algebra",
        reference="binary64 ALOHA + independent MG colour algebra",
        process_generated=False,
        scalar_coefficients_certified=False,
        full_process_certified=False,
        source_preserved=True,
        lorentz=controls,
        color=controls_color,
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ufo", type=Path, required=True)
    parser.add_argument("--madgraph", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = adjoint_scalar_oracle(
        args.ufo.resolve(), args.madgraph.resolve(), args.build_dir.resolve()
    )
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
