# Round 2 W3: permissions, first batch

Plan: `docs/superpowers/plans/2026-10-27-kb-core-round-2.md` W3 (T3.1-T3.9); design `docs/round-2-w3-access.md`.
Decisions D1 (label overlay + CR-2), D3 (three demo roles) and D4 (embargo with a test clock) are the project owner's.

## What is in place

| Task | Done |
|---|---|
| T3.1 labels | migration 0007 (document label, effective labels on nodes/pages/tables, `quality.access_audit`); overlay `config/access_labels.yaml` (simulated); import refuses a document without classification and owner; contract request CR-2 in `docs/contract-requests.md` |
| T3.2 labels only go up | an overlay entry can lower a stored label only with `lower: true` and a reason |
| T3.3 policy | `access/policy.py` (`decide`, `filter_terms`, `effective`, `now`), roles in `config/access_roles.yaml` (public, finance_analyst, finance_confidential; full_access for the regression gate) |
| T3.4 filter inside every route | ES node/page indexes carry access fields; every route and both hit counts filter; a live test checks that the ES filter agrees with `decide` for every role, label and time on ES 8.19 and 7.10 |
| T3.5 visible scope | documents a subject cannot see are unknown documents; available periods and parallel documents over visible documents; facts recomputed from visible observations (value, status, versions, availability) |
| T3.6 re-check, same error | read and browse re-check every node, page and table; a hidden node or page gives the same error as a missing one (tool calls and HTTP page image/regions) |
| T3.7 audit | one `quality.access_audit` row per call: subject, tool, returned ids, number hidden; never in a response |
| T3.8 embargo | `embargo_until` hides a document from roles without `embargo_exempt` until the time; `KB_CORE_NOW` works only with `KB_CORE_ALLOW_CLOCK_OVERRIDE=true`; live tests flip it |
| T3.9 subject everywhere | HTTP `X-KB-Subject`, MCP `X-KB-Subject` header, live chat `subject` per session; web dev role picker ("Viewing as", sends the header; page images name the subject in the query) |

Demo labels (simulated): `ocbc-group_ar_2025_en` internal to finance, embargoed until 2026-11-15 00:00 SGT; its
"Management Discussion and Analysis" confidential to finance; all other documents public.

## Gate (round 2 rule: full-access subject; public reported apart)

| Run | With year | Without | Cross-year | Old 16 | Facts |
|---|---|---|---|---|---|
| W2 (main) | 21/21 | 18/21 | 8/10 | 6/16 | 83 / 6 / 0 |
| W3, full_access | 21/21 | 18/21 | 8/10 | 6/16 | 83 / 6 / 0 |
| W3, public (outside the gate) | 12/21 | 8/21 | 6/10 | - | - |

Full access: 0 of 69 dev and 0 old-16 top-5 lists differ from W2 (filters do not change scores). Public: most
misses have their gold only in the 2025 English report, which is internal to finance; three without-year misses (q08,
v11, v15) also have gold on visible 2025 Chinese pages (corrected in the round 2 report review).

Acceptance with the three roles (five questions each, across the embargo time) and the live chat smoke run in T9.

## Known limits

- Labels are simulated (D1) until CR-2 lands.
- Admin traces, sessions, runs, evaluations and audit rows are an operator view and are not filtered by subject (design section 6).
- The dev role picker trusts the header; real authentication is out of scope for round 2.
- Facts are recomputed per call when a subject cannot see every observation of a concept (fine at this size).

## Review of the PR (independent subagent)

Fixed with tests (each failing first): search result outlines no longer name hidden sibling sections; concept node
counts count visible nodes only; the document tree endpoint is filtered and its error lists visible documents only;
search re-checks every candidate against Postgres labels and a missing label is visible only to full access (fail
closed; the ES filter no longer treats a missing classification as public); "labels only go up" now holds for
domains and embargo as well as classification.

Deferred (minor): a hidden page inside a read range can be inferred from the gap in returned pages; browse shows a
parent's full page range; term statistics for ranking (coverage IDF, BM25) include hidden pages; the search `doc_type`
enum is built from all documents; the audit count mixes units (pages, nodes, observations); roles are re-read from
disk per call; the subject is self-asserted (dev design).

## Evidence

Tests: `tests/test_access_policy.py`, `tests/test_access_labels.py`, `tests/test_access_scope.py`,
`tests/integration/test_access_es.py`, `tests/integration/test_access_live.py`, web `src/App.test.tsx`. Runs:
`recall_20261028T103457-0018e8.json` (full access, dev), `recall_20261028T103504-95b4f4.json` (full access, old 16),
`recall_20261028T103507-f8986f.json` (public, dev), `eval/results/w3/snapshot.json`.
