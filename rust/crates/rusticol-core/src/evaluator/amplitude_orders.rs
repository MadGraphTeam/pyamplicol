// SPDX-License-Identifier: 0BSD

//! Squared coupling-order reductions of compiled amplitude roots.
//!
//! Every amplitude root of a compiled artifact has one amplitude coupling
//! order (its component, recorded at generation). A squared order `s`
//! collects the ordered component pairs `(a, b)` with `a + b = s`; its
//! partial is the ordinary reduction with the left group amplitude restricted
//! to component `a` and the right one to component `b`:
//! `P_s = sum_{a+b=s} sym Re(w L_a conj(R_b))`. The pair set of every squared
//! order is swap symmetric, so the symmetry-folded contraction entries stay
//! exact (the recurrence lane's rule). These reductions never produce totals;
//! totals are always those of the ordinary evaluation.

use super::*;

/// Component group sums of one point: `[group][component]`.
fn component_group_sums<S: AmplitudeSamples>(
    samples: S,
    row: usize,
    output_length: usize,
    groups: &[RawSumGroup],
    root_components: &[u32],
    component_count: usize,
    sums: &mut [Complex<f64>],
) {
    sums.fill(c64(0.0, 0.0));
    for (group_index, group) in groups.iter().enumerate() {
        let base = group_index * component_count;
        for &output in &group.indices {
            sums[base + root_components[output] as usize] +=
                samples.value(row, output, output_length);
        }
    }
}

/// `sum_{(a, b) in pairs} L_a conj(R_b)` over `[group][component]` sums.
#[inline]
fn ordered_pair_product(
    sums: &[Complex<f64>],
    left_group: usize,
    right_group: usize,
    component_count: usize,
    pairs: &[(u32, u32)],
) -> Complex<f64> {
    let left_base = left_group * component_count;
    let right_base = right_group * component_count;
    let mut product = c64(0.0, 0.0);
    for &(left, right) in pairs {
        product += sums[left_base + left as usize] * sums[right_base + right as usize].conj();
    }
    product
}

fn validate_root_components(
    root_components: &[u32],
    output_length: usize,
    catalog: &AmplitudeOrderCatalog,
) -> RusticolResult<()> {
    if root_components.len() != output_length {
        return Err(RusticolError::artifact(format!(
            "compiled amplitude orders name {} roots, the amplitude stage has {output_length}",
            root_components.len()
        )));
    }
    let component_count = catalog.components().len();
    if root_components
        .iter()
        .any(|component| *component as usize >= component_count)
    {
        return Err(RusticolError::artifact(
            "compiled amplitude root names an absent coupling-order component",
        ));
    }
    Ok(())
}

fn order_resolved_values(
    values: Vec<Vec<f64>>,
    point_count: usize,
    helicity_indices: &[usize],
    color_indices: &[usize],
) -> Vec<ResolvedValues<f64>> {
    values
        .into_iter()
        .map(|values| ResolvedValues {
            values,
            point_count,
            helicity_indices: helicity_indices.to_vec(),
            color_indices: color_indices.to_vec(),
        })
        .collect()
}

/// Order-resolved physical group amplitudes of one colour topology replay:
/// `[(row * group + group) * component + component]`.
pub(crate) struct ColorReplayOrderScratch {
    values: Vec<Complex<f64>>,
    covered: Vec<bool>,
    component_count: usize,
    point_count: usize,
}

impl AmplitudeRuntime {
    /// Order-resolved values of the generic row-major amplitude scratch, one
    /// [`ResolvedValues`] per squared order of `catalog`.
    #[allow(clippy::too_many_arguments)]
    pub(crate) fn reduce_scratch_f64_order_resolved(
        &self,
        batch_size: usize,
        physics: &PhysicsRuntime,
        normalization_factor: f64,
        selected_helicity_ids: Option<&BTreeSet<String>>,
        selected_color_ids: Option<&BTreeSet<String>>,
        catalog: &AmplitudeOrderCatalog,
        root_components: &[u32],
    ) -> RusticolResult<Vec<ResolvedValues<f64>>> {
        let samples = RowMajorAmplitudeSamples::new(
            &self.output_scratch_f64,
            batch_size,
            self.output_length,
        )?;
        self.reduce_amplitude_samples_f64_order_resolved(
            samples,
            batch_size,
            physics,
            normalization_factor,
            selected_helicity_ids,
            selected_color_ids,
            catalog,
            root_components,
        )
    }

