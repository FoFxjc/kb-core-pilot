"""Check that contract/intake-v2/ is a copy of kb-intake's contract/v2/ (exit 1 on any difference).

  KB_CORE_INTAKE_REPO=/path/to/kb-intake uv run python scripts/check_contract.py   (or --intake-repo PATH)

The copies are identical to upstream except the top-level "$id", which is a neutral URN here: the files are
compared as JSON with that one key removed, so any other change (a field, a type, an enum value) is a difference.

Also reports kb-intake's current HEAD next to the commit recorded in contract/intake-v2/SOURCE.md, so a newer
upstream with an unchanged contract is visible but not an error.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPY = ROOT / "contract" / "intake-v2"


def _body(path: Path) -> dict:
    """The schema without its top-level $id (the only key the copy rewrites)."""
    doc = json.loads(path.read_text())
    doc.pop("$id", None)
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--intake-repo", default=os.environ.get("KB_CORE_INTAKE_REPO"),
                    help="a checkout of the kb-intake repository (or KB_CORE_INTAKE_REPO); required")
    args = ap.parse_args(argv)
    if not args.intake_repo:
        print("give the kb-intake repository: --intake-repo PATH or KB_CORE_INTAKE_REPO")
        return 2
    upstream = Path(args.intake_repo) / "contract" / "v2"
    if not upstream.is_dir():
        print(f"no kb-intake contract at {upstream}")
        return 1
    ours = {p.name for p in COPY.glob("*.schema.json")}
    theirs = {p.name for p in upstream.glob("*.schema.json")}
    problems = [f"missing here: {n}" for n in sorted(theirs - ours)]
    problems += [f"not upstream: {n}" for n in sorted(ours - theirs)]
    problems += [f"differs: {n}" for n in sorted(ours & theirs) if _body(COPY / n) != _body(upstream / n)]
    recorded = re.search(r"commit[^0-9a-f]*([0-9a-f]{7,40})", (COPY / "SOURCE.md").read_text())
    head = subprocess.run(["git", "-C", str(upstream), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print(f"recorded source commit {recorded.group(1)[:12] if recorded else '?'}; kb-intake HEAD {head[:12] or '?'}")
    for p in problems:
        print(p)
    print("contract copy matches kb-intake" if not problems else f"{len(problems)} difference(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
