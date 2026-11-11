# SPDX-License-Identifier: 0BSD
"""The M-LIT loop-induced validation campaign (m-lit PLAN §3.4 LIT-VAL, rules
§4.0 L1-L9, rows §4.1): the run matrix, the runs and data/lit.json.

Usage (worktree root, licence in the environment, the staged native)::

    python tools/loop_benchmark/li_manifest.py rows            # the run matrix
    python tools/loop_benchmark/li_manifest.py run --work-dir W li_gg_h ...
        [--skip-arm LABEL=REASON]  # an unfinished record is resumed
    python tools/loop_benchmark/li_manifest.py crossing --work-dir W  # C1
    python tools/loop_benchmark/li_manifest.py fig7 --work-dir W li_gg_zz=200 ...
    python tools/loop_benchmark/li_manifest.py stress-madloop --work-dir W
    python tools/loop_benchmark/li_manifest.py identity-tirust --work-dir W  # LI-L1, T
    python tools/loop_benchmark/li_manifest.py fabc --work-dir W  # LI-27's f^abc
    python tools/loop_benchmark/li_manifest.py born-l6 --campaign C --lanes-script \
        <lit-tir>/scripts/li_b1.py --ufo U --work-dir W --output D [ROWS]  # LI-B1
    python tools/loop_benchmark/li_manifest.py lit --records W [--output F]

The run matrix is read off lit-ref's manifest
``tools/loop_reference/li_campaign.json`` (rows, checks, tiers, reference
runs, excluded providers), the loop-induced row registry
``docs/performance_reports/loop/data/milestone.json`` (``loop_induced``: the
keys of data/lit.json) and the fixtures ``tests/fixtures/loop/required/li``
(points, parameters, scheme, references); nothing per row is written here.
Every fixture run of a §4.1 row is evaluated once (``run``), through the
public route (``Generator`` -> artifact -> ``Runtime``), at the fixture's
exact decimal points, on BOTH reduction backends (``reduction="ninjars"``,
``reduction="tirust"``; never ``"auto"``; TIRust in the extension's default
configuration: its method choice off before lit-tir-mp, on in binary64
since, ruling (d) lifted 2026-11-08 06:08), in
binary64 and double-double on every run and in arbitrary precision on the
AP run of each tier (the run of the tier with the fewest legs, campaign order
breaking ties), with the binary64 rule's stability checks of the one L6
comparison (``tools/loop_v2_observables_backends.py`` ``checks``: three
generic rotations and the rescaled re-test). Each run writes one record;
``lit`` judges the records by §4.0 (``judge``) and writes data/lit.json in the
LI_VALIDATION schema of ``scripts/build_summary.py`` (rows keyed by the
registry keys) plus the validation-only ids.

Rules (§4.0 with the rulings of the brief, m-lit DECISIONS): L1 binary64 vs
each designated provider <= 1e-5 relative (lax; digits recorded; a fixture
point marked ``l1_caution`` whose provider deviates beyond it is left out of
the L1 verdict and recorded with its binary64 vs double-double deviation,
which the E check judges; a point where binary64's own estimate covers its
deviation beyond it, |b64 - provider| <= 10 E_abs as the E check's rule,
is judged on its double-double value against the provider instead, the
binary64 deviation recorded and judged by E); L2 binary64 <= 1e-9 and
double-double / AP <= 1e-12 against the analytic oracle (targets: a
deviation below ~1e-5 is recorded and reported, never a failure, R5); L3
the amplitude-level finiteness probe (``induced.probe`` at every fixture
point: per (loop order, row) the poles against their estimate on the
row's term floor, x10), both backends in binary64 and double-double (the lanes' public
``finiteness`` ratios, formed with checks only, recorded beside it); L4/W1
the Ward probe epsilon_j -> p_j / E_j at every fixture point on every
external massless gauge-boson leg, both backends in binary64 and
double-double, on the run's probe slice (``ward_probes``: zero widths
outside the complex-mass scheme, Q7), with the generation-time Ward and
Goldstone probes the artifact records (a row no Ward probe reaches is
'recorded'); L5/L1-identity an exact Lorentz transform (rotation and boost with
terminating-decimal entries) leaves |A|^2 within 10 E of the fixture point
in binary64 on both backends (TIRust: ``identity-tirust``) and is recorded in
double-double; LI-27's f^abc part of g g > a g numerically (``fabc``: the
amplitude-basis anchors' asymmetry, the control g g > z g); C1 the crossing
(``crossing``); L6 |T - N| <= 10 max(E_N, E_T) per sector and Laurent
coefficient in binary64 through the one comparison (``_compare``; a TIRust
point whose checked call fails keeps E_N alone, which is conservative),
points TIRust fails closed recorded with its typed reasons (partial), and
within 1e-24 of the sector's largest coefficient in double-double and AP
(``_high_l6``); L6's verdict is the worst of its carriers; TIRust arms (L6,
L3) of an extension before lit-tir-mp (its recorded capability query:
TIRust not at every carrier) 'wait: lit-tir-mp' (the row partial naming
it; ``run --refresh-backend tirust`` re-runs them), a whole-arm refusal by
a later extension is partial with its typed reason;
L7 double-double vs AP <= 1e-24 (target, R5); L8 numerical zeros |A|^2 <=
10 E_abs in binary64 and double-double (Q13; no theorem-based zero), an
exact colour zero (LI-Z1) exactly 0 with the generation's colour record.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import resource
import subprocess
import sys
import time
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from typing import Any

WT = Path(__file__).resolve().parents[2]
if str(WT) not in sys.path:  # run as a script from the worktree root
    sys.path.insert(0, str(WT))

from tools import loop_v2_observables_backends as backends  # noqa: E402

CAMPAIGN = WT / "tools" / "loop_reference" / "li_campaign.json"
MILESTONE = WT / "docs" / "performance_reports" / "loop" / "data" / "milestone.json"
FIXTURES = WT / "tests" / "fixtures" / "loop" / "required" / "li"
LIT = WT / "docs" / "performance_reports" / "loop" / "data" / "lit.json"
# This package's additional fixtures (the same format; each names its §4.1
# row in "li_row"): the P15 point of LI-41, the stress points and LI-Z1's
# exact colour zeros (written from SPEC, ``stress``).
EXTRA = FIXTURES / "lit-val"
# The campaign specification (data): identity row ids, UFO loading options,
# the §4.1 stress points and the derived fixtures.
SPEC = EXTRA / "spec" / "campaign.json"

BACKENDS = ("ninjars", "tirust")
# PLAN §4.1: binary64 and double-double on every row, arbitrary precision on
# one row per tier.
CARRIERS = ("double", "double-double")
ARBITRARY = "arbitrary"
# The AP carrier's digits: enough above double-double's ~32 for L7's 1e-24
# (overridable, ``run --digits``).
DIGITS = 40
# PLAN §4.0 (the campaign's global rules, li_campaign.json "rules"); the x10
# estimate rule (L3-L6, L8) and the 1e-24 of L6 / L7 are the one
# comparison's (tools/loop_v2_observables_backends.py FACTOR, RELATIVE).
LAX = 1e-5  # L1; below it a deviation is never a failure (precision lax, R5)
ANALYTIC_DOUBLE = 1e-9  # L2 binary64
ANALYTIC_HIGH = 1e-12  # L2 double-double / AP (a target, R5)
# The waiting arm of L6 (ruling 17:20 (d), R4: DD/AP TIR is lit-tir-mp's;
# ruling (5): TIRust's binary64 L6 is re-run at its re-pin).
TIR_MP = "lit-tir-mp"
FACTOR = backends.FACTOR  # the x10 estimate rule
CARRIER = float(backends.RELATIVE)  # L6 / L7 in double-double and AP
# The rows outside this package's runs: the TIR unit row and the
# Born-interfered backend row (lit-tir's; LI-B1 recorded from its report),
# the EFT row (lit-eft's run-only check, USER ~14:55) and the observable row
# (lit-obs's both-backends script).
DELEGATED = {
    "LI-B1": "lit-tir",
    "LI-B2": "lit-tir",
    "LI-X1": "lit-eft",
    "LI-O1": "lit-obs",
}
# The tier whose rows are numerical zeros (L8).
ZERO_TIER = "zeros"
# The exact Lorentz transform of the identity check (L5, LI-L1): rotations by
# the 3-4-5 angles about x then y (no coordinate axis, no symmetry of a
# typical point) and a boost along z with gamma = 5/4, gamma beta = 3/4. Every
# entry is a terminating decimal, so the transformed fixture points stay
# exact decimals (the public route reads decimal inputs), exactly on shell
# and momentum conserving.
_ROTATION_X = (Fraction(3, 5), Fraction(4, 5))
_ROTATION_Y = (Fraction(4, 5), Fraction(3, 5))
_BOOST = (Fraction(5, 4), Fraction(3, 4))


# ------------------------------------------------------------- the matrix


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def fixture(name: str) -> dict:
    path = FIXTURES / f"{name}.json"
    return _load(path if path.is_file() else EXTRA / f"{name}.json")


def spec() -> dict:
    """The campaign specification (``SPEC``)."""

    return _load(SPEC)


def _extra_runs(campaign: dict) -> list[dict]:
    """The additional fixtures as reference runs of their rows (their
    providers: those of their reference rows)."""

    out = []
    for path in sorted(EXTRA.glob("*.json")):
        data = _load(path)
        providers = sorted({p for row in data["rows"] for p in row["providers"]})
        out.append(
            (
                data["li_row"],
                {
                    "process": data["name"],
                    "madloop_process": data["madloop_process"],
                    "providers": providers,
                },
            )
        )
    return out


def _norm(process: str) -> str:
    """A MadLoop process without its bracket, order limits and vetoes."""

    text = re.sub(r"\[[^\]]*\]|\S+(?:<=|>=|==|=)\S+", " ", process)
    return " ".join(text.split("/")[0].split())


def _ids(row_id: str) -> list[str]:
    """ "LI-W1/L1/P1/C1/S1" is LI-W1, LI-L1, LI-P1, LI-C1, LI-S1."""

    head, *rest = row_id.split("/")
    prefix = head.rsplit("-", 1)[0] + "-"
    return [head, *(prefix + r for r in rest)]


def registry() -> dict:
    return _load(MILESTONE)["loop_induced"]


def runs(campaign: dict | None = None, reg: dict | None = None) -> list[dict]:
    """The run matrix: one entry per fixture of a §4.1 row's reference runs
    (a fixture several rows list, e.g. li_h_aa of LI-A3 and LI-E1, runs
    once), with every row id, tier and check that lists it (L2 where the run
    designates the analytic oracle), the registry key
    whose ids and process it serves (None: validation-only), the designated
    providers (the run's providers less its excluded ones) and whether it is
    its tier's AP run."""

    campaign = _load(CAMPAIGN) if campaign is None else campaign
    reg = registry() if reg is None else reg
    out: dict[str, dict] = {}
    extra = _extra_runs(campaign)
    for row in campaign["rows"]:
        if row["row"] in DELEGATED:
            continue
        added = [run for row_id, run in extra if row_id == row["row"]]
        for run in [*row.get("runs", []), *added]:
            name = run["process"]
            entry = out.setdefault(
                name,
                {
                    "fixture": name,
                    "process": _norm(run["madloop_process"]),
                    "madloop_process": run["madloop_process"],
                    "ids": [],
                    "tiers": [],
                    "checks": [],
                    "providers": [],
                    "excluded": {},
                    "key": None,
                },
            )
            for i in _ids(row["row"]):
                if i not in entry["ids"]:
                    entry["ids"].append(i)
            if row["tier"] not in entry["tiers"]:
                entry["tiers"].append(row["tier"])
            for check in row["checks"]:
                # L2 compares with the analytic oracle, so it is the check of
                # the runs the row designates one for (the run's providers
                # name "analytic"): a row lists its checks once for all its
                # processes, and its references name AN for some of them only
                # (LI-A4 for h > z a, LI-C1 for g g > a a and a a > a a).
                if check == "L2" and "analytic" not in run.get("providers", []):
                    continue
                if check not in entry["checks"]:
                    entry["checks"].append(check)
            excluded = {**run.get("excluded", {})}
            for provider, note in run.get("provider_value_notes", {}).items():
                if "values_excluded" in note:
                    excluded.setdefault(provider, note["values_excluded"])
            entry["excluded"].update(excluded)
            for provider in run.get("providers", []):
                if provider not in excluded and provider not in entry["providers"]:
                    entry["providers"].append(provider)
    for entry in out.values():
        entry["legs"] = len(fixture(entry["fixture"])["pdgs"])
        keys = [
            r["key"]
            for r in reg["rows"]
            if r.get("process")
            and _norm(r["process"]) == entry["process"]
            and set(r["ids"]) & set(entry["ids"])
        ]
        if len(keys) > 1:
            raise ValueError(f"{entry['fixture']}: registry keys {keys}")
        # A stress fixture is validation-only (no reference, its own checks).
        data = fixture(entry["fixture"])
        stress = data.get("stress")
        entry["key"] = keys[0] if keys and not stress else None
        entry["exact_zero"] = bool(data.get("exact_colour_zero"))
        if stress:
            entry["tiers"] = ["stress"]
            entry["checks"] = ["E", "L6", "L7"]
    ordered = list(out.values())
    ap: dict[str, str] = {}
    for tier in dict.fromkeys(t for e in ordered for t in e["tiers"]):
        # (an exact colour zero has nothing for the AP carrier to resolve)
        members = [e for e in ordered if tier in e["tiers"] and not e["exact_zero"]]
        members = members or [e for e in ordered if tier in e["tiers"]]
        ap[tier] = min(members, key=lambda e: e["legs"])["fixture"]
    for entry in ordered:
        entry["ap"] = sorted(t for t, f in ap.items() if f == entry["fixture"])
    return ordered


def registry_runs(entries: list[dict], reg: dict | None = None) -> dict:
    """Registry key -> its runs (fixture names), every registry row listed
    (no run: an empty list)."""

    reg = registry() if reg is None else reg
    out = {r["key"]: [] for r in reg["rows"]}
    for entry in entries:
        if entry["key"] is not None:
            out[entry["key"]].append(entry["fixture"])
    return out


# ------------------------------------------------------------- generation


def _workspace() -> Path:
    """The loop workspace (reference UFOs): ``PYAMPLICOL_LOOP_WORKSPACE``,
    else the ``workspace`` directory beside the main checkout (the lookup of
    tests/conftest.py and msm_manifest.py; not imported from the latter,
    which writes its manifest when imported)."""

    if configured := os.environ.get("PYAMPLICOL_LOOP_WORKSPACE"):
        return Path(configured)
    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=WT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    main = Path(common).resolve().parent if common else WT
    return main.parent / "workspace"


def _model(data: dict) -> tuple[str, str | None, dict]:
    """(model source, restriction, UFO options) of a fixture's scheme:
    ``{mg5}/models/loop_sm[-<restriction>]`` is the shipped ``loop_sm``,
    ``{reference}/...`` a UFO below the workspace's reference tree, read
    with its loading options (``SPEC`` ``ufo_options``, by its directory
    name: how that model is read, not a row property)."""

    source = data["madloop_model"]
    restriction = data.get("restriction")
    if source.startswith("{mg5}/models/"):
        stem = source.removeprefix("{mg5}/models/")
        name, _, suffix = stem.partition("-")
        return name, restriction or suffix or "default", {}
    if source.startswith("{reference}/"):
        path = _workspace() / "reference" / source.removeprefix("{reference}/")
        return str(path), restriction, spec()["ufo_options"].get(path.name, {})
    raise ValueError(f"unknown model source {source!r}")


def _toml(value: Any) -> str:
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k} = {_toml(v)}" for k, v in value.items()) + "}"
    return json.dumps(value)


def compile_model(data: dict, cache: Path) -> Any:
    """A fixture's model, compiled once into the model cache ``cache``: its
    external parameters filter the fixture's fixed and run-time parameters
    (a parameter the model does not declare, e.g. a width of a particle its
    restriction removed, is not passed, as the loop-induced tests do) and
    its particle names spell the process (by PDG code)."""

    from pyamplicol.models.loading import compile_model_source

    source, restriction, _ = _model(data["scheme_data"])
    return compile_model_source(
        source,
        restriction=restriction or "default",
        require_supported=False,
        cache_dir=cache,
    )


def expression(data: dict, compiled: Any) -> str:
    """The fixture's process in the model's particle names (by PDG code,
    ``pyamplicol_v2.particle_names``)."""

    from tools.loop_benchmark.pyamplicol_v2 import particle_names

    names = particle_names(compiled)
    pdgs, initial = data["pdgs"], data["initial"]
    legs = [names[pdg] for pdg in pdgs]
    return " ".join(legs[:initial]) + " > " + " ".join(legs[initial:])


def run_parameters(data: dict, compiled: Any) -> dict:
    """The fixture's run-time model parameters: its parameters less the
    fixed ones (the generation card's) and those the model does not declare
    (e.g. a width of a particle its restriction removed)."""

    known = set(compiled.parameter_defaults)
    fixed = data["scheme_data"]["fixed_parameters"]
    return {
        k: v
        for k, v in data["scheme_data"]["parameters"].items()
        if k not in fixed and k in known
    }


def card(
    data: dict, output: Path, known: set[str], process: str, name: str = "p"
) -> str:
    """The generation card of a fixture: its model, correction (MadLoop's
    ``[sqrvirt=...]``), order limits (``X=n`` tokens), particle veto (``/
    x``), fixed parameters the model declares (``known``) and mass scheme
    (``complex_mass_scheme``)."""

    madloop = data["madloop_process"]
    correction = re.search(r"\[\s*sqrvirt\s*=\s*(\w+)\s*\]", madloop).group(1)
    limits = {
        m.group(1): int(m.group(2))
        for m in re.finditer(r"(\w+)\s*<?=\s*(\d+)", madloop.split("[")[0])
    }
    veto = madloop.split("[")[0].split("/")[1].split() if "/" in madloop else []
    scheme = data["scheme_data"]
    source, restriction, options = _model(scheme)
    sections: dict[str, dict] = {
        "model": {"source": source},
        "process": {
            "entries": [{"expression": process, "name": name}],
            "loop_coupling_orders": [correction],
        },
        "loop": {"r2_strategy": "model"},
        "loop.preparation": {
            "fixed_parameters": {
                k: v for k, v in scheme["fixed_parameters"].items() if k in known
            }
        },
        # The campaign is validation: the generation-time probes run (off
        # by default since DECISIONS 2026-11-08 22:34 (3)); L4 reads them.
        "generation": {
            "output": str(output),
            "emit_api_bundle": False,
            "loop_induced_probes": True,
        },
        "generation.validation": {"post_build_validation": False},
    }
    if restriction is not None:
        sections["model"]["restriction"] = restriction
    if limits:
        sections["process.max_coupling_orders"] = limits
    if veto:
        sections["generation"]["particle_veto"] = veto
    if scheme.get("complex_mass_scheme"):
        sections["loop.model.scheme"] = {"mass_scheme": "complex-mass"}
    for section, values in options.items():
        sections.setdefault(section, {}).update(values)
    lines = ['action = "generate"']
    for section, values in sections.items():
        lines.append(f"[{section}]")
        for key, value in values.items():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                listed = ", ".join(_toml(v) for v in value)
                lines.append(f"{key} = [{listed}]")
            else:
                lines.append(f"{key} = {_toml(value)}")
    return "\n".join(lines) + "\n"


def generate(
    name: str, work: Path, compiled: Any, data: dict | None = None
) -> tuple[Path, dict]:
    """The fixture's loop-induced artifact through the public ``Generator``
    (kept in ``work / name / "artifact"`` and re-used), with its generation
    record: seconds and the artifact's generation-time probe record
    (``data``: a fixture-shaped record instead of the fixture ``name``)."""

    from pyamplicol.api import Generator, ProcessRequest, ProcessSet
    from pyamplicol.config import resolve_config

    data = fixture(name) if data is None else data
    root = work / name
    output = root / "artifact"
    seconds = None
    if not (output / "artifact.json").is_file():
        root.mkdir(parents=True, exist_ok=True)
        path = root / "card.toml"
        process = expression(data, compiled)
        path.write_text(card(data, output, set(compiled.parameter_defaults), process))
        start = time.perf_counter()
        Generator(resolve_config(path)).generate(
            ProcessSet((ProcessRequest.parse(process, name="p"),)),
            output,
        )
        seconds = time.perf_counter() - start
    manifest = _load(output / "artifact.json")
    (filters,) = (
        record["filters"]
        for record in manifest["extensions"]["generation"]["concrete_processes"]
        if record["id"] == "p"
    )
    return output, {
        "seconds": seconds,
        "peak_gib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20,
        "probes": filters.get("loop_induced_probes"),
        "width_policy": filters.get("conventions", {}).get("width_policy"),
    }


# ------------------------------------------------------------- evaluation


def lorentz(point: list) -> list[list[str]]:
    """The exact transform of the identity check: Rz-free rotation Ry Rx
    then a z boost (``_ROTATION_X``, ``_ROTATION_Y``, ``_BOOST``), as exact
    decimal strings."""

    from pyamplicol.loops.v2.stability import Rotation

    rotation = Rotation.about("y", *_ROTATION_Y) @ Rotation.about("x", *_ROTATION_X)
    gamma, gamma_beta = _BOOST
    out = []
    for e, x, y, z in rotation.apply([[Fraction(c) for c in p] for p in point]):
        out.append([e * gamma + z * gamma_beta, x, y, e * gamma_beta + z * gamma])
    return [[_decimal(c) for c in p] for p in out]


def _decimal(value: Fraction) -> str:
    """An exact terminating decimal string of ``value``."""

    den = value.denominator
    twos = fives = 0
    while den % 2 == 0:
        den //= 2
        twos += 1
    while den % 5 == 0:
        den //= 5
        fives += 1
    if den != 1:
        raise ValueError(f"{value} is not a terminating decimal")
    digits = max(twos, fives)
    with localcontext() as context:
        context.prec = 200
        text = format(
            Decimal(value.numerator) / Decimal(value.denominator), f".{digits}f"
        )
    if Fraction(text) != value:
        raise ValueError(f"inexact decimal of {value}")
    return text


def _text(value: Any) -> str:
    return repr(value) if isinstance(value, float) else str(value)


def _laurent(laurent: Any) -> dict:
    return {
        name: None if getattr(laurent, name) is None else _text(getattr(laurent, name))
        for name in ("finite", "single_pole", "double_pole")
    }


def _estimate(estimate: Any) -> dict | None:
    if estimate is None:
        return None
    return {
        "relative": estimate.relative,
        "finite": estimate.finite,
        "single_pole": estimate.single_pole,
        "double_pole": estimate.double_pole,
        "scale": estimate.scale,
        "absolute": [
            {k: getattr(a, k) for k in ("finite", "single_pole", "double_pole")}
            for a in (estimate.absolute or ())
        ],
        "checks": [list(c) for c in estimate.checks],
    }


_NUMBER = re.compile(r"\d+(\.\d+)?(e-?\d+)?")
_COUNTED = re.compile(r"^(\d+) x ")


