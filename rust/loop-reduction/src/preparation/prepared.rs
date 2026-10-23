// SPDX-License-Identifier: 0BSD

use std::collections::{BTreeMap, BTreeSet};

use feynkit_model::{Model, ParameterCard};
use rusticol_core::loop_v2::generate::{
    families::{
        self, CurrentInput, FamilyInput, FamilyOutput, LegInput, SpeciesInput, VertexInput,
    },
    orders::OrderVec,
};
use symbolica::atom::{Atom, Symbol};

use super::{
    BlockCurrent, MassId, ModelBlockTable, ModelLoopCatalogue, Orders, SpeciesOrders,
    VertexSignature, normalize_orders,
};

/// Named coupling-order selection, normalized before compact ids are assigned.
#[derive(Clone, Debug)]
pub struct LoopOrderSelection {
    corrections: BTreeSet<String>,
    requested_order_names: BTreeSet<String>,
    loop_orders: BTreeSet<Orders>,
    cap: Orders,
}

impl LoopOrderSelection {
    pub fn new(
        corrections: impl IntoIterator<Item = String>,
        loop_orders: impl IntoIterator<Item = Orders>,
    ) -> Result<Self, String> {
        let corrections: BTreeSet<_> = corrections.into_iter().collect();
        let mut requested_order_names = BTreeSet::new();
        let loop_orders = loop_orders
            .into_iter()
            .map(|order| {
                for (name, power) in &order {
                    if *power < 0 {
                        return Err("loop coupling-order powers must be nonnegative".into());
                    }
                    requested_order_names.insert(name.clone());
                }
                normalize_orders(order)
            })
            .collect::<Result<BTreeSet<_>, String>>()?;
        if corrections.is_empty() || loop_orders.is_empty() {
            return Err("a loop selection needs corrections and loop orders".into());
        }
        let mut cap = BTreeMap::<String, i64>::new();
        for (name, power) in loop_orders.iter().flatten() {
            let bound = cap.entry(name.clone()).or_default();
            *bound = (*bound).max(*power);
        }
        Ok(Self {
            corrections,
            requested_order_names,
            loop_orders,
            cap: cap.into_iter().collect(),
        })
    }

    pub fn corrections(&self) -> &BTreeSet<String> {
        &self.corrections
    }
    pub fn loop_orders(&self) -> &BTreeSet<Orders> {
        &self.loop_orders
    }
    pub fn cap(&self) -> &Orders {
        &self.cap
    }
}

/// An owned, normalized model and its exact scalar specialization.
///
/// FeynKit resolves analytic definitions, restriction-card values, and exact
/// overrides. No f64 conversion is introduced by the native family producer.
/// Symbolic mass identities remain the model's identities even when an override
/// numerically sets a mass to zero; restrictions that change those identities
/// must be applied to the model before constructing this owner.
/// Conversely, effective scalar bindings may not change any already proved
/// structural zero, since normalization may have eliminated its occurrences.
pub struct PreparedModel {
    model: Model,
    scalars: BTreeMap<Symbol, Atom>,
}

impl PreparedModel {
    pub fn new(
        model: Model,
        card: Option<&ParameterCard>,
        overrides: &BTreeMap<Symbol, Atom>,
    ) -> Result<Self, String> {
        let scalars = model
            .scalar_bindings(card, overrides)
            .map_err(|e| e.to_string())?;
        Ok(Self { model, scalars })
    }

    pub fn model(&self) -> &Model {
        &self.model
    }
    pub fn scalar_bindings(&self) -> &BTreeMap<Symbol, Atom> {
        &self.scalars
    }

    /// Produce complete input for the Rust family recursion from a fresh model
    /// and process. Retain original species facts when using a pruned model.
    pub fn families(
        &self,
        incoming: &[&str],
        outgoing: &[&str],
        selection: &LoopOrderSelection,
        species_orders: Option<&SpeciesOrders>,
    ) -> Result<PreparedFamilies, String> {
        PreparedFamilies::from_model(
            &self.model,
            incoming,
            outgoing,
            selection,
            species_orders,
            Some(&self.scalars),
        )
    }
}

