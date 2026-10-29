# SPDX-License-Identifier: 0BSD
"""The M-QCD validation campaign: manifest, references, evaluation and the
acceptance rules of ``m-qcd/PLAN.md`` §1.4.

The manifest (``tests/fixtures/loop/mqcd/manifest.json``) holds one record
per campaign row (PLAN §4.2): the request (process, restriction, fixed
parameters, gauge, Born and loop orders, vetoes), its reference, the points
per tier, the expected predicted and unpredicted pole sectors, the extras and
the structural features it covers, and the listings the rules require (the
binary64 points outside the O1 scope, named reference outliers, coefficients
that vanish identically).

The rules (PLAN §1.4; no tolerance is widened):

1. double-double against the row's primary provider, strictly relative,
   rel <= the row's ``reference_tolerance`` per sector and coefficient, Born
   included: 1e-12 at 2->2 and 2->3, 1e-10 from 2->4 up (the user's ruling of
   2026-10-29 ~01:12: up to 1e-7 at 2->5 and beyond only where the
   providers' own precision requires it, stated per row); a listed reference
   outlier passes only if the provider's own accuracy covers the difference
   and a second provider agrees with double-double within the same
   tolerance; a coefficient that vanishes identically stays absolute at
   1e-12 F_s;
2. binary64 against our own double-double at the same point (the user's O1
   rule): E <= 1e-12 -> 1e-12, 1e-12 < E <= 1e-9 -> E, E > 1e-9 outside the
   binary64 scope, listed (an unlisted one fails, as does a stale listing);
   the Born (no estimate) is held to 1e-12;
3. the binary64 error against double-double is at most 10 E per coefficient
   at every point;
4. the poles equal Catani's: double-double within max(1e-24, 10 E_DD),
   binary64 in the bands of rule 2; the predicted and unpredicted sector sets
   equal the manifest's;
5. (``uv``) the bare loop's UV poles plus the UV-local counterterms cancel
   sum_legs delta-Z x Born per sector (Feynman-gauge Z^UV, n_f from the
   request), in double-double within max(1e-24, 10 E_DD);
6. (``ap``) arbitrary precision at 40 digits against double-double within
   max(1e-24, 10 E_DD), and against 60 digits within 1e-35;
7. (``nc``) LC/NLC projections: routed to MQ-NC (manifest ``extras_pending``).

(``ward``) O10 on the native input path (``loops.v2.ward``): at the row's
first point every external massless vector leg (or the manifest's
``ward_legs``), epsilon_j -> c p_j / p_j^0 for c = 1 and c = i, judged by
``ward.ward_row`` in binary64 (the O1 rule with the exact value 0) and in
double-double (|V_k| <= 1e-25 of the physical scale, the Born within 1e-24).

A reference point carries MQ-REF's record (``rows[i].reference``): status
``none`` (no provider reference at M-QCD accuracy: rule 1 is recorded as
not asserted with the record's reason, rules 2-4 hold the point) or ``ok``,
compared relatively, or absolutely against a regular neighbour (the S3
zero points, which the manifest's ``zero_points`` must name).

E is the stability estimate of one exact rotation (z, 3/5, 4/5) plus the
reduction-direction check (the O1 configuration,
``generation.loop_service._BINARY64_CHECK_ROTATIONS``). A coefficient that
vanishes identically (manifest ``vanishing``) is checked absolutely,
|a - r| <= 1e-12 F_s with F_s = |B_s| alpha_s / 2 pi.

``python -m tools.loop_benchmark.mqcd run A12 --points 0 1`` runs rows outside
pytest; the test modules ``tests/unit/test_loop_v2_mqcd_*.py`` run the tiers
and, with ``PYAMPLICOL_MQCD_RESULTS`` set, write one record per row and tier
for ``docs/performance_reports/loop/scripts/build_mqcd.py``.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "loop"
MANIFEST = FIXTURES / "mqcd" / "manifest.json"
RESULTS_ENVIRONMENT = "PYAMPLICOL_MQCD_RESULTS"
LOG = logging.getLogger("pyamplicol.mqcd")

LAURENT = ("finite", "single_pole", "double_pole")
COEFFICIENTS = ("born", *LAURENT)
TOTAL = "total"

REFERENCE_TOLERANCE = 1e-12  # rule 1 at 2->2 and 2->3 (the absolute checks)
# Rule 1 from 2->4 up (user, slice-status DECISIONS 2026-10-29 ~01:12): the
# providers' own precision; 2->5 and beyond may go up to the ceiling where a
# row's providers require it (the manifest states each row's tolerance).
REFERENCE_TOLERANCE_HIGH = 1e-10
REFERENCE_TOLERANCE_CEILING = 1e-7
O1_STRICT = 1e-12  # rule 2: E <= 1e-12
O1_CAP = 1e-9  # rule 2: E above it is outside the binary64 scope
BRACKET = 10  # rule 3 (and the 10 E bounds of rules 4-6)
DD_FLOOR = 1e-24  # rules 4-6
# A helicity configuration vanishes (its Born is an exact zero, so MadLoop's
# values are the rounding of a zero and are compared absolutely) when our
# double-double Born is at most this fraction of the summed Born; physical
# helicity suppressions are many orders larger.
VANISHING_HELICITY = 1e-24
AP_CONVERGENCE = 1e-35  # rule 6
CKM_RELATION = 1e-24  # PLAN §4.1: the H rows' CKM-factor relation in DD
AP_DIGITS = (40, 60)
CHECK_ROTATION = ("z", "3/5", "4/5")

TIERS = ("default", "nightly")
STATUSES = ("active", "pending")
# The packages a pending row or extra may wait for (PLAN §3.0).
UNBLOCKERS = (
    "MQ-REF",
    "MQ-MODEL",
    "MQ-5F",
    "MQ-NC",
    "MQ-WARD",
    "MQ-SELECT",
    "MQ-STAB",
    "MQ-VALIDATE",
)
EXTRAS = ("nc", "ap", "ward", "uv", "hel", "sp")
# Extras this harness checks today (the others are listed as pending).
# ``sp`` (PLAN §4.1 special points S1-S4) is checked by the row's gating
# variants (``<id>@<name>``: the special-point references on the base row's
# generation), so a row with ``sp`` and no gating variant is malformed.
IMPLEMENTED_EXTRAS = frozenset({"ap", "uv", "hel", "sp", "ward"})


Sector = tuple[tuple[str, int], ...]


def sector_key(orders: Mapping[str, Any] | Sequence[Sequence[Any]]) -> Sector:
    """The engine's sector key of squared coupling orders: (name, power)
    pairs, zero powers dropped, sorted by name."""

    items = orders.items() if isinstance(orders, Mapping) else orders
    return tuple(sorted((str(k), int(v)) for k, v in items if int(v)))


def sector_text(sector: Sector | str) -> str:
    if isinstance(sector, str):
        return sector
    return " ".join(f"{name}^{power}" for name, power in sector) or "1"


# ----------------------------------------------------------------- manifest


@dataclass(frozen=True)
class Row:
    """One campaign row of the manifest (PLAN §4.2)."""

    id: str
    cls: str
    process: str
    born_orders: Mapping[str, int]
    loop_orders: Mapping[str, int] | tuple[Mapping[str, int], ...]
    restriction: str
    restriction_code: str
    fixed_parameters: Mapping[str, str]
    gauge: str
    scheme: str
    tier: str
    status: str
    reference: Mapping[str, Any] | None
    points: Mapping[str, tuple[int, ...]]
    extras: tuple[str, ...]
    features: tuple[str, ...]
    predicted_sectors: tuple[Sector, ...]
    unpredicted_sectors: tuple[Sector, ...]
    particle_veto: tuple[int, ...] = ()
    corrections: tuple[str, ...] = ("QCD",)
    inputs: str = "python"
    parameters: Mapping[str, str] = field(default_factory=dict)
    pending: Mapping[str, str] | None = None
    extras_pending: Mapping[str, str] = field(default_factory=dict)
    binary64_out_of_scope: tuple[Mapping[str, Any], ...] = ()
    reference_outliers: tuple[Mapping[str, Any], ...] = ()
    vanishing: tuple[Mapping[str, Any], ...] = ()
    # Reference fixed parameters the model does not have (MadLoop's WTau).
    ignored_fixed_parameters: tuple[str, ...] = ()
    notes: str = ""
    # A variant ("<id>@<name>") shares its base row's request and generation
    # with another reference (a runtime parameter change, a diagnostic twin);
    # a non-gating variant is a diagnostic the test tiers do not assert.
    base: str | None = None
    gating: bool = True
    # A variant that is one subprocess of a multiparticle base row (its own
    # process and generation; M01).
    subprocess: bool = False
    # Born-zero points (S3, a radiation zero) -> their regular neighbour:
    # every coefficient there vanishes and is checked absolutely against
    # 1e-12 of the neighbour's Born (its F for the Laurent coefficients).
    zero_points: Mapping[int, int] = field(default_factory=dict)
    # Rule 4's prediction: "python" (the Python-input path's Catani operator,
    # every row on that route) or "none" for a row on the native-input route,
    # which forms no prediction (WP3.1 I5c): rule 4 is then recorded as not
    # asserted (the manifest names the gap), its poles held by rule 1 only.
    catani: str = "python"
    # The fixture holding MadLoop's per-helicity rows (``per_helicity``) when
    # it is not the row's reference (manifest path), for the ``hel`` extra.
    helicity_reference: str | None = None
    variants: tuple[Mapping[str, Any], ...] = ()
    # PLAN §4.1's exact relation of the H rows (manifest ``ckm_relation``):
    # ``twin_process`` (the diagonal twin, same masses and restriction) and
    # the CKM entries (model parameter names) whose |.|^2 products form the
    # factor numerator / denominator.
    ckm_relation: Mapping[str, Any] | None = None
    # The legs of the ``ward`` extra (None: every external massless vector
    # leg, ``ward.gauge_legs``).
    ward_legs: tuple[int, ...] | None = None
    # Binary64 Ward evaluations outside the O1 scope (E_k > 1e-9 of the
    # physical scale): {point, leg, factor: [re, im], E, true_error}, listed
    # like ``binary64_out_of_scope`` (double-double holds the identity, the
    # estimate must still bracket the value tenfold).
    ward_out_of_scope: tuple[Mapping[str, Any], ...] = ()
    # Rule 1's relative tolerance (``REFERENCE_TOLERANCE`` at 2->2 and 2->3,
    # ``REFERENCE_TOLERANCE_HIGH`` from 2->4 up; the manifest states it).
    reference_tolerance: float = REFERENCE_TOLERANCE

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Row:
        loop = data["loop_orders"]
        return cls(
            id=data["id"],
            cls=data["class"],
            process=data["process"],
            born_orders=dict(data["born_orders"]),
            loop_orders=dict(loop)
            if isinstance(loop, Mapping)
            else tuple(dict(x) for x in loop),
            restriction=data["restriction"],
            restriction_code=data["restriction_code"],
            fixed_parameters=dict(data.get("fixed_parameters", {})),
            gauge=data.get("gauge", "unitary"),
            scheme=data.get("scheme", "qcd"),
            tier=data["tier"],
            status=data["status"],
            reference=data.get("reference"),
            points={k: tuple(v) for k, v in data.get("points", {}).items()},
            extras=tuple(data.get("extras", ())),
            features=tuple(data.get("features", ())),
            predicted_sectors=tuple(
                sector_key(s) for s in data.get("predicted_sectors", ())
            ),
            unpredicted_sectors=tuple(
                sector_key(s) for s in data.get("unpredicted_sectors", ())
            ),
            particle_veto=tuple(data.get("particle_veto", ())),
            corrections=tuple(data.get("corrections", ("QCD",))),
            inputs=data.get("inputs", "python"),
            parameters=dict(data.get("parameters", {})),
            pending=data.get("pending"),
            extras_pending=dict(data.get("extras_pending", {})),
            binary64_out_of_scope=tuple(data.get("binary64_out_of_scope", ())),
            reference_outliers=tuple(data.get("reference_outliers", ())),
            vanishing=tuple(data.get("vanishing", ())),
            ignored_fixed_parameters=tuple(data.get("ignored_fixed_parameters", ())),
            notes=data.get("notes", ""),
            base=data.get("base"),
            subprocess=bool(data.get("subprocess", False)),
            zero_points={
                int(k): int(v) for k, v in data.get("zero_points", {}).items()
            },
            catani=data.get("catani", "python"),
            helicity_reference=data.get("helicity_reference"),
            gating=bool(data.get("gating", True)),
            variants=tuple(data.get("variants", ())),
            ckm_relation=data.get("ckm_relation"),
            ward_legs=None
            if data.get("ward_legs") is None
            else tuple(int(x) for x in data["ward_legs"]),
            ward_out_of_scope=tuple(data.get("ward_out_of_scope", ())),
            reference_tolerance=float(
                data.get("reference_tolerance", REFERENCE_TOLERANCE)
            ),
        )

    @property
    def active(self) -> bool:
        return self.status == "active"

    def tier_points(self, tier: str) -> tuple[int, ...]:
        """The reference point indices this row runs in ``tier`` (a default
        row's nightly points are the ones its default tier does not run)."""

        return tuple(self.points.get(tier, ()))


def load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    return json.loads(path.read_text())


def rows(manifest: Mapping[str, Any] | None = None) -> dict[str, Row]:
    """The manifest's rows and their variants (``<id>@<name>``)."""

    manifest = manifest or load_manifest()
    out = {}
    for data in manifest["rows"]:
        out[data["id"]] = Row.from_dict(data)
        for variant in data.get("variants", ()):
            merged = {
                **data,
                "pending": None,
                "status": "active",
                "variants": [],
                **variant,
                "id": f"{data['id']}@{variant['name']}",
                "base": data["id"],
            }
            out[merged["id"]] = Row.from_dict(merged)
    return out


def nightly_ids(manifest: Mapping[str, Any] | None = None) -> list[str]:
    """The nightly tier's row test ids: every active gating row or variant
    with nightly points or an extra the harness checks."""

    return sorted(
        name
        for name, row in rows(manifest).items()
        if row.active
        and row.gating
        and (row.tier_points("nightly") or set(row.extras) & IMPLEMENTED_EXTRAS)
    )


def nightly_job(job: int, manifest: Mapping[str, Any] | None = None) -> list[str]:
    """The row ids of nightly file job ``job`` (manifest ``nightly_jobs``:
    rows packed by measured cost so that each file job stays within the
    30-minute budget of PLAN §3.2)."""

    manifest = manifest or load_manifest()
    for entry in manifest["nightly_jobs"]["jobs"]:
        if entry["job"] == job:
            return list(entry["rows"])
    raise KeyError(f"no nightly job {job}")


# --------------------------------------------------------------- references


@dataclass
class Reference:
    """A row's reference, normalised: per point and provider the Born per
    Born sector and the Laurent coefficients per virtual sector (``TOTAL``
    when the provider reports only the sum over sectors), and the provider's
    own accuracy (a number or a per-coefficient mapping) where it states one."""

    source: str
    providers: tuple[str, ...]
    points: list[list[list[str]]]
    scales: list[str]
    parameters: dict[str, str]
    fixed_parameters: dict[str, str] | None
    born: list[dict[str, dict[Any, float]]]
    virtual: list[dict[str, dict[Any, tuple[float, float, float]]]]
    accuracy: list[dict[str, Any]]
    alpha_s: float
    # Per point and provider, what the provider states about its own value
    # (the return status, e.g. MadLoop's 216 = stable in double precision
    # and 3xx = in quadruple precision, and the relative deviation of its
    # double pole from its Born times the universal IR factor): evidence
    # printed with a rule 1 miss, never a pass condition.
    evidence: list[dict[str, dict[str, Any]]] = field(default_factory=list)
    # Per point, MQ-REF's reference record (``rows[i].reference``: status
    # "ok" or "none", comparison "relative" or "absolute" with the regular
    # neighbour ``absolute_scale_row``, the Born's source, the reason), or
    # None where the fixture has none.
    records: list[dict[str, Any] | None] = field(default_factory=list)
    # Per point superseded by MQ-REF's quadruple-precision rerun of the
    # existing reference (``spec["superseded"]``, MQ-REF's ``point_binding``):
    # the binding fixture and its row, whose primary values replaced the
    # existing reference's (its other providers stay the second providers).
    binding: dict[int, tuple[str, int]] = field(default_factory=dict)

    @property
    def primary(self) -> str:
        return self.providers[0]

    def record(self, index: int) -> dict[str, Any] | None:
        return self.records[index] if index < len(self.records) else None


def _strings(point) -> list[list[str]]:
    return [[str(x) for x in leg] for leg in point]


def _scale(mu: Any) -> str:
    return str(Fraction(str(mu)) ** 2)


def _laurent(values: Mapping[str, Any]) -> tuple[float, float, float]:
    return tuple(float(values[k]) for k in LAURENT)


def load_reference(row: Row) -> Reference:
    """The row's reference (``row.reference['format']``: ``required``,
    ``providers``, ``component-control``, ``model-control``, ``dilepton``,
    ``mixed-sm``, ``mqcd``)."""

    spec = row.reference
    if spec is None:
        raise ValueError(f"{row.id} has no reference yet")
    path = ROOT / spec["path"]
    data = json.loads(path.read_text())
    kind = spec["format"]
    loader = _LOADERS[kind]
    reference = loader(row, spec, data)
    reference.source = spec["path"]
    if "providers" in spec:
        missing = set(spec["providers"]) - set(reference.providers)
        if missing:
            raise ValueError(f"{row.id}: reference lacks providers {sorted(missing)}")
        reference.providers = tuple(spec["providers"])
    for index, binding in sorted((spec.get("superseded") or {}).items()):
        _supersede(row, reference, int(index), binding["path"], int(binding["row"]))
    return reference


def _supersede(
    row: Row, reference: Reference, index: int, path: str, other: int
) -> None:
    """The existing reference's point ``index`` is superseded by row
    ``other`` of MQ-REF's quadruple-precision rerun at ``path`` (the same
    exact point and mu_R, an ok record): its primary values (per sector),
    accuracy, evidence and record replace the existing primary's there; the
    existing fixture's other providers stay second providers (rule 1 ii)."""

    data = json.loads((ROOT / path).read_text())
    names = list(data["rows"][0]["providers"])
    first = data.get("primary_provider", names[0])
    rerun = _required(
        row, {"providers": [first, *(n for n in names if n != first)]}, data
    )
    primary = reference.primary
    if rerun.primary != primary:
        raise ValueError(f"{row.id}: {path} primary {rerun.primary} is not {primary}")
    if (rerun.points[other], rerun.scales[other]) != (
        reference.points[index],
        reference.scales[index],
    ):
        raise ValueError(f"{row.id}: {path} row {other} is not point {index}")
    fixed = {**(reference.fixed_parameters or {}), **reference.parameters}
    for name, value in {**(rerun.fixed_parameters or {}), **rerun.parameters}.items():
        if name in fixed and Fraction(str(fixed[name])) != Fraction(str(value)):
            raise ValueError(
                f"{row.id}: {path} has {name} = {value}, not {fixed[name]}"
            )
    record = rerun.record(other)
    if record is None or record.get("status") != "ok":
        raise ValueError(f"{row.id}: {path} row {other} is not an ok reference")
    reference.born[index][primary] = rerun.born[other][primary]
    reference.virtual[index][primary] = rerun.virtual[other][primary]
    reference.accuracy[index][primary] = rerun.accuracy[other][primary]
    if reference.evidence:
        reference.evidence[index][primary] = rerun.evidence[other][primary]
    while len(reference.records) <= index:
        reference.records.append(None)
    reference.records[index] = record
    reference.binding[index] = (path, other)


def _required(row, spec, data) -> Reference:
    """A required-format fixture (``tools/loop_reference``): every provider's
    totals per point; where a row carries MadLoop's squared split orders
    (``rows[i].sectors``, MQ-REF item 4) the primary provider's Born and
    Laurent coefficients per sector, with MadLoop's own accuracy per loop
    sector."""

    providers = tuple(spec.get("providers") or data["rows"][0]["providers"])
    born, virtual, accuracy, evidence, records = [], [], [], [], []
    for entry in data["rows"]:
        b, v, a, e = {}, {}, {}, {}
        for name in providers:
            values = entry["providers"][name]
            b[name] = {TOTAL: float(values["born"])}
            v[name] = {TOTAL: _laurent(values)}
            a[name] = values.get("accuracy", values.get("estimated_relative_accuracy"))
            e[name] = {
                key: values[key]
                for key in ("status", "universal_double_pole_relative_error")
                if values.get(key) is not None
            }
        record = entry.get("reference")
        if record is not None and providers[0] in e:
            # The primary's Born source and its Born / double-pole mismatch
            # (MQ-REF's per-point record): evidence with a rule 1 miss.
            e[providers[0]].update(
                {
                    key: record[key]
                    for key in ("born_source", "born_double_pole_relative_mismatch")
                    if record.get(key) is not None
                }
            )
        records.append(record)
        evidence.append(e)
        sectors = entry.get("sectors")
        if sectors and providers[0] == data.get("primary_provider", "madloop"):
            primary = providers[0]
            b[primary] = {
                sector_key({k: s[k] for k in ("QCD", "QED")}): float(s["born"])
                for s in sectors["born"]
            }
            v[primary] = {
                sector_key({k: s[k] for k in ("QCD", "QED")}): _laurent(s)
                for s in sectors["loop"]
            }
            a[primary] = {
                sector_text(sector_key({k: s[k] for k in ("QCD", "QED")})): s.get(
                    "accuracy"
                )
                for s in sectors["loop"]
            }
        born.append(b)
        virtual.append(v)
        accuracy.append(a)
    # A runtime parameter change of the run (``parameter_overrides``, the
    # S4 rows: e.g. MB = 4.5 and aS = 0.13 on top of the card).
    parameters = {**data["parameters"], **data.get("parameter_overrides", {})}
    return Reference(
        "",
        providers,
        [_strings(p) for p in data["points"]],
        [_scale(mu) for mu in data["mu_r"]],
        parameters,
        dict(data.get("fixed_parameters", {})),
        born,
        virtual,
        accuracy,
        float(parameters["aS"]),
        evidence,
        records,
    )


def _providers(row, spec, data) -> Reference:
    """``v2/gg_gg_providers.json``: the providers per point, no parameters
    (the manifest's ``parameters`` state them)."""

    providers = tuple(spec.get("providers") or data["validated_providers"])
    born, virtual = [], []
    for entry in data["rows"]:
        born.append(
            {p: {TOTAL: float(entry["providers"][p]["born"])} for p in providers}
        )
        virtual.append({p: {TOTAL: _laurent(entry["providers"][p])} for p in providers})
    return Reference(
        "",
        providers,
        [_strings(p) for p in data["points"]],
        [_scale(mu) for mu in data["mu_r"]],
        dict(row.parameters),
        None,
        born,
        virtual,
        [{} for _ in data["rows"]],
        float(row.parameters["aS"]),
    )


def _component_control(row, spec, data) -> Reference:
    """A MadLoop component control (``quark-gluon-component-control.json``):
    ``fixture`` holds the request and points; each row its Born and ``full``."""

    fixture = data["fixture"]
    mu = fixture["parameters"]["mu"]
    born = [{"madloop": {TOTAL: float(r["born"])}} for r in data["rows"]]
    virtual = [{"madloop": {TOTAL: _laurent(r["full"])}} for r in data["rows"]]
    return Reference(
        "",
        ("madloop",),
        [_strings(p) for p in fixture["points"]],
        [_scale(Fraction(str(mu)).limit_denominator(10**9)) for _ in data["rows"]],
        dict(row.parameters),
        None,
        born,
        virtual,
        [{} for _ in data["rows"]],
        float(row.parameters["aS"]),
    )


def _model_control(row, spec, data) -> Reference:
    """``top-pair-model.json`` style: ``rows[key]`` per process key with the
    Born, MadLoop's accuracy and the ``full`` component."""

    entries = data["rows"][spec["key"]]
    born = [{"madloop": {TOTAL: float(r["born"])}} for r in entries]
    virtual = [{"madloop": {TOTAL: _laurent(r["components"]["full"])}} for r in entries]
    accuracy = [{"madloop": r.get("madloop_accuracy")} for r in entries]
    parameters = {k: v for k, v in data["parameters"].items() if k != "MU_R"}
    return Reference(
        "",
        ("madloop",),
        [_strings(p) for p in data["points"]],
        [_scale(mu) for mu in data["mu_r"]],
        parameters,
        dict(data.get("fixed_parameters", {})),
        born,
        virtual,
        accuracy,
        float(parameters["aS"]),
    )


def _dilepton(row, spec, data) -> Reference:
    """``dilepton-two-gluon.json``: MadLoop per row, Recola converted; with
    ``"points": "precision"`` its exact rational points (``precision_points``,
    exactly massless with exact momentum conservation) instead of the rounded
    RAMBO ones."""

    exact = spec.get("points") == "precision"
    entries = data["precision_rows" if exact else "rows"]
    points = data["precision_points" if exact else "points"]
    born, virtual = [], []
    for entry in entries:
        born.append(
            {
                "madloop": {TOTAL: float(entry["born"])},
                "recola": {TOTAL: float(entry["recola_converted"]["born"])},
            }
        )
        virtual.append(
            {
                "madloop": {TOTAL: _laurent(entry)},
                "recola": {TOTAL: _laurent(entry["recola_converted"])},
            }
        )
    parameters = {k: v for k, v in data["parameters"].items() if k != "MU_R"}
    return Reference(
        "",
        ("madloop", "recola"),
        [_strings(p) for p in points],
        [_scale(mu) for mu in data["mu_r"]],
        parameters,
        dict(data.get("fixed_parameters", {})),
        born,
        virtual,
        [{} for _ in entries],
        float(parameters["aS"]),
    )


def _mixed_sm(row, spec, data) -> Reference:
    """``tools/loop_reference/uudd_mixed_sm_qcd.json``: MadLoop per squared
    split order (Born and virtual), one renormalisation scale."""

    born_keys = {k: sector_key(v) for k, v in data["born_squared_orders"].items()}
    loop_keys = {k: sector_key(v) for k, v in data["virtual_squared_orders"].items()}
    born, virtual, accuracy = [], [], []
    for entry in data["rows"]:
        born.append(
            {"madloop": {born_keys[k]: float(v) for k, v in entry["born"].items()}}
        )
        virtual.append(
            {"madloop": {loop_keys[k]: _laurent(v) for k, v in entry["full"].items()}}
        )
        accuracy.append(
            {
                "madloop": {
                    loop_keys[k]: v.get("accuracy") for k, v in entry["full"].items()
                }
            }
        )
    parameters = {k: v for k, v in data["parameters"].items() if k != "MU_R"}
    scale = str(data["mu_r2"])
    return Reference(
        "",
        ("madloop",),
        [_strings(p) for p in data["points"]],
        [scale for _ in data["rows"]],
        parameters,
        {k: v for k, v in data["fixed_parameters"].items()},
        born,
        virtual,
        accuracy,
        float(parameters["aS"]),
    )


def _mqcd(row, spec, data) -> Reference:
    """A normalised campaign reference (``tests/fixtures/loop/mqcd/
    references``): ``providers`` (primary first), per point ``values[provider]
    = {born, finite, single_pole, double_pole}`` and optional ``accuracy``."""

    providers = tuple(data["providers"])
    born = [
        {p: {TOTAL: float(entry["values"][p]["born"])} for p in providers}
        for entry in data["rows"]
    ]
    virtual = [
        {p: {TOTAL: _laurent(entry["values"][p])} for p in providers}
        for entry in data["rows"]
    ]
    accuracy = [dict(entry.get("accuracy", {})) for entry in data["rows"]]
    parameters = dict(data["parameters"])
    return Reference(
        "",
        providers,
        [_strings(p) for p in data["points"]],
        [_scale(mu) for mu in data["mu_r"]],
        parameters,
        dict(data.get("fixed_parameters", {})),
        born,
        virtual,
        accuracy,
        float(parameters["aS"]),
    )


def _process_control(row, spec, data) -> Reference:
    """``top-pair-ee-model-control.json`` style: ``processes[key].rows`` with
    MadLoop's Born, Laurent coefficients, status and accuracy (strings), the
    run's ``runtime_parameters`` (the card's other values are the
    restriction's defaults; ``all_widths`` 0 is the row's fixed widths)."""

    entries = data["processes"][spec["key"]]["rows"]
    born = [{"madloop": {TOTAL: float(r["born"])}} for r in entries]
    virtual = [{"madloop": {TOTAL: _laurent(r)}} for r in entries]
    accuracy = [{"madloop": float(r["accuracy"])} for r in entries]
    parameters = {
        k: v
        for k, v in data["runtime_parameters"].items()
        if k not in ("MU_R", "all_widths")
    }
    return Reference(
        "",
        ("madloop",),
        [_strings(p) for p in data["points"]],
        [_scale(mu) for mu in data["mu_r"]],
        parameters,
        None,
        born,
        virtual,
        accuracy,
        float(parameters["aS"]),
    )


_LOADERS = {
    "required": _required,
    "providers": _providers,
    "component-control": _component_control,
    "model-control": _model_control,
    "dilepton": _dilepton,
    "mixed-sm": _mixed_sm,
    "mqcd": _mqcd,
    "process-control": _process_control,
}
REFERENCE_FORMATS = tuple(_LOADERS)


# --------------------------------------------------------------- evaluation


def _number(value: Any) -> Decimal:
    real = getattr(value, "real", value)
    return Decimal(str(real))


@dataclass
class Evaluated:
    """One point in one carrier: the Born per Born sector, the virtual's
    Laurent coefficients per sector, Catani's poles per predicted sector (or
    None) and the absolute stability estimate per sector and coefficient."""

    carrier: str
    born: dict[Sector, Decimal]
    virtual: dict[Sector, tuple[Decimal, Decimal, Decimal]]
    catani: dict[Sector, tuple[Decimal, Decimal]] | None
    estimate: dict[Sector, tuple[float, float, float]] | None
    seconds: float = 0.0
    components: dict[str, dict[Sector, tuple[Decimal, ...]]] = field(
        default_factory=dict
    )
    # At a Born-zero point (S3) the Born of its regular neighbour: the scale
    # of every coefficient's absolute check (``Row.zero_points``).
    scale_born: Decimal | None = None

    def total(self) -> tuple[Decimal, tuple[Decimal, Decimal, Decimal]]:
        born = sum(self.born.values(), Decimal(0))
        laurent = tuple(
            sum((v[k] for v in self.virtual.values()), Decimal(0)) for k in range(3)
        )
        return born, laurent

    def total_estimate(self) -> tuple[float, float, float] | None:
        if self.estimate is None:
            return None
        return tuple(sum(e[k] for e in self.estimate.values()) for k in range(3))


def evaluated(result: Any, carrier: str, seconds: float = 0.0) -> Evaluated:
    """``Evaluated`` of a ``PointResult``."""

    born = {sector: _number(v) for sector, v in result.born.items()}
    virtual = {
        sector: tuple(_number(x) for x in laurent.coefficients)
        for sector, laurent in result.components["virtual"].items()
    }
    catani = None
    if result.ir_poles is not None:
        catani = {
            sector: (_number(single), _number(double))
            for sector, (single, double) in result.ir_poles.items()
        }
    estimate = None
    if result.stability is not None:
        estimate = {
            sector: tuple(abs(float(x)) for x in budget.coefficients)
            for sector, budget in result.stability.absolute.items()
        }
    components = {
        name: {
            sector: tuple(_number(x) for x in laurent.coefficients)
            for sector, laurent in sectors.items()
        }
        for name, sectors in result.components.items()
    }
    return Evaluated(carrier, born, virtual, catani, estimate, seconds, components)


def check_rotation():
    from pyamplicol.loops.v2.stability import Rotation

    return Rotation.about(*CHECK_ROTATION)


def check_configuration():
    """The O1 estimate's checks: one exact rotation plus the reduction
    direction."""

    from pyamplicol.loops.v2.stability import StabilityChecks

    return StabilityChecks((check_rotation(),), True)


def compile_restriction(ufo: Path, restriction: str, root: Path) -> Any:
    """loop_sm under ``restriction`` with the scalar-arity view of the tools
    route (``tests/conftest.py`` ``loop_sm_compiled_model``; MQ-MODEL moves
    the repair into production)."""

    from dataclasses import replace

    from pyamplicol.models.loading import compile_model_source, load_compiled_model
    from tools.loop_reference.model_compatibility import (
        prepare_loop_sm_scalar_declarations,
    )

    root.mkdir(parents=True, exist_ok=True)
    model = compile_model_source(
        ufo, restriction=restriction, cache_dir=root / "model-cache"
    )
    model = replace(
        model,
        raw_loop_model=prepare_loop_sm_scalar_declarations(
            model.raw_loop_model
        ).derived,
        _serialized_path=None,
        _prepared_bundle=None,
    )
    return load_compiled_model(model.write(root / f"loop-sm-{restriction}.json"))


def slice_request(row: Row, **changes: Any) -> Any:
    from pyamplicol.loops.v2.assemble import SliceRequest

    return SliceRequest(
        row.process,
        dict(row.born_orders),
        row.loop_orders
        if isinstance(row.loop_orders, Mapping)
        else tuple(row.loop_orders),
        corrections=tuple(row.corrections),
        fixed_parameters=dict(row.fixed_parameters),
        particle_veto=tuple(row.particle_veto),
        **changes,
    )


class RowRun:
    """A row's generated slice and native executor (generated once, shared by
    every carrier, point and check of the row)."""

    def __init__(
        self, row: Row, compiled: Any, native: Any, base: RowRun | None = None
    ):
        from pyamplicol.loops.v2.assemble import LoopSlice
        from pyamplicol.loops.v2.plan_export import NativeExecutor, export_plan

        self.row = row
        self.compiled = compiled
        self.native = native
        self._twin: RowRun | None = None
        self._ward: Any = None
        self.reference = load_reference(row)
        # (point, carrier) -> the native executor's reasons for a failed point
        self.failures: dict[tuple[int, str], str] = {}
        if base is not None:
            # A variant: the base row's request, generation and executor.
            if slice_request(row) != slice_request(base.row):
                raise ValueError(f"{row.id} changes its base row's request")
            self.slice, self.executor = base.slice, base.executor
            self.generate_seconds = self.export_seconds = 0.0
            self.parameters = {**self.reference.parameters, **dict(row.parameters)}
            return
        start = time.perf_counter()
        LOG.info("%s: generating %s", row.id, row.process)
        self.slice = LoopSlice.generate(compiled, slice_request(row), native)
        self.generate_seconds = time.perf_counter() - start
        LOG.info("%s: generated in %.1f s", row.id, self.generate_seconds)
        start = time.perf_counter()
        if row.inputs == "native":
            self.executor = NativeExecutor(self.slice, forward=False, inputs="native")
        else:
            self.executor = NativeExecutor(
                self.slice,
                forward=False,
                exported=export_plan(self.slice, forward=False),
            )
        self.export_seconds = time.perf_counter() - start
        self.parameters = {**self.reference.parameters, **dict(row.parameters)}

    def evaluate(
        self,
        indices: Sequence[int],
        carrier: str,
        *,
        poles: str = "all",
        stability: bool = True,
    ) -> list[Evaluated]:
        from pyamplicol.loops.v2.assemble import Precision

        precision = {
            "double": Precision.double(),
            "double-double": Precision.double_double(),
        }.get(carrier)
        if precision is None:
            precision = Precision.arbitrary(int(carrier.removeprefix("arbitrary-")))
        reference = self.reference
        start = time.perf_counter()
        LOG.info(
            "%s: %s at points %s (poles %s)", self.row.id, carrier, list(indices), poles
        )
        from pyamplicol.loops.v2.plan_export import FailedPoints

        try:
            results = self.executor.evaluate(
                [reference.points[i] for i in indices],
                [reference.scales[i] for i in indices],
                parameters=self.parameters,
                precision=precision,
                poles=poles,
                stability=check_configuration() if stability else None,
            )
        except FailedPoints as error:
            # A failed point fails alone (its reasons are the finding);
            # the others are complete.
            results = error.results
            self.failures.update(
                {(indices[k], carrier): "; ".join(v) for k, v in error.failures.items()}
            )
        seconds = (time.perf_counter() - start) / max(1, len(indices))
        LOG.info("%s: %s done, %.1f s per point", self.row.id, carrier, seconds)
        return [None if r is None else evaluated(r, carrier, seconds) for r in results]

    def ward(self, index: int, carrier: str) -> dict[str, Any]:
        """``ward.ward_check`` of reference point ``index`` in ``carrier``
        on the row's Ward slice (its request on the full tree kernels,
        ``ward.ward_slice``, with native inputs; generated once)."""

        from pyamplicol.loops.v2 import ward
        from pyamplicol.loops.v2.plan_export import NativeExecutor

        if self._ward is None:
            start = time.perf_counter()
            slice_ = ward.ward_slice(
                self.compiled, slice_request(self.row), self.native
            )
            self._ward = NativeExecutor(slice_, inputs="native", forward=False)
            LOG.info(
                "%s: Ward slice in %.1f s", self.row.id, time.perf_counter() - start
            )
        LOG.info("%s: Ward check, %s, point %d", self.row.id, carrier, index)
        return ward.ward_check(
            self._ward,
            self.reference.points[index],
            self.reference.scales[index],
            carrier,
            legs=self.row.ward_legs,
            parameters=self.parameters,
        )

    def twin(self) -> RowRun:
        """The row's diagonal twin (``ckm_relation.twin_process``: the same
        request, restriction and points with the twin's process), generated
        once."""

        if self._twin is None:
            twin = replace(
                self.row,
                id=f"{self.row.id}~twin",
                process=self.row.ckm_relation["twin_process"],
                ckm_relation=None,
                variants=(),
            )
            self._twin = RowRun(twin, self.compiled, self.native)
        return self._twin

    def legs(self) -> list[tuple[int, bool]]:
        """(|colour|, massive) of every external leg (the prepared model's
        particle records)."""

        from pyamplicol.loops.v2.families import ZERO

        records = {r["name"]: r for r in self.slice.data["particles"]}
        return [
            (abs(int(records[leg.field]["color"])), leg.mass.mass != ZERO)
            for leg in self.slice.families.legs
        ]

    def loop_flavours(self) -> int:
        """The n_f of the gluon's Z^UV: colour-triplet fermion species that
        are perturbative in the strong order and not vetoed (the request's
        loop quarks, massive ones included: UV poles do not decouple)."""

        veto = set(self.slice.request.particle_veto)
        records = {}
        for record in self.slice.data["particles"]:
            records.setdefault(abs(int(record["pdg_code"])), record)
        orders = self.slice.prepared.structure.perturbative_species_orders
        count = 0
        for pdg, species_orders in orders.items():
            pdg = abs(int(pdg))
            record = records.get(pdg)
            if record is None or pdg in veto or "QCD" not in set(species_orders):
                continue
            if abs(int(record["color"])) == 3 and int(record["spin"]) == 2:
                count += 1
        return count


# --------------------------------------------------------------- the rules


@dataclass(frozen=True)
class Check:
    """One assertion of a rule: ``passed`` when ``error <= bound`` (or the
    rule's set condition holds); ``asserted`` False for a binary64 value
    outside the O1 scope (rule 2), which the manifest lists."""

    rule: str
    point: int | None
    carrier: str
    sector: str
    coefficient: str
    value: str
    reference: str
    error: float
    bound: float
    passed: bool
    asserted: bool = True
    note: str = ""


def relative(a: Any, r: Any) -> float:
    """rel(a, r) = |a - r| / max(|a|, |r|): strictly relative, no floor
    (0 for a == r == 0, inf for a vanishing pair that differs)."""

    a, r = Decimal(str(a)), Decimal(str(r))
    with localcontext() as context:
        context.prec = 80
        scale = max(abs(a), abs(r))
        if scale == 0:
            return 0.0
        return float(abs(a - r) / scale)


def _absolute(a: Any, r: Any) -> float:
    with localcontext() as context:
        context.prec = 80
        return float(abs(Decimal(str(a)) - Decimal(str(r))))


def o1_bound(estimate: float) -> float | None:
    """The binary64 bound of the O1 rule for a relative estimate E (rule 2),
    None outside its scope (E > 1e-9)."""

    if estimate <= O1_STRICT:
        return O1_STRICT
    if estimate <= O1_CAP:
        return estimate
    return None


def _listed(entries: Iterable[Mapping[str, Any]], **match: Any) -> bool:
    return any(all(entry.get(k) == v for k, v in match.items()) for entry in entries)


def _vanishing(row: Row, sector: str, coefficient: str) -> bool:
    return _listed(row.vanishing, sector=sector, coefficient=coefficient)


def born_sector(sector: Sector) -> Sector:
    """The Born sector of a QCD-corrected virtual sector (two QCD powers
    fewer)."""

    orders = dict(sector)
    orders["QCD"] = orders.get("QCD", 0) - 2
    return sector_key(orders)


def _ours(
    point: Evaluated, sector: Any
) -> tuple[Decimal, tuple[Decimal, ...], tuple[float, ...] | None]:
    """(Born, Laurent, absolute estimate) of a virtual sector or the total."""

    if sector == TOTAL:
        born, laurent = point.total()
        return born, laurent, point.total_estimate()
    born = point.born.get(born_sector(sector), Decimal(0))
    estimate = None if point.estimate is None else point.estimate.get(sector)
    return born, point.virtual.get(sector), estimate


def _flux(born: Any, alpha_s: float) -> float:
    return abs(float(born)) * alpha_s / (2 * math.pi)


def born_scale(row: Row, point: Evaluated, sector: Any) -> Decimal:
    """|B_s| of a Born sector (``TOTAL``: the summed Born), the scale of the
    absolute checks of identically vanishing coefficients (F_s = |B_s|
    alpha_s / 2 pi); for a Born sector that itself vanishes identically (a
    colour-forbidden interference, listed in ``vanishing``) the summed
    |B| over Born sectors, the Born's own scale."""

    if point.scale_born is not None:
        return point.scale_born
    if sector == TOTAL:
        return abs(point.total()[0])
    if _vanishing(row, sector_text(sector), "born"):
        return sum((abs(b) for b in point.born.values()), Decimal(0))
    return abs(point.born.get(sector, Decimal(0)))


def rule1(row: Row, reference: Reference, index: int, dd: Evaluated) -> list[Check]:
    """Double-double against the primary provider (and the outlier rule)."""

    checks = []
    providers = reference.providers
    primary = reference.primary
    born_values = reference.born[index][primary]
    virtual_values = reference.virtual[index][primary]
    single = len(virtual_values) == 1

    def other_born(provider: str, sector) -> float | None:
        found = reference.born[index][provider]
        if sector not in found and single and len(born_values) == 1:
            sector = TOTAL  # a second provider's total of the single sector
        return found.get(sector)

    def other_virtual(provider: str, sector, k: int) -> float | None:
        found = reference.virtual[index][provider]
        if sector not in found and single:
            sector = TOTAL
        return None if sector not in found else found[sector][k]

    if TOTAL not in virtual_values:
        # Per-sector references: our sectors are the provider's.
        checks.append(Check(
            "1", index, "double-double", "", "sectors",
            ", ".join(sorted(map(sector_text, dd.virtual))),
            ", ".join(sorted(map(sector_text, virtual_values))), 0.0, 0.0,
            set(dd.virtual) == set(virtual_values),
            note="virtual sectors against the provider's split orders"))  # fmt: skip
    for sector, value in born_values.items():
        mine = dd.total()[0] if sector == TOTAL else dd.born.get(sector, Decimal(0))
        text = sector_text(sector)
        checks.append(
            _reference_check(
                row,
                reference,
                index,
                text,
                "born",
                mine,
                value,
                providers,
                lambda p, s=sector: other_born(p, s),
                # A vanishing Born sector: absolutely, against the Born.
                float(born_scale(row, dd, TOTAL)),
            )
        )
    for sector, laurent in virtual_values.items():
        _born, mine, _estimate = _ours(dd, sector)
        text = sector_text(sector)
        if mine is None:
            checks.append(
                Check(
                    "1",
                    index,
                    "double-double",
                    text,
                    "virtual",
                    "absent",
                    str(laurent),
                    math.inf,
                    row.reference_tolerance,
                    False,
                    note="the reference's sector is absent from ours",
                )
            )
            continue
        flux = _flux(
            born_scale(row, dd, sector if sector == TOTAL else born_sector(sector)),
            reference.alpha_s,
        )
        for k, name in enumerate(LAURENT):
            checks.append(
                _reference_check(
                    row,
                    reference,
                    index,
                    text,
                    name,
                    mine[k],
                    laurent[k],
                    providers,
                    lambda p, s=sector, k=k: other_virtual(p, s, k),
                    flux,
                )
            )
    return checks


def _accuracy(reference: Reference, index: int, provider: str, sector, name):
    """The provider's own accuracy of a coefficient: a number, or a mapping
    per coefficient name or per sector (its text)."""

    found = reference.accuracy[index].get(provider)
    if isinstance(found, Mapping):
        found = found.get(name, found.get(sector))
    return None if found is None or float(found) < 0 else float(found)


def _miss_evidence(
    reference: Reference,
    index: int,
    primary: str,
    accuracy: float | None,
    seconds: Mapping[str, float],
) -> str:
    """What a rule 1 miss is to be judged by (no pass condition): the
    primary's own accuracy and status, the deviation of its double pole from
    its Born times the universal IR factor, and the second providers'
    deviations from double-double."""

    stated = (reference.evidence[index] if reference.evidence else {}).get(primary, {})
    parts = [f"own accuracy {accuracy!r}"]
    if "status" in stated:
        parts.append(f"status {stated['status']}")
    if "universal_double_pole_relative_error" in stated:
        parts.append(
            "its double pole off its Born x the universal factor by "
            f"{float(stated['universal_double_pole_relative_error']):.3g}"
        )
    if "born_source" in stated:
        parts.append(f"Born from {stated['born_source']}")
    if "born_double_pole_relative_mismatch" in stated:
        parts.append(
            "Born / double-pole mismatch "
            f"{float(stated['born_double_pole_relative_mismatch']):.3g}"
        )
    parts.append(
        "second providers "
        + (", ".join(f"{p} {e:.3g}" for p, e in seconds.items()) or "none")
    )
    return " (" + "; ".join(parts) + ")"


def _reference_check(
    row, reference, index, sector, name, mine, value, providers, other, flux
) -> Check:
    primary = providers[0]
    if _vanishing(row, sector, name):
        error = _absolute(mine, value)
        bound = REFERENCE_TOLERANCE * flux
        return Check(
            "1",
            index,
            "double-double",
            sector,
            name,
            str(mine),
            repr(value),
            error,
            bound,
            error <= bound,
            note="vanishes identically: |a - r| <= 1e-12 F_s",
        )
    error = relative(mine, value)
    tolerance = row.reference_tolerance
    listed = _listed(
        row.reference_outliers, point=index, sector=sector, coefficient=name
    )
    if error <= tolerance:
        note = "stale outlier listing" if listed else ""
        return Check(
            "1",
            index,
            "double-double",
            sector,
            name,
            str(mine),
            repr(value),
            error,
            tolerance,
            not listed,
            note=note,
        )
    accuracy = _accuracy(reference, index, primary, sector, name)
    seconds = {
        p: relative(mine, other(p)) for p in providers[1:] if other(p) is not None
    }
    if not listed:
        return Check(
            "1",
            index,
            "double-double",
            sector,
            name,
            str(mine),
            repr(value),
            error,
            tolerance,
            False,
            note=f"against {primary}; not a listed outlier"
            + _miss_evidence(reference, index, primary, accuracy, seconds),
        )
    covered = accuracy is not None and accuracy >= error
    agreeing = [p for p, e in seconds.items() if e <= tolerance]
    passed = covered and bool(agreeing)
    note = (
        f"listed outlier of {primary}: own accuracy {accuracy!r} "
        f"{'covers' if covered else 'does not cover'} {error:.3g}; second "
        f"providers {', '.join(f'{p} {e:.3g}' for p, e in seconds.items()) or 'none'}"
    )
    return Check(
        "1",
        index,
        "double-double",
        sector,
        name,
        str(mine),
        repr(value),
        error,
        tolerance,
        passed,
        note=note,
    )


def rule2_and_3(
    row: Row, reference: Reference, index: int, b64: Evaluated, dd: Evaluated
) -> list[Check]:
    """Binary64 against double-double at the same point: the O1 bands (rule
    2) and the tenfold bracketing of the estimate (rule 3)."""

    checks = []
    for sector, value in dd.born.items():
        mine = b64.born.get(sector)
        text = sector_text(sector)
        if _vanishing(row, text, "born"):
            error = _absolute(mine, value)
            bound = O1_STRICT * float(born_scale(row, dd, TOTAL))
            note = "vanishes identically: against the Born"
            checks.append(Check("2", index, "double", text, "born", repr(mine),
                                str(value), error, bound, error <= bound,
                                note=note))  # fmt: skip
            continue
        error = relative(mine, value)
        listed = _listed(
            row.binary64_out_of_scope, point=index, sector=text, coefficient="born"
        )
        if listed:
            # A limit point's binary64 Born (S1-S3; PLAN §4.1), listed: no
            # estimate exists for the Born, double-double holds it (rule 1).
            checks.append(Check("2", index, "double", text, "born", repr(mine),
                                str(value), error, O1_STRICT, True, asserted=False,
                                note="listed limit-point binary64 Born"))  # fmt: skip
            continue
        checks.append(
            Check(
                "2",
                index,
                "double",
                text,
                "born",
                repr(mine),
                str(value),
                error,
                O1_STRICT,
                error <= O1_STRICT,
            )
        )
    for sector, laurent in dd.virtual.items():
        text = sector_text(sector)
        mine = b64.virtual.get(sector)
        estimate = None if b64.estimate is None else b64.estimate.get(sector)
        flux = _flux(born_scale(row, dd, born_sector(sector)), reference.alpha_s)
        for k, name in enumerate(LAURENT):
            truth = laurent[k]
            got = mine[k]
            absolute = _absolute(got, truth)
            e_abs = estimate[k]
            # Rule 3: the estimate brackets the true error tenfold.
            checks.append(
                Check(
                    "3",
                    index,
                    "double",
                    text,
                    name,
                    str(got),
                    str(truth),
                    absolute,
                    BRACKET * e_abs,
                    absolute <= BRACKET * e_abs,
                    note="absolute error against 10 E",
                )
            )
            if _vanishing(row, text, name):
                bound = REFERENCE_TOLERANCE * flux
                checks.append(
                    Check(
                        "2",
                        index,
                        "double",
                        text,
                        name,
                        str(got),
                        str(truth),
                        absolute,
                        bound,
                        absolute <= bound,
                        note="vanishes identically: 1e-12 F_s",
                    )
                )
                continue
            e_rel = e_abs / abs(float(got)) if float(got) else math.inf
            error = relative(got, truth)
            bound = o1_bound(e_rel)
            listed = _listed(
                row.binary64_out_of_scope, point=index, sector=text, coefficient=name
            )
            if bound is None:
                checks.append(
                    Check(
                        "2",
                        index,
                        "double",
                        text,
                        name,
                        str(got),
                        str(truth),
                        error,
                        e_rel,
                        listed,
                        asserted=False,
                        note=f"E = {e_rel:.3g} > 1e-9: outside the "
                        "binary64 scope" + ("" if listed else ", NOT listed"),
                    )
                )
            else:
                checks.append(
                    Check(
                        "2",
                        index,
                        "double",
                        text,
                        name,
                        str(got),
                        str(truth),
                        error,
                        bound,
                        error <= bound and not listed,
                        note=f"E = {e_rel:.3g}"
                        + ("; stale out-of-scope listing" if listed else ""),
                    )
                )
    return checks


def rule4(
    row: Row, index: int, point: Evaluated, alpha_s: float = 0.118
) -> list[Check]:
    """The virtual's poles against Catani's, and the sector sets."""

    checks = []
    predicted = set(point.catani or ())
    expected = set(row.predicted_sectors)
    checks.append(
        Check(
            "4",
            index,
            point.carrier,
            "",
            "predicted sectors",
            ", ".join(sorted(map(sector_text, predicted))),
            ", ".join(sorted(map(sector_text, expected))),
            0.0,
            0.0,
            predicted == expected,
            note="Catani's predicted sectors",
        )
    )
    unpredicted = set(point.virtual) - predicted
    expected_un = set(row.unpredicted_sectors)
    checks.append(
        Check(
            "4",
            index,
            point.carrier,
            "",
            "unpredicted sectors",
            ", ".join(sorted(map(sector_text, unpredicted))),
            ", ".join(sorted(map(sector_text, expected_un))),
            0.0,
            0.0,
            unpredicted == expected_un,
            note="sectors without a prediction",
        )
    )
    for sector in sorted(predicted & set(point.virtual)):
        text = sector_text(sector)
        poles = point.catani[sector]
        laurent = point.virtual[sector]
        estimate = None if point.estimate is None else point.estimate[sector]
        for k, name in ((1, "single_pole"), (2, "double_pole")):
            got, truth = laurent[k], poles[k - 1]
            if _vanishing(row, text, name):
                # Absolutely, against F_s: 1e-12 in binary64, 1e-24 in DD.
                born = born_scale(row, point, born_sector(sector))
                strict = O1_STRICT if point.carrier == "double" else DD_FLOOR
                bound = strict * _flux(born, alpha_s)
                error = _absolute(got, truth)
                checks.append(
                    Check(
                        "4",
                        index,
                        point.carrier,
                        text,
                        name,
                        str(got),
                        str(truth),
                        error,
                        bound,
                        error <= bound,
                        note="vanishes identically: |a - r| against F_s",
                    )
                )
                continue
            error = relative(got, truth)
            e_rel = estimate[k] / abs(float(got)) if float(got) else math.inf
            if point.carrier == "double":
                bound = o1_bound(e_rel)
                if bound is None:
                    listed = _listed(
                        row.binary64_out_of_scope,
                        point=index,
                        sector=text,
                        coefficient=name,
                    )
                    checks.append(
                        Check(
                            "4",
                            index,
                            "double",
                            text,
                            name,
                            str(got),
                            str(truth),
                            error,
                            e_rel,
                            listed,
                            asserted=False,
                            note=f"E = {e_rel:.3g} > 1e-9: outside the binary64 scope",
                        )
                    )
                    continue
            else:
                bound = max(DD_FLOOR, BRACKET * e_rel)
            checks.append(
                Check(
                    "4",
                    index,
                    point.carrier,
                    text,
                    name,
                    str(got),
                    str(truth),
                    error,
                    bound,
                    error <= bound,
                    note=f"E = {e_rel:.3g}",
                )
            )
    return checks


# Feynman-gauge Z^UV per leg (amplitude delta-Z / 2 enters the interference
# once per leg as delta-Z x Born), single-pole coefficients over alpha_s/4pi,
# exactly.
CA, CF, TF = Fraction(3), Fraction(4, 3), Fraction(1, 2)
PI = Decimal(
    "3.14159265358979323846264338327950288419716939937510582097494459230781640628621"
)


def field_poles(legs: Sequence[tuple[int, bool]], flavours: int) -> Fraction:
    """sum_legs delta-Z^UV (single pole, units of alpha_s / 4 pi)."""

    total = Fraction(0)
    for colour, _massive in legs:
        if colour == 8:
            total += Fraction(5, 3) * CA - Fraction(4, 3) * TF * flavours
        elif colour == 3:
            total -= CF
        elif colour != 1:
            raise ValueError(f"no field factor for colour {colour}")
    return total


def rule5(
    row: Row, index: int, uv: Evaluated, legs, flavours: int, alpha_s: str
) -> list[Check]:
    """bare UV + UV_local + sum_legs delta-Z x Born = 0 per sector, and the
    bare loop's UV double pole vanishes ("uv" selection, double-double);
    ``alpha_s`` is the parameter's exact decimal string."""

    checks = []
    poles = field_poles(legs, flavours)
    with localcontext() as context:
        context.prec = 80
        factor = (
            Decimal(poles.numerator)
            / Decimal(poles.denominator)
            * Decimal(alpha_s)
            / (4 * PI)
        )
    for sector, laurent in uv.virtual.items():
        text = sector_text(sector)
        born = uv.born.get(born_sector(sector), Decimal(0))
        local = uv.components["uv_local"][sector]
        estimate = uv.estimate[sector]
        bare = laurent[1]
        with localcontext() as context:
            context.prec = 80
            residual = bare + local[1] + factor * born
        scale = abs(float(bare))
        e_rel = estimate[1] / scale if scale else math.inf
        bound = max(DD_FLOOR, BRACKET * e_rel)
        error = abs(float(residual)) / scale if scale else math.inf
        checks.append(
            Check(
                "5",
                index,
                uv.carrier,
                text,
                "single_pole",
                str(bare),
                str(-local[1] - factor * born),
                error,
                bound,
                error <= bound,
                note=f"n_f = {flavours}; relative to the bare UV pole",
            )
        )
        double = abs(float(laurent[2]))
        checks.append(
            Check(
                "5",
                index,
                uv.carrier,
                text,
                "double_pole",
                str(laurent[2]),
                "0",
                double,
                0.0,
                double == 0.0,
                note="the bare loop's UV double pole",
            )
        )
    return checks


def rule6(
    row: Row, index: int, dd: Evaluated, ap: Evaluated, ap60: Evaluated
) -> list[Check]:
    """Arbitrary precision against double-double and against 60 digits."""

    checks = []
    for sector, value in ap.born.items():
        text = sector_text(sector)
        error = relative(value, dd.born[sector])
        checks.append(
            Check(
                "6",
                index,
                ap.carrier,
                text,
                "born",
                str(value),
                str(dd.born[sector]),
                error,
                DD_FLOOR,
                error <= DD_FLOOR,
            )
        )
        error = relative(value, ap60.born[sector])
        checks.append(
            Check(
                "6",
                index,
                ap.carrier,
                text,
                "born",
                str(value),
                str(ap60.born[sector]),
                error,
                AP_CONVERGENCE,
                error <= AP_CONVERGENCE,
                note="against 60 digits",
            )
        )
    for sector, laurent in ap.virtual.items():
        text = sector_text(sector)
        estimate = dd.estimate[sector]
        for k, name in enumerate(LAURENT):
            truth = dd.virtual[sector][k]
            error = relative(laurent[k], truth)
            e_rel = estimate[k] / abs(float(truth)) if float(truth) else math.inf
            bound = max(DD_FLOOR, BRACKET * e_rel)
            if _vanishing(row, text, name):
                continue
            checks.append(
                Check(
                    "6",
                    index,
                    ap.carrier,
                    text,
                    name,
                    str(laurent[k]),
                    str(truth),
                    error,
                    bound,
                    error <= bound,
                    note=f"E_DD = {e_rel:.3g}",
                )
            )
            error = relative(laurent[k], ap60.virtual[sector][k])
            checks.append(
                Check(
                    "6",
                    index,
                    ap.carrier,
                    text,
                    name,
                    str(laurent[k]),
                    str(ap60.virtual[sector][k]),
                    error,
                    AP_CONVERGENCE,
                    error <= AP_CONVERGENCE,
                    note="against 60 digits",
                )
            )
    return checks


# ------------------------------------------------------ per-helicity rows


def parameter_modulus_squared(
    compiled: Any, parameters: Mapping[str, str], name: str, digits: int = 60
) -> Decimal:
    """|p|^2 of a model parameter at ``parameters`` (an external one
    exactly, an internal one by its resolved definition at ``digits``
    digits; the engine's own evaluator, ``assemble._definition_value``)."""

    from pyamplicol.loops.v2.assemble import (
        _definition_value,
        _kernel_parameters,
        _substitutions,
    )

    values = _kernel_parameters(compiled, parameters)
    with localcontext() as context:
        context.prec = digits + 10
        if name in values:
            value = Decimal(values[name].numerator) / values[name].denominator
            return value * value
        records = {record.name: record for record in compiled.ir.parameters}
        if name not in records or records[name].nature != "internal":
            raise KeyError(f"{name!r} is no model parameter")
        external = {
            record.name: Decimal(
                parameters.get(
                    record.name, str(compiled.parameter_defaults[record.name][0])
                )
            )
            for record in compiled.ir.parameters
            if record.nature == "external"
            and record.name in compiled.parameter_defaults
        }
        real, imaginary = _definition_value(
            records[name].resolved_expression,
            _substitutions(compiled, external, digits),
            digits,
        )
        return real * real + imaginary * imaginary


def ckm_factor(compiled: Any, parameters: Mapping[str, str], relation) -> Decimal:
    """prod |V_num|^2 / prod |V_den|^2 of a ``ckm_relation``."""

    with localcontext() as context:
        context.prec = 70
        factor = Decimal(1)
        for name in relation["numerator"]:
            factor *= parameter_modulus_squared(compiled, parameters, name)
        for name in relation["denominator"]:
            factor /= parameter_modulus_squared(compiled, parameters, name)
        return factor


def rule_ckm(
    row: Row,
    index: int,
    ours: Evaluated,
    twin: Evaluated,
    factor: Decimal,
) -> list[Check]:
    """PLAN §4.1, the H rows: QCD corrections preserve flavour, so the row
    equals its diagonal twin times the CKM factor, per sector and
    coefficient (Born included), in double-double within 1e-24 (strictly
    relative; a coefficient that vanishes in both is checked absolutely
    against 1e-24 of the row's Born)."""

    checks = []
    scale = abs(ours.total()[0])
    pairs = [
        (sector_text(s), "born", ours.born.get(s), twin.born.get(s))
        for s in sorted(set(ours.born) | set(twin.born))
    ]
    for s in sorted(set(ours.virtual) | set(twin.virtual)):
        mine, theirs = ours.virtual.get(s), twin.virtual.get(s)
        for k, name in enumerate(LAURENT):
            pairs.append((
                sector_text(s), name, None if mine is None else mine[k],
                None if theirs is None else theirs[k]))  # fmt: skip
    for sector, name, mine, theirs in pairs:
        if mine is None or theirs is None:
            checks.append(Check(
                "ckm", index, "double-double", sector, name, str(mine), str(theirs),
                math.inf, CKM_RELATION, False,
                note="the sector is absent from the row or its twin"))  # fmt: skip
            continue
        with localcontext() as context:
            context.prec = 80
            expected = factor * Decimal(str(theirs))
        if Decimal(str(mine)) == 0 and expected == 0:
            error, bound, note = 0.0, CKM_RELATION, "vanishes in both"
        elif abs(expected) <= Decimal(CKM_RELATION) * scale:
            error = _absolute(mine, expected)
            bound = CKM_RELATION * float(scale)
            note = "vanishing in the twin: against 1e-24 of the Born"
        else:
            error, bound, note = relative(mine, expected), CKM_RELATION, ""
        checks.append(Check(
            "ckm", index, "double-double", sector, name, str(mine), str(expected),
            error, bound, error <= bound,
            note=note or f"CKM factor {float(factor):.17g} x the twin "
            f"{row.ckm_relation['twin_process']}"))  # fmt: skip
    return checks


def helicity_reference(row: Row) -> dict[str, Any]:
    """MadLoop's per-helicity rows of the row (``per_helicity`` of its
    reference or of ``row.helicity_reference``): SLOOPMATRIXHEL |M_h|^2 with
    the colour average and identical-particle factor and no helicity
    average, per point a list of {helicity, born, finite, single_pole,
    double_pole, accuracy, status}."""

    path = ROOT / (row.helicity_reference or row.reference["path"])
    found = json.loads(path.read_text()).get("per_helicity")
    if not found:
        raise ValueError(f"{row.id}: {path} has no per-helicity rows")
    return found


def rule_hel(
    row: Row,
    index: int,
    ours: Mapping[tuple[int, ...], Evaluated],
    madloop: Sequence[Mapping[str, Any]],
    alpha_s: float,
    source: str = "",
) -> list[Check]:
    """Per-helicity double-double against MadLoop (PLAN §3.2 item 5, under
    rule 1): every MadLoop helicity configuration, in the external legs'
    order and MG5's helicity labels, equals our helicity row of the same
    labels times the helicity average of the incoming legs (our rows keep
    the inclusive initial average); strictly relative within 1e-12 per
    coefficient. Only a vanishing configuration is checked absolutely: our
    double-double Born at most ``VANISHING_HELICITY`` of the summed Born (an
    exact zero) and MadLoop's within 1e-12 of it (MadLoop returns the
    rounding of a zero); then every coefficient, ours included, against
    1e-12 of the summed Born (its F for the Laurent coefficients). A
    configuration MQ-REF's per-helicity record compares absolutely
    (``reference.comparison`` "absolute") that does not vanish by that test
    (a suppressed helicity) stays strictly relative: the record's reason is
    kept in the note, and is not honoured (an absolute comparison of a
    suppressed helicity would loosen rule 1)."""

    checks = []
    counts = defaultdict(set)
    for helicity in ours:
        for leg, value in enumerate(helicity):
            counts[leg].add(value)
    average = math.prod(len(counts[leg]) for leg in (0, 1))
    total = sum((abs(p.total()[0]) for p in ours.values()), Decimal(0))
    found = {tuple(e["helicity"]) for e in madloop}
    summed = sum(abs(e["born"]) for e in madloop)
    checks.append(Check(
        "hel", index, "double-double", "", "helicity rows", str(len(ours)),
        str(len(found)), 0.0, 0.0, set(ours) == found,
        note="our helicity rows against MadLoop's configurations"
        + (f" (point {index} of {source})" if source else "")))  # fmt: skip
    for entry in madloop:
        helicity = tuple(entry["helicity"])
        if helicity not in ours:
            continue
        born, laurent = ours[helicity].total()
        text = "h" + "".join("+" if h > 0 else "-" if h < 0 else "0" for h in helicity)
        mine = [born * average, *(x * average for x in laurent)]
        theirs = [entry[k] for k in COEFFICIENTS]
        record = entry.get("reference") or {}
        if record.get("status") == "none":
            # No MadLoop reference for this configuration (MQ-REF's reason).
            checks.append(Check(
                "hel", index, "double-double", text, "no reference", "", "", 0.0,
                0.0, True, asserted=False,
                note=f"MQ-REF: {record.get('reason')}"))  # fmt: skip
            continue
        recorded = record.get("comparison") == "absolute"
        ratio = float(abs(born) / total) if total else 0.0
        if (
            ratio <= VANISHING_HELICITY
            and abs(entry["born"]) <= REFERENCE_TOLERANCE * summed
        ):
            # A vanishing helicity (MadLoop's value is its rounding of a
            # zero): every coefficient against the summed Born, ours included.
            scale_born = total * average
            flux = _flux(scale_born, alpha_s)
            reason = "vanishing helicity" + (
                f" (MQ-REF: {record.get('reason') or 'absolute'})" if recorded else ""
            )
            for k, name in enumerate(COEFFICIENTS):
                scale = float(scale_born) if k == 0 else flux
                error = _absolute(mine[k], theirs[k])
                bound = REFERENCE_TOLERANCE * scale
                strict = relative(mine[k], theirs[k])
                note = (
                    f"{reason}: our double-double Born {ratio:.3g} of the summed "
                    f"Born; against the summed Born (relative {strict:.3g})"
                )
                checks.append(Check("hel", index, "double-double", text, name,
                                    str(mine[k]), repr(theirs[k]), error, bound,
                                    error <= bound, note=note))  # fmt: skip
            continue
        note = f"MadLoop status {entry.get('status')}, accuracy {entry.get('accuracy')}"
        if recorded:
            note += (
                f"; MQ-REF's record compares it absolutely "
                f"({record.get('reason') or 'no reason'}), not honoured: our "
                f"double-double Born is {ratio:.3g} of the summed Born (not a "
                f"vanishing helicity, <= {VANISHING_HELICITY:g})"
            )
        for k, name in enumerate(COEFFICIENTS):
            error = relative(mine[k], theirs[k])
            checks.append(Check("hel", index, "double-double", text, name,
                                str(mine[k]), repr(theirs[k]), error,
                                REFERENCE_TOLERANCE, error <= REFERENCE_TOLERANCE,
                                note=note))  # fmt: skip
    return checks


def helicity_rows(run: RowRun, indices: Sequence[int], points, scales) -> list:
    """Our per-helicity results (double-double, native observables
    ``NativeObservables.resolved``): per point {helicity labels: Evaluated}."""

    from pyamplicol.loops.v2.assemble import Precision
    from pyamplicol.loops.v2.observables import NativeObservables, ObservableSlice

    native = NativeObservables.resolved(ObservableSlice.of(run.slice), "helicity")
    results = native.evaluate(
        points, scales, parameters=run.parameters, precision=Precision.double_double()
    )
    out = []
    for columns in results:
        rows = {}
        for (row, _component), result in columns.items():
            labels = tuple(h for _leg, h in sorted(row))
            rows[labels] = evaluated(result, "double-double")
        out.append(rows)
    return out


# ------------------------------------------------------------------ a row


def reference_record_checks(row: Row, reference: Reference, index: int) -> list[Check]:
    """MQ-REF's record of the point (``Reference.records``): status "none"
    is one not-asserted rule 1 check carrying the reason (no provider
    reference at M-QCD accuracy; rule 1 does not run there, rules 2-4 do);
    an absolute comparison must be the manifest's zero point with the same
    regular neighbour (else the manifest is stale: a failing check)."""

    record = reference.record(index)
    if record is None:
        return []
    checks = []
    if index in reference.binding:
        path, other = reference.binding[index]
        checks.append(Check(
            "1", index, "double-double", "", "binding reference", path,
            f"row {other}", 0.0, 0.0, True, asserted=False,
            note="the existing reference's point is superseded by MQ-REF's "
            "quadruple-precision rerun of it (point_binding): rule 1 holds its "
            "primary values; the existing fixture's other providers stay "
            "second providers"))  # fmt: skip
    outlier = record.get("outlier")
    if outlier:
        # A declared rule 1 outlier (MQ-REF): rule 1 judges it by its
        # conditions (the manifest's reference_outliers listing, the
        # primary's own accuracy and a second provider); the record's ruling
        # and evidence are carried for the report.
        checks.append(Check(
            "1", index, "double-double", "", "declared outlier",
            str(outlier.get("ruling")), "", 0.0, 0.0, True, asserted=False,
            note=f"MQ-REF: {record.get('reason') or ''}; conditions "
            f"{outlier.get('conditions')}"))  # fmt: skip
    status = record.get("status")
    if status == "none":
        checks.append(Check(
            "1", index, "double-double", "", "no reference", "", "", 0.0, 0.0,
            True, asserted=False, note="no provider reference at this point "
            f"(MQ-REF): {record.get('reason')}; rules 2-4 hold it"))  # fmt: skip
    elif status != "ok":
        checks.append(Check(
            "1", index, "double-double", "", "reference record", "", str(status),
            math.inf, 0.0, False, note="unknown reference status"))  # fmt: skip
    if record.get("comparison") == "absolute":
        neighbour = record.get("absolute_scale_row")
        named = row.zero_points.get(index)
        checks.append(Check(
            "1", index, "double-double", "", "reference record", str(named),
            str(neighbour), 0.0, 0.0, named is not None and named == neighbour,
            note="an absolute reference point against its regular neighbour: "
            "the manifest's zero_points must name it"))  # fmt: skip
    return checks


def rule_ward(
    row: Row, index: int, carrier: str, check: Mapping[str, Any]
) -> list[Check]:
    """The ``ward`` extra (O10, ``ward.ward_check`` of one point and
    carrier): per leg and factor c the substituted Born over the physical
    one (``ward.BORN_BOUNDS``) and the virtual's criterion (``ward.ward_row``:
    double-double |V_k| / scale_k <= 1e-25; binary64 the O1 rule's
    |V_k| / max(1e-12 scale_k, E_k) <= 1, E within the binary64 scope and
    |V_k| <= 10 E_k). A binary64 evaluation outside the O1 scope (E_k >
    1e-9 of the scale) is not asserted when the manifest lists it
    (``ward_out_of_scope``; an unlisted one fails, as does a stale listing),
    and its estimate must still bracket |V_k| tenfold (rule 3)."""

    from pyamplicol.loops.v2 import ward

    checks = []
    for entry in check["rows"]:
        label = f"leg {entry['leg']}, c = {complex(*entry['factor'])}"
        checks.append(Check(
            "ward", index, carrier, label, "born", "", "0", entry["born"],
            ward.BORN_BOUNDS[carrier], bool(entry["born_passed"]),
            note="|substituted Born| / |physical Born|"))  # fmt: skip
        virtual = entry["parts"]["virtual"]
        passed, asserted = entry["virtual_passed"] is True, True
        if carrier == "double-double":
            error, bound = max(virtual), ward.VIRTUAL_BOUNDS[carrier]
            note = "max_k |V_k| / scale_k"
        elif entry.get("o1_over") is not None:
            error, bound = max(entry["o1_over"]), 1.0
            bracket = max(entry["estimate_over"])
            listed = _listed(
                row.ward_out_of_scope,
                point=index,
                leg=entry["leg"],
                factor=list(entry["factor"]),
            )
            note = (
                f"max_k |V_k| / max(1e-12 scale_k, E_k); |V_k| / scale_k "
                f"{max(virtual):.3g}; |V_k| / E_k {bracket:.3g} "
                f"(<= {ward.ESTIMATE_FACTOR}); E_k / scale_k "
                f"{max(entry['estimate']):.3g} (in scope: {entry['in_scope']})"
            )
            if not entry["in_scope"]:
                # Outside the binary64 scope: listed, and bracketed tenfold.
                asserted = False
                passed = listed and bracket <= ward.ESTIMATE_FACTOR
                note += "; outside the binary64 scope" + (
                    ", listed" if listed else ", NOT listed"
                )
            elif listed:
                passed = False
                note += "; stale out-of-scope listing"
        else:
            error, bound = max(virtual), math.nan
            note = "no binary64 criterion without the reduction-direction check"
        checks.append(Check(
            "ward", index, carrier, label, "virtual", "", "0", error, bound,
            passed, asserted=asserted, note=note))  # fmt: skip
    return checks


@dataclass
class RowReport:
    row: str
    tier: str
    points: tuple[int, ...]
    checks: list[Check]
    timings: dict[str, float]
    status: str = "active"
    # Informational (no rule): binary64 against the primary provider, the
    # largest strict relative deviation per coefficient over the points.
    binary64_vs_reference: dict[str, float] = field(default_factory=dict)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]

    @property
    def passed(self) -> bool:
        return not self.failures

    def out_of_scope(self) -> list[Check]:
        return [c for c in self.checks if not c.asserted]

    def worst(self, rule: str, carrier: str | None = None) -> float | None:
        errors = [
            c.error
            for c in self.checks
            if c.rule == rule
            and c.asserted
            and (carrier is None or c.carrier == carrier)
            and c.coefficient in COEFFICIENTS
            and math.isfinite(c.error)
        ]
        return max(errors) if errors else None

    def ward_summary(self) -> dict[str, Any] | None:
        found = [c for c in self.checks if c.rule == "ward"]
        if not found:
            return None
        summary: dict[str, Any] = {"checks": len(found)}
        for carrier in ("double", "double-double"):
            for name in ("virtual", "born"):
                errors = [
                    c.error
                    for c in found
                    if c.carrier == carrier and c.coefficient == name
                ]
                if errors:
                    summary[f"{name}_{carrier}"] = max(errors)
        return summary

    def summary(self) -> dict[str, Any]:
        return {
            "row": self.row,
            "tier": self.tier,
            "status": self.status,
            "points": list(self.points),
            "passed": self.passed,
            "checks": len(self.checks),
            "failures": len(self.failures),
            "max_dd_vs_reference": self.worst("1"),
            "max_binary64_vs_dd": self.worst("2"),
            "max_catani_dd": self.worst("4", "double-double"),
            "max_catani_binary64": self.worst("4", "double"),
            "catani_not_formed": any(
                c.rule == "4" and not c.asserted and c.coefficient == "poles"
                for c in self.checks
            ),
            "binary64_vs_reference": self.binary64_vs_reference,
            # The ``ward`` extra: per carrier the worst virtual criterion
            # ratio (double-double |V_k| / scale_k, binary64 the O1 ratio)
            # and the worst Born ratio.
            "ward": self.ward_summary(),
            # Points without a provider reference (MQ-REF's record).
            "no_reference": [
                {"point": c.point, "reason": c.note}
                for c in self.checks
                if c.coefficient == "no reference"
            ],
            "binary64_out_of_scope": [
                {
                    "point": c.point,
                    "sector": c.sector,
                    "coefficient": c.coefficient,
                    "E": c.bound,
                    "true_error": c.error,
                }
                for c in self.out_of_scope()
                if c.rule == "2"
            ],
            "timings": self.timings,
        }

    def describe(self) -> str:
        lines = [
            f"{self.row} ({self.tier}, points {list(self.points)}): "
            f"{len(self.failures)} of {len(self.checks)} checks fail"
        ]
        for c in self.failures:
            lines.append(
                f"  rule {c.rule} point {c.point} {c.carrier} [{c.sector}] "
                f"{c.coefficient}: error {c.error:.3g} > bound {c.bound:.3g} "
                f"(ours {c.value}, reference {c.reference}) {c.note}"
            )
        return "\n".join(lines)

    def record(self) -> dict[str, Any]:
        return {**self.summary(), "check_records": [asdict(c) for c in self.checks]}