def _messages(detail: str) -> list[str]:
    """A lane detail's messages: split between the items of a quoted list
    (``', '``) and at '; ' outside parentheses and braces (a failed point's
    detail lists every failed lane, per frame)."""

    out = []
    for piece in re.split(r"""(?<=['"]), (?=['"])""", detail):
        depth, start = 0, 0
        for i, char in enumerate(piece):
            if char in "({[":
                depth += 1
            elif char in ")}]":
                depth -= 1
            elif depth <= 0 and piece.startswith("; ", i):
                out.append(piece[start:i])
                start = i + 2
        out.append(piece[start:])
    return [m for m in out if m]


def compact_detail(detail: str) -> str:
    """A lane detail with its repeated messages counted: every distinct
    message (numbers masked) once, as its first occurrence, prefixed by its
    count when it repeats ("N x message"). Every reason kind and its count
    stays; the per-lane numbers of the repeats go (a TIRust point that fails
    with checks lists every lane of every frame: tens of MB)."""

    classes: dict[str, list] = {}
    for message in _messages(detail):
        count = 1
        if match := _COUNTED.match(message):
            count, message = int(match.group(1)), message[match.end() :]
        key = _NUMBER.sub("#", message)
        entry = classes.setdefault(key, [0, message])
        entry[0] += count
    return "; ".join(
        message if count == 1 else f"{count} x {message}"
        for count, message in classes.values()
    )


def _call(runtime, points, scales, *, backend, arithmetic, checked, digits) -> dict:
    """One public evaluation: per point the status, typed detail, reduction
    record, finiteness ratio, values and estimate; a typed refusal of the
    whole call (``ReductionUnavailable``) is recorded as such."""

    from pyamplicol.loops.v2.reduction import ReductionUnavailable
    from tools.loop_v2_observables_backends import checks

    options: dict[str, Any] = {
        "mu_r2": scales,
        "reduction": backend,
        "arithmetic": arithmetic,
        "poles": "all",
        "on_failure": "return",
        "stability_checks": checks() if checked else None,
    }
    if arithmetic == ARBITRARY:
        options["precision"] = digits
    start = time.perf_counter()
    try:
        result = runtime.evaluate(points, **options)
    except ReductionUnavailable as error:
        return {"refused": f"{type(error).__name__}: {error}"}
    seconds = time.perf_counter() - start
    stability = result.stability or [None] * len(result.values)
    out = []
    for lane, values, estimate in zip(
        result.diagnostics, result.values, stability, strict=True
    ):
        reduction = lane.reduction
        out.append(
            {
                "status": lane.status,
                "detail": compact_detail(lane.detail),
                "reduction": None
                if reduction is None
                else [reduction.requested, reduction.effective, reduction.reason],
                "finiteness": lane.finiteness,
                "values": [_laurent(s) for s in values] if lane.valid else None,
                "estimate": _estimate(estimate) if lane.valid else None,
            }
        )
    return {"seconds": seconds, "points": out}


def evaluate(
    name: str,
    work: Path,
    *,
    ap: bool,
    digits: int = DIGITS,
    identity: bool = True,
    write: Any = None,
    previous: dict | None = None,
    skip: dict[str, str] | None = None,
    high_checked: bool = True,
) -> dict:
    """Every arm of one fixture run (module docstring), cheapest first:
    binary64 on both backends with and without the checks, double-double
    with the checks (TIRust's typed refusal recorded), the identity check's
    transformed points (binary64 checked, double-double) on NinjaRS, and AP
    without checks on an AP run. ``write`` (if given) receives the record
    after every arm (``complete`` False until the last). ``previous`` (an
    unfinished record of this run at the same native) is resumed: its arms
    and generation record are kept, not recomputed. ``skip`` maps an arm
    label (``l3/<probe label>`` for an L3 probe arm) to the reason it is not
    run; the arm is recorded as ``{"not_run": reason}``. ``high_checked``
    False runs the double-double arms without the checks (``.../plain``: the
    value without its estimate, about a fifth of the cost)."""

    skip = skip or {}

    from pyamplicol import Runtime

    data = fixture(name)
    compiled = compile_model(data, work / "model-cache")
    artifact, generation = generate(name, work, compiled)
    parameters = run_parameters(data, compiled)
    runtime = Runtime.load(artifact, process="p", model_parameters=parameters)
    points = data["points"]
    scales = [_decimal(Fraction(mu) ** 2) for mu in data["mu_r"]]
    carriers = tuple(data.get("carriers", CARRIERS))
    exact = set(CARRIERS) <= set(carriers)
    identity = identity and exact
    ap = (ap or ARBITRARY in carriers) and exact
    carriers = tuple(c for c in carriers if c != ARBITRARY)
    transformed = [lorentz(p) for p in points] if identity else []
    record: dict[str, Any] = {
        "fixture": name,
        "revision": _revision(),
        "native": _native(),
        "python_symbolica": _symbolica(),
        "reduction_backends": _capability(),
        "generation": generation,
        "digits": digits if ap else None,
        "transformed_points": transformed,
        "arms": {},
        "complete": False,
    }
    if previous is not None:
        # The kept arms' provenance is the previous record's (None where it
        # predates the field: never the staged native's by default).
        for key in RECORD_PROVENANCE:
            record[key] = previous.get(key)
        for key in ("generation", "revision", "refreshed", "native_digest"):
            if key in previous:
                record[key] = previous[key]
        record["arms"] = dict(previous["arms"])
        record["resumed_at"] = _revision()
    plan: list[tuple[str, str, str, bool, list]] = []
    for arithmetic in carriers:
        for backend in BACKENDS:
            for checked in (False, True) if arithmetic == "double" else (high_checked,):
                tag = "checked" if checked else "plain"
                plan.append(
                    (
                        f"{backend}/{arithmetic}/{tag}",
                        backend,
                        arithmetic,
                        checked,
                        points,
                    )
                )
    if identity:
        for arithmetic in CARRIERS:
            plan.append(
                (
                    f"identity/ninjars/{arithmetic}",
                    "ninjars",
                    arithmetic,
                    arithmetic == "double",
                    transformed,
                )
            )
    if ap:
        for backend in BACKENDS:
            plan.append(
                (f"{backend}/{ARBITRARY}/plain", backend, ARBITRARY, False, points)
            )
    for label, backend, arithmetic, checked, inputs in plan:
        if label in record["arms"]:
            continue
        record["arms"][label] = (
            {"not_run": skip[label]}
            if label in skip
            else _call(
                runtime,
                inputs,
                scales,
                backend=backend,
                arithmetic=arithmetic,
                checked=checked,
                digits=digits,
            )
        )
        record["peak_gib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20
        if write is not None:
            write(record)
    record["l3_probes"] = finiteness_probes(
        runtime,
        data,
        parameters,
        carriers,
        skip=skip,
        previous=(previous or {}).get("l3_probes"),
    )
    if write is not None:
        write(record)
    record["ward_probes"] = ward_probes(
        name,
        work,
        data,
        compiled,
        parameters,
        carriers,
        skip=skip,
        previous=(previous or {}).get("ward_probes"),
        write=None if write is None else lambda w: write({**record, "ward_probes": w}),
    )
    record["complete"] = True
    if write is not None:
        write(record)
    return record


# The L3 probe arms: (backend, carrier): both backends in binary64 and
# double-double (§4.0 L3; TIRust's double-double since lit-tir-mp: an older
# extension's typed refusal is recorded per point).
PROBES = tuple((b, c) for b in BACKENDS for c in ("double", "double_double"))


def run_skips(name: str) -> tuple[dict[str, str], bool]:
    """The arms SPEC's ``skips`` records for run ``name`` (label -> the
    measured reason it is not taken) and whether its double-double arms run
    without the checks (``high_plain``)."""

    entry = spec().get("skips", {}).get(name, {})
    return dict(entry.get("arms", {})), bool(entry.get("high_plain"))


def skip_arms(specs: list[str]) -> dict[str, str]:
    """``LABEL=REASON`` arguments (``run --skip-arm``) as a mapping."""

    out = {}
    for spec in specs:
        label, sep, reason = spec.partition("=")
        if not sep or not label or not reason:
            raise ValueError(f"--skip-arm expects LABEL=REASON, got {spec!r}")
        out[label] = reason
    return out


def finiteness_probes(
    runtime: Any,
    data: dict,
    parameters: dict,
    carriers: tuple = CARRIERS,
    skip: dict[str, str] | None = None,
    previous: dict | None = None,
) -> dict:
    """L3 at every fixture point: the amplitude-level finiteness probe
    (``induced.probe`` on the loaded artifact's native executor, its
    calibrated checks) per backend and carrier (``PROBES``); a point TIRust
    fails closed is recorded with its typed reason; a probe arm named in
    ``skip`` (``l3/<label>``) is recorded as ``{"not_run": reason}``; a
    probe arm of ``previous`` (a resumed record's) is kept."""

    from pyamplicol.loops.v2 import induced
    from pyamplicol.loops.v2.assemble import Precision
    from pyamplicol.loops.v2.reduction import running

    # (the loaded runtime's own native executor: the public Runtime has no
    # accessor for it, and a second executor from the stored artifact,
    # ``artifact.executor(inputs="native")``, would hold the native plans
    # twice on the six-leg rows; a test-side developer reach, like
    # tests/unit/test_correlator_runtime.py's)
    executor = runtime._backend._executor
    out: dict[str, list] = {}
    for backend, carrier in PROBES:
        if carrier.replace("_", "-") not in carriers:
            continue
        label = f"{backend}/{carrier.replace('_', '-')}"
        if previous and label in previous:
            out[label] = previous[label]
            continue
        if f"l3/{label}" in (skip or {}):
            out[label] = {"not_run": skip[f"l3/{label}"]}
            continue
        rows = []
        for point, mu in zip(data["points"], data["mu_r"], strict=True):
            try:
                with running(backend):
                    result = induced.probe(
                        executor,
                        point,
                        Fraction(mu) ** 2,
                        parameters=parameters,
                        precision=getattr(Precision, carrier)(),
                    )
                rows.append({"worst": result.worst, "passed": result.passed})
            except Exception as error:  # a typed failure of the arm, recorded
                rows.append(
                    {"error": compact_detail(f"{type(error).__name__}: {error}")}
                )
        out[label] = rows
    return out


def ward_probes(
    name: str,
    work: Path,
    data: dict,
    compiled: Any,
    parameters: dict,
    carriers: tuple = CARRIERS,
    skip: dict[str, str] | None = None,
    previous: dict | None = None,
    write: Any = None,
) -> dict:
    """L4 at every fixture point: the amplitude-level Ward probe epsilon_j
    -> p_j / E_j (``ward.gauge_ward``, c = 1; the amplitude is linear in it)
    on EVERY external massless gauge-boson leg (``ward.gauge_legs``), per
    backend and carrier (``PROBES``), on the run's probe slice: the stored
    artifact's own request (``artifact.request_from_record``) with the
    widths of the generation-time probe (``ew_policy.probe_widths``: zero
    outside the complex-mass scheme, Q7) on the full tree kernels
    (``ward.ward_slice``), each probe within ten times its own estimate
    (``induced.probes``: the calibrated checks, the physical amplitude's
    term floor). Massive vectors are the generation-time Goldstone probe's
    ('t Hooft-Feynman-gauge requests) and the cited both-gauges equality
    (§4.0 L4). A probe arm named in ``skip`` (``ward/<label>``) is recorded
    as ``{"not_run": reason}``; a resumed record's arms are kept; ``write``
    (if given) receives the record after every arm; an exact colour zero
    has nothing to probe."""

    from dataclasses import replace

    from pyamplicol.loops.native import load_loop_native
    from pyamplicol.loops.v2 import induced
    from pyamplicol.loops.v2.artifact import request_from_record
    from pyamplicol.loops.v2.assemble import Precision
    from pyamplicol.loops.v2.ew_policy import probe_widths
    from pyamplicol.loops.v2.plan_export import NativeExecutor
    from pyamplicol.loops.v2.reduction import running
    from pyamplicol.loops.v2.ward import gauge_legs, gauge_ward, ward_slice

    if data.get("exact_colour_zero"):
        return {"exact_colour_zero": True, "arms": {}}
    previous = previous or {}
    execution = _load(work / name / "artifact" / "processes" / "p" / "execution.json")
    request = request_from_record(execution["request"])
    fixed, zeroed = probe_widths(compiled, request.fixed_parameters)
    labels = [
        f"{backend}/{carrier.replace('_', '-')}"
        for backend, carrier in PROBES
        if carrier.replace("_", "-") in carriers
    ]
    if all(label in previous.get("arms", {}) for label in labels):
        return previous
    start = time.perf_counter()
    target = ward_slice(
        compiled, replace(request, fixed_parameters=fixed), load_loop_native()
    )
    legs = list(gauge_legs(target))
    out: dict[str, Any] = {
        "legs": legs,
        "zeroed_widths": list(zeroed),
        "slice_seconds": time.perf_counter() - start,
        "native": _native(),
        "arms": dict(previous.get("arms", {})),
    }
    if not legs:
        return out
    executor = NativeExecutor(target, forward=False, inputs="native")
    values = {k: v for k, v in parameters.items() if k not in fixed}
    for backend, carrier in PROBES:
        label = f"{backend}/{carrier.replace('_', '-')}"
        if label not in labels or label in out["arms"]:
            continue
        if f"ward/{label}" in (skip or {}):
            out["arms"][label] = {"not_run": skip[f"ward/{label}"]}
            continue
        rows = []
        for point, mu in zip(data["points"], data["mu_r"], strict=True):
            try:
                with running(backend):
                    found = induced.probes(
                        executor,
                        point,
                        Fraction(mu) ** 2,
                        [gauge_ward(leg, (1, 0), point) for leg in legs],
                        parameters=values,
                        precision=getattr(Precision, carrier)(),
                    )
                rows.append(
                    {
                        "worst": {
                            str(leg): r.worst
                            for leg, r in zip(legs, found, strict=True)
                        },
                        "passed": all(r.passed for r in found),
                    }
                )
            except Exception as error:  # a typed failure of the arm, recorded
                rows.append(
                    {"error": compact_detail(f"{type(error).__name__}: {error}")}
                )
        out["arms"][label] = rows
        if write is not None:
            write(out)
    return out


def _revision() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=WT, capture_output=True, text=True
    ).stdout.strip()


def _native() -> dict | None:
    """The staged native extension: its sha256 (what a resume compares), and
    the build directory's name and native-input digest from the staging
    record (``build_loop_native.py stage``; no absolute path)."""

    import hashlib

    staged = sorted((WT / "src" / "pyamplicol").glob("_rusticol*.so"))
    if not staged:
        return None
    out: dict[str, Any] = {
        "extension_sha256": hashlib.sha256(staged[0].read_bytes()).hexdigest()
    }
    info = WT / ".artifacts" / "source-runtime" / "_build_info.json"
    if info.is_file():
        data = _load(info)
        out["build"] = Path(data["native_build"]["directory"]).name
        out["inputs_digest"] = data["native_build_inputs_sha256"]
    return out


def _symbolica() -> str | None:
    """The Python Symbolica in use: its version and the name of the
    directory holding it (no absolute path)."""

    try:
        import symbolica
    except ImportError:
        return None
    where = Path(symbolica.__file__).resolve().parents[1].name
    return f"symbolica {getattr(symbolica, '__version__', '?')} ({where})"


_SLICE_LINE: list[set[str]] = []


def _engine_slice(revision: str) -> str:
    """The integration-branch commit a record's revision builds on: the
    newest commit of work/v2-slice's first-parent line among the
    revision's ancestors (the engine it ran, this package changing no engine
    code; unlike a merge base it stays the same after the package's own
    integration), else the revision itself.

    It reads the LOCAL branch work/v2-slice of the checkout (memoised per
    process in ``_SLICE_LINE``): regenerating lit.json in a clone without
    that branch, or with it at another tip, names bare revisions or other
    slice commits, so regenerate in the integration worktree's repository."""

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=WT, capture_output=True, text=True, check=False
        ).stdout

    if not _SLICE_LINE:
        _SLICE_LINE.append(
            set(git("rev-list", "--first-parent", "work/v2-slice").split())
        )
    for commit in git("rev-list", revision).split():
        if commit in _SLICE_LINE[0]:
            return commit[:9]
    return revision[:9]


def provenance(records: dict[str, dict]) -> dict:
    """Where the records come from: the engine slice of each record's
    revision (and of its resumption), the staged native and the Python
    Symbolica each new record names (counts)."""

    out: dict[str, dict] = {
        "engine_slice": {},
        "native": {},
        "python_symbolica": {},
        "refreshed": {},
    }
    for record in records.values():
        refreshed = record.get("refreshed", [])
        revisions = {record.get("revision"), record.get("resumed_at")}
        revisions |= {e.get("revision") for e in refreshed}
        for revision in revisions - {None, ""}:
            key = _engine_slice(revision)
            out["engine_slice"][key] = out["engine_slice"].get(key, 0) + 1
        native = (record.get("native") or {}).get("build")
        if native is None and record.get("revision"):
            # A record of the format before it named its native: the engine
            # slice it ran (the campaign source names that slice's native).
            native = (
                f"engine slice {_engine_slice(record['revision'])} "
                "(native not recorded by the record)"
            )
        native = native or "not recorded"
        out["native"][native] = out["native"].get(native, 0) + 1
        python = record.get("python_symbolica") or "not recorded"
        out["python_symbolica"][python] = out["python_symbolica"].get(python, 0) + 1
        for entry in refreshed:
            key = (
                f"{entry['backend']} arms at "
                f"{(entry.get('native') or {}).get('build') or 'not recorded'} "
                f"({entry.get('python_symbolica') or 'Python Symbolica not recorded'})"
            )
            out["refreshed"][key] = out["refreshed"].get(key, 0) + 1
    return out


def _capability() -> dict[str, list[str]] | None:
    """The carriers each reduction backend of the staged extension serves
    (its capability query, ``reduction.native_backends``), None without
    the extension."""

    from pyamplicol.api.errors import DependencyError
    from pyamplicol.loops.native import load_loop_native
    from pyamplicol.loops.v2.reduction import native_backends

    try:
        native = load_loop_native()
    except DependencyError:
        return None
    return {k: sorted(v) for k, v in sorted(native_backends(native).items())}


# A record's provenance of its arms (a resumed record keeps its own).
RECORD_PROVENANCE = ("native", "python_symbolica", "reduction_backends")


def _same_native(record: dict, backend: str | None = None) -> bool:
    """Whether ``record`` was taken with the staged extension, or (any
    backend, or ``backend``) refreshed with it (a record without the
    extension's hash is not)."""

    current = (_native() or {}).get("extension_sha256")
    natives = [record.get("native") or {}] + [
        entry.get("native") or {}
        for entry in record.get("refreshed", [])
        if backend is None or entry.get("backend") == backend
    ]
    return bool(current) and any(n.get("extension_sha256") == current for n in natives)


def tirust_carriers(record: dict) -> frozenset[str] | None:
    """The carriers TIRust served in the extension that took ``record``'s
    TIRust arms (its latest TIRust refresh, else the record's own capability
    query); None where the record predates the recorded query."""

    for entry in reversed(record.get("refreshed", [])):
        if entry.get("backend") == "tirust":
            capability = entry.get("reduction_backends")
            break
    else:
        capability = record.get("reduction_backends")
    return None if capability is None else frozenset(capability.get("tirust", ()))


# ------------------------------------------------------------- the rules


def _dec(text: str | None) -> Decimal | None:
    return None if text is None else Decimal(text)


def _rel(value: Any, reference: Any) -> float:
    with localcontext() as context:
        context.prec = 80
        v, r = Decimal(str(value)), Decimal(str(reference))
        if r == 0:
            return 0.0 if v == 0 else math.inf
        return float(abs(v / r - 1))


def _total(values: list | None) -> Decimal | None:
    """The finite |A|^2 summed over sectors."""

    if values is None:
        return None
    with localcontext() as context:
        context.prec = 80
        return sum((Decimal(s["finite"]) for s in values), Decimal(0))


def _abs_finite(estimate: dict | None) -> float | None:
    if estimate is None or not estimate["absolute"]:
        return None
    return sum(a["finite"] for a in estimate["absolute"])


def _pole_estimate(estimate: dict | None) -> float | None:
    """The estimate of the poles against the term floor (a loop-induced
    estimate's pole entries are E / S, ``VirtualStabilityEstimate``)."""

    if estimate is None:
        return None
    poles = [estimate[k] for k in ("single_pole", "double_pole") if estimate[k]]
    return max(poles, default=None)


def _verdict(strict: bool, lax: bool) -> str:
    """'pass' (the rule), 'pass (lax)' (beyond the target, below ~1e-5:
    recorded and reported, R5) or 'fail'."""

    return "pass" if strict else ("pass (lax)" if lax else "fail")


def _worst(statuses: list[str]) -> str:
    order = [
        "fail",
        "estimate miss",
        "reference defect",
        "partial",
        "waits",
        "not run",
        "recorded",
        "pass (lax)",
        "pass",
    ]
    for s in order:
        for status in statuses:
            if status.split(":")[0] == s:
                return status
    return "not run"


def _served(arm: dict | None) -> list[bool]:
    if not arm or "points" not in arm:
        return []
    return [p["status"] == "success" for p in arm["points"]]


def _reasons(arm: dict) -> dict[str, int]:
    """The typed reasons of an arm's failed points: per distinct message
    (numbers masked) its count over the points' lanes."""

    out: dict[str, int] = {}
    for p in arm.get("points", []):
        if p["status"] != "success":
            for message in _messages(compact_detail(p["detail"])):
                count = 1
                if match := _COUNTED.match(message):
                    count, message = int(match.group(1)), message[match.end() :]
                key = _NUMBER.sub("#", message)
                out[key] = out.get(key, 0) + count
    return out


def _counted(reasons) -> dict[str, int]:
    """Distinct reasons with their counts (numbers masked)."""

    out: dict[str, int] = {}
    for reason in reasons:
        key = _NUMBER.sub("#", reason)
        out[key] = out.get(key, 0) + 1
    return out


def _switched(arm: dict | None, backend: str) -> list:
    """The served points of ``arm`` whose effective backend is not
    ``backend`` (the one comparison's ``_effective`` guard on a record: a
    silent backend switch is never compared)."""

    if not arm or "points" not in arm:
        return []
    return [
        [p, point["reduction"]]
        for p, point in enumerate(arm["points"])
        if point["status"] == "success"
        and point.get("reduction") is not None
        and point["reduction"][1] != backend
    ]


def high_arm(arms: dict, backend: str, carrier: str = "double-double") -> dict:
    """A backend's arm in a high-precision carrier: the checked one, or the
    plain one of a run made with ``--high-plain`` ({} if neither ran)."""

    for tag in ("checked", "plain"):
        arm = arms.get(f"{backend}/{carrier}/{tag}")
        if arm is not None and "not_run" not in arm:
            return {**arm, "arm": tag}
    return arms.get(f"{backend}/{carrier}/checked", {})


