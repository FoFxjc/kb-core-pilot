"""Fact layer: get_metric_series and search's fact results (port of kb service/facts.py; api-contract §5.5, kb D40/D46).

The entity is the issuer whose facts are asked for: with one issuer in the store it is implied; with several, the
optional `issuer` parameter picks one (kb hard-coded its single issuer). Displays follow units.yaml `display`.
"""

from decimal import Decimal
from functools import cache

import yaml

from kb_core.build.concepts import parse_derive
from kb_core.domains import domain_dir
from kb_core.retrieval import context
from kb_core.retrieval.core import ApiError, boolean, enum, ignored_gap, int_list, reject_unknown
from kb_core.retrieval.tracing import traced

PARAMS = {"concept_id", "entity_scope", "fiscal_years", "period_kind", "basis", "as_of", "with_yoy", "include_obs",
          "include_mentions", "issuer"}
FACT_CONCEPTS = 3      # search fact layer: at most 3 concepts written in the query
FACT_YEARS = 3         # latest 3 years when fiscal_years is not given
NEXT_READS = 3


@cache
def _display_rules(domain: str) -> dict:
    return (yaml.safe_load((domain_dir(domain) / "units.yaml").read_text()) or {}).get("display") or {}


def _num(x: Decimal) -> int | float:
    return int(x) if x == x.to_integral_value() else float(x)


def display(value: Decimal, unit: str, raw: str, scale: str) -> str:
    """As written in the source: S$7,587m, S$1.67, 99.0 cents, 17.1%."""
    if unit == "pct":
        return f"{raw}%"
    d = _display_rules(context.current().settings.domain)
    prefix, minor = d.get("currency_prefix", ""), d.get("minor_unit", "")
    s = Decimal(scale)
    if s == Decimal(10) ** 6:
        return f"{prefix}{raw}m"
    if s == Decimal(10) ** 9:
        return f"{prefix}{raw}bn"
    if s == Decimal("0.01"):
        return f"{raw} {minor}"
    return f"{prefix}{raw}"


def _concept(cid: str) -> dict | None:
    rows = context.current().pg_rows("M3_concept", {"concept_id": cid})
    return rows[0] if rows else None


def derivation(cid: str) -> str | None:
    c = _concept(cid)
    return ((c or {}).get("derive") or {}).get("expr")


def _entities(concept_ids: list[str], issuer: str | None) -> list[str]:
    have = [r["entity_id"] for r in context.current().pg_rows("M4_fact_entities", {"ids": concept_ids})]
    if issuer:
        if issuer not in have:
            raise ApiError("INVALID_PARAM", f"no facts for issuer {issuer!r} and these concepts", param="issuer",
                           allowed=have)
        return [issuer]
    if len(have) > 1:
        raise ApiError("INVALID_PARAM", f"facts exist for several issuers {have}; give issuer", param="issuer",
                       allowed=have)
    return have


def _source(r: dict) -> dict:
    return {"doc_id": r["doc_id"], "table_id": r["table_id"], "row_label": r["row_label"],
            "page_range": [r["page_no"], r["page_no"]], "page_label_range": [r["page_label"], r["page_label"]],
            "snippet": r["snippet"]}


def availability(concept_ids: list[str]) -> dict[str, list[int]]:
    deriv = {c: parse_derive(derivation(c) or "") for c in concept_ids}
    need = sorted({x for c in concept_ids for x in ((deriv[c][0], deriv[c][2]) if deriv[c] else (c,))})
    years = {r["concept_id"]: list(r["years"]) for r in context.current().pg_rows("M5_fact_years", {"ids": need})}
    for c in need:            # years backed only by hidden observations are not available to this subject
        ents = [r["entity_id"] for r in context.current().pg_rows("M4_fact_entities", {"ids": [c]})]
        vis = _visible_facts(c, ents) if ents else None
        if vis is not None:
            years[c] = sorted({r["fiscal_year"] for r in vis[0]})
    out = {}
    for c in concept_ids:
        if deriv[c]:
            a, _, b = deriv[c]
            out[c] = sorted(set(years.get(a, [])) & set(years.get(b, [])))
        else:
            out[c] = years.get(c, [])
    return out


