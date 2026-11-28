# SPDX-License-Identifier: 0BSD
"""Ward identities at any multiplicity on the native per-point input path
(M-QCD MQ-WARD; REQUIREMENTS_ADDENDUM H; design §8.4, oracle O10).

The check replaces one external gluon's polarisation vector by its momentum
on the *loop side* of the Born-virtual interference (the asymmetric Ward
mode of ``observables``): the blocks the loop dresses, the counterterm
currents and the external-field insertions' Born amplitude read
epsilon_j -> c p_j; the Born bra keeps physical polarisations. For a
gauge-invariant amplitude the renormalised interference (bare + UV + R2)
vanishes per Laurent coefficient and squared-order sector as a complex
number; an inclusive output projects it to its real part, so c = 1 and
c = i together check all of it (``WARD_FACTORS``). The Born interference of
the physical bra with the substituted Born amplitude
(``PointResult.loop_born``) vanishes with the tree Ward identity. The parts
need not vanish on their own: the R2 part cancels a bare violation of its
own size (c = i on u u~ > g g g, O10), and with massive quarks the local UV
part holds the mass counterterm, whose insertion is not gauge invariant
without the bare self-energies (g g > t t~ g g, leg 1, epsilon_1 -> i p_1:
40 times the physical scale, the virtual 1.4e-24 of it in double-double).

* **Native inputs.** ``plan_export.NativeExecutor(..., inputs="native")
  .evaluate(..., ward=...)`` hands each point's loop-side vector to the
  native trees (``rusticol-core`` ``loop_v2::trees::TreeProgram::
  inputs_loop_side``): the tree program runs twice per point, physically for
  the Born bra and with the vector in the leg's source slots (every
  helicity source of the leg, times its crossing phase) for the block rows,
  the counterterm program and the field insertions' Born ket; nothing is
  formed in Python per point, so the check runs at any multiplicity the
  native lane evaluates (g g > g g g g g included).
* **Python oracle.** The same call on ``inputs="python"`` forms the inputs in
  the Python reference lane (``assemble._PointEvaluation(loop_sources=...)``,
  ``TreeRows`` in Decimal), which the native one must reproduce; the native
  executor dresses and reduces both.
* **Kernels.** The transverse Yang-Mills kernels drop terms proportional to
  an input current's p.J, exact only for conserved currents, so a Ward slice
  is generated on the model's full tree kernels (``ward_slice``;
  ``blocks.KERNEL_VARIANT_BY_BLOCK_CLASS["ward"]``); the executor refuses
  the Ward mode on a slice with other kernels (``require_full_kernels``),
  and on a stored process, whose record does not carry its kernel variant.

A Ward value is the leg j (c = 1), a (leg, c) pair with c a complex number
(a number, a decimal string or a (real, imaginary) pair) or a (leg, vector)
pair with a literal complex four-vector, the non-gauge control in which
nothing vanishes (``observables._ward``). ``gauge_ward`` gives the check's
vectors, c p_j / p_j^0: of the size of a polarisation vector, so that the
substituted amplitudes are measured against the physical ones on equal
footing (c p_j alone scales them by the leg's energy).

``ward_check`` runs the check of one point and carrier in one batch (the
physical entry and every leg and factor) and judges each row.

**The criterion** (``ward_row``), per point, leg and factor, against the
physical evaluation at the same point; the scale of a Laurent coefficient is
the largest physical component magnitude over the sectors
(``ward_scales``):

* Born: |sum of ``loop_born``| <= ``BORN_BOUNDS`` x |physical Born|
  (binary64 1e-12, double-double 1e-24: the O1 rule's binary64 tolerance and
  its double-double agreement);
* virtual, every sector and Laurent coefficient: in double-double
  |V_k| <= 1e-25 x scale_k (O10's double-double bound); in binary64, where
  the reduction's rounding grows with the multiplicity, the user's O1 rule
  (m-qcd PLAN §1.4 rules 2 and 3) with the exact value 0 and the scale in
  place of the coefficient: E_k, the absolute stability estimate of the
  Ward evaluation itself from the reduction-direction check
  (``REDUCTION``), is within O1's binary64 scope, E_k <= 1e-9 x scale_k;
  |V_k| <= max(1e-12 x scale_k, E_k) (rule 2, ``BINARY64_FLOOR``); and
  |V_k| <= 10 max(E_k, F_k) (rule 3, the 10x rule), with F_k = n u x
  scale_k the binary64 resolution of the checked quantity: the standard
  bound of a sum of the evaluation's n reduction lanes, formed from binary64
  inputs of at most the physical scale, at the unit roundoff u = 2^-53
  (``RESOLUTION_UNITS``). The direction check compares two reductions of the
  SAME binary64 numerator coefficients, so it never sees their rounding;
  where NinjaRS's cancellation rescue re-reduces the vanishing Ward lanes in
  double-double in both frames, E_k falls to ~1e-30 x scale_k while the
  residue keeps the inputs' ~1e-16 to 3e-15 x scale_k, as before the rescue
  (g g > g g); below F_k the estimate is not read. With a negligible
  estimate the binary64 tolerance is therefore min(1e-12, 10 n 2^-53) x
  scale_k. Double-double keeps its rule 3 as before, |V_k| <= 10 E_k without
  a floor (its residues stay within its estimate: no rescue re-reduces a
  double-double lane at a higher carrier in both frames). A gauge violation
  does not depend on the reduction frame, so the estimate does not cover it.
  LANES SERVED WITHOUT ACCURACY EVIDENCE (``PointResult.uncertified_bound``,
  ``judged``): such a lane (one that vanishes within the resolution of its
  own terms) carries no relative accuracy, and two frames can agree on the
  same wrong value, so neither the residue nor the estimate covers its
  error; its reducer-stated absolute bound, propagated to the component
  with the lane's contraction weight, is. Per sector and coefficient, with
  B_k the sum of those bounds and A_k the criterion's bound on |V_k| above:
  |V_k| + B_k <= A_k passes, |V_k| - B_k > A_k fails, anything between, or
  an infinite B_k, is INCONCLUSIVE (``passed`` None with the reason in
  ``inconclusive``: never a pass). The physical scale has the interval its
  own uncertified lanes' bound U_k gives it, [scale_k - U_k, scale_k + U_k]
  (A_k grows with the scale): the row passes only if it passes at the
  interval's lower end, fails only if it fails at its upper end, and is
  inconclusive otherwise. Bounds are taken only where credible (finite,
  normal, positive; never from the generic engine's ladder records,
  ``plan_export.uncertified_bound``). A real gauge violation therefore
  cannot pass: a pass needs |V_k| + B_k <= A_k <= max(1e-12 scale_k, E_k)
  for every scale the physical point allows, and the served residue
  differs from the true one by at most B_k (the uncertified lanes) plus the
  certified lanes' rounding that E_k and F_k estimate; two matching wrong
  zeros carry the bound of their own terms (2^300 for the reviewer's
  bubble with k = 400), which makes the row inconclusive, while a symmetry
  zero's bound is of order its terms' rounding. A
  rotation check is no rounding estimate here: the substituted leg's bra
  sums over its helicities against a helicity-independent ket, so each
  reduction lane changes by the helicities' little-group phases under a
  rotation and only the vanishing sum is invariant (g g > t t~ g g, leg 1:
  per-lane rotation budget 1.6 times the physical scale, the virtual
  2e-12 of it before and after the rotation). An evaluation without the
  reduction check has no binary64 criterion (``passed`` None).

**Vanishing coefficients** (``scale_floor``): a Laurent coefficient that
vanishes physically (the double pole of a QED correction with massive
emitters) has a physical scale of the size of its own rounding. Every
coefficient's scale is therefore at least |physical Born| x alpha / (2 pi)
(alpha = ``SCALE_FLOOR_COUPLING``, the fine-structure constant: the weakest
coupling of a shipped correction), so that rounding over a rounding-size
scale is not judged as a violation (``row["scale_floor"]`` marks the
coefficients it set).

**Unstable external legs** (``unstable_external_legs``,
``stabilised_parameters``). In the real on-shell mass scheme (zero widths)
an external particle that can decay at its own mass keeps the absorptive
part of its self-energy: the mass counterterm renormalises Re Sigma only, so
i Im Sigma(m^2) stays on the external leg, which is then not at the
(complex) pole of its propagator. The Ward identity of the renormalised
amplitude fails by a term of relative size about Gamma / m in the
absorptive part of the amplitude, while the dispersive part and the
interference a run serves are unaffected (g g > t t~ [QED] with MT > MW +
MB: the c = 1 finite part 8.6e-3 of the physical scale, zero below the
t -> W b threshold; MadLoop, Recola and OpenLoops agree with the served
values). The legs this affects are those charged under the substituted
boson: coloured legs for a gluon leg, electrically charged legs for a
photon leg. A leg is unstable when it is massive, its width is zero at the
check's parameters and a tree-level two-body channel of the model's
three-point vertices (ghosts excluded) that carries a coupling order of a
requested correction (a cut of the leg's one-loop self-energy) is open:
m > m_a + m_b at the evaluated masses. The rows cannot separate the absorptive from the
dispersive part (the substituted leg's helicity sum is i sqrt(2) times a
real transverse vector, so the c = 1 row holds the absorptive part only
for parity-even terms), so with an unstable leg ``ward_check``:

* judges the rows at the requested parameters as before, except that a row
  whose virtual fails becomes inconclusive (``passed`` None) with the
  reason (``row["unstable"]``: the leg, its open channel and the remedy);
  a passing row stays a pass, a Born failure stays a failure;
* evaluates the same rows again on a STABILISED spectrum and judges them
  normally (``check["stabilised"]``): every runtime mass input of a
  massive vector boson scaled by one common factor (so the weak mixing
  angle is kept), the smallest of the form k / 100 that closes every open
  channel with a margin ``STABILISING_MARGIN`` (g g > t t~ at MT = 173.3:
  MW = 80.419 -> 180.94275, MZ = 91.188 -> 205.173, the factor 2.25),
  provided no external leg's mass moves; the benchmark's ``ward_parameters``
  set such a spectrum by hand. The check's verdict comes from those rows, so a broken
  amplitude still fails; the requested parameters' values are untouched
  (every evaluation takes its parameters per call);
* without such a spectrum (no runtime vector-boson mass input, or one
  that moves an external mass, as for an external W, whose decays to
  massless fermions are always open) the unstable rows stay inconclusive,
  never a pass.

The stabilised evaluation costs one more Ward batch (the physical entry
and every leg and factor) per point, only where an unstable leg is
present. Outside the real on-shell scheme the case does not arise: the
complex-mass scheme refuses external unstable particles
(``cms-external-width``).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal
from fractions import Fraction
from typing import Any

from .assemble import COMPONENTS, LoopSlice
from .stability import REDUCTION, StabilityChecks

# epsilon_j -> c p_j for c = 1 and c = i (as (real, imaginary) parts): the
# inclusive output is the real part of the interference, so the two factors
# check all of it.
WARD_FACTORS = ((1, 0), (0, 1))

# The components a row reports (the virtual is the criterion).
PARTS = ("virtual", "bare", "r2", "uv_local", "uv_external_fields")

# Module docstring, "The criterion".
BORN_BOUNDS = {"double": 1e-12, "double-double": 1e-24}
VIRTUAL_BOUNDS = {"double-double": 1e-25}
ESTIMATE_FACTOR = 10
BINARY64_SCOPE = 1e-9
BINARY64_FLOOR = 1e-12
# The unit roundoff per carrier of rule 3's resolution floor F_k (module
# docstring).
RESOLUTION_UNITS = {"double": 2.0**-53, "double-double": 2.0**-104}
# The stability check the binary64 criterion reads.
WARD_CHECKS = StabilityChecks(reduction_direction=True)
# The coupling of a coefficient's scale floor (module docstring, "Vanishing
# coefficients"): alpha(0).
SCALE_FLOOR_COUPLING = 1 / 137.035999
# Module docstring, "Unstable external legs": the stabilised spectrum puts
# every open channel's threshold at least this factor above the decaying
# mass; the common scale factor is searched in steps of 1/100 up to
# ``STABILISING_LIMIT``.
STABILISING_MARGIN = Fraction(26, 25)
STABILISING_LIMIT = 20
# Digits of the masses the instability test evaluates.
MASS_DIGITS = 30


def ward_slice(compiled: Any, request: Any, native: Any, **options: Any) -> LoopSlice:
    """``LoopSlice.generate`` of ``request`` on the full tree kernels of the
    compiled model (``catalogue.compile_tree_kernel_variant``), which the
    Ward mode needs; ``options`` are ``generate``'s."""

    from .catalogue import compile_tree_kernel_variant

    full = compile_tree_kernel_variant(compiled, "full")
    return LoopSlice.generate(full, request, native, **options)


