# SPDX-License-Identifier: 0BSD
"""Compare native two-vector CT kernels to independently generated ALOHA.

This local off-shell tensor oracle does not certify scalar renormalization,
external states, chiral structures, a full process, or arbitrary-precision
physics. Native tensor arithmetic is exact; the independent ALOHA comparison is
binary64. Generated reference sources are only read, never patched.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
from symbolica import E
from symbolica.community import hepkit as hep
from symbolica.community import tensor as tensor

from pyamplicol.loops.model import CovariantKernelCatalogue, build_loop_model
from pyamplicol.loops.model_expressions import parse_exact_ufo
from pyamplicol.models.loop_import import load_raw_loop_model


def _native_contraction(local, momentum, polarizations):
    return native_vector_contraction(
        local, (momentum, tuple(-x for x in momentum)), polarizations
    )


def native_vector_contraction(local, momenta, polarizations):
    library = tensor.TensorLibrary.hep_lib_atom()
    for edge, momentum in enumerate(momenta):
        library.register(
            tensor.Tensor.dense(
                tensor.TensorName(hep.Symbols.edge_momentum().get_name())(
                    edge, tensor.Representation.mink(4)
                ),
                momentum,
            )
        )
    expression = local.lorentz
    for leg, components in enumerate(polarizations):
        label = hep.Symbols.half_edge()(local.leg_half_edges[leg], 1)
        axis = next(axis for axis in local.lorentz.axes if axis.index == label).dual()
        name = tensor.TensorName(f"ct_tensor_oracle::polarization{leg}")
        library.register(tensor.Tensor.dense(name(axis.representation), components))
        expression *= name(axis)
    value = expression.to_tensor(library)
    if value.axes:
        raise ValueError("local vector tensor contraction left unresolved ports")
    return value[0]


def _aloha_contraction(function, momentum, polarizations):
    return aloha_vector_contraction(
        function, (momentum, tuple(-x for x in momentum)), polarizations
    )


def aloha_vector_contraction(function, momenta, polarizations):
    # The generated routine accepts four explicit complex momentum components
    # followed by four vector-current components, for each ordered vector leg.
    waves = [
        np.asarray(
            [
                *(x.evaluate({}) for x in momentum),
                *(x.evaluate({}) for x in pol),
            ],
            dtype=np.complex128,
        )
        for momentum, pol in zip(momenta, polarizations, strict=True)
    ]
    coupling = np.asarray([complex(3 / 7, 2 / 5)], dtype=np.complex128)
    output = np.empty(1, dtype=np.complex128)
    function(
        *(array.ctypes.data_as(ctypes.c_void_p) for array in (*waves, coupling, output))
    )
    # ALOHA's generated vertex API includes this explicit common phase. Native
    # local kernels omit the scalar coupling/global graph phase by construction.
    return output[0] / (-1j * coupling[0])


def gluon_two_point_oracle(ufo: Path, madloop_build: Path, build_dir: Path) -> dict:
    from ufo_model_loader.model import Model

    names = ("R2_GG_1", "R2_GG_2", "R2_GG_3")
    sources = [madloop_build / "Source" / "DHELAS" / f"{name}_0.f" for name in names]
    build_dir.mkdir(parents=True, exist_ok=True)
    library_path = build_dir / "aloha_gluon_two_point.so"
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
    structural = Model.from_ufo_model(str(ufo))
    structural.wrap_indices_in_lorentz_structures()
    catalogue = CovariantKernelCatalogue(source, json.loads(structural.to_json()))
    basis = [[E(str(int(i == j))) for j in range(4)] for i in range(4)]
    momenta = [
        tuple(E(str(value)) for value in (5, 1, 2, 3)),
        tuple(
            map(
                parse_exact_ufo,
                (
                    "3+complex(0,1)/5",
                    "1/3-complex(0,1)/7",
                    "-2/5+complex(0,1)/11",
                    "4/7-complex(0,1)/13",
                ),
            )
        ),
    ]
    complex_polarizations = tuple(
        tuple(map(parse_exact_ufo, row))
        for row in (
            ("2/3+complex(0,1)/5", "1/2", "-3/7", "complex(0,1)/11"),
            ("-1/3", "2/7+complex(0,1)/5", "complex(0,1)/3", "5/11"),
        )
    )
    controls = []
    for name, reference_source in zip(names, sources, strict=True):
        entry = next(
            e
            for e in source.kernels
            if e.kind == "R2"
            and e.particle_names == ("G", "G")
            and e.lorentz_name == name
        )
        local = catalogue.lower(entry)
        color = local.color.to_tensor().to_dense()
        assert color.shape == [8, 8] or tuple(color.shape) == (8, 8)
        assert all(
            color[i, j] == E("1/2") * int(i == j) for i in range(8) for j in range(8)
        )
        function = getattr(library, f"{name.lower()}_0_")
        function.argtypes, function.restype = [ctypes.c_void_p] * 4, None
        errors = []
        for momentum in momenta:
            for polarizations in [
                *((left, right) for left in basis for right in basis),
                complex_polarizations,
            ]:
                exact = _native_contraction(local, momentum, polarizations)
                actual = _aloha_contraction(function, momentum, polarizations)
                expected = exact.evaluate({})
                error = abs(actual - expected) / max(1.0, abs(expected))
                if error > 5e-14:
                    raise AssertionError(
                        f"{name} native/ALOHA disagreement: {actual} != {expected}"
                    )
                errors.append(error)
        controls.append(
            {
                "source_key": entry.key,
                "lorentz_name": name,
                "source_lorentz": entry.lorentz,
                "source_color": entry.color,
                "reference_source": str(reference_source.resolve()),
                "reference_sha256": hashlib.sha256(
                    reference_source.read_bytes()
                ).hexdigest(),
                "checks": len(errors),
                "maximum_scaled_error": max(errors),
            }
        )
    return {
        "kind": "local-gluon-two-point-source-tensor-oracle",
        "native_arithmetic": "exact Symbolica expressions",
        "reference_arithmetic": "binary64 ALOHA",
        "reference_phase_removed": "-i*COUP",
        "off_shell_complex_momenta": True,
        "scalar_couplings_validated": False,
        "full_process_validated": False,
        "controls": controls,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ufo", type=Path, required=True)
    parser.add_argument("--madloop-build", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = gluon_two_point_oracle(args.ufo, args.madloop_build, args.build_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
