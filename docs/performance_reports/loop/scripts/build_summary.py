# SPDX-License-Identifier: 0BSD
"""Write data/summary.json, the data of Table 1 of the live loop report.

Usage: python scripts/build_summary.py [output]

Every value of Table 1 (times, memory, sizes, ratios, gate verdicts, stage
shares, validation figures) is assembled here from the report's data files,
and every entry names its source:

- data/g1.json            gate-G1 campaign (python -m tools.loop_benchmark gate)
- data/measured.json      development run records (scripts/collect_milestone.py):
                          the WP3.1 native validations of the required set and
                          the provider reference runs' records (generation,
                          MadLoop's production-build times, Recola's protocol
                          run)
- data/milestone.json     hand-maintained registry: the required set, the
                          OpenLoops and Recola production references of the
                          seven-leg rows (DESIGN 1.3 Table 1b, as text: the
                          gate limit is computed here), the branch of the
                          development revisions, user gate decisions and short
                          status notes
- tools/loop_benchmark/processes.json  the G1 process specifications

Main-configuration rule (MAIN_ORDER below): every cell of Table 1 and Figure
1 shows the most recent measured configuration of its row, and summary.json
records that configuration and its source with the cell.

Nothing is estimated or extrapolated: a value without a record stays absent
(null) and Table 1 prints an explicit marker. The report renders summary.json
as is; re-run this script after regenerating any input.
"""

from __future__ import annotations

import json
import re
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
# When several configurations of one side qualify, the engine's production
# per-point inputs come first.
INPUTS_PREFERENCE = ("native", "python")

# Main-configuration rule (user request of 2026-10-24: Table 1 shows only the
# most recent measurements). Every cell of a row (generation, validation, full
# colour, leading colour) shows the MOST RECENT configuration that measured
# it. The candidates, newest first:
#   rows with a G1 record (data/g1.json):
#     development          the campaign's development side (gate --meta
#                          native_revision, native_commit): work ahead of
#                          loop, being integrated into it;
#     integrated           the campaign's integrated side (--meta
#                          slice_revision, slice_lc_revision): the engine on
#                          loop;
#   rows without one (the 2 -> 5 set until measure-g1-7leg times it):
#     development_records  the development branch's native validation records
#                          (measured.json required_native): generation and
#                          validation, no batched timing ("pending");
#     registry             milestone.json status_notes: a refusal attributed
#                          to loop, or a capability nobody has started.
# A cell takes the newest candidate that measured it; if none did, the status
# of the newest candidate with a record of the row (refused, not timed, not
# batched, pending, not started). "refused" therefore appears only where the
# most recent configuration refuses. At the next milestone (G-int integrated,
# G1 re-measured on loop, so the campaign has no development side, or only a
# newer one) loop's configuration becomes the main value without code
# changes; rows timed by a later G1 campaign leave the records' kind.
MAIN_ORDER = {
    "g1": ("development", "integrated"),
    "records": ("development_records", "registry"),
}
MAIN_RULE = (
    "every cell shows the most recent configuration that measured it"
    " (G1 rows: development side, then integrated; other rows: the"
    " development validation records, then the registry); without a"
    " measurement, the status of the newest configuration with a record of"
    " the row"
)

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
    order = ("inputs", "numerator", "scatter", "ninjars", "masters", "glue")
    return {k: out[k] for k in order}


def _largest_batch(cfg: dict | None) -> str | None:
    if not cfg or not cfg.get("batches"):
        return None
    sizes = [int(b) for b in cfg["batches"] if int(b) > 1]
    return str(max(sizes)) if sizes else None


def _provider_runtime(proc: dict) -> dict:
    out = {}
    for name in PROVIDERS:
        rec = (proc.get("providers") or {}).get(name)
        if rec is None:
            out[name] = {"status": "not run"}
        elif "unavailable" in rec:
            out[name] = {"status": "unavailable", "reason": rec["unavailable"]}
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
    return {
        "providers": out,
        "fastest": None
        if fastest is None
        else {
            "name": NAMES[fastest[0]],
            "key": fastest[0],
            "seconds_per_point": fastest[1],
        },
    }


