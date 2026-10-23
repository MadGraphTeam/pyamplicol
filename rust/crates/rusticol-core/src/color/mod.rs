// SPDX-License-Identifier: 0BSD

//! Exact, generation-independent ordered color connections.
//!
//! This is the native counterpart of `pyamplicol.color.connections`. Literal
//! generators obey `tr(tau[a] tau[b]) = delta[a,b]`; physical charges are
//! `t = tau / sqrt(2)`. All legs are outgoing. Each emission or splitting adds
//! one inverse square root of two, retained separately until the final overlap.
//! No kinematic factor or fermion endpoint-pairing phase is included. A model
//! adapter must attach its basis convention as an exact tensor coefficient.
//!
//! Overlaps are sesquilinear Gram entries, not operator action matrices. In
//! particular, do not multiply overlap matrices to construct higher connections:
//! apply the ordered connection to each tensor, then contract the resulting
//! tensors. No leading-color approximation or floating conversion is used.

use std::collections::{BTreeMap, BTreeSet};

use symbolica::domains::{float::Complex, rational::Rational};

use crate::{RusticolError, RusticolResult};

pub mod network;
#[cfg(test)]
mod tests;
mod trace;

pub const COLOR_CONNECTION_CONVENTION: &str = "su3-literal-tau-physical-charge-all-outgoing-v1";
pub type ExactColorCoefficient = Complex<Rational>;
/// Exact Laurent coefficients in the number of colors, including negative powers.
pub type ColorNcTerms = BTreeMap<i64, ExactColorCoefficient>;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd)]
pub enum ColorRepresentation {
    Singlet,
    Fundamental,
    Antifundamental,
    Adjoint,
}

impl ColorRepresentation {
    pub fn conjugate(self) -> Self {
        match self {
            Self::Fundamental => Self::Antifundamental,
            Self::Antifundamental => Self::Fundamental,
            other => other,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd)]
pub struct ColorLeg {
    pub label: i64,
    pub representation: ColorRepresentation,
}

impl ColorLeg {
    /// Cross an incoming physical representation without changing its momentum.
    pub fn all_outgoing(label: i64, representation: ColorRepresentation, incoming: bool) -> Self {
        Self {
            label,
            representation: if incoming {
                representation.conjugate()
            } else {
                representation
            },
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd)]
pub struct OpenColorString {
    pub fundamental: i64,
    pub adjoints: Vec<i64>,
    pub antifundamental: i64,
}

/// An unordered product of open strings and cyclic, but not reflected, traces.
#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd)]
pub struct ColorTensor {
    open_strings: Vec<OpenColorString>,
    traces: Vec<Vec<i64>>,
}

impl ColorTensor {
    pub fn new(mut open_strings: Vec<OpenColorString>, traces: Vec<Vec<i64>>) -> Self {
        open_strings.sort();
        Self {
            open_strings,
            traces: canonical_traces(traces),
        }
    }

    pub fn open_strings(&self) -> &[OpenColorString] {
        &self.open_strings
    }
    pub fn traces(&self) -> &[Vec<i64>] {
        &self.traces
    }

    fn replacing_string(&self, index: usize, replacements: Vec<OpenColorString>) -> Self {
        let mut strings = self.open_strings.clone();
        strings.splice(index..=index, replacements);
        Self::new(strings, self.traces.clone())
    }

