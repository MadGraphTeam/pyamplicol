// SPDX-License-Identifier: 0BSD

//! Squared coupling-order partials of the on-the-fly lane.
//!
//! The ordinary family of a selection evaluates one amplitude per query. For
//! partials, every query trace splits into one trace per amplitude
//! coupling-order component it reaches (`split_trace_by_amplitude_order`),
//! and a query family of those traces runs in an executor of its own (the
//! lane's executor retains exactly one family: the warm ordinary family
//! stays untouched). Partials are the ordinary reductions with the left and
//! right amplitudes of every ordered component pair:
//! `P_s = sum_{(a,b) in s} B(A_a, A_b)`.

use super::*;
use crate::engine::AmplitudeOrderCatalog;
use crate::engine::recurrence_load::build_on_the_fly_source_domains;
use crate::recurrence::on_the_fly::{
    OnTheFlySelectedQueryTraceV1, on_the_fly_amplitude_order_components_v1,
    resolve_on_the_fly_coupling_policy_v1, split_trace_by_amplitude_order,
};

/// The order split of one selection: its family and destinations.
struct OnTheFlyOrderFamilyV1 {
    queries: Box<[DecodedLcQueryV1]>,
    /// Per projection slot, per amplitude component: its family destination.
    destinations: Box<[Box<[Option<usize>]>]>,
    destination_count: usize,
    executor: Option<OnTheFlyQueryFamilyExecutorV1<NativeOnTheFlyPreparedExecutorResolver>>,
    point_capacity: u32,
}

/// Lazily built order state of an on-the-fly lane.
pub(in crate::engine) struct OnTheFlyOrderStateV1 {
    components: Box<[Box<[u32]>]>,
    family: Option<OnTheFlyOrderFamilyV1>,
    amplitudes: Vec<(f64, f64)>,
    source_momenta: Vec<f64>,
}

impl OnTheFlyNativeRuntime {
    /// Amplitude and squared coupling-order axes of the process (cold, once:
    /// the coupling-order sweep within the effective limits).
    pub(in crate::engine) fn amplitude_order_catalog(
        &self,
    ) -> RusticolResult<&AmplitudeOrderCatalog> {
        if let Some(catalog) = self.order_catalog.get() {
            return Ok(catalog);
        }
        let resolved;
        let coupling_policy = match self.coupling_policy.as_ref() {
            Some(policy) => policy,
            None => {
                resolved = resolve_on_the_fly_coupling_policy_v1(&self.templates, &self.seed)?;
                &resolved
            }
        };
        let (names, components) =
            on_the_fly_amplitude_order_components_v1(&self.templates, &self.seed, coupling_policy)?;
        let catalog = AmplitudeOrderCatalog::from_components(
            names.into_boxed_slice(),
            components.into_boxed_slice(),
        )?;
        let _ = self.order_catalog.set(catalog);
        Ok(self
            .order_catalog
            .get()
            .expect("on-the-fly order catalog was just set"))
    }

    /// Helicity ordinals of the prepared contracted selection.
    pub(in crate::engine) fn contracted_helicity_ordinals(&self) -> RusticolResult<Box<[usize]>> {
        Ok(self
            .current_contracted_family()
            .ok_or_else(|| {
                RusticolError::invalid_argument(
                    "on-the-fly contracted partials require prepared queries",
                )
            })?
            .helicity_ordinals
            .clone())
    }

    fn ensure_order_state(&mut self) -> RusticolResult<()> {
        self.ensure_process_prepared()?;
        let components = self.amplitude_order_catalog()?.components().to_vec();
        if self.order_state.is_none() {
            self.order_state = Some(Box::new(OnTheFlyOrderStateV1 {
                components: components.into_boxed_slice(),
                family: None,
                amplitudes: Vec::new(),
                source_momenta: Vec::new(),
            }));
        }
        Ok(())
    }

