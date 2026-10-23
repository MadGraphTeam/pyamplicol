// SPDX-License-Identifier: 0BSD

//! Native vertex color networks and exact contraction of internal indices.
//!
//! This ports the generic network reduction of `loops/v2/colour.py` without
//! its optional color compression. A network is a sum of products of matrices
//! with upper row and lower column slots, as in Spenso. The output uses the
//! literal all-outgoing tensors of the parent module; the reversed word and
//! endpoint orientation is deliberate. Internal fundamental lines are joined,
//! then internal adjoint pairs use the same exact Fierz identity as overlaps.
//! No decomposition into a Born basis or inverse Gram matrix is involved.

use super::*;

mod spenso;
pub use spenso::spenso_color_network;
#[cfg(test)]
mod tests;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ColorString<L> {
    /// Upper fundamental slot (Spenso `cof`); an external antiquark endpoint.
    pub row: L,
    pub word: Vec<L>,
    /// Lower fundamental slot (Spenso `dind(cof)`); an external quark endpoint.
    pub col: L,
}

#[derive(Clone, Debug, PartialEq)]
pub struct ColorProduct<L> {
    pub coefficient: ExactColorCoefficient,
    pub strings: Vec<ColorString<L>>,
    pub traces: Vec<Vec<L>>,
    pub nc_power: i64,
    /// Power of 1/sqrt(2). Negative values allow exact normalization transfers.
    pub root2_power: i64,
}

pub type ColorNetwork<L> = Vec<ColorProduct<L>>;

impl<L> Default for ColorProduct<L> {
    fn default() -> Self {
        Self {
            coefficient: Complex::new(Rational::from(1), Rational::from(0)),
            strings: vec![],
            traces: vec![],
            nc_power: 0,
            root2_power: 0,
        }
    }
}

impl<L: Clone> ColorProduct<L> {
    pub fn multiply(&self, right: &Self) -> RusticolResult<Self> {
        Ok(Self {
            coefficient: product(&self.coefficient, &right.coefficient),
            strings: self.strings.iter().chain(&right.strings).cloned().collect(),
            traces: self.traces.iter().chain(&right.traces).cloned().collect(),
            nc_power: add_power(self.nc_power, right.nc_power)?,
            root2_power: add_power(self.root2_power, right.root2_power)?,
        })
    }

    pub fn relabel<M>(&self, mut rename: impl FnMut(&L) -> M) -> ColorProduct<M> {
        ColorProduct {
            coefficient: self.coefficient.clone(),
            strings: self
                .strings
                .iter()
                .map(|string| ColorString {
                    row: rename(&string.row),
                    word: string.word.iter().map(&mut rename).collect(),
                    col: rename(&string.col),
                })
                .collect(),
            traces: self
                .traces
                .iter()
                .map(|trace| trace.iter().map(&mut rename).collect())
                .collect(),
            nc_power: self.nc_power,
            root2_power: self.root2_power,
        }
    }
}

/// Expanded product of network sums. An empty sum is the zero network.
pub fn multiply<L: Clone>(
    left: &[ColorProduct<L>],
    right: &[ColorProduct<L>],
) -> RusticolResult<ColorNetwork<L>> {
    left.iter()
        .flat_map(|left| right.iter().map(move |right| left.multiply(right)))
        .collect()
}

fn product(left: &ExactColorCoefficient, right: &ExactColorCoefficient) -> ExactColorCoefficient {
    Complex::new(
        &left.re * &right.re - &left.im * &right.im,
        &left.re * &right.im + &left.im * &right.re,
    )
}

fn validate_external_slots<L: Ord>(
    term: &ColorProduct<L>,
    legs: &[ColorLeg],
    external: &BTreeMap<L, i64>,
) -> RusticolResult<()> {
    use ColorRepresentation::*;
    let mut indices = Vec::new();
    let mut add = |slot: &L, representation| {
        if let Some(&label) = external.get(slot) {
            indices.push(ColorLeg {
                label,
                representation,
            });
        }
    };
    for string in &term.strings {
        add(&string.row, Antifundamental);
        add(&string.col, Fundamental);
        for label in &string.word {
            add(label, Adjoint);
        }
    }
    for label in term.traces.iter().flatten() {
        add(label, Adjoint);
    }
    indices.sort();
    if indices
        != legs
            .iter()
            .copied()
            .filter(|leg| leg.representation != Singlet)
            .collect::<Vec<_>>()
    {
        return Err(invalid(
            "color network external slots must match typed process legs exactly once",
        ));
    }
    Ok(())
}

