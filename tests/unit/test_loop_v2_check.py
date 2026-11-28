# SPDX-License-Identifier: 0BSD
"""``pyamplicol check`` (m-lit lit-examples, USER 2026-11-09 ~08:30): the pole
and Ward checks of a one-loop request regenerated in memory
(``loops.v2.checks``, ``api.services.check``).

* **Born-interfered pass** (u u~ > g g, NLO QCD, loop_sm): the poles of every
  point and sector against Catani's operator and the Ward identity of both
  gluons (c = 1 and i) pass in binary64, from the run card and from the
  generated artifact; the Goldstone row reads "not applicable" with its
  reason; the CLI exits 0 and its JSON carries every row.
* **Loop-induced pass** (g g > a a, five massless quark flavours): the
  finiteness probe and the Ward probe of one leg per gauge-boson species
  pass in binary64 at every point.
* **The failing case**: the same request on a copy of loop_sm without the
  R2 vertex of its external particles (``loop_r2_dropped``) fails the Ward
  check in binary64 far beyond ten times its estimate and again after the
  double-double fallback; the CLI exits 1.
* **Complex-mass scheme, untagged photons** (u u~ > a a with QED
  corrections, WT != 0): the QED pole prediction's gamma_gamma counts the
  massless charged fermions; the top's complex pole mass is a massive
  internal species, not the cms-external-width refusal of an unstable leg.
* **Exit codes and statuses** of the report (pure records), and a process
  with nothing to check (an exact colour zero, h > g a) exits 3.
* **The threshold rule** (USER 2026-11-25; pure records): every row passes
  iff R < K S (equality a miss), is inconclusive iff R or S cannot be
  computed (not a finite number, a missing operand, a vanishing S, 0/0
  included), and a row made of several required rows fails if one fails;
  K is ``check.tolerance``, else the requested relative accuracy, and
  changes the verdict; a planted violation fails and a non-finite row is
  inconclusive; a sector without a pole row is listed "no prediction",
  never omitted.
* **An artifact is checked on what it stores**: an API-generated artifact
  whose configuration names another process is checked on its stored
  process; a model that is not the stored one (content hash) or a source
  that does not resolve is refused (``ArtifactError``), and ``--model`` /
  ``model=`` names the stored model's source.
* **The carrier ladder and the arbitrary-precision rung** (scripted carrier
  results): a row binary64 does not pass runs in double-double, a row
  double-double does not pass runs alone in arbitrary precision at twice
  double-double's digits (or ``check.arbitrary_digits``) and takes the
  verdict there, pole and Ward rows alike; a row still failing there fails
  its process (exit 1); an explicit carrier runs no rung; a later carrier's
  refusal leaves the row inconclusive, never a pass.
* **Ward rows not applicable** (USER 2026-11-10 ~00:17; records on a toy
  model): a request whose corrections include one other than the model's
  strong correction AND with an on-shell zero-width external massive quark
  (an antiquark alone included) has one "not applicable" Ward row with the
  reason; its Ward evaluation is never called and its passing poles pass
  the process. QCD-only corrections with external tops, EW corrections with
  massless quarks only, a massive colour-singlet fermion or a quark with a
  non-zero width are checked as before. Ward rows are not split by
  squared-order sector: there is no per-sector Ward row to keep checked.

The Goldstone-equivalence path itself (an external massive vector in
't Hooft-Feynman gauge) is lit-probe's (``test_loop_v2_induced_probes``,
``test_loop_v2_induced_ew_gauge``): ``check`` calls the same
``induced.goldstone_point``; here its "not applicable" row is tested.
"""

from __future__ import annotations

import io
import json
import shutil
from importlib import resources
from pathlib import Path

import pytest

from .loop_r2_dropped import declaration, drop_r2_vertex

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "loop" / "required" / "li"


def _card(
    root: Path,
    expression: str,
    *,
    source: str = "loop_sm",
    fixed: dict[str, str] | None = None,
    veto: tuple[str, ...] = (),
    action: str = "check",
    points: int = 1,
) -> Path:
    fixed = fixed or {"WT": "0"}
    root.mkdir(parents=True, exist_ok=True)
    card = root / "card.toml"
    card.write_text(
        f"""action = "{action}"
[model]
source = {json.dumps(source)}
restriction = "no_b_mass"
[process]
entries = [{{expression = {json.dumps(expression)}, name = "p"}}]
loop_coupling_orders = ["QCD"]
[loop]
r2_strategy = "model"
{declaration(source)}[loop.preparation]
fixed_parameters = {{{", ".join(f"{k} = {json.dumps(v)}" for k, v in fixed.items())}}}
[generation]
output = "artifact"
emit_api_bundle = false
particle_veto = {json.dumps(list(veto))}
[check]
points = {points}
"""
    )
    return card


def _nf5() -> dict[str, str]:
    fixture = json.loads((FIXTURES / "li_gg_aa_nf5.json").read_text())
    return dict(fixture["scheme_data"]["fixed_parameters"])


def _cli(*arguments: str) -> tuple[int, dict]:
    from pyamplicol.cli.main import run_cli

    stdout, stderr = io.StringIO(), io.StringIO()
    code = run_cli(
        ["check", *arguments, "--json", "--progress", "off"],
        stdout=stdout,
        stderr=stderr,
    )
    return code, json.loads(stdout.getvalue()) if stdout.getvalue() else {}


def _rows(report, check: str):
    (process,) = report.processes
    return [row for row in process.rows if row.check == check]


# --------------------------------------------------------------- records


@pytest.mark.loop_fast
def test_statuses_and_exit_codes_follow_the_rows():
    from pyamplicol.loops.v2 import checks

    def process(*verdicts):
        rows = tuple(
            checks.CheckRow("poles", "s", 0, "double", verdict) for verdict in verdicts
        )
        return checks.ProcessCheck(
            "p", "a > b", "virtual", "zero", (), "ninjars", rows, 0.0
        )

    def report(*processes):
        return checks.CheckReport(
            "x", "card", 1, 0, "auto", ("double",), processes, "", 0.0
        )

    passed = process(checks.PASS, checks.NOT_APPLICABLE, checks.NO_PREDICTION)
    failed = process(checks.PASS, checks.FAIL)
    empty = process(checks.NOT_APPLICABLE, checks.NO_PREDICTION)
    not_run = process(checks.PASS, checks.NOT_RUN)
    assert passed.status == checks.PASSED
    assert failed.status == checks.FAILED
    assert empty.status == checks.NOTHING_CHECKED
    assert not_run.status == checks.NOTHING_CHECKED
    assert report(passed).exit_code == checks.EXIT_PASSED == 0
    assert report(passed, failed).exit_code == checks.EXIT_FAILED == 1
    assert report(passed, empty).exit_code == checks.EXIT_NOTHING_CHECKED == 3
    assert report(failed, empty).exit_code == checks.EXIT_FAILED
    assert len({0, checks.EXIT_FAILED, checks.EXIT_NOTHING_CHECKED, 2}) == 4


@pytest.mark.loop_fast
def test_the_aggregate_is_closed_and_an_inconclusive_row_never_passes():
    """A process's status is a closed aggregate (``checks.status_of``): a
    pass next to an inconclusive row, or next to a verdict outside
    ``VERDICTS``, is INCONCLUSIVE (exit code 4), never PASSED; a failure
    wins over it; every row passing (with reasoned neutral rows) is PASSED;
    the text report names the status."""

    import prettytable

    from pyamplicol.loops.v2 import checks
    from pyamplicol.reporting.checks import check_report_summary

    def process(*verdicts):
        rows = tuple(
            checks.CheckRow("ward", "leg 1", 0, "double", verdict)
            for verdict in verdicts
        )
        return checks.ProcessCheck(
            "p", "a > b", "virtual", "zero", (), "ninjars", rows, 0.0
        )

    def report(*processes):
        return checks.CheckReport(
            "x", "card", 1, 0, "auto", ("double",), processes, "", 0.0
        )

    inconclusive = process(checks.PASS, checks.INCONCLUSIVE)
    unknown = process(checks.PASS, "maybe")
    passed = process(checks.PASS, checks.PASS, checks.NOT_APPLICABLE)
    assert inconclusive.status == checks.INCONCLUSIVE_STATUS == "inconclusive"
    assert unknown.status == checks.INCONCLUSIVE_STATUS
    assert passed.status == checks.PASSED
    assert process(checks.FAIL, checks.INCONCLUSIVE).status == checks.FAILED
    assert report(passed, inconclusive).exit_code == checks.EXIT_INCONCLUSIVE == 4
    assert report(passed, unknown).exit_code == checks.EXIT_INCONCLUSIVE
    assert report(inconclusive, process(checks.FAIL)).exit_code == checks.EXIT_FAILED
    assert report(passed).exit_code == checks.EXIT_PASSED
    assert not report(passed, inconclusive).passed

    text = check_report_summary(
        report(passed, inconclusive), prettytable=prettytable, color=False
    )
    assert "check INCONCLUSIVE (exit code 4)" in text
    assert ": inconclusive" in text


