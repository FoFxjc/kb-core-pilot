"""Concept layer (port of kb tests/test_concepts.py): concepts.yaml validation and node tagging (no database).
Tables are given as interpreted row labels (kb read Markdown first columns)."""

import pytest
import yaml

from kb_core.build import concepts
from kb_core.retrieval import aliases

SPEC = {
    "version": 9,
    "concepts": [
        {"id": "capital_adequacy", "name": {"en": "Capital adequacy ratio", "zh": "资本充足率"},
         "value_type": "percent", "aggregation": "ratio", "period_kind": "instant", "definition": "broader concept of the three capital adequacy ratios",
         "variants": []},
        {"id": "cet1_ratio", "name": {"en": "CET1 CAR", "zh": "普通股权一级资本充足率"}, "value_type": "percent",
         "aggregation": "ratio", "period_kind": "instant", "definition": "d", "variants": ["CET1 CAR", "普通股权一级资本充足率"]},
        {"id": "tier1_car", "name": {"en": "Tier 1 CAR", "zh": "一级资本充足率"}, "value_type": "percent",
         "aggregation": "ratio", "period_kind": "instant", "definition": "d", "variants": ["Tier 1 CAR"]},
        {"id": "payout_ratio", "name": {"en": "Payout ratio", "zh": "派息率"}, "value_type": "percent",
         "aggregation": "ratio", "period_kind": "duration", "definition": "d", "variants": ["payout ratio"]},
        {"id": "total_payout_ratio", "name": {"en": "Total payout ratio", "zh": "总派息率"}, "value_type": "percent",
         "aggregation": "ratio", "period_kind": "duration", "definition": "d", "variants": ["total payout ratio"]},
        {"id": "npl_ratio", "name": {"en": "NPL ratio", "zh": "不良贷款率"}, "value_type": "percent",
         "aggregation": "stock", "period_kind": "instant", "definition": "d (a stock concept in this test, for F3)",
         "variants": ["NPL ratio", "不良贷款率"], "row_labels": ["NPL ratio (%)"]},
    ],
    "edges": [
        {"src": "cet1_ratio", "relation": "broader", "dst": "capital_adequacy"},
        {"src": "tier1_car", "relation": "broader", "dst": "capital_adequacy"},
        {"src": "total_payout_ratio", "relation": "variant_of", "dst": "payout_ratio"},
    ],
}


def write(tmp_path, spec, heldout=()):  # noqa: D103
    c = tmp_path / "concepts.yaml"
    c.write_text(yaml.safe_dump(spec, allow_unicode=True))
    h = tmp_path / "heldout_terms.yaml"
    h.write_text(yaml.safe_dump({"terms": [{"term": t, "lang": "en"} for t in heldout]}, allow_unicode=True))
    return c, h


def test_valid_spec_loads(tmp_path):
    c, h = write(tmp_path, SPEC, heldout=["bad loans ratio"])
    spec = concepts.load_spec(c, h)
    assert spec["version"] == 9 and len(spec["concepts"]) == 6


def test_heldout_overlap_rejected(tmp_path):
    c, h = write(tmp_path, SPEC, heldout=["npl ratio"])
    with pytest.raises(concepts.ConceptSpecError, match="NPL ratio"):
        concepts.load_spec(c, h)


def test_heldout_recognised_inside_longer_phrase_rejected(tmp_path):
    """A held-out wording that contains a concept table wording (the query would be recognised) also counts as overlap."""
    c, h = write(tmp_path, SPEC, heldout=["group NPL ratio trend"])
    with pytest.raises(concepts.ConceptSpecError, match="group NPL ratio trend"):
        concepts.load_spec(c, h)


def test_row_label_counts_for_heldout_overlap(tmp_path):
    c, h = write(tmp_path, SPEC, heldout=["NPL ratio (%)"])
    with pytest.raises(concepts.ConceptSpecError):
        concepts.load_spec(c, h)


def test_variant_in_two_concepts_rejected(tmp_path):
    spec = yaml.safe_load(yaml.safe_dump(SPEC))
    spec["concepts"][2]["variants"].append("cet1  car")      # same as a cet1_ratio wording after normalisation
    c, h = write(tmp_path, spec)
    with pytest.raises(concepts.ConceptSpecError, match="cet1"):
        concepts.load_spec(c, h)


def test_edge_unknown_rejected(tmp_path):
    spec = yaml.safe_load(yaml.safe_dump(SPEC))
    spec["edges"].append({"src": "npl_ratio", "relation": "broader", "dst": "asset_quality"})
    c, h = write(tmp_path, spec)
    with pytest.raises(concepts.ConceptSpecError, match="asset_quality"):
        concepts.load_spec(c, h)


