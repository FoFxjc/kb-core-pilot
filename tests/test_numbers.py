import json

from kb_core.serve.numbers import check_numbers, evidence_from_tool_results

SERIES = {"tool": "get_metric_series", "trace_id": "tr_1", "scope": {"hit_counts": {"total": 999}},
          "results": [{"fiscal_year": 2025, "value": 7587, "display": "7,587", "unit": "S$ million", "rank": 1,
                       "yoy_pct": -3.1, "ratio": 0.1234, "values": [33.3, 44.4]}]}
SEARCH = {"tool": "search", "results": [{"page_no": 118, "score": 12.3456, "ms": 47, "page_range": [33, 34],
                                         "snippet": "Net interest margin was 2.05% in 2025 (2.20% in 2024). "
                                                    "NPL ratio 0.9%."}]}
TOOL_TEXTS = [json.dumps(SERIES, separators=(",", ":")) + "\n\n(7 tool calls left in this session)",
              json.dumps(SEARCH, separators=(",", ":")), "plain outline text: Note 33 Loans 4,321"]
EVIDENCE = evidence_from_tool_results(TOOL_TEXTS)


def unverified(answer: str) -> list[str]:
    return [x["text"] for x in check_numbers(answer, EVIDENCE)["unverified"]]


def test_exact_and_separator():
    assert unverified("Net profit was S$7,587 million.") == []
    assert unverified("Net profit was 7587 million.") == []
    assert unverified("Loans of 4,321 (from text that is not JSON).") == []


def test_rounding_and_unit_scales():
    assert unverified("Net profit was S$7.6 billion.") == []          # million -> billion
    assert unverified("净利润约为76亿新元。") == []                        # million -> yi (100 million)
    assert unverified("The ratio was 12.3%.") == []                     # 0.1234 -> percent, rounded


def test_fabricated_number_is_flagged():
    assert unverified("Net interest margin rose to 2.31% in 2025.") == ["2.31"]
    assert unverified("Net profit was S$8,104 million.") == ["8,104"]


def test_bookkeeping_numbers_are_not_evidence():
    # page_no 118, score 12.3456, ms 47, page_range 33-34 and scope counts must not verify anything
    assert unverified("NPL ratio rose to 1.2%.") == ["1.2"]
    assert unverified("Profit was S$12.35 billion.") == ["12.35"]
    assert unverified("ROE was 47%.") == ["47"]
    assert unverified("Total of 999 hits; 34 items.") == ["999", "34"]


def test_scaled_match_needs_two_significant_digits():
    # 2.05 x 0.01 rounds to 0.02, but a one-digit number is too easy to hit by scaling
    assert unverified("It moved 0.02.") == ["0.02"]


def test_sign():
    assert unverified("Year-on-year it fell 3.1%.") == []              # unsigned: either sign
    assert unverified("Change: -3.1%.") == []                           # explicit minus matches a negative value
    assert unverified("NPL ratio change: -0.9%.") == ["-0.9"]           # but not a positive one


def test_json_arrays_do_not_merge():
    ev = evidence_from_tool_results(['{"results":[{"values":[118,121]}]}'])
    assert check_numbers("Up 121%, from 118.", ev)["unverified"] == []
    assert check_numbers("Total 118,121.", ev)["unverified"][0]["text"] == "118,121"


def test_years_pages_small_integers_and_identifiers_are_skipped():
    r = check_numbers("In 2025 (ocbc-group_ar_2025_en, physical page 105, printed page 103) see 3 tables; FY2024.",
                      EVIDENCE)
    assert r["checked"] == 0 and r["unverified"] == []
    assert check_numbers("见第 105 页", EVIDENCE)["checked"] == 0


def test_result_shape():
    r = check_numbers("Margin 2.05%, made-up 41.7%.", EVIDENCE)
    assert r["checked"] == 2 and [x["text"] for x in r["verified"]] == ["2.05"]
    assert r["unverified"][0]["text"] == "41.7" and "41.7" in r["unverified"][0]["context"]
