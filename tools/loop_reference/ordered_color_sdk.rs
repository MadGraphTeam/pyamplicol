// SPDX-License-Identifier: 0BSD
//! Saved ordered LC families keep contracted shapes and owned source results.
#[path = "../../src/pyamplicol/_sdk/rust/rusticol.rs"]
#[allow(dead_code)]
mod rusticol;
use rusticol::virtual_amplitudes::{Complex64, Runtime};
fn main() {
    let path = std::env::args().nth(1).expect("artifact path");
    let mut runtime = Runtime::open(path, None, None, Some("model")).unwrap();
    let shape = runtime.shape();
    assert_eq!(shape.external_count, 4);
    assert_eq!(shape.born_color_components, 1);
    assert_eq!(shape.virtual_color_components, 1);
    assert_eq!(shape.resolved_available, 0);
    let capabilities = runtime.capabilities_json().unwrap();
    assert!(capabilities.contains("contracted colour"));
    assert!(!capabilities.contains("signed canonical Born"));
    let point = [
        500.0,
        0.0,
        0.0,
        500.0,
        500.0,
        0.0,
        0.0,
        -500.0,
        503.23360778192045,
        298.0598353308477,
        0.0,
        397.4131137744637,
        496.76639221807955,
        -298.0598353308477,
        0.0,
        -397.4131137744637,
    ];
    let vector = [6.177226676643207, 3.754587405996522, 0.0, 5.006116541328697];
    let vectors = vector
        .iter()
        .map(|&x| Complex64::new(x, 0.0))
        .chain(vector.iter().map(|&x| Complex64::new(2.0 * x, 3.0 * x)))
        .collect::<Vec<_>>();
    let result = runtime
        .evaluate_correlated_with_sources(
            &[point, point].concat(),
            2,
            Some(&[u64::MAX, 42]),
            &[1e6, 1e6],
            &[3],
            &vectors,
            None,
            None,
        )
        .unwrap();
    assert_eq!(result.spin_legs_json, "[3]");
    assert_eq!(result.shape.axes.histories, 11);
    assert_eq!(result.shape.axes.epsilon_count, 3);
    assert!(result.histories_json.contains("history-10"));
    assert_eq!(result.virtual_values.len(), 2 * 11 * 3);
    assert_eq!(result.born.len(), 2 * 11);
    for (a, b) in result.virtual_values[..33]
        .iter()
        .zip(&result.virtual_values[33..])
    {
        assert!(a.re.is_finite() && a.im.is_finite());
        assert!((b.re - 13.0 * a.re).abs() < 1e-9 * (1.0 + a.re.abs()));
        assert!((b.im - 13.0 * a.im).abs() < 1e-9 * (1.0 + a.im.abs()));
    }
    drop(runtime);
    assert_eq!(result.spin_legs_json, "[3]");
    assert!(result.histories_json.contains("history-10"));
    println!(
        "ORDERED_COLOR_SDK_PASSED contracted family axes, literal source scaling, owned result"
    );
}
