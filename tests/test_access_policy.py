"""kb_core.access.policy: subjects, effective labels and the allow rule (round 2 W3, docs/round-2-w3-access.md)."""

import itertools
from datetime import UTC, datetime, timedelta, timezone

import pytest

from kb_core.access.policy import (
    CLASSIFICATIONS,
    Access,
    Decision,
    Subject,
    access_from_label,
    decide,
    effective,
    filter_terms,
    load_roles,
    now,
    subject_for,
)

SGT = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
EMBARGO = datetime(2026, 11, 15, 0, 0, tzinfo=SGT)

ROLES = load_roles()
PUBLIC, ANALYST, CONFIDENTIAL, FULL = (ROLES[r] for r in
                                        ("public", "finance_analyst", "finance_confidential", "full_access"))


def acc(classification="public", domains=(), owner="o", embargo_until=None) -> Access:
    return Access(classification, tuple(domains), owner, embargo_until)


PUBLIC_DOC = acc()
INTERNAL_FINANCE = acc("internal", ["finance"])
CONFIDENTIAL_FINANCE = acc("confidential", ["finance"])
INTERNAL_HR = acc("internal", ["hr"])
RESTRICTED = acc("restricted", ["finance"])


# --- roles and subjects ---------------------------------------------------------------------------------------------

def test_roles_file_has_the_four_demo_roles():
    assert ROLES == {
        "public": Subject("public", "public", (), False),
        "finance_analyst": Subject("finance_analyst", "internal", ("finance",), False),
        "finance_confidential": Subject("finance_confidential", "confidential", ("finance",), True),
        "full_access": Subject("full_access", "restricted", ("*",), True),
    }


def test_classifications_are_ordered_low_to_high():
    assert CLASSIFICATIONS == ("public", "internal", "confidential", "restricted")


@pytest.mark.parametrize("role", [None, ""])
def test_missing_subject_is_public_never_full_access(role):
    s = subject_for(role)
    assert s == PUBLIC
    assert s.role != "full_access"


def test_named_roles_resolve():
    assert subject_for("finance_analyst") == ANALYST
    assert subject_for("full_access", ROLES) == FULL


def test_unknown_role_names_the_allowed_roles():
    with pytest.raises(ValueError) as e:
        subject_for("admin")
    for r in ROLES:
        assert r in str(e.value)


def test_load_roles_rejects_bad_files(tmp_path):
    bad = {
        "clearance": "roles:\n  x: {clearance: secret, domains: [], embargo_exempt: false}\n",
        "domains": "roles:\n  x: {clearance: public, domains: finance, embargo_exempt: false}\n",
        "exempt": "roles:\n  x: {clearance: public, domains: [], embargo_exempt: 'yes'}\n",
        "no_public": "roles:\n  x: {clearance: public, domains: [], embargo_exempt: false}\n",
        "empty": "",
    }
    for name, text in bad.items():
        p = tmp_path / f"{name}.yaml"
        p.write_text(text)
        with pytest.raises(ValueError):
            load_roles(p)


