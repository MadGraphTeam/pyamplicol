// Live report. Measured values are read from the accompanying JSON snapshot.
// Compile from this directory: typst compile benchmarks.typ benchmarks.pdf
#let data = json("data/measurements.json")
#let navy = rgb("#203c60")
#let blue = rgb("#356b92")
#let pale = rgb("#edf3f8")
#let grey = luma(95)
#let rule = luma(215)
#set document(title: "pyAmpliCol — one-loop implementation and benchmarks", author: "pyAmpliCol development team")
#set page(paper: "a4", margin: (x: 1.65cm, top: 1.65cm, bottom: 1.7cm), numbering: "1 / 1", header: context {
  if counter(page).get().first() > 1 {
    text(8pt, fill: grey)[pyAmpliCol · one-loop development #h(1fr) #data.date]
    v(3pt)
    line(length: 100%, stroke: 0.4pt + rule)
  }
})
#set text(font: "Libertinus Serif", size: 10.5pt, lang: "en")
#set par(justify: true, leading: 0.61em)
#set heading(numbering: none)
#show heading.where(level: 1): it => {
  v(2pt)
  block(text(17pt, weight: "bold", fill: navy, it.body))
  v(3pt)
}
#show heading.where(level: 2): it => {
  v(3pt)
  block(text(11.5pt, weight: "bold", fill: navy, it.body))
}
#show raw: set text(font: "DejaVu Sans Mono", size: 8pt)
#show link: set text(fill: blue)
#show figure.where(kind: table): set figure.caption(position: top)
#let note(body) = block(width: 100%, fill: pale, inset: 10pt, radius: 3pt, text(9.4pt, body))
#let small(body) = text(size: 8.7pt, fill: grey, body)
#let section-label(s) = text(8.4pt, fill: blue, weight: "semibold", tracking: 0.7pt, s)
#let fmt(x, digits: 1) = {
  if x == none { return [—] }
  let parts = str(calc.round(x, digits: digits)).split(".")
  if digits == 0 { return parts.first() }
  let decimal = if parts.len() > 1 { parts.at(1) } else { "" }
  parts.first() + "." + decimal + "0" * calc.max(0, digits - decimal.len())
}
#let label(key) = (
  dy: [$u overline(u) -> e^- e^+$],
  uudd: [$u overline(u) -> d overline(d)$],
  tt: [$u overline(u) -> t overline(t)$],
  qqgg: [$u overline(u) -> g g$],
  gg: [$g g -> g g$],
).at(key)
#let names(key) = (dy: "Photon-only Drell–Yan", uudd: "Distinct-flavour quarks", tt: "Stable top pair", qqgg: "Quark annihilation", gg: "Gluon scattering").at(key)
#let timed(c, b) = c.at("timings", default: (:)).at(str(b), default: (:)).at("median_us_per_point", default: none)
#let cell(body, dim: false) = text(size: 8.8pt, fill: if dim { grey } else { black }, body)
#let tab(columns, left-columns: (0,), ..cells) = {
  set par(justify: false, leading: 0.35em)
  set text(size: 8.7pt)
  table(columns: columns, inset: (x: 5pt, y: 6pt),
    stroke: (x, y) => (top: if y > 1 { 0.4pt + luma(225) } else { none }),
    fill: (x, y) => if y == 0 { navy } else if calc.rem(y, 2) == 0 { rgb("#f5f7f9") } else { none },
    align: (x, y) => if x in left-columns { left + horizon } else { right + horizon },
    ..cells.pos(),
  )
}
#let th(body) = text(fill: white, size: 8.1pt, weight: "semibold", body)
#let reference(c, provider) = data.references.at(c.case, default: (:)).at("timings", default: (:)).at("32", default: (:)).at(provider, default: (:)).at("median_us_per_point", default: none)
#let mlstage(c, field) = data.references.at(c.case, default: (:)).at("timings", default: (:)).at("32", default: (:)).at("madloop-instrumented", default: (:)).at("stages", default: (:)).at(field, default: (:)).at("median_us_per_point", default: none)
#let stages(c, field) = data.stages.at(c.case, default: (:)).at(field, default: none)

