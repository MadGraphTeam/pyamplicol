// SPDX-License-Identifier: 0BSD

//! Analytical graph-level tests. These are bare off-shell scalar Green
//! functions, not UV-renormalized amplitudes or NSC finite remainders.

use super::{ScalarLoopProgram, coherent_sum};
use crate::runtime::{Arithmetic, Batch, Data};
use feynkit_generator::{GenerationFilter, GenerationOptions, Process};
use feynkit_model::Model;
use std::{collections::BTreeMap, sync::Arc};
use symbolica::{
    domains::float::{Complex, Float, Real},
    parse, symbol,
};

fn scalar_definition(arity: usize) -> serde_json::Value {
    serde_json::json!({
        "name":"scalar-loop-analytical-fixture", "restriction":null,
        "orders":[{"name":"SELF","expansion_order":99,"hierarchy":1}],
        "parameters":[
            {"name":"ZERO","lhablock":null,"lhacode":null,"nature":"internal","parameter_type":"real","value":[0.0,0.0],"expression":null},
            {"name":"g_","lhablock":"SCALAR","lhacode":[1],"nature":"external","parameter_type":"complex","value":[1.0,0.0],"expression":null},
            {"name":"m","lhablock":"SCALAR","lhacode":[2],"nature":"external","parameter_type":"real","value":[2.0,0.0],"expression":null}
        ],
        "particles":[{"pdg_code":100,"name":"s","antiname":"s","spin":1,"color":1,"mass":"m","width":"ZERO","texname":"s","antitexname":"s","charge":0.0,"ghost_number":0,"lepton_number":0,"y_charge":0,"propagating":true,"goldstoneboson":false,"propagator":"s_prop"}],
        "propagators":[{"name":"s_prop","particle":"s","numerator":"1","denominator":"P^2-m^2"}],
        "lorentz_structures":[{"name":"SCALAR","spins":vec![1;arity],"structure":"1"}],
        "couplings":[{"name":"GC1","expression":"g_","orders":[["SELF",1]],"value":[1.0,0.0]}],
        "vertex_rules":[{"name":"V1","particles":vec!["s";arity],"color_structures":["1"],"lorentz_structures":["SCALAR"],"couplings":[["GC1"]]}],
        "functions":[],"form_factors":[]
    })
}

fn scalar_model(arity: usize) -> Arc<Model> {
    Arc::new(Model::from_json(&scalar_definition(arity).to_string()).unwrap())
}

fn two_point_process() -> Process {
    Process::new(["s"], ["s"])
}

fn bubble_options() -> GenerationOptions {
    GenerationOptions::default()
        .threads(1)
        .with_graph_filter(GenerationFilter::LoopOneParticleIrreducible)
}

fn two_point_momenta(program: &ScalarLoopProgram, energies: &[f64], ids: &[u64]) -> Batch {
    assert_eq!(program.momentum_legs().len(), 2);
    let values = energies
        .iter()
        .flat_map(|&energy| {
            program
                .momentum_legs()
                .iter()
                .flat_map(move |_| [energy, 0.0, 0.0, 0.0])
        })
        .map(|value| Complex::new(value, 0.0))
        .collect();
    Batch::typed(values, ids.to_vec(), 8, 53).unwrap()
}

fn double_scale(value: f64, ids: &[u64]) -> Batch {
    Batch::typed(
        vec![Complex::new(value, 0.0); ids.len()],
        ids.to_vec(),
        1,
        53,
    )
    .unwrap()
}

