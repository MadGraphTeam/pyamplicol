# SPDX-License-Identifier: 0BSD
"""A multiprocess one-loop generation releases each written subprocess.

``generation.loop_service._generate_v2`` generates the subprocesses of a
request one after the other. A written subprocess (its slice, plans and
observables) must be released before the next one is generated, so that the
peak memory of the generation is its largest subprocess's, not the sum over
subprocesses; with ``process.flavor_blind`` only the small admission record
of each representative stays (``observables.MemberAdmission``), and it admits
exactly the members the slice admits. The model caches the subprocesses share
(``ct_closure._LOWERED``, ``dag_input._MODEL_ROWS``) are released when the
generation ends.

The probe is a weak reference to every generated slice, read when the next
subprocess is generated: no resident-memory bound.
"""

from __future__ import annotations

import gc
import json
import weakref
from pathlib import Path

import pytest

pytestmark = pytest.mark.loop_physics

ZERO_WIDTHS = 'fixed_parameters = { WT = "0", WZ = "0", WW = "0", WH = "0" }'
# With process.flavor_blind: s s~ > g g is a species member of d d~ > g g
# (as in the flavour-blind p p > j j), d~ d > g g a leg-permutation alias of
# it; u u~ > g g is generated.
ENTRIES = (
    ("d d~ > g g", "dd_gg"),
    ("s s~ > g g", "ss_gg"),
    ("d~ d > g g", "dxd_gg"),
    ("u u~ > g g", "uu_gg"),
)


def _card(output: Path, *, flavor_blind: bool) -> str:
    entries = ", ".join(
        f"{{ expression = {json.dumps(e)}, name = {json.dumps(n)} }}"
        for e, n in ENTRIES
    )
    return f"""
action = "generate"
[model]
source = "loop_sm"
restriction = "no_b_mass"
[process]
entries = [{entries}]
loop_coupling_orders = ["QCD"]
flavor_blind = {json.dumps(flavor_blind)}
[loop.preparation]
{ZERO_WIDTHS}
[generation]
output = {json.dumps(str(output))}
emit_api_bundle = false
[generation.validation]
post_build_validation = false
"""


def _generate(tmp_path: Path, monkeypatch, *, flavor_blind: bool, inspect=None):
    """Generate ``ENTRIES`` and return, per generated process, whether the
    slices of the processes generated before it were still alive when its
    generation started."""

    from pyamplicol.api import Generator, ProcessRequest, ProcessSet
    from pyamplicol.config import resolve_config
    from pyamplicol.loops.v2 import artifact

    generate_process = artifact.generate_process
    slices: list[weakref.ref] = []
    alive: list[int] = []

    def probe(*args, **kwargs):
        gc.collect()
        alive.append(sum(ref() is not None for ref in slices))
        process = generate_process(*args, **kwargs)
        slices.append(weakref.ref(process.slice))
        if inspect is not None:
            inspect(process)
        return process

    monkeypatch.setattr(artifact, "generate_process", probe)
    card = tmp_path / "card.toml"
    output = tmp_path / "artifact"
    card.write_text(_card(output, flavor_blind=flavor_blind))
    processes = ProcessSet(tuple(ProcessRequest.parse(e, name=n) for e, n in ENTRIES))
    Generator(resolve_config(card)).generate(processes, output)
    gc.collect()
    return alive, slices, output


def _caches_empty() -> bool:
    from pyamplicol.loops.v2 import ct_closure, dag_input

    return not ct_closure._LOWERED and not dag_input._MODEL_ROWS


def test_a_written_subprocess_is_released_before_the_next(
    loop_native, tmp_path, monkeypatch
):
    alive, slices, _output = _generate(tmp_path, monkeypatch, flavor_blind=False)
    # Four subprocesses, each generated after the previous ones were released.
    assert len(slices) == 4
    assert alive == [0, 0, 0, 0]
    assert all(ref() is None for ref in slices)
    # The shared model caches do not outlive the generation.
    assert _caches_empty()


def test_flavour_grouping_keeps_only_the_admission_record(
    loop_native, tmp_path, monkeypatch
):
    from pyamplicol.loops.v2.observables import MemberAdmission, admit_member

    admitted = {}

    def inspect(process):
        # The record admits what the slice admits (same member, same proof).
        if not admitted:  # the first generated process: d d~ > g g
            for member in ("s s~ > g g", "d~ d > g g"):
                admitted[member] = (
                    admit_member(process.slice, member),
                    admit_member(MemberAdmission.of(process.slice), member),
                )

    alive, slices, output = _generate(
        tmp_path, monkeypatch, flavor_blind=True, inspect=inspect
    )
    for by_slice, by_record in admitted.values():
        assert by_record == by_slice
    assert admitted["s s~ > g g"][1].species
    assert admitted["d~ d > g g"][1].alias
    # Two generated subprocesses (d d~, u u~), the second generated once the
    # first's slice was released; s s~ and d~ d are served by d d~.
    assert len(slices) == 2
    assert alive == [0, 0]
    groups = json.loads((output / "process-groups.json").read_text())["groups"]
    served = {
        group["representative"]["process_id"]: sorted(
            member["process_id"] for member in group["members"]
        )
        for group in groups
    }
    assert served == {"dd_gg": ["dd_gg", "dxd_gg", "ss_gg"], "uu_gg": ["uu_gg"]}
    assert _caches_empty()