@pytest.mark.loop_fast
def test_the_stored_checks_never_scale_a_violation_away():
    """``stored_checks.compare_carriers`` (the external reviewer's inputs):
    both carriers return (finite, 1/eps, 1/eps^2) = (0, 1, 0), Catani
    predicts (0, 0), no uncertified lane, zero direction error: the
    double-double Catani comparison FAILS (the absolute deviation 1 against
    the double-double tolerance with its zero-denominator convention; a
    vanishing prediction never scales it away), and it is no inconclusive
    row."""

    from types import SimpleNamespace

    from tools.loop_benchmark import stored_checks

    sector = (("QCD", 4),)

    def laurent(*values):
        return SimpleNamespace(coefficients=tuple(values))

    def result(poles=None):
        return SimpleNamespace(
            born={sector: 1.0},
            components={"virtual": {sector: laurent(0.0, 1.0, 0.0)}},
            stability=SimpleNamespace(absolute={sector: laurent(0.0, 0.0, 0.0)}),
            ir_poles=poles,
            uncertified_bound={},
        )

    binary64, dd = result(), result({sector: (0.0, 0.0)})
    out = stored_checks.compare_carriers(binary64, dd)
    assert out["passed"] is False and out["inconclusive"] is False, out
    # The prediction met: passes.
    met = result({sector: (1.0, 0.0)})
    assert stored_checks.compare_carriers(binary64, met)["passed"] is True


@pytest.mark.loop_fast
def test_a_normalization_uncertain_ward_point_stays_asserted():
    """The stored Ward stage (the external reviewer's inputs): a row whose
    physical scale is 1 +- 2 with E = 2e-9 and residue 0 is inconclusive and
    nominally out of the binary64 scope, but in scope at the true scale 3:
    it is not ``scope_excluded``, its point stays asserted, and with one
    clean passing point the stage is NOT a pass (one inconclusive)."""

    from types import SimpleNamespace

    from pyamplicol.loops.v2 import ward
    from pyamplicol.loops.v2.assemble import COMPONENTS
    from pyamplicol.loops.v2.stability import REDUCTION
    from tools.loop_benchmark import stored_checks

    sector = ("QCD", 6)

    def laurent(*values):
        return SimpleNamespace(coefficients=tuple(values))

    def point(virtual, estimate=(1e-30,), bound=None):
        components = {name: {sector: laurent(1.0)} for name in COMPONENTS}
        components["virtual"] = {sector: laurent(*virtual)}
        return SimpleNamespace(
            components=components,
            born={sector: 1.0},
            loop_born={sector: 0.0},
            stability=SimpleNamespace(
                budgets={REDUCTION: {}}, absolute={sector: laurent(*estimate)}
            ),
            uncertified_bound={} if bound is None else {sector: bound},
        )

    uncertain = ward.ward_row(
        point((1.0,), bound=(2.0,)), point((0.0,), (2e-9,)), "double"
    )
    assert uncertain["passed"] is None and uncertain["inconclusive"]
    assert uncertain["in_scope"] is False and uncertain["scope_excluded"] is False
    clean = ward.ward_row(point((1.0,)), point((0.0,)), "double")
    assert clean["passed"] is True

    def record(index, row):
        asserted = not row["scope_excluded"]
        found_passed = row["passed"]
        return {
            "index": index,
            "carrier": "double",
            "asserted": asserted,
            "passed": found_passed if asserted else None,
            "rows": [
                {k: v for k, v in row.items() if k in stored_checks._WARD_ROW_KEYS}
            ],
        }

    stage = stored_checks.ward_stage([record(0, clean), record(1, uncertain)])
    assert stage == {"asserted": 2, "passed": False, "inconclusive": 1}
    assert stored_checks.ward_stage([record(0, clean)])["passed"] is True
    # Demonstrably out of scope at every scale: excluded, as before.
    far = ward.ward_row(point((1.0,)), point((0.0,), (2e-9,)), "double")
    assert far["scope_excluded"] is True


@pytest.mark.loop_fast
def test_the_stored_rescue_stages_never_meet_an_uncertified_level():
    """``stored_checks.rescue_level0`` / ``rescue_level1`` (the stored
    rescue stages, as the production policy): a binary64 point with a lane
    served without accuracy evidence is sent up whatever its estimate (here
    0); a double-double point with one is not met whatever its estimate,
    its reasons kept; clean points as before."""

    from types import SimpleNamespace

    from pyamplicol.api.virtual_results import UNCERTIFIED
    from tools.loop_benchmark import stored_checks

    reason = "a reduction lane vanishes within the resolution of its own terms"
    sector = (("QCD", 4),)

    def result(relative, unsure):
        return SimpleNamespace(
            stability=SimpleNamespace(relative=relative),
            lane_rescue=((UNCERTIFIED + reason, 1),) if unsure else (),
            components={
                "virtual": {sector: SimpleNamespace(coefficients=(1.0, 0.0, 0.0))}
            },
        )

    estimates, unsure, up = stored_checks.rescue_level0(
        {0: result(0.0, True), 1: result(1e-9, False), 2: result(1e-3, False)},
        1e-5,
    )
    assert up == [0, 2] and unsure[0] == (reason,) and not unsure[1]
    assert estimates[0] == 0.0
    flagged = stored_checks.rescue_level1(result(0.0, True), 1e-5)
    assert flagged["met"] is False and flagged["uncertified"] == [reason]
    assert stored_checks.rescue_level1(result(1e-9, False), 1e-5)["met"] is True


@pytest.mark.loop_fast
def test_the_threshold_rule():
    """``checks.threshold``: PASS iff R < K S (equality is a miss), FAIL iff
    R >= K S, INCONCLUSIVE iff R or S cannot be computed (None, NaN,
    infinite, negative R, S not positive, 0/0 included); compared as R / S <
    K, so neither K S nor R / S underflows to a false verdict. A row of
    several required rows fails if one fails, else is inconclusive if one
    is (or none was compared). The magnitudes: a non-finite or unconvertible
    value is None, never a raise. K: ``tolerating``, else the reduction
    target in effect, else the default target."""

    import math
    from decimal import Decimal

    from pyamplicol.loops.v2 import checks
    from pyamplicol.loops.v2.reduction import default_target, targeting
    from pyamplicol.loops.v2.ward import judged

    t = checks.threshold
    assert t(0.9e-5, 1.0, 1e-5) == checks.PASS
    assert t(1e-5, 1.0, 1e-5) == checks.FAIL  # equality is a miss
    assert t(2e-5, 1.0, 1e-5) == checks.FAIL
    assert t(0.0, 1.0, 1e-5) == checks.PASS
    for residual, scale in (
        (0.0, 0.0),
        (1e-20, 0.0),
        (None, 1.0),
        (1.0, None),
        (math.nan, 1.0),
        (1.0, math.nan),
        (math.inf, 1.0),
        (0.0, math.inf),
        (-1.0, 1.0),
        (0.0, -1.0),
    ):
        assert t(residual, scale, 1e-5) == checks.INCONCLUSIVE, (residual, scale)
    # Tiny and huge operands: R / S is formed, never K S.
    assert t(1e-320, 1e-300, 1e-5) == checks.PASS
    assert t(1e-310, 1e-306, 1e-5) == checks.FAIL
    assert t(1e300, 1e308, 1e-5) == checks.PASS
    assert checks.combined([checks.PASS, checks.INCONCLUSIVE]) == checks.INCONCLUSIVE
    assert checks.combined([checks.INCONCLUSIVE, checks.FAIL]) == checks.FAIL
    assert checks.combined([checks.PASS, checks.PASS]) == checks.PASS
    assert checks.combined([]) == checks.INCONCLUSIVE
    assert checks.magnitude(complex(3, 4)) == 5.0
    assert checks.magnitude(Decimal("1e400")) is None
    assert checks.magnitude(complex(math.nan, 0)) is None
    assert checks.magnitude("not a number") is None
    assert checks.real_gap(2.0 + 5j, 1.5 - 7j) == 0.5
    assert checks.real_gap(math.inf, 1.0) is None
    assert checks.real_gap(Decimal("1e400"), Decimal("1e400")) == 0.0
    with checks.tolerating(None):
        assert checks.tolerance() == default_target()
        with targeting(1e-7):
            assert checks.tolerance() == 1e-7
            with checks.tolerating(1e-3):
                assert checks.tolerance() == 1e-3
    # The rule per row (``judge``): incomplete or non-finite is
    # inconclusive (never vacuous); no term at all is vacuous; a known-zero
    # reference is judged term-relative; R < K P passes on the physical
    # scale; a miss that K T would pass is ambiguous only where P may be
    # noise (P = 0 from cancelling terms, or P <= 10 E_P), else a physical
    # failure.
    measure = checks.Measure

    def verdict(*args, **options):
        found = checks.judge(measure("x", *args, **options), 1e-5)
        return found.verdict, found.scale

    assert verdict(1e-6, 1.0, 1e5) == (checks.PASS, checks.PHYSICAL)
    assert verdict(1e-3, 1.0, 1e5) == (checks.FAIL, checks.PHYSICAL)
    assert verdict(1e-3, 1.0, 1e5, physical_error=0.11) == (checks.AMBIGUOUS, None)
    assert verdict(1e-3, 1.0, 1e5, physical_error=0.01) == (
        checks.FAIL,
        checks.PHYSICAL,
    )
    assert verdict(1e-3, 0.0, 1e5) == (checks.AMBIGUOUS, None)
    assert verdict(1e-3, 0.0, 1e5, zero_reference=True) == (
        checks.PASS,
        checks.TERM_RELATIVE,
    )
    assert verdict(2.0, 0.0, 1e5, zero_reference=True) == (
        checks.FAIL,
        checks.TERM_RELATIVE,
    )
    assert verdict(0.0, 0.0, 0.0) == (checks.VACUOUS, None)
    assert verdict(0.0, float("nan"), 0.0)[0] == checks.INCONCLUSIVE
    assert verdict(0.0, 0.0, 0.0, complete=False)[0] == checks.INCONCLUSIVE
    assert verdict(0.0, None, 1.0)[0] == checks.INCONCLUSIVE
    # An ambiguous row against a narrower carrier's measurement (``settle``):
    # P reproduces (a physical miss), collapses with the carriers' noise
    # (term-relative), or neither (inconclusive).
    double, double_double = 2.0**-53, 2.0**-104

    def ambiguous(p_before, p_now, residue=1e-3, terms=1e5):
        before = checks.Judgement(
            checks.FAIL,
            checks.PHYSICAL,
            None,
            None,
            measure("x", 1.0, p_before, terms),
            "double",
            double,
        )
        now = checks.Judgement(
            checks.AMBIGUOUS,
            None,
            None,
            None,
            measure("x", residue, p_now, terms),
            "double-double",
            double_double,
        )
        found = checks.settle(now, before, 1e-5)
        return found.verdict, found.scale

    assert ambiguous(1.0, 1.0) == (checks.FAIL, checks.PHYSICAL)
    assert ambiguous(1e-17, 1e-33) == (checks.PASS, checks.TERM_RELATIVE)
    assert ambiguous(1e-17, 1e-18)[0] == checks.INCONCLUSIVE
    assert (
        checks.settle(
            checks.Judgement(checks.AMBIGUOUS, None, None, None, measure("x", 1, 1, 1)),
            None,
            1e-5,
        ).verdict
        == checks.INCONCLUSIVE
    )
    # A row every part of which is vacuous; a process of vacuous rows passes.
    cells = {"x": checks.judge(measure("x", 0.0, 0.0, 0.0), 1e-5)}
    row = checks.row_from_cells("poles", "x", 0, cells, 1e-5)
    assert row.verdict == checks.VACUOUS and row.vacuous == 1
    assert row.reason.startswith("nothing to test")
    assert checks.status_of([checks.VACUOUS, checks.NOT_APPLICABLE]) == checks.PASSED
    assert checks.status_of([checks.NOT_APPLICABLE]) == checks.NOTHING_CHECKED
    # The stored-process harness keeps its three-way rule (``ward.judged``).
    assert judged(0.5, 1.0, 0.0) is True and judged(1.5, 1.0, 0.0) is False
    assert judged(0.5, 1.0, 0.6) is None


