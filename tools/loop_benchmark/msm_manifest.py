# SPDX-License-Identifier: 0BSD
# The row table quotes m-sm/PLAN.md §4.2's processes and legends.
# ruff: noqa: E501
"""Write tests/fixtures/loop/msm/manifest.json, the M-SM campaign rows.

Usage: python tools/loop_benchmark/msm_manifest.py

The rows are m-sm/PLAN.md §4.2's 70 core rows and MS-UFODB's SC10
(``row(...)`` below: process,
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
import re
import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WT))

from tools.loop_benchmark import mqcd  # noqa: E402

REQ = "tests/fixtures/loop/required"
FIX = "tests/fixtures/loop"
OUT = WT / "tests/fixtures/loop/msm/manifest.json"


def _workspace() -> Path:
    """The loop workspace (reference UFOs): ``PYAMPLICOL_LOOP_WORKSPACE``,
    else the ``workspace`` directory beside the main checkout (the parent of
    git's common directory, as ``tests/conftest.py`` finds it)."""

    if configured := os.environ.get("PYAMPLICOL_LOOP_WORKSPACE"):
        return Path(configured)
    import subprocess

    common = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=WT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    main = Path(common).resolve().parent if common else WT
    return main.parent / "workspace"


WORKSPACE = _workspace()
# The QCD+QED loop UFOs as UFOmodeldb ships them (tests/conftest.py's
# ``loop_gmu_ufo`` and ``loop_qcd_qed_sm_ufo``; MS-UFODB).
UFODB = WORKSPACE / "reference/models/ufodb-6ca4b120-patched"

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
    # restrict_ckm keeps MB, ymb, MTA, ymtau (4.7, 4.2, 1.777): MS-REF's run
    # sets them (MB = ymb = 4.7) at runtime; only the widths are fixed.
    "Gk": (GMU, "ckm", ZERO_WIDTHS, "ew-gmu-ckm", ALPHA_GMU),
    "Gt": (GMU, "with_technical", ZERO_WIDTHS, "ew-gmu-tech", ALPHA_GMU),
    # Under the complex-mass scheme the Yukawas follow the masses (no Yukawa
    # input, ``cms-yukawa-input``); a row with an MS-REF run takes that run's
    # fixed masses and widths (the card widths, zero for an external
    # unstable multiplet), CM01 its blocks' widths at runtime.
    "Gc": (GMU, "default", {"MB": "0", "MTA": "0"}, "ew-gmu-cms", ALPHA_GMU),
    "Gca": (GMU, "a0", {"MB": "0", "MTA": "0"}, "ew-gmu-a0-cms", ALPHA_GMU),
    # MS-REF's CM10 run: loop_sm-no_b_mass, WT = 1.4915, WZ = WW = WH = 0.
    "Lc": (LOOPSM, "no_b_mass", {"WW": "0", "WZ": "0", "WH": "0"}, "qcd-cms", ALPHA_MZ),
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
# CM01's card widths (``cms-source-gmu.json`` records none; its finite block
# is the card's, as the ufo-standard fixture's).
CM01_CARD_WIDTHS = {
    "WZ": "2.49877",
    "WW": "2.09291",
    "WT": "1.37758",
    "WH": "0.00407468",
}
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
# ttx_zh_ew, udx_tbx_ew; MS-PHOTON, per-leg photon tagging
# ``loop.external_photons``, integrated at 870e092f).
LANDED = {"EWI-7", "MS-PHOTON"}
# MS-CMS-N, integrated at a359965c, carries MS-CMS's transform and policy
# (work/v2-ms-cms fc3ad912): the complex-mass rows run.
LANDED |= {"MS-CMS", "MS-CMS-N"}
# MS-MODEL, integrated at 2ae8b88b: multiparticle members without a Born are
# skipped typed (Q2 (a)); the public EW models.
LANDED.add("MS-MODEL")
# Model codes under the complex-mass scheme (m-sm/PLAN.md §4.1).
CMS_CODES = {"Gc", "Gca", "Lc"}


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
    ["ward", "joint", "ap"],
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
    [],
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
    notes="joint QCD + QED request; s^6 against loop_sm's QCD fixture (pure QCD, independent of the EW inputs), s^4e^2 against the G_mu fixture; in the default tier since MS-GEN (PLAN §3.2 item 3: generation 58 s, < 60 s; LL01 83 s and DY01 84 s stay nightly; tmp/ms-validate/gen60 at e16b620f)",
    tier="default",
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
    notes='the default photon tags ("final"): both initial photons untagged, raw MadLoop and -gamma_gamma/eps each in rule 4; the twin @all tags both (Q1 (a), MG5_aMC\'s !a! on initial photons)',
    photon_twin={"name": "all", "code": "Ga", "external_photons": "all", "tagged": 2},
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
    {
        "format": "cms-control",
        "path": f"{FIX}/cms-ufo-standard-gmu.json",
        "block": "finite",
        "mu_r2": "1000000",
        "parameters": {k: v for k, v in CONTROL_PARAMETERS.items() if k != "ymt"},
    },
    ["ap", "sp"],
    ["2->2", "cms"],
    waits="MS-CMS",
    notes="MadLoop CMS double-precision exports (cms-ufo-standard-gmu.json): the card widths' block (continuum and three Z-resonance points); variants: zero widths, the widths x 0.001 (S3), and the G_mu source's reglog override (cms-source-gmu.json, a compatibility view, [U3]); the widths are runtime parameters of one generation",
    variants=[
        {
            "name": name,
            "gating": True,
            "tier": "nightly",
            "reference": {
                "format": "cms-control",
                "path": f"{FIX}/{fixture}",
                "block": block,
                "mu_r2": "1000000",
                "parameters": {
                    k: v for k, v in CONTROL_PARAMETERS.items() if k != "ymt"
                },
                **(
                    {"widths": CM01_CARD_WIDTHS}
                    if fixture == "cms-source-gmu.json"
                    else {}
                ),
            },
            **(
                {"reglog_convention": "source"}
                if fixture == "cms-source-gmu.json"
                else {}
            ),
            "points": {"nightly": list(range(count))},
            "extras": [],
            "extras_pending": {},
            "notes": note,
        }
        for name, fixture, block, note, count in (
            (
                "zero",
                "cms-ufo-standard-gmu.json",
                "zero",
                "every width zero at runtime (the real-mass values)",
                3,
            ),
            (
                "small",
                "cms-ufo-standard-gmu.json",
                "small",
                "S3: the widths x 0.001 at runtime",
                3,
            ),
            (
                "source",
                "cms-source-gmu.json",
                "finite",
                "the G_mu source's reglog override (reglog_convention source), the card widths",
                4,
            ),
        )
    ],
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
    [],
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
# MS-UFODB's row (slice 0e5930c2): the R2 vertices Z Z H H and Z Z G0 G0
# (coupling R2_ZZHH, fixed in UFOmodeldb 6ca4b120; no other row reaches
# them), MadLoop QP on the UFOmodeldb model with Recola.
row(
    "SC10",
    "z z > h h",
    "QED",
    "G0",
    [(0, 6)],
    [(0, 2)],
    "N (MS-UFODB: R2_ZZHH on UFOmodeldb 6ca4b120; MadLoop QP + Recola)",
    None,
    [],
    ["2->2", "r2-ufodb"],
    waits="MS-REF",
)

assert len(R) == 71, len(R)

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
    os.environ.get("PYAMPLICOL_EW_UFO_REFERENCE", UFODB / "loop_qcd_qed_sm_Gmu_py3")
)


