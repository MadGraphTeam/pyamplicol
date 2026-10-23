// SPDX-License-Identifier: 0BSD

//! Admission of the simple vacuum poles represented by native family keys.
//!
//! FeynKit's typed propagator lookup chooses the template, but its model type
//! permits arbitrary UFO denominators. A family key `(mass,width)` cannot stand
//! in for such a denominator until the equality below has been established.

use std::collections::BTreeSet;

use feynkit_model::{Model, ParameterId, Particle};
use symbolica::{
    atom::{Atom, AtomCore, AtomView, Symbol},
    symbol,
};

/// Exact oriented template facts for safe closed-loop class comparisons.
///
/// `numerator` is in the resolved template's slot orientation. The `reversed`
/// bit is retained rather than inferring a tensor transpose or erasing a sign.
/// Equal polynomial ranks alone never establish equality of these signatures.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub(crate) struct PropagatorSignature {
    pub numerator: Atom,
    pub denominator: Atom,
    pub reversed: bool,
    pub template_mass: Atom,
    pub template_width: Atom,
}

/// Accept a monic simple vacuum pole `q²-m²+i*m*width` in the native UFO
/// one-line momentum convention. A real pole is admitted when width is proved
/// zero. A nonzero declared width is never silently added to a real denominator.
///
/// Supported momentum spellings are `UFO::P(UFO::idx(1,1))` and the scalar
/// `UFO::P`. No numerical defaults are read. `zeros` must contain only the
/// independently proved zero parameters, from structural declarations or the
/// immutable exact scalar specialization owned by `PreparedModel`.
/// Chemical potentials require such a proof for both the requested particle
/// and the resolved propagator's owner. Other poles need an extended family
/// representation and matching reduction backend before they can be admitted.
pub(crate) fn validated_propagator(
    model: &Model,
    particle: &Particle,
    zeros: &BTreeSet<String>,
) -> Result<PropagatorSignature, String> {
    require_vacuum(model, particle, zeros)?;
    let (id, reversed) = model
        .particle_propagator(particle)
        .map_err(|error| error.to_string())?
        .ok_or_else(|| format!("particle {:?} has no propagator template", particle.name))?;
    let propagator = model
        .propagator_by_id(id)
        .map_err(|error| error.to_string())?;
    let owner = model
        .particle_by_id(propagator.particle)
        .map_err(|error| error.to_string())?;
    require_vacuum(model, owner, zeros)?;
    let zero_symbols = zeros
        .iter()
        .map(|name| symbol!(&format!("UFO::{name}")))
        .collect::<BTreeSet<_>>();
    let numerator = substitute_zeros(&propagator.numerator, &zero_symbols);
    let denominator = substitute_zeros(&propagator.denominator, &zero_symbols);
    let mass = parameter_atom(model, particle.mass, zeros)?;
    let width = parameter_atom(model, particle.width, zeros)?;
    if mass.is_zero() && !width.is_zero() {
        return Err(format!(
            "particle {:?} has a nonzero structural width but zero mass; this width convention is unsupported",
            particle.name
        ));
    }
    let pole_offset = -mass.clone().pow(2) + Atom::i() * &mass * &width;
    let p = symbol!("UFO::P");
    let idx = symbol!("UFO::idx");
    let momenta = [Atom::var(p), p.call_args([idx.call_args([1i64, 1i64])])];
    if !momenta.iter().any(|momentum| {
        (&denominator - (momentum.clone().pow(2) + &pole_offset))
            .expand()
            .is_zero()
    }) {
        return Err(format!(
            "propagator {:?} for particle {:?} is not the supported monic simple vacuum denominator q^2-m^2+i*m*width; custom poles, powers, normalization factors and unrepresented widths require an extended family contract",
            propagator.name, particle.name
        ));
    }
    Ok(PropagatorSignature {
        numerator,
        denominator,
        reversed,
        template_mass: parameter_atom(model, owner.mass, zeros)?,
        template_width: parameter_atom(model, owner.width, zeros)?,
    })
}

fn require_vacuum(
    model: &Model,
    particle: &Particle,
    zeros: &BTreeSet<String>,
) -> Result<(), String> {
    if let Some(id) = particle.chemical_potential {
        let parameter = model
            .parameter_by_id(id)
            .map_err(|error| error.to_string())?;
        if !zeros.contains(&parameter.name) {
            return Err(format!(
                "particle {:?} has chemical potential {:?}, which is not proved structurally zero; medium-dependent poles are unsupported",
                particle.name, parameter.name
            ));
        }
    }
    Ok(())
}

fn parameter_atom(
    model: &Model,
    id: ParameterId,
    zeros: &BTreeSet<String>,
) -> Result<Atom, String> {
    let name = &model
        .parameter_by_id(id)
        .map_err(|error| error.to_string())?
        .name;
    Ok(if zeros.contains(name) {
        Atom::Zero
    } else {
        Atom::var(symbol!(&format!("UFO::{name}")))
    })
}