    /// Plane-native counterpart of [`Self::reduce_scratch_f64_order_resolved`].
    #[allow(clippy::too_many_arguments)]
    pub(crate) fn reduce_planes_f64_order_resolved(
        &self,
        amplitudes: crate::direct_arena::DirectAmplitudePlanes<'_>,
        physics: &PhysicsRuntime,
        normalization_factor: f64,
        selected_helicity_ids: Option<&BTreeSet<String>>,
        selected_color_ids: Option<&BTreeSet<String>>,
        catalog: &AmplitudeOrderCatalog,
        root_components: &[u32],
    ) -> RusticolResult<Vec<ResolvedValues<f64>>> {
        let plane_count = usize::try_from(amplitudes.component_count()?)
            .map_err(|_| RusticolError::invalid_argument("amplitude plane count exceeds usize"))?;
        if plane_count != self.output_length {
            return Err(RusticolError::invalid_argument(format!(
                "direct amplitude plane count is {plane_count}, expected {}",
                self.output_length
            )));
        }
        self.reduce_amplitude_samples_f64_order_resolved(
            amplitudes,
            amplitudes.point_count() as usize,
            physics,
            normalization_factor,
            selected_helicity_ids,
            selected_color_ids,
            catalog,
            root_components,
        )
    }

    /// The resolved reducer (`reduce_amplitude_samples_f64_resolved`) per
    /// squared order: the same group sums, weights and contraction entries,
    /// with the left and right group amplitudes restricted to the components
    /// of each ordered pair.
    #[allow(clippy::too_many_arguments)]
    fn reduce_amplitude_samples_f64_order_resolved<S: AmplitudeSamples>(
        &self,
        amplitudes: S,
        batch_size: usize,
        physics: &PhysicsRuntime,
        normalization_factor: f64,
        selected_helicity_ids: Option<&BTreeSet<String>>,
        selected_color_ids: Option<&BTreeSet<String>>,
        catalog: &AmplitudeOrderCatalog,
        root_components: &[u32],
    ) -> RusticolResult<Vec<ResolvedValues<f64>>> {
        validate_root_components(root_components, self.output_length, catalog)?;
        let component_count = catalog.components().len();
        let squared = catalog.squared_orders();
        let groups = &self.raw_sum_groups;
        let helicity_count = physics.manifest.helicities.len();
        let color_count = physics.manifest.color_components.len();
        let helicity_indices = physics.selected_helicity_indices(selected_helicity_ids)?;
        let color_indices = physics.selected_color_indices(selected_color_ids)?;
        let mut selected_helicity_positions = vec![None; helicity_count];
        for (position, index) in helicity_indices.iter().copied().enumerate() {
            selected_helicity_positions[index] = Some(position);
        }
        let mut selected_color_positions = vec![None; color_count];
        for (position, index) in color_indices.iter().copied().enumerate() {
            selected_color_positions[index] = Some(position);
        }
        let selected_component_count = helicity_indices
            .len()
            .checked_mul(color_indices.len())
            .ok_or_else(|| RusticolError::invalid_argument("resolved shape overflows usize"))?;
        let mut values = vec![vec![0.0; batch_size * selected_component_count]; squared.len()];
        let mut sums = vec![c64(0.0, 0.0); groups.len() * component_count];

        if let Some(contraction) = self.color_contraction.as_ref() {
            if contraction.is_symmetric_group() {
                return Err(RusticolError::compatibility(
                    "compiled symmetric-group FFT diagnostic does not support squared \
                     coupling-order partials; use the direct colour contraction",
                ));
            }
            let entry_color_positions = contraction
                .entry_color_indices(physics)?
                .into_iter()
                .map(|index| selected_color_positions[index])
                .collect::<Vec<_>>();
            if groups.len() != contraction.group_count {
                return Err(RusticolError::invalid_argument(
                    "colour contraction group count does not match coherent groups",
                ));
            }
            let entries = contraction.logical_entries().collect::<Vec<_>>();
            let mut selected_helicity_weights_by_entry = Vec::with_capacity(entries.len());
            for entry in &entries {
                let left_group = &groups[entry.left_group_index];
                let right_group = &groups[entry.right_group_index];
                let reduction_of = |group: &RawSumGroup| {
                    physics
                        .numeric_reduction_by_group_id
                        .get(&group.id)
                        .ok_or_else(|| {
                            RusticolError::invalid_argument(format!(
                                "resolved metadata is missing coherent group {}",
                                group.id
                            ))
                        })
                };
                let left_reduction = reduction_of(left_group)?;
                let right_reduction = reduction_of(right_group)?;
                if left_reduction.physical_helicity_indices
                    != right_reduction.physical_helicity_indices
                {
                    return Err(RusticolError::invalid_argument(
                        "colour contraction mixed distinct physical helicities",
                    ));
                }
                let left_weights = &left_reduction.normalized_helicity_weights;
                let right_weights = &right_reduction.normalized_helicity_weights;
                if left_weights.len() != right_weights.len()
                    || left_weights.iter().zip(right_weights).any(
                        |((left_index, left_weight), (right_index, right_weight))| {
                            left_index != right_index
                                || left_weight.to_bits() != right_weight.to_bits()
                        },
                    )
                {
                    return Err(RusticolError::invalid_argument(
                        "colour contraction groups have inconsistent helicity weights",
                    ));
                }
                selected_helicity_weights_by_entry.push(
                    left_weights
                        .iter()
                        .copied()
                        .filter_map(|(helicity_index, weight)| {
                            selected_helicity_positions[helicity_index]
                                .map(|position| (position, weight))
                        })
                        .collect::<Vec<_>>(),
                );
            }
            for row in 0..batch_size {
                component_group_sums(
                    amplitudes,
                    row,
                    self.output_length,
                    groups,
                    root_components,
                    component_count,
                    &mut sums,
                );
                for ((entry, weights), color_position) in entries
                    .iter()
                    .zip(&selected_helicity_weights_by_entry)
                    .zip(&entry_color_positions)
                {
                    let Some(color_position) = *color_position else {
                        continue;
                    };
                    for (order_values, order) in values.iter_mut().zip(squared) {
                        let product = ordered_pair_product(
                            &sums,
                            entry.left_group_index,
                            entry.right_group_index,
                            component_count,
                            order.pairs(),
                        );
                        let contribution = normalization_factor
                            * entry.symmetry_factor
                            * (entry.weight_re * product.re - entry.weight_im * product.im);
                        for (helicity_position, weight) in weights {
                            order_values[row * selected_component_count
                                + *helicity_position * color_indices.len()
                                + color_position] += contribution * weight;
                        }
                    }
                }
            }
        } else {
            if !self.has_coherent_groups {
                return Err(RusticolError::invalid_argument(
                    "squared coupling-order partials require coherent amplitude-group metadata",
                ));
            }
            let mut selected_member_weights_by_group = Vec::with_capacity(groups.len());
            for group in groups {
                let reduction = physics
                    .numeric_reduction_by_group_id
                    .get(&group.id)
                    .ok_or_else(|| {
                        RusticolError::invalid_argument(format!(
                            "resolved metadata is missing coherent group {}",
                            group.id
                        ))
                    })?;
                selected_member_weights_by_group.push(
                    reduction
                        .normalized_member_weights
                        .iter()
                        .copied()
                        .filter_map(|(helicity_index, color_index, weight)| {
                            Some((
                                selected_helicity_positions[helicity_index]?,
                                selected_color_positions[color_index]?,
                                weight,
                            ))
                        })
                        .collect::<Vec<_>>(),
                );
            }
            for row in 0..batch_size {
                component_group_sums(
                    amplitudes,
                    row,
                    self.output_length,
                    groups,
                    root_components,
                    component_count,
                    &mut sums,
                );
                for (group_index, (group, member_weights)) in groups
                    .iter()
                    .zip(&selected_member_weights_by_group)
                    .enumerate()
                {
                    for (order_values, order) in values.iter_mut().zip(squared) {
                        let product = ordered_pair_product(
                            &sums,
                            group_index,
                            group_index,
                            component_count,
                            order.pairs(),
                        );
                        let contribution =
                            normalization_factor * group.all_sector_weight * product.re;
                        for (helicity_position, color_position, weight) in member_weights {
                            order_values[row * selected_component_count
                                + *helicity_position * color_indices.len()
                                + *color_position] += contribution * weight;
                        }
                    }
                }
            }
        }
        Ok(order_resolved_values(
            values,
            batch_size,
            &helicity_indices,
            &color_indices,
        ))
    }

