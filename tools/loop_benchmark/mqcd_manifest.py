# SPDX-License-Identifier: 0BSD
# The row table quotes PLAN §4.2's reference legends and notes verbatim.
# ruff: noqa: E501
"""Write tests/fixtures/loop/mqcd/manifest.json, the M-QCD campaign rows.

Usage: python tools/loop_benchmark/mqcd_manifest.py [MQ-REF-INDEX]

The rows are m-qcd/PLAN.md §4.2's (``row(...)`` below: process, Born
orders, restriction code, reference legend, extras, structural features);
the references come from the committed fixtures named here and, for the rows
MQ-REF produced, from its index ``tests/fixtures/loop/required/
mqcd_references.json`` (or MQ-REF-INDEX). The data-dependent listings of the
acceptance rules (rule 1 outliers, identically vanishing coefficients,
sector sets, the relaxed tolerances of the user's ruling of 2026-10-29
~10:20) are recorded from the campaign's runs with their evidence in
comments. Re-run it when MQ-REF
adds references; the manifest is the committed source the tests read.
"""

import json
import sys
from pathlib import Path

WT = Path(__file__).resolve().parents[2]
REQ = WT / "tests/fixtures/loop/required"

QCD_FIXED = {
    "MB": "0",
    "ymb": "0",
    "MTA": "0",
    "ymtau": "0",
    "WT": "0",
    "WW": "0",
    "WZ": "0",
    "WH": "0",
}
ZERO_WIDTHS = {"WT": "0", "WW": "0", "WZ": "0", "WH": "0"}
CODES = {
    "5F": ("no_b_mass", QCD_FIXED, "qcd"),
    "5F*": ("default", QCD_FIXED, "qcd"),
    "4F": ("default", ZERO_WIDTHS, "qcd-4fs"),
    "CM": ("c_mass", ZERO_WIDTHS, "qcd-cmass"),
    "ZC": ("zeromass_ckm", ZERO_WIDTHS, "qcd-ckm"),
    "CK": ("ckm", ZERO_WIDTHS, "qcd-ckm4"),
    "LM": ("lepton_masses", ZERO_WIDTHS, "qcd-lmass"),
    "W": (
        "no_b_mass",
        {"MB": "0", "ymb": "0", "MTA": "0", "ymtau": "0", "WT": "0"},
        "qcd-widths",
    ),
}
CLASS = {
    "A": "Q-massless",
    "B": "Q-top",
    "C": "Q-heavy",
    "D": "Q-EWBorn",
    "E": "Q-ttX",
    "F": "Q-singletop",
    "G": "Q-mixed",
    "H": "Q-CKM",
    "M": "Q-multi",
    "R": "Q-EWBorn",
}
DEFAULT_ROWS = {"A01", "A04", "A09", "A12", "B01", "C01", "D01", "D05", "F03", "G01"}


def qcd(n, qed=0):
    return {"QCD": n, "QED": qed}


# id, process, born (QCD, QED), code, legend, extras, features, reference spec or None, waits_for
R = []


def row(
    id_,
    process,
    born,
    code,
    legend,
    extras=(),
    features=(),
    reference=None,
    waits=None,
    cls=None,
    veto=(),
    notes="",
    loop=None,
    extras_pending=None,
    points=None,
):
    R.append(
        dict(
            id=id_,
            process=process,
            born=born,
            code=code,
            legend=legend,
            extras=list(extras),
            features=list(features),
            reference=reference,
            waits=waits,
            cls=cls,
            veto=list(veto),
            notes=notes,
            loop=loop,
            extras_pending=extras_pending,
            points=points,
        )
    )


def req(name, providers=None):
    spec = {"format": "required", "path": f"tests/fixtures/loop/required/{name}.json"}
    if not providers:
        data = json.loads((REQ / f"{name}.json").read_text())
        names = list(data["rows"][0]["providers"])
        primary = data.get("primary_provider", names[0])
        providers = [primary] + [p for p in names if p != primary]
    spec["providers"] = providers
    return spec


