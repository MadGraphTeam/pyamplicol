// pyAmpliCol one-loop report. Every number is read from data/*.json, except
// the cited architecture evidence in sections 6-14. Build from this directory:
//   typst compile benchmarks.typ benchmarks.pdf
#let m = json("data/measurements.json")
#let cold = json("data/provider-cold.json")
#let colours = json("data/colour-measurements.json")
#let audit = json("data/provider-audit.json")
#let procs = json("data/processes.json")
#let gen = json("data/generation.json")
#let report-date = procs.date

// ------------------------------------------------------------------ style --
#let navy = rgb("#1f3b63")
#let pale = rgb("#eef3f9")
#let ink2 = luma(90)
#let hair = 0.4pt + luma(222)
#let sans = "DejaVu Sans"

#set document(title: "pyAmpliCol at one loop — status, benchmarks and architecture", author: "pyAmpliCol developers", date: none)
#set page(paper: "a4", margin: (x: 1.6cm, top: 1.7cm, bottom: 1.6cm), numbering: "1 / 1",
  header: context if counter(page).get().first() > 1 {
    set text(8pt, fill: luma(110))
    [pyAmpliCol at one loop #h(1fr) report #report-date · timings #m.date]
  })
#set text(font: "Libertinus Serif", size: 10.5pt, lang: "en")
#set par(justify: true, leading: 0.62em)
#set heading(numbering: "1.1")
#show heading.where(level: 1): it => { v(0.5em); block(text(14pt, fill: navy, it)); v(0.15em) }
#show heading.where(level: 2): it => block(above: 1em, text(11pt, fill: navy, it))
#show raw: set text(font: "DejaVu Sans Mono", size: 8pt)
#show link: set text(fill: rgb("#1f5fa8"))
#show figure.where(kind: table): set figure.caption(position: top)
#show figure.caption: set text(9pt)
#show figure.caption: set par(justify: true)
#set figure(gap: 0.6em)

// ---------------------------------------------------------------- numbers --
#let is-num(x) = type(x) == int or type(x) == float
#let fixed(x, d) = {
  let s = str(calc.round(x, digits: d))
  if d == 0 { return s.split(".").first() }
  let parts = s.split(".")
  let frac = if parts.len() > 1 { parts.at(1) } else { "" }
  parts.at(0) + "." + frac + "0" * (d - frac.len())
}
#let group(n) = {
  let rest = str(n)
  let out = ()
  while rest.len() > 3 { out.insert(0, rest.slice(rest.len() - 3)); rest = rest.slice(0, rest.len() - 3) }
  out.insert(0, rest)
  out.join(sym.space.thin)
}
// Three significant figures, thin-space thousands.
#let sig(x) = {
  if not is-num(x) { return [—] }
  let a = calc.abs(x)
  if a == 0 { return "0" }
  if a >= 1000 {
    let e = calc.floor(calc.log(a, base: 10)) - 2
    return group(int(calc.round(x / calc.pow(10.0, e)) * calc.pow(10, e)))
  }
  let d = if a >= 100 { 0 } else if a >= 10 { 1 } else if a >= 1 { 2 } else if a >= 0.1 { 3 } else { 4 }
  fixed(x, d)
}
#let times(r) = [×#fixed(r, 1)]
#let gib(kib) = kib / 1048576
#let mem(mib) = if mib >= 1024 [#sig(mib / 1024) GiB] else [#sig(mib) MiB]

// --------------------------------------------------------- colour scales --
// Diverging ColorBrewer RdBu (colour-blind safe): blue faster, red slower.
#let palette = gradient.linear(rgb("#4393c3"), rgb("#d1e5f0"), white, rgb("#fddbc7"), rgb("#d6604d"))
#let ratio-fill(r) = if r == none { none } else { palette.sample(calc.clamp(0.5 + calc.log(r, base: 2) / 8, 0, 1) * 100%) }
#let legend() = align(center, {
  set text(7.2pt, font: sans)
  box(width: 10cm, {
    box(width: 10cm, height: 0.28cm, fill: palette, radius: 2pt)
    v(-0.45em)
    [×1/16 #h(1fr) ×1/4 #h(1fr) ×1 #h(1fr) ×4 #h(1fr) ×16]
    v(-0.55em)
    text(fill: ink2)[faster #h(1fr) time ÷ fastest reference, log scale, clamped #h(1fr) slower]
  })
})
// Okabe–Ito categorical colours for stage figures.
#let c-num = rgb("#0072b2")
#let c-born = rgb("#e69f00")
#let c-ct = rgb("#009e73")
#let c-red = rgb("#cc79a7")
#let c-mast = rgb("#d55e00")
#let c-other = rgb("#56b4e9")
#let c-rest = luma(200)

// ----------------------------------------------------------------- tables --
#let tstyle(body) = {
  set text(7.6pt, font: sans)
  set par(justify: false, leading: 0.4em)
  show table.cell.where(y: 0): set text(fill: white, weight: "bold")
  body
}
#let tstroke(x, y) = (top: if y <= 1 { none } else { hair })
#let thead-fill(x, y) = if y == 0 { navy } else { none }
#let dim(body) = text(fill: ink2, body)
#let tiny(body) = text(6.6pt, fill: ink2, body)
#let math-label(s) = eval(s, mode: "math")
// Standard process notation from processes.json; an unlisted case prints its key.
#let plabel(key) = {
  let label = procs.at("case_labels", default: (:)).at(key, default: none)
  if label == none { raw(key) } else { math-label(label) }
}
#let case-note(key) = (dy: "photon only", "ee-mumu-ew": [full EW, $G_mu$]).at(key, default: "QCD")
#let box-note(fill: pale, stroke: none, body) = block(width: 100%, fill: fill, stroke: stroke, inset: 9pt, radius: 3pt, text(9.2pt, body))

// ------------------------------------------------------- measured access --
#let providers = ("madloop", "recola", "openloops")
#let pname(p) = (pyamplicol: "pyAmpliCol", madloop: "MadLoop", recola: "Recola", openloops: "OpenLoops").at(p)
#let pshort(p) = (madloop: "ML", recola: "Recola", openloops: "OL").at(p)
#let record(c, b, p) = if p == "pyamplicol" {
  c.timings.at(str(b), default: none)
} else {
  m.references.at(c.case, default: (:)).at("timings", default: (:)).at(str(b), default: (:)).at(p, default: none)
}
#let median(c, b, p) = { let r = record(c, b, p); if r == none { none } else { r.median_us_per_point } }
#let spread(r) = {
  if r == none { return none }
  let lo = r.at("min_us_per_point", default: none)
  let hi = r.at("max_us_per_point", default: none)
  if lo == none { let s = r.samples_us_per_point; lo = calc.min(..s); hi = calc.max(..s) }
  (lo, hi)
}
#let fastest(c, b) = {
  let found = providers.map(p => (p: p, v: median(c, b, p))).filter(r => r.v != none)
  if found.len() == 0 { none } else { found.sorted(key: r => r.v).first() }
}
// Explicit markers for absent provider observations, from processes.json.
#let missing-markers = procs.at("missing_markers", default: (:))
#let missing(c, p) = missing-markers.at(c.case + "/" + p, default: missing-markers.at("default", default: "not timed"))
#let ratios(p, ref) = {
  let out = ()
  for c in m.cases { for b in (1, 128) {
    let a = median(c, b, p)
    let r = median(c, b, ref)
    if a != none and r != none { out.push(a / r) }
  } }
  out
}
#let range-text(v) = if v.len() == 0 [—] else [#times(calc.min(..v))–#times(calc.max(..v))]

// ================================================================ PAGE 1 ==
#align(center)[
  #v(0.2em)
  #text(24pt, weight: "bold", fill: navy)[pyAmpliCol at one loop]
  #v(-0.5em)
  #text(12pt, fill: luma(80))[Born–virtual interference: status, benchmarks and architecture]
  #v(-0.3em)
  #text(9pt, fill: luma(110))[Report #report-date · timings #m.date · AMD EPYC 9754, one pinned thread]
]

