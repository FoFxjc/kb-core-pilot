"""`kb-core build`: interpret one imported document into Postgres (design §3).

One transaction per document: delete the document's interpretation rows, run the stages, insert, record one
ingest_run row per stage. The same package with the same configuration (profile + domain files) gives the same
rows; `content_digest` proves it.
"""

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from kb_core.build.cells import load_units
from kb_core.build.chunks import deepest_covering, node_rows, page_rows, region_rows, table_rows
from kb_core.build.concepts import load_concepts, load_spec, node_fields, tag_nodes
from kb_core.build.facts import merge
from kb_core.build.observations import extract, observation_rules
from kb_core.build.tables import interpret, merge_continued
from kb_core.build.sections import assign
from kb_core.build.tree import flatten
from kb_core.build.view import DocView
from kb_core.config import Settings
from kb_core.domains import domain_dir
from kb_core.intake.package import Package
from kb_core.profiles import Profile, get
from kb_core.queries import pg_query

JSON_COLUMNS = {"font", "cells", "parsed", "continued_hint"}
OVERRIDES = "node_concept_overrides.yaml"


@dataclass
class FactSummary:
    observations: int
    facts: int
    agreed: int
    single: int
    conflict: int
    restated: int
    metrics_covered: list[str]


@dataclass
class RunSummary:
    doc_id: str
    run_id: uuid.UUID
    config_version: str
    counts: dict = field(default_factory=dict)


