# Solution assets copied from kb

kb-core carries over kb's solution, not its data (design §1, §6). These files were copied from the kb reference repository at commit
`2f6042e936a592e616d97905fab913b90146e932` (branch `chore/english-only`, which contains `main` and has English comments).
Chinese prose was translated (AGENTS.md "Language"); Chinese that must match source text or Chinese questions
(aliases, row labels, regexes, zh questions and gold answers, evidence snippets, the jieba dictionary) is kept.

`eval/baseline/` holds kb's recorded tree and concept-tag eval results: the comparison baseline, not inputs.
Files kb-core adds itself are listed with source `kb-core` and commit `-`.

`uv run python scripts/check_assets.py` checks that every file is listed and its sha256 matches. Changing an asset
means updating its row (and saying why in the notes).

| kb-core path | source path (kb) | source commit | sha256 | notes |
|---|---|---|---|---|
| `profiles/annual_report/sections.yaml` | `profiles/annual_report/sections.yaml` | 2f6042e | 47f24e693f0a6cf439162630144207256eb6ab50a1283f506e37ed7ce5b7ea9a | byte copy |
| `domains/banking/concepts.evidence.yaml` | `domains/banking/concepts.evidence.yaml` | 2f6042e | 39fbfe542d3f9a8f6b3aa9160217240e6763088fd497e32026f6432ec60c21b9 | byte copy |
| `domains/banking/concepts.yaml` | `domains/banking/concepts.yaml` | 2f6042e | 97d61982785196c84e10bd861bffc32522b1a85913d57b8bd129fbe62409785e | translated: 65 `definition` values, `review[].why`, one comment line glossed in English |
| `domains/banking/domain.yaml` | `domains/banking/domain.yaml` | 2f6042e | cc7049f1edb18ba54f3894744b827c770ed1ff7486a45b3e27023f92d6d17a46 | byte copy + kb-core `query_synonyms` block appended (round 2 W2, class F1) |
| `domains/banking/facts.yaml` | `domains/banking/facts.yaml` | 2f6042e | b181c70182637310a78d8fe4b621a4c7021d53d37310c6fba7f7c116060516c5 | byte copy |
| `domains/banking/finance_zh.txt` | `domains/banking/finance_zh.txt` | 2f6042e | 2c027c7bdb19b5a8105b3f5b84a2443e8e1d9ecbe9143bf526d8d22cdc70cff4 | byte copy |
| `domains/banking/low_info_terms.yaml` | `domains/banking/low_info_terms.yaml` | 2f6042e | aeae5c7339d10a0fcd9ace2d22e928143a14031d44c5cf225e1d85818c33d393 | byte copy + kb-core zh question words added (round 2 W2, class F3) |
| `domains/banking/units.yaml` | `domains/banking/units.yaml` | 2f6042e | 8e8bd9b01b635f1101951ac6ac23d2c110bee961fa2635f16dea489be4de0371 | byte copy + kb-core `cells` block appended (cell parsing, design §3.2) |
| `config/ranking.yaml` | `ref/ranking.yaml` | 2f6042e | 04aeda9d7fa45ba00bd89a8248251f07219f534d303f010f8a4273fd2e6d7043 | byte copy |
| `eval/baseline/concept_tag_eval.yaml` | `ref/concept_tag_eval.yaml` | 2f6042e | 5f8fb8944435b738cebcd9f37eecb62a460be5df6148eb64d731bf5ecba3314a | translated: `why` notes, `(final)` rule label |
| `eval/baseline/tree_eval.yaml` | `ref/tree_eval.yaml` | 2f6042e | 31e53868eeb21aa22909a8921dd501e7d6135599976a0a56933252370ee6fe12 | translated: `errors` notes |
| `eval/demo.yaml` | `eval/demo.yaml` | 2f6042e | 5fe0bebbcf9012f90835c91ca0d9068512bd3f26c25d4d0c553c573fc0bb455f | translated: `layer` labels (recorded zh answers kept as data); sanitized for enterprise readiness C (agent-tool, vendor and personal names, local paths and an agent session id replaced by neutral placeholders) |
| `eval/derived_allowlist.yaml` | `eval/derived_allowlist.yaml` | 2f6042e | 2cecf848364ead87067f1e8f097f5302dcdd5d2255d74231e7c92c1e85de6a3a | byte copy |
| `eval/heldout_terms.yaml` | `eval/heldout_terms.yaml` | 2f6042e | bbbc9cbcc2d905c8783eade9fcf89534e260df1dd4fafa6d82368ca411684c13 | byte copy |
| `eval/p1_agent.yaml` | `eval/p1_agent.yaml` | 2f6042e | 8f6622dc0208f21db08f04ab3699004b3270b2fdc8793374674a89e2e9726d82 | byte copy; sanitized for enterprise readiness C (agent-tool, vendor and personal names, local paths and an agent session id replaced by neutral placeholders) |
| `eval/p1_crossyear.yaml` | `eval/p1_crossyear.yaml` | 2f6042e | 50e314f99753d7d412594ebd08c3a4d539da4dc10d41f668f29812e19ff9daee | byte copy |
| `eval/p1_questions.yaml` | `eval/p1_questions.yaml` | 2f6042e | 88ff5ee3541da16b84c8fb4a605da7b29c8425438ca7a30a3a44bdca30c5f58b | byte copy |
| `eval/p1_v3.yaml` | `eval/p1_v3.yaml` | 2f6042e | 0955739bafd79fb3f1cb6ee5eb99488de91cbc5113d8787063daec1a1349df4f | byte copy |
| `eval/p2_fact_demo.yaml` | `eval/p2_fact_demo.yaml` | 2f6042e | 594da7f1f1a9c2005518c47d8f91859a17847ae0a06b5d448691e33c2f15916b | byte copy; sanitized for enterprise readiness C (agent-tool, vendor and personal names, local paths and an agent session id replaced by neutral placeholders) |
| `eval/p2_heldout.yaml` | `eval/p2_heldout.yaml` | 2f6042e | de21c49137a38ffd87b38848677a5ff7604c216f9dffc5e5ca00e40c042fe483 | byte copy |
| `eval/p3_search_path.yaml` | `eval/p3_search_path.yaml` | 2f6042e | f3b340aa412be38e9ccab11504f85452899e07b7b662aaa47cfa2432dc0943c1 | byte copy |
| `profiles/annual_report/tree.yaml` | `kb-core` | - | 5ef738ba0e4e8e792713adf7a0ba81f5c4956d159028bcbc619244454d1e9548 | kb-core's own |
| `profiles/generic/tree.yaml` | `kb-core` | - | 6346dbf6258a5acad09b3fa446ea1026afa2346da70caf7c376bca38ee8ef6b0 | kb-core's own |
| `config/mcp.yaml` | `kb-core` | - | ba454cd8dcb924ed52ca638a68064dda337755f9db920308774f26cb3257c4e1 | kb-core's own |
| `eval/tree_rubric.md` | `kb-core` | - | ac425d24361f26e602cfa58438aab2e457c504d066820647da3d31c90bada42e | kb-core's own; owner name replaced by a neutral role (enterprise readiness C) |
| `config/node_concept_overrides.yaml` | `kb-core` | - | 044e87835431578c664d050f2a1a6a17214b0f56cd42c17c88364d1d8d75faee | kb-core's own |
| `domains/banking/tagging.yaml` | `kb-core` | - | 4a505abd6b036089b0c0ec9f2243b8e510b4e96330eeadf83d49d4caab048dd6 | kb-core's own |
| `profiles/annual_report/observations.yaml` | `kb-core` | - | f2fd4bb19f144f1cd10207f5a8b23883bce1e55cbac740fb73692b631ff873c7 | kb-core's own |
| `eval/round2_heldout.yaml` | `kb-core` | - | f5420176bc9dd99e43c88b21c7fc0b0f5c500dad45af7f5c57fc69d2026f5353 | kb-core's own: sealed round 2 held-out set (blind writer) |
| `eval/round2_heldout.SEALED.md` | `kb-core` | - | d8ce1ee6fd77c2450591ac99394a4272cacced9d5dad71cfffcf09a0ee224a9a | kb-core's own: seal note with the set's SHA-256 |
| `config/access_roles.yaml` | `kb-core` | - | adf8e2c86694f57f01bcc7984532b5d730e52d055d6ed36772425ebc8a6ba5af | kb-core's own: demo access roles (round 2 W3, D3) |
| `config/access_labels.yaml` | `kb-core` | - | c826984712e3c8f88eb68fe0bc83d4d7f9cfcf1a87c554ae17986e2765e5e564 | kb-core's own |
| `config/access_role_map.yaml` | `kb-core` | - | cc0d66b1090c0044d7daf247327dd9469d8864b2066cea70a2e533530ca3c264 | kb-core's own: SSO gateway groups to roles (enterprise readiness B; placeholders) |
