// SPDX-License-Identifier: 0BSD
//! Explicit ordinary Bose members retain separate representative capabilities.
use rusticol_loop_sdk::Runtime;
use std::path::Path;

fn close(a: f64, b: f64) {
    assert!((a - b).abs() <= 3e-9 * a.abs().max(b.abs()).max(1.));
}

fn main() {
    let root = std::env::args().nth(1).expect("Bose fixture root");
    let root = Path::new(&root);
    let point = [
        500., 0., 0., 500., 500., 0., 0., -500., 500., 300., 0., 400., 500., -300., 0., -400.,
    ];
    for mode in ["ordinary", "spin"] {
        let path = root.join(format!("{mode}-artifact"));
        let mut member = Runtime::open(&path, Some("ssgg-swap"), None, "model").unwrap();
        let representative = Runtime::open(&path, Some("ddgg"), None, "model").unwrap();
        let mut independent = Runtime::open(
            root.join("independent-artifact"),
            Some("ssgg"),
            None,
            "model",
        )
        .unwrap();
        assert_eq!(member.shape().resolved_available, 0);
        assert!(member.correlation_history_ids().is_empty());
        assert!(member.spin_correlation_classes().is_empty());
        if mode == "ordinary" {
            assert_eq!(representative.shape().resolved_available, 1);
        } else {
            assert!(!representative.correlation_history_ids().is_empty());
            assert!(!representative.spin_correlation_classes().is_empty());
        }
        let a = member
            .evaluate(&point, &[u64::MAX], &[1e6], false, None, None)
            .unwrap();
        let b = independent
            .evaluate(&point, &[u64::MAX], &[1e6], false, None, None)
            .unwrap();
        assert_eq!(a.requested_point_ids, [u64::MAX]);
        assert_eq!(a.successful_point_ids, [u64::MAX]);
        assert_eq!(a.shape.external_count, b.shape.external_count);
        assert_eq!(a.shape.born_orders, b.shape.born_orders);
        assert_eq!(a.shape.virtual_orders, b.shape.virtual_orders);
        assert_eq!(a.born.len(), b.born.len());
        assert_eq!(a.virtual_values.len(), b.virtual_values.len());
        for (&x, &y) in a
            .born
            .iter()
            .chain(&a.virtual_values)
            .zip(b.born.iter().chain(&b.virtual_values))
        {
            close(x, y);
        }
        assert!(
            member
                .evaluate(&point, &[u64::MAX], &[1e6], true, None, None)
                .is_err()
        );
        assert!(
            member
                .evaluate_correlated(&point, &[u64::MAX], &[1e6], None, None)
                .is_err()
        );
        member.clear();
        drop(member);
        assert_eq!(a.successful_point_ids, [u64::MAX]);
        assert_eq!(a.virtual_values.len(), 3);
    }
    println!("BOSE_TRANSPORT_SDK_PASS member values, opaque IDs, capabilities and owned results");
}
