# SPDX-License-Identifier: 0BSD
"""Flat phase-space points for ``evaluate`` and ``profile`` without a
momenta file (``[evaluation.phase_space]``).

The points are flat in phase space (``generation.phase_space.
flat_final_state``, the product's flat generator: RAMBO on diet, arXiv:
1308.2922; a massive final state's weight is not applied): a 2 -> n
scattering in its centre-of-mass frame with the beams along +-z, a 1 -> n
decay in the rest frame of the decaying particle, a 2 -> 1 process at its
single point. Point i is drawn from seed + i, so a point does not depend on
how many are drawn. Cuts (``generation.phase_space_cuts``) reject attempts of a point,
so a point still depends on its own seed alone.

Except for which legs the cuts act on (the artifact's model record), nothing
is read from the model: the external masses are those the artifact's own
validation record states (``processes/<id>/validation-momenta.json``,
``"masses"``: the masses the amplitude binds, ``generation.validation.
bound_external_masses``, which a loop artifact records). A record without
them (a tree artifact, whose amplitudes bind the model's masses, the
validation point's) gives the masses of its point, m^2 = E^2 - |p|^2 in
exact decimal arithmetic on its stored digits; a square below the rounding
of the stored binary64 components (64 epsilon E^2) is a massless leg. The
default energy follows the generation's convention on those masses
(``generation.validation.default_sqrt_s``; a decay at rest, a 2 -> 1
process at its final mass), so it is above threshold.
"""

from __future__ import annotations

import functools
import json
import math
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext
from pathlib import Path
from typing import TYPE_CHECKING

from pyamplicol.config import ConfigurationError

if TYPE_CHECKING:
    from pyamplicol.generation.phase_space import FlatFinalState
    from pyamplicol.generation.phase_space_cuts import PhaseSpaceCuts

# The stored components are binary64 values: a squared mass below this many
# roundings of E^2 is a massless leg.
_MASSLESS_ROUNDINGS = 64


@dataclass(frozen=True, slots=True)
class FlatPoints:
    """``points`` (per point the four-momenta of the legs, in the artifact's
    leg order), drawn at ``sqrt_s`` from ``seed`` with ``masses``."""

    points: tuple[tuple[tuple[float, float, float, float], ...], ...]
    sqrt_s: float
    seed: int
    masses: tuple[float, ...]
    initial: int
    process_id: str
    cut_legs: tuple[int, ...] = ()

    def as_inputs(self, *, exact: bool) -> list[list[list[object]]]:
        """The points as evaluation inputs: decimal numbers (exact, a loop
        runtime's inputs) or floats."""

        convert = (lambda x: Decimal(repr(x))) if exact else float
        return [
            [[convert(component) for component in momentum] for momentum in point]
            for point in self.points
        ]

    def mu_r2(self) -> list[str]:
        """Per point the squared invariant mass of its initial state: the
        default renormalisation scale (as ``profile`` and ``check``)."""

        return [repr(self.sqrt_s * self.sqrt_s) for _ in self.points]


def _process_id(artifact: Path, process: str | None) -> str:
    try:
        manifest = json.loads((artifact / "artifact.json").read_text())
    except (OSError, ValueError) as exc:
        raise ConfigurationError(f"cannot read the artifact {artifact}: {exc}") from exc
    ids = [str(entry["id"]) for entry in manifest.get("processes", ())]
    if process is None:
        default = manifest.get("default_process_id")
        if default is not None:
            return str(default)
        if len(ids) == 1:
            return ids[0]
        raise ConfigurationError(
            f"the artifact {artifact} holds several processes ({', '.join(ids)}); "
            "select one with evaluation.process (--process) for its flat points"
        )
    for entry in manifest.get("processes", ()):
        if process == entry["id"] or process in entry.get("aliases", ()):
            return str(entry["id"])
    return process


def _validation_record(artifact: Path, process_id: str) -> dict:
    path = artifact / "processes" / process_id / "validation-momenta.json"
    try:
        record = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ConfigurationError(
            f"no momenta file was given and the artifact has no readable "
            f"validation point to take the external masses from ({path}: {exc}); "
            "give evaluation.momenta (--momenta)"
        ) from exc
    if not record.get("available") or not record.get("points"):
        raise ConfigurationError(
            f"no momenta file was given and the artifact's validation point is "
            f"unavailable ({record.get('error')}); give evaluation.momenta"
        )
    return record


def _validation_point(record: dict) -> list[tuple[Decimal, ...]]:
    return [
        tuple(Decimal(str(value)) for value in entry["momentum"])
        for entry in record["points"][0]
    ]


