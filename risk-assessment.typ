// Risk assessment document. Built by `risktool build`, which validates the
// Google Sheet and writes build/risk.json first. Method definitions come from
// risk-config.typ; nothing about the method is defined here.

#import "risk-config.typ": config
#import "template.typ": doc, doc-table, lead, th

#let data = json("build/risk.json")
#let final = data.mode == "final"

#let by-id(items, key) = items.fold((:), (acc, it) => { acc.insert(it.at(key), it); acc })
#let hazards = by-id(data.hazards, "hazard_id")
#let situations = by-id(data.situations, "situation_id")
#let mitigations = by-id(data.mitigations, "mitigation_id")
#let bands = by-id(config.bands, "code")
#let levels = ("1", "2", "3", "4", "5")

// ---- Small pieces ---------------------------------------------------------

// Band cell: colour plus letter, so it still reads in grayscale.
#let band-cell(code, ..args) = table.cell(
  fill: rgb(bands.at(code).color), align: center + horizon, ..args,
  text(weight: "bold", bands.at(code).label),
)

#let small(body) = text(8.5pt, body)
#let dash = text(fill: luma(140))[—]
#let ids(list) = if list.len() == 0 { dash } else { list.join(", ") }

#let situation-label(sid) = {
  let s = situations.at(sid)
  [*#sid* #s.persons, #lower(s.ride_phase)#if s.misuse [ (misuse)]: #s.situation]
}

// 5 × 5 matrix, severity 5 at the top. `cell(s, p)` returns the content for
// one cell; `shade(s, p)` whether to use the full band colour.
#let matrix(cell, shade: (s, p) => true, size: 32pt) = {
  let label(body) = text(8pt, body)
  grid(
    columns: (14pt, 16pt) + (size,) * 5,
    rows: (size,) * 5 + (16pt, 14pt),
    align: center + horizon,
    grid.cell(rowspan: 5, rotate(-90deg, reflow: true, label[*Severity*])),
    ..for s in levels.rev() {
      (label(s),)
      for p in levels {
        let code = config.matrix.at(s).at(int(p) - 1)
        let c = rgb(bands.at(code).color)
        (grid.cell(
          fill: if shade(s, p) { c } else { c.lighten(65%) },
          stroke: 0.75pt + black,
          cell(s, p, code),
        ),)
      }
    },
    [], [], ..levels.map(label),
    [], [], grid.cell(colspan: 5, label[*Probability*]),
  )
}

#let count-matrix(scores) = {
  let count(s, p) = scores.filter(x => str(x.s) == s and str(x.p) == p).len()
  matrix(
    shade: (s, p) => count(s, p) > 0,
    (s, p, code) => {
      let n = count(s, p)
      place(top + left, dx: 2.5pt, dy: 2.5pt, text(6.5pt, bands.at(code).label))
      if n > 0 { text(12pt, weight: "bold", str(n)) }
    },
  )
}

// ---- Document -------------------------------------------------------------

#show: doc.with(
  ..config.document,
  status: config.document.status.at(data.mode),
  date: {
    let (y, m, d) = data.date.split("-").map(int)
    datetime(year: y, month: m, day: d)
  },
)

= Method & Scope

This document records the hazard analysis and risk assessment for the ride.
Each risk pairs one hazard with one hazardous situation and describes the
event by which the hazard reaches a person. Risks are scored for probability
and severity before mitigation, mitigated where required, and scored again.
#if not final [This is the preliminary design review issue: it presents the
method, the hazard list and the initial risk scores. Mitigations and residual
risk follow in the final issue.]

== Scope
#config.scope

== Limits
#config.limits

