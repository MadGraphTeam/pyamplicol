# SPDX-License-Identifier: 0BSD
"""A multiprocess one-loop generation releases each written subprocess.

``generation.loop_service._generate_v2`` generates the subprocesses of a
request one after the other. A written subprocess (its slice, plans and
observables) must be released before the next one is generated, so that the
peak memory of the generation is its largest subprocess's, not the sum over
subprocesses; with ``process.flavor_blind`` only the small admission record
of each representative stays (``observables.MemberAdmission``), and it admits
exactly the members the slice admits. The model caches the subprocesses share
(the lowered counterterm models, ``ct_closure.lowered_model_scope``, and their
vertex rows, ``dag_input.model_rows_scope``) are the generation's own: shared
by its subprocesses, never touched by a concurrent generation (two
generations in threads, one finishing while the other is between a cache
lookup and its update, both succeed with the values of single runs), and
dropped with it (the module caches stay empty).

The probe is a weak reference to every generated slice, read when the next
subprocess is generated: no resident-memory bound.
"""

from __future__ import annotations

import gc
import inspect as source
import json
import sys
import threading
import weakref
from collections import OrderedDict
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
    """Generate ``ENTRIES`` and return, per generated process, how many
    slices of the processes generated before it were still alive when its
    generation started, the weak references and the number of counterterm
    lowerings."""

    from pyamplicol.api import Generator, ProcessRequest, ProcessSet
    from pyamplicol.config import resolve_config
    from pyamplicol.loops.v2 import artifact, ct_closure, ct_recursion, dag_input

    # Empty module caches: a generation must leave them so.
    monkeypatch.setattr(ct_closure, "_LOWERED", OrderedDict())
    monkeypatch.setattr(dag_input, "_MODEL_ROWS", {})
    generate_process = artifact.generate_process
    lower = ct_recursion.lower_model_counterterms
    slices: list[weakref.ref] = []
    alive: list[int] = []
    lowerings: list[int] = []

    def counted(*args, **kwargs):
        lowerings.append(1)
        return lower(*args, **kwargs)

    def probe(*args, **kwargs):
        gc.collect()
        alive.append(sum(ref() is not None for ref in slices))
        process = generate_process(*args, **kwargs)
        slices.append(weakref.ref(process.slice))
        if inspect is not None:
            inspect(process)
        return process

    monkeypatch.setattr(artifact, "generate_process", probe)
    monkeypatch.setattr(ct_recursion, "lower_model_counterterms", counted)
    card = tmp_path / "card.toml"
    output = tmp_path / "artifact"
    card.write_text(_card(output, flavor_blind=flavor_blind))
    processes = ProcessSet(tuple(ProcessRequest.parse(e, name=n) for e, n in ENTRIES))
    Generator(resolve_config(card)).generate(processes, output)
    gc.collect()
    return alive, slices, output, len(lowerings)


def _caches_empty() -> bool:
    from pyamplicol.loops.v2 import ct_closure, dag_input

    return not ct_closure._LOWERED and not dag_input._MODEL_ROWS


