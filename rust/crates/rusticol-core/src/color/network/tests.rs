// SPDX-License-Identifier: 0BSD

use super::*;
use ColorRepresentation::*;
use symbolica::atom::Atom;

fn expression(value: &str) -> Atom {
    Atom::parse(value, "spenso", Default::default()).unwrap()
}
fn leg(label: i64, representation: ColorRepresentation) -> ColorLeg {
    ColorLeg {
        label,
        representation,
    }
}
fn coefficient(numerator: i64, denominator: i64) -> ExactColorCoefficient {
    Complex::new(Rational::from((numerator, denominator)), Rational::from(0))
}
fn lower(value: &str, slots: &[(&str, i64, ColorRepresentation)]) -> ConnectedColorTensor {
    let legs = slots
        .iter()
        .map(|&(_, label, representation)| leg(label, representation))
        .collect();
    let external = slots
        .iter()
        .map(|&(name, label, _)| (format!("e::{name}"), label))
        .collect();
    reduce_network(
        &spenso_color_network(&expression(value)).unwrap(),
        legs,
        &external,
    )
    .unwrap()
}

#[test]
fn spenso_generators_and_structure_constants_have_physical_normalization() {
    let generator = lower(
        "t(coad(8,e::a),cof(3,e::i),dind(cof(3,e::j)))",
        &[
            ("a", 3, Adjoint),
            ("i", 2, Antifundamental),
            ("j", 1, Fundamental),
        ],
    );
    assert_eq!(generator.normalization_power(), 1);
    assert_eq!(
        generator.terms()[0].tensor.open_strings()[0],
        OpenColorString {
            fundamental: 1,
            adjoints: vec![3],
            antifundamental: 2
        }
    );
    assert_eq!(generator.overlap(&generator).unwrap(), coefficient(4, 1));
    let structure = lower(
        "f(coad(8,e::a),coad(8,e::b),coad(8,e::c))",
        &[("a", 1, Adjoint), ("b", 2, Adjoint), ("c", 3, Adjoint)],
    );
    assert_eq!(structure.overlap(&structure).unwrap(), coefficient(24, 1));
    let swapped = lower(
        "f(coad(8,e::a),coad(8,e::c),coad(8,e::b))",
        &[("a", 1, Adjoint), ("b", 2, Adjoint), ("c", 3, Adjoint)],
    );
    assert_eq!(structure.overlap(&swapped).unwrap(), coefficient(-24, 1));
    let network =
        spenso_color_network(&expression("f(coad(8,e::a),coad(8,e::b),coad(8,e::c))")).unwrap();
    let contracted = reduce_network(
        &multiply(&network, &network).unwrap(),
        vec![],
        &BTreeMap::new(),
    )
    .unwrap();
    assert_eq!(contracted.normalization_power(), 0);
    let values: BTreeMap<_, _> = contracted
        .terms()
        .iter()
        .map(|term| (term.nc_power, term.coefficient.clone()))
        .collect();
    assert_eq!(
        values,
        BTreeMap::from([(3, coefficient(1, 1)), (1, coefficient(-1, 1))])
    );
}

#[test]
fn open_network_fierz_preserves_subleading_color_and_matrix_orientation() {
    let tensor = lower(
        "t(coad(8,x::a),cof(3,e::i),dind(cof(3,e::j)))*t(coad(8,x::a),cof(3,e::k),dind(cof(3,e::l)))",
        &[
            ("i", 2, Antifundamental),
            ("j", 1, Fundamental),
            ("k", 4, Antifundamental),
            ("l", 3, Fundamental),
        ],
    );
    assert_eq!(tensor.normalization_power(), 0);
    assert_eq!(tensor.terms().len(), 2);
    for term in tensor.terms() {
        let endpoints: Vec<_> = term
            .tensor
            .open_strings()
            .iter()
            .map(|string| (string.fundamental, string.antifundamental))
            .collect();
        if term.nc_power == 0 {
            assert_eq!(endpoints, vec![(1, 4), (3, 2)]);
            assert_eq!(term.coefficient, coefficient(1, 2));
        } else {
            assert_eq!(term.nc_power, -1);
            assert_eq!(endpoints, vec![(1, 2), (3, 4)]);
            assert_eq!(term.coefficient, coefficient(-1, 2));
        }
    }
    assert_eq!(tensor.overlap(&tensor).unwrap(), coefficient(2, 1));
    let casimir = lower(
        "chain(cof(3,e::i),dind(cof(3,e::j)),t(coad(8,x::a),in,out),t(coad(8,x::a),in,out))",
        &[("i", -2, Antifundamental), ("j", -1, Fundamental)],
    );
    let values: BTreeMap<_, _> = casimir
        .terms()
        .iter()
        .map(|term| (term.nc_power, term.coefficient.clone()))
        .collect();
    assert_eq!(
        values,
        BTreeMap::from([(1, coefficient(1, 2)), (-1, coefficient(-1, 2))])
    );
    assert_eq!(casimir.overlap(&casimir).unwrap(), coefficient(16, 3));
}