MQREF = "MQ-REF"
# ---- A: massless QCD (5F)
row(
    "A01",
    "g g > g g",
    (2, 0),
    "5F",
    "E v2/gg_gg_providers.json",
    ["nc", "ap"],
    ["initial:gg", "2->2", "gluons-only"],
    {
        "format": "providers",
        "path": "tests/fixtures/loop/v2/gg_gg_providers.json",
        "providers": ["madloop", "recola", "openloops"],
    },
)
row(
    "A02",
    "u u~ > g g",
    (2, 0),
    "5F",
    "E quark-gluon-component-control (MadLoop binary64); N ~30 s",
    [],
    ["initial:qqbar", "2->2", "quark-line:1"],
    {
        "format": "component-control",
        "path": "tests/fixtures/loop/quark-gluon-component-control.json",
        "providers": ["madloop"],
    },
)
row(
    "A03",
    "g g > u u~",
    (2, 0),
    "5F",
    "N ~20 s",
    [],
    ["initial:gg", "2->2", "quark-line:1"],
    waits=MQREF,
)
row(
    "A04",
    "u g > u g",
    (2, 0),
    "5F",
    "N ~20 s",
    [],
    ["initial:qg", "2->2", "quark-line:1"],
    waits=MQREF,
)
row(
    "A05",
    "u u~ > d d~",
    (2, 0),
    "5F",
    "N ~15 s",
    ["uv"],
    ["initial:qqbar", "2->2", "quarks:distinct-flavour"],
    waits=MQREF,
)
row(
    "A06",
    "u u~ > u u~",
    (2, 0),
    "5F",
    "E required/uux_uux",
    [],
    ["initial:qqbar", "2->2", "quarks:identical-flavour"],
    req("uux_uux"),
)
row(
    "A07",
    "u u > u u",
    (2, 0),
    "5F",
    "N ~20 s",
    [],
    ["initial:qq", "2->2", "quarks:identical-flavour"],
    waits=MQREF,
)
row(
    "A08",
    "g g > g g g",
    (3, 0),
    "5F",
    "R runs/g1/gg_ggg (+NJet)",
    ["nc", "ward", "hel"],
    ["initial:gg", "2->3", "gluons-only"],
    waits=MQREF,
)
row(
    "A09",
    "u u~ > g g g",
    (3, 0),
    "5F",
    "E + R runs/g1/uux_ggg",
    ["nc", "sp"],
    ["initial:qqbar", "2->3", "quark-line:1", "special:soft-collinear"],
    waits=MQREF,
    notes="quark-three-gluon-component-control.json has no points of its own; the accurate run on runs/g1/uux_ggg comes from MQ-REF",
)
row(
    "A12",
    "u u~ > d d~ g",
    (3, 0),
    "5F",
    "E required/uux_ddxg",
    ["nc"],
    ["initial:qqbar", "2->3", "quarks:distinct-flavour"],
    req("uux_ddxg"),
)
row(
    "A13",
    "u u~ > u u~ g",
    (3, 0),
    "5F",
    "E required/uux_uuxg",
    ["nc", "ap"],
    ["initial:qqbar", "2->3", "quarks:identical-flavour"],
    req("uux_uuxg"),
)
row(
    "A14",
    "g g > g g g g",
    (4, 0),
    "5F",
    "E fixture (MadLoop QP committed by MQ-REF, + Recola, OpenLoops)",
    ["ward"],
    ["initial:gg", "2->4", "gluons-only"],
    req("gg_gggg"),
)
row(
    "A15",
    "u u~ > g g g g",
    (4, 0),
    "5F",
    "N ~3-5 min",
    ["nc"],
    ["initial:qqbar", "2->4", "quark-line:1"],
    waits=MQREF,
)
row(
    "A18",
    "g g > u u~ u u~",
    (4, 0),
    "5F",
    "N ~1-2 min",
    ["nc"],
    ["initial:gg", "2->4", "quarks:identical-flavour"],
    waits=MQREF,
)
row(
    "A19",
    "u u~ > d d~ s s~",
    (4, 0),
    "5F",
    "E required/uux_ddxssx",
    [],
    ["initial:qqbar", "2->4", "quarks:three-lines", "quarks:distinct-flavour"],
    req("uux_ddxssx"),
)
row(
    "A20",
    "u u~ > u u~ d d~",
    (4, 0),
    "5F",
    "E required/uux_uuxddx",
    [],
    ["initial:qqbar", "2->4", "quarks:three-lines", "quarks:identical-flavour"],
    req("uux_uuxddx"),
)
row(
    "A21",
    "u u~ > u u~ u u~",
    (4, 0),
    "5F",
    "E required/uux_uuxuux",
    ["nc"],
    ["initial:qqbar", "2->4", "quarks:three-lines", "quarks:identical-flavour"],
    req("uux_uuxuux"),
)
row(
    "A22",
    "u u~ > d d~ s s~ g",
    (5, 0),
    "5F",
    "E sevenleg (MadLoop Ninja + Recola)",
    [],
    ["initial:qqbar", "2->5", "quarks:three-lines"],
    {
        "format": "mqcd",
        "path": "tests/fixtures/loop/mqcd/references/uux_ddxssxg.json",
        "providers": ["madloop", "recola"],
    },
)
row(
    "A23",
    "u u~ > g g g g g",
    (5, 0),
    "5F",
    "E required/uux_ggggg",
    [],
    ["initial:qqbar", "2->5", "quark-line:1"],
    req("uux_ggggg", ["madloop", "recola"]),
)
row(
    "A24",
    "g g > g g g g g",
    (5, 0),
    "5F",
    "E gg_ggggg_njet (NJet DD)",
    ["uv"],
    ["initial:gg", "2->5", "gluons-only", "veto:top"],
    req("gg_ggggg_njet", ["njet_dd_oneloop_R1", "njet_double_R1", "njet_double_R2"]),
    veto=[6],
)
row(
    "A25",
    "u d > u d",
    (2, 0),
    "5F",
    "N ~15 s",
    [],
    ["initial:qq", "2->2", "quarks:distinct-flavour"],
    waits=MQREF,
)
row(
    "A26",
    "u~ u~ > u~ u~",
    (2, 0),
    "5F",
    "N ~15 s",
    [],
    ["initial:qbarqbar", "2->2", "quarks:identical-flavour"],
    waits=MQREF,
)
# ---- B: top (5F, WT = 0)
row(
    "B01",
    "g g > t t~",
    (2, 0),
    "5F",
    "E required/gg_ttx (+ R for S1, S4, hel)",
    ["ap", "uv", "hel", "sp"],
    ["initial:gg", "2->2", "massive:top", "special:threshold", "special:parameters"],
    req("gg_ttx"),
)
row(
    "B02",
    "u u~ > t t~",
    (2, 0),
    "5F",
    "E top-pair-model uu (MadLoop binary64); N ~15 s",
    [],
    ["initial:qqbar", "2->2", "massive:top"],
    {
        "format": "model-control",
        "path": "tests/fixtures/loop/top-pair-model.json",
        "key": "uu",
        "providers": ["madloop"],
    },
)
row(
    "B03",
    "g g > t t~ g",
    (3, 0),
    "5F",
    "N ~20-60 s",
    ["nc", "ward"],
    ["initial:gg", "2->3", "massive:top"],
    waits=MQREF,
)
row(
    "B05",
    "g g > t t~ g g",
    (4, 0),
    "5F",
    "E required/gg_ttxgg",
    [],
    ["initial:gg", "2->4", "massive:top"],
    req("gg_ttxgg"),
)
row(
    "B06",
    "u u~ > t t~ d d~",
    (4, 0),
    "5F",
    "N ~15-60 s",
    [],
    ["initial:qqbar", "2->4", "massive:top", "quarks:distinct-flavour"],
    waits=MQREF,
)
row(
    "B07",
    "g g > t t~ t t~",
    (4, 0),
    "5F",
    "N, S ~1-4 min",
    [],
    ["initial:gg", "2->4", "massive:top", "four-tops"],
    waits=MQREF,
)
row(
    "B08",
    "g g > t t~",
    (2, 0),
    "4F",
    "N ~15 s (4F: plain loop_sm, WT = 0; = no_widths smoke)",
    [],
    ["initial:gg", "2->2", "massive:top", "scheme:4FS"],
    waits=MQREF,
    cls="Q-heavy",
)
# ---- C: massive b/c (4F)
row(
    "C01",
    "g g > b b~",
    (2, 0),
    "4F",
    "N ~10 s",
    ["nc", "ap", "ward", "sp"],
    ["initial:gg", "2->2", "massive:b", "scheme:4FS", "special:parameters"],
    waits=MQREF,
)
row(
    "C02",
    "g g > g g",
    (2, 0),
    "4F",
    "N ~10 s (b decoupled)",
    ["uv"],
    ["initial:gg", "2->2", "gluons-only", "scheme:4FS"],
    waits=MQREF,
)
row(
    "C03",
    "b b~ > h",
    (0, 1),
    "4F",
    "N, S ~10 s",
    [],
    ["initial:qqbar", "2->1", "massive:b", "yukawa:b"],
    waits=MQREF,
)
row(
    "C04",
    "b b~ > h g",
    (1, 1),
    "4F",
    "N, S ~15 s (x-rotated points)",
    [],
    ["initial:qqbar", "2->2", "massive:b", "yukawa:b"],
    waits=MQREF,
)
row(
    "C05",
    "g g > b b~ h",
    (2, 1),
    "4F",
    "N, S ~20-60 s",
    [],
    ["initial:gg", "2->3", "massive:b", "yukawa:b"],
    waits=MQREF,
)
row(
    "C06",
    "g g > t t~ b b~",
    (4, 0),
    "4F",
    "N, S ~1-4 min",
    [],
    ["initial:gg", "2->4", "massive:top", "massive:b"],
    waits=MQREF,
)
row(
    "C07",
    "u g > d t b~",
    (1, 2),
    "4F",
    "N, S ~20-60 s (4FS t-channel)",
    [],
    ["initial:qg", "2->3", "singletop:4FS-t", "massive:b"],
    waits=MQREF,
    cls="Q-singletop",
)
row(
    "C08",
    "g g > c c~",
    (2, 0),
    "CM",
    "N ~10 s (+ Recola)",
    [],
    ["initial:gg", "2->2", "massive:c"],
    waits=MQREF,
)
row(
    "C09",
    "g s > w- c",
    (1, 1),
    "CM",
    "N, S ~15 s (+ Recola; MQ-5F)",
    [],
    ["initial:qg", "2->2", "massive:c", "ew:onshell-V+jet"],
    waits="MQ-5F",
)
# ---- D: colour-singlet bosons (5F)
row(
    "D01",
    "u u~ > e- e+",
    (0, 2),
    "5F",
    "N ~15 s (+ analytic form factor)",
    ["ap", "ff"],
    ["initial:qqbar", "2->2", "ew:dilepton"],
    waits="MQ-MODEL",
    notes="stock loop_sm on the public route needs the SSS1 repair (MQ-MODEL); its reference is new (MQ-REF)",
)
row(
    "D02",
    "u u~ > e- e+",
    (0, 2),
    "W",
    "run on D01 with card widths",
    [],
    ["initial:qqbar", "2->2", "ew:dilepton", "widths:colourless"],
    waits="MQ-MODEL",
)
row(
    "D05",
    "u u~ > e- e+ g",
    (1, 2),
    "5F",
    "R runs/g1/uux_emepg",
    ["nc", "ward", "uv", "hel"],
    ["initial:qqbar", "2->3", "ew:dilepton+jets"],
    waits=MQREF,
)
row(
    "D06",
    "u u~ > e- e+ g g",
    (2, 2),
    "5F",
    "E dilepton-two-gluon (MadLoop + Recola, binary64) + R",
    [],
    ["initial:qqbar", "2->4", "ew:dilepton+jets"],
    {
        "format": "dilepton",
        "path": "tests/fixtures/loop/dilepton-two-gluon.json",
        "points": "precision",
        "providers": ["madloop", "recola"],
    },
    notes="the fixture's exact rational points (precision_points, exactly massless with exact momentum conservation); its rounded RAMBO points are off shell at binary64 rounding, which double-double resolves (Catani vs the virtual at 4e-14)",
)
row(
    "D07",
    "u u~ > e- e+ g g g",
    (3, 2),
    "5F",
    "E required/uux_emepggg",
    [],
    ["initial:qqbar", "2->5", "ew:dilepton+jets"],
    req("uux_emepggg"),
)
row(
    "D08",
    "u u~ > e- e+ d d~ g",
    (3, 2),
    "5F",
    "E required/uux_emepddxg",
    [],
    ["initial:qqbar", "2->5", "ew:dilepton+jets", "quarks:distinct-flavour"],
    req("uux_emepddxg"),
)
row(
    "D09",
    "u u~ > e- e+ m- m+",
    (0, 4),
    "5F",
    "E required/uux_emepmummp",
    [],
    ["initial:qqbar", "2->4", "ew:VV"],
    req("uux_emepmummp"),
)
row(
    "D10",
    "u u~ > u u~ e+ e-",
    (2, 2),
    "5F",
    "E required/uux_uuxepem (the 22x case)",
    [],
    ["initial:qqbar", "2->4", "ew:dilepton+jets", "quarks:identical-flavour"],
    req("uux_uuxepem"),
)
row(
    "D11",
    "u u~ > z g",
    (1, 1),
    "5F",
    "N ~15-30 s",
    [],
    ["initial:qqbar", "2->2", "ew:onshell-V+jet"],
    waits=MQREF,
)
row(
    "D12",
    "u d~ > e+ ve g",
    (1, 2),
    "5F",
    "N ~15 s",
    [],
    ["initial:qqbar", "2->3", "ew:W-leptons"],
    waits=MQREF,
)
row(
    "D13",
    "u g > a u",
    (1, 1),
    "5F",
    "N ~10 s",
    [],
    ["initial:qg", "2->2", "ew:onshell-V+jet"],
    waits=MQREF,
)
row(
    "D15",
    "u u~ > z z",
    (0, 2),
    "5F",
    "N ~15 s",
    [],
    ["initial:qqbar", "2->2", "ew:VV"],
    waits=MQREF,
)
row(
    "D16",
    "u u~ > w+ w-",
    (0, 2),
    "5F",
    "N, S ~15 s",
    [],
    ["initial:qqbar", "2->2", "ew:VV"],
    waits=MQREF,
)
row(
    "D17",
    "b b~ > w+ w-",
    (0, 2),
    "5F*",
    "N, S ~15 s (MQ-5F)",
    [],
    ["initial:qqbar", "2->2", "ew:VV"],
    waits="MQ-5F",
)
row(
    "D18",
    "u u~ > z h",
    (0, 2),
    "5F",
    "N, S ~15 s",
    [],
    ["initial:qqbar", "2->2", "ew:VH"],
    waits=MQREF,
)
row(
    "D19",
    "u d > u d h",
    (0, 3),
    "5F",
    "N ~20-60 s (VBF, QCD=0)",
    [],
    ["initial:qq", "2->3", "ew:VBF-H"],
    waits=MQREF,
)
row(
    "D20",
    "e+ e- > u u~ g",
    (1, 2),
    "5F",
    "N ~10 s",
    [],
    ["initial:leptons", "2->3", "ew:lepton-initiated-jets"],
    waits=MQREF,
)
row(
    "D21",
    "e+ e- > t t~",
    (0, 2),
    "5F",
    "E required/top-pair-ee-model-control.json (committed by MQ-REF; MadLoop binary64)",
    [],
    ["initial:leptons", "2->2", "massive:top"],
    {
        "format": "process-control",
        "path": "tests/fixtures/loop/required/top-pair-ee-model-control.json",
        "key": "ee",
        "providers": ["madloop"],
    },
)
row(
    "D23",
    "a g > u u~",
    (1, 1),
    "5F",
    "N ~10 s",
    [],
    ["initial:photon-hadron", "2->2"],
    waits=MQREF,
)
row(
    "D24",
    "e- u > e- u",
    (0, 2),
    "5F",
    "N ~10 s",
    [],
    ["initial:lepton-hadron", "2->2"],
    waits=MQREF,
)
row(
    "D25",
    "u d~ > w+ a",
    (0, 2),
    "5F",
    "N, S ~15 s",
    ["sp"],
    ["initial:qqbar", "2->2", "ew:VV", "ew:radiation-zero", "special:radiation-zero"],
    waits=MQREF,
)
row(
    "D26",
    "u u~ > e- e+ g",
    (1, 2),
    "4F",
    "N ~15 s (4F twin of D05)",
    [],
    ["initial:qqbar", "2->3", "ew:dilepton+jets", "scheme:4FS"],
    waits=MQREF,
    cls="Q-heavy",
)
row(
    "D27",
    "g u > e+ ve d",
    (1, 2),
    "5F",
    "N ~15 s",
    [],
    ["initial:qg", "2->3", "ew:W-leptons"],
    waits=MQREF,
)
# VV + jet (mq-ewjoin): every flavour-flow tree of a field current in the loops
row(
    "D28",
    "u u~ > w+ w- g",
    (1, 2),
    "4F",
    "N, S (VV + jet, 4F)",
    ["ward"],
    ["initial:qqbar", "2->3", "ew:VV+jet", "scheme:4FS"],
    waits=MQREF,
)
row(
    "D29",
    "b b~ > w+ w- g",
    (1, 2),
    "5F*",
    "N, S (VV + jet, massive t-channel line; MQ-5F)",
    ["ward"],
    ["initial:qqbar", "2->3", "ew:VV+jet"],
    waits=MQREF,
)
# ---- E: tt + X (5F, WT = 0)
row(
    "E01",
    "g g > t t~ h",
    (2, 1),
    "5F",
    "N, S ~30-90 s",
    ["nc", "ward", "uv"],
    ["initial:gg", "2->3", "ttX", "yukawa:top"],
    waits=MQREF,
)
row(
    "E02",
    "g g > t t~ z",
    (2, 1),
    "5F",
    "N, S ~30-120 s",
    [],
    ["initial:gg", "2->3", "ttX"],
    waits=MQREF,
)
row(
    "E05",
    "e+ e- > t t~ h",
    (0, 3),
    "5F",
    "E top-pair-higgs-model.json (MadLoop binary64)",
    ["ap"],  # PLAN §1.3 AP per class (the §4.2 table names no Q-ttX row)
    ["initial:leptons", "2->3", "ttX", "yukawa:top"],
    {
        "format": "model-control",
        "path": "tests/fixtures/loop/top-pair-higgs-model.json",
        "key": "ee",
        "providers": ["madloop"],
    },
)
row(
    "E06",
    "g g > t t~ e- e+ g",
    (3, 2),
    "5F",
    "E required/gg_ttxemepg_qcd + point 2 (rule 1 outlier: OpenLoops)",
    [],
    ["initial:gg", "2->5", "ttX"],
    req("gg_ttxemepg_qcd"),
)
# ---- F: single top
row(
    "F01",
    "u b > d t",
    (0, 2),
    "5F*",
    "N ~15 s",
    ["nc", "uv", "ap"],
    ["initial:qq", "2->2", "singletop:t"],
    waits="MQ-MODEL",
)
row(
    "F02",
    "b u > d t",
    (0, 2),
    "5F*",
    "N ~15 s",
    [],
    ["initial:qq", "2->2", "singletop:t"],
    waits=MQREF,
)
row(
    "F03",
    "u d~ > t b~",
    (0, 2),
    "5F",
    "N ~15 s",
    [],
    ["initial:qqbar", "2->2", "singletop:s"],
    waits="MQ-MODEL",
)
row(
    "F04",
    "g b > t w-",
    (1, 1),
    "5F*",
    "N, S ~20 s",
    ["ward"],
    ["initial:qg", "2->2", "singletop:tW"],
    waits=MQREF,
)
# ---- G, H, M, R
row(
    "G01",
    "u u~ > d d~",
    (2, 2),
    "G-full",
    "E tools/loop_reference/uudd_mixed_sm_qcd.json (= mixed-uudd-sm-qcd-control)",
    ["uv", "ap"],  # PLAN §1.3 AP per class (the §4.2 table names no Q-mixed row)
    ["initial:qqbar", "2->2", "mixed-born-orders", "ew:W-exchange"],
    {
        "format": "mixed-sm",
        "path": "tools/loop_reference/uudd_mixed_sm_qcd.json",
        "providers": ["madloop"],
    },
    loop=[{"QCD": 4, "QED": 0}, {"QCD": 2, "QED": 2}],
)
row(
    "G02",
    "u u~ > t t~",
    (2, 2),
    "5F",
    "N ~15-30 s (driver item 4)",
    [],
    ["initial:qqbar", "2->2", "mixed-born-orders", "massive:top"],
    waits=MQREF,
    loop=[{"QCD": 4, "QED": 0}, {"QCD": 2, "QED": 2}],
)
row(
    "H01",
    "u s~ > w+ g",
    (1, 1),
    "ZC",
    "N, S ~15 s + CKM-factor relation",
    ["uv", "ap"],  # PLAN §1.3 AP per class (the §4.2 table names no Q-CKM row)
    ["initial:qqbar", "2->2", "ckm:non-diagonal"],
    waits=MQREF,
)
row(
    "H02",
    "g s > t w-",
    (1, 1),
    "ZC",
    "N, S ~15 s + CKM-factor relation (MQ-5F)",
    [],
    ["initial:qg", "2->2", "ckm:non-diagonal", "singletop:tW"],
    waits="MQ-5F",
)
row(
    "H03",
    "g d > t w-",
    (1, 1),
    "CK",
    "N, S ~15 s (single-provider exception; MQ-5F)",
    [],
    ["initial:qg", "2->2", "ckm:non-diagonal", "massive:b"],
    waits="MQ-5F",
)
row(
    "M01",
    "p p > t t~",
    (2, 0),
    "5F",
    "N multi-P ~1-2 min",
    [],
    ["initial:multiparticle", "2->2", "multiparticle", "massive:top"],
    waits=MQREF,
)
row(
    "R01",
    "u u~ > m- m+",
    (0, 2),
    "LM",
    "N ~15 s",
    [],
    ["initial:qqbar", "2->2", "massive:leptons"],
    waits=MQREF,
)

