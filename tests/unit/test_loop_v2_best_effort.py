# SPDX-License-Identifier: 0BSD
"""The best available value of a refused point (m-lit ux-besteffort; USER
2026-11-11 items 7-9).

With the reduction backends' own acceptance checks on (the default), an
explicitly selected backend and no configured alternative left, a point the
backend refuses is returned by default (``on_failure="best-effort"``) with
the value the same backend gives WITHOUT its own checks
(``reduction_unchecked=True``, bitwise), lane status ``"best-effort"`` (never
a success), the refusal kept and an uncertainty: the call's own stability
estimate when it ran checks, else a rotation re-test of that point alone; the
result's ``warnings`` metadata lists it. Nothing is printed, logged or warned
by default; ``emit_warnings()`` is the opt-in single Python warning;
``"return"`` keeps the failed lanes without a value; ``"raise"`` raises.
"""

from __future__ import annotations

import json
import math
import warnings
from decimal import Decimal
from fractions import Fraction

import pytest

from tests.unit.loop_v2_induced_observables_rows import generate


@pytest.fixture(autouse=True)
def _without_lane_rescue(monkeypatch):
    """These tests exercise the mechanisms behind the lane rescue (the
    per-point fallback and its guard, best-effort values, the unchecked
    mode against the checked one) on points whose refused lanes the lane
    rescue would serve: they run without it, the Python runtimes by their
    default (``lane_rescue``, ``reduction.default_lane_rescue``), the C ABI
    handles by ``rusticol_virtual_set_lane_rescue(handle, 0)``
    (``test_loop_v2_sdk_induced._open``)."""

    from pyamplicol.loops.v2 import reduction

    monkeypatch.setattr(reduction, "default_lane_rescue", lambda: False)


def _tirust(native) -> bool:
    return "tirust" in json.loads(native.reduction_backends())


@pytest.fixture(scope="module")
def aag(loop_sm_ufo, loop_native, tmp_path_factory):
    """g g > a a g (LI-33) and its first frozen stream points: they include
    points TIRust refuses structurally at the default acceptance."""

    from tools.loop_benchmark import streams

    if not _tirust(loop_native):
        pytest.skip("the staged native extension is built without TIRust")
    artifact = generate(tmp_path_factory.mktemp("aag"), "li_gg_aag", "g g > a a g")
    stream = streams.load("li_gg_aag")
    count = 6
    points = [
        [[str(Decimal(float(Fraction(c)))) for c in leg] for leg in point]
        for point in stream["points"][:count]
    ]
    scales = [str(Decimal(float(Fraction(mu) ** 2))) for mu in stream["mu_r"][:count]]
    return artifact, points, scales


# ------------------------------------------------------------ the model


def test_the_failure_policy_has_one_definition_and_best_effort_is_the_default():
    from pyamplicol.config.models import (
        DEFAULT_ON_FAILURE,
        ON_FAILURE,
        EvaluationConfig,
    )

    assert ON_FAILURE == ("best-effort", "return", "raise")
    assert DEFAULT_ON_FAILURE == "best-effort"
    assert EvaluationConfig().on_failure is None


def test_a_best_effort_record_states_its_refusal_and_uncertainty():
    from pyamplicol.api.virtual_results import (
        VirtualBestEffort,
        VirtualLaneDiagnostic,
        VirtualReduction,
        best_effort_detail,
    )

    record = VirtualBestEffort("TIRust Unstable: x", 3e-4, "recommended-checks", 2e-3)
    assert "3.00e-04" in best_effort_detail(record)
    none = VirtualBestEffort("TIRust Unstable: x", None, "none")
    assert "no uncertainty could be estimated" in best_effort_detail(none)
    with pytest.raises(ValueError):
        VirtualBestEffort("x", None, "recommended-checks")
    with pytest.raises(ValueError):
        VirtualBestEffort("", 1e-3, "recommended-checks")
    reduction = VirtualReduction(
        "tirust", "tirust", "best effort", unchecked=True, best_effort=record
    )
    lane = VirtualLaneDiagnostic(
        "best-effort", "double", 53, False, "d", reduction=reduction
    )
    assert lane.has_value and not lane.valid and lane.best_effort is record
    with pytest.raises(ValueError):
        VirtualLaneDiagnostic("success", "double", 53, False, "d", reduction=reduction)
    with pytest.raises(ValueError):
        VirtualReduction("tirust", "tirust", "x", unchecked=False, best_effort=record)


def test_refusal_measures_are_data_kept_by_the_bounded_reasons():
    """m-lit ux-polish item 4: the backend's lane measures travel as data
    next to the unchanged reason texts (``plan_export.Refusal``): bounding,
    relabelling and pickling keep them; ``backend_deviation`` and
    ``gram_conditioning`` read them, never the text."""

    import pickle

    from pyamplicol.loops.v2.plan_export import (
        Refusal,
        bounded_reasons,
        measures_of,
        relabelled,
        with_measures,
    )
    from pyamplicol.loops.v2.reduction import backend_deviation, gram_conditioning

    text = "deviation 1e-3 of term scale 1e+0 between its two frames"
    reasons = with_measures(
        [text, text, "TIRust Unstable: singular"],
        [("method-choice-deviation", 4e-9), ("gram-conditioning", 2e-13)],
    )
    more = [relabelled(f"rotation 0: {r}", r) for r in reasons]
    more.append(Refusal("other", [("method-choice-deviation", 7e-8)]))
    bounded = bounded_reasons(more)
    assert [str(r) for r in bounded] == [
        f"rotation 0: {text} (+1 more like this)",
        "rotation 0: TIRust Unstable: singular",
        "other",
    ]
    assert sorted(measures_of(bounded)) == [
        ("gram-conditioning", 2e-13),
        ("method-choice-deviation", 4e-9),
        ("method-choice-deviation", 7e-8),
    ]
    assert backend_deviation(bounded) == 7e-8
    assert gram_conditioning(bounded) == 2e-13
    # The text alone states nothing (no parsing).
    assert backend_deviation([text]) is None and gram_conditioning([text]) is None
    again = pickle.loads(pickle.dumps(bounded))
    assert measures_of(again) == measures_of(bounded)


