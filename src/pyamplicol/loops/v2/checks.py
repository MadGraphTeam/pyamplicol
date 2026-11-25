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
the requested number of stable digits"; ``judge``): every independently
required row (a point, a sector or loop order and helicity row, a leg and
factor, a Laurent coefficient) is judged on its own, before any
aggregation: PASS iff R < K S, FAIL iff R >= K S (equality is a miss),
INCONCLUSIVE iff R or S cannot be computed (not a finite number, a missing
operand, a refused run, S not positive), with

    S = max(P, K T):

R the row's residue, P its PHYSICAL reference (the size of the physical
quantities whose difference or vanishing the identity tests, at the same
point and row or sector) and T its term scale (the size of the terms that
cancel into it). K T only guards a row whose physical reference is below
what the computation resolves: there the test is R < K^2 T. A row with no
term at all (R = 0 exactly and T = 0: a coefficient neither the prediction
nor any part has, a helicity row that vanishes structurally) is VACUOUS:
skipped and counted, neither a pass nor an inconclusive; a check all of
whose rows are vacuous has nothing to test (the amplitude vanishes
identically) and passes with that warning. R, P and T are linear in the
amplitude (colour-metric norms, or the interference itself), so K is a
relative accuracy of the checked quantity. K is the check's tolerance
(``tolerance``: ``check.tolerance``, else the run's requested relative
accuracy ``evaluation.reduction_target``, whose default is the native
policy's target ``reduction.default_target()``). The comparisons are
ordinary carrier arithmetic: this is a tolerance, not a certificate. Each
row reports R / S, R, P, T and which of P and K T set S; the evaluation's
error estimate E over S is reported for information and decides nothing.

* **Poles, Born-interfered** (``born_interfered_rows``, ``_pole_rows``): per
  point, squared-order sector and pole coefficient k of the renormalised
  virtual V (poles "all") against Catani's prediction C of the requested
  corrections (QCD and QED summed per sector, formed natively,
  ``NativeExecutor(catani=True)``): R = |Re V_k - Re C_k|, P = max(|Re C_k|,
  |Re V_k|), T = the largest part (bare, R2, UV) of that sector and
  coefficient. A sector the operators do not predict is listed with its
  reason (``poles.UNPREDICTED_REASONS``), never as a pass; a sector they
  predict without a pole row at a point is "not run" (an applicable check
  that did not run).
* **Ward, Born-interfered** (``_ward_measures``): ``ward.ward_check`` on
  every external gluon and photon leg (``ward.gauge_legs``) and both
  factors (``ward.WARD_FACTORS``): per Born sector R = |loop-side Born|, P =
  T = |physical Born|; per virtual sector and coefficient R = |V_k| of the
  substituted evaluation, P = |V_k| of the physical evaluation at the same
  point, T = its largest part.
* **Loop-induced** (``induced.point_probes``): the finiteness probe (R =
  the colour-metric norm of each pole coefficient of each loop order and
  helicity row) and the amplitude-level Ward probe of one leg of every
  gluon and photon species (R = the substituted amplitude's norm at every
  coefficient): P = the norm of the physical finite amplitude of that row
  (``induced.RowFloors.finite``; for a Ward row the largest over the
  substituted leg's helicities), T = the row's term floor S_k(h)
  (``induced.row_scales``, ``induced.ward_floors``).
* **Goldstone** (``induced.goldstone_point``): k.A(V) = eta M_V A(G) where
  the probe serves the slice (``induced.goldstone_applicability``:
  't Hooft-Feynman gauge, an external massive vector with a Goldstone
  partner, a loop-induced amplitude); R = ||A(V)_k - eta (M/E) A(G)_k||,
  P = max(||A(V)_k||, ||eta (M/E) A(G)_k||), T = the vector row's floor
  plus M/E times the Goldstone row's (``goldstone.probe``); otherwise a
  "not applicable" row with the reason.
* **Ward rows not applicable** (``ward_applicability``, USER 2026-11-10
  ~00:17): a request whose corrections include one other than the model's
  strong correction and with an on-shell zero-width external massive quark
  has one "not applicable" Ward row (the Ward identity of the asymmetric
  check is not guaranteed there), nothing evaluated; Ward rows are not split
  by squared-order sector, so its QCD-loop sectors are not checked either.

Carriers (``induced.probe_carriers``): binary64 first and double-double
only for a row binary64 does not pass (a failure, an inconclusive row or a
refused run); an explicit carrier alone otherwise. The verdict is the one of
the first carrier that passes the row, else of the last carrier that judged
it; a later carrier's refusal leaves the row inconclusive (never a pass).
The deciding carrier and the fallback's reason are recorded per row.

**The arbitrary-precision rung** (``auto`` only, Born-interfered rows): a
row the ladder's last carrier does not pass is evaluated again in arbitrary
precision at ``check.arbitrary_digits`` digits, by default twice the last
carrier's decimal digits (``rung_digits``), the point lifted again at those
digits; its verdict there is the row's. The loop-induced probes keep their
ladder (binary64, double-double).
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
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
    it cannot be computed) and the evaluation's error estimate E (reported
    only)."""

    label: str
    residue: float | None
    physical: float | None
    terms: float | None
    estimate: float | None = None


def scale_of(
    physical: float | None, terms: float | None, tolerance_: float
) -> tuple[float | None, str | None]:
    """S = max(P, K T) and which of them set it ("P" or "K T"); None where P
    or T cannot be computed. K T only guards a row whose physical reference
    is below what the computation resolves: there the test is R < K^2 T."""

    if physical is None or terms is None:
        return None, None
    guard = tolerance_ * terms
    return (physical, "P") if physical >= guard else (guard, "K T")


def judge(measure: Measure, tolerance_: float) -> str:
    """THE RULE for one required row: VACUOUS iff it has no term at all (R =
    0 exactly and T = 0), else ``threshold`` of R against S = max(P, K T)
    (``scale_of``)."""

    if measure.residue == 0 and measure.terms == 0:
        return VACUOUS
    scale, _by = scale_of(measure.physical, measure.terms, tolerance_)
    return threshold(measure.residue, scale, tolerance_)


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


def _rung(
    decided: dict[Any, CheckRow],
    final: Any,
    run_at: Callable[[Any, list[Any]], Any],
    rung: Rung | None,
) -> None:
    """The rung of one point's rows of one kind, in place on ``decided``:
    the rows the ladder's final carrier ``final`` judged and did not pass
    (FAIL or INCONCLUSIVE) are re-run in arbitrary precision at the option's
    digits or ``rung_digits`` by ``run_at(carrier, keys)`` (per key the
    row judged there; or a refusal text), and take that verdict. Without a
    rung (an explicit carrier) they keep the final carrier's; a refused run
    or a row missing there leaves them inconclusive."""

    from .assemble import Precision

    name = _carrier_name(final)
    open_ = [
        key
        for key, row in decided.items()
        if row.verdict in (FAIL, INCONCLUSIVE) and row.carrier == name
    ]
    if not open_ or rung is None:
        return
    digits = (
        rung.digits if rung.digits is not None else rung_digits(final.unit_roundoff)
    )
    result = run_at(Precision.arbitrary(digits), open_)
    if isinstance(result, str):
        for key in open_:
            decided[key] = _refused(decided[key], result)
        return
    for key in open_:
        earlier = decided[key]
        if key not in result:
            decided[key] = _refused(earlier, f"no such row at {digits} digits")
            continue
        decided[key] = _with(result[key], digits=digits, fallback=_not_passed(earlier))


# ------------------------------------------------------------------ records


@dataclass(frozen=True)
class CheckRow:
    """One judged check: ``check`` ("poles", "ward" or "goldstone"),
    ``subject`` (a sector and pole coefficient, a leg and factor, or the
    finiteness of every loop order and row), the point index, the carrier
    that decided, the verdict (``VERDICTS``), ``deviation`` the measured R /
    S (``judge``; for a row made of several required rows, of the one with
    the largest R / S, whose R, P, T and the one of P and K T that set S
    are ``residue``, ``physical``, ``terms`` and ``scale_by``),
    ``tolerance`` the K it was judged with and ``ratio`` (R / S) / K (below
    1 passes), ``vacuous`` the count of its rows without any term (skipped);
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
    ``sector`` over the virtual's parts (bare, R2, UV; ``assemble.
    COMPONENTS`` but the virtual itself), 0 where no part has it, None where
    one cannot be computed (``magnitude``)."""

    found = 0.0
    for name, part in components.items():
        laurent = part.get(sector) if name != "virtual" else None
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


def _pole_rows(
    result: Any, index: int, carrier: str, tolerance_: float
) -> dict[Any, CheckRow]:
    """The pole rows of one evaluated point, keyed by (sector, k), each one
    required row (``judge``): R = |Re V_k - Re C_k|, P = max(|Re C_k|, |Re
    V_k|), T = the largest part (``_largest_part``); E / S where the
    evaluation ran its checks."""

    estimate = result.stability
    rows: dict[Any, CheckRow] = {}
    for sector, laurent in result.components["virtual"].items():
        poles = (result.ir_poles or {}).get(sector)
        if poles is None or len(laurent.coefficients) != 3:
            continue
        for k in (1, 2):
            sizes = (_real_size(poles[k - 1]), _real_size(laurent.coefficients[k]))
            error = None
            if estimate is not None:
                error = magnitude(estimate.absolute[sector].coefficients[k])
            measure = Measure(
                f"{_sector_name(sector)} {POLE_NAMES[k]}",
                real_gap(laurent.coefficients[k], poles[k - 1]),
                None if None in sizes else max(sizes),
                _largest_part(result.components, sector, k),
                error,
            )
            rows[(sector, k)] = _judged_row(
                "poles", measure.label, index, carrier, [measure], tolerance_
            )
    return rows


def _uncomputed(measure: Measure) -> str:
    """Why ``judge`` found a row inconclusive."""

    if measure.residue is None:
        return "the residue R cannot be computed (not a finite number or missing)"
    if measure.physical is None or measure.terms is None:
        return (
            "the physical reference P or the term scale T cannot be computed "
            "(not a finite number or missing)"
        )
    return (
        f"S = max(P, K T) is not positive (R {measure.residue:.3g}, P "
        f"{measure.physical:.3g}, T {measure.terms:.3g})"
    )


def _not_passed(row: CheckRow) -> str:
    """Why a carrier's row did not decide it (the next carrier's fallback)."""

    if row.verdict == INCONCLUSIVE and row.reason:
        return f"{row.carrier}: {row.reason}"
    return f"{row.carrier}: R / S {row.deviation} not below K {row.tolerance}"


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


def born_interfered_rows(
    target: Any,
    points: Sequence[tuple[Any, Any]],
    carriers: Sequence[Any],
    rung: Rung | None = None,
    kinematics: Any = None,
    out: list[CheckRow] | None = None,
) -> list[CheckRow]:
    """The pole and Ward rows of a Born-interfered probe slice (module
    docstring) at the lifted ``points`` ((point, mu_R^2) pairs), in
    ``carriers`` in order and, for a row the last one does not pass, the
    arbitrary-precision ``rung`` (None: none, an explicit carrier), judged
    with the check's ``tolerance``."""

    from . import induced, stability, ward
    from .plan_export import FailedPoints, NativeExecutor

    executor = NativeExecutor(target, inputs="native", forward=False, catani=True)
    tolerance_ = tolerance()
    legs = ward.gauge_legs(target)
    excluded = ward_applicability(target) if legs else None
    # ``out``: the caller's list, which keeps the rows of an interrupted
    # check.
    rows: list[CheckRow] = [] if out is None else out
    for index, (point, scale) in enumerate(points):
        # Poles against Catani's operator.
        decided: dict[Any, CheckRow] = {}
        sectors: list[Any] = []
        formed = evaluated = False
        refusal: str | None = None
        last: tuple[Any, Any, Any] | None = None
        for carrier in carriers:
            pending = [
                key
                for key, row in decided.items()
                if row.verdict not in (PASS, VACUOUS)
            ]
            if evaluated and not pending:
                break
            double = _carrier_name(carrier) == "double"
            status(
                f"{_point_text(index, points)}: poles against Catani's operator "
                f"({_carrier_name(carrier)})"
            )
            at, improved = _improved(executor, point, scale, carrier, kinematics)
            try:
                result = _evaluate(
                    executor,
                    at,
                    scale,
                    carrier,
                    stability.RECOMMENDED_CHECKS if double else None,
                )
            except FailedPoints as error:
                refusal = f"{_carrier_name(carrier)} refused: {error}"
                if evaluated:
                    # The earlier carrier's rows stay (never a pass) and say
                    # that this carrier was refused.
                    for key in pending:
                        decided[key] = _refused(decided[key], refusal)
                continue
            sectors = list(result.components["virtual"])
            formed = result.ir_poles is not None
            found = _pole_rows(result, index, _carrier_name(carrier), tolerance_)
            if improved is not None:
                found = {
                    key: _with(row, kinematics=improved) for key, row in found.items()
                }
            if not evaluated:
                decided = {
                    key: _with(row, fallback=refusal) if refusal else row
                    for key, row in found.items()
                }
            else:
                for key in pending:
                    earlier = decided[key]
                    decided[key] = (
                        _with(found[key], fallback=_not_passed(earlier))
                        if key in found
                        else _refused(
                            earlier, f"{_carrier_name(carrier)} has no such row"
                        )
                    )
            evaluated = True
            refusal = None
            last = (carrier, result, at)
        if last is not None and last[0] is carriers[-1]:
            _rung(
                decided,
                carriers[-1],
                _pole_rerun(executor, index, rung, tolerance_, kinematics),
                rung,
            )
        if not evaluated:
            rows.append(
                CheckRow(
                    "poles",
                    "every sector",
                    index,
                    None,
                    INCONCLUSIVE,
                    reason=f"inconclusive: {refusal}",
                    tolerance=tolerance_,
                )
            )
        rows.extend(decided.values())
        rows.extend(
            _unpredicted_rows(
                target, sectors, formed, index, {key[0] for key in decided}
            )
        )
        # Ward identities on every gluon and photon leg.
        if legs and excluded is None:
            status(f"{_point_text(index, points)}: Ward identities, {_legs(legs)}")
            rows.extend(
                _born_ward_rows(
                    executor,
                    point,
                    scale,
                    legs,
                    carriers,
                    index,
                    tolerance_,
                    rung,
                    kinematics,
                )
            )
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