def test_load_roles_reads_a_given_path(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text("roles:\n  public: {clearance: public, domains: [], embargo_exempt: false}\n"
                 "  hr: {clearance: internal, domains: [hr], embargo_exempt: false}\n")
    roles = load_roles(p)
    assert roles["hr"] == Subject("hr", "internal", ("hr",), False)
    assert subject_for(None, roles) == roles["public"]


def test_a_public_default_that_is_not_public_is_rejected(tmp_path):
    p = tmp_path / "r.yaml"
    p.write_text("roles:\n  public: {clearance: restricted, domains: ['*'], embargo_exempt: true}\n")
    with pytest.raises(ValueError):
        load_roles(p)


# --- decide: role x label -------------------------------------------------------------------------------------------

EXPECTED = {
    # resource:              public  analyst confidential full
    "public_doc":            (True,  True,   True,        True),
    "internal_finance":      (False, True,   True,        True),
    "confidential_finance":  (False, False,  True,        True),
    "internal_hr":           (False, False,  False,       True),
    "restricted":            (False, False,  False,       True),
}
RESOURCES = {"public_doc": PUBLIC_DOC, "internal_finance": INTERNAL_FINANCE,
             "confidential_finance": CONFIDENTIAL_FINANCE, "internal_hr": INTERNAL_HR, "restricted": RESTRICTED}
SUBJECTS = (PUBLIC, ANALYST, CONFIDENTIAL, FULL)


@pytest.mark.parametrize("name", list(EXPECTED))
def test_role_by_label(name):
    for subject, want in zip(SUBJECTS, EXPECTED[name], strict=True):
        d = decide(subject, RESOURCES[name], NOW)
        assert isinstance(d, Decision)
        assert d.allow is want, (subject.role, name, d.reason)
        assert d.reason and d.reason.isascii()


def test_clearance_reason_mentions_classification():
    d = decide(PUBLIC, INTERNAL_FINANCE, NOW)
    assert not d.allow and "classification" in d.reason


def test_domain_reason_mentions_domain():
    d = decide(CONFIDENTIAL, INTERNAL_HR, NOW)
    assert not d.allow and "domain" in d.reason


def test_resource_without_domains_is_open_to_any_cleared_subject():
    assert decide(ANALYST, acc("internal", []), NOW).allow
    assert not decide(PUBLIC, acc("internal", []), NOW).allow


def test_public_classification_ignores_domains():
    assert decide(PUBLIC, acc("public", ["hr"]), NOW).allow
    assert decide(ANALYST, acc("public", ["hr"]), NOW).allow


def test_star_domain_reads_any_domain():
    assert decide(FULL, acc("confidential", ["hr", "legal"]), NOW).allow


def test_any_shared_domain_is_enough():
    assert decide(ANALYST, acc("internal", ["hr", "finance"]), NOW).allow


def test_subject_without_domains_reads_only_unrestricted_non_public():
    s = Subject("internal_nodomain", "internal", (), False)
    assert decide(s, acc("internal", []), NOW).allow
    assert not decide(s, acc("internal", ["finance"]), NOW).allow


# --- embargo --------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("delta,allowed", [(timedelta(seconds=-1), False), (timedelta(0), True),
                                           (timedelta(seconds=1), True)])
def test_embargo_before_at_and_after_the_instant(delta, allowed):
    res = acc("internal", ["finance"], embargo_until=EMBARGO)
    d = decide(ANALYST, res, EMBARGO.astimezone(UTC) + delta)
    assert d.allow is allowed
    if not allowed:
        assert "embargo" in d.reason


def test_embargo_exempt_roles_read_before_the_embargo():
    res = acc("internal", ["finance"], embargo_until=EMBARGO)
    before = EMBARGO - timedelta(days=1)
    assert decide(CONFIDENTIAL, res, before).allow
    assert decide(FULL, res, before).allow
    assert not decide(ANALYST, res, before).allow


def test_embargo_does_not_override_clearance_for_exempt_roles():
    res = acc("restricted", ["finance"], embargo_until=EMBARGO)
    assert not decide(CONFIDENTIAL, res, EMBARGO + timedelta(days=1)).allow


def test_public_embargoed_doc_is_hidden_from_public_until_then():
    res = acc("public", [], embargo_until=EMBARGO)
    assert not decide(PUBLIC, res, EMBARGO - timedelta(seconds=1)).allow
    assert decide(PUBLIC, res, EMBARGO).allow


def test_decide_rejects_a_naive_now():
    with pytest.raises(ValueError):
        decide(PUBLIC, PUBLIC_DOC, datetime(2026, 10, 27, 12, 0))


# --- effective ------------------------------------------------------------------------------------------------------

def test_effective_without_block_is_the_document():
    doc = acc("internal", ["finance"], "group-finance", EMBARGO)
    assert effective(doc, None) == doc


def test_effective_takes_the_higher_classification():
    doc = acc("internal", ["finance"], "d")
    assert effective(doc, acc("confidential", [], "")).classification == "confidential"
    assert effective(acc("confidential", [], "d"), acc("public", [], "")).classification == "confidential"


