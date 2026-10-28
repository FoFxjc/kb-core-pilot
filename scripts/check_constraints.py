"""Check that constraints.txt is exactly what `uv export` produces from uv.lock (exit 1 on drift).

Regenerate with:  uv export --no-hashes --no-dev --no-emit-project -o constraints.txt
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CMD = ["uv", "export", "--frozen", "--no-hashes", "--no-dev", "--no-emit-project", "--no-header"]


def _body(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def main() -> int:
    r = subprocess.run(CMD, cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        return 1
    current = (ROOT / "constraints.txt").read_text()
    if _body(r.stdout) != _body(current):
        print("constraints.txt is out of date with uv.lock; regenerate it:\n  " + " ".join(CMD) + " -o constraints.txt")
        return 1
    print("constraints.txt matches uv.lock")
    return 0


if __name__ == "__main__":
    sys.exit(main())
