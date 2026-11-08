# SPDX-License-Identifier: 0BSD
"""Write data/summary.json, the data of Table 1 of the live loop report, and
data/summary-li.json, the data of the loop-induced summary table
(<tab:summary-li>, build_loop_induced).

Usage: python scripts/build_summary.py [output [output-loop-induced]]

Every value of Table 1 (times, memory, sizes, ratios, gate verdicts, stage
shares, validation figures) is assembled here from the report's data files,
and every entry names its source:

- data/g1.json            gate-G1 campaign (python -m tools.loop_benchmark gate)
- data/msm-g1.json        the electroweak G1 rows (the same gate tool on the EW
                          records), part of g1.json's integrated configuration
                          when both timed the same engine; gated since the
                          final G1 retime (M-LIT-a0; indicative at M-SM,
                          m-sm/PLAN.md [U5]), their leading-colour status from
                          milestone.json status_notes (_with_ew_rows,
                          _ew_cells)
- data/measured.json      development run records (scripts/collect_milestone.py):
                          the WP3.1 native validations of the required set and
                          the provider reference runs' records (generation,
                          MadLoop's production-build times, Recola's protocol
                          run)
- data/milestone.json     hand-maintained registry: the required set, the
                          OpenLoops and Recola production references of the
                          seven-leg rows (DESIGN 1.3 Table 1b, as text: the
                          gate limit is computed here), the branch of the
                          development revisions, user gate decisions (and
                          the user's 5 ms gate rule), short status notes and
                          notes on single measured cells (cell_notes: a
                          known limitation of a value, or its run
                          conditions)
- tools/loop_benchmark/processes.json  the G1 process specifications
- data/2to6.json          the 2 -> 6 rows (scripts/build_2to6.py, from the
                          mf-2to6 run records): summary.json "preliminary",
                          outside the main-configuration rule (their own
                          engine, pyAmpliCol only: no provider, no gate,
                          uncoloured) (_preliminary)

The loop-induced summary table (data/summary-li.json, build_loop_induced;
m-lit/PLAN.md §3.7 "Pushes") reads, each absent file read as "pending":

- data/milestone.json loop_induced  its row registry (every process row of
                          m-lit/PLAN.md §4.1 by multiplicity group, gate
                          class, serving package), checked against lit-ref's
                          manifest tools/loop_reference/li_campaign.json
                          once that exists
- data/li-timing.json     pyAmpliCol's loop-induced timing and generation
                          records (§5.1 protocol; lit-perf's gate tool
                          records from that package on)
- lit-ref's provider timings: the provider timing records of the manifest's
                          reference runs (tests/fixtures/loop/required/li/
                          timing/; MadLoop loop-induced production 7|6|1,
                          OpenLoops ls, Recola)
- data/lit.json           lit-val's validation figures

and its "figure" holds Figure 1's loop-induced rows (li_figure: the rows of
the table with a pyAmpliCol time and a matched provider time, drawn as
diamonds beside Table 1's).

Main-configuration rule (MAIN_RULE below): every cell of Table 1 and Figure
1 shows the most recent configuration that measured it, recency by git
ancestry of the configurations' revisions (and a G1 campaign's own roles),
and summary.json records that configuration, its source and the recency
facts with the cell. A validation that only repeats part of an older,
more complete comparison does not replace it (VALIDATION_RULE). The
ancestry is recorded in milestone.json and checked against git wherever the
revisions are present, so the builder runs in any checkout of the report.

Nothing is estimated or extrapolated: a value without a record stays absent
(null) and Table 1 prints an explicit marker. The report renders summary.json
as is; re-run this script after regenerating any input.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
DATA = HERE / "data"
REPO = HERE.parents[2]

PROVIDERS = ("madloop", "recola", "openloops")
NAMES = {"madloop": "MadLoop", "recola": "Recola", "openloops": "OpenLoops"}
SHORT = {
    "madloop": "ML",
    "recola": "Rc",
    "openloops": "OL",
    "njet_dd_oneloop_R1": "NJet DD",
}
# References shown in Table 1 (NJet: its double-double values; the record's
# binary64 NJet runs are cross-checks and stay in measured.json).
SHOWN = set(SHORT)
# A worst deviation that pyAmpliCol's double-double value repeats is the
# reference's own only if another reference agrees with that double-double
# value at least this many times better (_validation_g1).
REFERENCE_OWN_MARGIN = 100
# When several configurations of one side qualify, the engine's production
# per-point inputs come first.
INPUTS_PREFERENCE = ("native", "python")

# Main-configuration rule (user request of 2026-10-24: Table 1 shows only the
# most recent measurements; binding for every report update, slice-status
# DECISIONS ~18:35). Every cell of a row (generation, validation, full
# colour, leading colour) shows the MOST RECENT configuration that measured
# it. The candidates of a row (KIND_ORDER):
#   development          a G1 campaign's development side (gate --meta
#                        native_revision, native_commit): work ahead of loop,
#                        being integrated into it; its revision is
#                        native_revision (the engine; native_commit may only
#                        add timers in a scratch commit);
#   integrated           the campaign's integrated side (--meta
#                        slice_revision, slice_lc_revision): the engine on
#                        loop, revision slice_revision;
#   development_records  the development branch's native validation record
#                        of the process (measured.json required_native, with
#                        the revision of the DESIGN increment that reports
#                        it): generation and validation, no batched timing
#                        (a row G1 has not timed waits for it, "pending");
#   registry             milestone.json status_notes: a refusal attributed
#                        to loop, a capability in development that no
#                        configuration generates yet, or one nobody has
#                        started (no run, so always the last candidate).
# Recency (class Recency): A is newer than B if B's revision is an ancestor
# of A's (git merge-base --is-ancestor, recorded in milestone.json ancestry
# and checked against git where the revisions are present), or if A and B
# are the development and integrated sides of one G1 campaign (the campaign
# declares its development side ahead of loop), and transitively. Equal
# revisions keep KIND_ORDER (the G1 campaign first); two candidates that no
# basis orders, or that the bases order both ways, stop the build: the order
# is never guessed. A cell takes the newest candidate that measured it; if
# none did, the status of the newest candidate with a record of the row
# (refused, not timed, not batched, no gate batch, pending, in development,
# not started), so "refused"
# appears only where the most recent configuration refuses.
# The validation cell has one more condition (VALIDATION_RULE): a newer
# comparison that is less complete than an older one (fewer points, or
# fewer references) and finds no larger deviation only repeats part of it,
# so the older, more complete comparison stays in the cell and the repeat is
# recorded with it (partial_repeats). A check that omits a point cannot
# improve the cell this way; one that finds a larger deviation replaces it.
# Since the G-int milestone (G1 re-measured on loop at 4e9b5a9e, without a
# development side) loop's revision descends from every development record,
# so loop's configuration supplies every cell of the G1 rows, generation
# included; the 2 -> 5 rows keep the development records (measured on
# work/v2-generation-scale before its integration) until G1 times them.
KIND_ORDER = ("development", "integrated", "development_records", "registry")
MAIN_RULE = (
    "every cell shows the most recent configuration that measured it; A is"
    " newer than B if B's revision is an ancestor of A's (git merge-base"
    " --is-ancestor, recorded in milestone.json ancestry) or if A is the"
    " development side and B the integrated side of one G1 campaign,"
    " transitively; equal revisions keep the order development, integrated,"
    " development_records; the registry (no run) comes last; without a"
    " measurement, the status of the newest configuration with a record of"
    " the row"
)
VALIDATION_RULE = (
    "a newer comparison with fewer points or fewer references than an older"
    " one and no larger deviation repeats part of it: the older, more"
    " complete comparison stays in the cell and the repeat is listed in"
    " partial_repeats; a newer comparison with a larger deviation, or at"
    " least as many points and every reference, replaces it"
)
# Generation multipliers (GENERATION_RULE) pair pyAmpliCol's and the
# providers' generation timed under the same kind of conditions: in a G1 row
# the campaign's provider generation (idle pinned cores) with a G1 side; a
# newer development record of such a row (shared host under load) is shown
# without a multiplier, the providers' G1 values listed beside it. In the
# rows without a G1 record, the development record pairs with the providers'
# reference runs (measured.json provider_generation): both are run records on
# this shared host outside the G1 protocol.
GENERATION_RULE = (
    "a generation multiplier pairs values timed under the same kind of"
    " conditions: in a G1 row the campaign's provider generation with a G1"
    " configuration; a newer development record there (shared host under"
    " load) has no multiplier; in the other rows the development record"
    " with the providers' reference runs, both run records on this shared"
    " host outside the G1 protocol"
)
GENERATION_BASIS = {
    "g1": "G1 campaign on both sides (pinned cores of the G1 protocol)",
    "unmatched": "no multiplier: a development record on the shared host"
    " under load against the providers' G1 generation on idle pinned cores"
    " (GENERATION_RULE)",
    "records": "the development record and the providers' reference runs,"
    " both run records on this shared host outside the G1 protocol",
}
ROLE_BASIS = (
    "G1 campaign roles: the development side (gate --meta native_revision)"
    " is ahead of the integrated side (slice_revision)"
)


def _base(cid: str) -> str:
    """The configuration of a candidate id ("development_records@0ea83af2",
    an older record of the development records, is "development_records")."""
    return cid.split("@")[0]


class Recency:
    """Orders the candidate configurations of a row, newest first (the
    main-configuration rule), and keeps every fact it used for
    summary.json meta.main_rule.recency.

    The ancestry of the data's revisions is recorded in milestone.json
    ancestry (git merge-base --is-ancestor, as data), so summary.json
    rebuilds identically in a checkout without the development revisions
    (a clone of loop before the development work is integrated). Every
    fact used is checked against git wherever both revisions are present;
    a contradiction, or a revision the registry does not list, stops the
    build (the order is never guessed)."""

    def __init__(self, repo: Path, ancestry: dict) -> None:
        self.repo = repo
        self._listed = set(ancestry["revisions"])
        self._recorded = {tuple(pair) for pair in ancestry["ancestors"]}
        self._ancestor: dict[tuple[str, str], bool] = {}
        self._facts: dict[tuple[str, str], dict] = {}
        self.checked = 0

    def _git(self, old: str, new: str) -> bool | None:
        """git's answer, None where this checkout lacks a revision."""
        run = subprocess.run(
            ["git", "-C", str(self.repo), "merge-base", "--is-ancestor", old, new],
            capture_output=True,
            text=True,
            check=False,
        )
        return {0: True, 1: False}.get(run.returncode)

    def _is_ancestor(self, old: str, new: str) -> bool:
        key = (old, new)
        if key not in self._ancestor:
            missing = sorted({old, new} - self._listed)
            git = self._git(old, new)
            if missing:
                raise ValueError(
                    f"revisions {missing} are not in milestone.json"
                    " ancestry.revisions: add them with their ancestry facts"
                    f" (git merge-base --is-ancestor {old} {new}: "
                    f"{'not available here' if git is None else git})"
                )
            recorded = key in self._recorded
            if git is not None:
                self.checked += 1
                if git != recorded:
                    raise ValueError(
                        f"milestone.json ancestry says {old} is"
                        f"{'' if recorded else ' not'} an ancestor of {new};"
                        " git says the opposite"
                    )
            self._ancestor[key] = recorded
        return self._ancestor[key]

    def _fact(self, newer: str, older: str, basis: str) -> None:
        fact = {"newer": newer, "older": older, "basis": basis}
        self._facts.setdefault((newer, older), fact)

    def order(self, cands: list[tuple[str, str]]) -> list[str]:
        """The configurations of (configuration, revision) pairs, newest
        first."""
        rev = dict(cands)
        ids = [c for c, _ in cands]
        # An older record of a configuration is "<configuration>@<revision>".
        label = {c: f"{_base(c)} {r}" for c, r in cands}
        newer: set[tuple[str, str]] = set()
        if "development" in rev and "integrated" in rev:
            newer.add(("development", "integrated"))
            self._fact(label["development"], label["integrated"], ROLE_BASIS)
        for a in ids:
            for b in ids:
                if a != b and rev[a] != rev[b] and self._is_ancestor(rev[b], rev[a]):
                    newer.add((a, b))
                    self._fact(
                        label[a],
                        label[b],
                        f"git merge-base --is-ancestor {rev[b]} {rev[a]}"
                        " (milestone.json ancestry)",
                    )
        while True:
            extra = {(a, d) for a, b in newer for c, d in newer if b == c} - newer
            if not extra:
                break
            newer |= extra
        for a, b in newer:
            if (b, a) in newer:
                raise ValueError(f"recency of {label[a]} and {label[b]}: both ways")
        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                if rev[a] != rev[b] and (a, b) not in newer and (b, a) not in newer:
                    raise ValueError(
                        f"no recency basis orders {label[a]} and {label[b]}:"
                        " neither revision contains the other"
                    )
        rank = {a: sum((a, b) in newer for b in ids) for a in ids}
        return sorted(ids, key=lambda a: (-rank[a], KIND_ORDER.index(_base(a))))

    def newest_first(self, revisions: list[str]) -> list[str]:
        """Distinct revisions on one line of history, newest first."""
        out = sorted(set(revisions))
        for i, a in enumerate(out):
            for b in out[i + 1 :]:
                if not (self._is_ancestor(a, b) or self._is_ancestor(b, a)):
                    raise ValueError(f"revisions {a} and {b} are not on one line")
        rank = {a: sum(self._is_ancestor(b, a) for b in out if b != a) for a in out}
        return sorted(out, key=lambda a: -rank[a])

    def facts(self) -> list[dict]:
        return [self._facts[k] for k in sorted(self._facts)]


