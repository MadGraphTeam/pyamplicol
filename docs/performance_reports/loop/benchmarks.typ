// pyAmpliCol one-loop report, summary first. Table 1 and Figure 1 render
// data/summary.json (scripts/build_summary.py, from the files below); the
// other tables read data/*.json directly (g1.json: the G1 campaign,
// tools/loop_benchmark; milestone.json: registry with sources; measured.json:
// written by scripts/collect_milestone.py from the run records). Numbers
// quoted in prose name their source in the last section. Build from this
// directory:
//   typst compile benchmarks.typ benchmarks.pdf
#let ms = json("data/milestone.json")
#let meas = json("data/measured.json")
#let g = json("data/g1.json")
#let sg = meas.seven_gluon

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
    [pyAmpliCol at one loop #h(1fr) milestone #ms.date · engine #ms.engine_revision on `loop` · G1 timed at #g.slice_revision (`loop`)#if g.at("native_revision", default: none) != none [ and #g.native_revision (development)]]
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
// Run times (user rule (b) of 2026-10-24 ~22:35): diverging green (faster)
// -> white (×1) -> red (slower). Poles #1a9e77 / #d73027: ΔE 9.8 under
// deuteranopia (dataviz validator, light surface); every coloured cell also
// prints its multiplier, so colour never carries the value alone.
#let fast-green = rgb("#1a9e77")
#let slow-red = rgb("#d73027")
#let palette = gradient.linear(fast-green, rgb("#c4e6d9"), white, rgb("#fbd0c3"), slow-red)
#let ratio-fill(r) = if r == none { none } else { palette.sample(calc.clamp(0.5 + calc.log(r, base: 2) / 8, 0, 1) * 100%) }

// Stage colours of the per-point split (Table 1 bars, the stage-split table):
// categorical slots 1-5 and 7 of the dataviz reference palette, in stage
// order (validated for adjacent pairs, light surface; the stage table is the
// table view the contrast rule asks for). The seventh, neutral grey, is the
// untimed rest of the call (no stage: a build without per-point input timers).
#let seg-colours = (rgb("#2a78d6"), rgb("#eb6834"), rgb("#1baf7a"), rgb("#eda100"), rgb("#e87ba4"), rgb("#6250d6"), luma(170))

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
#let box-note(fill: pale, stroke: none, breakable: true, body) = block(width: 100%, fill: fill, stroke: stroke, breakable: breakable, inset: 9pt, radius: 3pt, text(9pt, body))
#let flag(body) = box(fill: warm, inset: (x: 3pt, y: 1.5pt), radius: 2pt, text(6.6pt, weight: "bold", fill: rgb("#8a4b08"), body))

// ===================================================================== G1 ==
// Gate G1 (WP2.7): data/g1.json, written by `python -m tools.loop_benchmark
// gate` from the pyAmpliCol, provider and stability records of the campaign.
#let gproc(key) = g.processes.find(p => p.key == key)
// The generated process text ("u u~ > e- e+ g g") as math.
#let tok(t) = if t == ">" { "->" } else if t.ends-with("~") { "overline(" + t.slice(0, -1) + ")" } else if t.ends-with("-") { t.slice(0, -1) + "^(-)" } else if t.ends-with("+") { t.slice(0, -1) + "^(+)" } else { t }
#let gname(key) = text(8.6pt, font: "Libertinus Serif", math-label(gproc(key).label.split(" ").map(tok).join(" ")))
#let cfg(p, name) = p.pyamplicol.at(name, default: none)
#let refused(c) = c != none and c.at("generation_error", default: none) != none
#let sizes(c) = if c == none { () } else { c.batches.keys().map(int).sorted() }
#let top(c) = { let s = sizes(c); if s.len() == 0 { none } else { str(s.last()) } }
#let bat(c, b) = if c == none or b == none { none } else { c.batches.at(b, default: none) }
#let msec(s) = box(sig(s * 1000))
// Multipliers: two significant figures below 10 (×0.27, ×0.045), integers above.
#let mult2(r) = [×#if r >= 10 { fixed(r, 0) } else if r >= 1 { fixed(r, 1) } else { fixed(r, 1 - calc.floor(calc.log(r, base: 10))) }]
#let pnames = ("madloop", "recola", "openloops")
#let prov(p, n) = if p.providers == none { none } else { p.providers.at(n, default: none) }
// The gate statistic: the provider's median per point (gate.py).
#let ptime(p, n) = { let r = prov(p, n); if r == none { none } else { r.at("median_seconds_per_point", default: none) } }
#let fastest-p(p) = {
  let ts = pnames.map(n => (n: n, t: ptime(p, n))).filter(x => x.t != none)
  if ts.len() == 0 { none } else { ts.sorted(key: x => x.t).first() }
}
#let stage(x, name) = x.stages_per_point.at(name, default: 0.0)
#let python-inputs(x) = ("python trees", "python counterterm program", "python scalars",
  "python Born and counterterm components").map(n => stage(x, n)).sum()
// A record without any per-point input timer (the build on `loop` before
// lc-perf, 88657260: the native trees timer was a scratch commit of the
// development campaign; since lc-perf the executor reports "trees") leaves
// its native trees, Born and counterterm inputs in "other": the untimed rest
// of the call, kept out of the glue and never attributed to a stage (as
// scripts/build_summary.py does for Table 1).
#let input-timers = ("python trees", "python counterterm program", "python scalars",
  "python Born and counterterm components", "native trees")
#let inputs-timed(x) = input-timers.any(n => n in x.stages_per_point)
#let untimed(x) = if inputs-timed(x) { 0.0 } else { stage(x, "other") }
#let glue(x) = ("python point parameters", "input conversion", "assembly", "other").map(n => stage(x, n)).sum() - untimed(x)
#let numerator(x) = ("seeds", "factors", "dressing").map(n => stage(x, n)).sum()
#let masters(x) = stage(x, "reduction: masters")
#let ninjars(x) = stage(x, "reduction") - masters(x)
#let verdict(x) = if x == none { none } else { x.gate }
// User decisions that replace a measured open verdict (milestone.json
// gate_decisions; Table 1 reads the same decisions through summary.json).
#let decision(p, b, gt) = if gt == none or gt.status != "inconclusive" { none } else {
  ms.gate_decisions.decisions.find(d => d.process == p.key and d.batch == b and d.measured == gt.status)
}
#let amber = rgb("#8a4b08")
#let pass-ink = rgb("#0f7356")
#let fail-ink = rgb("#b2182b")
#let rev(c) = if c == none { none } else { c.revision.slice(0, 8) }
// The configurations of the G1 details: native/full is the engine on `loop`
// (integrated, native per-point inputs: g.slice_revision; its earlier runs
// are G-int's at 4e9b5a9e and the development campaign's of 39824f9b);
// python/full the engine before G-int with Python per-point inputs
// (history, its own revision); native/full/L1 and the schedule-M runs the
// development campaign of 39824f9b (history, not repeated).
#let py-c(p) = cfg(p, "python/full")
#let nat-c(p) = cfg(p, "native/full")
#let l1-c(p) = cfg(p, "native/full/L1")
#let gated = g.processes.filter(p => p.gated)
#let big = "128"
// The user's gate rule (milestone.json gate_decisions.threshold_rule,
// 2026-10-24 ~22:35; Table 1 reads it through summary.json): a process whose
// batched time per point is below 5 ms has no blocking gate; its ratio and
// band stay as measured, at every batch size of the configuration. The
// batched time is the configuration's own at its largest batch above 1; a
// configuration timed at B = 1 only (the one-lane runs) takes the
// configuration on loop's. The rule takes precedence over a decision.
#let thr-rule = ms.gate_decisions.threshold_rule
#let batched-of(c) = if c == none or refused(c) { none } else {
  let s = sizes(c).filter(n => n > 1)
  if s.len() == 0 { none } else { bat(c, str(s.last())).median_seconds_per_point }
}
#let batched-time(p, c) = { let t = batched-of(c); if t != none { t } else { batched-of(nat-c(p)) } }
#let ungated(p, c) = p.gated and { let t = batched-time(p, c); t != none and t < thr-rule.below_seconds_per_point }
#let eff-status(p, c, b, gt) = if gt == none { none } else if "ratio_to_binding_limit" in gt and ungated(p, c) { "not gated" } else { let d = decision(p, b, gt); if d != none { d.verdict } else { gt.status } }
#let gate-word(p, c, b, gt) = if gt == none [—] else if eff-status(p, c, b, gt) == "not gated" {
  text(fill: ink2, weight: "bold")[not gated] + [ #fixed(gt.ratio_to_binding_limit, 2)]
} else if decision(p, b, gt) != none {
  text(fill: pass-ink, weight: "bold")[#decision(p, b, gt).verdict‡] + [ #fixed(gt.ratio_to_binding_limit, 2)]
} else if gt.status == "pass" {
  text(fill: pass-ink, weight: "bold")[pass] + [ #fixed(gt.ratio_to_binding_limit, 2)]
} else if gt.status == "fail" {
  text(fill: fail-ink, weight: "bold")[fail] + [ #mult2(gt.ratio_to_binding_limit)]
} else if gt.status == "inconclusive" {
  text(fill: amber, weight: "bold")[open] + [ #fixed(gt.ratio_to_binding_limit, 2)]
} else { text(fill: ink2, gt.status) }
// Revisions of the history configurations, from their own records.
// (Timed configurations only: a refusal recorded at another revision is not one.)
#let revs-of(f) = g.processes.map(f).filter(c => c != none and not refused(c)).map(rev).dedup()
#let builds-of(f) = g.processes.map(f).filter(c => c != none and not refused(c)).map(c => c.native.directory).dedup()
#let py-revs = revs-of(py-c)
#let l1-revs = revs-of(l1-c)
#let rev-list(rs) = rs.map(raw).join([, ])
// An earlier run of a configuration (g1.json earlier_runs, oldest first):
// the newest that timed batch b, with its revision; none if no earlier run
// did. The integrated configuration's earlier runs are the development
// campaign's (39824f9b) and G-int's (4e9b5a9e), whose binary64 values equal
// this campaign's to rounding level (g1.json values_note), and, for a single
// repeat, its own first run.
#let earlier-bat(c, b) = if c == none { none } else {
  let e = c.at("earlier_runs", default: ()).filter(r => b in r.batches)
  if e.len() == 0 { none } else { (rev: e.last().revision.slice(0, 8), x: e.last().batches.at(b)) }
}
// The first run of a single repeat: an earlier run at the configuration's own revision.
#let first-run(c) = if c == none { none } else {
  let e = c.at("earlier_runs", default: ()).filter(r => r.revision == c.revision)
  if e.len() == 0 { none } else { e.last() }
}

#let ratio-range(xs) = if xs.len() == 0 [—] else { let s = xs.sorted(); if s.len() == 1 [#mult2(s.first())] else [#mult2(s.first())–#fixed(s.last(), if s.last() >= 10 { 0 } else { 1 })] }
#let lim(p, c, b) = { let x = bat(c, b); if x == none or "ratio_to_binding_limit" not in x.gate { none } else { x.gate.ratio_to_binding_limit } }
#let status(p, c, b) = { let x = bat(c, b); if x == none { none } else { eff-status(p, c, b, x.gate) } }
#let py-timed = gated.filter(p => py-c(p) != none and not refused(py-c(p)))
#let py-refused = gated.filter(p => refused(py-c(p)))
// The Python-input rows timed in batches (B = 128) and those timed at B = 1 only.
#let py-batched = py-timed.filter(p => bat(py-c(p), big) != none)
#let py-one-only = py-timed.filter(p => top(py-c(p)) == "1")
#let py-big = py-batched.map(p => lim(p, py-c(p), big)).filter(r => r != none)
#let py-one-only-lim = py-one-only.map(p => lim(p, py-c(p), "1")).filter(r => r != none)
#let py-one = py-timed.map(p => lim(p, py-c(p), "1")).filter(r => r != none)
#let nat-at(c-of, b, s) = gated.filter(p => status(p, c-of(p), b) == s)
#let nat-pass = nat-at(nat-c, big, "pass")
#let nat-fail = nat-at(nat-c, big, "fail")
#let nat-open = nat-at(nat-c, big, "inconclusive")
#let nat-decided = gated.filter(p => { let x = bat(nat-c(p), big); x != none and not ungated(p, nat-c(p)) and decision(p, big, x.gate) != none })
// Below 5 ms per point on loop: no blocking gate (user rule); the gated rest.
#let nat-ungated = gated.filter(p => ungated(p, nat-c(p)))
#let nat-gated = gated.filter(p => not ungated(p, nat-c(p)))
#let ungated-text(ps) = ps.map(p => [#gname(p.key) #msec(bat(nat-c(p), big).median_seconds_per_point) ms (#fixed(lim(p, nat-c(p), big), 2) of its limit)]).join([, ], last: [ and ])
#let decided-text(ps) = ps.map(p => { let x = bat(nat-c(p), big).gate; let (lo, hi) = x.band_to_binding_limit; [#gname(p.key) by #decision(p, big, x).label (#fixed(x.ratio_to_binding_limit, 2) of its limit, band #fixed(lo, 2)–#fixed(hi, 2))] }).join([, ])
#let l1-pass = nat-at(l1-c, "1", "pass")
#let one-pass = nat-at(nat-c, "1", "pass")
#let share(x, v) = v / x.median_seconds_per_point
#let pct(v) = [#fixed(100 * v, 0)~%]
// A range of shares that never breaks across lines.
#let pct-range(xs) = box[#pct(calc.min(..xs))–#pct(calc.max(..xs))]
// Python per-point inputs' share of the Python-input time at B = 128: the
// "inputs" stage group of Table 1's bars and of the stage-split table's
// "Trees, Born, CT" column (input conversion is glue there and here).
#let inputs-share = py-batched.map(p => { let x = bat(py-c(p), big); share(x, python-inputs(x)) })
// The native trees' share (Born and counterterm inputs included): the
// executor's trees timer (since lc-perf, 88657260), or the untimed rest of a
// build without it (an upper bound: the rest of the call is in it too).
#let trees-share = gated.map(p => { let x = bat(nat-c(p), top(nat-c(p))); if x == none { none } else { (p: p, s: share(x, if inputs-timed(x) { stage(x, "native trees") } else { untimed(x) })) } }).filter(v => v != none)
#let trees-timed = gated.all(p => { let x = bat(nat-c(p), top(nat-c(p))); x == none or inputs-timed(x) })
// Python over native inputs at equal batch size.
#let speedup-at(b) = py-timed.map(p => { let (a, d) = (bat(py-c(p), b), bat(nat-c(p), b)); if a == none or d == none { none } else { a.median_seconds_per_point / d.median_seconds_per_point } }).filter(v => v != none)
// 16 lanes (integrated) over one lane (39824f9b's runs) at B = 1.
#let lanes-gain = gated.map(p => { let (a, b) = (bat(nat-c(p), "1"), bat(l1-c(p), "1")); if a == none or b == none { none } else { a.median_seconds_per_point / b.median_seconds_per_point } }).filter(v => v != none)
#let names(ps) = if ps.len() == 0 [none] else { ps.map(p => gname(p.key)).join([, ], last: [ and ]) }
#let host-spread = g.host_provider_spread
#let block-unc = gated.map(p => { let x = bat(nat-c(p), big); if x == none { none } else { x.uncertainty } }).filter(v => v != none)
// Providers whose time comes from one run (uncertainty assumed).
#let single-runs = g.processes.map(p => p.provider_uncertainty.pairs().filter(((n, u)) => u.assumed).map(((n, u)) => (p: p, n: n))).flatten()
#let pshort(n) = (madloop: "MadLoop", recola: "Recola", openloops: "OpenLoops").at(n)
// The cores of the integrated configuration's runs and of the provider records.
#let nat-cores = g.processes.map(p => nat-c(p)).filter(c => c != none and c.host_cpus != none).map(c => c.host_cpus).flatten().dedup().sorted()
#let prov-cores = g.processes.map(p => pnames.map(n => prov(p, n)).filter(r => r != none and r.at("cpu", default: none) != none and "median_seconds_per_point" in r).map(r => r.cpu)).flatten().dedup().sorted()
#let core-span(cs) = if cs.len() == 0 [—] else [#cs.first()–#cs.last()]
#let short-points = g.processes.map(p => pnames.filter(n => { let r = prov(p, n); r != none and r.at("points", default: 16) < 16 }).map(n => (p: p, n: n, k: prov(p, n).points))).flatten()
#let pairs-text(xs) = xs.map(x => [#pshort(x.n) #gname(x.p.key)]).join([, ], last: [ and ])

// ============================================================== TABLE 1 ==
// Table 1 renders data/summary.json (scripts/build_summary.py) as is: every
// value, ratio and verdict comes from there; this code only formats them and
// maps a ratio to a colour.
#let S = json("data/summary.json")
#let sm = S.meta
#let neutral = luma(243)
#let dur(s) = if s == none [—] else if s < 1 [#sig(s * 1000)~ms] else if s < 600 [#sig(s)~s] else if s < 10800 [#fixed(s / 60, 1)~min] else [#fixed(s / 3600, 1)~h]
// Peak memory: two decimals below 10 GiB, one above; never broken.
#let gib(x) = box[#fixed(x, if x >= 10 { 1 } else { 2 })~GiB]
// Compact scientific notation for deviations: 7.7e−13.
#let esci(x) = {
  if x == none or x == 0 { return [—] }
  let e = calc.floor(calc.log(calc.abs(x), base: 10))
  let m = x / calc.pow(10.0, e)
  if calc.round(m, digits: 1) >= 10 { m = m / 10; e += 1 }
  [#fixed(m, 1)e#str(e).replace("-", "−")]
}
#let dev-tag = box(fill: warm, stroke: 0.3pt + rgb("#d9a066"), inset: (x: 1.6pt, y: 0.7pt), radius: 1.5pt, baseline: 0.6pt, text(5.2pt, weight: "bold", stretch: 100%, fill: amber)[DEV])
#let chip-style = (pass: (rgb("#e1f2ea"), pass-ink), fail: (rgb("#f9e0da"), fail-ink), open: (rgb("#fdf0dc"), amber), (thr-rule.verdict): (luma(240), luma(90)))
// ‡: a verdict set by a user decision (data/milestone.json gate_decisions);
// "<5 ms: not gated": the user's gate rule (gate_decisions.threshold_rule).
// The ratio is always the measured one.
#let gate-chip(g) = {
  let (f, c) = chip-style.at(g.status)
  let word = if g.status == thr-rule.verdict { thr-rule.short } else { g.status }
  box(fill: f, stroke: 0.4pt + c, inset: (x: 2pt, y: 0.8pt), radius: 1.5pt, baseline: 0.8pt,
    text(5.9pt, fill: c, weight: "bold")[#word#if "decision" in g [‡] #mult2(g.ratio_to_limit)])
}
#let plain-chip(body) = box(fill: white, stroke: 0.4pt + luma(150), inset: (x: 2pt, y: 0.8pt), radius: 1.5pt, baseline: 0.8pt, text(5.9pt, fill: luma(80), weight: "bold", body))
#let stage-keys = ("inputs", "numerator", "scatter", "ninjars", "masters", "glue", "untimed")
#let stage-label = (inputs: [inputs], numerator: [numerator], scatter: [scatter], ninjars: [NinjaRS], masters: [masters], glue: [glue], untimed: [untimed])
#let stage-bar(st, width: 2.0cm) = {
  let vals = stage-keys.map(k => calc.max(st.at(k), 0))
  let tot = vals.sum()
  let top = stage-keys.zip(vals).sorted(key: x => x.at(1)).last()
  box(width: width, height: 4.6pt, baseline: 0.5pt, fill: white, outset: 0.8pt, radius: 1pt, {
    let x = 0pt
    for (k, v) in vals.enumerate() {
      let w = width * v / tot
      if w > 0.9pt { place(dx: x, rect(width: w - 0.6pt, height: 4.6pt, fill: seg-colours.at(k), stroke: none)) }
      x += w
    }
  })
  h(4pt)
  [#stage-label.at(top.at(0)) #fixed(100 * top.at(1) / tot, 0) %]
}
#let cell-lines(lines) = for l in lines.filter(l => l != none) { v(2.7pt); block(spacing: 0pt, text(6.4pt, l)) }
#let valued(fill: none, value, mult: none, ..lines) = table.cell(fill: fill, breakable: false, {
  set par(leading: 0.34em, justify: false)
  block(spacing: 0pt, width: 100%, {
    text(10.4pt, weight: "bold", value)
    h(1fr)
    if mult != none { text(8.6pt, weight: "bold", mult) }
  })
  cell-lines(lines.pos())
})
#let absent(title, ..lines) = table.cell(fill: neutral, breakable: false, {
  set par(leading: 0.34em, justify: false)
  block(spacing: 0pt, text(8pt, weight: "bold", fill: luma(105), style: "italic", title))
  set text(fill: luma(55))
  cell-lines(lines.pos())
})
#let pkey(k) = (madloop: "ML", recola: "Rc", openloops: "OL").at(k)
#let ratio-of(c) = c.at("ratio_to_fastest", default: none)
// "native" / "Python": the per-point inputs of a configuration.
#let inputs-word(c) = { let i = c.at("inputs", default: none); if i == none { "inputs not recorded" } else { (native: "native", python: "Python").at(i, default: i) } }

