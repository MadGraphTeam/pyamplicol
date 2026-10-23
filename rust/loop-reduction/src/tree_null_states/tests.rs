// SPDX-License-Identifier: 0BSD

//! Finite component and program-association checks, not accuracy certificates.

use std::{collections::BTreeMap, sync::Arc};

use feynkit_generator::{GenerationOptions, Process};
use feynkit_graph::ExternalState;
use feynkit_kinematics::{FutureNullMomentum, Helicity, KinematicScalar, ThreeMomentum};
use feynkit_model::Model;
use rusticol_core::color::{ColorRepresentation, evaluate_nc_terms};
use rusticol_core::{RusticolErrorKind, RusticolResult};
use symbolica::{
    atom::{Atom, Symbol},
    domains::{
        float::{DoubleFloat, Float, FloatLike, Real},
        rational::Rational,
    },
    symbol,
};

use crate::{
    Complex,
    runtime::{Arithmetic, Batch, BatchCarrier, Data},
    tree_correlations::{TreeColorInsertion, TreeColorProgram},
    tree_preparation::{RuntimeTreeParameter, TreeFieldClass, TreeParameterDomain, TreeProgram},
    tree_runtime::TreeStateSource,
};

fn scalar_definition() -> serde_json::Value {
    // The same native scalar-contact fixture class as tree_preparation tests.
    // A separate width parameter allows the name ZERO itself to carry mass.
    serde_json::json!({
        "name":"owned-scalar-contact", "restriction":null,
        "orders":[{"name":"SELF","expansion_order":99,"hierarchy":1}],
        "parameters":[
            {"name":"ZERO","lhablock":null,"lhacode":null,"nature":"internal","parameter_type":"real","value":[0.,0.],"expression":null},
            {"name":"g_","lhablock":"SCALAR","lhacode":[1],"nature":"external","parameter_type":"real","value":[1.,0.],"expression":null},
            {"name":"m","lhablock":"SCALAR","lhacode":[2],"nature":"external","parameter_type":"real","value":[4.,0.],"expression":null},
            {"name":"width","lhablock":null,"lhacode":null,"nature":"internal","parameter_type":"real","value":[0.,0.],"expression":null}
        ],
        "particles":[{"pdg_code":100,"name":"s","antiname":"s","spin":1,"color":1,"mass":"m","width":"width","texname":"s","antitexname":"s","charge":0.,"ghost_number":0,"lepton_number":0,"y_charge":0.,"propagating":true,"goldstoneboson":false,"propagator":"s_prop"}],
        "propagators":[{"name":"s_prop","particle":"s","numerator":"1","denominator":"P^2-m^2"}],
        "lorentz_structures":[{"name":"SSSS","spins":[1,1,1,1],"structure":"1"}],
        "couplings":[{"name":"GC1","expression":"g_","orders":[["SELF",1]],"value":[1.,0.]}],
        "vertex_rules":[{"name":"V1","particles":["s","s","s","s"],"color_structures":["1"],"lorentz_structures":["SSSS"],"couplings":[["GC1"]]}],
        "functions":[],"form_factors":[]
    })
}

fn scalar_program(
    definition: serde_json::Value,
    overrides: BTreeMap<Symbol, Atom>,
    runtime: &[RuntimeTreeParameter],
) -> RusticolResult<Arc<TreeProgram>> {
    TreeProgram::prepare_with_runtime_parameters(
        Arc::new(Model::from_json(&definition.to_string()).unwrap()),
        &Process::new(["s", "s"], ["s", "s"]),
        &GenerationOptions::default().threads(1),
        None,
        &overrides,
        TreeFieldClass::SingletScalars,
        runtime,
    )
    .map(Arc::new)
}

fn massless_scalar() -> Arc<TreeProgram> {
    scalar_program(
        scalar_definition(),
        BTreeMap::from([(symbol!("UFO::m"), Atom::Zero)]),
        &[],
    )
    .unwrap()
}

fn qcd(incoming: [&str; 2], outgoing: [&str; 2], runtime_g: bool) -> Arc<TreeProgram> {
    let model = Arc::new(Model::qcd());
    let mut exact = BTreeMap::new();
    if !runtime_g {
        exact.insert(symbol!("UFO::G"), Atom::one());
    }
    for particle in model.particles().iter().filter(|p| p.spin == 2) {
        let mass = model.parameter_by_id(particle.mass).unwrap();
        exact.insert(symbol!(&format!("UFO::{}", mass.name)), Atom::Zero);
    }
    let runtime = if runtime_g {
        vec![RuntimeTreeParameter {
            symbol: symbol!("UFO::G"),
            domain: TreeParameterDomain::Real,
        }]
    } else {
        vec![]
    };
    Arc::new(
        TreeProgram::prepare_with_runtime_parameters(
            model,
            &Process::new(incoming, outgoing),
            &GenerationOptions::default().threads(1),
            None,
            &exact,
            TreeFieldClass::MasslessQcdAndSingletScalars,
            &runtime,
        )
        .unwrap(),
    )
}