assert len(R) == 78, len(R)

# Data-dependent listings (rule 1 outliers, rule 2 out-of-scope binary64
# coefficients, identically vanishing coefficients) and sector sets.
SECTORS = {
    # Born trees joining the quark lines through different weak exchanges
    # (Z or W; the gluon on the light or on the heavy line): the QCD loops
    # leave out the gluon exchanges across the lines, so the sector has no
    # Catani prediction (poles.SEPARATED_EXCHANGE; former finding F1, closed
    # by mq-ewjoin) and rule 4 checks it against MadLoop per split order.
    "D19": ([], [{"QCD": 2, "QED": 6}]),
    "C07": ([], [{"QCD": 4, "QED": 4}]),
    "G01": ([{"QCD": 6}], [{"QCD": 4, "QED": 2}, {"QCD": 2, "QED": 4}]),
    "G02": ([{"QCD": 6}], [{"QCD": 4, "QED": 2}, {"QCD": 2, "QED": 4}]),
}


# Identically vanishing coefficients (checked absolutely) and named rule 1
# reference outliers. Binary64 coefficients outside the O1 scope are reported
# by the records (E, true error), not listed: the user's ruling of
# 2026-10-29 ~10:20 (no exemption lists below ~1e-5).
LISTINGS_INDEXED = {
    # massive tops, colourless leptons: no 1/eps^2
    "D21": {
        "vanishing": [
            {"sector": "total", "coefficient": "double_pole"},
            {"sector": "QCD^2 QED^4", "coefficient": "double_pole"},
        ]
    },
    # colour-forbidden octet x singlet interference: the Born sector and the
    # double pole of the loop sector it feeds vanish identically
    "G02": {
        "vanishing": [
            {"sector": "QCD^2 QED^2", "coefficient": "born"},
            {"sector": "QCD^4 QED^2", "coefficient": "double_pole"},
        ]
    },
    # massive b, colourless h: no 1/eps^2
    "C03": {"vanishing": [{"sector": "QCD^2 QED^2", "coefficient": "double_pole"}]},
}
LISTINGS = {
    "E05": {
        "vanishing": [
            {"sector": "total", "coefficient": "double_pole"},
            {"sector": "QCD^2 QED^6", "coefficient": "double_pole"},
        ]
    },
    "E06": {
        "reference_outliers": [
            {
                "point": 0,
                "sector": "total",
                "coefficient": "finite",
                "provider": "madloop",
                "note": "MadLoop binary64 (status 216, own accuracy 5.44e-12) 1.38e-12 from DD; OpenLoops 2.0e-14, Recola 9.2e-13",
            }
        ],
    },
}


