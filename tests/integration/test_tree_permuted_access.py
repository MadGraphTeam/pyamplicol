# SPDX-License-Identifier: 0BSD
"""A tree process named in another leg order than the stored one, and a
process-group member: its colour-flow and helicity IDs are those of a
single-process artifact of that spelling.

The stored artifact (built-in SM, ``process.flavor_blind``) holds
``u g > u g``, ``d u > d u``, ``u u~ > u u~`` and ``d d~ > g g`` and serves
``s s~ > g g`` and ``s~ s > g g`` as its process-group members. Each
spelling below (both sides swapped in a quark-gluon process, the final or the
initial state alone, distinct- and identical-flavour quark lines, the two
members) is served by its stored process at the permuted momenta in the
recurrence, compiled and on-the-fly modes, at leading and full colour:

* its colour-flow IDs are the canonical ones (open lines ordered by their
  fundamental label, a trace from its smallest label), those of a
  single-process artifact of that spelling, in the metadata and in every
  selector; each flow and each helicity selected by ID has that artifact's
  value; a word that is no flow stays refused;
* the listing (and so the positions the per-point selectors and the resolved
  output use) is the stored process's, consistent with itself: the entry
  listed at position k is the one position k selects;
* the native tree SDK (C ABI) lists the same IDs and serves the same values,
  bit for bit, by ID and by position;
* a spelling the artifact does not serve raises ``ProcessSelectionError``
  with a ``key``.
"""

from __future__ import annotations

import json
import struct
import subprocess
from pathlib import Path

import pytest

from tests.integration.test_runtime_selector_api_parity import (
    _compile_probe,
    _NativeSdk,
    _source_environment,
)
from tests.integration.test_runtime_selector_api_parity import (
    native_sdk as _native_sdk_fixture,
)

native_sdk = _native_sdk_fixture

STORED = (
    ("ug", "u g > u g"),
    ("du", "d u > d u"),
    ("uux", "u u~ > u u~"),
    ("ddx", "d d~ > g g"),
    ("ssx", "s s~ > g g"),
    ("sxs", "s~ s > g g"),
)
SINGLES = (
    ("gu", "g u > g u"),
    ("ugf", "u g > g u"),
    ("gui", "g u > u g"),
    ("ud", "u d > u d"),
    ("uxu", "u~ u > u~ u"),
    ("ssx", "s s~ > g g"),
    ("sxs", "s~ s > g g"),
)
# spelling -> its process in the single-process artifact
SPELLINGS = {
    "g u > g u": "gu",
    "u g > g u": "ugf",
    "g u > u g": "gui",
    "u d > u d": "ud",
    "u~ u > u~ u": "uxu",
    "s s~ > g g": "ssx",
    "s~ s > g g": "sxs",
}
NOT_SERVED = ("u u > d d", "u g > d g", "u u~ > g")
# The flow IDs released versions listed for u d > u d served by the stored
# d u > d u (the stored word relabelled in the stored block order), and the
# canonical IDs of the same flows: the old spellings stay selectable.
PUBLISHED = {"flow:4,2,3,1": "flow:3,1,4,2", "flow:4,1,3,2": "flow:3,2,4,1"}


def _published(flow) -> str:
    """The ID a released version listed for a flow of a permuted selection:
    its word as the stored process orders it."""

    return "flow:" + ",".join(str(label) for label in flow.word)


_FIRST = ((500.0, 0.0, 0.0, 500.0), (500.0, 0.0, 0.0, -500.0))
_SECOND = ((650.0, 0.0, 0.0, 650.0), (650.0, 0.0, 0.0, -650.0))
POINTS = [
    [*map(list, _FIRST), [500.0, 300.0, 0.0, 400.0], [500.0, -300.0, 0.0, -400.0]],
    [*map(list, _SECOND), [650.0, 600.0, 0.0, 250.0], [650.0, -600.0, 0.0, -250.0]],
]
CASES = [
    (mode, accuracy)
    for mode in ("recurrence", "compiled", "on-the-fly")
    for accuracy in ("lc", "full")
]


