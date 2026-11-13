"""Does DESTROY destroy an indestructible permanent (CR 702.12b says it cannot)?"""
import sys

ROOT = sys.argv[1]
sys.path.insert(0, ROOT)
import MTG_bot

assert MTG_bot.__file__.startswith(ROOT), MTG_bot.__file__

from MTG_bot.core.ability_tree import DurationEot, Keyword, KeywordAbility, Verb
from MTG_bot.core.executor import Executor
from MTG_bot.core.state import ZONE_BATTLEFIELD, GameWorld
from MTG_bot.core.test_executor_binding import all_bf, atom, card_id, referent_sel

world = GameWorld(num_players=2, start_life=20, master_seed=11)
p0 = world.player_order[0]
a = world.add_card(card_id("A", "2", "2"), p0, ZONE_BATTLEFIELD)
ex = Executor(world)
ex.execute(atom(Verb.GRANT_ABILITY, target=referent_sel("target"),
                ability=KeywordAbility(keyword=Keyword.INDESTRUCTIBLE), duration=DurationEot()),
           source=a, controller=p0, bindings={"target": a})
ex.layers.recompute()
print("indestructible:", ex.layers.keyword_of(a, Keyword.INDESTRUCTIBLE))
ex.execute(atom(Verb.DESTROY, target=all_bf()), source=a, controller=p0, bindings={"target": a})
print("after DESTROY:", world.zone_of(a).kind)
