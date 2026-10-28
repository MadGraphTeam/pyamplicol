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
acceptance rules (rule 1 outliers, binary64 coefficients outside the O1
scope, identically vanishing coefficients, sector sets) are recorded from
the campaign's runs with their evidence in comments. Re-run it when MQ-REF
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
    ["ap"],
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
    [],
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
    ["uv"],
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
    ["uv"],
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

assert len(R) == 76, len(R)

# Data-dependent listings (rule 1 outliers, rule 2 out-of-scope binary64
# coefficients, identically vanishing coefficients) and sector sets.
SECTORS = {
    "G01": ([{"QCD": 6}], [{"QCD": 4, "QED": 2}, {"QCD": 2, "QED": 4}]),
    "G02": ([{"QCD": 6}], [{"QCD": 4, "QED": 2}, {"QCD": 2, "QED": 4}]),
}


def oos(point, sector, coefficient, E, err):
    return {
        "point": point,
        "sector": sector,
        "coefficient": coefficient,
        "E": E,
        "true_error": err,
    }


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
    "D16": {
        "binary64_out_of_scope": [
            oos(0, "QCD^2 QED^4", "finite", 3.93e-09, 3.06e-11),
            oos(0, "QCD^2 QED^4", "single_pole", 3.18e-09, 9.81e-13),
            oos(3, "QCD^2 QED^4", "finite", 6.86e-09, 2.97e-11),
            oos(3, "QCD^2 QED^4", "single_pole", 1.76e-09, 4.23e-13),
        ]
    },
    "B03": {
        "binary64_out_of_scope": [
            oos(0, "QCD^8", "finite", 1.96e-09, 1.06e-09),
            oos(0, "QCD^8", "single_pole", 1.92e-09, 6.76e-10),
            oos(0, "QCD^8", "double_pole", 1.23e-09, 1.18e-09),
            oos(1, "QCD^8", "single_pole", 1.54e-09, 1.05e-10),
            oos(3, "QCD^8", "finite", 2.14e-09, 7.69e-10),
            oos(3, "QCD^8", "single_pole", 1.50e-08, 1.17e-08),
            oos(3, "QCD^8", "double_pole", 1.23e-09, 1.18e-09),
        ]
    },
    # the first three points' binary64 (precedent test_loop_v2_fermion_lines.py)
    "A18": {
        "binary64_out_of_scope": [
            oos(0, "QCD^10", "finite", 2.60e-08, 1.05e-08),
            oos(0, "QCD^10", "single_pole", 2.43e-09, 3.11e-10),
            oos(0, "QCD^10", "double_pole", 1.87e-09, 5.48e-10),
            oos(1, "QCD^10", "finite", 1.82e-09, 3.58e-10),
            oos(2, "QCD^10", "finite", 5.80e-08, 5.55e-08),
            oos(2, "QCD^10", "single_pole", 1.24e-08, 2.23e-09),
            oos(2, "QCD^10", "double_pole", 1.21e-08, 4.19e-10),
            oos(3, "QCD^10", "finite", 8.69e-08, 4.52e-08),
            oos(3, "QCD^10", "single_pole", 5.37e-09, 1.01e-09),
            oos(3, "QCD^10", "double_pole", 1.87e-09, 5.48e-10),
        ]
    },
}
LISTINGS = {
    # the E1 point (PLAN §6: G1 binary64 2.42e-7 with E = 4.72e-6): outside
    # the O1 binary64 scope, bracketed (rule 3); E1 stays open for the user
    "A14": {
        "binary64_out_of_scope": [
            oos(1, "QCD^10", "finite", 4.74e-06, 2.50e-07),
            oos(1, "QCD^10", "single_pole", 2.21e-06, 1.59e-07),
        ]
    },
    # g g > g g g g g binary64 (g1.json: E = 1.36e-8 / 7.69e-8 at points 0, 1)
    "A24": {
        "binary64_out_of_scope": [
            oos(0, "QCD^12", "finite", 1.36e-08, 1.40e-09),
            oos(0, "QCD^12", "single_pole", 5.15e-09, 6.79e-10),
            oos(1, "QCD^12", "finite", 7.78e-08, 2.00e-09),
            oos(1, "QCD^12", "single_pole", 5.38e-08, 2.00e-09),
        ]
    },
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
        "binary64_out_of_scope": [
            {
                "point": 2,
                "sector": "QCD^8 QED^4",
                "coefficient": "finite",
                "E": 3.42e-08,
                "true_error": 5.66e-09,
            }
        ],
    },
}


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
# the native-input route, which forms no Catani prediction (rule 4 recorded
# as not formed; WP3.1 I5c). g g > g g g g g natively: generation 180 s plus
# export, 308 s per double-double point and 69 s per binary64 point with the
# checks, 25 GB: two points keep its nightly job within 30 min.
NATIVE_ROWS = {"A14": [0, 1, 2], "A15": [0, 1, 2, 3], "A23": [0, 1, 2], "A24": [0, 1]}
# The ``ward`` extra (O10 on the native input path, ``ward.ward_check``)
# checks every external massless vector leg with c = 1 and c = i at the row's
# first point; a 2->4 row checks one leg (g g > g g g g: one double-double
# Ward batch of all six legs took 222 s on 16 threads, MQ-WARD's ladder
# record ladder-gg_gggg.json, which checked every leg).
WARD_LEGS = {"A14": [1]}
# Binary64 Ward evaluations outside the O1 scope (E_k / scale_k > 1e-9),
# from the campaign run of 2026-10-28 (tmp/mq-validate/pt6, B03 point 0):
# the final-state gluon of g g > t t~ g, whose substituted amplitude cancels
# to 1.2e-9 and 3.3e-9 of the physical scale with an estimate of 3.5e-8
# (bracketed: |V_k| / E_k = 0.09, 0.17); double-double holds the identity
# (1.9e-26 of the scale).
WARD_OUT_OF_SCOPE = {
    "B03": [
        {"point": 0, "leg": 5, "factor": [1, 0], "E": 3.54e-08, "true_error": 1.24e-09},
        {"point": 0, "leg": 5, "factor": [0, 1], "E": 3.54e-08, "true_error": 3.26e-09},
    ]
}
# Rows the tools route refuses at generation (MQ-5F: a Dirac current closing
# on a Weyl current), from the campaign's runs on MQ-REF's references.
REFUSED_5F = {"C09", "F03", "H02", "H03"}
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
# S1 (PLAN §4.1): binary64 is expected outside the O1 scope at the limit
# points; they are listed, double-double and rule 3 must pass.
VARIANT_LISTINGS = {
    # S2 soft gluon, E_g / sqrt(s) = 1e-5 (point 1): the binary64 Born itself
    # loses digits (no estimate), the Laurent coefficients are outside the O1
    # scope and bracketed (rule 3).
    "A09@soft": {
        "binary64_out_of_scope": [
            {
                "point": 1,
                "sector": "QCD^6",
                "coefficient": "born",
                "E": None,
                "true_error": 1.16e-11,
            },
            {
                "point": 1,
                "sector": "QCD^8",
                "coefficient": "finite",
                "E": 9.35e-07,
                "true_error": 6.26e-07,
            },
            {
                "point": 1,
                "sector": "QCD^8",
                "coefficient": "single_pole",
                "E": 1.47e-06,
                "true_error": 7.06e-07,
            },
            {
                "point": 1,
                "sector": "QCD^8",
                "coefficient": "double_pole",
                "E": 5.22e-07,
                "true_error": 2.31e-07,
            },
        ]
    },
    "B01@threshold": {
        "binary64_out_of_scope": [
            {
                "point": 1,
                "sector": "QCD^6",
                "coefficient": "finite",
                "E": 1.73e-09,
                "true_error": 1.21e-10,
            },
            {
                "point": 1,
                "sector": "QCD^6",
                "coefficient": "single_pole",
                "E": 5.65e-09,
                "true_error": 6.24e-12,
            },
            {
                "point": 2,
                "sector": "QCD^6",
                "coefficient": "finite",
                "E": 2.89e-06,
                "true_error": 1.74e-07,
            },
            {
                "point": 2,
                "sector": "QCD^6",
                "coefficient": "single_pole",
                "E": 4.61e-05,
                "true_error": 8.7e-10,
            },
            {
                "point": 2,
                "sector": "QCD^6",
                "coefficient": "double_pole",
                "E": 7.49e-09,
                "true_error": 2.95e-10,
            },
        ]
    },
}
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
# Index references a row does not use: B01's per-sector copy of its
# three-provider required/gg_ttx.json (one sector: the same values).
# MQ-REF batch 2's ``*_sectors`` reruns of the rows with an existing
# reference (the same points, MadLoop's split orders): the rows keep their
# multi-provider fixtures (second providers for rule 1's outlier route);
# B01's carries the per-helicity rows (``helicity_reference``).
UNUSED = {
    "required/mqcd/" + name
    for name in (
        "gg_gg_sectors.json",
        "gg_ttxemepg_qcd_sectors.json",
        "gg_ttxgg_sectors.json",
        "gg_ttx_sectors.json",
        "uux_ddxg_sectors.json",
        "uux_ddxssx_sectors.json",
        "uux_emepddxg_sectors.json",
        "uux_emepggg_sectors.json",
        "uux_emepmummp_sectors.json",
        "uux_uuxddx_sectors.json",
        "uux_uuxepem_sectors.json",
        "uux_uuxg_sectors.json",
        "uux_uux_sectors.json",
        "uux_uuxuux_sectors.json",
    )
}