def test_effective_block_domains_override_document_domains():
    doc = acc("internal", ["finance"], "d")
    assert effective(doc, acc("internal", ["hr"], "")).domains == ("hr",)
    assert effective(doc, acc("internal", [], "")).domains == ("finance",)


def test_effective_takes_the_later_embargo():
    early, late = EMBARGO, EMBARGO + timedelta(days=3)
    assert effective(acc(embargo_until=early), acc(embargo_until=late)).embargo_until == late
    assert effective(acc(embargo_until=late), acc(embargo_until=early)).embargo_until == late
    assert effective(acc(embargo_until=early), acc(embargo_until=None)).embargo_until == early
    assert effective(acc(embargo_until=None), acc(embargo_until=late)).embargo_until == late


def test_effective_owner_falls_back_to_the_document():
    doc = acc(owner="group-finance")
    assert effective(doc, acc(owner="")).owner == "group-finance"
    assert effective(doc, acc(owner="treasury")).owner == "treasury"


def test_overlay_demo_block_hides_mdna_from_the_analyst():
    doc = access_from_label({"classification": "internal", "domains": ["finance"], "owner": "group-finance",
                             "embargo_until": "2026-11-15T00:00:00+08:00"})
    block = access_from_label({"classification": "confidential", "domains": ["finance"]})
    mdna = effective(doc, block)
    after = datetime(2026, 11, 20, tzinfo=UTC)
    assert not decide(ANALYST, mdna, after).allow
    assert decide(ANALYST, doc, after).allow
    assert decide(CONFIDENTIAL, mdna, NOW).allow


# --- filter_terms ---------------------------------------------------------------------------------------------------

def test_filter_terms_per_role():
    assert filter_terms(PUBLIC, NOW) == {"classifications": ["public"], "domains": [], "embargo_before": NOW}
    assert filter_terms(ANALYST, NOW) == {"classifications": ["public", "internal"], "domains": ["finance"],
                                          "embargo_before": NOW}
    assert filter_terms(CONFIDENTIAL, NOW) == {"classifications": ["public", "internal", "confidential"],
                                               "domains": ["finance"], "embargo_before": None}
    assert filter_terms(FULL, NOW) == {"classifications": list(CLASSIFICATIONS), "domains": None,
                                       "embargo_before": None}


def test_filter_terms_rejects_a_naive_now():
    with pytest.raises(ValueError):
        filter_terms(PUBLIC, datetime(2026, 10, 27))


def passes(terms: dict, r: Access) -> bool:
    """How a store applies filter_terms (the ES bool filter / PG predicate the routes build)."""
    if r.classification not in terms["classifications"]:
        return False
    if not (r.classification == "public" or not r.domains or terms["domains"] is None
            or set(r.domains) & set(terms["domains"])):
        return False
    return terms["embargo_before"] is None or r.embargo_until is None or r.embargo_until <= terms["embargo_before"]


def test_filter_terms_agree_with_decide_on_a_grid():
    subjects = [*SUBJECTS, Subject("internal_nodomain", "internal", (), False),
                Subject("hr_lead", "restricted", ("hr", "legal"), False)]
    domain_sets = [(), ("finance",), ("hr",), ("finance", "hr"), ("legal",)]
    embargoes = [None, NOW - timedelta(days=1), NOW, NOW + timedelta(seconds=1), EMBARGO]
    checked = 0
    for s, c, ds, e in itertools.product(subjects, CLASSIFICATIONS, domain_sets, embargoes):
        r = acc(c, ds, "o", e)
        assert passes(filter_terms(s, NOW), r) is decide(s, r, NOW).allow, (s.role, r)
        checked += 1
    assert checked == len(subjects) * 4 * 5 * 5


# --- now ------------------------------------------------------------------------------------------------------------

BASE_ENV = {"KB_CORE_PG_DSN": "postgresql://unused", "KB_CORE_ES_URL": "http://unused"}


def _clock(env: dict):
    from kb_core.config import load_settings

    return load_settings({**BASE_ENV, **env}, env_file=None)


