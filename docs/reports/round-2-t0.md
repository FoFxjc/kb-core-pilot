# Round 2 T0: blind check, clean-up and regression baseline

2026-10-27, on `main` at dea140d (plan PR #9 merged; live chat #8 merged).

## T0.1 Blind check

**Question.** Round 1 concept tags (35/40 en, 37/40 zh) and facts (83 / 6 / 0) equal kb's numbers exactly. Does
kb-core read anything of kb's?

**What kb-core reads.** `scripts/trace_inputs.py` runs kb-core commands in one process under a Python audit hook,
installed before settings are read or kb-core is imported. It records every file Python opens, every socket Python
connects and every subprocess started, and classifies each path. Run on the rebuild and both recall evals (`import`,
`build --all`, `facts`, `reindex`, `eval recall` on the dev and held-out sets). The import step re-validated the six
packages, which were already in the store, so it wrote nothing there; the rebuild rewrote Postgres and ES.

| Class | Files | What |
|---|---|---|
| delivery | 66 | the six kb-intake contract v2 packages (manifest, JSONL files, source PDF, all checked against the manifest sha256 at import) |
| store | 24 | kb-core's read-only copies of those packages (`pages`, `regions`, `layout`, `tables` JSONL) |
| repo: domains, profiles, config | 13 | copied solution assets (listed with sha256 in `ASSETS.md`) and kb-core's own rule files |
| repo: queries, es, contract | 55 | query templates, index mappings, the contract schemas |
| repo: eval | 7 | question sets (`p1_*`, `p2_heldout`, `heldout_terms.yaml`) and the result files the run wrote |
| repo: src, `.env` | 43 | kb-core's own code and settings |
| python, system | 379 | the interpreter, site-packages, `/dev`, `/etc` |
| **under kb or kb-intake** | **0** | |
| unclassified | 0 | |

Sockets: Elasticsearch on 127.0.0.1:9200 only. Subprocesses: `git rev-parse HEAD` twice (the recall eval records the
commit). `eval/baseline/` (kb's recorded eval results, kept for comparison) is never opened. The full trace is
`eval/results/baseline_round2/input_trace.json`. It was regenerated on 2026-10-28 (enterprise readiness) with the same
commands and paths named relative to their root (`<repo>/`, `<store>/`, `<delivery>/`, `<tmp>/`); again nothing under
kb or kb-intake was opened, and its recall runs equal the round 2 results (0 of 69 and 0 of 35 top-k lists differ).

What the trace cannot see:

- Files opened inside C libraries: libpq (Postgres; the user's password file, service files, certificates) and PyMuPDF. Postgres
  is reached through `KB_CORE_PG_DSN` (127.0.0.1:5433/kbcore).
- Files opened by subprocesses (only their command lines are recorded).
- What the database held before the rebuild. The rebuild deletes and rewrites every interpretation row from the
  store copies, and the content digest is identical before and after.

Statically: no path to kb in `src/`, `queries/`, `config/`, `profiles/` or `domains/`, and the import-linter contract
forbids importing `kb_intake`, `pipeline` or `service`. One repository script reads kb-intake on purpose:
`scripts/check_contract.py` compares kb-core's contract copy with kb-intake's (the kb-intake repository, given with KB_CORE_INTAKE_REPO). kb-intake is
the upstream producer of the packages; this check reads its contract schemas, never kb's outputs.

**Why the facts equal kb's.** The counts are set by the reports' tables and the metric list, not by an implementation:

- The 15 fact metrics are kb's list (`domains/banking/facts.yaml`, a byte copy). kb-core extracts observations from
  its own table interpretation of the packages: 81 per English report (five-year summary plus the MD&A two-year key
  ratios), 55 per Chinese report (five-year summary only).
- 11 metrics are in the five-year summaries. The 2023, 2024 and 2025 reports cover 2019-2023, 2020-2024 and
  2021-2025, so every year 2019-2025 has two or more sources: 11 × 7 = 77 agreed facts.
- `nii`, `nim` and `npl_ratio` are only in the English MD&A two-year tables. 2023 and 2024 appear in two reports
  (agreed); 2022 and 2025 appear in one (single): 3 × 4 = 12 facts, 6 agreed and 6 single.
- Total 89 facts: 83 agreed, 6 single, 0 conflict. Any correct reading of the same tables gives these counts.
- The counts move with kb-core's inputs: merging with one document left out gives 86/69/17/0 (without 2023 en or
  2025 en), 89/72/17/0 (without 2023 zh or 2025 zh), 89/77/12/0 (without 2024 en), and 89/83/6/0 without 2024 zh
  (every 2024 zh value is also in another report).

**Why the concept tags equal kb's.** The scores are measured on different samples, so equality is a coincidence of two
40-node scores, not shared output:

- kb-core samples its own nodes (`kb-core eval concepts`, seeds 104, 106, 107; node ids `…:regions:…`). kb's sheets
  were seeds 41-44 on kb's PageIndex tree (`…:toc_flash:…`). The tags also differ in number: kb-core 133 en / 94 zh
  labels on its seed-107 sheets, kb 119 / 90 on its final sheets (from `eval/baseline/concept_tag_eval.yaml`, kb's
  recorded results kept in kb-core for comparison).
- The judges were fresh subagents reading only the PDF and the sheet.
- kb-core's scores across its three rounds were 31, 34, 35 (en) and 31, 28, 37 (zh). Tag tightening stopped once the
  sheet met kb's score (the round 1 target). That is selection on a dev sample: a fresh seed would show whether 35/37
  holds. W1 adds fresh seeds for the tree; tags get one fresh sheet per language at T9.

**Conclusion.** Within what the audit hook sees, kb-core reads only the delivery packages, its store copies and its own
repository; nothing under kb or kb-intake is opened. The facts equal kb's because both read the same tables with the same metric list. The tag scores equal kb's
on different samples.

## T0.2 Clean-up

- Stopped `kb-core serve` on 127.0.0.1:8200 (pid 3569, started 18:08 from the main checkout). Port 8200 is free.
- The `kb-core-ui-chat`, `kb-core-ui-trace` and `kb-core-ui-doc` worktree directories were already removed. Their
  branches `feat/ui-chat`, `feat/ui-trace` and `feat/ui-doc` were fully merged and are deleted (`git branch -d`).
  No uncommitted changes were lost.

## T0.3 Regression baseline

`eval/results/baseline_round2/baseline.yaml`, with the recall result files and the input trace.

| Check | Baseline | Round 1 report |
|---|---|---|
| Rebuild from packages | content digest, 714 node tags, 89 fact values identical before and after | identical rebuild |
| Recall with year / without / cross-year | 21/21 · 19/21 · 9/10 | same |
| Held-out legacy / old 16 | 3/3 · 3/16 | same |
| Per-question top-k vs round 1 runs | 0 of 69 dev, 0 of 35 held-out lists differ | - |
| Reindex invariance (both physical indexes deleted, rebuilt from Postgres) | 0 of 69 dev, 0 of 35 held-out lists differ | 0 of 69 |
| Facts | 408 observations, 89 facts, 83 / 6 / 0, 14 of 15 metrics | same |
| Concept tags (seed 107) | en 35/40 judged, 36/40 re-scored; zh 37/40 | 35/40 · 37/40 |
| Tree spot check | 85% (seed 105, stale; W1 re-measures) | same |
| pytest | 350 passed (live PG, ES 8.19, ES 7.10) | 302 (before #8 and T0) |

The only difference from round 1 is the en tag re-score. One judged item, "Volume and Rate Analysis" (2025 en
p101), lost exactly the two tags its judge marked wrong, after the step-2 review fix to the tag window. Its remaining
tag was judged correct.

New tools for the rest of round 2:

- `scripts/trace_inputs.py`: the input trace above.
- `kb-core eval compare BASE NEW`: per-question comparison of two recall runs. It exits 1 on a regression: any lower
  summary count (including the number of questions), a question missing from the new run, or a question that loses a
  hit it had, even when another question's gain keeps the totals level. Rank changes inside the top k and top-k list
  changes are listed, not gated; the PR's report explains them. Top-k lists are keyed by tier, document, pages and
  title, so a tree change that renumbers node ids is not a difference.