def require_full_kernels(slice_: Any) -> None:
    """Refuse the Ward mode on a slice (or a stored process's view) that was
    not generated on the full tree kernels."""

    blocks = getattr(slice_, "blocks", None)
    if getattr(blocks, "kernel_variant", None) != "full":
        raise ValueError(
            "the Ward mode needs the full tree kernels (the transverse "
            "Yang-Mills kernel assumes conserved currents): generate the slice "
            "with ward.ward_slice; a stored process serves it only when stored "
            "from such a slice"
        )


def point_wards(ward: Any, count: int) -> list[Any]:
    """One Ward value (or None) per point: ``ward`` for every point, or a
    list with one entry per point."""

    if isinstance(ward, list):
        if len(ward) != count:
            raise ValueError("one Ward value per point")
        return list(ward)
    return [ward] * count


def ward_leg(ward: Any) -> int:
    """The leg label of a Ward value."""

    from .observables import _ward

    return _ward(ward)[0]


def loop_vector(
    ward: Any, momentum: Sequence[Any]
) -> tuple[tuple[Fraction, Fraction], ...]:
    """The exact (real, imaginary) components of the loop-side vector of a
    Ward value at a point: c p_j for the leg's physical momentum ``momentum``
    (as given: incoming legs incoming, outgoing legs outgoing), or the
    literal vector."""

    from .assemble import _fraction
    from .observables import _ward

    _leg, value = _ward(ward)
    if len(value) == 4:
        return tuple((Fraction(re), Fraction(im)) for re, im in value)
    re, im = value
    return tuple((re * _fraction(x), im * _fraction(x)) for x in momentum)


