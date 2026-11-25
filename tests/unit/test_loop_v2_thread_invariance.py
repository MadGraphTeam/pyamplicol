# SPDX-License-Identifier: 0BSD
"""Results do not depend on the number of native threads.

A v2 runtime's ``threads`` (``Runtime.load(threads=)``) sizes its executor's
pool; nothing it returns may depend on it. For a Born-interfered and a
loop-induced process, the same calls are made on runtimes loaded with 1, 2,
4 and 8 threads, and everything each call returns is compared bit for bit:
every Laurent coefficient (as ``float.hex``), every lane diagnostic (status,
carrier, reduction record, lane rescue, the reduction's own rescue,
uncertified lanes), the stability estimates, the pole parts, the derived
statuses and warnings, and refusals (type and message). The calls cover
both reductions, unchecked and checked evaluation (one rotation and the
rescaled reduction-direction check), binary64 and double-double, batches
of 1, 3, 5 and 17 points (17 is not a multiple of the executor's lane
width), the summed, resolved and selected-helicity routes, and repeated
calls at 8 threads (a race shows up as a repeat that differs). The points
that trigger the lane rescue or the reduction's own rescue in checked
binary64 come first, so the small batches exercise those paths.

A thread count above the threads the process may use is clamped by the
runtime; the comparison then still holds, with less parallel work.
"""

from __future__ import annotations

import dataclasses
import enum
import json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

pytestmark = pytest.mark.loop_physics

THREADS = (1, 2, 4, 8)
MU_R2 = 8315.251344
REPEATS = 5


def _artifact(root: Path, expression: str, extra: str = "") -> Path:
    from pyamplicol.api import Generator, ProcessRequest, ProcessSet
    from pyamplicol.config import resolve_config

    root.mkdir(parents=True, exist_ok=True)
    card = root / "card.toml"
    card.write_text(
        f"""action = "generate"
[model]
source = "loop_sm"
restriction = "no_widths"
[process]
entries = [{{expression = {json.dumps(expression)}, name = "p"}}]
loop_coupling_orders = ["QCD"]
{extra}
[loop]
r2_strategy = "model"
[generation]
output = "artifact"
emit_api_bundle = false
"""
    )
    config = resolve_config(card)
    output = Path(config.effective.generation.output)
    Generator(config).generate(
        ProcessSet((ProcessRequest.parse(expression, name="p"),)), output
    )
    return output


PROCESSES = {
    "uux_ddxg": ("u u~ > d d~ g", ""),
    "gg_hg": ("g g > h g", 'loop_induced = "only"'),
}


def _canon(x, depth: int = 0):
    """A JSON-comparable form of a result: equal iff bit for bit equal."""

    if depth > 60:
        return "<deep>"
    if x is None or isinstance(x, (bool, str)):
        return x
    if isinstance(x, enum.Enum):
        return {"__enum": type(x).__name__, "value": _canon(x.value, depth + 1)}
    if isinstance(x, int):
        return x
    if isinstance(x, float):
        return "f:" + x.hex()
    if isinstance(x, complex):
        return ["c", x.real.hex(), x.imag.hex()]
    if isinstance(x, Decimal):
        return "d:" + str(x)
    if isinstance(x, Fraction):
        return "q:" + str(x)
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        out = {"__type": type(x).__name__}
        for field in dataclasses.fields(x):
            out[field.name] = _canon(getattr(x, field.name), depth + 1)
        return out
    if isinstance(x, tuple) and hasattr(x, "_fields"):
        return {"__type": type(x).__name__} | {
            k: _canon(getattr(x, k), depth + 1) for k in x._fields
        }
    if isinstance(x, (list, tuple)):
        return [_canon(v, depth + 1) for v in x]
    if hasattr(x, "items"):
        return {
            str(k): _canon(v, depth + 1)
            for k, v in sorted(x.items(), key=lambda kv: str(kv[0]))
        }
    return {"__repr": type(x).__name__, "value": repr(x)}


def _record(call):
    try:
        result = call()
    except Exception as error:  # a refusal is a result too
        return {"__exception": type(error).__name__, "message": str(error)}
    record = {"result": _canon(result)}
    for name in ("statuses", "warnings"):
        record[name] = _canon(getattr(result, name, None))
    return record


def _flatten(x, path="", out=None):
    out = [] if out is None else out
    if isinstance(x, dict):
        for k, v in x.items():
            _flatten(v, f"{path}.{k}" if path else k, out)
    elif isinstance(x, list):
        out.append((path + ".__len__", len(x)))
        for i, v in enumerate(x):
            _flatten(v, f"{path}[{i}]", out)
    else:
        out.append((path, x))
    return out


def _first_difference(a, b):
    fa, fb = _flatten(a), _flatten(b)
    for (pa, va), (pb, vb) in zip(fa, fb):
        if (pa, va) != (pb, vb):
            return f"{pa}: {va!r} vs {pb}: {vb!r}"
    return None if len(fa) == len(fb) else f"{len(fa)} vs {len(fb)} fields"


def _checks():
    from pyamplicol.api.virtual_results import VirtualStabilityChecks

    return VirtualStabilityChecks(1, True, rescaled=True)


def _options(reduction: str, checked: bool, arithmetic: str = "double") -> dict:
    options = {
        "mu_r2": MU_R2,
        "poles": "all",
        "reduction": reduction,
        "arithmetic": arithmetic,
    }
    if checked:
        options.update(
            reduction_unchecked=False,
            on_failure="best-effort",
            stability_checks=_checks(),
        )
    else:
        options.update(reduction_unchecked=True, on_failure="return")
    return options


