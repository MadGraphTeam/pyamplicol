# SPDX-License-Identifier: 0BSD
"""Known campaign outcomes the loop-induced campaign test expects to fail
strictly (``tests/unit/test_loop_v2_li_campaign.py``): each with the exact
signature of its record, validated after every ordinary assertion of the
run; any other outcome is an ordinary failure, and a clean run completes
normally (a strict XPASS), so a change of status is noticed."""

from __future__ import annotations

from typing import Any

# g g > Z vanishes by Landau-Yang; the generator does not prove the zero.
# At the probe point (the same 2 -> 1 point ``pyamplicol check`` takes) the
# helicity rows (-,+,-) and (+,-,+) that angular momentum forbids are below
# numerical resolution at k = 1, the helicities (-,-,-), (-,-,+), (+,+,-) and
# (+,+,+) have no resolved physical normalisation at k = 1 (T of 1e-15, P
# neither reproducing nor collapsing between the carriers), and neither has
# the Ward probe on leg 1.
GG_Z = "li_gg_z"
GG_Z_REASON = (
    "known limitation: g g > Z is a Landau-Yang zero the generator does not "
    "prove; its angular-momentum-forbidden helicity rows are below numerical "
    "resolution and its Ward probe has no resolved physical normalisation "
    "(recorded inconclusive, never a pass)"
)
GG_Z_ROWS = ("((0, -1), (1, 1), (2, -1))) k=1", "((0, 1), (1, -1), (2, 1))) k=1")
GG_Z_UNRESOLVED = (
    "((0, -1), (1, -1), (2, -1))) k=1",
    "((0, -1), (1, -1), (2, 1))) k=1",
    "((0, 1), (1, 1), (2, -1))) k=1",
    "((0, 1), (1, 1), (2, 1))) k=1",
)
BELOW_RESOLUTION = "helicity row below numerical resolution"
UNRESOLVED = "physical normalisation unresolved"


class KnownBelowResolution(Exception):
    """The known g g > Z outcome, exactly (``check_gg_z``)."""


def _open(cells: Any) -> list[dict]:
    return [c for c in cells if c.get("verdict") not in ("pass", "vacuous")]


# The known outcome's campaign statuses (``li_manifest.judge``): the checks
# and every L3 / L4 arm, fixed; only L4's generation entry is open.
def gg_z_statuses() -> dict[str, Any]:
    from tools.loop_benchmark import li_manifest as lm

    accepted = f"{lm.ACCEPTED}: {lm.NO_NORMALISATION}"
    arms = {
        "ninjars/double": "pass",
        "ninjars/double-double": accepted,
        "tirust/double": "pass",
        "tirust/double-double": accepted,
    }
    return {
        "checks": {
            "L1": "recorded",
            "L3": accepted,
            "L4": "inconclusive",
            "L5": "recorded",
            "L6": "pass",
            "L7": "pass",
            "L8": "pass",
            "E": "pass",
        },
        "L3": dict(arms),
        "L4": {"generation": "inconclusive", **arms},
        "legs": [1, 2],
    }


# The ``pyamplicol check`` report's rows: (check, subject) -> verdict.
GG_Z_REPORT = {
    ("poles", "finiteness (every loop order and row)"): "inconclusive",
    ("ward", "leg 1"): "inconclusive",
    ("goldstone", "external massive vectors"): "not applicable",
}
# The Ward row of leg 1: its open rows, each with the current reason
# ``UNRESOLVED`` in double-double.
GG_Z_WARD_OPEN = 8


def _arms(result: dict) -> dict[str, str]:
    return {
        label: value["status"]
        for label, value in result.items()
        if isinstance(value, dict) and "status" in value
    }


def _generation_entry(entry: dict, carrier: str = "double-double") -> None:
    """A generation-time probe entry decided in ``carrier`` by its rows'
    verdicts (no refusal in any carrier), its open rows' normalisation
    unresolved."""

    assert entry["verdict"] == "inconclusive" and not entry["passed"], entry
    assert entry["carrier"] == carrier, entry
    assert "refused" not in entry, entry
    fallback = entry.get("fallback")
    assert isinstance(fallback, dict), entry
    assert fallback["carrier"] == "double" and fallback["reason"] == "verdict", entry
    assert f": {UNRESOLVED}: " in entry.get("inconclusive", ""), entry


