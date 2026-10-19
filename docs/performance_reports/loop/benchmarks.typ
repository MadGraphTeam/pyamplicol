// Live report. Measured values are read from the accompanying JSON snapshot.
// Compile from this directory: typst compile benchmarks.typ benchmarks.pdf
#let data = json("data/measurements.json")
#let report-date = "2026-10-19"
#let sharing = json("data/local-sharing-experiment.json")
#let arena = json("data/local-arena-experiment.json")
#let cold = json("data/provider-cold.json")
#let colours = json("data/colour-measurements.json")
#let projectors = json("data/local-projector-experiment.json")
#let bound-projectors = json("data/projector-binding-benchmark.json")
#let navy = rgb("#203c60")
#let blue = rgb("#356b92")
#let pale = rgb("#edf3f8")
#let grey = luma(95)
#let rule = luma(215)
#set document(title: "pyAmpliCol — one-loop implementation and benchmarks", author: "pyAmpliCol development team")
#set page(paper: "a4", margin: (x: 1.65cm, top: 1.65cm, bottom: 1.7cm), numbering: "1 / 1", header: context {
  if counter(page).get().first() > 1 {
    text(8pt, fill: grey)[pyAmpliCol · one-loop development #h(1fr) #report-date]
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
#let sharing-ms(batch, stage, mode) = fmt(sharing.timings.at(str(batch)).at(stage).at(mode).median_us_per_point / 1000, digits: 2)
#let arena-ms(batch, stage, mode) = fmt(arena.timings.at(str(batch)).at(stage).at(mode).median_us_per_point / 1000, digits: 2)
#let projector-ms(stage, mode) = fmt(projectors.timings.at("128").at(stage).at(mode).median_us_per_point / 1000, digits: 2)
#let label(key) = (
  dy: [$u overline(u) -> e^- e^+$],
  uudd: [$u overline(u) -> d overline(d)$],
  tt: [$u overline(u) -> t overline(t)$],
  qqgg: [$u overline(u) -> g g$],
  gg: [$g g -> g g$],
  qqggg: [$u overline(u) -> g g g$],
  "ee-mumu-ew": [$e^- e^+ -> mu^- mu^+$],
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
#let stage-batch(c) = data.stages.at(c.case).batch_size
#let mlstage(c, field) = data.references.at(c.case, default: (:)).at("timings", default: (:)).at(str(stage-batch(c)), default: (:)).at("madloop-instrumented", default: (:)).at("stages", default: (:)).at(field, default: (:)).at("median_us_per_point", default: none)
#let stages(c, field) = data.stages.at(c.case, default: (:)).at(field, default: none)

// Comparison cards follow NinjaRS: value, named reference and multiplier.
#let palette = gradient.linear(rgb("#5aae61"), rgb("#d9f0d3"), white, rgb("#fddbc7"), rgb("#d6604d"))
#let ratio-fill(r) = if r == none { none } else {
  palette.sample(calc.clamp(0.5 + calc.log(r, base: 2) / 8, 0, 1) * 100%)
}
#let provider-name(p) = (madloop: "ML", recola: "Recola", openloops: "OL").at(p)
#let provider-time(c, b, p) = data.references.at(c.case, default: (:)).at("timings", default: (:)).at(str(b), default: (:)).at(p, default: (:)).at("median_us_per_point", default: none)
#let fastest(c, b) = {
  let found = ("madloop", "recola", "openloops").map(p => (name: provider-name(p), value: provider-time(c, b, p))).filter(r => r.value != none)
  if found.len() == 0 { return none }
  found.sorted(key: r => r.value).first()
}
#let value-fmt(x) = {
  if x == none { return [—] }
  let digits = if x >= 1000 { 0 } else if x >= 100 { 1 } else { 2 }
  let s = fmt(x, digits: digits)
  if x >= 10000 {
    let rest = str(int(calc.round(x)))
    let groups = ()
    while rest.len() > 3 {
      groups.insert(0, rest.slice(rest.len() - 3))
      rest = rest.slice(0, rest.len() - 3)
    }
    groups.insert(0, rest)
    return groups.join(sym.space.thin)
  }
  s
}
#let header(body) = text(font: "DejaVu Sans", size: 8pt, fill: white, weight: "bold", body)
#let legend = align(center)[
  #box(width: 9cm, height: 0.27cm, fill: palette, radius: 2pt)
  #v(-5pt)
  #box(width: 9cm, text(size: 7.3pt)[×1/16 #h(1fr) ×1/4 #h(1fr) ×1 #h(1fr) ×4 #h(1fr) ×16])
  #v(-3pt)
  #text(size: 8pt, fill: luma(75))[Logarithmic scale · lower is faster · white is parity · red is slower]
]

