# SPDX-License-Identifier: 0BSD
"""Frozen phase-space streams of the gate-G1 benchmark (MASTER_PLAN §5.8 item 1).

Every tool times the same stream of ``STREAM_LENGTH`` distinct exact on-shell
points per process, with mu_R cycling through 1000, 700 and 1400 GeV:

- the first ``CAMPAIGN_PREFIX`` points are the required-references
  campaign's (``tools/loop_reference/exact_points.py``: terminating
  decimals, minimal ``2|p_i.p_j|/s`` of 1/1000, resonance exclusion around
  M_Z, M_H and M_t), so the stream's first block is checked against the
  committed provider references (``tests/fixtures/loop/required/<key>.json``);
- the others come from the same tool's construction when the final state is
  massive (its parameter grid holds thousands of points), and otherwise from
  RAMBO at sqrt(s) = 1 TeV made exactly massless and momentum conserving
  (``tools/loop_v2_stability_calibration.exact_point``, with its jet cuts and
  the 1/1000 invariant cut): ``exact_points`` builds a massless final state
  from a fixed rotation cycle and one parameter per added particle, so it
  has only 12 points at 2->3 and 144 at 2->4.

pyAmpliCol reads the exact rationals (``points``); the Fortran and C++
provider drivers read decimal text, ``binary64`` (the shortest text of the
correctly rounded double), as every binary64 caller does. ``write`` freezes
the streams as ``streams/<key>.json``.
"""

from __future__ import annotations

import itertools
import json
import random
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REFERENCE = ROOT / "tools" / "loop_reference"
SPEC = HERE / "processes.json"
STREAMS = HERE / "streams"
FIXTURES = ROOT / "tests" / "fixtures" / "loop" / "required"
STREAM_LENGTH = 128
MU_R = ("1000", "700", "1400")
CUT = Fraction(1, 1000)
CAMPAIGN_PREFIX = 3
RAMBO_SEED = 20261024


def _toolkit() -> tuple[Any, Any]:
    if str(REFERENCE) not in sys.path:
        sys.path.insert(0, str(REFERENCE))
    import exact_points
    import required_spec

    return exact_points, required_spec


def spec(key: str) -> dict[str, Any]:
    """The process specification (``processes.json``, toolkit format)."""

    _, required_spec = _toolkit()
    return required_spec.load_process(SPEC, key)


def _invariants_pass(point: list[list[Fraction]]) -> bool:
    exact_points, _ = _toolkit()
    s = (point[0][0] + point[1][0]) ** 2
    return all(
        2 * abs(exact_points._dot(p, q)) >= CUT * s
        for p, q in itertools.combinations(point, 2)
    )


def _massive_grid(
    masses: list[Fraction], count: int, resonances: list[str], pdgs: list[int]
) -> list[list[list[Fraction]]]:
    """``exact_points.generate`` without its distinct-sqrt(s) rule after the
    campaign prefix (later points need only be distinct): same candidate
    sequence, cuts, resonance exclusion and exactness checks."""

    exact_points, _ = _toolkit()
    final_masses = masses[2:]
    _, additions = exact_points.plan(final_masses)
    accepted: list[list[list[Fraction]]] = []
    seen: set[tuple[Fraction, ...]] = set()
    scales: set[Fraction] = set()
    chooser = random.Random(20261020)
    window = (Fraction(800), Fraction(4000))
    for trial in itertools.count():
        if len(accepted) == count:
            return accepted
        if trial > 200 * count + 10**5:
            raise RuntimeError(f"only {len(accepted)} of {count} massive points")
        parameters = [chooser.choice(exact_points._K_SEED)] + [
            chooser.choice(exact_points._K_ADD) for _ in additions
        ]
        try:
            final, sqrt_s = exact_points.construct(
                final_masses, parameters, Fraction(100)
            )
        except ZeroDivisionError:
            continue
        if not window[0] <= sqrt_s <= window[1]:
            continue
        if len(accepted) < CAMPAIGN_PREFIX and sqrt_s in scales:
            continue
        half, zero = sqrt_s / 2, Fraction(0)
        point = [[half, zero, zero, half], [half, zero, zero, -half], *final]
        key = tuple(x for p in point for x in p)
        if key in seen or not _invariants_pass(point):
            continue
        if _resonant(final, pdgs, resonances):
            continue
        exact_points.check(point, masses, 2)
        accepted.append(point)
        seen.add(key)
        scales.add(sqrt_s)
    raise AssertionError("unreachable")


def _resonant(final, pdgs, resonances) -> bool:
    exact_points, _ = _toolkit()
    for (i, p), (j, q) in itertools.combinations(enumerate(final), 2):
        if pdgs[2 + i] != -pdgs[2 + j]:
            continue
        pair = [x + y for x, y in zip(p, q, strict=True)]
        pair_s = exact_points._dot(pair, pair)
        if any(
            abs(pair_s - Fraction(r) ** 2) < Fraction(r) ** 2 / 10 for r in resonances
        ):
            return True
    return False


