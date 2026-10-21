# SPDX-License-Identifier: 0BSD AND MIT
"""Exact dependency-backed conformance checks for the direct-R2 R0 milestone.

This is an algebra oracle, not the production recurrence or a capability
certificate for arbitrary models.  The diphoton example is loop-induced and
does not extend pyAmpliCol's supported Born-loop interference observables.

The numerator preparation, physical projection and dimensional integration
follow Symbolica Community's examples/hep/Higgs_diphoton_decay.py, MIT licensed
by Ruijl Research (2024). See THIRD_PARTY_LICENSES.md beside this file.
"""

from __future__ import annotations

import argparse
import json
from importlib.metadata import version
from pathlib import Path

from symbolica import E, Replacement, S
from symbolica.community import hepkit as hep
from symbolica.community import tensor
from symbolica.community.hepkit import oneloop


def tensor_conformance() -> dict:
    """Check available tensor operations without introducing an algebra engine."""
    dimension, epsilon, n_epsilon = S(
        "loop_r0::D", "loop_r0::eps", "loop_r0::n_epsilon"
    )
    physical = tensor.Representation.mink(4)
    full = tensor.Representation.mink(dimension)
    evanescent = tensor.Representation.euc(n_epsilon)
    assert physical.id("a", "a").contract().to_expression() == 4
    assert full.id("a", "a").contract().to_expression() == dimension
    assert evanescent.id("a", "a").contract().to_expression() == n_epsilon
    assert (4 + n_epsilon - dimension).replace(n_epsilon, -2 * epsilon).replace(
        dimension, 4 - 2 * epsilon
    ).expand() == 0

    # Equal index names in distinct representations are separate ports.  This
    # prevents an accidental physical/evanescent contraction; it does not invent
    # a cross-space metric or a split Clifford algebra.
    physical_vector = tensor.TensorName.vector("loop_r0::p")(physical("a"))
    extra_vector = tensor.TensorName.vector("loop_r0::ell")(evanescent("a"))
    assert (physical_vector * extra_vector).contract().rank == 2

    gamma = tensor.TensorExpression.dirac_gamma(dimension)
    trace = tensor.TensorExpression(
        gamma(1, 2, "mu").to_expression()
        * gamma(2, 3, "nu").to_expression()
        * gamma(3, 4, "mu").to_expression()
        * gamma(4, 1, "rho").to_expression()
    ).simplify_algebra(color=False)
    expected = 4 * (2 - dimension) * full.g("nu", "rho").to_expression()
    assert (trace.to_expression() - expected).expand() == 0
    epsilon_coefficient = (
        (4 * (2 - dimension)).replace(dimension, 4 - 2 * epsilon).expand()
    )
    assert epsilon_coefficient == -8 + 8 * epsilon

    gamma5 = tensor.TensorExpression.gamma5(4)

    def anticommutator(gamma_matrix):
        return (
            tensor.TensorExpression(
                gamma5(1, 2).to_expression() * gamma_matrix(2, 3, "mu").to_expression()
                + gamma_matrix(1, 2, "mu").to_expression()
                * gamma5(2, 3).to_expression()
            )
            .simplify_algebra(color=False)
            .to_expression()
        )

    assert anticommutator(tensor.TensorExpression.dirac_gamma(4)) == 0
    # Preserve the dependency's deliberate refusal to apply a naive D-dimensional
    # anticommutation identity. This nonzero symbolic remainder is not a physical
    # evaluation of the BMHV anticommutator.
    generic_gamma5 = anticommutator(gamma)
    assert generic_gamma5 != 0
    return {
        "physical_metric_trace": "4",
        "full_metric_trace": "D",
        "evanescent_metric_trace": "n_epsilon = D - 4 = -2*eps",
        "split_norm_convention": "q_D^2 = q_4^2 - mu2; mu2 = -q_tilde^2",
        "contracted_dirac_trace": "4*(2-D)*g(nu,rho)",
        "dirac_trace_epsilon_coefficient": "-8 + 8*eps",
        "gamma5_four_dimensional_anticommutator": "0",
        "gamma5_generic_dimension": "unsimplified; BMHV is not certified",
    }


def _prepared_numerator(diagram, model, dimension, indices, yukawa):
    amplitude = hep.Amplitude.from_diagram(diagram, dimension=dimension)
    edge, momentum, mass2, inverse = S("edge_", "momentum_", "mass2_", "inverse_")
    denominators = (
        diagram.denominator_expression(dimension=dimension, in_lmb=True)
        .to_expression()
        .replace(hep.Symbols.denominator()(edge, momentum, mass2, inverse), inverse)
    )
    numerator = (amplitude.expression().to_expression() * denominators).together()
    numerator = numerator.replace(
        model.parameter("yt").symbol * E("1/2").sqrt(), yukawa
    )
    return tensor.TensorExpression(numerator).rename_indices(
        {
            leg.tensor_index: index
            for leg, index in zip(amplitude.legs[1:], indices, strict=True)
        }
    )


