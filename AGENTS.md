# Agent Development Instructions

Development in this repository is workflow-first, not change-first.
Do not start by editing code. Load `development-workflow` for every
development task and follow it:

1. Understand the requirement first. Look facts up yourself; ask the user
   only for decisions, each with a recommended answer.
2. Workflow first, single-point second: run the matching `workflow-*`
   Skill for this kind of problem. Only if none fits, compose a single-point
   route for this task from the available Skills and native capabilities.
3. A new or changed route is approved by the user as part of the plan.
   Approved workflows are reused without re-approval.
4. Run the route. Propose updating a workflow when the run shows it should
   change, or solidifying a single-point route that will recur as a new
   workflow.

Follow each selected Skill's own instructions. Treat repository facts and
executable checks as stronger evidence than agent claims.

## Project-specific rules

### Language

Everything in this repository is written in English: code, comments, docstrings, UI text, tests, commit messages,
README, reports and design documents (`docs/kb-core-design-v1.md` is the project owner's design, translated at their request).
The only Chinese allowed is data that must match Chinese source text: concept aliases and row labels, the jieba
dictionary, regexes, and Chinese-language eval questions, gold answers and fixtures. Free-text notes in copied assets
(comments, `why:` fields, answer notes) are translated when copied.

### Boundaries

- kb-core is the interpretation, retrieval and agent layer (kb-core-design-v1 §1–2). Its only input is a kb-intake
  contract v2 delivery package. It does not parse PDFs (it may render a page image from `source.pdf` for display),
  never calls kb-intake and never imports kb-intake or kb code (enforced with `uv run lint-imports`).
- What needs only the file belongs to kb-intake; what needs a type profile or domain knowledge belongs here. If an
  interpretation step needs information the package does not carry, record it as a contract request for the project owner; never
  change kb-intake.
- `contract/intake-v2/` is a pinned copy of kb-intake's `contract/v2/` (source commit in `contract/intake-v2/SOURCE.md`);
  `scripts/check_contract.py` proves they match.
- Solution assets copied from kb (`profiles/`, `domains/`, `config/`, `eval/`) are listed with their source commit in
  `ASSETS.md`. kb's data, databases and intermediate artefacts are never copied; everything is regenerated from
  packages.
- Postgres is authoritative; Elasticsearch is a rebuildable index. `kb-core reindex` reads Postgres only.
- All queries live in `queries/pg/*.sql` and `queries/es/*.json` templates (`<ID>_<name>.v<N>`); code only
  substitutes parameters.
- No sample-specific logic in `src/`: issuer-, document- or page-specific rules go in profiles or domain packs.

### Delegation: subagents and workflows

1. **Split of work.** The main session owns planning, shared state (Postgres and ES contents, migrations, the
   contract copy, copied solution assets, pinned dependencies), decisions, integration, final verification and the
   report. Subagents only take bounded work that can be done independently.
2. **Good to delegate:** code review of each PR before merge, by a subagent that did not write the code; independent
   modules in parallel (e.g. UI views), each in its own git worktree and integrated by the main session; fact
   checking and eval judging from the source PDFs; writing missing tests; checking documentation.
3. **Not delegated:** writing to the shared Postgres / ES, rebuilding indexes or reloading data, changing
   `contract/`, `migrations/`, copied assets or `uv.lock`, and anything that needs the project owner's decision. Only one actor
   writes shared state at a time.
4. **Workflows** are for fixed, parallel or repeated procedures (eval runs, PR review).
5. **Concurrency:** at most 4 subagents at a time. Use subscription quota; no batch model calls.
6. **Verification:** the main session re-checks a subagent's conclusions (re-runs tests, samples evidence) and never
   takes them on trust. Every delegation is registered in Tallyback with task, constraints, verification and
   settlement.
7. **Reporting:** each round's report lists the delegations: who did what, under which constraints, how it was
   verified, and the conclusion.

### Stability and secrets

- Dependencies are pinned in `uv.lock`; `constraints.txt` is generated from it (`uv export`) and a check proves they
  match.
- No LLM call is needed to build, index or answer; the optional LLM (company chat-completions-compatible endpoint) is off by
  default, low weight, and never the only source.
- Secrets live in environment variables or a gitignored `.env` (template `.env.example`); kb-core reads `KB_CORE_*`
  names only. Never in tracked files, logs, traces or reports.
