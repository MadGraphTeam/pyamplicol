// SPDX-License-Identifier: 0BSD

//! Native, model-derived field reachability for the loop-prefix generator.
//!
//! These tables replace the Python producers in `loops/v2/families.py`.
//! They describe fields and coupling orders, not numerical tree currents,
//! colour contractions, or executable loop numerators. Scalar specialization
//! is delegated to FeynKit and retained exactly for subsequent kernel preparation.

mod blocks;
mod catalogue;
mod prepared;

pub use blocks::{BlockCurrent, ExternalLeg, ModelBlockTable, visit_set_partitions};
pub use catalogue::{
    LoopSpecies, LoopVertex, ModelLoopCatalogue, SpeciesOrders, VertexSignature, momentum_degree,
};
pub use prepared::{LoopOrderSelection, PreparedFamilies, PreparedModel};

use feynkit_model::{Model, Particle};
use std::collections::BTreeMap;

pub type Orders = Vec<(String, i64)>;

/// Symbolic mass/width identity; a numerical zero does not change a family key.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct MassId {
    pub mass: String,
    pub width: String,
}

impl MassId {
    pub fn massless(&self) -> bool {
        self.mass == "0" && self.width == "0"
    }
}

pub fn mass_name(name: &str) -> String {
    if matches!(name, "ZERO" | "0") {
        "0".into()
    } else {
        name.into()
    }
}

pub(crate) fn mass_id(model: &Model, particle: &Particle) -> Result<MassId, String> {
    Ok(MassId {
        mass: mass_name(
            &model
                .parameter_by_id(particle.mass)
                .map_err(|e| e.to_string())?
                .name,
        ),
        width: mass_name(
            &model
                .parameter_by_id(particle.width)
                .map_err(|e| e.to_string())?
                .name,
        ),
    })
}

pub(crate) fn normalize_orders(terms: Orders) -> Result<Orders, String> {
    let mut sums = BTreeMap::<String, i64>::new();
    for (name, power) in terms {
        let total = sums.entry(name).or_default();
        *total = total
            .checked_add(power)
            .ok_or("coupling-order sum overflows i64")?;
    }
    Ok(sums.into_iter().filter(|(_, power)| *power != 0).collect())
}

pub(crate) fn orders_within(orders: &Orders, cap: &Orders) -> bool {
    orders.iter().all(|(name, power)| {
        *power
            <= cap
                .iter()
                .find(|(other, _)| other == name)
                .map_or(0, |(_, bound)| *bound)
    })
}

/// Distinct order vectors in the coupling matrix, never their componentwise
/// maximum: that would invent interactions absent from mixed-order vertices.
pub(crate) fn vertex_orders(
    model: &Model,
    rule: &feynkit_model::VertexRule,
) -> Result<Vec<Orders>, String> {
    let mut result = std::collections::BTreeSet::new();
    for id in rule.couplings.iter().flatten().flatten() {
        let coupling = model.coupling_by_id(*id).map_err(|e| e.to_string())?;
        let terms = coupling
            .orders
            .iter()
            .map(|(name, power)| {
                Ok((
                    name.clone(),
                    i64::try_from(*power).map_err(|_| "coupling power exceeds i64")?,
                ))
            })
            .collect::<Result<Orders, String>>()?;
        result.insert(normalize_orders(terms)?);
    }
    Ok(result.into_iter().collect())
}