@pytest.mark.loop_fast
def test_the_catani_criterion_is_the_harness_rule():
    """|pole - Catani| <= 10 E + 1e-12 |Catani| per coefficient (binary64)
    and 1e-12 relative in double-double, as stored_checks.py applied it."""

    from pyamplicol.loops.v2.checks import catani_comparison, catani_dd_comparison

    values = [0.0, 2.0 + 1e-9, -3.0]
    poles = (2.0, -3.0)
    _c, deviations, bounds, ok = catani_comparison(values, poles, [0, 1e-10, 0])
    assert ok and bounds[0] == pytest.approx(10 * 1e-10 + 2e-12)
    assert deviations[0] == pytest.approx(1e-9)
    assert not catani_comparison(values, poles, [0, 1e-11, 0])[3]
    assert not catani_comparison(values, poles, None)[3]
    assert catani_dd_comparison([0.0, 2.0 * (1 + 1e-13), -3.0], poles)[2]
    assert not catani_dd_comparison([0.0, 2.0 * (1 + 1e-11), -3.0], poles)[2]


def _pole_rows(result, tolerance):
    """The pole check rows of one evaluation (``checks._pole_measures``,
    each judged at one carrier)."""

    from pyamplicol.loops.v2 import checks

    return {
        key: checks.row_from_cells(
            "poles", m.label, 0, {key: checks.judge(m, tolerance)}, tolerance
        )
        for key, m in checks._pole_measures(result).items()
    }


def _ward_row(measures, tolerance):
    """One Ward check row from its required rows, judged at one carrier."""

    from pyamplicol.loops.v2 import checks

    cells = {label: checks.judge(m, tolerance) for label, m in measures.items()}
    return checks.row_from_cells("ward", "leg 1, c = 1", 0, cells, tolerance)


def _laurent(*values):
    from types import SimpleNamespace as NS

    return NS(coefficients=list(values))


def _pole_result(sector, virtual, poles, parts=None, stability=None):
    """A pole evaluation stand-in: the virtual's Laurent coefficients, its
    parts (default: one bare part equal to the virtual) and Catani's (1/eps,
    1/eps^2)."""

    from types import SimpleNamespace as NS

    components = {"virtual": {sector: _laurent(*virtual)}}
    for name, values in (parts or {"bare": virtual}).items():
        components[name] = {sector: _laurent(*values)}
    return NS(stability=stability, components=components, ir_poles={sector: poles})


@pytest.mark.loop_fast
def test_pole_and_ward_rows_judge_r_against_k_s():
    """Pole rows: R = |Re V_k - Re C_k| against P = max(|Re C_k|, |Re V_k|)
    (a known-zero analytic C_k: term-relative against T, the largest part);
    a planted violation fails whatever the parts' cancellation, K changes
    the verdict, a non-finite coefficient is inconclusive, a coefficient no
    part has is vacuous, and a sector without a pole row is listed "no
    prediction" (or "not run" where predicted), never omitted. Ward
    rows: every Born sector and every virtual sector and coefficient judged
    on its own; a sector or coefficient only one evaluation has is a missing
    operand (inconclusive)."""

    from types import SimpleNamespace as NS

    from pyamplicol.loops.v2 import checks

    first, second = (("QCD", 4),), (("QCD", 2), ("QED", 2))
    exact = _pole_result(first, (0.5, 2.0, -3.0), (2.0, -3.0))
    rows = _pole_rows(exact, 1e-5)
    assert {row.verdict for row in rows.values()} == {checks.PASS}
    assert all(row.deviation == 0 and row.tolerance == 1e-5 for row in rows.values())
    # A planted violation of 1e-3 relative on the 1/eps pole.
    planted = _pole_result(first, (0.5, 2.002, -3.0), (2.0, -3.0))
    rows = _pole_rows(planted, 1e-5)
    assert rows[(first, 1)].verdict == checks.FAIL
    # S = max(|C|, |V|) = 2.002.
    assert rows[(first, 1)].deviation == pytest.approx(0.002 / 2.002, rel=1e-3)
    assert rows[(first, 2)].verdict == checks.PASS
    # K changes the verdict.
    assert _pole_rows(planted, 1e-2)[(first, 1)].verdict == (checks.PASS)
    # P = max(|C|, |V|) decides, whatever the parts (T): a bare part of 20 or
    # of 1e6 cancelling against the UV part changes nothing (the reviewer's
    # case: a per-mille violation never hides behind the term scale).
    parted = _pole_result(
        first, (0.5, 2.002, -3.0), (2.0, -3.0), parts={"bare": (1.0, 20.0, -3.0)}
    )
    row = _pole_rows(parted, 1e-5)[(first, 1)]
    assert (row.scale_by, row.physical, row.terms) == ("physical", 2.0, 20.0)
    assert row.deviation == pytest.approx(0.002 / 2.002, rel=1e-3)
    assert row.verdict == checks.FAIL and row.residue == pytest.approx(2e-3)
    cancelled = _pole_result(
        first, (0.5, 2.002, -3.0), (2.0, -3.0), parts={"bare": (1.0, 1e6, -3.0)}
    )
    row = _pole_rows(cancelled, 1e-5)[(first, 1)]
    assert row.scale_by == "physical" and row.verdict == checks.FAIL
    assert row.deviation == pytest.approx(0.002 / 2.002, rel=1e-3)
    # A non-finite coefficient: inconclusive, never a raise or a pass.
    broken = _pole_result(first, (0.5, float("nan"), -3.0), (2.0, -3.0))
    rows = _pole_rows(broken, 1e-5)
    assert rows[(first, 1)].verdict == checks.INCONCLUSIVE
    assert "cannot be computed" in rows[(first, 1)].reason
    # A double pole neither the prediction nor any part has (only massive
    # coloured legs): vacuous, nothing to test.
    massive = _pole_result(first, (0.5, 2.0, 0.0), (2.0, 0.0))
    row = _pole_rows(massive, 1e-5)[(first, 2)]
    assert (row.verdict, row.vacuous) == (checks.VACUOUS, 1)
    # A spurious double pole against a vanishing analytic prediction (a
    # known-zero reference): term-relative, R / T = 1, a failure.
    spurious = _pole_result(first, (0.5, 2.0, 1e-3), (2.0, 0.0))
    row = _pole_rows(spurious, 1e-5)[(first, 2)]
    assert row.verdict == checks.FAIL and row.deviation == pytest.approx(1.0)
    assert row.scale_by == "term-relative"
    # A sector the operators predict but without a pole row at this point:
    # an applicable check that did not run, "not run" (exit 3), not a neutral
    # "no prediction" (DECISIONS 2026-11-09 14:25, lit-examples re-audit
    # issue 8); a sector they do not predict keeps "no prediction".
    slice_ = NS(unpredicted_sectors=lambda: {})
    (row,) = checks._unpredicted_rows(slice_, [first, second], True, 0, {first})
    assert row.verdict == checks.NOT_RUN and row.subject == "QCD^2 QED^2"
    assert row.reason.startswith("an applicable check did not run")
    slice_ = NS(unpredicted_sectors=lambda: {second: "uncorrected exchange"})
    (row,) = checks._unpredicted_rows(slice_, [first, second], True, 0, {first})
    assert row.verdict == checks.NO_PREDICTION
    assert row.reason.startswith("uncorrected exchange")

    # Ward: physical and substituted evaluations.
    def evaluation(virtual, born, loop_born=None, sectors=(first,)):
        return NS(
            components={"virtual": {s: _laurent(*virtual) for s in sectors}},
            born=born,
            loop_born=loop_born,
            stability=None,
        )

    physical = evaluation((2.0, 1.0, 0.5), {first: 4.0})
    clean = evaluation((1e-16, 1e-17, 0.0), {first: 4.0}, {first: 1e-16})
    measures = checks._ward_measures(physical, clean)
    assert list(measures) == [
        "Born QCD^4",
        "QCD^4 finite",
        "QCD^4 1/eps",
        "QCD^4 1/eps^2",
    ]
    row = _ward_row(measures, 1e-5)
    assert row.verdict == checks.PASS and row.deviation == pytest.approx(5e-17)
    assert row.vacuous == 0 and row.scale_by == "physical" and len(row.cells) == 4
    planted = evaluation((1e-16, 1e-3, 0.0), {first: 4.0}, {first: 1e-16})
    row = _ward_row(checks._ward_measures(physical, planted), 1e-5)
    assert row.verdict == checks.FAIL and row.deviation == pytest.approx(1e-3)
    # A short Laurent tuple, a missing sector, a missing loop-side Born.
    short = evaluation((1e-16, 1e-17), {first: 4.0}, {first: 0.0})
    other = evaluation((0.0, 0.0, 0.0), {first: 4.0}, {first: 0.0}, sectors=(second,))
    none = evaluation((0.0, 0.0, 0.0), {first: 4.0}, None)
    for substituted in (short, other, none):
        row = _ward_row(checks._ward_measures(physical, substituted), 1e-5)
        assert row.verdict == checks.INCONCLUSIVE, substituted
    # A Born sector that vanishes at this point (a colour zero) on both sides
    # is vacuous; a loop-side residue where the physical Born has no term
    # fails (no cross-row fallback).
    zero = evaluation((2.0, 1.0, 0.5), {first: 4.0, second: 0.0})
    measures = checks._ward_measures(
        zero, evaluation((2.0, 1.0, 0.5), {}, {first: 0.0, second: 0.0})
    )
    assert [
        checks.judge(m, 1e-5).verdict
        for m in measures.values()
        if m.label.startswith("Born")
    ] == [checks.PASS, checks.VACUOUS]
    measures = checks._ward_measures(
        zero, evaluation((0.0, 0.0, 0.0), {}, {first: 0.0, second: 1e-3})
    )
    born = measures["Born QCD^2 QED^2"]
    assert (born.residue, born.physical, born.terms) == (1e-3, 0.0, 0.0)
    assert checks.judge(born, 1e-5).verdict == checks.FAIL


