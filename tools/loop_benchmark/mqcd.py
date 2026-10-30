# SPDX-License-Identifier: 0BSD
"""The M-QCD validation campaign: manifest, references, evaluation and the
acceptance rules of ``m-qcd/PLAN.md`` §1.4.

The manifest (``tests/fixtures/loop/mqcd/manifest.json``) holds one record
per campaign row (PLAN §4.2): the request (process, restriction, fixed
parameters, gauge, Born and loop orders, vetoes), its reference, the points
per tier, the expected predicted and unpredicted pole sectors, the extras and
the structural features it covers, the listings the rules require (named
reference outliers, coefficients that vanish identically) and the row's
relaxed tolerances (``relaxed``).

The rules (PLAN §1.4). The user's ruling of 2026-10-29 ~10:20 overrides
their tolerances: a discrepancy below ~1e-5 relative is not a finding, a
check failing at that level gets its row's tolerance relaxed (``relaxed``:
rule -> tolerance, stated per row, at most ``ATTENTION``) and passing
checks keep their tolerances; no exemption lists. Rule 4 holds two carriers:
its ``"4"`` relaxes the binary64 checks and ``"4dd"`` the double-double
ones, each only the carrier that needed it:

1. double-double against the row's primary provider, strictly relative,
   rel <= the row's ``reference_tolerance`` per sector and coefficient, Born
   included: 1e-12, relaxed per row to 1e-10 from 2->4 up (and up to 1e-7 at
   2->5 and beyond) only where the providers' own precision requires it (the
   user's ruling of 2026-10-29 ~01:12, stated per row); a listed reference
   outlier passes only if the provider's own accuracy covers the difference
   and a second provider agrees with double-double within the same
   tolerance; a coefficient that vanishes identically stays absolute at
   1e-12 F_s;
2. binary64 against our own double-double at the same point (the user's O1
   rule): E <= 1e-12 -> 1e-12, 1e-12 < E <= 1e-9 -> E, E > 1e-9 outside the
   binary64 scope: reported with E and the true error, not asserted (rule 3
   still holds it); the Born (no estimate) is held to 1e-12;
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
7. (``nc``) LC/NLC projections: MQ-NC's test ids of the row (manifest
   ``delegated.nc``: the formal projection against the N_c scan within 1e-24
   in double-double, then the row's independent N_c oracles), run by MQ-NC's
   test files, not repeated here; ``build_mqcd.py --junit`` reads their
   outcomes. Until MQ-NC lands the extra is pending (``extras_pending``).

A row's ``delegated`` columns name other packages' pytest ids that hold part
of it (``nc``; M01's ``bitwise``: MQ-MODEL's test that each subprocess of the
public route's multiparticle artifact is bitwise its own single-process
generation). A ``composite`` row (M01) has no evaluation of its own: its
gating variants (each subprocess's single-process generation, and on the
public route the multiparticle artifact's subprocess, ``route: public``,
against MadLoop's P references), its expansion check and its delegated
columns make it up.

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

E is the stability estimate of the recommended checks, the O1 rule's
estimate (``loops.v2.stability.RECOMMENDED_CHECKS``, MQ-STAB: one generic
exact rotation plus the rescaled reduction check; the earlier beam-axis
rotation with the cached check missed errors by up to 100x, finding F6).
A coefficient that vanishes identically (manifest ``vanishing``) is checked
absolutely, |a - r| <= 1e-12 F_s with F_s = |B_s| alpha_s / 2 pi.

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
from collections.abc import Callable, Iterable, Mapping, Sequence
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

REFERENCE_TOLERANCE = 1e-12  # rule 1 (and the absolute checks)
# Rule 1 of a 2->4+ row whose providers' precision needs it (user,
# slice-status DECISIONS 2026-10-29 ~01:12, "if need be"); 2->5 and beyond
# may go up to the ceiling (the manifest states each row's tolerance).
REFERENCE_TOLERANCE_HIGH = 1e-10
REFERENCE_TOLERANCE_CEILING = 1e-7
# The user's attention threshold (slice-status DECISIONS 2026-10-29 ~10:20:
# "only really bad cases (worse than around 1e-5 of relative prec or so
# require attention)"): the ceiling of a row's ``relaxed`` tolerances.
ATTENTION = 1e-5
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

# ``campaign``: rows run by the campaign CLI only (m-sm/PLAN.md §4.3: the
# 2->5 target and CM07, jobs above the nightly budget).
TIERS = ("default", "nightly", "campaign")
# ``composite``: a row made of its gating variants, checks and delegated
# columns, without an evaluation of its own (M01).
STATUSES = ("active", "pending", "composite")
# The routes a row's generation takes: the tools route (``LoopSlice``, the
# native executor) or the public route (``Generator`` / ``Runtime`` on the
# shipped loop_sm; M01's multiparticle artifact).
ROUTES = ("tools", "public")
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
EXTRAS = ("nc", "ap", "ward", "uv", "hel", "sp", "ff", "joint")
# Extras this harness checks today (the others are listed as pending).
# ``sp`` (PLAN §4.1 special points S1-S4) is checked by the row's gating
# variants (``<id>@<name>``: the special-point references on the base row's
# generation), so a row with ``sp`` and no gating variant is malformed.
# ``ff`` is the analytic quark form factor (PLAN §4.2 D01, ``rule_ff``).
IMPLEMENTED_EXTRAS = frozenset({"ap", "uv", "hel", "sp", "ward", "ff", "joint"})
# Extras another package's tests check, by the test ids the row lists
# (``nc``: MQ-NC's rule 7 column, ``Row.nc_column``).
DELEGATED_EXTRAS = frozenset({"nc"})


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
    reference_outliers: tuple[Mapping[str, Any], ...] = ()
    vanishing: tuple[Mapping[str, Any], ...] = ()
    # Reference fixed parameters the model does not have (MadLoop's WTau).
    ignored_fixed_parameters: tuple[str, ...] = ()
    # Reference parameters the row's model does not take (a reference of
    # another UFO: loop_sm's aEWM1 under the G_mu UFO, whose effect the row
    # states through its own ``parameters``, e.g. the derived MW).
    ignored_parameters: tuple[str, ...] = ()
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
    # every row on that route), "engine" (a native-input row: the engine's
    # operators on the Python-input Born, ``RowRun.engine_catani``, the M-SM
    # rows), "tree" (a row on the native-input route,
    # whose executor forms none, WP3.1 I5c: the harness's massless Catani
    # operator on the tree engine's colour-correlated Born, ``tree_catani``)
    # or "none" (recorded as not asserted: M01's public-route variants, whose
    # tools-route twins hold rule 4, and a native-input row without the tree
    # engine's committed correlations, reported "partial").
    catani: str = "python"
    # The committed tree-engine colour correlations of a "tree" row
    # (``tools/loop_benchmark/mqcd_tree_correlations.py``), or None (the
    # tree engine runs in the harness).
    tree_correlations: str | None = None
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
    # Runtime parameters of the ``ward`` extra only (on the row's points):
    # in the real-mass scheme the Ward identity holds only where no external
    # coloured (gluon Ward) or charged (photon Ward) particle has an
    # absorptive self-energy at its mass, which the scheme's real on-shell
    # counterterms leave unrenormalised; e.g. a stable top (MW, MZ above MT)
    # for the top-pair rows, whose W and Z are internal.
    ward_parameters: Mapping[str, str] = field(default_factory=dict)
    # Rule -> tolerance of the checks the user's ruling of 2026-10-29 ~10:20
    # relaxes on this row ("2": rule 2's binary64 bound, at least this; "6":
    # rule 6's 40 against 60 digits), at most ``ATTENTION``.
    relaxed: Mapping[str, float] = field(default_factory=dict)
    # Rule 1's relative tolerance (``REFERENCE_TOLERANCE``; a 2->4+ row whose
    # providers need it ``REFERENCE_TOLERANCE_HIGH``; the manifest states it).
    reference_tolerance: float = REFERENCE_TOLERANCE
    # Other packages' pytest node ids per column (rule 7's ``nc``: MQ-NC's;
    # M01's ``bitwise``: MQ-MODEL's).
    delegated: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    route: str = "tools"
    # The row's model (a key of the campaign's ``ufos``: loop_sm, or an EW
    # UFO of the M-SM manifest, m-sm/PLAN.md §4.1 model codes), its
    # structural source-compatibility profile and scale parameter
    # (``SliceRequest.compatibility`` / ``scale_parameter``).
    model: str = "loop_sm"
    compatibility: str | None = None
    scale_parameter: str | None = None
    # The loop coupling alpha of each correction other than the strong one
    # (QED: the scheme's alpha_Gmu or alpha(M_Z)), for F_s (m-sm/PLAN.md
    # §1.4: F_s = |B_s| alpha_c / 2 pi, the largest over the corrections
    # reaching s); the strong one is the reference's aS.
    alphas: Mapping[str, float] = field(default_factory=dict)
    # Rule 4's typed reasons (sector text -> ``poles.UNPREDICTED_REASONS``
    # entry) of the unpredicted sectors, asserted to be the slice's
    # (``LoopSlice.unpredicted_sectors``); None: the sets only (M-QCD).
    unpredicted_reasons: Mapping[str, str] | None = None
    # The R2 rule (m-sm/PLAN.md §1.4 rule 1, Q7): the UFO R2 couplings the
    # engine's counterterm program inserts and MadLoop's export does not
    # call (its label matching), as the row's reference records them; the
    # harness checks that the engine inserts them (``rule_r2``).
    madloop_omitted_r2: tuple[str, ...] | None = None
    # The UFO R2 couplings the MadLoop export of the row's reference calls
    # (MS-REF's ``madloop_r2_couplings``), for the structural difference
    # with the engine's (``rule_r2``); None where the reference lists none.
    madloop_r2_called: tuple[str, ...] | None = None
    # R2 couplings the engine inserts in the export's sectors whose
    # contribution vanishes there (colour: a colour-octet tree against the
    # singlet Born, which the colour-blind reachability keeps), so MadLoop
    # calls none of them; listed with the reason, they are no omission
    # (``rule_r2``).
    r2_vanishing: tuple[str, ...] = ()
    # [U2]: the request lowers a Levi-Civita cell its veto keeps from
    # cancelling (``SliceRequest.allow_anomalous_veto``; SC05's d s b veto).
    allow_anomalous_veto: bool = False
    # The request's ``loop.external_photons`` (``SliceRequest.external_
    # photons``: "final", "all", "none" or 1-based leg labels, MG5_aMC's
    # ``!a!`` tags); None: the engine's default ("final").
    external_photons: str | tuple[int, ...] | None = None
    # The mass scheme (None: the model's real on-shell masses; "complex-
    # mass": MS-CMS's port of MG5_aMC's transform, ``model_cms.complex_mass_
    # model``, deciding the pole masses at the row's fixed parameters, else
    # the restriction card) and the transform's reglog convention (None:
    # "ufo-standard"; "source": the G_mu source's override, CM01's
    # compatibility view).
    mass_scheme: str | None = None
    reglog_convention: str | None = None
    # Extras run as diagnostics: recorded, not asserted (the ``ward`` extra
    # under the complex-mass scheme, m-sm/PLAN.md §1.4 Ward and §1.5).
    diagnostic_extras: tuple[str, ...] = ()
    # Why a row forms no rule 4 (``catani`` "none"), when not the public
    # route's reason.
    catani_reason: str = ""

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
            reference_outliers=tuple(data.get("reference_outliers", ())),
            vanishing=tuple(data.get("vanishing", ())),
            ignored_fixed_parameters=tuple(data.get("ignored_fixed_parameters", ())),
            ignored_parameters=tuple(data.get("ignored_parameters", ())),
            notes=data.get("notes", ""),
            base=data.get("base"),
            subprocess=bool(data.get("subprocess", False)),
            zero_points={
                int(k): int(v) for k, v in data.get("zero_points", {}).items()
            },
            catani=data.get("catani", "python"),
            tree_correlations=data.get("tree_correlations"),
            helicity_reference=data.get("helicity_reference"),
            gating=bool(data.get("gating", True)),
            variants=tuple(data.get("variants", ())),
            ckm_relation=data.get("ckm_relation"),
            ward_legs=None
            if data.get("ward_legs") is None
            else tuple(int(x) for x in data["ward_legs"]),
            ward_parameters=dict(data.get("ward_parameters") or {}),
            relaxed={k: float(v) for k, v in (data.get("relaxed") or {}).items()},
            reference_tolerance=float(
                data.get("reference_tolerance", REFERENCE_TOLERANCE)
            ),
            delegated={k: tuple(v) for k, v in (data.get("delegated") or {}).items()},
            route=data.get("route", "tools"),
            model=data.get("model", "loop_sm"),
            compatibility=data.get("compatibility"),
            scale_parameter=data.get("scale_parameter"),
            alphas={k: float(v) for k, v in (data.get("alphas") or {}).items()},
            unpredicted_reasons=None
            if data.get("unpredicted_reasons") is None
            else dict(data["unpredicted_reasons"]),
            madloop_omitted_r2=None
            if data.get("madloop_omitted_r2") is None
            else tuple(data["madloop_omitted_r2"]),
            madloop_r2_called=None
            if data.get("madloop_r2_called") is None
            else tuple(data["madloop_r2_called"]),
            r2_vanishing=tuple(data.get("r2_vanishing") or ()),
            allow_anomalous_veto=bool(data.get("allow_anomalous_veto", False)),
            external_photons=data.get("external_photons")
            if not isinstance(data.get("external_photons"), list)
            else tuple(int(x) for x in data["external_photons"]),
            mass_scheme=data.get("mass_scheme"),
            reglog_convention=data.get("reglog_convention"),
            diagnostic_extras=tuple(data.get("diagnostic_extras", ())),
            catani_reason=data.get("catani_reason", ""),
        )

    @property
    def active(self) -> bool:
        return self.status == "active"

    @property
    def nc_column(self) -> tuple[str, ...]:
        """Rule 7's column: MQ-NC's test ids of the row."""
        return self.delegated.get("nc", ())

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
                # Delegated columns are the base row's (their ids name it).
                "delegated": {},
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
        and row.tier != "campaign"
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
    # Per point, the primary provider's instrumented components (MadLoop's
    # Born x CT interference split, ``madloop_ct_selection.py``) in the
    # engine's names: ``bare``, ``r2``, ``uv`` (UV counterterms, field
    # factors included) and ``ct`` (r2 + uv), each {sector or TOTAL:
    # Laurent}; empty where the reference has none (rule 5's EW form).
    components: list[dict[str, dict[Any, tuple[float, float, float]]]] = field(
        default_factory=list
    )

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
    # A ``sectors`` reference names its parts' fixtures instead of one path.
    source = spec.get("path") or spec["parts"][0]["path"]
    data = json.loads((ROOT / source).read_text())
    kind = spec["format"]
    loader = _LOADERS[kind]
    reference = loader(row, spec, data)
    reference.source = source
    if "providers" in spec:
        missing = set(spec["providers"]) - set(reference.providers)
        if missing:
            raise ValueError(f"{row.id}: reference lacks providers {sorted(missing)}")
        reference.providers = tuple(spec["providers"])
    for index, binding in sorted((spec.get("superseded") or {}).items()):
        _supersede(row, reference, int(index), binding["path"], int(binding["row"]))
    if spec.get("photon_conversion"):
        _photon_conversion(reference, spec["photon_conversion"], data)
    return reference


def _photon_conversion(
    reference: Reference, spec: Mapping[str, Any], data: Mapping[str, Any]
) -> None:
    """MG5_aMC's alpha(0) conversion of raw MadLoop G_mu values over the
    tagged photon legs (m-sm/PLAN.md §4.1 photon rows;
    ``export_fks.write_rescale_a0gmu_file``, as ``test_loop_v2_external_
    photons``): with r = (alpha(0) / alpha)^n for n tagged photons, the Born
    and the virtual times r and the virtual of the electromagnetic correction
    minus 2 n DGmua0 Born, DGmua0 the UFO's conversion parameter
    (``spec['counterterm']``) as MadLoop evaluates it at the card's MU_R
    (``spec['parameters']``, ``madloop-ct-parameters.json``), applied to
    every provider's values of the sector it corrects (``spec['sector']``,
    or the single sector)."""

    tagged = int(spec["tagged"])
    if spec.get("values") is not None:
        # The conversion parameter per point (its finite part depends on
        # MU_R), from the UFO's own source at each point's scale
        # (``msm_manifest.conversion_values``): [pole, finite] per point.
        if len(spec["values"]) != len(reference.points):
            raise ValueError(f"{reference.source}: one conversion value per point")
        per_point = [(float(p), float(f)) for p, f in spec["values"]]
    else:
        values = json.loads((ROOT / spec["parameters"]).read_text())["models"][
            spec["model"]
        ]
        card_scale = _scale(values["card"]["MU_R"])
        if any(scale != card_scale for scale in reference.scales):
            raise ValueError(
                f"{reference.source}: the conversion needs MU_R = the card's"
            )
        delta = values["values"][spec["counterterm"]]
        per_point = [tuple(float(delta[k]["double"][0]) for k in ("-1", "0"))] * len(
            reference.points
        )
    alpha = float(Fraction(data["derived_parameters"]["alpha"]))
    ratio = (1 / float(spec["alpha0_inverse"]) / alpha) ** tagged
    corrected = sector_key(spec["sector"]) if spec.get("sector") else None
    for index in range(len(reference.points)):
        pole, finite = per_point[index]
        for provider in reference.providers:
            born = reference.born[index][provider]
            total = sum(born.values())
            for key in born:
                born[key] *= ratio
            virtual = reference.virtual[index][provider]
            for key, (fin, single, double) in list(virtual.items()):
                if corrected is None or key in (corrected, TOTAL):
                    fin -= 2 * tagged * finite * total
                    single -= 2 * tagged * pole * total
                virtual[key] = (ratio * fin, ratio * single, ratio * double)


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
        if spec.get("sector"):
            # One squared sector of a request with several (m-sm/PLAN.md
            # §4.2 TV07): every provider's totals are that sector's values.
            sector = sector_key(spec["sector"])
            born_key = sector_key(spec["born_sector"])
            text = sector_text(sector)
            for name in providers:
                if TOTAL in b[name]:
                    b[name] = {born_key: b[name][TOTAL]}
                if TOTAL in v[name]:
                    v[name] = {sector: v[name][TOTAL]}
                    if not isinstance(a.get(name), Mapping):
                        a[name] = {text: a.get(name)}
        born.append(b)
        virtual.append(v)
        accuracy.append(a)
    # A runtime parameter change of the run (``parameter_overrides``, the
    # S4 rows: e.g. MB = 4.5 and aS = 0.13 on top of the card).
    parameters = {**data["parameters"], **data.get("parameter_overrides", {})}
    components = (
        _run_components(spec["components"], len(data["rows"]))
        if spec.get("components")
        else []
    )
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
        components=components,
    )


def _split_order_key(text: str) -> Sector:
    """``"QCD^2=4,QED^2=2"`` (MS-REF's squared split order) -> sector key."""

    return sector_key(
        {
            name.split("^")[0]: int(power)
            for name, power in (item.split("=") for item in text.split(","))
        }
    )


def _run_components(path: str, count: int) -> list[dict[str, dict]]:
    """MS-REF's instrumented components of a run (``madloop_components.py``:
    per loop squared split order and point MadLoop's Born x CT interference
    split into ``r2``, ``uv``, ``rest`` and ``ct`` = their sum, and ``bare``
    = the quadruple-precision sector value - ``ct``), in the engine's names
    per sector: ``bare``, ``r2``, ``uv`` (+ ``rest``, CT amplitudes that pass
    neither an R2 nor a UV coupling) and ``ct``."""

    data = json.loads((ROOT / path).read_text())
    out: list[dict[str, dict]] = [{} for _ in range(count)]
    for text, entry in data["sectors"].items():
        sector = _split_order_key(text)
        if len(entry["rows"]) != count:
            raise ValueError(f"{path}: {text} has {len(entry['rows'])} rows")
        for index, values in enumerate(entry["rows"]):
            uv = tuple(
                a + b
                for a, b in zip(
                    _laurent(values["uv"]), _laurent(values["rest"]), strict=True
                )
            )
            for name, laurent in (
                ("bare", _laurent(values["bare"])),
                ("r2", _laurent(values["r2"])),
                ("uv", uv),
                ("ct", _laurent(values["ct"])),
            ):
                out[index].setdefault(name, {})[sector] = laurent
    return out


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


def _ew_control(row, spec, data) -> Reference:
    """A MadLoop electroweak control (``electroweak-*-control.json``): per
    row the Born and the full virtual of its one squared-order sector ("1"),
    MadLoop's accuracy and its instrumented components; the points the
    control's ``exact_points`` or those of the manifest's ``points_path``
    (the controls' phase-space fixture), cycled over the rows; the scales
    the control's ``mu_r2``, each row's or the manifest's ``mu_r2``; the
    parameters the manifest's (the control states them in words)."""

    if data.get("exact_points"):
        points = data["exact_points"]
    else:
        points = json.loads((ROOT / spec["points_path"]).read_text())["points"]
    points = [_strings(p) for p in points]
    entries = data["rows"]
    scales = data.get("mu_r2") or [e.get("mu_r2") or spec["mu_r2"] for e in entries]
    born = [{"madloop": {TOTAL: float(e["born"]["1"])}} for e in entries]
    virtual = [{"madloop": {TOTAL: _laurent(e["full"]["1"])}} for e in entries]
    accuracy = [{"madloop": e.get("accuracy")} for e in entries]
    names = (("bare", "bare"), ("r2", "r2"), ("uv", "uv"), ("ct", "ct"))
    components = [
        {ours: {TOTAL: _laurent(e[key]["1"])} for ours, key in names if key in e}
        for e in entries
    ]
    parameters = dict(spec["parameters"])
    return Reference(
        "",
        ("madloop",),
        [points[i % len(points)] for i in range(len(entries))],
        [str(scale) for scale in scales],
        parameters,
        None,
        born,
        virtual,
        accuracy,
        float(parameters["aS"]),
        components=components,
    )


def _cms_control(row, spec, data) -> Reference:
    """A MadLoop complex-mass control (``cms-*-gmu.json``, CM01): block
    ``spec['block']`` of the fixture (its points, Born, full virtual and
    the instrumented bare / UV / R2 components, one squared-order sector);
    the scale the manifest's ``mu_r2``; the parameters the manifest's plus
    the block's widths (or the manifest's ``widths``), runtime parameters
    of the row's one complex-mass generation."""

    block = data[spec["block"]]

    def laurent(values) -> tuple[float, float, float]:
        # (finite, single pole, double pole), as LAURENT.
        return tuple(float(x) for x in values)

    widths = block.get("widths") or spec["widths"]
    parameters = {**spec["parameters"], **widths}
    count = len(block["points"])
    names = ("bare", "uv", "r2")
    components = [
        {name: {TOTAL: laurent(block[name][k])} for name in names if name in block}
        for k in range(count)
    ]
    return Reference(
        "",
        ("madloop",),
        [_strings(p) for p in block["points"]],
        [str(spec["mu_r2"])] * count,
        parameters,
        None,
        [{"madloop": {TOTAL: float(block["born"][k])}} for k in range(count)],
        [{"madloop": {TOTAL: laurent(block["full"][k])}} for k in range(count)],
        [{"madloop": None} for _ in range(count)],
        float(parameters["aS"]),
        components=components,
    )


def _madloop_components(row, spec, data) -> Reference:
    """``goldstone-mixing.json`` style: ``processes[key]`` with MadLoop's
    Born, virtual (its accuracy) and its Born x CT interference ``ct`` and
    ``r2`` per point. With ``spec['omitted_r2']`` the R2 rule's correction
    (m-sm/PLAN.md §1.4 rule 1): MadLoop's export omits an R2 coupling whose
    vertex term is proportional to one it calls (its label matching), so
    ``ratio`` x that coupling's component (``component``) is added to the
    virtual, the R2 and the counterterm components."""

    entry = data["processes"][spec["key"]]
    omitted = spec.get("omitted_r2")
    born, virtual, accuracy, components = [], [], [], []
    for e in entry["rows"]:
        extra = (0.0, 0.0, 0.0)
        if omitted:
            ratio = float(Fraction(omitted["ratio"]))
            extra = tuple(ratio * x for x in _laurent(e[omitted["component"]]))
        full, ct, r2 = _laurent(e["virtual"]), _laurent(e["ct"]), _laurent(e["r2"])
        born.append({"madloop": {TOTAL: float(e["born"])}})
        virtual.append(
            {"madloop": {TOTAL: tuple(a + b for a, b in zip(full, extra, strict=True))}}
        )
        accuracy.append({"madloop": e.get("virtual_accuracy")})
        components.append(
            {
                "bare": {TOTAL: tuple(a - b for a, b in zip(full, ct, strict=True))},
                "r2": {TOTAL: tuple(a + b for a, b in zip(r2, extra, strict=True))},
                "uv": {TOTAL: tuple(a - b for a, b in zip(ct, r2, strict=True))},
                "ct": {TOTAL: tuple(a + b for a, b in zip(ct, extra, strict=True))},
            }
        )
    parameters = dict(entry["parameters"])
    return Reference(
        "",
        ("madloop",),
        [_strings(p) for p in entry["points"]],
        [_scale(mu) for mu in entry["mu_r"]],
        parameters,
        dict(entry.get("fixed_parameters", {})),
        born,
        virtual,
        accuracy,
        float(parameters["aS"]),
        components=components,
    )


def _process_components(row, spec, data) -> Reference:
    """``epsilon-sign.json`` style: ``rows[key]`` with MadLoop's Born, status,
    accuracy and its components (``full``, ``bare``, ``r2``, ``uv``) at the
    fixture's points, scales and parameters."""

    entries = data["rows"][spec["key"]]
    born = [{"madloop": {TOTAL: float(e["born"])}} for e in entries]
    virtual = [{"madloop": {TOTAL: _laurent(e["components"]["full"])}} for e in entries]
    accuracy = [{"madloop": e.get("madloop_accuracy")} for e in entries]
    components = []
    for e in entries:
        found = {
            name: {TOTAL: _laurent(e["components"][name])}
            for name in ("bare", "r2", "uv")
            if name in e["components"]
        }
        if {"r2", "uv"} <= set(found):
            found["ct"] = {
                TOTAL: tuple(
                    a + b
                    for a, b in zip(found["r2"][TOTAL], found["uv"][TOTAL], strict=True)
                )
            }
        components.append(found)
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
        components=components,
    )


