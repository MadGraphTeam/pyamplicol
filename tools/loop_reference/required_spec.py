# SPDX-License-Identifier: 0BSD
"""Process specifications and generic physics metadata for provider references."""

from decimal import Decimal, localcontext
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
    """Return one process merged with its scheme and derived loop orders.

    A process may override scheme parameters (``parameter_overrides``, e.g. a
    runtime-parameter variant of a row reusing another row's export); the
    overrides replace the scheme's value wherever it is listed (``parameters``
    or ``fixed_parameters``) and are recorded in ``scheme_data``."""
    data = load(path)
    matches = [p for p in data["processes"] if p["name"] == name]
    if len(matches) != 1:
        raise KeyError(f"process {name!r} not uniquely defined in {path}")
    process = json.loads(json.dumps(matches[0]))
    scheme = json.loads(json.dumps(data["schemes"][process["scheme"]]))
    overrides = process.get("parameter_overrides", {})
    for key, text in overrides.items():
        block = "fixed_parameters" if key in scheme["fixed_parameters"] else "parameters"
        scheme[block][key] = text
    if overrides:
        scheme["parameter_overrides"] = dict(overrides)
    process["scheme_data"] = scheme
    step = CORRECTION_STEP[process["correction"]]
    process["loop_orders"] = {k: process["born_orders"][k] + step[k] for k in ("QCD", "QED")}
    # A joint request ([virt=QCD QED] over several loop sectors) lists every
    # correction reaching its sectors; ``correction`` stays the primary one
    # (the ROW sector of the driver, ``loop_orders``).
    process["corrections"] = list(process.get("corrections") or [process["correction"]])
    if process["corrections"][0] != process["correction"] or len(set(process["corrections"])) != len(
            process["corrections"]) or set(process["corrections"]) - set(CORRECTION_STEP):
        raise ValueError(f"{name}: corrections {process['corrections']} must start with {process['correction']!r}")
    # Requests with several Born amplitude orders (mixed Borns, every squared
    # split order printed by the MadLoop driver) list all of them; ``born_orders``
    # stays the primary one (the ROW line of the driver).
    process["born_orders_all"] = process.get("born_orders_all") or [dict(process["born_orders"])]
    process.setdefault("madloop", {})
    process["madloop"].setdefault("model", scheme["madloop_model"])
    for key, value in (roots or {}).items():
        process["madloop"]["model"] = process["madloop"]["model"].replace("{" + key + "}", str(value))
    return process


MASS_PARAMETERS = {4: "MC", 5: "MB", 6: "MT", 11: "Me", 13: "MM", 15: "MTA", 23: "MZ", 24: "MW", 25: "MH"}
DERIVED_DIGITS = 30  # significant digits of a derived parameter (shared by every provider)


def derived_mw(scheme):
    """Tree-level W mass of an ``alpha_fixed`` scheme (MG5 loop_sm: alpha, G_F
    and MZ inputs), as the decimal text every provider and the point
    construction share: ``DERIVED_DIGITS`` significant digits of
    sqrt(MZ^2/2 + sqrt(MZ^4/4 - alpha pi MZ^2 / (G_F sqrt 2))). Other schemes
    take MW as an input."""
    values = {**scheme["parameters"], **scheme["fixed_parameters"]}
    if "MW" in values:
        return values["MW"]
    if scheme["electroweak_inputs"] != "alpha_fixed":
        raise ValueError(f"no MW input and no tree-level derivation for {scheme['electroweak_inputs']!r}")
    with localcontext() as context:
        context.prec = 60
        pi = Decimal("3.14159265358979323846264338327950288419716939937510582097494459")
        alpha = 1 / Decimal(values["aEWM1"])
        mz2 = Decimal(values["MZ"]) ** 2
        two = Decimal(2)
        mw = (mz2 / 2 + (mz2 ** 2 / 4 - alpha * pi * mz2 / (Decimal(values["Gf"]) * two.sqrt())).sqrt()).sqrt()
        return f"{mw:.{DERIVED_DIGITS}g}"


def masses(process):
    """On-shell masses of the external legs from the scheme parameters: the
    scheme's (exact decimal) value of each mass parameter, MW derived at tree
    level (``derived_mw``) when the scheme does not list it, and 0 for a mass
    the scheme does not list (a parameter the restriction removed)."""
    scheme = process["scheme_data"]
    values = {**scheme["parameters"], **scheme["fixed_parameters"]}
    out = []
    for pdg in process["pdgs"]:
        name = MASS_PARAMETERS.get(abs(pdg))
        if name == "MW" and name not in values:
            out.append(Fraction(derived_mw(scheme)))
        else:
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


def double_pole_factor(process, coupling, correction=None):
    """Universal one-loop double pole D/Born for the declared correction
    (``correction``: one of the process's ``corrections``; default the primary).

    QCD: -alpha_s/(2 pi) * sum of C_F/C_A over massless coloured legs.
    EW: -alpha/(2 pi) * sum of Q^2 over massless charged legs (photon-exchange
    soft-collinear singularity; massive W/Z exchange is IR finite). Uses the
    MadLoop/BLHA C_epsilon normalization.
    """
    correction = correction or process["correction"]
    total = Fraction(0)
    for pdg, mass in zip(process["pdgs"], masses(process)):
        if mass:
            continue
        info = particle(pdg)
        if correction == "QCD":
            total += {3: Fraction(4, 3), 8: Fraction(3), 1: Fraction(0)}[info["colour"]]
        else:
            total += info["charge"] ** 2
    return -float(total) * coupling / (2 * math.pi)