def gauge_ward(leg: int, factor: Any, point: Sequence[Sequence[Any]]) -> Any:
    """The Ward value epsilon_j -> c p_j / p_j^0 of leg ``leg`` at ``point``
    (``factor`` c as a (real, imaginary) pair): exact, light-like for a
    massless leg, with components of the size of a polarisation vector's."""

    from .assemble import _fraction

    energy = _fraction(point[leg - 1][0])
    re, im = factor
    return (leg, (Fraction(re) / energy, Fraction(im) / energy))


def rotated_ward(rotation: Any, ward: Any) -> Any:
    """A Ward value for the rotated point (``observables._rotated_ward``: a
    literal vector rotates with the momenta, c p_j by itself)."""

    from .observables import _rotated_ward

    return _rotated_ward(rotation, ward)


def gauge_legs(slice_: Any) -> tuple[int, ...]:
    """The labels of the slice's external massless vector legs (gluons and
    photons: the legs whose polarisation the Ward check may replace); a
    stored process's view reads them from its record (``gauge_legs``, written
    for a process stored from a full-kernel slice; None otherwise)."""

    if not hasattr(slice_, "data"):
        stored = getattr(slice_, "gauge_legs", None)
        return () if stored is None else tuple(stored)
    particles = {int(entry["pdg_code"]): entry for entry in slice_.data["particles"]}
    out = []
    for leg in sorted(slice_.blocks.process.legs, key=lambda x: x.label):
        entry = particles[int(leg.pdg)]
        if int(entry["spin"]) == 3 and entry.get("mass") in (None, "ZERO", "0"):
            out.append(int(leg.label))
    return tuple(out)


@dataclass(frozen=True)
class UnstableLeg:
    """An external leg that can decay at its own mass (module docstring,
    "Unstable external legs"): its label and particle, its mass, the open
    channel's decay products (the lowest open threshold, a physical channel
    preferred to a Goldstone one of the same threshold) and that
    threshold."""

    leg: int
    particle: str
    mass: float
    channel: tuple[str, str]
    threshold: float

    def describe(self) -> str:
        a, b = self.channel
        return (
            f"leg {self.leg} ({self.particle}, mass {self.mass:.6g}) decays to "
            f"{a} {b} (threshold {self.threshold:.6g})"
        )