# Rule 1's relative tolerance per row. The user's ruling (slice-status
# DECISIONS 2026-10-29 ~01:12) allows 1e-10 from 2->4 up, and up to 1e-7 at
# 2->5 and beyond, "if need be": every row holds 1e-12 unless its providers'
# own precision needs more, and only such a 2->4+ row is relaxed, with its
# evidence. Campaign pt12 (slice 321efdb4), worst double-double deviation
# from the binding reference: A18 (g g > u u~ u u~) 1.17e-11 at point 2
# (MadLoop quadruple precision, Recola agrees with double-double; PLAN §6a)
# and A23 (u u~ > g g g g g) 3.18e-12 (MadLoop quadruple precision). Every
# other 2->4 and 2->5 row stays below 1e-12 (largest A22 7.0e-13).
RULE1_LOW, RULE1_HIGH = 1e-12, 1e-10
RULE1_RELAXED = {"A18": RULE1_HIGH, "A23": RULE1_HIGH}
# The user's ruling of 2026-10-29 ~10:20 (below ~1e-5 relative is not a
# finding): D28 (u u~ > w+ w- g) point 1, finite part 1.83e-12 from MadLoop's
# quadruple-precision value while 40-digit arbitrary precision equals our
# double-double to 1.2e-28 (mq-ewjoin, slice d8d9349f).
RULE1_ATTENTION = {"D28": 1e-11}


def reference_tolerance(row_id, process):
    final = len(process.split(">")[1].split())
    if row_id in RULE1_ATTENTION:
        return RULE1_ATTENTION[row_id]
    tolerance = RULE1_RELAXED.get(row_id, RULE1_LOW)
    assert tolerance == RULE1_LOW or final >= 4, row_id
    return tolerance


def loop_orders(born, loop):
    if loop is not None:
        return loop
    return {"QCD": born[0] + 2, "QED": born[1]}


def predicted(born, loop):
    # one squared sector for a single Born amplitude order
    if loop is not None:
        return None
    return [{"QCD": 2 * born[0] + 2, "QED": 2 * born[1]}]


INDEX = WT / "tests/fixtures/loop/required/mqcd_references.json"
INDEX_ROWS = {}
if len(sys.argv) > 1:
    INDEX = Path(sys.argv[1])
if INDEX.is_file():
    INDEX_ROWS = {e["row"]: e for e in json.loads(INDEX.read_text())["rows"]}
FIXTURE_ROOT = INDEX.parent.parent  # .../tests/fixtures/loop

