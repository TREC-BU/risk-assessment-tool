from conftest import event, make_sheet

from risktool.validate import validate


def run(config, **tabs):
    return validate(make_sheet(**tabs), config)


def has(messages, *fragments):
    return any(all(f in str(m) for f in fragments) for m in messages)


def test_clean_sheet_passes(config, base):
    r = run(config, events=[
        event(mits="M_001; M_002; M_003", p1=1, s1=4, p1j="redundant cable"),
        event("HE_002", st="ST_002", p0=2, s0=2),
    ], **base)
    assert r.errors == []
    he = r.data["events"][0]
    assert he["initial"] == {"p": 4, "s": 5, "score": 20, "band": "U"}
    assert he["residual"]["band"] == "A"
    assert he["mitigations"] == ["M_001", "M_002", "M_003"]
    assert he["hazard_id"] == "HZ_001"
    m2 = next(m for m in r.data["mitigations"] if m["mitigation_id"] == "M_002")
    assert m2["fat_ref"] == ["FAT_003", "FAT_039"]
    assert m2["events"] == ["HE_001"]
    assert r.data["tasks"][0]["person"] == "Rider"


def test_misspelled_situation_header_is_accepted(config, base):
    r = run(config, events=[event(p0=1, s0=1)], **base)
    assert r.data["situations"][0]["situation"] == "rider seated while suspended"


def test_comma_separated_mitigations(config, base):
    r = run(config, events=[event(mits="M_002, M_003", p1=1, s1=4, p1j="x")], **base)
    assert r.data["events"][0]["mitigations"] == ["M_002", "M_003"]


def test_prefilled_blank_rows_are_skipped(config, base):
    base["hazards"].append(["HZ_002", "", ""])
    base["mitigations"].append(["M_004", "Proposed", "", "", "", "", "", "", ""])
    r = run(config, events=[event(p0=1, s0=1), ["HE_002", "", "", "", "", "", "", "", "", "0"]],
            **base)
    assert r.errors == []
    assert [h["hazard_id"] for h in r.data["hazards"]] == ["HZ_001"]
    assert len(r.data["events"]) == 1
    assert len(r.data["mitigations"]) == 3
    assert not has(r.info, "M_004")


def test_blank_row_with_stray_scores_warns(config, base):
    stray = ["HE_002", "", "", "", "", "", "", "", "", "0", "", "2", "", "2", "", "4"]
    r = run(config, events=[event(p0=1, s0=1), stray], **base)
    assert has(r.info, "Harmful Events row 6 (HE_002)", "ignored", "p1")


def test_event_with_only_situation_is_ignored(config, base):
    r = run(config, events=[event(p0=1, s0=1), ["HE_002", "ST_001", "", "", "", "", "", "", "",
                                                 "0"]], **base)
    assert r.errors == []
    assert has(r.info, "HE_002", "ignored", "situation_id")


def test_errors_name_tab_and_row(config, base):
    r = run(config, events=[event(st="ST_404", mits="M_999", p0=1, s0=1)], **base)
    assert has(r.errors, "Harmful Events row 5 (HE_001)", "ST_404")
    assert has(r.errors, "Harmful Events row 5 (HE_001)", "M_999")


def test_situation_references(config, base):
    base["situations"].append(["ST_003", "TS_404", "HZ_404", "nowhere"])
    r = run(config, events=[event(p0=1, s0=1)], **base)
    assert has(r.errors, "Situations row 6 (ST_003)", "TS_404", "Tasks tab")
    assert has(r.errors, "Situations row 6 (ST_003)", "HZ_404", "Hazards tab")


def test_score_out_of_range(config, base):
    r = run(config, events=[event(p0=6)], **base)
    assert has(r.errors, "HE_001", "p0")


def test_duplicate_ids(config, base):
    r = run(config, events=[event(p0=1, s0=1), event(p0=1, s0=1)], **base)
    assert has(r.errors, "row 6", "duplicate event_id", "row 5")


def test_bad_reduces(config, base):
    base["mitigations"].append(["M_004", "Proposed", "Design", "Guard", "Q", "", "", "", ""])
    r = run(config, events=[event(p0=1, s0=1, mits="M_004")], **base)
    assert has(r.errors, "Mitigations row 7 (M_004)", "reduces")


def test_blank_reduces_warns(config, base):
    base["mitigations"].append(["M_004", "Proposed", "Design", "Guard", "", "", "", "", ""])
    r = run(config, events=[event(p0=1, s0=1, mits="M_004")], **base)
    assert r.errors == []
    assert has(r.warnings, "M_004", "reduces is blank")


def test_unknown_mitigation_type(config, base):
    base["mitigations"].append(["M_004", "Proposed", "Signage", "Sign", "P", "", "", "", ""])
    r = run(config, events=[event(p0=1, s0=1, mits="M_004")], **base)
    assert has(r.errors, "M_004", "Signage", "Administrative")


