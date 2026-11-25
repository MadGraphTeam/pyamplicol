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
    # S = max(P, K T): P decides a resolved row, K T guards an unresolved
    # one (there R < K^2 T); a row without any term is vacuous.
    assert checks.scale_of(2.0, 10.0, 1e-5) == (2.0, "P")
    assert checks.scale_of(1e-7, 10.0, 1e-5) == (1e-4, "K T")
    assert checks.scale_of(None, 1.0, 1e-5) == (None, None)
    measure = checks.Measure
    assert checks.judge(measure("x", 1e-6, 1.0, 1e5, None), 1e-5) == checks.PASS
    assert checks.judge(measure("x", 1e-3, 1.0, 1e5, None), 1e-5) == checks.FAIL
    assert checks.judge(measure("x", 0.0, 0.0, 0.0, None), 1e-5) == checks.VACUOUS
    assert checks.judge(measure("x", 1e-30, 0.0, 0.0), 1e-5) == checks.INCONCLUSIVE
    assert checks.judge(measure("x", 0.0, None, 1.0), 1e-5) == checks.INCONCLUSIVE
    # A row every part of which is vacuous; a process of vacuous rows passes.
    row = checks._judged_row(
        "poles", "x", 0, "double", [measure("x", 0.0, 0.0, 0.0)], 1e-5
    )
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
    """Pole rows: R = |Re V_k - Re C_k| against S = the largest of |C_k| and
    the sector's coefficient k in the virtual and its parts; a planted
    violation fails, K changes the verdict, a non-finite coefficient is
    inconclusive, a vanishing prediction with no part is measured against
    the next lower coefficient, and a sector without a pole row is listed
    "no prediction" (or "not run" where predicted), never omitted. Ward
    rows: every Born sector and every virtual sector and coefficient judged
    on its own; a sector or coefficient only one evaluation has is a missing
    operand (inconclusive)."""

    from types import SimpleNamespace as NS

    from pyamplicol.loops.v2 import checks

    first, second = (("QCD", 4),), (("QCD", 2), ("QED", 2))
    exact = _pole_result(first, (0.5, 2.0, -3.0), (2.0, -3.0))
    rows = checks._pole_rows(exact, 0, "double", 1e-5)
    assert {row.verdict for row in rows.values()} == {checks.PASS}
    assert all(row.deviation == 0 and row.tolerance == 1e-5 for row in rows.values())
    # A planted violation of 1e-3 relative on the 1/eps pole.
    planted = _pole_result(first, (0.5, 2.002, -3.0), (2.0, -3.0))
    rows = checks._pole_rows(planted, 0, "double", 1e-5)
    assert rows[(first, 1)].verdict == checks.FAIL
    # S = max(|C|, |V|) = 2.002.
    assert rows[(first, 1)].deviation == pytest.approx(0.002 / 2.002, rel=1e-3)
    assert rows[(first, 2)].verdict == checks.PASS
    # K changes the verdict.
    assert checks._pole_rows(planted, 0, "double", 1e-2)[(first, 1)].verdict == (
        checks.PASS
    )
    # S = max(P, K T): P = max(|C|, |V|) decides; a bare part of 20 is T and
    # only guards (K T = 2e-4 < P); a part of 1e6 sets S (K T = 10 > P).
    parted = _pole_result(
        first, (0.5, 2.002, -3.0), (2.0, -3.0), parts={"bare": (1.0, 20.0, -3.0)}
    )
    row = checks._pole_rows(parted, 0, "double", 1e-5)[(first, 1)]
    assert (row.scale_by, row.physical, row.terms) == ("P", 2.0, 20.0)
    assert row.deviation == pytest.approx(0.002 / 2.002, rel=1e-3)
    assert row.verdict == checks.FAIL and row.residue == pytest.approx(2e-3)
    cancelled = _pole_result(
        first, (0.5, 2.002, -3.0), (2.0, -3.0), parts={"bare": (1.0, 1e6, -3.0)}
    )
    row = checks._pole_rows(cancelled, 0, "double", 1e-5)[(first, 1)]
    assert row.scale_by == "K T" and row.deviation == pytest.approx(2e-4, rel=1e-3)
    # A non-finite coefficient: inconclusive, never a raise or a pass.
    broken = _pole_result(first, (0.5, float("nan"), -3.0), (2.0, -3.0))
    rows = checks._pole_rows(broken, 0, "double", 1e-5)
    assert rows[(first, 1)].verdict == checks.INCONCLUSIVE
    assert "cannot be computed" in rows[(first, 1)].reason
    # A double pole neither the prediction nor any part has (only massive
    # coloured legs): vacuous, nothing to test.
    massive = _pole_result(first, (0.5, 2.0, 0.0), (2.0, 0.0))
    row = checks._pole_rows(massive, 0, "double", 1e-5)[(first, 2)]
    assert (row.verdict, row.vacuous) == (checks.VACUOUS, 1)
    # A spurious double pole: S is its own size (the virtual is a part), so
    # R / S = 1 and it fails at any K below 1.
    spurious = _pole_result(first, (0.5, 2.0, 1e-3), (2.0, 0.0))
    row = checks._pole_rows(spurious, 0, "double", 1e-5)[(first, 2)]
    assert row.verdict == checks.FAIL and row.deviation == pytest.approx(1.0)
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
    assert [m.label for m in measures] == [
        "Born QCD^4",
        "QCD^4 finite",
        "QCD^4 1/eps",
        "QCD^4 1/eps^2",
    ]
    row = checks._judged_row("ward", "leg 1, c = 1", 0, "double", measures, 1e-5)
    # The double pole has no physical term (T = 0) and R = 0: vacuous.
    assert row.verdict == checks.PASS and row.deviation == pytest.approx(5e-17)
    assert row.vacuous == 1 and row.scale_by == "P"
    planted = evaluation((1e-16, 1e-3, 0.0), {first: 4.0}, {first: 1e-16})
    row = checks._judged_row(
        "ward",
        "leg 1, c = 1",
        0,
        "double",
        checks._ward_measures(physical, planted),
        1e-5,
    )
    assert row.verdict == checks.FAIL and row.deviation == pytest.approx(1e-3)
    # A short Laurent tuple, a missing sector, a missing loop-side Born.
    short = evaluation((1e-16, 1e-17), {first: 4.0}, {first: 0.0})
    other = evaluation((0.0, 0.0, 0.0), {first: 4.0}, {first: 0.0}, sectors=(second,))
    none = evaluation((0.0, 0.0, 0.0), {first: 4.0}, None)
    for substituted in (short, other, none):
        row = checks._judged_row(
            "ward",
            "leg 1, c = 1",
            0,
            "double",
            checks._ward_measures(physical, substituted),
            1e-5,
        )
        assert row.verdict == checks.INCONCLUSIVE, substituted
    # A Born sector that vanishes at this point (a colour zero) on both sides
    # is vacuous; a loop-side residue there has no reference (no cross-row
    # fallback): inconclusive, never a pass.
    zero = evaluation((2.0, 1.0, 0.5), {first: 4.0, second: 0.0})
    measures = checks._ward_measures(
        zero, evaluation((2.0, 1.0, 0.5), {}, {first: 0.0, second: 0.0})
    )
    assert [checks.judge(m, 1e-5) for m in measures if m.label.startswith("Born")] == [
        checks.PASS,
        checks.VACUOUS,
    ]
    measures = checks._ward_measures(
        zero, evaluation((0.0, 0.0, 0.0), {}, {first: 0.0, second: 1e-3})
    )
    (born,) = [m for m in measures if m.label == "Born QCD^2 QED^2"]
    assert (born.residue, born.physical, born.terms) == (1e-3, 0.0, 0.0)
    assert checks.judge(born, 1e-5) == checks.INCONCLUSIVE


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
        assert "at double" in row.reason, row
    (double_pole,) = [row for row in rows if row.subject == "QCD^4 1/eps^2"]
    assert double_pole.verdict == checks.PASS