def _recorded_masses(
    record: dict,
    validation: list[tuple[Decimal, ...]],
    artifact: Path,
    process_id: str,
) -> tuple[float, ...]:
    """The legs' masses: the record's bound masses (``"masses"``), else, for
    a tree process (whose amplitude binds the model's masses, those its
    point was drawn on), its point's (``_mass``). A loop process's record
    without bound masses was written before them (pyAmpliCol 1.0.3 and
    older), on the model's masses even where ``[loop.preparation]
    fixed_parameters`` changed one: the drawer cannot tell, and refuses."""

    stored = record.get("masses")
    if stored is None:
        if _is_loop_process(artifact, process_id):
            raise ConfigurationError(
                f"the validation record of {process_id!r} states no bound masses "
                "(generated by pyAmpliCol 1.0.3 or older, whose loop kinematics "
                "ignored [loop.preparation] fixed_parameters): flat points are "
                "not drawn on its masses; regenerate the artifact, or give "
                "evaluation.momenta (--momenta)"
            )
        return tuple(_mass(momentum) for momentum in validation)
    if len(stored) != len(validation):
        raise ConfigurationError(
            "the artifact's validation record states "
            f"{len(stored)} masses for {len(validation)} legs"
        )
    return tuple(float(value) for value in stored)


def _is_loop_process(artifact: Path, process_id: str) -> bool:
    """Whether the stored process is a one-loop one (its execution record's
    kind)."""

    path = artifact / "processes" / process_id / "execution.json"
    try:
        kind = json.loads(path.read_text()).get("kind")
    except (OSError, ValueError):
        return False
    return kind == "pyamplicol-runtime-loop-execution"


@dataclass(frozen=True, slots=True)
class FlatBinding:
    """The masses a loaded runtime binds for the flat points of its process
    (``runtime_binding``): the stored process's id, the mass of each of its
    legs in the stored (representative) order, and the caller's leg map
    (caller leg i is stored leg ``legs[i]``; None: the stored order)."""

    process_id: str
    masses: tuple[float, ...]
    legs: tuple[int, ...] | None = None


def runtime_binding(runtime: object) -> FlatBinding | None:
    """The flat points' binding of a loaded runtime (``Runtime.load``, with
    the caller's model parameters applied): a one-loop runtime's bound masses
    at its current parameters (``V2VirtualRuntime._bound_leg_masses``, the
    shared evaluator) and its leg map; a tree runtime's the masses its
    evaluation binds at the stored point (``_tree_kinematics_masses``).
    None: a runtime without such a binding (the validation record decides).
    A one-loop external mass that runs with the renormalisation scale is
    refused (its shell is not known before the points' scales)."""

    from pyamplicol.loops.v2.assemble import Precision, RunningExternalMass

    backend = getattr(runtime, "_backend", runtime)
    bound = getattr(backend, "_bound_leg_masses", None)
    if callable(bound):
        try:
            squares = bound(
                Precision.double(), dict(backend._parameters), None, caller=False
            )
        except RunningExternalMass as error:
            raise ConfigurationError(
                f"no flat points: {error}; give evaluation.momenta (--momenta)"
            ) from error
        if any(square is None for square in squares):
            raise ConfigurationError(
                "no flat points: an external mass of the process cannot be "
                "bound before evaluation; give evaluation.momenta (--momenta)"
            )
        member = backend._member
        return FlatBinding(
            str(backend._process_id),
            tuple(_root(square) for square in squares),
            None if member is None else tuple(member.legs),
        )
    tree = getattr(backend, "_tree_kinematics_masses", None)
    loader = getattr(backend, "validation_momenta", None)
    if not callable(tree) or not callable(loader):
        return None
    stored = loader()
    if not stored:
        return None
    squares, _initial = tree([[str(x) for x in leg] for leg in stored[0]], 16)
    if any(square is None for square in squares):
        return None
    physics = getattr(runtime, "physics", None)
    process_id = getattr(physics, "process_id", None)
    if process_id is None:
        return None
    return FlatBinding(str(process_id), tuple(_root(square) for square in squares))


def _root(square: object) -> float:
    """The binary64 root of an exact squared mass, rounded once."""

    from fractions import Fraction

    value = Fraction(square)  # type: ignore[arg-type]
    with localcontext() as context:
        context.prec = 60
        return float((Decimal(value.numerator) / Decimal(value.denominator)).sqrt())