def next_for_no_facts(concept_id: str, name: str, fiscal_years: list[int] | None) -> list[dict]:
    cat = context.current().catalog
    picked, years = [], set()
    for t in context.current().pg_rows("M6_concept_tags", {"concept_id": concept_id}):
        doc = cat.docs.get(t["doc_id"])
        if not doc or (fiscal_years and doc["fiscal_year"] not in fiscal_years) or doc["fiscal_year"] in years:
            continue
        years.add(doc["fiscal_year"])
        picked.append({"tool": "read", "params": {"node_id": t["node_id"]},
                       "why": f"section tagged \"{name}\" in the {doc['fiscal_year']} report"})
        if len(picked) >= NEXT_READS:
            break
    query = {"query": name, **({"fiscal_years": fiscal_years} if fiscal_years else {})}
    return picked + [{"tool": "search", "params": query, "why": "search the source text by name"}]


def _validate(p: dict) -> tuple[dict, list[str], list[dict]]:
    reject_unknown(p, PARAMS)
    cid = p.get("concept_id")
    if not isinstance(cid, str) or not cid.strip():
        raise ApiError("INVALID_PARAM", "concept_id is required", param="concept_id",
                       allowed="concept_id (look it up with resolve_concept first if needed)")
    v = {"concept_id": cid.strip().lower(), "fiscal_years": int_list(p, "fiscal_years", 2000, 2100),
         "basis": enum(p, "basis", ["latest", "original", "both"], "latest"),
         "with_yoy": boolean(p, "with_yoy", True), "include_obs": boolean(p, "include_obs", False),
         "issuer": p.get("issuer") if isinstance(p.get("issuer"), str) else None}
    enum(p, "period_kind", ["auto", "duration", "instant"], "auto")
    ignored, gaps = [], []
    if enum(p, "entity_scope", ["group", "bank"], "group") == "bank":
        ignored.append("entity_scope")
        gaps.append(ignored_gap("entity_scope", "facts only have group scope"))
    if p.get("as_of") is not None:
        ignored.append("as_of")
        gaps.append(ignored_gap("as_of", "versions are recorded by report edition, not by date"))
    if p.get("include_mentions"):
        ignored.append("include_mentions")
        gaps.append(ignored_gap("include_mentions", "mentions in body text are not extracted"))
    return v, ignored, gaps


def _compute(op: str, a: Decimal, b: Decimal, percent: bool) -> Decimal | None:
    if op == "/":
        return (a / b * (100 if percent else 1)) if b else None
    return a - b if op == "-" else a + b


def _visible_facts(cid: str, entities: list[str]) -> tuple[list[dict], list[dict]] | None:
    """Facts recomputed from the observations the current subject may see (round 2 W3, T3.5): (M1-shaped rows,
    M2-shaped observation links), or None when every observation is visible (the stored facts apply unchanged)."""
    from kb_core.access import scope
    from kb_core.build.facts import merge

    obs = context.current().pg_rows("M7_concept_observations", {"concept_id": cid, "entities": entities})
    vis = [o for o in obs if scope.visible(o["doc_access"]) and scope.visible(o["table_access"])]
    scope.note_filtered(len(obs) - len(vis))
    if len(vis) == len(obs):
        return None
    by_id = {o["obs_id"]: o for o in vis}
    rows, links = [], []
    for f in merge(vis):
        for v in f["versions"]:
            w = by_id[v["winning_obs_id"]]
            rows.append({"fact_id": f["fact_id"], "entity_id": f["entity_id"], "fiscal_year": f["fiscal_year"],
                         "period_id": f["period_id"], "unit": f["unit"], "restated_note": w["restated_note"],
                         **{k: v[k] for k in ("version_no", "known_from", "known_to", "value", "status", "n_sources")},
                         **{k: w[k] for k in ("doc_id", "table_id", "row_label", "page_no", "page_label", "raw_value",
                                              "raw_scale", "snippet")}})
        for lk in f["links"]:
            o = by_id[lk["obs_id"]]
            links.append({"fact_id": f["fact_id"], "version_no": lk["version_no"], "role": lk["role"],
                          **{k: o[k] for k in ("obs_id", "doc_id", "report_year", "table_id", "page_no", "page_label",
                                               "row_label", "value", "raw_value", "raw_scale", "snippet")}})
    rows.sort(key=lambda r: (r["fiscal_year"], r["version_no"]))
    return rows, links


def _series(cid: str, entities: list[str], with_obs: bool) -> tuple[list[dict], list[dict]]:
    """A concept's fact rows (and observation links when asked) over the current subject's visible observations."""
    vis = _visible_facts(cid, entities)
    if vis is not None:
        return vis[0], (vis[1] if with_obs else [])
    rows = context.current().pg_rows("M1_series", {"concept_id": cid, "entities": entities})
    obs = context.current().pg_rows("M2_obs", {"fact_ids": sorted({r["fact_id"] for r in rows})}) \
        if with_obs and rows else []
    return rows, obs