# Stage groups of the per-point split (the executor's stage names; see the
# report's stage-split table for their definitions).
STAGE_GROUPS = {
    "inputs": (
        "python trees",
        "python counterterm program",
        "python scalars",
        "python Born and counterterm components",
        "native trees",
    ),
    "numerator": ("seeds", "factors", "dressing"),
    "scatter": ("scatter",),
    "masters": ("reduction: masters",),
    "glue": ("python point parameters", "input conversion", "assembly", "other"),
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _math(text: str) -> str:
    """'u u~ > e- e+ g' -> Typst math 'u overline(u) -> e^- e^+ g'."""
    out = []
    for t in text.split():
        if t == ">":
            out.append("->")
        elif t.endswith("~"):
            out.append(f"overline({t[:-1]})")
        elif t.endswith(("-", "+")) and len(t) > 1:
            out.append(f"{t[:-1]}^{t[-1]}")
        else:
            out.append(t)
    return " ".join(out)


def _text(math: str) -> str:
    """Inverse of _math for the registry's labels."""
    out = []
    for t in math.split():
        if t == "->":
            out.append(">")
        elif t.startswith("overline("):
            out.append(t[len("overline(") : -1] + "~")
        elif "^" in t:
            out.append(t.replace("^", ""))
        else:
            out.append(t)
    return " ".join(out)


def _key(text: str, corr: str | None = None) -> str:
    """'u u~ > e- e+ d d~ g' -> 'uux_emepddxg' (the campaign's process keys)."""
    names = {"e-": "em", "e+": "ep"}
    initial, final = text.split(" > ")
    part = lambda s: "".join(names.get(t, t.replace("~", "x")) for t in s.split())  # noqa: E731
    key = f"{part(initial)}_{part(final)}"
    return f"{key}_{corr.lower()}" if corr else key


def _stage(stages: dict, names: tuple[str, ...]) -> float:
    return sum(stages.get(n, 0.0) for n in names)


def _split(stages: dict) -> dict:
    out = {g: _stage(stages, names) for g, names in STAGE_GROUPS.items()}
    out["ninjars"] = stages.get("reduction", 0.0) - stages.get(
        "reduction: masters", 0.0
    )
    # A record without any per-point input timer (the build on loop before
    # lc-perf, 88657260: the native trees timer was a scratch commit of the
    # development campaign; since lc-perf the executor reports "trees")
    # leaves its native trees, Born and counterterm inputs in "other", the
    # untimed rest of the call: shown apart, never attributed to a stage.
    out["untimed"] = 0.0
    if not any(name in stages for name in STAGE_GROUPS["inputs"]):
        out["untimed"] = stages.get("other", 0.0)
        out["glue"] -= out["untimed"]
    order = ("inputs", "numerator", "scatter", "ninjars", "masters", "glue", "untimed")
    return {k: out[k] for k in order}


# The gate batch (user 2026-10-28, slice-status DECISIONS ~08:20 item 2;
# tools/loop_benchmark/gate.py GATE_BATCH, package gate-b128): Table 1's
# batched full-colour and leading-colour cells, their gate verdict and the
# 5 ms floor take B = 128 explicitly, never the largest batch a configuration
# timed. Every other batch size is reported in the gate-G1 details without a
# verdict; a configuration without a B = 128 timing has no batched cell here.
GATE_BATCH = "128"


def _gate_batch(cfg: dict | None) -> str | None:
    if not cfg or not cfg.get("batches"):
        return None
    return GATE_BATCH if GATE_BATCH in cfg["batches"] else None


def _no_gate_batch(cfg: dict) -> str:
    """The status of a configuration without a B = 128 timing: no batched
    run at all, or batches other than the gate batch only."""
    return (
        "not batched" if all(int(b) <= 1 for b in cfg["batches"]) else "no gate batch"
    )


def _provider_runtime(proc: dict) -> dict:
    """The providers' production-mode times of a G1 row and the fastest.

    A matched provider's timing outside the protocol is shown beside the
    cell, never a gate limit. Where it does the production work and more
    (``production_upper_bound``, set by the gate tool's import: u u~ >
    g g g g g, Recola's reference run also evaluates the IR poles) it bounds
    that provider's production time from above, so the fastest provider's
    production time is at most it: below the fastest protocol-mode time it
    becomes the fastest as a bound (``fastest.bound`` "upper"), and the
    ratio to it is a lower bound of the ratio to the fastest provider
    (``_timing_of``). Never extrapolated, never a limit."""
    out = {}
    bounds = []
    for name in PROVIDERS:
        rec = (proc.get("providers") or {}).get(name)
        if rec is None:
            out[name] = {"status": "not run"}
        elif "unavailable" in rec:
            out[name] = {"status": "unavailable", "reason": rec["unavailable"]}
            if "median_seconds_per_point" in rec:
                out[name]["outside_protocol"] = {
                    "seconds_per_point": rec["median_seconds_per_point"],
                    "points": rec["points"],
                    "mode": rec["mode"],
                }
                if "production_upper_bound" in rec:
                    out[name]["outside_protocol"]["production_upper_bound"] = rec[
                        "production_upper_bound"
                    ]
                    bounds.append((name, rec["median_seconds_per_point"]))
        else:
            entry = {
                "status": "measured",
                "seconds_per_point": rec["median_seconds_per_point"],
                "points": rec["points"],
                "mode": rec["mode"],
            }
            if name == "openloops":
                entry["library"] = rec["library"]["name"]
            out[name] = entry
    timed = [
        (n, v["seconds_per_point"]) for n, v in out.items() if "seconds_per_point" in v
    ]
    fastest = min(timed, key=lambda x: x[1]) if timed else None
    best = (
        None
        if fastest is None
        else {
            "name": NAMES[fastest[0]],
            "key": fastest[0],
            "seconds_per_point": fastest[1],
        }
    )
    bound = min(bounds, key=lambda x: x[1]) if bounds else None
    if bound is not None and (fastest is None or bound[1] < fastest[1]):
        best = {
            "name": NAMES[bound[0]],
            "key": bound[0],
            "seconds_per_point": bound[1],
            "bound": "upper",
            "basis": f"{NAMES[bound[0]]}'s timing outside the protocol bounds its"
            " production time from above ("
            + out[bound[0]]["outside_protocol"]["production_upper_bound"]
            + "); the fastest provider's production time is at most it",
            "protocol_fastest": best,
        }
    return {"providers": out, "fastest": best}


def _provider_generation_g1(proc: dict) -> dict:
    """The providers' generation of a G1 row (g1.json): MadLoop's export
    stages, Recola's setup, OpenLoops's prebuilt library. A provider without a
    production-mode timing (``unavailable``) has one where its record still
    holds a run (an imported campaign timing, ``imported_from``: the process
    was generated; only its timing is outside the protocol)."""
    out = {}
    for name in PROVIDERS:
        rec = (proc.get("providers") or {}).get(name)
        if rec is None or ("unavailable" in rec and "imported_from" not in rec):
            out[name] = None
        elif name == "madloop":
            gen = rec.get("generation")
            out[name] = None if gen is None else _madloop_generation(gen)
        elif name == "recola":
            sec = rec.get("setup", {}).get("generation_seconds")
            out[name] = None if sec is None else {"seconds": sec}
        else:
            out[name] = {"prebuilt": rec["library"]["name"]}
    return out


def _reference_generation(pg: dict | None) -> tuple[dict, dict]:
    """The providers' generation in their reference runs (measured.json
    provider_generation.processes[key]) and the runs that did not finish
    (MadLoop's graph generation time and stage, Recola's status)."""
    gens: dict = {n: None for n in PROVIDERS}
    unfinished: dict = {}
    if pg is None:
        return gens, unfinished
    ml, rc = pg["madloop"], pg["recola"]
    if "total_s" in ml:
        gens["madloop"] = _madloop_generation(ml)
    else:
        unfinished["madloop"] = {
            "status": ml["status"],
            "graph_generation_s": ml.get("graph_generation_s"),
        }
    if "generation_s" in rc:
        gens["recola"] = {"seconds": rc["generation_s"]}
    else:
        unfinished["recola"] = {
            "status": rc["status"],
            "since": rc.get("updated"),
        }
    if pg["openloops"] is not None:
        gens["openloops"] = {"prebuilt": pg["openloops"]["library"]}
    return gens, unfinished


def _madloop_generation(gen: dict) -> dict:
    """MadLoop's generation: graph generation, source export, compilation."""
    return {
        "seconds": gen["total_s"],
        "graph_s": gen["graph_generation_s"],
        "export_s": gen["source_export_s"],
        "compile_s": gen["compile_s"],
    }


def _fastest_generation(gens: dict) -> dict | None:
    timed = [(n, v["seconds"]) for n, v in gens.items() if v and "seconds" in v]
    if not timed:
        return None
    name, sec = min(timed, key=lambda x: x[1])
    return {"name": NAMES[name], "key": name, "seconds": sec}


def _generation_of(cfg: dict | None, source: str) -> dict | None:
    """One configuration's generation cell; None without a record."""
    if cfg is None:
        return None
    if cfg.get("generation_error"):
        return {
            "status": "refused",
            "error": cfg["generation_error"].split(":")[0],
            "revision": cfg["revision"][:8],
            "source": source,
        }
    gen = cfg["generation"]
    return {
        "status": "measured",
        "seconds": gen["generate"]["seconds"] + gen["export"]["seconds"],
        "generate_s": gen["generate"]["seconds"],
        "export_s": gen["export"]["seconds"],
        "model_s": gen["model"]["seconds"],
        "peak_gib": max(gen["generate"]["peak_gib"], gen["export"]["peak_gib"]),
        "plan_mb": gen["export"]["plan_mb"],
        "inputs": cfg["inputs"],
        "revision": cfg["revision"][:8],
        "source": source,
    }


def _decision(decisions: dict, key: str, batch: str, status: str) -> dict | None:
    """A user verdict that replaces the measured open verdict of one process
    at one batch size (milestone.json gate_decisions)."""
    for d in decisions["decisions"]:
        if d["process"] == key and d["batch"] == batch and d["measured"] == status:
            return d
    return None


def _timing_of(
    proc: dict,
    name: str | None,
    cfg: dict | None,
    source: str,
    fastest: dict | None,
    decisions: dict,
) -> dict | None:
    """One configuration's batched full-colour cell; None without a record."""
    if cfg is None:
        return None
    if cfg.get("generation_error"):
        return {
            "status": "refused",
            "error": cfg["generation_error"].split(":")[0],
            "revision": cfg["revision"][:8],
            "source": source,
        }
    batch = _gate_batch(cfg)
    if batch is None:
        sizes = sorted(int(b) for b in cfg["batches"])
        return {
            "status": _no_gate_batch(cfg),
            "inputs": cfg["inputs"],
            "timed_batches": sizes,
            "revision": cfg["revision"][:8],
            "source": source,
        }
    rec = cfg["batches"][batch]
    t = rec["median_seconds_per_point"]
    out = {
        "status": "measured",
        "batch": int(batch),
        "seconds_per_point": t,
        "uncertainty": rec["uncertainty"],
        "stages": _split(rec["stages_per_point"]),
        "inputs": cfg["inputs"],
        "revision": cfg["revision"][:8],
        "g1_configuration": name,
        "source": f"{source}.batches['{batch}']",
    }
    if fastest is not None:
        out["ratio_to_fastest"] = t / fastest["seconds_per_point"]
        if fastest.get("bound") == "upper":
            # The fastest provider's production time is at most the bound,
            # so the ratio to it is at least this (_provider_runtime).
            out["ratio_to_fastest_bound"] = "lower"
    gate = rec.get("gate", {})
    if "ratio_to_binding_limit" in gate:
        # Below the user's 5 ms floor the gate tool's verdict is its floor
        # status (tools/loop_benchmark/gate.py GATE_FLOOR_STATUS) with the
        # checks' own verdict as measured_status.
        floored = "floor_seconds" in gate
        raw = gate["measured_status"] if floored else gate["status"]
        measured = {"inconclusive": "open"}.get(raw, raw)
        out["gate"] = {
            "status": measured,
            "ratio_to_limit": gate["ratio_to_binding_limit"],
            "band": gate["band_to_binding_limit"],
            "binding": NAMES[gate["binding_provider"]],
            "limit_seconds": gate["binding_limit"],
        }
        d = _decision(decisions, proc["key"], batch, raw)
        if d is not None:
            out["gate"].update(
                status=d["verdict"],
                measured_status=measured,
                decision=d["label"],
                decision_reason=d["reason"],
                decision_source="milestone.json gate_decisions"
                f" ({decisions['source']})",
            )
        # The user's gate rule (milestone.json gate_decisions.threshold_rule,
        # 2026-10-24 ~22:35): below 5 ms per point at B = 128 the
        # process has no blocking gate; the measured ratio, band and status
        # stay with the cell. It takes precedence over a decision. The gate
        # tool applies it (floor_seconds); the rule's words label it here,
        # and both must agree on the cell.
        rule = decisions.get("threshold_rule")
        below = rule is not None and t < rule["below_seconds_per_point"]
        if (
            rule is not None
            and floored
            and (gate["floor_seconds"] != rule["below_seconds_per_point"] or not below)
        ):
            raise ValueError(
                f"{proc['key']} B = {batch}: the gate tool's 5 ms floor"
                " disagrees with milestone.json gate_decisions.threshold_rule"
            )
        if below or floored:
            if rule is None:
                raise ValueError(
                    f"{proc['key']} B = {batch}: a floored gate verdict needs"
                    " milestone.json gate_decisions.threshold_rule"
                )
            out["gate"].setdefault("measured_status", measured)
            out["gate"].update(
                status=rule["verdict"],
                rule=rule["label"],
                rule_source="milestone.json gate_decisions.threshold_rule"
                f" ({rule['source']})",
            )
            if floored:
                out["gate"]["floor_seconds"] = gate["floor_seconds"]
    return out


def _adopted_schedule(
    proc: dict, name: str | None, batch: str, revision: str
) -> dict | None:
    """The schedule G1 adopted for a configuration's class where it is not
    the default protocol's B (g1.json schedules, adopt_m), timed at the same
    batch: shown next to the schedule-B value, which stays the main one.
    Only a schedule-M run of the main value's own revision (Table 1 shows
    the most recent measurements only, user 2026-10-24 ~18:35): an earlier
    campaign's run stays in the schedule table of the gate-G1 details."""
    if name is None:
        return None
    for s in proc.get("schedules", []):
        if s["configuration"] != name or not s["adopt_m"]:
            continue
        alt = proc["pyamplicol"].get(f"{name}/M")
        rec = (alt or {}).get("batches", {}).get(batch)
        if rec is None or alt["revision"][:8] != revision:
            return None
        return {
            "schedule": "M",
            "seconds_per_point": rec["median_seconds_per_point"],
            # The schedule-M run's own revision (an earlier campaign's run
            # where G1 did not repeat it): printed where it differs.
            "revision": alt["revision"][:8],
            "decision": f"g1.json processes[{proc['key']}].schedules ({name}: adopt_m)",
            "source": f"g1.json processes[{proc['key']}].pyamplicol"
            f"['{name}/M'].batches['{batch}']",
        }
    return None


def _lc_of(
    proc: dict,
    name: str | None,
    lc: dict | None,
    fc: dict | None,
    source: str,
    fc_source: str,
) -> dict | None:
    """One configuration's leading-colour cell; None if the configuration has
    no record of the row. A configuration that generated the process in full
    colour without an LC run says 'not timed'; one that refused it, 'refused'."""
    if lc is None:
        if fc is None:
            return None
        if fc.get("generation_error"):
            return {
                "status": "refused",
                "error": fc["generation_error"].split(":")[0],
                "revision": fc["revision"][:8],
                "source": f"{fc_source}.generation",
            }
        return {
            "status": "not timed",
            "what": "G1 timed this configuration in full colour only",
            "revision": fc["revision"][:8],
            "source": fc_source,
        }
    batch = _gate_batch(lc)
    if batch is None:
        return {
            "status": _no_gate_batch(lc),
            "timed_batches": sorted(int(b) for b in lc["batches"]),
            "source": source,
        }
    t = lc["batches"][batch]["median_seconds_per_point"]
    out = {
        "status": "measured",
        "batch": int(batch),
        "seconds_per_point": t,
        "schedule": lc["schedule"],
        "families": (lc.get("structure") or {}).get("families"),
        "inputs": lc["inputs"],
        "revision": lc["revision"][:8],
        "g1_configuration": name,
        "source": f"{source}.batches['{batch}']",
    }
    f = (fc or {}).get("batches", {}).get(batch)
    if f is not None:
        out["fc_seconds_per_point"] = f["median_seconds_per_point"]
        out["lc_over_fc"] = t / f["median_seconds_per_point"]
    adopted = _adopted_schedule(proc, name, batch, out["revision"])
    if adopted is not None:
        out["adopted_schedule"] = adopted
    return out


def _validation_g1(
    proc: dict, cfg: dict, configuration: str, source: str, checked: str | None
) -> dict:
    vs = cfg.get("values_vs_providers") or {}
    refs = [
        {
            "key": n,
            "short": SHORT[n],
            "points": vs[n]["points"],
            "max_finite": vs[n]["max_finite_deviation"],
            "median_finite": vs[n]["median_finite_deviation"],
            "worst_point": vs[n]["worst_point"],
        }
        for n in PROVIDERS
        if n in vs
    ]
    origin = f"{source}.values_vs_providers"
    fixture = not refs
    if fixture:
        # No provider run on the stream (g g > g g g g g): the run's own
        # check against its reference fixture (NJet's double-double values
        # at the stream's first points, at the fixture's scale).
        refs, origin = (
            _fixture_refs(cfg.get("accuracy_check")),
            f"{source}.accuracy_check",
        )
    if not refs:
        return {"status": "not compared"}
    worst = max(refs, key=lambda r: r["max_finite"])
    out = {
        "status": "compared",
        "configuration": configuration,
        "metric": "|a-b|/max(|a|,|b|,|Born| alpha/2pi), finite part, binary64",
        "points": max(r["points"] for r in refs),
        "references": refs,
        "max_finite": worst["max_finite"],
        "median_finite": max(r["median_finite"] for r in refs),
        "source": origin,
    }
    # The worst point re-evaluated with the stability checks: binary64
    # estimate E and the double-double value's deviation from the closest
    # provider, only if the campaign re-evaluated it in the validated
    # configuration itself (another configuration's estimate is not its own).
    # A fixture's worst point is indexed by the fixture, at its own scale
    # (NJet's mu_R = 1000 GeV, not the stream's): the stability rows of the
    # stream points are not its estimate; the rows at the fixture's own
    # points are (``stability --fixture``: fixture_stability, with their
    # deviations from the fixture's references).
    if fixture:
        name = worst.get("fixture")
        table, deviations = "fixture_stability", "deviation_vs_references"
        candidates = [
            r
            for r in proc.get(table, [])
            if name is not None and r.get("fixture") == name
        ]
    else:
        table, deviations = "stability", "deviation_vs_providers"
        candidates = proc.get(table, [])
    rows = {
        (r["index"], r["arithmetic"]): r
        for r in candidates
        if r["configuration"] == checked
    }
    b64 = rows.get((worst["worst_point"], "double"))
    dd = rows.get((worst["worst_point"], "double-double"))
    if b64 is not None:
        closest = independent = None
        if dd is not None:
            shown = {
                k: v for k, v in dd[deviations].items() if not fixture or k in SHOWN
            }
            closest = min(shown.values()) if shown else None
            others = {k: v for k, v in shown.items() if k != worst["key"]}
            if others:
                independent = min(others.items(), key=lambda kv: kv[1])
        within = b64["estimate"] >= worst["max_finite"]
        out["worst_point"] = {
            "index": worst["worst_point"],
            **({"fixture": name} if fixture else {}),
            "estimate": b64["estimate"],
            "within_estimate": within,
            "dd_closest": closest,
            # The stability run's revision (printed where it differs from
            # the validated configuration's).
            "revision": (b64.get("revision") or "")[:8] or None,
            "source": f"g1.json processes[{proc['key']}].{table} ({checked})",
        }
        # A deviation beyond pyAmpliCol's binary64 estimate that its
        # double-double value repeats is the reference's own (u u~ >
        # g g g g g at point 0: Recola 2.9e-10 in binary64 and in DD, E =
        # 1.9e-11, MadLoop 1.4e-12 in DD) only if another, independent
        # reference agrees with the DD value at least a hundred times better
        # (REFERENCE_OWN_MARGIN): the stability estimate measures numerical
        # conditioning only, and a systematic error of ours (a wrong
        # counterterm constant) would repeat in DD too. Stated, never used to
        # hide a deviation.
        own = None if dd is None or within else dd[deviations].get(worst["key"])
        if (
            own is not None
            and own > b64["estimate"]
            and dd["estimate"] < own
            and independent is not None
            and independent[1] <= own / REFERENCE_OWN_MARGIN
        ):
            out["worst_point"]["reference_own"] = {
                "key": worst["key"],
                "short": worst["short"],
                "dd_deviation": own,
                "dd_estimate": dd["estimate"],
                "independent": {"key": independent[0], "dd_deviation": independent[1]},
            }
    return out


def _fixture_refs(check: dict | None) -> list[dict]:
    """The references of a run's accuracy check against its reference
    fixture (pyamplicol_v2.Run.accuracy) in the shape of _validation_g1's,
    for the references Table 1 shows (SHOWN)."""
    if not check:
        return []
    names = sorted({n for row in check["rows"] for n in row["errors"]} & SHOWN)
    out = []
    for n in names:
        rows = [row for row in check["rows"] if n in row["errors"]]
        finite = [row["errors"][n]["finite"] for row in rows]
        worst = max(rows, key=lambda row: row["errors"][n]["finite"])
        out.append(
            {
                "key": n,
                "short": SHORT[n],
                "points": len(rows),
                "max_finite": max(finite),
                "median_finite": sorted(finite)[len(finite) // 2],
                "worst_point": worst["index"],
                "fixture": check.get("fixture"),
            }
        )
    return out


# An accepted point's double-double value equals the shown reference when they
# differ by at most binary64 rounding (the references are stored in binary64).
DD_EQUAL = 2.0**-52


def _accepted(proc: dict, entry: dict) -> dict:
    """A user acceptance of the points where a validation check exceeds its
    tolerance (milestone.json validation_decisions): the check keeps its
    tolerance and its passed: false. The label's claims are checked here:
    the accepted points must be exactly the check's points above the
    tolerance (over every reference and quantity), each within pyAmpliCol's
    binary64 estimate E at that point, with pyAmpliCol's double-double value
    equal to every shown reference to binary64 rounding (DD_EQUAL; the label
    states 'DD = NJet', ``fixture_stability`` rows of the configuration);
    otherwise the build stops."""
    name = entry["configuration"]
    check = proc["pyamplicol"][name]["accuracy_check"]
    where = f"g1.json processes[{proc['key']}].pyamplicol['{name}'].accuracy_check"
    tolerance = check["tolerance"]
    if check["fixture"] != entry["fixture"] or tolerance != entry["tolerance"]:
        raise ValueError(f"{where}: not the check the decision accepts")

    def worst(row: dict) -> float:
        return max(v for errors in row["errors"].values() for v in errors.values())

    above = {row["index"]: row for row in check["rows"] if worst(row) > tolerance}
    if sorted(above) != sorted(entry["points"]):
        raise ValueError(
            f"{where}: points above the tolerance {sorted(above)}, accepted"
            f" {entry['points']}"
        )
    rows = {
        (r["index"], r["arithmetic"]): r
        for r in proc.get("fixture_stability", [])
        if r["configuration"] == name and r.get("fixture") == check["fixture"]
    }
    points = []
    for index in entry["points"]:
        b64, dd = rows.get((index, "double")), rows.get((index, "double-double"))
        if b64 is None or dd is None:
            raise ValueError(f"{where}: point {index} has no estimate and DD value")
        shown = {k: v for k, v in dd["deviation_vs_references"].items() if k in SHOWN}
        if not shown or b64["estimate"] < worst(above[index]):
            raise ValueError(f"{where}: point {index} lies outside its estimate")
        if max(shown.values()) > DD_EQUAL:
            raise ValueError(f"{where}: point {index}'s DD value misses the reference")
        points.append(
            {
                "index": index,
                "finite": {
                    k: above[index]["errors"][k]["finite"]
                    for k in sorted(shown)
                    if "finite" in above[index]["errors"].get(k, {})
                },
                "max_error": worst(above[index]),
                "estimate": b64["estimate"],
                "dd_deviation": {k: shown[k] for k in sorted(shown)},
            }
        )
    return {
        "status": entry["label"],
        "short": entry["short"],
        "points": points,
        "tolerance": tolerance,
        "passed": check["passed"],
        "max_error": check["max_error"],
        "check": where,
        "source": "milestone.json validation_decisions",
    }


def _accept(rows: list[dict], g1: dict, decisions: dict | None) -> None:
    """Marks the user-accepted points on the row whose validation cell is
    the accepted check (validation.accepted); a decision on another check
    than the cell's stops the build (the acceptance would not be shown)."""
    procs = {p["key"]: p for p in g1["processes"]}
    cells = {r["key"]: r["validation"] for r in rows}
    for entry in (decisions or {}).get("accepted", []):
        accepted = _accepted(procs[entry["process"]], entry)
        validation = cells[entry["process"]]
        if validation.get("source") != accepted["check"]:
            raise ValueError(
                f"{entry['process']}: the accepted check {accepted['check']} is"
                f" not the validation cell's ({validation.get('source')})"
            )
        validation["accepted"] = accepted


NOTE_CELLS = ("generation", "full_colour", "leading_colour")


def _cell_notes(rows: list[dict], notes: dict | None) -> None:
    """Attaches the registry's notes on single measured cells (milestone.json
    cell_notes: a known limitation of a measured value, or its run
    conditions) to their main cells (<cell>.main.note). A note applies to one
    G1 configuration at one revision; when the cell's main value is not that
    measurement (a newer campaign, another configuration, no measurement) the
    build stops: the note is decided again, never carried over silently."""
    by_key = {r["key"]: r for r in rows}
    for entry in (notes or {}).get("notes", []):
        key, cell, name = entry["process"], entry["cell"], entry["configuration"]
        where = f"milestone.json cell_notes ({key}, {cell}, {name}@{entry['revision']})"
        if key not in by_key or cell not in NOTE_CELLS:
            raise ValueError(f"{where}: no such row or cell")
        main = by_key[key][cell]["main"]
        of_name = main.get("g1_configuration") == name or (
            f"pyamplicol['{name}']" in str(main.get("source", ""))
        )
        if (
            main.get("status") != "measured"
            or not of_name
            or main.get("revision") != entry["revision"][:8]
        ):
            raise ValueError(
                f"{where}: the cell's main value is {main.get('status')}"
                f" {main.get('g1_configuration')}@{main.get('revision')}"
                f" ({main.get('source')}), not the noted measurement"
            )
        main["note"] = {
            "kind": entry["kind"],
            "label": entry["label"],
            "reason": entry["reason"],
            "source": f"milestone.json cell_notes ({entry['source']})",
        }


def _meta_revisions(g1: dict, *keys: str) -> set[str]:
    """The revisions of meta keys (a key may list several, comma-separated)."""
    return {
        rev.strip()[:8]
        for k in keys
        if g1.get(k)
        for rev in str(g1[k]).split(",")
        if rev.strip()
    }


# Paths whose content is the engine: a tool revision of a campaign
# (slice_tool_revisions) must equal slice_revision on them.
ENGINE_PATHS = ("src", "rust")


def _check_tool_revisions(g1: dict) -> None:
    """Every slice_tool_revisions entry (the campaign's commits of the
    benchmark tools on top of slice_revision, e.g. the seven-leg rows of
    package measure-g1-7leg) runs slice_revision's engine: git diff over
    ENGINE_PATHS is empty wherever both revisions are present."""
    base = g1["slice_revision"][:8]
    for rev in sorted(_meta_revisions(g1, "slice_tool_revisions")):
        run = subprocess.run(
            ["git", "-C", str(REPO), "diff", "--quiet", base, rev, "--", *ENGINE_PATHS],
            capture_output=True,
            text=True,
            check=False,
        )
        if run.returncode == 1:
            raise ValueError(
                f"g1.json slice_tool_revisions {rev}: its engine"
                f" ({', '.join(ENGINE_PATHS)}) differs from slice_revision {base}"
            )


def _roles(g1: dict) -> tuple[set[str], set[str], set[str]]:
    """The campaign's two sides, from its own metadata (the gate CLI's --meta
    keys): the integrated configuration (slice_revision, slice_lc_revision,
    slice_tool_revisions -- tool commits on top of slice_revision with its
    engine, _check_tool_revisions -- and any revision recorded on the same
    branch, e.g. a refusal recorded earlier) and an optional development
    one (native_revision, native_commit; absent, equal to the integrated
    revision or not timed once the development work is integrated). A
    configuration on neither side is not shown."""
    integrated = _meta_revisions(
        g1, "slice_revision", "slice_lc_revision", "slice_tool_revisions"
    )
    _check_tool_revisions(g1)
    timed = {
        cfg["revision"][:8]
        for proc in g1["processes"]
        for cfg in proc["pyamplicol"].values()
    }
    dev = (_meta_revisions(g1, "native_revision", "native_commit") - integrated) & timed
    branches = {
        cfg["branch"]
        for proc in g1["processes"]
        for cfg in proc["pyamplicol"].values()
        if cfg["revision"][:8] in integrated and cfg["branch"] != "HEAD"
    }
    return integrated, dev, branches


def _dev_branch(g1: dict, ms: dict, dev: set[str]) -> str | None:
    """The branch of the development revisions: the campaign's own
    native_branch, else milestone.json development.revisions, else the
    configurations' records (the gate tool records a detached checkout as
    'HEAD', which names no branch)."""
    if not dev:
        return None
    if g1.get("native_branch"):
        return g1["native_branch"]
    known = (ms.get("development") or {}).get("revisions", {})
    names = {known[r] for r in dev if r in known}
    if not names:
        names = {
            cfg["branch"]
            for proc in g1["processes"]
            for cfg in proc["pyamplicol"].values()
            if cfg["revision"][:8] in dev and cfg["branch"] != "HEAD"
        }
    if len(names) != 1:
        raise ValueError(f"development revisions {sorted(dev)}: branch {names}")
    return names.pop()


def _pick(cfgs: dict, side, accuracy: str) -> tuple[str, dict] | tuple[None, None]:
    """The default-protocol configuration (schedule B, 16 lanes) of one side
    and colour accuracy; native per-point inputs first (INPUTS_PREFERENCE)."""
    found = [
        (name, cfg)
        for name, cfg in cfgs.items()
        if side(cfg)
        and cfg["accuracy"] == accuracy
        and cfg["schedule"] == "B"
        and cfg["lanes"] == 16
    ]
    if not found:
        return None, None
    rank = {inputs: i for i, inputs in enumerate(INPUTS_PREFERENCE)}
    return min(found, key=lambda x: rank.get(x[1]["inputs"], len(rank)))


def _newest(cells: list[tuple[str, str | None, dict | None]]) -> dict:
    """The main-configuration rule for one cell: the newest candidate that
    measured it, else the status of the newest candidate with a record of
    the row (cells are (configuration, revision, cell or None), newest
    first). The chosen cell names its configuration; 'considered' lists
    every candidate's revision and status in order, so the choice can be
    audited."""
    considered = [
        {
            "configuration": cid,
            "revision": rev,
            "status": "no record" if c is None else c["status"],
        }
        for cid, rev, c in cells
    ]
    chosen = next(
        (
            (cid, c)
            for cid, _, c in cells
            if c is not None and c["status"] in ("measured", "compared")
        ),
        None,
    )
    if chosen is None:
        chosen = next(((cid, c) for cid, _, c in cells if c is not None), None)
    if chosen is None:
        return {
            "status": "not measured",
            "configuration": None,
            "considered": considered,
        }
    cid, cell = chosen
    return {**cell, "configuration": cid, "considered": considered}


def _ref_keys(val: dict) -> list[str]:
    return [r["key"] for r in val["references"]]


def _partial_repeat(new: dict, old: dict) -> str | None:
    """Why a newer comparison only repeats part of an older one
    (VALIDATION_RULE), or None if it replaces it: less complete (fewer
    points or fewer references) and no larger deviation."""
    fewer = []
    if new["points"] < old["points"]:
        fewer.append(f"{new['points']} of {old['points']} points")
    lost = [SHORT[k] for k in _ref_keys(old) if k not in _ref_keys(new)]
    if lost:
        fewer.append(f"without {', '.join(lost)}")
    if not fewer or new["max_finite"] > old["max_finite"]:
        return None
    return (
        f"{'; '.join(fewer)}; largest deviation {new['max_finite']:.2e}"
        f" <= {old['max_finite']:.2e}"
    )


def _newest_validation(cells: list[tuple[str, str | None, dict | None]]) -> dict:
    """The main-configuration rule for the validation cell (MAIN_RULE with
    VALIDATION_RULE): from the newest comparison, step back to an older one
    while the current one only repeats part of it. The repeats stay with
    the cell (partial_repeats: configuration, revision, record, points,
    references, deviation and why), so the choice can be audited."""
    main = _newest(cells)
    compared = [
        (cid, rev, c)
        for cid, rev, c in cells
        if c is not None and c["status"] == "compared"
    ]
    if not compared:
        return main
    cid, rev, cur = compared[0]
    repeats = []
    for old_cid, old_rev, old in compared[1:]:
        why = _partial_repeat(cur, old)
        if why is None:
            continue
        repeats.append(
            {
                "configuration": cid,
                "revision": rev,
                "record": cur.get("record"),
                "points": cur["points"],
                "point_indices": cur.get("point_indices"),
                "references": [SHORT[k] for k in _ref_keys(cur)],
                "max_finite": cur["max_finite"],
                "repeats": old_cid,
                "repeats_revision": old_rev,
                "why": why,
                "source": cur["source"],
            }
        )
        cid, rev, cur = old_cid, old_rev, old
    if not repeats:
        return main
    return {
        **cur,
        "configuration": cid,
        "considered": main["considered"],
        "partial_repeats": repeats,
        "rule": VALIDATION_RULE,
    }


def _families(pairs: dict, main: dict, order: tuple[str, ...]) -> int | None:
    """Loop families: the configuration of the main full-colour (LC) value,
    else the newest one that recorded them."""
    for cid in (main.get("configuration"), *order):
        cfg = pairs.get(cid, (None, None))[1]
        count = ((cfg or {}).get("structure") or {}).get("families")
        if count is not None:
            return count
    return None


def _sides(g1: dict) -> dict:
    """The campaign's sides (configuration -> predicate on a configuration
    record) and their revisions for the recency order: the integrated side's
    slice_revision and the development side's native_revision (else
    native_commit)."""
    integrated, dev_revs, branches = _roles(g1)

    def is_integrated(cfg: dict) -> bool:
        rev = cfg["revision"][:8]
        return rev not in dev_revs and (rev in integrated or cfg["branch"] in branches)

    def is_dev(cfg: dict) -> bool:
        return cfg["revision"][:8] in dev_revs

    # A campaign without a configuration at its own slice_revision or at one
    # of its tool revisions (slice_tool_revisions: slice_revision's engine,
    # _check_tool_revisions) -- e.g. a new slice_revision over the
    # configurations of an older campaign -- is inconsistent: stop instead of
    # printing its cells as missing.
    slice_rev = g1["slice_revision"][:8]
    own = {slice_rev} | _meta_revisions(g1, "slice_tool_revisions")
    if not any(
        cfg["revision"][:8] in own
        for proc in g1["processes"]
        for cfg in proc["pyamplicol"].values()
    ):
        raise ValueError(
            f"g1.json slice_revision {slice_rev}: no configuration is"
            " recorded at it or at its tool revisions; re-record the"
            " configurations with the campaign"
        )
    side = {"integrated": is_integrated}
    revisions = {"integrated": g1["slice_revision"][:8]}
    if dev_revs:
        side["development"] = is_dev
        revisions["development"] = (g1.get("native_revision") or g1["native_commit"])[
            :8
        ]
    return {"predicates": side, "revisions": revisions}


def _threads(ms: dict, revision: str) -> str:
    """The generation threads of a development record, as its DESIGN
    increment states them (milestone.json development_records.threads)."""
    return (
        ms["development_records"]
        .get("threads", {})
        .get(revision, "thread count not recorded")
    )


def _record_cells(ms: dict, meas: dict, key: str) -> dict | None:
    """The development validation record of a process (measured.json
    required_native) as candidate cells: generation and validation, and the
    'pending' status of a batched timing the records never make."""
    rec = meas["required_native"]["processes"].get(key)
    if rec is None:
        return None
    src = f"measured.json required_native.processes[{key}]"
    # The records' run conditions differ from G1's protocol (shared host
    # under load against idle pinned cores): stated with every value.
    cond = ms["development_records"]
    conditions = {
        "conditions": cond["conditions"],
        "conditions_short": cond["short"],
        # The generation threads the record's DESIGN increment states.
        "threads": _threads(ms, rec["revision"]),
        "conditions_source": "milestone.json development_records",
    }
    generation = {
        "status": "measured",
        "seconds": rec["generate_s"] + rec["export_s"],
        "generate_s": rec["generate_s"],
        "export_s": rec["export_s"],
        # Generation memory: the larger of the two stages' peak RSS (VmHWM);
        # the record's process peak also covers the point evaluations of the
        # validation run.
        "peak_gib": max(rec["generate_peak_gib"], rec["export_peak_gib"]),
        "process_peak_gib": rec["max_rss_gib"],
        "plan_mb": rec["plan_json_mb"],
        "inputs": rec["inputs"],
        "counterterms": rec["counterterms"],
        "branch": meas["required_native"]["branch"],
        "record": rec["record"],
        "revision": rec["revision"],
        "source": src,
        **conditions,
    }
    validation = _validation_native(rec, src)
    validation.update(record=rec["record"], revision=rec["revision"])
    # Earlier records of the process (measured.json required_native
    # superseded): older candidates of the validation cell only
    # (VALIDATION_RULE), never of its generation, which the newest record
    # measured.
    older = meas["required_native"].get("superseded", {}).get(key, [])
    older_validations = []
    for i, old in enumerate(older if isinstance(older, list) else [older]):
        osrc = f"measured.json required_native.superseded[{key}]" + (
            f"[{i}]" if isinstance(older, list) else ""
        )
        cell = _validation_native(old, osrc)
        cell.update(record=old["record"], revision=old["revision"])
        older_validations.append(cell)
    timing = {
        "status": "pending",
        "package": ms["pending"]["batched"],
        "what": "the development validation records time single points"
        " only; batched timings come from G1",
        "revision": rec["revision"],
        "source": f"{src} (no batched timing); milestone.json pending",
    }
    return {
        "revision": rec["revision"],
        "generation": generation,
        "validation": validation,
        "older_validations": older_validations,
        "timing": timing,
    }


def _validation_cells(
    recency: Recency,
    cands: list[tuple[str, str]],
    side_cells: dict[str, dict | None],
    rec: dict | None,
) -> list[tuple[str, str | None, dict | None]]:
    """The validation cell's candidates newest first (MAIN_RULE): the row's
    configurations (cands; a G1 side's comparison from side_cells, the
    newest record's for the development records) and the process's older
    records, so that VALIDATION_RULE can keep an older, more complete
    comparison."""
    older = (
        {}
        if rec is None
        else {
            f"development_records@{c['revision']}": c for c in rec["older_validations"]
        }
    )
    vcands = cands + [(cid, c["revision"]) for cid, c in older.items()]
    rev = dict(vcands)
    cells = {
        **side_cells,
        **older,
        "development_records": None if rec is None else rec["validation"],
    }
    return [(_base(cid), rev[cid], cells.get(cid)) for cid in recency.order(vcands)]


def _ordered(
    order: list[str],
    rev: dict[str, str | None],
    side_cells: dict[str, dict | None],
    record_cell: dict | None = None,
) -> list[tuple[str, str | None, dict | None]]:
    """(configuration, revision, cell) newest first: a G1 side's cell from
    side_cells, the record's cell for the records' configuration (None: the
    records have no such cell)."""
    return [(cid, rev[cid], side_cells.get(cid, record_cell)) for cid in order]


def _g1_validation(
    proc: dict, cid: str, name: str | None, cfg: dict | None, base: str
) -> dict | None:
    """A G1 side's comparison with the providers (without a provider run on
    the stream, its check against its reference fixture); None without
    either."""
    if cfg is None or cfg.get("generation_error"):
        return None
    if not cfg.get("values_vs_providers") and not _fixture_refs(
        cfg.get("accuracy_check")
    ):
        return None
    return _validation_g1(proc, cfg, cid, f"{base}['{name}']", name)


def _g1_rows(
    g1: dict, specs: dict, decisions: dict, records: dict, recency: Recency
) -> list[dict]:
    sides = _sides(g1)
    side, revisions = sides["predicates"], sides["revisions"]
    rows = []
    for proc in g1["processes"]:
        key = proc["key"]
        base = f"g1.json processes[{key}].pyamplicol"
        cfgs = proc["pyamplicol"]
        rec = records.get(key)
        cands = [(cid, revisions[cid]) for cid in KIND_ORDER if cid in revisions]
        if rec is not None:
            cands.append(("development_records", rec["revision"]))
        rev = dict(cands)
        # Candidates newest first; the G1 sides among them.
        order = recency.order(cands)
        g1_order = tuple(cid for cid in order if cid in side)
        fc = {cid: _pick(cfgs, side[cid], "full") for cid in g1_order}
        lc = {cid: _pick(cfgs, side[cid], "lc") for cid in g1_order}
        runtime = _provider_runtime(proc)
        fastest = runtime["fastest"]
        gens = _provider_generation_g1(proc)
        gen_fastest = _fastest_generation(gens)

        rec_gen = None if rec is None else rec["generation"]
        gen = _newest(
            _ordered(
                order,
                rev,
                {
                    cid: _generation_of(
                        fc[cid][1], f"{base}['{fc[cid][0]}'].generation"
                    )
                    for cid in g1_order
                },
                rec_gen,
            )
        )
        if gen["status"] == "measured" and gen_fastest is not None:
            # GENERATION_RULE: G1's provider generation pairs with a G1 side
            # only; a newer record ran under other conditions.
            if gen["configuration"] in side:
                gen["ratio_to_fastest"] = gen["seconds"] / gen_fastest["seconds"]
                gen["ratio_basis"] = GENERATION_BASIS["g1"]
            else:
                gen["no_ratio"] = GENERATION_BASIS["unmatched"]
        fc_main = _newest(
            _ordered(
                order,
                rev,
                {
                    cid: _timing_of(
                        proc,
                        fc[cid][0],
                        fc[cid][1],
                        f"{base}['{fc[cid][0]}']",
                        fastest,
                        decisions,
                    )
                    for cid in g1_order
                },
            )
        )
        lc_main = _newest(
            _ordered(
                order,
                rev,
                {
                    cid: _lc_of(
                        proc,
                        lc[cid][0],
                        lc[cid][1],
                        fc[cid][1],
                        f"{base}['{lc[cid][0]}']",
                        f"{base}['{fc[cid][0]}']",
                    )
                    for cid in g1_order
                },
            )
        )
        # Validation: the newest configuration compared with the references,
        # unless it only repeats part of an older comparison (VALIDATION_RULE).
        validation = _newest_validation(
            _validation_cells(
                recency,
                cands,
                {cid: _g1_validation(proc, cid, *fc[cid], base) for cid in g1_order},
                rec,
            )
        )
        if validation["status"] == "not measured":
            validation.update(
                status="not compared",
                note="no configuration compared it with the providers",
            )
        rows.append(
            {
                "key": key,
                "label": proc["label"],
                "math": _math(proc["label"]),
                "outgoing": proc["outgoing"],
                "legs": 2 + proc["outgoing"],
                "corrections": specs[key]["correction"],
                "kind": "g1",
                "families": {
                    "fc": _families(fc, fc_main, g1_order),
                    "lc": _families(lc, lc_main, g1_order),
                    "source": f"{base}[...].structure (main value's configuration)",
                },
                "validation": validation,
                "generation": {
                    "main": gen,
                    "providers": gens,
                    "fastest": gen_fastest,
                    "source": f"g1.json processes[{key}].providers"
                    " (MadLoop generation, Recola setup)",
                },
                "full_colour": {
                    "gate_rule": "G1"
                    if proc["gated"]
                    else "no gate (2->2)"
                    if proc["outgoing"] < 3
                    else "no gate (no matched provider)",
                    "main": fc_main,
                    "providers": runtime["providers"],
                    "fastest": fastest,
                    "source": f"g1.json processes[{key}].providers (median s/pt)",
                },
                "leading_colour": {"main": lc_main},
            }
        )
    return rows


def _alternative(njet: dict, meas: dict, label: str) -> dict | None:
    """An existing alternative that is not a matched provider (NJet: massless
    five-flavour QCD) of a row without one, shown for orientation only: no
    ratio, no gate."""
    if label not in njet:
        return None
    one = meas["njet_single_evaluation"]["standard"]
    return {
        "name": one["tool"],
        "seconds_per_evaluation": one["mean_s"],
        "what": "standard full-colour sum, one evaluation, double precision,"
        " one pinned core; not a matched provider",
        "source": "measured.json njet_single_evaluation.standard",
    }


def _no_matched_provider(rows: list[dict], ms: dict, meas: dict, g1: dict) -> None:
    """A G1 row without any provider timing (g g > g g g g g: every provider
    beyond HANDOFF 0.1; g1.json gated false) is reported without a gate
    (ADDENDUM H), as its required row was: the registry's alternative and
    validation note stay with it, and its sanity checks (_sanity_checks)."""
    njet = {r["label"]: r for r in ms["njet"]["rows"]}
    notes = ms.get("status_notes", {}).get("notes", {})
    for r in rows:
        fc = r["full_colour"]
        if r["kind"] != "g1" or fc["gate_rule"] != "no gate (no matched provider)":
            continue
        fc["alternative"] = _alternative(njet, meas, r["math"])
        note = notes.get(r["key"], {})
        # Its providers' generations that did not finish (stopped under
        # HANDOFF 0.1), from their reference runs, as in its required row.
        _, unfinished = _reference_generation(
            meas["provider_generation"]["processes"].get(r["key"])
        )
        if unfinished:
            if "providers" in note:
                unfinished["note"] = note["providers"]
            r["generation"]["unfinished"] = unfinished
            r["generation"]["unfinished_source"] = (
                f"measured.json provider_generation.processes[{r['key']}]"
            )
        if "validation" in note and r["validation"].get("status") == "compared":
            r["validation"]["note"] = note["validation"]
        fc["sanity_checks"] = _sanity_checks(g1, r["key"], note)


def _sanity_checks(g1: dict, key: str, note: dict) -> dict:
    """ADDENDUM H's checks of a speed reported without a gate: rotational
    invariance (the binary64 stability rows of g1.json: one rotation and the
    reduction direction at stream points, per configuration) and the Ward
    identity (one gluon's polarisation replaced by its momentum: the row's own
    Ward rows, else every G1 row's at lower multiplicity with the registry's
    reason, milestone.json status_notes.notes[key].ward)."""
    procs = {p["key"]: p for p in g1["processes"]}
    proc = procs[key]
    base = f"g1.json processes[{key}]"
    rotation: dict = {}
    for row in proc.get("stability", []):
        if row["arithmetic"] != "double":
            continue
        rot = [v for name, v in row["checks"].items() if name.startswith("rotation")]
        c = rotation.setdefault(
            row["configuration"],
            {"points": [], "max_rotation": 0.0, "max_estimate": 0.0, "revision": None},
        )
        c["points"].append(row["index"])
        c["max_rotation"] = max(c["max_rotation"], *rot)
        c["max_estimate"] = max(c["max_estimate"], row["estimate"])
        c["revision"] = row["revision"][:8]
    out: dict = {
        "rotation": {
            "status": "measured" if rotation else "not run",
            "configurations": rotation,
            "what": "binary64 finite part: relative deviation under one rotation"
            " about z by (3/5, 4/5), and the estimate E (rotation plus reduction"
            " direction)",
            "source": f"{base}.stability",
        }
    }

    def ward_of(p: dict) -> dict:
        rows = [w for w in p.get("ward", []) if "passed" in w]
        return {
            "key": p["key"],
            "legs": p["outgoing"] + 2,
            "rows": len(rows),
            "passed": bool(rows) and all(w["passed"] for w in rows),
            "max_virtual_ratio": max(max(w["ratios"]["virtual"]) for w in rows)
            if rows
            else None,
            "source": f"g1.json processes[{p['key']}].ward",
        }

    if proc.get("ward"):
        out["ward"] = {"status": "measured", **ward_of(proc)}
    else:
        out["ward"] = {
            # A check the coordinator ruled pending (milestone.json
            # status_notes.notes[key].ward_status) says so.
            "status": note.get("ward_status", "not run"),
            "reason": note.get("ward"),
            "reason_source": f"milestone.json status_notes.notes[{key}].ward",
            "lower_multiplicity": [
                ward_of(p)
                for p in g1["processes"]
                if p.get("ward") and p["outgoing"] < proc["outgoing"]
            ],
        }
    return out


def _validation_native(rec: dict, source: str) -> dict:
    refs = []
    for ref, dev in rec["max_deviation"].items():
        if "finite" not in dev or ref not in SHOWN:
            continue  # the Catani operator checks the poles only
        refs.append(
            {
                "key": ref,
                "short": SHORT.get(ref, ref),
                "points": len(rec["points"]),
                "max_finite": dev["finite"],
            }
        )
    worst = max(refs, key=lambda r: r["max_finite"])
    out = {
        "status": "compared",
        "configuration": "development_records",
        "metric": "|a-b|/max(|a|,|b|,|Born| alpha/2pi), finite part, binary64",
        "points": len(rec["points"]),
        "point_indices": rec["points"],
        "references": refs,
        "max_finite": worst["max_finite"],
        "tolerance": rec["tolerance"],
        "passed": rec["passed"],
        "source": source,
    }
    per_point = rec["max_error_per_point"]
    estimates = rec["stability_estimate_per_point"]
    if all(e is not None for e in estimates):
        out["within_estimate"] = all(
            e >= err for e, err in zip(estimates, per_point, strict=True)
        )
    return out


def _seconds(text: str) -> list[float]:
    """The times of a transcribed provider entry (a value or a range such as
    '0.348-0.353' with an en dash); none for a status ('no library')."""
    if not re.match(r"^\s*\d", text):
        return []
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)]