// One process/provider grid, continued as validated measurements are added.
#let warm-block(c, p, b) = {
  let value = if p == "pyamplicol" { timed(c, b) } else { provider-time(c, b, p) }
  let best = fastest(c, b)
  let ratio = if value == none or best == none { none } else { value / best.value }
  block(width: 100%, fill: ratio-fill(ratio), inset: (x: 5pt, y: 5pt), radius: 2pt)[
    #set par(justify: false, leading: 0.15em)
    #text(size: 7pt, fill: luma(70))[$B=#b$] #h(1fr) #text(font: "DejaVu Sans", size: 11.2pt, weight: "bold", value-fmt(value))
    #linebreak()
    #if ratio != none {
      text(size: 7.1pt)[*×#fmt(ratio, digits: 2)* vs #best.name · #value-fmt(best.value) µs]
    } else { text(size: 7.1pt, fill: grey)[Timing not recorded] }
  ]
}
#let detail-line(name, value) = {
  text(size: 7.2pt, fill: luma(65), name)
  h(1fr)
  text(font: "DejaVu Sans", size: 7.4pt, weight: "semibold", value-fmt(value))
  linebreak()
}
#let provider-box(c, p) = table.cell(inset: (x: 3pt, y: 7pt), align: top, {
  set par(justify: false, leading: 0.25em, spacing: 0pt)
  set block(spacing: 0pt)
  warm-block(c, p, 1)
  v(3pt)
  warm-block(c, p, 128)
  v(6pt)
  let observation = cold.cases.at(c.case).at(p, default: (:))
  let seconds = observation.at("seconds", default: none)
  if p == "pyamplicol" {
    text(size: 7.3pt, fill: navy, weight: "bold")[Generation #fmt(c.generation_s, digits: 2) s]
    linebreak()
    text(size: 6.8pt, fill: grey)[source + complete plan]
    linebreak()
    text(size: 6.8pt, fill: grey)[first $B=3$: #fmt(c.first_evaluation_s, digits: 3) s]
    linebreak()
    text(size: 6.8pt, fill: grey)[peak RSS #fmt(c.peak_rss_mib, digits: 0) MiB]
  } else if p == "madloop" {
    text(size: 7.3pt, fill: navy, weight: "bold")[Generation #if seconds == none [—] else [#fmt(seconds, digits: 2) s]]
    linebreak()
    text(size: 6.8pt, fill: grey)[#if seconds == none [not yet recorded] else [export + static compilation]]
    if seconds != none and c.case == "dy" {
      linebreak()
      text(size: 6.8pt, fill: grey)[includes bundled reducers]
    }
  } else if p == "recola" {
    text(size: 7.3pt, fill: navy, weight: "bold")[Generation #if seconds == none [—] else [#fmt(seconds, digits: 3) s]]
    linebreak()
    text(size: 6.8pt, fill: grey)[#if seconds == none [matched control unavailable] else [parameters + define + generate]]
  } else {
    text(size: 7.3pt, fill: navy, weight: "bold")[Setup #if seconds == none [—] else [#fmt(seconds, digits: 3) s]]
    linebreak()
    text(size: 6.8pt, fill: grey)[#if seconds == none [matched control unavailable] else [prebuilt library · register + start]]
    if seconds != none {
      linebreak()
      text(size: 6.8pt, fill: grey)[source generation not timed]
    }
  }
  if p == "pyamplicol" or p == "madloop" {
    v(6pt)
    line(length: 100%, stroke: 0.4pt + rule)
    v(3pt)
    text(size: 7.1pt, fill: navy, weight: "bold")[Stages at $B=#stage-batch(c)$ · µs/point]
    linebreak()
    if p == "pyamplicol" {
      detail-line("Numerator", stages(c, "numerator_us"))
      detail-line("NinjaRS only", stages(c, "reduction_us"))
      detail-line("Scalar masters", stages(c, "masters_us"))
      detail-line("Other work", stages(c, "other_work_us"))
      detail-line("Clocked total", stages(c, "instrumented_total_us"))
    } else {
      detail-line("Numerator", mlstage(c, "loop_coefficients"))
      detail-line("Reduction + masters", mlstage(c, "reduction_masters"))
      text(size: 6.8pt, fill: grey)[Shared HELAS is outside the numerator clock.]
    }
  }
})
#let provider-grid(rows) = {
  set par(justify: false, leading: 0.25em)
  table(columns: (0.77fr, 1.18fr, 1.18fr, 1.18fr, 1.18fr),
    align: top, inset: (x: 5pt, y: 8pt),
    stroke: (x, y) => (top: if y > 1 { 0.6pt + luma(205) } else { none }, left: if x > 0 and y > 0 { 0.45pt + luma(224) } else { none }),
    fill: (x, y) => if y == 0 { navy } else { none },
    table.header(header[Process], header[pyAmpliCol], header[MadLoop], header[Recola], header[OpenLoops]),
    ..rows.map(c => (
      table.cell(align: top, {
        v(5pt)
        text(size: 10.5pt, weight: "semibold", label(c.case))
        linebreak()
        if c.case == "dy" { text(size: 7pt, fill: grey)[photon only]; linebreak() }
        if c.case == "ee-mumu-ew" { text(size: 7pt, fill: grey)[full EW · Gmu]; linebreak() }
        text(size: 7pt, fill: grey)[#c.counts.loop_graphs #if c.counts.loop_graphs == 1 [loop] else [loops]\ #c.counts.families #if c.counts.families == 1 [family] else [families]]
      }),
      ..("pyamplicol", "madloop", "recola", "openloops").map(p => provider-box(c, p)),
    )).flatten(),
  )
}

#align(center)[
  #v(3pt)
  #text(29pt, weight: "bold", fill: navy)[pyAmpliCol at one loop]
  #v(-2pt)
  #text(12.5pt, fill: luma(85))[Batched Born–loop interference · implementation & live benchmarks]
  #v(3pt)
  #text(8.5pt, fill: luma(110))[#report-date · timings #data.date · AMD EPYC 9754]
]
#v(8pt)
#note[
  *One grid, four providers.* Each coloured box gives *µs per point* at $B=1$
  or $B=128$, plus its multiplier against the fastest existing matched reference
  (ML, Recola or OL). Neutral lines show generation/setup and separately clocked
  stages at the indicated batch size. Binary64 results include Born, all helicities, full SU(3),
  UV, model-rule $R_2$ and all three Laurent coefficients.
]

#v(6pt)
#provider-grid(data.cases.slice(0, 3))
#v(7pt)
#legend

#pagebreak()
#section-label[MEASUREMENTS · SAME GRID, CONTINUED]
= Complete evaluation · remaining processes
#small[Warm boxes: µs per point at $B=1$ and $B=128$. Neutral preparation: seconds.
Instrumented stage lines: $B=32$ for two-to-two, $B=128$ for five-leg; no stage speed ratios.]
#v(5pt)
#provider-grid(data.cases.slice(3, 6))
#v(7pt)
#small[Original five processes retain revision #data.revision; the five-leg row uses
f89249d2. These are complete model-rule development observations; see the continued
grid and measurement boundaries on the next page.]

#pagebreak()
#section-label[MEASUREMENTS · SAME GRID, CONTINUED]
= Real-mass electroweak control
#small[Full Gmu electroweak correction, real masses, source compiler revision 85fb0900.
Warm boxes: µs per point. Generation: seconds. Separate stage clocks: $B=128$.]
#v(5pt)
#provider-grid(data.cases.slice(6))
#v(7pt)
#small[The matched Recola setup retains actual poles and the same Gmu inputs.
MadLoop validates complete components; its timing and OpenLoops timing are not
recorded here. No provider speed is inferred from correctness tests.]
#v(4pt)
#small[The EW row uses $G_mu=1.16639 times 10^(-5)$ $"GeV"^(-2)$, $m_W=80.419$,
$m_Z=91.188$, $m_H=125$, $m_t=173.3$ GeV, zero widths and light masses,
and $mu_R=1000$ GeV. Its full source counterterms are retained.]
#v(7pt)
#grid(columns: (1fr, 1fr), gutter: 13pt,
  [#text(weight: "bold", fill: navy)[Numerator, reduction and masters]
   #linebreak()
   #text(size: 8.6pt)[pyAmpliCol numerator includes loop DAGs, callbacks and coefficient-head
   preparation. NinjaRS excludes callbacks and masters; other work includes states,
   Born, UV/$R_2$, exact kinematics, assembly and transport. ML excludes shared HELAS
   from numerator and includes interfaces/retries in reduction + masters.]],
  [#text(weight: "bold", fill: navy)[Separate clocks, separate observations]
   #linebreak()
   #text(size: 8.6pt)[Warm totals use uninstrumented calls. Stage medians come from separate
   clocked calls and need not sum to the median clocked total. Master clocks retain
   the adapter cache policy. Rust dev: local opt3 / dependencies opt2, checks on,
   no LTO; Community opt2. Raw timing samples are retained.]],
)
#v(7pt)
#text(size: 8.2pt)[
  Five warm calls on repeated three-point streams; no cached event results in
  pyAmpliCol. CPU 382, one thread/shared host. pyAmpliCol includes decimal ingress/
  Python scheduling with rescue off; providers retain native-array input and normal
  rescue/cache policies. Formatting is excluded. Preparation: CPU 380, ML DY 381,
  Recola DY and EW 382; no cache flush or uncertainty estimate. Recola photon-only DY
  passes analytic checks; OL DY is absent.
]
#v(3pt)
#text(size: 8.6pt)[
  *Development comparison:* the measured QCD rows remain slower than ML. Acceptance requires
  distinct points, matched boundaries/stability, faster than ML and within $1.30 times$
  Recola/OL per designated high-multiplicity case; generation has no gate.
  OL actual-pole mode runs the amplitude three times with Collier cache off.
  Original loop kernels use `-O0`; a separate `-O3` gg trial showed no clear win.
]

