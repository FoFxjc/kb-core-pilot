# API contract v1 (kb-core)

> Port of kb `docs/api-contract.md` @ `2f6042e` (contract `v1`). The agent-facing contract is unchanged: tool names,
> parameters, defaults, envelope, layers, sources, gap codes, statuses, budgets and the agent rules are kb's
> (sections 3-5, 7, 9 and 10 are carried over verbatim). What changes is storage: Elasticsearch serves the BM25
> routes and hit counts, Postgres holds everything else, and section 6 lists kb-core's templates. Phase labels
> (P1, P2, P3) in the carried-over sections are kb's history; every tool is available in kb-core.
> Field meanings follow `docs/kb-core-design-v1.md` (sections 3-5). References such as "(D40)" point to kb's
> `docs/decisions.md` and "pN-report" to kb's reports; they record where a rule came from.

---

## 1. Principles

1. **Designed from the agent's point of view.** Each tool corresponds to one agent action; each returned object corresponds to a layer of the knowledge model, so the agent can tell at a glance what kind of thing it is and how far it can be trusted.
2. **Deterministic server.** The retrieval service and the MCP layer do not call LLMs or do intent recognition; the same request always gets the same result (except `trace_id`).
3. **Typed parameters, no query language.** The agent can only fill in typed, enumerated parameters; it writes no ES DSL or SQL. Queries exist only in server-side templates (`queries/es/*.json`, `queries/pg/*.sql`).
4. **Uniform response.** Every tool returns the same outer structure: results, scope, gaps.
5. **Additions only.** Within contract `v1`, fields and parameters are only added, never renamed or removed.

---

## 2. Tools and endpoints

| Name | Agent action | Via MCP | HTTP |
|---|---|---|---|
| `search` | Find | Yes | `POST /v1/search` |
| `browse` | View contents | Yes | `GET /v1/docs/{doc_id}/tree` |
| `read` | Read the original | Yes | `GET /v1/read` |
| `resolve_concept` | Match terms | Yes | `POST /v1/resolve_concept` |
| `get_metric_series` | Fetch numbers | Yes | `POST /v1/get_metric_series` |

These are kb's routes as served (kb's own section 2 table still showed the earlier GET forms for `resolve_concept` and
`get_metric_series`; kb's service and supplement log use POST). Admin endpoints are in section 8; they are used only
by the UI and evaluation and are not MCP tools. Documents enter through `kb-core import` (contract v2 delivery
packages), not through an upload API.

---

## 3. General conventions

- **Encoding**: requests and responses are UTF-8 JSON. `search` uses POST + JSON body; the rest use GET + query parameters, with array parameters as repeated keys (`fiscal_years=2024&fiscal_years=2025`).
- **Version**: every response carries `"contract": "v1"`.
- **`read`'s `page_range` over GET** (kb-core): repeated keys (`page_range=98&page_range=100`) as above, or one value
  `98-100` / `98,100`.
- **Page numbers**: every `page_no` is a physical page (starting at 1); the printed page is in `page_label`.
- **Language**: the `lang` parameter filters by **document language**, not question language. A Chinese question can hit English documents.
- **Errors**: HTTP status code + `{"contract": "v1", "error": {"code", "message", "details"}}`. The MCP layer converts them into tool errors (`isError=true`), keeping `code`.

| code | HTTP | When | details |
|---|---|---|---|
| `INVALID_PARAM` | 400 | Wrong type, value outside the enum, out of range (e.g. `page_range` over 5 pages); `X-KB-Subject` sent behind the SSO gateway | `param`, `allowed` |
| `UNAUTHENTICATED` | 401 | Behind the SSO gateway (auth mode `trusted_header`): the request carries no gateway user. Never served as `public` | |
| `FORBIDDEN` | 403 | Behind the SSO gateway: the user has no mapped role, a data call without a data role, or an admin endpoint without the admin role | |
| `UNKNOWN_DOC` | 404 | doc_id does not exist | `candidates` |
| `UNKNOWN_NODE` | 404 | node_id does not exist or does not belong to the document | |
| `UNKNOWN_CONCEPT` | 404 | concept_id does not exist (from P2) | `candidates`: the closest alias matches |
| `LAYER_UNAVAILABLE` | 409 | A layer was requested that the document or the current phase does not yet have | `available_layers` |
| `NOT_FOUND` | 404 | The endpoint does not exist, or the source_id / run_id in an admin API does not exist | |
| `METHOD_NOT_ALLOWED` | 405 | The endpoint exists but the method is wrong | `allowed` |
| `INTERNAL` | 500 | | `trace_id` |

