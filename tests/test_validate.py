from conftest import make_sheet, risk

from risktool.validate import validate


def run(config, mode="final", **tabs):
    return validate(make_sheet(**tabs), config, mode)


def has(messages, *fragments):
    return any(all(f in m for f in fragments) for m in messages)


def test_clean_sheet_passes(config, base):
    r = run(config, risks=[
        risk(mits="M_001; M_002; M_003", p1=1, s1=4, p1j="redundant cable"),
        risk("RK_002", st="ST_002", p0=2, s0=2),
    ], **base)
    assert r.errors == []
    rk = r.data["risks"][0]
    assert rk["initial"] == {"p": 4, "s": 5, "score": 20, "band": "U"}
    assert rk["residual"]["band"] == "A"
    assert rk["mitigations"] == ["M_001", "M_002", "M_003"]
    m2 = next(m for m in r.data["mitigations"] if m["mitigation_id"] == "M_002")
    assert m2["fat_ref"] == ["FAT_003", "FAT_039"]
    assert m2["risks"] == ["RK_001"]


def test_misspelled_situation_header_is_accepted(config, base):
    r = run(config, risks=[risk("RK_001", p0=1, s0=1)], **base)
    assert r.data["situations"][0]["situation"] == "rider seated while suspended"


def test_prefilled_blank_rows_are_skipped(config, base):
    base["hazards"].append(["HZ_002", "", ""])
    r = run(config, risks=[risk(p0=1, s0=1), ["RK_002", "", "", "", "", "", "", "", "0"]], **base)
    assert r.errors == []
    assert [h["hazard_id"] for h in r.data["hazards"]] == ["HZ_001"]
    assert len(r.data["risks"]) == 1


def test_blank_row_with_stray_scores_warns(config, base):
    stray = ["RK_002", "", "", "", "", "", "", "", "0", "", "2", "", "2", "", "4"]
    r = run(config, risks=[risk(p0=1, s0=1), stray], **base)
    assert has(r.warnings, "Risks row 6 (RK_002)", "ignored", "p1")


def test_errors_name_tab_and_row(config, base):
    r = run(config, risks=[risk(hz="HZ_404", st="ST_404", mits="M_999", p0=1, s0=1)], **base)
    assert has(r.errors, "Risks row 5 (RK_001)", "HZ_404")
    assert has(r.errors, "Risks row 5 (RK_001)", "ST_404")
    assert has(r.errors, "Risks row 5 (RK_001)", "M_999")


def test_score_out_of_range(config, base):
    r = run(config, risks=[risk(p0=6)], **base)
    assert has(r.errors, "RK_001", "p0")


def test_duplicate_ids(config, base):
    r = run(config, risks=[risk(p0=1, s0=1), risk(p0=1, s0=1)], **base)
    assert has(r.errors, "row 6", "duplicate risk_id", "row 5")


def test_bad_reduces_and_type(config, base):
    base["mitigations"].append(["M_004", "Signage", "Sign", "Q", "", "", ""])
    r = run(config, risks=[risk(p0=1, s0=1, mits="M_004")], **base)
    assert has(r.errors, "Mitigations row 7 (M_004)", "reduces")


def test_unknown_mitigation_type(config, base):
    base["mitigations"].append(["M_004", "Signage", "Sign", "P", "", "", ""])
    r = run(config, risks=[risk(p0=1, s0=1, mits="M_004")], **base)
    assert has(r.errors, "M_004", "Signage", "Administrative")


def test_unknown_design_ref_prefix(config, base):
    base["mitigations"].append(["M_004", "Design", "Guard", "P", "", "", "XYZ_1 Guard"])
    r = run(config, risks=[risk(p0=1, s0=1, mits="M_004")], **base)
    assert has(r.errors, "M_004", "prefix 'XYZ'")


def test_unacceptable_needs_mitigation_and_residual(config, base):
    r = run(config, risks=[risk()], **base)
    assert has(r.errors, "RK_001", "no mitigations")
    assert has(r.errors, "RK_001", "p1/s1 are missing")


