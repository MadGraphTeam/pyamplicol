// SPDX-License-Identifier: 0BSD

//! Native preparation of rank-zero scalar loop diagrams.
//!
//! FeynKit owns graph generation, symmetry factors, momentum routing and pole
//! extraction. This adapter retains each labelled complex diagram separately;
//! it neither contracts with a Born amplitude nor defines a UV/IR remainder.
//! Admitted local numerators are momentum-independent scalar expressions and
//! all participating fields are color-singlet scalars. Internal poles must be
//! canonical, zero-width vacuum poles. Repeated loop poles are rejected until
//! the reduction boundary supports propagator powers.

use std::{
    collections::{BTreeMap, BTreeSet},
    sync::Arc,
};

use feynkit_amplitude::AmplitudeOptions;
use feynkit_generator::{GenerationOptions, NumeratorGrouping, Process};
use feynkit_graph::{EdgeId, FeynmanDiagram, symbols};
use feynkit_kinematics::Kinematics;
use feynkit_model::{Model, ParameterCard, ParameterType, Particle};
use idenso::tensor::{AlgebraSettings, ContractSettings};
use rusticol_core::{RusticolError, RusticolResult, preparation::encode_exact_evaluator_state};
use symbolica::{
    atom::{Atom, AtomCore, AtomView, Symbol},
    coefficient::CoefficientView,
    symbol,
};

pub(super) struct PreparedScalarLoop {
    pub momentum_legs: Vec<usize>,
    pub evaluator_state: Vec<u8>,
    pub diagrams: Vec<DiagramLayout>,
}

/// One evaluator row is `[coefficient, (shift_E, shift_x, shift_y, shift_z,
/// mass_squared) ...]`. The coefficient includes every model/graph factor and
/// every loop-independent bridge denominator, each exactly once.
pub(super) struct DiagramLayout {
    pub offset: usize,
    pub propagators: usize,
}

fn error(message: impl std::fmt::Display) -> RusticolError {
    RusticolError::invalid_argument(format!("native scalar loop preparation: {message}"))
}

fn unsupported(message: impl AsRef<str>) -> RusticolError {
    RusticolError::unsupported_runtime_capability("native-scalar-loop", message)
}

fn bind_scalars(expression: &Atom, bindings: &BTreeMap<Symbol, Atom>) -> Atom {
    // Model names ending in underscores are literal symbols, not patterns.
    expression.replace_map(|term, _, out| {
        if let AtomView::Var(var) = term {
            if let Some(value) = bindings.get(&var.get_symbol()) {
                **out = value.clone();
            }
        }
    })
}

fn require_exact(expression: &Atom, context: &str) -> RusticolResult<()> {
    let mut approximate = false;
    let _ = expression.replace_map(|term, _, _| {
        if let AtomView::Num(number) = term {
            approximate |= matches!(number.get_coeff_view(), CoefficientView::Float(_, _));
        }
    });
    if approximate {
        return Err(error(format!(
            "{context} must use exact atoms, not floating coefficients"
        )));
    }
    Ok(())
}

fn scalar_bindings(
    model: &Model,
    card: Option<&ParameterCard>,
    overrides: &BTreeMap<Symbol, Atom>,
) -> RusticolResult<BTreeMap<Symbol, Atom>> {
    for key in overrides.keys() {
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
    // Structural-zero consistency belongs to the model owner, including cards
    // and exact overrides. No parameter spelling is a proof of zero here.
    let bindings = model.scalar_bindings(card, overrides).map_err(error)?;
    for (key, value) in &bindings {
        require_exact(value, &format!("scalar binding {key}"))?;
    }
    for parameter in model.parameters() {
        if parameter.parameter_type == ParameterType::Real {
            if let Some(value) = bindings.get(&symbol!(&format!("UFO::{}", parameter.name))) {
                if !value.is_real().is_true() {
                    return Err(error(format!(
                        "parameter {} must have a provably real binding",
                        parameter.name
                    )));
                }
            }
        }
    }
    Ok(bindings)
}

fn validate_scalar_pole(
    model: &Model,
    particle: &Particle,
    bindings: &BTreeMap<Symbol, Atom>,
) -> RusticolResult<()> {
    let invalid = || {
        unsupported(format!(
            "particle {:?} requires a canonical zero-width vacuum propagator p^2-m^2; custom denominators and medium-dependent poles are unsupported",
            particle.name
        ))
    };
    let (id, _) = model
        .particle_propagator(particle)
        .map_err(error)?
        .ok_or_else(invalid)?;
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
                return Err(invalid());
            }
        }
    }
    let mass = bind_scalars(&particle.symbolic_mass(model), bindings);
    if !mass.is_real().is_true() {
        return Err(unsupported(format!(
            "particle {:?} requires a provably real mass",
            particle.name
        )));
    }
    let denominator = bind_scalars(&propagator.denominator, bindings);
    let p = symbol!("UFO::P");
    let idx = symbol!("UFO::idx");
    let momenta = [Atom::var(p), p.call_args([idx.call_args([1i64, 1i64])])];
    if !momenta.iter().any(|momentum| {
        (&denominator - (momentum.clone().pow(2) - mass.clone().pow(2)))
            .expand()
            .is_zero()
    }) {
        return Err(invalid());
    }
    Ok(())
}

