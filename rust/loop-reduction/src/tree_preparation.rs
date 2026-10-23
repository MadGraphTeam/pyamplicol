// SPDX-License-Identifier: 0BSD

//! Fresh native tree preparation using FeynKit's existing amplitude
//! generator, exact color separation and Spenso tensor contraction. The result feeds
//! the existing precision-generic coefficient runtime, without source code
//! generation, Python preparation or a second numerical amplitude engine.
//!
//! Explicitly admitted classes share one generator, amplitude coefficient and
//! numerical instruction path. Unsupported participating fields are rejected,
//! never dropped.

use std::{
    collections::{BTreeMap, BTreeSet},
    sync::Arc,
};

use feynkit_amplitude::AmplitudeOptions;
use feynkit_generator::{
    FilterScope, GenerationFilter, GenerationOptions, NumeratorGrouping, Process,
};
use feynkit_graph::ExternalState;
use feynkit_model::{Model, ParameterCard, ParameterType, Particle};
use idenso::{representations::Bispinor, tensor::SymbolicTensor};
use rusticol_core::{
    RusticolError, RusticolResult,
    color::{ColorLeg, ColorRepresentation, ConnectedColorTensor},
    preparation::encode_exact_evaluator_state,
};
use spenso::structure::{
    representation::{Minkowski, RepName},
    slot::{DualSlotTo, IsAbstractSlot, ParseableAind},
};
use symbolica::{
    atom::{Atom, AtomCore, AtomView, Symbol, SymbolAttribute, SymbolBuilder},
    coefficient::CoefficientView,
    function, symbol,
};

pub use crate::tree_runtime::{ExternalTreeState, TreeEvaluator, TreeParameterDomain};
use crate::{
    runtime::{Arithmetic, arithmetic_mode},
    tree_color::{factor_tree_color, index_label},
    tree_components::{TreeComponentVector, contract_tree_state_components},
    tree_norm::hermitian_norm,
};

/// Immutable instructions for coherent tree amplitudes and their color norm.
/// Complex coefficients retain the complete color and external-state dependence.
/// External momenta are
/// physical incoming/outgoing momenta, in the FeynKit external-leg label order
/// returned by [`Self::momentum_legs`], each with components `(E,px,py,pz)`.
/// The Minkowski metric is +---. Inputs are unaveraged and unsymmetrized.
/// Flux, initial spin/color averages and identical-particle phase-space factors
/// belong to the consumer.
pub struct TreeProgram {
    field_class: TreeFieldClass,
    momentum_legs: Vec<usize>,
    diagram_count: usize,
    evaluator_state: Vec<u8>,
    norm_state: Vec<u8>,
    scalar_norm_state: Option<Vec<u8>>,
    states: Vec<ExternalTreeState>,
    runtime_parameters: Vec<RuntimeTreeParameter>,
    color_tensors: Vec<ConnectedColorTensor>,
}

/// Singlet-scalar entry point delegating to the common amplitude preparation.
/// Its existing evaluation methods remain available through [`TreeProgram`].
pub struct ScalarTreeProgram(TreeProgram);

impl ScalarTreeProgram {
    pub fn prepare(
        model: Arc<Model>,
        process: &Process,
        options: &GenerationOptions,
        card: Option<&ParameterCard>,
        exact_overrides: &BTreeMap<Symbol, Atom>,
    ) -> RusticolResult<Self> {
        TreeProgram::prepare(
            model,
            process,
            options,
            card,
            exact_overrides,
            TreeFieldClass::SingletScalars,
        )
        .map(Self)
    }

    /// Preserve the scalar entry point's exact norm instructions. Inputs are
    /// physical momentum components, with one coherent scalar-norm output.
    pub fn evaluator_state(&self) -> &[u8] {
        self.0
            .scalar_norm_state
            .as_deref()
            .expect("scalar class prepared its norm")
    }
}

impl std::ops::Deref for ScalarTreeProgram {
    type Target = TreeProgram;

    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

/// Structural field domains certified by native preparation. Lorentz/color
/// structures must also reduce to supported scalar instructions.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TreeFieldClass {
    SingletScalars,
    /// Singlet scalars, massless Dirac (anti)fundamental quarks, and massless
    /// adjoint vectors. Majorana fields, ghosts and exotic color are rejected.
    MasslessQcdAndSingletScalars,
}

/// One model parameter retained as a numerical input. Column order is explicit;
/// analytic dependent parameters/couplings are resolved by the native model.
#[derive(Clone, Debug)]
pub struct RuntimeTreeParameter {
    pub symbol: Symbol,
    pub domain: TreeParameterDomain,
}