// Provenance (main-configuration rule of scripts/build_summary.py): every
// cell shows the most recent configuration that measured it (git ancestry of
// the configurations' revisions, and a G1 campaign's own roles);
// summary.json names it per cell, and meta.configurations lists the
// candidates with the rows (main_rows) and cells (main_cells) where each
// supplies a main value. Stated once in Table 1 (column header; explained
// in "Reading the summary"); within a row, a cell from another configuration than the row's
// timing is marked: quietly with its revision (and its run conditions) if it
// is a newer record of the same branch, in amber with its origin otherwise.
#let C = sm.configurations
// A configuration's label with the branch name `loop` set as code.
#let lab(x) = { let t = x.label; if t.ends-with(" loop") [#t.slice(0, t.len() - 4)`loop`] else [#t] }
#let cfg-used(id) = id in C and C.at(id).main_rows.len() > 0
#let all-rows = S.groups.map(g => g.rows).flatten()
// Whether a Table 1 bar has an untimed rest (a build without per-point input
// timers; since lc-perf, 88657260, the executor times its native trees).
#let t1-untimed = all-rows.any(r => { let m = r.full_colour.main; m.status == "measured" and m.at("stages", default: none) != none and m.stages.untimed > 0 })
#let row-span(keys) = {
  let n = all-rows.filter(r => r.key in keys).map(r => r.outgoing)
  if n.len() == 0 { none } else if calc.min(..n) == calc.max(..n) [#box[$2 -> #calc.min(..n)$]] else [#box[$2 -> #calc.min(..n)$] to #box[$2 -> #calc.max(..n)$]]
}
// Rows named one by one, in table order.
#let row-names(keys) = all-rows.filter(r => r.key in keys).map(r => box(math-label(r.math))).join([, ], last: [ and ])
// A configuration's rows by kind: G1 rows and rows without a G1 record.
#let kind-keys(keys, kind) = all-rows.filter(r => r.key in keys and r.kind == kind).map(r => r.key)
// The configurations that supply measured main values, in row order.
#let first-row(id) = all-rows.position(r => r.key in C.at(id).main_rows)
#let measured-ids = ("development", "development_records", "integrated").filter(cfg-used).sorted(key: first-row)
#let dev-used = measured-ids.any(id => id != "integrated")
#let dev-rows = measured-ids.filter(id => id != "integrated").map(id => C.at(id).main_rows).flatten().dedup()
#let branch-of(id) = if id == "integrated" { "loop" } else { C.at(id).branch }
#let inputs-text(x) = x.inputs.map(i => inputs-word((inputs: i))).join(", ")
// A configuration's revisions: G1's, or the newest of the records.
#let rev-text(id) = {
  let x = C.at(id)
  if id == "development_records" {
    let rs = x.records.map(r => r.revision)
    if rs.len() == 1 [validation record #raw(rs.first())] else [validation records up to #raw(rs.first())]
  } else [G1 at #raw(x.revision)]
}
// The cells where the records supply values (main_cells): G1 rows by name
// and by cell (generation, validation or both), the other rows by
// multiplicity (generation and validation). Compact: the multiplicity alone.
#let rec-rows-text(x, compact: false, cap: false) = {
  let (g, o) = (kind-keys(x.main_rows, "g1"), kind-keys(x.main_rows, "records"))
  let (gen, val) = (x.main_cells.generation, x.main_cells.validation)
  let names(keys) = all-rows.filter(r => r.key in keys).map(r => box(math-label(r.math)))
  let both = names(g.filter(k => k in gen and k in val))
  if o.len() > 0 { both.push(if compact { row-span(o) } else [the #row-span(o) rows]) }
  let parts = (
    (names(g.filter(k => k in gen and k not in val)), "generation"),
    (names(g.filter(k => k in val and k not in gen)), "validation"),
    (both, "generation and validation"),
  ).filter(((items, _)) => items.len() > 0)
  parts.enumerate().map(((i, (items, what))) => {
    let w = if cap and i == 0 { upper(what.first()) + what.slice(1) } else { what }
    [#w of #items.join([, ], last: [ and ])]
  }).join([, ])
}
// The records' branch integrated into loop (milestone.json development
// integrated_at): its records measured the integrated code on the branch.
#let rec-integrated = C.development_records.at("integrated_at", default: none)
#let rec-before = if rec-integrated == none [] else [, made before its integration into `loop` (#C.development_records.integration, #raw(rec-integrated))]
// One clause per configuration that supplies main values, with its rows.
#let cfg-clause(id) = {
  let x = C.at(id)
  let rows = row-span(x.main_rows)
  if id == "development" [#rows: #raw(x.branch) #raw(x.revision) with #inputs-text(x) per-point inputs, gate G1 (#x.date)]
  else if id == "development_records" [#rec-rows-text(x): the validation records of #raw(x.branch)#if x.records.len() > 1 [ up to] #raw(x.records.first().revision) (#if kind-keys(x.main_rows, "g1").len() > 0 [newer revisions than G1's\; ]fixture points, #x.conditions_short, no batched timing)#rec-before]
  else if id == "integrated" [#rows: the engine on `loop` with #inputs-text(x) per-point inputs, gate G1 at #raw(x.revision) (#x.date)]
}
// The column header's compact form: the branch once, then per configuration
// its rows and revision.
#let one-branch = measured-ids.map(branch-of).dedup().len() == 1
#let cfg-short(id) = {
  let x = C.at(id)
  let rows = row-span(x.main_rows)
  let b = if one-branch { none } else if id == "integrated" [`loop` ] else [#raw(x.branch) ]
  if id == "development" [#rows: #b#raw(x.revision), #inputs-text(x) per-point inputs, G1 #x.date]
  else if id == "development_records" [#rec-rows-text(x, compact: true): #b#rev-text(id)#if rec-integrated != none [ (before #x.integration)]]
  else if id == "integrated" [#rows: #b#raw(x.revision), #inputs-text(x) per-point inputs, G1 #x.date]
}
#let header-prov = {
  let lead-in = if not one-branch [] else if measured-ids.first() == "integrated" [`loop`] else { let x = C.at(measured-ids.first()); [#raw(x.branch) (#lab(x))] }
  [*pyAmpliCol values: the most recent measured configuration*#if one-branch [ — #lead-in] · #measured-ids.map(cfg-short).join([ · ])]
}
// Where a status applies: the registry attributes refusals to loop.
#let where(c) = if c.at("configuration", default: none) in ("integrated", "registry") [on `loop`] else if c.at("configuration", default: none) == none [] else [on the development branch]
// The configuration of a row's timing, else of its generation.
#let row-lead(r) = { let m = r.full_colour.main; if m.status == "measured" { m.configuration } else { r.generation.main.at("configuration", default: none) } }
#let row-lead-rev(r) = { let m = r.full_colour.main; if m.status == "measured" { m.at("revision", default: none) } else { r.generation.main.at("revision", default: none) } }
#let origin(r, c) = {
  let id = c.at("configuration", default: none)
  let lead = row-lead(r)
  // An older record of the row's configuration kept by VALIDATION_RULE
  // (a newer one only repeats part of it): its revision, quietly.
  if id != none and id == lead and id == "development_records" and c.at("revision", default: none) != row-lead-rev(r) { dim[record #raw(c.revision)] }
  else if id == none or lead == none or id == lead { none }
  else if id == "development_records" and C.at(lead).at("branch", default: none) == C.development_records.branch {
    dim[newer record #raw(c.revision)#if "conditions_short" in c [, #c.conditions_short]]
  } else {
    let x = C.at(id)
    text(fill: amber, weight: "bold", if id == "integrated" [from `loop` (#raw(c.at("revision", default: x.revision)))] else if "branch" in x [from #raw(x.branch) (#lab(x))] else [from #lab(x)])
  }
}
#let status-title(c) = {
  let s = c.status
  if s == "refused" [refused #where(c)]
  else if s == "in development" [in development#if c.at("package", default: none) != none [ (#c.package)]]
  else if s == "not started" [not started#if c.at("package", default: none) != none [ (#c.package)]]
  else if s == "pending" [batched timing pending #box[(#c.package)]]
  else if s == "not timed" [not timed]
  else if s == "not batched" [no batched run]
  else [not measured]
}
#let status-reason(c) = if c.status == "refused" { c.at("reason", default: c.at("error", default: none)) } else if c.status in ("not started", "in development") [#c.reason: no configuration generates it yet] else { none }

// Process column: label, legs, corrections, families, validation.
#let t1-process(r) = table.cell(breakable: false, {
  set par(leading: 0.34em, justify: false)
  block(spacing: 0pt, text(10pt, font: "Libertinus Serif", math-label(r.math)))
  v(3.6pt)
  let f = r.families
  // A count recorded only for another particle veto (e.g. with top loops)
  // is printed as that configuration's, never as the row's.
  let other = f.at("other_configuration", default: none)
  let veto-text(v) = if v.len() == 0 [with top loops] else [veto #v.map(x => (str(6): "t").at(str(x), default: str(x))).join(",")]
  block(spacing: 0pt, text(6.4pt, fill: ink2)[#r.legs legs · #r.corrections · #if f.fc == none [families not recorded#if other != none [ #box[(#group(other.fc) #veto-text(other.particle_veto))]]] else [#box[#group(f.fc) families]]#if f.lc != none [ #box[(LC #group(f.lc))]]])
  let val = r.validation
  v(3.4pt)
  if val.status != "compared" {
    let rs = r.at("row_status", default: none)
    block(spacing: 0pt, text(6.4pt, fill: amber, weight: "bold", if rs != none [#status-title(rs)#if rs.at("reason", default: none) != none [: #rs.reason]] else { val.at("note", default: [not compared]) }))
  } else {
    // References whose largest deviations lie within a factor 10 share one
    // bound: "ML·OL ≤ 9.2e−13 · Rc 3.3e−10".
    let groups = ()
    for x in val.references.sorted(key: x => x.max_finite) {
      if groups.len() > 0 and x.max_finite <= 10 * groups.last().first().max_finite { groups.last().push(x) } else { groups.push((x,)) }
    }
    block(spacing: 0pt, text(6.6pt)[#groups.map(g => if g.len() == 1 [#g.first().short #esci(g.first().max_finite)] else [#g.map(x => x.short).join("·") ≤ #esci(g.last().max_finite)]).join([~· ])])
    v(2.2pt)
    let wp = val.at("worst_point", default: none)
    let within = if wp != none { wp.within_estimate } else { val.at("within_estimate", default: false) }
    let o = origin(r, val)
    block(spacing: 0pt, text(6.2pt, fill: ink2)[#if o != none [#o · ]#val.points #if val.points == 1 [pt] else [pts]#if "median_finite" in val [ · median #esci(val.median_finite)]#if within [ · †]#if val.at("note", default: none) != none [ · #val.note]])
  }
})

// Generation column: the fastest provider in bold (the multiplier's reference).
#let t1-generation(r) = {
  let g = r.generation
  let (m, f) = (g.main, g.fastest)
  let unf = g.at("unfinished", default: (:))
  let parts = ()
  if f != none { parts.push(text(weight: "bold")[#pkey(f.key) #dur(f.seconds)]) }
  parts += g.providers.pairs().filter(((k, x)) => x != none and "seconds" in x and (f == none or k != f.key)).sorted(key: ((k, x)) => x.seconds).map(((k, x)) => [#pkey(k) #dur(x.seconds)])
  if "madloop" in unf { parts.push([ML diagrams #dur(unf.madloop.graph_generation_s), stopped in export]) }
  if "recola" in unf { parts.push([Rc unfinished]) }
  let prov-line = if parts.len() == 0 [no provider generation recorded] else { parts.join([~· ]) }
  if m.status == "measured" {
    // GENERATION_RULE: a newer record in a G1 row has no multiplier (its
    // conditions differ from the providers' G1 runs, listed beside it).
    let o = origin(r, m)
    let unmatched = "no_ratio" in m
    // Uncoloured (user rule (a) of 2026-10-24 ~22:35): generation time is
    // not the main metric; the multiplier stays as text.
    valued(fill: none, dur(m.seconds), mult: if ratio-of(m) != none { mult2(ratio-of(m)) },
      [#gib(m.peak_gib) peak · plan #box[#sig(m.plan_mb)~MB]], prov-line,
      if unmatched [#if o != none [#o: ]#dim[no multiplier]] else { o })
  } else {
    absent(status-title(m), status-reason(m), m.at("basis", default: none), prov-line)
  }
}

// Full-colour column.
#let t1-fc(r) = {
  let c = r.full_colour
  let (m, f) = (c.main, c.at("fastest", default: none))
  let prov-line = if f == none { none } else {
    let rest = c.providers.pairs().filter(((k, x)) => k != f.key and "seconds_per_point" in x).sorted(key: ((k, x)) => x.seconds_per_point).map(((k, x)) => [#pkey(k) #dur(x.seconds_per_point)])
    let gone = c.providers.pairs().filter(((k, x)) => x.status == "unavailable").map(((k, x)) => [#pkey(k) no library])
    let nr = c.providers.pairs().filter(((k, x)) => x.status == "not run").map(((k, x)) => [#pkey(k) not exported])
    ((text(weight: "bold")[#pkey(f.key) #dur(f.seconds_per_point)],) + rest + gone + nr).join([~· ])
  }
  // Rows without a G1 record: the providers' production references (text
  // of DESIGN Table 1b), the computed gate limit, or the unmatched
  // alternative.
  let rt = c.at("reference", default: none)
  let alt = c.at("alternative", default: none)
  let no-gate = c.gate_rule.starts-with("no gate")
  // One provider's production entry, never broken across lines: OpenLoops
  // and Recola as transcribed, MadLoop from its timing record (range of the
  // points); Recola's protocol run where it has no production time.
  let srange(lo, hi) = if repr(sig(lo)) == repr(sig(hi)) { sig(lo) } else [#sig(lo)–#sig(hi)]
  let pentry(k) = {
    let x = rt.providers.at(k)
    if k == "madloop" { box[ML #if x.low == none [not measured] else { srange(x.low, x.high) }] }
    else if "protocol" in x { [#box[#pkey(k) #x.text] (protocol run, poles on, cache #x.protocol.collier_cache: #box[#srange(x.protocol.low, x.protocol.high)])] }
    else { box[#pkey(k) #x.text] }
  }
  let ref-lines = (
    if alt == none { none } else [#alt.name #dur(alt.seconds_per_evaluation) per evaluation (one core; not matched)],
    if rt == none { none } else if no-gate [no matched provider: reported without a gate (addendum H)] else [production, s/pt (20 Oct): #("openloops", "recola", "madloop").map(pentry).join([~· ])],
    if rt == none or no-gate { none } else if rt.limit_seconds == none [no complete gate limit (#rt.missing_production.join(", ") production not measured)] else [gate limit #str(rt.limit_seconds) s/pt (#rt.binding)],
  )
  if m.status == "measured" {
    valued(fill: ratio-fill(ratio-of(m)), dur(m.seconds_per_point), mult: mult2(ratio-of(m)),
      [#prov-line #h(1fr) $B = #m.batch$],
      ..if "gate" in m and m.gate.status == thr-rule.verdict {
        // The longer not-gated chip on its own line, the bar below it.
        ([#gate-chip(m.gate)], [#stage-bar(m.stages)])
      } else {
        ([#if "gate" in m { gate-chip(m.gate) } else { plain-chip[#c.gate_rule.replace("->", "→")] } #h(4pt) #stage-bar(m.stages)],)
      },
      origin(r, m))
  } else if m.status == "not batched" {
    absent(status-title(m), [G1 timed $B = #m.timed_batches.map(str).join(", ")$ only · #prov-line])
  } else {
    absent(status-title(m), if m.status == "refused" { status-reason(m) }, prov-line, ..ref-lines)
  }
}

// Leading-colour column (neutral: no provider ratio).
#let t1-lc(r) = {
  let m = r.leading_colour.main
  // The schedule G1 adopted for the class, where it is not the protocol's B
  // (summary.json carries it only when run at the main value's revision:
  // Table 1 shows the most recent measurements only).
  let alt(x) = if "adopted_schedule" not in x { none } else { let a = x.adopted_schedule; [ · #box[#a.schedule: #dur(a.seconds_per_point)]] }
  if m.status == "measured" {
    valued(fill: none, dur(m.seconds_per_point), mult: if "lc_over_fc" in m [#text(6.8pt)[LC/FC] #fixed(m.lc_over_fc, 2)],
      [$B = #m.batch$#if "fc_seconds_per_point" in m [ · FC #dur(m.fc_seconds_per_point)]#alt(m)], origin(r, m))
  } else if m.status == "not timed" {
    absent(status-title(m), [G1 timed full colour only])
  } else {
    absent(status-title(m))
  }
}

#let group-title = ("2->2": [$2 -> 2$], "2->3": [$2 -> 3$], "2->4": [$2 -> 4$], "2->5": [$2 -> 5$])
// The DESIGN records of the development validations shown in Table 1,
// newest first, each with its rows.
#let records-text = C.development_records.records.map(x => [#x.record.split(",").first() for #x.rows.map(r => box(math-label(r))).join([, ])]).join([\; ])
// Their short form: the increments and revisions only.
// A DESIGN record's increment ("ninth"), from its record string.
#let inc-name(rec) = rec.split(",").first().replace("DESIGN.md WP3.1 ", "").replace(" increment", "").split(" (").first()
#let records-short = [DESIGN WP3.1, #C.development_records.records.map(x => inc-name(x.record)).join([, ], last: [ and ]) increments]
// The generation threads each record's increment states (milestone.json
// development_records.threads, through summary.json), newest first.
#let threads-text = C.development_records.records.map(x => [#inc-name(x.record): #C.development_records.threads.at(x.revision)]).join([\; ])
// Rows whose gate verdict is a user decision (legend of Table 1).
#let decided-gate(r) = r.full_colour.main.at("gate", default: none)
#let decided-rows = all-rows.filter(r => { let x = decided-gate(r); x != none and "decision" in x })
// G1 rows whose generation is a newer record without a multiplier, and
// validations whose worst point was re-evaluated by an earlier run (reading
// notes of Table 1).
#let s-g1-count = all-rows.filter(r => r.kind == "g1" and r.validation.at("worst_point", default: none) != none).len()
#let no-ratio-rows = all-rows.filter(r => r.kind == "g1" and "no_ratio" in r.generation.main)
#let stab-other = all-rows.filter(r => {
  let v = r.validation
  let wp = v.at("worst_point", default: none)
  let id = v.at("configuration", default: none)
  wp != none and wp.at("revision", default: none) != none and id in C and C.at(id).at("revision", default: none) != wp.revision
})
// Rows with a gate limit but no G1 timing yet (the seven-leg rows).
#let seven-untimed = all-rows.filter(r => r.full_colour.gate_rule.starts-with("G1 (seven-leg") or r.full_colour.gate_rule.starts-with("G1 (no complete"))

// ================================================================ PAGE 1 ==
// Pages 1-2 hold only the title line, Table 1, Figure 1 and compact visual
// legends (user rule (e) of 2026-10-24 ~22:35); every explanation is in
// "Reading the summary" after Figure 1.
#align(center)[
  #v(-0.3em)
  #text(23pt, weight: "bold", fill: navy)[pyAmpliCol at one loop]
  #v(-0.6em)
  #text(11.5pt, fill: luma(80))[The recursive one-loop engine against MadLoop, Recola, OpenLoops and NJet]
  #v(-0.4em)
  #text(8.6pt, fill: luma(105))[#sm.date · engine #raw(sm.engine_on_loop) on `loop` · #sm.host.split(",").first(), shared host · finite part · binary64 · one pinned thread · batches of $B = 128$]
]


// Compact visual legend of Table 1 (its text: "Reading the summary").
#let thr-rows = all-rows.filter(r => { let x = decided-gate(r); x != none and x.status == thr-rule.verdict })
#let m-rows = all-rows.filter(r => "adopted_schedule" in r.leading_colour.main)
#let key-swatch(fill) = box(baseline: 0.5pt, rect(width: 5pt, height: 5pt, fill: fill, stroke: 0.3pt + luma(200)))
#block(breakable: false, width: 100%, above: 1.0em, below: 0.9em, {
  set text(6.9pt, font: sans, stretch: 87.5%)
  set par(justify: false, leading: 0.5em)
  grid(columns: (5.4cm, 1fr), column-gutter: 14pt,
    {
      box(width: 5.4cm, height: 0.26cm, fill: palette, radius: 2pt)
      v(-0.5em)
      [×1/16 #h(1fr) ×1/4 #h(1fr) ×1 #h(1fr) ×4 #h(1fr) ×16]
      v(-0.6em)
      text(fill: ink2)[faster #h(1fr) run time ÷ fastest provider #h(1fr) slower]
    },
    {
      [*Gate* #h(2pt) #gate-chip((status: "pass", ratio_to_limit: 0.25)) #gate-chip((status: "fail", ratio_to_limit: 1.4)) #gate-chip((status: "open", ratio_to_limit: 1.0)) #gate-chip((status: thr-rule.verdict, ratio_to_limit: 1.4)) #h(2pt) #text(fill: ink2)[time ÷ limit]]
      linebreak()
      [*Stages* #h(2pt) ]
      for (k, n) in stage-keys.enumerate() { if n != "untimed" or t1-untimed { box[#key-swatch(seg-colours.at(k))#h(1.5pt)#stage-label.at(n)]; h(4pt) } }
      linebreak()
      [#key-swatch(neutral) missing (why) #h(4pt) #key-swatch(white) no colour: generation, LC #h(4pt) † within estimate#if decided-rows.len() > 0 [ #h(4pt) ‡ user decision] #h(4pt) ML MadLoop · Rc Recola · OL OpenLoops]
    },
  )
})


#figure(kind: table,
  caption: [*State of the one-loop engine.* How to read it: #link(<reading>)[after Figure 1].],
  {
    set text(7pt, font: sans, stretch: 87.5%)
    set par(justify: false)
    show table.cell.where(y: 0): set text(fill: white, weight: "bold", size: 8pt)
    table(
      columns: (0.5cm, 3.95cm, 3.75cm, 5.75cm, 1fr),
      align: left + std.top,
      inset: (x: 4.5pt, y: 4.2pt),
      stroke: (x, y) => (top: if y <= 3 { none } else { 0.6pt + white }, left: if x > 0 and y != 1 { 0.6pt + white } else { none }),
      fill: (x, y) => if y == 0 { navy } else if y == 1 { warm } else if y == 2 { pale } else { none },
      table.header(
        [], [Process · validation], [Generation], [Full colour · per point, batched], [Leading colour (LC)],
        // Provenance of every value below, stated once (main-configuration
        // rule; per cell in data/summary.json).
        table.cell(colspan: 5, inset: (x: 4.5pt, y: 2.6pt), { show raw: set text(6.3pt); text(6.6pt, fill: amber, header-prov) }),
        [],
        ..(
          [legs · corrections · loop families; largest deviation of the finite part per reference],
          [generate + plan export, peak memory, plan size; provider generation on this host],
          [median per point at the largest batch; provider times; gate G1 (time ÷ limit); stage shares],
          [batched, same configuration; LC/FC; no provider ratio],
        ).map(t => text(6.1pt, fill: ink2, t)),
      ),
      ..S.groups.map(gr => (
        table.cell(rowspan: gr.rows.len(), fill: luma(226), inset: 0pt, align: center + horizon, breakable: false,
          rotate(-90deg, reflow: true, text(8.4pt, weight: "bold", fill: navy, font: "Libertinus Serif", group-title.at(gr.name)))),
        ..gr.rows.map(r => (t1-process(r), t1-generation(r), t1-fc(r), t1-lc(r))).flatten(),
      )).flatten(),
    )
  },
) <tab:summary>

// Figure 1: the batched full-colour time of each G1 row against its gate
// limit and the providers, on a log scale (data/summary.json).
#let fig-lo = calc.log(0.0005, base: 10)
#let fig-hi = calc.log(50.0, base: 10)
#let fig-w = 11.2cm
#let fig-h = 11pt
#let xpos(t) = fig-w * (calc.log(t, base: 10) - fig-lo) / (fig-hi - fig-lo)
#let fig-ticks = ((0.001, [1 ms]), (0.01, [10 ms]), (0.1, [100 ms]), (1.0, [1 s]), (10.0, [10 s]))
#let fig-rows = all-rows.filter(r => r.full_colour.at("fastest", default: none) != none)
#let fig-dot(fill: none, stroke: none) = circle(radius: 2.9pt, fill: fill, stroke: stroke)
// One value per row: Table 1's main value (the most recent configuration).
#let fig-row(r) = {
  let c = r.full_colour
  let m = c.main
  let g = m.at("gate", default: none)
  box(width: fig-w, height: fig-h, {
    for (t, _) in fig-ticks { place(dx: xpos(t), line(start: (0pt, 0pt), end: (0pt, fig-h), stroke: 0.4pt + luma(222))) }
    place(dy: fig-h / 2, line(start: (0pt, 0pt), end: (fig-w, 0pt), stroke: 0.4pt + luma(205)))
    if g != none and g.status == thr-rule.verdict {
      // Below 5 ms per point: no blocking gate (user rule), the limit grey.
      place(dx: xpos(g.limit_seconds) - 0.6pt, rect(width: 1.2pt, height: fig-h, fill: luma(150), stroke: none))
    } else if g != none {
      let xl = xpos(g.limit_seconds)
      place(dx: xl, rect(width: fig-w - xl, height: fig-h, fill: slow-red.transparentize(86%), stroke: none))
      place(dx: xl - 0.7pt, rect(width: 1.4pt, height: fig-h, fill: fail-ink, stroke: none))
    }
    place(dx: xpos(thr-rule.below_seconds_per_point), line(start: (0pt, 0pt), end: (0pt, fig-h), stroke: (paint: luma(110), thickness: 0.6pt, dash: "dotted")))
    for (k, x) in c.providers.pairs() {
      if "seconds_per_point" in x {
        let fast = k == c.fastest.key
        place(dx: xpos(x.seconds_per_point) - 2.4pt, dy: fig-h / 2 - 2.4pt,
          rotate(45deg, square(size: 3.4pt, fill: if fast { luma(40) } else { luma(165) }, stroke: 0.4pt + white)))
      }
    }
    if m.status == "measured" { place(dx: xpos(m.seconds_per_point) - 2.9pt, dy: fig-h / 2 - 2.9pt, fig-dot(fill: navy, stroke: 0.6pt + white)) }
  })
}
#figure(
  caption: [*Batched full colour against the gate* (finite part, $B = 128$; the rows of @tab:summary with a matched provider).],
  {
    set text(7pt, font: sans, stretch: 87.5%)
    grid(columns: (3.2cm, fig-w, 1fr), column-gutter: 6pt, row-gutter: 3pt, align: (right + horizon, left + horizon, left + horizon),
      ..fig-rows.map(r => {
        let m = r.full_colour.main
        let chip = if m.status != "measured" { plain-chip[#status-title(m)] } else if "gate" in m { gate-chip(m.gate) } else { plain-chip[no gate] }
        (text(8.6pt, font: "Libertinus Serif", math-label(r.math)), fig-row(r), chip)
      }).flatten(),
      [], box(width: fig-w, height: 9pt, for (t, l) in fig-ticks { place(dx: xpos(t) - 1cm, box(width: 2cm, align(center, text(fill: ink2, l)))) }), [],
    )
    // Compact visual key (its text: "Reading the summary").
    let key-mark(body) = box(width: 8pt, height: 7pt, baseline: 1pt, body)
    v(2pt)
    text(fill: ink2, {
      key-mark(place(dx: 1.1pt, dy: 0.6pt, fig-dot(fill: navy, stroke: 0.6pt + white))); [pyAmpliCol (@tab:summary)]; h(9pt)
      key-mark(place(dx: 1.6pt, dy: 1.2pt, rotate(45deg, square(size: 3.4pt, fill: luma(40), stroke: 0.4pt + white)))); [fastest provider]; h(9pt)
      key-mark(place(dx: 1.6pt, dy: 1.2pt, rotate(45deg, square(size: 3.4pt, fill: luma(165), stroke: 0.4pt + white)))); [other providers]; h(9pt)
      key-mark({ place(dx: 1pt, rect(width: 1.4pt, height: 7pt, fill: fail-ink, stroke: none)); place(dx: 2.4pt, rect(width: 5.6pt, height: 7pt, fill: slow-red.transparentize(86%), stroke: none)) }); [gate limit, shaded side fails]; h(9pt)
      key-mark(place(dx: 3pt, rect(width: 1.2pt, height: 7pt, fill: luma(150), stroke: none))); [limit, not gated]; h(9pt)
      key-mark(place(dx: 3.5pt, line(start: (0pt, 0pt), end: (0pt, 7pt), stroke: (paint: luma(110), thickness: 0.6pt, dash: "dotted")))); [5 ms]
    })
  },
) <fig:gate>

#pagebreak(weak: true)

// ============================================================== READING ==
// Everything that explains Table 1 and Figure 1 (user rule (e)).
#heading(numbering: none)[Reading the summary] <reading>
#[
#set text(9.4pt)
#set par(justify: true)
*Table 1* has one row per test process, by multiplicity. A cell gives pyAmpliCol's value in bold and, at its right, the
multiplier _pyAmpliCol ÷ the fastest provider_ on this host (in bold among the provider values). Only run times are
coloured: green faster, white at parity, red slower (log₂ scale, clamped at ×1/16 and ×16). Generation cells carry their
multiplier uncoloured (generation time is not the main metric, user 2026-10-24); leading colour has no provider ratio.
Grey cells say why a value is missing. Run times are per phase-space point in batches, finite part, stability checks off;
providers in production mode (@status). Every value is the *most recent measured configuration* of its cell (by git
ancestry of the revisions; a newer check that only repeats part of an older comparison does not replace it):
#measured-ids.map(cfg-clause).join([\; ])#if dev-used [. #if cfg-used("integrated") [The values of #row-span(dev-rows) are] else [These are] #if rec-integrated != none and not cfg-used("development") [*development measurements*, not yet repeated on `loop`] else [*development measurements* of a branch being integrated into `loop`#if C.development_records.at("integration", default: none) != none [ (#C.development_records.integration)], not yet on `loop`]]. #if not cfg-used("integrated") [The engine on `loop` (#inputs-text(C.integrated) per-point inputs, G1 at #raw(C.integrated.revision)) is not shown there: @g1 (gate-G1 details) keeps its timings for history.] else if py-revs.len() > 0 [The engine before #C.development_records.at("integration", default: "this milestone") (Python per-point inputs, G1 at #rev-list(py-revs)) is history in @g1.] The column header of Table 1 names these configurations once.

*Gate chips* (Table 1 and Figure 1): the time over the binding limit (MadLoop's time, or 1.30 × the faster of Recola and
OpenLoops), *pass* or *fail* when the whole uncertainty band is below or above 1, else *open*. The user's gate rule of 2026-10-24:
a process whose batched time per point is below 5 ms has no blocking gate, its verdict is "#thr-rule.label" and its chip
("#thr-rule.short") keeps the measured ratio#if thr-rows.len() > 0 [ (#thr-rows.map(r => { let x = decided-gate(r); [#box(math-label(r.math)) #dur(r.full_colour.main.seconds_per_point), #fixed(x.ratio_to_limit, 2) of its limit] }).join([, ], last: [ and ]))]. #box(math-label("g g -> g g")) ($2 -> 2$) has no gate#for r in decided-rows.filter(r => decided-gate(r).status != thr-rule.verdict) { let x = decided-gate(r); [; ‡ #math-label(r.math): #x.status (#x.decision), measured #x.measured_status at #fixed(x.ratio_to_limit, 2), band #fixed(x.band.at(0), 2)–#fixed(x.band.at(1), 2)] }.

*Stage shares* (the bar of the full-colour cell; the largest is named; @tab:g1split): inputs = trees, Born and
counterterm inputs (on `loop` the executor's own timer of its native trees, since lc-perf); glue = point parameters, input
conversion, assembly and the rest of the call#if t1-untimed [; untimed = the rest of the call of a build without input
timers]. Times use the protocol's schedule B#if m-rows.len() > 0 [; "M:" gives the schedule G1 adopted for the class (@tab:g1bm)].

*References and deviations.* ML MadLoop 3.7.0, Rc Recola 2.2.5 (COLLIER), OL OpenLoops 2.1.5 (prebuilt libraries: no
generation time), NJet DD NJet 3.1.2 in double-double. Deviation $|a - b| slash max(|a|, |b|, |B| alpha_s slash 2 pi)$ of the
binary64 finite part at the timed points (median: over the points, the largest over the references); † the largest lies
within the binary64 stability estimate of the same configuration at that point#if stab-other.len() > 0 [ (#if stab-other.len() == s-g1-count [G1 rows] else [#row-names(stab-other.map(r => r.key))]: stability runs of #rev-list(stab-other.map(r => r.validation.worst_point.revision).dedup()) on the same process, whose binary64 values equal the timed ones to rounding level, more at binary64-unstable points: `values_note` of `data/g1.json`)].
#if no-ratio-rows.len() > 0 [A newer development record's generation in a G1 row has no multiplier (its provider generation is G1's).]


// G1 rows whose newer validation record only repeats part of G1's
// comparison (summary.json validation.partial_repeats).
#let repeat-rows = all-rows.filter(r => r.validation.at("partial_repeats", default: ()).len() > 0)
// Those where G1's comparison stays, and those where an older record stays.
#let g1-repeats = repeat-rows.filter(r => r.validation.configuration != "development_records")
#let rec-repeats = repeat-rows.filter(r => r.validation.configuration == "development_records")
#let and-list(xs) = xs.join(", ", last: " and ")
#let repeat-text(r) = {
  let v = r.validation
  let x = v.partial_repeats.first()
  let lost = v.references.map(y => y.short).filter(s => s not in x.references)
  [#box(math-label(r.math)) (#x.points of #v.points#if lost.len() > 0 [, without #and-list(lost)])]
}
#let cfg-detail(id) = {
  let x = C.at(id)
  if id == "development" [#row-span(x.main_rows): #raw(x.branch) #raw(x.revision) with #inputs-text(x) per-point trees, Born and counterterm inputs; timers in scratch commit #raw(x.commit), build #raw(x.native_build)]
  else if id == "development_records" {
    let g = kind-keys(x.main_rows, "g1")
    let same = cfg-used("development") and C.development.branch == x.branch
    [#rec-rows-text(x, cap: true): #if same [that branch's validations] else [the validations of #raw(x.branch)] with #inputs-text(x) inputs and the production counterterm route (#records-short\; @tab:validation)#if g.len() > 0 [, newer than G1's revision], #x.conditions#if repeat-rows.len() > 0 [. Partial repeats leave the more complete comparison in the table: #(
      (if g1-repeats.len() > 0 { ([#g1-repeats.map(repeat-text).join([ and ]) keep G1's (@tab:g1values)],) } else { () })
      + rec-repeats.map(r => { let v = r.validation; let y = v.partial_repeats.first(); [#box(math-label(r.math)) (#inc-name(y.record), #y.points of #v.points points) the #inc-name(v.record) increment's (#raw(v.revision))] })
    ).join([, ])]#if seven-untimed.len() > 0 [. G1 has not timed the #row-span(kind-keys(x.main_rows, "records")) rows yet (#raw(ms.pending.batched)): their gate limits come from the providers' production times (20 Oct, DESIGN §1.3 Table 1b)]]
  }
  else if id == "integrated" [#row-span(x.main_rows): the engine on `loop`, gate G1 at #raw(x.revision)#if x.lc_revision != none and x.lc_revision != x.revision [ (LC: #raw(x.lc_revision))], build #raw(x.native_build), #inputs-text(x) per-point inputs (@g1)]
}
*Configurations* (main-configuration rule of `scripts/build_summary.py`; `data/summary.json` names the
configuration and source of every value). #measured-ids.map(cfg-detail).join([. ]). Generation excludes model loading;
unbatched development timings (e.g. a seven-gluon point with its rotation check) are not in this table (@sevenglue).


*Figure 1* places each row's batched full-colour value of Table 1 (dots; the most recent measured configuration:
#measured-ids.filter(id => C.at(id).main_cells.full_colour.len() > 0 and C.at(id).kind == "g1").map(cfg-short).join([\; ])#if C.at("development", default: none) != none and C.development.main_cells.full_colour.len() > 0 [\; development, not yet on `loop`]) against the providers (diamonds, the darkest
the fastest) and the gate limit (red bar, the shaded side fails; grey bar: the limit of a process below 5 ms, not gated;
dotted line: 5 ms), for the rows with a matched provider, at $B = 128$. The ratios and bands at every batch size: @tab:g1batch.
]


// =============================================================== STATUS ==
= Status at this milestone <status>

// The gate box reads Table 1's values (data/summary.json): the gated G1
// rows' full-colour main cells, their configuration and verdicts, and for
// B = 1 the same G1 configuration's records (and its one-lane twin).
#let s-gated = all-rows.filter(r => r.kind == "g1" and r.full_colour.gate_rule == "G1")
// Rows whose batched timing is pending, and rows without a matched provider
// (summary.json full_colour.main.status, full_colour.gate_rule).
#let s-pending = all-rows.filter(r => r.full_colour.main.status == "pending")
#let s-no-gate = all-rows.filter(r => r.full_colour.gate_rule == "no gate (no matched provider)")
#let s-main(r) = r.full_colour.main
#let s-gate(r) = { let m = s-main(r); if m.status == "measured" { m.at("gate", default: none) } else { none } }
#let s-ids = s-gated.filter(r => s-main(r).status == "measured").map(r => s-main(r).configuration).dedup()
#let s-with(st) = s-gated.filter(r => s-gate(r) != none and s-gate(r).status == st)
#let s-decided = s-gated.filter(r => s-gate(r) != none and "decision" in s-gate(r) and s-gate(r).status != thr-rule.verdict)
// Below 5 ms per point: no blocking gate (user rule; summary.json gate.rule).
#let s-thr = s-with(thr-rule.verdict)
#let s-blocking = s-gated.filter(r => r not in s-thr)
#let s-at-one(suffix, st) = s-gated.filter(r => {
  let m = s-main(r)
  let name = m.at("g1_configuration", default: none)
  name != none and status(gproc(r.key), cfg(gproc(r.key), name + suffix), "1") == st
})
#let s-lanes = s-gated.any(r => { let n = s-main(r).at("g1_configuration", default: none); n != none and cfg(gproc(r.key), n + "/L1") != none })
#let s-config(id) = {
  let x = C.at(id)
  if id == "integrated" [#inputs-text(x) per-point inputs on `loop` (G1 at #raw(x.revision))]
  else [#inputs-text(x) per-point inputs on #raw(x.branch) #raw(x.revision) (#lab(x)#if x.at("integration", default: none) != none [ as #x.integration])]
}
#grid(columns: (1fr, 1fr), gutter: 8pt,
  box-note[
    #set par(justify: false)
    *On `loop`* (engine #ms.engine_revision\; merges since #ms.previous_loop#if ms.at("previous_engine", default: none) != none [, engine #ms.previous_engine])
    #v(-0.2em)
    #set text(8.2pt)
    #table(columns: (auto, auto, 1fr), stroke: none, inset: (x: 2pt, y: 2.2pt),
      ..ms.integrated.map(r => (raw(r.sha), text(weight: "semibold", r.wp), [*#r.title.*])).flatten())
    #v(-0.3em)
    #text(8.2pt)[*Before (#if ms.at("previous_engine", default: none) != none [engine #ms.previous_engine] else [#ms.previous_loop]):* #ms.already_on_loop.
      *Native build* #raw(ms.native_build.name) (digest #raw(ms.native_build.digest)…).]
  ],
  block(width: 100%, stroke: 0.6pt + luma(195), inset: 9pt, radius: 3pt, {
    set text(8.4pt)
    set par(justify: false)
    [*Gate G1* (@g1; finite part, $2 -> 3$ and beyond)]
    [
      - *Most recent configuration* (Table 1 and Figure 1): #s-ids.map(s-config).join([; ]) at $B = 128$:
        #s-with("pass").len() of #s-blocking.len() gated #if s-blocking.len() == 1 [process passes] else [processes pass]#if s-decided.len() > 0 [ (#s-decided.map(r => { let x = s-gate(r); [#math-label(r.math) by #x.decision (#fixed(x.ratio_to_limit, 2) of its limit, band #fixed(x.band.at(0), 2)–#fixed(x.band.at(1), 2))] }).join([, ]))]#if s-with("open").len() > 0 [, #row-names(s-with("open").map(r => r.key)) open]#if s-with("fail").len() > 0 [, #row-names(s-with("fail").map(r => r.key)) #if s-with("fail").len() == 1 [fails] else [fail]
        (#s-with("fail").map(r => [×#fixed(s-gate(r).ratio_to_limit, 2)]).join([, ]) of the limit)]#if s-thr.len() > 0 [; #row-names(s-thr.map(r => r.key)) #if s-thr.len() == 1 [runs] else [run] below 5 ms per point: *not gated* (user 2026-10-24\; #s-thr.map(r => fixed(s-gate(r).ratio_to_limit, 2)).join([, ]) of the limit)].
        At $B = 1$ #if s-at-one("", "pass").len() == 0 [no gated process passes] else [#s-at-one("", "pass").len() pass] with 16 lanes#if s-lanes [ (#s-at-one("/L1", "pass").len() with one lane: the development runs of #rev-list(l1-revs), history; the public path runs 16 lanes)].
#if not cfg-used("integrated") [
      - *On `loop` (integrated, #inputs-text(C.integrated) per-point inputs): not met* (history, @g1). It fails every gated process it
        generates, at #ratio-range(py-big) of the binding limit at $B = 128$ (the Python inputs take
        #pct-range(inputs-share) of the time) and at #ratio-range(py-one-only-lim) for #names(py-one-only), timed at $B = 1$ only,
        and refuses #names(py-refused) ($Z$ fermion signs, WP3.2; Furry zeros, WP3.5). G-int brings the native inputs to `loop`.
] else if py-timed.len() > 0 [
      - *Before G-int* (Python per-point inputs, G1 at #rev-list(py-revs)\; history, @g1): failed every gated process it
        generated, at #ratio-range(py-big) of the binding limit at $B = 128$ (the Python inputs took
        #pct-range(inputs-share) of the time) and at #ratio-range(py-one-only-lim) for #names(py-one-only), timed at $B = 1$ only,
        and refused #names(py-refused).
]
#if s-pending.len() > 0 [
      - *#row-span(s-pending.map(r => r.key)):* not timed yet (#s-pending.map(r => r.full_colour.main.package).dedup().map(raw).join(", "))#for r in s-pending.filter(r => r.full_colour.at("reference", default: none) != none and r.full_colour.reference.missing_production.len() > 0) [\; #math-label(r.math) has no complete gate limit (#r.full_colour.reference.missing_production.join(", ") production not measured)]#if s-no-gate.len() > 0 [\; #row-names(s-no-gate.map(r => r.key)) #if s-no-gate.len() == 1 [has] else [have] no matched provider and #if s-no-gate.len() == 1 [is] else [are] reported without a gate].
]
    ]
  }),
)

#grid(columns: (1fr, 1fr), gutter: 8pt,
  box-note(fill: white, stroke: 0.6pt + luma(205))[
    #set par(justify: false)
    *In development* (branches, not on `loop`; HANDOFF §6)
    #set text(8.3pt)
    #let gg4-gen = cfg(gproc("gg_gggg"), "native/full").generation.generate.seconds
    - *Counterterm-route parity* (Rust A4, `native-dag`, with A5's counterterm emission brought forward; last fix round):
      A4 switches the counterterm program to the native builder of A3. ct-perf's output-identical Python savings are on
      `loop`; parity with the site oracle needs A4 (DECISIONS 2026-10-25 \~12:50). #gname("gg_gggg") generates in
      #sig(gg4-gen) s on `loop` (116 s at G-int, 64.5 s at `39824f9b` on the development branch; G1 records).
    - *Rust ports* (HANDOFF §0.4): A0–A3 are on `loop` (A3 not switched on); the switches of seeds (B), cells (C) and
      lowering (D), and generation-scale-2, follow A4.
    - *Seven-leg G1 rows* (`measure-g1-7leg`, in a fix round): batched FC and LC timings of the $2 -> 5$ rows on the
      slice, with the frozen setup heap of its harness (this milestone applied it by a launcher, @g1); not in this milestone.
    - *Electroweak* (WP3.2): the UFO's EW counterterms (`ew-ct`), massive vector bosons and Goldstones in Feynman gauge
      (`ew-gauge`); then $alpha(0)$ per external photon and several colour-singlet fermion lines.
    - *generation-scale-2:* every stored-process call without regeneration (`"uv"`/`"ir"`, correlated, resolved), SDK v4
      runtime, native Catani operator, lean poles companion.
  ],
  box-note(fill: white, stroke: 0.6pt + luma(205))[
    #set par(justify: false)
    *Missing or incomplete*
    #set text(8.3pt)
    - Electroweak loops with massive vector bosons, Goldstones, the UFO's EW counterterms and the complex-mass scheme
      (WP3.2, in development): $g g -> t overline(t) e^- e^+ g$ (EW) is not generated. On `loop`: typed refusals of EW
      requests with a non-zero width or an external photon, the QED Catani operator, and EW fermion lines ($W$ at the root
      and on loop quark lines, lepton-rooted processes); more than one colour-singlet fermion line is refused (EWI-5).
    - Gate G1 at $B = 1$ (16 lanes for one point)#if nat-fail.len() > 0 [ and for #names(nat-fail) at $B = 128$]\; batched timings of the $2 -> 5$ set
      (`measure-g1-7leg`); provider protocol-mode columns.
    - Seven-gluon generation cost (WP3.1 branch, before G-int): #let g7r = meas.required_native.processes.gg_ggggg
      #minutes(g7r.generate_s + g7r.export_s) with the plan export (generation #minutes(g7r.generate_s), mostly the
      always-generated poles companion), peak #fixed(calc.max(g7r.generate_peak_gib, g7r.export_peak_gib), 1) GiB
      (@sevenglue); inside addendum H, to be made lean.
    - Ward check at seven gluons. Prepared artifacts (addendum G): relocatable since `7db32901` (no host strings, SymJIT
      applications recompiled at load, bitwise binary64 after relocation), but correlated, resolved and flavour calls, the
      `"uv"`/`"ir"` selections and the writer's `regenerated-at-load` fallback still regenerate on first use
      (generation-scale-2), and the parameter program's SymJIT bytes differ per compilation (values unaffected; upstream
      fix filed).
  ],
)

#block(width: 100%, stroke: 0.6pt + luma(195), inset: 9pt, radius: 3pt, {
  set text(8.4pt)
  set par(justify: false)
  [*Performance gates and timing protocol: definitions*]
  [
    - *Gate.* Faster than MadLoop and at most 1.30× each matched Recola and OpenLoops time, on the *finite part*, from
      $2 -> 3$ upward; $2 -> 2$ is reported without a gate. A process whose batched time per point is below 5 ms has no
      blocking gate: its ratio is shown, its verdict is "#thr-rule.label" (user decision; `data/milestone.json`
      `gate_decisions.threshold_rule`); optimisation effort goes to higher multiplicities. Aspiration: fastest of all tools
      from $2 -> 3$.
    - *Protocol.* Providers in production mode with poles off where they allow it (OpenLoops `truepoles 0`, Recola without IR
      poles, MadLoop production build); pyAmpliCol finite-only (`poles = "none"`) with stability checks off, one pinned
      thread, binary64, 16 lanes, the same frozen points (pyAmpliCol receives their exact rationals, the providers their
      binary64 decimal text); since this milestone pyAmpliCol's setup heap is frozen out of Python's cyclic collector before
      the warm-up (a loaded runtime holds no generation objects; @g1). Statistic: median per point; the uncertainty band combines
      pyAmpliCol's block spread and the provider's repeat spread; a gate whose band contains the limit is *open*.
    - *Timing boundary.* pyAmpliCol: the public v2 runtime call (`NativeExecutor.evaluate`) for a batch of $B$ distinct
      points, everything included (per-point inputs, loop stage, assembly); the public `Runtime.evaluate` of a loaded artifact
      adds its input parsing (@g1). Providers have no batch API: one time per point
      serves every $B$. Generation: pyAmpliCol `LoopSlice.generate` plus the plan export, in G1 on one idle pinned core; a
      development record's generation in @tab:summary ran on the #C.development_records.conditions_short (threads per increment:
      @tab:validation), without a multiplier in a G1 row; MadLoop graph generation, export and compilation; Recola process
      generation; OpenLoops libraries are prebuilt (no generation time).
    - *Labels.* @tab:summary and @fig:gate show the most recent measured configuration of each cell
      (main-configuration rule of `scripts/build_summary.py`; `data/summary.json` names the configuration and source of every
      value); the column header of @tab:summary states it once, with branch and commit, and "Reading the summary" says
      when it is a development measurement not yet on `loop`. The detailed G1 tables (@g1) show the configuration on `loop` and, labelled,
      its history: the G-int runs (`4e9b5a9e`), the Python per-point inputs before G-int and the development runs of
      #rev-list(l1-revs).
      Missing values are marked, never estimated or extrapolated; test durations are never used as event timings. The legacy per-diagram engine's timings of 18 October are history (data kept in
      `data/measurements.json`, not shown).
  ]
})

= Gate G1: end-to-end timings of the v2 engine <g1>

G1 times the complete Born–virtual evaluation, *finite part only*, through the
call of the public v2 runtime (`NativeExecutor.evaluate`, which
`V2VirtualRuntime` calls) with stability checks off, on one pinned core and
one thread, binary64, 16 SIMD lanes, in batches of $B$ distinct points of a
frozen stream (REQUIREMENTS_ADDENDUM D, plan §5.8); pyAmpliCol receives the
stream's exact rational points, the providers their binary64 decimal text.
#let py-lc-revs = revs-of(p => cfg(p, "python/lc"))
The configurations:

- *native inputs, on `loop`* — the engine at #raw(g.slice_revision) (G-int
  with ct-perf, ew-poles, lc-perf, artifact-portability and ew-lines; build
  #raw(g.slice_build), unchanged by ew-lines): the executor forms the trees,
  the Born and the counterterm inputs per point, with binary64 SymJIT plane
  applications for every native tree kernel and the parameter program
  (`7db32901`) and tree closures in lanes of points (`88657260`; its report
  times them), then runs the loop stage. A stored artifact written by the
  public generator holds the plan v4 with `point_inputs = "native-v2"` (the
  SymJIT applications stored as IR, recompiled at load); for
  #gname("uux_ddxg") its plan digest equals the harness's (and G-int's), and
  `Runtime.load` in a fresh interpreter with generation forbidden gives the
  native executor (16 lanes), regenerates nothing over 128 evaluations, and
  returns bitwise the timed run's binary64 values at all 128 stream points.
  Its binary64 values equal those of G-int (`4e9b5a9e`) and of the
  development campaign of #rev-list(l1-revs) (`work/v2-generation-scale`
  #rev-list(ms.development.revisions.keys().filter(r => r not in l1-revs)) plus
  timers), whose runs are its earlier runs, to rounding level (median
  relative change 3×10⁻¹⁵ to 3×10⁻¹¹ per process; binary64-unstable points
  move more, about 10⁻³ at #gname("gg_ggg") point 66 and #gname("gg_gggg")
  point 50, outside the provider comparison); the development campaign's
  one-lane, schedule-M and stability runs were not repeated and appear below
  as history, labelled #rev-list(l1-revs)\;
- *Python inputs* #flag[history] — the engine on `loop` before G-int, G1 at
  #rev-list(py-revs)#if py-lc-revs.len() > 0 [ (LC at #rev-list(py-lc-revs))]: trees, Born amplitudes and
  counterterm scalars formed per point in Python, then the loop stage
  natively. It refused the $V$+jets rows: their closed-quark $A g g$
  triangles needed Furry's certified zeros (WP3.5), and their $Z$ couplings on
  loop quark lines the electroweak fermion signs (WP3.2).

*Timing protocol of this milestone* #flag[deviation]: the setup heap is frozen
out of Python's cyclic collector (`gc.collect()`, `gc.freeze()`) before the
warm-up. A scratch launcher applied it to the unmodified harness of
#raw(g.slice_revision) (clean checkout; the protocol of `work/v2-measure-g1-7leg`
`de8d3eb8`, not yet on `loop`); `timing_protocol` in `data/g1.json` records
it. The committed harness times with the whole generation heap in memory,
which a runtime loaded from an artifact never holds, and full collections of
that heap fell into the timed blocks: #gname("uux_ddxg") at $B = 128$ took
2.76 ms per point with the committed protocol (a collection of about 0.09 s in
2 of the 3 blocks), 1.95 ms with the frozen heap, 1.96 ms through the public
`Runtime.load` executor in a fresh interpreter and 2.08 ms through
`Runtime.evaluate` on decimal text; #gname("gg_ggg") 22.9 against 20.6 ms. The
evaluations' own collections stay in the timed blocks (0.2–2.8 % of the
timed wall). Earlier campaigns (G-int and before) used the committed
protocol.

#let g1-cell(p, c, b) = {
  if refused(c) { return table.cell(text(6.4pt, fill: amber, style: "italic")[not generable]) }
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
#let p-cell(p, n) = {
  let t = ptime(p, n)
  let r0 = prov(p, n)
  if t == none {
    let why = if r0 == none [not timed] else if "unavailable" in r0 { if n == "openloops" [no library] else [not exported] } else [not timed]
    return table.cell(text(6.6pt, fill: ink2, style: "italic", why))
  }
  let best = fastest-p(p)
  let r = t / best.t
  table.cell(fill: ratio-fill(r), {
    text(8pt, weight: "bold", msec(t))
    h(1fr)
    if best.n == n { text(6.6pt, fill: ink2)[fastest] } else { text(7.2pt, weight: "semibold", mult2(r)) }
  })
}
#let gen-v2(c) = if c == none { table.cell(tiny[—]) } else if refused(c) {
  table.cell(tiny[CT coverage refused])
} else {
  let st = c.generation
  table.cell(tiny[#sig(st.generate.seconds + st.export.seconds) s · #fixed(calc.max(st.generate.peak_gib, st.export.peak_gib), 1) GiB])
}
#let gen-p(p, n) = {
  let r = prov(p, n)
  if r == none or "unavailable" in r { return table.cell(tiny[—]) }
  if n == "madloop" {
    let gx = r.at("generation", default: none)
    let stg = r.at("stages", default: none)
    let num = if stg == none { none } else { stg.stages_seconds_per_point.at("loop numerator coefficients") / stg.instrumented_seconds_per_point }
    table.cell(tiny[#if gx == none [export] else [#sig(gx.total_s) s]#if num != none [ · #pct(num)]])
  } else if n == "recola" {
    let s = r.setup.at("generation_seconds", default: none)
    table.cell(tiny[#if s == none [—] else [#sig(s) s]])
  } else {
    let s = r.setup
    table.cell(tiny[#r.library.name · #sig(1000 * (s.at("start_seconds", default: 0) + s.at("initial_call_seconds", default: 0))) ms])
  }
}
#let gate-cell(p, b) = {
  if not p.gated { return table.cell(tiny[no gate]) }
  let a = if refused(py-c(p)) { none } else { verdict(bat(py-c(p), b)) }
  let d = verdict(bat(nat-c(p), b))
  table.cell(text(6.8pt)[#if refused(py-c(p)) { text(fill: ink2)[—] } else { gate-word(p, py-c(p), b, a) } #linebreak() #gate-word(p, nat-c(p), b, d)])
}
#figure(kind: table,
  caption: [*Gate G1, full colour*, ms per point (gate statistic: median),
    finite part, one thread. Rows $B = 1$ and $B = 128$ (the Python-input
    $2 -> 4$ rows only at $B = 1$: their Python inputs took seconds per point).
    Multiplier and colour: time ÷ the fastest provider of the row (legend of
    @tab:summary). Grey rows: generation — pyAmpliCol generation plus plan export with
    its peak memory; MadLoop graph generation, export and compilation · the
    share of its loop-numerator coefficients in its time (@tab:g1split);
    Recola process generation; OpenLoops: the prebuilt library and its load
    plus first call. MadLoop $u overline(u) -> g g g g$ was not exported: the
    $g g -> g g g g$ export took 2.4 h here (HANDOFF §0.1), and OpenLoops binds
    the gate. Gate: upper line Python inputs (history), lower line native
    inputs (`loop`); the number is the time over the binding limit (MadLoop's
    time or 1.30× the faster of Recola and OpenLoops); *open*: the band
    contains the limit#if nat-decided.len() > 0 [; ‡ pass by user decision although it does]\; *not gated*: the
    configuration runs below 5 ms per point at its largest batch (user rule of 2026-10-24, at every $B$; ratio as
    measured) (bands: @tab:g1batch).],
  tstyle(table(
    columns: (2.55cm, 0.75cm, 1fr, 1fr, 1fr, 1fr, 1fr, 2.3cm),
    align: left + horizon, inset: (x: 4pt, y: 2.6pt),
    stroke: (x, y) => (top: if y <= 1 { none } else if calc.rem(y - 1, 3) == 0 { 0.6pt + luma(190) } else { hair }, left: if x >= 2 and y > 0 { hair } else { none }),
    fill: thead-fill,
    table.header[Process][$B$][Python inputs#super[hist]][Native inputs, `loop`][MadLoop][Recola][OpenLoops][Gate],
    ..g.processes.map(p => {
      let (a, d) = (py-c(p), nat-c(p))
      let bb = if top(d) == none { top(a) } else { top(d) }
      (
        table.cell(rowspan: 3, align: left + horizon, breakable: false, {
          gname(p.key)
          linebreak()
          tiny[#if p.gated [$2 -> #p.outgoing$] else [$2 -> 2$, no gate]]
        }),
        [1], g1-cell(p, a, "1"), g1-cell(p, d, "1"), ..pnames.map(n => p-cell(p, n)), gate-cell(p, "1"),
        [#bb], g1-cell(p, a, bb), g1-cell(p, d, bb), ..pnames.map(n => p-cell(p, n)), gate-cell(p, bb),
        tiny[gen.], gen-v2(a), gen-v2(d), ..pnames.map(n => gen-p(p, n)), table.cell(tiny[]),
      )
    }).flatten(),
  )),
) <tab:g1>

The providers run in production mode on the same stream: OpenLoops with
`truepoles 0`, Recola without IR poles (one amplitude call per point), MadLoop
at its production stability setting on exports built with MG5's production
flags. OpenLoops has no installed library with QCD corrections to
$ell^+ ell^-$ + 1 or 2 jets (`ppllj_ew` carries electroweak corrections only;
existing provider builds only), so the $V$+jets gates bind on MadLoop and
Recola. Providers have no batch API: one time per point serves every $B$.
*Gate statistic:* the median per point on both sides — over pyAmpliCol's
timed blocks of one $B$, and over the provider's timed points (the stream's
first 16; 8 for #pairs-text(short-points)). The provider times are the
records of the measure-g1 campaign (23–24 October, on cores
#core-span(prov-cores)), not re-run for this milestone; pyAmpliCol ran on
cores #nat-cores.map(str).join([ and ]), one job per eight-core group sharing an L3 cache, inside the
cores 176–191 reserved for this campaign (no SMT siblings; DECISIONS
2026-10-25 \~13:45), while other users' jobs loaded those cores at 10–60 %.
The three $B = 128$ blocks of a process spread by at most
#fixed(100 * calc.max(..gated.map(p => bat(nat-c(p), big)).filter(x => x != none).map(x => x.uncertainty)), 1)~% (half the range over the median; #gname("uux_ddxg")
#bat(nat-c(gproc("uux_ddxg")), big).samples_seconds_per_point.map(v => fixed(1000 * v, 3)).join([, ]) ms).
The gate's uncertainty is pyAmpliCol's block spread (half the range of three blocks,
the median's standard error from five) plus the provider's half-range over its
repeated runs (#pct(host-spread), the campaign's largest, for the single runs
of #pairs-text(single-runs)). A gate passes or fails only if the whole band
does; otherwise it is *open* and the configuration is repeated once (plan §5.8
item 10). Every timed call returned all its points (failed points: 0); rescue
is off by protocol (no checks, no escalation), so the rescue rate is 0.

// earlier: where the configuration did not time b, its newest earlier run
// that did (marked °, uncoloured: history, not a verdict of this campaign).
// Earlier runs carry times only: their median over the same binding limit
// (one provider time serves every B), without a band.
#let band-cell(p, c, b, earlier: false) = {
  let x = bat(c, b)
  if x == none and earlier {
    let e = earlier-bat(c, b)
    let lim-big = bat(c, big)
    if e != none and lim-big != none and "binding_limit" in lim-big.gate {
      return table.cell(text(fill: ink2)[#text(7.6pt, style: "italic")[#fixed(e.x.median_seconds_per_point / lim-big.gate.binding_limit, 2)°] #h(1fr) #tiny[#msec(e.x.median_seconds_per_point) ms]])
    }
  }
  if x == none { return table.cell(dim[—]) }
  let gt = x.gate
  if "band_to_binding_limit" not in gt { return table.cell(tiny[#gt.status]) }
  let (lo, hi) = gt.band_to_binding_limit
  let st = eff-status(p, c, b, gt)
  table.cell(fill: if st == "pass" { rgb("#e1f2ea") } else if st == "fail" { rgb("#fbe3dd") } else if st == "not gated" { neutral } else { warm }, {
    text(7.6pt, weight: "bold")[#fixed(gt.ratio_to_binding_limit, 2)#if st != "not gated" and decision(p, b, gt) != none [‡]]
    h(1fr)
    tiny[#fixed(lo, 2)–#fixed(hi, 2)]
  })
}
#let repeated = gated.filter(p => first-run(nat-c(p)) != none)
#let earlier-revs = gated.map(p => ("8", "32").map(b => if bat(nat-c(p), b) == none { earlier-bat(nat-c(p), b) } else { none })).flatten().filter(e => e != none).map(e => e.rev).dedup()
#figure(kind: table,
  caption: [*The gate at every batch size* (native inputs on `loop`, full
    colour): time over the binding limit and its uncertainty band (cell
    colour: green pass, red fail, amber open, grey not gated: below 5 ms per point at $B = 128$, user rule of
    2026-10-24, at every $B$ of the process#if nat-decided.len() > 0 [; ‡ pass by user decision, the
    band containing the limit: #decided-text(nat-decided)]). $B = 1$ is timed with the
    default 16 lanes (a one-point call pays a 16-lane chunk); the one-lane
    column is the development campaign's (#rev-list(l1-revs), history: the
    public path always runs 16 lanes in binary64). This campaign timed
    $B = 1$ and $B = 128$#if repeated.len() > 0 [, and every batch size only for the single repeat of
    #names(repeated) (its first run, #repeated.map(p => { let x = first-run(nat-c(p)).batches.at(big); [#msec(x.median_seconds_per_point) ms at $B = 128$] }).join([; ]), was open at the limit: `repeats` in `data/g1.json`)] else [ (no verdict was open, so no repeat: `repeats` in `data/g1.json`)]#if earlier-revs.len() > 0 [; ° grey: the earlier
    run of #rev-list(earlier-revs) at that batch size, its median over the same binding limit with its time (no band;
    an earlier engine under the committed protocol; not a verdict of this campaign)].],
  tstyle(table(
    columns: (2.9cm, 1fr, 1fr, 1fr, 1fr, 1fr),
    align: left + horizon, inset: (x: 4pt, y: 2.6pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][$B = 1$, 16 lanes][$B = 1$, 1 lane #text(6pt, weight: "regular")[(#l1-revs.join(", "))]][$B = 8$][$B = 32$][$B = 128$],
    ..gated.map(p => (gname(p.key), band-cell(p, nat-c(p), "1"), band-cell(p, l1-c(p), "1"),
      band-cell(p, nat-c(p), "8", earlier: true), band-cell(p, nat-c(p), "32", earlier: true), band-cell(p, nat-c(p), "128"))).flatten(),
  )),
) <tab:g1batch>

== Where the time goes

#let bar(parts, total, width: 2.4cm) = box(width: width, height: 0.26cm, {
  let x = 0pt
  for (k, v) in parts.enumerate() {
    let w = width * calc.max(v, 0) / total
    place(dx: x, rect(width: w, height: 0.26cm, fill: seg-colours.at(k), stroke: none))
    x += w
  }
})
#let swatch(k) = box(fill: seg-colours.at(k), width: 5pt, height: 5pt, stroke: 0.3pt + white)
// The untimed-rest column only where a shown row has one (a build without
// per-point input timers; on loop the executor times its trees since lc-perf).
#let split-untimed = g.processes.any(p => (py-c(p), nat-c(p)).any(c => c != none and not refused(c) and { let x = bat(c, top(c)); x != none and untimed(x) > 0 }))
#let split-row(label, x) = {
  let parts = (python-inputs(x) + stage(x, "native trees"), numerator(x), stage(x, "scatter"), ninjars(x), masters(x), glue(x), untimed(x))
  let total = x.median_seconds_per_point
  // "—": the inputs where the build has no timer for them; the untimed rest where it has.
  let cells = parts.enumerate().map(((i, v)) => if (i == 0 and not inputs-timed(x)) or (i == 6 and inputs-timed(x)) { align(right, dim[—]) } else { align(right, msec(v)) })
  if not split-untimed { cells = cells.slice(0, 6) }
  (label, ..cells, align(right, text(weight: "bold", msec(total))), bar(parts, parts.sum()))
}
#let ml-row(p) = {
  let r = prov(p, "madloop")
  if r == none or r.at("stages", default: none) == none { return () }
  let s = r.stages.stages_seconds_per_point
  let parts = (s.at("Born and counterterm HELAS"), s.at("loop numerator coefficients"), 0.0, s.at("reduction and masters"), 0.0, r.stages.residual_seconds_per_point, 0.0)
  (tiny[MadLoop],
    align(right, msec(parts.at(0))), align(right, msec(parts.at(1))), align(right, dim[—]),
    table.cell(colspan: 2, align(center, msec(parts.at(3)))), align(right, msec(parts.at(5))), ..if split-untimed { (align(right, dim[—]),) } else { () },
    align(right, text(weight: "bold", msec(r.stages.instrumented_seconds_per_point))),
    bar(parts, parts.map(v => calc.max(v, 0)).sum()))
}
#figure(kind: table,
  caption: [*Stage split*, ms per point, full colour, at the largest batch timed
    (Python-input $2 -> 4$: $B = 1$). Trees/Born/CT: the per-point inputs,
    timed in Python before G-int (history: trees, counterterm program, Born
    and counterterm colour projections, scalars); on `loop` the executor forms
    them and, since lc-perf (`88657260`), times them itself (its `trees`
    stage: programs, closures, interferences)#if split-untimed [. Untimed rest: the part
    of the call a build without input timers does not time, its native trees, Born and
    counterterm inputs and the rest of the Python call]. Numerator: seeds, fused factors and the dressing of the open-loop
    objects (the pure numerator evaluation). Scatter: closures into NinjaRS
    lanes. NinjaRS: the reduction without the masters; masters: the master
    integrals (canonical arguments, cache, oneloopmaster). Glue: point
    parameters, carrier conversion, assembly and, where the inputs are timed,
    the rest of the Python call (all rows of this table).
    MadLoop (instrumented copy; its points less one, 3 for $g g -> g g g g$):
    Born/counterterm HELAS calls, loop-numerator coefficients, reduction plus
    masters, residual (stability test, colour sums). Bar: shares, colours as the
    column heads.],
  tstyle(table(
    columns: (1.8cm, 1.0cm, ..range(if split-untimed { 7 } else { 6 }).map(_ => 1fr), 1.45cm, 2.55cm),
    align: left + horizon, inset: (x: 3.5pt, y: 2.4pt),
    stroke: (x, y) => (top: if y <= 1 { none } else { hair }),
    fill: thead-fill,
    table.header(..([Process], [], [#swatch(0) Trees, Born, CT], [#swatch(1) Numerator], [#swatch(2) Scatter], [#swatch(3) NinjaRS], [#swatch(4) Masters], [#swatch(5) Glue], ..if split-untimed { ([#swatch(6) Untimed rest],) } else { () }, [Total], [Shares]).map(c => text(6.9pt, c))),
    ..g.processes.map(p => {
      let rows = ()
      let (a, d) = (py-c(p), nat-c(p))
      if d != none { rows.push(split-row(tiny[native, `loop`], bat(d, top(d)))) }
      if a != none and not refused(a) { rows.push(split-row(tiny[Python#super[hist]], bat(a, top(a)))) }
      let m = ml-row(p)
      if m.len() > 0 { rows.push(m) }
      let n = rows.len()
      rows.enumerate().map(((i, r)) => if i == 0 { (table.cell(rowspan: n, align: left + horizon, gname(p.key)), ..r) } else { r }).flatten()
    }).flatten(),
  )),
) <tab:g1split>

#let fast-word(p) = {
  let x = bat(nat-c(p), big)
  if x == none or "ratio_to_fastest" not in x.gate { return none }
  let f = x.gate.fastest_provider
  let u = x.gate.checks.at(f).uncertainty
  let r = x.gate.ratio_to_fastest
  if r < 1 - u { "faster" } else if r > 1 + u { "slower" } else { "parity" }
}
#box-note(fill: warm, breakable: false)[
  #set par(justify: true)
  *Verdict of gate G1* (processes from $2 -> 3$; $2 -> 2$ without a gate).
  - *Native inputs on `loop`* (G1 at #raw(g.slice_revision)) at $B = 128$: *pass* for
    #if nat-pass.len() == nat-gated.len() [all #nat-gated.len() gated processes, ] #names(nat-pass)#if nat-decided.len() > 0 [ (#decided-text(nat-decided))]#if nat-fail.len() > 0 [\; *fail* for #names(nat-fail)
    (#nat-fail.map(p => [#mult2(lim(p, nat-c(p), big)), #pshort(bat(nat-c(p), big).gate.binding_provider) binding]).join([; ]))]#if nat-open.len() > 0 [; *open* for #names(nat-open)
    (#nat-open.map(p => fixed(lim(p, nat-c(p), big), 2)).join([, ]) of its limit
    after the single repeat)]#if nat-ungated.len() > 0 [. *Not gated* (below 5 ms per point, user decision of 2026-10-24; ratios as measured): #ungated-text(nat-ungated)]. At $B = 1$ with 16 lanes
    #if one-pass.len() == 0 [no gated process passes] else [#names(one-pass) pass] (a
    one-point call pays a 16-lane chunk, @tab:g1batch); with one lane per
    call, in the development runs of #rev-list(l1-revs) (history),
    #if l1-pass.len() == nat-gated.len() [all #nat-gated.len() gated processes passed.] else [#names(l1-pass) passed.]
  - *Python inputs* #flag[history] (the engine before G-int, G1 at
    #rev-list(py-revs)): failed every process it generated, at $B = 128$ at
    #ratio-range(py-big) of the binding limit, the per-point Python inputs
    taking #pct-range(inputs-share) of its time (@tab:g1split); at $B = 1$ at
    #ratio-range(py-one), where #names(py-one-only) were timed only. It did
    not generate #names(py-refused) (Furry zeros, WP3.5; $Z$ fermion signs,
    WP3.2).
  - *Fastest of all tools* (aspiration), native inputs at $B = 128$, within
    the uncertainty band: faster than every provider for
    #names(gated.filter(p => fast-word(p) == "faster"))\; at parity with the
    fastest for #names(gated.filter(p => fast-word(p) == "parity"))\; slower
    than the fastest (OpenLoops) for #names(gated.filter(p => fast-word(p) == "slower")).
    NJet, not a matched provider, takes 4.58 s for its two-evaluation
    full-colour $g g -> g g g g$ test (@tab:njet).
  - Seven-leg rows ($u overline(u) -> e^- e^+ d overline(d) g$, $u overline(u) -> e^- e^+ g g g$,
    $g g -> t overline(t) e^- e^+ g$, $u overline(u) -> g g g g g$, $g g -> g g g g g$)
    are generated by the WP3.1 generator, on `loop` since G-int, and are
    added to G1 by the follow-on package `measure-g1-7leg` (not in this milestone)#if s-no-gate.len() > 0 [; #row-names(s-no-gate.map(r => r.key)) #if s-no-gate.len() == 1 [has] else [have] no matched provider timing
    (addendum F, H): reported without a gate].
]

#let sp-int = speedup-at("1")
// One stage share per gated row, native inputs at B = 128.
#let nat-shares(f) = gated.map(p => f(bat(nat-c(p), big)))
#let sp-big = speedup-at(big)
#figure(kind: table,
  caption: [*Levers*, measured on the rows of @tab:g1split. Gains are
    measured where a column says so; otherwise they are the stage's share, an
    upper bound.],
  tstyle(table(
    columns: (4.1cm, 1fr, 3.2cm, 2.9cm),
    align: left + horizon, inset: (x: 4pt, y: 3pt), stroke: tstroke, fill: thead-fill,
    table.header[Lever][Evidence][Expected gain][Owner],
    [*Native per-point inputs* (WP3.1 I3–I6: trees, Born, counterterm scalars in the executor)],
    [Python inputs #pct-range(inputs-share) of the Python-input time at $B = 128$ (history)],
    [measured, Python ÷ native inputs at equal $B$: #ratio-range(sp-int) at $B = 1$, #ratio-range(sp-big) at $B = 128$ ($2 -> 3$)],
    [done: G-int, on `loop` since `4e9b5a9e`],
    [*Binary64 point inputs* (the providers' input; the protocol passes the stream's exact rationals)],
    [paired run on the loaded artifact of G-int (`4e9b5a9e`, history), $B = 128$: #gname("uux_ddxg") 1.68 against 2.29 ms, #gname("uux_uuxg") 2.94 against 3.39 ms],
    [measured: ×1.37 and ×1.15 (information; not a G1 configuration)],
    [none: moot under the 5 ms gate rule (user, 2026-10-24); the protocol keeps exact inputs],
    [*Compiled native trees* (kernels as the tree engine's SymJIT planes, lanes batched)],
    [#if trees-timed [native trees (with the Born and counterterm inputs; the executor's timer)] else [untimed rest (the native trees, Born and counterterm inputs and the rest of the call)] #pct-range(trees-share.map(t => t.s)) of the time at $B = 128$; #gname(trees-share.sorted(key: t => t.s).last().p.key) #pct(trees-share.sorted(key: t => t.s).last().s)],
    [up to the share; ×#fixed(1 / (1 - calc.max(..trees-share.map(t => t.s))), 1) for the largest],
    [in part on `loop`: SymJIT plane applications (`7db32901`), lane-chunked tree closures (`88657260`); next: the native tree program (A5, `native-dag`)],
    [*Lanes by batch* in binary64 (`plan_export.lanes_for`: 16 lanes also for one point)],
    [$B = 1$: one 16-lane chunk per call],
    [measured: #ratio-range(lanes-gain) at $B = 1$ (16 lanes on `loop` ÷ 1 lane of #rev-list(l1-revs), different builds)],
    [executor policy (WP3.1 or wave 4)],
    [*Finite-only result path* (sum the virtual natively, no per-family lane export, Python assembly only for checks and observables)],
    [glue #pct-range(nat-shares(x => share(x, glue(x)))) of the native-input time],
    [up to the share (largest at $2 -> 3$ with quarks)],
    [`plan_export`, executor (wave 4)],
    [*Lane-major closures* (no scatter, no second copy into the reducer's batch)],
    [scatter #pct-range(nat-shares(x => share(x, stage(x, "scatter"))))],
    [up to the share],
    [executor, reducer adapter (wave 4)],
    [*AVX2 / AVX-512 kernels* (runtime selection)],
    [numerator #pct-range(nat-shares(x => share(x, numerator(x))))],
    [×1.0–1.4 on the dressing (gate G0)],
    [wave 4 (WP4.6)],
    [*NinjaRS and masters*: parallel reduction, transposed reduction, stage-2 sharing, a cheaper master cache key],
    [NinjaRS + masters #pct-range(nat-shares(x => share(x, stage(x, "reduction"))))\;
      masters #pct-range(nat-shares(x => masters(x) / stage(x, "reduction"))) of the reduction, oneloopmaster alone #pct-range(nat-shares(x => stage(x, "reduction: masters (oneloopmaster)") / stage(x, "reduction"))): the cache bookkeeping costs more than the integrals],
    [one thread: up to the share; threads: DESIGN §5.6],
    [NinjaRS requests (DESIGN §11.5)],
  )),
) <tab:levers>

#let ud = gproc("uux_ddxg")
#let udx = bat(nat-c(ud), big)
*Below 5 ms per point.* #names(nat-ungated) take
#nat-ungated.map(p => [#msec(bat(nat-c(p), big).median_seconds_per_point)]).join([, ], last: [ and ]) ms per point at
$B = 128$; by the user's decision of 2026-10-24 a process below 5 ms has no
blocking gate and its slowdown against the providers need not be pursued:
optimisation effort goes to higher multiplicities. Their ratios stay in the
tables (#gname("uux_ddxg"): #msec(udx.median_seconds_per_point) ms against a
limit of #msec(udx.gate.binding_limit) ms, OpenLoops
#msec(ptime(ud, "openloops")) ms × 1.30, #fixed(lim(ud, nat-c(ud), big), 2) of
it; measured #udx.gate.status, band #fixed(udx.gate.band_to_binding_limit.at(0), 2)–#fixed(udx.gate.band_to_binding_limit.at(1), 2)). The question whether G1 should pass the points as exact rationals (the
protocol) or as the binary64 text the providers read is moot under this
rule, and the protocol stays. For information only (not G1
configurations, no verdict formed from them): on #raw(g.slice_revision) the public
`Runtime.evaluate` of the loaded artifact takes 2.08 ms per point on 60-digit decimal text for #gname("uux_ddxg")
at $B = 128$, against 1.96 ms for its executor on the exact points (@g1, timing protocol); at G-int
(`4e9b5a9e`, committed protocol) a paired run (one core, ten alternating rounds) gave 1.68 ms on the binary64 text
against 2.29 ms on the exact points (×0.73; #gname("uux_uuxg"): 2.94 against 3.39 ms, ×0.87).

== Leading colour

// An earlier run of a configuration at one revision and batch.
#let earlier-at(c, b, r) = if c == none { none } else {
  let e = c.at("earlier_runs", default: ()).filter(x => x.revision.slice(0, 8) == r and b in x.batches)
  if e.len() == 0 { none } else { e.last().batches.at(b) }
}
// earlier: where the LC configuration did not time b, its newest earlier run
// that did, with the FC time of the same earlier campaign (°, grey).
#let lc-cell(p, lc, fc, b, earlier: false) = {
  let (x, y) = (bat(lc, b), bat(fc, b))
  if x == none and earlier {
    let e = earlier-bat(lc, b)
    if e != none {
      let f = earlier-at(fc, b, e.rev)
      return table.cell(text(fill: ink2)[#text(8pt, style: "italic", msec(e.x.median_seconds_per_point))° #h(1fr) #if f != none { tiny[FC #msec(f.median_seconds_per_point) · #fixed(e.x.median_seconds_per_point / f.median_seconds_per_point, 2)] }])
    }
  }
  if x == none { return table.cell(text(6.6pt, fill: ink2, style: "italic")[not timed]) }
  table.cell({
    text(8pt, weight: "bold", msec(x.median_seconds_per_point))
    h(1fr)
    if y != none { tiny[FC #msec(y.median_seconds_per_point) · #fixed(x.median_seconds_per_point / y.median_seconds_per_point, 2)] }
  })
}
#let lc-earlier-revs = g.processes.map(p => { let c = cfg(p, "native/lc"); if c == none or bat(c, "1") != none { none } else { earlier-bat(c, "1") } }).filter(e => e != none).map(e => e.rev).dedup()
#let lc-vjets = g.processes.filter(p => p.key.contains("emep") and cfg(p, "native/lc") != none)
#let lc-procs = g.processes.filter(p => cfg(p, "native/lc") != none or cfg(p, "python/lc") != none)
#block(breakable: false)[#figure(kind: table,
  caption: [*Leading colour* (LC), ms per point, same protocol as @tab:g1; in
    each cell the full-colour (FC) time of the same configuration and batch, and LC/FC.
    No provider ratio: the providers time full colour. LC uses the committed
    QCD colour continuation (`examples/loop/source_colour`)#if lc-vjets.len() > 0 [; the $V$+jets rows are
    timed at LC with native inputs only]. This campaign timed LC at $B = 128$#if lc-earlier-revs.len() > 0 [; ° grey: the
    earlier run of #rev-list(lc-earlier-revs) at $B = 1$ with its FC time (an earlier engine under the committed
    protocol; history)].],
  tstyle(table(
    columns: (2.9cm, 1fr, 1fr, 1fr, 1fr),
    align: left + horizon, inset: (x: 4pt, y: 2.6pt),
    stroke: (x, y) => (top: if y <= 2 { none } else { hair }, left: if x in (1, 3) and y > 0 { 0.6pt + luma(190) } else if x > 0 and y > 0 { hair } else { none }),
    fill: thead-fill,
    table.header(
      table.cell(rowspan: 2, align: left + horizon)[Process], table.cell(colspan: 2, align: center)[Python inputs#super[hist]], table.cell(colspan: 2, align: center)[Native inputs, `loop`],
      table.cell(fill: pale, text(fill: ink2)[$B = 1$]), table.cell(fill: pale, text(fill: ink2)[largest batch]),
      table.cell(fill: pale, text(fill: ink2)[$B = 1$]), table.cell(fill: pale, text(fill: ink2)[largest batch]),
    ),
    ..lc-procs.map(p => {
      let (al, af, dl, df) = (cfg(p, "python/lc"), py-c(p), cfg(p, "native/lc"), nat-c(p))
      let big-cell(lc, fc) = { let b = top(lc); if b == none { lc-cell(p, lc, fc, none) } else if b == "128" { lc-cell(p, lc, fc, b) } else { let c = lc-cell(p, lc, fc, b); table.cell[#c.body #box(tiny[($B = #b$)])] } }
      (gname(p.key), lc-cell(p, al, af, "1"), big-cell(al, af), lc-cell(p, dl, df, "1", earlier: true), big-cell(dl, df))
    }).flatten(),
  )),
) <tab:g1lc>]

#let lc-slower = g.processes.filter(p => { let (l, f) = (bat(cfg(p, "native/lc"), big), bat(nat-c(p), big)); l != none and f != none and l.median_seconds_per_point > f.median_seconds_per_point })
#let lc-big(key) = bat(cfg(gproc(key), "native/lc"), big)
#let fc-big(key) = bat(nat-c(gproc(key)), big)
// LC/FC at B = 128 on loop, and in the G-int campaign (earlier runs at 4e9b5a9e).
#let lc-ratio(p) = { let (l, f) = (bat(cfg(p, "native/lc"), big), bat(nat-c(p), big)); if l == none or f == none { none } else { l.median_seconds_per_point / f.median_seconds_per_point } }
#let lc-ratio-at(p, r) = { let (l, f) = (earlier-at(cfg(p, "native/lc"), big, r), earlier-at(nat-c(p), big, r)); if l == none or f == none { none } else { l.median_seconds_per_point / f.median_seconds_per_point } }
#let lc-now = g.processes.map(p => (p: p, r: lc-ratio(p))).filter(x => x.r != none).sorted(key: x => x.r)
#let lc-gint = g.processes.map(p => (p: p, r: lc-ratio-at(p, "4e9b5a9e"))).filter(x => x.r != none)
#let lc-trees(p) = { let x = bat(cfg(p, "native/lc"), big); if x == none or not inputs-timed(x) { none } else { share(x, stage(x, "native trees")) } }
#let fc-trees(p) = { let x = bat(nat-c(p), big); if x == none or not inputs-timed(x) { none } else { share(x, stage(x, "native trees")) } }
#if lc-slower.len() == 0 [
LC is cheaper in the loop stage (fewer families and skeletons) and, since lc-perf (`88657260`: LC-aware pruning of the
closure blocks, native tree closures in lanes of points), also end to end: with native inputs at $B = 128$ LC/FC is
#fixed(lc-now.first().r, 2)–#fixed(lc-now.last().r, 2) (#gname(lc-now.first().p.key) gains most,
#gname(lc-now.last().p.key) least), so LC is faster than full colour on every row#if lc-gint.len() > 0 [; at G-int it
was #fixed(calc.min(..lc-gint.map(x => x.r)), 2)–#fixed(calc.max(..lc-gint.map(x => x.r)), 2), slower than full colour for
#names(lc-gint.filter(x => x.r > 1).map(x => x.p)) (committed protocol; @g1)]. The native trees, with the Born and
counterterm inputs, take a larger share at LC (#("uux_ggg", "gg_gggg").map(k => [#gname(k): #pct(lc-trees(gproc(k))) at LC,
#pct(fc-trees(gproc(k))) at full colour]).join([; ])), the lever of compiled trees (@tab:levers).
] else [
LC is cheaper in the loop stage (fewer families and skeletons), but not yet
end to end: with native inputs at $B = 128$ it is slower than full colour for
#names(lc-slower) (@tab:g1lc).
]

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
    inset: (x: 3.5pt, y: 2.6pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][Work, MCMAC/pt][Dressing, ms][G CMAC/s][Native loop, ms][Outside, ms][Total, ms][Total ÷ recipe][NinjaRS ÷ R],
    ..rc.map(r => {
      let p = gproc(r.process)
      let x = bat(nat-c(p), str(r.batch))
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
#let outer-fc = rc.map(r => r.outer_factor).filter(v => v != none)
*Recalibration.* The kernels run #fixed(calc.min(..rates), 2)–#fixed(calc.max(..rates), 2)
G complex MAC/s per core on the real plans, the rate gate G0 measured on its
synthetic programs (1.29–1.37); the dressing term of the recipe holds. The
NinjaRS stage, masters included, lands on the design's model R (measured ÷ R
#fixed(calc.min(..rc.filter(r => r.at("design", default: none) != none).map(r => r.design.reduction_over_model.at(0))), 2)–#fixed(calc.max(..rc.filter(r => r.at("design", default: none) != none).map(r => r.design.reduction_over_model.at(1))), 2),
@tab:g1rate). What the recipe misses is the *outer factor*: it assumed trees,
seeds and counterterms add 5–10 % (DESIGN §1.3), but with the current native
inputs the total is #fixed(calc.min(..outer-fc), 2)–#fixed(calc.max(..outer-fc), 1)
times dressing plus reduction at full colour (up to
#fixed(calc.max(..g.recalibration.filter(r => r.configuration == "native/lc").map(r => r.outer_factor)), 0)
at LC). @tab:g1est re-estimates every design row with these measured terms.

#let est-band(b) = box[#sig(1000 * b.at(0))–#sig(1000 * b.at(1))]
#figure(kind: table,
  caption: [*Design estimates recalibrated by G1*
    (#raw("tools/loop_v2_costmodel.py --g1")), ms per point, finite only, one thread. Recipe: DESIGN Table 1a's
    finite-only band (outer factor 1.05–1.10). G1: the recipe's dressing term,
    the NinjaRS model R × #fixed(0.97, 2)–#fixed(1.39, 2) (the band of the first G1 campaign, a constant of
    the tool; this campaign measures #fixed(calc.min(..rc.filter(r => r.at("design", default: none) != none).map(r => r.design.reduction_over_model.at(0))), 2)–#fixed(calc.max(..rc.filter(r => r.at("design", default: none) != none).map(r => r.design.reduction_over_model.at(1))), 2), @tab:g1rate) and
    the measured outer factor of the row's class representative at $B = 128$
    with native inputs (same colour where measured#if g.estimates.any(e => e.outer_inferred) [; rows whose class
    was not measured at their colour take the FC factor, marked †]). Measured: G1's own time where the row
    was timed. Gate: 1.3× the best production provider of DESIGN Table 1b
    (seven-leg rows, protocol of 20 October), with the headroom gate ÷ upper
    estimate. The outer factor shrinks with compiled trees (@tab:levers);
    until then these replace the Table 1a targets.],
  tstyle(table(
    columns: (2.7cm, 0.7cm, 1fr, 0.9cm, 2.4cm, 1.45fr, 0.8fr, 0.8fr, 0.8fr),
    align: (x, y) => if x < 2 or x == 4 { left + horizon } else { right + horizon },
    inset: (x: 3.5pt, y: 2.4pt), stroke: tstroke, fill: thead-fill,
    table.header[Design row][Col.][Recipe][Outer][Class][G1 estimate][Measured][Gate][Headroom],
    ..g.estimates.map(e => (
      text(8.2pt, font: "Libertinus Serif", math-label(e.label.split(" ").map(tok).join(" "))),
      e.colour,
      est-band(e.recipe_finite_only),
      [#fixed(e.outer_factor, 2)#if e.outer_inferred [†]], text(7pt, font: "Libertinus Serif", math-label(gproc(e.outer_class).label.split(" ").map(tok).join(" "))),
      text(weight: "bold", est-band(e.estimate)),
      if e.measured == none { dim[—] } else { msec(e.measured) },
      if e.gate == none { dim[—] } else { msec(e.gate) },
      if e.headroom == none { dim[—] } else { fixed(e.headroom, 2) },
    )).flatten(),
  )),
) <tab:g1est>

#let sched-rows = g.processes.map(p => p.schedules.map(s => (p: p, s: s))).flatten()
#let m-revs = (revs-of(p => cfg(p, "native/full/M")) + revs-of(p => cfg(p, "native/lc/M"))).dedup()
#let ratio-cell(x, field) = if x == none [—] else { fixed(x.at(field), 2) }
#block(breakable: false)[#figure(kind: table,
  caption: [*Schedule M against B* (native inputs, one thread), pure-gluon
    classes, the only classes where M merges seed entries (DESIGN §5.6). The
    schedule-dependent stages are seeds, factors, dressing, scatter and the
    NinjaRS reduction ("the reduction included", §1.6 item 5); the trees,
    Born and counterterm inputs and the glue are the same work in both
    schedules. M: the development campaign's runs (#rev-list(m-revs), not
    repeated); B: the configuration on `loop` (#raw(g.slice_revision)), a later
    engine (native tree closures and plane applications, frozen setup heap) on
    the same processes, so the ratios pair runs of different builds and
    campaigns (the gate tool pairs them; history for M): end to end at
    $B = 128$ they set the M time with the older, slower trees against this
    engine's B time and do not measure M; LC was re-timed at $B = 128$ only. M is adopted where M/B ≤ 0.85 on the schedule-dependent
    stages at every common batch size; ± is the timing uncertainty of the
    ratio.],
  tstyle(table(
    columns: (2.9cm, 0.9cm, 1fr, 1fr, 1fr, 1fr, 1.4cm),
    align: (x, y) => if x < 2 { left + horizon } else { right + horizon },
    inset: (x: 4pt, y: 2.7pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][Col.][Stages M/B, $B = 1$][Stages M/B, $B = 128$][End to end, $B = 1$][End to end, $B = 128$][Adopt M],
    ..sched-rows.map(r => {
      let (one, many) = (r.s.batches.at("1", default: none), r.s.batches.at(big, default: none))
      (gname(r.p.key), if r.s.accuracy == "full" [FC] else [LC],
        if one == none [—] else [#text(weight: "bold", fixed(one.schedule_stages_ratio, 2)) #tiny[± #fixed(one.uncertainty, 2)]],
        if many == none [—] else [#text(weight: "bold", fixed(many.schedule_stages_ratio, 2)) #tiny[± #fixed(many.uncertainty, 2)]],
        ratio-cell(one, "total_ratio"), ratio-cell(many, "total_ratio"),
        if r.s.adopt_m { text(fill: rgb("#2166ac"), weight: "bold")[yes] } else [no])
    }).flatten(),
  )),
) <tab:g1bm>]

#let adopted = sched-rows.filter(r => r.s.adopt_m)
#let not-adopted = sched-rows.filter(r => not r.s.adopt_m)
#let stage-range(r) = { let v = r.s.batches.values().map(x => x.schedule_stages_ratio).sorted(); if v.len() == 1 { fixed(v.first(), 2) } else [#fixed(v.first(), 2)–#fixed(v.last(), 2)] }
#let col-word(r) = if r.s.accuracy == "full" [FC] else [LC]
*B against M (decision, provisional until the trees are compiled).* On the
schedule-dependent stages M passes the 15 % rule for
#if adopted.len() == 0 [no row] else { adopted.map(r => [#gname(r.p.key) at #col-word(r) (#stage-range(r)\; DESIGN §5.6 measured 0.75–0.80 on the dressing side)]).join([, ]) },
and not for
#not-adopted.map(r => [#gname(r.p.key) at #col-word(r) (#stage-range(r))]).join([, ], last: [ and ]).
The same rows qualify as in the development campaign's paired runs, on which
the decision was made (`data/g1.json` of `c3a7be09`). End to end the gain is diluted by
the tree inputs, which both schedules share and which compiled trees will
shrink (@tab:levers). With a quark line M's entries do not merge at all (M/B
work 1.00, DESIGN §5.6; equal by test). *Decision (G1):* schedule M for
pure-gluon classes at leading colour from $n = 6$; schedule B for every other
class at $n <= 6$, including pure-gluon full colour; M stays the planned
default from $n >= 8$, and both are re-measured at seven legs with the WP3.1
plans (`measure-g1-7leg`).

#let stab-revs = g.processes.map(p => p.stability.map(r => r.at("revision", default: none))).flatten().filter(r => r != none).map(r => r.slice(0, 8)).dedup()
#let dd-row(p, i) = p.stability.find(r => r.index == i and r.arithmetic == "double-double" and r.configuration == "native/full")
#let b64-row(p, i) = p.stability.find(r => r.index == i and r.arithmetic == "double" and r.configuration == "native/full")
#let best-dev(r) = if r == none or r.deviation_vs_providers.len() == 0 { none } else { r.deviation_vs_providers.pairs().sorted(key: ((n, v)) => v).first() }
#let camp-cell(c) = { let acc = if c == none { none } else { c.at("accuracy_check", default: none) }; if acc == none { dim[—] } else [#sci(acc.max_error) #if not acc.passed [#linebreak() #text(fill: amber, weight: "bold", tiny[above #sci(acc.tolerance)])]] }
#figure(kind: table,
  caption: [*Values at the timed points*: pyAmpliCol's binary64 finite part
    (native inputs on `loop`) against each provider's production-mode value on the
    common stream points (the providers read the binary64 decimal text of the
    exact points), largest deviation, metric
    $|a - b| slash max(|a|, |b|, |B| alpha_s slash 2 pi)$; Recola's finite part
    converted with the universal double pole (it returns no poles in
    production). Worst point: the point of the row's largest deviation,
    evaluated again with one rotation and the reduction-direction check in
    binary64 and in double-double (DD)#if stab-revs.any(r => r != g.slice_revision.slice(0, 8)) [ by the stability runs of
    #rev-list(stab-revs), not repeated (their binary64 values equal the timed ones to rounding level, more at
    binary64-unstable points)]: $E$ is the binary64 estimate, DD
    the DD value's deviation from the closest provider (named). Campaign: the
    first three points against the committed references
    (`tests/fixtures/loop/required`), fixture metric and tolerance, native
    inputs (`loop`) and Python inputs (history).],
  tstyle(table(
    columns: (2.7cm, 0.65cm, 1fr, 1fr, 1fr, 1.25fr, 1.45fr, 1fr, 1fr),
    align: (x, y) => if x == 0 { left + horizon } else { right + horizon },
    inset: (x: 3.5pt, y: 2.6pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][Pts][vs MadLoop][vs Recola][vs OpenLoops][Worst point: $E$][DD: closest provider][Campaign, native][Campaign, Python#super[hist]],
    ..g.processes.map(p => {
      let c = nat-c(p)
      let v = if c == none { none } else { c.values_vs_providers }
      let cell(n) = if v == none or v.at(n, default: none) == none { if prov(p, n) != none and "unavailable" in prov(p, n) { dim[no library] } else [—] } else { sci(v.at(n).max_finite_deviation) }
      let pts = if v == none or v.len() == 0 { 0 } else { calc.max(..v.values().map(x => x.points)) }
      let worst = if v == none or v.len() == 0 { none } else { v.values().sorted(key: x => x.max_finite_deviation).last() }
      let wi = if worst == none { none } else { worst.worst_point }
      let st = if wi == none { none } else { b64-row(p, wi) }
      let dd = if wi == none { none } else { best-dev(dd-row(p, wi)) }
      (gname(p.key), str(pts), cell("madloop"), cell("recola"), cell("openloops"),
        if st == none { dim[—] } else [#tiny[pt #st.index:] #sci(st.estimate)],
        if dd == none { dim[—] } else [#sci(dd.at(1)) #tiny[#pshort(dd.at(0))]],
        camp-cell(c), camp-cell(py-c(p)))
    }).flatten(),
  )),
) <tab:g1values>

#let all-born = g.processes.map(p => { let c = nat-c(p); if c == none or c.values_vs_providers == none { () } else { c.values_vs_providers.values().map(x => x.max_born_deviation) } }).flatten()
#let dd-rows = g.processes.map(p => p.stability.filter(r => r.arithmetic == "double-double").map(r => (p: p, r: r))).flatten()
#let dd-best = dd-rows.map(x => best-dev(x.r)).filter(x => x != none).map(x => x.at(1))
#let dd-of(key, i, n) = { let r = dd-row(gproc(key), i); if r == none { none } else { r.deviation_vs_providers.at(n, default: none) } }
#let ml-dd = dd-rows.map(x => x.r.deviation_vs_providers.at("madloop", default: 0)).filter(v => v > 1e-9)
#let gg4 = gproc("gg_gggg")
*Reading the values.* The Born agrees with every provider to
#sci(calc.max(..all-born)) or better. For the finite part, the double-double
(DD) value at each worst point (@tab:g1values) separates the sources: it
agrees with the closest provider to #sci(calc.max(..dd-best)) or better
everywhere. Where pyAmpliCol's binary64 estimate $E$ exceeds the deviation —
$g g -> g g g$, $g g -> g g g g$ and $g g -> t overline(t) g g$ (above
10⁻⁹) and $u overline(u) -> g g g g$ (#sci(dd-row(gproc("uux_gggg"), 9).deviation_vs_providers.openloops) in DD
against #sci(nat-c(gproc("uux_gggg")).values_vs_providers.openloops.max_finite_deviation) in binary64 at point #nat-c(gproc("uux_gggg")).values_vs_providers.openloops.worst_point) — the deviation is pyAmpliCol's own binary64
loss, which $E$ flags. The other deviations above 10⁻¹¹ stay in DD and are
the providers' own accuracy: Recola's at $u overline(u) -> d overline(d) g$
(#sci(dd-of("uux_ddxg", 1, "recola"))), $u overline(u) -> u overline(u) g$ and
$u overline(u) -> e^- e^+ g g$ (COLLIER's default target $10^(-8)$, HANDOFF
§7), OpenLoops' at $u overline(u) -> g g g$ (#sci(dd-of("uux_ggg", 2, "openloops"))) and MadLoop's at
$u overline(u) -> e^- e^+ g g$ (#sci(dd-of("uux_emepgg", 8, "madloop"))); MadLoop's production values also stay
off the DD values at the ill-conditioned gluon and top points (up to
#sci(calc.max(..ml-dd))). At the campaign points $g g -> g g g g$ point 1
misses the fixture tolerance (#sci(nat-c(gg4).accuracy_check.tolerance, d: 0)) in binary64 on both paths, within
its estimate $E$ = #sci(b64-row(gg4, 1).estimate)\; its DD value agrees with
Recola to #sci(dd-of("gg_gggg", 1, "recola")).

// ============================================================= REQUIRED ==
= Required processes: references and development validation <required>

The plan requires the $2 -> 5$ processes of @tab:summary (plan §5.7), compared
with MadLoop and Recola, and with OpenLoops where a public library exists. A
reference provider is run only if its generation completes in about 45 minutes,
or in a time comparable to pyAmpliCol's own generation of the process (HANDOFF
§0.1, addendum F). Otherwise pyAmpliCol is validated by Ward and gauge
identities, Catani poles, LC/NLC/FC and DD/AP consistency, stability checks,
lower multiplicities and existing references.

// Provider generation records of every row of Table 1 (data/summary.json:
// g1.json for the G1 rows, measured.json for the seven-leg rows): the rows
// with a provider generation over 45 minutes or unfinished, then the others.
#let rule-s = 2700
#let s-rows = S.groups.map(g => g.rows).flatten()
#let gen-times(r) = r.generation.providers.pairs().filter(((k, x)) => x != none and "seconds" in x)
#let over-rule(r) = gen-times(r).any(((k, x)) => x.seconds > rule-s) or r.generation.at("unfinished", default: (:)).keys().filter(k => k != "note").len() > 0
#let pg-rows = s-rows.filter(over-rule)
#let pg-rest = s-rows.filter(r => not over-rule(r))
#let pg-longest = pg-rest.map(r => gen-times(r).map(((k, x)) => (r: r, k: k, s: x.seconds))).flatten().sorted(key: x => x.s).last()
#let pg-dur(s) = if s >= 3600 [#fixed(s / 3600, 1) h] else { dur(s) }
#let pg-ml(r) = {
  let x = r.generation.providers.madloop
  let u = r.generation.at("unfinished", default: (:)).at("madloop", default: none)
  if x != none and "seconds" in x [#pg-dur(x.seconds) #tiny[(#group(int(calc.round(x.graph_s))) + #group(int(calc.round(x.export_s))) + #group(int(calc.round(x.compile_s))) s)]]
  else if u != none [diagrams #pg-dur(u.graph_generation_s)\; unfinished #tiny[(last state: #u.status)]]
  else { dim[not exported] }
}
#let pg-rc(r) = {
  let x = r.generation.providers.recola
  let u = r.generation.at("unfinished", default: (:)).at("recola", default: none)
  if x != none and "seconds" in x { pg-dur(x.seconds) } else if u != none [unfinished #tiny[(last state: #u.status, #u.since.slice(0, 10))]] else { dim[—] }
}
#let pg-ol(r) = { let x = r.generation.providers.openloops; if x == none [no public library] else [prebuilt #x.prebuilt] }
#let pg-rule(r) = {
  let u = r.generation.at("unfinished", default: (:))
  let over = gen-times(r).filter(((k, x)) => x.seconds > rule-s).map(((k, x)) => pshort(k))
  text(weight: "semibold", fill: amber, if u.at("note", default: none) != none [#u.note] else if over.len() > 0 [#over.join(", ") over 45 min; results exist and are used] else [unfinished])
}
#block(breakable: false)[#figure(kind: table,
  caption: [*Provider generation on this host and the 45-minute rule* (HANDOFF §0.1): the rows of @tab:summary where a
    provider generation takes more than 45 minutes or did not finish. MadLoop: graph generation + source export + compilation;
    Recola: process generation; OpenLoops: prebuilt public libraries (no generation time). Records: `data/g1.json` (G1 rows)
    and `data/measured.json` (`provider_generation`, the reference runs of the $2 -> 5$ rows), through `data/summary.json`.
    Every other row of @tab:summary generates within 45 minutes with every provider (longest:
    #pshort(pg-longest.k) #dur(pg-longest.s) for #math-label(pg-longest.r.math)#if pg-longest.r.corrections != "QCD" [ (#pg-longest.r.corrections)]).],
  tstyle(table(
    columns: (2.9cm, 4.1cm, 3.0cm, 2.0cm, 1fr),
    align: left + horizon, inset: (x: 4pt, y: 3.1pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][MadLoop][Recola][OpenLoops][45-minute rule],
    ..pg-rows.map(r => (text(8.4pt, font: "Libertinus Serif", math-label(r.math)), pg-ml(r), pg-rc(r), pg-ol(r), pg-rule(r))).flatten(),
  )),
) <tab:provgen>]

#let rn = meas.required_native
#let coeff = ("born", "finite", "single_pole", "double_pole")
#let rn-max(rec, k) = { let v = rec.max_deviation.values().filter(d => k in d).map(d => d.at(k)); if v.len() == 0 { none } else { calc.max(..v) } }
#let rn-refs(rec) = rec.max_deviation.keys().map(k => (madloop: "ML", recola: "Rc", openloops: "OL", njet_dd_oneloop_R1: "NJet DD", njet_double_R1: "NJet R1", njet_double_R2: "NJet R2", catani: "Catani").at(k, default: k)).join(", ")
#let rn-label(key) = { let r = S.groups.map(g => g.rows).flatten().find(r => r.key == key); math-label(r.math) + if key.ends-with("_qcd") [ (QCD)] }
// The records of this table's rows (the newest per process), each with its
// revision, the generation threads its increment states and its rows.
#let rn-records-text = rn.processes.values().map(x => x.record).dedup().map(rec => {
  let x = rn.processes.values().find(y => y.record == rec)
  [#inc-name(rec) increment (#raw(x.revision)\; #C.development_records.threads.at(x.revision, default: "threads not recorded")) for #rn.processes.pairs().filter(((k, y)) => y.record == rec).map(((k, y)) => box(rn-label(k))).join([, ])]
}).join([\; ])
#block(breakable: false)[#figure(kind: table,
  caption: [*Native validation of the required set* #dev-tag (#raw(rn.branch)#if rec-integrated != none [ before its integration into `loop` at #raw(rec-integrated)], DESIGN WP3.1: #rn-records-text): generation
    (`LoopSlice.generate`, then the plan export; peaks of each stage; #C.development_records.conditions_short), then binary64 virtuals with native per-point inputs and
    the production counterterm route at the fixture points, against the references committed on that branch
    (`tests/fixtures/loop/required`; fixture tolerance #sci(rn.processes.values().first().tolerance, d: 0)). Largest deviation
    over the references and points, metric of @tab:summary; the per-reference values are in `data/measured.json`. For
    $g g -> g g g g g$ the references are NJet (double-double and two binary64 runs) and the Catani operator for the poles,
    top-free with $N_f = 5$; its estimate column is the rotation plus reduction-direction check per point.],
  tstyle(table(
    columns: (3.1cm, 2.3cm, 1fr, 1fr, 1fr, 1fr, 2.3cm, 2.4cm),
    align: (x, y) => if x < 2 { left + horizon } else { right + horizon },
    inset: (x: 3.5pt, y: 3pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][References][Born][Finite][$1 slash epsilon$][$1 slash epsilon^2$][Estimate $E$][Generation + export],
    ..rn.processes.pairs().map(((key, rec)) => (
      text(8.4pt, font: "Libertinus Serif", rn-label(key)),
      tiny[#rn-refs(rec) · #rec.points.len() #if rec.points.len() == 1 [pt] else [pts]],
      ..coeff.map(k => sci(rn-max(rec, k))),
      if rec.stability_estimate_per_point.all(e => e != none) { rec.stability_estimate_per_point.map(e => sci(e)).join(", ") } else { dim[—] },
      [#dur(rec.generate_s + rec.export_s) #tiny[#fixed(calc.max(rec.generate_peak_gib, rec.export_peak_gib), 1) GiB]],
    )).flatten(),
  )),
) <tab:validation>]

#let ttq = rn.processes.gg_ttxemepg_qcd
#let ttq-old = ms.required.rows.find(r => r.label.starts-with("g g -> t overline(t) e^- e^+ g") and r.at("corr", default: none) == "QCD")
#let ttq-errs = ttq.max_error_per_point.sorted()
The $g g -> t overline(t) e^- e^+ g$ (QCD) finite part deviates by #sci(ttq-errs.last()) at one of its three points and by at
most #sci(ttq-errs.at(-2)) at the others: the point's known binary64 conditioning (earlier record, DESIGN WP3.1 fourth
increment: #ttq-old.validation). The electroweak target is in development (WP3.2: EW guards, the QED Catani operator
and EW fermion lines are on `loop`; the UFO's EW counterterms and massive vector bosons in Feynman gauge are not). The $u overline(u) -> g g g g g$ row comes
from #rn.processes.uux_ggggg.record.split(",").first(), the newest record of that process: the later re-runs on the merged
heads (eighth and ninth increments) do not include it. It uses the same production counterterm route; its check is in @tab:sevencheck.

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
#sig(meas.njet_single_evaluation.standard.mean_s) s (standard) and
#sig(meas.njet_single_evaluation.desymmetrised.mean_s) s (de-symmetrised; means over #meas.njet_single_evaluation.standard.points points), at #ms.njet.rss_mb MB;
double-double costs #group(ms.njet.double_double_s) s per point. NJet 3.1.2's
numerical five-gluon channel is 9/2 too large (NJet 2.1.1 is used there), and at
the unrotated seven-gluon points NJet keeps only 4–6 digits in double precision
(NaN at 3 of 10), so the reference values are taken at exactly rotated points.

== pyAmpliCol at seven gluons #dev-tag

#let g7 = rn.processes.gg_ggggg
#let g7-dd = g7.max_deviation.njet_dd_oneloop_R1
// An earlier record with more points (measured.json required_native
// superseded), cited beside the newest one.
#let g7-old = rn.at("superseded", default: (:)).at("gg_ggggg", default: none)
#let pts-word(n) = if n == 1 [point] else [points]
// The comparison Table 1 keeps (VALIDATION_RULE of scripts/build_summary.py):
// the newest record, or the older, more complete one it only repeats part of.
#let g7-row = all-rows.find(r => r.key == "gg_ggggg")
#let g7v = (g7, ..if g7-old != none { (g7-old,) } else { () }).find(x => x.revision == g7-row.validation.revision)
#let g7v-dd = g7v.max_deviation.njet_dd_oneloop_R1
#let g7v-within = g7v.stability_estimate_per_point.zip(g7v.max_error_per_point).all(((e, d)) => e != none and e >= d)
// The newest record's deviations at the points it re-ran, against the kept ones.
#let g7-same = g7.points.enumerate().all(((i, q)) => q in g7v.points and g7.max_error_per_point.at(i) == g7v.max_error_per_point.at(g7v.points.position(x => x == q)))
On the WP3.1 branch#if rec-integrated != none [ before its integration (G-int\; @tab:validation)] else [ (@tab:validation)] the full $g g -> g g g g g$ virtual, with the counterterms of the recursion and native
per-point inputs, top-free with $N_f = 5$, agrees with NJet's double-double values to #sci(g7v-dd.finite) in the finite part
(per point: #g7v.max_error_per_point.map(e => sci(e)).join(", ") over all references, #pts-word(g7v.points.len()) #g7v.points.map(str).join(", "), #inc-name(g7v.record) increment) and to #sci(g7v-dd.double_pole) in the
double pole; #if g7v-within [each point's rotation plus reduction-direction estimate bounds its difference] else [estimates #g7v.stability_estimate_per_point.map(e => if e == none [—] else { sci(e) }).join(", ")].#if g7v != g7 [ The
#inc-name(g7.record) increment re-ran #pts-word(g7.points.len()) #g7.points.map(str).join(", ")#if g7-same [ with equal deviations]\; @tab:summary keeps the more complete comparison.] Generation (#inc-name(g7.record) increment) took
#minutes(g7.generate_s) at #fixed(g7.generate_peak_gib, 1) GiB and the plan export #minutes(g7.export_s) at
#fixed(g7.export_peak_gib, 1) GiB (peak RSS of each stage; #sig(g7.plan_json_mb) MB of plan JSON; the whole validation run, point
evaluations included, peaked at #fixed(g7.max_rss_gib, 1) GiB), inside
addendum H's budget (hours, below 150 GB). DESIGN WP3.1 attributes the cost: 325 s before the counterterm recursion,
1,122 s with its counterterm program, 2,766 s once poles-uvir's always-generated companion merged (eighth increment), and
2,652 s after the ct-simplify merge (ninth increment, this record), 1,843 s of it the companion's seed table, which builds
generic seeds (making it lean is open). A point with its rotation and reduction-direction checks took
#g7.seconds_per_point_unbatched.map(t => sig(t)).join(", ") s, a single-point development evaluation (#C.development_records.threads.at(g7.revision, default: "threads not recorded")):
not a batched one-thread time and not comparable with NJet's
#sig(meas.njet_single_evaluation.standard.mean_s) s per evaluation on one pinned core. No batched seven-gluon timing exists yet.

== Validation without a matched provider

#let nv = ms.njet_validation
#let uxr = rn.processes.uux_ggggg
#let ux = uxr.max_deviation
#let ux-agree = meas.provider_generation.processes.uux_ggggg.reference.maximum_provider_relative_error
#let g7-cat = g7v.max_deviation.catani
#block(breakable: false)[#figure(kind: table,
  caption: [*Checks of the seven-leg QCD results*, #dev-tag on `work/v2-generation-scale`, except the Ward row (WP2.5 on
    `loop`); binary64, all three Laurent coefficients, deviation metric of @tab:summary. NJet values: fixture
    `gg_ggggg_njet.json` (NJet 3.1.2 double-double at exactly rotated points, scaling-test estimates ≤ #sci(1.3e-24)).],
  tstyle(table(
    columns: (4.4cm, 1fr, 2.9cm),
    align: left + horizon, inset: (x: 4pt, y: 2.8pt), stroke: tstroke, fill: thead-fill,
    table.header[Check][Result][Status],
    [$g g -> g g g g g$ full virtual against NJet (top-free, $N_f = 5$), #g7v.points.len() #pts-word(g7v.points.len()) (#inc-name(g7v.record) increment#if g7v != g7 [\; #inc-name(g7.record): #pts-word(g7.points.len()) #g7.points.map(str).join(", ")])],
    [Born ≤ #sci(g7v-dd.born), finite ≤ #sci(g7v-dd.finite), single pole ≤ #sci(g7v-dd.single_pole), double pole ≤ #sci(g7v-dd.double_pole)\;
      Catani poles: single ≤ #sci(g7-cat.single_pole), double ≤ #sci(g7-cat.double_pole)\; estimates #g7v.stability_estimate_per_point.map(e => sci(e)).join(", ")],
    [#if g7v.passed [passed] else [failed] (tolerance #sci(g7v.tolerance, d: 0))],
    [Top-free full virtual against NJet at lower multiplicity],
    [#nv.topfree.lower.map(l => [#math-label(l.label): #l.value]).join([; ]) (`test_loop_v2_topfree.py`)],
    [passed],
    [$u overline(u) -> g g g g g$ full virtual against MadLoop and Recola, #uxr.points.len() points (#uxr.record.split(",").first())],
    [MadLoop ≤ #sci(calc.max(..ux.madloop.values())), Recola ≤ #sci(calc.max(..ux.recola.values())) (finite ≤ #sci(ux.recola.finite)); the providers agree to #sci(ux-agree) (reference merge)],
    [#if uxr.passed [passed] else [failed] (tolerance #sci(uxr.tolerance, d: 0))],
    [Ward identity, one gluon's $epsilon -> p$, at seven gluons],
    [asymmetric Ward mode of WP2.5 (loop side only, bare + UV + $R_2$); passes on $g g -> g g$ and $u overline(u) -> g g g$ (`test_loop_v2_observables.py`)],
    text(fill: rgb("#8a4b08"), weight: "semibold")[not yet run at seven gluons (addendum H)],
  )),
) <tab:sevencheck>]

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
  ([Full, NLC and LC colour], "supported", [Exact seed tables in $N_c$; LC/NLC by generated classes and truncated cells. #if lc-slower.len() == 0 [Since lc-perf LC is faster than full colour end to end on every G1 row at $B = 128$ (LC/FC #fixed(lc-now.first().r, 2)–#fixed(lc-now.last().r, 2), @tab:g1lc); not cheaper to generate at seven legs (not re-measured since).] else [LC is cheaper in the loop stage but not yet end to end at large batches (@tab:g1lc), nor to generate at seven legs.]]),
  ([Colour and spin correlations], "supported", [Directed colour histories at LC/NLC/FC, spin sources, resolved helicities, flavour aliases, Ward sources (WP2.5). Seven-leg directed LC/NLC tables need the Rust seed tables (WP3.1).]),
  ([Per-order partials], "supported", [Every squared coupling order at tree level and at one loop, mixed Born orders, per-correction loop orders.]),
  ([Poles at runtime], "supported", [`poles = "all" | "none" | "uv" | "ir" | "split"` (WP2.10, on `loop` since 24 October): finite-only mode with the finite part bitwise unchanged and the pole work skipped; `"uv"` and `"ir"` with the user's semantics of 23 October; the IR poles sum one Catani operator per correction, QED included (ew-poles, `8b52179b`; a correction without a prediction gives none; the prediction for mixed QCD×EW sectors is still misleading, about 2 % in the single pole, open in WP3.2). The UV residue comes from an interim local module until the NinjaRS re-pin; a `"uv"` estimate needs a rotation check.]),
  ([Stability estimates], "supported", [Rotation checks (any number, 0 = estimate absent), reduction direction, exact rescaling, in any combination; no automatic escalation (WP2.3).]),
  ([Precision carriers], "supported", [Binary64, DoubleFloat, arbitrary precision and exact rationals in the native executor; since G-int the native per-point inputs run in binary64, DoubleFloat and arbitrary precision (DESIGN §5.5). Since `7db32901` binary64 runs SymJIT plane applications and needs no Symbolica licence; DoubleFloat and arbitrary precision run under pyAmpliCol's library key.]),
  ([Native executor, schedules], "supported", [Rust, 16 lanes (also for a one-point call, a G1 lever), threads; native tree closures in lanes of points with runtime AVX-512/AVX2 widths (lc-perf); G1 decision on the schedule-dependent stages (@tab:g1bm, provisional until compiled trees): M for pure-gluon LC from $n = 6$, B for every other class at $n <= 6$; F as oracle. The NinjaRS reduction runs serially. Development report: stage times, modelled kernel work, master-integral time.]),
  ([Plan v4 artifacts and API], "partial", [Published and loaded through Python, TOML and CLI; the artifact stores the native process (`point_inputs = "native-v2"`): a plain evaluation loads without any generation call. Since `7db32901` (addendum G) its SymJIT -O2 applications are stored as IR and recompiled at load for the loading CPU (AVX and FMA3 required), no host string is embedded, and binary64 values are bitwise equal after relocation to another machine, user and path; the parameter program's SymJIT bytes differ per compilation (a random external-call tag, values unaffected; upstream fix filed). Correlated, resolved and flavour calls and the `"uv"`/`"ir"` selections still regenerate the slice on first use, and processes the native export refuses keep `regenerated-at-load` (generation-scale-2). The Rust/C/C++/Fortran SDK refuses v4 until then.]),
  ([Counterterms (model UV, $R_2$)], "supported", [Plain tree vertices of the recursion inserted exactly once (WP2.2, a18b7599; addendum J, b4d76cc3), admitted by coupling orders and the public `particle_veto`; no witness table or loop matching in production. An unlowerable counterterm vertex that no tree of the request reaches is inert and recorded in the artifact; a reachable one is refused. Site closure is the test oracle. Per point they are formed natively (G-int), the Python stages kept as oracle; generation of the counterterm route has output-identical savings (ct-perf, `201bece5`: compile memos, a content-addressed lowered-model cache); the native counterterm-program builder (A3) is on `loop`, not switched on (A4 in development). EW counterterms of the UFO: `ew-ct`, in development.]),
  ([Direct $R_2$], "deferred", [A bonus by the user's rule; bounded controls only.]),
  ([Electroweak, complex mass], "progress", [WP3.2. On `loop`: typed refusals of EW requests with a non-zero width or an external photon (until the complex-mass scheme and $alpha(0)$ per photon); the QED Catani operator (`8b52179b`); EW fermion lines (`1d27426b`): Dirac–Weyl EW vertices, $W$ vertices along the fermion flow, conjugate readings, lepton- and colour-singlet-rooted processes, mixed-order Born with $W$ exchange, the sites oracle equal to the recursion at $W$ vertices; more than one colour-singlet fermion line refused until EWI-5. In development: the UFO's EW counterterms (`ew-ct`), massive vector bosons and Goldstones in Feynman gauge (`ew-gauge`); CMS later.]),
  ([Required set], "progress", [Seven of eight generate and agree with their references in all coefficients with native inputs (@tab:validation, validated on the WP3.1 branch before its integration), $g g -> g g g g g$ against NJet's double-double values; the generator is on `loop` since G-int. The EW target is in development (WP3.2); no batched $2 -> 5$ timing (`measure-g1-7leg`).]),
  ([Performance gates], "progress", [G1 on `loop` (@g1, native per-point inputs, #raw(g.slice_revision)) at $B = 128$: #nat-pass.len() of #nat-gated.len() gated processes pass#if nat-decided.len() > 0 [ (#names(nat-decided) by user decision, #nat-decided.map(p => decision(p, big, bat(nat-c(p), big).gate).label.replace("user decision ", "")).join([, ]))]#if nat-open.len() > 0 [, #names(nat-open) open]#if nat-fail.len() > 0 [, #names(nat-fail) #if nat-fail.len() == 1 [fails] else [fail]]#if nat-ungated.len() > 0 [; #nat-ungated.len() below 5 ms per point are not gated (user, 2026-10-24)]\; $B = 1$ needs lane adaptation (@tab:g1batch). The Python per-point inputs before G-int failed every gate they generated (history). Missing: provider protocol-mode columns, seven legs (`measure-g1-7leg`).]),
  ([$g g -> 6g$], "deferred", [No $2 -> 6$ work until the $2 -> 5$ plan is complete (user, 23 October).]),
)
#figure(kind: table,
  caption: [*Capability matrix* of the v2 engine on `loop` at #ms.engine_revision, with branch work marked.],
  tstyle(table(
    columns: (3.2cm, 1.75cm, 1fr), align: (x, y) => if x == 1 { center + horizon } else { left + horizon },
    inset: (x: 4.5pt, y: 2.2pt), stroke: tstroke, fill: thead-fill,
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
    batched numerics in the Rust executor (the per-point inputs since G-int);
    orange: Python per batch; white: generation. The owning
    code or dependency is named under each step.],
  grid(columns: (0.45cm, 1fr, 8pt, 1fr, 8pt, 1fr, 8pt, 1fr, 8pt, 1fr, 8pt, 1fr), row-gutter: 6pt, column-gutter: 1pt,
    lane[generation],
    stage-box([Loop kernel catalogue], [UFO loader, Symbolica, Idenso], "plain"), arr,
    stage-box([Tree blocks in loop mode], [tree engine: all-subset currents, Born], "plain"), arr,
    stage-box([Families by loop-prefix recursion], [pyAmpliCol; native in Rust], "plain"), arr,
    stage-box([Skeleton tries B, merged graph M], [pyAmpliCol, rusticol-core], "plain"), arr,
    stage-box([Exact seed tables $K[c,b]$], [colour flow, Laurent in $N_c$], "plain"), arr,
    stage-box([Counterterm program; plan v4], [CT recursion; native builder A3 (off)], "plain"),
    lane[evaluation],
    stage-box([Exact inputs, invariant table], [Rust executor], "nat"), arr,
    stage-box([Blocks, Born, CT scalars], [Rust executor, SymJIT planes; Python as oracle], "nat"), arr,
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
    [Role], [oracle], [default; generic fallback], [pure-gluon LC from $n = 6$ (G1); planned default from $n >= 8$],
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
On `loop` the counterterms come from the WP2.2 recursion (one counterterm
order in the tree recursion, the default route, whose $g g -> g g g g g$
program leaves no rule to site closure) with this admission
(`ct-simplify`, b4d76cc3): no witness table and no loop matching. A
counterterm vertex that the model cannot lower and that no tree of the request
reaches (the tree engine's own reachability, with the program's order limits
and `particle_veto`) is inert and recorded in the artifact; a reachable one is
refused. `particle_veto = [t]` replaces the internal top-free switch of
@tab:sevencheck; site closure and the witness machinery remain only as test
oracles.

*Precision, stability and assembly.* Every kernel is generic over binary64,
DoubleFloat, arbitrary-precision floats and exact rationals. A failed lane
fails its point and never branches a kernel. The assembly takes
$2 op("Re")$ of $i slash (16 pi^2)$ times the reduced family sum, plus local UV, $R_2$ and
field terms, per sector and column, with optional rotation, reduction-direction and rescaling estimates
and the finite-only mode. The public API selects `loop_engine = "v2"` from
TOML, CLI or Python and stores plan v4 as a relocatable PACBIN member (zlib
JSON of exact kernel term lists, no compiled code, digest checked at load) and
the native process (`point_inputs = "native-v2"`: the tree program with the
Born, counterterm and field components, their saved exact evaluators and the
binary64 SymJIT applications of every tree kernel and of the parameter
program, stored as IR and recompiled at load), so a plain evaluation loads
without regenerating the process, on another machine, user and path too.

#block(breakable: false)[#figure(kind: table,
  caption: [*Asymptotic classes per event* for $n$ gluons, full colour (DESIGN
    §1.4): $F_n approx (n - 1)! (1 / (ln 2))^n \/ 2$ families, $2^n$ helicities.
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
) <tab:complexity>]

#block(breakable: false)[#figure(kind: table,
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
) <tab:deps>]

// ============================================================== SOURCES ==
= Sources and reproducibility <sources>

#set par(justify: false)
#text(8.6pt)[
  - *Build:* `typst compile benchmarks.typ benchmarks.pdf` in
    `docs/performance_reports/loop/` (Typst 0.15).
  - *Status, in-flight work, decisions:* `data/milestone.json`, from the
    integration merges of #ms.engine_revision since #ms.previous_loop
    (#ms.integrated.map(r => [#r.wp.split(" ").last() #raw(r.sha)]).join([, ])\; commit subjects "Integrate work/v2-…")\;
    `workspace/reports/engine-v2/slice-status.md` (integration blocks,
    DECISIONS 2026-10-23/24/25, the milestone push m1025a of 2026-10-25 \~13:45 UTC; the user's gate decision of 2026-10-24, 16:05 UTC, is
    recorded in `data/milestone.json` `gate_decisions` and no longer applies after the
    re-measure; the user's rules of 2026-10-24, 22:35 UTC — uncoloured generation,
    green-to-red run times, summary pages with only Table 1, Figure 1 and legends,
    and the gate rule "#thr-rule.label", recorded as `gate_decisions.threshold_rule`
    and applied by `scripts/build_summary.py` and this report); `HANDOFF_24_10_2026.md` §6; MASTER_PLAN
    2026-10-23/24 entries; REQUIREMENTS_ADDENDUM A, D, F, G, H, I, J; DESIGN §5.5,
    §5.7 (G1), §6.1, §6.2, §7.5, §12.1, §12.4, WP3.1, WP3.2; the 24 October pushes (59badc7a and b4d76cc3,
    gates in slice-status.md) and the G-int push (79df367a, 25 October).
  - *@tab:summary, @fig:gate:* `data/summary.json`, written by
    `scripts/build_summary.py` from `data/g1.json`, `data/measured.json`,
    `data/milestone.json` and `tools/loop_benchmark/processes.json` by its
    main-configuration rule (the most recent measured configuration of each
    cell; a newer check that only repeats part of an older comparison does not
    replace it; revision ancestry from `data/milestone.json`); every entry
    names its configuration and source (README).
  - *@tab:provgen:* HANDOFF §0.1 (addendum F); the provider generation records of
    @tab:summary (`data/summary.json`): `data/g1.json` for the G1 rows and the
    reference runs' records (`workspace/reference/runs/required/<process>/`,
    collected into `data/measured.json`) for the $2 -> 5$ rows; MadLoop's production-build times of the $2 -> 5$ rows: the
    same runs' `madloop-production-result.json`. *@tab:validation, @required, @sevenglue:* the native
    validations on `work/v2-generation-scale` (#records-text), records
    `workspace/tmp/generation-scale/gint2/after/`, `gint/val1/` and `i7/val/` (the earlier seven-gluon
    points: `gint/val1/`), collected into `data/measured.json`; the earlier $g g -> t overline(t) e^- e^+ g$ record:
    DESIGN WP3.1 fourth increment. *Conventions:*
    #link("https://cp3.irmp.ucl.ac.be/projects/madgraph/wiki/MadLoopStandaloneLibrary")[MadLoop standalone],
    #link("https://arxiv.org/abs/1605.01090")[Recola],
    #link("https://arxiv.org/abs/1907.13071")[OpenLoops 2].
  - *@g1 (@tab:g1 to @tab:g1values):* `data/g1.json` and the per-point values
    `data/g1-values.json`, written by `python -m tools.loop_benchmark gate`
    (README and docstrings of `tools/loop_benchmark`); streams
    `tools/loop_benchmark/streams/`; run records archived in
    `workspace/reports/engine-v2/measure-g1/records/` (first campaign `runs/`,
    fix round `runs2/`, the re-measure at G-int (`4e9b5a9e`) `gint/` with its paired binary64-input runs
    `confirm/<process>/ab.json`, and this milestone's at #raw(g.slice_revision) `m1025a/`: its runs, logs, the
    frozen-heap launcher `gc_launcher.py` and its protocol experiment `gc/`, and the public-path confirmation
    `confirm/uux_ddxg/` (write, load and evaluate records); provider records reused from the first campaign and the
    fix round, not re-run), MadLoop exports of the G1-only processes in
    `workspace/reference/runs/g1/`; recalibration
    `tools/loop_v2_costmodel.py --g1 data/g1.json`. Builds:
    #raw(g.slice_build) (`loop`, #raw(g.slice_revision))#if g.at("native_build", default: none) != none [ and
    #raw(g.native_build) (`work/v2-generation-scale` #raw(g.native_revision) plus the timers;
    scratch commit #raw(g.native_commit), kept as tag #raw("g1-native-inputs-" + g.native_commit))] else [; history:
    #builds-of(l1-c).map(raw).join([, ]) (`work/v2-generation-scale` #rev-list(ms.development.revisions.keys().filter(r => r not in l1-revs)) plus the timers of
    scratch commit #rev-list(l1-revs), tag #l1-revs.map(r => raw("g1-native-inputs-" + r)).join([, ]): earlier runs, one lane, schedule M, stability) and
    #builds-of(py-c).map(raw).join([, ]) (Python inputs); G-int's earlier runs: `loop-native-v2-slice-4e9b5a9e`],
    release with one codegen unit and thin LTO; the harness is this
    branch's `tools/loop_benchmark`; the generations of 39824f9b and of G-int quoted in @status: `data/g1.json` of
    `c3a7be09` and of `79df367a`. Schedule M at seven legs: DESIGN §5.6.
  - *@tab:njet* and NJet prose: `workspace/reports/engine-v2/njet-benchmark.md`
    §2, §5, §6 (raw `workspace/reference/runs/njet/timing/`; the seven-gluon single evaluations are read from
    those records into `data/measured.json`);
    #link("https://arxiv.org/abs/1209.0100")[NJet, arXiv:1209.0100] Table 5.
  - *@tab:sevencheck:* `data/measured.json`
    (`scripts/collect_milestone.py <workspace>`); top-free values at lower multiplicity: DESIGN WP3.1 and
    `test_loop_v2_topfree.py`; the seven-gluon generation history: DESIGN WP3.1
    eighth and ninth increments. Memory in GiB = 2³⁰ bytes.
  - *@tab:caps, @arch:* `docs/development/loop_v2/DESIGN.md` §1–§3, §5.5,
    §5.6, §6, §10, §12, REQUIREMENTS_ADDENDUM J (counterterm rule) and the
    integration records above.
  - *History:* the legacy per-diagram engine's snapshot of 2026-10-18
    (`data/measurements.json`, `provider-cold.json`, `legacy-labels.json`,
    `colour-measurements.json`) stays for the DESIGN citations and is no longer
    shown; its table is in the earlier report revisions (README).
]
