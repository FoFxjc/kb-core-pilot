"""Build a small, valid contract v2 delivery package for tests (3 pages, a tiny generated PDF).

build_package(dest, **overrides) writes <dest>/<doc_id>@<sha12>/ and returns its path. `mutate(files)` may edit the
row lists / manifest before hashes are computed; `after(pkg)` may tamper with written files.
"""

import hashlib
import json
from pathlib import Path

import fitz

DOC = "acme_ar_2025_en"


def _pdf(lines_per_page: list[list[str]]) -> bytes:
    doc = fitz.open()
    for lines in lines_per_page:
        page = doc.new_page(width=595, height=842)
        y = 72
        for line in lines:
            page.insert_text((72, y), line, fontsize=11)
            y += 18
    data = doc.tobytes(garbage=4, deflate=True, no_new_id=True)
    doc.close()
    return data


def _region(doc_id, page, n, type_, text, bbox, order, font=None, status="extracted", table_id=None, layer="body"):
    return {"region_id": f"{doc_id}:p{page:04d}:r{n:03d}", "page_no": page, "bbox": bbox, "type": type_,
            "subtype": None, "score": 0.9, "label_source": "model", "layer": layer, "reading_order": order,
            "text": text, "text_source": "native" if text is not None else None, "font": font, "status": status,
            "handler": "table_structure" if type_ == "table" else "text", "table_id": table_id, "absorbed_into": None}


def _cell(r, c, text, header=False, x0=72.0):
    return {"r": r, "c": c, "rs": 1, "cs": 1, "text": text, "bbox": [x0 + 150 * c, 300 + 14 * r, x0 + 150 * c + 60, 310 + 14 * r],
            "bbox_source": "text", "is_header": header}


