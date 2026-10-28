# Round 2: miss analysis of the old 16 held-out questions (kb-core)

Run analysed: `eval/results/recall_20261027T215324-76f8dd.json` (3/16 hit), with questions from `eval/p2_heldout.yaml`.

## Method

- **Where the numbers come from.** Route ranks and gate drops come from the run's trace detail (`quality.trace_event.output->'detail'`: `routes`, `coverage_dropped`, `informative_terms`). Final ranks deeper than 5 come from re-running `kb_core.retrieval.search.run_search` in process with `limit=30`.
  - The re-run used the untraced function, so no trace rows were written.
  - It uses the same parameters as the eval: `fiscal_years` for the single questions; `group_by=fiscal_year` for the cross-year questions, with `per_group` raised to see positions.
  - The re-run reproduces the run's top 5 exactly for all 12 single questions.
- **What counts as gold.** A node counts as gold when its page range overlaps a gold physical page of the same document, which is the eval's `page_hit` rule. Route ranks are positions in each route's pool before the gate (pool size 50).
- **Variant probe.** Each question was also re-run with the report's wording (`variant_of`) in place of the held-out term. This shows how much depends on recognising the concept. The probe is only a diagnostic. It is not a proposed fix.
- **Failing step for a miss.** I named the earliest step at which the gold was lost, given that the concept is unknown by design:
  - **concept not recognised**: there is no lexical path at all, because the held-out tokens are absent from the gold text, so only a concept could bridge the gap.
  - **evidence not recalled**: gold is missing from every route's top 50, or the coverage gate removed it.
  - **ranked too low**: gold survives into the fused list but sits below 5 (single) or below 3 in its year (cross-year).

## Per-question table

