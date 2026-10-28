> Generated from kb-core 7a42359f1169cab4089a56e1d17b9bc5df2d1ae8; do not open PRs here; install: docs/deploy.md

# kb-core

Interpretation, retrieval and agent layer downstream of kb-intake.
kb-core reads kb-intake contract v2 delivery packages, interprets them into Postgres (tree, sections, chunks,
tables, concepts, observations, facts), indexes them into Elasticsearch, and serves 5 tools over HTTP and MCP
plus a small UI.

Design: [docs/kb-core-design-v1.md](docs/kb-core-design-v1.md). Development rules: [AGENTS.md](AGENTS.md).

## Deployment

[docs/deploy.md](docs/deploy.md): requirements, offline install from the internal pip mirror, first run, the service
unit, the SSO gateway, backup, upgrade, logs and key rotation. Every setting is listed in
[.env.example](.env.example).

## Development quick start

Point kb-core at your own Postgres database and Elasticsearch cluster (no Docker needed):

```bash
cp .env.example .env    # set KB_CORE_PG_DSN, KB_CORE_ES_URL, KB_CORE_DELIVERY_DIR, KB_CORE_STORE_DIR;
                        # for local work also KB_CORE_ENV=development and KB_CORE_AUTH_MODE=none
uv sync
uv run kb-core migrate
uv run kb-core doctor
```

Tests: `uv run pytest`. The integration tests run when `KB_CORE_TEST_PG_DSN`, `KB_CORE_TEST_ES_URL` (and optionally
`KB_CORE_TEST_ES7_URL`) point at a throwaway database and clusters (docs/deploy.md section 8). The web UI is built
with `cd web && npm ci && npm run build` (development only; the built UI is committed and served by the package).