def _calls(runtime, points, reduction):
    """The fixed call list: (name, zero-argument call)."""

    helicities = [
        h.id
        for h in runtime.physics.helicities
        if getattr(h, "computed", True) and not getattr(h, "structural_zero", False)
    ][:2]
    unchecked, checked = _options(reduction, False), _options(reduction, True)
    return [
        ("unchecked b17", lambda: runtime.evaluate(points[:17], **unchecked)),
        ("unchecked b1", lambda: runtime.evaluate(points[:1], **unchecked)),
        ("checked b5", lambda: runtime.evaluate(points[:5], **checked)),
        ("checked b1", lambda: runtime.evaluate(points[:1], **checked)),
        (
            "checked resolved b3",
            lambda: runtime.evaluate_resolved(points[:3], **checked),
        ),
        (
            "unchecked selected b3",
            lambda: runtime.evaluate(points[:3], helicities=helicities, **unchecked),
        ),
        (
            "unchecked double-double b2",
            lambda: runtime.evaluate(
                points[:2], **_options(reduction, False, "double-double")
            ),
        ),
    ]


@pytest.fixture(scope="module")
def artifacts(tmp_path_factory, loop_native):
    """Each process's artifact and its 17 points, the points with a lane
    rescue or the reduction's own rescue (checked binary64, one thread)
    first."""

    from pyamplicol.api import Runtime
    from pyamplicol.cli.flat_points import draw_flat_points
    from pyamplicol.generation.phase_space_cuts import PhaseSpaceCuts

    built = {}
    for name, (expression, extra) in PROCESSES.items():
        artifact = _artifact(tmp_path_factory.mktemp(name), expression, extra)
        points = list(
            draw_flat_points(
                artifact,
                process=None,
                points=24,
                seed=7000001,
                sqrt_s=1000.0,
                cuts=PhaseSpaceCuts(25.0, 0.7),
            ).points
        )
        runtime = Runtime.load(artifact, threads=1)
        rescued = set()
        for reduction in _reductions(loop_native):
            result = runtime.evaluate(points, **_options(reduction, True))
            rescued |= {
                i
                for i, lane in enumerate(result.diagnostics)
                if lane.lane_rescue is not None
                or getattr(lane, "reduction_rescue", None) is not None
            }
        order = sorted(range(len(points)), key=lambda i: (i not in rescued, i))
        built[name] = (artifact, [points[i] for i in order][:17], len(rescued))
    return built


def _reductions(native) -> tuple[str, ...]:
    return ("ninjars", "tirust") if native.tirust_available() else ("ninjars",)


@pytest.mark.parametrize("reduction", ["ninjars", "tirust"])
@pytest.mark.parametrize("name", sorted(PROCESSES))
def test_results_do_not_depend_on_the_thread_count(
    artifacts, loop_native, name, reduction
):
    from pyamplicol.api import Runtime

    if reduction not in _reductions(loop_native):
        pytest.skip("the staged native extension is built without TIRust")
    artifact, points, rescued = artifacts[name]
    print(f"{name}: {rescued} of 24 candidate points rescued in checked binary64")
    records = {}
    for threads in THREADS:
        runtime = Runtime.load(artifact, threads=threads)
        records[threads] = [
            (label, _record(call)) for label, call in _calls(runtime, points, reduction)
        ]
    differences = []
    for threads in THREADS[1:]:
        for (label, one), (_, other) in zip(
            records[1], records[threads], strict=True
        ):
            if one != other:
                differences.append(
                    f"{name} {reduction} '{label}' 1 vs {threads} threads: "
                    f"{_first_difference(one, other)}"
                )
    assert not differences, "\n".join(differences[:10])


@pytest.mark.parametrize("reduction", ["ninjars", "tirust"])
def test_repeated_calls_at_eight_threads_are_bitwise_equal(
    artifacts, loop_native, reduction
):
    """A race between workers shows up as a repeat that differs."""

    from pyamplicol.api import Runtime

    if reduction not in _reductions(loop_native):
        pytest.skip("the staged native extension is built without TIRust")
    for name in sorted(PROCESSES):
        artifact, points, _rescued = artifacts[name]
        runtime = Runtime.load(artifact, threads=8)
        for checked, batch in ((False, 17), (True, 5)):
            options = _options(reduction, checked)
            first = _record(lambda: runtime.evaluate(points[:batch], **options))
            for repeat in range(1, REPEATS):
                again = _record(lambda: runtime.evaluate(points[:batch], **options))
                assert again == first, (
                    f"{name} {reduction} checked={checked} repeat {repeat}: "
                    f"{_first_difference(first, again)}"
                )


@pytest.mark.loop_nightly
@pytest.mark.parametrize("reduction", ["ninjars", "tirust"])
def test_arbitrary_precision_does_not_depend_on_the_thread_count(
    artifacts, loop_native, reduction
):
    from pyamplicol.api import Runtime

    if reduction not in _reductions(loop_native):
        pytest.skip("the staged native extension is built without TIRust")
    artifact, points, _rescued = artifacts["uux_ddxg"]
    options = _options(reduction, False, "arbitrary") | {"precision": 32}
    found = {
        threads: _record(
            lambda threads=threads: Runtime.load(artifact, threads=threads).evaluate(
                points[:1], **options
            )
        )
        for threads in (1, 8)
    }
    assert found[1] == found[8], _first_difference(found[1], found[8])
