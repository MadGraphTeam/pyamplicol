# SPDX-License-Identifier: 0BSD
"""The Ward check with an unstable external leg: a hint, never a verdict
(``ward`` module docstring, "Unstable external legs"; ``checks`` module
docstring, the same section).

g g > t t~ with QED corrections on loop_qcd_qed_sm (alpha(M_Z), default
restriction, MB = 0, every width zero), double-double. With MT > MW + MB the
top can decay to W b at its own mass; the real on-shell scheme renormalises
only Re Sigma_t, so the gluon Ward identity has a physical absorptive
violation in the one-loop finite coefficient (8.6e-3 of the physical scale
at MT = 173.3, 5.5e-8 at MT = 81, zero at MT = 80), while the served values
equal MadLoop, Recola and OpenLoops. Such a failure cannot be told from an
implementation error, so every cell is judged as always: the failing finite
cell FAILS and carries a hint naming the unstable leg and its channel. Every
test also runs with the detection switched off: the verdicts are identical,
only the hint differs.
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
    finite part of ``sector`` moved by 0.1 of its physical finite part."""

    if kind is None or not any(w is not None for w in wards):
        return results

    def powers(key):
        return {str(o): int(n) for o, n in key if int(n)}

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
                if sector is not None and powers(key) != powers(sector):
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

    def __init__(self, inner, kind=None, **where):
        self.inner = inner
        self.slice = inner.slice
        self.kind = kind
        self.where = where

    def evaluate(self, points, scales, **options):
        results = self.inner.evaluate(points, scales, **options)
        wards = options.get("ward") or [None] * len(results)
        return _plant(results, wards, self.kind, **self.where)


def _no_detection(monkeypatch):
    monkeypatch.setattr(
        ward,
        "hint_legs",
        lambda _slice, legs, parameters=None: {leg: () for leg in legs},
    )


def _ward(
    monkeypatch,
    executor,
    point,
    parameters,
    kind=None,
    legs=None,
    factors=ward.WARD_FACTORS,
    **where,
):
    """``ward_check`` with ``_plant``'s residual, with the detection and
    without it: (row by key, check). The verdicts must be identical; only
    the hint may differ."""

    def run():
        return ward.ward_check(
            _Planted(executor, kind, **where),
            point,
            MU_R2,
            "double-double",
            parameters=parameters,
            legs=legs,
            factors=factors,
        )

    on = run()
    with monkeypatch.context() as patch:
        _no_detection(patch)
        off = run()
    assert [r["passed"] for r in on["rows"]] == [r["passed"] for r in off["rows"]]
    assert on["passed"] is off["passed"]
    assert all("hint" not in r for r in off["rows"])
    for row in on["rows"]:
        if "hint" in row:
            assert on["unstable_by_leg"][row["leg"]] and row["passed"] is False
    return _rows(on), on


MIXED = (("QCD", 4), ("QED", 2))
QCD6 = (("QCD", 6),)
HINT = "external leg 3 (t) is unstable at these parameters (open channel W+ b)"


def test_the_unstable_top_fails_its_finite_cell_with_the_hint(monkeypatch, executor):
    """Physical masses: legs 3 and 4 decay to W b; the c = 1 rows FAIL on
    their finite cell (8.6e-3 of the scale) with the hint, their Born and
    poles pass; the c = i rows pass (the double pole, zero by Catani, on the
    floor) without the hint; the check fails."""

    rows, check = _ward(monkeypatch, executor, _point("173.3"), PARAMETERS)
    unstable = {(leg.leg, leg.particle, leg.channel) for leg in check["unstable"]}
    assert unstable == {(3, "t", ("W+", "b")), (4, "t~", ("W-", "b~"))}
    for (_leg, factor), row in rows.items():
        assert row["born_passed"] is True
        if factor == (1, 0):
            assert row["passed"] is False and HINT in row["hint"]
            assert row["parts"]["virtual"][0] > 1e-3
        else:
            assert row["passed"] is True and "hint" not in row
            assert row["scale_floor"] == [False, False, True]
    assert check["passed"] is False


def test_a_stable_top_passes_in_full(monkeypatch, executor):
    """The benchmark's stable-top card (MW = 180, MZ = 200): no unstable
    leg, every row passes, no hint."""

    rows, check = _ward(
        monkeypatch,
        executor,
        _point("173.3"),
        {**PARAMETERS, "MW": "180", "MZ": "200"},
    )
    assert check["unstable"] == () and check["passed"] is True
    assert all(r["passed"] is True and "hint" not in r for r in rows.values())


