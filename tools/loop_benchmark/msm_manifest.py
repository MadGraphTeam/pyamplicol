# SPDX-License-Identifier: 0BSD
# The row table quotes m-sm/PLAN.md §4.2's processes and legends.
# ruff: noqa: E501
"""Write tests/fixtures/loop/msm/manifest.json, the M-SM campaign rows.

Usage: python tools/loop_benchmark/msm_manifest.py

The rows are m-sm/PLAN.md §4.2's 70 core rows (``row(...)`` below: process,
corrections, model code, squared sectors, Born amplitude orders, reference
legend, extras, the package a pending row waits for), written in the record
type of the M-QCD manifest (``tools/loop_benchmark/mqcd.py`` ``Row``; the
harness ``mqcd.py``, the tier bodies ``tests/unit/loop_mqcd_tiers.py`` and the
report data ``docs/performance_reports/loop/scripts/build_mqcd.py`` read
both manifests). Each record adds what an EW row needs: the model and its
restriction (§4.1 model codes), the corrections, the loop amplitude orders
derived from the sectors and the Born amplitude orders, the loop coupling per
correction (F_s), the expected predicted and unpredicted sectors with their
typed reasons, the R2 rule's ``madloop_omitted_r2`` and the package
dependency of a pending row (never an xfail). Re-run it when MS-REF or an
unblocking package lands; the manifest is the committed source the tests
read.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WT))

from tools.loop_benchmark import mqcd  # noqa: E402

REQ = "tests/fixtures/loop/required"
FIX = "tests/fixtures/loop"
OUT = WT / "tests/fixtures/loop/msm/manifest.json"
WORKSPACE = Path(
    os.environ.get(
        "PYAMPLICOL_LOOP_WORKSPACE", "/shared/vhirschi/t3code/pyamplicol/workspace"
    )
)

ZERO_WIDTHS = {"WT": "0", "WW": "0", "WZ": "0", "WH": "0"}
G_MU_FIXED = {"MB": "0", "ymb": "0", "MTA": "0", "ymtau": "0", **ZERO_WIDTHS}
GMU, QCDQED, LOOPSM = "loop_qcd_qed_sm_Gmu", "loop_qcd_qed_sm", "loop_sm"
MASSIVE_MUON = "loop_qcd_qed_sm_Gmu_massive_muon"
# alpha_Gmu at the G_mu card (Gf, MW = 80.419, MZ = 91.188; the required
# fixtures' derived alpha) and alpha(M_Z) of loop_qcd_qed_sm's default card
# (aEWM1 = 132.507): the loop coupling of the QED correction (F_s).
ALPHA_GMU = 0.00754677226134035151919702202521
ALPHA_MZ = 1 / 132.507
# m-sm/PLAN.md §4.1 model codes: (model, restriction, fixed parameters,
# toolkit scheme, QED loop alpha).
CODES = {
    "G0": (GMU, "default", G_MU_FIXED, "ew-gmu", ALPHA_GMU),
    "Ga": (GMU, "a0", G_MU_FIXED, "ew-gmu-a0", ALPHA_GMU),
    "Gb": (
        GMU,
        "with_b_mass",
        {"MTA": "0", "ymtau": "0", **ZERO_WIDTHS},
        "ew-gmu-b-mass",
        ALPHA_GMU,
    ),
    "Gm": (MASSIVE_MUON, "default", ZERO_WIDTHS, "ew-gmu-mm", ALPHA_GMU),
    "Gk": (GMU, "ckm", G_MU_FIXED, "ew-gmu-ckm", ALPHA_GMU),
    "Gt": (GMU, "with_technical", ZERO_WIDTHS, "ew-gmu-tech", ALPHA_GMU),
    "Gc": (
        GMU,
        "default",
        {"MB": "0", "ymb": "0", "MTA": "0", "ymtau": "0"},
        "ew-gmu-cms",
        ALPHA_GMU,
    ),
    "Gca": (
        GMU,
        "a0",
        {"MB": "0", "ymb": "0", "MTA": "0", "ymtau": "0"},
        "ew-gmu-a0-cms",
        ALPHA_GMU,
    ),
    "Lc": (LOOPSM, "default", {"WW": "0", "WZ": "0", "WH": "0"}, "qcd-cms", ALPHA_MZ),
    "Az": (QCDQED, "default", ZERO_WIDTHS, "ew-qcd-qed-sm", ALPHA_MZ),
    "L5": (LOOPSM, "default", G_MU_FIXED, "qcd", ALPHA_MZ),
}
MODELS = {
    GMU: {"fixture": "loop_gmu_ufo"},
    QCDQED: {"fixture": "loop_qcd_qed_sm_ufo"},
    MASSIVE_MUON: {
        "base": GMU,
        "restriction_card_from": f"{FIX}/electroweak-massive-mumu-control.json",
    },
}
CLASS = {
    "LL": "W-lep", "DY": "W-DY", "VJ": "W-V", "VV": "W-V", "V3": "W-V",
    "VH": "W-V", "TT": "W-top", "TV": "W-top", "ST": "W-singletop",
    "JJ": "W-jets", "PI": "W-photon", "CM": "W-CMS", "MP": "W-multi",
    "SC": "W-scheme",
}  # fmt: skip
# Packages a pending row waits for (m-sm/PLAN.md §3.0).
UNBLOCKERS = (
    "MS-REF",
    "EWI-7",
    "MS-PHOTON",
    "MS-CMS",
    "MS-CMS-N",
    "MS-MODEL",
    "MS-VALIDATE",
)
# The G_mu inputs of the MadLoop electroweak controls (their ``parameters``,
# as ``test_loop_v2_ew_leptons.CONTROL_PARAMETERS``).
CONTROL_PARAMETERS = {
    "Gf": "0.0000116639",
    "MW": "80.419",
    "MZ": "91.188",
    "MH": "125",
    "MT": "173.3",
    "ymt": "173.3",
    "aS": "0.118",
}
CONTROL_POINTS = "tools/loop_reference/uudd_qcd.json"
ALPHA0_INVERSE = "137.035999"

R = []


def row(id_, process, corr, code, sectors, born, legend, ref=None, extras=(),
        features=(), waits=None, tier="nightly", notes="", **more):  # fmt: skip
    R.append(dict(id=id_, process=process, corr=tuple(corr.split()), code=code,
                  sectors=[tuple(s) for s in sectors], born=[tuple(b) for b in born],
                  legend=legend, ref=ref, extras=list(extras), features=list(features),
                  waits=waits, tier=tier, notes=notes, more=more))  # fmt: skip


def req(name, providers=None, **spec):
    data = json.loads((WT / REQ / f"{name}.json").read_text())
    names = list(data["rows"][0]["providers"])
    primary = data.get("primary_provider", names[0])
    return {
        "format": "required",
        "path": f"{REQ}/{name}.json",
        "providers": providers or [primary] + [p for p in names if p != primary],
        **spec,
    }


def photons(tagged, sector=None):
    """MG5_aMC's alpha(0) conversion of the raw MadLoop G_mu reference over
    ``tagged`` final-state photons (Q1 (a): final photons tagged)."""

    spec = {"tagged": tagged, "alpha0_inverse": ALPHA0_INVERSE,
            "parameters": f"{FIX}/madloop-ct-parameters.json", "model": "gmu",
            "counterterm": "eCoup_DGmua0_UV_EW"}  # fmt: skip
    if sector:
        spec["sector"] = {"QCD": sector[0], "QED": sector[1]}
    return spec


N = "N"  # a new MadLoop job (MS-REF)
# Packages integrated on the slice: a row stops waiting for them (EWI-7,
# ew-validate, integrated at 753120c3 with its fixtures ttx_ttx_ew,
# ttx_zh_ew, udx_tbx_ew).
LANDED = {"EWI-7"}


# ---- LL: lepton-only
row(
    "LL01",
    "e- e+ > m- m+",
    "QED",
    "G0",
    [(0, 6)],
    [(0, 2)],
    "E electroweak-mumu-control.json (+ scale control)",
    {
        "format": "ew-control",
        "path": f"{FIX}/electroweak-mumu-control.json",
        "points_path": CONTROL_POINTS,
        "mu_r2": "1000000",
        "parameters": CONTROL_PARAMETERS,
    },
    ["ap", "uv"],
    ["2->2", "leptons-only", "two-lepton-lines"],
)
row(
    "LL02",
    "e- e+ > m- m+",
    "QED",
    "Gm",
    [(0, 6)],
    [(0, 2)],
    "E electroweak-massive-mumu-control.json",
    {
        "format": "ew-control",
        "path": f"{FIX}/electroweak-massive-mumu-control.json",
        "mu_r2": "1000000",
        "parameters": {**CONTROL_PARAMETERS, "MM": "0.105658", "ymm": "0.105658"},
    },
    [],
    ["2->2", "massive:muon"],
)
row(
    "LL03",
    "e- e+ > e- e+",
    "QED",
    "Az",
    [(0, 6)],
    [(0, 2)],
    "E required/emep_emep_ew.json",
    req("emep_emep_ew"),
    [],
    ["2->2", "lepton-line-through-loop", "scheme:alpha-mz"],
)
row(
    "LL05",
    "e- e+ > w+ w-",
    "QED",
    "G0",
    [(0, 6)],
    [(0, 2)],
    "N ~2 min",
    None,
    [],
    ["2->2", "internal-W"],
    waits=("MS-REF", "EWI-7"),
)
row(
    "LL08",
    "e- e+ > m- m+ a",
    "QED",
    "Ga",
    [(0, 8)],
    [(0, 3)],
    "N ~3-5 min",
    None,
    ["a0"],
    ["2->3", "photon:final"],
    waits="MS-REF",
)
row(
    "LL09",
    "e- e+ > t t~",
    "QCD QED",
    "G0",
    [(0, 6), (2, 4)],
    [(0, 2)],
    "N ~1-2 min",
    None,
    [],
    ["2->2", "massive:top"],
    waits="MS-REF",
)
row(
    "LL10",
    "e- e+ > t t~ h",
    "QED",
    "G0",
    [(0, 8)],
    [(0, 3)],
    "E required/emep_ttxh_ew.json (Recola primary: R2 rule)",
    req("emep_ttxh_ew", ["recola", "madloop"]),
    [],
    ["2->3", "r2-rule", "massive:top"],
)
# ---- DY: Drell-Yan and lepton-quark
row(
    "DY01",
    "u u~ > e- e+",
    "QCD QED",
    "G0",
    [(2, 4), (0, 6)],
    [(0, 2)],
    "N ~1 min",
    None,
    ["uv", "hel", "sp"],
    ["2->2"],
    waits="MS-REF",
)
row(
    "DY02",
    "u d~ > e+ ve",
    "QCD QED",
    "G0",
    [(2, 4), (0, 6)],
    [(0, 2)],
    "N ~1 min",
    None,
    [],
    ["2->2", "charged-current"],
    waits=("MS-REF", "EWI-7"),
)
row(
    "DY03",
    "u u~ > e- e+",
    "QED",
    "Az",
    [(0, 6)],
    [(0, 2)],
    "N ~1 min",
    None,
    [],
    ["2->2", "scheme:alpha-mz"],
    waits="MS-REF",
)
row(
    "DY04",
    "e- u > e- u",
    "QCD QED",
    "G0",
    [(2, 4), (0, 6)],
    [(0, 2)],
    "N ~1 min",
    None,
    [],
    ["2->2", "lepton-hadron"],
    waits="MS-REF",
)
row(
    "DY05",
    "u u~ > e- e+ g",
    "QCD QED",
    "G0",
    [(2, 6)],
    [(1, 2)],
    "E required/uux_emepg_ew.json (3 providers, s^2e^6) + N top-up s^4e^4 ~3 min",
    req("uux_emepg_ew"),
    ["ward", "joint", "ap", "nc"],
    ["2->3", "initial:qqbar"],
    notes="the s^2e^6 sector of the existing reference; the s^4e^4 top-up (MS-REF) extends the request to both sectors",
)
row(
    "DY07",
    "u u~ > e- e+ m- m+",
    "QED",
    "G0",
    [(0, 10)],
    [(0, 4)],
    "N ~8-15 min",
    None,
    [],
    ["2->4", "two-lepton-lines"],
    waits="MS-REF",
    notes="the 2->4 cost probe (m-sm/PLAN.md §3.2 item 3): generation 255 s, native export 95 s, peak 11.2 GB (tmp/ms-validate/probe/dy07, 2026-10-29): nightly",
)
row(
    "DY08",
    "u u~ > e- e+ g g",
    "QCD QED",
    "G0",
    [(6, 4), (4, 6)],
    [(2, 2)],
    "N ~8-15 min",
    None,
    ["nc"],
    ["2->4"],
    waits="MS-REF",
)
# ---- VJ, VV, V3, VH: vector bosons
row(
    "VJ01",
    "u u~ > z g",
    "QCD QED",
    "G0",
    [(4, 2), (2, 4)],
    [(1, 1)],
    "N ~1 min",
    None,
    ["ward"],
    ["2->2", "external:Z"],
    waits="MS-REF",
)
row(
    "VJ02",
    "u d~ > w+ g",
    "QCD QED",
    "G0",
    [(4, 2), (2, 4)],
    [(1, 1)],
    "N ~1 min",
    None,
    ["uv"],
    ["2->2", "external:W"],
    waits="MS-REF",
    tier="default",
)
row(
    "VJ03",
    "u u~ > a g",
    "QCD QED",
    "Ga",
    [(2, 4)],
    [(1, 1)],
    "E uux_ag_ew (s^2e^4) + N top-up ~1 min",
    req("uux_ag_ew", photon_conversion=photons(1)),
    ["a0", "ward"],
    ["2->2", "photon:final"],
    parameters={"aEW0M1": ALPHA0_INVERSE},
    notes="raw MadLoop G_mu x MG5_aMC's alpha(0) formula over the tagged final photon (Q1 (a)); the s^4e^2 top-up (MS-REF) extends the request",
)
row(
    "VV01",
    "u u~ > w+ w-",
    "QCD QED",
    "G0",
    [(2, 4), (0, 6)],
    [(0, 2)],
    "N ~2 min",
    None,
    ["sp"],
    ["2->2", "internal-W"],
    waits=("MS-REF", "EWI-7"),
)
row(
    "VV02",
    "u u~ > z z",
    "QCD QED",
    "G0",
    [(2, 4), (0, 6)],
    [(0, 2)],
    "N ~2 min",
    None,
    ["hel"],
    ["2->2"],
    waits="MS-REF",
)
row(
    "VV03",
    "u d~ > w+ z",
    "QCD QED",
    "G0",
    [(2, 4), (0, 6)],
    [(0, 2)],
    "N ~2 min",
    None,
    [],
    ["2->2", "internal-W"],
    waits=("MS-REF", "EWI-7"),
)
row(
    "VV05",
    "u d~ > w+ a",
    "QCD QED",
    "Ga",
    [(2, 4), (0, 6)],
    [(0, 2)],
    "N, S ~2 min",
    None,
    ["a0", "ward", "sp"],
    ["2->2", "photon:final", "radiation-zero"],
    waits="MS-REF",
)
row(
    "VV06",
    "u u~ > a a",
    "QCD QED",
    "Ga",
    [(0, 6)],
    [(0, 2)],
    "E uux_aa_ew (e^6) + N top-up ~1 min",
    req("uux_aa_ew", photon_conversion=photons(2)),
    ["a0"],
    ["2->2", "photon:final"],
    parameters={"aEW0M1": ALPHA0_INVERSE},
    notes="raw MadLoop G_mu x MG5_aMC's alpha(0) formula over the two tagged final photons (Q1 (a)); the s^2e^4 top-up (MS-REF) extends the request",
)
row(
    "VV07",
    "u u~ > w+ w- g",
    "QCD QED",
    "G0",
    [(4, 4), (2, 6)],
    [(1, 2)],
    "N ~5 min",
    None,
    ["ward"],
    ["2->3", "internal-W"],
    waits=("MS-REF", "EWI-7"),
)
row(
    "V301",
    "u u~ > w+ w- z",
    "QED",
    "G0",
    [(0, 8)],
    [(0, 3)],
    "N ~10-15 min",
    None,
    [],
    ["2->3", "internal-W"],
    waits=("MS-REF", "EWI-7"),
)
row(
    "VH01",
    "u u~ > z h",
    "QCD QED",
    "G0",
    [(2, 4), (0, 6)],
    [(0, 2)],
    "N ~1-2 min",
    None,
    [],
    ["2->2", "higgs"],
    waits="MS-REF",
)
row(
    "VH02",
    "u d~ > w+ h",
    "QCD QED",
    "G0",
    [(2, 4), (0, 6)],
    [(0, 2)],
    "N ~1-2 min",
    None,
    [],
    ["2->2", "higgs"],
    waits="MS-REF",
)
row(
    "VH03",
    "u d > u d h QCD=0",
    "QCD QED",
    "G0",
    [(2, 6), (0, 8)],
    [(0, 3)],
    "N ~3 min",
    None,
    [],
    ["2->3", "vbf", "capped"],
    waits="MS-REF",
    notes="capped (QCD = 0): typed unpredicted sectors are allowed",
)
# ---- TT, TV, ST: top quarks
row(
    "TT01",
    "g g > t t~",
    "QCD QED",
    "G0",
    [(6, 0), (4, 2)],
    [(2, 0)],
    "E required/gg_ttx + gg_ttx_ew (3 providers)",
    {
        "format": "sectors",
        "parameters_from": 1,
        "parts": [
            {
                "path": f"{REQ}/gg_ttx.json",
                "sector": {"QCD": 6},
                "born_sector": {"QCD": 4},
            },
            {
                "path": f"{REQ}/gg_ttx_ew.json",
                "sector": {"QCD": 4, "QED": 2},
                "born_sector": {"QCD": 4},
            },
        ],
        "providers": ["madloop", "recola", "openloops"],
    },
    ["joint", "ap", "uv"],
    ["2->2", "massive:top", "joint"],
    notes="joint QCD + QED request; s^6 against loop_sm's QCD fixture (pure QCD, independent of the EW inputs), s^4e^2 against the G_mu fixture",
)
row(
    "TT02",
    "u u~ > t t~",
    "QCD QED",
    "G0",
    [(6, 0), (4, 2), (2, 4), (0, 6)],
    [(2, 0), (0, 2)],
    "N ~1-2 min",
    None,
    ["so"],
    ["2->2", "massive:top", "mixed-born"],
    waits="MS-REF",
)
row(
    "TT03",
    "g g > t t~ g",
    "QCD QED",
    "G0",
    [(8, 0), (6, 2)],
    [(3, 0)],
    "N ~4-6 min",
    None,
    ["ward"],
    ["2->3", "massive:top"],
    waits="MS-REF",
)
row(
    "TT04",
    "t t~ > t t~ QCD=0",
    "QCD QED",
    "G0",
    [(0, 6)],
    [(0, 2)],
    "E required/ttx_ttx_ew (ew-validate; Recola primary: R2 rule, 7.7 %)",
    req("ttx_ttx_ew", ["recola", "madloop"]),
    [],
    ["2->2", "root-mixing", "r2-rule"],
    waits="EWI-7",
)
row(
    "TT05",
    "g t > t t t~",
    "QCD QED",
    "G0",
    [(2, 6)],
    [(1, 2)],
    "E gt_tttx_ew (goldstone-mixing.json, MadLoop double) + its omitted R2_G0tt_b component",
    {
        "format": "madloop-components",
        "path": f"{FIX}/goldstone-mixing.json",
        "key": "gt_tttx_ew",
    },
    ["uv"],
    ["2->3", "massive:top", "r2-rule", "goldstone-vector-mixing"],
)
row(
    "TT06",
    "g b > t t~ b",
    "QCD QED",
    "Gb",
    [(2, 6)],
    [(1, 2)],
    "E goldstone-mixing.json (gb_ttxb_ew_mb, MadLoop double)",
    {
        "format": "madloop-components",
        "path": f"{FIX}/goldstone-mixing.json",
        "key": "gb_ttxb_ew_mb",
    },
    [],
    ["2->3", "massive:b"],
    waits="EWI-7",
)
row(
    "TV01",
    "g g > t t~ h",
    "QCD QED",
    "G0",
    [(6, 2), (4, 4)],
    [(2, 1)],
    "N ~8-12 min",
    None,
    [],
    ["2->3", "higgs"],
    waits="MS-REF",
)
row(
    "TV02",
    "g g > t t~ z",
    "QCD QED",
    "G0",
    [(6, 2), (4, 4)],
    [(2, 1)],
    "N ~8-12 min",
    None,
    [],
    ["2->3", "external:Z"],
    waits="MS-REF",
)
row(
    "TV03",
    "u d~ > t t~ w+",
    "QCD QED",
    "G0",
    [(6, 2), (4, 4), (2, 6)],
    [(2, 1), (0, 3)],
    "N ~4-6 min",
    None,
    ["so"],
    ["2->3", "mixed-born"],
    waits="MS-REF",
)
row(
    "TV06",
    "g g > t t~ e- e+",
    "QCD QED",
    "G0",
    [(4, 6)],
    [(2, 2)],
    "E required/gg_ttxemep_ew (3 providers)",
    req("gg_ttxemep_ew"),
    [],
    ["2->4", "massive:top"],
)
row(
    "TV07",
    "g g > t t~ e- e+ g",
    "QCD QED",
    "G0",
    [(6, 6), (8, 4)],
    [(3, 2)],
    "E required/gg_ttxemepg_ew (3 providers) + gg_ttxemepg_qcd",
    req(
        "gg_ttxemepg_ew",
        sector={"QCD": 6, "QED": 6},
        born_sector={"QCD": 6, "QED": 4},
        sectors_subset=True,
    ),
    ["ward", "joint"],
    ["2->5", "massive:top", "target"],
    tier="campaign",
    inputs="native",
    catani="engine",
    notes="the required 2->5 target (EWI-9): the joint request's s^6e^6 sector against gg_ttxemepg_ew, its s^8e^4 sector (variant @qcd) against gg_ttxemepg_qcd at loop_sm's derived MW",
    variants=[
        {
            "name": "qcd",
            "gating": True,
            "tier": "campaign",
            "notes": "the joint twin: the s^8e^4 sector against gg_ttxemepg_qcd (loop_sm, MW derived from aEWM1 = 132.507: the G_mu inputs at that MW give the same alpha)",
            "reference": req(
                "gg_ttxemepg_qcd",
                sector={"QCD": 8, "QED": 4},
                born_sector={"QCD": 6, "QED": 4},
                sectors_subset=True,
            ),
            "parameters": {"MW": "80.4190024457561601055171371731"},
            "ignored_parameters": ["aEWM1"],
            "extras": [],
            "extras_pending": {},
        }
    ],
)
row(
    "ST01",
    "u b > d t",
    "QCD QED",
    "G0",
    [(2, 4), (0, 6)],
    [(0, 2)],
    "N ~1 min",
    None,
    [],
    ["2->2", "single-top"],
    waits="MS-REF",
)
row(
    "ST02",
    "u d~ > t b~ QCD=0",
    "QED",
    "G0",
    [(0, 6)],
    [(0, 2)],
    "E required/udx_tbx_ew (ew-validate; MadLoop + Recola)",
    req("udx_tbx_ew"),
    [],
    ["2->2", "single-top"],
    waits="EWI-7",
)
row(
    "ST03",
    "g b > t w-",
    "QCD QED",
    "G0",
    [(4, 2), (2, 4)],
    [(1, 1)],
    "N ~1-2 min",
    None,
    ["ward"],
    ["2->2", "single-top"],
    waits="MS-REF",
)
row(
    "ST04",
    "u d~ > t b~ QCD=0",
    "QED",
    "Gb",
    [(0, 6)],
    [(0, 2)],
    "R commit ew-validate's workspace run udx_tbx_ew_mb (MadLoop)",
    None,
    [],
    ["2->2", "single-top", "massive:b"],
    waits=("MS-REF", "EWI-7"),
)
# ---- JJ, PI: QCD with EW orders, photon-initiated
row(
    "JJ01",
    "u u~ > d d~",
    "QCD QED",
    "G0",
    [(6, 0), (4, 2), (2, 4), (0, 6)],
    [(2, 0), (0, 2)],
    "N ~1 min",
    None,
    ["so", "uv"],
    ["2->2", "mixed-born"],
    waits="MS-REF",
)
row(
    "JJ02",
    "u u~ > u u~",
    "QCD QED",
    "G0",
    [(6, 0), (4, 2), (2, 4), (0, 6)],
    [(2, 0), (0, 2)],
    "N ~1 min",
    None,
    [],
    ["2->2", "identical-flavours"],
    waits="MS-REF",
)
row(
    "JJ03",
    "u u~ > g g",
    "QCD QED",
    "G0",
    [(6, 0), (4, 2)],
    [(2, 0)],
    "N ~1 min",
    None,
    [],
    ["2->2"],
    waits="MS-REF",
)
row(
    "JJ04",
    "u u~ > d d~ g",
    "QCD QED",
    "G0",
    [(8, 0), (6, 2), (4, 4)],
    [(3, 0), (1, 2)],
    "N ~3-5 min",
    None,
    ["so"],
    ["2->3", "cross-order-catani"],
    waits="MS-REF",
)
row(
    "PI01",
    "a a > e- e+",
    "QED",
    "G0",
    [(0, 6)],
    [(0, 2)],
    "N ~1 min (one job serves both twins)",
    None,
    ["a0"],
    ["2->2", "photon:initial"],
    waits=("MS-REF", "MS-PHOTON"),
)
row(
    "PI02",
    "a a > w+ w-",
    "QED",
    "G0",
    [(0, 6)],
    [(0, 2)],
    "N ~2-3 min",
    None,
    [],
    ["2->2", "photon:initial", "internal-W"],
    waits=("MS-REF", "MS-PHOTON", "EWI-7"),
)
row(
    "PI03",
    "a g > u u~",
    "QCD QED",
    "G0",
    [(4, 2), (2, 4)],
    [(1, 1)],
    "N ~1 min",
    None,
    [],
    ["2->2", "photon:initial"],
    waits=("MS-REF", "MS-PHOTON"),
)
row(
    "PI04",
    "a u > a u",
    "QCD QED",
    "Ga",
    [(2, 4), (0, 6)],
    [(0, 2)],
    "N ~1 min",
    None,
    ["a0"],
    ["2->2", "photon:initial", "photon:final"],
    waits=("MS-REF", "MS-PHOTON"),
)
# ---- CM, MP, SC
row(
    "CM01",
    "e- e+ > m- m+",
    "QED",
    "Gc",
    [(0, 6)],
    [(0, 2)],
    "E cms-ufo-standard-gmu.json + cms-source-gmu.json + small-width control (MadLoop double)",
    None,
    ["ap", "sp"],
    ["2->2", "cms"],
    waits="MS-CMS",
)
row(
    "CM02",
    "u u~ > e- e+",
    "QCD QED",
    "Gc",
    [(2, 4), (0, 6)],
    [(0, 2)],
    "N, S ~2 min (at and off sqrt(s) = M_Z)",
    None,
    ["sp"],
    ["2->2", "cms"],
    waits=("MS-REF", "MS-CMS"),
)
row(
    "CM03",
    "u d~ > e+ ve",
    "QCD QED",
    "Gc",
    [(2, 4), (0, 6)],
    [(0, 2)],
    "N, S ~2 min (near M_W)",
    None,
    ["sp"],
    ["2->2", "cms"],
    waits=("MS-REF", "MS-CMS", "EWI-7"),
)
row(
    "CM04",
    "g g > t t~",
    "QCD QED",
    "Gc",
    [(6, 0), (4, 2)],
    [(2, 0)],
    "N ~2 min",
    None,
    [],
    ["2->2", "cms"],
    waits=("MS-REF", "MS-CMS"),
)
row(
    "CM05",
    "u u~ > e- e+ g",
    "QCD QED",
    "Gc",
    [(4, 4), (2, 6)],
    [(1, 2)],
    "N ~3 min",
    None,
    ["ward"],
    ["2->3", "cms"],
    waits=("MS-REF", "MS-CMS"),
)
row(
    "CM07",
    "g g > t t~ e- e+ g",
    "QCD QED",
    "Gc",
    [(6, 6)],
    [(3, 2)],
    "N ~35-45 min",
    None,
    ["ward"],
    ["2->5", "cms", "U4"],
    waits=("MS-REF", "MS-CMS-N"),
    tier="campaign",
)
row(
    "CM08",
    "u d~ > e+ ve b b~ QCD=0",
    "QCD",
    "Gc",
    [(2, 8)],
    [(0, 4)],
    "N ~10 min (2->4)",
    None,
    [],
    ["2->4", "cms", "coloured-width"],
    waits=("MS-REF", "MS-CMS-N"),
)
row(
    "CM09",
    "u d~ > e+ ve a",
    "QCD QED",
    "Gca",
    [(2, 6), (0, 8)],
    [(0, 3)],
    "N ~3-5 min (MadLoop CMS x the MG5 formula)",
    None,
    ["a0", "ward"],
    ["2->3", "cms", "photon:final"],
    waits=("MS-REF", "MS-CMS-N"),
)
row(
    "CM10",
    "u d~ > w+ b b~ QCD=0",
    "QCD",
    "Lc",
    [(2, 6)],
    [(0, 3)],
    "N ~3 min",
    None,
    [],
    ["2->3", "cms", "coloured-width", "loop_sm"],
    waits=("MS-REF", "MS-CMS-N"),
)
row(
    "MP01",
    "p p > e- e+",
    "QCD QED",
    "G0",
    [],
    [(0, 2)],
    "N multi-P ~3-5 min",
    None,
    [],
    ["multiparticle"],
    waits=("MS-REF", "MS-MODEL"),
)
row(
    "MP02",
    "p p > t t~",
    "QCD QED",
    "G0",
    [],
    [(2, 0), (0, 2)],
    "N multi-P ~4-6 min",
    None,
    [],
    ["multiparticle"],
    waits=("MS-REF", "MS-MODEL"),
)
row(
    "SC01",
    "e- e+ > u u~",
    "QED",
    "G0",
    [(0, 6)],
    [(0, 2)],
    "E electroweak-eeuu-control.json",
    {
        "format": "ew-control",
        "path": f"{FIX}/electroweak-eeuu-control.json",
        "points_path": CONTROL_POINTS,
        "mu_r2": "1000000",
        "parameters": CONTROL_PARAMETERS,
    },
    ["nc"],
    ["2->2", "quark-final-state"],
)
row(
    "SC02",
    "u u~ > m- m+",
    "QCD QED",
    "Gm",
    [(2, 4), (0, 6)],
    [(0, 2)],
    "N ~1 min",
    None,
    [],
    ["2->2", "massive:muon"],
    waits="MS-REF",
)
row(
    "SC03",
    "u d~ > e+ ve",
    "QCD QED",
    "Gk",
    [(2, 4), (0, 6)],
    [(0, 2)],
    "N ~1-2 min",
    None,
    [],
    ["2->2", "ckm"],
    waits=("MS-REF", "EWI-7"),
)
row(
    "SC04",
    "b b~ > w+ w-",
    "QCD QED",
    "Gb",
    [(2, 4), (0, 6)],
    [(0, 2)],
    "N ~2 min",
    None,
    [],
    ["2->2", "massive:b"],
    waits="MS-REF",
)
row(
    "SC05",
    "u u~ > e- e+ g g",
    "QCD",
    "L5",
    [(6, 4)],
    [(2, 2)],
    "E epsilon-sign.json",
    {"format": "process-components", "path": f"{FIX}/epsilon-sign.json", "key": "uu"},
    [],
    ["2->4", "epsilon-sign", "loop_sm"],
    veto=[1, 3, 5],
    allow_anomalous_veto=True,
    notes="the d s b veto leaves the axial Z-gluon R2 and the closed up-type loops' axial parts uncancelled: lowered by request ([U2], as test_loop_v2_epsilon_sign)",
)
row(
    "SC06",
    "w+ w- > w+ w-",
    "QED",
    "G0",
    [(0, 6)],
    [(0, 2)],
    "N, S ~2-4 min",
    None,
    [],
    ["2->2", "massive-initial", "root-closure"],
    waits=("MS-REF", "EWI-7"),
)
row(
    "SC07",
    "h h > h h",
    "QED",
    "G0",
    [(0, 6)],
    [(0, 2)],
    "N ~1-2 min",
    None,
    [],
    ["2->2", "scalar-loops", "root-closure"],
    waits=("MS-REF", "EWI-7"),
)
row(
    "SC08",
    "t t~ > w+ w-",
    "QED",
    "G0",
    [(0, 6)],
    [(0, 2)],
    "N ~2 min",
    None,
    [],
    ["2->2", "root-closure"],
    waits=("MS-REF", "EWI-7"),
)
row(
    "SC09",
    "t t~ > z h QCD=0",
    "QCD QED",
    "G0",
    [(0, 6)],
    [(0, 2)],
    "E required/ttx_zh_ew (ew-validate; MadLoop + Recola; Recola primary: R2 rule, 2.5 %)",
    req("ttx_zh_ew", ["recola", "madloop"]),
    [],
    ["2->2", "root-mixing", "r2-rule"],
    waits="EWI-7",
)

assert len(R) == 70, len(R)

# ---- MS-REF's references (m-sm/PLAN.md §3.2 MS-REF, §4.2 legends N, R):
# its reference manifest (``required/msm_references.json``) lists per row the
# committed MadLoop runs and the binding references of rule 1. Once it is on
# the branch, a row whose reference is a new run takes its first binding run
# (with the run's components for rule 5 and MG5's alpha(0) conversion over
# the run's tagged photons), its further binding runs become variants (the
# special points S1, S3, S4: ``<row>@<suffix>``), and an existing reference
# with a top-up run of another squared sector becomes a ``sectors`` reference
# of both at the existing fixture's points. Multiparticle members (MP rows)
# wait for MS-MODEL (Q2) and are not wired here.
MSREF_FILE = WT / REQ / "msm_references.json"
MSREF = (
    {e["row"]: e for e in json.loads(MSREF_FILE.read_text())["rows"]}
    if MSREF_FILE.is_file()
    else {}
)
if MSREF:
    LANDED.add("MS-REF")
GMU_UFO = Path(
    os.environ.get(
        "PYAMPLICOL_EW_UFO_REFERENCE",
        WORKSPACE / "reference/models/loop_qcd_qed_sm_Gmu_py3",
    )
)


def _ew_oracle():
    """tests/unit/test_loop_v2_ew.py's UFO-source evaluator (the photon
    conversion parameter per point, below)."""

    import importlib.util

    name = "_msm_manifest_test_loop_v2_ew"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            name, WT / "tests/unit/test_loop_v2_ew.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


def conversion_values(data, counterterm="eCoup_DGmua0_UV_EW"):
    """MG5_aMC's alpha(0) conversion parameter (its real part, as MG5's
    double-precision ``get_virtual_a0Gmu_conv`` keeps it) per point of a
    fixture: [pole, finite] at the point's MU_R and the fixture's
    parameters, from the G_mu UFO's own source (its finite part depends on
    MU_R; at the card's MU_R it equals ``madloop-ct-parameters.json``'s)."""

    if not GMU_UFO.is_dir():
        raise SystemExit("the G_mu UFO is needed for the photon conversion values")
    oracle = _ew_oracle()
    modules = oracle._import_ufo(GMU_UFO, "_msm_manifest_gmu_ufo")
    base = {**data["parameters"], **data.get("fixed_parameters", {})}
    base.update(data.get("parameter_overrides", {}))
    out = []
    for mu in data["mu_r"]:
        values, _env = oracle._ufo_source_values(
            modules, {**base, "MU_R": str(mu)}, exact=False, wrap=None
        )
        out.append(
            [repr(complex(values[counterterm, power]).real) for power in (-1, 0)]
        )
    return out


def _fixture(path):
    return json.loads((WT / FIX / path).read_text())


def _loop_sectors(data):
    """(loop sector, its Born sector, the correction reaching it) of a
    fixture's squared split orders (MS-REF's per-sector rows)."""

    found = []
    for s in data["rows"][0].get("sectors", {}).get("loop", ()):
        by = s.get("born_sectors") or {}
        correction = next((c for c, b in by.items() if b), data.get("correction"))
        found.append(((s["QCD"], s["QED"]), (s["born_sector"]["QCD"],
                      s["born_sector"]["QED"]), correction))  # fmt: skip
    return found


def _photon_spec(data, sector=None, n=None):
    """MG5's alpha(0) conversion over the fixture's tagged photon legs (or
    ``n``), with the conversion parameter per point."""

    tagged = len(data.get("tagged_photon_legs") or ()) if n is None else n
    if not tagged:
        return None
    spec = photons(tagged, sector)
    spec["values"] = conversion_values(data)
    return spec


def _ew_sector(data):
    """The loop sector the electroweak correction reaches (its conversion
    term's sector), if one."""

    sectors = [s for s, _b, c in _loop_sectors(data) if c in ("EW", "QED")]
    return sectors[0] if len(sectors) == 1 else None


def msref_reference(path, run):
    """A required-format reference of an MS-REF run (``path`` below
    tests/fixtures/loop)."""

    data = _fixture(path)
    spec = {
        "format": "required",
        "path": f"{FIX}/{path}",
        "providers": [data.get("primary_provider", "madloop")]
        + [p for p in data["validated_providers"]
           if p != data.get("primary_provider", "madloop")],
    }  # fmt: skip
    if run.get("components"):
        spec["components"] = f"{FIX}/{run['components']}"
    photon = _photon_spec(data, _ew_sector(data))
    if photon:
        spec["photon_conversion"] = photon
    return spec


def _same_point(a, b):
    from fractions import Fraction

    return all(
        Fraction(str(x)) == Fraction(str(y))
        for leg_a, leg_b in zip(a, b, strict=True)
        for x, y in zip(leg_a, leg_b, strict=True)
    )


def apply_msref(r):
    """Wire a row to MS-REF's committed runs (see above)."""

    entry = MSREF.get(r["id"])
    if not entry or r["id"].startswith("MP"):
        return
    runs = {x["fixture"]: x for x in entry["references"] if x["status"] == "committed"}
    # A committed run of another package that MS-REF lists as the row's
    # binding reference (ST04: ew-validate's udx_tbx_ew_mb).
    known = {
        **{x["fixture"]: x for x in entry["existing_references"]
           if x["status"] == "committed" and x["fixture"].startswith("required/")},
        **runs,
    }  # fmt: skip
    binding = [
        b["fixture"] for b in entry["binding_references"] if b["fixture"] in known
    ]
    if r["ref"] is None and binding:
        main = binding[0]
        r["ref"] = msref_reference(main, known[main])
        if r["ref"].get("components") and "uv" not in r["extras"]:
            # Rule 5's EW form on the class's component row (m-sm/PLAN.md
            # §1.4 rule 5: one row per class, MS-REF's component runs).
            r["extras"].append("uv")
        if known[main].get("point_labels"):
            r["more"]["special_points"] = known[main]["point_labels"]
        stem = Path(main).stem
        variants = list(r["more"].get("variants", ()))
        for other in binding[1:]:
            name = Path(other).stem.removeprefix(stem).strip("_") or Path(other).stem
            data = _fixture(other)
            variants.append({
                "name": name,
                "gating": True,
                "tier": r["tier"] if r["tier"] != "default" else "nightly",
                "reference": msref_reference(other, known[other]),
                "points": {"nightly": list(range(len(data["points"])))},
                "extras": [],
                "extras_pending": {},
                "notes": known[other].get("note") or "",
            })  # fmt: skip
        if variants:
            r["more"]["variants"] = variants
        return
    old = r["ref"]
    if not old or old.get("format") != "required":
        return
    existing = _fixture(old["path"].removeprefix(f"{FIX}/"))
    for path in runs:
        data = _fixture(path)
        new = [x for x in _loop_sectors(data) if x[0] not in r["sectors"]]
        if not new or len(new) != len(_loop_sectors(data)):
            continue
        # A top-up: the run's rows at the existing fixture's points and scales.
        rows = []
        for point, mu in zip(existing["points"], existing["mu_r"], strict=True):
            match = [i for i, (q, m) in enumerate(zip(data["points"], data["mu_r"],
                     strict=True)) if m == mu and _same_point(q, point)]  # fmt: skip
            rows.append(match[0] if match else None)
        if None in rows:
            continue
        (old_sector,) = r["sectors"]
        (old_born,) = r["born"]
        born_sector = (2 * old_born[0], 2 * old_born[1])
        parts = [
            {"path": old["path"], "sector": {"QCD": old_sector[0], "QED": old_sector[1]},
             "born_sector": {"QCD": born_sector[0], "QED": born_sector[1]}},
        ] + [
            {"path": f"{FIX}/{path}", "sector": {"QCD": s[0], "QED": s[1]},
             "born_sector": {"QCD": b[0], "QED": b[1]}, "rows": rows}
            for s, b, _c in new
        ]  # fmt: skip
        spec = {"format": "sectors", "parts": parts, "providers": ["madloop"]}
        if old.get("photon_conversion"):
            # The conversion term on the electromagnetic correction's sector
            # (the existing fixture's), every sector scaled.
            spec["photon_conversion"] = _photon_spec(
                existing, old_sector, n=old["photon_conversion"]["tagged"]
            )
        r["ref"] = spec
        r["sectors"] = sorted({*r["sectors"], *(s for s, _b, _c in new)}, reverse=True)
        r["legend"] += f" (top-up {Path(path).stem}: MS-REF)"
        return


# The R2 couplings MadLoop's export of a reference calls (MS-REF: each new
# run's ``madloop_r2_couplings``; ``required/msm/existing_r2_couplings.json``
# for the existing references' exports), the input of the R2 rule's
# structural difference with the engine's counterterm program
# (``mqcd.rule_r2``). None where a reference (or a part of it) lists none.
EXISTING_R2_FILE = WT / REQ / "msm" / "existing_r2_couplings.json"
EXISTING_R2 = (
    json.loads(EXISTING_R2_FILE.read_text())["exports"]
    if EXISTING_R2_FILE.is_file()
    else {}
)


def called_couplings(reference):
    if not reference:
        return None
    fmt = reference["format"]
    if fmt == "madloop-components":
        entry = EXISTING_R2.get(reference["key"])
        return None if entry is None else sorted(entry["called"])
    if fmt == "sectors":
        lists = [called_couplings({"format": "required", **part})
                 for part in reference["parts"]]  # fmt: skip
        if any(found is None for found in lists):
            return None
        return sorted(set().union(*lists))
    if fmt != "required":
        return None
    data = json.loads((WT / reference["path"]).read_text())
    if data.get("madloop_r2_couplings"):
        return sorted(data["madloop_r2_couplings"]["called"])
    entry = EXISTING_R2.get(Path(reference["path"]).stem)
    return None if entry is None else sorted(entry["called"])


for r in R:
    apply_msref(r)

# Extras the harness checks (``mqcd.IMPLEMENTED_EXTRAS``) and why the others
# wait (m-sm/PLAN.md §4.1 extras).
PENDING_EXTRAS = {
    "nc": "Q4 (a, recommended, pending with the user): EW LC/NLC is M-FINAL (typed colour-declaration-coverage refusal)",
    "hel": "MS-REF (per-helicity SLOOPMATRIXHEL references)",
    "sp": "MS-REF (special points S1-S4)",
}
# A row's ``uv`` extra is rule 5's EW component form: it needs the
# reference's instrumented components (MadLoop's Born x CT split).
COMPONENT_FORMATS = {"ew-control", "madloop-components", "process-components"}

# The R2 rule (m-sm/PLAN.md §1.4 rule 1, Q7): per row the R2 couplings the
# engine inserts that MadLoop's label matching omits, as the rows'
# references record them (``goldstone-mixing.json`` omitted_r2; the e+e- >
# t t~ h fixture's Recola agreement), checked against the engine's
# counterterm program by the harness (``mqcd.rule_r2``); rule 1 is then
# against Recola (LL10) or MadLoop plus the omitted component (TT05).
# Known (PLAN §1.4): LL10, TT04, SC09, TT05 (R2_G0tt_b of V_ttG02); TT04 and
# SC09 join with EWI-7's fixtures. A comparison by coupling name with the
# export's called couplings is not used: MG5_aMC's restricted model merges
# couplings of equal value (LL03's export calls R2_AAU and R2_AAD where the
# UFO's V_R2AA groups take R2_AAu3, R2_AAc3, ...), so names differ where the
# insertion is the same (LL03 = MadLoop to 4e-15).
OMITTED = {
    "LL10": ["R2_G0tt_b"],
    "TT05": ["R2_G0tt_b"],
    "TT04": ["R2_G0tt_b"],
    "SC09": ["R2_G0tt_b"],
}
# TT05's omitted component (``goldstone-mixing.json`` omitted_r2): MadLoop's
# Born x CT interference of the R2_G0tt amplitudes times R2_G0tt_b / R2_G0tt
# at the card, the UFO's couplings (``test_loop_v2_ew_gauge.
# _ufo_coupling_ratio``, binary64; 0.869 at lhv = 1), computed when this
# script runs with the G_mu UFO.
OMITTED_COMPONENT = {"TT05": ("r2_g0tt", "R2_G0tt_b", "R2_G0tt")}


def coupling_ratio(name, numerator, denominator, card) -> str | None:
    ufo = Path(
        os.environ.get(
            "PYAMPLICOL_EW_UFO_REFERENCE",
            WORKSPACE / "reference/models/loop_qcd_qed_sm_Gmu_py3",
        )
    )
    if not ufo.is_dir():
        return None
    from tests.unit.test_loop_v2_ew_gauge import _ufo_coupling_ratio

    return repr(_ufo_coupling_ratio(ufo, numerator, denominator, card))


def loop_orders(born, corrections, sectors):
    """The loop amplitude orders of a request: each Born amplitude order
    with two powers of a correction, kept where its interference with some
    Born amplitude order is one of the row's sectors (every one if the row
    lists none)."""

    out = set()
    for b in born:
        for c in corrections:
            loop = (b[0] + 2, b[1]) if c == "QCD" else (b[0], b[1] + 2)
            if not sectors or any(
                (x[0] + loop[0], x[1] + loop[1]) in sectors for x in born
            ):
                out.add(loop)
    orders = [{"QCD": q, "QED": e} for q, e in sorted(out, reverse=True)]
    return orders[0] if len(orders) == 1 else orders


def sector_orders(sector):
    return {"QCD": sector[0], "QED": sector[1]}


def point_count(reference):
    if reference is None:
        return 3
    fmt = reference["format"]
    data = json.loads(
        (
            WT
            / (
                reference["path"]
                if "path" in reference
                else reference["parts"][0]["path"]
            )
        ).read_text()
    )
    if fmt == "ew-control":
        return len(data["rows"])
    if fmt == "madloop-components":
        return len(data["processes"][reference["key"]]["points"])
    if fmt == "process-components":
        return len(data["rows"][reference["key"]])
    return len(data["points"])


# Identically vanishing coefficients (checked absolutely against F_s),
# recorded from the campaign's runs (tmp/ms-validate/c1, 2026-10-29): the
# QCD x EW sector of g g > t t~ has no 1/eps^2 (soft photons between the
# massive tops, neutral gluons): ours 1e-35, the providers' 1e-13 of the
# Born (their rounding of a zero).
VANISHING = {
    "TT01": [{"sector": "QCD^4 QED^2", "coefficient": "double_pole"}],
    # g t > t t t~ with QED corrections: massive tops, a neutral gluon (ours
    # exactly 0, MadLoop's 1e-17 of the Born).
    "TT05": [{"sector": "total", "coefficient": "double_pole"}],
    # g b > t t~ b (massive b) with QED corrections: every charged leg
    # massive (ours exactly 0, MadLoop's 1e-17 of the Born; c3 2026-10-30).
    "TT06": [{"sector": "total", "coefficient": "double_pole"}],
}
# Rule 1's tolerance per row (nominal 1e-12; 1e-10 from 2->4 up where the
# providers' precision needs it, the user's ruling of 2026-10-29 ~01:12; and
# below ~1e-5 relative no finding, ~10:20), with the evidence of c1:
# LL10 against Recola (the R2 rule's primary; MadLoop, which omits
# R2_G0tt_b, is 5.6e-4 and 1.1e-2 off): 3.9e-12 and 7.4e-12 at points 1, 2,
# Recola's double-precision finite part; TV06 (2->4) 1.16e-12 against
# MadLoop's quadruple precision at point 2; TT06 against MadLoop's double
# precision counterterm parameters (goldstone-mixing.json; ew-validate held
# its finite parts at 1e-8; c3 2026-10-30: 4e-11 to 1.1e-9).
RULE1 = {"LL10": 1e-10, "TV06": 1e-10, "TV07": 1e-10, "TT06": 1e-8}
# Relaxed rules per row (the user's ruling of ~10:20, at most 1e-5): SC05's
# poles against Catani in double-double, 2.9e-14 and 4.2e-14 at point 0
# (the fixture's binary64 points are on shell and conserve momentum to
# rounding only); TT05's, 1.2e-16 to 2.7e-16, and TT06's, 9.5e-16 to
# 1.5e-14 (the massive QED operator's double-double prediction).
RELAXED = {"SC05": {"4": 1e-12}, "TT05": {"4": 1e-14}, "TT06": {"4": 1e-13}}
# Rule 4 not formed (status partial): the massive-muon copy of the G_mu UFO
# (code Gm) changes only the muon mass in the restriction card, while the
# UFO writes the lepton field renormalisation for massless leptons, so its
# single pole (ours = MadLoop's) exceeds the massive QED operator by exactly
# 3 (alpha/2pi) Born (test_loop_v2_qed_catani's docstring; c1: 9.9e-5 =
# 3 x 3.30e-5 at point 0): not a reference of the operator.
NO_CATANI = {"LL02", "SC02"}
# Rows run on the native point inputs (the production route; rule 4 from the
# engine's operators on the Python-input Born): the 2->5 target and EWI-7's
# root-closure rows, checked with native inputs once EWI-7 lands (PLAN §3.2
# MS-VALIDATE item 6; a failure goes to the owner of the failing site).
NATIVE_ROWS = {"TV07", "TT04", "SC06", "SC07", "SC08", "SC09"}

rows = []
for r in R:
    model, restriction, fixed, scheme, alpha = CODES[r["code"]]
    reference = r["ref"]
    waits = r["waits"]
    waits = tuple(waits) if isinstance(waits, tuple) else ((waits,) if waits else ())
    waits = tuple(w for w in waits if w not in LANDED)
    status = "active" if reference and not waits else "pending"
    tier = r["tier"]
    count = point_count(reference)
    if tier == "default":
        points = {"default": [0, 1], "nightly": list(range(2, count))}
    else:
        points = {tier: list(range(count))}
    # The amplitude-order caps of PLAN §4.2's processes (``QCD=0``) are the
    # request's Born orders (``born_orders``), not particles.
    process = " ".join(t for t in r["process"].split() if "=" not in t)
    sectors = r["sectors"]
    corrections = list(r["corr"])
    ignored = []
    fixed = dict(fixed)
    if reference and reference.get("format") == "required":
        data = json.loads((WT / reference["path"]).read_text())
        # The providers' WTau: the G_mu and alpha(M_Z) UFOs have none.
        ignored = sorted(
            k
            for k in data.get("fixed_parameters", {})
            if k not in fixed and k == "WTau"
        )
    born = [b for b in r["born"]]
    entry = {
        "id": r["id"],
        "class": CLASS[r["id"][:2]],
        "process": process,
        # The request's Born bounds and the Born amplitude orders they hold.
        "born_orders": {"QCD": max(b[0] for b in born), "QED": max(b[1] for b in born)},
        "born_amplitude_orders": [{"QCD": q, "QED": e} for q, e in born],
        "loop_orders": loop_orders(born, corrections, sectors),
        "corrections": corrections,
        "model": model,
        "restriction": restriction,
        "restriction_code": r["code"],
        "fixed_parameters": fixed,
        "gauge": "feynman" if model != LOOPSM else "unitary",
        "scheme": scheme,
        "tier": tier,
        "status": status,
        "reference_legend": r["legend"],
        "reference": reference,
        "points": points,
        "extras": r["extras"],
        "features": r["features"],
        "sectors": [sector_orders(s) for s in sectors],
        # Every sector predicted unless the row states otherwise (a joint
        # QCD + QED request without caps must predict every one, PLAN §1.4).
        "predicted_sectors": [sector_orders(s) for s in sectors],
        "unpredicted_sectors": [],
        "unpredicted_reasons": {},
        "reference_outliers": [],
        "vanishing": [],
        "reference_tolerance": mqcd.REFERENCE_TOLERANCE,
        "alphas": {"QED": alpha} if "QED" in corrections else {},
    }
    if model != LOOPSM:
        entry["compatibility"] = "gmu_particle_anti"
        entry["scale_parameter"] = "MU_R"
    for key in ("parameters", "inputs", "variants", "catani", "allow_anomalous_veto"):
        if key in r["more"]:
            entry[key] = r["more"][key]
    if "veto" in r["more"]:
        entry["particle_veto"] = r["more"]["veto"]
    if ignored:
        entry["ignored_fixed_parameters"] = ignored
    if r["notes"]:
        entry["notes"] = r["notes"]
    if r["id"] in VANISHING:
        entry["vanishing"] = VANISHING[r["id"]]
    if r["id"] in RULE1:
        entry["reference_tolerance"] = RULE1[r["id"]]
    elif {"2->4", "2->5"} & set(r["features"]):
        # The user's ruling of 2026-10-29 ~01:12: 1e-10 from 2->4 up.
        entry["reference_tolerance"] = mqcd.REFERENCE_TOLERANCE_HIGH
    if r["id"] in RELAXED:
        entry["relaxed"] = RELAXED[r["id"]]
    if r["id"] in NATIVE_ROWS:
        entry["inputs"], entry["catani"] = "native", "engine"
    if r["id"] in NO_CATANI:
        entry["catani"] = "none"
        entry["catani_reason"] = (
            "the massive-muon UFO copy: the UFO writes the lepton field "
            "renormalisation for massless leptons (single pole = the massive "
            "QED operator + 3 alpha/2pi Born)"
        )
    if status == "pending":
        entry["pending"] = {
            "waits_for": waits[0] if len(waits) == 1 else list(waits),
            "reason": "reference not yet produced (PLAN §4.2 legend: "
            + r["legend"]
            + ")"
            if "MS-REF" in waits
            else "the row's package: " + ", ".join(waits),
        }
    pend = {}
    for extra in r["extras"]:
        if extra == "hel" and reference and "MS-REF" in LANDED:
            data = json.loads((WT / reference["path"]).read_text())
            if data.get("per_helicity"):
                continue
        if extra == "sp" and (
            r["more"].get("variants") or r["more"].get("special_points")
        ):
            # The special points are variants (S1, S3, S4) or the run's own
            # labelled points (S2).
            continue
        if extra in PENDING_EXTRAS:
            pend[extra] = PENDING_EXTRAS[extra]
        elif extra == "uv" and (reference or {}).get("components"):
            continue
        elif extra == "uv" and (reference or {}).get("format") not in COMPONENT_FORMATS:
            pend[extra] = (
                "rule 5's EW form runs on the class's component row (MS-REF's "
                "component runs, one row per class: m-sm/PLAN.md §1.4 rule 5)"
                if "MS-REF" in LANDED
                else "MS-REF (component runs: bare / R2 / UV-CT, "
                "madloop_ct_selection.py)"
            )
    if pend:
        entry["extras_pending"] = pend
    if r["id"] in OMITTED and status == "active":
        entry["madloop_omitted_r2"] = OMITTED[r["id"]]
    called = called_couplings(reference)
    if called is not None:
        entry["madloop_r2_called"] = called
        for variant in entry.get("variants", ()):
            variant["madloop_r2_called"] = called_couplings(variant["reference"])
    if r["id"] in OMITTED_COMPONENT and status == "active":
        component, numerator, denominator = OMITTED_COMPONENT[r["id"]]
        data = json.loads((WT / reference["path"]).read_text())["processes"][
            reference["key"]
        ]
        ratio = coupling_ratio(
            r["id"],
            numerator,
            denominator,
            {**data["parameters"], **data["fixed_parameters"]},
        )
        if ratio is None:
            raise SystemExit(
                f"{r['id']}: the G_mu UFO is needed for the omitted R2 ratio"
            )
        entry["reference"] = {
            **entry["reference"],
            "omitted_r2": {
                "component": component,
                "coupling": numerator,
                "proportional_to": denominator,
                "ratio": ratio,
            },
        }
    rows.append(entry)

# The nightly tier's file jobs (each within PLAN §3.2's 30 minutes): measured
# seconds per id where a run measured them (mqcd_manifest's packing), else
# DEFAULT_SECONDS per EW generation.
# (seconds, points) per id, wall time of one process per row (the c2 run of
# tmp/ms-validate, 2026-10-29 ~22:40 UTC, 4 cores each, host load ~80;
# generation 40-250 s each, the extras included).
MEASURED_SECONDS: dict[str, tuple[int, int]] = {
    "DY05": (652, 3), "LL01": (293, 3), "LL02": (306, 3), "LL03": (68, 3),
    "LL10": (322, 3), "SC01": (330, 4), "SC05": (30, 3), "TT01": (472, 3),
    "TT05": (453, 3), "TV06": (453, 3), "VJ03": (256, 3), "VV06": (247, 3),
}  # fmt: skip
DEFAULT_SECONDS = 600
JOB_SECONDS = 1500


def nightly_ids_of(entry):
    ids = []
    if (
        entry["status"] == "active"
        and (
            entry["points"].get("nightly")
            or set(entry["extras"]) & mqcd.IMPLEMENTED_EXTRAS
        )
        and entry["tier"] != "campaign"
    ):
        ids.append(entry["id"])
    for v in entry.get("variants", ()):
        if (
            v.get("gating", True)
            and v.get("tier", "nightly") == "nightly"
            and entry["status"] == "active"
        ):
            ids.append(f"{entry['id']}@{v['name']}")
    return ids


jobs = []
for entry in sorted(rows, key=lambda e: e["id"]):
    ids = nightly_ids_of(entry)
    if not ids:
        continue
    seconds = sum(MEASURED_SECONDS.get(i, (DEFAULT_SECONDS, 0))[0] for i in ids)
    fits = [j for j in jobs if j["seconds"] + seconds <= JOB_SECONDS]
    if fits:
        job = min(fits, key=lambda j: (j["seconds"], j["job"]))
    else:
        job = {"job": len(jobs) + 1, "seconds": 0, "rows": []}
        jobs.append(job)
    job["seconds"] += seconds
    job["rows"] += ids
for job in jobs:
    job["rows"].sort()
    job["file"] = (
        "tests/unit/test_loop_v2_msm_nightly"
        + ("" if job["job"] == 1 else f"_{job['job']}")
        + ".py"
    )

# The thin entry point of each file job after the first (written when
# missing; a stub of a job that no longer exists is reported, and
# test_loop_v2_msm_manifest fails until it is removed).
STUB = '''# SPDX-License-Identifier: 0BSD
"""M-SM campaign, nightly tier, file job {job} (manifest ``nightly_jobs``;
m-sm/PLAN.md §3.2 and §4.3): the job's rows at their nightly points under
PLAN §1.4 (``tests/unit/test_loop_v2_msm_nightly.py`` describes the tier)."""

from __future__ import annotations

from tests.unit.loop_mqcd_tiers import nightly_module
from tools.loop_benchmark import mqcd

MANIFEST = mqcd.ROOT / "tests" / "fixtures" / "loop" / "msm" / "manifest.json"
campaign, test_row_meets_the_acceptance_rules = nightly_module({job}, MANIFEST)
'''
for job in jobs[1:]:
    stub = WT / job["file"]
    if not stub.is_file():
        stub.write_text(STUB.format(job=job["job"]))
stale = sorted(
    str(path.relative_to(WT))
    for path in (WT / "tests/unit").glob("test_loop_v2_msm_nightly_*.py")
    if str(path.relative_to(WT)) not in {job["file"] for job in jobs}
)
if stale:
    print("stale nightly stubs (remove them):", " ".join(stale))

# PLAN §3.2 MS-VALIDATE item 8: each shipped restriction of both UFOs
# generates the request of a base row on its model, compared with the base
# row's generation (native executor, binary64, the row's first point, the
# row's parameters: the restrictions that change MT, MH or widths are
# evaluated at the row's values; with_b_mass at the row's MB = 0) within
# 1e-14. parallel_test* are out of scope (PLAN §1.1).
SMOKE_RESTRICTIONS = {
    "LL01": (
        "a0",
        "ckm",
        "no_widths",
        "with_b_mass",
        "with_b_mass_no_width",
        "with_technical",
    ),
    "LL03": (
        "ckm",
        "no_widths",
        "with_b_mass",
        "with_b_mass_no_widths",
        "with_technical",
    ),
}
SMOKE_SECONDS = 400
smokes = [
    {"id": f"{CODES[next(r['code'] for r in R if r['id'] == base)][0]}:{name}",
     "row": base, "restriction": name, "executor": "native"}
    for base, names in SMOKE_RESTRICTIONS.items()
    for name in names
]  # fmt: skip
smoke_jobs = []
for entry in smokes:
    if (
        not smoke_jobs
        or len(smoke_jobs[-1]["smokes"]) * SMOKE_SECONDS >= JOB_SECONDS - SMOKE_SECONDS
    ):
        smoke_jobs.append({"job": len(smoke_jobs) + 1, "smokes": []})
    smoke_jobs[-1]["smokes"].append(entry["id"])
for job in smoke_jobs:
    job["file"] = (
        "tests/unit/test_loop_v2_msm_smokes"
        + ("" if job["job"] == 1 else f"_{job['job']}")
        + ".py"
    )

manifest = {
    "schema_version": 1,
    "plan": "workspace/reports/engine-v2/m-sm/PLAN.md §1.4, §3.2 MS-VALIDATE, §4",
    "description": "M-SM validation campaign rows (one per PLAN §4.2 core row), in the record type of the M-QCD manifest. tools/loop_benchmark/mqcd.py reads it; tests/unit/test_loop_v2_msm_*.py run it.",
    "models": MODELS,
    "restriction_codes": {
        k: {
            "model": v[0],
            "restriction": v[1],
            "fixed_parameters": v[2],
            "scheme": v[3],
            "alpha": v[4],
        }
        for k, v in CODES.items()
    },
    "unblockers": list(UNBLOCKERS),
    "classes": sorted(set(CLASS.values())),
    "features": sorted({f for e in rows for f in e["features"]}),
    "cost_probes": {
        "DY07": {
            "process": "u u~ > e- e+ m- m+",
            "corrections": ["QED"],
            "model": "G0",
            "generate_s": 255.2,
            "export_native_s": 95.3,
            "peak_gb": 11.2,
            "source": "workspace/tmp/ms-validate/probe/dy07 (2026-10-29, 4 cores, host load ~70)",
            "tier": "the 2->4 EW rows (DY07, DY08, CM08) are nightly: one generation fits a 30-min job",
        },
    },
    "smokes": {"restrictions": smokes, "jobs": smoke_jobs},
    "nightly_jobs": {
        "budget_seconds": JOB_SECONDS,
        "measurement": "DEFAULT_SECONDS per id until a nightly run measures them",
        "jobs": jobs,
    },
    "rows": rows,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(manifest, indent=1) + "\n")
print("rows", len(rows), "active", sum(e["status"] == "active" for e in rows),
      "nightly jobs", len(jobs))  # fmt: skip
