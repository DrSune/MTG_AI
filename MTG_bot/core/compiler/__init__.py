"""compiler — structured ingest and ability-tree compilation of the card pool.

``ingest`` turns an MTGJSON v5 pool file into structured per-card records
(:class:`RawCard`) before any template matching, so nothing downstream infers
meaning from English strings; the scryfall oracle id is the primary key
everywhere. ``compiler`` matches each card's sentences against the templates
(``templates`` and the ``templates_b*`` bucket modules) and assembles its
ability tree (docs/DESIGN_CARD_POOL.md, "The compiler").
"""
