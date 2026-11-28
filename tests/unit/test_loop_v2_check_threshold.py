# SPDX-License-Identifier: 0BSD
"""The threshold rule's review cases (``loops.v2.checks``, ``induced``,
``goldstone``): each is a reproduction of a defect of the first threshold
head, run through the production judges with scripted carrier outputs.

* **A physical reference is never hidden by the term scale**: a Catani pole
  1e-3 off its prediction fails whatever its parts' cancellation (bare
  2e7, UV -2e7).
* **A cancelled colour norm is measured, not zero**: ||x||_G for G = [[9,
  3], [3, 1]] and x = (1, -2.999999997) is 3e-9 (the form's terms are of
  order 9), also on a rank-deficient metric of four colour flows; a pole
  that small against a finite amplitude of 3e-6 fails.
* **No required operand is dropped or called vacuous**: a Goldstone-side
  row no vector row maps to is inconclusive; a Ward row whose physical
  reference is not a number is inconclusive even where R = T = 0.
* **The ladder is per row**: two Ward sectors that each pass at one
  carrier pass; a sector failing in binary64 and absent from the
  double-double payload is inconclusive; the loop-induced probes keep each
  row's first pass, and their physical reference is formed at the same
  carrier and point as the residues.
* **A refusal never aborts and never ends the ladder early**: a refused
  physical-floor evaluation at generation is recorded inconclusive; a
  double-double refusal leaves the arbitrary-precision rung to decide; a
  refused estimate-only rotation never vetoes the Goldstone comparison.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace as NS

import pytest

from pyamplicol.loops.v2 import checks

pytestmark = pytest.mark.loop_fast

K = 1e-5


def _laurent(*values):
    return NS(coefficients=list(values))


# ------------------------------------------------- 1. the physical scale


def test_a_per_mille_pole_violation_fails_whatever_the_parts_cancel(monkeypatch):
    """C = 1, V = 1.001, bare = 20000001.001, UV = -20000000 (one sector,
    the single pole): R / P = 1e-3, a failure at K = 1e-5 (the term scale
    T = 2e7 does not enter: P = max(|C|, |V|) is a resolved analytic
    reference)."""

    from pyamplicol.loops.v2 import checks, induced, plan_export, ward
    from pyamplicol.loops.v2.assemble import Precision

    sector = (("QCD", 4),)

    def evaluate(_executor, _point, _scale, _carrier, _checks):
        return NS(
            stability=None,
            components={
                "virtual": {sector: _laurent(0.0, 1.001, -3.0)},
                "bare": {sector: _laurent(0.0, 20000001.001, -3.0)},
                "uv": {sector: _laurent(0.0, -20000000.0, 0.0)},
            },
            ir_poles={sector: (1.0, -3.0)},
        )

    monkeypatch.setattr(plan_export, "NativeExecutor", lambda *a, **k: None)
    monkeypatch.setattr(checks, "_evaluate", evaluate)
    monkeypatch.setattr(ward, "gauge_legs", lambda _target: ())
    monkeypatch.setattr(induced, "goldstone_applicability", lambda _t: "n/a")
    target = NS(unpredicted_sectors=lambda: {})
    with checks.tolerating(K):
        rows = checks.born_interfered_rows(target, [(None, 1)], (Precision.double(),))
    (single,) = [row for row in rows if row.subject == "QCD^4 1/eps"]
    assert single.verdict == checks.FAIL, single
    assert single.deviation == pytest.approx(1e-3, rel=1e-2)


# ------------------------------------------------ 2. the colour norm


def _numbers():
    from pyamplicol.loops.v2.assemble import Precision, _Numbers

    return _Numbers(Precision.double())


def test_a_cancelled_colour_norm_is_measured():
    """G = [[9, 3], [3, 1]]: ||x||_G = |3 x_1 + x_2|; for the pole vector
    (1, -2.999999997) the carrier's form cancels from terms of order 9 to
    9e-18, where the norm is 3e-9 (never zero); a rank-deficient metric of
    four colour flows (G = W^T W, W of rank 3) likewise."""

    from pyamplicol.loops.v2.induced import g_norm

    numbers = _numbers()
    gram = [[9 + 0j, 3 + 0j], [3 + 0j, 1 + 0j]]
    pole = [1 + 0j, -2.999999997 + 0j]
    exact = abs(3 * Fraction(1) + Fraction(-2.999999997))
    assert g_norm(pole, gram, numbers) == pytest.approx(float(exact), rel=1e-12)
    assert g_norm([1e-6 + 0j, 0j], gram, numbers) == pytest.approx(3e-6)
    # Four flows spanning three colour dimensions (SU(3) colour-flow
    # redundancy): W columns w1, w2, w3, w4 = w1 + w2 - w3.
    w = [[3, 1, 1, 3], [1, 3, 1, 3], [1, 1, 3, -1]]
    flows = [
        [sum(w[r][i] * w[r][j] for r in range(3)) for j in range(4)] for i in range(4)
    ]
    metric = [[complex(value) for value in row] for row in flows]
    near_null = [1 + 0j, 1 + 0j, -1 + 0j, -1 + 2e-9 + 0j]
    found = g_norm(near_null, metric, numbers)
    exact_form = sum(
        Fraction(near_null[i].real)
        * Fraction(flows[i][j])
        * Fraction(near_null[j].real)
        for i in range(4)
        for j in range(4)
    )
    assert found > 0
    assert found == pytest.approx(float(exact_form) ** 0.5, rel=1e-9)


def test_a_pole_three_orders_below_its_finite_amplitude_fails():
    """The finiteness judge on the cancelled norm: P = ||(1e-6, 0)||_G =
    3e-6 (the finite amplitude), R = 3e-9 (the pole), T = 6: R / P = 1e-3,
    a failure at K = 1e-5 (the finiteness probe's reference is the physical
    finite amplitude, a measured nonzero reference)."""

    from pyamplicol.loops.v2 import checks, induced

    numbers = _numbers()
    gram = [[9 + 0j, 3 + 0j], [3 + 0j, 1 + 0j]]
    evaluation = NS(
        native_budget={},
        gram=gram,
        numbers=numbers,
        poles=True,
        slice=NS(amplitude=[0, 0]),
        amplitude_vectors={
            "row": [[1e-6 + 0j, 1 + 0j, 0j], [0j, -2.999999997 + 0j, 0j]]
        },
    )
    floors = induced.RowFloors({"row": [6.0, 6.0, 6.0]})
    estimates = induced.amplitude_estimates(evaluation, 2.0**-53, floors, [])
    references = induced.physical_references(estimates)
    measures = induced.probe_measures(estimates, floors, 1, references, 3)
    result = induced.ProbeResult(
        "finiteness", induced.judged_cells(measures, K), tolerance=K
    )
    assert result.verdict == checks.FAIL
    cell = result.final[("row", 1)]
    assert cell.measure.residue == pytest.approx(3e-9, rel=1e-6)
    assert cell.ratio == pytest.approx(1e-3, rel=1e-6)


# ------------------------------------------- 3. operands and vacuity


class _Amplitude(list):
    """A one-tensor amplitude basis stand-in."""

    tensors = ("t",)


def _side(vectors):
    return NS(
        native_budget={},
        gram=[[1 + 0j]],
        numbers=_numbers(),
        poles=False,
        slice=NS(amplitude=_Amplitude([0])),
        amplitude_vectors=vectors,
    )


def _goldstone_stubs(monkeypatch, vector, goldstone_side, floors_g, rotation=None):
    """``goldstone.probe``'s runs scripted: the vector side ``vector``, the
    Goldstone side ``goldstone_side`` (by executor), the Goldstone rows'
    floors, M/E = 1; ``rotation``: a refusal text for the estimate-only
    rotated runs."""

    from pyamplicol.loops.v2 import goldstone, induced

    def runs(executor, runs_, _scale, _parameters, precision, frame, *_a):
        if rotation and frame is None:
            # A rotated run (no re-test frame) through the all-or-nothing
            # route: refused.
            raise induced.ProbePointRefused(rotation)
        evaluation = vector if executor == "vector" else goldstone_side
        return precision, tuple([evaluation] * len(runs_))

    def batch(executor, runs_, _scale, _parameters, precision, _frame, *_a):
        evaluation = vector if executor == "vector" else goldstone_side
        failures = {0: rotation} if rotation else {}
        return precision, [evaluation] * len(runs_), failures

    monkeypatch.setattr(induced, "_probe_runs", runs)
    monkeypatch.setattr(induced, "_probe_batch", batch)
    monkeypatch.setattr(induced, "probe_floors", lambda *_a, **_k: (floors_g, {}))
    monkeypatch.setattr(goldstone, "_mass_over_energy", lambda *_a: Decimal(1))


_POINT = [
    ["500", "0", "0", "500"],
    ["500", "0", "0", "-500"],
    ["500", "300", "0", "400"],
    ["500", "-300", "0", "-400"],
]


def test_a_goldstone_row_no_vector_row_maps_to_is_inconclusive(monkeypatch):
    """At M/E = 1 a matching finite unit row passes; a scalar-only row of
    magnitude 1e-3 and term scale 1 (no vector row maps to it) is a missing
    operand: the probe is inconclusive, never a pass at residue zero."""

    from pyamplicol.loops.v2 import goldstone, induced
    from pyamplicol.loops.v2.assemble import Precision
    from pyamplicol.loops.v2.stability import StabilityChecks

    order = (("QED", 2),)
    vector_row = (order, ((0, 1), (1, 1), (2, 1)))
    goldstone_row = (order, ((0, 1), (1, 1), (2, 0)))
    scalar_only = (order, ((0, -1), (1, 1), (2, 0)))
    vector = _side({vector_row: [[1 + 0j]]})
    side = _side({goldstone_row: [[1 + 0j]], scalar_only: [[1e-3 + 0j]]})
    floors_g = induced.RowFloors({goldstone_row: [1.0], scalar_only: [1.0]})
    floors_g.finite = {goldstone_row: 1.0, scalar_only: 1e-3}
    _goldstone_stubs(monkeypatch, vector, side, floors_g)
    physical = induced.RowFloors({vector_row: [1.0]})
    physical.finite = {vector_row: 1.0}
    result = goldstone.probe(
        "vector",
        "goldstone",
        _POINT,
        1,
        3,
        precision=Precision.double(),
        checks=StabilityChecks((), reduction_direction=True),
        physical=physical,
        tolerance=K,
    )
    assert result.verdict == "inconclusive", result.final
    assert any("no vector row maps to" in text for text in result.undefined)


def test_a_ward_row_whose_physical_reference_is_not_a_number_is_inconclusive(
    monkeypatch,
):
    """A NaN physical virtual coefficient beside a zero substituted one and
    no term (R = T = 0 otherwise) with a passing Born row: the required
    operand P is not a number, so the row is inconclusive (vacuity is only
    decided for complete, finite rows) and so is the Ward check."""

    from pyamplicol.loops.v2 import checks, induced, plan_export, ward
    from pyamplicol.loops.v2.assemble import Precision

    sector = (("QCD", 4),)

    def evaluate(_executor, _point, _scale, _carrier, _checks):
        return NS(
            stability=None,
            components={"virtual": {sector: _laurent(0.0, 2.0, -3.0)}},
            ir_poles={sector: (2.0, -3.0)},
        )

    def ward_check(_executor, _point, _scale, _name, *, legs, factors, **_options):
        physical = NS(
            components={
                "virtual": {sector: _laurent(float("nan"), 0.0, 0.0)},
                "bare": {sector: _laurent(0.0, 0.0, 0.0)},
            },
            born={sector: 4.0},
            loop_born=None,
            stability=None,
        )
        result = NS(
            components={"virtual": {sector: _laurent(0.0, 0.0, 0.0)}},
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
    monkeypatch.setattr("pyamplicol.loops.v2.ward.hint_legs", lambda *a, **k: {})
    target = NS(unpredicted_sectors=lambda: {})
    with checks.tolerating(K):
        rows = checks.born_interfered_rows(target, [(None, 1)], (Precision.double(),))
    wards = [row for row in rows if row.check == "ward"]
    assert len(wards) == 2
    assert {row.verdict for row in wards} == {checks.INCONCLUSIVE}, wards


# ------------------------------------------------ 4. the per-row ladder


def _scripted_ward(monkeypatch, physical_of, result_of):
    """``ward.ward_check`` scripted per carrier: the physical and the
    substituted evaluation of every (leg, factor)."""

    from pyamplicol.loops.v2 import checks, induced, plan_export, ward

    sector = (("QCD", 4),)

    def evaluate(_executor, _point, _scale, _carrier, _checks):
        return NS(
            stability=None,
            components={
                "virtual": {sector: _laurent(0.0, 2.0, -3.0)},
                "bare": {sector: _laurent(0.0, 2.0, -3.0)},
            },
            ir_poles={sector: (2.0, -3.0)},
        )

    def ward_check(_executor, _point, _scale, _name, *, legs, factors, **options):
        name = options["precision"].arithmetic
        labels = [(leg, factor) for leg in legs for factor in factors]
        return {
            "physical": physical_of(name),
            "results": [result_of(name)] * len(labels),
            "rows": [{"leg": leg, "factor": factor} for leg, factor in labels],
        }

    monkeypatch.setattr(plan_export, "NativeExecutor", lambda *a, **k: None)
    monkeypatch.setattr(checks, "_evaluate", evaluate)
    monkeypatch.setattr(ward, "gauge_legs", lambda _target: [3])
    monkeypatch.setattr(ward, "ward_check", ward_check)
    monkeypatch.setattr(induced, "goldstone_applicability", lambda _t: "n/a")
    monkeypatch.setattr("pyamplicol.loops.v2.ward.hint_legs", lambda *a, **k: {})


def _ward_rows(carriers):
    from pyamplicol.loops.v2 import checks

    target = NS(unpredicted_sectors=lambda: {})
    with checks.tolerating(K):
        rows = checks.born_interfered_rows(target, [(None, 1)], carriers)
    return [row for row in rows if row.check == "ward"]


def test_two_ward_sectors_that_each_pass_at_one_carrier_pass(monkeypatch):
    """Sectors A and B at (1e-6, 1e-3) of their physical virtual in binary64
    and (1e-3, 1e-6) in double-double: A passed in binary64 and keeps that
    pass, B passes in double-double: the check passes (the whole (leg,
    factor) is not re-judged by its last carrier)."""

    from pyamplicol.loops.v2 import checks
    from pyamplicol.loops.v2.assemble import Precision

    a, b = (("QCD", 4),), (("QCD", 2), ("QED", 2))

    def physical_of(_name):
        return NS(
            components={"virtual": {a: _laurent(1.0), b: _laurent(1.0)}},
            born={a: 1.0},
            loop_born=None,
            stability=None,
        )

    def result_of(name):
        x, y = (1e-6, 1e-3) if name == "double" else (1e-3, 1e-6)
        return NS(
            components={"virtual": {a: _laurent(x), b: _laurent(y)}},
            born={a: 1.0},
            loop_born={a: 0.0},
            stability=None,
        )

    _scripted_ward(monkeypatch, physical_of, result_of)
    wards = _ward_rows((Precision.double(), Precision.double_double()))
    assert {row.verdict for row in wards} == {checks.PASS}, wards


def test_a_failed_ward_sector_absent_from_the_next_carrier_is_inconclusive(
    monkeypatch,
):
    """A Born Ward sector at 1e-3 in binary64 that vanishes from the
    double-double payload, beside a clean sector: never a pass."""

    from pyamplicol.loops.v2 import checks
    from pyamplicol.loops.v2.assemble import Precision

    a, b = (("QCD", 4),), (("QCD", 2), ("QED", 2))

    def physical_of(name):
        born = {a: 1.0, b: 1.0} if name == "double" else {a: 1.0}
        return NS(
            components={"virtual": {a: _laurent(1.0)}},
            born=born,
            loop_born=None,
            stability=None,
        )

    def result_of(name):
        loop_born = {a: 0.0, b: 1e-3} if name == "double" else {a: 0.0}
        return NS(
            components={"virtual": {a: _laurent(1e-12)}},
            born=physical_of(name).born,
            loop_born=loop_born,
            stability=None,
        )

    _scripted_ward(monkeypatch, physical_of, result_of)
    wards = _ward_rows((Precision.double(), Precision.double_double()))
    assert {row.verdict for row in wards} == {checks.INCONCLUSIVE}, wards
    assert all("has no such row" in row.reason for row in wards)


def test_the_probes_keep_each_rows_first_pass_up_the_ladder(monkeypatch):
    """Two helicity rows of one loop-induced probe at R / P (1e-6, 1e-3) in
    binary64 and (1e-3, 1e-6) in double-double: each passed at one carrier,
    the probe passes; the physical run is in every carrier's batch (P at the
    same point and carrier as R)."""

    from pyamplicol.loops.v2 import checks, induced
    from pyamplicol.loops.v2.assemble import Precision

    batches = []

    def probe_results(_executor, _point, _scale, wards, **options):
        carrier = options["precision"]
        batches.append((carrier.arithmetic, list(wards)))
        x, y = (1e-6, 1e-3) if carrier.arithmetic == "double" else (1e-3, 1e-6)
        measures = {
            ("A", 1): checks.Measure("A k=1", x, 1.0, 1.0),
            ("B", 1): checks.Measure("B k=1", y, 1.0, 1.0),
        }
        return [
            induced.ProbeResult(
                "finiteness", induced.judged_cells(measures, K, carrier), tolerance=K
            )
            for _ward in wards
        ]

    monkeypatch.setattr(induced, "probe_results", probe_results)
    entries, results = induced.point_probes(
        None,
        _POINT,
        1,
        [],
        (Precision.double(), Precision.double_double()),
        {},
        tolerance=K,
    )
    (result,) = results
    assert result.verdict == checks.PASS, result.final
    assert [name for name, _wards in batches] == ["double", "double-double"]
    assert entries[0]["passed"] and entries[0]["verdict"] == "pass"


def test_the_physical_reference_is_formed_in_every_carriers_batch(monkeypatch):
    """``probe_results`` evaluates the physical amplitude (Ward value None)
    in the same batch as a Ward probe, so P is at the same point and carrier
    as the residue."""

    from pyamplicol.loops.v2 import induced
    from pyamplicol.loops.v2.assemble import Precision
    from pyamplicol.loops.v2.stability import StabilityChecks

    seen = []

    def batch(_executor, runs, _scale, _parameters, precision, frame, *_a):
        seen.append([ward for _point, ward in runs])
        return precision, [None] * len(runs), dict.fromkeys(range(len(runs)), "x")

    monkeypatch.setattr(induced, "_probe_batch", batch)
    ward = (1, (Fraction(1), Fraction(0)))
    found = induced.probe_results(
        None,
        _POINT,
        1,
        [ward],
        precision=Precision.double(),
        checks=StabilityChecks((), reduction_direction=True),
        physical={},
        tolerance=K,
    )
    assert seen == [[ward, None]]
    assert isinstance(found[0], str)


# ----------------------------------------------------- 5. refusals


def test_a_refused_physical_floor_at_generation_is_recorded_inconclusive(
    monkeypatch, caplog
):
    """Every carrier refuses the physical evaluation that forms the row
    floors: the generation-time probes are recorded inconclusive with the
    reason, nothing escapes as an exception."""

    from pyamplicol.loops.v2 import induced, ward

    legs = [NS(label=1, pdg=21, is_initial=True), NS(label=2, pdg=21, is_initial=True)]
    slice_ = NS(
        amplitude=NS(colour_zero=False),
        blocks=NS(process=NS(legs=legs), kernel_variant="full"),
        request=NS(process="g g > h"),
    )

    def refused(*_args, **_options):
        raise induced.ProbePointRefused(
            "the probe point failed: forced (both carriers)"
        )

    monkeypatch.setattr(induced, "probe_request", lambda s: (s.request, ()))
    monkeypatch.setattr(ward, "ward_slice", lambda *a, **k: slice_)
    monkeypatch.setattr(
        induced, "probe_point", lambda target, momenta, digits: (_POINT, 1.0)
    )
    monkeypatch.setattr(induced, "probe_legs", lambda target: [1])
    monkeypatch.setattr(induced, "probe_floors", refused)
    monkeypatch.setattr(induced, "_complex_mass", lambda _slice: False)
    monkeypatch.setattr(
        induced,
        "_goldstone_probes",
        lambda *a, **k: {"results": [], "entries": [], "seconds": {}, "record": None},
    )
    from pyamplicol.loops.v2 import plan_export

    monkeypatch.setattr(plan_export, "NativeExecutor", lambda *a, **k: None)
    record = induced.generation_probes(slice_, None, None, [_POINT], tolerance=K)
    assert not record["finiteness"]["passed"] and not record["ward"]["passed"]
    assert "failed" not in record
    assert all("physical floors" in line for line in record["inconclusive"])


def test_a_double_double_refusal_leaves_the_arbitrary_rung_to_decide(monkeypatch):
    """A binary64 Catani miss (1.001 against 1) and a double-double refusal:
    the configured 64-digit rung still runs and decides (1 against 1)."""

    from pyamplicol.loops.v2 import checks, induced, plan_export, ward
    from pyamplicol.loops.v2.assemble import Precision

    sector = (("QCD", 4),)

    def evaluate(_executor, _point, _scale, carrier, _checks):
        if carrier.arithmetic == "double-double":
            raise plan_export.FailedPoints([None], {0: ["refused"]})
        single = 1.001 if carrier.arithmetic == "double" else 1.0
        return NS(
            stability=None,
            components={
                "virtual": {sector: _laurent(0.0, single, -3.0)},
                "bare": {sector: _laurent(0.0, single, -3.0)},
            },
            ir_poles={sector: (1.0, -3.0)},
        )

    monkeypatch.setattr(plan_export, "NativeExecutor", lambda *a, **k: None)
    monkeypatch.setattr(checks, "_evaluate", evaluate)
    monkeypatch.setattr(ward, "gauge_legs", lambda _target: ())
    monkeypatch.setattr(induced, "goldstone_applicability", lambda _t: "n/a")
    target = NS(unpredicted_sectors=lambda: {})
    rung = checks.Rung(lambda index, carrier: (None, 1))
    with checks.tolerating(K):
        rows = checks.born_interfered_rows(
            target,
            [(None, 1)],
            (Precision.double(), Precision.double_double()),
            rung,
        )
    (single,) = [row for row in rows if row.subject == "QCD^4 1/eps"]
    assert (single.verdict, single.carrier) == (checks.PASS, "arbitrary"), single


def test_a_refused_estimate_only_rotation_never_vetoes_the_goldstone_comparison(
    monkeypatch,
):
    """The rotated runs only feed the reported estimate: one refused leaves
    the direct comparison (a clean unit row) to decide, a pass."""

    from pyamplicol.loops.v2 import goldstone, induced
    from pyamplicol.loops.v2.assemble import Precision
    from pyamplicol.loops.v2.stability import RECOMMENDED_CHECKS

    order = (("QED", 2),)
    vector_row = (order, ((0, 1), (1, 1), (2, 1)))
    goldstone_row = (order, ((0, 1), (1, 1), (2, 0)))
    vector = _side({vector_row: [[1 + 0j]]})
    side = _side({goldstone_row: [[1 + 0j]]})
    floors_g = induced.RowFloors({goldstone_row: [1.0]})
    floors_g.finite = {goldstone_row: 1.0}
    _goldstone_stubs(monkeypatch, vector, side, floors_g, rotation="refused rotation")
    monkeypatch.setattr(induced, "rotation_errors", lambda *a: {})
    physical = induced.RowFloors({vector_row: [1.0]})
    physical.finite = {vector_row: 1.0}
    result = goldstone.probe(
        "vector",
        "goldstone",
        _POINT,
        1,
        3,
        precision=Precision.double(),
        checks=RECOMMENDED_CHECKS,
        physical=physical,
        tolerance=K,
    )
    assert result.verdict == "pass", result.final


# ------------------------------------------ 6. stored verdicts and tools


def test_the_ward_tool_reports_an_empty_leg_set_as_nothing_tested(
    monkeypatch, tmp_path
):
    """``tools/loop_v2_ward.py`` on a process with no applicable leg (H -> b
    b~: no external massless gauge boson): "nothing tested" (exit code 3),
    never a pass and never a crash."""

    import json

    from pyamplicol.loops.v2 import plan_export, ward
    from tools import loop_v2_operation_counts, loop_v2_ward
    from tools.developer import prepare_source_runtime
    from tools.loop_benchmark import pyamplicol_v2, streams

    target = NS(
        normalisation=NS(average=1), blocks=NS(process=NS(legs=[])), process="h > b b~"
    )
    monkeypatch.setattr(loop_v2_ward, "_git", lambda *a: "")
    monkeypatch.setattr(
        prepare_source_runtime, "_native_build_inputs_digest", lambda root: "x"
    )
    monkeypatch.setattr(loop_v2_operation_counts, "compile_loop_sm", lambda *a: None)
    monkeypatch.setattr(
        pyamplicol_v2,
        "_request",
        lambda *a: NS(process="h > b b~", particle_veto=()),
    )
    monkeypatch.setattr(pyamplicol_v2, "_parameters", lambda name: {})
    monkeypatch.setattr(ward, "ward_slice", lambda *a: target)
    monkeypatch.setattr(ward, "gauge_legs", lambda slice_: ())
    monkeypatch.setattr(
        ward,
        "ward_check",
        lambda *a, **k: {
            "physical": NS(born={}, components={"virtual": {}}, stability=None),
            "results": [],
            "rows": [],
        },
    )
    monkeypatch.setattr(plan_export, "NativeExecutor", lambda *a, **k: None)
    monkeypatch.setattr(streams, "load", lambda name: {"mu_r": ["1"]})
    monkeypatch.setattr(streams, "exact", lambda stream, index: _POINT)
    output = tmp_path / "w.json"
    status = loop_v2_ward.main(
        [
            "h_bbx",
            "--points",
            "0",
            "--tolerance",
            "1e-5",
            "--scratch",
            str(tmp_path),
            "--json",
            str(output),
        ]
    )
    record = json.loads(output.read_text())
    assert status == 3 and record["status"] == "nothing tested"
    assert record["passed"] is False and record["legs"] == []


# ------------------------------------------- a helicity row below resolution


def _laddered(rows_by_carrier, floor_roundoff="binary64"):
    """``induced.ladder`` over binary64 then double-double for one probe whose
    rows' measures per carrier are ``rows_by_carrier[carrier name]`` (key ->
    (R, P, E_P, T) or a ``checks.Measure``), the term floors produced in
    binary64 (``floor_roundoff``: "binary64", or None for not recorded);
    returns the final rows (``ProbeResult.final``)."""

    from pyamplicol.loops.v2 import induced
    from pyamplicol.loops.v2.assemble import Precision

    k = 1e-5
    floors = None if floor_roundoff is None else Precision.double().unit_roundoff
    cells: dict = {}
    for carrier in (Precision.double(), Precision.double_double()):
        rows = rows_by_carrier.get(carrier.arithmetic)
        if rows is None:
            continue
        measures = {
            key: (
                value
                if isinstance(value, checks.Measure)
                else checks.Measure(
                    str(key), value[0], value[1], value[3], physical_error=value[2]
                )
            )
            for key, value in rows.items()
        }
        result = induced.ProbeResult(
            "finiteness",
            induced.judged_cells(measures, k, carrier),
            tolerance=k,
            **(
                {"floor_roundoff": floors}
                if floors is not None
                and "floor_roundoff" in induced.ProbeResult.__dataclass_fields__
                else {}
            ),
        )
        induced.ladder(cells, result, carrier, k)
        if not induced.pending(cells, [result]):
            break
    return induced.ProbeResult("finiteness", cells, tolerance=k).final


# g g > Z at the generator's probe point (h9): order (QCD 2, QED 1), k = 1.
_ORDER = (("QCD", 2), ("QED", 1))
_LARGE = ((_ORDER, "(-,-,0)"), 1)  # T = 23.5, P at binary64 noise
_FORBIDDEN = ((_ORDER, "(-,+,-)"), 1)  # angular momentum: T = 1.03e-30
_GG_Z = {
    "double": {
        _LARGE: (1.04e-15, 2.59e-15, 4.9e-14, 23.5),
        _FORBIDDEN: (1.73e-31, 2.19e-31, 3.3e-15, 1.03e-30),
    },
    "double-double": {
        _LARGE: (3.13e-32, 3.02e-31, 1.91e-29, 23.5),
        _FORBIDDEN: (3.34e-31, 1.76e-31, 3.86e-30, 1.03e-30),
    },
}


def test_a_helicity_row_below_numerical_resolution_is_deferred_never_passed():
    """g g > Z's angular-momentum-forbidden row at the generator's probe point
    misses R < K P in both carriers, P within ten times its estimate and
    max(R, P, T) far below 10 min(u_floor, u_work) T_max (T_max = 23.5, the
    same order's k = 1 maximum): deferred in binary64, deferred again in
    double-double, INCONCLUSIVE at the last carrier ("helicity row below
    numerical resolution"), never a pass, never term-relative, never
    vacuous. Its large neighbour settles as before (P collapses)."""

    from pyamplicol.loops.v2 import induced

    final = _laddered(_GG_Z)
    row = final[_FORBIDDEN]
    assert row.verdict == checks.INCONCLUSIVE and row.carrier == "double-double"
    assert row.reason.startswith(induced.BELOW_RESOLUTION), row.reason
    assert "T_max 23.5" in row.reason and row.scale != checks.TERM_RELATIVE
    assert row.measure.residue == 3.34e-31 and row.measure.terms == 1.03e-30
    assert final[_LARGE].verdict == checks.PASS
    assert final[_LARGE].scale == checks.TERM_RELATIVE
    assert checks.aggregate(final) == checks.INCONCLUSIVE
    # Without the recorded producer precision of the floors nothing is
    # deferred: the ordinary failure stands.
    final = _laddered(_GG_Z, floor_roundoff=None)
    assert final[_FORBIDDEN].verdict == checks.FAIL


def test_a_wider_rung_that_resolves_the_reference_decides_a_deferred_row():
    """A row deferred in binary64 is judged by the ordinary rule on its
    double-double measurement: a resolved P with R < K P passes there; a
    resolved P with a significant R fails there."""

    resolved = {_FORBIDDEN: (1e-12, 1e-3, 1e-35, 1.03e-30), _LARGE: (0, 1, 1e-17, 23.5)}
    final = _laddered({"double": _GG_Z["double"], "double-double": resolved})
    assert final[_FORBIDDEN].verdict == checks.PASS
    assert final[_FORBIDDEN].scale == checks.PHYSICAL
    missed = {**resolved, _FORBIDDEN: (1e-6, 1e-3, 1e-35, 1.03e-30)}
    final = _laddered({"double": _GG_Z["double"], "double-double": missed})
    assert final[_FORBIDDEN].verdict == checks.FAIL


def test_resolved_or_significant_misses_are_never_deferred():
    """The deferral needs every operand at the resolution of the comparable
    helicities: a tiny but well-resolved nonzero helicity with a per-mille
    defect beside a large one fails; a flagged tiny P with an appreciable R
    fails; a row whose only large neighbour is in another loop order or
    Laurent coefficient fails; C = 1, V = 1.001 under a 2e7 term scale
    fails (P far above u T); a complete termless row stays vacuous."""

    small = ((_ORDER, "(+,-,+)"), 1)
    per_mille = {
        "double": {_LARGE: (0, 1, 1e-17, 23.5), small: (1e-16, 1e-13, 1e-29, 1e-13)},
        "double-double": {
            _LARGE: (0, 1, 1e-33, 23.5),
            small: (1e-16, 1e-13, 1e-45, 1e-13),
        },
    }
    assert _laddered(per_mille)[small].verdict == checks.FAIL
    large_r = {
        c: {_LARGE: rows[_LARGE], small: (1e-13, 1e-31, 1e-15, 1e-30)}
        for c, rows in _GG_Z.items()
    }
    assert _laddered(large_r)[small].verdict == checks.FAIL
    other = (("QCD", 4), ("QED", 0))
    spectators = {
        c: {
            ((other, "(-,-,0)"), 1): rows[_LARGE],
            ((_ORDER, "(-,-,0)"), 2): rows[_LARGE],
            _FORBIDDEN: rows[_FORBIDDEN],
        }
        for c, rows in _GG_Z.items()
    }
    assert _laddered(spectators)[_FORBIDDEN].verdict == checks.FAIL
    catani = ((_ORDER, "(-,-,-)"), 1)
    per_mille_pole = {c: {catani: (1e-3, 1.0, 1.0, 2e7)} for c in _GG_Z}
    assert _laddered(per_mille_pole)[catani].verdict == checks.FAIL
    termless = ((_ORDER, "(-,+,+)"), 1)
    final = _laddered(
        {c: {**rows, termless: (0.0, 0.0, 1e-15, 0.0)} for c, rows in _GG_Z.items()}
    )
    assert final[termless].verdict == checks.VACUOUS
    assert final[_FORBIDDEN].verdict == checks.INCONCLUSIVE


def test_a_known_zero_reference_or_incomplete_row_is_never_deferred():
    """The deferral applies only to a measured reference with complete
    operands: a known-zero reference keeps its term-relative failure, a row
    without E_P keeps its failure."""

    zero = checks.Measure(
        "zero", 1.73e-31, 0.0, 1.03e-30, physical_error=3.3e-15, zero_reference=True
    )
    no_estimate = checks.Measure("open", 1.73e-31, 2.19e-31, 1.03e-30)
    for row in (zero, no_estimate):
        rows = {c: {_LARGE: r[_LARGE], _FORBIDDEN: row} for c, r in _GG_Z.items()}
        assert _laddered(rows)[_FORBIDDEN].verdict == checks.FAIL