== Severity Scale
#doc-table(
  columns: (38pt, 68pt, 110pt, 1fr),
  header: ([Level], [Qualifier], [Description], [Example]),
  ..for s in levels.rev() {
    let v = config.severity.at(s)
    ([#s], [*#v.name*], [#v.description], small(v.example))
  },
)

== Probability Scale
#doc-table(
  columns: (38pt, 68pt, 110pt, 1fr),
  header: ([Level], [Qualifier], [Frequency], [Typical basis]),
  ..for p in levels.rev() {
    let v = config.probability.at(p)
    ([#p], [*#v.name*], [#v.frequency], small(v.basis))
  },
)

== Risk Matrix
#lead[
Acceptability is read from the matrix below for each severity and probability
pair; it is a lookup, not a score threshold. Every cell carries its band letter
as well as its colour.
]

#grid(
  columns: (auto, 1fr),
  column-gutter: 24pt,
  align: horizon,
  matrix((s, p, code) => text(weight: "bold", bands.at(code).label)),
  {
    set par(first-line-indent: 0pt)
    doc-table(
      columns: (36pt, 1fr),
      header: ([Band], [Meaning]),
      ..for b in config.bands { (band-cell(b.code), [*#b.name* — #b.meaning]) },
    )
  },
)

An initial risk in the #bands.at(config.bands.last().code).name band must be
mitigated and rescored. The final issue requires every residual risk to be
#bands.at(config.acceptable-max).name or better.

== Mitigation Hierarchy
#lead[
Mitigations are listed from most to least effective. Each states whether it
reduces probability (P), severity (S) or both. Severity may only be lowered by
a mitigation of a type marked below; administrative measures can lower
probability but never severity.
]

#doc-table(
  columns: (1fr, 120pt),
  header: ([Type], [May lower severity]),
  ..for t in config.mitigation-types {
    ([#t.name], if t.lowers-severity [Yes] else [No])
  },
)

= Hazard List
#lead[
Hazards are devices, mechanisms, actions or objects with the potential to
cause harm.
]

#doc-table(
  columns: (52pt, 120pt, 1fr),
  header: ([ID], [Category], [Hazard]),
  ..for hz in data.hazards { ([*#hz.hazard_id*], [#hz.category], [#hz.hazard]) },
)

#if final [
  = Hazardous Situations & Coverage

  == Hazardous Situations
  #lead[
  A hazardous situation is a person, in a specific position and state during
  a specific ride phase, where a hazard could reach them. Situations are
  defined independently of hazards so every combination can be considered.
  ]

  #doc-table(
    columns: (52pt, 72pt, 78pt, 44pt, 1fr),
    header: ([ID], [Persons], [Ride phase], [Misuse], [Situation]),
    ..for s in data.situations {
      ([*#s.situation_id*], [#s.persons], [#s.ride_phase],
       if s.misuse [Yes] else [No], [#s.situation])
    },
  )

  == Coverage Grid
  #lead[
  Each cell lists the risks assessed for that hazard and situation, with the
  initial risk band. An empty cell is a combination judged not credible.
  ]

  #let chunk = 9
  #for start in range(0, data.situations.len(), step: chunk) {
    let cols = data.situations.slice(start, calc.min(start + chunk, data.situations.len()))
    doc-table(
      columns: (52pt,) + (1fr,) * cols.len(),
      align: center + horizon,
      header: ([Hazard],) + cols.map(s => [#s.situation_id \ #text(7.5pt, weight: "regular", s.persons)]),
      ..for hz in data.hazards {
        ([*#hz.hazard_id*],)
        for s in cols {
          let here = data.risks.filter(r => r.hazard_id == hz.hazard_id and r.situation_id == s.situation_id)
          (stack(spacing: 2pt, ..here.map(r => box(
            fill: rgb(bands.at(r.initial.band).color), inset: (x: 2pt, y: 2pt), radius: 1pt,
            text(7pt)[#r.risk_id *#bands.at(r.initial.band).label*],
          ))),)
        }
      },
    )
  }
]

= Initial Risk Assessment
Risks are grouped by hazard. P and S are the initial probability and severity;
the band is read from the risk matrix.

#for hz in data.hazards {
  let risks = data.risks.filter(r => r.hazard_id == hz.hazard_id)
  if risks.len() == 0 { continue }
  [== #hz.hazard_id — #hz.hazard]
  doc-table(
    columns: (46pt, 118pt, 1fr, 20pt, 20pt, 30pt),
    header: table.header(
      th[ID], th[Situation], th[Event],
      th(align: center)[P], th(align: center)[S], th(align: center)[Risk],
    ),
    ..for r in risks {
      (
        table.cell(rowspan: 2, align: top)[*#r.risk_id*],
        small(situation-label(r.situation_id)),
        [#r.event],
        table.cell(align: center)[#r.initial.p],
        table.cell(align: center)[#r.initial.s],
        band-cell(r.initial.band),
        table.cell(colspan: 5, small[
          *P#r.initial.p:* #if r.p0_justification != "" { r.p0_justification } else { dash }
          #h(1em) *S#r.initial.s:* #if r.s0_justification != "" { r.s0_justification } else { dash }
        ]),
      )
    },
  )
}

#if final [
  = Mitigations
  #doc-table(
    columns: (44pt, 80pt, 1fr, 54pt, 84pt, 52pt),
    header: ([ID], [Type], [Mitigation], [Reduces], [Implemented in], [Risks]),
    ..for m in data.mitigations {
      ([*#m.mitigation_id*], [#m.type], [#m.mitigation],
       table.cell(align: center, m.reduces.join(", ")),
       small(if m.implemented_in != "" { m.implemented_in } else { dash }),
       small(ids(m.risks)))
    },
  )

  = Residual Risk

  == Risk Matrices
  #lead[
  Number of risks in each cell before and after mitigation. Shaded cells hold
  at least one risk.
  ]

  #grid(
    columns: (1fr, 1fr),
    align: center,
    [*Initial* \ #v(4pt) #count-matrix(data.risks.map(r => r.initial))],
    [*Residual* \ #v(4pt) #count-matrix(data.risks.map(r => r.residual))],
  )

  == Residual Risk Table
  #lead[
  Residual scores after the linked mitigations are in place. Risks without
  mitigations carry their initial scores forward.
  ]

  #doc-table(
    columns: (46pt, 60pt, 20pt, 20pt, 26pt, 20pt, 20pt, 26pt, 1fr),
    header: table.header(
      th(rowspan: 2)[ID], th(rowspan: 2)[Mitigations],
      th(colspan: 3, align: center)[Initial], th(colspan: 3, align: center)[Residual],
      th(rowspan: 2)[Justification],
      ..([P], [S], [Risk], [P], [S], [Risk]).map(x => th(align: center, x)),
    ),
    ..for r in data.risks {
      let just = (("P", r.residual.p, r.p1_justification), ("S", r.residual.s, r.s1_justification))
        .filter(((_, _, t)) => t != "")
        .map(((k, v, t)) => [*#k#v:* #t])
      (
        [*#r.risk_id*], small(ids(r.mitigations)),
        table.cell(align: center)[#r.initial.p], table.cell(align: center)[#r.initial.s],
        band-cell(r.initial.band),
        table.cell(align: center)[#r.residual.p], table.cell(align: center)[#r.residual.s],
        band-cell(r.residual.band),
        small({
          if not r.residual.assessed [_Not mitigated; initial scores carried forward._ ]
          if just.len() > 0 { just.join(h(1em)) } else if r.residual.assessed { dash }
        }),
      )
    },
  )

  = Traceability
  Each risk is traced to its mitigations, the design document section that
  implements them, and the factory acceptance tests that verify them.

  == Document References
  #doc-table(
    columns: (60pt, 1fr),
    header: ([Prefix], [Document]),
    ..for (k, v) in config.document-prefixes { ([*#k*], [#v]) },
  )

  == Traceability Matrix
  #doc-table(
    columns: (46pt, 58pt, 72pt, 1fr, 90pt),
    header: ([Risk], [Mitigation], [Type], [Design reference], [FAT reference]),
    ..for r in data.risks {
      if r.mitigations.len() == 0 {
        ([*#r.risk_id*], table.cell(colspan: 4, small[No mitigations.]))
      } else {
        for (i, mid) in r.mitigations.enumerate() {
          let m = mitigations.at(mid)
          if i == 0 { (table.cell(rowspan: r.mitigations.len(), align: top)[*#r.risk_id*],) }
          ([#mid], small(m.type), small(ids(m.design_ref)), small(ids(m.fat_ref)))
        }
      }
    },
  )
]
