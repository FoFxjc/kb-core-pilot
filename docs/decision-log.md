# kb-core design decision log

Decisions that change the design (`docs/kb-core-design-v1.md`), newest first. Earlier decisions are recorded where
they were made: the round plans (`docs/superpowers/plans/`) and round reports (`docs/reports/`), for example D1-D4 of
round 2 in `docs/superpowers/plans/2026-10-27-kb-core-round-2.md` section 2.

| Date | Decision | Decided by | Consequence |
|---|---|---|---|
| 2026-10-28 | **Pilot set-up and round 3 items.** Every pilot user goes in the admin group; the pilot loads public documents only. No changes now; recorded for round 3: a non-admin chat path; admin views (traces, sessions) filtered by data role; combining multiple roles per domain; a test on Linux with wheels from the internal mirror and a real SSO gateway. | Project owner | Every pilot user can see all pilot users' tool calls and results in traces and sessions (`docs/deploy.md` section 5). With public documents only, the results hold no restricted documents, but users' ids and questions are visible to all pilot users. |
| 2026-10-28 | **The Judge's LLM layer stays in the retrieval layer (decision plane), off by default.** | Project owner | Implementation is round 3. Until then only its configuration exists: `KB_CORE_JUDGE_ENABLED` (default `false`), `KB_CORE_JUDGE_MODEL`, `KB_CORE_JUDGE_MAX_CALLS_PER_QUERY` (default 2), `KB_CORE_JUDGE_TIMEOUT_S` (default 30), and optionally its own base URL, key variable and CA bundle, each falling back to the default model endpoint (`KB_CORE_LLM_*`). Retrieval results do not change while it is off. |
