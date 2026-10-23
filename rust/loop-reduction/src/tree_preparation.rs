// SPDX-License-Identifier: 0BSD

//! Fresh native scalar tree preparation using FeynKit's existing amplitude
//! generator, coherent square and Idenso tensor contraction. The result feeds
//! the existing precision-generic coefficient runtime, without source code
//! generation, Python preparation or a second numerical amplitude engine.
//!
//! Initial admitted class: every generated internal/external particle must be
//! a color-singlet scalar. Unsupported participating fields are rejected, never
//! dropped. This is a preparation stepping stone, not a complete QCD provider.

use std::{collections::BTreeMap, sync::Arc};

use feynkit_amplitude::AmplitudeOptions;
use feynkit_generator::{GenerationOptions, NumeratorGrouping, Process};
use feynkit_model::{Model, ParameterCard, ParameterType, Particle};
use idenso::tensor::{AlgebraSettings, ContractSettings};
use rusticol_core::{RusticolError, RusticolResult, preparation::encode_exact_evaluator_state};
use spenso::{
    network::{library::function_lib::INBUILTS, tags::SPENSO_TAG},
    structure::representation::{Minkowski, RepName},
};
use symbolica::{
    atom::{Atom, AtomCore, AtomView, Symbol},
    coefficient::CoefficientView,
    symbol,
};

use crate::runtime::{Arithmetic, CoefficientEvaluator};

/// Immutable instructions for one coherent tree norm. External momenta are
/// physical incoming/outgoing momenta, in the FeynKit external-leg label order
/// returned by [`Self::momentum_legs`], each with components `(E,px,py,pz)`.
/// The Minkowski metric is +---. Inputs are unaveraged and unsymmetrized; scalar
/// color/spin averages are one. Flux and identical-particle phase-space factors
/// belong to the consumer.
pub struct ScalarTreeProgram {
    momentum_legs: Vec<usize>,
    diagram_count: usize,
    evaluator_state: Vec<u8>,
}

fn error(message: impl std::fmt::Display) -> RusticolError {
    RusticolError::invalid_argument(format!("native scalar tree preparation: {message}"))
}

fn bind_scalars(expression: &Atom, bindings: &BTreeMap<Symbol, Atom>) -> Atom {
    expression.replace_map(|term, _, out| {
        if let AtomView::Var(var) = term {
            if let Some(value) = bindings.get(&var.get_symbol()) {
                **out = value.clone();
            }
        }
    })
}

// FeynKit's amplitude denominator currently represents only p²-m², while the
// model permits arbitrary denominator templates. Check the exact specialization
// before allowing that representation to replace a participating propagator.
fn validate_scalar_pole(
    model: &Model,
    particle: &Particle,
    bindings: &BTreeMap<Symbol, Atom>,
) -> RusticolResult<()> {
    let unsupported = || {
        RusticolError::unsupported_runtime_capability(
            "native-scalar-tree",
            format!(
                "particle {:?} requires a canonical zero-width vacuum propagator p^2-m^2; custom denominators and medium-dependent poles are unsupported",
                particle.name
            ),
        )
    };
    let (id, _) = model
        .particle_propagator(particle)
        .map_err(error)?
        .ok_or_else(unsupported)?;
    let propagator = model.propagator_by_id(id).map_err(error)?;
    let owner = model.particle_by_id(propagator.particle).map_err(error)?;
    for field in [particle, owner] {
        for id in Some(field.width)
            .into_iter()
            .chain(field.chemical_potential)
        {
            let parameter = model.parameter_by_id(id).map_err(error)?;
            if !bindings
                .get(&symbol!(&format!("UFO::{}", parameter.name)))
                .is_some_and(|value| value.expand().is_zero())
            {
                return Err(unsupported());
            }
        }
    }
    let mass = bind_scalars(&particle.symbolic_mass(model), bindings);
    let denominator = bind_scalars(&propagator.denominator, bindings);
    let p = symbol!("UFO::P");
    let idx = symbol!("UFO::idx");
    let momenta = [Atom::var(p), p.call_args([idx.call_args([1i64, 1i64])])];
    if !momenta.iter().any(|momentum| {
        (&denominator - (momentum.clone().pow(2) - mass.clone().pow(2)))
            .expand()
            .is_zero()
    }) {
        return Err(unsupported());
    }
    Ok(())
}

