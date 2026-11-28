# SPDX-License-Identifier: 0BSD
"""The concrete processes a generation of a request produces, listed without
generating them (``pyamplicol model processes``).

The listing runs the generator's own expansion with the request's settings,
so it shows exactly the processes a generation stores, in its order and
under its names:

* a one-loop request (``process.loop_coupling_orders``): the one-loop dry
  run's processes (``loop_service.plan_loop_generation``: the expansion,
  ``process.max_quark_lines``, the routing of Born-less members by
  ``process.loop_induced``), with its skipped members;
* a tree-level request: the tree expansion (``GenerationBackend.
  _expand_process_set`` with the tree refusal of requests without a tree
  diagram: the built-in SM's own catalogue and filters, or a model's
  catalogue with its conserved charges and the quark-line cut), without the
  members that have no tree-level closure within the request's coupling-order
  limits, which tree generation skips. That check may over-estimate (as the
  generation's own pre-check), never drop a process with amplitudes.

A request the generation refuses is refused here with the same error.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
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
        route, rows, skipped = "one-loop", *_one_loop(backend, processes, compiled)
    else:
        route, rows, skipped = "tree", *_tree(backend, processes, compiled)
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
        "n_entries": len(rows),
        **({"max_quark_lines": limit} if limit is not None else {}),
        "multiparticles": {
            name: list(values) for name, values in sorted(multiparticles.items())
        },
        "entries": rows,
        "skipped": skipped,
    }


def _row(name: str, process_ir: Any, members: Sequence[Any] = ()) -> dict[str, Any]:
    return {
        "name": name,
        "key": process_ir.key,
        "process": process_ir.process,
        "ir": process_ir.to_json_dict(),
        **(
            {
                "served_members": [
                    {"name": member.process_id, "process": member.expression}
                    for member in members
                    if not member.generated
                ]
            }
            if members
            else {}
        ),
    }


def _one_loop(
    backend: Any, processes: ProcessSet, compiled: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from pyamplicol.processes.model import build_model_process_ir

    plan = backend.plan(processes, model=compiled)
    if plan.unsupported_features:
        raise GenerationError(
            "the generation of this request is refused: "
            + "; ".join(str(item) for item in plan.unsupported_features)
        )
    ir = backend._private_compiled_model(compiled).ir
    accuracy = str(backend._run_config.color.accuracy)
    rows = [
        _row(
            request.name,
            build_model_process_ir(request.expression, ir, color_accuracy=accuracy),
        )
        for request in plan.concrete_processes
    ]
    skipped = [
        dict(record)
        for record in plan.estimated_coverage.get("skipped_members", ())
        if isinstance(record, Mapping)
    ]
    return rows, skipped


def _tree(
    backend: Any, processes: ProcessSet, compiled: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from dataclasses import replace

    from pyamplicol.color.plan_build import build_color_plan

    from .dag_algorithms import (
        has_model_supported_amplitudes,
        request_coupling_order_limits,
    )
    from .loop_service import _quark_line_cut

    resolved = backend._resolve_model_for_plan(compiled)
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
    rows, skipped = [], []
    for entry in expanded:
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
        rows.append(_row(entry.request.name, process, entry.group_members))
    return rows, skipped
