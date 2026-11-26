// SPDX-License-Identifier: 0BSD

//! Squared coupling-order partials of compiled artifacts.
//!
//! Generation records the amplitude coupling-order component of every
//! amplitude root of the primary and helicity-sum executions in the
//! `amplitude_orders` extension of the process physics. Partials are reduced
//! from the same root outputs as the ordinary resolved evaluation (the
//! helicity-sum execution when it serves the selection, else the primary
//! one), through the plain amplitude stage, the LC topology replay or the
//! full-colour topology replay; the ordinary evaluation and its totals are
//! never modified.

use super::*;

/// Kind of the `amplitude_orders` physics extension of compiled artifacts.
pub(in crate::engine) const COMPILED_AMPLITUDE_ORDERS_KIND: &str =
    "pyamplicol-compiled-amplitude-orders-v1";
pub(in crate::engine) const COMPILED_AMPLITUDE_ORDERS_EXTENSION: &str = "amplitude_orders";

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct CompiledAmplitudeOrdersManifest {
    kind: String,
    names: Vec<String>,
    components: Vec<Vec<u32>>,
    executions: BTreeMap<String, Vec<u32>>,
}

/// Amplitude coupling-order components of the roots of a compiled process.
#[derive(Debug)]
pub(in crate::engine) struct CompiledAmplitudeOrders {
    catalog: AmplitudeOrderCatalog,
    primary: Box<[u32]>,
    helicity_sum: Option<Box<[u32]>>,
}

impl CompiledAmplitudeOrders {
    /// The orders a compiled process records; `None` for artifacts written
    /// before generation recorded them.
    pub(in crate::engine) fn from_physics(
        physics: &ProcessPhysicsV1,
    ) -> RusticolResult<Option<Self>> {
        let Some(value) = physics.extensions.get(COMPILED_AMPLITUDE_ORDERS_EXTENSION) else {
            return Ok(None);
        };
        let manifest: CompiledAmplitudeOrdersManifest = serde_json::from_value(value.clone())
            .map_err(|error| {
                RusticolError::artifact(format!(
                    "compiled amplitude coupling orders are invalid: {error}"
                ))
            })?;
        if manifest.kind != COMPILED_AMPLITUDE_ORDERS_KIND {
            return Err(RusticolError::artifact(format!(
                "unsupported compiled amplitude coupling-order kind {:?}",
                manifest.kind
            )));
        }
        if manifest.names.windows(2).any(|pair| pair[0] >= pair[1])
            || manifest
                .components
                .windows(2)
                .any(|pair| pair[0] >= pair[1])
        {
            return Err(RusticolError::artifact(
                "compiled amplitude coupling orders are not strictly ascending",
            ));
        }
        let catalog = AmplitudeOrderCatalog::from_components(
            manifest.names.into_boxed_slice(),
            manifest
                .components
                .into_iter()
                .map(Vec::into_boxed_slice)
                .collect(),
        )?;
        let mut executions = manifest.executions;
        let primary = executions.remove("primary").ok_or_else(|| {
            RusticolError::artifact("compiled amplitude coupling orders have no primary execution")
        })?;
        let helicity_sum = executions.remove("helicity_sum");
        if let Some(name) = executions.keys().next() {
            return Err(RusticolError::artifact(format!(
                "compiled amplitude coupling orders name an unknown execution {name:?}"
            )));
        }
        let component_count = catalog.components().len();
        if primary
            .iter()
            .chain(helicity_sum.iter().flatten())
            .any(|component| *component as usize >= component_count)
        {
            return Err(RusticolError::artifact(
                "compiled amplitude root names an absent coupling-order component",
            ));
        }
        Ok(Some(Self {
            catalog,
            primary: primary.into_boxed_slice(),
            helicity_sum: helicity_sum.map(Vec::into_boxed_slice),
        }))
    }

