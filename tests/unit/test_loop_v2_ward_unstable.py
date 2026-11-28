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
    # Catani's prediction (``catani``) tells the Ward rows which pole
    # coefficients vanish physically (the floor's only use).
    return NativeExecutor(slice_, inputs="native", forward=False, catani=True)


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
        assert absorptive["scopes"] == {
            "born": True,
            "poles": True,
            "finite": "inconclusive (unstable external leg)",
            "stabilised": True,
        }
        assert absorptive["verdict"] is True
        dispersive = rows[(leg, (0, 1))]
        assert dispersive["passed"] is True and "unstable" not in dispersive
        assert dispersive["verdict"] is True
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


def _plant(results, wards, parameters, kind):
    """Residuals planted into the Ward evaluations of one batch
    (``wards``: the batch's Ward values, None for the physical entry), at
    the requested spectrum only (a stabilised batch moves MW and stays
    clean): ``kind`` "born", the loop-side Born moved by 0.0995 of the
    physical Born; "double", the virtual's double pole moved by 0.1 of the
    physical finite part; "single", the single pole moved by 1 % of the
    physical single pole."""

    if kind is None or not any(w is not None for w in wards):
        return results
    if kind != "single" and "MW" in dict(parameters or {}):
        return results
    physical = next(r for r, w in zip(results, wards, strict=True) if w is None)
    out = []
    for result, value in zip(results, wards, strict=True):
        if value is None:
            out.append(result)
        elif kind == "born":
            born = abs(sum(complex(b) for b in physical.born.values()))
            loop_born = {
                s: complex(v) + 0.0995 * born for s, v in result.loop_born.items()
            }
            out.append(replace(result, loop_born=loop_born))
        else:
            components = {
                name: dict(parts) for name, parts in result.components.items()
            }
            for sector, laurent in result.components["virtual"].items():
                values = [complex(x) for x in laurent.coefficients]
                reference = physical.components["virtual"][sector].coefficients
                if kind == "double":
                    values[2] += 0.1 * abs(complex(reference[0]))
                else:
                    values[1] += 0.01 * abs(complex(reference[1]))
                components["virtual"][sector] = Laurent(*values)
            out.append(replace(result, components=components))
    return out


class _Planted:
    """The executor with ``_plant``'s residual in its Ward evaluations."""

    def __init__(self, inner, kind):
        self.inner = inner
        self.slice = inner.slice
        self.kind = kind

    def evaluate(self, points, scales, **options):
        results = self.inner.evaluate(points, scales, **options)
        wards = options.get("ward") or [None] * len(results)
        return _plant(results, wards, options.get("parameters"), self.kind)


def _check(tmp_path, monkeypatch, expression, orders, kind=None, extra="", **options):
    """``pyamplicol check`` of ``expression`` [QED] on loop_qcd_qed_sm (every
    width zero, one point) with ``_plant``'s residual of ``kind`` in its
    Ward evaluations: the process's rows by check and subject."""

    from pyamplicol.api.services import check
    from pyamplicol.loops.v2 import plan_export

    evaluate = plan_export.NativeExecutor.evaluate

    def planted(self, points, scales, *args, **kw):
        results = evaluate(self, points, scales, *args, **kw)
        wards = kw.get("ward") or [None] * len(results)
        return _plant(results, wards, kw.get("parameters"), kind)

    monkeypatch.setattr(plan_export.NativeExecutor, "evaluate", planted)
    card = tmp_path / "card.toml"
    card.write_text(
        f"""action = "check"
[model]
source = "loop_qcd_qed_sm"
restriction = "default"
[process]
entries = [{{expression = "{expression}", name = "p"}}]
loop_coupling_orders = ["QED"]
coupling_order_policy = "explicit"
max_coupling_orders = {orders}
{extra}[loop.preparation]
fixed_parameters = {{ WT = "0", WZ = "0", WW = "0", WH = "0" }}
[check]
points = 1
"""
    )
    report = check(card, **options)
    (process,) = report.processes
    return {(row.check, row.subject): row for row in process.rows}