def _pole_rerun(
    executor: Any,
    index: int,
    rung: Rung | None,
    tolerance_: float,
    kinematics: Any = None,
) -> Any:
    """The rung's ``run_at`` of a point's pole rows: the point lifted for
    the arbitrary-precision carrier and improved there like every rung's
    (``_improved``, m-lit lit-psimprove (G5)), evaluated with
    ``RECOMMENDED_CHECKS`` (its estimate is reported) and judged by
    ``_pole_rows``."""

    from . import stability
    from .plan_export import FailedPoints

    def run_at(carrier: Any, keys: list[Any]) -> Any:
        assert rung is not None
        point, scale = rung.lift(index, carrier)
        point, improved = _improved(executor, point, scale, carrier, kinematics)
        try:
            result = _evaluate(
                executor, point, scale, carrier, stability.RECOMMENDED_CHECKS
            )
        except FailedPoints as error:
            return f"arbitrary ({carrier.digits} digits) refused: {error}"
        found = _pole_rows(result, index, "arbitrary", tolerance_)
        return {
            key: _with(found[key], kinematics=improved) for key in keys if key in found
        }

    return run_at


def _with(row: CheckRow, **changes: Any) -> CheckRow:
    from dataclasses import replace

    return replace(row, **changes)


def _refused(row: CheckRow, refusal: str) -> CheckRow:
    """``row`` (an earlier carrier's row that did not pass) when a later
    carrier cannot judge it (a refusal, or no such row there): inconclusive
    (the carrier that would decide computed no R or S; never a pass), with
    the refusal and the earlier carrier's measurement in its reason."""

    earlier = f"R / S {row.deviation} at {row.carrier}"
    if row.verdict == INCONCLUSIVE and row.reason:
        earlier = f"{earlier} ({row.reason})"
    return _with(
        row, verdict=INCONCLUSIVE, reason=f"inconclusive: {refusal}; {earlier}"
    )


