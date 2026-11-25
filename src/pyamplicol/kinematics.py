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


# ------------------------------------------------------------ the shell guard
#
# A one-loop amplitude binds every invariant a single external leg fixes to
# that leg's bound squared mass, never to the p^2 of the given momenta (DESIGN
# §11.1, ``families.onshell_leg``): its integrals take m^2 while its
# numerators take the momenta. A point off those shells is therefore no
# consistent kinematics, and its value is no amplitude (the g g > t t~ h
# points of a card fixing MT = 173 drawn on shell at the model's 174.3: a
# double pole 0.2 off Catani's, the two reductions an order apart). THE GUARD
# measures every external leg of the point an evaluation runs (the caller's,
# after the call's kinematics improvement in its carrier) with the
# improvement's own exactness measure (``rusticol_core::
# kinematics_improvement::exactness``),
#
#     defect_k = |p_k^2 - m_k^2| / (REF_k S),
#     REF_k = |E_k| + |px_k| + |py_k| + |pz_k|,  S = sum_j |E_j|,
#
# against the bound m_k^2 (``NativeExecutor.leg_masses``, exact), and refuses
# the point when a defect exceeds (2 n + 5) u, n legs, u = 2^-53: the
# improvement's exactness bound (its "exact to the carrier's rounding") at
# the unit roundoff of binary64, the coarsest carrier momenta reach a runtime
# in. A point exact in its own carrier (an improved point in any carrier) is
# within it; so is a binary64 point drawn on the shell (rounding its
# components moves p^2 by about 2 u REF_k^2 <= 2 u REF_k S). A larger defect
# is no rounding: the point is off the bound shell (its masses are others',
# or it was given to fewer digits and no improvement ran: binary64 without
# ``kinematics_improvement_binary64``, the setting "off", or the improvement
# refused it as MadLoop's IS_PHYSICAL does, beyond 1e-2 of its scale).
SHELL_STAGE = "external-mass-shell"
_BINARY64_ROUNDOFF = 2.0**-53


def shell_bound(legs: int) -> float:
    """The guard's bound on a leg's shell defect: (2 n + 5) u of binary64
    for ``legs`` = n external legs (module notes, "the shell guard")."""

    return (2 * legs + 5) * _BINARY64_ROUNDOFF


def shell_defects(
    points: Sequence[Sequence[Sequence[Any]]],
    masses2: Sequence[Sequence[Fraction | None]],
    *,
    binary64: bool,
) -> list[tuple[float, ...]]:
    """Each point's shell defect per leg (module notes): ``points`` the
    evaluated momenta (decimal texts or numbers), ``masses2`` per point the
    bound squared mass of each leg (exact; None: the leg's own p^2, defect
    0). ``binary64``: the points run in binary64, whose inputs are their
    binary64 values, measured exactly in double-double arithmetic (numpy,
    vectorised: the error-free products and sums leave an error of order
    u^2 REF_k^2, far below the bound); otherwise the exact components in
    rational arithmetic."""

    if not points:
        return []
    if binary64:
        return _binary64_defects(points, masses2)
    out = []
    for point, masses in zip(points, masses2, strict=True):
        try:
            legs = [[Fraction(str(x)) for x in leg] for leg in point]
        except (ValueError, OverflowError):
            # A non-finite component: no measure, left to the evaluation.
            out.append((math.nan,) * len(point))
            continue
        scale = sum(abs(leg[0]) for leg in legs)
        out.append(
            tuple(
                0.0
                if mass is None
                else _relative(
                    leg[0] * leg[0]
                    - leg[1] * leg[1]
                    - leg[2] * leg[2]
                    - leg[3] * leg[3]
                    - mass,
                    sum(abs(x) for x in leg) * scale,
                )
                for leg, mass in zip(legs, masses, strict=True)
            )
        )
    return out