#pagebreak()
#section-label[MEASUREMENTS · MATCHED LEADING COLOUR]
= Leading colour and its full-colour counterpart
#note[
  *An internal comparison.* Each warm cell pairs LC with a new full-colour
  measurement of the same process and $R_2$ strategy. Its colour and multiplier
  refer only to that full-colour run; no external provider enters this page.
  Both binary64 paths return Born and all three completed Laurent coefficients.
]
#let colour-warm(c, b) = {
  let lc = timed(c.lc, b)
  let full = timed(c.full, b)
  block(width: 100%, fill: ratio-fill(lc/full), inset: 9pt, radius: 3pt)[
    #set par(justify: false, leading: 0.25em)
    #text(size: 8pt, fill: grey)[LEADING COLOUR]
    #linebreak()
    #text(font: "DejaVu Sans", size: 15pt, weight: "bold", value-fmt(lc)) #text(size: 8pt)[µs/point]
    #v(4pt)
    #text(size: 9pt)[Full: *#value-fmt(full)* µs/point]
    #linebreak()
    #text(size: 8.5pt)[LC / full: *×#fmt(lc/full, digits: 2)*]
  ]
  if b == 128 {
    v(6pt)
    text(size: 7.5pt, fill: navy, weight: "bold")[Stages · LC / full · µs/point]
    linebreak()
    for (name,key) in (("Numerator","numerator_us"),("NinjaRS only","reduction_us"),("Masters","masters_us"),("Other","other_work_us"),("Clocked total","instrumented_total_us")) {
      text(size: 7.4pt, fill: grey, name)
      h(1fr)
      let slc = c.at("lc_stages",default: (:)).at(key,default: none)
      let sfull = c.at("full_stages",default: (:)).at(key,default: none)
      text(size: 7.5pt)[#value-fmt(slc) / #value-fmt(sfull)]
      linebreak()
    }
  }
}
#let colour-grid(rows) = table(columns: (1.1fr, 1.55fr, 1.55fr, 1.35fr), align: top,
  inset: (x: 5pt, y: 8pt),
  stroke: (x,y) => (top: if y > 1 { 0.5pt + rule } else { none }),
  fill: (x,y) => if y == 0 { navy } else { none },
  table.header(header[Process / strategy], header[Single point · $B=1$], header[Native batch · $B=128$], header[Generation · seconds]),
  ..rows.map(c => (
    { v(8pt); text(size: 12pt, weight: "bold", label(c.case)); linebreak();
      if c.case == "dy" { text(size: 8pt, fill: grey)[photon only]; linebreak() }; v(4pt);
      text(size: 8.5pt, fill: grey)[#if c.full.r2_strategy == "direct" [Direct $R_2$] else [Model-rule $R_2$]] },
    colour-warm(c,1), colour-warm(c,128),
    { v(8pt); text(size: 9pt)[LC: *#fmt(c.lc.generation_s,digits: 2)* s]; linebreak();
      text(size: 9pt)[Full: *#fmt(c.full.generation_s,digits: 2)* s]; v(7pt);
      text(size: 7.8pt, fill: grey)[First $B=3$, LC / full:\ #fmt(c.lc.first_evaluation_s,digits: 3) / #fmt(c.full.first_evaluation_s,digits: 3) s] },
  )).flatten(),
)
#v(9pt)
#colour-grid(colours.cases.slice(0,2))
#v(7pt)
#legend
#v(5pt)
#text(size: 9pt)[
  Independent fresh process for each colour mode, revision #colours.revision, CPU #colours.cpu,
  one thread/shared host. Five timed calls use the repeated three-point controls;
  decimal ingress and Python batch scheduling are included, checks and output
  formatting excluded. Generation includes source capture and the complete plan;
  first evaluation is separate. These are development observations, not an LC
  performance target or a replacement for the full-colour snapshot on pages 1–3.
]
#v(5pt)
#text(size: 9pt)[
  Fixed-$N_f$ LC keeps the common highest formal-$N_c$ power before setting $N_c=3$.
  Full and LC retain the current graph schedules; this is not yet numerator pruning.
  Quark controls use the fixed-SU(3) full path and formal LC path. The gluon control
  uses the certified direct strategy and formal algebra for both paths, avoiding
  an unsupported continuation of the model's four-gluon $R_2$ coefficients.
  Full components pass independent references; LC checks use the certified Born,
  pole and UV/field relations, with complete component reconstruction.
]
#pagebreak()
#section-label[MEASUREMENTS · SAME COLOUR GRID, CONTINUED]
= Leading colour · massive quarks and gluons
#small[Warm cells: µs per point. Neutral B128 stage pairs: LC / full, from separate
instrumented calls; medians need not add. Generation and first evaluation: seconds.]
#v(9pt)
#colour-grid(colours.cases.slice(2))
#v(8pt)
#legend
#v(7pt)
#note[
  *What is and is not measured.* Every timed call computes the complete selected
  observable. LC changes the retained formal-colour powers; current graph schedules
  still run. These same-strategy internal pairs do not compare direct and model
  $R_2$, nor replace the model-rule provider grid. Stage scopes match that grid:
  numerator includes DAGs and reducer callbacks/head preparation; NinjaRS excludes
  callbacks and scalar masters. Other work includes states, Born weighting,
  counterterms, kinematics, assembly and instrumentation.
]
#v(7pt)
#small[
  *Opt-in projector JIT.* Saved family bilinears now bind through the existing
  tiled coefficient plan when `projector_engine="jit"` is requested in binary64.
  The interpreter remains the default and the DoubleFloat/AP path. A fresh complete
  gluon check at `d6c05e08`, on 128 distinct exact energy-scaled control points,
  gave $B=128$ projection medians of
  #fmt(bound-projectors.projection_B128.interpreted.median_us_per_point / 1000, digits: 2) to
  #fmt(bound-projectors.projection_B128.jit.median_us_per_point / 1000, digits: 2) ms/point and
  complete calls of #fmt(bound-projectors.complete_B128.interpreted.median_us_per_point / 1000, digits: 2) to
  #fmt(bound-projectors.complete_B128.jit.median_us_per_point / 1000, digits: 2) ms/point.
  Five paired CPU379 blocks retain visible variation; independent physics gates
  passed unchanged. Saved ordering, retained/portable bindings, tail/empty batches
  and precision checks pass. JIT is not bit-exact; earlier output-wise DD evidence
  remains available. No algebra, arena or factorization change is included.
  These observations do not replace the timing tables.
]

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
  label("qqggg"), [$1/216$], [Local/field UV; $R_2$],
  label("ee-mumu-ew"), [$1/4$], [Full EW; real-mass Gmu; local UV/$R_2$],
)

