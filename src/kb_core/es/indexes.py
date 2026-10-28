"""Versioned physical indexes behind aliases (design §4.2).

A physical index is `{prefix}{kind}_v{mapping version}_{UTC timestamp}`; queries only use the alias `{prefix}{kind}`.
A rebuild creates a new physical index, loads it, then swaps the alias atomically and deletes every other physical
index of that kind (including orphans left by a rebuild that died before its swap).
"""

import json
import re
import time
from datetime import UTC, datetime
from typing import Literal

from kb_core.config import Settings
from kb_core.es.client import EsClient
from kb_core.paths import data_dir

Kind = Literal["node", "page"]
MAPPINGS = data_dir("es")


def mapping_file(kind: Kind) -> tuple[int, dict]:
    best = max(MAPPINGS.glob(f"{kind}.v*.json"), key=lambda p: int(re.search(r"\.v(\d+)\.json$", p.name).group(1)))
    return int(re.search(r"\.v(\d+)\.json$", best.name).group(1)), json.loads(best.read_text())


def alias_name(settings: Settings, kind: Kind) -> str:
    return f"{settings.index_prefix}{kind}"


def _physical_pattern(settings: Settings, kind: Kind) -> re.Pattern:
    return re.compile(re.escape(f"{settings.index_prefix}{kind}_v") + r"\d+_\d{8}t\d{6}\d*")


def create_physical(es: EsClient, settings: Settings, kind: Kind) -> str:
    version, body = mapping_file(kind)
    while True:
        stamp = datetime.now(UTC).strftime("%Y%m%dt%H%M%S%f")
        name = f"{settings.index_prefix}{kind}_v{version}_{stamp}"
        if es.request("HEAD", f"/{name}", allow_404=True) is None:
            break
        time.sleep(0.001)
    es.request("PUT", f"/{name}", json=body)
    return name


def physical_indexes(es: EsClient, settings: Settings, kind: Kind) -> list[str]:
    pat = _physical_pattern(settings, kind)
    rows = es.request("GET", f"/_cat/indices/{settings.index_prefix}{kind}_v*",
                      params={"format": "json", "h": "index", "expand_wildcards": "all"})
    return sorted(r["index"] for r in rows if pat.fullmatch(r["index"]))


def alias_targets(es: EsClient, alias: str) -> list[str]:
    out = es.request("GET", f"/_alias/{alias}", allow_404=True)
    return sorted(out) if out else []


def orphan_indexes(es: EsClient, settings: Settings) -> list[str]:
    """Physical indexes that no alias points to."""
    out: list[str] = []
    for kind in ("node", "page"):
        live = set(alias_targets(es, alias_name(settings, kind)))
        out += [i for i in physical_indexes(es, settings, kind) if i not in live]
    return out


def swap_alias(es: EsClient, alias: str, new_index: str) -> list[str]:
    """Point alias at new_index only (one atomic _aliases call), then delete the other physical indexes of that kind.
    Returns the deleted index names."""
    prefix_kind = new_index.rsplit("_v", 1)[0]
    old = alias_targets(es, alias)
    actions = [{"remove": {"index": i, "alias": alias}} for i in old if i != new_index]
    actions.append({"add": {"index": new_index, "alias": alias}})
    es.request("POST", "/_aliases", json={"actions": actions})
    rows = es.request("GET", f"/_cat/indices/{prefix_kind}_v*",
                      params={"format": "json", "h": "index", "expand_wildcards": "all"})
    stale = sorted(r["index"] for r in rows if r["index"] != new_index
                   and re.fullmatch(re.escape(prefix_kind) + r"_v\d+_\d{8}t\d{6}\d*", r["index"]))
    for i in stale:
        es.request("DELETE", f"/{i}")
    return stale
