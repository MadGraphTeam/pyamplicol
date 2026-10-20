# SPDX-License-Identifier: 0BSD
"""Process specifications and generic physics metadata for provider references."""

from fractions import Fraction
import json
import math
from pathlib import Path

DEFAULT_SPEC = Path(__file__).with_name("required_processes.json")
CORRECTION_STEP = {"QCD": {"QCD": 2, "QED": 0}, "EW": {"QCD": 0, "QED": 2}}

# Generic SM particle data used only for metadata and independent pole checks:
# (spin states of a massless/massive particle, colour dimension, electric charge).
_FERMION = {1: -Fraction(1, 3), 2: Fraction(2, 3), 3: -Fraction(1, 3), 4: Fraction(2, 3),
            5: -Fraction(1, 3), 6: Fraction(2, 3), 11: -1, 13: -1, 15: -1, 12: 0, 14: 0, 16: 0}
_BOSON = {21: (8, 0), 22: (1, 0), 23: (1, 0), 24: (1, 1), 25: (1, 0)}


def particle(pdg):
    """Return colour dimension, charge and whether the field is a vector boson."""
    a = abs(pdg)
    if a in _FERMION:
        charge = Fraction(_FERMION[a]) * (1 if pdg > 0 else -1)
        return {"colour": 3 if a <= 6 else 1, "charge": charge, "spin": "1/2"}
    if a in _BOSON:
        colour, charge = _BOSON[a]
        return {"colour": colour, "charge": Fraction(charge if pdg > 0 else -charge),
                "spin": "0" if a == 25 else "1"}
    raise ValueError(f"no metadata for PDG {pdg}")


def load(path=DEFAULT_SPEC):
    return json.loads(Path(path).read_text())


def load_process(path, name, roots=None):
    """Return one process merged with its scheme and derived loop orders."""
    data = load(path)
    matches = [p for p in data["processes"] if p["name"] == name]
    if len(matches) != 1:
        raise KeyError(f"process {name!r} not uniquely defined in {path}")
    process = json.loads(json.dumps(matches[0]))
    scheme = data["schemes"][process["scheme"]]
    process["scheme_data"] = scheme
    step = CORRECTION_STEP[process["correction"]]
    process["loop_orders"] = {k: process["born_orders"][k] + step[k] for k in ("QCD", "QED")}
    process.setdefault("madloop", {})
    process["madloop"].setdefault("model", scheme["madloop_model"])
    for key, value in (roots or {}).items():
        process["madloop"]["model"] = process["madloop"]["model"].replace("{" + key + "}", str(value))
    return process


def masses(process):
    """Exact on-shell masses of the external legs from the scheme parameters."""
    values = {**process["scheme_data"]["parameters"], **process["scheme_data"]["fixed_parameters"]}
    names = {5: "MB", 6: "MT", 15: "MTA", 23: "MZ", 24: "MW", 25: "MH"}
    out = []
    for pdg in process["pdgs"]:
        name = names.get(abs(pdg))
        out.append(Fraction(values[name]) if name and name in values else Fraction(0))
    return out


def normalization(process, n_initial=2):
    """Initial spin/colour average and final identical-particle factor."""
    masses_ = masses(process)
    denominator = 1
    for pdg, mass in zip(process["pdgs"][:n_initial], masses_[:n_initial]):
        info = particle(pdg)
        spins = 2 if info["spin"] == "1/2" else (1 if info["spin"] == "0" else (3 if mass else 2))
        denominator *= spins * info["colour"]
    symmetry = 1
    final = process["pdgs"][n_initial:]
    for pdg in set(final):
        symmetry *= math.factorial(final.count(pdg))
    return {"initial_average": denominator, "final_symmetry": symmetry,
            "denominator": denominator * symmetry}


def double_pole_factor(process, coupling):
    """Universal one-loop double pole D/Born for the declared correction.

    QCD: -alpha_s/(2 pi) * sum of C_F/C_A over massless coloured legs.
    EW: -alpha/(2 pi) * sum of Q^2 over massless charged legs (photon-exchange
    soft-collinear singularity; massive W/Z exchange is IR finite). Uses the
    MadLoop/BLHA C_epsilon normalization.
    """
    total = Fraction(0)
    for pdg, mass in zip(process["pdgs"], masses(process)):
        if mass:
            continue
        info = particle(pdg)
        if process["correction"] == "QCD":
            total += {3: Fraction(4, 3), 8: Fraction(3), 1: Fraction(0)}[info["colour"]]
        else:
            total += info["charge"] ** 2
    return -float(total) * coupling / (2 * math.pi)
