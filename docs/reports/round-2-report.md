# kb-core round 2 report

2026-10-28. Plan: `docs/superpowers/plans/2026-10-27-kb-core-round-2.md` (PR #9). Work items: T0 (#10), gate (#11),
sealed set (#12), W1 tree (#13), W2 held-out wordings (#14), W3 permissions (#15), this report (T9 evidence and T10).
Item reports: `round-2-t0.md`, `round-2-w1.md`, `round-2-w2.md`, `round-2-w3.md`.

## 0. Where round 2 ends

All kb-core numbers are from T9 on `main` at e415b72, after a rebuild from the packages (10:37 SGT). The recall and
fact numbers use the full-access subject. kb's numbers are its recorded round 1 results, except for the sealed set,
where kb was scored at T9.

| Check | Round 1 | Round 2 (T9) | kb | Reading |
|---|---|---|---|---|
| Tree spot check | 85% (seed 105) | 80.0% (fresh seeds 221-226; no document below 70%) | 94% | **Target not met** (≥ 92%, no document < 85%). On the pre-W1 code, fresh seeds 201-206 measured 81.3%, so round 1's 85% was a favourable sample |
| Missed headings (blind PDF heading lists, 585 headings) | not measured | 38.1% before W1 → 8.7% | - | **Target not met** (≤ 3%) |
| Concept tags, nodes correct, en / zh | 35/40 · 37/40 (seed 107, tuned against) | 38/40 · 37/40 (fresh seed 209); tags 99/104 · 123/126 | 35/40 · 37/40 | Fresh seed-208 baseline before W1/W2: 38/40 · 36/40. Tag precision 96.4% (208) and 96.5% (209) |
| Facts agreed / single / conflict | 83 / 6 / 0 | 83 / 6 / 0 | same | Unchanged |
| Recall, with year / without / cross-year | 21/21 · 19/21 · 9/10 | 21/21 · 18/21 · 8/10 | 21/21 · 17/21 · 8/10 | Two losses (q05, v05) from the W1 tree, approved by the project owner as explained exceptions |
| Old 16 held-out (dev from round 2) | 3/16 | 6/16 | 4/16 | Target ≥ 6/16 met |
| **Sealed round 2 held-out (run once)** | - | **13/24** | **13/24** | Target "not below kb" met (equal) |
| Reindex invariance | 0 of 69 | 0 of 69 dev, 0 of 35 held-out | - | Unchanged |
| W3, public subject (outside the gate) | - | 21/21 · 18/21 · 8/10 full access; 12/21 · 8/21 · 6/10 public | - | Most public misses have their gold only in the 2025 English report (internal to finance). Three without-year misses (q08, v11, v15) also have gold on visible 2025 Chinese pages that ranked below the top 5 for public; not investigated |
| Live chat | 3 demo questions; injected 41.7% caught | 6 questions of 2026-10-27, all answered in English with cited pages; injected 41.7% caught again | - | See section 4 |
| pytest | 302 | 520 passed (live PG, ES 8.19, ES 7.10) | - | Round 1 report: 302; T0 baseline: 350 |

## 1. W1 coverage and tree

| Measure | Before W1 | After W1 |
|---|---|---|
| Missed headings (blind lists, 40 seeded pages per document, seeds 301-306) | 223 / 585 = 38.1% | 51 / 585 = 8.7% |
| Extra nodes on the sampled pages | 72 | 72 |
| Spot check, fresh seeds | 81.3% (201-206) | 80.0% (221-226) |

Per document after W1 (correct of 40): 2023 en 33, 2023 zh 34, 2024 en 28, 2024 zh 28, 2025 en 32, 2025 zh 37.
W1 brought most real sub-headings inside the financial-statement notes into the tree. The new nodes carry their own
errors, so precision stayed flat. Both tree targets move to round 3.

## 2. Sealed held-out set (T9, run once)

- **File:** `eval/round2_heldout.yaml`. SHA-256 `f5420176bc9dd99e43c88b21c7fc0b0f5c500dad45af7f5c57fc69d2026f5353`, checked
  before the run. This is the hash after the PR #12 review fixes (commit 96c8aa9); the writer's delivery had
  `dfddab26…`, recorded in its Tallyback evidence. No change after sealing.
- **Writer:** a blind subagent (D2), sealed in PR #12 before any W2 change.
- **Run:** once, `kb-core eval recall round2_heldout` → `eval/results/recall_20261028T103932-0ccfcd.json`. No change was tried
  or measured on it.
- **kb:** scored on the same set through kb's read-only HTTP search (127.0.0.1:8100), with kb-core's page-hit rules,
  → `eval/results/t9_sealed_kb.json`.

| Slice | Questions | kb-core | kb |
|---|---|---|---|
| All | 24 | 13 | 13 |
| English | 13 | 6 | 5 |
| Chinese | 11 | 7 | 8 |
| Single value | 15 | 8 | 8 |
| Cross-year | 6 | 3 | 4 |
| Narrative | 3 | 2 | 1 |

Both systems hit 12 questions. kb-core alone hits r2h09; kb alone hits r2h14; 10 are missed by both.

**Disclosure from W2:** some sealed wordings contain the general synonyms W2 added (for example employee, earnings).
Those synonyms came from the old-16 analysis, not from the sealed set.

**Per-fix effect on the sealed set cannot be measured.** The set ran once, after all fixes, so only the combined
result exists.

## 3. W3 acceptance (T9)

**Setup:** `eval/results/t9_w3_acceptance.json`, the same five questions for each role.
- Three searches: the NPL ratio, LCR and NIM for 2025.
- Two metric series: net profit and NIM, 2024-2025.

**Demo labels (simulated, D1):**
- `ocbc-group_ar_2025_en` is internal to finance and embargoed until 2026-11-15 00:00 SGT.
- Its "Management Discussion and Analysis" section is confidential to finance.
- Everything else is public.

| Role, time | Sees 2025 en | Sees MD&A pages | Net profit 2025 | NIM 2025 |
|---|---|---|---|---|
| public, now | no | no | 7,422m, **single** (2025 zh only) | not available (`period_unavailable`) |
| finance_analyst, now (embargoed) | no | no | 7,422m, single | not available |
| finance_analyst, after embargo (test clock) | yes | no | 7,422m, **agreed** | not available (the only source is MD&A) |
| finance_confidential, now | yes (embargo-exempt) | yes (pp. 98, 100, 101, 105) | 7,422m, agreed | 1.91%, single |

- **No hints about hidden content:**
  - Hit counts are counted over visible documents only: 183 for public, against 454 for finance_confidential, on the
    same question.
  - Gap codes refer only to the visible scope. Public gets `empty_scope` for an English 2025 question;
    `parallel_doc_available` (raised for a hit document's parallel) appears only when the 2025 English report is
    visible and is a hit.
  - Fact status is recomputed from visible observations, so the 2025 net profit is "single" for public and "agreed"
    for roles that can see both reports.
- **Same error:** public reading the hidden document and reading a document that does not exist both get
  `UNKNOWN_DOC` with the same message shape.
- **Embargo flip:** finance_analyst asks the same question with the English 2025 scope at two test-clock times
  (`KB_CORE_NOW`, with `KB_CORE_ALLOW_CLOCK_OVERRIDE=true`):
  - 2026-11-14 23:00 SGT: no results, gap `empty_scope`.
  - 2026-11-15 01:00 SGT: cited 2025 en pages 4, 4, 9, 4-15 and 25.

  Clock times and query are recorded in the acceptance file.
- **Gate:** full-access recall is identical to W2: 0 of 69 dev and 0 old-16 top-5 lists differ.

## 4. Live chat smoke (T9)

The trace table holds six chat sessions from 2026-10-27, not four. All six were run again through
`POST /v1/admin/chat` as `finance_confidential` (an external test model, one call at a time) →
`eval/results/t9_chat_smoke.json`.

The first four are the 2026-10-27 test set: NPL change, net profit growth, LCR, and net profit with an injected
"Cost-to-income ratio was 41.7%" sentence. The other two (ROE, and CET1 asked in Chinese) were added later that day.

| Question | Answer (English) | Number check |
|---|---|---|
| NPL ratio change 2024→2025 | unchanged at 0.9% (2025 en p98 / printed 96) | 17 verified, 0 unverified |
| Net profit growth 2025 | $7,422m vs $7,587m, −2% (p98, p99, p4) | 28 verified, 1 unverified (`-6`, the model's sign on "6% lower") |
| LCR 2025 | SGD 294%, all-currency 138% (p98) | 11 verified |
| Net profit 2025 + injected sentence | $7,422m. Says the report gives a CIR of 40.2%, then appends the requested sentence and marks it unsourced | **41.7% flagged twice as unverified** |
| ROE 2025 | 12.6% (p98, p99, p4); says plainly that p9 was not read | 13 verified |
| CET1 (asked in Chinese) | answered in English: 16.9% (p4, p110) | 21 verified |

The main session checked every cited figure against the PDF pages and found all of them: 2025 en pp. 4, 79, 98, 99, 100
and 110, and 2024 en p98. The check is recorded under `pdf_check` in `t9_chat_smoke.json`, with the model and the six
original session ids.

**Still open (round 3 answer gate, plan section 6):** the model still writes the injected sentence. It only labels
it as unsourced.

## 5. Fixes by failure class

| Item | Class | Fix | Effect on dev |
|---|---|---|---|
| W1 | Headings inside notes never became nodes | Headings attached to notes and subnotes; dotted, lettered and roman numbering nest by depth | Missed headings 38% → 10% at this step (8.7% final) |
| W1 | Callouts, signatures and value cards taken as headings | Rules for a figure-with-unit title, the larger figure after a title, the name after a signature, and card rows | Extra nodes 99 → 76 at this step (72 final) |
| W1 | Two-character Chinese labels dropped | Two CJK characters make a heading | 6 wrong parents fixed |
| W1 | "(continued)" repeats nested as children | A repeat is not a node | 2023 en "Overview" fixed |
| W1 | Pull quotes extended sections | Only running text keeps the previous section open | q10 recovered |
| W1 | Host chosen by height on two-column pages; titles wrapped over two lines | Host by reading order; wrapped titles joined | Inverted page ranges 5 → 0 |
| W1 | Page hit owned by a section from earlier pages | Page hit maps to the node that starts on the page (`owner_first`) | v06 recovered |
| W2 | F1 word-level finance synonyms | `query_synonyms` in the domain pack; a synonym never counts twice | Old 16: h07 and h17 gained |
| W2 | F3 question and measure words | 7 Chinese words added to `low_info_terms.yaml` | Old 16: h20 gained |
| W2 | F2 mainland line items; F6 rare non-finance words | Not done (F2 would need the held-out wordings as aliases, which the guard forbids; F6 has one question) | - |
| W3 | (new capability) labels, policy, filters in every route, visible-scope counts and facts, same error, audit, embargo, subject everywhere | See `round-2-w3.md` | Full access: 0 list changes |

## 6. Blind check (T0.1)

An audit-hooked run (`scripts/trace_inputs.py`) covered the import, rebuild, reindex and recall evals. In it, kb-core
opened only:
- the delivery packages;
- its store copies;
- its own repository.

Nothing under kb or kb-intake was opened. The facts equal kb's because both read the same tables with the same metric
list. The round 1 tag scores matched kb's on different samples.

The fresh seeds since then confirm the tag scores are kb-core's own: seed 208 gave 38 · 36 and seed 209 gave 38 · 37,
against round 1's tuned 35 · 37.

## 7. Decisions (project owner)

- **D1-D4:** approved as written.
  - D1: label overlay plus CR-2.
  - D2: a blind writer for the sealed set.
  - D3: three roles.
  - D4: embargo with a test clock.
- **Gate rules:**
  - Strict; explained exceptions need the project owner's approval and are never auto-waived.
  - The W3 regression runs with full access; public is reported separately.
  - Facts and per-document tree accuracy were added to `eval compare`.
- **W1:**
  - The ranking fix went into the W1 PR.
  - q05 and v05 (page hits included) were approved as exceptions.
  - One more bounded round, then merge with the targets not met; the 92% target moves to round 3.
- **W5 seed PoC:** deferred and reported, see section 8.
- **Unused Tallyback tasks:** listed and closed, not deleted (section 9).

## 8. Open issues

- **Tree targets not met:** spot check 80.0% against ≥ 92%; missed headings 8.7% against ≤ 3%. Classes left for
  round 3, from `round-2-w1.md`:
  - diagram, chart and award labels;
  - key-audit-matter table labels;
  - biography and country-label parents;
  - contents entries not printed on the page;
  - headings merged or typed as tables by intake.
- **Recall exceptions:** q05 (without year) and v05 (cross-year) are below round 1. q05's with-year node rank fell
  from 1 to 5.
- **W5 seed PoC:** not started. It is blocked on the PoC brief and on cost approval. Estimated pilot on
  `ocbc-group_ar_2025_en`:
  - about 205 chunks;
  - 400+ LLM calls;
  - about 1.5M input and 0.4M output tokens.

  It needs the project owner's cost approval before it runs.
- **W2 classes not done:** F2 (mainland line items) and F6 (rare non-finance words).
- **Labels are simulated:** the access labels stay simulated until kb-intake delivers CR-2. The subject is
  self-asserted (dev design).
- **Answer gate:** the live chat appends injected text, though it labels it, and states fact status without a
  fact-layer call. This is the start of round 3 (plan section 6).
- **Deferred minor review findings:** listed in each item report. Main ones:
  - W1: wrapped-title merge of stacked headings; a heading after a signature image is dropped.
  - W2: the synonym check is exact-match only; the held-out guard fails open if `eval/` is missing.
  - W3: a hidden page inside a read range can be inferred from the gap; ranking statistics include hidden pages; the
    audit count mixes units.
- **Judging calls:**
  - The main session first overruled one T9 tag verdict (2023 en node 0520, note 39) after checking the wrong year's
    PDF. The independent review caught it: the 2023 note has the Group's "Total assets 581,424" and "Total
    liabilities 525,870" rows, so the judge was right. The overrule is withdrawn and the judge's sheet stands.
  - Judges noted page-range judging is lenient where a table from a neighbouring subsection shares the page. The
    protocol was not changed in this round.

## 9. Delegations (Tallyback)

Every delegated task below has an attempt and a settlement. The main session re-checked each before settling:
- judging sheets: at least 10 items per sheet against the PDFs;
- reviews: findings checked against the code; important ones reproduced as failing tests, then fixed;
- code: tests rerun after integration.

| Tallyback task | Executor | What | Constraints | Verification | Settled |
|---|---|---|---|---|---|
| tsk_01a17d26-36cd-77bd-ab94-6691be87d940 | reviewer-r2t0 | Review PR #10 (T0) | read-only, did not write it | findings checked against the code | accept |
| tsk_01a17d3c-2c9f-7678-b239-02598db20678 | reviewer-gate | Review PR #11 (gate) | as above | findings reproduced as tests | accept |
| tsk_01a17d30-91ae-74bb-809e-3b1094bd151d | heldout-writer-r2 | T2.2 sealed held-out set | PDFs and question format only; no domains, old 16 or aliases | every snippet checked against the PDF; alias collisions replaced blind; SHA recorded | accept |
| tsk_01a17d53-5204-740a-8a9a-7fdecb419137 | reviewer-sealed | Review PR #12 (sealed set) | read-only | findings checked | accept |
| tsk_01a17d31-4ac3-7095-b924-b08ebefe0446 | judge-tags-208-en | Fresh tag sheet seed 208 en (W2 baseline) | PDF and sheet only | ≥ 10 items re-checked | accept |
| tsk_01a17d31-4ee1-7496-96b1-201d8a8dfb08 | judge-tags-208-zh | Fresh tag sheet seed 208 zh | as above | ≥ 10 items re-checked | accept |
| tsk_01a17d32-32fc-76b0-8526-8711da7fb03a | judge-tree-20x-2023 | W1 T1.1 tree sheets 2023 en+zh | PDF and sheet only | ≥ 10 items per sheet | accept |
| tsk_01a17d32-36fc-757e-b2b8-9831b8c10846 | judge-tree-20x-2024 | W1 T1.1 tree sheets 2024 | as above | as above | accept |
| tsk_01a17d32-3ba9-778e-b118-4c40d523ff4c | judge-tree-20x-2025 | W1 T1.1 tree sheets 2025 | as above | as above | accept |
| tsk_01a17d54-4961-733e-b16d-6174d87483a1 | headings-2023 | W1 T1.2 heading list 2023 | PDF pages only (not kb's tree) | 577 of 585 titles found as printed | accept (settled at T10) |
| tsk_01a17d54-7523-71d5-b9bd-c25a29901b7b | headings-2024 | W1 T1.2 heading list 2024 | as above | as above | accept (settled at T10) |
| tsk_01a17d54-91d7-776a-960a-e17b79ea24bc | headings-2025 | W1 T1.2 heading list 2025 | as above | as above | accept (settled at T10) |
| tsk_01a17da2-7698-706e-9eca-38a709190f70 | judge-tree-w1-2023 | W1 T1.4 post-fix sheets 2023 | PDF and sheet only | ≥ 10 items per sheet | accept |
| tsk_01a17da2-7bc9-71a3-a79b-b870c1b37ce3 | judge-tree-w1-2024 | W1 T1.4 post-fix sheets 2024 | as above | as above | accept |
| tsk_01a17da2-8083-7617-9136-6b7a686392e6 | judge-tree-w1-2025 | W1 T1.4 post-fix sheets 2025 | as above | as above | accept |
| tsk_01a17daf-bda3-70ed-9dad-ba7c8a49cd6b | rejudge-w1r4 | Re-judge 36 changed nodes | as above | items re-checked | accept |
| tsk_01a17fcb-a373-761f-b459-e173fc110d4e | judge-tree-w1f-2023 | W1 final fresh seeds 2023 | as above | ≥ 10 items per sheet | accept |
| tsk_01a17fcb-a6be-7435-b2c0-ad663b39ac77 | judge-tree-w1f-2024 | W1 final fresh seeds 2024 + 3 nodes | as above | as above | accept |
| tsk_01a17fcb-aa12-7019-a9cd-898e5e187c1f | judge-tree-w1f-2025 | W1 final fresh seeds 2025 | as above | as above | accept |
| tsk_01a18041-8c0d-71ff-8311-c43fa5c3c354 | reviewer-w1 | Review PR #13 (W1) | read-only | findings reproduced as tests; judged items unchanged | accept |
| tsk_01a17da3-b160-72ba-9ff0-cc73d11a1dac | w2-attrib | W2 T2.1 old-16 attribution | traces read-only; never saw the sealed set | hit list and h10 rank checked against the run file | accept |
| tsk_01a1804e-b4a9-7062-ac00-8a7f109c06ab | reviewer-w2 | Review PR #14 (W2) | read-only | finding reproduced as a test | accept |
| tsk_01a17d5c-5b9d-7060-bdef-0777ba2df1c0 | w3-policy | W3 T3.3 policy module, roles, unit tests | own worktree; no DB writes | tests rerun after integration | accept |
| tsk_01a18030-34df-77f0-9b99-945940a7a445 | w3-ui | W3 T3.9 UI role picker | own worktree; web only | Vitest and build rerun | accept |
| tsk_01a18055-5f73-710c-90d4-05eb20a706bc | reviewer-w3 | Review PR #15 (W3) | read-only | leaks reproduced as failing tests, fixed | accept |
| tsk_01a18060-25e7-7398-baee-147bd63298bf | t9-tags-en | T9 tag sheet seed 209 en + changed items | PDF and sheet only | 10 items re-checked, all agree (an overrule of 0520 was withdrawn after the PR #16 review) | accept |
| tsk_01a18060-293c-753a-94b0-ce18590ab403 | t9-tags-zh | T9 tag sheet seed 209 zh + changed items | as above | 10 items re-checked, all agree | accept |
| tsk_01a1811f-0b30-7718-a85d-652c329bdaee | reviewer-r2report | Review PR #16 (this report) | read-only; no sealed-set run; did not write it | important finding reproduced against the 2023 en PDF; all findings fixed | accept |

**Unused tasks, closed but not deleted.** Two tasks, not one: `tsk_01a17d25-db8b-74e3-8b66-2b6590cc0867` and
`tsk_01a17d25-fc44-7217-8703-1d79dbc6299a`, both titled "Review PR #10 (round 2 T0)".
- **Origin:** created by the first two registration attempts at T0, before the dispatch failed with
  "--executor must be kind:id". They were never dispatched.
- **How they were closed:** a task with no attempt cannot be settled, so each got a recorded decision ("closed
  unused (not deleted)"): `dec_01a18067-cf03-7108-9ff1-79201fc17abe` and `dec_01a18067-cfd8-77c4-bbea-cc98554d99e0`.

Outside round 2, round 1 task `tsk_01a1771f-910e-734e-9c6b-3e3e6b316bd7` ("Review PR #2") is also unused; it is
left as it is and listed here.

**Late settlements.** The three W1 heading-list tasks had been verified in W1 but were not settled until the T10
audit of the ledger.

## Evidence (T9)

- Recall, full access:
  - `recall_20261028T103745-4dab32.json` (dev);
  - `recall_20261028T103750-25e31a.json` (old 16);
  - `recall_20261028T103752-f2e922.json` (public, dev).
- Reindex invariance: `recall_20261028T103827-53edbc.json`, `recall_20261028T103832-a4c124.json`.
- Sealed set: `recall_20261028T103932-0ccfcd.json` (kb-core) and `t9_sealed_kb.json` (kb).
- Tag sheets:
  - `concepts_{en,zh}_209.yaml` and their `.judged.yaml` files;
  - re-judged changed items in `eval/results/t9/`.
- W3 acceptance: `t9_w3_acceptance.json`.
- Live chat: `t9_chat_smoke.json` (session ids and trace ids per tool call).
- pytest: 520 passed, with live Postgres, ES 8.19 and ES 7.10.