pyAmpliCol computes the interference $2 op("Re")(B^dagger G L)$ of one-loop and Born
amplitudes with the UV and $R_2$ counterterms supplied by the UFO loop model,
returning all three Laurent coefficients for every squared coupling order in
binary64, double-double (DD) and arbitrary precision (AP). This report tracks
the required $2 -> 5$ processes, the measured cost of the processes completed
so far, and the architecture that produced them. It marks what is not
measured, not validated or not working as such.

#grid(columns: (1fr, 1fr), gutter: 8pt,
  box-note[
    #set par(justify: false)
    *Status of the timing data.* All runtimes were measured on #m.date, at
    revisions #m.revision, #m.additional_revisions.qqggg.slice(0, 8) ($u overline(u) -> g g g$)
    and #m.additional_revisions.at("ee-mumu-ew").slice(0, 8) (EW). They time the
    _pre-shared-weight_ engine through its Python coordinator with
    #m.cases.map(c => upper(c.coefficient_engine)).dedup().join("/") coefficient evaluators,
    including exact decimal input, on repeated three-point streams. The delivered
    runtime (artifacts, CLI, SDKs) instead runs the interpreted evaluator in the
    Rust executor, which is not timed here. These are development observations,
    not the frozen acceptance campaign; later features have not been retimed
    (protocol box in @runtime).
  ],
  {
    let gate(name, value) = (text(weight: "semibold", name), align(right, text(weight: "bold", value)))
    let ml = ratios("pyamplicol", "madloop")
    let rc = ratios("pyamplicol", "recola")
    let ol = ratios("pyamplicol", "openloops")
    let n-req = procs.required.len()
    block(width: 100%, stroke: 0.6pt + luma(195), inset: 9pt, radius: 3pt, {
      set text(9.2pt)
      set par(justify: false)
      [*Acceptance gates* (on the required $2 -> 5$ set; development rows for orientation)]
      v(-0.3em)
      table(columns: (1fr, auto), stroke: none, inset: (x: 2pt, y: 2.6pt),
        ..gate([Required processes validated], [#procs.required.filter(r => r.validated).len() / #n-req]),
        ..gate([Required processes timed], [#procs.required.filter(r => r.timed).len() / #n-req]),
        ..gate([$t < t_"MadLoop"$, development rows], [#ml.filter(r => r < 1).len() / #ml.len() · #range-text(ml)]),
        ..gate([$t <= 1.3 t_"Recola"$, development rows], [#rc.filter(r => r <= 1.3).len() / #rc.len() · #range-text(rc)]),
        ..gate([$t <= 1.3 t_"OpenLoops"$, development rows], [#ol.filter(r => r <= 1.3).len() / #ol.len() · #range-text(ol)]),
      )
      v(-0.4em)
      text(7.8pt, fill: ink2)[Counts are process × batch cells at $B = 1$ and $B = 128$ (@runtime).]
    })
  },
)

= Required processes and feasibility <required>

The development plan requires the eight $2 -> 5$ processes of
@tab:required, to be compared with MadLoop and Recola, and with OpenLoops where
a public library exists. None has a result yet. The seven-leg control
$u overline(u) -> d overline(d) s overline(s) g$ measures where generation
spends its time (@sec:scaling).

#let yesno(v) = if v { text(fill: rgb("#1b6e3a"), weight: "bold")[yes] } else { dim[no] }
#let n-or-dash(x) = if x == none { dim[—] } else { group(x) }
#let tracker-row(r) = (
  {
    text(8.4pt, font: "Libertinus Serif", math-label(r.label))
    linebreak()
    tiny[#if r.openloops != none [OL #r.openloops] else [no public OL library]]
  },
  r.correction,
  n-or-dash(r.born_graphs),
  { n-or-dash(r.loop_graphs); if r.loop_count != "" { linebreak(); tiny(r.loop_count) } },
  {
    text(weight: "bold", r.generation)
    let note = if r.id == procs.control.id {
      let s = gen.seven_leg
      [after #sig(s.last_observed_s / 3600) h, inside the UV/$R_2$ projector; peak RSS #sig(gib(s.peak_rss_kib)) GiB]
    } else if r.generation_note != "" { eval(r.generation_note, mode: "markup") } else { none }
    if note != none { linebreak(); tiny(note) }
  },
  yesno(r.validated),
  yesno(r.timed),
  text(7pt, r.references),
  text(7pt, eval(r.blocker, mode: "markup")),
)
#figure(kind: table,
  caption: [*Required $2 -> 5$ processes* (plan §5.7) and the seven-leg control.
    Graph counts from MadLoop or pyAmpliCol generation as marked; — means not
    counted. _No result_: no complete generation exists. _Blocked_: a known
    model-admission gap stops generation. Sources in @sources.],
  tstyle(table(
    columns: (3.0cm, 0.75cm, 1.05cm, 1.35cm, 3.25cm, 0.95cm, 0.95cm, 1.6cm, 1fr),
    align: (x, y) => if x in (1, 5, 6) { center + horizon } else if x in (2, 3) { right + horizon } else { left + horizon },
    inset: (x: 4pt, y: 3.4pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][Corr.][Born][Loops][Generation][Valid.][Timed][References][Main blocker],
    ..procs.required.map(tracker-row).flatten(),
    table.cell(colspan: 9, fill: pale, inset: (x: 4pt, y: 2.5pt), text(7pt, weight: "semibold")[Control at seven legs]),
    ..tracker-row(procs.control),
  )),
) <tab:required>

#pagebreak(weak: true)
// ================================================================ RUNTIME ==
= Runtime of completed processes <runtime>

@tab:runtime compares the complete binary64 evaluation (Born, all helicities,
full colour, UV, model $R_2$, all three Laurent coefficients) of the seven timed
processes with MadLoop, Recola and OpenLoops at $B = 1$ and $B = 128$ points
per call.

#let rt-cell(c, b, p) = {
  let r = record(c, b, p)
  let best = fastest(c, b)
  if r == none {
    return table.cell(text(7pt, fill: ink2, style: "italic", missing(c, p)))
  }
  let v = r.median_us_per_point
  let ml-timed = median(c, b, "madloop") != none
  let ratio = if best == none { none } else { v / best.v }
  let (lo, hi) = spread(r)
  table.cell(fill: if ml-timed { ratio-fill(ratio) } else { none }, {
    text(8.2pt, weight: "bold", sig(v))
    h(1fr)
    if p != "pyamplicol" and best != none and best.p == p {
      text(6.8pt, fill: ink2)[fastest]
    } else if ratio != none {
      text(7.4pt, weight: "semibold", times(ratio))
    }
    linebreak()
    text(6.4pt, fill: luma(70))[#sig(lo)–#sig(hi)]
    if p == "pyamplicol" and not ml-timed and ratio != none { h(1fr); text(6.4pt, fill: luma(70))[vs #pshort(best.p) only] }
  })
}
#let gen-cell(c, p) = {
  let s = if p == "pyamplicol" { c.generation_s } else { cold.cases.at(c.case, default: (:)).at(p, default: (:)).at("seconds", default: none) }
  table.cell(text(6.8pt, fill: ink2, {
    if s == none { [—] } else { [#if p == "openloops" [setup ]#sig(s) s] }
    if p == "pyamplicol" [ · #mem(c.peak_rss_mib)]
  }))
}
#figure(kind: table,
  caption: [*Runtime per phase-space point*, µs, binary64, full colour.
    Bold: median of five warm calls; below: min–max of the five. Multiplier:
    time ÷ the fastest timed reference for that process and batch (marked
    _fastest_), shown and coloured only when MadLoop is timed for that row; the
    EW row gives its ratio to Recola uncoloured. Grey lines: generation
    (pyAmpliCol: fresh process to complete plan, with peak RSS; MadLoop: export
    and static compilation; Recola: parameters, process definition and
    generation) or OpenLoops setup of a prebuilt library (source generation not
    timed). Recola Drell–Yan is matched photon-only. $B$: points per call.],
  tstyle(table(
    columns: (2.9cm, 0.75cm, 1fr, 1fr, 1fr, 1fr),
    align: left + horizon,
    inset: (x: 4.5pt, y: 3.2pt),
    stroke: (x, y) => (top: if y <= 1 { none } else if calc.rem(y - 1, 3) == 0 { 0.6pt + luma(190) } else { hair }, left: if x >= 2 and y > 0 { hair } else { none }),
    fill: thead-fill,
    table.header[Process][$B$][pyAmpliCol][MadLoop][Recola][OpenLoops],
    ..m.cases.map(c => (
      table.cell(rowspan: 3, align: left + horizon, {
        text(9pt, font: "Libertinus Serif", plabel(c.case))
        linebreak()
        let pl(n, w) = [#n #w#if n != 1 [s]]
        tiny[#case-note(c.case) · #pl(c.counts.loop_graphs, "loop") · #pl(c.counts.families, "famil" + if c.counts.families == 1 { "y" } else { "ie" })]
      }),
      [1], rt-cell(c, 1, "pyamplicol"), ..providers.map(p => rt-cell(c, 1, p)),
      [128], rt-cell(c, 128, "pyamplicol"), ..providers.map(p => rt-cell(c, 128, p)),
      tiny[gen.], gen-cell(c, "pyamplicol"), ..providers.map(p => gen-cell(c, p)),
    )).flatten(),
  )),
) <tab:runtime>
#legend()

#v(0.3em)
Six further processes pass their complete physics checks but have not been
timed (@tab:untimed); validation durations are not used as runtimes.

#figure(kind: table,
  caption: [*Validated, not yet timed.* Complete components agree with the
    listed references in every listed arithmetic.],
  tstyle(table(
    columns: (3.0cm, 1fr, 2.1cm, 3.05cm, 2.3cm, 1.65cm),
    align: left + horizon, inset: (x: 4.5pt, y: 3.2pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][Scope][Born / loops / fam.][Arithmetic][References][Runtime],
    ..procs.validated_untimed.map(r => (
      text(8.4pt, font: "Libertinus Serif", math-label(r.label)),
      text(7pt, eval(r.scope, mode: "markup")),
      if r.loop_graphs == none { dim[—] } else [#r.born_graphs / #r.loop_graphs / #r.families],
      r.carriers, r.references,
      text(7pt, fill: ink2, style: "italic")[not timed],
    )).flatten(),
  )),
) <tab:untimed>

#box-note(fill: white, stroke: 0.6pt + luma(195))[
  #set par(justify: false)
  *Measurement protocol and deviations from the plan's timing protocol*
  #set text(8.6pt)
  #grid(columns: (1fr, 1fr), gutter: 10pt,
  [
    - CPU #m.reference_protocol.cpu (#m.host); one thread per process.
    - Five warm calls per batch after warm-up; medians with min–max. No paired
      blocks or uncertainty estimate (protocol item 9).
    - _Repeated_ three-point streams, not distinct frozen points (item 1).
    - pyAmpliCol includes Python batch scheduling and exact decimal ingress
      (item 3); providers start from binary64 arrays. The delivered runtime
      and SDKs use the interpreted evaluator instead.
  ],
  [
    - pyAmpliCol rescue off; providers keep their stability checks, rescue and
      caches (item 6). OpenLoops actual-pole mode reruns the amplitude three times.
    - Development-profile native builds, not release builds. DD/AP not timed.
      #let rb = procs.at("development_facts", default: (:)).at("release_builds", default: none)
      #if rb != none [
        A release A/B (#rb.date, not retimed here) was faster by
        #times(rb.native_eval_speedup) for native #math-label(rb.native_eval_process)
        at $B = #rb.native_eval_batch$, by
        #times(rb.colour_overlap_speedup.first())–#times(rb.colour_overlap_speedup.last())
        for colour overlaps and by
        #times(rb.generation_speedup.first())–#times(rb.generation_speedup.last()) for generation.
      ]
    - Repeat runs drift: an audit at $B = 128$ gave OpenLoops $g g -> g g$
      #sig(audit.openloops_gg_o3.median_us_per_point.ol0) µs and MadLoop
      #sig(audit.openloops_gg_o3.median_us_per_point.madloop) µs, against
      #let gg = m.cases.find(c => c.case == "gg")
      #sig(median(gg, 128, "openloops")) and #sig(median(gg, 128, "madloop")) µs in @tab:runtime.
      Ratios are therefore given to one decimal.
  ])
]

// ================================================================= STAGES ==
= Where the time goes <stages>

The instrumented runs split each evaluation into exclusive clocks
(@tab:stages, @fig:stages). Reduction and scalar masters are a few per cent of
the total; the per-graph numerators, the Born weighting and the counterterm
currents dominate, followed by work no clock attributes.

#let ct-keys = ("counterterm_scalars", "counterterm_coefficients", "field_scalars", "ct_projection")
#let other-keys = ("parameters", "born_coefficients", "born_projection", "family_masses", "bare_assembly", "complete_assembly")
#let sum-keys(x, keys) = keys.map(k => x.at(k, default: 0)).sum()
#let med(v) = { let s = v.sorted(); let n = s.len(); if calc.odd(n) { s.at(int(n / 2)) } else { (s.at(n / 2 - 1) + s.at(n / 2)) / 2 } }
// Per-sample categories, then medians; "unattributed" closes each sample.
#let py-split(st) = {
  let rows = st.samples.map(x => {
    let parts = (x.numerator_us, x.born_weighting, sum-keys(x, ct-keys), x.reduction_us, x.masters_us, sum-keys(x, other-keys))
    (..parts, x.instrumented_total_us - parts.sum(), x.instrumented_total_us)
  })
  range(8).map(i => med(rows.map(r => r.at(i))))
}
#let ml-split(c, b) = {
  let r = record(c, b, "madloop-instrumented")
  if r == none { return none }
  let s = r.stages
  (s.loop_coefficients.median_us_per_point, s.born_counterterm_helas.median_us_per_point,
   s.reduction_masters.median_us_per_point, s.residual.median_us_per_point, r.median_us_per_point)
}
#let num(x) = sig(x)
// Cases with an instrumented stage run; a timed case without one is omitted.
#let staged = m.cases.filter(c => c.case in m.stages)
#figure(kind: table,
  caption: [*Stage decomposition*, µs per point at the batch $B$ of the
    instrumented run, which is separate from the warm runs of @tab:runtime.
    pyAmpliCol: numerator = loop-coefficient DAGs, reducer callbacks and
    coefficient-head preparation; Born weighting = dual Born weights;
    counterterms = UV/$R_2$ and external-field scalars, coefficients and
    projection; NinjaRS = exclusive reduction; masters = oneloopmaster
    adapter; other clocked = parameters, Born coefficients and projection,
    family masses and assembly; unattributed = clocked total minus all stages
    (external states, kinematics, coordinator and timer overhead). Medians of
    per-sample values. MadLoop (grey rows): loop coefficients, shared HELAS
    (Born, local UV/$R_2$, external fields, wavefunctions), reduction plus
    masters, and residual; its stage clocks exclude the shared HELAS work from
    the numerator.],
  tstyle(table(
    columns: (2.5cm, 0.75cm, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr, 1.05cm),
    align: (x, y) => if x < 2 { left + horizon } else { right + horizon },
    inset: (x: 3.5pt, y: 3pt),
    stroke: (x, y) => (top: if y <= 1 { none } else if calc.odd(y) { 0.6pt + luma(190) } else { none }),
    fill: (x, y) => if y == 0 { navy } else if calc.even(y) and y > 0 { rgb("#f3f4f6") } else { none },
    table.header[Process][$B$][Numerator][Born weighting][Counter-terms][NinjaRS][Masters][Other clocked][Unattrib.][Total][Red.+mast.],
    ..staged.map(c => {
      let st = m.stages.at(c.case)
      let b = st.batch_size
      let p = py-split(st)
      let q = ml-split(c, b)
      (
        table.cell(rowspan: 2, text(8.6pt, font: "Libertinus Serif", plabel(c.case))),
        table.cell(rowspan: 2)[#b],
        ..p.slice(0, 7).map(num), text(weight: "bold", num(p.at(7))),
        [#fixed(100 * (p.at(3) + p.at(4)) / p.at(7), 1) %],
        ..if q == none {
          (table.cell(colspan: 9, text(7pt, fill: ink2, style: "italic")[MadLoop: #missing(c, "madloop")]),)
        } else {
          (dim(num(q.at(0))), dim[—], dim(num(q.at(1))), table.cell(colspan: 2, align: center, dim(num(q.at(2)))),
           dim[—], dim(num(q.at(3))), dim(text(weight: "bold", num(q.at(4)))),
           dim[#fixed(100 * q.at(2) / q.at(4), 0) %])
        },
      )
    }).flatten(),
  )),
) <tab:stages>

// One bar of length total/scale: the stage medians, then the explicit residual
// total - sum(stages). Medians need not add up; stages exceeding the total are
// scaled down to it, so every bar ends exactly at its total.
#let stack(parts, colours, total, scale, width) = box(width: width, height: 7pt, {
  let s = parts.sum()
  let (drawn, rest) = if s <= total { (parts, total - s) } else { (parts.map(v => v * total / s), 0) }
  let x = 0pt
  for (v, col) in (..drawn, rest).zip((..colours, c-rest)) {
    let w = width * v / scale
    if w > 0pt { place(dx: x, rect(width: calc.max(w - 0.6pt, 0.4pt), height: 7pt, fill: col)) }
    x += w
  }
})
#figure(
  caption: [*Composition of one evaluation*, pyAmpliCol (upper bar) and
    MadLoop (lower bar) at the batch of @tab:stages, to the scale of the larger
    clocked total. Each bar ends at its median total; the grey end is the total
    minus the drawn stage medians. The label is the ratio of the totals. The
    thin purple and vermilion slivers are all of reduction and masters.],
  {
    set text(7.4pt, font: sans)
    let width = 10.6cm
    let py-col = (c-num, c-born, c-ct, c-red, c-mast, c-other)
    let ml-col = (c-num, c-ct, c-red)
    grid(columns: (2.6cm, auto, 2.3cm), column-gutter: 6pt,
      row-gutter: range(2 * staged.len()).map(i => if calc.even(i) { 2pt } else { 7pt }),
      align: (right + horizon, left + horizon, left + horizon),
      ..staged.map(c => {
        let st = m.stages.at(c.case)
        let p = py-split(st)
        let q = ml-split(c, st.batch_size)
        let scale = if q == none { p.at(7) } else { calc.max(p.at(7), q.at(4)) }
        (
          grid.cell(rowspan: 2, [#text(8.4pt, font: "Libertinus Serif", plabel(c.case)) \ #text(6.6pt, fill: ink2)[$B = #st.batch_size$]]),
          stack(p.slice(0, 6), py-col, p.at(7), scale, width),
          [pyAmpliCol #if q != none { text(weight: "bold", times(p.at(7) / q.at(4))) }],
          if q == none { text(6.8pt, fill: ink2, style: "italic")[MadLoop not timed] } else { stack(q.slice(0, 3), ml-col, q.at(4), scale, width) },
          text(fill: ink2)[MadLoop],
        )
      }).flatten(),
    )
    v(4pt)
    for (col, name) in ((c-num, [Numerator]), (c-born, [Born weighting]), (c-ct, [Counterterms / ML HELAS]),
                        (c-red, [Reduction (ML: + masters)]), (c-mast, [Masters]), (c-other, [Other clocked]), (c-rest, [Unattributed / ML residual])) {
      box[#box(rect(width: 7pt, height: 7pt, fill: col, radius: 1pt)) #name]
      h(9pt)
    }
  },
) <fig:stages>

// ============================================================ GENERATION ==
= Generation cost and scaling <sec:scaling>

Generation is the present blocker for the required processes. Its time and
memory grow faster than linearly with the number of loop graphs
(@fig:scaling), and the seven-leg control shows which stages dominate
(@fig:sevenleg).

// --------------------------------------------------- generation scaling --
// Log-log scatter. Both axes span whole decades around the data and the
// reference lines, with headroom above the highest value, so a new case cannot
// leave the frame. Labels are clamped inside the frame; a lower bound
// (kind "open") carries an upward tick that also stays inside.
#let loglog(w, h, xlabel, ylabel, points, hlines: (), ytick: e => [$10^#e$]) = context {
  let lg(v) = calc.log(v, base: 10)
  let xs = points.map(p => lg(p.x))
  let ys = points.map(p => lg(p.y)) + hlines.map(l => lg(l.at(0)))
  let xr = (calc.floor(calc.min(..xs)), calc.ceil(calc.max(..xs) + 0.25))
  let yr = (calc.floor(calc.min(..ys)), calc.ceil(calc.max(..ys) + 0.5))
  let px(x) = w * (lg(x) - xr.at(0)) / (xr.at(1) - xr.at(0))
  let py(y) = h - h * (lg(y) - yr.at(0)) / (yr.at(1) - yr.at(0))
  set text(7pt, font: sans)
  let top = 0.45cm
  box(width: w + 1.25cm, height: h + 0.95cm + top, {
    place(dx: 1.1cm, dy: top, box(width: w, height: h, {
      for (y, t) in hlines {
        place(dy: py(y), line(length: w, stroke: (paint: luma(200), thickness: 0.4pt, dash: "dashed")))
        place(dx: w - 1.2cm, dy: py(y) - 8pt, box(width: 1.15cm, align(right, text(6.3pt, fill: luma(120), t))))
      }
      place(rect(width: w, height: h, stroke: 0.5pt + luma(150)))
      for e in range(xr.at(0), xr.at(1) + 1) {
        let x = w * (e - xr.at(0)) / (xr.at(1) - xr.at(0))
        place(dx: x, dy: h, line(angle: 90deg, length: 3pt, stroke: 0.5pt + luma(150)))
        place(dx: x - 0.5cm, dy: h + 4pt, box(width: 1cm, align(center, [$10^#e$])))
      }
      for e in range(yr.at(0), yr.at(1) + 1) {
        let y = h - h * (e - yr.at(0)) / (yr.at(1) - yr.at(0))
        place(dx: -3pt, dy: y, line(length: 3pt, stroke: 0.5pt + luma(150)))
        place(dx: -1.05cm, dy: y - 4pt, box(width: 0.95cm, align(right, ytick(e))))
      }
      for p in points {
        let (x, y) = (px(p.x), py(p.y))
        let s = 2.6pt
        if p.kind == "filled" {
          place(dx: x - s, dy: y - s, circle(radius: s, fill: navy, stroke: none))
        } else if p.kind == "hollow" {
          place(dx: x - s, dy: y - s, circle(radius: s, fill: white, stroke: 1pt + navy))
        } else {
          place(dx: x - s, dy: y - s, polygon(fill: rgb("#d6604d"), stroke: none, (0pt, 2 * s), (2 * s, 2 * s), (s, 0pt)))
          let tick = calc.min(9pt, y - s - 1pt)
          if tick > 0pt {
            place(dx: x - 0.25pt, dy: y - s - tick, line(angle: 90deg, length: tick, stroke: 0.8pt + rgb("#d6604d")))
          }
        }
        let label = text(6.5pt, p.label)
        let size = measure(label)
        let (dx, dy) = p.at("off", default: (4pt, -4pt))
        let lx = if p.at("anchor", default: left) == left { x + dx } else { x + dx - size.width }
        let ly = y + dy - 3pt
        let inside(v, hi) = calc.max(1pt, calc.min(v, hi - 1pt))
        place(dx: inside(lx, w - size.width), dy: inside(ly, h - size.height), label)
      }
    }))
    place(dx: 1.1cm, dy: top + h + 0.55cm, box(width: w, align(center, xlabel)))
    place(dx: 0.35cm, dy: 0pt, text(fill: ink2, ylabel))
  })
}
// Label placement per case and panel; unlisted cases use the default offset.
#let label-place(panel, key) = (
  time: (
    uudd: (off: (4pt, 4pt)), tt: (off: (4pt, -6pt)), gg: (off: (4pt, -7pt)),
    "ee-mumu-ew": (off: (-4pt, -5pt), anchor: right),
  ),
  rss: (
    uudd: (off: (4pt, 4pt)), tt: (off: (-1pt, -7pt), anchor: right),
    gg: (off: (4pt, 5pt)), "ee-mumu-ew": (off: (-4pt, -5pt), anchor: right),
  ),
).at(panel).at(key, default: (:))
#let sev = gen.seven_leg
#let case-point(c, panel, y) = (x: c.counts.loop_graphs, y: y, kind: "filled", label: plabel(c.case)) + label-place(panel, c.case)
#let time-points = (
  ..m.cases.map(c => case-point(c, "time", c.generation_s)),
  ..gen.correctness_runs.map(r => (x: r.loop_graphs, y: r.generation_s, kind: "hollow", label: math-label(r.label), off: (-4pt, -2pt), anchor: right)),
  (x: sev.loop_graphs, y: sev.last_observed_s, kind: "open", label: [#math-label(sev.label): stopped], off: (-6pt, 6pt), anchor: right),
)
#let rss-points = (
  ..m.cases.map(c => case-point(c, "rss", c.peak_rss_mib / 1024)),
  (x: sev.loop_graphs, y: gib(sev.peak_rss_kib), kind: "open", label: [#math-label(sev.label): #sig(gib(sev.peak_rss_kib)) GiB], off: (-6pt, 6pt), anchor: right),
)
#figure(
  caption: [*Generation time and peak memory against loop-graph count.*
    Filled: the timed processes of @tab:runtime (fresh process, source capture
    to complete plan). Open circles: cold generation observed during the
    complete correctness runs of #gen.correctness_runs.map(r => math-label(r.label)).join([ and ])
    (no memory record). Triangle with tick: the seven-leg control, which ended
    without a result; its time and memory are lower bounds. Generation grows
    faster than linearly in the graph count.],
  grid(columns: 2, gutter: 0.4cm,
    loglog(7.0cm, 5.0cm, [loop graphs], [seconds], time-points,
      hlines: ((60, [1 min]), (3600, [1 h]), (86400, [1 day]))),
    loglog(7.0cm, 5.0cm, [loop graphs], [peak RSS, GiB], rss-points,
      ytick: e => if e >= 0 [#calc.pow(10, e)] else [0.#("0" * (-e - 1))1]),
  ),
) <fig:scaling>

#let stage-colours = (luma(150), rgb("#56b4e9"), rgb("#0072b2"), rgb("#e69f00"), rgb("#009e73"), rgb("#d6604d"))
#figure(kind: image,
  caption: [*Where the seven-leg generation spent its time.* Stage lines of the
    #sev.source_revision correctness run of $u overline(u) -> d overline(d) s overline(s) g$
    (#sev.born_graphs Born, #group(sev.loop_graphs) loop graphs, #sev.families families,
    CPU #sev.cpu). The UV/$R_2$ projector had run for
    #sig((sev.last_observed_s - sev.stages.last().begin_s) / 3600) h when the process
    was last seen at #sig(sev.last_observed_s / 3600) h; it ended without a result.
    Memory is the maximum resident set recorded at the end of each stage.],
  {
    set text(7.4pt, font: sans)
    let total = sev.last_observed_s
    let w = 16.6cm
    box(width: w, height: 0.55cm, {
      let x = 0pt
      for (i, s) in sev.stages.enumerate() {
        let sw = w * (s.end_s - s.begin_s) / total
        place(dx: x, rect(width: calc.max(sw - 0.8pt, 0.6pt), height: 0.55cm,
          fill: if s.at("unfinished", default: false) { stage-colours.at(i).lighten(55%) } else { stage-colours.at(i) },
          stroke: if s.at("unfinished", default: false) { (paint: stage-colours.at(i), dash: "dashed", thickness: 0.8pt) } else { none }))
        if sw > 1.2cm { place(dx: x + 3pt, dy: 0.16cm, text(fill: if i == 5 { black } else { white }, weight: "bold")[#(i + 1)]) }
        x += sw
      }
    })
    v(-0.2em)
    box(width: w)[0 h #h(1fr) #sig(total / 3600 / 2) h #h(1fr) #sig(total / 3600) h]
    v(0.1em)
    table(columns: (auto, 1fr, auto, auto, auto), inset: (x: 5pt, y: 2.6pt), stroke: tstroke,
      align: (x, y) => if x < 2 { left + horizon } else { right + horizon },
      table.header(text(weight: "bold")[], text(weight: "bold")[Stage], text(weight: "bold")[Interval, h], text(weight: "bold")[Duration, s], text(weight: "bold")[Max. RSS at end]),
      ..sev.stages.enumerate().map(((i, s)) => (
        box(rect(width: 7pt, height: 7pt, fill: stage-colours.at(i), radius: 1pt)) + [ #(i + 1)],
        s.label,
        [#fixed(s.begin_s / 3600, 2)–#fixed(s.end_s / 3600, 2)],
        if s.at("unfinished", default: false) [≥ #group(int(calc.round(s.end_s - s.begin_s)))] else { group(int(calc.round(s.end_s - s.begin_s))) },
        if s.rss_kib_at_end == none [not recorded] else [#sig(gib(s.rss_kib_at_end)) GiB],
      )).flatten(),
    )
  },
) <fig:sevenleg>

// ============================================================ LEADING COL ==
= Leading colour <lc>

Leading-colour (LC) evaluation keeps the highest common power of $N_c$ at
fixed $N_f$ (@colour). @tab:lc pairs each LC run with a full-colour run of
the same process and $R_2$ strategy in one separate campaign (revision
#colours.revision, CPU #colours.cpu); its full-colour times therefore differ from
@tab:runtime. Both paths still evaluate every graph, so LC is not yet faster.
Next-to-leading colour is validated but not timed.

#let lc-cell(c, b) = {
  let lc = c.lc.timings.at(str(b))
  let full = c.full.timings.at(str(b))
  let r = lc.median_us_per_point / full.median_us_per_point
  (
    table.cell({ text(8pt, weight: "bold", sig(lc.median_us_per_point)); linebreak(); tiny[#sig(lc.min_us_per_point)–#sig(lc.max_us_per_point)] }),
    table.cell({ text(8pt, sig(full.median_us_per_point)); linebreak(); tiny[#sig(full.min_us_per_point)–#sig(full.max_us_per_point)] }),
    table.cell(fill: ratio-fill(r), align: center + horizon, text(weight: "semibold", times(r))),
  )
}
#figure(kind: table,
  caption: [*Leading colour against full colour*, µs per point, binary64,
    median and min–max of five warm calls. The LC/full cell is coloured with
    the palette of @tab:runtime; no external provider enters this table.
    Generation: fresh process to complete plan, LC / full.],
  tstyle(table(
    columns: (2.6cm, 1.25cm, 1fr, 1fr, 0.9cm, 1fr, 1fr, 0.9cm, 1.9cm),
    align: (x, y) => if x < 2 { left + horizon } else { left + horizon },
    inset: (x: 4pt, y: 3.2pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][$R_2$][LC, $B = 1$][Full, $B = 1$][LC/full][LC, $B = 128$][Full, $B = 128$][LC/full][Generation, s],
    ..colours.cases.map(c => (
      text(8.6pt, font: "Libertinus Serif", plabel(c.case)),
      if c.full.r2_strategy == "direct" [direct] else [model],
      ..lc-cell(c, 1), ..lc-cell(c, 128),
      [#sig(c.lc.generation_s) / #sig(c.full.generation_s)],
    )).flatten(),
  )),
) <tab:lc>

The $g g -> g g$ row uses the bounded direct-$R_2$ control for both colour
modes; its full-colour time is the only direct-$R_2$ observation. No
direct-versus-model cost comparison is made, because the model-$R_2$ row of
@tab:runtime belongs to a different campaign and CPU.

// ============================================================ CAPABILITY ==
= Capabilities and open gates <capabilities>

#let st-style = (
  supported: (rgb("#2166ac"), white, [supported]),
  partial: (rgb("#d1e5f0"), black, [partial]),
  open: (rgb("#fddbc7"), black, [open]),
  deferred: (luma(225), black, [deferred]),
)
#let badge(s) = { let (f, t, name) = st-style.at(s); box(fill: f, inset: (x: 4pt, y: 2pt), radius: 2pt, text(6.8pt, fill: t, weight: "bold", name)) }
#let caps = (
  ([Model import], "supported", [Lossless UFO loop models (Laurent parameters, UV/$R_2$ categories, loop groups) via the published loader 1.0.1; Goldstone-alias loader PR 3 and a coherent Community package are pending.]),
  ([QCD interference, massless and external tops], "supported", [Validated to $2 -> 4$ against MadLoop/Recola in binary64, DD and AP (@tab:runtime, @tab:untimed).]),
  ([Internal massive quarks], "supported", [Complete $g g -> t overline(t)$ (internal top loops, top-mass UV and $R_2$ two-points), $u overline(u) -> t overline(t)$ (top-loop gluon self-energy) and $e^- e^+ -> t overline(t) h$ (top Yukawa and Goldstone counterterms) match MadLoop in binary64, DD and AP. Not timed.]),
  ([Model UV and $R_2$], "supported", [Consumed from the UFO model for QCD; no completeness check of counterterm matching; tadpoles, one-point counterterms and bivalent mixing unsupported.]),
  ([Direct $R_2$], "deferred", [Deferred by the user; certified bounded controls only (full-colour $g g -> g g$); public dispatch gated.]),
  ([Coupling orders], "supported", [Joint QCD/QED eligibility as in MadLoop; every squared order and all three Laurent coefficients returned.]),
  ([Electroweak], "partial", [Real-mass $e^- e^+ -> mu^- mu^+$ and $e^- e^+ -> u overline(u)$ ($G_mu$); 1351 of 1918 $G_mu$ counterterm bases uncertified; no joint QCD+EW.]),
  ([Restriction cards], "supported", [Every shipped card of `loop_sm` (incl. `-ckm`), `loop_qcd_qed_sm` and `loop_qcd_qed_sm_Gmu` loads through the production simplification with MadGraph semantics; entries without a model parameter are ignored and recorded, cards MadGraph rejects are rejected.]),
  ([Complex-mass scheme], "open", [Matched component controls only; not wired into generation.]),
  ([General models], "partial", [Scalar QCD $u overline(u) -> sigma_8 sigma_8 g$ with isolated dependency candidates.]),
  ([Full colour], "partial", [To six legs; pairwise exact overlaps make seven gluons infeasible.]),
  ([LC / NLC], "partial", [Fixed-$N_f$ LC/NLC validated to six legs; formal $"SU"(N_c)$ fails on generic seven-leg networks.]),
  ([Colour FFT], "partial", [Certified rectangular binary64 full/NLC with exact DD/AP fallback; forced-LC and correlated FFT missing.]),
  ([Correlations and spin sources], "partial", [Directed complex colour histories, photon/gluon and $W$ sources; EW/CMS sources and resolved correlated output open.]),
  ([Flavour mappings], "partial", [Identity-port species reuse; Bose permutations partial; charge conjugation missing.]),
  ([Arithmetic], "supported", [Genuine binary64, DD and AP end to end from exact inputs.]),
  ([Batching and rescue], "partial", [Native Rust executor; timings use the Python coordinator; rescue on hard failure only, with no accuracy trigger and two implementations.]),
  ([Helicity selection], "open", [All $2^n$ helicities are evaluated, including structurally zero ones.]),
  ([Interfaces], "partial", [Python, TOML/CLI, artifacts, Rust/C/C++/Fortran/UMAMI SDKs; delivered runtime uses the interpreted evaluator; benchmark/profile commands broken; no wheel of the current source.]),
  ([Required $2 -> 5$ set], "open", [0 of 8 validated or timed; provider references exist for #procs.required.filter(r => r.references != "none generated").len() of #procs.required.len() (@tab:required).]),
  ([Performance gates], "open", [No timed process is faster than MadLoop (front page).]),
  ([NinjaRS and oneloopmaster], "partial", [Generic reduction up to seven propagators; scalar-master fixes (PR 9, PR 10) not yet adopted.]),
)
#figure(kind: table,
  caption: [*Capability matrix* of the current engine. Sources: @sources.],
  tstyle(table(
    columns: (3.6cm, 1.55cm, 1fr), align: (x, y) => if x == 1 { center + horizon } else { left + horizon },
    inset: (x: 4.5pt, y: 3.1pt), stroke: tstroke, fill: thead-fill,
    table.header[Feature][Status][Boundary],
    ..caps.map(((f, s, b)) => (text(weight: "semibold", f), badge(s), b)).flatten(),
  )),
) <tab:caps>

// ========================================================= ARCHITECTURE ==
= The computed quantity <observable>

For Born order $a$, loop order $b$ and squared coupling order $s = a + b$, the
ordinary observable is
$
  V_(s,k) = cal(N) sum_(a+b=s) 2 op("Re")[B_a^dagger G_(B L) L_(b,k)], quad k in {0, -1, -2},
$
where $G_(B L)$ is the rectangular colour matrix between the Born and loop
colour bases and $cal(N)$ holds initial-state averages and identical-particle
factors. Couplings are included; nothing is divided by the Born. The
coefficients follow the MadLoop convention
$
  V = C_epsilon (V_0 + V_(-1) / epsilon + V_(-2) / epsilon^2), quad
  C_epsilon = (4 pi)^epsilon / Gamma(1 - epsilon),
$
and the Recola controls convert with $V_0^"ML" = V_0^"Recola" + (pi^2 / 6) V_(-2)$.
Correction eligibility is a property of each graph: a mixed four-quark process
with $B = B_(20) + B_(02)$ and $L = L_(40) + L_(22) + L_(04)$ receives both
$B_(20)^* L_(22)$ and $B_(02)^* L_(40)$ at squared order $(4, 2)$, and joint
QCD+QED selection admits mixed loops that neither single correction contains.
Directed colour and spin correlations replace $2 op("Re")(dots)$ by the two cross
terms $B_A^dagger G L_B + L_A^dagger G B_B$, which can be complex.

= Generation and evaluation pipeline <pipeline>

@fig:pipeline shows the current dataflow. Generation runs once per process
in Python on top of Symbolica and its Community packages; the per-event path
runs in a Rust executor. The engine works _per Feynman diagram_: every loop and
Born graph owns a coefficient program, colour enters through exact
diagram-by-diagram overlaps, and the projections that combine graphs,
helicities and colour terms are built as whole-process symbolic expressions.

#let stage-box(title, owner, kind) = {
  let (f, s) = if kind == "sym" { (rgb("#fdf0e6"), 0.7pt + rgb("#d6604d")) } else if kind == "nat" { (rgb("#e8f1f8"), 0.7pt + rgb("#2166ac")) } else { (white, 0.7pt + luma(150)) }
  block(width: 100%, height: 1.25cm, fill: f, stroke: s, inset: (x: 3pt, y: 3pt), radius: 2pt, align(center + horizon, {
    set par(justify: false, leading: 0.32em)
    set text(6.9pt, font: sans)
    text(weight: "bold", title)
    linebreak()
    text(6.2pt, fill: ink2, owner)
  }))
}
#let arr = align(center + horizon, text(8pt, fill: luma(120), sym.arrow.r))
#let lane(body) = align(center + horizon, rotate(-90deg, reflow: true, text(6.6pt, font: sans, fill: ink2, weight: "bold", body)))
#figure(
  caption: [*Current pipeline.* Upper lane: generation, once per process, in
    Python on Symbolica and its Community packages. Lower lane: evaluation per
    batch in the Rust executor. Orange: whole-process symbolic constructions
    that dominate generation (@walls); blue: native batched numerics. The
    owning dependency is named under each step.],
  grid(columns: (0.45cm, 1fr, 8pt, 1fr, 8pt, 1fr, 8pt, 1fr, 8pt, 1fr, 8pt, 1fr), row-gutter: 6pt, column-gutter: 1pt,
    lane[generation],
    stage-box([UFO loop model], [ufo_model_loader, HepKit], "plain"), arr,
    stage-box([Graphs and families], [FeynKit, HepKit], "plain"), arr,
    stage-box([Per-graph numerator DAGs], [pyAmpliCol, Symbolica], "plain"), arr,
    stage-box([Colour overlaps per term pair], [Spenso, Idenso], "sym"), arr,
    stage-box([Born and family projectors], [Symbolica expressions], "sym"), arr,
    stage-box([All one-counterterm trees; UV/$R_2$ projector], [FeynKit, Symbolica], "sym"),
    lane[evaluation],
    stage-box([States, all $2^n$ helicities], [Rust executor], "nat"), arr,
    stage-box([Graph coefficient plans], [Symbolica evaluators], "nat"), arr,
    stage-box([Born weights, family projection], [Symbolica evaluators], "nat"), arr,
    stage-box([Reduction and masters], [NinjaRS, oneloopmaster], "nat"), arr,
    stage-box([Counterterm currents and projection], [Symbolica evaluators], "nat"), arr,
    stage-box([Assembly and output], [Rust executor], "nat"),
  ),
) <fig:pipeline>

#figure(
  caption: [Three graphs of $u overline(u) -> g g g$, drawn by FeynKit's
    renderer from its own graph generation: a Born graph, a pentagon, and a
    box with a tree attachment. The present engine evaluates the attached
    tree current again inside the program of every loop graph that contains it.],
  grid(columns: 3, gutter: 10pt,
    ..("born", "pentagon", "box").map(n => box(height: 3.7cm, image("figures/" + n + ".svg", height: 100%, fit: "contain")))),
) <fig:graphs>

*Model.* The upstream loader keeps Laurent-valued parameters and couplings,
UV and $R_2$ categories, loop-particle groups and external-field factors.
pyAmpliCol prepares one scalar program per coupling, a structural HepKit model
and one counterterm rule per vertex, loop group and coupling order. Lorentz and
colour tensors remain native Idenso/Spenso objects throughout; admission of a
vertex frame is currently by an explicit list of certified structures.

*Graphs.* FeynKit generates Born and one-loop graphs with its own filters
disabled; pyAmpliCol applies MadLoop-equivalent physical rejection and assigns
each graph to an integral family through HepKit's family mappings, keeping
routed propagators, bridges and the exact routing transformation.

#figure(kind: table,
  caption: [*Ownership of the mathematics.* pyAmpliCol reuses its
    dependencies for algebra, tensors, graphs and integrals, and owns the
    process-level assembly.],
  tstyle(table(
    columns: (3.4cm, 1fr), align: left + horizon,
    inset: (x: 4.5pt, y: 3.1pt), stroke: tstroke, fill: thead-fill,
    table.header[Component][Responsibility],
    [ufo_model_loader], [Lossless UFO loop-model import: Laurent-valued parameters and couplings, UV/$R_2$ categories, loop groups],
    [Symbolica], [Expressions, series and coefficient extraction; compiled evaluators (interpreted, SymJIT in binary64); exact rationals and arbitrary precision],
    [HepKit (Community)], [Structural model; integral families and family mappings],
    [FeynKit (Community)], [Born and loop graph generation, momentum routing, symmetry factors, counterterm trees, graph drawing (@fig:graphs)],
    [Spenso, Idenso (Community)], [Lorentz and colour tensors, gamma and colour algebra, exact colour overlaps],
    [NinjaRS], [Integrand reduction with Laurent expansion and rank admission],
    [oneloopmaster], [Scalar master integrals in binary64, DD and AP],
    [pyAmpliCol], [Order selection and physical rejection, coefficient programs, Born weighting, counterterm matching, projections, assembly, Rust executor, artifacts and interfaces],
  )),
) <tab:deps>

= Numerators, families and Born weighting <numerators>

Each graph's loop numerator is a polynomial in the loop momentum $q$. A current
holds the coefficients of that polynomial; a local vertex tensor $T$ acting on
the previous current $J$ gives the next one, $J' = T dot J$, with coefficient
extraction prepared once symbolically and evaluated natively in 16-row tiles.
Every graph owns its own coefficient program, so tree attachments and open-loop
segments shared by many graphs are recomputed in each (@fig:graphs).

The one decision that already scales well is to weight by the Born _before_
reduction. For each point and helicity $h$, the complex weight $omega_(g h)$
of graph $g$ is the component of the Born row $B_h^dagger G$ that belongs to
the colour structure of $g$, and each family $F$ is reduced once:
$
  B^dagger G L = sum_F integral d^d q space
  (sum_(g in F) sum_h omega_(g h) N_(g h)(q)) / (product_(i in F) D_i (q)).
$
One reduction per point, coupling sector and family replaces one per graph,
helicity and colour term; @tab:stages shows reduction plus masters at
#fixed(calc.min(..staged.map(c => { let p = py-split(m.stages.at(c.case)); 100 * (p.at(3) + p.at(4)) / p.at(7) })), 1)–#fixed(calc.max(..staged.map(c => { let p = py-split(m.stages.at(c.case)); 100 * (p.at(3) + p.at(4)) / p.at(7) })), 1) %
of the clocked time. Weights stay complex until the directed bilinear is formed,
because colour histories and other off-diagonal observables need both cross terms.

= Reduction and scalar masters <reduction>

NinjaRS receives the routed denominators, the weighted polynomial coefficients
and exact invariants in the carrier's precision; weighted rank counts $mu^2$
twice and explicit $epsilon$ sectors combine by Laurent multiplication. The
reducer owns rank admission (up to rank $n + 2$) and reduces up to seven
propagators generically, including a rank-eight seven-propagator control that
cancels exactly to a triangle. oneloopmaster evaluates the scalar masters
natively in all three arithmetics; its complex-mass and high-precision branch
fixes (PR 9, PR 10) pass isolated controls but are not yet adopted.

= Counterterms and rational terms <counterterms>

The production strategy uses the UV and $R_2$ effective vertices of the UFO
model. Every tree with exactly one counterterm vertex is enumerated by FeynKit
and matched against the admitted loops, keeping attachment currents, ordered
legs, coupling orders and loop-species alternatives; exact vertex transposition
identifies Bose-equivalent slots. Local UV, external-field factors and $R_2$
remain separately inspectable before joining the same ordered interference.
Model $R_2$ currents already carry the loop normalisation. A symbolic projector
over helicities, currents and Born terms then contracts all insertions.

Direct $R_2$, an evanescent recurrence with numerator
$N_0 + epsilon N_1 + epsilon^2 N_2$ and reduced sectors $(F_j, S_j, D_j)$ giving
$V_0 = F_0 + S_1 + D_2$, $V_(-1) = S_0 + D_1$, $V_(-2) = D_0$, is certified on
bounded vectorlike and Yang–Mills controls only and is deferred.

= Colour, correlations and mappings <colour>

Full colour contracts exact Born and loop colour tensors through Spenso/Idenso
into the rectangular $G_(B L)$, one overlap per pair of diagram colour terms,
with no numerical colour fits. For a certified formal-$N_c$ model, LC and NLC
keep the common highest power $P$ across all contributions of a squared order:
$
  "LC": N_c^P, quad "NLC": N_c^P, N_c^(P-1), N_c^(P-2), quad N_f "fixed".
$
Directed correlations act with native charge tensors on batched shared
currents. Identity-port flavour members reuse an exact plan; certified
rectangular FFT contraction covers binary64 full and NLC colour.

= Precision, batching and rescue <precision>

Binary64, DoubleFloat and arbitrary precision run through coefficients,
kinematics, reduction, masters and counterterms without promotion through
binary64; decimal inputs and rational model coefficients are exact until the
carrier is chosen. Ordered layouts preserve point, helicity and event
identities through tails and compaction. Rescue reevaluates a failed point in
higher precision and accepts it when two higher results agree on every
component; there is no accuracy-based trigger yet, and the Python and Rust
coordinators implement rescue separately.

= Measured scaling walls <walls>

The per-diagram design meets the walls of @tab:walls, which together put the
required $2 -> 5$ processes out of reach. Values are from the seven-leg stage
log (@fig:sevenleg) and from stack samples and probes of the 2026-10-20
assessment (@sources).

#figure(kind: table,
  caption: [*Scaling walls of the current engine.*],
  tstyle(table(
    columns: (3.9cm, 1fr, 4.1cm), align: left + horizon,
    inset: (x: 4.5pt, y: 3.2pt), stroke: tstroke, fill: thead-fill,
    table.header[Wall][Measured][Consequence],
    [Symbolic whole-process projectors (Born, families, UV/$R_2$), unrolled over helicities],
    [Seven legs: Born projector #group(int(calc.round(sev.stages.at(2).end_s - sev.stages.at(2).begin_s))) s; family projectors #group(int(calc.round(sev.stages.at(3).end_s - sev.stages.at(3).begin_s))) s; UV/$R_2$ projector unfinished after #sig((sev.last_observed_s - sev.stages.last().begin_s) / 3600) h. Family and counterterm projectors take 90.5 % and 8.4 % of the 394 MB six-leg artifact. Measured with the former quadratic term accumulation; one-pass sums now build the six-leg $u overline(u) -> d overline(d) s overline(s)$ counterterm projector expression in 2.2 s instead of 85.6 s.],
    [Blocks every $2 -> 5$ process; recompiled per colour mode, spin class and correlation.],
    [Enumeration of all one-counterterm trees, then matching to loops],
    [$u overline(u) -> d overline(d) s overline(s)$: 50 s, 832 MB; $g g -> g g g$: 86 s, 1.28 GB; $g g -> g g g g$: over 8 GB within 165 s; seven legs: #group(int(calc.round(sev.stages.at(4).end_s - sev.stages.at(4).begin_s))) s up to #sig(gib(sev.peak_rss_kib)) GiB.],
    [Blocks $g g -> g g g g$ and above; dominates memory.],
    [Pairwise exact colour overlaps, no colour basis],
    [About 5,000 s of the seven-leg DAG stage; formal $"SU"(N_c)$ fails on 14 of 24 random seven-gluon pairs.],
    [Seven-gluon full colour infeasible; no LC/NLC at seven legs.],
    [Per-diagram numerators without sharing],
    [54 % of loop-node and 95 % of counterterm-node evaluations are duplicates; numerator plus Born weighting dominate @tab:stages.],
    [Runtime #range-text(ratios("pyamplicol", "madloop")) MadLoop (front page).],
    [No helicity selection],
    [Structurally zero helicity rows: Drell–Yan 12 of 16, $u overline(u) -> d overline(d) s overline(s)$ 56 of 64.],
    [Two- to eightfold waste in every stage, squared in the projector builders.],
  )),
) <tab:walls>

= Redesign in progress <redesign>

The per-diagram numerator core is being replaced. The replacement is at the
design stage and is not implemented; nothing in this report measures it. Its
centre is a shared open-loop recursion in the style of OpenLoops and Recola,
built on pyAmpliCol's tree engine and its colour-flow currents, so that tree
attachments and open-loop segments are computed once per process rather than
once per graph. @tab:plan lists the planned answer to each wall. Model import,
counterterm rules, FeynKit graphs and families, Born weighting before
reduction, the NinjaRS and oneloopmaster adapters, the exact carriers, the Rust
executor and the public interfaces are kept.

#figure(kind: table,
  caption: [*Planned replacements* (design status; resumption assessment §4).],
  tstyle(table(
    columns: (3.9cm, 1fr, 4.1cm), align: left + horizon,
    inset: (x: 4.5pt, y: 3.2pt), stroke: tstroke, fill: thead-fill,
    table.header[Current construction][Planned replacement][Needed for],
    [Symbolic whole-process projectors], [Native sparse contractions over a helicity row axis], [Every $2 -> 5$ generation; artifact size],
    [All one-counterterm trees], [Enumeration of counterterm sites, with a completeness check], [$g g -> g g g g$ and above; memory],
    [Pairwise colour overlaps], [Canonical overlap cache, then a fixed trace or colour-flow basis], [Seven-gluon full colour; LC/NLC at seven legs],
    [Per-diagram numerator programs], [Shared open-loop recursion on the tree engine], [Speed gates; $g g -> g g g g$, $g g -> g g g g g$, $u overline(u) -> g g g g g$],
    [All $2^n$ helicities], [Selection of non-vanishing helicities], [Two- to eightfold saving in every stage],
    [Listed counterterm structures], [Generic tensor lowering for admission; CMS as a model transformation], [The EW $g g -> t overline(t) e^- e^+ g$ target; other EW and CMS processes],
  )),
) <tab:plan>

= Sources and reproducibility <sources>

#set par(justify: false)
#text(9pt)[
  - *Build:* `typst compile benchmarks.typ benchmarks.pdf` in
    `docs/performance_reports/loop/` (Typst 0.15).
  - *Timings:* `data/measurements.json` (samples, stages, provider references),
    `data/provider-cold.json` (provider generation and setup),
    `data/colour-measurements.json` (LC/full) and `data/provider-audit.json`
    (Recola Drell–Yan and OpenLoops audit). Their drivers are not yet in the
    repository: `workspace/experiments/loop_live_*.py` and
    `workspace/reference/live_provider_benchmark.py`.
  - *Process status:* `data/processes.json`, from the plan's §5.7, the
    continuation handoff (§3, §6, §7) and the 2026-10-20 resumption assessment
    (§1, §2.3, §8), which is also the source of the probe and stack-sample
    values in @tab:walls.
    #let srcs = procs.at("sources", default: (:))
    #let req-src = srcs.at("required_references", default: none)
    #let rb-src = srcs.at("release_builds", default: none)
    #if req-src != none [Required-process provider references: #raw(req-src.split(" ").first()).]
    Case labels, missing-value markers and development facts such as the
    release-build A/B#if rb-src != none [ (#raw(rb-src))] are also recorded there.
  - *Generation:* `data/generation.json`, written by
    `scripts/collect_generation.py` from the retained correctness-run records
    and the seven-leg stage log. Graph drawings: `scripts/draw_graphs.py`.
  - *Conventions:*
    #link("https://cp3.irmp.ucl.ac.be/projects/madgraph/wiki/MadLoopStandaloneLibrary")[MadLoop standalone],
    #link("https://arxiv.org/abs/1605.01090")[Recola],
    #link("https://arxiv.org/abs/1710.11452")[OpenLoops on-the-fly reduction],
    #link("https://arxiv.org/abs/1404.4783")[four-dimensional formulation].
]
