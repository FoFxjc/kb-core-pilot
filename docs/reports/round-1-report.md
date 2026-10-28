# kb-core round 1 report

2026-10-27. Design §10 steps 1–4: skeleton; packages, import, build and facts; index and retrieval; serve (HTTP, MCP
and three UI views). kb-core rebuilds kb's solution on Elasticsearch + Postgres, and its only input is kb-intake
contract v2 delivery packages. No kb database, JSONL or intermediate artefact was copied.

## 1. Results against kb

| check | kb-core | kb | target | status |
|---|---|---|---|---|
| doctor | passes (ES 8.19 and ES 7.10 compat profile) | — | passes | ✓ |
| migrate re-runnable | yes (advisory lock, sha check) | — | yes | ✓ |
| Tree spot check (D22, 40 nodes per document, seed 105) | 204/240 = 85% | 225/240 = 94% | no lower than kb | **below kb; accepted by the project owner** (§4.1) |
| Concept tags en (D39, 40 nodes, seed 107) | 35/40 | 35/40 | no lower than kb | ✓ |
| Concept tags zh (D39, 40 nodes, seed 107) | 37/40 | 37/40 | no lower than kb | ✓ |
| Facts agreed / single / conflict | 83 / 6 / 0 (89 facts, 408 observations, 14 of 15 metrics) | 83 / 6 / 0 (14 of 15) | 83 / 6 / 0 | ✓ |
| Recall with year (21 questions) | 21/21 | 21/21 | 21/21 | ✓ |
| Recall without year | 19/21 | 17/21 | ≥ 17/21 | ✓ |
| Recall cross-year (10 questions) | 9/10 | 8/10 | ≥ 8/10 | ✓ (after the project owner's ranking decision, §4.2) |
| Held-out, legacy wordings | 3/3 | 3/3 | info | — |
| Held-out, `p2_heldout` | 3/16 | 4/16 | info | one below kb (§5) |
| MCP demo (NPL 2024/2025, net profit growth, LCR) | all three answered; every cited number and page checked | — | agent completes it | ✓ |
| Reindex invariance | 0 of 69 per-question top-k lists differ | — | identical | ✓ |
| pytest / import-linter / contract check | see §3 | — | pass | ✓ |

Tree spot check per document (correct of 40):

| document | 2023 en | 2023 zh | 2024 en | 2024 zh | 2025 en | 2025 zh |
|---|---|---|---|---|---|---|
| kb-core (seed 105) | 33 | 35 | 34 | 33 | 37 | 32 |
| kb | 37 | 37 | 39 | 35 | 38 | 39 |

The recorded accuracies feed the `tree_quality_low` gap (`kb-core eval tree --record`). Documents under 85%
(2023 en, 2024 zh, 2025 zh) report it with every search hit.

## 2. Pull requests

| PR | content | state |
|---|---|---|
| #1 | design v1 (English), AGENTS.md, round 1 plan | merged |
| #2 | step 1: config, migrations, query templates, ES client and aliases, doctor | merged |
| #3 | slice: OCBC 2025 en end to end (import, tree, chunks, reindex, search, read, MCP) | merged |
| #4 | step 2: tables, concepts, observations, facts; two tree and tag rule rounds with judged evals | open, for the project owner |
| #6 | step 3: fact, concept and browse tools; gaps; api-contract; recall eval (stacked on #4) | open, for the project owner |
| #5 | first push of step 3 | superseded by #6 (force-push was not allowed); please close |
| step 4 | HTTP and admin API, five MCP tools, MCP demo, reindex invariance, three UI views (stacked on #6) | this report's PR |

## 3. Evidence per step

**Step 1, skeleton.**
- `kb-core doctor` checks: config, PG connect and version, ES version (minimum 7.10, warning below 8.0 that the
  vector route is unavailable), migrations, index aliases.
- `kb-core migrate` is re-runnable and refuses a migration whose sha changed.
- ES mappings use the `kb_ws` analyzer (whitespace + lowercase); jieba tokenises in Python.
- Live tests run against ES 8.19 and ES 7.10.

**Step 2, packages to facts.**
- Six packages were produced with the kb-intake CLI (default workflow, LLM off); `kb-intake check` passes on all.
- `kb-core import` validates contract v2 (schemas and sha256), keeps a read-only store copy and refuses a different
  delivery for an imported doc_id.
- `kb-core build` runs tree, sections, chunks, tables, concepts and observations. A rebuild gives an identical
  content digest, and tags are stable across rebuilds.
- `kb-core facts` gives 83/6/0.
- Judged sheets are in `eval/results/` (tree seeds 101–105, concept seeds 104, 106 and 107).

**Step 3, index and retrieval.**
- ES node and page indexes are versioned physical indexes behind aliases; reindex reads Postgres only.
- Five recall routes plus the fact route, the coverage gate, weighted RRF, layers, link cap, budget and kb's gap
  codes; queries come only from `queries/es/*.json` and `queries/pg/*.sql`.
- `docs/api-contract.md` is kb's contract with the storage sections rewritten.
- `kb-core eval recall` writes `eval.eval_run`/`eval_result` and a JSON file per run:
  `eval/results/recall_20261027T114712-73b0f3.json` (primary set) and `…114718-216912.json` (held-out).

**Step 4, serve.**
- HTTP: the five tools at kb's served routes, plus admin endpoints (documents, import, runs, traces, sessions,
  evaluations, full tree, page regions, config, replays).
- MCP: the five tools at `/mcp`, carrying kb's agent rules 1–11.
- The MCP demo and reindex invariance are in `docs/reports/round-1-mcp-demo.md`.
- UI: §3a.

**Test runs at the head of each branch** (PG 17.6, ES 8.19 and ES 7.10 running):

| branch | pytest | import-linter |
|---|---|---|
| step 2 | 240 passed | 1 contract kept |
| step 3 | 273 passed | 1 contract kept |
| step 4 | 302 passed; web: 46 Vitest tests and 4 Playwright smokes passed | 1 contract kept |

Repository checks at step 4: `scripts/check_contract.py --intake-repo <kb-intake checkout>` ("contract copy matches kb-intake",
source commit fc9b4b434a5a), `scripts/check_assets.py` (28 assets), `scripts/check_constraints.py` (constraints.txt
matches uv.lock). A clean `git archive` export of each branch also passes (integration tests skip without the services); the upstream
contract comparison needs a checkout of the kb-intake repository.

### 3a. UI

React 18 + Vite + TypeScript under `web/`. The built app is committed to `src/kb_core/serve/static` and served at
`/ui` with deep links; a rebuild gives identical hashed files. `client.ts` is typed against the generated OpenAPI paths.

- **Chat:** replays recorded MCP sessions (`/v1/admin/replays`; round 1 has no live chat). It shows questions, tool calls
  with tier badges and trace links, the answer with every citation linked to the document view, and gaps with severity.
- **Retrieval trace:** a call list with filters and paging. For one call it shows the request, results, gaps,
  per-route ranks per group, the coverage gate (pass or fail per candidate), tier decisions and every executed
  template's ES DSL or SQL.
- **Document & evidence:** a document picker with tree accuracy; the primary tree with concept chips and the nodes
  covering the page; the page image with region boxes toggled by type; page navigation by URL; the page's tables and
  text.

Each view has Vitest tests and a Playwright smoke test against the live OCBC data (`cd web && npm test`,
`npx playwright test`). All pass on the integrated build.

## 4. Decisions taken this round

1. **Tree accepted at 85% (project owner).**
   - kb took its in-section hierarchy from PageIndex Flash; kb-core builds it from the package's regions with
     layout rules, which is the design-level cause of the gap.
   - Two rule rounds raised the tree from 173/240 = 72% (seed 103) to 204/240 = 85% (seed 105).
   - After the step-2 review, 35 real headings that the subtitle rule had dropped were restored (Principle 1/6/9/11/13,
     "Allowances and Asset Quality", "Average Balance Sheet", "Our Opinion" and others). The 85% was judged before
     that fix; spot checks cannot show missing nodes, so the restored nodes are checked by hand only.
   - To revisit in round 2 with the UOB packages.
2. **A page hit counts toward one node (project owner).** kb maps a page-route hit to every deepest covering node. Because
   kb-core's tree splits some pages into several leaf nodes, cross-year recall was 7/10. Mapping each hit to the first
   covering node in reading order gives 9/10, with no loss elsewhere (plan note 15).
3. **Tag tightening (project owner).** `rule_dict` ignores passing mentions: regulatory minimums, sensitivities, insurance
   funds and dividend bases. The exclusion looks only at the hit's own sentence.
4. **Earlier rulings** (plan, PR #1): English design translation; packages first, then a vertical slice; CR-1 for
   font colour; table row paths from label indentation; doctor's ES minimum 7.10; and the main session executes,
   delegating only UI views, reviews and judging.

## 5. Open issues

- **CR-1** (`regions.font.color` in contract v2) is open with kb-intake. Note headings currently rely on numbering,
  size and weight.
- **Tree accuracy below kb** (85% vs 94%) on the judged samples; round 2.
- **Held-out wordings 3/16 vs kb 4/16** (information only). Not investigated this round.
- **Live chat** is not built. The Chat view replays recorded MCP sessions, and `/v1/admin/config` reports
  `live_chat: false`. A live mode needs an LLM tool loop behind `KB_CORE_LLM_ENABLED`.
- **Vector route** is not built (design: later or optional).
- **Deferred minor review findings:**
  - Step 2:
    - the content digest omits `fact.observation`;
    - `config_version` omits `node_concept_overrides.yaml`;
    - table indent levels round and kb's section-row rule is not ported;
    - `merge_continued` has no fan-in guard;
    - `picture` is a container type.
  - Step 3:
    - multi-issuer edge cases in the search fact layer;
    - browse drops `concept_ids` and does not enum-check `tree_source`;
    - contract §5.5 still names kb's admin facts endpoints;
    - test holes (derived metrics, `basis=both`, `include_obs`, other `group_by` values).
  - Step 4: page-route keys in trace detail are Python tuple reprs (`"('doc', 100)"`); the trace view parses them, but a
    structured key would be sturdier; `client.ts` types lag a few response fields (`events`, `demoted_link`).
    Also from the step-4 review:
    - UI fallback serves index.html for missing dotted files (no `Cache-Control: no-cache`);
    - a malformed `%` escape in a deep link throws in the router (no error boundary);
    - the trace list's "More" has no stale-response guard, and `PageImage` keeps the previous page's load state;
    - the citation regex keeps an `ocbc` alternative (the generic doc-id form already covers it);
    - a running server needs a restart to see accuracies recorded by another process;
    - the OpenAPI codegen adds little while routes return untyped dicts.
- **Process notes from the ledger:** some tests were written together with their code, so the failing run was not
  observed first. Where that happened the tests were checked by mutating the code: link cap, tree threshold.

## 6. Delegations (all registered in Tallyback, `.tallyback/` in the main checkout)

| who | what | constraints | verification | conclusion |
|---|---|---|---|---|
| reviewer (tsk_…3e3e6b316bd7, tsk_…486420287fc0) | PR #2 (step 1) | read-only | 3 findings reproduced as failing tests, fixed | accepted |
| reviewer (tsk_…0052b84959bf) | slice PR (#3) | read-only | important findings reproduced as failing tests, fixed | accepted |
| reviewer (tsk_…865ac283d7b1) | step 2 (#4) | read-only | subtitle and tag-window findings reproduced (node diff, lost tag), fixed RED→GREEN | accepted |
| reviewer (tsk_…d6f189bfa021) | step 3 (#6) | read-only | severity and issuer findings reproduced as failing live tests, fixed | accepted |
| 2 judges (tsk_…4fc269d54db0, tsk_…a06c83d58bba) | tree 2025 en, seeds 101/102 | PDF and sheet only, fresh agents | main session re-judged 10/10 of round 1; disputed items checked | accepted |
| 1 judge (tsk_…2dd257f6206b) | re-judge both 2025 en samples with the fixed rubric | PDF, sheet, rubric | spot checks | accepted |
| 6 judges (seed 103: tsk_…e116b9390b76, …0faa2558f153, …3769e68612c3; seed 105: …54b9236299d6, …5c79a050169c, …0bbb45340c88) | tree samples, seeds 103 and 105, two documents each | PDF and sheet only | sampled verdicts re-checked in the PDFs | accepted |
| 6 judges (seed 104: tsk_…5afe76b39b9f, …c2751955440f; 106: …c103ff0f5ccf, …bb7f266ec9ab; 107: …06e82319921a, …dc0dc589b2ab) | concept tags en/zh, seeds 104, 106, 107 | PDF and sheet only | sampled verdicts re-checked (e.g. seed 107: 2025 en p79, 2023 zh p121) | accepted |
| 3 UI workers (tsk_…c4ec133ddca0 chat, …e0e664a6048b trace, …d62f52789a3f document) | Chat, Retrieval trace, Document views | own worktree; own page and components only; no API changes | diffs checked in scope; tsc, Vitest and smokes rerun per branch and after integration; screenshot checked | accepted |
| reviewer (tsk_…472aecb6d571) | step 4 | read-only | error-envelope and repeated-key findings reproduced as failing live tests, fixed; report gaps fixed | accepted |
