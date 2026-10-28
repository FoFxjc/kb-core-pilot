import pytest

from kb_core.build.run import build_doc, content_digest
from kb_core.config import load_settings
from kb_core.intake.importer import import_path
from kb_core.pg.migrate import migrate
from tests.conftest import PG_DSN
from tests.fixtures.mini_package import DOC, build_package

pytestmark = pytest.mark.pg


@pytest.fixture
def imported(pg_conn, tmp_path):
    migrate(pg_conn)
    s = load_settings({"KB_CORE_PG_DSN": PG_DSN, "KB_CORE_ES_URL": "http://unused",
                       "KB_CORE_STORE_DIR": str(tmp_path / "store")}, env_file=None)
    import_path(pg_conn, s, build_package(tmp_path / "delivery"))
    return pg_conn, s


def test_build_writes_content(imported):
    conn, s = imported
    summary = build_doc(conn, s, DOC)
    assert summary.counts["pages"] == 3 and summary.counts["regions"] == 8 and summary.counts["tables"] == 2
    assert summary.counts["nodes"] >= 2
    pages = conn.execute("SELECT page_no, covering_node_ids, text_tok FROM content.page WHERE doc_id = %s "
                         "ORDER BY page_no", [DOC]).fetchall()
    assert [p[0] for p in pages] == [1, 2, 3] and "overview" in pages[1][2]
    assert conn.execute("SELECT status FROM registry.document WHERE doc_id = %s", [DOC]).fetchone()[0] == "built"


def test_build_twice_identical(imported):
    conn, s = imported
    build_doc(conn, s, DOC)
    first = content_digest(conn, DOC)
    build_doc(conn, s, DOC)
    assert content_digest(conn, DOC) == first
    assert conn.execute("SELECT count(*) FROM content.node WHERE doc_id = %s", [DOC]).fetchone()[0] > 0


def test_build_records_runs_per_stage(imported):
    conn, s = imported
    summary = build_doc(conn, s, DOC)
    stages = [r[0] for r in conn.execute("SELECT stage FROM registry.ingest_run WHERE run_id = %s ORDER BY started_at",
                                         [summary.run_id])]
    assert stages == ["tree", "sections", "chunks", "access", "tables", "concepts", "observations"]
    versions = {r[0] for r in conn.execute("SELECT config_version FROM registry.ingest_run WHERE run_id = %s",
                                           [summary.run_id])}
    assert len(versions) == 1 and len(versions.pop()) == 64


def test_build_unknown_doc_raises(imported):
    conn, s = imported
    with pytest.raises(LookupError, match="nope"):
        build_doc(conn, s, "nope")


def test_cli_build(imported, monkeypatch, capsys, tmp_path):
    import json

    from kb_core.cli import main

    conn, s = imported
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KB_CORE_PG_DSN", PG_DSN)
    monkeypatch.setenv("KB_CORE_ES_URL", "http://unused")
    monkeypatch.setenv("KB_CORE_STORE_DIR", str(s.store_dir))
    assert main(["build", "--all"]) == 0
    out = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert out["doc_id"] == DOC and out["pages"] == 3
    assert main(["build", "nope"]) == 1


def test_tree_sample_sheet_is_seeded_and_complete(imported):
    from kb_core.eval.samples import tree_sheet

    conn, s = imported
    build_doc(conn, s, DOC)
    a = tree_sheet(conn, DOC, n=3, seed=7)
    b = tree_sheet(conn, DOC, n=3, seed=7)
    assert a == b and len(a["items"]) == min(3, conn.execute(
        "SELECT count(*) FROM content.node WHERE doc_id = %s", [DOC]).fetchone()[0])
    item = a["items"][0]
    assert {"node_id", "title", "origin", "pages", "printed_pages", "parent", "start_page_text", "verdict"} <= set(item)
    assert item["verdict"] is None and a["protocol"].startswith("D22")


