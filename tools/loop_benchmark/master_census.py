# SPDX-License-Identifier: 0BSD
"""The scalar masters a v2 plan's reductions reach, against the known
complex-mass master defects of the pinned oneloopmaster (``5b710437``) and
NinjaRS (``41a4c00``) (m-sm/PLAN.md §3.2 MS-MASTERS, DESIGN risk 13).

Every family of the plan (``exported.program["families"]``) is a ring of
propagators ``(q + p(V_i))^2 - m_i^2`` with the cumulative leg masks
``V_1..V_N`` of its sequence (``Family::shift_masks``). Its reduction reaches
the masters of the subsets of at most four propagators: A0, the bubble
family (B0..B1111), C0 and D0. Their invariants are the executor's exact
``s[mask]`` (``loop_v2::dress``: ``p(mask)^2`` of the all-incoming momenta,
or the squared mass of the leg whose mass shell fixes it) and their masses
the plan masses bound at the point (``assemble._mass_values``, a complex
pole mass squared under the complex-mass scheme). The census enumerates them
exactly and counts the defect signatures:

* ``c0-zero-invariants``: C0(0, 0, 0; ...) with a complex mass; the
  ``complex-zero-real`` subset is the C0(0,0,0; m_c, 0, m_r) defect (every
  route, binary64 included; oneloopmaster STATUS "Open C0 limitations");
  the rest is interpreted ``Float``'s C0 at vanishing invariants;
* ``small-momentum-bubble``: the smallest ``max_mu |k^mu| / max_i |m_i|``
  over bubbles with unequal masses (NinjaRS V9 ``rn2-scan-bubp2-complex``:
  the bubble's reduction loses ~ (0.08 / r)^4 x 1e-12 in binary64 and
  x 3e-28 in double-double);
* ``negative-real-mass``: a real negative squared mass (not the -i0 limit);
* ``complex-box``: D0 with a complex mass (the interpreted ``Float`` route's
  boxes, checked at row level: AP(40) against AP(60) and double-double);
* ``tiny-width``: 0 < |Im m^2| / Re m^2 < 1e-150 (oneloopmaster's SymJIT
  masters, on no reducer's route; the double-double C0 turned non-finite
  there on CM01, so ``TreeProgram::bind`` refuses it in double-double:
  ``complex-mass-master``).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from itertools import combinations
from typing import Any

#: |Im m^2| / Re m^2 below which oneloopmaster's SymJIT masters and the
#: double-double C0 fail.
TINY_WIDTH = Fraction(1, 10**150)


@dataclass(frozen=True)
class Ring:
    """One family: cumulative leg masks and mass ids, propagator by
    propagator."""

    masks: tuple[int, ...]
    masses: tuple[int, ...]


def rings(exported: Any) -> tuple[Ring, ...]:
    """The rings of a plan's families (``ExportedPlan.program``)."""

    out = []
    for family in exported.program["families"]:
        total, masks, ids = 0, [], []
        for mask, mass in family["sequence"]:
            total |= int(mask)
            masks.append(total)
            ids.append(int(mass))
        out.append(Ring(tuple(masks), tuple(ids)))
    return tuple(out)


def _complex(value: Any) -> tuple[Fraction, Fraction]:
    """A squared mass as (real, imaginary) Fractions: a Fraction, a
    complex value with ``real`` / ``imag``, or a (real, imaginary) pair."""

    if isinstance(value, tuple):
        return Fraction(value[0]), Fraction(value[1])
    real = getattr(value, "real", value)
    imag = getattr(value, "imag", 0)
    return Fraction(real), Fraction(imag)


def _size(value: tuple[Fraction, Fraction]) -> Fraction:
    return abs(value[0]) + abs(value[1])


def _onshell_leg(mask: int, legs: int) -> int | None:
    full = (1 << legs) - 1
    for subset in (mask & full, full ^ (mask & full)):
        if subset and subset & (subset - 1) == 0:
            return subset.bit_length() - 1
    return None


@dataclass
class Point:
    """Exact kinematics of one phase-space point: all-incoming momenta and
    the legs' squared masses (the on-shell invariants)."""

    incoming: Sequence[Sequence[Fraction]]
    leg_masses: Sequence[Fraction]
    _momenta: dict[int, tuple[Fraction, ...]] = field(default_factory=dict)
    _squares: dict[int, Fraction] = field(default_factory=dict)

    def momentum(self, mask: int) -> tuple[Fraction, ...]:
        found = self._momenta.get(mask)
        if found is None:
            total = [Fraction(0)] * 4
            for leg, p in enumerate(self.incoming):
                if mask >> leg & 1:
                    total = [a + b for a, b in zip(total, p, strict=True)]
            found = self._momenta[mask] = tuple(total)
        return found

    def square(self, mask: int) -> Fraction:
        found = self._squares.get(mask)
        if found is None:
            leg = _onshell_leg(mask, len(self.incoming))
            if leg is not None:
                found = Fraction(self.leg_masses[leg])
            else:
                p = self.momentum(mask)
                found = p[0] ** 2 - p[1] ** 2 - p[2] ** 2 - p[3] ** 2
            self._squares[mask] = found
        return found


