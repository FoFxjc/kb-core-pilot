"""The policy's filter terms as store filters (round 2 W3 T3.4): every ES route adds `es_access_filter` to its bool
filter, so hidden content never takes part in recall, counts or gaps. Filters do not change BM25 scores, so the
full-access subject gets exactly the unfiltered ranking."""

from datetime import datetime


def es_access_filter(terms: dict | None) -> list[dict]:
    """ES bool-filter clauses for `policy.filter_terms(subject, now)`; [] when `terms` is None (no access control).

    A document passes when its classification is allowed; it is public, has no domains, or shares a domain with
    the subject (skipped for "any domain"); and it has no embargo or the embargo has passed (skipped for exempt
    subjects). Documents indexed before labels existed have no access fields and are treated as public with no
    domains and no embargo."""
    from kb_core.access.policy import CLASSIFICATIONS

    if terms is None or (len(terms["classifications"]) == len(CLASSIFICATIONS) and terms.get("domains") is None
                         and terms.get("embargo_before") is None):
        return []                         # the subject sees everything: no filter (scores are unchanged either way)
    # fail closed: a document without an access classification (indexed before labels) passes no restricted filter
    clauses: list[dict] = [{"terms": {"access_classification": list(terms["classifications"])}}]
    if terms.get("domains") is not None:
        clauses.append({"bool": {"should": [
            {"term": {"access_classification": "public"}},
            {"bool": {"must_not": {"exists": {"field": "access_domains"}}}},
            *([{"terms": {"access_domains": list(terms["domains"])}}] if terms["domains"] else []),
        ], "minimum_should_match": 1}})
    before = terms.get("embargo_before")
    if before is not None:
        stamp = before.isoformat() if isinstance(before, datetime) else str(before)
        clauses.append({"bool": {"should": [
            {"bool": {"must_not": {"exists": {"field": "access_embargo_until"}}}},
            {"range": {"access_embargo_until": {"lte": stamp}}},
        ], "minimum_should_match": 1}})
    return clauses
