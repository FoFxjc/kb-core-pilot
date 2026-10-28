import pytest

from kb_core.cli import SUBCOMMANDS, main


def test_help_lists_subcommands(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    for name in ["doctor", "migrate", "import", "build", "facts", "reindex", "serve", "eval"]:
        assert name in out
    assert set(SUBCOMMANDS) >= {"doctor", "migrate", "import", "build", "facts", "reindex", "serve", "eval"}


def test_unknown_command_exits_2():
    with pytest.raises(SystemExit) as e:
        main(["no-such-command"])
    assert e.value.code == 2


def test_unknown_eval_kind_exits_2(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("KB_CORE_PG_DSN", "postgresql://unused")
    monkeypatch.setenv("KB_CORE_ES_URL", "http://unused")
    assert main(["eval", "nope"]) == 2
    assert "not implemented" in capsys.readouterr().err


def test_config_error_is_a_message_not_a_traceback(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("KB_CORE_PG_DSN", raising=False)
    monkeypatch.delenv("KB_CORE_ES_URL", raising=False)
    assert main(["doctor"]) == 1
    assert "KB_CORE_PG_DSN" in capsys.readouterr().err


def _recall_file(path, no_year_hits):
    import json

    summary = {"single": {"questions": 1, "with_year": {"node_hit_at5": 1, "page_hit_at5": 1},
                          "no_year": {"node_hit_at5": no_year_hits, "page_hit_at5": no_year_hits}},
               "cross_year": {"questions": 0, "node_hit": 0, "page_hit": 0}}
    path.write_text(json.dumps({"summary": summary, "single": [], "cross_year": []}))
    return str(path)


def test_eval_compare_exits_1_on_a_regression_and_0_otherwise(tmp_path, capsys):
    base = _recall_file(tmp_path / "base.json", 1)
    worse = _recall_file(tmp_path / "worse.json", 0)
    assert main(["eval", "compare", base, base]) == 0
    assert main(["eval", "compare", base, worse]) == 1
    assert "single.no_year.node_hit_at5" in capsys.readouterr().out


def test_eval_compare_rejects_a_file_without_a_known_block(tmp_path, capsys):
    import json

    (tmp_path / "x.json").write_text(json.dumps({"commands": []}))
    assert main(["eval", "compare", str(tmp_path / "x.json"), str(tmp_path / "x.json")]) == 2


def test_eval_compare_needs_two_files(capsys):
    assert main(["eval", "compare", "only-one.json"]) == 2


def test_eval_compare_reads_an_exceptions_file(tmp_path, capsys):
    import json

    import yaml

    def run_file(name, node_rank):
        row = {"id": "q01", "with_year": {"node_hit_rank": 1, "page_hit_rank": 1},
               "no_year": {"node_hit_rank": node_rank, "page_hit_rank": 1}}
        summary = {"single": {"questions": 1, "with_year": {"node_hit_at5": 1, "page_hit_at5": 1},
                              "no_year": {"node_hit_at5": 1 if node_rank else 0, "page_hit_at5": 1}}}
        (tmp_path / name).write_text(json.dumps({"summary": summary, "single": [row], "cross_year": []}))
        return str(tmp_path / name)

    base, new = run_file("base.json", 2), run_file("new.json", None)
    exc = tmp_path / "exceptions.yaml"
    exc.write_text(yaml.safe_dump({"exceptions": [{"id": "q01", "variant": "no_year", "field": "node_hit_rank",
                                                   "reason": "gold node split", "approved_by": "project-owner",
                                                   "pr": 7}]}))
    assert main(["eval", "compare", base, new]) == 1
    assert main(["eval", "compare", base, new, "--exceptions", str(exc)]) == 2   # --pr is required with exceptions
    assert main(["eval", "compare", base, new, "--exceptions", str(exc), "--pr", "7"]) == 0
    assert '"waived"' in capsys.readouterr().out
