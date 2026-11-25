# SPDX-License-Identifier: 0BSD
"""The kinematics improvement of the input points.

Before a point is evaluated in a carrier above binary64 (double-double or
arbitrary precision), its external momenta are moved onto exact
energy-momentum conservation and the external mass shells in that carrier's
arithmetic, by default with MadLoop's default (``ImprovePSPoint = 2`` with
MadLoop's own fallback to ``ImprovePSPoint = 1``), finished by the
projection where MadLoop leaves the point inexact; binary64 evaluations
(by carrier kind) are improved only under the binary64 switch.

The one implementation is Rust's (``rusticol_core::kinematics_improvement``,
through ``improve_kinematics``); this module reads its policy (the values,
the default variant, the binary64 switch's default, the refusal texts), and
forms the public record (``api.virtual_results.VirtualKinematics``). Python
never re-implements the algorithm.

Settings: ``kinematics_improvement`` = ``"z-shift"`` (MadLoop 2, the
default) | ``"rescaling"`` (MadLoop 1) | ``"projection"`` (the
frame-independent minimal-norm projection) | ``"off"``, and
``kinematics_improvement_binary64`` (bool, default False).
"""

from __future__ import annotations

import functools
import json
import math
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

SETTING = "kinematics_improvement"
BINARY64 = "kinematics_improvement_binary64"


def _native() -> Any:
    from pyamplicol.loops.native import load_loop_native

    return load_loop_native()


@functools.lru_cache(maxsize=1)
def policy() -> Mapping[str, Any]:
    """The native policy record (``kinematics_policy()``), read once."""

    return json.loads(_native().kinematics_policy())


def default_setting() -> str:
    """The default variant (MadLoop's, the native policy's one constant)."""

    return str(policy()["default"])


def default_binary64() -> bool:
    """The binary64 switch's default (off)."""

    return bool(policy()["binary64_default"])


def setting_value(value: object) -> str:
    """Validate a variant setting (the native policy's values and refusal)."""

    if not isinstance(value, str) or value not in policy()["settings"]:
        raise ValueError(policy()["setting_refusal"])
    return value


def binary64_value(value: object) -> bool:
    """Validate the binary64 switch (a boolean; the native refusal text)."""

    if not isinstance(value, bool):
        raise ValueError(policy()["binary64_refusal"])
    return value


@dataclass(frozen=True, slots=True)
class KinematicsSettings:
    """A call's resolved settings: the variant setting and the binary64
    switch."""

    setting: str
    binary64: bool

    def variant(self, carrier: str) -> str | None:
        """The variant an evaluation in ``carrier`` (``"double"``,
        ``"double-double"``, ``"arbitrary"``) runs, or None (the native key,
        ``kinematics_applies``)."""

        return _native().kinematics_applies(self.setting, self.binary64, carrier)

    def records(self, carrier: str) -> bool:
        """Whether results in ``carrier`` carry a kinematics record: every
        evaluation the settings reach (binary64 only under the switch), also
        when the setting is ``"off"`` (the record then reads ``"off"``; the
        native key, ``kinematics_reaches``)."""

        return bool(_native().kinematics_reaches(self.binary64, carrier))


# The variant setting of the current call (``calling``).
_CALL_SETTING: ContextVar[str | None] = ContextVar(
    "pyamplicol_kinematics_call_setting", default=None
)


@contextmanager
def calling(setting: str | None) -> Iterator[None]:
    """Within this context the current call's resolved variant setting is
    ``setting`` (``"z-shift"``, ``"rescaling"``, ``"projection"`` or
    ``"off"``; None: none recorded), which the rescues' improved points
    follow (``plan_export.rescue_options``), as the call's double-double and
    arbitrary-precision evaluations do; reset on exit.
    """

    token = _CALL_SETTING.set(setting)
    try:
        yield
    finally:
        _CALL_SETTING.reset(token)


def call_setting() -> str | None:
    """The current call's variant setting (``calling``), None outside a
    call."""

    return _CALL_SETTING.get()


def resolve(
    setting: str | None,
    binary64: bool | None,
    *,
    default_setting_: str | None = None,
    default_binary64_: bool | None = None,
) -> KinematicsSettings:
    """A call's settings: its own, else the runtime's (load-time) ones, else
    the policy's defaults."""

    chosen = (
        setting_value(setting)
        if setting is not None
        else default_setting_
        if default_setting_ is not None
        else default_setting()
    )
    switch = (
        binary64_value(binary64)
        if binary64 is not None
        else default_binary64_
        if default_binary64_ is not None
        else default_binary64()
    )
    return KinematicsSettings(chosen, switch)