#align(center)[
  #v(3pt)
  #text(25pt, weight: "bold", fill: navy)[pyAmpliCol at one loop]
  #v(-2pt)
  #text(12.5pt, fill: grey)[Implementation and live performance report]
  #v(2pt)
  #text(9pt, fill: grey)[#data.date · revision #data.revision · #data.host]
]
#v(9pt)
#note[
  *First development snapshot.* The numbers below evaluate complete Born–loop
  interference for the listed internal QCD controls: all physical helicities,
  full SU(3), UV counterterms, model-supplied $R_2$, and all three Laurent
  coefficients. Native batched arithmetic is driven by the current Python
  coordinator. These are measured implementation diagnostics; the matched
  MadLoop/Recola/OpenLoops speed gates have not been run.
]

= Complete evaluation in binary64
Each cell is *microseconds per phase-space point*, the median of five warm
batch calls. The batch repeats three frozen, valid control points. It does not
reuse computed event results. Exact decimal ingress and Python batch scheduling
are inside the timer; output formatting and reference comparisons are outside.

#figure(kind: table, caption: [Warm complete runtime. $B$ is the number of physical phase-space points in one call. All rows use model-rule $R_2$.],
  tab((1.5fr, 1fr, 1fr, 1fr, 1fr),
    table.header(th[Process], th[$B=1$], th[$B=8$], th[$B=32$], th[$B=128$]),
    ..data.cases.map(c => (label(c.case), fmt(timed(c, 1)), fmt(timed(c, 8)), fmt(timed(c, 32)), fmt(timed(c, 128)))).flatten(),
  )
)

#figure(kind: table, caption: [Cold construction and first evaluation, measured separately. One cold observation per process; no statistical uncertainty is inferred.],
  tab((1.5fr, 1fr, 1fr, 1fr),
    table.header(th[Process], th[Generation / s], th[First $B=3$ / ms], th[Peak RSS / MiB]),
    ..data.cases.map(c => (label(c.case), fmt(c.at("generation_s", default: none), digits: 2), fmt(if "first_evaluation_s" in c { 1000*c.first_evaluation_s } else { none }, digits: 1), fmt(c.at("peak_rss_mib", default: none), digits: 0))).flatten(),
  )
)

*Generation* includes source UFO capture/lowering, graphs, colour and recurrence
preparation, counterterm matching, and creation of JIT/reducer plans. Imports,
dependency installation and the first evaluation are excluded. Lazy first-call
work is therefore visible separately. Peak RSS is the process high-water mark
across construction and all batch tests, not an event-buffer estimate.

#small[
  Development build: Rust dev profile, local module opt3 / dependencies opt2,
  no LTO; dev assertions and overflow checks retained. Community opt2; SymJIT.
  This is not a frozen release-performance build. One pinned core (CPU 382), one thread,
  shared AMD EPYC 9754 host. Five calls describe local variation only. Source
  capture and cold plans are rebuilt per process. “—” means not measured in this
  snapshot. Real-mass EW, higher multiplicity and direct-$R_2$ timings remain to
  be added under this same protocol.
]

#pagebreak()
#section-label[MEASUREMENTS · COMPONENT BOUNDARIES]
= Where the event time goes
The requested decomposition separates numerator work, integrand reduction and
scalar master integrals. A complete event also needs states, kinematics,
Born weighting, UV/$R_2$ currents and output assembly. Those costs must remain
visible; the three core columns need not sum to the end-to-end time.

#figure(kind: table, caption: [pyAmpliCol at $B=32$, in µs per point. Stage and “instr.” columns are medians of five instrumented calls; “total” repeats the independent uninstrumented baseline. Component medians need not sum to the median instrumented total.],
  tab((1.4fr, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr),
    table.header(th[Process], th[Numerator], th[NinjaRS\ reduction], th[Scalar\ masters], th[Other], th[Instr.\ total], th[Complete\ total]),
    ..data.cases.map(c => (label(c.case), fmt(stages(c, "numerator_us")), fmt(stages(c, "reduction_us")), fmt(stages(c, "masters_us")), fmt(stages(c, "other_work_us")), fmt(stages(c, "instrumented_total_us")), fmt(timed(c, 32)))).flatten(),
  )
)