def _ew_oracle():
    """The UFO-source evaluator (the photon conversion parameter per point,
    below): ``tools/loop_reference/ufo_source_oracle.py``."""

    from tools.loop_reference import ufo_source_oracle

    return ufo_source_oracle


def conversion_values(data, counterterm="eCoup_DGmua0_UV_EW"):
    """MG5_aMC's alpha(0) conversion parameter (its real part, as MG5's
    double-precision ``get_virtual_a0Gmu_conv`` keeps it) per point of a
    fixture: [pole, finite] at the point's MU_R and the fixture's
    parameters, from the G_mu UFO's own source (its finite part depends on
    MU_R; at the card's MU_R it equals ``madloop-ct-parameters.json``'s)."""

    if not GMU_UFO.is_dir():
        raise SystemExit("the G_mu UFO is needed for the photon conversion values")
    oracle = _ew_oracle()
    modules = oracle.import_ufo(GMU_UFO, "_msm_manifest_gmu_ufo")
    base = {**data["parameters"], **data.get("fixed_parameters", {})}
    base.update(data.get("parameter_overrides", {}))
    out = []
    for mu in data["mu_r"]:
        values, _env = oracle.ufo_source_values(
            modules, {**base, "MU_R": str(mu)}, exact=False, wrap=None
        )
        out.append(
            [repr(complex(values[counterterm, power]).real) for power in (-1, 0)]
        )
    return out


def conversion_values_cms(data, counterterm="eCoup_DGmua0_UV_EW"):
    """As ``conversion_values`` for a complex-mass reference: the real parts
    of the transformed model's conversion parameter (MS-CMS's port of MG5's
    transform at the fixture's fixed widths and masses), as MG5's
    double-precision ``get_virtual_a0Gmu_conv`` keeps them; its finite part
    must equal the MadLoop export's own value per MU_R (``export_
    parameters``) to 1e-12."""

    from pyamplicol.loops.model_cms import complex_mass_scheme
    from pyamplicol.loops.model_restrictions import prepare_loop_restrictions
    from pyamplicol.loops.scalar_bindings import (
        NativeScalarBindings,
        prepare_scalar_bindings,
    )
    from pyamplicol.models.loop_import import load_raw_loop_model

    raw = load_raw_loop_model(
        str(GMU_UFO), restriction=data["restriction"] or "default"
    )
    names = {record["name"] for record in raw.collections["parameters"]}
    fixed = {k: v for k, v in data["fixed_parameters"].items() if k in names}
    scheme = complex_mass_scheme(raw, fixed_parameters=fixed)
    derived = prepare_loop_restrictions(scheme.derived, simplify=False).derived
    names = {record["name"] for record in derived.collections["parameters"]}
    plan = prepare_scalar_bindings(
        derived,
        ((counterterm, -1), (counterterm, 0)),
        fixed_parameters={k: v for k, v in fixed.items() if k in names},
    )
    exported = data["export_parameters"]
    if exported["mu_r"] != data["mu_r"]:
        raise SystemExit("the export's conversion values are not at the fixture's MU_R")
    out = []
    for index, mu in enumerate(data["mu_r"]):
        parameters = {
            k: v for k, v in data["parameters"].items() if k in plan.external_names
        }
        parameters["MU_R"] = mu
        pole, finite = (
            complex(*map(float, value))
            for value in NativeScalarBindings(
                plan, arithmetic="double", parameters=parameters
            ).values.to_decimal()
        )
        key = "MDL_" + counterterm.upper() + "_FIN_"
        theirs = complex(*exported["values"][key][index])
        if abs(finite - theirs) > 1e-12 * abs(theirs):
            raise SystemExit(
                f"conversion at MU_R {mu}: ours {finite}, the export's {theirs}"
            )
        out.append([repr(pole.real), repr(finite.real)])
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
    spec["values"] = (
        conversion_values_cms(data)
        if data.get("complex_mass_scheme")
        else conversion_values(data)
    )
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