def test_bad_enum_rejected(tmp_path):
    spec = yaml.safe_load(yaml.safe_dump(SPEC))
    spec["concepts"][1]["value_type"] = "money"
    c, h = write(tmp_path, spec)
    with pytest.raises(concepts.ConceptSpecError, match="value_type"):
        concepts.load_spec(c, h)


def test_alias_rows_carry_source(tmp_path):
    c, h = write(tmp_path, SPEC)
    rows = concepts.alias_rows(concepts.load_spec(c, h))
    by = {r["alias"]: r for r in rows}
    assert by["NPL ratio (%)"]["source"] == "row_label" and by["NPL ratio"]["source"] == "manual"
    assert by["不良贷款率"]["lang"] == "zh" and by["NPL ratio"]["alias_norm"] == "nplratio"


@pytest.fixture
def concept_file(tmp_path, monkeypatch):
    write(tmp_path, SPEC)
    from kb_core.build import tokenize
    from kb_core.domains import dictionary

    monkeypatch.setattr(aliases, "domain_dir", lambda name: tmp_path)
    monkeypatch.setattr(tokenize, "dictionary", lambda name: dictionary("banking"))
    aliases.clear_caches()
    yield
    aliases.clear_caches()


def test_narrower_broader_only(concept_file):
    assert aliases.narrower("capital_adequacy", "t") == ["cet1_ratio", "tier1_car"]
    assert aliases.narrower("payout_ratio", "t") == []            # no expansion via variant_of
    assert aliases.narrower("cet1_ratio", "t") == []


def test_row_labels_recognised_not_expanded(concept_file):
    terms, sources, units = aliases.expand("NPL ratio (%) 2025", "t")
    assert units[0]["id"] == "npl_ratio"
    assert not any(s["variant"] == "NPL ratio (%)" for s in sources if s["source"] == "alias")


def test_real_concept_table_passes_validation():
    """The repository's domain pack concepts.yaml and eval/heldout_terms.yaml must load (held-out wordings stay out of the concept table)."""
    spec = concepts.load_spec()
    assert len(spec["concepts"]) >= 26


# ---------- Node tagging (p2-design §3.3) ----------

def _node(nid, title, start, end, depth=1, parent=None):
    return {"node_id": f"d:regions:{nid}", "title": title, "start_page": start, "end_page": end, "depth": depth,
            "parent_id": parent and f"d:regions:{parent}", "is_primary": True}


def _tag(nodes, pages=None, tables=None, overrides=None):
    spec = concepts.load_spec(*write_specs())
    rows = concepts.tag_nodes(nodes, pages or {}, tables or [], spec, overrides or {})
    return {(r["node_id"].split(":")[-1], r["concept_id"]): r for r in rows}


_SPEC_DIR = []


def write_specs():
    return _SPEC_DIR[0]


@pytest.fixture(autouse=True)
def _spec_files(tmp_path):
    spec = yaml.safe_load(yaml.safe_dump(SPEC))
    spec["concepts"].append({"id": "net_profit", "name": {"en": "Net profit", "zh": "净利润"}, "value_type": "amount",
                             "aggregation": "flow", "period_kind": "duration", "definition": "d",
                             "variants": ["net profit", "净利润"], "exclude": ["净利润率"]})
    spec["concepts"][5]["query_only"] = ["bad debt ratio"]
    _SPEC_DIR[:] = [write(tmp_path, spec)]
    yield


def test_rule_title_hit():
    got = _tag([_node("0001", "Non-performing loans: NPL ratio", 10, 11)])
    r = got[("0001", "npl_ratio")]
    assert r["method"] == "rule_title" and r["variant"] == "NPL ratio" and r["confidence"] == 0.9


def test_exclude_blocks_title():
    assert ("0001", "net_profit") not in _tag([_node("0001", "净利润率分析", 10, 11)])


def test_rule_row_label_from_table_rows():
    table = {"node_id": "d:regions:0002", "labels": ['**NPL ratio (%)**(1)']}
    r = _tag([_node("0002", "Financial Highlights", 4, 5)], tables=[table])[("0002", "npl_ratio")]
    assert r["method"] == "rule_row_label" and r["variant"] == "NPL ratio (%)"


def test_row_label_rejects_numeric_and_generic():
    table = {"node_id": "d:regions:0002", "labels": ["2025", "Total", "NPL ratio rose to 0.9% in the year"]}
    assert _tag([_node("0002", "Highlights", 4, 5)], tables=[table]) == {}


def test_rule_dict_needs_two_and_number():
    """D39: the rule_dict minimum count lowered from 3 to 2 (confirmed by the user 2026-10-19; no per-question regression on the same Doris state, and x02 2024 hits because of it)."""
    node = _node("0003", "Asset quality", 20, 20)
    two = {20: "NPL ratio was 0.9%. The NPL ratio stayed low."}
    one = {20: "NPL ratio was 0.9%."}
    no_num = {20: "NPL ratio. The NPL ratio stayed low."}
    r = _tag([node], pages=two)[("0003", "npl_ratio")]
    assert r["method"] == "rule_dict" and r["confidence"] == 0.6
    assert _tag([node], pages=one) == {} and _tag([node], pages=no_num) == {}