def improve(
    points: Sequence[Sequence[Sequence[Any]]],
    n_initial: int,
    masses2: Sequence[Fraction | None],
    arithmetic: str,
    digits: int | None,
    variant: str,
    *,
    fallback: bool = True,
    tolerances: Mapping[str, float] | None = None,
) -> tuple[list[list[list[str]]], list[dict[str, Any]]]:
    """Improve ``points`` (physical momenta, the ``n_initial`` initial states
    first, exact components) in ``arithmetic`` (``"arbitrary"`` at
    ``digits`` working digits, the native executor's) with ``variant``
    toward ``masses2`` (exact; None: a leg's own p²): the improved points
    (exact fraction texts; unchanged where no variant improves the point or
    it is already exactly physical) and the per-point records (the native
    JSON records, ``kinematics_improvement::Record``). ``fallback=False``
    runs the variant alone (a forced variant)."""

    texts = [
        [[str(Fraction(str(x))) for x in leg] for leg in point] for point in points
    ]
    masses = [None if m is None else str(Fraction(m)) for m in masses2]
    extra = dict(tolerances or {})
    out, records = _native().improve_kinematics(
        texts,
        n_initial,
        masses,
        arithmetic,
        digits,
        variant,
        fallback,
        extra.get("fourmom"),
        extra.get("onshell"),
        extra.get("close"),
    )
    found = [json.loads(record) for record in records]
    # An improved point as the exact decimal texts of its carrier values
    # (dyadic rationals: finite decimal expansions, the inputs' syntax); any
    # other point is the caller's own, unchanged.
    improved = [
        [[_exact_decimal(x) for x in leg] for leg in point]
        if record["status"] == "improved"
        else [[str(x) for x in leg] for leg in original]
        for point, record, original in zip(out, found, points, strict=True)
    ]
    return improved, found


def _exact_decimal(text: str) -> str:
    """The exact decimal text of a dyadic rational (a carrier value's exact
    rational, ``n / 2^k``)."""

    from decimal import Decimal

    value = Fraction(text)
    k = value.denominator.bit_length() - 1
    if value.denominator != 1 << k:
        raise ValueError(f"not a carrier value: {text}")
    scaled = value.numerator * 5**k
    digits = tuple(int(c) for c in str(abs(scaled)))
    # Constructed from its digits: exact (no context rounding).
    return str(Decimal((int(scaled < 0), digits, -k)))


def off_record(setting: str) -> dict[str, Any]:
    """The record of a point the settings reach but do not improve (the
    setting ``"off"``; the native record, ``kinematics_off_record``, the
    loop SDK's)."""

    return dict(json.loads(_native().kinematics_off_record(setting)))


def notes(
    records: Sequence[Mapping[str, Any]], carrier: str, precision: int
) -> list[str]:
    """The tree runtimes' warnings-channel lines of one call's records (the
    native formatter, ``kinematics_improvement::notes_json``, the tree C
    ABI's): a summary line and every typed warning."""

    return list(
        _native().kinematics_notes(
            [json.dumps(dict(record)) for record in records], carrier, precision
        )
    )


# A leg-mass provider: (v2 Precision, a caller-order point, its mu_R^2, the
# batch's point count) -> the squared mass of each caller-order leg (exact;
# None: no bound mass), exactly the masses the evaluation binds.
MassProvider = Callable[[Any, Sequence[Sequence[Any]], Any, int], list[Fraction | None]]


def initial_count(legs: Sequence[Any]) -> int:
    """The number of initial states of a process's legs (``is_initial``,
    ``label``): they come first (the improvement's convention, MadLoop's)."""

    initial = sorted(leg.label for leg in legs if leg.is_initial)
    if initial != list(range(1, len(initial) + 1)):
        raise ValueError("the kinematics improvement needs the initial states first")
    return len(initial)