def _reference(ref: dict, prov: dict | None, matched: list[str], factor: float) -> dict:
    """The seven-leg provider production references and the gate limit
    computed from them: faster than MadLoop and at most factor x each of
    Recola and OpenLoops, at the lower end of each range. OpenLoops and Recola
    are DESIGN Table 1b's production values (milestone.json, text); MadLoop's
    production-build times come from its timing record (measured.json). The
    limit exists only when every matched provider has a production time;
    otherwise the missing ones are named and no limit is formed."""
    providers = {}
    for name in ("openloops", "recola"):
        values = _seconds(ref[name])
        providers[name] = {
            "text": ref[name],
            "low": min(values) if values else None,
            "source": "milestone.json gate_references (DESIGN 1.3 Table 1b,"
            " 2026-10-20)",
        }
    ml = ((prov or {}).get("madloop") or {}).get("production")
    if ml is not None and "seconds_per_point" in ml:
        values = ml["seconds_per_point"]
        providers["madloop"] = {
            "text": None,
            "low": min(values),
            "high": max(values),
            "production_build": ml["production_build"],
            "source": ml["source"],
        }
    else:
        providers["madloop"] = {
            "text": None,
            "low": None,
            "status": "not measured"
            if ml is None
            else f"not measured (last run state: {ml['status']}, {ml['updated'][:10]})",
            "source": f"measured.json provider_generation.processes"
            f"[{(prov or {}).get('key', '?')}].madloop.production",
        }
    rc = ((prov or {}).get("recola") or {}).get("protocol")
    if providers["recola"]["low"] is None and rc is not None:
        # Recola's protocol run (all poles, Collier cache as recorded): shown
        # for orientation, never a production time or a limit.
        providers["recola"]["protocol"] = {
            "low": min(rc["seconds_per_point"]),
            "high": max(rc["seconds_per_point"]),
            "compute_ir_poles": rc["compute_ir_poles"],
            "collier_cache": rc["collier_cache"],
            "source": "measured.json provider_generation.processes"
            f"[{prov['key']}].recola.protocol",
        }
    missing = [NAMES[n] for n in matched if providers[n]["low"] is None]
    limits = [
        (round((1.0 if n == "madloop" else factor) * providers[n]["low"], 10), NAMES[n])
        for n in matched
        if providers[n]["low"] is not None
    ]
    limit = min(limits) if limits and not missing else None
    return {
        "providers": providers,
        "matched": [NAMES[n] for n in matched],
        "missing_production": missing,
        "limit_seconds": None if limit is None else limit[0],
        "binding": None if limit is None else limit[1],
        "source": "milestone.json gate_references (OpenLoops, Recola);"
        " measured.json provider_generation (MadLoop production build);"
        " limit computed by scripts/build_summary.py",
    }