    pub(in crate::engine) const fn catalog(&self) -> &AmplitudeOrderCatalog {
        &self.catalog
    }
}

/// Typed refusal of a compiled artifact without recorded amplitude orders.
pub(in crate::engine) fn compiled_orders_unrecorded() -> RusticolError {
    RusticolError::compatibility(
        "this compiled artifact records no amplitude coupling orders (it predates \
         squared coupling-order partials in the compiled lane); regenerate it to \
         evaluate partials",
    )
}

impl ExecutionRuntime {
    /// Point-major squared coupling-order partials (`[point][squared order]`)
    /// with the global selectors of the ordinary evaluation.
    pub(in crate::engine) fn run_order_partials_f64(
        &mut self,
        orders: &CompiledAmplitudeOrders,
        batch: F64MomentumBatchView<'_>,
        selected_helicity_ids: Option<&BTreeSet<String>>,
        selected_color_ids: Option<&BTreeSet<String>>,
        partials: &mut [f64],
    ) -> RusticolResult<()> {
        let point_count = batch.point_count();
        let squared_count = orders.catalog.squared_orders().len();
        if partials.len() != point_count * squared_count {
            return Err(RusticolError::invalid_argument(format!(
                "partial output has length {}, expected {}",
                partials.len(),
                point_count * squared_count
            )));
        }
        if self.has_compiled_symmetric_group_diagnostic() {
            return Err(
                self.compiled_symmetric_group_unsupported("squared coupling-order partials")
            );
        }
        let (selected_helicity_ids, selected_color_ids) =
            self.physics
                .as_ref()
                .map_or((selected_helicity_ids, selected_color_ids), |physics| {
                    (
                        physics.canonical_total_helicity_selector(selected_helicity_ids),
                        physics.canonical_total_color_selector(selected_color_ids),
                    )
                });
        let resolved = match (
            self.helicity_sum_runtime.as_mut(),
            orders.helicity_sum.as_deref(),
        ) {
            (Some(sum_runtime), Some(roots)) => sum_runtime.order_resolved_f64(
                &orders.catalog,
                roots,
                batch,
                selected_helicity_ids,
                selected_color_ids,
            )?,
            (None, _) => self.order_resolved_f64(
                &orders.catalog,
                &orders.primary,
                batch,
                selected_helicity_ids,
                selected_color_ids,
            )?,
            (Some(_), None) => {
                return Err(RusticolError::artifact(
                    "compiled amplitude coupling orders omit the helicity-sum execution",
                ));
            }
        };
        if resolved.len() != squared_count {
            return Err(RusticolError::integrity(
                "order-resolved reduction returned the wrong number of squared orders",
            ));
        }
        partials.fill(0.0);
        for (squared_index, values) in resolved.iter().enumerate() {
            let totals = resolved_f64_totals(values)?;
            if totals.len() != point_count {
                return Err(RusticolError::integrity(
                    "order-resolved reduction returned the wrong number of points",
                ));
            }
            for (point, total) in totals.into_iter().enumerate() {
                partials[point * squared_count + squared_index] = total;
            }
        }
        Ok(())
    }

    /// Order-resolved values (one [`ResolvedValues`] per squared order) of
    /// this execution, whose amplitude roots carry `root_components`.
    fn order_resolved_f64(
        &mut self,
        catalog: &AmplitudeOrderCatalog,
        root_components: &[u32],
        batch: F64MomentumBatchView<'_>,
        selected_helicity_ids: Option<&BTreeSet<String>>,
        selected_color_ids: Option<&BTreeSet<String>>,
    ) -> RusticolResult<Vec<ResolvedValues<f64>>> {
        let physics = self.physics.clone().ok_or_else(|| {
            RusticolError::artifact(
                "squared coupling-order partials require resolved physics metadata",
            )
        })?;
        if self.stages.is_none() || self.amplitude_stage.is_none() {
            return Err(self.execution_unavailable_error());
        }
        if self.color_topology_replay_enabled {
            return self.order_resolved_color_topology_replay_f64(
                catalog,
                root_components,
                batch,
                &physics,
                selected_helicity_ids,
                selected_color_ids,
            );
        }
        if self.lc_topology_replay_enabled {
            return self.order_resolved_lc_topology_replay_f64(
                catalog,
                root_components,
                batch,
                &physics,
                selected_helicity_ids,
                selected_color_ids,
            );
        }
        self.order_resolved_materialized_f64(
            catalog,
            root_components,
            batch,
            &physics,
            selected_helicity_ids,
            selected_color_ids,
            None,
        )
    }

