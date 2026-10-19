// SPDX-License-Identifier: 0BSD
//! Actual longitudinal W source through the unchanged standalone ABI.
#[path = "../../src/pyamplicol/_sdk/rust/rusticol.rs"]
#[allow(dead_code)]
mod rusticol;
use rusticol::virtual_amplitudes::{Complex64, Runtime};
fn main() {
    let path = std::env::args().nth(1).expect("artifact path");
    let mut runtime = Runtime::open(path, None, None, Some("model")).unwrap();
    assert_eq!(runtime.shape().external_count, 4);
    let point = [500.0,0.0,0.0,500.0,500.0,0.0,0.0,-500.0,503.23360778192045,298.0598353308477,0.0,397.4131137744637,496.76639221807955,-298.0598353308477,0.0,-397.4131137744637];
    let vector = [Complex64::new(6.177226676643207,0.0),
        Complex64::new(3.754587405996522,0.0),
        Complex64::new(0.0,0.0),
        Complex64::new(5.006116541328697,0.0)];
    let result = runtime.evaluate_correlated_with_sources(
        &point, 1, Some(&[u64::MAX]), &[1e6], &[3], &vector, None, None,
    ).unwrap();
    assert_eq!(result.spin_legs_json, "[3]");
    let expected = [0.0036849228082977982,-0.0021440863000850505,-0.0010447088709596558,-0.00039215540059478883];
    let actual = [result.born[0], result.virtual_values[0], result.virtual_values[1], result.virtual_values[2]];
    for (a, b) in actual.iter().zip(expected.iter()) {
        assert!((a.re-b).abs() <= 8e-9*b.abs()+2e-12, "{a:?} != {b}");
        assert!(a.im.abs() < 2e-12);
    }
    drop(runtime);
    assert_eq!(result.spin_legs_json, "[3]");
    println!("MASSIVE_VECTOR_SDK_PASSED physical longitudinal state, unchanged source ABI, owned result");
}