fn error(message: impl std::fmt::Display) -> RusticolError {
    RusticolError::invalid_argument(format!("native tree preparation: {message}"))
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

fn validate_order_filter(model: &Model, options: &GenerationOptions) -> RusticolResult<()> {
    if !options.filters(FilterScope::Graph).iter().any(
        |filter| matches!(filter, GenerationFilter::CouplingOrders(orders) if !orders.is_empty()),
    ) {
        return Ok(());
    }
    // FeynKit currently labels a vertex by componentwise maximum orders. Exact
    // filtering of mixed vertices requires upstream termwise order projection.
    for vertex in model.vertex_rules() {
        let mut expected = None;
        for &id in vertex.couplings.iter().flatten().flatten() {
            let orders: BTreeMap<_, _> = model
                .coupling_by_id(id)
                .map_err(error)?
                .orders
                .iter()
                .filter(|(_, power)| **power != 0)
                .map(|(name, &power)| (name.clone(), power))
                .collect();
            if expected
                .as_ref()
                .is_some_and(|previous| previous != &orders)
            {
                return Err(RusticolError::unsupported_runtime_capability(
                    "native-tree-orders",
                    format!(
                        "vertex {} mixes coupling-order vectors; order-filtered preparation requires homogeneous vertex orders",
                        vertex.name
                    ),
                ));
            }
            expected = Some(orders);
        }
    }
    Ok(())
}

// FeynKit's amplitude denominator currently represents only p²-m², while the
// model permits arbitrary denominator templates. Check the exact specialization
// before allowing that representation to replace a participating propagator.
fn validate_canonical_pole(
    model: &Model,
    particle: &Particle,
    bindings: &BTreeMap<Symbol, Atom>,
) -> RusticolResult<()> {
    let unsupported = || {
        RusticolError::unsupported_runtime_capability(
            "native-tree",
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

impl TreeProgram {
    /// Prepare a new process from the in-memory model and exact parameter
    /// overrides. Model/card numeric defaults retain their binary64 values as
    /// exact rationals; extra precision requires exact overrides. Pass any
    /// restriction card explicitly, including for an already restricted model.
    ///
    /// Graph selection/veto filters are honored. The loop range is fixed to
    /// zero, and external symmetrization/numerator grouping are disabled so the
    /// coherent amplitude retains each labelled diagram. Overrides must name model
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
        field_class: TreeFieldClass,
    ) -> RusticolResult<Self> {
        Self::prepare_with_runtime_parameters(
            model,
            process,
            options,
            card,
            exact_overrides,
            field_class,
            &[],
        )
    }

    /// Retain ordered model parameters as typed per-row evaluator inputs.
    /// Use the unrestricted model for parameters intended to vary: interactions
    /// already removed by model restriction cannot be reconstructed here.
    /// Domain assumptions are enforced on every runtime parameter batch.
    /// Dynamic masses/widths must still satisfy this class's admission proofs.
    pub fn prepare_with_runtime_parameters(
        model: Arc<Model>,
        process: &Process,
        options: &GenerationOptions,
        card: Option<&ParameterCard>,
        exact_overrides: &BTreeMap<Symbol, Atom>,
        field_class: TreeFieldClass,
        runtime_parameters: &[RuntimeTreeParameter],
    ) -> RusticolResult<Self> {
        validate_order_filter(&model, options)?;
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
        let mut overrides = exact_overrides.clone();
        let mut parameter_inputs = Vec::with_capacity(runtime_parameters.len());
        let mut names = BTreeSet::new();
        for (index, input) in runtime_parameters.iter().enumerate() {
            if !names.insert(input.symbol) || overrides.contains_key(&input.symbol) {
                return Err(error(
                    "runtime parameters must be distinct and cannot also have frozen overrides",
                ));
            }
            let parameter = model
                .parameters()
                .iter()
                .find(|parameter| input.symbol == symbol!(&format!("UFO::{}", parameter.name)))
                .ok_or_else(|| {
                    error(format!(
                        "runtime input {} does not name a model parameter",
                        input.symbol
                    ))
                })?;
            if parameter.parameter_type == ParameterType::Real
                && input.domain == TreeParameterDomain::Complex
            {
                return Err(error(format!(
                    "real model parameter {} requires a real runtime domain",
                    parameter.name
                )));
            }
            // Domains are part of the interned symbol name: Symbolica correctly
            // rejects conflicting assumptions on a previously created symbol.
            let (domain, attributes) = match input.domain {
                TreeParameterDomain::Real => ("real", vec![SymbolAttribute::Real]),
                TreeParameterDomain::PositiveReal => ("positive", vec![SymbolAttribute::Positive]),
                TreeParameterDomain::Complex => ("complex", vec![]),
            };
            let name = format!("rusticol_native_tree::runtime_{domain}_{index}");
            let free = SymbolBuilder::new(symbolica::wrap_symbol!(&name))
                .with_attributes(attributes)
                .build()
                .map_err(error)?;
            let free = Atom::var(free);
            overrides.insert(input.symbol, free.clone());
            parameter_inputs.push(free);
        }
        if exact_overrides
            .values()
            .chain(
                model
                    .parameters()
                    .iter()
                    .filter_map(|parameter| parameter.expression.as_ref()),
            )
            .chain(
                model
                    .couplings()
                    .iter()
                    .map(|coupling| &coupling.expression),
            )
            .any(|expression| {
                parameter_inputs
                    .iter()
                    .any(|input| expression.contains(input))
            })
        {
            return Err(error(
                "model scalar definitions use a reserved runtime parameter input symbol",
            ));
        }
        let scalar_bindings = model.scalar_bindings(card, &overrides).map_err(error)?;
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
                let singlet_scalar = particle.spin == 1 && particle.color == 1;
                let qcd_field = match particle.spin {
                    2 => {
                        particle.color.unsigned_abs() == 3
                            && !diagram.model().particle_is_self_conjugate(edge.particle)
                            // The unpolarized Dirac sum is slash(p) ± m also
                            // when m was adjustable at model import. An exact
                            // frozen m=0 specialization therefore gives its
                            // massless sum without changing the tensor basis.
                            && bind_scalars(&particle.symbolic_mass(diagram.model()), &scalar_bindings).expand().is_zero()
                    }
                    3 => particle.color == 8 && particle.is_massless(diagram.model()),
                    _ => false,
                };
                let supported = singlet_scalar
                    || (field_class == TreeFieldClass::MasslessQcdAndSingletScalars && qcd_field);
                if !supported || particle.ghost_number != 0 {
                    return Err(RusticolError::unsupported_runtime_capability(
                        "native-tree",
                        format!(
                            "participating field {:?} has spin {} and color {}; it is outside the admitted {:?} class",
                            particle.name, particle.spin, particle.color, field_class,
                        ),
                    ));
                }
                if edge.external.is_none() && !edge.is_dummy {
                    validate_canonical_pole(diagram.model(), particle, &scalar_bindings)?;
                }
            }
        }
        let amplitude = generated
            .into_amplitude(AmplitudeOptions::default())
            .map_err(|failure| error(format!("amplitude generation: {failure}")))?;
        let physical_expression = amplitude.expression().map_err(error)?;
        if parameter_inputs
            .iter()
            .any(|input| physical_expression.expression().contains(input))
        {
            return Err(error(
                "model uses a reserved runtime parameter input symbol",
            ));
        }
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
        let source = physical_expression
            .with_checked_expression(bind_scalars(
                physical_expression.expression(),
                &scalar_bindings,
            ))
            .map_err(error)?;
        let mut inputs = Vec::new();
        let mut vectors = BTreeMap::new();
        let mut states = Vec::new();
        let mut external_states = Vec::new();
        let mut color_legs = Vec::new();
        let mut external_color = BTreeMap::new();
        for (position, leg) in amplitude.legs().iter().enumerate() {
            let components: [Atom; 4] = std::array::from_fn(|mu| {
                Atom::var(symbol!(&format!(
                    "rusticol_native_tree::p_{}_{mu}",
                    leg.index
                )))
            });
            if components
                .iter()
                .any(|value| source.expression().contains(value))
            {
                return Err(error("model uses a reserved momentum input symbol"));
            }
            inputs.extend(components.iter().cloned());
            vectors.insert(
                leg.momentum(),
                TreeComponentVector {
                    representation: Minkowski {}.new_rep(4).to_lib(),
                    components,
                },
            );
            let particle = amplitude
                .model()
                .particle_by_id(leg.particle)
                .map_err(error)?;
            let incoming = leg.state == ExternalState::Incoming;
            let representation = match particle.color {
                1 => ColorRepresentation::Singlet,
                3 => ColorRepresentation::Fundamental,
                -3 => ColorRepresentation::Antifundamental,
                8 => ColorRepresentation::Adjoint,
                _ => return Err(error("unsupported external color representation")),
            };
            let label = i64::try_from(leg.index).map_err(error)?;
            color_legs.push(ColorLeg::all_outgoing(label, representation, incoming));
            if representation != ColorRepresentation::Singlet {
                external_color.insert(index_label(leg.tensor_index.to_atom()), label);
            }
            if particle.spin == 1 {
                continue;
            }
            let spin = leg
                .slots
                .iter()
                .copied()
                .find(|slot| {
                    slot.rep().rep.base() == (Bispinor {}).into()
                        || slot.rep().rep.base() == (Minkowski {}).into()
                })
                .ok_or_else(|| error("external state has no admitted spin port"))?;
            let head = spenso::vector_symbol!("rusticol_native_tree::external_state");
            if source.expression().contains_symbol(head) {
                return Err(error("model uses a reserved external-state symbol"));
            }
            let components: [Atom; 4] = std::array::from_fn(|mu| {
                Atom::var(symbol!(&format!(
                    "rusticol_native_tree::w_{}_{mu}",
                    leg.index
                )))
            });
            if components
                .iter()
                .any(|value| source.expression().contains(value))
            {
                return Err(error("model uses a reserved external-state input symbol"));
            }
            let kind = match (particle.spin, particle.is_antiparticle(), incoming) {
                (2, false, true) => "u",
                (2, false, false) => "u_bar",
                (2, true, true) => "v_bar",
                (2, true, false) => "v",
                (3, _, true) => "epsilon",
                (3, _, false) => "epsilon_bar",
                _ => return Err(error("unsupported external wavefunction")),
            };
            let dual = spin.dual();
            external_states.push((
                SymbolicTensor::infer(function!(head, label, dual.to_atom())).map_err(error)?,
                components.clone(),
            ));
            vectors.insert(
                function!(head, label),
                TreeComponentVector {
                    representation: dual.rep(),
                    components,
                },
            );
            states.push(ExternalTreeState {
                momentum_columns: std::array::from_fn(|mu| 4 * position + mu),
                kind: kind.into(),
                helicities: vec![-1, 1],
            });
        }
        // Momentums precede all wavefunctions, independently of the interleaved
        // external-leg spin/color metadata.
        for (_, components) in &external_states {
            inputs.extend(components.iter().cloned());
        }
        inputs.extend(parameter_inputs);
        let factors = factor_tree_color(&source, &color_legs, &external_color)?;
        let mut color_tensors = Vec::with_capacity(factors.len());
        let mut coefficients = Vec::with_capacity(factors.len());
        for (color, mut spin) in factors {
            for (state, _) in &external_states {
                spin = spin.multiply(state).map_err(error)?;
            }
            let coefficient = contract_tree_state_components(spin, &vectors)?;
            color_tensors.push(color);
            coefficients.push(coefficient);
        }
        let exact = Atom::evaluator_multiple(&coefficients, &inputs)
            .cores(1)
            .build()
            .map_err(error)?;
        let gram = color_tensors
            .iter()
            .map(|left| {
                color_tensors
                    .iter()
                    .map(|right| left.overlap(right))
                    .collect::<RusticolResult<Vec<_>>>()
            })
            .collect::<RusticolResult<Vec<_>>>()?;
        let (norm, amplitude_inputs) = hermitian_norm(&gram)?;
        // Preserve the scalar entry point's direct-norm state by composing the
        // already contracted coefficients. No diagrams or tensors are rebuilt.
        let scalar_norm_state = if field_class == TreeFieldClass::SingletScalars {
            let expression = norm.replace_map(|term, _, out| {
                if let Some(index) = amplitude_inputs
                    .iter()
                    .position(|input| input.as_view() == term)
                {
                    let coefficient = &coefficients[index / 2];
                    **out = if index % 2 == 0 {
                        (coefficient + coefficient.conj()) * Atom::num((1, 2))
                    } else {
                        (coefficient - coefficient.conj()) * Atom::i() * Atom::num((-1, 2))
                    };
                }
            });
            let evaluator = Atom::evaluator_multiple(&[expression], &inputs)
                .cores(1)
                .build()
                .map_err(error)?;
            Some(encode_exact_evaluator_state(&evaluator)?)
        } else {
            None
        };
        let norm = Atom::evaluator_multiple(&[norm], &amplitude_inputs)
            .cores(1)
            .build()
            .map_err(error)?;
        Ok(Self {
            field_class,
            momentum_legs,
            diagram_count: amplitude.diagrams().len(),
            evaluator_state: encode_exact_evaluator_state(&exact)?,
            norm_state: encode_exact_evaluator_state(&norm)?,
            scalar_norm_state,
            states,
            runtime_parameters: runtime_parameters.to_vec(),
            color_tensors,
        })
    }

    pub fn field_class(&self) -> TreeFieldClass {
        self.field_class
    }

    pub fn momentum_legs(&self) -> &[usize] {
        &self.momentum_legs
    }
    pub fn diagram_count(&self) -> usize {
        self.diagram_count
    }
    pub fn runtime_parameters(&self) -> &[RuntimeTreeParameter] {
        &self.runtime_parameters
    }
    /// Exact raw amplitude-coefficient instructions, before the color norm.
    /// Inputs are all physical momentum components, followed by four complex
    /// external components per entry in [`TreeEvaluator::states`], then the
    /// ordered [`Self::runtime_parameters`] columns.
    pub fn evaluator_state(&self) -> &[u8] {
        &self.evaluator_state
    }

    /// Exact complete SU(3) color tensors corresponding to the retained amplitude
    /// coefficient columns. They may be redundant; no Gram inverse is used.
    /// The reducer retains formal Nc polynomials, but this prepared model and
    /// numerical norm are certified only for Nc=3 and TR=1/2.
    pub fn color_tensors(&self) -> &[ConnectedColorTensor] {
        &self.color_tensors
    }

    /// Select binary64, double-double, or arbitrary decimal precision in the
    /// existing coefficient runtime. Batches remain typed in their carrier.
    /// The runtime validates real finite momenta and finite outputs, then reuses
    /// native wavefunctions and coefficient evaluation. On-shell consistency
    /// with the model and momentum conservation remain caller requirements.
    pub fn evaluator(
        &self,
        arithmetic: &str,
        decimal_digits: Option<u32>,
    ) -> RusticolResult<TreeEvaluator> {
        let (arithmetic, bits) = arithmetic_mode(arithmetic, decimal_digits).map_err(error)?;
        self.evaluator_with_precision_bits(arithmetic, bits)
    }

    /// Use an explicit initial working precision without hidden guard bits.
    /// The physical-domain requirements of [`Self::evaluator`] also apply.
    pub fn evaluator_with_precision_bits(
        &self,
        arithmetic: Arithmetic,
        bits: u32,
    ) -> RusticolResult<TreeEvaluator> {
        TreeEvaluator::with_parameter_domains(
            &self.evaluator_state,
            &self.norm_state,
            self.states.clone(),
            self.momentum_legs.len() * 4,
            self.runtime_parameters
                .iter()
                .map(|input| input.domain)
                .collect(),
            arithmetic,
            bits,
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::runtime::{Batch, Data, wavefunctions_batch};
    use rusticol_core::color::{ColorConnection, ColorEmission};
    use symbolica::{
        domains::{
            float::{Complex, Float, FloatLike, Real},
            rational::Rational,
        },
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

    fn massless_qcd_model() -> Model {
        // The native embedded model needs no Python/UFO import or file access.
        Model::qcd()
    }

    fn massless_qcd_parameters(model: &Model, coupling: Atom) -> BTreeMap<Symbol, Atom> {
        let mut exact_parameters = BTreeMap::from([(symbol!("UFO::G"), coupling)]);
        for particle in model
            .particles()
            .iter()
            .filter(|particle| particle.spin == 2)
        {
            let mass = model.parameter_by_id(particle.mass).unwrap();
            exact_parameters.insert(symbol!(&format!("UFO::{}", mass.name)), Atom::Zero);
        }
        exact_parameters
    }

    fn check_massless_qcd_channel(case: usize) {
        let model = Arc::new(massless_qcd_model());
        let exact_parameters = massless_qcd_parameters(&model, Atom::one());
        let (s, t, u) = (100.0_f64, -20.0_f64, -80.0_f64);
        // Independent spin/color-averaged channel formulas: PDG 2024,
        // Cross-Section Formulae, Eqs. 51.5, 51.7, 51.9, 51.10, 51.12.
        // https://pdg.lbl.gov/2024/reviews/rpp2024-rev-cross-section-formulae.pdf
        // Restore initial degeneracies 36, 36, 96, 256, 36 respectively;
        // no final-state identical-particle factor belongs in an amplitude norm.
        let cases = [
            (["u", "d"], ["u", "d"], 16.0 * (s * s + u * u) / (t * t)),
            (
                ["u", "u"],
                ["u", "u"],
                16.0 * ((s * s + u * u) / (t * t) + (s * s + t * t) / (u * u))
                    - 32.0 / 3.0 * s * s / (t * u),
            ),
            (
                ["u", "g"],
                ["u", "g"],
                96.0 * ((s * s + u * u) / (t * t) - 4.0 / 9.0 * (s * s + u * u) / (s * u)),
            ),
            (
                ["g", "g"],
                ["g", "g"],
                256.0 * 9.0 / 2.0 * (3.0 - u * t / (s * s) - s * u / (t * t) - s * t / (u * u)),
            ),
            (
                ["u", "u~"],
                ["g", "g"],
                36.0 * (32.0 / 27.0 * (u / t + t / u) - 8.0 / 3.0 * (u * u + t * t) / (s * s)),
            ),
        ];
        let momenta = [
            5., 0., 0., 5., 5., 0., 0., -5., 5., 4., 0., 3., 5., -4., 0., -3.,
        ];
        // A boost with beta_z=3/5 changes the timelike projector's rest frame,
        // while all three invariants and every physical norm remain unchanged.
        let boosted = [
            2.5, 0., 0., 2.5, 10., 0., 0., -10., 4., 4., 0., 0., 8.5, -4., 0., -7.5,
        ];
        // A transverse boost introduces genuinely complex helicity components.
        let transverse = [
            6.25, 0., -3.75, 5., 6.25, 0., -3.75, -5., 6.25, 4., -3.75, 3., 6.25, -4., -3.75, -3.,
        ];
        for (incoming, outgoing, expected) in cases.into_iter().skip(case).take(1) {
            let program = TreeProgram::prepare(
                model.clone(),
                &Process::new(incoming, outgoing),
                &GenerationOptions::default().threads(1),
                None,
                &exact_parameters,
                TreeFieldClass::MasslessQcdAndSingletScalars,
            )
            .unwrap_or_else(|error| panic!("{incoming:?} -> {outgoing:?}: {error}"));
            let input = Batch::typed(
                momenta
                    .into_iter()
                    .chain(boosted)
                    .chain(transverse)
                    .map(|value| Complex::new(value, 0.0))
                    .collect(),
                vec![13, 14, 15],
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
            for value in values.iter() {
                assert!(
                    (value.re - expected).abs() < 1e-9 * expected,
                    "{incoming:?} -> {outgoing:?}: got {value}, expected {expected}"
                );
                assert_eq!(
                    value.im, 0.,
                    "Hermitian norm is constructed as a real quadratic form"
                );
            }
            check_color_charge_conservation(&program);
            check_gluon_ward_identities(&program, &input, expected);
        }
    }

    fn check_color_charge_conservation(program: &TreeProgram) {
        let basis = program.color_tensors();
        let legs = basis[0].legs();
        let connected: Vec<Vec<_>> = legs
            .iter()
            .map(|leg| {
                let connection = ColorConnection::new(
                    legs.to_vec(),
                    vec![ColorEmission::EmitGluon {
                        emitter: leg.label,
                        emitted: 10_000,
                    }],
                )
                .unwrap();
                basis
                    .iter()
                    .map(|tensor| connection.apply_connected(tensor).unwrap())
                    .collect()
            })
            .collect();
        let zero = Complex::new(Rational::from(0), Rational::from(0));
        for (i, leg) in legs.iter().enumerate() {
            let casimir = match leg.representation {
                ColorRepresentation::Adjoint => Rational::from(3),
                _ => Rational::from((4, 3)),
            };
            for (a, bra) in basis.iter().enumerate() {
                for (b, ket) in basis.iter().enumerate() {
                    let gram = bra.overlap(ket).unwrap();
                    let expected = Complex::new(&gram.re * &casimir, &gram.im * &casimir);
                    assert_eq!(connected[i][a].overlap(&connected[i][b]).unwrap(), expected);
                    let mut sum = zero.clone();
                    for image in &connected {
                        sum += &connected[i][a].overlap(&image[b]).unwrap();
                    }
                    assert_eq!(
                        sum, zero,
                        "all-outgoing charge conservation on leg {}",
                        leg.label
                    );
                }
            }
        }
    }

    fn check_gluon_ward_identities(program: &TreeProgram, momenta: &Batch, scale: f64) {
        let mut evaluator = program.evaluator("double", None).unwrap();
        let states = evaluator.states().to_vec();
        let basis = program.color_tensors();
        let gram: Vec<Vec<_>> = basis
            .iter()
            .map(|bra| {
                basis
                    .iter()
                    .map(|ket| {
                        let value = bra.overlap(ket).unwrap();
                        Complex::new(value.re.to_f64(), value.im.to_f64())
                    })
                    .collect()
            })
            .collect();
        for replaced in states
            .iter()
            .enumerate()
            .filter_map(|(i, s)| s.kind.starts_with("epsilon").then_some(i))
        {
            for assignment in 0..(1usize << states.len()) {
                let components: Vec<_> = states
                    .iter()
                    .enumerate()
                    .map(|(i, state)| {
                        let p = momenta
                            .take_columns(state.momentum_columns.to_vec())
                            .unwrap();
                        if i == replaced {
                            return p;
                        }
                        let h = if assignment & (1 << i) == 0 { -1 } else { 1 };
                        wavefunctions_batch(
                            &p,
                            vec![h; momenta.rows()],
                            vec![state.kind.clone(); momenta.rows()],
                            Some(4),
                        )
                        .unwrap()
                    })
                    .collect();
                let coefficients = evaluator
                    .evaluate_external_components(momenta, &components.iter().collect::<Vec<_>>())
                    .unwrap();
                let Data::Double(values) = coefficients.data() else {
                    panic!("carrier changed")
                };
                // The retained basis may be redundant: a Ward cancellation
                // concerns its full color norm, not each coefficient separately.
                for row in values.chunks(basis.len()) {
                    let mut norm = Complex::new(0., 0.);
                    for (a, left) in row.iter().enumerate() {
                        for (b, right) in row.iter().enumerate() {
                            norm += &(left.conj() * gram[a][b] * right);
                        }
                    }
                    assert!(
                        norm.re.abs() + norm.im.abs() < 1e-10 * scale,
                        "Ward leg {replaced}: {norm}"
                    );
                }
            }
        }
    }

    #[test]
    fn four_gluon_amplitudes_keep_exact_sub_binary64_inputs_at_requested_bits() {
        let model = Arc::new(massless_qcd_model());
        let parameters = massless_qcd_parameters(&model, parse!("1+1/1208925819614629174706176"));
        let program = TreeProgram::prepare(
            model,
            &Process::new(["g", "g"], ["g", "g"]),
            &GenerationOptions::default().threads(1),
            None,
            &parameters,
            TreeFieldClass::MasslessQcdAndSingletScalars,
        )
        .unwrap();
        for bits in [113, 137, 256, 512, 1024] {
            let values = [5, 0, 0, 5, 5, 0, 0, -5, 5, 4, 0, 3, 5, -4, 0, -3]
                .into_iter()
                .map(|value| Complex::new(Float::with_val(bits, value), Float::with_val(bits, 0)))
                .collect();
            let input = Batch::typed(values, vec![23], 16, bits).unwrap();
            let mut evaluator = program
                .evaluator_with_precision_bits(Arithmetic::Arbitrary, bits)
                .unwrap();
            let output = evaluator.evaluate_batch(&input).unwrap();
            let Data::Arbitrary(values) = output.data() else {
                panic!("carrier changed")
            };
            let two = Float::with_val(bits, 2);
            let coupling = Float::with_val(bits, 1) + two.pow(80).inv();
            let base = Float::with_val(bits, 666792) / Float::with_val(bits, 25);
            let expected = base.clone() * coupling.pow(4);
            assert!(values[0].re > base);
            assert!(
                (values[0].re.clone() - expected).norm() < two.pow(u64::from(bits - 32)).inv(),
                "bits={bits}"
            );
            assert!(
                values[0].im.norm() < two.pow(u64::from(bits - 32)).inv(),
                "bits={bits}"
            );
            assert!(values[0].re.get_precision() > bits - 37, "bits={bits}");
        }
    }

    #[test]
    fn runtime_alpha_s_resolves_analytic_couplings_without_repreparation() {
        // Cached coupling zeros must not delete analytic interactions: only a
        // caller's prior explicit model restriction may do that.
        let mut definition = serde_json::to_value(Model::qcd()).unwrap();
        for coupling in definition["couplings"].as_array_mut().unwrap() {
            coupling["value"] = serde_json::json!([0., 0.]);
        }
        let model = Arc::new(Model::from_json(&definition.to_string()).unwrap());
        let program = TreeProgram::prepare_with_runtime_parameters(
            model,
            &Process::new(["g", "g"], ["g", "g"]),
            &GenerationOptions::default().threads(1),
            None,
            &BTreeMap::new(),
            TreeFieldClass::MasslessQcdAndSingletScalars,
            &[RuntimeTreeParameter {
                symbol: symbol!("UFO::aS"),
                domain: TreeParameterDomain::PositiveReal,
            }],
        )
        .unwrap();
        let bits = 173;
        let zero = Float::with_val(bits, 0);
        let two = Float::with_val(bits, 2);
        let first = two.pow(4).inv();
        let second = first.clone() + two.pow(90).inv();
        let momenta = Batch::typed(
            [5, 0, 0, 5, 5, 0, 0, -5, 5, 4, 0, 3, 5, -4, 0, -3]
                .into_iter()
                .cycle()
                .take(32)
                .map(|value| Complex::new(Float::with_val(bits, value), zero.clone()))
                .collect(),
            vec![7, 3],
            16,
            bits,
        )
        .unwrap();
        let parameters = Batch::typed(
            [first.clone(), second.clone()]
                .into_iter()
                .map(|value| Complex::new(value, zero.clone()))
                .collect(),
            vec![7, 3],
            1,
            bits,
        )
        .unwrap();
        let mut evaluator = program
            .evaluator_with_precision_bits(Arithmetic::Arbitrary, bits)
            .unwrap();
        assert!(evaluator.evaluate_batch(&momenta).is_err());
        let output = evaluator
            .evaluate_batch_with_parameters(&momenta, &parameters)
            .unwrap();
        let Data::Arbitrary(values) = output.data() else {
            panic!("carrier changed")
        };
        let base = Float::with_val(bits, 666792) / Float::with_val(bits, 25);
        for (value, alpha) in values.iter().zip([first, second]) {
            let g_squared = Float::with_val(bits, 4) * zero.pi() * alpha;
            let expected = base.clone() * g_squared.pow(2);
            assert!((value.re.clone() - expected).norm() < two.pow(135).inv());
            assert!(value.im.norm() < two.pow(135).inv());
        }
        assert!(
            values[1].re > values[0].re,
            "per-row sub-binary64 alpha_s survives"
        );
        let permuted = parameters.take_rows(vec![1, 0], None).unwrap();
        assert!(
            evaluator
                .evaluate_batch_with_parameters(&momenta, &permuted)
                .is_err()
        );
    }

    #[test]
    fn runtime_complex_coefficients_keep_phases_and_zero_default_vertices() {
        let mut definition = scalar_model_definition(4);
        definition["parameters"][1]["parameter_type"] = serde_json::json!("complex");
        definition["parameters"][1]["value"] = serde_json::json!([0., 0.]);
        definition["couplings"][0]["value"] = serde_json::json!([0., 0.]);
        let program = TreeProgram::prepare_with_runtime_parameters(
            Arc::new(Model::from_json(&definition.to_string()).unwrap()),
            &Process::new(["s", "s"], ["s", "s"]),
            &GenerationOptions::default().threads(1),
            None,
            &BTreeMap::new(),
            TreeFieldClass::SingletScalars,
            &[RuntimeTreeParameter {
                symbol: symbol!("UFO::g_"),
                domain: TreeParameterDomain::Complex,
            }],
        )
        .unwrap();
        assert_eq!(program.diagram_count(), 1);
        let momenta = Batch::typed(vec![Complex::new(0., 0.); 32], vec![11, 19], 16, 53).unwrap();
        let parameters = Batch::typed(
            vec![Complex::new(1., 2.), Complex::new(3., -4.)],
            vec![11, 19],
            1,
            53,
        )
        .unwrap();
        let mut evaluator = program.evaluator("double", None).unwrap();
        let amplitudes = evaluator
            .evaluate_coefficients_with_parameters(&momenta, &parameters, &[])
            .unwrap();
        let Data::Double(amplitudes) = amplitudes.data() else {
            panic!("carrier changed")
        };
        assert_eq!(
            amplitudes[0].conj() * amplitudes[1],
            Complex::new(-5., -10.)
        );
        let norms = evaluator
            .evaluate_batch_with_parameters(&momenta, &parameters)
            .unwrap();
        let Data::Double(norms) = norms.data() else {
            panic!("carrier changed")
        };
        assert_eq!(
            norms.as_slice(),
            &[Complex::new(5., 0.), Complex::new(25., 0.)]
        );
    }

    #[test]
    fn runtime_parameter_domains_do_not_erase_model_admission_proofs() {
        let model = Arc::new(scalar_model(4));
        for inputs in [
            vec![RuntimeTreeParameter {
                symbol: symbol!("UFO::missing"),
                domain: TreeParameterDomain::Real,
            }],
            vec![RuntimeTreeParameter {
                symbol: symbol!("UFO::ZERO"),
                domain: TreeParameterDomain::Real,
            }],
            vec![RuntimeTreeParameter {
                symbol: symbol!("UFO::g_"),
                domain: TreeParameterDomain::Complex,
            }],
            vec![
                RuntimeTreeParameter {
                    symbol: symbol!("UFO::g_"),
                    domain: TreeParameterDomain::Real
                };
                2
            ],
        ] {
            assert!(
                TreeProgram::prepare_with_runtime_parameters(
                    model.clone(),
                    &Process::new(["s", "s"], ["s", "s"]),
                    &GenerationOptions::default().threads(1),
                    None,
                    &BTreeMap::new(),
                    TreeFieldClass::SingletScalars,
                    &inputs
                )
                .is_err()
            );
        }
        let alias = Atom::var(symbol!("rusticol_native_tree::runtime_real_0"; Real));
        assert!(
            TreeProgram::prepare_with_runtime_parameters(
                model.clone(),
                &Process::new(["s", "s"], ["s", "s"]),
                &GenerationOptions::default().threads(1),
                None,
                &BTreeMap::from([(symbol!("UFO::m"), alias)]),
                TreeFieldClass::SingletScalars,
                &[RuntimeTreeParameter {
                    symbol: symbol!("UFO::g_"),
                    domain: TreeParameterDomain::Real
                }]
            )
            .is_err()
        );
        let qcd = Arc::new(Model::qcd());
        let mass = qcd
            .parameter_by_id(qcd.particle("u").unwrap().mass)
            .unwrap()
            .name
            .clone();
        assert!(
            TreeProgram::prepare_with_runtime_parameters(
                qcd,
                &Process::new(["u", "d"], ["u", "d"]),
                &GenerationOptions::default().threads(1),
                None,
                &BTreeMap::new(),
                TreeFieldClass::MasslessQcdAndSingletScalars,
                &[RuntimeTreeParameter {
                    symbol: symbol!(&format!("UFO::{mass}")),
                    domain: TreeParameterDomain::Real
                }]
            )
            .is_err()
        );
    }

    #[test]
    fn order_filters_reject_mixed_vertex_orders_without_discarding_terms() {
        let mut definition = scalar_model_definition(4);
        definition["couplings"]
            .as_array_mut()
            .unwrap()
            .push(serde_json::json!({
                "name":"GC2", "expression":"g_", "orders":[["SELF",2]], "value":[1.,0.]
            }));
        definition["lorentz_structures"]
            .as_array_mut()
            .unwrap()
            .push(serde_json::json!({
                "name":"SSSS2", "spins":[1,1,1,1], "structure":"1"
            }));
        definition["vertex_rules"][0]["lorentz_structures"] = serde_json::json!(["SSSS", "SSSS2"]);
        definition["vertex_rules"][0]["couplings"] = serde_json::json!([["GC1", "GC2"]]);
        let mixed = Arc::new(Model::from_json(&definition.to_string()).unwrap());
        let process = Process::new(["s", "s"], ["s", "s"]);
        let options = GenerationOptions::default().threads(1).with_graph_filter(
            GenerationFilter::CouplingOrders(BTreeMap::from([("SELF".into(), (1, Some(1)))])),
        );
        assert!(
            TreeProgram::prepare(
                mixed.clone(),
                &process,
                &options,
                None,
                &BTreeMap::new(),
                TreeFieldClass::SingletScalars
            )
            .is_err()
        );
        // Without an order projection both terms form a valid coherent sum.
        let complete = TreeProgram::prepare(
            mixed,
            &process,
            &GenerationOptions::default().threads(1),
            None,
            &BTreeMap::new(),
            TreeFieldClass::SingletScalars,
        )
        .unwrap();
        let input = Batch::typed(vec![Complex::new(0., 0.); 16], vec![4], 16, 53).unwrap();
        let output = complete
            .evaluator("double", None)
            .unwrap()
            .evaluate_batch(&input)
            .unwrap();
        let Data::Double(values) = output.data() else {
            panic!("carrier changed")
        };
        assert_eq!(values[0], Complex::new(4., 0.));
    }

    #[test]
    fn massless_qcd_distinct_quarks_match_pdg_and_boost() {
        check_massless_qcd_channel(0);
    }

    #[test]
    fn massless_qcd_identical_quarks_match_pdg_and_boost() {
        check_massless_qcd_channel(1);
    }

    #[test]
    fn massless_qcd_quark_gluon_match_pdg_and_boost() {
        check_massless_qcd_channel(2);
    }

    #[test]
    fn massless_qcd_four_gluons_match_pdg_and_boost() {
        check_massless_qcd_channel(3);
    }

    #[test]
    fn massless_qcd_annihilation_match_pdg_and_boost() {
        check_massless_qcd_channel(4);
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
        let mut high = program.evaluator("arbitrary", Some(70)).unwrap();
        let bits = high.precision_bits();
        let batch = Batch::typed(
            vec![Complex::new(Float::with_val(bits, 0), Float::with_val(bits, 0)); 16],
            vec![41],
            16,
            bits,
        )
        .unwrap();
        let out = high.evaluate_batch(&batch).unwrap();
        let direct = crate::runtime::CoefficientEvaluator::with_precision_bits(
            program.evaluator_state(),
            Arithmetic::Arbitrary,
            bits,
        )
        .unwrap()
        .evaluate_batch(&batch)
        .unwrap();
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
        let Data::Arbitrary(direct_values) = direct.data() else {
            panic!("carrier changed")
        };
        assert!(
            (direct_values[0].re.clone() - &values[0].re).norm() < Float::with_val(bits, 1e-65)
        );
    }

    #[test]
    fn fresh_cubic_tree_keeps_all_channel_interferences() {
        let model = scalar_model(3);
        let program = TreeProgram::prepare(
            Arc::new(model),
            &Process::new(["s", "s"], ["s", "s"]),
            &GenerationOptions::default()
                .threads(1)
                .symmetrize_initial(true)
                .symmetrize_final(true),
            None,
            &BTreeMap::new(),
            TreeFieldClass::SingletScalars,
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
            let result = TreeProgram::prepare(
                model.clone(),
                &Process::new(["s", "s"], ["s", "s"]),
                &GenerationOptions::default().threads(1),
                None,
                &BTreeMap::from([(key, value)]),
                TreeFieldClass::SingletScalars,
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
        let program = TreeProgram::prepare(
            Arc::new(model),
            &Process::new(["s", "s"], ["s", "s"]),
            &GenerationOptions::default().threads(1),
            None,
            &BTreeMap::from([(symbol!("UFO::g_"), Atom::num(1) + Atom::num(2) * Atom::i())]),
            TreeFieldClass::SingletScalars,
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
        let program = TreeProgram::prepare(
            Arc::new(model),
            &Process::new(["s", "s"], ["s", "s"]),
            &GenerationOptions::default().threads(1),
            None,
            &BTreeMap::new(),
            TreeFieldClass::SingletScalars,
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
        let result = TreeProgram::prepare(
            Arc::new(model),
            &Process::new(["s", "s"], ["s", "s"]),
            &GenerationOptions::default().threads(1),
            None,
            &BTreeMap::new(),
            TreeFieldClass::SingletScalars,
        );
        assert!(
            result
                .err()
                .expect("must reject participating vector")
                .to_string()
                .contains("outside the admitted SingletScalars")
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
        let program = TreeProgram::prepare(
            Arc::new(model),
            &Process::new(["s", "s"], ["s", "s"]),
            &GenerationOptions::default().threads(1),
            None,
            &BTreeMap::new(),
            TreeFieldClass::SingletScalars,
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
            let result = TreeProgram::prepare(
                Arc::new(model),
                &Process::new(["s", "s"], ["s", "s"]),
                &GenerationOptions::default().threads(1),
                None,
                &BTreeMap::new(),
                TreeFieldClass::SingletScalars,
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