def _sectors(row, spec, data) -> Reference:
    """Per-sector references from several required fixtures of one request
    (``spec['parts']``: each fixture's totals are the values of its squared
    sector ``sector``, its Born that of ``born_sector``), at the same points
    and scales: e.g. g g > t t~ joint, the QCD fixture's s^6 and the EW
    fixture's s^4 e^2 (m-sm/PLAN.md §4.2 TT01). Providers: those of every
    part, primary first (``spec['providers']``)."""

    parts = [
        (part, _part_rows(part, json.loads((ROOT / part["path"]).read_text())))
        for part in spec["parts"]
    ]
    first = parts[0][1]
    names = [set(d["rows"][0]["providers"]) for _part, d in parts]
    providers = tuple(
        p for p in (spec.get("providers") or first["rows"][0]["providers"])
        if all(p in n for n in names)
    )  # fmt: skip
    # The model's inputs are those of part ``parameters_from`` (the parts may
    # come from different UFOs: loop_sm's QCD fixture beside the G_mu EW
    # one); the inputs the parts share must agree.
    parameters = dict(parts[int(spec.get("parameters_from", 0))][1]["parameters"])
    for _part, d in parts:
        if _strings_all(d["points"]) != _strings_all(first["points"]) or list(
            d["mu_r"]
        ) != list(first["mu_r"]):
            raise ValueError(f"{row.id}: the parts' points or scales differ")
        for name, value in d["parameters"].items():
            if name in parameters and Fraction(parameters[name]) != Fraction(value):
                raise ValueError(f"{row.id}: the parts' {name} differ")
    born, virtual, accuracy, evidence = [], [], [], []
    for index in range(len(first["rows"])):
        b: dict[str, dict] = {p: {} for p in providers}
        v: dict[str, dict] = {p: {} for p in providers}
        a: dict[str, dict] = {p: {} for p in providers}
        for part, d in parts:
            sector, born_key = (
                sector_key(part["sector"]),
                sector_key(part["born_sector"]),
            )
            for p in providers:
                values = d["rows"][index]["providers"][p]
                b[p].setdefault(born_key, float(values["born"]))
                v[p][sector] = _laurent(values)
                a[p][sector_text(sector)] = values.get(
                    "accuracy", values.get("estimated_relative_accuracy")
                )
        born.append(b)
        virtual.append(v)
        accuracy.append(a)
        evidence.append({})
    return Reference(
        "",
        providers,
        [_strings(p) for p in first["points"]],
        [_scale(mu) for mu in first["mu_r"]],
        parameters,
        dict(first.get("fixed_parameters", {})),
        born,
        virtual,
        accuracy,
        float(parameters["aS"]),
        evidence,
    )