impl ScalarTreeProgram {
    /// Prepare a new process from the in-memory model and exact parameter
    /// overrides. Model/card numeric defaults retain their binary64 values as
    /// exact rationals; extra precision requires exact overrides. Pass any
    /// restriction card explicitly, including for an already restricted model.
    ///
    /// Graph selection/veto filters are honored. The loop range is fixed to
    /// zero, and external symmetrization/numerator grouping are disabled so the
    /// coherent square retains each labelled diagram. Overrides must name model
    /// parameters and respect their declared reality and structural zeros.
    /// Unresolved symbols or unsupported scalar functions fail preparation.
    /// Participating internal poles must be canonical zero-width vacuum poles;
    /// FeynKit's amplitude path does not yet preserve arbitrary denominators.
    pub fn prepare(
        model: Arc<Model>,
        process: &Process,
        options: &GenerationOptions,
        card: Option<&ParameterCard>,
        exact_overrides: &BTreeMap<Symbol, Atom>,
    ) -> RusticolResult<Self> {
        for key in exact_overrides.keys() {
            if !model
                .parameters()
                .iter()
                .any(|parameter| *key == symbol!(&format!("UFO::{}", parameter.name)))
            {
                return Err(error(format!(
                    "override {key} does not name a model parameter"
                )));
            }
        }
        let scalar_bindings = model
            .scalar_bindings(card, exact_overrides)
            .map_err(error)?;
        for (key, binding) in &scalar_bindings {
            let mut approximate = false;
            let _ = binding.replace_map(|term, _, _| {
                if let AtomView::Num(number) = term {
                    approximate |= matches!(number.get_coeff_view(), CoefficientView::Float(_, _));
                }
            });
            if approximate {
                return Err(error(format!(
                    "scalar binding {key} must use exact atoms, not floating coefficients"
                )));
            }
        }
        let options = options
            .clone()
            .with_loop_count(0, 0)
            .map_err(error)?
            .symmetrize_initial(false)
            .symmetrize_final(false)
            .symmetrize_left_right(false)
            .symmetrize_external_fermions(false)
            .numerator_grouping(NumeratorGrouping::None);
        let generated = process.generate_diagrams(model, &options).map_err(error)?;
        for diagram in &generated.diagrams {
            for (_, _, edge) in diagram.edges() {
                let particle = diagram
                    .model()
                    .particle_by_id(edge.particle)
                    .map_err(error)?;
                if particle.spin != 1 || particle.color != 1 {
                    return Err(RusticolError::unsupported_runtime_capability(
                        "native-scalar-tree",
                        format!(
                            "participating field {:?} has spin {} and color {}; only color-singlet scalars are currently admitted",
                            particle.name, particle.spin, particle.color
                        ),
                    ));
                }
                if edge.external.is_none() && !edge.is_dummy {
                    validate_scalar_pole(diagram.model(), particle, &scalar_bindings)?;
                }
            }
        }
        let amplitude = generated
            .into_amplitude(AmplitudeOptions::default())
            .map_err(error)?;
        let physical_expression = amplitude.expression().map_err(error)?;
        for parameter in amplitude.model().parameters() {
            let variable = symbol!(&format!("UFO::{}", parameter.name));
            if parameter.parameter_type == ParameterType::Real
                && physical_expression
                    .expression()
                    .contains(Atom::var(variable))
            {
                if let Some(value) = scalar_bindings.get(&variable) {
                    if !value.is_real().is_true() {
                        return Err(error(format!(
                            "parameter {} must have a provably real binding",
                            parameter.name
                        )));
                    }
                }
            }
        }
        let momentum_legs: Vec<_> = amplitude.legs().iter().map(|leg| leg.index).collect();
        let squared = amplitude.squared().map_err(error)?;
        let contracted = squared
            .expression()
            .simplify_algebra(&AlgebraSettings::default())
            .map_err(error)?
            .contract(ContractSettings::default())
            .map_err(error)?;
        let mut expression = contracted.expression().clone();
        // Literal symbol replacement avoids treating trailing underscores in
        // model parameter names as wildcard patterns.
        expression = bind_scalars(&expression, &scalar_bindings);
        // Idenso leaves scalar adjoints in Spenso's symbolic wrapper. Once
        // scalar values are bound, use Symbolica's ordinary scalar conjugation.
        expression = expression.replace_map(|term, _, out| {
            if let AtomView::Fun(function) = term {
                if function.get_symbol() == INBUILTS.conj && function.get_nargs() == 1 {
                    **out = function.iter().next().unwrap().conj();
                }
            }
        });
        let momenta: BTreeMap<_, _> = amplitude
            .legs()
            .iter()
            .map(|leg| {
                (
                    Minkowski {}.new_rep(4).vector(leg.momentum().as_view(), []),
                    leg.index,
                )
            })
            .collect();
        let mut inputs = Vec::new();
        let mut components = BTreeMap::new();
        for &leg in &momentum_legs {
            let row: Vec<_> = (0..4)
                .map(|mu| Atom::var(symbol!(&format!("rusticol_native_tree::p_{leg}_{mu}"))))
                .collect();
            if row.iter().any(|value| expression.contains(value)) {
                return Err(error("model uses a reserved momentum input symbol"));
            }
            inputs.extend(row.iter().cloned());
            components.insert(leg, row);
        }
        expression = expression.replace_map(|term, _, out| {
            let AtomView::Fun(function) = term else {
                return;
            };
            if function.get_symbol() != SPENSO_TAG.dot {
                return;
            }
            let args: Vec<_> = function.iter().collect();
            if args.len() != 2 {
                return;
            }
            let (Some(left), Some(right)) = (
                momenta.get(&Atom::from(args[0])),
                momenta.get(&Atom::from(args[1])),
            ) else {
                return;
            };
            let (left, right) = (&components[left], &components[right]);
            **out = &left[0] * &right[0]
                - &left[1] * &right[1]
                - &left[2] * &right[2]
                - &left[3] * &right[3];
        });
        let exact = Atom::evaluator_multiple(&[expression], &inputs)
            .cores(1)
            .build()
            .map_err(error)?;
        Ok(Self {
            momentum_legs,
            diagram_count: amplitude.diagrams().len(),
            evaluator_state: encode_exact_evaluator_state(&exact)?,
        })
    }

