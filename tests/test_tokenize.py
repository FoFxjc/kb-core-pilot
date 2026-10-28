from pathlib import Path

from kb_core.build.tokenize import to_field, tokens

FIXTURE = (Path(__file__).parent / "fixtures" / "zh_tokenize.txt").read_text().splitlines()


def test_tokenize_zh_uses_domain_dict():
    sentence, term = FIXTURE
    assert term in tokens(sentence, "banking")


def test_tokenize_keeps_thousand_numbers():
    assert tokens("Net profit was 42,174 and 1,234.5 million", "banking") == \
        ["net", "profit", "was", "42,174", "42174", "and", "1,234.5", "1234.5", "million"]


def test_tokenize_lowercases_and_drops_punctuation():
    assert to_field("CET1 Ratio: 16.9% (Group)", "banking") == "cet1 ratio 16.9% group"