def test_unknown_design_ref_prefix(config, base):
    base["mitigations"].append(["M_004", "Proposed", "Design", "Guard", "P", "", "", "",
                                "XYZ_1 Guard"])
    r = run(config, events=[event(p0=1, s0=1, mits="M_004")], **base)
    assert has(r.errors, "M_004", "prefix 'XYZ'")


def test_introduces_hazard(config, base):
    base["mitigations"].append(["M_004", "Proposed", "Design", "Guard", "P", "HZ_001; HZ_404",
                                "", "", ""])
    r = run(config, events=[event(p0=1, s0=1, mits="M_004")], **base)
    assert has(r.errors, "M_004", "introduces_hazard 'HZ_404'")
    assert not has(r.errors, "'HZ_001'")


def test_unacceptable_needs_mitigation_and_residual_but_never_blocks(config, base):
    r = run(config, events=[event()], **base)
    assert r.errors == [] and r.data is not None
    assert has(r.warnings, "HE_001", "no mitigations")
    assert has(r.warnings, "HE_001", "p1/s1 are missing")


def test_severity_cannot_drop_with_administrative_only(config, base):
    r = run(config, events=[event(mits="M_001", p1=2, s1=4, s1j="x")], **base)
    assert has(r.warnings, "HE_001", "S drops 5 → 4")


def test_severity_drop_needs_mitigation_reducing_s(config, base):
    # M_002 is Safeguarding but only reduces P.
    r = run(config, events=[event(mits="M_002", p1=1, s1=4, p1j="x")], **base)
    assert has(r.warnings, "HE_001", "S drops")


def test_probability_drop_needs_mitigation_reducing_p(config, base):
    r = run(config, events=[event(mits="M_003", p1=1, s1=4, p1j="x")], **base)
    assert has(r.warnings, "HE_001", "P drops")


def test_residual_cannot_exceed_initial(config, base):
    r = run(config, events=[event(p0=1, s0=1, mits="M_002", p1=2, s1=1)], **base)
    assert has(r.warnings, "HE_001", "higher than initial")


def test_justifiable_residual_needs_justification(config, base):
    r = run(config, events=[event(mits="M_002; M_003", p1=2, s1=3)], **base)
    assert has(r.warnings, "HE_001", "Justifiable", "justification")
    r = run(config, events=[event(mits="M_002; M_003", p1=2, s1=3, p1j="one safeguard")],
            **base)
    assert r.warnings == []


def test_unacceptable_residual_warns(config, base):
    r = run(config, events=[event(mits="M_002", p1=3, s1=5, p1j="x")], **base)
    assert r.errors == []
    assert has(r.warnings, "HE_001", "residual risk is Unacceptable")


def test_unmitigated_unacceptable_warns_even_without_residual(config, base):
    r = run(config, events=[event(p0=3, s0=4)], **base)
    assert has(r.warnings, "residual risk is Unacceptable")


def test_p1_without_s1(config, base):
    r = run(config, events=[event(mits="M_002", p1=2)], **base)
    assert has(r.errors, "HE_001", "both p1 and s1")


def test_info(config, base):
    base["tasks"].append(["TS_003", "Trained Person", "Maintainer", "Non-Operation", "panel",
                          "Working on the panel"])
    base["hazards"].append(["HZ_002", "Electrical", "24V bus"])
    r = run(config, events=[event(p0=3, s0=2, mits="M_001", p1=2, s1=2)], **base)
    assert r.errors == [] and r.warnings == []
    assert has(r.info, "Hazards row 5 (HZ_002)", "no harmful events")
    assert has(r.info, "Tasks row 6 (TS_003)", "no hazardous situations")
    assert has(r.info, "Situations row 5 (ST_002)", "no harmful events")
    assert has(r.info, "HZ_001", "only against rider")
    assert has(r.info, "HE_001", "only by Administrative")
    assert has(r.info, "M_002", "not linked")


def test_missing_column(config, base):
    sheet = make_sheet(**base)
    sheet["Hazards"][2] = ["", "hazard_id", "category"]
    r = validate(sheet, config)
    assert has(r.errors, "Hazards", "missing column", "hazard")


def test_missing_header_row(config, base):
    sheet = make_sheet(**base)
    sheet["Harmful Events"] = [["", "nothing here"]]
    r = validate(sheet, config)
    assert has(r.errors, "Harmful Events", "event_id")


def test_unmitigated_justifiable_event_needs_justification(config, base):
    r = run(config, events=[event(p0=3, s0=2)], **base)
    assert has(r.warnings, "HE_001", "Justifiable", "justification")
    r = run(config, events=[event(p0=3, s0=2, p1j="accepted: padded headrest")], **base)
    assert not has(r.warnings, "justification")


def test_issues_carry_their_location(config, base):
    r = run(config, events=[event(mits="M_999", p0=1, s0=1)], **base)
    issue = next(e for e in r.errors if "M_999" in e.message)
    assert (issue.tab, issue.row, issue.ident) == ("Harmful Events", 5, "HE_001")