/// Canonical id tables together with their native family-recursion input.
/// These are structural data; numerical tree and loop kernels remain separate.
#[derive(Debug)]
pub struct PreparedFamilies {
    pub fields: Vec<String>,
    pub masses: Vec<MassId>,
    pub order_names: Vec<String>,
    pub catalogue: ModelLoopCatalogue,
    /// Includes every member of a merged class, including its representative.
    pub closed_loop_representatives: BTreeMap<String, String>,
    pub input: FamilyInput,
}

impl PreparedFamilies {
    pub fn new(
        model: &Model,
        incoming: &[&str],
        outgoing: &[&str],
        selection: &LoopOrderSelection,
        species_orders: Option<&SpeciesOrders>,
    ) -> Result<Self, String> {
        Self::from_model(model, incoming, outgoing, selection, species_orders, None)
    }

    fn from_model(
        model: &Model,
        incoming: &[&str],
        outgoing: &[&str],
        selection: &LoopOrderSelection,
        species_orders: Option<&SpeciesOrders>,
        bindings: Option<&BTreeMap<Symbol, Atom>>,
    ) -> Result<Self, String> {
        let known: BTreeSet<_> = model.orders().iter().map(|order| &order.name).collect();
        for name in selection
            .corrections
            .iter()
            .chain(selection.requested_order_names.iter())
        {
            if !known.contains(name) {
                return Err(format!("unknown coupling-order name {name:?}"));
            }
        }
        let mut blocks = ModelBlockTable::new(model, incoming, outgoing, selection.cap.clone())?;
        let currents = blocks.all_currents()?;
        let catalogue = ModelLoopCatalogue::with_bindings(model, species_orders, bindings)?;
        let eligible: BTreeSet<_> = catalogue
            .species
            .iter()
            .filter(|(_, species)| {
                !species
                    .perturbative_orders
                    .is_disjoint(&selection.corrections)
            })
            .map(|(name, _)| name.clone())
            .collect();
        let merged = closed_loop_classes(&eligible, &catalogue, &currents);

        let fields: Vec<_> = catalogue.conjugates.keys().cloned().collect();
        let field_ids: BTreeMap<_, _> = fields
            .iter()
            .enumerate()
            .map(|(index, name)| {
                Ok((
                    name.clone(),
                    u32::try_from(index).map_err(|_| "more than u32::MAX fields")?,
                ))
            })
            .collect::<Result<_, String>>()?;
        let masses: Vec<_> = blocks
            .legs()
            .iter()
            .map(|leg| leg.mass.clone())
            .chain(
                catalogue
                    .species
                    .values()
                    .map(|species| species.mass.clone()),
            )
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect();
        let mass_ids: BTreeMap<_, _> = masses
            .iter()
            .enumerate()
            .map(|(index, mass)| {
                Ok((
                    mass.clone(),
                    u32::try_from(index).map_err(|_| "more than u32::MAX masses")?,
                ))
            })
            .collect::<Result<_, String>>()?;
        let mut order_names: BTreeSet<String> = selection.corrections.clone();
        order_names.extend(
            selection
                .loop_orders
                .iter()
                .flatten()
                .map(|(name, _)| name.clone()),
        );
        order_names.extend(
            catalogue
                .vertices
                .iter()
                .flat_map(|vertex| vertex.orders.iter().map(|(name, _)| name.clone())),
        );
        order_names.extend(
            catalogue
                .species
                .values()
                .flat_map(|species| species.perturbative_orders.iter().cloned()),
        );
        order_names.extend(
            currents
                .iter()
                .flat_map(|current| current.orders.iter().map(|(name, _)| name.clone())),
        );
        if order_names.len() > 64 {
            return Err(
                "the native order generator supports at most 64 coupling-order names".into(),
            );
        }
        let order_names: Vec<_> = order_names.into_iter().collect();
        let order_ids: BTreeMap<_, _> = order_names
            .iter()
            .enumerate()
            .map(|(index, name)| (name.clone(), index as u16))
            .collect();
        let orders = |named: &Orders| -> OrderVec {
            named
                .iter()
                .map(|(name, power)| (order_ids[name], *power))
                .collect()
        };
        let species = fields
            .iter()
            .map(|name| {
                catalogue
                    .species
                    .get(name)
                    .map(|species| {
                        let colour = i32::try_from(species.colour)
                            .map_err(|_| "species colour exceeds i32")?;
                        if colour == i32::MIN {
                            return Err("species colour has no representable absolute value".into());
                        }
                        Ok(SpeciesInput {
                            antiname: field_ids[&species.antiname],
                            colour,
                            mass: mass_ids[&species.mass],
                            perturbative: species
                                .perturbative_orders
                                .iter()
                                .map(|name| order_ids[name])
                                .collect(),
                        })
                    })
                    .transpose()
            })
            .collect::<Result<Vec<_>, String>>()?;
        let mut multiplicity = vec![1u32; fields.len()];
        let mut sizes = BTreeMap::<String, u32>::new();
        for name in merged.values() {
            let size = sizes.entry(name.clone()).or_default();
            *size = size
                .checked_add(1)
                .ok_or("closed-loop multiplicity exceeds u32")?;
        }
        for (name, size) in sizes {
            multiplicity[field_ids[&name] as usize] = size;
        }
        let input = FamilyInput {
            legs: blocks
                .legs()
                .iter()
                .map(|leg| LegInput {
                    field: field_ids[&leg.field],
                    mass: mass_ids[&leg.mass],
                })
                .collect(),
            species,
            massless: masses.iter().map(MassId::massless).collect(),
            vertices: catalogue
                .vertices
                .iter()
                .enumerate()
                .map(|(index, vertex)| VertexInput {
                    loop_in: field_ids[&vertex.loop_in],
                    attached: vertex.attached.iter().map(|name| field_ids[name]).collect(),
                    loop_out: field_ids[&vertex.loop_out],
                    orders: orders(&vertex.orders),
                    q_degree: vertex.q_degree,
                    reflected: catalogue.reflected[index],
                })
                .collect(),
            vertices_by_loop_in: fields
                .iter()
                .map(|name| {
                    catalogue
                        .vertices_by_loop_in
                        .get(name)
                        .cloned()
                        .unwrap_or_default()
                })
                .collect(),
            currents: currents
                .iter()
                .map(|current| CurrentInput {
                    mask: current.mask,
                    field: field_ids[&current.field],
                    orders: orders(&current.orders),
                })
                .collect(),
            eligible: eligible
                .iter()
                .filter(|name| {
                    merged
                        .get(*name)
                        .is_none_or(|representative| representative == *name)
                })
                .map(|name| field_ids[name])
                .collect(),
            multiplicity,
            corrections: selection
                .corrections
                .iter()
                .map(|name| order_ids[name])
                .collect(),
            loop_orders: selection.loop_orders.iter().map(orders).collect(),
            cap: orders(&selection.cap),
        };
        Ok(Self {
            fields,
            masses,
            order_names,
            catalogue,
            closed_loop_representatives: merged,
            input,
        })
    }

