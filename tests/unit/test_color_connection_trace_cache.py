# SPDX-License-Identifier: 0BSD
"""Exactness and reuse of closed overlaps, independently of the cache key."""

from fractions import Fraction
from itertools import permutations

import pytest

from pyamplicol.color import connections as color


def _uncached_overlap(left, right):
    traces = list(right.traces) + [tuple(reversed(t)) for t in left.traces]
    right_by_q = {s.fundamental_label: s for s in right.open_strings}
    left_by_qbar = {s.antifundamental_label: s for s in left.open_strings}
    visited = set()
    for start in sorted(right_by_q):
        if start in visited:
            continue
        current, trace = start, []
        while current not in visited:
            visited.add(current)
            ket = right_by_q[current]
            bra = left_by_qbar[ket.antifundamental_label]
            trace.extend(ket.adjoint_labels)
            trace.extend(reversed(bra.adjoint_labels))
            current = bra.fundamental_label
        traces.append(tuple(trace))
    return color._simplify_trace_terms_nc_power(((Fraction(1), 0, tuple(traces)),))


def test_reuse_keeps_trace_orientation_and_returns_fresh_mappings():
    cache = color._closed_trace_overlap_nc_terms
    cache.cache_clear()
    tensor = color.ColorTensor(traces=((1, 2, 3),))
    expected = _uncached_overlap(tensor, tensor)
    assert color._literal_tensor_overlap_nc_terms(tensor, tensor) == expected
    renamed = color.ColorTensor(traces=((12, 13, 11),))
    actual = color._literal_tensor_overlap_nc_terms(renamed, renamed)
    assert actual == expected
    assert cache.cache_info().misses == 1
    assert cache.cache_info().hits == 1
    actual.clear()
    assert color._literal_tensor_overlap_nc_terms(tensor, tensor) == expected
    reversed_tensor = color.ColorTensor(traces=((3, 2, 1),))
    reflected = color._literal_tensor_overlap_nc_terms(tensor, reversed_tensor)
    assert reflected == _uncached_overlap(tensor, reversed_tensor)
    assert reflected != expected
    assert cache.cache_parameters()["maxsize"] == 65536
    assert cache.cache_info().currsize <= cache.cache_info().maxsize


@pytest.mark.parametrize(
    "left,right",
    (
        (color.ColorTensor(), color.ColorTensor()),
        (color.ColorTensor(traces=((),)), color.ColorTensor(traces=((),))),
        (color.ColorTensor(traces=((1,),)), color.ColorTensor(traces=((1,),))),
        (
            color.ColorTensor(traces=((1, 2), (3, 4))),
            color.ColorTensor(traces=((1, 3, 2, 4),)),
        ),
        (
            color.ColorTensor((color.OpenColorString(1, (), 2),)),
            color.ColorTensor((color.OpenColorString(1, (), 2),)),
        ),
        (
            color.ColorTensor(
                (color.OpenColorString(1, (5,), 2), color.OpenColorString(3, (), 4))
            ),
            color.ColorTensor(
                (color.OpenColorString(1, (), 4), color.OpenColorString(3, (5,), 2))
            ),
        ),
    ),
)
def test_full_laurent_series_and_closed_fundamental_pairings(left, right):
    assert color._literal_tensor_overlap_nc_terms(left, right) == _uncached_overlap(
        left, right
    )


def test_five_gluon_connected_entries_match_uncached_polynomials(monkeypatch):
    legs = tuple(color.ColorLeg(i, 8) for i in range(1, 6))
    tensors = [
        color.ColorTensor(traces=((1, *tail),)) for tail in permutations(range(2, 6))
    ]
    bra = color.ColorConnection(legs, (color.EmitGluon(1, -1), color.EmitGluon(2, -2)))
    ket = color.ColorConnection(legs, (color.EmitGluon(3, -1), color.EmitGluon(4, -2)))
    pairs = ((0, 0), (0, 1), (0, 23), (5, 17), (8, 12), (23, 23))
    images = [
        (
            color.apply_color_connection(tensors[i], bra),
            color.apply_color_connection(tensors[j], ket),
        )
        for i, j in pairs
    ]
    actual = [color.contract_connected_tensor_nc_terms(a, b) for a, b in images]
    monkeypatch.setattr(color, "_literal_tensor_overlap_nc_terms", _uncached_overlap)
    expected = [color.contract_connected_tensor_nc_terms(a, b) for a, b in images]
    assert actual == expected
    assert any(len(polynomial) > 1 for polynomial in actual)