def resolve(path):
    """A reference path in this worktree, else below the index's checkout."""
    local = WT / path
    return local if local.is_file() else FIXTURE_ROOT.parent.parent.parent / path


def provider_list(fixture):
    names = list(fixture["rows"][0]["providers"])
    primary = fixture.get("primary_provider", names[0])
    return [primary] + [p for p in names if p != primary]


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
            variants.append(
                {
                    "name": name,
                    "gating": True,
                    "tier": "nightly",
                    "subprocess": True,
                    "process": process,
                    "notes": f"MadLoop SubProcesses/{vf['mqcd_run']['subprocess']} of p p > t t~",
                    "reference": {
                        "format": "required",
                        "path": f"tests/fixtures/loop/{x['fixture']}",
                        "providers": provider_list(vf),
                    },
                    "points": {"nightly": list(range(len(vf["points"])))},
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
                    **VARIANT_LISTINGS.get(f"{rid}@{name}", {}),
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
        variants = indexed[2]  # an existing reference keeps it; variants join
        indexed = None
    if indexed and indexed[0] is None:
        indexed = None
    if indexed:
        reference, fixture0, variants = indexed
        if r["id"] in REFUSED_5F:
            r["waits"] = "MQ-5F"
        elif r["id"] == "M01":
            r["waits"] = "MQ-MODEL"
        else:
            r["waits"] = None
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
        "binary64_out_of_scope": [],
        "reference_outliers": [],
        "vanishing": [],
    }
    if params:
        entry["parameters"] = params
    if r["id"] in SECTORS:
        entry["predicted_sectors"], entry["unpredicted_sectors"] = SECTORS[r["id"]]
    entry.update(LISTINGS.get(r["id"], {}))
    if indexed or r["id"] in ("D21",):
        entry.update(LISTINGS_INDEXED.get(r["id"], {}))
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
    if variants:
        entry["variants"] = variants
    if r["id"] == "B01":
        # MQ-REF's per-helicity run of B01's points
        entry["helicity_reference"] = (
            "tests/fixtures/loop/required/mqcd/gg_ttx_sectors.json"
        )
    if r["id"] in CKM_RELATIONS:
        entry["ckm_relation"] = CKM_RELATIONS[r["id"]]
    if r["id"] in WARD_LEGS:
        entry["ward_legs"] = WARD_LEGS[r["id"]]
    if r["id"] in WARD_OUT_OF_SCOPE:
        entry["ward_out_of_scope"] = WARD_OUT_OF_SCOPE[r["id"]]
    if r["id"] in NATIVE_ROWS:
        entry["inputs"] = "native"
        entry["catani"] = "none"
        entry["points"] = {"nightly": NATIVE_ROWS[r["id"]]}
    if status == "pending" and r["id"] in REFUSED_5F and indexed:
        entry["pending"]["reason"] = (
            "the reference exists (MQ-REF); the tools route refuses the request at generation: a Dirac (massive) current cannot close on a Weyl current (the MQ-5F class)"
        )
    if r["id"] == "M01" and indexed:
        entry["reference"] = None
        entry["pending"] = {
            "waits_for": "MQ-MODEL",
            "reason": "the public route's multiparticle artifact (each subprocess = its single-process generation, bitwise) waits for the public route on loop_sm; the expansion against MadLoop's P directories and every P reference (variants M01@P0, M01@P2) run now",
        }
        entry["madloop_subprocesses"] = MADLOOP_SUBPROCESSES
    pend = {}
    for e in r["extras"]:
        if e == "nc":
            pend[e] = (
                "MQ-NC (shipped N_c declaration and its independent oracles; rule 7)"
            )
        elif e == "hel" and r["id"] not in ("A08", "B01", "D05"):
            pend[e] = "MQ-REF (per-helicity SLOOPMATRIXHEL references)"
        elif e == "sp" and not any(v.get("gating", True) for v in variants):
            pend[e] = "MQ-REF (supplied special points S1-S4)"
    if pend:
        entry["extras_pending"] = pend
    rows.append(entry)

# The nightly tier's file jobs (PLAN §3.2 acceptance: each nightly file job
# <= 30 min). Seconds per nightly test id as measured by the campaign run of
# 2026-10-28 (tmp/mq-validate/pt3: one process per id on the shared host at
# load ~100, start-up and model compilation included; A24 1556 s on four
# pinned cores, s2);
# a row without a measurement counts DEFAULT_SECONDS. A row and its variants
# (which reuse its generation) form one group; groups are packed greedily,
# largest first, into jobs of at most JOB_SECONDS (a group above it is a job
# of its own); job 1 also holds the restriction smokes and the M01
# expansion (SMOKE_SECONDS).
MEASURED_SECONDS = {
    "A01": 31, "A02": 28, "A03": 33, "A04": 23, "A05": 36, "A06": 26, "A07": 31,
    "A08": 445, "A09": 40, "A09@collinear": 33, "A09@soft": 41, "A12": 20,
    "A13": 47, "A14": 182, "A15": 68, "A18": 145, "A19": 44, "A20": 42,
    "A21": 55, "A22": 182, "A23": 731, "A24": 1556, "A25": 31, "A26": 31,
    "B01": 37, "B01@mt170": 32, "B01@threshold": 27, "B02": 27, "B03": 71,
    "B05": 795, "B06": 52, "B07": 349, "B08": 34, "C01": 33, "C01@params": 33,
    "C02": 50, "C03": 28, "C04": 31, "C05": 48, "C06": 295, "C07": 35, "C08": 36,
    "D01": 26, "D02": 29, "D05": 39, "D06": 36, "D07": 112, "D08": 53, "D09": 26,
    "D10": 34, "D11": 34, "D12": 31, "D13": 34, "D15": 30, "D16": 31, "D17": 31,
    "D18": 29, "D19": 31, "D20": 36, "D21": 25, "D23": 33, "D24": 29, "D25": 31,
    "D25@zero": 23, "D26": 35, "D27": 33, "E01": 55, "E02": 51, "E05": 27,
    "E06": 181, "F01": 42, "F02": 30, "F04": 31, "G01": 29, "G02": 35, "H01": 37,
    "M01@P0": 31, "M01@P2": 34, "R01": 29,
}  # fmt: skip
DEFAULT_SECONDS = 60
JOB_SECONDS = 1200
SMOKE_SECONDS = 75


def nightly_groups(rows):
    """(seconds, [ids]) per row with nightly test ids: the row (if it has
    nightly points or checked extras) and its gating variants."""

    checked = {"ap", "uv", "hel", "sp"}
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
            if v.get("gating", True) and v["points"].get("nightly")
        ]
        if ids:
            seconds = sum(MEASURED_SECONDS.get(i, DEFAULT_SECONDS) for i in ids)
            groups.append((seconds, ids))
    return groups


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
        "lc_every_restriction": "MQ-NC",
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
