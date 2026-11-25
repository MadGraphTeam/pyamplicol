# SPDX-License-Identifier: 0BSD
"""The threshold rule's review cases (``loops.v2.checks``, ``induced``,
``goldstone``): each is a reproduction of a defect of the first threshold
head, run through the production judges with scripted carrier outputs.

* **A cancelled colour norm is measured, not zero**: ||x||_G for G = [[9,
  3], [3, 1]] and x = (1, -2.999999997) is 3e-9 (the form's terms are of
  order 9), also on a rank-deficient metric of four colour flows.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

pytestmark = pytest.mark.loop_fast


# ------------------------------------------------ 2. the colour norm


def _numbers():
    from pyamplicol.loops.v2.assemble import Precision, _Numbers

    return _Numbers(Precision.double())


def test_a_cancelled_colour_norm_is_measured():
    """G = [[9, 3], [3, 1]]: ||x||_G = |3 x_1 + x_2|; for the pole vector
    (1, -2.999999997) the carrier's form cancels from terms of order 9 to
    9e-18, where the norm is 3e-9 (never zero); a rank-deficient metric of
    four colour flows (G = W^T W, W of rank 3) likewise."""

    from pyamplicol.loops.v2.induced import g_norm

    numbers = _numbers()
    gram = [[9 + 0j, 3 + 0j], [3 + 0j, 1 + 0j]]
    pole = [1 + 0j, -2.999999997 + 0j]
    exact = abs(3 * Fraction(1) + Fraction(-2.999999997))
    assert g_norm(pole, gram, numbers) == pytest.approx(float(exact), rel=1e-12)
    assert g_norm([1e-6 + 0j, 0j], gram, numbers) == pytest.approx(3e-6)
    # Four flows spanning three colour dimensions (SU(3) colour-flow
    # redundancy): W columns w1, w2, w3, w4 = w1 + w2 - w3.
    w = [[3, 1, 1, 3], [1, 3, 1, 3], [1, 1, 3, -1]]
    flows = [
        [sum(w[r][i] * w[r][j] for r in range(3)) for j in range(4)] for i in range(4)
    ]
    metric = [[complex(value) for value in row] for row in flows]
    near_null = [1 + 0j, 1 + 0j, -1 + 0j, -1 + 2e-9 + 0j]
    found = g_norm(near_null, metric, numbers)
    exact_form = sum(
        Fraction(near_null[i].real)
        * Fraction(flows[i][j])
        * Fraction(near_null[j].real)
        for i in range(4)
        for j in range(4)
    )
    assert found > 0
    assert found == pytest.approx(float(exact_form) ** 0.5, rel=1e-9)