def zero_points(path):
    """Born-zero points of an MS-REF run (its per-point reference records
    compare absolutely against a regular neighbour, PLAN §4.1 S1) -> that
    neighbour's row (``mqcd.Row.zero_points``)."""

    rows = _fixture(path)["rows"]
    return {
        str(i): row["reference"]["absolute_scale_row"]
        for i, row in enumerate(rows)
        if (row.get("reference") or {}).get("comparison") == "absolute"
    }


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
    own = [
        f
        for f in binding
        if f in runs
        and set(r["sectors"]) <= {s for s, _b, _c in _loop_sectors(_fixture(f))}
    ]
    if r["ref"] is not None and own and not r["ref"].get("path", "").endswith(own[0]):
        # A committed run binding the row's own sectors replaces its existing
        # reference (MS-UFO-PATCH re-referenced the rows the user's UFO patch
        # changes, MadLoop QP + Recola on the patched models: LL10, TT04,
        # TT05, TT06, SC09; a top-up run of another sector is joined below).
        r["ref"] = None
        r["legend"] += f" (re-referenced: {Path(own[0]).stem}, MS-UFO-PATCH)"
        binding = [f for f in binding if f in runs]
    if r["ref"] is None and binding:
        main = binding[0]
        r["ref"] = msref_reference(main, known[main])
        if r["ref"].get("components") and "uv" not in r["extras"]:
            # Rule 5's EW form on the class's component row (m-sm/PLAN.md
            # §1.4 rule 5: one row per class, MS-REF's component runs).
            r["extras"].append("uv")
        if known[main].get("point_labels"):
            r["more"]["special_points"] = known[main]["point_labels"]
        if zero_points(main):
            r["more"]["zero_points"] = zero_points(main)
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
                "zero_points": zero_points(other),
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


def add_photon_twin(r):
    """A row's photon-tagging twin (PLAN §4.2 PI01: the same MadLoop run,
    another ``loop.external_photons`` on the twin's model code): a variant
    with its own request and generation (``mqcd.Campaign.run``), the run's
    reference converted by MG5's alpha(0) formula over the twin's tagged
    photons."""

    twin = r["more"].pop("photon_twin", None)
    if not twin or not r["ref"] or r["ref"].get("format") != "required":
        return
    _model, restriction, fixed, scheme, _alpha = CODES[twin["code"]]
    data = _fixture(r["ref"]["path"].removeprefix(f"{FIX}/"))
    reference = {k: v for k, v in r["ref"].items() if k != "photon_conversion"}
    reference["photon_conversion"] = _photon_spec(
        data, _ew_sector(data), n=twin["tagged"]
    )
    r["more"].setdefault("variants", []).append({
        "name": twin["name"],
        "gating": True,
        "tier": r["tier"] if r["tier"] != "default" else "nightly",
        "restriction": restriction,
        "restriction_code": twin["code"],
        "fixed_parameters": dict(fixed),
        "scheme": scheme,
        "external_photons": twin["external_photons"],
        "parameters": {"aEW0M1": ALPHA0_INVERSE},
        "reference": reference,
        "points": {"nightly": list(range(len(data["points"])))},
        "extras": [],
        "extras_pending": {},
        "notes": f"loop.external_photons = {twin['external_photons']!r} on "
        f"{twin['code']}: {twin['tagged']} tagged photons, raw MadLoop x MG5's "
        "alpha(0) formula over them (one MadLoop job serves both twins)",
    })  # fmt: skip


for r in R:
    add_photon_twin(r)

# Extras the harness checks (``mqcd.IMPLEMENTED_EXTRAS``) and why the others
# wait (m-sm/PLAN.md §4.1 extras).
# PLAN §4.1's nc extra (rule 7, EW LC/NLC) is dropped: the user ruled Q4
# (2026-10-30 ~08:10) that EW LC/NLC is never supported (the typed
# colour-declaration-coverage refusal is permanent).
PENDING_EXTRAS = {
    "hel": "MS-REF (per-helicity SLOOPMATRIXHEL references)",
    "sp": "MS-REF (special points S1-S4)",
}
# A row's ``uv`` extra is rule 5's EW component form: it needs the
# reference's instrumented components (MadLoop's Born x CT split).
COMPONENT_FORMATS = {"ew-control", "madloop-components", "process-components"}

# The R2 rule (m-sm/PLAN.md §1.4 rule 1, Q7): per row the R2 couplings the
# engine inserts that MadLoop's label matching omits. The manifest lists
# them (they choose the reference: Recola, LL10, or MadLoop plus the omitted
# component, TT05); the harness finds them structurally on every row with
# MS-REF's called-coupling lists (``mqcd.rule_r2``): the R2 couplings of
# the counterterm program's admitted rules whose vertex a tree of the
# export's sectors can hold (``mqcd.r2_reachability``, ``mqcd.
# r2_export_sectors``; a joint row's other sectors have their own export),
# less the listed vanishing insertions (``R2_VANISHING``) and those whose MG5
# identical-coupling class the MadLoop export calls (MG5's restricted model
# merges couplings of equal value: LL03's export calls R2_AAU and R2_AAD
# where the UFO's V_R2AA groups take R2_AAu3, R2_AAc3, ...), must equal the
# listed set (tmp/ms-validate/probe-r2: {R2_G0tt_b} on LL10, TT04, SC09, the
# empty set on DY01 and TT02). Known (PLAN §1.4): LL10, TT04, SC09, TT05
# (R2_G0tt_b of V_ttG02).
# On the shipped (patched) models MadLoop's label matching meets every R2
# coupling of V_ttG02 (UFOmodeldb issue-1 patch: R2_G0tt_b split by loop
# content into R2_G0tt_b_WG and R2_G0tt_b_G; DECISIONS 2026-10-30 ~12:45,
# ~13:40), and the re-referenced rows (MS-UFO-PATCH) call them: no row
# lists an omission; the harness still finds the set structurally on every
# row with a call list. (On the unpatched models: R2_G0tt_b on LL10, TT04,
# SC09, TT05, tmp/ms-validate/probe-r2 and fs3.)
OMITTED: dict[str, list[str]] = {}
# A row's omitted component (``goldstone-mixing.json`` omitted_r2: MadLoop's
# Born x CT interference of the proportional coupling's amplitudes, scaled
# by the UFO's coupling ratio, ``tools/loop_reference/ufo_source_oracle.
# coupling_ratio``): TT05's until MS-UFO-PATCH re-referenced it; none now.
OMITTED_COMPONENT: dict[str, tuple[str, str, str]] = {}
# R2 couplings the engine inserts in the export's sectors whose insertion
# vanishes there, so MadLoop calls none (``mqcd.Row.r2_vanishing``): u d~ >
# e+ ve b b~ (QCD corrections, sector QCD^2 QED^8): the W self-energy R2
# with a quark loop on the QCD^2 QED^2 tree (g -> b b~, a colour octet)
# against the QED^4 Born (b b~ a singlet) is Tr T^a = 0; the reachability
# sweep is colour-blind (tmp/ms-validate/probe-r2; rule 1 = MadLoop CMS to
# 1e-12 at every point, fs2).
R2_VANISHING = {"CM08": ["R2_WWcs1", "R2_WWtb1", "R2_WWtb3", "R2_WWud1"]}