fn rational<T: KinematicScalar>(prototype: &T, numerator: i64, denominator: i64) -> T {
    prototype.from_i64(numerator) / prototype.from_i64(denominator)
}

fn keyed_row<T: KinematicScalar>(
    program: &TreeProgram,
    prototype: &T,
    boosted: bool,
) -> Vec<(usize, FutureNullMomentum<T>)> {
    // Rotation of the existing (5,4,0,3) fixture by cos(phi)=3/5,
    // sin(phi)=4/5. The second row has a transverse beta_y=3/5 boost.
    // Both retain s=100, t=-20, u=-80, with exact rational spatial sources.
    let spatial = if boosted {
        [
            [(0, 1), (-15, 4), (5, 1)],
            [(0, 1), (-15, 4), (-5, 1)],
            [(12, 5), (1, 4), (3, 1)],
            [(-12, 5), (-31, 4), (-3, 1)],
        ]
    } else {
        [
            [(0, 1), (0, 1), (5, 1)],
            [(0, 1), (0, 1), (-5, 1)],
            [(12, 5), (16, 5), (3, 1)],
            [(-12, 5), (-16, 5), (-3, 1)],
        ]
    };
    assert_eq!(program.momentum_legs().len(), spatial.len());
    program
        .momentum_legs()
        .iter()
        .copied()
        .zip(spatial)
        .map(|(label, coordinates)| {
            let [x, y, z] = coordinates.map(|(n, d)| rational(prototype, n, d));
            (
                label,
                FutureNullMomentum::from_spatial(ThreeMomentum::new(x, y, z)).unwrap(),
            )
        })
        .collect()
}

fn failure<T>(result: RusticolResult<T>) -> rusticol_core::RusticolError {
    result.err().expect("request must fail explicitly")
}

fn assert_close_values<T: KinematicScalar>(
    actual: &[Complex<T>],
    expected: &[Complex<T>],
    bits: u32,
) {
    assert_eq!(actual.len(), expected.len());
    for (actual, expected) in actual.iter().zip(expected) {
        let guard = if bits == 53 { 16 } else { 32 };
        let tolerance = expected.re.from_usize(2).pow(u64::from(bits - guard)).inv();
        let scale = expected.re.norm() + expected.re.one();
        assert!((actual.re.clone() - expected.re.clone()).norm() < tolerance.clone() * &scale);
        assert!((actual.im.clone() - expected.im.clone()).norm() < tolerance * scale);
    }
}

fn assert_close_batch(actual: &Batch, expected: &Batch) {
    actual.same_rows(expected).unwrap();
    assert_eq!(actual.columns(), expected.columns());
    let bits = actual.precision_bits();
    match (actual.data(), expected.data()) {
        (Data::Double(a), Data::Double(b)) => assert_close_values(a, b, bits),
        (Data::DoubleDouble(a), Data::DoubleDouble(b)) => assert_close_values(a, b, bits),
        (Data::Arbitrary(a), Data::Arbitrary(b)) => assert_close_values(a, b, bits),
        _ => panic!("carrier changed"),
    }
}

#[test]
fn external_null_admission_uses_resolved_exact_mass_including_scalars() {
    let massive = scalar_program(scalar_definition(), BTreeMap::new(), &[]).unwrap();
    assert!(massive.external_states().is_empty());
    assert_eq!(
        failure(massive.future_null_domain()).kind(),
        RusticolErrorKind::UnsupportedRuntimeCapability,
    );
    // The old raw scalar API still admits a massive spectator inventory.
    let raw = Batch::typed(vec![Complex::new(0., 0.); 16], vec![3], 16, 53).unwrap();
    assert!(
        massive
            .evaluator("double", None)
            .unwrap()
            .evaluate_batch(&raw)
            .is_ok()
    );
    assert!(massless_scalar().future_null_domain().is_ok());

    let mut structural_zero = scalar_definition();
    structural_zero["particles"][0]["mass"] = serde_json::json!("ZERO");
    assert!(
        scalar_program(structural_zero.clone(), BTreeMap::new(), &[])
            .unwrap()
            .future_null_domain()
            .is_ok()
    );
    structural_zero["parameters"][0]["value"] = serde_json::json!([3., 0.]);
    assert_eq!(
        failure(
            scalar_program(structural_zero, BTreeMap::new(), &[])
                .unwrap()
                .future_null_domain()
        )
        .kind(),
        RusticolErrorKind::UnsupportedRuntimeCapability
    );

    let mut runtime_zero = scalar_definition();
    runtime_zero["parameters"][2]["value"] = serde_json::json!([0., 0.]);
    let runtime = [RuntimeTreeParameter {
        symbol: symbol!("UFO::m"),
        domain: TreeParameterDomain::Real,
    }];
    let dependent = scalar_program(runtime_zero, BTreeMap::new(), &runtime).unwrap();
    assert_eq!(
        failure(dependent.future_null_domain()).kind(),
        RusticolErrorKind::UnsupportedRuntimeCapability
    );

    // Leave a runtime symbol free; only the exactly vanishing dependent mass
    // is admissible, irrespective of that symbol's stored default.
    let mut identity = scalar_definition();
    identity["parameters"][2]["nature"] = serde_json::json!("internal");
    identity["parameters"][2]["expression"] = serde_json::json!("g_-g_");
    let runtime = [RuntimeTreeParameter {
        symbol: symbol!("UFO::g_"),
        domain: TreeParameterDomain::Real,
    }];
    assert!(
        scalar_program(identity, BTreeMap::new(), &runtime)
            .unwrap()
            .future_null_domain()
            .is_ok()
    );

    let unresolved = scalar_program(
        scalar_definition(),
        BTreeMap::from([(
            symbol!("UFO::m"),
            Atom::var(symbol!("null_fixture::unresolved_mass")),
        )]),
        &[],
    )
    .unwrap();
    assert_eq!(
        failure(unresolved.future_null_domain()).kind(),
        RusticolErrorKind::UnsupportedRuntimeCapability
    );
    // Actual quark, antiquark and vector inventories use the same factory.
    assert!(
        qcd(["u", "u~"], ["g", "g"], false)
            .future_null_domain()
            .is_ok()
    );
}

