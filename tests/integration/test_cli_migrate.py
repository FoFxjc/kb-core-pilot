import json

import pytest

from kb_core.cli import main
from tests.conftest import PG_DSN

pytestmark = pytest.mark.pg


def test_cli_migrate_twice(pg_conn, monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)  # no .env here
    monkeypatch.setenv("KB_CORE_PG_DSN", PG_DSN)
    monkeypatch.setenv("KB_CORE_ES_URL", "http://127.0.0.1:9200")
    assert main(["migrate"]) == 0
    first = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert main(["migrate"]) == 0
    second = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert first["applied"] and second["applied"] == []
    assert first["version"] == second["version"] == len(first["applied"])