def _contract(expression, kinematics):
    # contract() keeps products of tensor sums factored and reports Deferred on
    # the reducer's projector output; expanding first lets it finish.
    result = tensor.TensorExpression(expression).expand().contract()
    assert result.reduction_status == tensor.ReductionStatus.Complete
    result = result.to_dots()
    assert result.is_scalar
    return kinematics.apply(result).to_expression().together()


def _pole_rules(reductions, invariant, mass):
    rules = []
    # These substitutions select a nonsingular massive subthreshold domain only
    # to resolve pole coefficients. No finite master is evaluated at this point.
    assumptions = [Replacement(invariant, E("1")), Replacement(mass, E("2"))]
    for reduction in reductions:
        for _, master in reduction.terms:
            assert master.kind in ("bubble", "triangle")
            call = master.to_expression()
            coefficients = oneloop.master_coefficients(call)
            for position, power in ((1, -1), (2, -2)):
                residue = oneloop.get_expression(
                    call.replace_multiple(assumptions), coefficient=power
                )
                rules.append(Replacement(coefficients[position], residue))
    return rules


def diphoton_r2_oracle() -> dict:
    """Generate both fermion orientations and derive their entire evanescent tensor."""
    model = hep.Model.standard_model()
    top, higgs, photon = [model.particle(name) for name in ("t", "H", "a")]
    vertices = [
        vertex
        for vertex in model.vertex_rules
        if sorted(vertex.particles)
        in [sorted([top.name, top.antiname, boson.name]) for boson in (higgs, photon)]
    ]
    generated = model.process(
        [higgs], [photon, photon], vertex_allow=vertices
    ).generate_diagrams(
        loops=1,
        max_vertices=3,
        maximum_bridges=0,
        numerator_grouping=None,
        progress=None,
    )
    assert len(vertices) == len(generated.diagrams) == 2
    dimension, invariant, yukawa = S("loop_r0::D", "loop_r0::s", "loop_r0::y")
    mu, nu, n_epsilon = S("loop_r0::mu", "loop_r0::nu", "loop_r0::n_epsilon")
    loop, external = hep.Kinematics.loop_momentum(), hep.Kinematics.external_momentum()
    full, physical = (
        tensor.Representation.mink(dimension),
        tensor.Representation.mink(4),
    )

    def kinematics(dim):
        return (
            hep.Kinematics(dim, momenta=[loop(0), external(0), external(1)])
            .with_scalar_product(external(0), external(0), invariant)
            .with_scalar_product(external(1), external(1), E("0"))
            .with_scalar_product(external(0), external(1), invariant / 2)
        )

    full_kinematics, physical_kinematics = kinematics(dimension), kinematics(E("4"))
    algebra = dict(
        gamma=True, color=True, color_substitute_cof_dimension_invariants=True
    )

    def traces(dim):
        # contract="dots" reports Deferred for the open (mu, nu) metric times a
        # surviving scalar product although nothing is left to reduce; "fully"
        # certifies completion and to_dots() only changes the notation.
        result = [
            _prepared_numerator(diagram, model, dim, (mu, nu), yukawa).simplify_algebra(
                contract="fully", **algebra
            )
            for diagram in generated.diagrams
        ]
        assert all(
            trace.reduction_status == tensor.ReductionStatus.Complete
            for trace in result
        )
        return [trace.to_dots() for trace in result]

    full_traces, four_traces = traces(dimension), traces(E("4"))
    normalization = (
        3 * top.charge**2 * model.parameter("ee").symbol ** 2 * yukawa * top.mass
    )
    extra = tensor.TensorName.vector("loop_r0::ell")(
        tensor.Representation.euc(n_epsilon)
    )
    mu_squared = tensor.dot(extra, extra).to_expression()
    index = S("physical_index_")
    physical_slots = [
        Replacement(full(index).to_expression(), physical(index).to_expression()),
        Replacement(full.to_expression(), physical.to_expression()),
    ]
    k2 = full_kinematics.scalar_product(loop(0), loop(0))
    four_k2 = physical_kinematics.scalar_product(loop(0), loop(0))
    differences = [
        (
            (
                full_trace.to_expression()
                .replace(k2, four_k2 - mu_squared)
                .replace_multiple(physical_slots)
                - four_trace.to_expression()
            )
            / normalization
        ).expand()
        for full_trace, four_trace in zip(full_traces, four_traces, strict=True)
    ]
    physical_metric = physical.g(mu, nu)
    assert all(
        (delta + 4 * mu_squared * physical_metric.to_expression()).expand() == 0
        for delta in differences
    )

    def projector(space, kin):
        momentum = tensor.TensorName(external.get_name())
        p_mu, p_nu = momentum(1, space(mu)), momentum(1, space(nu))
        q_mu, q_nu = momentum(0, space(mu)) - p_mu, momentum(0, space(nu)) - p_nu
        transverse = space.g(mu, nu) - 2 * (p_mu * q_nu + q_mu * p_nu) / invariant
        trace = _contract(transverse * space.g(mu, nu), kin)
        return transverse / trace, trace

    physical_projector, physical_transverse = projector(physical, physical_kinematics)
    full_projector, full_transverse = projector(full, full_kinematics)
    assert physical_transverse == 2 and full_transverse == dimension - 2
    projected_delta = [
        -_contract(delta * physical_projector, physical_kinematics) / 4
        for delta in differences
    ]
    combined_delta = sum(projected_delta, E("0")).together()
    assert (combined_delta - 2 * mu_squared).expand() == 0

    families = [
        diagram.integral_family(kinematics=full_kinematics)
        for diagram in generated.diagrams
    ]
    kp = full_kinematics.scalar_product(loop(0), external(1))
    kq = full_kinematics.scalar_product(loop(0), external(0)) - kp
    # This is an integrated rotational identity, never a pointwise replacement.
    transverse_norm = k2 - 4 * kp * kq / invariant
    tilde_reduction = oneloop.reduce(
        families[0],
        [1, 1, 1],
        numerator=(dimension - 4) / full_transverse * transverse_norm,
    )
    tilde_laurent = [
        coefficient.replace_multiple(
            _pole_rules([tilde_reduction], invariant, top.mass)
        ).together()
        for coefficient in oneloop.reduction_coefficients(tilde_reduction)
    ]
    assert tilde_laurent == [E("-1/2"), E("0"), E("0")]
    assert (-combined_delta / mu_squared * tilde_laurent[0]).together() == 1

    # Independently reduce the full D-dimensional numerator. This retains the
    # explicit epsilon coefficient multiplying the UV bubble pole.
    reducer = hep.TensorReducer(
        dimension,
        integrated=[loop(0, tensor.PortPattern.exact(full))],
        external=[external(i, tensor.PortPattern.exact(full)) for i in (0, 1)],
    )
    reductions = [
        oneloop.reduce(
            family,
            [1, 1, 1],
            numerator=_contract(
                reducer.reduce(trace.to_expression()) * full_projector, full_kinematics
            )
            / normalization,
        )
        for family, trace in zip(families, full_traces, strict=True)
    ]
    full_result = (
        -sum((reduction.to_expression() for reduction in reductions), E("0")) / 4
    ).together()
    bubble = oneloop.B0(invariant, top.mass**2, top.mass**2, 1)
    triangle = oneloop.C0(0, invariant, 0, top.mass**2, top.mass**2, top.mass**2, 1)
    expected = (
        2 * (4 - dimension) / (dimension - 2) * bubble
        + (8 * top.mass**2 / (dimension - 2) - invariant) * triangle
    )
    assert (full_result - expected).together() == 0
    finite, single, double = [
        (
            -sum(
                (
                    oneloop.reduction_coefficients(reduction)[i]
                    for reduction in reductions
                ),
                E("0"),
            )
            / 4
        )
        .replace_multiple(_pole_rules(reductions, invariant, top.mass))
        .together()
        for i in range(3)
    ]
    assert single == double == 0
    finite_triangle = oneloop.master_coefficients(triangle)[0]
    assert (finite - (4 * top.mass**2 - invariant) * finite_triangle).together() == 2
    return {
        "graph_orientations": 2,
        "normalized_tensor_delta_per_orientation": "-4*mu2*g4(mu,nu)",
        "projected_normalized_sum": "2*mu2",
        "integrated_q_tilde_squared": {
            "finite": "-1/2",
            "single_pole": "0",
            "double_pole": "0",
        },
        "r2": "1",
        "full_rational_term": "2",
        "r1_inferred_from_full_minus_r2": "1",
        "full_explicit_epsilon_bubble_finite_term": "2",
        "fixture": "diphoton_r2.json",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON report path inside the task workspace",
    )
    args = parser.parse_args()
    report = {
        "symbolica_distribution": version("symbolica"),
        "tensor_conformance": tensor_conformance(),
        "diphoton": diphoton_r2_oracle(),
        "certified_scope": "Exact nonchiral local algebra oracle only",
        "not_certified": [
            "production recurrence",
            "BMHV gamma5",
            "chiral electroweak R2",
            "complex-mass scheme",
            "arbitrary BSM models",
            "numerical precision and batch execution",
        ],
    }
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()
