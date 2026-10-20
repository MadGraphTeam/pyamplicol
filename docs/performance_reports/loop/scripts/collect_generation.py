"""Collect generation observations that are not part of the timing snapshot.

Writes ``data/generation.json`` from retained correctness-run records and the
seven-leg stage log. No value is estimated: each entry copies an observed field
and names its source. Usage, from the report directory::

    python scripts/collect_generation.py <workspace>/reports
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPORTS = Path(sys.argv[1])
OUT = Path(__file__).resolve().parent.parent / "data" / "generation.json"

# Cold generation recorded by complete correctness runs (not timing campaigns).
CORRECTNESS = (
    ("uu-eegg", "u overline(u) -> e^- e^+ g g", "sixleg-source-physical.json"),
    (
        "uu-ddss",
        "u overline(u) -> d overline(d) s overline(s)",
        "multiquark-source-physical.json",
    ),
)

# Seven-leg stage segments: (label, begin event, end event). Events are the
# JSON stage lines written by the run; "start" is process time zero.
SEGMENTS = (
    ("Model and graph generation", "start", "bare_assembly_begin"),
    (
        "Recurrence DAGs and colour overlaps",
        "bare_assembly_begin",
        "born_projection_begin",
    ),
    ("Born projector", "born_projection_begin", "born_projection_done"),
    (
        "Dual weights and 751 family projectors",
        "shared_dual_weights_begin",
        "bare_assembly_done",
    ),
    (
        "Counterterm tree enumeration and matching",
        "bare_assembly_done",
        "uv_r2_assembly_begin",
    ),
)
# The UV/R2 projector never finished. The process was last observed alive at
# 33,950 s (ps elapsed time at 08:07 UTC on 2026-10-20, resumption assessment
# section 0); its log stops at 08:08 UTC without a result.
LAST_OBSERVED_S = 33950.0


def correctness_runs() -> list[dict]:
    rows = []
    for case, label, name in CORRECTNESS:
        record = json.loads((REPORTS / name).read_text())
        counts = record["counts"]
        rows.append(
            {
                "case": case,
                "label": label,
                "born_graphs": counts["born"],
                "loop_graphs": counts["loop"],
                "families": counts["families"],
                "generation_s": record["cold_generation_s_observed"],
                "source": f"workspace/reports/{name}",
                "kind": "cold generation observed in a correctness run",
            }
        )
    return rows


def seven_leg() -> dict:
    log = REPORTS / "multiquark-sevenprop-current.log"
    events = {"start": {"elapsed_s": 0.0, "maximum_rss_kib": None}}
    for line in log.read_text().splitlines():
        if line.startswith('{"stage"'):
            event = json.loads(line)
            if event.get("family") is None:
                events.setdefault(event["stage"], event)
    stages = [
        {
            "label": label,
            "begin_s": events[begin]["elapsed_s"],
            "end_s": events[end]["elapsed_s"],
            "rss_kib_at_end": events[end]["maximum_rss_kib"],
        }
        for label, begin, end in SEGMENTS
    ]
    stages.append(
        {
            "label": "UV/R2 projector (unfinished)",
            "begin_s": events["uv_r2_assembly_begin"]["elapsed_s"],
            "end_s": LAST_OBSERVED_S,
            "rss_kib_at_end": None,
            "unfinished": True,
        }
    )
    run = json.loads((REPORTS / "multiquark-sevenprop-current.json").read_text())
    return {
        "label": "u overline(u) -> d overline(d) s overline(s) g",
        "born_graphs": 64,
        "loop_graphs": 3540,
        "families": 751,
        "seven_propagator_families": 48,
        "counts_source": "HANDOFF.md section 6",
        "source_revision": run["source_revision"][:8],
        "cpu": run["cpu"],
        "scope": run["scope"],
        "peak_rss_kib": max(e["maximum_rss_kib"] or 0 for e in events.values()),
        "last_observed_s": LAST_OBSERVED_S,
        "outcome": "no result; process ended inside the UV/R2 projector",
        "stages": stages,
        "source": "workspace/reports/multiquark-sevenprop-current.{json,log}",
    }


if __name__ == "__main__":
    OUT.write_text(
        json.dumps(
            {"correctness_runs": correctness_runs(), "seven_leg": seven_leg()},
            indent=1,
        )
        + "\n"
    )
    print(OUT)
