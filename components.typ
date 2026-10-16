// Data loading and building blocks for risk-assessment.typ, kept here so the
// document file is just its content.

#import "risk-config.typ": config
#import "template.typ": doc, th

#let data = json("build/risk.json")

#let by-id(items, key) = items.fold((:), (acc, it) => { acc.insert(it.at(key), it); acc })
#let tasks = by-id(data.tasks, "task_id")
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

// Marks prose still to be written, so a gap can't slip into a PDF unnoticed.
#let todo() = text(fill: red, weight: "bold")[\[TODO: write this\]]
#let ids(list) = if list.len() == 0 { dash } else { list.join(", ") }

// Cross-references: each ID gets one anchor, placed where it is defined
// (tasks, hazards, situations), assessed (harmful events, Risk Evaluation) or
// described (mitigations, Risk Mitigation).
#let anchor(kind, id) = [#strong(id)#label(kind + "-" + id)]
#let ref-to(kind, id) = link(label(kind + "-" + id), id)
#let refs(kind, list) = if list.len() == 0 { dash } else { list.map(id => ref-to(kind, id)).join(", ") }

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

// Tasks performed by each person class for each use case (ASTM F3529
// Table X1.1), filled from the Tasks tab. Columns follow `classes`, then any
// other class the sheet uses; rows follow the sheet's order of use cases.
// Cells with fewer tasks than their row stretch to fill it.
#let task-table(classes, tasks) = {
  let classes = classes + tasks.map(t => t.person_class).dedup().filter(c => c not in classes)
  let use-cases = tasks.map(t => t.use_case).dedup()
  let entry(t) = [
    #anchor("task", t.task_id) #t.task \
    #small[#t.person#if t.location != "" [ · #t.location]]
  ]
  table(
    columns: (110pt,) + (1fr,) * classes.len(),
    align: left + top,
    inset: (x: 5pt, top: 7pt, bottom: 6pt),
    table.header(
      th(rowspan: 2, align: horizon)[Use Case],
      th(colspan: classes.len(), align: center)[Tasks (by Person)],
      ..classes.map(c => th(align: center, c)),
    ),
    ..for use-case in use-cases {
      let lists = classes.map(c => {
        let l = tasks.filter(t => t.use_case == use-case and t.person_class == c).map(entry)
        if l.len() == 0 { (dash,) } else { l }
      })
      let rows = calc.max(..lists.map(l => l.len()))
      // Emit row by row so Typst's grid places each cell in its column.
      for r in range(rows) {
        if r == 0 { (table.cell(rowspan: rows)[#use-case],) }
        for l in lists {
          if r < l.len() {
            let span = if r == l.len() - 1 { rows - r } else { 1 }
            (table.cell(rowspan: span, l.at(r)),)
          }
        }
      }
    },
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

// ---- Document setup -------------------------------------------------------

// Use as `#show: setup`.
#let setup = doc.with(
  ..config.document,
  date: {
    let (y, m, d) = data.date.split("-").map(int)
    datetime(year: y, month: m, day: d)
  },
)
