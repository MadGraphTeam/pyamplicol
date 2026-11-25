# SPDX-License-Identifier: 0BSD
"""On-demand physics checks of one-loop requests (``pyamplicol check``,
m-lit lit-examples, USER 2026-11-09 ~08:30: "a pyAmpliCol subcommand
`check` (which does ward and pole checks (catani for trees, and zero poles
for loop-induced))").

A check runs on an in-memory slice of the request (nothing is written): the
generation-time probe slice (``induced.probe_request_of``,
``ward.ward_slice``), i.e. the request on the model's full tree kernels with
every width zeroed outside the complex-mass scheme, at seeded phase-space
points of the generation's validation convention lifted to exact momentum
conservation (``induced.probe_point``; every carrier evaluates the same
exact point), with mu_R^2 the squared invariant mass of the initial state
(``induced._point_scale``). Every check reduces on ``induced.
PROBE_REDUCTION`` (NinjaRS) at every carrier.

**THE RULE** (USER 2026-11-25: "Just test for R < K * S where K is a
threshold set as a parameter for the checks, and typically of the order of
the requested number of stable digits"; ``judge``, ``settle``,
``ladder_step``): every independently required row (a point, a sector or
loop order and helicity row, a leg and factor, a Laurent coefficient) is
judged on its own, before any aggregation, from its residue R, its PHYSICAL
reference P (the size of the physical quantities whose difference or
vanishing the identity tests, at the same point, carrier and row or
sector), the estimate E_P of P's own numerical uncertainty where the
evaluation forms one, and its term scale T (the size of the terms that
cancel into it):

1. a required operand missing or not a finite number: INCONCLUSIVE (never
   vacuous, never dropped);
2. a complete row with no contributing term (R = 0 and T = 0): VACUOUS,
   skipped and counted (a check every row of which is vacuous has nothing
   to test and passes with that warning);
3. a known-zero reference (an analytic zero: a Catani pole that vanishes
   exactly; the poles of a loop-induced amplitude on both sides of the
   Goldstone identity): PASS iff R < K T, labelled term-relative;
4. R < K P: PASS on the physical scale (equality is a miss);
5. otherwise a miss: where R < K T would pass and P may be noise (P = 0
   from cancelling terms, or P <= ``induced.ESTIMATE_FACTOR`` E_P; no
   estimate: a finite P > 0 is physical) the row is AMBIGUOUS and only it
   is evaluated at the next carrier at the same point, where P either
   REPRODUCES (|P_wide - P_narrow| < K P_narrow: a physical miss), or
   COLLAPSES with the carriers' noise (P_wide / P_narrow at most
   sqrt(u_wide / u_narrow): R < K T, labelled term-relative), or neither
   (INCONCLUSIVE: physical normalisation unresolved; also where no wider
   carrier is available); any other miss climbs the carrier ladder as a
   miss and fails if the last carrier still misses.

The ladder is per row: a row keeps its first decision, a pending row a
later carrier lacks is inconclusive, a refused carrier leaves the next one
to try, and a check's verdict is formed at the end from its rows' final
verdicts (``aggregate``: FAIL, else INCONCLUSIVE, else PASS, else
VACUOUS). R, P and T are linear in the amplitude (colour-metric norms, or
the interference itself), so K is a relative accuracy of the checked
quantity. K is the check's tolerance (``tolerance``: ``check.tolerance``,
else the run's requested relative accuracy ``evaluation.reduction_target``,
whose default is the native policy's target ``reduction.default_target()``).
The comparisons are ordinary carrier arithmetic: this is a tolerance, not a
certificate. Each row reports R over the scale that decided, R, P, E_P, T,
the scale (physical, term-relative or vacuous) and the deciding carrier;
the evaluation's error estimate E is reported for information and decides
nothing.

* **Poles, Born-interfered** (``born_interfered_rows``, ``_pole_measures``):
  per point, squared-order sector and pole coefficient k of the
  renormalised virtual V (poles "all") against Catani's prediction C of the
  requested corrections (QCD and QED summed per sector, formed natively,
  ``NativeExecutor(catani=True)``): R = |Re V_k - Re C_k|, P = max(|Re
  C_k|, |Re V_k|) (an analytic reference: a C_k that is exactly zero is a
  known zero), T = the largest of the virtual and its parts (bare, R2, UV)
  at that sector and coefficient. A sector the operators do not predict is
  listed with its reason (``poles.UNPREDICTED_REASONS``), never as a pass; a
  sector they predict without a pole row at a point is "not run" (an
  applicable check that did not run).
* **Ward, Born-interfered** (``_ward_measures``): ``ward.ward_check`` on
  every external gluon and photon leg (``ward.gauge_legs``) and both
  factors (``ward.WARD_FACTORS``): per Born sector R = |loop-side Born|, P =
  T = |physical Born|; per virtual sector and coefficient R = |V_k| of the
  substituted evaluation, P = |V_k| of the physical evaluation at the same
  point (E_P its estimate where it ran its checks), T = its largest part.
* **Loop-induced** (``induced.point_probes``): the finiteness probe (R =
  the colour-metric norm of each pole coefficient of each loop order and
  helicity row) and the amplitude-level Ward probe of one leg of every
  gluon and photon species (R = the substituted amplitude's norm at every
  coefficient): P = the norm of the physical finite amplitude of that row
  at the same point and carrier with its estimate E_P
  (``induced.physical_references``; for a Ward row the largest over the
  substituted leg's helicities), T = the row's term floor S_k(h)
  (``induced.row_scales``, ``induced.ward_floors``).
* **Goldstone** (``induced.goldstone_point``): k.A(V) = eta M_V A(G) where
  the probe serves the slice (``induced.goldstone_applicability``:
  't Hooft-Feynman gauge, an external massive vector with a Goldstone
  partner, a loop-induced amplitude); R = ||A(V)_k - eta (M/E) A(G)_k||,
  P = max(||A(V)_k||, ||eta (M/E) A(G)_k||) with that side's estimate
  (the poles, k >= 1: a known zero), T = the vector row's floor plus M/E
  times the Goldstone row's, over the union of both sides' rows
  (``goldstone.probe``); otherwise a "not applicable" row with the reason.
* **Ward rows not applicable** (``ward_applicability``, USER 2026-11-10
  ~00:17): a request whose corrections include one other than the model's
  strong correction and with an on-shell zero-width external massive quark
  has one "not applicable" Ward row (the Ward identity of the asymmetric
  check is not guaranteed there), nothing evaluated; Ward rows are not split
  by squared-order sector, so its QCD-loop sectors are not checked either.

Carriers (``induced.probe_carriers``): binary64 first and double-double
only for a row binary64 does not decide (a failure, an inconclusive or
ambiguous row, or a refused run); an explicit carrier alone otherwise.

**The arbitrary-precision rung** (``auto`` only, Born-interfered rows): a
row double-double does not decide (refused included) is evaluated again in
arbitrary precision at ``check.arbitrary_digits`` digits, by default twice
the last carrier's decimal digits (``rung_digits``), the point lifted
again at those digits. The loop-induced probes keep their ladder (binary64,
double-double).
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Any

# The stored-process harness's criteria (``tools/loop_benchmark/
# stored_checks.py``, which imports them): each deviation within ESTIMATES x
# E plus CATANI_FLOOR of the prediction (binary64 with the recommended
# checks), or within CATANI_DD_FLOOR of the prediction in double-double.
# ``pyamplicol check`` judges by ``threshold`` (module docstring).
ESTIMATES = 10
CATANI_FLOOR = 1e-12
CATANI_DD_FLOOR = 1e-12

# Row verdicts: only PASS is a pass; UNDECIDED (no longer produced by the
# threshold rule; kept for records) fails its process as FAIL does;
# NOT_APPLICABLE, NO_PREDICTION and NOT_RUN carry their reason and never
# count as one.
PASS = "pass"
FAIL = "fail"
UNDECIDED = "undecided"
NOT_APPLICABLE = "not applicable"
NO_PREDICTION = "no prediction"
NOT_RUN = "not run"
# A row whose R or S cannot be computed (``threshold``): never a pass; the
# ladder's next carrier evaluates the row again.
INCONCLUSIVE = "inconclusive"
# A row with no term at all (R = 0 exactly and T = 0, ``judge``): nothing to
# test; neither a pass counted as evidence nor an inconclusive.
VACUOUS = "vacuous"
VERDICTS = (
    PASS,
    FAIL,
    UNDECIDED,
    NOT_APPLICABLE,
    NO_PREDICTION,
    NOT_RUN,
    INCONCLUSIVE,
    VACUOUS,
)
# The verdicts that carry their reason and neither pass nor fail a process.
_NEUTRAL = (NOT_APPLICABLE, NO_PREDICTION, VACUOUS)

# Process statuses and the exit code of a report (``CheckReport.exit_code``).
PASSED = "passed"
FAILED = "failed"
NOTHING_CHECKED = "nothing checked"
# A process none of whose rows failed but one of which is inconclusive or
# carries a verdict outside ``VERDICTS``: never passed.
INCONCLUSIVE_STATUS = "inconclusive"
EXIT_PASSED = 0
EXIT_FAILED = 1
EXIT_NOTHING_CHECKED = 3
EXIT_INCONCLUSIVE = 4

POLE_NAMES = {1: "1/eps", 2: "1/eps^2"}


def catani_comparison(
    values: Sequence[float],
    poles: Sequence[Any],
    absolute: Sequence[float] | None = None,
) -> tuple[list[float], list[float], list[float], bool]:
    """The binary64 pole criterion of one sector: ``values`` the real Laurent
    coefficients (finite, 1/eps, 1/eps^2), ``poles`` Catani's (1/eps,
    1/eps^2) prediction (``PointResult.ir_poles[sector]``), ``absolute`` the
    estimate E per coefficient (None: no estimate). Returns the prediction,
    the deviations |pole - Catani|, their bounds ESTIMATES E + CATANI_FLOOR
    |Catani| and whether both are within them."""

    catani = [complex(poles[0]).real, complex(poles[1]).real]
    deviations: list[float] = []
    bounds: list[float] = []
    ok = True
    for k in (1, 2):
        deviation = abs(values[k] - catani[k - 1])
        bound = CATANI_FLOOR * abs(catani[k - 1])
        if absolute is not None:
            bound += ESTIMATES * absolute[k]
        deviations.append(deviation)
        bounds.append(bound)
        ok = ok and deviation <= bound
    return catani, deviations, bounds, ok


def catani_dd_comparison(
    values: Sequence[float], poles: Sequence[Any]
) -> tuple[list[float], list[float], bool]:
    """The double-double pole criterion of one sector: the relative
    deviations |pole - Catani| / |Catani| of the 1/eps and 1/eps^2
    coefficients and whether both are within ``CATANI_DD_FLOOR``."""

    catani = [complex(poles[0]).real, complex(poles[1]).real]
    errors = [
        abs(values[k] - catani[k - 1]) / max(abs(catani[k - 1]), 1e-300) for k in (1, 2)
    ]
    return catani, errors, all(e <= CATANI_DD_FLOOR for e in errors)


# ------------------------------------------------------- the threshold rule

# The check's tolerance K (``tolerating``; None: ``tolerance``'s default).
_TOLERANCE: ContextVar[float | None] = ContextVar(
    "pyamplicol_check_tolerance", default=None
)


def tolerance() -> float:
    """K of the current check: ``check.tolerance`` (``tolerating``), else the
    run's requested relative accuracy (the reduction target in effect,
    ``evaluation.reduction_target``, ``reduction.targeting``), else the
    native policy's default target (``reduction.default_target``)."""

    found = _TOLERANCE.get()
    if found is not None:
        return found
    from .reduction import current_target, default_target

    target = current_target()
    return float(target) if target is not None else default_target()


