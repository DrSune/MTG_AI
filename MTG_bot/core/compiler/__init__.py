"""compiler — structured ingest and ability-tree compilation of the card pool.

Step 1 of the ability-tree compiler (docs/DESIGN_CARD_POOL.md, "The compiler"):
an MTGJSON v5 pool file is ingested into structured per-card records BEFORE
any template matching, so that nothing downstream ever infers meaning from
English strings (KNOWLEDGE/PITFALLS.md: "English substrings cannot be the
IR"). The scryfall oracle id is the primary key everywhere.

``ingest`` is the file boundary: it owns the split from MTGJSON's shape
(``data.cards`` / ``data.tokens``, the ``text`` field) into
:class:`RawCard` records, which the template compiler (later step) matches.
"""