    /// Evaluate the per-component amplitudes of `queries` (projection slot
    /// order) into the order state's amplitude scratch.
    fn execute_order_family(
        &mut self,
        queries: Vec<DecodedLcQueryV1>,
        point_major_momenta: &[f64],
        point_count: u32,
        runtime_parameters: &[f64],
    ) -> RusticolResult<()> {
        if point_count == 0 {
            return Err(RusticolError::invalid_argument(
                "on-the-fly evaluation requires at least one point",
            ));
        }
        self.ensure_order_state()?;
        let grammar = self.prepared_grammar.as_ref().ok_or_else(|| {
            RusticolError::internal("on-the-fly grammar disappeared after preparation")
        })?;
        let queries = queries
            .into_iter()
            .map(|query| grammar.canonicalize_query(&self.seed, query))
            .collect::<RusticolResult<Vec<_>>>()?;
        let state = self
            .order_state
            .as_mut()
            .expect("on-the-fly order state prepared");
        if state
            .family
            .as_ref()
            .is_none_or(|family| family.queries.as_ref() != queries.as_slice())
        {
            state.family = None;
            let coupling_policy = self.coupling_policy.as_ref().ok_or_else(|| {
                RusticolError::internal("on-the-fly coupling policy disappeared after preparation")
            })?;
            let outcomes = build_selected_lc_query_family_v1(
                &self.templates,
                &self.direct_catalog,
                &self.seed,
                coupling_policy,
                grammar,
                self.symmetric_group_color_workspace.is_some(),
                self.effective_query_construction_threads,
                queries.iter().cloned(),
            )?;
            if outcomes.len() != queries.len() {
                return Err(RusticolError::integrity(
                    "on-the-fly order trace builder changed the query count",
                ));
            }
            let component_count = state.components.len();
            let mut destinations = vec![vec![None; component_count]; queries.len()];
            let mut traces = Vec::<OnTheFlySelectedQueryTraceV1>::new();
            for ((slot, expected), outcome) in queries.iter().enumerate().zip(outcomes) {
                let OnTheFlySelectedQueryOutcomeV1::Trace(selected) = outcome else {
                    continue;
                };
                if &selected.query != expected {
                    return Err(RusticolError::integrity(
                        "on-the-fly order trace query changed during construction",
                    ));
                }
                for (component, trace, projection) in split_trace_by_amplitude_order(
                    &selected.trace,
                    selected.projection,
                    &self.templates,
                    &state.components,
                )? {
                    destinations[slot][component as usize] = Some(traces.len());
                    traces.push(OnTheFlySelectedQueryTraceV1 {
                        query: selected.query.clone(),
                        trace,
                        projection,
                    });
                }
            }
            let destination_count = traces.len();
            let executor = if traces.is_empty() {
                None
            } else {
                let resolver =
                    self.executor
                        .resolver()
                        .sibling(build_on_the_fly_source_domains(
                            &self.seed,
                            &self.templates,
                        )?)?;
                let mut executor = OnTheFlyQueryFamilyExecutorV1::new(resolver);
                // A QED-order-weighted lane (several Born orders of a model
                // whose couplings come from one global factor): the order
                // family weights its closures exactly as the ordinary one.
                executor.set_qed_order_index(self.qed_order_weights.map(|(_, _, index)| index));
                executor.resolver_mut().bind_on_the_fly_family(
                    &self.templates,
                    &self.direct_catalog,
                    &self.seed,
                    &mut traces,
                )?;
                let inputs = traces
                    .iter()
                    .map(|selected| QueryFamilyTraceInput {
                        trace: &selected.trace,
                        projection: selected.projection,
                    })
                    .collect::<Vec<_>>();
                executor.prepare(&self.direct_catalog, &inputs, point_count)?;
                let census = executor.prepared_census().ok_or_else(|| {
                    RusticolError::integrity("on-the-fly order family has no work census")
                })?;
                if usize::try_from(census.union_amplitude_destination_count).ok()
                    != Some(destination_count)
                {
                    return Err(RusticolError::integrity(
                        "on-the-fly order family does not retain one destination per component",
                    ));
                }
                Some(executor)
            };
            state.family = Some(OnTheFlyOrderFamilyV1 {
                queries: queries.into_boxed_slice(),
                destinations: destinations
                    .into_iter()
                    .map(Vec::into_boxed_slice)
                    .collect(),
                destination_count,
                executor,
                point_capacity: point_count,
            });
        }
        let family = state
            .family
            .as_mut()
            .expect("on-the-fly order family prepared");
        let Some(executor) = family.executor.as_mut() else {
            state.amplitudes.clear();
            return Ok(());
        };
        if point_count > family.point_capacity {
            executor.resize_active_family(point_count)?;
            family.point_capacity = point_count;
        }
        let prepared = projected_prepared_parameter_values(
            &self.parameter_defaults,
            &self.parameter_projection,
            runtime_parameters,
        )?;
        executor.set_parameters(&prepared)?;
        if let Some((alpha_s_slot, alpha_ew_slot, _)) = self.qed_order_weights {
            let value = |slot: usize| {
                runtime_parameters.get(slot).copied().ok_or_else(|| {
                    RusticolError::integrity("on-the-fly normalization input slot is absent")
                })
            };
            executor.set_qed_order_weight(Some(super::super::qed_order_weight_at(
                value(alpha_s_slot)?,
                value(alpha_ew_slot)?,
            )?))?;
        }
        let source_major_len = on_the_fly_source_major_momenta_into(
            &self.seed,
            point_major_momenta,
            point_count,
            4,
            &mut state.source_momenta,
        )?;
        let output_len = family
            .destination_count
            .checked_mul(point_count as usize)
            .ok_or_else(|| {
                RusticolError::invalid_argument("on-the-fly order amplitude shape exceeds usize")
            })?;
        state.amplitudes.clear();
        state.amplitudes.resize(output_len, (0.0, 0.0));
        executor.execute_into(
            &state.source_momenta[..source_major_len],
            point_count,
            &mut state.amplitudes,
        )?;
        Ok(())
    }

