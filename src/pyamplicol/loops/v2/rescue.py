# SPDX-License-Identifier: 0BSD
"""The built-in stability rescue of a v2 virtual ``evaluate`` (user ruling
2026-10-31 Q9; M-FINAL MF-RESCUE).

A :class:`~pyamplicol.api.virtual_results.VirtualRescuePolicy` is an ordered
ladder of levels (carrier, stability checks, target), modelled on gammaloop's
``StabilitySettings``. ``rescue`` runs it on one batch through a level
evaluator, the runtime's own single-carrier evaluation of a subset of the
batch (``V2VirtualRuntime`` and ``V2ObservablesRuntime``):

1. level 0 evaluates the whole batch;
2. a point that failed (``FailedPoints`` reasons, failures of its rotated
   evaluations included) or whose estimate missed the level's target is
   evaluated again at the next level, from its original exact inputs (no
   value is promoted, MASTER_PLAN §2.18, except the refused lanes' binary64
   coefficients, lifted exactly into the lane rescue's higher-carrier
   reduction inside a level); an accepted point is never
   evaluated again; a point whose estimate grew, against the next lower
   precision under the same metric, at least by the square root of the two
   levels' unit-roundoff ratio (``_stalled``), or whose value is zero
   within its estimate at both precisions while its E / S fell at least by
   their unit-roundoff ratio to the power 3/2 (``_vanishing``), is not
   escalated either (the stopping rule: the signatures of a numerical
   zero) and keeps that level's value with the target not met;
3. at the last level a point that evaluates keeps its value with the target
   marked as not met; a point that failed at every level is a failed lane,
   or, under ``on_failure="best-effort"``, a best-effort lane when the last
   level's unchecked reduction gives it a value (only the last level runs
   the best-effort evaluation, ``reduction.with_fallback``).

A level compares the public estimate's field named by its ``metric`` with
its target. An integrated zero (a Landau-Yang |A|^2 of a loop-induced
process, m-lit PLAN §2.a.8; numerical, never declared, RULED Q13) can never
meet a "relative" or "finite" target, its value being itself rounding. Its
estimate's floor is first order in each side's term floor (``stability``),
so its value (|A|^2 of amplitudes that vanish to u) and its estimate both
fall like u^2: its relative estimate stays above 1 at every precision while
its scale-relative estimate E / S falls like u^2, where a real point's
falls like u. The stopping rule's second criterion (``_vanishing``) keeps
it at the first level of higher precision where it is zero within its
estimate there and below and its E / S fell at least by (u_lower / u)^(3/2),
with the target not met (g g > z on the loop-induced default stack: the
double-double level; before the rule it climbed to the last level). The
first criterion (``_stalled``: the relative estimate grew at least by
sqrt(u_lower / u)) is kept. The opt-in "scale" metric
(``VirtualRescueLevel.metric``: E <= target x S, the estimate against the
pre-cancellation scale S, ``VirtualStabilityEstimate.scale``) accepts it at
the first level, where its E / S is at least the floor's second-order
(FLOOR_UNITS x u)^2 (M-LIT LIT-STAB-N, ``tests/unit/
test_loop_v2_induced_stability.py``).

Every level evaluates the points it receives in ONE call: the native
executor fills its chunks (binary64 SIMD chunks of the narrowest width
holding the rest, the scalar lanes of the extended carriers in filled
chunks, ``rusticol-core loop_execution::v2::lane_chunks``), so no padded
lane is evaluated and one executor serves each carrier. Every point's
value is its own lane's: the same as in a call of its own. The
per-scale partition and flavour members stay inside the level evaluator.
The rescue is off unless a policy is passed (REQUIREMENTS_ADDENDUM C:
never on for timing); it is offered by the Python native ``evaluate``
only, in no SDK, the CLI or the configuration.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, cast

from pyamplicol.api.errors import CompatibilityError, EvaluationError
from pyamplicol.api.virtual_results import (
    VirtualEvaluation,
    VirtualLaneDiagnostic,
    VirtualRescueAttempt,
    VirtualRescueLevel,
    VirtualRescuePolicy,
    VirtualRescueRecord,
    splits_poles,
    uncertified_detail,
)
from pyamplicol.kinematics import is_shell_reason
from pyamplicol.loops.v2.stability import relative_text

# One level's evaluation of the points at the given batch indices (in that
# order), failures returned as failed lanes (``on_failure="return"``).
LevelEvaluator = Callable[[tuple[int, ...], VirtualRescueLevel], VirtualEvaluation]

RESCUE_SCOPE = (
    "a VirtualRescuePolicy (stability=) applies to evaluate only; "
    "evaluate_resolved and evaluate_correlated(_many) take stability_checks "
    "and leave escalation to the caller"
)
RESCUE_OWNS_CARRIER = (
    "a VirtualRescuePolicy chooses each level's arithmetic, precision and "
    "stability checks; pass no arithmetic, precision or stability_checks "
    "with stability="
)


def loop_induced_stack() -> VirtualRescuePolicy:
    """The loop-induced default stack (m-lit F3 (b), USER 2026-11-08 ~15:40,
    DECISIONS 15:32): the default ladder's binary64 level on TIRust (at the
    default target, its acceptance calibrated from it), the same level on
    NinjaRS, then the default ladder's higher levels (``"auto"``)."""

    first, *rest = VirtualRescuePolicy().levels
    return VirtualRescuePolicy(
        (replace(first, reduction="tirust"), replace(first, reduction="ninjars"), *rest)
    )