def _part_rows(part: Mapping[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """A ``sectors`` part restricted to its rows ``part['rows']`` (e.g. a
    top-up run's rows at the existing fixture's points, without the top-up's
    mu_R / 2 copy); the whole fixture without them."""

    if part.get("rows") is None:
        return data
    keep = [int(i) for i in part["rows"]]
    return {
        **data,
        "rows": [data["rows"][i] for i in keep],
        "points": [data["points"][i] for i in keep],
        "mu_r": [data["mu_r"][i] for i in keep],
    }


def _strings_all(points) -> list:
    return [_strings(p) for p in points]


_LOADERS = {
    "ew-control": _ew_control,
    "cms-control": _cms_control,
    "madloop-components": _madloop_components,
    "process-components": _process_components,
    "sectors": _sectors,
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


def check_configuration():
    """The O1 estimate's checks: ``stability.RECOMMENDED_CHECKS`` (one
    generic exact rotation plus the rescaled reduction check)."""

    from pyamplicol.loops.v2.stability import RECOMMENDED_CHECKS

    return RECOMMENDED_CHECKS


def compile_restriction(ufo: Path, restriction: str, root: Path) -> Any:
    """loop_sm under ``restriction`` with the scalar-arity view of the tools
    route (``tests/conftest.py`` ``loop_sm_compiled_model``): the rows' main
    route, a test oracle of the model preparation. Production prepares the
    shipped loop_sm itself (MQ-MODEL, repairing only the reached vertices);
    the public route (``route: public``, ``PublicRun``) runs that path and
    M01's public variants hold it against the same references."""

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
        **{
            key: value
            for key, value in (
                ("compatibility", row.compatibility),
                ("scale_parameter", row.scale_parameter),
                ("allow_anomalous_veto", row.allow_anomalous_veto or None),
                ("external_photons", row.external_photons),
            )
            if value is not None
        },
        **changes,
    )


def row_request(row: Row, compiled: Any) -> Any:
    """``row``'s request on its compiled model: under the complex-mass scheme
    the fixed parameters the transformed model still has (the transform
    fixed them all; the former Yukawa inputs and the masses a restriction
    removed are not the model's parameters)."""

    if row.mass_scheme is None:
        return slice_request(row)
    defaults = compiled.parameter_defaults
    return slice_request(
        replace(
            row,
            fixed_parameters={
                k: v for k, v in row.fixed_parameters.items() if k in defaults
            },
        )
    )


def coloured_legs(row: Row) -> list[int]:
    """The one-based labels of a row's coloured external legs: the process's
    names other than loop_sm's colourless ones (``RowRun.tree_catani``
    checks them against the prepared model's colours)."""

    names = row.process.replace(">", " ").split()
    return [k for k, name in enumerate(names, 1) if name not in COLOURLESS]


# loop_sm's colourless particle names (leptons, neutrinos, bosons, Higgs).
COLOURLESS = frozenset(
    [
        "e-",
        "e+",
        "mu-",
        "mu+",
        "m-",
        "m+",
        "ta-",
        "ta+",
        "tt-",
        "tt+",
        "ve",
        "ve~",
        "vm",
        "vm~",
        "vt",
        "vt~",
        "a",
        "z",
        "w+",
        "w-",
        "h",
    ]
)


def tree_runtime(row: Row, ufo: Path, output: Path) -> Any:
    """The tree engine's artifact of the row's process with every dipole
    <T_j.T_k> of its coloured legs (``Generator.generate(...,
    correlators=...)``, full colour, the row's restriction and Born orders as
    explicit maxima), loaded; an existing artifact at ``output`` is loaded."""

    from itertools import combinations

    from pyamplicol import (
        ColorCorrelator,
        CorrelatorConfig,
        Generator,
        ModelSource,
        Runtime,
    )
    from pyamplicol.config import ColorConfig, RunConfig
    from pyamplicol.config.models import ProcessConfig

    if not (output / "artifact.json").is_file():
        config = RunConfig(
            action="generate",
            color=ColorConfig(accuracy="full"),
            process=ProcessConfig(
                coupling_order_policy="explicit",
                max_coupling_orders=dict(row.born_orders),
            ),
        )
        dipoles = tuple(
            ColorCorrelator.dipole(f"T{j}_{k}", j, k)
            for j, k in combinations(coloured_legs(row), 2)
        )
        Generator(config).generate(
            row.process,
            output,
            model=ModelSource.from_path(ufo, restriction=row.restriction),
            correlators=CorrelatorConfig(color_correlations=dipoles),
            mode="replace",
        )
    return Runtime.load(output)


def tree_point(runtime: Any, row: Row, point: Sequence[Sequence[str]]) -> dict:
    """The Born and every dipole of the tree engine's artifact at one point
    (decimal momenta, ``TREE_DIGITS`` digits), as fixture strings."""

    from itertools import combinations

    from pyamplicol.correlators import CorrelatedRequest

    pairs = [f"T{j}_{k}" for j, k in combinations(coloured_legs(row), 2)]
    requests = {name: CorrelatedRequest(color_correlation=name) for name in pairs}
    requests["born"] = CorrelatedRequest(color_correlation="born")
    momenta = (tuple(tuple(Decimal(x) for x in leg) for leg in point),)
    values = runtime.evaluate_correlated_many(momenta, requests, precision=TREE_DIGITS)
    return {
        "momenta": [list(leg) for leg in point],
        "born": str(values["born"][0].real),
        "dipoles": {name: str(values[name][0].real) for name in pairs},
    }


def _correlations(entry: Mapping[str, Any]) -> tuple[Decimal, dict]:
    correlated = {}
    for name, value in entry["dipoles"].items():
        j, k = (int(x) for x in name[1:].split("_"))
        correlated[j, k] = correlated[k, j] = Decimal(value)
    return Decimal(entry["born"]), correlated


def _row_parameters(row: Row, reference: Reference) -> dict[str, str]:
    """The runtime parameters of a row: its reference's (less those the
    row's model does not take, ``ignored_parameters``) and its own."""

    taken = {
        k: v for k, v in reference.parameters.items() if k not in row.ignored_parameters
    }
    return {**taken, **dict(row.parameters)}


class RowRun:
    """A row's generated slice and native executor (generated once, shared by
    every carrier, point and check of the row)."""

    def __init__(
        self,
        row: Row,
        compiled: Any,
        native: Any,
        base: RowRun | None = None,
        *,
        ufo: Path | None = None,
        work: Path | None = None,
    ):
        from pyamplicol.loops.v2.assemble import LoopSlice
        from pyamplicol.loops.v2.plan_export import NativeExecutor, export_plan

        self.row = row
        self.compiled = compiled
        self.native = native
        # The UFO and a work directory of the tree engine's artifact (the
        # "tree" Catani prediction).
        self.ufo, self.work = ufo, work
        self._tree: Any = None
        self._twin: RowRun | None = None
        self._ward: Any = None
        self.reference = load_reference(row)
        # (point, carrier) -> the native executor's reasons for a failed point
        self.failures: dict[tuple[int, str], str] = {}
        if base is not None:
            # A variant: the base row's request, generation and executor.
            if row_request(row, compiled) != row_request(base.row, base.compiled):
                raise ValueError(f"{row.id} changes its base row's request")
            self.slice, self.executor = base.slice, base.executor
            self.generate_seconds = self.export_seconds = 0.0
            self.parameters = _row_parameters(row, self.reference)
            return
        start = time.perf_counter()
        LOG.info("%s: generating %s", row.id, row.process)
        self.slice = LoopSlice.generate(compiled, row_request(row, compiled), native)
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
        self.parameters = _row_parameters(row, self.reference)

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
            parameters={**self.parameters, **self.row.ward_parameters},
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

    def tree_correlations(self, index: int) -> tuple[Decimal, dict]:
        """(Born, {(j, k): <T_j.T_k>}) of the tree engine at reference point
        ``index``: the row's committed tree-correlation fixture
        (``row.tree_correlations``, written by ``mqcd_tree_correlations.py``;
        checked to hold this point's momenta) or the tree engine run here
        (``tree_runtime``, generated once per row)."""

        point = self.reference.points[index]
        if self.row.tree_correlations is not None:
            data = json.loads((ROOT / self.row.tree_correlations).read_text())
            entry = next((e for e in data["points"] if e["index"] == index), None)
            if entry is None or entry["momenta"] != point:
                raise ValueError(
                    f"{self.row.id}: {self.row.tree_correlations} lacks point {index}"
                )
            return _correlations(entry)
        if self._tree is None:
            if self.ufo is None or self.work is None:
                raise ValueError(f"{self.row.id}: no UFO or work directory")
            start = time.perf_counter()
            self._tree = tree_runtime(
                self.row, self.ufo, self.work / f"tree-{self.row.id}"
            )
            LOG.info(
                "%s: tree correlators in %.1f s",
                self.row.id,
                time.perf_counter() - start,
            )
        return _correlations(tree_point(self._tree, self.row, point))

    def tree_catani(self, index: int) -> tuple[Decimal, dict[Sector, tuple]]:
        """(the tree engine's Born, rule 4's "tree" prediction {sector:
        (single, double)}) at reference point ``index``: the harness's
        massless Catani operator (``massless_catani``) on the tree engine's
        colour-correlated Born. Only for a QCD correction of one Born and one
        virtual sector with massless coloured legs (the native-input rows);
        anything else raises."""

        legs, loop = self.legs(), self.row.loop_orders
        if (
            tuple(self.row.corrections) != ("QCD",)
            or not isinstance(loop, Mapping)
            or any(massive for colour, massive in legs if colour != 1)
        ):
            raise NotImplementedError(f"{self.row.id}: no tree Catani prediction")
        born_orders = self.row.born_orders
        sector = sector_key(
            {k: born_orders.get(k, 0) + loop.get(k, 0) for k in {*born_orders, *loop}}
        )
        if coloured_legs(self.row) != [
            k for k, leg in enumerate(legs, 1) if leg[0] != 1
        ]:
            raise ValueError(f"{self.row.id}: coloured legs differ from the model's")
        born, correlated = self.tree_correlations(index)
        gluon = (
            Fraction(11, 6) * CA - Fraction(2, 3) * TF * self.light_flavours()
        )  # gamma_g = beta_0 over the massless flavours
        coloured = {
            label: (colour, gluon if colour == 8 else Fraction(3, 2) * CF)
            for label, (colour, _m) in enumerate(legs, 1)
            if colour != 1
        }
        if any(colour not in (3, 8) for colour, _gamma in coloured.values()):
            raise NotImplementedError(f"{self.row.id}: no tree Catani prediction")
        point = [[Fraction(x) for x in leg] for leg in self.reference.points[index]]
        poles = massless_catani(
            coloured,
            point,
            correlated,
            Fraction(self.reference.scales[index]),
            Decimal(str(self.parameters["aS"])),
        )
        return born, {sector: poles}

    def engine_catani(self, index: int) -> dict[Sector, tuple[Decimal, Decimal]] | None:
        """Rule 4's "engine" prediction of a native-input row (whose executor
        forms none, WP3.1 I5c): the engine's own operators (QCD and QED per
        correction, ``_PointEvaluation._ir_poles``) on the Python-input Born
        of reference point ``index`` in double-double, without the loops."""

        from pyamplicol.loops.v2.assemble import Precision, _fraction, _Numbers

        reference = self.reference
        point = tuple(
            tuple(_fraction(x) for x in leg) for leg in reference.points[index]
        )
        precision = Precision.double_double()
        with _Numbers(precision).scope():
            evaluation = self.slice._point(
                point,
                _fraction(reference.scales[index]),
                dict(self.parameters),
                precision,
                "all",
            )
            if not evaluation._stable_coloured_legs():
                return None
            found = evaluation._ir_poles()
        if found is None:
            return None
        return {
            sector: (_number(single), _number(double))
            for sector, (single, double) in found.items()
        }

    def light_flavours(self) -> int:
        """The n_f of Catani's gamma_g: the loop flavours (``loop_flavours``)
        that are massless at the row's parameters."""

        return self.loop_flavours(massless=True)

    def loop_flavours(self, massless: bool = False) -> int:
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
                if massless and not self._massless(record["mass"]):
                    continue
                count += 1
        return count

    def _massless(self, mass: str) -> bool:
        if mass == "ZERO":
            return True
        values = {**dict(self.row.fixed_parameters), **self.parameters}
        return mass in values and Fraction(str(values[mass])) == 0


# ---------------------------------------------------------- the public route


def public_card(row: Row, output: Path) -> str:
    """The public route's generation card of ``row``: the shipped loop_sm
    (``model.source = "loop_sm"``, no ``[loop.model]``, the default full
    colour), the row's restriction and fixed parameters, its corrections,
    the model's R2 and the minimal Born orders (PLAN §4.2 M01)."""

    if row.particle_veto or row.gauge != "unitary":
        raise ValueError(f"{row.id}: the public-route card states no veto or gauge")
    fixed = ", ".join(f"{k} = {json.dumps(v)}" for k, v in row.fixed_parameters.items())
    return f"""action = "generate"
[model]
source = "loop_sm"
restriction = {json.dumps(row.restriction)}
[process]
entries = [{{expression = {json.dumps(row.process)}, name = {json.dumps(row.id)}}}]
loop_coupling_orders = {json.dumps(list(row.corrections))}
coupling_order_policy = "minimal"
[loop]
r2_strategy = "model"
[loop.preparation]
fixed_parameters = {{{fixed}}}
[generation]
output = {json.dumps(str(output))}
emit_api_bundle = false
[generation.validation]
post_build_validation = false
"""


def generate_public(row: Row, work: Path) -> tuple[Path, float]:
    """``row``'s public-route artifact (``Generator``) and its seconds."""

    from pyamplicol.api import Generator, ProcessRequest, ProcessSet
    from pyamplicol.config import resolve_config

    work.mkdir(parents=True, exist_ok=True)
    output = work / "artifact"
    card = work / "card.toml"
    card.write_text(public_card(row, output))
    start = time.perf_counter()
    LOG.info("%s: generating %s on the public route", row.id, row.process)
    Generator(resolve_config(card)).generate(
        ProcessSet((ProcessRequest.parse(row.process, name=row.id),)), output
    )
    seconds = time.perf_counter() - start
    LOG.info("%s: generated in %.1f s", row.id, seconds)
    return output, seconds


def public_evaluated(result: Any, k: int, carrier: str, seconds: float) -> Evaluated:
    """``Evaluated`` of point ``k`` of a public ``VirtualEvaluation``. Its
    stability estimate is relative per coefficient for the whole point, so
    it becomes absolute per sector only for a single loop sector."""

    born = {
        sector_key(order): _number(value)
        for order, value in zip(result.born_orders, result.born_values[k], strict=True)
    }
    virtual = {
        sector_key(sector.order): tuple(
            _number(getattr(laurent, name)) for name in LAURENT
        )
        for sector, laurent in zip(result.sectors, result.values[k], strict=True)
    }
    estimate = None
    found = result.stability[k] if result.stability is not None else None
    if found is not None:
        if len(virtual) != 1:
            raise ValueError("a public-route estimate per sector needs one sector")
        ((sector, values),) = virtual.items()
        largest = max(abs(float(v)) for v in values)
        estimate = {
            sector: tuple(
                rel * abs(float(v)) if math.isfinite(rel) else found.relative * largest
                for rel, v in zip(
                    (found.finite, found.single_pole, found.double_pole),
                    values,
                    strict=True,
                )
            )
        }
    return Evaluated(carrier, born, virtual, None, estimate, seconds)


class PublicRun:
    """A subprocess variant on the public route (``route: public``; PLAN
    §4.2 M01): its base row's request generated once by ``Generator`` on the
    shipped loop_sm (a multiparticle label: one artifact of every
    subprocess), the variant's process loaded from it by expression and
    evaluated through ``Runtime`` at the variant's reference points with the
    O1 checks (one exact rotation and the reduction direction). The public
    route takes the model card's parameter values, which must be the
    reference's."""

    def __init__(self, row: Row, artifact: Path, generate_seconds: float, model):
        from pyamplicol import Runtime

        self.row = row
        self.reference = load_reference(row)
        self.failures: dict[tuple[int, str], str] = {}
        self.generate_seconds, self.export_seconds = generate_seconds, 0.0
        values = {record.name: record.value for record in model.ir.parameters}
        for name, value in self.reference.parameters.items():
            ours = values[name][0] if isinstance(values[name], tuple) else values[name]
            if Decimal(str(ours)) != Decimal(value):
                raise ValueError(
                    f"{row.id}: the model card's {name} = {ours} is not the "
                    f"reference's {value} (the public route takes the card)"
                )
        self.runtime = Runtime.load(artifact, process=row.process)

    def evaluate(
        self,
        indices: Sequence[int],
        carrier: str,
        *,
        poles: str = "all",
        stability: bool = True,
    ) -> list[Evaluated]:
        from pyamplicol.api.virtual_results import VirtualStabilityChecks

        if carrier not in ("double", "double-double"):
            raise ValueError(f"{self.row.id}: no {carrier} on the public route here")
        reference = self.reference
        start = time.perf_counter()
        LOG.info("%s: %s at points %s (public)", self.row.id, carrier, list(indices))
        result = self.runtime.evaluate(
            [reference.points[i] for i in indices],
            mu_r2=[reference.scales[i] for i in indices],
            arithmetic=carrier,
            poles=poles,
            stability_checks=VirtualStabilityChecks(
                check_configuration().rotations, True, rescaled=True
            )
            if stability
            else None,
            on_failure="return",
        )
        seconds = (time.perf_counter() - start) / max(1, len(indices))
        out = []
        for k, index in enumerate(indices):
            if not result.valid[k]:
                diagnostic = result.diagnostics[k]
                self.failures[index, carrier] = (
                    f"{diagnostic.status}: {diagnostic.detail}"
                )
                out.append(None)
                continue
            out.append(public_evaluated(result, k, carrier, seconds))
        return out


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


def born_sector(sector: Sector, correction: str = "QCD") -> Sector:
    """The Born sector of a virtual sector under ``correction`` (two powers
    of its order fewer; QCD by default)."""

    orders = dict(sector)
    orders[correction] = orders.get(correction, 0) - 2
    return sector_key(orders)


def alphas(row: Row, reference: Reference) -> dict[str, float]:
    """The loop coupling per correction: aS (the reference's) for QCD, the
    row's ``alphas`` for the others."""

    return {"QCD": reference.alpha_s, **dict(row.alphas)}


def sector_flux(
    row: Row, point: Evaluated, sector: Any, couplings: Mapping[str, float]
) -> float:
    """F_s of a virtual sector (``TOTAL``: the summed Born times the largest
    alpha): the largest |B_{s - 2c}| alpha_c / 2 pi over the row's
    corrections c reaching s (m-sm/PLAN.md §1.4; a QCD row's |B_{s-2}|
    alpha_s / 2 pi, m-qcd/PLAN.md §1.4)."""

    if sector == TOTAL:
        alpha = max(couplings[c] for c in row.corrections)
        return _flux(born_scale(row, point, TOTAL), alpha)
    reaching = [c for c in row.corrections if dict(sector).get(c, 0) >= 2]
    return max(
        (
            _flux(born_scale(row, point, born_sector(sector, c)), couplings[c])
            for c in reaching or ("QCD",)
        ),
        default=0.0,
    )


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
        # Per-sector references: our sectors are the provider's (a reference
        # of some of the request's sectors, ``sectors_subset``: among ours).
        subset = bool((row.reference or {}).get("sectors_subset"))
        same = (
            set(virtual_values) <= set(dd.virtual)
            if subset
            else set(dd.virtual) == set(virtual_values)
        )
        checks.append(Check(
            "1", index, "double-double", "", "sectors",
            ", ".join(sorted(map(sector_text, dd.virtual))),
            ", ".join(sorted(map(sector_text, virtual_values))), 0.0, 0.0, same,
            note="virtual sectors against the provider's split orders"
            + (" (the reference's among ours)" if subset else "")))  # fmt: skip
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
        flux = sector_flux(row, dd, sector, alphas(row, reference))
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
    2; at least the row's ``relaxed["2"]``) and the tenfold bracketing of the
    estimate (rule 3). A coefficient outside the O1 scope is reported with E
    and its true error, not asserted."""

    checks = []
    floor = row.relaxed.get("2", 0.0)
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
        bound = max(O1_STRICT, floor)
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
                bound,
                error <= bound,
            )
        )
    for sector, laurent in dd.virtual.items():
        text = sector_text(sector)
        mine = b64.virtual.get(sector)
        estimate = None if b64.estimate is None else b64.estimate.get(sector)
        flux = sector_flux(row, dd, sector, alphas(row, reference))
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
                # At least the row's relaxed rule-2 factor (a binary64
                # rounding residue of a cancelling coefficient, ~10:20).
                bound = max(REFERENCE_TOLERANCE, row.relaxed.get("2", 0.0)) * flux
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
                        True,
                        asserted=False,
                        note=f"E = {e_rel:.3g} > 1e-9: outside the binary64 scope",
                    )
                )
            else:
                bound = max(bound, floor)
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
                        error <= bound,
                        note=f"E = {e_rel:.3g}",
                    )
                )
    return checks


def rule4_relaxed_key(carrier: str) -> str:
    """The ``relaxed`` key of rule 4 on ``carrier``: ``"4"`` for binary64
    (``"double"``), ``"4dd"`` for double-double."""

    return "4" if carrier == "double" else "4dd"


def rule4(
    row: Row,
    index: int,
    point: Evaluated,
    alpha_s: float = 0.118,
    couplings: Mapping[str, float] | None = None,
) -> list[Check]:
    """The virtual's poles against Catani's (the engine's operators, QCD and
    QED per correction, ``PointResult.ir_poles``), and the sector sets
    (``couplings``: the loop coupling per correction for F_s, default the
    strong one ``alpha_s``)."""

    couplings = dict(couplings or {"QCD": alpha_s})

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
                # Absolutely, against F_s: 1e-12 in binary64 (at least the
                # row's relaxed rule-4 factor), 1e-24 in DD.
                strict = (
                    max(O1_STRICT, row.relaxed.get("4", 0.0))
                    if point.carrier == "double"
                    else DD_FLOOR
                )
                bound = strict * sector_flux(row, point, sector, couplings)
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
                            True,
                            asserted=False,
                            note=f"E = {e_rel:.3g} > 1e-9: outside the binary64 scope",
                        )
                    )
                    continue
            else:
                bound = max(DD_FLOOR, BRACKET * e_rel)
            # The user's ruling of 2026-10-29 ~10:20: a row's relaxed rule 4,
            # per carrier (``relaxed["4"]`` binary64, ``relaxed["4dd"]``
            # double-double; at most ``ATTENTION``): a carrier that passes
            # keeps its band.
            bound = max(bound, row.relaxed.get(rule4_relaxed_key(point.carrier), 0.0))
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


def rule4_reasons(row: Row, found: Mapping[Sector, str]) -> list[Check]:
    """Rule 4's typed reasons (m-sm/PLAN.md §1.4): the slice's unpredicted
    sectors and their reasons (``LoopSlice.unpredicted_sectors``) are the
    manifest's (``Row.unpredicted_reasons``), every one of them a listed
    reason (``poles.UNPREDICTED_REASONS``)."""

    from pyamplicol.loops.v2.poles import UNPREDICTED_REASONS

    if row.unpredicted_reasons is None:
        return []
    ours = {sector_text(sector): reason for sector, reason in found.items()}
    expected = dict(row.unpredicted_reasons)
    text = ", ".join(f"{k}: {v}" for k, v in sorted(ours.items()))
    want = ", ".join(f"{k}: {v}" for k, v in sorted(expected.items()))
    listed = all(reason in UNPREDICTED_REASONS for reason in ours.values())
    return [
        Check("4", None, "", "", "unpredicted reasons", text or "none",
              want or "none", 0.0, 0.0, ours == expected and listed,
              note="the slice's typed reasons of its unpredicted sectors")
    ]  # fmt: skip


# Feynman-gauge Z^UV per leg (amplitude delta-Z / 2 enters the interference
# once per leg as delta-Z x Born), single-pole coefficients over alpha_s/4pi,
# exactly.
CA, CF, TF = Fraction(3), Fraction(4, 3), Fraction(1, 2)
PI = Decimal(
    "3.14159265358979323846264338327950288419716939937510582097494459230781640628621"
)


TREE_DIGITS = 40  # the tree engine's colour-correlated Born (rule 4 "tree")


def _decimal(value: Fraction) -> Decimal:
    return Decimal(value.numerator) / Decimal(value.denominator)


def massless_catani(
    legs: Mapping[int, tuple[int, Fraction]],
    point: Sequence[Sequence[Fraction]],
    correlated: Mapping[tuple[int, int], Decimal],
    mu2: Fraction,
    alpha_s: Decimal,
) -> tuple[Decimal, Decimal]:
    """(single, double) pole of the renormalised virtual by Catani's operator
    for massless coloured legs: (alpha_s / 2 pi) sum_j sum_{k != j}
    <T_j.T_k> (1/eps^2 + (gamma_j / C_j + log(mu^2 / |2 p_j.p_k|)) / eps),
    with <T_j.T_k> the colour-correlated Born (``correlated``, both orders)
    and ``legs`` (|colour|, gamma_j) per coloured leg (one-based labels into
    ``point``), in ``TREE_DIGITS`` decimal digits."""

    with localcontext() as context:
        context.prec = TREE_DIGITS
        single = double = Decimal(0)
        for j, (colour, gamma) in legs.items():
            ratio = _decimal(gamma / (CA if colour == 8 else CF))
            for k in legs:
                if k == j:
                    continue
                a, b = point[j - 1], point[k - 1]
                dot = a[0] * b[0] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3]
                log = _decimal(mu2 / abs(2 * dot)).ln()
                double += correlated[j, k]
                single += (ratio + log) * correlated[j, k]
        prefactor = alpha_s / (2 * PI)
        return +(prefactor * single), +(prefactor * double)


def rule_ff(
    row: Row,
    index: int,
    dd: Evaluated,
    legs: Sequence[tuple[int, bool]],
    reference: Reference,
    alpha_s: Decimal,
) -> list[Check]:
    """The analytic quark form factor (PLAN §4.2 D01): a massless q q~ pair
    annihilating into colour singlets at QCD order zero has, per Born, V/B =
    (alpha_s / 2 pi) C_F (-2/eps^2 - (3 + 2L)/eps - 8 + pi^2 - L^2 - 3L),
    L = log(mu^2 / s), in the (4 pi)^eps / Gamma(1 - eps) normalisation of
    the 't Hooft-Veltman scheme (the time-like one-loop vertex; massless
    quarks need no field renormalisation). Double-double per coefficient at
    max(1e-24, 10 E_DD), strictly relative."""

    if [leg for leg in legs if leg[0] != 1] != [(3, False), (3, False)] or any(
        colour != 1 for colour, _m in legs[2:]
    ):
        raise ValueError(f"{row.id}: no massless q q~ -> colour singlets form factor")
    ((sector, laurent),) = dd.virtual.items()
    born = dd.total()[0]
    a, b = ([Fraction(x) for x in leg] for leg in reference.points[index][:2])
    total = [x + y for x, y in zip(a, b, strict=True)]
    s = total[0] ** 2 - total[1] ** 2 - total[2] ** 2 - total[3] ** 2
    checks = []
    with localcontext() as context:
        context.prec = TREE_DIGITS
        log = _decimal(Fraction(reference.scales[index]) / s).ln()
        factor = alpha_s / (2 * PI) * _decimal(CF) * born
        expected = (
            factor * (-8 + PI * PI - log * log - 3 * log),
            factor * (-3 - 2 * log),
            factor * -2,
        )
    estimate = None if dd.estimate is None else dd.estimate[sector]
    for k, name in enumerate(LAURENT):
        error = relative(laurent[k], expected[k])
        e_rel = (
            estimate[k] / abs(float(laurent[k]))
            if estimate is not None and float(laurent[k])
            else 0.0
        )
        bound = max(DD_FLOOR, BRACKET * e_rel)
        checks.append(Check(
            "ff", index, dd.carrier, sector_text(sector), name, str(laurent[k]),
            str(expected[k]), error, bound, error <= bound,
            note=f"analytic quark form factor; E_DD = {e_rel:.3g}"))  # fmt: skip
    return checks


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
    row: Row,
    index: int,
    dd: Evaluated,
    ap: Evaluated,
    ap60: Evaluated,
    alpha_s: float = 0.118,
    couplings: Mapping[str, float] | None = None,
) -> list[Check]:
    """Arbitrary precision against double-double and against 60 digits
    (``AP_CONVERGENCE``, at least the row's ``relaxed["6"]``; a coefficient
    that vanishes identically absolutely, against F_s; ``couplings`` the
    loop coupling per correction, default the strong one ``alpha_s``)."""

    couplings = dict(couplings or {"QCD": alpha_s})
    checks = []
    convergence = max(AP_CONVERGENCE, row.relaxed.get("6", 0.0))
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
                convergence,
                error <= convergence,
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
                flux = sector_flux(row, dd, sector, couplings)
                for other, scale, note in (
                    (truth, DD_FLOOR, "double-double"),
                    (ap60.virtual[sector][k], convergence, "60 digits"),
                ):
                    error = _absolute(laurent[k], other)
                    checks.append(Check(
                        "6", index, ap.carrier, text, name, str(laurent[k]),
                        str(other), error, scale * flux, error <= scale * flux,
                        note=f"vanishes identically: |a - r| against F_s ({note})",
                    ))  # fmt: skip
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
                    convergence,
                    error <= convergence,
                    note="against 60 digits",
                )
            )
    return checks


def rule5_components(
    row: Row,
    index: int,
    dd: Evaluated,
    reference: Reference,
    couplings: Mapping[str, float],
) -> list[Check]:
    """Rule 5's EW form (m-sm/PLAN.md §1.4): the bare, R2 and UV-counterterm
    components (and their CT sum) per sector equal the primary provider's
    instrumented components (``Reference.components``; MadLoop's Born x CT
    interference split, its omitted R2 component added where the row has
    one), in double-double within the row's rule 1 tolerance, relative to
    max(|a|, |r|, F_s) (a component may vanish identically: UV finite parts,
    the R2 poles)."""

    theirs = reference.components[index] if index < len(reference.components) else {}
    checks = []
    mine_parts = {
        "bare": ("bare",),
        "r2": ("r2",),
        "uv": ("uv",),
        "ct": ("r2", "uv"),
    }
    for name, values in sorted(theirs.items()):
        for sector, laurent in values.items():
            parts = [dd.components.get(part, {}) for part in mine_parts[name]]
            if sector == TOTAL:
                mine = [
                    sum((v[k] for part in parts for v in part.values()), Decimal(0))
                    for k in range(3)
                ]
            else:
                mine = [
                    sum(
                        (part[sector][k] for part in parts if sector in part),
                        Decimal(0),
                    )
                    for k in range(3)
                ]
            flux = sector_flux(row, dd, sector, couplings)
            text = sector_text(sector)
            for k, coefficient in enumerate(LAURENT):
                error = _absolute(mine[k], laurent[k]) / max(
                    abs(float(mine[k])), abs(laurent[k]), flux
                )
                bound = max(row.reference_tolerance, row.relaxed.get("5", 0.0))
                checks.append(Check(
                    "5", index, dd.carrier, text, f"{name} {coefficient}",
                    str(mine[k]), repr(laurent[k]), error, bound, error <= bound,
                    note=f"the {name} component against {reference.primary}'s, "
                    "relative to max(|a|, |r|, F_s)"))  # fmt: skip
    return checks


def rule_joint(row: Row, run: RowRun, index: int, dd: Evaluated) -> list[Check]:
    """The ``joint`` extra (m-sm/PLAN.md §1.2): a joint request equals the
    separate requests per sector. Each loop amplitude order of the row's
    request is generated as a request of its own (the same process, Born
    orders, corrections and model) and evaluated in double-double at point
    ``index``; its Born and each of its sectors' Laurent coefficients equal
    the joint request's within max(1e-24, 10 E_DD), strictly relative (a
    coefficient that vanishes in both passes)."""

    loops = row.loop_orders
    loops = (loops,) if isinstance(loops, Mapping) else tuple(loops)
    if len(loops) < 2:
        note = "one loop order: the joint request is the separate one"
        return [Check("joint", index, "double-double", "", "requests", "1", "",
                      0.0, 0.0, True, asserted=False, note=note)]  # fmt: skip
    checks = []
    for k, loop in enumerate(loops):
        single = replace(
            row,
            id=f"{row.id}~loop{k}",
            loop_orders=dict(loop),
            variants=(),
            madloop_omitted_r2=None,
        )
        separate = RowRun(single, run.compiled, run.native)
        (theirs,) = separate.evaluate([index], "double-double")
        if theirs is None:
            note = separate.failures.get((index, "double-double"), "")
            checks.append(Check("joint", index, "double-double", str(dict(loop)),
                                "evaluation", "failed", "", math.inf, 0.0, False,
                                note=note))  # fmt: skip
            continue
        pairs = [
            (sector_text(s), "born", dd.born.get(s), v, None)
            for s, v in theirs.born.items()
        ]
        for sector, laurent in theirs.virtual.items():
            mine = dd.virtual.get(sector)
            estimate = None if dd.estimate is None else dd.estimate.get(sector)
            for j, name in enumerate(LAURENT):
                pairs.append((
                    sector_text(sector), name, None if mine is None else mine[j],
                    laurent[j], None if estimate is None else estimate[j]))  # fmt: skip
        for sector, name, mine, value, estimate in pairs:
            if mine is None:
                checks.append(Check("joint", index, "double-double", sector, name,
                                    "absent", str(value), math.inf, 0.0, False,
                                    note="the separate request's sector is absent "
                                    "from the joint one"))  # fmt: skip
                continue
            error = relative(mine, value)
            e_rel = estimate / abs(float(mine)) if estimate and float(mine) else 0.0
            bound = max(DD_FLOOR, BRACKET * e_rel)
            checks.append(Check(
                "joint", index, "double-double", sector, name, str(mine), str(value),
                error, bound, error <= bound,
                note=f"the joint request against the separate request of loop "
                f"order {dict(loop)}"))  # fmt: skip
    return checks


def r2_reachability(
    slice_: Any, sectors: Iterable[Sector] | None = None
) -> Callable[[Any], bool]:
    """Whether a CT rule's vertex can enter a tree of the slice's request:
    ``ct_closure.InsertionReachability.admits`` over the CT program's
    lowered model, process, order limits and vetoed particles (the sweep
    production runs for its inert rules: species and coupling orders, no
    colour or flavour; a vertex it finds in no tree enters none). With
    ``sectors`` (squared-order sector keys) the physical order limits are
    those of the loop amplitude orders that reach them (``LoopSlice.
    sectors``): a tree of the request's other sectors is not held."""

    from pyamplicol.loops.v2.blocks import vetoed_particle_ids
    from pyamplicol.loops.v2.ct_closure import InsertionReachability
    from pyamplicol.models.loading import COUNTERTERM_INSERTION_ORDER
    from pyamplicol.processes.model import build_model_process_ir

    recursion = slice_.counterterm_program.recursion
    lowered = recursion.model.lowered
    ir = build_model_process_ir(
        slice_.request.process, lowered.compiled.ir, color_accuracy="full"
    )
    limits = recursion.coupling_order_limits()
    if sectors is not None:
        wanted = set(sectors)
        # ``LoopSlice.sectors``: per sector its (Born, loop) amplitude orders.
        loops = [
            dict(loop)
            for sector, pairs in slice_.sectors
            if sector_key(sector) in wanted
            for _born, loop in pairs
        ]
        if loops:
            insertion = COUNTERTERM_INSERTION_ORDER.upper()
            limits = {
                name: bound
                if name.upper() == insertion
                else max(loop.get(name, 0) for loop in loops)
                for name, bound in limits.items()
            }
    return InsertionReachability.build(
        lowered.tree_model(),
        ir,
        limits,
        ignored_particle_ids=vetoed_particle_ids(recursion.model.veto),
    ).admits