#[test]
fn fundamental_joining_and_trace_conversion_agree_with_explicit_chain() {
    let slots = [
        ("i", 2, Antifundamental),
        ("j", 1, Fundamental),
        ("a", 3, Adjoint),
        ("b", 4, Adjoint),
    ];
    let joined = lower(
        "t(coad(8,e::a),cof(3,e::i),dind(cof(3,x::k)))*id(cof(3,x::k),dind(cof(3,x::l)))*t(coad(8,e::b),cof(3,x::l),dind(cof(3,e::j)))",
        &slots,
    );
    let chain = lower(
        "chain(cof(3,e::i),dind(cof(3,e::j)),t(coad(8,e::a),in,out),t(coad(8,e::b),in,out))",
        &slots,
    );
    assert_eq!(joined.terms(), chain.terms());
    assert_eq!(
        joined.terms()[0].tensor.open_strings()[0].adjoints,
        vec![4, 3]
    );
    let traced = lower(
        "trace(cof(3),cyclic(t(coad(8,e::a),in,out),t(coad(8,e::b),in,out),t(coad(8,e::c),in,out)))",
        &[("a", 1, Adjoint), ("b", 2, Adjoint), ("c", 3, Adjoint)],
    );
    assert_eq!(traced.normalization_power(), 1);
    assert_eq!(traced.terms()[0].coefficient, coefficient(1, 2));
    assert_eq!(traced.terms()[0].tensor.traces(), &[vec![1, 3, 2]]);
    assert_eq!(traced.overlap(&traced).unwrap(), coefficient(7, 3));
    let loop_ = spenso_color_network(&expression(
        "id(cof(3,x::a),dind(cof(3,x::b)))*id(cof(3,x::b),dind(cof(3,x::a)))",
    ))
    .unwrap();
    let closed = reduce_network(&loop_, vec![], &BTreeMap::new()).unwrap();
    assert_eq!(closed.terms()[0].nc_power, 1);
    assert_eq!(closed.terms()[0].coefficient, coefficient(1, 1));
}

#[test]
fn exact_complex_numbers_relabeling_and_normalization_transfers() {
    let value = expression("(1+2*𝑖)/123456789012345678901234567890");
    let parsed = spenso_color_network(&value).unwrap();
    assert_eq!(parsed.len(), 1);
    assert_ne!(parsed[0].coefficient.re, Rational::from(0));
    assert_eq!(
        parsed[0].coefficient.im,
        &parsed[0].coefficient.re * &Rational::from(2)
    );
    let original: ColorProduct<&str> = ColorProduct {
        strings: vec![ColorString {
            row: "upper",
            word: vec![],
            col: "lower",
        }],
        root2_power: -2,
        ..Default::default()
    };
    let relabeled = original.relabel(|label| if *label == "upper" { -2 } else { -1 });
    let result = reduce_network(
        &[relabeled],
        vec![leg(-1, Fundamental), leg(-2, Antifundamental)],
        &BTreeMap::from([(-1, -1), (-2, -2)]),
    )
    .unwrap();
    assert_eq!(result.normalization_power(), 0);
    assert_eq!(result.terms()[0].coefficient, coefficient(2, 1));
    assert_eq!(result.overlap(&result).unwrap(), coefficient(12, 1));
}

#[test]
fn malformed_networks_and_unsupported_model_tensors_fail_explicitly() {
    let traceless =
        spenso_color_network(&expression("trace(cof(3),cyclic(t(coad(8,e::a),in,out)))")).unwrap();
    let external = BTreeMap::from([("e::a".to_owned(), 1)]);
    assert!(reduce_network(&traceless, vec![leg(1, Fundamental)], &external).is_err());
    assert!(
        reduce_network(
            &traceless,
            vec![leg(1, Adjoint), leg(2, Adjoint)],
            &external
        )
        .is_err()
    );
    assert!(
        reduce_network(&traceless, vec![leg(1, Adjoint)], &external)
            .unwrap()
            .terms()
            .is_empty()
    );
    let explicit_zero = spenso_color_network(&expression("0")).unwrap();
    assert!(
        reduce_network(&explicit_zero, vec![leg(1, Fundamental)], &external)
            .unwrap()
            .terms()
            .is_empty()
    );
    for value in [
        "t(coad(9,a),cof(3,b),dind(cof(3,c)))",
        "trace(cof(6),cyclic(t(coad(8,a),in,out)))",
        "t(coad(8,a),dind(cof(3,b)),cof(3,c))",
        "f(coad(8,a),cof(3,b),coad(8,c))",
        "d(coad(8,a),coad(8,b),coad(8,c))",
        "parameter*t(coad(8,a),cof(3,b),dind(cof(3,c)))",
    ] {
        assert!(spenso_color_network(&expression(value)).is_err(), "{value}");
    }
    for value in [
        "t(coad(8,x::a),cof(3,e::i),dind(cof(3,e::j)))", // unpaired internal adjoint
        "t(coad(8,x::a),cof(3,e::i),dind(cof(3,x::k)))", // dangling fundamental
    ] {
        let network = spenso_color_network(&expression(value)).unwrap();
        assert!(
            reduce_network(
                &network,
                vec![leg(1, Fundamental), leg(2, Antifundamental)],
                &BTreeMap::from([("e::i".into(), 2), ("e::j".into(), 1)])
            )
            .is_err()
        );
    }
    let zero: ColorNetwork<i64> = vec![];
    assert!(
        reduce_network(
            &zero,
            vec![leg(1, Fundamental)],
            &BTreeMap::from([(1, 1), (2, 1)])
        )
        .is_err()
    );
    let identity = ColorProduct::<i64>::default();
    let odd = ColorProduct::<i64> {
        root2_power: 1,
        ..Default::default()
    };
    assert!(reduce_network(&[identity, odd], vec![], &BTreeMap::new()).is_err());
    let bad = ColorProduct {
        strings: vec![
            ColorString {
                row: 1,
                word: vec![],
                col: 2,
            },
            ColorString {
                row: 1,
                word: vec![],
                col: 3,
            },
        ],
        ..Default::default()
    };
    assert!(reduce_network(&[bad], vec![], &BTreeMap::new()).is_err());
}