# Rows whose Python per-point inputs exceed the nightly job budget (one
# g g > g g g g point took > 22 min, u u~ > g g g g g > 22 min at 17 GB):
# the native-input route, whose executor forms no Catani prediction (WP3.1
# I5c): rule 4 takes the harness's massless Catani operator on the tree
# engine's colour-correlated Born (catani "tree"), committed per row by
# tools/loop_benchmark/mqcd_tree_correlations.py (TREE_FIXTURE: the tree
# artifact of g g > g g g g takes 968 s and 11 GB, too much for the nightly
# job); a row without the fixture keeps catani "none" (rule 4 not formed,
# the report's status "partial"). g g > g g g g g natively: generation 180 s plus
# export, 308 s per double-double point and 69 s per binary64 point with the
# checks, 25 GB: two points keep its nightly job within 30 min.
NATIVE_ROWS = {"A14": [0, 1, 2], "A15": [0, 1, 2, 3], "A23": [0, 1, 2], "A24": [0, 1]}
TREE_FIXTURE = "tests/fixtures/loop/mqcd/references/tree-correlations-{}.json"
# The ``ward`` extra (O10 on the native input path, ``ward.ward_check``)
# checks every external massless vector leg with c = 1 and c = i at the row's
# first point; a 2->4 row checks one leg (g g > g g g g: one double-double
# Ward batch of all six legs took 222 s on 16 threads, MQ-WARD's ladder
# record ladder-gg_gggg.json, which checked every leg).
WARD_LEGS = {"A14": [1]}
# True once MQ-5F is on the slice: its rows and variants turn active
# (MQ-5F's own records of them: workspace/reports/engine-v2/mq-5f/records/).
MQ5F_LANDED = True
# Rows the tools route refuses at generation (MQ-5F: a Dirac current closing
# on a Weyl current), from the campaign's runs on MQ-REF's references.
REFUSED_5F = set() if MQ5F_LANDED else {"C09", "F03", "H02", "H03"}
# PLAN §3.0 MQ-5F: the rows the campaign runs on the default restriction
# with MB = ymb = 0 (code 5F*) also run on the restricted UFO (no_b_mass), the
# same request and reference (variant ``<id>@5F``, its own generation); the
# tools route refuses that request at generation until MQ-5F lands.
RESTRICTED_5F = ("D17", "D29", "F01", "F02", "F04")
# True once MQ-NC is on the slice: rule 7 (the ``nc`` extra) of a row is
# MQ-NC's test ids for it (``NC_COLUMN`` of NC_TESTS: the LC/NLC projection
# against the N_c scan within 1e-24 in double-double, then the row's
# independent oracles), run by MQ-NC's test files and read by build_mqcd.py
# from their JUnit XML; the LC/NLC smoke on every shipped restriction is
# NC_SMOKE (PLAN §3.2 MQ-VALIDATE item 5, MQ-NC acceptance). Not repeated by
# this harness.
MQNC_LANDED = True
NC_TESTS = "tests/unit/test_loop_v2_nc_projection.py"
NC_SMOKE = "tests/unit/test_loop_v2_nc_declaration.py::test_lc_and_nlc_smoke_on_every_shipped_restriction"


# MQ-MODEL's test of M01's bitwise half (the public route's p p > t t~
# artifact: each subprocess equals its own single-process generation).
M01_BITWISE = "tests/unit/test_loop_v2_stock_loop_sm.py::test_multiparticle_subprocesses_are_madloops_and_their_own_generations"


def nc_columns():
    """MQ-NC's ``NC_COLUMN`` (row -> its rule 7 test ids), read from NC_TESTS."""
    import importlib

    if str(WT) not in sys.path:
        sys.path.insert(0, str(WT))
    module = importlib.import_module(NC_TESTS[:-3].replace("/", "."))
    return {name: list(ids) for name, ids in module.NC_COLUMN.items()}


NC_COLUMNS = nc_columns() if MQNC_LANDED else {}
# PLAN §4.1: the H rows replace a second provider with an exact relation.
# QCD corrections preserve flavour, so a single-W-line process equals its
# diagonal twin (same masses) times |V_num|^2 / |V_den|^2, per sector and
# coefficient, Born included (CKM entries by the model's parameter names:
# loop_sm's Wolfenstein CKM1x2 = V_us, CKM1x1 = V_ud, CKM3x2 = V_ts,
# CKM3x3 = V_tb), in double-double within 1e-24.
CKM_RELATIONS = {
    "H01": {
        "twin_process": "u d~ > w+ g",
        "numerator": ["CKM1x2"],
        "denominator": ["CKM1x1"],
    },
    "H02": {
        "twin_process": "g b > t w-",
        "numerator": ["CKM3x2"],
        "denominator": ["CKM3x3"],
    },
}
# Second references of a row: runtime parameter changes (S4) and the
# non-gating z twin of C04 (PLAN §4.1).
VARIANTS = {
    "B01": {
        "required/mqcd/gg_ttx_threshold.json": (
            "threshold",
            True,
            "S1: top-pair threshold points (beta = 1e-1, 1e-2, 1e-3), MadLoop in quadruple precision",
        ),
        "required/mqcd/gg_ttx_mt170.json": ("mt170", True, "S4: MT = 170 at run time"),
    },
    "C01": {
        "required/mqcd/gg_bbx_4fs_params.json": (
            "params",
            True,
            "S4: MB = 4.5, aS = 0.13 at run time (cond(MB) and reglog CT terms)",
        )
    },
    "C04": {
        "required/mqcd/bbx_hg_4fs_z.json": (
            "z",
            False,
            "the +-z beam-axis twin of the x-rotated points: a non-gating diagnostic (PLAN §4.1)",
        )
    },
    "A09": {
        "required/mqcd/uux_ggg_soft.json": (
            "soft",
            True,
            "S2: a soft gluon (E_g / sqrt(s) = 1e-3, 1e-5), MadLoop in quadruple precision",
        ),
        "required/mqcd/uux_ggg_collinear.json": (
            "collinear",
            True,
            "S2: a collinear pair (theta = 1e-3, 1e-5; small Gram determinants), MadLoop in quadruple precision",
        ),
    },
    "D25": {
        "required/mqcd/udx_wpa_zero.json": (
            "zero",
            True,
            "S3: the radiation-zero points (0, 1) and their regular neighbour (2); no division by the Born",
        )
    },
}
# S3: the radiation-zero points and their regular neighbour (the fixture's
# point_labels).
ZERO_POINTS = {"D25@zero": {"0": 2, "1": 2}}
# Checks failing below the user's attention threshold get their row's
# tolerance relaxed, stated per row (slice-status DECISIONS 2026-10-29 ~10:20:
# a discrepancy below ~1e-5 relative is not a finding; at most
# mqcd.ATTENTION, with margin over the campaign's value; passing checks keep
# theirs). Rule -> tolerance ("2": rule 2's binary64 bound is at least this;
# "6": rule 6's 40 against 60 digits), campaign pt13 (slice a2aa0d84):
RELAXED = {
    # g g > b b~ (4FS, massive b) point 2: 40 digits reach 4.6e-32 of 60
    # digits on the finite part (the masters' arbitrary-precision small-mass
    # digits, former finding F8)
    "C01": {"6": 1e-30},
    # g g > b b~ h (4FS) point 1: binary64 finite 2.3e-10 from double-double
    # at E = 3.2e-11 (within rule 3's 10 E; former finding F6)
    "C05": {"2": 1e-8},
    # S2 soft gluon, E_g / sqrt(s) = 1e-5 (point 1): the binary64 Born itself
    # is 1.16e-11 from double-double (no estimate exists for the Born)
    "A09@soft": {"2": 1e-9},
}
assert all(0 < t <= 1e-5 for rules in RELAXED.values() for t in rules.values())
# M01: MadLoop's SubProcesses/P* of `generate p p > t t~ [virt=QCD]` on
# loop_sm-no_b_mass (workspace/reference/runs/mqcd/pp_ttx/madloop-export,
# the "C Process:" lines), and one subprocess variant per P reference.
MADLOOP_SUBPROCESSES = {
    "P0_uux_ttx": [
        "b b~ > t t~",
        "c c~ > t t~",
        "d d~ > t t~",
        "s s~ > t t~",
        "u u~ > t t~",
    ],
    "P2_gg_ttx": ["g g > t t~"],
}
SUBPROCESS_VARIANTS = {
    "required/mqcd/pp_ttx_P0_uux_ttx.json": ("P0", "u u~ > t t~"),
    "required/mqcd/pp_ttx_P2_gg_ttx.json": ("P2", "g g > t t~"),
}
# Index references a row does not use (none since MQ-REF's fix round 2).
# MQ-REF's reruns of the rows with an existing reference (``*_sectors``: the
# same points plus the mu_R = mu_0/2 point of PLAN §4.1, MadLoop's split
# orders and per-sector accuracy, quadruple precision at every point since
# fix round 2; and its MadLoop runs of A02, B02, D06, whose existing
# references are MadLoop controls) are gating variants of the row
# (``<id>@sectors``, ``<id>@madloop``): the rows keep their existing
# (multi-provider) fixtures as the primary reference.
UNUSED = set()
# A variant's nightly points when not all of its fixture's (cost): B05's
# rerun repeats the existing fixture's three points (263 s per point, both
# carriers, at pt7) and adds the mu_R = mu_0/2 point 3.
VARIANT_POINTS = {"B05@sectors": [3]}


def resolve(path):
    """A reference path in this worktree, else below the index's checkout."""
    local = WT / path
    return local if local.is_file() else FIXTURE_ROOT.parent.parent.parent / path