All HTTP-layer errors (including the framework's own parameter validation failures) use the structure above, not the framework's default error format.

- **Caller identity** (enterprise readiness; `src/kb_core/access/identity.py`, `docs/deploy.md`). Two modes,
  `KB_CORE_AUTH_MODE`:
  - `none` (development only): no user. `X-KB-Subject` (a role in `config/access_roles.yaml`; on page images also the
    `subject` query parameter, on live chat the `subject` body field) picks the role a call runs as; missing = `public`.
  - `trusted_header` (required in production): the SSO gateway sets the user header (`KB_CORE_AUTH_USER_HEADER`) and
    the groups header (`KB_CORE_AUTH_GROUPS_HEADER`, comma-separated); groups map to roles in
    `config/access_role_map.yaml`. Calls run as the user's data role with the highest clearance. Every request,
    MCP included, is checked before any route runs: no user is `UNAUTHENTICATED`; `X-KB-Subject` (or `subject`) is
    `INVALID_PARAM`; no mapped role is `FORBIDDEN`; `/v1/admin/*` needs the admin role (from `admin_groups`), data
    tools and MCP need a data role. The access audit records the user with each call.

Empty results and truncated output are **not errors**; they show up in the response's `scope` and `gaps`.

---

## 4. Uniform response

```json
{
  "contract": "v1",
  "tool": "search",
  "results": [],
  "scope": {
    "filters_applied": {"lang": "any", "fiscal_years": [2023, 2024, 2025], "doc_ids": null},
    "filters_ignored": ["entity_scope"],
    "doc_count": 2,
    "docs": [
      {"doc_id": "ocbc-group_ar_2025_en", "lang": "en", "fiscal_year": 2025, "completeness": "full"},
      {"doc_id": "ocbc-group_ar_2025_zh", "lang": "zh", "fiscal_year": 2025, "completeness": "partial"}
    ],
    "hit_counts": {"fiscal_year": {"2025": 14}, "lang": {"en": 11, "zh": 3}, "section_type": {"notes": 6, "md_a": 4}},
    "hit_counts_unfiltered": {"fiscal_year": {"2023": 9, "2024": 12, "2025": 14}},
    "available_periods": [2025],
    "query_terms": ["npl", "ratio"]
  },
  "gaps": [
    {"code": "section_missing_in_lang", "severity": "warn", "lang": "zh", "section_types": ["md_a"], "detail": "the Chinese edition is an excerpt without the management discussion"}
  ],
  "truncated": false,
  "next": null,
  "trace_id": "tr_01J..."
}
```

### 4.1 Fields

| Field | Notes |
|---|---|
| `results` | Tool-specific entries, each carrying `tier`, `status`, `source` |
| `scope.filters_applied` | The filters actually applied (including defaults) |
| `scope.filters_ignored` | Parameters that do not take effect in the current phase and were ignored |
| `scope.docs` | Documents within this retrieval's scope |
| `scope.hit_counts` | Hit counts per dimension after filtering |
| `scope.hit_counts_unfiltered` | Hit counts with the agent-specified `fiscal_years` and `lang` filters removed, used to judge over-filtering |
| `scope.available_periods` | In P1/P2, the report years in the library; from P3, the periods with facts for that concept and entity |
| `scope.query_terms` | `search` only: the tokens actually searched after tokenizing the query (and, from P1, alias expansion), so the agent can judge whether to rephrase |
| `scope.query_term_sources` | `search` only: one-to-one with `query_terms`, elements `{term, source: "query" \| "alias", alias_id, variant}`, stating whether each token came from the question itself or from alias expansion (D30) |
| `scope.query_concepts` | `search` only (P2-2): concepts recognized in the query and their broader expansion, elements `{concept_id, via: "query" \| "broader", from, variant}`; separate from `query_terms`, as the concept route searches by concept_id, not by token. `resolve_concept` result entries are concept cards with no `source` |
| `gaps` | List of gaps, see 4.4 |
| `truncated`, `next` | true when output was truncated; `next` gives a handle to continue reading. `next` itself is a valid set of call parameters (`read` no more than 5 pages); when the node's remainder exceeds 5 pages, `next.remaining_page_range` is also given |
| `trace_id` | The corresponding trace event, which the UI uses to replay this step |

### 4.2 Layer `tier`

| tier | Meaning | How the agent uses it | Phase |
|---|---|---|---|
| `fact` | Canonical fact (knowledge model L5) | Can be cited directly, stating status and version; facts in this library are extracted only from financial highlights and MD&A tables, so the original must still be read before citing (rule 10) | Fact layer (D40) |
| `link` | Link hit: node concept tag or mention (L6) | Can serve as a basis for locating; the original must still be read before citing numbers | P2 |
| `structure` | Node title hit (L3 table-of-contents tree) | A lead; section location is fairly accurate | P1 |
| `text` | Summary, page body or vector hit (L3) | A lead; must be checked against the original | P1 |

### 4.3 Source `source`

Every result carries:

```json
{"doc_id": "ocbc-group_ar_2025_en", "lang": "en", "fiscal_year": 2025,
 "node_id": "ocbc-group_ar_2025_en:toc_flash:0143",
 "title_path": ["Notes to the Financial Statements", "32. Risk management", "32.3 Credit risk"],
 "page_range": [186, 189], "page_label_range": ["184", "187"],
 "source_url": "https://www.ocbc.com/group/investors/annual-report-and-agm"}
```

### 4.4 Gap codes

Additions only, no changes. Each gap carries a `severity`:

| severity | Meaning | How the agent uses it |
|---|---|---|
| `info` | A notice, does not affect the conclusion | May be left unmentioned |
| `warn` | May affect the conclusion | State it in the answer |

In P1, `param_ignored` and `parallel_doc_available` are `info`; the rest are `warn`.

| code | Meaning | Phase |
|---|---|---|
| `param_ignored` | A parameter does not take effect in the current phase | P1 |
| `empty_scope` | No documents remain after filtering | P1 |
| `over_filtered` | 0 hits after filtering, but hits without the filters | P1 |
| `section_missing_in_lang` | A language version does not contain the queried or filtered section | P1 |
| `parallel_doc_available` | A hit document has a version in another language | P1 |
| `tree_quality_low` | The primary-tree spot check of a hit document is below 85% | P1 |
| `page_label_unreliable` | The printed page number was inferred with low confidence | P1 |
| `truncated` | Output was truncated | P1 |
| `concept_unknown` | No concept could be resolved from the query (`info`; also given when `resolve_concept` does not recognize a term) | P2 |
| `unlinked_text_only` | A concept was resolved, but the returned results contain no link layer (`info`) | P2 |
| `layer_unavailable` | A hit document only reached degraded acceptance | P2 |
| `period_unavailable` | No facts for the requested period | P3 |
| `single_source` | The fact has only one source | P3 |
| `conflict` | Observations disagree | P3 |
| `restated` | The current version differs from the original value | P3 |
| `derived` | The value is derived from input facts by a domain-pack formula and is not disclosed directly in the annual report (`info`) | D46 |

**`next` (D46)**: a gap can carry `next: [{tool, params, why}]`, the suggested next call, not a requirement; it does not count against the output budget. Gaps that currently give `next`: `concept_unknown` from `resolve_concept` (similar concepts in `candidates`: `contained` means a phrasing of it appears in full in the term, and only these get a call; `partial` are only listed for confirmation; `concept_unknown` produced by search carries no `next`), `period_unavailable` (when there are no facts, read the sections tagged with the concept, search by name), `section_missing_in_lang` (query the other language version instead), `over_filtered` (rerun without filters), `derived` (read the original pages of the input facts). When `get_metric_series` receives an unknown concept_id, the error's `details` likewise gives `candidates` and `next`.

### 4.5 Status `status`

Link-type results take `linked` / `ambiguous` / `unlinked` / `conflict` / `excluded`; the `structure` and `text` layers are always `unlinked`; facts take `agreed` / `single` / `conflict`.

---

## 5. Tool contracts

### 5.1 `search`: find

**Parameters**

| Parameter | Type | Default | Values and validation | Effective from |
|---|---|---|---|---|
| `query` | string | Required | 1–200 characters | P1 |
| `lang` | enum | `any` | `any` \| `en` \| `zh` | P1 |
| `fiscal_years` | int[] | No filter | Each 2000–2100; values outside the library's range do not raise errors | P1 |
| `doc_ids` | string[] | No filter | Must exist | P1 |
| `section_types` | enum[] | No filter | `doc_type_vocab` vocabulary | P1 (after the vocabulary is confirmed) |
| `group_by` | enum | `none` | `none` \| `fiscal_year` \| `doc_id` \| `lang` \| `section_type` | P1 |
| `per_group` | int | 3 | 1–10; effective only when `group_by≠none` | P1 |
| `limit` | int | 10 | 1–30 | P1 |
| `include_snippet` | bool | true | When false, `snippet` is not returned | P1 |
| `entity_scope` | enum | `any` | `any` \| `group` \| `bank` | P2; ignored in P1 |
| `concepts` | string[] | Resolved from query | concept_id | P2; ignored in P1 |
| `doc_type` | enum | `annual_report` | Registered types and types actually present in the library (unregistered types are searchable after ingestion through the generic profile, D43); the MCP enum lists only registered types | P1; extension-seams round |

**Result entry**

```json
{
  "tier": "structure", "status": "unlinked", "rank": 1, "score": 0.083,
  "node_id": "ocbc-group_ar_2025_en:toc_flash:0143",
  "title": "32.3 Credit risk",
  "section_type": "notes",
  "matched": {"fields": ["title_tok", "page_text_tok"], "terms": ["credit", "risk"], "concepts": []},
  "snippet": "Non-performing loans ratio 0.9% (2024: 0.9%) …",
  "local_outline": ["32. Risk management", "  32.2 Market risk", "> 32.3 Credit risk", "  32.4 Liquidity risk"],
  "source": {"doc_id": "…", "lang": "en", "fiscal_year": 2025, "page_range": [186, 189], "page_label_range": ["184", "187"], "…": "…"},
  "parallel_node_id": null,
  "group": "2025"
}
```

- `score`: RRF fusion score, only for the `structure` and `text` layers; null for the `link` layer, which is ordered by deterministic rules
- `local_outline`: the hit node's parent and siblings, with `>` marking the hit node, at most 12 lines
- `group`: the group it belongs to when `group_by≠none`
- `fact_card` (P3, at the same level as `results`): given when a concept resolved from the query has data in the fact layer, suggesting `get_metric_series` instead; always null in P1 and P2

**Ordering and quotas**

1. Each node appears only once, keeping its highest layer; hits from several routes are merged into `matched.fields`
2. Order first by layer (`fact_card` > `link` > `structure` > `text`), then by score within a layer
3. When `group_by≠none`, each group is guaranteed its top `per_group` entries (all of them if the group has fewer hits), then the rest is filled to `limit` in global order; the total may slightly exceed `limit`, capped at `number of groups × per_group`

### 5.2 `browse`: view contents

| Parameter | Type | Default | Values and validation |
|---|---|---|---|
| `doc_id` | string | Required | Must exist |
| `node_id` | string | Root | Must belong to the document |
| `depth` | int | 2 | 1–6, number of levels expanded from `node_id` |
| `tree_source` | enum | Primary tree | `toc_flash` \| `pageindex_flash` \| `en_mapped` \| `pageindex_llm` \| `bookmark`, for comparison |

Result entries (pre-order traversal): `{tier: "structure", node_id, parent_id, depth, ord, title, section_type, page_range, page_label_range, child_count, concept_ids(P2), parallel_node_id(P2)}`.

`scope` additionally gives: `tree_source`, `tree_sample_accuracy` (spot-check accuracy), document metadata. When the output budget is exceeded, one level of expansion is removed automatically and `truncated` is set.

The MCP layer renders results as indented text, one line each: `[last 4 of node_id] title (physical pages s-e / printed pages s-e) {section_type}` (kb emitted Chinese labels here; kb-core emits these English ones).

### 5.3 `read`: read the original

| Parameter | Type | Default | Values and validation |
|---|---|---|---|
| `node_id` | string | — | Either this or `doc_id + page_range` |
| `doc_id`, `page_range` | string, [int, int] | — | Closed interval of physical pages, span ≤ 5 pages |
| `include_tables` | bool | true | Attach the page's table blocks (Markdown) |
| `include_images` | bool | false | Attach page images (PNG, long edge ≤ 1,280 px) |
| `max_chars` | int | 40,000 | 5,000–60,000, text budget |

Result entries (one per page): `{tier: "text", page_no, page_label, page_label_source, text, tables: [{table_id, markdown}], image?, nodes_covering: [node_id]}`.

- When reading by `node_id` and the node exceeds 5 pages, only the first 5 are returned and `next` gives the remaining page range: `{"doc_id": "…", "page_range": [191, 195]}`
- When text exceeds `max_chars`, pages are dropped from the last page backwards, and `next` is adjusted accordingly

### 5.4 `resolve_concept`: match terms (P2)

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `term` | string | Required | A term in any language, or a concept_id |
| `lang_hint` | enum | `any` | `any` \| `en` \| `zh` |
| `limit` | int | 5 | |

Result entry: `{tier: "link", concept_id, labels: {en, zh}, aliases: {en: [], zh: []}, value_type, aggregation, parents, children, variants, match: "exact"|"alias"|"prefix", node_count, has_facts(P3), available_periods(P3)}`.

Matching is deterministic: exact match on normalized aliases → prefix match. No fuzzy matching or vectors.

P2-2 implementation (p2b-report): HTTP is `POST /v1/resolve_concept`; `match` is `exact` (concept_id, case-insensitive), `alias`, `prefix` (alias or concept_id prefix); `lang_hint` is only a preference, and when nothing matches in the specified language it falls back to all languages (`scope.lang_fallback`); result cards also contain `components` (the parts under `component_of`) and `status = linked`; `parents` / `children` come from `broader`, `variants` from `variant_of` (both directions); `node_count` is the number of primary-tree nodes tagged with the concept; when unrecognized, `results` is empty and `concept_unknown` (`info`) is given.

### 5.5 `get_metric_series`: fetch numbers (fact layer, D40)

Fact-layer implementation (D40): HTTP is `POST /v1/get_metric_series`; group basis only; `as_of`, `include_mentions` and `entity_scope=bank` return `param_ignored`; `period_kind` is accepted but the concept default is used; `known_from` / `known_to` are annual-report fiscal years; `source` also contains `table_id`, `row_label`, `snippet`; the YoY base period is the previous year's fact in the library (even if outside the requested years); ratio-type metrics (`unit = pct`) give only `yoy_abs` (percentage points, `yoy_unit = "pp"`), not `yoy_pct`; `obs` is given only with `include_obs`, and `mentions` are not given; `restated_note = true` means a footnote in the annual report says that year's figure was restated but the original annual report is not in the library (the `restated` gap is also given); search's `fact` layer covers at most 3 concepts × 3 years each time, sources are taken only from documents in the retrieval scope, it does not count against `limit` or the output budget, and gaps are computed only from evidence results; when a concept has no facts or a year is missing, `period_unavailable` (warn) is given, `conflict` is warn, and `restated` and `single_source` are info. A nonexistent concept_id returns 400, suggesting `resolve_concept` first.

| Parameter | Type | Default | Notes | Implementation status (D40) |
|---|---|---|---|---|
| `concept_id` | string | Required | | Nonexistent → 400 `INVALID_PARAM`, suggesting `resolve_concept` first |
| `entity_scope` | enum | `group` | `group` \| `bank` | Group basis only; `bank` returns `param_ignored` |
| `fiscal_years` | int[] | All available | For growth rates the agent fetches one extra base period itself | Effective; missing years give `period_unavailable` |
| `period_kind` | enum | `auto` | `auto` (concept default) \| `duration` \| `instant` | Accepted, concept default used |
| `basis` | enum | `latest` | `latest` (current version) \| `original` (earliest version) \| `both` | Effective; `both` gives two entries per year |
| `as_of` | date | Not specified | Returns the version valid on that date | Not supported (no publication dates), returns `param_ignored` |
| `with_yoy` | bool | true | Year on year | Effective; base period is the previous year's fact in the library; ratio-type metrics give only `yoy_abs` (percentage points) |
| `include_obs` | bool | false | Attach every observation supporting the version | Effective |
| `include_mentions` | bool | false | Attach sentences in body text that cite the fact | Not supported (body-text mentions not extracted), returns `param_ignored` |
| `issuer` | string | the only issuer with facts | kb-core addition: the issuer whose facts are returned; needed only when facts exist for several issuers (kb hard-coded its single issuer). An issuer without facts for the concept returns `INVALID_PARAM` with `allowed` | Effective |

Result entry (one per period × basis; below is a real response from 2026-10-19, with only one `obs` listed):

```json
{"tier": "fact", "status": "agreed", "concept_id": "net_profit", "fiscal_year": 2024,
 "period": {"period_id": "D:2024-01-01:2024-12-31", "kind": "duration"},
 "basis": "latest", "value": 7587000000, "unit": "SGD", "display": "S$7,587m", "n_sources": 4,
 "version": {"version_no": 1, "known_from": 2024, "known_to": null},
 "restated": false, "original_value": null, "restated_note": false,
 "yoy_abs": 566000000, "yoy_pct": 8.06, "yoy_unit": "SGD",
 "source": {"doc_id": "ocbc-group_ar_2024_en", "table_id": "ocbc-group_ar_2024_en:t0006_01",
            "row_label": "Net profit attributable to equity holders of the Bank",
            "page_range": [6, 6], "page_label_range": ["4", "4"],
            "snippet": "Net profit attributable to equity holders of the Bank 3,586 4,858 5,526 7,021 7,587 …"},
 "obs": [{"obs_id": "ocbc-group_ar_2024_en:t0006_01:r06:c4", "role": "support", "doc_id": "ocbc-group_ar_2024_en",
          "report_year": 2024, "table_id": "ocbc-group_ar_2024_en:t0006_01", "page_no": 6, "page_label": "4",
          "row_label": "Net profit attributable to equity holders of the Bank", "value": 7587000000,
          "raw_value": "7,587", "snippet": "…"}]}
```

Differences from the design draft: `known_from` / `known_to` are annual-report fiscal years (int) rather than dates; `concept_id`, `restated_note` and `yoy_unit` are added, and `source` gains `snippet`; there are no `mentions`. `display` follows the original's form: amounts `S$7,587m`, per share `S$1.67`, dividends `99.0 cents`, ratios `17.1%`.

**Admin APIs for viewing the provenance chain** (write no traces; used by V7 and V3): `GET /v1/admin/facts` (concepts with facts, each with years, latest value and status distribution); `GET /v1/admin/facts/{concept_id}` (all fact versions per year, each with all its observations: role, document, language, edition year, page, table, original form, snippet); `GET /v1/admin/docs/{doc_id}/pages/{page_no}/facts` (observations on that page and the status of the facts they belong to).

---

## 6. Execution logic: the query compiler

### 6.1 Seven steps

| Step | What it does | Storage involved |
|---|---|---|
| 1. Validate | Types, enums, ranges; fill in defaults; record ignored parameters | — |
| 2. Preprocess | Tokenize (the build's tokenizer: jieba for Chinese, lower-cased words otherwise); resolve concepts and add Chinese and English aliases | Postgres (concept tables) |
| 3. Plan | Decide the retrieval routes and grouping, generate a list of query tasks | — |
| 4. Compile | Render each task's template with its parameters | — |
| 5. Execute | Run each route, collect its ranking | Elasticsearch (BM25 routes, concept match, hit counts); Postgres (facts) |
| 6. Post-process | Coverage gate (IDF from page document frequencies); map each page hit to one node (the first deepest covering node in reading order; kb maps it to every covering node); weighted RRF (k=60); layers fact > link > structure > text; link cap per group; group quotas; local outlines; hit distributions; gaps | In-memory catalog |
| 7. Render | Assemble the uniform response; enforce the output budget (facts outside it) | — |

**Catalog**: document metadata, each document's primary tree, page document frequencies and concept tags are loaded
from Postgres at service start (`G0`-`G4`) and refreshed after a rebuild. `browse`, local outlines and page-to-node
mapping do not query storage.

### 6.2 Templates

Templates are files named `<ID>_<name>.v<N>.json|sql`; the highest version of an id is used. ES templates take
whole-value `"{{param}}"` substitution (filters are rendered as ES filter clauses); PG templates use bound parameters
(`%(name)s`), and list filters render as `col = ANY(%(f_col)s)`.

Elasticsearch (`queries/es/`), against the aliases `{prefix}node` and `{prefix}page`:

| Template | Tool | Shape |
|---|---|---|
| `S1 node_title_bm25` | search | `match` on `title_tok`, filters in `bool.filter`, sorted by score then node_id |
| `S2 node_summary_bm25` | search | Same on `summary_tok` |
| `S3 page_text_bm25` | search | Same on page `text_tok` |
| `S4 hit_counts` | search | `match` as a filter, terms aggregations by year and language, no scoring |
| `S4b hit_pages` | search | Hit pages (filter, no scoring), mapped to nodes and counted by `section_type` |
| `S5 hit_counts_unfiltered` | search | `S4` without year and language filters |
| `S6 node_concept_match` | search | `terms` on `concept_tok` (link layer), no scoring |
| `D03 delete_doc` | reindex `--doc` | Delete one document's rows from both indexes |

Postgres (`queries/pg/`), used by the tools:

| Template | Tool | Purpose |
|---|---|---|
| `R1 pages_range`, `R2 tables_range`, `R3 document_package` | read | Page text, table blocks (with boxes), the stored package for page images |
| `K1 alias_exact`, `K2 alias_prefix`, `K3 concept_cards`, `K4 concept_edges` | resolve_concept, search | Alias matching and concept cards with broader/narrower edges |
| `M1 series`, `M2 obs`, `M3 concept`, `M4 fact_entities`, `M5 fact_years`, `M6 concept_tags` | get_metric_series, search fact layer | Fact versions per period, observations, concept metadata, entity and year availability, tagged sections as next steps |

Internal templates (catalog, tracing, build, import, evaluation):

| Template | Purpose |
|---|---|
| `G0 documents`, `G1 tree_nodes`, `G2 page_tokens`, `G3 node_concepts`, `G4 coverage` | Catalog load (section 6.1) and `tree_quality_low` |
| `G5 trace_insert`, `G6 gap_insert` | Trace events and the gap log (section 10) |
| `I01`-`I05` | Package import and registration |
| `B01`-`B13`, `C01`-`C05`, `F01`-`F05` | Build (tree, pages, regions, tables, tags, observations), concept import, fact merge |
| `D01 nodes_for_index`, `D02 pages_for_index` | Reindex reads Postgres only |
| `V1`-`V4` | Evaluation sheets, eval runs and results |

### 6.3 Rules

1. **Queries exist only in templates.** One file per template and version; no other code contains ES DSL or SQL
   strings.
2. **User text never goes into a query as syntax.** Query terms go through the tokenizer and are passed as values: ES
   `match` text or bound SQL parameters.
3. **Every query actually executed is written into the trace event** with its template id and final DSL or SQL and
   parameters, shown in the UI's retrieval trace view.
4. **Reindex reads Postgres only.** ES indexes are versioned physical indexes behind aliases; a reindex builds new
   ones and switches the aliases, so search results do not depend on index history.

---

## 7. MCP layer

- `MCPServer` and `@mcp.tool()` from the official MCP Python SDK v2 (`mcp>=2.3,<3`); Streamable HTTP mounted at `/mcp` in the same process as the HTTP API (`streamable_http_app(host=...)`, so the SDK's DNS-rebinding protection allows the configured host).
- Tool names and parameters map one-to-one to HTTP and are passed through; HTTP responses are returned as structured content as is. `browse` also attaches indented text.
- The MCP layer contains no retrieval logic.
- A single output respects the budget in section 9 (a typical MCP client's default cap on a single tool output is about 25k tokens, images included).

### 7.1 Rules for the agent in tool descriptions

Every tool description contains the following rules (the relevant part per tool):

1. The `text`, `structure` and `link` layer results you get are leads; before citing any number in them, read the original with `read`. Page numbers in search results are only leads and cannot be used directly as sources; if you mention a page you have not read, state "not read" explicitly and attach no number.
2. When citing a number, also give the source (document, physical page and printed page), in the uniform form "(ocbc-group_ar_2025_en, physical page 105, printed page 103)"; from P3, also give the status (consistent / single-source / conflicting) and version.
3. When results are empty or few, check `scope.hit_counts_unfiltered` and `gaps` before concluding "not there".
4. Relay in the answer the gaps in `gaps` relevant to the question, e.g. "the Chinese edition does not include the management discussion".
5. Convert relative time such as "the past three years" relative to the latest period in `scope.available_periods`; growth rates need one extra base period.
6. `lang` filters by document language. For questions asked in Chinese, the English annual reports often have more complete content.
7. Write units and currencies of amounts and ratios as in the original (`$` in OCBC annual reports is Singapore dollars; do not write US dollars); do not add comparisons, causes, evaluations or external data not in the original (D33, D35).
8. When a language version lacks a needed section, besides switching to the other language version, also point out the closest alternative content in the same language version (e.g. when the Chinese version has no MD&A, point out the CFO review).
9. For `read`, give either `node_id` or `page_range`; do not pass `null` for omitted optional parameters.
10. For values and trends, use `get_metric_series` first (or look at the `fact` layer in search results); its values carry sources, but still read the original with `read` before citing; also state the fact status and any restatement (fact layer, D40).
11. `next` in a gap is the suggested next call; when stuck, follow it first, do not guess concept_id and do not repeat the same call; when a term is not recognized, look at `candidates`. A value with status `derived` is computed by formula; when citing it, say it is derived, and check against the original via the sources of the input facts (D46).

---

## 8. Admin APIs (HTTP only)

| Endpoint | Request | Response |
|---|---|---|
| `GET /v1/admin/config` | None | What the UI may offer: `llm_enabled` (any model purpose on), `live_chat` (true when live chat is configured), `mode` (`live` / `replay`), `role_picker` (true only in auth mode `none`) |
| `GET /v1/admin/chat/status` | None | `enabled`, `reason` when not, `model`, `max_tool_calls`, `busy`, `calls_used` (model call ledger), `budget_calls` |
| `POST /v1/admin/chat` | `message` (1-2000 characters), optional `session_id` (from an earlier turn); `subject` only in auth mode `none` | Server-sent events of one turn (8.1) |
| `GET /v1/admin/replays` | None | Recorded MCP sessions (`eval/results/mcp_demo_*.yaml`): questions, the agent's answer, tool calls with trace ids |
| `GET /v1/admin/docs` | None | Imported documents: doc_id, language, fiscal year, package, build status, primary-tree source and spot-check accuracy |
| `POST /v1/admin/import` | `path` (a package or delivery folder on the server) | Per-package result, as `kb-core import` |
| `GET /v1/admin/runs` | `doc_id`, `stage`, `limit` | Import, build and fact runs with counts and errors |
| `GET /v1/admin/traces` | `from`, `to`, `tool`, `source`, `session_id`, `limit`, `cursor` | Trace events newest first; `next_cursor` gives the next page |
| `GET /v1/admin/traces/{trace_id}` | None | One trace: input, compact results, scope, gaps, the templates executed with their DSL or SQL, route rankings, coverage decisions |
| `GET /v1/admin/sessions/{session_id}` | None | The calls of one session in time order (chat replay) |
| `GET /v1/admin/evals` | `kind`, `limit` | Evaluation runs with their summary (recall: with year, without year, cross-year) |
| `GET /v1/admin/docs/{doc_id}/nodes` | None | The complete primary tree with concept tags (UI document view) |
| `GET /v1/docs/{doc_id}/pages/{page_no}.png` | None | Page image rendered from the stored `source.pdf`, cached in the store |
| `GET /v1/docs/{doc_id}/pages/{page_no}/regions` | None | Regions on the page with types, boxes (PDF coordinates) and the covering nodes |

### 8.1 Live chat (round 2)

The server runs the agent loop (ported from kb's live mode, D25) against a chat-completions-compatible
endpoint: the chat purpose (`KB_CORE_CHAT_BASE_URL`, `KB_CORE_CHAT_MODEL`, `KB_CORE_CHAT_API_KEY_VAR`,
`KB_CORE_CHAT_CA_CERTS`, `KB_CORE_CHAT_TIMEOUT_S`), each falling back to the default endpoint (`KB_CORE_LLM_*`);
`KB_CORE_CHAT_ENABLED=true` turns it on. The chat runs as the caller's identity (section 3); a session belongs to the
user who started it (another user gets `NOT_FOUND`, as for a missing session) and keeps its role. The tools, their descriptions and schemas are the MCP server's; tool calls are
traced with source `chat` and the server-generated `session_id` (`chat_<32 hex>`). Answers are always in English (system prompt), whatever the language of the question or the sources.

- **Limits:** at most `KB_CORE_CHAT_MAX_TOOL_CALLS` (default 8) tool calls per session, counted across turns; every
  tool result tells the model how many remain. At most `max + 2` model calls per turn. One live session at a time
  (a request made while a turn is running gets `LAYER_UNAVAILABLE`, 409, at once; a claimed turn whose stream never started is freed after 60 s). `KB_CORE_CHAT_BUDGET_CALLS` caps all model calls, counted from the
  ledger `<store>/chat/model_calls.jsonl` (one line per call, failed calls included; no key, no content).
- **Errors before streaming** (disabled, invalid `message` or `session_id`, unknown session, busy) are normal error
  responses (section 3). Once streaming starts, a failure arrives as an `error` event followed by `answer`.
- **Events**, in order: `session` (`session_id`, `model`, `tool_calls_used`, `max_tool_calls`); then any of
  `thinking` (reasoning the model exposed, truncated to 600 characters), `text` (notes before tool calls), `tool_call`
  (`n`, `tool`, `input`) and `tool_result` (`n`, `tool`, `status`, `trace_id`, `ms`, a summary; or `skipped` with
  `reason` `limit` / `invalid arguments`); then `error` (`message`, `trace_id`) when the turn failed; and always
  `answer` last (`answer`, `trace_id` of the `agent.answer` event, `model_calls`, `tool_calls`, `session_tool_calls`,
  `usage`, `number_check`, `error`).
- **History:** assistant messages are kept exactly as returned (reasoning included) and saved in `agent.answer`, so a
  session continues after a restart. A turn without a final answer (error, limit, output cut off, client disconnect)
  is rolled back; its messages stay in that turn's `agent.answer.turn_messages`.
- **Number check** (`number_check`): every number in a finished answer is looked for in the content of the
  session's tool results (the `results` of each body, without bookkeeping such as pages, ranks, scores, timings and
  ids), allowing thousands separators, rounding and the unit scales thousand / million / billion, percent and the
  Chinese yi (100 million). A scaled match needs at least two significant digits; an explicit minus sign must match a
  negative value. Years, page numbers, single digits and numbers inside identifiers are skipped.
  Result: `checked`, `verified` and `unverified` (each `text` and `context`), `skipped`. Unverified numbers are
  reported, never removed; the check cannot tell whether a found number belongs to the claimed metric and year, or
  whether a computed number is right.

**Call source**: HTTP header `X-KB-Source` (`mcp` / `chat` / `eval` / `ui` / `http`; default `http`, other values return
`INVALID_PARAM`) and optional `X-KB-Session`
(written into `session_id`). The MCP entry point always writes `mcp` and takes `X-KB-Session` from the connection's
HTTP headers when present.

---

## 9. Output budget

| Tool | Budget | Controls |
|---|---|---|
| `search` | ≤ 8k tokens | `limit ≤ 30`; `snippet ≤ 300` characters; `local_outline ≤ 12` lines |
| `browse` | ≤ 10k tokens | Automatically reduce expansion depth; one line per node |
| `read` | Text ≤ `max_chars`, plus images | ≤ 5 pages; images off by default; when exceeded, narrow the page range and give `next` |
| `get_metric_series` | ≤ 6k tokens | Observations and mentions not returned by default; at most 5 observations per period |

Estimation: 1 Chinese character ≈ 1 token, 4 English characters ≈ 1 token; images at `width × height / 750` tokens. JSON serialized compactly.

---

## 10. Tracing

Each tool call writes one `trace_event` (`kind = tool.{name}`):

- `input`: the full parameters
- `output`: the list of result node_ids and layers, `scope`, `gaps`, the template ids actually executed with the final ES DSL or SQL and its parameters, and the raw rankings of each retrieval route
- Each entry in `gaps` is also written to `gap_log`, used for the gap leaderboard

`session_id` is nullable (D17); in the chat page's live mode it is generated by the server (D25). Each event carries `source` (`mcp` / `chat` / `eval` / `ui`; for `ui` see D31).

The final answer of a live chat turn is written as one event with `kind = agent.answer`, source `chat`: `input` is the user message and the model; `output` holds `answer`, `finish_reason`, `model_calls`, `usage`, `steps` (each tool call with its trace_id and summary), `turn_tool_calls`, `session_tool_calls`, `number_check`, `turn_messages`, `history`, `completed` and `error`; `status` is `error` with `error` `MODEL_ERROR` or `DISCONNECTED` when the turn failed.

The `output` of `search` also records: `ranking_version`, `concepts_version` (`aliases_version` before P2-2), `link_per_group`, `coverage_threshold`, `coverage_units`, `coverage_dropped` (candidates blocked by the threshold per group and per route, with their coverage), `tier_decisions[*].coverage`. The V4 retrieval trace uses these to show blocked candidates.

---

## 11. Field dependencies

| API needs | Source (Postgres; copied into ES by reindex where marked) |
|---|---|
| `lang`, `fiscal_years` filters | `content.node` / `content.page` denormalized `lang`, `fiscal_year` (ES: yes) |
| `section_types` filter, `group_by=section_type` | `content.node.section_type` + the profile's `sections.yaml` (ES: yes) |
| `entity_scope` | `content.node.entity_scope` (ES: yes) |
| `concepts`, `link` layer | `concept.node_concept` (ES copy: `node.concept_tok`) |
| Physical and printed page of sources | `content.node.start_page / end_page / page_label_range`, `content.page.page_label` |
| Page-to-node mapping | The catalog's primary trees |
| `section_missing_in_lang` | `registry.document.completeness` (from the package declaration) |
| `tree_quality_low` | `quality.coverage` (primary-tree spot check) |
| `get_metric_series` | `fact.fact`, `fact.fact_version`, `fact.fact_obs_link`, `fact.observation` |

---

## 12. Acceptance (kb-core round 1)

**Contract tests** (`tests/integration/test_tools_live.py`, `test_search_live.py`, `tests/test_gaps.py`)

1. Every tool's response has the uniform structure with `contract = v1`
2. Values outside an enum return `INVALID_PARAM` with the allowed values
3. `read` with both `node_id` and `page_range` is an error; unknown documents and nodes return their error codes
4. When the output budget is exceeded, `truncated = true` with a `truncated` gap; fact results are outside the budget
5. Every call has a trace event holding the templates and the final DSL or SQL executed, without page text or images
6. The gap codes of section 4.4 are produced under their conditions

**Effectiveness** (`kb-core eval recall`): kb's 31 questions with year 21/21, without year >= 17/21, cross-year
>= 8/10; reindex invariance (identical per-question top-k after dropping and rebuilding the indexes).

---

## 13. Open items

| Item | Affects | Note |
|---|---|---|
| Vector route (`S7`) | search | Not built in round 1; doctor warns below ES 8.0 that it would be unavailable |
| Font colour in `regions.font` | Tree (note headings) | Contract request CR-1 to kb-intake (`docs/contract-requests.md`) |

---

## Change log

| Date | Content |
|---|---|
| 2026-10-28 | Enterprise readiness: caller identity (section 3: auth modes, `UNAUTHENTICATED` 401, `FORBIDDEN` 403), admin role for `/v1/admin/*`, `role_picker` in `GET /v1/admin/config`, live chat on the chat endpoint purpose with sessions owned by their user |
| 2026-10-27 | Round 2: live chat (`POST /v1/admin/chat`, `GET /v1/admin/chat/status`, section 8.1), `agent.answer` fields, `live_chat` / `mode` in `GET /v1/admin/config` |
| 2026-10-27 | Ported from kb `2f6042e`: storage sections rewritten for Elasticsearch + Postgres; section 2 uses kb's served routes; admin endpoints per the round 1 plan (Task 24); a page hit maps to one node (project owner, 2026-10-27) |