def coupling_ratio(name, numerator, denominator, card) -> str | None:
    ufo = GMU_UFO
    if not ufo.is_dir():
        return None
    from tools.loop_reference.ufo_source_oracle import coupling_ratio

    return repr(coupling_ratio(ufo, numerator, denominator, card))


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


# Rule 4's typed unpredicted sectors (m-sm/PLAN.md §1.4): legitimate for a
# single-correction or amplitude-order-capped request, never for a joint
# uncapped one. (QCD power, QED power) -> the slice's reason
# (``poles.UNPREDICTED_REASONS``).
UNPREDICTED = {
    # u d~ > e+ ve b b~ QCD=0 [QCD]: the QCD correction of an electroweak
    # Born; the operator would need the photon exchange of the QED^2-lower
    # tree (QCD^2 QED^2 amplitude), which the request does not correct
    # (MadLoop's [QCD] alike; rule 1 against it holds the sector).
    "CM08": {(2, 8): "uncorrected-exchange"},
    # u d~ > w+ b b~ QCD=0 [QCD] on loop_sm: likewise.
    "CM10": {(2, 6): "uncorrected-exchange"},
}


def produced_sectors(born, loops):
    """The squared sectors a request forms: every Born amplitude order times
    every loop amplitude order (``loop_orders``), largest QCD power first."""

    if not born or not loops:
        return []
    loops = [loops] if isinstance(loops, dict) else loops
    found = {(b[0] + x["QCD"], b[1] + x["QED"]) for b in born for x in loops}
    return [sector_orders(s) for s in sorted(found, reverse=True)]


def sector_orders(sector):
    return {"QCD": sector[0], "QED": sector[1]}


