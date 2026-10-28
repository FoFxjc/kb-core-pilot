# Tree spot-check rubric (kb D22, fixed by the project owner on 2026-10-26)

Sample 40 primary-tree nodes per document with a fixed, previously unused seed (`kb-core eval tree --doc ... --seed N`).
A node is **correct** only if title, pages and parent are all correct:

1. **Title** — a real heading or section title that appears on its start page as written (line wraps and a removed
   "(continued)" are fine). Wrong: body text, a sentence, a table row label or column header, a chart label, a caption,
   a stat-callout fragment, a field label (e.g. a job-title line under a name), or text merged from two headings.
   *kb's rule accepted:* a contents **group** title (origin `toc_group`) may be printed only on the contents page.
2. **Pages** — the start page is where the section starts and the end page is the last page of its content (the page
   before the next heading at the same or a higher level, or that page when the section's text continues onto it).
   Off by one page is wrong. *kb's rule accepted:* a section may start on divider or sub-contents pages that
   immediately precede its first heading.
3. **Parent** — the nearest real enclosing heading. A node that skips a real intermediate heading (e.g. committee
   bullets placed under "Principle 1" instead of under "Board Committees") is wrong. Top-level nodes are judged on
   title and pages only.

Judges read only the source PDF and the sheet. The main session re-judges at least 10 items per sheet.