fn substitute_zeros(expression: &Atom, zeros: &BTreeSet<Symbol>) -> Atom {
    expression.replace_map(|term, _, output| {
        if let AtomView::Var(variable) = term {
            if zeros.contains(&variable.get_symbol()) {
                **output = Atom::Zero;
            }
        }
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{Value, json};

    fn scalar_definition() -> Value {
        serde_json::from_str(&Model::phi3().to_json().unwrap()).unwrap()
    }

    fn checked(definition: Value) -> Result<PropagatorSignature, String> {
        let model = Model::from_json(&definition.to_string()).unwrap();
        validated_propagator(
            &model,
            model.particle("phi").unwrap(),
            &BTreeSet::from(["ZERO".into()]),
        )
    }

    #[test]
    fn admits_exact_simple_poles_and_preserves_custom_parameter_names() {
        assert!(checked(scalar_definition()).is_ok());
        let mut definition = scalar_definition();
        let mass = definition["parameters"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .find(|parameter| parameter["name"] == "mass")
            .unwrap();
        mass["name"] = json!("arbitrary_mass_label");
        definition["particles"][0]["mass"] = json!("arbitrary_mass_label");
        definition["propagators"][0]["denominator"] = json!("P(idx(1,1))^2-arbitrary_mass_label^2");
        assert!(checked(definition).is_ok());
    }

    #[test]
    fn rejects_unrepresented_powers_normalizations_and_mass_changes() {
        for denominator in [
            "(P(idx(1,1))^2-mass^2)^2",
            "2*(P(idx(1,1))^2-mass^2)",
            "P(idx(1,1))^2+mass^2",
            "P(idx(1,1))^2-mass^2+g",
            "P(idx(1,2))^2-mass^2",
            "other::P(other::idx(1,1))^2-mass^2",
        ] {
            let mut definition = scalar_definition();
            definition["propagators"][0]["denominator"] = json!(denominator);
            assert!(checked(definition).is_err(), "accepted {denominator}");
        }
    }

    #[test]
    fn finite_width_requires_the_explicit_matching_positive_imaginary_term() {
        let mut definition = scalar_definition();
        definition["particles"][0]["width"] = json!("g");
        assert!(checked(definition.clone()).is_err());
        definition["propagators"][0]["denominator"] = json!("P(idx(1,1))^2-mass^2+1𝑖*mass*g");
        assert!(checked(definition.clone()).is_ok());
        definition["propagators"][0]["denominator"] = json!("P(idx(1,1))^2-mass^2-1𝑖*mass*g");
        assert!(checked(definition).is_err());
    }

    #[test]
    fn adjustable_zero_chemical_potential_is_not_a_vacuum_proof() {
        let mut definition = scalar_definition();
        definition["particles"][0]["chemical_potential"] = json!("g");
        let parameter = definition["parameters"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .find(|parameter| parameter["name"] == "g")
            .unwrap();
        parameter["value"] = json!([0.0, 0.0]);
        assert!(checked(definition).is_err());
        let mut definition = scalar_definition();
        definition["particles"][0]["chemical_potential"] = json!("ZERO");
        assert!(checked(definition).is_ok());
    }

    #[test]
    fn equal_ranks_do_not_erase_numerator_normalizations() {
        let first = checked(scalar_definition()).unwrap();
        let mut definition = scalar_definition();
        definition["propagators"][0]["numerator"] = json!("2𝑖");
        let second = checked(definition).unwrap();
        assert_ne!(first, second);
        assert_eq!(
            crate::preparation::momentum_degree(&first.numerator, None).unwrap(),
            crate::preparation::momentum_degree(&second.numerator, None).unwrap(),
        );
    }

    #[test]
    fn supported_scalar_momentum_numerator_retains_its_rank() {
        let mut definition = scalar_definition();
        definition["propagators"][0]["denominator"] = json!("P^2-mass^2");
        definition["propagators"][0]["numerator"] = json!("1𝑖*P^2");
        let propagator = checked(definition).unwrap();
        assert_eq!(
            crate::preparation::momentum_degree(&propagator.numerator, None).unwrap(),
            2
        );
    }

    #[test]
    fn conjugate_template_fallback_retains_orientation() {
        let model = Model::scalar_qed();
        let mut definition: Value = serde_json::from_str(&model.to_json().unwrap()).unwrap();
        definition["particles"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .find(|particle| particle["name"] == "phi-")
            .unwrap()["propagator"] = Value::Null;
        definition["propagators"]
            .as_array_mut()
            .unwrap()
            .retain(|propagator| propagator["particle"] != "phi-");
        let model = Model::from_json(&definition.to_string()).unwrap();
        let zeros = BTreeSet::from(["ZERO".into()]);
        let positive =
            validated_propagator(&model, model.particle("phi+").unwrap(), &zeros).unwrap();
        let negative =
            validated_propagator(&model, model.particle("phi-").unwrap(), &zeros).unwrap();
        assert!(!positive.reversed);
        assert!(negative.reversed);
        assert_eq!(positive.numerator, negative.numerator);
        assert_ne!(positive, negative);
    }
}