def run_row(
    run: RowRun,
    tier: str,
    *,
    points: Sequence[int] | None = None,
) -> RowReport:
    """Every rule of the row at its ``tier`` points (the core rules, plus the
    implemented extras of the nightly tier)."""

    row, reference = run.row, run.reference
    indices = tuple(points if points is not None else row.tier_points(tier))
    timings = {
        "generate_s": round(run.generate_seconds, 2),
        "export_s": round(run.export_seconds, 2),
    }
    checks: list[Check] = []
    if not indices:
        return RowReport(row.id, tier, indices, checks, timings)
    start = time.perf_counter()
    dd = run.evaluate(indices, "double-double")
    timings["double_double_s_per_point"] = round(time.perf_counter() - start, 2) / len(
        indices
    )
    start = time.perf_counter()
    b64 = run.evaluate(indices, "double")
    timings["double_s_per_point"] = round(time.perf_counter() - start, 2) / len(indices)
    info: dict[str, float] = {}
    by_index = {i: d for i, d in zip(indices, dd, strict=True) if d is not None}
    for index, d, b in zip(indices, dd, b64, strict=True):
        if d is None or b is None:
            for carrier, value in (("double-double", d), ("double", b)):
                if value is None:
                    reason = run.failures.get((index, carrier), "")
                    checks.append(Check(
                        "eval", index, carrier, "", "evaluation", "failed", "", 0.0,
                        0.0, False, note=reason))  # fmt: skip
            if d is not None and index not in row.zero_points:
                # The binary64 evaluation failed alone: double-double still
                # meets the reference and Catani's poles.
                recorded = reference_record_checks(row, reference, index)
                checks += recorded
                if not any(c.coefficient == "no reference" for c in recorded):
                    checks += rule1(row, reference, index, d)
                if row.catani != "none":
                    checks += rule4(row, index, d, reference.alpha_s)
            continue
        if index in row.zero_points:
            neighbour = by_index[row.zero_points[index]]
            d.scale_born = b.scale_born = abs(neighbour.total()[0])
            entries = [{"sector": TOTAL, "coefficient": c} for c in COEFFICIENTS]
            entries += [
                {"sector": sector_text(s), "coefficient": c}
                for s in d.virtual
                for c in LAURENT
            ]
            entries += [
                {"sector": sector_text(s), "coefficient": "born"} for s in d.born
            ]
            row = replace(run.row, vanishing=(*run.row.vanishing, *entries))
        else:
            row = run.row
        recorded = reference_record_checks(row, reference, index)
        checks += recorded
        if not any(c.coefficient == "no reference" for c in recorded):
            checks += rule1(row, reference, index, d)
            for check in rule1(row, reference, index, b):
                worst = info.get(check.coefficient, 0.0)
                if check.coefficient in COEFFICIENTS and math.isfinite(check.error):
                    info[check.coefficient] = max(worst, check.error)
        checks += rule2_and_3(row, reference, index, b, d)
        if row.catani == "none":
            checks.append(Check(
                "4", index, "double-double", "", "poles", "", "", 0.0, 0.0, True,
                asserted=False, note="no Catani prediction on the native-input "
                "route (WP3.1 I5c); the poles are held by rule 1"))  # fmt: skip
        else:
            checks += rule4(row, index, d, reference.alpha_s)
            checks += rule4(row, index, b, reference.alpha_s)
    extras = set(row.extras) & IMPLEMENTED_EXTRAS if tier == "nightly" else set()
    extra_points = indices[:1]
    if "uv" in extras:
        start = time.perf_counter()
        uv = run.evaluate(extra_points, "double-double", poles="uv")
        timings["uv_s"] = round(time.perf_counter() - start, 2)
        flavours = run.loop_flavours()
        for index, point in zip(extra_points, uv, strict=True):
            checks += rule5(
                row, index, point, run.legs(), flavours, str(run.parameters["aS"])
            )
    if "hel" in extras:
        # At the first tier point of the helicity reference: the row's own
        # reference, or MQ-REF's per-helicity run of the row
        # (``row.helicity_reference``, its own points).
        start = time.perf_counter()
        madloop = helicity_reference(row)
        hel_points = [i for i in indices if i < len(madloop["rows"])][:1]
        if hel_points:
            source = row.helicity_reference or row.reference["path"]
            data = json.loads((ROOT / source).read_text())
            points = [_strings(data["points"][i]) for i in hel_points]
            scales = [_scale(data["mu_r"][i]) for i in hel_points]
            separate = source != row.reference["path"]
            for index, ours in zip(
                hel_points, helicity_rows(run, hel_points, points, scales), strict=True
            ):
                checks += rule_hel(
                    row, index, ours, madloop["rows"][index], reference.alpha_s,
                    source=source if separate else "",
                )  # fmt: skip
        timings["hel_s"] = round(time.perf_counter() - start, 2)
    if "ap" in extras:
        start = time.perf_counter()
        ap = run.evaluate(extra_points, f"arbitrary-{AP_DIGITS[0]}", stability=False)
        ap60 = run.evaluate(extra_points, f"arbitrary-{AP_DIGITS[1]}", stability=False)
        timings["ap_s"] = round(time.perf_counter() - start, 2)
        for k, index in enumerate(extra_points):
            checks += rule6(row, index, dd[indices.index(index)], ap[k], ap60[k])
    if "ward" in extras:
        start = time.perf_counter()
        for index in extra_points:
            for carrier in ("double", "double-double"):
                checks += rule_ward(row, index, carrier, run.ward(index, carrier))
        timings["ward_s"] = round(time.perf_counter() - start, 2)
    if row.ckm_relation is not None and tier == "nightly":
        start = time.perf_counter()
        twin = run.twin()
        factor = ckm_factor(run.compiled, run.parameters, row.ckm_relation)
        values = twin.evaluate(indices, "double-double", stability=False)
        for index, mine, theirs in zip(indices, dd, values, strict=True):
            if mine is None or theirs is None:
                continue
            checks += rule_ckm(row, index, mine, theirs, factor)
        timings["ckm_s"] = round(time.perf_counter() - start, 2)
    return RowReport(row.id, tier, indices, checks, timings, binary64_vs_reference=info)


