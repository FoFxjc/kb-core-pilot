"""Type profiles (design §6): per doc_type rules for tree building, sections and observations.

Rules live in profiles/<doc_type>/*.yaml; the code that applies them lives in kb_core.build. An unknown doc_type
uses the generic profile (regions and fonts only).
"""

from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import yaml

from kb_core.paths import data_dir

PROFILES = data_dir("profiles")


@dataclass(frozen=True)
class Profile:
    doc_type: str
    tree_rules: dict
    sections: dict = field(default_factory=dict)
    files: tuple[Path, ...] = ()

    def build_tree(self, view, notes: list | None = None):
        from kb_core.build.tree import build_annual_report_tree, build_generic_tree

        if "toc" in self.tree_rules:
            return build_annual_report_tree(view, self.tree_rules, notes)
        return build_generic_tree(view, self.tree_rules, notes)


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) if path.exists() else {}


@cache
def get(doc_type: str) -> Profile:
    d = PROFILES / doc_type
    if not (d / "tree.yaml").exists():
        d = PROFILES / "generic"
    files = tuple(sorted(p for p in d.glob("*.yaml")))
    return Profile(doc_type=d.name, tree_rules=_load(d / "tree.yaml"), sections=_load(d / "sections.yaml"),
                   files=files)


def registered() -> list[str]:
    """doc_types with their own profile folder (generic excluded)."""
    return sorted(p.name for p in PROFILES.iterdir() if p.is_dir() and p.name != "generic" and (p / "tree.yaml").exists())


def section_types() -> dict:
    """Section type vocabulary of all registered profiles, merged in registration order."""
    out: dict = {}
    for t in registered():
        for k, v in (get(t).sections.get("section_types") or {}).items():
            out.setdefault(k, v)
    return out


def queried_sections(query: str) -> list[str]:
    """Section types a query names through their query_patterns (section_missing_in_lang gap)."""
    q = query.lower()
    return [t for t, spec in section_types().items() if any(p.lower() in q for p in spec.get("query_patterns") or [])]