class LevelImprover:
    """One call's kinematics improvement, level by level: each carrier's
    evaluation of the user's points (a call without a rescue policy, or one
    rescue level) improves the ORIGINAL caller-order points once in its own
    carrier (MadLoop's SET_MP_PS: never an already improved point), with the
    masses the evaluation binds (``masses``). A point improved for a carrier
    is reused by every later evaluation of it at the same carrier."""

    def __init__(
        self, settings: KinematicsSettings, n_initial: int, masses: MassProvider
    ) -> None:
        self.settings = settings
        self.n_initial = n_initial
        self._masses = masses
        self._cache: dict[tuple[Any, ...], tuple[list[list[str]], dict[str, Any]]] = {}

    def level(
        self,
        points: Sequence[Sequence[Sequence[Any]]],
        scales: Sequence[Any],
        precision: Any,
    ) -> tuple[list[Any], list[Any]]:
        """The points of one carrier's evaluation (``precision``, a v2
        ``Precision``) and each point's record (``VirtualKinematics``; None:
        no record, a binary64 evaluation without the binary64 switch)."""

        from pyamplicol.api.virtual_results import VirtualKinematics

        carrier = precision.arithmetic
        variant = self.settings.variant(carrier)
        if variant is None:
            if not self.settings.records(carrier):
                return list(points), [None] * len(points)
            off = VirtualKinematics.from_record(off_record(self.settings.setting))
            return list(points), [off] * len(points)
        digits = precision.working_digits if carrier == "arbitrary" else None
        out: list[Any] = list(points)
        records: list[Any] = [None] * len(points)
        groups: dict[Fraction, list[int]] = {}
        for index, scale in enumerate(scales):
            groups.setdefault(Fraction(str(scale)), []).append(index)
        for indices in groups.values():
            first = indices[0]
            masses = self._masses(precision, points[first], scales[first], len(points))
            keys = {
                i: (carrier, digits, variant, tuple(masses), _key(points[i]))
                for i in indices
            }
            missing = [i for i in indices if keys[i] not in self._cache]
            if missing:
                improved, found = improve(
                    [points[i] for i in missing],
                    self.n_initial,
                    masses,
                    carrier,
                    digits,
                    variant,
                )
                for i, point, record in zip(missing, improved, found, strict=True):
                    self._cache[keys[i]] = (point, record)
            for i in indices:
                point, record = self._cache[keys[i]]
                out[i] = point
                records[i] = VirtualKinematics.from_record(record)
        return out, records


def _key(point: Sequence[Sequence[Any]]) -> tuple[tuple[Fraction, ...], ...]:
    return tuple(tuple(Fraction(str(x)) for x in leg) for leg in point)


def with_kinematics(evaluation: Any, records: Sequence[Any]) -> Any:
    """``evaluation`` (a ``VirtualEvaluation``) with each lane diagnostic's
    kinematics record; unchanged when no point has one."""

    from dataclasses import replace

    if all(record is None for record in records):
        return evaluation
    diagnostics = tuple(
        replace(diagnostic, kinematics=record)
        for diagnostic, record in zip(evaluation.diagnostics, records, strict=True)
    )
    return replace(evaluation, diagnostics=diagnostics)


# ------------------------------------------------------- the shell screen
#
# A one-loop amplitude binds every invariant a single external leg fixes to
# that leg's bound squared mass, never to the p^2 of the given momenta (DESIGN
# §11.1, ``families.onshell_leg``): its integrals take m^2, its numerators
# the momenta. At a point off those shells the value is no amplitude of
# consistent kinematics (the g g > t t~ h points of a card fixing MT = 173
# drawn on shell at the model's 174.3: a double pole 0.2 off Catani's, the
# two reductions an order apart), and a stable reduction does not certify it.
# THE SHELL-CONSISTENCY SCREEN (a screen, not an error bound on the
# amplitude) runs in the checked mode only (the unchecked mode measures
# nothing, bit for bit and at no cost): every external leg of the point a
# carrier evaluates (the caller's momenta after the call's kinematics
# improvement, in the caller's leg order) against the squared mass that call
# binds for the leg, per leg (a hard spectator cannot mask a soft leg):
#
#     massive (m^2 > 0):  |p^2 - m^2| <= t m^2 + C u (E^2 + |p|^2 + m^2),
#     massless:           |p^2|       <= t (E^2 + |p|^2) + C u (E^2 + |p|^2),
#
# t the call's point target (``reduction_target``, the user's, not the
# reduction's tightened per-lane value), u the unit roundoff of the carrier
# the momenta were SUPPLIED in (``input_roundoff``; the evaluating carrier's
# when coarser), and C = SHELL_ROUNDING = 8 the rounding allowance of a
# point drawn on its shell in that carrier: rounding E and the three
# components moves p^2 by at most 2 u (E^2 + |p|^2), the mass rounded to
# the carrier moves m^2 by 2 u m^2, and forming the on-shell energy from the
# momentum and the mass (three squares, three sums, a square root: six
# roundings of E^2) by 6 u E^2, together within 8 u (E^2 + |p|^2 + m^2) to
# first order. The test is exact (rational arithmetic; binary64 inputs in
# vectorised double-double arithmetic on each leg scaled by a power of two
# to its largest component first, so that no square overflows or
# underflows). Beyond it the ORIGINAL value is served, its lane marked
# ``uncertified`` with a typed reason (``SHELL_REASON``: the leg, its p^2,
# the bound m^2 and the measured ratio to the allowance); a measurement that
# cannot be made (a non-finite component, a mass the evaluator cannot bind)
# marks it too. The mark never escalates a rescue by itself and accumulates
# with every other reason; a failed lane stays failed.
SHELL_REASON = "off the bound mass shell"
SHELL_ROUNDING = 8
_BINARY64_ROUNDOFF = 2.0**-53