def identity_tirust(name: str, work: Path, record: dict) -> dict:
    """LI-L1 on TIRust (§4.1: the identity rows' backends N, T): the
    record's transformed points (``lorentz``, the exact rotation plus boost)
    and its fixture points on TIRust in binary64 with the checks, at the
    staged native, and whether the fixture-point arm reproduces the
    record's TIRust binary64 checked arm bitwise (the record's TIRust arms
    may be of another native)."""

    from pyamplicol import Runtime

    data = fixture(name)
    compiled = compile_model(data, work / "model-cache")
    artifact, _generation = generate(name, work, compiled)
    runtime = Runtime.load(
        artifact, process="p", model_parameters=run_parameters(data, compiled)
    )
    scales = [_decimal(Fraction(mu) ** 2) for mu in data["mu_r"]]
    arms = {
        label: _call(
            runtime,
            inputs,
            scales,
            backend="tirust",
            arithmetic="double",
            checked=True,
            digits=DIGITS,
        )
        for label, inputs in (
            ("fixture", data["points"]),
            ("transformed", record["transformed_points"]),
        )
    }
    recorded = record["arms"]["tirust/double/checked"]
    return {
        **arms,
        "native": _native(),
        "revision": _revision(),
        "bitwise_record": [p.get("values") for p in arms["fixture"].get("points", [])]
        == [p.get("values") for p in recorded.get("points", [])],
    }


def _identity_l5(fixture_arm: dict, transformed: dict, zero: bool) -> dict:
    """L5 of one backend: its binary64 value at the transformed points
    within 10 E of its value at the fixture points (E its estimate there);
    a numerical zero (ZERO_TIER) is two roundings, recorded (L8 judges it);
    points the backend fails closed are counted with their typed reasons
    (partial)."""

    ratios, failed = [], 0
    for a, b in zip(
        fixture_arm.get("points", []), transformed.get("points", []), strict=True
    ):
        if a["status"] != "success" or b["status"] != "success":
            failed += 1
            continue
        e = _abs_finite(a["estimate"]) or 0.0
        diff = abs(float(_total(a["values"]) - _total(b["values"])))
        ratios.append(diff / (FACTOR * e) if e else (0.0 if not diff else math.inf))
    worst = max(ratios, default=None)
    if worst is None:
        status = "partial" if failed else "not run"
    elif zero:
        status = "recorded"
    else:
        status = "pass" if worst <= 1 else "estimate miss"
        if failed and status == "pass":
            status = "partial"
    return {
        "status": status,
        "worst_ratio_to_10E": worst,
        "served": len(ratios),
        "failed_points": failed,
        "reasons": _counted(
            key
            for arm in (fixture_arm, transformed)
            for key, n in _reasons(arm).items()
            for _ in range(n)
        ),
    }


def _probe_carriers(probes: dict) -> dict[str, str] | str | None:
    """The carrier that decided each generation-time probe (binary64, or
    double-double after a fallback: ``induced.generation_probes``); a record
    before the per-probe carriers names its one carrier."""

    if "probes" not in probes:
        return probes.get("precision")
    return {
        entry["probe"] + (f" (leg {entry['leg']})" if "leg" in entry else ""): (
            entry["carrier"]
        )
        for entry in probes["probes"]
    }


def judge(record: dict, entry: dict) -> dict:
    """The §4.0 checks of one run record (module docstring); per check its
    status and figures."""

    from tools.loop_v2_observables_backends import _compare

    data = fixture(record["fixture"])
    arms = record["arms"]
    n64, n64c = arms["ninjars/double/plain"], arms["ninjars/double/checked"]
    t64, t64c = arms["tirust/double/plain"], arms["tirust/double/checked"]
    # (a binary64-only fixture, ``carriers``, has no double-double arms)
    ndd = high_arm(arms, "ninjars")
    tdd = high_arm(arms, "tirust")
    nap = arms.get(f"ninjars/{ARBITRARY}/plain")
    # The carriers TIRust served when its arms were taken; arms of an
    # extension that did not serve it at every campaign carrier (or before
    # the recorded capability query) predate lit-tir-mp (TIRust at every
    # carrier) and wait on it (ruling (5)).
    tir_carriers = tirust_carriers(record)
    stale = tir_carriers is None or not {*CARRIERS, ARBITRARY} <= tir_carriers
    out: dict[str, Any] = {}
    count = len(data["points"])
    n_served = _served(n64c)
    out["points"] = count
    if not all(n_served) or not all(_served(n64)):
        # NinjaRS fails points closed (typed; never a value): partial.
        out["N"] = {
            "status": "partial",
            "failed": count - sum(_served(n64)),
            "failed_checked": count - sum(n_served),
            "reasons": _reasons(n64c),
        }
    # L1 providers (binary64, NinjaRS; TIRust on the points it serves).
    refs: dict[str, float] = {}
    caution: list[dict] = []
    tir_refs: dict[str, float] = {}
    # A point where binary64 is known to its estimate only (the E check's x10
    # rule covers its deviation from the provider, beyond LAX): L1 judges the
    # double-double value there (the carrier E judges binary64 against).
    covered: list[dict] = []
    high_refs: dict[str, float] = {}
    n_dd_served = _served(ndd)
    for p, row in enumerate(data["rows"]):
        if p >= count:
            break
        value = _total(n64["points"][p]["values"])
        if value is None:
            continue  # failed closed (N)
        tvalue = _total(t64["points"][p]["values"]) if _served(t64)[p] else None
        for provider in entry["providers"]:
            if provider == "analytic" or provider not in row["providers"]:
                continue
            reference = row["providers"][provider]["value"]
            dev = _rel(value, reference)
            if row.get("l1_caution") and dev > LAX:
                served = _served(ndd)
                dd = (
                    _total(ndd["points"][p]["values"])
                    if p < len(served) and served[p]
                    else None
                )
                caution.append(
                    {
                        "point": p,
                        "provider": provider,
                        "deviation": dev,
                        "binary64_vs_double_double": None
                        if dd is None
                        else _rel(value, dd),
                    }
                )
                continue
            estimate = (
                _abs_finite(n64c["points"][p]["estimate"]) if n_served[p] else None
            )
            if (
                dev > LAX
                and estimate
                and p < len(n_dd_served)
                and n_dd_served[p]
                and abs(float(value) - float(reference)) <= FACTOR * estimate
            ):
                dd_dev = _rel(_total(ndd["points"][p]["values"]), reference)
                covered.append(
                    {
                        "point": p,
                        "provider": provider,
                        "deviation": dev,
                        "deviation_over_10E": abs(float(value) - float(reference))
                        / (FACTOR * estimate),
                        "double_double_deviation": dd_dev,
                    }
                )
                high_refs[provider] = max(high_refs.get(provider, 0.0), dd_dev)
                continue
            refs[provider] = max(refs.get(provider, 0.0), dev)
            if tvalue is not None:
                tir_refs[provider] = max(
                    tir_refs.get(provider, 0.0), _rel(tvalue, reference)
                )
    zero = ZERO_TIER in entry["tiers"]
    if zero:
        # A numerical zero: the providers' values are their own rounding,
        # no relative reference (L8 is the rule); recorded absolutely.
        out["L1"] = {
            "status": "recorded",
            "providers_max_abs": {
                provider: max(
                    abs(row["providers"][provider]["value"])
                    for row in data["rows"][:count]
                    if provider in row["providers"]
                )
                for provider in entry["providers"]
                if provider != "analytic"
            },
        }
        refs = {}
    elif refs or high_refs or "L1" in entry["checks"]:
        worst = max([*refs.values(), *high_refs.values()], default=None)
        out["L1"] = {
            "status": "not run" if worst is None else _verdict(worst <= LAX, False),
            "max_relative": dict(refs),
            "tirust_max_relative": tir_refs,
            "caution_points": caution,
        }
        if covered:
            out["L1"]["estimate_covered_points"] = covered
            out["L1"]["double_double_max_relative"] = high_refs
    # L2 analytic (binary64 / double-double / AP).
    analytic = [
        row["providers"]["analytic"]["decimal"]
        for row in data["rows"][:count]
        if "analytic" in row["providers"]
    ]
    if len(analytic) == count:
        l2: dict[str, Any] = {}
        statuses = []
        for carrier, arm, target in (
            ("double", n64, ANALYTIC_DOUBLE),
            ("double-double", ndd, ANALYTIC_HIGH),
            (ARBITRARY, nap, ANALYTIC_HIGH),
        ):
            if arm is None or "points" not in arm:
                continue
            devs = [
                _rel(_total(pt["values"]), a)
                for pt, a in zip(arm["points"], analytic, strict=True)
                if pt["values"] is not None
            ]
            if devs:
                l2[carrier] = max(devs)
                statuses.append(_verdict(max(devs) <= target, max(devs) <= LAX))
        out["L2"] = {"status": _worst(statuses), "max_relative": l2}
        refs["analytic"] = l2.get("double")
    # L3 finiteness: the amplitude-level probe at every fixture point
    # (``induced.probe``: per (loop order, row) the poles against their
    # estimate on the row's term floor, the x10 rule of the generation-time
    # probe), both backends in binary64 and double-double (``PROBES``); the
    # lanes' public finiteness ratios are recorded beside it.
    l3: dict[str, Any] = {}
    statuses = []
    for label, probe in (record.get("l3_probes") or {}).items():
        if isinstance(probe, dict):
            # a probe arm not run (``skip``): recorded with its reason, the
            # check covers the others only (partial)
            l3[label] = {"status": "not run", "reason": probe["not_run"]}
            statuses.append("partial")
            continue
        worst = [x["worst"] for x in probe if "worst" in x]
        served = len(worst)
        if not worst:
            status = "partial" if label.startswith("tirust") else "not run"
        elif max(worst) <= FACTOR:
            status = "pass" if served == count else "partial"
        else:
            status = "fail"
        l3[label] = {
            "status": status,
            "worst_ratio": max(worst, default=None),
            "served": served,
            "of": count,
            "failed": _counted(x["error"] for x in probe if "error" in x),
        }
        statuses.append(status)
    if stale:
        # TIRust's probe arms of an extension before lit-tir-mp (or absent,
        # for a carrier the run has) wait on its re-run; a failure stays.
        for carrier in (c for b, c in PROBES if b == "tirust"):
            label = f"tirust/{carrier.replace('_', '-')}"
            if label in l3:
                l3[label]["status"] = _worst([l3[label]["status"], f"waits: {TIR_MP}"])
            elif carrier.replace("_", "-") in data.get("carriers", CARRIERS):
                l3[label] = {"status": f"waits: {TIR_MP}"}
            else:
                continue
            statuses.append(l3[label]["status"])
            l3["waits_on"] = TIR_MP
    if not l3:
        statuses.append("not run")
    l3["lane_finiteness"] = {
        label: max(
            (
                pt["finiteness"]
                for pt in arm.get("points", [])
                if pt["finiteness"] is not None
            ),
            default=None,
        )
        for label, arm in (
            ("ninjars/double", n64c),
            ("ninjars/double-double", ndd),
            ("tirust/double", t64c),
            ("tirust/double-double", tdd),
        )
    }
    # The necessary-only cross-check at the |A|^2 level: every computed pole
    # of the sum within ten times its absolute estimate.
    poles = []
    for arm in (n64c, ndd, t64c, tdd):
        for pt in arm.get("points", []):
            if pt["status"] != "success" or pt["estimate"] is None:
                continue
            for sector, error in zip(
                pt["values"], pt["estimate"]["absolute"], strict=True
            ):
                for k in ("single_pole", "double_pole"):
                    if sector[k] is not None and error[k]:
                        poles.append(
                            abs(float(_complex(sector[k])[0])) / (FACTOR * error[k])
                        )
    l3["poles_over_10E"] = max(poles, default=None)
    out["L3"] = {"status": _worst(statuses), **l3}
    # L4 / W1: the Ward probes at every fixture point on every external
    # massless gauge-boson leg (``ward_probes``: both backends, binary64 and
    # double-double, on the probe slice) and the generation-time probes
    # (double-double at one point: finiteness, Ward, the Goldstone probe of
    # massive vectors where the artifact records it); its verdict is the
    # worst of them (TIRust's arms of an extension before lit-tir-mp wait).
    probes = record["generation"]["probes"] or {}
    # A record without the probes ("status": "off", or none) is "not run",
    # never a pass; a record before the status field ran them.
    ran = probes.get("status", "run") == "run"
    generation = {
        k: probes[k] for k in ("finiteness", "ward", "goldstone") if k in probes and ran
    }
    wards = record.get("ward_probes")
    l4: dict[str, Any] = {}
    statuses = []
    if generation:
        # the verdict reads the Ward-type probes (the finiteness one is
        # L3's, recorded here as the artifact has it), legs probed or a
        # failure recorded
        gauge = [
            v
            for k, v in generation.items()
            if k != "finiteness" and (v.get("legs") or not v.get("passed", True))
        ]
        passed = all(v.get("passed") for v in generation.values())
        if gauge or not passed:
            statuses.append("pass" if passed else "fail")
        l4["generation"] = {
            "status": "pass" if passed else "fail",
            "probes": generation,
            "carrier": _probe_carriers(probes),
            "widths": probes.get("widths"),
        }
    elif not probes.get("exact_colour_zero"):
        l4["generation"] = {
            "status": "not run",
            "reason": "the artifact records no generation-time probes "
            "(generation.loop_induced_probes off)",
        }
    if probes.get("exact_colour_zero") or (wards or {}).get("exact_colour_zero"):
        statuses.append("recorded")
        l4["fixture_points"] = {
            "status": "recorded",
            "reason": "an exact colour zero has nothing to probe",
        }
    elif wards is None:
        statuses.append("partial")
        l4["fixture_points"] = {
            "status": "not run",
            "reason": "no fixture-point Ward probe in this record (li_manifest.py run "
            "resumes it)",
        }
    elif not wards["legs"]:
        # no external massless gauge boson: no Ward probe reaches the row
        # (m-lit Q12 (a): Recola mandatory, lit-ref's references)
        statuses.append("recorded")
        l4["fixture_points"] = {
            "status": "recorded",
            "reason": "no external massless gauge-boson leg: no Ward probe reaches it",
        }
    else:
        for label, arm in wards["arms"].items():
            if isinstance(arm, dict):
                l4[label] = {"status": "not run", "reason": arm["not_run"]}
                statuses.append("partial")
                continue
            worst = [max(x["worst"].values()) for x in arm if "worst" in x]
            if not worst:
                status = "partial" if label.startswith("tirust") else "not run"
            elif max(worst) <= FACTOR and all(
                x.get("passed") for x in arm if "worst" in x
            ):
                status = "pass" if len(worst) == count else "partial"
            else:
                status = "fail"
            if label.startswith("tirust") and stale:
                status = _worst([status, f"waits: {TIR_MP}"])
                l4["waits_on"] = TIR_MP
            l4[label] = {
                "status": status,
                "worst_ratio": max(worst, default=None),
                "served": len(worst),
                "of": count,
                "failed": _counted(x["error"] for x in arm if "error" in x),
            }
            statuses.append(status)
        l4["legs"] = wards["legs"]
        l4["zeroed_widths"] = wards.get("zeroed_widths")
    if not statuses:
        statuses.append("not run")
    out["L4"] = {"status": _worst(statuses), **l4}
    # L5 / LI-L1: the exact Lorentz transform: binary64 within 10 E of the
    # fixture point (the transformed point's own estimate is recorded apart:
    # outside the partonic rest frame the rotation estimate overshoots, a
    # finding for lit-stab-n), double-double recorded.
    i64 = arms.get("identity/ninjars/double")
    idd = arms.get("identity/ninjars/double-double")
    if i64 is not None:
        ratios, devs, moved = [], [], []
        for p in range(count):
            a, b = n64c["points"][p], i64["points"][p]
            if a["status"] != "success" or b["status"] != "success":
                continue
            e = _abs_finite(a["estimate"]) or 0.0
            diff = abs(float(_total(a["values"]) - _total(b["values"])))
            ratios.append(diff / (FACTOR * e) if e else (0.0 if not diff else math.inf))
            moved.append(b["estimate"]["relative"])
        for a, b in zip(
            ndd.get("points", []), (idd or {}).get("points", []), strict=False
        ):
            if a["status"] == "success" and b["status"] == "success":
                devs.append(_rel(_total(b["values"]), _total(a["values"])))
        worst = max(ratios, default=None)
        out["L5"] = {
            "status": "not run"
            if worst is None
            # A numerical zero is two roundings: L8 judges it.
            else (
                "recorded"
                if ZERO_TIER in entry["tiers"]
                else ("pass" if worst <= 1 else "estimate miss")
            ),
            "worst_ratio_to_10E": worst,
            "double_double_max_relative": max(devs, default=None),
            "transformed_estimate_relative": max(moved, default=None),
        }
        if idd is not None and "not_run" in idd:
            out["L5"]["double_double_not_run"] = idd["not_run"]
        tid = record.get("identity_tirust")
        if tid is None:
            out["L5"]["tirust"] = {
                "status": "not run",
                "reason": "no TIRust identity arm in the record "
                "(li_manifest.py identity-tirust)",
            }
        else:
            l5 = _identity_l5(
                tid["fixture"], tid["transformed"], ZERO_TIER in entry["tiers"]
            )
            l5["native"] = (tid.get("native") or {}).get("build")
            l5["bitwise_record"] = tid["bitwise_record"]
            out["L5"]["tirust"] = l5
            if l5["status"] != "not run":
                out["L5"]["status"] = _worst([out["L5"]["status"], l5["status"]])
    # E: the binary64 estimate covers the binary64 error against the
    # double-double value (|b64 - DD| <= 10 E_abs, every point both serve;
    # a miss goes to lit-stab-n / lit-stab-t; TIRust's estimate on its
    # served points alike).
    e_rows = {}
    for label, checked in (("ninjars", n64c), ("tirust", t64c)):
        ratios, errors = [], []
        for p in range(count):
            a = checked["points"][p] if "points" in checked else None
            b = ndd["points"][p] if "points" in ndd else None
            if not a or not b or a["status"] != "success" or b["status"] != "success":
                continue
            e = _abs_finite(a["estimate"])
            diff = abs(float(_total(a["values"]) - _total(b["values"])))
            errors.append(_rel(_total(a["values"]), _total(b["values"])))
            ratios.append(diff / (FACTOR * e) if e else (0.0 if not diff else math.inf))
        e_rows[label] = {
            "worst_error_over_10E": max(ratios, default=None),
            "worst_relative_error": max(errors, default=None),
            "points": len(ratios),
        }
    worst = e_rows["ninjars"]["worst_error_over_10E"]
    out["E"] = {
        "status": "not run"
        if worst is None
        else (
            "pass"
            if worst <= 1 and (e_rows["tirust"]["worst_error_over_10E"] or 0) <= 1
            else "estimate miss"
        ),
        **e_rows,
    }
    # L6 both backends: binary64 through the one comparison.
    # (a numerical-zero row's double-double / AP comparison is absolute, on
    # the double-double estimates of both backends: ``_high_l6``)
    zero_bounds = (
        [
            (
                (n.get("estimate") if n.get("status") == "success" else None),
                (t.get("estimate") if t.get("status") == "success" else None),
            )
            for n, t in zip(ndd.get("points", []), tdd.get("points", []), strict=False)
        ]
        if zero and "points" in ndd and "points" in tdd
        else ([] if zero else None)
    )
    rows, failed = [], {}
    t_served = _served(t64)
    for p in range(count):
        if not t_served[p] or not n_served[p]:
            continue
        tc = t64c["points"][p] if "points" in t64c else None
        n_entries = _entries(n64c["points"][p])
        t_entries = _entries(
            t64["points"][p],
            tc["estimate"] if tc and tc["status"] == "success" else None,
        )
        for row in _compare(n_entries, t_entries, True):
            row["point"] = p
            row["e_t"] = bool(tc and tc["status"] == "success")
            rows.append(row)
    for p in range(count):
        if not t_served[p]:
            failed[p] = t64["points"][p]["detail"]
    misses = [r for r in rows if not r["passed"]]
    real = [
        r
        for r in misses
        if r["difference"] > LAX * max(abs(complex(*map(float, r["ninjars"]))), 1e-300)
        and r["coefficient"] == "finite"
    ]
    l6_status = "pass" if not misses else ("fail" if real else "estimate miss")
    if failed:
        l6_status = "partial" if l6_status == "pass" else l6_status
    worst = max(
        (
            r["difference"] / r["bound"] if r["bound"] else math.inf
            for r in rows
            if r["difference"]
        ),
        default=0.0,
    )
    finite_rel = max(
        (
            _rel(_total(t64["points"][p]["values"]), _total(n64["points"][p]["values"]))
            for p in range(count)
            if t_served[p]
        ),
        default=None,
    )
    switched = {
        label: found
        for label, arm, backend in (
            ("ninjars/double/checked", n64c, "ninjars"),
            ("tirust/double/plain", t64, "tirust"),
            ("tirust/double/checked", t64c, "tirust"),
            ("ninjars/double-double", ndd, "ninjars"),
            ("tirust/double-double", tdd, "tirust"),
        )
        if (found := _switched(arm, backend))
    }
    if switched:
        l6_status = "fail"
    out["L6"] = {
        "status": l6_status,
        "double": {
            "status": l6_status,
            "compared_entries": len(rows),
            "beyond_10E": len(misses),
            "worst_ratio_to_10E": worst,
            "finite_max_relative": finite_rel,
            "tirust_served": sum(t_served),
            "tirust_served_checked": sum(_served(t64c)),
            "of": count,
            "tirust_failed_reasons": _reasons(t64),
            **({"effective_backend_switched": switched} if switched else {}),
        },
        "double-double": _high_l6(ndd, tdd, tir_carriers, "double-double", zero_bounds)
        if tdd
        else {"status": "not run", "reason": "a binary64-only fixture (its carriers)"},
    }
    if nap is not None and "not_run" in nap:
        # the AP arm not run (``skip``): L6 / L7 in AP not run, with the reason
        out["L6"][ARBITRARY] = {"status": "not run", "reason": nap["not_run"]}
        out["L7"] = {"status": "not run", "reason": nap["not_run"]}
    elif nap is not None:
        out["L6"][ARBITRARY] = _high_l6(
            nap,
            arms.get(f"tirust/{ARBITRARY}/plain", {}),
            tir_carriers,
            ARBITRARY,
            zero_bounds,
        )
    # L6's verdict: the worst of its carriers (a high-precision carrier not
    # run makes it partial; an arm TIRust refuses typed for want of the
    # carrier waits on lit-tir-mp, as do TIRust arms taken before it, re-run
    # at its re-pin, ruling (5): a binary64 failure still fails).
    high = [
        out["L6"][c]["status"] for c in ("double-double", ARBITRARY) if c in out["L6"]
    ]
    out["L6"]["status"] = _worst(
        [
            l6_status,
            *("partial" if h == "not run" else h for h in high),
            *([f"waits: {TIR_MP}"] if stale else []),
        ]
    )
    if stale or any(h.startswith("waits") for h in high):
        out["L6"]["waits_on"] = TIR_MP
        out["L6"]["double"]["tirust_before"] = TIR_MP if stale else None
    # L7 DD vs AP.
    if nap is not None and "points" in nap:
        devs = [
            _rel(_total(a["values"]), _total(b["values"]))
            for a, b in zip(ndd["points"], nap["points"], strict=True)
            if a["values"] is not None and b["values"] is not None
        ]
        worst = max(devs, default=None)
        if zero:
            devs = [
                abs(float(_total(a["values"]) - _total(b["values"])))
                / (FACTOR * (_abs_finite(a["estimate"]) or math.inf))
                for a, b in zip(ndd["points"], nap["points"], strict=True)
                if a["values"] is not None and b["values"] is not None
            ]
            worst = max(devs, default=None)
            out["L7"] = {
                "status": "not run"
                if worst is None
                else ("pass" if worst <= 1 else "fail"),
                "max_difference_over_10E_dd": worst,
                "digits": record.get("digits"),
            }
    if nap is not None and "points" in nap and not zero:
        out["L7"] = {
            "status": "not run"
            if worst is None
            else _verdict(worst <= CARRIER, worst <= LAX),
            "max_relative": worst,
            "digits": record.get("digits"),
        }
    # L8 numerical zeros.
    if ZERO_TIER in entry["tiers"]:
        l8 = {}
        statuses = []
        for label, arm in (("double", n64c), ("double-double", ndd)):
            ratios = []
            for pt in arm.get("points", []):
                if pt["status"] != "success":
                    continue
                e = _abs_finite(pt["estimate"])
                value = abs(float(_total(pt["values"])))
                ratios.append(
                    value / (FACTOR * e) if e else (0.0 if not value else math.inf)
                )
            worst = max(ratios, default=None)
            l8[label] = worst
            statuses.append(
                "not run" if worst is None else ("pass" if worst <= 1 else "fail")
            )
        out["L8"] = {"status": _worst(statuses), "worst_value_over_10E_abs": l8}
        if data.get("exact_colour_zero"):
            # LI-Z1: exactly 0 with the generation's colour record (the one
            # exact-zero mechanism, Q13), every arm that serves.
            colour = bool(probes.get("exact_colour_zero"))
            values = [
                _total(pt["values"])
                for label, arm in arms.items()
                if isinstance(arm, dict) and "points" in arm
                for pt in arm["points"]
                if pt["status"] == "success"
            ]
            exact = colour and bool(values) and all(v == 0 for v in values)
            out["L8"] = {
                "status": "pass" if exact else "fail",
                "exact_colour_zero_record": colour,
                "values_exactly_zero": f"{sum(v == 0 for v in values)}/{len(values)}",
            }
    out["references"] = {k: v for k, v in refs.items() if v is not None}
    return out