def test_rule_dict_uses_only_own_pages():
    parent = _node("0010", "Notes", 20, 30)
    child = _node("0011", "Asset quality note", 25, 30, depth=2, parent="0010")
    pages = {25: "NPL ratio 0.9%. NPL ratio."}
    got = _tag([parent, child], pages=pages)
    assert ("0011", "npl_ratio") in got and ("0010", "npl_ratio") not in got


def test_title_beats_dict_for_same_pair():
    pages = {10: "NPL ratio 0.9%. NPL ratio. NPL ratio."}
    assert _tag([_node("0001", "NPL ratio", 10, 10)], pages=pages)[("0001", "npl_ratio")]["method"] == "rule_title"


def test_manual_add_and_remove_win():
    overrides = {"add": [{"node_id": "d:regions:0005", "concept_id": "cet1_ratio", "reason": "r"}],
                 "remove": [{"node_id": "d:regions:0001", "concept_id": "npl_ratio", "reason": "r"}]}
    got = _tag([_node("0001", "NPL ratio", 10, 10), _node("0005", "Capital", 12, 13)], overrides=overrides)
    assert ("0001", "npl_ratio") not in got
    assert got[("0005", "cet1_ratio")]["method"] == "manual" and got[("0005", "cet1_ratio")]["confidence"] == 1.0


def test_concept_tok_fields():
    rows = [{"node_id": "n1", "concept_id": "npl_ratio"}, {"node_id": "n1", "concept_id": "cet1_ratio"}]
    assert concepts.node_fields(rows) == {"n1": {"concept_tok": "cet1_ratio npl_ratio", "concept_ids": ["cet1_ratio", "npl_ratio"]}}


def test_longest_spelling_wins_across_concepts():
    """"Total payout ratio" is tagged only total_payout_ratio, not payout_ratio as well (consistent with longest match on the query side)."""
    got = _tag([_node("0007", "Total payout ratio", 30, 30)],
               pages={30: "total payout ratio 60%. total payout ratio. total payout ratio."})
    assert ("0007", "total_payout_ratio") in got and ("0007", "payout_ratio") not in got


def test_query_only_not_used_for_tagging():
    assert _tag([_node("0008", "Bad debt ratio", 30, 30)]) == {}    # query_only of npl_ratio


def test_nested_spellings_of_one_concept_count_once():
    spec = yaml.safe_load(yaml.safe_dump(SPEC))
    spec["concepts"][5]["variants"] = ["NPL ratio", "Group NPL ratio"]
    rows = concepts.tag_nodes([_node("0009", "Asset quality", 40, 40)],
                              {40: "Group NPL ratio 0.9%."}, [], spec, {})
    assert rows == []          # one "Group NPL ratio" is not counted twice because of the "NPL ratio" inside it


# ---------- Tagging rule fixes (after the first spot-check round, D39) ----------

def test_rule_dict_skips_pages_shared_with_siblings():
    """F1: pages shared with sibling nodes do not count as the node's own body text (accounting policies 2.16-2.19 are on one page)."""
    a = _node("0020", "2.17 Income tax expense", 151, 152, depth=2, parent="0019")
    b = _node("0021", "2.18 Earnings per share", 152, 152, depth=2, parent="0019")
    pages = {152: "NPL ratio 0.9%. NPL ratio."}
    got = _tag([a, b], pages=pages)
    assert ("0020", "npl_ratio") not in got and ("0021", "npl_ratio") not in got


def test_other_entity_sections_not_tagged_by_rows_or_text():
    """F2: row labels and body text in financial information of subsidiaries / associates / structured entities are not tagged (the title itself can still be)."""
    parent = _node("0030", "33. Investments in subsidiaries", 200, 202)
    child = _node("0031", "33.2 Non-controlling interests", 201, 201, depth=2, parent="0030")
    table = {"node_id": "d:regions:0031", "labels": ['NPL ratio']}
    assert _tag([parent, child], pages={201: "NPL ratio 0.9%. NPL ratio."}, tables=[table]) == {}


def test_stock_rows_skipped_in_flow_breakdown():
    """F3: in nodes titled with a flow concept (净利润), rows of stock concepts (npl_ratio is set to stock in the test SPEC) are not tagged; e.g. the "客户贷款" row in the net interest income note is interest, not a balance."""
    spec_rows = {"node_id": "d:regions:0040", "labels": ['NPL ratio', 'Net profit']}
    got = _tag([_node("0040", "Net profit", 300, 300)], tables=[spec_rows])
    assert ("0040", "net_profit") in got and ("0040", "npl_ratio") not in got