@dataclass
class Census:
    """Counts of the distinct masters reached (per kind; with a complex
    mass) and of the defect signatures over the points."""

    masters: Counter = field(default_factory=Counter)
    complex_masters: Counter = field(default_factory=Counter)
    c0_zero_invariants: int = 0
    c0_complex_zero_real: int = 0
    small_bubble_ratio: float | None = None
    negative_real_masses: list[int] = field(default_factory=list)
    tiny_widths: list[int] = field(default_factory=list)

    def bites(self, binary64_loss: float = 1e-5) -> dict[str, bool]:
        """Per signature: reached at a size where its known loss exceeds
        ``binary64_loss`` (the small-momentum bubble by the V9 scan's
        binary64 scaling; the complex box is assessed at row level)."""

        ratio = self.small_bubble_ratio
        return {
            "c0-complex-zero-real": self.c0_complex_zero_real > 0,
            "c0-zero-invariants": self.c0_zero_invariants > 0,
            "small-momentum-bubble": ratio is not None
            and bubble_loss(ratio) > binary64_loss,
            "negative-real-mass": bool(self.negative_real_masses),
            "tiny-width": bool(self.tiny_widths),
        }

    def record(self) -> dict[str, Any]:
        return {
            "masters": dict(sorted(self.masters.items())),
            "complex_masters": dict(sorted(self.complex_masters.items())),
            "c0_zero_invariants": self.c0_zero_invariants,
            "c0_complex_zero_real": self.c0_complex_zero_real,
            "small_bubble_ratio": self.small_bubble_ratio,
            "small_bubble_binary64_loss": None
            if self.small_bubble_ratio is None
            else bubble_loss(self.small_bubble_ratio),
            "negative_real_masses": self.negative_real_masses,
            "tiny_widths": self.tiny_widths,
            "bites": self.bites(),
        }


def bubble_loss(ratio: float, double_double: bool = False) -> float:
    """The V9 scan's relative loss of a small-momentum unequal-mass bubble
    at ``ratio`` = max |k^mu| / max |m| (binary64 9.7e-13 at 0.078, ~1/r^4;
    double-double 3.2e-28 there)."""

    scale = 3.2e-28 if double_double else 9.7e-13
    return scale * (0.078 / max(ratio, 1e-300)) ** 4


_KINDS = {1: "A0", 2: "B", 3: "C0", 4: "D0"}


def census(
    ring_list: Iterable[Ring],
    masses: Sequence[Any],
    points: Iterable[Point],
    into: Census | None = None,
) -> Census:
    """Enumerate the masters of ``ring_list`` at ``points`` with the plan
    masses squared ``masses`` (by mass id, as ``_complex`` reads them) and
    count the defect signatures."""

    out = into or Census()
    squared = [_complex(m) for m in masses]
    for mass_id, (re, im) in enumerate(squared):
        if im == 0 and re < 0 and mass_id not in out.negative_real_masses:
            out.negative_real_masses.append(mass_id)
        if im != 0 and abs(im) < TINY_WIDTH * re and mass_id not in out.tiny_widths:
            out.tiny_widths.append(mass_id)
    subsets: set[tuple[tuple[int, int], ...]] = set()
    for ring in ring_list:
        n = len(ring.masks)
        props = tuple(zip(ring.masks, ring.masses, strict=True))
        for k in range(1, min(4, n) + 1):
            for chosen in combinations(range(n), k):
                subsets.add(tuple(props[i] for i in chosen))
    for subset in subsets:
        kind = _KINDS[len(subset)]
        out.masters[kind] += 1
        if any(squared[m][1] != 0 for _mask, m in subset):
            out.complex_masters[kind] += 1
    for point in points:
        for subset in subsets:
            k = len(subset)
            values = [squared[m] for _mask, m in subset]
            complex_ = any(im != 0 for _re, im in values)
            masks = [mask for mask, _m in subset]
            if k == 2 and values[0] != values[1]:
                momentum = point.momentum(masks[0] ^ masks[1])
                scale = max(_size(v) for v in values)
                ratio = float(max(abs(x) for x in momentum)) / float(scale) ** 0.5
                if out.small_bubble_ratio is None or ratio < out.small_bubble_ratio:
                    out.small_bubble_ratio = ratio
            if k == 3 and complex_:
                invariants = [
                    point.square(masks[a] ^ masks[b])
                    for a, b in ((0, 1), (1, 2), (0, 2))
                ]
                if all(s == 0 for s in invariants):
                    out.c0_zero_invariants += 1
                    kinds = sorted(
                        "complex" if im != 0 else "zero" if re == 0 else "real"
                        for re, im in values
                    )
                    if kinds == ["complex", "real", "zero"]:
                        out.c0_complex_zero_real += 1
    return out


def slice_census(
    executor: Any,
    points: Sequence[Sequence[Sequence[Any]]],
    scales: Sequence[Any],
    parameters: Mapping[str, str] | None = None,
    digits: int = 40,
) -> Census:
    """The census of a ``NativeExecutor``'s plan at ``points`` (physical
    momenta, the Python inputs' point convention) and their ``scales``
    (mu_R^2) with the slice's mass values at ``parameters``."""

    from pyamplicol.loops.v2.assemble import (
        Precision,
        _fraction,
        _leg_masses,
        _mass_values,
    )

    slice_ = executor.slice
    exported = executor.exported
    process = slice_.blocks.process
    labels = sorted(leg.label for leg in process.legs)
    initial = {leg.label for leg in process.legs if leg.is_initial}
    precision = Precision.arbitrary(digits)
    masses, kinematics = None, []
    for point, scale in zip(points, scales, strict=True):
        values = slice_._point_parameters(
            dict(parameters or {}), _fraction(scale), precision
        )
        if masses is None:
            # The plan masses do not depend on the point (mu_R aside).
            squared = _mass_values(slice_.compiled, values, exported.masses, digits)
            masses = [squared[mass] for mass in exported.masses]
        legs = _leg_masses(slice_, values, digits)
        exact = [[_fraction(x) for x in p] for p in point]
        incoming = [
            [x if label in initial else -x for x in exact[label - 1]]
            for label in labels
        ]
        kinematics.append(Point(incoming, legs))
    return census(rings(exported), masses or [], kinematics)