/// Exactly the coordinate relabelling used by `Amplitude::diagram_term`:
/// graph basis positions become stable physical external-leg labels.
fn physical_external_labels(diagram: &FeynmanDiagram) -> RusticolResult<Vec<usize>> {
    diagram
        .loop_momentum_basis()
        .external_edges
        .iter()
        .map(|edge| {
            diagram
                .edges()
                .find(|(id, _, _)| id == edge)
                .and_then(|(_, _, edge)| edge.external.as_ref())
                .map(|external| external.index)
                .ok_or_else(|| error("stored external basis edge has no physical leg label"))
        })
        .collect()
}

fn relabel_externals(expression: &Atom, labels: &[usize]) -> RusticolResult<Atom> {
    let mut invalid = false;
    let result = expression.replace_map(|term, _, out| {
        let AtomView::Fun(function) = term else {
            return;
        };
        if function.get_symbol() != symbols::external_momentum() {
            return;
        }
        let mut arguments: Vec<_> = function.iter().map(|arg| arg.to_owned()).collect();
        let Some(position) = arguments
            .first()
            .and_then(|arg| usize::try_from(arg.as_view()).ok())
        else {
            invalid = true;
            return;
        };
        let Some(&label) = labels.get(position) else {
            invalid = true;
            return;
        };
        arguments[0] = Atom::num(label as i64);
        **out = symbols::external_momentum().call_args(arguments);
    });
    if invalid {
        return Err(error(
            "invalid external momentum coordinate in routed expression",
        ));
    }
    Ok(result)
}

/// Select the loop poles from the same tagged graph denominator expression
/// used by the amplitude owner. Its unexpanded dot notation cancels directly
/// against the corresponding amplitude term, before tensor simplification.
fn loop_denominator_product(
    diagram: &FeynmanDiagram,
    loop_edges: &BTreeSet<EdgeId>,
    labels: &[usize],
) -> RusticolResult<Atom> {
    let annotated = diagram
        .denominator_of_in_dimension(&diagram.internal_subgraph(), &BTreeMap::new(), 4.into())
        .map_err(error)?;
    let factors = match annotated.as_view() {
        AtomView::Mul(product) => product.iter().collect::<Vec<_>>(),
        factor => vec![factor],
    };
    let mut product = Atom::one();
    let mut found = BTreeSet::new();
    for factor in factors {
        let AtomView::Fun(propagator) = factor else {
            return Err(error("expected a tagged graph propagator"));
        };
        let arguments = propagator.iter().collect::<Vec<_>>();
        if propagator.get_symbol() != symbols::denominator() || arguments.len() != 4 {
            return Err(error("invalid graph propagator annotation"));
        }
        let edge = EdgeId(usize::try_from(arguments[0]).map_err(error)?);
        if loop_edges.contains(&edge) {
            if !found.insert(edge) {
                return Err(error("duplicate graph propagator annotation"));
            }
            product *= arguments[3].to_owned();
        }
    }
    if &found != loop_edges {
        return Err(error(
            "loop propagators and graph denominator annotations disagree",
        ));
    }
    relabel_externals(
        &diagram.loop_momentum_basis().route_expression(&product),
        labels,
    )
}

fn contains_loop_momentum(expression: &Atom) -> bool {
    let mut found = false;
    let _ = expression.replace_map(|term, _, _| {
        let head = match term {
            AtomView::Fun(function) => Some(function.get_symbol()),
            AtomView::Var(variable) => Some(variable.get_symbol()),
            _ => None,
        };
        found |= head
            .is_some_and(|head| head == symbols::loop_momentum() || head == symbols::momentum());
    });
    found
}

