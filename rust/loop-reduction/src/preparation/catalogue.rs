// SPDX-License-Identifier: 0BSD

//! Native model tables for the loop-prefix recursion.
//!
//! This is the typed counterpart of `loops/v2/families.py::ModelLoopCatalogue`.
//! Model expressions remain exact Symbolica atoms; numerical parameter values
//! never decide whether a field, coupling order, or propagator mass is present.

use std::collections::{BTreeMap, BTreeSet};

use feynkit_model::Model;
use symbolica::{
    atom::{Atom, AtomCore, AtomView},
    domains::atom::AtomField,
    symbol,
};

use super::{MassId, Orders, mass_name, normalize_orders};

/// Perturbative species facts from the unpruned model, indexed by absolute PDG.
/// Supplying an empty map intentionally marks every species nonperturbative.
pub type SpeciesOrders = BTreeMap<u64, BTreeSet<String>>;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LoopSpecies {
    pub name: String,
    pub antiname: String,
    /// UFO `2s+1`, including the ghost value `-1`.
    pub spin: i64,
    pub colour: i64,
    pub mass: MassId,
    pub perturbative_orders: BTreeSet<String>,
}

/// Structural information used to identify interchangeable closed-loop fields.
/// Slot positions are zero based, as in the Python catalogue's signature.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct VertexSignature {
    pub lorentz_structures: Vec<String>,
    pub color_structures: Vec<Atom>,
    pub couplings: Vec<Vec<Option<String>>>,
    pub attached_in_rule_order: Vec<String>,
    pub first: usize,
    pub second: usize,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LoopVertex {
    pub rule: String,
    pub loop_in: String,
    pub attached: Vec<String>,
    pub loop_out: String,
    pub orders: Orders,
    pub q_degree: i64,
    pub signature: VertexSignature,
}

type VertexIdentity = (String, String, Vec<String>, String, Orders);

impl LoopVertex {
    fn identity(&self) -> VertexIdentity {
        (
            self.rule.clone(),
            self.loop_in.clone(),
            self.attached.clone(),
            self.loop_out.clone(),
            self.orders.clone(),
        )
    }
}

#[derive(Clone, Debug)]
pub struct ModelLoopCatalogue {
    pub species: BTreeMap<String, LoopSpecies>,
    /// Includes nonpropagating fields, which can still occur in tree blocks.
    pub conjugates: BTreeMap<String, String>,
    /// Sorted by `(rule, loop_in, attached, loop_out, orders, q_degree)`.
    pub vertices: Vec<LoopVertex>,
    pub vertices_by_loop_in: BTreeMap<String, Vec<u32>>,
    /// Vertex id after reversing the loop direction and conjugating its ends.
    pub reflected: Vec<u32>,
}