def check_gg_z(statuses: dict, judged: dict, record: dict, report: Any) -> None:
    """Raise ``KnownBelowResolution`` iff the run is exactly the known g g > Z
    outcome; any deviation fails an ordinary assertion.

    * The campaign: the statuses of every check and of every L3 / L4 arm are
      the known ones (``gg_z_statuses``: the fixture-point arms pass in
      binary64 and are accepted, no physical normalisation, in
      double-double; only L4's generation entry is open).
    * The generation record: completed without failure or refusal; the
      finiteness probe and the Ward probe on leg 1 decided in double-double
      after a binary64 verdict, inconclusive with an unresolved
      normalisation, the finiteness probe with exactly two rows below
      numerical resolution; no other probe.
    * ``pyamplicol check`` on the artifact: exit 4 and exactly the known
      rows (``GG_Z_REPORT``); the finiteness row open exactly on the two
      known k = 1 helicities below numerical resolution and the four with
      an unresolved normalisation; the Ward row of leg 1 open exactly on
      its known rows, each with measured double-double operands and the
      current reason an unresolved normalisation; no failing row."""

    want = gg_z_statuses()
    assert statuses == want["checks"], statuses
    assert _arms(judged["L3"]) == want["L3"], judged["L3"]
    assert _arms(judged["L4"]) == want["L4"], judged["L4"]
    assert judged["L4"].get("legs") == want["legs"], judged["L4"]
    probes = record["generation"]["probes"]
    assert probes.get("status") == "run" and "failed" not in probes, probes
    entries = {(p["probe"], p.get("leg")): p for p in probes["probes"]}
    assert set(entries) == {("finiteness", None), ("ward", 1)}, sorted(entries)
    finiteness, ward_entry = entries[("finiteness", None)], entries[("ward", 1)]
    _generation_entry(finiteness)
    assert finiteness.get("below_resolution") == 2, finiteness
    _generation_entry(ward_entry)
    assert "below_resolution" not in ward_entry, ward_entry
    assert probes["ward"]["carriers"] == {"1": "double-double"}, probes["ward"]
    assert report.exit_code == 4, report.exit_code
    (process,) = report.processes
    rows = {(row.check, row.subject): row.verdict for row in process.rows}
    assert rows == GG_Z_REPORT, rows
    assert len(process.rows) == len(GG_Z_REPORT), rows
    for row in process.rows:
        for cell in row.cells:
            assert cell.get("verdict") != "fail", cell
    (poles,) = [row for row in process.rows if row.check == "poles"]
    opened = _open(poles.cells)

    def matching(labels: tuple[str, ...]) -> list[dict]:
        return [c for c in opened if c["label"].endswith(labels)]

    deferred, unresolved = matching(GG_Z_ROWS), matching(GG_Z_UNRESOLVED)
    assert len(opened) == len(GG_Z_ROWS) + len(GG_Z_UNRESOLVED), opened

    def suffixes(cells: list[dict], labels: tuple[str, ...]) -> list[str]:
        return sorted(x for c in cells for x in labels if c["label"].endswith(x))

    assert suffixes(deferred, GG_Z_ROWS) == sorted(GG_Z_ROWS), opened
    assert suffixes(unresolved, GG_Z_UNRESOLVED) == sorted(GG_Z_UNRESOLVED), opened
    for cell in opened:
        assert cell["carrier"] == "double-double", cell
        assert None not in (cell["residue"], cell["physical"], cell["terms"]), cell
    for cell in deferred:
        assert cell["reason"].startswith(BELOW_RESOLUTION), cell
    for cell in unresolved:
        assert cell["reason"].startswith(UNRESOLVED), cell
    (ward,) = [row for row in process.rows if row.check == "ward"]
    unresolved = _open(ward.cells)
    assert len(unresolved) == GG_Z_WARD_OPEN, unresolved
    for cell in unresolved:
        assert cell["verdict"] == "inconclusive", cell
        assert cell["carrier"] == "double-double", cell
        assert (cell.get("reason") or "").startswith(UNRESOLVED), cell
        assert None not in (cell["residue"], cell["physical"], cell["terms"]), cell
    raise KnownBelowResolution(GG_Z_REASON)
