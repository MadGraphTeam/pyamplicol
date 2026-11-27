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

The check is colour-blind and runs only for models with such a vertex. It
follows the singlet lines such a vertex emits (through colour-singlet
currents only, so an external Higgs at the vertex is not one) and asks
whether, within the coupling-order limits, one of them joins two leg sets
whose colour no sector of the lane carries: a quark-free gluon group and a
quark line (every mode), two gluon groups (every mode), or two parts with
quark lines (the compiled and eager modes, which do not build these trees:
also with no external gluon, ``u u~ > d d~ t t~``). The trees decide, not
the external legs.
"""

from __future__ import annotations

from collections.abc import Mapping
from itertools import combinations

from ..api.errors import GenerationError
from ..models.base import Model
from ..processes.ir import CanonicalProcessIR

_ADJOINT = 8
# The execution modes that build their trees by the generic DAG.
_DAG_MODES = frozenset({"compiled", "eager", None})


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
    execution_mode: str | None = None,
) -> None:
    """Raise ``SingletExchangeColourError`` for a request with such a tree.

    ``execution_mode`` (``"compiled"``, ``"eager"``, or ``None`` for the
    correlated lane and loop Borns, which build compiled trees) also refuses
    the trees those modes drop: a singlet from a vertex with gluons alone
    exchanged between two quark lines (``d d~ > t t~ g``), which the
    recurrence and on-the-fly modes serve.
    """

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
    carried = [orders for orders in order_sets if orders]
    vertex_orders = sorted(set.intersection(*carried)) if carried else []
    remedy = (
        " ".join(f"max_coupling_orders {{ {name} = 0 }}" for name in vertex_orders)
        if vertex_orders
        else "a zero limit on the coupling order of that vertex"
    )
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
    # The vertex can sit on internal gluons alone (two virtual gluons of two
    # quark lines fusing into the singlet, u u~ > d d~ t t~): the trees
    # decide, not the external gluons. Without a coloured leg there is no
    # colour to misrepresent.
    if not gluon_legs and len(open_legs) < 4:
        return
    limits = (
        {str(name).upper(): int(value) for name, value in max_coupling_orders.items()}
        if max_coupling_orders
        else None
    )
    marked = {
        (int(vertex.kind), tuple(vertex.particles)) for vertex in singlet_vertices
    }
    count = len(legs)
    full = (1 << count) - 1
    # reach[mask]: {species: {(coupling orders, on the singlet line of a
    # singlet-gluons vertex)}} of the currents that cover exactly the legs in
    # mask (colour-blind, within the limits).
    Entry = tuple[tuple[tuple[str, int], ...], bool]
    reach: dict[int, dict[int, set[Entry]]] = {}
    for index, pdg in enumerate(pdgs):
        reach[1 << index] = {pdg: {((), False)}}
    for size in range(2, count):
        for chosen in combinations(range(count), size):
            mask = sum(1 << index for index in chosen)
            currents: dict[int, set[Entry]] = {}
            low = mask & -mask
            sub = (mask - 1) & mask
            while sub:
                # Each unordered split once: the left side holds the lowest leg.
                if sub & low:
                    left_currents = reach.get(sub, {})
                    right_currents = reach.get(mask ^ sub, {})
                    for left, left_entries in left_currents.items():
                        for right, right_entries in right_currents.items():
                            for a, b, a_entries, b_entries in (
                                (left, right, left_entries, right_entries),
                                (right, left, right_entries, left_entries),
                            ):
                                for vertex in model.vertices_accepting(a, b):
                                    own = {
                                        str(name).upper(): int(value)
                                        for name, value in model.vertex_coupling_orders(
                                            vertex
                                        )
                                    }
                                    through = (
                                        int(vertex.kind),
                                        tuple(vertex.particles),
                                    ) in marked
                                    result = int(vertex.particles[2])
                                    # The flag follows the singlet line the
                                    # vertex emits: a colour-singlet result
                                    # of such a vertex, or of colour-singlet
                                    # inputs one of which carries it. A
                                    # coloured current drops it (an external
                                    # Higgs at the vertex, u c > u c g h).
                                    singlet_result = _colour(model, result) == 1
                                    a_singlet = _colour(model, a) == 1
                                    b_singlet = _colour(model, b) == 1
                                    for x, x_through in a_entries:
                                        for y, y_through in b_entries:
                                            total = _add(_add(dict(x), dict(y)), own)
                                            if _within(total, limits):
                                                carried = singlet_result and (
                                                    through
                                                    or (a_singlet and x_through)
                                                    or (b_singlet and y_through)
                                                )
                                                currents.setdefault(result, set()).add(
                                                    (
                                                        tuple(sorted(total.items())),
                                                        carried,
                                                    )
                                                )
                sub = (sub - 1) & mask
            if currents:
                reach[mask] = currents
    open_mask = sum(1 << index for index in open_legs)
    gluon_mask = sum(1 << index for index in gluon_legs)
    for mask, currents in reach.items():
        complement = full ^ mask
        if mask > complement:
            continue  # each split once
        other = reach.get(complement, {})
        for species, entries in currents.items():
            if _colour(model, species) != 1:
                continue
            for partner in (species, -species):
                for x, x_through in entries:
                    for y, y_through in other.get(partner, ()):
                        if not (x_through or y_through) or not _within(
                            _add(dict(x), dict(y)), limits
                        ):
                            continue
                        sides = (mask, complement)
                        quark_free = [side for side in sides if not side & open_mask]
                        gluon_sides = [side for side in quark_free if side & gluon_mask]
                        if gluon_sides and (
                            len(quark_free) == 1 or len(gluon_sides) == 2
                        ):
                            # A closed gluon trace beside an open line, or two
                            # closed traces: no colour-flow sector carries it.
                            gluons = [
                                process.legs[index].label
                                for index in gluon_legs
                                if gluon_sides[0] & (1 << index)
                            ]
                            raise SingletExchangeColourError(
                                f"process {process.process!r} is refused; set "
                                f"{remedy} to generate it without the trees "
                                "in which a colour singlet joins the gluons "
                                f"{gluons} to the rest through a vertex with "
                                "gluons alone: their colour holds a closed "
                                "gluon trace beside an open line or another "
                                "trace, which no colour-flow sector of this "
                                "version carries, so their value would be wrong"
                            )
                        if not quark_free and execution_mode in _DAG_MODES:
                            raise SingletExchangeColourError(
                                f"process {process.process!r} is refused in the "
                                f"{execution_mode or 'compiled'} mode: its "
                                "trees in which a colour singlet joins two "
                                "quark lines through a "
                                "vertex with gluons alone are not built there, "
                                "so its value would be wrong. Generate it in the "
                                "recurrence or on-the-fly mode, or set "
                                f"{remedy}"
                            )
