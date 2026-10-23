// SPDX-License-Identifier: 0BSD

//! Shared execution primitives independent of Python. The binding delegates to
//! these same operations for native coordination and standalone callers.

use crate::{Complex, NativeFloat};
use std::fmt::{Display, LowerExp};
use symbolica::domains::float::{DoubleFloat, Float};
mod batch;
mod coefficients;
mod dual_weights;
mod exact;
mod fast;
mod master_cache;
pub mod physical;
mod predicates;
mod reduction;
mod schedule;
mod stability;
mod states;
mod v2_execution;
mod v2_reduce;
mod v2_seeds;
pub use batch::{Batch, BatchCarrier, Data, shape};
pub use coefficients::{CoefficientEvaluator, exact_state};
pub use dual_weights::DualBornWeights;
pub use exact::{ExactPolynomialEvaluator, decimal_rational};
pub use master_cache::{MasterCache, MasterStatistics};
pub use ninjars::fast::tensor_layout::monomials as tensor_monomials;
pub use reduction::{DecimalMomentum, PolynomialPlan, RawLane, ReductionBatch};
pub use schedule::{CoefficientKernelCache, CoefficientPlan};
pub use states::{
    PartialStates, on_shell_wavefunctions_batch, wavefunctions_batch, wavefunctions_partial_batch,
};
pub use v2_execution::{TypedBatch, V2ReductionBackend};
pub use v2_reduce::{
    FamilyGroup, ReduceOptions, ReductionFrame, V2Output, V2Reducer, shift_coefficients,
    tensor_rank, true_rank,
};
pub use v2_seeds::V2SeedFourier;

/// Install immutable source-scalar callbacks before decoding saved programs.
pub fn register_scalar_primitives() {
    predicates::register();
}
pub type DecimalComplex = [String; 2];
pub type ExecutionResult<T> = Result<T, ExecutionError>;
#[derive(Debug, Clone)]
pub struct ExecutionError(rusticol_core::RusticolError);
impl ExecutionError {
    /// Preserve actionable numerical categories across runtime consumers.
    pub fn kind(&self) -> rusticol_core::RusticolErrorKind {
        self.0.kind()
    }
    fn nonfinite_result(value: impl Display) -> Self {
        Self(rusticol_core::RusticolError::nonfinite_result(
            value.to_string(),
        ))
    }
    fn insufficient_precision(bits: u32, value: impl Display) -> Self {
        Self(rusticol_core::RusticolError::insufficient_precision(
            bits,
            value.to_string(),
        ))
    }
    fn context(self, value: impl Display) -> Self {
        Self(rusticol_core::RusticolError::with_kind(
            self.kind(),
            value.to_string(),
        ))
    }
}
impl From<ExecutionError> for rusticol_core::RusticolError {
    fn from(error: ExecutionError) -> Self {
        error.0
    }
}
impl Display for ExecutionError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        Display::fmt(&self.0, f)
    }
}
impl std::error::Error for ExecutionError {}
fn error(value: impl Display) -> ExecutionError {
    ExecutionError(rusticol_core::RusticolError::evaluation(value.to_string()))
}

pub trait Carrier: NativeFloat + LowerExp + From<f64> {
    fn parse_decimal(value: &str, bits: u32) -> Result<Self, String>;
}

impl Carrier for f64 {
    fn parse_decimal(value: &str, _: u32) -> Result<Self, String> {
        value.parse::<f64>().map_err(|e| e.to_string())
    }
}

impl Carrier for DoubleFloat {
    fn parse_decimal(value: &str, _: u32) -> Result<Self, String> {
        Float::parse(value, Some(106)).map(|f| f.to_double_float())
    }
}

impl Carrier for Float {
    fn parse_decimal(value: &str, bits: u32) -> Result<Self, String> {
        Float::parse(value, Some(bits))
    }
}

pub fn parse_complex<T: Carrier>(value: &DecimalComplex, bits: u32) -> ExecutionResult<Complex<T>> {
    Ok(Complex::new(
        T::parse_decimal(&value[0], bits).map_err(error)?,
        T::parse_decimal(&value[1], bits).map_err(error)?,
    ))
}

pub fn decimal_complex<T: Carrier>(value: Complex<T>, bits: u32) -> DecimalComplex {
    // Default Symbolica Display intentionally drops some bits. Explicit output
    // digits allow each carrier to round-trip through the native external boundary.
    let digits = (f64::from(bits) * std::f64::consts::LOG10_2).ceil() as usize + 2;
    [
        format!("{:.digits$e}", value.re),
        format!("{:.digits$e}", value.im),
    ]
}

#[derive(Clone, Copy)]
pub enum Arithmetic {
    Double,
    DoubleDouble,
    Arbitrary,
}

pub fn arithmetic_mode(
    arithmetic: &str,
    precision: Option<u32>,
) -> ExecutionResult<(Arithmetic, u32)> {
    match (arithmetic, precision) {
        ("double", None) => Ok((Arithmetic::Double, 53)),
        ("double-double", None) => Ok((Arithmetic::DoubleDouble, 106)),
        ("arbitrary", Some(digits)) if digits > 0 => Ok((
            Arithmetic::Arbitrary,
            Float::decimal_digits_to_bits(f64::from(digits)).map_err(error)?,
        )),
        ("arbitrary", _) => Err(error(
            "arbitrary arithmetic requires a positive decimal precision",
        )),
        ("double" | "double-double", Some(_)) => {
            Err(error("precision applies only to arbitrary arithmetic"))
        }
        _ => Err(error(
            "arithmetic must be double, double-double, or arbitrary",
        )),
    }
}