def test_build_notes_become_build_gaps_and_run_detail(imported):
    conn, s = imported
    run = build_doc(conn, s, DOC)
    codes = [r[0] for r in conn.execute(
        "SELECT code FROM quality.gap_log WHERE doc_id = %s AND layer = 'build'", [DOC])]
    assert "font_colour_unavailable" in codes
    detail = conn.execute("SELECT detail FROM registry.ingest_run WHERE run_id = %s AND stage = 'tree'",
                          [run.run_id]).fetchone()[0]
    assert "font_colour_unavailable" in {g["code"] for g in detail["notes"]}
    build_doc(conn, s, DOC)    # a rebuild replaces build gaps, it does not add to them
    assert conn.execute("SELECT count(*) FROM quality.gap_log WHERE doc_id = %s AND layer = 'build' AND "
                        "code = 'font_colour_unavailable'", [DOC]).fetchone()[0] == 1


def test_build_interprets_tables_tags_and_extracts(imported):
    conn, s = imported
    run = build_doc(conn, s, DOC)
    assert [r[0] for r in conn.execute("SELECT stage FROM registry.ingest_run WHERE run_id = %s ORDER BY started_at",
                                       [run.run_id])] == ["tree", "sections", "chunks", "access", "tables", "concepts",
                                                          "observations"]
    parsed, kind = conn.execute("SELECT parsed, table_kind FROM content.table_block WHERE table_id = %s",
                                [f"{DOC}:t0002_01"]).fetchone()
    assert kind == "data" and parsed["rows"][-1]["label"] == "Net profit"
    assert conn.execute("SELECT decision, part_table_ids FROM content.table_merge WHERE doc_id = %s", [DOC]).fetchone() \
        == ("merged", [f"{DOC}:t0002_01", f"{DOC}:t0003_01"])
    obs = conn.execute("SELECT concept_id, fiscal_year, value FROM fact.observation WHERE doc_id = %s ORDER BY fiscal_year",
                       [DOC]).fetchall()
    assert [(c, y, int(v)) for c, y, v in obs] == [("net_profit", 2024, -5000000), ("net_profit", 2025, 1234000000)]


def test_facts_counts_on_fixture(imported):
    from kb_core.build.run import run_facts

    conn, s = imported
    build_doc(conn, s, DOC)
    summary = run_facts(conn)
    assert (summary.agreed, summary.single, summary.conflict) == (0, 2, 0) and summary.metrics_covered == ["net_profit"]
    assert conn.execute("SELECT count(*) FROM fact.fact").fetchone()[0] == 2
    build_doc(conn, s, DOC)            # a rebuild clears facts (they reference observations) until facts run again
    assert conn.execute("SELECT count(*) FROM fact.fact").fetchone()[0] == 0
    assert run_facts(conn).single == 2


def test_concept_sample_sheet_lists_tags(imported):
    from kb_core.eval.samples import concept_sheet

    conn, s = imported
    build_doc(conn, s, DOC)
    sheet = concept_sheet(conn, "en", n=5, seed=3)
    assert sheet == concept_sheet(conn, "en", n=5, seed=3) and sheet["sampled"] >= 1
    item = sheet["items"][0]
    assert item["tags"] and {"concept_id", "name_en", "method", "variant"} <= set(item["tags"][0])
    assert item["verdict"] is None and item["doc_id"] == DOC


def test_recorded_tree_accuracy_is_document_coverage(imported):
    from kb_core.eval.samples import record_tree_accuracy

    conn, _ = imported
    sheet = {"doc_id": DOC, "seed": 9, "sampled": 2, "items": [{"verdict": "correct"}, {"verdict": "wrong"}]}
    record_tree_accuracy(conn, sheet, "tree_x_9.judged.yaml")
    record_tree_accuracy(conn, sheet, "tree_x_9.judged.yaml")      # re-recording replaces the row
    rows = conn.execute("SELECT value, numerator, denominator FROM quality.coverage WHERE scope_type = 'document' "
                        "AND scope_id = %s AND metric = 'tree_sample_accuracy'", [DOC]).fetchall()
    assert len(rows) == 1 and rows[0][0]["value"] == 0.5 and rows[0][0]["sheet"] == "tree_x_9.judged.yaml"
    assert (rows[0][1], rows[0][2]) == (1, 2)


def test_cli_records_judged_tree_sheets(imported, tmp_path, monkeypatch, capsys):
    import json

    import yaml

    from kb_core.cli import main

    conn, s = imported
    sheet = tmp_path / "tree_x_3.judged.yaml"
    sheet.write_text(yaml.safe_dump({"doc_id": DOC, "seed": 3, "items": [{"verdict": "correct"}]}))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KB_CORE_PG_DSN", PG_DSN)
    monkeypatch.setenv("KB_CORE_ES_URL", "http://unused")
    monkeypatch.setenv("KB_CORE_STORE_DIR", str(s.store_dir))
    assert main(["eval", "tree", "--record", str(sheet)]) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1])[0]["value"] == 1.0


