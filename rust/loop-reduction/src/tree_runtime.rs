// SPDX-License-Identifier: 0BSD

//! Native external states and coherent coefficients, with a streamed spin sum.

use std::collections::BTreeSet;

use feynkit_kinematics::{Helicity, WavefunctionKind};
use rusticol_core::{RusticolError, RusticolResult};

use crate::{
    Complex,
    runtime::{
        Arithmetic, Batch, BatchCarrier, Carrier, CoefficientEvaluator, Data, exact_state,
        wavefunctions_batch,
    },
};

/// One nonscalar external state in the prepared amplitude input order.
#[derive(Clone, Debug)]
pub struct ExternalTreeState {
    /// Columns containing its physical `(E, px, py, pz)` momentum.
    pub momentum_columns: [usize; 4],
    /// The existing native wavefunction kind, including its adjoint convention.
    pub kind: String,
    /// Distinct physical helicities to include in the unaveraged spin sum.
    pub helicities: Vec<i32>,
}

/// Reusable coherent amplitudes and their exact-color one-helicity norm.
///
/// Both programs use the shared coefficient evaluator. Amplitude inputs are
/// all momentum columns followed by four components per external state. Its
/// outputs are the color-basis coefficients; the norm program consumes those
/// outputs, including their complex phases, and returns one scalar column.
pub struct TreeEvaluator {
    amplitude: CoefficientEvaluator,
    norm: CoefficientEvaluator,
    states: Vec<ExternalTreeState>,
    momentum_columns: usize,
    coefficient_columns: usize,
    arithmetic: Arithmetic,
    bits: u32,
}

fn error(message: impl std::fmt::Display) -> RusticolError {
    RusticolError::evaluation(format!("native tree evaluation: {message}"))
}

fn finite(batch: &Batch) -> RusticolResult<()> {
    if let Some(id) = batch.nonfinite_rows().first() {
        return Err(error(format!("nonfinite value in row {id}")));
    }
    Ok(())
}

fn real_finite<T: Carrier>(values: &[Complex<T>]) -> bool {
    values
        .iter()
        .all(|value| value.im.is_fully_zero() && value.re.is_finite())
}

fn empty_like(batch: &Batch, columns: usize) -> RusticolResult<Batch> {
    match batch.data() {
        Data::Double(_) => Batch::typed::<f64>(vec![], vec![], columns, batch.precision_bits()),
        Data::DoubleDouble(_) => Batch::typed::<symbolica::domains::float::DoubleFloat>(
            vec![],
            vec![],
            columns,
            batch.precision_bits(),
        ),
        Data::Arbitrary(_) => Batch::typed::<symbolica::domains::float::Float>(
            vec![],
            vec![],
            columns,
            batch.precision_bits(),
        ),
    }
    .map_err(error)
}

fn add_values<T: BatchCarrier>(
    left: &[Complex<T>],
    right: &[Complex<T>],
    metadata: &Batch,
) -> RusticolResult<Batch> {
    let values = left
        .iter()
        .zip(right)
        .map(|(left, right)| {
            let mut value = left.clone();
            value += right;
            value
        })
        .collect();
    Batch::typed(
        values,
        metadata.ids().to_vec(),
        1,
        metadata.precision_bits(),
    )
    .map_err(error)
}

fn add_norms(left: &Batch, right: &Batch) -> RusticolResult<Batch> {
    left.same_rows(right).map_err(error)?;
    if left.columns() != 1 || right.columns() != 1 {
        return Err(error("helicity norms require one scalar column"));
    }
    let sum = match (left.data(), right.data()) {
        (Data::Double(a), Data::Double(b)) => add_values(a, b, left),
        (Data::DoubleDouble(a), Data::DoubleDouble(b)) => add_values(a, b, left),
        (Data::Arbitrary(a), Data::Arbitrary(b)) => add_values(a, b, left),
        _ => unreachable!("same_rows checked the arithmetic"),
    }?;
    finite(&sum)?;
    Ok(sum)
}

