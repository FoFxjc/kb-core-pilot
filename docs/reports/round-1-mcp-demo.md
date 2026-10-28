# Round 1 MCP demo and reindex invariance (plan Task 25)

2026-10-27. Step-4 acceptance, part 1. The raw session (questions, prompt, tool calls with trace ids and the agent's
answer in its original language) is in `eval/results/mcp_demo_round1.yaml`.

## Setup

- `kb-core serve` (branch `feat/step-4`) on 127.0.0.1:8200. All six OCBC documents are built and indexed. Tree
  spot-check accuracy is recorded from the seed-105 judged sheets (`kb-core eval tree --record`).
- One non-interactive MCP client session (a coding agent). `--strict-mcp-config` gives it only the kb-core MCP server. The
  allowed tools are the five kb-core tools; built-in file, shell and web tools are disallowed. The session header is
  `X-KB-Session: round1-demo`.
- The prompt asked kb's demo questions d2, d3 and d4 (`eval/demo.yaml`, asked in Chinese as in kb):
  - d2: how the NPL ratio changed from 2024 to 2025;
  - d3: OCBC's net profit growth over the past three years;
  - d4: OCBC's LCR for 2025.
- The session took 10 turns, cost USD 0.43 and made 8 tool calls, all traced in `quality.trace_event` with source
  `mcp`:

| # | tool | parameters |
|---|---|---|
| 1 | resolve_concept | term "NPL ratio" (asked in Chinese) |
| 2 | resolve_concept | term "net profit" |
| 3 | resolve_concept | term "liquidity coverage ratio" |
| 4 | get_metric_series | npl_ratio, 2024-2025 |
| 5 | get_metric_series | net_profit, 2022-2025 (one extra base year, as rule 5 asks) |
| 6 | search | "liquidity coverage ratio LCR 2025", fiscal_years [2025] |
| 7 | read | ocbc-group_ar_2025_en, physical pages 98-100 |
| 8 | read | ocbc-group_ar_2025_en, physical page 4 |

## Answers (translated from the agent's Chinese answer) and checks

Each cited number was checked against the stored page text through `/v1/read`. "Page" means physical page; the
printed page is in brackets.

**d2, NPL ratio 2025 vs 2024: unchanged at 0.9%.**

| claim | source cited | check |
|---|---|---|
| NPL ratio 0.9 (2025) and 0.9 (2024) | 2025 en p98 [96], MD&A key financial ratios | The table row reads "Non-performing loan ratio 0.9 0.9" ✓ |
| "NPL ratio remained unchanged at 0.9% … total NPAs were $3.24 billion, up 13% … coverage stood at 151%" | 2025 en p100 [98] | Quoted text is on the page ✓ |

The agent named the fact status (2024: several sources agree; 2025: single source). It also mentioned the 2024
report's p98 as a further source and marked that page as not read, as rule 1 asks.

**d3, net profit growth over three years.** The agent took 2023-2025 relative to the latest period and used 2022 as
the base:

| year | net profit ($ million) | YoY |
|---|---|---|
| 2022 | 5,526 | — |
| 2023 | 7,021 | +27.1% |
| 2024 | 7,587 | +8.1% |
| 2025 | 7,422 | −2.2% |

| claim | source cited | check |
|---|---|---|
| The four values | 2025 en p4 [2], five-year summary, "Net profit attributable to equity holders of the Bank" | Row reads "4,858 5,526 7,021 7,587 7,422" (2021-2025) ✓ |
| "Group net profit of $7.42 billion for 2025 was 2% below the record $7.59 billion" | 2025 en p99 [97] | Quoted text is on the page ✓ |
| Three-year growth about 34.3%, CAGR about 10.3%, stated as its own calculation | — | 7,422 / 5,526 = 1.343; 1.343^(1/3) = 1.103 ✓ |
| 2022 figures restated under SFRS(I) 17 | 2025 en p4 footnote | "restated" footnote is on the page ✓ |

**d4, LCR 2025.** The agent said LCR is not in the fact layer and read the source table instead:

| claim | source cited | check |
|---|---|---|
| Singapore-dollar LCR 294% (2025), 299% (2024) | 2025 en p98 [96] | "Singapore dollar liquidity coverage ratio (5)(8) 294 299" ✓ |
| All-currency LCR 138% (2025), 141% (2024) | same | "All-currency liquidity coverage ratio (5)(8) 138 141" ✓ |
| Average for the year, computed under MAS Notice 649 | footnote (8), same page | Footnote text is on the page ✓ |

Every cited number and page matches the source. All amounts are given in Singapore dollars, as rule 7 requires. One
wording slip: the agent wrote that the LCR values were read "from the MAS original table". It means the annual
report's table, which is computed under MAS Notice 649.

## Reindex invariance

1. `kb-core eval recall p1_questions p1_crossyear p1_v3` → `eval/results/recall_20261027T120910-a3598f.json`
   (21/21 with year, 19/21 without, 9/10 cross-year).
2. Deleted both physical indexes by name (`kbcore_node_v1_…034710…`, `kbcore_page_v1_…034711…`).
   `kb-core doctor` then warned "alias without an index: kbcore_node, kbcore_page".
3. `kb-core reindex` (from Postgres only): 2,552 nodes and 1,472 pages into new physical indexes.
4. Reran the eval → `eval/results/recall_20261027T120930-a33799.json`. Same summary.
5. Compared the per-question top-k node lists (42 single-point variants and 27 cross-year year groups): **0 of 69
   differ**.