def test_a_written_subprocess_is_released_before_the_next(
    loop_native, tmp_path, monkeypatch
):
    alive, slices, _output, lowerings = _generate(
        tmp_path, monkeypatch, flavor_blind=False
    )
    # Four subprocesses, each generated after the previous ones were released.
    assert len(slices) == 4
    assert alive == [0, 0, 0, 0]
    assert all(ref() is None for ref in slices)
    # The subprocesses share the generation's lowered models...
    assert lowerings < len(slices)
    # ...which do not outlive it (nor enter the module caches).
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

    alive, slices, output, _lowerings = _generate(
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


def _single_card(output: Path, expression: str) -> str:
    return f"""
action = "generate"
[model]
source = "loop_sm"
restriction = "no_b_mass"
[process]
entries = [{{ expression = {json.dumps(expression)}, name = "p" }}]
loop_coupling_orders = ["QCD"]
[loop.preparation]
{ZERO_WIDTHS}
[generation]
output = {json.dumps(str(output))}
emit_api_bundle = false
"""


def _run(root: Path, label: str, expression: str) -> Path:
    from pyamplicol.api import Generator
    from pyamplicol.config import resolve_config

    output = root / label
    card = root / f"{label}.toml"
    card.write_text(_single_card(output, expression))
    Generator(resolve_config(card)).generate(expression, output)
    return output


def _process(output: Path) -> Path:
    (process,) = (path for path in (output / "processes").iterdir() if path.is_dir())
    return process


def _values(output: Path) -> list[str]:
    from pyamplicol.api import Runtime

    process = _process(output)
    stored = json.loads((process / "validation-momenta.json").read_text())
    point = [[float(x) for x in leg["momentum"]] for leg in stored["points"][0]]
    values = Runtime.load(output, process=process.name).evaluate(
        [point], mu_r2="1000000"
    )
    return [
        float(getattr(coefficient, part)).hex()
        for row in values.values
        for coefficient in row
        for part in ("finite", "single_pole", "double_pole")
    ]


# The two forced schedules: generation A is held inside a cache operation of
# the model preparation, the counterterm cache between its lookup and its
# update (``move_to_end``), the model-row cache between its bound check and
# its eviction (one row table kept, so that a generation evicts), while
# generation B runs to its end.
SCHEDULES = {
    "lowered-models": ("ct_closure", "lowered_counterterm_model", ".move_to_end(key)"),
    "model-rows": ("dag_input", "_model_rows", "del "),
}


@pytest.fixture(scope="module")
def singles(loop_native, tmp_path_factory):
    """The requests of the forced schedules, each generated alone."""

    root = tmp_path_factory.mktemp("single")
    return {
        expression: _run(root, label, expression)
        for label, expression in (("A1", "d d~ > g g"), ("B1", "u u~ > e+ e-"))
    }


@pytest.mark.parametrize("schedule", sorted(SCHEDULES))
def test_concurrent_generations_keep_their_own_model_caches(
    singles, tmp_path, monkeypatch, schedule
):
    """Generation A (a thread) is held inside a model-cache operation while
    generation B runs to its end in this thread: both succeed, with the
    stored plans and values of the same requests generated alone."""

    import importlib

    from pyamplicol.loops.v2 import dag_input

    module, name, marker = SCHEDULES[schedule]
    function = getattr(importlib.import_module(f"pyamplicol.loops.v2.{module}"), name)
    monkeypatch.setattr(dag_input, "_MODEL_ROWS_KEPT", 1)
    lines, first = source.getsourcelines(function)
    (held,) = (first + k for k, text in enumerate(lines) if marker in text)
    paused, finished = threading.Event(), threading.Event()
    outcome: dict[str, object] = {}

    def local(frame, event, _arg):
        if event == "line" and frame.f_lineno == held and not paused.is_set():
            outcome["held"] = True
            paused.set()
            assert finished.wait(300), "generation B did not finish"
        return local

    def tracer(frame, event, _arg):
        return local if frame.f_code is function.__code__ else None

    def generation_a():
        sys.settrace(tracer)
        try:
            outcome["A"] = _run(tmp_path, "A", "d d~ > g g")
        except BaseException as error:  # reported below
            outcome["A"] = error
        finally:
            sys.settrace(None)
            paused.set()

    thread = threading.Thread(target=generation_a)
    thread.start()
    try:
        assert paused.wait(300), "generation A never reached the cache operation"
        outcome["B"] = _run(tmp_path, "B", "u u~ > e+ e-")
    finally:
        finished.set()
        thread.join(300)
    assert not thread.is_alive()
    assert outcome.get("held"), "generation A was never held"
    a, b = outcome["A"], outcome["B"]
    assert isinstance(a, Path), a
    assert isinstance(b, Path), b
    # The stored plans and values of the same requests generated alone.
    for expression, concurrent in (("d d~ > g g", a), ("u u~ > e+ e-", b)):
        single = singles[expression]
        plan = "loop-runtime.pacbin"
        assert (_process(concurrent) / plan).read_bytes() == (
            _process(single) / plan
        ).read_bytes()
        assert _values(concurrent) == _values(single)
    assert _caches_empty()