def _toy_target(legs, corrections, fixed):
    """A probe-slice stand-in on a toy model (records): a gluon, a photon,
    a massive top (MT, width WT), a massless up quark, a massive muon (MM,
    width WM) whose orders are QCD (the gluon's vertices) and QED."""

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


@pytest.mark.loop_fast
def test_ew_corrections_with_a_zero_width_massive_quark_make_ward_not_applicable():
    """The class of the USER ruling 2026-11-10 ~00:17 from the request's own
    data: corrections other than the strong one (identified by the gluon's
    vertices) and an external massive quark with zero width (an antiquark's
    record carries colour -3). No sector split exists: the class takes the
    process's whole (leg, factor) Ward rows."""

    from pyamplicol.loops.v2 import checks

    zero = {"WT": "0", "WM": "0"}
    both = ("QCD", "QED")
    reason = checks.ward_applicability(_toy_target([21, 21, 6, -6], both, zero))
    assert reason and "QED" in reason and "(legs 3, 4)" in reason
    # An antiquark as the only external massive quark.
    reason = checks.ward_applicability(_toy_target([21, 2, 2, -6], both, zero))
    assert reason and "(leg 4)" in reason
    # QED corrections alone (no strong one) with an external top.
    assert checks.ward_applicability(_toy_target([22, 6, -6], ("QED",), zero))
    # Outside the class: QCD-only corrections with external tops; EW
    # corrections with massless quarks only, or a massive colour-singlet
    # fermion; a massive quark whose width is not zero.
    for legs, corrections, fixed in (
        ([21, 21, 6, -6], ("QCD",), zero),
        ([2, -2, 21, 22], both, zero),
        ([22, 22, 13, -13], both, zero),
        ([21, 21, 6, -6], both, {"WM": "0"}),
    ):
        target = _toy_target(legs, corrections, fixed)
        assert checks.ward_applicability(target) is None, (legs, corrections)