@pytest.mark.loop_fast
def test_a_refused_double_double_run_leaves_the_binary64_rows_inconclusive(
    monkeypatch,
):
    """When binary64 fails a row and double-double is refused, the row is
    inconclusive (the carrier that would decide computed no R or S; never a
    pass), its reason names the refusal and binary64's R / S; pole and Ward
    rows alike (lit-examples re-audit issue 3)."""

    from types import SimpleNamespace as NS

    from pyamplicol.loops.v2 import checks, induced, plan_export, ward

    sector = (("QCD", 4),)
    carriers = (NS(arithmetic="double"), NS(arithmetic="double-double"))

    def evaluate(_executor, _point, _scale, carrier, _checks):
        if carrier.arithmetic == "double-double":
            raise plan_export.FailedPoints([None], {0: ["ill-conditioned"]})
        return _pole_result(sector, (0.0, 2.002, -3.0), (2.0, -3.0))

    def ward_check(_executor, _point, _scale, name, *, legs, factors, **_options):
        if name == "double-double":
            raise plan_export.FailedPoints([None], {0: ["ill-conditioned"]})
        physical = NS(
            components={"virtual": {sector: _laurent(2.0, 1.0, 0.5)}},
            born={sector: 4.0},
            loop_born=None,
            stability=None,
        )
        result = NS(
            components={"virtual": {sector: _laurent(1e-3, 0.0, 0.0)}},
            born={sector: 4.0},
            loop_born={sector: 0.0},
            stability=None,
        )
        labels = [(leg, factor) for leg in legs for factor in factors]
        return {
            "physical": physical,
            "results": [result] * len(labels),
            "rows": [{"leg": leg, "factor": factor} for leg, factor in labels],
        }

    monkeypatch.setattr(plan_export, "NativeExecutor", lambda *a, **k: None)
    monkeypatch.setattr(checks, "_evaluate", evaluate)
    monkeypatch.setattr(ward, "gauge_legs", lambda _target: [3])
    monkeypatch.setattr(ward, "ward_check", ward_check)
    monkeypatch.setattr(induced, "goldstone_applicability", lambda _t: "n/a")
    # A stand-in target without request data: its Ward rows apply.
    monkeypatch.setattr(checks, "ward_applicability", lambda _t: None)
    target = NS(unpredicted_sectors=lambda: {})
    with checks.tolerating(1e-5):
        rows = checks.born_interfered_rows(target, [(None, 1)], carriers)
    single = [row for row in rows if row.subject == "QCD^4 1/eps"]
    ward_rows = [row for row in rows if row.check == "ward"]
    assert len(single) == 1 and len(ward_rows) == 2
    for row in [*single, *ward_rows]:
        assert row.verdict == checks.INCONCLUSIVE and row.carrier == "double"
        assert "double-double refused" in row.reason, row
        # binary64's measurement stays on the row (R / P, the carrier).
        assert row.deviation is not None and row.deviation > 1e-5, row
    (double_pole,) = [row for row in rows if row.subject == "QCD^4 1/eps^2"]
    assert double_pole.verdict == checks.PASS


def _toy_target(legs, corrections, fixed):
    """A probe-slice stand-in on a toy model (records): a gluon, a photon,
    a massive top (MT, width WT), a massless up quark, a massless bottom
    quark, a W (MW, width WW) coupling t b W, a massive muon (MM, width WM)
    whose orders are QCD (the gluon's vertices) and QED."""

    from types import SimpleNamespace as NS

    def particle(name, anti, pdg, spin, colour, charge=0.0, mass="ZERO", width="ZERO"):
        return NS(
            name=name,
            antiname=anti,
            pdg_code=pdg,
            spin=spin,
            color=colour,
            charge=charge,
            mass=mass,
            width=width,
            ghost_number=0,
            goldstoneboson=False,
            auxiliary_kind=None,
        )

    particles = [
        particle("g", "g", 21, 3, 8),
        particle("a", "a", 22, 3, 1),
        particle("t", "t~", 6, 2, 3, 2 / 3, "MT", "WT"),
        particle("t~", "t", -6, 2, -3, -2 / 3, "MT", "WT"),
        particle("u", "u~", 2, 2, 3, 2 / 3),
        particle("u~", "u", -2, 2, -3, -2 / 3),
        particle("b", "b~", 5, 2, 3, -1 / 3),
        particle("b~", "b", -5, 2, -3, 1 / 3),
        particle("W+", "W-", 24, 3, 1, 1.0, "MW", "WW"),
        particle("W-", "W+", -24, 3, 1, -1.0, "MW", "WW"),
        particle("mu-", "mu+", 13, 2, 1, -1.0, "MM", "WM"),
        particle("mu+", "mu-", -13, 2, 1, 1.0, "MM", "WM"),
    ]

    def vertex(names, order):
        return NS(particles=names, coupling_orders=((order, 1),))

    vertices = [
        vertex(("g", "g", "g"), "QCD"),
        vertex(("t~", "t", "g"), "QCD"),
        vertex(("u~", "u", "g"), "QCD"),
        vertex(("t~", "t", "a"), "QED"),
        vertex(("u~", "u", "a"), "QED"),
        vertex(("mu+", "mu-", "a"), "QED"),
        vertex(("b~", "t", "W-"), "QED"),
        vertex(("t~", "b", "W+"), "QED"),
        vertex(("b~", "u", "W-"), "QED"),
        vertex(("u~", "b", "W+"), "QED"),
    ]
    compiled = NS(ir=NS(particles=particles, parameters=[], vertex_terms=vertices))
    return NS(
        compiled=compiled,
        request=NS(corrections=corrections, fixed_parameters=fixed),
        blocks=NS(
            process=NS(legs=[NS(label=i + 1, pdg=pdg) for i, pdg in enumerate(legs)])
        ),
        unpredicted_sectors=lambda: {},
    )


def _toy_masses(monkeypatch, **values):
    """``ward.slice_masses`` on the toy model: MT 173.3, MW 80.419, MM 0.105
    (or ``values``), the widths from the target's fixed parameters (else 1)."""

    from pyamplicol.loops.v2 import ward

    masses = {"MT": 173.3, "MW": 80.419, "MM": 0.105, **values}

    def slice_masses(target, parameters=None):
        fixed = target.request.fixed_parameters

        def value(name):
            if name in ("ZERO", "0"):
                return 0.0
            if name.startswith("W"):
                return float(fixed.get(name, 1.0))
            return float(masses[name])

        return value

    monkeypatch.setattr(ward, "slice_masses", slice_masses)


def _gauge(legs):
    return [i + 1 for i, pdg in enumerate(legs) if pdg in (21, 22)]