def provider_list(fixture):
    names = list(fixture["rows"][0]["providers"])
    primary = fixture.get("primary_provider", names[0])
    return [primary] + [p for p in names if p != primary]


def rerun_variants(rid):
    """MQ-REF's main runs of a row that keeps an existing reference, as
    gating variants (``sectors`` for a ``*_sectors`` rerun, else
    ``madloop``) at every point of their fixture (``VARIANT_POINTS``)."""

    entry = INDEX_ROWS.get(rid)
    if entry is None:
        return []
    out = []
    for x in entry["references"]:
        if (
            x["status"] != "committed"
            or not x.get("fixture")
            or x["fixture"] in VARIANTS.get(rid, {})
            or x["fixture"] in UNUSED
            or not (FIXTURE_ROOT / x["fixture"]).is_file()
        ):
            continue
        name = "sectors" if x["fixture"].endswith("_sectors.json") else "madloop"
        vf = json.loads((FIXTURE_ROOT / x["fixture"]).read_text())
        points = VARIANT_POINTS.get(f"{rid}@{name}", list(range(len(vf["points"]))))
        out.append(
            {
                "name": name,
                "gating": True,
                "tier": "nightly",
                "notes": "MQ-REF's MadLoop run of the row ("
                + (x.get("note") or x["run"])
                + "); quadruple precision at every point (fix round 2)",
                "extras": [],
                "extras_pending": {},
                "reference": {
                    "format": "required",
                    "path": f"tests/fixtures/loop/{x['fixture']}",
                    "providers": provider_list(vf),
                },
                "points": {"nightly": points},
            }
        )
    return out


def helicity_fixture(rid):
    """The fixture of MQ-REF's per-helicity run of a row (the index row's
    ``helicity_reference``: a run name, or its fixture below tests/fixtures/loop), or None."""
    entry = INDEX_ROWS.get(rid) or {}
    run = entry.get("helicity_reference")
    if not run:
        return None
    found = [
        x
        for x in entry["references"]
        if run in (x["run"], x.get("fixture"), f"required/mqcd/{x['run']}.json")
    ]
    if len(found) != 1:
        raise ValueError(f"{rid}: helicity_reference {run} is not one run of the row")
    if found[0]["status"] != "committed":
        return HEL_PENDING
    if not (FIXTURE_ROOT / found[0]["fixture"]).is_file():
        raise ValueError(f"{rid}: helicity_reference {run} has no fixture")
    return f"tests/fixtures/loop/{found[0]['fixture']}"


# helicity_fixture of a row whose per-helicity run is not committed yet
HEL_PENDING = "pending"


def superseded_points(rid, reference):
    """The points of a row's existing reference that MQ-REF's quadruple-
    precision rerun supersedes (the index's ``existing_references[*].
    point_binding``, schema mqcd-references/2): {point: {"path", "row"}}."""
    entry = INDEX_ROWS.get(rid) or {}
    if not reference:
        return {}
    out = {}
    for x in entry.get("existing_references", []):
        if f"tests/fixtures/loop/{x['fixture']}" != reference["path"]:
            continue
        for i, b in enumerate(x.get("point_binding") or []):
            if not b["binding"]:
                out[str(i)] = {
                    "path": f"tests/fixtures/loop/{b['superseded_by']['fixture']}",
                    "row": b["superseded_by"]["row"],
                }
    return out


def index_reference(rid):
    """(reference spec, fixture, variants) of a row from MQ-REF's index."""
    entry = INDEX_ROWS.get(rid)
    if entry is None:
        return None
    found = [
        x
        for x in entry["references"]
        if x["status"] == "committed"
        and x.get("fixture")
        and (FIXTURE_ROOT / x["fixture"]).is_file()
        and x["fixture"] not in UNUSED
    ]
    if not found:
        return None
    main = [x for x in found if x["fixture"] not in VARIANTS.get(rid, {})]
    # A per-helicity run at its own points is not the row's main reference
    # (unless it is its only run).
    hel_run = entry.get("helicity_reference")
    main = [x for x in main if hel_run not in (x["run"], x["fixture"])] or main
    spec = fixture = None
    if main:
        first = main[0]
        path = FIXTURE_ROOT / first["fixture"]
        fixture = json.loads(path.read_text())
        spec = {
            "format": "required",
            "path": f"tests/fixtures/loop/{first['fixture']}",
            "providers": provider_list(fixture),
        }
    variants = []
    if rid == "M01":
        for x in found:
            name, process = SUBPROCESS_VARIANTS[x["fixture"]]
            vf = json.loads((FIXTURE_ROOT / x["fixture"]).read_text())
            single = {
                "name": name,
                "gating": True,
                "tier": "nightly",
                "subprocess": True,
                "process": process,
                "notes": f"MadLoop SubProcesses/{vf['mqcd_run']['subprocess']} of p p > t t~ (its single-process generation, tools route)",
                "reference": {
                    "format": "required",
                    "path": f"tests/fixtures/loop/{x['fixture']}",
                    "providers": provider_list(vf),
                },
                "points": {"nightly": list(range(len(vf["points"])))},
            }
            variants.append(single)
            # PLAN §4.2 M01 on the public route (MQ-MODEL): the same
            # subprocess in the multiparticle artifact of p p > t t~ on the
            # shipped loop_sm, at the same points and reference.
            variants.append(
                {
                    **single,
                    "name": f"public-{name}",
                    "route": "public",
                    "catani": "none",
                    "notes": f"MadLoop SubProcesses/{vf['mqcd_run']['subprocess']}: the subprocess {process} of the public route's multiparticle artifact of p p > t t~ (model.source = loop_sm)",
                }
            )
        return spec, fixture, variants
    for x in found:
        if x["fixture"] in VARIANTS.get(rid, {}):
            name, gating, note = VARIANTS[rid][x["fixture"]]
            vf = json.loads((FIXTURE_ROOT / x["fixture"]).read_text())
            variants.append(
                {
                    "name": name,
                    "gating": gating,
                    "tier": "nightly",
                    "notes": note,
                    # a variant runs the core rules on its own reference
                    "extras": [],
                    "extras_pending": {},
                    **(
                        {"relaxed": RELAXED[f"{rid}@{name}"]}
                        if f"{rid}@{name}" in RELAXED
                        else {}
                    ),
                    **(
                        {"zero_points": ZERO_POINTS[f"{rid}@{name}"]}
                        if f"{rid}@{name}" in ZERO_POINTS
                        else {}
                    ),
                    "reference": {
                        "format": "required",
                        "path": f"tests/fixtures/loop/{x['fixture']}",
                        "providers": provider_list(vf),
                    },
                    "points": {"nightly": list(range(len(vf["points"])))},
                }
            )
    return spec, fixture, variants


