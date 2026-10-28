"""Access labels from the overlay `config/access_labels.yaml` (decision D1: simulated until kb-intake carries labels,
contract request CR-2). Document labels at import and build; block labels by node title or page range. Labels only go
up automatically: an overlay entry that would lower an existing label needs `lower: true` and a `reason` (T3.2).
See docs/round-2-w3-access.md sections 1-2."""

import fnmatch
import re
from pathlib import Path

import yaml

from kb_core.access.policy import CLASSIFICATIONS, access_from_label, effective

LABEL_KEYS = ("classification", "domains", "owner", "embargo_until")


class LabelError(ValueError):
    pass


def _check_label(label: dict, where: str, partial: bool) -> dict:
    try:
        access_from_label(label)
    except ValueError as e:
        raise LabelError(f"{where}: {e}") from None
    if not partial and not (label.get("classification") and label.get("owner")):
        raise LabelError(f"{where}: a document label needs classification and owner")
    return label


def load_overlay(source: dict | Path | str | None = None) -> dict:
    """Validate an overlay (a dict, or a YAML path; default config/access_labels.yaml)."""
    if not isinstance(source, dict):
        from kb_core.paths import data_dir

        path = Path(source) if source else data_dir("config") / "access_labels.yaml"
        source = yaml.safe_load(path.read_text()) or {}
    ov = {"version": source.get("version", 1), "simulated": bool(source.get("simulated", True)),
          "default": source.get("default"), "documents": source.get("documents") or [],
          "blocks": source.get("blocks") or []}
    if ov["default"] is not None:
        _check_label(ov["default"], "default", partial=False)
    for i, d in enumerate(ov["documents"]):
        if not d.get("match"):
            raise LabelError(f"documents[{i}]: match is required")
        _check_label(d.get("label") or {}, f"documents[{i}]", partial=True)
        if d.get("lower") and not str(d.get("reason") or "").strip():
            raise LabelError(f"documents[{i}]: lower: true needs a reason")
    for i, b in enumerate(ov["blocks"]):
        if not b.get("doc") or not (b.get("title") or b.get("pages")):
            raise LabelError(f"blocks[{i}]: doc and a title or pages are required")
        if b.get("title"):
            try:
                b["_title"] = re.compile(b["title"], re.I)
            except re.error as e:
                raise LabelError(f"blocks[{i}]: bad title pattern: {e}") from None
        if b.get("pages") and (len(b["pages"]) != 2 or b["pages"][0] > b["pages"][1]):
            raise LabelError(f"blocks[{i}]: pages must be [first, last]")
        _check_label(b.get("label") or {}, f"blocks[{i}]", partial=True)
    return ov


def _rank(c: str) -> int:
    return CLASSIFICATIONS.index(c)


def _full(label: dict, source: str) -> dict:
    return {"classification": label.get("classification"), "domains": list(label.get("domains") or []),
            "owner": label.get("owner"), "embargo_until": label.get("embargo_until"), "label_source": source}


def doc_label(overlay: dict, doc_id: str, intake: dict | None = None, current: dict | None = None) -> dict:
    """The document's label: intake label (CR-2) if any, else the first matching overlay entry over the default.
    It never goes below `current` (the stored label) unless the matching entry says lower: true with a reason."""
    entry = next((d for d in overlay["documents"] if fnmatch.fnmatchcase(doc_id, d["match"])), None)
    if intake:
        label = _full(intake, "intake")
    elif entry:
        label = _full({**(overlay["default"] or {}), **entry["label"]}, "overlay")
    elif overlay["default"]:
        label = _full(overlay["default"], "default")
    else:
        raise LabelError(f"{doc_id}: no label (no intake label, no overlay entry, no default); "
                         "classification and owner are required")
    _check_label({k: label[k] for k in LABEL_KEYS}, doc_id, partial=False)
    if current and _looser(label, current):
        if entry and entry.get("lower"):
            label["lowered_reason"] = entry["reason"]
        else:
            label = _strictest(label, current)
    return label


def _looser(new: dict, cur: dict) -> bool:
    """Whether `new` is less restrictive than `cur` in any dimension: classification, domains, embargo."""
    if _rank(new["classification"]) < _rank(cur["classification"]):
        return True
    nd, cd = set(new.get("domains") or ()), set(cur.get("domains") or ())
    if cd and (not nd or not nd <= cd):
        return True
    ce, ne = cur.get("embargo_until"), new.get("embargo_until")
    return bool(ce) and (not ne or to_access({"classification": "public", "embargo_until": ne}).embargo_until
                         < to_access({"classification": "public", "embargo_until": ce}).embargo_until)


def _strictest(new: dict, cur: dict) -> dict:
    """Without an explicit lowering, each dimension keeps the stricter of the stored and the new value."""
    out = dict(new)
    if _rank(cur["classification"]) > _rank(new["classification"]):
        out["classification"] = cur["classification"]
    nd, cd = set(new.get("domains") or ()), set(cur.get("domains") or ())
    if cd and (not nd or not nd <= cd):
        out["domains"] = list(cur.get("domains") or [])
    ce, ne = cur.get("embargo_until"), new.get("embargo_until")
    if ce and (not ne or to_access({"classification": "public", "embargo_until": ne}).embargo_until
               < to_access({"classification": "public", "embargo_until": ce}).embargo_until):
        out["embargo_until"] = ce
    return out


def block_label(overlay: dict, doc_id: str, title: str, start_page: int, end_page: int) -> dict | None:
    """The overlay label of a block: a node by title, or a node or page lying inside a rule's page range; None when
    no rule applies. The effective label is policy.effective(document, block)."""
    for b in overlay["blocks"]:
        if b["doc"] != doc_id:
            continue
        if b.get("_title") is not None and b["_title"].search(title or ""):
            return dict(b["label"])
        if b.get("pages") and b["pages"][0] <= start_page and end_page <= b["pages"][1]:
            return dict(b["label"])
    return None


def to_access(label: dict):
    """policy.Access from a stored label (extra bookkeeping fields such as lowered_reason are ignored)."""
    return access_from_label({k: label.get(k) for k in LABEL_KEYS if k in label} |
                             ({"label_source": label["label_source"]} if label.get("label_source") else {}))


def to_label(access, source: str) -> dict:
    return {"classification": access.classification, "domains": list(access.domains), "owner": access.owner,
            "embargo_until": access.embargo_until.isoformat() if access.embargo_until else None,
            "label_source": source}


def _combine(base: dict, block: dict | None) -> dict:
    if block is None:
        return base
    return to_label(effective(to_access(base), access_from_label(block)), "overlay")


def node_labels(overlay: dict, doc_id: str, doc: dict, nodes: list[dict]) -> dict[str, dict]:
    """Effective label of every node, top-down: its parent's effective label (the document's for a top node)
    combined with the node's own block rule. `nodes` in pre-order with node_id, parent_id, title, start_page,
    end_page."""
    out: dict[str, dict] = {}
    for n in nodes:
        base = out.get(n["parent_id"]) if n.get("parent_id") else doc
        out[n["node_id"]] = _combine(base or doc, block_label(overlay, doc_id, n["title"], n["start_page"],
                                                                n["end_page"]))
    return out


def page_access(overlay: dict, doc_id: str, doc: dict, page_no: int, covering: list[dict]) -> dict:
    """Effective label of a page: the document label combined with every covering node's label and any page-range
    rule containing the page (the strictest wins)."""
    label = _combine(doc, block_label(overlay, doc_id, "", page_no, page_no))
    for c in covering:
        label = to_label(effective(to_access(label), to_access(c)), "overlay")
    return label