/// Prepare the selected, labelled one-loop graphs. Explicit user selection and
/// veto filters remain in force; loop count, grouping and external permutations
/// are fixed here. Self loops and zero-flow edges are enabled so tadpoles and
/// bridge attachments are not silently discarded. A singular bridge remains
/// an evaluator/runtime error, never an omitted contribution.
///
/// Numeric card/model defaults are the owner's exact rational representation
/// of those defaults; users requiring additional information supply exact
/// overrides. The evaluator takes real physical external momenta, ordered by
/// `momentum_legs`, flattened as `(E, px, py, pz)` with metric `+---`.
pub(super) fn prepare(
    model: Arc<Model>,
    process: &Process,
    options: &GenerationOptions,
    card: Option<&ParameterCard>,
    exact_overrides: &BTreeMap<Symbol, Atom>,
) -> RusticolResult<PreparedScalarLoop> {
    let bindings = scalar_bindings(&model, card, exact_overrides)?;
    let options = options
        .clone()
        .with_loop_count(1, 1)
        .map_err(error)?
        .symmetrize_initial(false)
        .symmetrize_final(false)
        .symmetrize_left_right(false)
        .symmetrize_external_fermions(false)
        .numerator_grouping(NumeratorGrouping::None)
        .allow_self_loops(true)
        .allow_zero_flow_edges(true)
        .threads(1);
    let generated = process.generate_diagrams(model, &options).map_err(error)?;
    let mut fragments = Vec::new();
    for diagram in &generated.diagrams {
        if diagram.loop_count() != 1 {
            return Err(error(
                "generator returned a graph outside the one-loop class",
            ));
        }
        diagram
            .loop_momentum_basis()
            .validate(diagram)
            .map_err(error)?;
        for (_, _, edge) in diagram.edges() {
            let particle = diagram
                .model()
                .particle_by_id(edge.particle)
                .map_err(error)?;
            if particle.spin != 1 || particle.color != 1 {
                return Err(unsupported(format!(
                    "participating field {:?} has spin {} and color {}; only color-singlet scalars are admitted",
                    particle.name, particle.spin, particle.color
                )));
            }
            if edge.external.is_none() && !edge.is_dummy {
                validate_scalar_pole(diagram.model(), particle, &bindings)?;
            }
            fragments.push(bind_scalars(
                &diagram
                    .model()
                    .expand_couplings(edge.numerator.expression()),
                &bindings,
            ));
        }
        for (_, vertex) in diagram.vertices() {
            fragments.push(bind_scalars(
                &diagram
                    .model()
                    .expand_couplings(vertex.numerator.expression()),
                &bindings,
            ));
        }
        fragments.push(bind_scalars(
            &diagram
                .model()
                .expand_couplings(diagram.numerator_prefactor().expression()),
            &bindings,
        ));
        if !bind_scalars(diagram.projector().expression(), &bindings).is_one() {
            return Err(unsupported(
                "nontrivial generation projectors are not scalar amplitudes",
            ));
        }
    }
    for fragment in &fragments {
        require_exact(fragment, "local numerator")?;
    }
    // Constant scalar compilation rejects derivative vertices, tensor traces,
    // unresolved functions and hidden D-dependent factors before a four-
    // dimensional amplitude representation can erase their dependence.
    let no_inputs: Vec<Atom> = Vec::new();
    if !fragments.is_empty() {
        Atom::evaluator_multiple(&fragments, &no_inputs)
            .cores(1)
            .build()
            .map_err(|cause| {
                unsupported(format!(
                    "local numerators must be momentum-independent scalar expressions: {cause}"
                ))
            })?;
    }
    let amplitude = generated
        .into_amplitude(AmplitudeOptions::default())
        .map_err(error)?;
    let momentum_legs: Vec<_> = amplitude.legs().iter().map(|leg| leg.index).collect();
    let components: BTreeMap<_, Vec<Atom>> = momentum_legs
        .iter()
        .map(|&leg| {
            (
                leg,
                (0..4)
                    .map(|mu| {
                        Atom::var(symbol!(&format!(
                            "rusticol_native_scalar_loop::p_{leg}_{mu}"
                        )))
                    })
                    .collect(),
            )
        })
        .collect();
    let inputs: Vec<_> = momentum_legs
        .iter()
        .flat_map(|leg| components[leg].iter().cloned())
        .collect();
    let mut component_kinematics = Kinematics::new();
    for left in amplitude.legs() {
        for right in amplitude.legs() {
            let (a, b) = (&components[&left.index], &components[&right.index]);
            let value = &a[0] * &b[0] - &a[1] * &b[1] - &a[2] * &b[2] - &a[3] * &b[3];
            component_kinematics = component_kinematics
                .with_scalar_product(&left.momentum(), &right.momentum(), value)
                .map_err(error)?;
        }
    }

    let mut outputs = Vec::new();
    let mut diagrams = Vec::new();
    for (diagram, term) in amplitude.diagrams().iter().zip(amplitude.terms()) {
        let basis = diagram.loop_momentum_basis();
        let labels = physical_external_labels(diagram)?;
        let local_externals: Vec<_> = (0..labels.len())
            .map(|i| symbols::external_momentum().call(i))
            .collect();
        let ordered = diagram
            .ordered_propagators(&Kinematics::new())
            .map_err(error)?;
        let family = diagram
            .propagator_family(&Kinematics::new())
            .map_err(error)?;
        let mut loop_edges = BTreeSet::new();
        let mut denominators: Vec<Atom> = Vec::new();
        let mut propagator_outputs = Vec::new();
        for (index, (edge, denominator)) in ordered.iter().enumerate() {
            let signature = basis
                .edge_signatures
                .get(edge)
                .ok_or_else(|| error("internal propagator has no owner momentum signature"))?
                .canonicalized();
            let loop_coefficients = signature.loops.integer_coefficients();
            if loop_coefficients
                .iter()
                .all(|&coefficient| coefficient == 0)
            {
                continue;
            }
            if loop_coefficients != [1] {
                return Err(unsupported(
                    "loop poles require one unit loop-momentum coefficient",
                ));
            }
            let quadratic = family
                .quadratic_denominator(index)
                .map_err(error)?
                .ok_or_else(|| {
                    unsupported("loop propagator is not one quadratic momentum square")
                })?;
            if !quadratic.scale().is_one() {
                return Err(unsupported(
                    "loop propagators must be monic simple quadratic poles",
                ));
            }
            let routed = signature
                .apply(&[symbols::loop_momentum().call(0usize)], &local_externals)
                .map_err(error)?
                .ok_or_else(|| error("empty loop-dependent momentum signature"))?;
            if !(quadratic.momentum() - routed).expand().is_zero() {
                return Err(error(
                    "quadratic pole and owner momentum signature disagree",
                ));
            }
            let mass_squared = bind_scalars(&(-quadratic.remainder()), &bindings).together();
            let particle = diagram
                .edges()
                .find(|(id, _, _)| id == edge)
                .map(|(_, _, edge)| edge.particle)
                .ok_or_else(|| error("ordered propagator has no source edge"))?;
            let particle = diagram.model().particle_by_id(particle).map_err(error)?;
            let expected_mass =
                bind_scalars(&particle.symbolic_mass(diagram.model()), &bindings).pow(2);
            if !(&mass_squared - expected_mass).together().is_zero() {
                return Err(error(
                    "quadratic pole remainder disagrees with the model mass",
                ));
            }
            let denominator = bind_scalars(denominator, &bindings).expand();
            if denominators
                .iter()
                .any(|previous| (&denominator - previous).together().is_zero())
            {
                return Err(unsupported(
                    "repeated loop propagators require reduction with propagator powers",
                ));
            }
            denominators.push(denominator);
            loop_edges.insert(*edge);
            for mu in 0..4 {
                let physical_basis = labels
                    .iter()
                    .map(|leg| {
                        components
                            .get(leg)
                            .map(|row| row[mu].clone())
                            .ok_or_else(|| {
                                error("routed external leg is absent from amplitude inputs")
                            })
                    })
                    .collect::<RusticolResult<Vec<_>>>()?;
                propagator_outputs.push(
                    signature
                        .external
                        .apply(&physical_basis)
                        .map_err(error)?
                        .unwrap_or(Atom::Zero),
                );
            }
            propagator_outputs.push(mass_squared);
        }
        if loop_edges.is_empty() {
            return Err(unsupported(
                "one-loop diagram has no loop-dependent propagator",
            ));
        }
        let loop_product = loop_denominator_product(diagram, &loop_edges, &labels)?;
        // The amplitude already contains the authoritative graph factor and
        // all local numerators. Cancel only its loop poles, leaving bridges.
        let coefficient = bind_scalars(&(term.expression() * loop_product).together(), &bindings);
        let coefficient = term
            .with_checked_expression(coefficient)
            .map_err(error)?
            .simplify_algebra(&AlgebraSettings::default())
            .map_err(error)?
            .contract(ContractSettings::default())
            .map_err(error)?;
        let coefficient = coefficient.expression().together();
        if contains_loop_momentum(&coefficient) {
            return Err(unsupported(
                "residual loop-momentum dependence requires nonzero-rank numerator preparation",
            ));
        }
        if inputs.iter().any(|input| coefficient.contains(input)) {
            return Err(error("model uses a reserved momentum input symbol"));
        }
        let offset = outputs.len();
        outputs.push(component_kinematics.apply(&coefficient));
        outputs.extend(propagator_outputs);
        diagrams.push(DiagramLayout {
            offset,
            propagators: loop_edges.len(),
        });
    }
    for expression in &outputs {
        require_exact(expression, "prepared evaluator output")?;
    }
    let exact = Atom::evaluator_multiple(&outputs, &inputs)
        .cores(1)
        .build()
        .map_err(error)?;
    Ok(PreparedScalarLoop {
        momentum_legs,
        evaluator_state: encode_exact_evaluator_state(&exact)?,
        diagrams,
    })
}
