// SPDX-License-Identifier: 0BSD

use std::{collections::BTreeMap, sync::Arc};

use feynkit_generator::{GenerationOptions, Process};
use feynkit_model::Model;
use rusticol_core::{RusticolErrorKind, color::ExactColorCoefficient};
use symbolica::{
    atom::{Atom, Symbol},
    domains::{
        float::{DoubleFloat, Float, FloatLike, Real, SingleFloat},
        rational::Rational,
    },
    symbol,
};

use super::*;
use crate::{
    Complex,
    runtime::{Arithmetic, Batch, BatchCarrier, CoefficientEvaluator, Data, wavefunctions_batch},
    tree_preparation::{TreeFieldClass, TreeProgram},
};

fn z(re: i64, im: i64) -> ExactColorCoefficient {
    Complex::new(re.into(), im.into())
}

fn exact_bilinear(
    matrix: &[Vec<ExactColorCoefficient>],
    bra: &[ExactColorCoefficient],
    ket: &[ExactColorCoefficient],
) -> ExactColorCoefficient {
    let mut result = z(0, 0);
    for b in 0..bra.len() {
        for c in 0..ket.len() {
            result += bra[b].conj() * &matrix[b][c] * &ket[c];
        }
    }
    result
}

fn coordinates<T: BatchCarrier>(
    bra: &[ExactColorCoefficient],
    ket: Option<&[ExactColorCoefficient]>,
    prototype: T,
    bits: u32,
) -> Batch {
    let values: Vec<_> = bra
        .iter()
        .chain(ket.into_iter().flatten())
        .flat_map(|z| [&z.re, &z.im])
        .map(|r| Complex::new(prototype.from_rational(r), prototype.zero()))
        .collect();
    let columns = values.len();
    Batch::typed(values, vec![91], columns, bits).unwrap()
}

#[test]
fn cartesian_bilinears_match_independent_exact_complex_double_sum_all_widths() {
    let matrices = vec![
        vec![vec![z(2, 0), z(1, 2)], vec![z(1, -2), z(3, 0)]],
        vec![vec![z(1, 1), z(-2, 3)], vec![z(4, -1), z(0, 2)]],
    ];
    let bra = vec![
        Complex::new((1, 3).into(), (2, 7).into()),
        Complex::new((-5, 11).into(), (3, 13).into()),
    ];
    let ket = vec![
        Complex::new((4, 9).into(), (-2, 5).into()),
        Complex::new((7, 17).into(), (-3, 19).into()),
    ];
    let (same, directed) = runtime::compile_states(&matrices).unwrap();
    for (state, other) in [(&same, None), (&directed, Some(ket.as_slice()))] {
        let expected: Vec<_> = matrices
            .iter()
            .map(|m| exact_bilinear(m, &bra, other.unwrap_or(&bra)))
            .flat_map(|z| [z.re, z.im])
            .collect();
        let out = CoefficientEvaluator::with_precision_bits(state, Arithmetic::Double, 53)
            .unwrap()
            .evaluate_batch(&coordinates(&bra, other, 0_f64, 53))
            .unwrap();
        let Data::Double(v) = out.data() else {
            panic!("carrier changed")
        };
        for (actual, expected) in v.iter().zip(&expected) {
            assert_eq!(actual.im, 0.);
            assert!((actual.re - expected.to_f64()).abs() < 1e-13);
        }
        let out = CoefficientEvaluator::with_precision_bits(state, Arithmetic::DoubleDouble, 106)
            .unwrap()
            .evaluate_batch(&coordinates(&bra, other, DoubleFloat::from(0.), 106))
            .unwrap();
        let Data::DoubleDouble(values) = out.data() else {
            panic!("carrier changed")
        };
        let prototype = DoubleFloat::from(0.);
        for (actual, expected) in values.iter().zip(&expected) {
            assert!(actual.im.is_fully_zero());
            assert!(
                (actual.re.clone() - prototype.from_rational(expected)).norm()
                    < DoubleFloat::from(2.).pow(90).inv()
            );
        }
        for bits in [113, 137, 256, 512, 1024] {
            let prototype = Float::with_val(bits, 0);
            let out = CoefficientEvaluator::with_precision_bits(state, Arithmetic::Arbitrary, bits)
                .unwrap()
                .evaluate_batch(&coordinates(&bra, other, prototype.clone(), bits))
                .unwrap();
            assert_eq!(out.precision_bits(), bits);
            let Data::Arbitrary(v) = out.data() else {
                panic!("carrier changed")
            };
            for (actual, expected) in v.iter().zip(&expected) {
                assert!(actual.im.is_fully_zero());
                assert!(
                    (actual.re.clone() - prototype.from_rational(expected)).norm()
                        < Float::with_val(bits, 2).pow(u64::from(bits - 20)).inv()
                );
            }
        }
    }
    // A Hermitian operator on independent vectors is not constrained to real.
    assert_ne!(
        exact_bilinear(&matrices[0], &bra, &ket).im,
        Rational::from(0)
    );
    // A non-Hermitian self product retains its physical imaginary component.
    assert_ne!(
        exact_bilinear(&matrices[1], &bra, &bra).im,
        Rational::from(0)
    );
}