The QCD scattering controls use $alpha_s=0.118$, $mu_R=1000$ GeV,
stable $m_t=173$ GeV, five renormalization flavours and six quarks in loops;
the other quark masses vanish under explicit control restrictions. Drell–Yan
uses $alpha^(-1)=132.507$. Initial spin and colour are averaged, and physical
external helicities are summed. Two final gluons include $1/2$, three include $1/6$.

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
Literal decimal and Laurent source text, exact overrides and fixed parameters
retain their scalar owner. Imported results of arbitrary Python computation or
mutation do not acquire exactness. Symbolica performs substitution, series and
expression preparation. Source helpers retain their branches; native evaluation
checks each value and active diagnostic. A nonfinite or unsupported branch cannot
silently succeed. Per-point scales reach the same counterterm scalar program.

Request-scoped lowering can omit a basis only when exact declared coupling
bounds prove it irrelevant. The full source and species-correction eligibility
remain retained; pruning does not certify a model or its counterterm completion.
The shared source compiler now prepares bounded complete QCD and neutral-current
Gmu controls through retained raw models, exact restrictions and model-derived
states, without named-process dispatch or rounded defaults. Source gluon controls
include external fields and owned scale snapshots in all three carriers.

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
insertion signs and propagators. Ordinary Bose slot classes are identified only
after exact native tests of the complete vertex under generating transpositions.
This repairs 39 missed insertions in the five-leg $u overline(u) -> g g g$
control. Complete Born, bare, UV and $R_2$ components now agree with MadLoop
at the reference accuracy in double, DoubleFloat and AP80; exact parameter-update
controls also pass.

