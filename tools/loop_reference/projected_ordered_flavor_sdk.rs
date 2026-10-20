// SPDX-License-Identifier: 0BSD
//! Actual projected ordered member versus independent member, using the safe SDK.
use rusticol_loop_sdk::{
    Complex64, CorrelatedEvaluation, PointStatus, Runtime, SourceOverrides, SpinSources,
};
use std::path::Path;

fn close(a: Complex64, b: Complex64) {
    for (x, y) in [(a.real, b.real), (a.imag, b.imag)] {
        assert!(x.is_finite() && y.is_finite());
        assert!((x - y).abs() <= 3e-9 * x.abs().max(y.abs()).max(1.));
    }
}

fn compare(actual: &CorrelatedEvaluation, expected: &CorrelatedEvaluation) {
    assert_eq!(
        actual.history_ids,
        ["born", "casimir", "ordered", "swapped"]
    );
    assert_eq!(actual.history_ids, expected.history_ids);
    assert_eq!(actual.requested_point_ids, [u64::MAX, 7]);
    assert_eq!(actual.successful_point_ids, actual.requested_point_ids);
    assert_eq!(actual.requested_point_ids, expected.requested_point_ids);
    assert_eq!(actual.statuses, [PointStatus::Success; 2]);
    assert_eq!(actual.statuses, expected.statuses);
    assert_eq!(actual.shape, expected.shape);
    assert_eq!(actual.shape.histories, 4);
    assert_eq!(actual.shape.epsilon_count, 3);
    assert_eq!(actual.spin_legs, [3, 4]);
    assert_eq!(actual.spin_legs, expected.spin_legs);
    assert_eq!(actual.born.len(), 2 * 4 * actual.shape.born_orders);
    assert_eq!(
        actual.virtual_values.len(),
        2 * 4 * actual.shape.virtual_orders * 3
    );
    assert_eq!(actual.born.len(), expected.born.len());
    assert_eq!(actual.virtual_values.len(), expected.virtual_values.len());
    for (&a, &b) in actual
        .born
        .iter()
        .chain(&actual.virtual_values)
        .zip(expected.born.iter().chain(&expected.virtual_values))
    {
        close(a, b);
    }
    let width = actual.shape.virtual_orders * 3;
    assert!(
        actual.virtual_values[2 * width..3 * width]
            .iter()
            .any(|value| value.imag.abs() > 1e-6),
        "NLC ordered imaginary interference was erased"
    );
    for row in actual.virtual_values.chunks_exact(4 * width) {
        for (&ordered, swapped) in row[2 * width..3 * width].iter().zip(&row[3 * width..]) {
            close(
                ordered,
                Complex64 {
                    real: swapped.real,
                    imag: -swapped.imag,
                },
            );
        }
    }
}

fn main() {
    let root = std::env::args()
        .nth(1)
        .expect("projected ordered fixture root");
    let root = Path::new(&root);
    let parameters: SourceOverrides = [
        ("aS", "0.118"),
        ("MB", "0"),
        ("ymb", "0"),
        ("MT", "173"),
        ("MU_R", "1000"),
    ]
    .into_iter()
    .map(|(name, value)| (name.into(), [value.into(), "0".into()]))
    .collect();
    let mut member = Runtime::open(
        root.join("nlc-mapped-artifact"),
        Some("ssgg"),
        Some(&parameters),
        "model",
    )
    .unwrap();
    let mut independent = Runtime::open(
        root.join("nlc-independent-artifact"),
        Some("ssgg"),
        Some(&parameters),
        "model",
    )
    .unwrap();
    assert_eq!(member.shape(), independent.shape());
    assert_eq!(member.shape().resolved_available, 0);
    assert_eq!(member.shape().born_color_components, 1);
    assert_eq!(member.shape().virtual_color_components, 1);
    assert_eq!(
        member.correlation_history_ids(),
        ["born", "casimir", "ordered", "swapped"]
    );
    assert_eq!(
        member.spin_correlation_classes(),
        [vec![3], vec![3, 4], vec![4]]
    );
    assert!(
        member
            .metadata_json()
            .unwrap()
            .contains("Bdagger K_BL L + Ldagger K_LB B")
    );
    assert!(
        member
            .capabilities_json()
            .unwrap()
            .contains("contracted colour")
    );
    let point = [
        500., 0., 0., 500., 500., 0., 0., -500., 500., 300., 0., 400., 500., -300., 0., -400.,
    ];
    let points = [point, point].concat();
    let vectors = [
        (0.1, 0.2),
        (0.8, -0.3),
        (0.4, 1.),
        (-0.6, 0.5),
        (-0.3, 0.7),
        (-0.2, 0.8),
        (0.6, 0.1),
        (0.5, -0.4),
    ]
    .map(|(real, imag)| Complex64 { real, imag })
    .to_vec();
    // An unsorted source key order must retain the literal vector association.
    let source = SpinSources {
        legs: &[4, 3],
        values: &vectors,
    };
    let actual = member
        .evaluate_correlated_with_sources(&points, &[u64::MAX, 7], &[1e6, 9e5], source, None, None)
        .unwrap();
    let expected = independent
        .evaluate_correlated_with_sources(&points, &[u64::MAX, 7], &[1e6, 9e5], source, None, None)
        .unwrap();
    compare(&actual, &expected);
    member.clear();
    drop((member, independent, vectors));
    assert_eq!(actual.successful_point_ids, [u64::MAX, 7]);
    assert_eq!(
        actual.history_ids,
        ["born", "casimir", "ordered", "swapped"]
    );
    assert_eq!(actual.spin_legs, [3, 4]);
    println!(
        "PROJECTED_ORDERED_FLAVOR_SDK_PASS complex totals, history/order/pole axes, literal sources, opaque IDs and owned results"
    );
}
