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
   rel <= 1e-12 per sector and coefficient, Born included; a listed reference
   outlier passes only if the provider's own accuracy covers the difference
   and a second provider agrees with double-double within 1e-12;
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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
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

REFERENCE_TOLERANCE = 1e-12  # rule 1
O1_STRICT = 1e-12  # rule 2: E <= 1e-12
O1_CAP = 1e-9  # rule 2: E above it is outside the binary64 scope
BRACKET = 10  # rule 3 (and the 10 E bounds of rules 4-6)
DD_FLOOR = 1e-24  # rules 4-6
AP_CONVERGENCE = 1e-35  # rule 6
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
IMPLEMENTED_EXTRAS = frozenset({"ap", "uv"})


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
    # Rule 4's prediction: "python" (the Python-input path's Catani operator,
    # every row on that route) or "none" for a row on the native-input route,
    # which forms no prediction (WP3.1 I5c): rule 4 is then recorded as not
    # asserted (the manifest names the gap), its poles held by rule 1 only.
    catani: str = "python"
    variants: tuple[Mapping[str, Any], ...] = ()

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
            catani=data.get("catani", "python"),
            gating=bool(data.get("gating", True)),
            variants=tuple(data.get("variants", ())),
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

    @property
    def primary(self) -> str:
        return self.providers[0]


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
    return reference


def _required(row, spec, data) -> Reference:
    """A required-format fixture (``tools/loop_reference``): every provider's
    totals per point; where a row carries MadLoop's squared split orders
    (``rows[i].sectors``, MQ-REF item 4) the primary provider's Born and
    Laurent coefficients per sector, with MadLoop's own accuracy per loop
    sector."""

    providers = tuple(spec.get("providers") or data["rows"][0]["providers"])
    born, virtual, accuracy = [], [], []
    for entry in data["rows"]:
        b, v, a = {}, {}, {}
        for name in providers:
            values = entry["providers"][name]
            b[name] = {TOTAL: float(values["born"])}
            v[name] = {TOTAL: _laurent(values)}
            a[name] = values.get("accuracy", values.get("estimated_relative_accuracy"))
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


_LOADERS = {
    "required": _required,
    "providers": _providers,
    "component-control": _component_control,
    "model-control": _model_control,
    "dilepton": _dilepton,
    "mixed-sm": _mixed_sm,
    "mqcd": _mqcd,
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
        self.reference = load_reference(row)
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
        results = self.executor.evaluate(
            [reference.points[i] for i in indices],
            [reference.scales[i] for i in indices],
            parameters=self.parameters,
            precision=precision,
            poles=poles,
            stability=check_configuration() if stability else None,
        )
        seconds = (time.perf_counter() - start) / max(1, len(indices))
        LOG.info("%s: %s done, %.1f s per point", self.row.id, carrier, seconds)
        return [evaluated(r, carrier, seconds) for r in results]

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
                    REFERENCE_TOLERANCE,
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
    listed = _listed(
        row.reference_outliers, point=index, sector=sector, coefficient=name
    )
    if error <= REFERENCE_TOLERANCE:
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
            REFERENCE_TOLERANCE,
            not listed,
            note=note,
        )
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
            REFERENCE_TOLERANCE,
            False,
            note=f"against {primary}; not a listed outlier",
        )
    accuracy = _accuracy(reference, index, primary, sector, name)
    seconds = {
        p: relative(mine, other(p)) for p in providers[1:] if other(p) is not None
    }
    covered = accuracy is not None and accuracy >= error
    agreeing = [p for p, e in seconds.items() if e <= REFERENCE_TOLERANCE]
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
        REFERENCE_TOLERANCE,
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


# ------------------------------------------------------------------ a row


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
    for index, d, b in zip(indices, dd, b64, strict=True):
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
    if "ap" in extras:
        start = time.perf_counter()
        ap = run.evaluate(extra_points, f"arbitrary-{AP_DIGITS[0]}", stability=False)
        ap60 = run.evaluate(extra_points, f"arbitrary-{AP_DIGITS[1]}", stability=False)
        timings["ap_s"] = round(time.perf_counter() - start, 2)
        for k, index in enumerate(extra_points):
            checks += rule6(row, index, dd[indices.index(index)], ap[k], ap60[k])
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
            if row.base is not None and self.rows[row.base].active:
                base = self.run(row.base)
            self._runs[name] = RowRun(
                row, self.model(row.restriction), self.native, base=base
            )
        return self._runs[name]

    def report(self, name: str, tier: str, points=None) -> RowReport:
        run = self.run(name)
        return run_row(run, tier, points=points)


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
    args = parser.parse_args(argv)
    logging.basicConfig(format="%(asctime)s %(message)s", level=logging.WARNING)
    LOG.setLevel(logging.INFO)

    from pyamplicol.loops.native import load_loop_native

    campaign = Campaign(args.ufo, load_loop_native(), args.work)
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
