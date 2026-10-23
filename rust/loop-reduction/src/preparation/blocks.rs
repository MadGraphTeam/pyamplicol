// SPDX-License-Identifier: 0BSD

use std::collections::{BTreeMap, BTreeSet};

use feynkit_model::Model;
use rusticol_core::loop_v2::generate::families::LegSet;

use super::{
    MassId, Orders, mass_id, normalize_orders, orders_within, structural_zeros, vertex_orders,
};

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ExternalLeg {
    pub index: usize,
    /// All fields enter the current: physical outgoing legs are conjugated.
    pub field: String,
    pub mass: MassId,
    pub colour: i64,
}

#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub struct BlockCurrent {
    pub mask: LegSet,
    pub field: String,
    pub orders: Orders,
}

/// Memoized native port of `ModelBlockTable`, including its proper-subset rule.
/// Every current represents all trees with the same fields and coupling orders;
/// it does not enumerate or evaluate individual Feynman diagrams.
pub struct ModelBlockTable {
    legs: Vec<ExternalLeg>,
    cap: Orders,
    merges: BTreeMap<Vec<String>, BTreeSet<(String, Orders)>>,
    arity: usize,
    table: BTreeMap<LegSet, Vec<BlockCurrent>>,
    full: LegSet,
}

impl ModelBlockTable {
    pub fn new(
        model: &Model,
        incoming: &[&str],
        outgoing: &[&str],
        cap: Orders,
    ) -> Result<Self, String> {
        let count = incoming
            .len()
            .checked_add(outgoing.len())
            .ok_or("external multiplicity overflows usize")?;
        if !(1..=64).contains(&count) {
            return Err(
                "the native family generator uses u64 leg masks and requires 1..=64 external legs"
                    .into(),
            );
        }
        if cap.iter().any(|(name, power)| {
            *power < 0 || !model.orders().iter().any(|order| order.name == *name)
        }) {
            return Err(
                "current coupling-order caps must name declared orders with nonnegative powers"
                    .into(),
            );
        }
        let cap = normalize_orders(cap)?;
        let zeros = structural_zeros(model)?;
        let mut legs = Vec::with_capacity(count);
        for (index, name) in incoming.iter().chain(outgoing).enumerate() {
            let particle = model.particle(name).map_err(|e| e.to_string())?;
            let particle = if index < incoming.len() {
                particle
            } else {
                model
                    .particle_by_id(particle.antiparticle)
                    .map_err(|e| e.to_string())?
            };
            legs.push(ExternalLeg {
                index,
                field: particle.name.clone(),
                mass: mass_id(model, particle, &zeros)?,
                colour: particle.color,
            });
        }
        let mut merges: BTreeMap<Vec<String>, BTreeSet<(String, Orders)>> = BTreeMap::new();
        for rule in model.vertex_rules() {
            let orders = vertex_orders(model, rule)?;
            for (result, particle_id) in rule.particles.iter().enumerate() {
                let particle = model
                    .particle_by_id(*particle_id)
                    .map_err(|e| e.to_string())?;
                let result_field = &model
                    .particle_by_id(particle.antiparticle)
                    .map_err(|e| e.to_string())?
                    .name;
                let mut attached = rule
                    .particles
                    .iter()
                    .enumerate()
                    .filter(|(index, _)| *index != result)
                    .map(|(_, id)| {
                        model
                            .particle_by_id(*id)
                            .map(|p| p.name.clone())
                            .map_err(|e| e.to_string())
                    })
                    .collect::<Result<Vec<_>, _>>()?;
                attached.sort();
                for order in &orders {
                    merges
                        .entry(attached.clone())
                        .or_default()
                        .insert((result_field.clone(), order.clone()));
                }
            }
        }
        let arity = merges.keys().map(Vec::len).max().unwrap_or(0);
        Ok(Self {
            legs,
            cap,
            merges,
            arity,
            table: BTreeMap::new(),
            full: u64::MAX >> (64 - count),
        })
    }

    pub fn legs(&self) -> &[ExternalLeg] {
        &self.legs
    }
    pub fn cap(&self) -> &Orders {
        &self.cap
    }
    pub fn full_mask(&self) -> LegSet {
        self.full
    }

    pub fn currents(&mut self, mask: LegSet) -> Result<&[BlockCurrent], String> {
        if mask & !self.full != 0 {
            return Err("current mask references an absent external leg".into());
        }
        if !self.table.contains_key(&mask) {
            let currents = self.build(mask)?;
            self.table.insert(mask, currents.into_iter().collect());
        }
        Ok(&self.table[&mask])
    }