@contextmanager
def tolerating(value: float | None) -> Iterator[None]:
    """Judge this context's rows with tolerance ``value`` (None:
    ``tolerance``'s default)."""

    token = _TOLERANCE.set(None if value is None else float(value))
    try:
        yield
    finally:
        _TOLERANCE.reset(token)


def magnitude(value: Any) -> float | None:
    """|value| as a finite binary64 number, None where it is not one (not a
    number, infinite, beyond binary64's range, or not convertible): the
    quantity cannot be computed in binary64 and decides nothing."""

    if value is None:
        return None
    try:
        found = abs(complex(value))
    except (ArithmeticError, TypeError, ValueError):
        return None
    return found if math.isfinite(found) else None


def real_gap(a: Any, b: Any) -> float | None:
    """|Re a - Re b|, the difference formed in the operands' own carrier
    arithmetic (binary64 only where they do not subtract), None where it
    cannot be computed (``magnitude``)."""

    try:
        gap = complex(a - b).real
    except (ArithmeticError, TypeError, ValueError):
        try:
            gap = complex(a).real - complex(b).real
        except (ArithmeticError, TypeError, ValueError):
            return None
    return abs(gap) if math.isfinite(gap) else None


def threshold(residual: float | None, scale: float | None, tolerance_: float) -> str:
    """THE RULE of every row (module docstring): PASS iff R < K S, FAIL iff
    R >= K S (equality is a miss), INCONCLUSIVE iff R or S cannot be
    computed: R not a finite non-negative number, or S not a finite
    positive one (a vanishing scale, 0/0 included). Compared as R / S < K,
    so that neither K S nor R / S underflows to a false verdict."""

    if (
        residual is None
        or scale is None
        or not math.isfinite(residual)
        or not math.isfinite(scale)
        or residual < 0
        or not scale > 0
    ):
        return INCONCLUSIVE
    return PASS if residual / scale < tolerance_ else FAIL


def over(residual: float | None, scale: float | None) -> float | None:
    """R / S where both are computed and S is positive, else None."""

    if residual is None or scale is None or not scale > 0:
        return None
    return residual / scale


def combined(verdicts: Sequence[str]) -> str:
    """The verdict of a row made of several required rows (judged each on its
    own): FAIL if one fails, else INCONCLUSIVE if one is, else PASS (and
    INCONCLUSIVE for none: nothing compared is no pass)."""

    found = set(verdicts)
    if FAIL in found:
        return FAIL
    if INCONCLUSIVE in found or not found:
        return INCONCLUSIVE
    return PASS


@dataclass(frozen=True)
class Measure:
    """One independently required row of a check (module docstring): its
    residue R, its physical reference P, its term scale T (each None where
    it cannot be computed or is missing), the estimate E of R (reported
    only), the estimate E_P of P's own numerical uncertainty (where the
    evaluation forms one: it only flags a possibly unresolved reference),
    whether the reference is a known zero (an analytic or structural zero,
    ``zero_reference``: the row uses the labelled term-relative tolerance
    at once) and whether every operand of the row is present
    (``complete``)."""

    label: str
    residue: float | None
    physical: float | None
    terms: float | None
    estimate: float | None = None
    physical_error: float | None = None
    zero_reference: bool = False
    complete: bool = True


# The rule's name, recorded with K and the explicit verdict wherever a
# verdict is stored (campaign records, generation records, tools): a record
# judged under another rule or another K is re-judged, never reused.
RULE = "threshold-p: per row R < K P (physical); R < K T for a known-zero reference"

# The scale a row was judged against (``Judgement.scale``).
PHYSICAL = "physical"
TERM_RELATIVE = "term-relative"
# A row that misses R < K P, would pass R < K T, and whose P may be noise
# (``judge``): it needs a wider evaluation at the same point (``settle``);
# never a final verdict (``finished``: INCONCLUSIVE).
AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class Judgement:
    """A row's verdict at one carrier (``judge``, ``settle``): the verdict,
    the scale that decided (``PHYSICAL`` P, ``TERM_RELATIVE`` T; None for a
    vacuous or inconclusive row), R over that scale (``ratio``; it passes
    iff below K), the reason of an inconclusive or ambiguous row, the
    measure and the carrier."""

    verdict: str
    scale: str | None
    ratio: float | None
    reason: str | None
    measure: Measure
    carrier: str | None = None
    unit_roundoff: float | None = None
    # The earlier carriers' outcomes of this row ("carrier: verdict, R /
    # scale"), oldest first.
    history: tuple[str, ...] = ()


def _summary(cell: Judgement) -> str:
    """One earlier carrier's outcome of a row, for its history."""

    ratio = "" if cell.ratio is None else f", R / {cell.scale or 'S'} {cell.ratio:.3g}"
    reason = f" ({cell.reason})" if cell.reason and cell.verdict != PASS else ""
    return f"{cell.carrier}: {cell.verdict}{ratio}{reason}"


