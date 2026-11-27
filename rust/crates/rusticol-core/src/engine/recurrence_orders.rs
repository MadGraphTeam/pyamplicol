// SPDX-License-Identifier: 0BSD

//! Squared coupling-order partials of Direct-Arena recurrence results.
//!
//! The plan records the exact amplitude coupling-order component of every
//! closure row. A squared order `s` collects the interference of every
//! ordered component pair `(a, b)` with `a + b = s`:
//! `P_s = sum_{a+b=s} Re(A_a^dagger C A_b)`. Any real-bilinear expansion of
//! the colour contraction yields these partials when evaluated on ordered
//! pairs, because the pair set of every squared order is swap symmetric.
//! The partials therefore reuse the ordinary contraction entries with
//! distinct left and right amplitudes; the total path is never modified.

use std::collections::BTreeMap;

use crate::recurrence::direct_runtime::{DirectAmplitudeOrderSplit, DirectDestinationOrders};
use crate::recurrence::{
    DirectAmplitudeOrders, DirectRecurrencePlan, RuntimeSymmetricGroupPairWorkspace,
};
use crate::{RusticolError, RusticolResult};

/// Closure exact factors that a QED-order-weighted normalization weighs by
/// `rho^QED` (`model_parameters::QedOrderWeights`).
///
/// Every closure row of an amplitude component with QED order `e > 0`
/// carries `rho^e`. The plan of such a process interns these closures' exact
/// factors per QED order (`DirectRecurrenceRuntimeOptions::
/// closure_factors_by_qed_order`), so each weighted factor ID is used by
/// closures of one QED order only and by no other row; [`Self::for_plan`]
/// checks this and refuses a plan that shares one.
#[derive(Clone, Debug)]
pub(crate) struct QedClosureFactorWeights {
    /// (factor ID, QED order, binary64 real part, binary64 imaginary part).
    entries: Box<[(usize, i32, f64, f64)]>,
}

impl QedClosureFactorWeights {
    pub(crate) fn for_plan(plan: &DirectRecurrencePlan) -> RusticolResult<Self> {
        let orders = plan.amplitude_orders();
        let Some(qed_index) = orders
            .names()
            .iter()
            .position(|name| name.eq_ignore_ascii_case("QED"))
        else {
            return Ok(Self {
                entries: Box::new([]),
            });
        };
        let closure_components = orders.closure_components();
        if closure_components.len() != plan.closures().len() {
            return Err(RusticolError::integrity(
                "recurrence closure order components do not cover every closure",
            ));
        }
        let mut weighted = BTreeMap::<usize, i32>::new();
        let mut unweighted = std::collections::BTreeSet::<usize>::new();
        for (closure, component) in plan.closures().iter().zip(closure_components) {
            let qed = orders
                .component(*component)
                .and_then(|powers| powers.get(qed_index).copied())
                .ok_or_else(|| {
                    RusticolError::integrity("recurrence closure order component is absent")
                })?;
            let id = closure.exact_factor_id as usize;
            if qed == 0 {
                unweighted.insert(id);
                continue;
            }
            let qed = i32::try_from(qed)
                .map_err(|_| RusticolError::integrity("closure QED order exceeds i32"))?;
            if *weighted.entry(id).or_insert(qed) != qed {
                return Err(RusticolError::integrity(
                    "a QED-order-weighted closure factor is shared by closures of different QED \
                     orders",
                ));
            }
        }
        let shared = |id: usize| {
            unweighted.contains(&id)
                || plan
                    .sources()
                    .iter()
                    .any(|row| row.exact_factor_id as usize == id)
                || plan
                    .contributions()
                    .iter()
                    .any(|row| row.exact_factor_id as usize == id)
                || plan
                    .finalizations()
                    .iter()
                    .any(|row| row.exact_factor_id as usize == id)
                || plan
                    .source_embeddings()
                    .iter()
                    .any(|row| row.exact_factor_id as usize == id)
                || plan
                    .source_dispatch_variants()
                    .iter()
                    .any(|row| row.crossing_exact_factor_id as usize == id)
                || plan
                    .replay_targets()
                    .iter()
                    .any(|row| row.phase_exact_factor_id as usize == id)
                || plan.closures().iter().any(|row| {
                    let start = row.component_factor_start as usize;
                    (start..start + usize::from(row.component_count)).contains(&id)
                })
        };
        let mut entries = Vec::with_capacity(weighted.len());
        for (id, qed) in weighted {
            if shared(id) {
                return Err(RusticolError::integrity(
                    "a QED-order-weighted closure factor is shared with another row: the plan \
                     was not built for a QED-order-weighted normalization",
                ));
            }
            let factor = plan.exact_factors().get(id).copied().ok_or_else(|| {
                RusticolError::integrity("recurrence closure exact factor is absent")
            })?;
            let real = factor.real().numerator() as f64 / factor.real().denominator() as f64;
            let imag = factor.imag().numerator() as f64 / factor.imag().denominator() as f64;
            entries.push((id, qed, real, imag));
        }
        Ok(Self {
            entries: entries.into_boxed_slice(),
        })
    }