rows = []
for r in R:
    code = r["code"]
    if code == "G-full":
        restriction, fixed, scheme = "none", None, "qcd-full-sm-ckm"
    else:
        restriction, fixed, scheme = CODES[code]
    fixed = dict(fixed) if fixed else {}
    reference = r["reference"]
    variants = []
    indexed = index_reference(r["id"])
    if indexed and reference:
        # An existing reference keeps it; the variants and MQ-REF's reruns
        # of the row (its main runs) join as gating variants.
        variants = indexed[2] + rerun_variants(r["id"])
        indexed = None
    if indexed and indexed[0] is None:
        indexed = None
    if indexed:
        reference, fixture0, variants = indexed
        # M01 is composite (its parts below; MQ-MODEL is on the slice).
        r["waits"] = "MQ-5F" if r["id"] in REFUSED_5F else None
        restriction = INDEX_ROWS[r["id"]]["pyamplicol_route"]["restriction"]
    params = {}
    if reference:
        data = json.loads(resolve(reference["path"]).read_text())
        if reference["format"] in ("required", "model-control", "dilepton"):
            fixed = dict(data.get("fixed_parameters", fixed))

        if reference["format"] == "mixed-sm":
            fixed = {k: v for k, v in data["fixed_parameters"].items() if k != "WTau"}
            r["ignored"] = ["WTau"]
        if reference["format"] in ("providers", "component-control"):
            params = {"aS": "0.118", "MT": "173"}
    tier = "default" if r["id"] in DEFAULT_ROWS else "nightly"
    status = "active" if reference and not r["waits"] else "pending"
    count = 3
    if reference:
        data = json.loads(resolve(reference["path"]).read_text())
        count = len(
            data["precision_points"]
            if reference.get("points") == "precision"
            else (data["points"] if "points" in data else data["fixture"]["points"])
        )
    points = r["points"] or (
        {"default": [0, 1], "nightly": list(range(2, count))}
        if tier == "default"
        else {"nightly": list(range(count))}
    )
    superseded = superseded_points(r["id"], reference)
    if superseded:
        # MQ-REF's quadruple-precision rerun of the existing reference is
        # the binding reference at the points it re-evaluates: the row's
        # rule 1 holds its values there, and its gating variant keeps only
        # the rows the row's tiers do not run (the mu_0/2 point).
        reference = {**reference, "superseded": superseded}
        covered = {i for tier_points in points.values() for i in tier_points}
        for variant in variants:
            taken = {
                b["row"]
                for i, b in superseded.items()
                if int(i) in covered and b["path"] == variant["reference"]["path"]
            }
            if taken:
                variant["points"] = {
                    "nightly": [
                        i for i in variant["points"]["nightly"] if i not in taken
                    ]
                }
                # Its own outlier listings at the rows it keeps (the row's
                # reference outliers are not the rerun's).
                variant["reference_outliers"] = [
                    e
                    for e in variant.get("reference_outliers", [])
                    if e["point"] in variant["points"]["nightly"]
                ]
                variant["notes"] += (
                    "; its rows "
                    + ", ".join(map(str, sorted(taken)))
                    + " supersede the row's reference at the same points (the row's rule 1 holds them)"
                )
        variants = [v for v in variants if v["points"]["nightly"]]
    entry = {
        "id": r["id"],
        "class": r["cls"] or CLASS[r["id"][0]],
        "process": r["process"],
        "born_orders": {"QCD": r["born"][0], "QED": r["born"][1]},
        "loop_orders": loop_orders(r["born"], r["loop"]),
        "corrections": ["QCD"],
        "restriction": restriction,
        "restriction_code": code,
        "fixed_parameters": fixed,
        "gauge": "unitary",
        "scheme": scheme,
        "tier": tier,
        "status": status,
        "reference_legend": r["legend"],
        "reference": reference,
        "points": points,
        "extras": r["extras"],
        "features": r["features"],
        "predicted_sectors": predicted(r["born"], r["loop"]) or [],
        "unpredicted_sectors": [],
        "reference_outliers": [],
        "vanishing": [],
        "reference_tolerance": reference_tolerance(r["id"], r["process"]),
    }
    if params:
        entry["parameters"] = params
    if r["id"] in SECTORS:
        entry["predicted_sectors"], entry["unpredicted_sectors"] = SECTORS[r["id"]]
    entry.update(LISTINGS.get(r["id"], {}))
    if indexed or r["id"] in ("D21",):
        entry.update(LISTINGS_INDEXED.get(r["id"], {}))
    if superseded:
        # An outlier of the existing reference at a point the rerun
        # supersedes is no longer the reference's.
        entry["reference_outliers"] = [
            o for o in entry["reference_outliers"] if str(o["point"]) not in superseded
        ]
    if r["veto"]:
        entry["particle_veto"] = r["veto"]
    if r.get("ignored"):
        entry["ignored_fixed_parameters"] = r["ignored"]
    if status == "pending":
        entry["pending"] = {
            "waits_for": r["waits"] or MQREF,
            "reason": "reference not yet produced (PLAN §4.2 legend: "
            + r["legend"]
            + ")"
            if (r["waits"] or MQREF) == MQREF
            else "public-route or admission package: " + (r["waits"]),
        }
    if r["notes"]:
        entry["notes"] = r["notes"]
    if r["id"] in RESTRICTED_5F and reference:
        variants.append(
            {
                "name": "5F",
                "gating": True,
                "tier": "nightly",
                "restriction": "no_b_mass",
                "restriction_code": "5F",
                # The row's (and its reference's) parameters, code 5F's.
                "fixed_parameters": dict(CODES["5F"][1]),
                "notes": "PLAN §3.0 MQ-5F: the row's request on the restricted UFO (no_b_mass), against the row's reference (so equal to its default-restriction MB = ymb = 0 route under §1.4)",
                "extras": [],
                "extras_pending": {},
                "reference": reference,
                "points": {"nightly": sorted({i for t in points.values() for i in t})},
                **(
                    {}
                    if MQ5F_LANDED
                    else {
                        "status": "pending",
                        "pending": {
                            "waits_for": "MQ-5F",
                            "reason": "the tools route refuses the restricted-UFO request at generation (a Dirac current closing on a Weyl current: the MQ-5F class)",
                        },
                    }
                ),
            }
        )
    if variants:
        entry["variants"] = variants
    hel_fixture = helicity_fixture(r["id"])
    if hel_fixture == HEL_PENDING:
        pass
    elif hel_fixture and (
        not entry.get("reference") or hel_fixture != entry["reference"]["path"]
    ):
        entry["helicity_reference"] = hel_fixture
    elif r["id"] == "B01" and not hel_fixture:
        # MQ-REF's per-helicity run of B01's points (an index without the
        # row's ``helicity_reference``)
        entry["helicity_reference"] = (
            "tests/fixtures/loop/required/mqcd/gg_ttx_sectors.json"
        )
    if r["id"] in CKM_RELATIONS:
        entry["ckm_relation"] = CKM_RELATIONS[r["id"]]
    if r["id"] in WARD_LEGS:
        entry["ward_legs"] = WARD_LEGS[r["id"]]
    if r["id"] in RELAXED:
        entry["relaxed"] = RELAXED[r["id"]]
    if r["id"] in NATIVE_ROWS:
        entry["inputs"] = "native"
        tree = TREE_FIXTURE.format(r["id"])
        if (WT / tree).is_file():
            entry["catani"], entry["tree_correlations"] = "tree", tree
        else:
            entry["catani"] = "none"
        entry["points"] = {"nightly": NATIVE_ROWS[r["id"]]}
    if status == "pending" and r["id"] in REFUSED_5F and indexed:
        entry["pending"]["reason"] = (
            "the reference exists (MQ-REF); the tools route refuses the request at generation: a Dirac (massive) current cannot close on a Weyl current (the MQ-5F class)"
        )
    if r["id"] == "M01" and indexed:
        # PLAN §4.2 M01, a row of its parts: the expansion against MadLoop's
        # P directories (``madloop_subprocesses``), each P reference against
        # the subprocess's own generation (M01@P<n>) and against the public
        # route's multiparticle artifact (M01@public-P<n>), and MQ-MODEL's
        # test that each subprocess of that artifact is bitwise its own
        # single-process generation (``delegated``).
        entry["status"] = "composite"
        entry["reference"] = None
        entry["madloop_subprocesses"] = MADLOOP_SUBPROCESSES
        entry["delegated"] = {"bitwise": [M01_BITWISE]}
    pend = {}
    for e in r["extras"]:
        if e == "nc" and MQNC_LANDED:
            # A row's nc extra without MQ-NC ids is a KeyError here.
            entry.setdefault("delegated", {})["nc"] = NC_COLUMNS[r["id"]]
        elif e == "nc":
            pend[e] = (
                "MQ-NC (shipped N_c declaration and its independent oracles; rule 7)"
            )
        elif e == "hel" and r["id"] not in ("A08", "B01", "D05"):
            pend[e] = "MQ-REF (per-helicity SLOOPMATRIXHEL references)"
        elif e == "hel" and hel_fixture == HEL_PENDING:
            pend[e] = "MQ-REF (the row's per-helicity run is not committed yet)"
        elif e == "sp" and not any(v.get("gating", True) for v in variants):
            pend[e] = "MQ-REF (supplied special points S1-S4)"
    if pend:
        entry["extras_pending"] = pend
    rows.append(entry)
# MQ-NC's columns are the nc rows', no more and no fewer.
assert not MQNC_LANDED or set(NC_COLUMNS) == {
    r["id"] for r in rows if "nc" in r["extras"]
}, sorted(set(NC_COLUMNS) ^ {r["id"] for r in rows if "nc" in r["extras"]})

