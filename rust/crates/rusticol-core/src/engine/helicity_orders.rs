// SPDX-License-Identifier: 0BSD

//! Squared coupling-order partials through the compiled helicity schedules.
//!
//! An execution with a compiled helicity plan materializes every physical
//! helicity through its schedule (source-state mapping and root factors):
//! the plain amplitude stage computes only the representatives. This is
//! `run_resolved_f64_with_helicity_recurrence_unprofiled` with each
//! helicity's materialized schedule reduced per squared order.

use super::*;

impl ExecutionRuntime {
    /// Order-resolved values (one [`ResolvedValues`] per squared order) of the
    /// selected physical helicities, each through its materialized schedule.
    #[allow(clippy::too_many_arguments)]
    pub(in crate::engine) fn order_resolved_with_helicity_schedules_f64(
        &mut self,
        catalog: &AmplitudeOrderCatalog,
        root_components: &[u32],
        batch: F64MomentumBatchView<'_>,
        physics: &PhysicsRuntime,
        selected_helicity_ids: Option<&BTreeSet<String>>,
        selected_color_ids: Option<&BTreeSet<String>>,
        selected_materialized_sector_ids: Option<&BTreeSet<i64>>,
    ) -> RusticolResult<Vec<ResolvedValues<f64>>> {
        if self.color_topology_replay_enabled
            || (self.lc_topology_replay_enabled && selected_materialized_sector_ids.is_none())
        {
            return Err(RusticolError::integrity(
                "topology-replay runtime cannot execute its representative materialized helicity schedule directly",
            ));
        }
        let helicity_indices = physics.selected_helicity_indices(selected_helicity_ids)?;
        let color_indices = physics.selected_color_indices(selected_color_ids)?;
        let point_count = batch.point_count();
        let component_count = helicity_indices
            .len()
            .checked_mul(color_indices.len())
            .ok_or_else(|| RusticolError::invalid_argument("resolved shape overflows usize"))?;
        let squared_count = catalog.squared_orders().len();
        let mut values = vec![vec![0.0; point_count * component_count]; squared_count];
        for (helicity_position, helicity_index) in helicity_indices.iter().copied().enumerate() {
            let schedule = self
                .compiled_helicity_execution_plan
                .as_ref()
                .and_then(|plan| {
                    plan.schedules_by_physical_helicity
                        .get(helicity_index)
                        .and_then(Option::as_ref)
                })
                .cloned()
                .ok_or_else(|| {
                    RusticolError::integrity(format!(
                        "physical helicity {} has no compiled recurrence schedule",
                        physics.manifest.helicities[helicity_index].id
                    ))
                })?;
            if schedule.structural_zero {
                continue;
            }
            let per_order = self.order_resolved_materialized_helicity_schedule_f64(
                catalog,
                root_components,
                batch,
                physics,
                selected_color_ids,
                selected_materialized_sector_ids,
                &schedule,
            )?;
            if per_order.len() != squared_count {
                return Err(RusticolError::integrity(
                    "materialized helicity order reduction returned the wrong number of orders",
                ));
            }
            for (target, selected) in values.iter_mut().zip(&per_order) {
                if selected.color_indices != color_indices || selected.point_count != point_count
                {
                    return Err(RusticolError::integrity(
                        "materialized helicity schedule returned an inconsistent resolved shape",
                    ));
                }
                for point in 0..point_count {
                    let source = point * color_indices.len();
                    let destination =
                        point * component_count + helicity_position * color_indices.len();
                    target[destination..destination + color_indices.len()]
                        .copy_from_slice(&selected.values[source..source + color_indices.len()]);
                }
            }
        }
        Ok(values
            .into_iter()
            .map(|values| ResolvedValues {
                values,
                point_count,
                helicity_indices: helicity_indices.clone(),
                color_indices: color_indices.clone(),
            })
            .collect())
    }

