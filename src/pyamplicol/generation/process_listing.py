# SPDX-License-Identifier: 0BSD
"""The concrete processes a generation of a request produces, listed without
generating them (``pyamplicol model processes``).

The listing runs the generator's own planning for the request as given (its
execution mode, colour accuracy, selections, coupling orders, grouping), so
it shows exactly what a generation does, in its order and under its names:
the processes it STORES (``entries``) and, with flavour grouping, the
processes it SERVES through one of them (``served``, each with the stored
process ``served_by``):

* a one-loop request (``process.loop_coupling_orders``): the one-loop dry
  run (``loop_service.plan_loop_generation``: the expansion,
  ``process.max_quark_lines``, the routing of Born-less members by
  ``process.loop_induced``, the exact flavour grouping), with its skipped
  members;
* a tree-level request: the tree dry run of the request's execution mode
  (its admission: a refusal is the generation's), the processes of the
  shared tree expansion it plans (the built-in SM's own catalogue and
  filters, or a model's catalogue with its conserved charges and the
  quark-line cut, as the compiled lane applies it), without the members that
  have no tree-level closure within the request's coupling-order limits,
  which tree generation skips (the generation's own pre-check, which may
  over-estimate but never drops a process with amplitudes).

A request the generation refuses is refused here with the same error.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import partial
from pathlib import Path
from typing import Any

from pyamplicol.api.errors import GenerationError
from pyamplicol.api.requests import ModelSource, ProcessSet
from pyamplicol.config import RunConfig
from pyamplicol.config.resolver import ConfigResolution

from .progress import PhaseHandle


def list_request_processes(
    configuration: RunConfig | ConfigResolution, processes: ProcessSet
) -> dict[str, Any]:
    """The listing of ``processes`` under ``configuration`` (``pyamplicol
    model processes``'s payload): the configuration the CLI's dry run plans
    with, the model resolved by the same call (``GenerationBackend.plan``
    with the configured ``ModelSource``), so the listing refuses exactly what
    the dry run refuses (an uncompiled model included) and then what the
    generation's per-process admission refuses."""

    from pyamplicol.processes.model import ModelParticleCatalog

    from .service import GenerationBackend

    backend = GenerationBackend(configuration, None)
    run = backend._run_config
    if run is None:  # pragma: no cover - a listing is always a run configuration
        raise GenerationError("model processes requires a run configuration")
    source = _model_for(backend, ModelSource.from_config(run.model))
    if backend._loop_execution_enabled:
        route = "one-loop"
        rows, served, skipped = _one_loop(backend, processes, source)
    else:
        route = "tree"
        rows, served, skipped = _tree(backend, processes, source)
    # The model the plan resolved (it succeeded above, so this resolves).
    compiled = backend._resolve_model_for_plan(source).compiled
    multiparticles: dict[str, Sequence[str]] = {}
    if compiled is not None:
        catalog = ModelParticleCatalog(
            compiled.ir.name, compiled.ir.particles, compiled.ir.parameters
        )
        multiparticles.update(catalog.default_multiparticles())
    multiparticles.update(run.process.multiparticles)
    limit = run.process.max_quark_lines
    return {
        "available": True,
        "model": compiled.name if compiled is not None else source.kind,
        "model_source": dict(compiled.source)
        if compiled is not None
        else {"kind": source.kind},
        "route": route,
        "requests": [request.expression for request in processes.requests],
        "default_key": rows[0]["key"] if rows else None,
        # ``entries``: the processes a generation stores; ``served``: those it
        # serves through one of them (flavour grouping). Every listed name
        # loads from the generated artifact.
        "n_entries": len(rows),
        "n_stored": len(rows),
        "n_served": len(served),
        "n_addressable": len(rows) + len(served),
        **({"max_quark_lines": limit} if limit is not None else {}),
        "multiparticles": {
            name: list(values) for name, values in sorted(multiparticles.items())
        },
        "entries": rows,
        "served": served,
        "skipped": skipped,
    }


# The dry run's refusals of a model it would have to compile (the cache
# holds none yet, or caching is off): the only ones the listing resolves by
# preparing the model; every other model error is the listing's too.
_DRY_RUN_COMPILES_NO_MODEL = "dry-run does not compile external model sources"


def _model_for(backend: Any, source: ModelSource) -> Any:
    """The model the listing plans with. The configured source as the dry
    run resolves it (built-in packaged preparations, the model cache). A
    model the dry run cannot load only because it would have to compile it
    is prepared on demand by the generation's own model resolution
    (``GenerationBackend._resolve_model``: the route's admission, one-loop or
    tree, and its own errors): compiled into the cache (then planned through
    the dry run's path), or in memory without the cache (then planned with
    the prepared model). Any other model refusal of the dry run (a listed
    source refusal, a restriction the mode's packaged model does not take)
    stays the listing's, unchanged."""

    from pyamplicol.api.errors import ModelError
    from pyamplicol.api.models import _compiled_model_from_payload

    try:
        backend._resolve_model_for_plan(source)
        return source
    except ModelError as error:
        if not str(error).startswith(_DRY_RUN_COMPILES_NO_MODEL):
            raise
    resolved = backend._resolve_model(source)
    if backend._run_config.model.cache:
        return source
    return _compiled_model_from_payload(resolved.compiled)


def _row(name: str, process_ir: Any, serves: Sequence[str] = ()) -> dict[str, Any]:
    return {
        "name": name,
        "key": process_ir.key,
        "process": process_ir.process,
        # The names served through this stored process (flavour grouping).
        "serves": list(serves),
        "ir": process_ir.to_json_dict(),
    }


def _minimal_limits(
    process: Any, model: Any, bounds: Mapping[str, int]
) -> Mapping[str, int] | None:
    from .dag_algorithms import infer_minimal_coupling_order_limits

    return infer_minimal_coupling_order_limits(
        process, model=model, max_coupling_orders=bounds or None
    )


def _planned(backend: Any, processes: ProcessSet, source: Any) -> Any:
    """The generator's dry run of the request: its refusals are the
    listing's."""

    plan = backend.plan(processes, model=source)
    if plan.unsupported_features:
        raise GenerationError(
            "the generation of this request is refused: "
            + "; ".join(str(item) for item in plan.unsupported_features)
        )
    return plan


def _one_loop(
    backend: Any, processes: ProcessSet, source: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    from pyamplicol.processes.model import build_model_process_ir

    plan = _planned(backend, processes, source)
    ir = backend._resolve_model_for_plan(source).compiled.ir
    accuracy = str(backend._run_config.color.accuracy)
    coverage = {
        str(row["key"]): row
        for row in plan.estimated_coverage.get("processes", ())
        if isinstance(row, Mapping)
    }
    served = [
        {
            "name": request.name,
            "process": request.expression,
            "served_by": str(coverage[request.name]["served_by"]),
        }
        for request in plan.concrete_processes
        if "served_by" in coverage.get(request.name, {})
    ]
    serves: dict[str, list[str]] = {}
    for row in served:
        serves.setdefault(row["served_by"], []).append(row["name"])
    rows = [
        _row(
            request.name,
            build_model_process_ir(request.expression, ir, color_accuracy=accuracy),
            serves.get(request.name, ()),
        )
        for request in plan.concrete_processes
        if "served_by" not in coverage.get(request.name, {})
    ]
    skipped = [
        dict(record)
        for record in plan.estimated_coverage.get("skipped_members", ())
        if isinstance(record, Mapping)
    ]
    return rows, served, skipped


def _tree(
    backend: Any, processes: ProcessSet, source: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """The tree listing: the dry run of the request's mode, then the stages
    of that mode's generation that decide which processes it stores, short
    of writing them (``_mode_admission``)."""

    from dataclasses import replace

    from .dag_algorithms import request_coupling_order_limits
    from .loop_service import _quark_line_cut
    from .singlet_exchange import require_representable_singlet_exchange

    # The mode's own dry run (selections, colour accuracy, kernel packs): a
    # request it refuses is refused.
    planned = {
        request.name
        for request in _planned(backend, processes, source).concrete_processes
    }
    resolved = backend._resolve_model_for_plan(source)
    if resolved.model is None and resolved.compiled is not None:
        from pyamplicol.models.external import CompiledUFOModel

        resolved = replace(resolved, model=CompiledUFOModel(resolved.compiled))
    builtin = resolved.compiled is None or not resolved.use_compiled_process_catalog
    expanded = backend._expand_process_set(
        processes,
        resolved,
        PhaseHandle("model-processes", None, len(processes.requests)),
        tree_refusal=True,
        # The built-in enumeration applies the cut itself; a model's
        # catalogue takes it as the compiled lane does.
        member_filter=None
        if builtin
        else _quark_line_cut(backend._run_config.process.max_quark_lines),
    )
    model = resolved.model
    explicit = {
        str(name).upper(): int(value)
        for name, value in backend._coupling_order_limits.items()
    }
    entries = tuple(entry for entry in expanded if entry.request.name in planned)
    for entry in entries:
        # The lanes' admission of a colour-singlet exchange (a closed gluon
        # trace times an open colour line), within the limits they build in.
        require_representable_singlet_exchange(
            entry.process_ir,
            model=model,
            max_coupling_orders=request_coupling_order_limits(
                explicit,
                model,
                policy=backend._coupling_order_policy,
                infer=partial(_minimal_limits, entry.process_ir, model),
            )
            or None,
            execution_mode=str(backend._run_config.evaluator.execution_mode),
        )
    kept = _mode_admission(backend, resolved, entries)
    rows: list[dict[str, Any]] = []
    served: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = [
        {
            "process": entry.request.name,
            "expression": entry.request.expression,
            "reason": "no tree-level amplitude within the coupling-order limits "
            "(generation skips it)",
        }
        for entry in entries
        if entry.request.name not in {item.request.name for item in kept}
    ]
    for entry in kept:
        members = [
            member
            for member in entry.group_members
            if not member.generated and member.process_id != entry.request.name
        ]
        rows.append(
            _row(entry.request.name, entry.process_ir, [m.process_id for m in members])
        )
        served.extend(
            {
                "name": member.process_id,
                "process": member.expression,
                "served_by": entry.request.name,
            }
            for member in members
        )
    return rows, served, skipped


def _mode_admission(
    backend: Any, resolved: Any, entries: tuple[Any, ...]
) -> tuple[Any, ...]:
    """The processes the request's tree mode stores: its generation's own
    stages that decide it, short of code generation and writing; a process
    without an amplitude in a multiparticle request is skipped, a request
    left without one refused, as generation does.

    * compiled (and eager): each process's DAG construction
      (``_compile_for_generation``: the colour plan, a cap or the selected
      sectors and source helicities, the DAG), partitioned as generation
      partitions it;
    * recurrence: its amplitude pre-check (``_drop_processes_without_amplitudes``)
      and, with a colour-sector cap or selection or a helicity selection,
      each process's compact recurrence construction
      (``_construct_recurrence_artifact``), which decides what such a
      selection keeps (seconds per process, no code generation);
    * on-the-fly: its dry run projects every process (and refuses colour or
      helicity selections); members without an amplitude are skipped by the
      same pre-check."""

    from pyamplicol.config.models import EvaluatorExecutionMode

    from .service import _partition_model_supported_processes

    mode = backend._run_config.evaluator.execution_mode
    model = resolved.model
    phase = PhaseHandle("model-processes", None, len(entries))
    if mode in (EvaluatorExecutionMode.COMPILED, EvaluatorExecutionMode.EAGER):
        supported, _unsupported = _partition_model_supported_processes(
            [backend._compile_for_generation(entry, model, phase) for entry in entries]
        )
        return tuple(result.expanded for result in supported)
    kept = backend._drop_processes_without_amplitudes(entries, model)
    selection = backend._process_selection
    if mode == EvaluatorExecutionMode.RECURRENCE and (
        selection.selected_color_sector_ids is not None
        or selection.max_color_sectors is not None
        or selection.selected_source_helicities
    ):
        from tempfile import TemporaryDirectory

        from .recurrence_schedule_sharing import RecurrenceScheduleLoweringCache

        inputs = backend._recurrence_model_inputs(resolved)
        cache: Any = RecurrenceScheduleLoweringCache()
        with TemporaryDirectory(prefix="pyamplicol-model-processes-") as temporary:
            for index, entry in enumerate(kept):
                backend._construct_recurrence_artifact(
                    entry,
                    model,
                    inputs,
                    Path(temporary),
                    index=index,
                    phase=phase,
                    lowering_cache=cache,
                )
    return tuple(kept)
