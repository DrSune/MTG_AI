"""core — the rebuilt rule engine and card representation.

This package is the D1 rebuild of the environment and the D2 ability-tree
card representation. It replaced the legacy ``rule_engine``/``strategic_brain``
packages, deleted on 2026-11-05 (``git show dbd6e9d:<path>``).

One representation, two consumers (DESIGN_CARD_POOL.md): the engine executes
the ability tree and the network reads that same tree. A card that does not
compile cleanly is simply not in the enabled pool — there is no silent
degradation path.
"""
