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
#let mx = json("data/mqcd-matrix.json")
#let mq = json("data/mqcd.json")
#let st = json("data/mqcd-selftest.json")
#let sx = json("data/msm-matrix.json")
#let eg = json("data/msm-g1.json")
#let dm = json("data/dec-matrix.json")
#let hcj = json("data/hc.json")
#let crj = json("data/corr.json")
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
    [pyAmpliCol at one loop #h(1fr) milestone #ms.at("milestone", default: ms.date).split(" ").first()#if ms.at("closed", default: none) != none [ closed] (#ms.date) · engine #ms.engine_revision on `loop` · G1 timed at #g.slice_revision (`loop`)#if g.at("native_revision", default: none) != none [ and #g.native_revision (development)]]
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
// MG5 particle names in math mode: multi-letter names quoted (ve, ta-).
#let ap-tok(t) = {
  if t == ">" { return "->" }
  let (b, suf) = if t.ends-with("~") { (t.slice(0, -1), "bar") } else if t.ends-with("-") or t.ends-with("+") { (t.slice(0, -1), t.slice(-1)) } else { (t, none) }
  let core = if b.len() == 1 { b } else { "\"" + b + "\"" }
  if suf == "bar" { "overline(" + core + ")" } else if suf != none { core + "^(" + suf + ")" } else { core }
}
// An MG5 process string as math text (math-label renders it).
#let ap-math(p) = p.split(" ").map(ap-tok).join(" ")
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
// The gate batch (user 2026-10-28, milestone.json gate_decisions.gate_batch;
// tools/loop_benchmark/gate.py GATE_BATCH): the runtime speed gate is taken
// at B = 128 only. Every other batch size (B = 1, the 2->5 rows' B = 16, the
// history's 8 and 32) keeps its ratio and band with status "reported": no
// pass/fail verdict and no verdict colour.
#let reported = "reported"
// The user's gate rule (milestone.json gate_decisions.threshold_rule,
// 2026-10-24 ~22:35; Table 1 reads it through summary.json): a process whose
// time per point at B = 128 is below 5 ms has no blocking gate; its ratio and
// band stay as measured. Decided on the configuration's own B = 128 time
// (gate-b128; a configuration without one, e.g. the one-lane runs, has no
// verdict at all). The rule takes precedence over a decision.
#let thr-rule = ms.gate_decisions.threshold_rule
#let batched-of(c) = if c == none or refused(c) { none } else { let x = bat(c, big); if x == none { none } else { x.median_seconds_per_point } }
#let ungated(p, c) = p.gated and { let t = batched-of(c); t != none and t < thr-rule.below_seconds_per_point }
#let eff-status(p, c, b, gt) = if gt == none { none } else if gt.status == reported { reported } else if "ratio_to_binding_limit" in gt and ungated(p, c) { "not gated" } else { let d = decision(p, b, gt); if d != none { d.verdict } else { gt.status } }
#let gratio(r) = if r < 0.01 { fixed(r, 1 - calc.floor(calc.log(r, base: 10))) } else { fixed(r, 2) }
#let gate-word(p, c, b, gt) = if gt == none [—] else if eff-status(p, c, b, gt) == reported {
  // Reported, not gated (B != 128): the ratio, uncoloured.
  text(fill: ink2)[reported] + if "ratio_to_binding_limit" in gt [ #gratio(gt.ratio_to_binding_limit)]
} else if eff-status(p, c, b, gt) == "not gated" {
  text(fill: ink2, weight: "bold")[not gated] + [ #fixed(gt.ratio_to_binding_limit, 2)]
} else if decision(p, b, gt) != none {
  text(fill: pass-ink, weight: "bold")[#decision(p, b, gt).verdict‡] + [ #fixed(gt.ratio_to_binding_limit, 2)]
} else if gt.status == "pass" {
  text(fill: pass-ink, weight: "bold")[pass] + [ #gratio(gt.ratio_to_binding_limit)]
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
// The B = 1 ratios of the configuration on loop (reported, no verdict: user
// 2026-10-28), and of the development campaign's one-lane runs (history).
// B = 1: this campaign's run, else the newest earlier run that timed it
// (not re-timed since M-QCD: g1.json timing_protocol), over the B = 128 limit.
#let one-of(c) = { let x = bat(c, "1"); if x != none { (rev: none, x: x) } else { earlier-bat(c, "1") } }
#let one-ratio(c) = { let o = one-of(c); let l = bat(c, big); if o == none or l == none or "binding_limit" not in l.gate { none } else { o.x.median_seconds_per_point / l.gate.binding_limit } }
#let one-lim = gated.map(p => one-ratio(nat-c(p))).filter(r => r != none)
#let one-revs = gated.map(p => one-of(nat-c(p))).filter(o => o != none and o.rev != none).map(o => o.rev).dedup()
#let l1-lim = gated.map(p => lim(p, l1-c(p), "1")).filter(r => r != none)
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
#let nat-cores = g.processes.map(p => (nat-c(p), cfg(p, "native/lc"))).flatten().filter(c => c != none and c.host_cpus != none).map(c => c.host_cpus).flatten().dedup().sorted()
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
// The PRELIMINARY 2 -> 6 rows (summary.json "preliminary", from data/2to6.json):
// pyAmpliCol only, no provider, no gate, uncoloured; another engine than loop.
#let six = S.at("preliminary", default: none)
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
  box[#stage-label.at(top.at(0)) #fixed(100 * top.at(1) / tot, 0)~%]
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
#let absent(title, colspan: 1, ..lines) = table.cell(colspan: colspan, fill: neutral, breakable: false, {
  set par(leading: 0.34em, justify: false)
  block(spacing: 0pt, text(8pt, weight: "bold", fill: luma(105), style: "italic", title))
  set text(fill: luma(55))
  cell-lines(lines.pos())
})
#let pkey(k) = (madloop: "ML", recola: "Rc", openloops: "OL").at(k)
#let ratio-of(c) = c.at("ratio_to_fastest", default: none)
// The multiplier text: none without a provider ratio (g g > g g g g g: no
// matched provider); "≥" where the fastest provider's time is an upper bound
// (summary.json ratio_to_fastest_bound "lower": a provider's run outside the
// protocol that does the production work and more, u u~ > g g g g g's Recola).
#let ratio-mult(m) = { let r = ratio-of(m); if r == none { none } else if m.at("ratio_to_fastest_bound", default: none) == "lower" [≥#mult2(r)] else { mult2(r) } }
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
  else if s == "no gate batch" [no $B = 128$ run]
  else if s == "not supported" [not supported]
  else [not measured]
}
// A note on a measured cell (milestone.json cell_notes, through
// summary.json <cell>.main.note): a known limitation of the value in amber,
// its run conditions in grey; the value stays as measured.
#let cell-note(m) = if "note" not in m { none } else if m.note.kind == "not validated" { text(fill: amber, weight: "bold", m.note.label) } else { dim(m.note.label) }
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
    block(spacing: 0pt, text(6.2pt, fill: ink2)[#if o != none [#o · ]#val.points #if val.points == 1 [pt] else [pts]#if "median_finite" in val [ · median #esci(val.median_finite)]#if within [ · †] else if wp != none and "reference_own" in wp [ · ¶]#if val.at("note", default: none) != none [ · #val.note]])
    // Points above the check's tolerance that the user accepted
    // (summary.json validation.accepted; the check keeps its tolerance).
    let acc = val.at("accepted", default: none)
    if acc != none {
      v(2.2pt)
      block(spacing: 0pt, text(6.2pt, fill: pass-ink)[‡ pts #acc.points.map(x => str(x.index)).join(", ") above #esci(acc.tolerance): #acc.short])
    }
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
    let gone = c.providers.pairs().filter(((k, x)) => x.status == "unavailable" and k != f.key).map(((k, x)) => if "outside_protocol" in x [#pkey(k) #dur(x.outside_protocol.seconds_per_point) outside protocol] else if k == "openloops" [#pkey(k) no library] else [#pkey(k) no production timing])
    let nr = c.providers.pairs().filter(((k, x)) => x.status == "not run").map(((k, x)) => [#pkey(k) not exported])
    let best = if f.at("bound", default: none) == "upper" [#pkey(f.key) ≤#dur(f.seconds_per_point)] else [#pkey(f.key) #dur(f.seconds_per_point)]
    ((text(weight: "bold", best),) + rest + gone + nr).join([~· ])
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
    valued(fill: if ratio-of(m) == none { none } else { ratio-fill(ratio-of(m)) }, dur(m.seconds_per_point), mult: ratio-mult(m),
      [#prov-line #h(1fr) $B = #m.batch$],
      ..if "gate" in m and m.gate.status == thr-rule.verdict {
        // The longer not-gated chip on its own line, the bar below it.
        ([#gate-chip(m.gate)], [#stage-bar(m.stages)])
      } else {
        ([#if "gate" in m { gate-chip(m.gate) } else { plain-chip[#c.gate_rule.replace("->", "→")] } #h(4pt) #stage-bar(m.stages)],)
      },
      origin(r, m), cell-note(m))
  } else if m.status in ("not batched", "no gate batch") {
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
      [$B = #m.batch$#if "fc_seconds_per_point" in m [ · FC #dur(m.fc_seconds_per_point)]#alt(m)], origin(r, m), cell-note(m))
  } else if m.status == "not timed" {
    absent(status-title(m), [G1 timed full colour only])
  } else {
    absent(status-title(m), m.at("reason", default: none))
  }
}

#let group-title = ("2->2": [$2 -> 2$], "2->3": [$2 -> 3$], "2->4": [$2 -> 4$], "2->5": [$2 -> 5$], "2->6": [$2 -> 6$])

// The PRELIMINARY 2 -> 6 rows (summary.json "preliminary", data/2to6.json):
// pyAmpliCol only (no provider exists at 2 -> 6), so every cell is
// uncoloured, without ratio or gate; internal checks instead of references.
#let six-check(c) = {
  let n = c.check
  let body = if n == "double_pole" [$epsilon^(-2)$ ≤ #esci(c.value)]
  else if n == "stability" [$E$ ≤ #esci(c.value)#if c.above.len() > 0 [ (#c.above.len() pts above $10^(-5)$)]]
  else if n == "rescue" [rescue #c.value/#c.of]
  else if n == "ward" [Ward ≤ #esci(c.value)#if c.at("double_double", default: none) != none [ (DD #esci(calc.max(..c.double_double)))]]
  else if n == "double_double" [binary64 = DD to #esci(c.value)]
  else if n == "catani" [Catani $epsilon^(-1)$ ≤ #esci(c.value)]
  else if n == "ngluon" [NGluon#if c.carrier == "double-double" [ DD] to #esci(c.value)]
  else [#n.replace("_", " ")]
  if c.status == "fail" { text(fill: fail-ink, weight: "bold")[#body FAIL] } else { body }
}
#let six-name = (double_pole: "poles", catani: "Catani", ward: "Ward", double_double: "DD", stability: "E", rescue: "rescue", ngluon: "NGluon", stored_checks: "checks")
#let six-not-done = ("not obtained", "not run", "not asserted", "in progress")
#let six-checks(r) = ("LC", "FC").map(a => {
  let cs = r.checks.filter(c => c.accuracy == a and c.status not in six-not-done)
  if cs.len() == 0 { none } else [*#a* #cs.map(six-check).join([ · ])]
}).filter(x => x != none)
#let six-pending(r) = {
  let xs = r.checks.filter(c => c.status in six-not-done).map(c => [#six-name.at(c.check, default: c.check) #c.accuracy #c.status])
  if xs.len() == 0 { none } else [#xs.join(", ")]
}
#let t6-process(r) = table.cell(breakable: false, {
  set par(leading: 0.34em, justify: false)
  block(spacing: 0pt, text(10pt, font: "Libertinus Serif", math-label(r.math)))
  v(3.6pt)
  block(spacing: 0pt, text(6.4pt, fill: ink2)[#r.legs legs · #r.corrections · #box[#group(if r.families.fc != none { r.families.fc } else { r.families.lc }) families] · $N_f = 5$, no top])
  v(3.4pt)
  block(spacing: 0pt, text(6.2pt, six-checks(r).join([ · ])))
  let pend = six-pending(r)
  if pend != none { v(2.2pt); block(spacing: 0pt, text(6.2pt, fill: ink2, pend)) }
})
#let t6-generation(r) = {
  let (m, l) = (r.generation.main, r.generation.lc)
  valued(fill: none, dur(m.seconds), mult: if l != none { text(6.8pt)[FC] },
    [#gib(m.peak_gib) peak · plan #box[#sig(m.plan_mb)~MB] · store #dur(m.store_s)],
    [artifact #box[#m.artifact_gb~GB] · load #dur(m.load_s) (#gib(m.load_peak_gib))],
    if l != none [*LC* #dur(l.seconds) · #gib(l.peak_gib) · artifact #box[#l.artifact_gb~GB]])
}
#let t6-timing(m, gate: true) = if m.status == "measured" {
  valued(fill: none, dur(m.seconds_per_point),
    [#m.protocol#if m.colour_contraction != none [ · FFT] #h(1fr) $B = #m.batch$],
    [#if gate [#plain-chip[no provider: no gate] #h(4pt)]#stage-bar(m.stages, width: if gate { 2.0cm } else { 1.5cm })],
    [peak #gib(m.peak_gib)#if "note" in m [ · #text(fill: amber, weight: "bold", m.note)]])
} else {
  absent([not run], m.reason)
}
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
// Validation cells with points the user accepted above the check's tolerance.
#let accepted-rows = all-rows.filter(r => "accepted" in r.validation)
// G1 rows whose generation is a newer record without a multiplier, and
// validations whose worst point was re-evaluated by an earlier run (reading
// notes of Table 1).
#let s-g1-count = all-rows.filter(r => r.kind == "g1" and r.validation.at("worst_point", default: none) != none).len()
#let no-ratio-rows = all-rows.filter(r => r.kind == "g1" and "no_ratio" in r.generation.main)
// slice_tool_revisions: benchmark-tool commits on slice_revision's engine
// (build_summary.py _check_tool_revisions): not another engine.
#let same-engine(r) = r == g.slice_revision.slice(0, 8) or g.at("slice_tool_revisions", default: "").split(",").map(x => x.trim().slice(0, 8)).contains(r)
#let stab-other = all-rows.filter(r => {
  let v = r.validation
  let wp = v.at("worst_point", default: none)
  let id = v.at("configuration", default: none)
  wp != none and wp.at("revision", default: none) != none and id in C and C.at(id).at("revision", default: none) != wp.revision and not (C.at(id).kind == "g1" and same-engine(wp.revision))
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
  #text(8.6pt, fill: luma(105))[milestone #ms.at("milestone", default: ms.date).split(" ").first()#if ms.at("closed", default: none) != none [ *closed*] (#ms.date) · engine #raw(sm.engine_on_loop) on `loop` · #sm.host.split(",").first(), shared host · finite part, binary64, one pinned thread, $B = 128$]
  // The engine on loop and the engine G1 timed differ when a milestone does
  // not re-measure G1: say so once, here (data/g1.json slice_revision,
  // slice_build; data/milestone.json engine_revision, previous_loop).
  #if g.slice_revision.slice(0, 8) != sm.engine_on_loop.slice(0, 8) {
    v(-0.45em)
    text(8.6pt, fill: amber)[G1 cells as in the M-FINAL-b report (#raw(ms.previous_loop)): timed by G1 on #sm.date at engine #raw(g.slice_revision), native #raw(g.slice_build)\; not re-measured on #raw(sm.engine_on_loop): the final retime is deferred to the next milestone]
  }
]


// Compact visual legend of Table 1 (its text: "Reading the summary").
#let thr-rows = all-rows.filter(r => { let x = decided-gate(r); x != none and x.status == thr-rule.verdict })
// EW G1 rows (data/msm-g1.json through summary.json): gated since the final
// G1 retime (M-LIT-a0; indicative at M-SM, [U5]).
#let ew-rows = all-rows.filter(r => r.corrections == "EW")
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
      [#key-swatch(neutral) missing (why) #h(4pt) #key-swatch(white) no colour: generation, LC #h(4pt) † within estimate #h(4pt) ¶ reference's own (DD)#if decided-rows.len() > 0 or accepted-rows.len() > 0 [ #h(4pt) ‡ user decision] #h(4pt) ML MadLoop · Rc Recola · OL OpenLoops]
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
          [median per point at $B = 128$, the gate batch; provider times; gate G1 (time ÷ limit); stage shares],
          [batched, same configuration; LC/FC; no provider ratio],
        ).map(t => text(6.1pt, fill: ink2, t)),
      ),
      ..S.groups.map(gr => (
        table.cell(rowspan: gr.rows.len(), fill: luma(226), inset: 0pt, align: center + horizon, breakable: false,
          rotate(-90deg, reflow: true, text(8.4pt, weight: "bold", fill: navy, font: "Libertinus Serif", group-title.at(gr.name)))),
        ..gr.rows.map(r => (t1-process(r), t1-generation(r), t1-fc(r), t1-lc(r))).flatten(),
      )).flatten(),
      // The PRELIMINARY 2 -> 6 rows: their engine and status, stated once.
      ..if six != none {
        (
          table.cell(colspan: 5, fill: warm, inset: (x: 4.5pt, y: 2.6pt), { show raw: set text(6.3pt); text(6.6pt, fill: amber)[*$2 -> 6$* (M-FINAL item 1, #link(<sixlegs>)[below Figure 1]): pyAmpliCol only, no provider exists at $2 -> 6$, so no ratio, no gate and no colour · engine #raw(six.engine.revision) (#raw(six.engine.branch)), native #raw(six.engine.native) (#raw(six.engine.native_digest)…), an ancestor of this milestone's pin, not re-run on it · internal checks only]}),
          table.cell(rowspan: six.rows.len(), fill: luma(226), inset: 0pt, align: center + horizon, breakable: false,
            rotate(-90deg, reflow: true, text(8.4pt, weight: "bold", fill: navy, font: "Libertinus Serif", group-title.at(six.name)))),
          ..six.rows.map(r => (t6-process(r), t6-generation(r), t6-timing(r.full_colour), t6-timing(r.leading_colour, gate: false))).flatten(),
        )
      } else { () },
    )
  },
) <tab:summary>

// Figure 1: the batched full-colour time of each G1 row against its gate
// limit and the providers, on a log scale (data/summary.json).
#let fig-lo = calc.log(0.0005, base: 10)
#let fig-hi = calc.log(1000.0, base: 10)
#let fig-w = 11.2cm
#let fig-h = 8pt
#let xpos(t) = fig-w * (calc.log(t, base: 10) - fig-lo) / (fig-hi - fig-lo)
#let fig-ticks = ((0.001, [1 ms]), (0.01, [10 ms]), (0.1, [100 ms]), (1.0, [1 s]), (10.0, [10 s]), (100.0, [100 s]))
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
      let fast = k == c.fastest.key
      if "seconds_per_point" in x {
        place(dx: xpos(x.seconds_per_point) - 2.4pt, dy: fig-h / 2 - 2.4pt,
          rotate(45deg, square(size: 3.4pt, fill: if fast { luma(40) } else { luma(165) }, stroke: 0.4pt + white)))
      } else if "outside_protocol" in x and "production_upper_bound" in x.outside_protocol {
        place(dx: xpos(x.outside_protocol.seconds_per_point) - 2.4pt, dy: fig-h / 2 - 2.4pt,
          rotate(45deg, square(size: 3.4pt, fill: white, stroke: 0.9pt + if fast { luma(40) } else { luma(165) })))
      }
    }
    if m.status == "measured" { place(dx: xpos(m.seconds_per_point) - 2.9pt, dy: fig-h / 2 - 2.9pt, fig-dot(fill: navy, stroke: 0.6pt + white)) }
  })
}
#figure(
  caption: [*Batched full colour against the gate* (finite part, $B = 128$; the rows of @tab:summary with a matched provider).],
  {
    set text(7pt, font: sans, stretch: 87.5%)
    grid(columns: (3.2cm, fig-w, 1fr), column-gutter: 6pt, row-gutter: 1.6pt, align: (right + horizon, left + horizon, left + horizon),
      ..fig-rows.map(r => {
        let m = r.full_colour.main
        let chip = if m.status != "measured" { plain-chip[#status-title(m)] } else if "gate" in m { gate-chip(m.gate) } else { plain-chip[#r.full_colour.gate_rule.replace("->", "→")] }
        (box[#text(7.8pt, font: "Libertinus Serif", math-label(r.math))#if r.corrections != "QCD" [ #text(6.6pt, fill: ink2)[(#r.corrections)]]], fig-row(r), chip)
      }).flatten(),
      [], box(width: fig-w, height: 9pt, for (t, l) in fig-ticks { place(dx: xpos(t) - 1cm, box(width: 2cm, align(center, text(fill: ink2, l)))) }), [],
    )
    // Compact visual key (its text: "Reading the summary").
    let key-mark(body) = box(width: 8pt, height: 7pt, baseline: 1pt, body)
    v(2pt)
    text(fill: ink2, {
      box[#key-mark(place(dx: 1.1pt, dy: 0.6pt, fig-dot(fill: navy, stroke: 0.6pt + white)))#[pyAmpliCol (@tab:summary)]]; h(5pt)
      box[#key-mark(place(dx: 1.6pt, dy: 1.2pt, rotate(45deg, square(size: 3.4pt, fill: luma(40), stroke: 0.4pt + white))))#[fastest provider]]; h(5pt)
      box[#key-mark(place(dx: 1.6pt, dy: 1.2pt, rotate(45deg, square(size: 3.4pt, fill: luma(165), stroke: 0.4pt + white))))#[other providers]]; h(5pt)
      box[#key-mark(place(dx: 1.6pt, dy: 1.2pt, rotate(45deg, square(size: 3.4pt, fill: white, stroke: 0.9pt + luma(40)))))#[upper bound (outside protocol)]]; h(5pt)
      box[#key-mark({ place(dx: 1pt, rect(width: 1.4pt, height: 7pt, fill: fail-ink, stroke: none)); place(dx: 2.4pt, rect(width: 5.6pt, height: 7pt, fill: slow-red.transparentize(86%), stroke: none)) })#[gate limit, shaded side fails]]; h(5pt)
      box[#key-mark(place(dx: 3pt, rect(width: 1.2pt, height: 7pt, fill: luma(150), stroke: none)))#[limit, not gated]]; h(5pt)
      box[#key-mark(place(dx: 3.5pt, line(start: (0pt, 0pt), end: (0pt, 7pt), stroke: (paint: luma(110), thickness: 0.6pt, dash: "dotted"))))#[5 ms]]
    })
  },
) <fig:gate>

// ====================================================== LOOP-INDUCED TABLE ==
// The loop-induced summary table (USER 2026-11-06 ~06:00; m-lit/PLAN.md §3.7
// "Pushes"): renders data/summary-li.json (scripts/build_summary.py,
// build_loop_induced) as is, drawn with Table 1's own cell, colour and marker
// functions (valued, absent, ratio-fill, gate-chip, plain-chip, dur, gib,
// mult2): one row per process of PLAN §4.1 by multiplicity, the batched
// B = 128 time on the default backend (TIRust; NinjaRS per amplitude
// labelled where TIR does not serve the row yet) against the fastest matched
// provider, generation uncoloured, explicit pending and missing markers.
#let LI = json("data/summary-li.json")
#let li-meta = LI.meta
#let li-rows = LI.groups.map(gr => gr.rows).flatten()
// A group's title from its registry name ("2->3" as $2 -> 3$, "/" as a
// middle dot; any name milestone.json declares).
#let li-group-title(name) = name.split(" / ").map(part => { let xs = part.split("->"); if xs.len() == 2 and xs.all(x => x.trim().len() > 0) { $#xs.at(0).trim() -> #xs.at(1).trim()$ } else { part } }).join([ · ])
// Missing-cell titles; the batch statuses take Table 1's words (status-title).
#let li-title(c) = if c.status in ("not batched", "no gate batch") { status-title(c) } else { (pending: [pending], "not run": [not run], "not recorded": [not recorded]).at(c.status, default: c.status) }
#let li-pending-rows = li-rows.filter(r => r.timing.status == "pending")
#let li-served = li-rows.filter(r => r.landed)
// The provider line of a row (lit-ref's timings, or why there are none).
#let li-prov-line(r) = {
  let p = r.providers
  if p.status == "pending" [providers pending (lit-ref): #p.expected.join(" · ")]
  else if p.status == "not run" [#p.expected.join(" · "): #p.reason]
  else {
    let f = p.fastest
    let xs = p.providers.pairs().sorted(key: ((k, x)) => x.at("seconds_per_point", default: 1e300))
    xs.map(((k, x)) => if "seconds_per_point" in x { if f != none and k == f.key { text(weight: "bold")[#pkey(k) #dur(x.seconds_per_point)] } else [#pkey(k) #dur(x.seconds_per_point)] } else [#pkey(k) #x.status: #x.reason]).join([~· ])
  }
}
// A cell's gate marker: lit-perf's verdict as Table 1's gate chip, every
// rule (reported, 5 ms, no matched provider, no verdict yet) as Table 1's
// plain chip.
#let li-chip(g) = if g.status in ("pass", "fail", "open") { gate-chip((status: g.status, ratio_to_limit: g.ratio_to_limit)) } else { plain-chip[#g.label.replace("->", "→")] }
#let li-process(r) = table.cell(breakable: false, {
  set par(leading: 0.34em, justify: false)
  block(spacing: 0pt, text(10pt, font: "Libertinus Serif", if r.math != none { math-label(r.math) } else { text(8.4pt, font: sans, stretch: 87.5%, r.label) }))
  if r.alternative != none { v(1.6pt); block(spacing: 0pt, text(6.4pt, fill: ink2)[or #box(text(8pt, font: "Libertinus Serif", math-label(r.alternative.split(" ").map(tok).join(" "))))]) }
  v(3.6pt)
  block(spacing: 0pt, text(6.4pt, fill: ink2)[#if r.legs != none [#r.legs legs · ]#r.corrections · #r.ids.join(", ")#if r.backends.len() == 1 [ · #r.backends.first() only]])
  v(3.4pt)
  let v = r.validation
  block(spacing: 0pt, text(6.2pt, if v.status == "pending" { dim[validation pending (lit-val)] } else if v.status == "not run" { dim[validation not run (no record in lit.json)] } else [#v.references.map(x => [#x.short #esci(x.max_relative)]).join([~· ]) · #v.status#if v.points != none [ · #v.points pts]]))
})
#let li-generation(r) = {
  let m = r.generation
  let p = r.providers
  let gens = if p.status == "recorded" { p.generation } else { (:) }
  let pline = if gens.len() == 0 { none } else { gens.pairs().sorted(key: ((k, s)) => s).map(((k, s)) => [#pkey(k) #dur(s)]).join([~· ]) }
  if m.status == "measured" {
    valued(fill: none, dur(m.seconds), mult: if "ratio_to_fastest" in m { mult2(m.ratio_to_fastest) },
      [#gib(m.peak_gib) peak#if m.plan_mb != none [ · plan #box[#sig(m.plan_mb)~MB]]], pline)
  } else {
    absent(li-title(m), m.at("reason", default: none), pline)
  }
}
#let li-timing(r) = {
  let m = r.timing
  if m.status == "measured" {
    valued(fill: if "ratio_to_fastest" in m { ratio-fill(m.ratio_to_fastest) } else { none }, dur(m.seconds_per_point),
      mult: if "ratio_to_fastest" in m { mult2(m.ratio_to_fastest) },
      [#li-prov-line(r) #h(1fr) $B = #m.batch$],
      [#li-chip(m.gate) #h(4pt) #text(weight: "bold", m.backend_label)#if "other_backend" in m [ · #m.other_backend.backend_label #dur(m.other_backend.seconds_per_point)]])
  } else {
    absent(li-title(m), m.at("reason", default: none), li-prov-line(r))
  }
}
// Generation and timing pending for the same reason: one marker over both.
#let li-cells(r) = if r.generation.status == "pending" and r.timing.status == "pending" and r.generation.reason == r.timing.reason {
  (absent(li-title(r.timing), colspan: 2, r.timing.reason, li-prov-line(r)),)
} else { (li-generation(r), li-timing(r)) }
#let li-head = {
  if li-meta.landed.len() == 0 [no loop-induced package has landed at this head: every row *pending* (served by the package named in its cell) · default backend #li-meta.default_backend · nothing estimated]
  else [packages landed: #li-meta.landed.map(raw).join(", ") · default backend #li-meta.default_backend, NinjaRS per amplitude labelled where TIR does not serve the row yet · the newest record of each cell]
}
#figure(kind: table,
  caption: [*Loop-induced processes* ($|A_"loop"|^2$; the equivalent of @tab:summary). How to read it: #link(<reading-li>)[after Figure 1].],
  {
    set text(7pt, font: sans, stretch: 87.5%)
    set par(justify: false)
    show table.cell.where(y: 0): set text(fill: white, weight: "bold", size: 8pt)
    table(
      columns: (0.5cm, 4.8cm, 4.0cm, 1fr),
      align: left + std.top,
      inset: (x: 4.5pt, y: 4.2pt),
      stroke: (x, y) => (top: if y <= 3 { none } else { 0.6pt + white }, left: if x > 0 and y != 1 { 0.6pt + white } else { none }),
      fill: (x, y) => if y == 0 { navy } else if y == 1 { warm } else if y == 2 { pale } else { none },
      table.header(
        [], [Process · validation], [Generation], [$|A_"loop"|^2$ · per point, batched, default backend],
        table.cell(colspan: 4, inset: (x: 4.5pt, y: 2.6pt), { show raw: set text(6.3pt); text(6.6pt, fill: amber, li-head) }),
        [],
        ..(
          [legs · corrections · PLAN §4.1 ids; largest deviation per reference (lit-val)],
          [generate + plan export, peak memory; provider generation],
          [median per point at $B = 128$; provider times (lit-ref); gate (lit-perf) or rule; backend],
        ).map(t => text(6.1pt, fill: ink2, t)),
      ),
      ..LI.groups.map(gr => (
        table.cell(rowspan: gr.rows.len(), fill: luma(226), inset: 0pt, align: center + horizon, breakable: false,
          rotate(-90deg, reflow: true, text(8.4pt, weight: "bold", fill: navy, font: "Libertinus Serif", li-group-title(gr.name)))),
        ..gr.rows.map(r => (li-process(r), ..li-cells(r))).flatten(),
      )).flatten(),
    )
  },
) <tab:summary-li>

#pagebreak(weak: true)

// ============================================================== READING ==
// Everything that explains Table 1 and Figure 1 (user rule (e)).
#heading(numbering: none)[Reading the summary] <reading>
#[
#set text(9.4pt)
#set par(justify: true)
// Rows whose fastest provider time is an upper bound (summary.json fastest.bound).
#let bound-rows = all-rows.filter(r => { let f = r.full_colour.at("fastest", default: none); f != none and f.at("bound", default: none) == "upper" })
*Table 1* has one row per test process, by multiplicity. A cell gives pyAmpliCol's value in bold and, at its right, the
multiplier _pyAmpliCol ÷ the fastest provider_ on this host (in bold among the provider values).#if bound-rows.len() > 0 [ A provider time marked ≤ (#row-names(bound-rows.map(r => r.key))) comes from a run outside the protocol that does the production work and more (Recola's reference run evaluates the IR poles too), so it bounds that provider's production time from above, and the multiplier against it is a lower bound (≥); it is never a gate limit.] Only run times are
coloured: green faster, white at parity, red slower (log₂ scale, clamped at ×1/16 and ×16). Generation cells carry their
multiplier uncoloured (generation time is not the main metric, user 2026-10-24); leading colour has no provider ratio.
Grey cells say why a value is missing. Run times are per phase-space point in batches, finite part, stability checks off;
providers in production mode (@status). Every value is the *most recent measured configuration* of its cell (by git
ancestry of the revisions; a newer check that only repeats part of an older comparison does not replace it):
#measured-ids.map(cfg-clause).join([\; ])#if dev-used [. #if cfg-used("integrated") [The values of #row-span(dev-rows) are] else [These are] #if rec-integrated != none and not cfg-used("development") [*development measurements*, not yet repeated on `loop`] else [*development measurements* of a branch being integrated into `loop`#if C.development_records.at("integration", default: none) != none [ (#C.development_records.integration)], not yet on `loop`]]. #if not cfg-used("integrated") [The engine on `loop` (#inputs-text(C.integrated) per-point inputs, G1 at #raw(C.integrated.revision)) is not shown there: @g1 (gate-G1 details) keeps its timings for history.] else if py-revs.len() > 0 [The engine before #C.development_records.at("integration", default: "this milestone") (Python per-point inputs, G1 at #rev-list(py-revs)) is history in @g1.] The column header of Table 1 names these configurations once.

*Gate chips* (Table 1 and Figure 1): the time over the binding limit (MadLoop's time, or 1.30 × the faster of Recola and
OpenLoops), *pass* or *fail* when the whole uncertainty band is below or above 1, else *open*. The user's gate rule of 2026-10-24:
a process whose time per point at $B = 128$ is below 5 ms has no blocking gate, its verdict is "#thr-rule.label" and its chip
("#thr-rule.short") keeps the measured ratio#if thr-rows.len() > 0 [ (#thr-rows.map(r => { let x = decided-gate(r); [#box(math-label(r.math)) #dur(r.full_colour.main.seconds_per_point), #fixed(x.ratio_to_limit, 2) of its limit] }).join([, ], last: [ and ]))]. #box(math-label("g g -> g g")) ($2 -> 2$) has no gate#for r in ew-rows [; #box(math-label(r.math)) (#r.corrections, `data/msm-g1.json`) is gated like the QCD rows since the final G1 retime (M-LIT-a0\; at M-SM it was timed indicatively, [U5])\; its leading colour is #r.leading_colour.main.reason]#for r in decided-rows.filter(r => decided-gate(r).status != thr-rule.verdict) { let x = decided-gate(r); [; ‡ #math-label(r.math): #x.status (#x.decision), measured #x.measured_status at #fixed(x.ratio_to_limit, 2), band #fixed(x.band.at(0), 2)–#fixed(x.band.at(1), 2)] }. The gate is taken at $B = 128$ only (user 2026-10-28,
`gate_decisions.gate_batch`): $B = 1$ and the $2 -> 5$ rows' $B = 16$ are measured and *reported* with their ratios
(@tab:g1, @tab:g1batch), without a verdict or a verdict colour.

*Stage shares* (the bar of the full-colour cell; the largest is named; @tab:g1split): inputs = trees, Born and
counterterm inputs (on `loop` the executor's own timer of its native trees, since lc-perf); glue = point parameters, input
conversion, assembly and the rest of the call#if t1-untimed [; untimed = the rest of the call of a build without input
timers]. Times use the protocol's schedule B#if m-rows.len() > 0 [; "M:" gives the schedule G1 adopted for the class (@tab:g1bm)].

*References and deviations.* ML MadLoop 3.7.0, Rc Recola 2.2.5 (COLLIER), OL OpenLoops 2.1.5 (prebuilt libraries: no
generation time), NJet DD NJet 3.1.2 in double-double. Deviation $|a - b| slash max(|a|, |b|, |B| alpha_s slash 2 pi)$ of the
binary64 finite part at the timed points (median: over the points, the largest over the references); † the largest lies
within the binary64 stability estimate of the same configuration at that point#if stab-other.len() > 0 [ (#if stab-other.len() == s-g1-count [G1 rows] else [#row-names(stab-other.map(r => r.key))]: stability runs of #rev-list(stab-other.map(r => r.validation.worst_point.revision).dedup()) on the same process, whose binary64 values equal the timed ones to rounding level, more at binary64-unstable points: `values_note` of `data/g1.json`)]\; ¶ the largest is the reference's own: pyAmpliCol's double-double value at that point lies as far from it, and its binary64 value lies within $E$ of the double-double one.#for r in accepted-rows { let a = r.validation.accepted; [ ‡ #box(math-label(r.math)): the reference check's points #a.points.map(x => str(x.index)).join(" and ") (#a.points.map(x => sci(x.finite.values().first())).join(" and ") from #r.validation.references.first().short) exceed its tolerance #sci(a.tolerance, d: 0) in binary64: *#a.status* (estimates $E$ #a.points.map(x => sci(x.estimate)).join(" and ")\; pyAmpliCol's double-double values equal the reference's); the check keeps its tolerance#if a.at("passed", default: false) [ and, asserting double-double at these points since the user's E1 ruling (2026-10-29), passes] else [ and records `passed: false`] (`data/milestone.json` `validation_decisions`).] }
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
#if g.at("generation_protocol", default: none) != none [G1 generates every row cold since milestone m1026a
(`11542fd5`), in its own process with a fresh cache directory, so the counterterm caches are rebuilt in every run
(@g1, generation protocol).]

// Notes on single measured cells (data/milestone.json cell_notes, through
// summary.json <cell>.main.note).
#let note-cells = all-rows.map(r => ("generation", "full_colour", "leading_colour").filter(k => "note" in r.at(k).main).map(k => (r: r, k: k))).flatten()
#let cell-word = (generation: [generation], full_colour: [full colour], leading_colour: [leading colour])
#if note-cells.len() > 0 [*Notes under a value* (`data/milestone.json` `cell_notes`) qualify it and leave it as measured, in
amber a known limitation of the value, in grey its run conditions: #note-cells.map(x => [#box(math-label(x.r.math)), #cell-word.at(x.k) ("#x.r.at(x.k).main.note.label"): #x.r.at(x.k).main.note.reason]).join([\; ]).]


#if six != none [*The $2 -> 6$ rows* (M-FINAL item 1; `data/2to6.json` through `summary.json` `preliminary`; #link(<sixlegs>)[their records and checks below]) are outside the main-configuration rule: pyAmpliCol only (no provider exists at $2 -> 6$), so no multiplier, no gate and no colour in any cell; engine #raw(six.engine.revision) (#raw(six.engine.branch)) for every record, an ancestor of this milestone's pin, not re-run on it (loop stores made before model compiler 17 do not load on the pin, so the rows keep their engine); generation = generate + plan export (store, artifact and load beside it; "FC" marks the full-colour generation, LC below it); the timed evaluation is binary64, finite part, checks off, one pinned thread, at the largest batch measured. The process cell lists the internal checks ($epsilon^(-2)$: double pole against the universal value; $E$: the recommended stability estimate, with the points above $10^(-5)$; rescue: the stream points of 16 the default rescue policy's binary64 level sends up; Ward on the external gluons; binary64 against double-double; Catani at full colour; NGluon at leading colour on the all-gluon row) and, in grey, those not run or not asserted.

]*Figure 1* places each row's batched full-colour value of Table 1 (dots; the most recent measured configuration:
#measured-ids.filter(id => C.at(id).main_cells.full_colour.len() > 0 and C.at(id).kind == "g1").map(cfg-short).join([\; ])#if C.at("development", default: none) != none and C.development.main_cells.full_colour.len() > 0 [\; development, not yet on `loop`]) against the providers (diamonds, the darkest
the fastest) and the gate limit (red bar, the shaded side fails; grey bar: the limit of a process below 5 ms, not gated;
dotted line: 5 ms), for the rows with a matched provider, at $B = 128$. The ratios and bands at every batch size: @tab:g1batch.

#heading(numbering: none, level: 2, outlined: false)[The loop-induced table] <reading-li>
// The legend of the loop-induced summary table (data/summary-li.json meta).
#let li-inputs = li-meta.inputs.values()
@tab:summary-li follows Table 1’s rules for loop-induced processes, $|A_"loop"|^2$ without a Born (`data/summary-li.json`,
written by `scripts/build_summary.py` from the row registry `data/milestone.json` `loop_induced` and the loop-induced
records). One row per process of the M-LIT validation matrix (`m-lit/PLAN.md` §4.1; its ids in the process cell),
grouped by multiplicity; the backend-unit, zero, identity, observable and complex-mass-scheme rows (#li-meta.validation_only.ids.join(", ")) stay in the
validation tables. The cell is the batched $B = #li-meta.gate_batch$ time per point (median, finite part, one pinned
thread, checks off) on the default backend #li-meta.default_backend\; NinjaRS per amplitude, labelled in the cell, where
TIR does not serve the row yet; the other backend's time beside it when both ran. Its multiplier against the fastest
matched provider (MadLoop's loop-induced production setting 7|6|1, OpenLoops `ls`, Recola; production mode, from
`lit-ref`) colours it with Table 1’s scale; generation is uncoloured. Rows of four legs or fewer ($2 -> 1$, $1 -> 2$,
$2 -> 2$, $1 -> 3$) are reported without a gate; from $2 -> 3$ upward the gate is Table 1’s (faster than MadLoop and at
most 1.30× each matched OpenLoops and Recola time, on TIRust), "#thr-rule.short" below 5 ms per point, no gate without a
matched provider; verdict chips come with `lit-perf`'s records, "no verdict yet" before them. Grey cells are explicit
markers: *pending* (the package that serves the row, named in the cell, has not landed at this head, or the input file
that fills the cell does not exist yet), *not run* (a landed package without a record of the row), and a provider's
reason where it has no matched time (no library, beyond the 45-minute rule). Nothing is estimated or extrapolated; each
cell shows the newest record of its row (git ancestry of the record revisions). At this head #li-served.len() of
#li-rows.len() rows are served; inputs: #li-inputs.map(x => [#raw(x.file) #if x.present [present] else [not written yet (#x.owner)]]).join([, ])\;
the registry against `lit-ref`'s manifest (#raw(li-meta.campaign.file)): #if li-meta.campaign.checked [checked, #li-meta.campaign.rows rows] else [#li-meta.campaign.reason].
]


// =============================================================== 2 -> 6 ==
// The 2 -> 6 rows of Table 1: data/2to6.json (scripts/build_2to6.py, from
// the mf-2to6 run records on one engine). Numbers from the data only.
#let sxj = json("data/2to6.json")
#let six-rec(k) = sxj.rows.find(r => r.key == k)
#let six-acc-word(r) = if r.accuracy == "lc" [LC] else [FC]
#let six-stage(st) = [#dur(st.s) · #gib(st.peak_gib)]
#let six-ok(k, c) = if k == "double_pole" { c.verdict == "pass" } else { c.at("passed", default: true) != false }
#heading(numbering: none)[$2 -> 6$: records and checks (M-FINAL item 1)] <sixlegs>
#[
#set text(9.4pt)
#set par(justify: true)
The $2 -> 6$ rows of @tab:summary come from `data/2to6.json`, which `scripts/build_2to6.py` derives byte for byte from the
mf-2to6 run records (harness store records, stored-checks, Ward, NGluon and timing records, watchdog status files and the
stores' `generation.json`; #sxj.sources.len() sources). Engine (every record#if not sxj.engine.one_engine [, #text(fill: fail-ink)[*not* one engine]]):
#raw(sxj.engine.branch) at #raw(sxj.engine.revision.slice(0, 8)) (#sxj.engine.base), native #raw(sxj.engine.native.directory)
(digest #raw(sxj.engine.native_digest_short)…), an ancestor of this milestone's pin (integrated as mf-8g-3, `df1d2a5d`), not re-run on it. Protocol: #sxj.engine.protocol\; particle veto
PDG #sxj.rows.first().particle_veto.map(str).join(", ") (top-free, $N_f = 5$, user Q-A), #sxj.rows.first().lanes lanes. No external reference exists at $2 -> 6$: acceptance is internal (double pole against the
universal value, Catani at full colour, NGluon at leading colour, Ward, double-double, the stability estimate) and the speed
is reported without a gate (cells uncoloured).
]

#figure(kind: table,
  caption: [*The $2 -> 6$ records* (`data/2to6.json` `rows`): generation stages (wall time · peak), the stored artifact and
    its load, the timed evaluations (finite part, poles and checks off; warm-up excluded, including lazy compilation) and
    the checks (grey: not run or not asserted, with the reason in the data). Peaks are the harness's per-stage high-water
    marks and the timing process's maximum resident set (GiB = 2#super[30] bytes).],
  {
    set text(6.6pt, font: sans, stretch: 87.5%)
    set par(justify: false, leading: 0.36em)
    show table.cell.where(y: 0): set text(fill: white, weight: "bold")
    table(
      columns: (2.4cm, 1.45cm, 1.6cm, 1.45cm, 1.75cm, 2.3cm, 1fr),
      align: left + horizon, inset: (x: 2.6pt, y: 2.2pt),
      stroke: (x, y) => (top: if y <= 1 { none } else { 0.3pt + luma(225) }),
      fill: (x, y) => if y == 0 { navy } else { none },
      table.header[Record][Generate][Export · plan][Store][Artifact · load][Evaluation][Checks],
      ..sxj.rows.filter(r => r.generation != none).map(r => {
        let st = r.generation.stages
        let e = r.evaluation
        (
          [#text(7.6pt, font: "Libertinus Serif", math-label(ap-math(r.process))) #six-acc-word(r) · #group(r.structure.families) families],
          six-stage(st.generate),
          [#six-stage(st.export) · #box[#sig(st.export.plan_mb)~MB]],
          six-stage(st.store),
          [#box[#r.artifact.gb~GB] · #dur(r.load.s), #gib(r.load.peak_gib)],
          [#r.evaluations.pairs().map(((b, x)) => if x.status == "measured" [*#dur(x.s_per_point)/pt* at $B = #b$ (#gib(x.peak_gib))] else [#dim[$B = #b$ #x.status]]).join([; ])#if e != none [; warm-up #dur(e.warm_up.s)]],
          {
            let done = r.checks.pairs().filter(((k, c)) => c.status == "done" and k != "stored_checks").map(((k, c)) => if six-ok(k, c) [#k.replace("_", " ")] else [#text(fill: fail-ink, weight: "bold")[#k.replace("_", " ") FAIL]])
            let miss = r.checks.pairs().filter(((k, c)) => c.status != "done").map(((k, c)) => [#k.replace("_", " ") #c.status])
            [#done.join(", ")#if miss.len() > 0 [; #dim[#miss.join(", ")]]]
          },
        )
      }).flatten(),
    )
  },
) <tab:sixrecs>

#[
#set text(9pt)
#let lc8 = six-rec("gg_gggggg-lc")
#let fc8 = six-rec("gg_gggggg-full")
#let done(r, k) = r.checks.at(k, default: (status: none)).status == "done"
#let fcs = sxj.rows.filter(r => done(r, "catani"))
#let wards = sxj.rows.filter(r => done(r, "ward"))
#let dds = sxj.rows.filter(r => done(r, "double_double"))
#let quarks = sxj.rows.filter(r => not r.all_gluon and done(r, "rescue"))
*Checks* (`data/2to6.json` `rows[].checks`):
- *Poles.* The double pole equals the universal value at points 0–2 on all #sxj.rows.filter(r => done(r, "double_pole")).len() records (≤ #esci(calc.max(..sxj.rows.filter(r => done(r, "double_pole")).map(r => r.checks.double_pole.max_deviation)))). Catani's poles (native, from the stored dipole orbits) agree on the #fcs.len() full-colour records within 10~$E$ (largest single-pole deviation #esci(calc.max(..fcs.map(r => r.checks.catani.max_single_deviation)))), in double-double at point 0 to binary64 resolution. At leading colour on $g g -> 6g$, NGluon (NJet) on exactly rotated points agrees in double-double to #esci(lc8.checks.ngluon.at("ngluon-dd").max_relative.first()) (finite part) and in binary64 within 10~$E$; the leading-colour single pole of the quark rows is not checked (the native Catani operator is full colour only, NGluon serves all-gluon rows only).
- *Double-double.* At point 0 the binary64 error against double-double is below its estimate $E$ on all #dds.len() records (largest #esci(calc.max(..dds.map(r => r.checks.double_double.binary64_true_error_finite_relative)))).
- *Ward* (external gluons, $epsilon_j -> p_j \/ p_j^0$, the real part of the interference). It passes on the #wards.len() quark records in binary64 (virtual/scale ≤ #esci(calc.max(..wards.map(r => calc.max(..r.checks.ward.max_virtual_ratio_finite_single_double))))), on $u overline(u) -> u overline(u) g g g g$ FC also in double-double. On $g g -> 6g$ LC every Ward point lies beyond the binary64 scope: recorded, not asserted (inconclusive; each ratio below its $E$); the full-colour and double-double Wards of $g g -> 6g$ were not run (user, 2026-11-04 \~17:35: enough evidence).
- *Stability.* The recommended estimate exceeds $10^(-5)$ at points #lc8.checks.stability.at("points_above_1e-5").map(str).join(", ") of $g g -> 6g$ (LC) and #fc8.checks.stability.at("points_above_1e-5").map(str).join(", ") (FC); the default rescue policy's binary64 level sends #lc8.checks.rescue.count (LC) and #fc8.checks.rescue.count (FC) of #lc8.checks.rescue.of stream points up at 8 gluons, #quarks.map(r => str(r.checks.rescue.count)).join(", ", last: " and ") on the quark records: rescue cases, not failures.
- *Caveats* (`global_caveats`): #sxj.global_caveats.map(x => x.replace("2->6", "2 → 6")).join("; ").
- *Not run or open* (`not_obtained`, as the data words it):
  #list(..sxj.not_obtained.map(x => text(8pt, x)))
]

// The M-FINAL optimisation rounds at seven legs (data/rounds-7leg.json,
// transcribed from m-final/round-table-7leg.md): the 8g0 baseline (u u~ > 5g: mf-8g-2's A/B base side) against
// now (d24a01ae), per stage, one pinned thread.
#let r7t = json("data/rounds-7leg.json")
#heading(numbering: none, level: 2)[Optimisation rounds at seven legs (M-FINAL)]
#let r7-val(unit, xs) = if unit == "MB" [#sig(xs.at(0))~MB] else if xs.len() == 1 [#dur(xs.at(0))] else [#dur(xs.at(0)) · #gib(xs.at(1))]
#let r7-fac(xs, ys) = xs.zip(ys).map(((a, b)) => [×#fixed(b / a + 1e-9, 2)]).join([ · ])
#let r7-cell(unit, x) = [#r7-val(unit, x.baseline) → *#r7-val(unit, x.now)* #tiny[#r7-fac(x.baseline, x.now)]]
#figure(kind: table,
  caption: [*The optimisation rounds at seven legs* (`data/rounds-7leg.json`, from `m-final/round-table-7leg.md`): $g g -> g g g g g$ (top-free, $N_f = 5$) and, below, $u overline(u) -> 5g$ at full colour,
    the baseline (for $g g -> g g g g g$ the 8g0 records, #r7t.baseline.split(" (").first(), before round 1; for $u overline(u) -> 5g$ mf-8g-2's A/B base side) against the slice after round 2 (`d24a01ae`), one
    pinned thread, s and peak GiB per stage, factors now/baseline; values bitwise through every round, the stored artifacts
    byte-identical between the rounds' records; indicative (shared host). The $2 -> 6$ records above ran on the engine
    after these rounds plus mf-8g-3.],
  {
    set text(6.8pt, font: sans, stretch: 87.5%)
    set par(justify: false, leading: 0.36em)
    show table.cell.where(y: 0): set text(fill: white, weight: "bold")
    table(
      columns: (3.6cm, 1fr, 1fr),
      align: left + horizon, inset: (x: 2.6pt, y: 2.2pt),
      stroke: (x, y) => (top: if y <= 1 { none } else { 0.3pt + luma(225) }),
      fill: (x, y) => if y == 0 { navy } else { none },
      table.header[Stage][LC: baseline → now][Full colour: baseline → now],
      ..r7t.rows.map(x => (x.stage, r7-cell(x.unit, x.lc), r7-cell(x.unit, x.fc))).flatten(),
      ..r7t.uux_ggggg_fc.rows.map(x => ([#x.stage #tiny[($u overline(u) -> 5g$)]], [—], r7-cell(x.unit, x))).flatten(),
    )
  },
) <rounds7>
#[
#set text(8.6pt)
#r7t.notes.map(x => [#upper(x.first())#x.slice(1).replace("~", "≈").replace("1.5x", "1.5×")]).join([. ]).
]

// =============================================================== STATUS ==
// The status page starts on its own page so that its two box rows are not
// split across pages.
#pagebreak(weak: true)
= Status at this milestone: M-LIT-a0 <status>

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
// The 2 -> 5 rows with a batched timing: gated ones and those without a
// matched provider (summary.json full_colour.gate_rule).
#let s-five = all-rows.filter(r => r.outgoing == 5 and s-main(r).status == "measured")
#let s-five-gated = s-five.filter(r => s-gate(r) != none)
#let s-five-free = s-five.filter(r => r in s-no-gate)
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
// M-QCD at a glance (data/mqcd-matrix.json, scripts/build_mqcd_matrix.py;
// data/mqcd-selftest.json).
#let mxc = mx.campaign.counts
#let mx-all = mx.classes
#let mx-max(f) = { let xs = mx-all.map(f).filter(v => v.value != none); xs.sorted(key: v => v.value).last() }
#let mx-dd = mx-max(c => c.dd_vs_reference)
#let mx-b64 = mx-max(c => c.binary64_vs_dd)
#let mx-cat = mx-max(c => c.catani_dd)
#let mx-pub = mx-all.map(c => c.public).flatten()
#let mx-pub-dd = calc.max(..mx-pub.map(p => p.dd_vs_reference))
#let st-virtual = st.pypi.checks.find(c => c.name == "physics-virtual")
#let st-ok = (st.pypi, st.community).all(x => x.checks.all(c => c.status == "pass"))
#let fft-seed = mx.fft.rows.filter(r => r.algorithm != "direct").map(r => r.seed_ratio)
#let fft-total = mx.fft.rows.filter(r => r.algorithm != "direct").map(r => r.total_ratio)
#let open-f = mx-all.map(c => c.findings).flatten().map(f => f.id).dedup()
// M-SM at a glance (data/msm-matrix.json, scripts/build_msm_matrix.py).
#let sxc = sx.campaign.counts
#let sx-pin = sx.campaign.branch.split(" ").at(1).slice(0, 8)
#let sx-rows = sx.classes.map(c => c.rows).sum()
#let sx-max(f) = { let xs = sx.classes.map(f).filter(v => v.value != none); xs.sorted(key: v => v.value).last() }
#let sx-dd = sx-max(c => c.dd_vs_reference)
#let sx-b64 = sx-max(c => c.binary64_vs_dd)
// Rule 4 in DD at its standard tolerance; the rows where the user's ruling
// of 2026-10-29 ~10:20 relaxes it, named apart (msm-matrix.json catani).
#let sx-cat = sx.catani.standard
#let sx-relaxed = sx.catani.relaxed
#let sx-partial = sx.rows.filter(r => r.status != "pass").map(r => r.row)
#let sx-cm07 = sx.cms.find(r => "U4" in r.features)
#let sx-ew-st = sx.selftest.virtuals.find(v => v.name == "physics-virtual-prepared").detail.split("MadLoop to ").last().split(" ").first()
#let ew-status = all-rows.filter(r => r.corrections == "EW" and r.full_colour.main.status == "measured")
// M-FINAL-b at a glance: decays (data/dec-matrix.json), HC_NLO_X0
// (data/hc.json), Recola correlations (data/corr.json), 2 -> 6 (summary.json
// preliminary).
#let dmc = dm.campaign.counts
#let dml = dm.largest
#let hc-ok = hcj.rows.filter(r => r.status == "pass")
#let hc-blocked = hcj.rows.filter(r => r.status == "blocked")
// HC05 comes from the mf-hc05 package record (one bound over every
// Laurent coefficient, `max_relative_deviation_all`, and its `record`).
#let hc-max = calc.max(..hc-ok.map(r => if "max_relative_deviation" in r { calc.max(..r.max_relative_deviation.values()) } else { r.max_relative_deviation_all }))
#let cr-born = calc.max(..crj.rows.map(r => calc.max(r.max_relative_deviation.tree_born, r.max_relative_deviation.virtual_born)))
#let cr-laurent = calc.max(..crj.rows.map(r => calc.max(r.max_relative_deviation.finite, r.max_relative_deviation.single_pole, r.max_relative_deviation.double_pole)))
#let cr-procs = crj.rows.map(r => r.process).dedup()
#box-note[
  #set par(justify: false)
  *On `loop`* (engine #ms.engine_revision\; merges since #ms.previous_loop, engine #ms.previous_engine)
  #v(-0.2em)
  #set text(7.9pt)
  #let half = calc.ceil(ms.integrated.len() / 2)
  #let pk(rs) = table(columns: (auto, auto, 1fr), stroke: none, inset: (x: 2pt, y: 1.4pt),
    ..rs.map(r => (raw(r.sha), text(weight: "semibold", r.wp.split(" ").last()), [#r.title])).flatten())
  #grid(columns: (1fr, 1fr), column-gutter: 10pt, pk(ms.integrated.slice(0, half)), pk(ms.integrated.slice(half)))
  #v(-0.3em)
  #text(7.6pt)[*Before (engine #ms.previous_engine):* #ms.already_on_loop.
    *Native build* #raw(ms.native_build.name) (digest #raw(ms.native_build.digest)…)#if g.slice_revision.slice(0, 8) != ms.engine_revision.slice(0, 8) [; G1 ran on #raw(g.slice_build) (engine #raw(g.slice_revision))].
    // Integrations after the measured engine (data/milestone.json after_integration).
    #let after = ms.at("after_integration", default: ())
    #if after.len() > 0 [*Integrated after it, not re-timed:* #after.map(r => [#raw(r.sha) #r.what (#r.detail)]).join("; ").]]
]

// M-LIT-a0, the first milestone push of M-LIT (m-lit/PLAN.md §3.2
// LIT-RETIME, §3.7 "Pushes"): the final G1 retime deferred from M-FINAL and
// the loop-induced summary table (every row pending).
#box-note(fill: white, stroke: 0.6pt + luma(205), breakable: false)[
  #set par(justify: false)
  *M-LIT-a0* (the first milestone push of M-LIT, loop-induced processes and the TIRust backend; user green light
  2026-11-06 \~07:05; `m-lit/PLAN.md` §3.2 LIT-RETIME)
  #v(-0.2em)
  #set text(7.9pt)
  - *The final G1 retime* (deferred from M-FINAL, `m-final/PLAN.md` §2.4): every G1 loop artifact regenerated
    (model compiler 17) and every G1 row re-timed on #raw(g.slice_revision) (#raw(g.slice_build)) with the G1
    protocol (finite part, $B = 128$, one pinned thread, checks off, providers' production records; no quiet
    window); the EW row is gated from now on; the $2 -> 6$ rows stay `data/2to6.json`'s. Not re-timed (LIT-RETIME's scope, which leaves out these rows of M-FINAL's MF-RETIME): the decay rows XX01–XX08 and HC01–HC04 (ungated) and the rescue level counts (indicative) keep their M-FINAL-b records (@dec, @tab:hc, the M-FINAL box). #if g.at("retime_vs_previous", default: none) != none [#g.retime_vs_previous.] This run is the baseline of every
    M-LIT no-regression A/B of the Born-interfered default (NinjaRS).
  - *The loop-induced summary table* (@tab:summary-li, `data/summary-li.json`): the #li-rows.len() process rows of
    the M-LIT validation matrix by multiplicity, #if li-served.len() == 0 [every row *pending*: no loop-induced
    package has landed at this push] else [#li-served.len() served]. Loop-induced requests are still refused typed
    (`loop-induced`) at this head.
]

// M-FINAL closing (lean close, slice-status DECISIONS 2026-11-05 ~07:35):
// what closed, the gate, the built-in SM fixes, dependencies and limits,
// the kept campaigns of M-FINAL-b, 2 -> 6; kept below M-LIT-a0.
#let a24 = mq.rows.find(r => r.id == "A24")
#let hc5 = hcj.rows.find(r => r.id == "HC05")
#let r7 = json("data/rounds-7leg.json")
#let r7-of(stage) = r7.rows.find(x => x.stage == stage)
#let r7-f(stage, acc, k) = { let x = r7-of(stage).at(acc); x.baseline.at(k) / x.now.at(k) }
#grid(columns: (1fr, 1fr), gutter: 8pt,
  block(width: 100%, stroke: 0.6pt + luma(195), inset: 9pt, radius: 3pt, {
    set text(8.2pt)
    set par(justify: false)
    [*M-FINAL, closed 2026-11-05* (engine #raw(ms.previous_engine)\; `m-final/PLAN.md`, the user's rulings of 2026-10-31 \~11:00, the lean close of 2026-11-05 \~07:30)]
    [
      - *Item 1, $2 -> 6$* (@tab:summary, #link(<sixlegs>)[records]): $g g -> 6g$ ($N_f = 5$, no top), $u overline(u) -> 6g$ and $u overline(u) -> u overline(u) g g g g$ at LC and full colour generated, stored (every step below 150 GB), loaded and evaluated on one engine (#raw(six.engine.revision.slice(0, 8)), an ancestor of the pin); every asserted internal check passes, no provider exists.
      - *Item 2, decays $1 -> n$* (M-FINAL-b, @dec): XX01–XX08 = MadLoop's quadruple precision, QCD and EW.
      - *Item 4:* the rescue stack (Python native evaluate API only; M-FINAL-b); HC_NLO_X0 #hc-ok.map(r => r.id).sorted().join(", ") = MadLoop 3.7.0 (@tab:hc; HC05 since mf-hc05); the optimisation rounds (#link(<rounds7>)[seven-leg table]: generation ÷#fixed(r7-f("generation total (wall, max peak)", "lc", 0), 1) LC / ÷#fixed(r7-f("generation total (wall, max peak)", "fc", 0), 1) FC, load resident ÷#fixed(r7-f("load (time, resident)", "lc", 1), 0) / ÷#fixed(r7-f("load (time, resident)", "fc", 1), 0), $B = 128$ peak ÷#fixed(r7-f("evaluation B = 128 (per point, peak)", "lc", 1), 1) / ÷#fixed(r7-f("evaluation B = 128 (per point, peak)", "fc", 1), 1), values bitwise); the Recola correlation oracles (M-FINAL-b). The final G1 retime followed at M-LIT-a0 (box above).
      - *Also since M-FINAL-b:* the SDK v4 extras (mf-sdk); lsimon125's PRs \#26 \#29 \#30 \#32 \#34 \#36 \#37 \#38 \#39 (\#24 adapted with credit): \#38 fixes a real 4× over-count of compiled-mode HEFT quark tree amplitudes (built-in SM-HEFT and HC_NLO_X0, now = MG5 and the MadLoop Borns), \#34 moves binary64 quark-line values by rounding only ($<= 10^(-12)$, accepted); the built-in SM fixes; the mechanical hard-coded limits lifted; Symbolica off the fork (boxes below).
      - *Validation scope:* the campaigns of M-FINAL-b (#raw(dm.campaign.slice): M-SM, M-QCD, decays, HC, correlations) stand, plus package evidence (A24 passes rule 4 with native Catani: mf-8g-3; HC05 = MadLoop: mf-hc05). The pin itself carries its integrators' targeted tests; the global tests run in CI on `loop` (no local whole-suite sweep, wheel self-test or retime: user 2026-11-05 \~07:30).
    ]
  }),
  block(width: 100%, stroke: 0.6pt + luma(195), inset: 9pt, radius: 3pt, {
    set text(8.2pt)
    set par(justify: false)
    [*Gate G1* (@g1; finite part, $2 -> 3$ and beyond)]
    [
      - *Re-timed at M-LIT-a0* (the final retime deferred from M-FINAL): every G1 row on #raw(g.slice_revision) (#raw(g.slice_build)), the EW row gated#if g.at("retime_vs_previous", default: none) != none [; #g.retime_vs_previous]. The evaluation and memory rounds of M-FINAL (#link(<rounds7>)[seven-leg table]) are in these cells now.
      - *Most recent configuration* (Table 1 and Figure 1): #s-ids.map(s-config).join([; ]) at $B = 128$:
        #s-with("pass").len() of #s-blocking.len() gated #if s-blocking.len() == 1 [process passes] else [processes pass]#if s-decided.len() > 0 [ (#s-decided.map(r => { let x = s-gate(r); [#math-label(r.math) by #x.decision (#fixed(x.ratio_to_limit, 2) of its limit, band #fixed(x.band.at(0), 2)–#fixed(x.band.at(1), 2))] }).join([, ]))]#if s-with("open").len() > 0 [, #row-names(s-with("open").map(r => r.key)) open]#if s-with("fail").len() > 0 [, #row-names(s-with("fail").map(r => r.key)) #if s-with("fail").len() == 1 [fails] else [fail]
        (#s-with("fail").map(r => [×#fixed(s-gate(r).ratio_to_limit, 2)]).join([, ]) of the limit)]#if s-thr.len() > 0 [; #row-names(s-thr.map(r => r.key)) #if s-thr.len() == 1 [runs] else [run] below 5 ms per point: *not gated* (user 2026-10-24\; #s-thr.map(r => fixed(s-gate(r).ratio_to_limit, 2)).join([, ]) of the limit)].
        $B = 1$ (16 lanes#if one-revs.len() > 0 [, the runs of #rev-list(one-revs), not re-timed]) is *reported*, not gated (user 2026-10-28): #ratio-range(one-lim) of the limit (@tab:g1batch).
#if s-five.len() > 0 [
      - *$2 -> 5$* (full and leading colour at $B = 128$; $B = 16$ reported): #s-five-gated.filter(r => s-gate(r).status == "pass").len() of #s-five-gated.len() gated
        rows pass (#s-five-gated.map(r => { let m = s-main(r); [#box(math-label(r.math))#if r.corrections == "EW" [ (EW)] #dur(m.seconds_per_point), #gratio(s-gate(r).ratio_to_limit) of its limit#if m.at("ratio_to_fastest_bound", default: none) == "lower" [, #ratio-mult(m) against #r.full_colour.fastest.name's upper bound]] }).join([\; ]))#for r in s-five-free [; #box(math-label(r.math)) #dur(s-main(r).seconds_per_point)#if "note" in s-main(r) [ (#s-main(r).note.label)] at full and #dur(r.leading_colour.main.seconds_per_point) at leading colour per point, no matched provider and no gate].
]
#if py-timed.len() > 0 [
      - *Before G-int* (Python per-point inputs, G1 at #rev-list(py-revs)\; history, @g1): failed every gated process it
        generated, at #ratio-range(py-big) of the binding limit at $B = 128$.
]
#if s-pending.len() > 0 [
      - *#row-span(s-pending.map(r => r.key)):* not timed yet (#s-pending.map(r => r.full_colour.main.package).dedup().map(raw).join(", "))#if s-no-gate.len() > 0 [\; #row-names(s-no-gate.map(r => r.key)) #if s-no-gate.len() == 1 [has] else [have] no matched provider].
]
    #if ew-status.len() > 0 [
      - *EW row* (`data/msm-g1.json`; gated since this retime, indicative at M-SM: [U5]): #ew-status.map(r => { let m = s-main(r); [#box(math-label(r.math)) (#r.corrections) #dur(m.seconds_per_point) per point at $B = 128$, #ratio-mult(m) of #r.full_colour.fastest.name's time#if s-gate(r) != none [, #gate-chip(s-gate(r))]] }).join([; ]) (@msm).
]
    ]
  }),
)

// The built-in SM fixes of mf-norm (049a9389) for the collaborator: the
// package report's table (slice-status UPDATE 2026-11-05 ~08:05; the
// factor wording of DECISIONS 2026-11-05 ~06:10 (c)).
#box-note(fill: white, stroke: 0.6pt + luma(205), breakable: false)[
  #set par(justify: false)
  *Built-in SM fixes* (tree level; mf-norm `049a9389`, with mf-limits-py `d958f2ea` for the initial-state averages): the built-in SM now equals the UFO `sm` in every lane. What was wrong, since when (2f876d1b, 2026-07-16, where the built-in model files enter this history, also on `origin/main`; 43e6fa5e, 2026-07-22) and by how much:
  #v(-0.2em)
  #{
    set text(6.9pt, font: sans, stretch: 87.5%)
    set par(leading: 0.35em)
    show table.cell.where(y: 0): set text(fill: white, weight: "bold")
    table(
      columns: (4.6cm, 2.4cm, 1.6cm, 1fr),
      align: left + horizon, inset: (x: 2.6pt, y: 2.0pt),
      stroke: (x, y) => (top: if y <= 1 { none } else { 0.3pt + luma(225) }),
      fill: (x, y) => if y == 0 { navy } else { none },
      table.header[Process class][Lanes][Since][Effect (old value against the UFO `sm`)],
      [every process without a coloured leg, decays included], [all], [`2f876d1b`], [too small by $1 slash (8 pi alpha)^2 = 27.797$ (old = $4 e^4 approx 0.036$ × correct); a run-time change of $alpha$ rescaled them with the wrong power],
      [initial $Z$ or $W$; initial Higgs], [all], [`2f876d1b`], [×3/2 per $Z$/$W$, ×1/2 per Higgs (spin averages; fixed by mf-limits-py)],
      [$W W gamma$ / $W W Z$ vertices and four-boson contacts], [recurrence], [`43e6fa5e`], [counted twice (old recurrence value against the compiled lane): $gamma gamma -> W^+ W^-$ ×16, $e^+ e^- -> W^+ W^-$ ×4 (the compiled lane itself lacked the neutrino exchange, next row), $u overline(u) -> W^+ W^-$ point-dependent],
      [$e^+ e^- -> W^+ W^-$; $e^+ e^- -> nu_e overline(nu)_e$], [all], [`2f876d1b`], [the $t$-channel neutrino exchange missing (e.g. 245× at one 500 GeV point); $nu_e overline(nu)_e$ refused (missing lepton/neutrino currents)],
      [electroweak exchange between quark lines], [all], [`2f876d1b`], [quark EW currents missing: QED-allowed requests silently gave the QCD-only value ($u overline(u) -> d overline(d)$: 1.445, 0.105, 1.079 × at three 700 GeV points); purely EW four-quark processes refused],
      [the $H H H H$ contact ($h h -> h h$, ...)], [compiled, eager, on-the-fly], [`2f876d1b`], [21.8, 97.8, 48.7 × at 700 GeV (and a further 1/27.797 before the colourless fix)],
      [the $H H V V$ contact ($h h -> Z Z$, $h h -> W^+ W^-$)], [all], [`2f876d1b`], [204, 11.4, 72 × and 381, 15.6, 121 × at 700 GeV],
    )
  }
  #v(-0.2em)
  #set text(7.9pt)
  *Regression test:* `tests/integration/test_builtin_sm_ufo_sweep.py` (default tier): every SM $2 -> 2$ process of the particle table (1993, reduced to 154 classes by crossing, charge-parity conjugation and the vertex-table relabellings), every $1 -> 2$ decay, 12 sample processes (seven $2 -> 3$, four $1 -> 3$, one $2 -> 2$) and three four-quark requests at explicit orders, in the compiled, eager, on-the-fly and recurrence lanes, against committed UFO `sm` values (MG5 3.7.0, `no_masses`) to $10^(-10)$ relative; where the UFO has no tree amplitude the built-in must refuse; a nightly variant runs 901 $2 -> 2$ processes against a freshly compiled UFO. Coloured processes: the compiled lane bitwise unchanged, the prepared lanes at ulp level ($<= 1.3 times 10^(-15)$, $9.6 times 10^(-14)$ at one ill-conditioned point; accepted). Typed refusals as the UFO `sm`: four-quark processes without gluon exchange in the recurrence lane, a massive top on a massless-$b$ line (`dirac-weyl-closure`). The one-loop engine is unaffected (it refuses the tree-only built-in SM).
]

#grid(columns: (1fr, 1fr), gutter: 8pt,
  block(width: 100%, stroke: 0.6pt + luma(195), inset: 9pt, radius: 3pt, {
    set text(8.2pt)
    set par(justify: false)
    [*M-SM, kept* (QCD + QED/EW on the shipped `loop_qcd_qed_sm(_Gmu)`; `m-sm/PLAN.md` §5; validated at M-FINAL-b, not re-run here: user 2026-11-04 \~17:35)]
    [
      - *Validation campaign* at #raw(sx-pin) (@msm, @tab:msmrows): #sx-rows rows in #sx.classes.len() classes, #sxc.pass pass, #sxc.partial partial, #sxc.fail fail (#sx-partial.join(", "): F7, accepted); no deviation above $10^(-5)$, no wrong pole or sector; against M-SM's campaign no status change and no deviation change above $10^(-5)$ (40 values in 8 rows moved by ≤ $7.4 times 10^(-11)$). Largest: DD from the reference #sci(sx-dd.value) (#sx-dd.row), binary64 from DD #sci(sx-b64.value) (#sx-b64.row), Catani DD #sci(sx-cat.value) (#sx-cat.row) at rule 4's standard tolerance (relaxed by the user's ruling: #sx-relaxed.map(r => [#r.row #sci(r.value) ≤ #sci(r.tolerance, d: 0)]).join(", ")).
      - *CMS* (@tab:cms): #sx.cms.len() rows = MadLoop CMS; the acceptance row #sx-cm07.row (#box(math-label(ap-math(sx-cm07.process)))) DD #sci(sx-cm07.dd_vs_reference), binary64 from DD #sci(sx-cm07.binary64_vs_dd), native inputs.
      - *Public route* on both shipped EW UFOs: `test_loop_v2_ew_public_models.py` #sx.public_route.tests.passed/#sx.public_route.tests.total at #raw(sx-pin)\; wheel self-test #if sx.selftest.passed [#sx.selftest.checks/#sx.selftest.checks] else [*failed*] in two fresh venvs, its EW virtual from the shipped prepared artifact = MadLoop to #sx-ew-st.
      - *EW products:* per-leg photon tagging (`loop.external_photons`, default `"final"`), poles `uv | ir | split` by the model's regulators, native complex pole masses, EW generation stages in Rust, binary64 of a stored artifact without Symbolica (@tab:caps).
    ]
  }),
  block(width: 100%, stroke: 0.6pt + luma(195), inset: 9pt, radius: 3pt, {
    set text(8.2pt)
    set par(justify: false)
    [*M-QCD, kept* (QCD on the stock `loop_sm`; `m-qcd/PLAN.md` §5; validated at M-FINAL-b, A24 from mf-8g-3)]
    [
      - *Campaign* at #raw(mx.campaign.campaign_head.split(" ").first()) (#mx.campaign.date, @mqcd, @tab:mqcdrows): #mx-all.map(c => c.rows).sum() rows, #mxc.pass pass, #mxc.partial partial, #mxc.fail fail#if open-f.len() > 0 [ (#open-f.join(", "), accepted)]. *A24* ($g g -> g g g g g$) passes since mf-8g-3: rule 4 with the native Catani operator from a stored QCD record (DD #sci(a24.max_catani_dd), binary64 #sci(a24.tiers.nightly.max_catani_binary64); rule 1 = NJet's DD to #sci(a24.max_dd_vs_reference); F11 resolved; the package's nightly record, re-run by its evidence audit on `2f3f76d9`). At M-FINAL-b, against M-SM's re-run, 42 of 1212 values moved, all binary64 (the largest, information only: A14's finite part against the providers $1.5 times 10^(-8) -> 5.6 times 10^(-8)$), every double-double value bitwise. Largest: DD from the reference #sci(mx-dd.value) (#mx-dd.row), binary64 from DD #sci(mx-b64.value) (#mx-b64.row), Catani DD #sci(mx-cat.value) (#mx-cat.row).
      - *At `e18a024b`* (not repeated: no status changed): public route on the shipped `loop_sm`, one row per class, DD from MadLoop ≤ #sci(mx-pub-dd)\; FFT seed contraction = direct to rounding, ×#fixed(calc.min(..fft-seed), 2)–#fixed(calc.max(..fft-seed), 1) of direct (@tab:fft). *Colour:* full colour by default; LC and NLC pass rule 7 on #mx-all.map(c => c.nc.rows.len()).sum() rows. *Ward* up to seven gluons (#ms.status_notes.notes.gg_ggggg.ward_status).
    ]
  }),
)

#grid(columns: (1fr, 1fr), gutter: 8pt,
  block(width: 100%, stroke: 0.6pt + luma(195), inset: 9pt, radius: 3pt, {
    set text(8.2pt)
    set par(justify: false)
    [*Dependencies* (`dependencies/manifest.json`; no fork: user 2026-11-02 \~19:00 / \~21:30)]
    [
      - *Symbolica* = symbolica-dev `community` `36cbac3a` plus the single consolidated PR symbolica-dev/symbolica\#163 (branch `loop_me_pyamplicol`, `20a9da94`, 6 commits; moves upstream once merged); the alphal00p fork is gone from the graph (mf-symbolica).
      - *NinjaRS* main `b3a29c85` (PRs \#7–\#12 and \#14 merged: UV residues from `ninjars::fast::TensorUvResidues`, the light-like spinors of \#10) and *oneloopmaster* main `128ea664`.
      - *Python:* the Community build of `20a9da94` or PyPI symbolica 3.0.3; every stored saved evaluator is canonical (referenced symbols only, numbered by name), so loop artifacts are byte-identical from either.
    ]
  }),
  block(width: 100%, stroke: 0.6pt + luma(195), inset: 9pt, radius: 3pt, {
    set text(8.2pt)
    set par(justify: false)
    [*Hard-coded limits* (mechanical ones: user 2026-11-04)]
    [
      - *Lifted:* Python (mf-limits-py `d958f2ea`): compile timeout and slots, exact rational charges and grouping factors, built-in SM $1 -> n$ decays, uncapped mappings and fixpoints, $N_c$ powers at any multiplicity; three tuning bounds became settings (`color.*`, `generation.validation.*`). Rust (mf-limits-rust `72fe20dc`): one rank admission from the reducer, one leg boundary 1–64, checked narrowing, the $S_m$ colour-FFT degree while $m!$ fits `usize`; values bitwise.
      - *Not supported* (generalisations; typed refusals, no milestone planned): rank $> N + 2$ (NinjaRS, oneloopmaster), multi-fermion loop vertices, coloured $n$-point EFT contacts, nested singlet contacts, octet/sextet fermions, an LC/NLC menu, binary64-only paths, C-API precision.
    ]
  }),
)

#grid(columns: (1fr, 1fr), gutter: 8pt,
  block(width: 100%, stroke: 0.6pt + luma(195), inset: 9pt, radius: 3pt, {
    set text(8.2pt)
    set par(justify: false)
    let sx6 = six.rows
    let of(k) = sx6.find(r => r.key == k)
    let g8 = of("gg_gggggg")
    let lcfc(r) = [#dur(r.leading_colour.seconds_per_point) / #dur(r.full_colour.seconds_per_point)]
    [*$2 -> 6$* (M-FINAL item 1, #flag[measured]; @tab:summary, #link(<sixlegs>)[records and checks])]
    [
      - *On one engine* (`data/2to6.json`; #raw(six.engine.revision), an ancestor of the pin), per point LC / FC: $g g -> 6g$ #lcfc(g8) (FC at $B = #g8.full_colour.batch$), $u overline(u) -> 6g$ #lcfc(of("uux_gggggg")), $u overline(u) -> u overline(u) g g g g$ #lcfc(of("uux_uuxgggg")); generation up to #dur(calc.max(..sx6.map(r => r.generation.main.seconds))) and #gib(calc.max(..sx6.map(r => r.generation.main.peak_gib))) (generate + plan export); every store step below #calc.ceil(calc.max(..sxj.rows.map(r => r.generation.step.peak_rss_gb)))~GB (budget 150 GB).
      - *Internal checks* (no reference exists): double pole, Catani (FC), NGluon (LC, 8 gluons), double-double and the quark rows' Ward pass; the 8-gluon LC Ward is recorded, not asserted (beyond the binary64 scope); at 8 gluons most points are rescue cases (binary64 $E > 10^(-5)$).
      - *Not run* (user, 2026-11-04): the 8-gluon full-colour and double-double Wards and the $u overline(u) -> 6g$ FC double-double Ward (\~17:35: enough evidence), the 8-gluon full-colour $B = 128$ timing (\~17:48).
    ]
  }),
  block(width: 100%, stroke: 0.6pt + luma(195), inset: 9pt, radius: 3pt, {
    set text(8.2pt)
    set par(justify: false)
    [*This milestone, M-LIT* (in progress; user 2026-11-03 \~21:15, green light 2026-11-06 \~07:05; `m-lit/PLAN.md`)]
    [
      - *Loop-induced processes* $|A_"loop"|^2$ (refused typed at this push, `loop-induced`): every row of @tab:summary-li pending.
      - *TIRust* (`huashengshao/TIRust`) as a tensor-integral reduction backend next to NinjaRS: the loop-induced default, on which the loop-induced speed gates are taken; M-LIT closes only when it lands.
      - *Done at M-LIT-a0:* the final G1 retime, with the EW speed gate binding.
    ]
  }),
)

#box-note(fill: white, stroke: 0.6pt + luma(205), breakable: false)[
    #set par(justify: false)
    *Missing or incomplete* (typed refusal keys, listed and shown by the dry run)
    #set text(7.9pt)
    #grid(columns: (1fr, 1fr), column-gutter: 12pt)[
    - *This milestone (M-LIT, in progress):* loop-induced processes, including loop-induced decays ($h -> g g$) and the
      loop-squared members of multiparticle requests (refused typed at this push, `loop-induced`; a multiparticle
      request generates its members with a Born and records the others as skipped; every row of @tab:summary-li
      pending), with TIRust as a tensor-integral reduction backend (the loop-induced default).
    - *Refused (typed):* decay chains and `$` (`madloop-syntax`); Majorana fermions (`majorana-fermion`) and
      multi-fermion contact vertices (`multi-fermion-contact`); numerical process-group analysis
      (`process-group-analysis`; exact aliases and members are served); photon-only and partial EW vetoes on the NLOCT
      UFOs (`veto-unlabelled-counterterms`: their counterterm couplings are not split by loop content); the
      complex-mass scheme for a width whose mass is an internal parameter (`cms-internal-mass`: `loop_sm`'s $W$), an
      external unstable species under CMS (`cms-external-width`), a Yukawa input under CMS (`cms-yukawa-input`); a width
      outside CMS (`electroweak-width`, `coloured-width`; a decaying particle has zero own width); tagged photons
      without an $alpha(0)$ input (`external-photon-scheme`); a spin-correlated leg without a vector source (refused at
      generation). HC_NLO_X0: $u overline(u) -> x_0 g g g$ (the U(1)-leak check), single-trace and C-odd five-point
      $R_2$ colours. *Tree level:* four-quark processes without gluon exchange in the recurrence lane (the other lanes
      serve them) and Dirac–Weyl currents the tree lanes cannot close (`dirac-weyl-closure`: a massive top on a
      massless-$b$ line), both as for the UFO `sm`.
    - *Not supported* (no milestone planned): reduction rank $> N + 2$ and the other capability generalisations of the
      limits box; helicity and colour-flow selection at NLC and full colour (LC has it; refused for mapped processes);
      the publication-grade timing campaign and the provider protocol-mode columns (user Q11).
    - *Not supported, by design:* EW LC/NLC (`colour-declaration-coverage`, permanent: user 2026-10-30; no plan to
      lift it).
    ][
    - *Accepted (validated at M-FINAL-b):* F7 — LL02 and SC02 partial (rule 4 not formed: the massive-muon $G_mu$ copy
      writes the field renormalisation of massless leptons; rule 1 = MadLoop); SC03's τ-mass relaxation of rule 4 to
      $10^(-5)$ (the EW counterterms omit the τ mass, the user's retained model limitation; MadLoop has the same
      offset); M-QCD's A09\@collinear (F7: typed `Unstable` / `CutFailed{DegenerateGram}`, never a value).
    - *Recorded test outcomes* (not gate failures; the integrators' records): `rusticol-capi`
      #[#show raw: set text(6pt); `static_c_api_advertises_all_symbolica_free_f64_capabilities`] fails as before
      mf-limits-rust (a legacy-JIT capability advertised); under PyPI symbolica 3.0.3 six double-double rows of
      `test_loop_v2_sdk_extras.py` differ at \~$10^(-30)$ relative (the Community build passes); the tree prepared-model
      kernels are not byte-reproducible run to run (operand order; their state sections are canonical).
    - *Compatibility notes:* the shipped EW UFOs are UFOmodeldb `6ca4b120` plus the user's issue-1 patch (PROVENANCE
      records the local delta); MadLoop never inserts R2_G0tt_b on the unpatched models (mg5amcnlo\#475): pyAmpliCol
      keeps the UFO-complete $R_2$ insertion (user Q7).
    - *No longer missing* (since M-FINAL-b): the $2 -> 6$ processes; HC05 ($g g -> x_0 g g$, its five-point $f f f f$
      $R_2$ contact); A24's rule 4 (native Catani); the built-in SM tree defects; NinjaRS's light-like spinors along
      $-z$ (\#10: the five xfails are plain cases, large unit factors keep the virtual); the alphal00p Symbolica fork;
      the SDK v4 extras. Earlier (M-FINAL-b): $1 -> n$ decays, permutation aliases and process-group members, Recola
      oracles of correlated Borns and virtuals, the stability rescue stack (Python API).
  ]
]
#block(width: 100%, stroke: 0.6pt + luma(195), inset: 9pt, radius: 3pt, breakable: false, {
  set text(8.4pt)
  set par(justify: false)
  [*Performance gates and timing protocol: definitions*]
  [
    - *Gate.* Faster than MadLoop and at most 1.30× each matched Recola and OpenLoops time, on the *finite part*, from
      $2 -> 3$ upward, *taken at $B = 128$ only* (user 2026-10-28, MASTER_PLAN §5.8: $B = 1$ and the $2 -> 5$ rows'
      $B = 16$ are measured and reported with their ratios, without a verdict; a configuration without a $B = 128$
      timing has none); $2 -> 2$ is reported without a gate. A process whose time per point at $B = 128$ is below 5 ms
      has no blocking gate: its ratio is shown, its verdict is "#thr-rule.label" (user decision; `data/milestone.json`
      `gate_decisions.threshold_rule`); optimisation effort goes to higher multiplicities. The electroweak row is timed
      and gated like the QCD rows since the final G1 retime (M-LIT-a0; `data/msm-g1.json`), after its indicative timing
      at M-SM ([U5]).
      Aspiration: fastest of all tools from $2 -> 3$.
    - *Protocol.* Providers in production mode with poles off where they allow it (OpenLoops `truepoles 0`, Recola without IR
      poles, MadLoop production build); pyAmpliCol finite-only (`poles = "none"`) with stability checks off, one pinned
      thread, binary64, 16 lanes, the same frozen points (pyAmpliCol receives their exact rationals, the providers their
      binary64 decimal text); since milestone m1025a pyAmpliCol's setup heap is frozen out of Python's cyclic collector
      before the warm-up (a loaded runtime holds no generation objects; in the committed harness since `de8d3eb8`, which
      times G1 at #raw(g.slice_revision)\; @g1). Statistic: median per point; the uncertainty band combines
      pyAmpliCol's block spread and the provider's repeat spread; a gate whose band contains the limit is *open*.
    - *Timing boundary.* pyAmpliCol: the public v2 runtime call (`NativeExecutor.evaluate`) for a batch of $B$ distinct
      points, everything included (per-point inputs, loop stage, assembly); the public `Runtime.evaluate` of a loaded artifact
      adds its input parsing (@g1). Providers have no batch API: one time per point
      serves every $B$. Generation: pyAmpliCol `LoopSlice.generate` plus the plan export, in G1 on one pinned core, cold (fresh cache
      directory) since `11542fd5` (m1026a)\; a
      development record's generation in @tab:summary ran on the #C.development_records.conditions_short (threads per increment:
      @tab:validation), without a multiplier in a G1 row; MadLoop graph generation, export and compilation; Recola process
      generation; OpenLoops libraries are prebuilt (no generation time).
    - *Labels.* @tab:summary and @fig:gate show the most recent measured configuration of each cell
      (main-configuration rule of `scripts/build_summary.py`; `data/summary.json` names the configuration and source of every
      value); the column header of @tab:summary states it once, with branch and commit, and "Reading the summary" says
      when it is a development measurement not yet on `loop`. The detailed G1 tables (@g1) show the configuration on `loop` and, labelled,
      its history: the runs of milestones M-SM (`71e2041e`), M-QCD (`e18a024b`), m1028a (`28a16255`), m1026a (`11542fd5`) and m1025a (`1d27426b`) and of G-int (`4e9b5a9e`), the
      Python per-point inputs before G-int and the development runs of
      #rev-list(l1-revs).
      Missing values are marked, never estimated or extrapolated; test durations are never used as event timings. The legacy per-diagram engine's timings of 18 October are history (data kept in
      `data/measurements.json`, not shown).
  ]
})

// ============================================================ M-FINAL-b ==
// The decay capability matrix (m-final/PLAN.md §2.2, MF-DEC-2):
// data/dec-matrix.json, written by scripts/build_dec_matrix.py from
// data/dec.json and the decay manifest; per-row data in the appendix
// (@tab:decrows). Then the HC_NLO_X0 rows (data/hc.json, scripts/build_hc.py)
// and the Recola correlation rows (data/corr.json, scripts/build_corr.py).
#pagebreak(weak: true)
// Matrix cells, chips and counts (also the QCD matrix and both appendices).
#let mq-chip(s) = {
  let (f, t) = (pass: (rgb("#e1f2ea"), pass-ink), accepted: (rgb("#eaf1e0"), rgb("#4d6b1f")), partial: (rgb("#fdf0dc"), amber), fail: (rgb("#f9e0da"), fail-ink)).at(s, default: (luma(240), luma(90)))
  box(fill: f, inset: (x: 2.2pt, y: 0.9pt), radius: 1.5pt, baseline: 0.9pt, text(6pt, weight: "bold", fill: t, s))
}
#let mq-counts(c) = ("pass", "partial", "fail", "pending", "not-run").filter(k => c.counts.at(k, default: 0) > 0).map(k => [#mq-chip(k)#h(1.5pt)#c.counts.at(k)]).join(h(3pt))
#let mq-ids(xs) = xs.join(", ")
#let fft-of(c) = mx.fft.rows.filter(r => r.name in c.fft)
#let mq-range(xs) = if xs.len() == 1 { fixed(xs.first(), 2) } else [#fixed(calc.min(..xs), 2)–#fixed(calc.max(..xs), 2)]
#let mq-cell(body) = table.cell(breakable: false, { set par(leading: 0.36em, justify: false); body })
#let mq-sub(body) = { v(1.6pt); block(spacing: 0pt, text(6pt, fill: ink2, body)) }
#let sm-model = (loop_qcd_qed_sm_Gmu: [$G_mu$], loop_qcd_qed_sm: [`qcd_qed_sm`], loop_qcd_qed_sm_Gmu_massive_muon: [$G_mu$, $m_mu$], loop_sm: [`loop_sm`])
#let sm-mod(m) = sm-model.at(m, default: raw(m))
#let ok-mark(b) = if b { text(fill: pass-ink, weight: "bold")[✓] } else { text(fill: fail-ink, weight: "bold")[✗] }
#let sm-rowlist(xs) = xs.map(x => [#x.row#if x.status != "pass" [ #mq-chip(x.status)]]).join(", ")
#let sm-case(c) = if c.case == "self-test" [self-test (#c.row)] else [#c.row]
#let dec-scheme = (qcd: [QCD, 5F], "qcd-4fs": [QCD, 4F], "ew-gmu": [$G_mu$], "ew-qcd-qed-sm": [$alpha(m_Z)$])
#let dec-chk(x) = if x == none [—] else [#x.status #ok-mark(x.status == "pass")]
= Decays $1 -> n$ (M-FINAL item 2) <dec>

#figure(kind: table,
  caption: [*Decay capability matrix* at #raw(dm.campaign.slice) (native #raw(dm.campaign.native.split(" ").first()), campaign of
    #dm.campaign.date; `data/dec-matrix.json` from `data/dec.json`; per-row data: @tab:decrows): every row against MadLoop's
    quadruple-precision reference of the same decay (MF-DEC-1 fixtures; the decaying particle at its real mass with zero own
    width, its absorptive self-energy dropped, as MadLoop does).],
  {
    set text(6.9pt, font: sans, stretch: 87.5%)
    set par(justify: false, leading: 0.35em)
    show table.cell.where(y: 0): set text(fill: white, weight: "bold")
    show raw: set text(6.1pt)
    table(
      columns: (0.85cm, 1.95cm, 1.15cm, 2.05cm, 2.15cm, 1.15cm, 1.15cm, 1.75cm, 1.2cm, 1.9cm, 1fr),
      align: (x, y) => if x in (5, 6) { right + horizon } else { left + horizon },
      inset: (x: 2.6pt, y: 2.4pt),
      stroke: (x, y) => (top: if y <= 1 { none } else { 0.3pt + luma(225) }),
      fill: (x, y) => if y == 0 { navy } else if calc.even(y) { luma(248) } else { none },
      table.header[Row][Process][Corr.][Model · scheme][Sectors][DD vs ML][b64/DD][Poles (DD)][LC/NLC][Public · inputs][Status],
      ..dm.rows.map(r => (
        [#text(weight: "bold", r.row) #tiny(r.multiplicity.replace("->", "→"))],
        text(8pt, font: "Libertinus Serif", math-label(ap-math(r.process))),
        r.corrections.join("+"),
        [#sm-mod(r.model)#if r.restriction != "default" [ #r.restriction] · #dec-scheme.at(r.scheme, default: r.scheme)],
        tiny(r.sectors.map(x => x.replace("^", "").replace("QCD0 ", "")).join(", ")),
        esci(r.dd_vs_reference), esci(r.binary64_vs_dd),
        [#esci(r.catani_dd) #tiny(r.poles)],
        if r.nc == none [—] else [$N_c$ scan #ok-mark(r.nc.status == "pass")],
        [#if r.public.len() > 0 [public #ok-mark(r.public.all(x => x.status == "pass"))]#if r.inputs == "native" [native inputs #ok-mark(true)]#if r.public.len() == 0 and r.inputs != "native" [—]],
        [#mq-chip(r.status)#if r.ward != none [ #tiny[Ward]]#if r.ff != none [ #tiny[form factor]]],
      )).flatten(),
    )
  },
) <tab:dec>

#[
#set text(9pt)
#let dff = dm.further.ff
#let dw = dm.further.ward
#let dnc = dm.further.nc
*Reading the matrix.* The decay campaign re-ran every row at the pin's Python tree (#raw(dm.campaign.slice), the native
#raw(dm.campaign.native)): #dmc.pass pass, #dmc.partial partial, #dmc.fail fail, as at its integration (no status change; the
largest metric change $7.9 times 10^(-31)$). Rows XX01–XX08 cover $1 -> 2$ and $1 -> 3$, QCD (`loop_sm`, five and four
flavours) and EW (QED and joint QCD+QED corrections on both shipped EW UFOs, $G_mu$ and $alpha(m_Z)$); the deviations are
the largest over every Laurent coefficient, sector, point and gating variant: DD from MadLoop's quadruple precision (rule 1),
binary64 from DD where binary64 is asserted (rule 2), the poles against Catani, plus the QED operator for EW corrections, in
DD (rule 4). XX02 runs on the native per-point inputs; XX01\@public and XX07\@public generate through `Generator` on the
shipped `loop_sm` and evaluate the stored artifact with the recommended checks. *Further checks:*
#dff.map(x => [#x.row: $Z -> u overline(u)$ (QCD) equals the analytic massless vector form factor (#x.tests test, #x.status)]).join([; ]);
#dw.map(x => [#x.row: the Ward identity on the external gluon of #box(math-label(ap-math(x.process))) (#x.checks checks; virtual #sci(x.virtual_dd) and Born #sci(x.born_dd) of the physical scale in DD, binary64 within its estimate)]).join([; ]);
#dnc.map(x => [#x.row]).join(" and "): LC and NLC are the kept powers of the $N_c$ scan (#dnc.map(x => x.tests).sum() tests, pass). Loop-induced decays are refused typed (`loop-induced`, e.g. $h -> g g$), chains and `$` too (`madloop-syntax`).
]

// HC_NLO_X0 rows (m-final/PLAN.md §2.4 MF-GM-HC): data/hc.json, written by
// scripts/build_hc.py from the campaign's test artifacts.
= Model genericity and correlation oracles (M-FINAL item 4) <genericity>

#let hc-dev(r, k) = esci(r.max_relative_deviation.at(k))
#figure(kind: table,
  caption: [*HC_NLO_X0 rows against MadLoop 3.7.0* (`data/hc.json`: the campaign rows at #raw(hcj.commit.slice(0, 8)), #hcj.native.split(" ").first(), `tests/unit/test_loop_v2_hc.py`
    #hcj.junit.values().filter(x => x == "passed").len()/#hcj.junit.len() passed#{ let rec = hcj.rows.filter(r => "record" in r).map(r => r.id); if rec.len() > 0 [; #rec.join(", ") from the mf-hc05 package record (integrated `e3d4ef4d`)] }): the Higgs characterisation UFO at NLO (v1.3) with its
    restriction and parameter cards ($kappa$ settings), the largest relative deviation #hcj.precision.split("; ").last() per
    Laurent coefficient (acceptance $10^(-5)$), the poles against Catani, the rotation estimate and double-double where run.],
  {
    set text(6.8pt, font: sans, stretch: 87.5%)
    set par(justify: false, leading: 0.35em)
    show table.cell.where(y: 0): set text(fill: white, weight: "bold")
    table(
      columns: (0.85cm, 2.2cm, 1.6cm, 1.2cm, 1.1cm, 1.1cm, 1.1cm, 1.1cm, 1.6cm, 1.15cm, 1fr),
      align: (x, y) => if x in (4, 5, 6, 7) { right + horizon } else { left + horizon },
      inset: (x: 2.6pt, y: 2.2pt),
      stroke: (x, y) => (top: if y <= 1 { none } else { 0.3pt + luma(225) }),
      fill: (x, y) => if y == 0 { navy } else { none },
      table.header[Row][Process][Restriction · veto][Pts · values][Born][Finite][$epsilon^(-1)$][$epsilon^(-2)$][Catani][Rotation][Status · DD],
      ..hcj.rows.map(r => if r.status == "blocked" {
        (text(weight: "bold", r.id), text(8pt, font: "Libertinus Serif", math-label(ap-math(r.process))), [#r.restriction#if r.particle_veto.len() > 0 [ · / #r.particle_veto.join(" ")]],
          table.cell(colspan: 8)[#mq-chip("blocked") typed #raw(r.refusal.key): #r.reason])
      } else if "record" in r {
        // A row from a package record (not this campaign's job): one bound.
        (text(weight: "bold", r.id), text(8pt, font: "Libertinus Serif", math-label(ap-math(r.process))), [#r.restriction#if r.particle_veto.len() > 0 [ · / #r.particle_veto.join(" ")]],
          [#r.points · #(2 * r.points)], table.cell(colspan: 4, align: center + horizon)[≤ #esci(r.max_relative_deviation_all) #tiny[(every coefficient)]],
          table.cell(colspan: 2)[#tiny[DD and rotation: the nightly row passed]],
          [#mq-chip(r.status) #tiny[mf-hc05 record]])
      } else {
        (text(weight: "bold", r.id), text(8pt, font: "Libertinus Serif", math-label(ap-math(r.process))), [#r.restriction#if r.particle_veto.len() > 0 [ · / #r.particle_veto.join(" ")]],
          [#r.points · #r.values], hc-dev(r, "born"), hc-dev(r, "finite"), hc-dev(r, "single_pole"), hc-dev(r, "double_pole"),
          { let c = r.catani_max_relative; let v = c.values().filter(x => x != none); [#esci(calc.max(..v))#if c.single_pole == none [ #tiny[($epsilon^(-2)$ only)]]] },
          esci(r.rotation_estimate_max),
          [#mq-chip(r.status)#if r.double_double != none [ DD #esci(r.double_double.vs_madloop)]])
      }).flatten(),
    )
  },
) <tab:hc>

#[
#set text(9pt)
The HC rows ran through the generic fixes of MF-GM-HC (`e2f0c78e`): the UFO namespace head, the Feynman-gauge refusal only
where massive vectors run in the loops (`ew_policy.require_loop_gauge`), positional UFO counterterm keys with zero extra
positions (other key lengths are the listed source refusal `ufo-counterterm-keys`) and a four-point contact with a colour-singlet
leg split through an adjoint auxiliary. #if hc5 != none and "record" in hc5 [#hc5.id (#box(math-label(ap-math(hc5.process))), refused typed at M-FINAL-b) passes since mf-hc05 (`e3d4ef4d`): #hc5.method\; binary64 = MadLoop 3.7.0 within #sci(hc5.max_relative_deviation_all) over every Laurent coefficient at #hc5.points points × 2 scales, and the nightly row with double-double and a rotation passed (the package's record, not re-run here; HC01–HC04 and HC06 bitwise unchanged). Still refused typed: $u overline(u) -> x_0 g g g$ (the U(1)-leak check) and single-trace or C-odd five-point $R_2$ colours.]#if hc-blocked.len() > 0 [ #hc-blocked.map(r => [#r.id (#box(math-label(ap-math(r.process)))) stays refused at
generation: the five-point $R_2$ contact `[G G G G X0]` carries the colour $f f f f$ that the tree colour flow holds only as the
multi-trace colour state of DESIGN §6.1, so the reachable vertex is refused, never dropped (addendum J); a recorded limitation
(optional row)]).join([; ]).]
]

// Recola correlation rows (m-final/PLAN.md §2.4 MF-CORR): data/corr.json,
// written by scripts/build_corr.py from the campaign's test artifacts.
#let cr-dev(r, k) = esci(r.max_relative_deviation.at(k))
#figure(kind: table,
  caption: [*Colour, spin and spin-colour correlations against Recola* (`data/corr.json` at #raw(crj.commit.slice(0, 8)),
    `tests/unit/test_loop_v2_corr_recola.py` #crj.junit.values().filter(x => x == "passed").len()/#crj.junit.len() passed;
    references #crj.reference): per process and kind the entries and points, the correlated Born of the tree engine and of the
    one-loop runtime relative to Recola's (acceptance $10^(-11)$), and the one-loop Laurent coefficients relative to the
    row's largest Recola coefficient (acceptance $10^(-8)$).],
  {
    set text(6.8pt, font: sans, stretch: 87.5%)
    set par(justify: false, leading: 0.35em)
    show table.cell.where(y: 0): set text(fill: white, weight: "bold")
    table(
      columns: (2.3cm, 1.7cm, 1.5cm, 1.4cm, 1.4cm, 1.4cm, 1.4cm, 1.4cm, 1fr),
      align: (x, y) => if x in (3, 4, 5, 6, 7) { right + horizon } else { left + horizon },
      inset: (x: 2.6pt, y: 1.9pt),
      stroke: (x, y) => (top: if y <= 1 { none } else if crj.rows.at(y - 1).process != crj.rows.at(y - 2, default: (process: none)).process { 0.5pt + luma(190) } else { 0.3pt + luma(232) }),
      fill: (x, y) => if y == 0 { navy } else { none },
      table.header[Process][Kind][Entries · pts][Tree Born][Loop Born][Finite][$epsilon^(-1)$][$epsilon^(-2)$][Status],
      ..crj.rows.map(r => (
        text(8pt, font: "Libertinus Serif", math-label(ap-math(r.recola_process.replace("->", ">")))), r.kind, [#r.entries · #r.points],
        cr-dev(r, "tree_born"), cr-dev(r, "virtual_born"), cr-dev(r, "finite"), cr-dev(r, "single_pole"), cr-dev(r, "double_pole"),
        mq-chip(r.status),
      )).flatten(),
    )
  },
) <tab:corr>

// ================================================================= M-SM ==
// The M-SM capability matrix and CMS table (m-sm/PLAN.md §5.2):
// data/msm-matrix.json, written by scripts/build_msm_matrix.py from
// data/msm.json, the campaign's public-route and self-test data and the
// manifest; the per-row data are in the appendix (@tab:msmrows). The G1 EW
// row: data/msm-g1.json (gated since M-LIT-a0).
#pagebreak(weak: true)
= Electroweak capability matrix (M-SM) <msm>

#figure(kind: table,
  caption: [*Electroweak capability matrix* at #raw(sx-pin), per class of `m-sm/PLAN.md` §1.1 (campaign of 2026-11-01/02 at the M-FINAL-b pin, M-SM's of 2026-10-31 re-run, on
    the shipped patched EW UFOs, `data/msm.json`; legend below the table, rows: @tab:msmrows).],
  {
    set text(7pt, font: sans, stretch: 87.5%)
    show table.cell.where(y: 0): set text(fill: white, weight: "bold", size: 7.2pt)
    show raw: set text(6.2pt)
    table(
      columns: (2.75cm, 1.55cm, 2.0cm, 1.6cm, 1.75cm, 2.05cm, 1.55cm, 1.6cm, 1fr),
      align: left + std.top, inset: (x: 3.5pt, y: 3.2pt),
      stroke: (x, y) => (top: if y <= 1 { none } else { 0.4pt + luma(215) }),
      fill: (x, y) => if y == 0 { navy } else if calc.even(y) { luma(248) } else { none },
      table.header[Class][Rows][Public route][DD vs ref.][binary64][Catani (DD)][Native inputs][CMS][Status],
      ..sx.classes.map(c => {
        let cat = c.catani_dd
        let out = c.binary64_vs_reference.rows_out_of_scope
        let fixtures = c.public.filter(x => x.madloop_fixture != none).len()
        (
          mq-cell[#text(8pt, weight: "bold", font: "Libertinus Serif", c.class) #mq-sub[#c.content#if c.max_outgoing != none [ · up to $2 -> #c.max_outgoing$] · #c.models.map(sm-mod).join(", ")]],
          mq-cell[#text(weight: "bold")[#c.rows] #mq-sub(mq-counts(c))],
          if c.public.len() == 0 { mq-cell[— #mq-sub[no public case]] } else {
            mq-cell[#c.public.map(sm-case).join(", ") #ok-mark(c.public.all(x => x.passed)) #mq-sub[bitwise the tools view#if fixtures > 0 [; #fixtures against MadLoop QP]]]
          },
          mq-cell[#text(weight: "bold", esci(c.dd_vs_reference.value)) #mq-sub[#c.dd_vs_reference.row#if c.dd_vs_reference.reference != "MadLoop" [ · #c.dd_vs_reference.reference]]],
          mq-cell[#text(weight: "bold", esci(c.binary64_vs_dd.value)) #mq-sub[#c.binary64_vs_dd.row · ref. #esci(c.binary64_vs_reference.value)#if out.len() > 0 [†]]],
          mq-cell[#if cat.value == none [—] else { text(weight: "bold", esci(cat.value)) } #mq-sub[#if cat.row != none [#cat.row]#for x in cat.not_formed [ · #x not formed]#for x in cat.no_predicted_sector [ · #x.row no sector (#x.reasons.join(", "))]#for x in cat.relaxed.filter(x => x.rule == "4dd") [ · #x.row ≤ #sci(x.tolerance, d: 0)]]],
          mq-cell[#if c.native_inputs.len() == 0 [—] else [#sm-rowlist(c.native_inputs) #ok-mark(c.native_inputs.all(x => x.status == "pass"))] #mq-sub[#if c.public.len() > 0 [public route: native] else [campaign rows]]],
          mq-cell[#if c.class == "W-CMS" [#c.cms.len() rows #ok-mark(c.cms.all(x => x.status == "pass")) #mq-sub[against MadLoop CMS (@tab:cms)]] else if c.cms.len() == 0 [—] else [#sm-rowlist(c.cms) #ok-mark(c.cms.all(x => x.status == "pass")) #mq-sub[same processes]]],
          mq-cell[#mq-chip(c.status) #if c.findings.len() > 0 { mq-sub[#c.counts.at("pass", default: 0) of #c.rows pass\; #c.findings.map(f => [#f.id #f.rows.join(", ") (#f.kind)]).join([; ])] }],
        )
      }).flatten(),
    )
  },
) <tab:msm>
#v(-0.3em)
#block(width: 100%, {
  set text(7.2pt, font: sans, stretch: 87.5%, fill: ink2)
  set par(justify: false, leading: 0.45em)
  [*Rows*: campaign rows and their status (passing every rule of their tier; partial: a rule not formed); class status
  *accepted*: every other row is a finding the coordinator accepted. Models: $G_mu$ = `loop_qcd_qed_sm_Gmu`,
  `qcd_qed_sm` = `loop_qcd_qed_sm` (both shipped: UFOmodeldb `6ca4b120` + the user's issue-1 patch), $G_mu$, $m_mu$ its
  massive-muon copy. *Public route*: the campaign's cases of `test_loop_v2_ew_public_models.py` (`Generator` on the
  shipped UFO with its shipped profile, `Runtime.load`, `evaluate`; Born and virtual bitwise the tools view at two
  points, and = MadLoop's quadruple precision where the case names a fixture) at the row of their process, and the wheel
  self-test's EW virtual from the shipped prepared artifact. *DD vs ref.*: largest relative deviation of the double-double
  Laurent coefficients (Born, finite, poles, every sector) from the row's reference (rule 1; MadLoop in quadruple
  precision, "double": its double-precision control exports). *binary64*: from DD where binary64 is asserted (rule 2,
  estimate $E <= 10^(-9)$); "ref." from the reference at every point (information; † the class has points with
  $E > 10^(-9)$, where DD is asserted). *Catani*: DD poles against the Catani operator (rule 4, every point and predicted
  sector; "≤" a tolerance relaxed by the user's ruling of 2026-10-29 \~10:20; "no sector": no predicted sector, typed
  reason in @tab:cms). *Native inputs*: the rows the campaign ran on the native per-point inputs (production route); the
  public route is native. *CMS*: the complex-mass rows of the class's processes.]
})

#[
#set text(9pt)
*Reading the matrix.* The campaign ran every row of its tier at the pin #raw(sx-pin) (native #raw(sx.campaign.natives.split(" ").first())) as whole test files, one process each: 23 nightly file jobs, four restriction-smoke files, the default tier and the campaign tier (TV07, its QCD twin and CM07 through the harness CLI), the manifest's points in binary64 and double-double (rules 1–4; rule 5 and the extras on the rows that name them; `m-sm/PLAN.md` §1.4 under the user's ruling of 2026-10-29 \~10:20: a deviation below \~$10^(-5)$ is not a finding). Its counts: #sxc.pass pass, #sxc.partial partial, #sxc.fail fail, #sxc.pending pending, #sxc.at("not-run") not run; the #sx.smokes_and_expansions.len() smokes and multiparticle expansions #if sx.smokes_and_expansions.values().all(x => x.status == "pass") [all pass] else [*do not all pass*]. The two partial rows are the accepted F7: rule 4 is not formed on the massive-muon $G_mu$ copy, which writes the field renormalisation of massless leptons (rule 1 = MadLoop). Notes of the campaign (`data/msm.json` `coverage_notes`): #sx.coverage_notes.join("; ").
]

// The CMS table (m-sm/PLAN.md §1.5, §5.2): every complex-mass row.
#let cms-w(w) = if w == none [card widths] else { w.pairs().map(((k, v)) => box[#k~#v]).join(h(3pt)) }
#figure(kind: table,
  caption: [*Complex-mass scheme against MadLoop CMS* (`data/msm-matrix.json` `cms`, from `data/msm.json` and the
    manifest): CM01–CM05 and CM07–CM10 at #raw(sx-pin) (CM06 was cut: its policy is an MS-CMS refusal test). Widths fixed
    at generation (GeV; "card widths": the restriction's), the per-point inputs, the points and checks (variants
    included), the largest deviation of double-double from MadLoop CMS (rule 1; quadruple precision, CM01 against its
    double-precision exports), binary64 from DD (rule 2), the poles against Catani in DD (rule 4) and the Ward identity
    in DD, a diagnostic only under CMS (`m-sm/PLAN.md` §1.4, §1.5). CM07 is the acceptance row ([U4]).],
  {
    set text(6.8pt, font: sans, stretch: 87.5%)
    set par(justify: false, leading: 0.35em)
    show table.cell.where(y: 0): set text(fill: white, weight: "bold")
    table(
      columns: (0.85cm, 2.45cm, 1.3cm, 3.5cm, 0.95cm, 1.1cm, 1.1cm, 1.1cm, 1.1cm, 1.1cm, 1fr),
      align: (x, y) => if x in (5, 6, 7, 8) { right + horizon } else { left + horizon },
      inset: (x: 2.8pt, y: 2.2pt),
      stroke: (x, y) => (top: if y <= 1 { none } else { 0.3pt + luma(225) }),
      fill: (x, y) => if y == 0 { navy } else { none },
      table.header[Row][Process][Model][Widths][Inputs][Pts · checks][DD][b64/DD][Catani][Ward (DD)][Variants · notes · status],
      ..sx.cms.map(r => (
        [#text(weight: "bold", r.row)#if "U4" in r.features [ #flag[U4]]],
        text(8pt, font: "Libertinus Serif", math-label(ap-math(r.process))),
        [#sm-mod(r.model)#if r.restriction != "default" [ #r.restriction]],
        tiny(cms-w(r.widths)),
        r.inputs,
        [#r.points · #r.checks],
        esci(r.dd_vs_reference), esci(r.binary64_vs_dd),
        if r.catani_dd == none [—] else { esci(r.catani_dd) },
        if r.ward_dd == none [—] else { esci(r.ward_dd.virtual) },
        [#r.variants.map(v => [#v.id.split("@").last()#if v.status != "pass" [ #mq-chip(v.status)]]).join(", ")#for u in r.unpredicted [#u.sector.replace("^", "") unpredicted (#u.reason) ]#mq-chip(r.status)],
      )).flatten(),
    )
  },
) <tab:cms>

// The G1 electroweak row (data/msm-g1.json): gated since the final G1 retime
// (M-LIT-a0; indicative at M-SM, [U5]).
#let ew-p = eg.processes.first()
#let ew-c = ew-p.pyamplicol.at("native/full")
#let ew-b = ew-c.batches.at("128")
#let ew-t = ew-b.median_seconds_per_point
#let ew-prov(n) = ew-p.providers.at(n).median_seconds_per_point
#let ew-rc = ew-prov("recola")
#let ew-early = ew-c.at("earlier_runs", default: ()).filter(e => e.at("batches", default: (:)).len() > 0)
#let ew-acc = ew-c.accuracy_check
#let ew-gen = ew-c.generation
#let ew-row = all-rows.find(r => r.key == ew-p.key)
#[
#set text(9pt)
*G1, electroweak row* (`data/msm-g1.json`, the gate tool on the EW records; gated since the final G1 retime, M-LIT-a0, after
its indicative timing at M-SM, [U5]). #box(math-label(ap-math(ew-p.label))) (EW) on #raw(eg.ew_model.split("/").last()) (the workspace's
Python-3 reference copy of `loop_qcd_qed_sm_Gmu`, the harness default; not the shipped patched UFO, which the campaign
used), native per-point inputs, full colour, binary64 finite part, checks off, one pinned core (#ew-c.host_cpus.map(str).join(", ")), at
$B = 128$: *#ms2(ew-t * 1000) ms per point* (±#fixed(100 * ew-b.uncertainty, 1) %) against Recola #dur(ew-rc), OpenLoops
#dur(ew-prov("openloops")) and MadLoop #dur(ew-prov("madloop")) (provider records reused, not re-run): ×#fixed(ew-t / ew-rc, 3) of Recola's
time, #fixed(ew-t / (eg.gate_factor * ew-rc), 3) of 1.30 × Recola, gate *#ew-b.gate.status*#if "ratio_to_binding_limit" in ew-b.gate [ (#fixed(ew-b.gate.ratio_to_binding_limit, 3) of the binding limit#if "band_to_binding_limit" in ew-b.gate [, band #fixed(ew-b.gate.band_to_binding_limit.at(0), 3)–#fixed(ew-b.gate.band_to_binding_limit.at(1), 3): pyAmpliCol's block spread plus the provider spread #fixed(100 * eg.host_provider_spread, 1)~%#if "host_provider_spread_source" in eg [, the G1 campaign's on the same host (`data/g1.json` `host_provider_spread`, the gate tool's `--host-spread`) for the single provider runs, as for the G1 rows]])] (Table 1 row, Figure 1). Generation #dur(ew-gen.generate.seconds) + #dur(ew-gen.export.seconds), peak
#gib(calc.max(ew-gen.generate.peak_gib, ew-gen.export.peak_gib)). Accuracy: against its fixture (#ew-acc.points points) #sci(ew-acc.max_error)
(DD asserted at point #ew-acc.double_double_points.map(str).join(", "), where $E > 10^(-9)$; binary64 #sci(ew-acc.max_error_binary64)); against the providers at #ew-row.validation.points stream points in binary64:
#ew-row.validation.references.map(x => [#x.short #sci(x.max_finite)]).join(", "). #if ew-early.len() > 0 [Earlier run (MS-VALIDATE, #raw(ew-early.last().revision.slice(0, 8))): #ew-early.last().batches.pairs().map(((b, x)) => [$B = #b$ #dur(x.median_seconds_per_point)]).join(", ").]
]

// ================================================================ M-QCD ==
// The QCD capability matrix (m-qcd/PLAN.md §5.2): data/mqcd-matrix.json,
// written by scripts/build_mqcd_matrix.py from data/mqcd.json and the
// campaign's public-route, FFT and self-test data; the per-row data are in
// the appendix (@tab:mqcdrows).
#pagebreak(weak: true)
= QCD capability matrix (M-QCD) <mqcd>

#figure(kind: table,
  caption: [*QCD capability matrix* at #raw(mx.campaign.campaign_head.split(" ").first()), per class of `m-qcd/PLAN.md`
    §1.1 (campaign of #mx.campaign.date, `data/mqcd.json`; legend below the table, rows: @tab:mqcdrows).],
  {
    set text(7pt, font: sans, stretch: 87.5%)
    show table.cell.where(y: 0): set text(fill: white, weight: "bold", size: 7.2pt)
    table(
      columns: (3.05cm, 1.75cm, 2.05cm, 1.55cm, 1.85cm, 2.0cm, 1.55cm, 1.85cm, 1fr),
      align: left + std.top, inset: (x: 3.5pt, y: 3.2pt),
      stroke: (x, y) => (top: if y <= 1 { none } else { 0.4pt + luma(215) }),
      fill: (x, y) => if y == 0 { navy } else if calc.even(y) { luma(248) } else { none },
      table.header[Class][Rows][Public route][DD vs ref.][binary64][Catani (DD)][LC/NLC][FFT][Status],
      ..mx.classes.map(c => {
        let fr = fft-of(c)
        let out = c.binary64_vs_reference.rows_out_of_scope
        let cat = c.catani_dd
        (
          mq-cell[#text(8pt, weight: "bold", font: "Libertinus Serif", c.class) #mq-sub[#c.content · up to $2 -> #c.max_outgoing$]],
          mq-cell[#text(weight: "bold")[#c.rows] #mq-sub(mq-counts(c))],
          mq-cell[#c.public.map(p => p.row.split("@").first() + if p.row.contains("public-") { "@" + p.row.split("-").last() } else { "" }).join(", ") #if c.public.all(p => p.passed) { text(fill: pass-ink, weight: "bold")[✓] } else { text(fill: fail-ink, weight: "bold")[✗] } #mq-sub[DD #esci(calc.max(..c.public.map(p => p.dd_vs_reference))) · #c.public.map(p => p.points).sum() pts]],
          mq-cell[#text(weight: "bold", esci(c.dd_vs_reference.value)) #mq-sub[#c.dd_vs_reference.row#if c.dd_vs_reference.reference != "MadLoop" [ · #c.dd_vs_reference.reference]]],
          mq-cell[#text(weight: "bold", esci(c.binary64_vs_dd.value)) #mq-sub[#c.binary64_vs_dd.row · ref. #esci(c.binary64_vs_reference.value)#if out.len() > 0 [†]]],
          mq-cell[#text(weight: "bold", esci(cat.value)) #mq-sub[#cat.row#for x in cat.not_formed [ · #x not formed]#for x in cat.no_predicted_sector [ · #x no sector]]],
          mq-cell[#if c.nc.rows.len() > 0 [rule 7 #if c.nc.status == ("pass",) { text(fill: pass-ink, weight: "bold")[✓] } else [#c.nc.status.join("/")] #mq-sub[#c.nc.rows.len() #if c.nc.rows.len() == 1 [row] else [rows] · smoke #c.nc.smoke_every_restriction]] else [smoke #c.nc.smoke_every_restriction #mq-sub[no rule-7 row]]],
          mq-cell[#if fr.len() > 0 [#text(weight: "bold")[×#mq-range(fr.map(r => r.seed_ratio))] #mq-sub[seed · #fr.len() #if fr.len() == 1 [row] else [rows]\; total ×#mq-range(fr.map(r => r.total_ratio))]] else [`auto` #mq-sub[no cost row]]],
          mq-cell[#mq-chip(c.status) #if c.findings.len() > 0 { mq-sub[#c.counts.at("pass", default: 0) of #c.rows pass\; #c.findings.map(f => [#f.id #f.rows.join(", ")#if f.accepted [ (accepted)]]).join([; ])] }],
        )
      }).flatten(),
    )
  },
) <tab:mqcd>
#v(-0.3em)
#block(width: 100%, {
  set text(7.2pt, font: sans, stretch: 87.5%, fill: ink2)
  set par(justify: false, leading: 0.45em)
  [*Rows*: campaign rows and their status (passing every rule of their tier; partial: a rule not formed); class
  status *accepted*: every other row is an open finding the coordinator accepted for the gate. *Public
  route* (at `e18a024b`): the class representative generated by `Generator` on the shipped `loop_sm`, `Runtime.load` and `evaluate`,
  against MadLoop (rules 1–3; Q-top and Q-multi by the campaign's public variants of $p p -> t overline(t)$). *DD vs
  ref.*: largest relative deviation of the double-double Laurent coefficients (Born, finite, poles, every sector) from
  the binding reference (rule 1; MadLoop in quadruple precision unless named). *binary64*: from DD where binary64 is
  asserted (rule 2, estimate $E <= 10^(-9)$); "ref." from the reference at every point (information; † the class has
  points with $E > 10^(-9)$, where DD is asserted). *Catani*: DD poles against the Catani operator (rule 4, every point and
  predicted sector). *LC/NLC*: rule 7 (formal-$N_c$ projection = $N_c$ scan, and MQ-NC's independent oracles) and the
  smoke on every shipped restriction. *FFT*: seed contraction FFT ÷ direct of the class's cost rows (@tab:fft); `auto`
  runs the certified FFT wherever the plan has a certified pair.]
})


#[
#set text(9pt)
*Reading the matrix.* The campaign ran every row of its tier at the pin as whole test files, one process each, the
manifest's points in binary64 and double-double (rules 1–4; rules 5–7 and the extras on the rows that name them;
`m-qcd/PLAN.md` §1.4 under the user's ruling of 2026-10-29 \~10:20: a deviation below \~$10^(-5)$ is not a finding).
Its counts: #mxc.pass pass, #mxc.partial partial, #mxc.fail fail, #mxc.pending pending, #mxc.at("not-run") not run. The two
non-passing rows are accepted limitations, not wrong values: A24 ($g g -> g g g g g$, F11) forms no rule 4 because the
seven-gluon colour-correlated trees exceed addendum H's memory budget, and its poles equal NJet's double-double values
(rule 1); A09 ($u overline(u) -> g g g$, F7) fails only through its collinear variant, where the executor returns typed
failures and no value (binary64 `Unstable` at $theta = 10^(-3)$–$10^(-5)$, DD `CutFailed{DegenerateGram}` at
$10^(-4)$, $10^(-5)$); A09 itself and its soft variant pass. D19 and C07 have no predicted pole sector (MQ-EWJOIN's
`separated-exchange` rule: their QCD loop selection omits IR-divergent loops, as MadLoop's does) and are checked against
MadLoop per split order. *Re-run at #raw(mx.campaign.campaign_head.split(" ").first())* (#mx.campaign.date): no status
or check count changed; against M-SM's re-run 42 of 1212 values moved, all binary64 (QCD-only rows too; likely the summation order of SymJIT 2.28.3, not proven; every double-double value bitwise; @status);
the public-route and FFT columns are M-QCD's runs at `e18a024b` (public route on a scratch manifest copy).
]

// FFT cost (data/mqcd-fft-cost.json through mqcd-matrix.json fft).
#let fft-s(x) = if x >= 100 [#fixed(x, 0)] else if x >= 1 [#sig(x)] else [#sig(x)]
#let fft-ms(x) = [#sig(1000 * x)]
#let fft-ratio(r) = table.cell(fill: ratio-fill(r), text(weight: "bold")[×#fixed(r, 2)])
#let fw = mx.fft.worst.max_by_carrier
#figure(kind: table,
  caption: [*FFT seed contraction against the direct one* (MQ-FFT, `color.contraction`): time for the batch of 128
    G1-stream points (binary64, poles none, checks off, one pinned thread; #raw("g g > u u~ d d~") on the six-gluon
    stream; one paired round, best of two below $2 -> 5$; indicative), FFT / direct and their ratio (green faster, red
    slower; Table 1's scale), for the whole evaluation and for the executor's seed-contraction stage. The values agree to
    rounding at stable points; at the cost runs' worst binary64 points (#mx.fft.worst.points point/carrier checks,
    binary64-unstable: $E$ up to $O(10^2)$) FFT − direct stays within #fixed(100 * fw.double.ratio_to_envelope, 1) % of
    the acceptance envelope $10 (E_"FFT" + E_"direct") + 16 u S$ in binary64 and within
    #fixed(100 * fw.at("double-double").ratio_to_envelope, 1) % in DD (relative ≤ #sci(fw.at("double-double").relative));
    `test_loop_v2_seed_fft.py` (default, nightly, seven legs) passed at `e18a024b`.],
  tstyle(table(
    columns: (3.0cm, 2.6cm, 1.1cm, 1.0cm, 2.9cm, 1.3cm, 2.9cm, 1.3cm),
    align: (x, y) => if x <= 1 { left + horizon } else { right + horizon },
    inset: (x: 4pt, y: 1.9pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][Class][group][pairs][evaluation, s][ratio][seed contraction, ms][ratio],
    ..mx.fft.rows.map(r => (
      text(8.4pt, font: "Libertinus Serif", math-label(r.process.split(" ").map(tok).join(" "))),
      tiny[#r.class#if r.algorithm == "direct" [ · no certified pair: direct]],
      [#if r.group_order == none [—] else { let k = ("2": 2, "6": 3, "24": 4, "120": 5, "720": 6, "5040": 7).at(str(r.group_order), default: none); if k == none [#r.group_order] else [$S_#k$] }],
      [#if r.pairs == none [—] else [#r.pairs]],
      [#fft-s(r.total_fft_s) / #fft-s(r.total_direct_s)],
      fft-ratio(r.total_ratio),
      [#fft-ms(r.seed_fft_s) / #fft-ms(r.seed_direct_s)],
      fft-ratio(r.seed_ratio),
    )).flatten(),
  )),
) <tab:fft>

#pagebreak(weak: true)
= Gate G1: end-to-end timings of the v2 engine <g1>

G1 times the complete Born–virtual evaluation, *finite part only*, through the
call of the public v2 runtime (`NativeExecutor.evaluate`, which
`V2VirtualRuntime` calls) with stability checks off, on one pinned core and
one thread, binary64, 16 SIMD lanes, in batches of $B$ distinct points of a
frozen stream (REQUIREMENTS_ADDENDUM D, plan §5.8); pyAmpliCol receives the
stream's exact rational points, the providers their binary64 decimal text.
#let py-lc-revs = revs-of(p => cfg(p, "python/lc"))
The configurations:

- *native inputs, on `loop`* — the engine at #raw(g.slice_revision) (milestone M-LIT-a0, the final G1 retime: M-FINAL's
  engine `c8885cc5` with the 1.0.2 release and its CI fixes, @status\; build #raw(g.slice_build), digest
  #raw(g.slice_native_digest.slice(0, 8))): the executor forms the trees, the Born and the counterterm inputs per
  point (binary64 SymJIT plane applications, tree closures in lanes of points), skips the counterterm interactions
  that only feed poles in finite-only mode, then runs the loop stage. #gname("gg_ggggg") is timed from its stored
  process. The public path (#gname("uux_ddxg"), `public_path_check` in `data/g1.json`): #g.public_path_check.
  *Values against the previous campaign* (`values_note`): #g.values_note. The timing runs evaluate every point with
  checks off. Earlier campaigns (M-SM `71e2041e`, M-QCD `e18a024b`, m1028a `28a16255`, m1026a `11542fd5`, m1025a
  `1d27426b`, G-int `4e9b5a9e`, the development campaign of #rev-list(l1-revs)) are `earlier_runs`, history;
- *Python inputs* #flag[history] — the engine on `loop` before G-int, G1 at
  #rev-list(py-revs)#if py-lc-revs.len() > 0 [ (LC at #rev-list(py-lc-revs))]: trees, Born amplitudes and
  counterterm scalars formed per point in Python, then the loop stage natively.

*Timing protocol at #raw(g.slice_revision)* (`timing_protocol` in `data/g1.json`): #g.timing_protocol. Host: #g.host.
#if g.at("retime_vs_previous", default: none) != none [*Against the previous campaign:* #g.retime_vs_previous.]

*Generation* (`generation_protocol`): #g.generation_protocol. The provider records are reused unchanged
(`provider_records`). The electroweak row is timed by the same protocol in `data/msm-g1.json` and gated (@msm); the
tables of this section are `data/g1.json`'s.

#let g7f-note = all-rows.find(r => r.key == "gg_ggggg").full_colour.main.at("note", default: none)
#if g7f-note != none [*Seven gluons, full colour* #flag[contention]: #gname("gg_ggggg")'s full-colour runtime was #g7f-note.reason (`seven_leg_rows`, `host` in `data/g1.json`; @tab:summary marks the cell). It has no gate.]

// A provider time outside the protocol (poles on) bounds its production time
// from above: a ratio taken against it is a lower bound (≥).
#let outside-p(p, n) = { let r = prov(p, n); r != none and r.at("protocol_mode", default: true) == false }
// earlier: a batch size this campaign did not re-time shows the newest
// earlier run that timed it (°, uncoloured: history; g1.json timing_protocol).
#let g1-cell(p, c, b, earlier: false) = {
  if refused(c) { return table.cell(text(6.4pt, fill: amber, style: "italic")[not generable]) }
  let x = bat(c, b)
  if x == none and earlier {
    let e = earlier-bat(c, b)
    let best = fastest-p(p)
    if e != none {
      let t = e.x.median_seconds_per_point
      return table.cell(text(fill: ink2)[#text(8pt, msec(t))° #h(1fr) #if best != none { text(7.2pt)[#mult2(t / best.t)] }])
    }
  }
  if x == none { return table.cell(text(6.6pt, fill: ink2, style: "italic")[not timed]) }
  let t = x.median_seconds_per_point
  let best = fastest-p(p)
  let r = if best == none { none } else { t / best.t }
  table.cell(fill: ratio-fill(r), {
    text(8pt, weight: "bold", msec(t))
    h(1fr)
    if r != none { text(7.2pt, weight: "semibold")[#if outside-p(p, best.n) [≥]#mult2(r)] }
  })
}
#let p-cell(p, n) = {
  let t = ptime(p, n)
  let r0 = prov(p, n)
  if t == none {
    let why = if r0 == none [not timed] else if "unavailable" in r0 { if r0.unavailable.starts-with("no generation") [not generated] else if n == "openloops" [no library] else [not exported] } else [not timed]
    return table.cell(text(6.6pt, fill: ink2, style: "italic", why))
  }
  let best = fastest-p(p)
  let r = t / best.t
  let outside = r0.at("protocol_mode", default: true) == false
  // A time outside the protocol bounds the provider's production time from
  // above (≤); a ratio taken against such a time is a lower bound (≥).
  table.cell(fill: ratio-fill(r), {
    text(8pt, weight: "bold")[#if outside [≤ ]#msec(t)]
    h(1fr)
    if best.n == n { if not outside { text(6.6pt, fill: ink2)[fastest] } } else { text(7.2pt, weight: "semibold")[#if outside-p(p, best.n) [≥]#mult2(r)] }
    if outside { linebreak(); text(6.2pt, fill: ink2)[(outside protocol, poles on: upper bound)] }
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
  let d-word = if d == none and b == "1" and one-ratio(nat-c(p)) != none { text(fill: ink2)[reported #gratio(one-ratio(nat-c(p)))°] } else { gate-word(p, nat-c(p), b, d) }
  table.cell(text(6.8pt)[#if refused(py-c(p)) { text(fill: ink2)[—] } else { gate-word(p, py-c(p), b, a) } #linebreak() #d-word])
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
    configuration runs below 5 ms per point at $B = 128$ (user rule of 2026-10-24; ratio as measured)\; *reported*:
    the verdict is taken at $B = 128$ only, so the $B = 1$ ratios are measured and shown without a verdict (user
    2026-10-28; bands: @tab:g1batch)#if one-revs.len() > 0 [\; ° native $B = 1$: the run of #rev-list(one-revs), not
    re-timed at #raw(g.slice_revision) (uncoloured, history; its ratio over this campaign's limit)].],
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
          tiny[$2 -> #p.outgoing$#if not p.gated [, no gate#if p.outgoing > 2 [ (no matched provider)]]]
        }),
        [1], g1-cell(p, a, "1"), g1-cell(p, d, "1", earlier: true), ..pnames.map(n => p-cell(p, n)), gate-cell(p, "1"),
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
#core-span(prov-cores)), not re-run since, and for the $2 -> 5$ rows
the production-mode runs of package `measure-g1-7leg` (25 October, each provider with its production Collier cache:
on for Recola's COLLIER 1.2.8 and OpenLoops, off for MadLoop's COLLIER 1.2.9 with its seven-leg cache defect;
$u overline(u) -> g g g g g$ imported from the reference campaign's three points); pyAmpliCol ran on
#nat-cores.len() cores between #nat-cores.first() and #nat-cores.last() (per run: `host_cpus` in `data/g1.json`) on
#g.date, at most one job per eight-core group sharing an L3 cache, each on the least busy core of a group whose least
busy core was below 50 % busy, while the milestone's whole-suite gate and other users' processes loaded the host
(`host` in `data/g1.json`: #g.host.split("; ").at(1, default: "")).
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
      return table.cell(text(fill: ink2)[#text(7.6pt, style: "italic")[#gratio(e.x.median_seconds_per_point / lim-big.gate.binding_limit)°] #h(1fr) #tiny[#msec(e.x.median_seconds_per_point) ms]])
    }
  }
  if x == none { return table.cell(dim[—]) }
  let gt = x.gate
  if "band_to_binding_limit" not in gt { return table.cell(tiny[#gt.status]) }
  let (lo, hi) = gt.band_to_binding_limit
  let st = eff-status(p, c, b, gt)
  // Reported (every B but 128, user 2026-10-28): ratio and band in a neutral,
  // uncoloured cell, no verdict word.
  if st == reported {
    return table.cell({
      text(7.6pt)[#gratio(gt.ratio_to_binding_limit)]
      h(1fr)
      tiny[#gratio(lo)–#gratio(hi)]
    })
  }
  table.cell(fill: if st == "pass" { rgb("#e1f2ea") } else if st == "fail" { rgb("#fbe3dd") } else if st == "not gated" { neutral } else { warm }, {
    text(7.6pt, weight: "bold")[#gratio(gt.ratio_to_binding_limit)#if st != "not gated" and decision(p, b, gt) != none [‡]]
    h(1fr)
    tiny[#gratio(lo)–#gratio(hi)]
  })
}
// The single verdict repeat of plan §5.8 item 10 times every batch size
// (8 and 32 too); an earlier run at the configuration's own revision without
// them is a host-contention repeat (m1028a's round 1, g1.json host), not one.
#let repeated = gated.filter(p => first-run(nat-c(p)) != none and bat(nat-c(p), "8") != none)
#let contention-repeated = gated.filter(p => first-run(nat-c(p)) != none and p not in repeated)
#let earlier-revs = gated.map(p => ("1", "8", "16", "32").map(b => if bat(nat-c(p), b) == none { earlier-bat(nat-c(p), b) } else { none })).flatten().filter(e => e != none).map(e => e.rev).dedup()
// The configurations of this table without a B = 128 timing: no verdict
// (g1.json configuration gate "missing", with its reason).
#let l1-missing = gated.map(l1-c).filter(c => c != none and c.at("gate", default: (:)).at("status", default: none) == "missing").map(c => c.gate.reason).dedup()
#let five-gated = gated.filter(p => bat(nat-c(p), "16") != none)
#figure(kind: table,
  caption: [*The gate at every batch size* (native inputs on `loop`, full
    colour): time over the binding limit and its uncertainty band. *The speed gate is taken at $B = 128$
    only* (user 2026-10-28, MASTER_PLAN §5.8; `data/milestone.json` `gate_decisions.gate_batch`): only that column has
    a verdict and a colour (green pass, red fail, amber open, grey not gated: below 5 ms per point at $B = 128$, user
    rule of 2026-10-24#if nat-decided.len() > 0 [; ‡ pass by user decision, the band containing the limit:
    #decided-text(nat-decided)]); every other batch size is *reported*: measured, its ratio and band shown in a white
    cell, no verdict. $B = 1$ is timed with the default 16 lanes (a one-point call pays a 16-lane chunk); the one-lane
    column is the development campaign's (#rev-list(l1-revs), history: the public path always runs 16 lanes in
    binary64)#if l1-missing.len() > 0 [, a configuration without a $B = 128$ timing and therefore without any verdict
    (gate missing: #l1-missing.join([; ]))]. This campaign timed #if one-revs.len() > 0 [$B = 128$ only] else [$B = 1$ and $B = 128$#if five-gated.len() > 0 [, and
    $B = 16$ and 128 for the $2 -> 5$ rows]]#if contention-repeated.len() > 0 [; the #row-span(contention-repeated.map(p => p.key)) rows twice, the
    second round deciding (a host-contention repeat, round 1 in `earlier_runs`: @g1)]#if repeated.len() > 0 [, and every batch size only for the single repeat of
    #names(repeated) (its first run, #repeated.map(p => { let x = first-run(nat-c(p)).batches.at(big); [#msec(x.median_seconds_per_point) ms at $B = 128$] }).join([; ]), was open at the limit: `repeats` in `data/g1.json`)] else [ (no verdict was open, so no repeat: `repeats` in `data/g1.json`)]#if earlier-revs.len() > 0 [; ° grey: the earlier
    run of #rev-list(earlier-revs) at that batch size, its median over the same binding limit with its time (no band;
    an earlier engine under the committed protocol; history)].],
  tstyle(table(
    columns: (2.9cm, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr),
    align: left + horizon, inset: (x: 4pt, y: 2.6pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][$B = 1$, 16 lanes][$B = 1$, 1 lane #text(6pt, weight: "regular")[(#l1-revs.join(", "))]][$B = 8$][$B = 16$][$B = 32$][$B = 128$ (gate)],
    ..gated.map(p => (gname(p.key), band-cell(p, nat-c(p), "1", earlier: true), band-cell(p, l1-c(p), "1"),
      band-cell(p, nat-c(p), "8", earlier: true), band-cell(p, nat-c(p), "16", earlier: true), band-cell(p, nat-c(p), "32", earlier: true), band-cell(p, nat-c(p), "128"))).flatten(),
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

// Providers whose time is only an upper bound of their production time.
#let bounded-n(p) = pnames.filter(n => { let r = prov(p, n); r != none and "production_upper_bound" in r })
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
    after the single repeat)]#if nat-ungated.len() > 0 [. *Not gated* (below 5 ms per point, user decision of 2026-10-24; ratios as measured): #ungated-text(nat-ungated)]. $B = 1$ (16 lanes)
    and the $2 -> 5$ rows' $B = 16$ are *reported* without a verdict (user 2026-10-28): $B = 1$ at
    #ratio-range(one-lim) of the limit (a one-point call pays a 16-lane chunk, @tab:g1batch)#if l1-lim.len() > 0 [; with
    one lane per call, in the development runs of #rev-list(l1-revs) (history), #ratio-range(l1-lim)].
  - *Python inputs* #flag[history] (the engine before G-int, G1 at
    #rev-list(py-revs)): failed every process it generated, at $B = 128$ at
    #ratio-range(py-big) of the binding limit, the per-point Python inputs
    taking #pct-range(inputs-share) of its time (@tab:g1split); at $B = 1$ at
    #ratio-range(py-one), where #names(py-one-only) were timed only. It did
    not generate #names(py-refused) (Furry zeros, WP3.5; $Z$ fermion signs,
    WP3.2).
  - *Fastest of all tools* (aspiration), native inputs at $B = 128$, within
    the uncertainty band: faster than every provider for
    #names(gated.filter(p => fast-word(p) == "faster" and bounded-n(p).len() == 0))#{
      let fb = gated.filter(p => fast-word(p) == "faster" and bounded-n(p).len() > 0)
      if fb.len() > 0 [\; faster than every provider with a production-mode time for #fb.map(p => [#gname(p.key) (#pshort(bat(nat-c(p), big).gate.fastest_provider)#for n in bounded-n(p) [; #pshort(n) has only an upper bound of its production time, ≤ #sig(ptime(p, n)) s])]).join([, ], last: [ and ])]
    }\; at parity with the
    fastest for #names(gated.filter(p => fast-word(p) == "parity"))\; slower
    than the fastest for #{
      let sl = gated.filter(p => fast-word(p) == "slower")
      if sl.len() == 0 [none] else { sl.map(p => [#gname(p.key) (#pshort(bat(nat-c(p), big).gate.fastest_provider))]).join([, ], last: [ and ]) }
    }.
    NJet, not a matched provider, takes #ms.njet.rows.find(r => r.label == "g g -> g g g g").n312_std s (NJet 3.1.2) for its two-evaluation
    full-colour $g g -> g g g g$ test (@tab:njet).
  - Seven-leg rows ($u overline(u) -> e^- e^+ d overline(d) g$, $u overline(u) -> e^- e^+ g g g$,
    $g g -> t overline(t) e^- e^+ g$, $u overline(u) -> g g g g g$, $g g -> g g g g g$)
    are generated by the WP3.1 generator, on `loop` since G-int, and timed by
    G1 since package `measure-g1-7leg` (full and leading colour at $B = 16$ and 128; re-timed at #raw(g.slice_revision))#if s-no-gate.len() > 0 [; #row-names(s-no-gate.map(r => r.key)) #if s-no-gate.len() == 1 [has] else [have] no matched provider timing
    (addendum F, H): reported without a gate].
]

#let sp-int = speedup-at("1")
// One stage share per gated row, native inputs at B = 128.
#let nat-shares(f) = gated.map(p => f(bat(nat-c(p), big)))
#let sp-big = speedup-at(big)
#block(breakable: false)[#figure(kind: table,
  caption: [*Levers*, measured on the gated rows of @tab:g1split ($2 -> 3$ and beyond; shares at $B = 128$). Gains are
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
    [$B = 1$: one 16-lane chunk per call ($B = 1$ is reported, not gated: user 2026-10-28)],
    [measured: #ratio-range(lanes-gain) at $B = 1$ (16 lanes on `loop` ÷ 1 lane of #rev-list(l1-revs), different builds)],
    [executor policy (WP3.1 or wave 4)],
    [*Finite-only result path* (sum the virtual natively, no per-family lane export, Python assembly only for checks and observables)],
    [glue #pct-range(nat-shares(x => share(x, glue(x)))) of the native-input time; skipping the pole-only counterterm
      interactions natively (generation-scale-2's I5 record) saved 2–5 % of the total at $u overline(u) -> g g g g$ and
      $g g -> g g g g$],
    [up to the share (largest at $2 -> 3$ with quarks)],
    [in part on `loop` (generation-scale-2); next `plan_export`, executor (wave 4)],
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
) <tab:levers>]

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
it; measured #udx.gate.at("measured_status", default: udx.gate.status), band #fixed(udx.gate.band_to_binding_limit.at(0), 2)–#fixed(udx.gate.band_to_binding_limit.at(1), 2)). The question whether G1 should pass the points as exact rationals (the
protocol) or as the binary64 text the providers read is moot under this
rule, and the protocol stays. For information only (not G1
configurations, no verdict formed from them): on #raw(g.slice_revision) the public
`Runtime.evaluate` of the loaded artifact (poles off, core 221) takes 11.71 ms per point at $B = 1$ and 2.01 ms at
$B = 128$ for #gname("uux_ddxg"), against the campaign's #dur(bat(nat-c(gproc("uux_ddxg")), big).median_seconds_per_point) of the harness's executor at $B = 128$ (core 147) and
1.98 ms in its smoke run, on other cores and at other times (`public_path_check` in `data/g1.json`, the campaign's
`STATE.md`; M-QCD's run, 2.20 ms on a busy host, was 1.83 ms at m1028a); at G-int
(`4e9b5a9e`, committed protocol) a paired run (one core, ten alternating rounds) gave 1.68 ms on the binary64 text
against 2.29 ms on the exact points (×0.73; #gname("uux_uuxg"): 2.94 against 3.39 ms, ×0.87).

== Leading colour <lc>

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
// A leading-colour value that is a cost measurement only (milestone.json
// cell_notes kind "not validated", through summary.json): marked in the
// native largest-batch cell.
#let lc-unvalidated(p) = { let r = all-rows.find(r => r.key == p.key); r != none and r.leading_colour.main.at("note", default: (kind: none)).kind == "not validated" }
#block(breakable: false)[#figure(kind: table,
  caption: [*Leading colour* (LC), ms per point, same protocol as @tab:g1; in
    each cell the full-colour (FC) time of the same configuration and batch, and LC/FC.
    No provider ratio: the providers time full colour. LC uses the committed
    QCD colour continuation (`examples/loop/source_colour`)#if lc-vjets.len() > 0 [; the $V$+jets rows are
    timed at LC with native inputs only]. This campaign timed LC at $B = 128$#if lc-earlier-revs.len() > 0 [; ° grey: the
    earlier run of #rev-list(lc-earlier-revs) at $B = 1$ with its FC time (an earlier engine under the committed
    protocol; history)]#if g.processes.any(lc-unvalidated) [; amber: a cost measurement whose LC value is not validated
    (identical-flavour quark lines, below)].],
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
      let nat-big = big-cell(dl, df)
      if lc-unvalidated(p) { nat-big = table.cell[#nat-big.body #linebreak() #text(6.2pt, fill: amber, weight: "bold")[cost only: value not validated (identical-flavour LC)]] }
      (gname(p.key), lc-cell(p, al, af, "1"), big-cell(al, af), lc-cell(p, dl, df, "1", earlier: true), nat-big)
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
#let lc-five = all-rows.filter(r => r.outgoing == 5 and r.leading_colour.main.status == "measured").map(r => (r: r, x: r.leading_colour.main.lc_over_fc)).sorted(key: v => v.x)
#if lc-five.len() > 0 [
The $2 -> 5$ rows follow: LC/FC
#fixed(lc-five.first().x, 2)–#fixed(lc-five.last().x, 2) at $B = 128$ (#lc-five.map(v => [#box(math-label(v.r.math)) #fixed(v.x, 2)]).join([, ])).
]
#let g7f = nat-c(gproc("gg_ggggg"))
#let g7l = cfg(gproc("gg_ggggg"), "native/lc")
#if g7f != none and g7l != none and g7l.structure.families >= g7f.structure.families [
At seven gluons the stored LC plan of #gname("gg_ggggg") keeps all #group(g7l.structure.families) full-colour loop
families, where the lower gluon multiplicities halve them (#("gg_ggg", "gg_gggg").map(k => [#group(nat-c(gproc(k)).structure.families) → #group(cfg(gproc(k), "native/lc").structure.families)]).join([ and ]) at five and six gluons, with the top).
This is not a defect (DESIGN §7.9): a family is keyed by its propagators' momenta and masses, so a closed massless-quark
loop shares its family with the gluon and ghost rings, and the prune drops a family only when none of its skeletons is
live; with the top the families halve, under this generation's `particle_veto = [t]` they cannot, while the tries shrink
alike. The LC plan generates in #minutes(g7l.generation.generate.seconds) against
#minutes(g7f.generation.generate.seconds) at full colour (`LoopSlice.generate` alone; on `1d27426b` 40.6 against
37.9 min).#if "note" in all-rows.find(r => r.key == "gg_ggggg").full_colour.main [ Its LC/FC pairs the LC run of
26 October with the full-colour re-run of 27 October on a busier host (about 15 % contention, see the timing protocol).]
]

#let uu-row = all-rows.find(r => r.key == "uux_uuxg")
#if uu-row != none and "note" in uu-row.leading_colour.main [

*Identical-flavour quark lines* #flag[known limitation]: G1's LC timing of #gname("uux_uuxg")
(#dur(uu-row.leading_colour.main.seconds_per_point) per point at $B = 128$, @tab:summary and @tab:g1lc) is marked:
#uu-row.leading_colour.main.note.reason.
] else if uu-row != none and uu-row.leading_colour.main.status == "measured" [
#let uu-lc = cfg(gproc("uux_uuxg"), "native/lc")
#let uu-old = earlier-at(uu-lc, big, "11542fd5")

*Identical-flavour quark lines*: since identical-flavour-lc (`5cb5ea83`, milestone m1028a) the leading and
next-to-leading colour of processes with identical-flavour quark lines (from #gname("uux_uuxg") up, any number of lines)
are exact formal-$N_c$ projections: the loop-request blocks and the counterterm program split by U(1)-subtraction $N_c$
grade in the Python and Rust lanes, with order-free block grades (second genericity audit, G2-M1; validated against the
legacy engine's LC and NLC, now frozen captures, and since MQ-NC by rule 7 against $N_c$ scans and independent oracles,
@mqcd). G1's LC of #gname("uux_uuxg") is a validated value (#dur(uu-row.leading_colour.main.seconds_per_point) per
point at $B = 128$).
]
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
    the NinjaRS model R × #fixed(calc.min(..g.estimates.map(e => e.ninjars_over_model.at(0))), 3)–#fixed(calc.max(..g.estimates.map(e => e.ninjars_over_model.at(1))), 3) (the band
    this campaign measures, @tab:g1rate) and
    the measured outer factor of the row's class representative at $B = 128$
    with native inputs (same colour where measured#if g.estimates.any(e => e.outer_inferred) [; rows whose class
    was not measured at their colour take the FC factor, marked †]). Measured: G1's own time where the row
    was timed. Gate: G1's binding limit at the row's largest batch where G1
    timed the providers (1.3× the fastest production provider, or MadLoop's
    time where it binds), else 1.3× the best production provider of DESIGN
    Table 1b (protocol of 20 October), with the headroom gate ÷ upper
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
default from $n >= 8$. The seven-leg comparison of M with B is open (the
schedule-M run of `measure-g1-7leg` stopped; G1 and Table 1 time schedule B).

#let stab-revs = g.processes.map(p => p.stability.map(r => r.at("revision", default: none))).flatten().filter(r => r != none).map(r => r.slice(0, 8)).dedup()
#let dd-row(p, i) = p.stability.find(r => r.index == i and r.arithmetic == "double-double" and r.configuration == "native/full")
#let b64-row(p, i) = p.stability.find(r => r.index == i and r.arithmetic == "double" and r.configuration == "native/full")
#let best-dev(r) = if r == none or r.deviation_vs_providers.len() == 0 { none } else { r.deviation_vs_providers.pairs().sorted(key: ((n, v)) => v).first() }
// The user's acceptance of a native check's points above its tolerance
// (summary.json validation.accepted): shown instead of the failure.
#let accepted-of(p) = { let r = all-rows.find(r => r.key == p.key); let a = if r == none { none } else { r.validation.at("accepted", default: none) }; if a != none and a.check.ends-with("['native/full'].accuracy_check") { a } else { none } }
#let camp-cell(c, accepted: none) = { let acc = if c == none { none } else { c.at("accuracy_check", default: none) }; if acc == none { dim[—] } else [#sci(acc.max_error) #if not acc.passed { if accepted != none [#linebreak() #text(fill: pass-ink, weight: "bold", tiny[‡ pts #accepted.points.map(x => str(x.index)).join(", ") accepted])] else [#linebreak() #text(fill: amber, weight: "bold", tiny[above #sci(acc.tolerance)])] }] }
#figure(kind: table,
  caption: [*Values at the timed points*: pyAmpliCol's binary64 finite part
    (native inputs on `loop`) against each provider's production-mode value on the
    common stream points (the providers read the binary64 decimal text of the
    exact points), largest deviation, metric
    $|a - b| slash max(|a|, |b|, |B| alpha_s slash 2 pi)$; Recola's finite part
    converted with the universal double pole (it returns no poles in
    production). Worst point: the point of the row's largest deviation,
    evaluated again with one rotation and the reduction-direction check in
    binary64 and in double-double (DD)#if stab-revs.any(r => not same-engine(r)) [ by the stability runs of
    #rev-list(stab-revs.filter(r => not same-engine(r))), not repeated (their binary64 values equal the timed ones to rounding level, more at
    binary64-unstable points)]: $E$ is the binary64 estimate, DD
    the DD value's deviation from the closest provider (named). Campaign: the
    first three points against the committed references
    (`tests/fixtures/loop/required`; $g g -> g g g g g$: NJet's ten points), fixture metric and tolerance, asserted
    in binary64 where its estimate $E <= 10^(-9)$ and in DD elsewhere (user 2026-10-29; earlier records: binary64
    throughout), native inputs (`loop`) and Python inputs (history); ‡ points above the tolerance that the user accepted (below the table).],
  tstyle(table(
    columns: (2.7cm, 0.65cm, 1fr, 1fr, 1fr, 1.25fr, 1.45fr, 1fr, 1fr),
    align: (x, y) => if x == 0 { left + horizon } else { right + horizon },
    inset: (x: 3.5pt, y: 2.6pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][Pts][vs MadLoop][vs Recola][vs OpenLoops][Worst point: $E$][DD: closest provider][Campaign, native][Campaign, Python#super[hist]],
    ..g.processes.map(p => {
      let c = nat-c(p)
      let v = if c == none { none } else { c.values_vs_providers }
      let cell(n) = if v == none or v.at(n, default: none) == none { if prov(p, n) != none and "unavailable" in prov(p, n) { if n == "openloops" { dim[no library] } else { dim[not generated] } } else [—] } else { sci(v.at(n).max_finite_deviation) }
      let pts = if v == none or v.len() == 0 { 0 } else { calc.max(..v.values().map(x => x.points)) }
      let worst = if v == none or v.len() == 0 { none } else { v.values().sorted(key: x => x.max_finite_deviation).last() }
      let wi = if worst == none { none } else { worst.worst_point }
      let st = if wi == none { none } else { b64-row(p, wi) }
      let dd = if wi == none { none } else { best-dev(dd-row(p, wi)) }
      (gname(p.key), str(pts), cell("madloop"), cell("recola"), cell("openloops"),
        if st == none { dim[—] } else [#tiny[pt #st.index:] #sci(st.estimate)],
        if dd == none { dim[—] } else [#sci(dd.at(1)) #tiny[#pshort(dd.at(0))]],
        camp-cell(c, accepted: accepted-of(p)), camp-cell(py-c(p)))
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
#sci(calc.max(..ml-dd))). At the campaign points the check asserts binary64 where its estimate $E <= 10^(-9)$ and double-double elsewhere
(user E1 ruling 2026-10-29 \~03:45, package g1-accuracy): $g g -> g g g g$ point 1 ($E$ = #sci(b64-row(gg4, 1).estimate))
is asserted in DD, the check passing at #sci(nat-c(gg4).accuracy_check.max_error) (tolerance
#sci(nat-c(gg4).accuracy_check.tolerance, d: 0); binary64 there #sci(nat-c(gg4).accuracy_check.max_error_binary64),
recorded); its DD value agrees with Recola to #sci(dd-of("gg_gggg", 1, "recola")).#for r in accepted-rows { let a = r.validation.accepted; [ ‡ #box(math-label(r.math)) against NJet: points #a.points.map(x => str(x.index)).join(" and ") exceed the tolerance #sci(a.tolerance, d: 0) in binary64 (#a.points.map(x => sci(x.finite.values().first())).join(" and ") from NJet's double-double values, at most #sci(a.max_error) over all its references), *#a.status*: estimates $E$ #a.points.map(x => sci(x.estimate)).join(" and "), and pyAmpliCol's double-double values equal NJet's; the check keeps its tolerance#if a.at("passed", default: false) [ and, asserting DD at these points ($E > 10^(-9)$, E1 ruling), passes] else [ (`passed: false`)].] }

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
increment: #ttq-old.validation). The electroweak target is validated by the M-SM campaign (@msm, @tab:msmrows), row #ms.required.rows.find(r => r.label.starts-with("g g -> t overline(t) e^- e^+ g") and r.at("corr", default: none) == "EW").validation; G1 times and gates it since the final retime (`data/msm-g1.json`, @msm; Table 1), and its
generation and validation are the integrated configuration's, not a development record (so it is not in the table
above). The QCD classes are M-QCD's (@mqcd). The $u overline(u) -> g g g g g$ row comes
from #rn.processes.uux_ggggg.record.split(",").first(), the newest record of that process: the later re-runs on the merged
heads (eighth and ninth increments) do not include it. It uses the same production counterterm route; its check is in @tab:sevencheck.

// ========================================================== SEVEN GLUONS ==
= Seven and eight gluons: NJet and pyAmpliCol <sevenglue>

== NJet: Table 5 of arXiv:1209.0100, re-measured on this host

NJet is the independent reference for $g g -> g g g g g$, where MadLoop and
Recola cannot generate under the 45-minute rule and OpenLoops has no library.
It is massless five-flavour QCD, and it is not one of the gate's matched
providers. At eight gluons ($g g -> 6g$, M-FINAL item 1) NJet's leading-colour primitives (NGluon, on exactly rotated
points) check pyAmpliCol's LC virtual in double-double to #esci(six-rec("gg_gggggg-lc").checks.ngluon.at("ngluon-dd").max_relative.first()) and in binary64 within 10~$E$
(#link(<sixlegs>)[the $2 -> 6$ records]); no provider times eight gluons.

#let nj-cell(v, ref, note: none) = if v == none {
  table.cell(text(7pt, fill: ink2, style: "italic", if note == none [—] else { note }))
} else {
  table.cell({
    text(8.2pt, weight: "bold", num(v))
    h(1fr)
    text(7pt, fill: ink2)[#mult(v / ref)]
  })
}
#block(breakable: false)[#figure(kind: table,
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
) <tab:njet>]

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
// Since the seven-leg G1 rows (measure-g1-7leg) Table 1 validates g g > g g g g g with G1's own accuracy
// check (no record revision): this section then cites the newest development record.
#let g7v = (g7, ..if g7-old != none { (g7-old,) } else { () }).find(x => x.revision == g7-row.validation.at("revision", default: none))
#let g7v = if g7v == none { g7 } else { g7v }
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
2,652 s after the ct-simplify merge (ninth increment, this record), 1,843 s of it the companion's seed table, which built
generic seeds. Since then native-seeds' in-crate colour reductions and generation-scale-2's lean companion (sharing
the slice's certificates) brought the companion's seeds to 4.7 s (DESIGN WP3.1), and G1's stored process on `loop`
(#raw(g.slice_revision), full colour) generates in #minutes(nat-c(gproc("gg_ggggg")).generation.generate.seconds) plus
#minutes(nat-c(gproc("gg_ggggg")).generation.export.seconds) of export at a
#fixed(calc.max(nat-c(gproc("gg_ggggg")).generation.generate.peak_gib, nat-c(gproc("gg_ggggg")).generation.export.peak_gib), 1) GiB peak (one pinned core, cold
caches; @tab:g1). A point with its rotation and reduction-direction checks took
#g7.seconds_per_point_unbatched.map(t => sig(t)).join(", ") s, a single-point development evaluation (#C.development_records.threads.at(g7.revision, default: "threads not recorded")):
not a batched one-thread time and not comparable with NJet's
#sig(meas.njet_single_evaluation.standard.mean_s) s per evaluation on one pinned core. The batched one-thread timing is G1's (@tab:summary, @g1),
and so is the check of the timed configuration against NJet's ten points (@tab:sevencheck).

== Validation without a matched provider

#let nv = ms.njet_validation
#let ux-agree = meas.provider_generation.processes.uux_ggggg.reference.maximum_provider_relative_error
// G1's own checks of the timed configurations (native/full, engine
// slice_revision): g g > g g g g g against NJet's ten points (with the
// user's acceptance of the points above the tolerance, summary.json
// validation.accepted) and u u~ > g g g g g against MadLoop and Recola at
// the timed stream points.
#let g7p = gproc("gg_ggggg")
#let g7c = nat-c(g7p)
#let g7a = g7c.accuracy_check
#let g7val = all-rows.find(r => r.key == "gg_ggggg").validation
#let g7acc = g7val.at("accepted", default: none)
#let g7-born = calc.max(..g7a.rows.map(r => r.errors.values().map(e => e.at("born", default: 0))).flatten())
#let g7-row-max(r) = calc.max(..r.errors.values().map(e => e.values()).flatten())
#let g7-est = g7p.fixture_stability.filter(r => r.arithmetic == "double" and r.configuration == "native/full" and r.fixture == g7a.fixture)
#let g7-within-all = g7a.rows.all(r => { let e = g7-est.find(x => x.index == r.index); e != none and e.estimate >= g7-row-max(r) })
#let g7-dp = calc.max(..g7c.physical.map(x => x.double_pole_deviation))
#let uxp = gproc("uux_ggggg")
#let uxc = nat-c(uxp)
#let uxv = uxc.values_vs_providers
#let uxval = all-rows.find(r => r.key == "uux_ggggg").validation
#let ux-own = uxval.at("worst_point", default: (:)).at("reference_own", default: none)
#let ux-dp = calc.max(..uxc.physical.map(x => x.double_pole_deviation))
#block(breakable: false)[#figure(kind: table,
  caption: [*Checks of the seven-leg QCD results.* First and third rows: G1's checks of the timed configurations (engine
    #raw(g.slice_revision) on `loop`, native per-point inputs, full colour; binary64 finite part and Born, and the double pole
    of G1's physical rows against the universal one); second row #dev-tag on `work/v2-generation-scale`; Ward row WP2.5 on
    `loop`; deviation metric of @tab:summary. NJet values: fixture `gg_ggggg_njet.json` (NJet 3.1.2 double-double at
    exactly rotated points, scaling-test estimates ≤ #sci(1.3e-24)\; points 0–2 are G1's stream points 0–2 at NJet's scale).],
  tstyle(table(
    columns: (4.4cm, 1fr, 2.9cm),
    align: left + horizon, inset: (x: 4pt, y: 2.8pt), stroke: tstroke, fill: thead-fill,
    table.header[Check][Result][Status],
    [$g g -> g g g g g$ full virtual against NJet (top-free, $N_f = 5$), #g7a.points points (G1)],
    [finite ≤ #sci(g7val.max_finite) against NJet's double-double values (median #sci(g7val.median_finite)\; NJet's binary64
      values ≤ #sci(g7a.max_error)), Born ≤ #sci(g7-born)#if g7-within-all [\; every point within its estimate $E$]#if g7a.at("double_double_points", default: ()).len() > 0 [\; asserted in DD at points #g7a.double_double_points.map(str).join(", ") ($E > 10^(-9)$, E1 ruling)]#if g7acc != none [\;
      above the tolerance: #g7acc.points.map(x => [point #x.index #sci(x.finite.values().first()) ($E$ = #sci(x.estimate))]).join(" and "),
      where the double-double values equal NJet's]\; double pole against the universal one ≤ #sci(g7-dp) (points
      #g7c.physical.map(x => str(x.index)).join(", "))],
    [#if g7a.passed [passed (tolerance #sci(g7a.tolerance, d: 0))] else if g7acc != none { text(fill: pass-ink, weight: "semibold", g7acc.status); linebreak(); text(6.6pt, fill: ink2)[points #g7acc.points.map(x => str(x.index)).join(" and ")\; tolerance #sci(g7acc.tolerance, d: 0) unchanged, `passed: false`] } else [failed (tolerance #sci(g7a.tolerance, d: 0))]],
    [Top-free full virtual against NJet at lower multiplicity],
    [#nv.topfree.lower.map(l => [#math-label(l.label): #l.value]).join([; ]) (`test_loop_v2_topfree.py`)],
    [passed],
    [$u overline(u) -> g g g g g$ full virtual against MadLoop and Recola, #calc.max(..uxv.values().map(x => x.points)) points (G1, the timed stream points)],
    [finite: MadLoop ≤ #sci(uxv.madloop.max_finite_deviation), Recola ≤ #sci(uxv.recola.max_finite_deviation)#if ux-own != none [ (Recola's own: pyAmpliCol's double-double value lies #sci(ux-own.dd_deviation) from it and #sci(ux-own.independent.dd_deviation) from #pshort(ux-own.independent.key))]\;
      Born ≤ #sci(calc.max(..uxv.values().map(x => x.max_born_deviation)))\; double pole against the universal one ≤ #sci(ux-dp)\; the providers agree to #sci(ux-agree) (reference merge)],
    [#if uxc.accuracy_check.passed [passed] else [failed] (tolerance #sci(uxc.accuracy_check.tolerance, d: 0))],
    [Ward identity, one gluon's $epsilon -> p$, at seven gluons],
    [MQ-WARD (`d3081568`): the generic gauge-Ward check on the native per-point input path, top-free $g g -> g g g g g$,
      legs 1, 4 and 7: virtual ≤ $2.9 times 10^(-10)$ (binary64) and $2.8 times 10^(-26)$ (DD) of the physical scale, Born
      ≤ $9.8 times 10^(-16)$ / $5.3 times 10^(-32)$ (nightly `test_loop_v2_ward.py`; `data/milestone.json` `status_notes`)],
    {
      let w = s-rows.find(r => r.key == "gg_ggggg").full_colour.sanity_checks.ward.status
      text(fill: if w.starts-with("passed") { pass-ink } else { amber }, weight: "semibold")[#w at seven gluons (addendum H)]
    },
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
  ([Recursive engine], "supported", [Trees, families and loop numerators from recursions; no loop diagram is enumerated (FeynKit graphs are test oracles only). Any number of coloured fermion lines, identical or distinct flavours, QCD and EW (fermion-lines, `db1ed5cb`: the fold of mixed colour-connection parities before the evaluation reuse, Python and Rust lanes; $u overline(u) -> d overline(d) s overline(s)$, $u overline(u) -> u overline(u) d overline(d)$, $u overline(u) -> u overline(u) u overline(u)$ and $u overline(u) -> u overline(u) e^+ e^-$ equal MadLoop in quadruple precision and Recola). Since ew-leptons (EWI-5, `b82d8280`) any number of lepton and colour-singlet fermion lines, through the loop too, with one reading-sign rule and one fermion classifier taken from the tree engine (Bhabha against MadLoop; genericity audit 2 G2-M5, G2-M6); since ew-epsilon (`6da37352`) one root-closure reading sign on every fermionless vertex (G2-M7). Listed, typed refusals replace every silent-wrong-value path of the second genericity audit (fail-closed, `fb54246c`; visible in the dry run). Counterterms: see below.]),
  ([Default engine], "supported", [v2 is the only one-loop engine (MQ-LEGACY-REMOVE, `539dffdd`; user 2026-10-28 \~16:10 Q3): the per-diagram legacy engine, its plan v3 artifacts and its precision-rescue options are removed (the built-in rescue stack of M-FINAL-b replaces them in the Python API, see Stability); `loop.engine`, `--loop-engine` and a non-default `[evaluation.stability]` are refused with the removal reason; tests that used the legacy engine as an oracle keep an independent one (frozen captures or providers).]),
  ([Shipped models, public route], "supported", [The wheel ships MG5 3.7.0's `loop_sm` and its restrictions with a `[loop.model]` profile (MQ-MODEL, `321efdb4`): every QCD class generates through `Generator` / TOML / CLI without a `tools/` helper or hand-written declaration, a multiparticle label one entry per subprocess, bitwise the tools route (@mqcd); MadLoop syntax mapped (`[virt=QCD]` → `loop_coupling_orders`, `QED=n` → `max_coupling_orders`, `/ x` → `particle_veto`), decay chains and `$` refused typed (decays are served since M-FINAL-b); `pyamplicol self-test` evaluates a `loop_sm` virtual against MadLoop. *Since M-SM* the wheel also ships `loop_qcd_qed_sm` and `loop_qcd_qed_sm_Gmu`, UFOmodeldb `6ca4b120` plus the user's issue-1 patch ($R_2$ of `R2_G0tt` split by loop origin, exactly unitary CKM, the $G_mu$ bottom-mass charge counterterm; PROVENANCE and `MANIFEST.sha256` record the local delta; MS-MODEL `2ae8b88b`, MS-UFODB `0e5930c2`, MS-UFO-PATCH `3eb4db9f`), with digest-keyed profiles and the structural Goldstone-flag repair: every EW class generates through the public route, bitwise the tools view (@msm); a multiparticle request generates its members with a Born and records the loop-induced members as skipped (`loop-induced`, Q2); the self-test also evaluates an EW virtual from the shipped prepared artifact (= MadLoop to #sx-ew-st).]),
  ([Full, NLC and LC colour], "supported", [*Full colour is the default* of loop requests (user 2026-10-28 Q1); LC and NLC are opt-in through the shipped `loop_sm` $N_c$ declaration (MQ-NC, `d8d9349f`: every counterterm vertex, resolved by structural digest; formal-$N_c$ projections equal to $N_c$ scans and checked against independent oracles, rule 7; an uncovered vertex refused, `colour-declaration-coverage`). *LC helicity and colour-flow selection* (MQ-SELECT, `e4964fc3`): `helicities=` / `color_flows=` at generation (recursion pruned to the selection) and at evaluation, tree-engine IDs; a complete set of selections sums to the inclusive LC value; NLC and full colour keep their API (selectors refused there). Exact seed tables in $N_c$, built in Rust since native-seeds (`7e3841f3`), with native colour cells, seed records and dipole orbits since native-cells (`5ebcebea`; the Python stages are the oracles); LC/NLC by generated classes and truncated cells. #if lc-slower.len() == 0 [LC is faster than full colour end to end on every G1 row at $B = 128$, the $2 -> 5$ rows included (LC/FC #fixed(lc-now.first().r, 2)–#fixed(lc-now.last().r, 2), @tab:g1lc); the top-free seven-gluon LC plan keeps every full-colour family by construction (@lc).] else [LC is cheaper in the loop stage but not yet end to end at large batches (@tab:g1lc), nor to generate at seven legs.] Since identical-flavour-lc (`5cb5ea83`) LC and NLC of identical-flavour quark lines (from $u overline(u) -> u overline(u) g$ up, any number of lines) are exact formal-$N_c$ projections: blocks and counterterm program split by U(1)-subtraction $N_c$ grade in both lanes, order-free grades (G2-M1; the limitation of m1026a is removed, @lc); a block that still mixes grades is refused (`colour-accuracy-nc-exact`, fail-closed). *EW LC/NLC is not supported, by design* (user 2026-10-30 Q4: the typed `colour-declaration-coverage` refusal is permanent); electroweak requests run at full colour. *Since M-FINAL-b:* `strict-lc` / `strict-nlc` and $N_c$-graded colour output (PR \#32), the exact U(1)-subtraction weight $1 slash N_c$ (PR \#34; binary64 quark-line values move by rounding only, model compiler 17: older loop artifacts are refused at load and regenerated); stored LC selections are masks on one template per process with per-call row liveness (mf-masks, mf-masks-rows: no executor or native heap per selection, bitwise the per-selection oracle).]),
  ([FFT colour contraction], "supported", [Certified symmetric-group FFT of the seed contraction in the native executor at full colour and NLC, binary64, double-double and MPFR (MQ-FFT, `da6980b0`): generic over the plan's certified pairs, policy `auto | direct | fft` (the algorithm run is reported; a forced FFT without a certified pair is refused, `forced-seed-fft-unserved`), public `color.contraction` route; FFT = direct to rounding up to $g g -> g g g g g$; the seed stage ×0.46–0.70 of direct at $S_5$, $S_6$, slower below, the whole evaluation unchanged within noise (@tab:fft).]),
  ([Colour and spin correlations], "supported", [Directed colour histories at LC/NLC/FC, spin sources, resolved helicities, flavour aliases, Ward sources (WP2.5). Since generation-scale-2 the directed metrics are native and stored with the process (correlated and resolved calls of a stored process regenerate nothing; one seed column per self-adjoint dipole): declaring the NLO dipoles costs +10 % of the six-gluon generation (38.5 against 35.0 s); at seven gluons 784 against 419 s, whose metric tables go to `native-cells`' next run. LC/NLC correlations of identical-flavour quark lines use the graded blocks of the colour row. *Independent oracles since M-FINAL-b* (MF-CORR, `821ae808`): Recola's colour, spin and spin-colour correlations on four processes equal the one-loop `evaluate_correlated_many` and the tree `Runtime.evaluate_correlated_many` (Born ≤ #sci(cr-born), Laurent coefficients ≤ #sci(cr-laurent) of the row scale, @tab:corr); a spin-correlated leg without a four-component vector source is refused at generation, as on the tree route (MF-SMALL2); correlations with an LC selection are refused (`selected-correlators`).]),
  ([Per-order partials], "supported", [Every squared coupling order at tree level and at one loop, mixed Born orders, per-correction loop orders.]),
  ([Poles at runtime], "supported", [`poles = "all" | "none" | "uv" | "ir" | "split"` (WP2.10, on `loop` since 24 October): finite-only mode with the finite part bitwise unchanged and the pole work skipped (natively per counterterm interaction since generation-scale-2's I5 record); `"uv"` and `"ir"` with the user's semantics of 23 October, from a lean stored companion of the certified-scaleless families (bitwise at $g g -> g g g$ and $u overline(u) -> g g g g$, equal to rounding at six and seven gluons) and in the SDK v4 too; the IR poles sum one Catani operator per correction, QED included (ew-poles, `8b52179b`; a correction without a prediction gives none); since `e6e7543a` a mixed QCD×EW sector is predicted only where the requested corrections complete its loops, and joint requests predict it exactly; since MQ-EWJOIN a sector whose QCD loop selection omits IR-divergent loops (gluon exchange between quark lines joined by a $W$/$Z$ in the loop, `separated-exchange`) is not predicted and checked against MadLoop per split order. Photon-only QED corrections on `loop_qcd_qed_sm` are refused (`veto-unlabelled-counterterms`: the veto reaches counterterms with empty or nominal loop labels; full EW on that model matches Catani; EWI-7). The UV residue comes from an interim local module until the NinjaRS re-pin; a `"uv"` estimate needs a rotation check. *EW pole split* (MS-POLES, `42b2794f`): on EW requests `"uv"` and `"split"` come from the model's pole regulators (`epsUV`, `epsIR`) under both mass schemes, at the cost of one more regulated pass of the tree program; the conventions record the regulators (= MadLoop on DY01 and TT01).]),
  ([Stability estimates], "supported", [*Recommended checks* (MQ-STAB, `a2aa0d84`): `loops.v2.stability.RECOMMENDED_CHECKS`, one generic exact rotation and the rescaled reduction check, the O1 estimate of the campaign and G1 (calibration: binary64 misses 0 % / 0.05–0.10 % of points, DD none; true error ≤ 10 $E$ at every campaign point; R3, DECISIONS 2026-10-29 \~18:25). Rotation checks (any number, 0 = estimate absent), reduction direction, exact rescaling, in any combination; no automatic escalation by default. *Rescue stack* (MF-RESCUE, `2234ee33`; user Q9: only in pyAmpliCol's Python native evaluate API, never in an SDK, the CLI or the config): `stability=VirtualRescuePolicy(...)` per call or as the `Runtime.load(..., stability=)` default, `DEFAULT_RESCUE` double → double-double → arbitrary precision (57 digits) to a target of $10^(-5)$, each level with an Euler rotation (`euler:0.1,0.2,0.3`) and the rescaled check; per-lane `VirtualEvaluation.rescue` records and `rescue_counts`, typed refusals; the legacy `VirtualStabilityPolicy` is removed. A non-finite counterterm coupling fails only its own points (MF-SMALL, `isolate_scale_failures`). Generation's post-build validation re-checks a binary64 miss alone against a 32-digit reference: double-double must agree at the same tolerance, binary64 Borns at the tolerance and binary64 virtuals within the larger of the tolerance and their own estimate (one exact rotation and the reduction direction; an estimate above $10^(-9)$ or absent refuses), else generation refuses; an accepted point is logged (onshell-consistency, `4fc72e39`). The rotation and reduction-direction checks flag the fast binary64 lanes' known misses (precision row): use them for such kinematics or model units.]),
  ([Precision carriers], "partial", [Binary64, DoubleFloat, arbitrary precision and exact rationals in the native executor; since G-int the native per-point inputs run in binary64, DoubleFloat and arbitrary precision (DESIGN §5.5). Since `7db32901` binary64 runs SymJIT plane applications and needs no Symbolica licence; DoubleFloat and arbitrary precision run under pyAmpliCol's library key. Since precision-ap (`a8409830`) a master-integral invariant of one external leg is that leg's squared mass at the point's parameters: DoubleFloat and arbitrary-precision virtuals were O(1) wrong at binary64-rounded massive momenta and now agree with a MadLoop quadruple-precision run within $10^(-15)$ (and DoubleFloat massive spinors along $-z$ are fixed); since generation-scale-2 derived masses (e.g. $M_W$ of `loop_sm`) are parameter-program outputs, bound exactly (genericity M2). Since `onshell-threshold` (`6e123fdb`, G2-M3) binary64 lanes at the fast engine's absolute thresholds (light masses, invariants near a mass shell) go to the generic binary64 engine. *The fast binary64 lanes' light-like spinors* near the $-z$ axis (off by up to \~$10^(-5)$ before, with silent percent-level errors at model units \~$10^4$ from GeV) are taken from the larger light-cone component since NinjaRS \#10 (in NinjaRS main since mf-symbolica: the five xfails are plain cases, large unit factors keep the virtual). *Tree runtime* (lsimon125's PRs \#26, \#29, \#36, \#39, LP-PRECISION): double-double and arbitrary-precision contracted-colour replay, exact correlated weights, couplings, parameters and masses at working precision, the $G_mu$ UFO boost fix. *Binary64 evaluation of a stored artifact never calls Symbolica* (user 2026-10-30), complex-mass artifacts included: a cut-function argument that becomes real when complex-mass widths are exactly zero takes its real part at run time (MS-MASTERS, `71e2041e`; binary64 = DD = AP(32) on the CM01 zero-width fuzz, = MadLoop where its double and quadruple precision agree).]),
  ([Native executor, schedules], "supported", [Rust, 16 lanes (also for a one-point call, a G1 lever), threads; native tree closures in lanes of points with runtime AVX-512/AVX2 widths (lc-perf); in finite-only mode the counterterm interactions that only feed poles are skipped natively (generation-scale-2); G1 decision on the schedule-dependent stages (@tab:g1bm, provisional until compiled trees): M for pure-gluon LC from $n = 6$, B for every other class at $n <= 6$; F as oracle. The NinjaRS reduction runs serially. Development report: stage times, modelled kernel work, master-integral time. *Memory and speed rounds of M-FINAL* (#link(<rounds7>)[seven-leg table], values bitwise): tree/CT fill and batches within fixed state, row and chunk-input budgets (mf-8g-2), stored members read on demand at load with a compact Rust plan and tree program (mf-8g-2b), binary stored forms and native CT DAG maps (mf-8g-1), lighter generation (mf-8g-1b, mf-8g-1c), row-sized interference blocks (mf-perf-opt).]),
  ([Plan v4 artifacts and API], "partial", [Published and loaded through Python, TOML and CLI; the artifact stores the native process (`point_inputs = "native-v2"`). Since `7db32901` (addendum G) its SymJIT -O2 applications are stored as IR and recompiled at load for the loading CPU (AVX and FMA3 required), no host string is embedded, and binary64 values are bitwise equal after relocation to another machine, user and path; since M-FINAL-b SymJIT 2.28.3 (MF-UP: siravan/symjit \#26, \#30, \#31) makes the stored runtime members byte-reproducible between generations, and the parameter program's evaluator bytes no longer depend on how the model was obtained (MF-SMALL2: the runtime-bound scalar predicates in their own id block). *Permutation aliases and process-group members* (MF-MAP, `9ad0c77f`): a one-loop alias or a permuted member of a plan v4 process is served from the stored target at permuted momenta, colour and spin correlations composed, LC anchors relabelled; numerical process-group analysis stays refused (`process-group-analysis`) and helicity/colour-flow selection is refused for mapped processes. *Virtual C ABI version 2* (MF-CLEAN, `25d39f6b`): the legacy agreement check and the SDK policy argument are removed from the Rust SDK, the C ABI, the C/C++/Fortran wrappers and UMAMI. Since model-determinism (`4e9262b5`) the compiled model and the artifact's digest no longer depend on the process history; since native-lowering (`79f2a5bd`) the plan JSON is written by the Rust plan model (Python writer as oracle). Since generation-scale-2 (`11542fd5`) no call of a stored process regenerates (every pole selection with the stored companion, correlated, resolved, flavour and catalogue calls), a process the native export cannot store fails its generation with a typed refusal (genericity M1; the plan-only, regenerated-at-load artifacts are gone), and the Rust/C/C++/Fortran SDK v4 evaluates these artifacts with the `"uv"`/`"ir"` selections, bitwise the Python API. Since sdk-parity (`f6619f34`) one parameter rule holds in the Python API, `V2Runtime`, the Rust SDK and the C/C++/Fortran clients: ASCII decimal values checked before names, unknown, generation-fixed (naming who fixed them) and scale parameters refused with typed errors (G2-M2). The release natives need glibc $>=$ 2.38, a lower glibc giving the typed `NativePlatformError` at load (glibc-floor, `5301e24a`). Since M-SM external-photon and complex-mass artifacts are `native-v2` too (ew-native, MS-CMS-N: complex pole masses through the native trees and executor, bitwise after relocation). *Since M-FINAL-b:* the SDK v4 extras (mf-sdk: resolved, colour/spin-correlated, double-double and arbitrary precision through the Rust SDK, the C ABI, the C++/Fortran wrappers, UMAMI and the packaged Rust wrapper); every stored saved evaluator is canonical (mf-symbolica: referenced symbols only, numbered by name), so artifact bytes no longer depend on the producing Symbolica (Community or PyPI 3.0.3) or the process history. Open: the plane check's outcome depends on the parameter order (G2-M4: a listed `plane-mismatch` refusal, never a wrong value).]),
  ([Counterterms (model UV, $R_2$)], "supported", [Plain tree vertices of the recursion inserted exactly once (WP2.2, a18b7599; addendum J, b4d76cc3), admitted by coupling orders and the public `particle_veto`; no witness table or loop matching in production. *Stock `loop_sm` compatibility rule* (MQ-MODEL): its four-$G^0$ vertex `V_1001` names the three-slot constant `SSS1` where the four-slot `SSSS1` (same exact value) is meant; model preparation moves such references by structure, only on vertices a request reaches, and records each repair (`pyamplicol_source_repairs`, `source_compatibility_diagnostics` in the dry run); any other slot mismatch is refused (`lorentz-slot-arity`). Vertices whose couplings vanish at the restriction leave the loop catalogue (fail-closed-2, `loop-vertex-outside-tree-model` otherwise). An unlowerable counterterm vertex that no tree of the request reaches is inert and recorded in the artifact; a reachable one is refused. Site closure is the test oracle. Per point they are formed natively (G-int), the Python stages kept as oracle; generation of the counterterm route has output-identical savings (ct-perf, `201bece5`: compile memos, a content-addressed lowered-model cache), and since A4 (`1b13005a`) the native DAG builder is the production route for the loop blocks and the counterterm program (its counterterm emission byte-identical to the Python oracle; 11 listed features keep a recorded per-request Python fallback, any other native failure fails closed), at parity with the site oracle. In EW requests ('t Hooft–Feynman gauge, EWI-4b, `8b19dae8`) the Goldstone–vector mixing counterterms are lowered as vertex insertions. The UFO's EW counterterms (ew-ct, `392d3f4a`) are lowered through the model's own helper bodies with MadLoop's branch side for exactly real arguments: every Laurent piece of MadLoop's model library equals pyAmpliCol's to $3.7 times 10^(-15)$ in binary64 and $6.0 times 10^(-31)$ in double-double (against MadLoop's quadruple precision). Since EWI-3R (`59d47cb3`) the lowering runs at scale: native, parallel kernel-equivalence proofs (Python the oracle), one reference pair per Laurent coefficient, shared Horner schemes; about 26 s cold at the target instead of 259 s, 8.4 % of the $G_mu$ $g g -> t overline(t)$ (EW) generation (criterion < 20 %, user 2026-10-28); a non-polynomial coupling term or one below $epsilon^(-2)$ is refused when reachable. Lorentz `Epsilon` is lowered (EWI-7b, `6da37352`; sign = MadLoop to $10^(-12)$), and the Goldstone–vector mixing sign, from the tree engine's momenta, matches MadLoop's counterterm selection. *UFO-complete $R_2$ insertion* on the EW UFOs (user Q7): every $R_2$ vertex a tree of the request reaches is inserted. Compatibility note: MadLoop never inserts R2_G0tt_b on the unpatched models (its label `[W+, b]` equals no loop's propagator set; mg5amcnlo\#475, up to 8.4 % on $t overline(t) -> z h$); on the shipped patched models MadLoop's exports call every $R_2$ coupling pyAmpliCol inserts (MS-VALIDATE).]),
  ([Decays $1 -> n$], "supported", [*Since M-FINAL-b* (MF-DEC-1 `eddb4b49`, MF-DEC-2 `28b24a2a`): one initial leg is admitted generically ($1 -> n$, $n >= 2$) at tree level and one loop, QCD and EW, through the same recursion; the decaying particle at its real mass with zero own width (the existing width guards; internal CMS widths allowed), MadLoop's convention (amputated loops, its absorptive self-energy dropped, $delta Z$ from the UFO counterterms); the rest-frame massive Dirac spinor fixed (was $2 times |M|^2$ at $|p| = 0$). XX01–XX08 = MadLoop's quadruple precision (@tab:dec: #dmc.pass of #dm.rows.len() pass, DD ≤ #sci(dml.dd_vs_reference.value)), $Z -> u overline(u)$ = the massless form factor, Ward on $t -> b W^+ g$, LC/NLC by the $N_c$ scan, public route and native inputs. Refused typed: loop-induced decays (`loop-induced`), chains and `$` (`madloop-syntax`).]),
  ([UFO genericity: HC_NLO_X0], "partial", [*Since M-FINAL-b* (MF-GM-HC, `e2f0c78e`): the Higgs characterisation UFO at NLO, HC01–HC04 and HC06 = MadLoop 3.7.0 through generic fixes (UFO namespace head, Feynman-gauge refusal only where massive vectors run in the loops, positional counterterm keys, a colour-singlet contact split through an adjoint auxiliary); *since M-FINAL* HC05 ($g g -> x_0 g g$) too (MF-HC05, `e3d4ef4d`): a counterterm colour the tree vocabulary refuses (its five-point $f f f f$ $R_2$ contact) is projected exactly at $N_c = 3$ onto products of at most two primitive adjoint tensors (zero residual required, else refused); all six ≤ #sci(hc-max) (@tab:hc). *PR \#38* (LP-MODELS): compiled-mode HEFT quark tree amplitudes (built-in SM-HEFT and HC_NLO_X0) were 4× too large, now = MG5 and the MadLoop Borns. Open, typed: $u overline(u) -> x_0 g g g$ (the U(1)-leak check), single-trace and C-odd five-point $R_2$ colours.]),
  ([Electroweak, complex mass], "supported", [*M-SM* (@msm, @tab:cms): QCD, QED and joint `[virt=QCD QED]` corrections on the shipped `loop_qcd_qed_sm` and `loop_qcd_qed_sm_Gmu` reproduce MadLoop in every class of `m-sm/PLAN.md` §1.1 (#sxc.pass of #sx-rows rows pass, #sx-partial.join(" and ") partial: F7, accepted). EW native inputs (ew-native, EWI-N), the EW ladder (ew-validate, EWI-7: ghosts of vetoed vector bosons, Goldstone-side root mixing), *per-leg photon tagging* (MS-PHOTON: `loop.external_photons` = `"final"` by default, `"all"`, `"none"` or a leg list, as MG5's `!a!`; $alpha(0)$ and the conversion counterterm on the tagged legs only), the *complex-mass scheme* (MS-CMS: MG5's transform per (mass, width) pair, coloured widths included; MS-CMS-N: native complex pole masses; = MadLoop CMS on CM01–CM05 and CM07–CM10), the EW pole split (MS-POLES), the EW generation stages in Rust (MS-GEN: catalogue segment polynomials and the parameter program's renaming behind PyO3, the Python stages the oracles, outputs byte-identical, EW generation 2.6–3.2× faster) and Symbolica-free binary64 (MS-MASTERS); since M-FINAL-b the EW export's kernel-string reading and parameter-program renaming run in Rust too (MF-RUST, `b36af289`: Python stages the oracles, byte-identical; EW $2 -> 3$ export 62.3 → 32.4 s). Before M-SM on `loop`: the QED Catani operator, EW fermion lines, 't Hooft–Feynman gauge for trees, loops and counterterms, on-shell photons at $alpha(0)$, the UFO's EW counterterms lowered at scale, Lorentz `Epsilon`, lepton lines through the loop (EWI-0 to EWI-7b). Refused, typed: the Missing box of @status; EW LC/NLC never.]),
  ([Required set], "supported", [All eight generate and agree with their references in all coefficients with native inputs: seven in @tab:validation (validated on the WP3.1 branch before its integration), the EW target in the M-SM campaign (TV07 against MadLoop, Recola and OpenLoops, @msm); $g g -> g g g g g$ against NJet's double-double values (its binary64 points 4 and 8, above the check's $2 times 10^(-8)$, accepted by the user: within the estimate, DD = NJet); the generator is on `loop` since G-int, and G1 times all seven in batches at full and leading colour (@g1; the $2 -> 5$ rows since `measure-g1-7leg`; all re-timed at #raw(g.slice_revision)). The seven-gluon Ward check (addendum H): #ms.status_notes.notes.gg_ggggg.ward_status. The G1 accuracy check asserts binary64 where $E <= 10^(-9)$ and DD elsewhere (user E1 ruling, g1-accuracy); R3 for QCD is recorded (DECISIONS 2026-10-29 \~18:25: two providers per process within their agreement, $g g -> g g g g g$ against NJet alone, addendum F). G1 times and gates the EW target since the final retime (@msm). The provider reference trees no longer read the old working root (reference-relocate, `48aeb123`; provider values bitwise, and the toolkit refuses provider files outside the configured reference root).]),
  ([Performance gates], "partial", [G1 on `loop` (@g1, native per-point inputs, #raw(g.slice_revision)) at $B = 128$: #nat-pass.len() of #nat-gated.len() gated processes pass#if nat-decided.len() > 0 [ (#names(nat-decided) by user decision, #nat-decided.map(p => decision(p, big, bat(nat-c(p), big).gate).label.replace("user decision ", "")).join([, ]))]#if nat-open.len() > 0 [, #names(nat-open) open]#if nat-fail.len() > 0 [, #names(nat-fail) #if nat-fail.len() == 1 [fails] else [fail]]#if nat-ungated.len() > 0 [; #nat-ungated.len() below 5 ms per point are not gated (user, 2026-10-24)]#if s-no-gate.len() > 0 [; #row-names(s-no-gate.map(r => r.key)) without a matched provider: no gate]\; the gate is taken at $B = 128$ only (user 2026-10-28): $B = 1$ and the $2 -> 5$ rows' $B = 16$ are reported without a verdict (@tab:g1batch). The Python per-point inputs before G-int failed every gate they generated (history).#for r in ew-status [ The EW row #box(math-label(r.math)) (EW) is gated since the final retime: #ratio-mult(r.full_colour.main) of #r.full_colour.fastest.name's time at $B = 128$#if s-gate(r) != none [, #s-gate(r).status].] Re-timed at M-LIT-a0 (the final retime deferred from M-FINAL, on #raw(g.slice_revision)). Missing: the provider protocol-mode columns.]),
  ([$2 -> 6$], "supported", [M-FINAL item 1 (user ruling 2026-10-31): $g g -> 6g$ ($N_f = 5$, no top), $u overline(u) -> 6g$ and $u overline(u) -> u overline(u) g g g g$, each at LC and full colour, generate, store (every step below 150 GB), load and evaluate on one engine after the optimisation rounds (#raw(sxj.engine.revision.slice(0, 8)), an ancestor of the pin; @tab:summary, #link(<sixlegs>)[records and checks]\; the N = 8 reduction adapter is tested, MF-8G-0 `7cdd32e9`); double pole, Catani (FC), NGluon (LC), double-double and the quark rows' Ward pass, the 8-gluon Ward is recorded but not asserted (beyond the binary64 scope) and its full-colour and double-double Wards were not run (user, 2026-11-04). Internal checks only: no provider exists.]),
  ([Built-in SM (tree)], "supported", [*Since M-FINAL* (MF-NORM `049a9389`, MF-LIMITS-PY `d958f2ea`): equal to the UFO `sm` in the compiled, eager, on-the-fly and recurrence lanes (the defects corrected and their history: @status, built-in SM fixes), $1 -> n$ decays; checked by the default-tier sweep `tests/integration/test_builtin_sm_ufo_sweep.py` (every $2 -> 2$ class, the $1 -> 2$ decays, $2 -> 3$ / $1 -> 3$ samples) against the UFO `sm` to $10^(-10)$. Typed refusals as for the UFO `sm`: four-quark processes without gluon exchange in the recurrence lane, `dirac-weyl-closure`. A one-loop request needs an NLO UFO (the built-in SM is tree only).]),
  ([Dependencies], "supported", [No fork (user 2026-11-02, MF-SYMBOLICA `e0a8375c`; `dependencies/manifest.json`): Symbolica = symbolica-dev `community` `36cbac3a` + the consolidated PR symbolica-dev/symbolica\#163 (`20a9da94`), NinjaRS main `b3a29c85`, oneloopmaster main `128ea664`; Python through the Community build of `20a9da94` or PyPI symbolica 3.0.3.]),
  ([Hard-coded limits], "partial", [Mechanical limits lifted (MF-LIMITS-PY `d958f2ea`, MF-LIMITS-RUST `72fe20dc`; @status, limits box): one rank admission from the reducer, one leg boundary 1–64, checked narrowing, exact rational charges, uncapped mappings and fixpoints, tuning bounds as settings. *Not supported* (capability generalisations, typed refusals, no milestone planned): rank $> N + 2$, multi-fermion loop vertices, coloured $n$-point EFT contacts, nested singlet contacts, octet/sextet fermions, an LC/NLC menu, binary64-only paths, C-API precision.]),
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
    stage-box([Tree blocks in loop mode], [tree-engine currents, Born; native DAG (A4)], "plain"), arr,
    stage-box([Families by loop-prefix recursion], [pyAmpliCol; native in Rust], "plain"), arr,
    stage-box([Skeleton tries B, merged graph M], [pyAmpliCol, rusticol-core], "plain"), arr,
    stage-box([Exact seed tables $K[c,b]$], [Laurent in $N_c$; native seeds, cells (B, C)], "plain"), arr,
    stage-box([Counterterm program; plan v4], [CT recursion, native DAG (A4); Rust plan writer (D)], "plain"),
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
(`ct-simplify`, b4d76cc3): no witness table and no loop matching. Since A4
(`1b13005a`) the native DAG builder emits this program (byte-identical to the
Python builder, which stays as oracle) and builds the loop blocks. The UFO's
electroweak counterterms (`392d3f4a`) enter the same way, lowered through the
model's own helper bodies with MadLoop's branch side for exactly real
arguments, and in 't Hooft–Feynman gauge the Goldstone–vector mixing
counterterms as vertex insertions (`8b19dae8`). A counterterm vertex that the model cannot lower and that no tree of the request
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
and the finite-only mode. The public API (TOML, CLI or Python; v2 is the only one-loop engine since
MQ-LEGACY-REMOVE) stores plan v4 as a relocatable PACBIN member (zlib
JSON of exact kernel term lists, written by the Rust plan model since
`79f2a5bd`, no compiled code, digest checked at load) and
the native process (`point_inputs = "native-v2"`: the tree program with the
Born, counterterm and field components, their saved exact evaluators and the
binary64 SymJIT applications of every tree kernel and of the parameter
program, stored as IR and recompiled at load) with the companion of the
certified-scaleless families and the observables' tables, so no call of a
stored process regenerates it (generation-scale-2), on another machine, user
and path too; a process the native export cannot store is refused at
generation. The Rust/C/C++/Fortran SDK v4 loads the same artifact.

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
    commits and integration merges of #ms.engine_revision since #ms.previous_loop
    (#ms.integrated.map(r => [#r.wp.split(" ").last() #raw(r.sha)]).join([, ])\; commit subjects "Integrate work/v2-…")\;
    `workspace/reports/engine-v2/slice-status.md` (integration blocks,
    DECISIONS 2026-10-23 to 29, the milestone pushes m1025a of 2026-10-25 \~13:45 UTC, m1025c of 2026-10-26 \~06:35 UTC
    (after the m1025b attempt at `db13c260`, not pushed) and m1026a of 2026-10-27 \~21:00 UTC (`8335e9e8`), and
    milestone m1028a (launched 2026-10-28 \~09:00 UTC; pin `28a16255`, native `loop-native-v2-slice-5cb5ea83`; the
    user's rules of 2026-10-28: the speed gate at $B = 128$ only (\~08:20 item 2, `gate_decisions.gate_batch`), the
    counterterm-lowering share below 20 % (\~08:20 item 1) and the glibc floor (\~07:40; 2.38 since glibc-floor); the
    known limitations from the coordinator's milestone brief and
    `known_limitations` in `data/g1.json`; the identical-flavour LC limitation of m1026a, DECISIONS 2026-10-26 \~21:10
    item 1, is removed by identical-flavour-lc), milestone M-QCD (DECISIONS 2026-10-29 \~17:20: pin
    `e18a024b`, native `loop-native-v2-slice-d0fef168`; the user's milestone plan of 2026-10-28 \~12:50 and its
    rulings \~15:25, \~15:35/40 and \~16:10, the user's rulings of 2026-10-29 \~03:45 (E1) and \~10:20 (precision),
    the coordinator's \~11:25 (F7, F11) and R3 for QCD \~18:25; `workspace/reports/engine-v2/m-qcd/PLAN.md` §1, §5) and
    milestone M-SM (DECISIONS 2026-10-31 \~07:45: pin `71e2041e`, native `loop-native-v2-slice-71e2041e`\; the
    plan `workspace/reports/engine-v2/m-sm/PLAN.md` §1, §5 and its §6a user answers of 2026-10-30 \~08:10 (Q1 per-leg
    photons, Q2 multiparticle members, Q3 decays in M-FINAL, Q4 EW LC/NLC never, Q5 both EW UFOs, Q7 the UFO-complete
    $R_2$); the user's rules of 2026-10-30 \~08:40 (UFOmodeldb as ground truth), \~08:50 (M-FINAL order), \~12:45 (the
    issue-1 patch, with the coordinator's \~13:40) and \~17:35 (binary64 without Symbolica); the accepted F7 and the SC03
    τ-mass relaxation; mg5amcnlo\#475 and UFOmodeldb issue 1); the user's gate decision of 2026-10-24, 16:05 UTC, is
    recorded in `data/milestone.json` `gate_decisions` and no longer applies after the
    re-measure; the user's rules of 2026-10-24, 22:35 UTC — uncoloured generation,
    green-to-red run times, summary pages with only Table 1, Figure 1 and legends,
    and the gate rule "#thr-rule.label", recorded as `gate_decisions.threshold_rule`
    and applied by `scripts/build_summary.py` and this report); milestone M-FINAL-b (DECISIONS 2026-11-01 \~23:35 and
    2026-11-02 \~00:20, \~01:05, \~03:08: pin `f3d9e361` = `617b59cd` + the test-only mf-map-fix, native
    `loop-native-v2-slice-b36af289`\; the plan `workspace/reports/engine-v2/m-final/PLAN.md` §2, §3 and the user's rulings of
    2026-10-31 \~11:00 (M-FINAL order, rescue only in the Python API, decays at the real mass with zero own width, EW
    LC/NLC never), \~14:20 (direct $R_2$ dropped), Q11 (one final retime) and 2026-11-01 \~23:15 (8-leg runs stopped
    for optimisation rounds); the G1 regression spot check at `617b59cd` against `71e2041e`:
    `workspace/tmp/g1-m1101-mfb/logs/compare.txt`); milestone M-FINAL, closed (pin #raw(ms.previous_engine), native
    `loop-native-v2-slice-e0a8375c`\; USER 2026-11-04 \~08:00 'close M-FINAL now' and the lean close of 2026-11-05 \~07:30,
    DECISIONS \~07:35: no local gate sweep, no retime, no closing audit, global tests by CI on `loop`; DECISIONS 2026-11-04
    \~17:40 (no Ward/Catani/campaign re-runs; status changes from package evidence only), \~22:00 (no pedantic tests),
    \~19:15 (mechanical limits only), \~08:35 (8-leg stop lifted) and 2026-11-03 \~13:05 (model compiler 17); the
    integration blocks of the packages in `data/milestone.json` `integrated`; the 2 → 6 report
    `workspace/reports/engine-v2/m-final/2to6-report.md`, the seven-leg round table `m-final/round-table-7leg.md`, mf-8g-3's
    report `m-final/8g3-report.md` §9 (A24) and the Symbolica re-pin report `m-final/symbolica-repin-report.md`; the
    built-in SM fixes: mf-norm's package report (its table for the collaborator) with the integration block of
    slice-status UPDATE 2026-11-05 \~08:05 and DECISIONS \~06:10); milestone M-LIT-a0 (pin #raw(ms.engine_revision), native
    #raw(ms.native_build.name)\; the user's green light for M-LIT of 2026-11-06 \~07:05 and DECISIONS \~07:20, \~07:32;
    `workspace/reports/engine-v2/m-lit/PLAN.md` §3.2 LIT-RETIME, §3.7 "Pushes", §5.1, and `m-final/PLAN.md` §2.4 MF-RETIME;
    the user's request of 2026-11-06 \~06:00 for the loop-induced summary table; the retime's records
    `workspace/reports/engine-v2/measure-g1/records/mlita0`); `HANDOFF_24_10_2026.md` §6; MASTER_PLAN
    2026-10-23/24 entries; REQUIREMENTS_ADDENDUM A, D, F, G, H, I, J; DESIGN §5.5,
    §3.3, §5.7 (G1), §6.1, §6.2, §7.2, §7.5, §7.9, §12.1, §12.4, WP3.1, WP3.2; the 24 October pushes (59badc7a and b4d76cc3,
    gates in slice-status.md), the G-int push (79df367a, 25 October), the m1025a push (bae3b9ea, 25 October), the
    m1025c push (36f43250, 26 October) and the m1026a push (8335e9e8, 27 October).
    WP3.2 increments and dependencies: `workspace/reports/engine-v2/wp32/PLAN.md`; the EW counterterm comparison with
    MadLoop and measurement M1: `wp32/M1-ew-ct.md` and DESIGN §6.1; the genericity audits:
    `workspace/reports/engine-v2/genericity-audit/REPORT.md` and `genericity-audit-2/REPORT.md` (at `11542fd5`, with the
    first audit's follow-up); precision-ap's MadLoop comparison:
    `workspace/reports/engine-v2/precision-ap/`; reference-relocate's inventory and evidence:
    `workspace/reports/engine-v2/reference-relocate/`; model-determinism: DESIGN WP2.5; native-lowering: DESIGN §12.1
    and WP3.1 (Rust migration D); onshell-consistency: DESIGN §11.1 and `docs/user/configuration.md`; native-seeds and
    native-cells: DESIGN §7.2, §7.9 and `workspace/reports/engine-v2/wp31/RUST-MIGRATION.md`; fermion-lines: DESIGN §3.3
    and the fixtures `tests/fixtures/loop/required/uux_{ddxssx,uuxddx,uuxuux,uuxepem}.json`; generation-scale-2: DESIGN
    WP3.1 (its status) and §12.1; EWI-4b and EWI-6b: DESIGN §12.4 and `wp32/PLAN.md`; the packages of m1028a: their
    integration blocks in slice-status.md (ew-ct EWI-3R `59d47cb3`, ew-epsilon EWI-7b `6da37352`, fail-closed
    `fb54246c`, sdk-parity `f6619f34`, ew-leptons EWI-5 `b82d8280` with its R2_G0tt_b evidence (DECISIONS
    2026-10-28 \~05:20 item 2 and \~08:10 item 1), identical-flavour-lc `5cb5ea83`, gate-b128 `28a16255`), DESIGN §5.7 ("Gate batch"), §12.4 and the listed
    generation refusals, `docs/user/configuration.md` and `docs/user/ufo-model-coverage.md`; the packages of M-QCD: their
    integration blocks in slice-status.md (@status), `docs/user/loop-sm-and-madloop.md` (the `loop_sm` repair rule) and
    the listed refusals of `src/pyamplicol/loops/v2/refusals.py` and `processes/refusals.py`.
  - *@status (M-SM), @msm, @tab:msm, @tab:cms, @tab:msmrows:* `data/msm.json` (`scripts/build_mqcd.py` with `--manifest tests/fixtures/loop/msm/manifest.json`, from the
    campaign's records, rebuilt byte-identically), `data/msm-findings.json`
    (MS-VALIDATE's triage, unchanged at the pin), `data/msm-public.json` (the public-route test file's JUnit outcomes and
    cases), `data/msm-selftest.json` (wheel self-test), combined with the manifest by `scripts/build_msm_matrix.py` into
    `data/msm-matrix.json`; the G1 EW row `data/msm-g1.json` and `data/msm-g1-values.json` (`python -m tools.loop_benchmark gate`
    over the EW records with `--host-spread` = the G1 campaign's `host_provider_spread`; Table 1 through `data/summary.json`); the campaign's records, logs and scripts in
    `workspace/reports/engine-v2/m-sm/records/m1031-msm/` (a copy of `workspace/tmp/campaign-m1031-msm`: `results/`, the
    JUnit and logs of the 32 jobs, `wheel/`, `STATE.md`). Re-run at M-FINAL-b (`617b59cd`): `data/msm.json`,
    `msm-public.json` and `msm-selftest.json` from `workspace/reports/engine-v2/m-sm/records/m1101-mfb/` (a copy of
    `workspace/tmp/campaign-m1101-mfb`: `results/`, the JUnit and logs of its 33 jobs, `wheel/out/`, `compare.py`,
    `msm-table.md`, `STATE.md`). The M-QCD re-run at M-FINAL-b: `data/mqcd.json`, records in
    `workspace/reports/engine-v2/m-qcd/records/m1101-mfb-mqcd/` (`c1/`, `compare.json` against the M-SM re-run's file,
    which came from `records/m1031-msm-mqcd/`). At M-FINAL `data/mqcd.json` is rebuilt from those records with
    mf-8g-3's A24 nightly record (`workspace/tmp/mf-8g-3/a24/results/A24.nightly.json`, catani native) as the later
    directory, and F11 of `data/mqcd-findings.json` is resolved (no new run).
  - *@dec, @tab:dec, @tab:decrows:* `data/dec.json` (`scripts/build_mqcd.py` with `--manifest
    tests/fixtures/loop/dec/manifest.json` and the decay checks' JUnit, re-run at `617b59cd`; `dec-compare.json` against
    MF-DEC-2's file: no status change), combined with the manifest by `scripts/build_dec_matrix.py` into
    `data/dec-matrix.json`; records in `workspace/reports/engine-v2/m-final/records/m1101-mfb-new/` (`results/`,
    `junit/`, `logs/`, `scripts/`, `STATE.md`).
  - *@tab:hc, @tab:corr:* `data/hc.json` and `data/corr.json`, written by `scripts/build_hc.py` and
    `scripts/build_corr.py` from the whole-file jobs of `tests/unit/test_loop_v2_hc.py` and
    `test_loop_v2_corr_recola.py` (their artifacts reloaded, JUnit) in the same records; the rescue and mapping counts of
    @status: that campaign's `junit/rescue.xml` and mf-map-fix's run at `f3d9e361` (slice-status UPDATE 2026-11-02
    \~01:05). HC05's row: the mf-hc05 record (`workspace/tmp/mf-hc05/STATE.md`, slice-status UPDATE 2026-11-03 \~21:25),
    entered by hand (`record`).
  - *@tab:summary ($2 -> 6$ rows), @tab:sixrecs:* `data/2to6.json`, written by `scripts/build_2to6.py` from the
    #sxj.sources.len() mf-2to6 records it lists in `sources` (`workspace/tmp/mf-2to6/runs/`,
    `workspace/artifacts/2to6/*-2f3f76d9/generation.json`, `processes.json`; arguments in
    `workspace/tmp/mf-2to6/build_args.sh`); reproduced byte for byte; Table 1 through `data/summary.json` `preliminary`.
    *@rounds7 (rounds at seven legs):* `data/rounds-7leg.json`, transcribed from
    `workspace/reports/engine-v2/m-final/round-table-7leg.md` (records `workspace/tmp/mf-8g-table/rec/`).
  - *@status (M-QCD), @mqcd, @tab:fft, @tab:mqcdrows:* `data/mqcd.json` (`scripts/build_mqcd.py` from the campaign's
    records), `data/mqcd-findings.json` (MQ-VALIDATE's triage, re-checked at the pin), `data/mqcd-public.json` (the
    public-route representatives), `data/mqcd-fft-cost.json` and `data/mqcd-fft-worst.json` (FFT cost and worst points),
    `data/mqcd-selftest.json` (wheel self-test), combined by `scripts/build_mqcd_matrix.py` into `data/mqcd-matrix.json`;
    the campaign's records, logs and scripts in `workspace/reports/engine-v2/m-qcd/records/m1029-mqcd/` (a copy of
    `workspace/tmp/campaign-m1029-mqcd`: `c1/` results, JUnit and logs, `x/` the FFT and stock-`loop_sm` test logs,
    `public/`, `fft/`, `wheel/`, `STATE.md`).
  - *@tab:summary, @fig:gate:* `data/summary.json`, written by
    `scripts/build_summary.py` from `data/g1.json`, the EW row of `data/msm-g1.json`, `data/measured.json`,
    `data/milestone.json`, `tools/loop_benchmark/processes.json` and the preliminary rows of `data/2to6.json` by its
    main-configuration rule (the most recent measured configuration of each
    cell; a newer check that only repeats part of an older comparison does not
    replace it; revision ancestry from `data/milestone.json`); every entry
    names its configuration and source (README).
  - *@tab:provgen:* HANDOFF §0.1 (addendum F); the provider generation records of
    @tab:summary (`data/summary.json`): `data/g1.json` for the G1 rows and the
    reference runs' records (`workspace/reference/runs/required/<process>/`,
    collected into `data/measured.json`) for the $2 -> 5$ rows; MadLoop's production-build times of the $2 -> 5$ rows: the
    same runs' `madloop-production-result.json`. *@tab:validation, @required, @sevenglue:* the native
    validations on `work/v2-generation-scale`#if C.development_records.records.len() > 0 [ (#records-text)], records
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
    `confirm/<process>/ab.json`, milestone m1025a's at `1d27426b` `m1025a/` (with the frozen-heap launcher
    `gc_launcher.py` and its protocol experiment `gc/`), milestone m1026a's at `11542fd5` `m1026a/` (a copy of
    `workspace/tmp/g1-m1026a/`, with the cold/warm generation A/B `ab/` and in `killed/` the first full-colour
    seven-gluon run, no gate input), milestone m1028a's at `28a16255` `m1028a/` (a copy of the campaign
    `workspace/tmp/g1-m1028a/`: `runs/` with every row's timing, generation, accuracy check and stability rows, round 2
    of the $2 -> 2$ to $2 -> 4$ rows (`m1028a-r2-*`, deciding) and the seven-gluon stores' records, `logs/` with
    `/usr/bin/time -v` and host-load samples (`hostload.txt`, `hostload-r2.txt`), the public-path confirmation
    `confirm/`, the same-core old/new A/B and bisect runs `ab/` with `logs/ab-summary.txt`, the gate inputs
    `out/inputs-final.txt` and labels `out/meta-final.json`, the campaign's scripts `scripts/`), milestone M-QCD's at
    `e18a024b` `m1029-mqcd/` (a copy of `workspace/tmp/g1-m1029-mqcd`: `runs/`, `logs/`, `bin/`, the gate
    inputs `inputs-final.txt`, labels `meta-final.json`, `compare.json`, `gate.log`, `STATE.md`; the seven-gluon stores
    are not copied), milestone M-SM's at `71e2041e` `m1031-msm/` (a copy of `workspace/tmp/g1-m1031-msm`:
    the same files, the EW gate's `msm-g1.json`, `msm-g1-values.json`, `msm-gate.log` and the public-path check
    `confirm/`) and the final retime's (M-LIT-a0, lit-retime) at #raw(g.slice_revision) `mlita0/` (a copy of
    `workspace/tmp/lit-retime`: `runs/`, `logs/`, `bin/`, the gate inputs and labels, `compare.json`, the EW gate's files and
    `confirm/`; the seven-gluon stores are not copied); provider records reused from the first campaign and the fix round, not re-run); the
    earlier $2 -> 5$ records and the provider runs of those rows in
    `workspace/reports/engine-v2/measure-g1-7leg/records/` (`runs-f2/`, `runs-f4/`), MadLoop exports of the G1-only processes in
    `workspace/reference/runs/g1/`; recalibration
    `tools/loop_v2_costmodel.py --g1 data/g1.json`. Builds:
    #raw(g.slice_build) (`loop`, #raw(g.slice_revision))#if g.at("native_build", default: none) != none [ and
    #raw(g.native_build) (`work/v2-generation-scale` #raw(g.native_revision) plus the timers;
    scratch commit #raw(g.native_commit), kept as tag #raw("g1-native-inputs-" + g.native_commit))] else [; history:
    #builds-of(l1-c).map(raw).join([, ]) (`work/v2-generation-scale` #rev-list(ms.development.revisions.keys().filter(r => r not in l1-revs)) plus the timers of
    scratch commit #rev-list(l1-revs), tag #l1-revs.map(r => raw("g1-native-inputs-" + r)).join([, ]): earlier runs, one lane, schedule M, stability) and
    #builds-of(py-c).map(raw).join([, ]) (Python inputs); the earlier runs of M-QCD: `loop-native-v2-slice-d0fef168`, of m1028a: `loop-native-v2-slice-5cb5ea83`, of m1026a: `loop-native-v2-slice-11542fd5`,
    of m1025a: `loop-native-v2-slice-7db32901`, of G-int: `loop-native-v2-slice-4e9b5a9e`],
    release with one codegen unit and thin LTO; the harness is the committed `tools/loop_benchmark` of
    #raw(g.slice_tool_revisions) for every row (the heap freeze in the harness; m1025a's launcher and
    `measure-g1-7leg`'s run worktree `2265a9f7` are history). Schedule M at seven legs: DESIGN §5.6.
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

// ============================================================= APPENDIX ==
// Per-row data of the decay campaign (data/dec-matrix.json rows, from
// data/dec.json; user rule: per-row data in data/ and an appendix).
#pagebreak(weak: true)
#heading(numbering: none)[Appendix: the decay campaign rows] <decrows-sec>

#let dec-b64(r) = { let b = r.binary64_vs_reference; ("born", "finite", "single_pole", "double_pole").map(k => esci(b.at(k, default: none))) }
#figure(kind: table,
  caption: [*Rows of the decay campaign* (`data/dec.json`, written by `scripts/build_mqcd.py` with the decay manifest
    `tests/fixtures/loop/dec/manifest.json` from the campaign's records at #raw(dm.campaign.slice), native
    #raw(dm.campaign.native); through `data/dec-matrix.json` `rows`). Per row: gauge and the Catani route (python: the
    tools' operator; engine: the runtime's `poles = "ir"`), tiers (d default, n nightly) with points · checks · failures,
    binary64 against the MadLoop reference per coefficient (Born, finite, $epsilon^(-1)$, $epsilon^(-2)$; information:
    rule 2 asserts binary64 against DD), the coefficients whose binary64 estimate is out of scope (DD asserted there), the
    extras and the reference fixture.],
  {
    set text(6.3pt, font: sans, stretch: 87.5%)
    set par(justify: false, leading: 0.35em)
    show table.cell.where(y: 0): set text(fill: white, weight: "bold")
    show raw: set text(5.8pt)
    table(
      columns: (0.75cm, 1.9cm, 1.55cm, 2.1cm, 1.05cm, 1.05cm, 1.05cm, 1.05cm, 1.75cm, 0.9cm, 1fr),
      align: (x, y) => if x in (4, 5, 6, 7) { right + horizon } else { left + horizon },
      inset: (x: 2.4pt, y: 1.9pt),
      stroke: (x, y) => (top: if y <= 1 { none } else { 0.3pt + luma(225) }),
      fill: (x, y) => if y == 0 { navy } else { none },
      table.header[Row][Process][Gauge · Catani][Tiers][Born][Finite][$epsilon^(-1)$][$epsilon^(-2)$][Out of scope][Extras][Reference],
      ..dm.rows.map(r => (
        text(weight: "bold", r.row),
        text(7.6pt, font: "Libertinus Serif", math-label(ap-math(r.process))),
        [#r.gauge · #r.catani_route],
        r.tiers.map(t => [#t.tier.first() #t.points · #t.checks · #t.failures]).join([; ]),
        ..dec-b64(r),
        if r.binary64_out_of_scope.len() == 0 [—] else [#r.binary64_out_of_scope.len() × #r.binary64_out_of_scope.first().coefficient.replace("_", " ") (#r.binary64_out_of_scope.first().sector.replace("^", ""))],
        r.extras.join(", "),
        raw(r.reference.split(" ").at(1).split("/").last()),
      )).flatten(),
    )
  },
) <tab:decrows>

// Per-row data of the M-SM campaign (data/msm-matrix.json rows, from
// data/msm.json; user rule: per-row data in data/ and an appendix).
#pagebreak(weak: true)
#heading(numbering: none)[Appendix: the M-SM campaign rows] <msmrows>

#let sm-pts(r) = if r.points.len() == 0 [variants] else { r.points.pairs().map(((t, n)) => [#t.first() #n]).join([ · ]) }
#figure(kind: table,
  caption: [*Rows of the M-SM validation campaign* (`data/msm.json`, written by `scripts/build_mqcd.py` with its M-SM
    manifest from the campaign's records at #raw(sx-pin), native
    #raw(sx.campaign.natives.split(" ").first()); through `data/msm-matrix.json` `rows`). Per row: class, process, model
    and restriction, tiers (d default, n nightly, c campaign) with their points, per-point inputs (n native), the
    reference (ML MadLoop in quadruple precision, "ML d" its double-precision controls, Rc Recola, OL OpenLoops), the
    largest deviations over the row and its gating variants (DD from the reference, rule 1; binary64 from DD, rule 2;
    poles from Catani in DD, rule 4, "≤" a relaxed tolerance; — not formed or no predicted sector), the extras and gating
    variants, the findings that name the row (`data/msm-findings.json`) and the status.],
  {
    set text(6.3pt, font: sans, stretch: 87.5%)
    set par(justify: false, leading: 0.35em)
    show table.cell.where(y: 0): set text(fill: white, weight: "bold")
    show raw: set text(5.8pt)
    table(
      columns: (0.72cm, 1.4cm, 2.9cm, 1.65cm, 1.1cm, 1.3cm, 1.1cm, 1.1cm, 1.35cm, 1fr, 1.15cm, 1.0cm),
      align: (x, y) => if x in (6, 7, 8) { right + horizon } else { left + horizon },
      inset: (x: 2.4pt, y: 1.8pt),
      stroke: (x, y) => (top: if y <= 1 { none } else { 0.3pt + luma(225) }),
      fill: (x, y) => if y == 0 { navy } else { none },
      table.header[Row][Class][Process][Model][Points][Reference][DD][b64/DD][Catani][Extras · variants][Findings][Status],
      ..sx.rows.map(r => (
        text(weight: "bold", r.row), r.class,
        text(7.8pt, font: "Libertinus Serif", math-label(ap-math(r.process))),
        [#sm-mod(r.model)#if r.restriction != "default" [ #r.restriction]],
        [#sm-pts(r)#if r.inputs == "native" [ · n]],
        r.reference.replace("MadLoop (double)", "ML d").replace("MadLoop", "ML").replace("Recola", "Rc").replace("Openloops", "OL").replace(" + ", ", "),
        esci(r.dd_vs_reference), esci(r.binary64_vs_dd),
        if r.catani_dd == none [—] else [#esci(r.catani_dd)#if "4dd" in r.relaxed [ ≤ #sci(r.relaxed.at("4dd"), d: 0)]],
        [#r.extras.join(", ")#if r.extras.len() > 0 and r.variants.len() > 0 [ · ]#r.variants.map(v => [#v.id.split("@").last()#if v.status != "pass" [ #mq-chip(v.status)]]).join(", ")],
        r.findings.join(", "),
        mq-chip(r.status),
      )).flatten(),
    )
  },
) <tab:msmrows>

// Per-row data of the M-QCD campaign (data/mqcd.json; user rule: per-row
// data in data/ and an appendix, not in the main text).
#pagebreak(weak: true)
#heading(numbering: none)[Appendix: the M-QCD campaign rows] <mqcdrows>

#let ap-ref-name(k) = if k.starts-with("njet") { "NJet" } else { (madloop: "ML", recola: "Rc", openloops: "OL").at(k, default: k) }
#let ap-ref(r) = {
  let refs = (r.reference,) + r.variants.filter(v => v.gating).map(v => v.reference)
  let ps = refs.filter(x => x != none).map(x => x.providers).flatten().map(ap-ref-name).dedup()
  if ps.len() == 0 [—] else [#ps.join(", ")]
}
#let ap-pts(r) = r.tiers.pairs().map(((t, x)) => [#t.first() #x.points.len()]).join([ · ])
#let ap-var(r) = { let v = r.variants.filter(v => v.gating); if v.len() == 0 [] else [#v.map(v => [#v.id.split("@").last()#if v.status != "pass" [ #mq-chip(v.status)]]).join(", ")] }
#figure(kind: table,
  caption: [*Rows of the M-QCD validation campaign* (`data/mqcd.json`, written by `scripts/build_mqcd.py` from the
    campaign's records; #mq.campaign_head.split(";").first(), native #raw(mq.native.split(" ").first())). Per row: class,
    process and `loop_sm` restriction, tiers (d default, n nightly) with their points, the reference providers of the row and its gating variants (ML
    MadLoop, Rc Recola, OL OpenLoops, NJet; MadLoop in quadruple precision from MQ-REF), the largest deviations over the row and its gating variants (DD from the
    reference, rule 1; binary64 from DD where asserted, rule 2; poles from Catani in DD, rule 4; — none formed), the
    extras and gating variants (status where not pass), and the row's status; the failures and their findings are in
    `data/mqcd.json` and `data/mqcd-findings.json`.],
  {
    set text(6.4pt, font: sans, stretch: 87.5%)
    set par(justify: false, leading: 0.35em)
    show table.cell.where(y: 0): set text(fill: white, weight: "bold")
    table(
      columns: (0.75cm, 1.55cm, 3.0cm, 1.65cm, 1.1cm, 1.45cm, 1.15cm, 1.15cm, 1.15cm, 1fr, 1.05cm),
      align: (x, y) => if x in (6, 7, 8) { right + horizon } else { left + horizon },
      inset: (x: 2.6pt, y: 1.9pt),
      stroke: (x, y) => (top: if y <= 1 { none } else { 0.3pt + luma(225) }),
      fill: (x, y) => if y == 0 { navy } else { none },
      table.header[Row][Class][Process][Restriction][Points][Reference][DD][b64/DD][Catani][Extras · variants][Status],
      ..mq.rows.map(r => (
        text(weight: "bold", r.id), r.class, text(8pt, font: "Libertinus Serif", math-label(r.process.split(" ").map(ap-tok).join(" "))), r.restriction, ap-pts(r), ap-ref(r),
        esci(r.max_dd_vs_reference), esci(r.max_binary64_vs_dd), if r.max_catani_dd == none [—] else { esci(r.max_catani_dd) },
        [#r.extras.join(", ")#if r.extras.len() > 0 and r.variants.filter(v => v.gating).len() > 0 [ · ]#ap-var(r)],
        mq-chip(r.status),
      )).flatten(),
    )
  },
) <tab:mqcdrows>