def r2_export_sectors(reference: Reference) -> frozenset[Sector] | None:
    """The sectors of the MadLoop export whose called R2 couplings the row
    lists (``madloop_r2_called``): those MadLoop's values report at the
    reference's points (the primary's without MadLoop values); None where a
    provider reports only the total."""

    found: set[Any] = set()
    for values in reference.virtual:
        name = "madloop" if "madloop" in values else reference.primary
        found |= set(values.get(name, {}))
    if not found or TOTAL in found:
        return None
    return frozenset(found)


def engine_r2(
    slice_: Any, reachable: Callable[[Any], bool] | None = None
) -> dict[str, frozenset[str]]:
    """CT vertex name -> the UFO R2 couplings the slice's counterterm program
    inserts at it: its admitted R2 rules (one per loop-particle group,
    ``CountertermRecursion.admission``), inert ones left out, whose vertex
    can enter a tree of the request (``reachable``, default
    ``r2_reachability``): the admission reads coupling orders only, so it
    also admits vertices no tree of the process holds (R2_AAAA in
    t t~ > t t~), which insert nothing."""

    program = getattr(slice_, "counterterm_program", None)
    if program is None:
        return {}
    recursion = program.recursion
    if reachable is None:
        reachable = r2_reachability(slice_)
    found: dict[str, set[str]] = defaultdict(set)
    for name, rule in recursion.rules.items():
        if rule.kind != "R2" or not recursion.admission.get(name):
            continue
        if name in recursion.inert or not reachable(rule):
            continue
        for _alias, entry in rule.couplings:
            found[entry.vertex_name].add(entry.coupling.name)
    return {vertex: frozenset(names) for vertex, names in found.items()}