def test_stock_rows_skipped_in_cash_flow_statement():
    table = {"node_id": "d:regions:0041", "labels": ['NPL ratio', 'Net profit']}
    got = _tag([_node("0041", "Consolidated Cash Flow Statement", 131, 131)], tables=[table])
    assert ("0041", "net_profit") in got and ("0041", "npl_ratio") not in got


def test_rule_dict_skipped_in_audit_and_policy_sections():
    """F4: body text in the auditor's report and accounting policies / critical accounting estimates is not tagged by rule_dict."""
    for title in ("Independent Auditor's Report", "2.21 Critical Accounting Estimates and Judgements", "重要会计政策摘要"):
        assert _tag([_node("0050", title, 60, 60)], pages={60: "NPL ratio 0.9%. NPL ratio."}) == {}, title


def test_non_headline_notes_not_tagged_by_rows_or_text():
    """F6: notes such as assets pledged, fair value hierarchy, offsetting, related party transactions and allowances for financial assets do not report the group's metric and are not tagged by row label or body text;
    "未合并结构实体" (unconsolidated structured entities) is another entity too."""
    table = lambda nid: {"node_id": f"d:regions:{nid}", "labels": ['NPL ratio']}
    for nid, title in (("0060", "45.1 Assets Pledged"), ("0061", "40.3 公允价值层级"), ("0062", "41. 对销金融资产与金融负债"),
                       ("0063", "46.1 主要关联人士交易"), ("0064", "30. Allowances for Financial Assets"), ("0065", "44. 未合并结构实体")):
        assert _tag([_node(nid, title, 70, 70)], pages={70: "NPL ratio 0.9%. NPL ratio."}, tables=[table(nid)]) == {}, title


def test_shared_page_split_at_next_title():
    """F1': a shared page is split at the next node's title position: text before the title belongs to the previous node, text after it to the next node."""
    a = _node("0070", "Key Financial Ratios (%)", 98, 100, depth=3, parent="0069")
    b = _node("0071", "Allowances and Asset Quality", 100, 101, depth=3, parent="0069")
    pages = {99: "NPL ratio was 0.9% for the year.", 100: "NPL ratio stayed at 0.9%. Allowances and Asset Quality Total allowances rose."}
    got = _tag([a, b], pages=pages)
    assert ("0070", "npl_ratio") in got and ("0071", "npl_ratio") not in got


def test_shared_page_split_keeps_policy_sections_apart():
    a = _node("0072", "2.17 Income Tax Expense", 151, 152, depth=2, parent="0019")
    b = _node("0073", "2.18 Earnings Per Share", 152, 152, depth=2, parent="0019")
    pages = {152: "Tax is recognised. 2.18 Earnings Per Share NPL ratio 0.9%. NPL ratio."}
    got = _tag([a, b], pages=pages)
    assert ("0073", "npl_ratio") in got and ("0072", "npl_ratio") not in got




def test_no_title_tags_inside_accounting_policy_sections():
    parent = _node("0080", "2. Material Accounting Policy Information", 130, 160)
    child = _node("0081", "2.17 Net profit recognition", 151, 151, depth=2, parent="0080")
    assert ("0081", "net_profit") not in _tag([parent, child])
    assert ("0090", "net_profit") in _tag([_node("0090", "Net profit", 10, 10)])


def test_rule_dict_ignores_mentions_in_excluded_contexts():
    """Passing-mention classes from the step-2 tag eval: regulatory minimums, sensitivity estimates, insurance-fund
    liabilities and a metric named only as a dividend base do not count as rule_dict hits."""
    node = _node("0095", "Share Buyback", 36, 36)
    minimums = {36: "The MAS minimum requirements are a CET1 CAR of 6.5%, and CET1 CAR including buffers of 9.0%."}
    sensitivity = {36: "Net profit would fall by 1,896 under the simulated scenario. Net profit sensitivity is monitored."}
    assert _tag([node], pages=minimums) == {}
    assert _tag([node], pages=sensitivity) == {}
    real = {36: "The Group CET1 CAR was 17.1%. The CET1 CAR stayed strong."}
    assert ("0095", "cet1_ratio") in _tag([node], pages=real)


def test_excluded_context_stops_at_the_sentence_boundary():
    """An excluding phrase in the neighbouring sentence does not suppress a real mention (review of step 2: 2024 en
    MD&A Overview, 2025 zh CFO review)."""
    node = _node("0096", "Overview", 99, 99)
    text = {99: "The MAS minimum requirement is unchanged. Net profit rose to a new high of $7.59 billion; "
                "net profit grew 8% from a year ago."}
    assert ("0096", "net_profit") in _tag([node], pages=text)
    zh = {99: "全球最低税率已经实施。净利润增长8%至75亿元，净利润创新高。"}
    assert ("0096", "net_profit") in _tag([node], pages=zh)
