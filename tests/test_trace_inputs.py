"""scripts/trace_inputs.py: classification of the paths a kb-core command opens (round 2 T0.1 blind check)."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("trace_inputs", ROOT / "scripts" / "trace_inputs.py")
trace_inputs = importlib.util.module_from_spec(_spec)
sys.modules["trace_inputs"] = trace_inputs  # dataclasses look their module up here
_spec.loader.exec_module(trace_inputs)

ROOTS = trace_inputs.Roots(
    repo=Path("/w/kb-core"),
    delivery=Path("/d/delivery"),
    store=Path("/d/store"),
    python=(Path("/w/kb-core/.venv"), Path("/opt/py")),
    forbidden=(Path("/w/kb"), Path("/w/kb-intake")),
)


def classify(p: str) -> str:
    return trace_inputs.classify(Path(p), ROOTS)


def test_repo_files_are_named_by_their_top_folder():
    assert classify("/w/kb-core/domains/banking/concepts.yaml") == "repo:domains"
    assert classify("/w/kb-core/queries/pg/M1_facts.v1.sql") == "repo:queries"


def test_delivery_and_store_are_package_inputs():
    assert classify("/d/delivery/ocbc/manifest.json") == "delivery"
    assert classify("/d/store/ocbc-group_ar_2025_en/regions.jsonl") == "store"


def test_python_runtime_is_its_own_class():
    assert classify("/w/kb-core/.venv/lib/python3.12/site-packages/psycopg/__init__.py") == "python"
    assert classify("/opt/py/lib/python3.12/json/__init__.py") == "python"


def test_kb_is_forbidden_but_a_sibling_with_the_same_prefix_is_not():
    assert classify("/w/kb/data/jsonl/nodes.jsonl") == "FORBIDDEN"
    assert classify("/w/kb-intake/src/kb_intake/cli.py") == "FORBIDDEN"
    assert classify("/w/kb-core/src/kb_core/cli.py") == "repo:src"


def test_unknown_locations_are_other():
    assert classify("/srv/elsewhere/notes.txt") == "other"


def test_read_write_modes_count_as_writes():
    assert trace_inputs.is_write("r+") and trace_inputs.is_write("rb+") and trace_inputs.is_write("wb")
    assert trace_inputs.is_write("a") and trace_inputs.is_write("x")
    assert not trace_inputs.is_write("r") and not trace_inputs.is_write("rb")


def test_the_report_names_paths_relative_to_their_root():
    show = lambda p: trace_inputs.display(Path(p), ROOTS)  # noqa: E731
    assert show("/w/kb-core/domains/banking/concepts.yaml") == "<repo>/domains/banking/concepts.yaml"
    assert show("/d/store/doc/pages.jsonl") == "<store>/doc/pages.jsonl"
    assert show("/d/delivery/pkg/manifest.json") == "<delivery>/pkg/manifest.json"
    assert show("/w/kb-intake/contract/v2/x.json") == "<forbidden:kb-intake>/contract/v2/x.json"
    assert show("/w/kb-core/.venv/lib/x.py") == "<python>/lib/x.py"
    assert show("/etc/hosts") == "/etc/hosts"


def test_forbidden_roots_must_be_given(capsys):
    import pytest

    with pytest.raises(SystemExit):
        trace_inputs.main(["--out", "unused.json", "--", "doctor"])
    assert "--forbid" in capsys.readouterr().err


def test_the_temp_folder_is_named_tmp():
    import tempfile

    tmp = Path(tempfile.gettempdir()).resolve()
    assert trace_inputs.display(tmp / "jieba.cache", ROOTS) == "<tmp>/jieba.cache"
