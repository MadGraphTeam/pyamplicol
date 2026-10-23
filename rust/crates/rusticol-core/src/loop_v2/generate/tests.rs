// SPDX-License-Identifier: 0BSD

use super::families::{
    CurrentInput, FamilyInput, LegInput, SpeciesInput, VertexInput, generate_families,
};
use super::schedules::{CostModel, FramePolicy, ScheduleInput, build_schedules, build_skeletons};

// A massive scalar cubic interaction, with only singleton external currents.
// Its n-gons are the unoriented cyclic orderings: (n-1)!/2.
fn scalar_polygon(legs: usize) -> FamilyInput {
    FamilyInput {
        legs: vec![LegInput { field: 0, mass: 0 }; legs],
        species: vec![Some(SpeciesInput {
            antiname: 0,
            colour: 1,
            mass: 0,
            perturbative: vec![0],
        })],
        massless: vec![false],
        vertices: vec![VertexInput {
            loop_in: 0,
            attached: vec![0],
            loop_out: 0,
            orders: vec![(0, 1)],
            q_degree: 0,
            reflected: 0,
        }],
        vertices_by_loop_in: vec![vec![0]],
        currents: (0..legs)
            .map(|leg| CurrentInput {
                mask: 1 << leg,
                field: 0,
                orders: vec![],
            })
            .collect(),
        eligible: vec![0],
        multiplicity: vec![1],
        corrections: vec![0],
        loop_orders: vec![vec![(0, legs as i64)]],
        cap: vec![(0, legs as i64)],
    }
}

fn scalar_states(positions: usize) -> ScheduleInput {
    ScheduleInput {
        states: vec![Some(vec![0]); positions],
        reflected: vec![0],
        keep: None,
        policy: FramePolicy::Cheapest {
            model: CostModel {
                fused: 1,
                split: 1,
                vertex: 1,
                seed_fused: 1,
                seed_split: 1,
                closure: 1,
                columns: 1,
            },
        },
    }
}

#[test]
fn scalar_polygon_families_and_schedules_count_cyclic_orderings() {
    for (legs, count) in [(3, 1), (4, 3), (5, 12)] {
        let input = scalar_polygon(legs);
        let output = generate_families(&input).unwrap();
        assert_eq!(output.families.len(), count);
        assert!(output.scaleless.is_empty());
        assert!(output.rejected.is_empty());
        let states = scalar_states(output.positions.len());
        let (_, _, skeletons) = build_skeletons(&input, &output, &states).unwrap();
        assert!(skeletons.iter().all(|family| family.len() == 1));
        let schedules = build_schedules(&input, &output, &states).unwrap();
        assert_eq!(schedules.schedules.len(), count);
        for schedule in schedules.schedules {
            assert_eq!(schedule.rank, 0);
            assert_eq!(schedule.leaves.len(), 1);
            let ring = &schedule.leaves[0].1;
            assert_eq!(ring.len(), legs);
            let masks = ring
                .iter()
                .map(|&label| schedules.contents[schedules.labels[label as usize] as usize].mask)
                .collect::<Vec<_>>();
            assert!(masks.iter().all(|mask| mask.count_ones() == 1));
            assert_eq!(
                masks.iter().fold(0, |all, mask| all | mask),
                (1 << legs) - 1
            );
        }
    }
}

#[test]
fn scalar_family_selection_respects_mass_and_coupling_order() {
    let mut input = scalar_polygon(3);
    input.massless[0] = true;
    let output = generate_families(&input).unwrap();
    assert!(output.families.is_empty());
    assert_eq!(output.scaleless.len(), 1);
    input.massless[0] = false;
    input.cap = vec![(0, 2)];
    assert!(generate_families(&input).unwrap().families.is_empty());
}

#[test]
fn invalid_native_table_references_are_errors() {
    let mut input = scalar_polygon(3);
    input.eligible = vec![1];
    assert!(generate_families(&input).is_err());
    input = scalar_polygon(3);
    input.vertices[0].orders = vec![(64, 1)];
    assert!(generate_families(&input).is_err());
    input = scalar_polygon(3);
    input.currents[0].mask = 0;
    assert!(generate_families(&input).is_err());
    input = scalar_polygon(3);
    input.vertices_by_loop_in[0] = vec![1];
    assert!(generate_families(&input).is_err());
    input = scalar_polygon(3);
    input.vertices[0].reflected = 1;
    assert!(generate_families(&input).is_err());
    input = scalar_polygon(3);
    let output = generate_families(&input).unwrap();
    let mut states = scalar_states(output.positions.len());
    states.reflected[0] = 1;
    assert!(build_schedules(&input, &output, &states).is_err());
}

#[test]
fn unrepresentable_schedule_cost_is_an_error() {
    let mut input = scalar_polygon(3);
    input.vertices[0].q_degree = i64::MAX / 6;
    let output = generate_families(&input).unwrap();
    let states = scalar_states(output.positions.len());
    assert!(build_schedules(&input, &output, &states).is_err());
}
