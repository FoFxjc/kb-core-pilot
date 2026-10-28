"""The access policy (T3.3, docs/round-2-w3-access.md sections 1, 3 and 4).

A subject (a demo role from config/access_roles.yaml) may read a resource (a document or block with an access label)
when its clearance covers the classification, the domains allow it and no embargo applies. `decide` answers that for
one resource; `filter_terms` gives the same rule as data for the stores to filter on. Both must agree: a resource
passes `filter_terms` exactly when `decide` allows it.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from kb_core.paths import data_dir

CLASSIFICATIONS = ("public", "internal", "confidential", "restricted")
LABEL_SOURCES = ("overlay", "intake", "default")
LABEL_KEYS = {"classification", "domains", "owner", "embargo_until", "label_source"}
DEFAULT_ROLE = "public"
ANY_DOMAIN = "*"


@dataclass(frozen=True)
class Subject:
    role: str
    clearance: str
    domains: tuple[str, ...]
    embargo_exempt: bool


@dataclass(frozen=True)
class Access:
    classification: str
    domains: tuple[str, ...]
    owner: str
    embargo_until: datetime | None


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str  # for the audit only, never returned to callers


def _rank(classification: str) -> int:
    if classification not in CLASSIFICATIONS:
        raise ValueError(f"unknown classification {classification!r}; allowed: {', '.join(CLASSIFICATIONS)}")
    return CLASSIFICATIONS.index(classification)


def _aware(t: datetime, what: str) -> datetime:
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError(f"{what} must carry a UTC offset: {t.isoformat()}")
    return t


def _parse_time(text: str, what: str) -> datetime:
    try:
        t = datetime.fromisoformat(text)
    except ValueError as e:
        raise ValueError(f"{what} is not an ISO-8601 timestamp: {text!r}") from e
    return _aware(t, what)


def _str_list(value, what: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise ValueError(f"{what} must be a list of non-empty strings: {value!r}")
    return tuple(value)


# --- subjects -------------------------------------------------------------------------------------------------------

def load_roles(path: Path | str | None = None) -> dict[str, Subject]:
    """Roles from config/access_roles.yaml (or `path`). The default role `public` must exist and be the lowest."""
    if path is None:
        from kb_core.config import current

        s = current()
        path = s.access_roles if s is not None and s.access_roles is not None else None
    p = Path(path) if path is not None else data_dir("config") / "access_roles.yaml"
    spec = yaml.safe_load(p.read_text()) or {}
    rows = spec.get("roles") if isinstance(spec, dict) else None
    if not isinstance(rows, dict) or not rows:
        raise ValueError(f"{p}: no roles")
    roles = {}
    for name, row in rows.items():
        if not isinstance(row, dict) or set(row) != {"clearance", "domains", "embargo_exempt"}:
            raise ValueError(f"{p}: role {name!r} needs exactly clearance, domains and embargo_exempt")
        _rank(row["clearance"])
        if not isinstance(row["embargo_exempt"], bool):
            raise ValueError(f"{p}: role {name!r}: embargo_exempt must be true or false")
        roles[str(name)] = Subject(str(name), row["clearance"], _str_list(row["domains"], f"role {name!r} domains"),
                                   row["embargo_exempt"])
    default = roles.get(DEFAULT_ROLE)
    if default != Subject(DEFAULT_ROLE, "public", (), False):
        raise ValueError(f"{p}: role {DEFAULT_ROLE!r} must exist with clearance public, no domains, not exempt")
    return roles


def subject_for(role: str | None, roles: Mapping[str, Subject] | None = None) -> Subject:
    """The subject for a role name; a missing role is `public` (never full access); an unknown one is an error."""
    roles = load_roles() if roles is None else roles
    if not role:
        return roles[DEFAULT_ROLE]
    if role not in roles:
        raise ValueError(f"unknown role {role!r}; allowed: {', '.join(sorted(roles))}")
    return roles[role]


# --- labels ---------------------------------------------------------------------------------------------------------

def access_from_label(label: dict) -> Access:
    """An Access from a label dict (overlay or intake). Only classification is required; a block label may leave
    domains, owner and embargo_until unset so that `effective` falls back to its document."""
    if not isinstance(label, dict):
        raise ValueError(f"an access label must be a mapping: {label!r}")
    extra = set(label) - LABEL_KEYS
    if extra:
        raise ValueError(f"unknown access label fields: {', '.join(sorted(map(str, extra)))}")
    if "classification" not in label:
        raise ValueError("an access label needs a classification")
    classification = label["classification"]
    if not isinstance(classification, str):
        raise ValueError(f"classification must be a string: {classification!r}")
    _rank(classification)
    domains = _str_list(label.get("domains", []), "domains")
    owner = label.get("owner", "")
    if not isinstance(owner, str):
        raise ValueError(f"owner must be a string: {owner!r}")
    embargo = label.get("embargo_until")
    if embargo is not None:
        if not isinstance(embargo, str):
            raise ValueError(f"embargo_until must be an ISO-8601 string or null: {embargo!r}")
        embargo = _parse_time(embargo, "embargo_until")
    source = label.get("label_source")
    if source is not None and source not in LABEL_SOURCES:
        raise ValueError(f"label_source must be one of {', '.join(LABEL_SOURCES)}: {source!r}")
    return Access(classification, domains, owner, embargo)


def effective(doc: Access, block: Access | None) -> Access:
    """A block's access: the higher classification, the block's domains if it sets any, the later embargo, the
    block's owner if set."""
    if block is None:
        return doc
    embargoes = [t for t in (doc.embargo_until, block.embargo_until) if t is not None]
    return Access(
        classification=max(doc.classification, block.classification, key=_rank),
        domains=block.domains or doc.domains,
        owner=block.owner or doc.owner,
        embargo_until=max(embargoes) if embargoes else None,
    )


# --- the rule -------------------------------------------------------------------------------------------------------

def decide(subject: Subject, resource: Access, now: datetime) -> Decision:
    _aware(now, "now")
    if _rank(subject.clearance) < _rank(resource.classification):
        return Decision(False, f"classification {resource.classification} above clearance {subject.clearance}")
    if not (resource.classification == "public" or not resource.domains or ANY_DOMAIN in subject.domains
            or set(resource.domains) & set(subject.domains)):
        return Decision(False, f"domain {','.join(resource.domains)} not in subject domains")
    if resource.embargo_until is not None and now < resource.embargo_until and not subject.embargo_exempt:
        return Decision(False, f"embargo until {resource.embargo_until.isoformat()}")
    return Decision(True, "allowed")


def filter_terms(subject: Subject, now: datetime) -> dict:
    """The rule of `decide` as data for the stores. A resource passes when its classification is listed, it is
    public or has no domains or `domains` is None (any) or the domains intersect, and `embargo_before` is None
    (exempt) or it has no embargo or its embargo is <= embargo_before."""
    _aware(now, "now")
    return {
        "classifications": list(CLASSIFICATIONS[: _rank(subject.clearance) + 1]),
        "domains": None if ANY_DOMAIN in subject.domains else list(subject.domains),
        "embargo_before": None if subject.embargo_exempt else now,
    }


def now(settings=None) -> datetime:
    """Real UTC time, or the test clock KB_CORE_NOW when KB_CORE_ALLOW_CLOCK_OVERRIDE is true (D4; development only,
    production refuses both). `settings` defaults to the running process's settings."""
    from kb_core.config import current

    s = settings if settings is not None else current()
    if s is not None and s.clock_override and s.now is not None:
        return s.now
    return datetime.now(UTC)
