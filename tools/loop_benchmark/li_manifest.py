# SPDX-License-Identifier: 0BSD
"""The M-LIT loop-induced validation campaign (m-lit PLAN §3.4 LIT-VAL, rules
§4.0 L1-L9, rows §4.1): the run matrix, the runs and data/lit.json.

Usage (worktree root, licence in the environment, the staged native)::

    python tools/loop_benchmark/li_manifest.py rows            # the run matrix
    python tools/loop_benchmark/li_manifest.py run --work-dir W li_gg_h ...
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
``reduction="tirust"``; never ``"auto"``, never TIRust's method choice), in
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
point marked ``l1_caution`` is judged against the double-double value
instead); L2 binary64 <= 1e-9 and double-double / AP <= 1e-12 against the
analytic oracle (targets: a deviation below ~1e-5 is recorded and reported,
never a failure, R5); L3 the amplitude-level finiteness ratio (the lane's
``finiteness``, formed with checks only) <= 10 times the pole estimate
against the same term floor, binary64 and double-double, NinjaRS and TIRust;
L4/W1 the generation-time Ward, Goldstone and finiteness probes (double-
double, zero widths, m-lit Q12) recorded from the artifact; L5/L1-identity
an exact Lorentz transform (rotation and boost with terminating-decimal
entries) leaves |A|^2 within 10 (E + E') in binary64 and is recorded in
double-double; L6 |T - N| <= 10 max(E_N, E_T) per sector and Laurent
coefficient through the one comparison (``_compare``; a TIRust point whose
checked call fails keeps E_N alone, which is conservative), points TIRust
fails closed recorded with its typed reasons (partial), the double-double /
AP arms 'WAITS ON lit-tir-mp' with TIRust's typed refusal; L7 double-double
vs AP <= 1e-24 (target, R5); L8 numerical zeros |A|^2 <= 10 E_abs in
binary64 and double-double (Q13; no theorem-based zero).
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
CAMPAIGN = WT / "tools" / "loop_reference" / "li_campaign.json"
MILESTONE = WT / "docs" / "performance_reports" / "loop" / "data" / "milestone.json"
FIXTURES = WT / "tests" / "fixtures" / "loop" / "required" / "li"
LIT = WT / "docs" / "performance_reports" / "loop" / "data" / "lit.json"

BACKENDS = ("ninjars", "tirust")
# PLAN §4.1: binary64 and double-double on every row, arbitrary precision on
# one row per tier.
CARRIERS = ("double", "double-double")
ARBITRARY = "arbitrary"
# The AP carrier's digits: enough above double-double's ~32 for L7's 1e-24
# (overridable, ``run --digits``).
DIGITS = 40
# PLAN §4.0 (the campaign's global rules, li_campaign.json "rules").
FACTOR = 10  # the x10 estimate rule (L3-L6, L8)
LAX = 1e-5  # L1; below it a deviation is never a failure (precision lax, R5)
ANALYTIC_DOUBLE = 1e-9  # L2 binary64
ANALYTIC_HIGH = 1e-12  # L2 double-double / AP (a target, R5)
CARRIER = 1e-24  # L7 double-double vs AP (a target, R5)
# The waiting arm of L6 (ruling 17:20 (d), R4: DD/AP TIR is lit-tir-mp's).
TIR_MP = "lit-tir-mp"
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
    return _load(FIXTURES / f"{name}.json")


def _norm(process: str) -> str:
    """A MadLoop process without its bracket, order limits and vetoes."""

    text = re.sub(r"\[[^\]]*\]|\S+(?:<=|>=|==|=)\S+", " ", process)
    return " ".join(text.split("/")[0].split())


def _ids(row_id: str) -> list[str]:
    """"LI-W1/L1/P1/C1/S1" is LI-W1, LI-L1, LI-P1, LI-C1, LI-S1."""

    head, *rest = row_id.split("/")
    prefix = head.rsplit("-", 1)[0] + "-"
    return [head, *(prefix + r for r in rest)]


def registry() -> dict:
    return _load(MILESTONE)["loop_induced"]


def runs(campaign: dict | None = None, reg: dict | None = None) -> list[dict]:
    """The run matrix: one entry per fixture of a §4.1 row's reference runs
    (a fixture several rows list, e.g. li_h_aa of LI-A3 and LI-E1, runs
    once), with every row id, tier and check that lists it, the registry key
    whose ids and process it serves (None: validation-only), the designated
    providers (the run's providers less its excluded ones) and whether it is
    its tier's AP run."""

    campaign = _load(CAMPAIGN) if campaign is None else campaign
    reg = registry() if reg is None else reg
    out: dict[str, dict] = {}
    for row in campaign["rows"]:
        if row["row"] in DELEGATED:
            continue
        for run in row.get("runs", []):
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
        entry["key"] = keys[0] if keys else None
    ordered = list(out.values())
    ap: dict[str, str] = {}
    for tier in dict.fromkeys(t for e in ordered for t in e["tiers"]):
        members = [e for e in ordered if tier in e["tiers"]]
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
    else the ``workspace`` directory beside the main checkout."""

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


# Loading options of a source UFO, by its directory name (how that model is
# read, as in tests/unit/test_loop_v2_induced_ew*.py; not a row property):
# the G_mu UFO's structural compatibility profile; MadLoop's photons are
# untagged.
UFO_OPTIONS = {
    "loop_qcd_qed_sm_Gmu_py3": {
        "loop": {"external_photons": "none"},
        "loop.preparation": {"compatibility": "gmu_particle_anti"},
    },
}


def _model(data: dict) -> tuple[str, str | None, dict]:
    """(model source, restriction, UFO options) of a fixture's scheme:
    ``{mg5}/models/loop_sm[-<restriction>]`` is the shipped ``loop_sm``,
    ``{reference}/...`` a UFO below the workspace's reference tree."""

    source = data["madloop_model"]
    restriction = data.get("restriction")
    if source.startswith("{mg5}/models/"):
        stem = source.removeprefix("{mg5}/models/")
        name, _, suffix = stem.partition("-")
        return name, restriction or suffix or "default", {}
    if source.startswith("{reference}/"):
        path = _workspace() / "reference" / source.removeprefix("{reference}/")
        return str(path), restriction, UFO_OPTIONS.get(path.name, {})
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
    """The fixture's process in the model's particle names (by PDG code)."""

    names = {int(r.pdg_code): str(r.name) for r in compiled.ir.particles}
    pdgs, initial = data["pdgs"], data["initial"]
    return (
        " ".join(names[pdg] for pdg in pdgs[:initial])
        + " > "
        + " ".join(names[pdg] for pdg in pdgs[initial:])
    )


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
        "generation": {"output": str(output), "emit_api_bundle": False},
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


def generate(name: str, work: Path, compiled: Any) -> tuple[Path, dict]:
    """The fixture's loop-induced artifact through the public ``Generator``
    (kept in ``work / name / "artifact"`` and re-used), with its generation
    record: seconds and the artifact's generation-time probe record."""

    from pyamplicol.api import Generator, ProcessRequest, ProcessSet
    from pyamplicol.config import resolve_config

    data = fixture(name)
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
                "detail": lane.detail[:300],
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
) -> dict:
    """Every arm of one fixture run (module docstring), cheapest first:
    binary64 on both backends with and without the checks, double-double
    with the checks (TIRust's typed refusal recorded), the identity check's
    transformed points (binary64 checked, double-double) on NinjaRS, and AP
    without checks on an AP run. ``write`` (if given) receives the record
    after every arm (``complete`` False until the last)."""

    from pyamplicol import Runtime

    data = fixture(name)
    compiled = compile_model(data, work / "model-cache")
    known = set(compiled.parameter_defaults)
    artifact, generation = generate(name, work, compiled)
    fixed = data["scheme_data"]["fixed_parameters"]
    parameters = {
        k: v
        for k, v in data["scheme_data"]["parameters"].items()
        if k not in fixed and k in known
    }
    runtime = Runtime.load(artifact, process="p", model_parameters=parameters)
    points = data["points"]
    scales = [str(Fraction(mu) ** 2) for mu in data["mu_r"]]
    transformed = [lorentz(p) for p in points] if identity else []
    record: dict[str, Any] = {
        "fixture": name,
        "revision": _revision(),
        "native_digest": _native_digest(),
        "generation": generation,
        "digits": digits if ap else None,
        "transformed_points": transformed,
        "arms": {},
        "complete": False,
    }
    plan: list[tuple[str, str, str, bool, list]] = []
    for arithmetic in CARRIERS:
        for backend in BACKENDS:
            for checked in (False, True) if arithmetic == "double" else (True,):
                tag = "checked" if checked else "plain"
                plan.append((f"{backend}/{arithmetic}/{tag}", backend, arithmetic, checked, points))
    if identity:
        for arithmetic in CARRIERS:
            plan.append(
                (f"identity/ninjars/{arithmetic}", "ninjars", arithmetic, arithmetic == "double", transformed)
            )
    if ap:
        for backend in BACKENDS:
            plan.append((f"{backend}/{ARBITRARY}/plain", backend, ARBITRARY, False, points))
    for label, backend, arithmetic, checked, inputs in plan:
        record["arms"][label] = _call(
            runtime,
            inputs,
            scales,
            backend=backend,
            arithmetic=arithmetic,
            checked=checked,
            digits=digits,
        )
        record["peak_gib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20
        if write is not None:
            write(record)
    record["complete"] = True
    if write is not None:
        write(record)
    return record


def _revision() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=WT, capture_output=True, text=True
    ).stdout.strip()


