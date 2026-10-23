// SPDX-License-Identifier: 0BSD

//! Native blocks of existing precision-generic FeynKit external states.

use super::*;
use feynkit_kinematics::{
    FourMomentum as PhysicalMomentum, Helicity, KinematicScalar, ThreeMomentum, WavefunctionError,
    WavefunctionKind,
};

fn specifications(
    rows: usize,
    helicities: &[i32],
    kinds: &[String],
    components: Option<usize>,
) -> ExecutionResult<(Vec<(Helicity, WavefunctionKind)>, usize)> {
    if helicities.len() != rows || kinds.len() != rows {
        return Err(error("external state row metadata dimensions differ"));
    }
    let specifications = helicities
        .iter()
        .zip(kinds)
        .map(|(&helicity, kind)| {
            Ok((
                Helicity::try_from(i8::try_from(helicity).map_err(error)?).map_err(error)?,
                kind.parse::<WavefunctionKind>().map_err(error)?,
            ))
        })
        .collect::<ExecutionResult<Vec<_>>>()?;
    let columns = components.unwrap_or_else(|| {
        specifications
            .first()
            .map_or(4, |(_, kind)| kind.component_count())
    });
    if !matches!(columns, 1 | 4)
        || specifications
            .iter()
            .any(|(_, kind)| kind.component_count() != columns)
    {
        return Err(error(
            "external state batch must have a common component count of one or four",
        ));
    }
    Ok((specifications, columns))
}

fn real_finite<T: Carrier>(value: &Complex<T>) -> bool {
    value.im.is_fully_zero() && value.re.is_finite()
}

fn state_components<T: BatchCarrier + KinematicScalar>(
    p: &[Complex<T>],
    helicity: Helicity,
    kind: WavefunctionKind,
    working_bits: u32,
) -> ExecutionResult<Vec<Complex<T>>> {
    if !p.iter().all(real_finite) {
        return Err(error("momenta must be finite and real"));
    }
    PhysicalMomentum::from(std::array::from_fn::<_, 4, _>(|i| p[i].re.clone()))
        .wavefunction(kind, helicity)
        .map(|wavefunction| wavefunction.into_components())
        .map_err(|failure| match failure {
            WavefunctionError::NonFinite => ExecutionError::nonfinite_result(failure),
            WavefunctionError::InsufficientPrecision { reason, .. } => {
                // Input components may have lower tracked precision after prior
                // arithmetic. Preserve the batch's original working precision.
                ExecutionError::insufficient_precision(
                    working_bits,
                    format!(
                        "external-state chart needs more than {working_bits} working bits: {reason}"
                    ),
                )
            }
            _ => error(failure),
        })
}

fn evaluate<T: BatchCarrier + KinematicScalar>(
    values: &[Complex<T>],
    input: &Batch,
    specifications: &[(Helicity, WavefunctionKind)],
    columns: usize,
) -> ExecutionResult<Batch> {
    let mut output = Vec::with_capacity(input.rows() * columns);
    for (row, (p, &(helicity, kind))) in values.chunks_exact(4).zip(specifications).enumerate() {
        let lane_error = |failure: ExecutionError| {
            let message = format!(
                "external state lane {} (row {row}): {failure}",
                input.ids()[row]
            );
            failure.context(message)
        };
        output.extend(
            state_components(p, helicity, kind, input.precision_bits()).map_err(lane_error)?,
        );
    }
    Batch::typed(
        output,
        input.ids().to_vec(),
        columns,
        input.precision_bits(),
    )
}

/// Sparse successful rows and legacy textual status for every input row.
///
/// Precision failures retain their lane identity and diagnostic text here, but
/// not their typed category or working-bit metadata. Call the strict batch API
/// when a caller needs machine-readable precision retry decisions.
pub type PartialStates = (Batch, Vec<(u64, String)>);

fn evaluate_partial<T: BatchCarrier + KinematicScalar>(
    values: &[Complex<T>],
    input: &Batch,
    specifications: &[(Helicity, WavefunctionKind)],
    columns: usize,
) -> ExecutionResult<PartialStates> {
    let mut output = Vec::with_capacity(input.rows() * columns);
    let mut ids = Vec::with_capacity(input.rows());
    let mut statuses = Vec::with_capacity(input.rows());
    for (p, (&id, &(helicity, kind))) in values
        .chunks_exact(4)
        .zip(input.ids().iter().zip(specifications))
    {
        match state_components(p, helicity, kind, input.precision_bits()) {
            Ok(components) => {
                output.extend(components);
                ids.push(id);
                statuses.push((id, "success".into()));
            }
            Err(failure) => statuses.push((id, failure.to_string())),
        }
    }
    Ok((
        Batch::typed(output, ids, columns, input.precision_bits())?,
        statuses,
    ))
}

