// SPDX-License-Identifier: 0BSD
//! Small binary64 saved-EW transport check; source physics has separate oracles.
#[path = "../../src/pyamplicol/_sdk/rust/rusticol.rs"]
#[allow(dead_code)]
mod rusticol;
use rusticol::virtual_amplitudes::{PointStatus, Runtime};

fn main() {
    let path = std::env::args().nth(1).expect("artifact path");
    let mut runtime = Runtime::open(path, None, None, Some("model")).unwrap();
    let shape = runtime.shape();
    assert_eq!(shape.external_count, 4);
    assert_eq!(shape.born_orders, 1);
    assert_eq!(shape.virtual_orders, 1);
    assert_eq!(shape.epsilon_count, 3);
    assert_eq!(shape.virtual_color_components, 1);
    assert_eq!(shape.resolved_available, 0);
    let metadata = runtime.metadata_json().unwrap();
    assert!(metadata.contains("Bdagger K_BL L + Ldagger K_LB B"));
    assert!(metadata.contains("QED"));
    let point = [
        500.0, 0.0, 0.0, 500.0,
        500.0, 0.0, 0.0, -500.0,
        500.0, 300.0, 0.0, 400.0,
        500.0, -300.0, 0.0, -400.0,
    ];
    let result = runtime.evaluate_correlated(
        &[point, point].concat(), 2, Some(&[u64::MAX, 7]), &[1e6, 1e6], None, None,
    ).unwrap();
    assert_eq!(result.successful_point_ids, [u64::MAX, 7]);
    assert_eq!(result.statuses, [PointStatus::Success, PointStatus::Success]);
    assert_eq!(result.shape.axes.histories, 5);
    assert_eq!(result.shape.axes.epsilon_count, 3);
    assert_eq!(result.spin_legs_json, "[]");
    assert!(result.histories_json.contains("history-4"));
    assert_eq!(result.virtual_values.len(), 30);
    assert_eq!(result.born.len(), 10);
    let factors = [1.0, 4.0/3.0, -4.0/3.0, -4.0/3.0, 4.0/3.0];
    let provider = [-0.004031504670321551, 9.092094536836312e-5, -0.0001721311784164292];
    for row in 0..2 {
        for (history, factor) in factors.iter().enumerate() {
            let born = result.born[row*5 + history];
            assert!((born.re - factor*0.04960749842717813).abs() < 1e-10);
            assert!(born.im.abs() < 1e-10);
            for (epsilon, reference) in provider.iter().enumerate() {
                let value = result.virtual_values[(row*5 + history)*3 + epsilon];
                assert!((value.re - factor*reference).abs() < 1e-10);
                assert!(value.im.abs() < 1e-10);
            }
        }
    }
    drop(runtime);
    assert!(result.histories_json.contains("history-4"));
    assert_eq!(result.successful_point_ids[0], u64::MAX);
    println!("EW_COLOR_SDK_PASSED five histories, Laurent axes, original IDs, owned results");
}