def test_numerical_warnings_summarise_the_lanes_and_emit_only_on_request():
    from pyamplicol.api.result_warnings import (
        NumericalAccuracyWarning,
        ResultWarning,
        emit,
        merge_warnings,
        numerical_warnings,
        summary_line,
    )
    from pyamplicol.api.virtual_results import (
        VirtualBestEffort,
        VirtualFailureDiagnostic,
        VirtualLaneDiagnostic,
        VirtualReduction,
    )

    best = VirtualReduction(
        "tirust",
        "tirust",
        "r",
        unchecked=True,
        best_effort=VirtualBestEffort("refused A", 1e-3, "recommended-checks"),
    )
    lanes = (
        VirtualLaneDiagnostic("success", "double", 53, False, "ok"),
        VirtualLaneDiagnostic("best-effort", "double", 53, False, "b", reduction=best),
        VirtualLaneDiagnostic(
            "failed",
            "double",
            53,
            False,
            "f",
            failures=(
                VirtualFailureDiagnostic(2, None, None, None, "v2", "no value B"),
            ),
        ),
        VirtualLaneDiagnostic("best-effort", "double", 53, False, "b", reduction=best),
    )
    found = numerical_warnings(lanes, "evaluate")
    assert [(w.kind, w.count, w.points, w.message) for w in found] == [
        ("best-effort", 2, (1, 3), "refused A"),
        ("failed", 1, (2,), "no value B"),
    ]
    assert ResultWarning.from_json(found[0].to_json()) == found[0]
    merged = merge_warnings(found, found[:1])
    assert merged[0].count == 4 and merged[0].points == (1, 3, 1, 3)
    assert summary_line(found).startswith("3 captured warning(s)")
    assert summary_line(()) is None
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert emit(found)
    assert [w.category for w in caught] == [NumericalAccuracyWarning]
    assert not emit(())


# ------------------------------------------------------------ the engine


def _quiet(capfd, call):
    """``call()`` with every Python warning recorded and the process's
    stdout / stderr captured: the evaluation path emits nothing."""

    capfd.readouterr()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = call()
    out, err = capfd.readouterr()
    assert not caught, [str(w.message) for w in caught]
    assert out == "" and err == "", (out[-500:], err[-500:])
    return result


@pytest.mark.loop_physics
def test_refused_points_carry_the_unchecked_value_by_default(aag, capfd):
    """Default policy on explicit TIRust: accepted points bitwise the
    "return" call's, refused points the unchecked TIRust call's values with
    status "best-effort", the refusal and a rotation re-test uncertainty;
    nothing emitted; ``"raise"`` raises; ``"return"`` keeps failed lanes."""

    from pyamplicol import EvaluationError, Runtime

    artifact, points, scales = aag
    options = {"mu_r2": scales, "poles": "none", "reduction": "tirust"}
    runtime = Runtime.load(artifact, process="p")
    returned = runtime.evaluate(points, on_failure="return", **options)
    refused = [p for p, ok in enumerate(returned.valid) if not ok]
    assert refused, "the fixture points include refused ones"
    unchecked = runtime.evaluate(
        points, on_failure="return", reduction_unchecked=True, **options
    )
    found = _quiet(capfd, lambda: runtime.evaluate(points, **options))
    assert found.has_warnings
    assert found.statuses == tuple(
        "best-effort" if p in refused else "success" for p in range(len(points))
    )
    for p, lane in enumerate(found.diagnostics):
        if p not in refused:
            assert repr(found.values[p]) == repr(returned.values[p]), p
            assert lane.best_effort is None
            continue
        assert repr(found.values[p]) == repr(unchecked.values[p]), p
        record = lane.best_effort
        assert record is not None and not lane.valid and lane.has_value
        assert record.refusal and "TIRust" in record.refusal
        assert lane.reduction.effective == "tirust" and lane.reduction.unchecked
        if record.uncertainty is None:
            assert record.source == "none"
        else:
            assert record.source == "recommended-checks"
            assert math.isfinite(record.uncertainty) and record.uncertainty >= 0
        assert lane.failures and lane.failures[0].detail == record.refusal
    # m-lit ux-polish item 4: TIRust states its measure of the refused
    # lanes as data (the method-choice deviation or the conditioning).
    assert all(
        found.diagnostics[p].best_effort.backend_deviation is not None
        or found.diagnostics[p].best_effort.gram_conditioning is not None
        for p in refused
    )
    # The call ran no checks: the public result carries no estimate.
    assert found.stability is None
    (warning,) = found.warnings
    assert (warning.source, warning.kind, warning.points) == (
        "numerical",
        "best-effort",
        tuple(refused),
    )
    with pytest.raises(EvaluationError):
        runtime.evaluate(points, on_failure="raise", **options)


def test_the_best_effort_checks_always_include_the_recommended_ones():
    """m-lit ux-polish item 2: the call's checks together with the
    recommended ones (guard rotation + rescaled reduction direction): one
    run when they combine, two when the call runs the cached reduction
    check, the call's own when they already include the recommended set."""

    from pyamplicol.loops.v2.reduction import best_effort_checks, guard_rotation
    from pyamplicol.loops.v2.stability import StabilityChecks, default_rotation

    guard, other = guard_rotation(), default_rotation(3)
    runs, source, names = best_effort_checks(None)
    assert source == "recommended-checks" and names is None
    assert runs == [StabilityChecks((guard,), True, True)]
    runs, source, names = best_effort_checks(StabilityChecks((other,)))
    assert source == "stability-and-recommended-checks"
    assert runs == [StabilityChecks((other, guard), True, True)]
    assert names == ("rotation-0",)
    runs, source, names = best_effort_checks(
        StabilityChecks((guard,), cross_backend=True)
    )
    assert runs == [StabilityChecks((guard,), True, True)]
    assert names == ("rotation-0",)
    runs, source, names = best_effort_checks(StabilityChecks((other,), True))
    assert source == "stability-and-recommended-checks"
    assert runs == [
        StabilityChecks((other,), True),
        StabilityChecks((guard,), True, True),
    ]
    assert names == ("rotation-0", "reduction-direction")
    runs, source, names = best_effort_checks(
        StabilityChecks((guard, other), True, True)
    )
    assert source == "stability-checks"
    assert runs == [StabilityChecks((guard, other), True, True)]


