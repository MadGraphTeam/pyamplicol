// SPDX-License-Identifier: 0BSD
//! Selected Bose histories and literal source labels through the safe SDK.
use rusticol_loop_sdk::{Complex64, CorrelatedEvaluation, Runtime, SpinSources};
use std::path::Path;

fn compare(actual: &CorrelatedEvaluation, reference: &CorrelatedEvaluation) {
    assert_eq!(actual.history_ids, ["born", "casimir"]);
    assert_eq!(actual.successful_point_ids, [u64::MAX]);
    assert_eq!(actual.requested_point_ids, [u64::MAX]);
    assert_eq!(actual.shape.histories, 2);
    assert_eq!(actual.shape.epsilon_count, 3);
    assert_eq!(actual.shape.born_orders, reference.shape.born_orders);
    assert_eq!(actual.shape.virtual_orders, reference.shape.virtual_orders);
    for (a, b, width) in [
        (&actual.born, &reference.born, actual.shape.born_orders),
        (
            &actual.virtual_values,
            &reference.virtual_values,
            actual.shape.virtual_orders * 3,
        ),
    ] {
        assert_eq!(a.len(), width * 2);
        for (selected, id) in actual.history_ids.iter().enumerate() {
            let independent = reference
                .history_ids
                .iter()
                .position(|value| value == id)
                .unwrap();
            for column in 0..width {
                let x = a[selected * width + column];
                let y = b[independent * width + column];
                for (left, right) in [(x.real, y.real), (x.imag, y.imag)] {
                    assert!((left - right).abs() <= 8e-10 * left.abs().max(right.abs()).max(1.));
                }
            }
        }
    }
}

fn main() {
    let root = std::env::args()
        .nth(1)
        .expect("actual Bose correlated fixture root");
    let root = Path::new(&root);
    let point = [
        500., 0., 0., 500., 500., 0., 0., -500., 500., 300., 0., 400., 500., -300., 0., -400.,
    ];
    let values = [
        (0.1, 0.2),
        (0.8, -0.3),
        (0.4, 1.),
        (-0.6, 0.5),
        (-0.3, 0.7),
        (-0.2, 0.8),
        (0.6, 0.1),
        (0.5, -0.4),
    ]
    .into_iter()
    .map(|(real, imag)| Complex64 { real, imag })
    .collect::<Vec<_>>();
    let mut member =
        Runtime::open(root.join("artifact"), Some("ssgg-swap"), None, "model").unwrap();
    let representative = Runtime::open(root.join("artifact"), Some("ddgg"), None, "model").unwrap();
    let mut independent = Runtime::open(
        root.join("independent-artifact"),
        Some("ssgg"),
        None,
        "model",
    )
    .unwrap();
    assert_eq!(member.correlation_history_ids(), ["born", "casimir"]);
    assert_eq!(
        representative.correlation_history_ids(),
        ["born", "casimir", "ordered", "swapped"]
    );
    assert_eq!(
        member.spin_correlation_classes(),
        [vec![3], vec![3, 4], vec![4]]
    );
    assert_eq!(member.shape().resolved_available, 0);
    let legs = [4, 3];
    let source = SpinSources {
        legs: &legs,
        values: &values,
    };
    let actual = member
        .evaluate_correlated_with_sources(&point, &[u64::MAX], &[1e6], source, None, None)
        .unwrap();
    let expected = independent
        .evaluate_correlated_with_sources(&point, &[u64::MAX], &[1e6], source, None, None)
        .unwrap();
    compare(&actual, &expected);
    assert_eq!(actual.spin_legs, [3, 4]);
    assert!(
        member
            .evaluate(&point, &[u64::MAX], &[1e6], true, None, None)
            .is_err()
    );
    let mut single = Runtime::open(
        root.join("single-source-artifact"),
        Some("ssgg-swap"),
        None,
        "model",
    )
    .unwrap();
    let single_rep = Runtime::open(
        root.join("single-source-artifact"),
        Some("ddgg"),
        None,
        "model",
    )
    .unwrap();
    assert_eq!(single.spin_correlation_classes(), [vec![4]]);
    assert_eq!(single_rep.spin_correlation_classes(), [vec![3]]);
    let single_source = SpinSources {
        legs: &[4],
        values: &values[..4],
    };
    let single_value = single
        .evaluate_correlated_with_sources(&point, &[u64::MAX], &[1e6], single_source, None, None)
        .unwrap();
    let reference = independent
        .evaluate_correlated_with_sources(&point, &[u64::MAX], &[1e6], single_source, None, None)
        .unwrap();
    compare(&single_value, &reference);
    assert_eq!(single_value.spin_legs, [4]);
    assert!(
        single
            .evaluate_correlated_with_sources(
                &point,
                &[0],
                &[1e6],
                SpinSources {
                    legs: &[3],
                    values: &values[..4]
                },
                None,
                None
            )
            .is_err()
    );
    member.clear();
    drop((
        member,
        representative,
        independent,
        single,
        single_rep,
        values,
    ));
    assert_eq!(actual.history_ids, ["born", "casimir"]);
    assert_eq!(actual.spin_legs, [3, 4]);
    assert_eq!(single_value.spin_legs, [4]);
    println!(
        "BOSE_CORRELATED_SDK_PASS selected histories, inverse source classes, values, opaque IDs, owned results"
    );
}
