-- Size (PDF points) and printed label of one page (document view: region boxes are in PDF coordinates).
SELECT page_no, page_label, page_label_source, width, height
FROM content.page
WHERE doc_id = %(doc_id)s AND page_no = %(page_no)s
