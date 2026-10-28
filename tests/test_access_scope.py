"""kb_core.access.scope: the subject of a tool call (round 2 W3)."""

import pytest

from kb_core.access import scope

INTERNAL_FINANCE = {"classification": "internal", "domains": ["finance"], "owner": "o", "embargo_until": None,
                    "label_source": "overlay"}


def test_no_subject_means_public():
    assert scope.subject().role == "public"
    assert not scope.visible(INTERNAL_FINANCE)
    assert not scope.visible(None)          # fail closed (review of PR #15)


def test_acting_as_sets_and_restores_the_subject():
    with scope.acting_as("finance_analyst") as s:
        assert s.role == "finance_analyst" and scope.visible(INTERNAL_FINANCE)
    assert scope.subject().role == "public"


def test_an_unknown_role_is_rejected():
    with pytest.raises(ValueError):
        with scope.acting_as("root"):
            pass


def test_terms_follow_the_subject():
    with scope.acting_as("full_access"):
        assert scope.terms()["domains"] is None and scope.terms()["embargo_before"] is None
    assert scope.terms()["classifications"] == ["public"]


def test_a_resource_without_a_label_is_visible_only_with_full_access():
    assert not scope.visible(None)
    with scope.acting_as("full_access"):
        assert scope.visible(None)