    pub fn generate(&self) -> Result<FamilyOutput, String> {
        families::generate_families(&self.input)
    }
}

/// Process-dependent structural equivalence of closed-loop species. Both the
/// interaction signature and every reachable attachment must agree; an external
/// flavour line or a species-changing interaction prevents the merge.
fn closed_loop_classes(
    eligible: &BTreeSet<String>,
    catalogue: &ModelLoopCatalogue,
    currents: &[BlockCurrent],
) -> BTreeMap<String, String> {
    let fields: BTreeSet<_> = currents.iter().map(|current| &current.field).collect();
    let usable =
        |vertex: &super::LoopVertex| vertex.attached.iter().all(|name| fields.contains(name));
    let vertices = |name: &str| {
        catalogue
            .vertices_by_loop_in
            .get(name)
            .into_iter()
            .flatten()
            .map(|&id| &catalogue.vertices[id as usize])
    };
    let mut entering = BTreeMap::<String, BTreeSet<String>>::new();
    for name in eligible {
        for vertex in vertices(name).filter(|vertex| usable(vertex)) {
            entering
                .entry(vertex.loop_out.clone())
                .or_default()
                .insert(name.clone());
        }
    }
    type Signature = Vec<(VertexSignature, Vec<String>, bool, Orders, i64)>;
    let signature = |name: &str| -> Option<Signature> {
        let species = catalogue.species.get(name)?;
        let own = BTreeSet::from([name, species.antiname.as_str()]);
        if entering
            .get(name)
            .is_some_and(|sources| sources.iter().any(|source| !own.contains(source.as_str())))
        {
            return None;
        }
        let mut found = Signature::new();
        for vertex in vertices(name).filter(|vertex| usable(vertex)) {
            if !own.contains(vertex.loop_out.as_str())
                || vertex
                    .attached
                    .iter()
                    .any(|field| own.contains(field.as_str()))
            {
                return None;
            }
            found.push((
                vertex.signature.clone(),
                vertex.attached.clone(),
                vertex.loop_out == name,
                vertex.orders.clone(),
                vertex.q_degree,
            ));
        }
        if found.is_empty() {
            return None;
        }
        // Distinct rules with identical tensors still represent distinct
        // interactions. Preserve their multiplicities when comparing species.
        found.sort();
        Some(found)
    };
    type Key = (
        MassId,
        i64,
        i64,
        bool,
        super::propagators::PropagatorSignature,
        super::propagators::PropagatorSignature,
        Signature,
        Signature,
    );
    let mut groups = BTreeMap::<Key, Vec<String>>::new();
    // Preserve insertion order of groups from sorted species, just as Python's
    // dict does; conjugate groups must choose mutually conjugate representatives.
    let mut group_order = Vec::new();
    for name in eligible {
        let species = &catalogue.species[name];
        // Treat a particle/antiparticle pair as one candidate. Otherwise equal
        // orientations can put both members in one class and overwrite their
        // representatives with a cycle, dropping both from eligible fields.
        if name > &species.antiname {
            continue;
        }
        let Some(found) = signature(name) else {
            continue;
        };
        let Some(conjugate) = catalogue.species.get(&species.antiname) else {
            continue;
        };
        // Pair-changing vertices such as a*a*h do not determine the separate
        // a~*a~*h interaction. Both orientations must agree before assigning
        // representatives to a species and its antiparticle together.
        let Some(conjugate_signature) = signature(&species.antiname) else {
            continue;
        };
        let key = (
            species.mass.clone(),
            species.spin,
            species.colour,
            species.name == species.antiname,
            species.propagator.clone(),
            conjugate.propagator.clone(),
            found,
            conjugate_signature,
        );
        if !groups.contains_key(&key) {
            group_order.push(key.clone());
        }
        groups.entry(key).or_default().push(name.clone());
    }
    let mut output = BTreeMap::new();
    for key in group_order {
        let members = &groups[&key];
        if members.len() < 2 || output.contains_key(&members[0]) {
            continue;
        }
        let representative = &members[0];
        let conjugate = &catalogue.species[representative].antiname;
        for name in members {
            output.insert(name.clone(), representative.clone());
            output.insert(catalogue.species[name].antiname.clone(), conjugate.clone());
        }
    }
    output
}

