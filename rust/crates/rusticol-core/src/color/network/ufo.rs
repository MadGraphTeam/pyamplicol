// SPDX-License-Identifier: 0BSD

//! Typed counterpart of `models/tensors.py::_ColorContext`. Lower directly to
//! the same tau networks instead of constructing an intermediate Spenso AST.

use super::*;
use symbolica::{
    atom::{Atom, AtomCore, AtomView},
    coefficient::{Coefficient, CoefficientView},
};

/// External model slots are one based. Negative UFO dummy labels occupy their
/// representation's own namespace; upper/lower fundamental slots with the same
/// dummy label denote the same contracted index.
/// This deliberately unifies their labels; the Python normalization's slot-kind
/// suffixes must not split the two ends of one internal fundamental contraction.
#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd)]
pub enum UfoColorIndex {
    Leg(usize),
    AdjointDummy(i64),
    FundamentalDummy(i64),
}

fn function(atom: AtomView<'_>) -> RusticolResult<(String, Vec<AtomView<'_>>)> {
    let AtomView::Fun(function) = atom else {
        return Err(invalid("expected a UFO color tensor"));
    };
    Ok((
        function
            .get_symbol()
            .get_name()
            .rsplit("::")
            .next()
            .unwrap_or("")
            .to_owned(),
        function.iter().collect(),
    ))
}

fn integer(atom: AtomView<'_>) -> RusticolResult<i64> {
    if let AtomView::Num(number) = atom {
        if let CoefficientView::Natural(value, 1, 0, _) = number.get_coeff_view() {
            if value != 0 {
                return Ok(value);
            }
        }
    }
    Err(invalid("UFO color indices must be nonzero signed integers"))
}

fn index(
    atom: AtomView<'_>,
    expected: ColorRepresentation,
    representations: &[ColorRepresentation],
) -> RusticolResult<UfoColorIndex> {
    let label = integer(atom)?;
    if label > 0 {
        let leg =
            usize::try_from(label).map_err(|_| invalid("UFO color leg does not fit an index"))?;
        if representations.get(leg - 1) != Some(&expected) {
            return Err(invalid(
                "UFO color slot has the wrong model representation or refers to an absent leg",
            ));
        }
        Ok(UfoColorIndex::Leg(leg))
    } else {
        match expected {
            ColorRepresentation::Adjoint => Ok(UfoColorIndex::AdjointDummy(label)),
            ColorRepresentation::Fundamental | ColorRepresentation::Antifundamental => {
                Ok(UfoColorIndex::FundamentalDummy(label))
            }
            ColorRepresentation::Singlet => Err(invalid("a singlet has no color index")),
        }
    }
}

fn factor(
    atom: AtomView<'_>,
    representations: &[ColorRepresentation],
) -> RusticolResult<ColorNetwork<UfoColorIndex>> {
    use ColorRepresentation::*;
    if let AtomView::Num(number) = atom {
        let Coefficient::Complex(coefficient) = number.get_coeff_view().to_owned() else {
            return Err(invalid(
                "UFO color coefficients must be exact complex rational numbers",
            ));
        };
        return Ok(vec![ColorProduct {
            coefficient,
            ..Default::default()
        }]);
    }
    let (head, args) = function(atom)?;
    match head.as_str() {
        "T" if args.len() == 3 => {
            let a = index(args[0], Adjoint, representations)?;
            let row = index(args[1], Fundamental, representations)?;
            let col = index(args[2], Antifundamental, representations)?;
            Ok(vec![ColorProduct {
                strings: vec![ColorString {
                    row,
                    word: vec![a],
                    col,
                }],
                root2_power: 1,
                ..Default::default()
            }])
        }
        "f" | "d" if args.len() == 3 => {
            let a = index(args[0], Adjoint, representations)?;
            let b = index(args[1], Adjoint, representations)?;
            let c = index(args[2], Adjoint, representations)?;
            let (first, second) = if head == "f" {
                (
                    Complex::new(Rational::from(0), Rational::from(-1)),
                    Complex::new(Rational::from(0), Rational::from(1)),
                )
            } else {
                // d^abc = 2 tr({t^a,t^b}t^c): one inverse sqrt(2)
                // multiplies the sum of the two tau traces.
                (
                    Complex::new(Rational::from(1), Rational::from(0)),
                    Complex::new(Rational::from(1), Rational::from(0)),
                )
            };
            Ok(vec![
                ColorProduct {
                    coefficient: first,
                    traces: vec![vec![a.clone(), b.clone(), c.clone()]],
                    root2_power: 1,
                    ..Default::default()
                },
                ColorProduct {
                    coefficient: second,
                    traces: vec![vec![a, c, b]],
                    root2_power: 1,
                    ..Default::default()
                },
            ])
        }
        "Identity" if args.len() == 2 => {
            let labels = [integer(args[0])?, integer(args[1])?];
            if labels.iter().any(|&label| label < 1) {
                return Err(invalid("UFO Identity requires two external model slots"));
            }
            let mut kinds = Vec::new();
            for &label in &labels {
                let leg = usize::try_from(label)
                    .map_err(|_| invalid("UFO color leg does not fit an index"))?;
                kinds.push(
                    *representations
                        .get(leg - 1)
                        .ok_or_else(|| invalid("UFO Identity refers to an absent leg"))?,
                );
            }
            match kinds.as_slice() {
                [Adjoint, Adjoint] => Ok(vec![ColorProduct {
                    traces: vec![vec![
                        index(args[0], Adjoint, representations)?,
                        index(args[1], Adjoint, representations)?,
                    ]],
                    ..Default::default()
                }]),
                [Fundamental, Antifundamental] | [Antifundamental, Fundamental] => {
                    let (upper, lower) = if kinds[0] == Fundamental {
                        (args[0], args[1])
                    } else {
                        (args[1], args[0])
                    };
                    Ok(vec![ColorProduct {
                        strings: vec![ColorString {
                            row: index(upper, Fundamental, representations)?,
                            word: vec![],
                            col: index(lower, Antifundamental, representations)?,
                        }],
                        ..Default::default()
                    }])
                }
                _ => Err(invalid(
                    "UFO Identity must join adjoints or dual fundamental representations",
                )),
            }
        }
        _ => Err(invalid(
            "unsupported UFO color tensor; expected Identity, T, f or d",
        )),
    }
}

