# SPDX-License-Identifier: 0BSD
"""Licensed local R2 kernel checks; these do not enable production direct R2."""

from decimal import Decimal, localcontext

import pytest
from symbolica import E, Replacement, S
from symbolica.community import tensor as t

from pyamplicol.loops.kernels import CoefficientDAG, NativeCoefficientDAG
from tools.loop_reference.local_r2_oracle import (
    build_chain,
    build_epsilon_transition,
    exact_outputs,
    full_dimension_trace,
    propagator,
    r2_columns,
    reconstruct,
    slash,
)

MODES = [
    ("double", None, "2e-12"),
    ("double-double", None, "2e-27"),
    ("arbitrary", 80, "2e-73"),
]


@pytest.fixture(scope="module")
def backend():
    """The loop core of the staged pyamplicol._rusticol (formerly _loop_reduction)."""
    from pyamplicol.loops.native import load_loop_native

    return load_loop_native()


@pytest.fixture(scope="module")
def chains():
    return [build_chain(orientation) for orientation in (1, -1)]


def test_extra_slash_identities_and_original_four_momentum_shift():
    q = tuple(S(f"r2_identity_q{k}") for k in range(4))
    mu, mass = S("r2_identity_mu", "r2_identity_mass")
    spin = t.Representation.bis(4)
    assert spin.id("a", "a").contract().to_expression() == 4

    def extra(a, b):
        return E("1i") * mu * t.TensorExpression.gamma5(4)(a, b).to_tensor()

    square = (extra(0, 1) * extra(1, 2) + mu**2 * spin.id(0, 2).to_tensor()).to_tensor()
    assert all(value.expand() == 0 for value in square)
    gamma = t.TensorExpression.dirac_gamma(4)
    anticommutes = (
        extra(0, 1) * gamma(1, 2, "a").to_tensor()
        + gamma(0, 1, "a").to_tensor() * extra(1, 2)
    ).to_tensor()
    assert all(value.expand() == 0 for value in anticommutes)
    momentum = t.Tensor.dense(
        t.TensorName.vector("r2_identity_p")(t.Representation.mink(4)), q
    )
    inverse = (
        propagator(q, mass, mu, 0, 1) * propagator(q, -mass, mu, 1, 2)
        - (momentum.dot(momentum).to_tensor().scalar() - mass**2 - mu**2)
        * spin.id(0, 2).to_tensor()
    ).to_tensor()
    assert all(value.expand() == 0 for value in inverse)
    shift = tuple(map(E, ("1/3", "-2/5", "7/11", "1/13")))
    difference = (
        propagator([a + b for a, b in zip(q, shift, strict=True)], mass, mu, 0, 1)
        - propagator(q, mass, mu, 0, 1)
        - slash(shift, 0, 1)
    ).to_tensor()
    assert all(value.expand() == 0 for value in difference)


@pytest.mark.parametrize("orientation", (1, -1))
@pytest.mark.parametrize("shift", (None, (E("1/3"), E("-2/5"), E("7/11"), E("1/13"))))
def test_local_even_closure_matches_independent_full_dimensional_trace(
    orientation, shift, chains
):
    chain = (
        chains[0 if orientation == 1 else 1]
        if shift is None
        else build_chain(orientation, shift=shift)
    )
    outputs = exact_outputs(chain)
    even = reconstruct(chain, chain.closed, outputs[chain.closed], parity=0)
    full = full_dimension_trace(chain)
    full = full.permute_axes([full.axes.index(axis) for axis in even.axes])
    assert all((a - b).expand() == 0 for a, b in zip(even, full, strict=True))
    # Removing odd-mu currents at any intermediate transition loses even terms.
    assert all(
        any(label.powers[4] % 2 for label in node.output_labels)
        for node in chain.dag.nodes[:5]
    )
    odd = reconstruct(chain, chain.closed, outputs[chain.closed], parity=1)
    assert any(value.expand() != 0 for value in odd)
    projected = reconstruct(chain, chain.projected, outputs[chain.projected], parity=0)[
        0
    ]
    assert (
        projected - projected.replace(chain.mu, E("0")) - chain.coupling * chain.mu**2
    ).expand() == 0
    selected = r2_columns(chain)
    assert [
        chain.dag.nodes[chain.projected].output_labels[i].powers for i in selected
    ] == [(0, 0, 0, 0, 2, 0)]
    assert chain.dag.direct_r2_certified is False


