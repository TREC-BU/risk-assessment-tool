// Risk assessment method definitions — the single source of truth.
//
// Python reads this back with
//   typst eval 'query(<risk-config>).first().value' --in risk-config.typ
// so nothing here is duplicated in code. It lives outside the main document
// because the query runs before build/risk.json exists.
//
// PROVISIONAL: scales, matrix and bands follow the "Definitions" tab of the
// REC 2027 Risk Assessment sheet. If the REC ASTM Adaptation Document
// prescribes its own scales or matrix, change them here — no code changes.

#let config = (
  // Cover page and footer. `status` is chosen by build mode.
  document: (
    title: "RISK ASSESSMENT",
    subtitle: "Technical Documentation",
    organization: "Terrier Ride Engineering Club",
    institution: "Boston University",
    event: "Ride Engineering Competition",
    status: (pdr: "Preliminary Design Review", final: "Final"),
  ),

  // 1–5 scales. Keys are the level as a string so the table reads top-down.
  severity: (
    "1": (name: "Negligible", description: "No injury",
      example: "An abrupt stop within ASTM F2291 limits startles a rider; operator touches 5V sensor wire."),
    "2": (name: "Minor", description: "First aid",
      example: "Rider's finger is pinched by a closing restraint during loading; operator touches a braking resistor after a cycle and gets a small first-degree burn."),
    "3": (name: "Major", description: "Medical treatment beyond first aid",
      example: "Rider strains their neck in a sudden ride stop and needs a clinician; a 24V supply is shorted by a tool and causes a severe burn."),
    "4": (name: "Significant", description: "Hospitalization, amputation, irreversible injury",
      example: "A bystander is hit by an unsecured phone from a rider's pocket, fracturing a rib."),
    "5": (name: "Severe", description: "Severe, permanent, or fatal injury",
      example: "Drop tower belt fails at the top, causing irreversible spinal injuries to riders; operator is electrocuted by an unexpectedly energized ride platform."),
  ),
  probability: (
    "1": (name: "Improbable", frequency: "< 1 in 100,000 cycles",
      basis: "Requires two or more independent failures"),
    "2": (name: "Rare", frequency: "1 in 10,000–100,000 cycles",
      basis: "A failure that one independent safeguard should catch"),
    "3": (name: "Occasional", frequency: "1 in 1,000–10,000 cycles",
      basis: "A human error in a defined procedure, or a single failure of a component with design margin"),
    "4": (name: "Probable", frequency: "1 in 100–1,000 cycles",
      basis: "A single human error in a task, or a single failure of a wear part"),
    "5": (name: "Frequent", frequency: "> 1 in 100 cycles",
      basis: "Expected to occur during normal operation"),
  ),

  // Acceptability bands, lowest to highest. `label` is printed in every
  // matrix cell so the PDF still reads in grayscale. A residual landing in a
  // band with `justify: true` needs a written justification.
  bands: (
    (code: "A", name: "Acceptable", label: "A", color: "#b7e1cd", justify: false,
      meaning: "No further mitigation required"),
    (code: "J", name: "Justifiable", label: "J", color: "#ffd966", justify: true,
      meaning: "Mitigation suggested; a residual risk here needs a written justification"),
    (code: "U", name: "Unacceptable", label: "U", color: "#e06666", justify: false,
      meaning: "Requires mitigation"),
  ),

  // 5 × 5 acceptability matrix as a lookup table, not a score threshold, so
  // individual cells can be overridden. Keyed by severity; each row lists
  // probability 1 → 5.
  matrix: (
    "5": ("J", "U", "U", "U", "U"),
    "4": ("A", "J", "U", "U", "U"),
    "3": ("A", "J", "J", "U", "U"),
    "2": ("A", "A", "J", "J", "U"),
    "1": ("A", "A", "A", "A", "J"),
  ),

  // Highest band a residual risk may sit in for a Final build.
  acceptable-max: "J",

  // Mitigation hierarchy, most to least effective. Only types with
  // `lowers-severity: true` may justify a drop in S.
  mitigation-types: (
    (name: "Elimination", lowers-severity: true),
    (name: "Design", lowers-severity: true),
    (name: "Safeguarding", lowers-severity: true),
    (name: "Administrative", lowers-severity: false),
  ),

  // Prefixes allowed in design_ref (the part before the first "_") and the
  // document each one points to.
  document-prefixes: (
    MSD: "Mechanical & Structural Design",
  ),

  // Text for the Method section.
  scope: [
    This assessment covers the REC 2027 ride through design, fabrication,
    factory acceptance testing, operation, maintenance and evacuation. It
    considers riders, operators, maintainers and bystanders, including
    reasonably foreseeable misuse.
  ],
  limits: [
    Probability is estimated per ride cycle from engineering judgment and
    component data, not from field statistics. Risks are assessed one
    hazard and situation pair at a time; combined failures are only
    considered where a risk states them explicitly.
  ],
)

#metadata(config) <risk-config>