@pytest.mark.loop_physics
@pytest.mark.parametrize(
    ("checks", "source"),
    [
        ({"rotations": 1}, "stability-and-recommended-checks"),
        (
            {"rotations": 1, "reduction_direction": True},
            "stability-and-recommended-checks",
        ),
        (
            {"rotations": 1, "reduction_direction": True, "rescaled": True},
            "stability-checks",
        ),
    ],
)
def test_a_checked_call_counts_the_recommended_checks_in_the_uncertainty(
    aag, checks, source
):
    from pyamplicol import Runtime
    from pyamplicol.api.virtual_results import VirtualStabilityChecks

    artifact, points, scales = aag
    checks = VirtualStabilityChecks(**checks)
    options = {"mu_r2": scales, "poles": "none", "reduction": "tirust"}
    runtime = Runtime.load(artifact, process="p")
    unchecked = runtime.evaluate(
        points, on_failure="return", reduction_unchecked=True, **options
    )
    plain = runtime.evaluate(
        points,
        stability_checks=checks,
        on_failure="return",
        reduction_unchecked=True,
        **options,
    )
    found = runtime.evaluate(points, stability_checks=checks, **options)
    served = [p for p, s in enumerate(found.statuses) if s == "best-effort"]
    assert served
    for p in served:
        record = found.diagnostics[p].best_effort
        assert repr(found.values[p]) == repr(unchecked.values[p]), p
        assert record.source == source
        # The public estimate is the call's own checks' (as an unchecked
        # call with those checks gives it); the uncertainty includes the
        # recommended checks: at least as large.
        assert found.stability[p].relative == plain.stability[p].relative
        if source == "stability-checks":
            assert record.uncertainty == found.stability[p].relative
        else:
            assert record.uncertainty >= found.stability[p].relative


@pytest.mark.loop_physics
def test_the_resolved_call_serves_best_effort_values(aag):
    from pyamplicol import Runtime

    artifact, points, scales = aag
    options = {"mu_r2": scales, "poles": "none", "reduction": "tirust"}
    runtime = Runtime.load(artifact, process="p")
    returned = runtime.evaluate_resolved(points, on_failure="return", **options)
    found = runtime.evaluate_resolved(points, **options)
    refused = [p for p, ok in enumerate(returned.valid) if not ok]
    assert refused
    for p in range(len(points)):
        if p in refused:
            assert found.statuses[p] == "best-effort"
            assert found.values[p] is not None
        else:
            assert repr(found.values[p]) == repr(returned.values[p])


# ------------------------------------------------------------ the SDKs

BEST_EFFORT_STATUS = 5
RUNTIME_ERROR = 3

CLIENT_CPP = r"""
// ./client artifact process input.txt: explicit TIRust under the default
// failure policy through the C++ wrapper: statuses, uncertainties (bits)
// and the diagnostics, one line each.
#include "rusticol_virtual.hpp"
#include <cinttypes>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

int main(int argc, char **argv) {
  if (argc < 4) return 2;
  std::ifstream in(argv[3]);
  std::size_t points = 0, legs = 0;
  in >> points >> legs;
  std::vector<double> momenta(points * legs * 4), scales(points);
  std::string token;
  for (std::size_t p = 0; p < points; ++p) {
    for (std::size_t i = 0; i < legs * 4; ++i) {
      in >> token;
      momenta[p * legs * 4 + i] = std::strtod(token.c_str(), nullptr);
    }
    in >> token;
    scales[p] = std::strtod(token.c_str(), nullptr);
  }
  try {
    rusticol::VirtualRuntime runtime(argv[1], std::string(argv[2]));
    runtime.set_poles("none");
    runtime.set_reduction("tirust");
    runtime.set_lane_rescue(false);
    auto result = runtime.evaluate(momenta, points, scales);
    std::printf("statuses");
    for (auto status : result.statuses()) std::printf(" %u", status);
    std::printf("\nuncertainties");
    for (double value : result.uncertainties()) std::printf(" %a", value);
    std::printf("\ndiagnostics %s\n", result.diagnostics_json().c_str());
    runtime.set_on_failure("raise");
    try {
      runtime.evaluate(momenta, points, scales);
      std::printf("strict no error\n");
    } catch (const rusticol::VirtualError &error) {
      std::printf("strict error %d\n", error.status());
    }
  } catch (const rusticol::VirtualError &error) {
    std::printf("error %d %s\n", error.status(), error.what());
    return 1;
  }
  return 0;
}
"""

CLIENT_FORTRAN = r"""
program best_effort_client
  use, intrinsic :: iso_c_binding
  use rusticol_virtual
  implicit none
  character(len=4096) :: artifact, process, path
  integer :: unit, points, legs, p, l, i
  integer(c_int64_t), allocatable :: bits(:)
  real(c_double), allocatable :: momenta(:,:,:), scales(:)
  type(virtual_runtime) :: runtime
  type(virtual_evaluation) :: result, strict
  integer(c_int) :: ierr
  character(:), allocatable :: message
  call get_command_argument(1, artifact)
  call get_command_argument(2, process)
  call get_command_argument(3, path)
  open(newunit=unit, file=trim(path), status='old', action='read')
  read(unit, *) points, legs
  allocate(momenta(4, legs, points), scales(points), bits(4*legs+1))
  do p = 1, points
    read(unit, *) bits
    do l = 1, legs
      do i = 1, 4
        momenta(i, l, p) = transfer(bits(4*(l-1)+i), 1.0_c_double)
      end do
    end do
    scales(p) = transfer(bits(4*legs+1), 1.0_c_double)
  end do
  close(unit)
  call runtime%load(trim(artifact), process=trim(process), ierr=ierr)
  if (ierr /= VIRTUAL_OK) stop 1
  call runtime%set_poles('none', ierr=ierr)
  if (ierr /= VIRTUAL_OK) stop 2
  call runtime%set_reduction('tirust', ierr=ierr)
  if (ierr /= VIRTUAL_OK) stop 3
  call runtime%set_lane_rescue(.false., ierr=ierr)
  if (ierr /= VIRTUAL_OK) stop 3
  call runtime%evaluate(momenta, scales, result, ierr=ierr, error_message=message)
  if (ierr /= VIRTUAL_OK) stop 4
  write(*, '(a,*(1x,i0))') 'statuses', result%statuses
  write(*, '(a,*(1x,i0))') 'uncertainties', &
    transfer(result%uncertainties, 1_c_int64_t, size(result%uncertainties))
  call runtime%set_on_failure('raise', ierr=ierr)
  if (ierr /= VIRTUAL_OK) stop 5
  call runtime%evaluate(momenta, scales, strict, ierr=ierr)
  write(*, '(a,1x,i0)') 'strict error', ierr
  call runtime%close()
end program
"""