def _generate(
    root: Path,
    entries,
    mode: str,
    accuracy: str,
    blind: bool,
    extra: str = "",
    aliases=(),
) -> Path:
    from pyamplicol.api import Generator, ProcessAlias, ProcessRequest, ProcessSet
    from pyamplicol.config import resolve_config

    root.mkdir(parents=True, exist_ok=True)
    processes = ", ".join(
        f"{{ expression = {json.dumps(e)}, name = {json.dumps(n)} }}"
        for n, e in entries
    )
    card = root / "card.toml"
    card.write_text(
        f"""
action = "generate"
[model]
source = "built-in-sm"
[process]
entries = [{processes}]
flavor_blind = {"true" if blind else "false"}
{extra}
[color]
accuracy = "{accuracy}"
[evaluator]
execution_mode = "{mode}"
[generation]
output = {json.dumps(str(root / "artifact"))}
emit_api_bundle = false
"""
    )
    Generator(resolve_config(card)).generate(
        ProcessSet(
            tuple(ProcessRequest.parse(e, name=n) for n, e in entries),
            tuple(ProcessAlias(*alias) for alias in aliases),
        ),
        root / "artifact",
    )
    return root / "artifact"


@pytest.fixture(scope="module", params=CASES, ids=["-".join(c) for c in CASES])
def artifacts(request, tmp_path_factory):
    mode, accuracy = request.param
    tag = f"{mode}-{accuracy}"
    stored = _generate(
        tmp_path_factory.mktemp(f"stored-{tag}"), STORED, mode, accuracy, True
    )
    singles = _generate(
        tmp_path_factory.mktemp(f"singles-{tag}"), SINGLES, mode, accuracy, False
    )
    return stored, singles, accuracy


def _load(artifact: Path, process: str):
    from pyamplicol import Runtime

    return Runtime.load(artifact, process=process)


def _values(result) -> list[complex]:
    out: list[complex] = []

    def walk(value) -> None:
        if isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
        else:
            out.append(complex(value))

    walk(getattr(result, "values", result))
    return out


def _close(left, right, scale: float, label) -> None:
    a, b = _values(left), _values(right)
    assert len(a) == len(b), label
    worst = max(abs(x - y) for x, y in zip(a, b, strict=True))
    assert worst <= 1e-12 * scale, (label, worst / scale)


def test_flow_and_helicity_ids_are_a_single_artifacts(artifacts):
    """Every flow and helicity ID of a permuted spelling or member is one a
    single-process artifact of that spelling uses, and selects that
    artifact's value; the flows sum to the inclusive value; a word that is
    no flow is refused."""

    from pyamplicol.api.errors import PyAmpliColError

    stored, singles, accuracy = artifacts
    for spelling, single in SPELLINGS.items():
        mapped, own = _load(stored, spelling), _load(singles, single)
        flows = [f.id for f in mapped.physics.color_flows]
        assert sorted(flows) == sorted(f.id for f in own.physics.color_flows)
        helicities = [h.id for h in mapped.physics.helicities]
        assert sorted(helicities) == sorted(h.id for h in own.physics.helicities)
        inclusive = mapped.evaluate(POINTS)
        scale = max(abs(x) for x in _values(inclusive))
        _close(inclusive, own.evaluate(POINTS), scale, spelling)
        for helicity in helicities:
            _close(
                mapped.evaluate(POINTS, helicities=[helicity]),
                own.evaluate(POINTS, helicities=[helicity]),
                scale,
                (spelling, helicity),
            )
        if accuracy != "lc":
            continue
        total = [0j] * len(_values(inclusive))
        for flow in flows:
            selected = mapped.evaluate(POINTS, color_flows=[flow])
            _close(selected, own.evaluate(POINTS, color_flows=[flow]), scale, flow)
            total = [x + y for x, y in zip(total, _values(selected), strict=True)]
        for x, y in zip(total, _values(inclusive), strict=True):
            assert abs(x - y) <= 1e-12 * scale, spelling
        with pytest.raises(PyAmpliColError):
            mapped.evaluate(POINTS, color_flows=["flow:1,3,2,4"])
        # The spellings released versions listed select the same flows.
        for flow in mapped.physics.color_flows:
            old = mapped.evaluate(POINTS, color_flows=[_published(flow)])
            assert _values(old) == _values(
                mapped.evaluate(POINTS, color_flows=[flow.id])
            ), (spelling, flow.id)
        if spelling == "u d > u d":
            assert sorted(flows) == sorted(PUBLISHED.values())
            assert {_published(f) for f in mapped.physics.color_flows} == set(PUBLISHED)
            for old, canonical in PUBLISHED.items():
                assert _values(mapped.evaluate(POINTS, color_flows=[old])) == (
                    _values(mapped.evaluate(POINTS, color_flows=[canonical]))
                )


