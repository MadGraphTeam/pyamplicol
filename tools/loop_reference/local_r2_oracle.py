# SPDX-License-Identifier: 0BSD
"""Segment-local direct-R2 feasibility oracle for a closed vectorlike chain.

This is a stripped scalar/fermion/two-vector kernel, not a model loader or a
physical loop-induced observable. Component tensors, contractions, polynomial
coefficients and numerical instructions are all supplied by the dependencies.
The two orientations are compared with independent symbolic D-dimensional
traces. No general chiral or internal D-vector rule is inferred from this test.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import prod
from typing import Any

from symbolica import E, Replacement, S
from symbolica.community import tensor as t

from pyamplicol.loops.kernels import CoefficientDAG


@dataclass(frozen=True)
class LocalChain:
    dag: CoefficientDAG
    closed: int
    projected: int
    orientation: int
    shifts: tuple[tuple[Any, ...], ...]
    mass: Any
    coupling: Any
    mu: Any
    epsilon: Any


def slash(components, left, right, name="local_r2::p"):
    """Use the dependency's metric contraction and explicit gamma library."""
    vector = t.Tensor.dense(
        t.TensorName.vector(name)(t.Representation.mink(4)("ell")), components
    )
    gamma = t.TensorExpression.dirac_gamma(4)(left, right, "ell").to_tensor()
    return (gamma * vector).to_tensor()


def propagator(components, mass, mu, left, right):
    """Restricted single-extra-slash representation; parity is retained.

    i*mu*gamma5 squares to -mu**2 and anticommutes with every physical gamma.
    It represents products of the one common evanescent slash only. Its odd
    traces are NOT the D-dimensional trace: they must be removed at closure.
    There are no physical axial vertices or contracted evanescent vector ports.
    """
    spin = t.Representation.bis(4)
    return (
        slash(components, left, right)
        + mass * spin.id(left, right).to_tensor()
        + E("1i") * mu * t.TensorExpression.gamma5(4)(left, right).to_tensor()
    ).to_tensor()


def build_chain(orientation=1, *, shift=None):
    """Build five local transitions, closure, then a physical projection.

    The scalar Yukawa factor is an input. q and the auxiliary variables remain
    polynomial labels, never numerical evaluator inputs. The fixture projector
    is -(xx+yy)/2 for photons along the z axis, divided by 4*m. The stripped
    closed-fermion sign cancels the -4*m normalization of diphoton_r2.json.
    """
    if orientation not in (-1, 1):
        raise ValueError("orientation must be +1 or -1")
    q = tuple(S(f"local_r2::q{k}") for k in range(4))
    mass, coupling, mu, epsilon = S(
        "local_r2::m", "local_r2::y", "local_r2::mu", "local_r2::eps"
    )
    origin = tuple(E("0") for _ in range(4)) if shift is None else tuple(shift)
    shifts = tuple(
        tuple(a + E(str(b)) for a, b in zip(origin, vector, strict=True))
        for vector in ((0, 0, 0, 0), ("-1/2", 0, 0, "-1/2"), (-1, 0, 0, 0))
    )
    dag = CoefficientDAG(q, extra_variables=(mu, epsilon), extra_weights=(1, 0))
    order, photons = (
        ((0, 1, 2), ("a", "b")) if orientation == 1 else ((2, 1, 0), ("b", "a"))
    )
    factors = []
    for position, momentum in enumerate(order):
        left, right = 2 * position, 2 * position + 1
        factor = propagator(
            [a + b for a, b in zip(q, shifts[momentum], strict=True)],
            mass,
            mu,
            left,
            right,
        )
        factors.append((f"fermion:{momentum}", factor))
        if position < 2:
            factors.append(
                (
                    f"vector:{photons[position]}",
                    t.TensorExpression.dirac_gamma(4)(
                        right, right + 1, photons[position]
                    ).to_tensor(),
                )
            )
    current = dag.add(factors[0][0], (coupling * factors[0][1]).to_tensor())
    for name, factor in factors[1:]:
        current = dag.add(name, factor, (current,))
    closed = dag.add(
        "close-spin-channel", t.Representation.bis(4).id(5, 0).to_tensor(), (current,)
    )
    # This contraction is still local and keeps the polynomial parity labels.
    projector = [E("0")] * 16
    projector[5] = projector[10] = -E("1/2") / (4 * mass)
    physical = t.Representation.mink(4)
    projection = t.Tensor.dense(
        t.TensorName("local_r2::transverse")(physical("a"), physical("b")), projector
    )
    projected = dag.add("physical-transverse-projection", projection, (closed,))
    return LocalChain(
        dag, closed, projected, orientation, shifts, mass, coupling, mu, epsilon
    )


def exact_outputs(chain):
    """Expand a small oracle only; native execution never calls this function."""
    resolved = []
    for node in chain.dag.nodes:
        replacements = [
            Replacement(
                S(f"loop_coefficient::input_{position}_{column}"),
                resolved[dependency][column],
            )
            for position, dependency in enumerate(node.dependencies)
            for column in range(len(chain.dag.nodes[dependency].output_labels))
        ]
        resolved.append(
            tuple(
                expression.replace_multiple(replacements).expand()
                for expression in node.expressions
            )
        )
    return tuple(resolved)


