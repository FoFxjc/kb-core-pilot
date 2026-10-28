"""kb_core.access.labels: the label overlay (D1), document and block labels, labels only go up (T3.1, T3.2)."""

import pytest

from kb_core.access.labels import LabelError, block_label, doc_label, load_overlay

OVERLAY = {
    "version": 1, "simulated": True,
    "default": {"classification": "public", "domains": [], "owner": "unassigned"},
    "documents": [
        {"match": "acme_ar_2025_*", "label": {"classification": "internal", "domains": ["finance"],
                                              "owner": "group-finance", "embargo_until": "2026-11-15T00:00:00+08:00"}},
        {"match": "acme_ar_2024_en", "label": {"classification": "public", "owner": "ir"},
         "lower": True, "reason": "published report, declassified"},
    ],
    "blocks": [
        {"doc": "acme_ar_2025_en", "title": "^Management Discussion and Analysis$",
         "label": {"classification": "confidential", "domains": ["finance"]}},
        {"doc": "acme_ar_2025_en", "pages": [40, 42], "label": {"classification": "restricted"}},
    ],
}


def test_overlay_validates_labels_and_patterns():
    assert load_overlay(OVERLAY)["simulated"] is True
    bad = {**OVERLAY, "blocks": [{"doc": "x", "title": "(", "label": {"classification": "public"}}]}
    with pytest.raises(LabelError):
        load_overlay(bad)
    with pytest.raises(LabelError):
        load_overlay({**OVERLAY, "default": {"classification": "secret", "owner": "x"}})


def test_first_matching_document_rule_wins_and_carries_its_source():
    label = doc_label(load_overlay(OVERLAY), "acme_ar_2025_en")
    assert label["classification"] == "internal" and label["domains"] == ["finance"]
    assert label["embargo_until"] == "2026-11-15T00:00:00+08:00" and label["label_source"] == "overlay"


def test_an_unmatched_document_gets_the_default():
    label = doc_label(load_overlay(OVERLAY), "other_doc")
    assert label == {"classification": "public", "domains": [], "owner": "unassigned", "embargo_until": None,
                     "label_source": "default"}


def test_a_document_without_classification_or_owner_is_rejected():
    no_default = {k: v for k, v in OVERLAY.items() if k != "default"}
    with pytest.raises(LabelError, match="owner|classification"):
        doc_label(load_overlay(no_default), "other_doc")


def test_labels_only_go_up_unless_lowering_is_explicit():
    ov = load_overlay(OVERLAY)
    current = {"classification": "confidential", "domains": ["finance"], "owner": "x", "embargo_until": None,
               "label_source": "intake"}
    raised = doc_label(ov, "acme_ar_2025_en", current=current)       # overlay says internal: keep confidential
    assert raised["classification"] == "confidential"
    lowered = doc_label(ov, "acme_ar_2024_en", current=current)      # explicit lower with a reason
    assert lowered["classification"] == "public" and lowered["lowered_reason"] == "published report, declassified"


def test_lowering_without_a_reason_is_rejected():
    bad = {**OVERLAY, "documents": [{"match": "d", "label": {"classification": "public", "owner": "o"},
                                     "lower": True}]}
    with pytest.raises(LabelError, match="reason"):
        load_overlay(bad)


def test_block_labels_by_title_and_by_page_range():
    ov = load_overlay(OVERLAY)
    assert block_label(ov, "acme_ar_2025_en", "Management Discussion and Analysis", 90, 120)["classification"] == \
        "confidential"
    assert block_label(ov, "acme_ar_2025_en", "Something", 41, 41)["classification"] == "restricted"
    assert block_label(ov, "acme_ar_2025_en", "Something", 50, 60) is None
    assert block_label(ov, "acme_ar_2024_en", "Management Discussion and Analysis", 90, 120) is None


def _nodes():
    return [{"node_id": "n1", "parent_id": None, "title": "Management Discussion and Analysis", "start_page": 90,
             "end_page": 120},
            {"node_id": "n2", "parent_id": "n1", "title": "Net Interest Income", "start_page": 95, "end_page": 96},
            {"node_id": "n3", "parent_id": None, "title": "Notes", "start_page": 30, "end_page": 60},
            {"node_id": "n4", "parent_id": "n3", "title": "Share Plans", "start_page": 41, "end_page": 41}]


def test_node_labels_inherit_from_ancestors_and_combine_with_block_rules():
    from kb_core.access.labels import node_labels

    ov = load_overlay(OVERLAY)
    doc = doc_label(ov, "acme_ar_2025_en")
    labels = node_labels(ov, "acme_ar_2025_en", doc, _nodes())
    assert labels["n1"]["classification"] == "confidential"
    assert labels["n2"]["classification"] == "confidential"          # inherits from its ancestor
    assert labels["n2"]["embargo_until"] == "2026-11-15T00:00:00+08:00"   # document embargo kept
    assert labels["n3"]["classification"] == "internal"              # only overlaps the page-range rule 40-42
    assert labels["n3"]["domains"] == ["finance"]
    assert labels["n4"]["classification"] == "restricted"


def test_page_access_is_the_strictest_of_its_covering_nodes_and_page_rules():
    from kb_core.access.labels import node_labels, page_access

    ov = load_overlay(OVERLAY)
    doc = doc_label(ov, "acme_ar_2025_en")
    labels = node_labels(ov, "acme_ar_2025_en", doc, _nodes())
    assert page_access(ov, "acme_ar_2025_en", doc, 95, [labels["n2"]])["classification"] == "confidential"
    assert page_access(ov, "acme_ar_2025_en", doc, 41, [])["classification"] == "restricted"
    assert page_access(ov, "acme_ar_2025_en", doc, 10, [])["classification"] == "internal"


def test_a_lowered_reason_does_not_break_conversion():
    from kb_core.access.labels import to_access

    label = {**doc_label(load_overlay(OVERLAY), "acme_ar_2024_en"), "lowered_reason": "x"}
    assert to_access(label).classification == "public"


def test_labels_only_go_up_in_every_dimension_without_lower():
    ov = load_overlay({"version": 1, "default": {"classification": "public", "owner": "o"},
                       "documents": [{"match": "d", "label": {"classification": "internal", "owner": "g"}}], "blocks": []})
    current = {"classification": "internal", "domains": ["finance"], "owner": "g",
               "embargo_until": "2026-11-15T00:00:00+08:00", "label_source": "overlay"}
    label = doc_label(ov, "d", current=current)
    assert label["domains"] == ["finance"] and label["embargo_until"] == "2026-11-15T00:00:00+08:00"