def _relative(defect: Any, reference: Any) -> float:
    if reference == 0:
        return 0.0 if defect == 0 else math.inf
    return float(abs(defect) / reference)


def _binary64_defects(
    points: Sequence[Sequence[Sequence[Any]]],
    masses2: Sequence[Sequence[Fraction | None]],
) -> list[tuple[float, ...]]:
    import numpy as np

    p = np.array(points, dtype=np.float64)
    # Each distinct mass row once (a batch's points share their masses).
    rows: dict[tuple[Fraction | None, ...], int] = {}
    index = [rows.setdefault(tuple(masses), len(rows)) for masses in masses2]
    split_masses = [
        [
            (0.0, 0.0, False)
            if m is None
            else (float(m), float(m - Fraction(float(m))), True)
            for m in masses
        ]
        for masses in rows
    ]
    table = np.array(split_masses, dtype=object)[index]
    high = table[..., 0].astype(np.float64)
    low = table[..., 1].astype(np.float64)
    known = table[..., 2].astype(bool)
    with np.errstate(all="ignore"):
        # E^2 - px^2 - py^2 - pz^2 - m^2 in double-double: Dekker's exact
        # square (a_hi^2 + 2 a_hi a_lo + a_lo^2) and Knuth's two-sum.
        split = 134217729.0 * p
        head = split - (split - p)
        tail = p - head
        square = p * p
        error = ((head * head - square) + 2.0 * head * tail) + tail * tail
        hi, lo = square[..., 0], error[..., 0]
        for mu in (1, 2, 3):
            term_hi, term_lo = -square[..., mu], -error[..., mu]
            total = hi + term_hi
            back = total - hi
            lo = lo + ((hi - (total - back)) + (term_hi - back)) + term_lo
            hi = total
        total = hi - high
        back = total - hi
        lo = lo + ((hi - (total - back)) + (-high - back)) - low
        defect = np.abs(total + lo)
        reference = np.abs(p).sum(axis=2) * np.abs(p[..., 0]).sum(axis=1)[:, None]
        relative = np.where(
            reference > 0.0,
            defect / np.where(reference > 0.0, reference, 1.0),
            np.where(defect == 0.0, 0.0, np.inf),
        )
        # A non-finite component: no measure (NaN), left to the evaluation.
        relative = np.where(np.isfinite(p).all(axis=(1, 2))[:, None], relative, np.nan)
    relative = np.where(known, relative, 0.0)
    return [tuple(row) for row in relative.tolist()]


def shell_refusals(
    points: Sequence[Sequence[Sequence[Any]]],
    masses2: Sequence[Sequence[Fraction | None]],
    defects: Sequence[Sequence[float]],
) -> dict[int, list[str]]:
    """The points the guard refuses (a leg's defect above ``shell_bound``),
    by index, with the refusal (``SHELL_STAGE``, the leg, its p^2 and the
    bound m^2, the defect and the bound; a non-finite defect, a non-finite
    component, is left to the evaluation)."""

    out: dict[int, list[str]] = {}
    for index, (point, masses, legs) in enumerate(
        zip(points, masses2, defects, strict=True)
    ):
        bound = shell_bound(len(point))
        if not legs or any(math.isnan(value) for value in legs):
            continue
        worst = max(range(len(legs)), key=lambda k: legs[k])
        if not legs[worst] > bound:
            continue
        energy, x, y, z = (Fraction(str(value)) for value in point[worst])
        square = energy * energy - x * x - y * y - z * z
        mass2 = masses[worst]
        out[index] = [
            f"{SHELL_STAGE}: external leg {worst + 1} is off the mass shell the "
            f"amplitude binds: p^2 = {float(square)!r}, bound m^2 = "
            f"{float(mass2)!r} (m = {math.sqrt(float(mass2))!r}); relative "
            f"shell defect {legs[worst]:.3e} above {bound:.3e}, the rounding "
            f"bound of a binary64 point, (2n + 5) u at n = {len(point)}. Give "
            "momenta on the shells the artifact binds (its fixed parameters), "
            "or let the kinematics improvement move them there "
            "(kinematics_improvement_binary64=True, or a carrier above binary64)"
        ]
    return out


