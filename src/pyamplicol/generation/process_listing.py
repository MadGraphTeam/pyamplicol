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
    source = ModelSource.from_config(run.model)
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


def _require_selected_support(backend: Any, process: Any, model: Any) -> None:
    """With a fixed colour-sector or helicity selection, the generation's
    own check of the SELECTED content: the compiled lane's construction of
    the process (``GenerationBackend._compile_concrete_process``: the colour
    plan, the selected sectors and source helicities, the DAG), which refuses
    a selection that keeps no tree-level amplitude (a structurally vanishing
    sector or helicity) with generation's error. The dry run checks only that
    the selected IDs exist. The recurrence lane serves the same selections
    from the same amplitudes; the on-the-fly lane refuses selections in its
    dry run."""

    from dataclasses import replace

    from pyamplicol.config.models import EvaluatorExecutionMode

    from .service import GenerationBackend

    selection = backend._process_selection
    if (
        selection.selected_color_sector_ids is None
        and not selection.selected_source_helicities
    ):
        return
    run = backend._run_config
    lane = (
        backend
        if run.evaluator.execution_mode == EvaluatorExecutionMode.COMPILED
        else GenerationBackend(
            replace(
                run,
                evaluator=replace(
                    run.evaluator, execution_mode=EvaluatorExecutionMode.COMPILED
                ),
            ),
            None,
        )
    )
    lane._compile_concrete_process(process, model)


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
        _require_selected_support(backend, process, model)
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