def rule_r2(
    row: Row,
    slice_: Any,
    reference: Reference,
    classes: Mapping[str, Any] | None = None,
    engine: Mapping[str, frozenset[str]] | None = None,
) -> list[Check]:
    """The R2 rule's structural checks (m-sm/PLAN.md §1.4 rule 1, Q7): every
    R2 coupling the row lists as omitted by MadLoop's label matching
    (``madloop_omitted_r2``) is inserted by the engine's counterterm program
    (``engine``, default ``engine_r2``), so rule 1 holds the UFO-complete
    insertion against Recola or MadLoop plus the omitted component; and,
    where the reference lists the couplings its MadLoop export calls
    (``madloop_r2_called``) and ``classes`` gives MG5_aMC's identical-coupling
    classes (``r2_value_classes``), the omission found structurally, the
    engine's inserted couplings that no called coupling's class holds,
    equals the listed set (less the row's ``r2_vanishing``, couplings whose
    insertion vanishes in its sectors, each of them in that difference): an
    unlisted omission fails here, before rule 1 against MadLoop."""

    if engine is None:
        engine = engine_r2(slice_)
    inserted = set().union(*engine.values()) if engine else set()
    checks = []
    listed = set(row.madloop_omitted_r2 or ())
    if listed:
        checks.append(Check(
            "r2", None, "", "", "inserted", ", ".join(sorted(listed - inserted))
            or "all", ", ".join(sorted(listed)), 0.0, 0.0, listed <= inserted,
            note="MadLoop's omitted R2 couplings are in the engine's "
            f"counterterm program (rule 1 against {reference.primary})"))  # fmt: skip
    if row.madloop_r2_called is not None and classes is not None:
        called = {classes.get(name) for name in row.madloop_r2_called} - {None}
        omitted = {
            name
            for name in inserted
            if classes.get(name) is not None and classes[name] not in called
        }
        vanishing = set(getattr(row, "r2_vanishing", ()) or ())
        found = omitted - vanishing
        checks.append(Check(
            "r2", None, "", "", "omitted", ", ".join(sorted(found)) or "none",
            ", ".join(sorted(listed)) or "none", 0.0, 0.0,
            listed == found and vanishing <= omitted,
            note="the engine's inserted R2 couplings (on vertices a tree of the "
            "request can hold) whose MG5 identical-coupling class MadLoop's "
            "export does not call = the row's madloop_omitted_r2"))  # fmt: skip
    return checks