#[cfg(test)]
mod tests {
    use super::super::structural_zeros;
    use super::*;
    use symbolica::{parse, symbol};

    fn qcd(power: i64) -> LoopOrderSelection {
        LoopOrderSelection::new(["QCD".into()], [vec![("QCD".into(), power)]]).unwrap()
    }

    fn vacuum_qcd_definition() -> serde_json::Value {
        let mut definition: serde_json::Value =
            serde_json::from_str(&Model::qcd().to_json().unwrap()).unwrap();
        let mut zeros = BTreeSet::new();
        for particle in definition["particles"].as_array().unwrap() {
            if particle["pdg_code"].as_i64().unwrap().unsigned_abs() <= 4 {
                zeros.insert(particle["mass"].as_str().unwrap().to_owned());
            }
            zeros.insert(particle["width"].as_str().unwrap().to_owned());
            if let Some(name) = particle["chemical_potential"].as_str() {
                zeros.insert(name.to_owned());
            }
        }
        for parameter in definition["parameters"].as_array_mut().unwrap() {
            if zeros.contains(parameter["name"].as_str().unwrap()) {
                parameter["nature"] = "internal".into();
                parameter["expression"] = "0".into();
                parameter["value"] = serde_json::json!([0.0, 0.0]);
            }
        }
        definition
    }

