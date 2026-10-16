// Risk assessment document. Built by `risktool build`, which validates the
// Google Sheet and writes build/risk.json first. Method definitions come from
// risk-config.typ; data loading and helpers live in components.typ.

#import "risk-config.typ": config
#import "template.typ": doc-table, lead, th
#import "components.typ": *

// ---- Person classes (ASTM F3529 Table X1.1) ------------------------------
// Column order of the Tasks table. The tasks themselves come from the Tasks
// tab; a class used there but not listed here is added as an extra column.
#let person-classes = ("Untrained Person", "Informed Person", "Trained Person")

#show: setup

= Overview & Prerequisites

This Risk Assessment is in compliance with the Standard Practice for Risk
Assessment for Amusement Rides and Devices as defined by ASTM F3598.

== Process
#todo()

== Scope
This Risk Assessment covers the interaction between persons and the amusement
ride.

This document is applicable to the phase of operation after ride
commissioning, but before permanent closure. It does not apply to ride
construction, or deconstruction. Routine disassembly and reassembly are
excluded, as they are not expected based on the prerequisites provided during
the risk assessment process.

Additionally, this document covers the electrical and mechanical interfaces
with the world outside the amusement ride, including electrical connections
and mechanical mounting solutions.

== Definitions
*Persons*: All human persons, as well as the candy riders as defined in the
Ride Engineering Competition Rule Book.

== Risk Assessment Responsible Party
The Risk Assessment Responsible Party, hereafter referred to as "RARP",
consists of the following individuals. Their competencies, as defined by ASTM
F3598, are listed below their name.

#set enum(numbering: "1.a.")

// One entry per RARP member, competencies nested below.
+ Jackson Justus
  + Risk Assessment Process
  + Technical Aspects of the Design
  + Operational Aspects
  + Evacuation Aspects

== Information for Risk Assessment
The information for the risk assessment consists of the following:

+ Theory of Operations
+ Design Documentation
  + Mechanical & Structural Design
  + Control Systems Design
  + ASTM F2291 Compliance
+ Acceptance Documentation
  + Factory Acceptance Tests
+ Service Plan

== Tasks
#task-table(person-classes, data.tasks)

= Hazard Identification

== Hazards
#lead[#todo()]