def _native_digest() -> str | None:
    path = WT / "src" / "pyamplicol" / "native-build.json"
    if path.is_file():
        return _load(path).get("native_digest")
    return None


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
    order = ["fail", "estimate miss", "partial", "waits", "not run", "pass (lax)", "pass"]
    present = [s.split(":")[0] for s in statuses]
    for s in order:
        if s in present:
            return s
    return "not run"


def _served(arm: dict | None) -> list[bool]:
    if not arm or "points" not in arm:
        return []
    return [p["status"] == "success" for p in arm["points"]]


def _reasons(arm: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    for p in arm.get("points", []):
        if p["status"] != "success":
            key = re.sub(r"\d+(\.\d+)?(e-?\d+)?", "#", p["detail"])[:160]
            out[key] = out.get(key, 0) + 1
    return out


def judge(record: dict, entry: dict) -> dict:
    """The §4.0 checks of one run record (module docstring); per check its
    status and figures."""

    from tools.loop_v2_observables_backends import _compare

    data = fixture(record["fixture"])
    arms = record["arms"]
    n64, n64c = arms["ninjars/double/plain"], arms["ninjars/double/checked"]
    t64, t64c = arms["tirust/double/plain"], arms["tirust/double/checked"]
    ndd, tdd = arms["ninjars/double-double/checked"], arms["tirust/double-double/checked"]
    nap = arms.get(f"ninjars/{ARBITRARY}/plain")
    out: dict[str, Any] = {}
    count = len(data["points"])
    n_served = _served(n64c)
    out["points"] = count
    if not all(n_served) or not all(_served(n64)):
        out["ninjars"] = {"status": "fail", "reasons": _reasons(n64c)}
    # L1 providers (binary64, NinjaRS; TIRust on the points it serves).
    refs: dict[str, float] = {}
    caution: list[dict] = []
    tir_refs: dict[str, float] = {}
    for p, row in enumerate(data["rows"]):
        if p >= count:
            break
        value = _total(n64["points"][p]["values"])
        tvalue = _total(t64["points"][p]["values"]) if _served(t64)[p] else None
        for provider in entry["providers"]:
            if provider == "analytic" or provider not in row["providers"]:
                continue
            reference = row["providers"][provider]["value"]
            dev = _rel(value, reference)
            if row.get("l1_caution") and dev > LAX:
                dd = _total(ndd["points"][p]["values"]) if _served(ndd)[p] else None
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
            refs[provider] = max(refs.get(provider, 0.0), dev)
            if tvalue is not None:
                tir_refs[provider] = max(tir_refs.get(provider, 0.0), _rel(tvalue, reference))
    if refs or "L1" in entry["checks"]:
        worst = max(refs.values(), default=None)
        out["L1"] = {
            "status": "not run"
            if worst is None
            else _verdict(worst <= LAX, False),
            "max_relative": dict(refs),
            "tirust_max_relative": tir_refs,
            "caution_points": caution,
        }
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
    # L3 finiteness (with checks), NinjaRS and TIRust, binary64 and DD.
    l3: dict[str, Any] = {}
    statuses = []
    for label, arm in (
        ("ninjars/double", n64c),
        ("ninjars/double-double", ndd),
        ("tirust/double", t64c),
    ):
        ratios = []
        for pt in arm.get("points", []):
            if pt["status"] != "success" or pt["finiteness"] is None:
                continue
            bound = _pole_estimate(pt["estimate"])
            ratios.append(
                pt["finiteness"] / bound
                if bound
                else (0.0 if not pt["finiteness"] else math.inf)
            )
        served = sum(_served(arm))
        if not ratios:
            if label.startswith("tirust"):
                l3[label] = {"status": "partial", "served": served, "of": count}
                statuses.append("partial")
            continue
        worst = max(ratios)
        finiteness = max(
            pt["finiteness"]
            for pt in arm["points"]
            if pt["status"] == "success" and pt["finiteness"] is not None
        )
        status = (
            "pass"
            if worst <= FACTOR
            else ("estimate miss" if finiteness <= LAX else "fail")
        )
        if served < count:
            status = "partial"
        l3[label] = {
            "status": status,
            "worst_ratio": worst,
            "worst_finiteness": finiteness,
            "served": served,
            "of": count,
        }
        statuses.append(status)
    # The necessary-only cross-check at the |A|^2 level: every computed pole
    # of the sum within ten times its absolute estimate.
    poles = []
    for arm in (n64c, ndd, t64c):
        for pt in arm.get("points", []):
            if pt["status"] != "success" or pt["estimate"] is None:
                continue
            for sector, error in zip(pt["values"], pt["estimate"]["absolute"], strict=True):
                for k in ("single_pole", "double_pole"):
                    if sector[k] is not None and error[k]:
                        poles.append(abs(float(_complex(sector[k])[0])) / (FACTOR * error[k]))
    l3["poles_over_10E"] = max(poles, default=None)
    out["L3"] = {"status": _worst(statuses), **l3}
    # L4 / W1: the generation-time probes (double-double, zero widths).
    probes = record["generation"]["probes"] or {}
    l4 = {
        k: probes[k]
        for k in ("finiteness", "ward", "goldstone", "exact_colour_zero")
        if k in probes
    }
    out["L4"] = {
        "status": "pass"
        if l4 and all(v is True or v.get("passed") for v in l4.values())
        else ("not run" if not l4 else "fail"),
        "probes": l4,
        "carrier": probes.get("precision"),
        "widths": probes.get("widths"),
    }
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
        for p in range(count):
            a, b = ndd["points"][p], idd["points"][p]
            if a["status"] == "success" and b["status"] == "success":
                devs.append(_rel(_total(b["values"]), _total(a["values"])))
        worst = max(ratios, default=None)
        out["L5"] = {
            "status": "not run"
            if worst is None
            else ("pass" if worst <= 1 else "estimate miss"),
            "worst_ratio_to_10E": worst,
            "double_double_max_relative": max(devs, default=None),
            "transformed_estimate_relative": max(moved, default=None),
        }
    # L6 both backends: binary64 through the one comparison.
    rows, failed = [], {}
    t_served = _served(t64)
    for p in range(count):
        if not t_served[p] or not n_served[p]:
            continue
        tc = t64c["points"][p] if "points" in t64c else None
        n_entries = _entries(n64c["points"][p])
        t_entries = _entries(
            t64["points"][p], tc["estimate"] if tc and tc["status"] == "success" else None
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
        (r["difference"] / r["bound"] if r["bound"] else math.inf for r in rows if r["difference"]),
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
    out["L6"] = {
        "status": l6_status,
        "double": {
            "compared_entries": len(rows),
            "beyond_10E": len(misses),
            "worst_ratio_to_10E": worst,
            "finite_max_relative": finite_rel,
            "tirust_served": sum(t_served),
            "tirust_served_checked": sum(_served(t64c)),
            "of": count,
            "tirust_failed_reasons": _reasons(t64),
        },
        "double-double": {"status": f"waits: {TIR_MP}", "tirust": tdd.get("refused")},
    }
    if nap is not None:
        out["L6"][ARBITRARY] = {
            "status": f"waits: {TIR_MP}",
            "tirust": arms.get(f"tirust/{ARBITRARY}/plain", {}).get("refused"),
        }
    # L7 DD vs AP.
    if nap is not None and "points" in nap:
        devs = [
            _rel(_total(a["values"]), _total(b["values"]))
            for a, b in zip(ndd["points"], nap["points"], strict=True)
            if a["values"] is not None and b["values"] is not None
        ]
        worst = max(devs, default=None)
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
            for pt in arm["points"]:
                if pt["status"] != "success":
                    continue
                e = _abs_finite(pt["estimate"])
                value = abs(float(_total(pt["values"])))
                ratios.append(value / (FACTOR * e) if e else (0.0 if not value else math.inf))
            worst = max(ratios, default=None)
            l8[label] = worst
            statuses.append("not run" if worst is None else ("pass" if worst <= 1 else "fail"))
        out["L8"] = {"status": _worst(statuses), "worst_value_over_10E_abs": l8}
    out["references"] = {k: v for k, v in refs.items() if v is not None}
    return out


def _entries(point: dict, estimate: dict | None = None) -> list:
    """A record point as the one comparison's entries (``_laurents``'s
    shape: per sector (coefficient, (re, im), absolute estimate))."""

    estimate = point["estimate"] if estimate is None else estimate
    out = []
    for s, sector in enumerate(point["values"]):
        errors = estimate["absolute"][s] if estimate else None
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


# ------------------------------------------------------------- data/lit.json


def lit(records: dict[str, dict], entries: list[dict], source: str) -> dict:
    """data/lit.json: per registry key its status, reference deviations
    (binary64, NinjaRS; the analytic oracle's too), points and per-check
    figures over its runs; the validation-only ids alike under ``ids``."""

    by_fixture = {e["fixture"]: e for e in entries}
    judged = {
        name: judge(record, by_fixture[name])
        for name, record in records.items()
        if name in by_fixture
    }
    rows: dict[str, dict] = {}
    for key, fixtures in registry_runs(entries).items():
        done = [f for f in fixtures if f in judged]
        if not fixtures:
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
        for i in entry["ids"]:
            ids.setdefault(i, {"runs": {}})["runs"][entry["fixture"]] = judged[
                entry["fixture"]
            ]
    for i, value in ids.items():
        value["status"] = _worst(
            [_run_status(j) for j in value["runs"].values()]
        )
    return {
        "what": "lit-val's loop-induced validation figures (m-lit PLAN §3.4 LIT-VAL, "
        "§4.0 rules, §4.1 rows): rows keyed by milestone.json loop_induced keys "
        "(read by scripts/build_summary.py build_loop_induced), per §4.1 id under "
        "'ids'; written by tools/loop_benchmark/li_manifest.py lit",
        "rules": _load(CAMPAIGN)["rules"],
        "source": source,
        "rows": rows,
        "ids": ids,
    }


CHECKS = ("L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8")


def _run_status(judged: dict) -> str:
    return _worst([judged[c]["status"] for c in CHECKS if c in judged])


def _merge(key, done, judged, fixtures, source) -> dict:
    refs: dict[str, float] = {}
    for f in done:
        for k, v in judged[f]["references"].items():
            refs[k] = max(refs.get(k, 0.0), v)
    status = _worst([_run_status(judged[f]) for f in done])
    if len(done) < len(fixtures):
        status = _worst([status, "partial"])
    checks = {f: {c: judged[f][c] for c in CHECKS if c in judged[f]} for f in done}
    notes = []
    for f in done:
        l6 = judged[f]["L6"]["double"]
        if l6["tirust_served"] < l6["of"]:
            notes.append(f"{f}: TIRust serves {l6['tirust_served']}/{l6['of']} points")
    missing = [f for f in fixtures if f not in done]
    if missing:
        notes.append("not run: " + ", ".join(missing))
    return {
        "status": status,
        "references": refs,
        "points": sum(judged[f]["points"] for f in done),
        "note": "; ".join(notes) or None,
        "source": source,
        "runs": checks,
    }


# ------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("rows", help="print the run matrix")
    run = sub.add_parser("run", help="evaluate fixture runs")
    run.add_argument("--work-dir", type=Path, required=True)
    run.add_argument("--digits", type=int, default=DIGITS)
    run.add_argument("fixtures", nargs="+")
    out = sub.add_parser("lit", help="write data/lit.json from run records")
    out.add_argument("--records", type=Path, required=True)
    out.add_argument("--output", type=Path, default=LIT)
    out.add_argument("--source", required=True)
    args = parser.parse_args(argv)
    sys.path.insert(0, str(WT))
    entries = runs()
    if args.command == "rows":
        print(json.dumps(entries, indent=1))
        return 0
    if args.command == "run":
        by_fixture = {e["fixture"]: e for e in entries}
        for name in args.fixtures:
            entry = by_fixture[name]
            path = args.work_dir / name / "record.json"

            def write(record: dict, path: Path = path) -> None:
                path.write_text(json.dumps(record, indent=1) + "\n")

            record = evaluate(
                name, args.work_dir, ap=bool(entry["ap"]), digits=args.digits, write=write
            )
            print(name, json.dumps({c: v.get("status") for c, v in judge(record, entry).items() if isinstance(v, dict) and "status" in v}), flush=True)
        return 0
    records = {
        path.parent.name: _load(path) for path in sorted(args.records.glob("*/record.json"))
    }
    args.output.write_text(json.dumps(lit(records, entries, args.source), indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