#figure(kind: table, caption: [Fresh reference performance at $B=32$, in µs per point, on the same control stream and pinned CPU. Full physical coefficients agree. Input and stability policies differ as described below; these are development comparisons.],
  tab((1.5fr, 1fr, 1fr, 0.9fr, 0.9fr, 0.9fr),
    table.header(th[Process], th[MadLoop\ numerator], th[MadLoop\ reduction\ + masters], th[MadLoop\ total], th[Recola\ total], th[OpenLoops\ total]),
    ..data.cases.map(c => (label(c.case), fmt(mlstage(c, "loop_coefficients")), fmt(mlstage(c, "reduction_masters")), fmt(reference(c, "madloop")), fmt(reference(c, "recola")), fmt(reference(c, "openloops")))).flatten(),
  )
)

== Timer definitions
*Numerator* is loop coefficient DAG execution plus reducer numerator callbacks
and coefficient-head preparation. *Reduction* excludes callbacks and scalar
integrals. *Masters* is the actual oneloopmaster adapter time, with its existing
cache policy. *Other* contains states, exact kinematics, Born and UV/$R_2$
work, weighting, assembly, transport and clock overhead. Instrumented components
and uninstrumented runtime are separate observations; neither is rescaled to
force agreement. Raw five-sample variation is retained with the report.

MadLoop coefficient construction excludes shared wavefunctions supplied by
HELAS; its loop-CT call window includes reducer interfaces, masters and retries.
Recola/OpenLoops totals use native public calls in compiled loops. Provider
input parsing is excluded; pyAmpliCol includes exact decimal ingress and Python
batch scheduling. Provider rescue stays enabled where supplied; pyAmpliCol
has no rescue here. Instrumented stage clocks are separate from original-binary
totals. The current complete totals are slower than MadLoop in every listed case.

#note[
  *Acceptance is still open.* On each designated high-multiplicity process,
  pyAmpliCol must be faster than MadLoop and at most $1.30$ times each available
  matched Recola and OpenLoops result, for warm single-point latency and native
  batch throughput. The faster complete, validated SM $R_2$ strategy may be used.
  A slow process cannot be hidden by a geometric mean. These measurements
  do not establish performance acceptance.
]

== How this report will evolve
Replace missing cells only with matched measurements. Keep generation, first
evaluation and warmed runtime separate. Add distinct frozen event streams,
paired provider timing blocks, rescue rates, uncertainty and memory before
evaluating a performance gate. Keep historical diagnostics tied to their own
revision instead of merging them into the current table.

#pagebreak()
#section-label[ARCHITECTURE · PHYSICAL CONTRACT]
= The quantity being computed
The new engine targets one-loop amplitudes interfered with a Born amplitude.
It does not compute the squared one-loop amplitude and does not admit
loop-induced production. A Born zero at an individual point or helicity remains
a valid event of a supported process.

For Born order $a$, loop order $b$ and squared coupling order $s=a+b$, the
ordinary uncorrelated observable is
$
  V_(s,k) = cal(N) sum_(a+b=s) 2 Re[B_a^dagger G_(B L) L_(b,k)],
  quad k in {0,-1,-2}.
$
The rectangular matrix $G_(B L)$ connects the actual Born and loop colour
bases. The normalization $cal(N)$ includes declared initial averages and final
identical-particle factors. Couplings are included; the result is neither
divided by the Born value nor normalized by an extracted strong coupling.

The returned coefficient order is *(finite, single pole, double pole)* in
the MadLoop convention,
$
  V = C_epsilon (V_0 + V_(-1)/epsilon + V_(-2)/epsilon^2),
  quad C_epsilon = (4 pi)^epsilon / Gamma(1-epsilon).
$
The finite conversion used in the matched Recola controls is
$V_0^"ML" = V_0^"Recola" + (pi^2/6) V_(-2)$; both poles are unchanged.
Such conversions act on the Laurent series, not on a process-dependent fitted
factor. Scheme, scale and finite renormalization conventions are retained
separately.

== Coupling selection is a graph property
`loop_coupling_orders` requests perturbative corrections. Eligibility depends
on the actual loop interactions and internal species, followed by explicit
Born–loop pairings. An order difference alone cannot identify the correct
graphs. In the mixed four-quark control,
$
  B = B_(20)+B_(02), quad L=L_(40)+L_(22)+L_(04),