impl ModelLoopCatalogue {
    /// Construct from the already normalized native model. For a request-pruned
    /// or counterterm-augmented model, pass perturbative species facts retained
    /// from the original model. `None` derives them from single-order vertices.
    pub fn new(model: &Model, species_orders: Option<&SpeciesOrders>) -> Result<Self, String> {
        let mut rules = Vec::new();
        for rule in model.vertex_rules() {
            // Distinct order monomials remain distinct; taking the componentwise
            // maximum (VertexRule::coupling_orders) would change the recursion.
            let mut orders = BTreeSet::new();
            for coupling in rule.couplings.iter().flatten().flatten() {
                let coupling = model.coupling_by_id(*coupling).map_err(|e| e.to_string())?;
                let order = coupling
                    .orders
                    .iter()
                    .map(|(name, &power)| {
                        Ok((
                            name.clone(),
                            i64::try_from(power)
                                .map_err(|_| format!("coupling order {name} exceeds i64"))?,
                        ))
                    })
                    .collect::<Result<Orders, String>>()?;
                orders.insert(normalize_orders(order)?);
            }
            for order in orders {
                rules.push((rule, order));
            }
        }

        let mut derived = SpeciesOrders::new();
        if species_orders.is_none() {
            for (rule, order) in &rules {
                if order.len() == 1 {
                    for particle in &rule.particles {
                        let particle =
                            model.particle_by_id(*particle).map_err(|e| e.to_string())?;
                        derived
                            .entry(particle.pdg_code.unsigned_abs())
                            .or_default()
                            .insert(order[0].0.clone());
                    }
                }
            }
        }
        let species_orders = species_orders.unwrap_or(&derived);
        let mut species = BTreeMap::new();
        let mut conjugates = BTreeMap::new();
        for particle in model.particles() {
            let antiname = model
                .particle_by_id(particle.antiparticle)
                .map_err(|e| e.to_string())?
                .name
                .clone();
            conjugates.insert(particle.name.clone(), antiname.clone());
            if !particle.propagating {
                continue;
            }
            let mass = model
                .parameter_by_id(particle.mass)
                .map_err(|e| e.to_string())?;
            let width = model
                .parameter_by_id(particle.width)
                .map_err(|e| e.to_string())?;
            species.insert(
                particle.name.clone(),
                LoopSpecies {
                    name: particle.name.clone(),
                    antiname,
                    spin: particle.spin,
                    colour: particle.color,
                    mass: MassId {
                        mass: mass_name(&mass.name),
                        width: mass_name(&width.name),
                    },
                    perturbative_orders: species_orders
                        .get(&particle.pdg_code.unsigned_abs())
                        .cloned()
                        .unwrap_or_default(),
                },
            );
        }

        let mut numerator_degrees = BTreeMap::<String, i64>::new();
        let mut degree_cache = BTreeMap::<(Atom, (usize, usize)), i64>::new();
        let mut templates = BTreeMap::<VertexIdentity, LoopVertex>::new();
        for (rule, order) in rules {
            let particles = rule
                .particles
                .iter()
                .map(|id| {
                    model
                        .particle_by_id(*id)
                        .map(|particle| particle.name.clone())
                        .map_err(|e| e.to_string())
                })
                .collect::<Result<Vec<_>, _>>()?;
            let structures = rule
                .lorentz_structures
                .iter()
                .map(|id| {
                    model
                        .lorentz_structure_by_id(*id)
                        .map_err(|e| e.to_string())
                })
                .collect::<Result<Vec<_>, _>>()?;
            let couplings = rule
                .couplings
                .iter()
                .map(|row| {
                    row.iter()
                        .map(|id| {
                            id.map(|id| {
                                model
                                    .coupling_by_id(id)
                                    .map(|coupling| coupling.name.clone())
                                    .map_err(|e| e.to_string())
                            })
                            .transpose()
                        })
                        .collect::<Result<Vec<_>, _>>()
                })
                .collect::<Result<Vec<_>, _>>()?;
            for first in 0..particles.len() {
                for second in 0..particles.len() {
                    if first == second {
                        continue;
                    }
                    let loop_in = &particles[first];
                    let loop_out = &conjugates[&particles[second]];
                    if !species.contains_key(loop_in) || !species.contains_key(loop_out) {
                        continue;
                    }
                    let mut attached: Vec<_> = particles
                        .iter()
                        .enumerate()
                        .filter(|(index, _)| *index != first && *index != second)
                        .map(|(_, name)| name.clone())
                        .collect();
                    attached.sort();
                    let mut vertex_degree = None;
                    for structure in &structures {
                        let slots = (first + 1, second + 1);
                        let key = (structure.structure.clone(), slots);
                        let degree = if let Some(&degree) = degree_cache.get(&key) {
                            degree
                        } else {
                            let degree = momentum_degree(&structure.structure, Some(slots))
                                .map_err(|e| format!("vertex {}: {e}", rule.name))?;
                            degree_cache.insert(key, degree);
                            degree
                        };
                        vertex_degree =
                            Some(vertex_degree.map_or(degree, |old: i64| old.max(degree)));
                    }
                    let vertex_degree = vertex_degree
                        .ok_or_else(|| format!("vertex {} has no Lorentz structure", rule.name))?;
                    let numerator_degree = if let Some(&degree) = numerator_degrees.get(loop_out) {
                        degree
                    } else {
                        let particle = model.particle(loop_out).map_err(|e| e.to_string())?;
                        // Unlike the Python field-name dictionary, native model
                        // resolution honors explicit/default and conjugate
                        // propagators. Reversing numerator slots and q -> -q
                        // does not change its total polynomial degree.
                        let (propagator, _reversed) = model
                            .particle_propagator(particle)
                            .map_err(|e| e.to_string())?
                            .ok_or_else(|| {
                                format!("particle {loop_out:?} has no propagator numerator")
                            })?;
                        let numerator = &model
                            .propagator_by_id(propagator)
                            .map_err(|e| e.to_string())?
                            .numerator;
                        let degree = momentum_degree(numerator, None)
                            .map_err(|e| format!("propagator {loop_out}: {e}"))?;
                        numerator_degrees.insert(loop_out.clone(), degree);
                        degree
                    };
                    let q_degree = vertex_degree
                        .checked_add(numerator_degree)
                        .ok_or_else(|| format!("loop rank overflows for vertex {}", rule.name))?;
                    let identity = (
                        rule.name.clone(),
                        loop_in.clone(),
                        attached.clone(),
                        loop_out.clone(),
                        order.clone(),
                    );
                    if templates
                        .get(&identity)
                        .is_some_and(|old| old.q_degree >= q_degree)
                    {
                        continue;
                    }
                    let signature = VertexSignature {
                        lorentz_structures: structures.iter().map(|s| s.name.clone()).collect(),
                        color_structures: rule.color_structures.clone(),
                        couplings: couplings.clone(),
                        // This membership filter intentionally matches the Python
                        // signature even when an attached field also labels a loop leg.
                        attached_in_rule_order: particles
                            .iter()
                            .filter(|name| attached.contains(name))
                            .cloned()
                            .collect(),
                        first,
                        second,
                    };
                    templates.insert(
                        identity,
                        LoopVertex {
                            rule: rule.name.clone(),
                            loop_in: loop_in.clone(),
                            attached,
                            loop_out: loop_out.clone(),
                            orders: order.clone(),
                            q_degree,
                            signature,
                        },
                    );
                }
            }
        }
        // There is one template per identity, so identity order is exactly the
        // Python LoopVertex order (its final q_degree tie-breaker cannot differ).
        let vertices: Vec<_> = templates.into_values().collect();
        let mut by_identity = BTreeMap::new();
        let mut vertices_by_loop_in = BTreeMap::<String, Vec<u32>>::new();
        for (index, vertex) in vertices.iter().enumerate() {
            let id =
                u32::try_from(index).map_err(|_| "too many loop-vertex templates".to_string())?;
            by_identity.insert(vertex.identity(), id);
            vertices_by_loop_in
                .entry(vertex.loop_in.clone())
                .or_default()
                .push(id);
        }
        let reflected = vertices
            .iter()
            .map(|vertex| {
                let identity = (
                    vertex.rule.clone(),
                    conjugates[&vertex.loop_out].clone(),
                    vertex.attached.clone(),
                    conjugates[&vertex.loop_in].clone(),
                    vertex.orders.clone(),
                );
                by_identity.get(&identity).copied().ok_or_else(|| {
                    format!(
                        "loop vertex {:?} has no reflected template",
                        vertex.identity()
                    )
                })
            })
            .collect::<Result<Vec<_>, _>>()?;
        Ok(Self {
            species,
            conjugates,
            vertices,
            vertices_by_loop_in,
            reflected,
        })
    }

