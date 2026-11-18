"""How often three reachable STRONGER faults fire in play (KNOWLEDGE/2026-11-18/215): seeded
heuristic games on the deal pools of one checkout (M21, M20, FDN; verified mode; the replay deals
of engine wave E3's replay.py: seeds 930000 + i, stress decks but every third game coherent),
with read-only hooks that change no behaviour:

- F14: an activated or triggered ability resolves after its source changed zones (the `gone`
  source of legality.resolve_activated / TriggerBinder._source_gone), counted per verb class: the
  fault fires when the source is back on the battlefield and the effect acts on "this object"
  with a verb other than PUT_COUNTER;
- F44: at a state-based check, an Aura stays attached to a battlefield host its enchant filter no
  longer allows (CR 704.5m: it should go);
- F45d: an Aura entering by an effect chooses as its host an object entering in the same move
  (CR 303.4f: it may not).

    occurrence.py <checkout> <games per set> <out.json>

Heuristic play stands in for the network's: both are legal play, but the network's choices
differ, so these are rates under heuristic play, a lower bound for a policy that seeks the lines.
"""
from __future__ import annotations

import dataclasses
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
from MTG_bot.core import ability_tree as at  # noqa: E402
from MTG_bot.core.executor import Executor, aura_entry, binding, legality, verbs  # noqa: E402
from MTG_bot.core.executor.events import KIND_ZONE_CHANGE  # noqa: E402
from MTG_bot.core.executor.returns import moved_since  # noqa: E402
from MTG_bot.core.executor.selectors import eval_filter  # noqa: E402
from MTG_bot.core.state import ZONE_BATTLEFIELD  # noqa: E402
from tools.selfplay import rig  # noqa: E402
from tools.selfplay.heuristic import HeuristicAgent  # noqa: E402

counts: Counter = Counter()
examples: dict[str, list[str]] = {}
current = {"game": ""}


def note(key: str, detail: str) -> None:
    counts[key] += 1
    examples.setdefault(key, [])
    if len(examples[key]) < 12:
        examples[key].append(f"{current['game']} {detail}")


def acts_on_source(effect) -> list[str]:
    out = []
    stack = [effect]
    while stack:
        n = stack.pop()
        if isinstance(n, at.Atom):
            for role, val in n.args.pairs:
                if isinstance(val, at.Selector) and (
                        val.referent == "source" or val.referent is None and isinstance(val.filter, at.FAtom)
                        and val.filter.pred is at.FAtomPred.IS_SOURCE):
                    out.append(f"{n.verb.name}.{role}")
        if dataclasses.is_dataclass(n) and not isinstance(n, (at.TokenSpec, at.EmblemSpec)):
            for f in dataclasses.fields(n):
                v = getattr(n, f.name)
                if f.name == "args":
                    stack.extend(val for _r, val in v.pairs if dataclasses.is_dataclass(val))
                elif dataclasses.is_dataclass(v):
                    stack.append(v)
                elif isinstance(v, tuple):
                    stack.extend(x for x in v if dataclasses.is_dataclass(x))
    return out


def name_of(ex, h) -> str:
    card = ex.world.cards.get(h)
    if card is not None:
        return card.identity.name
    lki = ex.departed_lki.get(h)
    return getattr(getattr(lki, "identity", None), "name", str(h))


def classify(ex, source, effect, lane: str) -> None:
    verbs_on_source = acts_on_source(effect)
    back = source in ex.world.cards and ex.world.zone_of(source).kind == ZONE_BATTLEFIELD
    note(f"F14 {lane}: source changed zones while waiting", f"{name_of(ex, source)} back={back}")
    risky = [v for v in verbs_on_source if not v.startswith("PUT_COUNTER")]
    if back and risky:
        note("F14 FIRES: back on the battlefield, a verb acts on it", f"{name_of(ex, source)} {sorted(set(risky))}")


_resolve_activated = legality.resolve_activated


def resolve_activated(executor, obj):
    source = obj.source
    if source.namespace == "card" and (
            source not in executor.world.cards or moved_since(executor.journal, source, obj.declared_clock)):
        classify(executor, source, obj.node.effect, "activated")
    counts["activated abilities resolved"] += 1
    return _resolve_activated(executor, obj)


legality.resolve_activated = resolve_activated
_source_gone = binding.TriggerBinder._source_gone


def source_gone(self, obj):
    out = _source_gone(self, obj)
    counts["triggered abilities resolving"] += 1
    if out:
        classify(self.executor, obj.source, obj.node.effect, "triggered")
    return out


binding.TriggerBinder._source_gone = source_gone
_unattached = Executor._unattached_auras


def unattached_auras(self):
    out = _unattached(self)
    for player in self.world.player_order:
        for card in self.battlefield(player):
            if "ENCHANT" not in self.world.cards[card].identity.keywords or card in out:
                continue
            host = self.attachments.get(card)
            if host is None or host not in self.world.cards or self.world.zone_of(host).kind != ZONE_BATTLEFIELD:
                continue
            ctx = legality.ctx_for(self, card, self.controller_of(card))
            try:
                ok = eval_filter(aura_entry._enchant_filter(self, card), host, ctx)
            except Exception as e:  # noqa: BLE001 - a census row, never a behaviour change
                note("F44 filter unreadable", f"{name_of(self, card)}: {type(e).__name__}")
                continue
            if not ok:
                note("F44 FIRES: an Aura stays on a host its enchant no longer allows",
                     f"{name_of(self, card)} on {name_of(self, host)}")
    return out


Executor._unattached_auras = unattached_auras
_entry_host = verbs._aura_entry_host


def aura_entry_host(ctx, card, player):
    enters, host = _entry_host(ctx, card, player)
    ex = ctx.executor
    counts["Auras entering by an effect"] += 1
    if host is not None and ex is not None:
        last = next((e for e in reversed(ex.journal.events)
                     if e.kind == KIND_ZONE_CHANGE and e.subject == host), None)
        if last is not None and last.zone_move[1] != ZONE_BATTLEFIELD:
            note("F45d FIRES: an Aura enchants an object entering in the same move",
                 f"{name_of(ex, card)} on {name_of(ex, host)}")
    return enters, host


verbs._aura_entry_host = aura_entry_host

n = int(sys.argv[2])
games_played = Counter()
for code in ("M21", "M20", "FDN"):
    for i in range(n):
        current["game"] = f"{code}:{i}"
        res = rig.play_game(930000 + i, [HeuristicAgent(), HeuristicAgent()],
                            deck_mode="stress" if i % 3 else "coherent", pool_mode="verified", set_code=code)
        games_played[code] += 1
        if res["crash"]:
            note("crash", str(res["crash"])[:120])
    print(code, "done", file=sys.stderr)
Path(sys.argv[3]).write_text(json.dumps({"games": games_played, "counts": counts, "examples": examples}, indent=1))
print(json.dumps({"games": games_played, "counts": counts}, indent=1))
