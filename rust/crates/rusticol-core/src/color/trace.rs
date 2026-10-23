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
            if other_trace == 0 {
                let between = &first[1..other_position];
                let after = &first[other_position + 1..];
                let mut direct = traces[1..].to_vec();
                direct.extend([after.to_vec(), between.to_vec()]);
                add_term(&mut next, coefficient.clone(), power, direct)?;
                let mut subleading = traces[1..].to_vec();
                subleading.push(concat(&[between, after]));
                add_term(&mut next, -coefficient, suppressed, subleading)?;
            } else {
                let second = &traces[other_trace];
                let rest: Vec<_> = traces
                    .iter()
                    .enumerate()
                    .filter(|&(index, _)| index != 0 && index != other_trace)
                    .map(|(_, trace)| trace.clone())
                    .collect();
                let mut direct = rest.clone();
                direct.push(concat(&[
                    &second[other_position + 1..],
                    &second[..other_position],
                    &first[1..],
                ]));
                add_term(&mut next, coefficient.clone(), power, direct)?;
                let mut subleading = rest;
                subleading.extend([
                    first[1..].to_vec(),
                    concat(&[&second[..other_position], &second[other_position + 1..]]),
                ]);
                add_term(&mut next, -coefficient, suppressed, subleading)?;
            }
        }
        terms = next;
    }
    result.retain(|_, value| *value != Rational::from(0));
    Ok(result)
}
