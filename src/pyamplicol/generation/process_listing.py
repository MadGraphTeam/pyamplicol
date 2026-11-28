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
from typing import Any

from pyamplicol.api.errors import GenerationError
from pyamplicol.api.requests import ModelSource, ProcessSet
from pyamplicol.config import RunConfig

from .progress import PhaseHandle


def list_request_processes(config: RunConfig, processes: ProcessSet) -> dict[str, Any]:
    """The listing of ``processes`` under ``config`` (``pyamplicol model
    processes``'s payload)."""

    from pyamplicol.processes.model import ModelParticleCatalog

    from .service import GenerationBackend

    compiled = ModelSource.from_config(config.model).compile(
        cache_dir=config.model.cache_dir,
        use_cache=config.model.cache,
    )
    backend = GenerationBackend(config, None)
    payload = backend._private_compiled_model(compiled)
    if backend._loop_execution_enabled:
        route = "one-loop"
        rows, served, skipped = _one_loop(backend, processes, compiled)
    else:
        route = "tree"
        rows, served, skipped = _tree(backend, processes, compiled)
    catalog = ModelParticleCatalog(
        payload.ir.name, payload.ir.particles, payload.ir.parameters
    )
    multiparticles = {
        **catalog.default_multiparticles(),
        **config.process.multiparticles,
    }
    limit = config.process.max_quark_lines
    return {
        "available": True,
        "model": payload.name,
        "model_source": dict(payload.source),
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


def _source(backend: Any, compiled: Any) -> Any:
    """The model the dry run resolves: the configured source, as a
    generation resolves it (built-in prepared packs, the model cache the
    listing just filled), or, without the cache, the compiled model."""

    return None if backend._run_config.model.cache else compiled


def _planned(backend: Any, processes: ProcessSet, compiled: Any) -> Any:
    """The generator's dry run of the request: its refusals are the
    listing's."""

    plan = backend.plan(processes, model=_source(backend, compiled))
    if plan.unsupported_features:
        raise GenerationError(
            "the generation of this request is refused: "
            + "; ".join(str(item) for item in plan.unsupported_features)
        )
    return plan


def _one_loop(
    backend: Any, processes: ProcessSet, compiled: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    from pyamplicol.processes.model import build_model_process_ir

    plan = _planned(backend, processes, compiled)
    ir = backend._private_compiled_model(compiled).ir
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
    backend: Any, processes: ProcessSet, compiled: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    from dataclasses import replace

    from pyamplicol.color.plan_build import build_color_plan

    from .dag_algorithms import (
        has_model_supported_amplitudes,
        request_coupling_order_limits,
    )
    from .loop_service import _quark_line_cut
    from .singlet_exchange import require_representable_singlet_exchange

    # The mode's own admission (selections, colour accuracy, kernel packs):
    # a request its dry run refuses is refused.
    planned = {
        request.name
        for request in _planned(backend, processes, compiled).concrete_processes
    }
    resolved = backend._resolve_model_for_plan(
        _source(backend, compiled) or backend._configured_model_source()
    )
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
    limits = request_coupling_order_limits(
        explicit, model, policy=backend._coupling_order_policy
    )
    rows: list[dict[str, Any]] = []
    served: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for entry in expanded:
        if entry.request.name not in planned:
            continue
        process = entry.process_ir
        plan = build_color_plan(
            process,
            color_accuracy=backend._color_accuracy,
            fold_trace_reflections=model.lc_trace_reflection_equivalence_is_proven(
                process
            ),
        )
        if not has_model_supported_amplitudes(
            process, model=model, color_plan=plan, max_coupling_orders=limits or None
        ):
            skipped.append(
                {
                    "process": entry.request.name,
                    "expression": entry.request.expression,
                    "reason": "no tree-level diagram within the coupling-order "
                    "limits (tree generation skips it)",
                }
            )
            continue
        members = [
            member
            for member in entry.group_members
            if not member.generated and member.process_id != entry.request.name
        ]
        # The lanes' own admission of a colour-singlet exchange (a closed
        # gluon trace times an open colour line), which the dry run does not
        # run: within the limits the lanes build in, for the request's mode.
        require_representable_singlet_exchange(
            process,
            model=model,
            max_coupling_orders=request_coupling_order_limits(
                explicit,
                model,
                policy=backend._coupling_order_policy,
                infer=partial(_minimal_limits, process, model),
            )
            or None,
            execution_mode=str(backend._run_config.evaluator.execution_mode),
        )
        rows.append(_row(entry.request.name, process, [m.process_id for m in members]))
        served.extend(
            {
                "name": member.process_id,
                "process": member.expression,
                "served_by": entry.request.name,
            }
            for member in members
        )
    return rows, served, skipped