def default_stack(
    policy: VirtualRescuePolicy | None,
    contribution: str,
    requested: str,
    fallback: str | None,
) -> VirtualRescuePolicy | None:
    """The stack a call runs: the loop-induced default stack
    (``loop_induced_stack``) for the default policy (``VirtualRescuePolicy()``)
    of a loop-induced call requesting ``"auto"`` whose ``"auto"`` takes
    TIRust in binary64 with a per-point NinjaRS fallback (``fallback``, the
    native policy's choice there: none on a TIR-only artifact or in a build
    without TIRust); any other policy as given. A call naming a backend runs
    the default ladder on it at every level (its levels are ``"auto"``)."""

    if (
        policy is None
        or policy != VirtualRescuePolicy()
        or contribution != "loop-induced"
        or requested != "auto"
        or fallback != "ninjars"
    ):
        return policy
    return loop_induced_stack()


def rescue_policy(
    stability: object,
    *,
    default: VirtualRescuePolicy | None = None,
    arithmetic: str | None = None,
    precision: int | None = None,
    default_precision: int | None = None,
    stability_checks: object = None,
) -> VirtualRescuePolicy | None:
    """The rescue policy of one call: ``stability`` when given (refused
    together with an explicit carrier or checks, which the levels own), else
    the load-time ``default`` unless the call names its own arithmetic, a
    precision other than ``default_precision`` or stability checks (such a
    call evaluates in that one carrier, without rescue). Checks that run
    nothing but set a floor weight are no checks: their weight reaches the
    policy's levels that set none (``VirtualRescuePolicy.with_floor_weight``;
    a level's own weight wins), resolved per call, never stored in the
    policy. Empty checks (no check, no weight) are explicit checks, as
    before the weight existed: a plain call without the policy."""

    weight = None
    if stability_checks is not None and not getattr(stability_checks, "enabled", True):
        weight = getattr(stability_checks, "floor_weight", None)
    checks = stability_checks is not None and weight is None
    explicit = (
        arithmetic is not None
        or (precision is not None and precision != default_precision)
        or checks
    )
    if stability is None:
        if explicit or default is None:
            return None
        return default.with_floor_weight(weight)
    if not isinstance(stability, VirtualRescuePolicy):
        raise TypeError("stability takes a VirtualRescuePolicy")
    if explicit:
        raise CompatibilityError(RESCUE_OWNS_CARRIER)
    return stability.with_floor_weight(weight)


@dataclass(frozen=True, slots=True)
class _Kept:
    """The evaluation (and its lane) that returns one point."""

    evaluation: VirtualEvaluation
    lane: int
    level: int
    met: bool
    # Kept below the last level by the stopping rule (``_stalled``): the
    # lower-precision attempt whose estimate it did not improve on.
    stalled: _Stall | None = None


