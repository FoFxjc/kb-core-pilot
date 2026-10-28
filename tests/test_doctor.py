import json

import pytest

from kb_core import doctor
from kb_core.config import load_settings
from kb_core.doctor import Check, doctor_main, run_checks

BASE = {"KB_CORE_PG_DSN": "postgresql://u:topsecret@127.0.0.1:1/x", "KB_CORE_ES_URL": "http://127.0.0.1:1",
        "KB_CORE_ES_PASSWORD": "espass"}


def settings(tmp_path, **extra):
    d = tmp_path / "delivery"
    d.mkdir(exist_ok=True)
    env = {**BASE, "KB_CORE_DELIVERY_DIR": str(d), "KB_CORE_STORE_DIR": str(tmp_path / "store"), **extra}
    return load_settings(env, env_file=None)


def fake_checks(monkeypatch, es_version="8.19.23", pg_ok=True):
    monkeypatch.setattr(doctor, "_es_checks", lambda s: doctor.es_version_check(es_version) + [
        Check("es_analyzer", "ok", "kb_ws created", ""), Check("es_alias", "ok", "alias swap ok", "")])
    monkeypatch.setattr(doctor, "_pg_checks", lambda s: [
        Check("pg_connect", "ok" if pg_ok else "fail", "connected" if pg_ok else "connection refused",
              "" if pg_ok else "check KB_CORE_PG_DSN"),
        Check("pg_migrations", "ok", "version 6 of 6", "")])


def test_all_ok_exits_0(tmp_path, monkeypatch, capsys):
    fake_checks(monkeypatch)
    assert doctor_main(settings(tmp_path), None) == 0
    assert "FAIL" not in capsys.readouterr().out


def test_one_failure_exits_1_and_names_fix(tmp_path, monkeypatch, capsys):
    fake_checks(monkeypatch, pg_ok=False)
    assert doctor_main(settings(tmp_path), None) == 1
    out = capsys.readouterr().out
    assert "FAIL pg_connect" in out and "check KB_CORE_PG_DSN" in out


def test_es_7_10_warns_vector_route_unavailable(tmp_path, monkeypatch, capsys):
    fake_checks(monkeypatch, es_version="7.10.1")
    assert doctor_main(settings(tmp_path), None) == 0
    assert "vector route unavailable" in capsys.readouterr().out


def test_es_below_7_10_fails():
    [c] = doctor.es_version_check("7.9.3")
    assert c.level == "fail" and "7.10" in c.fix


def test_es_8_ok():
    [c] = doctor.es_version_check("8.19.23")
    assert c.level == "ok"


def test_llm_check_skipped_when_disabled(tmp_path, monkeypatch):
    fake_checks(monkeypatch)
    names = [c.name for c in run_checks(settings(tmp_path))]
    assert "llm" not in names


def test_missing_delivery_dir_fails(tmp_path, monkeypatch):
    fake_checks(monkeypatch)
    s = settings(tmp_path, KB_CORE_DELIVERY_DIR=str(tmp_path / "nope"))
    c = {c.name: c for c in run_checks(s)}["delivery_dir"]
    assert c.level == "fail"


def test_report_never_contains_secrets(tmp_path, monkeypatch):
    fake_checks(monkeypatch)
    report = tmp_path / "r.json"
    doctor_main(settings(tmp_path), report)
    text = report.read_text()
    assert "topsecret" not in text and "espass" not in text
    assert json.loads(text)["ok"] is True


def test_unreachable_es_detail_hides_url_password(tmp_path):
    s = settings(tmp_path, KB_CORE_ES_URL="http://elastic:espw@127.0.0.1:1")
    checks = doctor._es_checks(s)
    assert checks[0].level == "fail"
    assert "espw" not in checks[0].detail


def test_es_transport_error_after_info_is_a_check_not_a_traceback(tmp_path, monkeypatch):
    import httpx

    from kb_core.es import client

    calls = {"n": 0}

    def flaky(self, method, path, **kw):
        calls["n"] += 1
        if path == "/":
            return {"version": {"number": "8.19.23"}}
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(client.EsClient, "request", flaky)
    checks = doctor._es_checks(settings(tmp_path))
    assert any(c.level == "fail" and "ReadTimeout" in c.detail for c in checks)
