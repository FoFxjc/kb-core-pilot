# Deploying kb-core

For the operators who install and run kb-core on a company server. Everything below runs without Docker and without
Node.js: the web UI ships prebuilt inside the Python package. Every setting is a `KB_CORE_*` variable; the full list,
grouped and commented, is [`.env.example`](../.env.example).

## 1. Requirements

| Component | Version | Notes |
|---|---|---|
| Python | 3.12 | `requires-python = "==3.12.*"` |
| Postgres | 17 (tested on 17.6) | Authoritative store. Plain SQL, no extensions; older versions are untested. One database, created before the first run |
| Elasticsearch | 7.10 to 8.x (tested on 7.10.2 and 8.19) | No plugins. Rebuildable index only: everything in it comes from Postgres |
| SSO gateway | any reverse proxy that authenticates users and sets headers | Required in production (section 5) |
| Model endpoints | chat-completions-compatible HTTP APIs | Optional; every model purpose is off by default |

Disk: the store folder holds read-only copies of the imported packages (with their PDFs) and a page-image cache.

## 2. Offline install from the internal pip mirror

kb-core installs as one wheel plus pinned dependencies. `constraints.txt` pins every package (direct and indirect).

**Online (internal pip mirror):** `setup.sh` does it all (section 3). pip reads the mirror from `PIP_INDEX_URL` or
`pip.conf`; when `uv` is installed, set `UV_INDEX_URL` instead.

**Fully offline (no index at all):** on a build machine with the same OS, CPU architecture and Python 3.12:

```bash
python3.12 -m pip wheel -w wheels -c constraints.txt .     # kb-core (UI included) and every pinned dependency
```

This builds a wheel for every package, including the few published only as source (they are pure Python), so the
server needs no build step.

Copy `wheels/` to the server, then:

```bash
python3.12 -m venv /srv/kb-core/.venv
/srv/kb-core/.venv/bin/pip install --no-index --find-links wheels -c constraints.txt kb-core
```

No Docker, no Node.js and no compiler on the server: it installs wheels only.

## 3. First run

```bash
cd /srv/kb-core                     # the source folder, or any folder holding .env
cp .env.example .env                # fill it in; keep it readable by the service user only (chmod 600)
./setup.sh                          # .venv, editable install (pip -c constraints.txt -e .), migrate, doctor
.venv/bin/kb-core import            # every package in KB_CORE_DELIVERY_DIR (idempotent)
.venv/bin/kb-core build --all       # tree, sections, chunks, tables, concepts, observations
.venv/bin/kb-core facts             # the fact layer
.venv/bin/kb-core reindex           # Elasticsearch from Postgres
.venv/bin/kb-core doctor            # every check ok (model purposes may warn); add --check-endpoints to call them
.venv/bin/kb-core serve             # refuses to start when doctor fails or the indexes are missing
```

`setup.sh` installs kb-core editable, so kb-core reads `config/`, `domains/` and `eval/` from this folder: edit
`config/access_role_map.yaml` here and restart. With a wheel install (section 2) there is no `setup.sh`: run
`kb-core migrate`, then the same commands, from the folder that holds `.env` (or with the settings in the service
environment). A wheel carries its own copy of `config/` and `domains/` and no `eval/`: point `KB_CORE_ACCESS_ROLE_MAP`
(and the other `KB_CORE_ACCESS_*` settings) at files outside the package, and run evaluations from a source folder.

`KB_CORE_ENV=production` refuses to start with auth mode `none`, with the test clock (`KB_CORE_NOW`,
`KB_CORE_ALLOW_CLOCK_OVERRIDE`) set, or with a model key variable outside `KB_CORE_*`. Development without identity
(`KB_CORE_ENV=development`, `KB_CORE_AUTH_MODE=none`) binds to a loopback address only.

**TLS to the stores.** Postgres: put `sslmode=verify-full&sslrootcert=/etc/kb-core/tls/company-ca.pem` in
`KB_CORE_PG_DSN` (any libpq parameter works there). Elasticsearch: `https://` in `KB_CORE_ES_URL` and the company CA in
`KB_CORE_ES_CA_CERTS`; credentials in `KB_CORE_ES_USER` / `KB_CORE_ES_PASSWORD` or `KB_CORE_ES_API_KEY`.

