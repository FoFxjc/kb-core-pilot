import shutil

import pytest

from kb_core.pg.migrate import MIGRATIONS, MigrationError, current_version, migrate

pytestmark = pytest.mark.pg

TABLES = {
    "registry": {"source", "document", "ingest_run"},
    "content": {"node", "page", "region", "table_block", "table_merge"},
    "concept": {"concept", "concept_alias", "concept_edge", "node_concept"},
    "fact": {"observation", "fact", "fact_version", "fact_obs_link"},
    "quality": {"trace_event", "gap_log", "coverage"},
    "eval": {"eval_run", "eval_result", "answer_check"},
}


def test_migrate_applies_all_then_noop(pg_conn):
    applied = migrate(pg_conn)
    assert applied == sorted(p.name for p in MIGRATIONS.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    assert migrate(pg_conn) == []
    assert current_version(pg_conn) == len(applied)


def test_schemas_exist(pg_conn):
    migrate(pg_conn)
    rows = pg_conn.execute(
        "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema = ANY(%s)",
        [list(TABLES)]).fetchall()
    found: dict[str, set] = {}
    for schema, table in rows:
        found.setdefault(schema, set()).add(table)
    for schema, tables in TABLES.items():
        assert tables <= found.get(schema, set()), schema


def test_migrate_refuses_edited_applied_file(pg_conn, tmp_path):
    d = tmp_path / "migrations"
    shutil.copytree(MIGRATIONS, d)
    migrate(pg_conn, d)
    first = sorted(d.glob("0001_*.sql"))[0]
    first.write_text(first.read_text() + "\n-- edited\n")
    with pytest.raises(MigrationError, match=first.name):
        migrate(pg_conn, d)


def test_current_version_zero_on_empty_db(pg_conn):
    assert current_version(pg_conn) == 0