#[test]
fn binding_canonicalizes_complete_labels_and_rejects_row_or_carrier_ambiguity() {
    let program = massless_scalar();
    let domain = program.future_null_domain().unwrap();
    let canonical = keyed_row(&program, &0_f64, false);
    let mut shuffled = canonical.clone();
    shuffled.rotate_left(1);
    shuffled.reverse();
    let batch = domain
        .bind(vec![41, 7], vec![shuffled, canonical.clone()], 53)
        .unwrap();
    assert_eq!(batch.momenta().ids(), &[41, 7]);
    assert_eq!(batch.momenta().columns(), 16);
    let Data::Double(values) = batch.momenta().data() else {
        panic!("carrier changed")
    };
    for row in 0..2 {
        for (column, (label, owner)) in canonical.iter().enumerate() {
            assert_eq!(batch.leg(row, *label), Some(owner));
            for (component, expected) in owner.as_momentum().components().iter().enumerate() {
                assert_eq!(
                    values[row * 16 + column * 4 + component],
                    Complex::new(**expected, 0.)
                );
            }
        }
    }
    assert!(batch.leg(2, canonical[0].0).is_none());
    assert!(batch.leg(0, usize::MAX).is_none());
    assert!(
        domain
            .bind(
                vec![1],
                Vec::<Vec<(usize, FutureNullMomentum<f64>)>>::new(),
                53
            )
            .is_err()
    );
    assert!(
        domain
            .bind(vec![1, 1], vec![canonical.clone(); 2], 53)
            .is_err()
    );
    let mut missing = canonical.clone();
    missing.pop();
    let mut duplicate = canonical.clone();
    duplicate[1].0 = duplicate[0].0;
    let mut extra = canonical.clone();
    extra.push((usize::MAX, canonical[0].1.clone()));
    let mut foreign = canonical.clone();
    foreign[0].0 = usize::MAX;
    for invalid in [missing, duplicate, extra, foreign] {
        assert!(domain.bind(vec![41], vec![invalid], 53).is_err());
    }
    assert!(domain.bind(vec![41], vec![canonical], 113).is_err());
    assert!(domain.bind::<f64>(vec![], vec![], 113).is_err());
    assert!(domain.bind::<DoubleFloat>(vec![], vec![], 106).is_ok());
    assert!(domain.bind::<DoubleFloat>(vec![], vec![], 113).is_err());
    assert!(domain.bind::<Float>(vec![], vec![], 1).is_err());
    assert!(domain.bind::<Float>(vec![], vec![], 233).is_ok());
}

#[test]
fn program_identity_is_checked_even_for_empty_scalar_batches() {
    let first = massless_scalar();
    let second = massless_scalar();
    assert!(!Arc::ptr_eq(&first, &second));
    assert_eq!(first.momentum_legs(), second.momentum_legs());
    let first_domain = first.future_null_domain().unwrap();
    let cloned_domain = first_domain.clone();
    let second_domain = second.future_null_domain().unwrap();
    let mut evaluator = first_domain
        .evaluator_with_precision_bits(Arithmetic::Double, 53)
        .unwrap();
    for empty in [false, true] {
        let rows = if empty {
            vec![]
        } else {
            vec![keyed_row(&first, &0_f64, false)]
        };
        let ids = if empty { vec![] } else { vec![19] };
        let accepted = cloned_domain.bind(ids.clone(), rows.clone(), 53).unwrap();
        let foreign = second_domain.bind(ids, rows, 53).unwrap();
        let result = evaluator.evaluate_batch(&accepted, None).unwrap();
        assert_eq!(result.rows(), usize::from(!empty));
        assert_eq!(result.columns(), 1);
        assert!(
            evaluator
                .evaluate_coefficients(&accepted, None, &[])
                .is_ok()
        );
        assert!(evaluator.evaluate_batch(&foreign, None).is_err());
        assert!(
            evaluator
                .evaluate_coefficients(&foreign, None, &[])
                .is_err()
        );
        assert!(
            evaluator
                .evaluate_coefficients(&accepted, None, &[1])
                .is_err()
        );
        if !empty {
            let Data::Double(values) = result.data() else {
                panic!("carrier changed")
            };
            assert_eq!(values.as_slice(), &[Complex::new(1., 0.)]);
        }
    }
}