def _provider_generation_g1(proc: dict) -> dict:
    out = {}
    for name in PROVIDERS:
        rec = (proc.get("providers") or {}).get(name)
        if rec is None or "unavailable" in rec:
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
    batch = _largest_batch(cfg)
    if batch is None:
        sizes = sorted(int(b) for b in cfg["batches"])
        return {
            "status": "not batched",
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
        "source": f"{source}.batches['{batch}']",
    }
    if fastest is not None:
        out["ratio_to_fastest"] = t / fastest["seconds_per_point"]
    gate = rec.get("gate", {})
    if "ratio_to_binding_limit" in gate:
        measured = {"inconclusive": "open"}.get(gate["status"], gate["status"])
        out["gate"] = {
            "status": measured,
            "ratio_to_limit": gate["ratio_to_binding_limit"],
            "band": gate["band_to_binding_limit"],
            "binding": NAMES[gate["binding_provider"]],
            "limit_seconds": gate["binding_limit"],
        }
        d = _decision(decisions, proc["key"], batch, gate["status"])
        if d is not None:
            out["gate"].update(
                status=d["verdict"],
                measured_status=measured,
                decision=d["label"],
                decision_reason=d["reason"],
                decision_source="milestone.json gate_decisions"
                f" ({decisions['source']})",
            )
    return out


def _adopted_schedule(proc: dict, name: str | None, batch: str) -> dict | None:
    """The schedule G1 adopted for a configuration's class where it is not
    the default protocol's B (g1.json schedules, adopt_m), timed at the same
    batch: shown next to the schedule-B value, which stays the main one."""
    if name is None:
        return None
    for s in proc.get("schedules", []):
        if s["configuration"] != name or not s["adopt_m"]:
            continue
        alt = proc["pyamplicol"].get(f"{name}/M")
        rec = (alt or {}).get("batches", {}).get(batch)
        if rec is None:
            return None
        return {
            "schedule": "M",
            "seconds_per_point": rec["median_seconds_per_point"],
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
    batch = _largest_batch(lc)
    if batch is None:
        return {"status": "not batched", "source": source}
    t = lc["batches"][batch]["median_seconds_per_point"]
    out = {
        "status": "measured",
        "batch": int(batch),
        "seconds_per_point": t,
        "schedule": lc["schedule"],
        "families": (lc.get("structure") or {}).get("families"),
        "inputs": lc["inputs"],
        "revision": lc["revision"][:8],
        "source": f"{source}.batches['{batch}']",
    }
    f = (fc or {}).get("batches", {}).get(batch)
    if f is not None:
        out["fc_seconds_per_point"] = f["median_seconds_per_point"]
        out["lc_over_fc"] = t / f["median_seconds_per_point"]
    adopted = _adopted_schedule(proc, name, batch)
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
        "source": f"{source}.values_vs_providers",
    }
    # The worst point re-evaluated with the stability checks: binary64
    # estimate E and the double-double value's deviation from the closest
    # provider, only if the campaign re-evaluated it in the validated
    # configuration itself (another configuration's estimate is not its own).
    rows = {
        (r["index"], r["arithmetic"]): r
        for r in proc.get("stability", [])
        if r["configuration"] == checked
    }
    b64 = rows.get((worst["worst_point"], "double"))
    dd = rows.get((worst["worst_point"], "double-double"))
    if b64 is not None:
        out["worst_point"] = {
            "index": worst["worst_point"],
            "estimate": b64["estimate"],
            "within_estimate": b64["estimate"] >= worst["max_finite"],
            "dd_closest": None
            if dd is None
            else min(dd["deviation_vs_providers"].values()),
            "source": f"g1.json processes[{proc['key']}].stability ({checked})",
        }
    return out


def _meta_revisions(g1: dict, *keys: str) -> set[str]:
    return {g1[k][:8] for k in keys if g1.get(k)}


