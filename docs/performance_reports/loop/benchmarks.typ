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

// Stage colours of the per-point split (Table 1 bars, the stage-split table):
// categorical slots 1-5 and 7 of the dataviz reference palette, in stage
// order (validated for adjacent pairs, light surface; the stage table is the
// table view the contrast rule asks for).
#let seg-colours = (rgb("#2a78d6"), rgb("#eb6834"), rgb("#1baf7a"), rgb("#eda100"), rgb("#e87ba4"), rgb("#6250d6"))

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
// gate` from the pyAmpliCol, provider and stability records of the campaign.
#let g = json("data/g1.json")
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
#let mult2(r) = [×#if r >= 10 { fixed(r, 0) } else if r >= 1 { fixed(r, 1) } else { fixed(r, 2) }]
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
#let glue(x) = ("python point parameters", "input conversion", "assembly", "other").map(n => stage(x, n)).sum()
#let numerator(x) = ("seeds", "factors", "dressing").map(n => stage(x, n)).sum()
#let masters(x) = stage(x, "reduction: masters")
#let ninjars(x) = stage(x, "reduction") - masters(x)
#let verdict(x) = if x == none { none } else { x.gate }
#let amber = rgb("#8a4b08")
#let gate-word(gt) = if gt == none [—] else if gt.status == "pass" {
  text(fill: rgb("#2166ac"), weight: "bold")[pass] + [ #fixed(gt.ratio_to_binding_limit, 2)]
} else if gt.status == "fail" {
  text(fill: rgb("#b2182b"), weight: "bold")[fail] + [ #mult2(gt.ratio_to_binding_limit)]
} else if gt.status == "inconclusive" {
  text(fill: amber, weight: "bold")[open] + [ #fixed(gt.ratio_to_binding_limit, 2)]
} else { text(fill: ink2, gt.status) }
#let rev(c) = if c == none { none } else { c.revision.slice(0, 8) }
#let slice-c(p) = cfg(p, "python/full")
#let dev-c(p) = cfg(p, "native/full")
#let l1-c(p) = cfg(p, "native/full/L1")
#let gated = g.processes.filter(p => p.gated)
#let big = "128"

#let ratio-range(xs) = if xs.len() == 0 [—] else { let s = xs.sorted(); if s.len() == 1 [#mult2(s.first())] else [#mult2(s.first())–#fixed(s.last(), if s.last() >= 10 { 0 } else { 1 })] }
#let lim(p, c, b) = { let x = bat(c, b); if x == none or "ratio_to_binding_limit" not in x.gate { none } else { x.gate.ratio_to_binding_limit } }
#let status(c, b) = { let x = bat(c, b); if x == none { none } else { x.gate.status } }
#let int-timed = gated.filter(p => slice-c(p) != none and not refused(slice-c(p)))
#let int-refused = gated.filter(p => refused(slice-c(p)))
#let int-top = int-timed.map(p => lim(p, slice-c(p), top(slice-c(p)))).filter(r => r != none)
#let int-one = int-timed.map(p => lim(p, slice-c(p), "1")).filter(r => r != none)
#let dev-at(c-of, b, s) = gated.filter(p => status(c-of(p), b) == s)
#let dev-pass = dev-at(dev-c, big, "pass")
#let dev-fail = dev-at(dev-c, big, "fail")
#let dev-open = dev-at(dev-c, big, "inconclusive")
#let l1-pass = dev-at(l1-c, "1", "pass")
#let one-pass = dev-at(dev-c, "1", "pass")
#let share(x, v) = v / x.median_seconds_per_point
#let pct(v) = [#fixed(100 * v, 0) %]
#let inputs-share = int-timed.map(p => { let x = bat(slice-c(p), top(slice-c(p))); if x == none { none } else { share(x, python-inputs(x) + stage(x, "input conversion")) } }).filter(v => v != none)
#let trees-share = gated.map(p => { let x = bat(dev-c(p), top(dev-c(p))); if x == none { none } else { (p: p, s: share(x, stage(x, "native trees"))) } }).filter(v => v != none)
// Integrated over native inputs at equal batch size.
#let speedup-at(b) = int-timed.map(p => { let (a, d) = (bat(slice-c(p), b), bat(dev-c(p), b)); if a == none or d == none { none } else { a.median_seconds_per_point / d.median_seconds_per_point } }).filter(v => v != none)
#let lanes-gain = gated.map(p => { let (a, b) = (bat(dev-c(p), "1"), bat(l1-c(p), "1")); if a == none or b == none { none } else { a.median_seconds_per_point / b.median_seconds_per_point } }).filter(v => v != none)
#let names(ps) = if ps.len() == 0 [none] else { ps.map(p => gname(p.key)).join([, ], last: [ and ]) }
#let host-spread = g.host_provider_spread
#let block-unc = gated.map(p => { let x = bat(dev-c(p), big); if x == none { none } else { x.uncertainty } }).filter(v => v != none)
// Providers whose time comes from one run (uncertainty assumed).
#let single-runs = g.processes.map(p => p.provider_uncertainty.pairs().filter(((n, u)) => u.assumed).map(((n, u)) => (p: p, n: n))).flatten()
#let pshort(n) = (madloop: "MadLoop", recola: "Recola", openloops: "OpenLoops").at(n)
// Provider runs not on the core of the native-input configuration.
#let off-core = g.processes.map(p => {
  let c = dev-c(p)
  if c == none or c.host_cpus == none { () } else {
    pnames.filter(n => { let r = prov(p, n); r != none and r.at("cpu", default: none) != none and "median_seconds_per_point" in r and r.cpu != c.host_cpus.first() }).map(n => (p: p, n: n))
  }
}).flatten()
#let short-points = g.processes.map(p => pnames.filter(n => { let r = prov(p, n); r != none and r.at("points", default: 16) < 16 }).map(n => (p: p, n: n, k: prov(p, n).points))).flatten()
#let pairs-text(xs) = xs.map(x => [#pshort(x.n) #gname(x.p.key)]).join([, ], last: [ and ])