#[test]
fn malformed_native_batches_fail_without_reusing_a_successful_result() {
    let program = ScalarLoopProgram::prepare(
        scalar_model(4),
        &two_point_process(),
        &GenerationOptions::default().threads(1),
        None,
        &BTreeMap::new(),
    )
    .unwrap();
    let mut evaluator = program.evaluator("double", None).unwrap();
    let momenta = two_point_momenta(&program, &[1.0], &[42]);
    let valid = evaluator
        .evaluate_batch(&momenta, &double_scale(4.0, &[42]))
        .unwrap();
    assert_eq!(valid.successful_values().ids(), &[42]);
    for scale in [0.0, -1.0, f64::INFINITY, f64::NAN] {
        assert!(
            evaluator
                .evaluate_batch(&momenta, &double_scale(scale, &[42]))
                .is_err()
        );
    }
    assert!(
        evaluator
            .evaluate_batch(&momenta, &double_scale(4.0, &[99]))
            .is_err()
    );
    let duplicates = two_point_momenta(&program, &[1.0, 2.0], &[42, 42]);
    assert!(
        evaluator
            .evaluate_batch(&duplicates, &double_scale(4.0, &[42, 42]))
            .is_err()
    );
    let nonfinite = two_point_momenta(&program, &[f64::NAN], &[42]);
    assert!(
        evaluator
            .evaluate_batch(&nonfinite, &double_scale(4.0, &[42]))
            .is_err()
    );
    let mut complex_values = vec![Complex::new(1.0, 0.0); 8];
    complex_values[0].im = 1.0;
    let complex = Batch::typed(complex_values, vec![42], 8, 53).unwrap();
    assert!(
        evaluator
            .evaluate_batch(&complex, &double_scale(4.0, &[42]))
            .is_err()
    );
    let recovered = evaluator
        .evaluate_batch(&momenta, &double_scale(4.0, &[42]))
        .unwrap();
    assert_eq!(
        valid.successful_values().to_decimal(),
        recovered.successful_values().to_decimal()
    );
}

fn assert_double_close(actual: &Complex<f64>, expected: Complex<f64>) {
    assert!(
        (actual.re - expected.re).abs() < 5e-12,
        "{actual} != {expected}"
    );
    assert!(
        (actual.im - expected.im).abs() < 5e-12,
        "{actual} != {expected}"
    );
}

#[test]
fn massive_tadpole_retains_its_symmetry_factor_and_complex_amplitude() {
    let program = ScalarLoopProgram::prepare(
        scalar_model(4),
        &two_point_process(),
        &GenerationOptions::default().threads(1),
        None,
        &BTreeMap::from([(symbol!("UFO::g_"), parse!("2+3i"))]),
    )
    .unwrap();
    assert_eq!(program.diagram_count(), 1, "self-loops must be enabled");
    let momenta = two_point_momenta(&program, &[1.0], &[11]);
    let result = program
        .evaluator("double", None)
        .unwrap()
        .evaluate_batch(&momenta, &double_scale(4.0, &[11]))
        .unwrap();
    assert_eq!(result.statuses(), &[(11, "success".to_owned())]);
    let values = result.successful_values();
    assert_eq!(values.ids(), &[11]);
    assert_eq!(values.columns(), 3);
    let Data::Double(values) = values.data() else {
        panic!("carrier changed")
    };
    // A0(m²) = m² [1/eps + 1 - ln(m²/mu²)] in the reducer's
    // rGamma-normalized convention. The graph has coefficient g/2 and
    // the public bare convention multiplies by i/(16 pi²), once.
    let denominator = 16.0 * std::f64::consts::PI.powi(2);
    let expected = Complex::new(-6.0 / denominator, 4.0 / denominator);
    assert_double_close(&values[0], expected);
    assert_double_close(&values[1], expected);
    assert_double_close(&values[2], Complex::new(0.0, 0.0));
}

