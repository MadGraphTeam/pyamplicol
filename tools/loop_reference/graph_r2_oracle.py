# SPDX-License-Identifier: 0BSD
"""Independent full-D comparison for graph-derived closed-fermion kernels.

Only small test graphs are expanded here. Production coefficient generation
continues to use local dependency tensors and saved evaluator instructions.
"""

from __future__ import annotations

from symbolica import E, Replacement, S
from symbolica.community import tensor as t

from pyamplicol.loops.recurrence import (
    momentum_component_library,
    separate_local_color,
)


def graph_full_dimension_numerator(
    recurrence, bindings, *, dimension_value=None, color_seed=None
):
    """Trace the unmodified source graph in D before physical materialization."""
    from symbolica.community import hepkit as h

    graph = recurrence.graph.native
    dimension = S("graph_r2_oracle::D")
    mu = recurrence.dag.variables[4]
    full, physical = t.Representation.mink(dimension), t.Representation.mink(4)
    expression = t.TensorExpression(graph.overall_factor_expression(evaluate=True))
    for items in (graph.vertices, graph.internal_edges):
        for item in items:
            source = item.numerator_expression()
            if color_seed is None:
                source, _color = separate_local_color(source)
            expression *= source
    if color_seed is not None:
        # This small oracle expands the original graph, not the coefficient DAG.
        # Contract SU(3) first so symbolic-D reduction has only Lorentz ports.
        from symbolica import AtomType

        expanded = expression.to_expression().expand()
        terms = list(expanded) if expanded.get_type() == AtomType.Add else [expanded]
        colors, projected = {}, E("0")
        color_library = t.TensorLibrary.hep_lib_atom()
        for term in terms:
            lorentz, color = separate_local_color(t.TensorExpression(term))
            key = color.to_expression()
            if key not in colors:
                colors[key] = project_external_gluon_colors(
                    color, graph, color_library, color_seed
                ).to_tensor(color_library)[0]
            projected += colors[key] * lorentz.to_expression()
        expression = t.TensorExpression(projected)
    rules = [Replacement(symbol, value) for symbol, value in bindings.items()]
    expression = t.TensorExpression(expression.to_expression().replace_multiple(rules))
    trace = (
        expression.with_lorentz_dimension(dimension)
        .expand()
        .simplify_algebra(color=False, contract="dots")
    )
    if trace.reduction_status != t.ReductionStatus.Complete:
        raise ValueError("independent source graph D-trace is incomplete")
    library = momentum_component_library(
        recurrence.graph, (recurrence.loop_components,), recurrence.momentum_parameters
    )
    qhead = t.TensorName(h.Symbols.edge_momentum().get_name())
    vectors = {}
    for edge in graph.edges:
        vector = edge.momentum_expression(dimension=4).to_tensor(library).to_dense()
        values = [value.replace_multiple(rules).expand() for value in vector]
        vectors[edge.id] = t.Tensor.dense(qhead(edge.id, physical), values)
        library.register(vectors[edge.id])
    replacements = []
    for left in graph.edges:
        for right in graph.edges:
            if right.id < left.id:
                continue
            left_sign = left.momentum_signature().loops[0]
            right_sign = right.momentum_signature().loops[0]
            replacements.append(
                Replacement(
                    t.dot(qhead(left.id, full), qhead(right.id, full)).to_expression(),
                    vectors[left.id].dot(vectors[right.id]).to_tensor().scalar()
                    - left_sign * right_sign * mu**2,
                )
            )
    index = S("graph_r2_index_")
    replacements.extend(
        (
            Replacement(full(index).to_expression(), physical(index).to_expression()),
            Replacement(full.to_expression(), physical.to_expression()),
        )
    )
    trace = t.TensorExpression(trace.to_expression().replace_multiple(replacements))
    if dimension_value is not None:
        trace = t.TensorExpression(
            trace.to_expression().replace(dimension, dimension_value)
        )
    if dimension in trace.to_expression().get_all_symbols():
        raise NotImplementedError(
            "source graph retained an unsupported dimensional contraction"
        )
    states = dict(recurrence.external_states)
    for edge in graph.external_edges:
        half = next(half for half in graph.half_edges if half.edge.id == edge.id)
        label = h.Symbols.half_edge()(half.id, 1)
        axes = tuple(
            slot.dual()
            for slot in trace.axes
            if slot.index == label and slot.representation == physical
        )
        if not axes:
            continue
        name = t.TensorName(f"graph_r2_oracle::state{edge.external_index}")
        library.register(
            t.Tensor.dense(
                name(*(axis.representation for axis in axes)),
                [bindings[symbol] for symbol in states[edge.external_index]],
            )
        )
        trace *= name(*axes)
    result = trace.to_tensor(library).to_dense()
    if result.axes:
        raise ValueError("independent D-trace retained open physical ports")
    return result[0].replace_multiple(rules).expand()