def _series_rows(cid: str, entities: list[str]) -> list[dict]:
    return _series(cid, entities, False)[0]


def _derived_series(v: dict, known: dict, deriv: str, ignored: list, gaps: list, entities: list[str]):
    a_id, op, b_id = parse_derive(deriv)
    percent = known["value_type"] == "percent"
    inputs = {}
    for cid in (a_id, b_id):
        by: dict[int, list[dict]] = {}
        for r in _series_rows(cid, entities):
            by.setdefault(r["fiscal_year"], []).append(r)
        inputs[cid] = by
    available = sorted(set(inputs[a_id]) & set(inputs[b_id]))
    want = v["fiscal_years"] or available
    bases = ["original", "latest"] if v["basis"] == "both" else [v["basis"]]

    def pick(cid, year, basis):
        vs = inputs[cid].get(year) or []
        return (vs[0] if basis == "original" else vs[-1]) if vs else None

    def value(year, basis):
        a, b = pick(a_id, year, basis), pick(b_id, year, basis)
        return _compute(op, a["value"], b["value"], percent) if a and b else None

    results = []
    for year in [y for y in want if y in available]:
        for basis in bases:
            val = value(year, basis)
            if val is None:
                continue
            prev = value(year - 1, basis)
            ins = [pick(a_id, year, basis), pick(b_id, year, basis)]
            unit = "pct" if percent else ins[0]["unit"]
            item = {
                "tier": "fact", "status": "derived", "concept_id": v["concept_id"], "fiscal_year": year,
                "period": {"period_id": ins[0]["period_id"], "kind": "duration"}, "basis": basis,
                "value": round(float(val), 4), "unit": unit,
                "display": f"{val:.1f}%" if percent else display(val, unit, f"{val / Decimal(10) ** 6:,.0f}", str(10 ** 6)),
                "n_sources": None, "version": None, "restated": False, "original_value": None,
                "restated_note": any(i["restated_note"] for i in ins), "derivation": deriv,
                "inputs": [{"concept_id": cid, "fiscal_year": year, "value": _num(i["value"]), "unit": i["unit"],
                            "display": display(i["value"], i["unit"], i["raw_value"], i["raw_scale"]),
                            "status": i["status"], "n_sources": i["n_sources"], "source": _source(i)}
                           for cid, i in zip((a_id, b_id), ins)],
                "yoy_abs": None, "yoy_pct": None, "yoy_unit": "pp" if percent else unit, "source": None}
            if v["with_yoy"] and prev is not None:
                item["yoy_abs"] = round(float(val - prev), 4)
                if not percent and prev:
                    item["yoy_pct"] = round(float((val - prev) / abs(prev) * 100), 2)
            results.append(item)
    if results:
        latest = max(results, key=lambda r: r["fiscal_year"])
        pages: dict[tuple, list[str]] = {}
        for x in latest["inputs"]:
            pages.setdefault((x["source"]["doc_id"], x["source"]["page_range"][0]), []).append(x["concept_id"])
        gaps.append({"code": "derived", "derivation": deriv,
                     "detail": f"not disclosed directly; computed per year as {deriv}; say it is derived and verify the "
                               "input facts against the source text",
                     "next": [{"tool": "read", "params": {"doc_id": d, "page_range": [p, p]},
                               "why": f"verify {', '.join(c)} for {latest['fiscal_year']}"} for (d, p), c in pages.items()]})
    missing = [y for y in want if y not in available]
    if missing or not available:
        gaps.append({"code": "period_unavailable", "fiscal_years": missing, "available_periods": available,
                     "detail": f"missing input facts needed to compute {deriv}"})
    if any(r["restated_note"] for r in results):
        gaps.append({"code": "restated", "fiscal_years": sorted({r["fiscal_year"] for r in results if r["restated_note"]}),
                     "detail": "figures of the input facts for these years were restated (report footnotes)"})
    if v["include_obs"]:
        ignored = [*ignored, "include_obs"]
    scope = {"filters_applied": {"concept_id": v["concept_id"], "entity_scope": "group", "fiscal_years": v["fiscal_years"],
                                 "basis": v["basis"], "with_yoy": v["with_yoy"]},
             "filters_ignored": ignored, "available_periods": available, "derivation": deriv, "entities": entities,
             "concept": {"concept_id": v["concept_id"], "labels": {"en": known["name_en"], "zh": known["name_zh"]}}}
    return results, scope, gaps, False, {"facts": 0, "derived_from": [a_id, b_id]}