def _registry_status(note: dict, key: str) -> dict | None:
    """The registry's status of a process without a G1 record: refused on
    loop (inferred, the basis says why), in development (its work package
    has started but no configuration generates the process yet) or not
    started anywhere, by its short attribution (no record of a run)."""
    src = f"milestone.json status_notes.notes[{key}]"
    if "refused" in note:
        return {
            "status": "refused",
            "reason": note["refused"],
            "basis": note.get("refused_basis"),
            "source": src,
        }
    if "in_development" in note:
        return {
            "status": "in development",
            "reason": note["in_development"],
            "package": note.get("package"),
            "source": src,
        }
    if "not_started" in note:
        return {
            "status": "not started",
            "reason": note["not_started"],
            "package": note.get("package"),
            "source": src,
        }
    return None


def _required_rows(
    ms: dict,
    meas: dict,
    known: set[str],
    factor: float,
    records: dict,
    recency: Recency,
) -> list[dict]:
    """The required rows without a G1 record (the 2 -> 5 set): the
    development validation record, then the registry (main-configuration
    rule)."""
    prov_gen = meas["provider_generation"]["processes"]
    refs = {(r["label"], r.get("corr")): r for r in ms["gate_references"]["rows"]}
    notes = ms.get("status_notes", {}).get("notes", {})
    njet = {r["label"]: r for r in ms["njet"]["rows"]}
    rows = []
    for req in ms["required"]["rows"]:
        corr = req.get("corr")
        text = _text(req["label"])
        key = _key(text, corr)
        if key in known:
            # A G1 row (g g > g g g g, g g > t t~ g g, the timed 2 -> 5 rows;
            # a corrections label is part of the key: gg_ttxemepg_qcd).
            continue
        note = notes.get(key, {})
        rec = records.get(key)
        dev_gen = None if rec is None else rec["generation"]
        # The newest record's comparison, unless it only repeats part of an
        # older record's (VALIDATION_RULE).
        validation = (
            {"status": "not compared", "note": req["validation"]}
            if rec is None
            else dict(
                _newest_validation(
                    _validation_cells(
                        recency, [("development_records", rec["revision"])], {}, rec
                    )
                )
            )
        )
        pg = prov_gen.get(key)
        gens, unfinished = _reference_generation(pg)
        if unfinished and "providers" in note:
            unfinished["note"] = note["providers"]
        gen_fastest = _fastest_generation(gens)
        if dev_gen is not None and gen_fastest is not None:
            # GENERATION_RULE: the record and the providers' reference runs.
            dev_gen["ratio_to_fastest"] = dev_gen["seconds"] / gen_fastest["seconds"]
            dev_gen["ratio_basis"] = GENERATION_BASIS["records"]
        # Matched providers: those with a generated process (a completed
        # generation or a prebuilt library); a gate needs one.
        matched = [n for n in PROVIDERS if gens[n] is not None]
        ref = refs.get((req["label"], corr))
        reference = (
            None
            if ref is None
            else _reference(
                ref, None if pg is None else {**pg, "key": key}, matched, factor
            )
        )
        if not matched:
            gate_rule = "no gate (no matched provider)"
        elif reference is not None and reference["limit_seconds"] is not None:
            gate_rule = "G1 (not timed by G1)"
        else:
            gate_rule = "G1 (no complete gate limit yet)"
        alternative = None if matched else _alternative(njet, meas, req["label"])
        # The only family count of a seven-leg generation is the seven-gluon
        # run of measured.json; it describes the row only with the row's
        # particle veto (the validation's, by the registry). Otherwise it is
        # printed as the other configuration's count, never as the row's.
        families = {"fc": None, "lc": None, "source": None}
        counts = meas["seven_gluon"]["generation_latest"]
        if counts["process"] == text and corr is None:
            source = "measured.json seven_gluon.generation_latest"
            if counts["particle_veto"] == note.get("particle_veto", []):
                families.update(fc=counts["counts"]["families"], source=source)
            else:
                families["other_configuration"] = {
                    "fc": counts["counts"]["families"],
                    "particle_veto": counts["particle_veto"],
                    "row_particle_veto": note["particle_veto"],
                    "source": f"{source} (counts, particle_veto);"
                    f" milestone.json status_notes.notes[{key}].particle_veto",
                }
        if "validation" in note and validation.get("status") == "compared":
            validation["note"] = note["validation"]
        status = _registry_status(note, key)
        # The records time single points only: a row they cover waits for
        # its batched timing (the package named in milestone.json pending).
        timing = None if rec is None else rec["timing"]
        registry = None if status is None else dict(status)
        # Candidates newest first: the record (one per process), then the
        # registry, which records no run.
        cands = [] if rec is None else [("development_records", rec["revision"])]
        order = [*recency.order(cands), "registry"]
        revs = {**dict(cands), "registry": None}
        rows.append(
            {
                "key": key,
                "label": text,
                "math": _math(text),
                "outgoing": len(text.split(" > ")[1].split()),
                "legs": len(text.split()) - 1,
                "corrections": corr or "QCD",
                "kind": "records",
                "families": families,
                "validation": validation,
                # Row-level status of the newest configuration with a record
                # (none where the development records generate the process).
                "row_status": None if rec is not None else status,
                "generation": {
                    "main": _newest(
                        _ordered(order, revs, {"registry": registry}, dev_gen)
                    ),
                    "providers": gens,
                    "unfinished": unfinished,
                    "fastest": gen_fastest,
                    "source": f"measured.json provider_generation.processes[{key}]",
                },
                "full_colour": {
                    "gate_rule": gate_rule,
                    "main": _newest(
                        _ordered(order, revs, {"registry": registry}, timing)
                    ),
                    "alternative": alternative,
                    "reference": reference,
                },
                "leading_colour": {
                    "main": _newest(
                        _ordered(order, revs, {"registry": registry}, timing)
                    )
                },
            }
        )
    return rows