CLIENT_RUST = """
#[path = "@WRAPPER@"]
#[allow(dead_code)]
mod rusticol;
use rusticol::virtual_amplitudes::{PointStatus, Runtime};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().collect();
    let text = std::fs::read_to_string(&args[3])?;
    let mut lines = text.lines();
    let head: Vec<usize> = lines
        .next()
        .ok_or("empty input")?
        .split_whitespace()
        .map(|v| v.parse())
        .collect::<Result<_, _>>()?;
    let (points, legs) = (head[0], head[1]);
    let (mut momenta, mut scales) = (Vec::new(), Vec::new());
    for line in lines.take(points) {
        let values: Vec<f64> = line
            .split_whitespace()
            .map(|v| v.parse::<i64>().map(|bits| f64::from_bits(bits as u64)))
            .collect::<Result<_, _>>()?;
        momenta.extend_from_slice(&values[..4 * legs]);
        scales.push(values[4 * legs]);
    }
    let mut runtime = Runtime::open(&args[1], Some(args[2].as_str()), None, None)?;
    runtime.set_poles("none")?;
    runtime.set_reduction("tirust")?;
    runtime.set_lane_rescue(false)?;
    let result = runtime.evaluate(&momenta, points, None, &scales, false, None)?;
    let codes: Vec<String> = result
        .statuses
        .iter()
        .map(|s| (if *s == PointStatus::BestEffort { "5" } else { "x" }).to_owned())
        .collect();
    println!("statuses {}", codes.join(" "));
    let bits: Vec<String> = result
        .uncertainties
        .iter()
        .map(|u| (u.to_bits() as i64).to_string())
        .collect();
    println!("uncertainties {}", bits.join(" "));
    runtime.set_on_failure("raise")?;
    let strict = runtime.evaluate(&momenta, points, None, &scales, false, None);
    println!("strict error {}", i32::from(strict.is_err()));
    Ok(())
}
"""


def _sdk_call(sdk, handle, points, scales, *, policy=None, unchecked=None):
    from tests.unit.test_loop_v2_sdk_induced import _evaluate

    if policy is not None:
        assert sdk.rusticol_virtual_set_on_failure(handle, policy) == 0
    if unchecked is not None:
        assert sdk.rusticol_virtual_set_reduction_unchecked(handle, unchecked) == 0
    return _evaluate(sdk, handle, points, scales)


def _uncertainties(sdk, handle, points, scales) -> list[float]:
    import ctypes

    from tests.unit.test_loop_v2_sdk_induced import _Request

    flat = [c for point in points for p in point for c in p]
    momenta = (ctypes.c_double * len(flat))(*flat)
    mu = (ctypes.c_double * len(scales))(*scales)
    request = _Request(momenta, len(flat), len(points), None, mu, len(scales))
    result = ctypes.c_void_p()
    assert (
        sdk.rusticol_virtual_evaluate(
            handle, ctypes.byref(request), ctypes.byref(result)
        )
        == 0
    )
    try:
        out = (ctypes.c_double * len(points))()
        function = sdk.rusticol_virtual_result_copy_uncertainties
        function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
        assert function(result, out, len(points)) == 0
        return list(out)
    finally:
        sdk.rusticol_virtual_result_free(result)