impl TreeEvaluator {
    pub fn new(
        coefficient_state: &[u8],
        norm_state: &[u8],
        states: Vec<ExternalTreeState>,
        momentum_columns: usize,
        arithmetic: Arithmetic,
        bits: u32,
    ) -> RusticolResult<Self> {
        for state in &states {
            if state
                .momentum_columns
                .iter()
                .any(|&column| column >= momentum_columns)
                || state
                    .momentum_columns
                    .iter()
                    .copied()
                    .collect::<BTreeSet<_>>()
                    .len()
                    != 4
            {
                return Err(error(
                    "external state requires four distinct valid momentum columns",
                ));
            }
            let kind: WavefunctionKind = state.kind.parse().map_err(error)?;
            if kind.component_count() != 4 {
                return Err(error(
                    "scalar external states do not need component metadata",
                ));
            }
            if state.helicities.is_empty()
                || state
                    .helicities
                    .iter()
                    .copied()
                    .collect::<BTreeSet<_>>()
                    .len()
                    != state.helicities.len()
            {
                return Err(error(
                    "external state requires nonempty distinct helicities",
                ));
            }
            for &helicity in &state.helicities {
                let helicity =
                    Helicity::try_from(i8::try_from(helicity).map_err(error)?).map_err(error)?;
                if kind.is_spinor() && helicity.is_zero() {
                    return Err(error("fermion external states require nonzero helicity"));
                }
            }
        }
        let inputs = states
            .len()
            .checked_mul(4)
            .and_then(|count| momentum_columns.checked_add(count))
            .ok_or_else(|| error("amplitude input dimensions overflow"))?;
        let coefficient = exact_state(coefficient_state).map_err(error)?;
        let norm = exact_state(norm_state).map_err(error)?;
        let coefficient_columns = coefficient.get_output_len();
        if coefficient.get_input_len() != inputs
            || coefficient_columns == 0
            || norm.get_input_len() != coefficient_columns
            || norm.get_output_len() != 1
        {
            return Err(error(
                "saved amplitude/norm dimensions differ from the declared inputs",
            ));
        }
        Ok(Self {
            amplitude: CoefficientEvaluator::with_precision_bits(
                coefficient_state,
                arithmetic,
                bits,
            )
            .map_err(error)?,
            norm: CoefficientEvaluator::with_precision_bits(norm_state, arithmetic, bits)
                .map_err(error)?,
            states,
            momentum_columns,
            coefficient_columns,
            arithmetic,
            bits,
        })
    }

    pub fn states(&self) -> &[ExternalTreeState] {
        &self.states
    }

    pub fn precision_bits(&self) -> u32 {
        self.amplitude.precision_bits()
    }

    pub fn coefficient_count(&self) -> usize {
        self.coefficient_columns
    }

    fn validate_momenta(&self, momenta: &Batch) -> RusticolResult<()> {
        if momenta.columns() != self.momentum_columns || momenta.precision_bits() != self.bits {
            return Err(error(
                "momentum shape or working precision differs from the prepared evaluator",
            ));
        }
        let valid = match (self.arithmetic, momenta.data()) {
            (Arithmetic::Double, Data::Double(values)) => real_finite(values),
            (Arithmetic::DoubleDouble, Data::DoubleDouble(values)) => real_finite(values),
            (Arithmetic::Arbitrary, Data::Arbitrary(values)) => real_finite(values),
            _ => {
                return Err(error(
                    "momentum arithmetic differs from the prepared evaluator",
                ));
            }
        };
        if !valid {
            return Err(error(
                "physical momentum components must be finite and real",
            ));
        }
        Ok(())
    }