@pytest.mark.loop_fast
def test_unstable_external_legs_are_found_from_the_model_spectrum(monkeypatch):
    """The unstable legs of the Ward check (module docstrings of ``ward`` and
    ``checks``, "Unstable external legs"): legs charged under the substituted
    boson (coloured for a gluon, charged for a photon), massive, of zero
    width, with an open two-body channel among the three-point vertices of
    a requested correction's order; the antiquark's channel is the
    conjugate one."""

    from pyamplicol.loops.v2 import ward

    _toy_masses(monkeypatch)
    zero = {"WT": "0", "WM": "0"}
    both = ("QCD", "QED")

    def found(legs, corrections=both, fixed=zero):
        target = _toy_target(legs, corrections, fixed)
        return ward.unstable_external_legs(target, _gauge(legs))

    top, antitop = found([21, 21, 6, -6])
    assert (top.leg, top.particle, top.channel) == (3, "t", ("W+", "b"))
    assert (antitop.leg, antitop.particle, antitop.channel) == (4, "t~", ("W-", "b~"))
    assert top.threshold == pytest.approx(80.419) and top.mass == pytest.approx(173.3)
    assert "leg 3 (t, mass 173.3) decays to W+ b" in top.describe()
    # A photon leg constrains the charged legs; QED corrections alone.
    assert [leg.leg for leg in found([22, 6, -6], ("QED",))] == [2, 3]
    # QCD-only corrections: t -> W b is no cut of a QCD loop.
    assert found([21, 21, 6, -6], ("QCD",)) == ()
    # A width, massless quarks, a muon without an open channel.
    assert found([21, 21, 6, -6], both, {"WM": "0", "WT": "1.4"}) == ()
    assert found([2, -2, 21, 22]) == ()
    assert found([22, 22, 13, -13]) == ()
    # Below the threshold the top is stable.
    _toy_masses(monkeypatch, MT=75)
    assert found([21, 21, 6, -6]) == ()


@pytest.mark.loop_fast
def test_ward_is_not_applicable_only_without_a_stabilised_spectrum(monkeypatch):
    """The USER ruling 2026-11-10 ~00:17 ("ignore ward check there"),
    refined: an unstable external leg makes the Ward rows "not applicable"
    only where no stabilised spectrum exists; with one they are checked; a
    stable top is checked as any process."""

    from pyamplicol.loops.v2 import checks, ward

    _toy_masses(monkeypatch)
    target = _toy_target([21, 21, 6, -6], ("QCD", "QED"), {"WT": "0"})
    monkeypatch.setattr(
        ward, "stabilised_parameters", lambda *a, **k: (None, "no input to move")
    )
    reason = checks.ward_applicability(target, [1, 2])
    assert reason.startswith("legs 1, 2: unstable external leg: leg 3 (t, mass 173.3)")
    assert "no admissible stabilised spectrum (no input to move)" in reason
    assert "the stable comparison is unavailable" in reason
    monkeypatch.setattr(
        ward, "stabilised_parameters", lambda *a, **k: ({"MW": "180"}, None)
    )
    assert checks.ward_applicability(target, [1, 2]) is None
    assert checks.ward_plan(target, [1, 2])[1] == {"MW": "180"}
    _toy_masses(monkeypatch, MT=75)
    assert checks.ward_plan(target, [1, 2]) == ((), {}, None)


@pytest.mark.loop_fast
def test_instability_is_decided_per_substituted_leg(monkeypatch):
    """u b~ > g a w+ with QED corrections (toy model: a massless u b W
    vertex): the W carries no colour, so the gluon leg's rows are checked
    as any process; the photon sees the unstable W (W+ -> u b~ open) and,
    without a stabilised spectrum, its rows alone are not applicable."""

    from pyamplicol.loops.v2 import checks, ward

    _toy_masses(monkeypatch)
    target = _toy_target([2, -5, 21, 22, 24], ("QCD", "QED"), {"WW": "0"})
    assert ward.unstable_external_legs(target, [3]) == ()
    (w,) = ward.unstable_external_legs(target, [4])
    assert (w.leg, w.particle, w.channel) == (5, "W+", ("b~", "u"))
    monkeypatch.setattr(
        ward, "stabilised_parameters", lambda *a, **k: (None, "it moves leg 5")
    )
    groups = checks.ward_groups(target, [3, 4])
    assert groups == [
        ([3], (), {}, None, ""),
        ([4], (w,), None, "it moves leg 5", ""),
    ]
    reason = checks.ward_applicability(target, [3, 4])
    assert reason.startswith("leg 4: unstable external leg: leg 5 (W+, mass 80.419)")
    assert checks.ward_applicability(target, [3]) is None


@pytest.mark.loop_fast
def test_without_an_admissible_stabilised_spectrum_only_the_finite_part_is_excused(
    monkeypatch,
):
    """The Born-interfered rows of a request with an unstable external leg
    and no admissible stabilised spectrum (the USER ruling 2026-11-10,
    refined): the Ward rows are evaluated at the requested spectrum; a
    failing finite coefficient makes its row "not applicable" with the
    reason, the Born and the poles still judged (a planted Born residual
    fails); the process passes otherwise. The loop-induced Ward probes are
    not applicable for such a leg."""

    from types import SimpleNamespace as NS

    from pyamplicol.loops.v2 import checks, induced, plan_export, stability, ward

    sector = (("QCD", 4),)
    estimate = NS(
        relative=1e-12,
        absolute={sector: NS(coefficients=[0.0, 1e-12, 1e-12])},
        scale={sector: NS(coefficients=[1.0, 1.0, 1.0])},
    )

    def evaluate(_executor, _point, _scale, carrier, checks_):
        assert (
            carrier.arithmetic == "double" and checks_ is stability.RECOMMENDED_CHECKS
        )
        return _pole_result(sector, (0.0, 2.0, -3.0), (2.0, -3.0), stability=estimate)

    def scripted(born_residual):
        def ward_check(_executor, _point, _scale, _name, *, legs, factors, **options):
            assert options.get("parameters") is None
            physical = NS(
                components={"virtual": {sector: _laurent(0.05, 2.0, -3.0)}},
                born={sector: 1.0},
                loop_born=None,
                stability=None,
                ir_poles={sector: (2.0, -3.0)},
            )
            labels = [(leg, factor) for leg in legs for factor in factors]
            results = [
                NS(
                    components={
                        "virtual": {
                            sector: _laurent(
                                4e-4 if tuple(factor) == (1, 0) else 0.0, 0.0, 0.0
                            )
                        }
                    },
                    born={sector: 1.0},
                    loop_born={sector: born_residual},
                    stability=None,
                )
                for _leg, factor in labels
            ]
            return {
                "physical": physical,
                "results": results,
                "rows": [{"leg": leg, "factor": factor} for leg, factor in labels],
            }

        return ward_check

    monkeypatch.setattr(plan_export, "NativeExecutor", lambda *a, **k: None)
    monkeypatch.setattr(checks, "_evaluate", evaluate)
    monkeypatch.setattr(ward, "gauge_legs", lambda _target: (1, 2))
    monkeypatch.setattr(induced, "goldstone_applicability", lambda _t: "n/a")
    monkeypatch.setattr(checks, "_improved", lambda *a: (None, None))
    _toy_masses(monkeypatch)
    monkeypatch.setattr(
        ward, "stabilised_parameters", lambda *a, **k: (None, "no input to move")
    )
    target = _toy_target([21, 21, 6, -6], ("QCD", "QED"), {"WT": "0"})
    carriers = (NS(arithmetic="double"), NS(arithmetic="double-double"))
    monkeypatch.setattr(ward, "ward_check", scripted(0.0))
    rows = checks.born_interfered_rows(target, [(None, 1)], carriers)
    ward_rows = {row.subject: row for row in rows if row.check == "ward"}
    assert set(ward_rows) == {f"leg {leg}, c = {c}" for leg in (1, 2) for c in "1i"}
    for leg in (1, 2):
        excused = ward_rows[f"leg {leg}, c = 1"]
        assert excused.verdict == checks.NOT_APPLICABLE
        assert (
            "requested spectrum: Born, poles: pass; finite: not applicable; "
            "stabilised spectrum: unavailable"
        ) in excused.reason
        assert "no admissible stabilised spectrum (no input to move)" in excused.reason
        assert ward_rows[f"leg {leg}, c = i"].verdict == checks.PASS
    process = checks.ProcessCheck(
        "p", "g g > t t~", "virtual", "zero", (), "ninjars", tuple(rows), 0.0
    )
    assert process.status == checks.PASSED
    # A planted Born residual at the requested spectrum fails.
    monkeypatch.setattr(ward, "ward_check", scripted(0.0995))
    rows = checks.born_interfered_rows(target, [(None, 1)], carriers)
    assert {row.verdict for row in rows if row.check == "ward"} == {checks.FAIL}
    # Loop-induced: the Ward probes are not evaluated (no legs probed).
    probed = []

    def point_probes(_executor, _point, _scale, legs, _carriers, _floors, **_options):
        probed.append(list(legs))
        return [{"probe": "finiteness", "carrier": "double"}], [
            induced.ProbeResult("finiteness", {})
        ]

    monkeypatch.setattr(induced, "probe_legs", lambda _target: [1, 2])
    monkeypatch.setattr(induced, "probe_floors", lambda *a: ({}, {}))
    monkeypatch.setattr(induced, "point_probes", point_probes)
    target.amplitude = NS(colour_zero=False)
    rows = checks.induced_rows(target, None, None, None, [(None, 1)], carriers)
    assert probed == [[]]
    assert [row.check for row in rows] == ["poles", "ward", "goldstone"]
    assert rows[1].verdict == checks.NOT_APPLICABLE
    assert rows[1].reason.startswith("legs 1, 2 not checked: unstable external leg")