@pytest.mark.loop_physics
def test_every_sdk_returns_refused_points_with_their_best_effort_value(
    aag, loop_native, tmp_path
):
    """The C ABI and the C++, Fortran and packaged Rust wrappers on explicit
    TIRust: by default the call succeeds, the refused points carry status
    BEST_EFFORT with the SDK's own unchecked TIRust values (bitwise) and the
    Python API's best-effort values, a finite uncertainty (rotation re-test)
    and the refusal in the diagnostics; "return" keeps them FAILED; "raise"
    is a runtime error; the accepted points keep their values. The clients
    turn the lane rescue off, as this module's Python calls do
    (``_without_lane_rescue``): the refusals are what is tested."""

    import ctypes
    import subprocess

    from pyamplicol import Runtime
    from tests.unit.test_loop_v2_sdk_extras import (
        SDK,
        WRAPPER,
        _compiler,
        _error,
        _sdk,
        _staged_sdk,
    )
    from tests.unit.test_loop_v2_sdk_induced import (
        FAILED_STATUS,
        _evaluate,
        _open,
        _python_flat,
        _same,
    )
    from tests.unit.test_loop_v2_unchecked import _feed

    artifact, exact_points, exact_scales = aag
    points = [[[float(c) for c in leg] for leg in point] for point in exact_points]
    scales = [float(Fraction(s)) for s in exact_scales]
    python = Runtime.load(artifact, process="p").evaluate(
        exact_points, mu_r2=exact_scales, poles="none", reduction="tirust"
    )
    refused = [p for p, s in enumerate(python.statuses) if s == "best-effort"]
    assert refused
    sdk = _sdk()
    sdk.rusticol_virtual_set_on_failure.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    sdk.rusticol_virtual_set_reduction_unchecked.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    handle = _open(sdk, artifact)
    try:
        assert sdk.rusticol_virtual_set_poles(handle, b"none") == 0, _error(sdk)
        assert sdk.rusticol_virtual_set_reduction(handle, b"tirust") == 0
        found = _evaluate(sdk, handle, points, scales)
        assert [p for p, s in enumerate(found["statuses"]) if s == 5] == refused
        assert FAILED_STATUS not in found["statuses"]
        assert _same(found["virtual"], _python_flat(python))
        record = found["diagnostics"]
        assert sorted(int(k) for k in record["best_effort"]) == refused
        for entry in record["best_effort"].values():
            assert (
                "TIRust" in entry["refusal"] and entry["source"] == "recommended-checks"
            )
            assert math.isfinite(entry["uncertainty"])
        # The backend's measures (m-lit ux-polish item 4): the Python API's.
        for p in refused:
            mine = python.diagnostics[p].best_effort
            entry = record["best_effort"][str(p)]
            assert (entry["backend_deviation"], entry["gram_conditioning"]) == (
                mine.backend_deviation,
                mine.gram_conditioning,
            ), p
        (warning,) = record["warnings"]
        assert warning["kind"] == "best-effort" and warning["count"] == len(refused)
        assert record["on_failure"] == "best-effort"
        # The helicity-resolved call: the same policy at the same points.
        from tests.unit.test_loop_v2_sdk_extras import _request

        request, _alive = _request(points, scales, resolved=True)
        result = ctypes.c_void_p()
        assert (
            sdk.rusticol_virtual_evaluate(
                handle, ctypes.byref(request), ctypes.byref(result)
            )
            == 0
        ), _error(sdk)
        statuses = (ctypes.c_uint32 * len(points))()
        try:
            assert (
                sdk.rusticol_virtual_result_copy_statuses(result, statuses, len(points))
                == 0
            )
        finally:
            sdk.rusticol_virtual_result_free(result)
        # (its own lanes: its refused points need not be the ordinary call's)
        assert 5 in list(statuses) and 3 not in list(statuses)
        uncertainties = _uncertainties(sdk, handle, points, scales)
        assert [math.isfinite(u) for u in uncertainties] == [
            p in refused for p in range(len(points))
        ]
        unchecked = _sdk_call(sdk, handle, points, scales, unchecked=1)
        assert _same(found["virtual"], unchecked["virtual"])
        assert sdk.rusticol_virtual_set_reduction_unchecked(handle, 0) == 0
        returned = _sdk_call(sdk, handle, points, scales, policy=b"return")
        assert [p for p, s in enumerate(returned["statuses"]) if s == 3] == refused
        assert sdk.rusticol_virtual_set_on_failure(handle, b"raise") == 0
        request_points = points
        flat = [c for point in request_points for p in point for c in p]
        from tests.unit.test_loop_v2_sdk_induced import _Request

        momenta = (ctypes.c_double * len(flat))(*flat)
        mu = (ctypes.c_double * len(scales))(*scales)
        request = _Request(momenta, len(flat), len(points), None, mu, len(scales))
        result = ctypes.c_void_p()
        status = sdk.rusticol_virtual_evaluate(
            handle, ctypes.byref(request), ctypes.byref(result)
        )
        assert status == RUNTIME_ERROR and not result.value
        assert "on_failure" in _error(sdk)
        assert sdk.rusticol_virtual_set_on_failure(handle, b"warn") != 0
    finally:
        sdk.rusticol_virtual_free(handle)

    build = _staged_sdk()
    link = [f"-L{build}", "-lrusticol_loop_sdk", f"-Wl,-rpath,{build}", "-lm"]
    (tmp_path / "client.cpp").write_text(CLIENT_CPP)
    (tmp_path / "client.f90").write_text(CLIENT_FORTRAN)
    (tmp_path / "client.rs").write_text(CLIENT_RUST.replace("@WRAPPER@", str(WRAPPER)))
    compile_steps = [
        [
            _compiler("CXX", "c++"),
            "-std=c++17",
            "-O2",
            f"-I{SDK / 'include'}",
            str(tmp_path / "client.cpp"),
            *link,
            "-o",
            str(tmp_path / "cpp"),
        ],
        [
            _compiler("FC", "gfortran"),
            "-std=f2018",
            "-O2",
            f"-J{tmp_path}",
            str(SDK / "fortran" / "rusticol_virtual.f90"),
            str(tmp_path / "client.f90"),
            *link,
            "-o",
            str(tmp_path / "fortran"),
        ],
        [
            _compiler("RUSTC", "rustc"),
            "--edition=2021",
            "-D",
            "warnings",
            str(tmp_path / "client.rs"),
            "-o",
            str(tmp_path / "rust"),
            "-L",
            f"native={build}",
            "-l",
            "dylib=rusticol_loop_sdk",
            "-C",
            f"link-arg=-Wl,-rpath,{build}",
        ],
    ]
    for step in compile_steps:
        subprocess.run(step, check=True, cwd=tmp_path)
    for language in ("cpp", "fortran", "rust"):
        path = tmp_path / f"{language}.txt"
        path.write_text(_feed(points, scales, bits=language != "cpp"))
        run = subprocess.run(
            [str(tmp_path / language), str(artifact), "p", str(path)],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-2000:]
        lines = {
            line.split(" ", 1)[0]: line.split(" ", 1)[1]
            for line in run.stdout.splitlines()
            if " " in line
        }
        codes = lines["statuses"].split()
        assert [p for p, c in enumerate(codes) if c == "5"] == refused, language
        assert lines["strict"].split()[-1] != "0", language
        values = lines["uncertainties"].split()
        if language == "cpp":
            found_u = [float.fromhex(v) if "nan" not in v else math.nan for v in values]
        else:
            import struct

            found_u = [
                struct.unpack("<d", struct.pack("<q", int(v)))[0] for v in values
            ]
        assert [math.isfinite(u) for u in found_u] == [
            p in refused for p in range(len(points))
        ], language
        for p in refused:
            assert found_u[p] == uncertainties[p], language


# ------------------------------------------------------------ heavy rows


