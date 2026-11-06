// pyAmpliCol one-loop benchmarks: the essentials (user 2026-11-06 ~13:25:
// "keep this document to the essential with mostly just the relevant
// tables"). Table 1 (Born-interfered processes), Figure 1 (Table 1 against
// the gate), Table 2 (loop-induced processes), Table 3 (the numbers behind
// Table 1's gate chips and stage bars) and how to read them: the newest
// measurement of each cell only, no history, no milestone narrative, one
// provenance line per table. Every value comes from data/summary.json and
// data/summary-li.json, which scripts/build_summary.py writes from the
// campaign records in data/ (README.md). Build from this directory:
//   typst compile benchmarks.typ benchmarks.pdf
#let S = json("data/summary.json")
#let LI = json("data/summary-li.json")
#let sm = S.meta


// ------------------------------------------------------------------ style --
#let navy = rgb("#1f3b63")
#let pale = rgb("#eef3f9")
#let warm = rgb("#fdf3e7")
#let ink2 = luma(90)
#let hair = 0.4pt + luma(222)
#let sans = "DejaVu Sans"

#set document(title: "pyAmpliCol at one loop — benchmarks", author: "pyAmpliCol developers", date: none)
#set page(paper: "a4", margin: (x: 1.6cm, top: 1.7cm, bottom: 1.6cm), numbering: "1 / 1",
  header: context if counter(page).get().first() > 1 {
    set text(8pt, fill: luma(110))
    [pyAmpliCol at one loop: benchmarks #h(1fr) #sm.date · engine #sm.engine_on_loop]
  })
#set text(font: "Libertinus Serif", size: 10.5pt, lang: "en")
#set par(justify: true, leading: 0.62em)
#show heading.where(level: 1): it => { v(0.45em); block(text(14pt, fill: navy, it)); v(0.1em) }
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

// --------------------------------------------------------- colour scales --
// Run times (user rule (b) of 2026-10-24 ~22:35): diverging green (faster)
// -> white (×1) -> red (slower). Poles #1a9e77 / #d73027: ΔE 9.8 under
// deuteranopia (dataviz validator, light surface); every coloured cell also
// prints its multiplier, so colour never carries the value alone.
#let fast-green = rgb("#1a9e77")
#let slow-red = rgb("#d73027")
#let palette = gradient.linear(fast-green, rgb("#c4e6d9"), white, rgb("#fbd0c3"), slow-red)
#let ratio-fill(r) = if r == none { none } else { palette.sample(calc.clamp(0.5 + calc.log(r, base: 2) / 8, 0, 1) * 100%) }

// Stage colours of the per-point split (Table 1 bars, Table 3's columns):
// categorical slots 1-5 and 7 of the dataviz reference palette, in stage
// order (validated for adjacent pairs, light surface; Table 3 is the table
// view the contrast rule asks for). The seventh, neutral grey, is the
// untimed rest of the call (no stage: a build without per-point input timers).
#let seg-colours = (rgb("#2a78d6"), rgb("#eb6834"), rgb("#1baf7a"), rgb("#eda100"), rgb("#e87ba4"), rgb("#6250d6"), luma(170))

// ----------------------------------------------------------------- tables --
#let dim(body) = text(fill: ink2, body)
#let math-label(s) = eval(s, mode: "math")

// ----------------------------------------------------------------- shared --
// The generated process text ("u u~ > e- e+ g g") as math.
#let tok(t) = if t == ">" { "->" } else if t.ends-with("~") { "overline(" + t.slice(0, -1) + ")" } else if t.ends-with("-") { t.slice(0, -1) + "^(-)" } else if t.ends-with("+") { t.slice(0, -1) + "^(+)" } else { t }
#let amber = rgb("#8a4b08")
#let pass-ink = rgb("#0f7356")
#let fail-ink = rgb("#b2182b")
// Multipliers: two significant figures below 10 (×0.27, ×0.045), integers above.
#let mult2(r) = [×#if r >= 10 { fixed(r, 0) } else if r >= 1 { fixed(r, 1) } else { fixed(r, 1 - calc.floor(calc.log(r, base: 10))) }]
// The user's gate rule (2026-10-24 ~22:35; summary.json
// meta.gate_decisions.threshold_rule): a process whose time per point at
// B = 128 is below 5 ms has no blocking gate; its ratio stays as measured.
#let thr-rule = sm.gate_decisions.threshold_rule

