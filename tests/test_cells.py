from decimal import Decimal

from kb_core.build.cells import load_units, parse_cell

U = load_units("banking")


def test_parse_cell_parenthesised_negative():
    v = parse_cell("(1,234)", U)
    assert v.num == Decimal("-1234") and v.negative and not v.nil


def test_parse_cell_percent():
    v = parse_cell("0.9%", U)
    assert v.num == Decimal("0.9") and v.percent and v.unit == "pct"


def test_parse_cell_nil_symbols():
    for s in ["-", "—", "–", "n.m.", "NM", "n.a.", "", None]:
        v = parse_cell(s, U)
        assert v.nil and v.num is None, s


def test_parse_cell_zero_not_nil():
    v = parse_cell("0.0%", U)
    assert v.num == Decimal("0.0") and not v.nil and v.percent


def test_parse_cell_unit_suffix():
    v = parse_cell("S$1,443m", U)
    assert v.num == Decimal("1443") and v.scale == 6 and v.unit == "SGD"
    b = parse_cell("$3.24 billion", U)
    assert b.num == Decimal("3.24") and b.scale == 9


def test_parse_cell_text_is_not_a_number():
    v = parse_cell("Net interest income", U)
    assert v.num is None and not v.nil


def test_parse_cell_footnote_marker_and_bold():
    assert parse_cell("**2,411**", U).num == Decimal("2411")
    assert parse_cell("1,228 (1)", U).num == Decimal("1228")
