// SPDX-License-Identifier: 0BSD
// Link against the built safe SDK rlib; argument: fresh ddgg/ssgg grouped artifact.
use rusticol_loop_sdk::{Complex64, Runtime, SpinSources};

fn main() {
    let path = std::env::args().nth(1).expect("grouped artifact path");
    let mut member = Runtime::open(&path, Some("ssgg"), None, "model").unwrap();
    let mut representative = Runtime::open(&path, Some("ddgg"), None, "model").unwrap();
    let metadata = member.metadata_json().unwrap();
    assert!(metadata.contains("\"process_id\":\"ssgg\""));
    assert!(metadata.contains("\"representative_process_id\":\"ddgg\""));
    let point = [
        500., 0., 0., 500., 500., 0., 0., -500., 500., 300., 0., 400., 500., -300., 0., -400.,
    ];
    // Unequal complex vectors, in reversed leg order, exercise source labels.
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
    let legs = vec![4, 3];
    let mapped = member
        .evaluate_correlated_with_sources(
            &point,
            &[u64::MAX],
            &[1e6],
            SpinSources {
                legs: &legs,
                values: &values,
            },
            None,
            None,
        )
        .unwrap();
    let direct = representative
        .evaluate_correlated_with_sources(
            &point,
            &[7],
            &[1e6],
            SpinSources {
                legs: &legs,
                values: &values,
            },
            None,
            None,
        )
        .unwrap();
    for (a, b) in mapped
        .born
        .iter()
        .chain(&mapped.virtual_values)
        .zip(direct.born.iter().chain(&direct.virtual_values))
    {
        assert_eq!((a.real, a.imag), (b.real, b.imag));
    }
    assert!(member
        .evaluate_correlated_with_sources(
            &point,
            &[0],
            &[1e6],
            SpinSources {
                legs: &[2],
                values: &values[..4]
            },
            None,
            None,
        )
        .is_err());
    member.clear();
    drop((member, representative, values, legs));
    assert_eq!(mapped.successful_point_ids, [u64::MAX]);
    assert_eq!(mapped.spin_legs, [3, 4]);
    assert!(!mapped.history_ids.is_empty());
    println!("mapped joint-source SDK selection, literal labels and result ownership passed");
}