@pytest.fixture(scope="module", params=["loop_gg_zgg", "loop_uux_ttxgg"])
def heavy(request, loop_native, tmp_path_factory):
    """The two examples where explicit TIRust refuses most flat points
    (m-lit ux-profile F1: g g > z g g 43 %, u u~ > t t~ g g 77 %; about 8 %
    and 26 % since m-lit tir-uuzggg's verified last resort), generated from
    their shipped cards, and sixteen flat points (seed 1: each row refuses
    at least one)."""

    import shutil

    from pyamplicol.cli.flat_points import draw_flat_points
    from pyamplicol.cli.main import main
    from tests.unit.test_examples import EXAMPLES

    if not _tirust(loop_native):
        pytest.skip("the staged native extension is built without TIRust")
    root = tmp_path_factory.mktemp(request.param)
    for item in EXAMPLES.iterdir():
        if item.name.endswith(".toml"):
            shutil.copy(item, root / item.name)
    shutil.copytree(EXAMPLES / "data", root / "data")
    artifact = root / "artifact"
    card = root / f"{request.param}_generate.toml"
    assert main(
        [str(card), "--progress", "off", "--set", f"generation.output={artifact}"]
    ) in (
        0,
        None,
    )
    flat = draw_flat_points(artifact, process=None, points=16, seed=1, sqrt_s=None)
    return artifact, flat.as_inputs(exact=True), flat.mu_r2()


@pytest.mark.loop_physics
def test_the_heavy_refusal_rows_return_the_unchecked_values(heavy):
    """On the heavy-refusal rows explicit TIRust's refused points carry
    exactly the unchecked TIRust values (best-effort), the accepted ones
    keep the "return" call's values bitwise, every lane has a value or a
    stated reason, and the warnings metadata counts them."""

    from pyamplicol import Runtime

    artifact, points, scales = heavy
    runtime = Runtime.load(artifact)
    options = {"mu_r2": scales, "poles": "none", "reduction": "tirust"}
    returned = runtime.evaluate(points, on_failure="return", **options)
    unchecked = runtime.evaluate(
        points, on_failure="return", reduction_unchecked=True, **options
    )
    found = runtime.evaluate(points, **options)
    refused = [p for p, ok in enumerate(returned.valid) if not ok]
    assert refused, "the heavy rows refuse flat points on TIRust"
    for p, status in enumerate(found.statuses):
        if p not in refused:
            assert status == "success" and repr(found.values[p]) == repr(
                returned.values[p]
            )
        elif unchecked.values[p] is not None:
            assert status == "best-effort"
            assert repr(found.values[p]) == repr(unchecked.values[p]), p
            record = found.diagnostics[p].best_effort
            assert record.refusal and (record.uncertainty is None) == (
                record.source == "none"
            )
        else:
            assert status == "failed" and found.values[p] is None
    counts = {w.kind: w.count for w in found.warnings}
    assert sum(counts.values()) == len(refused)


@pytest.mark.loop_physics
def test_a_point_failing_only_in_its_check_rows_keeps_its_unchecked_value(heavy):
    """Without the lane rescue, TIRust refuses a triangle below its
    fixed-precision floor at any gate, the gate-0 last resort included, so the
    best-effort evaluation of a refused point can fail only in the rows of the
    checks that estimate its uncertainty (u u~ > t t~ g g: one of the sixteen
    points). Such a point keeps its unchecked value, best-effort without an
    uncertainty, in the Python API and in the SDKs' failure policy (C ABI);
    a point the unchecked reduction fails too stays failed in both."""

    import ctypes

    from pyamplicol import Runtime
    from pyamplicol.api.virtual_results import VirtualStabilityChecks
    from tests.unit.test_loop_v2_sdk_extras import _error, _sdk
    from tests.unit.test_loop_v2_sdk_induced import FAILED_STATUS, _evaluate

    artifact, exact_points, exact_scales = heavy
    runtime = Runtime.load(artifact)
    options = {"mu_r2": exact_scales, "poles": "none", "reduction": "tirust"}
    returned = runtime.evaluate(exact_points, on_failure="return", **options)
    bare = runtime.evaluate(
        exact_points, on_failure="return", reduction_unchecked=True, **options
    )
    with_checks = runtime.evaluate(
        exact_points,
        on_failure="return",
        reduction_unchecked=True,
        stability_checks=VirtualStabilityChecks(1, True, rescaled=True),
        **options,
    )
    refused = [p for p, ok in enumerate(returned.valid) if not ok]
    rows_only = [p for p in refused if bare.valid[p] and not with_checks.valid[p]]
    without = [p for p in refused if not bare.valid[p]]
    if "uux_ttxgg" in str(artifact):
        assert rows_only and without, (rows_only, without)
    found = runtime.evaluate(exact_points, **options)
    for p in rows_only:
        assert found.statuses[p] == "best-effort", p
        assert repr(found.values[p]) == repr(bare.values[p]), p
        record = found.diagnostics[p].best_effort
        assert record.uncertainty is None and record.source == "none", p
        assert "the rows of its checks failed" in str(found.diagnostics[p]), p
    for p in without:
        assert found.statuses[p] == "failed" and found.values[p] is None, p

    points = [[[float(c) for c in leg] for leg in point] for point in exact_points]
    scales = [float(Fraction(s)) for s in exact_scales]
    sdk = _sdk()
    sdk.rusticol_virtual_set_reduction_unchecked.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    handle = ctypes.c_void_p()
    assert (
        sdk.rusticol_virtual_open(
            str(artifact).encode(), None, None, None, ctypes.byref(handle)
        )
        == 0
    ), _error(sdk)
    try:
        assert sdk.rusticol_virtual_set_lane_rescue(handle, 0) == 0, _error(sdk)
        assert sdk.rusticol_virtual_set_poles(handle, b"none") == 0, _error(sdk)
        assert sdk.rusticol_virtual_set_reduction(handle, b"tirust") == 0
        assert sdk.rusticol_virtual_set_reduction_unchecked(handle, 1) == 0
        unchecked = _evaluate(sdk, handle, points, scales)
        assert sdk.rusticol_virtual_set_reduction_unchecked(handle, 0) == 0
        policy = _evaluate(sdk, handle, points, scales)
    finally:
        sdk.rusticol_virtual_free(handle)

    def rows(result):
        """Each served point's values (the flat array holds served points
        only, in point order)."""

        served = [p for p, s in enumerate(result["statuses"]) if s != FAILED_STATUS]
        stride = len(result["virtual"]) // max(len(served), 1)
        return {
            p: result["virtual"][k * stride : (k + 1) * stride]
            for k, p in enumerate(served)
        }

    mine, theirs = rows(policy), rows(unchecked)
    entries = policy["diagnostics"]["best_effort"]
    for p in rows_only:
        assert policy["statuses"][p] == 5, p
        assert [x.hex() for x in mine[p]] == [x.hex() for x in theirs[p]], p
        entry = entries[str(p)]
        assert entry["uncertainty"] is None and entry["source"] == "none", p
    for p in without:
        assert policy["statuses"][p] == FAILED_STATUS, p


