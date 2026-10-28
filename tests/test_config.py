from pathlib import Path

import pytest

from kb_core.config import ConfigError, load_settings

BASE = {"KB_CORE_PG_DSN": "postgresql://u:secret@localhost:5433/kbcore", "KB_CORE_ES_URL": "http://localhost:9200"}


def test_reads_only_kb_core_vars(tmp_path):
    env = {**BASE, "INTAKE_INDEX_PREFIX": "intake_", "INDEX_PREFIX": "x_"}
    s = load_settings(env, env_file=None)
    assert s.index_prefix == "kbcore_"


def test_dotenv_ignores_other_names(tmp_path):
    f = tmp_path / ".env"
    f.write_text("INTAKE_CHAT_ENABLED=true\nKB_CORE_CHAT_ENABLED=false\n")
    s = load_settings(BASE, env_file=f)
    assert s.chat_enabled is False


def test_env_overrides_dotenv(tmp_path):
    f = tmp_path / ".env"
    f.write_text('KB_CORE_INDEX_PREFIX="from_file_"  # comment\nKB_CORE_PORT=9999\n')
    s = load_settings({**BASE, "KB_CORE_INDEX_PREFIX": "from_env_"}, env_file=f)
    assert s.index_prefix == "from_env_"
    assert s.port == 9999


def test_missing_pg_dsn_raises_config_error():
    with pytest.raises(ConfigError, match="KB_CORE_PG_DSN"):
        load_settings({"KB_CORE_ES_URL": "http://localhost:9200"}, env_file=None)


def test_redacted_hides_secrets():
    s = load_settings({**BASE, "KB_CORE_ES_PASSWORD": "pw", "KB_CORE_ES_API_KEY": "k"}, env_file=None)
    red = s.redacted()
    assert "secret" not in str(red) and red["es_password"] == "***" and red["es_api_key"] == "***"
    assert "***" in red["pg_dsn"] and "localhost" in red["pg_dsn"] and "kbcore" in red["pg_dsn"]


def test_index_prefix_must_be_lowercase():
    with pytest.raises(ConfigError, match="KB_CORE_INDEX_PREFIX"):
        load_settings({**BASE, "KB_CORE_INDEX_PREFIX": "KB_"}, env_file=None)


def test_defaults():
    s = load_settings(BASE, env_file=None)
    assert (s.host, s.port, s.domain, s.store_dir, s.llm_enabled) == ("127.0.0.1", 8200, "banking", Path("store"), False)
    assert s.llm.api_key_var == "KB_CORE_LLM_API_KEY" and s.env == "development" and s.auth_mode == "none"
    assert (s.aliases, s.coverage_threshold, s.clock_override, s.now, s.delivery_dir) == (True, None, False, None, None)


def test_redacted_hides_keyword_and_query_dsn_passwords():
    for dsn in ("host=db port=5432 dbname=kb user=u password=topsecret",
                "postgresql://h/db?password=qsecret&sslmode=require"):
        s = load_settings({**BASE, "KB_CORE_PG_DSN": dsn}, env_file=None)
        red = s.redacted()["pg_dsn"]
        assert "topsecret" not in red and "qsecret" not in red and "***" in red


def test_redacted_hides_es_url_credentials():
    s = load_settings({**BASE, "KB_CORE_ES_URL": "http://elastic:espw@127.0.0.1:9200"}, env_file=None)
    assert "espw" not in s.redacted()["es_url"]


# --- model endpoints by purpose (enterprise readiness A2) ----------------------------------------------------------------

DEFAULT_LLM = {"KB_CORE_LLM_BASE_URL": "https://llm.example.internal/v1/", "KB_CORE_LLM_MODEL": "default-model",
               "KB_CORE_LLM_API_KEY": "k-default", "KB_CORE_LLM_CA_CERTS": "/etc/pki/company-ca.pem"}


def test_purposes_fall_back_to_the_default_endpoint():
    s = load_settings({**BASE, **DEFAULT_LLM, "KB_CORE_CHAT_ENABLED": "true"}, env_file=None)
    for e in (s.chat, s.judge, s.extract):
        assert (e.base_url, e.model, e.api_key_var, e.api_key, e.ca_certs) == (
            "https://llm.example.internal/v1", "default-model", "KB_CORE_LLM_API_KEY", "k-default",
            "/etc/pki/company-ca.pem")
    assert (s.chat.timeout_s, s.judge.timeout_s, s.extract.timeout_s) == (120, 30, 120)
    assert s.chat.enabled and not s.judge.enabled and not s.extract.enabled


