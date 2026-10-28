# Round 2 W3: permissions, first batch (design)

Plan: `docs/superpowers/plans/2026-10-27-kb-core-round-2.md` W3 (guardrails-v1 section 8, steps 1-2). Decisions D1
(label overlay plus contract request CR-2), D3 (three demo roles) and D4 (embargo on `ocbc-group_ar_2025_en`, test
clock `KB_CORE_NOW`) are the project owner's. Everything else here is the main session's design.

## 1. Labels

An **access label** has the same shape on a document and on a block (a node, page or table):

| field | values | meaning |
|---|---|---|
| `classification` | `public` < `internal` < `confidential` < `restricted` | sensitivity |
| `domains` | list of strings, e.g. `[finance]`; empty = no domain restriction | business domains allowed to read |
| `owner` | string | accountable owner (audit only) |
| `embargo_until` | ISO-8601 timestamp with offset, or null | hidden from subjects without `embargo_exempt` until then |
| `label_source` | `overlay` (simulated, D1) / `intake` (after CR-2) / `default` | where the label came from |

**Effective access** of a block = its document's label combined with the block's own label:
`classification` = the higher of the two; `domains` = the block's if it sets any, else the document's;
`embargo_until` = the later of the two; `owner` = the block's if set, else the document's.

Labels only go up automatically (T3.2): an overlay entry may raise a block above its document freely; an entry that
would make a block or document *lower* than what it already has (from intake or a broader overlay rule) is rejected
unless it carries `lower: true` and a non-empty `reason`.

## 2. Overlay (D1): `config/access_labels.yaml`

```yaml
version: 1
simulated: true          # labels are a stand-in until kb-intake carries them (CR-2)
default: {classification: public, domains: [], owner: unassigned}
documents:               # first matching pattern wins (fnmatch on doc_id)
  - match: "ocbc-group_ar_2025_en"
    label: {classification: internal, domains: [finance], owner: group-finance,
            embargo_until: "2026-11-15T00:00:00+08:00"}
blocks:                  # within a document: by node title pattern (regex, case-insensitive) or page range
  - doc: "ocbc-group_ar_2025_en"
    title: "^Management Discussion and Analysis$"
    label: {classification: confidential, domains: [finance]}
```

A document with no matching entry and no intake label gets `default`; an imported document must end with
`classification` and `owner` set or import fails (T3.1). The demo labels above are simulated and chosen to exercise
every rule; the real values come with CR-2.

## 3. Subjects and roles (D3)

`config/access_roles.yaml`:

| role | clearance | domains | embargo_exempt |
|---|---|---|---|
| `public` (default subject) | public | [] | no |
| `finance_analyst` | internal | [finance] | no |
| `finance_confidential` | confidential | [finance] | yes |
| `full_access` (regression gate and admin only, never a default) | restricted | ["*"] | yes |

The subject comes from `X-KB-Subject` (dev: a role name) on HTTP, from the MCP session's `X-KB-Subject` header on
MCP, and from the chat request on live chat. Missing → `public`. Unknown role → `INVALID_PARAM`.

## 4. Policy (T3.3): `src/kb_core/access/policy.py`

```python
@dataclass(frozen=True)
class Subject: role: str; clearance: str; domains: tuple[str, ...]; embargo_exempt: bool
@dataclass(frozen=True)
class Access: classification: str; domains: tuple[str, ...]; owner: str; embargo_until: datetime | None
@dataclass(frozen=True)
class Decision: allow: bool; reason: str          # reason is for the audit only, never returned to callers

def effective(doc: Access, block: Access | None) -> Access
def decide(subject: Subject, resource: Access, now: datetime) -> Decision
def filter_terms(subject: Subject, now: datetime) -> dict    # what every route must filter on
def now() -> datetime          # real UTC time; KB_CORE_NOW only when KB_CORE_ALLOW_CLOCK_OVERRIDE=true (D4)
```

`decide` allows when all hold:
1. `rank(subject.clearance) >= rank(resource.classification)`;
2. `resource.classification == "public"` or `not resource.domains` or `"*" in subject.domains` or the domains intersect;
3. `resource.embargo_until is None` or `now >= resource.embargo_until` or `subject.embargo_exempt`.

`filter_terms` returns the same rule as data for the stores: `{"classifications": [...allowed levels],
"domains": [...] | None (None = any), "embargo_before": now | None (None = exempt)}`. ES routes translate it into a
bool filter on `access_classification`, `access_domains` (plus documents with no domains) and `access_embargo_until`
(missing or `<= now`); PG fact queries join observations to their document/table access and apply the same rule.

## 5. Where it is enforced

- Inside every route (T3.4): node and page indexes carry `access_*` fields (copied by reindex from Postgres);
  fact queries read only visible observations.
- Counts and gap codes over the visible scope only (T3.5); facts recomputed from visible observations.
- Every evidence id re-checked before it is returned (T3.6); "no permission" and "does not exist" give the same error.
- Audit (T3.7): `quality.access_audit` rows with subject, tool, returned ids and the number filtered; never in
  responses.

## 6. Scope of the guarantee (after review)

A subject learns nothing about content it may not see through the five tools (search, read, browse, resolve_concept,
get_metric_series), the page image and page regions endpoints, the document list and the document tree endpoint
(`/v1/admin/docs`, `/v1/admin/docs/{doc}/nodes`). Search re-checks every candidate against the labels in Postgres
(authoritative; the index may be stale), and a resource without a label is visible only to full access (fail closed).
Admin traces, sessions, runs, evaluations and the access audit are an operator view and are not filtered by subject.
The subject is self-asserted (header, query parameter or chat body): real authentication is outside round 2.
