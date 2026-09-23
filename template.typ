// Terrier Ride Engineering Club technical documentation style.
// Measured from "00 TEMPLATE.pdf": US Letter, 1in margins, Helvetica Neue
// 10pt body, red 16pt numbered sections over a grey rule, red table headers,
// grey centred footer. The cover title and section headings use Raleway Bold,
// which isn't committed: see "Fonts" in the README.

#let red = rgb("#d20000")
#let rule-grey = rgb("#cccccc")
#let footer-grey = rgb("#c1c1c1")
#let sans = ("Helvetica Neue", "Helvetica", "Arial")
#let heading-sans = ("Arial", "Helvetica Neue")
// Raleway defaults to old-style figures; section numbers need lining ones.
#let display(..args) = text(font: ("Raleway", "Arial"), weight: "bold", number-type: "lining", ..args)

// Table with the template's red header row(s). `header` is an array of
// cells or a single table.header(..) when spans are needed.
// Short tables (≤ 8 rows) are kept on one page.
#let doc-table(columns: (), header: (), align: left + horizon, ..body) = block(
  breakable: body.pos().len() > 8 * columns.len(),
  table(
  columns: columns,
  align: align,
  inset: (x: 5pt, top: 9.3pt, bottom: 7.6pt),
  stroke: 0.75pt + black,
  fill: (_, y) => none,
  if type(header) == array {
    table.header(..header.map(h => table.cell(fill: red, text(fill: white, weight: "bold", h))))
  } else { header },
  ..body,
))

// Paragraph that stays on the same page as the table or figure after it.
#let lead(body) = block(sticky: true, par(body))

// Red header cell for tables that build their own table.header(..).
#let th(body, ..args) = table.cell(fill: red, ..args, text(fill: white, weight: "bold", body))

#let doc(
  title: "SYSTEM NAME",
  subtitle: "Technical Documentation",
  organization: "Terrier Ride Engineering Club",
  institution: "Boston University",
  event: "Ride Engineering Competition",
  date: datetime.today(),
  status: "Prototyping",
  body,
) = {
  set document(title: title, author: organization)
  set text(font: sans, size: 10pt, lang: "en")
  let footer = context align(center, text(9pt, fill: footer-grey)[
    #organization — #institution#h(5pt)|#h(5pt)#event#h(5pt)|#h(5pt)Page #counter(page).display()
  ])
  set page(paper: "us-letter", margin: 1in, footer-descent: 16pt, footer: footer)
  set par(leading: 7.3pt, spacing: 17pt, first-line-indent: (amount: 0.5in, all: true))
  set list(marker: [●], indent: 0.75in, body-indent: 0.25in, spacing: 7.3pt)
  set enum(indent: 0.25in, body-indent: 0.25in, spacing: 7.3pt)
  set table(stroke: 0.75pt + black)
  show table: set par(first-line-indent: 0pt, leading: 5pt, spacing: 8pt)
  show table: set align(left)
  // External links are blue and underlined; internal ones (contents) are not.
  show link: it => if type(it.dest) == str { underline(text(fill: rgb("#1155cc"), it)) } else { it }

  set heading(numbering: (..n) => if n.pos().len() == 1 { numbering("1.", ..n) })
  show heading.where(level: 1): it => {
    pagebreak(weak: true)
    block(above: 0pt, below: 14.3pt, inset: (top: 3.6pt), stack(
      spacing: 8.9pt,
      display(size: 16pt, fill: red, {
        if it.numbering != none { box(width: 27pt, counter(heading).display(it.numbering)) }
        it.body
      }),
      line(length: 100%, stroke: 1.5pt + rule-grey),
    ))
  }
  show heading.where(level: 2): it => block(above: 18pt, below: 19pt, sticky: true,
    text(size: 14pt, weight: "bold", it.body))
  show heading.where(level: 3): it => block(above: 14pt, below: 10pt, sticky: true,
    text(size: 11pt, weight: "bold", it.body))

  // Cover
  page[
    #set par(first-line-indent: 0pt, spacing: 0pt)
    #v(116pt)
    #align(center)[
      #display(22pt, fill: red, title)
      #v(22pt)
      #text(10pt, subtitle)
      #v(18pt)
      #text(font: heading-sans, 18pt, weight: "bold", fill: red, "—————————")
      #v(29pt)
      #text(14pt, weight: "bold", organization)
      #v(15pt)
      #institution
      #v(22pt)
      #event
    ]
    #v(137pt)
    #pad(left: 72pt, grid(
      columns: (72pt, auto),
      row-gutter: 21.5pt,
      text(weight: "bold")[Date:], date.display("[month repr:short] [year]"),
      text(weight: "bold")[Status:], status,
    ))
  ]

  // Contents: no title, bold numbered sections, subsections indented 18pt,
  // tight dot leaders.
  {
    set par(first-line-indent: 0pt)
    show outline.entry: it => block(spacing: 8.5pt, link(it.element.location(), {
      set text(weight: if it.level == 1 { "bold" } else { "regular" })
      h((it.level - 1) * 18pt)
      if it.prefix() != none [#it.prefix() ]
      it.body()
      box(width: 1fr, repeat[.])
      it.page()
    }))
    v(3.3pt)
    outline(title: none, depth: 2)
  }

  body
}