# --------------------------------------------------- the floor weight's routes

FLOOR_WEIGHT = 1024.0


def _weighted_python(artifact, points, scales, way, explicit):
    """One TIRust call on g g > a a g with the floor weight ``FLOOR_WEIGHT``
    set by ``way``: the runtime-options card, the CLI (its flag resolved to
    the checks ``evaluate`` passes), or the Python object; with one rotation
    (``explicit``) or no check (the best-effort pass's recommended checks
    only)."""

    from pyamplicol import Runtime
    from pyamplicol.api.virtual_results import VirtualStabilityChecks
    from pyamplicol.cli import parse_cli

    call = dict(mu_r2=scales, poles="none", reduction="tirust")
    count = 1 if explicit else 0
    if way == "card":
        card = "[evaluation.stability_checks]\n" + (
            "rotation_count = 1\n" if explicit else ""
        )
        card += f"floor_weight = {FLOOR_WEIGHT}\n"
        runtime = Runtime.load(artifact, process="p", options=card)
        return runtime.evaluate(points, **call)
    if way == "cli":
        flags = ["evaluate", "artifact", "--stability-floor-weight", str(FLOOR_WEIGHT)]
        flags += ["--stability-rotations", "1"] if explicit else []
        resolved = parse_cli(tuple(flags)).resolve().effective
        checks = resolved.evaluation.stability_checks.to_checks()
        assert checks == VirtualStabilityChecks(count, floor_weight=FLOOR_WEIGHT)
    else:
        checks = VirtualStabilityChecks(count, floor_weight=FLOOR_WEIGHT)
    runtime = Runtime.load(artifact, process="p")
    return runtime.evaluate(points, stability_checks=checks, **call)


@pytest.mark.loop_physics
@pytest.mark.parametrize("explicit", [False, True], ids=["implicit", "explicit"])
def test_the_floor_weight_reaches_every_estimate_by_every_route(aag, explicit):
    """A floor weight is a setting of the estimate, whichever checks run: set
    by the runtime-options card, the CLI flag or the Python object, with an
    explicit rotation or with no check (the best-effort pass then runs its
    recommended checks), it gives the refused points the same best-effort
    uncertainty, and the checked points the same estimates reporting it; the
    default weight gives another uncertainty (the setting acts). Review r1:
    the card's weight without checks was dropped and the best-effort pass ran
    with the default."""

    from pyamplicol import Runtime

    artifact, points, scales = aag
    found = {
        way: _weighted_python(artifact, points, scales, way, explicit)
        for way in ("object", "card", "cli")
    }
    reference = found["object"]
    refused = [p for p, s in enumerate(reference.statuses) if s == "best-effort"]
    assert refused

    def uncertainties(result):
        return [result.diagnostics[p].best_effort.uncertainty for p in refused]

    for way, result in found.items():
        assert result.statuses == reference.statuses, way
        assert result.values == reference.values, way
        assert uncertainties(result) == uncertainties(reference), way
        if explicit:
            served = [e for e in result.stability if e is not None]
            assert served and {e.floor_weight for e in served} == {FLOOR_WEIGHT}
            assert [e.relative for e in served] == [
                e.relative for e in reference.stability if e is not None
            ], way
        else:
            assert result.stability is None or not any(result.stability), way
    from pyamplicol.api.virtual_results import VirtualStabilityChecks

    default = Runtime.load(artifact, process="p").evaluate(
        points,
        mu_r2=scales,
        poles="none",
        reduction="tirust",
        stability_checks=VirtualStabilityChecks(1 if explicit else 0),
    )
    assert default.statuses == reference.statuses
    assert uncertainties(default) != uncertainties(reference)


@pytest.mark.loop_physics
@pytest.mark.parametrize("explicit", [False, True], ids=["implicit", "explicit"])
@pytest.mark.parametrize("route", ["card", "setter"])
def test_the_sdk_floor_weight_reaches_its_best_effort_checks(
    aag, loop_native, explicit, route
):
    """The C ABI the same: a floor weight from the runtime-options TOML or
    from ``rusticol_virtual_set_stability_floor_weight``, with one rotation
    or no check, gives the refused points the best-effort uncertainty the
    Python API's runtime-options card gives on the same points."""

    import ctypes

    from tests.unit.test_loop_v2_sdk_extras import _error, _sdk
    from tests.unit.test_loop_v2_sdk_induced import _open

    artifact, exact_points, exact_scales = aag
    points = [[[float(c) for c in leg] for leg in point] for point in exact_points]
    scales = [float(Fraction(s)) for s in exact_scales]
    python = _weighted_python(artifact, exact_points, exact_scales, "card", explicit)
    refused = [p for p, s in enumerate(python.statuses) if s == "best-effort"]
    sdk = _sdk()
    sdk.rusticol_virtual_set_stability_floor_weight.argtypes = [
        ctypes.c_void_p,
        ctypes.c_double,
    ]
    handle = _open(sdk, artifact)
    try:
        assert sdk.rusticol_virtual_set_poles(handle, b"none") == 0, _error(sdk)
        assert sdk.rusticol_virtual_set_reduction(handle, b"tirust") == 0
        if route == "card":
            card = "[evaluation.stability_checks]\n" + (
                "rotation_count = 1\n" if explicit else ""
            )
            card += f"floor_weight = {FLOOR_WEIGHT}\n"
            assert sdk.rusticol_virtual_set_options(handle, card.encode()) == 0, _error(
                sdk
            )
        else:
            if explicit:
                assert (
                    sdk.rusticol_virtual_set_stability_checks(handle, 1, None, 0, 0, 0)
                    == 0
                )
            assert (
                sdk.rusticol_virtual_set_stability_floor_weight(handle, FLOOR_WEIGHT)
                == 0
            )
        uncertainties = _uncertainties(sdk, handle, points, scales)
    finally:
        sdk.rusticol_virtual_free(handle)
    mine = [python.diagnostics[p].best_effort.uncertainty for p in refused]
    assert [uncertainties[p] for p in refused] == pytest.approx(mine, rel=1e-12)