def test_premature_odd_projection_loses_the_rational_numerator(chains):
    chain = chains[0]
    wrong = []
    for node in chain.dag.nodes:
        replacements = [
            Replacement(
                S(f"loop_coefficient::input_{position}_{column}"),
                wrong[dependency][column],
            )
            for position, dependency in enumerate(node.dependencies)
            for column in range(len(chain.dag.nodes[dependency].output_labels))
        ]
        # Negative control: deliberately discard odd currents BEFORE closure.
        wrong.append(
            tuple(
                E("0")
                if node.id < chain.closed and label.powers[4] % 2
                else expression.replace_multiple(replacements).expand()
                for label, expression in zip(
                    node.output_labels, node.expressions, strict=True
                )
            )
        )
    projected = reconstruct(chain, chain.projected, wrong[chain.projected], parity=0)[0]
    assert (projected - projected.replace(chain.mu, E("0"))).expand() == 0
    assert chain.coupling * chain.mu**2 != 0


def test_local_completion_agrees_with_dependency_generated_diphoton_oracle(chains):
    from tools.loop_reference.tensor_oracle import diphoton_r2_oracle

    reference = diphoton_r2_oracle()
    assert reference["projected_normalized_sum"] == "2*mu2"
    total = E("0")
    for chain in chains:
        outputs = exact_outputs(chain)
        projected = reconstruct(
            chain, chain.projected, outputs[chain.projected], parity=0
        )[0]
        delta = projected - projected.replace(chain.mu, E("0"))
        total += delta / (chain.coupling * chain.mu**2)
    assert (total - 2).together() == 0


def test_auxiliary_weights_zero_kernel_and_validation():
    q = tuple(S(f"r2_zero_q{k}") for k in range(4))
    mu, eps = S("r2_zero_mu", "r2_zero_eps")
    dag = CoefficientDAG(q, extra_variables=(mu, eps), extra_weights=(1, 0))
    first = dag.add("zero", t.TensorExpression(E("0")).to_tensor())
    assert dag.nodes[first].output_labels[0].powers == (0, 0, 0, 0, 0, 0)
    second = dag.add("next", t.TensorExpression(mu**2 * eps**2).to_tensor(), (first,))
    # Structural rank is computed before substituting predecessor coefficients.
    assert dag.nodes[second].rank == 2
    standalone = dag.add(
        "weighted", t.TensorExpression(q[0] * mu**2 * eps**2).to_tensor()
    )
    assert dag.nodes[standalone].rank == 3
    for variables, weights in [
        ((mu,), ()),
        ((mu,), (-1,)),
        ((q[0],), (1,)),
        ((mu,), (True,)),
    ]:
        with pytest.raises(ValueError):
            CoefficientDAG(q, extra_variables=variables, extra_weights=weights)


def native_batch(backend, rows, columns, values, options, ids):
    return backend.NativeBatch.from_decimal(
        values, rows, columns, row_ids=ids, **options
    )


