# Vertical slice on ocbc-group_ar_2025_en — report

Plan Phase B (Tasks 8–15), 2026-10-26. The slice ran import → tree → chunks → reindex → search → one MCP
question on OCBC 2025 en (all six OCBC packages were imported, built and indexed along the way). This report ends the
slice; the next phase starts only on the project owner's go-ahead.

## Outcome in one paragraph

The pipeline works end to end on ES + Postgres from kb-intake packages alone: an agent answered the NPL question over
MCP with the right value and correctly cited pages, and kb's 10 `p1_questions` already hit 10/10 with the year filter
(9/10 without). **The tree is below kb**: on two independent 40-node samples of 2025 en the judged accuracy is
33/40 (round 1) and 30/40 after a fix (round 2, strict judge; 35/40 under round 1's leniency), against kb's 38/40.
The largest remaining error class is design-level (heading levels from font size alone), which is a stop condition, so
two decisions are needed (last section).

## Stage counts (all six documents, current rules)

| doc | pages | regions | tables | tree nodes | notes / subnotes |
|---|---|---|---|---|---|
| ocbc-group_ar_2023_en | 296 | 4,373 | 206 | 532 | 49 / 58 |
| ocbc-group_ar_2023_zh | 220 | 3,582 | 160 | 373 | 49 / 58 |
| ocbc-group_ar_2024_en | 284 | 4,508 | 204 | 535 | 48 / 60 |
| ocbc-group_ar_2024_zh | 200 | 3,403 | 149 | 316 | 48 / 60 |
| ocbc-group_ar_2025_en | 276 | 4,159 | 201 | 556 | 48 / 59 |
| ocbc-group_ar_2025_zh | 196 | 3,201 | 145 | 338 | 48 / 59 |

- Packages: kb-intake CLI, default workflow, LLM off (`manifest.llm = {used: false}`), 6.0–9.3 min per document on CPU,
  every `kb-intake check` ok; folder sha12 equals each PDF's sha12.
- `kb-core import` ~3 s per package (full contract validation); re-import is a no-op.
- `kb-core build --all` ~6 s for six documents; a rebuild gives an identical content digest.
- `kb-core reindex` 2,650 nodes + 1,472 pages in under 2 s (1,472 pages is the page count kb reports).
- Section types: every contents entry is typed except the "Financial Statements" container (and its zh counterpart), as in kb.

## Tree evaluation (kb D22 protocol: title, page range and parent all correct; 40 nodes; new seeds)

| round | rules | seed | judge | correct | notes |
|---|---|---|---|---|---|
| 1 | as first built | 101 | subagent, PDF only | 33/40 | main session re-judged 10 (7 wrong + 3 right): 10/10 agree |
| 2 | + six heading rules (below) | 102 | fresh subagent, PDF only | 28/40 strict | 33/40 if a node may skip a same-level intermediate heading (round 1's judge accepted such cases) |
| 2, after regression fix | + running-header fix | 102 | same verdicts | 30/40 strict / 35/40 lenient | two misses were caused by my round-1 fix and are fixed (note 37, 37.2 end on p209 now) |
| kb (reference) | toc_flash | 41 | kb main session | 38/40 | `eval/baseline/tree_eval.yaml` |

Rules added after round 1 (all in `profiles/annual_report/tree.yaml`, generic): callout fragments ending in a function
word, `Table N:` captions, headings inside a table's box and labels smaller than body text are not headings; a node
extends onto the next node's page when body text precedes that heading (running headers excluded), and to the last
page of its own "(continued)" heading. Round 2 was judged on a new seed, never on the sample the rules were fixed on.

Remaining misses in round 2 (after the regression fix), by class:

| class | items | nature |
|---|---|---|
| Same-size nesting: committee bullets under "Board Committees", countries under "Southeast Asia" are the same font size as their heading, so nesting by size makes them siblings | 5 | **design-level**: font size alone cannot give heading levels; kb took this hierarchy from PageIndex Flash |
| kb's own contents-page rules: a divider page joins the next section (MD&A starts on the divider p96, heading on p98); a contents group title is printed only on the contents page | 2 | inherited from kb unchanged; a strict judge would fail kb's tree on these too |
| Section ends: "Key Audit Matters" runs to p122 (repeated table headers), a committee bullet ends on p56 | 2 | rule gaps |
| A job-title line ("CEO Bank of Singapore") under a name heading taken as a heading | 1 | rule gap |

Judged sheets: `eval/results/tree_ocbc-group_ar_2025_en_101.judged.yaml`, `..._102.judged.yaml`.

## One MCP question (kb q01)

A non-interactive MCP client with only the kb-core MCP server (`search`, `read`), session header `slice-q01`:
"What was OCBC's non-performing loan (NPL) ratio at the end of 2025?" — 5 turns, 1 search + 2 reads (traced in
`quality.trace_event`, source `mcp`).

Answer: **0.9%** as at 31 December 2025, citing (ocbc-group_ar_2025_en, physical page 100, printed page 98) and
(ocbc-group_ar_2025_en, physical page 105, printed page 103). Checked against the stored pages: p100 reads "NPL ratio
remained unchanged at 0.9%", p105 holds the NPA table with the NPL ratio column. kb's gold pages for q01 are 13, 100,
105. The agent also relayed the gaps (concept not yet tagged, tree quality not yet checked).

## Search smoke test (kb `p1_questions`, top 5, kb's page-range hit rule)

With the year filter 10/10; without 9/10 (q02 "Why did net interest income decline in 2025?" misses). The full recall
evaluation (31 questions) is Task 23.

## Review and fixes

Independent review of the slice (subagent, read-only): PASS WITH ISSUES, no critical findings. Fixed with a failing
test first: a package without page labels now falls back to the generic tree with `page_label_unreliable` /
`tree_fallback_generic` build gaps; traces keep compact results (no page text, no base64 images); import, listing and
the ES per-document delete moved into `queries/` templates; the stored package folder is read-only and a stale store
copy of a different delivery is refused; `/v1/search` no longer blocks the event loop; build notes (including "font
colour not in package") become build gaps. A bare `build/` line in `.gitignore` had kept `src/kb_core/build/` out of
the commits; fixed, and every PR now also runs the suite from a clean `git archive` export (168 passed, 1 skipped:
the upstream contract comparison needs a checkout of the kb-intake repository).

## Delegations (all registered in Tallyback)

| who | what | constraints | verification | conclusion |
|---|---|---|---|---|
| reviewer (PR #2) | review of step 1 | read-only | 3 findings reproduced as failing tests, fixed | accepted |
| judge round 1 | 40 tree nodes, seed 101 | PDF + sheet only | main session re-judged 10/10 | accepted (33/40) |
| reviewer (slice) | review of Tasks 8–15 | read-only | important findings reproduced as failing tests, fixed | accepted |
| judge round 2 | 40 tree nodes, seed 102 | PDF + sheet only, fresh agent | main session checked the disputed items in PDF spans | accepted (28/40 strict) |

## Decisions needed

1. **Judging standard.** The two judges disagreed on whether a node that skips a same-level intermediate heading is
   wrong, and the strict judge also fails kb's own contents-page rules (divider pages, contents-only group titles).
   kb's 38/40 was judged by kb's main session. Recommended: fix one written rubric (my proposal: skipping a real
   intermediate heading is wrong; kb's divider-page and group-title rules are accepted as kb's design) and re-judge
   both samples with it, so the comparison with kb is fair.
2. **Hierarchy evidence for same-size headings (design-level).** Options:
   (a) rules from layout already in the package — a bullet-prefixed heading nests under the preceding non-bullet heading
   of the same size, and a run of same-size headings in one column under a heading set apart by position (cheap, generic,
   recommended first);
   (b) PageIndex Flash as an in-section hierarchy source rather than only a witness (closest to kb's 38/40, changes
   design §3.1 / §11.1);
   (c) a contract request to kb-intake for heading level hints (Docling does not provide levels, so probably not useful).
   Recommended: (a), then one new-seed judging round on all six documents in Phase C as planned, keeping the stop rule.
