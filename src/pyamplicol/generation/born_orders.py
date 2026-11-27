# SPDX-License-Identifier: 0BSD
"""Coupling orders of the Born amplitudes behind one normalization payload.

A model whose stage evaluators omit the coupling constants (the built-in SM)
restores them with a global factor whose powers are the amplitude coupling
orders of the Born. ``RuntimeNormalizationRequest`` hands a model's
``runtime_normalization_payload`` the process and, computed only when the
model asks, those orders: from the amplitude roots of a compiled DAG, or,
before any DAG exists, from the closures the generation's coupling-order
limits admit (over the generation's colour plan, or colour-blind where the
generation builds none).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping

from .._internal.qed_order_weights import (
    NORMALIZATION_ALPHA_EW,
    NORMALIZATION_ALPHA_S,
    QED_ORDER_WEIGHTED_COUPLING_POLICY,
)
from ..api.errors import GenerationError
from ..color.plan import GenericColorPlan
from ..models.base import CouplingOrders, Model, Vertex
from ..processes.ir import CanonicalProcessIR
from .dag_algorithms import (
    _closure_totals_from_color_plan,
    _minimal_coupling_order_limits_from_totals,
)
from .dag_reachability import (
    _combine_coupling_order_tuples,
    _coupling_orders_within_limits,
    _normalize_coupling_order_limits,
)
from .dag_types import GenericDAG


def runtime_normalization_payload(
    model: Model, request: RuntimeNormalizationRequest
) -> dict[str, object]:
    """``model.runtime_normalization_payload``, also for several Born orders.

    A model whose stage evaluators carry local vertex couplings only and whose
    global factor (4 pi alpha_s)^q (8 pi alpha_ew)^e restores g_s and e (its
    run-time normalization inputs are ``NORMALIZATION_ALPHA_S`` and
    ``NORMALIZATION_ALPHA_EW``) cannot weigh Born amplitudes of different
    (q, e) with that one factor. For such a Born the payload of one of its
    orders is rewritten to the QED-order-weighted policy
    (``QED_ORDER_WEIGHTED_COUPLING_POLICY``); every other request is the
    model's own payload, unchanged.
    """

    # Models without the two run-time inputs keep their own payload; the Born
    # orders (which need the process DAG) are read only for the others.
    parameter_defaults = getattr(
        model, "runtime_normalization_parameter_defaults", None
    )
    defaults = parameter_defaults() if callable(parameter_defaults) else {}
    if NORMALIZATION_ALPHA_S not in defaults or NORMALIZATION_ALPHA_EW not in defaults:
        return dict(model.runtime_normalization_payload(request))
    totals = request.born_amplitude_orders
    if len(totals) <= 1:
        return dict(model.runtime_normalization_payload(request))
    process = request.process.process
    powers: set[tuple[int, int]] = set()
    for total in totals:
        orders = {str(name).upper(): int(value) for name, value in total if value}
        unknown = sorted(set(orders) - {"QCD", "QED"})
        if unknown:
            raise GenerationError(
                f"process {process!r} has Born amplitudes of coupling orders "
                f"{unknown!r} without a global-coupling normalization"
            )
        powers.add((orders.get("QCD", 0), orders.get("QED", 0)))
    if len({qcd + qed for qcd, qed in powers}) != 1:
        listed = ", ".join(f"QCD^{qcd} QED^{qed}" for qcd, qed in sorted(powers))
        raise GenerationError(
            f"process {process!r} has Born amplitudes of different total coupling "
            f"orders ({listed}); a QED-order weight needs one total order"
        )
    _require_qed_order_weightable_vertices(model, process)
    reference = min(totals)
    payload = dict(
        model.runtime_normalization_payload(
            RuntimeNormalizationRequest(request.process, lambda: (reference,))
        )
    )
    total_order = next(iter(powers))[0] + next(iter(powers))[1]
    alpha_s = float(defaults[NORMALIZATION_ALPHA_S])
    payload.update(
        {
            "qcd_coupling_power": total_order,
            "electroweak_coupling_power": 0,
            "global_coupling_factor": (4.0 * math.pi * alpha_s) ** total_order,
            "couplings_in_stage_evaluators": True,
            "coupling_policy": QED_ORDER_WEIGHTED_COUPLING_POLICY,
        }
    )
    return payload


def _require_qed_order_weightable_vertices(model: Model, process: str) -> None:
    """Every vertex with a run-time coupling has exactly one QED order, and
    every vertex with a QED order has a run-time coupling: then weighting each
    coupling slot by rho weighs every amplitude by rho^QED."""

    lowering_rule = getattr(model, "vertex_lowering_rule", None)
    if not callable(lowering_rule):
        raise GenerationError(
            f"process {process!r} has Born amplitudes of several coupling orders "
            "and its model declares no vertex lowering rules to weigh them"
        )
    for vertex in model.vertices:
        orders = tuple(
            (str(name).upper(), int(value))
            for name, value in model.vertex_coupling_orders(vertex)
            if value
        )
        runtime_coupling = lowering_rule(int(vertex.kind)).coupling_mode == "vertex"
        if orders == (("QED", 1),) and runtime_coupling:
            continue
        if orders == (("QCD", 1),) and not runtime_coupling:
            continue
        raise GenerationError(
            f"process {process!r} has Born amplitudes of several coupling orders, "
            f"but model vertex kind {vertex.kind} {vertex.particles} (orders "
            f"{orders!r}, run-time coupling {runtime_coupling}) cannot carry a "
            "QED-order weight"
        )


class RuntimeNormalizationRequest:
    """The process of one normalization payload and its Born coupling orders."""

    __slots__ = ("_orders", "_provider", "process")

    def __init__(
        self,
        process: CanonicalProcessIR,
        born_amplitude_orders: Callable[[], Iterable[CouplingOrders]] | None = None,
    ) -> None:
        self.process = process
        self._provider = born_amplitude_orders
        self._orders: frozenset[CouplingOrders] | None = None

    @classmethod
    def of_dag(cls, dag: GenericDAG, model: Model) -> RuntimeNormalizationRequest:
        return cls(dag.process, lambda: dag_born_amplitude_orders(dag, model))

    @property
    def born_amplitude_orders(self) -> frozenset[CouplingOrders]:
        """Distinct total coupling orders of the Born amplitudes."""

        if self._orders is None:
            if self._provider is None:
                raise TypeError(
                    f"normalization of {self.process.process!r} was requested "
                    "without the coupling orders of its Born amplitudes"
                )
            self._orders = frozenset(
                _combine_coupling_order_tuples(tuple(orders))
                for orders in self._provider()
            )
        return self._orders


def dag_born_amplitude_orders(
    dag: GenericDAG,
    model: Model,
) -> frozenset[CouplingOrders]:
    """Total coupling orders of the amplitude roots of a compiled DAG.

    A vertex closure adds its vertex's orders to those of its two currents;
    every other root contracts its currents directly.
    """

    vertices: dict[tuple[int, tuple[int, ...]], Vertex] = {}
    for model_vertex in model.vertices:
        vertices.setdefault(
            (int(model_vertex.kind), tuple(model_vertex.particles)), model_vertex
        )
    orders: set[CouplingOrders] = set()
    for root in dag.amplitude_roots:
        left = dag.currents[root.left_id].index
        right = dag.currents[root.right_id].index
        if root.kind != "vertex-closure":
            orders.add(
                _combine_coupling_order_tuples(
                    tuple(left.coupling_orders), tuple(right.coupling_orders)
                )
            )
            continue
        vertex: Vertex | None = (
            None
            if root.vertex_kind is None or root.vertex_particles is None
            else vertices.get((int(root.vertex_kind), tuple(root.vertex_particles)))
        )
        if vertex is None:
            raise ValueError(
                f"amplitude root {root.id} of {dag.process.process!r} names no "
                f"model vertex {root.vertex_kind} {root.vertex_particles}"
            )
        orders.add(
            _combine_coupling_order_tuples(
                tuple(model.combine_coupling_orders(left, right, vertex))
            )
        )
    return frozenset(orders)


def process_born_amplitude_orders(
    process: CanonicalProcessIR,
    *,
    model: Model,
    max_coupling_orders: Mapping[str, int] | None,
    color_plan: GenericColorPlan | None = None,
    closure_totals: Iterable[CouplingOrders] | None = None,
    minimal: bool = False,
) -> frozenset[CouplingOrders]:
    """Total coupling orders of the closures a generation admits, pre-DAG.

    ``max_coupling_orders`` are the generation's limits; ``minimal`` narrows
    them to the minimal-order envelope, as generation does. Coupling orders
    only grow along a recursion, so the closures within the envelope are the
    envelope's subset of those within the limits: one sweep serves both, and
    ``closure_totals`` hands in one the generation already ran within the
    limits (``_closure_totals_from_color_plan``).

    The sweep runs over ``color_plan`` when the generation has one; without
    it, it is colour-blind (``_colour_blind_closure_totals``) and costs no
    colour ordering.
    """

    limits = dict(max_coupling_orders or {}) or None
    if closure_totals is not None:
        normalized = _normalize_coupling_order_limits(limits)
        totals = tuple(
            total
            for total in closure_totals
            if _coupling_orders_within_limits(total, normalized)
        )
    elif color_plan is None:
        totals = _colour_blind_closure_totals(
            process, model=model, max_coupling_orders=limits
        )
    else:
        totals = _closure_totals_from_color_plan(
            process,
            model=model,
            color_plan=color_plan,
            max_coupling_orders=limits,
        )
    if minimal:
        envelope = _minimal_coupling_order_limits_from_totals(totals, model=model)
        if envelope:
            totals = tuple(
                total
                for total in totals
                if _coupling_orders_within_limits(total, envelope)
            )
    return frozenset(totals)


def _colour_blind_closure_totals(
    process: CanonicalProcessIR,
    *,
    model: Model,
    max_coupling_orders: Mapping[str, int] | None,
) -> tuple[CouplingOrders, ...]:
    """The closure sweep of ``_closure_totals_from_color_plan`` without colour.

    An empty colour plan keeps the sweep's species, coupling-order and
    process-level vertex filters (``ColorEngine.vertex_allowed`` reads only the
    process and the model) and closes on the canonical sink leg. Every tree
    reaches every external leg, so one sink sees all of their totals, over
    O(3^n) leg-set splits instead of the (n-1)! orderings of an LC colour plan.
    What it drops, the pruning of current leg sets to segments of LC colour
    words, could only remove the totals of trees no colour word keeps planar;
    over the built-in-SM sweep processes (LC and full colour, minimal and
    explicit orders) both sweeps give the same totals.
    """

    return _closure_totals_from_color_plan(
        process,
        model=model,
        color_plan=GenericColorPlan(
            process=process, color_accuracy=process.color_accuracy, sectors=()
        ),
        max_coupling_orders=max_coupling_orders,
        color_order_mask_pruning=False,
    )
