"""Enterprise readiness A5 and C6: .env.example lists every KB_CORE_* name the code reads, and tracked files carry
no local or personal content (scripts/check_clean.py)."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r"KB_CORE_[A-Z0-9_]+")


def names_in_code() -> set[str]:
    """Every KB_CORE_* name in src/, scripts/ and the web test config (a family reference such as KB_CORE_CHAT_* is not a name)."""
    out = set()
    paths = [p for f in ("src", "scripts") for p in (ROOT / f).rglob("*.py")]
    paths += [ROOT / "web" / "playwright.config.ts", *(ROOT / "web" / "e2e").rglob("*.ts")]
    for path in paths:
        out |= {n for n in NAME.findall(path.read_text()) if not n.endswith("_")}
    return out


def test_env_example_lists_every_kb_core_name_the_code_reads():
    listed = set(NAME.findall((ROOT / ".env.example").read_text()))
    missing = sorted(names_in_code() - listed)
    assert not missing, f"add these to .env.example: {missing}"


def test_the_scan_sees_names_built_in_config():
    names = names_in_code()
    assert {"KB_CORE_JUDGE_MAX_CALLS_PER_QUERY", "KB_CORE_AUTH_GROUPS_HEADER", "KB_CORE_NOW"} <= names


def test_env_example_has_no_local_placeholders():
    text = (ROOT / ".env.example").read_text()
    assert "localhost" not in text and "127.0.0.1:5433" not in text and "~/" not in text
    test_only = text.split("NEVER IN PRODUCTION", 1)
    assert len(test_only) == 2 and "KB_CORE_NOW" in test_only[1] and "KB_CORE_TEST_PG_DSN" in test_only[1]
    assert "KB_CORE_NOW" not in test_only[0].replace("KB_CORE_NOW / ", "")


def test_no_direct_environment_reads_in_src():
    offenders = [str(p.relative_to(ROOT)) for p in (ROOT / "src").rglob("*.py")
                 if re.search(r"os\.environ|os\.getenv|getenv\(", p.read_text()) and p.name != "config.py"]
    assert offenders == []


def test_tracked_files_are_clean():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_clean.py")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:]


def test_check_clean_catches_each_class(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import check_clean
    finally:
        sys.path.pop(0)
    uuid = "-".join(["3f4090f2", "bd8b", "4933", "b4cc", "1a6264f9f5fa"])   # built so this file stays clean itself
    (tmp_path / "a.md").write_text("see /" + "Users/someone/notes\nrun " + uuid + "\n"
                                   "mail someone" + "@corp-mail.test\nasked an " + "Open" + "AI model\n"
                                   "ok: tsk_" + uuid + ", user@db.example.internal\n")
    labels = [f.split(": ", 1)[1] for f in check_clean.findings(tmp_path)]
    assert labels == ["home path", "session id", "e-mail", "personal or vendor name"]


def test_check_clean_catches_glued_model_names_and_escaped_windows_paths(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import check_clean
    finally:
        sys.path.pop(0)
    lines = ["q" + "wen3-32b", "gp" + "t4o", "Deep" + "SeekV3", "son" + "net", "co" + "dex", "C:" + "\\\\Users" + "\\\\bob"]
    (tmp_path / "b.md").write_text("\n".join(lines) + "\n")
    assert len(check_clean.findings(tmp_path)) == len(lines)


def _check_clean():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import check_clean
    finally:
        sys.path.pop(0)
    return check_clean


def test_common_login_names_are_not_denied(monkeypatch):
    """A machine whose login is an ordinary word (root on a build server) must not flag `#root` or root nodes."""
    check_clean = _check_clean()
    monkeypatch.setattr(check_clean.getpass, "getuser", lambda: "root")
    assert check_clean.findings(ROOT) == []


def test_distinctive_login_names_are_still_denied(monkeypatch, tmp_path):
    check_clean = _check_clean()
    login = "zq" + "vwxlogin"                      # built so this file stays clean itself
    monkeypatch.setattr(check_clean.getpass, "getuser", lambda: login)
    (tmp_path / "a.md").write_text(f"owner: {login}\nthe root node\n")
    assert [f.split(": ", 1)[1] for f in check_clean.findings(tmp_path)] == ["personal or vendor name"]


def test_setup_installs_the_folder_editable():
    """setup.sh must install kb-core editable: a copy in .venv would read config/, domains/ and eval/ from
    site-packages, so edits to config/access_role_map.yaml in the install folder would do nothing and
    `kb-core eval` would find no question sets."""
    lines = [l for l in (ROOT / "setup.sh").read_text().splitlines()
             if l.strip().startswith(("uv pip install", ".venv/bin/python -m pip install"))]
    assert len(lines) == 2 and all("-e ." in l for l in lines), lines