def test_check_judges_the_unstable_top_in_two_scopes(tmp_path, monkeypatch):
    """``pyamplicol check`` of g g > t t~ [QED] (the USER ruling 2026-11-10
    refined: "not applicable" becomes "checked on a stabilised spectrum"):
    every Ward row passes; the c = 1 rows' requested finite part is
    inconclusive for the unstable top and decided on the stabilised
    spectrum, the Born and poles judged at the requested spectrum; the
    reason names each scope, the leg, its channel, the moved inputs and the
    derived inputs the move changes. (The pole rows are not this test's:
    their 1/eps^2 row, which vanishes physically, fails on main as well.)"""

    from pyamplicol.loops.v2 import checks

    rows = _check(tmp_path, monkeypatch, "g g > t t~", "{ QCD = 2, QED = 0 }")
    moved = "judged on the stabilised spectrum MW = 180.94275, MZ = 205.173"
    for leg in (1, 2):
        absorptive = rows[("ward", f"leg {leg}, c = 1")]
        assert absorptive.verdict == checks.PASS
        assert (
            "requested spectrum: Born, poles: pass; finite: inconclusive (unstable "
            "external leg); stabilised spectrum: pass"
        ) in absorptive.reason
        assert "leg 3 (t, mass 173.3) decays to W+ b" in absorptive.reason
        assert moved in absorptive.reason
        assert (
            "derived: Gf" in absorptive.reason and "sw2, ee kept" in absorptive.reason
        )
        dispersive = rows[("ward", f"leg {leg}, c = i")]
        assert dispersive.verdict == checks.PASS
        assert (
            "requested spectrum: Born, poles: pass; finite: pass; stabilised "
            "spectrum: pass"
        ) in dispersive.reason


@pytest.mark.parametrize("kind", ["born", "double"])
def test_check_keeps_requested_born_and_pole_failures(tmp_path, monkeypatch, kind):
    """Planted residuals through the CLI's Ward reducer, at the
    physical spectrum only (the stabilised one clean): a Born residual of
    0.0995 of the Born and a double-pole residual of 0.1 of the finite part
    fail every Ward row, as in ``ward_check``."""

    from pyamplicol.loops.v2 import checks

    rows = _check(tmp_path, monkeypatch, "g g > t t~", "{ QCD = 2, QED = 0 }", kind)
    ward_rows = [row for (check, _), row in rows.items() if check == "ward"]
    assert len(ward_rows) == 4
    for row in ward_rows:
        assert row.verdict == checks.FAIL
        assert "requested spectrum: Born, poles: fail" in row.reason


def test_check_judges_a_small_nonzero_pole_on_its_own_size(tmp_path, monkeypatch):
    """A small nonzero pole: a stable top (MW = 180, MZ = 200 at
    generation) at sqrt(s) = 346.61, the QED single pole small but nonzero;
    1 % of it planted fails the Ward rows at K = 1e-5 (no floor for a
    coefficient Catani does not predict zero)."""

    from pyamplicol.loops.v2 import checks

    rows = _check_stable_threshold(tmp_path, monkeypatch)
    ward_rows = [row for (check, _), row in rows.items() if check == "ward"]
    assert ward_rows and all(row.verdict == checks.FAIL for row in ward_rows)
    for row in ward_rows:
        assert row.reason is None or "unstable" not in row.reason


