"""Where kb-core's data folders are: the repository root in a source checkout, or kb_core/_data in an installed wheel
(pyproject force-include)."""

from pathlib import Path

_PKG = Path(__file__).resolve().parent
_REPO = _PKG.parents[1]


def data_dir(name: str) -> Path:
    """contract, migrations, queries, es, profiles, domains, config, eval."""
    src = _REPO / name
    return src if src.exists() else _PKG / "_data" / name