def ufo_parameters(model):
    """name -> nature of a model's UFO parameters (its ``parameters.py``)."""

    path = {
        GMU: GMU_UFO,
        QCDQED: UFODB / "loop_qcd_qed_sm",
        LOOPSM: WORKSPACE / "reference/sources/MG5_aMC_v3_7_0/models/loop_sm",
    }[model]
    text = (path / "parameters.py").read_text()
    pattern = r"Parameter\(\s*name\s*=\s*'([^']+)'\s*,\s*nature\s*=\s*'(\w+)'"
    return {m.group(1): m.group(2) for m in re.finditer(pattern, text)}


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
    if fmt == "cms-control":
        return len(data[reference["block"]]["points"])
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
    # The QED corrections of top-pair processes whose other legs are neutral
    # (g g > t t~ h / z / g): no massless charged leg, so no soft-collinear
    # photon pole (MS-REF's runs, tmp/ms-validate/m1 2026-10-30: ours
    # 1e-42 to 1e-38 of the Born, MadLoop's 1e-27 to 1e-20).
    "TV01": [{"sector": "QCD^4 QED^4", "coefficient": "double_pole"}],
    "TV02": [{"sector": "QCD^4 QED^4", "coefficient": "double_pole"}],
    "TT03": [{"sector": "QCD^6 QED^2", "coefficient": "double_pole"}],
    # The QCD x EW Born interference of s-channel q q~ > t t~ (a colour
    # octet against singlets: Tr T^a = 0; ours 0, MadLoop's 1e-17).
    "TT02": [{"sector": "QCD^2 QED^2", "coefficient": "born"}],
    # h h > h h: neutral scalars only, no IR pole and the UV poles cancel
    # (ours 1e-33, MadLoop's 1e-17 of the Born; tmp/ms-validate/f1 with the
    # plan-rank fix of finding F1).
    "SC07": [{"sector": "QED^6", "coefficient": "single_pole"}],
    # z z > h h: neutral legs only, as SC07 (ours 1e-32, MadLoop's 1e-16 of
    # the Born; tmp/ms-validate/fs2).
    "SC10": [{"sector": "QED^6", "coefficient": "single_pole"}],
    # a a > w+ w- with QED corrections: neutral initial photons, massive
    # charged final W's, so no soft-collinear photon pole (ours 7e-33,
    # MadLoop's 1.5e-34 of the Born; tmp/ms-validate/fs 2026-10-30).
    "PI02": [{"sector": "QED^6", "coefficient": "double_pole"}],
    # u d~ > t t~ w+: the QCD x EW Born interference vanishes (the top pair
    # from a gluon, a colour octet, against one from a photon or Z; ours 0,
    # MadLoop's 1e-17; tmp/ms-validate/f3).
    "TV03": [{"sector": "QCD^2 QED^4", "coefficient": "born"}],
    # g g > t t~ under CMS (Gamma_t = 0): as TT01 (tmp/ms-validate/cm4).
    "CM04": [{"sector": "QCD^4 QED^2", "coefficient": "double_pole"}],
}
# Rule 1's tolerance per row (nominal 1e-12; 1e-10 from 2->4 up where the
# providers' precision needs it, the user's ruling of 2026-10-29 ~01:12; and
# below ~1e-5 relative no finding, ~10:20), with the evidence of c1:
# TV06 (2->4) 1.16e-12 against MadLoop's quadruple precision at point 2
# (LL10's and TT06's relaxations were for their pre-patch references:
# Recola's double-precision finite part, MadLoop's double-precision CT
# parameters; MS-UFO-PATCH's MadLoop QP runs replace them).
# VV07 and TT03 (2->3) against MadLoop's quadruple precision (m1: up to
# 5.3e-11 and 1.4e-11): 1e-10, as the 2->4 rows; TT05 and TT06 (2->3)
# against MS-UFO-PATCH's MadLoop QP runs (fs4: up to 3.9e-12 and 1.2e-11).
RULE1 = {
    "TV06": 1e-10,
    "TV07": 1e-10,
    "VV07": 1e-10,
    "TT05": 1e-10,
    "TT06": 1e-10,
    "TT03": 1e-10,
    # ew-validate's udx_tbx_ew_mb run: MadLoop in double precision (status
    # 216; m1: 3.7e-11).
    "ST04": 1e-10,
    # SC03 (CKM, massive b and tau): 1.15e-12 (rule 1), 2.3e-12 (rule 5's
    # CT components, MadLoop's double-precision CT runs) in m2.
    "SC03": 1e-10,
    # SC02 (massive muon, m^2/s = 1e-8) against MadLoop's CutTools
    # quadruple precision (MS-REF's re-run): finite parts to 4.9e-9 (c7).
    "SC02": 1e-8,
    # SC04 (b b~ > w+ w-, massive b) and SC06 (w+ w- > w+ w-) against
    # MadLoop QP with status 329 at some points: 2.3e-10 and 6.3e-10
    # (tmp/ms-validate/f3, with the candidate F1 fix).
    "SC04": 1e-9,
    "SC06": 1e-9,
    # CM01 against MadLoop CMS double-precision exports (cms-ufo-standard-
    # gmu.json, cms-source-gmu.json; MS-CMS's test holds 1e-8).
    "CM01": 1e-8,
}
# Relaxed rules per row (the user's ruling of ~10:20, at most 1e-5): SC05's
# poles against Catani in double-double, 2.9e-14 and 4.2e-14 at point 0
# (the fixture's binary64 points are on shell and conserve momentum to
# rounding only); TT05's, 1.2e-16 to 2.7e-16, and TT06's, 9.5e-16 to
# 1.5e-14 (the massive QED operator's double-double prediction).
# TT03's vanishing QCD^6 QED^2 double pole in binary64 (m2: 7e-10 F_s, the
# rounding residue of the cancelling soft-photon terms between massive
# tops; double-double 1e-30): rules 2 and 4 against 1e-8 F_s there.
# Rule 5 after MS-POLES (m-sm/PLAN.md §1.4): the counterterms' UV part at
# the TECHNICAL epsIR = 0 equals MadLoop's at epsIR = 0 on
# restrict_with_technical (MS-REF's uux_emep_ew_tech, gg_ttx_ew_tech; the
# "all" totals at epsIR = 1 and 0, the "uv"/"ir" parts and their identities):
# MS-POLES's tests, delegated (``build_mqcd.py --junit``), not repeated here.
POLE_SPLIT = "tests/unit/test_loop_v2_ew_pole_split.py::"
DELEGATED = {
    "DY01": {
        "uv_eps_ir0": [
            POLE_SPLIT + "test_dy01_technical_card_pole_split_equals_madloop"
        ]
    },
    "TT01": {
        "uv_eps_ir0": [
            POLE_SPLIT + "test_tt01_technical_card_pole_split_equals_madloop"
        ]
    },
}
RELAXED = {
    # w+ w- > w+ w- (the gauge cancellations of longitudinal W scattering):
    # binary64 Born 1.1e-10 off double-double (tmp/ms-validate/f3, with the
    # candidate F1 fix; the user's ruling of ~10:20).
    "SC06": {"2": 1e-9},
    # Rule 4 per carrier (``mqcd.rule4_relaxed_key``): "4dd" relaxes only
    # the double-double poles against Catani, "4" only the binary64 ones
    # (reasons above; their binary64 poles pass in the bands of rule 2:
    # tmp/ms-validate fs, r6, r5).
    "SC05": {"4dd": 1e-12},
    "TT05": {"4dd": 1e-14},
    "TT06": {"4dd": 1e-13},
    "TT03": {"2": 1e-8, "4": 1e-8},
    # h h > h h: the vanishing QED^6 single pole in binary64 is the rounding
    # residue of the cancelling UV poles, -3.3e-15 = 1e-11 F_s at points 0
    # and 3 (double-double 8e-33; tmp/ms-validate/f4).
    "SC07": {"2": 1e-10, "4": 1e-10},
    # z z > h h: the same residue in binary64, 7.0e-13 = 2.6e-9 F_s at points
    # 0 and 3 (within its estimate, rule 3; double-double 4e-32;
    # tmp/ms-validate/fs2).
    "SC10": {"2": 1e-8, "4": 1e-8},
    # u d~ > e+ ve on restrict_ckm (the patched model's unitary CKM): the EW
    # counterterms omit the tau mass (MTA = 1.777 there; the user's retained
    # model limitation, DECISIONS 2026-10-30 ~12:45), so the QED^6 single
    # pole exceeds Catani's by MTA^2/(2 sw^2 (s - MW^2)) (alpha/2pi) Born
    # (MS-UFO-PATCH's note on udx_epve_ew_ckm), = MadLoop's: 3.1e-7 to
    # 1.1e-6 relative in both carriers (tmp/ms-validate/fs4).
    "SC03": {"4": 1e-5, "4dd": 1e-5},
}
# Rule 4 not formed (status partial): the massive-muon copy of the G_mu UFO
# (code Gm) changes only the muon mass in the restriction card, while the
# UFO writes the lepton field renormalisation for massless leptons, so its
# single pole (ours = MadLoop's) exceeds the massive QED operator by exactly
# 3 (alpha/2pi) Born (test_loop_v2_qed_catani's docstring; c1: 9.9e-5 =
# 3 x 3.30e-5 at point 0): not a reference of the operator.
NO_CATANI = {
    "LL02": "the massive-muon UFO copy: the UFO writes the lepton field "
    "renormalisation for massless leptons (single pole = the massive QED "
    "operator + 3 alpha/2pi Born)",
    "SC02": "the massive-muon UFO copy: the UFO writes the lepton field "
    "renormalisation for massless leptons (single pole = the massive QED "
    "operator + 3 alpha/2pi Born)",
    # (SC03, restrict_ckm: the O(lambda^3) Wolfenstein CKM kept a UV pole,
    # finding F6; the patched model's CKM is exactly unitary, so rule 4 is
    # formed again.)
}
# The Ward extra in the real-mass scheme (m-sm/PLAN.md §1.4 Ward): the
# identity holds only where no external coloured (gluon Ward) or charged
# (photon Ward) particle has an absorptive self-energy at its mass, which
# the scheme's real on-shell counterterms (Re Sigma) leave unrenormalised:
# TT03's gluon Ward residual of the EW virtual is 3.3e-4 of the physical
# scale in double-double with the top unstable (t -> b W open) and 5e-30 with
# MW = 180, MZ = 200 (tmp/ms-validate/probe-ward, 2026-10-30; bare, R2 and
# UV parts 1e-2 each). The top-pair rows, whose W and Z are internal, check
# it there; a row with an external W (its massless-fermion decays) or an
# external top beside an external W has no such point: its Ward check is
# CMS's (CM05, CM07, CM09: a gauge diagnostic, PLAN §1.5).
STABLE_TOP = {"MW": "180", "MZ": "200"}
WARD_PARAMETERS = {"TT03": STABLE_TOP, "TV07": STABLE_TOP}
NO_REAL_SCHEME_WARD = {
    "VV05": "the photon Ward identity with an external W: its absorptive "
    "self-energy (W -> f f') is not renormalised in the real-mass scheme "
    "(c = i residual 4e-4 of the scale, m1 2026-10-30); under CMS: CM09",
    "ST03": "the gluon Ward identity with an external top beside an external "
    "W: no parameter point closes t -> b W at the W's own mass; under CMS",
}
# Rows run on the native point inputs (the production route; rule 4 from the
# engine's operators on the Python-input Born): the 2->5 target and EWI-7's
# root-closure rows, checked with native inputs once EWI-7 lands (PLAN §3.2
# MS-VALIDATE item 6; a failure goes to the owner of the failing site).
NATIVE_ROWS = {"TV07", "TT04", "SC06", "SC07", "SC08", "SC09", "CM07"}