#[test]
fn owned_state_source_checks_the_entire_prepared_four_column_tuple() {
    let program = qcd(["u", "d"], ["u", "d"], false);
    let domain = program.future_null_domain().unwrap();
    let source = domain
        .bind(vec![71], vec![keyed_row(&program, &0_f64, false)], 53)
        .unwrap();
    let empty = domain.bind::<f64>(vec![], vec![], 53).unwrap();
    let state = program.external_states()[0].clone();
    assert!(source.components(&state, state.helicities[0]).is_ok());
    assert!(empty.components(&state, state.helicities[0]).is_ok());
    for column in 0..4 {
        let mut corrupt = state.clone();
        corrupt.momentum_columns[column] = (corrupt.momentum_columns[column] + 4) % 16;
        assert!(source.components(&corrupt, state.helicities[0]).is_err());
        assert!(empty.components(&corrupt, state.helicities[0]).is_err());
    }
    // Matching the first column alone must not identify a native occurrence.
    let mut swapped = state.clone();
    swapped.momentum_columns.swap(1, 2);
    assert!(source.components(&swapped, state.helicities[0]).is_err());
    let mut wrong_role = state.clone();
    wrong_role.kind = "epsilon".into();
    assert!(source.components(&wrong_role, state.helicities[0]).is_err());
    let mut wrong_helicities = state.clone();
    wrong_helicities.helicities = vec![0];
    assert!(source.components(&wrong_helicities, 0).is_err());
}

fn analytic_norm<T: BatchCarrier + KinematicScalar>(
    program: &Arc<TreeProgram>,
    expected: &Rational,
    prototype: T,
    arithmetic: Arithmetic,
    bits: u32,
) {
    let domain = program.future_null_domain().unwrap();
    let mut rows = vec![
        keyed_row(program, &prototype, false),
        keyed_row(program, &prototype, true),
    ];
    rows[1].reverse();
    let source = domain.bind(vec![13, 907], rows, bits).unwrap();
    let mut evaluator = domain
        .evaluator_with_precision_bits(arithmetic, bits)
        .unwrap();
    let output = evaluator.evaluate_batch(&source, None).unwrap();
    let expected = Batch::typed(
        vec![Complex::new(prototype.from_rational(expected), prototype.zero()); 2],
        vec![13, 907],
        1,
        bits,
    )
    .unwrap();
    assert_close_batch(&output, &expected);
    assert!(output.nonfinite_rows().is_empty());
    // The coefficient seam consumes components of the same retained owners.
    // This is a path-association check; the analytic norm above is independent.
    let helicities: Vec<_> = program
        .external_states()
        .iter()
        .enumerate()
        .map(|(i, state)| state.helicities[i % state.helicities.len()])
        .collect();
    let components: Vec<_> = program
        .external_states()
        .iter()
        .zip(&helicities)
        .map(|(state, &helicity)| source.components(state, helicity).unwrap())
        .collect();
    for ((state, &helicity), actual) in program
        .external_states()
        .iter()
        .zip(&helicities)
        .zip(&components)
    {
        let label = program.momentum_legs()[state.momentum_columns[0] / 4];
        let expected = Batch::typed(
            (0..source.momenta().rows())
                .flat_map(|row| {
                    source
                        .leg(row, label)
                        .unwrap()
                        .wavefunction(
                            state.kind.parse().unwrap(),
                            Helicity::try_from(helicity as i8).unwrap(),
                        )
                        .unwrap()
                        .into_components()
                })
                .collect(),
            source.momenta().ids().to_vec(),
            4,
            bits,
        )
        .unwrap();
        assert_close_batch(actual, &expected);
    }
    let owned = evaluator
        .evaluate_coefficients(&source, None, &helicities)
        .unwrap();
    let supplied = program
        .evaluator_with_precision_bits(arithmetic, bits)
        .unwrap()
        .evaluate_external_components(source.momenta(), &components.iter().collect::<Vec<_>>())
        .unwrap();
    assert_close_batch(&owned, &supplied);
}

