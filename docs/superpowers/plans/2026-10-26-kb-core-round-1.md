# kb-core round 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-land kb's solution in kb-core on Postgres + Elasticsearch, fed only by kb-intake contract v2 packages,
through design §10 steps 1–4 (skeleton, import + build + facts, index + retrieval, serve), meeting kb's reported
numbers.

**Architecture:** A Python 3.12 package `kb_core` with four stages: `import → build → index → serve`. Postgres
(schemas registry/content/concept/fact/quality/eval) holds every interpretation result. ES holds two aliased indexes
(`{prefix}node`, `{prefix}page`) rebuilt only from Postgres. Retrieval re-implements kb's RecallRoute + fusion in
Python over ES/PG query templates and exposes 5 tools over HTTP (FastAPI) and MCP, plus a React + Vite UI with 3 views.

**Tech Stack:** Python 3.12, uv + hatchling, psycopg 3, httpx (thin ES REST client for ES 7.10–8.x), jieba, jsonschema, FastAPI + uvicorn,
mcp, PyMuPDF (page rendering only), pytest, import-linter; React 18 + Vite + TypeScript; Docker only for local dev ES/PG.

**Spec:** `docs/kb-core-design-v1.md` (the design). Reference implementation (read-only): the kb reference repository at
`chore/english-only` @ `2f6042e`. Upstream contract: the kb-intake repository, `contract/v2/` @ `fc9b4b4`.

## Global Constraints

- Inputs: only contract v2 packages. No PDF parsing (rendering a page image from `source.pdf` for the UI is allowed).
  No import or call of kb-intake or kb; `uv run lint-imports` forbids `kb_intake`, `pipeline`, `service`, `scripts`
  (kb's top-level packages) from `kb_core`.
- English everywhere (AGENTS.md "Language"); Chinese only in matched data (aliases, row labels, jieba dictionary,
  regexes, zh questions/gold, fixtures).
- Config: only `KB_CORE_*` environment variables (or a gitignored `.env`). `serve` binds 127.0.0.1 by default.
- Postgres is authoritative; `reindex` reads Postgres only. ES: no plugins, no RRF retriever, 1 shard, versioned
  physical index behind an alias, analyzer `kb_ws` = `whitespace` tokenizer + `lowercase` filter.
- Queries only in `queries/pg/<ID>_<name>.v<N>.sql` and `queries/es/<ID>_<name>.v<N>.json`; only parameter
  substitution. Traces record the final DSL / SQL.
- Elasticsearch ≥ 7.10 is supported (doctor fails below 7.10, warns below 8.0 that the vector route is
  unavailable); kb-core talks to ES over plain REST, not the version-locked official client.
- Ranking parameters from `config/ranking.yaml` (kb v3): coverage threshold 0.5, RRF k = 60, link_per_group = 2,
  budget 8,000 tokens, per-route pool 50 (concept route 200).
- Determinism: same package + same config version ⇒ identical Postgres content except run timestamps.
- Dependencies pinned in `uv.lock`; `constraints.txt` from `uv export --no-hashes --no-dev`.
- No sample-specific logic in `src/`. Profile/domain rules live in YAML under `profiles/` and `domains/`.
- No batch LLM calls; LLM disabled by default. kb-intake packages are produced with `INTAKE_LLM_ENABLED=false`.

## Decisions made in this plan (the project owner can overrule in PR review)

1. **Asset source commit:** kb `chore/english-only` @ `2f6042e` (contains `main`; comments already English). kb-intake
   contract @ `fc9b4b4` (release 0.3.1).
2. **concepts.yaml is v8 / 65 concepts** (v7's 64 + derived `net_profit_margin`); the design text says v7/64 because
   it predates v8.
3. **"31-question eval" = kb's 31 recall questions** (p1_questions 10 + p1_crossyear 3 + p1_v3 18 = 21 single-point +
   10 cross-year). kb reports these as 21/21 with year (= "single-year 100%") and 8/10 cross-year (= "80%"); there is
   no separate metric in kb's reports. Held-out (p2_heldout, kb 4/16) is reported for information.
4. **Tree source.** Contract v2 has no font colour and kb-core cannot read PDF spans, so kb's red-note-heading rule
   and Flash attachment cannot be ported as-is. The annual-report tree is rebuilt from `toc` regions (skeleton),
   `title`/`heading` regions with `font{size,bold}` and numbering patterns from `profiles/annual_report/tree.yaml`
   (notes `N.` / `N.M`). PageIndex Flash witness is not built this round (design: optional, absence has no effect).
   `tree_source` value: `regions`. **Stop rule:** if the tree eval is below kb per document, stop and ask the project owner.
   **Contract request CR-1** (recorded in `docs/contract-requests.md`, kb-intake is not changed): add an optional
   `color` to `regions.font` (additive, contract v2). The note-heading rule uses it when present: a note heading must
   also differ in colour from the document's dominant body-text colour (computed per document, so no issuer colour
   is configured). Without the field, numbering + font size/bold decide alone.
5. **Continued tables** are new (kb never merged them): `continued_heading` ⇒ merge, `same_first_row` ⇒ hint only;
   every merge is a `content.table_merge` row naming its part table ids.
6. **Paragraph chunks** = intake `text`/`list`/`caption`/`footnote` regions stored in `content.region` with the node
   that covers them; they are not indexed in ES this round (kb's retrieval units are node, page, table).
7. **Eval judging:** tree and concept-tag samples follow kb's protocol (40 nodes/doc for tree; 40 tagged nodes/lang
   for concepts; correct = all fields right; threshold 85% and no lower than kb). Judging is delegated to a subagent
   that reads only the PDFs and the sample sheet; the main session re-judges 10 items per sheet.
8. **Chat view:** live chat uses the optional LLM when `KB_CORE_LLM_ENABLED=true`; otherwise it replays recorded
   sessions from `quality.trace_event` (including the MCP demo session). The MCP demo is run with
   a non-interactive MCP client (one session, not a batch).
9. **Dev infrastructure:** `docker/compose.dev.yaml` with `postgres:17.6` on 127.0.0.1:5433 and ES 8.19 (latest
   8.19.x patch at Task 2, pinned in the file; security off for local dev) on 127.0.0.1:9200, plus an optional `es7` service (ES 7.10.2 on 127.0.0.1:9201,
   profile `compat`) for the ES 7.10 compatibility tests. kb's running
   Postgres/Doris containers are not touched.
10. **Delivery folder for OCBC:** `$KB_CORE_DELIVERY_DIR` (via `INTAKE_DATA_DIR=<intake data folder>`), so kb's
    and kb-intake's own data dirs are untouched.
11. **"5 recall routes + fact route" = kb's five routes:** title, summary, body, concept, fact (kb
    `service/routes.py:2`). The vector and LLM-summary routes are "later / optional" in the design and not built this
    round.
