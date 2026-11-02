#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Write mqcd_campaign.json: the rows of m-qcd/PLAN.md §4.2 and the MadLoop reference runs producing them.

Usage: make_mqcd_campaign.py tools/loop_reference/mqcd_campaign.json (the committed JSON is its output)."""
import json
import sys
from pathlib import Path

ROUTES = {
    "5F": {"restriction": "no_b_mass", "fixed_parameters": {"WT": "0", "WZ": "0", "WW": "0", "WH": "0"}, "scheme": "qcd"},
    "5F*": {"restriction": "default", "fixed_parameters": {"MB": "0", "ymb": "0", "WT": "0", "WZ": "0", "WW": "0", "WH": "0"},
            "scheme": "qcd", "note": "default restriction with MB = ymb = 0 (until MQ-5F, then also 5F); the MadLoop reference is the 5F (no_b_mass) one: the same QCD parameter values (default keeps MTA = ymtau = 1.777 where no_b_mass has 0; no tau enters these QCD rows)"},
    "4F": {"restriction": "default", "fixed_parameters": {"WT": "0", "WZ": "0", "WW": "0", "WH": "0"}, "scheme": "qcd-4fs",
           "note": "= no_widths"},
    "CM": {"restriction": "c_mass", "fixed_parameters": {"WT": "0", "WZ": "0", "WW": "0", "WH": "0"}, "scheme": "qcd-cmass"},
    "ZC": {"restriction": "zeromass_ckm", "fixed_parameters": {"WT": "0", "WZ": "0", "WW": "0", "WH": "0"}, "scheme": "qcd-ckm"},
    "CK": {"restriction": "ckm", "fixed_parameters": {"WT": "0", "WZ": "0", "WW": "0", "WH": "0"}, "scheme": "qcd-ckm4"},
    "LM": {"restriction": "lepton_masses", "fixed_parameters": {"WT": "0", "WZ": "0", "WW": "0", "WH": "0"}, "scheme": "qcd-lmass"},
    "W": {"restriction": "no_b_mass", "fixed_parameters": {"WT": "0"}, "scheme": "qcd-widths", "note": "colourless widths at the card values"},
}

rows, runs = [], {}


def run(rid, key, export=None, points=None, helicities=None, split_points=False, recola=False, subprocess=None,
        pdgs=None, note=None, second=(), accuracy=None, exclude=None, notes=None, point_status=None, trigger=None,
        keep=None):
    r = {"id": rid, "process": key, "export": export or f"runs/mqcd/{key}/madloop-export",
         "points": points or {"generator": "exact"}}
    if helicities:
        r["helicities"] = helicities
    if split_points:
        r["split_points"] = True
    if recola or second:
        r["second_providers"] = list(second) or ["recola"]
        if not trigger:
            raise ValueError(f"{rid}: a second provider needs its m-qcd/PLAN.md §4.1 trigger (or 'diagnostic')")
        r["second_provider_trigger"] = trigger
    if point_status:
        r["point_status"] = point_status
    if accuracy:
        r["madloop_accuracy"] = accuracy
    if keep:
        r["madloop_evaluation"] = {"mode": "mlstabthres", "reason": keep}
    if exclude:
        r["exclude_providers"] = exclude
    if notes:
        r["reference_notes"] = notes
    if subprocess:
        r["subprocess"] = subprocess
    if pdgs:
        r["pdgs"] = pdgs
    if note:
        r["note"] = note
    runs[rid] = r
    return rid


def row(rid, cls, process, code, ref, tier="n", extras=(), runs_=(), fixtures=(), note=None, primary=None,
        helicity_reference=None):
    e = {"row": rid, "class": cls, "process": process, "restriction_code": code, "reference_kind": ref,
         "tier": tier, "extras": list(extras), "runs": list(runs_), "existing_fixtures": list(fixtures)}
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


S2_DIAGNOSTIC = ("diagnostic outside the §4.1 triggers (recorded, not a trigger): the installed ppjjj library and "
                 "Recola, < 1 min per run, to test MadLoop's quadruple-precision evaluation at the S2 limit points "
                 "where no other cross-check exists; it exposed MadLoop's unstable collinear theta = 1e-4, 1e-5 "
                 "evaluations")
CHARM = "§4.1: the massive-charm rows C08 and C09, after the charm fix"
F2 = ("§4.1: rule 1 (DD against MadLoop) exceeded 1e-12 at point 1 (mq-validate finding F2: 3.25e-11 finite, "
      "4.8e-13 poles against the batch-2 MadLoop values); outcome recorded in the fixture's provider pairs: the cause "
      "was MadLoop's numerical helicity filter (HelicityFilterLevel 2 dropped and folded mass-suppressed b-quark "
      "helicities): with the campaign's HelicityFilterLevel = 0 MadLoop agrees with Recola")
F3 = ("§4.1: rule 1 (DD against MadLoop) exceeded 1e-12 at points 0, 2, 3 (mq-validate finding F3: MadLoop's "
      "CutTools quadruple-precision values, return code 329, 3.5e-12 .. 1.2e-11 off); the installed ppjjjj library "
      "and Recola (a third independent value for the user's ruling, audit of fix round 2), no installation; outcome "
      "recorded in the fixture's provider pairs")
KEEP = ("not re-evaluated (2->4/2->5 runs of 2.0-2.4 CPU-hours per batch; the per-sector batch-2 values stand): MadLoop "
        "quadruple precision at every point already (return code 328, MLStabThres 1e-13 with its own CTModeRun -1 "
        "test), the evaluation the campaign forces elsewhere; MadLoop's helicity filter {}")
G1 = "runs/g1/{}/madloop-export".format
REQ = "runs/required/{}/madloop-export".format

# A: massless QCD (5F)
row("A01", "Q-massless", "g g > g g", "5F", "E", "d", ["nc", "ap"], fixtures=["v2/gg_gg_providers.json"],
    runs_=[run("gg_gg_sectors", "gg_gg", export='runs/g1/gg_gg/madloop-export', points={"generator": "fixture", "fixture": "v2/gg_gg_providers.json", "half_scale_point": True}, note="per-sector MadLoop accuracy and the mu_R = mu_0/2 point at the committed fixture's points")])
row("A02", "Q-massless", "u u~ > g g", "5F", "N", runs_=[run("uux_gg", "uux_gg")])
row("A03", "Q-massless", "g g > u u~", "5F", "N", runs_=[run("gg_uux", "gg_uux")])
row("A04", "Q-massless", "u g > u g", "5F", "N", "d", runs_=[run("ug_ug", "ug_ug")])
row("A05", "Q-massless", "u u~ > d d~", "5F", "N", extras=["uv"], runs_=[run("uux_ddx", "uux_ddx")])
row("A06", "Q-massless", "u u~ > u u~", "5F", "E", fixtures=["required/uux_uux.json"],
    runs_=[run("uux_uux_sectors", "uux_uux", export='runs/required/uux_uux/madloop-export', points={"generator": "fixture", "fixture": "required/uux_uux.json", "half_scale_point": True}, note="per-sector MadLoop accuracy and the mu_R = mu_0/2 point at the committed fixture's points")])
row("A07", "Q-massless", "u u > u u", "5F", "N", runs_=[run("uu_uu", "uu_uu")])
row("A08", "Q-massless", "g g > g g g", "5F", "R", extras=["nc", "ward", "hel"],
    runs_=[run("gg_ggg", "gg_ggg", export=G1("gg_ggg")),
           run("gg_ggg_hel", "gg_ggg", export=G1("gg_ggg"), helicities="all",
               points=S(count=3, half_scale_point=False, madloop_qp_point=True),
               note="per-helicity reference at MadLoop's own quadruple-precision points (published to 30 digits): "
                    "its quadruple-precision values refer to the published point, so every non-vanishing helicity "
                    "is a strictly relative reference, including those suppressed by 1e-11 .. 1e-4 of the summed "
                    "Born, whose values at the exact points of gg_ggg depend on MadLoop's 1e-16 repair of the "
                    "binary64 rounding (gg_ggg's per-helicity run is superseded)")],
    note="+ NJet (nc)", helicity_reference="gg_ggg_hel")
row("A09", "Q-massless", "u u~ > g g g", "5F", "R", "d", extras=["nc", "sp:S2"],
    runs_=[run("uux_ggg", "uux_ggg", export=G1("uux_ggg")),
           run("uux_ggg_soft", "uux_ggg", export=G1("uux_ggg"),
               points=S(family="soft", values=["1/1000", "1/100000"], half_scale_point=False, madloop_qp_point=True),
               second=("recola", "openloops"), trigger=S2_DIAGNOSTIC,
               note="S2: soft gluon E/sqrt(s) = 1e-3, 1e-5",
               exclude={"recola": "COLLIER double precision fails in the soft limit (4.6e-9 at E/sqrt(s) = 1e-3, "
                                  "6.0e-3 at 1e-5 against MadLoop QP and OpenLoops, which agree to 1.5e-14 and 2.5e-13)"}),
           run("uux_ggg_collinear", "uux_ggg", export=G1("uux_ggg"),
               points=S(family="collinear", values=["1/1000", "1/10000", "1/100000"], half_scale_point=False, madloop_qp_point=True),
               accuracy=1e-20, second=("recola", "openloops"), trigger=S2_DIAGNOSTIC,
               keep="not re-evaluated: a fixed CTModeRun = 4 evaluation returns NaN at the theta = 1e-4, 1e-5 points "
                    "(rows 1, 2: no reference, status none), where MadLoop's own CTModeRun -1 evaluation ends "
                    "unstable (420); the batch-2 run (MLStabThres 1e-20: quadruple precision, return code 328 at row "
                    "0) stands. Its helicity filter set only configurations violating helicity conservation on the "
                    "massless quark line or with a vanishing Born to zero (no folded entry)",
               exclude={"recola": "COLLIER double precision fails at small opening angles (1e-4 relative at theta = 1e-3)"},
               point_status={
                   "1": {"status": "none", "reason": "MadLoop's quadruple-precision evaluation is unstable (return "
                                                     "code 420, own accuracy 1.3e-6) and OpenLoops differs by 4.3e-5: "
                                                     "good to ~1e-6 at best, no reference at M-QCD accuracies"},
                   "2": {"status": "none", "reason": "MadLoop's quadruple-precision evaluation is unstable (return "
                                                     "code 420, own accuracy 28) and MadLoop, Recola and OpenLoops "
                                                     "disagree at O(1)"}},
               notes={"0": "MadLoop quadruple precision at its own projected point (published); OpenLoops reads the "
                           "binary64 rounding of the point, whose Born condition (~1e7: MadLoop's double-precision "
                           "Born at the binary64 point differs from its quadruple-precision one by 1.6e-9) limits "
                           "the provider comparison to ~1e-8",
                      "1": "REFERENCE GOOD TO ~1e-6 ONLY: MadLoop's quadruple-precision evaluation is unstable "
                           "(return code 420, own accuracy 1.3e-6) and OpenLoops differs by 4.3e-5; not a 1e-12 "
                           "reference (rule 1 outlier without a confirming provider)",
                      "2": "NO PROVIDER REFERENCE: MadLoop's quadruple-precision evaluation is unstable (return code "
                           "420, own accuracy 28; OneLOop: 'input does not seem to represent hard kinematics') and "
                           "MadLoop, Recola and OpenLoops disagree at O(1); validate by internal oracles only"},
               note="S2: collinear gluon pair theta = 1e-3, 1e-5 (small Gram determinants)")],
    note="+ NJet, BDK (nc)")
row("A12", "Q-massless", "u u~ > d d~ g", "5F", "E", "d", ["nc"], fixtures=["required/uux_ddxg.json"],
    runs_=[run("uux_ddxg_sectors", "uux_ddxg", export='runs/required/uux_ddxg/madloop-export', points={"generator": "fixture", "fixture": "required/uux_ddxg.json", "half_scale_point": True}, note="per-sector MadLoop accuracy and the mu_R = mu_0/2 point at the committed fixture's points")])
row("A13", "Q-massless", "u u~ > u u~ g", "5F", "E", extras=["nc", "ap"], fixtures=["required/uux_uuxg.json"],
    runs_=[run("uux_uuxg_sectors", "uux_uuxg", export='runs/required/uux_uuxg/madloop-export', points={"generator": "fixture", "fixture": "required/uux_uuxg.json", "half_scale_point": True}, note="per-sector MadLoop accuracy and the mu_R = mu_0/2 point at the committed fixture's points")])
row("A14", "Q-massless", "g g > g g g g", "5F", "E", extras=["ward"], fixtures=["required/gg_gggg.json"],
    note="MadLoop QP values committed into the fixture (never regenerated)")
row("A15", "Q-massless", "u u~ > g g g g", "5F", "N", extras=["nc"],
    runs_=[run("uux_gggg", "uux_gggg", split_points=True)])
A18_RECOLA = ("Recola (COLLIER, binary64) differs from MadLoop and OpenLoops by 1.7e-12 .. 5.6e-11 (Laurent coefficients) at "
              "every point, "
              "including point 1 where MadLoop (Ninja, 328) and OpenLoops agree to 1e-12: not a 1e-12 reference for "
              "this process, so it decides no point")


def a18_outlier(index, ir, ol, fin, dp, dd_openloops, condition_ii):
    """Rule 1 outlier record of a g g > u u~ u u~ point (mq-validate F3)."""
    return {
        "outlier": {
            "rule": 1, "ruling": "pending: routed to the user via the coordinator",
            "conditions": {
                "i": "fails: MadLoop's own accuracy at the point is 0.0 (forced quadruple-precision stage, CutTools, "
                     "return code 329); an accuracy of 0.0 covers no nonzero difference, so rule 1 (i) cannot hold "
                     "at any point where DD and MadLoop differ (mq-validate F3: by 3.5e-12 or more)",
                "ii": f"{condition_ii}: OpenLoops (ppjjjj, binary64) = DD to {dd_openloops} (mq-validate F3)"},
            "providers": {
                "madloop": f"CutTools quadruple precision (329, accuracy 0.0); misses its own universal double pole "
                           f"by {ir}",
                "openloops": f"misses the universal double pole by {ol}; MadLoop - OpenLoops: finite {fin}, double "
                             f"pole {dp}",
                "recola": A18_RECOLA}},
        "reason": f"rule 1 outlier at point {index}: no provider value satisfies rule 1 (i) here; ruling pending"}


row("A18", "Q-massless", "g g > u u~ u u~", "5F", "N", extras=["nc"],
    runs_=[run("gg_uuxuux", "gg_uuxuux", split_points=True, second=("openloops", "recola"), trigger=F3,
               point_status={str(i): a18_outlier(i, *values) for i, *values in (
                   (0, "3.5e-13", "3.5e-14", "4.0e-12", "3.1e-13", "5.5e-13", "holds"),
                   (2, "1.1e-12", "1.2e-13", "5.2e-12", "1.2e-12", "1.2e-12", "fails"),
                   (3, "3.5e-13", "4.7e-14", "1.4e-11", "4.0e-13", "2.6e-12", "fails"))},
               notes={"0": "OUTLIER (rule 1): reference.outlier; OpenLoops satisfies (ii) only, (i) fails",
                      "1": "MadLoop's quadruple-precision stage takes Ninja (328) and agrees with OpenLoops to 1e-12",
                      "2": "OUTLIER (rule 1): reference.outlier; no provider is a 1e-12 reference",
                      "3": "OUTLIER (rule 1): reference.outlier; no provider is a 1e-12 reference"})])
row("A19", "Q-massless", "u u~ > d d~ s s~", "5F", "E", fixtures=["required/uux_ddxssx.json"],
    runs_=[run("uux_ddxssx_sectors", "uux_ddxssx", export='runs/required/uux_ddxssx/madloop-export', points={"generator": "fixture", "fixture": "required/uux_ddxssx.json", "half_scale_point": True}, note="per-sector MadLoop accuracy and the mu_R = mu_0/2 point at the committed fixture's points")])
row("A20", "Q-massless", "u u~ > u u~ d d~", "5F", "E", fixtures=["required/uux_uuxddx.json"],
    runs_=[run("uux_uuxddx_sectors", "uux_uuxddx", export='runs/required/uux_uuxddx/madloop-export', points={"generator": "fixture", "fixture": "required/uux_uuxddx.json", "half_scale_point": True}, note="per-sector MadLoop accuracy and the mu_R = mu_0/2 point at the committed fixture's points")])
row("A21", "Q-massless", "u u~ > u u~ u u~", "5F", "E", extras=["nc"], fixtures=["required/uux_uuxuux.json"],
    runs_=[run("uux_uuxuux_sectors", "uux_uuxuux", export='runs/required/uux_uuxuux/madloop-export', points={"generator": "fixture", "fixture": "required/uux_uuxuux.json", "half_scale_point": True}, note="per-sector MadLoop accuracy and the mu_R = mu_0/2 point at the committed fixture's points")])
row("A22", "Q-massless", "u u~ > d d~ s s~ g", "5F", "E", fixtures=["multiquark-sevenleg-component-control.json"],
    note="Recola <= 4e-11 (existing control)")
row("A23", "Q-massless", "u u~ > g g g g g", "5F", "E", fixtures=["required/uux_ggggg.json"])
row("A24", "Q-massless", "g g > g g g g g (top veto)", "5F", "E", extras=["uv"], fixtures=["required/gg_ggggg_njet.json"],
    primary="njet", note="NJet double-double; no MadLoop (HANDOFF §0.1)")
row("A25", "Q-massless", "u d > u d", "5F", "N", runs_=[run("ud_ud", "ud_ud")])
row("A26", "Q-massless", "u~ u~ > u~ u~", "5F", "N", runs_=[run("uxux_uxux", "uxux_uxux")])
# B: top (5F, WT = 0)
row("B01", "Q-top", "g g > t t~", "5F", "E", "d", ["ap", "uv", "hel", "sp:S1", "sp:S4"], fixtures=["required/gg_ttx.json"],
    runs_=[run("gg_ttx_sectors", "gg_ttx", export=REQ("gg_ttx"), points={"generator": "fixture", "fixture": "required/gg_ttx.json", "half_scale_point": True},
               helicities="all", note="per-sector and per-helicity MadLoop run at the committed fixture's points"),
           run("gg_ttx_threshold", "gg_ttx", export=REQ("gg_ttx"),
               points=S(family="threshold", values=["1/10", "1/100", "1/1000"], half_scale_point=False, madloop_qp_point=True),
               note="S1: threshold beta = 1e-1, 1e-2, 1e-3"),
           run("gg_ttx_mt170", "gg_ttx_mt170", export=REQ("gg_ttx"), note="S4: runtime MT = 170")],
    helicity_reference="gg_ttx_sectors")
row("B02", "Q-top", "u u~ > t t~", "5F", "N", runs_=[run("uux_ttx", "uux_ttx")])
row("B03", "Q-top", "g g > t t~ g", "5F", "N", extras=["nc", "ward"], runs_=[run("gg_ttxg", "gg_ttxg")])
row("B05", "Q-top", "g g > t t~ g g", "5F", "E", fixtures=["required/gg_ttxgg.json"],
    runs_=[run("gg_ttxgg_sectors", "gg_ttxgg", export='runs/required/gg_ttxgg/madloop-export', points={"generator": "fixture", "fixture": "required/gg_ttxgg.json", "half_scale_point": True}, split_points=True, note="per-sector MadLoop accuracy and the mu_R = mu_0/2 point at the committed fixture's points",
               keep=KEEP.format("computed every helicity configuration (no zero and no folded entry in its "
                                "HelFilter.dat), the same as HelicityFilterLevel = 0"))])
row("B06", "Q-top", "u u~ > t t~ d d~", "5F", "N", runs_=[run("uux_ttxddx", "uux_ttxddx")])
row("B07", "Q-top", "g g > t t~ t t~", "5F", "N", runs_=[run("gg_ttxttx", "gg_ttxttx", points=S(), split_points=True)])
row("B08", "Q-top", "g g > t t~ (4F)", "4F", "N", runs_=[run("gg_ttx_4fs", "gg_ttx_4fs")],
    note="plain loop_sm with WT = 0 (= no_widths smoke)")
# C: massive b/c
row("C01", "Q-heavy", "g g > b b~", "4F", "N", "d", ["nc", "ap", "ward", "sp:S4"],
    runs_=[run("gg_bbx_4fs", "gg_bbx_4fs", points=S(), second=("recola",), trigger=F2),
           run("gg_bbx_4fs_params", "gg_bbx_4fs_params", export="runs/mqcd/gg_bbx_4fs/madloop-export", points=S(),
               second=("recola",), trigger=F2,
               note="S4: runtime MB = 4.5, aS = 0.13 (cond(MB) and reglog CT terms)")])
row("C02", "Q-heavy", "g g > g g (b decoupled)", "4F", "N", extras=["uv"], runs_=[run("gg_gg_4fs", "gg_gg_4fs")])
row("C03", "Q-heavy", "b b~ > h", "4F", "N", runs_=[run("bbx_h_4fs", "bbx_h_4fs", points=S(family="rest"))])
row("C04", "Q-heavy", "b b~ > h g (x-rotated)", "4F", "N",
    runs_=[run("bbx_hg_4fs", "bbx_hg_4fs", points=S(rotate="x")),
           run("bbx_hg_4fs_z", "bbx_hg_4fs", export="runs/mqcd/bbx_hg_4fs/madloop-export", points=S(),
               note="non-gating diagnostic: the same construction with the beams on +-z")])
row("C05", "Q-heavy", "g g > b b~ h", "4F", "N", runs_=[run("gg_bbxh_4fs", "gg_bbxh_4fs", points=S())])
row("C06", "Q-heavy", "g g > t t~ b b~", "4F", "N", runs_=[run("gg_ttxbbx_4fs", "gg_ttxbbx_4fs", points=S(), split_points=True)])
row("C07", "Q-singletop", "u g > d t b~ (4FS t-channel)", "4F", "N", runs_=[run("ug_dtbx_4fs", "ug_dtbx_4fs", points=S())])
row("C08", "Q-heavy", "g g > c c~", "CM", "N", runs_=[run("gg_ccx_cmass", "gg_ccx_cmass", points=S(), recola=True, trigger=CHARM)])
row("C09", "Q-heavy", "g s > w- c", "CM", "N", runs_=[run("gs_wmc_cmass", "gs_wmc_cmass", points=S(), recola=True, trigger=CHARM)],
    note="MQ-5F (Dirac-Weyl closure)")
# D: colour-singlet bosons (5F)
row("D01", "Q-EWBorn", "u u~ > e- e+", "5F", "N", "d", ["ap"], runs_=[run("uux_emep", "uux_emep")],
    note="+ analytic form factor")
row("D02", "Q-EWBorn", "u u~ > e- e+ (widths)", "W", "R",
    runs_=[run("uux_emep_widths", "uux_emep_widths", export="runs/mqcd/uux_emep/madloop-export",
               points={"generator": "run", "run": "uux_emep"})])
row("D05", "Q-EWBorn", "u u~ > e- e+ g", "5F", "R", "d", ["nc", "ward", "uv", "hel"],
    runs_=[run("uux_emepg", "uux_emepg", export=G1("uux_emepg"), helicities="all")], helicity_reference="uux_emepg")
row("D06", "Q-EWBorn", "u u~ > e- e+ g g", "5F", "R", fixtures=["dilepton-two-gluon.json"],
    runs_=[run("uux_emepgg", "uux_emepgg", export=G1("uux_emepgg"))], note="existing LC/NLC test (ew_lines:943)")
row("D07", "Q-EWBorn", "u u~ > e- e+ g g g", "5F", "E", fixtures=["required/uux_emepggg.json"],
    runs_=[run("uux_emepggg_sectors", "uux_emepggg", export='runs/required/uux_emepggg/madloop-export', points={"generator": "fixture", "fixture": "required/uux_emepggg.json", "half_scale_point": True}, split_points=True, note="per-sector MadLoop accuracy and the mu_R = mu_0/2 point at the committed fixture's points")])
row("D08", "Q-EWBorn", "u u~ > e- e+ d d~ g", "5F", "E", fixtures=["required/uux_emepddxg.json"],
    runs_=[run("uux_emepddxg_sectors", "uux_emepddxg", export='runs/required/uux_emepddxg/madloop-export', points={"generator": "fixture", "fixture": "required/uux_emepddxg.json", "half_scale_point": True}, note="per-sector MadLoop accuracy and the mu_R = mu_0/2 point at the committed fixture's points")])
row("D09", "Q-EWBorn", "u u~ > e- e+ mu- mu+", "5F", "E", fixtures=["required/uux_emepmummp.json"],
    runs_=[run("uux_emepmummp_sectors", "uux_emepmummp", export='runs/required/uux_emepmummp/madloop-export', points={"generator": "fixture", "fixture": "required/uux_emepmummp.json", "half_scale_point": True}, note="per-sector MadLoop accuracy and the mu_R = mu_0/2 point at the committed fixture's points")])
row("D10", "Q-EWBorn", "u u~ > u u~ e+ e-", "5F", "E", fixtures=["required/uux_uuxepem.json"], note="22x case (MQ-STAB)",
    runs_=[run("uux_uuxepem_sectors", "uux_uuxepem", export='runs/required/uux_uuxepem/madloop-export', points={"generator": "fixture", "fixture": "required/uux_uuxepem.json", "half_scale_point": True}, note="per-sector MadLoop accuracy and the mu_R = mu_0/2 point at the committed fixture's points")])
row("D11", "Q-EWBorn", "u u~ > z g", "5F", "N", runs_=[run("uux_zg", "uux_zg")])
row("D12", "Q-EWBorn", "u d~ > e+ ve g", "5F", "N", runs_=[run("udx_epveg", "udx_epveg")])
row("D13", "Q-EWBorn", "u g > a u", "5F", "N", runs_=[run("ug_au", "ug_au")])
row("D15", "Q-EWBorn", "u u~ > z z", "5F", "N", runs_=[run("uux_zz", "uux_zz")])
row("D16", "Q-EWBorn", "u u~ > w+ w-", "5F", "N", runs_=[run("uux_wpwm", "uux_wpwm", points=S())])
row("D17", "Q-EWBorn", "b b~ > w+ w-", "5F*", "N", runs_=[run("bbx_wpwm", "bbx_wpwm", points=S())], note="MQ-5F")
row("D18", "Q-EWBorn", "u u~ > z h", "5F", "N", runs_=[run("uux_zh", "uux_zh", points=S())])
row("D19", "Q-EWBorn", "u d > u d h QCD=0 (VBF)", "5F", "N", runs_=[run("ud_udh", "ud_udh")])
row("D20", "Q-EWBorn", "e+ e- > u u~ g", "5F", "N", runs_=[run("epem_uuxg", "epem_uuxg")])
row("D21", "Q-ttX", "e+ e- > t t~", "5F", "E", fixtures=["required/top-pair-ee-model-control.json"],
    note="committed from runs/top-pair-ee-model-control.json")
row("D23", "Q-EWBorn", "a g > u u~", "5F", "N", runs_=[run("ag_uux", "ag_uux")])
row("D24", "Q-EWBorn", "e- u > e- u", "5F", "N", runs_=[run("emu_emu", "emu_emu")])
row("D25", "Q-EWBorn", "u d~ > w+ a (radiation zero)", "5F", "N", extras=["sp:S3"],
    runs_=[run("udx_wpa", "udx_wpa", points=S()),
           run("udx_wpa_zero", "udx_wpa", export="runs/mqcd/udx_wpa/madloop-export",
               points=S(family="radiation-zero", count=2, zero_cosine="-1/3", neighbour_cosine="-1/5", half_scale_point=False,
                        madloop_qp_point=True),
               point_status={str(i): {"comparison": "absolute", "scale_row": 2,
                                      "reason": "§4.1 S3 Born-zero point: the Born and the double pole vanish to "
                                                "rounding; compare absolutely against the regular neighbour's Born"}
                             for i in (0, 1)},
               note="S3: Born-zero points cos(u, photon) = -1/3 and one regular neighbour")])
row("D26", "Q-heavy", "u u~ > e- e+ g (4F twin of D05)", "4F", "N", runs_=[run("uux_emepg_4fs", "uux_emepg_4fs")])
row("D27", "Q-EWBorn", "g u > e+ ve d", "5F", "N", runs_=[run("gu_epved", "gu_epved")])
row("D28", "Q-EWBorn", "u u~ > w+ w- g (4F)", "4F", "N", extras=["ward"],
    runs_=[run("uux_wpwmg_4fs", "uux_wpwmg_4fs", points=S())],
    note="VV + jet (mq-ewjoin: the loop vertex attaches the sum of a field current's flavour-flow trees)")
row("D29", "Q-EWBorn", "b b~ > w+ w- g", "5F*", "N", extras=["ward"], runs_=[run("bbx_wpwmg", "bbx_wpwmg", points=S())],
    note="MQ-5F; VV + jet with a massive t-channel line (mq-ewjoin)")
# E: tt + X
row("E01", "Q-ttX", "g g > t t~ h", "5F", "N", extras=["nc", "ward", "uv"], runs_=[run("gg_ttxh", "gg_ttxh", points=S())])
row("E02", "Q-ttX", "g g > t t~ z", "5F", "N", runs_=[run("gg_ttxz", "gg_ttxz", points=S())])
row("E05", "Q-ttX", "e+ e- > t t~ h", "5F", "E", fixtures=["top-pair-higgs-model.json"])
row("E06", "Q-ttX", "g g > t t~ e- e+ g", "5F", "E", fixtures=["required/gg_ttxemepg_qcd.json"],
    note="point 2: the plan lists a rule 1 outlier (DD vs MadLoop 1.43e-8, vs OpenLoops 5.8e-13); the provider "
         "references themselves do not show it: at that point MadLoop (quadruple precision, code 328) = OpenLoops to "
         "6.0e-13 in the finite part (committed fixture and the 1e-13 rerun alike) and Recola is the outlier "
         "(1.0e-8); MQ-VALIDATE re-checks the DD comparison",
    runs_=[run("gg_ttxemepg_qcd_sectors", "gg_ttxemepg_qcd", export='runs/required/gg_ttxemepg_qcd/madloop-export', points={"generator": "fixture", "fixture": "required/gg_ttxemepg_qcd.json", "half_scale_point": True}, split_points=True, note="per-sector MadLoop accuracy and the mu_R = mu_0/2 point at the committed fixture's points",
               keep=KEEP.format("set only the 64 configurations that violate helicity conservation on the massless "
                                "lepton line to zero (exactly vanishing; no folded entry)"))])
# F: single top (MadLoop on 5F; pyAmpliCol on 5F*, and 5F after MQ-5F)
row("F01", "Q-singletop", "u b > d t", "5F*", "N", extras=["nc", "uv", "ap"], runs_=[run("ub_dt", "ub_dt")])
row("F02", "Q-singletop", "b u > d t", "5F*", "N", runs_=[run("bu_dt", "bu_dt")])
row("F03", "Q-singletop", "u d~ > t b~", "5F", "N", "d", runs_=[run("udx_tbx", "udx_tbx")])
row("F04", "Q-singletop", "g b > t w-", "5F*", "N", extras=["ward"], runs_=[run("gb_twm", "gb_twm", points=S())])
# G, H, M, R
row("G01", "Q-mixed", "u u~ > d d~ QED<=2, full SM, every split order", "5F", "E", "d", ["uv"],
    fixtures=["mixed-uudd-sm-qcd-control.json"], note="+ photon-only controls")
row("G02", "Q-mixed", "u u~ > t t~ QED<=2, every split order", "5F", "N", runs_=[run("uux_ttx_mixed", "uux_ttx_mixed")])
row("H01", "Q-CKM", "u s~ > w+ g", "ZC", "N", extras=["uv"], runs_=[run("usx_wpg_ckm", "usx_wpg_ckm", points=S())],
    note="+ CKM-factor relation to u d~ > w+ g on zeromass_ckm")
row("H02", "Q-CKM", "g s > t w-", "ZC", "N", runs_=[run("gs_twm_ckm", "gs_twm_ckm", points=S())],
    note="MQ-5F; + CKM-factor relation to g b > t w- (massless b)")
row("H03", "Q-CKM", "g d > t w-", "CK", "N", runs_=[run("gd_twm_ckm4", "gd_twm_ckm4", points=S())],
    note="MQ-5F; recorded single-provider exception")
row("M01", "Q-multi", "p p > t t~ (multiparticle label)", "5F", "N",
    runs_=[run("pp_ttx_P0_uux_ttx", "pp_ttx", export="runs/mqcd/pp_ttx/madloop-export", subprocess="P0_uux_ttx",
               pdgs=[2, -2, 6, -6], points={"generator": "exact", "pdgs": [2, -2, 6, -6]}),
           run("pp_ttx_P2_gg_ttx", "pp_ttx", export="runs/mqcd/pp_ttx/madloop-export", subprocess="P2_gg_ttx",
               pdgs=[21, 21, 6, -6])],
    note="one MadLoop export; one run per SubProcesses/P* directory")
row("R01", "Q-heavy", "u u~ > mu- mu+ (massive muons)", "LM", "N", runs_=[run("uux_mummp_lmass", "uux_mummp_lmass", points=S())])

campaign = {
    "description": "M-QCD validation campaign (workspace/reports/engine-v2/m-qcd/PLAN.md §4): the rows of §4.2 and the "
                   "MadLoop reference runs producing them. Runs live under $LOOP_REFERENCE_ROOT/runs/mqcd/<run>/ and "
                   "their merged references are committed as tests/fixtures/loop/required/mqcd/<run>.json; existing "
                   "fixtures are paths below tests/fixtures/loop/. Driven by mqcd_campaign.py.",
    "restriction_codes": ROUTES,
    "madloop_settings": {
        "evaluation": {
            "requested_relative_accuracy": 1e-13, "madloop_params": {"HelicityFilterLevel": "0"},
            "quadruple_precision_stage": True,
            "description": "every point in quadruple precision, chosen by MadLoop's own test: the run's copy of "
                           "loop_matrix.f bypasses MadLoop's double-precision acceptance (references.py "
                           "--madloop-quadruple, force_quadruple_stage), so every point goes on to MadLoop's "
                           "quadruple-precision stage, where its CTModeRun -1 test (two propagator directions, "
                           "forced on every call) at MLStabThres 1e-13 accepts Ninja or else CutTools, exactly as "
                           "for a point whose double-precision estimate failed; HelicityFilterLevel = 0 (every "
                           "helicity configuration computed, no numerical helicity filter); every run starts "
                           "without filters of earlier runs; a run with a double-precision point is refused",
            "reason": "m-qcd/PLAN.md §1.4 rule 1 compares DD with the reference at 1e-12 per coefficient. The batch-2 "
                      "evaluation (MLStabThres 1e-13, rescue only where the double-precision estimate failed) left "
                      "209 of 303 points in binary64, whose estimate does not bound a cancelling coefficient (C02 "
                      "point 0 finite 2.0e-12, D11 point 1 single pole 4.3e-12, A06 point 1 single pole 1.2e-12 "
                      "against estimates of ~1e-14 or exactly 0), and MadLoop's numerical helicity filter "
                      "(HelicityFilterLevel 2, ZeroThres 1e-9) zeroed and folded mass-suppressed helicities of the "
                      "massive-b rows (C01 point 1 finite 3.2e-11 off in both precisions; with HelicityFilterLevel 0 "
                      "MadLoop = Recola to 1e-15). MadLoop's own quadruple-precision selection is kept: a fixed "
                      "CTModeRun = 4 (Ninja in quadruple precision, no fallback; references.py --madloop-ctmode, "
                      "diagnostic) is worse where that test rejects Ninja (g g > t t~ g points 0, 3: double pole "
                      "3.1e-11 off the universal relation, CutTools 1e-14; g g > u u~ u u~ points 0, 2, 3: 5.5e-12, "
                      "CutTools 3.5e-13 .. 1.1e-12) while its CTModeRun = 5 twin agrees to 1e-13; and MLStabThres "
                      "1e-20 (with NRotations_DP = 1 to fail every double-precision test) rejects Ninja on a "
                      "one-ulp difference of its two directions, moving g g > t t~ g point 1 to CutTools (finite "
                      "1.1e-12 away)"},
        "madloop_accuracy_definition": "MadLoop's own accuracy (CTModeRun = -1, ML5_0_COMPUTE_ACCURACY) is ONE number "
                                       "per squared split order, sum_k |v_k(mode 1) - v_k(mode 2)| / (|sum_k v_k| / 3) "
                                       "over the three Laurent coefficients k: it is not a per-coefficient relative "
                                       "accuracy and does not bound a coefficient much smaller than the others (a "
                                       "cancelling finite part or single pole); the campaign's direction test is per "
                                       "coefficient",
        "requested_relative_accuracy": 1e-13,
        "requested_relative_accuracy_reason": "only for runs kept from batch 2 (madloop_evaluation mode "
                                              "'mlstabthres'): MLStabThres 1e-13 with MadLoop's forced stability "
                                              "test and quadruple-precision rescue",
        "special_points": "limit-point runs (S1-S3) at points that are MadLoop's own quadruple-precision projection of "
                          "their binary64 rounding (supplied_points.py --madloop-qp-point), evaluated like every run",
        "job_timeout_seconds": 2700,
        "plan_deviations_for_coordinator_ruling": [
                             "every point in MadLoop's quadruple-precision stage (double-precision acceptance "
                             "bypassed in the run's loop_matrix.f copy, MLStabThres 1e-13, HelicityFilterLevel = 0) "
                             "instead of the accurate mode of m-qcd/PLAN.md §4.1 "
                             "(--madloop-accuracy 1e-11 with MadLoop's rescue): stricter, never looser (reason in "
                             "evaluation); the three runs kept from batch 2 used MLStabThres 1e-13 (1e-20 for the "
                             "collinear limit points) and are in quadruple precision at every reference point",
                             "new MadLoop evaluations (no export regenerated) on the existing 2->5 exports of D07 "
                             "(u u~ > e- e+ g g g), D08 (u u~ > e- e+ d d~ g) and E06 (g g > t t~ e- e+ g) for "
                             "per-sector accuracies and the mu_R = mu_0/2 point: one job per point, each under "
                             "timeout 2700 (largest 2185 s); §3.2/§4.3's 'nothing is regenerated for any 2->5' read "
                             "as exports/generations (HANDOFF §0.1)",
                             "Recola and OpenLoops on the A09 soft and collinear limit points (uux_ggg_soft, "
                             "uux_ggg_collinear) outside the §4.1 triggers: diagnostics, < 1 min per run, "
                             "second_provider_trigger states it (" + S2_DIAGNOSTIC + ")"]},
    "rows": rows,
    "runs": list(runs.values()),
}
assert len(rows) == 78, len(rows)
Path(sys.argv[1]).write_text(json.dumps(campaign, indent=1) + "\n")
print(len(rows), "rows,", len(runs), "runs")
