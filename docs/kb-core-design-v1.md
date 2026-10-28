# kb-core design v1: re-landing the kb solution on ES + Postgres

> English translation of the project owner's original design (written in Chinese, 2026-10-26), made at their request so that
> everything in this repository is English. Where the translation and the original disagree, the original's meaning
> wins; report the discrepancy and fix the translation.

Status: draft (the project owner has confirmed the component name kb-core and "migrate the solution, not the data"; the tree source
and the UI scope default to the recommendations in §11, pending confirmation)
Date: 2026-10-26
Reference implementation: the kb reference repository (frozen, read-only)
Upstream: the kb-intake repository (delivery package contract v2)

## 1. Positioning

kb-core is downstream of kb-intake and is responsible for **interpretation, retrieval and the agent interface**. It
turns delivery packages into knowledge an agent can use with confidence.

```
source files → kb-intake (describe: what is on the page, where, the original text) → delivery folder → kb-core (interpret + retrieve + agent)
```

- **Reads delivery packages only**: it does not parse PDFs, does not call kb-intake and does not import its code. Its
  only input is a contract v2 delivery package
- **Carry over the solution, not the data**: the knowledge model, type profiles, domain packs, recall routes, fusion,
  tool contracts and eval questions come over from kb; kb's databases and JSONL are not migrated, everything is
  regenerated from the delivery packages
- **Storage the company already has**: Postgres is the authoritative data; Elasticsearch is only a retrieval index and
  can be rebuilt from Postgres at any time
- **Runs on a local machine**: like kb-intake — source zip + internal pip mirror + `uv` + `setup.sh`, no Docker needed

## 2. Boundaries

| Belongs to kb-intake | Belongs to kb-core |
|---|---|
| Region types, boxes, reading order, fonts | Table-of-contents tree, heading levels |
| Table rows and columns, original cell text | Number parsing, units, no-value symbols, continued-table merging, header restoration, table business types |
| Page classification, printed page numbers, word coordinates | Section classification (type profiles) |
| Continued-table hints (`continued_hint`) | Whether to merge, and how |
| gaps (problems in the scan layer) | Inherits these gaps and adds interpretation-layer gaps |

The test is the same as kb-intake's: what needs only the file belongs to intake; what needs a type profile or domain
knowledge belongs to kb-core.

## 3. Flow

```
import → build → index → serve
```

| Stage | What it does | Writes to |
|---|---|---|
| import | Validate the delivery package against the contract v2 schemas; register source and document; copy the package into `store/packages/` (kept read-only) | Postgres |
| build | Take the type profile by doc_type: build the tree → classify sections → chunk (node, page, table, paragraph) → interpret tables (numbers, units, continued tables) → tag concepts → extract observations; merge facts across documents | Postgres |
| index | Tokenise (jieba + domain dictionary) and write the ES node and page indexes | ES |
| serve | 5 tools (HTTP + MCP), UI, tracing, evaluation | Reads Postgres + ES |

- Each stage writes one `ingest_run` row per document; re-running the same package with the same configuration
  version produces identical Postgres content (except run times)
- `index` only reads Postgres, so `kb-core reindex` can rebuild ES in full at any time, e.g. after switching
  clusters, changing a mapping or changing the tokeniser dictionary

### 3.1 Tree building

- Basis: intake regions (types `title`, `heading`, `toc`; `font` size and weight; reading order) + table-of-contents
  pages + numbering rules (type profile)
- The annual report type profile keeps kb's table-of-contents page rules and numbering rules; the generic type uses
  only regions and fonts
- PageIndex Flash is demoted to an optional witness: if it is present in the environment it is used for comparison
  and disagreements are recorded as gaps; if it is absent, tree building is unaffected
- Acceptance follows kb's tree evaluation (the question set behind `ref/tree_eval.yaml`)

### 3.2 Table interpretation

- Input is intake's `cells` (original text); parsing numbers, parenthesised negatives, percent signs, units and
  no-value symbols happens in kb-core, with rules from the domain pack's `units.yaml`
- Continued tables: `continued_hint.reason` decides whether to merge (`continued_heading` merges by default,
  `same_first_row` is only a hint by default); merge records are traceable to the original table ids