#[test]
fn exact_hermitian_lowering_preserves_sub_binary64_phase_difference() {
    let matrix = vec![vec![z(0, 0), z(0, 1)], vec![z(0, -1), z(0, 0)]];
    let epsilon = Rational::from((1, 2)).pow(80);
    let vector = vec![
        z(1, 1),
        Complex::new(1.into(), Rational::from(1) + &epsilon),
    ];
    let expected = exact_bilinear(&matrix, &vector, &vector);
    assert_eq!(
        expected,
        Complex::new(-Rational::from(2) * epsilon, Rational::from(0))
    );
    let (same, _) = runtime::compile_states(&[matrix]).unwrap();
    let low = CoefficientEvaluator::with_precision_bits(&same, Arithmetic::Double, 53)
        .unwrap()
        .evaluate_batch(&coordinates(&vector, None, 0_f64, 53))
        .unwrap();
    let Data::Double(low) = low.data() else {
        panic!()
    };
    assert_eq!(low[0].re, 0.);
    for bits in [113, 137, 256, 512, 1024] {
        let zero = Float::with_val(bits, 0);
        let output = CoefficientEvaluator::with_precision_bits(&same, Arithmetic::Arbitrary, bits)
            .unwrap()
            .evaluate_batch(&coordinates(&vector, None, zero.clone(), bits))
            .unwrap();
        let Data::Arbitrary(v) = output.data() else {
            panic!()
        };
        assert_ne!(v[0].re, zero);
        assert!(
            (v[0].re.clone() - zero.from_rational(&expected.re)).norm()
                < Float::with_val(bits, 2).pow(u64::from(bits - 10)).inv()
        );
        assert!(v[1].re.is_fully_zero() && v[0].im.is_fully_zero() && v[1].im.is_fully_zero());
    }
}

fn qcd(incoming: [&str; 2], outgoing: [&str; 2], runtime_g: bool) -> Arc<TreeProgram> {
    let model = Arc::new(Model::qcd());
    let mut parameters: BTreeMap<Symbol, Atom> = BTreeMap::new();
    if !runtime_g {
        parameters.insert(symbol!("UFO::G"), Atom::one());
    }
    for particle in model.particles().iter().filter(|p| p.spin == 2) {
        let mass = model.parameter_by_id(particle.mass).unwrap();
        parameters.insert(symbol!(&format!("UFO::{}", mass.name)), Atom::Zero);
    }
    let runtime = if runtime_g {
        vec![crate::tree_preparation::RuntimeTreeParameter {
            symbol: symbol!("UFO::G"),
            domain: crate::tree_preparation::TreeParameterDomain::Real,
        }]
    } else {
        vec![]
    };
    Arc::new(
        TreeProgram::prepare_with_runtime_parameters(
            model,
            &Process::new(incoming, outgoing),
            &GenerationOptions::default().threads(1),
            None,
            &parameters,
            TreeFieldClass::MasslessQcdAndSingletScalars,
            &runtime,
        )
        .unwrap(),
    )
}

fn momenta<T: BatchCarrier>(prototype: T, bits: u32) -> Batch {
    let values = [5, 0, 0, 5, 5, 0, 0, -5, 5, 4, 0, 3, 5, -4, 0, -3]
        .into_iter()
        .map(|v| {
            Complex::new(
                prototype.from_rational(&Rational::from(v)),
                prototype.zero(),
            )
        })
        .collect();
    Batch::typed(values, vec![17], 16, bits).unwrap()
}