def _high_l6(
    ninjars: dict,
    tirust: dict,
    served: frozenset[str] | None = None,
    carrier: str = "double-double",
    bounds: list | None = None,
) -> dict:
    """L6 in double-double / AP: |N - T| <= 1e-24 of the sector's largest
    coefficient through the one comparison (a target, R5: below ~1e-5 it is
    recorded, never a failure); on a numerical-zero row (``bounds``: per
    point the double-double estimates of both backends, the L8 rule) the
    largest coefficient is rounding itself, so the comparison is absolute,
    |N - T| <= 10 max(E_N, E_T) with those estimates (an AP value's error is
    below its double-double estimate). TIRust's typed refusal of the whole arm is
    the arm waiting on lit-tir-mp where the extension that took it did not
    serve the carrier (``served``: ``tirust_carriers``; None, a record
    before the recorded capability query: not served), else a TIRust
    coverage gap (partial, with the typed reason)."""

    from tools.loop_v2_observables_backends import _compare

    if "not_run" in tirust or "not_run" in ninjars:
        return {
            "status": "not run",
            "reason": tirust.get("not_run") or ninjars.get("not_run"),
        }
    if "refused" in tirust or "points" not in tirust:
        if served is not None and carrier in served:
            return {"status": "partial", "tirust": tirust.get("refused")}
        return {"status": f"waits: {TIR_MP}", "tirust": tirust.get("refused")}
    rows, failed = [], 0
    for p, (n, t) in enumerate(
        zip(ninjars.get("points", []), tirust["points"], strict=False)
    ):
        if n["status"] != "success" or t["status"] != "success":
            failed += t["status"] != "success"
            continue
        if bounds is not None:
            e_n, e_t = bounds[p]
            if e_n is None or e_t is None:
                failed += 1
                continue
            rows.extend(_compare(_entries(n, e_n), _entries(t, e_t), True))
            continue
        rows.extend(
            _compare(
                _entries(n, {"absolute": []}), _entries(t, {"absolute": []}), False
            )
        )
    worst = max(
        (r["difference"] / r["bound"] for r in rows if r["bound"]), default=None
    )
    relative = max(
        (
            r["difference"] / max(abs(float(Decimal(r["ninjars"][0]))), 1e-300)
            for r in rows
            if r["coefficient"] == "finite"
        ),
        default=None,
    )
    strict = all(r["passed"] for r in rows)
    if not rows:
        status = "not run"
    elif bounds is not None:
        # a numerical zero: absolute only (a relative figure is meaningless)
        relative = None
        status = "pass" if strict else "fail"
    else:
        status = _verdict(strict, relative is None or relative <= LAX)
    if failed:
        status = _worst([status, "partial"])
    return {
        "status": status,
        **(
            {"rule": "absolute: 10 max(E_N, E_T), the double-double estimates (L8)"}
            if bounds is not None
            else {}
        ),
        "compared_entries": len(rows),
        "worst_ratio_to_bound": worst,
        "finite_max_relative": relative,
        "tirust_failed": failed,
        "tirust_failed_reasons": _reasons(tirust),
        # the TIRust coverage of this carrier is that of the arm compared:
        # with the checks (a failure of a check frame alone fails the point)
        # where the run took them, else without
        "tirust_arm": tirust.get("arm", "checked" if carrier != ARBITRARY else "plain"),
    }


def _entries(point: dict, estimate: dict | None = None) -> list:
    """A record point as the one comparison's entries (``_laurents``'s
    shape: per sector (coefficient, (re, im), absolute estimate))."""

    estimate = point["estimate"] if estimate is None else estimate
    out = []
    for s, sector in enumerate(point["values"]):
        errors = estimate["absolute"][s] if estimate and estimate["absolute"] else None
        out.append(
            [
                (
                    name,
                    _complex(sector[name]),
                    0.0 if errors is None else float(errors[name]),
                )
                for name in ("finite", "single_pole", "double_pole")
                if sector[name] is not None
            ]
        )
    return out


def _complex(text: str) -> tuple[Decimal, Decimal]:
    """A recorded coefficient (float repr, complex repr or decimal) as exact
    (re, im) decimals."""

    if "j" in text:
        value = complex(text)
        return Decimal(value.real), Decimal(value.imag)
    return Decimal(text), Decimal(0)


# ------------------------------------------------------------- stress points


# PLAN §4.1 "Stress points" (M §4.7): SPEC's "stress" entries, each one
# stress fixture (``EXTRA/<name>.json``, default ``li_stress_<base>_<kind>``:
# the base's scheme, or a process of its scheme (``process``), no provider
# reference, binary64 + double-double + AP; judged by E, L6, L7). The 2 -> 2
# kinds (``pt``, ``forward``, ``threshold``, ``top-threshold``) build an
# equal-mass or massless final pair (``_pair``); an entry with
# ``fractions`` / ``transverse`` builds n final particles on the light cone
# (``_lightcone``: ``planar`` scales the out-of-plane components by the
# value, ``top-threshold`` sits at sqrt(s) = 2 m_t (1 + value)).
def stress_entries() -> list[dict]:
    return spec()["stress"]


def stress_name(entry: dict) -> str:
    return (
        entry.get("name")
        or f"li_stress_{entry['base'].removeprefix('li_')}_{entry['kind']}"
    )


def _near(target: float, span: int = 60) -> Fraction:
    """The 2^x 5^y (|x| + |y| <= span) nearest ``target`` on a log scale:
    a coarse knob whose every product and quotient stays a terminating
    decimal."""

    best = min(
        (
            (x, y)
            for x in range(-span, span + 1)
            for y in range(abs(x) - span, span - abs(x) + 1)
        ),
        key=lambda e: abs(e[0] * math.log(2) + e[1] * math.log(5) - math.log(target)),
    )
    return Fraction(2) ** best[0] * Fraction(5) ** best[1]


def _pair(mass2: Fraction, pt: Fraction, rho: Fraction) -> list:
    """An exact 2 -> 2 point with massless beams along z and a final pair of
    equal squared mass ``mass2`` back to back at transverse momentum ``pt``:
    with M^2 = mass2 + pt^2, particle 3 has E + p_z = u (u = 2^x 5^y near M)
    and E - p_z = M^2 / u, the beams a = (u + w) / 2 and b = a (M^2 / u) / w
    with w = rho u, so that particle 4 = p1 + p2 - p3 is on the same shell;
    then sqrt(s) = M (sqrt(rho) + 1 / sqrt(rho)) (a z-boosted frame: pt and
    the invariants are those of the CM frame). Every entry a terminating
    decimal, mass shells and momentum conservation exact."""

    m2 = mass2 + pt * pt
    u = _near(math.sqrt(m2))
    r = m2 / u
    w = rho * u
    a = (u + w) / 2
    b = a * r / w
    p3 = [(u + r) / 2, pt, Fraction(0), (u - r) / 2]
    p4 = [a + b - p3[0], -pt, Fraction(0), a - b - p3[3]]
    return [[a, 0, 0, a], [b, 0, 0, -b], p3, p4]


def _rho(ratio: float) -> float:
    """rho with sqrt(rho) + 1 / sqrt(rho) = ratio (= sqrt(s) / M >= 2)."""

    root = (ratio + math.sqrt(ratio * ratio - 4)) / 2
    return root * root


def _lightcone(
    masses2: list[Fraction],
    transverse: list[list[Fraction]],
    fractions: list[Fraction],
    s: Fraction,
) -> list:
    """An exact 2 -> n point with massless beams along z and final squared
    masses ``masses2``: final particle i has transverse momentum kappa k_i
    (``transverse``: the first n - 1, the last balances them) and light-cone
    component E + p_z = lambda x_i (x_i the 2^x 5^y nearest ``fractions``),
    E - p_z = (m_i^2 + kappa^2 k_i^2) / (lambda x_i); kappa (12 decimals)
    puts sqrt(s) at the target (to ~1e-12), lambda (2^x 5^y) balances the
    beams. Every entry a terminating decimal, mass shells and momentum
    conservation exact."""

    k = [*transverse, [-sum(c[0] for c in transverse), -sum(c[1] for c in transverse)]]
    x = [_near(float(f)) for f in fractions]
    total = sum(x)
    rest = sum(m / xi for m, xi in zip(masses2, x, strict=True))
    spread = sum((c[0] ** 2 + c[1] ** 2) / xi for c, xi in zip(k, x, strict=True))
    kappa2 = (s / total - rest) / spread
    if kappa2 <= 0:
        raise ValueError(
            f"sqrt(s) = {math.sqrt(float(s))} is below the final state's reach"
        )
    kappa = Fraction(Decimal(format(math.sqrt(float(kappa2)), ".12f")))
    k = [[kappa * c[0], kappa * c[1]] for c in k]
    big = [m + c[0] ** 2 + c[1] ** 2 for m, c in zip(masses2, k, strict=True)]
    scale = _near(
        math.sqrt(float(sum(m / xi for m, xi in zip(big, x, strict=True)) / total))
    )
    plus = [scale * xi for xi in x]
    minus = [m / u for m, u in zip(big, plus, strict=True)]
    a, b = sum(plus) / 2, sum(minus) / 2
    final = [
        [(u + v) / 2, c[0], c[1], (u - v) / 2]
        for u, v, c in zip(plus, minus, k, strict=True)
    ]
    return [[a, 0, 0, a], [b, 0, 0, -b], *final]


def _stress_masses(base: dict, entry: dict) -> list[Fraction]:
    """The final squared masses of an n-body stress entry: the named
    parameters of the base's scheme (``masses``), else the base point's
    final mass shells."""

    names = entry.get("masses")
    if names:
        parameters = base["scheme_data"]["parameters"]
        derived = base.get("derived_parameters") or {}
        return [
            Fraction(0) if n is None else Fraction(parameters.get(n) or derived[n]) ** 2
            for n in names[base["initial"] :]
        ]
    point = [[Fraction(c) for c in p] for p in base["points"][0]]
    return [p[0] ** 2 - sum(c * c for c in p[1:]) for p in point[base["initial"] :]]


def stress_points(base: dict, entry: dict) -> list:
    """The exact points of one stress entry (``stress_entries``): ``pt`` at
    the transverse momenta ``values`` (sqrt(s) near ``energy``), ``forward``
    at the CM angles ``values`` (pt = theta sqrt(s) / 2), ``threshold`` at
    the distances sqrt(s) / 2M - 1 ~ ``values`` above the pair threshold
    (rho from the 2^x 5^y knob, the pair at ``pt``), ``top-threshold`` at
    sqrt(s) = 2 m_t (1 + value) (to ~1e-12; the pair at ``rho``, or n final
    particles on the light cone), ``planar`` n final particles at sqrt(s) =
    ``energy`` with the out-of-plane transverse components scaled by the
    value (5-point Gram ~ value^2)."""

    kind, values, energy = entry["kind"], entry["values"], entry.get("energy")
    out = []
    if "fractions" in entry:
        masses2 = _stress_masses(base, entry)
        fractions = [Fraction(Decimal(f)) for f in entry["fractions"]]
        shape = [[Fraction(Decimal(c)) for c in pair] for pair in entry["transverse"]]
        for text in values:
            value = Fraction(Decimal(text))
            if kind == "planar":
                transverse = [[c[0], c[1] * value] for c in shape]
                target = Fraction(energy) ** 2
            elif kind == "top-threshold":
                transverse = shape
                mt = Fraction(base["scheme_data"]["parameters"]["MT"])
                target = (2 * mt * (1 + value)) ** 2
            else:
                raise ValueError(f"unknown n-body stress kind {kind!r}")
            out.append(_lightcone(masses2, transverse, fractions, target))
        return [[[_decimal(Fraction(c)) for c in p] for p in q] for q in out]
    point = [[Fraction(c) for c in p] for p in base["points"][0]]
    mass2 = point[2][0] ** 2 - sum(c * c for c in point[2][1:])
    for text in values:
        value = Fraction(Decimal(text))
        if kind in ("pt", "forward"):
            pt = value if kind == "pt" else value * Fraction(energy) / 2
            ratio = float(Fraction(energy)) / math.sqrt(float(mass2 + pt * pt))
            out.append(_pair(mass2, pt, _near(_rho(ratio))))
        elif kind == "threshold":
            root = math.sqrt(float(value)) + math.sqrt(float(value) + 1)
            out.append(_pair(mass2, Fraction(Decimal(entry["pt"])), _near(root * root)))
        elif kind == "top-threshold":
            mt = Fraction(base["scheme_data"]["parameters"]["MT"])
            rho = _near(float(Fraction(Decimal(entry["rho"]))))
            m = 2 * float(mt * (1 + value)) / (math.sqrt(rho) + 1 / math.sqrt(rho))
            pt = Fraction(Decimal(format(math.sqrt(m * m - float(mass2)), ".12f")))
            out.append(_pair(mass2, pt, rho))
        else:
            raise ValueError(f"unknown stress kind {kind!r}")
    return [[[_decimal(Fraction(c)) for c in p] for p in q] for q in out]


# The fields a derived fixture takes from its base unchanged.
BASE_FIELDS = (
    "loop_induced",
    "pdgs",
    "initial",
    "madloop_process",
    "loop_orders",
    "squared_orders",
    "correction",
    "scheme",
    "scheme_data",
    "normalization",
)


def _normalization(base: dict, pdgs: list[int]) -> dict:
    """The base's normalisation with the final identical-particle factor of
    ``pdgs`` (the initial average is the base's: same initial state)."""

    final = pdgs[base["initial"] :]
    symmetry = math.prod(math.factorial(final.count(p)) for p in set(final))
    initial = base["normalization"]["initial_average"]
    return {
        **base["normalization"],
        "final_symmetry": symmetry,
        "denominator": initial * symmetry,
    }


def _derive(base: dict, changes: dict) -> dict:
    """The base's fields with a process of its scheme (``changes``: pdgs,
    madloop_process, orders, fixed parameters overriding the base's)."""

    out = {k: base[k] for k in BASE_FIELDS}
    for key in ("pdgs", "madloop_process", "loop_orders", "squared_orders"):
        if key in changes:
            out[key] = changes[key]
    if "fixed_parameters" in changes:
        scheme = json.loads(json.dumps(base["scheme_data"]))
        scheme["fixed_parameters"].update(changes["fixed_parameters"])
        if "parameter_overrides" in scheme:
            scheme["parameter_overrides"].update(changes["fixed_parameters"])
        out["scheme_data"] = scheme
    out["normalization"] = _normalization(base, out["pdgs"])
    return out


def write_stress() -> list[Path]:
    """Write every derived fixture of SPEC (``derived_fixtures``)."""

    return [_write_fixture(data) for data in derived_fixtures()]


def derived_fixtures() -> list[dict]:
    """Every derived fixture of SPEC (deterministic): the stress fixtures
    and the exact-colour-zero fixtures (``derived``: the base's scheme and
    points with another process, no provider reference)."""

    out = []
    for entry in stress_entries():
        base = fixture(entry["base"])
        process = _derive(base, entry.get("process", {}))
        points = stress_points(base, entry)
        data = {
            "name": stress_name(entry),
            "li_row": base["li_row"],
            "stress": {k: v for k, v in entry.items() if k not in ("name", "source")},
            **process,
            "carriers": [*CARRIERS, ARBITRARY],
            "points": points,
            "mu_r": [base["mu_r"][0]] * len(points),
            "rows": [{"providers": {}} for _ in points],
            "source": f"PLAN §4.1 stress points (M §4.7; {entry['source']}): exact "
            "decimal points of "
            "tools/loop_benchmark/li_manifest.py write_stress; no provider reference "
            "in the fixture "
            "(the binary64 estimate against double-double and AP, NinjaRS against "
            "TIRust, MadLoop "
            "QP: stress-madloop)",
        }
        out.append(data)
    for entry in spec()["derived"]:
        base = fixture(entry["base"])
        data = {
            "name": entry["name"],
            "li_row": entry["li_row"],
            **_derive(base, entry),
            "exact_colour_zero": entry["exact_colour_zero"],
            "points": base["points"],
            "mu_r": base["mu_r"],
            "rows": [{"providers": {}} for _ in base["points"]],
            "source": f"{entry['source']} (tools/loop_benchmark/li_manifest.py "
            "write_stress)",
        }
        out.append(data)
    return out


def _write_fixture(data: dict) -> Path:
    path = EXTRA / f"{data['name']}.json"
    path.write_text(json.dumps(data, indent=1) + "\n")
    return path


# The MadLoop QP comparison of the stress points (§4.1 "binary64 estimate vs
# DD vs AP vs MadLoop QP"): lit-ref's reference run (``li_references.py run
# --provider madloop``: relative accuracy 1e-11 with the stability test on
# every call, quadruple-precision rescue, helicity filter off) on the base
# process's MadLoop export of the reference tree
# (``<root>/runs/li/<base>/madloop-export``) at the stress fixture's exact
# points, under the 45-minute rule (``REFERENCE_TIMEOUT`` s per run).
REFERENCE_TIMEOUT = 2700


def stress_madloop(
    work: Path, entries: list[dict], root: Path, cpu: int | None = None
) -> dict:
    """Per stress fixture its MadLoop QP rows (value, MadLoop's accuracy
    estimate and return code per point), or why it was not run."""

    out: dict[str, Any] = {}
    tool = WT / "tools" / "loop_reference" / "li_references.py"
    for entry in entries:
        if "stress" not in entry["tiers"]:
            continue
        name = entry["fixture"]
        data = fixture(name)
        base = data["stress"]["base"]
        export = root / "runs" / "li" / base / "madloop-export"
        if data["pdgs"] != fixture(base)["pdgs"]:
            out[name] = {
                "status": "not run",
                "reason": "a process outside lit-ref's reference set "
                f"({data['madloop_process']}): "
                "no MadLoop export in the reference tree",
            }
            continue
        if not export.is_dir():
            out[name] = {"status": "not run", "reason": f"no MadLoop export of {base}"}
            continue
        run_dir = work / "stress-madloop" / name
        run_dir.mkdir(parents=True, exist_ok=True)
        points = run_dir / "points.json"
        points.write_text(
            json.dumps(
                {
                    "process_name": base,
                    "pdgs": data["pdgs"],
                    "construction": data["source"],
                    "points": data["points"],
                    "mu_r": data["mu_r"],
                },
                indent=1,
            )
            + "\n"
        )
        command = [
            sys.executable,
            str(tool),
            "run",
            "--process",
            base,
            "--provider",
            "madloop",
            "--points",
            str(points),
            "--work-dir",
            str(run_dir),
            "--mg5",
            str(root / "sources" / "MG5_aMC_v3_7_0"),
            "--madloop-export",
            str(export),
            "--reference-root",
            str(root),
        ]
        if cpu is not None:
            command += ["--cpu", str(cpu)]
        start = time.perf_counter()
        try:
            done = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=REFERENCE_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired:
            out[name] = {
                "status": "not run",
                "reason": "45-minute rule: MadLoop did not finish in "
                f"{REFERENCE_TIMEOUT} s",
            }
            continue
        result = run_dir / "madloop-result.json"
        if done.returncode or not result.is_file():
            out[name] = {
                "status": "not run",
                "reason": f"MadLoop run failed (rc {done.returncode}): "
                f"{done.stderr.strip()[-2000:]}",
            }
            continue
        rows = _load(result)["rows"]
        out[name] = {
            "base": base,
            "seconds": time.perf_counter() - start,
            "rows": [
                {k: row[k] for k in ("value", "accuracy", "status") if k in row}
                for row in rows
            ],
        }
        print(name, json.dumps(out[name]["rows"]), flush=True)
    return out


def judge_madloop(madloop: dict, record: dict) -> dict:
    """MadLoop QP at the stress points against pyAmpliCol's 40-digit AP
    (else double-double) on the exact points: per point the relative
    deviation, whether MadLoop's own accuracy estimate covers it (|ML - AP|
    <= 10 x accuracy x |ML|) and whether the point's binary64 conditioning
    does (MadLoop reads the momenta in binary64 and restores the shells
    itself, ImprovePSPoint: at an ill-conditioned point it evaluates a
    point ~1e-16 away from the exact one; pyAmpliCol's binary64 relative
    estimate E at the point measures that conditioning: deviation <= 10 E);
    recorded, the stress points' rules are E, L6 and L7."""

    if "rows" not in madloop:
        return madloop
    truth = record["arms"].get(f"ninjars/{ARBITRARY}/plain")
    carrier = ARBITRARY
    if not truth or "points" not in truth:
        truth, carrier = high_arm(record["arms"], "ninjars"), "double-double"
    points = []
    b64 = record["arms"]["ninjars/double/checked"].get("points", [])
    for p, (row, pt) in enumerate(
        zip(madloop["rows"], truth.get("points", []), strict=False)
    ):
        if pt["status"] != "success":
            points.append({"madloop": row, "truth": None})
            continue
        value = _total(pt["values"])
        deviation = _rel(row["value"], value)
        conditioning = (
            b64[p]["estimate"]["relative"]
            if p < len(b64) and b64[p]["status"] == "success" and b64[p]["estimate"]
            else None
        )
        points.append(
            {
                "madloop": row["value"],
                "madloop_accuracy": row.get("accuracy"),
                "madloop_status": row.get("status"),
                "relative_to_truth": deviation,
                "covered": deviation <= FACTOR * (row.get("accuracy") or 0.0),
                "binary64_estimate": conditioning,
                "within_input_conditioning": conditioning is not None
                and deviation <= FACTOR * conditioning,
            }
        )
    return {
        "status": "recorded",
        "truth": f"pyAmpliCol NinjaRS {carrier} at the exact points",
        "points": points,
        "seconds": madloop.get("seconds"),
    }