def run_series(params: dict):
    v, ignored, gaps = _validate(params)
    known = _concept(v["concept_id"])
    if known is None:
        from kb_core.retrieval.concepts import nearby, next_for_unknown

        term = v["concept_id"].replace("_", " ")
        cands = nearby(term)
        raise ApiError("INVALID_PARAM", f"unknown concept_id {v['concept_id']!r}", param="concept_id",
                       allowed="resolve the term to a concept_id with resolve_concept first", candidates=cands,
                       next=next_for_unknown(term, cands))
    deriv = (known.get("derive") or {}).get("expr")
    parts = parse_derive(deriv) if deriv else None
    entities = _entities([v["concept_id"], *([parts[0], parts[2]] if parts else [])], v["issuer"])
    if deriv:
        return _derived_series(v, known, deriv, ignored, gaps, entities)
    rows, obs = _series(v["concept_id"], entities, v["include_obs"])
    by_year: dict[int, list[dict]] = {}
    for r in rows:
        by_year.setdefault(r["fiscal_year"], []).append(r)
    available = sorted(by_year)
    want = v["fiscal_years"] or available
    bases = ["original", "latest"] if v["basis"] == "both" else [v["basis"]]

    def pick(year, basis):
        vs = by_year.get(year) or []
        return (vs[0] if basis == "original" else vs[-1]) if vs else None

    results = []
    for year in [y for y in want if y in by_year]:
        for basis in bases:
            r, prev, vs = pick(year, basis), pick(year - 1, basis), by_year[year]
            item = {
                "tier": "fact", "status": r["status"], "concept_id": v["concept_id"], "fiscal_year": year,
                "period": {"period_id": r["period_id"], "kind": "instant" if r["period_id"].startswith("I:") else "duration"},
                "basis": basis, "value": _num(r["value"]), "unit": r["unit"],
                "display": display(r["value"], r["unit"], r["raw_value"], r["raw_scale"]), "n_sources": r["n_sources"],
                "version": {"version_no": r["version_no"], "known_from": r["known_from"], "known_to": r["known_to"]},
                "restated": len(vs) > 1, "original_value": _num(vs[0]["value"]) if len(vs) > 1 else None,
                "restated_note": r["restated_note"], "yoy_abs": None, "yoy_pct": None,
                "yoy_unit": "pp" if r["unit"] == "pct" else r["unit"], "source": _source(r)}
            if v["with_yoy"] and prev is not None:
                item["yoy_abs"] = _num(r["value"] - prev["value"])
                if r["unit"] != "pct" and prev["value"]:
                    item["yoy_pct"] = round(float((r["value"] - prev["value"]) / abs(prev["value"]) * 100), 2)
            if v["include_obs"]:
                item["obs"] = [{k: (_num(o[k]) if k == "value" else o[k]) for k in
                                ("obs_id", "role", "doc_id", "report_year", "table_id", "page_no", "page_label",
                                 "row_label", "value", "raw_value", "snippet")}
                               for o in obs if o["fact_id"] == r["fact_id"] and o["version_no"] == r["version_no"]]
            results.append(item)
    missing = [y for y in want if y not in by_year]
    if not rows:
        gaps.append({"code": "period_unavailable", "fiscal_years": v["fiscal_years"] or [], "available_periods": [],
                     "detail": "this concept has no facts (facts come only from the five-year summary and the MD&A "
                               "overview, about 15 core metrics); use search to find the source text",
                     "next": next_for_no_facts(v["concept_id"], known["name_en"], v["fiscal_years"])})
    elif missing:
        gaps.append({"code": "period_unavailable", "fiscal_years": missing, "available_periods": available,
                     "detail": "these years have no facts; use search to find the source text"})
    if any(r["status"] == "conflict" for r in results):
        gaps.append({"code": "conflict", "detail": "sources within the same report disagree; see include_obs"})
    if any(r["restated"] for r in results):
        gaps.append({"code": "restated", "detail": "a newer report gives a different value; results carry original_value"})
    noted = sorted({r["fiscal_year"] for r in results if r["restated_note"]})
    if noted:
        gaps.append({"code": "restated", "fiscal_years": noted,
                     "detail": "report table footnotes say these years were restated; the reports with the original "
                               "figures are not in the store, so there is no original_value"})
    if any(r["status"] == "single" for r in results):
        gaps.append({"code": "single_source", "detail": "some years have only one source"})
    scope = {"filters_applied": {"concept_id": v["concept_id"], "entity_scope": "group", "fiscal_years": v["fiscal_years"],
                                 "basis": v["basis"], "with_yoy": v["with_yoy"], "include_obs": v["include_obs"]},
             "filters_ignored": ignored, "available_periods": available, "entities": entities,
             "concept": {"concept_id": v["concept_id"], "labels": {"en": known["name_en"], "zh": known["name_zh"]}}}
    return results, scope, gaps, False, {"facts": len(rows)}