    #[test]
    fn exact_model_specialization_keeps_small_rational_override() {
        let model = Model::phi4();
        let value = parse!("1+1/1208925819614629174706176");
        let prepared = PreparedModel::new(
            model,
            None,
            &BTreeMap::from([(symbol!("UFO::mass"), value.clone())]),
        )
        .unwrap();
        assert_eq!(prepared.scalar_bindings()[&symbol!("UFO::mass")], value);
        assert_ne!(
            prepared.scalar_bindings()[&symbol!("UFO::mass")],
            Atom::one()
        );
    }

    #[test]
    fn order_selection_normalizes_terms_and_retains_distinct_targets() {
        let selected = LoopOrderSelection::new(
            ["QCD".into()],
            [
                vec![("QCD".into(), 2), ("QCD".into(), 2)],
                vec![("QED".into(), 2), ("QCD".into(), 2)],
            ],
        )
        .unwrap();
        assert_eq!(selected.cap(), &vec![("QCD".into(), 4), ("QED".into(), 2)]);
        assert_eq!(selected.loop_orders().len(), 2);
        assert!(LoopOrderSelection::new([], [vec![]]).is_err());
        assert!(LoopOrderSelection::new(["QCD".into()], [vec![("QCD".into(), -1)]]).is_err());
        assert!(
            LoopOrderSelection::new(
                ["QCD".into()],
                [vec![("QCD".into(), -1), ("QCD".into(), 2)]]
            )
            .is_err()
        );
        let model = Model::phi4();
        let typo =
            LoopOrderSelection::new(["UNKNOWN".into()], [vec![("UNKNOWN".into(), 2)]]).unwrap();
        assert!(
            PreparedFamilies::new(&model, &["phi", "phi"], &["phi", "phi"], &typo, None)
                .unwrap_err()
                .contains("unknown coupling-order")
        );
        let typo_zero = LoopOrderSelection::new(
            ["SCALAR".into()],
            [vec![("SCALAR".into(), 2), ("UNKNOWN".into(), 0)]],
        )
        .unwrap();
        assert!(
            PreparedFamilies::new(&model, &["phi"; 2], &["phi"; 2], &typo_zero, None)
                .unwrap_err()
                .contains("unknown coupling-order")
        );
        assert!(
            ModelBlockTable::new(&model, &["phi"; 3], &[], vec![("UNKNOWN".into(), 0)]).is_err()
        );
    }

