# SPDX-License-Identifier: 0BSD
"""Active SU(3) four-gluon R2 source tensors versus ALOHA and MG color algebra.

This certifies only local tensor correspondence. The commented alternate model,
general-Nc continuation, scalar CT normalization and full physical amplitudes
are outside the control. Supplied provider sources are never edited.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import subprocess
import sys
from fractions import Fraction
from itertools import product
from pathlib import Path
from types import SimpleNamespace

from ct_tensor_oracle import aloha_vector_contraction, native_vector_contraction
from symbolica import E, S
from symbolica.community import hepkit as hep
from symbolica.community import tensor

from pyamplicol.loops.model import CovariantKernelCatalogue, build_loop_model
from pyamplicol.models.loop_import import load_raw_loop_model


def color_oracle(entries, catalogue, mg5_source, ufo_path):
    """Compare exact contractions with MadGraph's independent color machinery."""
    sys.path.insert(0, str(mg5_source.resolve()))
    try:
        import models
        from madgraph.core import color_algebra, color_amp
        from models import import_ufo

        ufo = models.load_model(str(ufo_path.resolve()))
        converter = import_ufo.UFOMG5Converter(ufo)
        external_legs = len(entries[0].particle_ids)
        if external_legs not in (3, 4) or any(
            len(entry.particle_ids) != external_legs for entry in entries
        ):
            raise ValueError("local gluon colour oracle requires three or four legs")
        metadata = SimpleNamespace(
            particles=[SimpleNamespace(color=8, pdg_code=21)] * external_legs
        )
        selected = {entry.color: entry for entry in entries}
        strings, native = [], []
        for index in sorted(selected):
            entry = selected[index]
            local = catalogue.lower(entry)
            labels = {
                hep.Symbols.half_edge()(half, 1): f"four_gluon_color_leg_{leg}"
                for leg, half in enumerate(local.leg_half_edges)
            }
            strings.append(entry.color)
            native.append(local.color.rename_indices(labels))
        generator = tensor.TensorExpression.color_t(8, 3)
        probe_legs = (
            ((1, 2, 3), (1, 3, 2))
            if external_legs == 3
            else ((1, 2, 3, 4), (1, 3, 2, 4))
        )
        for legs in probe_legs:
            # Complex trace probes test the relative orientation of d*f terms;
            # their overlaps with the real source basis need not be real.
            strings.append("Tr(" + ",".join(map(str, legs)) + ")")
            native.append(
                tensor.trace(
                    tensor.Representation.cof(3),
                    *(
                        generator(
                            f"four_gluon_color_leg_{leg - 1}", tensor.AUTO, tensor.AUTO
                        )
                        for leg in legs
                    ),
                )
            )
        converted = [converter.treat_color(text, metadata, {}) for text in strings]
        # ColorMatrix consumes the reduced trace basis produced by ColorBasis,
        # not unexpanded f/d tensors. In particular raw ColorObject conjugation
        # reverses indices; expand f/d with the provider before conjugating.
        decompositions = []
        for item in converted:
            terms = color_algebra.ColorFactor([item]).full_simplify()
            decompositions.append(
                tuple(
                    (
                        term.to_immutable(),
                        E(str(term.coeff * Fraction(3) ** term.Nc_power))
                        * (E("1i") if term.is_imaginary else 1),
                    )
                    for term in terms
                )
            )
        basis = dict.fromkeys((key for terms in decompositions for key, _ in terms), ())
        # Both bases explicitly select the general rectangular path. MG's
        # same-basis shortcut assumes real symmetric entries, unlike our probes.
        reference = color_amp.ColorMatrix(basis, dict(basis), Nc=3)
        locations = {key: index for index, key in enumerate(sorted(basis))}
        # Materialize each fixed-SU(3) local basis once. Some symbolic d*d cross
        # contractions retain compact traces; native component contraction owns
        # this fixed-color oracle without implementing new color identities.
        bras = [
            value.wrap_indices(S("ct_color_oracle::bra"), dummies_only=True)
            .dirac_adjoint(preserve_indices=True)
            .to_tensor()
            for value in native
        ]
        kets = [
            value.wrap_indices(S("ct_color_oracle::ket"), dummies_only=True).to_tensor()
            for value in native
        ]
        nonreal = 0
        for i, j in product(range(len(native)), repeat=2):
            # MG returns left * right.conjugate(); use left.conjugate() * right.
            # Its importer, not this oracle, owns Identity's trace normalization.
            expected = E("0")
            for (left, lc), (right, rc) in product(
                decompositions[i], decompositions[j]
            ):
                real, imaginary = reference.col_matrix_fixed_Nc[
                    locations[left], locations[right]
                ]
                expected += (
                    lc.conj() * rc * (E(str(real)) - E("1i") * E(str(imaginary)))
                )
            actual = (bras[i] * kets[j]).to_tensor()
            if actual.axes or (actual[0] - expected).expand() != 0:
                raise AssertionError(
                    f"gluon color overlap ({i},{j}) disagrees with MadGraph: "
                    f"native={actual}, expected={expected}, ports={actual.axes}"
                )
            nonreal += expected != expected.conj()
        return {
            "source_color_basis_count": len(selected),
            "complex_trace_probe_count": 2,
            "exact_overlap_checks": len(native) ** 2,
            "nonreal_overlap_count": nonreal,
            "provider": "MadGraph UFOMG5Converter.treat_color + ColorMatrix, Nc=3",
            "native_color_arithmetic": (
                "exact native SU(3) tensor component contraction"
            ),
            "color_sources": strings,
            "reference_code_sha256": hashlib.sha256(
                (mg5_source / "madgraph" / "core" / "color_algebra.py").read_bytes()
            ).hexdigest(),
        }
    finally:
        sys.path.pop(0)


