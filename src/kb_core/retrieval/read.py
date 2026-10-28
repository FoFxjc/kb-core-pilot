"""read: read the source text (port of kb service/read.py; api-contract §5.3). Pages, tables and (on request) page
images; images are rendered on demand from the package's source.pdf and cached under store/cache/pages/."""

import base64

from kb_core.access import scope as access_scope
from kb_core.retrieval import context
from kb_core.retrieval.core import ApiError, boolean, integer, reject_unknown
from kb_core.retrieval.tracing import traced

PARAMS = {"node_id", "doc_id", "page_range", "include_tables", "include_images", "max_chars"}
MAX_PAGES = 5
IMAGE_LONG_EDGE = 1280


def _page_range(params: dict, page_count: int) -> list[int]:
    pr = params.get("page_range")
    if isinstance(pr, str):
        pr = [x for x in pr.replace("–", "-").replace(",", "-").split("-") if x]
    if not isinstance(pr, list) or len(pr) != 2:
        raise ApiError("INVALID_PARAM", "page_range must be [start, end]", param="page_range", allowed="[int, int]")
    try:
        s, e = int(pr[0]), int(pr[1])
    except (TypeError, ValueError):
        raise ApiError("INVALID_PARAM", "page_range must be integers", param="page_range", allowed="[int, int]") from None
    if not 1 <= s <= e <= page_count:
        raise ApiError("INVALID_PARAM", f"page_range must satisfy 1 <= start <= end <= {page_count}",
                       param="page_range", allowed=[1, page_count])
    if e - s + 1 > MAX_PAGES:
        raise ApiError("INVALID_PARAM", f"page_range spans {e - s + 1} pages; at most {MAX_PAGES}",
                       param="page_range", allowed=f"<= {MAX_PAGES} pages")
    return [s, e]


def render_image(doc_id: str, page_no: int):
    """Page PNG (long edge 1,280 px) from the stored source.pdf, cached; returns the path."""
    import fitz

    ctx = context.current()
    store = ctx.settings.store_dir
    path = store / "cache" / "pages" / doc_id / f"{page_no:04d}.png"
    if not path.exists():
        package = ctx.pg_rows("R3_document_package", {"doc_id": doc_id})[0]["package"]
        path.parent.mkdir(parents=True, exist_ok=True)
        with fitz.open(store / "packages" / package / "source.pdf") as pdf:
            page = pdf[page_no - 1]
            zoom = IMAGE_LONG_EDGE / max(page.rect.width, page.rect.height)
            page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).save(path)
    return path


def _image(doc_id: str, page_no: int) -> dict:
    import fitz

    path = render_image(doc_id, page_no)
    pix = fitz.Pixmap(str(path))
    return {"mime": "image/png", "width": pix.width, "height": pix.height,
            "url": f"/v1/docs/{doc_id}/pages/{page_no}.png", "data_base64": base64.b64encode(path.read_bytes()).decode()}