# The nightly tier's file jobs (PLAN §3.2 acceptance: each nightly file job
# <= 30 min). (seconds, points) per nightly test id as measured by the
# campaign run pt9 of 2026-10-28 ~23:00 UTC (tmp/mq-validate/pt9: the seven
# nightly files as whole files, one process each, pytest --durations setup +
# call + teardown, on the shared host at load ~110; the first id of a file
# carries its model compilation); an id whose point count differs from the
# measured one counts its seconds scaled by the point ratio, an id without a
# measurement DEFAULT_SECONDS. A row and its variants (which reuse its
# generation) form one group; groups are packed greedily, largest first, into
# jobs of at most JOB_SECONDS (a group above it is a job of its own); job 1
# also holds the restriction smokes and the M01 expansion (SMOKE_SECONDS).
MEASURED_SECONDS = {
    "A01": (31, 1), "A01@sectors": (29, 4), "A02": (20, 3), "A02@madloop": (19, 4),
    "A03": (32, 4), "A04": (16, 2), "A05": (29, 4), "A06": (19, 3),
    "A06@sectors": (18, 4), "A07": (24, 4), "A08": (483, 4), "A09": (40, 2),
    "A09@collinear": (18, 3), "A09@soft": (23, 2), "A12": (13, 1),
    "A12@sectors": (22, 4), "A13": (39, 3), "A13@sectors": (23, 4), "A14": (254, 3),
    "A15": (60, 4), "A18": (138, 4), "A19": (30, 3), "A19@sectors": (28, 4),
    "A20": (34, 3), "A20@sectors": (33, 4), "A21": (51, 3), "A21@sectors": (47, 4),
    "A22": (178, 3), "A23": (709, 3), "A24": (1351, 2), "A25": (23, 4), "A26": (24, 4),
    "B01": (30, 1), "B01@mt170": (21, 4), "B01@sectors": (20, 4),
    "B01@threshold": (15, 3), "B02": (19, 3), "B02@madloop": (18, 4), "B03": (86, 4),
    "B05": (804, 3), "B05@sectors": (254, 1), "B06": (45, 4), "B07": (349, 4),
    "B08": (30, 4), "C01": (45, 2), "C01@params": (21, 4), "C02": (43, 4),
    "C03": (22, 4), "C04": (25, 4), "C05": (41, 4), "C06": (296, 4), "C07": (28, 4),
    "C08": (30, 4), "D01": (20, 2), "D02": (21, 4), "D05": (45, 2), "D06": (29, 3),
    "D06@madloop": (23, 4), "D07": (108, 3), "D07@sectors": (113, 4), "D08": (47, 3),
    "D08@sectors": (36, 4), "D09": (20, 3), "D09@sectors": (18, 4), "D10": (24, 3),
    "D10@sectors": (21, 4), "D11": (28, 4), "D12": (25, 4), "D13": (24, 4),
    "D15": (22, 4), "D16": (22, 4), "D17": (26, 4), "D18": (21, 4), "D19": (23, 4),
    "D20": (27, 4), "D21": (16, 3), "D23": (26, 4), "D24": (21, 4), "D25": (22, 4),
    "D25@zero": (14, 3), "D26": (28, 4), "D27": (23, 4), "E01": (71, 4),
    # mq-ewjoin (tmp/mq-ewjoin/h-d28, h-d29, 2026-10-29 ~11:25 UTC).
    "D28": (50, 4), "D29": (50, 4),
    "E02": (43, 4), "E05": (19, 3), "E06": (175, 3), "E06@sectors": (179, 4),
    "F01": (35, 4), "F02": (24, 4), "F04": (37, 4), "G01": (24, 1), "G02": (29, 4),
    "H01": (48, 4), "M01@P0": (24, 4), "M01@P2": (26, 4), "R01": (24, 4),
    # MQ-5F's ids (pending until MQ5F_LANDED), measured the same way on the
    # merge tree of this branch and work/v2-mq-5f ef1c12f0 with its native
    # (tmp/mq-validate/s7, 2026-10-29 ~02:05 UTC, one process per file job).
    "C09": (31, 4), "F03": (18, 2), "H02": (43, 4), "H03": (30, 4),
    "D17@5F": (31, 4), "F01@5F": (23, 4), "F02@5F": (22, 4), "F04@5F": (26, 4),
    # M01 on the public route (tmp/mq-validate/s8, ~02:35 UTC; the first
    # carries the multiparticle generation).
    "M01@public-P0": (55, 4), "M01@public-P2": (15, 4),
}  # fmt: skip
DEFAULT_SECONDS = 60
JOB_SECONDS = 1200
SMOKE_SECONDS = 75


def nightly_groups(rows):
    """(seconds, [ids]) per row with nightly test ids: the row (if it has
    nightly points or checked extras) and its gating variants."""

    checked = {"ap", "uv", "hel", "sp", "ward"}
    groups = []
    for r in rows:
        ids = []
        if r["status"] == "active" and (
            r["points"].get("nightly") or set(r["extras"]) & checked
        ):
            ids.append(r["id"])
        ids += [
            f"{r['id']}@{v['name']}"
            for v in r.get("variants", ())
            if v.get("gating", True)
            and v.get("status", "active") == "active"
            and v["points"].get("nightly")
        ]
        if ids:
            groups.append((sum(id_seconds(r, i) for i in ids), ids))
    return groups


def id_seconds(row, name):
    """The measured seconds of a nightly id, scaled to its current points."""
    if name not in MEASURED_SECONDS:
        return DEFAULT_SECONDS
    seconds, measured = MEASURED_SECONDS[name]
    if "@" in name:
        variant = next(v for v in row["variants"] if v["name"] == name.split("@")[1])
        points = len(variant["points"]["nightly"])
    else:
        points = len(row["points"].get("nightly", ()))
    return (
        seconds
        if points == measured or not points
        else -(-seconds * points // measured)
    )


def nightly_jobs(rows):
    jobs = [{"job": 1, "seconds": SMOKE_SECONDS, "rows": []}]
    for seconds, ids in sorted(nightly_groups(rows), key=lambda g: (-g[0], g[1])):
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
        suffix = "" if job["job"] == 1 else f"_{job['job']}"
        job["file"] = f"tests/unit/test_loop_v2_mqcd_nightly{suffix}.py"
    return jobs


NIGHTLY_JOBS = nightly_jobs(rows)
FEATURES = sorted({f for r in rows for f in r["features"]})
manifest = {
    "schema_version": 1,
    "plan": "workspace/reports/engine-v2/m-qcd/PLAN.md §1.4, §3.2 MQ-VALIDATE, §4",
    "description": "M-QCD validation campaign rows (one per PLAN §4.2 row). tools/loop_benchmark/mqcd.py reads it; tests/unit/test_loop_v2_mqcd_*.py run it.",
    "process_aliases": {"mu-": "m-", "mu+": "m+"},
    "restriction_codes": {
        k: {"restriction": v[0], "fixed_parameters": v[1], "scheme": v[2]}
        for k, v in CODES.items()
    },
    "classes": [
        "Q-massless",
        "Q-top",
        "Q-heavy",
        "Q-EWBorn",
        "Q-ttX",
        "Q-singletop",
        "Q-mixed",
        "Q-CKM",
        "Q-multi",
    ],
    "features": FEATURES,
    "restrictions_in_scope": [
        "default",
        "no_b_mass",
        "no_widths",
        "no_masses",
        "no_tau_mass",
        "lepton_masses",
        "c_mass",
        "ckm",
        "zeromass_ckm",
    ],
    "smokes": {
        "same_request": {
            "no_masses": {"row": "A12"},
            "no_tau_mass": {"row": "A12"},
            "no_widths": {"row": "B08", "points_from": "B01"},
        },
        "lc_every_restriction": {"test": NC_SMOKE} if MQNC_LANDED else "MQ-NC",
    },
    "nightly_jobs": {
        "budget_seconds": JOB_SECONDS,
        "measurement": "seconds per nightly test id, campaign run of 2026-10-28 (one process per id, shared host at load ~100, start-up included)",
        "jobs": NIGHTLY_JOBS,
    },
    "rows": rows,
}
out = WT / "tests/fixtures/loop/mqcd/manifest.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(manifest, indent=1) + "\n")
print("rows", len(rows), "active", sum(r["status"] == "active" for r in rows))
print("features", FEATURES)