def _scripted_poles(monkeypatch, script):
    """``checks._evaluate`` replaced by ``script(carrier)`` -> the 1/eps
    coefficient of one sector whose Catani 1/eps pole is 2 (1/eps^2: -3,
    always exact; S = 2 for the 1/eps row); the calls are recorded as
    (carrier name, digits, checked)."""

    from pyamplicol.loops.v2 import checks, induced, plan_export, ward

    sector = (("QED", 4),)
    calls = []

    def evaluate(_executor, _point, _scale, carrier, checks_):
        calls.append((carrier.arithmetic, carrier.digits, checks_ is not None))
        single = script(carrier)
        if isinstance(single, Exception):
            raise single
        return _pole_result(sector, (0.0, single, -3.0), (2.0, -3.0))

    monkeypatch.setattr(plan_export, "NativeExecutor", lambda *a, **k: None)
    monkeypatch.setattr(checks, "_evaluate", evaluate)
    monkeypatch.setattr(ward, "gauge_legs", lambda _target: ())
    monkeypatch.setattr(induced, "goldstone_applicability", lambda _t: "n/a")
    return calls


def _rung_rows(rows):
    return {row.subject: row for row in rows if row.check == "poles"}


@pytest.mark.loop_fast
def test_the_ladder_takes_a_row_to_arbitrary_precision_until_it_passes(
    monkeypatch,
):
    """Point 0: binary64 and double-double miss R < K S on 1/eps (R / S 1e-6
    and 1e-9 at K 1e-10); the row alone runs in arbitrary precision at twice
    double-double's digits (64; the point lifted for it) and passes there.
    Point 1 passes in binary64: no other carrier runs. The 1/eps^2 row keeps
    its binary64 pass."""

    from types import SimpleNamespace as NS

    from pyamplicol.loops.v2 import checks
    from pyamplicol.loops.v2.assemble import Precision

    def script(carrier):
        if carrier.arithmetic == "double":
            return 2.0 * (1 + 1e-6) if script.point == 0 else 2.0
        if carrier.arithmetic == "double-double":
            return 2.0 * (1 + 1e-9)
        return 2.0 * (1 + 1e-30)

    calls = _scripted_poles(monkeypatch, script)
    lifted = []

    def lift(index, carrier):
        lifted.append((index, carrier.digits))
        return (f"point {index} at {carrier.working_digits}", 1)

    rung = checks.Rung(lift)
    carriers = (Precision.double(), Precision.double_double())
    target = NS(unpredicted_sectors=lambda: {})
    rows = []
    with checks.tolerating(1e-10):
        for point in (0, 1):
            script.point = point
            rows.append(
                checks.born_interfered_rows(target, [(None, 1)], carriers, rung)
            )
    first, second = _rung_rows(rows[0]), _rung_rows(rows[1])
    single = first["QED^4 1/eps"]
    assert (single.verdict, single.carrier, single.digits) == (
        checks.PASS,
        "arbitrary",
        64,
    )
    assert single.fallback == (
        "double: fail, R / physical 1e-06; double-double: fail, R / physical 1e-09"
    )
    assert single.deviation == pytest.approx(1e-30)
    assert first["QED^4 1/eps^2"].carrier == "double"
    assert first["QED^4 1/eps^2"].verdict == checks.PASS
    assert lifted == [(0, 64)]
    assert calls == [
        ("double", None, True),
        ("double-double", None, False),
        ("arbitrary", 64, False),
        ("double", None, True),
    ]
    assert {row.carrier for row in second.values()} == {"double"}
    assert checks.rung_digits(Precision.double_double().unit_roundoff) == 64


@pytest.mark.loop_fast
def test_a_row_still_failing_in_arbitrary_precision_fails_its_process(
    monkeypatch,
):
    """A row that misses R < K S in every carrier, arbitrary precision
    included, fails (exit 1) with the arbitrary carrier's R / S;
    ``check.arbitrary_digits`` sets the digits; an explicit carrier runs no
    rung; a refused arbitrary-precision run leaves the row inconclusive."""

    from types import SimpleNamespace as NS

    from pyamplicol.loops.v2 import checks, plan_export
    from pyamplicol.loops.v2.assemble import Precision

    target = NS(unpredicted_sectors=lambda: {})
    carriers = (Precision.double(), Precision.double_double())
    rung = checks.Rung(lambda index, carrier: (None, 1))

    def wrong(carrier):
        return 2.0 * (1 + 1e-3)

    _scripted_poles(monkeypatch, wrong)
    with checks.tolerating(1e-5):
        rows = checks.born_interfered_rows(target, [(None, 1)], carriers, rung)
    row = _rung_rows(rows)["QED^4 1/eps"]
    assert (row.verdict, row.carrier, row.digits) == (checks.FAIL, "arbitrary", 64)
    assert row.deviation == pytest.approx(0.002 / 2.002, rel=1e-3)
    process = checks.ProcessCheck(
        "p", "u u~ > a a", "virtual", "zero", (), "ninjars", tuple(rows), 0.0
    )
    assert process.status == checks.FAILED
    report = checks.CheckReport(
        "x", "card", 1, 0, "auto", ("double",), (process,), "", 0.0
    )
    assert report.exit_code == checks.EXIT_FAILED

    calls = _scripted_poles(monkeypatch, wrong)
    option = checks.Rung(lambda index, carrier: (None, 1), digits=60)
    with checks.tolerating(1e-5):
        rows = checks.born_interfered_rows(target, [(None, 1)], carriers, option)
    assert _rung_rows(rows)["QED^4 1/eps"].digits == 60
    assert ("arbitrary", 60, False) in calls

    calls = _scripted_poles(monkeypatch, wrong)
    explicit = (Precision.double_double(),)
    with checks.tolerating(1e-5):
        rows = checks.born_interfered_rows(target, [(None, 1)], explicit)
    row = _rung_rows(rows)["QED^4 1/eps"]
    assert row.verdict == checks.FAIL and row.carrier == "double-double"
    assert all(carrier != "arbitrary" for carrier, _digits, _checked in calls)

    def refused(carrier):
        if carrier.arithmetic == "arbitrary":
            return plan_export.FailedPoints([None], {0: ["no arbitrary lane"]})
        return 2.0 * (1 + 1e-3)

    _scripted_poles(monkeypatch, refused)
    with checks.tolerating(1e-5):
        rows = checks.born_interfered_rows(target, [(None, 1)], carriers, rung)
    row = _rung_rows(rows)["QED^4 1/eps"]
    assert row.verdict == checks.INCONCLUSIVE
    assert "arbitrary refused" in row.reason
    # A loop-induced probe: its verdict is its rows' (the threshold rule).
    from pyamplicol.loops.v2.induced import ProbeResult

    def probe(residue, physical=1.0, terms=1.0):
        measure = checks.Measure("k k=0", residue, physical, terms)
        return ProbeResult(
            "ward", {("k", 0): checks.judge(measure, 1e-5)}, tolerance=1e-5
        )

    failed = checks._probe_row(
        {"probe": "ward", "leg": 1, "carrier": "double-double"}, probe(1e-3), 0
    )
    assert failed.verdict == checks.FAIL and failed.deviation == pytest.approx(1e-3)
    passed = checks._probe_row(
        {"probe": "ward", "leg": 1, "carrier": "double"}, probe(1e-13), 0
    )
    assert passed.verdict == checks.PASS and passed.scale_by == "physical"
    undefined = checks._probe_row(
        {"probe": "ward", "leg": 1, "carrier": "double-double"},
        probe(float("nan")),
        0,
    )
    assert undefined.verdict == checks.INCONCLUSIVE
    assert "cannot be computed" in undefined.reason


@pytest.mark.loop_fast
def test_ward_rows_take_the_rung_by_the_threshold_rule(monkeypatch):
    """A Ward row binary64 and double-double fail (virtual 1e-6 and 4e-22 of
    the physical scale at K 1e-25) is re-run in arbitrary precision at 64
    digits and passes there (1e-30)."""

    from types import SimpleNamespace as NS

    from pyamplicol.loops.v2 import checks, ward
    from pyamplicol.loops.v2.assemble import Precision

    sector = (("QED", 10),)
    calls = []

    def ward_check(_executor, point, _scale, name, *, legs, factors, **options):
        precision = options.get("precision")
        calls.append((precision.arithmetic, precision.digits, options.get("judge")))
        virtual = {"double": 1e-6, "double-double": 4e-22, "arbitrary": 1e-30}
        physical = NS(
            components={"virtual": {sector: _laurent(1.0, 0.0, 0.0)}},
            born={sector: 1.0},
            loop_born=None,
            stability=None,
        )
        result = NS(
            components={
                "virtual": {sector: _laurent(virtual[precision.arithmetic], 0.0, 0.0)}
            },
            born={sector: 1.0},
            loop_born={sector: 0.0},
            stability=None,
        )
        labels = [(leg, factor) for leg in legs for factor in factors]
        return {
            "physical": physical,
            "results": [result] * len(labels),
            "rows": [{"leg": leg, "factor": factor} for leg, factor in labels],
        }

    monkeypatch.setattr(ward, "ward_check", ward_check)
    lifted = []
    rung = checks.Rung(
        lambda index, carrier: lifted.append(carrier.digits) or (None, 1)
    )
    carriers = (Precision.double(), Precision.double_double())
    stages = checks._stages(carriers, rung)

    def at(carrier):
        if carrier.arithmetic == "arbitrary":
            return (*rung.lift(2, carrier), None)
        return None, 1, None

    rows = checks._born_ward_rows(None, 2, stages, at, [5], 1e-25)
    assert len(rows) == 2
    for row in rows:
        assert (row.verdict, row.carrier, row.digits) == (checks.PASS, "arbitrary", 64)
        assert row.fallback == (
            "double: fail, R / physical 1e-06; double-double: fail, R / physical 4e-22"
        )
        # The 1/eps and 1/eps^2 rows (no physical part) take the finite scale.
        assert row.deviation == pytest.approx(1e-30)
    assert lifted == [64]
    assert calls == [
        ("double", None, False),
        ("double-double", None, False),
        ("arbitrary", 64, False),
    ]


