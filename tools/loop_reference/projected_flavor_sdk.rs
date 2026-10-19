// SPDX-License-Identifier: 0BSD
//! Actual projected identity members, signed resolved axes and owned sources.
use rusticol_loop_sdk::{Complex64, Runtime, SpinSources};
use std::path::Path;

fn close(a: f64, b: f64) {
    assert!((a - b).abs() <= 3e-9 * a.abs().max(b.abs()).max(1.));
}

fn main() {
    let root = std::env::args()
        .nth(1)
        .expect("projected flavour fixture root");
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
    for accuracy in ["lc", "nlc"] {
        let mut mapped = Runtime::open(
            root.join(format!("{accuracy}-ordinary-mapped-artifact")),
            Some("ssgg"),
            None,
            "model",
        )
        .unwrap();
        let mut independent = Runtime::open(
            root.join(format!("{accuracy}-ordinary-independent-artifact")),
            Some("ssgg"),
            None,
            "model",
        )
        .unwrap();
        assert_eq!(mapped.shape(), independent.shape());
        assert_eq!(
            mapped.shape().virtual_color_components,
            if accuracy == "lc" { 3 } else { 1 }
        );
        for resolved in [false, true] {
            let a = mapped
                .evaluate(&point, &[u64::MAX], &[1e6], resolved, None, None)
                .unwrap();
            let b = independent
                .evaluate(&point, &[u64::MAX], &[1e6], resolved, None, None)
                .unwrap();
            assert_eq!(a.shape, b.shape);
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
        }
        let mut mapped = Runtime::open(
            root.join(format!("{accuracy}-spin-mapped-artifact")),
            Some("ssgg"),
            None,
            "model",
        )
        .unwrap();
        let mut independent = Runtime::open(
            root.join(format!("{accuracy}-spin-independent-artifact")),
            Some("ssgg"),
            None,
            "model",
        )
        .unwrap();
        let a = mapped
            .evaluate_correlated_with_sources(
                &point,
                &[u64::MAX],
                &[1e6],
                SpinSources {
                    legs: &[4, 3],
                    values: &values,
                },
                None,
                None,
            )
            .unwrap();
        let b = independent
            .evaluate_correlated_with_sources(
                &point,
                &[u64::MAX],
                &[1e6],
                SpinSources {
                    legs: &[4, 3],
                    values: &values,
                },
                None,
                None,
            )
            .unwrap();
        assert_eq!(a.shape, b.shape);
        assert_eq!(a.born.len(), b.born.len());
        assert_eq!(a.virtual_values.len(), b.virtual_values.len());
        for (x, y) in a
            .born
            .iter()
            .chain(&a.virtual_values)
            .zip(b.born.iter().chain(&b.virtual_values))
        {
            close(x.real, y.real);
            close(x.imag, y.imag);
        }
        mapped.clear();
        drop((mapped, independent));
        assert_eq!(a.successful_point_ids, [u64::MAX]);
        assert_eq!(a.spin_legs, [3, 4]);
    }
    println!(
        "PROJECTED_FLAVOR_SDK_PASS signed axes, independent members, sources and owned results"
    );
}