def test_the_listing_and_its_positions_refer_to_each_other(artifacts):
    """The resolved output lists the flows and helicities in the order the
    runtime's metadata lists them (the stored process's), and its entry at
    position k is the value of the ID listed at position k."""

    stored, _singles, accuracy = artifacts
    for spelling in SPELLINGS:
        mapped = _load(stored, spelling)
        flows = [f.id for f in mapped.physics.color_flows]
        helicities = [h.id for h in mapped.physics.helicities]
        resolved = mapped.evaluate_resolved(POINTS)
        assert list(resolved.helicity_ids) == helicities
        if accuracy == "lc":
            assert list(resolved.color_ids) == flows
        scale = max(abs(x) for x in _values(mapped.evaluate(POINTS)))
        for k, flow in enumerate(resolved.color_ids):
            if accuracy != "lc":
                break
            selected = _values(mapped.evaluate(POINTS, color_flows=[flow]))
            column = [
                sum(point[h][k] for h in range(len(point))) for point in resolved.values
            ]
            for x, y in zip(selected, column, strict=True):
                assert abs(x - y) <= 1e-12 * scale, (spelling, flow)


def test_a_spelling_that_is_not_served_is_refused_with_a_key(artifacts):
    from pyamplicol.api.errors import EvaluationError, ProcessSelectionError

    stored, _singles, _accuracy = artifacts
    for spelling in NOT_SERVED:
        with pytest.raises(ProcessSelectionError) as error:
            _load(stored, spelling)
        assert isinstance(error.value, EvaluationError)
        assert error.value.key == "process-not-served", spelling


PROBE = r"""
#include <rusticol.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const double MOMENTA[32] = {
    500, 0, 0, 500, 500, 0, 0, -500, 500, 300, 0, 400, 500, -300, 0, -400,
    650, 0, 0, 650, 650, 0, 0, -650, 650, 600, 0, 250, 650, -600, 0, -250};

static void bits(const double *values, size_t count) {
    for (size_t k = 0; k < count; ++k) {
        unsigned long long word;
        memcpy(&word, &values[k], sizeof word);
        printf(" %016llx", word);
    }
}

int main(int argc, char **argv) {
    RusticolRuntimeHandle *handle = NULL;
    if (rusticol_runtime_load(argv[1], argv[2], NULL, &handle) != 0) {
        char message[1024];
        size_t needed = 0;
        rusticol_last_error_message(message, sizeof message, &needed);
        printf("LOAD-ERROR %s\n", message);
        return 0;
    }
    size_t colors = 0;
    rusticol_runtime_color_count(handle, &colors);
    for (size_t k = 0; k < colors; ++k) {
        char id[256];
        size_t needed = 0;
        rusticol_runtime_color_id(handle, k, id, sizeof id, &needed);
        double by_id[2], by_position[2];
        const char *ids[1] = {id};
        uint32_t positions[2] = {(uint32_t)k, (uint32_t)k};
        int a = rusticol_runtime_evaluate_selected_f64(
            handle, MOMENTA, 32, 2, NULL, 0, ids, 1, NULL, 0, NULL, 0, by_id, 2);
        int b = rusticol_runtime_evaluate_selected_f64(
            handle, MOMENTA, 32, 2, NULL, 0, NULL, 0, NULL, 0, positions, 2,
            by_position, 2);
        printf("COLOR %zu %s %d %d", k, id, a, b);
        bits(by_id, 2);
        printf(" |");
        bits(by_position, 2);
        printf("\n");
    }
    for (int arg = 3; arg < argc; ++arg) {
        double value[2];
        const char *ids[1] = {argv[arg]};
        int status = rusticol_runtime_evaluate_selected_f64(
            handle, MOMENTA, 32, 2, NULL, 0, ids, 1, NULL, 0, NULL, 0, value, 2);
        printf("SELECT %s %d", argv[arg], status);
        if (status == 0) bits(value, 2);
        printf("\n");
    }
    rusticol_runtime_free(handle);
    return 0;
}
"""