def input_roundoff(momenta: Any) -> list[tuple[float, ...]]:
    """Per point and leg the unit roundoff of the carrier the leg's
    components were supplied in, by each component's INPUT CONTRACT
    (``runtime.virtual._number``: a component is read as an exact decimal):
    binary64's 2^-53 for a Python float (a binary64 value, whatever its
    text), 0 for every exact spelling (an integer, a decimal text or
    ``Decimal`` at any number of digits, a rational); a leg takes its
    coarsest component's. Nothing is inferred from a text's spelling."""

    def unit(value: Any) -> float:
        return _BINARY64_ROUNDOFF if isinstance(value, float) else 0.0

    return [
        tuple(max((unit(x) for x in leg), default=0.0) for leg in point)
        for point in momenta
    ]


@dataclass(frozen=True, slots=True)
class ShellCheck:
    """The screen's measure of one carrier's points of a call: per point the
    relative shell defect of every leg (|p^2 - m^2| / m^2, massless
    |p^2| / (E^2 + |p|^2); NaN where it cannot be measured) and, by index,
    the typed ``uncertified`` reason of each point the screen marks."""

    defects: tuple[tuple[float, ...], ...]
    reasons: Mapping[int, str]


def shell_check(
    points: Sequence[Sequence[Sequence[Any]]],
    scales: Sequence[Any],
    precision: Any,
    masses: MassProvider,
    target: float,
    roundoff: Sequence[float],
) -> ShellCheck:
    """The screen on the points one carrier evaluates (``precision``, a v2
    ``Precision``; the caller's legs, after the call's kinematics
    improvement) against the squared masses that call binds (``masses``,
    caller order; None: no mass bound), at the call's point ``target`` and
    the supplied carriers' unit roundoffs (``roundoff``, per point,
    ``input_roundoff``)."""

    masses2: list[Sequence[Fraction | None]] = [()] * len(points)
    # (By text: equal values of other texts ask the provider again, which
    # binds the same masses.)
    groups: dict[str, list[int]] = {}
    for index, scale in enumerate(scales):
        groups.setdefault(str(scale), []).append(index)
    for indices in groups.values():
        first = indices[0]
        bound = masses(precision, points[first], scales[first], len(points))
        for index in indices:
            masses2[index] = bound
    carrier = (
        _BINARY64_ROUNDOFF
        if precision.arithmetic == "double"
        else 2.0**-106
        if precision.arithmetic == "double-double"
        else 0.0
    )
    # Per point and leg: the leg's supplied carrier (``input_roundoff``; a
    # number per point applies to each of its legs), the evaluating
    # carrier's when coarser.
    units = [
        tuple(
            max(float(u), carrier)
            for u in (
                [leg_unit] * len(point)
                if isinstance(leg_unit, (int, float))
                else leg_unit
            )
        )
        for point, leg_unit in zip(points, roundoff, strict=True)
    ]
    binary64 = precision.arithmetic == "double"
    if binary64 and points:
        # The binary64 values, measured in vectorised double-double
        # arithmetic (``_binary64_legs``); a point it marks is measured
        # again exactly for its reason.
        relative, ratio = _binary64_legs(points, masses2, float(target), units)
        defects = [tuple(row) for row in relative]
        candidates = [
            index for index, row in enumerate(ratio) if not max(row, default=0.0) <= 1.0
        ]
    else:
        defects = [()] * len(points)
        candidates = list(range(len(points)))
    reasons: dict[int, str] = {}
    for index in candidates:
        point, legs = points[index], masses2[index]
        measured = _shell_legs(point, legs, float(target), units[index], binary64)
        if not binary64:
            defects[index] = tuple(relative for relative, _ratio, _sq in measured)
        reason = _shell_reason(point, legs, measured)
        if reason is not None:
            reasons[index] = reason
    return ShellCheck(tuple(defects), reasons)