# The multiparticle rows (m-sm/PLAN.md §4.2 MP, Q2 (a)): composite rows of
# their parts, as M-QCD's M01. MG5_aMC adds the photon to p on these
# QED-perturbed models; the request states it through process.multiparticles
# (``multiparticles``), so the expansion is MadLoop's SubProcesses/P*
# (``madloop_subprocesses``: the "C Process:" lines of MS-REF's exports,
# workspace/reference/runs/msm/<run>/madloop-export). The members without a
# Born (MadLoop's loop-squared P0_gg_emep) are skipped with a typed
# loop-induced record (``skipped_members``, the public route's dry run);
# each P reference runs as its subprocess's own generation: (variant name,
# process, Born amplitude orders).
MP_PARTONS = ["g", "u", "c", "d", "s", "b", "u~", "c~", "d~", "s~", "b~", "a"]
MULTIPARTICLE_ROWS = {
    "MP01": {
        "madloop_subprocesses": {
            "P0_gg_emep": ["g g > e- e+"],
            "P2_uux_emep": ["c c~ > e- e+", "u u~ > e- e+"],
            "P3_ddx_emep": ["d d~ > e- e+", "s s~ > e- e+"],
            "P4_bbx_emep": ["b b~ > e- e+"],
            "P5_aa_emep": ["a a > e- e+"],
        },
        # g a > e- e+ has no amplitude at any order (MadLoop exports none).
        "skipped_members": ["g a > e- e+", "g g > e- e+"],
        "madloop_loop_squared": ["P0_gg_emep"],
        "parts": {
            "required/msm/pp_emep_ew_P2_uux_emep.json": (
                "P2",
                "u u~ > e- e+",
                [(0, 2)],
            ),
            "required/msm/pp_emep_ew_P3_ddx_emep.json": (
                "P3",
                "d d~ > e- e+",
                [(0, 2)],
            ),
            "required/msm/pp_emep_ew_P4_bbx_emep.json": (
                "P4",
                "b b~ > e- e+",
                [(0, 2)],
            ),
            "required/msm/pp_emep_ew_P5_aa_emep.json": ("P5", "a a > e- e+", [(0, 2)]),
        },
    },
    "MP02": {
        "madloop_subprocesses": {
            "P0_ga_ttx": ["g a > t t~"],
            "P2_gg_ttx": ["g g > t t~"],
            "P3_uux_ttx": ["c c~ > t t~", "u u~ > t t~"],
            "P4_ddx_ttx": ["d d~ > t t~", "s s~ > t t~"],
            "P5_aa_ttx": ["a a > t t~"],
            "P6_bbx_ttx": ["b b~ > t t~"],
        },
        "skipped_members": [],
        "madloop_loop_squared": [],
        # The QCD x EW Born interference of s-channel q q~ > t t~ vanishes
        # (a colour octet against singlets, as TT02); b b~ > t t~ has the
        # t-channel W.
        "vanishing": {
            "P3": [{"sector": "QCD^2 QED^2", "coefficient": "born"}],
            "P4": [{"sector": "QCD^2 QED^2", "coefficient": "born"}],
            # The QED corrections of photon-initiated top pairs: no massless
            # charged leg, no soft-collinear pole (ours 1e-35, MadLoop's
            # 1e-37 of the Born; tmp/ms-validate/mp1).
            "P0": [{"sector": "QCD^2 QED^4", "coefficient": "double_pole"}],
            "P5": [{"sector": "QED^6", "coefficient": "double_pole"}],
            # g g > t t~: the QCD x EW sector has no 1/eps^2 (as TT01).
            "P2": [{"sector": "QCD^4 QED^2", "coefficient": "double_pole"}],
        },
        "parts": {
            "required/msm/pp_ttx_ew_P0_ga_ttx.json": ("P0", "g a > t t~", [(1, 1)]),
            "required/msm/pp_ttx_ew_P2_gg_ttx.json": ("P2", "g g > t t~", [(2, 0)]),
            "required/msm/pp_ttx_ew_P3_uux_ttx.json": (
                "P3",
                "u u~ > t t~",
                [(2, 0), (0, 2)],
            ),
            "required/msm/pp_ttx_ew_P4_ddx_ttx.json": (
                "P4",
                "d d~ > t t~",
                [(2, 0), (0, 2)],
            ),
            "required/msm/pp_ttx_ew_P5_aa_ttx.json": ("P5", "a a > t t~", [(0, 2)]),
            "required/msm/pp_ttx_ew_P6_bbx_ttx.json": (
                "P6",
                "b b~ > t t~",
                [(2, 0), (0, 2)],
            ),
        },
    },
}