@pytest.mark.parametrize("kind", ["born", "double"])
def test_planted_born_and_pole_failures_fail(monkeypatch, executor, kind):
    """A Born residual (0.0995 of the Born) or a double-pole residual (0.1
    of the finite part) planted on leg 1, c = i only (a row that otherwise
    passes): that row FAILS, without the hint (no finite failure there)."""

    rows, check = _ward(
        monkeypatch, executor, _point("173.3"), PARAMETERS, kind, only=(1, (0, 1))
    )
    assert rows[(1, (0, 1))]["passed"] is False and "hint" not in rows[(1, (0, 1))]
    assert rows[(2, (0, 1))]["passed"] is True
    assert check["passed"] is False


def test_the_threshold_decides_the_hint(monkeypatch, executor):
    """MT = 80 (below MW = 80.419): stable, every row passes; MT = 81: the
    c = 1 finite cell (5.5e-8 of the scale) FAILS with the hint."""

    rows, below = _ward(
        monkeypatch,
        executor,
        _point("80"),
        {**PARAMETERS, "MT": "80", "ymt": "80"},
        legs=[1],
    )
    assert below["unstable"] == () and below["passed"] is True
    rows, _above = _ward(
        monkeypatch,
        executor,
        _point("81"),
        {**PARAMETERS, "MT": "81", "ymt": "81"},
        legs=[1],
    )
    absorptive = rows[(1, (1, 0))]
    assert absorptive["passed"] is False and HINT in absorptive["hint"]
    assert 1e-9 < absorptive["parts"]["virtual"][0] < 1e-6


def test_a_small_nonzero_pole_is_judged_on_its_own_size(monkeypatch, executor):
    """A stable top near threshold (sqrt(s) = 346.61), 1 % of the physical
    single pole planted: no floor for a pole Catani does not predict zero;
    it fails."""

    rows, check = _ward(
        monkeypatch,
        executor,
        _threshold_point(),
        {**PARAMETERS, "MW": "180", "MZ": "200"},
        "single",
        legs=[1],
    )
    assert check["unstable"] == ()
    for row in rows.values():
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
    evaluations (``where``), with the detection and without it: the rows by
    (check, subject) of the run with it, after asserting that both runs give
    identical verdicts (only the hint differs); ``corrections`` (default
    ["QED"]), ``restriction``, ``extra`` card lines, ``fixed`` more fixed
    parameters, ``options`` for ``check``."""

    from pyamplicol.api.services import check
    from pyamplicol.loops.v2 import plan_export

    where = settings.get("where", {})
    fixed = {"WT": "0", "WZ": "0", "WW": "0", "WH": "0", **settings.get("fixed", {})}
    card = tmp_path / "card.toml"
    card.write_text(
        f"""action = "check"
[model]
source = "loop_qcd_qed_sm"
restriction = "{settings.get("restriction", "default")}"
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
    evaluate = plan_export.NativeExecutor.evaluate

    def planted(self, points, scales, *args, **kw):
        results = evaluate(self, points, scales, *args, **kw)
        wards = kw.get("ward") or [None] * len(results)
        return _plant(results, wards, kind, **where)

    def run(detection):
        with monkeypatch.context() as patch:
            patch.setattr(plan_export.NativeExecutor, "evaluate", planted)
            if not detection:
                _no_detection(patch)
            report = check(card, **settings.get("options", {}))
        (process,) = report.processes
        return {(row.check, row.subject): row for row in process.rows}, process.status

    (on, status_on), (off, status_off) = run(True), run(False)
    assert {k: r.verdict for k, r in on.items()} == {
        k: r.verdict for k, r in off.items()
    }
    assert status_on == status_off
    assert all(
        "unstable at these parameters" not in (r.reason or "") for r in off.values()
    )
    return on


def test_check_fails_the_unstable_top_finite_cell_with_the_hint(tmp_path, monkeypatch):
    """``pyamplicol check`` of g g > t t~ [QED] (the earlier skip removed):
    the c = 1 Ward rows FAIL on their finite cell, the reason carrying the
    hint; their Born and pole cells pass; the c = i rows pass."""

    from pyamplicol.loops.v2 import checks

    rows = _check(tmp_path, monkeypatch, "g g > t t~", "{ QCD = 2, QED = 0 }")
    for leg in (1, 2):
        failing = rows[("ward", f"leg {leg}, c = 1")]
        assert failing.verdict == checks.FAIL and HINT in failing.reason
        cells = {cell["label"]: cell["verdict"] for cell in failing.cells}
        assert cells["QCD^4 QED^2 finite"] == checks.FAIL
        assert cells["QCD^4 QED^2 1/eps"] == checks.PASS
        assert cells["Born QCD^4"] == checks.PASS
        assert rows[("ward", f"leg {leg}, c = i")].verdict == checks.PASS