class Campaign:
    """Rows of one test module or CLI run: one compiled loop_sm per
    restriction and one ``RowRun`` per row, built on first use."""

    def __init__(self, ufo: Path, native: Any, work: Path, manifest=None):
        self.ufo, self.native, self.work = Path(ufo), native, Path(work)
        self.rows = rows(manifest)
        self._models: dict[str, Any] = {}
        self._runs: dict[str, RowRun] = {}

    def model(self, restriction: str) -> Any:
        if restriction not in self._models:
            self._models[restriction] = compile_restriction(
                self.ufo, restriction, self.work / f"model-{restriction}"
            )
        return self._models[restriction]

    def run(self, name: str) -> RowRun:
        if name not in self._runs:
            row = self.rows[name]
            if not row.active:
                raise ValueError(f"{name} is pending: {row.pending}")
            base = None
            if (
                row.base is not None
                and self.rows[row.base].active
                and not row.subprocess
            ):
                base = self.run(row.base)
            self._runs[name] = RowRun(
                row, self.model(row.restriction), self.native, base=base
            )
        return self._runs[name]

    def report(self, name: str, tier: str, points=None) -> RowReport:
        run = self.run(name)
        return run_row(run, tier, points=points)


def multiparticle_subprocesses(campaign: Campaign, name: str) -> list[Check]:
    """A multiparticle row's concrete processes (the public route's expansion,
    ``processes.model.expand_model_processes`` with the model's conserved
    charges) against MadLoop's SubProcesses/P* process lists (manifest
    ``madloop_subprocesses``), each process as a multiset of initial and of
    final particles (side permutations are one matrix element)."""

    from pyamplicol.processes.conservation import conserved_charges
    from pyamplicol.processes.model import (
        ModelParticleCatalog,
        expand_model_processes,
    )

    row = campaign.rows[name]
    data = next(r for r in load_manifest()["rows"] if r["id"] == name)
    ir = campaign.model(row.restriction).ir
    catalog = ModelParticleCatalog(ir.name, ir.particles, ir.parameters)
    ours = expand_model_processes(row.process, catalog, charges=conserved_charges(ir))

    def key(process: str) -> tuple:
        """Initial and final PDG multisets (the model's own spelling of a
        name is case-insensitive: loop_sm's gluon is ``G``)."""

        initial, final = process.split(">")
        return tuple(
            tuple(sorted(int(catalog.resolve(n).pdg_code) for n in side.split()))
            for side in (initial, final)
        )

    theirs = {
        key(process)
        for processes in data["madloop_subprocesses"].values()
        for process in processes
    }
    found = {key(process) for process in ours}
    return [
        Check("multi", None, "", "", "subprocesses", ", ".join(sorted(ours)),
              ", ".join(sorted(p for ps in data["madloop_subprocesses"].values()
                               for p in ps)),
              0.0, 0.0, found == theirs,
              note=f"{len(found)} processes against MadLoop's "
              f"{len(data['madloop_subprocesses'])} P directories")
    ]  # fmt: skip


