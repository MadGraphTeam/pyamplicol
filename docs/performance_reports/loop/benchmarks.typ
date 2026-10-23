// pyAmpliCol one-loop report, milestone of 2026-10-23. Table values are read
// from data/*.json (milestone.json: registry with sources; measured.json:
// written by scripts/collect_milestone.py from the run records;
// measurements.json, provider-cold.json, legacy-labels.json: the legacy
// snapshot of 2026-10-18). Numbers quoted in prose name their source in the
// last section. Build from this directory:
//   typst compile benchmarks.typ benchmarks.pdf
#let ms = json("data/milestone.json")
#let meas = json("data/measured.json")
#let sg = meas.seven_gluon
#let hm = json("data/measurements.json")
#let hcold = json("data/provider-cold.json")
#let hlab = json("data/legacy-labels.json")

// ------------------------------------------------------------------ style --
#let navy = rgb("#1f3b63")
#let pale = rgb("#eef3f9")
#let warm = rgb("#fdf3e7")
#let ink2 = luma(90)
#let hair = 0.4pt + luma(222)
#let sans = "DejaVu Sans"

#set document(title: "pyAmpliCol at one loop — milestone status, benchmarks and architecture", author: "pyAmpliCol developers", date: none)
#set page(paper: "a4", margin: (x: 1.6cm, top: 1.7cm, bottom: 1.6cm), numbering: "1 / 1",
  header: context if counter(page).get().first() > 1 {
    set text(8pt, fill: luma(110))
    [pyAmpliCol at one loop #h(1fr) milestone #ms.date · engine #ms.engine_revision]
  })
#set text(font: "Libertinus Serif", size: 10.5pt, lang: "en")
#set par(justify: true, leading: 0.62em)
#set heading(numbering: "1.1")
#show heading.where(level: 1): it => { v(0.45em); block(text(14pt, fill: navy, it)); v(0.1em) }
#show heading.where(level: 2): it => block(above: 0.9em, below: 0.55em, text(11pt, fill: navy, it))
#show raw: set text(font: "DejaVu Sans Mono", size: 8pt)
#show link: set text(fill: rgb("#1f5fa8"))
#show figure.where(kind: table): set figure.caption(position: top)
#show figure.caption: set text(9pt)
#show figure.caption: set par(justify: true)
#show figure.caption: set align(left)
#set figure(gap: 0.55em)

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
  let d = if a >= 100 { 0 } else if a >= 10 { 1 } else if a >= 1 { 2 } else if a >= 0.1 { 3 } else if a >= 0.01 { 4 } else { 5 }
  fixed(x, d)
}
// Scientific notation, d decimals in the mantissa; Unicode superscripts, as in
// the registry's text values.
#let sup-digits = ("0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹", "-": "⁻", "−": "⁻")
#let sci(x, d: 1) = {
  if not is-num(x) { return [—] }
  if x == 0 { return [0] }
  let e = calc.floor(calc.log(calc.abs(x), base: 10))
  let mant = x / calc.pow(10.0, e)
  if calc.abs(calc.round(mant, digits: d)) >= 10 { mant = mant / 10; e += 1 }
  let m = fixed(mant, d)
  if m.starts-with("-") { m = "−" + m.slice(1) }
  [#m×10#str(e).clusters().map(c => sup-digits.at(c)).join()]
}
// A registry value exactly as recorded (its own precision).
#let num(x) = if x == none [—] else if type(x) == int and x >= 1000 { group(x) } else { str(x) }
// Milliseconds with the source table's precision (two decimals below 10).
#let ms2(x) = if x >= 1000 { group(int(calc.round(x))) } else if x >= 100 { fixed(x, 0) } else if x >= 10 { fixed(x, 1) } else { fixed(x, 2) }
#let mult(r) = [×#fixed(r, 1)]
#let kib-gib(k) = k / 1048576
#let minutes(s) = [#fixed(s / 60, 1) min]

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
#let plabel(r) = {
  text(8.4pt, font: "Libertinus Serif", math-label(r.label))
  let c = r.at("corr", default: none)
  let n = r.at("note", default: none)
  if c != none or n != none { h(3pt); tiny[#if c != none [#c]#if n != none [#n]] }
}
#let box-note(fill: pale, stroke: none, body) = block(width: 100%, fill: fill, stroke: stroke, inset: 9pt, radius: 3pt, text(9pt, body))
#let flag(body) = box(fill: warm, inset: (x: 3pt, y: 1.5pt), radius: 2pt, text(6.6pt, weight: "bold", fill: rgb("#8a4b08"), body))

// ================================================================ PAGE 1 ==
#align(center)[
  #v(0.1em)
  #text(24pt, weight: "bold", fill: navy)[pyAmpliCol at one loop]
  #v(-0.5em)
  #text(12pt, fill: luma(80))[Born–virtual interference: milestone status, benchmarks and architecture]
  #v(-0.3em)
  #text(9pt, fill: luma(110))[Milestone #ms.date · engine revision #ms.engine_revision · AMD EPYC 9754 (shared host)]
]

pyAmpliCol computes the interference $2 op("Re")(B^dagger G L)$ of one-loop and
Born amplitudes with the UV and $R_2$ counterterms of the UFO loop model, for
every squared coupling order and all three Laurent coefficients, in binary64,
double-double (DD) and arbitrary precision (AP). The engine is the recursive
_v2_ engine: tree currents, loop topologies and loop numerators come from
recursions, and no loop Feynman diagram is enumerated (@arch). The public
counterterm route at this push is still site closure, which the user reserves
for test oracles; counterterms inside the recursion (WP2.2) are in flight.
This report is the status of the intermediate push of
#ms.date to the `loop` branch. It separates development measurements from the
acceptance campaign, which has not run yet.