#[test]
fn generated_color_identities_crossings_and_runtime_parameters() {
    for (incoming, outgoing) in [
        (["u", "d"], ["u", "d"]),
        (["u", "u~"], ["d", "d~"]),
        (["u", "g"], ["u", "g"]),
        (["g", "g"], ["g", "g"]),
    ] {
        let tree = qcd(incoming, outgoing, true);
        let legs = tree.color_tensors()[0].legs();
        let first = legs[0].label;
        let mut requests = vec![TreeColorInsertion::Identity];
        requests.extend(legs.iter().map(|leg| TreeColorInsertion::Pair {
            left: first,
            right: leg.label,
        }));
        requests.push(TreeColorInsertion::Identity);
        let color = TreeColorProgram::prepare(tree.clone(), requests.clone()).unwrap();
        assert!(std::ptr::eq(color.tree(), tree.as_ref()));
        assert_eq!(color.requests(), requests);
        assert!(color.matrix_nc_terms(requests.len()).is_err());
        let p = momenta(0_f64, 53);
        let params = Batch::typed(vec![Complex::new(1., 0.)], vec![17], 1, 53).unwrap();
        let norm = tree
            .evaluator_with_precision_bits(Arithmetic::Double, 53)
            .unwrap()
            .evaluate_batch_with_parameters(&p, &params)
            .unwrap();
        let mut evaluator = color
            .evaluator_with_precision_bits(Arithmetic::Double, 53)
            .unwrap();
        let result = evaluator
            .evaluate_batch_with_parameters(&p, &params)
            .unwrap();
        let (Data::Double(v), Data::Double(norm)) = (result.data(), norm.data()) else {
            panic!()
        };
        assert_eq!(result.ids(), [17]);
        // A multi-output evaluator can share/reassociate exact subexpressions
        // differently from the one-output norm. Only numerical rounding may differ.
        assert!((v[0].re - norm[0].re).abs() <= 8. * f64::EPSILON * norm[0].re.abs());
        assert_eq!(v[0].im, norm[0].im);
        assert_eq!(v[0], v[v.len() - 1]);
        assert!(v.iter().all(|z| z.im == 0.));
        let casimir = match legs[0].representation {
            rusticol_core::color::ColorRepresentation::Adjoint => 3.,
            _ => 4. / 3.,
        };
        assert!((v[1].re - casimir * v[0].re).abs() < 1e-10 * v[0].re.abs());
        assert!(v[1..=legs.len()].iter().map(|z| z.re).sum::<f64>().abs() < 1e-10 * v[0].re.abs());
        let params2 = Batch::typed(vec![Complex::new(2., 0.)], vec![17], 1, 53).unwrap();
        let result2 = evaluator
            .evaluate_batch_with_parameters(&p, &params2)
            .unwrap();
        let Data::Double(v2) = result2.data() else {
            panic!()
        };
        for (a, b) in v.iter().zip(v2.iter()) {
            assert!((b.re - 16. * a.re).abs() < 1e-9 * v[0].re.abs());
        }
    }
}

