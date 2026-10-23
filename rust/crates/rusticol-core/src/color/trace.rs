// SPDX-License-Identifier: 0BSD

//! Exact trace/Fierz reduction used by the validated literal tensor overlap.

use super::*;

fn overlap_traces(left: &ColorTensor, right: &ColorTensor) -> Vec<Vec<i64>> {
    let mut traces = right.traces.clone();
    traces.extend(
        left.traces
            .iter()
            .map(|trace| trace.iter().rev().copied().collect()),
    );
    let right_by_q: BTreeMap<_, _> = right
        .open_strings
        .iter()
        .map(|string| (string.fundamental, string))
        .collect();
    let left_by_qbar: BTreeMap<_, _> = left
        .open_strings
        .iter()
        .map(|string| (string.antifundamental, string))
        .collect();
    let mut visited = BTreeSet::new();
    for &start in right_by_q.keys() {
        if visited.contains(&start) {
            continue;
        }
        let mut current = start;
        let mut trace = Vec::new();
        while visited.insert(current) {
            let right_string = right_by_q[&current];
            let left_string = left_by_qbar[&right_string.antifundamental];
            trace.extend(&right_string.adjoints);
            trace.extend(left_string.adjoints.iter().rev());
            current = left_string.fundamental;
        }
        // An empty newly closed loop contributes Nc.
        traces.push(trace);
    }
    traces
}

type TraceTerms = BTreeMap<(i64, Vec<Vec<i64>>), Rational>;

/// The two terms of the tau-generator Fierz identity. The second carries
/// coefficient -1/Nc; this operation is shared by overlaps and open networks.
pub(super) fn fierz_pair<T: Clone>(
    traces: &[Vec<T>],
    first_trace: usize,
    first_position: usize,
    second_trace: usize,
    second_position: usize,
) -> (Vec<Vec<T>>, Vec<Vec<T>>) {
    let first = &traces[first_trace];
    let concat = |parts: &[&[T]]| parts.iter().flat_map(|part| part.iter().cloned()).collect();
    let mut direct: Vec<_> = traces
        .iter()
        .enumerate()
        .filter(|&(index, _)| index != first_trace && index != second_trace)
        .map(|(_, trace)| trace.clone())
        .collect();
    let mut suppressed = direct.clone();
    if first_trace == second_trace {
        let before = &first[..first_position];
        let between = &first[first_position + 1..second_position];
        let after = &first[second_position + 1..];
        direct.extend([concat(&[before, after]), between.to_vec()]);
        suppressed.push(concat(&[before, between, after]));
    } else {
        let second = &traces[second_trace];
        direct.push(concat(&[
            &first[..first_position],
            &second[second_position + 1..],
            &second[..second_position],
            &first[first_position + 1..],
        ]));
        suppressed.extend([
            concat(&[&first[..first_position], &first[first_position + 1..]]),
            concat(&[&second[..second_position], &second[second_position + 1..]]),
        ]);
    }
    (direct, suppressed)
}

fn add_term(
    terms: &mut TraceTerms,
    coefficient: Rational,
    power: i64,
    traces: Vec<Vec<i64>>,
) -> RusticolResult<()> {
    if coefficient == Rational::from(0) || traces.iter().any(|trace| trace.len() == 1) {
        return Ok(());
    }
    let empty = i64::try_from(traces.iter().filter(|trace| trace.is_empty()).count())
        .map_err(|_| invalid("color trace count overflows"))?;
    let power = add_power(power, empty)?;
    let traces = canonical_traces(
        traces
            .into_iter()
            .filter(|trace| !trace.is_empty())
            .collect(),
    );
    *terms
        .entry((power, traces))
        .or_insert_with(|| Rational::from(0)) += coefficient;
    Ok(())
}

pub(super) fn contract(
    left: &ColorTensor,
    right: &ColorTensor,
) -> RusticolResult<BTreeMap<i64, Rational>> {
    let mut terms = TraceTerms::new();
    add_term(
        &mut terms,
        Rational::from(1),
        0,
        overlap_traces(left, right),
    )?;
    let mut result = BTreeMap::new();
    while !terms.is_empty() {
        let mut next = TraceTerms::new();
        for ((power, traces), coefficient) in terms {
            if coefficient == Rational::from(0) {
                continue;
            }
            if traces.is_empty() {
                *result.entry(power).or_insert_with(|| Rational::from(0)) += coefficient;
                continue;
            }
            // Valid matching bra/ket tensors contain each adjoint label exactly
            // twice. Each Fierz step eliminates that pair, ensuring termination.
            let first = &traces[0];
            let label = first[0];
            let (other_trace, other_position) = traces
                .iter()
                .enumerate()
                .find_map(|(index, trace)| {
                    trace
                        .iter()
                        .enumerate()
                        .find(|&(position, &value)| value == label && (index != 0 || position != 0))
                        .map(|(position, _)| (index, position))
                })
                .ok_or_else(|| {
                    RusticolError::internal("unpaired adjoint index in validated color overlap")
                })?;
            let suppressed = add_power(power, -1)?;
            let (direct, subleading) = fierz_pair(&traces, 0, 0, other_trace, other_position);
            add_term(&mut next, coefficient.clone(), power, direct)?;
            add_term(&mut next, -coefficient, suppressed, subleading)?;
        }
        terms = next;
    }
    result.retain(|_, value| *value != Rational::from(0));
    Ok(result)
}
