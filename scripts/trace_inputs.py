"""Run kb-core commands under an audit hook and list the files they open, the sockets they connect to and the
subprocesses they start.

Round 2 T0.1 blind check: shows which inputs kb-core reads (repository assets, delivery packages, the store)
and that nothing under kb or kb-intake is opened. Blind spots: Python's audit hook does not see opens made inside C
libraries (libpq, PyMuPDF) or by subprocesses (only their command lines are recorded). Usage:

    uv run python scripts/trace_inputs.py --out trace.json --forbid /path/to/kb --forbid /path/to/kb-intake \
        -- build --all -- facts -- reindex

Each `--`-separated group is one `kb-core` command, run in this process. Exit code 1 when any path is FORBIDDEN or
`other`, or when a command fails. `--forbid` names the roots nothing may be read from (the kb reference repository
and the kb-intake repository); it is required. The report names every path relative to its root (`<repo>/...`,
`<store>/...`, `<delivery>/...`, `<forbidden:NAME>/...`), so it carries no machine-specific locations.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SYSTEM = (Path("/dev"), Path("/etc"), Path("/usr"), Path("/System"), Path("/Library"), Path("/private/etc"),
          Path("/private/var"), Path("/var"), Path("/tmp"), Path("/private/tmp"), Path("/opt/homebrew"))


@dataclass(frozen=True)
class Roots:
    repo: Path
    delivery: Path | None
    store: Path
    python: tuple[Path, ...]
    forbidden: tuple[Path, ...]


def _under(p: Path, root: Path) -> bool:
    return p == root or root in p.parents


def classify(p: Path, roots: Roots) -> str:
    if any(_under(p, r) for r in roots.forbidden):
        return "FORBIDDEN"
    if any(_under(p, r) for r in roots.python):
        return "python"
    if roots.delivery and _under(p, roots.delivery):
        return "delivery"
    if _under(p, roots.store):
        return "store"
    if _under(p, roots.repo):
        rel = p.relative_to(roots.repo).parts
        return f"repo:{rel[0]}" if len(rel) > 1 else "repo:."
    if any(_under(p, r) for r in SYSTEM):
        return "system"
    return "other"


def display(p: Path, roots: Roots) -> str:
    """A path relative to the root it belongs to; system paths as they are; anything else relative to home."""
    for label, root in (("delivery", roots.delivery), ("store", roots.store)):
        if root is not None and _under(p, root):
            return f"<{label}>/{p.relative_to(root)}"
    for r in roots.forbidden:
        if _under(p, r):
            return f"<forbidden:{r.name}>/{p.relative_to(r)}"
    for r in roots.python:
        if _under(p, r):
            return f"<python>/{p.relative_to(r)}"
    if _under(p, roots.repo):
        return f"<repo>/{p.relative_to(roots.repo)}"
    tmp = Path(tempfile.gettempdir()).resolve()          # per-user temp folder (machine-specific name)
    if _under(p, tmp):
        return f"<tmp>/{p.relative_to(tmp)}"
    if any(_under(p, r) for r in SYSTEM):
        return str(p)
    home = Path.home()
    return f"<home>/{p.relative_to(home)}" if _under(p, home) else str(p)


def is_write(mode: str) -> bool:
    return any(c in mode for c in "wax+")


def _roots(forbidden: list[str]) -> Roots:
    from kb_core.config import load_settings

    s = load_settings()
    home_cache = Path.home() / ".cache" / "uv"  # uv's interpreter and wheel cache
    python = {Path(sys.prefix), Path(sys.base_prefix), Path(sys.exec_prefix), home_cache,
              Path.home() / ".local" / "share" / "uv"}
    return Roots(
        repo=REPO,
        delivery=s.delivery_dir.expanduser().resolve() if s.delivery_dir else None,
        store=s.store_dir.expanduser().resolve(),
        python=tuple(sorted({p.resolve() for p in python})),
        forbidden=tuple(Path(f).expanduser().resolve() for f in forbidden),
    )


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    head = argv.index("--") if "--" in argv else len(argv)
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, help="JSON report path")
    ap.add_argument("--forbid", action="append", required=True,
                    help="a root nothing may be read from (repeatable): the kb and kb-intake repositories")
    args = ap.parse_args(argv[:head])
    commands, cur = [], []
    for a in argv[head + 1:]:
        if a == "--":
            commands.append(cur)
            cur = []
        else:
            cur.append(a)
    if cur:
        commands.append(cur)

    opened: dict[str, set[str]] = defaultdict(set)  # path -> modes
    sockets: Counter = Counter()
    subprocesses: list[list[str]] = []

    def hook(event: str, a: tuple) -> None:
        if event == "open" and isinstance(a[0], (str, bytes)) and a[0] not in ("", b""):
            path = a[0].decode() if isinstance(a[0], bytes) else a[0]
            mode = a[1] if isinstance(a[1], str) else ("w" if isinstance(a[2], int) and a[2] & 0o3 else "r")
            opened[str(Path(path).expanduser().resolve())].add(mode or "r")
        elif event == "socket.connect":
            addr = a[1]
            if isinstance(addr, tuple) and len(addr) >= 2:
                sockets[f"{addr[0]}:{addr[1]}"] += 1
        elif event == "subprocess.Popen":
            subprocesses.append([str(x) for x in (a[1] or [a[0]])])

    # installed before settings are read or kb_core is imported, so those reads are traced too
    sys.addaudithook(hook)
    roots = _roots(args.forbid)
    from kb_core.cli import main as kb_main

    results = []
    for cmd in commands:
        try:
            code = kb_main(cmd)
        except SystemExit as e:  # argparse exits
            code = e.code if isinstance(e.code, int) else 1
        results.append({"command": cmd, "exit": code})

    by_class: dict[str, list[str]] = defaultdict(list)
    for path in sorted(opened):
        by_class[classify(Path(path), roots)].append(display(Path(path), roots))
    summary = {
        "commands": results,
        "roots": {"repo": "<repo>", "delivery": "<delivery>" if roots.delivery else None, "store": "<store>",
                  "python": f"{len(roots.python)} interpreter and package roots (<python>)",
                  "forbidden": [f"<forbidden:{r.name}>" for r in roots.forbidden]},
        "counts": {k: len(v) for k, v in sorted(by_class.items())},
        "sockets": dict(sockets),
        "subprocesses": subprocesses,
        "written": sorted(display(Path(p), roots) for p, modes in opened.items() if any(is_write(m) for m in modes)),
        "paths": {k: v for k, v in sorted(by_class.items()) if k != "python"},
    }
    text = json.dumps(summary, indent=2, ensure_ascii=False)
    Path(args.out).write_text(text + "\n")
    print(json.dumps({k: summary[k] for k in ("commands", "counts", "sockets", "subprocesses")}, indent=2))
    bad = by_class.get("FORBIDDEN", []) + by_class.get("other", [])
    failed = any(r["exit"] not in (0, None) for r in results)
    return 1 if bad or failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