$
the squared order $(4,2)$ receives both $B_(20)^* L_(22)$ and
$B_(02)^* L_(40)$. Their identities survive through counterterm matching and
output assembly. Joint QCD/QED selection also admits mixed graphs absent from
either singleton selection. Independent MadLoop graph controls give 16 QCD,
15 QED and 35 joint loops for the retained mixed model.

== What the measured processes include
#tab((1.6fr, 1fr, 1fr), left-columns: (0, 2),
  table.header(th[Control], th[Initial / identical\ normalization], th[Physical completion]),
  label("dy"), [$1/36$], [Photon Born; QCD virtual],
  label("uudd"), [$1/36$], [Local UV and $R_2$],
  label("tt"), [$1/36$], [Local and external-field UV; $R_2$],
  label("qqgg"), [$1/72$], [Local/field UV; $R_2$],
  label("gg"), [$1/512$], [Local/field UV; $R_2$],
)

The QCD scattering controls use $alpha_s=0.118$, $mu_R=1000$ GeV,
stable $m_t=173$ GeV, five renormalization flavours and six quarks in loops;
the other quark masses vanish under explicit control restrictions. Drell–Yan
uses $alpha^(-1)=132.507$. Initial spin and colour are averaged, and physical
external helicities are summed. The two final-gluon controls include $1/2$.

#pagebreak()
#section-label[ARCHITECTURE · MODEL AND COUNTERTERMS]
= Preserve the model before lowering it
Loop models contain information that a tree-only loader can discard:
Laurent-valued parameters and couplings, UV and $R_2$ categories, loop-particle
groups, external-field factors and duplicate vertex names. The new raw model
retains positional declaration identities and these fields before constructing
the exact scalar and covariant-kernel representations.

#v(5pt)
#grid(columns: (1fr, auto, 1fr, auto, 1fr), gutter: 6pt,
  note[#set par(justify: false)
    *Raw source* #linebreak() Exact declarations #linebreak() Species and loop groups], align(horizon)[$arrow.r$],
  note[#set par(justify: false)
    *Prepared model* #linebreak() Scalar programs #linebreak() Colour × Lorentz entries], align(horizon)[$arrow.r$],
  note[#set par(justify: false)
    *Process plan* #linebreak() Admitted graphs #linebreak() Matched UV / $R_2$ / fields],
)
#v(5pt)

== Exactness begins at input
Statically identifiable source literals are preserved as text, including long
decimal and Laurent coefficients. String-valued expressions remain exact.
Arbitrary Python computations or mutations do not gain an exactness claim
merely because their imported result is a number. Explicit exact runtime
overrides and fixed parameters flow through the same retained scalar owner.

Symbolica performs substitution, series extraction and expression preparation.
Source helper functions and their branch semantics are retained. Each selected
scalar has a value and an active diagnostic expression; native evaluation
checks both. A nonfinite or unsupported active branch cannot silently inherit
a successful amplitude status. Per-point renormalization scales reach the
same scalar program used by counterterms.

== Tensor structure and physical frame
Each basis entry retains its scalar coefficient, native Lorentz tensor,
native colour tensor and ordered particle ports. Multi-colour quartic vertices
remain sums of local terms. There is no reconstruction of tensor algebra in
pyAmpliCol: Idenso/Spenso/FeynKit own contractions, traces, component libraries
and index transformations.

Source spinor slots and the native physical wavefunction convention require an
explicit, bounded frame map. The FFV map renames typed external Dirac
ports simultaneously. The newly admitted bounded FFS map also exchanges
`ProjP`/`ProjM`, with 580 independent ALOHA controls; the FFV map and propagators
remain unchanged. Neither map rewrites momentum labels or supplies a universal
gamma-five transpose. Unvalidated source structures retain an explicit boundary.

== Counterterms follow admitted loops
UV-tree terms, local loop counterterms and external-field factors have different
eligibility rules. A standalone counterterm tree is insufficient evidence that
its loop correction belongs to the request. Local $R_2$/UV matching retains the
actual attachment currents, ordered binding legs, local coupling order and
allowed loop-species alternatives. Wildcards and repeated alternatives preserve
their source semantics and multiplicity. Fresh native tree graphs provide the
insertion signs and propagators.

External-field factors multiply the applicable Born currents with each physical
leg retained. Local and field UV remain separately inspectable, then join the
same ordered interference. Model-rule $R_2$ currents already contain their loop
normalization; the assembly does not multiply them by a second loop measure.

The bounded Gmu continuation offers an explicit `ufo-standard` logarithm
convention. The default preserves the source helper; either choice retains
the original model and does not certify complete CMS physics.

#note[
  *Evidence boundary.* Complete bounded QCD controls and real-mass neutral-current charged-lepton
  EW components are validated. That does not certify every rule in a supplied
  UFO, arbitrary restriction cards, all gauges, or general BSM renormalization.
]

#pagebreak()
#section-label[ARCHITECTURE · RECURRENCE AND FAMILIES]
= Local tensors, reusable coefficient currents
The production direction is a dedicated loop recurrence. FeynKit supplies the
graphs, directed incidence, loop signs, symmetry factors, cuts and affine
momentum routing. pyAmpliCol turns those local ingredients into a coefficient
dataflow graph and schedules its numerical evaluation.

A current retains the coefficients of a symmetric polynomial in the physical
loop momentum. For a local tensor $T$ and previous current $J$, the next step is
the contraction $T dot J$, followed by coefficient extraction using Symbolica.
Only the local transition is prepared symbolically. A whole-diagram symbolic
trace is used in small independent oracles, not as the numerical recurrence.

#note[
  *Coefficient dataflow.* External states and tree attachments feed local
  transitions; loop closure produces ordered coefficient outputs. Native saved
  evaluator instructions update these outputs in batches. Each original graph
  retains its colour terms, coupling sector and routing map even when it shares
  an identical numerical schedule with another graph.
]