def _records(rows: list[dict], recency: Recency) -> list[dict]:
    """The DESIGN records of the main values from the development records
    (generation or validation), newest first, each with its revision and the
    rows it covers."""
    out: dict[str, dict] = {}
    for r in rows:
        for main in (r["generation"]["main"], r["validation"]):
            if main.get("configuration") != "development_records":
                continue
            x = out.setdefault(
                main["record"],
                {"record": main["record"], "revision": main["revision"], "rows": []},
            )
            if r["math"] not in x["rows"]:
                x["rows"].append(r["math"])
    order = recency.newest_first([x["revision"] for x in out.values()])
    return sorted(out.values(), key=lambda x: order.index(x["revision"]))


def _side_inputs(g1: dict, predicate) -> list[str]:
    """The per-point inputs of a G1 side's default-protocol configurations
    (full colour and LC), from its own records."""
    found = set()
    for proc in g1["processes"]:
        for accuracy in ("full", "lc"):
            _, cfg = _pick(proc["pyamplicol"], predicate, accuracy)
            if cfg is not None:
                found.add(cfg["inputs"])
    return sorted(found)


def _configurations(
    g1: dict, ms: dict, meas: dict, rows: list[dict], recency: Recency
) -> dict:
    """The candidate configurations of the main-configuration rule, each with
    its provenance, its per-point inputs (from its own records), the rows
    where it supplies a main value (main_rows) and, per cell, those rows
    (main_cells: generation, validation, full_colour, leading_colour)."""
    cells = ("generation", "full_colour", "leading_colour")

    def main_cells(cid: str) -> dict[str, list[str]]:
        out = {
            c: [r["key"] for r in rows if r[c]["main"].get("configuration") == cid]
            for c in cells
        }
        out["validation"] = [
            r["key"] for r in rows if r["validation"].get("configuration") == cid
        ]
        return {c: out[c] for c in ("generation", "validation", *cells[1:])}

    def main_rows(cid: str) -> list[str]:
        found = {k for keys in main_cells(cid).values() for k in keys}
        return [r["key"] for r in rows if r["key"] in found]

    side = _sides(g1)["predicates"]
    development = ms.get("development") or {}
    label = development.get("label", "development")
    _, dev_revs, _ = _roles(g1)
    out: dict = {}
    if dev_revs:
        out["development"] = {
            "kind": "g1",
            "label": label,
            "integration": development.get("integration"),
            "branch": _dev_branch(g1, ms, dev_revs),
            "revision": g1.get("native_revision"),
            "commit": g1.get("native_commit"),
            "native_build": g1.get("native_build"),
            "native_digest": g1.get("native_digest"),
            "date": g1["date"],
            "inputs": _side_inputs(g1, side["development"]),
            "main_rows": main_rows("development"),
            "main_cells": main_cells("development"),
            "source": "g1.json native_revision, native_commit, native_build,"
            " native_digest, date;"
            " label, integration and branch: milestone.json development",
        }
    out["integrated"] = {
        "kind": "g1",
        "label": "on loop",
        "revision": g1["slice_revision"],
        "lc_revision": g1.get("slice_lc_revision"),
        "native_build": g1.get("slice_build"),
        "native_digest": g1.get("slice_native_digest"),
        "date": g1["date"],
        "inputs": _side_inputs(g1, side["integrated"]),
        "main_rows": main_rows("integrated"),
        "main_cells": main_cells("integrated"),
        "source": "g1.json slice_revision, slice_lc_revision, slice_build,"
        " slice_native_digest, date",
    }
    branch = meas["required_native"]["branch"]
    in_development = branch in (development.get("revisions") or {}).values()
    records_used = _records(rows, recency)
    out["development_records"] = {
        "kind": "records",
        "label": label if in_development else "development records",
        "integration": development.get("integration") if in_development else None,
        # The revision that integrated the branch into loop (milestone.json
        # development.integrated_at): its records then measured the
        # integrated code on the branch, before the integration.
        "integrated_at": development.get("integrated_at") if in_development else None,
        "branch": branch,
        "inputs": sorted(
            {r["inputs"] for r in meas["required_native"]["processes"].values()}
        ),
        "conditions": ms["development_records"]["conditions"],
        "conditions_short": ms["development_records"]["short"],
        # Generation threads per record revision (as each increment states).
        "threads": {r["revision"]: _threads(ms, r["revision"]) for r in records_used},
        # The DESIGN records of the development validations, each with the
        # rows it covers.
        "records": records_used,
        "main_rows": main_rows("development_records"),
        "main_cells": main_cells("development_records"),
        "source": "measured.json required_native; label: milestone.json"
        " development; conditions: milestone.json development_records",
    }
    out["registry"] = {
        "kind": "records",
        "label": "registry (no run)",
        "main_rows": main_rows("registry"),
        "main_cells": main_cells("registry"),
        "source": "milestone.json status_notes",
    }
    return out


EW_G1 = "msm-g1.json"


def _with_ew_rows(g1: dict) -> tuple[dict, set[str]]:
    """g1.json with the electroweak G1 rows of data/msm-g1.json (the same gate
    tool on the EW records; m-sm/PLAN.md §5.1 item 6). They join the
    campaign's integrated configuration only when both campaigns timed the
    same engine (slice_revision): another engine would be a configuration of
    its own and stops the build. The EW rows are gated like the others since
    the final G1 retime (M-LIT-a0, m-final/PLAN.md §2.4 MF-RETIME; at M-SM
    they were indicative, [U5]): the gate tool's verdict stands."""
    path = DATA / EW_G1
    if not path.exists():
        return g1, set()
    ew = _load(path)
    if ew["slice_revision"][:8] != g1["slice_revision"][:8]:
        raise ValueError(
            f"{EW_G1} slice_revision {ew['slice_revision']} is not g1.json's"
            f" ({g1['slice_revision']}): the EW rows would be another configuration"
        )
    known = {p["key"] for p in g1["processes"]}
    procs = []
    for proc in ew["processes"]:
        if proc["key"] in known:
            raise ValueError(f"{EW_G1} processes[{proc['key']}]: in g1.json")
        procs.append(proc)
    return dict(g1, processes=g1["processes"] + procs), {p["key"] for p in procs}


def _ew_cells(rows: list[dict], keys: set[str], notes: dict) -> None:
    """The EW rows' registry attribution (milestone.json status_notes): the
    leading colour, which EW requests never support (typed refusal, by
    design); every source names msm-g1.json. Their gate rule is the gate
    tool's (gated since the final G1 retime, M-LIT-a0)."""
    for i, r in enumerate(rows):
        if r["key"] not in keys:
            continue
        note = notes.get(r["key"], {})
        src = f"milestone.json status_notes.notes[{r['key']}]"
        if "leading_colour" not in note:
            raise ValueError(f"{src}: an EW G1 row needs 'leading_colour'")
        if r["leading_colour"]["main"].get("status") == "not timed":
            r["leading_colour"]["main"] = {
                "status": "not supported",
                "reason": note["leading_colour"],
                "source": src,
            }
        text = re.sub(
            rf"(?<!msm-)g1\.json processes\[{re.escape(r['key'])}\]",
            f"{EW_G1} processes[{r['key']}]",
            json.dumps(r),
        )
        rows[i] = json.loads(text)