    /// Evaluate the materialized amplitude stage (all roots, or those of
    /// `selected_color_sector_ids`) and reduce it per squared order.
    #[allow(clippy::too_many_arguments)]
    fn order_resolved_materialized_f64(
        &mut self,
        catalog: &AmplitudeOrderCatalog,
        root_components: &[u32],
        batch: F64MomentumBatchView<'_>,
        physics: &PhysicsRuntime,
        selected_helicity_ids: Option<&BTreeSet<String>>,
        selected_color_ids: Option<&BTreeSet<String>>,
        selected_color_sector_ids: Option<&BTreeSet<i64>>,
    ) -> RusticolResult<Vec<ResolvedValues<f64>>> {
        #[cfg(any(feature = "f64-compiled", feature = "f64-symjit"))]
        if self.compiled_direct_runtime.is_some() {
            let point_count = batch.point_count();
            let Self {
                compiled_direct_runtime: Some(direct),
                compiled_direct_color_schedules,
                sources,
                external_count,
                particle_masses,
                momentum_slots,
                external_is_initial,
                model_parameter_values_f64,
                amplitude_stage: Some(amplitude),
                normalization_factor,
                ..
            } = self
            else {
                return Err(RusticolError::integrity(
                    "compiled Direct-Arena order split was selected without a complete runtime",
                ));
            };
            let helicity_indices = physics.selected_helicity_indices(selected_helicity_ids)?;
            let color_indices = physics.selected_color_indices(selected_color_ids)?;
            let component_count = helicity_indices.len() * color_indices.len();
            let squared_count = catalog.squared_orders().len();
            let mut values = vec![vec![0.0; point_count * component_count]; squared_count];
            let tile_capacity = direct.reduction_tile_capacity();
            let mut point_start = 0usize;
            while point_start < point_count {
                let point_stop = (point_start + tile_capacity).min(point_count);
                let tile = batch.subview(point_start, point_stop)?;
                direct.begin_tile_from_inputs(
                    tile,
                    sources,
                    None,
                    *external_count,
                    particle_masses,
                    momentum_slots,
                    external_is_initial,
                    model_parameter_values_f64,
                )?;
                evaluate_direct_color_schedule(
                    direct,
                    compiled_direct_color_schedules,
                    selected_color_sector_ids,
                    point_stop - point_start,
                )?;
                let resolved = amplitude.reduce_planes_f64_order_resolved(
                    direct.amplitude_planes()?,
                    physics,
                    *normalization_factor,
                    selected_helicity_ids,
                    selected_color_ids,
                    catalog,
                    root_components,
                )?;
                for (target, tile_values) in values.iter_mut().zip(&resolved) {
                    if tile_values.helicity_indices != helicity_indices
                        || tile_values.color_indices != color_indices
                        || tile_values.point_count != point_stop - point_start
                    {
                        return Err(RusticolError::integrity(
                            "compiled Direct-Arena order reducer returned an inconsistent shape",
                        ));
                    }
                    target[point_start * component_count..point_stop * component_count]
                        .copy_from_slice(&tile_values.values);
                }
                point_start = point_stop;
            }
            return Ok(values
                .into_iter()
                .map(|values| ResolvedValues {
                    values,
                    point_count,
                    helicity_indices: helicity_indices.clone(),
                    color_indices: color_indices.clone(),
                })
                .collect());
        }
        self.evaluate_f64_materialized_selected_unprofiled(batch, selected_color_sector_ids)?;
        self.amplitude_stage
            .as_ref()
            .expect("generic amplitude stage checked")
            .reduce_scratch_f64_order_resolved(
                batch.point_count(),
                physics,
                self.normalization_factor,
                selected_helicity_ids,
                selected_color_ids,
                catalog,
                root_components,
            )
    }

