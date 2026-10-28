"""kb-core doctor (design §9): check the environment item by item. Any `fail` makes `serve` refuse to start.

Checks: configuration, Postgres connection and migration version, ES version (fail below 7.10, warn below 8.0 that
the vector route is unavailable), the kb_ws analyzer, index + alias creation, delivery and store folders, identity
(environment, auth mode, role map) and every enabled model purpose. Reports never contain secrets.
"""

import json
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from kb_core.config import Endpoint, Settings

Level = Literal["ok", "warn", "fail"]
MIN_ES = (7, 10)
VECTOR_ES = (8, 0)


@dataclass
class Check:
    name: str
    level: Level
    detail: str
    fix: str


def _version_tuple(v: str) -> tuple[int, int]:
    major, minor, *_ = (v.split("-")[0] + ".0.0").split(".")
    return int(major), int(minor)


def es_version_check(version: str, licence: str | None = None) -> list[Check]:
    v = _version_tuple(version)
    detail = f"Elasticsearch {version}" + (f", licence {licence}" if licence else "")
    if v < MIN_ES:
        return [Check("es_version", "fail", detail, "kb-core needs Elasticsearch 7.10 or later")]
    if v < VECTOR_ES:
        return [Check("es_version", "warn", detail + "; vector route unavailable (needs 8.0+)",
                      "upgrade to Elasticsearch 8 to use the vector route later; everything else works")]
    return [Check("es_version", "ok", detail, "")]


def _index_check(es, settings: Settings) -> Check:
    """Both aliases point at a physical index (a deleted index drops its alias: a half-finished rebuild or a manual
    delete leaves search broken until the next reindex)."""
    from kb_core.es.indexes import alias_name, alias_targets

    missing, taken = [], []
    for kind in ("node", "page"):
        alias = alias_name(settings, kind)
        if alias_targets(es, alias):
            continue
        if es.request("HEAD", f"/{alias}", allow_404=True) is not None:
            taken.append(alias)
        else:
            missing.append(alias)
    if taken:
        return Check("es_indexes", "fail", f"a concrete index uses the alias name: {taken}",
                     "delete or rename that index (kb-core needs the name for its alias), then run kb-core reindex")
    if missing:
        return Check("es_indexes", "warn", f"alias without an index: {missing}",
                     "run kb-core reindex (search needs both indexes)")
    return Check("es_indexes", "ok", "node and page aliases point at an index", "")


def _es_checks(settings: Settings) -> list[Check]:
    import httpx

    from kb_core.es.client import EsError, es_client
    from kb_core.es.indexes import mapping_file

    es = es_client(settings)
    try:
        return _es_checks_with(es, settings, mapping_file, (EsError, httpx.HTTPError))
    finally:
        es.close()


def _es_checks_with(es, settings: Settings, mapping_file, errors: tuple) -> list[Check]:
    url = settings.redacted()["es_url"]
    try:
        info = es.info()
    except Exception as e:  # connection refused, TLS, auth
        return [Check("es_version", "fail", f"cannot reach {url}: {type(e).__name__}",
                      "check KB_CORE_ES_URL and the ES credentials")]
    licence = None
    try:
        licence = es.request("GET", "/_license").get("license", {}).get("type")
    except errors:
        pass
    out = es_version_check(info["version"]["number"], licence)
    if out[0].level == "fail":
        return out
    probe = f"{settings.index_prefix}doctor_{uuid.uuid4().hex[:8]}"
    alias = probe + "_alias"
    _, body = mapping_file("node")
    try:
        es.request("PUT", f"/{probe}", json=body)
        tokens = es.analyze(probe, "kb_ws", "Doctor CHECK")
        ok = tokens == ["doctor", "check"]
        out.append(Check("es_analyzer", "ok" if ok else "fail", f"kb_ws tokens {tokens}",
                         "" if ok else "the whitespace tokenizer / lowercase filter behave unexpectedly"))
        es.request("POST", "/_aliases", json={"actions": [{"add": {"index": probe, "alias": alias}}]})
        es.request("POST", "/_aliases", json={"actions": [{"remove": {"index": probe, "alias": alias}}]})
        out.append(Check("es_alias", "ok", f"created index {probe}, added and removed alias", ""))
    except errors as e:
        stage = "es_analyzer" if len(out) == 1 else "es_alias"
        out.append(Check(stage, "fail", f"{type(e).__name__}: {e}",
                         f"kb-core needs the right to create indexes and aliases named {settings.index_prefix}*"))
        return out
    finally:
        try:
            es.request("DELETE", f"/{probe}", allow_404=True)
        except errors:
            pass
    try:
        from kb_core.es.indexes import orphan_indexes

        out.append(_index_check(es, settings))
        orphans = orphan_indexes(es, settings)
        if orphans:
            out.append(Check("es_orphans", "warn", f"indexes without an alias: {orphans}",
                             "run kb-core reindex; it removes them"))
    except errors as e:
        out.append(Check("es_indexes", "fail", f"{type(e).__name__}: {e}", "check ES health and permissions"))
    return out