/// Prepare exact vertex color networks directly from raw UFO model atoms.
///
/// `representations` are the signed representations in the model's vertex
/// particle order. Their fundamental slots are matrix *upper* indices, as in
/// the existing UFO-to-Spenso normalization, and antifundamentals are lower.
/// This function does not cross process legs. Before multiplying different
/// vertices, callers must use [`ColorProduct::relabel`] on *every* index: connect
/// `UfoColorIndex::Leg` slots to the required process/current labels and scope
/// dummy indices to that vertex. For example, map a dummy to `(vertex_id, index)`;
/// two vertices may independently use the same negative UFO label. Supports `Identity`,
/// `T`, `f`, `d`, exact numbers and their sums/products. Oriented current metrics
/// with two equal fundamental roles require an explicit orientation adapter.
pub fn ufo_color_network(
    expression: &Atom,
    representations: &[ColorRepresentation],
) -> RusticolResult<ColorNetwork<UfoColorIndex>> {
    let expanded = expression.expand();
    let summands = if let AtomView::Add(sum) = expanded.as_view() {
        sum.iter().collect()
    } else {
        vec![expanded.as_view()]
    };
    let mut result = Vec::new();
    for summand in summands {
        let factors = if let AtomView::Mul(product) = summand {
            product.iter().collect()
        } else {
            vec![summand]
        };
        let mut terms = vec![ColorProduct::default()];
        for atom in factors {
            terms = multiply(&terms, &factor(atom, representations)?)?;
        }
        result.extend(terms);
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use ColorRepresentation::*;
    fn parse(value: &str) -> Atom {
        Atom::parse(value, "UFO", Default::default()).unwrap()
    }
    fn external(
        representations: &[ColorRepresentation],
    ) -> (Vec<ColorLeg>, BTreeMap<UfoColorIndex, i64>) {
        // A vertex's matrix upper/lower slots are dual to literal outgoing
        // endpoints. A process adapter normally supplies its own relabeling.
        let legs = representations
            .iter()
            .enumerate()
            .map(|(index, rep)| ColorLeg {
                label: (index + 1) as i64,
                representation: rep.conjugate(),
            })
            .collect();
        let mapping = representations
            .iter()
            .enumerate()
            .filter(|(_, rep)| **rep != Singlet)
            .map(|(index, _)| (UfoColorIndex::Leg(index + 1), (index + 1) as i64))
            .collect();
        (legs, mapping)
    }
    fn tensor(value: &str, representations: &[ColorRepresentation]) -> ConnectedColorTensor {
        let (legs, mapping) = external(representations);
        reduce_network(
            &ufo_color_network(&parse(value), representations).unwrap(),
            legs,
            &mapping,
        )
        .unwrap()
    }
    fn exact(n: i64, d: i64) -> ExactColorCoefficient {
        Complex::new(Rational::from((n, d)), Rational::from(0))
    }

    #[test]
    fn raw_ufo_generators_match_spenso_and_symmetric_invariant_normalization() {
        let reps = [Antifundamental, Fundamental, Adjoint];
        let raw = tensor("T(3,2,1)", &reps);
        let translated = spenso_color_network(
            &Atom::parse(
                "t(coad(8,e::a),cof(3,e::i),dind(cof(3,e::j)))",
                "spenso",
                Default::default(),
            )
            .unwrap(),
        )
        .unwrap();
        let normalized = reduce_network(
            &translated,
            external(&reps).0,
            &BTreeMap::from([("e::a".into(), 3), ("e::i".into(), 2), ("e::j".into(), 1)]),
        )
        .unwrap();
        assert_eq!(raw.terms(), normalized.terms());
        assert_eq!(raw.normalization_power(), normalized.normalization_power());
        assert_eq!(raw.overlap(&raw).unwrap(), exact(4, 1));
        let d = tensor("d(1,2,3)", &[Adjoint; 3]);
        assert_eq!(d.overlap(&d).unwrap(), exact(40, 3));
        let f = tensor("f(1,2,3)", &[Adjoint; 3]);
        assert_eq!(f.overlap(&f).unwrap(), exact(24, 1));
        assert_eq!(d.overlap(&f).unwrap(), exact(0, 1));
    }

    #[test]
    fn raw_ufo_dummy_contractions_and_jacobi_identity() {
        let reps = [Antifundamental, Fundamental, Adjoint, Adjoint];
        let chained = tensor("T(3,2,-1)*T(4,-1,1)", &reps);
        assert_eq!(chained.terms().len(), 1);
        assert_eq!(
            chained.terms()[0].tensor.open_strings()[0].adjoints,
            vec![4, 3]
        );
        assert_eq!(chained.overlap(&chained).unwrap(), exact(16, 3));
        let jacobi = tensor(
            "f(1,2,-1)*f(-1,3,4)+f(2,3,-1)*f(-1,1,4)+f(3,1,-1)*f(-1,2,4)",
            &[Adjoint; 4],
        );
        assert!(jacobi.terms().is_empty());
        let ff = tensor("f(1,2,-1)*f(-1,3,4)", &[Adjoint; 4]);
        assert_eq!(ff.overlap(&ff).unwrap(), exact(72, 1));
    }

    #[test]
    fn independent_vertices_scope_their_internal_dummy_indices() {
        let network = ufo_color_network(&parse("f(1,2,-1)*f(-1,3,4)"), &[Adjoint; 4]).unwrap();
        // Two independent four-gluon vertices each use -1 locally. Their four
        // boundary indices are contracted, while the two dummy lines differ.
        let scoped = |vertex| {
            network
                .iter()
                .map(|term| {
                    term.relabel(|index| {
                        (
                            if matches!(index, UfoColorIndex::Leg(_)) {
                                0
                            } else {
                                vertex
                            },
                            index.clone(),
                        )
                    })
                })
                .collect::<Vec<_>>()
        };
        let closed = reduce_network(
            &multiply(&scoped(1), &scoped(2)).unwrap(),
            vec![],
            &BTreeMap::new(),
        )
        .unwrap();
        let values: ColorNcTerms = closed
            .terms()
            .iter()
            .map(|term| (term.nc_power, term.coefficient.clone()))
            .collect();
        assert_eq!(evaluate_nc_terms(&values, 3).unwrap(), exact(72, 1));
        assert!(
            reduce_network(
                &multiply(&network, &network).unwrap(),
                vec![],
                &BTreeMap::new()
            )
            .is_err()
        );
    }

    #[test]
    fn colorless_identity_and_invalid_raw_model_slots() {
        let scalar = tensor("1", &[Singlet, Singlet, Singlet]);
        assert_eq!(scalar.overlap(&scalar).unwrap(), exact(1, 1));
        let delta = tensor("Identity(1,2)", &[Fundamental, Antifundamental]);
        assert_eq!(delta.overlap(&delta).unwrap(), exact(3, 1));
        let adjoint = tensor("Identity(1,2)", &[Adjoint, Adjoint]);
        assert_eq!(adjoint.overlap(&adjoint).unwrap(), exact(8, 1));
        for value in [
            "T(3,1,2)",
            "T(4,2,1)",
            "T(0,2,1)",
            "T(3,2,1/2)",
            "f(1,2,3)",
            "Identity(-1,2)",
            "Epsilon(1,2,3)",
        ] {
            assert!(
                ufo_color_network(&parse(value), &[Antifundamental, Fundamental, Adjoint]).is_err(),
                "{value}"
            );
        }
        assert!(ufo_color_network(&parse("Identity(1,2)"), &[Fundamental, Fundamental]).is_err());
    }
}