SIX = "2to6.json"
# The 2 -> 6 rows of Table 1 (M-FINAL item 1; data/2to6.json, from the
# mf-2to6 run records): one row per process with its full-colour and
# leading-colour records, in the data's order (a missing record stays
# absent). pyAmpliCol only (no provider exists at 2 -> 6): no ratio, no
# gate, every cell uncoloured; their engine is not loop's (stated once in
# the table).
SIX_NOT_DONE = ("not obtained", "not run", "not asserted", "in progress")


def _six_generation(r: dict, src: str) -> dict:
    """generate + plan export (Table 1's generation definition), then store,
    artifact and load of one 2 -> 6 record."""
    g, st = r["generation"], r["generation"]["stages"]
    return {
        "accuracy": r["accuracy"],
        "seconds": st["generate"]["s"] + st["export"]["s"],
        "peak_gib": max(st["generate"]["peak_gib"], st["export"]["peak_gib"]),
        "plan_mb": st["export"].get("plan_mb"),
        "store_s": st["store"]["s"],
        "store_peak_gib": st["store"]["peak_gib"],
        "artifact_gb": r["artifact"]["gb"],
        "load_s": r["load"]["s"],
        "load_peak_gib": r["load"]["peak_gib"],
        "families": r["structure"]["families"],
        "threads": g.get("threads"),
        "revision": g["revision"][:8],
        "source": f"{src} rows[{r['key']}].generation.stages, .artifact, .load",
    }


def _six_timing(r: dict, src: str, caveats: list[str]) -> dict:
    """The largest measured batch of one 2 -> 6 record (the other batches
    beside it); a record without a measured batch is 'not run' with the
    data's reason."""
    e = r["evaluation"]
    evals = r.get("evaluations", {})
    if e is None:
        why = "; ".join(
            f"B = {b}: {x.get('why') or x.get('status')}" for b, x in evals.items()
        )
        return {
            "status": "not run",
            "reason": why or "no timing record",
            "source": f"{src} rows[{r['key']}].evaluations",
        }
    rot = "copies" in e["timed"]
    # A run in swap (2to6.json row_caveats): its time is likely inflated.
    swap = any("swap" in c for c in caveats)
    blocks = e["timed"]["blocks"]
    other = {
        b: (
            {"seconds_per_point": x["s_per_point"], "peak_gib": x["peak_gib"]}
            if x.get("status") == "measured"
            else {"status": x.get("status"), "reason": x.get("why")}
        )
        for b, x in evals.items()
        if int(b) != e["B"]
    }
    return {
        "status": "measured",
        "accuracy": r["accuracy"],
        "seconds_per_point": e["s_per_point"],
        "batch": e["B"],
        "blocks": blocks,
        "points": e["timed"]["points"],
        "protocol": (
            f"one rotation block: {len(e['timed']['stream_indices'])} points x"
            f" {len(e['timed']['copies'])} copies"
            if rot
            else f"{blocks} block{'s' if blocks != 1 else ''} of {e['timed']['points_per_block']}"
        ),
        "colour_contraction": (e.get("colour_contraction") or {}).get("evaluated"),
        "peak_gib": r["table1"]["eval_peak_gib"],
        "stages": _split(e["stages_s_per_point"]),
        "other_batches": other,
        "revision": e["revision"][:8],
        **({"note": "ran partly in swap: time likely inflated"} if swap else {}),
        "source": f"{src} rows[{r['key']}].evaluation, .evaluations; row_caveats[{r['key']}]",
    }


def _six_checks(r: dict) -> list[dict]:
    """The internal checks of one 2 -> 6 record: status pass / fail / rescue
    case, or one of SIX_NOT_DONE with its reason; the largest value where
    one exists. The stored-checks run itself is not a check (its parts are)."""
    out = []
    acc = r["accuracy"].upper().replace("FULL", "FC")
    for name, c in r["checks"].items():
        if name == "stored_checks" and c["status"] == "done":
            continue
        x = {"check": name, "accuracy": acc, "status": c["status"], "value": None}
        if c["status"] in SIX_NOT_DONE:
            x["why"] = c.get("why")
            if name == "ward" and c.get("max_virtual_ratio_finite_single_double"):
                x["value"] = max(c["max_virtual_ratio_finite_single_double"])
        elif name == "double_pole":
            x.update(
                status=c["verdict"], value=c["max_deviation"], points=len(c["points"])
            )
        elif name == "stability":
            x.update(
                status="rescue case" if c["points_above_1e-5"] else "pass",
                value=c["max_estimate"],
                points=len(c["points"]),
                above=c["points_above_1e-5"],
            )
        elif name == "ward":
            x.update(
                status="pass" if c["passed"] else "fail",
                value=max(c["max_virtual_ratio_finite_single_double"]),
                double_double=c.get("double_double_virtual_ratio"),
            )
        elif name == "double_double":
            x.update(
                status="pass" if c["passed"] else "fail",
                value=c["binary64_true_error_finite_relative"],
                estimate=c["binary64"]["estimate_finite_relative"],
            )
        elif name == "catani":
            x.update(
                status="pass" if c["passed"] else "fail",
                value=c["max_single_deviation"],
                double=c["max_double_deviation"],
                double_double=c["max_double_double_deviation"],
            )
        elif name == "ngluon":
            dd = c.get("ngluon-dd")
            b64 = c.get("ngluon")
            x.update(
                status="pass" if c["passed"] else "fail",
                value=dd["max_relative"][0] if dd else b64["max_relative"][0],
                carrier="double-double" if dd else "binary64",
            )
        elif name == "rescue":
            x.update(status="done", value=c["count"], of=c["of"])
        out.append(x)
    return out


def _preliminary() -> dict | None:
    path = DATA / SIX
    if not path.exists():
        return None
    d = _load(path)
    src = f"data/{SIX}"
    by_process: dict = {}
    for r in d["rows"]:
        if r["generation"] is not None:
            by_process.setdefault(r["process"], {})[r["accuracy"]] = r
    rows = []
    for label, recs in by_process.items():
        fc, lc = recs.get("full"), recs.get("lc")
        lead = fc or lc
        legs = len(label.replace(">", "").split())
        row = {
            "key": _key(label),
            "label": label,
            "math": _math(label),
            "legs": legs,
            "outgoing": legs - 2,
            "corrections": lead["correction"],
            "particle_veto": lead["particle_veto"],
            "particle_veto_note": lead["particle_veto_note"],
            "families": {
                "fc": fc["structure"]["families"] if fc else None,
                "lc": lc["structure"]["families"] if lc else None,
            },
            "generation": {
                "main": _six_generation(lead, src),
                "lc": _six_generation(lc, src) if fc and lc else None,
            },
            "full_colour": _six_timing(fc, src, d["row_caveats"].get(fc["key"], []))
            if fc
            else {
                "status": "not run",
                "reason": "no full-colour record",
                "source": src,
            },
            "leading_colour": _six_timing(lc, src, d["row_caveats"].get(lc["key"], []))
            if lc
            else {
                "status": "not run",
                "reason": "no leading-colour record",
                "source": src,
            },
            "checks": (_six_checks(fc) if fc else []) + (_six_checks(lc) if lc else []),
            "caveats": [
                c for x in (fc, lc) if x for c in d["row_caveats"].get(x["key"], [])
            ],
            "gate": lead["table1"]["gate"],
        }
        rows.append(row)
    e = d["engine"]
    return {
        "name": "2->6",
        "status": d["status"],
        "engine": {
            "branch": e["branch"],
            "base": e["base"],
            "revision": e["revision"][:8],
            "one_engine": e["one_engine"],
            "engine_source_change_vs_base": e["engine_source_change_vs_base"],
            "native": e["native"]["directory"],
            "native_digest": e["native_digest_short"],
            "protocol": e["protocol"],
        },
        "stop": d["stop"]["text"],
        "global_caveats": d["global_caveats"],
        "not_obtained": d["not_obtained"],
        "source": f"{src} (scripts/build_2to6.py)",
        "rows": rows,
    }


# ------------------------------------------------- loop-induced table --
# The loop-induced summary table <tab:summary-li> (USER 2026-11-06 ~06:00;
# m-lit/PLAN.md §3.7 "Pushes"): data/summary-li.json, the equivalent of
# Table 1 for loop-induced |A_loop|^2, written from
#   data/milestone.json loop_induced  the row registry (hand-maintained):
#                         every process row of m-lit/PLAN.md §4.1 by
#                         multiplicity group, with its §4.1 ids, gate class
#                         and the package that serves it ("served_by");
#                         "landed" lists the serving packages integrated at
#                         this head; checked against lit-ref's manifest
#                         tools/loop_reference/li_campaign.json once it
#                         exists (LI_CAMPAIGN);
#   data/li-timing.json   pyAmpliCol's loop-induced timing and generation
#                         records (development records under the §5.1
#                         protocol until lit-perf's gate tool writes them):
#                         {"records": [{"key", "revision", "backend"
#                         ("tirust" | "ninjars": the effective backend),
#                         "requested"? ("auto" | "ninjars" | "tirust": the
#                         backend the timed calls requested, as the runtime
#                         resolves a call; with "effective" and "reason" as
#                         returned), "batch", "seconds_per_point" (median,
#                         finite part, one pinned thread, checks off; only a
#                         record that served every point of every block has
#                         one), "failed_points"? (per block, the points the
#                         call failed closed, plan_export.FailedPoints),
#                         "served_fraction"?, "failure_causes"? ({cause:
#                         failed points}), "whole_call_seconds_per_point"?
#                         (a call that failed points, timed whole: not a
#                         served-point time), "refused"? (a typed refusal of
#                         the request: no time), "missing"? (the row was not
#                         generated or timed: the measured reason, e.g. a
#                         generation beyond the 45-min rule with its
#                         progress; no time), "host", "generation":
#                         {"seconds" (generate + the exact helicity-zero
#                         filter + plan export), "probes_seconds" (the
#                         mandatory generation-time double-double probes,
#                         m-lit Q12), "peak_gib" (over all of them),
#                         "plan_mb"?}?, "native_build"?, "source", "gate"?
#                         (lit-perf: {"status", "ratio_to_limit", "band"})}]};
#   lit-ref's provider timings: the manifest tools/loop_reference/
#                         li_campaign.json, per reference run of a row's
#                         process ("madloop_process") its
#                         "provider_timing_records" (paths below
#                         tests/fixtures/loop/; the gate tool's providers
#                         format, median per point) and "unavailable"
#                         ({provider: reason}); MadLoop at its production
#                         card only (LI_MADLOOP_PRODUCTION; the OPP column
#                         belongs to the detailed sections);
#   data/lit.json         lit-val's validation figures: {"rows": {key:
#                         {"status", "references": {provider or "analytic":
#                         largest relative deviation}, "points", "note"?,
#                         "source"}}}.
# A file that does not exist yet reads as "pending" for every cell it would
# fill. The rules are Table 1's: the newest measurement of a row (by git
# ancestry of the record revisions, Recency), nothing estimated or
# extrapolated, a value without a record stays absent with an explicit
# marker; the cell is the batched B = 128 time per point of the record the
# backend "auto" serves at the row's newest revision (its effective backend
# labelled; records before the "requested" field: the default backend
# TIRust first, NinjaRS per amplitude labelled where only NinjaRS is timed),
# never a record with failed points; the other backend's B = 128 record is
# shown beside it with its served fraction and the recorded cause of its
# failed points (its time per point only when it served every point); the
# ratio to the fastest matched
# provider colours the cell (Table 1's colour map); generation is
# uncoloured; rows of four legs or fewer are reported (no gate); below the
# 5 ms rule a row is not gated; gate verdicts only from lit-perf's records
# (before them: "no verdict yet"). The generation cell is the full production
# `generate` cost: generate + the exact helicity-zero filter + plan export +
# the generation-time probes, which run for every loop-induced process (m-lit
# Q10, Q12; the probes' share is shown); a record without its probe time is
# "not recorded" (never a partial cost).
LI_TIMING = "li-timing.json"
LI_VALIDATION = "lit.json"
LI_CAMPAIGN = Path("tools") / "loop_reference" / "li_campaign.json"
# The manifest's fixture paths are relative to this directory.
LI_FIXTURES = Path("tests") / "fixtures" / "loop"
# MadLoop's loop-induced production card (PLAN §5.1/§5.2: COLLIER first,
# MLReductionLib 7|6|1): the summary's MadLoop time; other reduction orders
# (the 6|7|1 OPP column) are detailed-section columns.
LI_MADLOOP_PRODUCTION = "7|6|1"
LI_BACKENDS = {"tirust": "TIRust", "ninjars": "NinjaRS per amplitude"}
LI_REFERENCES = ("analytic", "madloop", "openloops", "recola")
LI_SHORT = {"analytic": "AN", **{k: SHORT[k] for k in PROVIDERS}}
# The serving package of each input file (the "pending" marker's owner).
LI_OWNERS = {
    LI_TIMING: "the row's serving package",
    str(LI_CAMPAIGN): "lit-ref",
    LI_VALIDATION: "lit-val",
}
LI_RULE = (
    "every row of the registry (milestone.json loop_induced, PLAN §4.1"
    " process rows) by multiplicity; the cell is the newest record's"
    " batched B = 128 time per point (git ancestry of the record"
    " revisions) of the backend 'auto' serves at that revision (its"
    " effective backend labelled; records without a request: the default"
    " backend TIRust first, NinjaRS per amplitude labelled where only"
    " NinjaRS is timed), never a record with failed points; the other"
    " backend beside it with its served fraction and the recorded cause of"
    " its failed points, its time only where it served every point; the"
    " ratio to"
    " the fastest matched provider (production mode) colours it; generation"
    " = the full production generate cost (generate + the exact"
    " helicity-zero filter + plan export + the mandatory generation-time"
    " probes, their share shown), uncoloured;"
    " every record names its host; four legs or fewer reported, below the"
    " 5 ms rule not"
    " gated, gate verdicts only from lit-perf's records; a row whose serving"
    " package has not landed, or whose input file does not exist yet, is"
    " pending; nothing estimated or extrapolated"
)


def _li_legs_word(process: str) -> str:
    """'g g > h' -> '2->1' (the gate rule's multiplicity words)."""
    initial, final = process.split(" > ")
    return f"{len(initial.split())}->{len(final.split())}"


def _li_registry(ms: dict) -> dict:
    """milestone.json loop_induced, checked: unique keys and ids, declared
    groups, gate classes and backends; four legs or fewer is exactly the
    reported class (the gate tool's multiplicity rule, PLAN §5.2), the EFT
    row (no process fixed yet) excepted."""
    reg = ms.get("loop_induced")
    if reg is None:
        raise ValueError("milestone.json has no loop_induced registry")
    keys, ids = set(), {}
    for row in reg["rows"]:
        src = f"milestone.json loop_induced.rows[{row['key']}]"
        if row["key"] in keys:
            raise ValueError(f"{src}: duplicate key")
        keys.add(row["key"])
        for i in row["ids"]:
            ids.setdefault(i, []).append(row["key"])
            if i in reg["validation_only"]["ids"]:
                raise ValueError(f"{src}: {i} is a validation-only id")
        if row["group"] not in reg["groups"]:
            raise ValueError(f"{src}: group {row['group']!r} is not declared")
        if row["gate_class"] not in reg["gate_classes"]:
            raise ValueError(f"{src}: gate class {row['gate_class']!r} unknown")
        if not row["backends"] or set(row["backends"]) - set(LI_BACKENDS):
            raise ValueError(f"{src}: backends {row['backends']}")
        if set(row["references"]) - set(LI_REFERENCES):
            raise ValueError(f"{src}: references {row['references']}")
        legs = row["legs"]
        if legs is None:
            if row["gate_class"] != "eft":
                raise ValueError(f"{src}: only the EFT row may leave legs open")
        elif (legs <= 4) != (row["gate_class"] == "reported"):
            raise ValueError(
                f"{src}: {legs} legs and gate class {row['gate_class']!r}"
                " (four legs or fewer is exactly 'reported', PLAN §5.2)"
            )
        elif row.get("process") and legs != len(
            row["process"].replace(">", "").split()
        ):
            raise ValueError(f"{src}: legs {legs} != the process's")
    if reg["default_backend"] not in LI_BACKENDS:
        raise ValueError(
            f"milestone.json loop_induced.default_backend {reg['default_backend']!r}"
        )
    unknown = set(reg["landed"]) - {r["served_by"] for r in reg["rows"]}
    if unknown:
        raise ValueError(
            f"milestone.json loop_induced.landed: {sorted(unknown)} serve no row"
        )
    return reg


