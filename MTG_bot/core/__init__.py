"""core — the rules engine and the card representation.

One representation, two consumers (docs/DESIGN_CARD_POOL.md): the engine executes
the ability tree and the network reads that same tree. A card that does not
compile cleanly is not in the enabled pool; there is no silent degradation path.
"""
