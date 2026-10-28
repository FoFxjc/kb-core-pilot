# Round 2 W1: tree

Plan: `docs/superpowers/plans/2026-10-27-kb-core-round-2.md` W1 (T1.1-T1.4). Five rule rounds; the fifth was a
bounded round decided by the project owner (2026-10-28), after which W1 merges with what it reached, provided recall stays within
the approved exceptions.

## Results

| Measure | Before W1 (main) | After W1 | Plan target |
|---|---|---|---|
| Missed headings (blind heading lists, 40 seeded pages per document, seeds 301-306; 585 judged headings) | 223 / 585 = 38.1% | 51 / 585 = 8.7% | <= 3% |
| Extra nodes on the sampled pages | 72 | 72 | - |
| Tree spot check, fresh seeds (221-226, judged on the W1 tree) | 195 / 240 = 81.3% (seeds 201-206, same code as main) | 192 / 240 = 80.0% | >= 92%, no document < 85% |
| Recall with year / without / cross-year | 21/21 · 19/21 · 9/10 | 21/21 · 18/21 · 8/10 | no loss |
| Held-out old 16 | 3/16 | 3/16 | - |
| Facts | 83 / 6 / 0 | 83 / 6 / 0 | no loss |

Spot check per document (fresh seeds, correct of 40): 2023 en 33, 2023 zh 34, 2024 en 28, 2024 zh 28, 2025 en 32,
2025 zh 37. Recorded as each document's `tree_sample_accuracy` (`kb-core eval tree --record`).

**Not met:** the 92% spot-check target and the 3% missed-headings target. W1 raised coverage a lot (most real
sub-headings inside the financial-statement notes are now nodes) but precision is flat: the new nodes bring their own
errors. Targets move to round 3.

**Gate.** Against main the net recall effect is two losses (q05, v05); q05's with-year node rank also fell from 1 to
5, one step from a third loss. Recall: two losses, approved by the project owner as explained exceptions (`eval/results/w1/exceptions.yaml`):
q05 (without year; real accounting-policy sub-headings now out-rank note 28) and v05 (cross-year; the gold page moved
from rank 10 to 11 of 10). Tree block of `eval compare`: four documents are lower than their round 1 recorded values
(seed 105). These are different samples (listed for review by the gate); on the same pre-W1 code, fresh seeds 201-206
measured 81.3% against round 1's 85% on seed 105, so the round 1 value was a favourable sample. The project owner's decision covers
merging with the tree targets not met.

## What changed (by failure class)

| Class (T1.3) | Fix (T1.4) | Effect, measured right after that step (intermediate) |
|---|---|---|
| Headings inside notes never became nodes | attach headings to notes and subnotes; dotted numbering (2.13.6, 2.13.6.1) and lettered items nest by depth; a dotted number names its subnote; unnumbered sub-headings nest under the dotted heading before them; roman groups stay level; dotted headings never sit under a dotted sibling | missed headings 38% -> 10% (final, after all steps: 8.7%) |
| Stat callouts, signatures, value cards taken as headings | title ending in a figure with a unit; heading followed by a larger figure; name after a signature image; rows of four or more same-size headings | extras 99 -> 76 after this step (the notes step had raised them from 72; final 72) |
| Two-character Chinese labels dropped as junk | two CJK characters make a heading (country labels) | six wrong parents fixed |
| "(continued)" repeats nested as children | a "(continued)" repeat of a heading seen earlier in its section is not a node | 2023 en "Overview" fixed |
| Pull quotes and continued headers extended sections | only running text before the next heading keeps the previous section on that page | q10, lost by an earlier W1 step, recovered (against main: unchanged) |
| Host chosen by page height on two-column pages | host by reading order | inverted page ranges on the six documents 5 -> 2, the rest fixed by the next step |
| Titles wrapped over two regions | join the second line (same style, directly below, not numbered, not after "(continued)") | running-title fragments removed |
| Page hit owned by a section continuing from earlier pages | a page hit maps to the covering node that starts on the page | v06, lost by an earlier W1 step, recovered (against main: unchanged) |

Not fixed (round 3): diagram, chart and award labels (no layout signal separates them from real headings without
losing real ones), key-audit-matter table labels, biography and country-label parents, contents entries not printed on
the page, numbered headings that intake merged into one region, headings inside regions intake typed as tables.

## Review of the PR (independent subagent)

Fixed with tests: the dotted-number host now applies only inside the note that holds the heading by position (a dotted
heading outside the notes, or a second note set reusing numbers, stays put); a dotted heading climbs as many levels as
needed and takes the headings after it along (no inverted ranges); thresholds and patterns moved from code to the
profile (`notes.dotted`, `notes.roman_group`, `headings.row_dy`, `card_row`, `card_max_pitch`, `wrap_gap`,
`display_text_factor`; the "(continued)" pattern is the profile's); a card row also needs a narrow pitch, so a
four-column section row stays; the unnumbered-under-dotted rule applies inside notes only; directory pages are detected
over all headings. None of these changed a judged item (all 552 judged-correct and 130 judged-wrong items are the same
nodes). Report numbers corrected (extras 72 before and after; step effects marked as intermediate).

Deferred (minor): `_merge_wrapped` can join two stacked headings of the same style; `_end_before` keeps unused
parameters and a section ending in a chart above a low heading loses that page; any heading right after a signature
image is dropped; owner-first page mapping has no isolated measurement beyond v06; heading matching is first-come with
prefix matching (exact matches first and a word boundary would be better); approved_by is not verifiable.

## Evidence

- Judged sheets: pre-fix `tree_*_20{1-6}.judged.yaml`; round-4 re-score `tree_*_20?.w1.judged.yaml` and fresh
  `tree_*_21{1-6}.judged.yaml`; re-judged changed nodes `eval/results/w1/rejudge*.judged.yaml`; final fresh
  `tree_*_22{1-6}.judged.yaml`. Every sheet was re-checked by the main session (at least 10 items per sheet, 6 for one
  sheet with only 3 wrong items); all checked verdicts agreed.
- Heading lists: `eval/results/headings/*_30{1-6}.judged.yaml` (blind judges, PDF only); main-session check: 577 of 585
  titles appear on their page as printed, the rest differ only in punctuation or are drawn as graphics.
- `eval/results/w1/headings_before.json` (main's tree code) and `eval/results/w1/headings.json` (W1),
  `eval/results/w1/snapshot.json`, recall runs `recall_20261028T101548-aab4e9.json`
  (dev) and `recall_20261028T101552-157b8a.json` (old 16).