def config_version(profile: Profile, domain: str) -> str:
    """sha256 over the profile and domain pack files the build reads (their paths and bytes)."""
    h = hashlib.sha256()
    files = list(profile.files) + sorted(p for p in domain_dir(domain).iterdir() if p.is_file())
    for p in files:
        h.update(f"{p.parent.name}/{p.name}\n".encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def _execute(conn: psycopg.Connection, name: str, params: dict) -> psycopg.Cursor:
    return conn.execute(pg_query(name)[1], params)


def _insert(conn: psycopg.Connection, name: str, rows: list[dict]) -> None:
    sql = pg_query(name)[1]
    wrapped = [{k: (Jsonb(v) if k in JSON_COLUMNS and v is not None else v) for k, v in r.items()} for r in rows]
    with conn.cursor() as cur:
        cur.executemany(sql, wrapped)


def load_view(conn: psycopg.Connection, settings: Settings, doc_id: str) -> tuple[DocView, dict, Package]:
    row = _execute(conn, "B01_doc_for_build", {"doc_id": doc_id}).fetchone()
    if row is None:
        raise LookupError(f"document {doc_id!r} is not imported")
    doc = dict(zip(("doc_id", "issuer_id", "doc_type", "fiscal_year", "lang", "package", "manifest", "access"), row))
    pkg = Package(Path(settings.store_dir) / "packages" / doc["package"], doc["manifest"])
    return DocView.from_package(pkg), doc, pkg


class _Stages:
    def __init__(self, run_id: uuid.UUID, doc_id: str, version: str):
        self.run_id, self.doc_id, self.version, self.rows = run_id, doc_id, version, []

    def record(self, stage: str, started: datetime, counts: dict, detail: dict | None = None) -> None:
        self.rows.append({"run_id": self.run_id, "doc_id": self.doc_id, "stage": stage, "status": "ok",
                          "config_version": self.version, "started_at": started, "finished_at": datetime.now(UTC),
                          "counts": Jsonb(counts), "detail": Jsonb(detail) if detail else None, "error": None})


def build_doc(conn: psycopg.Connection, settings: Settings, doc_id: str) -> RunSummary:
    view, doc, pkg = load_view(conn, settings, doc_id)
    profile = get(view.doc_type)
    version = config_version(profile, settings.domain)
    run = RunSummary(doc_id, uuid.uuid4(), version)
    stages = _Stages(run.run_id, doc_id, version)
    tree_source = profile.tree_rules.get("tree_source", "regions")

    t0 = datetime.now(UTC)
    notes: list[dict] = []
    tree = profile.build_tree(view, notes)
    stages.record("tree", t0, {"top_level": len(tree)}, {"notes": notes} if notes else None)
    t0 = datetime.now(UTC)
    assign(tree, profile.sections)
    nodes = flatten(tree, doc_id, tree_source)
    stages.record("sections", t0, {"typed": sum(1 for n in nodes if n.section_type)})
    t0 = datetime.now(UTC)
    covering = deepest_covering(nodes, view.page_count)
    label_source = (doc["manifest"]["metadata"].get("page_label_method") or {}).get("method")
    rows = {"B03_insert_node": node_rows(view, nodes, doc, settings.domain, tree_source),
            "B04_insert_page": page_rows(view, covering, doc, settings.domain, label_source),
            "B05_insert_region": region_rows(view, nodes, covering),
            "B06_insert_table_block": table_rows(view, list(pkg.tables()), covering)}
    stages.record("chunks", t0, {"nodes": len(rows["B03_insert_node"]), "pages": len(rows["B04_insert_page"]),
                                 "regions": len(rows["B05_insert_region"])})

    # access: the document label (refreshed from the overlay; only up unless lowered explicitly) and every node's,
    # page's and table's effective label (round 2 W3)
    t0 = datetime.now(UTC)
    doc_access = _label_rows(doc_id, doc.get("access"), rows, settings.access_labels)
    stages.record("access", t0, {"classification": doc_access["classification"],
                                 "restricted_nodes": sum(1 for r in rows["B03_insert_node"]
                                                         if r["access"].obj["classification"]
                                                         != doc_access["classification"])})

    # tables: interpret cells, record continued-table merges
    t0 = datetime.now(UTC)
    units = load_units(settings.domain)
    page_text = {p["page_no"]: p.get("text") or "" for p in view.pages}
    page_label = {p["page_no"]: p.get("page_label") for p in view.pages}
    preceding = _text_before_tables(view)
    interpreted = {}
    for t, row in zip(list(pkg.tables()), rows["B06_insert_table_block"]):
        it = interpret(t, preceding.get(t["table_id"], ""), units)
        interpreted[t["table_id"]] = (t, it)
        row.update(parsed=it.to_json(), unit_hint=it.unit_hint, table_kind="artifact" if it.is_artifact else "data")
    merges = merge_continued([t for t, _ in interpreted.values()])
    merge_rows = [{"merge_id": m.part_table_ids[0], "doc_id": doc_id, "part_table_ids": m.part_table_ids,
                   "reason": m.reason, "decision": m.decision, "header_from": m.header_from} for m in merges]
    stages.record("tables", t0, {"tables": len(interpreted), "artifacts": sum(1 for _, it in interpreted.values()
                                                                               if it.is_artifact),
                                 "merged": sum(1 for m in merges if m.decision == "merged"),
                                 "hints": sum(1 for m in merges if m.decision == "hint")})

    # concepts: tag primary nodes (manual > rule_title > rule_row_label > rule_dict)
    t0 = datetime.now(UTC)
    spec = load_spec(*_spec_paths(settings.domain))
    load_concepts(conn, spec)
    node_dicts = [r for r in rows["B03_insert_node"] if r["is_primary"]]
    table_labels = [{"node_id": r["node_id"], "labels": [x.label for x in interpreted[r["table_id"]][1].rows]}
                    for r in rows["B06_insert_table_block"] if r["node_id"]]
    tags = tag_nodes(node_dicts, page_text, table_labels, spec, _overrides(), domain=settings.domain)
    fields = node_fields(tags)
    for r in rows["B03_insert_node"]:
        f = fields.get(r["node_id"]) or {}
        r.update(concept_ids=f.get("concept_ids") or [], concept_tok=f.get("concept_tok"))
    tag_rows = [dict(t, doc_id=doc_id) for t in tags]
    stages.record("concepts", t0, {"tags": len(tags), "nodes": len(fields)})

    # observations: profile rules over interpreted tables
    t0 = datetime.now(UTC)
    obs = extract({"doc_id": doc_id, "fiscal_year": doc["fiscal_year"], "issuer_id": doc["issuer_id"]},
                  [{"table": t, "interpreted": it, "page_text": page_text.get(t["page_no"], ""),
                    "page_label": page_label.get(t["page_no"])} for t, it in interpreted.values()],
                  spec, units, observation_rules(view.doc_type), settings.domain)
    stages.record("observations", t0, {"observations": len(obs)})
    run.counts = {"nodes": len(rows["B03_insert_node"]), "pages": len(rows["B04_insert_page"]),
                  "regions": len(rows["B05_insert_region"]), "tables": len(rows["B06_insert_table_block"]),
                  "tags": len(tags), "observations": len(obs)}
    with conn.transaction():
        _execute(conn, "B02_delete_doc_content", {"doc_id": doc_id})
        _execute(conn, "B14_update_document_access", {"doc_id": doc_id, "access": Jsonb(doc_access)})
        for name, data in rows.items():
            _insert(conn, name, data)
        _insert(conn, "B11_insert_table_merge", merge_rows)
        _insert(conn, "B12_insert_node_concept", tag_rows)
        _insert(conn, "B13_insert_observation", obs)
        _insert(conn, "B07_insert_ingest_run", stages.rows)
        _insert(conn, "B10_insert_build_gap", [{"doc_id": doc_id, "code": g["code"], "page_no": g.get("page_no"),
                                                "detail": Jsonb(g)} for g in notes])
        _execute(conn, "B08_mark_document", {"doc_id": doc_id, "status": "built"})
    return run


def _label_rows(doc_id: str, current: dict | None, rows: dict[str, list[dict]], overlay_path=None) -> dict:
    """Set `access` (Jsonb) on node, page and table rows; return the document label."""
    from kb_core.access.labels import doc_label, load_overlay, node_labels, page_access

    overlay = load_overlay(overlay_path)
    label = doc_label(overlay, doc_id, current=current)
    nodes = node_labels(overlay, doc_id, label, rows["B03_insert_node"])
    for r in rows["B03_insert_node"]:
        r["access"] = Jsonb(nodes[r["node_id"]])
    pages = {}
    for r in rows["B04_insert_page"]:
        pages[r["page_no"]] = page_access(overlay, doc_id, label, r["page_no"],
                                          [nodes[n] for n in r.get("covering_node_ids") or [] if n in nodes])
        r["access"] = Jsonb(pages[r["page_no"]])
    for r in rows["B06_insert_table_block"]:
        r["access"] = Jsonb(nodes.get(r.get("node_id")) or pages.get(r.get("page_start")) or label)
    return label


def _spec_paths(domain: str):
    from kb_core.build.concepts import default_paths

    return default_paths(domain)


def _overrides() -> dict:
    import yaml

    from kb_core.paths import data_dir

    path = data_dir("config") / OVERRIDES
    return yaml.safe_load(path.read_text()) or {} if path.exists() else {}


def _text_before_tables(view: DocView) -> dict[str, str]:
    """Text of the regions just before each table on its page (unit hints such as "($ million)")."""
    out: dict[str, str] = {}
    recent: list[str] = []
    page = None
    for r in view.regions:
        if r["page_no"] != page:
            page, recent = r["page_no"], []
        if r["type"] == "table" and r.get("table_id"):
            out[r["table_id"]] = " ".join(recent[-3:])
        elif r["layer"] == "body" and r.get("text"):
            recent.append(r["text"])
    return out


def run_facts(conn: psycopg.Connection) -> FactSummary:
    """kb-core facts: merge every observation into facts (fact, fact_version and fact_obs_link rewritten)."""
    from psycopg.rows import dict_row

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(pg_query("F01_all_observations")[1])
        observations = cur.fetchall()
    facts = merge(observations)
    with conn.transaction():
        _execute(conn, "F02_clear_facts", {})
        _insert(conn, "F03_insert_fact", [{k: f[k] for k in ("fact_id", "concept_id", "entity_id", "fiscal_year",
                                                             "period_id", "unit", "restated_note")} for f in facts])
        _insert(conn, "F04_insert_fact_version", [{**{k: v[k] for k in ("version_no", "known_from", "known_to", "value",
                                                                          "status", "n_sources", "winning_obs_id")},
                                                   "fact_id": f["fact_id"]} for f in facts for v in f["versions"]])
        _insert(conn, "F05_insert_fact_obs_link", [dict(lk, fact_id=f["fact_id"]) for f in facts for lk in f["links"]])
    statuses = [v["status"] for f in facts for v in f["versions"]]
    return FactSummary(observations=len(observations), facts=len(facts), agreed=statuses.count("agreed"),
                       single=statuses.count("single"), conflict=statuses.count("conflict"),
                       restated=sum(1 for f in facts if len(f["versions"]) > 1),
                       metrics_covered=sorted({f["concept_id"] for f in facts}))


def content_digest(conn: psycopg.Connection, doc_id: str) -> str:
    return _execute(conn, "B09_content_digest", {"doc_id": doc_id}).fetchone()[0]


def build_all(conn: psycopg.Connection, settings: Settings, doc_ids: list[str] | None = None) -> list[RunSummary]:
    if not doc_ids:
        doc_ids = [r[0] for r in conn.execute(pg_query("I05_document_ids")[1])]
    out = []
    for d in doc_ids:
        t = time.monotonic()
        out.append(build_doc(conn, settings, d))
        out[-1].counts["seconds"] = round(time.monotonic() - t, 1)
    return out
