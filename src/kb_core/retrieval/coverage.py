"""Coverage gate (port of kb service/search.py coverage_units / coverage; ranking.yaml rule a).

coverage = IDF-weighted share of the query's information units that a hit contains, IDF over all page bodies:
idf(t) = ln(1 + (N - df + 0.5) / (df + 0.5)). A matched metric (alias unit) counts only when every token of one of
its wordings is present (a metric name is a phrase); a unit none of whose wordings occurs on any page is skipped.
"""

import math
from collections import Counter
from collections.abc import Callable


def idf(df: int, n: int) -> float:
    return math.log(1 + (n - df + 0.5) / (df + 0.5))


def coverage_units(query_terms: list[str], alias_units: list[dict], informative: Callable[[str], bool]) -> list[dict]:
    units, absorbed = [], set()
    for u in alias_units:
        units.append({"kind": u.get("kind", "alias"), "id": u["id"], "typed": u["typed"], "variants": u["variants"]})
        absorbed |= {t for v in u["typed"] for t in v}
    for t in query_terms:
        if informative(t) and t not in absorbed:
            units.append({"kind": "term", "id": t, "typed": [[t]], "variants": [[t]]})
    return units


def coverage(units: list[dict], hay: set[str], page_df: tuple[int, Counter]) -> float:
    n, df = page_df
    num = den = 0.0
    for u in units:
        viable = [v for v in u["variants"] if any(df[t] for t in v)]
        if not viable:
            continue
        weight = {frozenset(v): sum(idf(df[t], n) for t in v) for v in viable}
        typed = [weight[frozenset(v)] for v in u["typed"] if frozenset(v) in weight]
        w = max(typed) if typed else min(weight.values())
        best = 1.0 if any(all(t in hay for t in v) for v in viable) else 0.0
        den += w
        num += w * best
    return round(num / den, 4) if den else 1.0