== Topology remains attached to the numerator
Reduction needs a denominator set as well as a polynomial. Each graph carries
its routed propagators and a dependency-proved map into an integral family.
Numerators are transported through that map before combination. Cyclic or
reversed order is not inferred from a loose list of masses: momenta, incidence,
external attachments and the actual transformation must agree.

The family plan retains bridges and local tree denominators. Native graph
factors carry fermion and ghost signs. Multi-term local vertices are expanded
into ordered recurrence outputs, while the original graph/family identities
remain intact. This separates a numerical reuse opportunity from a physical
multiplicity or symmetry factor.

== Contract before reducing when linearity permits
For an interference observable, Born amplitudes and the rectangular colour
weights can multiply numerator coefficients before integration. Compatible
graphs, helicities and colour terms then share a reduction within their family
and coupling sector. The reducer sees the coefficient combination needed by
the observable, rather than every independent loop amplitude.

Complex weights are retained until the correctly directed bilinear is formed.
Taking a real part too early loses information needed by colour histories and
other off-diagonal observables. Counterterm interference uses the same Born
currents and colour conventions, with its own local scalar factors.

== Sharing that is safe under parameter updates
Compiled kernel reuse keys the saved instructions, settings, carrier precision
and output layout. Evaluators may share immutable compiled code while owning
independent work buffers. Whole-schedule numerical reuse additionally requires
identical ordered inputs under an exact model-binding proof. Equal floating
values at one point are insufficient.

The current process cache shares compatible Born, loop and counterterm kernels;
exact whole-schedule groups cover Born and loop execution. It does not cache
event results between calls. Complete unprojected model-rule QCD plans now
retain exact instructions and bindings across arithmetic views. Rebinding
creates fresh evaluators, reducers and buffers without repeating graph,
colour or coefficient preparation. Colour-weight changes invalidate the cached
plan. Source-model, direct-$R_2$ and formal-colour reuse remain outside this
checkpoint; persistent artifacts and broader subtree reuse are still open.

#small[
  The staged NinjaRS path supports up to six propagators and validated weighted
  rank through $n+1$; unsupported ranks reject. The owner's generic-any-$n$
  extension (`e4c16a7`) has been pulled. A separate consumer candidate is testing
  seven propagators in all three carriers; staged-module adoption and required
  high-multiplicity physics remain pending. No timing table uses that candidate.
]