def _check_stable_threshold(tmp_path, monkeypatch):
    from pyamplicol.api.services import check
    from pyamplicol.loops.v2 import plan_export

    evaluate = plan_export.NativeExecutor.evaluate

    def planted(self, points, scales, *args, **kw):
        results = evaluate(self, points, scales, *args, **kw)
        wards = kw.get("ward") or [None] * len(results)
        return _plant(results, wards, kw.get("parameters"), "single")

    monkeypatch.setattr(plan_export.NativeExecutor, "evaluate", planted)
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
fixed_parameters = { WT = "0", WZ = "0", WW = "0", WH = "0", MW = "180", MZ = "200" }
[check]
points = 1
"""
    )
    report = check(card, sqrt_s=346.61, tolerance=1e-5)
    (process,) = report.processes
    return {(row.check, row.subject): row for row in process.rows}


def test_check_decides_instability_per_substituted_leg(tmp_path, monkeypatch):
    """Per substituted leg, u d~ > g a w+ [QED] with an untagged photon:
    the W carries no colour, so the gluon's Ward rows are checked and pass
    as any process; the photon sees the unstable W, which has no admissible
    stabilised spectrum (its decay products are massless): its rows judge
    the Born and poles at the requested spectrum and read "not applicable"
    for the finite part, with the reason. The process passes."""

    from pyamplicol.loops.v2 import checks

    rows = _check(
        tmp_path,
        monkeypatch,
        "u d~ > g a w+",
        "{ QCD = 1, QED = 2 }",
        extra='[loop]\nexternal_photons = "none"\n',
    )
    for c in ("1", "i"):
        gluon = rows[("ward", f"leg 3, c = {c}")]
        assert gluon.verdict == checks.PASS and gluon.reason is None
        photon = rows[("ward", f"leg 4, c = {c}")]
        assert photon.verdict == checks.NOT_APPLICABLE
        assert (
            "requested spectrum: Born, poles: pass; finite: not applicable; "
            "stabilised spectrum: unavailable"
        ) in photon.reason
        assert "leg 5 (W+, mass 80.419) decays to" in photon.reason
        assert "no admissible stabilised spectrum" in photon.reason


@pytest.mark.parametrize("kind", ["born", "double"])
def test_requested_born_and_pole_failures_stay_decisive(executor, kind):
    """Planted residuals at the physical spectrum, the stabilised
    spectrum clean: a Born residual (0.0995 of the Born) and a double-pole
    residual (0.1 of the finite part) fail the check; the unstable top
    excuses the requested FINITE coefficient only."""

    check = ward.ward_check(
        _Planted(executor, kind),
        _point("173.3"),
        MU_R2,
        "double-double",
        parameters=PARAMETERS,
    )
    assert check["unstable"]
    assert all(row["passed"] is True for row in check["stabilised"]["rows"])
    for row in check["rows"]:
        assert row["verdict"] is False and "unstable" not in row, row["scopes"]
    assert check["passed"] is False


def test_a_small_nonzero_pole_is_judged_on_its_own_size(executor):
    """The stable-top card near threshold: 1 % of the physical single pole
    planted (a small nonzero pole): the single pole is not a predicted
    zero, takes no floor, and fails."""

    check = ward.ward_check(
        _Planted(executor, "single"),
        _threshold_point(),
        MU_R2,
        "double-double",
        parameters={**PARAMETERS, "MW": "180", "MZ": "200"},
        legs=[1],
    )
    assert check["unstable"] == ()
    for row in check["rows"]:
        assert row["scale_floor"][1] is False
        assert row["scopes"]["poles"] is False and row["verdict"] is False
    assert check["passed"] is False


def _threshold_point() -> list[list[str]]:
    """g g > t t~ at sqrt(s) = 346.61 (MT = 173.3, just above 2 MT), the
    top pair along the x axis: on shell to 60 digits."""

    from decimal import Decimal, localcontext

    with localcontext() as context:
        context.prec = 60
        energy = Decimal("173.305")
        mass = Decimal("173.3")
        p = (energy * energy - mass * mass).sqrt()
        legs = [
            [energy, 0, 0, energy],
            [energy, 0, 0, -energy],
            [energy, p, 0, 0],
            [energy, -p, 0, 0],
        ]
        return [[format(+Decimal(x), "f") for x in leg] for leg in legs]


@pytest.fixture(scope="module")
def models(tmp_path_factory):
    """Both shipped electroweak schemes, compiled once."""

    from pyamplicol.models.loading import compile_model_source

    root = tmp_path_factory.mktemp("ew-models")
    return {
        name: compile_model_source(name, restriction="default", cache_dir=root / name)
        for name in ("loop_qcd_qed_sm", "loop_qcd_qed_sm_Gmu")
    }


@pytest.mark.parametrize("name", ["loop_qcd_qed_sm", "loop_qcd_qed_sm_Gmu"])
def test_the_stabilised_spectrum_is_an_admissible_point(models, loop_native, name):
    """An admissible stabilised point, in both schemes. Free MW and MZ: one common
    factor (2.25) keeps sin^2(theta_W); the report names what the move
    changes (G_mu: alpha recomputed from 0.00754677 to 0.0382055, Gf and
    sw2 kept; alpha(M_Z): Gf and vev change, aEW and sw2 kept). MZ fixed at
    generation: no common scaling, the stable comparison is unavailable and
    the Ward check never returns True (the helper used to move MW alone,
    sin^2(theta_W) = -2.94). A requested point with MW above MZ: the moved
    point is not admissible (sw is not real)."""

    def slice_(fixed):
        request = SliceRequest(
            "g g > t t~",
            {"QCD": 2, "QED": 0},
            {"QCD": 2, "QED": 2},
            corrections=("QED",),
            fixed_parameters=fixed,
            scale_parameter="MU_R",
        )
        return ward.ward_slice(models[name], request, loop_native)

    free = slice_(FIXED)
    moved, why = ward.stabilised_parameters(free, None, PARAMETERS)
    assert (moved, why) == (STABILISED, None)
    derived = ward.derived_changes(free, PARAMETERS, moved)
    if name == "loop_qcd_qed_sm_Gmu":
        assert "aEW 0.00754677 -> 0.0382055" in derived
        assert derived.endswith("Gf, sw2, vev kept")
    else:
        assert derived.startswith("derived: Gf") and "sw2" in derived.split(";")[-1]
    moved, why = ward.stabilised_parameters(free, None, {**PARAMETERS, "MW": "95"})
    assert moved is None and "is not admissible: sw = " in why
    fixed = slice_({**FIXED, "MZ": "91.188"})
    moved, why = ward.stabilised_parameters(fixed, None, PARAMETERS)
    assert moved is None and why.startswith("MZ fixed at generation")
    check = ward.ward_check(
        NativeExecutor(fixed, inputs="native", forward=False, catani=True),
        _point("173.3"),
        MU_R2,
        "double-double",
        parameters=PARAMETERS,
        legs=[1],
    )
    assert check["stabilised"]["parameters"] is None
    absorptive = _rows(check)[(1, (1, 0))]
    assert absorptive["verdict"] is None
    assert (
        "no admissible stabilised spectrum (MZ fixed at generation"
        in (absorptive["unstable"])
    )
    assert check["passed"] is None
