# SPDX-License-Identifier: 0BSD
"""Refuse trees whose colour needs a closed gluon trace beside an open line.

A model vertex that joins a colour singlet to gluons alone (the scalar-HEFT
``H g g``, ``H g g g`` and ``H g g g g`` effective interactions) lets a
singlet propagate between a pure-gluon part of a tree and a part that holds a
quark line: ``g g > t t~`` through ``g g -> H* -> t t~``,
``t t~ > t t~ g g``, ``u u~ > z g g`` through ``Z* -> Z H*``. The colour of
such a tree is a product of an open colour line and a separate closed trace
of the gluons, ``delta_ij tr(T^a T^b)``. The colour-flow sectors of this
version are open lines, single traces or singlets, so no sector carries that
product: the compiled and eager modes project it onto the open-line flows
(the squared Higgs term of ``g g > t t~`` came out 14/9 times too large),
the recurrence and on-the-fly modes drop it. Until the sectors exist,
generation refuses such a request in every mode, before any lowering.

The check is colour-blind and runs only for models with such a vertex: it
asks whether, within the coupling-order limits, one colour singlet can be the
current of a leg set holding a coloured non-adjoint leg and, at the same
time, of the complementary leg set, which holds gluons and no such leg.
"""

from __future__ import annotations

from collections.abc import Mapping
from itertools import combinations

from ..api.errors import GenerationError
from ..models.base import Model
from ..processes.ir import CanonicalProcessIR

_ADJOINT = 8


class SingletExchangeColourError(GenerationError):
    """A tree needs an open colour line times a closed gluon trace."""


def _colour(model: Model, pdg: int) -> int | None:
    try:
        return int(model.color_rep(int(pdg)))
    except (KeyError, NotImplementedError, TypeError, ValueError):
        return None


def _gluon_singlet_vertices(model: Model) -> tuple[object, ...]:
    """The model vertices with one colour singlet and coloured legs that are
    all adjoint or auxiliary (no fundamental-like representation)."""

    found = []
    for vertex in model.vertices:
        reps = [_colour(model, pdg) for pdg in vertex.particles]
        if any(rep is None for rep in reps):
            continue
        singlets = sum(1 for rep in reps if rep == 1)
        coloured = [rep for rep in reps if rep != 1]
        if (
            singlets == 1
            and len(coloured) == 2
            and all(abs(rep) == _ADJOINT for rep in coloured)
        ):
            found.append(vertex)
    return tuple(found)


def _within(orders: Mapping[str, int], limits: Mapping[str, int] | None) -> bool:
    if not limits:
        return True
    return all(orders.get(name, 0) <= limit for name, limit in limits.items())


def _add(left: Mapping[str, int], right: Mapping[str, int]) -> dict[str, int]:
    total = dict(left)
    for name, value in right.items():
        total[name] = total.get(name, 0) + value
    return total


def require_representable_singlet_exchange(
    process: CanonicalProcessIR,
    *,
    model: Model,
    max_coupling_orders: Mapping[str, int] | None,
) -> None:
    """Raise ``SingletExchangeColourError`` for a request with such a tree."""

    singlet_vertices = _gluon_singlet_vertices(model)
    if not singlet_vertices:
        return
    # The orders every such vertex carries (HIG for the scalar HEFT; the
    # H g g g vertex also carries QCD, which must not be named).
    order_sets = [
        {
            str(name).upper()
            for name, value in model.vertex_coupling_orders(vertex)
            if value
        }
        for vertex in singlet_vertices
    ]
    vertex_orders = sorted(set.intersection(*order_sets)) or [
        "<the order of that vertex>"
    ]
    legs = tuple(process.legs)
    pdgs: list[int] = []
    for leg in legs:
        if leg.outgoing_pdg is None:
            return
        pdgs.append(int(leg.outgoing_pdg))
    reps = [_colour(model, pdg) for pdg in pdgs]
    if any(rep is None for rep in reps):
        return
    open_legs = [index for index, rep in enumerate(reps) if rep not in (1, _ADJOINT)]
    gluon_legs = [index for index, rep in enumerate(reps) if rep == _ADJOINT]
    if not open_legs or not gluon_legs:
        return
    limits = (
        {str(name).upper(): int(value) for name, value in max_coupling_orders.items()}
        if max_coupling_orders
        else None
    )
    count = len(legs)
    full = (1 << count) - 1
    # reach[mask]: {species: set of frozen coupling orders} of currents that
    # cover exactly the legs in mask (colour-blind, within the limits).
    reach: dict[int, dict[int, set[tuple[tuple[str, int], ...]]]] = {}
    for index, pdg in enumerate(pdgs):
        reach[1 << index] = {pdg: {()}}
    for size in range(2, count):
        for chosen in combinations(range(count), size):
            mask = sum(1 << index for index in chosen)
            currents: dict[int, set[tuple[tuple[str, int], ...]]] = {}
            low = mask & -mask
            sub = (mask - 1) & mask
            while sub:
                # Each unordered split once: the left side holds the lowest leg.
                if sub & low:
                    other = mask ^ sub
                    left_currents = reach.get(sub, {})
                    right_currents = reach.get(other, {})
                    for left, left_orders in left_currents.items():
                        for right, right_orders in right_currents.items():
                            for a, b, a_orders, b_orders in (
                                (left, right, left_orders, right_orders),
                                (right, left, right_orders, left_orders),
                            ):
                                for vertex in model.vertices_accepting(a, b):
                                    vertex_orders = {
                                        str(name).upper(): int(value)
                                        for name, value in model.vertex_coupling_orders(
                                            vertex
                                        )
                                    }
                                    result = int(vertex.particles[2])
                                    for x in a_orders:
                                        for y in b_orders:
                                            total = _add(
                                                _add(dict(x), dict(y)), vertex_orders
                                            )
                                            if _within(total, limits):
                                                currents.setdefault(result, set()).add(
                                                    tuple(sorted(total.items()))
                                                )
                sub = (sub - 1) & mask
            if currents:
                reach[mask] = currents
    open_mask = sum(1 << index for index in open_legs)
    for mask, currents in reach.items():
        complement = full ^ mask
        if not mask & open_mask or complement & open_mask:
            continue
        if not any(complement & (1 << index) for index in gluon_legs):
            continue
        other = reach.get(complement, {})
        for species, orders in currents.items():
            if _colour(model, species) != 1:
                continue
            for partner in (species, -species):
                for x in orders:
                    for y in other.get(partner, ()):
                        if _within(_add(dict(x), dict(y)), limits):
                            gluons = [
                                process.legs[index].label
                                for index in gluon_legs
                                if complement & (1 << index)
                            ]
                            raise SingletExchangeColourError(
                                f"process {process.process!r}: its coupling orders "
                                "admit a tree in which a colour singlet is "
                                f"exchanged between the gluons {gluons} and the "
                                "quark line(s), through a vertex that joins a "
                                "singlet to gluons alone. The colour of such a "
                                "tree is an open colour line times a closed gluon "
                                "trace, which no colour-flow sector of this "
                                "version carries, so its value would be wrong. "
                                "To generate the process without these trees, "
                                "set the coupling order of that vertex to zero: "
                                + " ".join(
                                    f"max_coupling_orders {{ {name} = 0 }}"
                                    for name in vertex_orders
                                )
                            )
