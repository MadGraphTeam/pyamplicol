// pyAmpliCol one-loop report, gate G1 of 2026-10-24. Table values are read
// from data/*.json (g1.json: the G1 campaign, tools/loop_benchmark;
// milestone.json: registry with sources; measured.json:
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
// Long tables continue on the next page (headers repeat) instead of leaving
// a blank page end.
#show figure.where(kind: table): set block(breakable: true)
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
#let box-note(fill: pale, stroke: none, breakable: true, body) = block(width: 100%, fill: fill, stroke: stroke, breakable: breakable, inset: 9pt, radius: 3pt, text(9pt, body))
#let flag(body) = box(fill: warm, inset: (x: 3pt, y: 1.5pt), radius: 2pt, text(6.6pt, weight: "bold", fill: rgb("#8a4b08"), body))

// ===================================================================== G1 ==
// Gate G1 (WP2.7): data/g1.json, written by `python -m tools.loop_benchmark
// gate` from the pyAmpliCol and provider records of the campaign.
#let g = json("data/g1.json")
#let gproc(key) = g.processes.find(p => p.key == key)
#let glabels = (
  gg_gg: "g g -> g g", uux_ddxg: "u overline(u) -> d overline(d) g",
  uux_uuxg: "u overline(u) -> u overline(u) g", uux_ggg: "u overline(u) -> g g g",
  gg_ggg: "g g -> g g g", gg_gggg: "g g -> g g g g",
  gg_ttxgg: "g g -> t overline(t) g g", uux_gggg: "u overline(u) -> g g g g",
)
#let gkeys = g.processes.map(p => p.key)
#let gname(key) = text(8.6pt, font: "Libertinus Serif", math-label(glabels.at(key)))
#let cfg(p, name) = p.pyamplicol.at(name, default: none)
#let sizes(c) = if c == none { () } else { c.batches.keys().map(int).sorted() }
#let top(c) = { let s = sizes(c); if s.len() == 0 { none } else { str(s.last()) } }
#let bat(c, b) = if c == none or b == none { none } else { c.batches.at(b, default: none) }
#let msec(s) = sig(s * 1000)
#let mult2(r) = [×#if r >= 10 { fixed(r, 0) } else if r >= 1 { fixed(r, 1) } else { fixed(r, 2) }]
#let ptime(p, n) = if p.providers == none { none } else { p.providers.at(n, default: (:)).at("mean_seconds_per_point", default: none) }
#let pnames = ("madloop", "recola", "openloops")
#let fastest-p(p) = {
  let ts = pnames.map(n => (n: n, t: ptime(p, n))).filter(x => x.t != none)
  if ts.len() == 0 { none } else { ts.sorted(key: x => x.t).first() }
}
#let stage(x, name) = x.stages_per_point.at(name, default: 0.0)
#let python-inputs(x) = ("python trees", "python counterterm program", "python scalars",
  "python Born and counterterm components").map(n => stage(x, n)).sum()
#let glue(x) = ("python point parameters", "input conversion", "assembly", "other").map(n => stage(x, n)).sum()
#let numerator(x) = ("seeds", "factors", "dressing").map(n => stage(x, n)).sum()
#let masters(x) = stage(x, "reduction: masters")
#let ninjars(x) = stage(x, "reduction") - masters(x)
#let verdict(x) = if x == none { none } else { x.gate }
#let gate-word(gt) = if gt == none [—] else if gt.status == "pass" {
  text(fill: rgb("#2166ac"), weight: "bold")[pass] + [ #fixed(gt.ratio_to_binding_limit, 2)]
} else if gt.status == "fail" {
  text(fill: rgb("#b2182b"), weight: "bold")[fail] + [ #mult2(gt.ratio_to_binding_limit)]
} else { text(fill: ink2, gt.status) }
#let rev(c) = if c == none { none } else { c.revision.slice(0, 8) }
#let slice-c(p) = cfg(p, "python/full")
#let dev-c(p) = cfg(p, "native/full")
#let gated = g.processes.filter(p => p.gated)

#let ratio-range(xs) = if xs.len() == 0 [—] else { let s = xs.sorted(); if s.len() == 1 [#mult2(s.first())] else [#mult2(s.first())–#fixed(s.last(), if s.last() >= 10 { 0 } else { 1 })] }
#let lim(p, c, b) = { let x = bat(c, b); if x == none or x.gate.status not in ("pass", "fail") { none } else { x.gate.ratio_to_binding_limit } }
#let int-top = gated.map(p => lim(p, slice-c(p), top(slice-c(p)))).filter(r => r != none)
#let int-one = gated.map(p => lim(p, slice-c(p), "1")).filter(r => r != none)
#let dev-pass = gated.filter(p => { let r = lim(p, dev-c(p), top(dev-c(p))); r != none and r <= 1 })
#let dev-fail = gated.filter(p => { let r = lim(p, dev-c(p), top(dev-c(p))); r != none and r > 1 })
#let l1-c(p) = cfg(p, "native/full/L1")
#let l1-pass = gated.filter(p => { let r = lim(p, l1-c(p), "1"); r != none and r <= 1 })
#let share(x, v) = v / x.median_seconds_per_point
#let pct(v) = [#fixed(100 * v, 0) %]
#let inputs-share = gated.map(p => { let x = bat(slice-c(p), top(slice-c(p))); if x == none { none } else { share(x, python-inputs(x) + stage(x, "input conversion")) } }).filter(v => v != none)
#let trees-share = gated.map(p => { let x = bat(dev-c(p), top(dev-c(p))); if x == none { none } else { (p: p, s: share(x, stage(x, "native trees"))) } }).filter(v => v != none)
#let speedup-native = gated.map(p => { let (a, d) = (bat(slice-c(p), top(slice-c(p))), bat(dev-c(p), top(dev-c(p)))); if a == none or d == none { none } else { a.median_seconds_per_point / d.median_seconds_per_point } }).filter(v => v != none)
#let lanes-gain = gated.map(p => { let (a, b) = (bat(dev-c(p), "1"), bat(l1-c(p), "1")); if a == none or b == none { none } else { a.median_seconds_per_point / b.median_seconds_per_point } }).filter(v => v != none)
#let names(ps) = ps.map(p => gname(p.key)).join([, ], last: [ and ])
#let repeat-spread = calc.max(..g.processes.map(p => p.provider_repeats.values().map(rs => {
  let ts = rs.map(r => r.mean_seconds_per_point)
  (calc.max(..ts) - calc.min(..ts)) / calc.min(..ts)
})).flatten())
#let block-spread = calc.max(..gated.map(p => {
  let x = bat(dev-c(p), top(dev-c(p)))
  calc.max(x.max_seconds_per_point / x.median_seconds_per_point - 1, 1 - x.min_seconds_per_point / x.median_seconds_per_point)
}))
#let near(p) = { let r = lim(p, dev-c(p), top(dev-c(p))); r != none and r > 0.95 and r <= 1 }

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
recursions, and no loop Feynman diagram is enumerated (@arch). Counterterms
come from the tree recursion (WP2.2); in production they will be plain tree
vertices inserted exactly once, without loop matching (addendum J; `ct-simplify`
in flight). This report records *gate G1*, the first end-to-end measurement of
v2 against MadLoop, Recola and OpenLoops (@g1), on the engine published on
`loop` on 24 October (measured at dfa6bf7c; #ms.engine_revision adds a
generation-only counterterm fix) and, as a development configuration, on the
WP3.1 branch whose native per-point inputs are being integrated.