    /// Materialize the proper-subset table in canonical `(mask,field,orders)` order.
    /// This scans exponentially many masks; the 64-bit representation limit is
    /// not a promise that preparing a 64-leg process is computationally feasible.
    pub fn all_currents(&mut self) -> Result<Vec<BlockCurrent>, String> {
        let mut currents = Vec::new();
        for mask in 1..self.full {
            currents.extend_from_slice(self.currents(mask)?);
        }
        Ok(currents)
    }

    fn build(&mut self, mask: LegSet) -> Result<BTreeSet<BlockCurrent>, String> {
        if mask == 0 || mask == self.full {
            return Ok(BTreeSet::new());
        }
        if mask.is_power_of_two() {
            return Ok([BlockCurrent {
                mask,
                field: self.legs[mask.trailing_zeros() as usize].field.clone(),
                orders: Vec::new(),
            }]
            .into());
        }
        let mut output = BTreeSet::new();
        visit_set_partitions(mask, 2, self.arity, |parts| {
            let options = parts
                .iter()
                .map(|&part| self.currents(part).map(<[BlockCurrent]>::to_vec))
                .collect::<Result<Vec<_>, _>>()?;
            self.combine(
                mask,
                &options,
                0,
                &mut Vec::new(),
                &mut Vec::new(),
                &mut output,
            )
        })?;
        Ok(output)
    }

    fn combine(
        &self,
        mask: LegSet,
        options: &[Vec<BlockCurrent>],
        index: usize,
        fields: &mut Vec<String>,
        orders: &mut Orders,
        output: &mut BTreeSet<BlockCurrent>,
    ) -> Result<(), String> {
        if index == options.len() {
            let mut fields = fields.clone();
            fields.sort();
            if let Some(merges) = self.merges.get(&fields) {
                for (field, vertex_orders) in merges {
                    let total =
                        normalize_orders(orders.iter().chain(vertex_orders).cloned().collect())?;
                    if orders_within(&total, &self.cap) {
                        output.insert(BlockCurrent {
                            mask,
                            field: field.clone(),
                            orders: total,
                        });
                    }
                }
            }
            return Ok(());
        }
        for current in &options[index] {
            fields.push(current.field.clone());
            let prior = orders.len();
            orders.extend_from_slice(&current.orders);
            self.combine(mask, options, index + 1, fields, orders, output)?;
            orders.truncate(prior);
            fields.pop();
        }
        Ok(())
    }
}