def _roles(g1: dict) -> tuple[set[str], set[str], set[str]]:
    """The campaign's two sides, from its own metadata (the gate CLI's --meta
    keys): the integrated configuration (slice_revision, slice_lc_revision,
    and any revision recorded on the same branch, e.g. a refusal recorded
    earlier) and an optional development one (native_revision,
    native_commit; absent, equal to the integrated revision or not timed
    once the development work is integrated). A configuration on neither
    side is not shown."""
    integrated = _meta_revisions(g1, "slice_revision", "slice_lc_revision")
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


def _newest(cells: list[tuple[str, dict | None]]) -> dict:
    """The main-configuration rule for one cell: the newest candidate that
    measured it, else the status of the newest candidate with a record of
    the row (cells are (configuration, cell or None), newest first). The
    chosen cell names its configuration; 'considered' lists every
    candidate's status in order, so the choice can be audited."""
    considered = [
        {"configuration": cid, "status": "no record" if c is None else c["status"]}
        for cid, c in cells
    ]
    chosen = next(
        ((cid, c) for cid, c in cells if c is not None and c["status"] == "measured"),
        None,
    )
    if chosen is None:
        chosen = next(((cid, c) for cid, c in cells if c is not None), None)
    if chosen is None:
        return {
            "status": "not measured",
            "configuration": None,
            "considered": considered,
        }
    cid, cell = chosen
    return {**cell, "configuration": cid, "considered": considered}


def _families(pairs: dict, main: dict, order: tuple[str, ...]) -> int | None:
    """Loop families: the configuration of the main full-colour (LC) value,
    else the newest one that recorded them."""
    for cid in (main.get("configuration"), *order):
        cfg = pairs.get(cid, (None, None))[1]
        count = ((cfg or {}).get("structure") or {}).get("families")
        if count is not None:
            return count
    return None


