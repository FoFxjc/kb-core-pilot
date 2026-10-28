"""Fact merge (port of kb pipeline/facts.py; design §3 build).

Observations of one concept, entity and fiscal year are merged by report vintage (fiscal year of the report) from
early to late: a value different from the current version starts a new version (restatement); disagreement within a
vintage is a conflict; two or more documents agreeing -> agreed; one document -> single. The representative
observation prefers the year's own report, then the latest report, then English (doc_id order) and the first table.
"""

import hashlib
from collections import Counter
from decimal import Decimal


def _pick(obs: list[dict]) -> Decimal:
    counts = Counter(o["value"] for o in obs)
    best = max(counts.values())
    return next(o["value"] for o in sorted(obs, key=lambda o: o["doc_id"]) if counts[o["value"]] == best)


def merge(observations: list[dict]) -> list[dict]:
    groups: dict[tuple, list[dict]] = {}
    for o in observations:
        groups.setdefault((o["concept_id"], o["entity_id"], o["fiscal_year"]), []).append(o)
    facts = []
    for (cid, entity, fy), obs in sorted(groups.items()):
        period = obs[0]["period_id"]
        fact_id = hashlib.sha1(f"{cid}|{entity}|{period}".encode()).hexdigest()[:16]
        versions: list[dict] = []
        links: list[dict] = []
        for vintage in sorted({o["report_year"] for o in obs}):
            vo = [o for o in obs if o["report_year"] == vintage]
            value = _pick(vo)
            if not versions or versions[-1]["value"] != value:
                if versions:
                    versions[-1]["known_to"] = vintage
                versions.append({"version_no": len(versions) + 1, "value": value, "known_from": vintage,
                                 "known_to": None, "obs": [], "conflict": False})
            cur = versions[-1]
            cur["obs"] += vo
            cur["conflict"] |= len({o["value"] for o in vo}) > 1
            links += [{"version_no": cur["version_no"], "obs_id": o["obs_id"],
                       "role": "support" if o["value"] == value else "conflict"} for o in vo]
        for v in versions:
            support = [o for o in v["obs"] if o["value"] == v["value"]]
            v["n_sources"] = len({o["doc_id"] for o in support})
            v["status"] = "conflict" if v["conflict"] else "agreed" if v["n_sources"] >= 2 else "single"
            v["winning_obs_id"] = sorted(support, key=lambda o: (o["report_year"] != fy, -o["report_year"],
                                                                 o["doc_id"], o["obs_id"]))[0]["obs_id"]
            del v["obs"], v["conflict"]
        facts.append({"fact_id": fact_id, "concept_id": cid, "entity_id": entity, "fiscal_year": fy,
                      "period_id": period, "unit": obs[0]["unit"], "versions": versions, "links": links,
                      "restated_note": any(o.get("restated_note") for o in obs)})
    return facts
