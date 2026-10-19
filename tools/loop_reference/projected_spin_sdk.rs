// SPDX-License-Identifier: 0BSD
//! Saved projected identity shape and literal source ingress; no generation.
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
    let point = [500.,0.,0.,500.,500.,0.,0.,-500.,500.,300.,0.,400.,500.,-300.,0.,-400.];
    let vector = [
        Complex64::default(), Complex64::new(0.8,0.),
        Complex64::new(0.,1.), Complex64::new(-0.6,0.),
    ];
    let result = runtime.evaluate_correlated_with_sources(
        &point, 1, Some(&[u64::MAX]), &[1e6], &[3], &vector, None, None,
    ).unwrap();
    assert_eq!(result.spin_legs_json, "[3]");
    assert!(result.virtual_values.iter().all(|x|x.re.is_finite() && x.im.is_finite()));
    assert_eq!(result.virtual_values.len(), 3);
    drop(runtime);
    assert_eq!(result.spin_legs_json, "[3]");
    println!("PROJECTED_IDENTITY_SDK_PASSED contracted component, no resolved anchors, owned source result");
}