def build_package(dest: Path, doc_id: str = DOC, lang: str = "en", period_end: str = "2025-12-31",
                  issuer_id: str = "acme", doc_type: str = "annual_report", state: str = "confirmed",
                  contract_version: str = "2", cover: str = "Acme Annual Report 2025", mutate=None,
                  after=None) -> Path:
    page_lines = [[cover, "Contents", "Overview 2", "Financial Statements 3"],
                  ["Overview", "Net profit rose to $1,234m.", "Key figures"],
                  ["Financial Statements", "Key figures (continued)"]]
    pdf = _pdf(page_lines)
    sha = hashlib.sha256(pdf).hexdigest()
    big = {"name": "Helvetica-Bold", "size": 20.0, "bold": True}
    mid = {"name": "Helvetica-Bold", "size": 14.0, "bold": True}
    body = {"name": "Helvetica", "size": 10.0, "bold": False}
    t1, t2 = f"{doc_id}:t0002_01", f"{doc_id}:t0003_01"
    regions = [
        _region(doc_id, 1, 1, "title", "Acme Annual Report 2025", [72, 60, 400, 80], 0, big),
        _region(doc_id, 1, 2, "toc", "Contents\nOverview 2\nFinancial Statements 3", [72, 90, 400, 150], 1, body),
        _region(doc_id, 2, 1, "heading", "Overview", [72, 60, 300, 76], 0, mid),
        _region(doc_id, 2, 2, "text", "Net profit rose to $1,234m.", [72, 80, 400, 96], 1, body),
        _region(doc_id, 2, 3, "table", None, [72, 290, 500, 340], 2, None, table_id=t1),
        _region(doc_id, 2, 4, "page_footer", "2", [290, 800, 300, 812], 3, body, status="discarded", layer="furniture"),
        _region(doc_id, 3, 1, "heading", "Financial Statements", [72, 60, 300, 76], 0, mid),
        _region(doc_id, 3, 2, "table", None, [72, 290, 500, 340], 1, None, table_id=t2),
    ]
    tables = [
        {"table_id": t1, "region_id": f"{doc_id}:p0002:r003", "page_no": 2, "bbox": [72, 290, 500, 340],
         "n_rows": 3, "n_cols": 3, "cells": [_cell(0, 1, "2025", True), _cell(0, 2, "2024", True),
                                             _cell(1, 0, "Selected Income Statement Items ($ million)"),
                                             _cell(2, 0, "Net profit"), _cell(2, 1, "1,234"), _cell(2, 2, "(5)")],
         "markdown": "| | 2025 | 2024 |\n|---|---|---|\n| Selected Income Statement Items ($ million) | | |\n"
                     "| Net profit | 1,234 | (5) |", "extract_method": "docling",
         "checks": {"unassigned_words": 0}, "continued_hint": None},
        {"table_id": t2, "region_id": f"{doc_id}:p0003:r002", "page_no": 3, "bbox": [72, 290, 500, 340],
         "n_rows": 1, "n_cols": 3, "cells": [_cell(0, 0, "Total income"), _cell(0, 1, "2,000"), _cell(0, 2, "-")],
         "markdown": "| Total income | 2,000 | - |", "extract_method": "docling", "checks": {"unassigned_words": 0},
         "continued_hint": {"table_id": t1, "reason": "continued_heading"}},
    ]
    pages = [{"page_no": i + 1, "page_label": str(i + 1), "width": 595.0, "height": 842.0, "kind": "native",
              "text": "\n".join(lines), "text_source": "native", "excluded": False} for i, lines in enumerate(page_lines)]
    layout = [{"page_no": i + 1, "words": [[72.0, 60.0 + 18 * j, 200.0, 72.0 + 18 * j, w]
                                           for j, w in enumerate(" ".join(lines).split()[:5])]}
              for i, lines in enumerate(page_lines)]
    gaps = [{"code": "low_confidence", "page_no": 2, "detail": "region score below 0.5",
             "region_id": f"{doc_id}:p0002:r002"}]
    workflow = {"workflow": {"name": "default", "version": 1, "handlers": {
        t: ("table_structure" if t == "table" else "discard" if t in ("picture", "logo", "icon", "page_header",
            "page_footer") else "record" if t in ("signature", "stamp") else "unhandled" if t == "unknown" else "text")
        for t in ["title", "heading", "text", "list", "caption", "footnote", "formula", "toc", "table", "chart",
                  "diagram", "picture", "logo", "icon", "signature", "stamp", "page_header", "page_footer", "unknown"]},
        "exclude_pages": []}, "approved_by": "tester", "approved_at": "2026-10-26T00:00:00+00:00"}
    review = [{"action": "confirm", "region_id": None, "from": None, "to": None, "by": "tester",
               "at": "2026-10-26T00:00:01+00:00", "note": None}]
    files = {"pages.jsonl": pages, "regions.jsonl": regions, "tables.jsonl": tables, "layout.jsonl": layout,
             "gaps.jsonl": gaps, "review.jsonl": review, "workflow.json": workflow}
    manifest = {
        "contract_version": contract_version, "package": f"{doc_id}@{sha[:12]}", "doc_id": doc_id,
        "source": {"filename": f"{doc_id}.pdf", "sha256": sha, "bytes": len(pdf), "media_type": "application/pdf"},
        "metadata": {"declaration": {"doc_id": doc_id, "issuer_id": issuer_id, "doc_type": doc_type,
                                     "period_end": period_end, "lang": lang, "source_url": "https://example.com/ar",
                                     "completeness": {"full": True, "sections": None}},
                     "declaration_filled": [], "page_count": 3, "lang": lang, "detected_lang": lang,
                     "page_kinds": {"native": 3}, "has_text_layer": True,
                     "page_label_method": {"method": "pdf_labels"}},
        "stats": {"labeled_by_type": {}, "regions_by_type": {}, "regions_by_status": {}, "tables": 2,
                  "gaps_by_code": {"low_confidence": 1}},
        "engines": {"docling": {}, "models": [], "pymupdf": "1.28.2", "device": "cpu", "params": {}, "stages": {}},
        "workflow": {"name": "default", "version": 1, "approved_by": "tester", "approved_at": "2026-10-26T00:00:00+00:00"},
        "status": {"state": state, "confirmed_by": "tester", "confirmed_at": "2026-10-26T00:00:01+00:00"},
        "files": {}, "kb_intake_version": "0.3.1", "run": {},
    }
    files["manifest.json"] = manifest
    if mutate:
        mutate(files)
    pkg = dest / f"{doc_id}@{sha[:12]}"
    pkg.mkdir(parents=True)
    (pkg / "source.pdf").write_bytes(pdf)
    for name, content in files.items():
        if name == "manifest.json":
            continue
        if name.endswith(".jsonl"):
            data = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in content)
        else:
            data = json.dumps(content, ensure_ascii=False, indent=1)
        (pkg / name).write_text(data)
        b = (pkg / name).read_bytes()
        manifest["files"][name] = {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b),
                                   "rows": len(content) if name.endswith(".jsonl") else None}
    (pkg / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    if after:
        after(pkg)
    return pkg
