"""Spot-check sheets (kb D22 protocol, scripts/t3_sample.py): sample n primary-tree nodes of one document with a fixed
seed; a node is correct only if its title, its page range and its parent are all right. Judges fill `verdict`
(correct | wrong) and `note` from the source PDF."""

import random

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from kb_core.queries import pg_query

PROTOCOL = "D22: correct only if title, page range and parent are all right; judged against the source PDF"


def tree_sheet(conn: psycopg.Connection, doc_id: str, n: int = 40, seed: int = 101) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(pg_query("V1_tree_sample_nodes")[1], {"doc_id": doc_id})
        nodes = cur.fetchall()
        cur.execute(pg_query("R1_pages_range")[1], {"doc_id": doc_id, "start": 1, "end": 100000})
        pages = {p["page_no"]: p for p in cur.fetchall()}
    by_id = {r["node_id"]: r for r in nodes}
    picked = sorted(random.Random(seed).sample(nodes, min(n, len(nodes))), key=lambda r: r["ord"])
    items = []
    for r in picked:
        parent = by_id.get(r["parent_id"])
        start = pages.get(r["start_page"]) or {}
        items.append({
            "node_id": r["node_id"], "title": r["title"], "origin": r["origin"],
            "pages": [r["start_page"], r["end_page"]], "printed_pages": r["page_label_range"],
            "parent": ({"node_id": parent["node_id"], "title": parent["title"],
                        "pages": [parent["start_page"], parent["end_page"]]} if parent else None),
            "start_page_text": " ".join((start.get("text") or "").split())[:200],
            "verdict": None, "note": ""})
    return {"doc_id": doc_id, "seed": seed, "sampled": len(items), "protocol": PROTOCOL, "items": items}


def tree_accuracy(sheet: dict) -> dict:
    """Spot-check accuracy of a judged tree sheet; every item must carry a verdict."""
    verdicts = [it.get("verdict") for it in sheet["items"]]
    if not verdicts or any(v not in ("correct", "wrong") for v in verdicts):
        raise ValueError(f"sheet for {sheet['doc_id']} is not judged (every item needs verdict correct or wrong)")
    correct = verdicts.count("correct")
    return {"doc_id": sheet["doc_id"], "seed": sheet.get("seed"), "correct": correct, "sampled": len(verdicts),
            "value": round(correct / len(verdicts), 4)}


def record_tree_accuracy(conn: psycopg.Connection, sheet: dict, sheet_name: str) -> dict:
    """Write a judged sheet's accuracy as the document's tree_sample_accuracy (read by tree_quality_low)."""
    acc = tree_accuracy(sheet)
    conn.execute(pg_query("V5_upsert_document_coverage")[1], {
        "doc_id": acc["doc_id"], "metric": "tree_sample_accuracy", "numerator": acc["correct"],
        "denominator": acc["sampled"], "value": Jsonb({**acc, "sheet": sheet_name}), "config_version": None})
    return acc


TAG_PROTOCOL = ("D39: a tag is correct when the node actually reports or discusses the concept (it is the title, a "
                "table has its row, or the text gives its value or change); a node is correct only if all its tags are")


def concept_sheet(conn: psycopg.Connection, lang: str, n: int = 40, seed: int = 101) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(pg_query("V2_tagged_nodes")[1], {"lang": lang})
        nodes = cur.fetchall()
    picked = sorted(random.Random(seed).sample(nodes, min(n, len(nodes))), key=lambda r: (r["doc_id"], r["ord"]))
    items = [{"doc_id": r["doc_id"], "node_id": r["node_id"], "title": r["title"],
              "pages": [r["start_page"], r["end_page"]], "printed_pages": r["page_label_range"], "tags": r["tags"],
              "verdict": None, "wrong_tags": [], "note": ""} for r in picked]
    return {"lang": lang, "seed": seed, "sampled": len(items), "protocol": TAG_PROTOCOL, "items": items}