#[test]
fn owned_qcd_crossings_match_analytic_norms_with_fresh_runtime_width_sources() {
    // PDG 2024 Cross-Section Formulae, Eqs. 51.5, 51.4, 51.10, 51.12:
    // https://pdg.lbl.gov/2024/reviews/rpp2024-rev-cross-section-formulae.pdf
    // Spin/color sums restore initial degeneracies; no symmetry or flux factor.
    let s = Rational::from(100);
    let t = Rational::from(-20);
    let u = Rational::from(-80);
    let cases = [
        (
            ["u", "d"],
            ["u", "d"],
            Rational::from(16) * (s.clone().pow(2) + u.clone().pow(2)) / t.clone().pow(2),
        ),
        (
            ["u", "u~"],
            ["d", "d~"],
            Rational::from(16) * (t.clone().pow(2) + u.clone().pow(2)) / s.clone().pow(2),
        ),
        (
            ["u", "g"],
            ["u", "g"],
            Rational::from(96)
                * ((s.clone().pow(2) + u.clone().pow(2)) / t.clone().pow(2)
                    - Rational::from((4, 9)) * (s.clone().pow(2) + u.clone().pow(2))
                        / (s.clone() * &u)),
        ),
        (
            ["g", "g"],
            ["g", "g"],
            Rational::from(1152)
                * (Rational::from(3)
                    - u.clone() * &t / s.clone().pow(2)
                    - s.clone() * &u / t.clone().pow(2)
                    - s.clone() * &t / u.clone().pow(2)),
        ),
    ];
    for (incoming, outgoing, expected) in cases {
        let program = qcd(incoming, outgoing, false);
        let domain = program.future_null_domain().unwrap();
        let legs: Vec<_> = domain.external_legs().collect();
        assert_eq!(
            legs.iter().map(|(label, _, _)| *label).collect::<Vec<_>>(),
            program.momentum_legs()
        );
        assert_eq!(domain.process(), &Process::new(incoming, outgoing));
        for ((_, particle, role), (name, expected_role)) in legs.into_iter().zip(
            incoming
                .into_iter()
                .map(|name| (name, ExternalState::Incoming))
                .chain(
                    outgoing
                        .into_iter()
                        .map(|name| (name, ExternalState::Outgoing)),
                ),
        ) {
            assert_eq!(domain.model().particle_by_id(particle).unwrap().name, name);
            assert_eq!(role, expected_role);
        }
        analytic_norm(&program, &expected, 0_f64, Arithmetic::Double, 53);
        for bits in [113, 137, 233, 256, 512, 1024] {
            analytic_norm(
                &program,
                &expected,
                Float::with_val(bits, 0),
                Arithmetic::Arbitrary,
                bits,
            );
        }
    }
}

fn delicate<T: KinematicScalar>(prototype: &T, mixed: bool) -> FutureNullMomentum<T> {
    let spatial = if mixed {
        let huge = prototype.from_usize(2).pow(600);
        ThreeMomentum::new(huge.clone().inv(), prototype.zero(), huge)
    } else {
        let delta = prototype.from_usize(2).pow(30).inv();
        ThreeMomentum::new(
            prototype.from_usize(2) * &delta,
            prototype.zero(),
            -prototype.one() + delta.pow(2),
        )
    };
    FutureNullMomentum::from_spatial(spatial).unwrap()
}

#[test]
fn typed_chart_failures_keep_external_label_row_and_attempt_bits() {
    let program = qcd(["u", "d"], ["u", "d"], false);
    let domain = program.future_null_domain().unwrap();
    let state = &program.external_states()[0];
    let label = program.momentum_legs()[state.momentum_columns[0] / 4];
    for mixed in [false, true] {
        let mut low = keyed_row(&program, &0_f64, false);
        low.iter_mut().find(|(id, _)| *id == label).unwrap().1 = delicate(&0_f64, mixed);
        let source = domain
            .bind(
                vec![31, 907],
                vec![keyed_row(&program, &0_f64, false), low],
                53,
            )
            .unwrap();
        let error = failure(source.components(state, state.helicities[0]));
        assert_eq!(
            error.kind(),
            RusticolErrorKind::InsufficientPrecision { bits: 53 }
        );
        assert!(
            error
                .message()
                .contains(&format!("lane 907 (row 1), occurrence {label}:"))
        );
        for bits in [113, 137, 233, 256, 512, 1024] {
            let prototype = Float::with_val(bits, 0);
            let mut row = keyed_row(&program, &prototype, false);
            row.iter_mut().find(|(id, _)| *id == label).unwrap().1 = delicate(&prototype, mixed);
            let source = domain.bind(vec![907], vec![row], bits).unwrap();
            let output = source.components(state, state.helicities[0]).unwrap();
            assert_eq!(output.ids(), &[907]);
            assert_eq!(output.precision_bits(), bits);
            assert!(output.nonfinite_rows().is_empty());
        }
    }
    // Metadata records the attempt, not the lesser tracked precision of an
    // intermediate. Do not pad its precision or silently promote the source.
    let tracked = Float::with_val(53, 0);
    let mut row = keyed_row(&program, &tracked, false);
    row.iter_mut().find(|(id, _)| *id == label).unwrap().1 = delicate(&tracked, false);
    let source = domain.bind(vec![1021], vec![row], 137).unwrap();
    let error = failure(source.components(state, state.helicities[0]));
    assert_eq!(
        error.kind(),
        RusticolErrorKind::InsufficientPrecision { bits: 137 }
    );
    assert!(
        error
            .message()
            .contains(&format!("lane 1021 (row 0), occurrence {label}:"))
    );
}

