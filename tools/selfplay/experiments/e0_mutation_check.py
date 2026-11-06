"""Mutation check: the leak test must fail when a hidden zone leaks into the simulator's input."""
import sys
import pytest
from tools.selfplay import features as FT
from MTG_bot.core.state import ZONE_HAND, ZONE_LIBRARY

which = sys.argv[1]
if which == "window":
    FT.PUBLIC = FT.PUBLIC + (ZONE_HAND, ZONE_LIBRARY)
elif which == "public":
    orig = FT.public_cards
    def leaky(executor, player, table):
        world = executor.world
        hand = world.players[player].zones[ZONE_HAND].entries
        import numpy as np
        return np.concatenate([orig(executor, player, table), np.array(sorted(table.row(world.cards[h].identity.oracle_id) for h in hand), np.int16)])
    FT.public_cards = leaky
sys.exit(pytest.main(["-q", "-x", "tools/selfplay/test_simulator.py::test_the_simulator_never_reads_hidden_cards"]))
