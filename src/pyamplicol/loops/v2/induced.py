# SPDX-License-Identifier: 0BSD
"""Loop-induced |A_loop|^2 in amplitude mode, route R1 (M-LIT LIT-AMP).

A loop-induced request has no Born amplitude within its coupling-order
limits (m-lit PLAN §1.2), so there is no bra to interfere the loop with: the
one-loop amplitude is kept as a colour vector on the amplitude basis T of
the request (``colour.AmplitudeBasis``, LIT-COL) and squared with the
full-colour metric G (PLAN §2.a.2):

    a_{l,h,t} = (i / 16 pi^2) sum_f Omega_f[N_{f,l,h,t}] + A^CT_{l,h,t},
    |A|^2_s   = (1 / avg) sum_h sum_{(l,l') in s} kappa_{ll'}
                    Re sum_{t,t'} conj(a_{l,h,t}) G_{tt'} a_{l',h,t'},

with kappa = 1 for l = l' and 2 for l != l' (loop x loop sectors: the pair
(l, l') of a sector has l <= l'), avg the slice's spin/colour average and
symmetry factor (``Normalisation.of``, unchanged), G at N_c = 3 (full colour
only, RULED Q8). The amplitude numerator of family f, helicity row h and
basis element t is today's family numerator with the leaf weight
w_s c_{c(s),t} instead of w_s U0_c(h): same tries, contents and kernels.

**Route R1** (RULED Q14 = (a)): schedule B with one-hot "resolved" columns
(h0, t), whose seed is c_{c,t} on row h0 only (the native plan writes them
as ``column_rows = {h0}`` with unit Born components; ``plan_export``). This
module is the Python oracle of that route (the reference executor) and of
the amplitude assembly and the canonical squaring the native carrier runs.

**Canonical squaring order** (DESIGN §7.10): sectors in order, their pairs
(l, l') in order, then helicity rows h in plan order, then t, then t'
(``square``). Laurent coefficients convolve as [finite, 1/eps, 1/eps^2] =
[a0^dag G b0, a0^dag G b1 + a1^dag G b0, a0^dag G b2 + a1^dag G b1 +
a2^dag G b0]: the finite part of |a|^2 is exact only if the amplitude's
poles vanish (its O(eps) terms are not computed), which the finiteness
diagnostic checks (PLAN §2.a.7 "Pole shape").

**Exact zeros** (RULED Q13, relaxed by the USER ~22:39 for zeros the
engine's exact algebra proves): two mechanisms, never a physics rule
(Furry, C-parity, Landau-Yang, J_z are never assumed). (1) The colour zero,
by colour algebra alone: at a requested loop order no seed class has a
nonzero colour coefficient at N_c = 3 and no counterterm ket carries a
colour tensor (``bind``: the classes' coefficients vanish, or no family is
routed because every loop has a single coloured attachment, Tr T^a = 0 in
any model; ``LoopSlice.colour_zero_orders``). (2) The fold zero (M-LIT
lit-fold, ``fold``): the exact test certifies chains exactly proportional
and their combined weights cancel exactly, so a loop order (or the whole
request) is left with no chain and no counterterm ket (``StoredAmplitude.
fold_zero``: the certificate, its failure probability and bound; e.g.
g g > a a a and g g > h a). Every other zero is evaluated numerically and
reported within its absolute estimate.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Any

from . import reference_executor as rx
from .families import Orders
from .wide import Wide, magnitude

# The interference of a loop-induced result (the artifact metadata value).
LOOP_INDUCED_INTERFERENCE = "conj(loop)*loop"


def loop_sectors(
    loop_orders: Iterable[Orders],
) -> tuple[tuple[Orders, frozenset[tuple[Orders, Orders]]], ...]:
    """The loop x loop sectors of a loop-induced request (m-lit PLAN §1.3):
    per squared order l + l' its pairs (l, l') with l <= l' (sorted), in
    squared-order order. The pair type is the Born-interfered (Born, loop)
    pair's: its first slot holds the conjugated loop order."""

    from .families import add_orders

    ordered = sorted(set(loop_orders))
    sectors: dict[Orders, set[tuple[Orders, Orders]]] = {}
    for i, left in enumerate(ordered):
        for right in ordered[i:]:
            sectors.setdefault(add_orders(left, right), set()).add((left, right))
    return tuple(
        (sector, frozenset(pairs)) for sector, pairs in sorted(sectors.items())
    )


def bind(slice_: Any, *, generation: Any = None) -> None:
    """Complete a generated loop-induced slice: its amplitude basis
    (``LoopSlice.amplitude``: the seed classes' literal tensors and the
    counterterm kets', ``colour.amplitude_basis``) and its exact colour-zero
    loop orders (``LoopSlice.colour_zero_orders``).

    A requested loop order is an exact colour zero when no counterterm ket
    carries a colour tensor there and no seed class read at that order has
    a nonzero coefficient cell: either the order's classes all vanish by
    the colour algebra (c_{c,t} = 0 at N_c = 3) or no family routes it at
    all, which is accepted only when the field-level family recursion at
    that order drops a loop for a single coloured attachment (Tr T^a = 0,
    ``COLOUR_ZERO_REJECTION``, the mechanism of ``reachable_loop_orders``).
    Any other order without a loop amplitude is refused
    (``no-loop-amplitude``): never a silent zero."""

    from .colour import amplitude_basis
    from .families import LoopOrderSelection, add_orders
    from .native_cells import _DegreeKeys

    request = slice_.request
    keys = _DegreeKeys(slice_, orbits=False)
    kets = {order for order, found in keys.counterterms.items() if found}
    tensors = sorted(
        {tensor for found in keys.counterterms.values() for tensor, _p in found}
    )
    basis = amplitude_basis(slice_.table, tensors)
    slice_.amplitude = basis
    requested = {
        add_orders(tuple(orders.items())) for orders in request.exact_loop_orders
    }
    live = {
        order
        for c, row in enumerate(basis.cells_at_three())
        if row
        for order in slice_.table.orders[c]
    }
    families = slice_.families
    routed = {
        add_orders(*(position.orders for position in families.routing(closure)[1]))
        for group in (families.families, families.scaleless_families)
        for family in group.values()
        for closure in family.closures
    }
    zero = requested - live - kets
    unrouted = sorted(zero - routed)
    if unrouted:
        from pyamplicol.processes.model import build_model_process_ir

        from .assemble import COLOUR_ZERO_REJECTION, _field_level_families

        process = build_model_process_ir(
            request.process, slice_.compiled.ir, color_accuracy="full"
        )
        for order in unrouted:
            found = _field_level_families(
                slice_.data,
                process,
                slice_.loop_catalogue,
                LoopOrderSelection(frozenset(request.corrections), frozenset({order})),
                request,
                slice_.native if generation is not None else None,
            )
            if found.families or not any(
                entry.reason == COLOUR_ZERO_REJECTION for entry in found.rejected
            ):
                from .refusals import LoopRequestUnsupported

                raise LoopRequestUnsupported(
                    "no-loop-amplitude",
                    f"{request.process!r}: no loop amplitude at the loop order "
                    f"{dict(order)} (no family, no counterterm ket and no exact "
                    "colour zero)",
                )
    slice_.colour_zero_orders = frozenset(zero)


@dataclass(frozen=True)
class StoredAmplitude:
    """The amplitude basis of a stored loop-induced process (its native
    record's ``amplitude``, ``amplitude_record``): what the native route
    reads of ``colour.AmplitudeBasis`` (the basis size, the full-colour
    metric at N_c = 3, the elements the counterterm kets carry), the map of
    the tree program's counterterm ket components onto the basis
    (``ket_map``), the helicity rows of the amplitude-mode plan, the exact
    colour-zero loop orders (RULED Q13's colour-zero record) and whether the
    whole request is an exact colour zero (``colour_zero``,
    ``AmplitudeBasis.colour_zero`` at generation: no nonzero coefficient
    cell and no counterterm ket; the record keeps no cells, so it stores
    the generation's answer)."""

    size: int
    metric: tuple[tuple[Any, ...], ...]
    counterterms: tuple[int, ...]
    ket_map: tuple[tuple[int, int, Orders, int], ...]
    rows: tuple[rx.Row, ...]
    colour_zero_orders: frozenset[Orders]
    colour_zero: bool
    # The declared observables (``induced_observables.declare``): the
    # resolved ``CorrelatorConfig`` and each colour history's matrix on the
    # basis; None without a declaration.
    correlators: Any = None
    # The fold zero (M-LIT lit-fold, ``fold``; module docs "Exact zeros"):
    # ``exact_fold_zero`` (the whole request), ``fold_zero_loop_orders`` and
    # the ``certificate`` (prime, seed, points, degree bound, identities,
    # failure probability and bound); None without a fold zero.
    fold_zero: Mapping[str, Any] | None = None

    def __len__(self) -> int:
        return self.size

    def metric_at_three(self) -> tuple[tuple[Any, ...], ...]:
        return self.metric

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> StoredAmplitude:
        from pyamplicol.color.connections import ExactColorCoefficient

        from .induced_observables import correlators_from_record

        def orders(value) -> Orders:
            return tuple((str(name), int(power)) for name, power in value)

        return cls(
            int(record["size"]),
            tuple(
                tuple(
                    ExactColorCoefficient(Fraction(re), Fraction(im)) for re, im in row
                )
                for row in record["metric"]
            ),
            tuple(int(t) for t in record["counterterms"]),
            tuple(
                (int(t), int(k), orders(order), int(nc))
                for t, k, order, nc in record["ket_map"]
            ),
            tuple(tuple(enumerate(int(h) for h in row)) for row in record["rows"]),
            frozenset(orders(order) for order in record["colour_zero_orders"]),
            bool(record["colour_zero"]),
            correlators_from_record(record["correlators"])
            if "correlators" in record
            else None,
            dict(record["fold_zero"]) if "fold_zero" in record else None,
        )


def amplitude_record(slice_: Any, exported: Any) -> dict[str, Any]:
    """The amplitude record of a stored loop-induced process
    (``native_process.NativeProcess.export``; ``StoredAmplitude``): exact
    rationals as strings, loop orders as [name, power] lists; no path, user
    or host enters it."""

    from .induced_observables import correlators_record

    basis = slice_.amplitude

    def orders(value: Orders) -> list[list[Any]]:
        return [[name, power] for name, power in value]

    mapping = (
        ket_map(slice_, exported.trees)
        if exported.trees.program.get("counterterms")
        else []
    )
    return {
        "size": len(basis),
        "metric": [
            [[str(cell.real), str(cell.imag)] for cell in row]
            for row in basis.metric_at_three()
        ],
        "counterterms": list(basis.counterterms),
        "ket_map": [[t, k, orders(order), nc] for t, k, order, nc in mapping],
        "rows": [[h for _leg, h in row] for row in exported.rows],
        "colour_zero_orders": [
            orders(order) for order in sorted(slice_.colour_zero_orders)
        ],
        # The request's exact colour zero (``AmplitudeBasis.colour_zero``):
        # one colour-zero order beside live ones does not make it.
        "colour_zero": basis.colour_zero,
        # Declared observables only (``induced_observables.declare``): a
        # record without them keeps its bytes.
        **(
            {"correlators": correlators_record(declared)}
            if (declared := getattr(slice_, "amplitude_correlators", None)) is not None
            else {}
        ),
        # A fold zero only (M-LIT lit-fold): a record without one keeps its
        # bytes.
        **({"fold_zero": zero} if (zero := fold_zero_record(slice_)) else {}),
    }


def fold_zero_record(slice_: Any) -> dict[str, Any] | None:
    """The fold-zero record of a folded loop-induced slice (``fold``; module
    docs "Exact zeros"): whether the whole request is an exact fold zero,
    its exact fold-zero loop orders and the certificate; None when the fold
    left no exact zero."""

    folded = getattr(slice_, "fold", None)
    if folded is None:
        return None
    verdict = folded.verdict
    if not verdict.exact_zero and not verdict.zero_orders:
        return None
    return {
        "exact_fold_zero": verdict.exact_zero,
        "fold_zero_loop_orders": [
            [[name, power] for name, power in order] for order in verdict.zero_orders
        ],
        "certificate": verdict.certificate(),
    }


def kappa(pair: tuple[Orders, Orders]) -> int:
    """1 for a diagonal pair (l, l), 2 (2 Re) for l != l'."""

    return 1 if pair[0] == pair[1] else 2


def column_labels(rows: Sequence[rx.Row], size: int) -> tuple[tuple[rx.Row, int], ...]:
    """The R1 columns (h0, t), row-major: column r * T + t."""

    return tuple((row, t) for row in rows for t in range(size))


class AmplitudeSeeds:
    """R1 leaf seeds of the Python reference executor (an ``rx.SeedSource``):
    column (h0, t) of row h0 carries sum_c x_c c_{c,t} of the skeleton's
    seed combination; every other (row, column) is zero, so column (h0, t)
    collects the amplitude numerator of row h0 alone."""

    def __init__(self, slice_: Any, rows: Sequence[rx.Row], numbers: Any):
        basis = slice_.amplitude
        self.size = len(basis)
        self.rows = tuple(rows)
        self.columns = len(self.rows) * self.size
        self.class_of = slice_.class_of
        self._numbers = numbers
        self._cells = [
            [(t, numbers.colour(value, 0)) for t, value in row]
            for row in basis.cells_at_three()
        ]
        self._cache: dict[Any, dict[rx.Row, tuple[Any, ...]]] = {}

    def _vector(self, combination) -> list[Any]:
        numbers = self._numbers
        out = [numbers.zero] * self.size
        for c, x in combination:
            weight = numbers.pair(numbers.real(x.real), numbers.real(x.imag))
            for t, cell in self._cells[c]:
                out[t] = out[t] + weight * cell
        return out

    def seed(self, skeleton, contents):
        reading = rx._reading(skeleton, contents)
        combination = self.class_of.get(reading)
        if combination is None:
            raise KeyError("reading without a seed class")
        key = tuple(combination)
        found = self._cache.get(key)
        if found is None:
            vector = self._vector(combination)
            zero = self._numbers.zero
            found = {}
            for r, row in enumerate(self.rows):
                values = [zero] * self.columns
                values[r * self.size : (r + 1) * self.size] = vector
                found[row] = tuple(values)
            self._cache[key] = found
        return (key, skeleton.orders), found


def counterterm_kets(
    slice_: Any, site_vectors: Mapping[rx.Row, Mapping], numbers: Any, width: int
) -> dict[tuple[Orders, rx.Row], list[list[Any]]]:
    """The counterterm amplitude A^CT_{l,h,t} per (loop order, row): the CT
    program's per-row colour vectors (``_PointEvaluation.site_vectors``:
    (component, Laurent power, loop order) -> {(literal tensor, N_c power):
    value}, coefficients and 1/sqrt(2) powers folded) on the amplitude
    basis at N_c = 3, its components summed (the R2 and UV parts are not
    additive in a square). Per (l, h): T lists of ``width`` Laurent
    coefficients [finite, 1/eps, 1/eps^2]."""

    basis = slice_.amplitude
    index = {tensor: t for t, tensor in enumerate(basis.tensors)}
    three = numbers.real(3)
    zero = numbers.zero
    out: dict[tuple[Orders, rx.Row], list[list[Any]]] = {}
    for row, vectors in site_vectors.items():
        for (_component, power, order), vector in vectors.items():
            k = -power
            if k >= width:
                continue
            ket = out.get((order, row))
            if ket is None:
                ket = out[(order, row)] = [[zero] * width for _ in basis.tensors]
            for (tensor, nc), value in vector.items():
                t = index.get(tensor)
                if t is None:
                    raise KeyError(
                        f"a counterterm ket tensor {tensor!r} outside the amplitude "
                        "basis (colour.amplitude_basis of the slice's CT tensors)"
                    )
                ket[t][k] = ket[t][k] + value * three**nc
    return out


