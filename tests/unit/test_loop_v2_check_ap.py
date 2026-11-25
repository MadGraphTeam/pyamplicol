# SPDX-License-Identifier: 0BSD
"""``pyamplicol check`` on real requests for m-lit lit-check (nightly: each
regenerates an electroweak request in memory).

* **The arbitrary-precision rung** (the threshold rule, R < K P): u u~ > d
  d~ a a with QED corrections (QCD 0, QED 4, every width zero, untagged
  photons), the default check (three points from seed 12345) at K =
  1e-28. At the third point the finite and 1/eps rows of the Ward probes
  on legs 5 and 6 miss K in double-double by more than two orders of
  magnitude, as does that point's 1/eps pole row; those rows alone are
  re-run in arbitrary precision at twice double-double's digits (64) and
  pass there far below K. Rows within about two orders of K in
  double-double may go either way across platforms and are not pinned; the
  Born rows of every Ward probe pass in double-double far below K. Every
  row passes; exit 0. At the default K every row passes without the rung.
  About 4 minutes and 10-20 GiB (the probe slice of a 2 -> 4 electroweak
  request and an MPFR Ward batch).
* **Ward rows not applicable** (USER 2026-11-10 ~00:17): g t > t t t~ with
  QCD and QED corrections (lit-ew-blocks census row TT05, external on-shell
  zero-width tops), whose gluon Ward rows failed by 3e8 - 7e8: one "not
  applicable" Ward row naming the class, nothing Ward-evaluated; the 1/eps
  pole row of sector QCD^2 QED^6 passes on its physical scale, its 1/eps^2
  row has no term (R = P = T = 0, vacuous) and QCD^4 QED^4 has no
  prediction; exit 0. About 3 minutes and 9 GiB.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.loop_nightly

WIDTHS = 'WT = "0", WZ = "0", WW = "0", WH = "0"'


def _card(root: Path, body: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    card = root / "card.toml"
    card.write_text('action = "check"\n' + body)
    return card


def test_the_arbitrary_precision_rung_decides_the_two_photon_point(tmp_path):
    from pyamplicol.api.services import check
    from pyamplicol.loops.v2 import checks

    card = _card(
        tmp_path,
        f"""[model]
source = "loop_qcd_qed_sm_Gmu"
restriction = "default"
[process]
entries = [{{expression = "u u~ > d d~ a a", name = "uux_ddxaa"}}]
loop_coupling_orders = ["QED"]
coupling_order_policy = "explicit"
max_coupling_orders = {{ QCD = 0, QED = 4 }}
[loop]
external_photons = "none"
[loop.preparation]
fixed_parameters = {{MB = "0", MTA = "0", {WIDTHS}}}
""",
    )
    tolerance = 1e-28
    report = check(card, seed=12345, tolerance=tolerance)
    assert report.carriers == ("double", "double-double", "arbitrary")
    assert report.tolerance == tolerance
    assert report.exit_code == checks.EXIT_PASSED, report
    (process,) = report.processes
    ward = [row for row in process.rows if row.check == "ward"]
    poles = [row for row in process.rows if row.check == "poles"]
    assert len(ward) == 12 and len(poles) == 6
    assert all(row.verdict == checks.PASS for row in (*ward, *poles))
    # A row reports the carrier of its largest-ratio row; each required
    # row's own deciding carrier is in its record (``cells``).
    cells = [cell for row in ward for cell in row.cells]
    assert all(cell["verdict"] == checks.PASS for cell in cells)
    assert all(
        cell["ratio"] < tolerance
        and cell["carrier"] in ("double", "double-double", "arbitrary")
        for cell in cells
    )
    # The rows that miss K clearly in double-double (at the third point the
    # finite and 1/eps rows of legs 5 and 6, and its 1/eps pole row) are
    # decided by the rung, far below K.
    lifted = [
        cell
        for row in ward
        if row.point == 2 and row.subject.startswith(("leg 5,", "leg 6,"))
        for cell in row.cells
        if cell["label"] in ("QED^10 finite", "QED^10 1/eps")
    ]
    assert len(lifted) == 8
    for cell in lifted:
        assert cell["carrier"] == "arbitrary" and cell["ratio"] < 1e-40, cell
    (pole,) = [r for r in poles if r.point == 2 and r.subject == "QED^10 1/eps"]
    assert pole.carrier == "arbitrary" and pole.digits == 64
    assert pole.deviation < 1e-40 and "double-double: fail" in pole.fallback
    # The rung runs once, at 64 digits.
    assert {r.digits for r in (*ward, *poles) if r.carrier == "arbitrary"} == {64}
    # Rows that pass in double-double far below K are never reported as
    # decided by the rung: every Born row of every Ward probe.
    born = [cell for cell in cells if cell["label"].startswith("Born")]
    assert len(born) == 12
    assert all(cell["carrier"] == "double-double" for cell in born), born


def test_ward_rows_of_ew_corrections_with_external_tops_are_not_applicable(tmp_path):
    from pyamplicol.api.services import check
    from pyamplicol.loops.v2 import checks

    card = _card(
        tmp_path,
        f"""[model]
source = "loop_qcd_qed_sm_Gmu"
restriction = "default"
[process]
entries = [{{expression = "g t > t t t~", name = "tt05"}}]
loop_coupling_orders = ["QCD", "QED"]
coupling_order_policy = "explicit"
max_coupling_orders = {{ QCD = 1, QED = 2 }}
[loop.preparation]
fixed_parameters = {{MB = "0", ymb = "0", MTA = "0", ymtau = "0", {WIDTHS}}}
""",
    )
    report = check(card, points=1, seed=12345)
    assert report.exit_code == checks.EXIT_PASSED, report
    (process,) = report.processes
    (ward,) = [row for row in process.rows if row.check == "ward"]
    assert ward.verdict == checks.NOT_APPLICABLE and ward.point is None
    assert ward.reason.startswith("leg 1 not checked: EW corrections (QED)")
    assert "(legs 2, 3, 4, 5)" in ward.reason
    poles = {row.subject: row for row in process.rows if row.check == "poles"}
    assert {row.verdict for row in poles.values()} == {
        checks.PASS,
        checks.NO_PREDICTION,
        checks.VACUOUS,
    }
    # The one vacuous row: the 1/eps^2 coefficient of QCD^2 QED^6, with no
    # term (R = P = T = 0, every operand present); the same sector's 1/eps
    # row passes on its physical scale.
    (vacuous,) = [r for r in poles.values() if r.verdict == checks.VACUOUS]
    assert vacuous.subject == "QCD^2 QED^6 1/eps^2" and vacuous.scale_by == "vacuous"
    (cell,) = vacuous.cells
    assert (cell["residue"], cell["physical"], cell["terms"]) == (0.0, 0.0, 0.0)
    single = poles["QCD^2 QED^6 1/eps"]
    assert single.verdict == checks.PASS and single.scale_by == "physical"
    assert single.deviation < single.tolerance
    assert poles["QCD^4 QED^4"].verdict == checks.NO_PREDICTION
