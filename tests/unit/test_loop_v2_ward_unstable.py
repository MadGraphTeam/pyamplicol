# SPDX-License-Identifier: 0BSD
"""The Ward check with an unstable external leg (``ward`` module docstring,
"Unstable external legs"; ``checks`` module docstring, the same section).

g g > t t~ with QED corrections on loop_qcd_qed_sm (alpha(M_Z), default
restriction, MB = 0, every width zero), double-double. With MT > MW + MB the
top can decay to W b at its own mass; the real on-shell scheme renormalises
only Re Sigma_t, so the gluon Ward identity fails in the absorptive part of
the one-loop finite coefficient of the sector the decay reaches (QCD^4
QED^2): 8.6e-3 of the physical scale at MT = 173.3, 5.5e-8 just above the
threshold (MT = 81), zero below it (MT = 80), while the served values equal
MadLoop, Recola and OpenLoops. That finite coefficient is not applicable;
the Born, every pole and every other sector (QCD^6 of a mixed request) stay
decisive, and a proved failure always fails the check.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from pyamplicol.loops.v2 import ward
from pyamplicol.loops.v2.assemble import Laurent, SliceRequest
from pyamplicol.loops.v2.plan_export import NativeExecutor
from tools.loop_reference import exact_points

pytestmark = pytest.mark.loop_physics

FIXED = {"WT": "0", "WZ": "0", "WW": "0", "WH": "0"}
PARAMETERS = {"aS": "0.118"}
MU_R2 = "8315.251344"


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


def _plant(results, wards, kind, *, sector=None, only=None):
    """Residuals planted into the Ward evaluations of one batch (``wards``:
    the batch's Ward values, None for the physical entry); ``only`` =
    (leg, factor) restricts it to one row. ``kind`` "born", the loop-side
    Born moved by 0.0995 of the physical Born; "double", the virtual's
    double pole moved by 0.1 of the physical finite part; "single", the
    single pole moved by 1 % of the physical single pole; "finite", the
    finite part of ``sector`` (by its nonzero powers) moved by 0.1 of the
    physical finite part of that sector."""

    if kind is None or not any(w is not None for w in wards):
        return results
    physical = next(r for r, w in zip(results, wards, strict=True) if w is None)
    out = []
    for result, value in zip(results, wards, strict=True):
        if value is None or (
            only is not None
            and (
                value[0] != only[0]
                or (float(value[1][1]) == 0) != (tuple(only[1]) == (1, 0))
            )
        ):
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
            for key, laurent in result.components["virtual"].items():
                if sector is not None and ward.sector_powers(key) != ward.sector_powers(
                    sector
                ):
                    continue
                values = [complex(x) for x in laurent.coefficients]
                reference = physical.components["virtual"][key].coefficients
                if kind == "double":
                    values[2] += 0.1 * abs(complex(reference[0]))
                elif kind == "finite":
                    values[0] += 0.1 * abs(complex(reference[0]))
                else:
                    values[1] += 0.01 * abs(complex(reference[1]))
                components["virtual"][key] = Laurent(*values)
            out.append(replace(result, components=components))
    return out


class _Planted:
    """The executor with ``_plant``'s residual in its Ward evaluations."""

    def __init__(self, inner, kind, **where):
        self.inner = inner
        self.slice = inner.slice
        self.kind = kind
        self.where = where

    def evaluate(self, points, scales, **options):
        results = self.inner.evaluate(points, scales, **options)
        wards = options.get("ward") or [None] * len(results)
        return _plant(results, wards, self.kind, **self.where)


MIXED = (("QCD", 4), ("QED", 2))
QCD6 = (("QCD", 6),)


def test_the_reached_finite_part_is_not_applicable(executor):
    """Physical masses: legs 3 and 4 decay to W b (a QED vertex); every Ward
    row leaves the QCD^4 QED^2 finite coefficient (the c = 1 one 8.6e-3 of
    the scale) not applicable, judges the Born and poles (they pass, the
    double pole, zero by Catani, on the floor), and is therefore undecided:
    the check is inconclusive, never True."""

    check = ward.ward_check(
        executor, _point("173.3"), MU_R2, "double-double", parameters=PARAMETERS
    )
    unstable = {(leg.leg, leg.particle, leg.channel) for leg in check["unstable"]}
    assert unstable == {(3, "t", ("W+", "b")), (4, "t~", ("W-", "b~"))}
    for (_leg, factor), row in _rows(check).items():
        assert row["passed"] is None and row["born_passed"] is True
        assert row["virtual_passed"] is True
        (sector,) = row["not_applicable"]
        assert ward.sector_powers(sector) == {"QCD": 4, "QED": 2}
        assert "unstable external leg 3 (t), open channel W+ b" in row["unstable"]
        if factor == (1, 0):
            assert row["not_applicable"][sector] is False
            assert row["parts"]["virtual"][0] > 1e-3
        else:
            assert row["scale_floor"] == [False, False, True]
    assert check["passed"] is None


@pytest.mark.parametrize("kind", ["born", "double"])
def test_requested_born_and_pole_failures_stay_decisive(executor, kind):
    """A Born residual (0.0995 of the Born) or a double-pole residual (0.1
    of the finite part) planted on leg 1, c = 1 only: that row fails, the
    others are undecided, and the check FAILS (an undecided row never
    overrules a proved failure)."""

    check = ward.ward_check(
        _Planted(executor, kind, only=(1, (1, 0))),
        _point("173.3"),
        MU_R2,
        "double-double",
        parameters=PARAMETERS,
    )
    rows = _rows(check)
    assert rows[(1, (1, 0))]["passed"] is False
    assert {row["passed"] for key, row in rows.items() if key != (1, (1, 0))} == {None}
    assert check["passed"] is False


def test_a_stable_top_is_checked_in_full(executor):
    """The benchmark's stable-top card (MW = 180, MZ = 200): no unstable
    leg, every row passes."""

    check = ward.ward_check(
        executor,
        _point("173.3"),
        MU_R2,
        "double-double",
        parameters={**PARAMETERS, "MW": "180", "MZ": "200"},
    )
    assert check["unstable"] == ()
    assert all(row["passed"] is True for row in check["rows"])
    assert check["passed"] is True


def test_the_threshold_decides_the_instability(executor):
    """MT = 80 (below MW = 80.419): stable, every row passes; MT = 81: the
    top decays to W b, the reached finite part (5.5e-8 of the scale) is not
    applicable."""

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
    absorptive = _rows(above)[(1, (1, 0))]
    assert absorptive["passed"] is None and "not_applicable" in absorptive
    assert 1e-9 < absorptive["parts"]["virtual"][0] < 1e-6
    assert above["passed"] is None


def test_a_small_nonzero_pole_is_judged_on_its_own_size(executor):
    """A stable top near threshold (sqrt(s) = 346.61), 1 % of the physical
    single pole planted: the single pole is not a predicted zero, takes no
    floor, and fails."""

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
        assert row["scale_floor"][1] is False and row["passed"] is False
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


def _check(tmp_path, monkeypatch, expression, orders, kind=None, **settings):
    """``pyamplicol check`` of ``expression`` on loop_qcd_qed_sm (every width
    zero, one point) with ``_plant``'s residual of ``kind`` in its Ward
    evaluations (``where``); ``corrections`` (default ["QED"]), ``extra``
    card lines, ``fixed`` more fixed parameters, ``options`` for ``check``.
    Returns the process's rows by (check, subject) and the probe slice."""

    from pyamplicol.api.services import check
    from pyamplicol.loops.v2 import checks, plan_export

    where = settings.get("where", {})
    evaluate = plan_export.NativeExecutor.evaluate

    def planted(self, points, scales, *args, **kw):
        results = evaluate(self, points, scales, *args, **kw)
        wards = kw.get("ward") or [None] * len(results)
        return _plant(results, wards, kind, **where)

    monkeypatch.setattr(plan_export.NativeExecutor, "evaluate", planted)
    captured = {}
    rows_of = checks.born_interfered_rows

    def spy(target, *args, **kw):
        captured["target"] = target
        return rows_of(target, *args, **kw)

    monkeypatch.setattr(checks, "born_interfered_rows", spy)
    fixed = {"WT": "0", "WZ": "0", "WW": "0", "WH": "0", **settings.get("fixed", {})}
    card = tmp_path / "card.toml"
    card.write_text(
        f"""action = "check"
[model]
source = "loop_qcd_qed_sm"
restriction = "default"
[process]
entries = [{{expression = "{expression}", name = "p"}}]
loop_coupling_orders = {settings.get("corrections", '["QED"]')}
coupling_order_policy = "explicit"
max_coupling_orders = {orders}
{settings.get("extra", "")}[loop.preparation]
fixed_parameters = {{ {", ".join(f'{k} = "{v}"' for k, v in fixed.items())} }}
[check]
points = 1
"""
    )
    report = check(card, **settings.get("options", {}))
    (process,) = report.processes
    rows = {(row.check, row.subject): row for row in process.rows}
    return rows, captured.get("target")


def test_check_leaves_the_reached_finite_part_not_applicable(tmp_path, monkeypatch):
    """``pyamplicol check`` of g g > t t~ [QED] (the USER ruling 2026-11-10
    refined: the Born, the poles and every other sector are checked): every
    Ward row passes on its Born and poles, its QCD^4 QED^2 finite cell not
    applicable with the leg and channel named. (The pole rows are not this
    test's: their 1/eps^2 row, which vanishes physically, fails on main as
    well.)"""

    from pyamplicol.loops.v2 import checks

    rows, _ = _check(tmp_path, monkeypatch, "g g > t t~", "{ QCD = 2, QED = 0 }")
    ward_rows = {
        subject: row for (check, subject), row in rows.items() if check == "ward"
    }
    assert set(ward_rows) == {f"leg {leg}, c = {c}" for leg in (1, 2) for c in "1i"}
    for row in ward_rows.values():
        assert row.verdict == checks.PASS
        assert (
            "QCD^4 QED^2 finite: not applicable (unstable external leg 3 (t), open "
            "channel W+ b; unstable external leg 4 (t~), open channel W- b~)"
        ) in row.reason
        cells = {cell["label"]: cell["verdict"] for cell in row.cells}
        assert cells["QCD^4 QED^2 finite"] == checks.NOT_APPLICABLE
        assert cells["QCD^4 QED^2 1/eps"] == checks.PASS


@pytest.mark.parametrize("kind", ["born", "double"])
def test_check_keeps_requested_born_and_pole_failures(tmp_path, monkeypatch, kind):
    """The same plantings through the CLI's Ward reducer, on leg 1, c = 1
    only: that row FAILS, as in ``ward_check``; the process fails."""

    from pyamplicol.loops.v2 import checks

    rows, _ = _check(
        tmp_path,
        monkeypatch,
        "g g > t t~",
        "{ QCD = 2, QED = 0 }",
        kind,
        where={"only": (1, (1, 0))},
    )
    assert rows[("ward", "leg 1, c = 1")].verdict == checks.FAIL
    assert rows[("ward", "leg 2, c = i")].verdict == checks.PASS
    assert checks.status_of(row.verdict for row in rows.values()) == checks.FAILED


def test_check_judges_a_small_nonzero_pole_on_its_own_size(tmp_path, monkeypatch):
    """A stable top (MW = 180, MZ = 200 at generation) at sqrt(s) = 346.61,
    the QED single pole small but nonzero; 1 % of it planted fails the Ward
    rows at K = 1e-5 (no floor for a coefficient Catani does not predict
    zero)."""

    from pyamplicol.loops.v2 import checks

    rows, _ = _check(
        tmp_path,
        monkeypatch,
        "g g > t t~",
        "{ QCD = 2, QED = 0 }",
        "single",
        fixed={"MW": "180", "MZ": "200"},
        options={"sqrt_s": 346.61, "tolerance": 1e-5},
    )
    ward_rows = [row for (check, _), row in rows.items() if check == "ward"]
    assert ward_rows and all(row.verdict == checks.FAIL for row in ward_rows)


def test_check_decides_instability_per_substituted_leg(tmp_path, monkeypatch):
    """u d~ > g a w+ [QED] with an untagged photon: the W carries no colour,
    so the gluon's Ward rows are judged in full (pass, no reason); the
    photon sees the unstable W: its rows judge the Born and poles (pass) and
    leave the reached finite cell not applicable with the reason."""

    from pyamplicol.loops.v2 import checks

    rows, _ = _check(
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
        assert photon.verdict == checks.PASS
        assert "finite: not applicable (unstable external leg 5 (W+), open channel" in (
            photon.reason
        )


def test_the_finite_exception_does_not_cross_sectors(tmp_path, monkeypatch):
    """g g > t t~ [QCD QED] at the physical masses: +0.1 in the pure QCD^6
    finite gluon Ward coefficient alone (leg 1, c = 1) FAILS in ``pyamplicol
    check`` and in ``ward_check``: the open t -> W b decay reaches QCD^4
    QED^2 only. The converse: the same planting in QCD^4 QED^2 is not
    applicable (undecided, never a failure or a pass)."""

    from pyamplicol.loops.v2 import checks

    rows, target = _check(
        tmp_path,
        monkeypatch,
        "g g > t t~",
        "{ QCD = 2, QED = 0 }",
        "finite",
        corrections='["QCD", "QED"]',
        where={"sector": QCD6, "only": (1, (1, 0))},
    )
    planted = rows[("ward", "leg 1, c = 1")]
    assert planted.verdict == checks.FAIL
    cells = {cell["label"]: cell["verdict"] for cell in planted.cells}
    assert cells["QCD^6 finite"] == checks.FAIL
    assert cells["QCD^4 QED^2 finite"] == checks.NOT_APPLICABLE
    # The check's planting (on the executor class) ends here.
    monkeypatch.undo()
    executor = NativeExecutor(target, inputs="native", forward=False, catani=True)
    for sector, verdict, overall in ((QCD6, False, False), (MIXED, None, None)):
        check = ward.ward_check(
            _Planted(executor, "finite", sector=sector, only=(1, (1, 0))),
            _point("173.3"),
            MU_R2,
            "double-double",
            parameters=PARAMETERS,
            legs=[1],
        )
        assert _rows(check)[(1, (1, 0))]["passed"] is verdict, sector
        assert check["passed"] is overall, sector
