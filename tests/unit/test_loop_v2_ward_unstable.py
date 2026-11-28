# SPDX-License-Identifier: 0BSD
"""The Ward check with an unstable external leg (``ward`` module docstring,
"Unstable external legs"; ``checks`` module docstring, the same section).

g g > t t~ with QED corrections on loop_qcd_qed_sm (alpha(M_Z), default
restriction, MB = 0, every width zero), the QCD^4 QED^2 sector, double-double.
With MT > MW + MB the top can decay to W b at its own mass. The real
on-shell scheme renormalises only Re Sigma_t, so the gluon Ward identity
fails in the absorptive part of the amplitude: the c = 1 finite part is
8.6e-3 of the physical scale at MT = 173.3, 5.5e-8 just above the threshold
(MT = 81) and zero below it (MT = 80). The served values equal MadLoop,
Recola and OpenLoops. The check reports those rows as inconclusive for the
unstable leg and judges the same rows on a stabilised spectrum (MW and MZ
scaled together until the channel closes), where they must pass; a broken
amplitude fails there. The stabilised spectrum is used by the Ward rows only:
the requested spectrum's values are unchanged by a check.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from pyamplicol.loops.v2 import ward
from pyamplicol.loops.v2.assemble import Laurent, Precision, SliceRequest
from pyamplicol.loops.v2.plan_export import NativeExecutor
from tools.loop_reference import exact_points

pytestmark = pytest.mark.loop_physics

FIXED = {"WT": "0", "WZ": "0", "WW": "0", "WH": "0"}
PARAMETERS = {"aS": "0.118"}
MU_R2 = "8315.251344"
STABILISED = {"MW": "180.94275", "MZ": "205.173"}


def _point(mass: str) -> list[list[str]]:
    """The first exact on-shell point of g g > t t~ at the top mass ``mass``
    (``exact_points.generate``; at 173.3 the investigation's point)."""

    (point,) = exact_points.generate([0, 0, mass, mass], count=1)
    return [[exact_points.decimal_string(x) for x in p] for p in point]


@pytest.fixture(scope="module")
def executor(tmp_path_factory, loop_native):
    from pyamplicol.models.loading import compile_model_source

    root = tmp_path_factory.mktemp("loop-qcd-qed-sm")
    compiled = compile_model_source(
        "loop_qcd_qed_sm", restriction="default", cache_dir=root / "cache"
    )
    request = SliceRequest(
        "g g > t t~",
        {"QCD": 2, "QED": 0},
        {"QCD": 2, "QED": 2},
        corrections=("QED",),
        fixed_parameters=FIXED,
        scale_parameter="MU_R",
    )
    slice_ = ward.ward_slice(compiled, request, loop_native)
    return NativeExecutor(slice_, inputs="native", forward=False)


def _rows(check):
    return {(row["leg"], tuple(row["factor"])): row for row in check["rows"]}


def test_the_unstable_top_is_judged_on_the_stabilised_spectrum(executor):
    """Physical masses: legs 3 and 4 decay to W b; the requested c = 1 rows
    (the absorptive violation, 8.6e-3 of the scale) are inconclusive with the
    leg, the channel and the stabilised spectrum; the c = i rows pass (their
    double pole, zero physically, on the Born x alpha / 2 pi floor); every
    stabilised row passes, and so does the check."""

    check = ward.ward_check(
        executor, _point("173.3"), MU_R2, "double-double", parameters=PARAMETERS
    )
    unstable = {(leg.leg, leg.particle, leg.channel) for leg in check["unstable"]}
    assert unstable == {(3, "t", ("W+", "b")), (4, "t~", ("W-", "b~"))}
    assert check["stabilised"]["parameters"] == STABILISED
    rows = _rows(check)
    for leg in (1, 2):
        absorptive = rows[(leg, (1, 0))]
        assert absorptive["passed"] is None and absorptive["virtual_passed"] is False
        assert absorptive["parts"]["virtual"][0] > 1e-3
        assert "leg 3 (t, mass 173.3) decays to W+ b" in absorptive["unstable"]
        assert (
            "judged on the stabilised spectrum MW = 180.94275, MZ = 205.173"
            in absorptive["inconclusive"]
        )
        dispersive = rows[(leg, (0, 1))]
        assert dispersive["passed"] is True and "unstable" not in dispersive
        assert dispersive["scale_floor"] == [False, False, True]
    stabilised = check["stabilised"]["rows"]
    assert len(stabilised) == 4 and all(row["passed"] is True for row in stabilised)
    assert check["passed"] is True


def test_a_stable_top_takes_no_stabilised_spectrum(executor):
    """The benchmark's stable-top card (MW = 180, MZ = 200): no unstable
    leg, one batch, every row passes."""

    check = ward.ward_check(
        executor,
        _point("173.3"),
        MU_R2,
        "double-double",
        parameters={**PARAMETERS, "MW": "180", "MZ": "200"},
    )
    assert check["unstable"] == () and check["stabilised"] is None
    assert all(row["passed"] is True for row in check["rows"])
    assert check["passed"] is True


def test_the_threshold_decides_the_instability(executor):
    """MT = 80 (below MW = 80.419): stable, every row passes as it is; MT = 81:
    the top decays to W b, the requested c = 1 rows are inconclusive for it
    (5.5e-8 of the scale), the stabilised spectrum (MW and MZ times 1.05)
    passes."""

    below = ward.ward_check(
        executor,
        _point("80"),
        MU_R2,
        "double-double",
        parameters={**PARAMETERS, "MT": "80", "ymt": "80"},
        legs=[1],
    )
    assert below["unstable"] == () and below["passed"] is True
    above = ward.ward_check(
        executor,
        _point("81"),
        MU_R2,
        "double-double",
        parameters={**PARAMETERS, "MT": "81", "ymt": "81"},
        legs=[1],
    )
    assert [leg.leg for leg in above["unstable"]] == [3, 4]
    assert above["stabilised"]["parameters"] == {"MW": "84.43995", "MZ": "95.7474"}
    absorptive = _rows(above)[(1, (1, 0))]
    assert absorptive["passed"] is None
    assert 1e-9 < absorptive["parts"]["virtual"][0] < 1e-6
    assert all(row["passed"] is True for row in above["stabilised"]["rows"])
    assert above["passed"] is True


class _BrokenR2:
    """The executor with every R2 insertion scaled by 1 + 1e-6 (the virtual
    moved by the same amount): a broken amplitude."""

    def __init__(self, inner):
        self.inner = inner
        self.slice = inner.slice

    def evaluate(self, *args, **options):
        return [
            self._broken(result) for result in self.inner.evaluate(*args, **options)
        ]

    @staticmethod
    def _broken(result):
        components = {name: dict(parts) for name, parts in result.components.items()}
        for sector, r2 in result.components["r2"].items():
            virtual = result.components["virtual"][sector]
            moved = [
                complex(v) + 1e-6 * complex(r)
                for v, r in zip(virtual.coefficients, r2.coefficients, strict=True)
            ]
            components["r2"][sector] = Laurent(
                *(complex(r) * (1 + 1e-6) for r in r2.coefficients)
            )
            components["virtual"][sector] = Laurent(*moved)
        return replace(result, components=components)


def test_a_broken_amplitude_fails_with_an_unstable_leg_present(executor):
    """The R2 part scaled by 1 + 1e-6 with the unstable top present: the
    requested spectrum's failing rows are inconclusive for the unstable leg,
    the stabilised spectrum's dispersive rows fail, so the check fails."""

    check = ward.ward_check(
        _BrokenR2(executor),
        _point("173.3"),
        MU_R2,
        "double-double",
        parameters=PARAMETERS,
    )
    assert check["unstable"]
    assert all(row["passed"] is not False for row in check["rows"])
    stabilised = {
        (row["leg"], tuple(row["factor"])): row["passed"]
        for row in check["stabilised"]["rows"]
    }
    assert stabilised[(1, (0, 1))] is False and stabilised[(2, (0, 1))] is False
    assert check["passed"] is False


def test_the_stabilised_spectrum_does_not_leak(executor):
    """The values at the requested spectrum after a check with a stabilised
    spectrum equal those before it, bit for bit."""

    point = _point("173.3")

    def values():
        (result,) = executor.evaluate(
            [point], [MU_R2], parameters=PARAMETERS, precision=Precision.double_double()
        )
        return {
            name: {
                sector: tuple(str(x) for x in laurent.coefficients)
                for sector, laurent in parts.items()
            }
            for name, parts in result.components.items()
        }, {sector: str(born) for sector, born in result.born.items()}

    before = values()
    check = ward.ward_check(
        executor, point, MU_R2, "double-double", parameters=PARAMETERS
    )
    assert check["stabilised"]["parameters"] == STABILISED
    assert values() == before


def test_check_judges_the_unstable_top_on_the_stabilised_spectrum(tmp_path):
    """``pyamplicol check`` of g g > t t~ [QED] (the USER ruling 2026-11-10
    refined: "not applicable" becomes "checked on a stabilised spectrum"):
    every Ward row (legs 1 and 2, c = 1 and i) passes, the c = 1 rows from
    the stabilised spectrum with the requested spectrum's inconclusive
    verdict, the leg, its channel and the moved inputs in the reason, the
    c = i rows at the requested spectrum with the stabilised verdict in the
    reason. (The pole rows are not this test's: the 1/eps^2 row, which
    vanishes physically, fails on main as well, rounding over rounding.)"""

    from pyamplicol.api.services import check
    from pyamplicol.loops.v2 import checks

    card = tmp_path / "card.toml"
    card.write_text(
        """action = "check"
[model]
source = "loop_qcd_qed_sm"
restriction = "default"
[process]
entries = [{expression = "g g > t t~", name = "p"}]
loop_coupling_orders = ["QED"]
coupling_order_policy = "explicit"
max_coupling_orders = { QCD = 2, QED = 0 }
[loop.preparation]
fixed_parameters = { WT = "0", WZ = "0", WW = "0", WH = "0" }
[check]
points = 1
"""
    )
    report = check(card)
    (process,) = report.processes
    rows = {row.subject: row for row in process.rows if row.check == "ward"}
    assert set(rows) == {f"leg {leg}, c = {c}" for leg in (1, 2) for c in ("1", "i")}
    moved = "judged on the stabilised spectrum MW = 180.94275, MZ = 205.173"
    for leg in (1, 2):
        absorptive = rows[f"leg {leg}, c = 1"]
        assert absorptive.verdict == checks.PASS
        assert "requested spectrum: inconclusive (fail" in absorptive.reason
        assert "leg 3 (t, mass 173.3) decays to W+ b" in absorptive.reason
        assert moved in absorptive.reason
        dispersive = rows[f"leg {leg}, c = i"]
        assert dispersive.verdict == checks.PASS
        assert dispersive.reason.endswith("stabilised spectrum: pass")
