"""A document as the build stage sees it: the package's pages, regions and layout words."""

from collections.abc import Callable
from dataclasses import dataclass

from kb_core.intake.package import Package


@dataclass
class DocView:
    doc_id: str
    doc_type: str
    lang: str | None
    pages: list[dict]
    regions: list[dict]
    words: Callable[[int], list[list]]

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def page(self, page_no: int) -> dict:
        p = self.pages[page_no - 1] if 0 < page_no <= len(self.pages) else None
        if p is None or p["page_no"] != page_no:
            p = next(x for x in self.pages if x["page_no"] == page_no)
        return p

    @classmethod
    def from_package(cls, pkg: Package) -> "DocView":
        d = pkg.declaration
        regions = sorted(pkg.regions(), key=lambda r: (r["page_no"], r["reading_order"]))
        return cls(doc_id=pkg.doc_id, doc_type=d["doc_type"], lang=d.get("lang") or pkg.manifest["metadata"]["lang"],
                   pages=sorted(pkg.pages(), key=lambda p: p["page_no"]), regions=regions, words=pkg.words)
