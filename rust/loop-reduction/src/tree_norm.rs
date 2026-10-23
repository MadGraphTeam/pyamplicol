// SPDX-License-Identifier: 0BSD

//! Exact Cartesian lowering of Hermitian color norms. Directed correlations
//! retain their complex coefficient programs and do not use this lowering.

use rusticol_core::{RusticolError, RusticolResult, color::ExactColorCoefficient};
use symbolica::{atom::Atom, symbol};

pub(crate) fn hermitian_norm(
    gram: &[Vec<ExactColorCoefficient>],
) -> RusticolResult<(Atom, Vec<Atom>)> {
    if gram.iter().any(|row| row.len() != gram.len()) {
        return Err(RusticolError::evaluation(
            "tree norm Gram matrix must be square",
        ));
    }
    for (i, row) in gram.iter().enumerate() {
        for (j, value) in row.iter().enumerate() {
            if *value != gram[j][i].conj() {
                return Err(RusticolError::evaluation(
                    "tree norm Gram matrix must be exactly Hermitian",
                ));
            }
        }
    }
    let inputs: Vec<_> = (0..gram.len())
        .flat_map(|index| {
            ["real", "imag"].map(move |part| {
                Atom::var(symbol!(&format!("rusticol_native_tree::amplitude_{part}_{index}"); Real))
            })
        })
        .collect();
    let mut norm = Atom::Zero;
    for i in 0..gram.len() {
        let (x, y) = (&inputs[2 * i], &inputs[2 * i + 1]);
        norm += Atom::num(gram[i][i].re.clone()) * (x * x + y * y);
        for j in i + 1..gram.len() {
            let (u, v) = (&inputs[2 * j], &inputs[2 * j + 1]);
            // 2 Re[(x-i y) (R+i I) (u+i v)]. The imaginary
            // Gram entry contributes +2 I (y u-x v), not its negative.
            norm += Atom::num(2)
                * (Atom::num(gram[i][j].re.clone()) * (x * u + y * v)
                    + Atom::num(gram[i][j].im.clone()) * (y * u - x * v));
        }
    }
    Ok((norm, inputs))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        Complex,
        runtime::{Arithmetic, Batch, Data},
        tree_runtime::TreeEvaluator,
    };
    use rusticol_core::preparation::encode_exact_evaluator_state;
    use symbolica::atom::AtomCore;
    use symbolica::domains::{
        float::{Float, FloatLike, Real, SingleFloat},
        rational::Rational,
    };

    fn gram() -> Vec<Vec<ExactColorCoefficient>> {
        vec![
            vec![
                Complex::new(2.into(), 0.into()),
                Complex::new(1.into(), 2.into()),
            ],
            vec![
                Complex::new(1.into(), (-2).into()),
                Complex::new(3.into(), 0.into()),
            ],
        ]
    }

    #[test]
    fn complex_hermitian_gram_uses_real_instructions_without_losing_phases() {
        let matrix = gram();
        let vector = [
            Complex::new(Rational::from((1, 3)), Rational::from((2, 7))),
            Complex::new(Rational::from((-5, 11)), Rational::from((3, 13))),
        ];
        // Independent exact directed double sum, without Cartesian lowering.
        let mut expected = Complex::new(Rational::from(0), Rational::from(0));
        for i in 0..2 {
            for j in 0..2 {
                expected += vector[i].conj() * &matrix[i][j] * &vector[j];
            }
        }
        assert_eq!(expected.im, Rational::from(0));
        let coefficients = vector
            .iter()
            .map(|z| Atom::num(z.re.clone()) + Atom::i() * Atom::num(z.im.clone()))
            .collect::<Vec<_>>();
        let exact = Atom::evaluator_multiple(&coefficients, &[] as &[Atom])
            .cores(1)
            .build()
            .unwrap();
        let (norm, inputs) = hermitian_norm(&matrix).unwrap();
        let norm = Atom::evaluator_multiple(&[norm], &inputs)
            .cores(1)
            .build()
            .unwrap();
        let exact = encode_exact_evaluator_state(&exact).unwrap();
        let norm = encode_exact_evaluator_state(&norm).unwrap();
        let mut evaluator =
            TreeEvaluator::new(&exact, &norm, vec![], 0, Arithmetic::Double, 53).unwrap();
        let p = Batch::typed::<f64>(vec![], vec![9], 0, 53).unwrap();
        let result = evaluator.evaluate_batch(&p).unwrap();
        let Data::Double(result) = result.data() else {
            panic!("carrier changed")
        };
        assert_eq!(result[0].im, 0.);
        assert!((result[0].re - expected.re.to_f64()).abs() < 1e-14);
        let directed = evaluator.evaluate_coefficients(&p, &[]).unwrap();
        let Data::Double(directed) = directed.data() else {
            panic!("carrier changed")
        };
        assert!(directed.iter().all(|z| z.im != 0.));
        for bits in [113, 173, 512] {
            let mut evaluator =
                TreeEvaluator::new(&exact, &norm, vec![], 0, Arithmetic::Arbitrary, bits).unwrap();
            let p = Batch::typed::<Float>(vec![], vec![9], 0, bits).unwrap();
            let output = evaluator.evaluate_batch(&p).unwrap();
            let Data::Arbitrary(values) = output.data() else {
                panic!("carrier changed")
            };
            let target = Float::with_val(bits, 0).from_rational(&expected.re);
            assert_eq!(values[0].im, Float::with_val(bits, 0));
            assert!(
                (values[0].re.clone() - target).norm()
                    < Float::with_val(bits, 2).pow(u64::from(bits - 12)).inv()
            );
        }
    }

    #[test]
    fn nonhermitian_gram_is_rejected_before_real_lowering() {
        let mut invalid = gram();
        invalid[1][0].im = 2.into();
        assert!(hermitian_norm(&invalid).is_err());
        let mut invalid = gram();
        invalid[0][0].im = 1.into();
        assert!(hermitian_norm(&invalid).is_err());
        assert!(hermitian_norm(&[vec![]]).is_err());
    }
}