def slice_masses(slice_: Any, parameters: Mapping[str, str] | None = None) -> Any:
    """The slice's parameter evaluator at ``parameters`` (the caller's runtime
    parameters, validated as an evaluation validates them, with the fixed
    ones): parameter name -> |value| as a float, an external parameter its
    value, a derived one its definition at ``MASS_DIGITS`` digits (as
    ``assemble._model_masses`` evaluates masses, a vanishing one included),
    ZERO -> 0."""

    from decimal import Decimal as _Decimal

    from .assemble import (
        Precision,
        _definition_value,
        _kernel_parameters,
        _substitutions,
    )

    compiled = slice_.compiled
    values = slice_._point_parameters(
        dict(parameters or {}), Fraction(1), Precision.double()
    )
    known = _kernel_parameters(compiled, values)
    definitions = {
        record.name: record.resolved_expression
        for record in compiled.ir.parameters
        if record.nature == "internal"
    }
    found: dict[str, float] = {}
    substitutions: list[Any] = []

    def value(name: str) -> float:
        name = str(name)
        if name in ("ZERO", "0"):
            return 0.0
        if name in known:
            return abs(complex(known[name]))
        if name not in found:
            if name not in definitions:
                raise KeyError(f"{name!r} is no model parameter")
            if not substitutions:
                external = {
                    record.name: _Decimal(
                        values.get(
                            record.name,
                            str(compiled.parameter_defaults[record.name][0]),
                        )
                    )
                    for record in compiled.ir.parameters
                    if record.nature == "external"
                    and record.name in compiled.parameter_defaults
                }
                substitutions.append(_substitutions(compiled, external, MASS_DIGITS))
            real, imaginary = _definition_value(
                definitions[name], substitutions[0], MASS_DIGITS
            )
            found[name] = abs(complex(float(real), float(imaginary)))
        return found[name]

    return value


def _particle_records(compiled: Any) -> tuple[dict[int, Any], dict[str, Any]]:
    by_pdg: dict[int, Any] = {}
    by_name: dict[str, Any] = {}
    for record in compiled.ir.particles:
        by_pdg[int(record.pdg_code)] = record
        by_name[str(record.name)] = record
    return by_pdg, by_name


def _leg_record(by_pdg: Mapping[int, Any], pdg: int) -> Any:
    return by_pdg.get(int(pdg)) or by_pdg.get(-int(pdg))


def _substituted_kinds(
    by_pdg: Mapping[int, Any], slice_: Any, legs: Sequence[int]
) -> set[str]:
    """What the substituted legs constrain: "colour" (a gluon leg), "charge"
    (a photon leg: a massless colour-singlet neutral vector)."""

    pdgs = {int(leg.label): int(leg.pdg) for leg in slice_.blocks.process.legs}
    kinds = set()
    for label in legs:
        record = _leg_record(by_pdg, pdgs[int(label)])
        if record is None:
            continue
        kinds.add("colour" if abs(int(record.color)) != 1 else "charge")
    return kinds


def unstable_external_legs(
    slice_: Any,
    legs: Sequence[int] | None = None,
    parameters: Mapping[str, str] | None = None,
    *,
    masses: Callable[[str], float] | None = None,
) -> tuple[UnstableLeg, ...]:
    """The external legs of ``slice_`` that the Ward check of the substituted
    ``legs`` (default: ``gauge_legs``) constrains and that can decay at their
    own mass at ``parameters`` (module docstring, "Unstable external legs"):
    coloured legs for a gluon leg, charged legs for a photon leg; massive,
    of zero width, with an open tree-level two-body channel among the
    model's three-point vertices (ghosts excluded). ``masses`` (default:
    ``slice_masses``) maps a parameter name to its value. A stored process's
    view (no model) has none it can name."""

    compiled = getattr(slice_, "compiled", None)
    blocks = getattr(slice_, "blocks", None)
    if compiled is None or blocks is None:
        return ()
    legs = tuple(gauge_legs(slice_) if legs is None else legs)
    if not legs:
        return ()
    value = masses or slice_masses(slice_, parameters)
    by_pdg, by_name = _particle_records(compiled)
    kinds = _substituted_kinds(by_pdg, slice_, legs)
    # Only a channel whose vertex the requested corrections' loops carry
    # opens a cut of the leg's self-energy (t -> W b is no cut of a QCD loop).
    request = getattr(slice_, "request", None)
    orders = None
    if request is not None:
        from .ew_policy import request_corrections

        orders = set(request_corrections(compiled, request))
    three = [
        tuple(str(name) for name in term.particles)
        for term in compiled.ir.vertex_terms
        if len(term.particles) == 3
        and (
            orders is None
            or any(str(order) in orders for order, _ in term.coupling_orders)
        )
    ]
    found = []
    for leg in sorted(blocks.process.legs, key=lambda x: x.label):
        record = _leg_record(by_pdg, int(leg.pdg))
        if record is None or int(leg.label) in legs:
            continue
        charged = ("colour" in kinds and abs(int(record.color)) != 1) or (
            "charge" in kinds and float(record.charge) != 0
        )
        if not charged:
            continue
        mass = value(str(record.mass))
        if mass == 0 or value(str(record.width)) != 0:
            continue
        name = (
            str(record.name)
            if int(leg.pdg) == int(record.pdg_code)
            else str(record.antiname)
        )
        conjugate = (
            str(record.antiname) if name == str(record.name) else str(record.name)
        )
        channels = []
        for particles in three:
            rest = list(particles)
            if name in rest:
                # Incoming parent: the others are the conjugates of the
                # decay products.
                rest.remove(name)
                products = [
                    str(by_name[x].antiname) if x in by_name else x for x in rest
                ]
            elif conjugate in rest:
                rest.remove(conjugate)
                products = rest
            else:
                continue
            records = [by_name.get(x) for x in rest]
            if any(
                r is None or int(getattr(r, "ghost_number", 0) or 0) for r in records
            ):
                continue
            threshold = sum(value(str(r.mass)) for r in records)
            if mass > threshold * (1 + 1e-12) + 1e-300:
                goldstone = any(
                    bool(getattr(r, "goldstoneboson", False)) for r in records
                )
                channels.append((threshold, goldstone, tuple(sorted(products))))
        if channels:
            threshold, _goldstone, products = min(channels)
            found.append(
                UnstableLeg(
                    int(leg.label), name, mass, (products[0], products[1]), threshold
                )
            )
    return tuple(found)


