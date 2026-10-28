from decimal import Decimal

from kb_core.build.facts import merge


def obs(obs_id, doc_id, report_year, fy, value, concept="net_profit"):
    return {"obs_id": obs_id, "doc_id": doc_id, "report_year": report_year, "concept_id": concept, "entity_id": "x",
            "fiscal_year": fy, "period_id": f"D:{fy}-01-01:{fy}-12-31", "value": Decimal(value), "unit": "SGD"}


def test_merge_agreed_single_conflict():
    facts = {f["fiscal_year"]: f for f in merge([
        obs("a", "x_ar_2025_en", 2025, 2025, "7"), obs("b", "x_ar_2025_zh", 2025, 2025, "7"),   # agreed
        obs("c", "x_ar_2025_en", 2025, 2024, "6"),                                               # single
        obs("d", "x_ar_2025_en", 2025, 2023, "5"), obs("e", "x_ar_2025_zh", 2025, 2023, "4")])}  # conflict
    assert facts[2025]["versions"][0]["status"] == "agreed" and facts[2025]["versions"][0]["n_sources"] == 2
    assert facts[2024]["versions"][0]["status"] == "single"
    assert facts[2023]["versions"][0]["status"] == "conflict"


def test_restatement_makes_a_new_version():
    [f] = merge([obs("a", "x_ar_2024_en", 2024, 2024, "6"), obs("b", "x_ar_2025_en", 2025, 2024, "6.5")])
    assert [(v["version_no"], v["known_from"], v["known_to"], v["value"]) for v in f["versions"]] == [
        (1, 2024, 2025, Decimal("6")), (2, 2025, None, Decimal("6.5"))]


def test_winning_prefers_own_year_then_en():
    [f] = merge([obs("z1", "x_ar_2025_zh", 2025, 2024, "6"), obs("e1", "x_ar_2025_en", 2025, 2024, "6"),
                 obs("z0", "x_ar_2024_zh", 2024, 2024, "6"), obs("e0", "x_ar_2024_en", 2024, 2024, "6")])
    assert f["versions"][0]["winning_obs_id"] == "e0"
