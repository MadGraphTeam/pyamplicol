# SPDX-License-Identifier: 0BSD
"""Write tests/fixtures/loop/dec/manifest.json, the one-loop decay rows of
M-FINAL MF-DEC-2 (workspace/reports/engine-v2/m-final/PLAN.md §2.2).

Usage: python tools/loop_benchmark/dec_manifest.py

Rows XX01-XX08 against MadLoop's quadruple-precision references of MF-DEC-1
(``tests/fixtures/loop/required/dec/``, README there: MadLoop's conventions
for the decaying leg), in the record type of the M-QCD / M-SM manifests
(``tools/loop_benchmark/mqcd.py`` ``Row``; the campaign rules 1-4 of
m-sm/PLAN.md §1.4, lax precision). Everything a row states is read off its
reference (process, Born and loop orders, sectors, parameters, the scheme's
loop alpha, the R2 couplings MadLoop's export calls); this file adds the
model code, the tier and the extras. The tests are
``tests/unit/test_loop_v2_dec_default.py`` (default tier) and
``tests/unit/test_loop_v2_dec_nightly*.py`` (nightly jobs); with
``PYAMPLICOL_MQCD_RESULTS`` set they write the records of
``docs/performance_reports/loop/data/dec.json`` (``scripts/build_mqcd.py
RESULTS --manifest tests/fixtures/loop/dec/manifest.json --output
data/dec.json --junit`` the JUnit XML of
``tests/unit/test_loop_v2_dec_checks.py``, the delegated columns).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WT))

from tools.loop_benchmark import mqcd  # noqa: E402

DEC = "tests/fixtures/loop/required/dec"
OUT = WT / "tests/fixtures/loop/dec/manifest.json"

ZERO_WIDTHS = {"WT": "0", "WW": "0", "WZ": "0", "WH": "0"}
MASSLESS_B_TAU = {"MB": "0", "ymb": "0", "MTA": "0", "ymtau": "0"}
GMU, QCDQED, LOOPSM = "loop_qcd_qed_sm_Gmu", "loop_qcd_qed_sm", "loop_sm"
# Model codes (m-qcd / m-sm manifests): (model, restriction, fixed
# parameters, toolkit scheme). The decaying particle's own width is zero in
# every code (user ruling 2026-10-31 ~11:00).
CODES = {
    "5F": (LOOPSM, "no_b_mass", {**MASSLESS_B_TAU, **ZERO_WIDTHS}, "qcd"),
    "4F": (LOOPSM, "default", ZERO_WIDTHS, "qcd-4fs"),
    "G0": (GMU, "default", {**MASSLESS_B_TAU, **ZERO_WIDTHS}, "ew-gmu"),
    "Az": (QCDQED, "default", ZERO_WIDTHS, "ew-qcd-qed-sm"),
}
MODELS = {
    GMU: {"fixture": "loop_gmu_ufo"},
    QCDQED: {"fixture": "loop_qcd_qed_sm_ufo"},
}

# (id, reference, model code, tier, extras, features). Extras the harness
# checks on the nightly tier (``mqcd.IMPLEMENTED_EXTRAS``): ``uv`` (rule 5,
# the bare loop's UV poles against the counterterms and the field factors of
# every external leg, the incoming one included), ``ap`` (rule 6), ``ward``
# (O10 on the external gluon). LC/NLC (XX01, XX07) and the analytic form
# factor of z > u u~ [QCD] are tests/unit/test_loop_v2_dec_checks.py's.
ROWS = (
    ("XX01", "t_bwp_qcd", "5F", "default", ("uv", "ap"), ("1->2", "massive:top", "external:W")),
    ("XX02", "t_bwp_ew", "G0", "nightly", (), ("1->2", "massive:top", "external:W", "joint")),
    ("XX03", "z_emep_ew", "Az", "nightly", (), ("1->2", "external:Z", "leptons-only")),
    ("XX04", "z_uux_ew", "Az", "nightly", (), ("1->2", "external:Z", "joint")),
    ("XX05", "wp_epve_ew", "Az", "nightly", (), ("1->2", "external:W", "charged-initial")),
    ("XX06", "h_bbx_4fs", "4F", "nightly", ("uv",), ("1->2", "higgs", "massive:b")),
    ("XX07", "t_bwpg_qcd", "5F", "nightly", ("uv", "ward"), ("1->3", "massive:top", "external:W")),
    ("XX08", "z_uuxg_ew", "Az", "nightly", (), ("1->3", "external:Z", "joint")),
)  # fmt: skip
CLASS = {"5F": "D-QCD", "4F": "D-QCD", "G0": "D-EW", "Az": "D-EW"}
# The public route (``Generator`` on the shipped loop_sm, a stored artifact
# evaluated through ``Runtime.evaluate`` with the O1 checks: one exact
# rotation and the reduction direction) of the loop_sm rows, at the base
# row's reference points (no Catani prediction on that route: the base row
# holds rule 4).
PUBLIC = ("XX01", "XX07")
# Rows on the production native-input route (the plan's tree program, as a
# stored artifact runs it; rule 4 from the engine's operators on the
# Python-input Born, ``RowRun.engine_catani``): one electroweak decay.
NATIVE_INPUTS = ("XX02",)

# The nightly file jobs (each within the campaigns' 30-minute budget):
# measured wall seconds per row (generation, export, its points in both
# carriers and its extras, plus imports and model compilation;
# workspace/tmp/mf-dec-2, 2026-11-01).
MEASURED_SECONDS = {
    "XX01": 70, "XX02": 190, "XX03": 110, "XX04": 110, "XX05": 120,
    "XX06": 70, "XX07": 80, "XX08": 130, "XX01@public": 70, "XX07@public": 75,
}  # fmt: skip
DEFAULT_SECONDS = 300
# Delegated columns (``build_mqcd.py --junit``): the checks of
# tests/unit/test_loop_v2_dec_checks.py (LC/NLC of the loop_sm QCD decays
# against the N_c scan; the analytic form factor of z > u u~ [QCD]).
_CHECKS = "tests/unit/test_loop_v2_dec_checks.py::"
DELEGATED = {
    "XX01": {"nc": [
        f"{_CHECKS}test_decay_lc_and_nlc_are_the_kept_powers_of_the_nc_scan[XX01]",
        f"{_CHECKS}test_decay_lc_and_nlc_at_the_nightly_points[XX01]",
    ]},
    "XX04": {"ff": [f"{_CHECKS}test_z_to_u_ubar_qcd_is_the_massless_quark_form_factor"]},
    "XX07": {"nc": [
        f"{_CHECKS}test_decay_lc_and_nlc_are_the_kept_powers_of_the_nc_scan[XX07]",
    ]},
}  # fmt: skip
JOB_SECONDS = 1500


def _sector(entry) -> tuple[int, int]:
    return int(entry.get("QCD", 0)), int(entry.get("QED", 0))


def _orders(pair) -> dict[str, int]:
    return {"QCD": pair[0], "QED": pair[1]}


def _loop_alpha(data, code) -> float | None:
    """The QED loop coupling of the reference's scheme (F_s): the G_mu
    scheme's derived alpha, else 1 / aEWM1 at the reference's card."""

    if code == "G0":
        return float(data["derived_parameters"]["alpha"])
    if "aEWM1" in data["parameters"]:
        return 1 / float(data["parameters"]["aEWM1"])
    return None


def build_row(id_, name, code, tier, extras, features) -> dict:
    model, restriction, fixed, scheme = CODES[code]
    path = f"{DEC}/{name}.json"
    data = json.loads((WT / path).read_text())
    process = " ".join(
        t for t in data["process"].split("[")[0].split() if "=" not in t
    )
    born = _sector(data["born_orders"])
    loop = _sector(data["loop_orders"])
    corrections = list(data.get("corrections") or [data["correction"]])
    corrections = ["QED" if c == "EW" else c for c in corrections]
    sectors = sorted(
        {_sector(x) for x in data["squared_split_orders"]["loop"]}, reverse=True
    )
    loops = sorted(
        {(s[0] - born[0], s[1] - born[1]) for s in sectors}, reverse=True
    )
    count = len(data["points"])
    points = (
        {"default": [0, 1], "nightly": list(range(2, count))}
        if tier == "default"
        else {tier: list(range(count))}
    )
    entry = {
        "id": id_,
        "class": CLASS[code],
        "process": process,
        "born_orders": _orders(born),
        "born_amplitude_orders": [_orders(born)],
        "loop_orders": _orders(loops[0])
        if len(loops) == 1
        else [_orders(x) for x in loops],
        "corrections": corrections,
        "model": model,
        "restriction": restriction,
        "restriction_code": code,
        "fixed_parameters": dict(fixed),
        "gauge": "feynman" if model != LOOPSM else "unitary",
        "scheme": scheme,
        "tier": tier,
        "status": "active",
        "reference_legend": f"E {path} (MF-DEC-1, MadLoop QP)",
        "reference": {"format": "required", "path": path, "providers": ["madloop"]},
        "points": points,
        "extras": list(extras),
        "features": list(features),
        "sectors": [_orders(s) for s in sectors],
        "predicted_sectors": [_orders(s) for s in sectors],
        "unpredicted_sectors": [],
        "unpredicted_reasons": {},
        "reference_outliers": [],
        "vanishing": [],
        "reference_tolerance": mqcd.REFERENCE_TOLERANCE,
        "alphas": {"QED": _loop_alpha(data, code)} if "QED" in corrections else {},
    }
    if model != LOOPSM:
        entry["compatibility"] = "gmu_particle_anti"
        entry["scale_parameter"] = "MU_R"
    ignored = sorted(set(data.get("fixed_parameters", {})) - set(fixed) - {"MB", "ymb", "MTA", "ymtau"})
    ignored = [k for k in ignored if k == "WTau"]
    if ignored:
        # The providers' WTau: the G_mu and alpha(M_Z) UFOs have none.
        entry["ignored_fixed_parameters"] = ignored
    if id_ in NATIVE_INPUTS:
        entry["inputs"], entry["catani"] = "native", "engine"
    if id_ in DELEGATED:
        entry["delegated"] = DELEGATED[id_]
    if id_ in PUBLIC:
        entry["variants"] = [{
            "name": "public",
            "gating": True,
            "tier": "nightly",
            "notes": "the public route: Generator on the shipped loop_sm, "
            "Runtime.evaluate of the stored artifact with the O1 checks",
            # The reference points at mu_R = M (the public route takes
            # decimal mu_R^2; the M/2 copy's is a fraction).
            "points": {"nightly": [
                k for k, mu in enumerate(data["mu_r"]) if "." not in str(mu)
            ]},
            "extras": [],
            "route": "public",
            "catani": "none",
        }]  # fmt: skip
    called = (data.get("madloop_r2_couplings") or {}).get("called")
    if called is not None:
        entry["madloop_r2_called"] = sorted(called)
    return entry


def nightly_jobs(rows) -> dict:
    """Rows packed into file jobs of at most JOB_SECONDS (first fit,
    largest first)."""

    ids = mqcd.nightly_ids({"rows": rows})
    cost = {i: MEASURED_SECONDS.get(i, DEFAULT_SECONDS) for i in ids}
    jobs: list[dict] = []
    for name in sorted(ids, key=lambda i: (-cost[i], i)):
        for job in jobs:
            if job["seconds"] + cost[name] <= JOB_SECONDS:
                job["rows"].append(name)
                job["seconds"] += cost[name]
                break
        else:
            jobs.append({"seconds": cost[name], "rows": [name]})
    out = []
    for k, job in enumerate(jobs, 1):
        suffix = "" if k == 1 else f"_{k}"
        out.append({
            "job": k,
            "seconds": job["seconds"],
            "rows": sorted(job["rows"]),
            "file": f"tests/unit/test_loop_v2_dec_nightly{suffix}.py",
        })  # fmt: skip
    return {
        "budget_seconds": JOB_SECONDS,
        "measurement": "MEASURED_SECONDS per id, DEFAULT_SECONDS without one",
        "jobs": out,
    }


def manifest() -> dict:
    rows = [build_row(*spec) for spec in ROWS]
    return {
        "schema_version": 1,
        "plan": "workspace/reports/engine-v2/m-final/PLAN.md §2.2 MF-DEC-2 "
        "(rows XX01-XX08), campaign rules of m-sm/PLAN.md §1.4",
        "description": "One-loop 1 -> 2 and 1 -> 3 decays, QCD and EW, against "
        "MadLoop's quadruple-precision references (tests/fixtures/loop/"
        "required/dec/README.md: zero own width of the decaying particle, "
        "amputated loops, its absorptive self-energy dropped). tools/"
        "loop_benchmark/mqcd.py reads it; tests/unit/test_loop_v2_dec_*.py "
        "run it.",
        "models": MODELS,
        "restriction_codes": {
            code: {
                "model": model,
                "restriction": restriction,
                "fixed_parameters": fixed,
                "scheme": scheme,
            }
            for code, (model, restriction, fixed, scheme) in CODES.items()
        },
        "classes": sorted(set(CLASS.values())),
        "features": sorted({f for spec in ROWS for f in spec[5]}),
        "nightly_jobs": nightly_jobs(rows),
        "rows": rows,
    }


def main() -> int:
    data = manifest()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1) + "\n")
    print(f"wrote {OUT.relative_to(WT)}: {len(data['rows'])} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
