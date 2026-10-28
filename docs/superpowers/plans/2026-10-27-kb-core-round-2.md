# kb-core round 2 implementation plan

> **For agentic workers:** follow AGENTS.md (development-workflow). Each work item below is one PR, reviewed by a
> subagent that did not write it before merge; every delegation is registered in Tallyback.

> Status: approved in outline by the project owner, 2026-10-27; decisions D1-D4 (section 2) use the recommended answers until
> The project owner says otherwise. Inputs: the round 1 report (`docs/reports/round-1-report.md`), the permissions and guardrails
> design (guardrails-v1, the project owner's project docs), the seed-to-query PoC brief, and the live chat run on 2026-10-27.

**Goal:** close the two quality gaps round 1 left (tree accuracy, held-out wordings), add the first batch of
permissions, and keep every round 1 number at least where it is.

**Where it runs:** on the local machine that holds the delivery packages, Postgres and Elasticsearch (the round 1
setup). W4 (live chat) is already merged (#8).

**Rules unchanged:** kb is read-only; blind evaluation (kb-core never reads kb's outputs); dev and test sets stay apart;
no batch model calls; paid model experiments report their cost and need approval before they run.

---

## 0. Where round 1 ended

| Check | kb-core | kb | Reading |
|---|---|---|---|
| Tree spot check | 85% (judged before the heading fix) | 94% | Stale, and a spot check cannot see missing nodes |
| Concept tags en / zh | 35/40 · 37/40 | same | Identical to kb: confirm they are computed independently (T0.1) |
| Facts agreed / single / conflict | 83 / 6 / 0 | same | As above |
| Recall with year / without / cross-year | 21/21 · 19/21 · 9/10 | 21/21 · 17/21 · 8/10 | Dev set, tuned against |
| Held-out wordings | 3/16 | 4/16 | Ahead on dev, behind on held-out: the signal to watch |
| Live chat (W4, #8) | three demo questions answered; injected 41.7% caught | - | Done |

Live run findings that feed this round: `resolve_concept("Common Equity Tier 1 ratio")` returned `concept_unknown`
(a common full wording missing from the aliases: W2); an answer stated a fact status in a turn without a fact-layer
call, and another gave numbers from a page it had not read (answer-gate rules: section 6, not this round).

---

## 1. Order and dependencies

```
T0 baseline ──┬── W1 tree ────────────────┐
              ├── W2 held-out ── W2 fixes ┼── T9 final eval (sealed set once) ── T10 report
              └── W3 permissions ─────────┘
W5 seed PoC (separate repo/branch, never touches kb-core state)
```

- W1, W2 and W3 touch different code and can run in parallel worktrees, but **only the main session writes Postgres /
  ES, rebuilds, migrates or edits copied assets** (AGENTS.md). Rebuilds are serialized: W1 first, then W2.
- Every PR re-runs the full regression (T0.3). A PR that lowers any round 1 number does not merge.

## 2. Decisions (recommended answers in use)

| # | Decision | Recommended | Why |
|---|---|---|---|
| D1 | Where W3 labels come from before kb-intake carries them | A kb-core label overlay `config/access_labels.yaml` (doc and block patterns), marked simulated, **plus** contract request CR-2 to kb-intake | Unblocks W3 now without changing kb-intake; the overlay is deleted when CR-2 lands |
| D2 | Who writes the new held-out set | A blind subagent (reads only the six source PDFs and the question format; cannot see `domains/`, `eval/heldout_terms.yaml` or the old 16) | Same method as round 1's subagent B, which passed the main-session checks |
| D3 | W3 demo roles | `public` (public only), `finance_analyst` (internal, domain finance), `finance_confidential` (confidential, domain finance) | Three roles show filtering and the embargo flip |
| D4 | How the embargo flip is demonstrated | `embargo_until` on `ocbc-group_ar_2025_en` plus a test-only clock override `KB_CORE_NOW` (ignored unless `KB_CORE_ALLOW_CLOCK_OVERRIDE=true`) | Deterministic demo and tests without waiting for a date |

## 3. T0 Baseline (main session, ~0.5 day)

- **T0.1 Blind check.** Explain why concept tags and facts equal kb's exactly. List every path kb-core reads
  (`kb-core doctor --inputs` or a script), showing no kb JSONL, database or eval result is read. Record the conclusion
  in the report.
- **T0.2 Clean-up.** Stop the old `kb-core serve` on 8200; remove the three view worktrees.
- **T0.3 Regression baseline.** On current `main`: rebuild from packages, run recall (with year / without / cross-year),
  concept-tag sheets, facts counts, held-out (old 16), reindex invariance. Save as `eval/results/baseline_round2/`;
  every later PR compares against it.
- **Done when:** baseline files committed; blind-check conclusion written; numbers equal or explainably different from
  the round 1 report.

## 4. Work items

### W1 Tree: re-measure and add a coverage check (PR "round 2 W1")

| Task | What | Files | Done when |
|---|---|---|---|
| T1.1 | Re-judge the spot check on fixed data: 40 nodes × 6 documents with **new seeds** (e.g. 201-206), per `eval/tree_rubric.md`; the main session re-judges ≥ 10 items per sheet | `eval/results/tree_*_20x.judged.yaml` | 6 judged sheets; accuracy recorded with `kb-core eval tree --record` |
| T1.2 | **Heading coverage check**: compare kb-core's primary-tree titles with a heading list drawn from the PDFs by a blind judge (not from kb's tree: blind rule). Normalize titles; report missed and extra per document | `src/kb_core/eval/coverage.py`, `kb-core eval headings`, `eval/headings/*.yaml` | Command and tests; per-document missed / extra lists |
| T1.3 | Classify missed and wrong nodes: running header, numbering rule, missing contents page, layout, merge, parent skip | report table | Every miss has a class |
| T1.4 | Fix by class in `build/tree.py`, `build/toc.py` or profiles (no document-specific rules in `src/`) | tree code, `profiles/` | Tests per class; rebuild; T1.1 sheets re-scored on the same seeds |

- **Targets:** spot check ≥ 92% overall (no document below 85%); missed headings ≤ 3% of the judged heading list.
- **Delegation:** T1.1 and T1.2 judging go to subagents (one per document pair, ≤ 4 at a time); T1.4 code may go to
  a worktree subagent; rebuilds and recording stay in the main session.

### W2 Held-out wordings (PR "round 2 W2")

| Task | What | Files | Done when |
|---|---|---|---|
| T2.1 | Attribute each of the old 16 held-out questions to its failing step: concept not recognised / wrong domain or route / evidence not recalled / ranked too low / answer assembly. Analyse separately the one kb answers and kb-core does not | `docs/reports/round-2-heldout.md` | 16 rows with trace ids |
| T2.2 | **New sealed held-out set** (D2): ≥ 20 questions, ≥ 8 en, ≥ 8 zh, ≥ 4 cross-year, wordings checked to appear on 0 pages of the six PDFs, gold from PDF pages with snippets | `eval/round2_heldout.yaml` (committed sealed: SHA-256 in the plan PR; nobody tunes on it) | Main session re-checks every snippet against the PDF; hash recorded |
| T2.3 | Fix by **class**: aliases for common full forms and abbreviations (e.g. "Common Equity Tier 1 ratio"), query-side normalisation, route rules. Domain pack edits are copied-asset changes: main session only, each listed in `ASSETS.md` as a kb-core change | `domains/banking/*.yaml`, `retrieval/concepts.py`, `ASSETS.md` | Old-16 and dev results improve; no dev regression |
| T2.4 | Guard: the held-out loader check still rejects any concept spelling that matches a held-out term (old and new lists) | `domains.py` checks, tests | Test proves the new sealed terms are rejected if added as aliases |

- **Targets:** old 16 ≥ 6/16 (they are dev now); the sealed set is run **once**, in T9, and must not be below kb's
  score on it.
- **Delegation:** T2.2 is a blind subagent (Tallyback task with the constraints above); T2.1 can be a subagent with
  read access to traces; T2.3 stays in the main session.

### W3 Permissions, first batch (PR "round 2 W3"; guardrails-v1 section 8, steps 1-2)

| Task | What | Files | Done when |
|---|---|---|---|
| T3.1 | Label schema: document and block `access` (`classification`, `domains`, `owner`, `embargo_until`, `label_source`) and computed `effective_access`. Source: overlay (D1). Contract request **CR-2** written for kb-intake | `migrations/00xx_access.sql`, `config/access_labels.yaml`, `docs/contract-requests.md` | Migration applies; import fills labels; a document without required labels is rejected at import |
| T3.2 | Labels only go up automatically; lowering needs an explicit overlay entry with a reason | `intake/importer.py` | Tests |
| T3.3 | Policy function with a decision-point interface: `decide(subject, resource) -> allow / deny + filter terms`; subject from `X-KB-Subject` (dev) and the MCP session; default subject `public` | `src/kb_core/access/policy.py` | Unit tests per role and label |
| T3.4 | Filter **inside** every route: ES filters on node and page indexes (labels copied by reindex), PG fact queries joined to visible observations | `queries/es/*.json`, `queries/pg/M*.sql` v2, `es/indexer.py` | Hidden docs never appear in any route's ranks (trace detail checked) |
| T3.5 | **Counts and gap codes over the visible scope only** (`hit_counts`, `hit_counts_unfiltered`, `over_filtered`, `parallel_doc_available`, `section_missing_in_lang`); facts recomputed from visible observations (value, status, version) | `retrieval/search.py`, `retrieval/facts.py` | Tests: hidden content changes no count, gap or fact status |
| T3.6 | Re-check every evidence id before returning; "no permission" and "does not exist" return the same error | `retrieval/core.py`, `read.py`, `browse.py` | Tests on read / browse of hidden nodes |
| T3.7 | Audit: subject, tool, ids returned, number filtered (audit only, never to the caller) | `quality.access_audit` migration, tracing | Rows written; not in tool responses |
| T3.8 | Embargo (D4): `embargo_until` hides the document from roles without clearance until the time passes | policy, tests | Flip demonstrated with the clock override |
| T3.9 | Live chat and MCP pass the subject through; the chat UI gets a dev role picker | `serve/chat.py`, `serve/mcp.py`, web | Same question, three roles, three different visible evidence sets |

- **Acceptance (T3):** the three roles ask the same five questions; each sees only its evidence, and nothing in
  counts, gap codes, fact status or errors hints at hidden content; across the embargo time the same question returns
  "no data", then the cited answer; permission regression tests run in CI with the rest.
- **Delegation:** T3.3 and T3.6 tests may go to a worktree subagent; migrations, reindex and query templates stay in
  the main session.

### W5 Seed PoC (parallel, outside kb-core state)

- As in the seed-to-query PoC brief: LightRAG first, pilot on `ocbc-group_ar_2025_en`, then **stop for cost
  confirmation**. Never writes kb-core's Postgres or ES; output is candidate files for review.

## 5. Close-out

- **T9 Final evaluation:** rebuild from packages; full regression versus T0.3; run the sealed held-out set once; W3
  acceptance with the three roles; live chat smoke (the four questions of 2026-10-27, English answers).
- **T10 Report** `docs/reports/round-2-report.md`: the section 0 table for round 2 plus W1 coverage, sealed held-out
  and W3 acceptance; per fix its failure class and effect on dev and sealed sets; the blind-check conclusion;
  decisions; open issues; every delegation with its Tallyback id.

## 6. Not in round 2

Structured data plane (Starburst); the Judge's LLM layer; model egress policy; mosaic-inference limits; the
`check_answer` tool; answer-gate rules beyond the number check (fact status only from tool output, no numbers from
unread pages: start of round 3); CR-1 (waiting on kb-intake); the vector route; the deferred minor review findings
from round 1 (cleared opportunistically when a PR touches that code).

## 7. Risks

- **Tuning to the judge:** W1 re-scores on the same seeds after fixes; the report must also give one fresh seed per
  document so the improvement is not a fit to the sample.
- **Overlay drift (D1):** the overlay is a stopgap; CR-2 must name the exact fields so the overlay can be deleted.
- **ES filter cost:** label filters on every route may change ranking; T3.4 compares dev recall with the `public`
  role off and on and explains any change.