def _pg_checks(settings: Settings) -> list[Check]:
    from kb_core.pg.db import connect
    from kb_core.pg.migrate import current_version, latest_version

    try:
        with connect(settings) as conn:
            have, want = current_version(conn), latest_version()
    except Exception as e:
        return [Check("pg_connect", "fail", f"{type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}",
                      "check KB_CORE_PG_DSN and that the database exists")]
    out = [Check("pg_connect", "ok", "connected", "")]
    if have == want:
        out.append(Check("pg_migrations", "ok", f"version {have} of {want}", ""))
    elif have < want:
        out.append(Check("pg_migrations", "fail", f"version {have} of {want}", "run kb-core migrate"))
    else:
        out.append(Check("pg_migrations", "fail", f"database at version {have}, this kb-core knows {want}",
                         "this kb-core is older than the database; install the matching version"))
    return out


def _folder_checks(settings: Settings) -> list[Check]:
    out = []
    d = settings.delivery_dir
    if d is None:
        out.append(Check("delivery_dir", "fail", "KB_CORE_DELIVERY_DIR is not set (required; there is no default)",
                         "set it to the folder kb-intake delivers packages to"))
    elif d.is_dir() and os.access(d, os.R_OK | os.X_OK):
        out.append(Check("delivery_dir", "ok", f"{d} readable", ""))
    else:
        out.append(Check("delivery_dir", "fail", f"{d} is not a readable folder", "check KB_CORE_DELIVERY_DIR"))
    s = settings.store_dir
    try:
        s.mkdir(parents=True, exist_ok=True)
        probe = s / f".doctor-{uuid.uuid4().hex[:8]}"
        probe.write_text("ok")
        probe.unlink()
        out.append(Check("store_dir", "ok", f"{s} writable", ""))
    except OSError as e:
        out.append(Check("store_dir", "fail", f"{s}: {e}", "check KB_CORE_STORE_DIR"))
    return out


def purpose_check(e: Endpoint, reach: bool = False) -> Check:
    """One enabled model purpose: the key is present and, with `reach`, the endpoint answers GET /models (through
    the purpose's CA bundle and the process's HTTPS_PROXY / NO_PROXY). Model purposes are optional: a problem warns
    and never blocks serve (live chat falls back to replay; the judge and extraction stay off)."""
    import httpx

    name = f"model:{e.purpose}"
    if not e.api_key:
        return Check(name, "warn", f"{e.api_key_var} is not set",
                     f"set {e.api_key_var} (environment or .env), or switch the purpose off")
    where = f"{e.model} at {e.base_url}" + (f" (CA {e.ca_certs})" if e.ca_certs else "")
    if not reach:
        return Check(name, "ok", f"{where}; key present (reachability not checked: doctor --check-endpoints)", "")
    try:
        with httpx.Client(**e.httpx_options()) as client:
            r = client.get(f"{e.base_url}/models", headers={"Authorization": f"Bearer {e.api_key}"})
    except httpx.HTTPError as err:
        return Check(name, "warn", f"{where}: {type(err).__name__}",
                     "check the base URL, the CA bundle, HTTPS_PROXY / NO_PROXY and the network")
    if r.status_code >= 400:
        return Check(name, "warn", f"{where}: HTTP {r.status_code}", "check the key and the base URL")
    return Check(name, "ok", f"{where} answered", "")


def identity_checks(settings: Settings) -> list[Check]:
    """Environment and identity: production with the SSO gateway, or development without identity."""
    if settings.auth_mode == "none":
        return [Check("identity", "warn" if settings.production else "ok",
                      f"KB_CORE_ENV={settings.env}, KB_CORE_AUTH_MODE=none: no identity, demo roles via X-KB-Subject "
                      f"(serving on {settings.host} only)", "")]
    from kb_core.access.identity import role_map

    try:
        rm = role_map(settings)
    except (OSError, ValueError) as err:
        return [Check("identity", "fail", f"role map: {err}", "fix config/access_role_map.yaml (or "
                                                               "KB_CORE_ACCESS_ROLE_MAP)")]
    if not settings.auth_groups_header:
        return [Check("identity", "fail", "KB_CORE_AUTH_GROUPS_HEADER is not set: no user could get a role",
                      "set it to the header the SSO gateway puts the user's groups in")]
    detail = (f"KB_CORE_ENV={settings.env}, identity from the SSO gateway headers {settings.auth_user_header} / "
              f"{settings.auth_groups_header}; {len(rm.groups)} mapped group(s), {len(rm.admin_groups)} admin group(s)")
    return [Check("identity", "ok", detail, "")]


def run_checks(settings: Settings, reach: bool = False) -> list[Check]:
    checks = [Check("config", "ok", "settings loaded", "")]
    checks += identity_checks(settings)
    checks += _pg_checks(settings)
    checks += _es_checks(settings)
    checks += _folder_checks(settings)
    checks += [purpose_check(e, reach) for e in settings.purposes() if e.enabled]
    return checks


def failed(checks: list[Check]) -> list[Check]:
    return [c for c in checks if c.level == "fail"]


def doctor_main(settings: Settings, report: Path | None, reach: bool = False) -> int:
    checks = run_checks(settings, reach)
    for c in checks:
        print(f"{c.level.upper():4} {c.name}: {c.detail}" + (f"\n     what to do: {c.fix}" if c.fix and c.level != "ok" else ""))
    ok = not failed(checks)
    print("doctor: " + ("ready" if ok else f"{len(failed(checks))} check(s) failed"))
    if report is not None:
        report.write_text(json.dumps({"ok": ok, "settings": settings.redacted(), "checks": [asdict(c) for c in checks]},
                                     indent=2, ensure_ascii=False))
    return 0 if ok else 1