#[test]
fn distinct_mass_tadpoles_are_summed_as_complex_amplitudes() {
    let mut definition = scalar_definition(4);
    let mut external = definition["particles"][0].clone();
    external["name"] = serde_json::json!("x");
    external["antiname"] = serde_json::json!("x");
    external["pdg_code"] = serde_json::json!(101);
    external["mass"] = serde_json::json!("ZERO");
    external["propagator"] = serde_json::json!("x_prop");
    let mut second = definition["particles"][0].clone();
    second["name"] = serde_json::json!("t");
    second["antiname"] = serde_json::json!("t");
    second["pdg_code"] = serde_json::json!(102);
    second["mass"] = serde_json::json!("n");
    second["propagator"] = serde_json::json!("t_prop");
    definition["particles"]
        .as_array_mut()
        .unwrap()
        .extend([external, second]);
    definition["parameters"].as_array_mut().unwrap().extend([
        serde_json::json!({"name":"n","lhablock":"SCALAR","lhacode":[3],"nature":"external","parameter_type":"real","value":[3.0,0.0],"expression":null}),
        serde_json::json!({"name":"h","lhablock":"SCALAR","lhacode":[4],"nature":"external","parameter_type":"complex","value":[1.0,0.0],"expression":null})
    ]);
    definition["propagators"].as_array_mut().unwrap().extend([
        serde_json::json!({"name":"x_prop","particle":"x","numerator":"1","denominator":"P^2"}),
        serde_json::json!({"name":"t_prop","particle":"t","numerator":"1","denominator":"P^2-n^2"}),
    ]);
    definition["vertex_rules"][0]["particles"] = serde_json::json!(["x", "x", "s", "s"]);
    definition["couplings"].as_array_mut().unwrap().push(
        serde_json::json!({"name":"GC2","expression":"h","orders":[["SELF",1]],"value":[1.0,0.0]}),
    );
    definition["vertex_rules"].as_array_mut().unwrap().push(
        serde_json::json!({"name":"V2","particles":["x","x","t","t"],"color_structures":["1"],"lorentz_structures":["SCALAR"],"couplings":[["GC2"]]})
    );
    let program = ScalarLoopProgram::prepare(
        Arc::new(Model::from_json(&definition.to_string()).unwrap()),
        &Process::new(["x"], ["x"]),
        &GenerationOptions::default().threads(1),
        None,
        &BTreeMap::from([
            (symbol!("UFO::g_"), parse!("2+3i")),
            (symbol!("UFO::h"), parse!("-1+2i")),
        ]),
    )
    .unwrap();
    assert_eq!(program.diagram_count(), 2);
    let result = program
        .evaluator("double", None)
        .unwrap()
        .evaluate_batch(
            &two_point_momenta(&program, &[1.0], &[17]),
            &double_scale(4.0, &[17]),
        )
        .unwrap();
    assert_eq!(result.statuses(), &[(17, "success".to_owned())]);
    let Data::Double(values) = result.successful_values().data() else {
        panic!("carrier changed")
    };
    let finite_second = 9.0 * (1.0 - (9.0_f64 / 4.0).ln());
    let normalization = 32.0 * std::f64::consts::PI.powi(2);
    assert_double_close(
        &values[0],
        Complex::new(
            -(12.0 + 2.0 * finite_second) / normalization,
            (8.0 - finite_second) / normalization,
        ),
    );
    assert_double_close(
        &values[1],
        Complex::new(-30.0 / normalization, -1.0 / normalization),
    );
    assert_double_close(&values[2], Complex::new(0.0, 0.0));
}

#[test]
fn massive_bubble_has_the_analytical_laurent_coefficients() {
    let program = ScalarLoopProgram::prepare(
        scalar_model(3),
        &two_point_process(),
        &bubble_options(),
        None,
        &BTreeMap::new(),
    )
    .unwrap();
    assert_eq!(program.diagram_count(), 1);
    let result = program
        .evaluator("double", None)
        .unwrap()
        .evaluate_batch(
            &two_point_momenta(&program, &[2.0], &[23]),
            &double_scale(4.0, &[23]),
        )
        .unwrap();
    assert_eq!(result.statuses(), &[(23, "success".to_owned())]);
    let Data::Double(values) = result.successful_values().data() else {
        panic!("carrier changed")
    };
    // B0(m²;m²,m²) = 1/eps + 2 - pi/sqrt(3) at mu²=m².
    let normalization = 32.0 * std::f64::consts::PI.powi(2);
    assert_double_close(
        &values[0],
        Complex::new(
            0.0,
            (2.0 - std::f64::consts::PI / 3.0_f64.sqrt()) / normalization,
        ),
    );
    assert_double_close(&values[1], Complex::new(0.0, 1.0 / normalization));
    assert_double_close(&values[2], Complex::new(0.0, 0.0));
}

#[test]
fn zero_flow_tadpole_bridge_is_retained_with_its_denominator() {
    let program = ScalarLoopProgram::prepare(
        scalar_model(3),
        &two_point_process(),
        &GenerationOptions::default().threads(1),
        None,
        &BTreeMap::new(),
    )
    .unwrap();
    assert_eq!(
        program.diagram_count(),
        2,
        "bubble and tadpole attachment must both survive"
    );
    let result = program
        .evaluator("double", None)
        .unwrap()
        .evaluate_batch(
            &two_point_momenta(&program, &[2.0], &[31]),
            &double_scale(4.0, &[31]),
        )
        .unwrap();
    assert_eq!(result.statuses(), &[(31, "success".to_owned())]);
    let Data::Double(values) = result.successful_values().data() else {
        panic!("carrier changed")
    };
    // The zero-flow bridge is 1/(-m²). Thus the sum is
    // i/[32 pi²] [B0(p²;m²,m²) - A0(m²)/m²], without another
    // symmetry factor or absolute square. This cancellation is fixture algebra.
    let normalization = 32.0 * std::f64::consts::PI.powi(2);
    assert_double_close(
        &values[0],
        Complex::new(
            0.0,
            (1.0 - std::f64::consts::PI / 3.0_f64.sqrt()) / normalization,
        ),
    );
    assert_double_close(&values[1], Complex::new(0.0, 0.0));
    assert_double_close(&values[2], Complex::new(0.0, 0.0));
}