    /// Start an order-resolved colour topology replay of `batch_size` points.
    pub(crate) fn begin_color_topology_replay_orders(
        &self,
        batch_size: usize,
        component_count: usize,
    ) -> RusticolResult<ColorReplayOrderScratch> {
        let replay = self.color_topology_replay.as_ref().ok_or_else(|| {
            RusticolError::integrity(
                "color topology replay was requested without its amplitude gather",
            )
        })?;
        let scalar_count = batch_size
            .checked_mul(replay.physical_groups.len())
            .and_then(|count| count.checked_mul(component_count))
            .ok_or_else(|| {
                RusticolError::invalid_argument(
                    "order-resolved color topology replay shape overflows usize",
                )
            })?;
        Ok(ColorReplayOrderScratch {
            values: vec![c64(0.0, 0.0); scalar_count],
            covered: vec![false; replay.physical_groups.len()],
            component_count,
            point_count: batch_size,
        })
    }

    /// Route one relabelled evaluation (generic scratch) into the
    /// order-resolved physical groups.
    pub(crate) fn gather_color_topology_replay_order_mapping(
        &self,
        scratch: &mut ColorReplayOrderScratch,
        batch_size: usize,
        mapping_index: usize,
        root_components: &[u32],
    ) -> RusticolResult<()> {
        let samples = RowMajorAmplitudeSamples::new(
            &self.output_scratch_f64,
            batch_size,
            self.output_length,
        )?;
        self.gather_color_topology_replay_order_samples(
            scratch,
            samples,
            batch_size,
            0,
            mapping_index,
            root_components,
        )
    }

