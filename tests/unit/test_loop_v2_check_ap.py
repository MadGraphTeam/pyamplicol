# SPDX-License-Identifier: 0BSD
"""``pyamplicol check`` on real requests for m-lit lit-check (nightly: each
regenerates an electroweak request in memory).

* **The arbitrary-precision rung** (the threshold rule, R < K S): u u~ > d
  d~ a a with QED corrections (QCD 0, QED 4, every width zero, untagged
  photons), the default check (three points from seed 12345) at K =
  1e-24: double-double's Ward residues (up to 4e-22 of the physical scale
  at the third point, lit-ew-blocks §3 (d)) miss it, so those rows alone are
  re-run in arbitrary precision at twice double-double's digits (64) and
  pass there; every row passes; exit 0. At the default K every row passes
  without the rung. About 4 minutes and 10-20 GiB (the probe slice of a
  2 -> 4 electroweak request and an MPFR Ward batch).
* **Ward rows not applicable** (USER 2026-11-10 ~00:17): g t > t t t~ with
  QCD and QED corrections (lit-ew-blocks census row TT05, external on-shell
  zero-width tops), whose gluon Ward rows failed by 3e8 - 7e8: one "not
  applicable" Ward row naming the class, nothing Ward-evaluated, its pole
  rows passing as in the census; exit 0. About 3 minutes and 9 GiB.
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
    report = check(card, seed=12345, tolerance=1e-24)
    assert report.carriers == ("double", "double-double", "arbitrary")
    assert report.tolerance == 1e-24
    assert report.exit_code == checks.EXIT_PASSED, report
    (process,) = report.processes
    ward = [row for row in process.rows if row.check == "ward"]
    assert len(ward) == 12 and all(row.verdict == checks.PASS for row in ward)
    decided = [row for row in ward if row.carrier == "arbitrary"]
    assert decided
    for row in decided:
        assert row.digits == 64 and row.deviation < row.tolerance == 1e-24
        assert row.fallback.startswith("double-double: R / S")
    poles = [row for row in process.rows if row.check == "poles"]
    assert len(poles) == 6 and all(row.verdict == checks.PASS for row in poles)


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
    poles = [row for row in process.rows if row.check == "poles"]
    assert {row.verdict for row in poles} == {checks.PASS, checks.NO_PREDICTION}