def _mass(momentum: tuple[Decimal, ...]) -> float:
    with localcontext() as context:
        context.prec = 60
        energy, px, py, pz = momentum
        square = energy * energy - px * px - py * py - pz * pz
        rounding = _MASSLESS_ROUNDINGS * Decimal(sys.float_info.epsilon) * energy**2
        if abs(square) <= rounding:
            return 0.0
        if square < 0:
            raise ConfigurationError(
                "the artifact's validation point has a spacelike external leg"
            )
        return float(square.sqrt())


def _initial_count(artifact: Path, process_id: str, legs: int) -> int:
    physics = artifact / "processes" / process_id / "physics.json"
    try:
        record = json.loads(physics.read_text())
        states = record.get("state_legs") or record.get("metadata", {}).get(
            "state_legs"
        )
        if states:
            return sum(1 for state in states if str(state).startswith("in"))
    except (OSError, ValueError):
        pass
    # The validation point's leg order: initial legs first; their energies
    # sum to the final ones'.
    raise ConfigurationError(
        f"cannot read the initial legs of {process_id!r} from {physics}; "
        f"give evaluation.momenta ({legs} legs per point)"
    )


def draw_flat_points(
    artifact: Path,
    *,
    process: str | None,
    points: int,
    seed: int,
    sqrt_s: float | None,
    cuts: PhaseSpaceCuts | None = None,
    binding: FlatBinding | None = None,
) -> FlatPoints:
    """``points`` flat phase-space points of the artifact's process
    (``process``: an id or alias, None the default process) from ``seed``
    at ``sqrt_s`` (None: the generation's default energy at the masses
    drawn on; a decay or a 2 -> 1 process takes its (bound) mass and refuses
    another value), within ``cuts``
    (``generation.phase_space_cuts``; None: none). The external masses (of
    the points, the thresholds and the cuts' massless-leg test) are
    ``binding``'s (``runtime_binding``: those the loaded runtime binds, its
    caller parameters included, and its leg map), else the validation
    record's (``_recorded_masses``: a loop record's bound masses, a tree
    record's point; a loop record without them, generated before the bound
    masses, is refused)."""

    from pyamplicol.generation.phase_space import flat_final_states
    from pyamplicol.generation.phase_space_cuts import CutsError, draw_accepted

    process_id = (
        _process_id(artifact, process) if binding is None else binding.process_id
    )
    record = _validation_record(artifact, process_id)
    validation = _validation_point(record)
    if binding is None:
        masses = _recorded_masses(record, validation, artifact, process_id)
    else:
        masses = tuple(binding.masses)
        if len(masses) != len(validation):
            raise ConfigurationError(
                f"the runtime binds {len(masses)} masses for the "
                f"{len(validation)} legs of {process_id!r}"
            )
    from pyamplicol.generation.validation import default_sqrt_s

    initial = _initial_count_from_point(artifact, process_id, validation)
    final = len(validation) - initial
    fixed_energy = initial == 1 or final == 1
    if sqrt_s is None:
        # The defaults of the generation's convention on THESE masses (the
        # bound ones; never the stored point's energy): a decay at rest, a
        # 2 -> 1 process at its final mass, a 2 -> n scattering at
        # ``validation.default_sqrt_s``.
        energy = (
            masses[0]
            if initial == 1
            else masses[-1]
            if final == 1
            else default_sqrt_s(masses[:initial], masses[initial:])
        )
    elif fixed_energy:
        expected = masses[0] if initial == 1 else masses[-1]
        if not math.isclose(sqrt_s, expected, rel_tol=1e-12):
            raise ConfigurationError(
                f"evaluation.phase_space.sqrt_s = {sqrt_s} for {process_id!r}, "
                f"whose energy is fixed by its masses ({expected}); remove it"
            )
        energy = expected
    else:
        energy = float(sqrt_s)
    if initial == 2 and energy <= masses[0] + masses[1]:
        raise ConfigurationError(
            f"evaluation.phase_space.sqrt_s = {energy} is below the threshold "
            f"of the initial state ({masses[0]} + {masses[1]})"
        )
    if final > 1 and energy <= sum(masses[initial:]):
        raise ConfigurationError(
            f"evaluation.phase_space.sqrt_s = {energy} is below the threshold "
            f"of the final state (sum of masses {sum(masses[initial:])})"
        )
    seeds = [seed + index for index in range(points)]
    cut_legs: tuple[int, ...] = ()
    if cuts is not None and cuts.active:
        if initial == 1:
            raise ConfigurationError(
                "evaluation.phase_space.pt_min / delta_r_min need the beams of "
                f"a scattering; {process_id!r} is a decay"
            )
        # Indices into the final state, as ``flat_final_states`` orders it.
        cut_legs = _cut_legs(artifact, process_id, masses[initial:])

    def draw(attempt_seeds: list[int]) -> list[FlatFinalState]:
        return flat_final_states(masses[initial:], sqrt_s=energy, seeds=attempt_seeds)

    finals: Sequence[FlatFinalState]
    if final <= 1:
        finals = ()
    elif cuts is not None and cut_legs:
        try:
            cuts.require_possible(len(cut_legs), energy)
            finals = draw_accepted(
                seeds, draw, lambda state: state.momenta, cuts, cut_legs
            )
        except CutsError as error:
            raise ConfigurationError(str(error)) from error
    else:
        finals = draw(seeds)
    drawn = []
    for index in range(points):
        if initial == 1:
            legs = [(energy, 0.0, 0.0, 0.0)]
        else:
            m1, m2 = masses[0], masses[1]
            e1 = (energy * energy + m1 * m1 - m2 * m2) / (2.0 * energy)
            e2 = energy - e1
            momentum = math.sqrt(max(0.0, e1 * e1 - m1 * m1))
            legs = [(e1, 0.0, 0.0, momentum), (e2, 0.0, 0.0, -momentum)]
        if final == 1:
            legs.append((energy, 0.0, 0.0, 0.0))
        else:
            legs.extend(finals[index].momenta)
        drawn.append(tuple(tuple(float(x) for x in leg) for leg in legs))
    cut_positions = tuple(initial + leg for leg in cut_legs)
    if binding is not None and binding.legs is not None:
        # The stored (representative) order drawn, the caller's returned:
        # caller leg i is stored leg legs[i] (a permuted selector, an alias,
        # a process-group member; within each side).
        order = tuple(binding.legs)
        if sorted(order) != list(range(len(masses))) or sorted(order[:initial]) != list(
            range(initial)
        ):
            raise ConfigurationError(
                f"the runtime's leg map {list(order)} is no permutation within "
                f"each side of {process_id!r}"
            )
        drawn = [tuple(point[leg] for leg in order) for point in drawn]
        masses = tuple(masses[leg] for leg in order)
        cut_positions = tuple(
            sorted(order.index(position) for position in cut_positions)
        )
    return FlatPoints(
        tuple(drawn),
        float(energy),
        int(seed),
        masses,
        initial,
        process_id,
        cut_positions,
    )