def _binary64_legs(
    points: Sequence[Sequence[Sequence[Any]]],
    masses2: Sequence[Sequence[Fraction | None]],
    target: float,
    units: Sequence[Sequence[float]],
) -> tuple[list[list[float]], list[list[float]]]:
    """Per point and leg the relative defect and the ratio to the screen's
    allowance (``_shell_legs``) of binary64 values, vectorised: each leg
    scaled by a power of two to its largest component (and mass) first, so
    that no square overflows or underflows, then p^2 - m^2 in double-double
    (Dekker's exact square, Knuth's two-sum: an error of order u^2 of the
    leg's scale, far below any allowance). A non-finite component or a leg
    without a bound mass: NaN defect, infinite ratio (the exact pass marks
    it)."""

    import numpy as np

    p = np.array(points, dtype=np.float64)
    rows: dict[tuple[Fraction | None, ...], int] = {}
    index = [rows.setdefault(tuple(masses), len(rows)) for masses in masses2]
    known = np.array([[m is not None for m in masses] for masses in rows], dtype=bool)[
        index
    ]
    # Each mass as an exact (mantissa high, mantissa low, binary exponent).
    parts = [[_split_exponent(m) for m in masses] for masses in rows]
    m_hi = np.array([[part[0] for part in row] for row in parts])[index]
    m_lo = np.array([[part[1] for part in row] for row in parts])[index]
    m_exp = np.array([[part[2] for part in row] for row in parts])[index]
    with np.errstate(all="ignore"):
        finite = np.isfinite(p).all(axis=2)
        largest = np.abs(np.where(np.isfinite(p), p, 0.0)).max(axis=2)
        _mant, exponent = np.frexp(largest)
        # The mass's own exponent (m^2 = hi 2^e): its root's is about e / 2.
        exponent = np.maximum(exponent, (m_exp + 1) // 2 + 1)
        q = np.ldexp(p, -exponent[..., None])
        mh = np.ldexp(m_hi, m_exp - 2 * exponent)
        ml = np.ldexp(m_lo, m_exp - 2 * exponent)
        split = 134217729.0 * q
        head = split - (split - q)
        tail = q - head
        square = q * q
        error = ((head * head - square) + 2.0 * head * tail) + tail * tail
        hi, lo = square[..., 0], error[..., 0]
        for mu in (1, 2, 3):
            term_hi, term_lo = -square[..., mu], -error[..., mu]
            total = hi + term_hi
            back = total - hi
            lo = lo + ((hi - (total - back)) + (term_hi - back)) + term_lo
            hi = total
        size = square.sum(axis=2)
        total = hi - mh
        back = total - hi
        lo = lo + ((hi - (total - back)) + (-mh - back)) - ml
        defect = np.abs(total + lo)
        mass2 = mh + ml
        u = np.array(units, dtype=np.float64)
        massive = mass2 > 0.0
        allowance = np.where(
            massive,
            target * mass2 + SHELL_ROUNDING * u * (size + mass2),
            (target + SHELL_ROUNDING * u) * size,
        )
        reference = np.where(massive, mass2, size)
        relative = np.where(reference > 0.0, defect / reference, 0.0)
        ratio = np.where(
            allowance > 0.0,
            defect / np.where(allowance > 0.0, allowance, 1.0),
            np.where(defect == 0.0, 0.0, np.inf),
        )
        bad = ~(finite & known)
        relative = np.where(bad, np.nan, relative)
        ratio = np.where(bad, np.inf, ratio)
    return relative.tolist(), ratio.tolist()


def _split_exponent(mass2: Fraction | None) -> tuple[float, float, int]:
    """An exact squared mass as (high, low, e) with mass2 = (high + low) 2^e
    to double-double accuracy, high in [0.5, 1) (0 for 0; NaN for None)."""

    if mass2 is None:
        return (math.nan, 0.0, 0)
    if mass2 == 0:
        return (0.0, 0.0, 0)
    e = mass2.numerator.bit_length() - mass2.denominator.bit_length()
    scaled = mass2 / (Fraction(2) ** e) if e >= 0 else mass2 * (Fraction(2) ** -e)
    high = float(scaled)
    low = float(scaled - Fraction(high))
    return (high, low, e)


def _shell_legs(
    point: Sequence[Sequence[Any]],
    masses2: Sequence[Fraction | None],
    target: float,
    units: Sequence[float],
    binary64: bool,
) -> list[tuple[float, float, Fraction | None]]:
    """Per leg (relative defect, ratio to the allowance, exact p^2): NaN /
    inf where the measurement cannot be made; (0, 0, None) for a leg
    without a bound mass (its invariants are its own p^2)."""

    out: list[tuple[float, float, Fraction | None]] = []
    for leg, mass2, unit in zip(point, masses2, units, strict=True):
        if mass2 is None:
            out.append((math.nan, math.inf, None))
            continue
        try:
            components = (
                [Fraction(float(x)) for x in leg]
                if binary64
                else [Fraction(str(x)) for x in leg]
            )
        except (ValueError, OverflowError):
            out.append((math.nan, math.inf, None))
            continue
        energy, x, y, z = components
        # Exact rationals: no overflow or underflow (the evaluated binary64
        # values are exact rationals too).
        spatial = x * x + y * y + z * z
        square = energy * energy - spatial
        size = energy * energy + spatial
        if mass2 > 0:
            defect = abs(square - mass2)
            relative = defect / mass2
            allowance = Fraction(target) * mass2 + SHELL_ROUNDING * Fraction(unit) * (
                size + mass2
            )
        else:
            defect = abs(square)
            relative = defect / size if size else Fraction(0)
            allowance = (Fraction(target) + SHELL_ROUNDING * Fraction(unit)) * size
        ratio = (
            float(defect / allowance)
            if allowance
            else (0.0 if defect == 0 else math.inf)
        )
        out.append((float(relative), ratio, square))
    return out


def _shell_reason(
    point: Sequence[Sequence[Any]],
    masses2: Sequence[Fraction | None],
    measured: Sequence[tuple[float, float, Fraction | None]],
) -> str | None:
    """The point's typed reason, or None when every leg passes."""

    worst = max(range(len(measured)), key=lambda k: measured[k][1], default=None)
    if worst is None or not measured[worst][1] > 1.0:
        return None
    relative, ratio, square = measured[worst]
    mass2 = masses2[worst]
    if square is None or mass2 is None:
        return (
            f"{SHELL_REASON}: external leg {worst + 1} cannot be measured (a "
            "non-finite component or no bound mass); the value is served "
            "without a shell-consistency screen"
        )
    return (
        f"{SHELL_REASON}: external leg {worst + 1}, p^2 = {float(square)!r}, "
        f"bound m^2 = {float(mass2)!r}, relative defect {relative:.3e}, "
        f"{ratio:.3g} times the screen's allowance (target m^2 + "
        f"{SHELL_ROUNDING} u (E^2 + |p|^2 + m^2); a shell-consistency screen, "
        "not an error bound: the value is served as computed)"
    )


def is_shell_reason(reason: str) -> bool:
    """Whether an ``uncertified`` reason is the shell screen's (which never
    escalates a rescue by itself)."""

    return str(reason).startswith(SHELL_REASON)


__all__ = [
    "BINARY64",
    "SETTING",
    "SHELL_REASON",
    "SHELL_ROUNDING",
    "KinematicsSettings",
    "LevelImprover",
    "MassProvider",
    "ShellCheck",
    "binary64_value",
    "default_binary64",
    "default_setting",
    "improve",
    "initial_count",
    "input_roundoff",
    "is_shell_reason",
    "notes",
    "off_record",
    "policy",
    "resolve",
    "setting_value",
    "shell_check",
    "with_kinematics",
]