# ------------------------------------------------------------- LI-A7


# The large-m_t row (PLAN §4.1 LI-A7; SPEC's ``limit_row``): the registry
# rows that carry it.
LIMIT_ROW = _load(SPEC)["identities"]["limit_row"]
# LI-A1's "HEFT ratio reported" (§4.1; SPEC's ``heft_ratio_row``): its runs
# take the same scan against the HEFT tree, recorded, no limit rule.
HEFT_RATIO_ROW = _load(SPEC)["identities"]["heft_ratio_row"]
# The heavy-top scan: m_t = y_t = the fixture's m_t times 2^k, k = 0 ..
# DOUBLINGS (overridable, ``limits --doublings``), in double-double at the
# fixture's exact points (the loop integrals cancel to O(s / m_t^2)).
DOUBLINGS = 7
HEFT = "built-in-sm-heft"


def limit_targets(entries: list[dict]) -> list[dict]:
    """LI-A7's fixtures: the campaign run of every registry row carrying
    the id, against its limit oracle: the fixture rows' ``limit_oracle``
    (g g > h h: the low-energy theorem) or else the process's HEFT tree;
    and LI-A1's runs against the HEFT tree (its ratio reported)."""

    keys = {
        r["key"]
        for r in registry()["rows"]
        if {LIMIT_ROW, HEFT_RATIO_ROW} & set(r["ids"])
    }
    out = []
    for entry in entries:
        if entry["key"] in keys and (FIXTURES / f"{entry['fixture']}.json").is_file():
            data = fixture(entry["fixture"])
            oracle = "let" if "limit_oracle" in data["rows"][0] else "heft"
            out.append(
                {"fixture": entry["fixture"], "key": entry["key"], "oracle": oracle}
            )
    return out


def _color_accuracy(artifact: Path) -> str:
    """The colour accuracy ``artifact`` was generated at (its effective
    configuration's ``[color] accuracy``)."""

    import tomllib

    config = tomllib.loads((artifact / "config" / "effective.toml").read_text())
    return str(config["color"]["accuracy"])


def _heft_runtime(data: dict, work: Path, process: str, accuracy: str) -> Any:
    """The HEFT tree of the fixture's process (``built-in-sm-heft``, the
    loop model's MG5 particle names) at ``accuracy``, the colour accuracy
    of the loop run it divides (loop-induced: full colour only), generated
    once into ``work``. A tree request's own default is leading colour,
    whose colour factor is the leading N_c power (N^2 for g g > h, not
    N^2 - 1): unset, it put exactly N^2 / (N^2 - 1) = 9/8 into the HEFT
    trees of every LI-A7 ratio (lit-heft)."""

    from pyamplicol import Runtime
    from pyamplicol.api import Generator, ProcessRequest, ProcessSet
    from pyamplicol.config import resolve_config

    # The accuracy names the directory: a tree of another accuracy is never
    # reused.
    root = work / f"heft-{data['name']}-{accuracy}"
    output = root / "artifact"
    if not (output / "artifact.json").is_file():
        root.mkdir(parents=True, exist_ok=True)
        path = root / "card.toml"
        path.write_text(
            "\n".join(
                [
                    'action = "generate"',
                    "[model]",
                    f"source = {json.dumps(HEFT)}",
                    "[process]",
                    f'entries = [{{expression = {json.dumps(process)}, name = "p"}}]',
                    "[color]",
                    f"accuracy = {json.dumps(accuracy)}",
                    "[generation]",
                    f"output = {json.dumps(str(output))}",
                    "emit_api_bundle = false",
                    "[generation.validation]",
                    "post_build_validation = false",
                ]
            )
            + "\n"
        )
        Generator(resolve_config(path)).generate(
            ProcessSet((ProcessRequest.parse(process, name="p"),)), output
        )
    return Runtime.load(output, process="p")


def _richardson(h: list[float], values: list[Decimal]) -> tuple[float, float]:
    """R(h -> 0) from the last three samples of R(h) = R0 + a h + b h^2
    (h = 1 / m_t^2), with the difference to the two-term extrapolation of
    the last two as its error estimate."""

    with localcontext() as context:
        context.prec = 60
        x = [Decimal(repr(v)) for v in h[-3:]]
        y = values[-3:]
        # Lagrange interpolation at 0 through three points (quadratic).
        r3 = sum(
            y[i]
            * math.prod((Decimal(0) - x[j]) / (x[i] - x[j]) for j in range(3) if j != i)
            for i in range(3)
        )
        r2 = (y[2] * x[1] - y[1] * x[2]) / (x[1] - x[2])
        return float(r3), float(abs(r3 - r2))


def judge_limit(limit: float, error: float) -> dict:
    """One point's LI-A7 verdict: the extrapolated ratio equals 1 within ten
    times its error, the Richardson extrapolation error plus the oracle's
    roundoff floor. Both oracles are binary64 values (the HEFT tree's
    binary64 evaluation, the fixture's ``limit_oracle`` float), so the ratio
    is known no better than FLOOR_UNITS u of a binary64 value (the floor of
    ``stability.StabilityEstimate``): an exactly decoupling scan's
    extrapolation error falls below it (g g > h over its HEFT tree: ~1e-17
    at a limit 1 - 4e-16)."""

    from pyamplicol.loops.v2.assemble import Precision
    from pyamplicol.loops.v2.stability import FLOOR_UNITS

    floor = FLOOR_UNITS * Precision.double().unit_roundoff
    return {
        "limit": limit,
        "extrapolation_error": error,
        "oracle_floor": floor,
        "passed": abs(limit - 1) <= FACTOR * (error + floor),
    }


def limits(name: str, oracle: str, work: Path, doublings: int = DOUBLINGS) -> dict:
    """LI-A7 for one fixture: |A_loop|^2(m_t) over the limit oracle at
    every fixture point for m_t = y_t scanned (``DOUBLINGS``), the loop in
    double-double on the campaign's artifact (``work / name``), and its
    Richardson extrapolation to m_t -> infinity; passes when it equals 1
    within ten times its error (``judge_limit``: no fixed tolerance, the
    decoupling of the scan decides). The HEFT tree carries the shipped
    m_t corrections of its coupling (r = M_H^2 / m_t^2 through r^3), the
    low-energy theorem none."""

    from pyamplicol import Runtime

    data = fixture(name)
    compiled = compile_model(data, work / "model-cache")
    parameters = run_parameters(data, compiled)
    base = Fraction(parameters["MT"])
    masses = [base * 2**k for k in range(doublings + 1)]
    points = data["points"]
    scales = [_decimal(Fraction(mu) ** 2) for mu in data["mu_r"]]
    shared: list[str] = []
    if oracle == "heft":
        heft = _heft_runtime(
            data,
            work,
            expression(data, compiled),
            _color_accuracy(work / name / "artifact"),
        )
        # The fixture's parameters the HEFT model shares (the others, e.g.
        # its Yukawa, are none of the tree's).
        for key, value in parameters.items():
            try:
                heft.set_model_parameter(key, float(value))
            except (KeyError, ValueError):
                continue
            shared.append(key)
        if "MT" not in shared or "aS" not in shared:
            raise ValueError(f"the HEFT tree takes {shared}: no MT / aS")
    loop, reference = [], []
    for mass in masses:
        text = _decimal(mass)
        runtime = Runtime.load(
            work / name / "artifact",
            process="p",
            model_parameters={**parameters, "MT": text, "ymt": text},
        )
        result = runtime.evaluate(
            points, mu_r2=scales, arithmetic="double-double", poles="none"
        )
        loop.append([_total([_laurent(s) for s in v]) for v in result.values])
        if oracle == "heft":
            for key in ("MT", "ymt"):
                if key in shared:
                    heft.set_model_parameter(key, float(mass))
            values = heft.evaluate(
                [[[float(Fraction(c)) for c in m] for m in p] for p in points]
            )
            reference.append([Decimal(repr(complex(v).real)) for v in values])
        else:
            reference.append(
                [Decimal(repr(row["limit_oracle"]["value"])) for row in data["rows"]]
            )
    h = [float(1 / (m * m)) for m in masses]
    out = {
        "oracle": oracle,
        "masses": [str(m) for m in masses],
        "heft_parameters": shared,
        "points": [],
    }
    status = []
    for p in range(len(points)):
        with localcontext() as context:
            context.prec = 60
            ratios = [loop[k][p] / reference[k][p] for k in range(len(masses))]
        limit, error = _richardson(h, ratios)
        s = sum(Fraction(points[p][i][0]) for i in range(data["initial"])) ** 2 - sum(
            sum(Fraction(points[p][i][k]) for i in range(data["initial"])) ** 2
            for k in (1, 2, 3)
        )
        judged = judge_limit(limit, error)
        status.append(judged["passed"])
        out["points"].append(
            {
                "ratios": [float(r) for r in ratios],
                "s_over_mt2": [float(s / (m * m)) for m in masses],
                **judged,
            }
        )
    out["status"] = "pass" if all(status) else "fail"
    return out


# ------------------------------------------------------------- crossing

# The crossing identity (§4.1's identity row "LI-W1, L1, P1, C1, S1": C1, the
# crossing of LI-26's runs, g g > h g <-> u g > h u <-> u u~ > h g). Its
# data/lit.json id is 'crossing': the id LI-C1 is the complex-mass-scheme row
# (milestone.json loop_induced.validation_only). A run's artifact is evaluated
# at the crossed fixture points of every run of the row it relates to by
# crossing (itself included: the crossing of identical bosons), the crossed
# legs carrying negative-energy momenta: the loop integrals are then taken in
# the other process's physical region (the analytic continuation by +i0).
CROSSING_ROW, CROSSING_ID = _load(SPEC)["identities"]["crossing_row"], "crossing"


def legs(data: dict, compiled: Any) -> list[dict]:
    """Per leg of a fixture its all-outgoing flavour (an incoming leg's
    antiparticle, from the model), direction and statistics."""

    particles = {int(r.pdg_code): r for r in compiled.ir.particles}
    codes = {str(r.name): int(r.pdg_code) for r in compiled.ir.particles}
    out = []
    for i, pdg in enumerate(data["pdgs"]):
        record = particles[pdg]
        incoming = i < data["initial"]
        out.append(
            {
                "flavour": codes[str(record.antiname)] if incoming else pdg,
                "incoming": incoming,
                "fermion": record.statistics == "fermion",
            }
        )
    return out


def crossing_maps(target: list[dict], source: list[dict]) -> list[list[list[int]]]:
    """Every crossing of ``source``'s legs onto ``target``'s (``legs``): per
    target leg [source leg, sign], sign -1 for a crossed leg (its momentum
    negated). A crossing is fixed by the set of crossed source legs (an empty
    set is no crossing); within a target class (direction, flavour) the
    source legs keep their order, so relabellings of identical legs are not
    counted twice."""

    n = len(target)
    if len(source) != n or sorted(t["flavour"] for t in target) != sorted(
        s["flavour"] for s in source
    ):
        return []
    need: dict[tuple, list[int]] = {}
    for j, t in enumerate(target):
        need.setdefault((t["flavour"], t["incoming"]), []).append(j)
    maps = []
    for mask in range(1, 1 << n):
        crossed = [bool(mask >> i & 1) for i in range(n)]
        pool: dict[tuple, list[int]] = {}
        for i, s in enumerate(source):
            pool.setdefault((s["flavour"], s["incoming"] != crossed[i]), []).append(i)
        if {k: len(v) for k, v in pool.items()} != {k: len(v) for k, v in need.items()}:
            continue
        mapping: list[list[int]] = [[]] * n
        for key, targets in need.items():
            for j, i in zip(targets, pool[key], strict=True):
                mapping[j] = [i, -1 if crossed[i] else 1]
        maps.append(mapping)
    return maps


def crossed_points(points: list, mapping: list[list[int]]) -> list[list[list[str]]]:
    """The source's exact points on the target's legs (``crossing_maps``)."""

    return [
        [[_decimal(Fraction(c) * sign) for c in point[i]] for i, sign in mapping]
        for point in points
    ]


def crossing(work: Path, entries: list[dict]) -> dict:
    """The crossing evaluations of CROSSING_ROW's runs (module comment
    above): per (target, source, map) the target's artifact (the campaign's,
    ``work / target``) at the source's crossed points, NinjaRS binary64 with
    the checks and double-double, TIRust binary64 with the checks; judged in
    ``lit`` against the source's record. Runs whose fixtures differ in their
    parameters do not relate."""

    from pyamplicol import Runtime

    names = [e["fixture"] for e in entries if CROSSING_ROW in e["ids"]]
    data = {n: fixture(n) for n in names}
    compiled = {n: compile_model(data[n], work / "model-cache") for n in names}
    flavours = {n: legs(data[n], compiled[n]) for n in names}
    out: dict[str, Any] = {
        "row": CROSSING_ROW,
        "revision": _revision(),
        "crossings": [],
    }
    for target in names:
        artifact, _ = generate(target, work, compiled[target])
        parameters = run_parameters(data[target], compiled[target])
        runtime = None
        for source in names:
            if data[source]["scheme_data"] != data[target]["scheme_data"]:
                continue
            for mapping in crossing_maps(flavours[target], flavours[source]):
                if runtime is None:
                    runtime = Runtime.load(
                        artifact, process="p", model_parameters=parameters
                    )
                points = crossed_points(data[source]["points"], mapping)
                scales = [_decimal(Fraction(mu) ** 2) for mu in data[source]["mu_r"]]
                fermions = sum(
                    flavours[source][i]["fermion"] for i, sign in mapping if sign < 0
                )
                arms = {
                    arithmetic: _call(
                        runtime,
                        points,
                        scales,
                        backend="ninjars",
                        arithmetic=arithmetic,
                        checked=True,
                        digits=DIGITS,
                    )
                    for arithmetic in CARRIERS
                }
                # TIRust in binary64 (its carrier at this pin, R4)
                arms["tirust/double"] = _call(
                    runtime,
                    points,
                    scales,
                    backend="tirust",
                    arithmetic="double",
                    checked=True,
                    digits=DIGITS,
                )
                out["crossings"].append(
                    {
                        "target": target,
                        "source": source,
                        "map": mapping,
                        "crossed_fermions": fermions,
                        "points": points,
                        "arms": arms,
                    }
                )
                print(target, source, mapping, flush=True)
    return out


def _summed(values: list | None, data: dict) -> Decimal | None:
    """The finite |A|^2 summed over helicities and colours (the fixture's
    normalisation denominator: the initial averages and the final
    identical-particle factor)."""

    total = _total(values)
    if total is None:
        return None
    with localcontext() as context:
        context.prec = 80
        return total * data["normalization"]["denominator"]


def _signed(value: Decimal, sign: int) -> Decimal:
    return value.copy_negate() if sign < 0 else value  # (exact: no context rounding)


# The crossing finding (to the coordinator, for the public API / SDK owner):
# a crossing whose crossed values are exactly zero at every point.
CROSSING_FINDING = (
    "the public route returns status 'success' with |A|^2 exactly 0 at every crossed "
    "point (a "
    "negative-energy massless fermion leg), where the source's values are not zero: "
    "neither served nor "
    "refused typed (no document states a physical-momenta contract); the boson "
    "crossings at the same "
    "kind of negative-energy kinematics are served correctly; the tree spinors "
    "continue a negative-"
    "energy fermion of helicity h to the other chirality, so the loop plan likely "
    "fixes each fermion "
    "leg's chirality from positive energy (cause not established). Routed to the "
    "coordinator for the "
    "public-API / SDK owner; reproducer: li_manifest.py crossing --work-dir W (the "
    "source records "
    "from li_manifest.py run), then this entry"
)


def _crossing_side(
    arm: dict, source_arm: dict, sign: int, tdata: dict, sdata: dict
) -> dict:
    """One backend's crossing identity in binary64: sum |A_target|^2 at the
    crossed points against (-1)^(crossed fermions) sum |A_source|^2 within
    10 max(E_target, E_source) on the points both serve."""

    ratios, zeros, served = [], [], 0
    for p, crossed in enumerate(arm.get("points", [])):
        reference = source_arm["points"][p] if "points" in source_arm else None
        if (
            reference is None
            or crossed["status"] != "success"
            or reference["status"] != "success"
        ):
            continue
        served += 1
        lhs = _summed(crossed["values"], tdata)
        rhs = _signed(_summed(reference["values"], sdata), sign)
        zeros.append(lhs == 0 and rhs != 0)
        e = max(
            (_abs_finite(crossed["estimate"]) or 0.0)
            * tdata["normalization"]["denominator"],
            (_abs_finite(reference["estimate"]) or 0.0)
            * sdata["normalization"]["denominator"],
        )
        diff = abs(float(lhs - rhs))
        ratios.append(diff / (FACTOR * e) if e else (0.0 if not diff else math.inf))
    worst = max(ratios, default=None)
    if zeros and all(zeros):
        status = "partial"
    elif worst is None:
        status = "not run" if not arm.get("points") else "partial"
    elif worst > 1:
        status = "estimate miss"
    else:
        status = "pass" if served == len(arm.get("points", [])) else "partial"
    return {
        "status": status,
        "served": served,
        "of": len(arm.get("points", [])),
        "worst_ratio_to_10E": worst,
        "exactly_zero": bool(zeros) and all(zeros),
        **(
            {"failed_reasons": _reasons(arm)}
            if served < len(arm.get("points", []))
            else {}
        ),
    }


def judge_crossing(result: dict, records: dict[str, dict]) -> dict:
    """The crossing identity: sum |A_target|^2 at the crossed points =
    (-1)^(crossed fermions) sum |A_source|^2 at the source's points; binary64
    within 10 max(E_target, E_source) (each E the checked call's absolute
    estimate, summed like its value) on NinjaRS and on TIRust (each against
    the source's record of the same backend), NinjaRS double-double
    recorded. A crossing whose crossed values are exactly zero at every
    point where the source's are not is recorded partial with the finding
    (``CROSSING_FINDING``), never passed."""

    runs: dict[str, dict] = {}
    for c in result["crossings"]:
        label = f"{c['target']} <- {c['source']} {c['map']}"
        source = records.get(c["source"])
        if source is None:
            runs[label] = {"status": "not run", "reason": f"no record of {c['source']}"}
            continue
        sign = -1 if c["crossed_fermions"] % 2 else 1
        tdata, sdata = fixture(c["target"]), fixture(c["source"])
        ninjars = _crossing_side(
            c["arms"]["double"],
            source["arms"]["ninjars/double/checked"],
            sign,
            tdata,
            sdata,
        )
        devs = []
        for p, crossed in enumerate(c["arms"]["double-double"].get("points", [])):
            reference = high_arm(source["arms"], "ninjars")["points"][p]
            if crossed["status"] == "success" and reference["status"] == "success":
                rhs = _signed(_summed(reference["values"], sdata), sign)
                devs.append(_rel(_summed(crossed["values"], tdata), rhs))
        entry: dict[str, Any] = {
            "crossed_fermions": c["crossed_fermions"],
            **{k: v for k, v in ninjars.items() if k != "status"},
            "double_double_max_relative": max(devs, default=None),
        }
        statuses = [ninjars["status"]]
        if "tirust/double" in c["arms"]:
            tirust = _crossing_side(
                c["arms"]["tirust/double"],
                source["arms"]["tirust/double/checked"],
                sign,
                tdata,
                sdata,
            )
            entry["tirust"] = tirust
            statuses.append(tirust["status"])
        else:
            entry["tirust"] = {
                "status": "not run",
                "reason": "no TIRust arm in the crossing record",
            }
            statuses.append("partial")
        if ninjars["exactly_zero"]:
            entry["finding"] = CROSSING_FINDING
        entry["status"] = _worst(statuses)
        runs[label] = entry
    return {
        "row": "LI-W1/L1/P1/C1/S1 (C1, crossing; the id LI-C1 is the "
        "complex-mass-scheme row)",
        "processes": CROSSING_ROW,
        "status": _worst([r["status"] for r in runs.values()]) if runs else "not run",
        "runs": runs,
    }


# ------------------------------------------------------------- Fig. 7


# arXiv:1604.01363 Fig. 7 (comparison material, USER ~14:55): SPEC "fig7".
FIG7_ID = "arXiv:1604.01363 Fig. 7"
# The cumulative thresholds Delta of the comparison (10^-3 .. 10^-15).
FIG7_DECADES = range(3, 16)


def rambo(masses: list[float], energy: float, rng: Any) -> list[list[str]]:
    """A massive RAMBO point (Kleiss, Stirling, Ellis) at sqrt(s) =
    ``energy`` with massless beams along z, as binary64 strings: the
    calibration tool's massless RAMBO (``loop_v2_stability_calibration.
    _rambo``) rescaled to the masses by Newton on xi, iterated while the
    energy residual decreases (it converges monotonically from below; it
    stops at the binary64 fixed point); a residual beyond the rounding of
    the n energies (4 n u sqrt(s)) raises (never a silently off-shell
    point)."""

    from tools.loop_v2_stability_calibration import _rambo

    p = _rambo(len(masses), energy, rng)

    def residual(xi: float) -> float:
        return (
            sum(
                math.sqrt(m * m + (xi * v[0]) ** 2)
                for m, v in zip(masses, p, strict=True)
            )
            - energy
        )

    def slope(xi: float) -> float:
        return sum(
            xi * v[0] ** 2 / math.sqrt(m * m + (xi * v[0]) ** 2)
            for m, v in zip(masses, p, strict=True)
        )

    xi = math.sqrt(1 - (sum(masses) / energy) ** 2)
    f = residual(xi)
    while f:
        trial = xi - f / slope(xi)
        g = residual(trial)
        if abs(g) >= abs(f):
            break
        xi, f = trial, g
    if abs(f) > 4 * len(masses) * 2.0**-53 * energy:
        raise ValueError(f"RAMBO's massive rescaling left an energy residual {f}")
    final = [
        [math.sqrt(m * m + (xi * v[0]) ** 2)] + [xi * c for c in v[1:]]
        for m, v in zip(masses, p, strict=True)
    ]
    beams = [[energy / 2, 0.0, 0.0, energy / 2], [energy / 2, 0.0, 0.0, -energy / 2]]
    return [[repr(float(c)) for c in v] for v in beams + final]