SMOKE_TOLERANCE = 1e-14


def smoke(campaign: Campaign, restriction: str, spec: Mapping[str, Any]) -> list[Check]:
    """A generation smoke (PLAN §3.2 MQ-VALIDATE item 5): the request of row
    ``spec['row']`` generated on ``restriction`` equals the row on its own
    restriction, binary64, at the first point of ``spec.get('points_from',
    row)``'s reference, within 1e-14 strictly relative per sector and
    coefficient (Born included)."""

    from pyamplicol.loops.v2.assemble import LoopSlice, Precision

    row = campaign.rows[spec["row"]]
    source = campaign.rows[spec.get("points_from", row.id)]
    reference = load_reference(source)
    parameters = {**reference.parameters, **dict(source.parameters)}
    values = []
    for name in (row.restriction, restriction):
        slice_ = LoopSlice.generate(
            campaign.model(name), slice_request(row), campaign.native
        )
        values.append(
            evaluated(
                slice_.evaluate(
                    reference.points[0],
                    reference.scales[0],
                    parameters=parameters,
                    precision=Precision.double(),
                ),
                "double",
            )
        )
    base, other = values
    same = set(other.virtual) == set(base.virtual) and set(other.born) == set(base.born)
    checks = [
        Check("smoke", 0, "double", "", "sectors",
              ", ".join(map(sector_text, sorted(other.virtual))),
              ", ".join(map(sector_text, sorted(base.virtual))), 0.0, 0.0,
              same, note=f"{restriction} against {row.restriction}")
    ]  # fmt: skip
    for sector, value in base.born.items():
        error = relative(other.born.get(sector, Decimal(0)), value)
        checks.append(Check("smoke", 0, "double", sector_text(sector), "born",
                            str(other.born.get(sector)), str(value), error,
                            SMOKE_TOLERANCE, error <= SMOKE_TOLERANCE))  # fmt: skip
    for sector, laurent in base.virtual.items():
        mine = other.virtual.get(sector, (Decimal(0),) * 3)
        for k, name in enumerate(LAURENT):
            error = relative(mine[k], laurent[k])
            checks.append(Check("smoke", 0, "double", sector_text(sector), name,
                                str(mine[k]), str(laurent[k]), error,
                                SMOKE_TOLERANCE, error <= SMOKE_TOLERANCE))  # fmt: skip
    return checks


