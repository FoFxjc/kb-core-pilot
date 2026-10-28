import os
import stat

import pytest

from kb_core.config import load_settings
from kb_core.intake.importer import import_path
from kb_core.intake.package import PackageError
from kb_core.pg.migrate import migrate
from tests.conftest import PG_DSN
from tests.fixtures.mini_package import DOC, build_package

pytestmark = pytest.mark.pg


@pytest.fixture
def env(pg_conn, tmp_path):
    migrate(pg_conn)
    s = load_settings({"KB_CORE_PG_DSN": PG_DSN, "KB_CORE_ES_URL": "http://unused",
                       "KB_CORE_STORE_DIR": str(tmp_path / "store")}, env_file=None)
    return pg_conn, s, tmp_path


def count(conn, table, doc_id=DOC):
    return conn.execute(f"SELECT count(*) FROM {table} WHERE doc_id = %s", [doc_id]).fetchone()[0]


def test_import_registers_document_and_keeps_readonly_copy(env):
    conn, s, tmp = env
    [r] = import_path(conn, s, build_package(tmp / "delivery"))
    assert r.created and r.doc_id == DOC
    row = conn.execute("SELECT issuer_id, doc_type, fiscal_year, lang, page_count, contract_version, package, status "
                       "FROM registry.document WHERE doc_id = %s", [DOC]).fetchone()
    assert row[:6] == ("acme", "annual_report", 2025, "en", 3, "2") and row[7] == "imported"
    stored = s.store_dir / "packages" / row[6]
    assert (stored / "manifest.json").is_file()
    assert not os.stat(stored / "regions.jsonl").st_mode & stat.S_IWUSR
    assert count(conn, "quality.gap_log") == 1
    assert conn.execute("SELECT stage, status FROM registry.ingest_run WHERE doc_id = %s", [DOC]).fetchall() == \
        [("import", "ok")]


def test_import_is_idempotent(env):
    conn, s, tmp = env
    pkg = build_package(tmp / "delivery")
    import_path(conn, s, pkg)
    [again] = import_path(conn, s, pkg)
    assert not again.created
    assert count(conn, "registry.document") == 1 and count(conn, "quality.gap_log") == 1


def test_import_conflicting_sha_rejected(env):
    conn, s, tmp = env
    import_path(conn, s, build_package(tmp / "d1"))
    other = build_package(tmp / "d2", cover="Acme Annual Report 2025 (revised)")
    with pytest.raises(PackageError, match="already imported"):
        import_path(conn, s, other)


def test_rejects_schema_violation_and_writes_nothing(env):
    conn, s, tmp = env

    def bad(files):
        files["regions.jsonl"][0]["type"] = "banner"
    with pytest.raises(PackageError):
        import_path(conn, s, build_package(tmp / "delivery", mutate=bad))
    assert count(conn, "registry.document") == 0
    assert not (s.store_dir / "packages").exists() or not any((s.store_dir / "packages").iterdir())


def test_import_delivery_folder_imports_all(env):
    conn, s, tmp = env
    build_package(tmp / "delivery")
    build_package(tmp / "delivery", doc_id="acme_ar_2024_en", period_end="2024-12-31")
    results = import_path(conn, s, tmp / "delivery")
    assert sorted(r.doc_id for r in results) == ["acme_ar_2024_en", DOC]
    assert all(r.created for r in results)


def test_cli_import_prints_one_line_per_package(env, monkeypatch, capsys):
    import json

    from kb_core.cli import main

    conn, s, tmp = env
    build_package(tmp / "delivery")
    monkeypatch.chdir(tmp)
    monkeypatch.setenv("KB_CORE_PG_DSN", PG_DSN)
    monkeypatch.setenv("KB_CORE_ES_URL", "http://unused")
    monkeypatch.setenv("KB_CORE_STORE_DIR", str(tmp / "store"))
    monkeypatch.setenv("KB_CORE_DELIVERY_DIR", str(tmp / "delivery"))
    assert main(["import"]) == 0
    assert json.loads(capsys.readouterr().out.splitlines()[-1]) == {"doc_id": DOC, "package": next(
        (tmp / "delivery").iterdir()).name, "created": True}
    monkeypatch.setenv("KB_CORE_DELIVERY_DIR", str(tmp / "nowhere"))
    assert main(["import"]) == 1


def test_store_copy_is_fully_read_only(env):
    conn, s, tmp = env
    [r] = import_path(conn, s, build_package(tmp / "delivery"))
    root = s.store_dir / "packages" / r.package
    assert not os.stat(root).st_mode & stat.S_IWUSR


def test_stale_store_copy_with_other_manifest_is_refused(env):
    conn, s, tmp = env
    pkg = build_package(tmp / "d1")
    import_path(conn, s, pkg)
    conn.execute("DELETE FROM quality.gap_log; DELETE FROM registry.ingest_run; DELETE FROM registry.document")

    def different_regions(files):
        files["regions.jsonl"][0]["text"] = "Another title"
    redelivered = build_package(tmp / "d2", mutate=different_regions)
    assert redelivered.name == pkg.name
    with pytest.raises(PackageError, match="store"):
        import_path(conn, s, redelivered)


# --- round 2 W3: access labels at import (T3.1) ---

def test_import_stores_the_access_label(env):
    conn, s, tmp = env
    import_path(conn, s, build_package(tmp / "delivery"))
    access = conn.execute("SELECT access FROM registry.document WHERE doc_id = %s", [DOC]).fetchone()[0]
    assert access["classification"] and access["owner"] and access["label_source"] in ("default", "overlay")


def test_a_document_left_without_a_label_is_refused_and_nothing_is_written(env):
    from kb_core.access.labels import load_overlay
    from kb_core.intake.importer import import_one

    conn, s, tmp = env
    pkg = build_package(tmp / "delivery")
    with pytest.raises(PackageError, match="access label"):
        import_one(conn, s, pkg, overlay=load_overlay({"documents": [], "blocks": []}))
    assert count(conn, "registry.document") == 0
    assert not (s.store_dir / "packages").exists() or not any((s.store_dir / "packages").iterdir())
