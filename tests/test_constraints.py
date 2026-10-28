import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_constraints_match_lock():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_constraints.py")], cwd=ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_constraints_pin_runtime_deps():
    text = (ROOT / "constraints.txt").read_text()
    for pin in ["fastapi==0.143.2", "httpx==0.28.1", "jieba==0.42.1", "psycopg==3.3.6"]:
        assert pin in text