def reconstruct(chain, node_id, coefficients, *, parity=None):
    """Small exact comparison tensor; selection happens after spin closure."""
    node = chain.dag.nodes[node_id]
    values = [E("0")] * max(1, prod(node.shape))
    for label, coefficient in zip(node.output_labels, coefficients, strict=True):
        if parity is not None and label.powers[4] % 2 != parity:
            continue
        monomial = coefficient
        for variable, power in zip(chain.dag.variables, label.powers, strict=True):
            monomial *= variable**power
        values[label.component] += monomial
    return t.Tensor.dense(
        t.TensorName("local_r2::comparison")(*node.axes), [v.expand() for v in values]
    )


def full_dimension_trace(chain):
    """Independent Idenso trace; scalar products implement qD²=q4²-mu².

    All three routed momenta have the same evanescent component. Thus every
    pairwise scalar product receives -mu². External vector ports are physical.
    This is not the component recurrence or an integrated rotational identity.
    """
    dimension = S("local_r2::D")
    full, physical, spin = (
        t.Representation.mink(dimension),
        t.Representation.mink(4),
        t.Representation.bis(4),
    )
    gamma = t.TensorExpression.dirac_gamma(dimension)
    names = [t.TensorName.vector(f"local_r2::P{k}") for k in range(3)]
    vectors = [
        t.Tensor.dense(
            name(physical),
            [q + v for q, v in zip(chain.dag.variables[:4], shift, strict=True)],
        )
        for name, shift in zip(names, chain.shifts, strict=True)
    ]

    def prop(index, left, right):
        return gamma(left, right, f"l{index}") * names[index](
            full(f"l{index}")
        ) + chain.mass * spin.id(left, right)

    order, photons = (
        ((0, 1, 2), ("a", "b")) if chain.orientation == 1 else ((2, 1, 0), ("b", "a"))
    )
    expression = (
        chain.coupling
        * prop(order[0], 0, 1)
        * gamma(1, 2, photons[0])
        * prop(order[1], 2, 3)
        * gamma(3, 4, photons[1])
        * prop(order[2], 4, 0)
    )
    # contract="dots" reports Deferred whenever an open-index metric multiplies a
    # surviving scalar product, although nothing is left to reduce; "fully"
    # certifies completion and to_dots() only changes the notation.
    trace = t.TensorExpression(expression).simplify_algebra(
        color=False, contract="fully"
    )
    if trace.reduction_status != t.ReductionStatus.Complete:
        raise ValueError("dependency D-dimensional trace was not reduced completely")
    trace = trace.to_dots()
    replacements = [
        Replacement(
            t.dot(names[i](full), names[j](full)).to_expression(),
            vectors[i].dot(vectors[j]).to_tensor().scalar() - chain.mu**2,
        )
        for i in range(3)
        for j in range(i, 3)
    ]
    index = S("local_r2_index_")
    replacements.extend(
        (
            Replacement(full(index).to_expression(), physical(index).to_expression()),
            Replacement(full.to_expression(), physical.to_expression()),
        )
    )
    library = t.TensorLibrary.hep_lib_atom()
    for vector in vectors:
        library.register(vector)
    return (
        t.TensorExpression(trace.to_expression().replace_multiple(replacements))
        .to_tensor(library)
        .to_dense()
    )


def r2_columns(chain):
    """Only the certified closed even, positive-mu part enters this R2 oracle."""
    return tuple(
        i
        for i, label in enumerate(chain.dag.nodes[chain.projected].output_labels)
        if label.powers[4] > 0 and label.powers[4] % 2 == 0
    )


def build_epsilon_transition():
    """One dependency-reduced local D-vector contraction, not a general rule set.

    Idenso contracts gamma^a gamma^b gamma_a before its remaining physical port
    is materialized. It retains (2-D); after closure against gamma^0 this yields
    -8+8*epsilon. This separate kernel checks explicit epsilon/pole convolution.
    """
    dimension, epsilon = S("local_r2_epsilon::D", "local_r2_epsilon::eps")
    gamma = t.TensorExpression.dirac_gamma(dimension)
    reduced = t.TensorExpression(
        gamma(0, 1, "a") * gamma(1, 2, "b") * gamma(2, 3, "a")
    ).simplify_algebra(color=False)
    if reduced.reduction_status != t.ReductionStatus.Complete:
        raise ValueError("local dimensional Clifford contraction is incomplete")
    index = S("local_r2_epsilon_index_")
    physical = t.TensorExpression(
        reduced.to_expression()
        .replace(
            t.Representation.mink(dimension)(index).to_expression(),
            t.Representation.mink(4)(index).to_expression(),
        )
        .replace(dimension, 4 - 2 * epsilon)
    ).undo_chain()
    temporal = t.Tensor.dense(
        t.TensorName.vector("local_r2_epsilon::temporal")(
            t.Representation.mink(4)("b")
        ),
        [E("1"), E("0"), E("0"), E("0")],
    )
    dag = CoefficientDAG(
        tuple(S(f"local_r2_epsilon::q{k}") for k in range(4)),
        extra_variables=(epsilon,),
        extra_weights=(0,),
    )
    first = dag.add(
        "dimensional-local-transition", (physical.to_tensor() * temporal).to_tensor()
    )
    second = dag.add(
        "physical-gamma0-closure",
        t.TensorExpression.gamma0(4)(3, 0).to_tensor(),
        (first,),
    )
    return dag, second, epsilon