#[test]
fn independent_external_components_keep_directed_complex_phase() {
    let tree = qcd(["u", "d"], ["u", "d"], false);
    let color =
        TreeColorProgram::prepare(tree.clone(), vec![TreeColorInsertion::Identity]).unwrap();
    let p = momenta(0_f64, 53);
    let mut native = tree
        .evaluator_with_precision_bits(Arithmetic::Double, 53)
        .unwrap();
    let components: Vec<_> = native
        .states()
        .iter()
        .map(|state| {
            wavefunctions_batch(
                &p.take_columns(state.momentum_columns.to_vec()).unwrap(),
                vec![state.helicities[0]],
                vec![state.kind.clone()],
                Some(4),
            )
            .unwrap()
        })
        .collect();
    let helicities: Vec<_> = native.states().iter().map(|s| s.helicities[0]).collect();
    let mut evaluator = color
        .evaluator_with_precision_bits(Arithmetic::Double, 53)
        .unwrap();
    let norm = evaluator
        .evaluate_fixed_helicities(&p, &helicities)
        .unwrap();
    let Data::Double(norm) = norm.data() else {
        panic!()
    };
    assert!(norm[0].re > 0.);
    let mut bra = components.clone();
    let mut ket = components.clone();
    let phase = |batch: &Batch, z: Complex<f64>| {
        let Data::Double(v) = batch.data() else {
            panic!()
        };
        Batch::typed(
            v.iter().map(|v| v * &z).collect(),
            batch.ids().to_vec(),
            4,
            53,
        )
        .unwrap()
    };
    bra[0] = phase(&bra[0], Complex::new(0., 2.));
    ket[0] = phase(&ket[0], Complex::new(3., -4.));
    let output = evaluator
        .evaluate_external_components(
            &p,
            &bra.iter().collect::<Vec<_>>(),
            &ket.iter().collect::<Vec<_>>(),
        )
        .unwrap();
    let Data::Double(value) = output.data() else {
        panic!()
    };
    assert!((value[0].re + 8. * norm[0].re).abs() < 1e-10 * norm[0].re);
    assert!((value[0].im + 6. * norm[0].re).abs() < 1e-10 * norm[0].re);
    let reverse = evaluator
        .evaluate_external_components(
            &p,
            &ket.iter().collect::<Vec<_>>(),
            &bra.iter().collect::<Vec<_>>(),
        )
        .unwrap();
    let Data::Double(reverse) = reverse.data() else {
        panic!()
    };
    assert!((reverse[0].re - value[0].re).abs() < 1e-10 * norm[0].re);
    assert!((reverse[0].im + value[0].im).abs() < 1e-10 * norm[0].re);
    // Metadata checks include independent component blocks on empty rows.
    let empty = Batch::typed::<f64>(vec![], vec![], 16, 53).unwrap();
    let valid: Vec<_> = (0..components.len())
        .map(|_| Batch::typed::<f64>(vec![], vec![], 4, 53).unwrap())
        .collect();
    let invalid = Batch::typed::<f64>(vec![], vec![], 3, 53).unwrap();
    let empty_result = evaluator
        .evaluate_external_components(
            &empty,
            &valid.iter().collect::<Vec<_>>(),
            &valid.iter().collect::<Vec<_>>(),
        )
        .unwrap();
    assert_eq!((empty_result.rows(), empty_result.columns()), (0, 1));
    let mut refs: Vec<_> = valid.iter().collect();
    refs[0] = &invalid;
    assert!(
        evaluator
            .evaluate_external_components(&empty, &valid.iter().collect::<Vec<_>>(), &refs)
            .is_err()
    );
    // The native coefficient method remains available and is not replaced by a density.
    assert_eq!(
        native
            .evaluate_coefficients(&p, &helicities)
            .unwrap()
            .columns(),
        color.basis_len()
    );
}

#[test]
fn arbitrary_directed_facade_retains_a_subbinary64_external_phase() {
    let bits = 137;
    let tree = qcd(["u", "d"], ["u", "d"], false);
    let color =
        TreeColorProgram::prepare(tree.clone(), vec![TreeColorInsertion::Identity]).unwrap();
    let p = momenta(Float::with_val(bits, 0), bits);
    let native = tree
        .evaluator_with_precision_bits(Arithmetic::Arbitrary, bits)
        .unwrap();
    let states = native.states();
    let helicities: Vec<_> = states.iter().map(|s| s.helicities[0]).collect();
    let components: Vec<_> = states
        .iter()
        .map(|state| {
            wavefunctions_batch(
                &p.take_columns(state.momentum_columns.to_vec()).unwrap(),
                vec![state.helicities[0]],
                vec![state.kind.clone()],
                Some(4),
            )
            .unwrap()
        })
        .collect();
    let mut evaluator = color
        .evaluator_with_precision_bits(Arithmetic::Arbitrary, bits)
        .unwrap();
    let norm = evaluator
        .evaluate_fixed_helicities(&p, &helicities)
        .unwrap();
    let Data::Arbitrary(norm) = norm.data() else {
        panic!("carrier changed")
    };
    let epsilon = Float::with_val(bits, 2).pow(80).inv();
    let mut bra = components.clone();
    let mut ket = components.clone();
    let phase = |batch: &Batch, z: Complex<Float>| {
        let Data::Arbitrary(v) = batch.data() else {
            panic!("carrier changed")
        };
        Batch::typed(
            v.iter().map(|v| v * &z).collect(),
            batch.ids().to_vec(),
            4,
            bits,
        )
        .unwrap()
    };
    bra[0] = phase(
        &bra[0],
        Complex::new(Float::with_val(bits, 0), Float::with_val(bits, 2)),
    );
    ket[0] = phase(
        &ket[0],
        Complex::new(
            Float::with_val(bits, 3),
            -(Float::with_val(bits, 4) + &epsilon),
        ),
    );
    let value = evaluator
        .evaluate_external_components(
            &p,
            &bra.iter().collect::<Vec<_>>(),
            &ket.iter().collect::<Vec<_>>(),
        )
        .unwrap();
    assert_eq!(
        (value.precision_bits(), value.columns(), value.ids()),
        (bits, 1, &[17][..])
    );
    let Data::Arbitrary(values) = value.data() else {
        panic!("carrier changed")
    };
    let expected_re =
        -(Float::with_val(bits, 8) + Float::with_val(bits, 2) * &epsilon) * &norm[0].re;
    let expected_im = -Float::with_val(bits, 6) * &norm[0].re;
    let tolerance = Float::with_val(bits, 2).pow(115).inv() * &norm[0].re;
    assert!((values[0].re.clone() - expected_re).norm() < tolerance);
    assert!((values[0].im.clone() - expected_im).norm() < tolerance);
    // Promoting binary64 components would erase this exact phase perturbation.
    assert!(
        (values[0].re.clone() + Float::with_val(bits, 8) * &norm[0].re).norm()
            > epsilon * &norm[0].re
    );
}