def test_pdr_downgrades_residual_rules(config, base):
    r = run(config, mode="pdr", risks=[risk()], **base)
    assert r.errors == []
    assert has(r.warnings, "RK_001", "no mitigations")


def test_severity_cannot_drop_with_administrative_only(config, base):
    r = run(config, risks=[risk(mits="M_001", p1=2, s1=4, s1j="x")], **base)
    assert has(r.errors, "RK_001", "S drops 5 → 4")


def test_severity_drop_needs_mitigation_reducing_s(config, base):
    # M_002 is Safeguarding but only reduces P.
    r = run(config, risks=[risk(mits="M_002", p1=1, s1=4, p1j="x")], **base)
    assert has(r.errors, "RK_001", "S drops")


def test_probability_drop_needs_mitigation_reducing_p(config, base):
    r = run(config, risks=[risk(mits="M_003", p1=1, s1=4, p1j="x")], **base)
    assert has(r.errors, "RK_001", "P drops")


def test_residual_cannot_exceed_initial(config, base):
    r = run(config, risks=[risk(p0=1, s0=1, mits="M_002", p1=2, s1=1)], **base)
    assert has(r.errors, "RK_001", "higher than initial")


def test_justifiable_residual_needs_justification(config, base):
    r = run(config, risks=[risk(mits="M_002; M_003", p1=2, s1=3)], **base)
    assert has(r.errors, "RK_001", "Justifiable", "justification")
    r = run(config, risks=[risk(mits="M_002; M_003", p1=2, s1=3, p1j="one safeguard")], **base)
    assert r.errors == []


def test_final_fails_on_unacceptable_residual(config, base):
    r = run(config, risks=[risk(mits="M_002", p1=3, s1=5, p1j="x")], **base)
    assert has(r.errors, "RK_001", "residual risk is Unacceptable")


def test_final_fails_on_unmitigated_unacceptable_even_without_residual(config, base):
    r = run(config, risks=[risk(p0=3, s0=4)], **base)
    assert has(r.errors, "residual risk is Unacceptable")


def test_p1_without_s1(config, base):
    r = run(config, risks=[risk(mits="M_002", p1=2)], **base)
    assert has(r.errors, "RK_001", "both p1 and s1")


def test_warnings(config, base):
    base["hazards"].append(["HZ_002", "Electrical", "24V bus"])
    base["situations"].append(["ST_003", "Maintainer", "Maintenance", "0", "working on panel"])
    r = run(config, risks=[risk(p0=3, s0=2, mits="M_001", p1=2, s1=2)], **base)
    assert r.errors == []
    assert has(r.warnings, "Hazards row 5 (HZ_002)", "no risks")
    assert has(r.warnings, "Situations row 6 (ST_003)", "no risks")
    assert has(r.warnings, "HZ_001", "only against rider")
    assert has(r.warnings, "RK_001", "only by Administrative")
    assert has(r.warnings, "M_002", "not linked")


def test_missing_column(config, base):
    sheet = make_sheet(**base)
    sheet["Hazards"][2] = ["", "hazard_id", "category"]
    r = validate(sheet, config, "final")
    assert has(r.errors, "Hazards", "missing column", "hazard")


def test_missing_header_row(config, base):
    sheet = make_sheet(**base)
    sheet["Risks"] = [["", "nothing here"]]
    r = validate(sheet, config, "final")
    assert has(r.errors, "Risks", "risk_id")


def test_unmitigated_justifiable_risk_needs_justification_in_final(config, base):
    r = run(config, risks=[risk(p0=3, s0=2)], **base)
    assert has(r.errors, "RK_001", "Justifiable", "justification")
    r = run(config, risks=[risk(p0=3, s0=2, p1j="accepted: padded headrest")], **base)
    assert r.errors == []
    r = run(config, mode="pdr", risks=[risk(p0=3, s0=2)], **base)
    assert not has(r.warnings, "justification")