#pagebreak()
#section-label[ARCHITECTURE · COLOUR AND OBSERVABLES]
= Full colour without dense event tensors
The current complete QCD path contracts colour at plan construction using
native fixed-SU(3) tensors. It forms the properly scoped bra–ket expression,
uses dependency colour simplification and caches the exact pair. The numerical
event path receives the resulting rectangular weights. Dense SU(3) components
remain an independent small-control oracle, not the production colour sum.

Closed residual contractions use the dependency's existing projector expansion,
trace/chain operations and canonicalization. Minimal upstream fixes address
specific demonstrated tensor-lowering or invariant-contraction defects. No
private group identities or numerical colour fitting are inserted into the
application.

== LC and NLC are structural projections
For a certified formal-$N_c$ model, all contributions belonging to one squared
order and operator family are combined before finding the common highest power
$P$. With $N_f$ held fixed,
$
  "LC": N_c^P, quad
  "NLC": N_c^P, N_c^(P-1), N_c^(P-2).
$
Odd suppression powers are retained. The same $P$ spans the relevant helicities,
epsilon sectors and source contributions; choosing a different leading power
for each term would change the approximation. Exact native algebra handles
Laurent coefficients and semantic $C_A,C_F,T_R$ relations.

Complete bounded quark-process colour projections have controls. The active
`loop_sm` four-gluon $R_2$ model contains fixed-$N_c=3$ coefficients. Its
full-SU(3) validity does not imply a formal continuation, and numerical constants
are never promoted heuristically to $N_c$. Validated direct completion can
provide a different continuation only within its certified domain.

== Directed colour and spin sources
Correlated virtual observables require both rectangular cross terms. For
operator histories $A$ and $B$, their generic form is
$
  B_A^dagger G L_B + L_A^dagger G B_B.
$
For unequal histories this is not generally $2 Re(B_A^dagger G L_B)$; the
result can be complex. Existing colour-connection metadata and native charge
tensors provide the operator action and signs. Current internal controls compose
bounded histories with Born, bare loop, local counterterms and field factors.

Literal complex spin-source vectors enter the admitted physical external ports
without an implicit conjugation, normalization or projection. Spectator states
are summed and a replaced leg is counted once. The source/current frame and
crossing factors remain explicit. Scalar and massive-vector layouts reuse native
wavefunctions; a generic source API is not yet certified by these controls.

== Flavour mapping and FFT remain distinct work
An exact species-symmetry certificate now compares the entire retained ordinary,
UV, $R_2$ and external-field plan, including prepared native structures and
parameter bindings. Independent massless $d$ and $s$ catalogues pass; unequal masses,
Yukawas or UV logarithms reject. This is a prerequisite for mapping, not yet
external-leg, momentum, spin-source or colour-history transport.

Optional FFT contraction is an agreed feature but is not part of the measured
path. Its cost model, exact observable reconstruction and composition with the
other features remain acceptance gates.

#pagebreak()
#section-label[ARCHITECTURE · NATIVE BATCHES AND PRECISION]
= One numerical path, three real carriers
The internal numerical core uses binary64, DoubleFloat and arbitrary-precision
carriers throughout coefficient evaluation, kinematics, NinjaRS reduction,
scalar masters, counterterms and contractions. It does not compute a binary64
answer and promote it afterward. Fixed-carrier precision metadata follows the
actual numerical types; arbitrary precision carries its requested precision.

Exact decimal or rational input is parsed before carrier conversion. S-matrix
and admitted on-shell invariants are constructed through the exact input boundary;
source mass/coupling formulas are evaluated natively in the chosen carrier.
Controls with differences below binary64 resolution verify that DoubleFloat
and arbitrary precision retain the input information through the output.
Source scalar callbacks and their diagnostics use those same carriers.

== Batching is an execution contract
Points, helicities and coefficient components have explicit ordered layouts.
Native buffers retain original point identities through compaction, tail batches,
failure masks and result scatter. Changing sizes, empty batches and repeated
calls are covered. Python coordinates batch plans; it does not evaluate each
phase-space point in an interpreted numerical loop.

The coefficient scheduler uses bounded row tiles and reusable scratch storage.
Its present 16-row default is a measured development choice, not a universal
optimum. Dependency evaluators own their arithmetic workspaces. Binary64 can
use SymJIT; high-precision paths remain native batches without an unsupported
SIMD claim. Public standalone SDK integration is a separate unfinished layer.

