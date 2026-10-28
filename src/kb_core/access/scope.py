"""The subject of the current tool call (round 2 W3). `traced` runs every tool inside `acting_as(role)`; routes,
counts, the document catalogue and evidence checks read `subject()`, `terms()` and `visible()` from here, so one
setting applies to every route of the call. No subject set means the default subject `public`."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from kb_core.access.policy import Subject, decide, filter_terms, now, subject_for

_subject: ContextVar[Subject | None] = ContextVar("kb_core_subject", default=None)
_filtered: ContextVar[list[int] | None] = ContextVar("kb_core_filtered", default=None)
_user: ContextVar[str | None] = ContextVar("kb_core_user", default=None)


@contextmanager
def as_user(user: str | None) -> Iterator[None]:
    """The authenticated user of the enclosed calls (from the SSO gateway; None in auth mode none): audit only."""
    token = _user.set(user)
    try:
        yield
    finally:
        _user.reset(token)


def user() -> str | None:
    return _user.get()


@contextmanager
def acting_as(role: str | None) -> Iterator[Subject]:
    """Run the enclosed tool call as `role` (None or "" -> public; an unknown role raises ValueError)."""
    token, counter = _subject.set(subject_for(role)), _filtered.set([0])
    try:
        yield _subject.get()
    finally:
        _subject.reset(token)
        _filtered.reset(counter)


def note_filtered(n: int) -> None:
    """Count items the policy hid in this call (for the audit only, never for the caller)."""
    c = _filtered.get()
    if c is not None and n > 0:
        c[0] += n


def filtered() -> int:
    c = _filtered.get()
    return c[0] if c is not None else 0


def restricted() -> bool:
    """Whether the current subject's filter hides anything at all (full access does not)."""
    t = terms()
    from kb_core.access.policy import CLASSIFICATIONS

    return len(t["classifications"]) < len(CLASSIFICATIONS) or t["domains"] is not None \
        or t["embargo_before"] is not None


def subject() -> Subject:
    return _subject.get() or subject_for(None)


def terms() -> dict:
    """The current subject's filter terms for the stores (policy.filter_terms at the current time)."""
    return filter_terms(subject(), now())


def visible(label: dict | None) -> bool:
    """Whether the current subject may see a resource with this stored label. A resource without a label (built
    before labels existed, or a stale row) is visible only to a subject whose filter hides nothing (fail closed)."""
    from kb_core.access.labels import to_access

    if not label:
        return not restricted()
    return decide(subject(), to_access(label), now()).allow
