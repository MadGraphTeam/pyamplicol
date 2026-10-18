# SPDX-License-Identifier: 0BSD
"""Directed source FFS/Dirac-propagator/chiral-FFV currents versus ALOHA.

The source scalar vertex's raw diagonal _0 matrix does not determine the
physical directed-current convention. This control uses the two crossed HELAS
charge flows actually present in the Gmu charged-Goldstone/neutrino triangle.
It retains the native propagator and tests arbitrary complex components before
any helicity sum or integration. It also checks both massive scalar-current
flows. Reference routines are generated without modification.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import subprocess
import sys
from itertools import product
from pathlib import Path

import numpy as np
from symbolica import E
from symbolica.community import hepkit as h
from symbolica.community import tensor as t

from pyamplicol.loops.covariant_model import build_covariant_structure
from pyamplicol.loops.graphs import build_loop_process
from pyamplicol.loops.vertex_frames import native_physical_vertex
from pyamplicol.models.loop_import import load_raw_loop_model


def _array(values):
    return np.asarray([complex(x.evaluate({})) for x in values], dtype=np.complex128)


def _call(function, *arrays):
    function.argtypes = [ctypes.c_void_p] * len(arrays)
    function.restype = None
    function(*(array.ctypes.data_as(ctypes.c_void_p) for array in arrays))


def _current(library, name, which, components, momentum, mass):
    wave = _array((*(-p for p in momentum), *components))
    scalar = _array((E("0"),) * 4 + (E("1"),))
    coupling = np.asarray([1 + 0j], dtype=np.complex128)
    output = np.zeros(8, dtype=np.complex128)
    _call(
        getattr(library, f"{name.lower()}_{which}_"),
        wave,
        scalar,
        coupling,
        np.asarray([mass]),
        np.asarray([0.0]),
        output,
    )
    return output


def _reference_chain(library, current, other, vector, orientation):
    other = _array((E("0"),) * 4 + other)
    vector = _array((E("0"),) * 4 + vector)
    coupling, output = np.asarray([1 + 0j]), np.zeros(1, dtype=np.complex128)
    first, second = (current, other) if orientation == 0 else (other, current)
    _call(library.ffv2_0_, first, second, vector, coupling, output)
    return output[0] / (-1j)


def _native(expression, edge, momentum, states, mass=0):
    library = t.TensorLibrary.hep_lib_atom()
    library.register(
        t.Tensor.dense(
            t.TensorName(h.Symbols.edge_momentum().get_name())(
                edge, t.Representation.mink(4)
            ),
            momentum,
        )
    )
    for half, components in states.items():
        axis = next(
            a for a in expression.axes if a.index == h.Symbols.half_edge()(half, 1)
        ).dual()
        name = t.TensorName(f"dirac_current_oracle::state{half}")
        library.register(t.Tensor.dense(name(axis.representation), components))
        expression *= name(axis)
    result = expression.to_tensor(library)
    assert not result.axes
    return complex(
        (
            result[0] / (momentum[0] ** 2 - sum(p * p for p in momentum[1:]) - mass**2)
        ).evaluate({})
    )


def _unit_vertex(model, vertex):
    result = vertex.numerator_expression()
    for row in model.vertex_rule(vertex.interaction).couplings:
        for name in row:
            if name:
                result = result.replace(model.coupling(name).symbol, E("1"))
    return result


def dirac_current_oracle(ufo, madgraph, build_dir):
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(madgraph))
    import aloha
    from aloha import create_aloha

    build_dir.mkdir(parents=True, exist_ok=True)
    reference = create_aloha.AbstractALOHAModel(str(ufo))
    reference.look_for_symmetries()
    aloha.loop_mode = True
    for name, routines in (
        ("FFS1", [(1, [])]),
        ("FFS3", [(2, [])]),
        ("FFS4", [(1, []), (2, [])]),
        ("FFV2", [(0, [])]),
    ):
        reference.compute_aloha(
            create_aloha.AbstractRoutineBuilder(getattr(reference.model.lorentz, name)),
            routines=routines,
        )
    reference.write(str(build_dir), "Fortran")
    paths = [
        build_dir / f"{name}.f"
        for name in ("FFS1_1", "FFS3_2", "FFS4_1", "FFS4_2", "FFV2_0")
    ]
    shared = build_dir / "dirac_current_oracle.so"
    subprocess.run(
        ["gfortran", "-O2", "-fPIC", "-shared", *map(str, paths), "-o", str(shared)],
        check=True,
        capture_output=True,
    )
    library = ctypes.CDLL(str(shared.resolve()))
    zeros = (
        "aEW0M1",
        "MD",
        "MU",
        "MS",
        "MC",
        "MB",
        "Me",
        "MTA",
        "lamWS",
        "AWS",
        "rhoWS",
        "etaWS",
        "ymdo",
        "ymup",
        "yms",
        "ymc",
        "ymb",
        "yme",
        "ymtau",
    )
    ones = ("epsUV", "epsIR", "LogSwitch", "GfRedefinitionChoice")
    structure = build_covariant_structure(
        load_raw_loop_model(ufo, restriction="full"),
        compatibility="gmu_particle_anti",
        fixed_parameters={**dict.fromkeys(zeros, "0"), **dict.fromkeys(ones, "1")},
        covariant_multiplets={
            23: [23, 250, 9000002, -9000002],
            24: [24, 251, 9000003, -9000004],
            -24: [-24, -251, 9000004, -9000003],
        },
    )
    model = structure.native
    process = build_loop_process(
        model.process(["e-", "e+"], ["m-", "m+"]),
        ordinary_model=model,
        selected_corrections=["QED"],
        perturbative_orders={"QED": 1, "QCD": 1},
        born_order_bounds={"QCD": 0, "QED": 2},
        loop_order_bounds={"QCD": 0, "QED": 4},
    )
    charged = next(
        g
        for g in process.loops
        if sorted(abs(e.pdg) for e in g.edges if e.id in g.loop_edges) == [14, 14, 251]
    )
    # Identify actual rule/edge attachments, not incidental canonical IDs.
    vertex = next(
        v
        for v in charged.native.vertices
        if tuple(
            model.particle(p).pdg_code
            for p in model.vertex_rule(v.interaction).particles
        )
        == (-14, 14, 23)
    )
    vector_factor = native_physical_vertex(
        charged, vertex.id, _unit_vertex(model, vertex)
    )
    vector_half = next(
        half
        for half, owner, edge, _ in charged.half_edges
        if owner == vertex.id
        and next(e for e in charged.edges if e.id == edge).spin == 3
    )
    momenta = (
        tuple(map(E, ("3", "1/3", "-2/5", "4/7"))),
        tuple(map(E, ("3+1i/5", "1/3-1i/7", "-2/5+1i/11", "4/7-1i/13"))),
    )
    basis = tuple(tuple(E(str(int(i == j))) for j in range(4)) for i in range(4))
    states = (
        *basis,
        tuple(map(E, ("2/3+1i/5", "-3/7+1i/11", "5/13-2i/7", "-1/3-4i/9"))),
    )
    vectors = (
        *basis,
        tuple(map(E, ("1/7+2i/3", "-2/5+1i/7", "3/11-1i/13", "-2/17+1i/19"))),
    )
    report = {
        "kind": "directed-FFS-propagator-chiral-FFV-ALOHA",
        "reference_arithmetic": "binary64",
        "native_arithmetic": "exact components",
        "propagators_modified": False,
        "dimensional_gamma5_validated": False,
        "source_graph": charged.id,
        "reference_sources": list(map(str, paths)),
        "controls": [],
    }
    for external_index, name, which, sign, orientation in (
        (3, "FFS3", 2, -1, 0),
        (2, "FFS1", 1, 1, 1),
    ):
        external = next(e for e in charged.edges if e.external_index == external_index)
        half, owner, *_ = next(
            row for row in charged.half_edges if row[2] == external.id
        )
        scalar_vertex = next(v for v in charged.native.vertices if v.id == owner)
        edge = next(
            e
            for e in charged.native.internal_edges
            if abs(e.particle.pdg_code) == 14 and owner in (e.source, e.target)
        )
        other_half = next(
            hh
            for hh, vv, ee, _ in charged.half_edges
            if vv == vertex.id
            and ee != edge.id
            and next(e for e in charged.edges if e.id == ee).spin == 2
        )
        raw = _unit_vertex(model, scalar_vertex)
        scalar = native_physical_vertex(charged, owner, raw)
        expression = scalar * edge.numerator_expression() * vector_factor
        previous = raw * edge.numerator_expression() * vector_factor
        errors, failures = [], 0
        for q, incoming, other, vector in product(momenta, states, states, vectors):
            current = _current(library, name, which, incoming, q, 0.0)
            target = _reference_chain(library, current, other, vector, orientation)
            assignments = {half: incoming, other_half: other, vector_half: vector}
            actual = _native(
                expression, edge.id, tuple(sign * p for p in q), assignments
            )
            error = abs(actual - target) / max(1.0, abs(target))
            if error > 3e-13:
                raise AssertionError((name, which, error, actual, target))
            errors.append(error)
            old = _native(previous, edge.id, tuple(sign * p for p in q), assignments)
            failures += abs(old - target) > 3e-13 * max(1.0, abs(target))
        report["controls"].append(
            {
                "source_rule": scalar_vertex.interaction,
                "reference_current": f"{name}_{which}",
                "external_index": external_index,
                "checks": len(errors),
                "maximum_scaled_error": max(errors),
                "endpoint_only_failing_checks": int(failures),
            }
        )
    # Both orientations of the unchanged massive source Dirac propagator, with
    # the scalar identity current. This isolates its mass term from chirality.
    seen = set()
    for graph in process.loops:
        if sorted(abs(e.pdg) for e in graph.edges if e.id in graph.loop_edges) != [
            13,
            25,
            250,
        ]:
            continue
        for vertex in graph.native.vertices:
            rule = model.vertex_rule(vertex.interaction)
            if tuple(model.particle(p).pdg_code for p in rule.particles) != (
                -13,
                13,
                25,
            ):
                continue
            edge = next(
                e
                for e in graph.native.internal_edges
                if abs(e.particle.pdg_code) == 13 and vertex.id in (e.source, e.target)
            )
            direction = vertex.id == edge.source
            if direction in seen:
                continue
            seen.add(direction)
            half = next(
                hh
                for hh, vv, ee, _ in graph.half_edges
                if vv == vertex.id
                and next(e for e in graph.edges if e.id == ee).external_index
                is not None
            )
            output = next(
                hh
                for hh, vv, ee, _ in graph.half_edges
                if ee == edge.id and vv != vertex.id
            )
            mass = E("2/3")
            expression = native_physical_vertex(
                graph, vertex.id, _unit_vertex(model, vertex)
            ) * edge.numerator_expression().replace(model.parameter("MM").symbol, mass)
            which, sign = (1, 1) if direction else (2, -1)
            errors = []
            for q, incoming in product(momenta, states):
                target = _current(library, "FFS4", which, incoming, q, 2 / 3)[4:]
                actual = [
                    _native(
                        expression,
                        edge.id,
                        tuple(sign * p for p in q),
                        {half: incoming, output: probe},
                        mass,
                    )
                    for probe in basis
                ]
                error = max(abs(a - b) for a, b in zip(actual, target, strict=True))
                if error > 3e-13:
                    raise AssertionError(("massive", which, error))
                errors.append(error)
            report["controls"].append(
                {
                    "reference_current": f"FFS4_{which}",
                    "mass": "2/3",
                    "checks": len(errors) * 4,
                    "maximum_scaled_error": max(errors),
                }
            )
    assert seen == {False, True}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ufo", "madgraph", "build-dir", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = dirac_current_oracle(args.ufo, args.madgraph, args.build_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "checks": sum(r["checks"] for r in report["controls"]),
                "maximum_error": max(
                    r["maximum_scaled_error"] for r in report["controls"]
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