#[test]
fn runtime_parameters_preserve_typed_rows_and_sub_binary64_couplings() {
    let program = qcd(["u", "d"], ["u", "d"], true);
    let domain = program.future_null_domain().unwrap();
    let bits = 137;
    let p = Float::with_val(bits, 0);
    let source = domain
        .bind(vec![29, 11], vec![keyed_row(&program, &p, false); 2], bits)
        .unwrap();
    let first = p.one();
    let second = p.one() + Float::with_val(bits, 2).pow(90).inv();
    let parameters = Batch::typed(
        vec![
            Complex::new(first.clone(), p.zero()),
            Complex::new(second.clone(), p.zero()),
        ],
        vec![29, 11],
        1,
        bits,
    )
    .unwrap();
    let mut evaluator = domain
        .evaluator_with_precision_bits(Arithmetic::Arbitrary, bits)
        .unwrap();
    assert!(evaluator.evaluate_batch(&source, None).is_err());
    let result = evaluator
        .evaluate_batch(&source, Some(&parameters))
        .unwrap();
    let expected = Batch::typed(
        [first, second]
            .into_iter()
            .map(|g| Complex::new(Float::with_val(bits, 656) * g.pow(4), p.zero()))
            .collect(),
        vec![29, 11],
        1,
        bits,
    )
    .unwrap();
    assert_close_batch(&result, &expected);
    let Data::Arbitrary(values) = result.data() else {
        panic!("carrier changed")
    };
    assert!(values[1].re > values[0].re);
    assert!(
        evaluator
            .evaluate_batch(
                &source,
                Some(&parameters.take_rows(vec![1, 0], None).unwrap())
            )
            .is_err()
    );
    let complex = Batch::typed(
        vec![Complex::new(p.one(), p.one()); 2],
        vec![29, 11],
        1,
        bits,
    )
    .unwrap();
    assert!(evaluator.evaluate_batch(&source, Some(&complex)).is_err());
    let mismatch = domain
        .evaluator_with_precision_bits(Arithmetic::Arbitrary, 233)
        .unwrap()
        .evaluate_batch(&source, Some(&parameters));
    assert!(mismatch.is_err());
}

fn color_requests(program: &TreeProgram) -> Vec<TreeColorInsertion> {
    let legs = program.color_tensors()[0].legs();
    let [a, b, c] = std::array::from_fn(|i| legs[i].label);
    let mut requests = vec![TreeColorInsertion::Identity];
    // Two anchors include fundamental and adjoint Casimirs in the QCD fixture.
    for anchor in &legs[..2] {
        requests.extend(legs.iter().map(|leg| TreeColorInsertion::Pair {
            left: anchor.label,
            right: leg.label,
        }));
    }
    requests.extend([
        TreeColorInsertion::OrderedProduct(vec![[a, b], [b, c]]),
        TreeColorInsertion::OrderedProduct(vec![[b, c], [a, b]]),
        TreeColorInsertion::Anticommutator {
            first: [a, b],
            second: [b, c],
        },
        TreeColorInsertion::StructureConstantTripole {
            first: a,
            second: b,
            third: c,
        },
    ]);
    requests
}

fn check_color_conservation<T: KinematicScalar>(
    values: &[Complex<T>],
    columns: usize,
    legs: &[rusticol_core::color::ColorLeg],
    bits: u32,
) {
    for row in values.chunks_exact(columns) {
        let identity = &row[0];
        assert!(identity.re > identity.re.zero());
        for (anchor_index, anchor) in legs[..2].iter().enumerate() {
            let casimir = match anchor.representation {
                ColorRepresentation::Adjoint => Rational::from(3),
                _ => Rational::from((4, 3)),
            };
            let expected =
                identity * &Complex::new(identity.re.from_rational(&casimir), identity.re.zero());
            let start = 1 + anchor_index * legs.len();
            assert_close_values(
                &row[start + anchor_index..start + anchor_index + 1],
                std::slice::from_ref(&expected),
                bits,
            );
            let sum = row[start..start + legs.len()]
                .iter()
                .enumerate()
                .filter(|(index, _)| *index != anchor_index)
                .fold(
                    Complex::new(identity.re.zero(), identity.re.zero()),
                    |sum, (_, value)| sum + value,
                );
            // Sum of all distinct spectators = -C_i times the identity.
            assert_close_values(&[sum], &[-expected], bits);
        }
    }
}