    /// Plane-native counterpart of [`Self::gather_color_topology_replay_order_mapping`].
    pub(crate) fn gather_color_topology_replay_order_planes(
        &self,
        scratch: &mut ColorReplayOrderScratch,
        amplitudes: crate::direct_arena::DirectAmplitudePlanes<'_>,
        target_row_start: usize,
        mapping_index: usize,
        root_components: &[u32],
    ) -> RusticolResult<()> {
        let plane_count = usize::try_from(amplitudes.component_count()?)
            .map_err(|_| RusticolError::invalid_argument("amplitude plane count exceeds usize"))?;
        if plane_count != self.output_length {
            return Err(RusticolError::integrity(
                "color topology replay direct amplitude width is inconsistent",
            ));
        }
        self.gather_color_topology_replay_order_samples(
            scratch,
            amplitudes,
            amplitudes.point_count() as usize,
            target_row_start,
            mapping_index,
            root_components,
        )
    }

    fn gather_color_topology_replay_order_samples<S: AmplitudeSamples>(
        &self,
        scratch: &mut ColorReplayOrderScratch,
        amplitudes: S,
        batch_size: usize,
        target_row_start: usize,
        mapping_index: usize,
        root_components: &[u32],
    ) -> RusticolResult<()> {
        let replay = self.color_topology_replay.as_ref().ok_or_else(|| {
            RusticolError::integrity(
                "color topology replay was requested without its amplitude gather",
            )
        })?;
        if root_components.len() != self.output_length {
            return Err(RusticolError::artifact(
                "compiled amplitude orders do not match the replayed amplitude stage",
            ));
        }
        let mapping = replay.mappings.get(mapping_index).ok_or_else(|| {
            RusticolError::integrity(
                "color topology replay requested an unknown external-label mapping",
            )
        })?;
        let group_count = replay.physical_groups.len();
        let component_count = scratch.component_count;
        if target_row_start
            .checked_add(batch_size)
            .is_none_or(|stop| stop > scratch.point_count)
        {
            return Err(RusticolError::integrity(
                "color topology replay target row range exceeds its physical scratch",
            ));
        }
        for route in &mapping.group_routes {
            if target_row_start == 0 {
                if std::mem::replace(&mut scratch.covered[route.target_group_index], true) {
                    return Err(RusticolError::integrity(
                        "color topology replay attempted to materialize a physical group twice",
                    ));
                }
            } else if !scratch.covered[route.target_group_index] {
                return Err(RusticolError::integrity(
                    "color topology replay direct tiles arrived out of order",
                ));
            }
            let source_group = &self.raw_sum_groups[route.source_group_index];
            for row in 0..batch_size {
                let base = ((target_row_start + row) * group_count + route.target_group_index)
                    * component_count;
                let target = &mut scratch.values[base..base + component_count];
                target.fill(c64(0.0, 0.0));
                for &output in &source_group.indices {
                    target[root_components[output] as usize] +=
                        amplitudes.value(row, output, self.output_length);
                }
                for value in target {
                    *value *= route.factor;
                }
            }
        }
        Ok(())
    }