    pub fn momentum_legs(&self) -> &[usize] {
        &self.momentum_legs
    }
    pub fn diagram_count(&self) -> usize {
        self.diagram_count
    }
    pub fn evaluator_state(&self) -> &[u8] {
        &self.evaluator_state
    }

    /// Select binary64, double-double, or arbitrary decimal precision in the
    /// existing coefficient runtime. Batches remain typed in their carrier.
    /// This is an unchecked coefficient evaluator: the caller must supply real,
    /// finite physical momenta and verify finite outputs before interpreting a
    /// result as a coherent norm. It does not validate the physical domain,
    /// on-shell conditions or momentum conservation.
    pub fn evaluator(
        &self,
        arithmetic: &str,
        decimal_digits: Option<u32>,
    ) -> RusticolResult<CoefficientEvaluator> {
        CoefficientEvaluator::new(&self.evaluator_state, arithmetic, decimal_digits).map_err(error)
    }

    /// Use an explicit initial working precision, including 113-bit Float.
    /// This does not add guard bits or recover accuracy already lost in inputs.
    /// The physical-domain requirements of [`Self::evaluator`] also apply.
    pub fn evaluator_with_precision_bits(
        &self,
        arithmetic: Arithmetic,
        bits: u32,
    ) -> RusticolResult<CoefficientEvaluator> {
        CoefficientEvaluator::with_precision_bits(&self.evaluator_state, arithmetic, bits)
            .map_err(error)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::runtime::{Batch, Data};
    use symbolica::{
        domains::float::{Complex, Float},
        parse,
    };

    fn scalar_model_definition(arity: usize) -> serde_json::Value {
        let mut model = serde_json::json!({
            "name":"scalar-contact", "restriction":null,
            "orders":[{"name":"SELF","expansion_order":99,"hierarchy":1}],
            "parameters":[
                {"name":"ZERO","lhablock":null,"lhacode":null,"nature":"internal","parameter_type":"real","value":[0.0,0.0],"expression":null},
                {"name":"g_","lhablock":"SCALAR","lhacode":[1],"nature":"external","parameter_type":"real","value":[1.0,0.0],"expression":null},
                {"name":"m","lhablock":"SCALAR","lhacode":[2],"nature":"external","parameter_type":"real","value":[4.0,0.0],"expression":null}
            ],
            "particles":[{"pdg_code":100,"name":"s","antiname":"s","spin":1,"color":1,"mass":"m","width":"ZERO","texname":"s","antitexname":"s","charge":0.0,"ghost_number":0,"lepton_number":0,"y_charge":0,"propagating":true,"goldstoneboson":false,"propagator":"s_prop"}],
            "propagators":[{"name":"s_prop","particle":"s","numerator":"1","denominator":"P^2-m^2"}],
            "lorentz_structures":[{"name":"SSSS","spins":[1,1,1,1],"structure":"1"}],
            "couplings":[{"name":"GC1","expression":"g_","orders":[["SELF",1]],"value":[1.0,0.0]}],
            "vertex_rules":[{"name":"V1","particles":["s","s","s","s"],"color_structures":["1"],"lorentz_structures":["SSSS"],"couplings":[["GC1"]]}],
            "functions":[],"form_factors":[]
        });
        model["lorentz_structures"][0]["spins"] = serde_json::json!(vec![1; arity]);
        model["vertex_rules"][0]["particles"] = serde_json::json!(vec!["s"; arity]);
        model
    }

    fn scalar_model(arity: usize) -> Model {
        Model::from_json(&scalar_model_definition(arity).to_string()).unwrap()
    }

    #[test]
    fn fresh_scalar_contact_runs_in_double_and_arbitrary_without_codegen() {
        let model = scalar_model(4);
        let overrides =
            BTreeMap::from([(symbol!("UFO::g_"), parse!("1+1/1208925819614629174706176"))]);
        let program = ScalarTreeProgram::prepare(
            Arc::new(model),
            &Process::new(["s", "s"], ["s", "s"]),
            &GenerationOptions::default().threads(1),
            None,
            &overrides,
        )
        .unwrap();
        assert_eq!(program.diagram_count(), 1);
        assert_eq!(program.momentum_legs().len(), 4);
        let mut double = program.evaluator("double", None).unwrap();
        let batch = Batch::typed(vec![Complex::new(0.0, 0.0); 16], vec![41], 16, 53).unwrap();
        let out = double.evaluate_batch(&batch).unwrap();
        let Data::Double(values) = out.data() else {
            panic!("carrier changed")
        };
        assert!((values[0].re - 1.0).abs() < 1e-14, "{}", values[0]);
        let mut high = program
            .evaluator_with_precision_bits(Arithmetic::Arbitrary, 233)
            .unwrap();
        let bits = high.precision_bits();
        let batch = Batch::typed(
            vec![Complex::new(Float::with_val(bits, 0), Float::with_val(bits, 0)); 16],
            vec![41],
            16,
            bits,
        )
        .unwrap();
        let out = high.evaluate_batch(&batch).unwrap();
        let Data::Arbitrary(values) = out.data() else {
            panic!("carrier changed")
        };
        assert!(
            values[0].re > Float::with_val(bits, 1),
            "exact sub-binary64 parameter must survive"
        );
        let exact_coupling = Float::with_val(bits, 1) + Float::with_val(bits, 2.0_f64.powi(-80));
        let expected = exact_coupling.clone() * exact_coupling;
        let residual = values[0].re.clone() - expected;
        assert!(residual > Float::with_val(bits, -1e-65));
        assert!(residual < Float::with_val(bits, 1e-65));
        assert_eq!(values[0].im, Float::with_val(bits, 0));
    }

    #[test]
    fn fresh_cubic_tree_keeps_all_channel_interferences() {
        let model = scalar_model(3);
        let program = ScalarTreeProgram::prepare(
            Arc::new(model),
            &Process::new(["s", "s"], ["s", "s"]),
            &GenerationOptions::default()
                .threads(1)
                .symmetrize_initial(true)
                .symmetrize_final(true),
            None,
            &BTreeMap::new(),
        )
        .unwrap();
        assert_eq!(program.diagram_count(), 3);
        let momenta = [
            5., 0., 0., 3., 5., 0., 0., -3., 5., 3., 0., 0., 5., -3., 0., 0.,
        ];
        let input = Batch::typed(
            momenta.into_iter().map(|re| Complex::new(re, 0.)).collect(),
            vec![7],
            16,
            53,
        )
        .unwrap();
        let output = program
            .evaluator("double", None)
            .unwrap()
            .evaluate_batch(&input)
            .unwrap();
        let Data::Double(values) = output.data() else {
            panic!("carrier changed")
        };
        // m=4, s=100,t=u=-18: |1/84-2/34|². Unlike massless
        // phi³ 2→2, the channel interferences do not accidentally sum to zero.
        let coherent = (1.0_f64 / 84.0 - 2.0 / 34.0).powi(2);
        let incoherent = 1.0_f64 / 84.0_f64.powi(2) + 2.0 / 34.0_f64.powi(2);
        assert!((values[0].re - coherent).abs() < 1e-14, "{}", values[0]);
        assert!((values[0].re - incoherent).abs() > 1e-4);
        assert!(values[0].im.abs() < 1e-13);
    }

    #[test]
    fn invalid_parameter_specializations_fail_before_preparation() {
        let model = Arc::new(scalar_model(4));
        for (key, value, expected) in [
            (
                symbol!("UFO::g_"),
                Atom::num(Float::with_val(53, 1.25)),
                "exact atoms",
            ),
            (symbol!("UFO::g_"), Atom::i(), "provably real"),
            (symbol!("UFO::ZERO"), Atom::num(1), "structural-zero"),
            (symbol!("UFO::GC1"), Atom::num(2), "model parameter"),
        ] {
            let result = ScalarTreeProgram::prepare(
                model.clone(),
                &Process::new(["s", "s"], ["s", "s"]),
                &GenerationOptions::default().threads(1),
                None,
                &BTreeMap::from([(key, value)]),
            );
            let message = result.err().expect("must reject binding").to_string();
            assert!(message.contains(expected), "{message}");
        }
    }

    #[test]
    fn complex_parameter_binding_preserves_the_scalar_adjoint() {
        let mut definition = scalar_model_definition(4);
        definition["parameters"][1]["parameter_type"] = serde_json::json!("complex");
        let model = Model::from_json(&definition.to_string()).unwrap();
        let program = ScalarTreeProgram::prepare(
            Arc::new(model),
            &Process::new(["s", "s"], ["s", "s"]),
            &GenerationOptions::default().threads(1),
            None,
            &BTreeMap::from([(symbol!("UFO::g_"), Atom::num(1) + Atom::num(2) * Atom::i())]),
        )
        .unwrap();
        let input = Batch::typed(vec![Complex::new(0.0, 0.0); 16], vec![9], 16, 53).unwrap();
        let output = program
            .evaluator("double", None)
            .unwrap()
            .evaluate_batch(&input)
            .unwrap();
        let Data::Double(values) = output.data() else {
            panic!("carrier changed")
        };
        assert_eq!(values.as_slice(), &[Complex::new(5.0, 0.0)]);
    }

    #[test]
    fn real_underscore_parameter_does_not_remove_an_unrelated_adjoint() {
        let mut definition = scalar_model_definition(4);
        definition["parameters"]
            .as_array_mut()
            .unwrap()
            .push(serde_json::json!({
                "name":"h", "lhablock":"SCALAR", "lhacode":[3],
                "nature":"external", "parameter_type":"complex",
                "value":[1.0,2.0], "expression":null
            }));
        definition["couplings"][0]["expression"] = serde_json::json!("h");
        let model = Model::from_json(&definition.to_string()).unwrap();
        let program = ScalarTreeProgram::prepare(
            Arc::new(model),
            &Process::new(["s", "s"], ["s", "s"]),
            &GenerationOptions::default().threads(1),
            None,
            &BTreeMap::new(),
        )
        .unwrap();
        let input = Batch::typed(vec![Complex::new(0.0, 0.0); 16], vec![11], 16, 53).unwrap();
        let output = program
            .evaluator("double", None)
            .unwrap()
            .evaluate_batch(&input)
            .unwrap();
        let Data::Double(values) = output.data() else {
            panic!("carrier changed")
        };
        assert_eq!(values.as_slice(), &[Complex::new(5.0, 0.0)]);
    }

    #[test]
    fn participating_vector_fields_are_explicitly_unsupported() {
        let mut definition = scalar_model_definition(4);
        definition["particles"][0]["spin"] = serde_json::json!(3);
        definition["lorentz_structures"][0]["spins"] = serde_json::json!([3, 3, 3, 3]);
        let model = Model::from_json(&definition.to_string()).unwrap();
        let result = ScalarTreeProgram::prepare(
            Arc::new(model),
            &Process::new(["s", "s"], ["s", "s"]),
            &GenerationOptions::default().threads(1),
            None,
            &BTreeMap::new(),
        );
        assert!(
            result
                .err()
                .expect("must reject participating vector")
                .to_string()
                .contains("only color-singlet scalars")
        );
    }

    #[test]
    fn nonzero_mass_named_zero_is_not_silently_massless() {
        let mut definition = scalar_model_definition(3);
        definition["parameters"][0]["name"] = serde_json::json!("VACZERO");
        definition["parameters"][2]["name"] = serde_json::json!("ZERO");
        definition["particles"][0]["mass"] = serde_json::json!("ZERO");
        definition["particles"][0]["width"] = serde_json::json!("VACZERO");
        definition["propagators"][0]["denominator"] = serde_json::json!("P^2-ZERO^2");
        let model = Model::from_json(&definition.to_string()).unwrap();
        let program = ScalarTreeProgram::prepare(
            Arc::new(model),
            &Process::new(["s", "s"], ["s", "s"]),
            &GenerationOptions::default().threads(1),
            None,
            &BTreeMap::new(),
        )
        .unwrap();
        let momenta = [
            5., 0., 0., 3., 5., 0., 0., -3., 5., 3., 0., 0., 5., -3., 0., 0.,
        ];
        let input = Batch::typed(
            momenta
                .into_iter()
                .map(|value| Complex::new(value, 0.0))
                .collect(),
            vec![15],
            16,
            53,
        )
        .unwrap();
        let output = program
            .evaluator("double", None)
            .unwrap()
            .evaluate_batch(&input)
            .unwrap();
        let Data::Double(values) = output.data() else {
            panic!("carrier changed")
        };
        let expected = (1.0_f64 / 84.0 - 2.0 / 34.0).powi(2);
        assert!((values[0].re - expected).abs() < 1e-14, "{}", values[0]);
    }

    #[test]
    fn custom_poles_widths_and_chemical_potentials_are_explicitly_unsupported() {
        for mutation in 0..3 {
            let mut definition = scalar_model_definition(3);
            match mutation {
                0 => definition["propagators"][0]["denominator"] = serde_json::json!("2*(P^2-m^2)"),
                1 => definition["particles"][0]["width"] = serde_json::json!("g_"),
                _ => definition["particles"][0]["chemical_potential"] = serde_json::json!("g_"),
            }
            let model = Model::from_json(&definition.to_string()).unwrap();
            let result = ScalarTreeProgram::prepare(
                Arc::new(model),
                &Process::new(["s", "s"], ["s", "s"]),
                &GenerationOptions::default().threads(1),
                None,
                &BTreeMap::new(),
            );
            let message = result
                .err()
                .expect("must reject unrepresented pole")
                .to_string();
            assert!(
                message.contains("canonical zero-width vacuum propagator"),
                "{message}"
            );
        }
    }
}