    /// `run_resolved_f64_with_lc_topology_replay_unprofiled` per squared
    /// order, through the materialized amplitude stage of every source flow.
    fn order_resolved_lc_topology_replay_f64(
        &mut self,
        catalog: &AmplitudeOrderCatalog,
        root_components: &[u32],
        batch: F64MomentumBatchView<'_>,
        physics: &Arc<PhysicsRuntime>,
        selected_helicity_ids: Option<&BTreeSet<String>>,
        selected_color_ids: Option<&BTreeSet<String>>,
    ) -> RusticolResult<Vec<ResolvedValues<f64>>> {
        let replay_plan = self.cached_lc_resolved_replay_plan(physics)?;
        let selection = self.cached_lc_resolved_replay_selection(
            physics,
            replay_plan.as_ref(),
            selected_helicity_ids,
            selected_color_ids,
        )?;
        let n_points = batch.point_count();
        let component_count = selection.helicity_indices.len() * selection.color_indices.len();
        let squared_count = catalog.squared_orders().len();
        let mut full_values = vec![vec![0.0; n_points * component_count]; squared_count];
        let mappings = self.lc_topology_replay_mappings.clone();
        let mappings_per_chunk = replay_mappings_per_expanded_batch(n_points);
        for source_group in &selection.source_groups {
            let materialized_sector_ids =
                self.lc_materialized_sector_ids_for_color_ids(physics, &source_group.color_ids)?;
            for chunk_start in (0..source_group.mapping_indices.len()).step_by(mappings_per_chunk) {
                let chunk_end = usize::min(
                    chunk_start + mappings_per_chunk,
                    source_group.mapping_indices.len(),
                );
                let mapping_chunk = source_group.mapping_indices[chunk_start..chunk_end]
                    .iter()
                    .map(|mapping_index| mappings[*mapping_index].clone())
                    .collect::<Vec<_>>();
                let entry_chunk = &source_group.entries[chunk_start..chunk_end];
                let expanded_batch = if mapping_chunk.len() == 1 && mapping_chunk[0].is_empty() {
                    None
                } else {
                    Some(apply_lc_topology_label_permutations_from_view(
                        batch,
                        self.external_count,
                        &mapping_chunk,
                    )?)
                };
                let evaluation_view = if let Some(expanded_batch) = expanded_batch.as_deref() {
                    F64MomentumBatchView::from_nested(expanded_batch, self.external_count)?
                } else {
                    batch
                };
                let materialized = self.order_resolved_materialized_f64(
                    catalog,
                    root_components,
                    evaluation_view,
                    physics,
                    Some(&source_group.helicity_ids),
                    Some(&source_group.color_ids),
                    Some(&materialized_sector_ids),
                )?;
                for (target, values) in full_values.iter_mut().zip(&materialized) {
                    accumulate_selected_lc_replay_resolved_f64(
                        target,
                        n_points,
                        values,
                        entry_chunk,
                        source_group.source_component_count,
                        component_count,
                    )?;
                }
            }
        }
        Ok(full_values
            .into_iter()
            .map(|values| ResolvedValues {
                values,
                point_count: n_points,
                helicity_indices: selection.helicity_indices.clone(),
                color_indices: selection.color_indices.clone(),
            })
            .collect())
    }