@pytest.mark.loop_fast
def test_a_process_in_the_class_reports_one_not_applicable_ward_row(monkeypatch):
    """The Born-interfered rows of an in-class request: its passing poles,
    one "not applicable" Ward row naming the legs and the reason, the Ward
    evaluation never called; the process passes (the row is neutral). The
    loop-induced rows probe finiteness only, with the same Ward row."""

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

    def never(*_args, **_options):
        raise AssertionError("the Ward evaluation runs for a not-applicable class")

    monkeypatch.setattr(plan_export, "NativeExecutor", lambda *a, **k: None)
    monkeypatch.setattr(checks, "_evaluate", evaluate)
    monkeypatch.setattr(ward, "ward_check", never)
    monkeypatch.setattr(ward, "gauge_legs", lambda _target: (1, 2))
    monkeypatch.setattr(induced, "goldstone_applicability", lambda _t: "n/a")
    target = _toy_target([21, 21, 6, -6], ("QCD", "QED"), {"WT": "0"})
    carriers = (NS(arithmetic="double"), NS(arithmetic="double-double"))
    rows = checks.born_interfered_rows(target, [(None, 1)], carriers)
    (row,) = [row for row in rows if row.check == "ward"]
    assert row.verdict == checks.NOT_APPLICABLE and row.point is None
    assert row.reason.startswith("legs 1, 2 not checked: EW corrections (QED)")
    assert "(legs 3, 4)" in row.reason
    poles = [row for row in rows if row.check == "poles"]
    assert len(poles) == 2 and {row.verdict for row in poles} == {checks.PASS}
    process = checks.ProcessCheck(
        "p", "g g > t t~", "virtual", "zero", (), "ninjars", tuple(rows), 0.0
    )
    assert process.status == checks.PASSED
    # Loop-induced: the Ward probes are not evaluated (no legs probed).
    probed = []

    def point_probes(_executor, _point, _scale, legs, _carriers, _floors, **_options):
        probed.append(list(legs))
        return [{"probe": "finiteness", "carrier": "double"}], [
            induced.ProbeResult("finiteness", {"k": 0.1})
        ]

    monkeypatch.setattr(induced, "probe_legs", lambda _target: [1, 2])
    monkeypatch.setattr(induced, "probe_floors", lambda *a: ({}, {}))
    monkeypatch.setattr(induced, "point_probes", point_probes)
    target.amplitude = NS(colour_zero=False)
    rows = checks.induced_rows(target, None, None, None, [(None, 1)], carriers)
    assert probed == [[]]
    assert [row.check for row in rows] == ["poles", "ward", "goldstone"]
    assert rows[1].verdict == checks.NOT_APPLICABLE
    assert rows[1].reason.startswith("legs 1, 2 not checked: EW corrections")


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
    assert single.fallback.startswith("double-double: R / S 1e-09 not below K")
    assert single.deviation == pytest.approx(1e-30)
    assert first["QED^4 1/eps^2"].carrier == "double"
    assert first["QED^4 1/eps^2"].verdict == checks.PASS
    assert lifted == [(0, 64)]
    assert calls == [
        ("double", None, True),
        ("double-double", None, False),
        ("arbitrary", 64, True),
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
    assert ("arbitrary", 60, True) in calls

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
    assert "arbitrary (64 digits) refused" in row.reason
    # A loop-induced probe: its verdict is the threshold rule's.
    from pyamplicol.loops.v2.induced import ProbeResult

    failed = checks._probe_row(
        {"probe": "ward", "leg": 1, "carrier": "double-double"},
        ProbeResult("ward", {"k": 1e-3}, tolerance=1e-5),
        0,
    )
    assert failed.verdict == checks.FAIL
    passed = checks._probe_row(
        {"probe": "ward", "leg": 1, "carrier": "double"},
        ProbeResult("ward", {"k": 1e-13}, tolerance=1e-5),
        0,
    )
    assert passed.verdict == checks.PASS
    undefined = checks._probe_row(
        {"probe": "ward", "leg": 1, "carrier": "double-double"},
        ProbeResult("ward", {"k": 1e-13}, undefined=("k k=0: R nan",), tolerance=1e-5),
        0,
    )
    assert undefined.verdict == checks.INCONCLUSIVE
    assert "R, P or T cannot be computed" in undefined.reason


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
    rows = checks._born_ward_rows(None, None, 1, [5], carriers, 2, 1e-25, rung)
    assert len(rows) == 2
    for row in rows:
        assert (row.verdict, row.carrier, row.digits) == (checks.PASS, "arbitrary", 64)
        assert row.fallback.startswith("double-double: R / S 4e-22 not below K")
        # The 1/eps and 1/eps^2 rows (no physical part) take the finite scale.
        assert row.deviation == pytest.approx(1e-30)
    assert lifted == [64]
    assert calls == [
        ("double", None, False),
        ("double-double", None, False),
        ("arbitrary", 64, False),
    ]


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
        assert row.fallback.startswith("double: fail, largest R / S")
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
