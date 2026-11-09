# SPDX-License-Identifier: 0BSD
"""Frozen phase-space streams of the gate-G1 benchmark (MASTER_PLAN §5.8 item 1).

Every tool times the same stream of ``STREAM_LENGTH`` distinct exact on-shell
points per process, with mu_R cycling through 1000, 700 and 1400 GeV:

- the first ``CAMPAIGN_PREFIX`` points are the required-references
  campaign's (``tools/loop_reference/exact_points.py``: terminating
  decimals, minimal ``2|p_i.p_j|/s`` of 1/1000, resonance exclusion around
  M_Z, M_H and M_t), so the stream's first block is checked against the
  committed provider references (``tests/fixtures/loop/required/<key>.json``);
- beyond ``CAMPAIGN_MAX_FINAL`` massless final-state particles (2->6: no
  provider serves it, so there is no campaign to start with) the whole stream
  is RAMBO's: the campaign construction finds no point passing the 1/1000
  invariant cut there (0 of ~17,000 candidates in 30 s at 2->6);
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

Decays (1 -> n, the processes of ``tools/loop_reference/required_processes.json``
with ``"initial": 1``, ``decay_keys``, and the loop-induced decays of
``processes.json``) take ``STREAM_LENGTH`` exact points in the decaying
particle's rest frame (``tools/loop_reference/decay_points.py``, same cuts;
mu_R = the decaying mass); the first ``CAMPAIGN_PREFIX`` printed to 32 digits
are the decay reference campaign's points (``tests/fixtures/loop/required/
dec/<key>.json``, a loop-induced decay's ``required/li/<key>.json``).

A 2 -> 1 process (the toolkit's ``rest`` family, e.g. the loop-induced
g g > h) has one point up to the direction of the beam axis: its stream is the
final particle at rest with the beams along ``STREAM_LENGTH`` distinct exact
rational directions, the first ``CAMPAIGN_PREFIX`` the reference campaign's
(``supplied_points.rotation``), the others rational points of the unit sphere
(inverse stereographic projection of a fixed pseudo-random rational grid).
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
DECAY_SPEC = REFERENCE / "required_processes.json"
STREAMS = HERE / "streams"
FIXTURES = ROOT / "tests" / "fixtures" / "loop" / "required"
STREAM_LENGTH = 128
MU_R = ("1000", "700", "1400")
CUT = Fraction(1, 1000)
CAMPAIGN_PREFIX = 3
# The largest massless final state of a required-references campaign (2->5).
CAMPAIGN_MAX_FINAL = 5
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
    masses: list[Fraction],
    count: int,
    resonances: list[str],
    pdgs: list[int],
    window: tuple[Fraction, Fraction] = (Fraction(800), Fraction(4000)),
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


def _pair_points(
    masses: list[Fraction],
    count: int,
    window: tuple[Fraction, Fraction],
    taken: list[list[list[Fraction]]],
) -> list[list[list[Fraction]]]:
    """``count`` exact 2 -> 2 points with a massive final pair: the final
    state of each is ``decay_points``' exact rational two-body split of the
    centre-of-mass system (a rational point on the momentum sphere, seeded
    rotation), at distinct sqrt(s) inside ``window`` (sqrt(s) values whose
    momentum sphere holds no rational point are skipped; for an equal-mass
    pair, where a whole progression of sqrt(s) can lack one, e.g. Z Z or H H
    from 800 GeV, the step's sqrt(s) is moved to ``_equal_mass_scale``,
    whose momentum is rational)."""

    exact_points, _ = _toolkit()
    import decay_points

    final = masses[2:]
    low = max(window[0], sum(final) + 1)
    seen = {tuple(x for p in point for x in p) for point in taken}
    out: list[list[list[Fraction]]] = []
    step = 0
    while len(out) < count:
        step += 1
        if step > 100 * count:
            raise RuntimeError(f"only {len(out)} of {count} two-body points")
        sqrt_s = low + (window[1] - low) * Fraction(step, 4 * count + 1)
        try:
            (rest,) = decay_points.generate(
                [sqrt_s, *final], 1, CUT, (), seed=decay_points.SEED + step
            )
        except ValueError:
            sqrt_s = _equal_mass_scale(
                final, (low, window[1]), Fraction(step, 4 * count + 1)
            )
            if sqrt_s is None:
                continue
            try:
                (rest,) = decay_points.generate(
                    [sqrt_s, *final], 1, CUT, (), seed=decay_points.SEED + step
                )
            except ValueError:
                continue
        half, zero = sqrt_s / 2, Fraction(0)
        point = [[half, zero, zero, half], [half, zero, zero, -half], rest[1], rest[2]]
        key = tuple(x for p in point for x in p)
        if key in seen or not _invariants_pass(point):
            continue
        exact_points.check(point, masses, 2)
        out.append(point)
        seen.add(key)
    return out


def _equal_mass_scale(
    final: list[Fraction], window: tuple[Fraction, Fraction], fraction: Fraction
) -> Fraction | None:
    """For an equal-mass pair m m: a sqrt(s) = 2 m (1 + t^2) / (1 - t^2) with
    rational t, whose momentum |p| = 2 m t / (1 - t^2) is rational, at the
    ``fraction`` of the window in t (None for any other final state or outside
    the window)."""

    if len(final) != 2 or final[0] != final[1] or not final[0]:
        return None
    m = final[0]

    def t_of(scale: Fraction) -> float:
        return float((scale - 2 * m) / (scale + 2 * m)) ** 0.5

    lo, hi = t_of(max(window[0], 2 * m)), t_of(window[1])
    t = Fraction(lo + (hi - lo) * float(fraction)).limit_denominator(10**6)
    if not 0 < t < 1:
        return None
    scale = 2 * m * (1 + t * t) / (1 - t * t)
    return scale if window[0] <= scale <= window[1] else None


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


def _supplied(
    masses: list[Fraction], count: int, record: dict[str, Any], pdgs: list[int]
) -> list[list[list[Fraction]]]:
    """``supplied_points.generate`` (regular family) at the specification's
    ``sqrt_s`` values cycled to ``count`` points: the same construction,
    cuts and printed quantum as the reference campaign's points file, so
    the stream starts with the campaign's points. A repeated point (a 2 -> 2
    final state has few direction choices per sqrt(s)) is skipped: the
    construction is extended along the same cycle until ``count`` distinct
    points (its sequence is prefix-stable)."""

    _toolkit()
    from decimal import localcontext

    import supplied_points

    listed = [Fraction(s) for s in record["sqrt_s"]]
    length = count
    while True:
        values = list(itertools.islice(itertools.cycle(listed), length))
        with localcontext() as context:
            context.prec = supplied_points.CONSTRUCTION_DIGITS
            points, scales, _ = supplied_points.generate(
                masses, "regular", length, (), CUT, (), pdgs, sqrt_s_values=values
            )
            printed = [
                supplied_points.quantise(point, scale)
                for point, scale in zip(points, scales, strict=True)
            ]
        distinct: list[list[list[Fraction]]] = []
        seen: set[tuple[Fraction, ...]] = set()
        for point in printed:
            exact = [[Fraction(supplied_points.text(x)) for x in leg] for leg in point]
            key = tuple(x for leg in exact for x in leg)
            if key not in seen:
                seen.add(key)
                distinct.append(exact)
        if len(distinct) >= count:
            return distinct[:count]
        if length > 100 * count:
            raise RuntimeError(
                f"only {len(distinct)} of {count} distinct supplied points"
            )
        length *= 2


def _rest(masses: list[Fraction], count: int) -> list[list[list[Fraction]]]:
    """``count`` exact 2 -> 1 points at sqrt(s) = the final mass (massless
    beams): the beam axis turned by ``supplied_points.rotation`` for the first
    ``CAMPAIGN_PREFIX`` points (the reference campaign's ``rest`` family),
    then along rational unit vectors n = (2a, 2b, 1 - a^2 - b^2) / (1 + a^2 +
    b^2) for rational (a, b) drawn from a fixed pseudo-random grid, every
    direction distinct."""

    _toolkit()
    import supplied_points

    if len(masses) != 3 or any(masses[:2]) or not masses[2]:
        raise ValueError(
            "a 2 -> 1 rest stream needs massless beams and a massive final particle"
        )
    pythagorean = supplied_points._PYTHAGOREAN
    half, mass, zero = masses[2] / 2, masses[2], Fraction(0)

    def turned(index: int) -> tuple[Fraction, Fraction, Fraction]:
        # supplied_points.rotation(index) applied to the unit z vector, in
        # exact rationals: R_x(c1, s1) R_y(c2, s2) e_z.
        c1, s1 = pythagorean[index % len(pythagorean)]
        c2, s2 = pythagorean[(3 * index + 1) % len(pythagorean)]
        return (s2, -s1 * c2, c1 * c2)

    directions: list[tuple[Fraction, Fraction, Fraction]] = []
    for index in range(min(count, CAMPAIGN_PREFIX)):
        directions.append(turned(index))
    chooser = random.Random(RAMBO_SEED)
    grid = [Fraction(p, q) for q in range(1, 13) for p in range(-24, 25)]
    while len(directions) < count:
        a, b = chooser.choice(grid), chooser.choice(grid)
        norm = 1 + a * a + b * b
        n = (2 * a / norm, 2 * b / norm, (1 - a * a - b * b) / norm)
        if n not in directions:
            directions.append(n)
    return [
        [
            [half, half * n[0], half * n[1], half * n[2]],
            [half, -half * n[0], -half * n[1], -half * n[2]],
            [mass, zero, zero, zero],
        ]
        for n in directions
    ]


def decay_keys() -> list[str]:
    """The decay processes (``"initial": 1``) of the reference specification,
    the Born-interfered ones (the loop-induced decays, M-LIT, have their
    points in their reference fixtures)."""

    return [
        p["name"]
        for p in json.loads(DECAY_SPEC.read_text())["processes"]
        if p.get("initial") == 1 and not p.get("loop_induced")
    ]


def _resonances(process: dict[str, Any]) -> list[str]:
    values = {
        **process["scheme_data"]["parameters"],
        **process["scheme_data"]["fixed_parameters"],
    }
    return [
        values[name]
        for name in ("MZ", "MW", "MH", "MT")
        if name in values and Fraction(values[name])
    ]


def _decay(key: str) -> bool:
    """Whether ``key`` is a decay: a Born-interfered one of the reference
    specification (``decay_keys``) or a ``processes.json`` process with
    ``"initial": 1`` (the loop-induced decays)."""

    if key in decay_keys():
        return True
    return key in keys() and spec(key).get("initial") == 1


def make_decay_stream(key: str, count: int = STREAM_LENGTH) -> dict[str, Any]:
    """The frozen rest-frame stream of the decay ``key`` (module docstring)."""

    _, required_spec = _toolkit()
    import decay_points

    source = SPEC if key in keys() else DECAY_SPEC
    process = required_spec.load_process(source, key)
    masses = [Fraction(m) for m in required_spec.masses(process)]
    resonances = _resonances(process)
    points = decay_points.generate(masses, count, CUT, resonances, pdgs=process["pdgs"])
    return {
        "process_name": key,
        "pdgs": process["pdgs"],
        "initial": 1,
        "masses": [_text(m) for m in masses],
        "construction": "decay_points rest-frame construction (seed "
        f"{decay_points.SEED}): exact rationals, the decaying particle at rest",
        "cuts": {
            "min_2pipj_over_M2": str(CUT),
            "resonance_exclusion": "|s_ij-M^2| >= M^2/10 for final "
            "particle-antiparticle pairs (1 -> 3 and beyond)",
            "resonances": resonances,
        },
        "campaign_prefix": CAMPAIGN_PREFIX,
        "points": [[[_text(x) for x in leg] for leg in point] for point in points],
        "mu_r": [_text(masses[0])] * count,
    }


def decay_campaign_agreement(key: str, stream: dict[str, Any]) -> bool | None:
    """Whether the decay campaign's points (``required/dec/<key>.json``, a
    loop-induced decay's ``required/li/<key>.json``) are the stream's first
    points printed to 32 digits (None without a fixture)."""

    induced = key in keys() and spec(key).get("loop_induced")
    fixture = FIXTURES / ("li" if induced else "dec") / f"{key}.json"
    if not fixture.exists():
        return None
    _toolkit()
    import decay_points

    data = json.loads(fixture.read_text())
    count = min(len(data["points"]), CAMPAIGN_PREFIX)
    printed = [decay_points.decimal_point(exact(stream, i)) for i in range(count)]
    return printed == data["points"][:count]


def make_stream(key: str, count: int = STREAM_LENGTH) -> dict[str, Any]:
    """The frozen stream of ``key`` (module docstring)."""

    if _decay(key):
        return make_decay_stream(key, count)
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
    prefix_count = CAMPAIGN_PREFIX
    # A loop-induced specification may set its points' sqrt(s) window
    # (``points.scale_window`` of the toolkit specification).
    window = tuple(
        Fraction(x)
        for x in process.get("points", {}).get("scale_window", ("800", "4000"))
    )
    record = process.get("points", {})
    if record.get("tool") == "supplied_points.py" and record.get("family") == "rest":
        # A 2 -> 1 process: the final particle at rest, the beam axis along
        # distinct exact rational directions (module docstring).
        points = _rest(masses, count)
        construction = (
            "2 -> 1 at rest: the beams along distinct exact rational directions "
            "(the campaign's supplied_points rest rotations first, then rational "
            "points of the unit sphere)"
        )
    elif (
        record.get("tool") == "supplied_points.py" and record.get("family") == "regular"
    ):
        # A loop-induced specification whose mass pattern exact_points cannot
        # represent (g g > h h h, g g > z z z, g g > h z g): its listed
        # sqrt(s) values cycled, so the first points are the campaign's.
        points = _supplied(masses, count, record, pdgs)
        construction = (
            "supplied_points regular family at the specification's sqrt(s) values, "
            "cycled (30 significant digits, exact momentum conservation, mass shells "
            "to ~1e-29); the first points are the reference campaign's"
        )
    elif any(masses[2:]) and len(pdgs) == 4:
        # A massive 2 -> 2 final pair: the exact_points grid holds only a
        # dozen points (one parameter, a few rotations); the campaign prefix
        # comes from it, the rest from exact rational CM-frame points.
        prefix = _massive_grid(masses, CAMPAIGN_PREFIX, resonances, pdgs, window)
        points = prefix + _pair_points(masses, count - CAMPAIGN_PREFIX, window, prefix)
        construction = (
            "exact_points campaign prefix, then exact rational centre-of-mass "
            "points of distinct sqrt(s) (decay_points' two-body construction)"
        )
    elif any(masses[2:]):
        points = _massive_grid(masses, count, resonances, pdgs, window)
        construction = "exact_points grid (distinct points after the prefix)"
    elif len(pdgs) - 2 > CAMPAIGN_MAX_FINAL:
        prefix_count = 0
        points = _rambo(count, len(pdgs), pdgs, resonances)
        construction = (
            "RAMBO at sqrt(s) = 1 TeV made exactly massless "
            "(loop_v2_stability_calibration.exact_point, its jet cuts); no campaign "
            f"prefix beyond {CAMPAIGN_MAX_FINAL} final-state particles"
        )
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
        "campaign_prefix": prefix_count,
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


def mu_r2(stream: dict[str, Any], count: int) -> list[str]:
    """The first ``count`` points' mu_R^2 as decimal text, as the public API
    reads it (``Runtime.evaluate(..., mu_r2=...)`` takes decimal numbers):
    the exact square of the stream's mu_R (a terminating decimal stays
    exact, e.g. M_Z^2 = 8315.251344 for a Z decay)."""

    exact_points, _ = _toolkit()
    out = []
    for m in stream["mu_r"][:count]:
        square = Fraction(m) ** 2
        if not exact_points.terminating(square):
            raise ValueError(f"mu_R^2 = {square} has no exact decimal text")
        out.append(exact_points.decimal_string(square))
    return out


def fixture_name(key: str) -> str:
    """The reference fixture of ``key`` (``tests/fixtures/loop/required``):
    the specification's ``reference_fixture`` (e.g. NJet's
    ``gg_ggggg_njet``), else the required fixture of the same name."""

    return spec(key).get("reference_fixture", key)


def campaign_agreement(key: str, stream: dict[str, Any]) -> bool | None:
    """Whether the stream starts with the committed fixture's points (None
    without a fixture; a decay's printed points: ``decay_campaign_agreement``)."""

    if stream.get("initial") == 1:
        return decay_campaign_agreement(key, stream)
    # Loop-induced references: required/li (tools/loop_reference/li_references.py).
    sub = "li" if spec(key).get("loop_induced") else ""
    fixture = FIXTURES / sub / f"{key}.json"
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
        agreement = (
            decay_campaign_agreement(key, stream)
            if stream.get("initial") == 1
            else campaign_agreement(key, stream)
        )
        if agreement is False:
            raise AssertionError(f"{key}: the stream does not start with the campaign")
        path(key).write_text(json.dumps(stream, separators=(",", ":")) + "\n")
        print(key, len(stream["points"]), "points; campaign prefix:", agreement)


def keys() -> list[str]:
    return [p["name"] for p in json.loads(SPEC.read_text())["processes"]]