/// Visit unordered set partitions in the exact Python generator's order.
/// The lowest remaining bit fixes the next block, avoiding permutation copies.
/// This streams partitions, rather than allocating a Bell-number sized array.
pub fn visit_set_partitions(
    mask: LegSet,
    minimum: usize,
    maximum: usize,
    mut visitor: impl FnMut(&[LegSet]) -> Result<(), String>,
) -> Result<(), String> {
    fn split(
        rest: LegSet,
        parts: &mut Vec<LegSet>,
        minimum: usize,
        maximum: usize,
        visitor: &mut impl FnMut(&[LegSet]) -> Result<(), String>,
    ) -> Result<(), String> {
        if rest == 0 {
            if parts.len() >= minimum {
                visitor(parts)?;
            }
            return Ok(());
        }
        if parts.len() == maximum {
            return Ok(());
        }
        let low = 1u64 << rest.trailing_zeros();
        let others = rest ^ low;
        let mut sub = others;
        loop {
            parts.push(sub | low);
            split(others ^ sub, parts, minimum, maximum, visitor)?;
            parts.pop();
            if sub == 0 {
                break;
            }
            sub = (sub - 1) & others;
        }
        Ok(())
    }
    if minimum > maximum {
        return Ok(());
    }
    split(mask, &mut Vec::new(), minimum, maximum, &mut visitor)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn partitions_match_python_order_and_have_no_duplicate_unordered_covers() {
        let mut partitions = Vec::new();
        visit_set_partitions(0b111, 2, 3, |parts| {
            partitions.push(parts.to_vec());
            Ok(())
        })
        .unwrap();
        assert_eq!(
            partitions,
            vec![vec![5, 2], vec![3, 4], vec![1, 6], vec![1, 2, 4]]
        );
        let mut count = 0;
        visit_set_partitions(0b1111, 2, 4, |parts| {
            assert_eq!(parts.iter().fold(0, |a, b| a | b), 15);
            for (i, a) in parts.iter().enumerate() {
                assert!(parts[i + 1..].iter().all(|b| a & b == 0));
            }
            count += 1;
            Ok(())
        })
        .unwrap();
        assert_eq!(count, 14); // Bell(4) minus the single-block partition.
    }

    #[test]
    fn native_qcd_reachability_crossing_and_proper_subset_contract() {
        let model = Model::standard_model();
        let mut blocks =
            ModelBlockTable::new(&model, &["u", "u~"], &["g", "g"], vec![("QCD".into(), 2)])
                .unwrap();
        let fields = |rows: &[BlockCurrent]| {
            rows.iter()
                .map(|r| (r.field.clone(), r.orders.clone()))
                .collect::<Vec<_>>()
        };
        assert_eq!(
            fields(blocks.currents(3).unwrap()),
            vec![("g".into(), vec![("QCD".into(), 1)])]
        );
        assert_eq!(
            fields(blocks.currents(5).unwrap()),
            vec![("u".into(), vec![("QCD".into(), 1)])]
        );
        assert_eq!(
            fields(blocks.currents(6).unwrap()),
            vec![("u~".into(), vec![("QCD".into(), 1)])]
        );
        assert_eq!(
            fields(blocks.currents(7).unwrap()),
            vec![("g".into(), vec![("QCD".into(), 2)])]
        );
        assert!(blocks.currents(0).unwrap().is_empty());
        assert!(blocks.currents(15).unwrap().is_empty());
        assert!(blocks.currents(16).is_err());
        let crossed = ModelBlockTable::new(&model, &["g", "g"], &["u", "u~"], vec![]).unwrap();
        assert_eq!(crossed.legs()[2].field, "u~");
        assert_eq!(crossed.legs()[3].field, "u");
    }

    #[test]
    fn zero_cap_and_three_child_vertices_follow_the_model() {
        let model = Model::standard_model();
        let mut forbidden = ModelBlockTable::new(&model, &["g", "g"], &["g", "g"], vec![]).unwrap();
        assert!(forbidden.currents(3).unwrap().is_empty());
        let mut blocks =
            ModelBlockTable::new(&model, &["g", "g"], &["g", "g"], vec![("QCD".into(), 2)])
                .unwrap();
        assert_eq!(
            blocks.currents(7).unwrap(),
            &[BlockCurrent {
                mask: 7,
                field: "g".into(),
                orders: vec![("QCD".into(), 2)]
            }]
        );
        let currents = blocks.all_currents().unwrap();
        assert!(currents.windows(2).all(|rows| rows[0] < rows[1]));
        assert_eq!(currents.len(), 14);
    }

    #[test]
    fn mask_boundary_supports_bit_63_without_enumerating_subsets() {
        let model = Model::phi3();
        let mut blocks = ModelBlockTable::new(&model, &["phi"; 64], &[], vec![]).unwrap();
        assert_eq!(blocks.full_mask(), u64::MAX);
        assert_eq!(blocks.currents(1u64 << 63).unwrap()[0].field, "phi");
        assert!(blocks.currents(u64::MAX).unwrap().is_empty());
        assert!(ModelBlockTable::new(&model, &["phi"; 65], &[], vec![]).is_err());
    }

    #[test]
    fn mixed_vertex_orders_remain_alternative_monomials() {
        let mut definition: serde_json::Value =
            serde_json::from_str(&Model::phi3().to_json().unwrap()).unwrap();
        let mut second = definition["couplings"][0].clone();
        second["name"] = "SECOND_COUPLING".into();
        second["orders"][0][1] = 2.into();
        definition["couplings"].as_array_mut().unwrap().push(second);
        let lorentz = definition["vertex_rules"][0]["lorentz_structures"][0].clone();
        definition["vertex_rules"][0]["lorentz_structures"]
            .as_array_mut()
            .unwrap()
            .push(lorentz);
        definition["vertex_rules"][0]["couplings"][0]
            .as_array_mut()
            .unwrap()
            .push("SECOND_COUPLING".into());
        let model = Model::from_json(&definition.to_string()).unwrap();
        let name = model.couplings()[0].orders.keys().next().unwrap().clone();
        let mut blocks =
            ModelBlockTable::new(&model, &["phi"; 3], &[], vec![(name.clone(), 2)]).unwrap();
        assert_eq!(
            blocks
                .currents(3)
                .unwrap()
                .iter()
                .map(|current| current.orders.clone())
                .collect::<Vec<_>>(),
            vec![vec![(name.clone(), 1)], vec![(name, 2)]]
        );
    }
}
