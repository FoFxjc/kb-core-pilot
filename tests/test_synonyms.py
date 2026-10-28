"""Round 2 W2 (T2.3 class F1, T2.4): word-level query synonyms and the held-out guard."""

import pytest

from kb_core.retrieval.aliases import synonym_units
from kb_core.retrieval.coverage import coverage, coverage_units

SYN = {"employee": ["staff"], "分红": ["股息", "派息"]}


def test_a_query_word_with_synonyms_adds_them_as_terms_and_one_unit():
    extra, units = synonym_units(["employee", "costs"], SYN)
    assert extra == ["staff"]
    assert units == [{"kind": "synonym", "id": "employee", "typed": [["employee"]],
                      "variants": [["employee"], ["staff"]]}]


def test_the_synonym_unit_is_hit_by_any_of_its_words_and_counts_once():
    _, syn = synonym_units(["employee", "costs"], SYN)
    units = coverage_units(["employee", "costs"], syn, informative=lambda t: True)
    assert [u["id"] for u in units] == ["employee", "costs"]          # "employee" absorbed into its synonym unit
    df = (100, {"employee": 5, "staff": 20, "costs": 30})
    assert coverage(units, {"staff", "costs"}, df) == 1.0
    assert coverage(units, {"costs"}, df) < 1.0


def test_chinese_synonyms_expand_the_same_way():
    extra, _ = synonym_units(["分红", "比例"], SYN)
    assert extra == ["股息", "派息"]


def test_the_guard_rejects_a_synonym_that_is_a_held_out_wording(tmp_path):
    from kb_core.domains import check_synonyms

    with pytest.raises(ValueError, match="held-out"):
        check_synonyms({"employee costs": ["staff costs"]}, held_out={"employee costs"})
    with pytest.raises(ValueError, match="held-out"):
        check_synonyms({"wage": ["employee pay bill"]}, held_out={"employee pay bill"})
    check_synonyms(SYN, held_out={"employee costs"})                  # a single word inside a phrase is fine


def test_the_held_out_wordings_include_the_sealed_set():
    from kb_core.domains import held_out_wordings

    words = held_out_wordings()
    assert "book value per share" in words                             # old 16
    assert len(words) >= 16 + 24                                       # old 16 + sealed 24 (+ legacy list)


def test_a_concept_spelling_recognising_a_sealed_wording_fails_to_load(tmp_path):
    import yaml

    from kb_core.build.concepts import default_paths, load_spec

    path, _ = default_paths("banking")
    spec = yaml.safe_load(path.read_text())
    sealed = next(q["heldout_term"] for q in yaml.safe_load(
        (path.parents[2] / "eval" / "round2_heldout.yaml").read_text())["questions"] if q["lang"] == "en")
    spec["concepts"][0].setdefault("query_only", []).append(sealed)
    bad = tmp_path / "concepts.yaml"
    bad.write_text(yaml.safe_dump(spec, allow_unicode=True))
    with pytest.raises(ValueError, match="held-out"):
        load_spec(bad)
    load_spec(path)                                                     # the real table loads


def test_a_word_inside_an_alias_unit_gets_no_synonym_unit():
    extra, units = synonym_units(["earnings", "per", "share"], {"earnings": ["results"]},
                                 absorbed={"earnings", "per", "share"})
    assert extra == [] and units == []


def test_synonyms_are_off_when_aliases_are_off():
    from kb_core.config import load_settings, use
    from kb_core.retrieval import aliases

    base = {"KB_CORE_PG_DSN": "postgresql://unused", "KB_CORE_ES_URL": "http://unused"}
    try:
        use(load_settings({**base, "KB_CORE_ALIASES": "off"}, env_file=None))
        assert not aliases.enabled()
        use(load_settings(base, env_file=None))
        assert aliases.enabled()
    finally:
        use(None)
    assert aliases.enabled()                  # no running settings: the default (on)