def judge(measure: Measure, tolerance_: float) -> Judgement:
    """THE RULE for one required row at one carrier (module docstring):

    1. an incomplete row, or one whose R, P or T is not a finite
       non-negative number: INCONCLUSIVE (never vacuous, never dropped);
    2. a complete row with no contributing term (R = 0 and T = 0): VACUOUS;
    3. a known-zero reference (``zero_reference``): R < K T, labelled
       term-relative (PASS / FAIL);
    4. R < K P: PASS on the physical scale;
    5. otherwise a miss on K P: AMBIGUOUS when R < K T would pass and P may
       be noise (P = 0 from cancelling terms, or P <= ``ESTIMATE_FACTOR`` E_P
       where an estimate exists: the flag only), else FAIL on the physical
       scale (no estimate: a finite P > 0 is physical)."""

    from .induced import ESTIMATE_FACTOR

    r, p, t = measure.residue, measure.physical, measure.terms

    def bad(x: float | None) -> bool:
        return x is None or not math.isfinite(x) or x < 0

    if not measure.complete or bad(r) or bad(p) or bad(t):
        return Judgement(INCONCLUSIVE, None, None, _uncomputed(measure), measure)
    assert r is not None and p is not None and t is not None
    if r == 0 and t == 0:
        return Judgement(VACUOUS, None, None, None, measure)
    if measure.zero_reference:
        if not t > 0:
            return Judgement(
                INCONCLUSIVE,
                None,
                None,
                "a known-zero reference without a term scale (T = 0, R > 0)",
                measure,
            )
        ratio = r / t
        return Judgement(
            PASS if ratio < tolerance_ else FAIL, TERM_RELATIVE, ratio, None, measure
        )
    if p > 0 and r / p < tolerance_:
        return Judgement(PASS, PHYSICAL, r / p, None, measure)
    passes_on_terms = t > 0 and r / t < tolerance_
    error = measure.physical_error
    flagged = p == 0 or (
        error is not None and math.isfinite(error) and p <= ESTIMATE_FACTOR * error
    )
    if passes_on_terms and flagged:
        return Judgement(
            AMBIGUOUS,
            None,
            r / t,
            "the physical reference may be noise (P "
            + (f"{p:.3g} <= {ESTIMATE_FACTOR} E_P" if p else "0 from cancelling terms")
            + "): a wider evaluation decides",
            measure,
        )
    if p == 0:
        return Judgement(FAIL, TERM_RELATIVE, r / t if t else math.inf, None, measure)
    return Judgement(FAIL, PHYSICAL, r / p, None, measure)


def settle(now: Judgement, before: Judgement | None, tolerance_: float) -> Judgement:
    """An AMBIGUOUS row at a wider carrier (``now``) against the same row at
    a narrower one (``before``): P REPRODUCES (|P_now - P_before| < K
    P_before) - the physical reference is real, and ``now`` misses it: FAIL
    on the physical scale; P COLLAPSES with the carriers' noise (P_now /
    P_before at most sqrt(u_now / u_before), the geometric midpoint between
    an unchanged P and one that falls with the unit roundoff; or P = 0 in
    both) - R < K T at the wider carrier, labelled term-relative; anything
    else, or no narrower measurement: INCONCLUSIVE (physical normalisation
    unresolved). Any other ``now`` is returned as it is."""

    if now.verdict != AMBIGUOUS:
        return now
    m = now.measure
    if (
        before is None
        or before.measure.physical is None
        or before.unit_roundoff is None
        or now.unit_roundoff is None
    ):
        return replace(
            now,
            verdict=INCONCLUSIVE,
            reason="physical normalisation unresolved: no wider evaluation at "
            "the same point to tell P from noise",
        )
    p_now, p_before = m.physical, before.measure.physical
    assert p_now is not None and m.residue is not None and m.terms is not None
    if p_before > 0 and abs(p_now - p_before) < tolerance_ * p_before:
        return replace(
            now,
            verdict=FAIL,
            scale=PHYSICAL,
            ratio=m.residue / p_now if p_now else math.inf,
            reason=f"P reproduces ({p_before:.3g} at {before.carrier}, "
            f"{p_now:.3g} at {now.carrier}): a physical miss",
        )
    collapse = math.sqrt(now.unit_roundoff / before.unit_roundoff)
    if (p_before == 0 and p_now == 0) or (
        p_before > 0 and p_now <= collapse * p_before
    ):
        ratio = m.residue / m.terms
        return replace(
            now,
            verdict=PASS if ratio < tolerance_ else FAIL,
            scale=TERM_RELATIVE,
            ratio=ratio,
            reason=f"P collapses with the carrier's noise ({p_before:.3g} at "
            f"{before.carrier}, {p_now:.3g} at {now.carrier}): term-relative "
            "tolerance",
        )
    return replace(
        now,
        verdict=INCONCLUSIVE,
        reason=f"physical normalisation unresolved: P {p_before:.3g} at "
        f"{before.carrier}, {p_now:.3g} at {now.carrier}, neither reproduced "
        "nor falling with the carrier's noise",
    )


# A row's final, decided verdicts (a decided row keeps its verdict up the
# ladder); every other verdict is pending.
_DECIDED = (PASS, VACUOUS)


def ladder_step(
    cells: dict[Any, Judgement],
    found: Mapping[Any, Measure] | None,
    carrier: str,
    unit_roundoff: float | None,
    tolerance_: float,
    keys: Sequence[Any] | None = None,
) -> list[Any]:
    """One carrier of the per-row ladder, in place on ``cells`` (row key ->
    its latest ``Judgement``): every pending row (and, on the first carrier,
    every row of ``found``; ``keys``: the required rows, every one of which
    must be measured) is judged at ``carrier`` (``judge``, then ``settle``
    against its narrower measurement); a decided row keeps its verdict; a
    pending row absent from ``found`` is INCONCLUSIVE (``found`` None: the
    carrier refused, with ``refusal`` in the reason by the caller). Returns
    the keys still pending."""

    wanted = [
        key
        for key in dict.fromkeys([*(keys or ()), *cells, *(found or {})])
        if key not in cells or cells[key].verdict not in _DECIDED
    ]
    for key in wanted:
        before = cells.get(key)
        measure = None if found is None else found.get(key)
        if measure is None:
            label = before.measure.label if before is not None else str(key)
            missing = Measure(label, None, None, None, complete=False)
            cells[key] = Judgement(
                INCONCLUSIVE,
                None,
                None,
                f"{carrier} has no such row",
                before.measure if before is not None else missing,
                carrier,
                unit_roundoff,
                before.history if before is not None else (),
            )
            continue
        now = replace(
            judge(measure, tolerance_), carrier=carrier, unit_roundoff=unit_roundoff
        )
        if now.verdict == AMBIGUOUS and before is not None:
            now = settle(now, before, tolerance_)
        if before is not None and before.carrier is not None:
            now = replace(now, history=(*before.history, _summary(before)))
        cells[key] = now
    return [key for key, cell in cells.items() if cell.verdict not in _DECIDED]


def refused_step(cells: dict[Any, Judgement], refusal: str, carrier: str) -> None:
    """A carrier refused: its pending rows keep their measurement and turn
    INCONCLUSIVE with the refusal (a later carrier may still decide them)."""

    for key, cell in list(cells.items()):
        if cell.verdict not in _DECIDED:
            cells[key] = replace(
                cell,
                verdict=INCONCLUSIVE,
                reason=f"{carrier} refused: {refusal}"
                + (f"; before: {cell.reason}" if cell.reason else ""),
            )


def finished(cells: Mapping[Any, Judgement]) -> dict[Any, Judgement]:
    """The rows' final verdicts: an AMBIGUOUS row left after the last
    carrier is INCONCLUSIVE (physical normalisation unresolved)."""

    return {
        key: (
            replace(
                cell,
                verdict=INCONCLUSIVE,
                reason="physical normalisation unresolved: no wider carrier to "
                "tell P from noise",
            )
            if cell.verdict == AMBIGUOUS
            else cell
        )
        for key, cell in cells.items()
    }


def aggregate(cells: Mapping[Any, Judgement]) -> str:
    """A check's verdict from its rows' final verdicts: FAIL if one fails,
    else INCONCLUSIVE if one is (or none was compared), else PASS if one
    passed, else VACUOUS (every row without a term)."""

    found = {cell.verdict for cell in cells.values()}
    if FAIL in found:
        return FAIL
    if found & {INCONCLUSIVE, AMBIGUOUS} or not found:
        return INCONCLUSIVE
    if PASS in found:
        return PASS
    return VACUOUS


