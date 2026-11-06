#!/usr/bin/env python3
# SPDX-License-Identifier: 0BSD
"""Write ``li_campaign.json``: the loop-induced validation matrix (M-LIT PLAN §4).

The rows are PLAN §4.1's (ids, processes, references, rules, backends, tier);
each process of a row points at its reference run (a ``"loop_induced": true``
process of ``required_processes.json``, run by ``run_li.sh`` /
``li_references.py``) and the committed fixture
``tests/fixtures/loop/required/li/<process>.json`` when it exists, with the
fixture's providers, worst provider-pair deviation and the 45-minute misses;
a process without a run names the package that owns it. Provider timings of
the gated rows are the ``tools/loop_benchmark providers`` records under
``tests/fixtures/loop/required/li/timing/``.

    python tools/loop_reference/make_li_campaign.py [--output tools/loop_reference/li_campaign.json]
"""

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
FIXTURES = REPOSITORY / "tests" / "fixtures" / "loop" / "required" / "li"
TIMING = FIXTURES / "timing"

RULES = {
    "L1": "provider: binary64 |A|^2 vs MadLoop (QP-checked, target 1e-11) / Recola / OpenLoops <= 1e-5 relative",
    "L2": "analytic: DD/AP vs the mpmath oracle <= 1e-12 relative (binary64 <= 1e-9 at stable points)",
    "L3": "finiteness: combined poles per (loop, helicity) <= 10 E against the pre-reduction term floor (DECISIONS 2026-11-06 ~09:00 (1))",
    "L4": "Ward: per (loop, helicity) at zero widths (complex masses kept under CMS) <= 10 E",
    "L5": "rotation: ADDENDUM C rotations <= 10 E",
    "L6": "backend: NinjaRS vs TIRust |A|^2 <= 10 max(E_N, E_T) binary64; DD/AP within 1e-24",
    "L7": "carrier: DD vs AP <= 1e-24",
    "L8": "zeros: numerical by default (Q13): |A|^2 <= 10 E_abs in binary64 and DD; exact 0 only for vanishing colour coefficients",
    "L9": "limits: HEFT / LET / crossing / symmetry identities as stated per row",
    "N0": "non-regression of the Born-interfered plans and outputs",
}