    fn validate_legs(&self, legs: &[ColorLeg]) -> RusticolResult<()> {
        use ColorRepresentation::*;
        let mut indices = Vec::new();
        for string in &self.open_strings {
            indices.push(ColorLeg {
                label: string.fundamental,
                representation: Fundamental,
            });
            indices.push(ColorLeg {
                label: string.antifundamental,
                representation: Antifundamental,
            });
            indices.extend(string.adjoints.iter().map(|&label| ColorLeg {
                label,
                representation: Adjoint,
            }));
        }
        indices.extend(self.traces.iter().flatten().map(|&label| ColorLeg {
            label,
            representation: Adjoint,
        }));
        indices.sort();
        if indices
            != legs
                .iter()
                .copied()
                .filter(|leg| leg.representation != Singlet)
                .collect::<Vec<_>>()
        {
            return Err(invalid(
                "tensor indices must match typed external color legs exactly once",
            ));
        }
        Ok(())
    }
}

fn canonical_traces(mut traces: Vec<Vec<i64>>) -> Vec<Vec<i64>> {
    for trace in &mut traces {
        if !trace.is_empty() {
            let rotation = (0..trace.len())
                .min_by(|&a, &b| {
                    trace[a..]
                        .iter()
                        .chain(&trace[..a])
                        .cmp(trace[b..].iter().chain(&trace[..b]))
                })
                .unwrap();
            trace.rotate_left(rotation);
        }
    }
    traces.sort();
    traces
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ColorEmission {
    EmitGluon {
        emitter: i64,
        emitted: i64,
    },
    SplitGluon {
        parent: i64,
        quark: i64,
        antiquark: i64,
    },
}

/// Validated ordered connection; later operations may act on emitted legs.
#[derive(Clone, Debug)]
pub struct ColorConnection {
    initial_legs: Vec<ColorLeg>,
    emissions: Vec<ColorEmission>,
    output_legs: Vec<ColorLeg>,
    order: u32,
}

impl ColorConnection {
    pub fn new(initial_legs: Vec<ColorLeg>, emissions: Vec<ColorEmission>) -> RusticolResult<Self> {
        use ColorRepresentation::*;
        let initial_legs = canonical_legs(initial_legs)?;
        let order =
            u32::try_from(emissions.len()).map_err(|_| invalid("connection order overflows"))?;
        let mut active: BTreeMap<_, _> = initial_legs
            .iter()
            .map(|leg| (leg.label, leg.representation))
            .collect();
        let mut seen: BTreeSet<_> = active.keys().copied().collect();
        for &emission in &emissions {
            let additions = match emission {
                ColorEmission::EmitGluon { emitter, emitted } => {
                    if !matches!(
                        active.get(&emitter),
                        Some(Fundamental | Antifundamental | Adjoint)
                    ) {
                        return Err(invalid("gluon emitter must be an active colored leg"));
                    }
                    vec![(emitted, Adjoint)]
                }
                ColorEmission::SplitGluon {
                    parent,
                    quark,
                    antiquark,
                } => {
                    if active.get(&parent) != Some(&Adjoint) {
                        return Err(invalid(
                            "quark-pair splitting parent must be an active gluon",
                        ));
                    }
                    active.remove(&parent);
                    vec![(quark, Fundamental), (antiquark, Antifundamental)]
                }
            };
            for (label, representation) in additions {
                if !seen.insert(label) {
                    return Err(invalid(
                        "emitted color labels must be fresh, including retired labels",
                    ));
                }
                active.insert(label, representation);
            }
        }
        let output_legs = active
            .into_iter()
            .map(|(label, representation)| ColorLeg {
                label,
                representation,
            })
            .collect();
        Ok(Self {
            initial_legs,
            emissions,
            output_legs,
            order,
        })
    }

    pub fn initial_legs(&self) -> &[ColorLeg] {
        &self.initial_legs
    }
    pub fn output_legs(&self) -> &[ColorLeg] {
        &self.output_legs
    }
    pub fn emissions(&self) -> &[ColorEmission] {
        &self.emissions
    }
    pub fn order(&self) -> u32 {
        self.order
    }

    pub fn apply(
        &self,
        tensor: &ColorTensor,
        coefficient: ExactColorCoefficient,
    ) -> RusticolResult<ConnectedColorTensor> {
        tensor.validate_legs(&self.initial_legs)?;
        let mut terms = vec![TensorTerm {
            coefficient,
            tensor: tensor.clone(),
            nc_power: 0,
        }];
        for &emission in &self.emissions {
            let mut transformed = Vec::new();
            for term in terms {
                for (sign, power, tensor) in transform(&term.tensor, emission)? {
                    transformed.push(TensorTerm {
                        coefficient: scale(&term.coefficient, &Rational::from(sign)),
                        tensor,
                        nc_power: add_power(term.nc_power, power)?,
                    });
                }
            }
            terms = combine_terms(transformed)?;
        }
        ConnectedColorTensor::new(self.output_legs.clone(), terms, self.order)
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct TensorTerm {
    pub coefficient: ExactColorCoefficient,
    pub tensor: ColorTensor,
    pub nc_power: i64,
}

/// Exact linear combination with a common inverse-sqrt(2) normalization.
#[derive(Clone, Debug)]
pub struct ConnectedColorTensor {
    legs: Vec<ColorLeg>,
    terms: Vec<TensorTerm>,
    normalization_power: u32,
}

impl ConnectedColorTensor {
    pub fn new(
        legs: Vec<ColorLeg>,
        terms: Vec<TensorTerm>,
        normalization_power: u32,
    ) -> RusticolResult<Self> {
        let legs = canonical_legs(legs)?;
        for term in &terms {
            term.tensor.validate_legs(&legs)?;
        }
        Ok(Self {
            legs,
            terms: combine_terms(terms)?,
            normalization_power,
        })
    }

    pub fn legs(&self) -> &[ColorLeg] {
        &self.legs
    }
    pub fn terms(&self) -> &[TensorTerm] {
        &self.terms
    }
    pub fn normalization_power(&self) -> u32 {
        self.normalization_power
    }

    /// The exact Laurent coefficients of `self.conjugate() * right`.
    /// Odd combined inverse-sqrt(2) powers require irrational coefficients and
    /// are rejected, rather than rounded. Matching connection orders are even.
    pub fn overlap_nc_terms(&self, right: &Self) -> RusticolResult<ColorNcTerms> {
        if self.legs != right.legs {
            return Err(invalid(
                "bra and ket must have identical typed output color legs",
            ));
        }
        let power = u64::from(self.normalization_power) + u64::from(right.normalization_power);
        if power % 2 != 0 {
            return Err(invalid(
                "bra/ket normalization has an odd inverse sqrt(2) power",
            ));
        }
        let normalization = Rational::from((1, 2)).pow(power / 2);
        let mut result = ColorNcTerms::new();
        for left_term in &self.terms {
            for right_term in &right.terms {
                let coefficient = scale(
                    &bra_product(&left_term.coefficient, &right_term.coefficient),
                    &normalization,
                );
                for (nc_power, factor) in trace::contract(&left_term.tensor, &right_term.tensor)? {
                    let exponent = add_power(
                        add_power(nc_power, left_term.nc_power)?,
                        right_term.nc_power,
                    )?;
                    add_coefficient(&mut result, exponent, scale(&coefficient, &factor));
                }
            }
        }
        result.retain(|_, value| !is_zero(value));
        Ok(result)
    }

    /// Full SU(3) overlap, retaining directed complex phases and signed entries.
    pub fn overlap(&self, right: &Self) -> RusticolResult<ExactColorCoefficient> {
        evaluate_nc_terms(&self.overlap_nc_terms(right)?, 3)
    }
}

/// Evaluate a Laurent polynomial at an integer number of colors, exactly.
pub fn evaluate_nc_terms(terms: &ColorNcTerms, nc: u32) -> RusticolResult<ExactColorCoefficient> {
    if nc < 2 {
        return Err(invalid("the number of colors must be at least two"));
    }
    let mut result = zero();
    for (&power, coefficient) in terms {
        let factor = if power < 0 {
            Rational::from((1, i64::from(nc)))
        } else {
            Rational::from(i64::from(nc))
        }
        .pow(power.unsigned_abs());
        add_assign(&mut result, scale(coefficient, &factor));
    }
    Ok(result)
}

fn invalid(message: &str) -> RusticolError {
    RusticolError::invalid_argument(message)
}
fn add_power(a: i64, b: i64) -> RusticolResult<i64> {
    a.checked_add(b)
        .ok_or_else(|| invalid("color Laurent exponent overflows"))
}
fn zero() -> ExactColorCoefficient {
    Complex::new(Rational::from(0), Rational::from(0))
}
fn is_zero(value: &ExactColorCoefficient) -> bool {
    value.re == Rational::from(0) && value.im == Rational::from(0)
}
fn scale(value: &ExactColorCoefficient, factor: &Rational) -> ExactColorCoefficient {
    Complex::new(&value.re * factor, &value.im * factor)
}
fn add_assign(value: &mut ExactColorCoefficient, rhs: ExactColorCoefficient) {
    value.re += rhs.re;
    value.im += rhs.im;
}
fn add_coefficient<K: Ord>(
    terms: &mut BTreeMap<K, ExactColorCoefficient>,
    key: K,
    value: ExactColorCoefficient,
) {
    add_assign(terms.entry(key).or_insert_with(zero), value);
}
fn bra_product(
    left: &ExactColorCoefficient,
    right: &ExactColorCoefficient,
) -> ExactColorCoefficient {
    Complex::new(
        &left.re * &right.re + &left.im * &right.im,
        &left.re * &right.im - &left.im * &right.re,
    )
}
fn canonical_legs(mut legs: Vec<ColorLeg>) -> RusticolResult<Vec<ColorLeg>> {
    legs.sort();
    if legs.windows(2).any(|pair| pair[0].label == pair[1].label) {
        return Err(invalid("connection leg labels must be unique"));
    }
    Ok(legs)
}

fn combine_terms(terms: Vec<TensorTerm>) -> RusticolResult<Vec<TensorTerm>> {
    let mut combined = BTreeMap::new();
    for term in terms {
        if term.tensor.traces.iter().any(|trace| trace.len() == 1) {
            continue;
        }
        let empty_traces = i64::try_from(
            term.tensor
                .traces
                .iter()
                .filter(|trace| trace.is_empty())
                .count(),
        )
        .map_err(|_| invalid("color trace count overflows"))?;
        let power = add_power(term.nc_power, empty_traces)?;
        let tensor = ColorTensor::new(
            term.tensor.open_strings,
            term.tensor
                .traces
                .into_iter()
                .filter(|trace| !trace.is_empty())
                .collect(),
        );
        add_coefficient(&mut combined, (tensor, power), term.coefficient);
    }
    Ok(combined
        .into_iter()
        .filter(|(_, value)| !is_zero(value))
        .map(|((tensor, nc_power), coefficient)| TensorTerm {
            coefficient,
            tensor,
            nc_power,
        })
        .collect())
}

fn concat(parts: &[&[i64]]) -> Vec<i64> {
    parts.iter().flat_map(|part| part.iter().copied()).collect()
}
type TensorChanges = Vec<(i32, i64, ColorTensor)>;

fn transform(tensor: &ColorTensor, emission: ColorEmission) -> RusticolResult<TensorChanges> {
    match emission {
        ColorEmission::EmitGluon { emitter, emitted } => emit(tensor, emitter, emitted),
        ColorEmission::SplitGluon {
            parent,
            quark,
            antiquark,
        } => split(tensor, parent, quark, antiquark),
    }
}

fn emit(tensor: &ColorTensor, emitter: i64, emitted: i64) -> RusticolResult<TensorChanges> {
    for (index, string) in tensor.open_strings.iter().enumerate() {
        let (q, word, qbar) = (string.fundamental, &string.adjoints, string.antifundamental);
        let replace = |adjoints| {
            tensor.replacing_string(
                index,
                vec![OpenColorString {
                    fundamental: q,
                    adjoints,
                    antifundamental: qbar,
                }],
            )
        };
        if emitter == q {
            return Ok(vec![(1, 0, replace(concat(&[&[emitted], word])))]);
        }
        if emitter == qbar {
            return Ok(vec![(-1, 0, replace(concat(&[word, &[emitted]])))]);
        }
        if let Some(position) = word.iter().position(|&label| label == emitter) {
            return Ok(vec![
                (
                    1,
                    0,
                    replace(concat(&[
                        &word[..position],
                        &[emitter, emitted],
                        &word[position + 1..],
                    ])),
                ),
                (
                    -1,
                    0,
                    replace(concat(&[
                        &word[..position],
                        &[emitted, emitter],
                        &word[position + 1..],
                    ])),
                ),
            ]);
        }
    }
    for (index, trace) in tensor.traces.iter().enumerate() {
        if let Some(position) = trace.iter().position(|&label| label == emitter) {
            return Ok([(1, [emitter, emitted]), (-1, [emitted, emitter])]
                .into_iter()
                .map(|(sign, middle)| {
                    let mut traces = tensor.traces.clone();
                    traces[index] = concat(&[&trace[..position], &middle, &trace[position + 1..]]);
                    (
                        sign,
                        0,
                        ColorTensor::new(tensor.open_strings.clone(), traces),
                    )
                })
                .collect());
        }
    }
    Err(invalid("emitter has no tensor index"))
}

fn split(
    tensor: &ColorTensor,
    parent: i64,
    quark: i64,
    antiquark: i64,
) -> RusticolResult<TensorChanges> {
    for (index, string) in tensor.open_strings.iter().enumerate() {
        if let Some(position) = string.adjoints.iter().position(|&label| label == parent) {
            let (before, after) = (
                &string.adjoints[..position],
                &string.adjoints[position + 1..],
            );
            return Ok(vec![
                (
                    1,
                    0,
                    tensor.replacing_string(
                        index,
                        vec![
                            OpenColorString {
                                fundamental: string.fundamental,
                                adjoints: before.to_vec(),
                                antifundamental: antiquark,
                            },
                            OpenColorString {
                                fundamental: quark,
                                adjoints: after.to_vec(),
                                antifundamental: string.antifundamental,
                            },
                        ],
                    ),
                ),
                (
                    -1,
                    -1,
                    tensor.replacing_string(
                        index,
                        vec![
                            OpenColorString {
                                fundamental: string.fundamental,
                                adjoints: concat(&[before, after]),
                                antifundamental: string.antifundamental,
                            },
                            OpenColorString {
                                fundamental: quark,
                                adjoints: vec![],
                                antifundamental: antiquark,
                            },
                        ],
                    ),
                ),
            ]);
        }
    }
    for (index, trace) in tensor.traces.iter().enumerate() {
        if let Some(position) = trace.iter().position(|&label| label == parent) {
            let (before, after) = (&trace[..position], &trace[position + 1..]);
            let mut remaining = tensor.traces.clone();
            remaining.remove(index);
            let mut strings = tensor.open_strings.clone();
            strings.push(OpenColorString {
                fundamental: quark,
                adjoints: concat(&[after, before]),
                antifundamental: antiquark,
            });
            let direct = ColorTensor::new(strings, remaining.clone());
            let mut strings = tensor.open_strings.clone();
            strings.push(OpenColorString {
                fundamental: quark,
                adjoints: vec![],
                antifundamental: antiquark,
            });
            remaining.push(concat(&[before, after]));
            return Ok(vec![
                (1, 0, direct),
                (-1, -1, ColorTensor::new(strings, remaining)),
            ]);
        }
    }
    Err(invalid("splitting parent has no tensor index"))
}