    /// The `(factor ID, real, imaginary)` values at weight `rho`.
    pub(crate) fn weighted_factors(
        &self,
        rho: f64,
    ) -> impl Iterator<Item = (usize, f64, f64)> + '_ {
        self.entries.iter().map(move |(id, qed, real, imag)| {
            let weight = rho.powi(*qed);
            (*id, real * weight, imag * weight)
        })
    }

    /// Writes the weighted factors into split-complex factor planes.
    pub(crate) fn apply(&self, rho: f64, real: &mut [f64], imag: &mut [f64]) -> RusticolResult<()> {
        for (id, weighted_real, weighted_imag) in self.weighted_factors(rho) {
            match (real.get_mut(id), imag.get_mut(id)) {
                (Some(re), Some(im)) => {
                    *re = weighted_real;
                    *im = weighted_imag;
                }
                _ => {
                    return Err(RusticolError::integrity(
                        "QED-order-weighted closure factor is outside the factor planes",
                    ));
                }
            }
        }
        Ok(())
    }
}

/// One squared coupling order and its contributing ordered component pairs.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SquaredAmplitudeOrder {
    powers: Box<[u32]>,
    pairs: Box<[(u32, u32)]>,
}

impl SquaredAmplitudeOrder {
    /// Coupling powers aligned with [`AmplitudeOrderCatalog::names`].
    pub fn powers(&self) -> &[u32] {
        &self.powers
    }

    /// Ordered `(left, right)` amplitude-component pairs.
    pub fn pairs(&self) -> &[(u32, u32)] {
        &self.pairs
    }
}

/// Amplitude and squared coupling-order axes of one recurrence process.
///
/// Squared orders are every pairwise sum of amplitude components, including
/// structurally vanishing interference, in canonical coupling-order order:
/// their nonzero `(name, power)` pairs over the sorted names, compared
/// lexicographically. This is the order of Python's canonical
/// `CouplingOrders` tuples, so native, SDK and Python columns agree.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AmplitudeOrderCatalog {
    names: Box<[String]>,
    components: Box<[Box<[u32]>]>,
    squared: Box<[SquaredAmplitudeOrder]>,
}

impl AmplitudeOrderCatalog {
    pub fn from_plan(orders: &DirectAmplitudeOrders) -> RusticolResult<Self> {
        let components = (0..orders.component_count())
            .map(|component| {
                orders
                    .component(component)
                    .map(Box::<[u32]>::from)
                    .ok_or_else(|| RusticolError::integrity("amplitude order component is absent"))
            })
            .collect::<RusticolResult<Box<[Box<[u32]>]>>>()?;
        Self::from_components(orders.names().into(), components)
    }