@pytest.mark.loop_physics
def test_a_rescue_level_takes_the_floor_weight_it_sets_or_the_cards(aag):
    """A rescue policy owns its levels' checks: a level's own floor weight
    applies to its estimates, and the runtime-options card's weight reaches
    every level that sets none (per call and at load time), reported on the
    estimates; a level's own weight wins over the card's."""

    from pyamplicol import Runtime
    from pyamplicol.api.virtual_results import VirtualRescueLevel, VirtualRescuePolicy

    artifact, points, scales = aag
    call = dict(mu_r2=scales, poles="none")
    card = f"[evaluation.stability_checks]\nfloor_weight = {FLOOR_WEIGHT}\n"

    def level(weight=None):
        return VirtualRescuePolicy(
            (VirtualRescueLevel("double", reduction="ninjars", floor_weight=weight),)
        )

    own = Runtime.load(artifact, process="p").evaluate(
        points, stability=level(FLOOR_WEIGHT), **call
    )
    per_call = Runtime.load(artifact, process="p", options=card).evaluate(
        points, stability=level(), **call
    )
    at_load = Runtime.load(
        artifact, process="p", options=card, stability=level()
    ).evaluate(points, **call)
    wins = Runtime.load(artifact, process="p", options=card).evaluate(
        points, stability=level(2.0), **call
    )
    for result in (own, per_call, at_load):
        assert result.values == own.values
        assert {e.floor_weight for e in result.stability if e is not None} == {
            FLOOR_WEIGHT
        }
        assert [e.relative for e in result.stability] == [
            e.relative for e in own.stability
        ]
    assert {e.floor_weight for e in wins.stability if e is not None} == {2.0}


@pytest.mark.loop_physics
def test_a_profile_with_only_a_floor_weight_weighs_its_default_checks(aag):
    """``profile --stability`` with ``evaluation.stability_checks.floor_weight``
    set and no check keeps its default set (one rotation; TIRust's points
    add the rescaled reduction check) and weighs its estimates: 0 and 1024
    give different estimates on both backends (review r1: identical)."""

    import io

    from pyamplicol.cli.main import run_cli
    from tests.unit.test_loop_v2_orders_profile import _records

    artifact, _points, _scales = aag
    estimates = {}
    for weight in ("0.0", "1024.0"):
        stdout = io.StringIO()
        code = run_cli(
            [
                "profile",
                str(artifact),
                "--stability",
                "--stability-points",
                "2",
                "--ground-truth",
                "none",
                "--set",
                f"evaluation.stability_checks.floor_weight={weight}",
                "--progress",
                "off",
                "--json",
            ],
            stdout=stdout,
            stderr=io.StringIO(),
        )
        assert code == 0
        report = json.loads(stdout.getvalue())
        estimates[weight] = [
            [sample["estimate_relative"] for sample in _records(row["samples"])]
            for row in report["stability"]
        ]
    low, high = estimates["0.0"], estimates["1024.0"]
    assert len(low) == len(high) >= 2
    for row_low, row_high in zip(low, high, strict=True):
        pairs = [
            (a, b)
            for a, b in zip(row_low, row_high, strict=True)
            if a is not None and b is not None
        ]
        assert pairs and all(a < b for a, b in pairs), (row_low, row_high)


@pytest.mark.loop_physics
def test_a_weight_alone_leaves_an_ordinary_evaluation_without_an_estimate(
    aag, loop_native, monkeypatch
):
    """A floor weight on its own runs no check: an ordinary successful call
    (NinjaRS serves every point here) with a runtime-options card setting
    only ``floor_weight`` returns the plain call's values, no estimate, no
    finiteness ratio and no other diagnostic, after the same number of
    executor runs; the C ABI the same (no ``stability`` record)."""

    from pyamplicol import Runtime
    from pyamplicol.loops.v2 import plan_export
    from tests.unit.test_loop_v2_sdk_extras import _error, _sdk
    from tests.unit.test_loop_v2_sdk_induced import _evaluate, _open, _same

    artifact, points, scales = aag
    call = dict(mu_r2=scales, poles="none", reduction="ninjars")
    card = f"[evaluation.stability_checks]\nfloor_weight = {FLOOR_WEIGHT}\n"
    runs = []
    original = plan_export.NativeExecutor._runs

    def counted(self, *args, **kwargs):
        runs.append(1)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(plan_export.NativeExecutor, "_runs", counted)
    plain = Runtime.load(artifact, process="p").evaluate(points, **call)
    plain_runs, runs[:] = len(runs), []
    weighted = Runtime.load(artifact, process="p", options=card).evaluate(
        points, **call
    )
    assert plain.statuses == ("success",) * len(points)
    assert weighted.statuses == plain.statuses and weighted.values == plain.values
    assert plain.stability is None and weighted.stability is None
    assert weighted.diagnostics == plain.diagnostics
    assert len(runs) == plain_runs
    sdk = _sdk()
    floats = [[[float(c) for c in leg] for leg in point] for point in points]
    mu = [float(Fraction(s)) for s in scales]
    handle = _open(sdk, artifact)
    try:
        assert sdk.rusticol_virtual_set_poles(handle, b"none") == 0, _error(sdk)
        assert sdk.rusticol_virtual_set_reduction(handle, b"ninjars") == 0
        before = _evaluate(sdk, handle, floats, mu)
        assert sdk.rusticol_virtual_set_options(handle, card.encode()) == 0, _error(sdk)
        after = _evaluate(sdk, handle, floats, mu)
    finally:
        sdk.rusticol_virtual_free(handle)
    assert before["diagnostics"]["stability"] is None
    assert after["diagnostics"]["stability"] is None
    assert after["statuses"] == before["statuses"]
    assert _same(after["virtual"], before["virtual"])