def test_snapshot_has_fact_counts_and_tree_accuracy(imported):
    from kb_core.build.run import run_facts
    from kb_core.eval.samples import record_tree_accuracy
    from kb_core.eval.snapshot import snapshot

    conn, s = imported
    build_doc(conn, s, DOC)
    run_facts(conn)
    record_tree_accuracy(conn, {"doc_id": DOC, "seed": 9, "items": [{"verdict": "correct"}, {"verdict": "wrong"}]},
                         "tree_x_9.judged.yaml")
    snap = snapshot(conn)
    assert snap["facts"] == {"observations": 2, "facts": 2, "agreed": 0, "single": 2, "conflict": 0, "restated": 0,
                             "metrics_covered": ["net_profit"]}
    assert snap["tree"] == {DOC: {"value": 0.5, "correct": 1, "sampled": 2, "seed": 9,
                                  "sheet": "tree_x_9.judged.yaml"}}


# --- round 2 W3: effective labels written by the build (T3.1, T3.2) ---

def test_build_writes_effective_labels_on_nodes_pages_and_tables(imported):
    conn, s = imported
    build_doc(conn, s, DOC)
    for table in ("content.node", "content.page", "content.table_block"):
        missing = conn.execute(f"SELECT count(*) FROM {table} WHERE doc_id = %s AND access IS NULL", [DOC]).fetchone()
        assert missing[0] == 0, table


def test_build_never_lowers_a_stored_document_label(imported):
    from psycopg.types.json import Jsonb

    conn, s = imported
    raised = {"classification": "confidential", "domains": ["finance"], "owner": "cfo", "embargo_until": None,
              "label_source": "intake"}
    conn.execute("UPDATE registry.document SET access = %s WHERE doc_id = %s", [Jsonb(raised), DOC])
    build_doc(conn, s, DOC)
    doc = conn.execute("SELECT access FROM registry.document WHERE doc_id = %s", [DOC]).fetchone()[0]
    node = conn.execute("SELECT access FROM content.node WHERE doc_id = %s LIMIT 1", [DOC]).fetchone()[0]
    assert doc["classification"] == "confidential" and node["classification"] == "confidential"


def test_tagged_nodes_carry_their_concept_ids_on_the_node_row(imported):
    conn, s = imported
    build_doc(conn, s, DOC)
    tagged = {r[0] for r in conn.execute("SELECT node_id FROM concept.node_concept WHERE doc_id = %s", [DOC])}
    on_rows = {r[0] for r in conn.execute("SELECT node_id FROM content.node WHERE doc_id = %s "
                                          "AND cardinality(concept_ids) > 0", [DOC])}
    assert tagged and tagged == on_rows


def test_cli_heading_check_reports_found_and_missed(imported, tmp_path, monkeypatch, capsys):
    import json

    import yaml

    from kb_core.cli import main

    conn, s = imported
    build_doc(conn, s, DOC)
    first = conn.execute("SELECT title, start_page FROM content.node WHERE doc_id = %s AND is_primary ORDER BY ord "
                         "LIMIT 1", [DOC]).fetchone()
    sheet = {"doc_id": DOC, "seed": 1, "pages": [{"page": first[1], "headings": [
        {"title": first[0], "level": 1}, {"title": "A Heading The Tree Does Not Have", "level": 2}]}]}
    f = tmp_path / f"{DOC}_1.judged.yaml"
    f.write_text(yaml.safe_dump(sheet))
    monkeypatch.setenv("KB_CORE_PG_DSN", PG_DSN)
    monkeypatch.setenv("KB_CORE_ES_URL", "http://unused")
    monkeypatch.chdir(tmp_path)
    assert main(["eval", "headings", str(f)]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["totals"] == {"judged": 2, "found": 1, "missed": 1, "misplaced": 0, "missed_rate": 0.5}
    assert out["docs"][0]["missed"] == [{"page": first[1], "title": "A Heading The Tree Does Not Have"}]