def test_check_passes_a_stable_top_in_full(tmp_path, monkeypatch):
    """The same on a stable spectrum (MW = 180, MZ = 200 at generation):
    every Ward row passes, no hint."""

    from pyamplicol.loops.v2 import checks

    rows = _check(
        tmp_path,
        monkeypatch,
        "g g > t t~",
        "{ QCD = 2, QED = 0 }",
        fixed={"MW": "180", "MZ": "200"},
    )
    ward_rows = [row for (check, _), row in rows.items() if check == "ward"]
    assert ward_rows and all(row.verdict == checks.PASS for row in ward_rows)
    assert all("unstable" not in (row.reason or "") for row in ward_rows)


@pytest.mark.parametrize("kind", ["born", "double"])
def test_check_fails_planted_born_and_pole_residuals(tmp_path, monkeypatch, kind):
    """The plantings through the CLI's Ward reducer on leg 1, c = i only:
    that row FAILS; the process fails."""

    from pyamplicol.loops.v2 import checks

    rows = _check(
        tmp_path,
        monkeypatch,
        "g g > t t~",
        "{ QCD = 2, QED = 0 }",
        kind,
        where={"only": (1, (0, 1))},
    )
    assert rows[("ward", "leg 1, c = i")].verdict == checks.FAIL
    assert rows[("ward", "leg 2, c = i")].verdict == checks.PASS