External-field factors multiply the applicable Born currents with each physical
leg retained. Local and field UV remain separately inspectable, then join the
same ordered interference. Model-rule $R_2$ currents already contain their loop
normalization; the assembly does not multiply them by a second loop measure.

The bounded Gmu continuation offers an explicit `ufo-standard` logarithm
convention. The default preserves the source helper; either choice retains
the original model and does not certify complete CMS physics.

#note[
  *Evidence boundary.* Bounded QCD and real-mass neutral-current EW controls
  do not certify arbitrary UFO rules, restrictions, gauges or BSM renormalization.
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
plan. The bounded full-colour direct-$R_2$ gluon plan also rebinds its retained
dimensional DAG and physical/evanescent sectors, including UV and field completion.
Source-owned complete QCD views also retain their exact scalar definitions and
parameter snapshots across carrier rebinding. Formal-colour and correlated plan
reuse remain outside this checkpoint; reducer Laurent preparation remains a cold binding cost.

#small[
  *Separate sharing experiment.* On distinct exact energy rescalings of gluon
  controls, five alternating calls at $B=32,128$ gave complete medians
  #sharing-ms(32, "complete", "baseline") → #sharing-ms(32, "complete", "joined") /
  #sharing-ms(128, "complete", "baseline") → #sharing-ms(128, "complete", "joined") ms per point.
  Exact interning reduced 1,963 nodes to 1,358 with bit-identical outputs, but native
  execution slowed. A cache-locality explanation remains an inference; global
  interning was not adopted. CPU 379/shared host; separate from headline data.
]