#let g1-badge = {
  let n = gated.len()
  [G1: integrated slice fails #int-top.len() of #n · native inputs#super[dev] pass #dev-pass.len() of #n]
}
#grid(columns: (1.2fr, 1fr), gutter: 8pt,
  box-note[
    #set par(justify: false)
    *Published on `loop` on 24 October* (engine #ms.engine_revision\; merges since #ms.previous_loop)
    #v(-0.2em)
    #set text(8.2pt)
    #table(columns: (auto, auto, 1fr), stroke: none, inset: (x: 2pt, y: 2.4pt),
      ..ms.integrated.map(r => (raw(r.sha), text(weight: "semibold", r.wp), [*#r.title.* #text(fill: ink2, r.detail)])).flatten())
    #v(-0.3em)
    #text(8.2pt)[*Before (#ms.previous_loop):* #ms.already_on_loop.
      *Native build* #raw(ms.native_build.name) (digest
      #raw(ms.native_build.digest)…).]
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
        build); pyAmpliCol finite-only (`poles = "none"`) with stability checks
        off, one pinned thread, the same frozen points.
      - *Status (G1, @tab:g1).* The integrated slice fails every gated process
        (#ratio-range(int-top) of the limit): its per-point inputs still run in
        Python. With native inputs #flag[development] #dev-pass.len() of
        #gated.len() pass at the largest batch; #names(dev-fail) fails
        (@tab:levers).
      - *Seven legs* follow with the WP3.1 generator (`measure-g1-7leg`); no
        matched provider timing exists for $g g -> g g g g g$: its speed is
        reported without a gate (@tab:provgen, @tab:sevencheck).
      - *History.* The timings of 2026-10-18 measure the superseded per-diagram
        engine and appear only in @history.
    ]
    v(0.2em)
    align(center, box(fill: warm, inset: (x: 8pt, y: 4pt), radius: 3pt,
      text(8.6pt, weight: "bold", fill: rgb("#8a4b08"), g1-badge)))
  }),
)

#grid(columns: (1fr, 1fr), gutter: 8pt,
  box-note(fill: white, stroke: 0.6pt + luma(205))[
    #set par(justify: false)
    *In flight* (branches, not on `loop`)
    #set text(8.4pt)
    - *Generation at scale* (WP3.1 G-int, `work/v2-generation-scale`): native
      trees, Born and counterterm inputs, regeneration-free artifacts; timed
      here as the native-input configuration; audit and integration next.
    - *Rust ports* (HANDOFF §0.4): native loop DAG (A1–A2), seeds (B), cells
      (C) and lowering (D), phase 0.
    - *`ct-simplify`* (fix round after a refused integration): removes the
      witness-table admission and loop matching (addendum J); a public
      `particle_veto` replaces the internal top-free switch.
    - *`measure-g1-7leg`*: the seven-leg G1 rows after WP3.1; *electroweak*
      and complex mass (WP3.2) pending.
  ],
  box-note(fill: white, stroke: 0.6pt + luma(205))[
    #set par(justify: false)
    *User decisions of 23 October*
    #set text(8.4pt)
    - *Counterterms* (addendum J): model $R_2$ and UV vertices are plain tree
      vertices inserted exactly once, admitted by coupling orders and a public
      `particle_veto`; no witness table or loop matching in production (site
      closure and witnesses: test oracles only).
    - *Poles:* `"uv"` = UV poles of the bare loop, the counterterms' UV poles
      separate; `"ir"` = Catani poles of the renormalised virtual; one finite part.
    - *Rust* (HANDOFF §0.4): heavy, contained generation stages move to
      rusticol (PyO3 API) with oracle equality; new heavy code in Rust.
    - Generation may take O(hours) below 150 GB (addendum H); $g g -> g g g g g$
      speed without a gate, with rotation and Ward checks; no $2 -> 6$ before
      the $2 -> 5$ plan is complete.
    - Binary64 observables: $10^(-12)$ unless the own estimate $E > 10^(-12)$ (then
      $E$, capped at $10^(-9)$, plus DD within $10^(-24)$).
    - Stability-estimate tests: tenfold margin (error ≤ 10 $E$). Development
      first, proportionate testing; push to `loop` at milestones with this report.
  ],
)

= Gate G1: end-to-end timings of the v2 engine <g1>

G1 times the complete Born–virtual evaluation, *finite part only*, through the
call of the public v2 runtime (`NativeExecutor.evaluate`, which
`V2VirtualRuntime` calls) with stability checks off, on one pinned core and
one thread, binary64, 16 SIMD lanes, in batches of $B$ distinct points of a
frozen stream (REQUIREMENTS_ADDENDUM D, plan §5.8). Two pyAmpliCol
configurations are timed:

- *integrated* — the published engine (`work/v2-slice` #raw(g.slice_revision),
  on `loop` since 24 October, with this package's timers): trees, Born amplitudes
  and counterterm scalars are still formed per point in Python, then the loop
  stage runs natively;
- *native inputs* #flag[development] — `work/v2-generation-scale`
  #raw(g.native_revision) (WP3.1, under integration), where the executor also
  forms the trees, the Born and the counterterm inputs itself (same timers;
  a scratch release build of that branch).

The providers run in production mode on the same stream: OpenLoops with
`truepoles 0`, Recola without IR poles (one amplitude call per point), MadLoop
at its production stability setting on exports built with MG5's production
flags; mean per point over the stream's first 16 points (MadLoop
$g g -> g g g g$: 8), on the core that timed the native-input configuration
of the process. Providers have no batch API: one time per point serves every
$B$. The stream's first three points are the reference campaign's, and
pyAmpliCol's Born and finite part agree with every provider there and on all
common points (@tab:g1values).