12. **ES access:** a thin REST client over httpx (`src/kb_core/es/client.py`) instead of `elasticsearch-py`, because
    the 8.x client sends compatibility headers ES 7.x rejects and the design must run on the company's unknown ES
    version (design §11.3, minimum 7.10).
13. **Order (project owner, PR #1 review):** the 6 packages are produced first; after the skeleton, a thin vertical slice on
    `ocbc-group_ar_2025_en` (import → tree → chunks → reindex → search → one MCP question) runs before concepts,
    facts and evals, and its tree quality is reported to the project owner before continuing.
14. **Execution:** the main session implements every task; only the 3 UI views, PR reviews and eval judging are
    delegated (Tallyback-registered, re-checked by the main session).

15. **Page hits map to one node (project owner, 2026-10-27, after the first recall run).** kb maps a page-route hit to every
    deepest node covering the page. kb-core's region tree splits some pages into several leaf nodes (2025 en p13: three),
    so one page filled a year group's top 3 and cross-year recall was 7/10 (kb 8/10). A page hit now counts toward
    the first covering node in reading order only (`fusion.fuse`): 21/21 · 19/21 · 9/10.

## Review Focus

1. **Re-import / re-build of the same package** must be a no-op or an identical rewrite, never duplicate rows —
   Task 9 `test_import_is_idempotent`, Task 12 `test_build_twice_identical`.
2. **A package from a different contract version, unconfirmed, or with a tampered file** must be rejected with a
   clear message and no rows written — Task 9 `test_rejects_*`.
3. **A query whose terms are all low-information or unknown** (e.g. "2025", "OCBC") must return gaps, not an
   exception or an empty envelope — Task 14 `test_search_low_info_query_returns_gap`.
4. **ES alias missing or pointing to a deleted index** (half-finished reindex) must be detected by doctor and fixed
   by the next `reindex` — Task 6 `test_reindex_recovers_from_orphan_index`, Task 7 doctor check `es_alias`.
5. **Zero-value and no-value table cells** (`-`, `—`, `n.m.`, `(0.3)`, `0.0%`) must parse to nil / negative / zero
   distinctly — Task 16 `test_parse_cell_*`.

---

## Phase 0 — packages first

### Task 1: Produce the 6 OCBC packages (main session, operational, runs first)

- [ ] **Step 1:** In the kb-intake repository (read-only use of its CLI), for each PDF in the sample folder (`intake-samples/ocbc/` with
  `INTAKE_DATA_DIR=<intake data folder> INTAKE_LLM_ENABLED=false`: `uv run kb-intake label <pdf> --decl
  declarations.yaml` → `approve <job> --by "agent-for-owner"` (default workflow) → `extract <job>` → `confirm <job>
  --by "agent-for-owner"` → `check <package>`. Run in the background; keep the JSON lines output.
- [ ] **Step 2:** Verify: 6 folders `ocbc-group_ar_{2023,2024,2025}_{en,zh}@<sha12>` whose sha12 equals the PDFs'
  (`c096369d1fac, eea4bedbd5f6, c931fd287b5f, b333687e3671, d10f4fc11fd5, 0797f849cd02`); every `check` ok;
  `manifest.llm` absent.
- [ ] **Step 3:** Start this before Task 2 and let it run in the background while Phase A proceeds (about 45 min CPU).

---

## Phase A — Step 1: skeleton (PR "step 1: skeleton")

### Task 2: Project scaffold and pinned dependencies

**Files:**
- Create: `pyproject.toml`, `uv.lock`, `constraints.txt`, `.python-version`, `.gitignore`, `.env.example`,
  `README.md`, `src/kb_core/__init__.py`, `src/kb_core/cli.py`, `scripts/check_constraints.py`,
  `docker/compose.dev.yaml`, `setup.sh`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces: console script `kb-core = "kb_core.cli:main"`; `main(argv: list[str] | None = None) -> int` with
  subcommands `doctor, migrate, import, build, facts, reindex, serve, eval` (unimplemented ones exit 2 with
  "not implemented yet" until their task lands).

- [ ] **Step 1:** Write `tests/test_cli.py::test_help_lists_subcommands` (runs `main(["--help"])`, asserts every
  subcommand name appears) and `test_unknown_command_exits_2`.
- [ ] **Step 2:** Run `uv run pytest tests/test_cli.py -v` → FAIL (module missing).
- [ ] **Step 3:** Write `pyproject.toml`: `requires-python = "==3.12.*"`, hatchling, wheel force-includes
  `contract/`, `migrations/`, `queries/`, `es/`, `profiles/`, `domains/`, `config/`, `constraints.txt`; runtime deps
  `psycopg[binary]`, `httpx`, `jieba==0.42.1`, `jsonschema`, `pyyaml`, `fastapi`, `uvicorn`, `mcp`,
  `pymupdf`; dev group `pytest`, `import-linter`. Pin exact versions via `uv lock` (match kb's `uv.lock` versions
  where kb uses the package). Add `[tool.importlinter]` root `kb_core`, `include_external_packages = true`, one
  forbidden contract "kb-core does not import kb-intake or kb": forbidden `kb_intake`, `pipeline`, `service`,
  `scripts`.
- [ ] **Step 4:** Implement `cli.py` with argparse; `scripts/check_constraints.py` regenerates `uv export
  --no-hashes --no-dev` to a temp file and diffs against `constraints.txt` (exit 1 on drift).
- [ ] **Step 5:** `docker/compose.dev.yaml` (decision 9); `setup.sh` skeleton copying kb-intake's step/ok/fail
  structure: parse `.env` → create `.venv` with uv/python3.12 → `pip install -c constraints.txt .` → `kb-core doctor`.
- [ ] **Step 6:** Run `uv run pytest -q && uv run lint-imports && uv run python scripts/check_constraints.py` → all
  pass. Commit `chore: scaffold kb-core package, pinned deps and dev compose`.

### Task 3: Configuration

**Files:** Create `src/kb_core/config.py`; Test `tests/test_config.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class Settings` with `pg_dsn: str`, `es_url: str`, `es_user: str | None`,
  `es_password: str | None`, `es_api_key: str | None`, `es_ca_certs: str | None`, `index_prefix: str` (default
  `"kbcore_"`), `delivery_dir: Path | None`, `store_dir: Path` (default `./store`), `domain: str` (default
  `"banking"`), `llm_enabled: bool` (False), `llm_base_url: str | None`, `llm_model: str | None`,
  `llm_api_key_var: str` (default `"KB_CORE_LLM_API_KEY"`), `host: str` (`"127.0.0.1"`), `port: int` (8200);
  `load_settings(env: Mapping[str, str] | None = None, env_file: Path | None = Path(".env")) -> Settings`;
  `Settings.redacted() -> dict` (secrets replaced by `"***"`).

- [ ] **Step 1:** Tests: `test_reads_only_kb_core_vars` (an `INTAKE_PG_DSN`/`PG_DSN` in env is ignored),
  `test_env_overrides_dotenv`, `test_missing_pg_dsn_raises_config_error` (message names `KB_CORE_PG_DSN`),
  `test_redacted_hides_secrets`, `test_index_prefix_must_be_lowercase` (ES naming).
- [ ] **Step 2–4:** Run → FAIL; implement (tiny `.env` parser, no python-dotenv); run → PASS.
- [ ] **Step 5:** Fill `.env.example` with every `KB_CORE_*` name, one comment line each. Commit.

### Task 4: Postgres migrations and `kb-core migrate`

**Files:**
- Create: `migrations/0001_registry.sql`, `0002_content.sql`, `0003_concept.sql`, `0004_fact.sql`,
  `0005_quality.sql`, `0006_eval.sql`; `src/kb_core/pg/__init__.py`, `src/kb_core/pg/db.py`,
  `src/kb_core/pg/migrate.py`
- Test: `tests/integration/test_migrate.py` (marker `pg`; skipped when `KB_CORE_TEST_PG_DSN` is unset)

**Interfaces:**
- Produces: `connect(settings) -> psycopg.Connection`; `migrate(conn, dir: Path = MIGRATIONS) -> list[str]`
  (applied names); `current_version(conn) -> int`; table `public.schema_migrations(version int primary key, name
  text, sha256 text, applied_at timestamptz)`.
- Table content: port columns from kb `schemas/postgres/{sources,concepts,facts,quality,trace_event,eval}.sql` and
  the Doris `schemas/doris/01_tables.sql` node/page/table_block, into schemas registry/content/concept/fact/quality/
  eval (design §4.1). New: `content.region` (intake region columns + `node_id`), `content.table_merge(merge_id,
  doc_id, part_table_ids text[], reason, decision text check in ('merged','hint'), header_from text)`,
  `content.table_block` gains `parsed jsonb` (interpreted cells) and `table_kind text`. `registry.document` gains
  `package text`, `package_sha256 text`, `contract_version text`. Every content/concept/fact row has `doc_id` so a
  rebuild can delete-then-insert per document.

- [ ] **Step 1:** Tests: `test_migrate_applies_all_then_noop` (second call returns `[]`),
  `test_migrate_refuses_edited_applied_file` (sha mismatch → `MigrationError`), `test_schemas_exist`
  (all six schemas and the tables named in design §4.1).
- [ ] **Step 2–4:** Run → FAIL; write SQL + `migrate.py` (each file in one transaction, advisory lock
  `pg_advisory_xact_lock(4242)`); run → PASS.
- [ ] **Step 5:** Wire `kb-core migrate`; run it twice against dev PG and keep the output. Commit.

### Task 5: Query template loaders

**Files:** Create `src/kb_core/queries.py`, `queries/pg/.keep`, `queries/es/.keep`; Test `tests/test_queries.py`

**Interfaces:**
- Produces: `pg_query(name: str, **fragments) -> tuple[str, str]` returning `(template_id, sql)` — picks the highest
  `v<N>` of `<ID>_<name>`, substitutes only `{filters}` (from a whitelisted column set) and `{limit}` (int);
  `es_query(name: str, params: Mapping[str, Any]) -> tuple[str, dict]` — loads JSON, replaces every string value
  exactly equal to `"{{param}}"` with the JSON value of `params[param]`; unknown or missing params raise
  `TemplateError`. Template id format `S1_node_title_bm25.v1` (kb api-contract §6.2 naming).

- [ ] Tests: `test_pg_picks_highest_version`, `test_pg_rejects_unlisted_filter_column`,
  `test_es_substitutes_whole_values_only` (a `"{{q}}"` inside a longer string is not substituted),
  `test_es_missing_param_raises`. Red → implement → green → commit.

### Task 6: ES mappings, kb_ws analyzer and alias management

**Files:** Create `es/node.v1.json`, `es/page.v1.json` (settings + mappings, design §4.2), `src/kb_core/es/client.py`,
`src/kb_core/es/indexes.py`; Test `tests/integration/test_es_indexes.py` (marker `es`)

**Interfaces:**
- Produces: `class EsClient` (`__init__(settings)`; httpx with basic auth / API key / CA certs from settings;
  `info() -> dict`, `request(method: str, path: str, json: Any = None, params: dict | None = None) -> dict`,
  `bulk(actions: list[dict]) -> dict` (NDJSON, raises on item errors), `analyze(index: str, analyzer: str, text: str)
  -> list[str]`; HTTP errors raise `EsError(status, reason)`); `es_client(settings) -> EsClient`; `alias_name(settings, kind: Literal["node","page"]) -> str`
  (`{prefix}{kind}`); `create_physical(es, settings, kind) -> str` (name `{prefix}{kind}_v{mapping_version}_{utc
  yyyymmddHHMMSS}`); `swap_alias(es, alias, new_index) -> list[str]` (atomic `_aliases` actions; returns removed
  indexes, then deletes them); `orphan_indexes(es, settings) -> list[str]`.
- Mapping: keyword `node_id, doc_id, lang, issuer, section_type`; integer `fiscal_year, page_no, depth`; boolean
  `is_primary`; `text` type with analyzer `kb_ws` for `title_tok, summary_tok, concept_tok, text_tok`; `text` field on
  page with `"index": false`; `number_of_shards: 1`, `number_of_replicas: 0` for dev (replicas from config).

- [ ] Tests: `test_kb_ws_analyzer_splits_on_whitespace_and_lowercases` (`_analyze` of `"NPL <zh term> Ratio"` → `["npl","<zh term>","ratio"]`;
  the zh term comes from `tests/fixtures/`), `test_swap_alias_is_atomic_and_deletes_old`,
  `test_reindex_recovers_from_orphan_index` (an extra `{prefix}node_v1_*` with no alias is removed by the next swap).
  All integration tests also run against ES 7.10.2 when `KB_CORE_TEST_ES7_URL` is set (compose profile
  `compat`). Red → implement → green → commit.

### Task 7: `kb-core doctor`

**Files:** Create `src/kb_core/doctor.py`; Test `tests/test_doctor.py` (unit, with fakes) +
`tests/integration/test_doctor_live.py`

**Interfaces:**
- Produces: `@dataclass Check(name: str, level: Literal["ok","warn","fail"], detail: str, fix: str)`; `run_checks(settings) -> list[Check]`
  with names `config`, `pg_connect`, `pg_migrations` (current == latest file), `es_version` (fail below 7.10; warn
  below 8.0 "vector route unavailable"; reports version and licence), `es_analyzer` (creates and deletes a temp index with `kb_ws`), `es_alias` (create temp
  index + alias, swap, delete; also warns about orphan indexes), `delivery_dir` (exists, readable), `store_dir`
  (writable), `llm` (only when enabled: GET `{base_url}/models` with key from the named env var).
  `doctor_main(settings, report: Path | None) -> int` (0 when no check fails — warnings allowed, 1 otherwise; JSON
  report when asked).
- `serve` calls `run_checks` and refuses to start when any check fails (wired in Task 15).

- [ ] Tests: `test_all_ok_exits_0`, `test_one_failure_exits_1_and_names_fix`, `test_llm_check_skipped_when_disabled`,
  `test_report_never_contains_secrets`,
  `test_es_7_10_warns_vector_route_unavailable` (exit 0), `test_es_below_7_10_fails`. Red → implement → green.
- [ ] Acceptance: `docker compose -f docker/compose.dev.yaml up -d && uv run kb-core migrate && uv run kb-core migrate
  && uv run kb-core doctor` → no `fail` (and no `warn` on ES 8.19); also run doctor against the `es7` service; keep both outputs. Keep output for the report. Commit; open PR "step 1"; independent
  review (requesting-code-review + earn-it); merge.

---

## Phase B — Vertical slice on `ocbc-group_ar_2025_en` (PR "slice"; ends with a stop for the project owner)

### Task 8: Contract copy and copied solution assets

**Files:**
- Create: `contract/intake-v2/*.schema.json` (9 files, byte copies), `contract/intake-v2/SOURCE.md` (repo, path,
  commit `fc9b4b4…`, copy date), `scripts/check_contract.py`, `ASSETS.md`, `scripts/check_assets.py`
- Create (copies from kb @ `2f6042e`): `profiles/annual_report/sections.yaml`, `domains/banking/{concepts.yaml,
  concepts.evidence.yaml, domain.yaml, facts.yaml, finance_zh.txt, low_info_terms.yaml, units.yaml}`,
  `config/ranking.yaml` (from `ref/ranking.yaml`), `eval/{p1_questions, p1_crossyear, p1_v3, p2_fact_demo, p2_heldout,
  p3_search_path, demo, p1_agent, heldout_terms, derived_allowlist}.yaml`, `eval/baseline/{tree_eval,
  concept_tag_eval}.yaml` (kb's recorded results, the comparison baseline)
- Test: `tests/test_contract_and_assets.py`

**Interfaces:**
- `check_contract.py [--intake-repo PATH]` (the kb-intake repository; env `KB_CORE_INTAKE_REPO`): byte-compares every
  `contract/v2/*.schema.json` with the copy, and reports the upstream HEAD vs `SOURCE.md` commit; exit 1 on any
  difference or missing file.
- `ASSETS.md`: one table row per copied file: kb-core path, kb source path, source commit, sha256 of the copied
  bytes, and "edited" notes (English translation of free-text fields). `check_assets.py` verifies the table lists
  every file under `profiles/ domains/ config/ eval/` (except `eval/results/`) and the sha256 matches.
- Free-text Chinese notes (`why:`, `answer:` notes, comments) are translated; matched data stays.

- [ ] Tests: `test_contract_copy_matches_upstream` (skipped when the upstream repo is absent),
  `test_assets_manifest_complete_and_hashes_match`, `test_no_cjk_outside_allowed_data` (scans `src/`, `scripts/`,
  `migrations/`, `queries/`, `es/`, `docs/`, `web/src/`, YAML comments; allowlist: alias/row-label/regex/query/gold
  fields, `finance_zh.txt`, `tests/fixtures/`). Red → copy + implement → green → commit.

### Task 9: Package reader and `kb-core import`

**Files:** Create `src/kb_core/intake/package.py`, `src/kb_core/intake/importer.py`, `queries/pg/R*_*.v1.sql`;
Test `tests/test_package.py`, `tests/integration/test_import.py`, fixture `tests/fixtures/mini_package/` (a
hand-built 3-page contract v2 package with a tiny PDF made by a test helper, regions, one table split by a
`continued_heading` hint, one gap)

**Interfaces:**
- Produces: `class Package` (`path`, `manifest: dict`, `doc_id: str`, `sha12: str`, `declaration: dict`,
  `pages() -> Iterator[dict]`, `regions() -> Iterator[dict]`, `tables() -> Iterator[dict]`,
  `words(page_no: int) -> list[list]`, `gaps() -> Iterator[dict]`, `source_pdf: Path`);
  `validate(path: Path) -> Package` raising `PackageError(message)`;
  `import_path(conn, settings, path: Path) -> list[ImportResult]` where `ImportResult(doc_id, package, created:
  bool)` and `path` is a package or a delivery folder.
- Validation: folder name `<doc_id>@<sha256[:12]>`; `contract_version == "2"`; `status.state == "confirmed"`;
  every row of every jsonl validates against its schema; `manifest.files` sha256/bytes match; `source.pdf` sha256
  matches `manifest.source.sha256` and the folder name.
- Import: copy to `store/packages/<name>/` then `chmod -R a-w`; upsert `registry.source` (issuer) and
  `registry.document` (doc_id, issuer_id, doc_type, fiscal_year = year of `period_end`, lang, translation_of,
  package, contract_version); insert `ingest_run(stage='import')`; insert inherited intake gaps into
  `quality.gap_log` with `layer='intake'`. Same doc_id + same sha ⇒ no-op (`created=False`); same doc_id + different
  sha ⇒ `PackageError` (kb rule).

- [ ] Tests: `test_validate_accepts_fixture`, `test_rejects_wrong_contract_version`, `test_rejects_unconfirmed`,
  `test_rejects_tampered_file_hash`, `test_rejects_schema_violation_and_writes_nothing`,
  `test_import_is_idempotent`, `test_import_conflicting_sha_rejected`, `test_import_delivery_folder_imports_all`.
  Red → implement → green → commit.
- [ ] **Slice import:** `uv run kb-core import $KB_CORE_DELIVERY_DIR` → 6 created; run again → 6 no-op. If a
  field the plan needs is missing from the packages, add it to `docs/contract-requests.md` and ask the project owner.

### Task 10: Profiles and the region-based tree

**Files:** Create `src/kb_core/profiles/__init__.py`, `base.py`, `generic.py`, `annual_report.py`;
`profiles/generic/tree.yaml`, `profiles/annual_report/tree.yaml`; `src/kb_core/build/tree.py`,
`src/kb_core/build/toc.py`; Test `tests/test_tree.py`, `tests/test_toc.py`

**Interfaces:**
- Produces: `class Profile(Protocol)`: `doc_type: str`, `build_tree(pkg: Package) -> list[TreeNode]`,
  `classify_sections(nodes: list[TreeNode]) -> None`, `observation_rules() -> dict`, `entity_words() -> dict`;
  `profiles.get(doc_type: str) -> Profile` (falls back to generic).
  `@dataclass TreeNode(node_id: str, parent_id: str | None, depth: int, title: str, page_start: int, page_end: int,
  origin: Literal["toc","heading","note","subnote","root"], section_type: str | None, is_primary: bool, region_ids:
  list[str])`. node_id = `f"{doc_id}:regions:{n:04d}"` in pre-order.
- `toc.py`: `parse_toc(regions_on_toc_pages, pages) -> list[TocEntry(title, printed_page: str, group: str | None)]`
  and `printed_to_physical(pages) -> dict[str, int]` from `pages.page_label` (falls back to a constant offset
  detected from labelled pages, else a `page_label_unreliable` gap).
- Generic tree: headings = `title`/`heading` regions in body layer, ordered by (page_no, reading_order); level by
  ranking distinct rounded font sizes (larger = shallower), bold breaks ties; numbering patterns from `tree.yaml`
  override level when matched.
- Annual-report tree (port of kb `profiles/annual_report/tree.py` logic, inputs swapped): TOC skeleton from `toc`
  regions within the first `toc_scan_pages` (7) pages, groups vs entries as in kb (entry has a page number; group
  is bold without one); divider pages (< 30 chars) move to the following section; sub-TOC pages (≥ 5 entries,
  increasing pages); notes `^(\d{1,2})\.\s` and subnotes `^(\d{1,2})\.(\d{1,2})\s` among heading regions inside
  the notes section, consecutive numbering, skipping "(continued)" and its zh form (both patterns in `tree.yaml`); other heading regions attach under the
  deepest skeleton node covering their page. All thresholds live in `tree.yaml`.
- Note-heading colour (CR-1): when regions carry `font.color`, `body_colour(regions) -> str | None` is the most common
  colour of `text` regions in the document, and a note/subnote heading must also have a different colour. When no
  region has the field, the rule is skipped and recorded once in `ingest_run.detail` ("font colour not in package").

- [ ] Tests (on fixture regions, no OCBC data): `test_toc_entries_and_groups`, `test_printed_to_physical_offset`,
  `test_divider_page_moves_to_next_section`, `test_note_numbering_must_be_consecutive`,
  `test_continued_note_heading_skipped`,
  `test_note_heading_uses_colour_when_present`, `test_note_rule_without_colour_field`, `test_generic_levels_from_font_size`, `test_node_ids_preorder_stable`.
  Red → implement → green → commit.

### Task 11: Section classification

**Files:** Create `src/kb_core/build/sections.py`; Test `tests/test_sections.py`

**Interfaces:** `assign(nodes: list[TreeNode], rules: dict) -> None` — port kb `profiles/annual_report/sections.py`:
first matching rule R01–R22 (regex on title / group / origin) sets `section_type`; children inherit; unmatched
roots → `other`. `origin` values map kb `toc`→`toc`, kb `flash`→`heading`.

- [ ] Tests: one per rule family using titles from `sections.yaml` query_patterns (`test_md_a_rule`,
  `test_notes_children_inherit`, `test_unmatched_is_other`). Red → implement → green → commit.

### Task 12: Chunks (node, page, region, table rows)

**Files:** Create `src/kb_core/build/chunks.py`, `src/kb_core/build/tokenize.py`, `src/kb_core/build/run.py`,
`queries/pg/B*_*.v1.sql`; Modify `src/kb_core/cli.py`; Test `tests/test_chunks.py`, `tests/test_tokenize.py`,
`tests/integration/test_build.py`

**Interfaces:**
- `tokenize(text: str, lang: str) -> str` — port of kb `pipeline/tokenize.py` (jieba with
  `domains/<domain>/finance_zh.txt`, lowercase, numbers with thousands separators kept whole and also without commas,
  punctuation-only tokens dropped); returns space-joined tokens.
- `node_rows(nodes, pages, regions) -> list[dict]`: kb's node fields (ancestors, depth, title, title_tok, summary =
  title + first 300 chars of the node's own text, summary_tok, page_start/end, section_type, is_primary, fiscal_year,
  lang, issuer); `page_rows(...)`: text, text_tok, `covering_node_ids` (deepest primary nodes);
  `region_rows(...)` with `node_id`; `table_rows(...)` with `parsed`, `unit_hint`, `table_kind`, `node_id`.
  `concept_tok` is filled by Task 17.
- `build_doc(conn, settings, doc_id: str) -> RunSummary`: one transaction per document; delete the doc's content
  rows, then run the stages built so far (here: tree → sections → chunks; Task 19 adds tables/merges → tags →
  observations); one `ingest_run` row per stage with counts and `config_version` = sha256 of the profile + domain
  files used. `content_digest(conn, doc_id) -> str` = sha256 over ordered content rows, excluding run times.
  CLI `kb-core build <doc_id>...|--all`.

- [ ] Tests: `test_tokenize_zh_uses_domain_dict` (fixture sentence containing a dictionary term keeps it whole),
  `test_tokenize_keeps_thousand_numbers`, `test_page_covering_nodes_are_deepest`, `test_summary_is_title_plus_300`,
  `test_build_twice_identical` (fixture package; digest equal), `test_build_records_runs_per_stage`.
  Red → implement → green → commit. Then `uv run kb-core build ocbc-group_ar_2025_en`; record counts.

### Task 13: `kb-core reindex`

**Files:** Create `src/kb_core/es/indexer.py`, `queries/pg/D*_*.v1.sql`; Test `tests/integration/test_reindex.py`

**Interfaces:** `reindex(conn, es, settings, doc_id: str | None = None) -> IndexSummary(nodes: int, pages: int,
index_names: dict)`. Full: create new physical indexes, bulk load from PG (node docs from `content.node` +
`concept_tok`; page docs from `content.page`), refresh, `swap_alias`. `--doc`: delete-by-query on the alias for that
doc, then bulk insert. Never reads the package store.

- [ ] Tests: `test_reindex_counts_match_pg`, `test_reindex_doc_replaces_only_that_doc`,
  `test_reindex_after_index_deleted` (delete the physical index, reindex, counts equal). Red → implement → green →
  commit. Then `uv run kb-core reindex` (slice: one document built).

### Task 14: Slice search path: S1–S3 routes, core fusion, search and read

**Files:** Create `src/kb_core/retrieval/{routes,coverage,fusion,envelope,search,read,tracing}.py`,
`queries/es/{S1_node_title_bm25, S2_node_summary_bm25, S3_page_text_bm25}.v1.json` (kb's template ids),
`queries/pg/M*_*.v1.sql` (deepest-node lookup, page text for read), `config/ranking.yaml` already copied in Task 8;
Test `tests/test_routes.py`, `tests/test_coverage.py`, `tests/test_fusion.py`, `tests/integration/test_search_live.py`

**Interfaces:**
- `routes.py`: port kb `service/routes.py` `RecallRoute` (attributes `name, unit, scored, gated, tier, structural,
  layer`; methods `recall(ctx: RecallContext) -> list[Hit]`, `hay(hit) -> str`, `accept(hit, ctx) -> bool`);
  `TitleRoute` (S1), `SummaryRoute` (S2), `PageTextRoute` (S3, page hits → deepest covering node via PG);
  `Hit(node_id, doc_id, score, rank, route, page_no | None)`; pool 50. Each route records template id + final DSL.
- `coverage.py`: `idf(df: int, n: int) -> float` = `ln(1 + (n - df + 0.5) / (df + 0.5))`; `page_df(es, settings,
  units) -> dict[str, int]` (ES `_count` on `page.text_tok`, cached per process); `coverage(hay: str, units, idf) ->
  float` (df = 0 units skipped; alias units all-or-nothing once Task 21 adds aliases).
- `fusion.py`: `fuse(route_hits, ranking: dict) -> FusedResult` — gate at `coverage_threshold`, weighted RRF
  `Σ w / (k + rank)` with k = 60, layers structure > text (a title is structure only if it contains an informative
  token), budget 8,000 tokens, gaps `over_filtered`, `page_label_unreliable`, `truncated`, `concept_unknown` (no
  informative unit).
- `envelope.py`, `search.py` (`search(params) -> Envelope`), `read.py` (`read(params) -> Envelope`, ≤ 5 pages,
  node_id xor page_range), `tracing.py` (`quality.trace_event` with route ranks, gate decisions, final DSL/SQL),
  all shaped as kb `docs/api-contract.md` §4–5 and §10.

- [ ] Tests: `test_page_hits_map_to_deepest_node`, `test_filters_rendered_into_dsl` (fiscal_year, lang, doc_id),
  `test_idf_formula`, `test_gate_drops_low_coverage_hits`, `test_rrf_k60_weighted`,
  `test_search_low_info_query_returns_gap` (query "OCBC 2025"), `test_read_rejects_node_id_and_page_range`,
  `test_trace_records_final_dsl`. Red → implement → green → commit.

### Task 15: Minimal serve + MCP, one MCP question, slice tree report

**Files:** Create `src/kb_core/serve/app.py`, `src/kb_core/serve/mcp.py`, `.mcp.json.example`,
`docs/reports/slice-2025-en.md`; Test `tests/test_app.py`

**Interfaces:** `create_app(settings) -> FastAPI` with POST `/v1/search`, GET `/v1/read`, MCP at `/mcp` exposing
`search` and `read` with kb's agent rules text (kb `service/app.py` RULES_COMMON); `kb-core serve` runs
`run_checks` first and exits 1 on any `fail`; default host 127.0.0.1.

- [ ] **Step 1:** Tests `test_serve_refuses_when_doctor_fails`, `test_default_bind_is_localhost`,
  `test_search_route_returns_envelope`. Red → implement → green → commit.
- [ ] **Step 2: One MCP question.** `uv run kb-core serve` (background); one non-interactive MCP client session with the kb-core MCP
  server only, question kb `eval/p1_questions.yaml` q01 ("What was OCBC's non-performing loan (NPL) ratio at the end
  of 2025?", gold 0.9% on physical pages 13/100/105). Keep the transcript; check the cited page.
- [ ] **Step 3: Slice tree quality.** `kb-core eval tree --doc ocbc-group_ar_2025_en --seed <new>` (40 primary nodes;
  the sheet generator lands here, Task 19 reuses it); delegated judging (Tallyback; PDF-only; D22 criterion: title,
  page and parent all correct); main session re-judges 10. Compare with kb 38/40.
- [ ] **Step 4:** Write `docs/reports/slice-2025-en.md` (counts per stage, tree score and every wrong node with its
  cause, the MCP transcript, search results for 5 recall questions, open problems); open PR "slice"; independent
  review; merge. **Stop and report to the project owner; continue only on their go-ahead.**

---

## Phase C — Step 2 complete: tables, concepts, facts, evals (PR "step 2")

### Task 16: Table interpretation and continued-table merge

**Files:** Create `src/kb_core/build/cells.py`, `src/kb_core/build/tables.py`; Test `tests/test_cells.py`,
`tests/test_tables.py`

**Interfaces:**
- `@dataclass Value(raw: str, num: Decimal | None, nil: bool, negative: bool, percent: bool, unit: str | None,
  scale: int)`; `parse_cell(text: str | None, units: dict) -> Value`.
- `interpret(table: dict, context_text: str, units: dict) -> InterpretedTable` with `header_rows: list[list[str]]`,
  `columns: list[str]` (header cells joined top-down across `rs/cs` spans), `rows: list[Row(label: str, path:
  list[str], values: list[Value])]`, `unit_hint: str | None` (from the table's own header or the `context_text` of
  regions just before it on the same page, by `units.yaml` `table_unit_hint`), `is_artifact: bool`.
- `merge_continued(tables: list[dict]) -> list[Merge(part_table_ids: list[str], reason: str, decision:
  Literal["merged","hint"])]`: follow `continued_hint` chains; `continued_heading` ⇒ `merged` (header from the first
  part when a later part has none); `same_first_row` ⇒ `hint`.
- Row paths from label indentation (project owner, PR #1): in the label column, `indent = cell.bbox.x0 − min(x0 of that
  column's label cells)`; indent levels group offsets that differ by less than `indent_step_pt` (`units.yaml` table
  section, default 4 pt); a row's path = labels of the nearest preceding rows at each shallower level (kb
  `pipeline/tables.py` row-path behaviour). Cells with `bbox: null` get a flat path and `parsed` records
  `indent_unavailable`. Artifact detection is ported from kb `pipeline/tables.py` where it applies to cells.

- [ ] Tests: `test_parse_cell_parenthesised_negative` (`"(1,234)"` → −1234), `test_parse_cell_percent`
  (`"0.9%"`), `test_parse_cell_nil_symbols` (`"-"`, `"—"`, `"n.m."`, `""` → nil), `test_parse_cell_zero_not_nil`
  (`"0.0%"`), `test_parse_cell_unit_suffix` (`"S$1,443m"` → 1443, scale 6), `test_header_rows_joined_across_spans`,
  `test_unit_hint_from_preceding_text`, `test_merge_continued_heading`, `test_same_first_row_is_hint_only`, `test_row_path_from_label_indentation` (label x0 = 40, 48, 48, 40
  → paths `[A]`, `[A, B]`, `[A, C]`, `[D]`), `test_row_path_flat_when_bbox_missing`.
  Red → implement → green → commit.

### Task 17: Concepts — load and tag

**Files:** Create `src/kb_core/domains.py`, `src/kb_core/build/concepts.py`; Test `tests/test_concepts.py`

**Interfaces:** `load_domain(name: str) -> Domain` (concepts, edges, facts list, units, low_info, dict path);
`load_concepts(conn, domain) -> int` (upsert concept, concept_alias, concept_edge; validates ids/edges);
`tag_nodes(nodes: list[dict], tables: list[dict], domain) -> list[NodeConcept(node_id, concept_id, method:
Literal["manual","rule_title","rule_row_label","rule_dict"], confidence: float, evidence: str)]` — port of kb
`pipeline/concepts.py` r4 rules (priority manual > rule_title > rule_row_label > rule_dict; rule_dict needs ≥ 2 hits in
the node's own text near a number; filters F1′ shared-page split by title position, F2 other entities, F3 movement /
cash-flow stock rows, F4 auditor/policy passing mentions, F5 concept exclusions, F6 note families) and writes
`concept_tok`.

- [ ] Tests: port kb `tests/test_concepts.py` cases that do not depend on Doris/JSONL (rewrite fixtures as dicts),
  plus `test_f1_shared_page_split_by_title_position`, `test_other_entity_filtered`. Red → implement → green → commit.

### Task 18: Observations and fact merge

**Files:** Create `profiles/annual_report/observations.yaml`, `src/kb_core/build/observations.py`,
`src/kb_core/build/facts.py`; Test `tests/test_observations.py`, `tests/test_facts.py`

**Interfaces:**
- `observations.yaml`: table title patterns (kb's en/zh `Selected Income Statement Items` patterns, copied as data),
  year-header regex, default unit (`SGD million`), restatement footnote regex `(\d{4})\s*\(\d\)`.
- `extract(doc: dict, tables: list[InterpretedTable], domain, rules) -> list[Observation(obs_id, doc_id, concept_id,
  entity, fiscal_year, value: Decimal, unit, scale, restated: bool, table_id, page_no, row_label)]` — port of kb
  `profiles/annual_report/observations.py`.
- `merge(observations: list[Observation], documents: list[dict]) -> list[Fact]` — port of kb `pipeline/facts.py`:
  group by (concept, entity, fiscal_year); versions by report vintage; status `conflict` if values differ within a
  vintage, `agreed` if ≥ 2 docs, else `single`; `winning_obs_id` prefers the year's own report, then English; writes
  observation, fact, fact_version, fact_obs_link. Keep kb's cross-checks (prior-year comparatives, en/zh, multiple
  reports) exactly as kb implements them.

- [ ] Tests: `test_years_from_header_columns`, `test_years_from_preceding_text_when_header_lacks_them`,
  `test_restated_footnote`, `test_merge_agreed_single_conflict`, `test_winning_prefers_own_year_then_en`.
  Red → implement → green → commit.

### Task 19: All build stages, `kb-core facts` and step-2 acceptance

**Files:** Modify `src/kb_core/build/run.py` (from Task 12), `src/kb_core/cli.py`; Create `src/kb_core/eval/samples.py`;
Test `tests/integration/test_build.py`

**Interfaces:** `build_doc` (Task 12) gains the stages tables/merges → tags → observations, and its delete step also
clears the doc's concept/observation rows; `run_facts(conn) -> FactSummary(agreed, single, conflict,
metrics_covered)`; `content_digest` covers the new tables. `kb-core eval tree --seed N` / `eval concepts --seed N` write sample sheets
`eval/results/tree_<doc>_<seed>.yaml` (40 primary nodes with title, physical pages, parent title, blank verdicts).

- [ ] **Step 1:** Tests on the fixture package: `test_build_twice_identical` still passes with all stages,
  `test_facts_counts_on_fixture`. Red → implement → green → commit.
- [ ] **Step 2:** `uv run kb-core build --all && uv run kb-core facts` on the 6 OCBC packages. Record counts.
- [ ] **Step 3: Fact acceptance.** Expect 89 facts = 83 agreed / 6 single / 0 conflict, 14 of 15 metrics
  (`credit_costs` missing as in kb). Any difference: list each fact with the observations behind it and explain.
  A difference caused by missing package information is a stop condition (contract request); a difference caused by
  table parsing is fixed in Task 16/18 code.
- [ ] **Step 4: Tree eval.** Sample 40 nodes per document (new seeds, never tuned on); delegate judging (Tallyback
  task; constraints: read only the PDFs in `../intake-samples/ocbc/` and the sheets, D22 criterion); re-judge 10 per
  sheet myself. Pass = per document ≥ kb (`2025 zh 39, 2025 en 38, 2024 en 39, 2024 zh 35, 2023 en 37, 2023 zh 37`
  of 40) — if any document is lower and the cause is missing evidence in the package, stop and ask the project owner.
- [ ] **Step 5: Concept-tag eval.** 40 tagged primary nodes per language, same delegation; pass = node accuracy
  en ≥ 35/40 and zh ≥ 37/40 (kb r4). Commit sheets + summary; open PR "step 2"; independent review; merge.

---

## Phase D — Step 3 complete: index + retrieval (PR "step 3")

### Task 20: Concept and fact routes

**Files:** Modify `src/kb_core/retrieval/routes.py`; Create `queries/es/S6_node_concept_match.v1.json`,
`queries/pg/M*_*.v1.sql` (fact route, deepest-node lookup);
Test `tests/test_routes.py` (fake ES/PG), `tests/integration/test_routes_live.py`

**Interfaces:** Task 14 created the module with `TitleRoute`, `SummaryRoute`, `PageTextRoute`; this task adds
`ConceptRoute` and `FactRoute`. Port kb `service/routes.py` `RecallRoute` (attributes `name, unit, scored, gated, tier, structural,
layer`; methods `recall(query: Query, filters: Filters) -> list[Hit]`, `hay(hit) -> str`, `accept(hit, query) ->
bool`). Routes: `TitleRoute` (S1), `SummaryRoute` (S2), `PageTextRoute` (S3, page hits mapped to deepest covering
node via PG), `ConceptRoute` (S6, unscored, pool 200), `FactRoute` (PG `fact`, layer `fact`). Each route records its
template id and final DSL/SQL into the trace. `Hit(node_id, doc_id, score, rank, route, page_no | None)`.

- [ ] Tests: `test_concept_route_unscored`, `test_fact_route_layer_fact`. Red → implement → green → commit.

### Task 21: Fusion: links, aliases and remaining gaps

**Files:** Modify `src/kb_core/retrieval/fusion.py` (from Task 14); Create `src/kb_core/retrieval/aliases.py`; Test `tests/test_fusion.py`, `tests/test_coverage.py`

**Interfaces:** Task 14 built the core (idf, page_df, coverage gate, RRF, structure/text layers, budget); this task
adds the link layer, `cap_links`, group quotas, facts-first and the gaps that need concepts or facts. Full spec: port kb `service/search.py::_fuse` and helpers: `idf(df: int, n: int) -> float` =
`ln(1 + (n - df + 0.5) / (df + 0.5))`; `page_df(es, settings, units) -> dict[str,int]` (ES `_count` on
`page.text_tok`, cached per process); `coverage(hit_text, units, idf) -> float` (alias units all-or-nothing, df = 0
units skipped); `fuse(route_hits, ranking: dict) -> FusedResult` (gate at `coverage_threshold`, weighted RRF
`Σ w / (k + rank)`, layers fact > link > structure > text, a title counts as structure only if it contains an
informative token, `cap_links` at `link_per_group`, group_by/per_group quotas, budget 8,000 tokens with facts
outside the budget); gap codes as kb api-contract §4.4 (`over_filtered`, `section_missing_in_lang`,
`parallel_doc_available`, `tree_quality_low`, `page_label_unreliable`, `concept_unknown`, `unlinked_text_only`,
`truncated`). `expand_aliases(query, domain)` ports kb `service/aliases.py`.

- [ ] Tests: port kb's fusion/coverage unit tests (rewritten against plain dicts), plus
  `test_facts_bypass_budget`,
  `test_link_cap_two_per_group`. Red → implement → green → commit.

### Task 22: Remaining tools and the API contract

**Files:** Modify `src/kb_core/retrieval/search.py`; Create `src/kb_core/retrieval/{browse,concepts,facts}.py`,
`docs/api-contract.md` (kb's contract ported; §6 template list replaced by kb-core's ES/PG templates; storage
references updated); Test `tests/test_tools.py`, `tests/integration/test_tools_live.py`

**Interfaces:** `search` and `read` exist from Task 14 (they gain group_by/per_group and concept/fact layers);
new: `browse`, `resolve_concept`, `get_metric_series`. All: `search(params: dict) -> Envelope`, `browse(params) -> Envelope`, `read(params) -> Envelope` (≤ 5
pages; node_id xor page_range), `resolve_concept(params) -> Envelope`, `get_metric_series(params) -> Envelope` —
parameter names, defaults, envelope fields, tiers, source format and status values exactly as kb
`docs/api-contract.md` §4–5. `trace(call_id, session_id, tool, params, routes, dsl/sql per template, decisions,
duration)` → `quality.trace_event`.

- [ ] Tests: envelope shape per tool, `read` rejects both node_id and page_range, `get_metric_series` returns status
  and provenance (doc_id, physical page, printed page). Red → implement → green → commit.

### Task 23: Recall eval and step-3 acceptance

**Files:** Create `src/kb_core/eval/recall.py`; Modify `cli.py` (`kb-core eval recall <set>...`); Test
`tests/test_recall_eval.py`

**Interfaces:** port kb `scripts/eval.py` recall mode: single-point = limit 5, hit when a top-5 node's page range
overlaps a gold physical page in the same doc; with-year and without-year variants as kb; cross-year =
`group_by=fiscal_year`, per_group 3, every required year must hit. Writes `eval.eval_run/eval_result` and
`eval/results/recall_<timestamp>.json` (per-question top-k node ids).

- [ ] **Step 1:** Unit tests on the hit rule with fixture results. Red → implement → green.
- [ ] **Step 2:** `uv run kb-core reindex && uv run kb-core eval recall p1_questions p1_crossyear p1_v3` → expect
  with-year ≥ 21/21, without-year ≥ 17/21, cross-year ≥ 8/10; also run `p2_heldout` (kb 4/16) for information.
- [ ] **Step 3:** Commit; PR "step 3"; independent review; merge.

---

## Phase E — Step 4: serve (PRs "step 4a: API + MCP", "step 4b: UI")

### Task 24: Full HTTP API, admin and MCP tools

**Files:** Create `src/kb_core/serve/app.py`, `src/kb_core/serve/mcp.py`, `src/kb_core/serve/admin.py`,
`.mcp.json.example`; Test `tests/test_app.py`

**Interfaces:** Task 15 created `serve` with doctor gate and MCP `search`/`read`; this task adds the rest. Routes as kb api-contract §2/§8: POST `/v1/search`, `/v1/resolve_concept`, `/v1/get_metric_series`;
GET `/v1/docs/{doc_id}/tree`, `/v1/read`; admin GET `/v1/admin/docs`, POST `/v1/admin/import`, GET
`/v1/admin/runs`, `/v1/admin/traces`, `/v1/admin/traces/{call_id}`, `/v1/admin/evals`, `/v1/admin/sessions/{id}`;
GET `/v1/docs/{doc_id}/pages/{page_no}.png` (PyMuPDF render from the stored `source.pdf`, cached under
`store/cache/`), `/v1/docs/{doc_id}/pages/{page_no}/regions`; MCP at `/mcp` with the 5 tools and kb's agent rules
1–11 (kb `service/app.py` RULES_COMMON, translated text already English). `serve` runs doctor first and exits 1 on
failure; default host 127.0.0.1.

- [ ] Tests (TestClient + fakes): each tool route returns the envelope; `test_serve_refuses_when_doctor_fails`;
  `test_default_bind_is_localhost`; `test_page_png_served_from_store`. Red → implement → green → commit.

### Task 25: MCP demo and reindex invariance (step-4 acceptance, part 1)

- [ ] **Step 1:** `uv run kb-core serve` (background). Run one non-interactive MCP client session with `.mcp.json` pointing at
  `/mcp`, allowed tools = the 5 kb-core tools only, prompt = kb `eval/demo.yaml` questions: NPL ratio 2024 and 2025,
  net profit growth, LCR. Save the transcript to `docs/reports/round-1-mcp-demo.md`; check each cited number against
  the source page (doc_id, physical page, printed page).
- [ ] **Step 2:** Reindex invariance: save `eval recall` per-question top-k ids → delete both physical indexes →
  `kb-core reindex` → rerun → `diff` of the two result files is empty (excluding timestamps).

### Task 26: UI (3 views)

**Files:** Create `web/` (Vite + React 18 + TypeScript, structure like kb-intake `web/src/{App.tsx, api, components,
lib, pages, styles}`); built assets served by FastAPI at `/ui`; Test `web/src/**/*.test.tsx` (Vitest) and one
Playwright smoke test per view.

**Interfaces:** `web/src/api/client.ts` typed against `/v1/*` (types generated from FastAPI's OpenAPI into
`web/src/api/schema.d.ts` with openapi-typescript). Views:
1. `pages/Chat.tsx` — session list + messages; each answer shows tool calls with tier badges and citations
   (doc_id, physical/printed page) that link to view 3; live mode only when `/v1/admin/config` says LLM enabled,
   otherwise replay (decision 8).
2. `pages/Trace.tsx` — one call: per-route ranks, coverage gate pass/fail, tier decisions, final DSL/SQL per
   template.
3. `pages/Document.tsx` — tree (left), page image with region boxes (toggle by type), tables of the page; deep link
   `/ui/docs/:doc_id/pages/:page_no`.

- [ ] **Step 1 (main session):** app shell, router, API client, shared components (TierBadge, Citation); commit.
- [ ] **Step 2 (delegated, ≤ 3 subagents in parallel worktrees, registered in Tallyback):** one view each, constraints:
  only `web/src/pages/<View>.tsx` + its components/tests; no API changes; English text.
- [ ] **Step 3:** Integrate, `npm run build`, `npm test`, Playwright smoke against a live `serve`; independent review;
  merge PR "step 4b".

### Task 27: Round report

**Files:** Create `docs/reports/round-1-report.md`

- [ ] Final verification run: `uv run pytest -q`, `uv run lint-imports`, `uv run python scripts/check_contract.py`,
  `uv run python scripts/check_assets.py`, `uv run python scripts/check_constraints.py`, `uv run kb-core doctor`,
  `uv run kb-core migrate` (twice). Report (English): PR/commit list; evidence per step (commands + output
  summaries); comparison table vs kb (tree per doc, concept tags en/zh, facts 83/6/0, recall 21/21 · 17/21 · 8/10,
  held-out, MCP demo); delegation list (who, constraints, verification, conclusion; Tallyback ids); open issues and
  kb-intake contract requests.