def r2_value_classes(
    ufo: Path, restriction: str, names: Iterable[str]
) -> dict[str, Any]:
    """MG5_aMC's identical-coupling classes of a UFO's couplings ``names``
    (``import_ufo.detect_identical_couplings``, which the restricted export
    merges under one name): each coupling's value at the restriction card
    (``restrict_<restriction>.dat``) from the UFO's own source (a Laurent
    coupling's finite part), rounded to ten significant digits per component
    and taken up to sign; None for a vanishing coupling (MG5 removes it).
    The UFO's evaluated parameters are cached per (UFO, restriction)."""

    key = (str(Path(ufo).resolve()), restriction)
    if key not in _R2_CLASSES:
        from tools.loop_reference import ufo_source_oracle as oracle

        modules = oracle.import_ufo(Path(ufo), f"_mqcd_r2_ufo_{len(_R2_CLASSES)}")
        card = restriction_card(Path(ufo), restriction)
        values, environment = oracle.ufo_source_values(
            modules, card, exact=False, wrap=None
        )
        environment = {
            **environment,
            **{k: v for (k, power), v in values.items() if power == 0},
        }
        couplings = {c.name: c for c in modules[3].all_couplings}
        _R2_CLASSES[key] = (oracle, environment, couplings, {})
    oracle, environment, couplings, found = _R2_CLASSES[key]

    def rounded(x: float) -> float:
        # MG5's limit_to_6_digit: ten significant digits.
        return x if x == 0 else round(x, int(abs(round(math.log10(abs(x)), 0))) + 10)

    for name in set(names) - set(found):
        source = couplings[name].value
        if isinstance(source, dict):  # a Laurent coupling: its finite part
            source = source.get(0, "0")
        value = complex(eval(oracle.compiled(source, False), environment))
        if abs(value) < 1e-13:
            found[name] = None
            continue
        z = complex(rounded(value.real), rounded(value.imag))
        if z.real < 0 or (z.real == 0 and z.imag < 0):
            z = -z
        found[name] = (z.real, z.imag)
    return {name: found[name] for name in names}