def rescue(
    policy: VirtualRescuePolicy,
    count: int,
    evaluate: LevelEvaluator,
    *,
    on_failure: str = "raise",
) -> VirtualEvaluation:
    """Run ``policy`` on a batch of ``count`` points through ``evaluate``
    (module docstring); one ``VirtualEvaluation`` in the batch order with
    ``rescue`` records. ``on_failure="raise"`` raises only for a point that
    failed at every level."""

    levels = policy.levels
    attempts: list[list[VirtualRescueAttempt]] = [[] for _ in range(count)]
    # Per point and attempt its zero signature (``_signature``), for the
    # stopping rule's second criterion (``_vanishing``).
    signatures: list[list[_Signature | None]] = [[] for _ in range(count)]
    kept: list[_Kept | None] = [None] * count
    pending = tuple(range(count))
    template: VirtualEvaluation | None = None
    for k, level in enumerate(levels):
        if k and not pending:
            break
        last = k == len(levels) - 1
        batches = [pending]
        retry: list[int] = []
        for batch in batches:
            evaluation = evaluate(batch, level)
            if len(evaluation.diagnostics) != len(batch):
                raise EvaluationError("a rescue level returned another lane count")
            template = template or evaluation
            for lane, index in enumerate(batch):
                diagnostic = evaluation.diagnostics[lane]
                attempt = _attempt(evaluation, lane, level)
                attempts[index].append(attempt)
                signatures[index].append(_signature(evaluation, lane))
                # A level whose result carries lanes served without accuracy
                # evidence (``VirtualLaneDiagnostic.uncertified``) is never
                # met: the policy escalates, or keeps it not established.
                met = (
                    diagnostic.valid
                    # (The shell-consistency screen's mark never escalates by
                    # itself: a higher carrier serves the same kinematics.)
                    and not [
                        reason
                        for reason in getattr(diagnostic, "uncertified", ())
                        if not is_shell_reason(reason)
                    ]
                    and attempt.estimate is not None
                    and attempt.estimate <= level.target
                )
                stalled = (
                    None
                    if met or last or not diagnostic.valid
                    else _stalled(attempts[index], levels)
                    or _vanishing(attempts[index], signatures[index], levels)
                )
                if met or last or stalled is not None:
                    kept[index] = _Kept(evaluation, lane, k, met, stalled)
                else:
                    retry.append(index)
        pending = tuple(sorted(retry))
    if template is None:  # pragma: no cover - level 0 always runs
        raise EvaluationError("a rescue policy ran no level")
    return _merged(template, kept, attempts, policy, on_failure)


def _stalled(
    history: list[VirtualRescueAttempt], levels: tuple[VirtualRescueLevel, ...]
) -> _Stall | None:
    """The stopping rule ("stop when no gain", USER 2026-11-18; refined by
    review B3): a point is not escalated when its estimate at its latest
    level (the last of ``history``, one attempt per level from level 0)
    GREW, against its estimate at the next lower precision under the same
    metric, at least by sqrt(u_lower / u_latest), the square root of the
    ratio of the two levels' unit roundoffs. That growth is the signature of
    a numerical zero: its value is rounding of the size u^2 (|A|^2 of
    amplitudes that vanish to u) while its absolute error falls like u, so
    its relative estimate grows like 1 / u (g g > z: 4.7e15 in binary64,
    8.4e33 in double-double, a growth of 1.8e18 against the 4.7e7 needed).
    A real point's relative estimate falls with u, or, ruined (a relative
    estimate above 1 has no order), stays flat and noisy, its error and its
    wrong value falling together (HC05 #40 point 29: 13.96 at 50 digits,
    48.8 at 57, a growth of 3.5 against the 3.2e3 needed): both escalate.
    The argument holds for the same computation at two roundoffs: where two
    backends ran at the next lower precision (the loop-induced default
    stack's TIRust and NinjaRS binary64 levels), the comparison is with the
    latest level's own effective backend when it has an estimate there, else
    with the larger of their estimates (never the smaller, which would count
    the gap between the backends as growth: review F1). Returns the
    comparison (``_Stall``), or None (escalate). A failed attempt has no
    estimate and never stops a point; nor does a level of the same
    precision (the other backend)."""

    latest = history[-1]
    if latest.estimate is None:
        return None
    k = len(history) - 1
    metric = levels[k].metric
    lower = [
        (j, attempt)
        for j, attempt in enumerate(history[:-1])
        if attempt.estimate is not None
        and attempt.precision_bits < latest.precision_bits
        and levels[j].metric == metric
    ]
    if not lower:
        return None
    # The next lower precision. The growth argument holds for the same
    # computation at two roundoffs: where two backends ran there, compare
    # with the latest level's own effective backend when it has an estimate,
    # else with the larger estimate (review F1: the smaller would add the gap
    # between the backends to the growth).
    bits = max(attempt.precision_bits for _, attempt in lower)
    candidates = [
        (j, attempt) for j, attempt in lower if attempt.precision_bits == bits
    ]
    mine = _effective(latest)
    same = [item for item in candidates if mine and _effective(item[1]) == mine]
    j, below = max(same or candidates, key=lambda item: cast(float, item[1].estimate))
    before, after = cast(float, below.estimate), latest.estimate
    if not before or not after:
        return None
    needed = (_log2_roundoff(levels[j]) - _log2_roundoff(levels[k])) / 2
    grew = math.log2(after) - math.log2(before) if math.isfinite(after) else math.inf
    return _Stall(below, grew, needed) if grew >= needed else None


