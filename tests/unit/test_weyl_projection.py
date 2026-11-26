# SPDX-License-Identifier: 0BSD
"""Weyl projection at single-chirality vertices, on the built-in model.

A fermion current whose line passed a massive fermion is a full (Dirac,
chirality-0) current. A vertex that takes it to a massless fermion through a
single chiral coupling (the W) has a Dirac result whose other half vanishes
identically, so the model gives the massless result as the Weyl state of that
chirality instead, and the line is Weyl again at its massless end (where its
external fermion is a Weyl source). A vertex with both chiral couplings (the
photon) keeps the full state. The tree-level consequences, per lane and
against MadGraph, are in ``tests/integration/test_tree_weyl_projection.py``.
"""

from __future__ import annotations

import random
from types import SimpleNamespace

import pytest

from pyamplicol.models import BuiltinSMModel


def _index(particle_id: int, chirality: int) -> SimpleNamespace:
    return SimpleNamespace(
        particle_id=particle_id,
        pdg=particle_id,
        chirality=chirality,
        flavour_flow=(particle_id,),
        coupling_orders=(),
    )


def _vertex(model: BuiltinSMModel, particles: tuple[int, int, int]):
    (vertex,) = (vertex for vertex in model.vertices if vertex.particles == particles)
    return vertex


@pytest.fixture(scope="module")
def model() -> BuiltinSMModel:
    return BuiltinSMModel()


@pytest.mark.parametrize(
    ("particles", "expected"),
    [
        # t W- -> b and t~ W+ -> b~ (massless b): the left-handed coupling only.
        ((6, -24, 5), (-1,)),
        ((-6, 24, -5), (1,)),
        # W- t -> b, the boson-first orientation.
        ((-24, 6, 5), (-1,)),
    ],
)
def test_a_single_chiral_coupling_gives_a_weyl_result(
    model: BuiltinSMModel, particles: tuple[int, int, int], expected: tuple[int, ...]
) -> None:
    vertex = _vertex(model, particles)
    left, right, _ = particles
    flows = model.allowed_quantum_flows(vertex, _index(left, 0), _index(right, 0))
    assert tuple(flow.chirality for flow in flows) == expected
    assert tuple(flow.spin_state for flow in flows) == expected


def test_a_vector_like_coupling_keeps_the_full_state(model: BuiltinSMModel) -> None:
    """The photon couples both chiralities of the b: a full b current stays
    full (the built-in model has no full massless current, but the rule is
    local to the vertex)."""

    vertex = _vertex(model, (5, 22, 5))
    flows = model.allowed_quantum_flows(vertex, _index(5, 0), _index(22, 0))
    assert tuple(flow.chirality for flow in flows) == (0,)


@pytest.mark.parametrize("particles", [(6, -24, 5), (-6, 24, -5), (-24, 6, 5)])
def test_the_weyl_result_is_the_nonzero_half_of_the_dirac_kernel(
    model: BuiltinSMModel, particles: tuple[int, int, int]
) -> None:
    """The projected kernel is the half of the Dirac kernel its chirality
    holds, and the other half vanishes: no term is lost."""

    vertex = _vertex(model, particles)
    left_pdg, right_pdg, result = particles
    (flow,) = model.allowed_quantum_flows(
        vertex, _index(left_pdg, 0), _index(right_pdg, 0)
    )
    rng = random.Random(7)

    def values(pdg: int) -> tuple[complex, ...]:
        return tuple(
            complex(rng.uniform(-1, 1), rng.uniform(-1, 1))
            for _ in range(model.current_dimension(pdg, 0))
        )

    left, right = values(left_pdg), values(right_pdg)

    def kernel(chirality: int) -> tuple[complex, ...]:
        return tuple(
            complex(component)
            for component in model.vertex_component_expression(
                vertex.kind,
                left,
                right,
                result_particle_id=result,
                result_chirality=chirality,
                coupling=vertex.coupling,
            )
        )

    weyl = kernel(flow.chirality)
    dirac = kernel(0)
    assert len(weyl) == 2 and len(dirac) == 4
    kept, dropped = (
        (dirac[0:2], dirac[2:4]) if flow.chirality == -1 else (dirac[2:4], dirac[0:2])
    )
    assert weyl == kept
    assert dropped == (0, 0)
    assert any(weyl)


def test_the_template_flows_add_the_full_state_counterpart(
    model: BuiltinSMModel,
) -> None:
    """The recurrence template's flows hold the projection and its full-state
    counterpart (for the all-flow union); every other vertex input pair keeps
    the model's own flows."""

    projected = _vertex(model, (6, -24, 5))
    flows = model.recurrence_quantum_flows(projected, _index(6, 0), _index(-24, 0))
    assert tuple(flow.chirality for flow in flows) == (-1, 0)
    assert flows[1].coupling == flows[0].coupling
    assert flows[1].flavour_flow == flows[0].flavour_flow
    photon = _vertex(model, (5, 22, 5))
    for left in (_index(5, 0), _index(5, -1)):
        right = _index(22, 0)
        assert model.recurrence_quantum_flows(
            photon, left, right
        ) == model.allowed_quantum_flows(photon, left, right)