def unstable_reason(
    unstable: Sequence[UnstableLeg],
    stabilised: Mapping[str, str] | None,
    why: str | None = None,
) -> str:
    """The reason of a Ward row inconclusive at the requested spectrum (module
    docstring, "Unstable external legs"): the legs, their open channels and
    the remedy (the stabilised spectrum the check judges instead, or why
    there is none)."""

    legs = "; ".join(leg.describe() for leg in unstable)
    text = (
        f"unstable external leg: {legs}; in the real on-shell scheme the Ward "
        "identity does not hold for the absorptive part of the amplitude there"
    )
    if stabilised:
        moved = ", ".join(f"{k} = {v}" for k, v in sorted(stabilised.items()))
        return text + f"; judged on the stabilised spectrum {moved}"
    return (
        text
        + "; no stabilised spectrum"
        + (f" ({why})" if why else "")
        + ": check on a spectrum where these legs are stable"
    )


def stabilised_parameters(
    slice_: Any,
    legs: Sequence[int] | None = None,
    parameters: Mapping[str, str] | None = None,
) -> tuple[dict[str, str] | None, str | None]:
    """The stabilised spectrum of a Ward check at ``parameters`` (module
    docstring, "Unstable external legs"): (the runtime inputs it moves with
    their values, None), ({}, None) without an unstable leg, or (None, why
    there is none). Every runtime mass input of a massive vector boson is
    scaled by the smallest common factor k / 100 that leaves no unstable leg
    with every open threshold of the requested spectrum at least
    ``STABILISING_MARGIN`` above its leg's mass; refused if it moves an
    external leg's mass."""

    from .assemble import Precision

    legs = tuple(gauge_legs(slice_) if legs is None else legs)
    unstable = unstable_external_legs(slice_, legs, parameters)
    if not unstable:
        return {}, None
    compiled = slice_.compiled
    values = slice_._point_parameters(
        dict(parameters or {}), Fraction(1), Precision.double()
    )
    runtime = set(slice_._external_parameters()) - set(slice_.fixed_parameters)
    runtime -= set(getattr(slice_, "preparation_fixed_parameters", None) or ())
    runtime.discard(slice_.scale_parameter)
    names = sorted(
        {
            str(record.mass)
            for record in compiled.ir.particles
            if int(record.spin) == 3
            and not int(getattr(record, "ghost_number", 0) or 0)
            and str(record.mass) in runtime
        }
    )
    if not names:
        return None, "the model has no runtime mass input of a massive vector boson"
    current = {
        name: Decimal(str(values.get(name, compiled.parameter_defaults[name][0])))
        for name in names
    }
    before = slice_masses(slice_, parameters)
    by_pdg, _ = _particle_records(compiled)
    externals = [
        _leg_record(by_pdg, int(leg.pdg)) for leg in slice_.blocks.process.legs
    ]
    leg_masses = [before(str(r.mass)) if r is not None else 0.0 for r in externals]
    need = max(
        float(STABILISING_MARGIN) * leg.mass / leg.threshold
        if leg.threshold
        else math.inf
        for leg in unstable
    )
    if not math.isfinite(need):
        return None, "an open channel has massless decay products only"
    step = Decimal("0.01")
    factor = (Decimal(str(need))).quantize(step, rounding=ROUND_CEILING)
    while factor <= STABILISING_LIMIT:
        moved = {name: _decimal_text(current[name] * factor) for name in names}
        trial = {**dict(parameters or {}), **moved}
        after = slice_masses(slice_, trial)
        if [
            after(str(r.mass)) if r is not None else 0.0 for r in externals
        ] != leg_masses:
            return None, (f"scaling {', '.join(names)} moves an external leg's mass")
        if not unstable_external_legs(slice_, legs, trial, masses=after) and all(
            _threshold(compiled, leg, after) >= float(STABILISING_MARGIN) * leg.mass
            for leg in unstable
        ):
            return moved, None
        factor += step
    return None, (
        f"scaling {', '.join(names)} by up to {STABILISING_LIMIT} closes no open "
        "channel"
    )


def _threshold(compiled: Any, leg: UnstableLeg, value: Callable[[str], float]) -> float:
    """The threshold of ``leg``'s channel at the masses ``value``."""

    _, by_name = _particle_records(compiled)
    total = 0.0
    for name in leg.channel:
        record = by_name.get(name)
        total += value(str(record.mass)) if record is not None else 0.0
    return total


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def scale_floor(physical: Any) -> float:
    """The floor of every coefficient's scale (module docstring, "Vanishing
    coefficients"): |physical Born| x alpha / (2 pi); 0 without a Born."""

    born = getattr(physical, "born", None) or {}
    total = abs(sum(complex(value) for value in born.values())) if born else 0.0
    return total * SCALE_FLOOR_COUPLING / (2 * math.pi)


def ward_scales(physical: Any) -> list[float]:
    """Per Laurent coefficient (finite, single, double pole) the physical
    scale of a Ward result: the largest component magnitude over the
    sectors of the physical evaluation ``physical`` (a ``PointResult``)."""

    width = len(next(iter(physical.components["virtual"].values())).coefficients)
    return [
        max(
            abs(complex(laurent.coefficients[k]))
            for name in COMPONENTS
            for laurent in physical.components[name].values()
        )
        for k in range(width)
    ]