@dataclass(frozen=True, slots=True)
class _Stall:
    """A point the stopping rule keeps: the lower-precision attempt compared
    with, and log2 of the estimate's growth and of the growth needed."""

    attempt: VirtualRescueAttempt
    grew: float
    needed: float
    # "grew": the relative estimate grew (``_stalled``); "fell": the
    # scale-relative estimate E / S fell quadratically while the value stayed
    # within its estimate (``_vanishing``; ``grew`` then holds log2 of the
    # fall).
    kind: str = "grew"


@dataclass(frozen=True, slots=True)
class _Signature:
    """What the second stopping criterion reads of one attempt
    (``_vanishing``): the public estimate's largest E / S (``scale``) and
    whether the value is zero within its estimate, |value_k| <= E_k for
    every sector and computed Laurent coefficient k."""

    scale: float
    within: bool


def _signature(evaluation: VirtualEvaluation, lane: int) -> _Signature | None:
    """The attempt's ``_Signature``, or None where the lane has no value, no
    estimate or no E / S (the criterion then never stops the point)."""

    if evaluation.stability is None or evaluation.values is None:
        return None
    estimate = evaluation.stability[lane]
    values = evaluation.values[lane]
    scale = None if estimate is None else getattr(estimate, "scale", None)
    absolute = None if estimate is None else getattr(estimate, "absolute", None)
    if values is None or scale is None or absolute is None:
        return None
    if len(values) != len(absolute):
        return None
    within, compared = True, 0
    for value, error in zip(values, absolute, strict=True):
        for name in ("finite", "single_pole", "double_pole"):
            x, e = getattr(value, name, None), getattr(error, name, None)
            if x is None or e is None:
                continue
            compared += 1
            if not abs(complex(x)) <= float(e):
                within = False
    if not compared:
        return None
    return _Signature(float(scale), within)