def _ward_measures(physical: Any, result: Any) -> list[Measure]:
    """The required rows of one Ward evaluation (module docstring): per Born
    sector R = |loop-side Born|, P = T = |physical Born| (a tree is its own
    term); per virtual sector and Laurent coefficient R = |V_k| of the
    substituted evaluation, P = |V_k| of the physical one, T = the physical
    evaluation's largest part (``_largest_part``), E the substituted
    evaluation's estimate where formed. A sector or coefficient only one of
    the two evaluations has is a missing operand (R None: inconclusive),
    never skipped."""

    out: list[Measure] = []
    loop_born = result.loop_born
    born = physical.born or {}
    if loop_born is None:
        out.append(Measure("Born", None, None, None))
    else:
        for sector in dict.fromkeys([*born, *loop_born]):
            size = magnitude(born[sector]) if sector in born else None
            out.append(
                Measure(
                    f"Born {_sector_name(sector)}",
                    magnitude(loop_born[sector]) if sector in loop_born else None,
                    size,
                    size,
                )
            )
    virtual = result.components["virtual"]
    reference = physical.components["virtual"]
    estimate = result.stability
    for sector in dict.fromkeys([*reference, *virtual]):
        laurent = virtual.get(sector)
        width = len(reference[sector].coefficients) if sector in reference else None
        if laurent is None or width is None or len(laurent.coefficients) != width:
            out.append(
                Measure(
                    f"{_sector_name(sector)} (a sector or coefficient only one "
                    "evaluation has)",
                    None,
                    None,
                    None,
                )
            )
            continue
        for k in range(width):
            error = None
            if estimate is not None and sector in estimate.absolute:
                error = magnitude(estimate.absolute[sector].coefficients[k])
            out.append(
                Measure(
                    f"{_sector_name(sector)} {COEFFICIENT_NAMES[k]}",
                    magnitude(laurent.coefficients[k]),
                    magnitude(reference[sector].coefficients[k]),
                    _largest_part(physical.components, sector, k),
                    error,
                )
            )
    return out


