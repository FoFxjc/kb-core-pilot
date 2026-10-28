-- aliases and edges are rewritten from concepts.yaml on every load
WITH e AS (DELETE FROM concept.concept_edge) DELETE FROM concept.concept_alias
