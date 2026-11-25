# SPDX-License-Identifier: 0BSD
"""Deterministic validation-point records for generated process artifacts."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from ..models.base import Model
from .dag_types import GenericDAG
from .phase_space import massive_rambo_final_state

if TYPE_CHECKING:
    from .contracts import CanonicalProcessIR

FourMomentum = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class ValidationPointRecord:
    process_id: str
    process: str
    seed: int
    particles: tuple[tuple[int, FourMomentum], ...] = ()
    error: str | None = None
    # The bound mass of every leg (``bound_external_masses``), recorded for a
    # loop process (its amplitude binds them from the parameters it fixes,
    # which the model's own values need not be); None: not recorded.
    masses: tuple[float, ...] | None = None

    @property
    def available(self) -> bool:
        return self.error is None

    @property
    def four_vectors(self) -> tuple[FourMomentum, ...]:
        if not self.available:
            return ()
        return tuple(momentum for _pdg, momentum in self.particles)

    def to_mapping(self) -> dict[str, object]:
        points: list[object] = []
        if self.available:
            points.append(
                [
                    {
                        "pdg": pdg,
                        "momentum": [_decimal_string(value) for value in momentum],
                    }
                    for pdg, momentum in self.particles
                ]
            )
        return {
            "schema_version": 1,
            "kind": "pyamplicol-rusticol-validation-momenta",
            "process_id": self.process_id,
            "process": self.process,
            "seed": self.seed,
            "available": self.available,
            "error": self.error,
            "points": points,
            **(
                {"masses": [_decimal_string(mass) for mass in self.masses]}
                if self.masses is not None and self.available
                else {}
            ),
        }


def build_validation_point(
    dag: GenericDAG,
    model: Model,
    *,
    process_id: str,
    seed: int,
) -> ValidationPointRecord:
    return build_process_validation_point(
        dag.process,
        model,
        process_id=process_id,
        seed=seed,
    )


# The decimal digits at which a derived external mass is formed from the
# exact parameter texts (``loops.v2.assemble.bound_leg_masses``) before it is
# rounded, once, to the binary64 mass of the generated momenta: well beyond
# binary64, so that a cancelling definition (loop_sm's W mass from MZ,
# aEWM1 and Gf) does not lose the digits the momenta keep.
BOUND_MASS_DIGITS = 40


def bound_external_masses(
    process: CanonicalProcessIR,
    model: Model,
    fixed_parameters: Mapping[str, str] | None = None,
    *,
    scale_parameter: str | None = None,
) -> tuple[float, ...]:
    """The mass of every external leg of ``process`` (initial states first)
    that its amplitude binds. Without ``fixed_parameters`` (a tree request):
    the model's masses, bit for bit. With them (a loop request: the EFFECTIVE
    slice binding, the request's fixed parameters and those its model
    preparation adds, exact decimal texts): THE shared evaluator of the bound
    external masses, ``loops.v2.assemble.bound_leg_masses`` on the compiled
    model, the one the runtime's screen, its load check and the flat points
    use, from the exact texts at ``BOUND_MASS_DIGITS`` digits, rounded once
    to binary64 here. A mass that depends on the renormalisation scale
    (``scale_parameter``) is refused (``RunningExternalMass``): its shell is
    not known before the point's scale is. The one source of the external
    masses of the generated kinematics: the stored validation point, the
    momenta of ``pyamplicol check`` and of the loop-induced generation
    probes, and the masses of the flat phase-space points
    (``cli.flat_points`` reads them from the validation record)."""

    pdgs = (*process.initial_pdgs, *process.final_pdgs)
    if fixed_parameters is None:
        return tuple(_mass(model, int(pdg)) for pdg in pdgs)
    from decimal import Decimal, localcontext

    from pyamplicol.loops.v2.assemble import bound_leg_masses

    compiled = getattr(model, "compiled", None)
    if compiled is None:
        raise ValueError(
            "the bound masses of a loop request need its compiled model "
            f"({type(model).__name__} has none)"
        )
    squares = bound_leg_masses(
        compiled,
        [int(pdg) for pdg in pdgs],
        dict(fixed_parameters),
        BOUND_MASS_DIGITS,
        scale_parameter=scale_parameter,
    )
    out = []
    for pdg, square in zip(pdgs, squares, strict=True):
        if square is None:
            raise ValueError(f"particle {pdg} has no bound mass")
        with localcontext() as context:
            context.prec = BOUND_MASS_DIGITS + 10
            root = (Decimal(square.numerator) / Decimal(square.denominator)).sqrt()
        out.append(float(root))
    return tuple(out)


def build_process_validation_point(
    process: CanonicalProcessIR,
    model: Model,
    *,
    process_id: str,
    seed: int,
    sqrt_s: float | None = None,
    fixed_parameters: Mapping[str, str] | None = None,
    record_masses: bool = False,
    scale_parameter: str | None = None,
    masses: Sequence[float] | None = None,
) -> ValidationPointRecord:
    """Build validation momenta without requiring a materialized DAG, on
    shell at the masses the amplitude binds (``bound_external_masses`` at
    ``fixed_parameters``). ``sqrt_s`` replaces the centre-of-mass energy of
    a 2 -> n scattering (n >= 2) (None: the convention of
    ``_build_particles``). ``record_masses`` stores the bound masses in the
    record (a loop process's, ``ValidationPointRecord.masses``). ``masses``:
    the legs' masses as the amplitude's own binding gives them (a loop
    process's native binary64 binding, ``loop_service.
    _native_external_masses``), in place of ``bound_external_masses``."""

    try:
        if masses is None:
            masses = bound_external_masses(
                process, model, fixed_parameters, scale_parameter=scale_parameter
            )
        masses = tuple(float(mass) for mass in masses)
        particles = _build_particles(process, masses, seed=seed, sqrt_s=sqrt_s)
    except (ArithmeticError, KeyError, RuntimeError, ValueError) as exc:
        return ValidationPointRecord(
            process_id=process_id,
            process=process.process,
            seed=seed,
            error=str(exc),
        )
    return ValidationPointRecord(
        process_id=process_id,
        process=process.process,
        seed=seed,
        particles=particles,
        masses=masses if record_masses else None,
    )


def rotate_validation_point(
    point: ValidationPointRecord,
    *,
    rotation_seed: int,
) -> ValidationPointRecord:
    """Apply a deterministic proper rotation to one physical event."""

    if not point.available:
        return point
    digest = hashlib.sha256(
        f"{rotation_seed}:proper-spatial-rotation-v1".encode("ascii")
    ).digest()
    denominator = float(1 << 64)
    azimuth = 2.0 * math.pi * ((int.from_bytes(digest[:8], "big") + 0.5) / denominator)
    cosine_polar = (
        2.0 * ((int.from_bytes(digest[8:16], "big") + 0.5) / denominator) - 1.0
    )
    sine_polar = math.sqrt(max(0.0, 1.0 - cosine_polar * cosine_polar))
    cos_azimuth = math.cos(azimuth)
    sin_azimuth = math.sin(azimuth)
    # Rz(azimuth) Ry(polar), a proper orthogonal map taking +z to the
    # deterministic direction above.
    rotation = (
        (
            cos_azimuth * cosine_polar,
            -sin_azimuth,
            cos_azimuth * sine_polar,
        ),
        (
            sin_azimuth * cosine_polar,
            cos_azimuth,
            sin_azimuth * sine_polar,
        ),
        (-sine_polar, 0.0, cosine_polar),
    )

    def rotated(momentum: FourMomentum) -> FourMomentum:
        energy, x_component, y_component, z_component = momentum
        spatial = (x_component, y_component, z_component)
        return (
            energy,
            *tuple(
                sum(row[column] * spatial[column] for column in range(3))
                for row in rotation
            ),
        )

    return replace(
        point,
        particles=tuple((pdg, rotated(momentum)) for pdg, momentum in point.particles),
    )


def validation_point_map(
    records: tuple[ValidationPointRecord, ...],
) -> Mapping[str, Mapping[str, object]]:
    return {record.process_id: record.to_mapping() for record in records}


# Massive beams: sqrt(s) over the larger threshold (unit-free, well above
# both thresholds, beams far from the ultra-relativistic limit).
_MASSIVE_BEAM_SCALE = 2.0


def _build_particles(
    process: CanonicalProcessIR,
    masses: tuple[float, ...],
    *,
    seed: int,
    sqrt_s: float | None = None,
) -> tuple[tuple[int, FourMomentum], ...]:
    """One on-shell point of ``process`` at the legs' ``masses`` (initial
    states first, ``bound_external_masses``).

    A decay (1 -> n) is taken in the rest frame of the decaying particle; a
    scattering (2 -> n, n >= 2) in its centre-of-mass frame, beams along +-z.
    Massive beams take ``sqrt(s)`` twice the larger of the initial and the
    final threshold (a scale of the process, in no particular units); massless
    beams keep the historical ``sqrt(s) = max(1000, final threshold + 100)``
    exactly (their points are byte-identical). A 2 -> 1 scattering takes
    ``sqrt(s)`` = the final mass. A process has one or two initial particles
    (``processes.model.require_external_leg_counts``). A given ``sqrt_s``
    replaces the energy of a 2 -> n scattering (n >= 2) and must exceed both
    thresholds; a decay or a 2 -> 1 point has no free energy and refuses it.
    """

    initial_pdgs = tuple(int(pdg) for pdg in process.initial_pdgs)
    final_pdgs = tuple(int(pdg) for pdg in process.final_pdgs)
    if len(initial_pdgs) not in (1, 2):
        raise ValueError(
            "validation momenta require a one- or two-particle initial state"
        )
    if not final_pdgs:
        raise ValueError("validation momenta require at least one final-state particle")
    initial_masses = masses[: len(initial_pdgs)]
    final_masses = masses[len(initial_pdgs) :]
    threshold = sum(final_masses)
    if sqrt_s is not None and (len(initial_pdgs) == 1 or len(final_pdgs) == 1):
        raise ValueError(
            "a validation energy applies to 2 -> n scatterings with n >= 2 (a "
            "decay or a 2 -> 1 point has no free energy)"
        )
    if len(initial_pdgs) == 1:
        (mass,) = initial_masses
        if len(final_pdgs) < 2 or not mass > threshold:
            raise ValueError(
                f"no validation point: a decay of mass {mass!r} into "
                f"{len(final_pdgs)} particle(s) of total mass {threshold!r}"
            )
        final_momenta = massive_rambo_final_state(
            len(final_pdgs), sqrt_s=mass, masses=final_masses, seed=seed
        )
        particles = (
            (initial_pdgs[0], (mass, 0.0, 0.0, 0.0)),
            *tuple(zip(final_pdgs, final_momenta, strict=True)),
        )
        return _finite(particles)
    beams = sum(initial_masses)
    if len(final_pdgs) == 1:
        if threshold <= 0.0:
            raise ValueError(
                "no finite center-of-mass point exists for one massless final state"
            )
        if beams > 0.0 and not threshold > beams:
            raise ValueError(
                f"no validation point: beams of total mass {beams!r} above the "
                f"final-state mass {threshold!r}"
            )
        sqrt_s = threshold
        final_momenta: tuple[FourMomentum, ...] = ((float(sqrt_s), 0.0, 0.0, 0.0),)
    else:
        if sqrt_s is None:
            sqrt_s = default_sqrt_s(initial_masses, final_masses)
        elif not (math.isfinite(sqrt_s) and sqrt_s > max(threshold, beams)):
            raise ValueError(
                f"no validation point at sqrt(s) = {sqrt_s!r}: it must exceed the "
                f"final-state threshold {threshold!r} and the beams' total mass "
                f"{beams!r}"
            )
        final_momenta = massive_rambo_final_state(
            len(final_pdgs),
            sqrt_s=sqrt_s,
            masses=final_masses,
            seed=seed,
        )
    if beams == 0.0:
        beam_energy = 0.5 * sqrt_s
        incoming = (
            (beam_energy, 0.0, 0.0, beam_energy),
            (beam_energy, 0.0, 0.0, -beam_energy),
        )
    else:
        incoming = _massive_beams(sqrt_s, *initial_masses)
    particles = (
        *tuple(zip(initial_pdgs, incoming, strict=True)),
        *tuple(zip(final_pdgs, final_momenta, strict=True)),
    )
    return _finite(particles)


def default_sqrt_s(
    initial_masses: Sequence[float], final_masses: Sequence[float]
) -> float:
    """The default energy of a 2 -> n scattering (n >= 2) at these masses
    (``_build_particles``' convention, also the flat points' default):
    massless beams ``max(1000, final threshold + 100)``, massive beams twice
    the larger of the initial and the final threshold."""

    threshold = sum(final_masses)
    beams = sum(initial_masses)
    if beams == 0.0:
        return max(1000.0, threshold + 100.0)
    return _MASSIVE_BEAM_SCALE * max(threshold, beams)


def _massive_beams(
    sqrt_s: float, first: float, second: float
) -> tuple[FourMomentum, FourMomentum]:
    """Beams of masses ``first`` and ``second`` along +-z in their
    centre-of-mass frame: E_i = (s + m_i^2 - m_j^2) / (2 sqrt(s)), |p_z| =
    lambda(s, m_1^2, m_2^2)^(1/2) / (2 sqrt(s))."""

    s = sqrt_s * sqrt_s
    a, b = first * first, second * second
    # lambda = (s - (m1 + m2)^2) (s - (m1 - m2)^2), cancellation-free.
    lam = (s - (first + second) ** 2) * (s - (first - second) ** 2)
    momentum = math.sqrt(lam) / (2.0 * sqrt_s)
    return (
        ((s + a - b) / (2.0 * sqrt_s), 0.0, 0.0, momentum),
        ((s + b - a) / (2.0 * sqrt_s), 0.0, 0.0, -momentum),
    )


def _finite(
    particles: tuple[tuple[int, FourMomentum], ...],
) -> tuple[tuple[int, FourMomentum], ...]:
    if not all(math.isfinite(value) for _, momentum in particles for value in momentum):
        raise ArithmeticError("validation momenta contain non-finite components")
    return particles


def _mass(model: Model, pdg: int) -> float:
    value = float(model.mass(pdg))
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"particle {pdg} has invalid mass {value!r}")
    return value


def _decimal_string(value: float) -> str:
    return format(float(value), ".17g")


__all__ = [
    "BOUND_MASS_DIGITS",
    "ValidationPointRecord",
    "bound_external_masses",
    "build_process_validation_point",
    "build_validation_point",
    "default_sqrt_s",
    "rotate_validation_point",
    "validation_point_map",
]
