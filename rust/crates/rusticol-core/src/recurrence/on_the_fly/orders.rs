// SPDX-License-Identifier: 0BSD

//! Amplitude coupling-order components of on-the-fly queries.
//!
//! A closure's amplitude coupling order is the coupling orders of its parent
//! currents plus the closure template's local orders (the recurrence lane's
//! rule, `direct_lowering::closure_term_amplitude_orders`). The process-wide
//! components are the viable total orders of the global coupling-order sweep
//! within the effective limits; a query trace splits into one trace per
//! component it reaches, each keeping only that component's closures, so a
//! query family of those traces evaluates every amplitude component of every
//! query separately. Nothing of the ordinary evaluation changes.

use super::super::direct_plan::DIRECT_NONE_U32;
use super::coupling_policy::viable_amplitude_orders_v1;
use super::*;

/// Coupling-order names and the amplitude components (powers over them).
pub(crate) type AmplitudeOrderComponents = (Vec<String>, Vec<Box<[u32]>>);

/// Coupling-order names (the template catalogue's, ascending) and the
/// process-wide amplitude components of an on-the-fly process.
pub(crate) fn on_the_fly_amplitude_order_components_v1(
    templates: &ValidatedRecurrenceTemplateInput,
    seed: &OnTheFlyProcessSeedV1,
    coupling_policy: &OnTheFlyResolvedCouplingPolicyV1,
) -> RusticolResult<AmplitudeOrderComponents> {
    let catalog = validate_seed_against_templates(templates, seed)?;
    let names = catalog
        .coupling_order_names()
        .iter()
        .map(|name| (*name).to_owned())
        .collect::<Vec<_>>();
    let grammar = prepare_on_the_fly_grammar_v1(templates, &catalog, seed)?;
    let limits = coupling_policy.effective_limits();
    if limits.len() != names.len() {
        return Err(integrity(
            "on-the-fly coupling-order limits do not match the template catalogue",
        ));
    }
    let components = viable_amplitude_orders_v1(templates, seed, &grammar, limits)?;
    Ok((names, components))
}

/// The amplitude coupling order of every closure operation of `trace`, by
/// operation index.
fn closure_amplitude_orders(
    trace: &OnTheFlyStructuralTraceV1,
    templates: &ValidatedRecurrenceTemplateInput,
) -> RusticolResult<BTreeMap<usize, Vec<u32>>> {
    let catalog = TemplateCatalog::new(templates.input())?;
    let current_by_base = trace
        .current_component_ranges
        .iter()
        .enumerate()
        .map(|(current, [base, _])| (*base, current))
        .collect::<BTreeMap<_, _>>();
    let parent_orders = |base: u32| -> RusticolResult<&[u32]> {
        let current = current_by_base
            .get(&base)
            .ok_or_else(|| integrity("on-the-fly closure parent is not a trace current"))?;
        Ok(trace.current_keys[*current].coupling_orders())
    };
    let mut orders = BTreeMap::new();
    for (index, operation) in trace.operations.iter().enumerate() {
        let OnTheFlyTraceOperationV1::Closure { key, row } = operation else {
            continue;
        };
        let OnTheFlyExecutorKeyV1::PreparedOperation {
            operation_kind: OnTheFlyOperationKindV1::Closure,
            operation_id,
            ..
        } = *key
        else {
            return Err(integrity(
                "on-the-fly closure operation names no closure template",
            ));
        };
        let template = templates
            .input()
            .closures
            .get(operation_id as usize)
            .ok_or_else(|| integrity("on-the-fly closure template is absent"))?;
        let mut powers = catalog.coupling_orders(template.coupling_order_set_id)?;
        let mut parents = vec![parent_orders(row.parent0_component_base)?];
        if row.parent1_component_base_or_sentinel != DIRECT_NONE_U32 {
            parents.push(parent_orders(row.parent1_component_base_or_sentinel)?);
        }
        for parent in parents {
            if parent.len() != powers.len() {
                return Err(integrity(
                    "on-the-fly current coupling orders do not match the template catalogue",
                ));
            }
            for (power, value) in powers.iter_mut().zip(parent) {
                *power = power
                    .checked_add(*value)
                    .ok_or_else(|| invalid("on-the-fly coupling order exceeds u32"))?;
            }
        }
        orders.insert(index, powers);
    }
    Ok(orders)
}

/// The traces of the amplitude components `trace` reaches: `(component,
/// trace with only that component's closures, its projection proof)`,
/// ascending by component. A closure whose order is not one of `components`
/// is refused.
pub(crate) fn split_trace_by_amplitude_order(
    trace: &OnTheFlyStructuralTraceV1,
    projection: OnTheFlyProjectionProbeV1,
    templates: &ValidatedRecurrenceTemplateInput,
    components: &[Box<[u32]>],
) -> RusticolResult<Vec<(u32, OnTheFlyStructuralTraceV1, OnTheFlyProjectionProbeV1)>> {
    let orders = closure_amplitude_orders(trace, templates)?;
    let mut component_of = BTreeMap::new();
    for (index, powers) in &orders {
        let component = components
            .binary_search_by(|candidate| candidate.as_ref().cmp(powers.as_slice()))
            .map_err(|_| {
                integrity(format!(
                    "on-the-fly closure coupling order {powers:?} is outside the process's \
                     viable amplitude orders"
                ))
            })?;
        component_of.insert(*index, component);
    }
    let reached = component_of.values().copied().collect::<BTreeSet<_>>();
    let mut traces = Vec::with_capacity(reached.len());
    for component in reached {
        let component_id = u32::try_from(component)
            .map_err(|_| invalid("on-the-fly amplitude component exceeds u32"))?;
        let split = trace
            .order_component_trace(component_id, |index| {
                component_of.get(&index) == Some(&component)
            })?
            .ok_or_else(|| integrity("on-the-fly order-component trace lost its closures"))?;
        // The retained-trace proof of the component trace: its own closures.
        let mut split_projection = projection;
        split_projection.post[2] = split.proof.closure_count();
        traces.push((component_id, split, split_projection));
    }
    Ok(traces)
}