def shell_leg(reason: str) -> int | None:
    """The 0-based external leg a guard refusal (``shell_refusals``) names,
    also within a longer failure text (a fallback's), None for any other
    failure reason."""

    prefix = f"{SHELL_STAGE}: external leg "
    at = reason.find(prefix)
    if at < 0:
        return None
    return int(reason[at + len(prefix) :].split(" ", 1)[0]) - 1


def failure_diagnostic(index: int, reason: str, stage: str = "v2-evaluation") -> Any:
    """The failure record (``VirtualFailureDiagnostic``) of a point that
    failed with ``reason``: a guard refusal's at stage ``SHELL_STAGE``, naming
    its external leg; any other at ``stage``."""

    from pyamplicol.api.virtual_results import VirtualFailureDiagnostic

    leg = shell_leg(reason)
    if leg is None:
        return VirtualFailureDiagnostic(index, None, None, None, stage, reason)
    return VirtualFailureDiagnostic(
        index, None, None, None, SHELL_STAGE, reason, external_leg=leg
    )


@dataclass(frozen=True, slots=True)
class ShellCheck:
    """The guard's measure of one carrier's points of a call: per point the
    shell defect of every leg (``shell_defects``, in the caller's leg
    order) and the refused points (``shell_refusals``, by index)."""

    defects: tuple[tuple[float, ...], ...]
    refused: Mapping[int, list[str]]


def shell_check(
    points: Sequence[Sequence[Sequence[Any]]],
    scales: Sequence[Any],
    precision: Any,
    masses: MassProvider,
) -> ShellCheck:
    """The guard on the points one carrier evaluates (``precision``, a v2
    ``Precision``; the caller's legs, after the call's kinematics
    improvement) against the squared masses the evaluation binds
    (``masses``, the improvement's provider: per mu_R^2 of the batch, as
    the improvement asks it)."""

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
    defects = shell_defects(points, masses2, binary64=precision.arithmetic == "double")
    return ShellCheck(tuple(defects), shell_refusals(points, masses2, defects))


def guarded_run(
    run: Callable[[list[int]], tuple[list[Any], Mapping[int, list[str]]]],
    count: int,
    refused: Mapping[int, list[str]],
    indices: Sequence[int] | None = None,
) -> tuple[list[Any], dict[int, list[str]]]:
    """``run`` (indices of the call's points -> results and failures by
    position) of the points ``indices`` (None: all ``count``) that the guard
    admits; a refused point is not evaluated: its result is None and its
    failure the refusal. Results and failures by position in ``indices``."""

    chosen = list(range(count)) if indices is None else list(indices)
    kept = [i for i in chosen if i not in refused]
    found, failed = run(kept) if kept else ([], {})
    results: list[Any] = [None] * len(chosen)
    failures: dict[int, list[str]] = {}
    at = {index: position for position, index in enumerate(chosen)}
    for local, index in enumerate(kept):
        results[at[index]] = found[local]
        if local in failed:
            failures[at[index]] = list(failed[local])
    for index in chosen:
        if index in refused:
            failures[at[index]] = list(refused[index])
    return results, failures


__all__ = [
    "BINARY64",
    "SETTING",
    "KinematicsSettings",
    "LevelImprover",
    "MassProvider",
    "ShellCheck",
    "binary64_value",
    "default_binary64",
    "default_setting",
    "failure_diagnostic",
    "guarded_run",
    "improve",
    "initial_count",
    "notes",
    "off_record",
    "policy",
    "resolve",
    "setting_value",
    "shell_bound",
    "shell_check",
    "shell_defects",
    "shell_leg",
    "shell_refusals",
    "with_kinematics",
]