def _li_norm(process: str) -> str:
    """A process string without order annotations or bracketed options."""
    text = re.sub(r"\[[^\]]*\]|\S+(?:<=|>=|==|=)\S+", " ", process)
    return " ".join(text.split())


def _li_manifest_ids(row_id: str) -> list[str]:
    """The ids of one manifest row: "LI-W1/L1/P1/C1/S1" (one row for the
    identity rows of PLAN §4.1) is LI-W1, LI-L1, LI-P1, LI-C1, LI-S1."""
    head, *rest = row_id.split("/")
    prefix = head.rsplit("-", 1)[0] + "-" if "-" in head else ""
    return [head, *(prefix + r for r in rest)]


def _li_listed(process: str, text: str) -> bool:
    """Whether a manifest row's process text lists ``process`` as an item
    of its own (delimited by , ; : ( or 'or' / 'vs'): "g g > h" is listed
    in "g g > h (t; t + b ...)", not in "g g > h g, ..."."""
    item = re.escape(process)
    pattern = rf"(?:^|[,;:(]\s*|\bor\s+){item}(?=\s*$|\s*[,;()]|\s+or\b|\s+vs\b)"
    return re.search(pattern, text) is not None


def _li_manifest(repo: Path) -> dict | None:
    """lit-ref's manifest by id: per manifest row carrying the id, its
    reference runs and its process text (normalised), with the number of
    manifest rows; None while it does not exist."""
    path = repo / LI_CAMPAIGN
    if not path.exists():
        return None
    rows = _load(path)["rows"]
    ids: dict[str, list[dict]] = {}
    for row in rows:
        text = row.get("processes") or row.get("process") or ""
        if isinstance(text, list):
            text = ", ".join(text)
        entry = {"row": row["row"], "runs": row.get("runs", []), "text": _li_norm(text)}
        for i in _li_manifest_ids(row["row"]):
            ids.setdefault(i, []).append(entry)
    return {"rows": len(rows), "ids": ids}


def _li_runs(entry: dict, process: str) -> list[dict]:
    """A manifest row's reference runs of ``process`` (normalised)."""
    return [
        r
        for r in entry["runs"]
        if r.get("madloop_process") and _li_norm(r["madloop_process"]) == process
    ]


def _li_campaign(reg: dict, manifest: dict | None) -> dict:
    """The registry against lit-ref's manifest (li_campaign.json), once it
    exists: every registry id is a manifest row (a row may carry several
    ids, ``_li_manifest_ids``) whose processes include the registry's
    process and alternative: a process of the row's reference runs
    (``runs[].madloop_process``) or an item of its ``processes`` text; and
    every manifest id is a registry row or validation-only. Absent:
    recorded as not checked yet."""
    out = {"file": str(LI_CAMPAIGN), "present": manifest is not None}
    out["checked"] = False
    if manifest is None:
        out["reason"] = "not written yet (lit-ref)"
        return out
    by_id = manifest["ids"]
    known = set(reg["validation_only"]["ids"])
    for row in reg["rows"]:
        for i in row["ids"]:
            known.add(i)
            if i not in by_id:
                raise ValueError(
                    f"loop_induced row {row['key']}: {i} is not in {LI_CAMPAIGN}"
                )
            for process in (row.get("process"), row.get("alternative")):
                if not process:
                    continue
                p = _li_norm(process)
                if not any(
                    _li_runs(e, p) or _li_listed(p, e["text"]) for e in by_id[i]
                ):
                    raise ValueError(
                        f"loop_induced row {row['key']}: {process!r} is not a"
                        f" process of {LI_CAMPAIGN} row {i}"
                    )
    extra = sorted(set(by_id) - known)
    if extra:
        raise ValueError(
            f"{LI_CAMPAIGN} rows {extra} are neither registry rows nor"
            " validation-only (milestone.json loop_induced)"
        )
    out.update(checked=True, rows=manifest["rows"], ids=len(by_id))
    return out


def _li_input(data: Path, name: str) -> dict | None:
    path = data / name
    return _load(path) if path.exists() else None


def _li_pending(what: str, reason: str) -> dict:
    return {"status": "pending", "reason": reason, "what": what}


def _li_providers(row: dict, manifest: dict | None, repo: Path) -> dict:
    """The row's provider entries from lit-ref's timing records
    (production mode: MadLoop at LI_MADLOOP_PRODUCTION), the reasons of
    the providers its runs record as unavailable, and the fastest matched
    one."""
    expected = [LI_SHORT[k] for k in row["references"] if k != "analytic"]
    if manifest is None:
        return {
            "status": "pending",
            "reason": f"provider timings: {LI_CAMPAIGN.name} not written yet (lit-ref)",
            "expected": expected,
        }
    runs, seen = [], set()
    if row.get("process"):
        p = _li_norm(row["process"])
        for i in row["ids"]:
            for e in manifest["ids"].get(i, ()):
                for r in _li_runs(e, p):
                    # A manifest row with several ids is met once per id.
                    if (e["row"], r.get("process")) not in seen:
                        seen.add((e["row"], r.get("process")))
                        runs.append(r)
    records = sorted({x for r in runs for x in r.get("provider_timing_records", ())})
    if not records and not any(r.get("unavailable") for r in runs):
        return {
            "status": "not run",
            "reason": f"no provider timing record of the row in {LI_CAMPAIGN.name}",
            "expected": expected,
        }
    providers, times, gens = {}, {}, {}
    for name in records:
        rec = _load(repo / LI_FIXTURES / name)
        for k, x in rec["providers"].items():
            if k not in PROVIDERS or "median_seconds_per_point" not in x:
                continue
            lib = (x.get("madloop_params") or {}).get("MLReductionLib")
            if lib is not None and lib != LI_MADLOOP_PRODUCTION:
                continue
            if k in providers:
                raise ValueError(
                    f"{LI_CAMPAIGN.name} {row['key']}: two production timings"
                    f" of {k} ({providers[k]['source']}, {name})"
                )
            t = x["median_seconds_per_point"]
            providers[k] = {"seconds_per_point": t, "source": f"{name} providers.{k}"}
            if lib is not None:
                providers[k]["setting"] = f"MLReductionLib {lib}"
            # The record's host: the table's provenance line.
            if rec.get("host") is not None:
                providers[k]["host"] = rec["host"]
            times[k] = t
            gen = (x.get("setup") or {}).get("generation_seconds")
            if gen is not None:
                gens[k] = gen
    for r in runs:
        for k, reason in (r.get("unavailable") or {}).items():
            if k in PROVIDERS and k not in providers:
                providers[k] = {
                    "status": "unavailable",
                    "reason": reason,
                    "source": f"{LI_CAMPAIGN.name} runs[{r.get('process')}]",
                }
    for k in row["references"]:
        if k in PROVIDERS and k not in providers:
            providers[k] = {"status": "not timed", "reason": "no production timing yet"}
    out = {"status": "recorded", "providers": providers, "fastest": None}
    # No provider can be matched: every reference provider is unavailable.
    out["unmatched"] = not times and all(
        x.get("status") == "unavailable" for x in providers.values()
    )
    if times:
        k = min(times, key=times.get)
        out["fastest"] = {"key": k, "name": NAMES[k], "seconds_per_point": times[k]}
    out["generation"] = gens
    if gens:
        k = min(gens, key=gens.get)
        out["fastest_generation"] = {"key": k, "name": NAMES[k], "seconds": gens[k]}
    return out


def _li_records(
    row: dict, timing: dict | None, recency: Recency, default: str
) -> list[dict]:
    """The row's timing records at its newest revision: the gate batch
    (B = 128) first, there the default backend (the registry's, TIRust)
    before the other, then the other batches (B = 1 is reported in the
    detailed sections, PLAN §5.1). One record per backend and batch at a
    revision: a repeat is ambiguous and refused."""
    if timing is None:
        return []
    recs = [r for r in timing["records"] if r["key"] == row["key"]]
    for r in recs:
        if not r.get("host"):
            raise ValueError(
                f"{LI_TIMING} record of {row['key']} at {r['revision'][:8]}"
                " names no host"
            )
        if r["backend"] not in row["backends"]:
            raise ValueError(
                f"{LI_TIMING} record of {row['key']}: backend {r['backend']}"
                f" is not one of the row's {row['backends']}"
            )
        _li_check_record(r)
    if not recs:
        return []
    newest = recency.newest_first([r["revision"][:8] for r in recs])[0]
    recs = [r for r in recs if r["revision"][:8] == newest]
    seen = set()
    for r in recs:
        cell = (r.get("requested", r["backend"]), r["backend"], int(r["batch"]))
        if cell in seen:
            raise ValueError(
                f"{LI_TIMING}: two records of {row['key']} at {newest} with"
                f" request {cell[0]}, backend {cell[1]} and B = {cell[2]}"
            )
        seen.add(cell)
    gate = int(GATE_BATCH)
    return sorted(
        recs,
        key=lambda r: (
            int(r["batch"]) != gate,
            r["backend"] != default,
            r["backend"],
            int(r["batch"]),
        ),
    )


def _li_check_record(r: dict) -> None:
    """A timing record's request and outcome are consistent: an explicit
    request is its own effective backend (never a silent switch); a
    record that failed points (``failed_points``, per block) or was refused
    carries no time per point (its call was timed whole: not a served-point
    time), and its served fraction is the one its failed points give."""

    src = f"{LI_TIMING} record of {r['key']} at {r['revision'][:8]}"
    requested = r.get("requested")
    if requested is not None:
        if requested != "auto" and requested not in LI_BACKENDS:
            raise ValueError(f"{src}: unknown request {requested!r}")
        if requested != "auto" and requested != r["backend"]:
            raise ValueError(
                f"{src}: {requested!r} was requested but {r['backend']!r} ran"
            )
    if r.get("effective", r["backend"]) != r["backend"]:
        raise ValueError(f"{src}: effective {r['effective']!r} is not its backend")
    failed = r.get("failed_points") or []
    unserved = r.get("refused") or r.get("missing")
    if (unserved or any(failed)) and "seconds_per_point" in r:
        raise ValueError(
            f"{src}: a refused, missing or failed call has no time per point"
        )
    if not unserved and not any(failed) and "seconds_per_point" not in r:
        raise ValueError(f"{src}: a served record without its time per point")
    if failed and "served_fraction" in r:
        fraction = 1 - sum(failed) / (int(r["batch"]) * len(failed))
        if abs(fraction - r["served_fraction"]) > 1e-12:
            raise ValueError(
                f"{src}: served fraction {r['served_fraction']} is not its"
                f" failed points' {fraction}"
            )


def _li_served(r: dict) -> bool:
    """Whether a timing record served every point of every block."""

    return "seconds_per_point" in r


def _li_main(batched: list[dict]) -> tuple[dict | None, dict | None]:
    """(the cell's record, the record that names the request's outcome)
    among the B = 128 records of a revision (``_li_records``' order): the
    record of the backend "auto" serves (``requested == "auto"``) when one
    was taken, else (records before the request field, or explicit
    requests only) the first served one, the default backend first; never
    a record with failed points or a refusal (None, with the "auto"
    record that failed or was refused)."""

    auto = [r for r in batched if r.get("requested") == "auto"]
    if auto:
        return (auto[0] if _li_served(auto[0]) else None), auto[0]
    served = [r for r in batched if _li_served(r)]
    return (served[0] if served else None), (served[0] if served else batched[0])


def _li_failed(r: dict) -> dict:
    """The outcome of a B = 128 record that did not serve every point: the
    refusal, or the points failed closed per block of the batch, the
    served fraction and the recorded causes (``failure_causes``; a call
    that failed points was timed whole and has no time per point)."""

    if r.get("refused"):
        return {"status": "refused", "reason": r["refused"], "label": "refused"}
    if r.get("missing"):
        # Not generated or timed: the measured reason (never an estimate).
        return {"status": "not run", "reason": r["missing"], "label": "not run"}
    failed = r["failed_points"]
    batch = int(r["batch"])
    causes = dict(r.get("failure_causes") or {})
    low, high = min(failed), max(failed)
    count = str(low) if low == high else f"{low}-{high}"
    label = (
        f"failed closed on every point ({batch}/{batch})"
        if low == batch
        else f"{count}/{batch} failed closed"
    )
    return {
        "status": "failed closed",
        "batch": batch,
        "blocks": len(failed),
        "failed_points": [low, high],
        "served_fraction": 1 - sum(failed) / (batch * len(failed)),
        "every_point": low == batch,
        "causes": causes,
        # The cell's words: the points failed closed per block of the batch
        # and the recorded causes.
        "label": ", ".join([label, *causes]),
    }


def _li_other(r: dict) -> dict:
    """The other backend's B = 128 record beside the cell: its request,
    its time per point only where it served every point, else its served
    fraction and causes (``_li_failed``)."""

    out = {
        "backend": r["backend"],
        "backend_label": LI_BACKENDS[r["backend"]],
        "requested": r.get("requested", r["backend"]),
    }
    if _li_served(r):
        out.update(status="served", served_fraction=1.0)
        out["seconds_per_point"] = r["seconds_per_point"]
    else:
        out.update(_li_failed(r))
    return out


def _li_gate(row: dict, t: float, rec: dict, prov: dict, rule: dict) -> dict:
    """The cell's gate rule: reported (four legs or fewer), the user's 5 ms
    rule, no matched provider (every reference unavailable), lit-perf's
    verdict, or no verdict yet (no provider time yet)."""
    if row["gate_class"] == "reported":
        return {
            "status": "reported",
            "label": f"no gate ({_li_legs_word(row['process'])})",
        }
    if t < rule["below_seconds_per_point"]:
        return {
            "status": rule["verdict"],
            "label": rule["short"],
            "rule": rule["label"],
            "rule_source": "milestone.json gate_decisions.threshold_rule"
            f" ({rule['source']})",
        }
    if prov.get("status") == "recorded" and prov["unmatched"]:
        return {"status": "no gate", "label": "no matched provider: no gate"}
    g = rec.get("gate")
    if g is not None:
        status = {"inconclusive": "open"}.get(g["status"], g["status"])
        if status not in ("pass", "fail", "open"):
            raise ValueError(f"{LI_TIMING} {row['key']}: gate status {g['status']!r}")
        return {
            "status": status,
            "ratio_to_limit": g["ratio_to_limit"],
            "band": g["band"],
            "source": f"{rec['source']} (lit-perf gate tool)",
        }
    if prov.get("fastest") is None:
        return {"status": "no verdict", "label": "no provider time yet"}
    return {"status": "no verdict", "label": "no verdict yet"}


