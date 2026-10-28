"""Check ASSETS.md: every file under profiles/, domains/, config/ and eval/ (except eval/results/) is listed, and each
listed file's sha256 matches (exit 1 otherwise).

  uv run python scripts/check_assets.py [--root PATH] [--update-own]

--update-own adds missing files as kb-core's own (source `kb-core`, commit `-`) and refreshes the sha256 of
kb-core's own rows. Rows copied from kb are never rewritten: changing one is a deliberate edit of its row.
"""

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRS = ("profiles", "domains", "config", "eval")


def table(root: Path) -> dict[str, str]:
    rows = {}
    for line in (root / "ASSETS.md").read_text().splitlines():
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if len(cells) >= 5 and re.fullmatch(r"[0-9a-f]{64}", cells[3]):
            rows[cells[0]] = cells[3]
    return rows


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def update_own(root: Path, files: set[str]) -> None:
    path = root / "ASSETS.md"
    lines = path.read_text().splitlines()
    listed = set(table(root))
    out = []
    for line in lines:
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if len(cells) >= 5 and cells[2] == "-" and re.fullmatch(r"[0-9a-f]{64}", cells[3]) and (root / cells[0]).is_file():
            line = line.replace(cells[3], _sha(root / cells[0]))
        out.append(line)
    for f in sorted(files - listed):
        out.append(f"| `{f}` | `kb-core` | - | {_sha(root / f)} | kb-core's own |")
    path.write_text("\n".join(out) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--update-own", action="store_true")
    args = ap.parse_args(argv)
    root = Path(args.root)
    if args.update_own:
        update_own(root, {str(p.relative_to(root)) for d in DIRS for p in (root / d).rglob("*")
                          if p.is_file() and p.name != ".keep" and "results" not in p.relative_to(root).parts})
    rows = table(root)
    files = {str(p.relative_to(root)) for d in DIRS for p in (root / d).rglob("*")
             if p.is_file() and p.name != ".keep" and "results" not in p.relative_to(root).parts}
    problems = [f"not listed in ASSETS.md: {f}" for f in sorted(files - set(rows))]
    for path, sha in sorted(rows.items()):
        p = root / path
        if not p.is_file():
            problems.append(f"listed but missing: {path}")
        elif _sha(p) != sha:
            problems.append(f"sha256 differs from ASSETS.md: {path}")
    for p in problems:
        print(p)
    print(f"{len(rows)} asset(s) checked" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