# PLAN §4.1: (id, description, processes (reference run keys or None), references, checks, backends, tier, owner).
ROWS = [
    ("LI-B1", "every Born-interfered campaign row (G1, M-QCD, M-SM, decays, HC)", None,
     "NinjaRS in-tree + the stored Born-interfered ML/RC fixtures", ["L6"], "N vs T", "backend", "lit-tir"),
    ("LI-B2", "single-monomial tensor coefficients N = 1..6, R <= N+2", None,
     "COLLIER 1.2.8 TNten_cll (MadLoop mapping), NinjaRS, AP", ["basis", "sign", "normalisation", "poles"], "T",
     "backend", "lit-tir"),
    ("LI-A1", "g g > h (t; t + b at m_b = 4.7)", ["li_gg_h", "li_gg_h_tb"],
     "AN (Spira) = the gate; HEFT ratio reported; ML, OL pphj2, RC", ["L1", "L2", "L3", "L4", "L5"], "N, T",
     "analytic", None),
    ("LI-A2", "h > g g", ["li_h_gg"], "AN (crossing of A1); ML, RC", ["L1", "L2", "L3", "L4", "L5"], "N, T", "analytic",
     None),
    ("LI-A3", "h > a a [QED]", ["li_h_aa"], "AN (Djouadi); ML, RC", ["L1", "L2", "L3", "L4", "L5"], "N, T", "analytic",
     None),
    ("LI-A4", "h > z a [QED]; e+ e- > h a [QED]", ["li_h_za", "li_emep_ha"],
     "AN (Djouadi/Spira I1, I2) for h > z a; ML, RC", ["L1", "L2", "L3", "L4", "L5"], "N, T", "analytic", None),
    ("LI-A5", "g g > a a (5 massless + top; massless separately)", ["li_gg_aa", "li_gg_aa_nf5"],
     "AN (GPR / Glover-van der Bij massive box + Bern et al. massless box); ML, OL ppvv2, RC (RC not for nf5)",
     ["L3", "L1", "L2"], "N, T", "analytic", None),
    ("LI-A6", "a a > a a [QED], complete (fermion + W/G/ghost loops)", ["li_aa_aa"],
     "AN (Karplus-Neuman/Glover-van der Bij + Jikia-Tkabladze via GPR); RC (mandatory), ML", ["L1", "L2"], "N, T",
     "analytic", "lit-ew"),
    ("LI-A7", "large m_t: g g > h g, u u~ > h g, g g > h g g vs HEFT trees; g g > h h vs the LET",
     ["li_gg_hh"], "built-in-sm-heft trees (pyAmpliCol); LET (li_analytic gg_hh_let, a limit only)", ["L9"], "N, T",
     "analytic", "lit-val"),
    ("LI-Z1", "exact colour zeros h > g a, z > g a", None,
     "exact 0 (MG5 generates no diagram: NoDiagramException)", ["L8"], "N, T", "zeros", None),
    ("LI-Z1b", "numerical Furry zeros g g > a a a, g g > h a", ["li_gg_ha", "li_gg_aaa"],
     "zero within estimate (provider values recorded); g g > a a a: Recola only (MG5 removes Furry loops by rule)",
     ["L8"], "N, T", "zeros", None),
    ("LI-Z2", "integrated zeros g g > z, z > g g, e+ e- > g g", ["li_gg_z", "li_z_gg", "li_emep_gg"],
     "zero within estimate (provider values recorded)", ["L8"], "N, T", "zeros", None),
    ("LI-W1/L1/P1/C1/S1", "Ward, rotations/boosts, amplitude poles, crossing, N_f multiplicity", None,
     "identities (pyAmpliCol)", ["L3", "L4", "L5", "L9"], "N, T", "identities", "lit-val"),
    ("LI-21", "g g > z z", ["li_gg_zz"], "ML, OL ppvv2 zzgg, RC", ["L1"], "N, T", "2->2", None),
    ("LI-22", "g g > w+ w-", ["li_gg_wpwm"], "ML, OL ppvv2 wwxgg, RC", ["L1"], "N, T", "2->2", None),
    ("LI-23", "g g > z a", ["li_gg_za"], "ML, OL ppvv2 azgg, RC", ["L1"], "N, T", "2->2", None),
    ("LI-24", "g g > h h", ["li_gg_hh"], "ML, OL pphh2 hhgg, RC; LET", ["L1", "L9"], "N, T", "2->2", None),
    ("LI-25", "g g > h z", ["li_gg_hz"], "ML, OL pphz2 hzgg, RC", ["L1"], "N, T", "2->2", None),
    ("LI-26", "g g > h g, u u~ > h g, u g > h u", ["li_gg_hg", "li_uux_hg", "li_ug_hu"],
     "ML, OL pphj2 hggg / uuxhg (u g > h u by crossing), RC", ["L1"], "N, T", "2->2", None),
    ("LI-27", "g g > z g, g g > a g", ["li_gg_zg", "li_gg_ag"], "ML, OL ppvj2 zggg / aggg, RC", ["L1"], "N, T",
     "2->2", None),
    ("LI-E1", "h > a a, h > z a (= LI-A3/A4)", ["li_h_aa", "li_h_za"], "= LI-A3/A4", ["L1", "L2"], "N, T", "EW",
     "lit-ew"),
    ("LI-E2", "a a > a a (= LI-A6), a a > h, a a > z z, a a > h h", ["li_aa_aa", "li_aa_h", "li_aa_zz", "li_aa_hh"],
     "ML, RC (RC mandatory); AN for a a > h (crossing of LI-A3)", ["L1"], "N, T", "EW", "lit-ew"),
    ("LI-E3", "e+ e- > h a, e+ e- > h h [QED]", ["li_emep_ha", "li_emep_hh"],
     "ML, RC (RC mandatory for e+ e- > h h)", ["L1"], "N, T", "EW", "lit-ew"),
    ("LI-E4", "e+ e- > g g g [QED]", ["li_emep_ggg"], "ML, RC (no OpenLoops ls library)", ["L1"], "N, T",
     "2->3 gate", None),
    ("LI-31", "g g > h h h", ["li_gg_hhh"], "ML, OL pphhh2, RC; supplied points", ["L1"], "N, T", "2->3 gate", None),
    ("LI-32", "g g > h g g", ["li_gg_hgg"], "ML, OL pphjj2 hgggg, RC", ["L1"], "N, T", "2->3 gate", None),
    ("LI-33", "g g > z z g, g g > a a g, g g > w+ w- g", ["li_gg_zzg", "li_gg_aag", "li_gg_wpwmg"],
     "ML, OL ppvvj2 (zzggg, aaggg, wwxggg), RC", ["L1"], "N, T", "2->3 gate", None),
    ("LI-34", "g g > z z z", ["li_gg_zzz"], "ML, OL ppvvv2, RC; supplied points", ["L1"], "N, T", "2->3 gate", None),
    ("LI-35", "g g > h z g, g g > a g g, g g > z g g", ["li_gg_hzg", "li_gg_agg", "li_gg_zgg"],
     "ML, OL pphzj2 hzggg / ppajj2 agggg (added library), RC; g g > z g g: ML, RC (no OpenLoops ls library)",
     ["L1"], "N, T", "2->3 gate", None),
    ("LI-36", "u u~ > h g g, u u~ > d d~ h (QED <= 1)", ["li_uux_hgg", "li_uux_ddxh"],
     "ML, OL pphjj2 uuxhgg / uuxddxh, RC (mandatory for u u~ > d d~ h)", ["L1"], "N, T", "2->3 gate", None),
    ("LI-37", "h > g g g, z > g g g", ["li_h_ggg", "li_z_ggg"], "ML, RC", ["L1"], "N, T", "1->3", None),
    ("LI-41", "g g > h h g g", ["li_gg_hhgg"],
     "ML, OL pphhjj2 hhgggg, RC; the P15 point 1.3033633142042775e-12 GeV^-4 is lit-val's", ["L1"], "N, T",
     "2->4 gate", None),
    ("LI-42", "g g > h g g g", ["li_gg_hggg"], "ML, OL pphjjj2 hggggg, RC", ["L1"], "N, T", "2->4 gate", None),
    ("LI-43", "g g > e+ e- mu+ mu-", ["li_gg_emepmupmum"],
     "ML, OL ppllll2 (fixed widths; Recola's width convention differs: excluded, deviation recorded)", ["L1"],
     "N, T", "2->4 gate", None),
    ("LI-44", "g g > a a g g, g g > z z z z", ["li_gg_aagg", "li_gg_zzzz"],
     "ML, OL ppaajj2 aagggg (added library), RC; g g > z z z z: ML, RC (no OpenLoops ls library)", ["L1"], "N, T",
     "2->4 optional", None),
    ("LI-51", "g g > e+ e- mu+ mu- g (2->5 stretch)", ["li_gg_emepmupmumg"],
     "ML, OL ppllllj2 (added library), RC", ["L1"], "N, T", "2->5 stretch", None),
    ("LI-X1", "one EFT row with rank > N+2", None,
     "ML (TIR); NOT PRODUCED (lit-ref-b): HC_NLO_X0 declares QNP expansion_order = 1, so an amplitude carries one "
     "x0 vertex and its loops reach rank N+1 at most (the heft g g > x0 g export: MAXRANK 5 at N = 4); MG5 caps "
     "g g > x0 x0 x0 QNP=3 at QNP=1 and generates no diagram; by power counting a single dimension-6 (SMEFT) insertion "
     "also stays at rank <= N+1 in Feynman gauge: the row needs a ruling (a model with a higher declared expansion "
     "order, or another row)",
     ["L1"], "T", "EFT", "lit-eft"),
    ("LI-O1", "correlated, colour-resolved and single-helicity outputs", None,
     "RC loop-induced colour correlations; identities", ["sum_h"], "N, T", "observables", "lit-obs"),
    ("LI-C1", "complex-mass scheme rows (Q7)",
     ["li_gg_aa_cms", "li_aa_aa_cms", "li_gg_zz_cms", "li_gg_aag_cms", "li_emep_ggg_cms", "li_gg_emepmupmum_cms"],
     "RC, ML, OL where designated; AN with complex masses (g g > a a, a a > a a)", ["L1", "L2"], "N, T", "EW",
     "lit-ew"),
]