def lane_scales(result: Any, average: int) -> list[float]:
    """Per Laurent coefficient the absolute sum of a result's family lanes'
    bare contributions, 2 |Omega| / (16 pi^2 average): the conditioning of
    the Ward cancellation (``test_loop_v2_observables._lane_scale``)."""

    import math

    from .conventions import LOOP_FACTOR_DENOMINATOR

    factor = 2 / (LOOP_FACTOR_DENOMINATOR * math.pi**2 * average)
    lanes = list(result.families.values())
    width = len(lanes[0].coefficients) if lanes else 1
    return [
        factor * sum(abs(complex(lane.coefficients[k])) for lane in lanes)
        for k in range(width)
    ]


def largest(result: Any, part: str) -> list[float]:
    """Per Laurent coefficient the largest magnitude of a component over the
    sectors of a result."""

    laurents = list(result.components[part].values())
    width = len(laurents[0].coefficients)
    return [
        max(abs(complex(laurent.coefficients[k])) for laurent in laurents)
        for k in range(width)
    ]


def born_ratio(result: Any, physical: Any) -> float:
    """|sum of a Ward result's loop-side Born interference| over |the
    physical Born| (``PointResult.loop_born``, ``born``)."""

    if result.loop_born is None:
        raise ValueError("the result has no loop-side Born (no Ward value)")
    ward = sum(complex(value) for value in result.loop_born.values())
    born = sum(complex(value) for value in physical.born.values())
    return abs(ward) / abs(born)


def _ratio(value: float, scale: float) -> float:
    """``value / scale``; a vanishing scale (a coefficient no physical
    component has, e.g. the double pole of the "uv" selection) admits only a
    vanishing value (0, else infinity)."""

    if scale:
        return value / scale
    return 0.0 if value == 0 else float("inf")


def uncertified_bounds(result: Any, sectors: Sequence[Any], width: int) -> Any:
    """The absolute bound of a result's lanes served without accuracy
    evidence (``PointResult.uncertified_bound``) per sector of ``sectors``
    and Laurent coefficient (``width`` of them): a list per sector, zeros
    without such lanes. A bound recorded for a column that is not one of the
    sectors (an observable column) is not attributable: every sector's bound
    is then infinite."""

    found = getattr(result, "uncertified_bound", None) or {}
    out = {sector: [0.0] * width for sector in sectors}
    for column, bound in found.items():
        if column not in out:
            return {sector: [math.inf] * width for sector in sectors}
        out[column] = [float(b) for b in bound[:width]]
    return out


def judged(residual: float, allowed: float, uncertain: float) -> bool | None:
    """THE THREE-WAY RULE of a check whose residual includes lanes served
    without accuracy evidence, of absolute bound ``uncertain`` (0: none):
    True iff residual + uncertain <= allowed (the criterion holds whatever
    those lanes' true values within their bound), False iff residual -
    uncertain > allowed (it fails whatever they are), None otherwise
    (inconclusive: never a pass), and for an infinite bound."""

    if uncertain == 0:
        return residual <= allowed
    if not math.isfinite(uncertain):
        return None
    if residual + uncertain <= allowed:
        return True
    if residual - uncertain > allowed:
        return False
    return None