def anchor_asymmetry(name: str, work: Path, record: dict | None = None) -> dict:
    """Per carrier (binary64, double-double) and fixture point the largest
    |anchor_0 - anchor_1| / (|anchor_0| + |anchor_1|) over the helicity
    rows of run ``name``'s two amplitude-basis anchors (finite part,
    NinjaRS), with the bound it is judged against: binary64 10 x the
    point's relative estimate (``record``'s NinjaRS binary64 checked arm),
    double-double the 1e-24 target (CARRIER)."""

    from pyamplicol import Runtime

    data = fixture(name)
    compiled = compile_model(data, work / "model-cache")
    artifact, _generation = generate(name, work, compiled)
    runtime = Runtime.load(
        artifact, process="p", model_parameters=run_parameters(data, compiled)
    )
    scales = [_decimal(Fraction(mu) ** 2) for mu in data["mu_r"]]
    record = record if record is not None else _load(work / name / "record.json")
    estimates = [
        (p.get("estimate") or {}).get("relative")
        for p in record["arms"]["ninjars/double/checked"]["points"]
    ]
    out: dict[str, Any] = {"run": name}
    for carrier in CARRIERS:
        result = runtime.evaluate_resolved(
            data["points"],
            mu_r2=scales,
            color_resolution="amplitude-basis",
            reduction="ninjars",
            poles="all",
            arithmetic=carrier,
        )
        if len(result.virtual_color_ids) != 2:
            out[carrier] = {"reason": f"anchors {result.virtual_color_ids}: not a pair"}
            continue
        points = []
        for p, values in enumerate(result.values):
            worst = 0.0
            for row in values[0]:
                # (exact in the carrier's digits: Decimal of the value)
                a, b = (Decimal(str(x.finite)) for x in row)
                if a or b:
                    worst = max(worst, float(abs(a - b) / (abs(a) + abs(b))))
            bound = (
                FACTOR * estimates[p]
                if carrier == "double" and estimates[p] is not None
                else (CARRIER if carrier != "double" else None)
            )
            points.append({"asymmetry": worst, "bound": bound})
        out[carrier] = {
            "anchors": list(result.virtual_color_ids),
            "points": points,
        }
    return out


def fabc_check(work: Path, check: dict) -> dict:
    """LI-27's f^abc check (SPEC ``colour_checks``): the run's anchor
    asymmetry within its bounds at every point and carrier (the f^abc part
    vanishes numerically), the control's beyond them at some point (the
    check sees an f^abc part); 'pass' when both hold, else 'fail'."""

    run, control = (anchor_asymmetry(check[k], work) for k in ("run", "control"))

    def within(result: dict) -> list[bool]:
        return [
            p["bound"] is not None and p["asymmetry"] <= p["bound"]
            for carrier in CARRIERS
            for p in result.get(carrier, {}).get("points", [])
        ]

    held, seen = within(run), within(control)
    status = "pass" if held and all(held) and not all(seen) else "fail"
    return {"status": status, "run": run, "control": control, "what": COLOUR["what"]}


def fig7(
    work: Path,
    counts: dict[str, int],
    own_scheme: bool = False,
    out: Path | None = None,
) -> dict:
    """The Fig. 7 comparison runs (SPEC "fig7"): per process (a fixture of
    a §4.1 row, ``counts`` points each) its artifact at the paper's scheme
    (``scheme_of``: MG5 defaults, massive b; ``own_scheme``: the fixture's
    own scheme and its campaign artifact), RAMBO points at sqrt(s) =
    ``energy`` (seeded), per helicity selection (initial helicities
    ``initial_helicity``, every final Z at the selection's) the binary64
    value with its estimate (``checks``) and the double-double value at the
    same binary64 inputs (the truth of the error); ``out`` is rewritten
    after each chunk (a stopped run keeps its points)."""

    import random

    from pyamplicol import Runtime
    from pyamplicol.api import VirtualStabilityChecks

    setup = spec()["fig7"]
    record: dict[str, Any] = {
        "setup": {k: v for k, v in setup.items() if k != "runs"},
        "own_scheme": own_scheme,
        "revision": _revision(),
        "native": _native(),
        "processes": {},
    }
    energy = float(Fraction(setup["energy"]))
    for name, count in counts.items():
        data = fixture(name)
        if own_scheme:
            label, run = name, data
        else:
            base = fixture(setup["scheme_of"])
            run = {
                **_derive(
                    base,
                    {
                        k: data[k]
                        for k in (
                            "pdgs",
                            "madloop_process",
                            "loop_orders",
                            "squared_orders",
                        )
                    },
                ),
                "name": f"fig7-{name}-{setup['scheme_of']}",
            }
            label = run["name"]
        compiled = compile_model(run, work / "model-cache")
        artifact, generation = generate(label, work, compiled, run)
        parameters = run_parameters(run, compiled)
        runtime = Runtime.load(artifact, process="p", model_parameters=parameters)
        final = len(data["pdgs"]) - data["initial"]
        wanted = {
            selection: (setup["initial_helicity"],) * data["initial"] + (h,) * final
            for selection, h in setup["selections"].items()
        }
        ids = {
            selection: [
                h.id for h in runtime.physics.helicities if tuple(h.values) == values
            ]
            for selection, values in wanted.items()
        }
        scheme = run["scheme_data"]
        masses = [math.sqrt(float(m)) for m in _final_masses2(run, compiled)]
        rng = random.Random(setup["seed"] + count)
        points = [rambo(masses, energy, rng) for _ in range(count)]
        scale = _decimal(Fraction(setup["mu_r"]) ** 2)
        entry: dict[str, Any] = {
            "points": 0,
            "requested": count,
            "scheme": scheme.get("description"),
            "generation": generation,
            "selections": {},
        }
        errors: dict[str, list] = {s: [] for s in ids}
        estimates: dict[str, list] = {s: [] for s in ids}
        seconds: dict[str, float] = {s: 0.0 for s in ids}
        chunk = setup["chunk"]
        for first in range(0, count, chunk):
            block = points[first : first + chunk]
            scales = [scale] * len(block)
            for selection, chosen in ids.items():
                start = time.perf_counter()
                b64 = runtime.evaluate(
                    block,
                    mu_r2=scales,
                    helicities=chosen,
                    poles="none",
                    reduction="ninjars",
                    stability_checks=VirtualStabilityChecks(
                        1, reduction_direction=True, rescaled=True
                    ),
                    on_failure="return",
                )
                dd = runtime.evaluate(
                    block,
                    mu_r2=scales,
                    helicities=chosen,
                    poles="none",
                    reduction="ninjars",
                    arithmetic="double-double",
                    on_failure="return",
                )
                seconds[selection] += time.perf_counter() - start
                for v, e, t, lane, lane_dd in zip(
                    b64.values,
                    b64.stability,
                    dd.values,
                    b64.diagnostics,
                    dd.diagnostics,
                    strict=True,
                ):
                    if lane.status != "success" or lane_dd.status != "success":
                        continue
                    value, truth = float(v[0].finite), float(t[0].finite)
                    errors[selection].append(
                        abs(value / truth - 1) if truth else abs(value)
                    )
                    estimates[selection].append(e.finite)
            entry["points"] = first + len(block)
            for selection, chosen in ids.items():
                entry["selections"][selection] = {
                    "helicity_ids": chosen,
                    "seconds": seconds[selection],
                    "errors": errors[selection],
                    "estimates": estimates[selection],
                }
            record["processes"][name] = entry
            if out is not None:
                out.write_text(json.dumps(record, indent=1) + "\n")
            print(name, entry["points"], flush=True)
    return record


def _final_masses2(data: dict, compiled: Any) -> list[Fraction]:
    """The final particles' squared masses at the fixture's parameters (the
    model's mass parameter of each PDG code; derived masses, e.g. m_W, from
    the fixture's derived parameters)."""

    particles = {int(r.pdg_code): r for r in compiled.ir.particles}
    parameters = {
        **(data.get("derived_parameters") or {}),
        **data["scheme_data"]["parameters"],
        **data["scheme_data"]["fixed_parameters"],
    }
    out = []
    for pdg in data["pdgs"][data["initial"] :]:
        mass = str(particles[abs(pdg)].mass)
        out.append(
            Fraction(0) if mass in ("ZERO", "0") else Fraction(parameters[mass]) ** 2
        )
    return out


def judge_fig7(results: list[dict]) -> dict:
    """The Fig. 7 figures: per run, process and selection the served
    points, the cumulative fractions of the true binary64 error (vs
    double-double) and of the binary64 estimate (the paper's plotted
    quantity is MadLoop's estimate) below 10^-3 .. 10^-15, the worst error
    and the worst error over its estimate; the setup, what is matched and
    what is not."""

    setup = spec()["fig7"]
    runs = []
    for result in results:
        processes = {}
        for name, entry in result["processes"].items():
            selections = {}
            for selection, data in entry["selections"].items():
                errors, estimates = data["errors"], data["estimates"]

                def below(values: list) -> dict:
                    return (
                        {
                            f"1e-{k:02d}": sum(x < 10.0**-k for x in values)
                            / len(values)
                            for k in FIG7_DECADES
                        }
                        if values
                        else {}
                    )

                selections[selection] = {
                    "served": len(errors),
                    "error_below": below(errors),
                    "estimate_below": below(estimates),
                    "max_error": max(errors, default=None),
                    "max_estimate": max(estimates, default=None),
                    "max_error_over_estimate": max(
                        (
                            x / y if y else math.inf
                            for x, y in zip(errors, estimates, strict=True)
                        ),
                        default=None,
                    ),
                }
            processes[name] = {
                "points": entry["points"],
                "selections": selections,
                "generation_seconds": (entry.get("generation") or {}).get("seconds"),
            }
        runs.append(
            {
                "scheme": "the fixture's own scheme (loop_sm no_b_mass: NOT the "
                "paper's, b massless)"
                if result["own_scheme"]
                else f"{setup['scheme_of']}'s: {setup['scheme_note']}",
                "matched": not result["own_scheme"],
                "native": result.get("native"),
                "processes": processes,
            }
        )
    return {
        "status": "recorded",
        "source": setup["source"],
        "comparison_material": setup["comparison_material"],
        "setup": {
            "pyamplicol": "NinjaRS per amplitude, binary64 value + estimate ("
            + setup["checks"]
            + "), double-double at the same binary64 inputs as the truth",
            "matched": "processes, single-helicity selections, sqrt(s) = 1 TeV, no "
            "cuts, RAMBO points, "
            "binary64 reduction, a direction + rotation stability estimate; the "
            "paper's MG5 default "
            "parameters with massive b (the 'matched' runs)",
            "not matched": "point counts (here 200 / 50 / 50 or 100 vs 100K / 10K / "
            "1K), MadLoop's exact "
            "estimate (its loop-direction test reverses the propagators; here the "
            "re-test and one "
            "rotation), the curves themselves (an image: features compared only)",
        },
        "runs": runs,
    }


# ---------------------------------------------- LI-B1: the Born-interfered L6

# R8 (DECISIONS 2026-11-07 21:50): lit-val extends LI-B1's Born-interfered L6
# to the other campaigns of PLAN §4.1 (M-QCD, M-SM incl. CMS, decay XX01-08;
# HC through ``public_l6``), lane by lane (every lane, every Laurent order,
# NinjaRS vs TIRust). Each row's executor is its campaign's own generation
# (``mqcd.Campaign``), at its tier points and the forward points.
#
# Binary64 in two stages. The SCREEN is lit-tir's per-lane comparison: its
# ``scripts/li_b1.py`` (``--lanes-script``, a path argument: lit-tir's scratch
# script, not a module of this tree; its sha256 is recorded) evaluates each
# point's lanes with the reduction-direction re-test (``lanes``), E = the
# re-test's deviation, floor 4 u of the lane's scale (its MARGIN, FLOOR). A
# point set with a lane beyond 10 x that estimate, or deviating >= LAX
# relative (a lane the 08:31 rule could fail), is judged entirely under the
# L6 estimate of ruling (6) / R3 (b) (RULED): the one E configuration
# (``backends.checks()``: three generic rotations and the rescaled re-test,
# as the executor's ``runs`` evaluates them), per lane the stability module's
# combination, through the one comparison (``backends._compare``). The
# reduction-direction re-test alone misses the masters' own rounding (DESIGN
# §10.4), so it only selects; a set it passes has no lane beyond 10 x it and
# none >= LAX, which no estimate can fail (08:31).
BORN = _load(SPEC)["born_l6"]
SCREEN = "screen: lit-tir's lanes (reduction-direction re-test, floor 4 u of the lane)"
RULED = (
    "L6 estimate (ruling (6), R3 (b)): backends.checks(), three generic rotations "
    "and the rescaled re-test, per lane E = SAFETY x (largest rotation deviation + "
    "rescaled re-test deviation) + FLOOR_UNITS u |lane| (stability.StabilityEstimate), "
    "per Laurent coefficient through backends._compare"
)
# §4.1 LI-27's numerical f^abc check, the §4.1 checks not run and those a user
# ruling makes not applicable (SPEC; e.g. LI-24's lambda_hhh scan, USER
# 2026-11-09 ~08:42).
COLOUR = _load(SPEC)["colour_checks"]
UNRUN = _load(SPEC)["unrun_checks"]
NOT_APPLICABLE = _load(SPEC).get("not_applicable_checks", {})


def lanes_module(path: Path) -> Any:
    """lit-tir's ``li_b1.py`` at ``path`` (``lanes``, ``MARGIN``, ``FLOOR``),
    with its sha256 as ``SHA256`` (recorded in each row's record)."""

    import hashlib
    import importlib.util

    found = importlib.util.spec_from_file_location("lit_tir_li_b1", path)
    if found is None or found.loader is None:
        raise ValueError(f"{path}: not a Python script")
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    module.SHA256 = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return module


class _Carrier:
    """A native executor whose batches run in ``precision`` (lit-tir's
    ``lanes`` evaluates at the executor's default carrier, binary64)."""

    def __init__(self, executor: Any, precision: Any):
        self._executor, self._precision = executor, precision

    def _evaluated(self, points, scales, parameters, _precision, *rest):
        return self._executor._evaluated(
            points, scales, parameters, self._precision, *rest
        )

    @property
    def last_report(self) -> dict:
        return self._executor.last_report


def ruled_lanes(
    executor: Any, points: list, scales: list, parameters: Any, backend: str
) -> tuple[list[dict], float]:
    """The binary64 lanes of ``points`` on ``backend`` with the L6 estimate
    (RULED): the executor's ``runs`` with ``backends.checks()`` (the
    reference evaluation re-tested in the rescaled frame and the rotated
    points, exact as production rotates them), per point its ``direct``
    lanes, per lane and Laurent coefficient its estimate (``estimate``:
    ``StabilityEstimate.from_checks`` with the lane as its sector, so S =
    |lane|) and the ``virtual`` totals; a point the reference or a check run
    fails is ``failed`` with its typed reasons (production fails it so with
    these checks). Returns the points and the seconds."""

    from pyamplicol.loops.v2.stability import ROTATION, Budget, StabilityEstimate

    stability = backends.checks().to_checks()
    start = time.perf_counter()
    precision, evaluations, rotated, failures = executor.runs(
        points,
        scales,
        parameters=parameters,
        poles="all",
        stability=stability,
        reduction=backend,
    )
    seconds = time.perf_counter() - start

    def deviations(other: dict, lanes: dict) -> dict:
        return {
            lane: Budget(
                tuple(
                    float(abs(a - b))
                    for a, b in zip(
                        value,
                        other[lane] if lane in other else [0 * x for x in value],
                        strict=True,
                    )
                )
            )
            for lane, value in lanes.items()
        }

    out: list[dict] = []
    for index, evaluation in enumerate(evaluations):
        if index in failures:
            out.append({"failed": list(failures[index])})
            continue
        direct = {k: v.coefficients for k, v in evaluation.families.items()}
        retest = {k: v.coefficients for k, v in evaluation.retest_families.items()}
        budgets = {stability.reduction: deviations(retest, direct)}
        for k, runs in enumerate(rotated):
            moved = {lane: v.coefficients for lane, v in runs[index].families.items()}
            budgets[ROTATION.format(k)] = deviations(moved, direct)
        sizes = {
            lane: Budget(tuple(float(abs(x)) for x in v)) for lane, v in direct.items()
        }
        absolute = (
            StabilityEstimate.from_checks(
                sizes, budgets, scale=sizes, roundoff=precision.unit_roundoff
            ).absolute
            if direct
            else {}
        )
        out.append(
            {
                "direct": direct,
                "estimate": {lane: absolute[lane].coefficients for lane in direct},
                "virtual": {
                    str(o): [
                        complex(x) if x is not None else None for x in v.coefficients
                    ]
                    for o, v in evaluation.result.components["virtual"].items()
                },
            }
        )
    return out, seconds


def _lane_terms(
    n: dict, t: dict, lane: Any, margin: float, floor: float
) -> tuple[float, float, float] | None:
    """One lane's (deviation, scale, ratio to 10 x the estimate): the screen
    (entries with ``check``: E = the lane's largest re-test deviation,
    floor ``floor`` x its scale) or the L6 estimate (entries with
    ``estimate``: per Laurent coefficient through ``backends._compare``, the
    ratio its largest difference / bound); None without an estimate."""

    a, b = n["direct"][lane], t["direct"].get(lane)
    scale = float(max(abs(x) for x in a))
    if b is None:
        return None
    deviation = float(max(abs(x - y) for x, y in zip(a, b, strict=True)))
    if "estimate" in n:
        e_n, e_t = n["estimate"].get(lane), t["estimate"].get(lane)
        if e_n is None or e_t is None:
            return None

        def arm(values, errors) -> list:
            return [
                [
                    (
                        backends.COEFFICIENTS[k],
                        (Decimal(complex(x).real), Decimal(complex(x).imag)),
                        e,
                    )
                    for k, (x, e) in enumerate(zip(values, errors, strict=True))
                ]
            ]

        rows = backends._compare(arm(a, e_n), arm(b, e_t), True)
        ratio = max(
            (
                r["difference"] / r["bound"]
                if r["bound"]
                else (math.inf if r["difference"] else 0.0)
            )
            for r in rows
        )
        return deviation, scale, ratio
    checked = (n["check"].get(lane), t["check"].get(lane))
    if None in checked:
        return None
    e_n = float(max(abs(x - y) for x, y in zip(a, checked[0], strict=True)))
    e_t = float(max(abs(x - y) for x, y in zip(b, checked[1], strict=True)))
    larger = max(e_n, e_t, floor * scale)
    ratio = (
        deviation / (margin * larger) if larger else (math.inf if deviation else 0.0)
    )
    return deviation, scale, ratio


def compare_lanes(found: dict[str, list], margin: float, floor: float) -> dict:
    """The per-lane L6 over ``found`` (backend -> per point its lanes: the
    screen's ``lanes`` output or ``ruled_lanes``', ``_lane_terms``): lanes
    compared, beyond 1x / 10x the larger estimate, the worst ratio to 10x
    and the worst relative deviation (of all lanes and of those beyond
    10x), lanes served without an estimate, failed points and typed reasons
    per backend, the virtual totals' largest relative difference.

    A lane beyond 10x whose deviation is within ``margin`` x ``floor`` of
    the point's lane scale (the largest coefficient of any lane at the
    point, both backends: the magnitude the lanes' terms carry) is counted
    a numerical zero at the carrier's resolution (lit-val's reading of Q13
    and R5, for the coordinator: the lane is a cancellation at that
    resolution and its own estimate reproduces the cancellation's rounding
    or 0, so the 10x rule cannot judge it): counted in ``beyond_10x`` and
    ``beyond_10x_zero`` with its deviation relative to the point's lane
    scale (``worst_zero_point_relative``), and left out of
    ``worst_beyond_10x``; ``beyond`` lists every lane beyond 10x (point,
    lane, ratio, both relative deviations)."""

    out = {
        "lanes": 0,
        "beyond_1x": 0,
        "beyond_10x": 0,
        "worst_over_10x": 0.0,
        "worst_deviation": 0.0,
        "worst_beyond_10x": 0.0,
        "no_estimate": 0,
        "failed_points": {b: 0 for b in BACKENDS},
        "failed": {b: [] for b in BACKENDS},
        "virtual_max_relative": 0.0,
        "beyond_10x_zero": 0,
        "worst_zero_point_relative": 0.0,
        "beyond": [],
    }
    for k, (n, t) in enumerate(zip(found["ninjars"], found["tirust"], strict=True)):
        for backend, value in (("ninjars", n), ("tirust", t)):
            if "failed" in value:
                out["failed_points"][backend] += 1
                out["failed"][backend].extend(str(r) for r in value["failed"])
        if "failed" in n or "failed" in t:
            continue
        point_scale = max(
            (
                float(abs(x))
                for side in (n, t)
                for lane in side["direct"].values()
                for x in lane
            ),
            default=0.0,
        )
        for lane in n["direct"]:
            terms = _lane_terms(n, t, lane, margin, floor)
            if terms is None:
                out["no_estimate"] += 1
                continue
            deviation, scale, ratio = terms
            relative = deviation / scale if scale else deviation
            out["lanes"] += 1
            out["beyond_1x"] += ratio * margin > 1
            out["beyond_10x"] += ratio > 1
            out["worst_over_10x"] = max(out["worst_over_10x"], ratio)
            out["worst_deviation"] = max(out["worst_deviation"], relative)
            if ratio > 1:
                zero = deviation <= margin * floor * point_scale
                against = deviation / point_scale if point_scale else deviation
                out["beyond"].append(
                    {
                        "point": k,
                        "lane": compact_detail(str(lane)),
                        "over_10x": ratio,
                        "relative": relative,
                        "point_relative": against,
                        "zero": zero,
                    }
                )
                if zero:
                    out["beyond_10x_zero"] += 1
                    out["worst_zero_point_relative"] = max(
                        out["worst_zero_point_relative"], against
                    )
                else:
                    out["worst_beyond_10x"] = max(out["worst_beyond_10x"], relative)
        for order, a in n["virtual"].items():
            b = t["virtual"][order]
            scale = max((abs(x) for x in a if x is not None), default=0.0)
            if scale:
                difference = max(
                    abs(x - y) for x, y in zip(a, b, strict=True) if x is not None
                )
                out["virtual_max_relative"] = max(
                    out["virtual_max_relative"], difference / scale
                )
    out["failed"] = {
        b: _counted(compact_detail(r) for r in v) for b, v in out["failed"].items()
    }
    return out


def screened(result: dict) -> bool:
    """Whether a screen comparison needs the L6 estimate: a lane beyond 10x
    its re-test estimate, or one deviating >= LAX relative (the lanes the
    08:31 rule could fail)."""

    return bool(result["beyond_10x"]) or result["worst_deviation"] >= LAX


def born_verdict(result: dict) -> str:
    """A comparison's verdict (DECISIONS 2026-11-08 08:31): 'fail' on a lane
    beyond 10x deviating >= ~1e-5 relative (LAX; numerical-zero lanes,
    ``compare_lanes``, excepted) or served without an estimate; 'pass (lax)'
    with lanes beyond 10x all below it or numerical zeros; 'partial' where a
    backend failed points (closed, typed) and the rest passes, or no lane
    was compared; else 'pass'."""

    if result["no_estimate"] or result["worst_beyond_10x"] >= LAX:
        return "fail"
    if any(result["failed_points"].values()) or not result["lanes"]:
        return "partial"
    return "pass (lax)" if result["beyond_10x"] else "pass"


def _parts(x: Any) -> tuple[Decimal, Decimal]:
    """A carrier value's (real, imaginary) parts as exact Decimals (binary64
    ``complex`` or ``reference_executor.Complex`` of Decimal)."""

    return Decimal(x.real), Decimal(x.imag)


def _carrier_distance(a: Any, b: Any) -> float:
    """|a - b| formed in the carrier's digits (no binary64 truncation)."""

    (ar, ai), (br, bi) = _parts(a), _parts(b)
    with localcontext() as context:
        context.prec = 80
        return float(backends._modulus((ar - br, ai - bi)))