@pytest.mark.parametrize("arithmetic,precision,tolerance", MODES)
def test_both_local_orientations_reduce_natively_in_three_precisions(
    backend, chains, arithmetic, precision, tolerance
):
    options = {"arithmetic": arithmetic, "precision": precision}
    native = [
        NativeCoefficientDAG(c.dag, output_nodes=(c.projected,), **options)
        for c in chains
    ]
    a, b = S("local_r2_sum_a", "local_r2_sum_b")
    combine = backend.CoefficientEvaluator(
        (a + b).evaluator([a, b], n_cores=1, jit_compile=False).save(), **options
    )
    reducer = backend.PolynomialPlan(3, ["c*mu2", "0", "0"], ["c"], **options)
    shifts = ["0", "0", "0", "0", "-0.5", "0", "0", "-0.5", "-1", "0", "0", "0"]
    with localcontext() as context:
        context.prec = 150
        tiny = Decimal(2) ** -(80 if arithmetic == "double-double" else 180)
        for rows in (1, 5, 0, 33, 1):
            ids = [123 - 3 * i for i in range(rows)]
            couplings = [
                Decimal(1)
                + (tiny if arithmetic != "double" else Decimal("0.125")) * (i + 1)
                for i in range(rows)
            ]
            all_coefficients = []
            for chain, program in zip(chains, native, strict=True):
                values = [
                    ["2" if p == chain.mass else str(y), "0"]
                    for y in couplings
                    for p in chain.dag.parameters
                ]
                inputs = native_batch(
                    backend, rows, len(chain.dag.parameters), values, options, ids
                )
                all_coefficients.append(
                    program.evaluate_batch(inputs).take_columns(list(r2_columns(chain)))
                )
            coefficients = combine.evaluate_batch(
                backend.NativeBatch.concat_columns(all_coefficients)
            )
            result = reducer.evaluate_batch(
                native_batch(
                    backend,
                    rows,
                    12,
                    [[x, "0"] for _ in ids for x in shifts],
                    options,
                    ids,
                ),
                native_batch(
                    backend,
                    rows,
                    3,
                    [["4", "0"] for _ in ids for _ in range(3)],
                    options,
                    ids,
                ),
                native_batch(backend, rows, 1, [["1", "0"] for _ in ids], options, ids),
                coefficients,
                native_batch(
                    backend,
                    rows,
                    9,
                    [
                        [x, "0"]
                        for _ in ids
                        for x in ["0", "0", "1", "0", "0", "0", "1", "0", "0"]
                    ],
                    options,
                    ids,
                ),
            )
            assert result.values.row_ids == ids
            assert result.statuses == [(i, "success") for i in ids]
            raw = result.values.to_decimal()
            for row, y in enumerate(couplings):
                finite, single, double = [
                    Decimal(raw[3 * row + k][0]) for k in range(3)
                ]
                assert abs(finite - y) < Decimal(tolerance)
                assert abs(single) < Decimal(tolerance) and abs(double) < Decimal(
                    tolerance
                )
                assert all(
                    abs(Decimal(raw[3 * row + k][1])) < Decimal(tolerance)
                    for k in range(3)
                )
                if arithmetic != "double":
                    assert finite != 1
                    assert abs((finite - 1) / (y - 1) - 1) < Decimal("2e-5")


@pytest.mark.parametrize("arithmetic,precision,tolerance", MODES)
def test_local_epsilon_factor_convolves_with_bubble_pole(
    backend, arithmetic, precision, tolerance
):
    dag, closed, _eps = build_epsilon_transition()
    assert dag.nodes[closed].rank == 0
    labels = dag.nodes[closed].output_labels
    assert {label.powers for label in labels} == {(0, 0, 0, 0, 0), (0, 0, 0, 0, 1)}
    options = {"arithmetic": arithmetic, "precision": precision}
    program = NativeCoefficientDAG(dag, output_nodes=(closed,), **options)
    names = [f"c{i}" for i in range(len(labels))]
    sectors = [
        next(names[i] for i, label in enumerate(labels) if label.powers[-1] == power)
        for power in range(2)
    ] + ["0"]
    reducer = backend.PolynomialPlan(2, sectors, names, **options)
    for rows in (1, 4, 0, 1):
        ids = [700 - i for i in range(rows)]
        coefficients = program.evaluate_batch(
            native_batch(backend, rows, 0, [], options, ids)
        )
        result = reducer.evaluate_batch(
            native_batch(
                backend,
                rows,
                8,
                [
                    [x, "0"]
                    for _ in ids
                    for x in ["0", "0", "0", "0", "0", "1", "0", "0"]
                ],
                options,
                ids,
            ),
            native_batch(
                backend,
                rows,
                2,
                [["0", "0"] for _ in ids for _ in range(2)],
                options,
                ids,
            ),
            native_batch(backend, rows, 1, [["1", "0"] for _ in ids], options, ids),
            coefficients,
        )
        # B0(-1,0,0)=2+1/eps. (-8+8eps)*B0 gives finite -8,
        # whereas silently omitting the epsilon transition would give -16.
        for row in range(rows):
            values = result.values.to_decimal()[3 * row : 3 * row + 3]
            for actual, expected in zip(values, (-8, -8, 0), strict=True):
                assert abs(Decimal(actual[0]) - expected) < Decimal(tolerance)
                assert abs(Decimal(actual[1])) < Decimal(tolerance)