#[test]
fn arbitrary_precision_retains_a_sub_binary64_momentum_increment() {
    let program = ScalarLoopProgram::prepare(
        scalar_model(3),
        &two_point_process(),
        &bubble_options(),
        None,
        &BTreeMap::new(),
    )
    .unwrap();
    let bits = 173;
    let zero = Float::with_val(bits, 0);
    let one = Float::with_val(bits, 1);
    let delta = one.clone() / Float::parse("1208925819614629174706176", Some(bits)).unwrap();
    let energies = [one.clone(), one + delta];
    let mut values = Vec::new();
    for energy in &energies {
        for _ in program.momentum_legs() {
            values.push(Complex::new(energy.clone(), zero.clone()));
            values.extend(vec![Complex::new(zero.clone(), zero.clone()); 3]);
        }
    }
    let momenta = Batch::typed(values, vec![41, 42], 8, bits).unwrap();
    let scales = Batch::typed(
        vec![Complex::new(Float::with_val(bits, 4), zero.clone()); 2],
        vec![41, 42],
        1,
        bits,
    )
    .unwrap();
    let result = program
        .evaluator_with_precision_bits(Arithmetic::Arbitrary, bits)
        .unwrap()
        .evaluate_batch(&momenta, &scales)
        .unwrap();
    assert_eq!(
        result.statuses(),
        &[(41, "success".to_owned()), (42, "success".to_owned())]
    );
    let Data::Arbitrary(values) = result.successful_values().data() else {
        panic!("AP carrier changed")
    };
    // Below threshold, d B0 / d p² = integral_0^1 dx x(1-x)/
    // [m²-x(1-x)p²] > 0. The tiny input change must reach the finite
    // amplitude; casting momenta or masters through binary64 erases it.
    let difference = values[3].im.clone() - values[0].im.clone();
    assert!(
        difference > Float::parse("1e-32", Some(bits)).unwrap(),
        "increment was lost: {difference}"
    );
    assert!(
        difference < Float::parse("1e-24", Some(bits)).unwrap(),
        "unexpected increment: {difference}"
    );
    assert_eq!(values[1], values[4], "the UV pole is momentum independent");
    assert_eq!(values[2], values[5]);

    let rounded = two_point_momenta(&program, &[1.0, 1.0], &[41, 42]);
    let result = program
        .evaluator("double", None)
        .unwrap()
        .evaluate_batch(&rounded, &double_scale(4.0, &[41, 42]))
        .unwrap();
    let Data::Double(values) = result.successful_values().data() else {
        panic!("double carrier changed")
    };
    assert_eq!(values[0], values[3]);
}

#[test]
fn a_low_precision_first_lane_does_not_set_other_lanes_normalization() {
    let bits = 256;
    let low_zero = Float::with_val(8, 0);
    let high_zero = Float::with_val(bits, 0);
    let one = Float::with_val(bits, 1);
    let delta = one.clone() / Float::parse("1208925819614629174706176", Some(bits)).unwrap();
    let finite = Complex::new(one.clone() + delta, Float::with_val(bits, 2));
    let single = Complex::new(Float::with_val(bits, 3), Float::with_val(bits, 4));
    let double = Complex::new(Float::with_val(bits, 5), Float::with_val(bits, 6));
    let mut part = vec![Complex::new(low_zero.clone(), low_zero); 3];
    part.extend([finite.clone(), single.clone(), double.clone()]);
    let result = coherent_sum(&[part.as_slice()], vec![71, 72], bits).unwrap();
    assert_eq!(result.ids(), &[71, 72]);
    assert_eq!(result.precision_bits(), bits);
    let Data::Arbitrary(values) = result.data() else {
        panic!("AP carrier changed")
    };

    let pi = high_zero.pi();
    let factor = one / (Float::with_val(bits, 16) * pi.clone() * pi);
    let tolerance = Float::parse("1e-65", Some(bits)).unwrap();
    for (actual, input) in values[3..].iter().zip([finite, single, double]) {
        let expected = Complex::new(-input.im * factor.clone(), input.re * factor.clone());
        for residual in [
            actual.re.clone() - expected.re,
            actual.im.clone() - expected.im,
        ] {
            assert!(
                residual > -tolerance.clone(),
                "normalization lost precision: {residual}"
            );
            assert!(
                residual < tolerance,
                "normalization lost precision: {residual}"
            );
        }
    }
}