def multiparticle_parts(r, entry):
    """A multiparticle row as its parts (composite, as M-QCD's M01)."""

    spec = MULTIPARTICLE_ROWS[r["id"]]
    entry.update(
        status="composite",
        reference=None,
        madloop_subprocesses=spec["madloop_subprocesses"],
        multiparticles={"p": MP_PARTONS},
        skipped_members=spec["skipped_members"],
        madloop_loop_squared=spec["madloop_loop_squared"],
        points={},
    )
    entry.pop("pending", None)
    variants = []
    for path, (name, process, born) in spec["parts"].items():
        data = _fixture(path)
        run = next(
            x
            for x in MSREF[r["id"]]["references"]
            if x["fixture"] == path and x["status"] == "committed"
        )
        sectors = [s for s, _b, _c in _loop_sectors(data)]
        loops = loop_orders(born, entry["corrections"], sectors)
        reference = msref_reference(path, run)
        variants.append({
            "name": name,
            "gating": True,
            "tier": "nightly",
            "subprocess": True,
            "process": process,
            "born_orders": {"QCD": max(b[0] for b in born), "QED": max(b[1] for b in born)},
            "born_amplitude_orders": [{"QCD": q, "QED": e} for q, e in born],
            "loop_orders": loops,
            "sectors": [sector_orders(x) for x in sectors],
            "predicted_sectors": produced_sectors(born, loops),
            "reference": reference,
            "madloop_r2_called": called_couplings(reference),
            "points": {"nightly": list(range(len(data["points"])))},
            "vanishing": spec.get("vanishing", {}).get(name, []),
            "extras": [],
            "extras_pending": {},
            "notes": f"MadLoop SubProcesses/{data['mqcd_run']['subprocess']} of {r['process']} (its single-process generation, tools route)",
        })  # fmt: skip
    entry["variants"] = variants


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
        # Every sector the request forms is predicted unless the row states
        # otherwise (a joint QCD + QED request without caps must predict
        # every one, PLAN §1.4): the Born amplitude orders times the loop
        # orders, which may hold sectors beyond PLAN §4.2's list (JJ04's
        # QCD^2 QED^6: the QED correction of the QED^4 Born).
        "predicted_sectors": produced_sectors(
            born, loop_orders(born, corrections, sectors) if sectors else []
        ),
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
    for key in (
        "parameters",
        "inputs",
        "variants",
        "catani",
        "allow_anomalous_veto",
        "zero_points",
    ):
        if key in r["more"]:
            entry[key] = r["more"][key]
    if "veto" in r["more"]:
        entry["particle_veto"] = r["more"]["veto"]
    for (qcd, qed), reason in UNPREDICTED.get(r["id"], {}).items():
        sector = sector_orders((qcd, qed))
        entry["predicted_sectors"].remove(sector)
        entry["unpredicted_sectors"].append(sector)
        entry["unpredicted_reasons"][mqcd.sector_text(mqcd.sector_key(sector))] = reason
    if r["code"] in CMS_CODES:
        entry["mass_scheme"] = "complex-mass"
        if "ward" in r["extras"]:
            # Under CMS the Ward identity is a gauge diagnostic, not an
            # acceptance identity (m-sm/PLAN.md §1.4 Ward, §1.5).
            entry["diagnostic_extras"] = ["ward"]
        if reference and reference.get("format") == "required":
            # The run's fixed masses and widths (its card widths, zero for
            # an external unstable multiplet), those the model has; its
            # runtime parameters the model's external ones.
            data = json.loads((WT / reference["path"]).read_text())
            names = ufo_parameters(model)
            fixed = {k: v for k, v in data["fixed_parameters"].items() if k in names}
            entry["fixed_parameters"] = fixed
            ignored = sorted(set(data["fixed_parameters"]) - set(fixed))
            internal = sorted(
                k for k in data["parameters"] if names.get(k) != "external"
            )
            if internal:
                entry["ignored_parameters"] = internal
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
    if r["id"] in DELEGATED:
        entry["delegated"] = DELEGATED[r["id"]]
    if r["id"] in NATIVE_ROWS:
        entry["inputs"], entry["catani"] = "native", "engine"
    if r["id"] in WARD_PARAMETERS:
        entry["ward_parameters"] = WARD_PARAMETERS[r["id"]]
    if r["id"] in NO_CATANI:
        entry["catani"] = "none"
        entry["catani_reason"] = NO_CATANI[r["id"]]
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
        if extra == "ward" and r["id"] in NO_REAL_SCHEME_WARD:
            pend[extra] = NO_REAL_SCHEME_WARD[r["id"]]
        elif extra in PENDING_EXTRAS:
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
        if r["id"] in R2_VANISHING:
            entry["r2_vanishing"] = R2_VANISHING[r["id"]]
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
    if r["id"] in MULTIPARTICLE_ROWS and not waits:
        multiparticle_parts(r, entry)
    rows.append(entry)