    /// Evaluate coherent color coefficients for one declared helicity per state.
    ///
    /// Momentum components must be real and finite in the selected carrier.
    /// On-shell conditions and conservation remain the kinematics owner's
    /// responsibility; the existing wavefunction implementation supplies states.
    pub fn evaluate_coefficients(
        &mut self,
        momenta: &Batch,
        helicities: &[i32],
    ) -> RusticolResult<Batch> {
        self.validate_momenta(momenta)?;
        if helicities.len() != self.states.len()
            || self
                .states
                .iter()
                .zip(helicities)
                .any(|(state, helicity)| !state.helicities.contains(helicity))
        {
            return Err(error(
                "helicity assignment differs from the declared state domain",
            ));
        }
        if momenta.rows() == 0 {
            return empty_like(momenta, self.coefficient_columns);
        }
        let components = self
            .states
            .iter()
            .zip(helicities)
            .map(|(state, &helicity)| {
                let p = momenta
                    .take_columns(state.momentum_columns.to_vec())
                    .map_err(error)?;
                wavefunctions_batch(
                    &p,
                    vec![helicity; momenta.rows()],
                    vec![state.kind.clone(); momenta.rows()],
                    Some(4),
                )
                .map_err(error)
            })
            .collect::<RusticolResult<Vec<_>>>()?;
        self.evaluate_external_components(momenta, &components.iter().collect::<Vec<_>>())
    }

    /// Evaluate with caller-supplied complex external vectors or spinors.
    ///
    /// Each four-column block uses the declared state's convention and the
    /// momentum batch's row identities, arithmetic and working precision.
    /// Components are retained exactly as supplied, including Dirac adjoints;
    /// this interface also admits component-basis probes for open spin tensors.
    pub fn evaluate_external_components(
        &mut self,
        momenta: &Batch,
        components: &[&Batch],
    ) -> RusticolResult<Batch> {
        self.validate_momenta(momenta)?;
        if components.len() != self.states.len() {
            return Err(error(
                "external component block count differs from the declared states",
            ));
        }
        for state in components {
            momenta.same_rows(state).map_err(error)?;
            if state.columns() != 4 {
                return Err(error("external component blocks require four columns"));
            }
            finite(state)?;
        }
        if momenta.rows() == 0 {
            return empty_like(momenta, self.coefficient_columns);
        }
        let mut inputs = Vec::with_capacity(1 + components.len());
        inputs.push(momenta);
        inputs.extend_from_slice(components);
        let input = Batch::concat_columns(&inputs).map_err(error)?;
        let coefficients = self.amplitude.evaluate_batch(&input).map_err(error)?;
        finite(&coefficients)?;
        Ok(coefficients)
    }