def _cut_legs(
    artifact: Path, process_id: str, masses: Sequence[float]
) -> tuple[int, ...]:
    """The final-state legs the cuts act on (``phase_space_cuts``): the
    massless ones (``masses``, the validation point's) whose particle (the
    artifact's own model record) is a parton, photon or charged lepton."""

    path = artifact / "processes" / process_id / "validation-momenta.json"
    record = json.loads(path.read_text())
    pdgs = [int(entry["pdg"]) for entry in record["points"][0]][-len(masses) :]
    model = artifact / "model" / "compiled-model.json"
    try:
        particles = _model_particles(str(model), model.stat().st_mtime_ns)
        return tuple(
            leg
            for leg, (pdg, mass) in enumerate(zip(pdgs, masses, strict=True))
            if mass == 0.0 and particles[pdg]
        )
    except (OSError, ValueError, KeyError) as error:
        raise ConfigurationError(
            f"cannot read the final-state particles of {process_id!r} from {model} "
            f"({error!r}) for the phase-space cuts"
        ) from error


@functools.lru_cache(maxsize=4)
def _model_particles(model: str, _mtime: int) -> dict[int, bool]:
    """Per PDG code of the artifact's model: whether the cuts act on it."""

    from pyamplicol.generation.phase_space_cuts import is_cut_particle

    record = json.loads(Path(model).read_text())
    return {
        int(entry["pdg_code"]): is_cut_particle(
            spin=int(entry["spin"]),
            color=int(entry["color"]),
            charge=float(entry["charge"] or 0.0),
        )
        for entry in record["ir"]["particles"]
    }


def _initial_count_from_point(
    artifact: Path, process_id: str, validation: list[tuple[Decimal, ...]]
) -> int:
    """The number of initial legs (1 or 2): from the artifact's manifest
    (the process expression's arrow), else the physics record."""

    try:
        manifest = json.loads((artifact / "artifact.json").read_text())
        for entry in manifest.get("processes", ()):
            if str(entry["id"]) == process_id:
                expression = str(entry["expression"])
                if ">" in expression:
                    return len(expression.split(">", 1)[0].split())
    except (OSError, ValueError, KeyError):
        pass
    return _initial_count(artifact, process_id, len(validation))


__all__ = ["FlatBinding", "FlatPoints", "draw_flat_points", "runtime_binding"]