| id | lang | heldout_term → variant_of | result | failing step | evidence (trace; gold position per route) | fix class (primary; secondary) |
|---|---|---|---|---|---|---|
| h01 | en | book value per share → net asset value per ordinary share | miss | ranked too low | tr_41bc0ced. Gold 2024_en p98 at page-route rank 9, which is also its final rank (12 without the year). The title and summary routes have no gold in their top 50. "per" and "share" are low-info, so "book" alone (df-weighted cov 0.74) made 3 Trading-Book/Banking-Book titles (p87-89) structure tier, at ranks 1-3. Variant: concept nav_per_share puts the gold at rank 1. | F1 finance synonym normalisation (book value ≈ net asset value); F5 tier rule |
| h04 | en | Tier 1 ratio → Tier 1 CAR | **hit** | — | tr_5ac7baa7. The "Capital Adequacy Ratios" node is first in each year's group: summary rank 1-2 and page rank 1-3, with no concept involved. | — |
| h05 | en | cost of risk → credit costs | miss | ranked too low | tr_f9f0ff85. Gold 2024_en p99 at page-route rank 6; final rank 11 (18 without the year). Summary gold node 0263 (p100) was at rank 49 and was dropped at cov 0.0. Title: none. Top 1 is the structure-tier "Debt Instruments Measured at Amortised Cost" (matched on "cost"). Variant: gold at rank 1. | F1 (risk-metric synonyms); F5 |
| h06 | en | fee revenue → net fee income | **hit** | — | tr_1756f36b. Gold p158 and p102 at final ranks 1 and 2, through the summary route (ranks 8 and 10) and the page route. | — |
| h07 | en | employee costs → staff costs | miss | ranked too low (dropped by the gate just below the threshold) | tr_06293189. Gold node "9. Staff Costs and Other Operating Expenses" (p160) was at title rank 15 and summary rank 4. Both were **dropped at cov 0.4943 < 0.5** because only "costs" matched. That left only page-route rank 7, giving final rank 15, below 6 structure-tier "Employee …" titles. Variant: gold at rank 1. | F1 (employee ↔ staff); F5 |
| h09 | zh | 非息收入 → 非利息收入 | **hit** | — | tr_45724ad8. "非息" has df 0, but "收入" matched the title "收入报表" (p52), which ranked 1 (structure). This was a lucky hit. | — |
| h10 | zh | 营业收入 → 总收入 | miss | ranked too low (**final rank 6**) | tr_9ae9c33d. Gold 2025_zh p9 at page-route rank 4, final rank 6. Summary hits on the p9 nodes were dropped at cov 0.29, because "收入" matched but the more weighted "营业" did not. "营业" pulls in subsidiary and region tables (33.1 主要附属公司列表, 日本, 32.1, 大中华区) at ranks 1, 2, 4 and 5. Variant: gold at rank 2. | F2 PRC accounting term mapping (营业收入 is a PRC line item); F1 |
| h11 | zh | 利润总额 → 税前盈利 | miss | concept not recognised | tr_0149341f. The tokenizer keeps "利润总额" whole and it has **df 0**, so the only informative token matches nothing. All 3 routes return filler (华侨银行/年/的) with no gold in their top 50, and nothing is in the top 30. Variant: gold at rank 2. | F2; F4 back-off for zh compounds with df 0 (alone it would not reach "盈利") |
| h12 | zh | 分红比例 → 派息率 | miss (**2/3 years**) | ranked too low (year 2023) | tr_fbfa9f48. 2024 is at position 2 and 2025 at position 2; 2023 is not in the group. "分红" has df 0, so only "比例" (df 23) carries the query. "到" and "分别" are counted as informative. For 2023, gold 2023_zh p8 is at page-route rank 9. Title node 0014 (p8-9, rank 5) was dropped at cov 0.0. Summary nodes 0014 and 0025 were dropped at cov 0.31, matched only on "到". The 2023 top 3 are 47.2 主要管理层人士薪酬, 保险 and 加速过渡至净零排放. Variant: all 3 years hit. | F1 (分红 ↔ 股息/派息, 比例 ↔ 率); F3 |
| h14 | zh | 员工人数 → Group staff strength | miss | concept not recognised | tr_328b8220. Gold exists **only in the English editions** (2024_en p103); the Chinese edition has no such figure. Chinese tokens cannot match English text, and no concept means no cross-language bridge. No route has gold in its top 50. Also, "年底" is informative while "年末" is low-info. Variant (with the English wording): gold at rank 1. | F1 (zh → concept, cross-lingual); F3 (年底) |
| h15 | en | loan loss provisions → allowances for loans and other assets | miss | evidence not recalled | tr_915ac2ac. Gold appears only at title rank 6 ("Year in Focus" p4-15, dropped at cov 0.0), summary rank 14 (node 0282 p100, dropped at cov 0.19) and page rank 33. Nothing is in the final top 30. "set" and "aside" count as informative, which inflates the denominator: without them, cov for 0282 is 0.34. "loan" does not match the report's "Loans". Variant: gold at rank 1. | F1 (provision ↔ allowance); F4 plural/stem normalisation; F3 |
| h16 | en | tax bill → income tax expense | miss (0/2 years) | evidence not recalled (removed by the gate) | tr_090ac493. Gold "11. Income Tax Expense" p161-162 is at summary rank 6 and title rank 14 in both years. Both were **dropped at cov 0.2993**: "bill" has df 3, so its high IDF carries about 70% of the weight. Page-route ranks are 31 (2024) and 22 (2025). Variant: both years at rank 1. | F6 gate rule (a rare non-domain token dominates the IDF); F1 |
| h17 | en | earnings from associates → share of results of associates | miss | ranked too low (**final rank 8**) | tr_b658bae2. Gold is reached only through the page route: p99 at rank 8, p125 at rank 9 and p98 at rank 12, giving final rank 8 (20 without the year). The title and summary routes have no gold. "book" (a verb here) counts as informative. Variant: gold at rank 1 (2024_zh p52). | F1 (earnings ↔ results/profit); F3 (verbs such as book/earn/set aside) |
| h18 | zh | 拨备前利润 → 扣除准备金与摊销前的营运盈利 | miss | concept not recognised | tr_e1b5299e. "拨备" has df 1 and "利润" has df 5; the report says 准备金 and 盈利. No route has gold in its top 50. Variant: gold at rank 1. | F2 (PRC term); F1 (拨备 ↔ 准备金, 利润 ↔ 盈利) |
| h19 | zh | 业务及管理费 → 营运支出 | miss (0/3 years) | concept not recognised | tr_2f47bad4. "管理费" has df 3, and "业务" and "及" are generic. No route has gold in its top 50 for any year. Variant: all 3 years at rank 1. | F2 (PRC line item → report line item) |
| h20 | zh | 存款规模 → 非银行客户存款 | miss | evidence not recalled (removed by the gate) | tr_25bf8cb4. Gold node 0295 (2025_zh p92, "17. 非银行客户…存款和结存") was at title rank 11 and summary rank 29, and both were **dropped at cov 0.193**. "有", "多" and "大" count as informative. Dropping them gives 0.443, which is still below 0.5 because "规模" (df 25) outweighs "存款" (df 58); dropping "规模" too gives 1.0. Page rank 41. Variant: gold at rank 2. | F3 (question words and measure nouns such as 规模/size/amount as low-info) |