@pytest.mark.loop_fast
def test_an_unstable_leg_is_judged_on_the_stabilised_spectrum(monkeypatch):
    """With an unstable external leg (module docstring, "Unstable external
    legs") each (leg, factor) Ward row is evaluated at the requested
    spectrum and on the stabilised one, in two scopes: at the requested
    spectrum the Born and every pole coefficient are judged as always (a
    planted Born or double-pole residual FAILS whatever the stabilised
    spectrum says); only a failing finite coefficient is the unstable leg's
    and is decided by the stabilised spectrum's finite coefficient; any
    stabilised failure fails the row (a broken amplitude still fails)."""

    from types import SimpleNamespace as NS

    from pyamplicol.loops.v2 import checks, ward
    from pyamplicol.loops.v2.assemble import Precision

    sector = (("QCD", 4), ("QED", 2))
    born_sector = (("QCD", 4),)
    calls = []
    stable = {"MW": "180.94275", "MZ": "205.173"}

    def script(requested, stabilised):
        """Per spectrum, per factor: (finite, 1/eps, 1/eps^2, loop-side Born)
        of the Ward evaluation; the physical one is (0.05, 3e-3, 1e-35) with
        Catani's double pole exactly zero and Born 1."""

        def ward_check(_executor, _point, _scale, _name, *, legs, factors, **options):
            parameters = options.get("parameters")
            calls.append(parameters)
            values = requested if parameters is None else stabilised
            physical = NS(
                components={"virtual": {sector: _laurent(0.05, 3e-3, 1e-35)}},
                born={born_sector: 1.0},
                loop_born=None,
                stability=None,
                ir_poles={sector: (3e-3, 0.0)},
            )
            labels = [(leg, factor) for leg, factor in labels_of(legs, factors)]
            results = []
            for _leg, factor in labels:
                finite, single, double, born = values[tuple(factor)]
                results.append(
                    NS(
                        components={
                            "virtual": {sector: _laurent(finite, single, double)}
                        },
                        born={born_sector: 1.0},
                        loop_born={born_sector: born},
                        stability=None,
                    )
                )
            return {
                "physical": physical,
                "results": results,
                "rows": [{"leg": leg, "factor": factor} for leg, factor in labels],
            }

        return ward_check

    def labels_of(legs, factors):
        return [(leg, factor) for leg in legs for factor in factors]

    unstable = (ward.UnstableLeg(3, "t", 173.3, ("W+", "b"), 80.419),)
    stages = checks._stages((Precision.double_double(),), None)

    def at(_carrier):
        return None, 1, None

    def rows(requested, stabilised):
        monkeypatch.setattr(ward, "ward_check", script(requested, stabilised))
        calls.clear()
        found = checks._born_ward_rows(
            None, 0, stages, at, [1], 1e-25, unstable=unstable, stabilised=stable
        )
        assert calls == [None, stable]
        return {row.subject: row for row in found}

    clean = (1e-33, 1e-36, 1e-38, 0.0)
    # g g > t t~ [QED]: the requested c = 1 finite part fails by the
    # unstable top alone, everything else passes (the double pole, zero by
    # Catani, on the floor); the stabilised spectrum passes.
    found = rows(
        {(1, 0): (4e-4, 1e-36, 1e-38, 0.0), (0, 1): clean},
        {(1, 0): clean, (0, 1): clean},
    )
    one, i = found["leg 1, c = 1"], found["leg 1, c = i"]
    assert one.verdict == checks.PASS and i.verdict == checks.PASS
    assert (
        "requested spectrum: Born, poles: pass; finite: inconclusive (unstable "
        "external leg); stabilised spectrum: pass"
    ) in one.reason
    assert "leg 3 (t, mass 173.3) decays to W+ b" in one.reason
    assert (
        "judged on the stabilised spectrum MW = 180.94275, MZ = 205.173" in one.reason
    )
    assert "requested spectrum: Born, poles: pass; finite: pass" in i.reason
    # Residuals planted at the requested spectrum, the stabilised
    # spectrum clean: a Born residual (0.0995 of the Born) and a double-pole
    # residual (0.1 of the finite scale) fail.
    for planted in ((4e-4, 1e-36, 1e-38, 0.0995), (4e-4, 1e-36, 5e-3, 0.0)):
        found = rows({(1, 0): planted, (0, 1): clean}, {(1, 0): clean, (0, 1): clean})
        failed = found["leg 1, c = 1"]
        assert failed.verdict == checks.FAIL, planted
        assert "requested spectrum: Born, poles: fail" in failed.reason
    # A broken amplitude: the finite part fails on both spectra; the
    # stabilised finite coefficient decides it: FAIL.
    found = rows(
        {(1, 0): (4e-4, 1e-36, 1e-38, 0.0), (0, 1): (1e-7, 1e-36, 1e-38, 0.0)},
        {(1, 0): clean, (0, 1): (1e-7, 1e-36, 1e-38, 0.0)},
    )
    assert found["leg 1, c = 1"].verdict == checks.PASS
    broken = found["leg 1, c = i"]
    assert broken.verdict == checks.FAIL
    assert "stabilised spectrum: fail" in broken.reason
    # A row passing at the requested spectrum fails where the stabilised
    # spectrum fails.
    found = rows(
        {(1, 0): clean, (0, 1): clean},
        {(1, 0): (1e-7, 1e-36, 1e-38, 0.0), (0, 1): clean},
    )
    assert found["leg 1, c = 1"].verdict == checks.FAIL
    process = checks.ProcessCheck(
        "p", "g g > t t~", "virtual", "zero", (), "ninjars", tuple(found.values()), 0.0
    )
    assert process.status == checks.FAILED


@pytest.mark.loop_fast
def test_the_floor_excuses_only_a_coefficient_that_vanishes_physically():
    """``_ward_measures``: a pole coefficient Catani predicts exactly zero is
    a known-zero reference on the Born x alpha / (2 pi) floor (rounding
    passes; a planted residual of 0.1 fails); a small but NONZERO pole
    coefficient (a 1/eps of 2.7073e-8 near threshold) keeps its
    own P and T, so a residual of 1 % of it fails at K = 1e-5."""

    from types import SimpleNamespace as NS

    from pyamplicol.loops.v2 import checks

    sector = (("QCD", 4), ("QED", 2))
    born_sector = (("QCD", 4),)

    def measures(physical_poles, ward_values, predicted):
        physical = NS(
            components={"virtual": {sector: _laurent(0.05, *physical_poles)}},
            born={born_sector: 1.0},
            loop_born=None,
            stability=None,
            ir_poles={sector: predicted},
        )
        result = NS(
            components={"virtual": {sector: _laurent(*ward_values)}},
            born={born_sector: 1.0},
            loop_born={born_sector: 0.0},
            stability=None,
        )
        return checks._ward_measures(physical, result)

    def verdict(measure):
        return checks.judge(measure, 1e-5).verdict

    label = f"{checks._sector_name(sector)} 1/eps"
    double = f"{checks._sector_name(sector)} 1/eps^2"
    # The double pole vanishes physically: rounding passes, 0.1 fails.
    found = measures((2.7073e-8, 1e-35), (0.0, 0.0, 1e-35), (2.7073e-8, 0.0))
    assert found[double].zero_reference and verdict(found[double]) == checks.PASS
    found = measures((2.7073e-8, 1e-35), (0.0, 0.0, 0.1), (2.7073e-8, 0.0))
    assert verdict(found[double]) == checks.FAIL
    # The single pole is small but nonzero: no floor, 1 % of it fails.
    found = measures((2.7073e-8, 1e-35), (0.0, 2.7073e-10, 0.0), (2.7073e-8, 0.0))
    assert not found[label].zero_reference
    assert found[label].physical == pytest.approx(2.7073e-8)
    assert verdict(found[label]) == checks.FAIL


# --------------------------------------------------------------- physics