def worst_cell(cells: Mapping[Any, Judgement]) -> Judgement | None:
    """The row that decided the aggregate: the largest ratio among the
    failing rows, else the first inconclusive one, else the largest ratio
    among the passing ones."""

    def ratio(cell: Judgement) -> float:
        return -1.0 if cell.ratio is None else cell.ratio

    for verdicts in ((FAIL,), (INCONCLUSIVE, AMBIGUOUS), (PASS,), (VACUOUS,)):
        chosen = [cell for cell in cells.values() if cell.verdict in verdicts]
        if chosen:
            return max(chosen, key=ratio)
    return None


def cell_record(cell: Judgement) -> dict[str, Any]:
    """A row's record for the reports: label, verdict, scale, R / scale, R,
    P, E_P, T, deciding carrier, reason."""

    m = cell.measure
    return {
        "label": m.label,
        "verdict": cell.verdict,
        "scale": cell.scale or (VACUOUS if cell.verdict == VACUOUS else None),
        "ratio": _short(cell.ratio),
        "residue": _short(m.residue),
        "physical": _short(m.physical),
        "physical_error": _short(m.physical_error),
        "terms": _short(m.terms),
        "carrier": cell.carrier,
        "reason": cell.reason,
    }


def carrier_digits(roundoff: float) -> float:
    """The decimal digits of a carrier of unit roundoff ``roundoff``: the
    inverse of ``assemble.Precision.arbitrary``'s 0.5 x 10^(1 - digits)
    (double-double, 2^-104: 32.0)."""

    return 1 + math.log10(0.5 / roundoff)


def rung_digits(roundoff: float) -> int:
    """The default digits of the arbitrary-precision rung after a carrier of
    unit roundoff ``roundoff``: twice its whole decimal digits (64 after
    double-double, whose 2^-104 is 32.006 digits)."""

    return 2 * math.floor(carrier_digits(roundoff))


@dataclass(frozen=True)
class Rung:
    """The arbitrary-precision rung of the auto ladder: ``lift(index,
    carrier)`` is point ``index`` lifted for ``carrier`` (the same binary64
    momenta again at the carrier's digits where the check lifted them at
    fewer); ``digits`` the option's digit count (``check.arbitrary_digits``;
    None: ``rung_digits``)."""

    lift: Callable[[int, Any], tuple[Any, Any]]
    digits: int | None = None


# ------------------------------------------------------------------ records


@dataclass(frozen=True)
class CheckRow:
    """One judged check: ``check`` ("poles", "ward" or "goldstone"),
    ``subject`` (a sector and pole coefficient, a leg and factor, or the
    finiteness of every loop order and row), the point index, the carrier
    that decided, the verdict (``VERDICTS``), ``deviation`` R over the scale
    that decided (``judge``; for a row made of several required rows, of
    the deciding one, ``worst_cell``, whose R, P, E_P, T and scale -
    "physical", "term-relative" or "vacuous" - are ``residue``,
    ``physical``, ``physical_error``, ``terms`` and ``scale_by``), every
    required row's record (``cells``), ``tolerance`` the K it was judged
    with and ``ratio`` that over K (below 1 passes), ``vacuous`` the count
    of its rows without any term (skipped);
    ``estimate`` the evaluation's error estimate E over the same S, for
    information (it decides nothing);
    ``fallback`` why the first carrier did not decide, ``reason`` why a row
    is not a verdict; ``digits`` the digit count of an arbitrary-precision
    carrier (the rung, ``_rung``)."""

    check: str
    subject: str
    point: int | None
    carrier: str | None
    verdict: str
    ratio: float | None = None
    deviation: float | None = None
    estimate: float | None = None
    fallback: str | None = None
    reason: str | None = None
    digits: int | None = None
    tolerance: float | None = None
    residue: float | None = None
    physical: float | None = None
    terms: float | None = None
    scale_by: str | None = None
    vacuous: int = 0
    physical_error: float | None = None
    # Every independently required row's record (``cell_record``): label,
    # verdict, scale, R / scale, R, P, E_P, T, deciding carrier, reason.
    cells: tuple[dict[str, Any], ...] = ()
    # The deciding rung's kinematics improvement of the lifted point (m-lit
    # lit-psimprove (G5)): the variant that produced it, "exact" or
    # "not-improved"; None where none ran (binary64 without the switch).
    kinematics: str | None = None


@dataclass(frozen=True)
class ProcessCheck:
    """The checks of one process: its rows, the slice they ran on and the
    status, a closed aggregate (``status_of``): ``FAILED`` if a row failed
    or is undecided; else ``INCONCLUSIVE_STATUS`` if a row is inconclusive
    or carries a verdict outside ``VERDICTS``; else ``NOTHING_CHECKED`` if
    no row passed or a check that applies did not run; else ``PASSED``
    (every row passed, or carries its reason as not applicable or without a
    prediction)."""

    process: str
    expression: str
    contribution: str
    widths: str
    zeroed_widths: tuple[str, ...]
    reduction: str
    rows: tuple[CheckRow, ...]
    seconds: float
    status: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", status_of(row.verdict for row in self.rows))


def status_of(verdicts: Any) -> str:
    """The closed aggregate of a process's row verdicts (``ProcessCheck``):
    FAILED, else INCONCLUSIVE (an inconclusive or an unrecognized verdict),
    else NOTHING_CHECKED (no pass and no vacuous row, or a check that did
    not run), else PASSED (a process whose every tested row is vacuous, an
    amplitude that vanishes identically, passes with that row's warning)."""

    found = set(verdicts)
    if FAIL in found or UNDECIDED in found:
        return FAILED
    if INCONCLUSIVE in found or not found <= set(VERDICTS):
        return INCONCLUSIVE_STATUS
    if not found & {PASS, VACUOUS} or NOT_RUN in found:
        return NOTHING_CHECKED
    assert found <= {PASS, *_NEUTRAL}
    return PASSED


@dataclass(frozen=True)
class CheckReport:
    """``pyamplicol check``'s result: what was checked (``source``: the run
    card or artifact whose request was regenerated in memory), the point
    count, seed and carriers, every process's checks, and the exit code
    (``EXIT_PASSED`` iff every process passed, ``EXIT_FAILED`` on any
    failure, else ``EXIT_INCONCLUSIVE`` if a process is inconclusive, else
    ``EXIT_NOTHING_CHECKED``)."""

    source: str
    source_kind: str
    points: int
    seed: int
    precision: str
    carriers: tuple[str, ...]
    processes: tuple[ProcessCheck, ...]
    regeneration: str
    seconds: float
    exit_code: int = EXIT_PASSED
    # Known, benign dependency log events of the check, returned instead of
    # printed (``ResultWarning``; m-lit ux-besteffort).
    warnings: tuple[Any, ...] = ()
    # Ctrl-C stopped the check: the tests not run are marked "not run" (the
    # exit code is not 0; the CLI exits with 130).
    interrupted: bool = False
    # The tolerance K every row was judged with (``tolerance``).
    tolerance: float | None = None

    def __post_init__(self) -> None:
        statuses = {process.status for process in self.processes}
        if FAILED in statuses:
            code = EXIT_FAILED
        elif INCONCLUSIVE_STATUS in statuses:
            code = EXIT_INCONCLUSIVE
        elif statuses == {PASSED}:
            code = EXIT_PASSED
        else:
            code = EXIT_NOTHING_CHECKED
        object.__setattr__(self, "exit_code", code)

    @property
    def passed(self) -> bool:
        return self.exit_code == EXIT_PASSED


# ------------------------------------------------- progress and Ctrl-C

# The current check's status callback (``reporting``) and process name.
_STATUS: ContextVar[Callable[[str], None] | None] = ContextVar(
    "pyamplicol_check_status", default=None
)
_PROCESS: ContextVar[str | None] = ContextVar("pyamplicol_check_process", default=None)


@contextmanager
def reporting(callback: Callable[[str], None] | None) -> Iterator[None]:
    """Report every test a check starts (``status``) to ``callback(text)``
    within the block (``api.services.check``'s progress)."""

    token = _STATUS.set(callback)
    try:
        yield
    finally:
        _STATUS.reset(token)


def status(text: str) -> None:
    """The test the check starts now (the previous one is finished),
    prefixed with the process being checked."""

    callback = _STATUS.get()
    if callback is not None:
        process = _PROCESS.get()
        callback(f"{process}: {text}" if process else text)


class CheckInterrupted(KeyboardInterrupt):
    """Ctrl-C during a check: ``partial`` holds what was checked (rows of
    one process, or the ``ProcessCheck`` list of the processes started),
    the tests not run marked as such."""

    def __init__(self, partial: Any) -> None:
        super().__init__()
        self.partial = partial


