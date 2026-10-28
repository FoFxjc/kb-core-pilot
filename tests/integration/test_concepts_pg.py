import pytest

from kb_core.build.concepts import load_concepts, load_spec
from kb_core.pg.migrate import migrate

pytestmark = pytest.mark.pg


def test_load_concepts_is_idempotent_and_complete(pg_conn):
    migrate(pg_conn)
    spec = load_spec()
    first = load_concepts(pg_conn, spec)
    second = load_concepts(pg_conn, spec)
    assert first == second
    assert first["concept"] == len(spec["concepts"]) == pg_conn.execute("SELECT count(*) FROM concept.concept").fetchone()[0]
    assert pg_conn.execute("SELECT count(*) FROM concept.concept_alias").fetchone()[0] == first["concept_alias"]
    assert pg_conn.execute("SELECT count(*) FROM concept.concept_edge").fetchone()[0] == first["concept_edge"]
    row = pg_conn.execute("SELECT name_en, spec_version, derive FROM concept.concept WHERE concept_id = 'net_profit_margin'").fetchone()
    assert row[1] == spec["version"] and row[2] is not None