def judge_truth(
    result: dict,
    found: dict[str, list],
    high: dict[str, list],
    points: list[int],
    margin: float,
    floor: float,
) -> None:
    """A failing binary64 comparison (``result`` of ``compare_lanes`` on
    ``found``) against the double-double lanes ``high`` at its failing
    ``points`` (ruling (7): a consistent truth first): per lane beyond 10x
    at or above LAX, where both backends' double-double values agree (their
    difference formed in the carrier) to within 1 / ``margin`` of the
    binary64 deviation under test, each backend's binary64 error against
    them relative to the lane and its estimate (relative to the lane: the
    L6 estimate's largest coefficient where ``found`` carries it, else the
    re-test's, floor ``floor`` x the lane's scale); a backend whose error
    exceeds ``margin`` x its estimate has an estimate miss. Every such lane
    explained by an estimate miss makes the status 'estimate miss' (a
    stability finding, the backend named), otherwise it stays 'fail'."""

    truths, explained = [], True
    for b in result["beyond"]:
        if b["zero"] or b["relative"] < LAX:
            continue
        k = points.index(b["point"])
        entry: dict[str, Any] = {"point": b["point"], "lane": b["lane"]}
        sides = [high[backend][k] for backend in BACKENDS]
        if any("failed" in side for side in sides):
            entry["truth"] = "a backend fails the point closed in double-double"
            truths.append(entry)
            explained = False
            continue
        key = next(x for x in sides[0]["direct"] if compact_detail(str(x)) == b["lane"])
        dd = [side["direct"][key] for side in sides]
        scale = max(_carrier_distance(x, 0) for x in dd[0]) or 1.0
        agreement = (
            max(_carrier_distance(x, y) for x, y in zip(*dd, strict=True)) / scale
        )
        entry["double_double_backends_relative"] = agreement
        if agreement * margin > b["relative"]:
            entry["truth"] = (
                "the backends' double-double values disagree beyond a tenth of "
                "the binary64 deviation under test"
            )
            truths.append(entry)
            explained = False
            continue
        missed = []
        for backend in BACKENDS:
            value = found[backend][b["point"]]
            a = [complex(x) for x in value["direct"][key]]
            own = max(abs(x) for x in a) or 1.0
            if "estimate" in value:
                estimate = max(value["estimate"][key]) / own
            else:
                c = [complex(x) for x in value["check"][key]]
                bound = max(abs(x - y) for x, y in zip(a, c, strict=True)) / own
                estimate = max(bound, floor)
            error = (
                max(abs(x - complex(y)) for x, y in zip(a, dd[0], strict=True)) / own
            )
            entry[backend] = {"error": error, "estimate": estimate}
            if error > margin * estimate:
                missed.append(backend)
        entry["estimate_miss"] = missed
        explained = explained and bool(missed)
        truths.append(entry)
    result["truth"] = truths
    if truths and explained:
        result["status"] = "estimate miss"
        result["estimate_miss"] = {
            backend: sum(backend in t["estimate_miss"] for t in truths)
            for backend in BACKENDS
        }


def forward_points(run: Any, values: list[str], digits: int = DIGITS) -> tuple | str:
    """The forward points of a 2 -> 2 row (§4.1 LI-B1's theta rows): at the
    angles ``values`` (pT-defined: pt = theta sqrt(s_target) / 2, the CM
    angle theta / beta for massive final states), sqrt(s_target) the 2^x 5^y
    nearest the row's first reference point's, its scale; massless beams and
    the row's equal final masses (the model's, ``assemble._leg_masses``) in
    ``_pair``'s exact construction. Returns the points, scales and their
    figures (``sqrt_s_target``, per point the constructed ``sqrt_s`` and the
    CM angle ``cm_theta``), or a reason (str) where the row has no such
    construction."""

    from pyamplicol.loops.v2.assemble import _leg_masses

    with localcontext() as context:
        # a derived mass (``_model_masses``: ``digits`` digits) squared, as a
        # terminating decimal of ``digits`` significant digits (the shell
        # then holds to ~10^-digits, below every carrier)
        context.prec = digits
        masses = [
            Fraction(+Decimal(m.numerator) / Decimal(m.denominator))
            for m in _leg_masses(run.slice, run.parameters, digits)
        ]
    if len(masses) != 4 or masses[0] or masses[1] or masses[2] != masses[3]:
        return (
            "no forward construction: not 2 -> 2 with massless beams and equal "
            "final masses"
        )
    point = [[Fraction(Decimal(c)) for c in p] for p in run.reference.points[0]]
    total = [p[0][k] + p[1][k] for p in [point] for k in range(4)]
    s = total[0] ** 2 - sum(c * c for c in total[1:])
    energy = _near(math.sqrt(float(s)))
    out = []
    for text in values:
        pt = Fraction(Decimal(text)) * energy / 2
        ratio = float(energy) / math.sqrt(float(masses[2] + pt * pt))
        if ratio < 2:
            return (
                f"no forward construction: sqrt(s) = {float(energy)} below the pair "
                "threshold"
            )
        out.append(_pair(masses[2], pt, _near(_rho(ratio))))
    figures: dict[str, Any] = {
        "sqrt_s_target": float(energy),
        "sqrt_s": [],
        "cm_theta": [],
    }
    for q in out:
        s_q = (q[0][0] + q[1][0]) ** 2 - (q[0][3] + q[1][3]) ** 2
        p_cm = math.sqrt(float(s_q / 4 - masses[2]))
        figures["sqrt_s"].append(math.sqrt(float(s_q)))
        figures["cm_theta"].append(math.asin(float(q[2][1]) / p_cm))
    points = [[[_decimal(Fraction(c)) for c in p] for p in q] for q in out]
    return points, [run.reference.scales[0]] * len(points), figures


def born_l6(
    campaign: Any,
    name: str,
    module: Any,
    *,
    forward: list[str] = BORN["forward"]["values"],
    high_points: int = BORN["high_points"],
) -> dict:
    """LI-B1's L6 of campaign row ``name``: lanes on both backends
    (reduction requested explicitly per call, ``reduction.running``) in
    binary64 at the row's tier points and its forward points (the screen,
    then the L6 estimate where it flags a lane, ``screened``), and in
    double-double at its first ``high_points`` tier points and the forward
    points (lit-tir's lanes, floor the 1e-24 target, R5); a binary64 set
    still failing is judged against its double-double truth
    (``judge_truth``)."""

    from pyamplicol.loops.v2.assemble import Precision

    row = campaign.rows[name]
    record: dict[str, Any] = {
        "row": name,
        "process": row.process,
        "native": _native(),
        "lanes_script": {
            "source": "lit-tir's workspace/tmp/lit-tir/scripts/li_b1.py",
            "sha256": getattr(module, "SHA256", None),
        },
    }
    if not row.active:
        reason = (
            "composite row: no evaluation of its own; its single-process "
            "variants are compared (mqcd.py STATUSES)"
            if row.status == "composite"
            else f"{row.status}: {row.pending}"
        )
        return {**record, "status": "not run", "reason": reason}
    if row.route == "public":
        return {
            **record,
            "status": "not run",
            "reason": f"public-route variant of {row.base}: its request and plan are "
            "the "
            "tools-route base row's (compared there); the public route is the artifact "
            "path",
        }
    start = time.perf_counter()
    run = campaign.run(name)
    record["generate_seconds"] = round(time.perf_counter() - start, 2)
    indices = sorted({i for tier in row.points for i in row.tier_points(tier)})
    sets = {
        "reference": (
            indices,
            [run.reference.points[i] for i in indices],
            [run.reference.scales[i] for i in indices],
        )
    }
    built = forward_points(run, forward)
    if isinstance(built, str):
        record["forward"] = built
    else:
        sets["forward"] = (forward, built[0], built[1])
        record["forward_points"] = built[2]
    carriers = {
        "double": (None, module.FLOOR),
        "double-double": (Precision.double_double(), CARRIER),
    }
    for label, (where, points, scales) in sets.items():
        for carrier, (precision, floor) in carriers.items():
            # (the forward points in double-double too: binary64 fails them
            # closed where the Gram conditioning is the stress)
            take = (
                len(points)
                if precision is None or label != "reference"
                else min(high_points, len(points))
            )
            executor = (
                run.executor if precision is None else _Carrier(run.executor, precision)
            )
            found, seconds = {}, {}
            for backend in BACKENDS:
                found[backend], _counts, seconds[backend] = module.lanes(
                    executor, points[:take], scales[:take], run.parameters, backend
                )
            result = compare_lanes(found, module.MARGIN, floor)
            result["estimate"] = SCREEN
            if precision is None and screened(result):
                screen = {
                    k: result[k]
                    for k in ("beyond_10x", "worst_over_10x", "worst_deviation")
                }
                for backend in BACKENDS:
                    found[backend], seconds[f"{backend}/checks"] = ruled_lanes(
                        run.executor,
                        points[:take],
                        scales[:take],
                        run.parameters,
                        backend,
                    )
                result = compare_lanes(found, module.MARGIN, floor)
                result["estimate"] = RULED
                result["screen"] = screen
            result["points"] = list(where[:take])
            result["seconds"] = {b: round(v, 2) for b, v in seconds.items()}
            result["status"] = born_verdict(result)
            if precision is None and result["status"] == "fail":
                # ruling (7): a consistent truth before a defect: the
                # double-double lanes at the failing points
                failing = sorted(
                    {
                        b["point"]
                        for b in result["beyond"]
                        if not b["zero"] and b["relative"] >= LAX
                    }
                )
                high = _Carrier(run.executor, Precision.double_double())
                truth_found = {
                    backend: module.lanes(
                        high,
                        [points[k] for k in failing],
                        [scales[k] for k in failing],
                        run.parameters,
                        backend,
                    )[0]
                    for backend in BACKENDS
                }
                judge_truth(result, found, truth_found, failing, module.MARGIN, floor)
            record.setdefault("sets", {}).setdefault(label, {})[carrier] = result
    record["status"] = _worst(
        [c["status"] for s in record["sets"].values() for c in s.values()]
    )
    return record


def public_l6(runtime: Any, points: list, scales: list, high_points: int) -> dict:
    """LI-B1's L6 on a public-route artifact (the HC rows: no tools-route
    executor): both backends requested explicitly per call, binary64 with
    the checks (``backends.checks()``) through the one comparison
    (``backends._compare``, |T - N| <= 10 max(E_N, E_T) per Laurent
    coefficient), double-double without checks at the first
    ``high_points`` points (1e-24 of the sector's largest coefficient, a
    target, R5); a miss below ~1e-5 relative is 'pass (lax)' (08:31)."""

    from tools.loop_v2_observables_backends import _compare

    out: dict[str, Any] = {}
    for carrier, checked, count in (
        ("double", True, len(points)),
        ("double-double", False, min(high_points, len(points))),
    ):
        arms = {
            b: _call(
                runtime,
                points[:count],
                scales[:count],
                backend=b,
                arithmetic=carrier,
                checked=checked,
                digits=DIGITS,
            )
            for b in BACKENDS
        }
        rows, failed = [], {}
        served = {b: _served(arms[b]) for b in BACKENDS}
        for b in BACKENDS:
            if "refused" in arms[b]:
                failed[b] = {arms[b]["refused"]: count}
            elif not all(served[b]):
                failed[b] = _reasons(arms[b])
        for k in range(count):
            if not all(k < len(served[b]) and served[b][k] for b in BACKENDS):
                continue
            n, t = (arms[b]["points"][k] for b in BACKENDS)
            for row in _compare(_entries(n), _entries(t), carrier == "double"):
                row["point"] = k
                rows.append(row)
        misses = [r for r in rows if not r["passed"]]
        real = [
            r
            for r in misses
            if r["difference"]
            > LAX * max(abs(complex(*map(float, r["ninjars"]))), 1e-300)
        ]
        status = "fail" if real else ("pass (lax)" if misses else "pass")
        if (failed or not rows) and status != "fail":
            status = "partial"
        out[carrier] = {
            "status": status,
            "points": count,
            "coefficients": len(rows),
            "beyond_bound": len(misses),
            "worst_over_bound": max(
                (
                    r["difference"] / r["bound"] if r["bound"] else math.inf
                    for r in rows
                    if r["difference"]
                ),
                default=0.0,
            ),
            "worst_relative": max(
                (
                    r["difference"] / abs(complex(*map(float, r["ninjars"])))
                    for r in rows
                    if r["difference"] and abs(complex(*map(float, r["ninjars"])))
                ),
                default=0.0,
            ),
            "served": {b: sum(served[b]) for b in BACKENDS},
            "failed": failed,
            "reduction": sorted(
                {
                    tuple(p["reduction"])
                    for b in BACKENDS
                    for p in arms[b].get("points", [])
                    if p.get("reduction")
                }
            ),
            "seconds": {b: round(arms[b].get("seconds", 0.0), 2) for b in BACKENDS},
        }
    return out


def born_l6_hc(
    work: Path, ufo: Path, names: list[str] | None = None
) -> dict[str, dict]:
    """LI-B1's L6 on the HC rows (tools/loop_reference/hc_nlo_x0.json, each
    generated as its nightly test does, ``test_loop_v2_hc._generate``) at
    every card's fixture points (exact decimals, the card's parameters)."""

    from tests.unit import test_loop_v2_hc as hc

    card = hc._card()
    work.mkdir(parents=True, exist_ok=True)
    out = {}
    for row in card["rows"]:
        if names and row["id"] not in names:
            continue
        record: dict[str, Any] = {
            "row": row["id"],
            "process": row["process"],
            "native": _native(),
        }
        start = time.perf_counter()
        runtime = hc._generate(ufo, card, row, work)
        record["generate_seconds"] = round(time.perf_counter() - start, 2)
        fixture = _load(hc.FIXTURES / f"{row['id'].lower()}.json")
        for c, entry in enumerate(fixture["cards"]):
            runtime.set_model_parameters(
                {
                    k: v
                    for k, v in entry["parameters"].items()
                    if k not in card["fixed_parameters"]
                }
            )
            points = [fixture["points"][v["point"]] for v in entry["values"]]
            scales = [str(Decimal(v["mu_r"]) ** 2) for v in entry["values"]]
            record.setdefault("sets", {})[f"card-{c}"] = public_l6(
                runtime, points, scales, BORN["high_points"]
            )
        record["status"] = _worst(
            [r["status"] for s in record["sets"].values() for r in s.values()]
        )
        out[row["id"]] = record
    return out


def born_summary(records: dict[str, dict]) -> dict:
    """LI-B1's campaign rows in data/lit.json: per campaign the verdict
    tally and per row its figures per point set and carrier, the typed
    reasons of the points each backend fails closed merged over them
    (``failed_reasons``: per backend, per reason, its lane count)."""

    out: dict[str, Any] = {}
    for key, record in sorted(records.items()):
        campaign = key.split("/", 1)[0]
        entry = out.setdefault(campaign, {"tally": {}, "rows": {}})
        status = record["status"]
        entry["tally"][status] = entry["tally"].get(status, 0) + 1
        compact: dict[str, Any] = {"status": status, "process": record["process"]}
        if "reason" in record:
            compact["reason"] = record["reason"]
        merged: dict[str, dict[str, int]] = {}
        for label, carriers in (record.get("sets") or {}).items():
            for carrier, r in carriers.items():
                for backend, reasons in (r.get("failed") or {}).items():
                    into = merged.setdefault(backend, {})
                    for reason, n in reasons.items():
                        into[reason] = into.get(reason, 0) + n
                if "coefficients" in r:  # a public-route row (public_l6)
                    compact[f"{label}/{carrier}"] = {
                        k: v
                        for k, v in r.items()
                        if k not in ("reduction", "seconds", "failed")
                    }
                    continue
                # (records written before the numerical-zero split carry no
                # ``beyond_10x_zero``: the split re-classifies 'fail' only;
                # those before the L6 estimate stage no ``estimate``: the
                # screen judged them, and flagged none at or above LAX)
                compact[f"{label}/{carrier}"] = {"estimate": SCREEN} | {
                    k: r[k]
                    for k in (
                        "status",
                        "estimate",
                        "screen",
                        "points",
                        "lanes",
                        "beyond_10x",
                        "worst_over_10x",
                        "worst_deviation",
                        "worst_beyond_10x",
                        "beyond_10x_zero",
                        "worst_zero_point_relative",
                        "truth",
                        "estimate_miss",
                        "no_estimate",
                        "failed_points",
                        "virtual_max_relative",
                    )
                    if k in r
                }
        if any(merged.values()):
            compact["failed_reasons"] = {b: v for b, v in merged.items() if v}
        for field in ("forward", "forward_points"):
            if field in record:
                compact[field] = record[field]
        entry["rows"][record["row"]] = compact
    return out


# ------------------------------------------------------------- data/lit.json


# Records of the rows other packages run and of findings on the references
# (data/lit.json's delegated ids; a check a finding names is a reference
# defect, not a pyAmpliCol failure).
DELEGATED_RECORDS = EXTRA / "records" / "delegated.json"
# The identity rows (§4.1 "LI-W1, L1, P1, C1, S1"): the check of every run
# each stands on (W1: L4, the fixture-point and generation-time Ward /
# Goldstone probes; L1: the
# exact Lorentz transform; P1: the amplitude poles), C1 the crossing
# (``crossing``, id CROSSING_ID), S1 the N_f rows (LI-A5's runs with and
# without the top loop).
IDENTITIES = _load(SPEC)["identities"]["checks"]
FLAVOUR_ROW = _load(SPEC)["identities"]["flavour_row"]


def lit(
    records: dict[str, dict],
    entries: list[dict],
    source: str,
    limit_results: dict | None = None,
    delegated: dict | None = None,
    crossing_result: dict | None = None,
    madloop: dict | None = None,
    fig7_result: dict | None = None,
    born: dict[str, dict] | None = None,
    fabc: dict | None = None,
) -> dict:
    """data/lit.json: per registry key its status, reference deviations
    (binary64, NinjaRS; the analytic oracle's too), points and per-check
    figures over its runs (with LI-A7's heavy-top scan as L9 of its rows'
    runs, ``limit_results``, and LI-A1's HEFT ratio); per §4.1 id under
    ``ids``, the identity rows from every run's checks, the crossing
    evaluations (``crossing_result``), the stress points with MadLoop QP
    (``madloop``, ``stress_madloop``), the arXiv:1604.01363 Fig. 7
    comparison (``fig7_result``) and the delegated rows from their
    records."""

    delegated = _load(DELEGATED_RECORDS) if delegated is None else delegated
    findings = delegated.get("findings", {})
    by_fixture = {e["fixture"]: e for e in entries}
    judged = {
        name: judge(record, by_fixture[name])
        for name, record in records.items()
        if name in by_fixture
    }
    ratio_rows = {e["fixture"] for e in entries if HEFT_RATIO_ROW in e["ids"]}
    for name, result in (limit_results or {}).items():
        if name in judged:
            judged[name]["L9"] = dict(result)
            if name in ratio_rows and LIMIT_ROW not in by_fixture[name]["ids"]:
                # LI-A1's HEFT ratio is reported (§4.1), not a limit rule.
                judged[name]["L9"]["status"] = "recorded"
    for name, checks in findings.items():
        for check, finding in checks.items():
            if name in judged and check in judged[name]:
                _apply_finding(judged[name][check], finding)
    rows: dict[str, dict] = {}
    ids_of = {r["key"]: r.get("ids") or [] for r in registry()["rows"]}
    for key, fixtures in registry_runs(entries).items():
        done = [f for f in fixtures if f in judged]
        if not fixtures:
            # a row of another package's (``DELEGATED``): its record's status
            # and reason (e.g. LI-X1, lit-eft's run-only check outside L6)
            for i in ids_of.get(key, []):
                if i in DELEGATED and i in delegated:
                    rows[key] = {
                        "status": f"{delegated[i]['status']} ({delegated[i]['owner']})",
                        "references": {},
                        "points": None,
                        "note": delegated[i]["source"],
                        "source": f"{DELEGATED_RECORDS.relative_to(WT)} {i}",
                    }
            continue
        if not done:
            rows[key] = {
                "status": "not run",
                "references": {},
                "points": 0,
                "note": "no run record: " + ", ".join(fixtures),
                "source": source,
            }
            continue
        rows[key] = _merge(key, done, judged, fixtures, source)
    ids: dict[str, dict] = {}
    for entry in entries:
        if entry["fixture"] not in judged:
            continue
        # The stress fixtures (PLAN §4.1 "Stress points") are their own
        # validation-only entry, not their base row's.
        for i in ["stress"] if "stress" in entry["tiers"] else entry["ids"]:
            ids.setdefault(i, {"runs": {}})["runs"][entry["fixture"]] = judged[
                entry["fixture"]
            ]
    for value in ids.values():
        value["status"] = _worst([_run_status(j) for j in value["runs"].values()])
    if "stress" in ids:
        for name, judged_run in ids["stress"]["runs"].items():
            judged_run["madloop_qp"] = (
                judge_madloop(madloop[name], records[name])
                if madloop and name in madloop
                else {
                    "status": "not run",
                    "reason": "no MadLoop record (li_manifest.py stress-madloop)",
                }
            )
    if limit_results:
        limited = [f for f in limit_results if f in judged and f not in ratio_rows]
        ids[LIMIT_ROW] = {
            "status": _worst([judged[f]["L9"]["status"] for f in limited]),
            "runs": {f: judged[f]["L9"] for f in limited},
        }
        ratios = {
            f: {
                "heft_ratio_at_physical_mt": [
                    p["ratios"][0] for p in judged[f]["L9"]["points"]
                ],
                "mt": judged[f]["L9"]["masses"][0],
                "large_mt_limit": [p["limit"] for p in judged[f]["L9"]["points"]],
                "extrapolation_error": [
                    p["extrapolation_error"] for p in judged[f]["L9"]["points"]
                ],
                **(
                    {"finding": judged[f]["L9"]["finding"]}
                    if "finding" in judged[f]["L9"]
                    else {}
                ),
            }
            for f in ratio_rows
            if f in judged and "L9" in judged[f]
        }
        if ratios and HEFT_RATIO_ROW in ids:
            ids[HEFT_RATIO_ROW]["heft_ratio"] = ratios
    campaign_runs = {f for f in judged if "stress" not in by_fixture[f]["tiers"]}
    for i, check in IDENTITIES.items():
        per_run = {
            f: j[check] for f, j in judged.items() if check in j and f in campaign_runs
        }
        ids[i] = {
            "check": check,
            # (a zero row's 'recorded' identity is L8's: not this row's verdict)
            "status": _worst(
                [v["status"] for v in per_run.values() if v["status"] != "recorded"]
            ),
            "runs": per_run,
        }
    if "LI-W1" in ids:
        ids["LI-W1"]["cited"] = spec()["identities"].get("ward_cited", {})
    ids[CROSSING_ID] = (
        judge_crossing(crossing_result, records)
        if crossing_result
        else {
            "status": "not run",
            "reason": "no crossing record (li_manifest.py crossing)",
        }
    )
    flavours = [e["fixture"] for e in entries if FLAVOUR_ROW in e["ids"]]
    ids["LI-S1"] = {
        "status": _worst(
            [
                judged[f][c]["status"]
                for f in flavours
                if f in judged
                for c in ("L1", "L2")
                if c in judged[f]
            ]
        ),
        "note": f"{FLAVOUR_ROW}'s runs with and without the top loop against the "
        "analytic oracle "
        "(the quark sum with its charges) and the providers",
        "runs": {
            f: {c: judged[f][c] for c in ("L1", "L2") if c in judged[f]}
            for f in flavours
            if f in judged
        },
    }
    for i, record in delegated.items():
        if i.startswith("LI-"):
            ids[i] = record
    if born:
        # LI-B1's campaign rows (``born_l6``) next to lit-tir's G1 evidence.
        scripts = sorted(
            {
                r["lanes_script"]["sha256"]
                for r in born.values()
                if (r.get("lanes_script") or {}).get("sha256")
            }
        )
        ids["LI-B1"] = {
            **ids.get("LI-B1", {}),
            "campaigns": born_summary(born),
            "lanes_script_sha256": scripts,
            "status": _worst(
                [ids.get("LI-B1", {}).get("status", "pass")]
                + [r["status"] for r in born.values() if r["status"] != "not run"]
            ),
        }
    if fig7_result:
        ids[FIG7_ID] = judge_fig7(fig7_result)
    for i, result in (fabc or {}).items():
        # LI-27's f^abc check (``fabc_check``) next to its runs
        ids[i] = {
            **ids.get(i, {}),
            "fabc": result,
            "status": _worst([ids.get(i, {}).get("status", "pass"), result["status"]]),
        }
    for i, checks in UNRUN.items():
        if not i.startswith("LI-"):
            continue
        # a §4.1 check not run makes its id and the id's rows partial (PLAN
        # §3.4 Done: partial rows recorded with reasons)
        ids.setdefault(i, {})["not_run"] = checks
        ids[i]["status"] = _worst([ids[i].get("status", "partial"), "partial"])
        for key, row_ids in ids_of.items():
            if i in row_ids and key in rows:
                rows[key]["status"] = _worst([rows[key]["status"], "partial"])
                rows[key]["note"] = "; ".join(
                    [
                        *([rows[key]["note"]] if rows[key].get("note") else []),
                        *(f"{i} {check}: {why}" for check, why in checks.items()),
                    ]
                )
    for i, checks in NOT_APPLICABLE.items():
        if not i.startswith("LI-"):
            continue
        # a §4.1 check a user ruling makes not applicable: recorded with the
        # ruling on its id and rows, their status unchanged
        ids.setdefault(i, {})["not_applicable"] = checks
        for key, row_ids in ids_of.items():
            if i in row_ids and key in rows:
                rows[key]["note"] = "; ".join(
                    [
                        *([rows[key]["note"]] if rows[key].get("note") else []),
                        *(f"{i} {check}: {why}" for check, why in checks.items()),
                    ]
                )
    for value in ids.values():
        status = value.get("status", "")
        if status.startswith("waits"):
            # R2: waiting on a package not yet landed is partial, naming it.
            value["status"] = "partial"
            value["waits_on"] = TIR_MP
    _dedupe(ids, rows)
    return {
        "what": "lit-val's loop-induced validation figures (m-lit PLAN §3.4 LIT-VAL, "
        "§4.0 rules, §4.1 rows): rows keyed by milestone.json loop_induced keys "
        "(read by scripts/build_summary.py build_loop_induced), per §4.1 id under "
        "'ids'; written by tools/loop_benchmark/li_manifest.py lit",
        "rules": _load(CAMPAIGN)["rules"],
        "source": source,
        "provenance": provenance(records),
        "rows": rows,
        "ids": ids,
    }