fn join_strings<L: Ord + Clone>(
    strings: &[ColorString<L>],
    external: &BTreeMap<L, i64>,
) -> RusticolResult<(Vec<ColorString<L>>, Vec<Vec<L>>, i64)> {
    let mut by_row = BTreeMap::new();
    let mut columns = BTreeSet::new();
    for string in strings {
        if by_row.insert(string.row.clone(), string).is_some()
            || !columns.insert(string.col.clone())
        {
            return Err(invalid("a fundamental index occurs twice as row or column"));
        }
    }
    let mut used = BTreeSet::new();
    let mut opened = Vec::new();
    for start in by_row.keys().filter(|row| external.contains_key(*row)) {
        let mut word = Vec::new();
        let mut current = start;
        loop {
            if !used.insert(current.clone()) {
                return Err(invalid("fundamental strings do not form disjoint paths"));
            }
            let string = by_row
                .get(current)
                .ok_or_else(|| invalid("fundamental index is not contracted"))?;
            word.extend(string.word.iter().cloned());
            if external.contains_key(&string.col) {
                opened.push(ColorString {
                    row: start.clone(),
                    word,
                    col: string.col.clone(),
                });
                break;
            }
            current = &string.col;
        }
    }
    let mut traces = Vec::new();
    let mut empty = 0;
    for row in by_row.keys() {
        if used.contains(row) {
            continue;
        }
        let mut word = Vec::new();
        let mut current = row;
        while used.insert(current.clone()) {
            let string = by_row
                .get(current)
                .ok_or_else(|| invalid("fundamental index is not contracted"))?;
            if external.contains_key(&string.col) {
                return Err(invalid("fundamental index is not contracted"));
            }
            word.extend(string.word.iter().cloned());
            current = &string.col;
        }
        if current != row {
            return Err(invalid("fundamental indices do not close into a loop"));
        }
        if word.is_empty() {
            empty = add_power(empty, 1)?;
        } else {
            traces.push(word);
        }
    }
    Ok((opened, traces, empty))
}

#[derive(Clone, Debug, Eq, PartialEq, Ord, PartialOrd)]
enum Index<L> {
    External(i64),
    Internal(L),
    Sentinel(usize),
}

type Rows<L> = Vec<Vec<Index<L>>>;
type ReducedRows<L> = BTreeMap<(i64, Rows<L>), Rational>;

fn add_rows<L: Ord + Clone>(
    result: &mut ReducedRows<L>,
    coefficient: Rational,
    power: i64,
    mut rows: Rows<L>,
) -> RusticolResult<()> {
    if coefficient == Rational::from(0)
        || rows
            .iter()
            .any(|row| row.len() == 1 && !matches!(row[0], Index::Sentinel(_)))
    {
        return Ok(());
    }
    let empty = i64::try_from(rows.iter().filter(|row| row.is_empty()).count())
        .map_err(|_| invalid("color trace count overflows"))?;
    rows.retain(|row| !row.is_empty());
    for row in &mut rows {
        let rotation = (0..row.len())
            .min_by(|&a, &b| {
                row[a..]
                    .iter()
                    .chain(&row[..a])
                    .cmp(row[b..].iter().chain(&row[..b]))
            })
            .unwrap();
        row.rotate_left(rotation);
    }
    rows.sort();
    *result
        .entry((add_power(power, empty)?, rows))
        .or_insert_with(|| Rational::from(0)) += coefficient;
    Ok(())
}

fn fierz<L: Ord + Clone>(rows: Rows<L>) -> RusticolResult<ReducedRows<L>> {
    let mut occurrences = BTreeMap::new();
    for index in rows.iter().flatten() {
        *occurrences.entry(index).or_insert(0usize) += 1;
    }
    for (index, count) in occurrences {
        let expected = if matches!(index, Index::Internal(_)) {
            2
        } else {
            1
        };
        if count != expected {
            return Err(invalid(
                "internal adjoint indices must occur twice and external indices once",
            ));
        }
    }
    let mut terms = ReducedRows::new();
    add_rows(&mut terms, Rational::from(1), 0, rows)?;
    let mut finished = ReducedRows::new();
    while !terms.is_empty() {
        let mut next = ReducedRows::new();
        for ((power, rows), coefficient) in terms {
            if coefficient == Rational::from(0) {
                continue;
            }
            let first = rows.iter().enumerate().find_map(|(r, row)| {
                row.iter()
                    .enumerate()
                    .find(|(_, index)| matches!(index, Index::Internal(_)))
                    .map(|(p, index)| (r, p, index))
            });
            let Some((first_row, first_pos, index)) = first else {
                add_rows(&mut finished, coefficient, power, rows)?;
                continue;
            };
            let (second_row, second_pos) = rows
                .iter()
                .enumerate()
                .find_map(|(r, row)| {
                    row.iter()
                        .enumerate()
                        .find(|&(p, other)| other == index && (r != first_row || p != first_pos))
                        .map(|(p, _)| (r, p))
                })
                .ok_or_else(|| {
                    RusticolError::internal("unpaired internal adjoint after Fierz reduction")
                })?;
            let (direct, suppressed) =
                trace::fierz_pair(&rows, first_row, first_pos, second_row, second_pos);
            add_rows(&mut next, coefficient.clone(), power, direct)?;
            add_rows(&mut next, -coefficient, add_power(power, -1)?, suppressed)?;
        }
        terms = next;
    }
    finished.retain(|_, value| *value != Rational::from(0));
    Ok(finished)
}

