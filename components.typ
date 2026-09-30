// Data loading and building blocks for risk-assessment.typ, kept here so the
// document file is just its content.

#import "risk-config.typ": config
#import "template.typ": doc

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

// Marks prose still to be written, so a gap can't slip into a PDF unnoticed.
#let todo() = text(fill: red, weight: "bold")[\[TODO: write this\]]
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

// ---- Document setup -------------------------------------------------------

// Use as `#show: setup`.
#let setup = doc.with(
  ..config.document,
  status: config.document.status.at(data.mode),
  date: {
    let (y, m, d) = data.date.split("-").map(int)
    datetime(year: y, month: m, day: d)
  },
)