== Reducer and master interfaces
NinjaRS receives the polynomial layout, routed denominator data, exact kinematic
invariants and carrier-appropriate inputs. The adapter retains weighted rank:
$mu^2$ counts as two powers of loop momentum. Separate explicit-epsilon sectors
reduce independently and combine by Laurent multiplication. A newer dense-$mu$
numerator adapter is available as an additive internal option; the headline
timings specify the actual `fast` engine they use.

The native module and Community producer use the same underlying numerical and
symbolic owners. Python distribution and Rust kernel version labels are recorded
separately. A genuine isolated development-package install now passes a public
ordinary-tree generation/evaluation smoke. Publishable dependency packaging,
loop artifacts and cross-language virtual SDK delivery remain open.

== Success, accuracy and rescue are different facts
A reducer's success flag is not an accuracy certificate. Native checks reject
nonfinite input, state, coefficient and counterterm values, preserve the original
failed point identity, and permit an explicit partial-result contract. Optional
cross-precision checks compare complete outputs and can rescue selected failed
or disagreeing points at higher precision without changing $R_2$ strategy.

The result records requested/evaluated precision, strategy, status and available
agreement evidence. Failed points cannot silently appear as zero or be declared
accurate. Existing bounded rescue controls are not a universal stability policy:
threshold choices, complete feature composition and adversarial tests remain
open. None of the headline runtime cells enables rescue or cross-precision
verification, and each is labelled accordingly.

#note[
  *Known numerical gate.* An equal-value, differently tracked arbitrary-precision
  mass construction exposed a scalar-box branch discrepancy in a CMS zero-width
  control. This is retained as a dependency-owner accuracy issue. Extra digits
  alone are not evidence that a branch-sensitive result is correct.
]

#pagebreak()
#section-label[ARCHITECTURE · RATIONAL TERMS]
= Two complete strategies, one observable
The model strategy combines the four-dimensional numerator contribution with
the model's effective $R_2$ rules and UV terms. The direct strategy instead
computes the required evanescent numerator remainder and retains the same UV
completion. The strategy is explicit in the result; a caller cannot relabel
an executed model result as direct.

Four-dimensional reduction already produces denominator-related rational terms.
The presence of $mu^2$ in a reducer interface therefore does not, on its own,
prove that numerator-origin $R_2$ is complete. The direct extension must account
for extra-dimensional momentum, metric/spin traces and explicit epsilon factors.

== Local evanescent state, not a whole-loop trace engine
For a certified closed vectorlike fermion cycle, the local component construction
uses dependency gamma matrices with one auxiliary evanescent slash. Odd auxiliary
powers survive every open transition; only the closed trace selects even parity.
Independent full-$D$ local-graph oracles check routed bubbles, triangles and boxes.
The auxiliary gamma-five realization is not a general physical chiral or
dimensional gamma-five prescription.

For the admitted massless Yang–Mills cycles, dependency metric and momentum
rules are continued to an explicit physical/aligned/spectator state space.
The remaining transverse-state multiplicity is retained symbolically in
$D=4-2epsilon$. Local cubic and quartic colour terms, closure, routing and
spectator weighting are checked independently. Ghost cycles keep their native
statistics and their ordinary bare contribution.

== Epsilon sectors matter after integration
If the numerator is $N_0+epsilon N_1+epsilon^2 N_2$ and each reduced sector
has finite/single/double coefficients $(F_j,S_j,D_j)$, the assembled result is
$
  V_0 = F_0+S_1+D_2, quad
  V_(-1)=S_0+D_1, quad V_(-2)=D_0.
$
Dropping explicit epsilon terms can therefore change the finite answer even
when the mu-dependent terms are retained. Native reduction controls exercise
this convolution in all three carriers. Source templates, full-graph algebra
and integrated physical results have separate checks.

== What is supported internally today
The complete retained full-colour $g g -> g g$ control admits the local direct
kernels, includes UV completion, and agrees with model-rule components and
independent reference results in all three arithmetic modes. Bounded
cross-precision verification and direct-strategy rescue are also implemented.
Public direct dispatch remains behind its integration gates.

Open fermion chains, general mixed-spin loops, massive gauge/Goldstone sectors,
physical axial or anomaly-sensitive structures and arbitrary BSM dimensional
extensions are not inferred from that success. Unsupported direct domains need
compatible model-rule completion. No universal massless FDH-to-HV shift is
assumed for massive EW or general models.