#[test]
fn derivative_propagator_numerators_and_custom_poles_are_rejected() {
    for (numerator, denominator, expected) in [
        ("P^2", "P^2-m^2", "momentum-independent"),
        ("1", "2*(P^2-m^2)", "canonical zero-width"),
        ("1", "(P^2-m^2)^2", "canonical zero-width"),
    ] {
        let mut definition = scalar_definition(4);
        definition["propagators"][0]["numerator"] = serde_json::json!(numerator);
        definition["propagators"][0]["denominator"] = serde_json::json!(denominator);
        let result = ScalarLoopProgram::prepare(
            Arc::new(Model::from_json(&definition.to_string()).unwrap()),
            &two_point_process(),
            &GenerationOptions::default().threads(1),
            None,
            &BTreeMap::new(),
        );
        let message = result
            .err()
            .expect("must reject unsupported structure")
            .to_string();
        assert!(message.contains(expected), "{message}");
    }
}

#[test]
fn a_two_point_insertion_does_not_silently_drop_repeated_loop_poles() {
    let mut definition = scalar_definition(4);
    definition["lorentz_structures"]
        .as_array_mut()
        .unwrap()
        .push(serde_json::json!({"name":"SCALAR2","spins":[1,1],"structure":"1"}));
    definition["vertex_rules"].as_array_mut().unwrap().push(
        serde_json::json!({"name":"V2","particles":["s","s"],"color_structures":["1"],"lorentz_structures":["SCALAR2"],"couplings":[["GC1"]]})
    );
    // Exact order two and a two-vertex cap isolate one quartic vertex plus
    // one two-point insertion; no unbounded series of mass insertions is made.
    let options =
        bubble_options()
            .max_vertices(2)
            .with_graph_filter(GenerationFilter::CouplingOrders(BTreeMap::from([(
                "SELF".to_owned(),
                (2, Some(2)),
            )])));
    let result = ScalarLoopProgram::prepare(
        Arc::new(Model::from_json(&definition.to_string()).unwrap()),
        &two_point_process(),
        &options,
        None,
        &BTreeMap::new(),
    );
    let message = result
        .err()
        .expect("must reject repeated poles")
        .to_string();
    assert!(message.contains("repeated loop propagators"), "{message}");
}

#[test]
fn an_ordinary_nonzero_parameter_named_zero_keeps_its_mass() {
    let mut definition = scalar_definition(4);
    definition["parameters"][0]["name"] = serde_json::json!("VACZERO");
    definition["parameters"][2]["name"] = serde_json::json!("ZERO");
    definition["particles"][0]["mass"] = serde_json::json!("ZERO");
    definition["particles"][0]["width"] = serde_json::json!("VACZERO");
    definition["propagators"][0]["denominator"] = serde_json::json!("P^2-ZERO^2");
    let program = ScalarLoopProgram::prepare(
        Arc::new(Model::from_json(&definition.to_string()).unwrap()),
        &two_point_process(),
        &GenerationOptions::default().threads(1),
        None,
        &BTreeMap::new(),
    )
    .unwrap();
    let result = program
        .evaluator("double", None)
        .unwrap()
        .evaluate_batch(
            &two_point_momenta(&program, &[1.0], &[59]),
            &double_scale(4.0, &[59]),
        )
        .unwrap();
    assert_eq!(result.statuses(), &[(59, "success".to_owned())]);
    let Data::Double(values) = result.successful_values().data() else {
        panic!("carrier changed")
    };
    let expected = Complex::new(0.0, 1.0 / (8.0 * std::f64::consts::PI.powi(2)));
    assert_double_close(&values[0], expected);
    assert_double_close(&values[1], expected);
    assert_double_close(&values[2], Complex::new(0.0, 0.0));
}
