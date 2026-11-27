# SPDX-License-Identifier: 0BSD
"""Extended-precision evaluation with a beam a rounding residue off the axis.

Above binary64 a tree evaluation first improves the caller's points
(``pyamplicol.kinematics``, on by default). When the z-shift refuses a
massive initial state, the fallback projection spreads the points' binary64
conservation defect over every leg, beams included: a beam along -z then
carries a transverse momentum of about 1e-17 GeV. The external fermion
sources form their light-cone component there, and it cancels:

* a massive Dirac source formed ``|p| + pz`` from the rounded ``|p|``
  (at 40 working digits, the working precision of every request from 17 to
  32 digits, 9.4e-37 for 8.8e-37: a top spinor 6 % off and
  ``b~ t > w+ h`` 12 % off in the compiled and eager lanes);
* a massless Weyl source formed ``E + pz``, which then depends on the point's
  residual ``p²`` (zero only to the carrier's precision, also after the
  improvement) amplified by ``E² / pT²`` (``t d > t d`` 2e-6 off).

The same sums were in the native generic (double-double and MPFR) sources
that the one-loop runtime's trees use: the double-double virtual of a
process with a massive fermion in the initial state was off by about 1e-17.
Both are now formed without the cancellation (``|p| + pz = pT² / (|p| - pz)``
and, massless, ``E + pz = pT² / (E - pz)`` when ``E`` and ``pz`` have
opposite signs), in every carrier. The binary64 sources had the same
cancellation for a physical fermion close to the axis (a forward or backward
final state: u u~ > t t~ 5e-5 off at 1 - cos(theta) = 1e-12, 3e-2 at 1e-15).
"""

from __future__ import annotations

import math
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from pyamplicol import CorrelatorConfig, Generator, ModelSource, Runtime
from pyamplicol.config import (
    ColorConfig,
    EvaluatorConfig,
    EvaluatorOptimizationConfig,
    GenerationConfig,
    GenerationRelationDiscoveryConfig,
    GenerationValidationConfig,
    RunConfig,
)
from pyamplicol.generation.phase_space import massive_rambo_final_state
from pyamplicol.runtime.symbolica_exact import _antiquark_dirac, _quark_dirac

LANES = ("compiled", "eager", "recurrence")
PRECISIONS = (17, 24, 32, 33, 50)
REFERENCE_PRECISION = 100


def _norm(wave: tuple[tuple[Decimal, Decimal], ...]) -> Decimal:
    return sum((re * re + im * im for re, im in wave), Decimal(0))