    /// One physical helicity's materialized schedule reduced per squared
    /// order (`run_f64_materialized_helicity_schedule_unprofiled`, never the
    /// union, never a selector lane: those executions record no root orders).
    #[allow(clippy::too_many_arguments)]
    fn order_resolved_materialized_helicity_schedule_f64(
        &mut self,
        catalog: &AmplitudeOrderCatalog,
        root_components: &[u32],
        batch: F64MomentumBatchView<'_>,
        physics: &PhysicsRuntime,
        selected_color_ids: Option<&BTreeSet<String>>,
        selected_materialized_sector_ids: Option<&BTreeSet<i64>>,
        schedule: &CompiledHelicitySelectorSchedule,
    ) -> RusticolResult<Vec<ResolvedValues<f64>>> {
        #[cfg(any(feature = "f64-compiled", feature = "f64-symjit"))]
        if self.compiled_direct_runtime.is_some() {
            let color_indices = physics.selected_color_indices(selected_color_ids)?;
            let point_count = batch.point_count();
            let squared_count = catalog.squared_orders().len();
            let mut values = vec![vec![0.0; point_count * color_indices.len()]; squared_count];
            let Self {
                compiled_direct_runtime: Some(direct),
                compiled_direct_color_schedules,
                compiled_direct_helicity_schedules,
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
                    "compiled Direct-Arena helicity execution was selected without a complete runtime",
                ));
            };
            let color_schedule = bind_direct_helicity_color_schedule(
                direct,
                compiled_direct_helicity_schedules,
                compiled_direct_color_schedules,
                schedule,
                selected_materialized_sector_ids,
            )?;
            let tile_capacity = direct.reduction_tile_capacity();
            let mut point_start = 0usize;
            while point_start < point_count {
                let point_stop = (point_start + tile_capacity).min(point_count);
                direct.begin_tile_from_inputs(
                    batch.subview(point_start, point_stop)?,
                    sources,
                    Some(&schedule.source_states),
                    *external_count,
                    particle_masses,
                    momentum_slots,
                    external_is_initial,
                    model_parameter_values_f64,
                )?;
                evaluate_direct_helicity_schedule(
                    direct,
                    compiled_direct_helicity_schedules,
                    schedule,
                    color_schedule.as_deref(),
                    false,
                    point_stop - point_start,
                )?;
                let resolved = amplitude.reduce_planes_f64_order_resolved_for_materialized_helicity(
                    direct.amplitude_planes()?,
                    physics,
                    *normalization_factor,
                    schedule.physical_helicity_index,
                    &schedule.root_factors,
                    selected_color_ids,
                    catalog,
                    root_components,
                )?;
                for (target, tile) in values.iter_mut().zip(&resolved) {
                    if tile.color_indices != color_indices
                        || tile.point_count != point_stop - point_start
                    {
                        return Err(RusticolError::integrity(
                            "compiled Direct-Arena materialized-helicity order reducer returned an inconsistent shape",
                        ));
                    }
                    target[point_start * color_indices.len()..point_stop * color_indices.len()]
                        .copy_from_slice(&tile.values);
                }
                point_start = point_stop;
            }
            return Ok(values
                .into_iter()
                .map(|values| ResolvedValues {
                    values,
                    point_count,
                    helicity_indices: vec![schedule.physical_helicity_index],
                    color_indices: color_indices.clone(),
                })
                .collect());
        }
        self.evaluate_f64_materialized_helicity_schedule_unprofiled(
            batch,
            selected_materialized_sector_ids,
            schedule,
            false,
        )?;
        self.amplitude_stage
            .as_ref()
            .expect("generic amplitude stage checked")
            .reduce_scratch_f64_order_resolved_for_materialized_helicity(
                batch.point_count(),
                physics,
                self.normalization_factor,
                schedule.physical_helicity_index,
                &schedule.root_factors,
                selected_color_ids,
                catalog,
                root_components,
            )
    }
}