def _rambo(count: int, legs: int, pdgs: list[int], resonances) -> list:
    """``count`` exact massless points (calibration tool's construction)."""

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from tools.loop_v2_stability_calibration import (
        ENERGY,
        _passes_cuts,
        exact_point,
    )

    exact_points, _ = _toolkit()
    rng = random.Random(RAMBO_SEED)
    out: list = []
    while len(out) < count:
        point = [list(p) for p in exact_point(legs - 2, ENERGY, rng)]
        if not _passes_cuts(point) or not _invariants_pass(point):
            continue
        if _resonant(point[2:], pdgs, resonances):
            continue
        exact_points.check(point, [Fraction(0)] * legs, 2)
        out.append(point)
    return out


def _text(x: Fraction) -> str:
    exact_points, _ = _toolkit()
    if exact_points.terminating(x):
        return exact_points.decimal_string(x)
    return f"{x.numerator}/{x.denominator}"


def make_stream(key: str, count: int = STREAM_LENGTH) -> dict[str, Any]:
    """The frozen stream of ``key`` (module docstring)."""

    exact_points, required_spec = _toolkit()
    process = spec(key)
    masses = [Fraction(m) for m in required_spec.masses(process)]
    values = {
        **process["scheme_data"]["parameters"],
        **process["scheme_data"]["fixed_parameters"],
    }
    resonances = [
        values[name]
        for name in ("MZ", "MW", "MH", "MT")
        if name in values and Fraction(values[name])
    ]
    pdgs = process["pdgs"]
    if any(masses[2:]):
        points = _massive_grid(masses, count, resonances, pdgs)
        construction = "exact_points grid (distinct points after the prefix)"
    else:
        prefix = exact_points.generate(
            masses, CAMPAIGN_PREFIX, CUT, resonances, pdgs=pdgs
        )
        points = prefix + _rambo(count - CAMPAIGN_PREFIX, len(pdgs), pdgs, resonances)
        construction = (
            "exact_points campaign prefix, then RAMBO at sqrt(s) = 1 TeV made exactly "
            "massless (loop_v2_stability_calibration.exact_point, its jet cuts)"
        )
    return {
        "process_name": key,
        "pdgs": pdgs,
        "masses": [_text(m) for m in masses],
        "construction": construction,
        "cuts": {
            "min_2pipj_over_s": str(CUT),
            "resonance_exclusion": "|s_ij-M^2| >= M^2/10 for final "
            "particle-antiparticle pairs",
            "resonances": resonances,
        },
        "campaign_prefix": CAMPAIGN_PREFIX,
        "points": [[[_text(x) for x in leg] for leg in point] for point in points],
        "mu_r": list(itertools.islice(itertools.cycle(MU_R), count)),
    }


def path(key: str) -> Path:
    return STREAMS / f"{key}.json"


def load(key: str) -> dict[str, Any]:
    """The frozen stream of ``key``."""

    return json.loads(path(key).read_text())


def exact(stream: dict[str, Any], index: int) -> list[list[Fraction]]:
    return [[Fraction(x) for x in leg] for leg in stream["points"][index]]


def binary64(stream: dict[str, Any], count: int) -> list[list[list[str]]]:
    """The first ``count`` points as the providers read them: the shortest
    decimal text of each component's correctly rounded double."""

    return [
        [[repr(float(Fraction(x))) for x in leg] for leg in point]
        for point in stream["points"][:count]
    ]


def fixture_name(key: str) -> str:
    """The reference fixture of ``key`` (``tests/fixtures/loop/required``):
    the specification's ``reference_fixture`` (e.g. NJet's
    ``gg_ggggg_njet``), else the required fixture of the same name."""

    return spec(key).get("reference_fixture", key)


def campaign_agreement(key: str, stream: dict[str, Any]) -> bool | None:
    """Whether the stream starts with the committed fixture's points (None
    without a fixture)."""

    fixture = FIXTURES / f"{key}.json"
    if not fixture.exists():
        return None
    data = json.loads(fixture.read_text())
    count = len(data["points"])
    return (
        stream["points"][:count] == data["points"]
        and stream["mu_r"][:count] == data["mu_r"]
    )


def write(keys: list[str], count: int = STREAM_LENGTH) -> None:
    STREAMS.mkdir(exist_ok=True)
    for key in keys:
        stream = make_stream(key, count)
        agreement = campaign_agreement(key, stream)
        if agreement is False:
            raise AssertionError(f"{key}: the stream does not start with the campaign")
        path(key).write_text(json.dumps(stream, separators=(",", ":")) + "\n")
        print(key, len(stream["points"]), "points; campaign prefix:", agreement)


def keys() -> list[str]:
    return [p["name"] for p in json.loads(SPEC.read_text())["processes"]]