    /// Point-major partials (`[point][squared order]`) of the prepared LC
    /// selection: every request's coefficient times the real bilinear
    /// `Re(A_a conj(A_b))` of each ordered component pair.
    pub(in crate::engine) fn run_lc_order_partials_f64(
        &mut self,
        point_major_momenta: &[f64],
        point_count: u32,
        runtime_parameters: &[f64],
        normalization_factor: f64,
        partials: &mut [f64],
    ) -> RusticolResult<()> {
        let requests = self
            .current_family()
            .ok_or_else(|| {
                RusticolError::invalid_argument("on-the-fly partials require prepared LC queries")
            })?
            .requests
            .iter()
            .map(|request| (request.query.clone(), request.total_coefficient()))
            .collect::<Vec<_>>();
        let (queries, weights): (Vec<_>, Vec<_>) = requests.into_iter().unzip();
        self.execute_order_family(
            queries,
            point_major_momenta,
            point_count,
            runtime_parameters,
        )?;
        let catalog = self.amplitude_order_catalog()?;
        let state = self
            .order_state
            .as_ref()
            .expect("on-the-fly order state prepared");
        let family = state
            .family
            .as_ref()
            .expect("on-the-fly order family prepared");
        let squared = catalog.squared_orders();
        let point_count = point_count as usize;
        if partials.len() != point_count * squared.len() {
            return Err(RusticolError::invalid_argument(
                "on-the-fly partial output has the wrong size",
            ));
        }
        partials.fill(0.0);
        let amplitude =
            |destination: usize, point: usize| state.amplitudes[destination * point_count + point];
        for (slot, weight) in weights.iter().enumerate() {
            let weight = weight * normalization_factor;
            for (squared_index, order) in squared.iter().enumerate() {
                for &(left, right) in order.pairs() {
                    let (Some(left), Some(right)) = (
                        family.destinations[slot][left as usize],
                        family.destinations[slot][right as usize],
                    ) else {
                        continue;
                    };
                    for point in 0..point_count {
                        let (left_re, left_im) = amplitude(left, point);
                        let (right_re, right_im) = amplitude(right, point);
                        partials[point * squared.len() + squared_index] +=
                            weight * left_re.mul_add(right_re, left_im * right_im);
                    }
                }
            }
        }
        Ok(())
    }