def _li_cells(
    row: dict,
    landed: bool,
    files: dict,
    prov: dict,
    recency: Recency,
    rule: dict,
    default: str,
) -> dict:
    """The row's process, generation and timing cells (``prov``: its
    provider entries, ``_li_providers``)."""
    pending_pkg = f"served by {row['served_by']} (not landed at this head)"
    out = {"providers": prov}
    val = files[LI_VALIDATION]
    if val is None:
        out["validation"] = _li_pending(
            "validation", f"{LI_VALIDATION} not written yet (lit-val)"
        )
    elif row["key"] not in val["rows"]:
        out["validation"] = {
            "status": "not run",
            "reason": f"no record in {LI_VALIDATION}",
        }
    else:
        v = val["rows"][row["key"]]
        refs = {k: x for k, x in v["references"].items() if k in LI_SHORT}
        out["validation"] = {
            "status": v["status"],
            "references": [
                {"key": k, "short": LI_SHORT[k], "max_relative": refs[k]}
                for k in sorted(refs, key=refs.get)
            ],
            "points": v.get("points"),
            "note": v.get("note"),
            "source": f"{LI_VALIDATION} rows[{row['key']}]",
        }
    if not landed:
        out["generation"] = _li_pending("generation", pending_pkg)
        out["timing"] = _li_pending("timing", pending_pkg)
        return out
    if files[LI_TIMING] is None:
        why = f"{LI_TIMING} not written yet ({row['served_by']})"
        out["generation"] = _li_pending("generation", why)
        out["timing"] = _li_pending("timing", why)
        return out
    recs = _li_records(row, files[LI_TIMING], recency, default)
    if not recs:
        missing = {
            "status": "not run",
            "reason": f"no record of the row in {LI_TIMING}",
        }
        out["generation"], out["timing"] = dict(missing), dict(missing)
        return out
    gate = int(GATE_BATCH)
    batched = [r for r in recs if int(r["batch"]) == gate]
    main, named = _li_main(batched) if batched else (recs[0], recs[0])
    first = main or named
    at = f"{row['key']}, {first['backend']}, {first['revision'][:8]}"
    src = f"{LI_TIMING} records[{at}]"
    gen = first.get("generation")
    if gen is None and first.get("missing"):
        out["generation"] = {"status": "not run", "reason": first["missing"]}
    elif gen is None:
        out["generation"] = {
            "status": "not recorded",
            "reason": f"{src} has no generation",
        }
    elif gen.get("probes_seconds") is None:
        # The probes are part of every loop-induced generation (m-lit Q12):
        # without their time the record holds no full production cost.
        out["generation"] = {
            "status": "not recorded",
            "reason": f"{src} has no generation-time probe time",
        }
    else:
        # The full production `generate` cost: generate + plan export + the
        # mandatory generation-time probes (their share shown).
        total = gen["seconds"] + gen["probes_seconds"]
        out["generation"] = {
            "status": "measured",
            "seconds": total,
            "generate_seconds": gen["seconds"],
            "probes_seconds": gen["probes_seconds"],
            "probe_share": gen["probes_seconds"] / total if total else 0.0,
            "peak_gib": gen["peak_gib"],
            "plan_mb": gen.get("plan_mb"),
            "revision": first["revision"][:8],
            "host": first["host"],
            "source": f"{src}.generation",
        }
        fg = prov.get("fastest_generation")
        if fg is not None:
            out["generation"]["ratio_to_fastest"] = total / fg["seconds"]
    if not batched:
        # No B = 128 record at the newest revision (Table 1's rule): no
        # batched cell, the batches timed named.
        timed = sorted({int(r["batch"]) for r in recs})
        out["timing"] = {
            "status": _no_gate_batch({"batches": timed}),
            "reason": f"timed B = {', '.join(map(str, timed))} only",
            "timed_batches": timed,
            "revision": first["revision"][:8],
            "source": src,
        }
        return out
    if main is None:
        # The request's record failed points or was refused: never a cell
        # (status "failed closed" or "refused", with its fraction, causes or
        # reason).
        out["timing"] = {
            **_li_failed(named),
            "requested": named.get("requested", named["backend"]),
            "backend": named["backend"],
            "backend_label": LI_BACKENDS[named["backend"]],
            "revision": named["revision"][:8],
            "source": src,
        }
        return out
    t = main["seconds_per_point"]
    cell = {
        "status": "measured",
        "batch": int(main["batch"]),
        "seconds_per_point": t,
        "backend": main["backend"],
        "backend_label": LI_BACKENDS[main["backend"]],
        "default_backend": main["backend"] == default,
        "revision": main["revision"][:8],
        "native_build": main.get("native_build"),
        "native_digest": main.get("native_digest"),
        "host": main["host"],
        "source": src,
    }
    if "requested" in main:
        # The request as the runtime resolved it (requested, reason).
        cell["requested"] = main["requested"]
        cell["reason"] = main.get("reason")
    other = [r for r in batched if r["backend"] != main["backend"]]
    if other:
        # An explicit request of the other backend before an "auto" one.
        other.sort(key=lambda r: r.get("requested") == "auto")
        cell["other_backend"] = _li_other(other[0])
    fastest = prov.get("fastest")
    if fastest is not None:
        cell["ratio_to_fastest"] = t / fastest["seconds_per_point"]
    cell["gate"] = _li_gate(row, t, main, prov, rule)
    out["timing"] = cell
    return out


def build_loop_induced(
    ms: dict, recency: Recency, data: Path = DATA, repo: Path = REPO
) -> dict:
    """data/summary-li.json: the loop-induced summary table."""
    reg = _li_registry(ms)
    manifest = _li_manifest(repo)
    campaign = _li_campaign(reg, manifest)
    names = (LI_TIMING, LI_VALIDATION)
    files = {n: _li_input(data, n) for n in names}
    rule = ms["gate_decisions"]["threshold_rule"]
    groups = []
    for name in reg["groups"]:
        rows = []
        for row in (r for r in reg["rows"] if r["group"] == name):
            landed = row["served_by"] in reg["landed"]
            rows.append(
                {
                    "key": row["key"],
                    "process": row.get("process"),
                    "math": _math(row["process"]) if row.get("process") else None,
                    "label": row.get("label") or row.get("process"),
                    "alternative": row.get("alternative"),
                    "ids": row["ids"],
                    "legs": row["legs"],
                    "corrections": row["corrections"],
                    "gate_class": row["gate_class"],
                    "backends": [LI_BACKENDS[b] for b in row["backends"]],
                    "references": [LI_SHORT[k] for k in row["references"]],
                    "served_by": row["served_by"],
                    "landed": landed,
                    "note": row.get("note"),
                    **_li_cells(
                        row,
                        landed,
                        files,
                        _li_providers(row, manifest, repo),
                        recency,
                        rule,
                        reg["default_backend"],
                    ),
                }
            )
        if rows:
            groups.append({"name": name, "rows": rows})
    return {
        "what": (
            "the loop-induced summary table <tab:summary-li> of"
            " docs/performance_reports/loop/benchmarks.typ, written by"
            " scripts/build_summary.py (build_loop_induced); do not edit by hand"
        ),
        "meta": {
            "date": ms["date"],
            "engine_on_loop": ms["engine_revision"],
            # The engine's native build (name, digest): the provenance line
            # while no record of its own names one.
            "native_build_on_loop": {
                k: (ms.get("native_build") or {}).get(k) for k in ("name", "digest")
            },
            "default_backend": LI_BACKENDS[reg["default_backend"]],
            "gate_batch": int(GATE_BATCH),
            "threshold_rule": rule,
            "gate_classes": reg["gate_classes"],
            "landed": reg["landed"],
            "rule": LI_RULE,
            "registry": f"milestone.json loop_induced ({reg['source']})",
            "inputs": {
                LI_TIMING: {
                    "file": f"data/{LI_TIMING}",
                    "present": files[LI_TIMING] is not None,
                    "owner": LI_OWNERS[LI_TIMING],
                },
                "providers": {
                    "file": f"{LI_CAMPAIGN} (provider_timing_records)",
                    "present": manifest is not None,
                    "owner": LI_OWNERS[str(LI_CAMPAIGN)],
                },
                LI_VALIDATION: {
                    "file": f"data/{LI_VALIDATION}",
                    "present": files[LI_VALIDATION] is not None,
                    "owner": LI_OWNERS[LI_VALIDATION],
                },
            },
            "campaign": campaign,
            "validation_only": reg["validation_only"],
        },
        "groups": groups,
    }


# Figure 1's loop-induced rows (USER 2026-11-07 ~10:40, m-lit USER-NOTES:
# "the loop-induced processes should eventually be added to the progress bar
# summary with diamond markers (Figure. 1)").
LI_FIGURE_RULE = (
    "every row of the loop-induced table with a measured batched (B = 128)"
    " pyAmpliCol time and a matched provider time (its ratio to the fastest"
    " provider), in the table's order, drawn as a diamond on Figure 1's time"
    " axis beside Table 1's rows: the providers' production times, and the"
    " gate limit where the row is gated (2->3 upward: MadLoop's time and the"
    " gate factor times each other matched provider's, the smallest; grey"
    " below the 5 ms rule); the other rows are not drawn, counted by reason"
)
LI_NO_TIME = "no pyAmpliCol time at B = 128"
LI_NO_PROVIDER = "no matched provider time"


def li_figure(loop_induced: dict, factor: float) -> dict:
    """summary-li.json "figure": Figure 1's loop-induced rows (LI_FIGURE_RULE)
    from the table's own cells (build_loop_induced), nothing else read;
    ``factor``: the gate factor of OpenLoops and Recola (g1.json, Table 1's)."""
    rows, missing = [], {LI_NO_TIME: [], LI_NO_PROVIDER: []}
    for group in loop_induced["groups"]:
        for r in group["rows"]:
            t = r["timing"]
            if t.get("status") != "measured":
                missing[LI_NO_TIME].append(r["key"])
                continue
            if "ratio_to_fastest" not in t:
                missing[LI_NO_PROVIDER].append(r["key"])
                continue
            prov = r["providers"]
            timed = {
                k: x["seconds_per_point"]
                for k, x in prov["providers"].items()
                if "seconds_per_point" in x
            }
            limit = None
            if r["gate_class"] != "reported":
                limits = [
                    ((1.0 if k == "madloop" else factor) * s, NAMES[k])
                    for k, s in timed.items()
                ]
                seconds, binding = min(limits)
                limit = {"seconds": seconds, "binding": binding}
            rows.append(
                {
                    "key": r["key"],
                    "group": group["name"],
                    "math": r["math"],
                    "corrections": r["corrections"],
                    "seconds_per_point": t["seconds_per_point"],
                    "backend_label": t["backend_label"],
                    "ratio_to_fastest": t["ratio_to_fastest"],
                    "providers": timed,
                    "fastest": prov["fastest"]["key"],
                    "limit": limit,
                    "gate": t["gate"],
                    "source": f"groups[{group['name']}].rows[{r['key']}].timing",
                }
            )
    return {
        "rule": LI_FIGURE_RULE,
        "gate_factor": factor,
        "rows": rows,
        "not_drawn": {k: v for k, v in missing.items() if v},
    }


def build() -> tuple[dict, Recency]:
    """summary.json, and the recency order it used (for the build log)."""
    g1, ew_keys = _with_ew_rows(_load(DATA / "g1.json"))
    ms = _load(DATA / "milestone.json")
    meas = _load(DATA / "measured.json")
    specs = {
        p["name"]: p
        for p in _load(REPO / "tools/loop_benchmark/processes.json")["processes"]
    }
    decisions = ms["gate_decisions"]
    recency = Recency(REPO, ms["ancestry"])
    records = {
        key: _record_cells(ms, meas, key)
        for key in meas["required_native"]["processes"]
    }
    rows = _g1_rows(g1, specs, decisions, records, recency)
    _accept(rows, g1, ms.get("validation_decisions"))
    _no_matched_provider(rows, ms, meas, g1)
    rows += _required_rows(
        ms, meas, {r["key"] for r in rows}, g1["gate_factor"], records, recency
    )
    notes = ms.get("status_notes", {}).get("notes", {})
    _ew_cells(rows, ew_keys, notes)
    for r in rows:
        note = notes.get(r["key"], {})
        r.setdefault("row_status", None)
        main = (
            r["generation"]["main"],
            r["full_colour"]["main"],
            r["leading_colour"]["main"],
        )
        # A refusal of the newest configuration: the registry's short
        # attribution where it has one (else the error class is printed).
        reason = note.get("refused")
        for cell in main:
            if cell.get("status") == "refused" and "reason" not in cell and reason:
                cell["reason"] = reason
        gen = r["generation"]["main"]
        if r["row_status"] is None and gen.get("status") == "refused":
            r["row_status"] = {
                "status": "refused",
                "reason": gen.get("reason", gen.get("error")),
                "configuration": gen["configuration"],
                "source": f"{gen['source']} (generation_error {gen['error']});"
                f" milestone.json status_notes.notes[{r['key']}]",
            }
        if "madloop" in note:
            r["full_colour"]["madloop_note"] = note["madloop"]
    _cell_notes(rows, ms.get("cell_notes"))
    # Increasing multiplicity, then increasing colour complexity (number of
    # gluons) within a multiplicity; stable otherwise.
    rows.sort(key=lambda r: (r["outgoing"], r["label"].split().count("g")))

    groups = []
    for r in rows:
        name = f"2->{r['outgoing']}"
        if not groups or groups[-1]["name"] != name:
            groups.append({"name": name, "rows": []})
        groups[-1]["rows"].append(r)
    configurations = _configurations(g1, ms, meas, rows, recency)
    if ew_keys:
        configurations["integrated"]["source"] += (
            f"; the EW rows of {EW_G1} ({', '.join(sorted(ew_keys))}, same engine)"
        )
    summary = {
        "what": (
            "Table 1 of docs/performance_reports/loop/benchmarks.typ, written by"
            " scripts/build_summary.py; do not edit by hand"
        ),
        "meta": {
            "date": g1["date"],
            "host": g1["host"],
            "gate_factor": g1["gate_factor"],
            "engine_on_loop": ms["engine_revision"],
            "native_build_on_loop": ms["native_build"]["name"],
            "main_rule": {
                "rule": MAIN_RULE,
                "validation_rule": VALIDATION_RULE,
                "generation_rule": GENERATION_RULE,
                "kinds": list(KIND_ORDER),
                # Every recency fact the rule used: the newer and older
                # configuration with its revision, and the basis.
                "recency": recency.facts(),
                "source": "scripts/build_summary.py MAIN_RULE,"
                " VALIDATION_RULE, GENERATION_RULE, Recency; ancestry:"
                " milestone.json ancestry",
            },
            "configurations": configurations,
            "gate_decisions": decisions,
            "validation_decisions": ms.get("validation_decisions"),
        },
        "groups": groups,
    }
    six = _preliminary()
    if six is not None:
        summary["preliminary"] = six
    return summary, recency


def report_meta(summary: dict, loop_induced: dict, recency: Recency, ms: dict) -> dict:
    """The report's own line (its running header and page-1 subtitle): its
    date (milestone.json date) and its newest measured engine revision, the
    newest (git ancestry, Recency) of the revisions Table 1's and Table 2's
    cells show, beside each table's own newest revision, so that no reader
    takes the whole report to be at Table 1's configuration. The 2 -> 6 rows
    (another engine, labelled in Table 1) take no part."""

    def newest(revisions: list[str]) -> str | None:
        found = sorted({r[:8] for r in revisions if r})
        return recency.newest_first(found)[0] if found else None

    table1 = [
        r[kind]["main"].get("revision")
        for g in summary["groups"]
        for r in g["rows"]
        for kind in ("generation", "full_colour", "leading_colour")
        if r[kind]["main"].get("status") == "measured"
    ]
    table2 = [
        r[cell].get("revision")
        for g in loop_induced["groups"]
        for r in g["rows"]
        for cell in ("generation", "timing")
        if r[cell].get("status") == "measured"
    ]
    one, two = newest(table1), newest(table2)
    return {
        "date": ms["date"],
        "head": newest([x for x in (one, two) if x]),
        "table1": one,
        "table2": two,
        "source": "milestone.json date; the newest revision of the measured"
        " cells of summary.json and summary-li.json (git ancestry:"
        " milestone.json ancestry)",
    }


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA / "summary.json"
    out_li = Path(sys.argv[2]) if len(sys.argv) > 2 else DATA / "summary-li.json"
    summary, recency = build()
    ms = _load(DATA / "milestone.json")
    loop_induced = build_loop_induced(ms, recency)
    loop_induced["figure"] = li_figure(loop_induced, summary["meta"]["gate_factor"])
    summary["meta"]["report"] = report_meta(summary, loop_induced, recency, ms)
    out.write_text(json.dumps(summary, indent=1) + "\n")
    out_li.write_text(json.dumps(loop_induced, indent=1) + "\n")
    print(
        f"recency: {len(recency.facts())} facts used;"
        f" {recency.checked} ancestry queries checked against git",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