def _vanishing(
    history: list[VirtualRescueAttempt],
    signatures: list[_Signature | None],
    levels: tuple[VirtualRescueLevel, ...],
) -> _Stall | None:
    """The stopping rule's second criterion ("stop when no gain" for a
    numerical zero, USER 2026-11-18; restated for an estimate whose floor is
    first order in each side's term floor, ``stability``): the point is not
    escalated when its value is zero within its estimate (|value_k| <= E_k,
    ``_signature``) at its latest level AND at the next lower precision, and
    its scale-relative estimate E / S fell between the two by at least
    (u_lower / u_latest)^(3/2). A numerical zero's E falls like u^2 (its
    amplitudes are rounding of the size u S, so both the first-order floor
    and the checks' budgets are of the size u^2 S), a real or ruined
    point's like u (S is the same at every precision): the 3/2 power
    separates the two as the square root does in ``_stalled``. The lower
    attempt is the latest level's own effective backend's when it ran
    there, else the one with the smallest E / S (the smaller fall: the gap
    between two backends never counts as a fall). Returns the comparison
    (``_Stall``, kind "fell"), or None (escalate)."""

    latest, mine = history[-1], signatures[-1]
    if latest.estimate is None or mine is None or not mine.within:
        return None
    lower = [
        (j, attempt)
        for j, attempt in enumerate(history[:-1])
        if signatures[j] is not None
        and attempt.estimate is not None
        and attempt.precision_bits < latest.precision_bits
    ]
    if not lower:
        return None
    bits = max(attempt.precision_bits for _, attempt in lower)
    candidates = [
        (j, attempt) for j, attempt in lower if attempt.precision_bits == bits
    ]
    backend = _effective(latest)
    same = [item for item in candidates if backend and _effective(item[1]) == backend]
    j, below = min(
        same or candidates, key=lambda item: cast(_Signature, signatures[item[0]]).scale
    )
    found = cast(_Signature, signatures[j])
    before, after = found.scale, mine.scale
    if not found.within or not before or not after:
        return None
    needed = 1.5 * (
        _log2_roundoff(levels[j]) - _log2_roundoff(levels[len(history) - 1])
    )
    fell = math.log2(before) - math.log2(after)
    return _Stall(below, fell, needed, "fell") if fell >= needed else None


def _effective(attempt: VirtualRescueAttempt) -> str | None:
    """The attempt's effective reduction backend, None when not recorded."""

    return None if attempt.reduction is None else attempt.reduction.effective


def _factor(log2: float) -> str:
    """2^log2 as text (``inf`` beyond binary64)."""

    return f"{2.0**log2:.1e}" if log2 < 1000 else "inf"


def _log2_roundoff(level: VirtualRescueLevel) -> float:
    """log2 of a level's unit roundoff: 2^-53 binary64, 2^-104
    double-double (``assemble.Precision.unit_roundoff``), 0.5 x 10^(1 - d)
    at d digits."""

    if level.arithmetic == "double":
        return -53.0
    if level.arithmetic == "double-double":
        return -104.0
    return -1.0 + (1 - cast(int, level.precision)) * math.log2(10.0)


def _attempt(
    evaluation: VirtualEvaluation, lane: int, level: VirtualRescueLevel
) -> VirtualRescueAttempt:
    diagnostic = evaluation.diagnostics[lane]
    # The level's reduction backend as its evaluation recorded it
    # (``VirtualLaneDiagnostic.reduction``: requested, effective, reason).
    # A best-effort lane (the last level's, ``on_failure="best-effort"``)
    # is an attempt with a value: its estimate when the level checks.
    if not diagnostic.has_value:
        return VirtualRescueAttempt(
            diagnostic.arithmetic,
            diagnostic.precision_bits,
            None,
            diagnostic.detail or diagnostic.status,
            diagnostic.reduction,
            diagnostic.kinematics,
        )
    estimate = None if evaluation.stability is None else evaluation.stability[lane]
    value = None if estimate is None else float(getattr(estimate, level.metric))
    return VirtualRescueAttempt(
        diagnostic.arithmetic,
        diagnostic.precision_bits,
        value,
        reduction=diagnostic.reduction,
        kinematics=diagnostic.kinematics,
    )


def _detail(
    record: VirtualRescueRecord,
    metric: str,
    stalled: _Stall | None = None,
) -> str:
    level = f"rescue level {record.level} ({record.arithmetic})"
    value = record.attempts[-1].estimate
    if value is None:
        return f"{level}: last level, no stability check; accuracy not estimated"
    if record.met:
        verdict = f"within the target {record.target:.1e}"
    elif stalled is not None and stalled.kind == "fell":
        below = stalled.attempt
        backend = "" if below.reduction is None else f" {below.reduction.effective}"
        verdict = (
            f"target {record.target:.1e} not met; not escalated: the value is "
            f"zero within its estimate here and at the {below.arithmetic}{backend} "
            f"level, whose E / S fell by {_factor(stalled.grew)} to this one's "
            f"(at least {_factor(stalled.needed)}, their unit-roundoff ratio to "
            "the power 3/2), as a numerical zero's does"
        )
    elif stalled is not None:
        below = stalled.attempt
        backend = "" if below.reduction is None else f" {below.reduction.effective}"
        verdict = (
            f"target {record.target:.1e} not met; not escalated: its estimate "
            f"grew from the {below.arithmetic}{backend} level's by "
            f"{_factor(stalled.grew)} (at least {_factor(stalled.needed)}, the "
            "square root of their unit-roundoff ratio), as a numerical zero's does"
        )
    else:
        verdict = f"target {record.target:.1e} not met at the final level"
    return f"{level}: estimated {metric} accuracy {relative_text(value)}, {verdict}"