def project_external_gluon_colors(expression, graph, library, seed):
    """Attach exact test colour vectors; the dependency contracts all SU(3) tensors."""
    from symbolica.community import hepkit as h

    for edge in graph.external_edges:
        half = next(half for half in graph.half_edges if half.edge.id == edge.id)
        label = h.Symbols.half_edge()(half.id, 1)
        axes = tuple(
            slot
            for slot in expression.axes
            if slot.index == label and slot.representation == t.Representation.coad(8)
        )
        if len(axes) != 1:
            raise ValueError("expected one external adjoint-colour slot")
        axis = axes[0]
        name = t.TensorName(f"graph_r2_oracle::color{edge.external_index}")
        values = [
            E(str(((edge.external_index + 2) * (j + seed + 1) + j * j) % 11 - 5))
            for j in range(8)
        ]
        library.register(t.Tensor.dense(name(axis.representation.dual()), values))
        expression *= name(axis.dual())
    return expression


def exact_graph_coefficients(recurrence, bindings):
    """Evaluate local coefficient instructions exactly for a small oracle point."""
    return exact_node_coefficients(recurrence, bindings)[recurrence.final_node]


def exact_node_coefficients(recurrence, bindings):
    """Return every local output, including separate closed colour alternatives."""
    physical = [Replacement(symbol, value) for symbol, value in bindings.items()]
    outputs = []
    for node in recurrence.dag.nodes:
        replacements = [
            Replacement(
                S(f"loop_coefficient::input_{position}_{column}"),
                outputs[dependency][column],
            )
            for position, dependency in enumerate(node.dependencies)
            for column in range(len(recurrence.dag.nodes[dependency].output_labels))
        ]
        outputs.append(
            tuple(
                expression.replace_multiple([*physical, *replacements]).expand()
                for expression in node.expressions
            )
        )
    return tuple(outputs)


def closed_polynomial(recurrence, coefficients, *, even=True, node=None):
    result = E("0")
    node = recurrence.dag.nodes[recurrence.final_node if node is None else node]
    if node.axes:
        raise ValueError("polynomial comparison requires a closed current")
    for label, coefficient in zip(node.output_labels, coefficients, strict=True):
        if even and len(label.powers) > 4 and label.powers[4] % 2:
            continue
        term = coefficient
        for variable, power in zip(recurrence.dag.variables, label.powers, strict=True):
            term *= variable**power
        result += term
    return result.expand()


def sample_bindings(recurrence, *, model=None):
    """Exact physical-momentum control with general off-shell vector currents."""
    momenta = (
        ("1/2", "0", "0", "1/2"),
        ("1/2", "0", "0", "-1/2"),
        ("1/2", "3/10", "0", "2/5"),
        ("1/2", "-3/10", "0", "-2/5"),
    )
    states = (
        ("1", "2", "3", "5"),
        ("2", "-1", "4", "1"),
        ("3", "2", "-1", "2"),
        ("1", "-2", "1", "3"),
    )
    values = {}
    for symbols, vector in zip(recurrence.momentum_parameters, momenta, strict=True):
        values.update(
            (symbol, E(value)) for symbol, value in zip(symbols, vector, strict=True)
        )
    for index, symbols in recurrence.external_states:
        values.update(
            (symbol, E(value))
            for symbol, value in zip(symbols, states[index], strict=True)
        )
    for symbol in recurrence.dag.parameters:
        if symbol not in values:
            name = symbol.get_name().split("::")[-1]
            if name == "MT":
                values[symbol] = E("2")
            elif name in {"MB", "MC"}:
                values[symbol] = E("0")
            elif model is not None and name.startswith("GC_"):
                values[symbol] = model.coupling(name).expression.replace(
                    S("UFO::G"), E("2/3")
                )
            elif name == "GC_10":
                values[symbol] = E("-2/3")
            elif name == "GC_11":
                values[symbol] = E("2i/3")
            else:
                raise ValueError(f"unbound oracle model parameter {name}")
    return values