def test_each_purpose_overrides_url_model_key_variable_ca_and_timeout():
    s = load_settings({**BASE, **DEFAULT_LLM, "KB_CORE_LLM_TIMEOUT_S": "45",
                       "KB_CORE_JUDGE_ENABLED": "true", "KB_CORE_JUDGE_BASE_URL": "https://judge.example.internal/v1",
                       "KB_CORE_JUDGE_MODEL": "small", "KB_CORE_JUDGE_API_KEY_VAR": "KB_CORE_JUDGE_API_KEY",
                       "KB_CORE_JUDGE_API_KEY": "k-judge", "KB_CORE_JUDGE_CA_CERTS": "/etc/pki/judge-ca.pem",
                       "KB_CORE_JUDGE_TIMEOUT_S": "10", "KB_CORE_JUDGE_MAX_CALLS_PER_QUERY": "1"}, env_file=None)
    j = s.judge
    assert (j.base_url, j.model, j.api_key, j.ca_certs, j.timeout_s) == (
        "https://judge.example.internal/v1", "small", "k-judge", "/etc/pki/judge-ca.pem", 10)
    assert s.judge_max_calls_per_query == 1
    assert s.chat.timeout_s == 45 and s.chat.api_key == "k-default"      # the default's timeout and key


def test_the_judge_is_off_by_default():
    s = load_settings({**BASE, **DEFAULT_LLM}, env_file=None)
    assert not s.judge.enabled and s.judge_max_calls_per_query == 2 and not s.llm_enabled


def test_an_enabled_purpose_needs_a_url_and_a_model():
    with pytest.raises(ConfigError, match="KB_CORE_EXTRACT_ENABLED"):
        load_settings({**BASE, "KB_CORE_EXTRACT_ENABLED": "true"}, env_file=None)


def test_httpx_options_without_a_ca_bundle_use_the_default_verification():
    assert load_settings(BASE, env_file=None).chat.httpx_options() == {"verify": True, "timeout": 120,
                                                                      "trust_env": True}


def test_redacted_hides_every_purpose_key():
    s = load_settings({**BASE, **DEFAULT_LLM, "KB_CORE_EXTRACT_API_KEY_VAR": "KB_CORE_EXTRACT_KEY",
                       "KB_CORE_EXTRACT_KEY": "k-extract"}, env_file=None)
    red = str(s.redacted())
    assert "k-default" not in red and "k-extract" not in red and "k-default" not in repr(s)


def test_retrieval_switches_are_settings():
    s = load_settings({**BASE, "KB_CORE_COVERAGE_THRESHOLD": "0.4", "KB_CORE_ALIASES": "off"}, env_file=None)
    assert s.coverage_threshold == 0.4 and s.aliases is False
    with pytest.raises(ConfigError, match="KB_CORE_ALIASES"):
        load_settings({**BASE, "KB_CORE_ALIASES": "no"}, env_file=None)
    with pytest.raises(ConfigError, match="KB_CORE_COVERAGE_THRESHOLD"):
        load_settings({**BASE, "KB_CORE_COVERAGE_THRESHOLD": "high"}, env_file=None)


def test_coverage_threshold_reaches_ranking():
    from kb_core.config import use
    from kb_core.retrieval.search import ranking

    default = ranking()["threshold"]
    try:
        use(load_settings({**BASE, "KB_CORE_COVERAGE_THRESHOLD": "0.25"}, env_file=None))
        assert ranking()["threshold"] == 0.25
    finally:
        use(None)
    assert ranking()["threshold"] == default


def test_paths_are_not_home_expanded():
    tilde = str(Path("~") / "store")                 # a home-relative path is taken literally, never expanded
    s = load_settings({**BASE, "KB_CORE_STORE_DIR": tilde}, env_file=None)
    assert str(s.store_dir) == tilde


def test_an_empty_environment_variable_does_not_hide_the_env_file(tmp_path):
    f = tmp_path / ".env"
    f.write_text("KB_CORE_ENV=production\nKB_CORE_NOW=2030-01-01T00:00:00Z\n")
    with pytest.raises(ConfigError, match="production refuses"):
        load_settings({**BASE, "KB_CORE_ENV": ""}, env_file=f)


def test_httpx_options_load_the_purpose_ca_bundle_as_an_ssl_context():
    import ssl

    import certifi

    s = load_settings({**BASE, **DEFAULT_LLM, "KB_CORE_CHAT_CA_CERTS": certifi.where()}, env_file=None)
    opts = s.chat.httpx_options()
    assert isinstance(opts["verify"], ssl.SSLContext) and opts["trust_env"] is True and opts["timeout"] == 120