COEFFICIENT_NAMES = ("finite", "1/eps", "1/eps^2")


def _judged_row(
    check: str,
    subject: str,
    index: int,
    carrier: str,
    measures: Sequence[Measure],
    tolerance_: float,
) -> CheckRow:
    """One row made of the required rows ``measures``, each judged on its
    own first (``judge``), then ``combined`` over the rows with a term: the
    largest R / S is shown with its R, P, T, the one of P and K T that set
    S and its E / S; an inconclusive part names its label; rows without any
    term are counted (``vacuous``) and skipped, and a row all of whose parts
    are vacuous is VACUOUS (nothing to test: the quantity vanishes
    identically)."""

    verdicts = []
    reasons = []
    vacuous = 0
    worst: tuple[float, Measure, str | None, float | None] | None = None
    for measure in measures:
        verdict = judge(measure, tolerance_)
        if verdict == VACUOUS:
            vacuous += 1
            continue
        verdicts.append(verdict)
        if verdict == INCONCLUSIVE:
            reasons.append(f"{measure.label}: {_uncomputed(measure)}")
            continue
        scale, by = scale_of(measure.physical, measure.terms, tolerance_)
        measured = over(measure.residue, scale)
        if measured is not None and (worst is None or measured >= worst[0]):
            worst = (measured, measure, by, scale)
    if not verdicts and vacuous:
        verdict = VACUOUS
        reason = (
            "nothing to test: the quantity vanishes identically (every row "
            "vacuous: no term)"
        )
    else:
        verdict = combined(verdicts)
        reason = None
        if verdict == INCONCLUSIVE:
            reason = "inconclusive: " + ("; ".join(reasons) or "nothing compared")
        elif vacuous:
            reason = f"{vacuous} vacuous row(s) (no term) skipped"
    if worst is None:
        return CheckRow(
            check,
            subject,
            index,
            carrier,
            verdict,
            reason=reason,
            tolerance=tolerance_,
            vacuous=vacuous,
        )
    measured, measure, by, scale = worst
    return CheckRow(
        check,
        subject,
        index,
        carrier,
        verdict,
        _short(measured / tolerance_),
        _short(measured),
        _short(over(measure.estimate, scale)),
        reason=reason,
        tolerance=tolerance_,
        residue=_short(measure.residue),
        physical=_short(measure.physical),
        terms=_short(measure.terms),
        scale_by=by,
        vacuous=vacuous,
    )


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
    index: int,
    tolerance_: float,
) -> dict[Any, CheckRow]:
    """The Ward rows ``keys`` ((leg, factor)) of one point evaluated in
    ``carrier`` (``ward.ward_check``, binary64 with its estimate's checks),
    judged by ``_ward_measures``; a refused run raises ``FailedPoints``."""

    from . import ward

    name = _carrier_name(carrier)
    found: dict[Any, CheckRow] = {}
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
            found[key] = _judged_row(
                "ward",
                _ward_subject(*key),
                index,
                name,
                _ward_measures(check["physical"], result),
                tolerance_,
            )
    return found