**Model endpoints and proxies.** A default endpoint (`KB_CORE_LLM_*`) and three purposes that fall back to it setting
by setting: live chat (`KB_CORE_CHAT_*`), the judge (`KB_CORE_JUDGE_*`, decision plane inside retrieval; configuration
only until round 3) and graph extraction (`KB_CORE_EXTRACT_*`). Each purpose may set its own base URL, model, key
variable, CA bundle and timeout. Every model client trusts its purpose's CA bundle (`*_CA_CERTS`); without one it uses
the CA set bundled with its HTTP library (or `SSL_CERT_FILE` / `SSL_CERT_DIR`), not the operating system's store,
so set `*_CA_CERTS` for an endpoint signed by the company CA. Every model client honours the standard `HTTPS_PROXY` / `HTTP_PROXY` / `NO_PROXY` variables of the service environment; put the
Postgres and Elasticsearch hosts in `NO_PROXY` when a proxy is set. A model purpose that fails (missing key,
unreachable endpoint) makes doctor warn and never blocks `serve`.

## 4. Service unit (systemd example)

```ini
# /etc/systemd/system/kb-core.service
[Unit]
Description=kb-core retrieval service
After=network-online.target

[Service]
User=kbcore
Group=kbcore
WorkingDirectory=/srv/kb-core
EnvironmentFile=/etc/kb-core/kb-core.env        # KB_CORE_* settings and keys; mode 600, owned by root
ExecStartPre=/srv/kb-core/.venv/bin/kb-core doctor
ExecStart=/srv/kb-core/.venv/bin/kb-core serve
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/srv/kb-core/store
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

The store folder (`KB_CORE_STORE_DIR`) must be writable by the service user; the delivery folder only readable.

## 5. Identity: the SSO gateway

In production kb-core never authenticates users itself. The company SSO gateway authenticates every request and
passes the result in two headers:

```bash
KB_CORE_ENV=production
KB_CORE_AUTH_MODE=trusted_header
KB_CORE_AUTH_USER_HEADER=X-Auth-User        # the user id the gateway established
KB_CORE_AUTH_GROUPS_HEADER=X-Auth-Groups    # the user's groups, comma-separated
```

Groups map to roles in [`config/access_role_map.yaml`](../config/access_role_map.yaml) (or `KB_CORE_ACCESS_ROLE_MAP`);
roles are defined in `config/access_roles.yaml`. A user holds every role their groups map to and calls run as the
data role with the highest clearance; `admin_groups` grant the admin role, which `/v1/admin/*` needs (import, live
chat, traces, sessions, evaluations, the UI's data). Admin gives no data role, but traces and sessions are an operator
view of every user's tool calls and their results, so grant it only to people trusted with all of that. HTTP, MCP
and live chat use the same identity, and every tool
call's audit row (`quality.access_audit`) records the user.

What kb-core enforces:
- no user header: `401 UNAUTHENTICATED` (never served as `public`);
- `X-KB-Subject` or a `subject` parameter: `400 INVALID_PARAM` (only development without identity accepts them);
- no mapped role: `403 FORBIDDEN`; an admin endpoint without the admin role, or a data call without a data role: `403`;
- the UI's role picker is hidden.

**The gateway must:**
1. be the only way to reach kb-core: bind kb-core to `127.0.0.1` (gateway on the same host) or to a private interface
   that only the gateway can reach (`KB_CORE_HOST`), and firewall the port;
2. replace (not append to) any client-supplied `X-Auth-User`, `X-Auth-Groups` and remove `X-KB-Subject`; kb-core
   refuses a request that carries an identity header twice, or a user header holding a comma;
3. forward the upstream address as `Host` (kb-core's MCP endpoint accepts only its bind address as `Host` when bound to
   loopback) and drop a browser `Origin` header on `/mcp`;
4. not buffer server-sent events on `/v1/admin/chat` (live chat streams).

Example (nginx with an `auth_request` check against the company SSO; adapt the names to your gateway):

```nginx
location / {
    auth_request /_sso_check;                                    # 401/403 from the SSO stop the request here
    auth_request_set $sso_user   $upstream_http_x_sso_user;
    auth_request_set $sso_groups $upstream_http_x_sso_groups;
    proxy_set_header X-KB-Subject "";                            # never let a client pick a role
    proxy_set_header X-Auth-User   $sso_user;                    # replaces anything the client sent
    proxy_set_header X-Auth-Groups $sso_groups;
    proxy_set_header Host $proxy_host;                           # 127.0.0.1:8200
    proxy_buffering off;                                         # live chat events
    proxy_read_timeout 300s;
    proxy_pass http://127.0.0.1:8200;
}
location /mcp {
    auth_request /_sso_check;
    auth_request_set $sso_user   $upstream_http_x_sso_user;
    auth_request_set $sso_groups $upstream_http_x_sso_groups;
    proxy_set_header X-KB-Subject "";
    proxy_set_header X-Auth-User   $sso_user;
    proxy_set_header X-Auth-Groups $sso_groups;
    proxy_set_header Host $proxy_host;
    proxy_set_header Origin "";
    proxy_buffering off;
    proxy_pass http://127.0.0.1:8200;
}
```

**Pilot:** every pilot user is in the admin group, and the pilot loads public documents only.

MCP clients connect to the gateway's address (see `.mcp.json.example`) with whatever credential the gateway accepts.

## 6. Operations

**Backup.** Postgres is authoritative: back up the kb-core database (`pg_dump -Fc`) on the company schedule. The store
folder holds the imported package copies; they can also be imported again from the delivery folder. Elasticsearch
needs no backup: `kb-core reindex` rebuilds it from Postgres (new indexes, then an atomic alias swap).

**Upgrade.**
1. Install the new wheel (section 2) into the same virtual environment, or a new one.
2. `kb-core migrate` (append-only numbered migrations; a changed migration is refused).
3. `kb-core reindex` (index mappings may have changed; the alias swap keeps search available until the switch).
4. `kb-core doctor`, then restart the service.
When a release changes interpretation rules, its notes say to run `kb-core build --all` and `kb-core facts` before the
reindex.

From releases before enterprise readiness: `KB_CORE_LLM_ENABLED` is no longer read (each model purpose has its own
`*_ENABLED` switch), and `~` in folder settings is no longer expanded (use absolute paths).

**Logs.** The service writes its log to stdout and stderr (the journal under systemd). Every tool call is a row in
`quality.trace_event` (input, results, timing, subject); every call's access decision in `quality.access_audit` (user,
role, returned ids, how much the policy hid). Admin endpoints read both (`/v1/admin/traces`, `/v1/admin/sessions/...`).

**The model-call ledger.** Every live chat model call appends one line to `<store>/chat/model_calls.jsonl`: time,
session, model, duration, finish reason, error and token counts; never the key or the content.
`KB_CORE_CHAT_BUDGET_CALLS` caps the total calls counted from it. Rotate or archive the file with the store's backups.

**Key rotation.** Keys live only in the service environment (or `.env`), never in tracked files:
`KB_CORE_LLM_API_KEY` or the `KB_CORE_*` variable a purpose names with `*_API_KEY_VAR`; `KB_CORE_ES_PASSWORD` /
`KB_CORE_ES_API_KEY`; the Postgres password in the DSN or a libpq password file. To rotate, put the new value in the
environment file and restart the service; settings are read once at start. To switch without editing the old
variable, add the new key under a new `KB_CORE_*` name, point `*_API_KEY_VAR` at it, restart, then remove the old one.

## 7. Releasing a pilot

Development happens in kb-core. The pilot repository (`kb-core-pilot`, next to kb-core on the same host) only
receives snapshots: one commit per release, never kb-core's history. Company machines download its `main` zip
(`https://github.com/<owner>/kb-core-pilot/archive/refs/heads/main.zip`) and install it as in sections 2 and 3.

```bash
# bump `version` in pyproject.toml and merge to main first
scripts/release_pilot.sh 0.2.1                 # releases origin/main; a second argument picks another commit
```

The script exports the commit with `git archive` (files marked `export-ignore` in `.gitattributes` stay out). It
stops if the version is already in the pilot repository (and exits 0 if that commit is already the latest release),
if the export holds a file that looks like a secret (`.env`, `*.pem`, `*.key`, ...) or if `scripts/check_clean.py`
finds anything in it. It builds the wheel set from it and imports `kb_core` from a
fresh virtual environment, puts a "Generated from kb-core <sha>" note at the top of the export's `README.md`, and
commits the export to a fresh clone of the pilot repository as `kb-core pilot <version> (snapshot of kb-core <sha>)`,
replacing every file. It pushes, downloads the zip and prints the pilot commit, the zip URL and the zip's SHA-256:
give that hash to the people who install it. It needs Python 3.12 (`PYTHON=/path/to/python3.12` to pick one), a pip
index and push access to the pilot repository; `PILOT_REMOTE=/path/to/bare.git` runs it against a local copy instead
(no zip and no hash then: they exist only for a GitHub remote). If GitHub has not served the new zip within a minute,
the script says so after the push: download the zip later and hash it yourself.
Never commit `.env` or any key: the export holds tracked files only.

## 8. Integration tests against your own stores

The test suite runs without stores; the integration tests run when these point at a throwaway Postgres database and
Elasticsearch clusters (they create and delete their own `kbtest_` indexes and tables):

```bash
KB_CORE_TEST_PG_DSN=postgresql://kbcore_test@db.example.internal:5432/kbcore_test \
KB_CORE_TEST_ES_URL=https://es-test.example.internal:9200 \
KB_CORE_TEST_ES7_URL=https://es7-test.example.internal:9200 \
uv run pytest
```

`KB_CORE_TEST_ES7_URL` is optional (it adds the Elasticsearch 7.10 runs). Never point them at a production database.