def interrupted_row() -> CheckRow:
    """The row marking the tests a Ctrl-C left unrun."""

    return CheckRow(
        "interrupted",
        "the remaining tests",
        None,
        None,
        NOT_RUN,
        reason="Ctrl-C: not run",
    )


def _point_text(index: int, points: Sequence[Any]) -> str:
    return f"point {index + 1}/{len(points)}"


# ------------------------------------------------------------- the checks


def _sector_name(sector: Any) -> str:
    return " ".join(f"{name}^{power}" for name, power in sector)


def _short(value: float | None) -> float | None:
    """``induced._short`` with an infinite ratio kept a float."""

    from .induced import _short as short

    return short(value, infinite=float("inf"))


def _carrier_name(carrier: Any) -> str:
    return str(carrier.arithmetic)


def _evaluate(executor: Any, point: Any, scale: Any, carrier: Any, checks: Any) -> Any:
    """One point's ``PointResult`` (poles "all"); a refused point raises
    ``plan_export.FailedPoints``."""

    (result,) = executor.evaluate([point], [scale], precision=carrier, stability=checks)
    return result


def _improved(
    executor: Any, point: Any, scale: Any, carrier: Any, settings: Any
) -> tuple[Any, str | None]:
    """The lifted point a rung in ``carrier`` evaluates (m-lit lit-psimprove
    (G5)): improved in that carrier under the user's ``settings``
    (``kinematics.KinematicsSettings``, which ``check_request`` resolves from
    the run card / CLI, the policy's defaults included; None: an internal
    caller, no improvement) as
    ``Runtime.evaluate`` improves a user's point, toward the masses the
    executor binds; the lifted point is exact to twice the last carrier's
    digits, so this moves it by the rung's rounding at most. Also the
    record's short form (the variant that produced the point, "exact",
    "not-improved"; None: no improvement in this carrier)."""

    from pyamplicol import kinematics

    if settings is None:
        return point, None
    name = _carrier_name(carrier)
    variant = settings.variant(name)
    if variant is None:
        return point, None
    masses = executor.leg_masses(point, scale, None, carrier, 1)
    initial = kinematics.initial_count(executor.slice.blocks.process.legs)
    digits = carrier.working_digits if name == "arbitrary" else None
    (improved,), (record,) = kinematics.improve(
        [point], initial, masses, name, digits, variant
    )
    return improved, record["produced"] or record["status"]


def _largest_part(
    components: Mapping[str, Mapping[Any, Any]], sector: Any, k: int
) -> float | None:
    """T of a Born-interfered row: the largest magnitude of coefficient k of
    ``sector`` over the virtual and its parts (bare, R2, UV; ``assemble.
    COMPONENTS``), 0 where none has it (no contributing term), None where
    one cannot be computed (``magnitude``)."""

    found = 0.0
    for part in components.values():
        laurent = part.get(sector)
        if laurent is None or len(laurent.coefficients) <= k:
            continue
        size = magnitude(laurent.coefficients[k])
        if size is None:
            return None
        found = max(found, size)
    return found


def _real_size(value: Any) -> float | None:
    """|Re value| as a finite binary64 number, else None."""

    try:
        found = abs(complex(value).real)
    except (ArithmeticError, TypeError, ValueError):
        return None
    return found if math.isfinite(found) else None


def _pole_measures(result: Any) -> dict[Any, Measure]:
    """The pole rows of one evaluated point, keyed by (sector, k): R = |Re
    V_k - Re C_k|, P = max(|Re C_k|, |Re V_k|) (Catani's prediction is an
    analytic reference: a C_k that is exactly zero is a known-zero reference,
    judged term-relative), T = the largest part (``_largest_part``), E the
    evaluation's estimate where it ran its checks."""

    estimate = result.stability
    found: dict[Any, Measure] = {}
    for sector, laurent in result.components["virtual"].items():
        poles = (result.ir_poles or {}).get(sector)
        if poles is None or len(laurent.coefficients) != 3:
            continue
        for k in (1, 2):
            sizes = (_real_size(poles[k - 1]), _real_size(laurent.coefficients[k]))
            error = None
            if estimate is not None:
                error = magnitude(estimate.absolute[sector].coefficients[k])
            try:
                known_zero = complex(poles[k - 1]).real == 0
            except (ArithmeticError, TypeError, ValueError):
                known_zero = False
            found[(sector, k)] = Measure(
                f"{_sector_name(sector)} {POLE_NAMES[k]}",
                real_gap(laurent.coefficients[k], poles[k - 1]),
                None if None in sizes else max(sizes),
                _largest_part(result.components, sector, k),
                error,
                zero_reference=known_zero,
            )
    return found


def _uncomputed(measure: Measure) -> str:
    """Why ``judge`` found a row inconclusive."""

    def bad(x: float | None) -> bool:
        return x is None or not math.isfinite(x) or x < 0

    if not measure.complete:
        return "a required operand is missing (the row is incomplete)"
    if bad(measure.residue):
        return "the residue R cannot be computed (not a finite number)"
    if bad(measure.physical):
        return "the physical reference P cannot be computed (not a finite number)"
    if bad(measure.terms):
        return "the term scale T cannot be computed (not a finite number)"
    return "R, P and T are finite but give no scale"


def _unpredicted_rows(
    slice_: Any,
    sectors: Sequence[Any],
    formed: bool,
    index: int,
    judged: Sequence[Any] = (),
) -> list[CheckRow]:
    """A row per sector without a pole row, with its reason, never omitted:
    "no prediction" for the sectors the operators do not predict
    (``poles.UNPREDICTED_REASONS``) or where no prediction could be formed,
    "not run" for a sector they predict that got no pole row at this point
    (``judged``): an applicable check that did not run (exit code 3)."""

    unpredicted = slice_.unpredicted_sectors()
    rows = []
    for sector in sectors:
        verdict = NO_PREDICTION
        if sector in unpredicted:
            reason = (
                f"{unpredicted[sector]}: the requested corrections' operators do "
                "not predict this sector's poles (poles.sector_predictions)"
            )
        elif not formed:
            reason = (
                "no prediction formed: Catani's native operator needs a "
                "full-colour request with two coloured legs (dipoles.correlator)"
            )
        elif sector not in judged:
            verdict = NOT_RUN
            reason = (
                "an applicable check did not run: the operators predict this "
                "sector's poles, but no prediction or pole coefficients were "
                "formed for it at this point"
            )
        else:
            continue
        rows.append(
            CheckRow("poles", _sector_name(sector), index, None, verdict, reason=reason)
        )
    return rows


def ward_applicability(target: Any) -> str | None:
    """None where the Ward rows of a probe slice are checked, else why they
    are not applicable (USER 2026-11-10 ~00:17: with EW corrections and an
    on-shell zero-width external top "it may break some EW gauge relations
    ... ignore ward check there"). One rule on the request's own data,
    decided before any Ward evaluation: its corrections include one other
    than the model's strong correction (``ew_policy.correction_orders``,
    identified by the gluon's vertices, never by an order's name) AND an
    external leg is a massive quark with zero width at the check's
    parameters: a fermion (``ew_policy.FERMION_SPIN``) of colour triplet or
    anti-triplet (|colour| = 3; an antiquark's record carries -3) whose mass
    parameter is not zero and whose width parameter is (``ew_policy.
    is_zero`` on the probe request's fixed parameters: outside the
    complex-mass scheme the probe zeroes every width, ``ew_policy.
    probe_widths``). Every external leg is on shell at a check point
    (``induced.probe_point``). Ward rows are not split by squared-order
    sector, so a pure-QCD-loop sector of such a request is not checked
    either."""

    from .ew_policy import FERMION_SPIN, correction_orders, is_zero, request_corrections

    compiled, request = target.compiled, target.request
    fixed = request.fixed_parameters
    strong = correction_orders(compiled, fixed).strong
    others = sorted(set(request_corrections(compiled, request)) - {strong})
    if not others:
        return None
    particles = {int(record.pdg_code): record for record in compiled.ir.particles}
    parameters = {record.name: record for record in compiled.ir.parameters}
    quarks = [
        int(leg.label)
        for leg in sorted(target.blocks.process.legs, key=lambda x: x.label)
        if (record := particles.get(int(leg.pdg))) is not None
        and int(record.spin) == FERMION_SPIN
        and abs(int(record.color)) == 3
        and not is_zero(str(record.mass), parameters, fixed)
        and is_zero(str(record.width), parameters, fixed)
    ]
    if not quarks:
        return None
    return (
        f"EW corrections ({', '.join(others)}) with an on-shell zero-width "
        f"external massive quark ({_legs(quarks)}): the "
        "gluon / photon Ward identity of the asymmetric check is not "
        "guaranteed there (USER 2026-11-10); not evaluated, every "
        "squared-order sector alike"
    )


