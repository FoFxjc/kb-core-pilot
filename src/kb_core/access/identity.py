"""Who is calling (enterprise readiness B): the identity of an HTTP, MCP or live chat request.

Two modes (KB_CORE_AUTH_MODE):

- `none` (development only): no user; the caller may pick a demo role with X-KB-Subject (or `subject` on page
  images and the live chat body); without one the call runs as `public`.
- `trusted_header` (required in production): the company SSO gateway authenticates the user and sets the user header
  (KB_CORE_AUTH_USER_HEADER) and the groups header (KB_CORE_AUTH_GROUPS_HEADER, comma-separated). Groups map to roles
  in config/access_role_map.yaml. X-KB-Subject is rejected; a request without a user is 401 and is never served as
  `public`; a user with no mapped role is 403. The service must be reachable only through the gateway.

A user may hold several roles. Data access runs as the data role with the highest clearance (ties: the first in
config/access_roles.yaml); roles are never combined into a broader one. The `admin` role (from `admin_groups`) is
required for /v1/admin/* (including import and live chat). It gives no data role, so it cannot call the data tools or
MCP; but the admin endpoints are an operator view: traces and sessions show every user's tool calls and results.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import yaml

from kb_core.config import Settings
from kb_core.paths import data_dir
from kb_core.retrieval.core import ApiError

ADMIN = "admin"
SUBJECT_HEADER = "x-kb-subject"


@dataclass(frozen=True)
class Identity:
    user: str | None                 # None only in auth mode none
    groups: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()      # every role the user holds (data roles and admin)
    role: str | None = None          # the data role tool calls run as (None: public in mode none)
    admin: bool = False

    @property
    def can_read(self) -> bool:
        return self.user is None or self.role is not None


@dataclass(frozen=True)
class RoleMap:
    groups: dict[str, str]
    admin_groups: tuple[str, ...]


def _role_map_path(settings: Settings) -> Path:
    return settings.access_role_map or data_dir("config") / "access_role_map.yaml"


@cache
def _load_role_map(path: Path) -> RoleMap:
    from kb_core.access.policy import load_roles

    spec = yaml.safe_load(path.read_text()) or {}
    groups = spec.get("groups") or {}
    admin_groups = spec.get("admin_groups") or []
    if not isinstance(groups, dict) or not isinstance(admin_groups, list):
        raise ValueError(f"{path}: groups must be a mapping and admin_groups a list")
    roles = load_roles()
    for g, r in groups.items():
        if r not in roles:
            raise ValueError(f"{path}: group {g!r} maps to unknown role {r!r} (roles: {', '.join(sorted(roles))})")
    return RoleMap({str(g): str(r) for g, r in groups.items()}, tuple(str(g) for g in admin_groups))


def role_map(settings: Settings) -> RoleMap:
    return _load_role_map(_role_map_path(settings))


def _data_role(names: set[str]) -> str | None:
    from kb_core.access.policy import CLASSIFICATIONS, load_roles

    roles = load_roles()
    held = [r for r in roles if r in names]          # file order breaks ties
    if not held:
        return None
    return max(held, key=lambda r: CLASSIFICATIONS.index(roles[r].clearance))


def _one(headers: Mapping[str, str], name: str) -> str | None:
    """The single value of an identity header. A header sent more than once is refused: a gateway that appends its
    header to a client's would otherwise leave two identities in one request."""
    key = name.lower()
    getlist = getattr(headers, "getlist", None)
    values = getlist(key) if getlist is not None else ([headers[key]] if key in headers else [])
    if len(values) > 1:
        raise ApiError("INVALID_PARAM", f"the {name} header appears more than once", param=name)
    return values[0] if values else None


def identify(headers: Mapping[str, str], settings: Settings, subject_param: str | None = None) -> Identity:
    """The identity of a request from its headers (lower-case names, as Starlette gives them). `subject_param` is a
    subject sent outside the headers (page image query, live chat body). Raises ApiError 400 / 401 / 403."""
    if settings.auth_mode == "none":
        from kb_core.access.policy import load_roles

        role = headers.get(SUBJECT_HEADER) or subject_param or None
        if role is not None and role not in load_roles():
            raise ApiError("INVALID_PARAM", f"unknown subject {role!r}", param="X-KB-Subject",
                           allowed=sorted(load_roles()))
        return Identity(user=None, role=role, admin=True)
    if headers.get(SUBJECT_HEADER) or subject_param:
        raise ApiError("INVALID_PARAM", "X-KB-Subject is not accepted: identity comes from the SSO gateway",
                       param="X-KB-Subject")
    user = (_one(headers, settings.auth_user_header) or "").strip()
    if not user:
        raise ApiError("UNAUTHENTICATED", "no authenticated user (the request did not come through the SSO gateway)")
    if "," in user:
        raise ApiError("INVALID_PARAM", "the user header must hold one user", param=settings.auth_user_header)
    raw = (_one(headers, settings.auth_groups_header) or "") if settings.auth_groups_header else ""
    groups = tuple(dict.fromkeys(g.strip() for g in raw.split(",") if g.strip()))
    rm = role_map(settings)
    roles = {rm.groups[g] for g in groups if g in rm.groups}
    admin = any(g in rm.admin_groups for g in groups)
    if not roles and not admin:
        raise ApiError("FORBIDDEN", "the user has no kb-core role (no group maps to one)")
    held = tuple(sorted(roles | ({ADMIN} if admin else set())))
    return Identity(user=user, groups=groups, roles=held, role=_data_role(roles), admin=admin)


def require_admin(identity: Identity) -> None:
    if not identity.admin:
        raise ApiError("FORBIDDEN", "this endpoint needs the admin role")


def require_reader(identity: Identity) -> None:
    if not identity.can_read:
        raise ApiError("FORBIDDEN", "the user has no data role")