def bare_amplitudes(
    families: Mapping[tuple[Any, Orders, tuple[rx.Row, int]], Any],
    size: int,
    numbers: Any,
    width: int,
) -> dict[tuple[Orders, rx.Row], list[list[Any]]]:
    """a_bare_{l,h,t} = (i/16 pi^2) sum_f Omega_f per (loop order, row) from
    the reduced lanes (family, loop order, (row, t)), families summed in
    sorted lane order (the Laurent ``coefficients`` of each lane)."""

    from .conventions import LOOP_FACTOR_DENOMINATOR

    factor = numbers.pair(0, 1) * (
        1 / (LOOP_FACTOR_DENOMINATOR * numbers.pi * numbers.pi)
    )
    zero = numbers.zero
    sums: dict[tuple[Orders, rx.Row], list[list[Any]]] = {}
    for (_family, order, (row, t)), value in sorted(families.items(), key=_lane_key):
        amplitude = sums.get((order, row))
        if amplitude is None:
            amplitude = sums[(order, row)] = [[zero] * width for _ in range(size)]
        cell = amplitude[t]
        for k, coefficient in enumerate(value.coefficients[:width]):
            cell[k] = cell[k] + coefficient
    return {
        key: [[factor * z for z in cell] for cell in amplitude]
        for key, amplitude in sums.items()
    }


def _lane_key(item):
    (family, order, (row, t)), _value = item
    return (family, order, row, t)


def add_amplitudes(*parts: Mapping, numbers: Any, size: int, width: int) -> dict:
    """The sum of per-(order, row) amplitude vectors (missing entries zero)."""

    zero = numbers.zero
    out: dict = {}
    for part in parts:
        for key, vector in part.items():
            total = out.get(key)
            if total is None:
                total = [[zero] * width for _ in range(size)]
            # The same sums, entry by entry, as list comprehensions.
            if width == 1:
                out[key] = [
                    [entries[0] + vector[t][0]] for t, entries in enumerate(total)
                ]
            else:
                out[key] = [
                    [a + b for a, b in zip(entries, vector[t], strict=False)]
                    for t, entries in enumerate(total)
                ]
    return out


def metric(slice_: Any, numbers: Any) -> list[list[Any]]:
    """G_{tt'} = <t|t'> at N_c = 3 in the carrier (real symmetric)."""

    return [
        [numbers.colour(cell, 0) for cell in row]
        for row in slice_.amplitude.metric_at_three()
    ]


def square(
    amplitudes: Mapping[tuple[Orders, rx.Row], Sequence[Sequence[Any]]],
    gram: Sequence[Sequence[Any]],
    sectors: Sequence[tuple[Orders, frozenset[tuple[Orders, Orders]]]],
    rows: Sequence[rx.Row],
    width: int,
    numbers: Any,
    average: Any,
) -> dict[Orders, tuple[Any, ...]]:
    """|A|^2 per sector and Laurent coefficient in the canonical order
    (module docstring): sectors, pairs, rows h, t, t'; per coefficient k
    sum_{i+j=k} Re(a_{l,i}^dag G a_{l',j}) times kappa, divided by
    ``average``."""

    zero = numbers.zero
    real_zero = numbers.real(0)
    size = len(gram)
    out: dict[Orders, tuple[Any, ...]] = {}
    for sector, pairs in sectors:
        totals = [real_zero] * width
        for pair in sorted(pairs):
            left, right = pair
            weight = kappa(pair)
            for row in rows:
                a = amplitudes.get((left, row))
                b = amplitudes.get((right, row))
                if a is None or b is None:
                    continue
                for k in range(width):
                    total = zero
                    for i in range(k + 1):
                        j = k - i
                        for t in range(size):
                            inner = zero
                            for u in range(size):
                                inner = inner + gram[t][u] * b[u][j]
                            total = total + a[t][i].conjugate() * inner
                    totals[k] = totals[k] + weight * total.real
        out[sector] = tuple(value / average for value in totals)
    return out


def rows_of(evaluation: Any) -> tuple[rx.Row, ...]:
    """The helicity rows of a point evaluation in plan order (the product of
    the legs' helicities, ``plan_export.born_rows``): the native executor's
    rows, else those of the point's counterterm vectors."""

    rows = getattr(evaluation, "amplitude_rows", None)
    return tuple(evaluation.site_vectors) if rows is None else rows


def finish(evaluation: Any, retest: str | None) -> Any:
    """Dress (schedule B, R1 seeds), reduce and assemble a loop-induced point
    (``_PointEvaluation.finish`` of an amplitude-mode slice)."""

    from .poles import splits

    if splits(evaluation.mode):
        raise ValueError(
            "a loop-induced result admits the pole selections 'all' and 'none' "
            "only: its UV and IR parts are not additive in |A|^2 (m-lit PLAN "
            "§2.a.7)"
        )
    slice_ = evaluation.slice
    rows = rows_of(evaluation)
    labels = column_labels(rows, len(slice_.amplitude))
    if not slice_.plan.schedules:
        # An exact colour zero at every order: no family to dress.
        evaluation.set_lanes({}, None if retest is None else {})
    else:
        seeds = AmplitudeSeeds(slice_, rows, evaluation.numbers)
        execution = evaluation.dress(seeds=seeds)
        evaluation._reduce(execution.numerators, retest, columns=labels)
        # The term scale's numerator coefficients (``term_values``).
        evaluation.amplitude_numerators = execution.numerators
    evaluation._assemble()
    return evaluation


def read_native(
    evaluation: Any, output: Mapping, index: int, exported: Any, carrier, numbers
) -> None:
    """Read the native amplitude sum of point ``index`` of an amplitude-mode
    evaluation (``NativeExecutor.reduce``): per (loop order, row) the bare
    amplitude vectors (``native_bare``), with a check their re-test budget
    (``native_budget``: (i/16 pi^2) sum_f |delta Omega_f| per t and k) and,
    when the executor formed it, the term scale (``native_terms``,
    ``term_values``); binary64 squares natively (``native_square``). A row
    selection's output carries its kept rows only (``amplitude_rows``, the
    plan rows in order; lit-dress (H)): those are the evaluation's rows."""

    size = exported.amplitude
    kept = output.get("amplitude_rows")
    rows = (
        tuple(exported.rows) if kept is None else tuple(exported.rows[r] for r in kept)
    )
    columns = len(rows) * size

    from .plan_export import _double_pairs

    def vectors(slots, read):
        out = {}
        for o, order in enumerate(exported.orders):
            for r, row in enumerate(rows):
                base = o * columns + r * size
                cells = slots[base : base + size]
                if len(cells) != size:
                    raise IndexError("a native amplitude output misses slots")
                if read is _double_pairs:
                    # binary64: a finite-part slot ([[re, im]]) without a call
                    out[(order, row)] = [
                        [complex(float(cell[0][0]), float(cell[0][1]))]
                        if len(cell) == 1
                        else _double_pairs(cell)
                        for cell in cells
                    ]
                else:
                    out[(order, row)] = [read(cell) for cell in cells]
        return out

    # (An empty amplitude basis, an exact colour zero, has no slot.)
    amplitudes = output.get("amplitudes")
    slots = [] if amplitudes is None else amplitudes[index]
    kets = output.get("counterterm_kets")
    pending = (
        carrier is _double_pairs
        and kets is not None
        and size > 0
        and len(set(exported.orders)) == len(exported.orders)
    )
    if pending:
        # binary64 with counterterm kets: the vectors are formed on first
        # read, |A|^2 natively from the same outputs (``native_squares``).
        found = evaluation.__dict__
        found.pop("native_bare", None)
        found["_pending_native_bare"] = _formed(lambda: vectors(slots, carrier))
        found["_native_amplitudes"] = (slots, kets[index])
    else:
        evaluation.native_bare = vectors(slots, carrier)
    # Magnitudes: binary64 floats, or exponent-safe in arbitrary precision
    # (``loops.v2.wide``; a 500-digit budget is far below binary64's range).
    size_of = (
        (lambda values: [Wide.of(x) for x in values])
        if numbers.wide
        else (lambda values: [float(x) for x in values])
    )
    budget = output.get("amplitude_budget")
    evaluation.native_budget = (
        None if budget is None else vectors(budget[index], size_of)
    )
    terms = output.get("amplitude_scale")
    evaluation.native_terms = None if terms is None else vectors(terms[index], size_of)
    evaluation.native_square = numbers.double
    evaluation.amplitude_rows = rows
    if kets is not None:

        def form_kets(values=kets[index]):
            return native_kets(
                evaluation.slice,
                exported,
                carrier(values),
                numbers,
                width_of(evaluation),
                rows,
            )

        if pending:
            evaluation.__dict__.pop("native_kets", None)
            evaluation.__dict__["_pending_native_kets"] = _formed(form_kets)
        else:
            evaluation.native_kets = form_kets()


def width_of(evaluation: Any) -> int:
    """Laurent coefficients per value: [finite, 1/eps, 1/eps^2], or finite."""

    return 3 if evaluation.poles else 1


def ket_map(slice_: Any, trees: Any) -> list[tuple[int, int, Orders, int]]:
    """Per counterterm ket component of a native tree program (its layout
    (ket tensor, vector, N_c power), ``native_trees._counterterm_program``)
    the amplitude basis element of its tensor, the Laurent index of its
    vector's epsilon power, the vector's loop orders and its N_c power."""

    basis = {tensor: t for t, tensor in enumerate(slice_.amplitude.tensors)}
    layout = trees.program["counterterms"]["ket"]
    out = []
    for tensor, vector, nc_power in layout:
        _component, power, order = trees.ket_vectors[vector]
        literal = trees.ket_tensors[tensor]
        t = basis.get(literal)
        if t is None:
            raise KeyError(
                f"a native counterterm ket tensor {literal!r} outside the "
                "amplitude basis"
            )
        out.append((t, -power, order, nc_power))
    return out


def _ket_mapping(slice_: Any, exported: Any) -> Sequence[tuple[int, int, Orders, int]]:
    """``ket_map`` of a native process (its recorded map, else formed once
    per exported plan)."""

    mapping = getattr(slice_.amplitude, "ket_map", None)
    if mapping is None:
        mapping = exported.__dict__.get("_ket_map")
    if mapping is None:
        mapping = exported.__dict__["_ket_map"] = ket_map(slice_, exported.trees)
    return mapping


def _formed(make: Callable[[], Any]) -> Any:
    from .assemble import _Formed

    return _Formed(make)


def native_squares(evaluations: Sequence[Any], exported: Any) -> None:
    """|A|^2 of the binary64 points of a batch whose amplitude and
    counterterm-ket vectors are pending (``read_native``), in one native call
    (``induced_squares``: the vectors ``add_amplitudes`` forms from the same
    executor outputs, squared as ``native_square`` squares them, bitwise),
    kept as each point's ``native_squared`` for ``assemble``."""

    points = [e for e in evaluations if "_native_amplitudes" in e.__dict__]
    if not points:
        return
    first = points[0]
    slice_, numbers = first.slice, first.numbers
    width = width_of(first)
    rows = rows_of(first)
    size = len(slice_.amplitude)
    mapping = _ket_mapping(slice_, exported)
    orders = {order: o for o, order in enumerate(exported.orders)}
    three = numbers.real(3)
    powers: dict[int, Any] = {}
    entries = []
    for j, (t, k, order, nc) in enumerate(mapping):
        if k >= width:
            continue
        power = powers.get(nc)
        if power is None:
            power = powers[nc] = three**nc
        entries.append((j, t, k, orders.setdefault(order, len(orders)), power))
    squared_orders = sorted(
        {order for _sector, pairs in slice_.sectors for pair in pairs for order in pair}
    )
    slot = {order: k for k, order in enumerate(squared_orders)}
    gram = metric(slice_, numbers)
    found = slice_.native.induced_squares(
        [
            (amplitudes, kets, float(e.average))
            for e in points
            for amplitudes, kets in (e.__dict__.pop("_native_amplitudes"),)
        ],
        len(rows),
        size,
        width,
        len(exported.orders),
        (len(orders), len(mapping), entries),
        [orders.get(order) for order in squared_orders],
        [[complex(x).real, complex(x).imag] for line in gram for x in line],
        [
            sorted((slot[left], slot[right]) for left, right in pairs)
            for _sector, pairs in slice_.sectors
        ],
    )
    for evaluation, squares in zip(points, found, strict=True):
        evaluation.native_squared = {
            sector: tuple(totals)
            for (sector, _pairs), totals in zip(slice_.sectors, squares, strict=True)
        }


def native_kets(
    slice_: Any,
    exported: Any,
    values: Sequence[Any],
    numbers: Any,
    width: int,
    rows: Sequence[rx.Row] | None = None,
) -> dict[tuple[Orders, rx.Row], list[list[Any]]]:
    """A^CT per (loop order, row) from a point's native counterterm kets
    (``V2Executor.evaluate``'s ``counterterm_kets``: rows x ket components,
    the program's layout; ``rows``: the rows they carry, every plan row by
    default) on the amplitude basis at N_c = 3 (``ket_map``, or a stored
    process's recorded map; the native twin of ``counterterm_kets``)."""

    mapping = _ket_mapping(slice_, exported)
    components = len(mapping)
    size = len(slice_.amplitude)
    zero = numbers.zero
    three = numbers.real(3)
    # 3^nc once per N_c power (the same carrier value as at every use).
    powers: dict[int, Any] = {}
    out: dict[tuple[Orders, rx.Row], list[list[Any]]] = {}
    for r, row in enumerate(exported.rows if rows is None else rows):
        for j, (t, k, order, nc) in enumerate(mapping):
            if k >= width:
                continue
            value = values[r * components + j]
            ket = out.get((order, row))
            if ket is None:
                ket = out[(order, row)] = [[zero] * width for _ in range(size)]
            power = powers.get(nc)
            if power is None:
                power = powers[nc] = three**nc
            ket[t][k] = ket[t][k] + value * power
    return out


def assemble(evaluation: Any) -> None:
    """``_PointEvaluation._assemble`` of a loop-induced point: the amplitude
    vectors a = a_bare + A^CT per (loop order, row) (kept as
    ``evaluation.amplitude_vectors``), |A|^2 per sector (``square``) as the
    "virtual" component of the ``PointResult`` (no other component: the bare,
    R2 and UV parts are not additive in a square), Born fields empty, and
    the stability inputs (``budgets``)."""

    from .assemble import Laurent, PointResult

    numbers = evaluation.numbers
    slice_ = evaluation.slice
    width = 3 if evaluation.poles else 1
    size = len(slice_.amplitude)
    rows = rows_of(evaluation)
    squared_natively = evaluation.__dict__.pop("native_squared", None)
    if squared_natively is not None:
        _assemble_pending(evaluation, squared_natively, width)
        return
    native = getattr(evaluation, "native_bare", None)
    with numbers.scope():
        bare = (
            bare_amplitudes(evaluation.families, size, numbers, width)
            if native is None
            else native
        )
        kets = getattr(evaluation, "native_kets", None)
        if kets is None:
            if not hasattr(evaluation, "site_vectors"):
                if slice_.amplitude.counterterms:
                    # Never a silent loss of the R2/UV part.
                    raise ValueError(
                        "a loop-induced native point needs the executor's "
                        "counterterm kets (native trees with counterterms)"
                    )
                kets = {}
            else:
                kets = counterterm_kets(slice_, evaluation.site_vectors, numbers, width)
        total = add_amplitudes(bare, kets, numbers=numbers, size=size, width=width)
        gram = metric(slice_, numbers)
        if getattr(evaluation, "native_square", False):
            squared = native_square(
                total,
                gram,
                slice_.sectors,
                rows,
                width,
                evaluation.average,
                slice_.native,
            )
        else:
            squared = square(
                total, gram, slice_.sectors, rows, width, numbers, evaluation.average
            )
        zero = numbers.real(0)
        virtual = {sector: Laurent(*values) for sector, values in squared.items()}
        totals = [zero]
        for k in range(width):
            totals.append(sum((values[k] for values in squared.values()), zero))
    evaluation.amplitude_vectors = total
    evaluation.bare_vectors = bare
    evaluation.counterterm_vectors = kets
    evaluation.gram = gram
    evaluation.result = PointResult(
        {},
        {"virtual": virtual},
        tuple(totals),
        dict(evaluation.families),
        None,
        colour_contraction=getattr(evaluation, "colour_contraction", "direct"),
        poles=evaluation.mode,
        finiteness=point_finiteness(evaluation),
    )
    budgets(evaluation)