def _not_applicable_ward(legs: Sequence[int], reason: str) -> CheckRow:
    """The one Ward row of a process whose Ward rows are not applicable
    (``ward_applicability``), naming the legs not checked."""

    return CheckRow(
        "ward",
        "external gluons and photons",
        None,
        None,
        NOT_APPLICABLE,
        reason=f"{_legs(legs)} not checked: {reason}",
    )


def _legs(labels: Sequence[int]) -> str:
    return ("leg " if len(labels) == 1 else "legs ") + ", ".join(map(str, labels))


def _stages(carriers: Sequence[Any], rung: Rung | None) -> list[Any]:
    """The carriers of a Born-interfered row's ladder: ``carriers``, then the
    arbitrary-precision rung (``rung``: its digits, else ``rung_digits``
    after the last carrier)."""

    from .assemble import Precision

    stages = list(carriers)
    if rung is not None and carriers:
        digits = (
            rung.digits
            if rung.digits is not None
            else rung_digits(carriers[-1].unit_roundoff)
        )
        stages.append(Precision.arbitrary(digits))
    return stages


def born_interfered_rows(
    target: Any,
    points: Sequence[tuple[Any, Any]],
    carriers: Sequence[Any],
    rung: Rung | None = None,
    kinematics: Any = None,
    out: list[CheckRow] | None = None,
) -> list[CheckRow]:
    """The pole and Ward rows of a Born-interfered probe slice (module
    docstring) at the lifted ``points`` ((point, mu_R^2) pairs), per row up
    the ladder of ``carriers`` and, for a row the last one does not decide,
    the arbitrary-precision ``rung`` (None: none, an explicit carrier),
    judged with the check's ``tolerance`` (``ladder_step``: each row keeps
    its first decision; a carrier's refusal leaves the next one to try)."""

    from . import induced, stability, ward
    from .plan_export import FailedPoints, NativeExecutor

    executor = NativeExecutor(target, inputs="native", forward=False, catani=True)
    tolerance_ = tolerance()
    legs = ward.gauge_legs(target)
    excluded = ward_applicability(target) if legs else None
    stages = _stages(carriers, rung)
    # ``out``: the caller's list, which keeps the rows of an interrupted
    # check.
    rows: list[CheckRow] = [] if out is None else out
    for index, (point, scale) in enumerate(points):

        def at(
            carrier: Any, index: int = index, point: Any = point, scale: Any = scale
        ):
            """The point ``carrier`` evaluates and its kinematics record:
            the lifted point (again at the rung's digits for an
            arbitrary-precision carrier), improved in that carrier."""

            lifted, mu = (
                rung.lift(index, carrier)
                if rung is not None and _carrier_name(carrier) == "arbitrary"
                else (point, scale)
            )
            moved, improved = _improved(executor, lifted, mu, carrier, kinematics)
            return moved, mu, improved

        # Poles against Catani's operator, per (sector, k) up the ladder.
        cells: dict[Any, Judgement] = {}
        sectors: list[Any] = []
        formed = evaluated = False
        refusals: list[str] = []
        improvements: dict[str, Any] = {}
        for carrier in stages:
            name = _carrier_name(carrier)
            if evaluated and all(cell.verdict in _DECIDED for cell in cells.values()):
                break
            status(
                f"{_point_text(index, points)}: poles against Catani's operator "
                f"({name})"
            )
            moved, mu, improved = at(carrier)
            improvements[name] = improved
            try:
                result = _evaluate(
                    executor,
                    moved,
                    mu,
                    carrier,
                    stability.RECOMMENDED_CHECKS if name == "double" else None,
                )
            except FailedPoints as error:
                refusals.append(f"{name} refused: {error}")
                refused_step(cells, str(error), name)
                continue
            if not evaluated:
                sectors = list(result.components["virtual"])
                formed = result.ir_poles is not None
            ladder_step(
                cells,
                _pole_measures(result),
                name,
                getattr(carrier, "unit_roundoff", None),
                tolerance_,
            )
            evaluated = True
        if not evaluated:
            rows.append(
                CheckRow(
                    "poles",
                    "every sector",
                    index,
                    None,
                    INCONCLUSIVE,
                    reason="inconclusive: " + "; ".join(refusals),
                    tolerance=tolerance_,
                )
            )
        for key, cell in finished(cells).items():
            rows.append(
                row_from_cells(
                    "poles",
                    cell.measure.label,
                    index,
                    {key: cell},
                    tolerance_,
                    improvements,
                    stages,
                )
            )
        rows.extend(
            _unpredicted_rows(target, sectors, formed, index, {key[0] for key in cells})
        )
        # Ward identities on every gluon and photon leg.
        if legs and excluded is None:
            status(f"{_point_text(index, points)}: Ward identities, {_legs(legs)}")
            rows.extend(_born_ward_rows(executor, index, stages, at, legs, tolerance_))
    if excluded is not None:
        rows.append(_not_applicable_ward(legs, excluded))
    if not legs:
        rows.append(
            CheckRow(
                "ward",
                "external gluons and photons",
                None,
                None,
                NOT_APPLICABLE,
                reason="the process has no external gluon or photon",
            )
        )
    reason = induced.goldstone_applicability(target) or (
        "the Goldstone-equivalence probe is amplitude-level (loop-induced "
        "requests); a Born-interfered virtual has none"
    )
    rows.append(
        CheckRow(
            "goldstone",
            "external massive vectors",
            None,
            None,
            NOT_APPLICABLE,
            reason=reason,
        )
    )
    return rows


def _with(row: CheckRow, **changes: Any) -> CheckRow:
    return replace(row, **changes)


def row_from_cells(
    check: str,
    subject: str,
    index: int | None,
    cells: Mapping[Any, Judgement],
    tolerance_: float,
    improvements: Mapping[str, Any] | None = None,
    stages: Sequence[Any] = (),
) -> CheckRow:
    """A check row from its independently required rows' final verdicts
    (``aggregate``): the deciding row (``worst_cell``) gives the carrier, R
    over its scale, R, P, E_P, T, the scale that decided and the earlier
    carriers' outcomes (``fallback``); every row's record is kept
    (``cells``, ``cell_record``); an inconclusive row names its reason, a
    vacuous one is counted."""

    verdict = aggregate(cells)
    worst = worst_cell(cells)
    vacuous = sum(1 for cell in cells.values() if cell.verdict == VACUOUS)
    reason = None
    if verdict == INCONCLUSIVE:
        open_ = [
            f"{cell.measure.label}: {cell.reason}"
            for cell in cells.values()
            if cell.verdict in (INCONCLUSIVE, AMBIGUOUS)
        ]
        more = f" (and {len(open_) - 3} more)" if len(open_) > 3 else ""
        reason = "inconclusive: " + ("; ".join(open_[:3]) or "nothing compared") + more
    elif verdict == VACUOUS:
        reason = (
            "nothing to test: the quantity vanishes identically (every row "
            "vacuous: no term)"
        )
    elif vacuous:
        reason = f"{vacuous} vacuous row(s) (no term) skipped"
    if worst is None:
        return CheckRow(
            check,
            subject,
            index,
            None,
            verdict,
            reason=reason,
            tolerance=tolerance_,
            vacuous=vacuous,
        )
    m = worst.measure
    scale = (
        m.physical
        if worst.scale == PHYSICAL
        else m.terms
        if worst.scale == TERM_RELATIVE
        else None
    )
    digits = next(
        (
            carrier.digits
            for carrier in stages
            if _carrier_name(carrier) == "arbitrary" and worst.carrier == "arbitrary"
        ),
        None,
    )
    return CheckRow(
        check,
        subject,
        index,
        worst.carrier,
        verdict,
        _short(None if worst.ratio is None else worst.ratio / tolerance_),
        _short(worst.ratio),
        _short(over(m.estimate, scale)),
        fallback="; ".join(worst.history) or None,
        reason=reason if verdict != PASS or vacuous else None,
        digits=digits,
        tolerance=tolerance_,
        residue=_short(m.residue),
        physical=_short(m.physical),
        terms=_short(m.terms),
        scale_by=worst.scale or (VACUOUS if worst.verdict == VACUOUS else None),
        vacuous=vacuous,
        physical_error=_short(m.physical_error),
        cells=tuple(cell_record(cell) for cell in cells.values()),
        kinematics=(improvements or {}).get(worst.carrier or ""),
    )