// ============================================================== TABLE 1 ==
// Table 1 renders data/summary.json (scripts/build_summary.py) as is: every
// value, ratio and verdict comes from there; this code only formats them and
// maps a ratio to a colour.
#let S = json("data/summary.json")
#let sm = S.meta
#let neutral = luma(243)
#let dur(s) = if s == none [—] else if s < 1 [#sig(s * 1000) ms] else if s < 600 [#sig(s) s] else if s < 10800 [#fixed(s / 60, 1) min] else [#fixed(s / 3600, 1) h]
// Compact scientific notation for deviations: 7.7e−13.
#let esci(x) = {
  if x == none or x == 0 { return [—] }
  let e = calc.floor(calc.log(calc.abs(x), base: 10))
  let m = x / calc.pow(10.0, e)
  if calc.round(m, digits: 1) >= 10 { m = m / 10; e += 1 }
  [#fixed(m, 1)e#str(e).replace("-", "−")]
}
#let dev-tag = box(fill: warm, stroke: 0.3pt + rgb("#d9a066"), inset: (x: 1.6pt, y: 0.7pt), radius: 1.5pt, baseline: 0.6pt, text(5.2pt, weight: "bold", stretch: 100%, fill: amber)[DEV])
#let chip-style = (pass: (rgb("#e1edf7"), rgb("#2166ac")), fail: (rgb("#f9e0da"), rgb("#b2182b")), open: (rgb("#fdf0dc"), amber))
#let gate-chip(g) = {
  let (f, c) = chip-style.at(g.status)
  box(fill: f, stroke: 0.4pt + c, inset: (x: 2pt, y: 0.8pt), radius: 1.5pt, baseline: 0.8pt,
    text(5.9pt, fill: c, weight: "bold")[#g.status #mult2(g.ratio_to_limit)])
}
#let plain-chip(body) = box(fill: white, stroke: 0.4pt + luma(150), inset: (x: 2pt, y: 0.8pt), radius: 1.5pt, baseline: 0.8pt, text(5.9pt, fill: luma(80), weight: "bold", body))
#let stage-keys = ("inputs", "numerator", "scatter", "ninjars", "masters", "glue")
#let stage-label = (inputs: [inputs], numerator: [numerator], scatter: [scatter], ninjars: [NinjaRS], masters: [masters], glue: [glue])
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

// Process column: label, legs, corrections, families, validation.
#let t1-process(r) = table.cell(breakable: false, {
  set par(leading: 0.34em, justify: false)
  block(spacing: 0pt, text(10pt, font: "Libertinus Serif", math-label(r.math)))
  v(3.6pt)
  let f = r.families
  block(spacing: 0pt, text(6.4pt, fill: ink2)[#r.legs legs · #r.corrections · #if f.fc == none [families —] else [#group(f.fc) families]#if f.lc != none [ (LC #group(f.lc))]])
  let val = r.validation
  v(3.4pt)
  if val.status != "compared" {
    block(spacing: 0pt, text(6.4pt, fill: amber, weight: "bold", if r.loop_note != none { r.loop_note } else { val.note }))
  } else {
    // References whose largest deviations lie within a factor 10 share one
    // bound: "ML·OL ≤ 9.2e−13 · Rc 3.3e−10".
    let groups = ()
    for x in val.references.sorted(key: x => x.max_finite) {
      if groups.len() > 0 and x.max_finite <= 10 * groups.last().first().max_finite { groups.last().push(x) } else { groups.push((x,)) }
    }
    block(spacing: 0pt, text(6.6pt)[#groups.map(g => if g.len() == 1 [#g.first().short #esci(g.first().max_finite)] else [#g.map(x => x.short).join("·") ≤ #esci(g.last().max_finite)]).join([ · ])])
    v(2.2pt)
    let wp = val.at("worst_point", default: none)
    let within = if wp != none { wp.within_estimate } else { val.at("within_estimate", default: false) }
    block(spacing: 0pt, text(6.2pt, fill: ink2)[#if val.configuration != "integrated" [#dev-tag ]#val.points pts#if "median_finite" in val [ · median #esci(val.median_finite)]#if within [ · †]#if val.at("note", default: none) != none [ · #val.note]])
  }
})

// Generation column: the fastest provider in bold (the multiplier's reference).
#let t1-generation(r) = {
  let g = r.generation
  let (m, d, f) = (g.main, g.dev, g.fastest)
  let unf = g.at("unfinished", default: (:))
  let parts = ()
  if f != none { parts.push(text(weight: "bold")[#pkey(f.key) #dur(f.seconds)]) }
  parts += g.providers.pairs().filter(((k, x)) => x != none and "seconds" in x and (f == none or k != f.key)).sorted(key: ((k, x)) => x.seconds).map(((k, x)) => [#pkey(k) #dur(x.seconds)])
  if "madloop" in unf { parts.push([ML diagrams #dur(unf.madloop.graph_generation_s), stopped in export]) }
  if "recola" in unf { parts.push([Rc unfinished]) }
  let prov-line = if parts.len() == 0 [no provider generation recorded] else { parts.join([ · ]) }
  let dev-line(full) = if d.status != "measured" { none } else {
    // An older record (no newer one exists) shows its revision and a note.
    let rev = if "note" in d { d.revision } else { none }
    [#dev-tag #if rev != none [#rev] else [#inputs-word(d)] #dur(d.seconds)#if ratio-of(d) != none [ #mult2(ratio-of(d))]#if full [ · #fixed(d.peak_gib, 2) GiB · #sig(d.plan_mb) MB]]
  }
  if m.status == "measured" {
    valued(fill: ratio-fill(ratio-of(m)), dur(m.seconds), mult: if ratio-of(m) != none { mult2(ratio-of(m)) },
      [#fixed(m.peak_gib, 2) GiB peak · plan #sig(m.plan_mb) MB], prov-line, dev-line(false))
  } else if m.status == "refused" {
    absent([refused on `loop`], prov-line, dev-line(true))
  } else {
    absent([not measured on `loop`], prov-line, dev-line(true), d.at("note", default: none))
  }
}

// Full-colour column.
#let t1-fc(r) = {
  let c = r.full_colour
  let (m, d, f) = (c.main, c.dev, c.at("fastest", default: none))
  let prov-line = if f == none { none } else {
    let rest = c.providers.pairs().filter(((k, x)) => k != f.key and "seconds_per_point" in x).sorted(key: ((k, x)) => x.seconds_per_point).map(((k, x)) => [#pkey(k) #dur(x.seconds_per_point)])
    let gone = c.providers.pairs().filter(((k, x)) => x.status == "unavailable").map(((k, x)) => [#pkey(k) no library])
    let nr = c.providers.pairs().filter(((k, x)) => x.status == "not run").map(((k, x)) => [#pkey(k) not exported])
    ((text(weight: "bold")[#pkey(f.key) #dur(f.seconds_per_point)],) + rest + gone + nr).join([ · ])
  }
  let dev-line = if d.status != "measured" { none } else [#dev-tag #inputs-word(d) #dur(d.seconds_per_point) #mult2(ratio-of(d))#if "gate" in d [ #h(2pt) #gate-chip(d.gate)]]
  if m.status == "measured" {
    valued(fill: ratio-fill(ratio-of(m)), dur(m.seconds_per_point), mult: mult2(ratio-of(m)),
      [#prov-line #h(1fr) $B = #m.batch$],
      [#if "gate" in m { gate-chip(m.gate) } else { plain-chip[#c.gate_rule.replace("->", "→")] } #h(4pt) #stage-bar(m.stages)],
      dev-line)
  } else if m.status == "refused" {
    absent([refused on `loop`: #m.at("reason", default: m.error)], prov-line, dev-line, if d.status == "measured" [#dev-tag #stage-bar(d.stages)])
  } else if m.status == "not batched" {
    absent([no batched run on `loop`], [G1 timed $B = #m.timed_batches.map(str).join(", ")$ only (#inputs-word(m) inputs) · #prov-line], dev-line, if d.status == "measured" [#dev-tag #stage-bar(d.stages)])
  } else {
    let rt = c.at("reference_text", default: none)
    let alt = c.at("alternative", default: none)
    absent([not measured],
      if alt == none { none } else [#alt.name #dur(alt.seconds_per_evaluation) per evaluation (one core; not matched)],
      if rt == none { none } else if rt.threshold == "no gate" [no matched provider: reported without a gate (addendum H)] else [providers, s/pt (20 Oct): OL #rt.openloops · Rc #rt.recola · ML #rt.madloop],
      if rt == none or rt.threshold == "no gate" { none } else if rt.threshold == "—" [no production-mode provider time; seven-leg G1 rows not yet timed] else [gate limit #rt.threshold s/pt · seven-leg G1 rows not yet timed])
  }
}

// Leading-colour column (neutral: no provider ratio).
#let t1-lc(r) = {
  let c = r.leading_colour
  let (m, d) = (c.main, c.dev)
  let dev-line = if d.status != "measured" { none } else [#dev-tag #inputs-word(d) #dur(d.seconds_per_point)#if "lc_over_fc" in d [ · LC/FC #fixed(d.lc_over_fc, 2)]#if d.batch != 128 [ · $B = #d.batch$]]
  if m.status == "measured" {
    valued(fill: none, dur(m.seconds_per_point), mult: [#text(6.8pt)[LC/FC] #fixed(m.lc_over_fc, 2)],
      [$B = #m.batch$#if "fc_seconds_per_point" in m [ · FC #dur(m.fc_seconds_per_point)]], dev-line)
  } else {
    absent([not timed on `loop`], dev-line)
  }
}

#let group-title = ("2->2": [$2 -> 2$], "2->3": [$2 -> 3$], "2->4": [$2 -> 4$], "2->5": [$2 -> 5$])

// ================================================================ PAGE 1 ==
#align(center)[
  #v(-0.3em)
  #text(23pt, weight: "bold", fill: navy)[pyAmpliCol at one loop]
  #v(-0.6em)
  #text(11.5pt, fill: luma(80))[The recursive one-loop engine against MadLoop, Recola, OpenLoops and NJet]
  #v(-0.4em)
  #text(8.6pt, fill: luma(105))[#sm.date · engine #raw(sm.engine_on_loop) on `loop` · #sm.host.split(",").first(), shared host · binary64 · one pinned thread · batches of $B = 128$]
]

#block(fill: pale, inset: (x: 9pt, y: 7pt), radius: 3pt, width: 100%, {
  set text(8.4pt)
  set par(justify: true, leading: 0.5em)
  [*Reading guide.* One row per test process, by multiplicity. A cell gives pyAmpliCol's value in bold and, at its right, the
  multiplier _pyAmpliCol ÷ the fastest provider_ on this host (in bold among the provider values); the colour encodes it (blue
  faster, red slower). Main values are the engine on `loop` (gate-G1 campaign, #sm.date); lines tagged #dev-tag are the WP3.1
  development configuration with native per-point inputs and never set a colour. Grey cells say why a value is missing. Run times:
  per phase-space point in batches, finite part, stability checks off; providers in production mode (@status).]
})

#figure(kind: table,
  caption: [*State of the one-loop engine.* Every value from `data/summary.json` (`scripts/build_summary.py`).],
  {
    set text(7pt, font: sans, stretch: 87.5%)
    set par(justify: false)
    show table.cell.where(y: 0): set text(fill: white, weight: "bold", size: 8pt)
    table(
      columns: (0.5cm, 3.95cm, 3.75cm, 5.75cm, 1fr),
      align: left + std.top,
      inset: (x: 4.5pt, y: 4.2pt),
      stroke: (x, y) => (top: if y <= 2 { none } else { 0.6pt + white }, left: if x > 0 { 0.6pt + white } else { none }),
      fill: (x, y) => if y == 0 { navy } else if y == 1 { pale } else { none },
      table.header(
        [], [Process · validation], [Generation], [Full colour · per point, batched], [Leading colour (LC)],
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

#block(breakable: false, width: 100%, {
  set text(6.9pt, font: sans, stretch: 87.5%)
  set par(justify: false, leading: 0.42em)
  grid(columns: (5.4cm, 1fr), column-gutter: 14pt,
    {
      box(width: 5.4cm, height: 0.26cm, fill: palette, radius: 2pt)
      v(-0.5em)
      [×1/16 #h(1fr) ×1/4 #h(1fr) ×1 #h(1fr) ×4 #h(1fr) ×16]
      v(-0.6em)
      text(fill: ink2)[faster #h(1fr) pyAmpliCol ÷ fastest provider #h(1fr) slower]
      v(0.1em)
      text(fill: ink2)[RdBu, log₂ scale, clamped. Grey: missing (reason given). White without a multiplier: no provider ratio.]
    },
    {
      [*Stage shares* (bar; the largest is named): ]
      for (k, n) in stage-keys.enumerate() { box(baseline: 0.5pt, rect(width: 5pt, height: 5pt, fill: seg-colours.at(k), stroke: none)); h(1.5pt); stage-label.at(n); h(5pt) }
      [(@tab:g1split).]
      linebreak()
      [*References:* ML MadLoop 3.7.0, Rc Recola 2.2.5 (COLLIER), OL OpenLoops 2.1.5 (prebuilt libraries: no generation
      time), NJet DD NJet 3.1.2 in double-double. Deviation $|a - b| slash max(|a|, |b|, |B| alpha_s slash 2 pi)$ of the
      binary64 finite part at the timed points (median: over the points, the largest over the references); † the largest lies within pyAmpliCol's own binary64 stability estimate at that
      point. *Gate chip:* time ÷ binding limit (MadLoop, or 1.30 × the faster of Recola and OpenLoops); pass or fail when the
      whole uncertainty band is below or above 1, else open.]
    },
  )
})
#v(0.1em)
#[#show raw: set text(6.8pt)
#text(7.4pt, fill: ink2)[*Configurations.* Main values: _integrated_, the engine on `loop` as timed by gate G1 at
#raw(sm.integrated.revision) (LC: #raw(sm.integrated.lc_revision); both ancestors of `loop`; the later ct-simplify merge was not
re-timed): #sm.integrated.inputs.map(i => inputs-word((inputs: i))).join(", ") per-point trees, Born and counterterm inputs, native loop stage (#raw(sm.integrated.native_build)).
#dev-tag in the $2 -> 3$ and $2 -> 4$ rows: #raw(sm.dev.branch) #raw(sm.dev.revision) with #sm.dev.inputs.map(i => inputs-word((inputs: i))).join(", ") per-point inputs (timers
#raw(sm.dev.commit), #raw(sm.dev.native_build)); in the $2 -> 5$ rows: that branch's validations of
#sm.dev_required.record.split(",").first() (generation, then single points). Generation excludes model loading. Unbatched
development timings, such as a seven-gluon point with its rotation check, are not in this table (@sevenglue).]]

// Figure 1: the batched full-colour time of each G1 row against its gate
// limit and the providers, on a log scale (data/summary.json).
#let fig-lo = calc.log(0.0005, base: 10)
#let fig-hi = calc.log(50.0, base: 10)
#let fig-w = 11.2cm
#let fig-h = 12pt
#let xpos(t) = fig-w * (calc.log(t, base: 10) - fig-lo) / (fig-hi - fig-lo)
#let fig-ticks = ((0.001, [1 ms]), (0.01, [10 ms]), (0.1, [100 ms]), (1.0, [1 s]), (10.0, [10 s]))
#let fig-rows = S.groups.map(g => g.rows).flatten().filter(r => r.full_colour.at("fastest", default: none) != none)
#let dot(fill: none, stroke: none) = circle(radius: 2.9pt, fill: fill, stroke: stroke)
#let fig-row(r) = {
  let c = r.full_colour
  let (m, d) = (c.main, c.dev)
  let g = if "gate" in m { m.gate } else if "gate" in d { d.gate } else { none }
  box(width: fig-w, height: fig-h, {
    for (t, _) in fig-ticks { place(dx: xpos(t), line(start: (0pt, 0pt), end: (0pt, fig-h), stroke: 0.4pt + luma(222))) }
    place(dy: fig-h / 2, line(start: (0pt, 0pt), end: (fig-w, 0pt), stroke: 0.4pt + luma(205)))
    if g != none {
      let xl = xpos(g.limit_seconds)
      place(dx: xl, rect(width: fig-w - xl, height: fig-h, fill: rgb("#d6604d").transparentize(84%), stroke: none))
      place(dx: xl - 0.7pt, rect(width: 1.4pt, height: fig-h, fill: rgb("#b2182b"), stroke: none))
    }
    for (k, x) in c.providers.pairs() {
      if "seconds_per_point" in x {
        let fast = k == c.fastest.key
        place(dx: xpos(x.seconds_per_point) - 2.4pt, dy: fig-h / 2 - 2.4pt,
          rotate(45deg, square(size: 3.4pt, fill: if fast { luma(40) } else { luma(165) }, stroke: 0.4pt + white)))
      }
    }
    let ms = if m.status == "measured" { m.seconds_per_point } else { none }
    let ds = if d.status == "measured" { d.seconds_per_point } else { none }
    if ms != none and ds != none {
      place(dx: xpos(ds), dy: fig-h / 2 - 0.5pt, line(start: (0pt, 0pt), end: (xpos(ms) - xpos(ds), 0pt), stroke: 1pt + luma(130)))
    }
    if ds != none { place(dx: xpos(ds) - 2.9pt, dy: fig-h / 2 - 2.9pt, dot(fill: white, stroke: 1.3pt + rgb("#e08214"))) }
    if ms != none { place(dx: xpos(ms) - 2.9pt, dy: fig-h / 2 - 2.9pt, dot(fill: navy, stroke: 0.6pt + white)) }
  })
}
#figure(
  caption: [*Batched full colour against the gate* ($B = 128$ or the largest batch, finite part; the rows of @tab:summary with a
    matched provider). Filled: the engine on `loop` (integrated; absent where G1 timed only $B = 1$ or the process is refused);
    open: native inputs (#dev-tag); diamonds: the providers, the darkest the fastest; red line: the gate limit, the shaded side
    fails. Values: @tab:summary; the ratios and bands: @tab:g1batch.],
  {
    set text(7pt, font: sans, stretch: 87.5%)
    grid(columns: (3.2cm, fig-w, 1fr), column-gutter: 6pt, row-gutter: 3pt, align: (right + horizon, left + horizon, left + horizon),
      ..fig-rows.map(r => {
        let c = r.full_colour
        let mark(x) = if x == c.main { box(baseline: -0.5pt, circle(radius: 2.4pt, fill: navy)) } else { box(baseline: -0.5pt, circle(radius: 2.1pt, fill: white, stroke: 1.1pt + rgb("#e08214"))) }
        let chips = (c.main, c.dev).filter(x => "gate" in x).map(x => [#mark(x) #gate-chip(x.gate)])
        (text(8.6pt, font: "Libertinus Serif", math-label(r.math)), fig-row(r), if chips.len() == 0 { plain-chip[no gate] } else { chips.join(h(2pt)) })
      }).flatten(),
      [], box(width: fig-w, height: 9pt, for (t, l) in fig-ticks { place(dx: xpos(t) - 1cm, box(width: 2cm, align(center, text(fill: ink2, l)))) }), [],
    )
  },
) <fig:gate>

#pagebreak(weak: true)

// =============================================================== STATUS ==
= Status at this milestone <status>

#let int-gen = gated.filter(p => slice-c(p) != none and not refused(slice-c(p)))
#grid(columns: (1fr, 1fr), gutter: 8pt,
  box-note[
    #set par(justify: false)
    *On `loop`* (engine #ms.engine_revision; merges since #ms.previous_loop)
    #v(-0.2em)
    #set text(8.2pt)
    #table(columns: (auto, auto, 1fr), stroke: none, inset: (x: 2pt, y: 2.2pt),
      ..ms.integrated.map(r => (raw(r.sha), text(weight: "semibold", r.wp), [*#r.title.*])).flatten())
    #v(-0.3em)
    #text(8.2pt)[*Before (#ms.previous_loop):* #ms.already_on_loop.
      *Native build* #raw(ms.native_build.name) (digest #raw(ms.native_build.digest)…).]
  ],
  block(width: 100%, stroke: 0.6pt + luma(195), inset: 9pt, radius: 3pt, {
    set text(8.4pt)
    set par(justify: false)
    [*Gate G1* (@g1; finite part, $2 -> 3$ and beyond)]
    [
      - *On `loop` (integrated): not met.* It fails every gated process it generates, at #ratio-range(int-top) of the
        binding limit at the largest batch (Python per-point inputs take #pct(calc.min(..inputs-share))–#pct(calc.max(..inputs-share))
        of the time), refuses #names(int-refused) ($Z$ fermion signs, WP3.2; Furry zeros, WP3.5), and the $2 -> 4$ rows
        #names(gated.filter(p => slice-c(p) != none and not refused(slice-c(p)) and top(slice-c(p)) == "1")) were timed at $B = 1$ only.
      - *Native inputs* #dev-tag (WP3.1, not yet integrated) at $B = 128$: #dev-pass.len() of #gated.len() pass,
        #names(dev-open) open, #names(dev-fail) fails (×#fixed(lim(gproc("uux_ddxg"), dev-c(gproc("uux_ddxg")), big), 2) of its limit).
        At $B = 1$ #if one-pass.len() == 0 [no process passes] else [#one-pass.len() pass] with 16 lanes (#l1-pass.len() with one lane).
      - *$2 -> 5$:* not timed yet (`measure-g1-7leg`); $g g -> g g g g g$ has no matched provider and is reported without a gate.
    ]
  }),
)

#grid(columns: (1fr, 1fr), gutter: 8pt,
  box-note(fill: white, stroke: 0.6pt + luma(205))[
    #set par(justify: false)
    *In development* (branches, not on `loop`; HANDOFF §6)
    #set text(8.3pt)
    - *Generation at scale* (WP3.1 G-int, `work/v2-generation-scale`): native trees, Born and counterterm inputs per point,
      native families and schedules, regeneration-free artifacts. Its validations are the #dev-tag lines of the $2 -> 5$ rows
      of @tab:summary; integrating it is the next milestone, after which G1 is re-measured on the integrated configuration.
    - *Rust ports* (HANDOFF §0.4): A0 and A1–A2 are on `loop` (not switched on); seeds (B) and cells (C) passed their phase-0
      audits and wait for G-int; lowering (D) is in a fix round; A3 (counterterm-lowered model in the native DAG) is open.
    - *Artifact portability* (partial branch) and the seven-leg G1 rows (`measure-g1-7leg`, specifications and streams).
  ],
  box-note(fill: white, stroke: 0.6pt + luma(205))[
    #set par(justify: false)
    *Missing or incomplete*
    #set text(8.3pt)
    - Electroweak loops, Goldstones and the complex-mass scheme (WP3.2): $g g -> t overline(t) e^- e^+ g$ (EW) not started;
      $V$+jets refused on `loop`.
    - Batched timings of the $2 -> 5$ set; LC timings of the $V$+jets rows; provider protocol-mode columns.
    - Seven-gluon generation cost on the WP3.1 branch: #minutes(meas.required_native.processes.gg_ggggg.generate_s), process
      peak #fixed(meas.required_native.processes.gg_ggggg.max_rss_gib, 1) GiB, mostly the always-generated poles companion
      (@sevenglue); inside addendum H, to be made lean.
    - Ward check at seven gluons; prepared-artifact portability without regeneration (addendum G).
  ],
)

#block(width: 100%, stroke: 0.6pt + luma(195), inset: 9pt, radius: 3pt, {
  set text(8.4pt)
  set par(justify: false)
  [*Performance gates and timing protocol: definitions*]
  [
    - *Gate.* Faster than MadLoop and at most 1.30× each matched Recola and OpenLoops time, on the *finite part*, from
      $2 -> 3$ upward; $2 -> 2$ is reported without a gate. Aspiration: fastest of all tools from $2 -> 3$.
    - *Protocol.* Providers in production mode with poles off where they allow it (OpenLoops `truepoles 0`, Recola without IR
      poles, MadLoop production build); pyAmpliCol finite-only (`poles = "none"`) with stability checks off, one pinned
      thread, binary64, 16 lanes, the same frozen points. Statistic: median per point; the uncertainty band combines
      pyAmpliCol's block spread and the provider's repeat spread; a gate whose band contains the limit is *open*.
    - *Timing boundary.* pyAmpliCol: the public v2 runtime call (`NativeExecutor.evaluate`) for a batch of $B$ distinct
      points, everything included (per-point inputs, loop stage, assembly). Providers have no batch API: one time per point
      serves every $B$. Generation: pyAmpliCol `LoopSlice.generate` plus the plan export, one thread; MadLoop graph
      generation, export and compilation; Recola process generation; OpenLoops libraries are prebuilt (no generation time).
    - *Labels.* Development measurements carry the branch and commit and never drive a colour or a verdict; missing values
      are marked, never estimated or extrapolated; test durations are never used as event timings. The legacy per-diagram
      engine's timings of 18 October are history (data kept in `data/measurements.json`, not shown).
  ]
})

= Gate G1: end-to-end timings of the v2 engine <g1>

G1 times the complete Born–virtual evaluation, *finite part only*, through the
call of the public v2 runtime (`NativeExecutor.evaluate`, which
`V2VirtualRuntime` calls) with stability checks off, on one pinned core and
one thread, binary64, 16 SIMD lanes, in batches of $B$ distinct points of a
frozen stream (REQUIREMENTS_ADDENDUM D, plan §5.8). Two pyAmpliCol
configurations are timed:

- *integrated* — this report's branch at #raw(g.slice_revision) (LC rows at
  #raw(g.slice_lc_revision), the same engine code): the engine on `loop` since
  24 October plus the native-DAG merge (no production call site switched) and
  this package's timers. Trees, Born amplitudes and counterterm
  scalars are formed per point in Python, then the loop stage runs natively.
  It refuses the $V$+jets rows: their closed-quark $A g g$ triangles need
  Furry's certified zeros (WP3.5), and their $Z$ couplings on loop quark lines
  the electroweak fermion signs (WP3.2);
- *native inputs* #flag[development] — `work/v2-generation-scale`
  #raw(g.native_revision) (WP3.1, under integration; scratch commit
  #raw(g.native_commit) adds the timers), where the executor also forms the
  trees, the Born and the counterterm inputs. It generates the $V$+jets rows
  with $gamma$ and $Z$ exchange.

The providers run in production mode on the same stream: OpenLoops with
`truepoles 0`, Recola without IR poles (one amplitude call per point), MadLoop
at its production stability setting on exports built with MG5's production
flags. OpenLoops has no installed library with QCD corrections to
$ell^+ ell^-$ + 1 or 2 jets (`ppllj_ew` carries electroweak corrections only;
existing provider builds only), so the $V$+jets gates bind on MadLoop and
Recola. Providers have no batch API: one time per point serves every $B$.
*Gate statistic:* the median per point on both sides — over pyAmpliCol's
timed blocks of one $B$, and over the provider's timed points (the stream's
first 16; 8 for #pairs-text(short-points)) in its run on the core that timed
the native-input configuration#if off-core.len() > 0 [ (other cores: #pairs-text(off-core))].
Its uncertainty is pyAmpliCol's block spread (half the range of three blocks,
the median's standard error from five) plus the provider's half-range over its
repeated runs (#pct(host-spread), the campaign's largest, for the single runs
of #pairs-text(single-runs)). A gate passes or fails only if the whole band
does; otherwise it is *open* and the configuration is repeated once (plan §5.8
item 10). Every timed call returned all its points (failed points: 0); rescue
is off by protocol (no checks, no escalation), so the rescue rate is 0.

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
  let a = if refused(slice-c(p)) { none } else { verdict(bat(slice-c(p), b)) }
  let d = verdict(bat(dev-c(p), b))
  table.cell(text(6.8pt)[#if refused(slice-c(p)) { text(fill: ink2)[—] } else { gate-word(a) } #linebreak() #gate-word(d)])
}
#figure(kind: table,
  caption: [*Gate G1, full colour*, ms per point (gate statistic: median),
    finite part, one thread. Rows $B = 1$ and $B = 128$ (the integrated $2 -> 4$
    rows only at $B = 1$: their Python inputs take seconds per point).
    Multiplier and colour: time ÷ the fastest provider of the row (legend of
    @tab:summary). Grey rows: generation — pyAmpliCol generation plus plan export with
    its peak memory; MadLoop graph generation, export and compilation · the
    share of its loop-numerator coefficients in its time (@tab:g1split);
    Recola process generation; OpenLoops: the prebuilt library and its load
    plus first call. MadLoop $u overline(u) -> g g g g$ was not exported: the
    $g g -> g g g g$ export took 2.4 h here (HANDOFF §0.1), and OpenLoops binds
    the gate. Gate: upper line integrated, lower line native inputs; the number
    is the time over the binding limit (MadLoop's time or 1.30× the faster of
    Recola and OpenLoops); *open*: the uncertainty band contains the limit
    (@tab:g1batch gives the bands).],
  tstyle(table(
    columns: (2.75cm, 0.75cm, 1fr, 1fr, 1fr, 1fr, 1fr, 1.7cm),
    align: left + horizon, inset: (x: 4pt, y: 2.6pt),
    stroke: (x, y) => (top: if y <= 1 { none } else if calc.rem(y - 1, 3) == 0 { 0.6pt + luma(190) } else { hair }, left: if x >= 2 and y > 0 { hair } else { none }),
    fill: thead-fill,
    table.header[Process][$B$][Integrated][Native inputs#super[dev]][MadLoop][Recola][OpenLoops][Gate],
    ..g.processes.map(p => {
      let (a, d) = (slice-c(p), dev-c(p))
      let bb = if top(d) == none { top(a) } else { top(d) }
      (
        table.cell(rowspan: 3, align: left + horizon, {
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

#let band-cell(c, b) = {
  let x = bat(c, b)
  if x == none { return table.cell(dim[—]) }
  let gt = x.gate
  if "band_to_binding_limit" not in gt { return table.cell(tiny[#gt.status]) }
  let (lo, hi) = gt.band_to_binding_limit
  table.cell(fill: if gt.status == "pass" { rgb("#e8f1f8") } else if gt.status == "fail" { rgb("#fbe3dd") } else { warm }, {
    text(7.6pt, weight: "bold", fixed(gt.ratio_to_binding_limit, 2))
    h(1fr)
    tiny[#fixed(lo, 2)–#fixed(hi, 2)]
  })
}
#figure(kind: table,
  caption: [*The gate at every batch size* (native inputs#super[dev], full
    colour): time over the binding limit and its uncertainty band (cell
    colour: blue pass, red fail, amber open). $B = 1$ is timed with the
    default 16 lanes (a one-point call pays a 16-lane chunk) and with one
    lane. #if dev-c(gproc("uux_uuxg")).earlier_runs.len() > 0 [The
    $u overline(u) -> u overline(u) g$ and $u overline(u) -> d overline(d) g$
    rows are the single repeat; their first runs gave
    #(gproc("uux_uuxg"), gproc("uux_ddxg")).map(p => [#gname(p.key) #msec(dev-c(p).earlier_runs.first().batches.at(big).median_seconds_per_point) ms]).join([ and ]) at $B = 128$.]],
  tstyle(table(
    columns: (2.9cm, 1fr, 1fr, 1fr, 1fr, 1fr),
    align: left + horizon, inset: (x: 4pt, y: 2.6pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][$B = 1$, 16 lanes][$B = 1$, 1 lane][$B = 8$][$B = 32$][$B = 128$],
    ..gated.map(p => (gname(p.key), band-cell(dev-c(p), "1"), band-cell(l1-c(p), "1"),
      band-cell(dev-c(p), "8"), band-cell(dev-c(p), "32"), band-cell(dev-c(p), "128"))).flatten(),
  )),
) <tab:g1batch>

== Where the time goes

#let bar(parts, total, width: 2.8cm) = box(width: width, height: 0.26cm, {
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
  let r = prov(p, "madloop")
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
    MadLoop (instrumented copy; its points less one, 3 for $g g -> g g g g$):
    Born/counterterm HELAS calls, loop-numerator coefficients, reduction plus
    masters, residual (stability test, colour sums). Bar: shares, colours as the
    column heads.],
  tstyle(table(
    columns: (2.4cm, 1.2cm, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr, 1.45cm, 2.8cm),
    align: left + horizon, inset: (x: 3.5pt, y: 2.4pt),
    stroke: (x, y) => (top: if y <= 1 { none } else { hair }),
    fill: thead-fill,
    table.header[Process][][#swatch(0) Trees, Born, CT][#swatch(1) Numerator][#swatch(2) Scatter][#swatch(3) NinjaRS][#swatch(4) Masters][#swatch(5) Glue][Total][Shares],
    ..g.processes.map(p => {
      let rows = ()
      let (a, d) = (slice-c(p), dev-c(p))
      if d != none { rows.push(split-row(tiny[native#super[dev]], bat(d, top(d)))) }
      if a != none and not refused(a) { rows.push(split-row(tiny[integrated], bat(a, top(a)))) }
      let m = ml-row(p)
      if m.len() > 0 { rows.push(m) }
      let n = rows.len()
      rows.enumerate().map(((i, r)) => if i == 0 { (table.cell(rowspan: n, align: left + horizon, gname(p.key)), ..r) } else { r }).flatten()
    }).flatten(),
  )),
) <tab:g1split>

#let fast-word(p) = {
  let x = bat(dev-c(p), big)
  if x == none or "ratio_to_fastest" not in x.gate { return none }
  let f = x.gate.fastest_provider
  let u = x.gate.checks.at(f).uncertainty
  let r = x.gate.ratio_to_fastest
  if r < 1 - u { "faster" } else if r > 1 + u { "slower" } else { "parity" }
}
#box-note(fill: warm, breakable: false)[
  #set par(justify: true)
  *Verdict of gate G1* (processes from $2 -> 3$; $2 -> 2$ without a gate).
  - *Integrated slice: fails* every process it generates, at
    #ratio-range(int-top) of the binding limit at the largest batch and
    #ratio-range(int-one) at $B = 1$; the per-point Python inputs take
    #pct(calc.min(..inputs-share))–#pct(calc.max(..inputs-share)) of its time
    (@tab:g1split). It does not generate #names(int-refused) (counterterm
    coverage: Furry zeros, WP3.5; $Z$ fermion signs, WP3.2).
  - *Native inputs* #flag[development] at $B = 128$: *pass* for
    #names(dev-pass); *fail* for #names(dev-fail)
    (#dev-fail.map(p => [#mult2(lim(p, dev-c(p), big))]).join([, ]) of the limit,
    OpenLoops binding)#if dev-open.len() > 0 [; *open* for #names(dev-open)
    (#dev-open.map(p => fixed(lim(p, dev-c(p), big), 2)).join([, ]) of its limit
    after the single repeat; #dev-open.map(p => [#fixed(lim(p, dev-c(p), "32"), 2) at $B = 32$]).join([, ]))].
    The gate holds for every $B$ (@tab:g1batch): at $B = 1$ with 16 lanes
    #if one-pass.len() == 0 [none passes] else [#names(one-pass) pass] (a
    one-point call pays a 16-lane chunk); with one lane per call
    #names(l1-pass) pass.
  - *Fastest of all tools* (aspiration), native inputs at $B = 128$, within
    the uncertainty band: faster than every provider for
    #names(gated.filter(p => fast-word(p) == "faster"))\; at parity with the
    fastest for #names(gated.filter(p => fast-word(p) == "parity"))\; slower
    than the fastest (OpenLoops) for #names(gated.filter(p => fast-word(p) == "slower")).
    NJet, not a matched provider, takes 4.58 s for its two-evaluation
    full-colour $g g -> g g g g$ test (@tab:njet).
  - Seven-leg rows ($u overline(u) -> e^- e^+ d overline(d) g$, $u overline(u) -> e^- e^+ g g g$,
    $g g -> t overline(t) e^- e^+ g$, $u overline(u) -> g g g g g$, $g g -> g g g g g$)
    need the WP3.1 generator and are added by the follow-on package
    `measure-g1-7leg`; $g g -> g g g g g$ has no matched provider timing
    (addendum F, H): reported without a gate.
]

#let sp-int = speedup-at("1")
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
    [Python inputs #pct(calc.min(..inputs-share))–#pct(calc.max(..inputs-share)) of the integrated time],
    [measured, integrated ÷ native at equal $B$: #ratio-range(sp-int) at $B = 1$, #ratio-range(sp-big) at $B = 128$ ($2 -> 3$)],
    [`generation-scale` (G-int, branch; audit pending)],
    [*Compiled native trees* (kernels as the tree engine's SymJIT planes, lanes batched)],
    [native trees #pct(calc.min(..trees-share.map(t => t.s)))–#pct(calc.max(..trees-share.map(t => t.s))) of the native-input time; #gname(trees-share.sorted(key: t => t.s).last().p.key) #pct(trees-share.sorted(key: t => t.s).last().s)],
    [up to the share; ×#fixed(1 / (1 - calc.max(..trees-share.map(t => t.s))), 1) for the largest],
    [Rust ports A/B (`native-dag`, HANDOFF §0.4)],
    [*Lanes by batch* in binary64 (`plan_export.lanes_for`: 16 lanes also for one point)],
    [$B = 1$: one 16-lane chunk per call],
    [measured: #ratio-range(lanes-gain) at $B = 1$ (16 lanes ÷ 1 lane)],
    [executor policy (WP3.1 or wave 4)],
    [*Finite-only result path* (sum the virtual natively, no per-family lane export, Python assembly only for checks and observables)],
    [glue #pct(calc.min(..gated.map(p => { let x = bat(dev-c(p), big); share(x, glue(x)) })))–#pct(calc.max(..gated.map(p => { let x = bat(dev-c(p), big); share(x, glue(x)) }))) of the native-input time],
    [up to the share (largest at $2 -> 3$ with quarks)],
    [`plan_export`, executor (wave 4)],
    [*Lane-major closures* (no scatter, no second copy into the reducer's batch)],
    [scatter #pct(calc.min(..gated.map(p => { let x = bat(dev-c(p), big); share(x, stage(x, "scatter")) })))–#pct(calc.max(..gated.map(p => { let x = bat(dev-c(p), big); share(x, stage(x, "scatter")) })))],
    [up to the share],
    [executor, reducer adapter (wave 4)],
    [*AVX2 / AVX-512 kernels* (runtime selection)],
    [numerator #pct(calc.min(..gated.map(p => { let x = bat(dev-c(p), big); share(x, numerator(x)) })))–#pct(calc.max(..gated.map(p => { let x = bat(dev-c(p), big); share(x, numerator(x)) })))],
    [×1.0–1.4 on the dressing (gate G0)],
    [wave 4 (WP4.6)],
    [*NinjaRS and masters*: parallel reduction, transposed reduction, stage-2 sharing, a cheaper master cache key],
    [NinjaRS + masters #pct(calc.min(..gated.map(p => { let x = bat(dev-c(p), big); share(x, stage(x, "reduction")) })))–#pct(calc.max(..gated.map(p => { let x = bat(dev-c(p), big); share(x, stage(x, "reduction")) })))\;
      masters #pct(calc.min(..gated.map(p => { let x = bat(dev-c(p), big); masters(x) / stage(x, "reduction") })))–#pct(calc.max(..gated.map(p => { let x = bat(dev-c(p), big); masters(x) / stage(x, "reduction") }))) of the reduction, oneloopmaster alone #pct(calc.min(..gated.map(p => { let x = bat(dev-c(p), big); stage(x, "reduction: masters (oneloopmaster)") / stage(x, "reduction") })))–#pct(calc.max(..gated.map(p => { let x = bat(dev-c(p), big); stage(x, "reduction: masters (oneloopmaster)") / stage(x, "reduction") }))): the cache bookkeeping costs more than the integrals],
    [one thread: up to the share; threads: DESIGN §5.6],
    [NinjaRS requests (DESIGN §11.5)],
  )),
) <tab:levers>

#let ud = gproc("uux_ddxg")
#let udx = bat(dev-c(ud), big)
#let ud-after = udx.median_seconds_per_point - glue(udx) - stage(udx, "scatter")
#let ud32 = bat(dev-c(ud), "32")
The failing native-input row, #gname("uux_ddxg"), takes #msec(udx.median_seconds_per_point) ms
at $B = 128$ against a limit of #msec(udx.gate.binding_limit) ms (OpenLoops
#msec(ptime(ud, "openloops")) ms × 1.30). Its glue and scatter are
#msec(glue(udx) + stage(udx, "scatter")) ms; without them it would take
#msec(ud-after) ms, #fixed(ud-after / udx.gate.binding_limit, 2) of the limit.
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
#block(breakable: false)[#figure(kind: table,
  caption: [*Leading colour* (LC), ms per point, same protocol as @tab:g1; in
    each cell the full-colour (FC) time of the same configuration and batch, and LC/FC.
    No provider ratio: the providers time full colour. LC uses the committed
    QCD colour continuation (`examples/loop/source_colour`); the $V$+jets rows
    were not timed at LC.],
  tstyle(table(
    columns: (2.9cm, 1fr, 1fr, 1fr, 1fr),
    align: left + horizon, inset: (x: 4pt, y: 2.6pt),
    stroke: (x, y) => (top: if y <= 2 { none } else { hair }, left: if x in (1, 3) and y > 0 { 0.6pt + luma(190) } else if x > 0 and y > 0 { hair } else { none }),
    fill: thead-fill,
    table.header(
      table.cell(rowspan: 2, align: left + horizon)[Process], table.cell(colspan: 2, align: center)[Integrated], table.cell(colspan: 2, align: center)[Native inputs#super[dev]],
      table.cell(fill: pale, text(fill: ink2)[$B = 1$]), table.cell(fill: pale, text(fill: ink2)[largest batch]),
      table.cell(fill: pale, text(fill: ink2)[$B = 1$]), table.cell(fill: pale, text(fill: ink2)[largest batch]),
    ),
    ..lc-procs.map(p => {
      let (al, af, dl, df) = (cfg(p, "python/lc"), slice-c(p), cfg(p, "native/lc"), dev-c(p))
      let big-cell(lc, fc) = { let b = top(lc); if b == none { lc-cell(p, lc, fc, none) } else if b == "128" { lc-cell(p, lc, fc, b) } else { let c = lc-cell(p, lc, fc, b); table.cell[#c.body #tiny[($B = #b$)]] } }
      (gname(p.key), lc-cell(p, al, af, "1"), big-cell(al, af), lc-cell(p, dl, df, "1"), big-cell(dl, df))
    }).flatten(),
  )),
) <tab:g1lc>]

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
    inset: (x: 3.5pt, y: 2.6pt), stroke: tstroke, fill: thead-fill,
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

#let est-band(b) = [#sig(1000 * b.at(0))–#sig(1000 * b.at(1))]
#figure(kind: table,
  caption: [*Design estimates recalibrated by G1*
    (#raw("tools/loop_v2_costmodel.py --g1")), ms per point, finite only, one thread. Recipe: DESIGN Table 1a's
    finite-only band (outer factor 1.05–1.10). G1: the recipe's dressing term,
    the NinjaRS model R × #fixed(0.97, 2)–#fixed(1.39, 2) (measured above) and
    the measured outer factor of the row's class representative at $B = 128$
    with native inputs (same colour where measured; LC rows of the $V$+jets
    class take the FC factor, marked †). Measured: G1's own time where the row
    was timed. Gate: 1.3× the best production provider of DESIGN Table 1b
    (seven-leg rows, protocol of 20 October), with the headroom gate ÷ upper
    estimate. The outer factor shrinks with compiled trees (@tab:levers);
    until then these replace the Table 1a targets.],
  tstyle(table(
    columns: (2.7cm, 0.7cm, 1fr, 0.9cm, 2.4cm, 1fr, 1fr, 1fr, 1fr),
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
#let ratio-cell(x, field) = if x == none [—] else { fixed(x.at(field), 2) }
#block(breakable: false)[#figure(kind: table,
  caption: [*Schedule M against B* (native inputs, one thread), pure-gluon
    classes, the only classes where M merges seed entries (DESIGN §5.6). The
    schedule-dependent stages are seeds, factors, dressing, scatter and the
    NinjaRS reduction ("the reduction included", §1.6 item 5); the trees,
    Born and counterterm inputs and the glue are the same work in both
    schedules. M is adopted where M/B ≤ 0.85 on the schedule-dependent
    stages at both batch sizes; ± is the timing uncertainty of the ratio.],
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
*B against M (decision, provisional until the trees are compiled).* On the
schedule-dependent stages M passes the 15 % rule for
#if adopted.len() == 0 [no row] else { adopted.map(r => [#gname(r.p.key) at #if r.s.accuracy == "full" [FC] else [LC]]).join([, ]) }
(as DESIGN §5.6 measured on the dressing side, 0.75–0.80), and not for the
others: $g g -> g g g g$ at FC lies at 0.85–0.88, the rule's edge within its
uncertainty, and $g g -> g g g$ at 0.90–1.0. End to end the gain is diluted by
the tree inputs, which both schedules share and which compiled trees will
shrink (@tab:levers). With a quark line M's entries do not merge at all (M/B
work 1.00, DESIGN §5.6; equal by test). *Decision (G1):* schedule M for
pure-gluon classes at leading colour from $n = 6$; schedule B for every other
class at $n <= 6$, including pure-gluon full colour; M stays the planned
default from $n >= 8$, and both are re-measured at seven legs with the WP3.1
plans (`measure-g1-7leg`).

#let dd-row(p, i) = p.stability.find(r => r.index == i and r.arithmetic == "double-double" and r.configuration == "native/full")
#let b64-row(p, i) = p.stability.find(r => r.index == i and r.arithmetic == "double" and r.configuration == "native/full")
#let best-dev(r) = if r == none or r.deviation_vs_providers.len() == 0 { none } else { r.deviation_vs_providers.pairs().sorted(key: ((n, v)) => v).first() }
#let camp-cell(c) = { let acc = if c == none { none } else { c.at("accuracy_check", default: none) }; if acc == none { dim[—] } else [#sci(acc.max_error) #if not acc.passed [#linebreak() #text(fill: amber, weight: "bold", tiny[above #sci(acc.tolerance)])]] }
#figure(kind: table,
  caption: [*Values at the timed points*: pyAmpliCol's binary64 finite part
    (native inputs) against each provider's production-mode value on the
    common stream points (the providers read the binary64 decimal text of the
    exact points), largest deviation, metric
    $|a - b| slash max(|a|, |b|, |B| alpha_s slash 2 pi)$; Recola's finite part
    converted with the universal double pole (it returns no poles in
    production). Worst point: the point of the row's largest deviation,
    evaluated again with one rotation and the reduction-direction check in
    binary64 and in double-double (DD): $E$ is the binary64 estimate, DD
    the DD value's deviation from the closest provider (named). Campaign: the
    first three points against the committed references
    (`tests/fixtures/loop/required`), fixture metric and tolerance, native
    inputs and integrated.],
  tstyle(table(
    columns: (2.7cm, 0.65cm, 1fr, 1fr, 1fr, 1.25fr, 1.45fr, 1fr, 1fr),
    align: (x, y) => if x == 0 { left + horizon } else { right + horizon },
    inset: (x: 3.5pt, y: 2.6pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][Pts][vs MadLoop][vs Recola][vs OpenLoops][Worst point: $E$][DD: closest provider][Campaign, native][Campaign, integr.],
    ..g.processes.map(p => {
      let c = dev-c(p)
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
        camp-cell(c), camp-cell(slice-c(p)))
    }).flatten(),
  )),
) <tab:g1values>

#let all-born = g.processes.map(p => { let c = dev-c(p); if c == none or c.values_vs_providers == none { () } else { c.values_vs_providers.values().map(x => x.max_born_deviation) } }).flatten()
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
against #sci(b64-row(gproc("uux_gggg"), 9).deviation_vs_providers.openloops) in binary64) — the deviation is pyAmpliCol's own binary64
loss, which $E$ flags. The other deviations above 10⁻¹¹ stay in DD and are
the providers' own accuracy: Recola's at $u overline(u) -> d overline(d) g$
(#sci(dd-of("uux_ddxg", 1, "recola"))), $u overline(u) -> u overline(u) g$ and
$u overline(u) -> e^- e^+ g g$ (COLLIER's default target $10^(-8)$, HANDOFF
§7), OpenLoops' at $u overline(u) -> g g g$ (#sci(dd-of("uux_ggg", 2, "openloops"))) and MadLoop's at
$u overline(u) -> e^- e^+ g g$ (#sci(dd-of("uux_emepgg", 8, "madloop"))); MadLoop's production values also stay
off the DD values at the ill-conditioned gluon and top points (up to
#sci(calc.max(..ml-dd))). At the campaign points $g g -> g g g g$ point 1
misses the fixture tolerance (#sci(dev-c(gg4).accuracy_check.tolerance, d: 0)) in binary64 on both paths, within
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

#block(breakable: false)[#figure(kind: table,
  caption: [*Provider generation on this host and the 45-minute rule.* MadLoop
    graph generation, export and compilation; Recola process generation;
    OpenLoops: prebuilt public libraries (HANDOFF §0.1; the measured times of
    the $2 -> 5$ rows are in @tab:summary).],
  tstyle(table(
    columns: (3.4cm, 3.9cm, 2.2cm, 1.9cm, 1fr),
    align: left + horizon, inset: (x: 4pt, y: 3.1pt), stroke: tstroke, fill: thead-fill,
    table.header[Process][MadLoop][Recola][OpenLoops][45-minute rule],
    ..ms.provider_generation.rows.map(r => (
      if r.label.contains("controls") { text(8.4pt, font: "Libertinus Serif")[$2 -> 2$, $2 -> 3$ controls] } else { plabel(r) },
      r.madloop, r.recola, r.openloops,
      if r.rule.starts-with("within") { r.rule } else { text(weight: "semibold", fill: rgb("#8a4b08"), r.rule) },
    )).flatten(),
  )),
) <tab:provgen>]

#let rn = meas.required_native
#let coeff = ("born", "finite", "single_pole", "double_pole")
#let rn-max(rec, k) = { let v = rec.max_deviation.values().filter(d => k in d).map(d => d.at(k)); if v.len() == 0 { none } else { calc.max(..v) } }
#let rn-refs(rec) = rec.max_deviation.keys().map(k => (madloop: "ML", recola: "Rc", openloops: "OL", njet_dd_oneloop_R1: "NJet DD", njet_double_R1: "NJet R1", njet_double_R2: "NJet R2", catani: "Catani").at(k, default: k)).join(", ")
#let rn-label(key) = { let r = S.groups.map(g => g.rows).flatten().find(r => r.key == key); math-label(r.math) + if key.ends-with("_qcd") [ (QCD)] }
#figure(kind: table,
  caption: [*Native validation of the required set* #dev-tag (#raw(rn.branch), #rn.record): generation in one thread
    (`LoopSlice.generate`, then the plan export; peaks of each stage), then binary64 virtuals with native per-point inputs and
    the production counterterm route at the fixture points, against the committed references
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
      tiny[#rn-refs(rec) · #rec.points.len() pts],
      ..coeff.map(k => sci(rn-max(rec, k))),
      if rec.stability_estimate_per_point.all(e => e != none) { rec.stability_estimate_per_point.map(e => sci(e)).join(", ") } else { dim[—] },
      [#sig(rec.generate_s + rec.export_s) s #tiny[#fixed(calc.max(rec.generate_peak_gib, rec.export_peak_gib), 1) GiB]],
    )).flatten(),
  )),
) <tab:validation>

#let ttq = rn.processes.gg_ttxemepg_qcd
#let ttq-old = ms.required.rows.find(r => r.label.starts-with("g g -> t overline(t) e^- e^+ g") and r.at("corr", default: none) == "QCD")
#let ttq-errs = ttq.max_error_per_point.sorted()
The $g g -> t overline(t) e^- e^+ g$ (QCD) finite part deviates by #sci(ttq-errs.last()) at one of its three points and by at
most #sci(ttq-errs.at(-2)) at the others: the point's known binary64 conditioning (earlier record, DESIGN WP3.1 fourth
increment: #ttq-old.validation). The electroweak target is not started (WP3.2), and $u overline(u) -> g g g g g$ has no
native validation record yet; its earlier development comparison is in @tab:sevencheck.

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

== pyAmpliCol at seven gluons #dev-tag

#let g7 = rn.processes.gg_ggggg
#let g7-dd = g7.max_deviation.njet_dd_oneloop_R1
On the WP3.1 branch (@tab:validation) the full $g g -> g g g g g$ virtual, with the counterterms of the recursion and native
per-point inputs, top-free with $N_f = 5$, agrees with NJet's double-double values to #sci(g7-dd.finite) in the finite part
(per point: #g7.max_error_per_point.map(e => sci(e)).join(", ") over all references) and to #sci(g7-dd.double_pole) in the
double pole; each point's rotation plus reduction-direction estimate bounds its difference. Generation took
#minutes(g7.generate_s) at #fixed(g7.generate_peak_gib, 1) GiB and the plan export #minutes(g7.export_s) at
#fixed(g7.export_peak_gib, 1) GiB (process peak #fixed(g7.max_rss_gib, 1) GiB, #sig(g7.plan_json_mb) MB of plan JSON), inside
addendum H's budget (hours, below 150 GB). DESIGN WP3.1 (eighth increment) attributes the cost: 325 s before the
counterterm recursion, 1,122 s with its counterterm program, 2,766 s once poles-uvir's always-generated companion merged (its
seed table builds generic seeds; making it lean is open). A point with its rotation and reduction-direction checks took
#g7.seconds_per_point_unbatched.map(t => sig(t)).join(", ") s: single-point development evaluations, unpinned, with up to
eight threads (the workspace sets `RAYON_NUM_THREADS=8`), so not a batched one-thread time and not comparable with NJet's
#ms.njet.single_evaluation.standard s per evaluation on one pinned core. No batched seven-gluon timing exists yet;
@tab:summary therefore has none.

== Validation without a matched provider

#let nv = ms.njet_validation
#let ux = sg.uux_ggggg_vs_providers.max_relative_deviation
#let g7-cat = g7.max_deviation.catani
#figure(kind: table,
  caption: [*Checks of the seven-leg QCD results*, #dev-tag on `work/v2-generation-scale`, except the Ward row (WP2.5 on
    `loop`); binary64, all three Laurent coefficients, deviation metric of @tab:summary. NJet values: fixture
    `gg_ggggg_njet.json` (NJet 3.1.2 double-double at exactly rotated points, scaling-test estimates ≤ #sci(1.3e-24)).],
  tstyle(table(
    columns: (4.4cm, 1fr, 2.9cm),
    align: left + horizon, inset: (x: 4pt, y: 2.8pt), stroke: tstroke, fill: thead-fill,
    table.header[Check][Result][Status],
    [$g g -> g g g g g$ full virtual against NJet (top-free, $N_f = 5$), #g7.points.len() points (#rn.record.split(",").first())],
    [Born ≤ #sci(g7-dd.born), finite ≤ #sci(g7-dd.finite), single pole ≤ #sci(g7-dd.single_pole), double pole ≤ #sci(g7-dd.double_pole);
      Catani poles: single ≤ #sci(g7-cat.single_pole), double ≤ #sci(g7-cat.double_pole); estimates #g7.stability_estimate_per_point.map(e => sci(e)).join(", ")],
    [#if g7.passed [passed] else [failed] (tolerance #sci(g7.tolerance, d: 0))],
    [Top-free full virtual against NJet at lower multiplicity],
    [#nv.topfree.lower.map(l => [#math-label(l.label): #l.value]).join([; ]) (`test_loop_v2_topfree.py`)],
    [passed],
    [$u overline(u) -> g g g g g$ full virtual against MadLoop and Recola, #sg.uux_ggggg_vs_providers.points points],
    [MadLoop ≤ #sci(calc.max(..ux.madloop.values())), Recola ≤ #sci(calc.max(..ux.recola.values())) (finite ≤ #sci(ux.recola.finite)); the providers agree to 6.2×10⁻¹⁰],
    [passed],
    [Ward identity, one gluon's $epsilon -> p$, at seven gluons],
    [asymmetric Ward mode of WP2.5 (loop side only, bare + UV + $R_2$); passes on $g g -> g g$ and $u overline(u) -> g g g$ (`test_loop_v2_observables.py`)],
    text(fill: rgb("#8a4b08"), weight: "semibold")[not yet run at seven gluons (addendum H)],
  )),
) <tab:sevencheck>

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
  ([Native executor, schedules], "supported", [Rust, 16 lanes (also for a one-point call, a G1 lever), threads; G1 decision on the schedule-dependent stages (@tab:g1bm, provisional until compiled trees): M for pure-gluon LC from $n = 6$, B for every other class at $n <= 6$; F as oracle. The NinjaRS reduction runs serially. Development report: stage times, modelled kernel work, master-integral time.]),
  ([Plan v4 artifacts and API], "partial", [Published and loaded through Python, TOML and CLI; relocation to another path tested on the same host and CPU. Loading regenerates the process (the `LoopSlice`) in Python and checks the plan digest, which addendum G forbids for prepared artifacts; WP3.1 removes it. The Rust/C/C++/Fortran SDK refuses v4 until WP3.1.]),
  ([Counterterms (model UV, $R_2$)], "supported", [Plain tree vertices of the recursion inserted exactly once (WP2.2, a18b7599; addendum J, b4d76cc3), admitted by coupling orders and the public `particle_veto`; no witness table or loop matching in production. An unlowerable counterterm vertex that no tree of the request reaches is inert and recorded in the artifact; a reachable one is refused. Site closure is the test oracle. Per point they are formed in Python on `loop`, natively on the WP3.1 branch.]),
  ([Direct $R_2$], "deferred", [A bonus by the user's rule; bounded controls only.]),
  ([Electroweak, complex mass], "open", [Tree EW lanes fixed, the Dirac–Weyl class refused; loop EW, Goldstones and CMS are WP3.2.]),
  ([Required set], "progress", [On the WP3.1 branch seven of eight generate and agree with their references in all coefficients with native inputs (@tab:validation), $g g -> g g g g g$ against NJet's double-double values; the EW target is not started. Not on `loop` yet; no batched $2 -> 5$ timing.]),
  ([Performance gates], "progress", [G1 measured (@g1): the integrated slice fails every $2 -> 3$ and $2 -> 4$ gate it generates (Python per-point inputs) and does not generate $V$+jets (WP3.5, WP3.2). With the WP3.1 native inputs at $B = 128$: #dev-pass.len() of #gated.len() pass, #names(dev-open) open, #names(dev-fail) fails; $B = 1$ needs lane adaptation (@tab:g1batch). Missing: provider protocol-mode columns, LC for $V$+jets, seven legs (`measure-g1-7leg`).]),
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
JSON of exact kernel term lists, no compiled code, digest checked at load).

#block(breakable: false)[#figure(kind: table,
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
    `Integrate …` merges of #ms.engine_revision since #ms.previous_loop;
    `workspace/reports/engine-v2/slice-status.md` (integration blocks,
    DECISIONS 2026-10-23/24); `HANDOFF_24_10_2026.md`; MASTER_PLAN
    2026-10-23/24 entries; REQUIREMENTS_ADDENDUM A, D, F, G, H, I, J; DESIGN §5.7
    (G1), §6.1, §6.2, §12.4; the 24 October pushes (59badc7a and b4d76cc3,
    gates in slice-status.md).
  - *@tab:summary, @fig:gate:* `data/summary.json`, written by
    `scripts/build_summary.py` from `data/g1.json`, `data/measured.json`,
    `data/milestone.json` and `tools/loop_benchmark/processes.json`; every
    entry names its source (README).
  - *@tab:provgen:* HANDOFF §0.1 (addendum F); the measured provider generation
    times of @tab:summary from the reference runs' records
    (`workspace/reference/runs/required/<process>/`, collected into
    `data/measured.json`). *@tab:validation, @required, @sevenglue:* the native
    validations of DESIGN WP3.1 eighth increment (0ea83af2) on
    `work/v2-generation-scale`, records
    `workspace/tmp/generation-scale/gint/val1/` and `val2/`, collected into
    `data/measured.json`; the earlier $g g -> t overline(t) e^- e^+ g$ and
    $u overline(u) -> g g g g g$ records: DESIGN WP3.1 first to fourth
    increment. *Conventions:*
    #link("https://cp3.irmp.ucl.ac.be/projects/madgraph/wiki/MadLoopStandaloneLibrary")[MadLoop standalone],
    #link("https://arxiv.org/abs/1605.01090")[Recola],
    #link("https://arxiv.org/abs/1907.13071")[OpenLoops 2].
  - *@g1 (@tab:g1 to @tab:g1values):* `data/g1.json` and the per-point values
    `data/g1-values.json`, written by `python -m tools.loop_benchmark gate`
    (README and docstrings of `tools/loop_benchmark`); streams
    `tools/loop_benchmark/streams/`; run records archived in
    `workspace/reports/engine-v2/measure-g1/records/` (first campaign `runs/`,
    fix round `runs2/`), MadLoop exports of the G1-only processes in
    `workspace/reference/runs/g1/`; recalibration
    `tools/loop_v2_costmodel.py --g1 data/g1.json`. Builds:
    #raw(g.slice_build) (integrated, this branch at #raw(g.slice_revision)) and
    #raw(g.native_build) (`work/v2-generation-scale` 889af02c plus the timers;
    scratch commit #raw(g.native_commit), kept as tag `g1-native-inputs-39824f9b`),
    release with one codegen unit and thin LTO; the native-input harness is this
    branch's `tools/loop_benchmark`. Schedule M at seven legs: DESIGN §5.6.
  - *@tab:njet* and NJet prose: `workspace/reports/engine-v2/njet-benchmark.md`
    §2, §5, §6 (raw `workspace/reference/runs/njet/timing/`);
    #link("https://arxiv.org/abs/1209.0100")[NJet, arXiv:1209.0100] Table 5.
  - *@tab:sevencheck:* `data/measured.json`
    (`scripts/collect_milestone.py <workspace>`); top-free values at lower multiplicity: DESIGN WP3.1 and
    `test_loop_v2_topfree.py`; the seven-gluon generation history: DESIGN WP3.1
    eighth increment. Memory in GiB = 2³⁰ bytes.
  - *@tab:caps, @arch:* `docs/development/loop_v2/DESIGN.md` §1–§3, §5.5,
    §5.6, §6, §10, §12, REQUIREMENTS_ADDENDUM J (counterterm rule) and the
    integration records above.
  - *History:* the legacy per-diagram engine's snapshot of 2026-10-18
    (`data/measurements.json`, `provider-cold.json`, `legacy-labels.json`,
    `colour-measurements.json`) stays for the DESIGN citations and is no longer
    shown; its table is in the earlier report revisions (README).
]