fn on_shell<T: BatchCarrier + KinematicScalar>(
    spatial: &[Complex<T>],
    masses: &[Complex<T>],
    input: &Batch,
    specifications: &[(Helicity, WavefunctionKind)],
    columns: usize,
) -> ExecutionResult<(Batch, Batch)> {
    let mut momenta = Vec::with_capacity(input.rows() * 4);
    for (row, (p, mass)) in spatial.chunks_exact(3).zip(masses).enumerate() {
        if !p.iter().all(real_finite) || !real_finite(mass) || mass.re < mass.re.zero() {
            return Err(error(format!(
                "on-shell construction lane {} (row {row}) requires finite real spatial momentum and nonnegative real mass",
                input.ids()[row]
            )));
        }
        let momentum = ThreeMomentum::from(std::array::from_fn::<_, 3, _>(|i| p[i].re.clone()))
            .on_shell(Some(&mass.re));
        if (&momentum).into_iter().any(|value| !value.is_finite()) {
            return Err(ExecutionError::nonfinite_result(format!(
                "on-shell construction produced nonfinite momentum in row {}",
                input.ids()[row]
            )));
        }
        momenta.extend(
            momentum
                .into_iter()
                .map(|value| Complex::new(value.clone(), value.zero())),
        );
    }
    let states = evaluate(&momenta, input, specifications, columns)?;
    Ok((
        Batch::typed(momenta, input.ids().to_vec(), 4, input.precision_bits())?,
        states,
    ))
}

pub fn wavefunctions_batch(
    momenta: &Batch,
    helicities: Vec<i32>,
    kinds: Vec<String>,
    components: Option<usize>,
) -> ExecutionResult<Batch> {
    if momenta.columns() != 4 {
        return Err(error("external states require four momentum columns"));
    }
    let (specifications, columns) =
        specifications(momenta.rows(), &helicities, &kinds, components)?;
    match momenta.data() {
        Data::Double(v) => evaluate(v, momenta, &specifications, columns),
        Data::DoubleDouble(v) => evaluate(v, momenta, &specifications, columns),
        Data::Arbitrary(v) => evaluate(v, momenta, &specifications, columns),
    }
}

/// Numerical failures remain sparse native rows; malformed metadata still raises.
pub fn wavefunctions_partial_batch(
    momenta: &Batch,
    helicities: Vec<i32>,
    kinds: Vec<String>,
    components: Option<usize>,
) -> ExecutionResult<PartialStates> {
    if momenta.columns() != 4 {
        return Err(error("external states require four momentum columns"));
    }
    let (specifications, columns) =
        specifications(momenta.rows(), &helicities, &kinds, components)?;
    if specifications.iter().any(|(helicity, kind)| {
        (kind.is_spinor() && helicity.is_zero())
            || (*kind == WavefunctionKind::Scalar && !helicity.is_zero())
    }) {
        return Err(error(
            "external state kind does not admit the requested helicity",
        ));
    }
    match momenta.data() {
        Data::Double(v) => evaluate_partial(v, momenta, &specifications, columns),
        Data::DoubleDouble(v) => evaluate_partial(v, momenta, &specifications, columns),
        Data::Arbitrary(v) => evaluate_partial(v, momenta, &specifications, columns),
    }
}