    pub fn species(&self, name: &str) -> Result<&LoopSpecies, String> {
        self.species
            .get(name)
            .ok_or_else(|| format!("unknown loop species {name:?}"))
    }

    pub fn conjugate(&self, name: &str) -> Result<&str, String> {
        self.conjugates
            .get(name)
            .map(String::as_str)
            .ok_or_else(|| format!("unknown field {name:?}"))
    }

    pub fn loop_species(&self) -> impl Iterator<Item = &str> {
        self.species.keys().map(String::as_str)
    }

    pub fn vertices(&self, loop_in: &str) -> impl Iterator<Item = &LoopVertex> {
        self.vertices_by_loop_in
            .get(loop_in)
            .into_iter()
            .flatten()
            .map(|&id| &self.vertices[id as usize])
    }
}

/// Exact degree in the loop momentum of a UFO expression.
///
/// Vertex slots are one based. Their momenta are shifted by `+t*q(mu)` and
/// `-t*q(mu)` before exact expansion, so `P_in + P_out` has degree zero.
/// For a propagator (`None`), every `P` and `PSlash` is scaled by `t`.
/// Unsupported vertex momentum forms and nonpolynomial dependence fail explicitly.
pub fn momentum_degree(expression: &Atom, slots: Option<(usize, usize)>) -> Result<i64, String> {
    if slots.is_some_and(|(first, second)| first == 0 || second == 0 || first == second) {
        return Err("loop slots must be distinct positive UFO leg numbers".into());
    }
    let t_symbol = symbol!("rusticol_loop_preparation::momentum_degree_t");
    let q_symbol = symbol!("rusticol_loop_preparation::momentum_degree_q");
    if expression.contains_symbol(t_symbol) || expression.contains_symbol(q_symbol) {
        return Err("model expression uses a reserved loop-rank marker".into());
    }
    let t = Atom::var(t_symbol);
    let mut error = None;
    let shifted = expression.replace_map(|term, _, out| {
        let AtomView::Fun(function) = term else {
            return;
        };
        let symbol = function.get_symbol();
        let name = symbol.get_name().rsplit("::").next().unwrap_or("");
        if name != "P" && name != "PSlash" {
            return;
        }
        let Some((first, second)) = slots else {
            **out = Atom::from(term) * &t;
            return;
        };
        let arguments: Vec<_> = function.iter().collect();
        let leg = if name == "P" && arguments.len() == 2 {
            if let AtomView::Fun(index) = arguments[1] {
                let symbol = index.get_symbol();
                let entries: Vec<_> = index.iter().collect();
                if symbol.get_name().rsplit("::").next() == Some("idx") && entries.len() == 2 {
                    Some(entries[1])
                } else {
                    None
                }
            } else {
                None
            }
        } else {
            None
        };
        let Some(leg) = leg else {
            error = Some(format!(
                "vertex momentum outside P(mu, leg) form in {expression}"
            ));
            return;
        };
        let sign = if leg == Atom::num(first) {
            1
        } else if leg == Atom::num(second) {
            -1
        } else {
            0
        };
        if sign != 0 {
            let q = q_symbol.call_args([arguments[0]]);
            **out = Atom::from(term) + Atom::num(sign) * &t * q;
        }
    });
    if let Some(error) = error {
        return Err(error);
    }
    let expanded = shifted.expand();
    let polynomial = expanded.to_polynomial_in_vars_with_field::<i32>(
        t_symbol,
        &AtomField {
            statistical_zero_test: false,
            ..AtomField::new()
        },
    );
    let mut degree = 0;
    for (index, coefficient) in polynomial.coefficients.iter().enumerate() {
        let coefficient = coefficient.expand();
        if coefficient == Atom::Zero {
            continue;
        }
        let exponent = polynomial.exponents(index)[0];
        if coefficient.contains_symbol(t_symbol) || exponent < 0 {
            return Err(format!(
                "nonpolynomial loop-momentum dependence in {expression}"
            ));
        }
        degree = degree.max(i64::from(exponent));
    }
    Ok(degree)
}

