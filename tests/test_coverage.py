import math
from collections import Counter

from kb_core.retrieval.coverage import coverage, coverage_units, idf


def test_idf_formula():
    assert idf(0, 10) == math.log(1 + 10.5 / 0.5)
    assert idf(10, 10) == math.log(1 + 0.5 / 10.5)


def df():
    return 100, Counter({"npl": 5, "ratio": 40, "group": 90, "nim": 3})


def test_coverage_weighs_rare_terms_more():
    units = coverage_units(["npl", "ratio"], [], informative=lambda t: True)
    full = coverage(units, {"npl", "ratio"}, df())
    rare_only = coverage(units, {"npl"}, df())
    common_only = coverage(units, {"ratio"}, df())
    assert full == 1.0 and rare_only > 0.5 > common_only


def test_coverage_skips_units_absent_from_every_page():
    units = coverage_units(["npl", "zzz"], [], informative=lambda t: True)
    assert coverage(units, {"npl"}, df()) == 1.0


def test_alias_unit_is_all_or_nothing():
    alias = {"id": "npl_ratio", "typed": [["npl", "ratio"]], "variants": [["npl", "ratio"], ["nim"]]}
    units = coverage_units(["npl", "ratio"], [alias], informative=lambda t: True)
    assert len(units) == 1
    assert coverage(units, {"npl"}, df()) == 0.0
    assert coverage(units, {"nim"}, df()) == 1.0