fn owned_color_paths<T: BatchCarrier + KinematicScalar>(
    program: &Arc<TreeProgram>,
    color: &TreeColorProgram,
    prototype: T,
    arithmetic: Arithmetic,
    bits: u32,
) {
    let domain = program.future_null_domain().unwrap();
    let exact_row = program
        .momentum_legs()
        .iter()
        .copied()
        .zip([[0, 0, 5], [0, 0, -5], [4, 0, 3], [-4, 0, -3]])
        .map(|(label, [x, y, z])| {
            (
                label,
                FutureNullMomentum::from_spatial(ThreeMomentum::new(
                    prototype.from_i64(x),
                    prototype.from_i64(y),
                    prototype.from_i64(z),
                ))
                .unwrap(),
            )
        })
        .collect();
    let exact = domain.bind(vec![81], vec![exact_row], bits).unwrap();
    let helicities: Vec<_> = program
        .external_states()
        .iter()
        .map(|state| state.helicities[0])
        .collect();
    let mut evaluator = color
        .evaluator_with_precision_bits(arithmetic, bits)
        .unwrap();
    let owned_fixed = evaluator
        .evaluate_future_null_fixed_helicities(&exact, None, &helicities)
        .unwrap();
    let raw_fixed = evaluator
        .evaluate_fixed_helicities(exact.momenta(), &helicities)
        .unwrap();
    assert_close_batch(&owned_fixed, &raw_fixed);
    let owned_sum = evaluator.evaluate_future_null_batch(&exact, None).unwrap();
    let raw_sum = evaluator.evaluate_batch(exact.momenta()).unwrap();
    assert_close_batch(&owned_sum, &raw_sum);

    let nonaxis = domain
        .bind(
            vec![13, 907],
            vec![
                keyed_row(program, &prototype, false),
                keyed_row(program, &prototype, true),
            ],
            bits,
        )
        .unwrap();
    for output in [
        evaluator
            .evaluate_future_null_fixed_helicities(&nonaxis, None, &helicities)
            .unwrap(),
        evaluator
            .evaluate_future_null_batch(&nonaxis, None)
            .unwrap(),
    ] {
        let legs = program.color_tensors()[0].legs();
        match output.data() {
            Data::Double(v) => check_color_conservation(v, output.columns(), legs, bits),
            Data::DoubleDouble(v) => check_color_conservation(v, output.columns(), legs, bits),
            Data::Arbitrary(v) => check_color_conservation(v, output.columns(), legs, bits),
        }
    }

    // Existing directed supplied-component probe, not a new admitted physical
    // spin/source API: phase one ket block by i and retain i times every output.
    // The unphased blocks and momenta come from these same bound owners.
    let components: Vec<_> = program
        .external_states()
        .iter()
        .zip(&helicities)
        .map(|(state, &helicity)| exact.components(state, helicity).unwrap())
        .collect();
    let phase = |batch: &Batch| -> Batch {
        fn rotate<T: BatchCarrier>(values: &[Complex<T>], batch: &Batch) -> Batch {
            Batch::typed(
                values
                    .iter()
                    .map(|z| Complex::new(-z.im.clone(), z.re.clone()))
                    .collect(),
                batch.ids().to_vec(),
                batch.columns(),
                batch.precision_bits(),
            )
            .unwrap()
        }
        match batch.data() {
            Data::Double(v) => rotate(v, batch),
            Data::DoubleDouble(v) => rotate(v, batch),
            Data::Arbitrary(v) => rotate(v, batch),
        }
    };
    let mut ket = components.clone();
    ket[0] = phase(&ket[0]);
    let directed = evaluator
        .evaluate_external_components(
            exact.momenta(),
            &components.iter().collect::<Vec<_>>(),
            &ket.iter().collect::<Vec<_>>(),
        )
        .unwrap();
    assert_close_batch(&directed, &phase(&owned_fixed));
    let ordered_column = 1 + 2 * program.color_tensors()[0].legs().len();
    match directed.data() {
        Data::Double(v) => assert_ne!(v[ordered_column].im, 0.),
        Data::DoubleDouble(v) => assert_ne!(v[ordered_column].im, v[ordered_column].im.zero()),
        Data::Arbitrary(v) => assert_ne!(v[ordered_column].im, v[ordered_column].im.zero()),
    }
}

#[test]
fn owned_color_insertions_reuse_raw_contractions_and_obey_independent_color_identities() {
    let tree = qcd(["u", "g"], ["u", "g"], false);
    let color = TreeColorProgram::prepare(tree.clone(), color_requests(&tree)).unwrap();
    // Use the existing exact insertion matrix. Verify the chosen ordered probe
    // really is non-Hermitian; no duplicate operator or color-network oracle.
    let ordered_column = 1 + 2 * tree.color_tensors()[0].legs().len();
    let matrix = color.matrix_nc_terms(ordered_column).unwrap();
    assert!((0..matrix.len()).any(|i| (0..matrix.len()).any(|j| {
        evaluate_nc_terms(&matrix[i][j], 3).unwrap()
            != evaluate_nc_terms(&matrix[j][i], 3).unwrap().conj()
    })));
    owned_color_paths(&tree, &color, 0_f64, Arithmetic::Double, 53);
    for bits in [113, 137, 233, 256, 512, 1024] {
        owned_color_paths(
            &tree,
            &color,
            Float::with_val(bits, 0),
            Arithmetic::Arbitrary,
            bits,
        );
    }
}