@pytest.mark.parametrize("digits", [25, 40, 48])
@pytest.mark.parametrize("mass", ["0", "173"])
def test_fermion_sources_near_the_minus_z_axis_keep_their_norm(
    digits: int, mass: str
) -> None:
    """u†u = 2|E| for a fermion a rounding residue off the z axis, at both
    orientations and energy signs (a crossed leg is negated): the massive
    source's |p| + pz kept only the digits of the rounded |p|, the massless
    one's E + pz the residual p² of a point on shell to the carrier (its E
    rounded to ``digits``) amplified by E²/pT²."""

    with localcontext() as context:
        context.prec = digits
        m = Decimal(mass)
        pt = Decimal(10) ** -(digits // 2 - 2) * Decimal(485) / 7
        px, py, pz = pt * Decimal("0.6"), pt * Decimal("0.8"), Decimal(485)
        energy = (px * px + py * py + pz * pz + m * m).sqrt()
        for axis in (-1, 1):
            for sign in (-1, 1):
                momentum = (sign * energy, sign * px, sign * py, sign * axis * pz)
                for helicity in (-1, 1):
                    for source in (_quark_dirac, _antiquark_dirac):
                        norm = _norm(source(momentum, helicity, m))
                        error = abs(norm / (2 * energy) - 1)
                        assert error < Decimal(10) ** -(digits - 6), (
                            source.__name__,
                            axis,
                            sign,
                            helicity,
                            error,
                        )


def _config(lane: str) -> RunConfig:
    return RunConfig(
        action="generate",
        color=ColorConfig(accuracy="full"),
        evaluator=EvaluatorConfig(
            execution_mode=lane,
            optimization=EvaluatorOptimizationConfig(cores=1, horner_iterations=1),
        ),
        generation=GenerationConfig(
            workers=1,
            emit_api_bundle=False,
            relation_discovery=GenerationRelationDiscoveryConfig(mode="off"),
            validation=GenerationValidationConfig(
                enabled=False, samples=1, seed=7, post_build_validation=False
            ),
        ),
    )


def _points(masses: list[float], seeds: tuple[int, ...] = (9001, 9002)) -> list:
    """Two RAMBO points at sqrt(s) = 1000 GeV, the beams along the z axis
    (binary64: their conservation defect is what the improvement projects)."""

    sqrt_s = 1000.0
    m1, m2 = masses[:2]
    s = sqrt_s**2
    p = math.sqrt((s - (m1 + m2) ** 2) * (s - (m1 - m2) ** 2)) / (2 * sqrt_s)
    beams = [[math.hypot(p, m1), 0.0, 0.0, p], [math.hypot(p, m2), 0.0, 0.0, -p]]
    return [
        [
            *beams,
            *(
                list(q)
                for q in massive_rambo_final_state(
                    len(masses) - 2, sqrt_s=sqrt_s, masses=masses[2:], seed=seed
                )
            ),
        ]
        for seed in seeds
    ]


def _relative(values, reference) -> float:
    return max(
        float(abs(Decimal(value) - b) / abs(b))
        for value, b in zip(values, reference, strict=True)
    )


def _check_lane(runtime: Runtime, points: list) -> None:
    reference = runtime.evaluate(points, precision=REFERENCE_PRECISION)
    assert all(value > 0 for value in reference)
    binary64 = [complex(value).real for value in runtime.evaluate(points)]
    assert _relative([repr(x) for x in binary64], reference) < 1e-13
    for precision in PRECISIONS:
        values = runtime.evaluate(points, precision=precision)
        assert _relative(values, reference) < 10.0 ** -(precision - 1), precision


@pytest.mark.parametrize("lane", LANES)
@pytest.mark.parametrize(
    "process",
    [
        "d t > d t",  # the massive beam along -z
        "t d > t d",  # a massless beam along -z
        "t~ t > z h",
    ],
)
def test_builtin_massive_initial_fermion_at_every_precision(
    process: str, lane: str, tmp_path: Path
) -> None:
    from pyamplicol.models import BuiltinSMModel

    Generator(_config(lane)).generate(
        [process], tmp_path / "artifact", model=ModelSource.built_in_sm()
    )
    runtime = Runtime.load(tmp_path / "artifact")
    sm = BuiltinSMModel()
    masses = [sm.mass(leg.pdg_id) for leg in runtime.physics.external_particles]
    _check_lane(runtime, _points(masses))


@pytest.fixture(scope="module")
def sm_default(
    madgraph_source: Path, tmp_path_factory: pytest.TempPathFactory
) -> ModelSource:
    root = tmp_path_factory.mktemp("madgraph-sm")
    bundle = root / "sm.pyamplicol-model"
    ModelSource.from_path(madgraph_source / "models/sm", restriction="default").compile(
        cache_dir=root / "cache", prepared_output=bundle, evaluator=EvaluatorConfig()
    )
    return ModelSource.from_path(bundle)


def _sm_masses(process_runtime: Runtime) -> list[float]:
    parameters = {
        p.name: p.default_real for p in process_runtime.physics.model_parameters
    }
    mz, alpha, gf = parameters["MZ"], 1 / parameters["aEWM1"], parameters["Gf"]
    mw = math.sqrt(
        mz**2 / 2
        + math.sqrt(mz**4 / 4 - (alpha * math.pi * mz**2) / (gf * math.sqrt(2)))
    )
    names = {5: "MB", 6: "MT", 15: "MTA", 23: "MZ", 25: "MH"}
    return [
        mw
        if abs(leg.pdg_id) == 24
        else float(parameters.get(names.get(abs(leg.pdg_id), ""), 0.0))
        for leg in process_runtime.physics.external_particles
    ]


@pytest.mark.parametrize("lane", LANES)
@pytest.mark.parametrize("process", ["b~ t > w+ h", "b e+ > t ve~"])
def test_ufo_sm_massive_initial_fermions_at_every_precision(
    sm_default: ModelSource, process: str, lane: str, tmp_path: Path
) -> None:
    """b~ t > w+ h was 12 % off at 17 to 32 digits in the compiled and eager
    lanes (the reported case); b e+ > t ve~ has the massless beam along -z."""

    Generator(_config(lane)).generate(
        [process], tmp_path / "artifact", model=sm_default
    )
    runtime = Runtime.load(tmp_path / "artifact")
    _check_lane(runtime, _points(_sm_masses(runtime)))


def test_ufo_sm_correlated_born_near_the_axis(
    sm_default: ModelSource, tmp_path: Path
) -> None:
    """The correlated reader (arbitrary precision at every requested
    precision) was 7.6e-10 off at 16 and 32 digits on b~ t > w+ h; its
    double-double carrier takes the same sources."""

    Generator(_config("compiled")).generate(
        ["b~ t > w+ h"],
        tmp_path / "artifact",
        model=sm_default,
        correlators=CorrelatorConfig(),
    )
    runtime = Runtime.load(tmp_path / "artifact")
    points = _points(_sm_masses(runtime))
    reference = [
        value.real for value in runtime.evaluate_correlated(points, precision=100)
    ]
    for precision in (16, 32, 50):
        values = [
            value.real
            for value in runtime.evaluate_correlated(points, precision=precision)
        ]
        assert _relative(values, reference) < 10.0 ** -(precision - 1), precision
    double_double = [
        value.real
        for value in runtime.evaluate_correlated(
            points, arithmetic="double-double", precision=31
        )
    ]
    assert _relative(double_double, reference) < 1e-28


LOOP_CARD = """
action = "generate"
[model]
source = "loop_sm"
restriction = "no_widths"
[process]
entries = [{{ expression = "{process}", name = "{name}" }}]
loop_coupling_orders = ["QCD"]
[loop.preparation]
fixed_parameters = {{ WT = "0", WZ = "0", WW = "0", WH = "0" }}
[generation]
output = "{output}"
workers = 1
"""


def _flat(evaluation) -> list[Decimal]:
    values = [Decimal(str(x)) for row in evaluation.born_values for x in row]
    for row in evaluation.values:
        for sector in row:
            values.extend(Decimal(str(x)) for x in sector if x is not None)
    return values


@pytest.mark.loop_physics
@pytest.mark.parametrize("process", ["g b > t w-", "t t~ > b b~"])
def test_loop_double_double_with_a_massive_initial_fermion(
    loop_native, process: str, tmp_path: Path
) -> None:
    """The double-double Born and virtual agree with 100 digits to the
    carrier (they were 2e-18 and 6e-17 off: the loop runtime's trees take
    the native generic sources)."""

    from pyamplicol.api import ProcessRequest, ProcessSet
    from pyamplicol.config import resolve_config

    card = tmp_path / "card.toml"
    card.write_text(
        LOOP_CARD.format(process=process, name="near_axis", output=tmp_path / "art")
    )
    Generator(resolve_config(card)).generate(
        ProcessSet((ProcessRequest.parse(process, name="near_axis"),)),
        tmp_path / "art",
    )
    runtime = Runtime.load(tmp_path / "art", lane_rescue=False)
    mz, alpha, gf = 91.188, 1 / 132.507, 1.16639e-5
    mw = math.sqrt(
        mz**2 / 2
        + math.sqrt(mz**4 / 4 - (alpha * math.pi * mz**2) / (gf * math.sqrt(2)))
    )
    mass = {5: 4.7, 6: 173.0, 23: mz, 24: mw}
    # Seed 9012: one of the points (3 and 4 of 20) where the double-double
    # spinor of the beam along -z nearly vanished (the value 99 % off).
    points = _points(
        [mass.get(abs(leg.pdg_id), 0.0) for leg in runtime.physics.external_particles],
        seeds=(9001, 9012),
    )
    scales = [8315.25] * len(points)
    reference = _flat(
        runtime.evaluate(points, mu_r2=scales, arithmetic="arbitrary", precision=100)
    )
    for arithmetic, precision, bound in (
        ("double-double", None, 1e-28),
        ("arbitrary", 50, 1e-45),
    ):
        values = _flat(
            runtime.evaluate(
                points, mu_r2=scales, arithmetic=arithmetic, precision=precision
            )
        )
        assert len(values) == len(reference)
        worst = max(
            float(abs(a - b) / abs(b))
            for a, b in zip(values, reference, strict=True)
            if b != 0
        )
        assert worst < bound, (arithmetic, worst)


# Binary64 (commit B): the same cancellation for a physical final state close
# to the beam axis. The reference is the exact runtime at 100 digits on the
# same binary64 input (improvement off: both evaluate the caller's point), so
# the tolerance is the binary64 evaluation's own rounding; s-channel processes,
# whose matrix element is well conditioned in the forward direction.
FORWARD = (8, 12, 15)


def _forward_point(masses: list[float], one_minus_cos: float, sign: int) -> list:
    sqrt_s = 1000.0
    m1, m2, m3, m4 = masses
    s = sqrt_s**2
    beam = math.sqrt((s - (m1 + m2) ** 2) * (s - (m1 - m2) ** 2)) / (2 * sqrt_s)
    q = math.sqrt((s - (m3 + m4) ** 2) * (s - (m3 - m4) ** 2)) / (2 * sqrt_s)
    cos = sign * (1 - one_minus_cos)
    sin = math.sqrt(1 - cos * cos)
    p3 = [math.hypot(q, m3), q * sin * 0.6, q * sin * 0.8, q * cos]
    return [
        [math.hypot(beam, m1), 0.0, 0.0, beam],
        [math.hypot(beam, m2), 0.0, 0.0, -beam],
        p3,
        [math.hypot(q, m4), -p3[1], -p3[2], -p3[3]],
    ]


@pytest.mark.parametrize("lane", (*LANES, "on-the-fly"))
@pytest.mark.parametrize("process", ["u u~ > t t~", "e+ e- > u u~"])
def test_binary64_forward_and_backward_fermions(
    process: str, lane: str, tmp_path: Path
) -> None:
    """u u~ > t t~ was 2e-9 off at 1 - cos(theta) = 1e-8, 5e-5 at 1e-12 and
    3e-2 at 1e-15 in binary64 (the massive spinor's |p| + pz from the rounded
    |p|); a massless final quark the same through E + pz."""

    from pyamplicol.models import BuiltinSMModel

    Generator(_config(lane)).generate(
        [process], tmp_path / "artifact", model=ModelSource.built_in_sm()
    )
    runtime = Runtime.load(tmp_path / "artifact")
    sm = BuiltinSMModel()
    masses = [sm.mass(leg.pdg_id) for leg in runtime.physics.external_particles]
    points = [
        _forward_point(masses, 10.0**-k, sign) for k in FORWARD for sign in (1, -1)
    ]
    binary64 = [complex(value).real for value in runtime.evaluate(points)]
    if lane == "on-the-fly":
        # The on-the-fly lane serves binary64 only: its reference is the
        # compiled lane's exact runtime on the same points.
        Generator(_config("compiled")).generate(
            [process], tmp_path / "exact", model=ModelSource.built_in_sm()
        )
        exact = Runtime.load(tmp_path / "exact")
    else:
        exact = runtime
    wide = exact.evaluate(
        points, precision=REFERENCE_PRECISION, kinematics_improvement="off"
    )
    assert _relative([repr(x) for x in binary64], wide) < 1e-12


@pytest.mark.loop_physics
def test_loop_binary64_forward_massive_fermion(loop_native, tmp_path: Path) -> None:
    """A default one-loop call (binary64, checks and lane rescue on) on
    g b > t w- with the top within 1e-6 rad of the axis was served as a
    success 1e-2 off (1 - cos(theta) = 1e-15)."""

    from pyamplicol.api import ProcessRequest, ProcessSet
    from pyamplicol.config import resolve_config

    process = "g b > t w-"
    card = tmp_path / "card.toml"
    card.write_text(
        LOOP_CARD.format(process=process, name="forward", output=tmp_path / "art")
    )
    Generator(resolve_config(card)).generate(
        ProcessSet((ProcessRequest.parse(process, name="forward"),)),
        tmp_path / "art",
    )
    runtime = Runtime.load(tmp_path / "art")
    mz, alpha, gf = 91.188, 1 / 132.507, 1.16639e-5
    mw = math.sqrt(
        mz**2 / 2
        + math.sqrt(mz**4 / 4 - (alpha * math.pi * mz**2) / (gf * math.sqrt(2)))
    )
    points = [
        _forward_point([0.0, 4.7, 173.0, mw], 10.0**-k, sign)
        for k in (12, 15)
        for sign in (1, -1)
    ]
    scales = [8315.25] * len(points)
    served = runtime.evaluate(points, mu_r2=scales)
    assert all(d.status in ("success", "rescued") for d in served.diagnostics)
    wide = Runtime.load(tmp_path / "art", lane_rescue=False).evaluate(
        points,
        mu_r2=scales,
        arithmetic="arbitrary",
        precision=50,
        kinematics_improvement="off",
    )
    values, reference = _flat(served), _flat(wide)
    worst = max(
        float(abs(a - b) / abs(b)) for a, b in zip(values, reference, strict=True) if b
    )
    assert worst < 1e-12, worst


# Extreme tilts: a transverse momentum far below the binary64 range of pT²
# (1e-156 of the scale made the binary64 Weyl root's reciprocal infinite and
# a tree value NaN), the smallest values and exactly zero. Every carrier takes
# the on-axis branch at or below 2^-500 of the leg's scale (the previous
# release found the cancelling sum exactly zero there) and the general one
# above it; across the switch the spinor is continuous up to its phase.
TILT = Decimal(2) ** -500
TILTS = (Decimal("1e-140"), Decimal("1e-156"), Decimal("1e-300"), Decimal("1e-400"))


def _projector(wave) -> list[list[complex]]:
    u = [complex(re, im) for re, im in wave]
    return [[a * b.conjugate() for b in u] for a in u]


@pytest.mark.parametrize("mass", ["0", "4.7", "173"])
def test_exact_sources_at_extreme_tilts(mass: str) -> None:
    with localcontext() as context:
        context.prec = 40
        m, q = Decimal(mass), Decimal(485)
        energy = (q * q + m * m).sqrt()
        for axis in (-1, 1):
            for sign in (-1, 1):

                def momentum(tilt, axis=axis, sign=sign):
                    pt = q * tilt
                    return (
                        sign * energy,
                        sign * pt * Decimal("0.6"),
                        sign * pt * Decimal("0.8"),
                        sign * axis * q,
                    )

                for helicity in (-1, 1):
                    for source in (_quark_dirac, _antiquark_dirac):
                        on_axis = source(momentum(Decimal(0)), helicity, m)
                        for tilt in (*TILTS, Decimal(0)):
                            wave = source(momentum(tilt), helicity, m)
                            error = abs(_norm(wave) / (2 * energy) - 1)
                            assert error < Decimal("1e-35"), (tilt, axis, sign, error)
                            # The switch acts where the light-cone sum
                            # cancels: the -z side (its signed pz < 0).
                            if axis == -1 and tilt < TILT:
                                assert wave == on_axis, (tilt, axis, sign)
                        above = _projector(
                            source(momentum(TILT * Decimal("1.000001")), helicity, m)
                        )
                        below = _projector(
                            source(momentum(TILT * Decimal("0.999999")), helicity, m)
                        )
                        worst = max(
                            abs(a - b)
                            for ra, rb in zip(above, below, strict=True)
                            for a, b in zip(ra, rb, strict=True)
                        )
                        assert worst <= 1e-14 * 2 * float(energy), (axis, sign, worst)


def _tilted_point(masses: list[float], tilt: float, sign: int) -> list:
    sqrt_s = 1000.0
    m1, m2, m3, m4 = masses
    s = sqrt_s**2
    beam = math.sqrt((s - (m1 + m2) ** 2) * (s - (m1 - m2) ** 2)) / (2 * sqrt_s)
    q = math.sqrt((s - (m3 + m4) ** 2) * (s - (m3 - m4) ** 2)) / (2 * sqrt_s)
    p3 = [math.hypot(q, m3), q * tilt * 0.6, q * tilt * 0.8, sign * q]
    return [
        [math.hypot(beam, m1), 0.0, 0.0, beam],
        [math.hypot(beam, m2), 0.0, 0.0, -beam],
        p3,
        [math.hypot(q, m4), -p3[1], -p3[2], -p3[3]],
    ]


@pytest.mark.parametrize("lane", (*LANES, "on-the-fly"))
@pytest.mark.parametrize("process", ["u u~ > t t~", "e+ e- > u u~"])
def test_binary64_final_state_at_extreme_tilts(
    process: str, lane: str, tmp_path: Path
) -> None:
    """Finite, equal to the exact runtime at 100 digits on the same points and
    to the value exactly on the axis."""

    from pyamplicol.models import BuiltinSMModel

    Generator(_config(lane)).generate(
        [process], tmp_path / "artifact", model=ModelSource.built_in_sm()
    )
    runtime = Runtime.load(tmp_path / "artifact")
    sm = BuiltinSMModel()
    masses = [sm.mass(leg.pdg_id) for leg in runtime.physics.external_particles]
    tilts = (1e-140, 1e-156, 1e-300, 5e-324, 0.0)
    for sign in (1, -1):
        points = [_tilted_point(masses, tilt, sign) for tilt in tilts]
        binary64 = [complex(value).real for value in runtime.evaluate(points)]
        assert all(math.isfinite(value) and value > 0 for value in binary64)
        on_axis = binary64[-1]
        assert max(abs(v / on_axis - 1) for v in binary64) < 1e-13
        if lane != "on-the-fly":
            wide = runtime.evaluate(
                points, precision=REFERENCE_PRECISION, kinematics_improvement="off"
            )
            assert _relative([repr(x) for x in binary64], wide) < 1e-13
