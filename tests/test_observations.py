from decimal import Decimal

from kb_core.build.cells import load_units
from kb_core.build.concepts import load_spec
from kb_core.build.observations import extract, observation_rules
from kb_core.build.tables import interpret

U = load_units("banking")
SPEC = load_spec()
RULES = observation_rules("annual_report")
DOC = {"doc_id": "x_ar_2025_en", "fiscal_year": 2025, "issuer_id": "x"}


def cell(r, c, text, header=False):
    return {"r": r, "c": c, "rs": 1, "cs": 1, "text": text, "bbox": [72.0 + 150 * c, 300 + 14 * r, 130.0 + 150 * c, 310 + 14 * r],
            "bbox_source": "text", "is_header": header}


def five_year(header_years=("2021", "2022(1)", "2023", "2024", "2025")):
    cells = [cell(0, k + 1, y, True) for k, y in enumerate(header_years)]
    cells += [cell(1, 0, "Selected Income Statement Items ($ million)")]
    cells += [cell(2, 0, "Total income")] + [cell(2, k + 1, v) for k, v in enumerate(["10,596", "11,286", "13,507", "14,473", "14,614"])]
    cells += [cell(3, 0, "Key Financial Ratios (%)")]
    cells += [cell(4, 0, "NPL ratio")] + [cell(4, k + 1, v) for k, v in enumerate(["1.5", "1.2", "0.9", "0.9", "0.9"])]
    return {"table_id": "x_ar_2025_en:t0004_01", "page_no": 4, "n_rows": 5, "n_cols": 6, "cells": cells,
            "continued_hint": None, "markdown": ""}


def run(table, page_text="Financial Highlights"):
    it = interpret(table, "", U)
    return extract(DOC, [{"table": table, "interpreted": it, "page_text": page_text, "page_label": "2"}], SPEC, U, RULES)


def test_years_from_header_columns():
    obs = run(five_year())
    income = {o["fiscal_year"]: o["value"] for o in obs if o["concept_id"] == "total_income"}
    assert income == {2021: Decimal("10596000000"), 2022: Decimal("11286000000"), 2023: Decimal("13507000000"),
                      2024: Decimal("14473000000"), 2025: Decimal("14614000000")}
    npl = {o["fiscal_year"]: (o["value"], o["unit"]) for o in obs if o["concept_id"] == "npl_ratio"}
    assert npl[2025] == (Decimal("0.9"), "pct")


def test_years_from_preceding_text_when_header_lacks_them():
    obs = run(five_year(("Col2", "Col3", "Col4", "Col5", "Col6")),
              page_text="Five-Year Summary 2025 2024 2023 2022 2021 Selected Income Statement Items ($ million)")
    income = {o["fiscal_year"] for o in obs if o["concept_id"] == "total_income"}
    assert income == {2021, 2022, 2023, 2024, 2025}
    first = next(o for o in obs if o["concept_id"] == "total_income" and o["raw_value"] == "10,596")
    assert first["fiscal_year"] == 2025          # the text gives 2025 first: columns follow the text order


def test_restated_footnote():
    obs = run(five_year(), page_text="(1) Figures for 2022 were restated. Selected Income Statement Items")
    restated = {o["fiscal_year"] for o in obs if o["restated_note"]}
    assert restated == {2022}
    assert not any(o["restated_note"] for o in run(five_year(), page_text="no note here"))


def test_non_target_table_gives_nothing():
    t = five_year()
    t["cells"][5]["text"] = "Other table"
    assert run(t) == []