    /// `run_resolved_f64_with_color_topology_replay_unprofiled` per squared order.
    fn order_resolved_color_topology_replay_f64(
        &mut self,
        catalog: &AmplitudeOrderCatalog,
        root_components: &[u32],
        batch: F64MomentumBatchView<'_>,
        physics: &PhysicsRuntime,
        selected_helicity_ids: Option<&BTreeSet<String>>,
        selected_color_ids: Option<&BTreeSet<String>>,
    ) -> RusticolResult<Vec<ResolvedValues<f64>>> {
        let mappings = Arc::clone(&self.color_topology_replay_mappings);
        let component_count = catalog.components().len();
        let mut scratch = self
            .amplitude_stage
            .as_ref()
            .ok_or_else(|| {
                RusticolError::integrity("color topology replay has no executable amplitude stage")
            })?
            .begin_color_topology_replay_orders(batch.point_count(), component_count)?;
        let mut flat_momenta = std::mem::take(&mut self.color_replay_flat_momenta_scratch);
        let result = (|| {
            for (mapping_index, mapping) in mappings.iter().enumerate() {
                let evaluation_view = if mapping.is_empty() {
                    batch
                } else {
                    apply_lc_topology_label_permutation_from_view_into_flat(
                        batch,
                        self.external_count,
                        mapping,
                        &mut flat_momenta,
                    )?;
                    F64MomentumBatchView::from_contiguous_prevalidated(
                        &flat_momenta,
                        batch.point_count(),
                        self.external_count,
                        None,
                    )?
                };
                self.gather_order_color_topology_replay_mapping(
                    &mut scratch,
                    evaluation_view,
                    mapping_index,
                    root_components,
                )?;
            }
            self.amplitude_stage
                .as_ref()
                .expect("color topology replay amplitude stage preflighted")
                .reduce_color_topology_replay_f64_order_resolved(
                    &scratch,
                    physics,
                    self.normalization_factor,
                    selected_helicity_ids,
                    selected_color_ids,
                    catalog,
                )
        })();
        self.color_replay_flat_momenta_scratch = flat_momenta;
        result
    }

    fn gather_order_color_topology_replay_mapping(
        &mut self,
        scratch: &mut ColorReplayOrderScratch,
        batch: F64MomentumBatchView<'_>,
        mapping_index: usize,
        root_components: &[u32],
    ) -> RusticolResult<()> {
        #[cfg(any(feature = "f64-compiled", feature = "f64-symjit"))]
        if self.compiled_direct_runtime.is_some() {
            let Self {
                compiled_direct_runtime: Some(direct),
                sources,
                external_count,
                particle_masses,
                momentum_slots,
                external_is_initial,
                model_parameter_values_f64,
                amplitude_stage: Some(amplitude),
                ..
            } = self
            else {
                return Err(RusticolError::integrity(
                    "compiled color replay selected an incomplete Direct-Arena runtime",
                ));
            };
            let tile_capacity = direct.tile_capacity();
            let mut point_start = 0usize;
            while point_start < batch.point_count() {
                let point_stop = (point_start + tile_capacity).min(batch.point_count());
                let tile = batch.subview(point_start, point_stop)?;
                direct.begin_tile_from_inputs(
                    tile,
                    sources,
                    None,
                    *external_count,
                    particle_masses,
                    momentum_slots,
                    external_is_initial,
                    model_parameter_values_f64,
                )?;
                direct.evaluate_all(point_stop - point_start)?;
                amplitude.gather_color_topology_replay_order_planes(
                    scratch,
                    direct.amplitude_planes()?,
                    point_start,
                    mapping_index,
                    root_components,
                )?;
                point_start = point_stop;
            }
            return Ok(());
        }
        self.evaluate_f64_materialized_selected_unprofiled(batch, None)?;
        self.amplitude_stage
            .as_ref()
            .expect("color topology replay amplitude stage checked")
            .gather_color_topology_replay_order_mapping(
                scratch,
                batch.point_count(),
                mapping_index,
                root_components,
            )
    }
}
