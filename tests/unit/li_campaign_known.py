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


def check_gg_z(statuses: dict, judged: dict, record: dict, report: Any) -> None:
    """Raise ``KnownBelowResolution`` iff the run's only open item is exactly
    the known g g > Z signature; any deviation fails an ordinary assertion.

    * The campaign checks: no failure, and the only unaccepted inconclusive
      is L4, from the generation-time probes alone.
    * The generation record: generation completed (no decisive failure),
      the finiteness probe inconclusive in double-double with exactly two
      rows below numerical resolution, the Ward probe on leg 1 inconclusive.
    * ``pyamplicol check`` on the artifact (exit 4): the finiteness row's
      only open rows are the two known k = 1 helicities below numerical
      resolution and the four known k = 1 helicities with an unresolved
      physical normalisation, and the Ward row of leg 1 is open only with
      complete operands and an unresolved physical normalisation; no
      failing row."""

    from tools.loop_benchmark import li_manifest as lm

    assert "fail" not in statuses.values(), statuses
    assert lm.unaccepted(statuses.values()) == [statuses.get("L4")], statuses
    l4 = judged["L4"]
    assert l4["generation"]["status"] == "inconclusive", l4["generation"]
    for label, value in l4.items():
        if label != "generation" and isinstance(value, dict) and "status" in value:
            assert value["status"] != "fail", (label, value)
            assert not lm.unaccepted([value["status"]]), (label, value)
    probes = record["generation"]["probes"]
    assert probes.get("status") == "run" and "failed" not in probes, probes
    entries = {(p["probe"], p.get("leg")): p for p in probes["probes"]}
    assert set(entries) == {("finiteness", None), ("ward", 1)}, sorted(entries)
    finiteness = entries[("finiteness", None)]
    assert finiteness["verdict"] == "inconclusive", finiteness
    assert finiteness.get("below_resolution") == 2, finiteness
    assert finiteness["carrier"] == "double-double", finiteness
    assert entries[("ward", 1)]["verdict"] == "inconclusive", entries[("ward", 1)]
    assert report.exit_code == 4, report.exit_code
    (process,) = report.processes
    rows = {(row.check, row.subject): row for row in process.rows}
    for row in process.rows:
        assert row.verdict != "fail", (row.check, row.subject, row.verdict)
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
    ward = rows.get(("ward", "leg 1"))
    assert ward is not None and ward.verdict == "inconclusive", sorted(rows)
    assert [r for r in process.rows if r.check == "ward"] == [ward], sorted(rows)
    unresolved = _open(ward.cells)
    assert unresolved, ward
    for cell in unresolved:
        assert UNRESOLVED in (cell.get("reason") or ""), cell
        assert None not in (cell["residue"], cell["physical"], cell["terms"]), cell
    raise KnownBelowResolution(GG_Z_REASON)