def _g1_rows(g1: dict, specs: dict, decisions: dict) -> list[dict]:
    integrated, dev_revs, branches = _roles(g1)

    def is_integrated(cfg: dict) -> bool:
        rev = cfg["revision"][:8]
        return rev not in dev_revs and (rev in integrated or cfg["branch"] in branches)

    def is_dev(cfg: dict) -> bool:
        return cfg["revision"][:8] in dev_revs

    side = {"development": is_dev, "integrated": is_integrated}
    order = MAIN_ORDER["g1"]
    rows = []
    for proc in g1["processes"]:
        key = proc["key"]
        base = f"g1.json processes[{key}].pyamplicol"
        cfgs = proc["pyamplicol"]
        # Per configuration (newest first): its full-colour and LC entries.
        fc = {cid: _pick(cfgs, side[cid], "full") for cid in order}
        lc = {cid: _pick(cfgs, side[cid], "lc") for cid in order}
        runtime = _provider_runtime(proc)
        fastest = runtime["fastest"]
        gens = _provider_generation_g1(proc)
        gen_fastest = _fastest_generation(gens)
        gen = _newest(
            [
                (cid, _generation_of(fc[cid][1], f"{base}['{fc[cid][0]}'].generation"))
                for cid in order
            ]
        )
        if gen["status"] == "measured" and gen_fastest is not None:
            gen["ratio_to_fastest"] = gen["seconds"] / gen_fastest["seconds"]
        fc_main = _newest(
            [
                (
                    cid,
                    _timing_of(
                        proc, fc[cid][1], f"{base}['{fc[cid][0]}']", fastest, decisions
                    ),
                )
                for cid in order
            ]
        )
        lc_main = _newest(
            [
                (
                    cid,
                    _lc_of(
                        proc,
                        lc[cid][0],
                        lc[cid][1],
                        fc[cid][1],
                        f"{base}['{lc[cid][0]}']",
                        f"{base}['{fc[cid][0]}']",
                    ),
                )
                for cid in order
            ]
        )
        # Validation: the newest configuration compared with the providers.
        validation = {"status": "not compared"}
        for cid in order:
            name, cfg = fc[cid]
            if (
                cfg is not None
                and not cfg.get("generation_error")
                and cfg.get("values_vs_providers")
            ):
                validation = _validation_g1(proc, cfg, cid, f"{base}['{name}']", name)
                break
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
                    "fc": _families(fc, fc_main, order),
                    "lc": _families(lc, lc_main, order),
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
                    "gate_rule": "G1" if proc["gated"] else "no gate (2->2)",
                    "main": fc_main,
                    "providers": runtime["providers"],
                    "fastest": fastest,
                    "source": f"g1.json processes[{key}].providers (median s/pt)",
                },
                "leading_colour": {"main": lc_main},
            }
        )
    return rows


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
    loop (inferred, the basis says why) or not started anywhere, by its short
    attribution (no record of a run)."""
    src = f"milestone.json status_notes.notes[{key}]"
    if "refused" in note:
        return {
            "status": "refused",
            "reason": note["refused"],
            "basis": note.get("refused_basis"),
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


def _required_rows(ms: dict, meas: dict, known: set[str], factor: float) -> list[dict]:
    """The required rows without a G1 record (the 2 -> 5 set): newest first
    the development validation records, then the registry (MAIN_ORDER)."""
    native = meas["required_native"]["processes"]
    pending = ms["pending"]
    prov_gen = meas["provider_generation"]["processes"]
    refs = {(r["label"], r.get("corr")): r for r in ms["gate_references"]["rows"]}
    notes = ms.get("status_notes", {}).get("notes", {})
    njet = {r["label"]: r for r in ms["njet"]["rows"]}
    rows = []
    for req in ms["required"]["rows"]:
        corr = req.get("corr")
        text = _text(req["label"])
        key = _key(text, corr)
        if _key(text) in known and corr is None:
            continue  # a G1 row (g g > g g g g, g g > t t~ g g)
        note = notes.get(key, {})
        rec = native.get(key)
        src = f"measured.json required_native.processes[{key}]"
        dev_gen = None
        validation = {"status": "not compared", "note": req["validation"]}
        if rec is not None:
            dev_gen = {
                "status": "measured",
                "seconds": rec["generate_s"] + rec["export_s"],
                "generate_s": rec["generate_s"],
                "export_s": rec["export_s"],
                # Generation memory: the larger of the two stages' peak RSS
                # (VmHWM); the record's process peak also covers the point
                # evaluations of the validation run.
                "peak_gib": max(rec["generate_peak_gib"], rec["export_peak_gib"]),
                "process_peak_gib": rec["max_rss_gib"],
                "plan_mb": rec["plan_json_mb"],
                "inputs": rec["inputs"],
                "counterterms": rec["counterterms"],
                "branch": meas["required_native"]["branch"],
                "record": rec["record"],
                "source": src,
            }
            validation = _validation_native(rec, src)
            validation["record"] = rec["record"]
        pg = prov_gen.get(key)
        gens: dict = {n: None for n in PROVIDERS}
        unfinished = {}
        if pg is not None:
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
        if unfinished and "providers" in note:
            unfinished["note"] = note["providers"]
        gen_fastest = _fastest_generation(gens)
        if dev_gen is not None and gen_fastest is not None:
            dev_gen["ratio_to_fastest"] = dev_gen["seconds"] / gen_fastest["seconds"]
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
            gate_rule = "G1 (seven-leg rows not timed yet)"
        else:
            gate_rule = "G1 (no complete gate limit yet)"
        # An existing alternative that is not a matched provider (NJet:
        # massless five-flavour QCD), shown for orientation only: no ratio,
        # no gate.
        alternative = None
        nj = njet.get(req["label"])
        if nj is not None and not matched:
            one = meas["njet_single_evaluation"]["standard"]
            alternative = {
                "name": one["tool"],
                "seconds_per_evaluation": one["mean_s"],
                "what": "standard full-colour sum, one evaluation, double precision,"
                " one pinned core; not a matched provider",
                "source": "measured.json njet_single_evaluation.standard",
            }
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
        timing = None
        if rec is not None:
            timing = {
                "status": "pending",
                "package": pending["batched"],
                "what": "the development validation records time single points"
                " only; batched timings come from G1",
                "source": f"{src} (no batched timing); milestone.json pending",
            }
        order = MAIN_ORDER["records"]
        registry = None if status is None else dict(status)
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
                    "main": _newest(list(zip(order, (dev_gen, registry), strict=True))),
                    "providers": gens,
                    "unfinished": unfinished,
                    "fastest": gen_fastest,
                    "source": f"measured.json provider_generation.processes[{key}]",
                },
                "full_colour": {
                    "gate_rule": gate_rule,
                    "main": _newest(list(zip(order, (timing, registry), strict=True))),
                    "alternative": alternative,
                    "reference": reference,
                },
                "leading_colour": {
                    "main": _newest(list(zip(order, (timing, registry), strict=True)))
                },
            }
        )
    return rows


def _records(rows: list[dict]) -> list[dict]:
    """The DESIGN records of the main values from the development records,
    each with the rows it covers."""
    out: list[dict] = []
    for r in rows:
        main = r["generation"]["main"]
        if main.get("configuration") != "development_records":
            continue
        record = main["record"]
        found = next((x for x in out if x["record"] == record), None)
        if found is None:
            out.append({"record": record, "rows": [r["math"]]})
        else:
            found["rows"].append(r["math"])
    return out


def _configurations(g1: dict, ms: dict, meas: dict, rows: list[dict]) -> dict:
    """The candidate configurations of the main-configuration rule, each with
    its provenance and the rows where it supplies a main value (main_rows)."""
    cells = ("generation", "full_colour", "leading_colour")

    def main_rows(cid: str) -> list[str]:
        return [
            r["key"]
            for r in rows
            if any(r[c]["main"].get("configuration") == cid for c in cells)
            or r["validation"].get("configuration") == cid
        ]

    def inputs(cid: str) -> list[str]:
        found = {
            r[c]["main"]["inputs"]
            for r in rows
            for c in cells
            if r[c]["main"].get("configuration") == cid and "inputs" in r[c]["main"]
        }
        return sorted(found)

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
            "inputs": inputs("development"),
            "main_rows": main_rows("development"),
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
        "inputs": inputs("integrated"),
        "main_rows": main_rows("integrated"),
        "source": "g1.json slice_revision, slice_lc_revision, slice_build, date",
    }
    branch = meas["required_native"]["branch"]
    in_development = branch in (development.get("revisions") or {}).values()
    out["development_records"] = {
        "kind": "records",
        "label": label if in_development else "development records",
        "integration": development.get("integration") if in_development else None,
        "branch": branch,
        "inputs": inputs("development_records"),
        # The DESIGN records of the development validations, each with the
        # rows it covers.
        "records": _records(rows),
        "main_rows": main_rows("development_records"),
        "source": "measured.json required_native; label: milestone.json development",
    }
    out["registry"] = {
        "kind": "records",
        "label": "registry (no run)",
        "main_rows": main_rows("registry"),
        "source": "milestone.json status_notes",
    }
    return out


def build() -> dict:
    g1 = _load(DATA / "g1.json")
    ms = _load(DATA / "milestone.json")
    meas = _load(DATA / "measured.json")
    specs = {
        p["name"]: p
        for p in _load(REPO / "tools/loop_benchmark/processes.json")["processes"]
    }
    decisions = ms["gate_decisions"]
    rows = _g1_rows(g1, specs, decisions)
    rows += _required_rows(ms, meas, {r["key"] for r in rows}, g1["gate_factor"])
    notes = ms.get("status_notes", {}).get("notes", {})
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
    # Increasing multiplicity, then increasing colour complexity (number of
    # gluons) within a multiplicity; stable otherwise.
    rows.sort(key=lambda r: (r["outgoing"], r["label"].split().count("g")))

    groups = []
    for r in rows:
        name = f"2->{r['outgoing']}"
        if not groups or groups[-1]["name"] != name:
            groups.append({"name": name, "rows": []})
        groups[-1]["rows"].append(r)
    return {
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
                "order": {k: list(v) for k, v in MAIN_ORDER.items()},
                "source": "scripts/build_summary.py MAIN_ORDER",
            },
            "configurations": _configurations(g1, ms, meas, rows),
            "gate_decisions": decisions,
        },
        "groups": groups,
    }


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA / "summary.json"
    out.write_text(json.dumps(build(), indent=1) + "\n")


if __name__ == "__main__":
    main()
