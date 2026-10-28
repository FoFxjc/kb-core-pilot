import pytest

from kb_core.eval import samples


def _sheet(*verdicts):
    return {"doc_id": "d", "seed": 105, "sampled": len(verdicts), "protocol": samples.PROTOCOL,
            "items": [{"node_id": f"n{i}", "verdict": v} for i, v in enumerate(verdicts)]}


def test_tree_accuracy_counts_correct_items():
    acc = samples.tree_accuracy(_sheet("correct", "wrong", "correct", "correct"))
    assert acc == {"doc_id": "d", "seed": 105, "correct": 3, "sampled": 4, "value": 0.75}


def test_tree_accuracy_refuses_an_unjudged_sheet():
    with pytest.raises(ValueError, match="not judged"):
        samples.tree_accuracy(_sheet("correct", None))