def ward_row(
    physical: Any,
    result: Any,
    carrier: str,
    unstable: Sequence[UnstableLeg] = (),
    reason: str | None = None,
) -> dict[str, Any]:
    """The criterion of one Ward evaluation (module docstring): ``physical``
    and ``result`` are the ``PointResult`` of the same point without and with
    the Ward value, ``carrier`` "double" or "double-double". Returns the
    ratios to the physical scale (per Laurent coefficient, the largest over
    the sectors), the estimate's (E_k / scale_k, None without checks) with
    |V_k| / max(E_k, F_k) (``estimate_over``, rule 3; F_k / scale_k is
    ``resolution``, binary64 only) and, in binary64, |V_k| / max(1e-12
    scale_k, E_k) (``o1_over``, rule 2), the Born ratio, the bound of the
    lanes served without accuracy evidence over the scale (``uncertified``,
    None without such lanes) and ``passed``: True, False, or None (binary64
    without checks; or INCONCLUSIVE, with the reason in ``inconclusive``:
    the uncertified lanes' bound straddles the criterion, has no finite
    value, or the physical scale itself rests on uncertified lanes)."""

    if carrier not in BORN_BOUNDS:
        raise ValueError(f"no Ward criterion for the carrier {carrier!r}")
    measured = ward_scales(physical)
    floor = scale_floor(physical)
    scale = [max(s, floor) for s in measured]
    width = len(scale)
    parts = {
        name: [_ratio(v, s) for v, s in zip(largest(result, name), scale, strict=True)]
        for name in PARTS
    }
    born = born_ratio(result, physical)
    row: dict[str, Any] = {
        "born": born,
        "born_passed": born <= BORN_BOUNDS[carrier],
        "parts": parts,
        "scale_floor": [s < floor for s in measured],
        "estimate": None,
        "estimate_over": None,
        "uncertified": None,
    }
    virtual = result.components["virtual"]
    uncertain = uncertified_bounds(result, list(virtual), width)
    if any(b for bounds in uncertain.values() for b in bounds):
        row["uncertified"] = [
            _ratio(max(uncertain[sector][k] for sector in virtual), scale[k])
            for k in range(width)
        ]
    # The physical normalization's interval: the scale of coefficient k is
    # the largest physical component, which the physical point's uncertified
    # lanes can move by at most U_k (their bound, the largest over sectors).
    physical_virtual = physical.components["virtual"]
    normalization = uncertified_bounds(physical, list(physical_virtual), width)
    spread = [
        max((bounds[k] for bounds in normalization.values()), default=0.0)
        for k in range(width)
    ]
    low = [max(scale[k] - spread[k], 0.0) for k in range(width)]
    high = [scale[k] + spread[k] for k in range(width)]
    if any(spread):
        row["scale_interval"] = [
            (_ratio(a, s_), _ratio(b, s_))
            for a, b, s_ in zip(low, high, scale, strict=True)
        ]
    estimate = result.stability
    if estimate is not None and set(estimate.budgets) != {REDUCTION}:
        raise ValueError(
            "the Ward criterion reads the reduction-direction check alone (a "
            "rotation check is no rounding estimate of a Ward evaluation)"
        )
    absolute = None
    in_scope = True
    if estimate is not None:
        absolute = {
            sector: [abs(float(x)) for x in estimate.absolute[sector].coefficients]
            for sector in virtual
        }
        # Rule 3's resolution floor F_k, binary64 only (module docstring);
        # double-double keeps E_k alone.
        lanes = max(1, len(getattr(result, "families", None) or ()))
        floor = [
            lanes * RESOLUTION_UNITS[carrier] * scale[k] if carrier == "double" else 0.0
            for k in range(width)
        ]
        row["estimate"] = [
            _ratio(max(absolute[sector][k] for sector in virtual), scale[k])
            for k in range(width)
        ]
        if carrier == "double":
            row["resolution"] = [_ratio(floor[k], scale[k]) for k in range(width)]
        row["estimate_over"] = [
            max(
                _ratio(
                    abs(complex(laurent.coefficients[k])),
                    max(absolute[sector][k], floor[k]),
                )
                for sector, laurent in virtual.items()
            )
            for k in range(width)
        ]
        if carrier == "double":
            in_scope = all(e <= BINARY64_SCOPE for e in row["estimate"])
            row["o1_over"] = [
                max(
                    _ratio(
                        abs(complex(laurent.coefficients[k])),
                        max(BINARY64_FLOOR * scale[k], absolute[sector][k]),
                    )
                    for sector, laurent in virtual.items()
                )
                for k in range(width)
            ]
            row["in_scope"] = in_scope

    lanes = max(1, len(getattr(result, "families", None) or ()))

    def allowed(sector: Any, k: int, size: float) -> float | None:
        """The bound on |V_k| of one sector at the physical scale ``size``:
        binary64 min(max(1e-12 S_k, E_k), 10 max(E_k, F_k)) with F_k = n u
        S_k (rules 2 and 3; None without the estimate); double-double 1e-25
        S_k, and 10 E_k with the estimate (rule 3, no floor). Monotone in
        S_k."""

        if carrier == "double":
            if absolute is None:
                return None
            e = absolute[sector][k]
            resolution = lanes * RESOLUTION_UNITS[carrier] * size
            return min(
                max(BINARY64_FLOOR * size, e), ESTIMATE_FACTOR * max(e, resolution)
            )
        bound = VIRTUAL_BOUNDS[carrier] * size
        if absolute is not None:
            bound = min(bound, ESTIMATE_FACTOR * absolute[sector][k])
        return bound

    # The three-way rule over the residue's interval (its uncertified lanes'
    # bound) AND the scale's (the physical normalization's): a pass at the
    # smallest scale passes everywhere, a failure at the largest fails
    # everywhere (``allowed`` grows with the scale); anything else, or no
    # finite interval, is inconclusive.
    verdicts = []
    for sector, laurent in virtual.items():
        for k in range(width):
            least = allowed(sector, k, low[k])
            most = allowed(sector, k, high[k])
            if least is None or most is None:
                verdicts.append("none")
                continue
            value = abs(complex(laurent.coefficients[k]))
            if judged(value, least, uncertain[sector][k]) is True:
                verdicts.append(True)
            elif judged(value, most, uncertain[sector][k]) is False:
                verdicts.append(False)
            else:
                verdicts.append(None)
    scope_low = scope_high = True
    if carrier == "double" and absolute is not None:
        largest_e = [
            max(absolute[sector][k] for sector in virtual) for k in range(width)
        ]
        scope_low = all(
            e <= BINARY64_SCOPE * size for e, size in zip(largest_e, low, strict=True)
        )
        scope_high = all(
            e <= BINARY64_SCOPE * size for e, size in zip(largest_e, high, strict=True)
        )
    # Demonstrably out of the binary64 scope: at every scale the physical
    # normalization allows (the stored checks skip only such a point).
    row["scope_excluded"] = not scope_high
    if "none" in verdicts:
        virtual_passed = None
    elif not scope_high or False in verdicts:
        virtual_passed = False
    elif None in verdicts or not scope_low:
        virtual_passed = None
        if any(spread):
            row["inconclusive"] = (
                "the physical normalization rests on reduction lanes served "
                "without accuracy evidence: the criterion differs across its "
                "interval"
            )
        else:
            row["inconclusive"] = (
                "reduction lanes served without accuracy evidence: their absolute "
                "bound ("
                + ", ".join(f"{x:.3g}" for x in (row["uncertified"] or [math.inf]))
                + " of the physical scale) straddles the criterion or is not finite"
            )
    else:
        virtual_passed = True
    row["virtual_passed"] = virtual_passed
    row["passed"] = (
        None if virtual_passed is None else bool(virtual_passed and row["born_passed"])
    )
    if unstable and virtual_passed is False and row["born_passed"]:
        # Module docstring, "Unstable external legs": not a failure at the
        # requested spectrum; the stabilised rows judge.
        row["passed"] = None
        row["unstable"] = reason or unstable_reason(unstable, None)
        row["inconclusive"] = "inconclusive: " + row["unstable"]
    return row