## Fix classes (general; none adds a held-out wording as an alias)

- **F1, finance synonym normalisation at the word level.** Map single words, or very short standard phrases, to report vocabulary or concepts before concept matching. Examples are employee→staff, provision→allowance, earnings→results/profit, cost of risk ≈ credit costs, book value ≈ net asset value, 利润→盈利, 拨备→准备金, 分红→股息/派息, 比例→率, and zh→en for cross-lingual concepts. The list should come from a finance glossary, not from the eval.
- **F2, mapping of PRC (mainland) accounting line items.** Mainland bank statement terms (营业收入, 利润总额, 业务及管理费, 拨备前利润 and the like) map to the Singapore report's line items. This is a structured cousin of F1 that covers one whole family of user wordings.
- **F3, a low-info list for question scaffolding and measure words.**
  - zh: 有, 多, 大, 到, 至, 分别, 年底 (年末 is already listed).
  - en verbs: earn, book, set aside.
  - Measure nouns: 规模, 金额, size, amount, level.
- **F4, query-side morphological back-off.** Map plural to singular (loan↔loans). For a zh compound with df 0, split it into sub-words for the BM25 routes.
- **F5, a tier rule.** A title hit on a single polysemous token (for example "book" in "Trading Book", or "employee" in "Employee Share Plan") should not reach the structure tier when the query has other informative units that the title does not match.
- **F6, a coverage-gate rule.** Cap the IDF weight of a rare token that is outside the domain vocabulary (such as "bill"), so it cannot by itself push a node with the metric head below the threshold.

## Summary

**Hits: 3/16 (h04, h06, h09). Misses: 13.**

Counts per failing step (13 misses):

| failing step | count | ids |
|---|---|---|
| ranked too low | 6 | h01, h05, h07, h10, h12 (2023), h17 |
| evidence not recalled (incl. gate drop) | 3 | h15, h16, h20 |
| concept not recognised | 4 | h11, h14, h18, h19 |
| wrong domain or route | 0 | — |
| answer assembly | 0 | — (the eval measures recall only) |

Counts per primary fix class: **F1 = 7** (h01, h05, h07, h12, h14, h15, h17), **F2 = 4** (h10, h11, h18, h19), **F3 = 1** (h20), **F6 = 1** (h16). F5 and F4 appear only as secondary classes: F5 on h01, h05 and h07; F4 on h11 and h15. F3 is also secondary on h12, h14, h15 and h17.

The variant probe recovers 13/13 misses. With the report's wording, every missed question hits (rank ≤ 2, or every year in the top 3). So the misses come from wording and concept bridging, not from parsing, tree or index defects.

**Near misses:**
1. **h10 (营业收入)**: the gold is at final rank 6, one slot short. Gold p9 is at page-route rank 4, and its summary hits were dropped at cov 0.29.
2. **h12 (分红比例)**: 2 of 3 years hit. For 2023, gold p8 is at page-route rank 9 in the 2023 group, and its title and summary nodes were dropped by the gate (0.0 and 0.31).
3. **h07 (employee costs)**: the gold node "9. Staff Costs…" was at summary rank 4 but was dropped by the gate at **0.4943 vs a threshold of 0.5**, leaving final rank 15.

h17 (final rank 8) and h01 (final rank 9) come next.

## Full trace ids

h01 tr_41bc0ced71a047caa98fdc2b80d49be0 · h04 tr_5ac7baa750684e11b5c0e1ca515fb445 · h05 tr_f9f0ff85787c488684be720ba9badf2a · h06 tr_1756f36b654e40ef93955f6dcfc3e3a5 · h07 tr_06293189306c484e94a394d3b704c6fb · h09 tr_45724ad8d9c14700891609aed9230eb4 · h10 tr_9ae9c33d1be848aa9e883914a760efca · h11 tr_0149341f56cf4c9ab2d1b0399fa6e0e1 · h12 tr_fbfa9f48758c41e0bc5fa3031a00c6e3 · h14 tr_328b822039bf4f4aaf94613796f3cfcf · h15 tr_915ac2accbb44047b54cbe413919291d · h16 tr_090ac493e8ba4ebea99952bcec31d832 · h17 tr_b658bae243b94783a0131ba284242fe2 · h18 tr_e1b5299e99bf4fa9af36f90036ee4178 · h19 tr_2f47bad4076746ce8e938af129646c7d · h20 tr_25bf8cb469d24ee28bd80d41085cce52

Probe scripts were scratch files of the analysis run and are not committed.