def test_now_is_real_aware_utc_by_default():
    t = now(_clock({}))
    assert t.tzinfo is not None and t.utcoffset() == timedelta(0)
    assert abs(t - datetime.now(UTC)) < timedelta(seconds=5)


def test_now_ignores_the_clock_without_the_override_flag():
    for env in ({"KB_CORE_NOW": "2030-01-01T00:00:00+00:00"},
                {"KB_CORE_NOW": "2030-01-01T00:00:00+00:00", "KB_CORE_ALLOW_CLOCK_OVERRIDE": "false"}):
        assert abs(now(_clock(env)) - datetime.now(UTC)) < timedelta(seconds=5)


@pytest.mark.parametrize("flag", ["1", "yes", "on", "maybe"])
def test_the_override_flag_accepts_only_true_or_false(flag):
    from kb_core.config import ConfigError

    with pytest.raises(ConfigError, match="KB_CORE_ALLOW_CLOCK_OVERRIDE"):
        _clock({"KB_CORE_NOW": "2030-01-01T00:00:00+00:00", "KB_CORE_ALLOW_CLOCK_OVERRIDE": flag})


@pytest.mark.parametrize("flag", ["true", "TRUE", "True"])
def test_now_uses_the_clock_with_the_override_flag(flag):
    t = now(_clock({"KB_CORE_NOW": "2026-11-15T00:00:00+08:00", "KB_CORE_ALLOW_CLOCK_OVERRIDE": flag}))
    assert t == datetime(2026, 11, 14, 16, 0, tzinfo=UTC)
    assert t.utcoffset() == timedelta(0)


def test_now_rejects_a_naive_override():
    with pytest.raises(ValueError):
        _clock({"KB_CORE_NOW": "2026-11-15T00:00:00", "KB_CORE_ALLOW_CLOCK_OVERRIDE": "true"})


def test_now_rejects_a_malformed_override():
    with pytest.raises(ValueError):
        _clock({"KB_CORE_NOW": "next tuesday", "KB_CORE_ALLOW_CLOCK_OVERRIDE": "true"})


def test_now_with_flag_but_no_clock_is_real_time():
    assert abs(now(_clock({"KB_CORE_ALLOW_CLOCK_OVERRIDE": "true"})) - datetime.now(UTC)) < timedelta(seconds=5)


def test_now_reads_the_running_settings_by_default():
    from kb_core.config import use

    try:
        use(_clock({"KB_CORE_NOW": "2031-05-01T00:00:00Z", "KB_CORE_ALLOW_CLOCK_OVERRIDE": "true"}))
        assert now() == datetime(2031, 5, 1, tzinfo=UTC)
        use(_clock({"KB_CORE_NOW": "2031-05-01T00:00:00Z"}))
        assert abs(now() - datetime.now(UTC)) < timedelta(seconds=5)
    finally:
        use(None)


# --- access_from_label ----------------------------------------------------------------------------------------------

def test_access_from_label_full():
    a = access_from_label({"classification": "internal", "domains": ["finance"], "owner": "group-finance",
                           "embargo_until": "2026-11-15T00:00:00+08:00", "label_source": "overlay"})
    assert a == Access("internal", ("finance",), "group-finance", EMBARGO)


def test_access_from_label_defaults():
    assert access_from_label({"classification": "public"}) == Access("public", (), "", None)


@pytest.mark.parametrize("label", [
    {},
    {"classification": "secret"},
    {"classification": "public", "domains": "finance"},
    {"classification": "public", "domains": [1]},
    {"classification": "public", "owner": 3},
    {"classification": "public", "embargo_until": "2026-11-15T00:00:00"},
    {"classification": "public", "embargo_until": "soon"},
    {"classification": "public", "embargo_until": 20261115},
    {"classification": "public", "label_source": "guess"},
    {"classification": "public", "clearance": "restricted"},
    "public",
])
def test_access_from_label_rejects_bad_input(label):
    with pytest.raises(ValueError):
        access_from_label(label)