#[test]
fn owned_color_empty_batches_still_validate_program_parameters_precision_and_helicities() {
    let tree = qcd(["u", "d"], ["u", "d"], true);
    let other = qcd(["u", "d"], ["u", "d"], true);
    let domain = tree.future_null_domain().unwrap();
    let foreign_domain = other.future_null_domain().unwrap();
    let color =
        TreeColorProgram::prepare(tree.clone(), vec![TreeColorInsertion::Identity]).unwrap();
    let bits = 137;
    let empty = domain.bind::<Float>(vec![], vec![], bits).unwrap();
    let foreign = foreign_domain.bind::<Float>(vec![], vec![], bits).unwrap();
    let parameters = Batch::typed::<Float>(vec![], vec![], 1, bits).unwrap();
    let helicities: Vec<_> = tree
        .external_states()
        .iter()
        .map(|state| state.helicities[0])
        .collect();
    let mut evaluator = color
        .evaluator_with_precision_bits(Arithmetic::Arbitrary, bits)
        .unwrap();
    let valid = evaluator
        .evaluate_future_null_batch(&empty, Some(&parameters))
        .unwrap();
    assert_eq!(
        (valid.rows(), valid.columns(), valid.precision_bits()),
        (0, 1, bits)
    );
    assert!(
        evaluator
            .evaluate_future_null_fixed_helicities(&empty, Some(&parameters), &helicities)
            .is_ok()
    );
    assert!(
        evaluator
            .evaluate_future_null_batch(&foreign, Some(&parameters))
            .is_err()
    );
    assert!(
        evaluator
            .evaluate_future_null_fixed_helicities(&foreign, Some(&parameters), &helicities)
            .is_err()
    );
    let malformed = [
        None,
        Some(Batch::typed::<Float>(vec![], vec![], 0, bits).unwrap()),
        Some(Batch::typed::<Float>(vec![], vec![], 2, bits).unwrap()),
        Some(Batch::typed::<Float>(vec![], vec![], 1, 233).unwrap()),
        // Batch is the raw parameter boundary: an empty wrong carrier with
        // matching bit metadata must still be rejected before evaluation.
        Some(Batch::typed::<f64>(vec![], vec![], 1, bits).unwrap()),
        Some(
            Batch::typed(
                vec![Complex::new(
                    Float::with_val(bits, 1),
                    Float::with_val(bits, 0),
                )],
                vec![7],
                1,
                bits,
            )
            .unwrap(),
        ),
    ];
    for parameters in malformed {
        assert!(
            evaluator
                .evaluate_future_null_batch(&empty, parameters.as_ref())
                .is_err()
        );
        assert!(
            evaluator
                .evaluate_future_null_fixed_helicities(&empty, parameters.as_ref(), &helicities)
                .is_err()
        );
    }
    let wrong_source = domain.bind::<Float>(vec![], vec![], 233).unwrap();
    assert!(
        evaluator
            .evaluate_future_null_batch(&wrong_source, Some(&parameters))
            .is_err()
    );
    assert!(
        evaluator
            .evaluate_future_null_fixed_helicities(&wrong_source, Some(&parameters), &helicities)
            .is_err()
    );
    let wrong_carrier = domain.bind::<f64>(vec![], vec![], 53).unwrap();
    assert!(
        evaluator
            .evaluate_future_null_batch(&wrong_carrier, Some(&parameters))
            .is_err()
    );
    assert!(
        evaluator
            .evaluate_future_null_fixed_helicities(&wrong_carrier, Some(&parameters), &helicities)
            .is_err()
    );
    let float53 = domain.bind::<Float>(vec![], vec![], 53).unwrap();
    let parameters53 = Batch::typed::<f64>(vec![], vec![], 1, 53).unwrap();
    let mut double = color
        .evaluator_with_precision_bits(Arithmetic::Double, 53)
        .unwrap();
    assert!(
        double
            .evaluate_future_null_batch(&float53, Some(&parameters53))
            .is_err()
    );
    assert!(
        double
            .evaluate_future_null_fixed_helicities(&float53, Some(&parameters53), &helicities)
            .is_err()
    );
    assert!(
        evaluator
            .evaluate_future_null_fixed_helicities(&empty, Some(&parameters), &[])
            .is_err()
    );
    let mut wrong_helicity = helicities;
    wrong_helicity[0] = 0;
    assert!(
        evaluator
            .evaluate_future_null_fixed_helicities(&empty, Some(&parameters), &wrong_helicity)
            .is_err()
    );
}