#[cfg(test)]
mod tests {
    use super::*;
    use symbolica::parse;

    #[test]
    fn opposite_loop_shifts_cancel_before_degree_is_counted() {
        let sum = parse!("UFO::P(UFO::idx(1,3),UFO::idx(1,1))+UFO::P(UFO::idx(1,3),UFO::idx(1,2))");
        let difference =
            parse!("UFO::P(UFO::idx(1,3),UFO::idx(1,1))-UFO::P(UFO::idx(1,3),UFO::idx(1,2))");
        assert_eq!(momentum_degree(&sum, Some((1, 2))).unwrap(), 0);
        assert_eq!(momentum_degree(&difference, Some((1, 2))).unwrap(), 1);
        assert_eq!(
            momentum_degree(&(&sum * &difference).expand(), Some((1, 2))).unwrap(),
            1
        );
        assert_eq!(
            momentum_degree(&parse!("UFO::P(UFO::idx(1,3),UFO::idx(1,4))"), Some((1, 2))).unwrap(),
            0
        );
    }

    #[test]
    fn propagator_scaling_and_unsupported_momentum_forms() {
        assert_eq!(
            momentum_degree(&parse!("UFO::PSlash(1,2,3)+mass"), None).unwrap(),
            1
        );
        assert_eq!(
            momentum_degree(&parse!("-UFO::PSlash(2,1,3)+mass"), None).unwrap(),
            momentum_degree(&parse!("UFO::PSlash(1,2,3)+mass"), None).unwrap(),
        );
        assert_eq!(
            momentum_degree(&parse!("UFO::P(1)*UFO::P(2)+1"), None).unwrap(),
            2
        );
        assert!(momentum_degree(&parse!("UFO::PSlash(1,2,3)"), Some((1, 2))).is_err());
        assert!(momentum_degree(&parse!("UFO::P(UFO::idx(1,3),2)"), Some((1, 2))).is_err());
        assert!(momentum_degree(&parse!("1/UFO::P(1)"), None).is_err());
    }

    #[test]
    fn scalar_catalogue_preserves_symbolic_mass_and_reflection() {
        for model in [Model::phi3(), Model::phi4()] {
            let catalogue = ModelLoopCatalogue::new(&model, None).unwrap();
            assert!(!catalogue.vertices.is_empty());
            for species in catalogue.species.values() {
                assert_eq!(species.mass.mass, "mass");
                assert!(!species.perturbative_orders.is_empty());
            }
            for (index, &reflected) in catalogue.reflected.iter().enumerate() {
                assert_eq!(catalogue.reflected[reflected as usize] as usize, index);
                assert_eq!(catalogue.vertices[index].q_degree, 0);
            }
            let explicit_empty =
                ModelLoopCatalogue::new(&model, Some(&SpeciesOrders::new())).unwrap();
            assert!(
                explicit_empty
                    .species
                    .values()
                    .all(|species| species.perturbative_orders.is_empty())
            );
        }
    }
}
