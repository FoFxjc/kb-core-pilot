"""Small builders for tree tests: pages and regions as kb-intake delivers them."""

from kb_core.build.view import DocView

DOC = "t_ar_2025_en"


def page(n, label=None, text="x" * 200, width=595.0):
    return {"page_no": n, "page_label": label if label is not None else str(n), "width": width, "height": 842.0,
            "kind": "native", "text": text, "text_source": "native", "excluded": False}


def region(page_no, order, text, type_="heading", size=13.0, bold=True, x=51.0, y=100.0, w=200.0, h=10.0,
           color=None, layer="body"):
    font = {"name": "F", "size": size, "bold": bold}
    if color is not None:
        font["color"] = color
    return {"region_id": f"{DOC}:p{page_no:04d}:r{order:03d}", "page_no": page_no, "bbox": [x, y, x + w, y + h],
            "type": type_, "layer": layer, "reading_order": order, "text": text, "font": font,
            "status": "extracted", "table_id": None}


def view(pages, regions, words=None, doc_type="annual_report", lang="en"):
    words = words or {}
    regions = sorted(regions, key=lambda r: (r["page_no"], r["reading_order"]))   # as DocView.from_package does
    return DocView(doc_id=DOC, doc_type=doc_type, lang=lang, pages=pages, regions=regions,
                   words=lambda p: words.get(p, []))