// ================================================================ TABLE 1 ==
// Table 1 renders data/summary.json (scripts/build_summary.py) as is: every
// value, ratio and verdict comes from there; this code only formats them and
// maps a ratio to a colour.
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

// Provenance (main-configuration rule of scripts/build_summary.py): every
// cell shows the most recent configuration that measured it (git ancestry of
// the configurations' revisions, and a G1 campaign's own roles);
// summary.json names it per cell, and meta.configurations lists the
// candidates with the rows (main_rows) and cells (main_cells) where each
// supplies a main value. Stated once in Table 1 (its provenance row: engine,
// native build and digest, date, host); within a row, a cell from another
// configuration than the row's timing is marked: quietly with its revision
// (and its run conditions) if it is a newer record of the same branch, in
// amber with its origin otherwise.
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
#let branch-of(id) = if id == "integrated" { "loop" } else { C.at(id).branch }
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
// The provenance row of Table 1 (one line): the branch once, then per
// configuration its rows, engine revision, native build and digest and date;
// the host once.
#let one-branch = measured-ids.map(branch-of).dedup().len() == 1
#let digest(x) = { let d = x.at("native_digest", default: none); if d == none { none } else [ (#raw(d.slice(0, calc.min(8, d.len())))…)] }
#let native-of(x) = if x.at("native_build", default: none) == none [] else [, native #raw(x.native_build)#digest(x)]
#let cfg-short(id) = {
  let x = C.at(id)
  let rows = row-span(x.main_rows)
  let b = if one-branch { none } else if id == "integrated" [`loop` ] else [#raw(x.branch) ]
  if id == "development_records" [#rec-rows-text(x, compact: true): #b#rev-text(id)#if rec-integrated != none [ (before #x.integration)]]
  else [#rows: #b engine #raw(x.revision)#native-of(x), G1 #x.date]
}
#let header-prov = {
  let lead-in = if not one-branch [] else if measured-ids.first() == "integrated" [`loop`] else { let x = C.at(measured-ids.first()); [#raw(x.branch) (#lab(x))] }
  [*pyAmpliCol: the most recent measured configuration*#if one-branch [ — #lead-in] · #measured-ids.map(cfg-short).join([ · ]) · #sm.host.split(",").first(), shared host]
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
// Rows whose gate verdict is a user decision (legend of Table 1).
#let decided-gate(r) = r.full_colour.main.at("gate", default: none)
#let decided-rows = all-rows.filter(r => { let x = decided-gate(r); x != none and "decision" in x })
// Validation cells with points the user accepted above the check's tolerance.
#let accepted-rows = all-rows.filter(r => "accepted" in r.validation)
#let no-ratio-rows = all-rows.filter(r => r.kind == "g1" and "no_ratio" in r.generation.main)

// ================================================================= PAGE 1 ==
// The first pages hold the title line, Table 1, Figure 1, Table 2 and their
// compact visual legends; the explanations follow in "Reading the tables".
#align(center)[
  #v(-0.3em)
  #text(23pt, weight: "bold", fill: navy)[pyAmpliCol at one loop]
  #v(-0.6em)
  #text(11.5pt, fill: luma(80))[Benchmarks of the recursive one-loop engine against MadLoop, Recola and OpenLoops]
  #v(-0.4em)
  #text(8.6pt, fill: luma(105))[#sm.date · engine #raw(sm.engine_on_loop) · #sm.host.split(",").first(), shared host · finite part, binary64, one pinned thread, $B = 128$]
]

// Compact visual legend of Table 1 (its text: "Reading the tables").
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
  caption: [*Born-interfered one-loop processes* (the one-loop amplitude interfered with the Born). How to read it: #link(<reading>)[after Table 3].],
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
          table.cell(colspan: 5, fill: warm, inset: (x: 4.5pt, y: 2.6pt), { show raw: set text(6.3pt); text(6.6pt, fill: amber)[*$2 -> 6$*: pyAmpliCol only, no provider exists at $2 -> 6$, so no ratio, no gate and no colour · engine #raw(six.engine.revision) (#raw(six.engine.branch)), native #raw(six.engine.native) (#raw(six.engine.native_digest)…), an ancestor of the engine above, not re-run on it · shared host, indicative · internal checks only]}),
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
    // Compact visual key (its text: "Reading the tables").
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
#let li-meta = LI.meta
#let li-rows = LI.groups.map(gr => gr.rows).flatten()
// A group's title from its registry name ("2->3" as $2 -> 3$, "/" as a
// middle dot; any name milestone.json declares).
#let li-group-title(name) = name.split(" / ").map(part => { let xs = part.split("->"); if xs.len() == 2 and xs.all(x => x.trim().len() > 0) { $#xs.at(0).trim() -> #xs.at(1).trim()$ } else { part } }).join([ · ])
// Missing-cell titles; the batch statuses take Table 1's words (status-title).
#let li-title(c) = if c.status in ("not batched", "no gate batch") { status-title(c) } else { (pending: [pending], "not run": [not run], "not recorded": [not recorded]).at(c.status, default: c.status) }
#let li-served = li-rows.filter(r => r.landed)
// The provider line of a row (lit-ref's timings, or why there are none).
#let li-prov-line(r) = {
  let p = r.providers
  if p.status == "pending" [providers pending (lit-ref): #p.expected.join(" · ")]
  else if p.status == "not run" [#p.expected.join(" · "): #p.reason]
  else {
    // Timed providers by time (the fastest in bold), then the others grouped
    // by their status and reason.
    let f = p.fastest
    let timed = p.providers.pairs().filter(((k, x)) => "seconds_per_point" in x).sorted(key: ((k, x)) => x.seconds_per_point)
    let why = (:)
    for (k, x) in p.providers.pairs().filter(((k, x)) => "seconds_per_point" not in x) {
      let g = x.status + ": " + x.reason
      why.insert(g, why.at(g, default: ()) + (pkey(k),))
    }
    (timed.map(((k, x)) => if f != none and k == f.key { text(weight: "bold")[#pkey(k) #dur(x.seconds_per_point)] } else [#pkey(k) #dur(x.seconds_per_point)])
      + why.pairs().map(((g, ks)) => [#ks.join(" · ") #g])).join([~· ])
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
// The provenance row of the loop-induced table (one line): pyAmpliCol's
// records (engine revision, native build and digest) or, without any, the
// engine at this head; the providers' host; the date.
#let li-timed = li-rows.filter(r => r.timing.status == "measured")
#let li-builds = li-timed.map(r => (revision: r.timing.revision, native_build: r.timing.at("native_build", default: none), native_digest: r.timing.at("native_digest", default: none))).dedup()
#let li-hosts = li-rows.filter(r => r.providers.status == "recorded").map(r => r.providers.providers.values().filter(x => "host" in x).map(x => x.host)).flatten().dedup().sorted()
#let li-engine = (revision: li-meta.engine_on_loop, native_build: li-meta.native_build_on_loop.name, native_digest: li-meta.native_build_on_loop.digest)
#let li-head = {
  let ours = if li-builds.len() == 0 [no pyAmpliCol record at this head: every row *pending*, served by the package named in its cell · engine #raw(li-engine.revision)#native-of(li-engine)]
    else [*pyAmpliCol:* #li-builds.map(x => [engine #raw(x.revision)#native-of(x)]).join([, ])#if li-meta.landed.len() > 0 [ (packages landed: #li-meta.landed.map(raw).join(", "))]]
  [#ours · default backend #li-meta.default_backend · providers: `lit-ref`'s production timing records#if li-hosts.len() > 0 [ on #li-hosts.join(", ")] · #li-meta.date · nothing estimated]
}
#figure(kind: table,
  caption: [*Loop-induced processes* ($|A_"loop"|^2$; the equivalent of @tab:summary). How to read it: #link(<reading>)[after Table 3].],
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

// ================================================================ TABLE 3 ==
// The numbers behind Table 1's gate chips and stage bars and Figure 1: the
// full-colour main cell of every row of Table 1 timed at B = 128
// (data/summary.json full_colour.main: median, gate limit, binding provider,
// band, verdict, stages).
#let t3-rows = all-rows.filter(r => r.full_colour.main.status == "measured")
#let t3-keys = stage-keys.filter(k => k != "untimed" or t1-untimed)
#let t3-ms(t) = sig(t * 1000)
#let t3-binding = (MadLoop: "ML", Recola: "Rc", OpenLoops: "OL")
#block(breakable: false, width: 100%)[#figure(kind: table,
  caption: [*Gate and stage split at $B = 128$*, ms per point: the numbers behind the gate chips and stage bars of
    @tab:summary and behind @fig:gate. pyAmpliCol's median (full colour), the binding limit and its provider, the
    uncertainty band of time ÷ limit, the gate chip of @tab:summary, and pyAmpliCol's time per stage.],
  {
    set text(7pt, font: sans, stretch: 87.5%)
    set par(justify: false, leading: 0.4em)
    show table.cell.where(y: 0): set text(6.6pt, fill: white, weight: "bold")
    table(
      columns: (1fr, auto, auto, auto, auto, ..t3-keys.map(_ => auto)),
      align: (x, y) => if x == 0 or x == 4 { left + horizon } else { right + horizon },
      inset: (x: 3pt, y: 2.8pt),
      stroke: (x, y) => (top: if y <= 1 { none } else { hair }),
      fill: (x, y) => if y == 0 { navy } else { none },
      table.header([Process], [ms/pt], [Limit], [Band], [Gate],
        ..t3-keys.map(k => [#key-swatch(seg-colours.at(stage-keys.position(x => x == k)))\ #stage-label.at(k)])),
      ..t3-rows.map(r => {
        let m = r.full_colour.main
        let g = m.at("gate", default: none)
        (
          [#text(8pt, font: "Libertinus Serif", math-label(r.math))#if r.corrections != "QCD" [ #dim[(#r.corrections)]]],
          text(weight: "bold", t3-ms(m.seconds_per_point)),
          if g == none { dim[—] } else [#t3-ms(g.limit_seconds) #dim[#t3-binding.at(g.binding, default: g.binding)]],
          if g == none { dim[—] } else [#sig(g.band.at(0))–#sig(g.band.at(1))],
          if g != none { gate-chip(g) } else { plain-chip[#r.full_colour.gate_rule.replace("->", "→")] },
          ..t3-keys.map(k => t3-ms(m.stages.at(k))),
        )
      }).flatten(),
    )
  },
) <tab:gate>]


// ============================================================== READING ==
// Everything that explains the tables (the first pages carry no prose).
#heading(numbering: none)[Reading the tables] <reading>
#[
#set text(9.4pt)
#set par(justify: true)
// Rows whose fastest provider time is an upper bound (summary.json fastest.bound).
#let bound-rows = all-rows.filter(r => { let f = r.full_colour.at("fastest", default: none); f != none and f.at("bound", default: none) == "upper" })
*@tab:summary* (Born-interfered one-loop processes) has one row per test process, by multiplicity. A cell gives
pyAmpliCol's value in bold and, at its right, the multiplier _pyAmpliCol ÷ the fastest provider_ on this host (in bold
among the provider values).#if bound-rows.len() > 0 [ A provider time marked ≤ (#row-names(bound-rows.map(r => r.key))) comes from a run outside the protocol that does the production work and more (Recola's reference run evaluates the IR poles too), so it bounds that provider's production time from above, and the multiplier against it is a lower bound (≥); it is never a gate limit.] Only run times are coloured: green faster, white at parity, red slower (log₂ scale, clamped at
×1/16 and ×16). Generation multipliers are uncoloured (generation time is not the main metric) and leading colour (LC)
has no provider ratio. Grey cells say why a value is missing. Run times are medians per phase-space point at
$B = 128$, finite part, binary64, one pinned thread, stability checks off; generation is generate + plan export (model
loading excluded) with its peak memory and plan size. The providers run in production mode: MadLoop 3.7.0 (ML),
Recola 2.2.5 with COLLIER (Rc), OpenLoops 2.1.5 from prebuilt libraries (OL: no generation time). Each cell shows the
most recent measured configuration (`scripts/build_summary.py`, by git ancestry of the revisions), named once in the
table's first row (engine, native build and digest, date, host); a cell from another configuration names its origin.#if no-ratio-rows.len() > 0 [ A newer development record's generation in a G1 row has no multiplier (its provider generation is G1's).]

*Gate chips* (@tab:summary, @fig:gate, @tab:gate): the time over the binding limit, the smallest of MadLoop's time and
1.30 × each of OpenLoops' and Recola's; *pass* or *fail* when the whole uncertainty band (@tab:gate) lies below or
above 1, else *open*. A process below 5 ms per point has no blocking gate ("#thr-rule.short", user rule of 2026-10-24)
and its chip keeps the measured ratio; $2 -> 2$ has no gate. The gate is taken at $B = 128$ only#for r in decided-rows.filter(r => decided-gate(r).status != thr-rule.verdict) { let x = decided-gate(r); [; ‡ #box(math-label(r.math)): #x.status (#x.decision), measured #x.measured_status at #fixed(x.ratio_to_limit, 2), band #fixed(x.band.at(0), 2)–#fixed(x.band.at(1), 2)] }.

*Stage bars* (the full-colour cell names the largest share; @tab:gate gives every stage in ms): inputs = trees, Born and
counterterm inputs; numerator = seeds, fused factors and the dressing of the open-loop objects; scatter = closures into
NinjaRS lanes; NinjaRS = the reduction without the masters; masters = the master integrals (canonical arguments, cache,
oneloopmaster); glue = point parameters, input conversion, assembly and the rest of the call#if t1-untimed [; untimed = the rest of the call of a build without input timers].#if m-rows.len() > 0 [ Times use the protocol's schedule B; "M:" gives the schedule G1 adopted for the class.]

*Validation* (process cell): the largest deviation $|a - b| slash max(|a|, |b|, |B| alpha_s slash 2 pi)$ of the binary64
finite part per reference at the timed points (NJet DD: NJet 3.1.2 in double-double), and the median over the points
and references; † the largest lies within pyAmpliCol's binary64 stability estimate at that point; ¶ it is the
reference's own: pyAmpliCol's double-double value lies as far from it, and its binary64 value lies within its estimate
of the double-double one.#for r in accepted-rows { let a = r.validation.accepted; [ ‡ #box(math-label(r.math)): the reference check's points #a.points.map(x => str(x.index)).join(" and ") (#a.points.map(x => sci(x.finite.values().first())).join(" and ") from #r.validation.references.first().short) exceed its tolerance #sci(a.tolerance, d: 0) in binary64: *#a.status* (estimates $E$ #a.points.map(x => sci(x.estimate)).join(" and ")\; pyAmpliCol's double-double values equal the reference's); the check keeps its tolerance#if a.at("passed", default: false) [ and, asserting double-double at these points, passes] else [ and records `passed: false`].] }

#let note-cells = all-rows.map(r => ("generation", "full_colour", "leading_colour").filter(k => "note" in r.at(k).main).map(k => (r: r, k: k))).flatten()
#let cell-word = (generation: [generation], full_colour: [full colour], leading_colour: [leading colour])
#if note-cells.len() > 0 [*Notes under a value* qualify it and leave it as measured, in amber a known limitation, in
grey its run conditions: #note-cells.map(x => [#box(math-label(x.r.math)), #cell-word.at(x.k) ("#x.r.at(x.k).main.note.label"): #x.r.at(x.k).main.note.reason]).join([\; ]).]

#if six != none [*The $2 -> 6$ rows* (`summary.json` `preliminary`, from `data/2to6.json`) have no provider, so no
multiplier, gate or colour; their engine is stated once in the table. Generation = generate + plan export, with the
store, artifact and load beside it ("FC" marks the full-colour generation, LC below it); the timed evaluation is
binary64, finite part, checks off, one pinned thread, at the largest batch measured. The process cell lists the internal
checks ($epsilon^(-2)$: double pole against the universal value; $E$: the stability estimate, with the points above
$10^(-5)$; rescue: the stream points the default rescue policy's binary64 level sends up; Ward on the external gluons;
binary64 against double-double; Catani at full colour; NGluon at leading colour on the all-gluon row) and, in grey,
those not run or not asserted.

]*@fig:gate* places each row's batched full-colour value of @tab:summary (dots) against the providers (diamonds, the
darkest the fastest) and the gate limit (red bar, the shaded side fails; grey bar: the limit of a process below 5 ms,
not gated; dotted line: 5 ms), for the rows with a matched provider.

// The legend of the loop-induced summary table (data/summary-li.json meta).
#let li-inputs = li-meta.inputs.values()
*@tab:summary-li* follows @tab:summary's rules for loop-induced processes, $|A_"loop"|^2$ without a Born: one row per
process of the M-LIT validation matrix (`m-lit/PLAN.md` §4.1; its ids in the process cell), grouped by multiplicity;
the backend-unit, zero, identity, observable and complex-mass-scheme rows (#li-meta.validation_only.ids.join(", ")) are
validation-only and not listed. The cell is the batched $B = #li-meta.gate_batch$ time per point (median, finite part,
one pinned thread, checks off) on the default backend #li-meta.default_backend\; NinjaRS per amplitude, labelled in
the cell, where TIR does not serve the row yet; the other backend's time beside it when both ran. Its multiplier
against the fastest matched provider (MadLoop at its loop-induced production setting 7|6|1, OpenLoops `ls`, Recola;
production mode) colours it with @tab:summary's scale; generation is uncoloured. Rows of four legs or fewer
($2 -> 1$, $1 -> 2$, $2 -> 2$, $1 -> 3$) are reported without a gate; from $2 -> 3$ upward the gate is @tab:summary's
(faster than MadLoop and at most 1.30× each matched OpenLoops and Recola time, on TIRust), "#thr-rule.short" below
5 ms per point, no gate without a matched provider; verdict chips come with the gate tool's records, "no verdict yet"
before them ("no provider time yet" while no provider of the row is timed). Grey cells are explicit markers:
*pending* (the package that serves the row, named in the cell, has not landed at this head, or the input file that
fills the cell does not exist yet), *not run* (a landed package without a record of the row), and a provider's reason
where it has no matched time. Nothing is estimated or extrapolated; each cell shows the newest record of its row. At
this head #li-served.len() of #li-rows.len() rows are served; inputs: #li-inputs.map(x => [#raw(x.file) #if x.present [present] else [not written yet (#x.owner)]]).join([, ])\;
the registry against `lit-ref`'s manifest (#raw(li-meta.campaign.file)): #if li-meta.campaign.checked [checked (#li-meta.campaign.rows rows, #li-meta.campaign.ids ids)] else [#li-meta.campaign.reason].

*@tab:gate* lists, for every row of @tab:summary timed at $B = 128$, the numbers its gate chip and stage bar summarise:
the binding limit and its provider, the uncertainty band of time ÷ limit (the standard error of pyAmpliCol's median over
its timing blocks plus the provider's run-to-run half-range), and the time of each stage. Data: `data/summary.json` and `data/summary-li.json`, written by
`scripts/build_summary.py` from the campaign records in `data/` (`README.md`).
]