    /// Order-resolved counterpart of `reduce_color_topology_replay_f64_resolved`.
    #[allow(clippy::too_many_arguments)]
    pub(crate) fn reduce_color_topology_replay_f64_order_resolved(
        &self,
        scratch: &ColorReplayOrderScratch,
        physics: &PhysicsRuntime,
        normalization_factor: f64,
        selected_helicity_ids: Option<&BTreeSet<String>>,
        selected_color_ids: Option<&BTreeSet<String>>,
        catalog: &AmplitudeOrderCatalog,
    ) -> RusticolResult<Vec<ResolvedValues<f64>>> {
        let replay = self.color_topology_replay.as_ref().ok_or_else(|| {
            RusticolError::integrity(
                "color topology replay was requested without its amplitude gather",
            )
        })?;
        if scratch.covered.iter().any(|covered| !covered) {
            return Err(RusticolError::integrity(
                "color topology replay did not materialize every physical amplitude group",
            ));
        }
        if scratch.component_count != catalog.components().len() {
            return Err(RusticolError::integrity(
                "order-resolved color topology replay changed its component count",
            ));
        }
        let layout = ColorReplayResolvedLayout::new(
            replay,
            physics,
            selected_helicity_ids,
            selected_color_ids,
        )?;
        let component_count = layout.component_count()?;
        let batch_size = scratch.point_count;
        let squared = catalog.squared_orders();
        let order_components = scratch.component_count;
        let group_count = replay.physical_groups.len();
        let mut values = vec![vec![0.0; batch_size * component_count]; squared.len()];
        for row in 0..batch_size {
            let sums = &scratch.values
                [row * group_count * order_components..(row + 1) * group_count * order_components];
            for (entry, color_position) in layout.entries.iter().zip(&layout.entry_color_positions)
            {
                let Some(color_position) = *color_position else {
                    continue;
                };
                for (order_values, order) in values.iter_mut().zip(squared) {
                    let product = ordered_pair_product(
                        sums,
                        entry.left_group_index,
                        entry.right_group_index,
                        order_components,
                        order.pairs(),
                    );
                    let contribution = normalization_factor
                        * entry.symmetry_factor
                        * (entry.weight_re * product.re - entry.weight_im * product.im);
                    for (helicity_index, weight) in &layout.members_by_group[entry.left_group_index]
                    {
                        let Some(position) = layout.selected_positions[*helicity_index] else {
                            continue;
                        };
                        order_values[row * component_count
                            + position * layout.color_indices.len()
                            + color_position] += contribution * weight;
                    }
                }
            }
        }
        Ok(order_resolved_values(
            values,
            batch_size,
            &layout.helicity_indices,
            &layout.color_indices,
        ))
    }
}