#let g1-cell(p, c, b) = {
  let x = bat(c, b)
  if x == none { return table.cell(text(6.6pt, fill: ink2, style: "italic")[not timed]) }
  let t = x.median_seconds_per_point
  let best = fastest-p(p)
  let r = if best == none { none } else { t / best.t }
  table.cell(fill: ratio-fill(r), {
    text(8pt, weight: "bold", msec(t))
    h(1fr)
    if r != none { text(7.2pt, weight: "semibold", mult2(r)) }
  })
}
#let prov-missing = (
  uux_gggg: (madloop: [not exported], recola: [—]),
  gg_ttxgg: (:), gg_gggg: (recola: [generation 34 min; see text]),
)
#let p-cell(p, n) = {
  let t = ptime(p, n)
  if t == none {
    return table.cell(text(6.6pt, fill: ink2, style: "italic", prov-missing.at(p.key, default: (:)).at(n, default: [not timed])))
  }
  let best = fastest-p(p)
  let r = t / best.t
  table.cell(fill: ratio-fill(r), {
    text(8pt, weight: "bold", msec(t))
    h(1fr)
    if best.n == n { text(6.6pt, fill: ink2)[fastest] } else { text(7.2pt, weight: "semibold", mult2(r)) }
  })
}
#let gen-v2(c) = if c == none { table.cell(tiny[—]) } else {
  let st = c.generation
  table.cell(tiny[#sig(st.generate.seconds + st.export.seconds) s · #fixed(calc.max(st.generate.peak_gib, st.export.peak_gib), 1) GiB])
}
#let gen-p(p, n) = {
  let r = if p.providers == none { none } else { p.providers.at(n, default: none) }
  if r == none { return table.cell(tiny[—]) }
  if n == "madloop" {
    let gx = r.at("generation", default: none)
    table.cell(tiny[#if gx == none [export] else [#sig(gx.total_s) s]])
  } else if n == "recola" {
    let s = r.setup.at("generation_seconds", default: none)
    table.cell(tiny[#if s == none [—] else [#sig(s) s]])
  } else {
    table.cell(tiny[#r.library.name])
  }
}
#let gate-cell(p, b) = {
  if not p.gated { return table.cell(tiny[no gate]) }
  let a = verdict(bat(slice-c(p), b))
  let d = verdict(bat(dev-c(p), b))
  table.cell(text(6.8pt)[#gate-word(a) #linebreak() #gate-word(d)])
}
#figure(kind: table,
  caption: [*Gate G1, full colour*, ms per point (median over the timed blocks),
    finite part, one thread. Rows $B = 1$ and the largest batch timed ($B = 128$; the
    integrated $2 -> 4$ rows only at $B = 1$: their Python inputs take seconds per
    point). Multiplier and colour: time ÷ the fastest provider of the row (legend
    below). Grey rows: generation — pyAmpliCol generation plus plan export with
    its peak memory; MadLoop graph generation, export and compilation; Recola
    process generation; OpenLoops: the prebuilt library. MadLoop
    $u overline(u) -> g g g g$ was not exported: the $g g -> g g g g$ export took
    2.4 h here (HANDOFF §0.1), and OpenLoops binds the gate. Gate: upper line
    integrated, lower line native inputs; the number is the time over the binding
    limit (MadLoop's time or 1.30× the faster of Recola and OpenLoops), so
    below 1 passes. Provider times repeated on a second core agree within
    #pct(repeat-spread)\; pyAmpliCol's blocks spread by #pct(block-spread) at most
    around their median (largest batch, native inputs).],
  tstyle(table(
    columns: (2.75cm, 0.75cm, 1fr, 1fr, 1fr, 1fr, 1fr, 1.65cm),
    align: left + horizon, inset: (x: 4pt, y: 2.7pt),
    stroke: (x, y) => (top: if y <= 1 { none } else if calc.rem(y - 1, 3) == 0 { 0.6pt + luma(190) } else { hair }, left: if x >= 2 and y > 0 { hair } else { none }),
    fill: thead-fill,
    table.header[Process][$B$][Integrated][Native inputs#super[dev]][MadLoop][Recola][OpenLoops][Gate],
    ..g.processes.map(p => {
      let (a, d) = (slice-c(p), dev-c(p))
      let big = if top(d) == none { top(a) } else { top(d) }
      (
        table.cell(rowspan: 3, align: left + horizon, {
          gname(p.key)
          linebreak()
          tiny[#if p.gated [$2 -> #p.outgoing$] else [$2 -> 2$, no gate]]
        }),
        [1], g1-cell(p, a, "1"), g1-cell(p, d, "1"), ..pnames.map(n => p-cell(p, n)), gate-cell(p, "1"),
        [#big], g1-cell(p, a, big), g1-cell(p, d, big), ..pnames.map(n => p-cell(p, n)), gate-cell(p, big),
        tiny[gen.], gen-v2(a), gen-v2(d), ..pnames.map(n => gen-p(p, n)), table.cell(tiny[]),
      )
    }).flatten(),
  )),
) <tab:g1>
#legend()

== Where the time goes

#let seg-colours = (rgb("#d6604d"), rgb("#4393c3"), rgb("#92c5de"), rgb("#2166ac"), rgb("#053061"), luma(170))
#let bar(parts, total, width: 3.4cm) = box(width: width, height: 0.26cm, {
  let x = 0pt
  for (k, v) in parts.enumerate() {
    let w = width * calc.max(v, 0) / total
    place(dx: x, rect(width: w, height: 0.26cm, fill: seg-colours.at(k), stroke: none))
    x += w
  }
})
#let swatch(k) = box(fill: seg-colours.at(k), width: 5pt, height: 5pt, stroke: 0.3pt + white)
#let split-row(label, x) = {
  let parts = (python-inputs(x) + stage(x, "native trees"), numerator(x), stage(x, "scatter"), ninjars(x), masters(x), glue(x))
  let total = x.median_seconds_per_point
  (label, ..parts.map(v => align(right, msec(v))), align(right, text(weight: "bold", msec(total))), bar(parts, parts.sum()))
}
#let ml-row(p) = {
  let r = if p.providers == none { none } else { p.providers.at("madloop", default: none) }
  if r == none or r.at("stages", default: none) == none { return () }
  let s = r.stages.stages_seconds_per_point
  let parts = (s.at("Born and counterterm HELAS"), s.at("loop numerator coefficients"), 0.0, s.at("reduction and masters"), 0.0, r.stages.residual_seconds_per_point)
  (tiny[MadLoop],
    align(right, msec(parts.at(0))), align(right, msec(parts.at(1))), align(right, dim[—]),
    table.cell(colspan: 2, align(center, msec(parts.at(3)))), align(right, msec(parts.at(5))),
    align(right, text(weight: "bold", msec(r.stages.instrumented_seconds_per_point))),
    bar(parts, parts.map(v => calc.max(v, 0)).sum()))
}
#figure(kind: table,
  caption: [*Stage split*, ms per point, full colour, at the largest batch timed
    (integrated $2 -> 4$: $B = 1$). Trees/Born/CT: the per-point inputs — in
    Python for the integrated slice (trees, counterterm program, Born and
    counterterm colour projections, scalars), in the executor with native
    inputs. Numerator: seeds, fused factors and the dressing of the open-loop
    objects (the pure numerator evaluation). Scatter: closures into NinjaRS
    lanes. NinjaRS: the reduction without the masters; masters: the master
    integrals (canonical arguments, cache, oneloopmaster). Glue: point
    parameters, carrier conversion, assembly and the rest of the Python call.
    MadLoop (instrumented copy, 15 points; 3 for $g g -> g g g g$):
    Born/counterterm HELAS calls, loop-numerator coefficients, reduction plus
    masters, residual (stability test, colour sums). Bar: shares, colours as the
    column heads.],
  tstyle(table(
    columns: (2.4cm, 1.2cm, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr, 1.3cm, 3.0cm),
    align: left + horizon, inset: (x: 3.5pt, y: 2.5pt),
    stroke: (x, y) => (top: if y <= 1 { none } else if x == 0 and y > 1 { hair } else { hair }),
    fill: thead-fill,
    table.header[Process][][#swatch(0) Trees, Born, CT][#swatch(1) Numerator][#swatch(2) Scatter][#swatch(3) NinjaRS][#swatch(4) Masters][#swatch(5) Glue][Total][Shares],
    ..g.processes.map(p => {
      let rows = ()
      let (a, d) = (slice-c(p), dev-c(p))
      if d != none { rows.push(split-row(tiny[native#super[dev]], bat(d, top(d)))) }
      if a != none { rows.push(split-row(tiny[integrated], bat(a, top(a)))) }
      let m = ml-row(p)
      if m.len() > 0 { rows.push(m) }
      let n = rows.len()
      rows.enumerate().map(((i, r)) => if i == 0 { (table.cell(rowspan: n, align: left + horizon, gname(p.key)), ..r) } else { r }).flatten()
    }).flatten(),
  )),
) <tab:g1split>


#box-note(fill: warm, breakable: false)[
  #set par(justify: true)
  *Verdict of gate G1* (processes from $2 -> 3$; $2 -> 2$ without a gate).
  - *Integrated slice: fails* every process, at #ratio-range(int-top) of the
    binding limit at the largest batch and #ratio-range(int-one) at $B = 1$. The
    per-point Python inputs take #pct(calc.min(..inputs-share))–#pct(calc.max(..inputs-share))
    of its time (@tab:g1split); the native loop stage alone is far below the limits.
  - *Native inputs* #flag[development]: at the largest batch it *passes* for
    #names(dev-pass) and *fails* for #names(dev-fail)
    (#dev-fail.map(p => [#mult2(lim(p, dev-c(p), top(dev-c(p))))]).join([, ]) of the
    limit, OpenLoops binding)#if gated.filter(near).len() > 0 [; #names(gated.filter(near)) passes
    within the timing spread (#gated.filter(near).map(p => fixed(lim(p, dev-c(p), top(dev-c(p))), 2)).join([, ]) of its limit; #fixed(lim(gproc("uux_uuxg"), dev-c(gproc("uux_uuxg")), "32"), 2) at $B = 32$)]. At $B = 1$ with 16 lanes it fails everywhere (a
    one-point call pays a 16-lane chunk); with one lane per call it passes for
    #names(l1-pass).
  - *Fastest of all tools* (aspiration): with native inputs at the largest batch
    pyAmpliCol is the fastest code for
    #names(gated.filter(p => { let x = bat(dev-c(p), top(dev-c(p))); x != none and x.gate.ratio_to_fastest < 1 })),
    and slower than OpenLoops for
    #names(gated.filter(p => { let x = bat(dev-c(p), top(dev-c(p))); x != none and x.gate.ratio_to_fastest >= 1 })).
    NJet, not a matched provider, takes 4.58 s for its two-evaluation
    full-colour $g g -> g g g g$ test (@tab:njet).
  - Seven-leg rows ($u overline(u) -> e^- e^+ d overline(d) g$, $u overline(u) -> e^- e^+ g g g$,
    $g g -> t overline(t) e^- e^+ g$, $u overline(u) -> g g g g g$, $g g -> g g g g g$)
    need the WP3.1 generator and are added by the follow-on package
    `measure-g1-7leg`; $g g -> g g g g g$ has no matched provider timing
    (addendum F, H): reported without a gate.
]

#figure(kind: table,
  caption: [*Levers*, measured on the rows of @tab:g1split. Gains are
    measured where a column says so; otherwise they are the stage's share, an
    upper bound.],
  tstyle(table(
    columns: (4.1cm, 1fr, 3.2cm, 2.9cm),
    align: left + horizon, inset: (x: 4pt, y: 3pt), stroke: tstroke, fill: thead-fill,
    table.header[Lever][Evidence][Expected gain][Owner],
    [*Native per-point inputs* (WP3.1 I3–I6: trees, Born, counterterm scalars in the executor)],
    [Python inputs #pct(calc.min(..inputs-share))–#pct(calc.max(..inputs-share)) of the integrated time],
    [measured: #ratio-range(speedup-native) (integrated ÷ native, largest $B$)],
    [`generation-scale` (G-int, under integration)],
    [*Compiled native trees* (kernels as the tree engine's SymJIT planes, lanes batched)],
    [native trees #pct(calc.min(..trees-share.map(t => t.s)))–#pct(calc.max(..trees-share.map(t => t.s))) of the native-input time; #gname(trees-share.sorted(key: t => t.s).last().p.key) #pct(trees-share.sorted(key: t => t.s).last().s)],
    [up to the share; ×#fixed(1 / (1 - calc.max(..trees-share.map(t => t.s))), 1) for the largest],
    [Rust ports A/B (`native-dag`, HANDOFF §0.4)],
    [*Lanes by batch* in binary64 (`plan_export.lanes_for`: 16 lanes also for one point)],
    [$B = 1$: one 16-lane chunk per call],
    [measured: #ratio-range(lanes-gain) at $B = 1$ (16 lanes ÷ 1 lane)],
    [executor policy (WP3.1 or wave 4)],
    [*Finite-only result path* (sum the virtual natively, no per-family lane export, Python assembly only for checks and observables)],
    [glue #pct(calc.min(..gated.map(p => { let x = bat(dev-c(p), top(dev-c(p))); share(x, glue(x)) })))–#pct(calc.max(..gated.map(p => { let x = bat(dev-c(p), top(dev-c(p))); share(x, glue(x)) }))) of the native-input time],
    [up to the share (largest at $2 -> 3$ with quarks)],
    [`plan_export`, executor (wave 4)],
    [*Lane-major closures* (no scatter, no second copy into the reducer's batch)],
    [scatter #pct(calc.min(..gated.map(p => { let x = bat(dev-c(p), top(dev-c(p))); share(x, stage(x, "scatter")) })))–#pct(calc.max(..gated.map(p => { let x = bat(dev-c(p), top(dev-c(p))); share(x, stage(x, "scatter")) })))],
    [up to the share],
    [executor, reducer adapter (wave 4)],
    [*AVX2 / AVX-512 kernels* (runtime selection)],
    [numerator #pct(calc.min(..gated.map(p => { let x = bat(dev-c(p), top(dev-c(p))); share(x, numerator(x)) })))–#pct(calc.max(..gated.map(p => { let x = bat(dev-c(p), top(dev-c(p))); share(x, numerator(x)) })))],
    [×1.0–1.4 on the dressing (gate G0)],
    [wave 4 (WP4.6)],
    [*NinjaRS and masters*: parallel reduction, transposed reduction, stage-2 sharing],
    [NinjaRS + masters #pct(calc.min(..gated.map(p => { let x = bat(dev-c(p), top(dev-c(p))); share(x, stage(x, "reduction")) })))–#pct(calc.max(..gated.map(p => { let x = bat(dev-c(p), top(dev-c(p))); share(x, stage(x, "reduction")) })))\;
      masters #pct(calc.min(..gated.map(p => { let x = bat(dev-c(p), top(dev-c(p))); masters(x) / stage(x, "reduction") })))–#pct(calc.max(..gated.map(p => { let x = bat(dev-c(p), top(dev-c(p))); masters(x) / stage(x, "reduction") }))) of the reduction, oneloopmaster alone #pct(calc.min(..gated.map(p => { let x = bat(dev-c(p), top(dev-c(p))); stage(x, "reduction: masters (oneloopmaster)") / stage(x, "reduction") })))–#pct(calc.max(..gated.map(p => { let x = bat(dev-c(p), top(dev-c(p))); stage(x, "reduction: masters (oneloopmaster)") / stage(x, "reduction") }))): the cache bookkeeping costs more than the integrals],
    [one thread: up to the share; threads: DESIGN §5.6],
    [NinjaRS requests (DESIGN §11.5)],
  )),
) <tab:levers>

#let ud = gproc("uux_ddxg")
#let udx = bat(dev-c(ud), top(dev-c(ud)))
#let ud-after = udx.median_seconds_per_point - glue(udx) - stage(udx, "scatter")
The failing native-input row, #gname("uux_ddxg"), takes #msec(udx.median_seconds_per_point) ms
against a limit of #msec(udx.gate.binding_limit) ms (OpenLoops
#msec(ptime(ud, "openloops")) ms × 1.30). Its glue and scatter are
#msec(glue(udx) + stage(udx, "scatter")) ms; without them it would take
#msec(ud-after) ms, #fixed(ud-after / udx.gate.binding_limit, 2) of the limit.
#let ud32 = bat(dev-c(ud), "32")
At $B = 32$ it takes #msec(ud32.median_seconds_per_point) ms: its glue grows
with the batch (#msec(glue(ud32)) ms per point at $B = 32$,
#msec(glue(udx)) ms at $B = 128$).

== Leading colour

#let lc-cell(p, lc, fc, b) = {
  let (x, y) = (bat(lc, b), bat(fc, b))
  if x == none { return table.cell(text(6.6pt, fill: ink2, style: "italic")[not timed]) }
  table.cell({
    text(8pt, weight: "bold", msec(x.median_seconds_per_point))
    h(1fr)
    if y != none { tiny[FC #msec(y.median_seconds_per_point) · #fixed(x.median_seconds_per_point / y.median_seconds_per_point, 2)] }
  })
}
#let lc-procs = g.processes.filter(p => cfg(p, "native/lc") != none or cfg(p, "python/lc") != none)
#figure(kind: table,
  caption: [*Leading colour* (LC), ms per point, same protocol as @tab:g1; in
    each cell the full-colour (FC) time of the same configuration and LC/FC.
    No provider ratio: the providers time full colour. LC uses the committed
    QCD colour continuation (`examples/loop/source_colour`).],
  tstyle(table(
    columns: (2.9cm, 0.8cm, 1fr, 1fr),
    align: left + horizon, inset: (x: 4pt, y: 2.7pt),
    stroke: (x, y) => (top: if y <= 1 { none } else if calc.rem(y - 1, 2) == 0 { 0.6pt + luma(190) } else { hair }, left: if x >= 2 and y > 0 { hair } else { none }),
    fill: thead-fill,
    table.header[Process][$B$][Integrated][Native inputs#super[dev]],
    ..lc-procs.map(p => {
      let (al, af, dl, df) = (cfg(p, "python/lc"), slice-c(p), cfg(p, "native/lc"), dev-c(p))
      let big = if top(dl) == none { top(al) } else { top(dl) }
      (
        table.cell(rowspan: 2, gname(p.key)),
        [1], lc-cell(p, al, af, "1"), lc-cell(p, dl, df, "1"),
        [#big], lc-cell(p, al, af, big), lc-cell(p, dl, df, big),
      )
    }).flatten(),
  )),
) <tab:g1lc>

LC is cheaper in the loop stage (fewer families and skeletons), but not yet
end to end: with native inputs the trees at LC cost more than at full colour
for the processes with many colour orderings
(#gname("uux_ggg"): #msec(stage(bat(cfg(gproc("uux_ggg"), "native/lc"), top(cfg(gproc("uux_ggg"), "native/lc"))), "native trees")) against
#msec(stage(bat(dev-c(gproc("uux_ggg")), top(dev-c(gproc("uux_ggg")))), "native trees")) ms per point),
and in the integrated slice the Python inputs dominate either way.

== Throughput, model recalibration and schedule M

#let rc = g.recalibration.filter(r => r.configuration == "native/full")
#figure(kind: table,
  caption: [*Kernel throughput and the design recipe* (native inputs, full
    colour, largest batch). Work: the executor's modelled complex
    multiply-adds of the chosen kernel forms per point (one lane);
    throughput: work × lanes over the dressing time (fused-factor builds
    excluded). Native loop: seeds, factors, dressing, scatter and reduction;
    outside: everything else of the call (trees, glue). Recipe: DESIGN §1.3,
    finite only, where the design has a row; measured ÷ recipe for the total
    and for the NinjaRS stage (masters included) against its model R.],
  tstyle(table(
    columns: (2.9cm, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr),
    align: (x, y) => if x == 0 { left + horizon } else { right + horizon },
    inset: (x: 3.5pt, y: 2.7pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][Work, MCMAC/pt][Dressing, ms][G CMAC/s][Native loop, ms][Outside, ms][Total, ms][Total ÷ recipe][NinjaRS ÷ R],
    ..rc.map(r => {
      let p = gproc(r.process)
      let x = bat(dev-c(p), str(r.batch))
      let w = if x.throughput == none { none } else { x.throughput.work_per_lane_per_chunk }
      let d = r.at("design", default: none)
      (
        gname(r.process),
        if w == none [—] else { sig(w / 1e6) },
        msec(stage(x, "dressing")),
        if r.kernel_cmac_per_second == none [—] else { fixed(r.kernel_cmac_per_second / 1e9, 2) },
        msec(r.total - r.outside_native_loop),
        msec(r.outside_native_loop),
        text(weight: "bold", msec(r.total)),
        if d == none { dim[no row] } else [#fixed(d.total_over_recipe.at(0), 1)–#fixed(d.total_over_recipe.at(1), 1)],
        if d == none { dim[—] } else [#fixed(d.reduction_over_model.at(0), 2)–#fixed(d.reduction_over_model.at(1), 2)],
      )
    }).flatten(),
  )),
) <tab:g1rate>

#let rates = rc.filter(r => r.kernel_cmac_per_second != none).map(r => r.kernel_cmac_per_second / 1e9)
*Recalibration.* The kernels run #fixed(calc.min(..rates), 2)–#fixed(calc.max(..rates), 2)
G complex MAC/s per core on the real plans, the rate gate G0 measured on its
synthetic programs (1.29–1.37); the dressing term of the recipe holds. The
NinjaRS stage, masters included, lands on the design's model R (measured ÷ R
#fixed(calc.min(..rc.filter(r => r.at("design", default: none) != none).map(r => r.design.reduction_over_model.at(0))), 2)–#fixed(calc.max(..rc.filter(r => r.at("design", default: none) != none).map(r => r.design.reduction_over_model.at(1))), 2),
@tab:g1rate). What the recipe misses is the *outer factor*:
it assumed trees, seeds and counterterms add 5–10 % (DESIGN §1.3), but with
the current native inputs everything outside the native loop stage is
#fixed(calc.min(..rc.map(r => r.outside_native_loop / (r.total - r.outside_native_loop))), 1)–#fixed(calc.max(..rc.map(r => r.outside_native_loop / (r.total - r.outside_native_loop))), 1)
times the loop stage. `tools/loop_v2_costmodel.py --g1` prints the full
comparison.

#let bm-row(key, acc) = {
  let p = gproc(key)
  let (b, m) = if acc == "full" { (dev-c(p), cfg(p, "native/full/M")) } else { (cfg(p, "native/lc"), cfg(p, "native/lc/M")) }
  if b == none or m == none { return () }
  (gname(key), if acc == "full" [FC] else [LC],
    ..("1", top(m)).map(s => {
      let (x, y) = (bat(b, s), bat(m, s))
      if x == none or y == none { ([—], [—], [—]) } else {
        (msec(x.median_seconds_per_point), msec(y.median_seconds_per_point),
          text(weight: "bold", fixed(y.median_seconds_per_point / x.median_seconds_per_point, 2)))
      }
    }).flatten())
}
#block(breakable: false)[#figure(kind: table,
  caption: [*Schedule B against M end to end* (native inputs, one thread),
    ms per point, pure-gluon classes, the only classes where M merges seed
    entries (DESIGN §5.6). M/B below 0.85 would adopt M (the design's 15 %
    rule with the reduction included).],
  tstyle(table(
    columns: (2.9cm, 0.9cm, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr),
    align: (x, y) => if x < 2 { left + horizon } else { right + horizon },
    inset: (x: 4pt, y: 2.7pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][Col.][B, $B = 1$][M, $B = 1$][M/B][B, largest][M, largest][M/B],
    ..(("gg_ggg", "full"), ("gg_ggg", "lc"), ("gg_gggg", "full"), ("gg_gggg", "lc")).map(((k, a)) => bm-row(k, a)).flatten(),
  )),
) <tab:g1bm>]

#let bm-ratios = (("gg_ggg", "full"), ("gg_ggg", "lc"), ("gg_gggg", "full"), ("gg_gggg", "lc")).map(((k, a)) => {
  let p = gproc(k)
  let (b, m) = if a == "full" { (dev-c(p), cfg(p, "native/full/M")) } else { (cfg(p, "native/lc"), cfg(p, "native/lc/M")) }
  if b == none or m == none { () } else {
    ("1", top(m)).map(s => bat(m, s).median_seconds_per_point / bat(b, s).median_seconds_per_point)
  }
}).flatten()
*B against M.* End to end, M/B lies between #fixed(calc.min(..bm-ratios), 2)
and #fixed(calc.max(..bm-ratios), 2) on the pure-gluon rows: M shortens the
dressing of $g g -> g g g g$, but the dressing is a minority of the time once
trees and glue are counted (@tab:g1split), so no row reaches the 0.85 that
would adopt M; with a quark line M's entries do not merge at all (M/B
1.00 ± 0.02 on one thread for every quark-line class, DESIGN §5.6).
*Decision (G1):* schedule B for every class at $n <= 6$; M stays the planned
default from $n >= 8$ and is re-measured at seven legs with the WP3.1 plans
(`measure-g1-7leg`).

#figure(kind: table,
  caption: [*Values at the timed points*: pyAmpliCol's finite part against
    each provider's production-mode value on the common stream points (the
    providers read the binary64 decimal text of the exact points), metric
    $|a - b| slash max(|a|, |b|, |B| alpha_s slash 2 pi)$; Recola's finite part converted with
    the universal double pole (it returns no poles in production). Worst
    point: the stream point with the largest deviation, evaluated again with
    one rotation and the reduction-direction check; $E$ is pyAmpliCol's
    returned relative accuracy estimate there (DESIGN §10.4), to be set
    against the deviation. Campaign: the first three points against the
    committed references (`tests/fixtures/loop/required`, native inputs),
    fixture metric and tolerance.],
  tstyle(table(
    columns: (2.9cm, 0.9cm, 1fr, 1fr, 1fr, 1.25fr, 1.25fr),
    align: (x, y) => if x == 0 { left + horizon } else { right + horizon },
    inset: (x: 4pt, y: 2.7pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][Points][vs MadLoop][vs Recola][vs OpenLoops][Worst point: $E$][Campaign],
    ..g.processes.map(p => {
      let c = dev-c(p)
      let v = if c == none { none } else { c.values_vs_providers }
      let cell(n) = if v == none or v.at(n, default: none) == none [—] else { sci(v.at(n).max_finite_deviation) }
      let pts = if v == none or v.len() == 0 { 0 } else { calc.max(..v.values().map(x => x.points)) }
      let acc = if c == none { none } else { c.accuracy_check }
      let worst = if v == none or v.len() == 0 { none } else { v.values().sorted(key: x => x.max_finite_deviation).last() }
      let st = if worst == none { none } else { p.stability.find(r => r.index == worst.worst_point) }
      (gname(p.key), str(pts), cell("madloop"), cell("recola"), cell("openloops"),
        if st == none { dim[—] } else [#tiny[point #st.index:] #sci(st.estimate)],
        if acc == none { dim[no reference] } else [#sci(acc.max_error) #if not acc.passed [#linebreak() #tiny[above #sci(acc.tolerance)]]])
    }).flatten(),
  )),
) <tab:g1values>

Every deviation above $10^(-9)$ lies at a point whose returned estimate $E$
exceeds it: binary64 losses at ill-conditioned points, which the stability
checks flag and DoubleFloat resolves (@tab:validation), not disagreements
between the codes. The deviations near $10^(-10)$ against Recola alone are
Recola's own integral accuracy (COLLIER's default target $10^(-8)$, HANDOFF
§7); MadLoop and OpenLoops agree with pyAmpliCol to better than $10^(-11)$ on those
points.

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
        if r.label.contains("controls") { text(8.4pt, font: "Libertinus Serif")[$2 -> 2$, $2 -> 3$ controls] } else { plabel(r) },
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
  caption: [*Provider references for the seven-leg gates*, s per point, one
    pinned core, production mode (finite part; OpenLoops `truepoles 0` with
    I-operator poles, Recola without IR poles, MadLoop production build),
    measured on 2026-10-20 for the design (DESIGN §1.3, Table 1b); inferred
    values of that table are omitted. G1 re-measures them with the seven-leg
    rows (`measure-g1-7leg`); the $2 -> 3$ and $2 -> 4$ references are in
    @tab:g1. Threshold: the largest pyAmpliCol finite-only time that would
    pass, 1.3× the fastest matched Recola/OpenLoops time where it is below
    MadLoop's.],
  tstyle(table(
    columns: (3.2cm, 1fr, 1fr, 1fr, 1.9cm),
    align: (x, y) => if x == 0 { left + horizon } else { right + horizon },
    inset: (x: 4pt, y: 3.1pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][OpenLoops][Recola][MadLoop][Threshold],
    ..ms.gate_references.rows.map(r => (plabel(r), r.openloops, r.recola, r.madloop, text(weight: "bold", r.threshold))).flatten(),
  )),
) <tab:gateref>

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
    pinned core, idle at launch, of the shared host; 10 frozen points per channel, mean (spread ≤ 2 %); the
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
// CPU-time bound of the five bare-loop evaluations: the job's user + system
// time less one busy core over generation and over the export with trees.
#let nb-cpu = nb.user_s + nb.system_s
#let nb-eval-wall = nb.seconds.sum()
#let nb-cpu-eval = nb-cpu - nb.generate_s - nb.export_with_trees_s
#let nb-cores = nb-cpu-eval / nb-eval-wall
#let nb-cpu-pt = nb-cpu-eval / nb.seconds.len()
#box-note(fill: warm)[
  #set par(justify: false)
  These are #flag[development] measurements on the branches named, on the
  shared host. Generation and the counterterm program ran in one thread; the
  bare-loop job's thread count was not recorded, so its wall times are not
  per-core timings (@tab:sevendev). They are not part of the acceptance campaign and not a like-for-like speed
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
    averaged #nb.cpu_percent % CPU. Its #group(int(calc.round(nb-cpu))) CPU-s
    (user + system), less one core over generation (#sig(nb.generate_s) s) and
    export with trees (#sig(nb.export_with_trees_s) s), leave at most
    #sig(nb-cpu-eval) CPU-s for the #sig(nb-eval-wall) s of evaluations: up to
    #fixed(nb-cores, 1) busy cores on average and up to #sig(nb-cpu-pt) CPU-s per
    point, so the per-core comparison with NJet is undetermined. Counts of the
    generated slice:
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
    [Binary64; per point the point and one rotation (two evaluations); no counterterms, no $R_2$; thread count not recorded (up to #fixed(nb-cores, 1) cores, ≤ #sig(nb-cpu-pt) CPU-s per point)],
    text(weight: "bold")[#sig(calc.min(..nb.seconds))–#sig(calc.max(..nb.seconds)) s/pt], [#text(weight: "bold")[#fixed(kib-gib(nb.max_rss_kib), 1) GiB] #linebreak() #tiny[whole job]],
  )),
) <tab:sevendev>

On the same host (@tab:njet) NJet takes #num(ms.njet.rows.last().n312_std)~s
per point for its standard sum and #num(ms.njet.rows.last().n312_ds)~s for its
de-symmetrised sum, two evaluations each, on one pinned core, idle at launch,
of the shared host.
The native path's #sig(calc.min(..nb.seconds))–#sig(calc.max(..nb.seconds))~s
per point (also two evaluations) are wall times of a multi-threaded job: its CPU
accounting allows up to ≈#fixed(nb-cores, 1) busy cores, ≈#sig(nb-cpu-pt)~CPU-s
per point, during the evaluations, which is above NJet's
#num(ms.njet.rows.last().n312_std)~s. Whether the native bare path is faster
than NJet's standard sum per core is therefore undetermined until a one-thread
run exists. The comparison is not like-for-like either: counterterms and $R_2$
are missing on the pyAmpliCol side, its job ran unpinned and multi-threaded on
the same shared host, and the de-symmetrised sum is not a point value. Generation fits
addendum H's budget (O(hours), below 150 GB). MASTER_PLAN quotes the same two
peaks as KiB/10⁶ ("#fixed(g1.max_rss_kib / 1e6, 1) GB",
"#fixed(ctp.max_rss_kib / 1e6, 1) GB"); of the run records, the counterterm
record prints KiB/10⁶ and the generation record GiB.

== Validation without a matched provider

#let fv = sg.first_virtual
#let nv = ms.njet_validation
#let ux = sg.uux_ggggg_vs_providers.max_relative_deviation
#figure(kind: table,
  caption: [*Checks of the seven-leg QCD results*, #flag[development]
    measurements on `work/v2-generation-scale`, not part of the acceptance
    campaign, except the Ward row (WP2.5 on `loop`); binary64, deviation metric
    of @tab:validation. NJet values: fixture `gg_ggggg_njet.json` (NJet 3.1.2
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
    align: left + horizon, inset: (x: 4pt, y: 2.8pt), stroke: tstroke, fill: thead-fill,
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
    [Top-free full virtual against NJet at lower multiplicity],
    [#nv.topfree.lower.map(l => [#math-label(l.label): #l.value]).join([; ]) (`test_loop_v2_topfree.py`)],
    [passed],
    [$u overline(u) -> g g g g g$ full virtual against MadLoop and Recola, 3 points],
    [MadLoop ≤ #sci(calc.max(..ux.madloop.values())), Recola ≤ #sci(calc.max(..ux.recola.values())) (finite ≤ #sci(ux.recola.finite)); the providers agree to 6.2×10⁻¹⁰],
    [passed],
    [Ward identity, one gluon's $epsilon -> p$, at seven gluons],
    [asymmetric Ward mode of WP2.5 (loop side only, bare + UV + $R_2$); passes on $g g -> g g$ and $u overline(u) -> g g g$ (`test_loop_v2_observables.py`)],
    text(fill: rgb("#8a4b08"), weight: "semibold")[not yet run at seven gluons (addendum H)],
  )),
) <tab:sevencheck>

#box-note(breakable: false)[
  #set par(justify: false)
  *First $g g -> g g g g g$ virtual* #flag[development] `work/v2-generation-scale`,
  not part of the acceptance campaign (full colour, Born $alpha_s^5$, loop_sm with
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
  ([Full, NLC and LC colour], "supported", [Exact seed tables in $N_c$; LC/NLC by generated classes and truncated cells. LC is cheaper in the loop stage but not yet end to end at large batches (its native trees cost more, @tab:g1lc), nor to generate at seven legs.]),
  ([Colour and spin correlations], "supported", [Directed colour histories at LC/NLC/FC, spin sources, resolved helicities, flavour aliases, Ward sources (WP2.5). Seven-leg directed LC/NLC tables need the Rust seed tables (WP3.1).]),
  ([Per-order partials], "supported", [Every squared coupling order at tree level and at one loop, mixed Born orders, per-correction loop orders.]),
  ([Poles at runtime], "supported", [`poles = "all" | "none" | "uv" | "ir" | "split"` (WP2.10, on `loop` since 24 October): finite-only mode with the finite part bitwise unchanged and the pole work skipped; `"uv"` and `"ir"` with the user's semantics of 23 October. The UV residue comes from an interim local module until the NinjaRS re-pin; a `"uv"` estimate needs a rotation check.]),
  ([Stability estimates], "supported", [Rotation checks (any number, 0 = estimate absent), reduction direction, exact rescaling, in any combination; no automatic escalation (WP2.3).]),
  ([Precision carriers], "supported", [Binary64, DoubleFloat, arbitrary precision and exact rationals in the native executor; DD/AP point inputs are formed in Python Decimal until WP3.1.]),
  ([Native executor, schedules], "supported", [Rust, 16 lanes (also for a one-point call, a G1 lever), threads; schedule B for every class at $n <= 6$ (G1 decision, @tab:g1bm), M native, F as oracle. The NinjaRS reduction runs serially. Development report: stage times, modelled kernel work, master-integral time.]),
  ([Plan v4 artifacts and API], "partial", [Published and loaded through Python, TOML and CLI; relocation to another path tested on the same host and CPU. Loading regenerates the process (the `LoopSlice`) in Python and checks the plan digest, which addendum G forbids for prepared artifacts; WP3.1 removes it. The Rust/C/C++/Fortran SDK refuses v4 until WP3.1.]),
  ([Counterterms (model UV, $R_2$)], "partial", [Counterterms from the tree recursion are the default route on `loop` since 24 October (WP2.2, a18b7599; constant-argument fix 59badc7a), site closure the test oracle; both still admit sites by the witness table. Production rule (addendum J): plain tree vertices inserted exactly once, admitted by coupling orders and `particle_veto`, no loop matching; `ct-simplify` removes the matching. Per point they are formed in Python on the slice, natively on the WP3.1 branch.]),
  ([Direct $R_2$], "deferred", [A bonus by the user's rule; bounded controls only.]),
  ([Electroweak, complex mass], "open", [Tree EW lanes fixed, the Dirac–Weyl class refused; loop EW, Goldstones and CMS are WP3.2.]),
  ([Required set], "progress", [On the WP3.1 branch seven of eight generate and six agree with their provider references in all coefficients (@tab:validation); $g g -> g g g g g$ is validated in Born and poles; the EW target is not started.]),
  ([Performance gates], "progress", [G1 measured (@g1): the integrated slice fails every $2 -> 3$ and $2 -> 4$ gate (Python per-point inputs); with the WP3.1 native inputs six of seven pass at the largest batch, $u overline(u) -> d overline(d) g$ fails by 1.3×, $B = 1$ needs lane adaptation. Seven legs: `measure-g1-7leg`.]),
  ([$g g -> 6g$], "deferred", [No $2 -> 6$ work until the $2 -> 5$ plan is complete (user, 23 October).]),
)
#figure(kind: table,
  caption: [*Capability matrix* of the v2 engine on `loop` at #ms.engine_revision, with branch work marked.],
  tstyle(table(
    columns: (3.5cm, 1.6cm, 1fr), align: (x, y) => if x == 1 { center + horizon } else { left + horizon },
    inset: (x: 4.5pt, y: 2.6pt), stroke: tstroke, fill: thead-fill,
    table.header[Feature][Status][Boundary],
    ..caps.map(((f, s, b)) => (text(weight: "semibold", f), badge(s), b)).flatten(),
  )),
) <tab:caps>

// ========================================================= ARCHITECTURE ==
= Architecture of the v2 engine <arch>

== The computed quantity

#block(breakable: false)[
For Born order $a$, loop order $b$ and squared coupling order $s = a + b$,
$
  V_(s,k) = cal(N) sum_(a+b=s) 2 op("Re")[B_a^dagger G_(B L) L_(b,k)], quad k in {0, -1, -2},
  quad V = C_epsilon (V_0 + V_(-1) / epsilon + V_(-2) / epsilon^2), quad C_epsilon = (4 pi)^epsilon / Gamma(1 - epsilon),
$
]
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
  block(width: 100%, height: 1.2cm, fill: f, stroke: s, inset: (x: 3pt, y: 3pt), radius: 2pt, align(center + horizon, {
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
    stage-box([Blocks, Born, CT scalars], [Python per point; native on WP3.1 (G1)], "py"), arr,
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
    ..("born", "pentagon", "box").map(n => box(height: 2.8cm, image("figures/" + n + ".svg", height: 100%, fit: "contain")))),
) <fig:graphs>

*Loop numerators and schedules.* An open-loop recursion dresses skeletons one
segment at a time with polynomial-valued objects,
$O' = O dot Y + "raise"(O dot Z_mu, q^mu)$, in the NinjaRS monomial layout
($binom(r + 4, 4)$ coefficients at rank $r$, no rank cap). The seed is the
colour-summed Born interference, and each block's helicities are summed as it
is attached. One generator feeds three schedules (@tab:schedules).

#block(breakable: false)[#figure(kind: table,
  caption: [*Three schedules on one generator* (DESIGN §2.2, §5.6).],
  tstyle(table(
    columns: (2.2cm, 1fr, 1fr, 1fr),
    align: left + horizon, inset: (x: 4pt, y: 3pt), stroke: tstroke, fill: thead-fill,
    table.header[][F: forward][B: suffix trie (default)][M: merged, primitive-seeded],
    [Born weighting], [at closure], [at the leaves (one seed per skeleton class)], [at the cut, one seed per colour ordering],
    [Shared], [prefixes across families], [all prefixes with equal family and remainder], [prefixes across families and compositions],
    [Colour certificate], [none needed], [none needed], [certified classes: adjoint rings, traces, quark rings],
    [Role], [oracle], [default; generic fallback], [pure-gluon classes; $n >= 8$ default],
  )),
) <tab:schedules>]

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

*Counterterms.* The model's UV and $R_2$ vertices, two-point ones included,
are ordinary vertices of the tree recursion, and each contribution contains
exactly one of them; external field factors are separate sources. Admission
is the requested coupling orders, the exactly-once constraint and a public
`particle_veto`: a coupling term whose loop particles include a vetoed
particle is dropped, and a vetoed particle is removed from every tree vertex,
loop line and propagator of the generation, so loops and counterterms stay
consistent. Nothing is matched to the loop (user, 23 October; addendum J).
On `loop` (since 24 October) the counterterms come from the WP2.2 recursion
(one counterterm order in the tree recursion, the default route, whose
$g g -> g g g g g$ program leaves no rule to site closure, @tab:sevendev); it
still admits counterterm sites by a witness table of divergent loop routings
with a power-counting completeness check, as the site closure (the test
oracle) does. The package `ct-simplify` removes the witness table and the matching from
production and adds `particle_veto`, which replaces the internal top-free
switch of @tab:sevencheck (then `particle_veto = [t]`); site closure and the
witness machinery remain only as test oracles.

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
    The required set ($n <= 7$) is far below the crossover of schedule B with
    the unitarity class ($n approx 30$–$50$); schedule M is planned as the
    default from $n >= 8$.],
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
  - *Status, in-flight work, decisions:* `data/milestone.json`, from the
    `Integrate …` merges of #ms.engine_revision since #ms.previous_loop;
    `workspace/reports/engine-v2/slice-status.md` (integration blocks,
    DECISIONS 2026-10-23); `HANDOFF_22_10_2026.md` §0–§3; MASTER_PLAN
    2026-10-23 entries; REQUIREMENTS_ADDENDUM A, D, F, G, H, I, J; DESIGN §5.7
    (G1), §6.1, §12.4; the 24 October push (59badc7a, gate in slice-status.md).
  - *@tab:provgen:* provider columns HANDOFF §0.1 (addendum F); pyAmpliCol
    column DESIGN WP3.1 third increment "Generation per process" on
    `work/v2-generation-scale` (201efa8b). *@tab:validation:* DESIGN WP3.1
    first to fourth increment, same branch (records
    `workspace/tmp/generation-scale/runs/`); the $g g -> g g g g$ row from
    `cmp_gg_gggg.json`, `cmp_gg_gggg_p1_stab.json` and `cmp_gg_gggg_p1_dd.json`
    there. *@tab:gateref:* DESIGN §1.3 Table 1b. *Conventions:*
    #link("https://cp3.irmp.ucl.ac.be/projects/madgraph/wiki/MadLoopStandaloneLibrary")[MadLoop standalone],
    #link("https://arxiv.org/abs/1605.01090")[Recola],
    #link("https://arxiv.org/abs/1907.13071")[OpenLoops 2].
  - *@g1 (@tab:g1 to @tab:g1values):* `data/g1.json`, written by
    `python -m tools.loop_benchmark gate` (README and docstrings of
    `tools/loop_benchmark`); streams `tools/loop_benchmark/streams/`; records
    and logs `workspace/tmp/measure-g1/{runs,logs}/`; recalibration
    `tools/loop_v2_costmodel.py --g1 data/g1.json`; builds
    `loop-native-measure-g1-0f87abd2` (slice + timers) and
    `loop-native-measure-g1-genscale-39824f9b` (889af02c + timers), release
    with one codegen unit and thin LTO; schedule M at seven legs: DESIGN §5.6.
  - *@tab:njet* and NJet prose: `workspace/reports/engine-v2/njet-benchmark.md`
    §2, §5, §6 (raw `workspace/reference/runs/njet/timing/`);
    #link("https://arxiv.org/abs/1209.0100")[NJet, arXiv:1209.0100] Table 5.
  - *@tab:sevendev, @tab:sevencheck, first virtual:* `data/measured.json`
    (`scripts/collect_milestone.py <workspace>` from the records in
    `workspace/tmp/generation-scale/runs/` and `workspace/tmp/ct-recursion/s4/`);
    NJet deviations: njet-benchmark.md §5.3 and `gg_ggggg_njet.json`; top-free
    values: DESIGN WP3.1 and `test_loop_v2_topfree.py`. Memory in GiB = KiB/2²⁰.
  - *@tab:caps, @arch:* `docs/development/loop_v2/DESIGN.md` §1–§3, §5.5,
    §5.6, §6, §10, §12, REQUIREMENTS_ADDENDUM J (counterterm rule) and the
    integration records above.
  - *@tab:history:* `data/measurements.json`, `data/provider-cold.json` and
    `data/legacy-labels.json` (legacy snapshot of 2026-10-18, unchanged);
    `data/colour-measurements.json` stays for the DESIGN citations; removed
    data are in the git history (README).
]