#doc-table(
  columns: (52pt, 120pt, 1fr),
  header: ([ID], [Category], [Hazard]),
  ..for hz in data.hazards { (anchor("hazard", hz.hazard_id), [#hz.category], [#hz.hazard]) },
)

== Hazardous Situations
#lead[#todo()]

#doc-table(
  columns: (52pt, 46pt, 60pt, 52pt, 1fr),
  header: ([ID], [Task], [Person], [Hazard], [Situation]),
  ..for s in data.situations {
    (anchor("situation", s.situation_id), ref-to("task", s.task_id),
     [#tasks.at(s.task_id).person], ref-to("hazard", s.hazard_id), [#s.situation])
  },
)

== Harmful Events
#lead[#todo()]

#doc-table(
  columns: (46pt, 52pt, 70pt, 1fr, 1fr),
  header: ([ID], [Situation], [Cause type], [Cause], [Harm]),
  ..for e in data.events {
    (strong(ref-to("event", e.event_id)), ref-to("situation", e.situation_id),
     [#e.cause_type], [#e.cause], [#e.harm])
  },
)

= Risk Estimation & Evaluation

== Risk Estimation
#lead[#todo()]

=== Severity Scale
#doc-table(
  columns: (38pt, 68pt, 110pt, 1fr),
  header: ([Level], [Qualifier], [Description], [Example]),
  ..for s in levels.rev() {
    let v = config.severity.at(s)
    ([#s], [*#v.name*], [#v.description], small(v.example))
  },
)

=== Probability Scale
#doc-table(
  columns: (38pt, 68pt, 110pt, 1fr),
  header: ([Level], [Qualifier], [Frequency], [Typical basis]),
  ..for p in levels.rev() {
    let v = config.probability.at(p)
    ([#p], [*#v.name*], [#v.frequency], small(v.basis))
  },
)

== Risk Evaluation
#lead[#todo()]

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

#todo()

#for hz in data.hazards {
  let events = data.events.filter(e => e.hazard_id == hz.hazard_id)
  if events.len() == 0 { continue }
  [=== #hz.hazard_id — #hz.hazard]
  doc-table(
    columns: (44pt, 1fr, 1fr, 18pt, 18pt, 26pt, 62pt, 18pt, 18pt, 26pt),
    header: table.header(
      th(rowspan: 2)[ID], th(rowspan: 2)[Cause], th(rowspan: 2)[Harm],
      th(colspan: 3, align: center)[Initial], th(rowspan: 2)[Mitigations],
      th(colspan: 3, align: center)[Residual],
      ..([P], [S], [Risk], [P], [S], [Risk]).map(x => th(align: center, x)),
    ),
    ..for r in events {
      let just(pairs) = pairs.map(((k, v, t)) => [*#k#v:* #if t != "" { t } else { dash }]).join(h(1em))
      (
        table.cell(rowspan: 2, align: top)[
          #anchor("event", r.event_id) \ #small(ref-to("situation", r.situation_id))
        ],
        [#r.cause], [#r.harm],
        table.cell(align: center)[#r.initial.p], table.cell(align: center)[#r.initial.s],
        band-cell(r.initial.band),
        small(refs("mitigation", r.mitigations)),
        table.cell(align: center)[#r.residual.p], table.cell(align: center)[#r.residual.s],
        band-cell(r.residual.band),
        table.cell(colspan: 9, small[
          _Initial_ #h(0.5em) #just((("P", r.initial.p, r.p0_justification), ("S", r.initial.s, r.s0_justification))) \
          _Residual_ #h(0.5em) #if r.residual.assessed {
            just((("P", r.residual.p, r.p1_justification), ("S", r.residual.s, r.s1_justification)))
          } else [_Not mitigated; initial scores carried forward._]
        ]),
      )
    },
  )
}

= Risk Mitigation
#lead[#todo()]

#for m in data.mitigations {
  [#heading(level: 3)[#m.mitigation_id — #m.mitigation]#label("mitigation-" + m.mitigation_id)]
  block(breakable: false, table(
    columns: (110pt, 1fr),
    th[Status], [#if m.status != "" { m.status } else { dash }],
    th[Type], [#m.type],
    th[Reduces], [#if m.reduces.len() > 0 { m.reduces.join(", ") } else { dash }],
    th[Introduces hazards], refs("hazard", m.introduces_hazard),
    th[Implemented in], [#if m.implemented_in != "" { m.implemented_in } else { dash }],
    th[Design references], ids(m.design_ref),
    th[Verification (FAT)], ids(m.fat_ref),
    th[Harmful events], refs("event", m.events),
  ))
}

= Results

== Coverage Grid
#lead[#todo()]

#let chunk = 9
#for start in range(0, data.tasks.len(), step: chunk) {
  let cols = data.tasks.slice(start, calc.min(start + chunk, data.tasks.len()))
  doc-table(
    columns: (52pt,) + (1fr,) * cols.len(),
    align: center + horizon,
    header: ([Hazard],) + cols.map(t => [#t.task_id \ #text(7.5pt, weight: "regular", t.person)]),
    ..for hz in data.hazards {
      ([*#hz.hazard_id*],)
      for t in cols {
        let here = data.events.filter(e => e.hazard_id == hz.hazard_id
          and situations.at(e.situation_id).task_id == t.task_id)
        (stack(spacing: 2pt, ..here.map(e => box(
          fill: rgb(bands.at(e.initial.band).color), inset: (x: 2pt, y: 2pt), radius: 1pt,
          text(7pt)[#e.event_id *#bands.at(e.initial.band).label*],
        ))),)
      }
    },
  )
}

== Risk Matrices
#lead[#todo()]

#grid(
  columns: (1fr, 1fr),
  align: center,
  [*Initial* \ #v(4pt) #count-matrix(data.events.map(e => e.initial))],
  [*Residual* \ #v(4pt) #count-matrix(data.events.map(e => e.residual))],
)

== Residual Risk Table
#lead[#todo()]

#let justified = data.events.filter(r => bands.at(r.residual.band).justify)
#if justified.len() == 0 [
  No residual risks require justification.
] else {
  doc-table(
    columns: (46pt, 60pt, 20pt, 20pt, 26pt, 20pt, 20pt, 26pt, 1fr),
    header: table.header(
      th(rowspan: 2)[ID], th(rowspan: 2)[Mitigations],
      th(colspan: 3, align: center)[Initial], th(colspan: 3, align: center)[Residual],
      th(rowspan: 2)[Justification],
      ..([P], [S], [Risk], [P], [S], [Risk]).map(x => th(align: center, x)),
    ),
    ..for r in justified {
      let just = (("P", r.residual.p, r.p1_justification), ("S", r.residual.s, r.s1_justification))
        .filter(((_, _, t)) => t != "")
        .map(((k, v, t)) => [*#k#v:* #t])
      (
        strong(ref-to("event", r.event_id)), small(refs("mitigation", r.mitigations)),
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
}