_R2_CLASSES: dict[tuple[str, str], tuple] = {}


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
    regular neighbour (else the manifest is stale: a failing check). A
    superseded point's binding rerun (``Reference.binding``) and a declared
    outlier need no check of their own: rule 1 holds the binding values and
    judges an outlier by the manifest's listing."""

    record = reference.record(index)
    if record is None:
        return []
    checks = []
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
    1e-9 of the scale) is not asserted; its estimate must still bracket
    |V_k| tenfold (rule 3)."""

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
            note = (
                f"max_k |V_k| / max(1e-12 scale_k, E_k); |V_k| / scale_k "
                f"{max(virtual):.3g}; |V_k| / E_k {bracket:.3g} "
                f"(<= {ward.ESTIMATE_FACTOR}); E_k / scale_k "
                f"{max(entry['estimate']):.3g} (in scope: {entry['in_scope']})"
            )
            if not entry["in_scope"]:
                # Outside the binary64 scope: bracketed tenfold only.
                asserted = False
                passed = bracket <= ward.ESTIMATE_FACTOR
                note += "; outside the binary64 scope"
        else:
            error, bound = max(virtual), math.nan
            note = "no binary64 criterion without the reduction-direction check"
        checks.append(Check(
            "ward", index, carrier, label, "virtual", "", "0", error, bound,
            passed, asserted=asserted, note=note))  # fmt: skip
    return checks


def diagnostics(checks: Iterable[Check]) -> list[Check]:
    """``checks`` recorded as diagnostics: not asserted, their outcome in
    the note (a diagnostic extra, ``Row.diagnostic_extras``)."""

    return [
        replace(
            check,
            passed=True,
            asserted=False,
            note=f"diagnostic ({'holds' if check.passed else 'misses'}): {check.note}",
        )
        for check in checks
    ]


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
    tree_seconds = 0.0

    def poles(index: int, *points: Evaluated) -> list[Check]:
        """Rule 4 at ``index`` in each evaluated carrier (double-double
        first): the executor's prediction, the tree engine's ("tree", with
        its Born against ours) or none (recorded as not formed)."""

        nonlocal tree_seconds
        if row.catani == "none":
            reason = row.catani_reason or (
                "no Catani prediction on the public route (the tools-route "
                "variant holds rule 4)"
            )
            return [Check(
                "4", index, "double-double", "", "poles", "", "", 0.0, 0.0, True,
                asserted=False, note=reason)]  # fmt: skip
        found = []
        if row.catani == "engine":
            start = time.perf_counter()
            prediction = run.engine_catani(index)
            tree_seconds += time.perf_counter() - start
            for point in points:
                point.catani = prediction
        if row.catani == "tree":
            start = time.perf_counter()
            born, prediction = run.tree_catani(index)
            tree_seconds += time.perf_counter() - start
            ours = points[0].total()[0]
            error = relative(ours, born)
            found.append(Check(
                "4", index, points[0].carrier, TOTAL, "tree born", str(ours),
                str(born), error, DD_FLOOR, error <= DD_FLOOR,
                note="the tree engine's Born (the prediction's colour-correlated "
                "Born) against ours"))  # fmt: skip
            for point in points:
                point.catani = prediction
        for point in points:
            found += rule4(row, index, point, reference.alpha_s, alphas(row, reference))
        return found

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
                    checks += poles(index, d)
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
        checks += poles(index, d, b)
    if tree_seconds:
        timings[f"{row.catani}_catani_s"] = round(tree_seconds, 2)
    if row.unpredicted_reasons is not None and row.catani != "none":
        checks += rule4_reasons(row, run.slice.unpredicted_sectors())
    # The extras the harness checks on the nightly tier (the campaign tier's
    # rows too), less those the manifest lists as waiting for a package.
    extras = (
        (set(row.extras) & IMPLEMENTED_EXTRAS) - set(row.extras_pending)
        if tier in ("nightly", "campaign")
        else set()
    )
    extra_points = indices[:1]
    if (
        row.madloop_omitted_r2 is not None or row.madloop_r2_called is not None
    ) and hasattr(run, "slice"):
        ufo = getattr(run, "model_ufo", None)
        classes = None
        # The R2 couplings of the sectors the MadLoop export covers.
        engine = engine_r2(
            run.slice, r2_reachability(run.slice, r2_export_sectors(reference))
        )
        if ufo is not None and row.madloop_r2_called is not None:
            inserted = set().union(*engine.values()) if engine else set()
            classes = r2_value_classes(
                ufo, row.restriction, sorted(inserted | set(row.madloop_r2_called))
            )
        checks += rule_r2(row, run.slice, reference, classes, engine)
    if "uv" in extras and reference.components:
        # Rule 5's EW form: the components against the provider's.
        for index, point in zip(indices, dd, strict=True):
            if point is not None:
                checks += rule5_components(
                    row, index, point, reference, alphas(row, reference)
                )
    elif "uv" in extras:
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
            checks += rule6(
                row,
                index,
                dd[indices.index(index)],
                ap[k],
                ap60[k],
                reference.alpha_s,
                alphas(row, reference),
            )
    if "ff" in extras:
        legs, alpha_s = run.legs(), Decimal(str(run.parameters["aS"]))
        for index, point in zip(indices, dd, strict=True):
            if point is not None:
                checks += rule_ff(row, index, point, legs, reference, alpha_s)
    if "joint" in extras:
        start = time.perf_counter()
        for index in extra_points:
            point = dd[indices.index(index)]
            if point is not None:
                checks += rule_joint(row, run, index, point)
        timings["joint_s"] = round(time.perf_counter() - start, 2)
    if "ward" in extras:
        start = time.perf_counter()
        for index in extra_points:
            for carrier in ("double", "double-double"):
                found = rule_ward(row, index, carrier, run.ward(index, carrier))
                if "ward" in row.diagnostic_extras:
                    found = diagnostics(found)
                checks += found
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
    """Rows of one test module or CLI run: one compiled model per (model,
    restriction) and one ``RowRun`` per row, built on first use. ``ufo`` is
    loop_sm's; ``ufos`` the other models of the manifest (its ``models``
    section: the M-SM EW UFOs) by name."""

    def __init__(
        self,
        ufo: Path,
        native: Any,
        work: Path,
        manifest=None,
        ufos: Mapping[str, Path] | None = None,
    ):
        self.ufo, self.native, self.work = Path(ufo), native, Path(work)
        self.manifest = manifest or load_manifest()
        self.rows = rows(self.manifest)
        self.ufos = {
            "loop_sm": self.ufo,
            **{k: Path(v) for k, v in (ufos or {}).items()},
        }
        self._models: dict[tuple[str, str], Any] = {}
        self._runs: dict[str, RowRun | PublicRun] = {}
        # base row -> its public-route artifact and generation seconds
        self._public: dict[str, tuple[Path, float]] = {}

    def ufo_path(self, name: str) -> Path:
        """The UFO of model ``name``: a campaign input, or a copy of its
        ``base`` with a reference's restriction card (manifest ``models``:
        ``restriction_card_from``, e.g. the massive-muon G_mu copy MadLoop's
        control was generated with)."""

        if name in self.ufos:
            return self.ufos[name]
        spec = (self.manifest.get("models") or {}).get(name)
        if spec is None or "restriction_card_from" not in spec:
            raise KeyError(f"no UFO for model {name!r}")
        import hashlib
        import shutil

        data = json.loads((ROOT / spec["restriction_card_from"]).read_text())
        card = data["restriction_card_text"]
        if hashlib.sha256(card.encode()).hexdigest() != data["restriction_card_sha256"]:
            raise ValueError(f"{spec['restriction_card_from']}: card digest differs")
        target = self.work / f"ufo-{name}"
        if not target.is_dir():
            shutil.copytree(
                self.ufo_path(spec["base"]),
                target,
                ignore=shutil.ignore_patterns("__pycache__", "*.pkl"),
            )
            (target / "restrict_default.dat").write_text(card)
        self.ufos[name] = target
        return target

    def model(self, restriction: str, name: str = "loop_sm") -> Any:
        key = (name, restriction)
        if key not in self._models:
            if name == "loop_sm":
                self._models[key] = compile_restriction(
                    self.ufo, restriction, self.work / f"model-{restriction}"
                )
            else:
                from pyamplicol.models.loading import compile_model_source

                self._models[key] = compile_model_source(
                    self.ufo_path(name),
                    restriction=restriction,
                    require_supported=False,
                    cache_dir=self.work / f"model-{name}-{restriction}",
                )
        return self._models[key]

    def row_model(self, row: Row) -> Any:
        """The compiled model of ``row``: its (model, restriction), under the
        complex-mass scheme transformed at the row's fixed parameters that
        are the model's (``model_cms.complex_mass_model``, one per fixed
        set and reglog convention)."""

        compiled = self.model(row.restriction, row.model)
        if row.mass_scheme is None:
            return compiled
        if row.mass_scheme != "complex-mass":
            raise ValueError(f"{row.id}: unknown mass scheme {row.mass_scheme!r}")
        import hashlib

        from pyamplicol.loops.model_cms import complex_mass_model

        names = {
            record["name"]
            for record in compiled.raw_loop_model.collections["parameters"]
        }
        fixed = {k: v for k, v in sorted(row.fixed_parameters.items()) if k in names}
        convention = row.reglog_convention or "ufo-standard"
        key = (row.model, row.restriction, convention, json.dumps(fixed))
        if key not in self._models:
            tag = hashlib.sha256(json.dumps(key).encode()).hexdigest()[:12]
            self._models[key], _scheme = complex_mass_model(
                compiled,
                fixed_parameters=fixed,
                reglog_convention=convention,
                cache_dir=self.work / f"model-cms-{tag}",
            )
        return self._models[key]

    def run(self, name: str) -> RowRun | PublicRun:
        if name not in self._runs:
            row = self.rows[name]
            if not row.active:
                raise ValueError(f"{name} is {row.status}: {row.pending}")
            if row.route == "public":
                # One artifact per base row, its seconds on the first variant.
                first = row.base not in self._public
                if first:
                    self._public[row.base] = generate_public(
                        self.rows[row.base], self.work / f"public-{row.base}"
                    )
                artifact, seconds = self._public[row.base]
                self._runs[name] = PublicRun(
                    row,
                    artifact,
                    seconds if first else 0.0,
                    self.model(row.restriction, row.model),
                )
                return self._runs[name]
            base = None
            # A variant shares its base row's generation unless it is a
            # subprocess of it (M01), runs on another restriction (the
            # restricted-UFO variants of the 5F* rows) or tags other photons
            # (PI01's "all" twin) or another mass scheme or reglog convention
            # (CM01's source view).
            other = self.rows.get(row.base) if row.base is not None else None
            if (
                other is not None
                and other.active
                and not row.subprocess
                and (row.restriction, row.model, row.external_photons)
                == (other.restriction, other.model, other.external_photons)
                and (row.mass_scheme, row.reglog_convention)
                == (other.mass_scheme, other.reglog_convention)
            ):
                base = self.run(row.base)
            self._runs[name] = RowRun(
                row,
                self.row_model(row),
                self.native,
                base=base,
                ufo=self.ufo,
                work=self.work,
            )
            # The row's model UFO (the R2 rule's coupling classes).
            self._runs[name].model_ufo = self.ufo_path(row.model)
        return self._runs[name]

    def report(self, name: str, tier: str, points=None) -> RowReport:
        run = self.run(name)
        return run_row(run, tier, points=points)

    def record(self, name: str, tier: str, points=None) -> RowReport:
        """The row's report, or, when its generation or evaluation raises,
        a failed report holding the error (one "eval" check), so that the
        campaign records a crash as the row's failure, not as a missing
        record (the tiers and the CLI write it)."""

        try:
            return self.report(name, tier, points=points)
        except Exception as error:  # a crash is the row's record
            LOG.exception("%s: raised", name)
            row = self.rows[name]
            return RowReport(name, tier, tuple(points or row.tier_points(tier)), [
                Check("eval", None, "", "", "generation or evaluation", "raised",
                      "", math.inf, 0.0, False,
                      note=f"{type(error).__name__}: {error}")], {})  # fmt: skip


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
    data = next(r for r in campaign.manifest["rows"] if r["id"] == name)
    ir = campaign.model(row.restriction, row.model).ir
    catalog = ModelParticleCatalog(ir.name, ir.particles, ir.parameters)
    ours = expand_model_processes(
        row.process,
        catalog,
        multiparticles=data.get("multiparticles"),
        charges=conserved_charges(ir),
    )

    def key(process: str) -> tuple:
        """Initial and final PDG multisets (the model's own spelling of a
        name is case-insensitive: loop_sm's gluon is ``G``)."""

        initial, final = process.split(">")
        return tuple(
            tuple(sorted(int(catalog.resolve(n).pdg_code) for n in side.split()))
            for side in (initial, final)
        )

    # Members without a Born (manifest ``skipped_members``, m-sm Q2 (a)) are
    # skipped on our side; MadLoop exports the loop-squared ones as their
    # own P directories (``madloop_loop_squared``) and none for a member
    # with no amplitude at all: the members with a Born must agree.
    skipped = {key(process) for process in data.get("skipped_members", ())}
    loop_squared = set(data.get("madloop_loop_squared", ()))
    theirs = {
        key(process)
        for directory, processes in data["madloop_subprocesses"].items()
        if directory not in loop_squared
        for process in processes
    }
    found = {key(process) for process in ours} - skipped
    return [
        Check("multi", None, "", "", "subprocesses", ", ".join(sorted(ours)),
              ", ".join(sorted(p for ps in data["madloop_subprocesses"].values()
                               for p in ps)),
              0.0, 0.0, found == theirs,
              note=f"{len(found)} processes against MadLoop's "
              f"{len(data['madloop_subprocesses'])} P directories")
    ]  # fmt: skip


def public_card_text(
    row: Row,
    output: Path,
    *,
    multiparticles: Mapping[str, Sequence[str]] | None = None,
) -> str:
    """A public-route generation card of ``row`` on its shipped model (no
    ``[loop.model]``, no compatibility profile): its restriction and fixed
    parameters, corrections, the model's R2, the minimal Born orders and
    the request's ``process.multiparticles``."""

    fixed = ", ".join(f"{k} = {json.dumps(v)}" for k, v in row.fixed_parameters.items())
    restriction = (
        f"restriction = {json.dumps(row.restriction)}"
        if row.restriction != "default"
        else ""
    )
    aliases = "".join(
        f"{key} = {json.dumps(list(values))}\n"
        for key, values in (multiparticles or {}).items()
    )
    return f"""action = "generate"
[model]
source = {json.dumps(row.model)}
{restriction}
[process]
entries = [{{expression = {json.dumps(row.process)}, name = {json.dumps(row.id)}}}]
loop_coupling_orders = {json.dumps(list(row.corrections))}
coupling_order_policy = "minimal"
[process.multiparticles]
{aliases}[loop]
r2_strategy = "model"
[loop.preparation]
fixed_parameters = {{{fixed}}}
[generation]
output = {json.dumps(str(output))}
emit_api_bundle = false
[generation.validation]
post_build_validation = false
"""


def multiparticle_members(campaign: Campaign, name: str) -> list[Check]:
    """A multiparticle row's members on the public route's dry run (m-sm
    PLAN Q2 (a)): the members without a Born (manifest ``skipped_members``)
    are skipped with the typed ``loop-induced`` record, every other member of
    the expansion is planned."""

    from pyamplicol.api import Generator, ModelSource, ProcessRequest, ProcessSet
    from pyamplicol.config import resolve_config

    row = campaign.rows[name]
    # The dry run reads the configured model cache (a compiled shipped model).
    ModelSource.from_path(row.model, restriction=row.restriction).compile()
    data = next(r for r in campaign.manifest["rows"] if r["id"] == name)
    work = campaign.work / f"dry-run-{name}"
    work.mkdir(parents=True, exist_ok=True)
    card = work / "card.toml"
    card.write_text(
        public_card_text(row, work / "out", multiparticles=data.get("multiparticles"))
    )
    plan = Generator(resolve_config(card)).plan(
        ProcessSet((ProcessRequest.parse(row.process, name=row.id),), ())
    )
    coverage = plan.estimated_coverage
    skipped = coverage.get("skipped_members", ())
    found = sorted(" ".join(r["process"].split()) for r in skipped)
    typed = all(r.get("refusal") == "loop-induced" for r in skipped)
    want = sorted(data.get("skipped_members", ()))
    planned = sorted(" ".join(r["process"].split()) for r in coverage["processes"])
    loop_squared = set(data.get("madloop_loop_squared", ()))
    expansion = {
        p for d, ps in data["madloop_subprocesses"].items()
        if d not in loop_squared for p in ps
    }  # fmt: skip
    return [
        Check("multi", None, "", "", "skipped members", ", ".join(found) or "none",
              ", ".join(want) or "none", 0.0, 0.0,
              [p.casefold() for p in found] == [p.casefold() for p in want] and typed,
              note="members without a Born: the typed loop-induced record"),
        Check("multi", None, "", "", "planned members", str(len(planned)),
              str(len(expansion)), 0.0, 0.0,
              len(planned) == len(expansion)
              and not set(map(str.casefold, planned)) & set(map(str.casefold, found)),
              note="every member with a Born planned, the skipped ones not; "
              f"unsupported features: {list(plan.unsupported_features)}"),
    ]  # fmt: skip


SMOKE_TOLERANCE = 1e-14


# Rule 4's "tree" prediction against the Python-input executor's Catani:
# rows with the tree rows' colour structures (gluons only; one quark line).
TREE_ORACLE_ROWS = ("A01", "A09")
TREE_ORACLE_TOLERANCE = 1e-30


def tree_oracle(campaign: Campaign, names: Sequence[str] = TREE_ORACLE_ROWS):
    """The "tree" prediction (``RowRun.tree_catani``, the tree engine run
    here) against the Python-input executor's own Catani at point 0 in
    double-double, per sector and pole within ``TREE_ORACLE_TOLERANCE``
    (measured 1e-40), its Born against ours within 1e-24."""

    checks = []
    for name in names:
        run = campaign.run(name)
        (dd,) = run.evaluate([0], "double-double", stability=False)
        born, prediction = run.tree_catani(0)
        error = relative(dd.total()[0], born)
        checks.append(Check(
            "4", 0, "double-double", f"{name} {TOTAL}", "tree born",
            str(dd.total()[0]), str(born), error, DD_FLOOR, error <= DD_FLOOR,
            note="the tree engine's Born against ours"))  # fmt: skip
        if set(prediction) != set(dd.catani or ()):
            checks.append(Check(
                "4", 0, "double-double", name, "predicted sectors",
                str(sorted(prediction)), str(sorted(dd.catani or ())), math.inf,
                0.0, False, note="tree and executor sectors differ"))  # fmt: skip
            continue
        for sector, poles in prediction.items():
            for k, coefficient in enumerate(("single_pole", "double_pole")):
                error = relative(poles[k], dd.catani[sector][k])
                checks.append(Check(
                    "4", 0, "double-double", f"{name} {sector_text(sector)}",
                    coefficient, str(poles[k]), str(dd.catani[sector][k]), error,
                    TREE_ORACLE_TOLERANCE, error <= TREE_ORACLE_TOLERANCE,
                    note="tree prediction against the executor's Catani"))  # fmt: skip
    return checks


def smoke(campaign: Campaign, restriction: str, spec: Mapping[str, Any]) -> list[Check]:
    """A generation smoke (PLAN §3.2 MQ-VALIDATE item 5): the request of row
    ``spec['row']`` generated on ``restriction`` equals the row on its own
    restriction, binary64, at the first point of ``spec.get('points_from',
    row)``'s reference, within 1e-14 strictly relative per sector and
    coefficient (Born included)."""

    from pyamplicol.loops.v2.assemble import LoopSlice, Precision

    row = campaign.rows[spec["row"]]
    if spec.get("executor") == "native":
        # The M-SM smokes (m-sm/PLAN.md §3.2 MS-VALIDATE item 8): the row's
        # own generation and native executor against the request generated
        # on the restriction, both through the native executor (Python
        # inputs) at the row's first reference point.
        from tools.loop_v2_generate import _external_parameters

        base = campaign.run(row.id).evaluate([0], "double", stability=False)[0]
        model = campaign.model(restriction, row.model)
        base_model = campaign.model(row.restriction, row.model)
        externals = _external_parameters(model)
        # The base restriction's values of the parameters it removes and the
        # other keeps (``parameter_defaults`` None in the base, a value in the
        # other: e.g. MB = 0 under with_b_mass, the Wolfenstein parameters 0
        # under ckm), fixed as the base fixes them; and none the other
        # restricts away (a width of no_widths).
        kept = {
            k
            for k in externals
            if model.parameter_defaults.get(k) is not None
            and base_model.parameter_defaults.get(k) is None
        }
        card = restriction_card(campaign.ufo_path(row.model), row.restriction)
        restricted = replace(
            row,
            id=f"{row.id}~{restriction}",
            restriction=restriction,
            fixed_parameters={
                **{k: v for k, v in row.fixed_parameters.items() if k in externals},
                **{k: card[k] for k in sorted(kept) if k in card},
            },
        )
        run = RowRun(restricted, model, campaign.native)
        run.parameters = {k: v for k, v in run.parameters.items() if k in externals}
        # Every other runtime parameter the row leaves at its card's value
        # takes the base card's (the restrictions' cards differ: e.g. the
        # alpha(M_Z) UFO's MT, MH and aEWM1, with_technical's epsUV = 1 +
        # 1e-8); the scale is the point's.
        free = externals - set(run.parameters) - set(restricted.fixed_parameters)
        for k in sorted(free):
            if (
                k != row.scale_parameter
                and k in card
                and model.parameter_defaults.get(k) is not None
                and base_model.parameter_defaults.get(k) is not None
            ):
                run.parameters[k] = card[k]
        other = run.evaluate([0], "double", stability=False)[0]
        return _smoke_checks(base, other, restriction, row.restriction)
    source = campaign.rows[spec.get("points_from", row.id)]
    reference = load_reference(source)
    parameters = {**reference.parameters, **dict(source.parameters)}
    values = []
    for name in (row.restriction, restriction):
        slice_ = LoopSlice.generate(
            campaign.model(name, row.model), slice_request(row), campaign.native
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
    return _smoke_checks(base, other, restriction, row.restriction)


def restriction_card(ufo: Path, restriction: str) -> dict[str, str]:
    """Parameter name -> value of a UFO's ``restrict_<restriction>.dat``
    (an MG5 param card: ``<codes> <value> # <name>`` lines)."""

    import re

    pattern = re.compile(r"^\s*\d+(?:\s+\d+)*\s+([-+0-9.eE]+)\s*#\s*(\S+)")
    values = {}
    for line in (Path(ufo) / f"restrict_{restriction}.dat").read_text().splitlines():
        found = pattern.match(line)
        if found:
            values[found.group(2)] = format(Decimal(found.group(1)).normalize(), "f")
    return values


def _smoke_checks(
    base: Evaluated, other: Evaluated, restriction: str, own: str
) -> list[Check]:
    """The smoke's checks: the same sectors, every coefficient within
    ``SMOKE_TOLERANCE`` strictly relative."""

    same = set(other.virtual) == set(base.virtual) and set(other.born) == set(base.born)
    checks = [
        Check("smoke", 0, "double", "", "sectors",
              ", ".join(map(sector_text, sorted(other.virtual))),
              ", ".join(map(sector_text, sorted(base.virtual))), 0.0, 0.0,
              same, note=f"{restriction} against {own}")
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


def delegated_ids(manifest: Mapping[str, Any] | None = None) -> list[str]:
    """The pytest node ids of the delegated columns, once each in manifest
    order: every row's columns (``delegated``: rule 7's MQ-NC ids, M01's
    MQ-MODEL id), then the LC/NLC smoke on every shipped restriction when it
    names its test. Run them with ``--junitxml`` for ``build_mqcd.py
    --junit``."""

    manifest = manifest or load_manifest()
    ids = [
        node
        for row in rows(manifest).values()
        for column in row.delegated.values()
        for node in column
    ]
    smoke = manifest.get("smokes", {}).get("lc_every_restriction")
    if isinstance(smoke, Mapping):
        ids.append(smoke["test"])
    return list(dict.fromkeys(ids))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.loop_benchmark.mqcd")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "delegated-ids",
        help="print the delegated columns' pytest ids (MQ-NC's, MQ-MODEL's)",
    )
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
    run.add_argument(
        "--model-ufo",
        nargs="*",
        default=[],
        metavar="NAME=PATH",
        help="the UFO of a manifest model other than loop_sm (its ``models``)",
    )
    args = parser.parse_args(argv)
    if args.command == "delegated-ids":
        for node in delegated_ids():
            print(node)
        return 0
    logging.basicConfig(format="%(asctime)s %(message)s", level=logging.WARNING)
    LOG.setLevel(logging.INFO)

    from pyamplicol.loops.native import load_loop_native

    campaign = Campaign(
        args.ufo,
        load_loop_native(),
        args.work,
        manifest=load_manifest(args.manifest),
        ufos=dict(item.split("=", 1) for item in args.model_ufo),
    )
    failed = 0
    for name in args.rows:
        row = campaign.rows[name]
        if not row.active:
            print(f"{name}: pending ({row.pending})", flush=True)
            continue
        report = campaign.record(name, args.tier, points=args.points)
        print(report.describe(), flush=True)
        print(json.dumps(report.summary(), default=str), flush=True)
        write_result(report, args.results)
        failed += not report.passed
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