fn decode<L>(rows: Rows<L>, sentinel_ends: &[(i64, i64)]) -> RusticolResult<ColorTensor> {
    let mut strings = Vec::new();
    let mut traces = Vec::new();
    let external = |index: &Index<L>| match index {
        Index::External(label) => Ok(*label),
        _ => Err(invalid(
            "an internal index survived color network reduction",
        )),
    };
    for mut row in rows {
        let Some(first) = row
            .iter()
            .position(|index| matches!(index, Index::Sentinel(_)))
        else {
            traces.push(
                row.iter()
                    .rev()
                    .map(external)
                    .collect::<RusticolResult<_>>()?,
            );
            continue;
        };
        row.rotate_left(first);
        let marks: Vec<_> = row
            .iter()
            .enumerate()
            .filter_map(|(pos, index)| {
                if let Index::Sentinel(number) = index {
                    Some((pos, *number))
                } else {
                    None
                }
            })
            .collect();
        for (index, &(start, first)) in marks.iter().enumerate() {
            let (stop, next) = marks
                .get(index + 1)
                .copied()
                .unwrap_or((row.len(), marks[0].1));
            // tr(E_1 W_1 E_2 W_2...) joins row_1 to col_2. Literal
            // tensors run from the quark (lower) to antiquark (upper).
            strings.push(OpenColorString {
                fundamental: sentinel_ends[next].1,
                adjoints: row[start + 1..stop]
                    .iter()
                    .rev()
                    .map(external)
                    .collect::<RusticolResult<_>>()?,
                antifundamental: sentinel_ends[first].0,
            });
        }
    }
    Ok(ColorTensor::new(strings, traces))
}

/// Contract every internal index, retaining the entire external color tensor.
/// `external` maps network slot labels to process leg labels. Negative external
/// labels are supported and cannot collide with internal or sentinel indices.
pub fn reduce_network<L: Ord + Clone>(
    network: &[ColorProduct<L>],
    legs: Vec<ColorLeg>,
    external: &BTreeMap<L, i64>,
) -> RusticolResult<ConnectedColorTensor> {
    let legs = canonical_legs(legs)?;
    let mapped: BTreeSet<_> = external.values().copied().collect();
    if mapped.len() != external.len()
        || mapped
            .iter()
            .any(|label| !legs.iter().any(|leg| leg.label == *label))
    {
        return Err(invalid(
            "external color network slots must map to distinct process legs",
        ));
    }
    let mut reduced = Vec::new();
    for term in network {
        if is_zero(&term.coefficient) {
            continue;
        }
        // Validate the typed domain before algebra: a traceless term must not
        // hide an incorrect representation or missing external index.
        validate_external_slots(term, &legs, external)?;
        let (opened, joined, empty) = join_strings(&term.strings, external)?;
        let number = |label: &L| match external.get(label) {
            Some(&label) => Index::External(label),
            None => Index::Internal(label.clone()),
        };
        let mut rows: Rows<L> = term
            .traces
            .iter()
            .chain(&joined)
            .map(|row| row.iter().map(number).collect())
            .collect();
        let mut sentinel_ends = Vec::new();
        for string in opened {
            let sentinel = Index::Sentinel(sentinel_ends.len());
            sentinel_ends.push((external[&string.row], external[&string.col]));
            let mut row: Vec<_> = string.word.iter().map(number).collect();
            row.push(sentinel);
            rows.push(row);
        }
        for ((power, rows), factor) in fierz(rows)? {
            reduced.push((
                TensorTerm {
                    coefficient: scale(&term.coefficient, &factor),
                    tensor: decode(rows, &sentinel_ends)?,
                    nc_power: add_power(add_power(term.nc_power, empty)?, power)?,
                },
                term.root2_power,
            ));
        }
    }
    let mut parity = None;
    for (_, power) in &reduced {
        let current = power.rem_euclid(2);
        if parity.is_some_and(|old| old != current) {
            return Err(invalid(
                "color network mixes rational and sqrt(2) coefficients",
            ));
        }
        parity = Some(current);
    }
    let target = parity.unwrap_or(0);
    let terms = reduced
        .into_iter()
        .map(|(mut term, power)| {
            let exponent = target
                .checked_sub(power)
                .ok_or_else(|| invalid("color normalization exponent overflows"))?
                / 2;
            let factor = if exponent < 0 {
                Rational::from((1, 2))
            } else {
                Rational::from(2)
            }
            .pow(exponent.unsigned_abs());
            term.coefficient = scale(&term.coefficient, &factor);
            Ok(term)
        })
        .collect::<RusticolResult<_>>()?;
    ConnectedColorTensor::new(legs, terms, target as u32)
}