def _assemble_pending(evaluation: Any, squared: Mapping, width: int) -> None:
    """``assemble`` of a binary64 point squared natively (``native_squares``):
    the same result, its amplitude, bare and counterterm vectors formed on
    first read (``add_amplitudes`` of the pending ``native_bare`` and
    ``native_kets``), as ``assemble`` forms them."""

    from .assemble import Laurent, PointResult

    numbers = evaluation.numbers
    slice_ = evaluation.slice
    size = len(slice_.amplitude)
    found = evaluation.__dict__
    bare = found.get("native_bare", found.get("_pending_native_bare"))
    kets = found.get("native_kets", found.get("_pending_native_kets"))

    def value(source: Any) -> Any:
        return source() if callable(source) and not isinstance(source, dict) else source

    def total() -> dict:
        return add_amplitudes(
            value(bare), value(kets), numbers=numbers, size=size, width=width
        )

    with numbers.scope():
        gram = metric(slice_, numbers)
        zero = numbers.real(0)
        virtual = {sector: Laurent(*values) for sector, values in squared.items()}
        totals = [zero]
        for k in range(width):
            totals.append(sum((values[k] for values in squared.values()), zero))
    for name in ("amplitude_vectors", "bare_vectors", "counterterm_vectors"):
        found.pop(name, None)
    found["_pending_amplitude_vectors"] = _formed(total)
    found["_pending_bare_vectors"] = _formed(lambda: value(bare))
    found["_pending_counterterm_vectors"] = _formed(lambda: value(kets))
    evaluation.gram = gram
    evaluation.result = PointResult(
        {},
        {"virtual": virtual},
        tuple(totals),
        dict(evaluation.families),
        None,
        colour_contraction=getattr(evaluation, "colour_contraction", "direct"),
        poles=evaluation.mode,
        finiteness=point_finiteness(evaluation),
    )
    budgets(evaluation)


def native_square(
    amplitudes: Mapping[tuple[Orders, rx.Row], Sequence[Sequence[Any]]],
    gram: Sequence[Sequence[Any]],
    sectors: Sequence[tuple[Orders, frozenset[tuple[Orders, Orders]]]],
    rows: Sequence[rx.Row],
    width: int,
    average: Any,
    native: Any,
) -> dict[Orders, tuple[float, ...]]:
    """``square`` of binary64 amplitude vectors by the native canonical
    square (``square_amplitudes``, the one Rust implementation of RULED Q41
    for the Python API and the SDK): dense slots (loop order, row, t) over
    the sectors' loop orders (zero where absent)."""

    orders = sorted(
        {order for _sector, pairs in sectors for pair in pairs for order in pair}
    )
    slot = {order: k for k, order in enumerate(orders)}
    size = len(gram)
    zero = [[0.0, 0.0]] * width
    values: list[Any] = []
    for order in orders:
        for row in rows:
            vector = amplitudes.get((order, row))
            if vector is None:
                values.extend([zero] * size)
            elif width == 1:
                values.extend([[cell[0].real, cell[0].imag]] for cell in vector[:size])
            else:
                values.extend(
                    [[z.real, z.imag] for z in cell[:width]] for cell in vector[:size]
                )
    metric_values = [[complex(x).real, complex(x).imag] for line in gram for x in line]
    pairs = [
        sorted((slot[left], slot[right]) for left, right in pairs)
        for _sector, pairs in sectors
    ]
    squared = native.square_amplitudes(
        values,
        len(orders),
        len(rows),
        size,
        width,
        metric_values,
        pairs,
        float(average),
    )
    return {
        sector: tuple(totals)
        for (sector, _pairs), totals in zip(sectors, squared, strict=True)
    }


def _bound_norm(errors, gram) -> float:
    """sqrt(e^T |G| e) for absolute errors e per t (an upper bound of
    ||delta a||_G for |delta a_t| <= e_t)."""

    total = 0.0
    for t, x in enumerate(errors):
        for u, y in enumerate(errors):
            total += _size(x) * abs(complex(gram[t][u])) * _size(y)
    return total**0.5


def _size(value: Any) -> Any:
    """A magnitude as the budgets hold it: a ``Wide`` as it is, anything
    else as a binary64 float (``float`` as before)."""

    return value if isinstance(value, Wide) else float(value)


def sector_form(
    evaluation: Any,
    rows: Sequence[rx.Row],
    left: Callable[[tuple[Orders, rx.Row]], Sequence[Any] | None],
    right: Callable[[tuple[Orders, rx.Row]], Sequence[Any] | None],
    kernel: Callable[[Any, Any], float],
) -> dict:
    """The |A|^2-level Laurent convolution of every budget and scale per
    sector: sum_pairs kappa sum_rows sum_{i+j=k} kernel(x_i, y_j) / avg
    (a ``Budget`` per Laurent coefficient k), x = left((l, row)) and
    y = right((l', row)) per Laurent coefficient (None: no term)."""

    from .stability import Budget

    width = width_of(evaluation)
    average = float(evaluation.average)
    out = {}
    for sector, pairs in evaluation.slice.sectors:
        totals = [0.0] * width
        for pair in sorted(pairs):
            weight = kappa(pair)
            for row in rows:
                x = left((pair[0], row))
                y = right((pair[1], row))
                if x is None or y is None:
                    continue
                for k in range(width):
                    for i in range(k + 1):
                        totals[k] += weight * kernel(x[i], y[k - i])
        out[sector] = Budget(tuple(value / average for value in totals))
    return out


def quadratic_budget(evaluation: Any, errors: Mapping) -> dict:
    """The error budget of |A|^2 per sector and Laurent coefficient from
    absolute amplitude errors ``errors`` ((order, row) -> per t and k):
    sum_pairs kappa sum_h sum_{i+j=k} (||a_i||_G ||e_j|| + ||e_i|| ||a_j||_G
    + ||e_i|| ||e_j||) / avg, colour-metric norms (PLAN §2.a.8; never a raw
    component)."""

    gram = evaluation.gram
    numbers = evaluation.numbers
    width = width_of(evaluation)
    amplitude = evaluation.amplitude_vectors
    size = len(evaluation.slice.amplitude)

    def terms(key):
        """(||a_k||_G, ||e_k|| bound) per Laurent coefficient k."""

        vector = amplitude.get(key)
        error = errors.get(key)
        return [
            (
                0.0
                if vector is None
                else magnitude(
                    g_norm([vector[t][k] for t in range(size)], gram, numbers),
                    numbers.wide,
                ),
                0.0
                if error is None
                else _bound_norm([error[t][k] for t in range(size)], gram),
            )
            for k in range(width)
        ]

    def kernel(x, y):
        (a, da), (b, db) = x, y
        return a * db + da * b + da * db

    return sector_form(evaluation, rows_of(evaluation), terms, terms, kernel)


def lane_errors(evaluation: Any, lanes: Mapping) -> dict:
    """Absolute amplitude errors (i/16 pi^2) sum_f |delta Omega_f| per
    (order, row), t and k from per-lane absolute deviations (no
    cancellation between families)."""

    import math

    from .conventions import LOOP_FACTOR_DENOMINATOR

    width = 3 if evaluation.poles else 1
    size = len(evaluation.slice.amplitude)
    factor = 1 / (LOOP_FACTOR_DENOMINATOR * math.pi**2)
    out: dict = {}
    wide = evaluation.numbers.wide
    for (_family, order, (row, t)), values in lanes.items():
        cell = out.setdefault((order, row), [[0.0] * width for _ in range(size)])[t]
        for k, value in enumerate(tuple(values)[:width]):
            cell[k] += factor * magnitude(value, wide)
    return out


def budgets(evaluation: Any) -> None:
    """The re-test inputs of a loop-induced point's stability estimate:
    ``retest_budget`` and ``family_deviations`` (quadratic in the
    colour-metric norm). The scale S of the estimate's floor is formed on
    demand (``stability_scale``: it costs the term scale's reductions)."""

    evaluation.family_deviations = None
    evaluation.retest_budget = None
    native = getattr(evaluation, "native_budget", None)
    if native is not None:
        evaluation.retest_budget = quadratic_budget(evaluation, native)
    elif evaluation.retest_families:
        deviations = {}
        for lane, value in evaluation.families.items():
            other = evaluation.retest_families[lane].coefficients
            deviations[lane] = tuple(
                abs(a - b) for a, b in zip(value.coefficients, other, strict=True)
            )
        evaluation.family_deviations = deviations
        evaluation.retest_budget = quadratic_budget(
            evaluation, lane_errors(evaluation, deviations)
        )
    evaluation.absolute = None


def rotation_budget(direct: Any, rotated: Any) -> dict:
    """The error budget of one rotation check of a loop-induced point.

    A rotation keeps |A|^2 but not the helicity amplitudes: the external
    wavefunctions at the rotated momenta differ from the rotated ones by a
    little-group phase per helicity row, common to every loop order, basis
    element and lane of the row. Each row's lanes and counterterm kets are
    therefore compared after removing that phase (the phase of
    sum_{l,t} conj(a'_{l,h,t}) a_{l,h,t} of the finite parts; 1 where that
    sum vanishes), lane by lane, and the absolute deviations enter the
    quadratic budget (``quadratic_budget``) as the reduction re-test's do."""

    return quadratic_budget(
        direct, _rotation_deviations(direct, rotated, _row_phases(direct, rotated, 1))
    )


def cross_budget(direct: Any, other: Any) -> dict:
    """The error budget of the cross-backend check of a loop-induced point
    (``stability.CROSS``): ``other`` is the same point on the other
    reduction backend, so the lanes and kets are compared as
    ``rotation_budget`` compares them, without a little-group phase."""

    with direct.numbers.scope():
        unit = {row: direct.numbers.pair(1) for row in rows_of(direct)}
    return quadratic_budget(direct, _rotation_deviations(direct, other, unit))


def rotation_errors(direct: Any, rotated: Any) -> dict:
    """Per (loop order, row), t and Laurent coefficient k the absolute
    deviation bound of a probe's rotation check (``probe``): the lanes and
    counterterm kets of ``rotated`` against ``direct`` after removing each
    row's little-group phase (``rotation_budget``'s comparison), here with
    the phase from every Laurent coefficient (a probe's residues may sit in
    the poles), summed over the lanes so that no two cancel. A true value
    rotates with its row's phase and deviates by rounding only; rounding
    noise deviates by its own size: the residues of a Furry zero (g g > a a
    a), whose numerator coefficients cancel between the loop's two
    orientations, so that its term floor is at rounding too, are covered by
    this budget, not by the floor. Needs the raw lanes (or compares the
    bare amplitudes, ``rotation_budget``)."""

    width = width_of(direct)
    return _rotation_deviations(direct, rotated, _row_phases(direct, rotated, width))


def _row_phases(direct: Any, rotated: Any, width: int) -> dict:
    """Per helicity row the little-group phase of ``rotated`` against
    ``direct``: the phase of sum conj(a') a over the row's loop orders, t
    and its first ``width`` Laurent coefficients (1 where it vanishes).

    The modulus is taken in the carrier (``_modulus``): a phase normalised
    in binary64 is off unity by ~1e-16, which a double-double or arbitrary
    precision comparison would read as a deviation of every rotated value
    (lit-stab-n: the rotation budget of g g > h h in double-double was
    7e-17 relative instead of 2e-30)."""

    numbers = direct.numbers
    size = len(direct.slice.amplitude)
    with numbers.scope():
        phases = {}
        for row in rows_of(direct):
            total = numbers.zero
            for (order, key_row), vector in direct.amplitude_vectors.items():
                if key_row != row:
                    continue
                other = rotated.amplitude_vectors.get((order, row))
                if other is None:
                    continue
                for t in range(size):
                    for k in range(width):
                        total = total + other[t][k].conjugate() * vector[t][k]
            magnitude = _modulus(total, numbers)
            phases[row] = (
                numbers.pair(1)
                if not magnitude
                else total * numbers.real(1 / magnitude)
                if numbers.double
                else total * (1 / magnitude)
            )
    return phases


def _modulus(value: Any, numbers: Any) -> Any:
    """|value| in the carrier: ``abs`` in binary64; for the Decimal pairs of
    the extended carriers sqrt(re^2 + im^2) at the active context precision
    (their ``abs`` is a binary64 float)."""

    if numbers.double:
        return abs(value)
    return (value.real * value.real + value.imag * value.imag).sqrt()


def _rotation_deviations(direct: Any, rotated: Any, phases: Mapping) -> dict:
    """``lane_errors`` of the phase-corrected lane deviations of ``rotated``
    from ``direct``, plus the counterterm kets' (and, without raw lanes, the
    bare amplitudes') per (loop order, row, t) deviations."""

    numbers = direct.numbers
    width = 3 if direct.poles else 1
    size = len(direct.slice.amplitude)
    with numbers.scope():
        deviations = {}
        zero = numbers.zero
        for lane in dict.fromkeys([*direct.families, *rotated.families]):
            _family, _order, (row, _t) = lane
            a = direct.families.get(lane)
            b = rotated.families.get(lane)
            a = (zero,) * width if a is None else a.coefficients[:width]
            b = (zero,) * width if b is None else b.coefficients[:width]
            deviations[lane] = tuple(
                magnitude(y * phases[row] - x, True)
                if numbers.wide
                else abs(y * phases[row] - x)
                for x, y in zip(a, b, strict=True)
            )
        errors = lane_errors(direct, deviations)
        # Without raw lanes (the native amplitude sum) the bare amplitudes
        # themselves are compared, per (loop order, row, t).
        parts = [(direct.counterterm_vectors, rotated.counterterm_vectors)]
        if not direct.families and getattr(direct, "native_bare", None) is not None:
            parts.append((direct.bare_vectors, rotated.bare_vectors))
        for key, a, b in (
            (key, mine.get(key), theirs.get(key))
            for mine, theirs in parts
            for key in dict.fromkeys([*mine, *theirs])
        ):
            _order, row = key
            cell = errors.setdefault(key, [[0.0] * width for _ in range(size)])
            for t in range(size):
                for k in range(width):
                    x = zero if a is None else a[t][k]
                    y = zero if b is None else b[t][k]
                    cell[t][k] += magnitude(y * phases[row] - x, numbers.wide)
    return errors