def ward_check(
    executor: Any,
    point: Sequence[Sequence[Any]],
    scale: Any,
    carrier: str,
    *,
    legs: Sequence[int] | None = None,
    factors: Sequence[Any] = WARD_FACTORS,
    parameters: Any = None,
    checks: bool | None = None,
    precision: Any = None,
    judge: bool = True,
    stabilise: bool = True,
) -> dict[str, Any]:
    """The Ward check of one point in one batch of ``executor`` (a
    ``plan_export.NativeExecutor`` of a ``ward_slice``, either input path):
    the physical evaluation and, per leg (default: ``gauge_legs``) and
    factor, the evaluation with ``gauge_ward``, judged by ``ward_row``.
    ``carrier`` is "double" or "double-double" (the criterion);
    ``precision`` the evaluation's ``assemble.Precision`` (default: that
    carrier's; an arbitrary-precision one takes the double-double criterion,
    ``pyamplicol check``'s rung); ``checks`` (default: in binary64 only)
    runs ``WARD_CHECKS``, which the binary64 criterion reads. Returns
    ``physical`` (the ``PointResult``), ``results`` (one per row), ``rows``
    (``ward_row`` plus ``leg`` and ``factor``) and ``passed`` (every row;
    None if a row has no criterion). ``judge`` False: ``rows`` hold ``leg``
    and ``factor`` alone and ``passed`` is None (``pyamplicol check`` judges
    the results itself, ``checks._ward_measures``).

    ``unstable`` lists the external legs that can decay at their own mass
    (``unstable_external_legs``, module docstring "Unstable external legs").
    With one, a judged check whose ``stabilise`` is True (the default) also
    evaluates the rows on the stabilised spectrum (``stabilised_parameters``)
    in a second batch: ``stabilised`` holds its ``parameters`` (the moved
    inputs; None without such a spectrum, ``why`` says why), ``physical``,
    ``results`` and ``rows``; ``passed`` is then formed from the stabilised
    rows and the requested-spectrum rows that are not inconclusive for the
    unstable leg alone (None, never a pass, without a stabilised spectrum).
    Each evaluation takes its parameters per call: the requested
    spectrum's values are not changed by the stabilised one."""

    from .assemble import Precision

    precisions = {"double": Precision.double, "double-double": Precision.double_double}
    if carrier not in precisions:
        raise ValueError(f"no Ward criterion for the carrier {carrier!r}")
    if precision is None:
        precision = precisions[carrier]()
    elif (precision.arithmetic == "double") != (carrier == "double"):
        raise ValueError(
            f"a {precision.arithmetic} evaluation has no {carrier} Ward criterion"
        )
    legs = tuple(legs if legs is not None else gauge_legs(executor.slice))
    checked = carrier == "double" if checks is None else checks
    labels = [(leg, factor) for leg in legs for factor in factors]

    def batch(values: Any) -> tuple[Any, list[Any]]:
        found = executor.evaluate(
            [point] * (len(labels) + 1),
            [scale] * (len(labels) + 1),
            parameters=values,
            precision=precision,
            ward=[None, *(gauge_ward(leg, factor, point) for leg, factor in labels)],
            stability=WARD_CHECKS if checked else None,
        )
        return found[0], list(found[1:])

    unstable = unstable_external_legs(executor.slice, legs, parameters)
    physical, results = batch(parameters)
    stabilised: dict[str, Any] | None = None
    reason = None
    if unstable and judge and stabilise:
        moved, why = stabilised_parameters(executor.slice, legs, parameters)
        reason = unstable_reason(unstable, moved, why)
        stabilised = {"parameters": moved, "why": why}
        if moved:
            stable_physical, stable_results = batch({**dict(parameters or {}), **moved})
            stable_rows = []
            for (leg, factor), result in zip(labels, stable_results, strict=True):
                judged = ward_row(stable_physical, result, carrier)
                stable_rows.append({**judged, "leg": leg, "factor": factor})
            stabilised.update(
                physical=stable_physical, results=stable_results, rows=stable_rows
            )
    rows = []
    for (leg, factor), result in zip(labels, results, strict=True):
        judged = (
            ward_row(physical, result, carrier, unstable, reason)
            if judge
            else {"passed": None}
        )
        rows.append({**judged, "leg": leg, "factor": factor})
    verdicts = [
        row["passed"]
        for row in rows
        if not (stabilised and stabilised.get("rows") and "unstable" in row)
    ]
    if stabilised and stabilised.get("rows"):
        verdicts += [row["passed"] for row in stabilised["rows"]]
    return {
        "physical": physical,
        "results": results,
        "rows": rows,
        "unstable": unstable,
        "stabilised": stabilised,
        "passed": None if None in verdicts else all(verdicts),
    }


__all__ = [
    "BINARY64_FLOOR",
    "BINARY64_SCOPE",
    "BORN_BOUNDS",
    "ESTIMATE_FACTOR",
    "MASS_DIGITS",
    "PARTS",
    "RESOLUTION_UNITS",
    "SCALE_FLOOR_COUPLING",
    "STABILISING_LIMIT",
    "STABILISING_MARGIN",
    "VIRTUAL_BOUNDS",
    "WARD_CHECKS",
    "WARD_FACTORS",
    "UnstableLeg",
    "born_ratio",
    "gauge_legs",
    "gauge_ward",
    "judged",
    "lane_scales",
    "largest",
    "loop_vector",
    "point_wards",
    "require_full_kernels",
    "rotated_ward",
    "scale_floor",
    "slice_masses",
    "stabilised_parameters",
    "uncertified_bounds",
    "unstable_external_legs",
    "unstable_reason",
    "ward_check",
    "ward_leg",
    "ward_row",
    "ward_scales",
    "ward_slice",
]