def get_metric_series(params: dict, source: str = "http", session_id: str | None = None,
                      subject: str | None = None) -> dict:
    return traced("get_metric_series", params, run_series, source=source, session_id=session_id, subject=subject)


def _derived_fact_results(cid: str, fiscal_years, group_by: str, scope: set, include_snippet: bool) -> list[dict]:
    items, sc, *_ = run_series({"concept_id": cid, "fiscal_years": fiscal_years, "with_yoy": False})
    items = [i for i in items if all(x["source"]["doc_id"] in scope for x in i["inputs"])]
    if not fiscal_years:
        items = items[-FACT_YEARS:]
    cat = context.current().catalog
    out = []
    for i in items:
        first = i["inputs"][0]["source"]
        src = cat.source(first["doc_id"], page_range=first["page_range"], page_labels=first["page_label_range"])
        src.update(table_id=None, row_label=f"derived: {i['derivation']}")
        group = {"fiscal_year": str(i["fiscal_year"]), "doc_id": first["doc_id"], "lang": src["lang"]}.get(group_by)
        out.append({"tier": "fact", "status": "derived", "rank": 0, "score": None, "node_id": None,
                    "title": f"{sc['concept']['labels']['en']} {i['fiscal_year']}: {i['display']} (derived: {i['derivation']})",
                    "concept_id": cid, "fiscal_year": i["fiscal_year"], "value": i["value"], "unit": i["unit"],
                    "display": i["display"], "n_sources": None, "restated": False, "derivation": i["derivation"],
                    "inputs": i["inputs"], "matched": {"fields": ["fact"], "terms": [], "concepts": [{"concept_id": cid}]},
                    "section_type": None, "snippet": first["snippet"] if include_snippet else None,
                    "local_outline": [], "source": src, "parallel_node_id": None, "group": group})
    return out


def fact_results(concept_ids: list[str], fiscal_years: list[int] | None, group_by: str, docs: list[str],
                 include_snippet: bool = True) -> list[dict]:
    """search's fact layer: one result per written concept and year (latest version), provenance from documents in
    this search's scope only (the year's own report first)."""
    ctx = context.current()
    cat = ctx.catalog
    scope = set(docs)
    issuers = sorted({cat.docs[d]["issuer_id"] for d in docs if d in cat.docs})
    out = []
    for cid in concept_ids[:FACT_CONCEPTS]:
        if derivation(cid):
            out += _derived_fact_results(cid, fiscal_years, group_by, scope, include_snippet)
            continue
        rows, support = _series(cid, issuers, True)
        if not rows:
            continue
        name = (_concept(cid) or {}).get("name_en", cid)
        latest = {}
        for r in rows:
            latest[r["fiscal_year"]] = r
        years = [y for y in (fiscal_years or sorted(latest)[-FACT_YEARS:]) if y in latest]
        for y in sorted(years):
            r = latest[y]
            cands = sorted((o for o in support if o["fact_id"] == r["fact_id"] and o["version_no"] == r["version_no"]
                            and o["role"] == "support" and o["doc_id"] in scope),
                           key=lambda o: (o["report_year"] != y, -o["report_year"], o["doc_id"], o["obs_id"]))
            if not cands:
                continue
            o = cands[0]
            src = cat.source(o["doc_id"], page_range=[o["page_no"], o["page_no"]],
                             page_labels=[o["page_label"], o["page_label"]])
            src.update(table_id=o["table_id"], row_label=o["row_label"])
            shown = display(r["value"], r["unit"], o["raw_value"], o["raw_scale"])
            group = {"fiscal_year": str(y), "doc_id": o["doc_id"], "lang": src["lang"]}.get(group_by)
            out.append({"tier": "fact", "status": r["status"], "rank": 0, "score": None, "node_id": None,
                        "title": f"{name} {y}: {shown}", "concept_id": cid, "fiscal_year": y, "value": _num(r["value"]),
                        "unit": r["unit"], "display": shown, "n_sources": r["n_sources"], "restated": r["version_no"] > 1,
                        "matched": {"fields": ["fact"], "terms": [], "concepts": [{"concept_id": cid}]},
                        "section_type": None, "snippet": o["snippet"] if include_snippet else None,
                        "local_outline": [], "source": src, "parallel_node_id": None, "group": group})
    return out