def _ward_measures(physical: Any, result: Any) -> dict[Any, Measure]:
    """The required rows of one Ward evaluation (module docstring), keyed by
    label: per Born sector R = |loop-side Born|, P = T = |physical Born| (a
    tree is its own term); per virtual sector and Laurent coefficient R =
    |V_k| of the substituted evaluation, P = |V_k| of the physical one (E_P:
    its estimate where the physical evaluation ran its checks), T = the
    physical evaluation's largest part (``_largest_part``), E the
    substituted evaluation's estimate. Every sector and coefficient of
    either evaluation is required: one only one of them has is a missing
    operand (incomplete: inconclusive), never skipped or vacuous."""

    out: dict[Any, Measure] = {}
    loop_born = result.loop_born
    born = physical.born or {}
    if loop_born is None:
        out["Born"] = Measure("Born", None, None, None, complete=False)
    else:
        for sector in dict.fromkeys([*born, *loop_born]):
            size = magnitude(born[sector]) if sector in born else None
            label = f"Born {_sector_name(sector)}"
            out[label] = Measure(
                label,
                magnitude(loop_born[sector]) if sector in loop_born else None,
                size,
                size,
                complete=sector in born and sector in loop_born,
            )
    virtual = result.components["virtual"]
    reference = physical.components["virtual"]
    estimate = result.stability
    physical_estimate = physical.stability
    widths = [len(laurent.coefficients) for laurent in reference.values()]
    width = max(widths, default=0)
    for sector in dict.fromkeys([*reference, *virtual]):
        laurent = virtual.get(sector)
        mine = reference.get(sector)
        for k in range(width):
            label = f"{_sector_name(sector)} {COEFFICIENT_NAMES[k]}"
            present = (
                laurent is not None
                and mine is not None
                and len(laurent.coefficients) > k
                and len(mine.coefficients) > k
            )
            if not present:
                out[label] = Measure(label, None, None, None, complete=False)
                continue
            error = physical_error = None
            if estimate is not None and sector in estimate.absolute:
                error = magnitude(estimate.absolute[sector].coefficients[k])
            if physical_estimate is not None and sector in physical_estimate.absolute:
                physical_error = magnitude(
                    physical_estimate.absolute[sector].coefficients[k]
                )
            out[label] = Measure(
                label,
                magnitude(laurent.coefficients[k]),
                magnitude(mine.coefficients[k]),
                _largest_part(physical.components, sector, k),
                error,
                physical_error,
            )
    return out


COEFFICIENT_NAMES = ("finite", "1/eps", "1/eps^2")


def _ward_subject(leg: int, factor: Any) -> str:
    return f"leg {leg}, " + ("c = 1" if tuple(factor) == (1, 0) else "c = i")


def _ward_batches(keys: Sequence[Any], legs: Sequence[int]) -> list[Any]:
    """The ``ward.ward_check`` batches of (leg, factor) rows ``keys``: one for
    every row when they are every leg's factors (the physical evaluation
    shared), else one per leg."""

    from . import ward

    if len(keys) == len(legs) * len(ward.WARD_FACTORS):
        return [(list(legs), list(ward.WARD_FACTORS))]
    return [
        ([leg], [f for other, f in keys if other == leg])
        for leg in sorted({leg for leg, _ in keys})
    ]


def _ward_found(
    executor: Any,
    point: Any,
    scale: Any,
    keys: Sequence[Any],
    legs: Sequence[int],
    carrier: Any,
) -> dict[Any, dict[Any, Measure]]:
    """The Ward rows ``keys`` ((leg, factor)) of one point evaluated in
    ``carrier`` (``ward.ward_check``: the physical evaluation runs its
    reduction-direction check in binary64), per (leg, factor) its required
    rows (``_ward_measures``); a refused run raises ``FailedPoints``."""

    from . import ward

    name = _carrier_name(carrier)
    found: dict[Any, dict[Any, Measure]] = {}
    for batch_legs, factors in _ward_batches(keys, legs):
        check = ward.ward_check(
            executor,
            point,
            scale,
            "double" if name == "double" else "double-double",
            legs=batch_legs,
            factors=factors,
            precision=carrier,
            judge=False,
        )
        for row, result in zip(check["rows"], check["results"], strict=True):
            key = (row["leg"], tuple(row["factor"]))
            found[key] = _ward_measures(check["physical"], result)
    return found


def _born_ward_rows(
    executor: Any,
    index: int,
    stages: Sequence[Any],
    at: Callable[[Any], tuple[Any, Any, Any]],
    legs: Sequence[int],
    tolerance_: float,
) -> list[CheckRow]:
    """The Ward rows of one point, per (leg, factor) and per required row
    (Born sector, virtual sector and coefficient) up the ladder of
    ``stages`` (``ladder_step``): each row keeps its first decision, a
    pending row absent from a later carrier is inconclusive, a refusal
    leaves the next carrier to try; one check row per (leg, factor) from
    its rows' final verdicts (``row_from_cells``)."""

    from . import ward
    from .plan_export import FailedPoints

    every = [(leg, factor) for leg in legs for factor in ward.WARD_FACTORS]
    cells: dict[Any, dict[Any, Judgement]] = {key: {} for key in every}
    seen: set[Any] = set()
    refusals: dict[Any, list[str]] = {key: [] for key in every}
    improvements: dict[str, Any] = {}
    for carrier in stages:
        name = _carrier_name(carrier)
        pending = [
            key
            for key in every
            if key not in seen
            or any(cell.verdict not in _DECIDED for cell in cells[key].values())
        ]
        if not pending:
            break
        moved, mu, improved = at(carrier)
        improvements[name] = improved
        try:
            found = _ward_found(executor, moved, mu, pending, legs, carrier)
        except FailedPoints as error:
            for key in pending:
                refusals[key].append(f"{name} refused: {error}")
                refused_step(cells[key], str(error), name)
            continue
        for key in pending:
            if key in found:
                seen.add(key)
            ladder_step(
                cells[key],
                found.get(key),
                name,
                getattr(carrier, "unit_roundoff", None),
                tolerance_,
            )
    rows = []
    for key in every:
        if key not in seen:
            rows.append(
                CheckRow(
                    "ward",
                    _ward_subject(*key),
                    index,
                    None,
                    INCONCLUSIVE,
                    reason="inconclusive: " + "; ".join(refusals[key]),
                    tolerance=tolerance_,
                )
            )
            continue
        rows.append(
            row_from_cells(
                "ward",
                _ward_subject(*key),
                index,
                finished(cells[key]),
                tolerance_,
                improvements,
                stages,
            )
        )
    return rows