    #[test]
    fn names_are_not_zero_proofs_and_structural_zero_overrides_are_rejected() {
        for (nature, expression) in [("internal", "1"), ("external", "0")] {
            let mut definition: serde_json::Value =
                serde_json::from_str(&Model::phi3().to_json().unwrap()).unwrap();
            let zero = definition["parameters"]
                .as_array_mut()
                .unwrap()
                .iter_mut()
                .find(|parameter| parameter["name"] == "ZERO")
                .unwrap();
            zero["nature"] = nature.into();
            zero["expression"] = expression.into();
            let model = Model::from_json(&definition.to_string()).unwrap();
            assert!(PreparedModel::new(model.clone(), None, &BTreeMap::new()).is_ok());
            let blocks = ModelBlockTable::new(&model, &["phi"; 3], &[], vec![]).unwrap();
            assert_eq!(blocks.legs()[0].mass.width, "ZERO");
            assert!(!structural_zeros(&model).unwrap().contains("ZERO"));
            // A bare real denominator does not represent this unbound width.
            assert!(ModelLoopCatalogue::new(&model, None).is_err());
        }
        let model = Model::phi3();
        assert!(
            PreparedModel::new(
                model.clone(),
                None,
                &BTreeMap::from([(symbol!("UFO::ZERO"), Atom::one())])
            )
            .is_err()
        );
        let card = ParameterCard::from_json(r#"{"ZERO":[1.0,0.0]}"#).unwrap();
        assert!(PreparedModel::new(model, Some(&card), &BTreeMap::new()).is_err());
    }

    #[test]
    fn general_exact_zero_names_are_supported_and_cannot_be_redefined() {
        let json = Model::phi3()
            .to_json()
            .unwrap()
            .replace("ZERO", "null_parameter");
        let mut definition: serde_json::Value = serde_json::from_str(&json).unwrap();
        let mass = definition["parameters"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .find(|parameter| parameter["name"] == "mass")
            .unwrap();
        mass["nature"] = "internal".into();
        mass["expression"] = "2*null_parameter".into();
        let model = Model::from_json(&definition.to_string()).unwrap();
        let catalogue = ModelLoopCatalogue::new(&model, None).unwrap();
        assert!(catalogue.species["phi"].mass.massless());
        assert!(PreparedModel::new(model.clone(), None, &BTreeMap::new()).is_ok());
        assert!(
            PreparedModel::new(
                model,
                None,
                &BTreeMap::from([(symbol!("UFO::null_parameter"), Atom::one())])
            )
            .is_err()
        );
    }

    #[test]
    fn zero_proofs_treat_trailing_underscores_as_literal_symbols() {
        let mut definition: serde_json::Value =
            serde_json::from_str(&Model::phi3().to_json().unwrap()).unwrap();
        definition["parameters"]
            .as_array_mut()
            .unwrap()
            .push(serde_json::json!({
                "name": "null_", "nature": "internal", "parameter_type": "real", "expression": "0"
            }));
        definition["parameters"].as_array_mut().unwrap().push(serde_json::json!({
            "name": "mass_copy", "nature": "internal", "parameter_type": "real", "expression": "mass"
        }));
        let model = Model::from_json(&definition.to_string()).unwrap();
        let zeros = structural_zeros(&model).unwrap();
        assert!(zeros.contains("null_"));
        assert!(!zeros.contains("mass_copy"));
        assert!(PreparedModel::new(model, None, &BTreeMap::new()).is_ok());
    }

    #[test]
    fn immutable_exact_binding_can_certify_vacuum_without_using_unbound_defaults() {
        let mut definition: serde_json::Value =
            serde_json::from_str(&Model::phi4().to_json().unwrap()).unwrap();
        definition["parameters"]
            .as_array_mut()
            .unwrap()
            .push(serde_json::json!({
                "name": "medium", "nature": "external", "parameter_type": "real", "value": [0.0,0.0]
            }));
        definition["particles"][0]["chemical_potential"] = "medium".into();
        let model = Model::from_json(&definition.to_string()).unwrap();
        let order = model.couplings()[0].orders.keys().next().unwrap().clone();
        let selection = LoopOrderSelection::new([order.clone()], [vec![(order, 2)]]).unwrap();
        assert!(PreparedFamilies::new(&model, &["phi"; 2], &["phi"; 2], &selection, None).is_err());
        let vacuum = PreparedModel::new(model.clone(), None, &BTreeMap::new()).unwrap();
        assert_eq!(
            vacuum
                .families(&["phi"; 2], &["phi"; 2], &selection, None)
                .unwrap()
                .generate()
                .unwrap()
                .families
                .len(),
            3
        );
        let medium = PreparedModel::new(
            model,
            None,
            &BTreeMap::from([(symbol!("UFO::medium"), Atom::one())]),
        )
        .unwrap();
        assert!(
            medium
                .families(&["phi"; 2], &["phi"; 2], &selection, None)
                .is_err()
        );
    }

    #[test]
    fn imported_scalar_model_has_three_two_propagator_channels() {
        let model = Model::from_json(&Model::phi4().to_json().unwrap()).unwrap();
        let order = model.couplings()[0].orders.keys().next().unwrap().clone();
        let selection = LoopOrderSelection::new([order.clone()], [vec![(order, 2)]]).unwrap();
        let prepared = PreparedModel::new(model, None, &BTreeMap::new()).unwrap();
        let families = prepared
            .families(&["phi", "phi"], &["phi", "phi"], &selection, None)
            .unwrap();
        let output = families.generate().unwrap();
        // Two quartic vertices partition four labeled legs into the three
        // independent pairings (s, t, u), without a hard-coded process table.
        assert_eq!(output.families.len(), 3);
        assert!(
            output
                .families
                .iter()
                .all(|family| family.key.len() == 2 && family.rank == 0)
        );
        assert!(output.scaleless.is_empty());
    }

    #[test]
    fn fresh_model_generates_families_and_process_dependent_flavour_classes() {
        // Make the symbolic light-flavour restriction explicit. Numerically
        // small/default-zero values must never cause structural mass merging.
        let definition = vacuum_qcd_definition();
        let model = Model::from_json(&definition.to_string()).unwrap();
        let gluons =
            PreparedFamilies::new(&model, &["g", "g"], &["g", "g"], &qcd(4), None).unwrap();
        let output = gluons.generate().unwrap();
        assert!(!output.families.is_empty());
        assert!(gluons.fields.windows(2).all(|pair| pair[0] < pair[1]));
        assert!(gluons.masses.windows(2).all(|pair| pair[0] < pair[1]));
        // The SM fixture's light flavours share scalar, spin and colour facts.
        assert_eq!(
            gluons.closed_loop_representatives.get("d"),
            gluons.closed_loop_representatives.get("s")
        );
        assert!(gluons.closed_loop_representatives.contains_key("d"));
        let quarks =
            PreparedFamilies::new(&model, &["d", "d~"], &["g", "g"], &qcd(4), None).unwrap();
        assert!(!quarks.closed_loop_representatives.contains_key("d"));
        assert!(!quarks.generate().unwrap().families.is_empty());
    }

    #[test]
    fn same_rank_unequal_propagator_numerators_do_not_merge_flavours() {
        let mut definition = vacuum_qcd_definition();
        for propagator in definition["propagators"].as_array_mut().unwrap() {
            if matches!(propagator["particle"].as_str(), Some("d" | "d~")) {
                propagator["numerator"] =
                    format!("2*({})", propagator["numerator"].as_str().unwrap()).into();
            }
        }
        let model = Model::from_json(&definition.to_string()).unwrap();
        let prepared =
            PreparedFamilies::new(&model, &["g", "g"], &["g", "g"], &qcd(4), None).unwrap();
        assert!(!prepared.closed_loop_representatives.contains_key("d"));
        assert!(!prepared.closed_loop_representatives.contains_key("d~"));
        assert!(prepared.closed_loop_representatives.contains_key("s"));
    }

    #[test]
    fn distinct_identical_vertex_rules_retain_their_interaction_multiplicity() {
        let mut definition = vacuum_qcd_definition();
        let rules = definition["vertex_rules"].as_array_mut().unwrap();
        let mut duplicate = rules
            .iter()
            .find(|rule| {
                let fields = rule["particles"].as_array().unwrap();
                fields.len() == 3
                    && ["d", "d~", "g"]
                        .iter()
                        .all(|field| fields.iter().any(|entry| entry == field))
            })
            .unwrap()
            .clone();
        duplicate["name"] = format!("{}_duplicate", duplicate["name"].as_str().unwrap()).into();
        rules.push(duplicate);
        let model = Model::from_json(&definition.to_string()).unwrap();
        let prepared =
            PreparedFamilies::new(&model, &["g", "g"], &["g", "g"], &qcd(4), None).unwrap();
        assert!(!prepared.closed_loop_representatives.contains_key("d"));
        assert!(!prepared.closed_loop_representatives.contains_key("d~"));
        assert!(prepared.closed_loop_representatives.contains_key("s"));
    }

    #[test]
    fn flavour_classes_preserve_real_and_complex_conjugation_types() {
        let mut definition: serde_json::Value =
            serde_json::from_str(&Model::phi3().to_json().unwrap()).unwrap();
        let prototype_particle = definition["particles"][0].clone();
        let prototype_propagator = definition["propagators"][0].clone();
        let prototype_rule = definition["vertex_rules"][0].clone();
        for (name, anti, pdg) in [
            ("a", "a~", 9000002),
            ("a~", "a", -9000002),
            ("r", "r", 9000003),
        ] {
            let mut particle = prototype_particle.clone();
            particle["name"] = name.into();
            particle["antiname"] = anti.into();
            particle["pdg_code"] = pdg.into();
            particle["propagator"] = format!("{name}_prop").into();
            definition["particles"]
                .as_array_mut()
                .unwrap()
                .push(particle);
            let mut propagator = prototype_propagator.clone();
            propagator["name"] = format!("{name}_prop").into();
            propagator["particle"] = name.into();
            definition["propagators"]
                .as_array_mut()
                .unwrap()
                .push(propagator);
        }
        for (name, fields) in [
            ("V_COMPLEX", ["a", "a~", "phi"]),
            ("V_REAL", ["r", "r", "phi"]),
        ] {
            let mut rule = prototype_rule.clone();
            rule["name"] = name.into();
            rule["particles"] = serde_json::json!(fields);
            definition["vertex_rules"]
                .as_array_mut()
                .unwrap()
                .push(rule);
        }
        let model = Model::from_json(&definition.to_string()).unwrap();
        let selection =
            LoopOrderSelection::new(["SCALAR".into()], [vec![("SCALAR".into(), 4)]]).unwrap();
        let prepared =
            PreparedFamilies::new(&model, &["phi"; 2], &["phi"; 2], &selection, None).unwrap();
        assert!(!prepared.closed_loop_representatives.contains_key("r"));
        for (name, representative) in &prepared.closed_loop_representatives {
            let conjugate = &prepared.catalogue.species[name].antiname;
            let conjugate_representative = prepared
                .closed_loop_representatives
                .get(conjugate)
                .unwrap_or(conjugate);
            assert_eq!(
                conjugate_representative,
                &prepared.catalogue.species[representative].antiname
            );
        }
    }

    #[test]
    fn pair_changing_vertices_compare_both_conjugate_interactions() {
        let mut definition: serde_json::Value =
            serde_json::from_str(&Model::phi3().to_json().unwrap()).unwrap();
        let prototype_particle = definition["particles"][0].clone();
        let prototype_propagator = definition["propagators"][0].clone();
        let prototype_rule = definition["vertex_rules"][0].clone();
        let mut unequal_coupling = definition["couplings"][0].clone();
        unequal_coupling["name"] = "UNEQUAL_PAIR".into();
        unequal_coupling["expression"] =
            format!("2*({})", unequal_coupling["expression"].as_str().unwrap()).into();
        definition["couplings"]
            .as_array_mut()
            .unwrap()
            .push(unequal_coupling);
        for (name, anti, pdg) in [
            ("a", "a~", 9000002),
            ("a~", "a", -9000002),
            ("b", "b~", 9000003),
            ("b~", "b", -9000003),
        ] {
            let mut particle = prototype_particle.clone();
            particle["name"] = name.into();
            particle["antiname"] = anti.into();
            particle["pdg_code"] = pdg.into();
            particle["propagator"] = format!("{name}_prop").into();
            definition["particles"]
                .as_array_mut()
                .unwrap()
                .push(particle);
            let mut propagator = prototype_propagator.clone();
            propagator["name"] = format!("{name}_prop").into();
            propagator["particle"] = name.into();
            definition["propagators"]
                .as_array_mut()
                .unwrap()
                .push(propagator);
            let mut rule = prototype_rule.clone();
            rule["name"] = format!("PAIR_{pdg}").into();
            rule["particles"] = serde_json::json!([name, name, "phi"]);
            if name == "b~" {
                rule["couplings"][0][0] = "UNEQUAL_PAIR".into();
            }
            definition["vertex_rules"]
                .as_array_mut()
                .unwrap()
                .push(rule);
        }
        let model = Model::from_json(&definition.to_string()).unwrap();
        let selection =
            LoopOrderSelection::new(["SCALAR".into()], [vec![("SCALAR".into(), 4)]]).unwrap();
        let prepared =
            PreparedFamilies::new(&model, &["phi"; 2], &["phi"; 2], &selection, None).unwrap();
        for name in ["a", "a~", "b", "b~"] {
            assert!(!prepared.closed_loop_representatives.contains_key(name));
        }
        // Equal conjugate interactions do permit the two complete pairs to
        // merge, while each representative must remain a fixed point.
        let unequal_rule = definition["vertex_rules"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .find(|rule| rule["name"] == "PAIR_-9000003")
            .unwrap();
        unequal_rule["couplings"] = prototype_rule["couplings"].clone();
        let equal_model = Model::from_json(&definition.to_string()).unwrap();
        let equal = PreparedFamilies::new(&equal_model, &["phi"; 2], &["phi"; 2], &selection, None)
            .unwrap();
        assert_eq!(equal.closed_loop_representatives["a"], "a");
        assert_eq!(equal.closed_loop_representatives["b"], "a");
        assert_eq!(equal.closed_loop_representatives["a~"], "a~");
        assert_eq!(equal.closed_loop_representatives["b~"], "a~");
    }
}
