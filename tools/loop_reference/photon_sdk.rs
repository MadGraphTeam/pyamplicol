// SPDX-License-Identifier: 0BSD
// Link against the built safe SDK rlib; argument: fresh u ubar -> photon gluon artifact.
use rusticol_loop_sdk::{Complex64, Runtime, SpinSources};

fn main() {
    let path = std::env::args().nth(1).expect("photon artifact path");
    let mut runtime = Runtime::open(path, None, None, "model").unwrap();
    assert!(runtime.spin_correlation_classes().contains(&vec![3, 4]));
    let point = [
        500., 0., 0., 500., 500., 0., 0., -500., 500., 300., 0., 400., 500., -300., 0., -400.,
    ];
    let vector = vec![
        Complex64 {
            real: 0.1,
            imag: 0.2,
        },
        Complex64 {
            real: 0.8,
            imag: -0.3,
        },
        Complex64 {
            real: 0.4,
            imag: 1.,
        },
        Complex64 {
            real: -0.6,
            imag: 0.5,
        },
    ];
    let doubled = vector
        .iter()
        .map(|v| Complex64 {
            real: 2. * v.real,
            imag: 2. * v.imag,
        })
        .collect::<Vec<_>>();
    let base = runtime
        .evaluate_correlated_with_sources(
            &point,
            &[91],
            &[1e6],
            SpinSources {
                legs: &[3],
                values: &vector,
            },
            None,
            None,
        )
        .unwrap();
    let scaled = runtime
        .evaluate_correlated_with_sources(
            &point,
            &[7],
            &[1e6],
            SpinSources {
                legs: &[3],
                values: &doubled,
            },
            None,
            None,
        )
        .unwrap();
    for (a, b) in base.virtual_values.iter().zip(&scaled.virtual_values) {
        let size = a.real.abs().max(a.imag.abs()).max(1.);
        assert!((b.real - 4. * a.real).abs() < 1e-8 * size);
        assert!((b.imag - 4. * a.imag).abs() < 1e-8 * size);
    }
    assert!(
        runtime
            .evaluate_correlated_with_sources(
                &point,
                &[0],
                &[1e6],
                SpinSources {
                    legs: &[2],
                    values: &vector
                },
                None,
                None,
            )
            .is_err()
    );
    runtime.clear();
    drop(runtime);
    drop(vector);
    assert_eq!(base.successful_point_ids, [91]);
    assert_eq!(base.spin_legs, [3]);
    assert!(base.born[0].real > 0.);
    println!("new-schema photon SDK loading, literal source homogeneity and ownership passed");
}