def write_result(report: RowReport, directory: str | os.PathLike | None = None) -> None:
    """Write the row's record to ``$PYAMPLICOL_MQCD_RESULTS/<row>.<tier>.json``
    when that directory is set (report data, ``build_mqcd.py``)."""

    directory = directory or os.environ.get(RESULTS_ENVIRONMENT)
    if not directory:
        return
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{report.row}.{report.tier}.json").write_text(
        json.dumps(report.record(), indent=1, default=str) + "\n"
    )


# ---------------------------------------------------------------------- CLI


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.loop_benchmark.mqcd")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run campaign rows outside pytest")
    run.add_argument("rows", nargs="+")
    run.add_argument("--tier", choices=TIERS, default="default")
    run.add_argument("--points", type=int, nargs="*")
    run.add_argument("--ufo", required=True, type=Path)
    run.add_argument("--work", required=True, type=Path)
    run.add_argument("--results", type=Path)
    run.add_argument(
        "--manifest", type=Path, default=MANIFEST, help="another manifest file"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(format="%(asctime)s %(message)s", level=logging.WARNING)
    LOG.setLevel(logging.INFO)

    from pyamplicol.loops.native import load_loop_native

    campaign = Campaign(
        args.ufo, load_loop_native(), args.work, manifest=load_manifest(args.manifest)
    )
    failed = 0
    for name in args.rows:
        row = campaign.rows[name]
        if not row.active:
            print(f"{name}: pending ({row.pending})", flush=True)
            continue
        report = campaign.report(name, args.tier, points=args.points)
        print(report.describe(), flush=True)
        print(json.dumps(report.summary(), default=str), flush=True)
        write_result(report, args.results)
        failed += not report.passed
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