- Observation extraction keeps kb's annual-report "row label × year column" approach; the cross-validation rules
  (arithmetic relations, prior-year comparatives, Chinese and English editions, multiple reports) are unchanged

## 4. Storage

### 4.1 Postgres (authoritative)

One database, split by schema:

| schema | Tables | Source |
|---|---|---|
| `registry` | source, document, ingest_run | kb's sources.sql |
| `content` | node, page, region, table_block, table_merge | kb's Doris tables turned into Postgres tables; region is new |
| `concept` | concept, concept_alias, concept_edge, node_concept | kb's concepts.sql |
| `fact` | observation, fact, fact_version, fact_obs_link | kb's facts.sql |
| `quality` | trace_event, gap_log, coverage | kb's quality.sql, trace_event.sql |
| `eval` | eval_run, eval_result, answer_check | kb's eval.sql |

- Migrations are numbered SQL files (`migrations/0001_*.sql`) + a `schema_migrations` table, run by
  `kb-core migrate`; no ORM
- All queries live in `queries/pg/*.sql` templates, with kb's naming and versioning rules

### 4.2 Elasticsearch (index, rebuildable)

| Index | Fields | Used by |
|---|---|---|
| `{prefix}node` | node_id, doc_id, fiscal_year, lang, issuer, section_type, is_primary (keyword / numeric); title_tok, summary_tok, concept_tok (kb_ws analyzer); later summary_vec (dense_vector), llm_summary_tok | title route, summary route, concept route, vector route, LLM summary route |
| `{prefix}page` | doc_id, page_no, fiscal_year, lang, issuer (keyword / numeric); text (stored, not indexed, for excerpts); text_tok (kb_ws) | body route, hit distribution |

- Analyzer `kb_ws`: the built-in `whitespace` tokenizer + `lowercase` filter. Chinese is segmented in Python;
  **no plugins are installed on ES**
- One shard per index; physical indexes carry a version (`{prefix}node_v1`) and queries only go through aliases; a
  rebuild creates a new index, loads it, switches the alias and deletes the old index
- The index prefix is set in configuration, following the company's naming rules
- Fusion is done in Python, not with ES's RRF retriever (it needs a paid licence)
- Query templates live in `queries/es/*.json` (versioned) and only do parameter substitution; the trace records the
  final query DSL

### 4.3 Files

- `store/packages/{doc_id}@{sha}/`: imported delivery packages, kept as-is; the final origin of all evidence (page
  images are rendered on demand from `source.pdf`)
- There is no longer a JSONL intermediate layer: the delivery package is the only source of input, and Postgres is
  the only source of interpretation results

## 5. Retrieval layer (carried over from kb, storage swapped)

Later design decisions, including where the Judge's LLM layer sits (2026-10-28), are in
[decision-log.md](decision-log.md).

5 tools: `search`, `browse`, `read`, `resolve_concept`, `get_metric_series`. The contract is kb's
`docs/api-contract.md` (uniform response, layers, provenance, gap codes, status, output budget, tracing), changing only
the template list in §6.

| Recall route | Reads | Weight | Layer |
|---|---|---|---|
| Title BM25 | ES node.title_tok | 1, passes the coverage gate | structure |
| Summary BM25 | ES node.summary_tok | 1, passes the gate | text |
| Body BM25 | ES page.text_tok → deepest node | 1 | text |
| Concept route | ES node.concept_tok | not scored | link |
| Fact route | Postgres fact | not fused, ranked first | fact |
| Vector route (later) | ES node.summary_vec | decided after measurement | text |
| LLM summary route (optional) | ES node.llm_summary_tok | 0.5 | top of text |

Fusion: coverage gate 0.5 (IDF computed over all page bodies) → weighted RRF, k = 60 → layering (fact > link >>>
structure > text) → per-group quota, link_per_group = 2 → facts first → gaps and budget. Parameters are in
`config/ranking.yaml`, following kb's `ref/ranking.yaml` v3. Recall routes follow the RecallRoute interface of kb's
`service/routes.py`.

## 6. Configuration and solution assets (copied from kb, with the source commit noted)

- `profiles/`: base, generic, annual_report (sections.yaml, table-of-contents and numbering rules, observation
  extraction)