    /// Catalog of explicit amplitude components (powers over `names`).
    pub fn from_components(
        names: Box<[String]>,
        components: Box<[Box<[u32]>]>,
    ) -> RusticolResult<Self> {
        if components.iter().any(|powers| powers.len() != names.len()) {
            return Err(RusticolError::artifact(
                "amplitude order component does not match its coupling-order names",
            ));
        }
        let mut squared = BTreeMap::<Vec<(usize, u32)>, (Vec<u32>, Vec<(u32, u32)>)>::new();
        for (left, left_powers) in components.iter().enumerate() {
            for (right, right_powers) in components.iter().enumerate() {
                let powers = left_powers
                    .iter()
                    .zip(right_powers.iter())
                    .map(|(left, right)| {
                        left.checked_add(*right).ok_or_else(|| {
                            RusticolError::integrity("squared coupling order exceeds u32")
                        })
                    })
                    .collect::<RusticolResult<Vec<_>>>()?;
                let canonical = powers
                    .iter()
                    .copied()
                    .enumerate()
                    .filter(|(_, power)| *power != 0)
                    .collect::<Vec<_>>();
                squared
                    .entry(canonical)
                    .or_insert_with(|| (powers, Vec::new()))
                    .1
                    .push((left as u32, right as u32));
            }
        }
        Ok(Self {
            names,
            components,
            squared: squared
                .into_values()
                .map(|(powers, pairs)| SquaredAmplitudeOrder {
                    powers: powers.into_boxed_slice(),
                    pairs: pairs.into_boxed_slice(),
                })
                .collect(),
        })
    }

    pub fn names(&self) -> &[String] {
        &self.names
    }

    pub fn components(&self) -> &[Box<[u32]>] {
        &self.components
    }

    pub fn squared_orders(&self) -> &[SquaredAmplitudeOrder] {
        &self.squared
    }

    /// One amplitude component: its only squared order is the total.
    pub fn is_single(&self) -> bool {
        self.components.len() == 1
    }
}

/// Lazily allocated order-resolved workspace of one recurrence runtime.
pub(super) struct RecurrenceOrderState {
    pub(super) split: DirectAmplitudeOrderSplit,
    pub(super) slots_re: Vec<f64>,
    pub(super) slots_im: Vec<f64>,
    pub(super) rows: Vec<crate::recurrence::DirectClosureRow>,
    /// Contracted colour: dense `[component][destination][point]` planes.
    pub(super) components_re: Vec<f64>,
    pub(super) components_im: Vec<f64>,
    /// Contracted Walsh colour: `[component][local group][point]` transforms.
    pub(super) transform_re: Vec<f64>,
    pub(super) transform_im: Vec<f64>,
    pub(super) symmetric_pairs: Option<RuntimeSymmetricGroupPairWorkspace>,
    /// Destination-major LC weights collected while accumulating a total.
    pub(super) lc_weights: Vec<(u32, f64)>,
}

impl RecurrenceOrderState {
    pub(super) fn new(split: DirectAmplitudeOrderSplit) -> Self {
        Self {
            split,
            slots_re: Vec::new(),
            slots_im: Vec::new(),
            rows: Vec::new(),
            components_re: Vec::new(),
            components_im: Vec::new(),
            transform_re: Vec::new(),
            transform_im: Vec::new(),
            symmetric_pairs: None,
            lc_weights: Vec::new(),
        }
    }

    /// Grow the order slots to the scheduler's current point pitch, which
    /// changes between packed-singleton and tiled layouts.
    pub(super) fn ensure_slot_capacity(&mut self, point_stride: usize) -> RusticolResult<()> {
        let needed = (self.split.slot_count() as usize)
            .checked_mul(point_stride)
            .ok_or_else(|| RusticolError::artifact("order slot workspace overflows usize"))?;
        if self.slots_re.len() < needed {
            self.slots_re.resize(needed, 0.0);
            self.slots_im.resize(needed, 0.0);
        }
        Ok(())
    }

    /// Accumulate `weight * sum_{(a,b)} Re(A_a conj(A_b))` of one LC
    /// destination into the point-major squared-order partials.
    #[allow(clippy::too_many_arguments)]
    pub(super) fn accumulate_lc_destination(
        &self,
        catalog: &AmplitudeOrderCatalog,
        amplitude_re: &[f64],
        amplitude_im: &[f64],
        destination_id: u32,
        weight: f64,
        point_stride: usize,
        point_count: usize,
        partials: &mut [f64],
    ) -> RusticolResult<()> {
        let squared_count = catalog.squared_orders().len();
        for (squared_index, squared) in catalog.squared_orders().iter().enumerate() {
            for &(left, right) in squared.pairs() {
                let amplitude = |component| {
                    order_component(
                        &self.split,
                        (&self.slots_re, &self.slots_im),
                        (amplitude_re, amplitude_im),
                        destination_id,
                        component,
                        point_stride,
                        point_count,
                    )
                };
                let (Some((left_re, left_im)), Some((right_re, right_im))) =
                    (amplitude(left)?, amplitude(right)?)
                else {
                    continue;
                };
                for point in 0..point_count {
                    partials[point * squared_count + squared_index] += weight
                        * left_re[point].mul_add(right_re[point], left_im[point] * right_im[point]);
                }
            }
        }
        Ok(())
    }
}

