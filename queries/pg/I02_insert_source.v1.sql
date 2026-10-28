INSERT INTO registry.source (issuer_id, publisher) VALUES (%(issuer_id)s, %(publisher)s)
ON CONFLICT (issuer_id) DO NOTHING
