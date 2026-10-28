-- Size (PDF points), printed label and access label of one page (document view: region boxes are in PDF
-- coordinates; round 2 W3: the label decides whether the subject may see the page).
SELECT page_no, page_label, page_label_source, width, height, access
FROM content.page
WHERE doc_id = %(doc_id)s AND page_no = %(page_no)s