def run_read(params: dict):
    cat = context.current().catalog
    reject_unknown(params, PARAMS)
    node_id, doc_id = params.get("node_id"), params.get("doc_id")
    include_tables = boolean(params, "include_tables", True)
    include_images = boolean(params, "include_images", False)
    max_chars = integer(params, "max_chars", 40000, 5000, 60000)
    if bool(node_id) == bool(doc_id or params.get("page_range")):
        raise ApiError("INVALID_PARAM", "give either node_id, or doc_id + page_range", param="node_id",
                       allowed=["node_id", "doc_id+page_range"])
    gaps, next_ = [], None
    if node_id:
        doc_id = node_id.split(":")[0]
        # a node the subject may not see is reported exactly like one that does not exist (T3.6)
        if doc_id not in cat.visible_docs() or node_id not in cat.primary(doc_id).nodes \
                or not access_scope.visible(cat.primary(doc_id).nodes[node_id].get("access")):
            raise ApiError("UNKNOWN_NODE", f"unknown node_id: {node_id!r}")
        node = cat.primary(doc_id).nodes[node_id]
        start, end = node["start_page"], node["end_page"]
        if end - start + 1 > MAX_PAGES:
            next_ = {"doc_id": doc_id, "page_range": [start + MAX_PAGES, end]}
            end = start + MAX_PAGES - 1
            gaps.append({"code": "truncated", "detail": f"the node has {node['end_page'] - start + 1} pages; only the "
                         f"first {MAX_PAGES} are returned"})
        full_end = node["end_page"]
    else:
        if doc_id not in cat.visible_docs():
            raise ApiError("UNKNOWN_DOC", f"unknown doc_id: {doc_id!r}", candidates=sorted(cat.visible_docs()))
        start, end = _page_range(params, cat.docs[doc_id]["page_count"])
        full_end = end
    ctx, log = context.current(), {}
    # every page and table is re-checked before it is returned; hidden ones are left out without a trace (T3.6)
    all_pages = ctx.pg_rows("R1_pages_range", {"doc_id": doc_id, "start": start, "end": end}, log=log)
    pages = [p for p in all_pages if access_scope.visible(p.get("access"))]
    access_scope.note_filtered(len(all_pages) - len(pages))
    tree = cat.primary(doc_id)
    tables: dict[int, list] = {}
    if include_tables:
        for t in ctx.pg_rows("R2_tables_range", {"doc_id": doc_id, "start": start, "end": end}, log=log):
            if not access_scope.visible(t.get("access")):
                access_scope.note_filtered(1)
                continue
            tables.setdefault(int(t["page_start"]), []).append({"table_id": t["table_id"], "markdown": t["markdown"]})
    results, used, images = [], 0, []
    for p in pages:
        page_no = int(p["page_no"])
        text = p["text"] or ""
        cost = len(text) + sum(len(t["markdown"] or "") for t in tables.get(page_no, []))
        if results and used + cost > max_chars:
            next_ = {"doc_id": doc_id, "page_range": [page_no, full_end]}
            gaps.append({"code": "truncated", "detail": f"text exceeds max_chars={max_chars}; pages from {page_no} on "
                         "are not returned"})
            break
        clipped = False
        if not results and cost > max_chars:
            text, clipped = text[:max_chars], True
        entry = {"tier": "text", "page_no": page_no, "page_label": p["page_label"],
                 "page_label_source": p["page_label_source"], "text": text,
                 "tables": [] if clipped else tables.get(page_no, []), "nodes_covering": [n for n in p["covering_node_ids"] or []
                                    if n in tree.nodes and access_scope.visible(tree.nodes[n].get("access"))]}
        if include_images:
            entry["image"] = _image(doc_id, page_no)
            images.append((entry["image"]["width"], entry["image"]["height"]))
        results.append(entry)
        used += cost
        if clipped:
            if page_no < full_end:
                next_ = {"doc_id": doc_id, "page_range": [page_no + 1, full_end]}
            gaps.append({"code": "truncated", "detail": f"text of page {page_no} exceeds max_chars={max_chars} and was "
                         "truncated"})
            break
    if next_ and next_["page_range"][1] - next_["page_range"][0] + 1 > MAX_PAGES:
        next_["remaining_page_range"] = [next_["page_range"][0], full_end]
        next_["page_range"] = [next_["page_range"][0], next_["page_range"][0] + MAX_PAGES - 1]
    if cat.docs[doc_id]["page_label_source"] == "none":
        gaps.append({"code": "page_label_unreliable", "doc_id": doc_id,
                     "detail": "this document has no usable printed page numbers"})
    labels = [results[0]["page_label"], results[-1]["page_label"]] if results else None
    returned = [results[0]["page_no"], results[-1]["page_no"]] if results else None
    scope = {"filters_applied": {"node_id": node_id, "doc_id": doc_id, "page_range": [start, end],
                                 "include_tables": include_tables, "include_images": include_images,
                                 "max_chars": max_chars},
             "filters_ignored": [], "doc_count": 1, "docs": [cat.doc_summary(doc_id)],
             "available_periods": cat.available_periods(),
             "source": cat.source(doc_id, page_range=returned, page_labels=labels)}
    truncated = bool(next_) or any(g["code"] == "truncated" for g in gaps)
    return results, scope, gaps, truncated, {"queries": log}, next_


def read(params: dict, source: str = "http", session_id: str | None = None,
         subject: str | None = None) -> dict:
    return traced("read", params, run_read, source=source, session_id=session_id, subject=subject)
