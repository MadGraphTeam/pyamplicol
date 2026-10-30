#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Write msm_campaign.json: the rows of m-sm/PLAN.md §4.2 and the MadLoop reference runs producing them.

Usage: make_msm_campaign.py tools/loop_reference/msm_campaign.json (the committed JSON is its output).
Driven by ``mqcd_campaign.py --campaign tools/loop_reference/msm_campaign.json`` (same format as the M-QCD
campaign; its ``layout`` puts work directories under runs/msm/ and fixtures under required/msm/)."""
import json
import sys
from pathlib import Path

ZERO_WIDTHS = {"WT": "0", "WZ": "0", "WW": "0", "WH": "0"}
GMU = "loop_qcd_qed_sm_Gmu"
# pyAmpliCol routes per model code (m-sm/PLAN.md §4.1); the request takes the fixture's parameters.
ROUTES = {
    "G0": {"model": GMU, "restriction": "default", "fixed_parameters": ZERO_WIDTHS, "scheme": "ew-gmu"},
    "Ga": {"model": GMU, "restriction": "a0", "fixed_parameters": ZERO_WIDTHS, "scheme": "ew-gmu-a0",
           "note": "aEW0M1 = 137.035999; MadLoop's raw values equal G0's (no coupling uses aEW0): tagged photons "
                   "compare against raw MadLoop x MG5's alpha(0) formula over the tagged legs"},
    "Gb": {"model": GMU, "restriction": "with_b_mass", "fixed_parameters": {"MB": "4.5", "ymb": "4.5", **ZERO_WIDTHS},
           "scheme": "ew-gmu-b-mass",
           "note": "MadLoop: the loop_qcd_qed_sm_Gmu_py3_b_mass copy (restrict_default.dat with MB = ymb = 4.5)"},
    "Gm": {"model": "loop_qcd_qed_sm_Gmu_massive_muon_py3", "restriction": "default", "fixed_parameters": ZERO_WIDTHS,
           "scheme": "ew-gmu-mm", "note": "declared [loop.model] (no shipped profile)"},
    "Gk": {"model": GMU, "restriction": "ckm", "fixed_parameters": ZERO_WIDTHS, "scheme": "ew-gmu-ckm"},
    "Gt": {"model": GMU, "restriction": "with_technical", "fixed_parameters": ZERO_WIDTHS, "scheme": "ew-gmu-tech",
           "note": "its own MT = 174.3, MH = 120; epsIR = 0 runs (MS-POLES oracle)"},
    "Gc": {"model": GMU, "restriction": "default", "mass_scheme": "complex-mass", "fixed_parameters": {},
           "scheme": "ew-gmu-cms",
           "note": "card widths; an external unstable multiplet's width is 0 (the run's parameter_overrides)"},
    "Gca": {"model": GMU, "restriction": "a0", "mass_scheme": "complex-mass", "fixed_parameters": {},
            "scheme": "ew-gmu-a0-cms", "note": "as Gc on the a0 restriction"},
    "Lc": {"model": "loop_sm", "restriction": "no_b_mass", "mass_scheme": "complex-mass",
           "fixed_parameters": {"WT": "1.4915", "WZ": "0", "WW": "0", "WH": "0"}, "scheme": "qcd-cms",
           "note": "MadLoop: loop_sm-no_b_mass under CMS, which MG5 switches to (aEWM1, MZ, MW) inputs; MW = the "
                   "tree-level value of the alpha_fixed scheme, so the couplings are the same"},
    "Az": {"model": "loop_qcd_qed_sm", "restriction": "default", "fixed_parameters": ZERO_WIDTHS,
           "scheme": "ew-qcd-qed-sm"},
    "L5": {"model": "loop_sm", "restriction": "no_b_mass", "fixed_parameters": ZERO_WIDTHS, "scheme": "qcd",
           "note": "M-QCD route (the epsilon-sign regression)"},
}

rows, runs = [], {}


def run(rid, key=None, export=None, points=None, helicities=None, split_points=False, note=None, binding=True,
        point_status=None, notes=None, madloop_params=None, second=(), trigger=None):
    key = key or rid
    r = {"id": rid, "process": key, "export": export or f"runs/msm/{key}/madloop-export",
         "points": points or {"generator": "exact"}}
    if second:
        r["second_providers"] = list(second)
        r["second_provider_trigger"] = trigger
    if madloop_params:
        r["madloop_params"] = madloop_params  # over madloop_settings.evaluation's, this run only
    if helicities:
        r["helicities"] = helicities
    if split_points:
        r["split_points"] = True
    if not binding:
        r["binding"] = False
    if point_status:
        r["point_status"] = point_status
    if notes:
        r["reference_notes"] = notes
    if note:
        r["note"] = note
    runs[rid] = r
    return rid


def row(rid, cls, process, code, ref, tier="n", extras=(), runs_=(), fixtures=(), note=None, primary=None,
        helicity_reference=None, sectors=None, r2_exports=None):
    e = {"row": rid, "class": cls, "process": process, "restriction_code": code, "reference_kind": ref,
         "tier": tier, "extras": list(extras), "runs": list(runs_), "existing_fixtures": list(fixtures)}
    if r2_exports:
        # Existing fixture -> the MadLoop exports giving its R2 name list, or why it has none
        # (default: runs/required/<name>/madloop-export of required/<name>.json; mqcd_campaign.py existing-r2).
        e["existing_r2_exports"] = r2_exports
    if sectors:
        e["sectors"] = sectors
    if note:
        e["note"] = note
    if helicity_reference:
        if helicity_reference not in e["runs"] or not runs[helicity_reference].get("helicities"):
            raise ValueError(f"{rid}: helicity_reference {helicity_reference} is not a per-helicity run of the row")
        e["helicity_reference"] = helicity_reference
    if primary:
        e["primary_provider"] = primary
    rows.append(e)


def S(**kw):
    return {"generator": "supplied", "family": "regular", **kw}


def F(fixture, half=True):
    return {"generator": "fixture", "fixture": fixture, "half_scale_point": half}


EWI7 = "[EWI-7]"
TOPUP = "top-up: the missing correction sector at the existing fixture's points (+ the mu_R = mu_0/2 copy of point 1)"
CKM_REMNANT = ("UFOmodeldb issue-1 patch: exactly unitary CKM, the O(lambda^3) remnant (-2.1e-2 (alpha/2pi) Born) is "
               "gone; the EW counterterms omit the tau mass (MTA = 1.777 on restrict_ckm), a retained model "
               "limitation: the e^6 single pole exceeds the IR prediction by MTA^2/(2 sw^2 (s - MW^2)) (alpha/2pi) "
               "Born (scheme ew-gmu-ckm) -> MS-VALIDATE rule 4")
# The model patch of UFOmodeldb issue 1 / mg5amcnlo#475 (user rule 2026-10-30 ~12:45): MadLoop exports of the
# patched models insert R2_G0tt_b (split by loop content), and the G_mu charge counterterm has its b-mass term.
UFOPATCH = ("MadLoop QP on the patched model (UFOmodeldb issue 1: R2_G0tt_{d,s,b} split by loop content, so MadLoop "
            "inserts them; G_mu b-mass charge counterterm) [MS-UFO-PATCH]")
UFOPATCH_RECOLA = ("independent check of the UFOmodeldb issue-1 patch: Recola's counterterms and R2 terms are its "
                   "own (workspace/reports/engine-v2/upstream/ufo-patch-validation.md)")

# LL: lepton-only
CTL = "runs/msm/{}/madloop-export"  # --no-compile export of a control fixture's MadLoop command (R2 name list)
MM_CT = ("the model's muon counterterms are the massless muon's: single pole +3/2 Q^2 (alpha/2pi) Born per muon "
         "leg (scheme ew-gmu-mm)")
row("LL01", "W-lep", "e- e+ > mu- mu+", "G0", "E", extras=["ap", "uv"],
    fixtures=["electroweak-mumu-control.json", "electroweak-mumu-scale-control.json"], sectors=["e^6"],
    r2_exports={f: [CTL.format("emep_mummp_ew_ctl")] for f in ("electroweak-mumu-control.json",
                                                                "electroweak-mumu-scale-control.json")})
row("LL02", "W-lep", "e- e+ > mu- mu+ (massive mu)", "Gm", "E", fixtures=["electroweak-massive-mumu-control.json"],
    sectors=["e^6"], note=MM_CT,
    r2_exports={"electroweak-massive-mumu-control.json": [CTL.format("emep_mummp_ew_mm_ctl")]})
row("LL03", "W-lep", "e- e+ > e- e+", "Az", "E", fixtures=["required/emep_emep_ew.json"], sectors=["e^6"],
    note="lepton line through the loop")
row("LL05", "W-lep", "e- e+ > w+ w-", "G0", "N", runs_=[run("emep_wpwm_ew")], sectors=["e^6"], note=EWI7)
row("LL08", "W-lep", "e- e+ > mu- mu+ a", "Ga", "N", extras=["a0"], runs_=[run("emep_mummpa_ew_a0")], sectors=["e^8"],
    note="final photon tagged")
row("LL09", "W-lep", "e- e+ > t t~", "G0", "N", runs_=[run("emep_ttx_ew")], sectors=["e^6", "s^2e^4"])
row("LL10", "W-lep", "e- e+ > t t~ h", "G0", "N", fixtures=["required/emep_ttxh_ew.json"], sectors=["e^8"],
    runs_=[run("emep_ttxh_ew", points=F("required/emep_ttxh_ew.json"), second=["recola"], trigger=UFOPATCH_RECOLA)],
    note=UFOPATCH)
# DY: Drell-Yan and lepton-quark
row("DY01", "W-DY", "u u~ > e- e+", "G0", "N", extras=["uv", "hel", "sp:S3"], sectors=["s^2e^4", "e^6"],
    runs_=[run("uux_emep_ew", helicities="all"),
           run("uux_emep_ew_mwmz", export="runs/msm/uux_emep_ew/madloop-export",
               points={"generator": "run", "run": "uux_emep_ew"}, note="S3: runtime MW = 80.379, MZ = 91.1876"),
           run("uux_emep_ew_tech", binding=False,
               note="MS-POLES oracle on the technical card (Gt: MT = 174.3, MH = 120), epsIR = 1"),
           run("uux_emep_ew_tech_ir0", export="runs/msm/uux_emep_ew_tech/madloop-export", binding=False,
               points={"generator": "run", "run": "uux_emep_ew_tech"},
               note="MS-POLES oracle: the technical card at epsIR = 0 (UV part of the counterterms alone)")],
    helicity_reference="uux_emep_ew")
row("DY02", "W-DY", "u d~ > e+ ve", "G0", "N", runs_=[run("udx_epve_ew")], sectors=["s^2e^4", "e^6"], note=EWI7)
row("DY03", "W-DY", "u u~ > e- e+ (alpha(M_Z) twin)", "Az", "N", runs_=[run("uux_emep_ew_az")], sectors=["e^6"])
row("DY04", "W-DY", "e- u > e- u", "G0", "N", runs_=[run("emu_emu_ew")], sectors=["s^2e^4", "e^6"])
row("DY05", "W-DY", "u u~ > e- e+ g", "G0", "E", extras=["ward", "joint", "ap", "nc"], sectors=["s^4e^4", "s^2e^6"],
    fixtures=["required/uux_emepg_ew.json"],
    runs_=[run("uux_emepg_ew_qcd", points=F("required/uux_emepg_ew.json"), note=TOPUP + ": s^4e^4")])
row("DY07", "W-DY", "u u~ > e- e+ mu- mu+", "G0", "N", "n*", runs_=[run("uux_emepmummp_ew")], sectors=["e^10"],
    note="two lepton lines; the 2->4 cost probe")
row("DY08", "W-DY", "u u~ > e- e+ g g", "G0", "N", "n*", extras=["nc"], runs_=[run("uux_emepgg_ew")],
    sectors=["s^6e^4", "s^4e^6"])
# VJ, VV, V3, VH
row("VJ01", "W-V", "u u~ > z g", "G0", "N", extras=["ward"], runs_=[run("uux_zg_ew")], sectors=["s^4e^2", "s^2e^4"])
row("VJ02", "W-V", "u d~ > w+ g", "G0", "N", "d", extras=["uv"], runs_=[run("udx_wpg_ew")],
    sectors=["s^4e^2", "s^2e^4"])
row("VJ03", "W-V", "u u~ > a g", "Ga", "E", extras=["a0", "ward"], sectors=["s^4e^2", "s^2e^4"],
    fixtures=["required/uux_ag_ew.json"],
    runs_=[run("uux_ag_ew_qcd", points=F("required/uux_ag_ew.json"), note=TOPUP + ": s^4e^2 (ew-gmu = Ga raw)")])
row("VV01", "W-V", "u u~ > w+ w-", "G0", "N", extras=["sp:S4"], sectors=["s^2e^4", "e^6"], note=EWI7,
    runs_=[run("uux_wpwm_ew"),
           run("uux_wpwm_ew_4tev", "uux_wpwm_ew", points=S(sqrt_s=["4000", "4000"], half_scale_point=False),
               note="S4: sqrt(s) = 4 TeV (EW Sudakov region, longitudinal-W cancellations)")])
row("VV02", "W-V", "u u~ > z z", "G0", "N", extras=["hel"], runs_=[run("uux_zz_ew", helicities="all")],
    sectors=["s^2e^4", "e^6"], helicity_reference="uux_zz_ew")
row("VV03", "W-V", "u d~ > w+ z", "G0", "N", runs_=[run("udx_wpz_ew", points=S())], sectors=["s^2e^4", "e^6"],
    note=EWI7)
row("VV05", "W-V", "u d~ > w+ a", "Ga", "N", extras=["a0", "ward", "sp:S1"], sectors=["s^2e^4", "e^6"],
    runs_=[run("udx_wpa_ew_a0"),
           run("udx_wpa_ew_a0_zero", "udx_wpa_ew_a0",
               points=S(family="radiation-zero", count=2, zero_cosine="-1/3", neighbour_cosine="-1/5",
                        half_scale_point=False, madloop_qp_point=True),
               point_status={str(i): {"comparison": "absolute", "scale_row": 2,
                                      "reason": "§4.1 S1 radiation zero: the Born and the double pole vanish to "
                                                "rounding; compare absolutely against the regular neighbour's Born"}
                             for i in (0, 1)},
               split_points=True,
               note="S1: Born-zero points cos(u, photon) = -1/3 and one regular neighbour; one job per point: "
                    "after MadLoop's initialisation at a Born-zero point the neighbour's QCD double pole missed "
                    "the universal one by 2.9e-5 in a three-point job (alone: 1e-15)")])
row("VV06", "W-V", "u u~ > a a", "Ga", "E", extras=["a0"], sectors=["s^2e^4", "e^6"],
    fixtures=["required/uux_aa_ew.json"],
    runs_=[run("uux_aa_ew_qcd", points=F("required/uux_aa_ew.json"), note=TOPUP + ": s^2e^4 (ew-gmu = Ga raw)")])
row("VV07", "W-V", "u u~ > w+ w- g", "G0", "N", extras=["ward"], runs_=[run("uux_wpwmg_ew")],
    sectors=["s^4e^4", "s^2e^6"], note=EWI7)
row("V301", "W-V", "u u~ > w+ w- z", "G0", "N", runs_=[run("uux_wpwmz_ew", points=S())], sectors=["e^8"], note=EWI7)
row("VH01", "W-V", "u u~ > z h", "G0", "N", runs_=[run("uux_zh_ew", points=S())], sectors=["s^2e^4", "e^6"])
row("VH02", "W-V", "u d~ > w+ h", "G0", "N", runs_=[run("udx_wph_ew", points=S())], sectors=["s^2e^4", "e^6"])
row("VH03", "W-V", "u d > u d h QCD=0", "G0", "N", runs_=[run("ud_udh_ew")], sectors=["s^2e^6", "e^8"],
    note="VBF; capped (QCD=0), so typed unpredicted sectors are allowed")
# TT, TV, ST
row("TT01", "W-top", "g g > t t~", "G0", "E", extras=["joint", "ap", "uv"], sectors=["s^6", "s^4e^2"],
    fixtures=["required/gg_ttx.json", "required/gg_ttx_ew.json"],
    runs_=[run("gg_ttx_ew_tech", binding=False,
               note="MS-POLES oracle on the technical card (Gt: MT = 174.3, MH = 120), epsIR = 1"),
           run("gg_ttx_ew_tech_ir0", export="runs/msm/gg_ttx_ew_tech/madloop-export", binding=False,
               points={"generator": "run", "run": "gg_ttx_ew_tech"},
               note="MS-POLES oracle: the technical card at epsIR = 0 (UV part of the counterterms alone)")])
row("TT02", "W-top", "u u~ > t t~", "G0", "N", extras=["so"], runs_=[run("uux_ttx_ew")],
    sectors=["s^6", "s^4e^2", "s^2e^4", "e^6"])
row("TT03", "W-top", "g g > t t~ g", "G0", "N", extras=["ward"], runs_=[run("gg_ttxg_ew")], sectors=["s^8", "s^6e^2"])
row("TT04", "W-top", "t t~ > t t~ QCD=0", "G0", "N", fixtures=["required/ttx_ttx_ew.json"], sectors=["e^6"],
    runs_=[run("ttx_ttx_ew", points=F("required/ttx_ttx_ew.json"), second=["recola"], trigger=UFOPATCH_RECOLA)],
    note=f"{UFOPATCH}; root mixing; ew-validate's fixture's points {EWI7}")
row("TT05", "W-top", "g t > t t t~", "G0", "N", fixtures=["goldstone-mixing.json"], sectors=["s^2e^6"],
    r2_exports={"goldstone-mixing.json": ["runs/required/gt_tttx_ew/madloop-export"]},
    runs_=[run("gt_tttx_ew", points=S(), second=["recola"], trigger=UFOPATCH_RECOLA)],
    note=f"{UFOPATCH}; goldstone-mixing.json gt_tttx_ew (MadLoop double on the unpatched model, R2_G0tt_b omitted) "
         "stays the components control")
row("TT06", "W-top", "g b > t t~ b (massive b)", "Gb", "N", fixtures=["goldstone-mixing.json"], sectors=["s^2e^6"],
    r2_exports={"goldstone-mixing.json": ["runs/required/gb_ttxb_ew_mb/madloop-export"]},
    runs_=[run("gb_ttxb_ew_mb", points=S(), second=["recola"], trigger=UFOPATCH_RECOLA)],
    note=f"{UFOPATCH}; goldstone-mixing.json gb_ttxb_ew_mb (MadLoop double on the unpatched model) stays the "
         f"components control; binary64 point 0 outside the O1 scope (DD asserted) {EWI7}")
row("TV01", "W-top", "g g > t t~ h", "G0", "N", runs_=[run("gg_ttxh_ew", points=S())], sectors=["s^6e^2", "s^4e^4"])
row("TV02", "W-top", "g g > t t~ z", "G0", "N", runs_=[run("gg_ttxz_ew", points=S())], sectors=["s^6e^2", "s^4e^4"])
row("TV03", "W-top", "u d~ > t t~ w+", "G0", "N", extras=["so"], runs_=[run("udx_ttxwp_ew", points=S())],
    sectors=["s^6e^2", "s^4e^4", "s^2e^6"], note="mixed Born orders")
row("TV06", "W-top", "g g > t t~ e- e+", "G0", "E", fixtures=["required/gg_ttxemep_ew.json"], sectors=["s^4e^6"])
row("TV07", "W-top", "g g > t t~ e- e+ g (required target)", "G0", "E", "c", extras=["ward", "joint", "G1"],
    fixtures=["required/gg_ttxemepg_ew.json", "required/gg_ttxemepg_qcd.json"], sectors=["s^6e^6", "s^8e^4"])
row("ST01", "W-singletop", "u b > d t", "G0", "N", runs_=[run("ub_dt_ew")], sectors=["s^2e^4", "e^6"])
row("ST02", "W-singletop", "u d~ > t b~ QCD=0", "G0", "E", fixtures=["required/udx_tbx_ew.json"], sectors=["e^6"],
    note=f"ew-validate's fixture (MadLoop + Recola) {EWI7}")
row("ST03", "W-singletop", "g b > t w-", "G0", "N", extras=["ward"], runs_=[run("gb_twm_ew", points=S())],
    sectors=["s^4e^2", "s^2e^4"])
row("ST04", "W-singletop", "u d~ > t b~ QCD=0 (massive b)", "Gb", "N", fixtures=["required/udx_tbx_ew_mb.json"],
    sectors=["e^6"],
    runs_=[run("udx_tbx_ew_mb", points=F("required/udx_tbx_ew_mb.json"), second=["recola"],
               trigger=UFOPATCH_RECOLA)],
    note=f"{UFOPATCH}: the unpatched model omitted dMB_eCoup_UV_EW (Recola - MadLoop = 9.48e-5 x Born on "
         f"required/udx_tbx_ew_mb.json, ew-validate's run, whose points this run re-evaluates) {EWI7}")
# JJ, PI
row("JJ01", "W-jets", "u u~ > d d~", "G0", "N", extras=["so", "uv"], runs_=[run("uux_ddx_ew")],
    sectors=["s^6", "s^4e^2", "s^2e^4", "e^6"])
row("JJ02", "W-jets", "u u~ > u u~", "G0", "N", runs_=[run("uux_uux_ew")], sectors=["s^6", "s^4e^2", "s^2e^4", "e^6"],
    note="identical flavours")
row("JJ03", "W-jets", "u u~ > g g", "G0", "N", runs_=[run("uux_gg_ew")], sectors=["s^6", "s^4e^2"])
row("JJ04", "W-jets", "u u~ > d d~ g", "G0", "N", extras=["so"], runs_=[run("uux_ddxg_ew")],
    sectors=["s^8", "s^6e^2", "s^4e^4"], note="cross-order Catani")
row("PI01", "W-photon", "a a > e- e+", "G0", "N", extras=["a0"], runs_=[run("aa_emep_ew")], sectors=["e^6"],
    note="one job serves the untagged G0 row and its Ga twin (\"all\": both photons tagged) [MS-PHOTON]")
row("PI02", "W-photon", "a a > w+ w-", "G0", "N", runs_=[run("aa_wpwm_ew")], sectors=["e^6"],
    note=f"untagged photons [MS-PHOTON] {EWI7}")
row("PI03", "W-photon", "a g > u u~", "G0", "N", runs_=[run("ag_uux_ew")], sectors=["s^4e^2", "s^2e^4"],
    note="untagged photon [MS-PHOTON]")
row("PI04", "W-photon", "a u > a u", "Ga", "N", extras=["a0"], runs_=[run("au_au_ew_a0")], sectors=["s^2e^4", "e^6"],
    note="initial photon untagged, final tagged [MS-PHOTON]")
# CM
row("CM01", "W-CMS", "e- e+ > mu- mu+ CMS", "Gc", "E", extras=["ap", "sp:S3"], sectors=["e^6"],
    fixtures=["cms-ufo-standard-gmu.json", "cms-source-gmu.json"],
    r2_exports={f: [CTL.format("emep_mummp_ew_cms_ctl")] for f in ("cms-ufo-standard-gmu.json", "cms-source-gmu.json")},
    note="MadLoop double references kept (§1.3); S3 widths x 0.001: the fixture's small-width control")
row("CM02", "W-CMS", "u u~ > e- e+ CMS", "Gc", "N", extras=["sp:S2"], sectors=["s^2e^4", "e^6"],
    runs_=[run("uux_emep_cms", points=S(sqrt_s=["91.188", "100", "1000"]),
               note="S2: sqrt(s) = M_Z, 100 GeV and 1 TeV")])
row("CM03", "W-CMS", "u d~ > e+ ve CMS", "Gc", "N", extras=["sp:S2"], sectors=["s^2e^4", "e^6"], note=EWI7,
    runs_=[run("udx_epve_cms", points=S(sqrt_s=["80.419", "90", "1000"]),
               note="S2: sqrt(s) = M_W, 90 GeV and 1 TeV")])
row("CM04", "W-CMS", "g g > t t~ CMS (Gamma_t = 0)", "Gc", "N", runs_=[run("gg_ttx_cms")], sectors=["s^6", "s^4e^2"],
    note="EW-25: external top stable (WT = 0)")
row("CM05", "W-CMS", "u u~ > e- e+ g CMS", "Gc", "N", extras=["ward"], runs_=[run("uux_emepg_cms")],
    sectors=["s^4e^4", "s^2e^6"])
row("CM07", "W-CMS", "g g > t t~ e- e+ g CMS (Gamma_Z, Gamma_W > 0, Gamma_t = 0)", "Gc", "N", "c", extras=["ward"],
    sectors=["s^6e^6"],
    runs_=[run("gg_ttxemepg_cms", points=F("required/gg_ttxemepg_ew.json", half=False), split_points=True,
               note="[U4] acceptance: MadLoop CMS at the points of the zero-width reference required/"
                    "gg_ttxemepg_ew.json, one job per point")])
row("CM08", "W-CMS", "u d~ > e+ ve b b~ QCD=0 CMS (Gamma_t, Gamma_W > 0)", "Gc", "N", "n*",
    runs_=[run("udx_epvebbx_cms")], sectors=["s^2e^8"], note="coloured width [MS-CMS-N]")
row("CM09", "W-CMS", "u d~ > e+ ve a CMS (Gamma_W, Gamma_Z > 0)", "Gca", "N", extras=["a0", "ward"],
    runs_=[run("udx_epvea_cms")], sectors=["s^2e^6", "e^8"],
    note="CMS x tagged photon: raw MadLoop CMS x MG5's formula (the real part of the complex conversion) [MS-CMS-N]")
row("CM10", "W-CMS", "u d~ > w+ b b~ QCD=0 CMS (Gamma_t > 0)", "Lc", "N", runs_=[run("udx_wpbbx_cms")],
    sectors=["s^2e^6"], note="CMS on loop_sm (no CMSParam), coloured width [MS-CMS-N]")
# MP (multiparticle; runs per Born subprocess directory are added once the export lists them)
def member(process, directory, pdgs, key=None):
    """One run per Born subprocess directory of a multiparticle export (exact points of the parent's masses)."""
    rid = run(f"{process}_{directory}", key or process, export=f"runs/msm/{process}/madloop-export",
              points={"generator": "exact", "pdgs": pdgs})
    runs[rid].update({"subprocess": directory, "pdgs": pdgs})
    return rid


MP_NOTE = ("Q2(a): only Born members are compared; MG5 adds the photon to p on this QED-perturbed model, so its "
           "multi-P export also holds the photon-initiated members (references for requests that add the photon "
           "through process.multiparticles)")
row("MP01", "W-multi", "p p > e- e+", "G0", "N", sectors=["per Born subprocess"],
    runs_=[member("pp_emep_ew", "P2_uux_emep", [2, -2, 11, -11]),
           member("pp_emep_ew", "P3_ddx_emep", [1, -1, 11, -11]),
           member("pp_emep_ew", "P4_bbx_emep", [5, -5, 11, -11]),
           member("pp_emep_ew", "P5_aa_emep", [22, 22, 11, -11], "pp_emep_ew_aa")],
    note=MP_NOTE + "; P0_gg_emep is MG5's loop-squared member (sqrvirt), skipped (typed loop-induced on the "
                   "pyAmpliCol side)")
row("MP02", "W-multi", "p p > t t~", "G0", "N", sectors=["per Born subprocess"],
    runs_=[member("pp_ttx_ew", "P2_gg_ttx", [21, 21, 6, -6]),
           member("pp_ttx_ew", "P3_uux_ttx", [2, -2, 6, -6]),
           member("pp_ttx_ew", "P4_ddx_ttx", [1, -1, 6, -6]),
           member("pp_ttx_ew", "P6_bbx_ttx", [5, -5, 6, -6]),
           member("pp_ttx_ew", "P0_ga_ttx", [21, 22, 6, -6], "pp_ttx_ew_ga"),
           member("pp_ttx_ew", "P5_aa_ttx", [22, 22, 6, -6], "pp_ttx_ew_aa")],
    note=MP_NOTE)
# SC
row("SC01", "W-scheme", "e- e+ > u u~", "G0", "E", extras=["nc"], fixtures=["electroweak-eeuu-control.json"],
    sectors=["e^6"], r2_exports={"electroweak-eeuu-control.json": [CTL.format("emep_uux_ew_ctl")]})
row("SC02", "W-scheme", "u u~ > mu- mu+ (massive mu)", "Gm", "N", note=MM_CT,
    runs_=[run("uux_mummp_ew_mm", points=S(), madloop_params={"MLReductionLib": "1"},
               note="CutTools only: MadLoop's quadruple-precision Ninja stage mis-evaluates the e^6 sector at "
                    "m_mu^2/s ~ 1e-9 (3 of 4 points, wrong single pole, undetected by its own test)")],
    sectors=["s^2e^4", "e^6"])
row("SC03", "W-scheme", "u d~ > e+ ve (CKM)", "Gk", "N",
    runs_=[run("udx_epve_ew_ckm", note=CKM_REMNANT)], sectors=["s^2e^4", "e^6"], note=f"{CKM_REMNANT} {EWI7}")
row("SC04", "W-scheme", "b b~ > w+ w- (massive b)", "Gb", "N",
    runs_=[run("bbx_wpwm_ew_mb", points=S()),
           run("bbx_wpwm_ew_mb_qed", points={"generator": "run", "run": "bbx_wpwm_ew_mb"}, binding=False,
               second=["recola"], trigger=UFOPATCH_RECOLA,
               note="control: the e^6 sector alone ([virt=QED]) at the joint run's points, MadLoop and Recola")],
    sectors=["s^2e^4", "e^6"], note="O1 scope per point (m_b^2/s cancellation)")
row("SC05", "W-scheme", "u u~ > e- e+ g g / d s b (epsilon sign)", "L5", "E", fixtures=["epsilon-sign.json"],
    note="regression", r2_exports={"epsilon-sign.json": "QCD-only loop_sm reference: no EW R2"})
row("SC06", "W-scheme", "w+ w- > w+ w-", "G0", "N", runs_=[run("wpwm_wpwm_ew", points=S())], sectors=["e^6"],
    note=f"massive initial states, root closure {EWI7}")
row("SC07", "W-scheme", "h h > h h", "G0", "N", runs_=[run("hh_hh_ew", points=S())], sectors=["e^6"],
    note=f"scalar EW loops, root closure {EWI7}")
row("SC08", "W-scheme", "t t~ > w+ w-", "G0", "N", runs_=[run("ttx_wpwm_ew", points=S())], sectors=["e^6"],
    note=f"root closure, R2 rule checked first {EWI7}")
row("SC09", "W-scheme", "t t~ > z h QCD=0", "G0", "N", fixtures=["required/ttx_zh_ew.json"], sectors=["e^6"],
    runs_=[run("ttx_zh_ew", points=F("required/ttx_zh_ew.json"), second=["recola"], trigger=UFOPATCH_RECOLA)],
    note=f"{UFOPATCH}; root mixing; ew-validate's fixture's points {EWI7}")
row("SC10", "W-scheme", "z z > h h", "G0", "N", sectors=["e^6"],
    runs_=[run("zz_hh_ew", points=S(), second=["recola"],
               trigger="diagnostic: Recola's R2 terms are not the UFO's, so it decides UFOmodeldb's R2_ZZHH fix"),
           run("zz_hh_ew_mg5", points={"generator": "run", "run": "zz_hh_ew"}, binding=False,
               note="control: MadLoop on MG5_aMC's online-database G_mu model, whose R2_ZZHH predates UFOmodeldb's "
                    "fix (the only difference)")],
    note="the R2 vertices Z Z H H and Z Z G0 G0 (coupling R2_ZZHH, fixed in UFOmodeldb 6ca4b120; no other row "
         "reaches them) on the UFOmodeldb model [MS-UFODB]")

# Rule 5 (m-sm/PLAN.md §1.4): bare, R2 and UV-CT components per sector on one row per class
# (madloop_components.py; the uv extras DY01, VJ02, JJ01, TT01 (its technical-card run) and one row of every
# other class).
for rid in ("uux_emep_ew", "udx_wpg_ew", "uux_ddx_ew", "emep_ttx_ew", "uux_ttx_ew", "gg_ttx_ew_tech", "ub_dt_ew",
            "ag_uux_ew", "gg_ttx_cms", "pp_emep_ew_P2_uux_emep", "udx_epve_ew_ckm"):
    runs[rid]["components"] = f"required/msm/components/{rid}.json"
# CM09: the export's own photon conversion parameter per mu_R (m-sm/PLAN.md §1.5; MG5's
# get_virtual_a0Gmu_conv takes its real part), madloop_parameters.py.
runs["udx_epvea_cms"]["export_parameters"] = ["MDL_ECOUP_DGMUA0_UV_EW_FIN_"]
# A row's components: those of its own runs; a uv row without a MadLoop run (LL01: an existing control
# fixture) names its class's.
for e in rows:
    own = [runs[r]["components"] for r in e["runs"] if runs[r].get("components")]
    if not own and "uv" in e["extras"]:
        own = [runs[r]["components"] for c in rows if c["class"] == e["class"] for r in c["runs"]
               if runs[r].get("components")][:1]
        if not own:
            raise ValueError(f"{e['row']}: no component run in class {e['class']}")
    if own:
        e["components"] = own

campaign = {
    "description": "M-SM validation campaign (workspace/reports/engine-v2/m-sm/PLAN.md §4): the 70 core rows of §4.2 "
                   "(the decay rows XX01/XX02 wait for the user's Q3), SC10 (the R2_ZZHH row of MS-UFODB) and the "
                   "MadLoop reference runs producing them. "
                   "Runs live under $LOOP_REFERENCE_ROOT/runs/msm/<run>/ and their merged references are committed "
                   "as tests/fixtures/loop/required/msm/<run>.json; existing fixtures are paths below "
                   "tests/fixtures/loop/. Driven by mqcd_campaign.py --campaign msm_campaign.json.",
    "layout": {"name": "M-SM", "runs": "runs/msm", "fixtures": "required/msm",
               "manifest": "required/msm_references.json", "schema": "msm-references/1", "plan": "m-sm/PLAN.md",
               "r2_couplings": True},
    "restriction_codes": ROUTES,
    "madloop_settings": {
        "evaluation": {
            "requested_relative_accuracy": 1e-13, "madloop_params": {"HelicityFilterLevel": "0"},
            "quadruple_precision_stage": True,
            "description": "as the M-QCD campaign (mqcd_campaign.json): every point in MadLoop's quadruple-precision "
                           "stage (double-precision acceptance bypassed in the run's loop_matrix.f copy), its own "
                           "test at MLStabThres 1e-13 choosing Ninja or CutTools, HelicityFilterLevel = 0; CMS "
                           "exports carry the quadruple-precision model-function repair (MP_RECMS and the other "
                           "CMPLX calls with KIND=16, references.fix_qp_model_functions)",
            "reason": "stricter than the accurate mode of m-sm/PLAN.md §4.1 (1e-11, forced test, QP rescue), never "
                      "looser; the M-QCD campaign's reasons apply"},
        "madloop_accuracy_definition": "MadLoop's own accuracy is ONE number per squared split order over the three "
                                       "Laurent coefficients (see mqcd_campaign.json)",
        "requested_relative_accuracy": 1e-13,
        "orders": "explicit squared orders on every job: QCD^2<=99 QED^2<=99 on joint [virt=QCD QED] requests (MadLoop's "
                  "default selection drops the highest-alpha sector of mixed-Born requests), == on the sector-only "
                  "jobs; every squared split order is printed (SECTORS)",
        "job_timeout_seconds": 2700},
    "rows": rows,
    "runs": list(runs.values()),
}
assert len(rows) == 71, len(rows)
Path(sys.argv[1]).write_text(json.dumps(campaign, indent=1) + "\n")
print(len(rows), "rows,", len(runs), "runs")