#small[
  *Graph-local arena experiment.* Existing lifetime allocation reduced retained
  arena capacity by 48.4% without changing instructions or 16-row tiles. Complete
  $B=32,128$ medians were
  #arena-ms(32, "complete", "baseline") → #arena-ms(32, "complete", "compact") /
  #arena-ms(128, "complete", "baseline") → #arena-ms(128, "complete", "compact") ms per point.
  Coefficients and complete components were bit-identical; DD/AP80 layout checks
  passed. No speed benefit was established; the production layout is unchanged.
  Both plans coexisted, capacity excludes dependency buffers, and raw DAG clocks
  remain available. Same distinct-point protocol and CPU.
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
calls are covered. Headline timings use Python to coordinate native batch plans.
The shared Rust coordinator now executes complete validated QCD plans in one call,
including source-model gluon controls checked in all three carriers.

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

The staged generic-any-$n$ consumer (`e4c16a7`) removes the old six-propagator
cap. A seven-propagator rank-eight numerator cancelling to a triangle master
passes generic double/DD/AP80 and binary64 fast-tensor evaluation; broader
physical multiplicity remains a separate gate. Rank above $n+1$ still rejects.

`Runtime.load` uses checked schema-v3/PACBIN artifacts and the Rust coordinator,
without producer imports. Source gluon controls pass double/DD/AP70, independent
Born/double-pole checks, exact updates and native lifecycle tests. Load-time
arithmetic/precision/$R_2$ defaults precede parameter binding: AP70 accepts exact
`aS="1e400"`; empty batches retain AP.

