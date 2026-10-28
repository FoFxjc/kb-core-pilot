"""Query templates (design §4.1, §4.2): queries/pg/<ID>_<name>.v<N>.sql and queries/es/<ID>_<name>.v<N>.json.

Code only substitutes parameters; the highest version of a template is used and its id (`<ID>_<name>.v<N>`) goes
into traces with the final SQL / DSL.

- Postgres: `{filters}` becomes `col = ANY(%(f_col)s)` clauses over whitelisted columns (values are bound by the
  driver, see `filter_params`), `{limit}` becomes an integer. Everything else is a bound `%(name)s` parameter.
- Elasticsearch: a JSON string value that is exactly `"{{param}}"` is replaced by the JSON value of that param.
  Every placeholder must be given and no extra params are accepted.
"""

import json
import re
from functools import cache
from pathlib import Path
from typing import Any

from kb_core.paths import data_dir

QUERIES = data_dir("queries")
FILTER_COLUMNS = frozenset({"doc_id", "fiscal_year", "lang", "issuer", "section_type", "is_primary", "tree_source",
                            "node_id", "concept_id", "page_no", "entity_id"})
_VERSIONED = re.compile(r"(?P<name>[A-Za-z0-9]+_[a-z0-9_]+)\.v(?P<v>\d+)\.(sql|json)")
_PLACEHOLDER = re.compile(r"\{\{([a-z_][a-z0-9_]*)\}\}")


class TemplateError(ValueError):
    pass


def clear_cache() -> None:
    _load.cache_clear()


@cache
def _load(kind: str, name: str) -> tuple[str, str]:
    best: tuple[int, Path] | None = None
    for p in (QUERIES / kind).glob(f"{name}.v*.*"):
        m = _VERSIONED.fullmatch(p.name)
        if m and m.group("name") == name and (best is None or int(m.group("v")) > best[0]):
            best = (int(m.group("v")), p)
    if best is None:
        raise TemplateError(f"no {kind} template named {name!r} in {QUERIES / kind}")
    return f"{name}.v{best[0]}", best[1].read_text()


def filter_params(filters: dict[str, list]) -> dict[str, list]:
    return {f"f_{col}": list(values) for col, values in filters.items()}


def pg_query(name: str, filters: dict[str, list] | None = None, limit: int | None = None) -> tuple[str, str]:
    tid, sql = _load("pg", name)
    filters = filters or {}
    bad = sorted(set(filters) - FILTER_COLUMNS)
    if bad:
        raise TemplateError(f"filter column(s) not allowed: {bad}")
    clauses = [f"{col} = ANY(%(f_{col})s)" for col in sorted(filters)]
    if "{filters}" in sql:
        sql = sql.replace("{filters}", " AND ".join(clauses) or "TRUE")
    elif filters:
        raise TemplateError(f"{tid} takes no filters")
    if "{limit}" in sql:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
            raise TemplateError(f"{tid}: limit must be a non-negative int, got {limit!r}")
        sql = sql.replace("{limit}", str(limit))
    return tid, sql


def _substitute(node: Any, params: dict, used: set) -> Any:
    if isinstance(node, dict):
        return {k: _substitute(v, params, used) for k, v in node.items()}
    if isinstance(node, list):
        return [_substitute(v, params, used) for v in node]
    if isinstance(node, str):
        m = _PLACEHOLDER.fullmatch(node)
        if m:
            key = m.group(1)
            if key not in params:
                raise TemplateError(f"missing parameter {key!r}")
            used.add(key)
            return params[key]
    return node


def es_query(name: str, params: dict[str, Any]) -> tuple[str, dict]:
    tid, text = _load("es", name)
    used: set = set()
    body = _substitute(json.loads(text), params, used)
    extra = sorted(set(params) - used)
    if extra:
        raise TemplateError(f"{tid}: unknown parameter(s) {extra}")
    return tid, body