    /// Point-major partials of a contracted (NLC/full colour) selection:
    /// the metric's real bilinear of every ordered component pair.
    #[allow(clippy::too_many_arguments)]
    pub(in crate::engine) fn run_contracted_order_partials_f64(
        &mut self,
        selectors: &OnTheFlyCompactSelectorAdapterV1,
        helicity_ordinals: &[usize],
        destination_by_owner_ordinal: &[u32],
        contraction: &RecurrenceColorContraction,
        point_major_momenta: &[f64],
        point_count: u32,
        runtime_parameters: &[f64],
        normalization_factor: f64,
        partials: &mut [f64],
    ) -> RusticolResult<()> {
        let structural_color_count = selectors.color_count();
        let slot_count = helicity_ordinals
            .len()
            .checked_mul(structural_color_count)
            .ok_or_else(|| {
                RusticolError::invalid_argument("on-the-fly contracted query shape exceeds usize")
            })?;
        let mut queries = vec![None; slot_count];
        for (helicity_position, helicity_ordinal) in helicity_ordinals.iter().enumerate() {
            for owner_ordinal in 0..structural_color_count {
                let slot = contracted_projection_index(
                    helicity_position,
                    owner_ordinal,
                    structural_color_count,
                    destination_by_owner_ordinal,
                )?;
                let query =
                    selectors.decoded_query_at(&self.seed, *helicity_ordinal, owner_ordinal)?;
                if queries[slot].replace(query).is_some() {
                    return Err(RusticolError::integrity(
                        "on-the-fly contracted projection slot is repeated",
                    ));
                }
            }
        }
        let queries = queries
            .into_iter()
            .map(|query| {
                query.ok_or_else(|| {
                    RusticolError::integrity("on-the-fly contracted projection slot is absent")
                })
            })
            .collect::<RusticolResult<Vec<_>>>()?;
        self.execute_order_family(
            queries,
            point_major_momenta,
            point_count,
            runtime_parameters,
        )?;
        let catalog = self.amplitude_order_catalog()?;
        let state = self
            .order_state
            .as_ref()
            .expect("on-the-fly order state prepared");
        let family = state
            .family
            .as_ref()
            .expect("on-the-fly order family prepared");
        let squared = catalog.squared_orders();
        let point_count = point_count as usize;
        if partials.len() != point_count * squared.len() {
            return Err(RusticolError::invalid_argument(
                "on-the-fly partial output has the wrong size",
            ));
        }
        partials.fill(0.0);
        let squared_count = squared.len();
        match contraction.runtime_reducer() {
            Some(RuntimeColorContractionReducer::SymmetricGroupFourier(reducer)) => {
                if reducer.local_group_count() != structural_color_count {
                    return Err(RusticolError::integrity(
                        "on-the-fly symmetric-group reducer disagrees with its structural owner basis",
                    ));
                }
                let pairs = squared
                    .iter()
                    .map(|order| order.pairs())
                    .collect::<Vec<_>>();
                let mut workspace =
                    reducer.pair_workspace(state.components.len(), squared_count, point_count)?;
                for helicity in 0..helicity_ordinals.len() {
                    let base = helicity * structural_color_count;
                    reducer.reduce_lane_pairs(
                        &mut workspace,
                        point_count,
                        &pairs,
                        |part, local_group, lane| {
                            let Some(destination) = family.destinations[base + local_group][part]
                            else {
                                return Ok((0.0, 0.0));
                            };
                            Ok(state.amplitudes[destination * point_count + lane])
                        },
                    )?;
                    for squared_index in 0..squared_count {
                        for (point, value) in workspace
                            .reduced(squared_index, point_count)?
                            .iter()
                            .enumerate()
                        {
                            partials[point * squared_count + squared_index] +=
                                normalization_factor * value;
                        }
                    }
                }
                return Ok(());
            }
            Some(RuntimeColorContractionReducer::Walsh(_)) => {
                return Err(RusticolError::integrity(
                    "on-the-fly contracted execution does not support Walsh color storage",
                ));
            }
            None => {}
        }
        for entry in contraction.runtime_entries() {
            let left_color = usize::try_from(entry.left_destination_id).map_err(|_| {
                RusticolError::artifact("on-the-fly contracted left destination exceeds usize")
            })?;
            let right_color = usize::try_from(entry.right_destination_id).map_err(|_| {
                RusticolError::artifact("on-the-fly contracted right destination exceeds usize")
            })?;
            if left_color >= structural_color_count || right_color >= structural_color_count {
                return Err(RusticolError::integrity(
                    "on-the-fly contracted metric destination is outside its structural basis",
                ));
            }
            for helicity in 0..helicity_ordinals.len() {
                let base = helicity * structural_color_count;
                let left_slot = &family.destinations[base + left_color];
                let right_slot = &family.destinations[base + right_color];
                for (squared_index, order) in squared.iter().enumerate() {
                    for &(left, right) in order.pairs() {
                        let (Some(left), Some(right)) =
                            (left_slot[left as usize], right_slot[right as usize])
                        else {
                            continue;
                        };
                        for point in 0..point_count {
                            let (left_re, left_im) = state.amplitudes[left * point_count + point];
                            let (right_re, right_im) =
                                state.amplitudes[right * point_count + point];
                            partials[point * squared_count + squared_index] += normalization_factor
                                * entry
                                    .contract_real_bilinear(left_re, left_im, right_re, right_im);
                        }
                    }
                }
            }
        }
        Ok(())
    }
}
