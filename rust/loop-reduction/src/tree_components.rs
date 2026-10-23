// SPDX-License-Identifier: 0BSD

//! Exact finite-component contraction at the checked tree-tensor boundary.
//! FeynKit owns the coherent amplitude and physical external-state ports;
//! Spenso owns component realization, metric signs and contraction ordering.

use std::collections::BTreeMap;

use idenso::{CookMode, CookSettings, color::CS, epsilon::EPSILON_SYMBOL, tensor::SymbolicTensor};
use rusticol_core::{RusticolError, RusticolResult};
use spenso::{
    network::{
        MinIntermediateCost, Network, Sequential,
        library::{
            function_lib::{INBUILTS, SymbolLib, Wrap},
            symbolic::ExplicitKey,
        },
        parsing::{ParseSettings, ShadowedStructure},
        store::NetworkStore,
        tags::SPENSO_TAG,
    },
    structure::{
        Canonicalized,
        abstract_index::AbstractIndex,
        partial::PartialStructure,
        representation::{LibraryRep, Minkowski, RepName, Representation},
    },
    tensors::{data::StorageTensor, parametric::ParamTensor},
};
use spenso_hep_lib::hep_lib_atom;
use symbolica::atom::{Atom, AtomCore, AtomView, Symbol};

type ComponentTensor = ParamTensor<ShadowedStructure<AbstractIndex>>;
type ComponentNetwork =
    Network<NetworkStore<ComponentTensor, Atom>, ExplicitKey<AbstractIndex>, Symbol, AbstractIndex>;

/// One exact rank-one tensor supplied to the existing component library.
pub(crate) struct TreeComponentVector {
    pub representation: Representation<LibraryRep>,
    pub components: [Atom; 4],
}

fn error(message: impl std::fmt::Display) -> RusticolError {
    RusticolError::invalid_argument(format!("native tree component contraction: {message}"))
}

/// Contract a checked closed tensor using exact four-dimensional SU(3) data.
///
/// Vector keys are unindexed heads, such as `p(leg)` or an axial-reference
/// symbol. Values are contravariant `(E, px, py, pz)` components; the component
/// library supplies the Minkowski metric. Scalar parameters and the reality
/// assumptions of physical momentum components belong to the caller.
pub(crate) fn contract_tree_components(
    source: SymbolicTensor<PartialStructure>,
    momenta: &BTreeMap<Atom, [Atom; 4]>,
) -> RusticolResult<Atom> {
    let vectors = momenta
        .iter()
        .map(|(head, components)| {
            (
                head.clone(),
                TreeComponentVector {
                    representation: Minkowski {}.new_rep(4).to_lib(),
                    components: components.clone(),
                },
            )
        })
        .collect();
    contract_tree_state_components(source, &vectors)
}