# The nightly tier's file jobs (each within PLAN §3.2's 30 minutes): measured
# seconds per id where a run measured them (mqcd_manifest's packing), else
# DEFAULT_SECONDS per EW generation.
# (seconds, points) per id: a row process's own seconds (generation,
# export, its points in both carriers and its extras, + 60 s of imports and
# model compilation) from the campaign records (tmp/ms-validate c2, c4, m1,
# m2, 2026-10-29/30, 4 cores each, host load ~70-120); ids without a
# record take DEFAULT_SECONDS.
MEASURED_SECONDS: dict[str, tuple[int, int]] = {
    "DY01": (411, 4), "DY01@mwmz": (88, 4), "DY02": (360, 4), "DY03": (130, 4),
    "DY04": (370, 4), "DY05": (1115, 3), "DY07": (398, 4), "DY08": (405, 4),
    "JJ01": (380, 4), "JJ02": (361, 4), "JJ03": (234, 4), "JJ04": (433, 4),
    "LL01": (346, 3), "LL02": (359, 3), "LL03": (123, 3), "LL05": (389, 4),
    "LL08": (360, 4), "LL09": (360, 4), "LL10": (376, 3), "SC01": (344, 4),
    "SC02": (399, 4), "SC05": (86, 3), "SC09": (414, 3), "ST01": (365, 4),
    "ST02": (348, 3), "ST04": (343, 3), "TT01": (524, 3), "TT02": (365, 4),
    "TT03": (539, 4), "TT04": (420, 3), "TT05": (416, 3), "TT06": (431, 3),
    "TV01": (323, 4), "TV02": (355, 4), "TV06": (416, 3), "VJ01": (451, 4),
    "VJ02": (213, 4), "VJ03": (460, 3), "VV01": (389, 4), "VV01@4tev": (76, 2),
    "VV03": (378, 4), "VV05": (372, 4), "VV05@zero": (79, 3), "VV06": (306, 3),
    "VV07": (823, 4),
    # tmp/ms-validate fs, cm1, cm2 (2026-10-30): the photon-initiated and
    # complex-mass rows.
    "PI01": (339, 4), "PI01@all": (329, 4), "PI02": (399, 4), "PI03": (256, 4),
    "PI04": (336, 4), "CM01": (541, 4), "CM01@zero": (77, 3),
    "CM01@small": (750, 3), "CM01@source": (492, 4), "CM02": (508, 4),
    "CM03": (498, 4), "CM04": (376, 4), "CM08": (265, 4), "CM09": (870, 4),
    "CM10": (88, 4),
    # tmp/ms-validate/mp1 (2026-10-30): the multiparticle members.
    "MP01@P2": (382, 4), "MP01@P3": (397, 4), "MP01@P5": (344, 4),
    "MP02@P0": (291, 4), "MP02@P2": (279, 4), "MP02@P3": (393, 4),
    "MP02@P4": (414, 4), "MP02@P5": (365, 4),
    # The F1 and F2 rows once fixed (wall seconds of the CLI rows with MS-GEN,
    # tmp/ms-validate f4 and r5, 2026-10-30) and VV02 (mp1's record).
    "SC04": (206, 4), "SC06": (244, 4), "SC07": (130, 4), "SC08": (210, 4),
    "ST03": (120, 4), "TV03": (257, 4), "V301": (279, 4), "VH01": (149, 4),
    "VH02": (154, 4), "VH03": (201, 4), "MP01@P4": (145, 4),
    "MP02@P6": (188, 4), "VV02": (412, 4),
    # MS-UFODB's row (tmp/ms-validate/fs2, 2026-10-30).
    "SC10": (195, 4),
}  # fmt: skip
DEFAULT_SECONDS = 600
JOB_SECONDS = 1500
# Ids without a measurement whose cost differs from one EW generation.
ESTIMATED_SECONDS: dict[str, int] = {}


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
            and entry["status"] in ("active", "composite")
        ):
            ids.append(f"{entry['id']}@{v['name']}")
    return ids


# A variant with its own generation (another process, restriction, photon
# tags, mass scheme or reglog convention: ``mqcd.Campaign.run``) is packed on
# its own; the others share their base row's generation and stay in its job.
OWN_GENERATION = (
    "process",
    "restriction",
    "external_photons",
    "mass_scheme",
    "reglog_convention",
)


def packing_units(entry):
    ids = nightly_ids_of(entry)
    own = {
        f"{entry['id']}@{v['name']}"
        for v in entry.get("variants", ())
        if any(k in v and v[k] != entry.get(k) for k in OWN_GENERATION)
    }
    shared = [i for i in ids if i not in own]
    return ([shared] if shared else []) + [[i] for i in ids if i in own]


units = [
    unit
    for entry in sorted(rows, key=lambda e: e["id"])
    for unit in packing_units(entry)
]
jobs = []
for ids in units:
    seconds = sum(
        MEASURED_SECONDS.get(i, (ESTIMATED_SECONDS.get(i, DEFAULT_SECONDS), 0))[0]
        for i in ids
    )
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
        "measurement": "MEASURED_SECONDS per id (the campaign records), DEFAULT_SECONDS without one",
        "jobs": jobs,
    },
    "rows": rows,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(json.dumps(manifest, indent=1) + "\n")
print("rows", len(rows), "active", sum(e["status"] == "active" for e in rows),
      "nightly jobs", len(jobs))  # fmt: skip