def fixture_summary(process):
    path = FIXTURES / f"{process}.json"
    if not path.exists():
        return {"process": process, "status": "no reference yet"}
    data = json.loads(path.read_text())
    out = {"process": process, "fixture": f"required/li/{process}.json", "madloop_process": data["madloop_process"],
           "scheme": data["scheme"], "providers": sorted(data["providers"]), "points": len(data["points"]),
           "max_provider_pair_relative_error": data["max_provider_pair_relative_error"],
           "status": "zero row" if data.get("zero_row") else "pass" if data["passed"] else
           "single provider" if len(data["providers"]) < 2 else "FAIL"}
    for key in ("excluded", "unavailable", "misses_45_min"):
        if data.get(key):
            out[key] = {k: (v["reason"] if isinstance(v, dict) else v) for k, v in data[key].items()}
    reports = data["providers"].get("analytic", {}).get("reports")
    if reports:
        out["reports"] = {k: {"value": v[0], "expected": v[1]} for k, v in reports.items()}
    if any("limit_oracle" in row for row in data["rows"]):
        out["limit_oracle_ratios"] = [row["limit_oracle"]["ratio_to_reference"] for row in data["rows"]]
    timing = sorted(p.name for p in TIMING.glob(f"{process}-providers*.json"))
    if timing:
        out["provider_timing_records"] = [f"required/li/timing/{name}" for name in timing]
        out["provider_ms_per_point"] = timing_summary(process)
    return out


