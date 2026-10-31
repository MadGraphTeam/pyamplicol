# SPDX-License-Identifier: 0BSD
"""Write data/summary.json, the data of Table 1 of the live loop report.

Usage: python scripts/build_summary.py [output]

Every value of Table 1 (times, memory, sizes, ratios, gate verdicts, stage
shares, validation figures) is assembled here from the report's data files,
and every entry names its source:

- data/g1.json            gate-G1 campaign (python -m tools.loop_benchmark gate)
- data/msm-g1.json        the electroweak G1 rows (the same gate tool on the EW
                          records), part of g1.json's integrated configuration
                          when both timed the same engine; indicative at M-SM
                          (no gate: m-sm/PLAN.md [U5]), their gate rule and
                          leading-colour status from milestone.json
                          status_notes (_with_ew_rows, _ew_cells)
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
            "date": g1["date"],
            "inputs": _side_inputs(g1, side["development"]),
            "main_rows": main_rows("development"),
            "main_cells": main_cells("development"),
            "source": "g1.json native_revision, native_commit, native_build, date;"
            " label, integration and branch: milestone.json development",
        }
    out["integrated"] = {
        "kind": "g1",
        "label": "on loop",
        "revision": g1["slice_revision"],
        "lc_revision": g1.get("slice_lc_revision"),
        "native_build": g1.get("slice_build"),
        "date": g1["date"],
        "inputs": _side_inputs(g1, side["integrated"]),
        "main_rows": main_rows("integrated"),
        "main_cells": main_cells("integrated"),
        "source": "g1.json slice_revision, slice_lc_revision, slice_build, date",
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
    its own and stops the build. At M-SM the EW rows are indicative (no gate,
    [U5]: the EW speed gate binds in M-FINAL): a gated EW row stops it too."""
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
        if proc["key"] in known or proc["gated"]:
            raise ValueError(f"{EW_G1} processes[{proc['key']}]: in g1.json or gated")
        procs.append(proc)
    return dict(g1, processes=g1["processes"] + procs), {p["key"] for p in procs}


def _ew_cells(rows: list[dict], keys: set[str], notes: dict) -> None:
    """The EW rows' registry attributions (milestone.json status_notes): the
    full-colour cell's gate rule (indicative, not gated) and the leading
    colour, which EW requests never support (typed refusal, by design); every
    source names msm-g1.json."""
    for i, r in enumerate(rows):
        if r["key"] not in keys:
            continue
        note = notes.get(r["key"], {})
        src = f"milestone.json status_notes.notes[{r['key']}]"
        if "gate" not in note or "leading_colour" not in note:
            raise ValueError(f"{src}: an EW G1 row needs 'gate' and 'leading_colour'")
        r["full_colour"].update(
            gate_rule=note["gate"],
            gate_rule_reason=note.get("gate_reason"),
            gate_rule_source=src,
        )
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
    return summary, recency


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA / "summary.json"
    summary, recency = build()
    out.write_text(json.dumps(summary, indent=1) + "\n")
    print(
        f"recency: {len(recency.facts())} facts used;"
        f" {recency.checked} ancestry queries checked against git",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