def four_gluon_oracle(ufo, madloop_build, build_dir, mg5_source):
    from ufo_model_loader.model import Model

    names = ("R2RGA_VVVV10", "R2RGA_VVVV2", "R2RGA_VVVV3", "R2RGA_VVVV5")
    sources = [madloop_build / "Source" / "DHELAS" / f"{name}_0.f" for name in names]
    build_dir.mkdir(parents=True, exist_ok=True)
    library_path = build_dir / "aloha_four_gluon_r2.so"
    subprocess.run(
        [
            "gfortran",
            "-O2",
            "-fPIC",
            "-shared",
            *map(str, sources),
            "-o",
            str(library_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    library = ctypes.CDLL(str(library_path.resolve()))
    source = build_loop_model(load_raw_loop_model(ufo))
    entries = [
        entry
        for entry in source.kernels
        if entry.vertex_name == "V_R2RGA" and entry.kind == "R2"
    ]
    if len(entries) != 57 or {entry.lorentz_name for entry in entries} != set(names):
        raise ValueError("four-gluon oracle requires the active loop_sm V_R2RGA basis")
    structural = Model.from_ufo_model(str(ufo))
    structural.wrap_indices_in_lorentz_structures()
    catalogue = CovariantKernelCatalogue(source, json.loads(structural.to_json()))
    basis = [[E(str(int(i == j))) for j in range(4)] for i in range(4)]
    real_momenta = tuple(
        tuple(E(str(x)) for x in row)
        for row in ((5, 1, 2, 3), (7, -2, 1, 4), (-3, 4, -2, 1), (-9, -3, -1, -8))
    )
    complex_momenta = tuple(
        tuple(
            real_momenta[leg][axis] + E("1i") * E(str((leg + 1) * (axis + 1)))
            for axis in range(4)
        )
        for leg in range(3)
    )
    complex_momenta += (
        tuple(-sum(row[axis] for row in complex_momenta) for axis in range(4)),
    )
    polarizations = [tuple(row) for row in product(basis, repeat=4)]
    polarizations += [
        tuple(
            tuple(
                E(f"{(leg + 1) * (axis + 2) + seed}/7")
                + E("1i") * E(f"{(leg + 2) * (axis + 1) - seed}/11")
                for axis in range(4)
            )
            for leg in range(4)
        )
        for seed in range(4)
    ]
    controls = []
    for name, reference_source in zip(names, sources, strict=True):
        entry = next(entry for entry in entries if entry.lorentz_name == name)
        local = catalogue.lower(entry)
        if local.lorentz.rank != 4:
            raise ValueError("four-gluon Lorentz structure lost external ports")
        function = getattr(library, f"{name.lower()}_0_")
        function.argtypes, function.restype = [ctypes.c_void_p] * 6, None
        errors = []
        for index, pol in enumerate(polarizations):
            momenta = real_momenta if index < 256 else complex_momenta
            expected = native_vector_contraction(local, momenta, pol).evaluate({})
            actual = aloha_vector_contraction(function, momenta, pol)
            error = abs(actual - expected) / max(1.0, abs(expected))
            if error > 5e-14:
                raise AssertionError(f"{name} native/ALOHA disagreement")
            errors.append(error)
        controls.append(
            {
                "lorentz_name": name,
                "source_lorentz": entry.lorentz,
                "checks": len(errors),
                "maximum_scaled_error": max(errors),
                "reference_source": str(reference_source.resolve()),
                "reference_sha256": hashlib.sha256(
                    reference_source.read_bytes()
                ).hexdigest(),
            }
        )
    return {
        "kind": "local-four-gluon-r2-aloha-and-mg-color-control",
        "source_vertex": "V_R2RGA",
        "active_source_basis_entries": len(entries),
        "source_keys": [entry.key for entry in entries],
        "native_arithmetic": "exact Symbolica expressions",
        "aloha_arithmetic": "binary64",
        "reference_phase_removed": "-i*COUP",
        "arbitrary_off_shell_polarizations": True,
        "full_lorentz_component_basis": True,
        "scalar_couplings_validated": False,
        "full_process_validated": False,
        "formal_nc_continuation_validated": False,
        "lorentz_controls": controls,
        "color_control": color_oracle(entries, catalogue, mg5_source, ufo),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ufo", "madloop-build", "build-dir", "mg5-source", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    report = four_gluon_oracle(
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