def timing_summary(process):
    """Mean ms per point of each timed provider (16 stream points, one pinned
    core): MadLoop 7|6|1 (production card), its 6|7|1 OPP column, its
    one-helicity column (mean per kept-helicity call), OpenLoops, Recola."""
    out = {}
    main = TIMING / f"{process}-providers.json"
    records = [main] if main.exists() else []
    records += [TIMING / f"{process}-providers-madloop-{tag}.json" for tag in ("opp", "one-helicity")]
    for path in records:
        if not path.exists():
            continue
        tag = path.name[len(f"{process}-providers"):-len(".json")].lstrip("-")
        for provider, entry in json.loads(path.read_text())["providers"].items():
            if "mean_seconds_per_point" not in entry:
                continue
            if tag == "madloop-opp":
                out["madloop_6|7|1"] = round(entry["mean_seconds_per_point"] * 1e3, 4)
                continue
            if tag == "":
                out[provider] = round(entry["mean_seconds_per_point"] * 1e3, 4)
            if provider == "madloop" and "one_helicity" in entry:
                out["madloop_one_helicity"] = round(entry["one_helicity"]["mean_seconds_per_call"] * 1e3, 4)
    return out


def build():
    rows = []
    for row_id, text, processes, references, checks, backends, tier, owner in ROWS:
        entry = {"row": row_id, "processes": text, "references": references, "checks": checks, "backends": backends,
                 "tier": tier, "gated": "gate" in tier}
        if owner:
            entry["owner"] = owner
        entry["runs"] = [fixture_summary(p) for p in processes or ()]
        rows.append(entry)
    return {
        "description": ("M-LIT loop-induced validation matrix (workspace/reports/engine-v2/m-lit/PLAN.md §4): the rows "
                        "of §4.1 with their reference runs (tools/loop_reference/run_li.sh, li_references.py; work "
                        "directories $LOOP_REFERENCE_ROOT/runs/li/<process>/) and the committed fixtures "
                        "tests/fixtures/loop/required/li/<process>.json (paths below tests/fixtures/loop/). Written by "
                        "make_li_campaign.py."),
        "rules": RULES,
        "madloop_settings": {
            "reference": "standalone [sqrvirt=...] export at MG5's production Fortran flags; target accuracy 1e-11 "
                         "(stability test forced on every call, QP rescue through CutTools/Ninja), "
                         "HelicityFilterLevel = 0, every helicity (SLOOPMATRIXHEL_THRES, USERHEL reset after the rows), "
                         "warm-up >= CheckCycle + 1 calls",
            "timing": "the export's own card (MLReductionLib 7|6|1, COLLIER UV/IR poles off, HelicityFilterLevel 2, "
                      "MLStabThres); a 6|7|1 (OPP) column; tools/loop_benchmark providers --madloop-stages",
            "single_helicity": "|A(h)|^2/avg (Q39) = MadLoop's USERHEL value / HELAVGFACTOR",
        },
        "conventions": "|A_loop|^2 summed over final and averaged over initial helicities and colours, with the final "
                       "identical-particle factor; physical couplings; widths zero outside the complex-mass rows",
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, default=HERE / "li_campaign.json")
    args = parser.parse_args()
    args.output.write_text(json.dumps(build(), indent=1) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