/// Amplitude part of `component` at `destination_id`; `None` is zero.
///
/// Single-component destinations read the ordinary amplitude planes; split
/// destinations read their replayed order slot.
pub(super) fn order_component<'a>(
    split: &DirectAmplitudeOrderSplit,
    slots: (&'a [f64], &'a [f64]),
    amplitudes: (&'a [f64], &'a [f64]),
    destination_id: u32,
    component: u32,
    point_stride: usize,
    point_count: usize,
) -> RusticolResult<Option<(&'a [f64], &'a [f64])>> {
    let orders = split.destination_orders(destination_id).ok_or_else(|| {
        RusticolError::integrity("order-resolved amplitude destination is absent")
    })?;
    let ((values_re, values_im), plane) = match orders {
        DirectDestinationOrders::Single(only) if only == component => {
            (amplitudes, destination_id as usize)
        }
        DirectDestinationOrders::Single(_) => return Ok(None),
        DirectDestinationOrders::Split { first_slot } => (slots, (first_slot + component) as usize),
    };
    let start = plane * point_stride;
    match (
        values_re.get(start..start + point_count),
        values_im.get(start..start + point_count),
    ) {
        (Some(real), Some(imaginary)) => Ok(Some((real, imaginary))),
        _ => Err(RusticolError::integrity(
            "order-resolved amplitude plane is out of bounds",
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn squared_catalog_pairs_every_ordered_component_sum() {
        let orders = DirectAmplitudeOrders {
            names: vec!["QCD".into(), "QED".into()],
            component_count: 2,
            powers: vec![0, 2, 2, 0],
            closure_components: vec![0, 1],
        };
        let catalog = AmplitudeOrderCatalog::from_plan(&orders).unwrap();
        let squared = catalog
            .squared_orders()
            .iter()
            .map(|order| (order.powers().to_vec(), order.pairs().to_vec()))
            .collect::<Vec<_>>();
        assert_eq!(
            squared,
            vec![
                (vec![2, 2], vec![(0, 1), (1, 0)]),
                (vec![4, 0], vec![(1, 1)]),
                (vec![0, 4], vec![(0, 0)]),
            ]
        );
        assert!(!catalog.is_single());
    }

    #[test]
    fn explicit_components_give_the_plan_catalog_and_check_their_width() {
        let orders = DirectAmplitudeOrders {
            names: vec!["QCD".into(), "QED".into()],
            component_count: 2,
            powers: vec![0, 2, 2, 0],
            closure_components: vec![0, 1],
        };
        let explicit = AmplitudeOrderCatalog::from_components(
            vec!["QCD".to_owned(), "QED".to_owned()].into_boxed_slice(),
            vec![vec![0, 2].into_boxed_slice(), vec![2, 0].into_boxed_slice()].into_boxed_slice(),
        )
        .unwrap();
        assert_eq!(explicit, AmplitudeOrderCatalog::from_plan(&orders).unwrap());
        let single = AmplitudeOrderCatalog::from_components(
            vec!["QCD".to_owned(), "QED".to_owned()].into_boxed_slice(),
            vec![vec![2, 0].into_boxed_slice()].into_boxed_slice(),
        )
        .unwrap();
        assert!(single.is_single());
        assert_eq!(single.squared_orders().len(), 1);
        assert!(
            AmplitudeOrderCatalog::from_components(
                vec!["QCD".to_owned()].into_boxed_slice(),
                vec![vec![2, 0].into_boxed_slice()].into_boxed_slice(),
            )
            .is_err()
        );
    }
}