    /// Sum the exact-color norm over the declared Cartesian helicity domain.
    /// No averaging, flux, or identical-particle factors are included.
    pub fn evaluate_batch(&mut self, momenta: &Batch) -> RusticolResult<Batch> {
        self.validate_momenta(momenta)?;
        if momenta.rows() == 0 {
            return empty_like(momenta, 1);
        }
        let mut positions = vec![0; self.states.len()];
        let mut accumulated = None;
        loop {
            let helicities = self
                .states
                .iter()
                .zip(&positions)
                .map(|(state, &position)| state.helicities[position])
                .collect::<Vec<_>>();
            let coefficients = self.evaluate_coefficients(momenta, &helicities)?;
            let norm = self.norm.evaluate_batch(&coefficients).map_err(error)?;
            finite(&norm)?;
            accumulated = Some(match accumulated {
                None => norm,
                Some(previous) => add_norms(&previous, &norm)?,
            });
            // The empty product has one assignment. Otherwise increment the
            // last state first, retaining only one assignment and norm at once.
            let mut position = positions.len();
            while position > 0 {
                position -= 1;
                positions[position] += 1;
                if positions[position] < self.states[position].helicities.len() {
                    break;
                }
                positions[position] = 0;
            }
            if position == 0 && positions.first().is_none_or(|&value| value == 0) {
                return Ok(accumulated.expect("one helicity assignment was evaluated"));
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rusticol_core::preparation::encode_exact_evaluator_state;
    use symbolica::{
        atom::{Atom, AtomCore},
        domains::float::{Float, FloatLike, Real},
        parse, symbol,
    };

    fn states() -> Vec<ExternalTreeState> {
        [0, 4]
            .map(|offset| ExternalTreeState {
                momentum_columns: std::array::from_fn(|mu| offset + mu),
                kind: "u".into(),
                helicities: vec![-1, 1],
            })
            .to_vec()
    }

    fn programs() -> (Vec<u8>, Vec<u8>) {
        let inputs: Vec<_> = (0..16)
            .map(|i| Atom::var(symbol!(&format!("native_tree_runtime_test::x{i}"))))
            .collect();
        // The upstream MadGraph fixture at p=(2,0,0,-2) gives U-=(2,0,0,0)
        // and U+=(0,0,0,-2). These four assignments have norms summing to 800.
        let coefficient = parse!("1+1/1208925819614629174706176")
            * (&inputs[8] + Atom::num(2) * &inputs[11])
            * (&inputs[12] + Atom::num(3) * &inputs[15]);
        let exact = Atom::evaluator_multiple(&[coefficient], &inputs)
            .cores(1)
            .build()
            .unwrap();
        let a = Atom::var(symbol!("native_tree_runtime_test::a"));
        let norm = Atom::evaluator_multiple(&[a.clone().conj() * &a], &[a])
            .cores(1)
            .build()
            .unwrap();
        (
            encode_exact_evaluator_state(&exact).unwrap(),
            encode_exact_evaluator_state(&norm).unwrap(),
        )
    }

    fn momenta<T: BatchCarrier>(bits: u32) -> Batch {
        let values = [2, 0, 0, -2, 2, 0, 0, -2]
            .into_iter()
            .map(|value| {
                Complex::new(
                    T::parse_decimal(&value.to_string(), bits).unwrap(),
                    T::parse_decimal("0", bits).unwrap(),
                )
            })
            .collect();
        Batch::typed(values, vec![17], 8, bits).unwrap()
    }

    #[test]
    fn streamed_cartesian_spin_sum_preserves_native_precision() {
        let (coefficient, norm) = programs();
        let mut double =
            TreeEvaluator::new(&coefficient, &norm, states(), 8, Arithmetic::Double, 53).unwrap();
        let output = double.evaluate_batch(&momenta::<f64>(53)).unwrap();
        let Data::Double(values) = output.data() else {
            panic!("wrong carrier")
        };
        assert_eq!(values[0], Complex::new(800.0, 0.0));
        assert_eq!(output.ids(), &[17]);

        let bits = 137;
        let mut high = TreeEvaluator::new(
            &coefficient,
            &norm,
            states(),
            8,
            Arithmetic::Arbitrary,
            bits,
        )
        .unwrap();
        let output = high.evaluate_batch(&momenta::<Float>(bits)).unwrap();
        let Data::Arbitrary(values) = output.data() else {
            panic!("wrong carrier")
        };
        let one = Float::with_val(bits, 1);
        let two = Float::with_val(bits, 2);
        let coupling = one + two.pow(80).inv();
        let base = Float::with_val(bits, 800);
        let expected = base.clone() * &coupling * &coupling;
        assert!(values[0].re > base);
        assert!((values[0].re.clone() - expected).norm() < two.pow(115).inv());
        assert!(values[0].im.norm() < two.pow(115).inv());
        assert!(values[0].re.get_precision() > 100);
        assert!(values[0].im.get_precision() > 100);
        assert_eq!(output.precision_bits(), bits);
    }

    #[test]
    fn supplied_complex_states_preserve_coefficients_and_empty_metadata_checks() {
        let (coefficient, norm) = programs();
        let mut evaluator =
            TreeEvaluator::new(&coefficient, &norm, states(), 8, Arithmetic::Double, 53).unwrap();
        let p = momenta::<f64>(53);
        let component = |value| {
            Batch::typed(
                vec![
                    value,
                    Complex::new(0., 0.),
                    Complex::new(0., 0.),
                    Complex::new(0., 0.),
                ],
                vec![17],
                4,
                53,
            )
            .unwrap()
        };
        let first = component(Complex::new(2., 1.));
        let second = component(Complex::new(3., -2.));
        let output = evaluator
            .evaluate_external_components(&p, &[&first, &second])
            .unwrap();
        let Data::Double(values) = output.data() else {
            panic!("wrong carrier")
        };
        assert_eq!(values[0], Complex::new(8., -1.));

        let empty = Batch::typed::<f64>(vec![], vec![], 8, 53).unwrap();
        assert_eq!(evaluator.evaluate_batch(&empty).unwrap().columns(), 1);
        assert!(evaluator.evaluate_coefficients(&empty, &[0, 1]).is_err());
        let wrong_carrier = Batch::typed::<Float>(vec![], vec![], 8, 53).unwrap();
        assert!(evaluator.evaluate_batch(&wrong_carrier).is_err());
        let wrong_shape = Batch::typed::<f64>(vec![], vec![], 7, 53).unwrap();
        assert!(evaluator.evaluate_batch(&wrong_shape).is_err());
        let wrong_bits = Batch::typed::<f64>(vec![], vec![], 8, 106).unwrap();
        assert!(evaluator.evaluate_batch(&wrong_bits).is_err());
        assert!(evaluator.evaluate_external_components(&empty, &[]).is_err());
    }

    #[test]
    fn state_metadata_and_nonphysical_momentum_components_fail() {
        let (coefficient, norm) = programs();
        let mut invalid = states();
        invalid[0].helicities = vec![-1, -1];
        assert!(
            TreeEvaluator::new(&coefficient, &norm, invalid, 8, Arithmetic::Double, 53).is_err()
        );
        let mut invalid = states();
        invalid[0].kind = "unknown".into();
        assert!(
            TreeEvaluator::new(&coefficient, &norm, invalid, 8, Arithmetic::Double, 53).is_err()
        );
        let mut evaluator =
            TreeEvaluator::new(&coefficient, &norm, states(), 8, Arithmetic::Double, 53).unwrap();
        for component in [Complex::new(1., 1.), Complex::new(f64::INFINITY, 0.)] {
            let input = Batch::typed(vec![component; 8], vec![17], 8, 53).unwrap();
            assert!(evaluator.evaluate_batch(&input).is_err());
        }
    }

    #[test]
    fn scalar_state_product_evaluates_once_with_zero_momentum_inputs() {
        let p: Vec<_> = (0..4)
            .map(|i| Atom::var(symbol!(&format!("native_tree_runtime_test::scalar_p{i}"))))
            .collect();
        let amplitude = Atom::evaluator_multiple(&[Atom::num(2) + Atom::i()], &p)
            .cores(1)
            .build()
            .unwrap();
        let a = Atom::var(symbol!("native_tree_runtime_test::scalar_a"));
        let norm = Atom::evaluator_multiple(&[a.clone().conj() * &a], &[a])
            .cores(1)
            .build()
            .unwrap();
        let mut evaluator = TreeEvaluator::new(
            &encode_exact_evaluator_state(&amplitude).unwrap(),
            &encode_exact_evaluator_state(&norm).unwrap(),
            vec![],
            4,
            Arithmetic::Double,
            53,
        )
        .unwrap();
        let input = Batch::typed(vec![Complex::new(0., 0.); 4], vec![31], 4, 53).unwrap();
        let output = evaluator.evaluate_batch(&input).unwrap();
        let Data::Double(values) = output.data() else {
            panic!("wrong carrier")
        };
        assert_eq!(values.as_slice(), &[Complex::new(5., 0.)]);
        assert_eq!(output.ids(), &[31]);
    }
}