- `domains/banking/`: concepts.yaml (v7, 64 concepts), concepts.evidence.yaml, domain.yaml, facts.yaml (15 core
  metrics), finance_zh.txt, low_info_terms.yaml, units.yaml
- `config/ranking.yaml`
- `eval/`: the 31-question eval set and the recall question sets (p1_questions, p1_crossyear, p1_v3, p2_fact_demo,
  p2_heldout, p3_search_path, etc.), plus tree_eval and concept_tag_eval

Only configuration and questions are copied, not kb's data, databases or intermediate artefacts.

## 7. Interfaces

**Command line**

```
kb-core doctor                         # environment check (§9)
kb-core migrate                        # Postgres migrations
kb-core import <package or delivery folder>   # validate and register
kb-core build  [doc_id…|--all]         # interpret
kb-core facts                          # cross-document fact merge
kb-core reindex [--doc doc_id]         # rebuild ES from Postgres
kb-core serve                          # HTTP API + MCP + UI
kb-core eval <question set>            # evaluation
```

**HTTP API and MCP**: 5 tools + admin endpoints (document list, import, run status, trace queries, evaluation).
`serve` listens on 127.0.0.1 only by default.

## 8. UI (3 views in the first version)

React + Vite, interface text in English, consistent with kb-intake.

1. Chat: conversation demo; answers carry provenance and layers
2. Retrieval trace: one call's per-route ranks, gates, layer decisions, final query DSL / SQL
3. Document & evidence: table-of-contents tree, page image, region boxes, tables; jump from a result to the source
   page

The session overview, ingestion dashboard and fact lineage go to the next version.

## 9. Deployment

- Install: source zip → internal pip mirror → `./setup.sh` (uv creates the environment, installs dependencies from
  `constraints.txt`)
- `.env` (template `.env.example`; only variables starting with `KB_CORE_*` are read): ES address and credentials,
  index prefix, PG connection string, delivery folder path, LLM endpoint and the name of its key variable
- `kb-core doctor` checks the following; if any one fails, `serve` refuses to start:
  - ES version, and whether the kb_ws analyzer can be created
  - Whether indexes and aliases can be created
  - PG connection and migration version
  - Delivery folder readable
  - LLM endpoint (when enabled)
- LLM: the company's internal chat-completions-compatible endpoint, off by default; only used for summaries (low weight) and as
  a witness, never the only source
- Embedding model (later): downloaded separately from the intranet, read from local files, version pinned in the docs
- No Docker needed; for local development ES and PG can run in Docker, but it is not required

## 10. Plan and acceptance

| Step | Content | Acceptance |
|---|---|---|
| 1 | Skeleton: pyproject, package structure, configuration loading, doctor, migrate, PG migrations, ES mappings and aliases | doctor passes everything; migrate can be re-run |
| 2 | import + build: delivery package → Postgres (tree, sections, chunks, table interpretation, concepts, observations); facts merge | All 6 OCBC delivery packages imported; tree eval and concept tagging eval no lower than kb; fact merge matches kb (83 agreed, 6 single source, 0 conflicts) |
| 3 | index + retrieval: ES indexes, 5 recall routes, fusion, fact route, gaps, tracing | Recall question sets: with year 21/21, without year 17/21, cross-year 8/10, no lower than kb |
| 4 | serve: HTTP + MCP + 3 UI views | 31-question eval no lower than kb (single-year fact questions 100%, cross-year questions 80%); an agent completes the demo Q&A through MCP |
| 5 | Generalisation: UOB 2025 goes through kb-intake → kb-core | No code changes, only configuration changes; problems and gaps written into the report |
| 6 | Deployment: README, setup.sh, doctor | A clean machine follows the README to install, import and answer questions, without Docker at any point |

The comparison baseline for metrics is the numbers in kb's existing reports (docs/p1*–p3a reports), not kb's
database.

## 11. Pending confirmation

1. Tree building is primarily from intake regions, with PageIndex Flash as an optional witness (default)
2. The first UI version has only 3 views (default)
3. The company's ES version and licence, and whether creating our own indexes and analyzers is allowed (to be
   measured by doctor in the company environment)

## 12. Not doing

Migrating kb's databases or JSONL; Doris; ES plugins; ES's built-in RRF; resident workers and queues; kb-core calling
kb-intake; multi-tenancy and permission systems.