#grid(columns: (1.2fr, 1fr), gutter: 8pt,
  box-note[
    #set par(justify: false)
    *What `loop` contains at this push* (engine #ms.engine_revision\; merges since #ms.previous_loop)
    #v(-0.2em)
    #set text(8.2pt)
    #table(columns: (auto, auto, 1fr), stroke: none, inset: (x: 2pt, y: 2.4pt),
      ..ms.integrated.map(r => (raw(r.sha), text(weight: "semibold", r.wp), [*#r.title.* #text(fill: ink2, r.detail)])).flatten())
    #v(-0.3em)
    #text(8.2pt)[*Already on `loop`:* #ms.already_on_loop. *Requirements addendum* F, G, H
      (heavy processes and slow references, portable artifacts, high-multiplicity
      budget). *Native build* #raw(ms.native_build.name) (digest #raw(ms.native_build.digest)…).]
  ],
  block(width: 100%, stroke: 0.6pt + luma(195), inset: 9pt, radius: 3pt, {
    set text(9pt)
    set par(justify: false)
    [*Performance gates: policy and status*]
    v(-0.1em)
    set text(8.4pt)
    [
      - *Gate.* Faster than MadLoop and at most 1.30× each matched Recola and
        OpenLoops time, on the *finite part*, for processes from $2 -> 3$ upward.
        $2 -> 2$ is reported without a gate.
      - *Protocol.* Providers in production mode with poles off where they allow
        it (OpenLoops `truepoles 0`, Recola without IR poles, MadLoop production
        build); pyAmpliCol finite-only (`poles = "none"`) with stability checks off.
      - *Status.* The acceptance campaign (G1) has *not run*. No gate is claimed
        passed or failed. Provider references for the gate are in @tab:gateref.
      - *Seven gluons.* No matched provider timing exists for $g g -> g g g g g$
        (@tab:provgen): its speed is reported without a gate, with rotation
        checks; the Ward check that addendum H requires alongside is still
        pending (@tab:sevencheck).
      - *History.* The timings of 2026-10-18 measure the superseded per-diagram
        engine and appear only in @history.
    ]
    v(0.2em)
    align(center, box(fill: warm, inset: (x: 8pt, y: 4pt), radius: 3pt,
      text(9pt, weight: "bold", fill: rgb("#8a4b08"))[G1 pending: no gate result at this milestone]))
  }),
)

#grid(columns: (1fr, 1fr), gutter: 8pt,
  box-note(fill: white, stroke: 0.6pt + luma(205))[
    #set par(justify: false)
    *In flight* (branches, not on `loop`)
    #set text(8.4pt)
    - *Counterterms inside the recursion* (WP2.2, `work/v2-ct-recursion`): one
      $"CT"=1$ order in the tree recursion; the six-gluon recursion route is being
      profiled (a run was stopped as slower than the site-closure oracle).
    - *Generation at scale* (WP3.1, `work/v2-generation-scale`): native trees and
      Born per point, native counterterms, regeneration-free artifacts and SDK v4.
    - *UV/IR pole selection* (`poles = "uv" | "ir"`; NinjaRS 41a4c00,
      oneloopmaster 5b710437).
    - *G1* end-to-end measurement and live report (WP2.7), not started.
    - *Electroweak and complex-mass scheme* (WP3.2), pending.
    - *The $2 -> 5$ set* (WP3.3/3.4) on the WP3.1 branch (@required).
  ],
  box-note(fill: white, stroke: 0.6pt + luma(205))[
    #set par(justify: false)
    *User decisions of 23 October*
    #set text(8.4pt)
    - Generation at high multiplicity may take O(hours) below 150 GB (addendum H).
    - $g g -> g g g g g$: speed reported without a gate, with rotation and Ward checks.
    - No $2 -> 6$ work until the $2 -> 5$ plan is complete.
    - `poles = "uv"`: UV poles of the bare loop, with the counterterms' UV poles
      separately; `"ir"`: Catani poles of the renormalised virtual; the finite
      part is the same in all four modes.
    - Binary64 observables: $10^(-12)$ unless the own estimate $E > 10^(-12)$ (then
      $E$, capped at $10^(-9)$, plus DD within $10^(-24)$).
    - Stability-estimate tests may use a tenfold margin; development first,
      proportionate testing; push to `loop` at milestones with this report.
  ],
)

// ============================================================= REQUIRED ==
= Required processes: references and generation <required>

The plan requires the processes of @tab:provgen (plan §5.7), compared with
MadLoop and Recola, and with OpenLoops where a public library exists. A
reference provider is run only if its generation completes in about 45 minutes,
or in a time comparable to pyAmpliCol's own generation of the process (HANDOFF
§0.1, addendum F). Otherwise pyAmpliCol is validated by Ward and gauge
identities, Catani poles, LC/NLC/FC and DD/AP consistency, stability checks,
lower multiplicities and existing references.

#let gen-cell(r) = if r.gen_s == none { dim[not generated] } else {
  text(8.2pt, weight: "bold")[#num(r.gen_s) s]
  text(fill: ink2)[ #sym.plus #num(r.export_s) s]
  linebreak()
  tiny[#num(r.plan_mb) MB · #num(r.peak_gib) GiB]
}
#let req-of(label, corr) = ms.required.rows.find(r => r.label == label and r.at("corr", default: none) == corr)
#figure(kind: table,
  caption: [*Generation on this host.* Providers: MadLoop graph generation,
    export and compilation; Recola process generation; OpenLoops library
    availability (HANDOFF §0.1). pyAmpliCol: v2 generation + plan export
    (`LoopSlice.generate`, then plan v4 JSON), plan size and peak resident
    memory, one thread;
    a #flag[development] measurement on `work/v2-generation-scale`, not part of
    the acceptance campaign. Values stand side by side without a ratio.],
  tstyle(table(
    columns: (3.2cm, 2.65cm, 3.4cm, 1.9cm, 1.75cm, 1fr),
    align: left + horizon, inset: (x: 4pt, y: 3.1pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][pyAmpliCol v2, dev.][MadLoop][Recola][OpenLoops][45-minute rule],
    ..ms.provider_generation.rows.map(r => {
      let q = req-of(r.label, r.at("corr", default: none))
      (
        if r.label.contains("controls") { text(8pt)[$2 -> 2$, $2 -> 3$ controls] } else { plabel(r) },
        if q == none { dim[—] } else { gen-cell(q) },
        r.madloop, r.recola, r.openloops,
        if r.rule.starts-with("within") { r.rule } else { text(weight: "semibold", fill: rgb("#8a4b08"), r.rule) },
      )
    }).flatten(),
  )),
) <tab:provgen>

#figure(kind: table,
  caption: [*Validation of the required set* (#flag[development], `work/v2-generation-scale`;
    binary64, all three Laurent coefficients, three exact points per process,
    trees, Born and counterterms from the Python per-point inputs). Deviation
    metric $|a - b| slash max(|a|, |b|, |B| alpha_s slash 2 pi)$. Points that the
    stability estimate flags in binary64 are resolved in DoubleFloat. ML:
    MadLoop; OL: OpenLoops.],
  tstyle(table(
    columns: (3.2cm, 2.4cm, 1fr),
    align: left + horizon, inset: (x: 4pt, y: 3.1pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][References][Agreement],
    ..ms.required.rows.map(r => (plabel(r), r.refs, r.validation)).flatten(),
  )),
) <tab:validation>

#figure(kind: table,
  caption: [*Provider references for the speed gate*, s per point, one pinned
    core, production mode (finite part; OpenLoops `truepoles 0` with I-operator
    poles, Recola without IR poles, MadLoop production build). Measured on
    2026-10-20 for the design (DESIGN §1.3, Table 1b) and to be re-frozen by
    G1; inferred provider values of that table are omitted. Threshold: the
    largest pyAmpliCol finite-only time that would pass, 1.3× the
    fastest matched Recola/OpenLoops time where it is below MadLoop's.],
  tstyle(table(
    columns: (3.2cm, 1fr, 1fr, 1fr, 1.9cm),
    align: (x, y) => if x == 0 { left + horizon } else { right + horizon },
    inset: (x: 4pt, y: 3.1pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][OpenLoops][Recola][MadLoop][Threshold],
    ..ms.gate_references.rows.map(r => (plabel(r), r.openloops, r.recola, r.madloop, text(weight: "bold", r.threshold))).flatten(),
  )),
) <tab:gateref>

// ============================================================== RUNTIME ==
= Native runtime of the loop stage (development) <runtime>

No v2 process has an end-to-end timing yet. The native executor evaluates the
loop stage (seeds, dressing, NinjaRS reduction with cached oneloopmaster
masters, scatter), while trees, Born amplitudes and counterterm scalars are
still formed per point in Python and handed over (native lanes for them are
WP3.1 work). @tab:native therefore times the native loop stage alone: a
#flag[development] measurement of schedules B and M (WP2.8), not a gate row.
The cells stay neutral: they exclude work that a provider time includes.

#figure(kind: table,
  caption: [*Native loop stage*, ms per point, binary64, poles off, no
    stability check, 16 lanes, 16 points at $sqrt(s) = 1$ TeV, best of 3
    (DESIGN §5.6). Excludes trees, Born and counterterm scalars. B: per-family
    suffix tries (default); M: merged primitive-seeded entries, M/B as the
    source prints it (from unrounded times) in brackets. Reduction: share of the 8-thread time spent in the serial NinjaRS
    reduction with cached masters. $gamma^*$: photon exchange only.],
  tstyle(table(
    columns: (3.3cm, 0.8cm, 1.2cm, 1fr, 1fr, 1fr, 1fr, 1.5cm),
    align: (x, y) => if x < 2 { left + horizon } else { right + horizon },
    inset: (x: 4pt, y: 3.1pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][Col.][Families][B, 1 thread][M, 1 thread][B, 8 threads][M, 8 threads][Reduction],
    ..ms.native_stage.rows.map(r => (
      plabel(r), r.colour, num(r.families),
      text(weight: "bold", num(r.b1)), [#num(r.m1) #tiny[(#fixed(r.mb1, 2))]],
      num(r.b8), [#num(r.m8) #tiny[(#fixed(r.mb8, 2))]],
      [#fixed(100 * r.red8, 0) %],
    )).flatten(),
  )),
) <tab:native>

#let gs = ms.native_split.rows.find(r => r.label == "g g -> g g g")
#figure(kind: table,
  caption: [*Where the native time goes* (WP2.1 executor, 2026-10-22, release
    build without LTO; DESIGN §5.5), ms per point, binary64, one thread, 16
    lanes, schedule B. Dressing: open-loop segments; factors: per-point vertex
    tensors; reduction: NinjaRS with cached oneloopmaster masters (not clocked
    separately); finite only and with the reduction-direction re-test. Last
    column: the Python per-point inputs the native time excludes.],
  tstyle(table(
    columns: (3.3cm, 1.2cm, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr, 1.6cm),
    align: (x, y) => if x < 1 { left + horizon } else { right + horizon },
    inset: (x: 4pt, y: 3.1pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][Families][Dressing][Factors][Reduction][Seeds][Scatter][Finite only][With re-test][Python inputs],
    ..ms.native_split.rows.map(r => (
      plabel(r), num(r.families), ms2(r.dressing), ms2(r.factors), ms2(r.reduction), ms2(r.seeds), ms2(r.scatter),
      text(weight: "bold", ms2(r.finite)), ms2(r.retest), dim(ms2(r.python_inputs)),
    )).flatten(),
  )),
) <tab:split>

The dressing dominates the native loop stage and the reduction follows
($g g -> g g g$: #sig(gs.dressing) and #sig(gs.reduction) of #sig(gs.finite) ms).
Poles on or off cost the same there; the finite-only saving lies in the
counterterm and Catani work that is still in Python. Schedule M gains only on
pure-gluon classes, most at leading colour ($g g -> g g g g$ LC: 0.80 on one
thread); classes with a quark line stay at $1.00 plus.minus 0.02$ on one
thread (0.87–1.01 at 8 threads), so B stays the default for them. The Python inputs, two to three orders of magnitude above
the native loop stage, are the open item: G1 measures end to end once they run
natively.

// ========================================================== SEVEN GLUONS ==
= Seven gluons: NJet and pyAmpliCol <sevenglue>

== NJet: Table 5 of arXiv:1209.0100, re-measured on this host

NJet is the independent reference for $g g -> g g g g g$, where MadLoop and
Recola cannot generate under the 45-minute rule and OpenLoops has no library.
It is massless five-flavour QCD, and it is not one of the gate's matched
providers.

#let nj-cell(v, ref, note: none) = if v == none {
  table.cell(text(7pt, fill: ink2, style: "italic", if note == none [—] else { note }))
} else {
  table.cell({
    text(8.2pt, weight: "bold", num(v))
    h(1fr)
    text(7pt, fill: ink2)[#mult(v / ref)]
  })
}
#figure(kind: table,
  caption: [*NJet, s per point*, double precision, two evaluations each (NJet's
    scaling test). Paper: Xeon E3-1240 at 3.3 GHz, NJet 1.0. This host: one
    pinned idle core, 10 frozen points per channel, mean (spread ≤ 2 %); the
    multiplier is time ÷ the paper's. De-symmetrised sums equal the standard
    sums only after phase-space integration; they are timing figures, not
    point values.],
  tstyle(table(
    columns: (2.7cm, 1.3cm, 1fr, 1fr, 1.3cm, 1fr, 1fr),
    align: left + horizon, inset: (x: 4pt, y: 3.2pt),
    stroke: (x, y) => (top: if y <= 1 { none } else { hair }, left: if x in (1, 4) and y > 0 { 0.6pt + luma(190) } else { none }),
    fill: thead-fill,
    table.header[Channel][Table 5][NJet 3.1.2][NJet 2.1.1][Table 5][NJet 3.1.2][NJet 2.1.1],
    table.cell(fill: pale)[], table.cell(colspan: 3, fill: pale, align: center, text(7pt, weight: "semibold")[standard full-colour sum]),
    table.cell(colspan: 3, fill: pale, align: center, text(7pt, weight: "semibold")[de-symmetrised sum]),
    ..ms.njet.rows.map(r => (
      text(8.6pt, font: "Libertinus Serif", math-label(r.label)),
      num(r.t5_std),
      nj-cell(r.n312_std, r.t5_std, note: [defective channel]),
      nj-cell(r.n211_std, r.t5_std),
      num(r.t5_ds),
      nj-cell(r.n312_ds, r.t5_ds, note: if r.label == "g g -> g g" [no class] else [defective channel]),
      nj-cell(r.n211_ds, r.t5_ds, note: [no class]),
    )).flatten(),
  )),
) <tab:njet>

At seven gluons one NJet 3.1.2 evaluation without the scaling test takes
#ms.njet.single_evaluation.standard s (standard) and
#ms.njet.single_evaluation.desymmetrised s (de-symmetrised), at #ms.njet.rss_mb MB;
double-double costs #group(ms.njet.double_double_s) s per point. NJet 3.1.2's
numerical five-gluon channel is 9/2 too large (NJet 2.1.1 is used there), and at
the unrotated seven-gluon points NJet keeps only 4–6 digits in double precision
(NaN at 3 of 10), so the reference values are taken at exactly rotated points.

== pyAmpliCol development measurements

#let g1 = sg.generation_first
#let g2 = sg.generation_latest
#let ctp = sg.ct_program
#let nb = sg.native_bare
#box-note(fill: warm)[
  #set par(justify: false)
  These are #flag[development] measurements on the branches named, on the
  shared host. Generation and the counterterm program ran in one thread; the
  thread count of the native bare-loop timing was not recorded (@tab:sevendev).
  They are not part of the acceptance campaign and not a like-for-like speed
  comparison: the native path below does not yet include counterterms or
  $R_2$.
]

#figure(kind: table,
  caption: [*$g g -> g g g g g$ in full colour, development runs.* Wall
    times and peak resident memory from `/usr/bin/time` for the whole process,
    including model loading. Generation and the counterterm program are
    single-threaded (CPU share #g1.cpu_percent %, #g2.cpu_percent % and
    #ctp.cpu_percent %; `RAYON_NUM_THREADS=1` for the counterterm program). The
    bare-loop job did not record its thread count (the native executor's
    default is all cores); the whole job, generation and export included,
    averaged #nb.cpu_percent % CPU. Counts of the generated slice:
    #group(g1.counts.families) families, #group(g1.counts.skeletons) skeletons,
    #group(g1.counts.trie_nodes) trie nodes, #group(g1.counts.blocks) tree
    blocks, #group(g1.counts.seed_classes) colour-seed classes on a
    #g1.counts.born_basis\-element Born basis, #group(g1.counts.ct_sites)
    counterterm sites.],
  tstyle(table(
    columns: (4.4cm, 1fr, 2.5cm, 1.9cm),
    align: (x, y) => if x < 2 { left + horizon } else { right + horizon },
    inset: (x: 4pt, y: 3.2pt), stroke: tstroke, fill: thead-fill,
    table.header[Run (branch)][Stages][Wall][Peak memory],
    [Generation and plan, first run \ #tiny[`work/v2-generation-scale`, 03:55 UTC]],
    [`LoopSlice.generate` #minutes(g1.generate_s) (peak #fixed(g1.generate_peak_gib, 1) GiB), plan export #minutes(g1.export_s), JSON #sig(g1.plan_json_s) s; #sig(g1.plan_json_mb) MB plan],
    text(weight: "bold", minutes(g1.wall_s)), text(weight: "bold")[#fixed(kib-gib(g1.max_rss_kib), 1) GiB],
    [Generation and plan, latest run \ #tiny[same branch, 10:42 UTC]],
    [`LoopSlice.generate` #minutes(g2.generate_s) (peak #fixed(g2.generate_peak_gib, 1) GiB), plan export #minutes(g2.export_s), JSON #sig(g2.plan_json_s) s; #sig(g2.plan_json_mb) MB plan (derived row links)],
    text(weight: "bold", minutes(g2.wall_s)), text(weight: "bold")[#fixed(kib-gib(g2.max_rss_kib), 1) GiB],
    [Counterterms in the recursion \ #tiny[`work/v2-ct-recursion`]],
    [Plain blocks #minutes(ctp.plain_blocks_s), CT program #minutes(ctp.ct_program_s)\; #group(ctp.ct_currents) CT currents, #group(ctp.ct_interactions) interactions, #ctp.root_sites root sites, no rule left to site closure; script total #minutes(ctp.total_s). Root-closure (bind) terms not measured; run before the request-scoped lowering (ct-recursion DESIGN §6.1)],
    text(weight: "bold", minutes(ctp.wall_s)), text(weight: "bold")[#fixed(kib-gib(ctp.max_rss_kib), 1) GiB],
    [Bare loop + Born, native trees \ #tiny[`work/v2-generation-scale`, 5 points]],
    [Binary64; per point the point and one rotation (two evaluations); no counterterms, no $R_2$; thread count not recorded],
    text(weight: "bold")[#sig(calc.min(..nb.seconds))–#sig(calc.max(..nb.seconds)) s/pt], [#text(weight: "bold")[#fixed(kib-gib(nb.max_rss_kib), 1) GiB] #linebreak() #tiny[whole job]],
  )),
) <tab:sevendev>

Next to NJet on the same host (@tab:njet), the native path's
#sig(calc.min(..nb.seconds))–#sig(calc.max(..nb.seconds))~s per point for two
evaluations compares with #num(ms.njet.rows.last().n312_std)~s for NJet's
standard sum and #num(ms.njet.rows.last().n312_ds)~s for its de-symmetrised sum,
both also two evaluations. The comparison is not like-for-like: counterterms and
$R_2$ are missing on the pyAmpliCol side; NJet ran on one pinned core of the idle
host, while the pyAmpliCol job ran on the shared host with an unrecorded thread
count and load; and the de-symmetrised sum is not a point value. Generation fits
addendum H's budget (O(hours), below 150 GB). MASTER_PLAN quotes the same two
peaks as KiB/10⁶ ("#fixed(g1.max_rss_kib / 1e6, 1) GB",
"#fixed(ctp.max_rss_kib / 1e6, 1) GB"); of the run records, the counterterm
record prints KiB/10⁶ and the generation record GiB.

== Validation without a matched provider

#let fv = sg.first_virtual
#let nv = ms.njet_validation
#let ux = sg.uux_ggggg_vs_providers.max_relative_deviation
#figure(kind: table,
  caption: [*Checks of the seven-leg QCD results* (binary64; deviation metric of
    @tab:validation). NJet values: fixture `gg_ggggg_njet.json` (NJet 3.1.2
    double-double at exactly rotated points, scaling-test estimates
    ≤ #sci(1.3e-24)). The bare single pole is compared after subtracting the
    counterterm pole of its request, as marked in each row:
    $(alpha_s slash 4 pi) B \[(n - 2) beta_0^((5)) + 8 T_F slash 3\] = (alpha_s slash 4 pi) B dot 119 slash 3$
    for loop_sm (five-flavour coupling renormalisation and the top's
    decoupling term) and
    $(alpha_s slash 4 pi)(n - 2) beta_0^((5)) B = (alpha_s slash 4 pi) B dot 115 slash 3$
    for the top-free request.],
  tstyle(table(
    columns: (4.2cm, 1fr, 3.1cm),
    align: left + horizon, inset: (x: 4pt, y: 3.2pt), stroke: tstroke, fill: thead-fill,
    table.header[Check][Result][Status],
    [$g g -> g g g g g$, native bare loop, 5 points: double pole ÷ Born against $-(alpha_s slash 2 pi) dot 7 C_A$],
    [≤ #sci(calc.max(..nb.double_pole_deviation))\; rotation estimates #sci(calc.min(..nb.stability_estimate))–#sci(calc.max(..nb.stability_estimate))],
    [passed],
    [$g g -> g g g g g$ against NJet, native bare loop (loop_sm, 5 points; shift 119/3)],
    [Born ≤ #sci(nv.native_bare_vs_njet.born, d: 0), double pole ≤ #sci(nv.native_bare_vs_njet.double_pole), single pole #sci(nv.native_bare_vs_njet.single_pole_points_0_3.first())–#sci(nv.native_bare_vs_njet.single_pole_points_0_3.last()) at points 0–3; #sci(nv.native_bare_vs_njet.single_pole_point_4) at point 4, which pyAmpliCol's estimate (#sci(nv.native_bare_vs_njet.estimate_point_4)) flags],
    [no deviation beyond the estimates],
    [$g g -> g g g g g$ top-free (NJet's scheme) against NJet, native bare loop, 3 points; shift 115/3],
    [Born ≤ #sci(nv.topfree.born), double pole ≤ #sci(nv.topfree.double_pole), single pole #sci(nv.topfree.single_pole.at(0)) and #sci(nv.topfree.single_pole.at(1)) (estimates #sci(nv.topfree.estimates.at(0)), #sci(nv.topfree.estimates.at(1))), #sci(nv.topfree.single_pole.at(2))],
    [finite part needs the native counterterms],
    [Top-free full virtual against NJet at lower multiplicity (`test_loop_v2_topfree.py`)],
    [#nv.topfree.lower.map(l => [#math-label(l.label): #l.value]).join([; ])],
    [passed],
    [$u overline(u) -> g g g g g$ full virtual against MadLoop and Recola, 3 points],
    [MadLoop ≤ #sci(calc.max(..ux.madloop.values())), Recola ≤ #sci(calc.max(..ux.recola.values())) (finite ≤ #sci(ux.recola.finite)); the providers agree to 6.2×10⁻¹⁰],
    [passed],
    [Ward identity, one gluon's $epsilon -> p$, at seven gluons],
    [asymmetric Ward mode of WP2.5 (loop side only, bare + UV + $R_2$); passes on $g g -> g g$ and $u overline(u) -> g g g$ (`test_loop_v2_observables.py`)],
    text(fill: rgb("#8a4b08"), weight: "semibold")[not yet run at seven gluons (addendum H)],
  )),
) <tab:sevencheck>

#box-note[
  #set par(justify: false)
  *First $g g -> g g g g g$ virtual* (full colour, Born $alpha_s^5$, loop_sm with
  top loops, point #fv.point, $mu = 1$ TeV; Python per-point inputs with
  counterterms, about 3 h per evaluation on that development path):
  #v(-0.2em)
  #align(center, text(8.6pt, font: sans, table(columns: 5, stroke: none, inset: (x: 7pt, y: 2.5pt), align: right,
    [], [Born], [finite], [$1 slash epsilon$], [$1 slash epsilon^2$],
    [value, GeV#super[−6]], sci(fv.born, d: 5), sci(fv.virtual.at(0), d: 5), sci(fv.virtual.at(1), d: 5), sci(fv.virtual.at(2), d: 5),
    [rotated copy, rel. diff.], [], sci(fv.rotation_relative.finite), sci(fv.rotation_relative.single_pole), sci(fv.rotation_relative.double_pole),
    [NJet (no top), deviation], sci(nv.python_path_point0.born), [top loops], sci(nv.python_path_point0.single_pole), sci(nv.python_path_point0.double_pole),
  )))
  #v(-0.2em)
  The finite part differs from NJet's by the top-loop contribution
  (#sci(nv.python_path_point0.finite_difference, d: 2), i.e.
  #fixed(nv.python_path_point0.finite_difference_floor_units, 3) $|B| alpha_s slash 2 pi$),
  which continues the sign and size seen at four to six legs; it is not a test.
]

// ============================================================ CAPABILITY ==
= Capabilities at this milestone <capabilities>

#let st-style = (
  supported: (rgb("#2166ac"), white, [supported]),
  partial: (rgb("#d1e5f0"), black, [partial]),
  progress: (rgb("#fde7c7"), black, [in progress]),
  open: (rgb("#fddbc7"), black, [open]),
  deferred: (luma(225), black, [deferred]),
)
#let badge(s) = { let (f, t, name) = st-style.at(s); box(fill: f, inset: (x: 4pt, y: 2pt), radius: 2pt, text(6.8pt, fill: t, weight: "bold", name)) }
#let caps = (
  ([Recursive engine], "supported", [Trees, families and loop numerators from recursions; no loop diagram is enumerated (FeynKit graphs are test oracles only). Counterterms: see below.]),
  ([Full, NLC and LC colour], "supported", [Exact seed tables in $N_c$; LC/NLC by generated classes and truncated cells. LC is not yet cheaper to generate at seven legs.]),
  ([Colour and spin correlations], "supported", [Directed colour histories at LC/NLC/FC, spin sources, resolved helicities, flavour aliases, Ward sources (WP2.5). Seven-leg directed LC/NLC tables need the Rust seed tables (WP3.1).]),
  ([Per-order partials], "supported", [Every squared coupling order at tree level and at one loop, mixed Born orders, per-correction loop orders.]),
  ([Poles at runtime], "partial", [`poles = "all" | "none"`: finite-only mode with the finite part bitwise unchanged and the poles explicitly absent. `"uv" | "ir"` in progress with the user's semantics of 23 October.]),
  ([Stability estimates], "supported", [Rotation checks (any number, 0 = estimate absent), reduction direction, exact rescaling, in any combination; no automatic escalation (WP2.3).]),
  ([Precision carriers], "supported", [Binary64, DoubleFloat, arbitrary precision and exact rationals in the native executor; DD/AP point inputs are formed in Python Decimal until WP3.1.]),
  ([Native executor, schedules], "supported", [Rust, 16 lanes, threads; schedule B by default, M native (adopted per class at G1), F as oracle. The NinjaRS reduction runs serially.]),
  ([Plan v4 artifacts and API], "partial", [Published and loaded through Python, TOML and CLI; relocation to another path tested on the same host and CPU; loading regenerates the per-point inputs in Python, and the Rust/C/C++/Fortran SDK refuses v4 until WP3.1.]),
  ([Counterterms (model UV, $R_2$)], "partial", [Site closure is the public route (QCD incl. massive quarks), a form the user reserves for test oracles; counterterms inside the recursion are on `work/v2-ct-recursion` (WP2.2).]),
  ([Direct $R_2$], "deferred", [A bonus by the user's rule; bounded controls only.]),
  ([Electroweak, complex mass], "open", [Tree EW lanes fixed, the Dirac–Weyl class refused; loop EW, Goldstones and CMS are WP3.2.]),
  ([Required $2 -> 5$ set], "progress", [On the WP3.1 branch seven of eight generate and six agree with their provider references in all coefficients (@tab:validation); $g g -> g g g g g$ is validated in Born and poles; the EW target is not started.]),
  ([Performance gates], "open", [G1 not run; no gate result (front page).]),
  ([$g g -> 6g$], "deferred", [No $2 -> 6$ work until the $2 -> 5$ plan is complete (user, 23 October).]),
)
#figure(kind: table,
  caption: [*Capability matrix* of the v2 engine on `loop` at #ms.engine_revision, with branch work marked.],
  tstyle(table(
    columns: (3.5cm, 1.6cm, 1fr), align: (x, y) => if x == 1 { center + horizon } else { left + horizon },
    inset: (x: 4.5pt, y: 3.0pt), stroke: tstroke, fill: thead-fill,
    table.header[Feature][Status][Boundary],
    ..caps.map(((f, s, b)) => (text(weight: "semibold", f), badge(s), b)).flatten(),
  )),
) <tab:caps>

// ========================================================= ARCHITECTURE ==
= Architecture of the v2 engine <arch>

== The computed quantity

For Born order $a$, loop order $b$ and squared coupling order $s = a + b$,
$
  V_(s,k) = cal(N) sum_(a+b=s) 2 op("Re")[B_a^dagger G_(B L) L_(b,k)], quad k in {0, -1, -2},
  quad V = C_epsilon (V_0 + V_(-1) / epsilon + V_(-2) / epsilon^2), quad C_epsilon = (4 pi)^epsilon / Gamma(1 - epsilon),
$
where $G_(B L)$ is the colour metric between Born and loop colour structures and
$cal(N)$ holds the initial-state averages and identical-particle factors
(MadLoop/BLHA convention; couplings included, nothing divided by the Born).
Directed colour and spin correlations replace $2 op("Re")(dots)$ by the two
cross terms $B_A^dagger G L_B + L_A^dagger G B_B$.

== Pipeline

For every denominator family $f$, sector $s$ and observable column $o$, v2
builds the four-dimensional numerator $N_(f,s,o)(q) = sum_alpha c_alpha q^alpha$
that NinjaRS reduces: Born-weighted and helicity-summed, produced by three
recursions that share all work (@fig:pipeline).

#let stage-box(title, owner, kind) = {
  let (f, s) = if kind == "py" { (rgb("#fdf0e6"), 0.7pt + rgb("#d6604d")) } else if kind == "nat" { (rgb("#e8f1f8"), 0.7pt + rgb("#2166ac")) } else { (white, 0.7pt + luma(150)) }
  block(width: 100%, height: 1.3cm, fill: f, stroke: s, inset: (x: 3pt, y: 3pt), radius: 2pt, align(center + horizon, {
    set par(justify: false, leading: 0.32em)
    set text(6.8pt, font: sans)
    text(weight: "bold", title)
    linebreak()
    text(6.1pt, fill: ink2, owner)
  }))
}
#let arr = align(center + horizon, text(8pt, fill: luma(120), sym.arrow.r))
#let lane(body) = align(center + horizon, rotate(-90deg, reflow: true, text(6.6pt, font: sans, fill: ink2, weight: "bold", body)))
#figure(
  caption: [*v2 pipeline.* Upper lane: generation, once per process, into a
    plan v4 artifact. Lower lane: evaluation per batch of points. Blue: native
    batched numerics in the Rust executor; orange: still formed in Python per
    point (native lanes on the WP3.1 branch); white: generation. The owning
    code or dependency is named under each step.],
  grid(columns: (0.45cm, 1fr, 8pt, 1fr, 8pt, 1fr, 8pt, 1fr, 8pt, 1fr, 8pt, 1fr), row-gutter: 6pt, column-gutter: 1pt,
    lane[generation],
    stage-box([Loop kernel catalogue], [UFO loader, Symbolica, Idenso], "plain"), arr,
    stage-box([Tree blocks in loop mode], [tree engine: all-subset currents, Born], "plain"), arr,
    stage-box([Families by loop-prefix recursion], [pyAmpliCol; native in Rust], "plain"), arr,
    stage-box([Skeleton tries B, merged graph M], [pyAmpliCol, rusticol-core], "plain"), arr,
    stage-box([Exact seed tables $K[c,b]$], [colour flow, Laurent in $N_c$], "plain"), arr,
    stage-box([Counterterm program; plan v4], [site closure / CT recursion], "plain"),
    lane[evaluation],
    stage-box([Exact inputs, invariant table], [Rust executor], "nat"), arr,
    stage-box([Blocks, Born, CT scalars], [Python per point → WP3.1], "py"), arr,
    stage-box([Seeds $U_0 = K overline(A_0)$], [Rust executor], "nat"), arr,
    stage-box([Dressing, B or M], [threads × 16 lanes], "nat"), arr,
    stage-box([Reduction, master cache], [NinjaRS, oneloopmaster], "nat"), arr,
    stage-box([Assembly, checks, estimates], [$2 op("Re")$ + UV + $R_2$ + fields], "py"),
  ),
) <fig:pipeline>

*Trees.* The tree engine's colour-ordered Berends–Giele recursion computes,
once per point, every off-shell current over every leg subset a loop vertex can
absorb (the _blocks_), the Born colour components $A_0$ and, with WP2.2, every
tree with one counterterm vertex. A loop-aware reachability test keeps exactly
the currents some family position or root needs. Blocks with transverse
sources use the exact transverse Yang–Mills kernels; loop segments,
counterterm currents and Ward sources use the full ones.

*Families and skeletons.* A Recola-type recursion over loop prefixes (ordered
leg sets, propagator species and masses) yields the denominator families, keyed
by the canonical cyclic sequence of (leg mask, mass) and equal to Recola's
tensor-integral identities. Per family it yields the colour-ordered
_skeletons_: rings of blocks, each block summing all trees on its leg subset
(@fig:graphs). Skeletons are never stored as a list; they are the leaves of the
schedule tries. Only certified structural zeros are dropped (scaleless rings,
external wave-function corrections, VEV tadpoles, colour zeros); nothing is
restricted to 1PI.

#figure(
  caption: [Three graphs of $u overline(u) -> g g g$ drawn by FeynKit's
    renderer from its own generation (an oracle, not a production input).
    In v2 the Born (left) is a closure of blocks; the pentagon (middle) is a
    ring of five single-leg blocks; the box with a tree attachment (right) is a
    ring of four blocks, one of them the two-leg current, computed once per
    point and shared by every skeleton that contains that leg subset.],
  grid(columns: 3, gutter: 10pt,
    ..("born", "pentagon", "box").map(n => box(height: 3.0cm, image("figures/" + n + ".svg", height: 100%, fit: "contain")))),
) <fig:graphs>

*Loop numerators and schedules.* An open-loop recursion dresses skeletons one
segment at a time with polynomial-valued objects,
$O' = O dot Y + "raise"(O dot Z_mu, q^mu)$, in the NinjaRS monomial layout
($binom(r + 4, 4)$ coefficients at rank $r$, no rank cap). The seed is the
colour-summed Born interference, and each block's helicities are summed as it
is attached. One generator feeds three schedules (@tab:schedules).

#figure(kind: table,
  caption: [*Three schedules on one generator* (DESIGN §2.2, §5.6).],
  tstyle(table(
    columns: (2.2cm, 1fr, 1fr, 1fr),
    align: left + horizon, inset: (x: 4pt, y: 3pt), stroke: tstroke, fill: thead-fill,
    table.header[][F: forward][B: suffix trie (default)][M: merged, primitive-seeded],
    [Born weighting], [at closure], [at the leaves (one seed per skeleton class)], [at the cut, one seed per colour ordering],
    [Shared], [prefixes across families], [all prefixes with equal family and remainder], [prefixes across families and compositions],
    [Colour], [none needed], [none needed], [certified classes: adjoint rings, traces, quark rings],
    [Role], [oracle], [default; generic fallback], [pure-gluon classes; $n >= 8$ default],
  )),
) <tab:schedules>

*Colour.* Colour lives only in exact seed tables $K[c, b]$, Laurent polynomials
in $N_c$ between seed classes $c$ (the colour vector obtained by closing the
cut of a skeleton's colour flow) and Born basis elements $b$; per point the
seeds are $U_0 = sum_b K[c,b] overline(A_0[b])$, with a symmetric-group FFT where
certified. LC and NLC differ from full colour only in which classes are
generated and how cells are truncated: at LC each colour ordering is seeded by
its own Born amplitude and skeletons below the leading $N_c$ degree are never
generated. Certificates (adjoint rings, fundamental traces, quark rings) are
proved at loop level, never inherited from the tree level.

*Reduction and masters.* Families close directly into NinjaRS
`TensorNumerator` lanes: one reduction per (family, sector, column), families
with equal (propagators, rank) batched as lanes of one call, scalar masters
from oneloopmaster cached per event. A second reduction in a relabelled frame
reuses the numerators and the cached masters as the cheap stability check.

*Counterterms.* The model's UV and $R_2$ vertices enter as counterterm sites
admitted by a witness table with a power-counting completeness check; external
field factors are separate sources. The slice form closes the sites over block
currents (the public route today); the production form inserts one counterterm
order into the tree recursion (WP2.2), whose $g g -> g g g g g$ program leaves
no rule to site closure (@tab:sevendev).

*Precision, stability and assembly.* Every kernel is generic over binary64,
DoubleFloat, arbitrary-precision floats and exact rationals. A failed lane
fails its point and never branches a kernel. The assembly takes
$2 op("Re")$ of $i slash (16 pi^2)$ times the reduced family sum, plus local UV, $R_2$ and
field terms, per sector and column, with optional rotation, reduction-direction and rescaling estimates
and the finite-only mode. The public API selects `loop_engine = "v2"` from
TOML, CLI or Python and stores plan v4 as a relocatable PACBIN member (zlib
JSON of exact kernel term lists, no compiled code, digest checked at load).

#figure(kind: table,
  caption: [*Asymptotic classes per event* for $n$ gluons, full colour (DESIGN
    §1.4): $F_n approx (n - 1)! (1 / ln 2)^n \/ 2$ families, $2^n$ helicities.
    The required set ($n <= 7$) is far below the B/M crossover.],
  tstyle(table(
    columns: (4.2cm, 1fr),
    align: left + horizon, inset: (x: 4pt, y: 3pt), stroke: tstroke, fill: thead-fill,
    table.header[Stage or code][Class],
    [Tree blocks], [$Theta(n dot n!)$ currents; $Theta(n! dot 2^n)$ current-helicity rows],
    [Dressing, schedule B], [$Theta((n - 1)! dot 4^n)$ seed injection; trie dressing dominates for $n <= 8$],
    [Dressing, schedule M], [$Theta(n! dot 2^n dot n^4)$],
    [NinjaRS], [$Theta(F_n)$ reductions, $Theta(F_n dot n^8)$ work, $Theta(4^n)$ distinct masters after caching],
    [MadLoop (per diagram, per helicity)], [$Theta(D_n dot 2^n dot n^4)$, $D_n$ super-exponential ($g g -> g g g g$: 26 975 loop diagrams)],
    [Unitarity with exact helicity sums (NJet)], [$Theta((n - 1)! dot 2^n dot n^(6 dots 9))$],
  )),
) <tab:complexity>

#figure(kind: table,
  caption: [*Ownership of the mathematics.* pyAmpliCol reuses its dependencies
    for algebra, tensors, graphs and integrals and owns the recursions and the
    assembly.],
  tstyle(table(
    columns: (3.4cm, 1fr), align: left + horizon,
    inset: (x: 4.5pt, y: 3pt), stroke: tstroke, fill: thead-fill,
    table.header[Component][Responsibility],
    [ufo_model_loader], [Lossless UFO loop-model import: Laurent-valued parameters and couplings, UV/$R_2$ categories, loop groups],
    [Symbolica], [Expressions, coefficient extraction in $q$, evaluators; exact rationals and arbitrary precision],
    [Spenso, Idenso (Community)], [Lorentz and colour tensors behind the kernel catalogue and the colour metrics],
    [FeynKit (Community)], [Test oracles: graph and family counts, overall factors, drawings (@fig:graphs)],
    [NinjaRS, oneloopmaster], [Integrand reduction with Laurent expansion; scalar masters in all carriers],
    [pyAmpliCol tree engine], [Blocks, Born, coupling orders and colour flow (Python lane; Rust recurrence)],
    [pyAmpliCol loop v2], [Families, skeletons, schedules, seed tables, counterterm program, plan v4, native executor, API],
  )),
) <tab:deps>

// ============================================================== HISTORY ==
= History: legacy per-diagram engine, 2026-10-18 <history>

#box-note(fill: luma(244))[
  #set par(justify: false)
  *History only.* These timings measure the superseded per-diagram engine
  (per-graph coefficient programs, pairwise colour overlaps, whole-process
  symbolic projectors) through its Python coordinator with exact decimal
  input, on repeated three-point streams, against providers that kept their
  protocol settings (actual poles, stability checks and rescue). They are
  neither the gate protocol nor the v2 engine, include $2 -> 2$ processes, and
  are kept for reference without gate counts. Revisions #hm.revision.slice(0, 8)
  and two follow-ups; #hm.reference_protocol.cpu_model.
]

#let providers = ("madloop", "recola", "openloops")
#let pshort(p) = (madloop: "ML", recola: "Recola", openloops: "OL").at(p)
#let record(c, b, p) = if p == "pyamplicol" {
  c.timings.at(str(b), default: none)
} else {
  hm.references.at(c.case, default: (:)).at("timings", default: (:)).at(str(b), default: (:)).at(p, default: none)
}
#let median(c, b, p) = { let r = record(c, b, p); if r == none { none } else { r.median_us_per_point } }
#let fastest(c, b) = {
  let found = providers.map(p => (p: p, v: median(c, b, p))).filter(r => r.v != none)
  if found.len() == 0 { none } else { found.sorted(key: r => r.v).first() }
}
#let missing(c, p) = hlab.missing_markers.at(c.case + "/" + p, default: hlab.missing_markers.at("default"))
#let hlabel(key) = { let l = hlab.case_labels.at(key, default: none); if l == none { raw(key) } else { math-label(l) } }
#let case-note(key) = (dy: "photon only", "ee-mumu-ew": [full EW, $G_mu$]).at(key, default: "QCD")
#let rt-cell(c, b, p) = {
  let r = record(c, b, p)
  let best = fastest(c, b)
  if r == none { return table.cell(text(6.8pt, fill: ink2, style: "italic", missing(c, p))) }
  let v = r.median_us_per_point
  let ml-timed = median(c, b, "madloop") != none
  let ratio = if best == none { none } else { v / best.v }
  table.cell(fill: if ml-timed { ratio-fill(ratio) } else { none }, {
    text(8pt, weight: "bold", sig(v))
    h(1fr)
    if p != "pyamplicol" and best != none and best.p == p { text(6.6pt, fill: ink2)[fastest] } else if ratio != none { text(7.2pt, weight: "semibold", mult(ratio)) }
  })
}
#let hgen(c, p) = {
  let s = if p == "pyamplicol" { c.generation_s } else { hcold.cases.at(c.case, default: (:)).at(p, default: (:)).at("seconds", default: none) }
  table.cell(text(6.6pt, fill: ink2, if s == none { [—] } else [#if p == "openloops" [setup ]#sig(s) s]))
}
#figure(kind: table,
  caption: [*Legacy engine, µs per point* (#hm.date), binary64, full colour,
    all three Laurent coefficients; median of five warm calls; multiplier: time
    ÷ the fastest timed reference of that row, coloured only where MadLoop is
    timed. Grey rows: generation (pyAmpliCol fresh process to plan; MadLoop
    export and compilation; Recola generation; OpenLoops setup of a prebuilt
    library). $B$: points per call.],
  tstyle(table(
    columns: (2.9cm, 0.7cm, 1fr, 1fr, 1fr, 1fr),
    align: left + horizon, inset: (x: 4.5pt, y: 2.6pt),
    stroke: (x, y) => (top: if y <= 1 { none } else if calc.rem(y - 1, 3) == 0 { 0.6pt + luma(190) } else { hair }, left: if x >= 2 and y > 0 { hair } else { none }),
    fill: thead-fill,
    table.header[Process][$B$][pyAmpliCol (legacy)][MadLoop][Recola][OpenLoops],
    ..hm.cases.map(c => (
      table.cell(rowspan: 3, align: left + horizon, {
        text(8.6pt, font: "Libertinus Serif", hlabel(c.case))
        linebreak()
        tiny[#case-note(c.case) · #c.counts.loop_graphs loop graphs]
      }),
      [1], rt-cell(c, 1, "pyamplicol"), ..providers.map(p => rt-cell(c, 1, p)),
      [128], rt-cell(c, 128, "pyamplicol"), ..providers.map(p => rt-cell(c, 128, p)),
      tiny[gen.], hgen(c, "pyamplicol"), ..providers.map(p => hgen(c, p)),
    )).flatten(),
  )),
) <tab:history>
#legend()

The per-diagram design could not reach the $2 -> 5$ set: a seven-leg
generation ran for more than nine hours without a result, and its counterterm
enumeration alone needed up to 77 GiB. The v2 engine replaced its numerator,
colour and counterterm core (@arch) and keeps model import, the counterterm
rules, Born weighting before reduction, the NinjaRS/oneloopmaster adapter, the
exact carriers and the public interfaces.

// ============================================================== SOURCES ==
= Sources and reproducibility <sources>

#set par(justify: false)
#text(8.6pt)[
  - *Build:* `typst compile benchmarks.typ benchmarks.pdf` in
    `docs/performance_reports/loop/` (Typst 0.15).
  - *Status, gates, in-flight work, decisions:* `data/milestone.json`, from the
    `Integrate …` merges on the first-parent history of #ms.engine_revision
    since #ms.previous_loop, `workspace/reports/engine-v2/slice-status.md`
    (Current state, Integrated packages, DECISIONS 2026-10-23),
    `HANDOFF_22_10_2026.md` §0–§3, MASTER_PLAN 2026-10-23 entries and
    `docs/development/loop_v2/REQUIREMENTS_ADDENDUM.md` A, D, F, G, H.
  - *@tab:provgen:* provider columns HANDOFF §0.1 (addendum F); pyAmpliCol
    column DESIGN WP3.1 third increment "Generation per process" on
    `work/v2-generation-scale` (201efa8b). *@tab:validation:* DESIGN WP3.1
    first to fourth increment, same branch (records
    `workspace/tmp/generation-scale/runs/`); the $g g -> g g g g$ row from
    `cmp_gg_gggg.json`, `cmp_gg_gggg_p1_stab.json` and `cmp_gg_gggg_p1_dd.json`
    there. *@tab:gateref:* DESIGN §1.3 Table 1b.
  - *@tab:native, @tab:split:* DESIGN §5.6 and §5.5 (data
    `workspace/reports/engine-v2/wp28-g1/`); the M/B ratios as §5.6 prints them.
  - *@tab:njet* and NJet prose: `workspace/reports/engine-v2/njet-benchmark.md`
    §2, §5, §6 (raw `workspace/reference/runs/njet/timing/`); arXiv:1209.0100
    Table 5.
  - *@tab:sevendev, @tab:sevencheck, first virtual:* `data/measured.json`,
    written by `scripts/collect_milestone.py <workspace>` from the records
    `gen_gg_ggggg_final`, `gen_gg_ggggg_hash`, `poles2_gg_ggggg`,
    `eval2_gg_ggggg`, `eval2_gg_ggggg_rot` and `cmp_uux_ggggg` in
    `workspace/tmp/generation-scale/runs/` and `gg_ggggg` in
    `workspace/tmp/ct-recursion/s4/` (JSON and `/usr/bin/time` logs: wall time,
    peak memory, CPU share); thread settings from DESIGN WP3.1 (generation, one
    thread) and ct-recursion DESIGN §6.1 (`RAYON_NUM_THREADS=1`, bind not
    measured); the 119/3 shift and NJet deviations from njet-benchmark.md §5.3
    and the fixture
    `tests/fixtures/loop/required/gg_ggggg_njet.json`; top-free values from
    DESIGN WP3.1 fourth increment and `tests/unit/test_loop_v2_topfree.py`
    (`work/v2-generation-scale`). Memory is shown in GiB = KiB/2²⁰.
  - *@tab:caps, @arch:* `docs/development/loop_v2/DESIGN.md` §1–§3, §5.5,
    §5.6, §10, §12 and the integration records above.
  - *@tab:history:* `data/measurements.json`, `data/provider-cold.json`
    (legacy snapshot of 2026-10-18, unchanged) and `data/legacy-labels.json`.
    `data/colour-measurements.json` (legacy LC/FC runs) stays for the DESIGN
    citations; the legacy status registry, audit and generation data are
    archived outside the repository (`workspace/reports/report-data-archive/`).
  - *Conventions:*
    #link("https://cp3.irmp.ucl.ac.be/projects/madgraph/wiki/MadLoopStandaloneLibrary")[MadLoop standalone],
    #link("https://arxiv.org/abs/1605.01090")[Recola],
    #link("https://arxiv.org/abs/1907.13071")[OpenLoops 2],
    #link("https://arxiv.org/abs/1209.0100")[NJet].
]
