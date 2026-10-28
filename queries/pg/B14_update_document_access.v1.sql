-- A document's access label (round 2 W3): set at import and refreshed by each build from the overlay (labels only go
-- up unless an overlay entry lowers them explicitly with a reason).
UPDATE registry.document SET access = %(access)s WHERE doc_id = %(doc_id)s
