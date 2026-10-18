# SPDX-License-Identifier: 0BSD
"""Diagnostic only: varying tracked mass precision changes a real-mass I4 branch.
Requires Symbolica and the existing experimental _loop_reduction binding.
No UFO, graph generation, pyAmpliCol imports, input snapping, or integral formula.
"""

import _loop_reduction as native
from symbolica import E, Expression, S

options = dict(arithmetic="arbitrary", precision=80)


def batch(values, columns):
    return native.NativeBatch.from_decimal(values, 1, columns, **options)


def real(values):
    return batch([[str(value), "0"] for value in values], len(values))


def evaluator(values, inputs):
    state = Expression.evaluator_multiple(
        values, inputs, n_cores=1, jit_compile=False
    ).save()
    return native.CoefficientEvaluator(state, **options)


mass = S("probe::mass")
pole = evaluator([(mass * mass) ** E("1/2")], [mass]).evaluate_batch(real(["91.188"]))
masses = evaluator([E("0"), mass * mass, mass * mass, E("0")], [mass]).evaluate_batch(
    pole
)
reparsed = batch(masses.to_decimal(), 4)
assert all(equal for _, equal in masses.agreement_rows(reparsed, "0", "1e-200"))
shifts = real([500, 300, 0, 400, 1000, 0, 0, 0, 0, 0, 0, 0, 500, 0, 0, 500])
invariants = real(
    [0, 0, 0, -100000, 0, 0, 1000000, 0, 0, 1000000, 0, 0, -100000, 0, 0, 0]
)
scale = real([1000000])
plan = native.PolynomialPlan(4, ["1", "0", "0"], [], **options)
for label, values in [
    ("sqrt-square", masses),
    ("reparsed", reparsed),
    ("sqrt-square-repeat", masses),
]:
    result = plan.evaluate_batch(
        shifts, values, scale, batch([], 0), s_matrix=invariants
    )
    print(label, result.statuses, result.values.to_decimal()[0])