def _merged(
    template: VirtualEvaluation,
    kept: list[_Kept | None],
    attempts: list[list[VirtualRescueAttempt]],
    policy: VirtualRescuePolicy,
    on_failure: str,
) -> VirtualEvaluation:
    """One evaluation of every point from the lanes that return them."""

    born: list[Any] = []
    values: list[Any] = []
    diagnostics: list[VirtualLaneDiagnostic] = []
    estimates: list[Any] = []
    parts: list[Any] = []
    records: list[VirtualRescueRecord] = []
    failed: dict[int, str] = {}
    for index, item in enumerate(kept):
        if item is None:  # pragma: no cover - the last level keeps every point
            raise EvaluationError(f"rescue kept no evaluation of point {index}")
        evaluation, lane = item.evaluation, item.lane
        level = policy.levels[item.level]
        original = evaluation.diagnostics[lane]
        record = VirtualRescueRecord(
            item.level,
            original.arithmetic,
            original.precision_bits,
            level.target,
            item.met,
            tuple(attempts[index]),
        )
        if original.status == "best-effort":
            # Every level refused the point; the last level's best-effort
            # value is returned, never as a success.
            diagnostic = replace(
                original,
                detail=f"{_detail(record, level.metric)}; {original.detail}",
                failures=tuple(
                    replace(failure, point_id=index) for failure in original.failures
                ),
            )
        elif original.valid:
            diagnostic = replace(
                original,
                status="success" if item.level == 0 else "rescued",
                accuracy_established=item.met and not original.uncertified,
                detail=_detail(record, level.metric, item.stalled)
                + uncertified_detail(original.uncertified),
            )
        else:
            reasons = "; ".join(
                f"level {k} ({attempt.arithmetic}): {attempt.failure}"
                for k, attempt in enumerate(record.attempts)
            )
            failed[index] = reasons
            diagnostic = replace(
                original,
                detail=f"failed at every rescue level: {reasons}",
                failures=tuple(
                    replace(failure, point_id=index) for failure in original.failures
                ),
            )
        born.append(evaluation.born_values[lane])
        values.append(evaluation.values[lane])
        diagnostics.append(diagnostic)
        estimates.append(
            None if evaluation.stability is None else evaluation.stability[lane]
        )
        parts.append(
            None if evaluation.pole_parts is None else evaluation.pole_parts[lane]
        )
        records.append(record)
    if failed and on_failure == "raise":
        index = min(failed)
        raise EvaluationError(
            f"v2 virtual evaluation failed at point {index} at every rescue "
            f"level: {failed[index]}",
            failures=diagnostics[index].failures,
        )
    checked = any(level.checks.enabled for level in policy.levels)
    return VirtualEvaluation(
        tuple(born),
        tuple(values),
        template.born_orders,
        template.sectors,
        tuple(diagnostics),
        template.r2,
        template.correlated,
        color_accuracy=template.color_accuracy,
        poles=template.poles,
        stability=tuple(estimates) if checked else None,
        pole_parts=tuple(parts) if splits_poles(template.poles) else None,
        rescue=tuple(records),
        # The kind of the levels' results ("virtual" or "loop-induced").
        contribution=template.contribution,
    )


__all__ = [
    "RESCUE_OWNS_CARRIER",
    "RESCUE_SCOPE",
    "LevelEvaluator",
    "rescue",
    "rescue_policy",
]