@pytest.mark.loop_physics
def test_a_born_interfered_request_passes_from_card_and_artifact(tmp_path):
    from pyamplicol.api import Generator, ProcessRequest, ProcessSet
    from pyamplicol.api.services import check
    from pyamplicol.config import resolve_config
    from pyamplicol.loops.v2 import checks

    card = _card(tmp_path / "card", "u u~ > g g")
    report = check(card)
    assert report.exit_code == 0 and report.source_kind == "card"
    (process,) = report.processes
    assert process.contribution == "virtual" and process.status == checks.PASSED
    poles = _rows(report, "poles")
    assert {row.subject.split()[-1] for row in poles} == {"1/eps", "1/eps^2"}
    assert all(row.verdict == checks.PASS for row in poles)
    assert all(row.carrier == "double" and row.ratio < 1 for row in poles)
    assert all(row.deviation < row.tolerance == 1e-5 for row in poles)
    # A binary64 rung: no improvement (off by default in binary64).
    assert all(row.kinematics is None for row in poles)
    ward = _rows(report, "ward")
    assert sorted(row.subject for row in ward) == [
        "leg 3, c = 1",
        "leg 3, c = i",
        "leg 4, c = 1",
        "leg 4, c = i",
    ]
    assert all(row.verdict == checks.PASS for row in ward)
    (goldstone,) = _rows(report, "goldstone")
    assert goldstone.verdict == checks.NOT_APPLICABLE and goldstone.reason
    # The generated artifact: its request regenerated from config/effective.toml.
    config = resolve_config(_card(tmp_path / "gen", "u u~ > g g", action="generate"))
    output = Path(config.effective.generation.output)
    Generator(config).generate(
        ProcessSet((ProcessRequest.parse("u u~ > g g", name="p"),)), output
    )
    code, payload = _cli(str(output), "--points", "1")
    assert code == 0 and payload["exit_code"] == 0
    assert payload["source_kind"] == "artifact"
    (entry,) = payload["processes"]
    assert entry["status"] == "passed"
    assert {row["check"] for row in entry["rows"]} == {"poles", "ward", "goldstone"}
    assert set(entry["rows"][0]) >= {
        "check",
        "subject",
        "point",
        "carrier",
        "verdict",
        "ratio",
        "deviation",
        "estimate",
        "tolerance",
        "fallback",
        "reason",
    }


@pytest.mark.loop_physics
def test_the_tolerance_on_the_command_line_changes_the_verdict(tmp_path):
    """u u~ > g g in binary64 alone: every row's R / S is of binary64's
    rounding, so the default K (the requested relative accuracy, 1e-5)
    passes and K = 1e-30 fails every row (exit 1); the report states K."""

    card = _card(tmp_path, "u u~ > g g")
    code, payload = _cli(str(card), "--precision", "double")
    assert code == 0 and payload["tolerance"] == 1e-5
    rows = [
        row
        for row in payload["processes"][0]["rows"]
        if row["check"] in ("poles", "ward")
    ]
    assert rows and all(row["verdict"] == "pass" for row in rows)
    assert all(0 <= row["deviation"] < 1e-10 for row in rows)
    code, payload = _cli(str(card), "--precision", "double", "--tolerance", "1e-30")
    assert code == 1 and payload["tolerance"] == 1e-30
    verdicts = {
        row["verdict"]
        for row in payload["processes"][0]["rows"]
        if row["check"] in ("poles", "ward")
    }
    assert "fail" in verdicts


@pytest.mark.loop_physics
def test_a_loop_induced_request_passes_its_probes(tmp_path):
    from pyamplicol.api.services import check
    from pyamplicol.loops.v2 import checks

    card = _card(tmp_path, "g g > a a", fixed=_nf5(), veto=("t",), points=2)
    report = check(card)
    assert report.exit_code == 0
    (process,) = report.processes
    assert process.contribution == "loop-induced"
    poles, ward = _rows(report, "poles"), _rows(report, "ward")
    assert [row.point for row in poles] == [0, 1]
    assert all(row.subject.startswith("finiteness") for row in poles)
    # One Ward probe per gauge-boson species: the first gluon and photon.
    assert sorted({row.subject for row in ward}) == ["leg 1", "leg 3"]
    for row in poles + ward:
        assert row.verdict == checks.PASS and row.carrier == "double"
        assert row.deviation < row.tolerance and row.fallback is None
    (goldstone,) = _rows(report, "goldstone")
    assert goldstone.verdict == checks.NOT_APPLICABLE


@pytest.mark.loop_physics
def test_a_dropped_r2_vertex_fails_the_ward_check(tmp_path):
    from pyamplicol.api.services import check
    from pyamplicol.loops.v2 import checks

    shipped = Path(
        str(resources.files("pyamplicol").joinpath("assets", "models", "ufo"))
    )
    dropped = tmp_path / "loop_sm_r2_dropped"
    shutil.copytree(shipped / "loop_sm", dropped)
    assert drop_r2_vertex(dropped, [21, 21, 22, 22])
    card = _card(
        tmp_path / "card",
        "g g > a a",
        source=str(dropped),
        fixed=_nf5(),
        veto=("t",),
    )
    report = check(card)
    assert report.exit_code == checks.EXIT_FAILED
    ward = _rows(report, "ward")
    assert ward
    for row in ward:
        # binary64 far beyond K, then double-double too (no rung for the
        # loop-induced probes).
        assert row.verdict == checks.FAIL and row.carrier == "double-double"
        # The double-double rung evaluates its lifted point improved in
        # double-double (m-lit lit-psimprove (G5)); beams along z: MadLoop's
        # z-shift (the default) produces it.
        assert row.kinematics == "z-shift", row
        assert row.fallback.startswith("double: fail, R / physical")
        assert float(row.fallback.split()[-1]) > 10 * row.tolerance
        assert row.deviation > 10 * row.tolerance
    # R2 is finite: the finiteness probe passes.
    assert all(row.verdict == checks.PASS for row in _rows(report, "poles"))
    code, payload = _cli(str(card))
    assert code == 1 and payload["exit_code"] == 1
    assert payload["processes"][0]["status"] == "failed"
    # The report names the card it checked.
    assert payload["source"] == str(card.resolve())
    assert payload["source_kind"] == "card"


@pytest.mark.loop_physics
def test_an_artifact_is_checked_on_its_stored_processes_and_model(tmp_path):
    """The artifact's configuration names u u~ > g g, the API call generated
    g g > a a (``api_p``) from a copy of loop_sm given by path: check takes
    the stored process; the copy's name alone (``effective.toml``) does not
    resolve, a model that is not the stored one is refused."""

    from pyamplicol.api import ArtifactError, Generator, ProcessRequest, ProcessSet
    from pyamplicol.api.services import check
    from pyamplicol.config import resolve_config
    from pyamplicol.loops.v2 import checks

    shipped = Path(
        str(resources.files("pyamplicol").joinpath("assets", "models", "ufo"))
    )
    copy = tmp_path / "loop_sm_copy"
    shutil.copytree(shipped / "loop_sm", copy)
    card = _card(
        tmp_path / "gen",
        "u u~ > g g",
        source=str(copy),
        fixed=_nf5(),
        veto=("t",),
        action="generate",
    )
    config = resolve_config(card)
    output = Path(config.effective.generation.output)
    Generator(config).generate(
        ProcessSet((ProcessRequest.parse("g g > a a", name="api_p"),)), output
    )
    # effective.toml keeps the UFO directory's name only.
    with pytest.raises(ArtifactError, match="cannot be resolved"):
        check(output, points=1)
    code, payload = _cli(str(output), "--points", "1", "--model", str(copy))
    assert code == 0 and payload["source_kind"] == "artifact"
    (entry,) = payload["processes"]
    assert entry["process"] == "api_p" and entry["contribution"] == "loop-induced"
    assert entry["status"] == checks.PASSED
    # Another model (the copy without an R2 vertex): not the stored one.
    dropped = tmp_path / "loop_sm_r2_dropped"
    shutil.copytree(shipped / "loop_sm", dropped)
    assert drop_r2_vertex(dropped, [21, 21, 22, 22])
    with pytest.raises(ArtifactError, match="not the artifact's stored model"):
        check(output, points=1, model=str(dropped))


@pytest.mark.loop_physics
def test_nothing_to_check_exits_with_its_own_code(tmp_path):
    """h > g a: every loop has one coloured attachment (Tr T^a = 0), an exact
    colour zero; nothing is checked, which is no pass (exit 3)."""

    from pyamplicol.loops.v2 import checks

    card = _card(tmp_path, "h > g a", fixed={"WT": "0", "WH": "0"})
    code, payload = _cli(str(card))
    assert code == checks.EXIT_NOTHING_CHECKED == payload["exit_code"]
    (entry,) = payload["processes"]
    assert entry["status"] == "nothing checked"
    assert {row["verdict"] for row in entry["rows"]} == {"not applicable"}


@pytest.mark.loop_physics
def test_an_untagged_photon_under_the_complex_mass_scheme_with_a_top_width(tmp_path):
    """u u~ > a a with QED corrections, complex-mass scheme, WT != 0, the
    photons untagged: the QED pole prediction's gamma_gamma counts the
    massless charged fermions only; the top's complex pole mass makes it a
    massive internal species (it raised the untyped cms-external-width
    ValueError before, DECISIONS 2026-11-09 22:40 side item (b)). Both poles
    pass at both points, so the top is not counted."""

    from pyamplicol.api.services import check
    from pyamplicol.loops.v2 import checks

    tmp_path.mkdir(parents=True, exist_ok=True)
    card = tmp_path / "card.toml"
    card.write_text(
        """action = "check"
[model]
source = "loop_qcd_qed_sm_Gmu"
restriction = "default"
[process]
entries = [{expression = "u u~ > a a", name = "p"}]
loop_coupling_orders = ["QED"]
coupling_order_policy = "explicit"
max_coupling_orders = { QCD = 0, QED = 2 }
[loop]
external_photons = "none"
[loop.preparation]
fixed_parameters = { MB = "0", MTA = "0", WT = "1.37758", WZ = "2.49877", \
WW = "2.09291", WH = "0.00407468" }
[loop.model.scheme]
mass_scheme = "complex-mass"
[check]
points = 2
"""
    )
    report = check(card)
    assert report.exit_code == checks.EXIT_PASSED
    poles = _rows(report, "poles")
    assert len(poles) == 2 * 2 and all(row.verdict == checks.PASS for row in poles)
