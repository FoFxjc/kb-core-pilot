"""Domain packs (design §6): domains/<name>/ holds concepts, facts, units, low-information terms and the jieba
dictionary. kb-core selects one with KB_CORE_DOMAIN."""

import re
from functools import cache
from pathlib import Path

import yaml

from kb_core.paths import data_dir

DOMAINS = data_dir("domains")


def domain_dir(name: str) -> Path:
    d = DOMAINS / name
    if not d.is_dir():
        raise ValueError(f"no domain pack {name!r} in {DOMAINS}")
    return d


def dictionary(name: str) -> Path:
    return domain_dir(name) / "finance_zh.txt"


@cache
def low_info(name: str) -> tuple[int, frozenset, re.Pattern]:
    """Low-information terms of a domain pack (low_info_terms.yaml): (version, terms, year pattern)."""
    spec = yaml.load((domain_dir(name) / "low_info_terms.yaml").read_text(), Loader=yaml.BaseLoader)
    terms = frozenset(t.lower() for lang in spec["terms"].values() for t in lang)
    return int(spec["version"]), terms, re.compile(spec["year_pattern"])


def informative(term: str, name: str) -> bool:
    _, terms, year = low_info(name)
    return term not in terms and not year.match(term)


HELD_OUT_FILES = ("heldout_terms.yaml", "round2_heldout.yaml")   # the legacy and old-16 list; the sealed round 2 set


def held_out_wordings() -> frozenset[str]:
    """Every held-out wording (lowercased): no concept spelling may equal or recognise one, and no query synonym may
    equal one
    (round 2 T2.4). Reading the sealed set's wordings for this guard is not tuning on it."""
    out = set()
    for name in HELD_OUT_FILES:
        path = data_dir("eval") / name
        if not path.exists():
            continue
        spec = yaml.safe_load(path.read_text()) or {}
        out |= {str(t["term"]).lower() for t in spec.get("terms") or ()}
        out |= {str(q["heldout_term"]).lower() for q in spec.get("questions") or () if q.get("heldout_term")}
    return frozenset(out)


def check_synonyms(synonyms: dict[str, list[str]], held_out: frozenset[str] | set[str] | None = None) -> None:
    """A query synonym (a word or its replacement) must not be a held-out wording."""
    held_out = held_out_wordings() if held_out is None else held_out
    for word, subs in synonyms.items():
        for w in (word, *subs):
            if str(w).lower() in held_out:
                raise ValueError(f"query synonym {w!r} is a held-out wording")


@cache
def query_synonyms(name: str) -> dict[str, tuple[str, ...]]:
    """Word-level query synonyms of a domain pack (domain.yaml `query_synonyms`, round 2 W2 class F1): a query word
    adds the report's words for it. Checked against the held-out wordings."""
    spec = yaml.safe_load((domain_dir(name) / "domain.yaml").read_text()) or {}
    syn = {str(k).lower(): tuple(str(x).lower() for x in v) for k, v in (spec.get("query_synonyms") or {}).items()}
    check_synonyms(syn)
    return syn