#[test]
fn facade_precision_empty_metadata_and_retryable_overflow() {
    let tree = qcd(["u", "d"], ["u", "d"], true);
    let program = TreeColorProgram::prepare(tree, vec![TreeColorInsertion::Identity]).unwrap();
    let mut double = program
        .evaluator_with_precision_bits(Arithmetic::Double, 53)
        .unwrap();
    let p = momenta(0_f64, 53);
    let params = |g| Batch::typed(vec![Complex::new(g, 0.)], vec![17], 1, 53).unwrap();
    let error = double
        .evaluate_batch_with_parameters(&p, &params(1e100))
        .err()
        .unwrap();
    assert_eq!(error.kind(), RusticolErrorKind::NonFiniteResult);
    assert_ne!(
        double
            .evaluate_batch_with_parameters(&p, &params(f64::INFINITY))
            .err()
            .unwrap()
            .kind(),
        RusticolErrorKind::NonFiniteResult
    );
    let wrong_ids = Batch::typed(vec![Complex::new(1., 0.)], vec![18], 1, 53).unwrap();
    assert!(
        double
            .evaluate_batch_with_parameters(&p, &wrong_ids)
            .is_err()
    );
    for bits in [113, 137, 256, 512, 1024] {
        let mut evaluator = program
            .evaluator_with_precision_bits(Arithmetic::Arbitrary, bits)
            .unwrap();
        let p = momenta(Float::with_val(bits, 0), bits);
        let parameters = Batch::typed(
            vec![Complex::new(
                Float::parse("1e100", Some(bits)).unwrap(),
                Float::with_val(bits, 0),
            )],
            vec![17],
            1,
            bits,
        )
        .unwrap();
        let value = evaluator
            .evaluate_batch_with_parameters(&p, &parameters)
            .unwrap();
        assert!(value.nonfinite_rows().is_empty());
        assert_eq!(value.precision_bits(), bits);
        let Data::Arbitrary(v) = value.data() else {
            panic!("carrier changed")
        };
        assert!(v[0].im.is_fully_zero());
        let empty = Batch::typed::<Float>(vec![], vec![], 16, bits).unwrap();
        let ep = Batch::typed::<Float>(vec![], vec![], 1, bits).unwrap();
        let result = evaluator
            .evaluate_batch_with_parameters(&empty, &ep)
            .unwrap();
        assert_eq!((result.rows(), result.columns()), (0, 1));
        assert!(evaluator.evaluate_batch(&empty).is_err());
        let wrong = Batch::typed::<Float>(vec![], vec![], 16, bits + 1).unwrap();
        assert!(
            evaluator
                .evaluate_batch_with_parameters(&wrong, &ep)
                .is_err()
        );
        let wrong = Batch::typed::<f64>(vec![], vec![], 16, bits).unwrap();
        assert!(
            evaluator
                .evaluate_batch_with_parameters(&wrong, &ep)
                .is_err()
        );
    }
    assert!(
        program
            .evaluator_with_precision_bits(Arithmetic::Double, 113)
            .is_err()
    );
}