/// The same exact contraction accepts typed spinor wavefunction inputs as well
/// as momenta. Representation and metric conventions remain owned by Spenso.
pub(crate) fn contract_tree_state_components(
    source: SymbolicTensor<PartialStructure>,
    vectors: &BTreeMap<Atom, TreeComponentVector>,
) -> RusticolResult<Atom> {
    for head in [*EPSILON_SYMBOL, CS.d] {
        if source.expression().contains_symbol(head) {
            return Err(RusticolError::unsupported_runtime_capability(
                "native-tree-components",
                format!("the exact component library does not supply {head}"),
            ));
        }
    }
    let mut library = hep_lib_atom::<AbstractIndex, ParamTensor<ExplicitKey<AbstractIndex>>>();
    for (momentum, vector) in vectors {
        let (head, args) = match momentum.as_view() {
            AtomView::Var(variable) => (variable.get_symbol(), None),
            AtomView::Fun(function) => (
                function.get_symbol(),
                Some(
                    function
                        .iter()
                        .map(|argument| argument.to_owned())
                        .collect(),
                ),
            ),
            _ => return Err(error("a momentum key must be an unindexed vector head")),
        };
        let key = ExplicitKey::from_iter([vector.representation], head, args);
        library
            .insert_explicit_dense(key, vector.components.to_vec())
            .map_err(error)?;
    }
    let mut functions: SymbolLib<ComponentTensor, Wrap> = Wrap::new_lib();
    functions.insert(INBUILTS.conj, |tensor| {
        tensor.map_data_self(|component| component.conj())
    });
    functions.insert_scalar_fallible(INBUILTS.conj, |component| Ok(component.conj()));
    let cooking = CookSettings::indices().with_mode(CookMode::ReversibleEncoding);
    let lowered: Canonicalized<ComponentNetwork> = source
        .into_network(
            &library,
            &functions,
            &ParseSettings::default(),
            Some(&cooking),
        )
        .map_err(error)?;
    let (mut network, layout) = lowered.into_parts();
    network.graph.contract_ready_sum_boundaries();
    network
        .execute::<Sequential, MinIntermediateCost, _, _, _>(&library, &functions)
        .map_err(error)?;
    // Retain the logical-axis mapping through execution. Future open spin/color
    // results can reuse this owner path and extract a tensor with this layout.
    let scalar: Atom = network.result_scalar().map_err(error)?.into();
    drop(layout);
    let mut unresolved_tensor = None;
    scalar.visitor(&mut |value| {
        if let AtomView::Fun(function) = value {
            if function.get_symbol().has_tag(&SPENSO_TAG.tensor) {
                unresolved_tensor = Some(function.get_symbol());
                return false;
            }
        }
        unresolved_tensor.is_none()
    });
    if let Some(head) = unresolved_tensor {
        return Err(RusticolError::unsupported_runtime_capability(
            "native-tree-components",
            format!("component contraction left an unresolved tensor {head}"),
        ));
    }
    Ok(scalar)
}

#[cfg(test)]
mod tests {
    use super::*;
    use symbolica::{function, parse};

    #[test]
    fn exact_component_contraction_preserves_metadata_metric_and_phase() {
        let head = spenso::vector_symbol!("native_tree_components_test::p");
        let p = function!(head, 17, 2);
        let reference = Atom::var(spenso::vector_symbol!("native_tree_components_test::n"));
        let rep = Minkowski {}.new_rep(4);
        let phase = Atom::one() + Atom::i();
        let source = SymbolicTensor::infer(
            &phase * rep.inner_product(&p, &p) + rep.inner_product(&p, &reference),
        )
        .unwrap();
        let energy = parse!("1+1/1208925819614629174706176");
        let momenta = BTreeMap::from([
            (
                p,
                [energy.clone(), Atom::num(1), Atom::num(2), Atom::num(3)],
            ),
            (reference, [Atom::one(), Atom::Zero, Atom::Zero, Atom::Zero]),
        ]);
        let expected = phase * (&energy * &energy - Atom::num(14)) + energy;
        assert_eq!(
            contract_tree_components(source, &momenta).unwrap(),
            expected
        );
    }

    #[test]
    fn component_contraction_rejects_an_unclosed_port() {
        let p = Atom::var(spenso::vector_symbol!(
            "native_tree_components_test::open_p"
        ));
        let source =
            SymbolicTensor::infer(Minkowski {}.new_rep(4).vector(p.as_view(), [Atom::num(7)]))
                .unwrap();
        let momenta = BTreeMap::from([(p, [Atom::one(), Atom::Zero, Atom::Zero, Atom::Zero])]);
        assert!(contract_tree_components(source, &momenta).is_err());
    }

    #[test]
    fn component_contraction_rejects_missing_component_data() {
        // Spenso may realize an absent library entry as formal shadow
        // components. Those must not escape as an executable physical norm.
        let p = Atom::var(spenso::vector_symbol!(
            "native_tree_components_test::missing_p"
        ));
        let source = SymbolicTensor::infer(Minkowski {}.new_rep(4).inner_product(&p, &p)).unwrap();
        let failure = contract_tree_components(source, &BTreeMap::new()).unwrap_err();
        assert!(failure.to_string().contains("unresolved tensor"));
    }
}