def induced_rows(
    target: Any,
    compiled: Any,
    request: Any,
    native: Any,
    points: Sequence[tuple[Any, Any]],
    carriers: Sequence[Any],
    *,
    memo: Any = None,
    kinematics: Any = None,
    out: list[CheckRow] | None = None,
) -> list[CheckRow]:
    """The finiteness, Ward and Goldstone rows of a loop-induced probe slice
    (``induced.point_probes``, ``induced.goldstone_point``) at the lifted
    ``points``; ``memo`` shares the Goldstone sides' model preparation."""

    from . import induced
    from .plan_export import NativeExecutor

    if target.amplitude.colour_zero:
        zero = [
            CheckRow(
                check,
                "every loop order",
                None,
                None,
                NOT_APPLICABLE,
                reason="an exact colour zero: nothing to probe",
            )
            for check in ("poles", "ward", "goldstone")
        ]
        if out is None:
            return zero
        out.extend(zero)
        return out
    legs = induced.probe_legs(target)
    excluded = ward_applicability(target) if legs else None
    probed = legs if excluded is None else []
    executor = NativeExecutor(
        target,
        forward=False,
        inputs="native",
        lanes=induced.probe_lanes(1 + len(probed)),
    )
    applicability = induced.goldstone_applicability(target)
    sides: Mapping[int, Any] = {}
    skipped: Mapping[str, str] = {}
    if applicability is None:
        sides, skipped, _seconds = induced.goldstone_sides(
            target, compiled, request, native, memo=memo
        )
    executors: dict[Any, Any] = {}
    rows: list[CheckRow] = [] if out is None else out
    for index, (point, scale) in enumerate(points):
        status(
            f"{_point_text(index, points)}: finiteness"
            + (f" and Ward probes, {_legs(probed)}" if probed else "")
        )
        try:
            floors, _record = induced.probe_floors(executor, point, scale)
        except induced.ProbePointRefused as error:
            rows.append(
                CheckRow(
                    "poles",
                    "finiteness",
                    index,
                    None,
                    INCONCLUSIVE,
                    reason="inconclusive: the point's physical floors (S) were "
                    f"refused: {error}",
                    tolerance=tolerance(),
                )
            )
            continue
        entries, decided = induced.point_probes(
            executor,
            point,
            scale,
            probed,
            carriers,
            floors,
            improve=lambda point, scale, carrier: _improved(
                executor, point, scale, carrier, kinematics
            ),
            tolerance=tolerance(),
        )
        for entry, result in zip(entries, decided, strict=True):
            rows.append(_probe_row(entry, result, index))
        if sides:
            status(f"{_point_text(index, points)}: Goldstone-equivalence probes")
            results, gentries, _phases, _times = induced.goldstone_point(
                target, sides, point, scale, carriers, floors, executors, tolerance()
            )
            for entry, (_leg, result) in zip(gentries, results, strict=True):
                rows.append(_probe_row(entry, result, index))
    if not legs:
        rows.append(
            CheckRow(
                "ward",
                "external gluons and photons",
                None,
                None,
                NOT_APPLICABLE,
                reason="the process has no external gluon or photon",
            )
        )
    if excluded is not None:
        rows.append(_not_applicable_ward(legs, excluded))
    if applicability is not None:
        rows.append(
            CheckRow(
                "goldstone",
                "external massive vectors",
                None,
                None,
                NOT_APPLICABLE,
                reason=applicability,
            )
        )
    for leg, text in skipped.items():
        rows.append(
            CheckRow("goldstone", f"leg {leg}", None, None, NOT_RUN, reason=text)
        )
    return rows


def _probe_row(entry: Mapping[str, Any], result: Any, index: int) -> CheckRow:
    """A generation-time probe's decided result as a check row, from its
    required rows' final verdicts (``row_from_cells``)."""

    probe = entry["probe"]
    check = {"finiteness": "poles", "ward": "ward", "goldstone": "goldstone"}[probe]
    subject = (
        "finiteness (every loop order and row)"
        if probe == "finiteness"
        else f"leg {entry['leg']}"
    )
    fallback = entry.get("fallback")
    if isinstance(fallback, list):
        fallback = fallback[-1]
    fallback_text = None
    if fallback is not None:
        fallback_text = (
            f"{fallback['carrier']} refused: {fallback['detail']}"
            if fallback["reason"] == "refused"
            else f"{fallback['carrier']}: {fallback['verdict']}, largest R / S "
            f"{fallback['worst']}"
        )
    improved = entry.get("kinematics", {}).get(entry["carrier"])
    if isinstance(result, str):
        return CheckRow(
            check,
            subject,
            index,
            entry["carrier"],
            INCONCLUSIVE,
            fallback=fallback_text,
            reason=f"inconclusive: refused: {result}",
            kinematics=improved,
            tolerance=tolerance(),
        )
    row = row_from_cells(
        check,
        subject,
        index,
        result.final,
        result.tolerance,
        entry.get("kinematics", {}),
    )
    return _with(row, fallback=row.fallback or fallback_text)


def check_request(
    process: str,
    expression: str,
    compiled: Any,
    request: Any,
    native: Any,
    momenta: Sequence[Sequence[Sequence[float]]],
    carriers: Sequence[Any],
    *,
    memo: Any = None,
    kinematics: Any = None,
    arbitrary: bool = False,
    digits: int | None = None,
) -> ProcessCheck:
    """The checks of one generation request (``SliceRequest``) at the
    binary64 phase-space points ``momenta`` (module docstring): its probe
    slice is generated in memory, the points lifted once at the digits of
    the last carrier (again at an arbitrary-precision carrier's, where
    more). ``arbitrary``: the auto ladder's arbitrary-precision rung after
    ``carriers`` (``Rung``), at ``digits`` digits (None: derived per row);
    ``memo`` (the check's ``preparation_cache.PreparationMemo``) shares the
    model preparation of the probe and Goldstone slices, as at
    generation."""

    from .induced import (
        PROBE_REDUCTION,
        _complex_mass,
        probe_request_of,
    )
    from .reduction import running
    from .ward import ward_slice

    start = time.perf_counter()
    token = _PROCESS.set(process)
    rows: list[CheckRow] = []
    zeroed: Any = ()
    target: Any = None
    try:
        with running(PROBE_REDUCTION):
            status("regenerating the probe slice in memory")
            probe, zeroed = probe_request_of(compiled, request)
            target = ward_slice(compiled, probe, native, memo=memo)
            status(f"lifting {len(momenta)} point(s) to exact conservation")
            _check_points(
                compiled,
                request,
                native,
                momenta,
                carriers,
                memo,
                kinematics,
                arbitrary,
                digits,
                probe,
                target,
                rows,
            )
    except KeyboardInterrupt as error:
        if isinstance(error, CheckInterrupted):
            raise
        raise CheckInterrupted(
            ProcessCheck(
                process,
                expression,
                request.contribution,
                "-"
                if target is None
                else "complex-mass"
                if not zeroed and _complex_mass(target)
                else "zero",
                tuple(zeroed),
                PROBE_REDUCTION,
                (*rows, interrupted_row()),
                round(time.perf_counter() - start, 3),
            )
        ) from None
    finally:
        _PROCESS.reset(token)
    return ProcessCheck(
        process,
        expression,
        request.contribution,
        "complex-mass" if not zeroed and _complex_mass(target) else "zero",
        tuple(zeroed),
        PROBE_REDUCTION,
        tuple(rows),
        round(time.perf_counter() - start, 3),
    )


def _check_points(
    compiled: Any,
    request: Any,
    native: Any,
    momenta: Sequence[Sequence[Sequence[float]]],
    carriers: Sequence[Any],
    memo: Any,
    kinematics: Any,
    arbitrary: bool,
    digits: int | None,
    probe: Any,
    target: Any,
    rows: list[CheckRow],
) -> None:
    """``check_request``'s rows of the probe slice ``target`` at
    ``momenta``, appended to ``rows`` as they are judged."""

    from .induced import _point_scale, probe_point

    lifted = 2 * max(carrier.working_digits for carrier in carriers)
    initial = sum(1 for leg in target.blocks.process.legs if leg.is_initial)
    points = []
    for momentum in momenta:
        point, _distance = probe_point(target, momentum, lifted)
        points.append((point, _point_scale(point, initial)))
    relifted: dict[tuple[int, int], tuple[Any, Any]] = {}

    def lift(index: int, carrier: Any) -> tuple[Any, Any]:
        needed = 2 * carrier.working_digits
        if needed <= lifted:
            return points[index]
        if (index, needed) not in relifted:
            point, _distance = probe_point(target, momenta[index], needed)
            relifted[(index, needed)] = (point, _point_scale(point, initial))
        return relifted[(index, needed)]

    rung = Rung(lift, digits) if arbitrary else None
    if request.contribution == "loop-induced":
        induced_rows(
            target,
            compiled,
            probe,
            native,
            points,
            carriers,
            memo=memo,
            kinematics=kinematics,
            out=rows,
        )
    else:
        born_interfered_rows(target, points, carriers, rung, kinematics, out=rows)


__all__ = [
    "CATANI_DD_FLOOR",
    "CATANI_FLOOR",
    "ESTIMATES",
    "EXIT_FAILED",
    "EXIT_INCONCLUSIVE",
    "EXIT_NOTHING_CHECKED",
    "EXIT_PASSED",
    "FAIL",
    "FAILED",
    "INCONCLUSIVE",
    "INCONCLUSIVE_STATUS",
    "NOTHING_CHECKED",
    "NOT_APPLICABLE",
    "NOT_RUN",
    "NO_PREDICTION",
    "PASS",
    "PASSED",
    "RULE",
    "UNDECIDED",
    "VACUOUS",
    "VERDICTS",
    "CheckInterrupted",
    "CheckReport",
    "CheckRow",
    "Measure",
    "ProcessCheck",
    "Rung",
    "born_interfered_rows",
    "carrier_digits",
    "catani_comparison",
    "catani_dd_comparison",
    "check_request",
    "induced_rows",
    "interrupted_row",
    "judge",
    "ladder_step",
    "reporting",
    "rung_digits",
    "settle",
    "status",
    "status_of",
    "threshold",
    "tolerance",
    "tolerating",
    "ward_applicability",
]
