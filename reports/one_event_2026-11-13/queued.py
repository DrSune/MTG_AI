"""Every trigger a replay.py game queues on a checkout, with the journal row it matched and how it
resolved: queued.py <checkout> <SET> <i>"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
from MTG_bot.core.executor import binding as B
from tools.selfplay import rig
from tools.selfplay.heuristic import HeuristicAgent

log = []
queue = B.TriggerBinder._queue
resolve = B.TriggerBinder.resolve


def q(self, source, controller, node, event, *a, **k):
    before = len(self.world.triggers)
    out = queue(self, source, controller, node, event, *a, **k)
    if len(self.world.triggers) > before:
        name = self.world.cards[source].identity.name if source in self.world.cards else str(source)
        subj = event.subject
        sname = self.world.cards[subj].identity.name if subj in self.world.cards else str(subj)
        log.append(f"queue @{event.clock} {event.kind} subject={sname} -> {name} {type(node.event).__name__}")
    return out


def r(self, obj):
    out = resolve(self, obj)
    name = self.world.cards[obj.source].identity.name if obj.source in self.world.cards else str(obj.source)
    log.append(f"  resolve {name}: {out} @ journal {self.executor.journal.clock}")
    return out


B.TriggerBinder._queue = q
B.TriggerBinder.resolve = r
i = int(sys.argv[3])
rig.play_game(910000 + i, [HeuristicAgent(), HeuristicAgent()],
              deck_mode="stress" if i % 3 else "coherent", pool_mode="verified", set_code=sys.argv[2])
print("\n".join(log))