The public slice requires full-colour inclusive model-rule $R_2$ plus UV and
explicit positive scalar or per-point $mu_R^2$. Generation must retain exact
source, completion and scheme metadata; model names confer no certification.
Commands, resolved/correlated output, LC/FFT, rescue and SDK/UMAMI remain open.
NinjaRS packaging remains an owner follow-up.

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
prove that numerator-origin $R_2$ is complete. In the target HV scheme, effective
rules already include the missing spin-dimension terms. They must not also be
added to the four-dimensional numerator. FDH has a different prescription.

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
  *Current priority.* Complete effective-rule $R_2$ plus UV, feature coverage and
  higher multiplicities. Further generic direct development and strategy timing
  are deferred; existing bounded controls and interfaces are retained. Headline
  timings use model rules. The historical paired gluon LC/full cells use direct
  completion. Scheme distinction: #link("https://arxiv.org/html/0903.0356v2#S2")[QCD rational rules, §2].
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
  [Complete QCD], [Internal two-to-two DY, four-quark, top-pair, quark/gluon and gluon controls; all three carriers. The complete five-leg quark-to-three-gluon control passes after the counterterm witness fix and now has a separate measured row.],
  [Real-mass EW], [Source-owned neutral-current charged-lepton controls, including bounded massive muons; complete components and scale/parameter changes.],
  [CMS], [Explicit Gmu log choice matches MadLoop components: double/DD across widths, AP80 at finite/small widths. The AP80 zero-width master gate and Recola finite-UV convention remain separate.],
  [Correlations / mapping], [Bounded directed/spin controls and exact species symmetry; general composition and mapping transport remain open.],
  [Public delivery], [Saved source artifacts execute through Runtime.load and the shared Rust coordinator in double/DD/AP70. Typed orders/poles, exact updates and explicit per-point scales pass; generation commands and SDK/UMAMI remain open.],
  [Performance], [Current development timings only; distinct-point matched provider gates and required high multiplicity remain open.],
)

== Required multiplicity and acceptance
The target includes selected $2 -> 5$ processes, with $2 -> 6$ as a stretch
goal. The common-provider set includes gluon jets, heavy-quark plus jets,
lepton-pair plus jets, and heavy-quark/lepton-pair production with a jet.
Five-final-parton gluon channels also require MadLoop/Recola controls; an
unavailable public OpenLoops channel is not invented for comparison.

The generic-any-$n$ consumer is adopted after a seven-propagator anchor in all
three carriers; high-multiplicity physical validation is still a separate gate.
For $u overline(u) -> e^- e^+ g g$, MadLoop/Recola reference points and the
additional local counterterm tensor checks pass; complete pyAmpliCol validation
is pending, so this process has no timing row yet.
Rank above the supported $n+1$ domain must reject. Required progress also includes broader cold-plan and portable-plan coverage, optional FFT,
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
  *Living document.* Update source, data and PDF after each milestone. Current
  priority is requested feature coverage and validated two-to-four/two-to-five
  processes; further two-to-two optimization is deferred. Add timing rows only
  after physical validation. No arbitrary caps on process size or current count;
  report actual dependency limits explicitly.
]