#note[
  *Selection and performance.* Automatic policy may prefer a certified direct
  strategy, but completeness is mandatory. Model and direct costs must be
  measured as standalone complete evaluations. The present headline table uses
  model rules throughout; a new direct-versus-model comparison is still due
  after recent colour and scheduling changes.
]

#pagebreak()
#section-label[VALIDATION · NEXT GATES]
= What this snapshot establishes
The measured controls are useful working vertical slices: model import,
graphs, local recurrence, full colour, native states, reduction, UV/$R_2$ and
ordered physical output all run together. Independent reference comparisons
separate bare, local UV, external-field UV and $R_2$ so cancellations in the
complete answer cannot conceal a wrong component.

#tab((1.4fr, 2.6fr), left-columns: (0, 1),
  table.header(th[Area], th[Current boundary]),
  [Complete QCD], [Internal DY, four-quark, top-pair, quark/gluon and gluon controls; all three carriers.],
  [Real-mass EW], [Source-owned neutral-current charged-lepton controls, including bounded massive muons; complete components and scale/parameter changes.],
  [CMS], [Shared exact continuation and source-semantic controls; independent finite UV/branch conventions and an AP master boundary remain open.],
  [Correlations / mapping], [Bounded directed/spin controls and exact species symmetry; general composition and mapping transport remain open.],
  [Public delivery], [A genuine development install passes the public tree smoke; loop artifacts, commands and SDK/UMAMI integration remain open.],
  [Performance], [Current development timings only; distinct-point matched provider gates and required high multiplicity remain open.],
)

== Required multiplicity and acceptance
The target includes selected $2 -> 5$ processes, with $2 -> 6$ as a stretch
goal. The common-provider set includes gluon jets, heavy-quark plus jets,
lepton-pair plus jets, and heavy-quark/lepton-pair production with a jet.
Five-final-parton gluon channels also require MadLoop/Recola controls; an
unavailable public OpenLoops channel is not invented for comparison.

The new generic-any-$n$ reducer still needs consumer validation and adoption;
seven-propagator physics is a separate gate. Rank above the supported $n+1$
domain must reject. Required progress also includes broader cold-plan coverage,
persistent artifacts, optional FFT,
complete correlation/mapping transport and broader certified model coverage.
These requirements remain visible even when a smaller control is fast.

== Independent evidence and reproducibility
The accompanying `data/measurements.json` contains the actual five timing samples,
revision, process counts, cold times and checksums behind the headline tables.
The frozen point fixtures and native reference drivers live in
`tools/loop_reference/`. The measured driver calls the complete internal
`evaluate_ordered_native` path; checks and decimal result conversion occur after
the event timer. Test durations and earlier bare-only profiles are not event
timings in this report.

Provider controls use MadLoop 3.7.0, Recola2 2.3.0 with its matched SM/Collier
model, and OpenLoops 2.1.5. Their independent component tests establish the
bounded normalization comparisons; only the fresh matched-host control timings enter
the current performance table, with their input and rescue asymmetries declared. This report follows the visual structure of
the NinjaRS benchmark while measuring a different object: a complete physical
interference, not a single diagram and helicity.

#small[
  Further reading: repository `docs/development/LOOP_MODEL_IR.md`,
  `docs/development/LOOP_DIRECT_R2.md`, `docs/loop-flavor-symmetry.md`, and
  `tools/loop_reference/README.md`;
  #link("https://arxiv.org/abs/1710.11452")[OpenLoops on-the-fly reduction] ·
  #link("https://arxiv.org/abs/1605.01090")[Recola] ·
  #link("https://arxiv.org/abs/1404.4783")[four-dimensional formulation] ·
  #link("https://cp3.irmp.ucl.ac.be/projects/madgraph/wiki/MadLoopStandaloneLibrary")[MadLoop standalone convention].
]

#v(5pt)
#note[
  *Living document.* Update the source, measured data and compiled PDF together
  after each implementation milestone. Keep incomplete rows and capability
  limits explicit. The completion criterion is the full physics, feature,
  precision, packaging and per-process performance contract—not the existence
  of this first report.
]