def _bits(value: complex) -> str:
    return struct.pack(">d", complex(value).real).hex()


def test_the_native_tree_sdk_names_and_serves_the_canonical_ids(
    artifacts, native_sdk: _NativeSdk, tmp_path
):
    """The C ABI opens each spelling, lists the IDs the Python runtime lists,
    serves each flow by ID and by its listed position with the same value
    (bitwise the Python runtime's), and refuses an unserved spelling."""

    stored, _singles, accuracy = artifacts
    if accuracy != "lc":
        pytest.skip("colour flows exist at leading colour")
    binary = _compile_probe("c", PROBE, native_sdk, tmp_path)
    for spelling in SPELLINGS:
        mapped = _load(stored, spelling)
        flows = [f.id for f in mapped.physics.color_flows]
        published = {_published(f): f.id for f in mapped.physics.color_flows}
        run = subprocess.run(
            [
                str(binary),
                str(stored),
                spelling,
                *flows,
                *published,
                "flow:1,3,2,4",
            ],
            capture_output=True,
            text=True,
            env=_source_environment(),
            timeout=120,
            check=True,
        )
        lines = run.stdout.splitlines()
        listed = [line.split() for line in lines if line.startswith("COLOR")]
        assert [row[2] for row in listed] == flows, spelling
        for row in listed:
            assert row[3] == row[4] == "0", (spelling, row)
            by_id, by_position = row[5:7], row[8:10]
            assert by_id == by_position, (spelling, row)
            want = [
                _bits(x) for x in _values(mapped.evaluate(POINTS, color_flows=[row[2]]))
            ]
            assert by_id == want, (spelling, row)
        selected = {
            line.split()[1]: line.split()[2:]
            for line in lines
            if line.startswith("SELECT")
        }
        assert selected["flow:1,3,2,4"][0] != "0", spelling
        # The spellings released versions listed select the same flows.
        for old, canonical in published.items():
            assert selected[old][0] == "0", (spelling, old)
            assert selected[old][1:] == selected[canonical][1:], (spelling, old)
    for spelling in NOT_SERVED:
        run = subprocess.run(
            [str(binary), str(stored), spelling],
            capture_output=True,
            text=True,
            env=_source_environment(),
            timeout=120,
            check=True,
        )
        assert run.stdout.startswith("LOAD-ERROR"), spelling


SUBSETS = {
    "cap": "max_color_sectors = 1",
    "fixed": "selected_color_sector_ids = [0]",
}


# The modes that generate a subset (recurrence refuses a truncating cap and
# on-the-fly keeps complete selector coverage, at generation).
@pytest.mark.parametrize(
    ("mode", "subset"),
    [("compiled", "cap"), ("compiled", "fixed"), ("recurrence", "fixed")],
)
def test_a_subset_alias_keeps_its_ids_and_the_stored_positions(subset, mode, tmp_path):
    """u u~ > g g with one sector kept and its alias exchanging the outgoing
    gluons: the alias lists the stored flow on its legs under its canonical
    ID (flow:2,4,3,1, where a fresh artifact of that card keeps
    flow:2,3,4,1), position 0 selects that listed entry, and its value is
    the complete artifact's flow:2,4,3,1."""

    entries = (("uugg", "u u~ > g g"),)
    stored = _generate(
        tmp_path / "subset",
        entries,
        mode,
        "lc",
        False,
        SUBSETS[subset],
        (("uugg_swap", "uugg", (0, 1, 3, 2)),),
    )
    complete = _generate(tmp_path / "complete", entries, mode, "lc", False)
    alias, base = _load(stored, "uugg_swap"), _load(stored, "uugg")
    assert [f.id for f in base.physics.color_flows] == ["flow:2,3,4,1"]
    assert [f.id for f in alias.physics.color_flows] == ["flow:2,4,3,1"]
    resolved = alias.evaluate_resolved(POINTS)
    assert list(resolved.color_ids) == ["flow:2,4,3,1"]
    reference = _load(complete, "uugg")
    scale = max(abs(x) for x in _values(reference.evaluate(POINTS)))
    _close(
        alias.evaluate(POINTS, color_flows=["flow:2,4,3,1"]),
        reference.evaluate(POINTS, color_flows=["flow:2,4,3,1"]),
        scale,
        (subset, mode),
    )