pub fn on_shell_wavefunctions_batch(
    spatial_momenta: &Batch,
    masses: &Batch,
    helicities: Vec<i32>,
    kinds: Vec<String>,
    components: Option<usize>,
) -> ExecutionResult<(Batch, Batch)> {
    spatial_momenta.same_rows(masses)?;
    if spatial_momenta.columns() != 3 || masses.columns() != 1 {
        return Err(error(
            "on-shell construction requires three spatial columns and one mass column",
        ));
    }
    let (specifications, columns) =
        specifications(spatial_momenta.rows(), &helicities, &kinds, components)?;
    match (spatial_momenta.data(), masses.data()) {
        (Data::Double(p), Data::Double(m)) => {
            on_shell(p, m, spatial_momenta, &specifications, columns)
        }
        (Data::DoubleDouble(p), Data::DoubleDouble(m)) => {
            on_shell(p, m, spatial_momenta, &specifications, columns)
        }
        (Data::Arbitrary(p), Data::Arbitrary(m)) => {
            on_shell(p, m, spatial_momenta, &specifications, columns)
        }
        _ => unreachable!("same_rows checked carriers"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rusticol_core::{RusticolError, RusticolErrorKind};
    use symbolica::domains::float::{FloatLike, SingleFloat};

    fn momentum<T: BatchCarrier>(prototype: &T, mixed_scales: bool) -> Vec<Complex<T>> {
        let values = if mixed_scales {
            let large = prototype.from_usize(2).pow(600);
            [large.clone(), large.inv(), prototype.zero(), large]
        } else {
            let delta = prototype.from_usize(2).pow(30).inv();
            let square = delta.clone() * delta.clone();
            [
                prototype.one() + square.clone(),
                prototype.from_usize(2) * delta,
                prototype.zero(),
                -prototype.one() + square,
            ]
        };
        values
            .into_iter()
            .map(|value| Complex::new(value, prototype.zero()))
            .collect()
    }

    #[test]
    fn wavefunction_chart_errors_preserve_lane_identity_and_allow_fresh_reconstruction() {
        for mixed_scales in [false, true] {
            let mut low = [2., 0., 0., 2.]
                .map(|value| Complex::new(value, 0.))
                .to_vec();
            low.extend(momentum(&0.0_f64, mixed_scales));
            let input = Batch::typed(low, vec![31, 907], 4, 53).unwrap();
            let error = wavefunctions_batch(&input, vec![1, 1], vec!["u".into(); 2], Some(4))
                .err()
                .unwrap();
            assert_eq!(
                error.kind(),
                RusticolErrorKind::InsufficientPrecision { bits: 53 }
            );
            assert!(error.to_string().contains("lane 907 (row 1)"));
            let core: RusticolError = error.into();
            assert_eq!(
                core.kind(),
                RusticolErrorKind::InsufficientPrecision { bits: 53 }
            );

            // Recreate both rows from exact integer/power-of-two source inputs.
            // The wider request never promotes the rounded binary64 momentum.
            let bits = 137;
            let prototype = Float::with_val(bits, 0);
            let mut high = [2, 0, 0, 2]
                .map(|value| Complex::new(prototype.from_i64(value), prototype.zero()))
                .to_vec();
            high.extend(momentum(&prototype, mixed_scales));
            let input = Batch::typed(high, vec![31, 907], 4, bits).unwrap();
            let output =
                wavefunctions_batch(&input, vec![1, 1], vec!["u".into(); 2], Some(4)).unwrap();
            assert_eq!(output.ids(), &[31, 907]);
            assert_eq!(output.precision_bits(), bits);
            assert!(output.nonfinite_rows().is_empty());
            let Data::Arbitrary(values) = output.data() else {
                panic!("wrong carrier")
            };
            assert!(!values[6].re.is_zero());
            assert!(!values[7].re.is_zero());
            if mixed_scales {
                let vectors =
                    wavefunctions_batch(&input, vec![1, 1], vec!["epsilon".into(); 2], Some(4))
                        .unwrap();
                let Data::Arbitrary(values) = vectors.data() else {
                    panic!("wrong carrier")
                };
                assert!(!values[7].re.is_zero());
            }
        }
    }

    #[test]
    fn wavefunction_precision_category_uses_working_bits_not_component_bits() {
        let tracked = Float::with_val(53, 0);
        let values = momentum(&tracked, false);
        let physical =
            PhysicalMomentum::from(std::array::from_fn::<_, 4, _>(|i| values[i].re.clone()));
        assert!(matches!(
            physical.wavefunction(WavefunctionKind::U, Helicity::PLUS),
            Err(WavefunctionError::InsufficientPrecision { bits, .. }) if bits < 137
        ));
        // The original attempt used 137 working bits; its stored intermediate
        // components now have only 53 tracked bits. No precision is padded here.
        let input = Batch::typed(values, vec![1021], 4, 137).unwrap();
        let failure = wavefunctions_batch(&input, vec![1], vec!["u".into()], Some(4))
            .err()
            .unwrap();
        assert_eq!(
            failure.kind(),
            RusticolErrorKind::InsufficientPrecision { bits: 137 }
        );
        assert!(failure.to_string().contains("lane 1021 (row 0)"));
    }

    #[test]
    fn partial_chart_failure_keeps_successful_rows_without_a_zero_placeholder() {
        let mut values = [2., 0., 0., 2.]
            .map(|value| Complex::new(value, 0.))
            .to_vec();
        values.extend(momentum(&0.0_f64, false));
        let input = Batch::typed(values, vec![31, 907], 4, 53).unwrap();
        let (successful, statuses) =
            wavefunctions_partial_batch(&input, vec![1, 1], vec!["u".into(); 2], Some(4)).unwrap();
        assert_eq!(successful.ids(), &[31]);
        assert_eq!(successful.rows(), 1);
        assert_eq!(statuses[0], (31, "success".into()));
        assert_eq!(statuses[1].0, 907);
        assert!(statuses[1].1.contains("53 working bits"));
        assert_ne!(statuses[1].1, "success");
    }

    #[test]
    fn chart_precision_does_not_reclassify_nonfinite_results_or_bad_inputs() {
        let make = |values: [f64; 4]| {
            Batch::typed(
                values.map(|value| Complex::new(value, 0.)).to_vec(),
                vec![89],
                4,
                53,
            )
            .unwrap()
        };
        let overflow = make([1e308, 0., 0., 1e308]);
        let failure = wavefunctions_batch(&overflow, vec![1], vec!["u".into()], Some(4))
            .err()
            .unwrap();
        assert_eq!(failure.kind(), RusticolErrorKind::NonFiniteResult);

        let malformed = make([f64::INFINITY, 0., 0., 1.]);
        let failure = wavefunctions_batch(&malformed, vec![1], vec!["u".into()], Some(4))
            .err()
            .unwrap();
        assert_eq!(failure.kind(), RusticolErrorKind::Evaluation);
        let ordinary = make([2., 0., 0., 2.]);
        for (helicities, kinds) in [
            (vec![], vec!["u".into()]),
            (vec![0], vec!["u".into()]),
            (vec![1], vec!["unknown".into()]),
        ] {
            let failure = wavefunctions_batch(&ordinary, helicities, kinds, Some(4))
                .err()
                .unwrap();
            assert_eq!(failure.kind(), RusticolErrorKind::Evaluation);
        }
    }
}