def _born_ward_rows(
    executor: Any,
    point: Any,
    scale: Any,
    legs: Sequence[int],
    carriers: Sequence[Any],
    index: int,
    tolerance_: float,
    rung: Rung | None = None,
    kinematics: Any = None,
) -> list[CheckRow]:
    from . import ward
    from .plan_export import FailedPoints

    decided: dict[Any, CheckRow] = {}
    lifted = point
    every = [(leg, factor) for leg in legs for factor in ward.WARD_FACTORS]
    for carrier in carriers:
        name = _carrier_name(carrier)
        point, improved = _improved(executor, lifted, scale, carrier, kinematics)
        pending = [
            key
            for key in every
            if key not in decided or decided[key].verdict not in (PASS, VACUOUS)
        ]
        if not pending:
            break
        try:
            found = _ward_found(
                executor, point, scale, pending, legs, carrier, index, tolerance_
            )
        except FailedPoints as error:
            refusal = f"{name} refused: {error}"
            for key in pending:
                earlier = decided.get(key)
                decided[key] = (
                    CheckRow(
                        "ward",
                        _ward_subject(*key),
                        index,
                        name,
                        INCONCLUSIVE,
                        reason=f"inconclusive: {refusal}",
                        tolerance=tolerance_,
                    )
                    if earlier is None
                    else _refused(earlier, refusal)
                )
            continue
        for key in pending:
            earlier = decided.get(key)
            if key not in found:
                row = CheckRow(
                    "ward",
                    _ward_subject(*key),
                    index,
                    name,
                    INCONCLUSIVE,
                    reason=f"inconclusive: {name} has no such row",
                    tolerance=tolerance_,
                )
            else:
                row = _with(found[key], kinematics=improved)
            if earlier is not None:
                row = _with(row, fallback=_not_passed(earlier))
            decided[key] = row

    def run_at(carrier: Any, keys: list[Any]) -> Any:
        assert rung is not None
        relifted, at = rung.lift(index, carrier)
        relifted, improved = _improved(executor, relifted, at, carrier, kinematics)
        try:
            found = _ward_found(
                executor, relifted, at, keys, legs, carrier, index, tolerance_
            )
        except FailedPoints as error:
            return f"arbitrary ({carrier.digits} digits) refused: {error}"
        return {
            key: _with(row, carrier="arbitrary", kinematics=improved)
            for key, row in found.items()
        }

    if decided and carriers:
        _rung(decided, carriers[-1], run_at, rung)
    return list(decided.values())


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
    """A generation-time probe's decided result as a check row (its verdict
    the threshold rule's, ``induced.probe_verdict``)."""

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
    deviation = estimate = None
    relative = getattr(result, "relative", None) or {}
    if relative and result.ratios:
        key = max(result.ratios, key=lambda k: result.ratios[k])
        if key in relative:
            deviation, estimate = relative[key]
    worst = getattr(result, "worst_row", None) or (None,) * 5
    verdict = result.verdict
    reason = result.reason
    if verdict == INCONCLUSIVE:
        reason = f"inconclusive: {reason}"
    elif verdict != VACUOUS and getattr(result, "vacuous", 0):
        reason = f"{result.vacuous} vacuous row(s) (no term) skipped"
    return CheckRow(
        check,
        subject,
        index,
        entry["carrier"],
        verdict,
        _short(None if deviation is None else deviation / result.tolerance),
        _short(deviation),
        _short(estimate),
        fallback=fallback_text,
        reason=reason,
        kinematics=improved,
        tolerance=result.tolerance,
        residue=_short(worst[1]),
        physical=_short(worst[2]),
        terms=_short(worst[3]),
        scale_by=worst[4],
        vacuous=getattr(result, "vacuous", 0),
    )


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
    "reporting",
    "rung_digits",
    "scale_of",
    "status",
    "status_of",
    "threshold",
    "tolerance",
    "tolerating",
    "ward_applicability",
]