CHECKS = ("N", "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9", "E")
# The typed-reason tallies of a check (per distinct message its count).
REASONS = ("failed", "tirust_failed_reasons", "reasons")


def _without_reasons(value: Any) -> Any:
    """``value`` with its typed-reason tallies (``REASONS``) replaced by
    their counts (``<key>_count``)."""

    if isinstance(value, list):
        return [_without_reasons(v) for v in value]
    if not isinstance(value, dict):
        return value
    out = {}
    for k, v in value.items():
        if k in REASONS and isinstance(v, dict):
            out[f"{k}_count"] = sum(v.values())
        else:
            out[k] = _without_reasons(v)
    return out


def _dedupe(ids: dict, rows: dict) -> None:
    """Each run's checks once in data/lit.json: an id's run that a registry
    row carries is its status and that row's key (a whole run), or the
    check's figures without the typed-reason tallies (an identity row's
    check); the stress and validation-only runs stay whole in their ids."""

    in_rows = {f: key for key, row in rows.items() for f in (row.get("runs") or {})}
    for value in ids.values():
        runs = value.get("runs")
        if not isinstance(runs, dict):
            continue
        for name, checks in list(runs.items()):
            if name not in in_rows or not isinstance(checks, dict):
                continue
            if any(c in checks for c in CHECKS):  # a whole run (its checks)
                runs[name] = {"status": _run_status(checks), "row": in_rows[name]}
            else:
                runs[name] = {**_without_reasons(checks), "row": in_rows[name]}


def _apply_finding(result: dict, finding: Any) -> None:
    """A recorded reference finding on a check: attached as is; a failing
    L9 becomes 'reference defect' only where the finding's ``expected_limit``
    explains it (every point's limit within ten times its error of it, the
    error of ``judge_limit``); any other failure stays a failure."""

    note = finding if isinstance(finding, str) else finding["note"]
    result["finding"] = note
    expected = None if isinstance(finding, str) else finding.get("expected_limit")
    if result["status"] != "fail" or expected is None:
        return
    target = float(Fraction(expected))
    explained = [
        abs(p["limit"] - target)
        <= FACTOR * (p["extrapolation_error"] + p.get("oracle_floor", 0.0))
        for p in result.get("points", [])
    ]
    result["finding_explains"] = bool(explained) and all(explained)
    if result["finding_explains"]:
        result["status"] = "reference defect"


def _run_status(judged: dict) -> str:
    """A run's verdict: its worst check ('recorded' figures, e.g. a zero
    row's provider values, are information, not a verdict)."""

    statuses = [judged[c]["status"] for c in CHECKS if c in judged]
    return _worst([x for x in statuses if x != "recorded"] or statuses)


# Verdicts that need no note.
PASSING = ("pass", "pass (lax)", "recorded")


def _causes(name: str, judged: dict) -> list[str]:
    """Why a run is not a plain pass: per check not passing, its status and
    cause (the figures and typed reasons stay in the run's checks)."""

    out = []
    for check in CHECKS:
        if check not in judged or judged[check]["status"] in PASSING:
            continue
        result = judged[check]
        cause = result.get("reason") or result.get("finding")
        if check == "L6":
            b64 = result["double"]
            parts = []
            if b64["tirust_served"] < b64["of"]:
                parts.append(
                    f"TIRust fails {b64['of'] - b64['tirust_served']} of {b64['of']} "
                    "binary64 "
                    "points closed (typed: L6.double.tirust_failed_reasons)"
                )
            for carrier in ("double-double", ARBITRARY):
                sub = result.get(carrier)
                if sub and sub["status"] not in PASSING:
                    parts.append(f"{carrier} {sub['status']}")
            cause = "; ".join(parts) or cause
        elif check == "L3":
            cause = ", ".join(
                f"{label} {v['status']}"
                + (f" ({v['served']}/{v['of']} points)" if "served" in v else "")
                for label, v in result.items()
                if isinstance(v, dict) and v.get("status") not in (None, *PASSING)
            )
        elif check == "N":
            cause = f"NinjaRS fails {result['failed']} points closed (typed: N.reasons)"
        elif check == "L4":
            cause = ", ".join(
                f"{label} {v['status']}"
                + (f" ({v['served']}/{v['of']} points)" if "served" in v else "")
                for label, v in result.items()
                if isinstance(v, dict) and v.get("status") not in (None, *PASSING)
            )
        text = f"{check} {result['status']}"
        out.append(f"{name}: {text}" + (f" ({cause})" if cause else ""))
    return out


def _merge(key, done, judged, fixtures, source) -> dict:
    refs: dict[str, float] = {}
    for f in done:
        for k, v in judged[f]["references"].items():
            refs[k] = max(refs.get(k, 0.0), v)
    status = _worst([_run_status(judged[f]) for f in done])
    if len(done) < len(fixtures):
        status = _worst([status, "partial"])
    waiting = {
        (judged[f][c]["waits_on"], c)
        for f in done
        for c in CHECKS
        if c in judged[f] and "waits_on" in judged[f][c]
    }
    waits = sorted({package for package, _ in waiting})
    if status.startswith("waits"):
        # R2: a row whose check waits on a package not yet landed is
        # partial, naming that package.
        status = "partial"
    checks = {f: {c: judged[f][c] for c in CHECKS if c in judged[f]} for f in done}
    notes = [
        f"WAITS ON {package}: TIRust's arms of "
        + ", ".join(sorted(c for p, c in waiting if p == package))
        + " (taken before it, or refused typed for want of the carrier), re-run at its "
        "re-pin"
        for package in waits
    ]
    for f in done:
        notes.extend(_causes(f, judged[f]))
    missing = [f for f in fixtures if f not in done]
    if missing:
        notes.append("not run: " + ", ".join(missing))
    return {
        "status": status,
        "references": refs,
        "points": sum(judged[f]["points"] for f in done),
        "note": "; ".join(notes) or None,
        "waits_on": waits,
        "source": source,
        "runs": checks,
    }


# ------------------------------------------------------------- CLI


def _resumable(path: Path, refresh: str | None, name: str, work: Path) -> dict | None:
    """The record at ``path`` to continue from (None: run afresh): a record
    taken or refreshed (for ``refresh``: refreshed for that backend) with
    the staged extension (``_same_native``) is kept (complete: skipped;
    unfinished, e.g. an interrupted refresh, or complete without the L3
    probes: resumed); with ``refresh`` (a backend) a complete record of
    another native keeps its other arms if the staged native reproduces its
    NinjaRS binary64 values bitwise (``refresh_check``), its ``refresh``
    arms and L3 probes are dropped and recomputed (recorded under
    ``refreshed`` with the extension, revision, Python Symbolica and
    capability that took them)."""

    if not path.is_file():
        return None
    done = _load(path)
    if _same_native(done, refresh):
        if done.get("complete") and not {"l3_probes", "ward_probes"} <= set(done):
            done = {**done, "complete": False}
        return done
    if not refresh or not done.get("complete"):
        return None
    if not refresh_check(name, work, done):
        raise SystemExit(
            f"{name}: the staged native does not reproduce the record's NinjaRS "
            "binary64 "
            "values bitwise: run it afresh in a new --work-dir"
        )
    arms = {k: v for k, v in done["arms"].items() if not k.startswith(f"{refresh}/")}
    probes = {
        k: v
        for k, v in (done.get("l3_probes") or {}).items()
        if not k.startswith(refresh)
    }
    wards = done.get("ward_probes")
    if wards is not None:
        kept = {
            k: v for k, v in wards.get("arms", {}).items() if not k.startswith(refresh)
        }
        wards = {**wards, "arms": kept}
    refreshed = [
        *done.get("refreshed", []),
        {
            "backend": refresh,
            "native": _native(),
            "revision": _revision(),
            "python_symbolica": _symbolica(),
            "reduction_backends": _capability(),
        },
    ]
    return {
        **done,
        "arms": arms,
        "l3_probes": probes,
        **({"ward_probes": wards} if wards is not None else {}),
        "refreshed": refreshed,
        "complete": False,
    }


def refresh_check(name: str, work: Path, record: dict) -> bool:
    """Whether the staged native reproduces ``record``'s NinjaRS binary64
    values (the plain arm) bitwise on its artifact."""

    from pyamplicol import Runtime

    data = fixture(name)
    compiled = compile_model(data, work / "model-cache")
    runtime = Runtime.load(
        work / name / "artifact",
        process="p",
        model_parameters=run_parameters(data, compiled),
    )
    scales = [_decimal(Fraction(mu) ** 2) for mu in data["mu_r"]]
    arm = _call(
        runtime,
        data["points"],
        scales,
        backend="ninjars",
        arithmetic="double",
        checked=False,
        digits=DIGITS,
    )
    recorded = record["arms"]["ninjars/double/plain"]["points"]
    return [p["values"] for p in arm["points"]] == [p["values"] for p in recorded]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("rows", help="print the run matrix")
    sub.add_parser("stress", help="write the stress-point fixtures")
    run = sub.add_parser("run", help="evaluate fixture runs")
    run.add_argument("--work-dir", type=Path, required=True)
    run.add_argument("--digits", type=int, default=DIGITS)
    run.add_argument(
        "--skip-arm",
        action="append",
        default=[],
        metavar="LABEL=REASON",
        help="record an arm (l3/<label> for an L3 probe arm) as not run, with the "
        "reason",
    )
    run.add_argument(
        "--high-plain",
        action="store_true",
        help="run the double-double arms without the checks (value only)",
    )
    run.add_argument(
        "--refresh-backend",
        choices=BACKENDS,
        default=None,
        help="recompute this backend's arms of complete records of another native "
        "(after lit-tir-mp: tirust), the others kept if NinjaRS binary64 is bitwise",
    )
    run.add_argument("fixtures", nargs="*", help="default: every campaign run")
    ident = sub.add_parser(
        "identity-tirust",
        help="LI-L1 on TIRust: the transformed points of complete records (binary64)",
    )
    ident.add_argument("--work-dir", type=Path, required=True)
    ident.add_argument("fixtures", nargs="*", help="default: every complete record")
    lim = sub.add_parser("limits", help="LI-A7: the heavy-top scan of the limit rows")
    lim.add_argument("--work-dir", type=Path, required=True)
    lim.add_argument("--doublings", type=int, default=DOUBLINGS)
    out = sub.add_parser("lit", help="write data/lit.json from run records")
    out.add_argument("--records", type=Path, required=True)
    out.add_argument("--output", type=Path, default=LIT)
    out.add_argument("--source", required=True)
    out.add_argument(
        "--limits", type=Path, default=None, help="the limits command's output"
    )
    out.add_argument(
        "--crossing", type=Path, default=None, help="the crossing command's output"
    )
    out.add_argument(
        "--stress-madloop",
        type=Path,
        default=None,
        help="the stress-madloop command's output",
    )
    out.add_argument(
        "--fabc", type=Path, default=None, help="the fabc command's output"
    )
    out.add_argument(
        "--fig7",
        type=Path,
        action="append",
        default=[],
        help="a fig7 command's output (repeatable)",
    )
    f7 = sub.add_parser("fig7", help="the arXiv:1604.01363 Fig. 7 comparison runs")
    f7.add_argument("--work-dir", type=Path, required=True)
    f7.add_argument("--output", type=Path, required=True)
    f7.add_argument(
        "--own-scheme",
        action="store_true",
        help="each fixture's own scheme and campaign artifact (not the paper's)",
    )
    f7.add_argument(
        "counts", nargs="*", help="FIXTURE=POINTS (default: SPEC fig7 runs)"
    )
    fabc = sub.add_parser(
        "fabc", help="LI-27: the f^abc check of g g > a g (SPEC colour_checks)"
    )
    fabc.add_argument("--work-dir", type=Path, required=True)
    cross = sub.add_parser(
        "crossing", help="C1: the crossing evaluations of LI-26's runs"
    )
    cross.add_argument("--work-dir", type=Path, required=True)
    ml = sub.add_parser(
        "stress-madloop", help="MadLoop QP at the stress points (lit-ref's exports)"
    )
    ml.add_argument("--work-dir", type=Path, required=True)
    ml.add_argument(
        "--reference-root",
        type=Path,
        default=None,
        help="the reference tree (default: LOOP_REFERENCE_ROOT, else the workspace's)",
    )
    ml.add_argument("--cpu", type=int, default=None)
    bl = sub.add_parser(
        "born-l6",
        help="LI-B1: the Born-interfered L6 of campaign rows (lit-tir's lanes)",
    )
    bl.add_argument(
        "--campaign",
        choices=sorted({*BORN["campaigns"], *BORN["public"]}),
        required=True,
    )
    bl.add_argument(
        "--lanes-script",
        type=Path,
        default=None,
        help="lit-tir's scripts/li_b1.py (required by the tools-route campaigns; "
        "its sha256 is recorded per row)",
    )
    bl.add_argument(
        "--ufo", type=Path, required=True, help="loop_sm's UFO (hc: HC_NLO_X0's)"
    )
    bl.add_argument(
        "--model-ufo",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="the UFO of a manifest model other than loop_sm (its ``models``)",
    )
    bl.add_argument("--work-dir", type=Path, required=True)
    bl.add_argument(
        "--output", type=Path, required=True, help="a directory: one record per row"
    )
    bl.add_argument("rows", nargs="*", help="default: every row of the campaign")
    out.add_argument(
        "--born-l6",
        type=Path,
        default=None,
        help="the born-l6 command's output directory (LI-B1's campaign rows)",
    )
    args = parser.parse_args(argv)
    sys.path.insert(0, str(WT))
    entries = runs()
    if args.command == "stress":
        for path in write_stress():
            print(path.relative_to(WT))
        return 0
    if args.command == "rows":
        print(json.dumps(entries, indent=1))
        return 0
    if args.command == "run":
        by_fixture = {e["fixture"]: e for e in entries}
        skip = skip_arms(args.skip_arm)
        for name in args.fixtures or list(by_fixture):
            entry = by_fixture[name]
            path = args.work_dir / name / "record.json"

            def write(record: dict, path: Path = path) -> None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(record, indent=1) + "\n")

            previous = _resumable(path, args.refresh_backend, name, args.work_dir)
            if previous is not None and previous.get("complete"):
                print(name, "complete", flush=True)
                continue
            own, plain = run_skips(name)
            record = evaluate(
                name,
                args.work_dir,
                ap=bool(entry["ap"]),
                digits=args.digits,
                write=write,
                previous=previous,
                skip={**own, **skip},
                high_checked=not (args.high_plain or plain),
            )
            print(
                name,
                json.dumps(
                    {
                        c: v.get("status")
                        for c, v in judge(record, entry).items()
                        if isinstance(v, dict) and "status" in v
                    }
                ),
                flush=True,
            )
        return 0
    if args.command == "limits":
        result = {}
        for target in limit_targets(entries):
            result[target["fixture"]] = limits(
                target["fixture"], target["oracle"], args.work_dir, args.doublings
            )
            print(
                target["fixture"],
                json.dumps(result[target["fixture"]]["status"]),
                flush=True,
            )
            (args.work_dir / "limits.json").write_text(
                json.dumps(result, indent=1) + "\n"
            )
        return 0
    if args.command == "fig7":
        counts = (
            {k: int(v) for k, v in (a.split("=") for a in args.counts)}
            if args.counts
            else spec()["fig7"]["runs"]
        )
        fig7(args.work_dir, counts, args.own_scheme, args.output)
        return 0
    if args.command == "stress-madloop":
        root = args.reference_root or Path(
            os.environ.get("LOOP_REFERENCE_ROOT") or _workspace() / "reference"
        )
        result = stress_madloop(args.work_dir, entries, root.resolve(), args.cpu)
        (args.work_dir / "stress-madloop.json").write_text(
            json.dumps(result, indent=1) + "\n"
        )
        return 0
    if args.command == "born-l6" and args.campaign in BORN["public"]:
        args.output.mkdir(parents=True, exist_ok=True)
        for name, record in born_l6_hc(args.work_dir, args.ufo, args.rows).items():
            record["campaign"] = args.campaign
            path = args.output / f"{args.campaign}-{name}.json"
            path.write_text(json.dumps(record, indent=1, default=str) + "\n")
            print(name, record["status"], flush=True)
        return 0
    if args.command == "born-l6":
        from pyamplicol.loops.native import load_loop_native
        from tools.loop_benchmark import mqcd

        if args.lanes_script is None:
            parser.error(f"born-l6 --campaign {args.campaign} needs --lanes-script")
        module = lanes_module(args.lanes_script)
        campaign = mqcd.Campaign(
            args.ufo,
            load_loop_native(),
            args.work_dir,
            manifest=mqcd.load_manifest(WT / BORN["campaigns"][args.campaign]),
            ufos=dict(item.split("=", 1) for item in args.model_ufo),
        )
        args.output.mkdir(parents=True, exist_ok=True)
        names = args.rows or list(campaign.rows)
        for k, name in enumerate(names):
            path = args.output / f"{args.campaign}-{name}.json"
            group = campaign.rows[name].base or name
            later = {campaign.rows[n].base or n for n in names[k + 1 :]}
            if path.is_file():
                print(name, "recorded", flush=True)
                continue
            try:
                record = born_l6(campaign, name, module)
            except Exception as error:  # the row's record (a typed reason)
                record = {
                    "row": name,
                    "process": campaign.rows[name].process,
                    "status": "fail",
                    "reason": f"{type(error).__name__}: {error}"[:2000],
                }
            record["campaign"] = args.campaign
            path.write_text(json.dumps(record, indent=1, default=str) + "\n")
            print(name, record["status"], flush=True)
            if group not in later:
                # the row's generation is not needed again (memory)
                campaign._runs.clear()
        return 0
    if args.command == "fabc":
        result = {
            i: fabc_check(args.work_dir, check)
            for i, check in COLOUR.items()
            if i.startswith("LI-")
        }
        (args.work_dir / "fabc.json").write_text(json.dumps(result, indent=1) + "\n")
        print({i: r["status"] for i, r in result.items()}, flush=True)
        return 0
    if args.command == "identity-tirust":
        paths = (
            [args.work_dir / n / "record.json" for n in args.fixtures]
            if args.fixtures
            else sorted(args.work_dir.glob("*/record.json"))
        )
        for path in paths:
            record = _load(path)
            name = record["fixture"]
            if not record.get("complete") or not record.get("transformed_points"):
                print(name, "no identity arm", flush=True)
                continue
            if _same_native(record.get("identity_tirust") or {}):
                print(name, "recorded", flush=True)
                continue
            record["identity_tirust"] = identity_tirust(name, args.work_dir, record)
            path.write_text(json.dumps(record, indent=1) + "\n")
            print(name, record["identity_tirust"]["bitwise_record"], flush=True)
        return 0
    if args.command == "crossing":
        result = crossing(args.work_dir, entries)
        (args.work_dir / "crossing.json").write_text(
            json.dumps(result, indent=1) + "\n"
        )
        return 0
    records = {
        path.parent.name: record
        for path in sorted(args.records.glob("*/record.json"))
        if (record := _load(path)).get("complete")
    }
    limit_results = _load(args.limits) if args.limits else None
    crossing_result = _load(args.crossing) if args.crossing else None
    madloop = _load(args.stress_madloop) if args.stress_madloop else None
    fig7_result = [_load(path) for path in args.fig7] or None
    born = (
        {
            f"{r['campaign']}/{r['row']}": r
            for r in map(_load, sorted(args.born_l6.glob("*.json")))
        }
        if args.born_l6
        else None
    )
    args.output.write_text(
        json.dumps(
            lit(
                records,
                entries,
                args.source,
                limit_results,
                crossing_result=crossing_result,
                madloop=madloop,
                fig7_result=fig7_result,
                born=born,
                fabc=_load(args.fabc) if args.fabc else None,
            ),
            indent=1,
            sort_keys=True,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
