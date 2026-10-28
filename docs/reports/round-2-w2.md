# Round 2 W2: held-out wordings

Plan: `docs/superpowers/plans/2026-10-27-kb-core-round-2.md` W2 (T2.1-T2.4).

## Results

| Measure | After W1 | After W2 | Target |
|---|---|---|---|
| Old 16 held-out (now dev) | 3/16 | 6/16 | >= 6/16 (met) |
| Recall with year / without / cross-year | 21/21 · 18/21 · 8/10 | 21/21 · 18/21 · 8/10 | no loss (no hit or rank changes; 5 of 69 top-5 lists reorder below the hits) |
| Facts | 83 / 6 / 0 | 83 / 6 / 0 | no loss (no rebuild needed: the build reads the low-information list only to skip all-low-information labels when tagging, and no added word is a concept spelling) |
| Sealed set | not run | not run | run once at T9 |

Gained: h07 (employee costs; synonym employee -> staff), h17 (earnings from associates; earnings -> results), h20
(a Chinese "deposit size" wording; question and measure words marked low-information).

## T2.1 attribution (old 16)

Full table with trace ids: `eval/results/w2/old16-analysis.md` (subagent, read-only, never saw the sealed set; main
session checked the hit list and the h10 rank against the run file). Of 13 misses: 6 ranked too low, 3 not recalled
(two removed by the coverage gate), 4 concept not recognised; none were tree or index defects (with the reports' own
wording all 13 hit).

## T2.3 fixes, by class

| Class | Fix | Questions it addressed (old 16) |
|---|---|---|
| F1 word-level finance synonyms | `domains/banking/domain.yaml` `query_synonyms` (employee/employees -> staff, provision(s) -> allowance(s), earnings -> results/profit, and three Chinese pairs: profit, provisioning and dividend words to the reports' words); a query word and its synonyms form one coverage unit, so a synonym never counts twice; a word inside a matched metric's wording gets no synonym unit (review fix) | h07, h17 gained; h12, h15, h18 not yet |
| F3 question and measure words | seven Chinese scaffolding words added to `low_info_terms.yaml` (they no longer count as information in the coverage gate) | h20 gained |
| F2 mainland accounting line items | not done: the fix would be adding the held-out wordings themselves as aliases, which the guard forbids | h10, h11, h18, h19 |
| F6 coverage weight of rare non-finance words | not done: one question (h16), and no definition of "non-finance word" that is not fitted to it | h16 |

Both changed files are copied assets; their ASSETS.md rows record the kb-core change.

## T2.4 guard

`domains.held_out_wordings()` reads the legacy and old-16 list and the sealed round 2 set. The concept table guard
(`build/concepts.load_spec`) now checks every held-out wording (before: only a file passed in), and query synonyms are
checked the same way on load. Tests: a concept spelling that recognises a sealed wording fails to load; a synonym equal
to a held-out wording is rejected.

## Sealed set hygiene

The sealed set was written blind and sealed in PR #12 before any W2 change. The main session saw its questions while
checking snippets (T2.2). Every W2 change comes from the old-16 analysis above; no change was tried or measured on the
sealed set, which has not been run. The synonyms are general words, and some sealed wordings contain them; that overlap
is disclosed here so T9 can be read with it in mind.

## Review of the PR (independent subagent)

Fixed: a word inside a matched metric's wording no longer gets a synonym unit (it could lower coverage for pages naming
the metric another way); low-information list version bumped to 2 and its header corrected; report reasoning on why
tags do not change corrected. Deferred (minor): the synonym check is exact-match only; the held-out guard is skipped
if eval/ is missing (fails open); recall result files carry no commit hash; the plural synonyms (employees,
provisions) are morphological extensions not named in the analysis.

## Evidence

`eval/results/w2/old16-analysis.md`; recall runs `recall_20261028T102336-3194f6.json` (dev) and `recall_20261028T102341-56214d.json` (old 16).