def term_values(evaluation: Any) -> dict:
    """Per (loop order, row) the term scale of the bare amplitude per basis
    element t and Laurent coefficient k, sum_f sum_alpha |N_{f,h,t,alpha}|
    |I_{f,alpha,k}| / 16pi^2 (m-lit DECISIONS 2026-11-06 ~09:00 (1)): the
    size of each amplitude component before the reduction's own
    cancellations, from the tensor moments I_{f,alpha} (the integral of
    monomial alpha of family f, one unit-numerator reduction per monomial,
    family and point; TIRust's moments). The native executor forms it on
    request (``V2Options::term_scale``, ``native_terms``); the Python
    reference reduces the unit numerators of its own dressing (the oracle).
    Cached on the evaluation."""

    found = getattr(evaluation, "term_cache", None)
    if found is not None:
        return found
    native = getattr(evaluation, "native_bare", None)
    if native is not None:
        terms = getattr(evaluation, "native_terms", None)
        if terms is None and not native:
            # No (loop order, row) slot: no family is routed at any order
            # (an amplitude of counterterm kets alone, e.g. a ket whose
            # coupling the restriction makes vanish), so there is no family
            # term to scale and the native executor returns none.
            terms = {}
        if terms is None:
            raise ValueError(
                "a native loop-induced point has no term scale: the executor "
                "forms it with the stability checks (term_scale)"
            )
        evaluation.term_cache = terms
        return terms
    out: dict = {}
    numerators = getattr(evaluation, "amplitude_numerators", None) or {}
    if numerators:
        # (Formed on demand, possibly after the point's own scope.)
        with evaluation.numbers.scope():
            moments = _moments(evaluation, numerators)
            out = _term_sums(evaluation, numerators, moments)
    evaluation.term_cache = out
    return out


def _moments(evaluation: Any, numerators: Mapping) -> dict:
    """I_{f,alpha} per (family f, numerator frame) and monomial alpha, as
    Laurent coefficient lists: the unit numerators of one of the family's
    loop orders in that frame (the integrals depend on the propagators and
    the frame alone) reduced through the evaluation's own reducer
    (``_PointEvaluation.reducer``: the call's reduction backend) on its
    groups (``_PointEvaluation._groups``)."""

    from dataclasses import replace

    from .poles import reducer_poles

    numbers = evaluation.numbers
    units = {}
    frames = {}
    for (family, order), numerator in sorted(numerators.items()):
        if (family, numerator.frame) in frames:
            continue
        frames[(family, numerator.frame)] = (family, order)
        size = len(numerator.columns[0])
        one, zero = numbers.pair(1), numbers.zero
        units[(family, order)] = replace(
            numerator,
            columns=tuple(
                tuple(one if m == alpha else zero for m in range(size))
                for alpha in range(size)
            ),
        )
    width = max(len(numerator.columns) for numerator in units.values())
    lanes, groups = evaluation._groups(units, 0, list(range(width)))
    direct, _check = evaluation.reducer().reduce(
        groups, poles=reducer_poles(evaluation.mode), check=False, rescale=False
    )
    frame_of = {key: frame for (_family, frame), key in frames.items()}
    out: dict = {}
    for (family, order, alpha), batch in zip(lanes, direct, strict=True):
        key = (family, frame_of[(family, order)])
        out.setdefault(key, {})[alpha] = evaluation._values(batch, alpha)
    return out


