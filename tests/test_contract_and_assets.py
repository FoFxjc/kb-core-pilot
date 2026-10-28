"""Contract copy, copied-asset provenance and the English-only rule (AGENTS.md "Language")."""

import io
import re
import subprocess
import sys
import tokenize
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CJK = re.compile(r"[\u3000-\u303f\u3400-\u9fff\uff00-\uffef]")
ASSET_DIRS = ("profiles", "domains", "config", "eval")
# YAML keys whose values must match Chinese source text or Chinese questions (data, not prose)
DATA_KEYS = {
    "zh", "regex", "snippet", "text", "variants", "query_only", "row_labels", "exclude", "year_pattern",
    "row_unit", "row_unit_strip", "table_unit_hint", "reporting_writings", "query", "question", "heldout_term",
    "variant_of", "answer", "cited_by_agent", "query_patterns", "title", "label_zh", "name_zh", "pattern",
    "patterns", "writings", "group", "label", "alias", "aliases", "terms", "stopwords", "words", "term", "dropped",
    "added_exclude", "reporting", "reporting_name", "foreign", "foreign_name", "generic", "inside_back_cover",
    "section", "continued", "refer_to", "title_start", "note", "subnote", "numbered", "other_entity", "no_dict",
    "movement", "caption", "target", "restated", "stat_units", "field_line", "dict_context_exclude",
}
DATA_PARENTS = {"answer", "absent_in"}  # every value under these keys is data (gold answers per year, evidence)
NO_CJK_DIRS = ("src", "scripts", "migrations", "queries", "es", "docs", "contract")
NO_CJK_FILES = ("README.md", "AGENTS.md", "CLAUDE.md", "pyproject.toml", ".env.example", "setup.sh")


def _chinese_prose(text: str) -> bool:
    """Chinese prose, not English prose that quotes Chinese terms: CJK characters outnumber Latin letters."""
    return len(CJK.findall(text)) > len(re.findall(r"[A-Za-z]", text))


def _walk(node, path=()):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, path + (str(k),))
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v, path)
    elif isinstance(node, str):
        yield path, node


def _yaml_comments(text: str) -> list[str]:
    out = []
    block_indent = None  # inside a block scalar (| or >) every more-indented line is content, not a comment
    for line in text.splitlines():
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if block_indent is not None:
            if not stripped or indent > block_indent:
                continue
            block_indent = None
        if re.search(r":\s*[|>][-+]?\s*$", line):
            block_indent = indent
        if stripped.startswith("#"):
            out.append(stripped)
        elif " #" in line:
            # a trailing comment outside quotes
            tail = re.sub(r"'[^']*'|\"[^\"]*\"", "", line)
            if " #" in tail:
                out.append(tail.split(" #", 1)[1])
    return out


def cjk_violations() -> list[str]:
    bad: list[str] = []
    for d in ASSET_DIRS:
        for p in sorted((ROOT / d).rglob("*.yaml")):
            if "results" in p.relative_to(ROOT).parts:
                continue
            text = p.read_text()
            for c in _yaml_comments(text):
                if _chinese_prose(c):
                    bad.append(f"{p.relative_to(ROOT)}: comment {c[:60]!r}")
            for path, value in _walk(yaml.safe_load(text)):
                key = path[-1] if path else ""
                if _chinese_prose(value) and key not in DATA_KEYS and not DATA_PARENTS & set(path) \
                        and not CJK.search(key):
                    bad.append(f"{p.relative_to(ROOT)}: {'.'.join(path)} = {value[:60]!r}")
    for d in NO_CJK_DIRS:
        for p in sorted((ROOT / d).rglob("*")):
            if p.is_file() and p.suffix in (".py", ".sql", ".json", ".md", ".sh", ".yaml", ".txt") \
                    and CJK.search(p.read_text(errors="ignore")):
                bad.append(f"{p.relative_to(ROOT)}: contains CJK")
    for name in NO_CJK_FILES:
        p = ROOT / name
        if p.exists() and CJK.search(p.read_text()):
            bad.append(f"{name}: contains CJK")
    for p in sorted((ROOT / "tests").rglob("*.py")):
        toks = tokenize.generate_tokens(io.StringIO(p.read_text()).readline)
        if any(t.type == tokenize.COMMENT and CJK.search(t.string) for t in toks):
            bad.append(f"{p.relative_to(ROOT)}: CJK in a comment")
    return bad


def test_no_cjk_outside_allowed_data():
    assert cjk_violations() == []


def test_assets_manifest_complete_and_hashes_match():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_assets.py")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_assets_check_detects_an_edit(tmp_path):
    import shutil

    for d in ("profiles", "domains", "config", "eval"):
        shutil.copytree(ROOT / d, tmp_path / d)
    shutil.copy(ROOT / "ASSETS.md", tmp_path / "ASSETS.md")
    (tmp_path / "config" / "ranking.yaml").write_text("version: 99\n")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_assets.py"), "--root", str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode == 1 and "config/ranking.yaml" in r.stdout


def test_contract_copy_matches_upstream():
    upstream = ROOT.parent / "kb-intake"
    if not (upstream / "contract" / "v2").is_dir():
        pytest.skip("kb-intake checkout not found next to kb-core")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_contract.py"), "--intake-repo", str(upstream)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_contract_check_detects_a_difference(tmp_path):
    fake = tmp_path / "kb-intake" / "contract" / "v2"
    fake.mkdir(parents=True)
    for p in (ROOT / "contract" / "intake-v2").glob("*.schema.json"):
        (fake / p.name).write_bytes(p.read_bytes())
    (fake / "page.schema.json").write_text("{}")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_contract.py"), "--intake-repo",
                        str(tmp_path / "kb-intake")], capture_output=True, text=True)
    assert r.returncode == 1 and "page.schema.json" in r.stdout


def test_update_own_refreshes_only_kb_core_rows(tmp_path):
    import shutil

    for d in ("profiles", "domains", "config", "eval"):
        shutil.copytree(ROOT / d, tmp_path / d)
    shutil.copy(ROOT / "ASSETS.md", tmp_path / "ASSETS.md")
    script = [sys.executable, str(ROOT / "scripts" / "check_assets.py"), "--root", str(tmp_path)]
    (tmp_path / "profiles" / "annual_report" / "tree.yaml").write_text("version: 2\n")    # kb-core's own file
    assert subprocess.run(script, capture_output=True, text=True).returncode == 1
    assert subprocess.run(script + ["--update-own"], capture_output=True, text=True).returncode == 0
    assert subprocess.run(script, capture_output=True, text=True).returncode == 0
    (tmp_path / "config" / "ranking.yaml").write_text("version: 99\n")                   # a copied file
    assert subprocess.run(script + ["--update-own"], capture_output=True, text=True).returncode == 1