def test_check_fails_a_small_nonzero_pole(tmp_path, monkeypatch):
    """A stable top (MW = 180, MZ = 200 at generation) at sqrt(s) = 346.61,
    1 % of the QED single pole planted: the Ward rows FAIL at K = 1e-5."""

    from pyamplicol.loops.v2 import checks

    rows = _check(
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


def test_check_hints_per_substituted_leg(tmp_path, monkeypatch):
    """u d~ > g a w+ [QED] with an untagged photon: the gluon's Ward rows
    pass with no hint (the W carries no colour); the photon's rows FAIL on
    their finite cell, the hint naming the unstable W."""

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
    photon = [rows[("ward", f"leg 4, c = {c}")] for c in ("1", "i")]
    assert {row.verdict for row in photon} <= {checks.PASS, checks.FAIL}
    for row in photon:
        if row.verdict == checks.FAIL:
            assert "external leg 5 (W+) is unstable at these parameters" in row.reason
    assert any(row.verdict == checks.FAIL for row in photon)


def test_check_fails_a_qcd_sector_planting_of_a_mixed_request(tmp_path, monkeypatch):
    """g g > t t~ [QCD QED]: +0.1 in the pure QCD^6 finite gluon Ward cell
    (leg 1, c = i): that cell FAILS."""

    from pyamplicol.loops.v2 import checks

    rows = _check(
        tmp_path,
        monkeypatch,
        "g g > t t~",
        "{ QCD = 2, QED = 0 }",
        "finite",
        corrections='["QCD", "QED"]',
        where={"sector": QCD6, "only": (1, (0, 1))},
    )
    planted = rows[("ward", "leg 1, c = i")]
    assert planted.verdict == checks.FAIL
    cells = {cell["label"]: cell["verdict"] for cell in planted.cells}
    assert cells["QCD^6 finite"] == checks.FAIL


@pytest.fixture(scope="module")
def ckm(tmp_path_factory, loop_native):
    """g g > t t~ [QED] on loop_qcd_qed_sm with the ckm restriction
    (Wolfenstein inputs, MB = 4.7), every width zero, Catani enabled."""

    from pyamplicol.models.loading import compile_model_source

    root = tmp_path_factory.mktemp("loop-qcd-qed-sm-ckm")
    compiled = compile_model_source(
        "loop_qcd_qed_sm", restriction="ckm", cache_dir=root / "cache"
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
    return NativeExecutor(slice_, inputs="native", forward=False, catani=True)


def test_a_channel_without_coupling_is_no_hint(monkeypatch, ckm):
    """The ckm restriction at MT = 82, MB = 4.7, MW = 80.419: t -> W+ b is
    closed (85.119 GeV). With AWS = 0 (Vtd = Vts = 0) t -> W+ d and W+ s have
    vanishing couplings: no unstable leg; gluon leg 1, c = 1 passes (about
    6e-32 of the scale), and a planted 0.1 finite failure there FAILS without
    a hint. With the restriction's AWS (Vtd != 0) t -> W+ d is open and
    coupled: the same planted cell FAILS with the hint. (The c = i rows are
    not this test's: on this restriction they keep a dispersive residue of
    about 1e-6 of the scale with or without the top's decay.)"""

    point = _point("82")
    one = [(1, 0)]
    stable = {**PARAMETERS, "MT": "82", "ymt": "82", "AWS": "0"}
    assert ward.unstable_external_legs(ckm.slice, [1], stable) == ()
    rows, check = _ward(monkeypatch, ckm, point, stable, legs=[1], factors=one)
    assert check["unstable"] == () and check["passed"] is True
    rows, check = _ward(
        monkeypatch,
        ckm,
        point,
        stable,
        "finite",
        legs=[1],
        factors=one,
        sector=MIXED,
        only=(1, (1, 0)),
    )
    assert rows[(1, (1, 0))]["passed"] is False and "hint" not in rows[(1, (1, 0))]
    coupled = {**PARAMETERS, "MT": "82", "ymt": "82"}
    found = ward.unstable_external_legs(ckm.slice, [1], coupled)
    assert {(leg.leg, leg.channel) for leg in found} == {
        (3, ("W+", "d")),
        (4, ("W-", "d~")),
    }
    rows, check = _ward(
        monkeypatch,
        ckm,
        point,
        coupled,
        "finite",
        legs=[1],
        factors=one,
        sector=MIXED,
        only=(1, (1, 0)),
    )
    assert rows[(1, (1, 0))]["passed"] is False
    assert "open channel W+ d" in rows[(1, (1, 0))]["hint"]


def test_check_fails_a_planting_on_the_ckm_diagonal_card(tmp_path, monkeypatch):
    """The same stable top through ``pyamplicol check`` (ckm restriction,
    MT = ymt = 82 and AWS = 0 fixed): the planted 0.1 finite cell on gluon
    leg 1, c = 1 FAILS without a hint."""

    from pyamplicol.loops.v2 import checks

    rows = _check(
        tmp_path,
        monkeypatch,
        "g g > t t~",
        "{ QCD = 2, QED = 0 }",
        "finite",
        restriction="ckm",
        fixed={"MT": "82", "ymt": "82", "AWS": "0"},
        where={"sector": MIXED, "only": (1, (1, 0))},
    )
    planted = rows[("ward", "leg 1, c = 1")]
    assert planted.verdict == checks.FAIL
    assert "unstable" not in (planted.reason or "")
    cells = {cell["label"]: cell["verdict"] for cell in planted.cells}
    assert cells["QCD^4 QED^2 finite"] == checks.FAIL


def test_a_qcd_loop_against_an_electroweak_born_is_judged(
    monkeypatch, tmp_path_factory, loop_native
):
    """u u~ > t t~ g, Born limits {QCD: 3, QED: 2}, corrections (QCD, QED),
    the exact loop amplitude order {QCD: 5, QED: 0}: a pure QCD loop whose
    interference with the electroweak Born gives QCD^6 QED^2. A planted 0.1
    finite failure there (gluon leg 5, c = i) FAILS."""

    from pyamplicol.models.loading import compile_model_source

    root = tmp_path_factory.mktemp("uux-ttxg")
    compiled = compile_model_source(
        "loop_qcd_qed_sm", restriction="default", cache_dir=root / "cache"
    )
    request = SliceRequest(
        "u u~ > t t~ g",
        {"QCD": 3, "QED": 2},
        {"QCD": 5, "QED": 0},
        corrections=("QCD", "QED"),
        fixed_parameters=FIXED,
        scale_parameter="MU_R",
    )
    executor = NativeExecutor(
        ward.ward_slice(compiled, request, loop_native),
        inputs="native",
        forward=False,
        catani=True,
    )
    (point,) = exact_points.generate([0, 0, "173.3", "173.3", 0], count=1)
    point = [[exact_points.decimal_string(x) for x in p] for p in point]
    rows, check = _ward(
        monkeypatch,
        executor,
        point,
        PARAMETERS,
        "finite",
        legs=[5],
        sector=(("QCD", 6), ("QED", 2)),
        only=(5, (0, 1)),
    )
    assert rows[(5, (0, 1))]["passed"] is False
    assert check["passed"] is False