def _term_sums(evaluation: Any, numerators: Mapping, moments: Mapping) -> dict:
    """``term_values`` of the Python reference from its numerators (columns
    (row, t), ``column_labels``) and the families' moments."""

    import math

    from .conventions import LOOP_FACTOR_DENOMINATOR

    width = width_of(evaluation)
    size = len(evaluation.slice.amplitude)
    rows = rows_of(evaluation)
    factor = 1 / (LOOP_FACTOR_DENOMINATOR * math.pi**2)
    wide = evaluation.numbers.wide
    out: dict = {}
    for (family, order), numerator in sorted(numerators.items()):
        integrals = moments[(family, numerator.frame)]
        for column, coefficients in enumerate(numerator.columns):
            if not any(coefficients):
                continue
            row, t = rows[column // size], column % size
            cell = out.setdefault((order, row), [[0.0] * width for _ in range(size)])[t]
            for alpha, value in enumerate(coefficients):
                if not value:
                    continue
                size_ = magnitude(value, wide)
                for k in range(width):
                    cell[k] += factor * size_ * magnitude(integrals[alpha][k], wide)
    return out


def row_scales(evaluation: Any) -> dict:
    """The per-row term floor of every (loop order, row): per Laurent
    coefficient k, S_k(h) = max(S_term,k(h), S_term,0(h)) with S_term,k(h) =
    sum_t T_{h,t,k} sqrt(G_tt) + ||A^CT_{h,k}||_G (``term_values`` T; m-lit
    DECISIONS 2026-11-06 ~09:00 (1)). The floor by the row's own finite
    order covers order-k numerator content that cancels in the dressing
    (gg>hh, gg>zz 1/eps^2); the term scale covers families that integrate
    to zero by themselves (Landau-Yang), where scales measured after the
    integration are themselves at rounding. Cached on the evaluation."""

    found = getattr(evaluation, "row_scale_cache", None)
    if found is not None:
        return found
    terms = term_values(evaluation)
    gram = evaluation.gram
    numbers = evaluation.numbers
    width = width_of(evaluation)
    size = len(evaluation.slice.amplitude)
    roots = [max(float(complex(gram[t][t]).real), 0.0) ** 0.5 for t in range(size)]
    kets = evaluation.counterterm_vectors
    out = {}
    with numbers.scope():
        for key in dict.fromkeys([*terms, *kets]):
            vector = terms.get(key)
            ket = kets.get(key)
            values = []
            for k in range(width):
                value = 0.0
                if vector is not None:
                    value = sum(vector[t][k] * roots[t] for t in range(size))
                if ket is not None:
                    value += magnitude(
                        g_norm([ket[t][k] for t in range(size)], gram, numbers),
                        numbers.wide,
                    )
                values.append(value)
            out[key] = [max(value, values[0]) for value in values]
    evaluation.row_scale_cache = out
    return out


def row_values(evaluation: Any) -> dict:
    """Per (loop order, row) and Laurent coefficient k the absolute size of
    the computed amplitude on the term floor's footing (``row_scales``):
    N_k(h) = sum_t |a_{h,t,k}| sqrt(G_tt) (an upper bound of ||a_{h,k}||_G
    and of the colour square's own terms, sum_tu |a_t| |G_tu| |a_u| <= N^2,
    G positive semidefinite)."""

    gram = evaluation.gram
    width = width_of(evaluation)
    size = len(evaluation.slice.amplitude)
    wide = evaluation.numbers.wide
    roots = [max(float(complex(gram[t][t]).real), 0.0) ** 0.5 for t in range(size)]
    return {
        key: [
            sum(magnitude(vector[t][k], wide) * roots[t] for t in range(size))
            for k in range(width)
        ]
        for key, vector in evaluation.amplitude_vectors.items()
    }


def floor_kernel(roundoff: Any) -> Callable[[Any, Any], Any]:
    """The floor's bilinear kernel on (value, floor) pairs of the two sides:
    x S' + S y + FLOOR_UNITS u S S'. With |delta a| <= FLOOR_UNITS u S per
    side (the roundings no check samples, ``stability``), the form a^dag G a'
    computed from the rounded vectors moves by at most FLOOR_UNITS u (x S' +
    S y) + (FLOOR_UNITS u)^2 S S' (x, y the computed sizes), so
    FLOOR_UNITS u times this kernel bounds it: first order in each side's
    floor against the other side's value, as the checks' budgets
    (``quadratic_budget``). The second-order term keeps a vanishing value
    "zero within the estimate" (RULED Q13): there x ~ u S."""

    from .stability import FLOOR_UNITS

    epsilon = FLOOR_UNITS * roundoff

    def kernel(left: Any, right: Any) -> Any:
        (x, s), (y, t) = left, right
        return x * t + s * y + epsilon * s * t

    return kernel


def scale(evaluation: Any) -> dict:
    """The scale S of the estimate's floor per sector and coefficient
    (``StabilityEstimate.from_checks``' ``scale``, its floor FLOOR_UNITS u
    S): the |A|^2-level first-order form of the per-row term floors S_{l,h}
    (``row_scales``; PLAN §2.a.8 with the DECISIONS ~09:00 (1) scale)
    against the computed amplitude's sizes N_{l,h} (``row_values``),
    sum_pairs kappa sum_h sum_{i+j=k} (N_{l,h,i} S_{l',h,j} + S_{l,h,i}
    N_{l',h,j} + FLOOR_UNITS u S_{l,h,i} S_{l',h,j}) / avg
    (``floor_kernel``): an amplitude that cancels by a factor r between its
    terms gets a floor linear in r, as its roundings are; a numerical zero
    (N ~ u S) is still reported as "zero within the estimate" by the
    second-order term (RULED Q13: no zero is declared). A key with a
    value and no floor (or the reverse) counts with a zero for the missing
    part."""

    scales = row_scales(evaluation)
    values = row_values(evaluation)
    width = width_of(evaluation)
    zero = [0.0] * width

    def pairs(key: tuple[Orders, rx.Row]) -> list[tuple[Any, Any]] | None:
        found, value = scales.get(key), values.get(key)
        if found is None and value is None:
            return None
        found = zero if found is None else found
        value = zero if value is None else value
        return [(value[k], found[k]) for k in range(width)]

    return sector_form(
        evaluation,
        rows_of(evaluation),
        pairs,
        pairs,
        floor_kernel(evaluation.numbers.precision.estimate_roundoff),
    )


def stability_scale(evaluation: Any) -> dict:
    """``scale`` of a point (formed on first use: the Python reference
    reduces its unit numerators then; a native point needs the executor's
    term scale, requested with the stability checks)."""

    if evaluation.absolute is None:
        evaluation.absolute = scale(evaluation)
    return evaluation.absolute


def finiteness(evaluation: Any) -> dict:
    """The amplitude-level finiteness ratio per (loop order, row): max over
    the pole coefficients k = 1, 2 of ||a_{-k}||_G / S_k(h), the residue of
    the amplitude's poles against the row's term floor (``row_scales``;
    PLAN §2.a.7 L3 with the DECISIONS 2026-11-06 ~09:00 (1) scale). A
    one-loop amplitude with no tree is IR finite and UV finite after
    renormalisation, so the ratio is of the order of the carrier's unit
    roundoff (0 for a row with no amplitude). Empty without poles."""

    width = width_of(evaluation)
    if width == 1:
        return {}
    scales = row_scales(evaluation)
    gram = evaluation.gram
    numbers = evaluation.numbers
    size = len(evaluation.slice.amplitude)
    out = {}
    for key, vector in evaluation.amplitude_vectors.items():
        ratio = 0.0
        for k in range(1, width):
            with numbers.scope():
                residue = magnitude(
                    g_norm([vector[t][k] for t in range(size)], gram, numbers),
                    numbers.wide,
                )
            if residue:
                bound = scales.get(key, [0.0] * width)[k]
                ratio = max(ratio, float(residue / bound) if bound else float("inf"))
        out[key] = ratio
    return out


def point_finiteness(evaluation: Any) -> float | None:
    """The finiteness ratio of a point (the public lane diagnostic's
    ``finiteness``): the largest ``finiteness`` ratio over its loop orders
    and rows, when its poles were computed and its term scale is at hand
    without another reduction (a native point whose executor formed it,
    ``native_terms``: the stability checks request it, as the floor of
    their estimate); None otherwise. A default call (no checks) does not
    form the term scale: its unit-numerator reductions cost 1.3x (g g > z z)
    to 2x (g g > h) a plain evaluation on NinjaRS (lit-api-b). An exact
    colour zero (an empty amplitude basis) has ratio 0."""

    if width_of(evaluation) == 1:
        return None
    if getattr(evaluation, "native_terms", None) is None:
        # (The Python reference forms its term scale by reducing unit
        # numerators: only on request, ``finiteness``, ``stability_scale``.)
        return None
    return max(finiteness(evaluation).values(), default=0.0)


# The x10 rule (m-lit Q12): a residue within ten times its own stability
# estimate. The helicity-zero filter's binary64 screen reads it
# (``helicity_filter``); the probes' verdicts are the threshold rule's
# (``ProbeResult``, ``checks.threshold``).
ESTIMATE_FACTOR = 10


def amplitude_estimates(
    evaluation: Any,
    roundoff: float,
    scales: Mapping | None = None,
    rotations: Sequence[Mapping] = (),
) -> dict:
    """Per (loop order, row) and Laurent coefficient k the pair (||a_k||_G,
    E_k): the amplitude's colour-metric norm and its absolute estimate E_k =
    SAFETY x (max over rotations of ||delta a_k||_G + ||delta a_k||_G of the
    re-test) + FLOOR_UNITS x u x S_k(h) (``stability``'s combination at the
    amplitude level, PLAN §2.a.8), with the re-test's ||delta a_k||_G
    bounded by its per-component deviations (``native_budget``, or the
    Python lanes' ``family_deviations``; no two families cancel), a
    rotation's by ``rotation_errors`` (``rotations``), and S_k(h) the row's
    term floor (``row_scales``, or ``scales``: a Ward probe's are the
    physical amplitude's, ``probe``). Needs the reduction re-test and the
    term scale (``probe``)."""

    from .stability import FLOOR_UNITS, SAFETY

    errors = getattr(evaluation, "native_budget", None)
    if errors is None:
        deviations = evaluation.family_deviations
        if deviations is None:
            raise ValueError("an amplitude estimate needs the reduction re-test")
        errors = lane_errors(evaluation, deviations)
    if scales is None:
        scales = row_scales(evaluation)
    gram = evaluation.gram
    numbers = evaluation.numbers
    width = width_of(evaluation)
    size = len(evaluation.slice.amplitude)
    out = {}
    with numbers.scope():
        items = [
            (
                key,
                [
                    g_norm([vector[t][k] for t in range(size)], gram, numbers)
                    for k in range(width)
                ],
            )
            for key, vector in evaluation.amplitude_vectors.items()
        ]
    for key, norms in items:
        error = errors.get(key)
        scale_ = scales.get(key, [0.0] * width)
        entries = []
        for k in range(width):
            residue = float(norms[k])
            budget = (
                0.0
                if error is None
                else _bound_norm([error[t][k] for t in range(size)], gram)
            )
            budget += max(
                (
                    _bound_norm([turned[key][t][k] for t in range(size)], gram)
                    for turned in rotations
                    if key in turned
                ),
                default=0.0,
            )
            entries.append(
                (residue, SAFETY * budget + FLOOR_UNITS * roundoff * scale_[k])
            )
        out[key] = tuple(entries)
    return out


def _default_tolerance() -> float:
    from .checks import tolerance

    return tolerance()


class _Judged:
    """The verdict properties of a probe result from its rows' judgements
    (``cells``: row key -> ``checks.Judgement``; ``tolerance``): every
    independently required row decides on its own, the aggregate is formed
    from the rows' final verdicts (``checks.aggregate``)."""

    cells: Mapping[Any, Any]
    tolerance: float

    @property
    def final(self) -> dict[Any, Any]:
        from .checks import finished

        return finished(self.cells)

    @property
    def verdict(self) -> str:
        from .checks import aggregate

        return aggregate(self.final)

    @property
    def passed(self) -> bool:
        """Decided without a failure: every row with a term passes, or every
        row is vacuous (nothing to test, ``verdict`` "vacuous")."""

        return self.verdict in ("pass", "vacuous")

    @property
    def ratios(self) -> dict[Any, float]:
        """Per (loop order, row) the largest R over its deciding scale."""

        out: dict[Any, float] = {}
        for (key, _k), cell in self.final.items():
            if cell.ratio is not None and cell.verdict in ("pass", "fail"):
                out[key] = max(out.get(key, 0.0), cell.ratio)
        return out

    @property
    def worst(self) -> float:
        return max(self.ratios.values(), default=0.0)

    @property
    def relative(self) -> dict[Any, tuple[float, float | None]]:
        """Per (loop order, row): R / scale and E / scale of its deciding
        coefficient (E reported only)."""

        out: dict[Any, tuple[float, float | None]] = {}
        for (key, _k), cell in self.final.items():
            if cell.ratio is None or cell.verdict not in ("pass", "fail"):
                continue
            if key in out and out[key][0] > cell.ratio:
                continue
            m = cell.measure
            scale = m.physical if cell.scale == "physical" else m.terms
            error = None if m.estimate is None or not scale else m.estimate / scale
            out[key] = (cell.ratio, error)
        return out

    @property
    def undefined(self) -> tuple[str, ...]:
        return tuple(
            f"{cell.measure.label}: {cell.reason}"
            for cell in self.final.values()
            if cell.verdict == "inconclusive"
        )

    @property
    def vacuous(self) -> int:
        return sum(1 for cell in self.final.values() if cell.verdict == "vacuous")

    @property
    def deciding(self) -> Any:
        """The row that decided the aggregate (``checks.worst_cell``)."""

        from .checks import worst_cell

        return worst_cell(self.final)

    @property
    def worst_row(self) -> tuple[Any, ...] | None:
        """(label, R, P, T, scale) of the deciding row."""

        cell = self.deciding
        if cell is None:
            return None
        m = cell.measure
        return (m.label, m.residue, m.physical, m.terms, cell.scale)

    @property
    def measures(self) -> tuple[tuple[Any, Any], ...]:
        return tuple((key, cell.measure) for key, cell in self.cells.items())

    @property
    def reason(self) -> str | None:
        """Why the probe is inconclusive, or that it has nothing to test
        (None otherwise)."""

        verdict = self.verdict
        if verdict == "vacuous":
            return (
                "nothing to test: the amplitude vanishes identically (every row "
                "vacuous: no term)"
            )
        if verdict != "inconclusive":
            return None
        undefined = self.undefined
        if not undefined:
            return "nothing compared"
        more = len(undefined) - 1
        return undefined[0] + (f" (and {more} more)" if more else "")


def judged_cells(
    measures: Mapping[Any, Any], tolerance: float, carrier: Any = None
) -> dict[Any, Any]:
    """The rows' judgements at one carrier (``checks.judge`` each; the
    carrier's name and unit roundoff recorded for the ladder)."""

    from dataclasses import replace

    from .checks import judge

    name = None if carrier is None else carrier.arithmetic
    roundoff = None if carrier is None else carrier.unit_roundoff
    return {
        key: replace(judge(measure, tolerance), carrier=name, unit_roundoff=roundoff)
        for key, measure in measures.items()
    }


def physical_references(estimates: Mapping) -> dict[Any, tuple[Any, Any]]:
    """Per (loop order, row) of a physical evaluation its finite amplitude's
    colour-metric norm P and that norm's estimate E_P (``amplitude_
    estimates``' k = 0 entry): the probes' physical reference."""

    return {
        key: (_finite(entries[0][0]), _finite(entries[0][1]))
        for key, entries in estimates.items()
        if entries
    }


def ward_references(references: Mapping, leg: int) -> dict[Any, tuple[Any, Any]]:
    """``physical_references`` for a Ward probe of leg ``leg``: per row the
    largest P and E_P over the rows that differ from it only in that leg's
    helicity (``ward_floors``); None where one of them is None."""

    def merged(row):
        return tuple((i, 0 if i == leg - 1 else h) for i, h in row)

    widest: dict[Any, tuple[Any, Any]] = {}
    for (order, row), (size, error) in references.items():
        key = (order, merged(row))
        known = widest.get(key, (0.0, 0.0))
        widest[key] = (
            None if size is None or known[0] is None else max(size, known[0]),
            None if error is None or known[1] is None else max(error, known[1]),
        )
    return {(order, row): widest[(order, merged(row))] for order, row in references}


def probe_measures(
    estimates: Mapping,
    floors: Mapping,
    first: int,
    references: Mapping | None,
    width: int,
) -> dict[Any, Any]:
    """The required rows of one probe ((loop order, row), k) -> ``checks.
    Measure``: every row of the evaluation OR of the floors (their union)
    and every Laurent coefficient k >= ``first`` of ``width``: R the
    colour-metric residue (``amplitude_estimates``), P and E_P the row's
    physical reference at the same point and carrier
    (``physical_references``; None: unavailable), T the row's term floor at
    k. A row or coefficient one operand lacks is incomplete (inconclusive),
    never skipped."""

    from .checks import Measure

    references = references or {}
    out: dict[Any, Any] = {}
    for key in dict.fromkeys([*estimates, *floors]):
        entries = estimates.get(key)
        floor = floors.get(key)
        size, error = references.get(key, (None, None))
        for k in range(first, width):
            present = (
                entries is not None
                and len(entries) > k
                and floor is not None
                and len(floor) > k
                and key in references
            )
            out[(key, k)] = Measure(
                f"{key} k={k}",
                _finite(entries[k][0]) if present else None,
                size if present else None,
                _finite(floor[k]) if present else None,
                _finite(entries[k][1]) if present else None,
                error if present else None,
                complete=present,
            )
    return out


def _finite(value: Any) -> float | None:
    """A non-negative magnitude as a finite binary64 number, else None."""

    try:
        found = float(value)
    except (ArithmeticError, TypeError, ValueError):
        return None
    return found if math.isfinite(found) else None


@dataclass(frozen=True)
class ProbeResult(_Judged):
    """A loop-induced probe of one point (``probe``): per required row
    ((loop order, row), Laurent coefficient) its judgement (``cells``,
    ``checks.judge``; R the colour-metric residue, P the norm of the
    physical finite amplitude of that row at the same point and carrier
    with its estimate E_P, T the row's term floor); the verdict and the
    reported figures follow from them (``_Judged``). ``scales`` are the
    physical amplitude's row term floors."""

    kind: str
    cells: Mapping[Any, Any]
    scales: Mapping[tuple[Orders, rx.Row], Sequence[float]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    # Whether a run of the probe (its evaluation or a rotated one) served a
    # reduction lane without accuracy evidence (``PointResult.
    # uncertified_bound``): recorded; the verdict is the threshold rule's.
    uncertified: bool = False
    tolerance: float = field(default_factory=_default_tolerance)
    # The unit roundoff of the carrier that produced the term floors T
    # (``RowFloors.unit_roundoff``; None: not recorded): the resolution
    # bound of ``withhold`` reads it.
    floor_roundoff: float | None = None


class ProbePointRefused(ArithmeticError):
    """The native backend refused a probe run's point or lane in the
    probe's carrier (``_probe_runs``): the probe has no verdict there (the
    generation-time probes re-run it in double-double, ``generation_probes``)."""


def _probe_batch(executor, runs, scale, parameters, precision, frame, term_scale=False):
    """One native batch of probe runs, (point, Ward value or None) each, at
    one scale, with the reduction re-test in ``frame`` (None: none), the raw
    lanes (``rotation_errors`` sums its deviations over them) and, with
    ``term_scale``, the term scale: (the carrier's precision, the
    evaluations, the failures per run index; a failed run's evaluation is
    unassembled). The points of a batch run concurrently."""

    wards = [ward for _point, ward in runs]
    executor.term_scale = term_scale
    raw, executor.raw_lanes = executor.raw_lanes, True
    try:
        return executor._evaluated(
            [point for point, _ward in runs],
            [scale] * len(runs),
            dict(parameters or {}),
            precision,
            "all",
            frame,
            "B",
            None if all(ward is None for ward in wards) else wards,
        )
    finally:
        executor.term_scale = False
        executor.raw_lanes = raw


def _probe_runs(executor, runs, scale, parameters, precision, frame, term_scale=False):
    """``_probe_batch`` of runs that must all succeed: (the carrier's
    precision, the evaluations); a failed run raises ``ProbePointRefused``."""

    precision, evaluations, failures = _probe_batch(
        executor, runs, scale, parameters, precision, frame, term_scale
    )
    if failures:
        index = min(failures)
        raise ProbePointRefused(f"the probe point failed: {failures[index]}")
    return precision, evaluations


def physical_floors(
    executor: Any,
    point: Sequence[Sequence[Any]],
    scale: Any,
    parameters: Mapping[str, str] | None = None,
    precision: Any = None,
) -> dict:
    """The row term floors (``row_scales``) of the physical amplitude at a
    point, from a binary64 run with the term scale: a scale is a magnitude,
    which binary64 gives far better than the x10 rule needs, while the term
    scale's unit-numerator reductions (C(R + 4, 4) per family) cost 51 s in
    double-double against 3 s in binary64 on g g > z z g. Where the
    numerators cancel term by term (a Furry zero) the floor is rounding in
    either carrier; the rotation budget carries those probes
    (``rotation_errors``). ``precision``: the run's carrier (default
    binary64; the generation-time probes take double-double only where the
    backend refuses the binary64 run, ``probe_floors``)."""

    from .assemble import Precision

    _carrier, (evaluation,) = _probe_runs(
        executor,
        [(point, None)],
        scale,
        parameters,
        precision or Precision.double(),
        None,
        True,
    )
    floors = row_floors(evaluation)
    floors.unit_roundoff = _carrier.unit_roundoff
    return floors


class RowFloors(dict):
    """Per (loop order, row) the term floor T_k of each Laurent coefficient
    (``row_scales``), with ``finite``: per row the colour-metric norm of the
    physical finite amplitude ||a_0(h)||, the probes' physical reference P
    (None where it cannot be computed), and ``unit_roundoff``: that of the
    carrier that produced them (None: not recorded)."""

    finite: dict
    unit_roundoff: float | None = None


def row_floors(evaluation: Any) -> RowFloors:
    """``RowFloors`` of a physical evaluation: its row term floors and the
    norm of each row's finite amplitude."""

    floors = RowFloors(row_scales(evaluation))
    numbers = evaluation.numbers
    gram = evaluation.gram
    size = len(evaluation.slice.amplitude)
    with numbers.scope():
        floors.finite = {
            key: _finite(g_norm([vector[t][0] for t in range(size)], gram, numbers))
            for key, vector in evaluation.amplitude_vectors.items()
        }
    return floors


def probe_floors(
    executor: Any,
    point: Sequence[Sequence[Any]],
    scale: Any,
    parameters: Mapping[str, str] | None = None,
) -> tuple[dict, dict[str, Any]]:
    """The physical row floors of the generation-time probes
    (``physical_floors``) in binary64, or in double-double where the backend
    refuses the binary64 run (a scale is a magnitude: either carrier serves
    it); with the record of the carrier that formed them."""

    from .assemble import Precision

    try:
        return physical_floors(executor, point, scale, parameters), {
            "carrier": Precision.double().arithmetic
        }
    except ProbePointRefused as error:
        precision = Precision.double_double()
        floors = physical_floors(executor, point, scale, parameters, precision)
        return floors, {
            "carrier": precision.arithmetic,
            "fallback": {"reason": "refused", "detail": str(error)},
        }


def ward_floors(physical: Mapping, leg: int) -> RowFloors:
    """The term floors and physical references a Ward probe of leg ``leg``
    (1-based) stands on: per (loop order, row) the largest physical floor
    and the largest physical finite-amplitude norm (``RowFloors.finite``)
    over the rows that differ from it only in that leg's helicity (the
    substituted leg reads one vector for every helicity, so its rows repeat
    the same amplitude)."""

    def merged(row):
        return tuple((i, 0 if i == leg - 1 else h) for i, h in row)

    out: dict = {}
    for (order, row), values in physical.items():
        key = (order, merged(row))
        found = out.get(key)
        out[key] = (
            list(values)
            if found is None
            else [max(a, b) for a, b in zip(found, values, strict=True)]
        )
    floors = RowFloors(
        {(order, row): out[(order, merged(row))] for order, row in physical}
    )
    finite = getattr(physical, "finite", None) or {}
    widest: dict = {}
    for (order, row), value in finite.items():
        key = (order, merged(row))
        known = widest.get(key, 0.0)
        widest[key] = None if value is None or known is None else max(known, value)
    floors.finite = {
        (order, row): widest[(order, merged(row))] for order, row in finite
    }
    floors.unit_roundoff = getattr(physical, "unit_roundoff", None)
    return floors


def probe(
    executor: Any,
    point: Sequence[Sequence[Any]],
    scale: Any,
    *,
    parameters: Mapping[str, str] | None = None,
    precision: Any = None,
    ward: Any = None,
    checks: Any = None,
    physical: Mapping | None = None,
    tolerance: float | None = None,
) -> ProbeResult:
    """The finiteness probe (``ward`` None) or the amplitude-level Ward
    probe of a loop-induced point on a native executor of its slice
    (``plan_export.NativeExecutor``; PLAN §2.a.7, items 5-6).

    * **Finiteness**: a one-loop amplitude without a tree is IR finite and,
      renormalised, UV finite, so its pole coefficients a_{-1}, a_{-2}
      vanish per (loop order, row) in the colour-metric norm; each is
      measured against its estimate on the row's term floor (DECISIONS
      2026-11-06 ~09:00 (1)): a missing family, a wrong scaleless drop or a
      wrong master shows here (it replaces Catani for loop-induced).
    * **Ward** (``ward``: a Ward value, ``ward.gauge_ward``: epsilon_j ->
      c p_j / E_j of a massless gauge boson j): the amplitude with leg j's
      polarisation replaced vanishes at every Laurent coefficient; the bare
      part alone does not, the R2 counterterms restore it, so a missing R2
      vertex shows here (invisible to the poles). The slice must be on the
      full tree kernels (``ward.ward_slice``). Widths enter the probe as
      the caller's parameters (zero widths outside the complex-mass scheme,
      m-lit Q7). The residue is measured against the PHYSICAL amplitude's
      term floor (``ward_floors``; ``physical``: the row floors of the
      physical evaluation at the same point, ``ProbeResult.scales`` of its
      finiteness probe, ``physical_floors`` when not given), as ``ward.py``'s
      criterion measures against the physical evaluation: the substituted
      amplitude's own floor can be at rounding (the numerators of g g > h
      vanish term by term), which would make its estimate meaningless.

    ``checks`` (``stability.StabilityChecks``; default the calibrated
    ``RECOMMENDED_CHECKS``: the rescaled reduction re-test and one generic
    rotation) are the estimate's checks: the re-test runs at the probe's
    precision, each rotation re-evaluates the rotated point (a Ward value
    rotates with it, ``ward.rotated_ward``) and enters by
    ``rotation_errors``, which also covers residues that are rounding of a
    cancellation inside the family numerators (a Furry zero), where the
    term floor is at rounding itself."""

    (result,) = probes(
        executor,
        point,
        scale,
        [ward],
        parameters=parameters,
        precision=precision,
        checks=checks,
        physical=physical,
        tolerance=tolerance,
    )
    return result


def probes(
    executor: Any,
    point: Sequence[Sequence[Any]],
    scale: Any,
    wards: Sequence[Any],
    *,
    parameters: Mapping[str, str] | None = None,
    precision: Any = None,
    checks: Any = None,
    physical: Mapping | None = None,
    tolerance: float | None = None,
) -> list[ProbeResult]:
    """``probe`` for every Ward value of ``wards`` (None: the finiteness
    probe) at one point: the probes' runs in one native batch with the
    re-test, their rotated runs in another without it. A run the backend
    refuses raises ``ProbePointRefused`` (``probe_results`` returns it per
    probe instead)."""

    found = probe_results(
        executor,
        point,
        scale,
        wards,
        parameters=parameters,
        precision=precision,
        checks=checks,
        physical=physical,
        tolerance=tolerance,
    )
    for result in found:
        if isinstance(result, str):
            raise ProbePointRefused(result)
    return found


def probe_results(
    executor: Any,
    point: Sequence[Sequence[Any]],
    scale: Any,
    wards: Sequence[Any],
    *,
    parameters: Mapping[str, str] | None = None,
    precision: Any = None,
    checks: Any = None,
    physical: Mapping | None = None,
    tolerance: float | None = None,
) -> list[ProbeResult | str]:
    """``probes``, with a probe whose direct run the backend refuses in the
    carrier returned as the refusal's text ("the probe point failed: ..."),
    the other probes' results unchanged (the runs of a batch are
    independent points). The physical evaluation (Ward value None) is in
    every batch: its finite amplitude per row is the probes' physical
    reference P with its estimate E_P (``physical_references``), at the same
    point and carrier as the residues; refused, the rows have no P
    (inconclusive). A refused rotated run only drops that rotation from the
    estimates (R, P and T do not read it). ``tolerance``: K (None:
    ``checks.tolerance``)."""

    from .assemble import Precision, _fraction
    from .stability import RECOMMENDED_CHECKS
    from .ward import rotated_ward, ward_leg

    precision = precision or Precision.double_double()
    tolerance = _default_tolerance() if tolerance is None else tolerance
    checks = RECOMMENDED_CHECKS if checks is None else checks
    frame = checks.frame
    if frame is None:
        raise ValueError("a probe needs the reduction re-test")
    runs_of = list(wards) if None in wards else [*wards, None]
    reference = runs_of.index(None)
    exact = tuple(tuple(_fraction(x) for x in p) for p in point)
    moved = [rotation.apply(exact) for rotation in checks.rotations]
    stride = len(moved)
    # Two batches: the probes' runs with the re-test, their rotated runs
    # without it (a rotation compares values, ``rotation_errors``).
    carrier, evaluations, failures = _probe_batch(
        executor,
        [(point, ward) for ward in runs_of],
        scale,
        parameters,
        precision,
        frame,
    )
    refused: dict[int, str] = {
        index: f"the probe point failed: {failures[index]}" for index in failures
    }
    rotated = []
    turned_failures: dict = {}
    if moved:
        _carrier, rotated, turned_failures = _probe_batch(
            executor,
            [
                (turned, None if ward is None else rotated_ward(rotation, ward))
                for ward in runs_of
                for rotation, turned in zip(checks.rotations, moved, strict=True)
            ],
            scale,
            parameters,
            precision,
            None,
        )
    # The term floor is the physical amplitude's, a magnitude: formed once in
    # binary64 (``physical_floors``; in double-double the term scale's unit
    # reductions would dominate the probe's cost) and shared by the Ward
    # probes of the point (``physical``).
    if physical is None:
        physical = physical_floors(executor, point, scale, parameters)

    def estimates_of(index: int, floors: Mapping) -> tuple[dict, list]:
        evaluation = evaluations[index]
        kept = [
            run
            for position, run in enumerate(
                rotated[index * stride : (index + 1) * stride], start=index * stride
            )
            if position not in turned_failures
        ]
        turned = [rotation_errors(evaluation, run) for run in kept]
        return (
            amplitude_estimates(evaluation, carrier.unit_roundoff, floors, turned),
            [evaluation, *kept],
        )

    references = None
    if reference not in refused:
        references = physical_references(estimates_of(reference, physical)[0])
    out: list[ProbeResult | str] = []
    for index, ward in enumerate(wards):
        if index in refused:
            out.append(refused[index])
            continue
        floors = physical if ward is None else ward_floors(physical, ward_leg(ward))
        estimates, runs = estimates_of(index, floors)
        refs = (
            None
            if references is None
            else references
            if ward is None
            else ward_references(references, ward_leg(ward))
        )
        measures = probe_measures(
            estimates,
            floors,
            0 if ward is not None else 1,
            refs,
            width_of(evaluations[index]),
        )
        out.append(
            ProbeResult(
                "ward" if ward is not None else "finiteness",
                judged_cells(measures, tolerance, carrier),
                MappingProxyType(physical),
                uncertified=any(
                    getattr(run, "uncertified_bound", None) for run in runs
                ),
                tolerance=tolerance,
                floor_roundoff=getattr(floors, "unit_roundoff", None),
            )
        )
    return out


# ------------------------------------------------- generation-time probes


class ProbeFailure(ArithmeticError):
    """A generation-time probe of a loop-induced request that fails R < K S
    (``checks.threshold``; m-lit Q12: generation fails unless
    overridden)."""

    refusal_key = "loop-induced-probe"


def probe_request(slice_: Any) -> tuple[Any, tuple[str, ...]]:
    """The request of the generation-time probe slice and the widths it
    zeroes (m-lit Q7, ``ew_policy.probe_widths``): outside the complex-mass
    scheme every external width parameter of the model that is not zero is
    fixed to 0 (a fixed width in a tree propagator breaks the Ward identity
    of an external photon or gluon line it attaches to, so the probe would
    fail spuriously); under the complex-mass scheme the widths stay (the
    scheme is gauge invariant). The production artifact keeps its widths."""

    return probe_request_of(slice_.compiled, slice_.request)


def probe_request_of(compiled: Any, request: Any) -> tuple[Any, tuple[str, ...]]:
    """``probe_request`` of a slice request on its compiled model, before any
    slice exists (``pyamplicol check`` generates only the probe slice)."""

    from dataclasses import replace

    from .ew_policy import probe_widths

    fixed, zeroed = probe_widths(compiled, request.fixed_parameters)
    if not zeroed:
        return request, ()
    return replace(request, fixed_parameters=fixed), zeroed


def probe_point(
    slice_: Any, momenta: Sequence[Sequence[float]], digits: int
) -> tuple[list[list[str]], float | None]:
    """A probe point of the slice's process lifted from a binary64 phase-space
    point (``generation.validation``: decays at rest, scatterings in the
    centre-of-mass frame with the beams along +-z), with momentum
    conservation exact and every mass shell within 10^-digits relative, so
    the probe's residues measure the amplitude, not the point.

    The final three-momenta are read exactly, the last one replaced by minus
    the sum of the others; a scattering's final energies are the on-shell
    ones and its beams carry their total along +-z; a decay's final momenta
    are scaled (Newton, at ``digits``) so that their energies add up to the
    decaying mass. Masses are the slice's (``assemble._leg_masses`` at the
    generation parameters). Returns the decimal strings and the point's
    smallest relative distance |s_I - M^2| / M^2 over the invariants of
    every leg subset I with 2 <= |I| <= n - 2 (a tree propagator's) and
    every massive particle of the model (None without such a subset)."""

    from decimal import Decimal, localcontext
    from itertools import combinations

    from .assemble import _leg_masses

    legs = sorted(slice_.blocks.process.legs, key=lambda leg: leg.label)
    count = sum(1 for leg in legs if leg.is_initial)
    squares = _leg_masses(slice_, slice_.request.fixed_parameters, digits + 10)
    with localcontext() as context:
        context.prec = digits + 10

        def exact(value: Any) -> Fraction:
            return value if isinstance(value, Fraction) else Fraction(value)

        def root(value: Fraction) -> Fraction:
            if value <= 0:
                return Fraction(0)
            return exact(
                Decimal(value.numerator).sqrt() / Decimal(value.denominator).sqrt()
            )

        final = [
            [Fraction(float(x)) for x in momentum[1:]] for momentum in momenta[count:]
        ]
        final[-1] = [-sum(p[i] for p in final[:-1]) for i in range(3)]
        spatial = [sum(x * x for x in p) for p in final]
        masses = squares[count:]

        def energies(scale: Fraction) -> list[Fraction]:
            return [
                root(scale * scale * q + m)
                for q, m in zip(spatial, masses, strict=True)
            ]

        scale = Fraction(1)
        if count == 1:
            target = root(squares[0])
            for _ in range(digits):
                values = energies(scale)
                error = sum(values) - target
                slope = sum(
                    scale * q / e for q, e in zip(spatial, values, strict=True) if e
                )
                if not slope:
                    break
                step = exact(Decimal(error.numerator) / Decimal(error.denominator))
                step = exact(
                    Decimal(step.numerator)
                    / Decimal(step.denominator)
                    / (Decimal(slope.numerator) / Decimal(slope.denominator))
                )
                scale -= step
                if abs(step) <= Fraction(1, 10 ** (digits + 5)) * abs(scale):
                    break
        values = energies(scale)
        final_momenta = [
            [e, *(scale * x for x in p)] for e, p in zip(values, final, strict=True)
        ]
        total = sum(values)
        if count == 1:
            initial = [[total, Fraction(0), Fraction(0), Fraction(0)]]
        else:
            first, second = squares[0], squares[1]
            energy = (total * total + first - second) / (2 * total)
            pz = root(energy * energy - first)
            initial = [
                [energy, Fraction(0), Fraction(0), pz],
                [total - energy, Fraction(0), Fraction(0), -pz],
            ]
        point = [*initial, *final_momenta]
        massive = sorted(
            {
                square
                for square in (
                    _particle_square(slice_, record, digits)
                    for record in slice_.compiled.ir.particles
                )
                if square
            }
        )
        outgoing = [
            [(-x if index < count else x) for x in p] for index, p in enumerate(point)
        ]
        distance = None
        for size in range(2, len(point) - 1):
            for subset in combinations(range(len(point)), size):
                p = [sum(outgoing[i][mu] for i in subset) for mu in range(4)]
                invariant = p[0] * p[0] - p[1] * p[1] - p[2] * p[2] - p[3] * p[3]
                for square in massive:
                    gap = float(abs(invariant - square) / square)
                    distance = gap if distance is None else min(distance, gap)
        text = [
            [
                str(Decimal(x.numerator) / Decimal(x.denominator))
                if x.denominator != 1
                else str(x.numerator)
                for x in p
            ]
            for p in point
        ]
    return text, distance


def _particle_square(slice_: Any, record: Any, digits: int) -> Fraction | None:
    """A model particle's squared mass at the generation parameters (None if
    massless or not a real mass, e.g. a complex-mass scheme's pole mass)."""

    from .assemble import _model_masses

    mass = str(record.mass)
    try:
        value = _model_masses(slice_.compiled, slice_.request.fixed_parameters, digits)(
            mass
        )
    except (KeyError, ValueError):
        return None
    if not isinstance(value, Fraction) or not value:
        return None
    return value * value


# The reduction backend of the generation-time probes: NinjaRS at every
# carrier, named in the record (requested / effective / reason); never the
# artifact's run-time choice (``reduction.resolve``), so a change of the
# run-time 'auto' rule never moves the probes silently.
PROBE_REDUCTION = "ninjars"
PROBE_REDUCTION_REASON = (
    "the generation-time probes reduce on NinjaRS at every carrier (their "
    "x10 estimate, re-test and rotation, is calibrated there; m-lit Q12)"
)


def probe_carriers(precision: Any = None) -> tuple[Any, ...]:
    """The carriers of the generation-time probes, in order: binary64, then
    double-double for a probe whose binary64 run fails its verdict or is
    refused (DECISIONS 2026-11-08 22:34 (3)); ``precision`` given: that
    carrier alone (no fallback)."""

    from .assemble import Precision

    if precision is not None:
        return (precision,)
    return (Precision.double(), Precision.double_double())


def probe_lanes(runs: int) -> int:
    """The lanes of a probe executor: the smallest power of two holding its
    largest batch (``runs`` probe points, or their rotated copies under
    ``stability.RECOMMENDED_CHECKS``), at most the executor's default. A
    binary64 chunk costs its full lane count however few points it holds
    (``NativeExecutor.lanes_for``); the other carriers already size their
    lanes to the batch, so they run as before."""

    from .plan_export import DEFAULT_LANES
    from .stability import RECOMMENDED_CHECKS

    batch = runs * max(1, len(RECOMMENDED_CHECKS.rotations))
    lanes = 1
    while lanes < min(batch, DEFAULT_LANES):
        lanes *= 2
    return lanes


def _fallback(result: Any) -> dict[str, Any]:
    """An earlier carrier's outcome of a probe (the next carrier re-ran its
    pending rows): the backend's refusal, or its verdict and largest R over
    its scale."""

    if isinstance(result, str):
        return {"reason": "refused", "detail": result}
    return {
        "reason": "verdict",
        "verdict": result.verdict,
        "worst": _short(result.worst),
    }


def ladder(
    cells: dict[Any, Any],
    result: Any,
    carrier: Any,
    tolerance: float,
) -> None:
    """One carrier of a probe's per-row ladder (``checks.ladder_step``), in
    place on ``cells``: a refused run leaves its pending rows inconclusive
    for the next carrier to decide; a result's rows are judged where still
    pending (a decided row keeps its first decision, a pending row the
    carrier lacks is inconclusive)."""

    from .checks import ladder_step, refused_step

    name = carrier.arithmetic
    if isinstance(result, str):
        refused_step(cells, result, name)
        return
    ladder_step(
        cells,
        {key: cell.measure for key, cell in result.cells.items()},
        name,
        carrier.unit_roundoff,
        tolerance,
    )
    withhold(cells, result, carrier)


# The reason of a loop-induced row whose miss is deferred (``withhold``).
BELOW_RESOLUTION = "helicity row below numerical resolution"


def withhold(cells: dict[Any, Any], result: Any, carrier: Any) -> list[Any]:
    """Defer an otherwise failing loop-induced row whose operands are all at
    the numerical resolution of its comparable helicities (the reviewer's
    ruling on g g > Z), in place on ``cells``; returns the deferred keys.

    A row that FAILs at ``carrier`` (the ordinary per-row test, ``checks.
    ladder_step``; a physical reference that reproduced between carriers
    keeps its decision) is deferred only when all of the following hold at
    this carrier:

    * its comparison is complete: R, P, T and E_P finite and nonnegative,
      P measured (not a known-zero reference) and P <= ESTIMATE_FACTOR E_P;
    * T_max, the largest term floor of the rows of the same probe at this
      point with the same loop order and Laurent coefficient (the comparable
      helicities; no other sector, coefficient, point or backend), is finite
      and positive;
    * max(R, P, T) <= ESTIMATE_FACTOR min(u_floor, u_work) T_max, u_floor
      the unit roundoff of the carrier that produced the term floors
      (``ProbeResult.floor_roundoff``; not recorded: nothing is deferred),
      u_work this carrier's.

    A deferred row is INCONCLUSIVE ("helicity row below numerical
    resolution"), with its operands and carrier kept: it is pending, so the
    next carrier evaluates it again and the ordinary rule judges its actual
    measurements there (a resolved physical reference or a significant
    residue decides; a row ambiguous on its own row at that carrier is
    settled by the existing rule); at the last carrier it stays
    INCONCLUSIVE. The deferral never passes a row, never settles it
    term-relative and never makes it vacuous."""

    from dataclasses import replace

    from .checks import FAIL, INCONCLUSIVE

    floor = getattr(result, "floor_roundoff", None)
    work = getattr(carrier, "unit_roundoff", None)
    cells_of = getattr(result, "cells", None)
    if floor is None or work is None or not cells_of:
        return []
    u = min(floor, work)

    def group(key: Any) -> Any:
        try:
            (order, _row), k = key
        except (TypeError, ValueError):
            return None
        return (order, k)

    largest: dict[Any, float] = {}
    for key, cell in cells_of.items():
        t = cell.measure.terms
        g = group(key)
        if g is None or t is None or not math.isfinite(t) or t < 0:
            continue
        largest[g] = max(largest.get(g, 0.0), t)
    deferred = []
    for key, cell in list(cells.items()):
        if cell.verdict != FAIL or cell.carrier != carrier.arithmetic:
            continue
        if (cell.reason or "").startswith("P reproduces"):
            continue
        m = cell.measure
        operands = (m.residue, m.physical, m.terms, m.physical_error)
        if (
            m.zero_reference
            or not m.complete
            or any(x is None or not math.isfinite(x) or x < 0 for x in operands)
            or m.physical > ESTIMATE_FACTOR * m.physical_error
        ):
            continue
        t_max = largest.get(group(key))
        if t_max is None or not math.isfinite(t_max) or t_max <= 0:
            continue
        bound = ESTIMATE_FACTOR * u * t_max
        size = max(m.residue, m.physical, m.terms)
        if size > bound:
            continue
        order, k = group(key)
        cells[key] = replace(
            cell,
            verdict=INCONCLUSIVE,
            reason=(
                f"{BELOW_RESOLUTION}: max(R, P, T) {size:.3g} <= "
                f"{ESTIMATE_FACTOR} min(u_floor, u_work) T_max {bound:.3g} "
                f"(T_max {t_max:.3g} over the helicities of {order} k={k}; "
                f"floors at u {floor:.3g}, {carrier.arithmetic} at u {work:.3g}; "
                f"R {m.residue:.3g}, P {m.physical:.3g} <= {ESTIMATE_FACTOR} E_P "
                f"{m.physical_error:.3g}, T {m.terms:.3g}): an otherwise failing "
                "miss deferred to a wider carrier, inconclusive at the last"
            ),
        )
        deferred.append(key)
    return deferred


def pending(cells: Mapping[Any, Any], runs: Sequence[Any]) -> bool:
    """Whether a probe still has a row to decide (or no measured row yet)."""

    if not cells:
        return True
    return any(cell.verdict not in ("pass", "vacuous") for cell in cells.values())


def _decided(
    entries: list[dict[str, Any]],
    outcomes: Sequence[Any],
    carriers: Sequence[Any],
    cells: Sequence[dict[Any, Any]],
    tolerance: float,
) -> list[Any]:
    """The verdict of each probe from its rows' final verdicts up the ladder
    (``cells``; a probe no carrier measured keeps its last refusal text:
    inconclusive, never a pass); ``entries`` gets the record per probe: the
    deciding row's carrier, ``passed``, ``verdict``, the largest R over its
    scale (``worst``) and K (``tolerance``), the reason of an inconclusive
    or vacuous one, each earlier carrier's outcome (``fallback``)."""

    from dataclasses import replace

    out = []
    for entry, runs, rows in zip(entries, outcomes, cells, strict=True):
        measured = [run for run in runs if not isinstance(run, str)]
        if not rows or not measured:
            result = runs[-1]
            carrier = carriers[len(runs) - 1]
            entry["carrier"] = carrier.arithmetic
            entry["passed"] = False
            entry["verdict"] = "inconclusive"
            entry["refused"] = result
            entry["inconclusive"] = f"refused in {carrier.arithmetic}: {result}"
        else:
            result = replace(
                measured[-1],
                cells=dict(rows),
                uncertified=any(run.uncertified for run in measured),
                tolerance=tolerance,
            )
            # The last carrier a row needed (every row decided by then).
            order = [carrier.arithmetic for carrier in carriers]
            used = [
                order.index(cell.carrier)
                for cell in rows.values()
                if cell.carrier in order
            ]
            entry["carrier"] = order[max(used)] if used else order[len(runs) - 1]
            entry["worst"] = _short(result.worst)
            entry["tolerance"] = tolerance
            entry["verdict"] = result.verdict
            entry["passed"] = result.passed
            if result.verdict == "inconclusive":
                entry["inconclusive"] = result.reason
            elif result.verdict == "vacuous":
                entry["vacuous"] = result.reason
            deferred = sum(
                1
                for cell in result.final.values()
                if (cell.reason or "").startswith(BELOW_RESOLUTION)
            )
            if deferred:
                # Rows whose miss ``withhold`` deferred: inconclusive, the
                # operands at the resolution of their helicities.
                entry["below_resolution"] = deferred
            if result.uncertified:
                entry["uncertified"] = True
        fallbacks = [
            {"carrier": carriers[i].arithmetic, **_fallback(run)}
            for i, run in enumerate(runs[:-1])
        ]
        if fallbacks:
            entry["fallback"] = fallbacks if len(fallbacks) > 1 else fallbacks[0]
        out.append(result)
    return out


def probe_legs(target: Any) -> list[int]:
    """The legs of the amplitude-level Ward probes of a probe slice: one per
    external gauge-boson species (its first leg; Bose symmetry relates the
    others; ``ward.gauge_legs``: gluons and photons)."""

    from .ward import gauge_legs

    species = {int(leg.label): int(leg.pdg) for leg in target.blocks.process.legs}
    first: dict[int, int] = {}
    for leg in gauge_legs(target):
        first.setdefault(species[leg], leg)
    return sorted(first.values())


def point_probes(
    executor: Any,
    point: Sequence[Sequence[Any]],
    scale: Any,
    legs: Sequence[int],
    carriers: Sequence[Any],
    floors: Mapping,
    seconds: dict[str, Any] | None = None,
    improve: Callable[[Any, Any, Any], tuple[Any, str | None]] | None = None,
    tolerance: float | None = None,
) -> tuple[list[dict[str, Any]], list[Any]]:
    """The finiteness probe and the Ward probe of every leg of ``legs``
    (``probe_legs``) at one lifted point (``probe_point``) of a probe
    slice's executor, in ``carriers`` in order (``probe_carriers``), judged
    with tolerance K (``tolerance``; None: ``checks.tolerance``): a probe
    that does not pass (a failure, an inconclusive verdict or a refused run)
    runs again in the next one only. The Ward probes are at c = 1: the
    amplitude is linear in the substituted vector, so c = i (needed where an
    interference takes a real part, ``ward.WARD_FACTORS``) has the same
    norm. ``floors`` are the
    point's physical row floors (``probe_floors``); ``seconds`` gets each
    carrier's pass time. Returns the per-probe record entries (``_decided``)
    and each probe's deciding result (a ``ProbeResult`` or a refusal text),
    finiteness first. ``improve`` (``pyamplicol check``'s rungs only, m-lit
    lit-psimprove (G5); None at generation, whose records are unchanged):
    the point a carrier evaluates and its record's short form, per carrier
    from the lifted point (each entry's ``"kinematics"``, by carrier)."""

    from .ward import gauge_ward

    entries: list[dict[str, Any]] = [{"probe": "finiteness"}] + [
        {"probe": "ward", "leg": leg} for leg in legs
    ]
    tolerance = _default_tolerance() if tolerance is None else tolerance
    outcomes: list[list[Any]] = [[] for _ in entries]
    cells: list[dict[Any, Any]] = [{} for _ in entries]
    waiting = list(range(len(entries)))
    for carrier in carriers:
        if not waiting:
            break
        rung, improved = (
            (point, None) if improve is None else improve(point, scale, carrier)
        )
        wards = [None, *(gauge_ward(leg, (1, 0), rung) for leg in legs)]
        if improved is not None:
            for i in waiting:
                entries[i].setdefault("kinematics", {})[carrier.arithmetic] = improved
        clock = time.perf_counter()
        found = probe_results(
            executor,
            rung,
            scale,
            [wards[i] for i in waiting],
            precision=carrier,
            physical=floors,
            tolerance=tolerance,
        )
        elapsed = time.perf_counter() - clock
        if seconds is not None:
            seconds[carrier.arithmetic] = elapsed
        for i, result in zip(waiting, found, strict=True):
            outcomes[i].append(result)
            ladder(cells[i], result, carrier, tolerance)
            # The probes of one pass share its native batches.
            entries[i]["seconds"] = _seconds(entries[i].get("seconds", 0.0) + elapsed)
        waiting = [i for i in waiting if pending(cells[i], outcomes[i])]
    return entries, _decided(entries, outcomes, carriers, cells, tolerance)


def generation_probes(
    slice_: Any,
    compiled: Any,
    native: Any,
    candidates: Sequence[Sequence[Sequence[float]]],
    *,
    allow_failure: bool = False,
    precision: Any = None,
    memo: Any = None,
    tolerance: float | None = None,
) -> dict[str, Any]:
    """The generation-time probes of a loop-induced slice (m-lit Q12, PLAN
    §2.a.7 items 5-6), run only when the user enables them
    (``generation.loop_induced_probes``, off by default: DECISIONS
    2026-11-08 22:34 (3); nothing the artifact stores or evaluates depends
    on them): the finiteness probe and, on one leg of every external
    massless gauge-boson species (gluons and photons), the amplitude-level
    Ward probe epsilon_j -> p_j / E_j, on a slice of the request generated
    on the full tree kernels at zero widths outside the complex-mass scheme
    (``probe_request``; the production slice itself when it already is
    one). The point is the candidate binary64 point (``candidates``, the
    generation's validation points) farthest from every tree pole, lifted
    once by ``probe_point`` at the digits of the last carrier, so that every
    carrier evaluates the same exact point.

    Every probe runs first in binary64 (``probe_carriers``); a probe whose
    binary64 run fails its verdict or is refused by the backend
    (``ProbePointRefused``) is re-run in double-double, and only those (the
    term floors stay binary64, formed once per point, ``probe_floors``).
    ``precision`` given: that carrier alone (a measurement of one carrier).
    A probe is judged as ``pyamplicol check`` judges it (``checks.
    threshold``: R < K S per row and coefficient, K = ``tolerance``, None:
    ``checks.tolerance``); its verdict is the first passing carrier's, else
    the last one's. A decisive failure after the fallback raises
    ``ProbeFailure`` unless ``allow_failure`` (recorded); an inconclusive
    probe (R or S cannot be computed, or every carrier refused it) is
    recorded (``inconclusive``, never a pass) and generation continues. An
    exact colour zero has nothing to probe. Massive external vectors take
    the Goldstone-equivalence probe (``goldstone``, m-lit LIT-EW) on one leg
    of every species with a Goldstone partner, in a 't Hooft-Feynman gauge
    request only (the identity needs the Goldstone vertices; a QCD-only
    request in unitary gauge has its both-gauges equality as a validation
    check instead), with the same carriers, recorded as ``goldstone``. The
    probes reduce on ``PROBE_REDUCTION`` (recorded).

    Returns the record the artifact stores (``generation_filters``): per
    probe the carrier that decided, its worst ratio, the fallback's reason
    (the binary64 ratio or the refusal) and its time, and the time of each
    stage (``seconds``: the probe slice, the lift, the floors, the native
    passes per carrier, the Goldstone slices and probes, the total).
    ``memo`` (the generation's ``preparation_cache.PreparationMemo``)
    shares the probe and Goldstone slices' model preparation with the
    generation's."""

    from .plan_export import NativeExecutor
    from .reduction import running
    from .ward import ward_slice

    if slice_.amplitude.colour_zero:
        return {"exact_colour_zero": True}

    carriers = probe_carriers(precision)
    tolerance = _default_tolerance() if tolerance is None else float(tolerance)
    start = time.perf_counter()
    seconds: dict[str, Any] = {}
    with running(PROBE_REDUCTION):
        request, zeroed = probe_request(slice_)
        blocks = slice_.blocks
        if zeroed or getattr(blocks, "kernel_variant", None) != "full":
            clock = time.perf_counter()
            target = ward_slice(compiled, request, native, memo=memo)
            seconds["probe_slice"] = time.perf_counter() - clock
        else:
            target = slice_
            seconds["probe_slice"] = 0.0
        clock = time.perf_counter()
        digits = 2 * max(carrier.working_digits for carrier in carriers)
        lifted = [probe_point(target, momenta, digits) for momenta in candidates]
        index = max(
            range(len(lifted)),
            key=lambda i: float("inf") if lifted[i][1] is None else lifted[i][1],
        )
        point, distance = lifted[index]
        legs = probe_legs(target)
        executor = NativeExecutor(
            target, forward=False, inputs="native", lanes=probe_lanes(1 + len(legs))
        )
        scale = _point_scale(
            point, sum(1 for leg in blocks.process.legs if leg.is_initial)
        )
        seconds["point"] = time.perf_counter() - clock
        clock = time.perf_counter()
        try:
            floors, floors_record = probe_floors(executor, point, scale)
        except ProbePointRefused as error:
            # Every carrier refused the physical evaluation that forms the
            # row floors T: the probes are inconclusive (recorded, a
            # warning), generation continues.
            floors, floors_record = None, {"refused": str(error)}
        seconds["floors"] = time.perf_counter() - clock
        if floors is None:
            text = f"the physical floors (T) were refused: {floors_record['refused']}"
            entries = [{"probe": "finiteness"}] + [
                {"probe": "ward", "leg": leg} for leg in legs
            ]
            for entry in entries:
                entry.update(
                    carrier=carriers[-1].arithmetic,
                    passed=False,
                    verdict="inconclusive",
                    refused=text,
                    inconclusive=text,
                )
            decided = [text] * len(entries)
        else:
            entries, decided = point_probes(
                executor,
                point,
                scale,
                legs,
                carriers,
                floors,
                seconds,
                tolerance=tolerance,
            )
        goldstones = _goldstone_probes(
            target,
            compiled,
            request,
            native,
            point,
            scale,
            carriers,
            floors,
            memo=memo,
            tolerance=tolerance,
        )
    entries += goldstones["entries"]
    seconds.update(goldstones["seconds"])
    seconds["total"] = time.perf_counter() - start

    def passed(result: Any) -> bool:
        return not isinstance(result, str) and result.passed

    def worst(result: Any) -> float:
        return float("inf") if isinstance(result, str) else result.worst

    record: dict[str, Any] = {
        "status": "run",
        "carriers": [carrier.arithmetic for carrier in carriers],
        "rule": rule_name(),
        "tolerance": tolerance,
        "reduction": {
            "requested": PROBE_REDUCTION,
            "effective": PROBE_REDUCTION,
            "reason": PROBE_REDUCTION_REASON,
        },
        "widths": "complex-mass" if not zeroed and _complex_mass(slice_) else "zero",
        **({"zeroed_widths": list(zeroed)} if zeroed else {}),
        "candidate": index,
        "pole_distance": None if distance is None else _short(distance),
        "lift_digits": digits,
        "floors": floors_record,
        "finiteness": {
            "worst": _short(worst(decided[0])),
            "passed": passed(decided[0]),
            "verdict": entries[0].get("verdict"),
            "carrier": entries[0]["carrier"],
        },
        "ward": {
            "legs": list(legs),
            "worst": _short(max((worst(r) for r in decided[1:]), default=0.0)),
            "passed": all(passed(r) for r in decided[1:]),
            "verdict": combined_verdict(
                [
                    entry.get("verdict")
                    for entry in entries[1:]
                    if entry["probe"] == "ward"
                ]
            ),
            "carriers": {
                str(entry["leg"]): entry["carrier"]
                for entry in entries
                if entry["probe"] == "ward"
            },
        },
        **({"goldstone": goldstones["record"]} if goldstones["record"] else {}),
        "probes": entries,
        "fallbacks": sum(1 for entry in entries if "fallback" in entry),
        "seconds": {
            key: (
                {k: _seconds(v) for k, v in value.items()}
                if isinstance(value, dict)
                else _seconds(value)
            )
            for key, value in seconds.items()
        },
    }

    def label(entry: dict[str, Any]) -> str:
        return f"{entry['probe']} probe" + (
            f" (leg {entry['leg']})" if "leg" in entry else ""
        )

    inconclusive = [
        f"{label(entry)}: inconclusive, {entry['inconclusive']} in {entry['carrier']}"
        for entry in entries
        if entry.get("verdict") == "inconclusive"
    ]
    if inconclusive:
        record["inconclusive"] = inconclusive
    vacuous = [
        f"{label(entry)}: {entry['vacuous']} in {entry['carrier']}"
        for entry in entries
        if entry.get("verdict") == "vacuous"
    ]
    if vacuous:
        record["vacuous"] = vacuous
    failed = [
        f"{label(entry)}: R / S {entry['worst']} not below K {tolerance:g} in "
        f"{entry['carrier']}"
        for entry in entries
        if entry.get("verdict") == "fail"
    ]
    if failed:
        record["failed"] = failed
        if not allow_failure:
            raise ProbeFailure(
                f"{slice_.request.process!r}: the loop-induced generation-time "
                f"probes failed ({'; '.join(failed)}; a probe passes iff R < K S "
                "for every row and coefficient, binary64 first and "
                "double-double where binary64 does not pass, m-lit Q12): a "
                "missing family or counterterm (finiteness), R2 vertex (Ward) "
                "or Goldstone-side vertex or counterterm (Goldstone). "
                "generation.allow_failed_probes = true stores the artifact "
                "anyway, with the failure recorded"
            )
        record["allowed_failure"] = True
    # Strict JSON for the artifact's manifest (an R / S can be inf or nan).
    return _json_safe(record)


def rule_name() -> str:
    """The checks' rule name (``checks.RULE``), recorded with K."""

    from .checks import RULE

    return RULE


def combined_verdict(verdicts: Sequence[Any]) -> str:
    """Several probes' verdicts as one: fail, else inconclusive (also for
    a missing one), else pass, else vacuous; "nothing tested" for none."""

    found = set(verdicts)
    if not found:
        return "nothing tested"
    for verdict in ("fail", "inconclusive"):
        if verdict in found:
            return verdict
    if None in found or not found <= {"pass", "vacuous"}:
        return "inconclusive"
    return "pass" if "pass" in found else "vacuous"


def _json_safe(value: Any) -> Any:
    """``value`` with every non-finite float as text ("inf", "-inf",
    "nan"): the artifact's manifest is strict JSON."""

    if isinstance(value, float) and not math.isfinite(value):
        return "nan" if math.isnan(value) else ("inf" if value > 0 else "-inf")
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def goldstone_applicability(target: Any) -> str | None:
    """None where the Goldstone-equivalence probe (``goldstone``) serves a
    probe slice, else why it does not: it needs the Goldstone vertices
    ('t Hooft-Feynman gauge, the gauge of every electroweak request) and an
    external massive vector with a Goldstone partner."""

    from . import goldstone

    if not goldstone.massive_vector_legs(target):
        return "no external massive vector with a Goldstone partner"
    if str(target.compiled.ir.gauge) != "feynman":
        return (
            f"a {target.compiled.ir.gauge}-gauge request has no Goldstone "
            "vertices (the identity k.A(V) = eta M_V A(G) needs 't Hooft-Feynman "
            "gauge, the gauge of an electroweak request)"
        )
    return None


def goldstone_sides(
    target: Any, compiled: Any, request: Any, native: Any, *, memo: Any = None
) -> tuple[dict[int, Any], dict[str, str], dict[str, float]]:
    """The Goldstone sides of a probe slice served by the probe
    (``goldstone_applicability``): per external massive-vector leg (one per
    species) its Goldstone slice (``goldstone.goldstone_slice``), the legs
    whose side the engine refuses with the refusal's text (key, rule and
    remedy), and each side's generation time. ``memo`` (the generation's
    ``preparation_cache.PreparationMemo``) shares the model preparation:
    a Goldstone side's recipe is its probe slice's."""

    from . import goldstone
    from .refusals import LoopRequestUnsupported

    sides: dict[int, Any] = {}
    skipped: dict[str, str] = {}
    slices: dict[str, float] = {}
    for leg, partner in goldstone.massive_vector_legs(target).items():
        clock = time.perf_counter()
        try:
            side = goldstone.goldstone_slice(
                compiled, request, native, target, leg, partner, memo=memo
            )
        except LoopRequestUnsupported as error:
            # The listed refusal's text: its key, rule and remedy.
            skipped[str(leg)] = str(error)
            continue
        slices[str(leg)] = time.perf_counter() - clock
        sides[leg] = side
    return sides, skipped, slices


def goldstone_point(
    target: Any,
    sides: Mapping[int, Any],
    point: Sequence[Sequence[Any]],
    scale: Any,
    carriers: Sequence[Any],
    physical: Mapping,
    executors: dict[Any, Any],
    tolerance: float | None = None,
) -> tuple[list[Any], list[dict[str, Any]], dict[str, Any], dict[str, float]]:
    """The Goldstone-equivalence probe of every side of ``sides``
    (``goldstone_sides``) at one lifted point, with the point's physical row
    floors, in ``carriers`` in order, judged with tolerance K
    (``tolerance``; None: ``checks.tolerance``): a probe that does not pass
    runs again in the next one. ``executors`` caches the native
    executors (the vector's under "vector", each side's under its leg)
    across points. Returns the (leg, result or refusal text) pairs, the
    per-probe record entries, the phases read and each probe's time."""

    from . import goldstone
    from .plan_export import NativeExecutor

    results: list[Any] = []
    entries: list[dict[str, Any]] = []
    phases: dict[str, Any] = {}
    probes_seconds: dict[str, float] = {}
    for leg, side in sides.items():
        clock = time.perf_counter()
        if "vector" not in executors:
            executors["vector"] = NativeExecutor(
                target, forward=False, inputs="native", lanes=probe_lanes(1)
            )
        if leg not in executors:
            executors[leg] = NativeExecutor(
                side, forward=False, inputs="native", lanes=probe_lanes(1)
            )
        runs: list[Any] = []
        rows: dict[Any, Any] = {}
        judged_at = _default_tolerance() if tolerance is None else tolerance
        for carrier in carriers:
            try:
                result = goldstone.probe(
                    executors["vector"],
                    executors[leg],
                    point,
                    scale,
                    leg,
                    precision=carrier,
                    physical=physical,
                    tolerance=judged_at,
                )
            except ProbePointRefused as error:
                result = str(error)
            runs.append(result)
            ladder(rows, result, carrier, judged_at)
            if not pending(rows, runs):
                break
        probes_seconds[str(leg)] = time.perf_counter() - clock
        entry: dict[str, Any] = {
            "probe": "goldstone",
            "leg": leg,
            "seconds": _seconds(probes_seconds[str(leg)]),
        }
        (result,) = _decided([entry], [runs], carriers, [rows], judged_at)
        entries.append(entry)
        results.append((leg, result))
        if not isinstance(result, str) and result.phase is not None:
            phases[str(leg)] = [_short(x) for x in result.phase]
    return results, entries, phases, probes_seconds


def _goldstone_probes(
    target,
    compiled,
    request,
    native,
    point,
    scale,
    carriers,
    physical,
    memo=None,
    tolerance=None,
) -> dict[str, Any]:
    """The Goldstone-equivalence probes of a probe slice (``goldstone``,
    m-lit LIT-EW): in a 't Hooft-Feynman gauge slice, one per external
    massive-vector species with a Goldstone partner, at the probe point,
    with the physical row floors of its finiteness probe, in ``carriers``
    in order (``probe_carriers``; None: binary64, then double-double): a
    probe whose run fails its verdict or is refused (``ProbePointRefused``)
    runs again in the next one. Returns the (leg, ``GoldstoneResult`` or
    refusal text) pairs, the per-probe record entries, the stage times and
    the record (None without such a leg); a Goldstone side the engine
    refuses is recorded as skipped, never a silent pass, and when every
    side is refused the probe did not run: the record is ``status``
    "not-run" with the refusals, and no ``passed``."""

    empty: dict[str, Any] = {
        "results": [],
        "entries": [],
        "seconds": {},
        "record": None,
    }
    if goldstone_applicability(target) is not None:
        return empty
    carriers = probe_carriers() if carriers is None else tuple(carriers)
    sides, skipped, slices = goldstone_sides(
        target, compiled, request, native, memo=memo
    )
    results, entries, phases, probes_seconds = goldstone_point(
        target, sides, point, scale, carriers, physical, {}, tolerance
    )
    seconds = (
        {"goldstone_slices": slices, "goldstone": probes_seconds} if slices else {}
    )
    if not results:
        # Every Goldstone side was refused: nothing was probed, which is not
        # a pass (all([]) would read True).
        return {
            "results": [],
            "entries": [],
            "seconds": seconds,
            "record": {"status": "not-run", "legs": [], "skipped": skipped},
        }

    def passed(result: Any) -> bool:
        return not isinstance(result, str) and result.passed

    record: dict[str, Any] = {
        "legs": [leg for leg, _ in results],
        "worst": _short(
            max(
                (float("inf") if isinstance(r, str) else r.worst for _, r in results),
                default=0.0,
            )
        ),
        "passed": all(passed(r) for _, r in results),
        "verdict": combined_verdict([entry.get("verdict") for entry in entries]),
        "carriers": {str(entry["leg"]): entry["carrier"] for entry in entries},
        **({"phases": phases} if phases else {}),
        **({"skipped": skipped} if skipped else {}),
    }
    return {
        "results": results,
        "entries": entries,
        "seconds": seconds,
        "record": record,
    }


def _seconds(value: float) -> float:
    """A time for the artifact record: whole milliseconds (the record's
    times are subtracted from the generation's phase times, so they keep an
    absolute, not a relative, resolution)."""

    return round(value, 3)


def _short(value: float | None, *, infinite: Any = "inf") -> Any:
    """A ratio for a record: three significant digits (a JSON number);
    ``infinite`` for an infinite one ("inf" in the artifact record), None
    and NaN as they are (``checks._short`` keeps an infinite ratio a
    float)."""

    if value is None:
        return None
    if value == float("inf"):
        return infinite
    return float(f"{value:.3g}") if value == value else value


def _complex_mass(slice_: Any) -> bool:
    from pyamplicol.loops.model_cms import convention_record

    return convention_record(slice_.compiled) is not None


def initial_invariant(
    point: Sequence[Sequence[Any]], initial: int, *, exact: bool = True
) -> Any:
    """mu_R^2 = s of the initial state, the convention of the probes, of
    ``pyamplicol check`` and of the loop profile (``benchmarking.
    profile_virtual``): the squared invariant mass of the first ``initial``
    momenta, exact (``Fraction`` of the decimal components) or in binary64
    (each component a ``math.fsum``)."""

    if exact:
        total = [sum(Fraction(p[mu]) for p in point[:initial]) for mu in range(4)]
    else:
        total = [math.fsum(float(p[mu]) for p in point[:initial]) for mu in range(4)]
    return total[0] ** 2 - total[1] ** 2 - total[2] ** 2 - total[3] ** 2


def _point_scale(point: Sequence[Sequence[str]], initial: int) -> Fraction:
    """The probe's mu_R^2: the squared invariant mass of the initial state."""

    return initial_invariant(point, initial)


def g_norm(vector: Sequence[Any], gram: Sequence[Sequence[Any]], numbers: Any) -> Any:
    """||x||_G = sqrt(x^dag G x) (G positive semidefinite), stable against a
    cancelled contraction: in a redundant colour basis the form can cancel
    far below its terms (G = [[9, 3], [3, 1]] and x = (1, -2.999999997): the
    norm is |3 x_1 + x_2| = 3e-9 while the terms are of order 9). Where the
    carrier's form is not above n^2 u times the sum of its terms'
    magnitudes (the summation's own rounding bound, n the basis size, u the
    carrier's unit roundoff; or not a positive finite number), the form is
    recomputed exactly from the carrier values as rationals and its root
    taken at the carrier's precision: a cancelled norm is never returned as
    zero. A form below zero by the metric's own rounding returns the root of
    its magnitude (its size), never a clipped zero. A value that is not a
    finite number gives a NaN norm (the row cannot be computed)."""

    zero = numbers.zero
    total = zero
    size = 0.0
    for t, x in enumerate(vector):
        inner = zero
        for u, y in enumerate(vector):
            inner = inner + gram[t][u] * y
            size += _term_size(x, gram[t][u], y)
        total = total + x.conjugate() * inner
    value = total.real
    resolved = len(vector) ** 2 * numbers.precision.unit_roundoff * size
    if value == value and value > resolved and size < math.inf:
        return value.sqrt() if hasattr(value, "sqrt") else value**0.5
    exact = _exact_form(vector, gram)
    if exact is None:
        return numbers.real(math.nan) if numbers.double else Decimal("NaN")
    magnitude_ = abs(exact)
    if numbers.double:
        return math.sqrt(float(magnitude_))
    with numbers.scope():
        return (Decimal(magnitude_.numerator) / Decimal(magnitude_.denominator)).sqrt()


def _term_size(x: Any, g: Any, y: Any) -> float:
    """|x| |g| |y| in binary64 (inf where it overflows or cannot be formed)."""

    try:
        return abs(complex(x)) * abs(complex(g)) * abs(complex(y))
    except (ArithmeticError, TypeError, ValueError):
        return math.inf


def _exact_pair(value: Any) -> tuple[Fraction, Fraction]:
    """(Re, Im) of a carrier value as exact rationals (raises for a value
    that is not a finite number)."""

    if isinstance(value, (complex, float, int)):
        value = complex(value)
    return Fraction(value.real), Fraction(value.imag)


def _exact_form(
    vector: Sequence[Any], gram: Sequence[Sequence[Any]]
) -> Fraction | None:
    """Re(x^dag G x) exactly from the carrier values (None where one is not a
    finite number)."""

    try:
        xs = [_exact_pair(x) for x in vector]
        total = Fraction(0)
        for t, (ar, ai) in enumerate(xs):
            for u, (br, bi) in enumerate(xs):
                gr, gi = _exact_pair(gram[t][u])
                # Re(conj(a) g b) = Re((ar - i ai)(gr + i gi)(br + i bi)).
                pr, pi = ar * gr + ai * gi, ar * gi - ai * gr
                total += pr * br - pi * bi
    except (ArithmeticError, TypeError, ValueError):
        return None
    return total


__all__ = [
    "ESTIMATE_FACTOR",
    "LOOP_INDUCED_INTERFERENCE",
    "PROBE_REDUCTION",
    "AmplitudeSeeds",
    "ProbeFailure",
    "ProbePointRefused",
    "ProbeResult",
    "StoredAmplitude",
    "add_amplitudes",
    "amplitude_estimates",
    "amplitude_record",
    "bare_amplitudes",
    "bind",
    "column_labels",
    "counterterm_kets",
    "finiteness",
    "g_norm",
    "generation_probes",
    "goldstone_applicability",
    "goldstone_point",
    "goldstone_sides",
    "kappa",
    "loop_sectors",
    "metric",
    "physical_floors",
    "point_probes",
    "probe",
    "probe_carriers",
    "probe_floors",
    "probe_lanes",
    "probe_legs",
    "probe_point",
    "probe_request",
    "probe_request_of",
    "probe_results",
    "probes",
    "rotation_errors",
    "row_scales",
    "scale",
    "square",
    "stability_scale",
    "term_values",
    "ward_floors",
]
